"""
PixelCharm Outreach — Web Server
Scrapes Google Maps, checks each website for outdated signals,
and categorizes leads into: no website, outdated website, or modern website.
"""

import re, os, datetime
from flask import Flask, jsonify, request, send_from_directory
from playwright.sync_api import sync_playwright

app = Flask(__name__, static_folder="static")

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/search")
def search():
    query = request.args.get("q", "small business Halifax")
    limit = min(int(request.args.get("limit", 20)), 40)
    try:
        leads = scrape_google_maps(query, limit)
        return jsonify({"ok": True, "leads": leads})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def check_website_age(browser, url):
    """
    Visit a website and check for outdated signals.
    Returns dict: { outdated: bool, reasons: [str], year: int|None }
    """
    if not url:
        return None

    # Normalise URL
    if not url.startswith("http"):
        url = "https://" + url

    page = None
    try:
        page = browser.new_page()
        page.set_default_timeout(12000)
        page.goto(url, wait_until="domcontentloaded", timeout=12000)
        page.wait_for_timeout(1500)

        html = page.content().lower()
        reasons = []
        current_year = datetime.datetime.now().year

        # 1. Copyright year in footer
        year_found = None
        year_matches = re.findall(r'copyright[^\d]*(\d{4})|©[^\d]*(\d{4})|&copy;[^\d]*(\d{4})', html)
        for match in year_matches:
            for y in match:
                if y:
                    yr = int(y)
                    if 1990 < yr <= current_year:
                        year_found = yr
                        break

        if year_found and year_found <= current_year - 4:
            reasons.append("© " + str(year_found) + " copyright")

        # 2. HTTP only (no SSL)
        if page.url.startswith("http://"):
            reasons.append("no SSL (http://)")

        # 3. Old meta generator tags
        if any(x in html for x in ["wordpress 2.", "wordpress 3.", "wordpress 4.", "joomla 1.", "joomla 2.", "drupal 6", "drupal 7"]):
            reasons.append("outdated CMS version")

        # 4. Table-based layout
        table_count = html.count("<table")
        if table_count > 8:
            reasons.append("table-based layout")

        # 5. Flash or old tech
        if any(x in html for x in ["shockwave-flash", "application/x-flash", ".swf", "silverlight"]):
            reasons.append("uses Flash/Silverlight")

        # 6. No viewport meta tag = not mobile friendly
        if "viewport" not in html:
            reasons.append("not mobile-friendly")

        # 7. Very old jQuery
        old_jquery = re.search(r'jquery[.-](1\.[0-4]\.|0\.)', html)
        if old_jquery:
            reasons.append("outdated jQuery")

        # 8. Page looks like it was built pre-2015 (font tags, marquee, etc.)
        if any(x in html for x in ["<font ", "<marquee", "<blink", "<frameset", "bgcolor="]):
            reasons.append("uses obsolete HTML tags")

        outdated = len(reasons) >= 1

        return {
            "outdated": outdated,
            "reasons": reasons,
            "year": year_found,
            "url": page.url
        }

    except Exception as e:
        print("[website-check] error on " + url + ": " + str(e))
        return {"outdated": False, "reasons": [], "year": None, "url": url}
    finally:
        if page:
            try: page.close()
            except: pass


def scrape_google_maps(query, max_results):
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )

        # Search page
        page = browser.new_page()
        page.set_extra_http_headers({
            "Accept-Language": "en-CA,en;q=0.9",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
        })

        url = "https://www.google.com/maps/search/" + query.replace(" ", "+") + "/"
        print("[scraper] " + url)
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        # Scroll to load more
        for _ in range(8):
            try:
                panel = page.locator('[role="feed"]').first
                panel.evaluate("el => el.scrollBy(0, 800)")
                page.wait_for_timeout(600)
            except:
                break

        # Collect listing links
        links = page.locator('a[href*="/maps/place/"]').all()
        hrefs, seen = [], set()
        for link in links:
            try:
                href = link.get_attribute("href")
                if href and href not in seen and "/maps/place/" in href:
                    seen.add(href)
                    hrefs.append(href)
            except:
                pass

        page.close()
        print("[scraper] " + str(len(hrefs)) + " listings found, checking up to " + str(max_results))

        for i, href in enumerate(hrefs[:max_results]):
            detail_page = None
            try:
                print("[scraper] " + str(i+1) + "/" + str(min(len(hrefs), max_results)) + " fetching details...")
                detail_page = browser.new_page()
                detail_page.goto(href, wait_until="networkidle", timeout=20000)
                detail_page.wait_for_timeout(1200)

                name = ""
                try: name = detail_page.locator("h1").first.inner_text(timeout=3000).strip()
                except: pass

                address = ""
                try: address = detail_page.locator('[data-item-id="address"]').first.inner_text(timeout=3000).strip()
                except: pass

                phone = ""
                try: phone = detail_page.locator('[data-item-id^="phone"]').first.inner_text(timeout=3000).strip()
                except:
                    try:
                        m = re.search(r'tel:([+\d\-\(\)\s]{7,20})', detail_page.content())
                        if m: phone = m.group(1).strip()
                    except: pass

                website = ""
                try: website = detail_page.locator('[data-item-id="authority"]').first.inner_text(timeout=3000).strip()
                except:
                    try: website = detail_page.locator('a[data-item-id="authority"]').first.get_attribute("href", timeout=3000) or ""
                    except: pass

                detail_page.close()
                detail_page = None

                if not name:
                    continue

                # Categorise based on website presence + age check
                website_check = None
                category = "no_website"

                if website:
                    print("[website-check] checking " + website)
                    website_check = check_website_age(browser, website)
                    if website_check and website_check["outdated"]:
                        category = "outdated_website"
                    else:
                        category = "modern_website"

                lead = {
                    "id": "gm-" + str(len(results)),
                    "name": name,
                    "address": address,
                    "phone": phone,
                    "website": website,
                    "email": "",
                    "status": "new",
                    "category": category,
                    "outdated_reasons": website_check["reasons"] if website_check else [],
                    "copyright_year": website_check["year"] if website_check else None
                }
                results.append(lead)
                print("[scraper] + " + name + " [" + category + "]")

            except Exception as e:
                print("[scraper] skip: " + str(e))
            finally:
                if detail_page:
                    try: detail_page.close()
                    except: pass

        browser.close()
    return results


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7842))
    app.run(host="0.0.0.0", port=port, debug=False)
