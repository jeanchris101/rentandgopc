"""
Airbnb Rate Tracker — Punta Cana Neighborhoods
Scrapes Airbnb search results for comparable listings, stores daily snapshots,
calculates trends, and flags pricing opportunities.

Designed to run as a daily Railway cron job.

Usage:
    python airbnb_tracker.py              # Full run: scrape + analyze
    python airbnb_tracker.py --analyze    # Analyze only (no scraping)
    python airbnb_tracker.py --summary    # Print latest summary to stdout
"""

import json
import os
import sys
import time
import random
import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
RATES_FILE = DATA_DIR / "airbnb-rates.json"
SUMMARY_FILE = DATA_DIR / "airbnb-summary.json"

HISTORY_DAYS = 90  # Keep 90 days of snapshots

# Punta Cana neighborhoods to track
NEIGHBORHOODS = {
    "los_corales": {
        "name": "Los Corales / El Cortecito",
        "lat": 18.6808,
        "lng": -68.4096,
        "zoom": 14,
        "description": "Walkable beach area, studios to 2BR condos",
    },
    "cap_cana": {
        "name": "Cap Cana",
        "lat": 18.5218,
        "lng": -68.3693,
        "zoom": 13,
        "description": "Luxury gated community, villas and premium condos",
    },
    "cocotal": {
        "name": "Cocotal Golf",
        "lat": 18.6510,
        "lng": -68.3900,
        "zoom": 14,
        "description": "Golf resort community, mid-range condos and penthouses",
    },
    "bavaro_downtown": {
        "name": "Downtown Bavaro",
        "lat": 18.6700,
        "lng": -68.4200,
        "zoom": 14,
        "description": "Local area, budget apartments",
    },
    "arena_gorda": {
        "name": "Arena Gorda / Cana Bay",
        "lat": 18.7050,
        "lng": -68.3850,
        "zoom": 14,
        "description": "Resort corridor, family-friendly condos",
    },
    "palma_real": {
        "name": "Palma Real / Bavaro",
        "lat": 18.6630,
        "lng": -68.4050,
        "zoom": 14,
        "description": "Residential area, townhouses and villas",
    },
}

# Check-in/check-out window for search (2 weeks out, 3-night stay)
SEARCH_CHECKIN_OFFSET_DAYS = 14
SEARCH_NIGHTS = 3

# Rate limiting
MIN_DELAY_SECONDS = 4
MAX_DELAY_SECONDS = 8
MAX_RETRIES = 2

# Rotating user agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("airbnb_tracker")


# ---------------------------------------------------------------------------
# Data persistence
# ---------------------------------------------------------------------------

def load_rates_data() -> dict:
    """Load the historical rates JSON file."""
    if RATES_FILE.exists():
        try:
            with open(RATES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            log.warning("Failed to load rates file, starting fresh: %s", e)
    return {"snapshots": [], "metadata": {"created": datetime.utcnow().isoformat()}}


def save_rates_data(data: dict):
    """Save rates data, pruning snapshots older than HISTORY_DAYS."""
    cutoff = (datetime.utcnow() - timedelta(days=HISTORY_DAYS)).isoformat()
    data["snapshots"] = [
        s for s in data["snapshots"] if s.get("date", "") >= cutoff[:10]
    ]
    data["metadata"]["last_updated"] = datetime.utcnow().isoformat()
    data["metadata"]["snapshot_count"] = len(data["snapshots"])

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(RATES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info("Saved %d snapshots to %s", len(data["snapshots"]), RATES_FILE)


def save_summary(summary: dict):
    """Save the analysis summary."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    log.info("Summary saved to %s", SUMMARY_FILE)


# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------

def create_session() -> requests.Session:
    """Create a requests session with browser-like headers."""
    session = requests.Session()
    ua = random.choice(USER_AGENTS)
    session.headers.update({
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    })
    return session


def rate_limit_delay():
    """Random delay between requests to avoid rate limiting."""
    delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
    log.debug("Sleeping %.1fs", delay)
    time.sleep(delay)


# ---------------------------------------------------------------------------
# Scraping — Airbnb search results
# ---------------------------------------------------------------------------

def build_search_url(neighborhood: dict, checkin: str, checkout: str) -> str:
    """Build an Airbnb search URL for a neighborhood."""
    params = {
        "refinement_paths[]": "/homes",
        "checkin": checkin,
        "checkout": checkout,
        "adults": "2",
        "search_type": "filter_change",
        "tab_id": "home_tab",
        "query": f"{neighborhood['name']}, Punta Cana, Dominican Republic",
        "place_id": "",  # Let Airbnb resolve from query
    }
    base = "https://www.airbnb.com/s/Punta-Cana--Dominican-Republic/homes"
    qs = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
    return f"{base}?{qs}"


def extract_listings_from_html(html: str) -> list[dict]:
    """
    Extract listing data from Airbnb search results HTML.

    Airbnb renders most content client-side, but embeds structured data in
    <script> tags as JSON (type="application/json" with data-deferred-state
    or embedded in __NEXT_DATA__). We try multiple extraction strategies.
    """
    listings = []

    # Strategy 1: Look for JSON-LD structured data
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                for item in data:
                    listing = _parse_jsonld_item(item)
                    if listing:
                        listings.append(listing)
            elif isinstance(data, dict):
                listing = _parse_jsonld_item(data)
                if listing:
                    listings.append(listing)
        except (json.JSONDecodeError, TypeError):
            continue

    # Strategy 2: Look for deferred state / NEXT_DATA JSON blobs
    if not listings:
        for script in soup.find_all("script", id="data-deferred-state"):
            listings.extend(_parse_deferred_state(script.string or ""))

    if not listings:
        for script in soup.find_all("script"):
            text = script.string or ""
            if "__NEXT_DATA__" in text or "StaysSearch" in text:
                listings.extend(_parse_next_data(text))

    # Strategy 3: Parse meta tags and visible elements as fallback
    if not listings:
        listings.extend(_parse_meta_fallback(soup))

    # Deduplicate by listing ID
    seen = set()
    unique = []
    for lst in listings:
        lid = lst.get("listing_id", "")
        if lid and lid not in seen:
            seen.add(lid)
            unique.append(lst)
        elif not lid:
            unique.append(lst)

    return unique


def _parse_jsonld_item(item: dict) -> Optional[dict]:
    """Parse a JSON-LD item into our listing format."""
    if item.get("@type") not in ("LodgingBusiness", "VacationRental", "Product", "Accommodation"):
        return None
    price_spec = item.get("priceRange") or item.get("offers", {})
    price = None
    if isinstance(price_spec, dict):
        price = price_spec.get("price") or price_spec.get("lowPrice")
    elif isinstance(price_spec, str):
        # Try to extract number from "$100 - $200" format
        import re
        nums = re.findall(r"\d+", price_spec)
        if nums:
            price = int(nums[0])

    return {
        "listing_id": str(item.get("identifier", item.get("url", ""))).split("/")[-1],
        "name": item.get("name", ""),
        "price_per_night": _to_float(price),
        "rating": _to_float(item.get("aggregateRating", {}).get("ratingValue")),
        "reviews_count": _to_int(item.get("aggregateRating", {}).get("reviewCount")),
        "url": item.get("url", ""),
    }


def _parse_deferred_state(text: str) -> list[dict]:
    """Parse Airbnb's deferred state JSON for listing data."""
    listings = []
    try:
        data = json.loads(text)
        # Navigate the nested structure to find search results
        results = _deep_find_key(data, "searchResults") or []
        if not results:
            results = _deep_find_key(data, "listings") or []
        for item in results:
            listing = _extract_listing_from_result(item)
            if listing:
                listings.append(listing)
    except (json.JSONDecodeError, TypeError):
        pass
    return listings


def _parse_next_data(text: str) -> list[dict]:
    """Parse __NEXT_DATA__ or inline JSON containing search results."""
    listings = []
    # Try to extract JSON object from script content
    import re
    patterns = [
        r'window\.__NEXT_DATA__\s*=\s*({.+?})\s*;?\s*(?:</script>|$)',
        r'"searchResults"\s*:\s*(\[.+?\])',
        r'"sections"\s*:\s*(\[.+?\])',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                results = _deep_find_key(data, "searchResults") or _deep_find_key(data, "listings") or []
                if isinstance(data, list):
                    results = data
                for item in results:
                    listing = _extract_listing_from_result(item)
                    if listing:
                        listings.append(listing)
                if listings:
                    break
            except (json.JSONDecodeError, TypeError):
                continue
    return listings


def _parse_meta_fallback(soup: BeautifulSoup) -> list[dict]:
    """Last resort: extract any pricing info from meta tags or visible cards."""
    listings = []
    import re

    # Look for price patterns in text content
    for el in soup.select('[data-testid="listing-card-title"], [itemprop="name"]'):
        name = el.get_text(strip=True)
        if name:
            # Try to find nearby price
            parent = el.find_parent("div", {"data-testid": True}) or el.parent
            if parent:
                price_text = parent.get_text()
                price_match = re.search(r"\$(\d+)", price_text)
                price = int(price_match.group(1)) if price_match else None
                listings.append({
                    "listing_id": hashlib.md5(name.encode()).hexdigest()[:12],
                    "name": name,
                    "price_per_night": price,
                    "rating": None,
                    "reviews_count": None,
                    "url": "",
                })
    return listings


def _extract_listing_from_result(item: dict) -> Optional[dict]:
    """Extract listing data from a search result item (various formats)."""
    if not isinstance(item, dict):
        return None

    # Try different Airbnb JSON structures
    listing = item.get("listing") or item.get("listingData") or item
    pricing = item.get("pricingQuote") or item.get("pricing") or item.get("price") or {}
    if isinstance(pricing, dict):
        price = (
            pricing.get("rate", {}).get("amount")
            or pricing.get("priceString")
            or pricing.get("price")
            or pricing.get("amount")
        )
    else:
        price = pricing

    name = listing.get("name") or listing.get("title") or ""
    listing_id = str(listing.get("id") or listing.get("listingId") or "")

    if not name and not listing_id:
        return None

    return {
        "listing_id": listing_id,
        "name": name,
        "price_per_night": _to_float(price),
        "rating": _to_float(listing.get("avgRating") or listing.get("rating")),
        "reviews_count": _to_int(listing.get("reviewsCount") or listing.get("reviews_count")),
        "room_type": listing.get("roomType") or listing.get("room_type") or "",
        "bedrooms": _to_int(listing.get("bedrooms")),
        "min_nights": _to_int(listing.get("minNights") or listing.get("min_nights")),
        "is_superhost": listing.get("isSuperhost", False),
        "url": f"https://www.airbnb.com/rooms/{listing_id}" if listing_id else "",
    }


def _deep_find_key(data, key: str, max_depth: int = 10):
    """Recursively search for a key in nested dicts/lists."""
    if max_depth <= 0:
        return None
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for v in data.values():
            result = _deep_find_key(v, key, max_depth - 1)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data[:50]:  # Limit iteration
            result = _deep_find_key(item, key, max_depth - 1)
            if result is not None:
                return result
    return None


def _to_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        s = str(val).replace("$", "").replace(",", "").strip()
        return float(s) if s else None
    except (ValueError, TypeError):
        return None


def _to_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(float(str(val).replace(",", "").strip()))
    except (ValueError, TypeError):
        return None


def scrape_neighborhood(
    session: requests.Session, neighborhood_key: str, neighborhood: dict,
    checkin: str, checkout: str,
) -> dict:
    """Scrape Airbnb search results for one neighborhood."""
    url = build_search_url(neighborhood, checkin, checkout)
    log.info("Scraping %s: %s", neighborhood["name"], url[:100] + "...")

    listings = []
    for attempt in range(MAX_RETRIES + 1):
        try:
            # Rotate user agent per request
            session.headers["User-Agent"] = random.choice(USER_AGENTS)
            resp = session.get(url, timeout=30)

            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                log.warning("Rate limited (429). Waiting %ds before retry.", wait)
                time.sleep(wait)
                continue

            if resp.status_code != 200:
                log.warning("HTTP %d for %s", resp.status_code, neighborhood["name"])
                if attempt < MAX_RETRIES:
                    rate_limit_delay()
                    continue
                break

            listings = extract_listings_from_html(resp.text)
            log.info("  Found %d listings in %s", len(listings), neighborhood["name"])
            break

        except requests.RequestException as e:
            log.warning("Request error for %s (attempt %d): %s", neighborhood["name"], attempt + 1, e)
            if attempt < MAX_RETRIES:
                rate_limit_delay()

    # Calculate neighborhood stats
    prices = [l["price_per_night"] for l in listings if l.get("price_per_night")]
    ratings = [l["rating"] for l in listings if l.get("rating")]

    return {
        "neighborhood": neighborhood_key,
        "neighborhood_name": neighborhood["name"],
        "listing_count": len(listings),
        "listings": listings,
        "stats": {
            "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "median_price": _median(prices),
            "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "superhost_count": sum(1 for l in listings if l.get("is_superhost")),
        },
    }


def _median(values: list) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n % 2 == 0:
        return round((s[n // 2 - 1] + s[n // 2]) / 2, 2)
    return s[n // 2]


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_trends(data: dict) -> dict:
    """Analyze rate trends across snapshots."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    week_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    two_weeks_ago = (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d")

    snapshots = data.get("snapshots", [])
    if not snapshots:
        return {"error": "No snapshot data available", "generated": today}

    # Get latest snapshot and last week's snapshot
    latest = snapshots[-1] if snapshots else None
    week_old = None
    for s in reversed(snapshots):
        if s.get("date", "") <= week_ago:
            week_old = s
            break

    trends = {
        "generated": datetime.utcnow().isoformat(),
        "latest_date": latest.get("date") if latest else None,
        "total_snapshots": len(snapshots),
        "neighborhoods": {},
        "opportunities": [],
        "market_summary": {},
    }

    if not latest:
        return trends

    # Per-neighborhood analysis
    all_prices_this_week = []
    all_prices_last_week = []

    for nb_data in latest.get("neighborhoods", []):
        nb_key = nb_data["neighborhood"]
        stats = nb_data.get("stats", {})
        avg_price = stats.get("avg_price")
        listing_count = nb_data.get("listing_count", 0)

        nb_trend = {
            "name": nb_data["neighborhood_name"],
            "current_avg_price": avg_price,
            "current_listing_count": listing_count,
            "current_min_price": stats.get("min_price"),
            "current_max_price": stats.get("max_price"),
            "current_avg_rating": stats.get("avg_rating"),
            "price_change_vs_last_week": None,
            "price_change_pct": None,
            "listing_count_change": None,
        }

        if avg_price:
            all_prices_this_week.append(avg_price)

        # Compare with last week
        if week_old:
            old_nb = None
            for nb in week_old.get("neighborhoods", []):
                if nb["neighborhood"] == nb_key:
                    old_nb = nb
                    break
            if old_nb:
                old_avg = old_nb.get("stats", {}).get("avg_price")
                old_count = old_nb.get("listing_count", 0)
                if old_avg and avg_price:
                    change = avg_price - old_avg
                    pct = round((change / old_avg) * 100, 1)
                    nb_trend["price_change_vs_last_week"] = round(change, 2)
                    nb_trend["price_change_pct"] = pct
                    all_prices_last_week.append(old_avg)
                nb_trend["listing_count_change"] = listing_count - old_count

        # Flag underpriced listings (20%+ below neighborhood avg)
        if avg_price:
            threshold = avg_price * 0.80
            for listing in nb_data.get("listings", []):
                lp = listing.get("price_per_night")
                if lp and lp <= threshold:
                    discount_pct = round((1 - lp / avg_price) * 100, 1)
                    trends["opportunities"].append({
                        "type": "underpriced",
                        "neighborhood": nb_data["neighborhood_name"],
                        "listing_name": listing.get("name", "Unknown"),
                        "listing_url": listing.get("url", ""),
                        "price": lp,
                        "neighborhood_avg": avg_price,
                        "discount_pct": discount_pct,
                        "reason": f"${lp}/night is {discount_pct}% below neighborhood avg (${avg_price})",
                    })

        trends["neighborhoods"][nb_key] = nb_trend

    # Market-wide summary
    market_avg = round(sum(all_prices_this_week) / len(all_prices_this_week), 2) if all_prices_this_week else None
    last_week_avg = round(sum(all_prices_last_week) / len(all_prices_last_week), 2) if all_prices_last_week else None

    trends["market_summary"] = {
        "overall_avg_price": market_avg,
        "last_week_avg_price": last_week_avg,
        "week_over_week_change": round(market_avg - last_week_avg, 2) if market_avg and last_week_avg else None,
        "total_listings_tracked": sum(
            nb.get("listing_count", 0) for nb in latest.get("neighborhoods", [])
        ),
        "neighborhoods_tracked": len(latest.get("neighborhoods", [])),
        "opportunity_count": len(trends["opportunities"]),
    }

    # Sort opportunities by discount percentage
    trends["opportunities"].sort(key=lambda x: x.get("discount_pct", 0), reverse=True)

    return trends


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

def run_scrape():
    """Run a full scrape of all neighborhoods."""
    log.info("Starting Airbnb rate tracker scrape")

    # Calculate search dates (2 weeks out, 3-night stay)
    checkin_date = datetime.utcnow() + timedelta(days=SEARCH_CHECKIN_OFFSET_DAYS)
    checkout_date = checkin_date + timedelta(days=SEARCH_NIGHTS)
    checkin = checkin_date.strftime("%Y-%m-%d")
    checkout = checkout_date.strftime("%Y-%m-%d")
    today = datetime.utcnow().strftime("%Y-%m-%d")

    log.info("Search window: %s to %s", checkin, checkout)

    session = create_session()
    neighborhood_results = []

    for nb_key, nb_info in NEIGHBORHOODS.items():
        result = scrape_neighborhood(session, nb_key, nb_info, checkin, checkout)
        neighborhood_results.append(result)
        rate_limit_delay()

    # Build snapshot
    snapshot = {
        "date": today,
        "scraped_at": datetime.utcnow().isoformat(),
        "search_checkin": checkin,
        "search_checkout": checkout,
        "neighborhoods": neighborhood_results,
        "total_listings": sum(r["listing_count"] for r in neighborhood_results),
    }

    # Save to historical data
    data = load_rates_data()
    # Replace today's snapshot if it already exists (idempotent re-runs)
    data["snapshots"] = [s for s in data["snapshots"] if s.get("date") != today]
    data["snapshots"].append(snapshot)
    save_rates_data(data)

    total = snapshot["total_listings"]
    log.info("Scrape complete: %d total listings across %d neighborhoods", total, len(neighborhood_results))

    return data


def run_analyze(data: Optional[dict] = None):
    """Run analysis on stored data."""
    if data is None:
        data = load_rates_data()

    summary = analyze_trends(data)
    save_summary(summary)

    # Print summary
    ms = summary.get("market_summary", {})
    log.info("=== Market Summary ===")
    log.info("  Overall avg price: $%s", ms.get("overall_avg_price", "N/A"))
    log.info("  Week-over-week change: $%s", ms.get("week_over_week_change", "N/A"))
    log.info("  Total listings tracked: %s", ms.get("total_listings_tracked", 0))
    log.info("  Opportunities found: %s", ms.get("opportunity_count", 0))

    for nb_key, nb_trend in summary.get("neighborhoods", {}).items():
        change_str = ""
        if nb_trend.get("price_change_pct") is not None:
            sign = "+" if nb_trend["price_change_pct"] >= 0 else ""
            change_str = f" ({sign}{nb_trend['price_change_pct']}% vs last week)"
        log.info(
            "  %s: $%s avg, %d listings%s",
            nb_trend["name"],
            nb_trend.get("current_avg_price", "N/A"),
            nb_trend.get("current_listing_count", 0),
            change_str,
        )

    if summary.get("opportunities"):
        log.info("=== Top Opportunities ===")
        for opp in summary["opportunities"][:5]:
            log.info(
                "  %s — $%s/night (%s%% below avg in %s)",
                opp["listing_name"][:40],
                opp["price"],
                opp["discount_pct"],
                opp["neighborhood"],
            )

    return summary


def print_summary():
    """Print the latest summary without scraping."""
    if not SUMMARY_FILE.exists():
        log.error("No summary file found. Run a full scrape first.")
        return

    with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
        summary = json.load(f)

    ms = summary.get("market_summary", {})
    print(f"\nAirbnb Rate Tracker — Punta Cana")
    print(f"Generated: {summary.get('generated', 'N/A')}")
    print(f"{'=' * 50}")
    print(f"Overall avg nightly rate: ${ms.get('overall_avg_price', 'N/A')}")
    print(f"Week-over-week change:    ${ms.get('week_over_week_change', 'N/A')}")
    print(f"Total listings tracked:   {ms.get('total_listings_tracked', 0)}")
    print(f"Neighborhoods:            {ms.get('neighborhoods_tracked', 0)}")
    print(f"{'=' * 50}")

    print("\nBy Neighborhood:")
    for _, nb in summary.get("neighborhoods", {}).items():
        change = ""
        if nb.get("price_change_pct") is not None:
            sign = "+" if nb["price_change_pct"] >= 0 else ""
            change = f"  {sign}{nb['price_change_pct']}%"
        print(
            f"  {nb['name']:<30} ${nb.get('current_avg_price', 'N/A'):>7}  "
            f"({nb.get('current_listing_count', 0)} listings){change}"
        )

    opps = summary.get("opportunities", [])
    if opps:
        print(f"\nOpportunities ({len(opps)} found):")
        for opp in opps[:10]:
            print(f"  ${opp['price']}/night — {opp['listing_name'][:45]}")
            print(f"    {opp['reason']}")
            if opp.get("listing_url"):
                print(f"    {opp['listing_url']}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if "--analyze" in sys.argv:
        run_analyze()
    elif "--summary" in sys.argv:
        print_summary()
    else:
        data = run_scrape()
        run_analyze(data)


if __name__ == "__main__":
    main()
