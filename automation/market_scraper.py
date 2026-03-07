"""
Punta Cana Market Data Scraper
Runs daily via Railway cron. Scrapes Airbnb rates, tourism stats,
and property listings. Outputs to data/market-pulse.json.
"""

import json
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_FILE = DATA_DIR / "market-pulse.json"
HISTORY_FILE = DATA_DIR / "market-pulse-history.json"

NEIGHBORHOODS = [
    "Los Corales",
    "Cocotal",
    "Cap Cana",
    "Bavaro",
    "El Cortecito",
    "Downtown Punta Cana",
    "Uvero Alto",
    "Macao",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

REQUEST_DELAY = (2, 5)  # seconds between requests (min, max)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("market_scraper")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return s


def _rate_limit():
    delay = random.uniform(*REQUEST_DELAY)
    time.sleep(delay)


def _safe_get(session: requests.Session, url: str, params: dict | None = None,
              timeout: int = 30) -> requests.Response | None:
    """GET with error handling and user-agent rotation."""
    session.headers["User-Agent"] = random.choice(USER_AGENTS)
    try:
        resp = session.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        log.warning("Request failed for %s: %s", url, e)
        return None


def _extract_numbers(text: str) -> list[float]:
    """Pull all numeric values from a string."""
    results = []
    for x in re.findall(r"[\d,]+\.?\d*", text):
        cleaned = x.replace(",", "").strip(".")
        if cleaned and cleaned.replace(".", "").isdigit():
            try:
                results.append(float(cleaned))
            except ValueError:
                continue
    return results


# ---------------------------------------------------------------------------
# 1. Airbnb neighborhood rates (via search page scraping)
# ---------------------------------------------------------------------------


def _scrape_airbnb_api(session: requests.Session, neighborhood: str) -> dict | None:
    """
    Try Airbnb's internal StaysSearch API endpoint (returns JSON).
    This is the same endpoint the Airbnb SPA calls under the hood.
    """
    api_url = "https://www.airbnb.com/api/v3/StaysSearch"
    query = f"{neighborhood} Punta Cana Dominican Republic"

    # Airbnb API requires specific headers and an API key embedded in the page.
    # We first fetch the search page to grab the key from meta/script tags.
    search_url = "https://www.airbnb.com/s/" + requests.utils.quote(query) + "/homes"
    resp = _safe_get(session, search_url)
    if not resp:
        return None

    # Extract API key from page source
    api_key_match = re.search(r'"key"\s*:\s*"(d306zoyjsyarp7ifhu67rjxn52tv0t)"', resp.text)
    if not api_key_match:
        # Try common known Airbnb public API key
        api_key = "d306zoyjsyarp7ifhu67rjxn52tv0t"
    else:
        api_key = api_key_match.group(1)

    # Try to extract dehydrated data from the SSR page (Airbnb embeds search results as JSON)
    prices = []
    ratings = []
    prop_types: dict[str, int] = {}

    # Look for the large JSON blob containing search results
    for pattern in [
        r'<script\s+id="data-delorian-state"[^>]*>(.*?)</script>',
        r'<script\s+data-state="true"[^>]*>(.*?)</script>',
        r'<!--(.*?)-->',
    ]:
        matches = re.findall(pattern, resp.text, re.DOTALL)
        for match in matches:
            if len(match) < 500:
                continue
            # Look for price patterns in JSON blobs
            price_matches = re.findall(
                r'"priceString"\s*:\s*"\$(\d+)"', match
            )
            for p in price_matches:
                val = float(p)
                if 20 < val < 2000:
                    prices.append(val)

            price_matches2 = re.findall(
                r'"price"\s*:\s*"?\$?(\d+)"?', match
            )
            for p in price_matches2:
                val = float(p)
                if 30 < val < 1500:
                    prices.append(val)

            rating_matches = re.findall(
                r'"avgRating(?:Localized)?"\s*:\s*"?([\d.]+)"?', match
            )
            for r_val in rating_matches:
                val = float(r_val)
                if 1 <= val <= 5:
                    ratings.append(val)

            type_matches = re.findall(r'"roomType"\s*:\s*"([^"]+)"', match)
            for t in type_matches:
                prop_types[t] = prop_types.get(t, 0) + 1

    # Also try standard script tags with application/json
    soup = BeautifulSoup(resp.text, "html.parser")
    for script in soup.find_all("script", type="application/json"):
        try:
            text = script.string or ""
            if len(text) < 200:
                continue
            for p in re.findall(r'"priceString"\s*:\s*"\$(\d+)"', text):
                val = float(p)
                if 20 < val < 2000:
                    prices.append(val)
            for r_val in re.findall(r'"avgRating"\s*:\s*([\d.]+)', text):
                val = float(r_val)
                if 1 <= val <= 5:
                    ratings.append(val)
            for t in re.findall(r'"roomType"\s*:\s*"([^"]+)"', text):
                prop_types[t] = prop_types.get(t, 0) + 1
        except Exception:
            continue

    if prices:
        # Deduplicate (same price might appear in multiple blobs)
        prices = list(set(prices))
        return {
            "listings_sampled": len(prices),
            "avg_nightly_rate": round(sum(prices) / len(prices), 2),
            "min_nightly_rate": round(min(prices), 2),
            "max_nightly_rate": round(max(prices), 2),
            "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "property_types": prop_types,
        }
    return None


# Baseline market data from verified 2026 research sources (TheLatinvestor, Airbtics, AirROI).
# Used as fallback when live scraping is blocked. Updated manually when new research is done.
BASELINE_RATES = {
    "Los Corales":         {"avg_nightly_rate": 120, "min_nightly_rate": 65, "max_nightly_rate": 280, "avg_rating": 4.65, "yield_range": "7-12%"},
    "El Cortecito":        {"avg_nightly_rate": 115, "min_nightly_rate": 60, "max_nightly_rate": 260, "avg_rating": 4.60, "yield_range": "7-11%"},
    "Cocotal":             {"avg_nightly_rate": 105, "min_nightly_rate": 55, "max_nightly_rate": 220, "avg_rating": 4.70, "yield_range": "6-10%"},
    "Downtown Punta Cana": {"avg_nightly_rate": 95,  "min_nightly_rate": 50, "max_nightly_rate": 200, "avg_rating": 4.55, "yield_range": "6-10%"},
    "Cap Cana":            {"avg_nightly_rate": 165, "min_nightly_rate": 80, "max_nightly_rate": 450, "avg_rating": 4.80, "yield_range": "5-8%"},
    "Bavaro":              {"avg_nightly_rate": 110, "min_nightly_rate": 55, "max_nightly_rate": 240, "avg_rating": 4.60, "yield_range": "6-10%"},
    "Uvero Alto":          {"avg_nightly_rate": 125, "min_nightly_rate": 65, "max_nightly_rate": 300, "avg_rating": 4.70, "yield_range": "5-8%"},
    "Macao":               {"avg_nightly_rate": 105, "min_nightly_rate": 50, "max_nightly_rate": 220, "avg_rating": 4.55, "yield_range": "4-7%"},
}


def scrape_airbnb_rates(session: requests.Session) -> list[dict]:
    """
    Scrape Airbnb search results for Punta Cana neighborhoods.
    Tries live scraping first, falls back to baseline research data.
    """
    results = []

    for neighborhood in NEIGHBORHOODS:
        log.info("Scraping Airbnb rates for: %s", neighborhood)
        _rate_limit()

        entry = {
            "neighborhood": neighborhood,
            "listings_sampled": 0,
            "avg_nightly_rate": None,
            "min_nightly_rate": None,
            "max_nightly_rate": None,
            "avg_rating": None,
            "property_types": {},
            "yield_range": None,
            "source": "airbnb_search",
            "scraped": False,
        }

        # Try live scraping
        live_data = _scrape_airbnb_api(session, neighborhood)
        if live_data and live_data.get("listings_sampled", 0) >= 3:
            entry.update(live_data)
            entry["scraped"] = True
            entry["source"] = "airbnb_live"
            log.info("  Live data: %d listings, avg $%.0f/night",
                     entry["listings_sampled"], entry["avg_nightly_rate"])
        else:
            # Fallback to baseline research data
            baseline = BASELINE_RATES.get(neighborhood)
            if baseline:
                entry.update(baseline)
                entry["listings_sampled"] = 0
                entry["source"] = "baseline_research_2026"
                entry["scraped"] = False
                log.info("  Using baseline: avg $%.0f/night", entry["avg_nightly_rate"])

        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# 2. Tourism statistics from public sources
# ---------------------------------------------------------------------------


def scrape_tourism_stats(session: requests.Session) -> dict:
    """Scrape tourism arrival data from public news/government sources."""
    log.info("Scraping tourism statistics...")
    stats: dict[str, Any] = {
        "source_urls": [],
        "latest_data": {},
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    # Source 1: Tourism Analytics
    _rate_limit()
    resp = _safe_get(session, "https://tourismanalytics.com/puntacana-statistics.html")
    if resp:
        stats["source_urls"].append("https://tourismanalytics.com/puntacana-statistics.html")
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(separator=" ")

        # Extract key figures
        arrivals_match = re.search(r"([\d,.]+)\s*(?:million|M)?\s*(?:visitors?|tourist|arrivals?)", text, re.I)
        if arrivals_match:
            stats["latest_data"]["visitor_figure_raw"] = arrivals_match.group(0).strip()

        growth_match = re.search(r"(\+?-?\d+\.?\d*)\s*%?\s*(?:growth|increase|change)", text, re.I)
        if growth_match:
            stats["latest_data"]["growth_pct_raw"] = growth_match.group(0).strip()

        # Try to find Punta Cana airport share
        share_match = re.search(r"Punta\s*Cana.*?(\d+\.?\d*)\s*%", text, re.I)
        if share_match:
            stats["latest_data"]["punta_cana_airport_share"] = f"{share_match.group(1)}%"

    # Source 2: Dominican Today tourism section
    _rate_limit()
    resp = _safe_get(session, "https://dominicantoday.com/dr/tourism/")
    if resp:
        stats["source_urls"].append("https://dominicantoday.com/dr/tourism/")
        soup = BeautifulSoup(resp.text, "html.parser")

        headlines = []
        for article in soup.select("article, .entry-title, h2 a, h3 a")[:10]:
            title = article.get_text(strip=True)
            link = article.get("href") or (article.find("a") or {}).get("href", "")
            if title and len(title) > 10:
                headlines.append({"title": title[:200], "url": str(link)})
        stats["latest_data"]["recent_headlines"] = headlines[:5]

    # Source 3: DR1 tourism news
    _rate_limit()
    resp = _safe_get(session, "https://dr1.com/news/category/tourism/")
    if resp:
        stats["source_urls"].append("https://dr1.com/news/category/tourism/")
        soup = BeautifulSoup(resp.text, "html.parser")

        headlines = []
        for a_tag in soup.select("h2 a, h3 a, .entry-title a")[:5]:
            title = a_tag.get_text(strip=True)
            link = a_tag.get("href", "")
            if title:
                headlines.append({"title": title[:200], "url": link})
        if headlines:
            stats["latest_data"]["dr1_headlines"] = headlines

    return stats


# ---------------------------------------------------------------------------
# 3. Property listings from DR real estate sites
# ---------------------------------------------------------------------------


def _extract_listing_from_card(card, source: str) -> dict | None:
    """Generic listing extractor for property cards."""
    title_el = card.find(["h2", "h3", "h4"]) or card.find("a")
    price_el = (
        card.find(class_=re.compile(r"price|cost|amount", re.I))
        or card.find(string=re.compile(r"\$[\d,]+"))
    )
    location_el = card.find(class_=re.compile(r"location|address|area|neighborhood", re.I))

    title = title_el.get_text(strip=True) if title_el else ""
    if not title or len(title) < 5:
        return None

    price_text = ""
    if price_el:
        price_text = price_el if isinstance(price_el, str) else price_el.get_text(strip=True)

    location = location_el.get_text(strip=True) if location_el else ""

    link = ""
    if title_el:
        if title_el.name == "a":
            link = title_el.get("href", "")
        else:
            a = title_el.find("a")
            if a:
                link = a.get("href", "")

    price_num = None
    for n in _extract_numbers(str(price_text)):
        if n > 10000:
            price_num = n
            break

    return {
        "title": title[:200],
        "price_text": str(price_text)[:100],
        "price_usd": price_num,
        "location": location[:100],
        "url": link,
        "source": source,
    }


def scrape_property_listings(session: requests.Session) -> list[dict]:
    """Check DR property listing sites for Punta Cana listings and prices."""
    log.info("Scraping property listings...")
    listings = []

    sources = [
        (
            "https://puntacanavilla.com/label/new-construction-for-sale-properties-punta-cana/",
            "puntacanavilla.com",
        ),
        ("https://everythingpuntacana.com/real-estate/", "everythingpuntacana.com"),
        (
            "https://gopuntacanarealestate.com/dominican-republic-pre-construction-deals/",
            "gopuntacanarealestate.com",
        ),
    ]

    card_selectors = "article, .property-item, .listing-item, .listing-card, .property, .property-card, .hentry"

    for url, source_name in sources:
        _rate_limit()
        resp = _safe_get(session, url)
        if not resp:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select(card_selectors)[:20]

        # Fallback: if no cards found, try any link that contains a price-like string
        if not cards:
            for a_tag in soup.find_all("a", href=True):
                text = a_tag.get_text(strip=True)
                if re.search(r"\$[\d,]+", text) and len(text) > 10:
                    entry = {
                        "title": text[:200],
                        "price_text": "",
                        "price_usd": None,
                        "location": "",
                        "url": a_tag["href"],
                        "source": source_name,
                    }
                    for n in _extract_numbers(text):
                        if n > 10000:
                            entry["price_usd"] = n
                            break
                    listings.append(entry)
            continue

        for card in cards:
            entry = _extract_listing_from_card(card, source_name)
            if entry:
                listings.append(entry)

        log.info("  %s: found %d cards", source_name, len(cards))

    # Source 4: TheLatinvestor market intel (articles with pricing data)
    _rate_limit()
    resp = _safe_get(session, "https://thelatinvestor.com/blogs/news/punta-cana-housing-prices")
    if resp:
        soup = BeautifulSoup(resp.text, "html.parser")
        article_body = soup.find("article") or soup.find(class_=re.compile(r"article|blog|content|entry", re.I))
        if article_body:
            text = article_body.get_text(separator=" ")
            # Extract any price-per-sqm data
            sqm_matches = re.findall(
                r"\$?([\d,]+)\s*(?:per|/)\s*(?:sq(?:uare)?\s*m(?:eter)?|m2|m²|sqm)",
                text, re.I,
            )
            if sqm_matches:
                listings.append({
                    "title": "TheLatinvestor Price/m2 Data (2026)",
                    "price_text": f"Prices/m2 found: {', '.join(f'${m}' for m in sqm_matches[:6])}",
                    "price_usd": None,
                    "location": "Punta Cana (various)",
                    "url": "https://thelatinvestor.com/blogs/news/punta-cana-housing-prices",
                    "source": "thelatinvestor.com",
                    "price_per_sqm_samples": [
                        float(m.replace(",", "")) for m in sqm_matches[:6] if m.replace(",", "").replace(".", "").isdigit()
                    ],
                })

    return listings


# ---------------------------------------------------------------------------
# Output & History
# ---------------------------------------------------------------------------


def save_snapshot(data: dict):
    """Save current snapshot and append to history."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Write latest snapshot
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    log.info("Saved snapshot to %s", OUTPUT_FILE)

    # Append to history
    history: list[dict] = []
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, IOError):
            history = []

    history.append(data)

    # Keep last 365 daily snapshots
    if len(history) > 365:
        history = history[-365:]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False, default=str)
    log.info("Appended to history (%d total snapshots)", len(history))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run():
    log.info("=== Punta Cana Market Scraper starting ===")
    start = time.time()
    session = _session()

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "airbnb_rates": [],
        "tourism_stats": {},
        "property_listings": [],
        "meta": {
            "scraper_version": "1.0.0",
            "neighborhoods_tracked": NEIGHBORHOODS,
            "duration_seconds": 0,
            "errors": [],
        },
    }

    # 1. Airbnb rates
    try:
        snapshot["airbnb_rates"] = scrape_airbnb_rates(session)
        log.info("Airbnb: scraped %d neighborhoods", len(snapshot["airbnb_rates"]))
    except Exception as e:
        log.error("Airbnb scraping failed: %s", e)
        snapshot["meta"]["errors"].append(f"airbnb: {e}")

    # 2. Tourism stats
    try:
        snapshot["tourism_stats"] = scrape_tourism_stats(session)
        log.info("Tourism stats collected")
    except Exception as e:
        log.error("Tourism stats failed: %s", e)
        snapshot["meta"]["errors"].append(f"tourism: {e}")

    # 3. Property listings
    try:
        snapshot["property_listings"] = scrape_property_listings(session)
        log.info("Property listings: found %d", len(snapshot["property_listings"]))
    except Exception as e:
        log.error("Property listings failed: %s", e)
        snapshot["meta"]["errors"].append(f"listings: {e}")

    elapsed = round(time.time() - start, 1)
    snapshot["meta"]["duration_seconds"] = elapsed
    log.info("Scraping completed in %.1fs", elapsed)

    save_snapshot(snapshot)
    log.info("=== Scraper finished ===")

    return snapshot


if __name__ == "__main__":
    run()
