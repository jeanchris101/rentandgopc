# Automation Architecture

Automated pipelines for the Rent & Go PC property website. All automation runs via GitHub Actions with data stored in `automation/data/`.

## Pipelines

### 1. Weekly Data Refresh (Sunday 11 PM UTC / 7 PM DR)

**Workflow:** `.github/workflows/weekly-refresh.yml`

```
automation/data/market-pulse.json   -->  refresh-site-data.js  -->  market-intel.html
automation/data/airbnb-rates.json   -->                        -->  roi-calculator.html
                                                               -->  git commit + push
                                                               -->  Vercel redeploy
```

**What it does:**
- Reads latest scraped data from `automation/data/` JSON files
- Updates hardcoded values in `market-intel.html` (zone ADR, occupancy, revenue, seasonal heatmap, insights)
- Updates defaults and data tables in `roi-calculator.html`
- Commits changes only if data actually changed
- Triggers Vercel redeployment via webhook

**Data sources** (populated by the market scraper or manual updates):
- `market-pulse.json` — Property prices, tourism stats, market trends
- `airbnb-rates.json` — Per-zone ADR, occupancy, revenue estimates

### 2. Daily Content Generation & Posting (1 PM UTC / 9 AM DR)

**Workflow:** `.github/workflows/daily-content.yml`

```
config.json  -->  content_generator.py  -->  post text + image selection
                  (Claude Haiku)        -->  fb_autoposter.py  -->  Facebook Page
                                        -->  content-log.json
```

**What it does:**
- Generates one social media post per day using Claude Haiku (budget: $0.25/day)
- Rotates through post types: property spotlight, neighborhood guide, market insight, lifestyle, testimonial, ROI breakdown
- Outputs in English, Spanish, and French
- Posts to Facebook Page via Graph API
- Logs all generated content to `automation/data/content-log.json`

**Manual trigger:** Can run manually from GitHub Actions with option to skip posting (generate content only).

### 3. Market Data Scraper (Railway Cron — Daily 8 AM UTC)

**Script:** `automation/scripts/market_scraper.py` (deployed separately on Railway)

Collects Punta Cana real estate market data daily:
- Airbnb nightly rates and occupancy by neighborhood
- Tourism arrival statistics from public sources
- Property listing prices from DR real estate sites

**Railway setup:**
- Root directory: `automation/`
- Start command: `python scripts/market_scraper.py`
- Cron schedule: `0 8 * * *`
- Attach a volume to `/app/data/` for persistent storage
- No API keys required (scrapes public pages only)

**Output:** `data/market-pulse.json` (latest) and `data/market-pulse-history.json` (daily snapshots, max 365).

### 4. Airbnb Rate Tracker (Railway Cron — Daily 9 AM UTC)

**Script:** `automation/airbnb_tracker.py`

Tracks comparable Airbnb listings across 6 Punta Cana neighborhoods. Snapshots nightly rates, calculates week-over-week trends, and flags underpriced opportunities.

**Neighborhoods:** Los Corales, Cap Cana, Cocotal Golf, Downtown Bavaro, Arena Gorda, Palma Real

**Usage:**
```bash
python airbnb_tracker.py              # Full run: scrape + analyze
python airbnb_tracker.py --analyze    # Analyze only (no scraping)
python airbnb_tracker.py --summary    # Print latest summary
```

**Railway setup:**
- Root directory: `automation/`
- Start command: `python airbnb_tracker.py`
- Cron schedule: `0 9 * * *`
- Attach a volume to `/app/data/` for persistent storage
- No API keys required (scrapes public search pages only)

**Anti-scraping measures:**
- Rotates 6 user agent profiles per request
- Random 4-8s delays between neighborhoods
- HTTP 429 backoff (30s, 60s)
- Max 2 retries per neighborhood
- Browser-like headers (Sec-Fetch-*, Accept, etc.)

**Output:**
- `data/airbnb-rates.json` — Historical snapshots (90 days retained). Per-neighborhood listing data with prices, ratings, room types.
- `data/airbnb-summary.json` — Latest analysis: avg rates, week-over-week trends, underpriced listing opportunities (20%+ below neighborhood avg).

### 5. Facebook Auto-Poster

**Script:** `fb_autoposter.py`

Reads from `data/content-queue.json` (produced by `content_generator.py`) and publishes to the Facebook Page via Graph API.

**Supports two queue formats:**
- **Content generator format:** `{id, type, topic, content: {en: {text, hashtags}, ...}, status}` — auto-normalizes per language
- **Direct format:** `{id, message, image_url, link, language, category, status}` — posts as-is

**Commands:**
```bash
python fb_autoposter.py              # Post next pending item
python fb_autoposter.py --dry-run    # Preview without posting
python fb_autoposter.py --status     # Show queue & log status
python fb_autoposter.py --schedule   # Continuous mode (posts at 9am/12pm/6pm ET)
python fb_autoposter.py --lang en    # Post next English item only
python fb_autoposter.py --init       # Create sample queue
python fb_autoposter.py --verify     # Test Facebook token
```

**Rate limits:** Max 3 posts/day (configurable), 5-minute minimum between posts.

**Post log:** All activity logged to `data/post-log.json` with timestamps, FB post IDs, and errors.

**Facebook Page Token Setup:**
1. Create a Facebook App at developers.facebook.com (type: Business)
2. Request permissions: `pages_manage_posts`, `pages_read_engagement`
3. Generate a User Token via Graph API Explorer
4. Exchange for a long-lived token: `GET /oauth/access_token?grant_type=fb_exchange_token&...`
5. Get Page Token: `GET /me/accounts?access_token={long-lived-user-token}`
6. Set env vars: `FB_PAGE_ID` and `FB_PAGE_ACCESS_TOKEN`

---

## Configuration

All configurable values live in `automation/config.json`:

| Section | What it controls |
|---------|-----------------|
| `neighborhoods` | Zone names, ADR ranges, occupancy, price ranges, price/m2 |
| `market_stats` | Median prices, ADR benchmarks, occupancy averages, tourism data |
| `schedule` | Cron schedules, timezone, post times |
| `budget_caps` | AI spending limits (daily/monthly), ad budget caps |
| `content` | Languages, post types, hashtags, max posts/day |
| `facebook` | Page ID and access token env var names |
| `vercel` | Deploy hook env var name |
| `data_sources` | File paths for all JSON data files |

## Directory Structure

```
automation/
  config.json              # Shared configuration
  airbnb_tracker.py        # Daily Airbnb rate tracker (Pipeline 4)
  README.md                # This file
  data/
    market-pulse.json      # Market data (prices, tourism, trends)
    airbnb-rates.json      # Per-zone Airbnb rate snapshots (90-day history)
    airbnb-summary.json    # Latest rate analysis and opportunities
    content-log.json       # History of generated posts
  scripts/
    refresh-site-data.js   # Reads JSON data, updates HTML files
    market_scraper.py      # Daily market data collection
    content_generator.py   # AI-powered post generation (Haiku)
    fb_autoposter.py       # Facebook Graph API posting

.github/workflows/
  weekly-refresh.yml       # Sunday data refresh + Vercel redeploy
  daily-content.yml        # Daily AI content + Facebook posting
```

## Required Secrets (GitHub Actions)

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key for content generation |
| `FB_PAGE_ACCESS_TOKEN` | Facebook Page long-lived access token |
| `FB_PAGE_ID` | Facebook Page ID |
| `VERCEL_DEPLOY_HOOK` | Vercel deploy hook URL for redeployment |

## Running Locally

Workflows can be triggered manually from the GitHub Actions tab. For local testing:

```bash
# Market scraper
python automation/scripts/market_scraper.py

# Weekly refresh
node automation/scripts/refresh-site-data.js

# Content generation (requires ANTHROPIC_API_KEY env var)
python automation/scripts/content_generator.py

# Facebook posting (requires FB_* env vars)
python automation/scripts/fb_autoposter.py
```

## Budget Controls

- AI content generation: $0.25/day cap ($7.50/month) using Claude Haiku
- Facebook ads: $0 default (manual boost only)
- All caps configured in `config.json` under `budget_caps`
- The content generator checks the daily spend log before making API calls

## Neighborhoods Tracked

Los Corales, Cocotal, Cap Cana, Bavaro, El Cortecito, Downtown Punta Cana, Uvero Alto, Vista Cana

## Output Format (market-pulse.json)

- `airbnb_rates`: Per-neighborhood nightly rates, ratings, property types
- `tourism_stats`: Latest visitor arrival data and news headlines
- `property_listings`: New listings with prices from DR real estate sites
- `meta`: Scraper version, duration, errors
