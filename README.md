# PixelCharm Outreach

AI-powered lead gen + email outreach tool for local businesses.

## Deploy to Railway (free, 5 minutes)

1. Create a free account at **github.com** if you don't have one
2. Create a new repository called `pixelcharm-outreach`
3. Upload all these files to it (drag and drop on GitHub)
4. Go to **railway.app** → New Project → Deploy from GitHub repo
5. Select your repo → Railway auto-detects everything and deploys
6. Click the generated URL — your app is live for anyone to use

## Run locally

```bash
pip install flask playwright
python -m playwright install chromium
python server.py
# open http://localhost:7842
```

## Files

- `server.py` — Flask server + Google Maps scraper
- `static/index.html` — The full app frontend
- `requirements.txt` — Python dependencies
- `nixpacks.toml` — Railway build config
- `Procfile` — Railway start command
