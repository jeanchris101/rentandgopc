# ============================================================
# CRITICAL: READ-ONLY MODE — NEVER WRITE TO FACEBOOK
# This scraper ONLY reads/captures data from Marketplace.
# It must NEVER post, message, bid, or interact with listings.
# ============================================================

"""
marketplace.py — Facebook Marketplace scraper for Punta Cana real estate.
Uses the same Patchright session as the group scraper.
Intercepts GraphQL responses for structured data, falls back to DOM extraction.
Feeds into the same SQLite database + agent pipeline.
"""

import asyncio
import json
import logging
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from patchright.async_api import async_playwright, Page, BrowserContext

from config import load_config, ScraperConfig, AccountConfig
from database import (
    get_connection, init_db, post_exists, insert_raw_post,
    process_post, start_scrape_log, finish_scrape_log, get_stats,
)
from parser import parse
from scraper import BrowserCrashError, is_browser_crash, raise_if_browser_crash

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("marketplace")

SESSIONS_DIR = Path(__file__).parent / "sessions"

# Marketplace search URLs for Punta Cana area
# We discover the location ID dynamically, but these are the category paths
MARKETPLACE_CATEGORIES = [
    "propertyforsale",
    "propertyrentals",
]

# Search queries to supplement category browsing
SEARCH_QUERIES = [
    "apartamento punta cana",
    "villa punta cana",
    "casa bavaro",
    "apartamento bavaro",
    "villa cap cana",
    "terreno punta cana",
    "penthouse bavaro",
    "casa punta cana",
    "condo punta cana",
    "apartamento cocotal",
    "villa vista cana",
    "propiedad bavaro",
]

# Read-only guard (same as scraper.py)
READONLY_GUARD_JS = """
() => {
    if (window.__readonlyGuardInstalled) return;
    window.__readonlyGuardInstalled = true;
    const BLOCKED = ['post','publish','publicar','comment','comentar','reply','send','enviar','like','share','compartir','buy','comprar','message','mensaje','make offer','hacer oferta'];
    document.addEventListener('click', (e) => {
        const el = e.target.closest('button, [role="button"], a[role="button"]');
        if (!el) return;
        const text = (el.textContent || '').trim().toLowerCase();
        const aria = (el.getAttribute('aria-label') || '').trim().toLowerCase();
        const combined = text + ' ' + aria;
        for (const b of BLOCKED) {
            if (combined.includes(b)) {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                console.error('[READONLY GUARD] Blocked: ' + text);
                return;
            }
        }
    }, true);
}
"""


async def install_readonly_guard(page: Page):
    try:
        await page.evaluate(READONLY_GUARD_JS)
    except Exception:
        pass


# ─── GraphQL Interception ───

class MarketplaceCollector:
    """Collects Marketplace listing data from intercepted GraphQL responses."""

    def __init__(self):
        self.listings: list[dict] = []
        self._seen_ids: set[str] = set()

    def handle_response(self, response):
        """Attach as page.on('response', collector.handle_response)"""
        url = response.url
        if "/api/graphql/" not in url:
            return
        # Process async to not block
        asyncio.ensure_future(self._process_response(response))

    async def _process_response(self, response):
        try:
            if response.status != 200:
                return
            body = await response.text()
            # GraphQL responses may contain multiple JSON objects separated by newlines
            for line in body.split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                self._extract_from_graphql(data)
        except Exception:
            pass

    def _extract_from_graphql(self, data: dict):
        """Recursively search for marketplace listing data in GraphQL response."""
        if not isinstance(data, dict):
            return

        # Look for marketplace_search results
        edges = None

        # Path 1: data.marketplace_search.feed_units.edges
        ms = data.get("data", {}).get("marketplace_search", {})
        if ms:
            fu = ms.get("feed_units", {})
            edges = fu.get("edges", [])

        # Path 2: data.node.marketplace_listing_category_feed.edges
        node = data.get("data", {}).get("node", {})
        if node and not edges:
            mlcf = node.get("marketplace_listing_category_feed", {})
            edges = mlcf.get("edges", [])

        # Path 3: Search in viewer
        viewer = data.get("data", {}).get("viewer", {})
        if viewer and not edges:
            mfs = viewer.get("marketplace_feed_stories", {})
            edges = mfs.get("edges", [])

        # Path 4: Deeply nested — look for any key containing "edges" with listing nodes
        if not edges:
            edges = self._find_listing_edges(data)

        if not edges:
            return

        for edge in edges:
            if not isinstance(edge, dict):
                continue
            node = edge.get("node", edge)
            listing = self._parse_listing_node(node)
            if listing and listing["id"] not in self._seen_ids:
                self._seen_ids.add(listing["id"])
                self.listings.append(listing)

    def _find_listing_edges(self, obj, depth=0) -> list:
        """Recursively search for listing edges in nested GraphQL data."""
        if depth > 8 or not isinstance(obj, dict):
            return []
        for key, val in obj.items():
            if key == "edges" and isinstance(val, list) and val:
                # Check if first edge looks like a marketplace listing
                first = val[0] if val else {}
                node = first.get("node", first) if isinstance(first, dict) else {}
                if isinstance(node, dict) and ("listing_price" in node or "marketplace_listing_title" in node or "listing_id" in node):
                    return val
            if isinstance(val, dict):
                result = self._find_listing_edges(val, depth + 1)
                if result:
                    return result
        return []

    def _parse_listing_node(self, node: dict) -> Optional[dict]:
        """Extract structured data from a marketplace listing GraphQL node."""
        if not isinstance(node, dict):
            return None

        # Unwrap feed story wrapper — the real listing may be nested multiple levels deep
        # Common structures: node.listing, node.target, node.story, node.story.target,
        # node.marketplace_listing_renderable_target
        for unwrap_key in ("listing", "target", "story", "marketplace_listing_renderable_target"):
            inner = node.get(unwrap_key)
            if not isinstance(inner, dict):
                continue
            # Check if inner has listing data directly
            listing_keys = {"listing_id", "marketplace_listing_title", "listing_price", "listing_title", "marketplace_listing_seller"}
            if listing_keys & inner.keys():
                node = {**node, **inner}
                break
            # Check one level deeper (story.target, story.listing, etc.)
            for sub_key in ("listing", "target", "marketplace_listing_renderable_target"):
                sub = inner.get(sub_key)
                if isinstance(sub, dict) and listing_keys & sub.keys():
                    node = {**node, **inner, **sub}
                    break
            else:
                continue
            break

        listing_id = (
            node.get("listing_id")
            or node.get("id")
            or node.get("marketplace_listing_id")
        )
        if not listing_id:
            return None

        # Title — extract from multiple possible GraphQL field shapes
        title = ""
        if node.get("marketplace_listing_title"):
            title = node["marketplace_listing_title"]
        elif isinstance(node.get("listing_title"), dict):
            title = node["listing_title"].get("text", "")
        elif node.get("listing_title"):
            title = str(node["listing_title"])
        if isinstance(title, dict):
            title = title.get("text", "")

        # Price
        price_data = node.get("listing_price", {})
        if isinstance(price_data, dict):
            price_text = price_data.get("text", "")
            price_amount = price_data.get("amount", "")
            currency = price_data.get("currency", "USD")
        else:
            price_text = str(price_data) if price_data else ""
            price_amount = ""
            currency = "USD"

        # Location
        location = node.get("location", {})
        if isinstance(location, dict):
            location_name = location.get("reverse_geocode", {}).get("city", "") if isinstance(location.get("reverse_geocode"), dict) else ""
            latitude = location.get("latitude")
            longitude = location.get("longitude")
        else:
            location_name = ""
            latitude = None
            longitude = None

        # Also check marketplace_listing_renderable_target for location
        target = node.get("marketplace_listing_renderable_target", {})
        if isinstance(target, dict) and not location_name:
            loc2 = target.get("location", {})
            if isinstance(loc2, dict):
                location_name = loc2.get("reverse_geocode", {}).get("city", "") if isinstance(loc2.get("reverse_geocode"), dict) else ""

        # Location text fallback
        loc_text = node.get("location_text", {})
        if isinstance(loc_text, dict) and not location_name:
            location_name = loc_text.get("text", "")
        elif isinstance(loc_text, str) and not location_name:
            location_name = loc_text

        # Images — check multiple GraphQL paths
        images = []
        seen_uris = set()

        def _add_img(uri):
            if uri and uri not in seen_uris and ("scontent" in uri or "fbcdn" in uri):
                seen_uris.add(uri)
                images.append(uri)

        # Path 1: primary_listing_photo
        primary = node.get("primary_listing_photo", {})
        if isinstance(primary, dict):
            img = primary.get("image", primary)
            if isinstance(img, dict):
                _add_img(img.get("uri", ""))

        # Path 2: listing_photos / all_listing_photos
        for key in ("listing_photos", "all_listing_photos", "photos", "images"):
            photos = node.get(key, [])
            if isinstance(photos, list):
                for photo in photos:
                    if isinstance(photo, dict):
                        img = photo.get("image", photo)
                        if isinstance(img, dict):
                            _add_img(img.get("uri", ""))
                        elif isinstance(photo, str):
                            _add_img(photo)

        # Path 3: target.listing_photos
        target = node.get("marketplace_listing_renderable_target", {})
        if isinstance(target, dict):
            for key in ("listing_photos", "primary_listing_photo"):
                tp = target.get(key)
                if isinstance(tp, dict):
                    _add_img(tp.get("image", {}).get("uri", "") if isinstance(tp.get("image"), dict) else "")
                elif isinstance(tp, list):
                    for p in tp:
                        if isinstance(p, dict):
                            _add_img(p.get("image", {}).get("uri", "") if isinstance(p.get("image"), dict) else "")

        # Path 4: thumbnail_image / cover_photo
        for key in ("thumbnail_image", "cover_photo", "listing_image"):
            thumb = node.get(key, {})
            if isinstance(thumb, dict):
                _add_img(thumb.get("uri", ""))

        # Seller info
        seller = node.get("marketplace_listing_seller", {}) or node.get("actor", {})
        seller_name = ""
        seller_id = ""
        seller_profile_url = ""
        if isinstance(seller, dict):
            seller_name = seller.get("name", "")
            seller_id = seller.get("id", "")
            seller_profile_url = seller.get("url", "") or seller.get("profile_url", "")
            if seller_id and not seller_profile_url:
                seller_profile_url = f"https://www.facebook.com/profile.php?id={seller_id}"

        # Description
        description = ""
        desc_obj = node.get("redacted_description", {}) or node.get("marketplace_listing_renderable_target", {}).get("redacted_description", {})
        if isinstance(desc_obj, dict):
            description = desc_obj.get("text", "")
        elif isinstance(desc_obj, str):
            description = desc_obj

        # Category / property details
        category = node.get("marketplace_listing_category_id", "") or node.get("category_type", "")

        # Property-specific fields (if available)
        bedrooms = node.get("property_bedrooms") or node.get("num_bedrooms")
        bathrooms = node.get("property_bathrooms") or node.get("num_bathrooms")
        sqm = node.get("property_area") or node.get("square_feet")
        property_type = node.get("property_type", "")

        # Creation time
        created = node.get("creation_time") or node.get("created_time")
        if created and isinstance(created, (int, float)):
            created = datetime.fromtimestamp(created, tz=timezone.utc).isoformat()

        # Debug: log node keys when title is empty to diagnose GraphQL structure
        if not title:
            # Log first few keys and any nested dict keys to understand the structure
            sample_vals = {k: type(v).__name__ for k, v in list(node.items())[:15]}
            log.info(f"  [MP DEBUG] Empty title for {listing_id}, keys: {sample_vals}")

        return {
            "id": str(listing_id),
            "title": title or "",
            "price_text": price_text,
            "price_amount": str(price_amount),
            "currency": currency,
            "location_name": location_name,
            "latitude": latitude,
            "longitude": longitude,
            "images": images[:10],
            "seller_name": seller_name,
            "seller_id": seller_id,
            "seller_profile_url": seller_profile_url,
            "description": description,
            "category": str(category),
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "sqm": sqm,
            "property_type": property_type,
            "created": created,
        }


# ─── DOM Extraction (fallback) ───

async def extract_marketplace_from_dom(page: Page) -> list[dict]:
    """Fallback: extract listing cards from Marketplace DOM."""
    listings = await page.evaluate("""
        () => {
            const results = [];
            const seenIds = new Set();

            // Marketplace listing cards are typically in a grid
            // Look for links to /marketplace/item/
            const links = document.querySelectorAll('a[href*="/marketplace/item/"]');

            for (const link of links) {
                const href = link.href || '';
                const m = href.match(/\\/marketplace\\/item\\/(\\d+)/);
                if (!m) continue;
                const id = m[1];
                if (seenIds.has(id)) continue;
                seenIds.add(id);

                // Get the card container (usually the link itself or its parent)
                const card = link.closest('[class]') || link;

                // Extract text content
                const text = card.textContent || '';

                // Try to find price (usually prominent text with $ or RD$)
                let price = '';
                const priceMatch = text.match(/(?:US?\\$|RD\\$)\\s*[\\d,.]+/);
                if (priceMatch) price = priceMatch[0];

                // Find images
                const images = [];
                const imgs = card.querySelectorAll('img');
                for (const img of imgs) {
                    const src = img.src || '';
                    if (src && (src.includes('scontent') || src.includes('fbcdn')) && !src.includes('emoji')) {
                        images.push(src);
                    }
                }

                // Title is usually the first significant text line
                const spans = card.querySelectorAll('span');
                let title = '';
                for (const s of spans) {
                    const t = s.textContent.trim();
                    if (t.length > 10 && t.length < 200 && !t.includes('$') && t !== price) {
                        title = t;
                        break;
                    }
                }

                // Location - usually shorter text after title
                let location = '';
                for (const s of spans) {
                    const t = s.textContent.trim();
                    if (t.length > 3 && t.length < 60 && t !== title && t !== price &&
                        !t.includes('$') && !t.includes('Listed')) {
                        location = t;
                        break;
                    }
                }

                results.push({
                    id: id,
                    title: title,
                    price_text: price,
                    location_name: location,
                    images: images.slice(0, 5),
                    permalink: 'https://www.facebook.com/marketplace/item/' + id + '/',
                });
            }
            return results;
        }
    """)
    return listings or []


# ─── Detail Page Scraping ───

async def scrape_listing_detail(page: Page, listing_id: str, collector: MarketplaceCollector) -> Optional[dict]:
    """Visit a listing detail page to get full info (description, all images, seller)."""
    # Clean composite IDs like "12345:IN_MEMORY_..." to just the numeric part
    clean_id = listing_id.split(":")[0] if ":" in listing_id else listing_id
    url = f"https://www.facebook.com/marketplace/item/{clean_id}/"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await install_readonly_guard(page)
        # Human-like dwell time
        await asyncio.sleep(random.uniform(5, 12))

        # GraphQL collector may have captured detail data
        # Also try DOM extraction for fallback
        detail = await page.evaluate("""
            () => {
                const result = {};

                // Title — usually in the first h1 or prominent heading
                const h1 = document.querySelector('h1');
                if (h1) result.title = h1.textContent.trim();
                // Fallback: first span with aria-level heading
                if (!result.title) {
                    const heading = document.querySelector('[role="heading"]');
                    if (heading) result.title = heading.textContent.trim();
                }

                // Description
                const descEls = document.querySelectorAll('span[dir="auto"]');
                let longest = '';
                for (const el of descEls) {
                    const t = el.textContent.trim();
                    if (t.length > longest.length && t.length > 50) longest = t;
                }
                result.description = longest;

                // All images
                result.images = [];
                const imgs = document.querySelectorAll('img');
                const seen = new Set();
                for (const img of imgs) {
                    const src = img.src || '';
                    if (src && (src.includes('scontent') || src.includes('fbcdn')) &&
                        !src.includes('emoji') && !src.includes('rsrc') &&
                        (img.width > 100 || img.naturalWidth > 100 || img.width === 0)) {
                        try { const u = new URL(src); u.searchParams.delete('stp'); const clean = u.toString(); if (!seen.has(clean)) { seen.add(clean); result.images.push(clean); } } catch(e) {}
                    }
                }

                // Seller link
                const sellerLinks = document.querySelectorAll('a[href*="/profile"], a[href*="/user/"]');
                for (const link of sellerLinks) {
                    const name = link.textContent.trim();
                    if (name.length > 2 && name.length < 80) {
                        result.seller_name = name;
                        result.seller_profile_url = link.href.split('?')[0];
                        break;
                    }
                }

                // Property details from structured fields
                const allText = document.body.textContent;
                const bedMatch = allText.match(/(\\d+)\\s*(?:bed|hab|dorm)/i);
                const bathMatch = allText.match(/(\\d+\\.?\\d*)\\s*(?:bath|ba[ñn])/i);
                const sqmMatch = allText.match(/(\\d+[,.]?\\d*)\\s*(?:m[²2]|sq\\s*m|metros)/i);
                if (bedMatch) result.bedrooms = parseInt(bedMatch[1]);
                if (bathMatch) result.bathrooms = parseFloat(bathMatch[1]);
                if (sqmMatch) result.sqm = parseFloat(sqmMatch[1].replace(',', ''));

                // Price
                const priceMatch = allText.match(/(?:US?\\$|RD\\$)\\s*([\\d,]+(?:\\.\\d+)?)/);
                if (priceMatch) result.price_text = priceMatch[0];

                return result;
            }
        """)
        return detail
    except Exception as e:
        raise_if_browser_crash(e)  # Re-raise as BrowserCrashError if browser died
        log.warning(f"  Failed to load detail page for {listing_id}: {e}")
        return None


# ─── Location Discovery ───

# Known Facebook Marketplace location slugs/IDs for Punta Cana area.
# Facebook accepts both city name slugs and numeric place IDs in the URL.
# We try multiple candidates and use whichever one Facebook accepts (doesn't
# redirect back to the generic /marketplace/ page).
PUNTA_CANA_LOCATION_CANDIDATES = [
    # City-name slugs (Facebook normalises these)
    "puntacana",
    "bavaropuntacana",
    "bavaro",
    "higuey",
    # Numeric Facebook Place IDs for the area
    "109448275746122",   # Punta Cana
    "104076956295273",   # Bavaro
    "108145592543498",   # Higuey (municipality covering Bavaro/PC)
    "112037318812498",   # La Altagracia province
]

# Hardcoded fallback — if every candidate fails, use this.  It is the most
# commonly seen numeric ID for Punta Cana on Facebook.
FALLBACK_LOCATION_ID = "109448275746122"


async def discover_location_id(page: Page) -> str:
    """
    Determine the correct Facebook Marketplace location slug/ID for Punta Cana.

    Instead of fragile UI interaction (clicking location pickers, typing, waiting
    for dropdowns), we navigate directly to known location URLs and check whether
    Facebook keeps the location in the resulting URL.  The first candidate that
    sticks is used for all subsequent category/search URLs.

    Always returns a location string (never None) — falls back to a hardcoded ID.
    """
    log.info("Discovering Marketplace location ID for Punta Cana...")

    for candidate in PUNTA_CANA_LOCATION_CANDIDATES:
        test_url = f"https://www.facebook.com/marketplace/{candidate}/"
        try:
            resp = await page.goto(test_url, wait_until="domcontentloaded", timeout=20000)
            await install_readonly_guard(page)
            await asyncio.sleep(random.uniform(2, 4))

            final_url = page.url
            log.info(f"  Tried '{candidate}' -> {final_url}")

            # Success criteria: the final URL still contains a location segment
            # (i.e., Facebook did NOT strip it back to plain /marketplace/)
            m = re.search(r'/marketplace/([a-zA-Z0-9_]+)/?', final_url)
            if m:
                loc = m.group(1)
                skip = {"category", "search", "item", "you", "selling", "buying",
                        "create", "notifications", "inbox"}
                if loc.lower() not in skip:
                    log.info(f"  SUCCESS — using location ID: {loc}")
                    return loc

        except Exception as e:
            raise_if_browser_crash(e)
            log.warning(f"  Candidate '{candidate}' failed: {e}")
            continue

    # All candidates failed — use hardcoded fallback
    log.warning(f"  All location candidates failed — using fallback: {FALLBACK_LOCATION_ID}")
    return FALLBACK_LOCATION_ID


# ─── Main Marketplace Scraper ───

async def scrape_marketplace(
    page: Page,
    conn,
    account: AccountConfig,
    max_listings: int = 200,
    visit_details: int = 30,
) -> tuple[int, int]:
    """
    Scrape Facebook Marketplace for real estate listings.
    Returns (total_found, new_inserted).
    """
    log_id = start_scrape_log(conn, "marketplace", "Facebook Marketplace")
    total_found = 0
    new_inserted = 0

    try:
        # Set up GraphQL interceptor
        collector = MarketplaceCollector()
        page.on("response", collector.handle_response)

        # Discover location
        location_id = await discover_location_id(page)

        # Scrape category pages (always location-scoped — discover_location_id
        # guarantees a non-None return)
        for category in MARKETPLACE_CATEGORIES:
            url = f"https://www.facebook.com/marketplace/{location_id}/{category}/"

            log.info(f"Scraping Marketplace: {category} ({url})")

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await install_readonly_guard(page)
                await asyncio.sleep(random.uniform(3, 5))

                # Scroll to load more listings
                scroll_count = 0
                max_scrolls = 15  # ~20 listings per scroll = ~300 total
                prev_count = len(collector.listings)

                while scroll_count < max_scrolls and len(collector.listings) < max_listings:
                    dist = random.randint(800, 1500)
                    await page.evaluate(f"window.scrollBy(0, {dist})")
                    await asyncio.sleep(random.uniform(2.0, 4.0))

                    # Medium pause every 5 scrolls
                    if scroll_count > 0 and scroll_count % 5 == 0:
                        await asyncio.sleep(random.uniform(3, 6))
                        log.info(f"  Scroll {scroll_count}/{max_scrolls}, {len(collector.listings)} listings from GraphQL")

                    scroll_count += 1

                    # Check if we're still getting new data
                    if scroll_count > 5 and len(collector.listings) == prev_count:
                        # Try DOM extraction as fallback
                        dom_listings = await extract_marketplace_from_dom(page)
                        if dom_listings:
                            for dl in dom_listings:
                                if dl["id"] not in collector._seen_ids:
                                    collector._seen_ids.add(dl["id"])
                                    collector.listings.append({
                                        "id": dl["id"],
                                        "title": dl.get("title", ""),
                                        "price_text": dl.get("price_text", ""),
                                        "price_amount": "",
                                        "currency": "USD",
                                        "location_name": dl.get("location_name", ""),
                                        "latitude": None,
                                        "longitude": None,
                                        "images": dl.get("images", []),
                                        "seller_name": "",
                                        "seller_id": "",
                                        "seller_profile_url": "",
                                        "description": "",
                                        "category": category,
                                        "bedrooms": None,
                                        "bathrooms": None,
                                        "sqm": None,
                                        "property_type": "",
                                        "created": None,
                                    })
                            log.info(f"  DOM fallback: found {len(dom_listings)} additional listings")

                    prev_count = len(collector.listings)

                log.info(f"  {category}: {len(collector.listings)} total listings collected")

            except Exception as e:
                raise_if_browser_crash(e)  # Re-raise as BrowserCrashError if browser died
                log.error(f"  Error scraping {category}: {e}")
                continue

            # Pause between categories
            await asyncio.sleep(random.uniform(5, 10))

        # Also run search queries
        for query in SEARCH_QUERIES[:6]:  # Limit to 6 queries per run
            if len(collector.listings) >= max_listings:
                break

            search_url = f"https://www.facebook.com/marketplace/{location_id}/search/?query={query.replace(' ', '+')}"
            log.info(f"  Searching: {query}")

            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                await install_readonly_guard(page)
                await asyncio.sleep(random.uniform(3, 5))

                # Quick scroll — 5 scrolls per search
                for _ in range(5):
                    await page.evaluate(f"window.scrollBy(0, {random.randint(800, 1400)})")
                    await asyncio.sleep(random.uniform(2, 4))

                # DOM fallback for search results too
                dom_listings = await extract_marketplace_from_dom(page)
                for dl in dom_listings:
                    if dl["id"] not in collector._seen_ids:
                        collector._seen_ids.add(dl["id"])
                        collector.listings.append({
                            "id": dl["id"],
                            "title": dl.get("title", ""),
                            "price_text": dl.get("price_text", ""),
                            "price_amount": "",
                            "currency": "USD",
                            "location_name": dl.get("location_name", ""),
                            "latitude": None,
                            "longitude": None,
                            "images": dl.get("images", []),
                            "seller_name": "",
                            "seller_id": "",
                            "seller_profile_url": "",
                            "description": "",
                            "category": "search",
                            "bedrooms": None,
                            "bathrooms": None,
                            "sqm": None,
                            "property_type": "",
                            "created": None,
                        })

            except Exception as e:
                raise_if_browser_crash(e)  # Re-raise as BrowserCrashError if browser died
                log.warning(f"  Search error for '{query}': {e}")

            await asyncio.sleep(random.uniform(4, 8))

        log.info(f"Total unique listings collected: {len(collector.listings)}")

        # Remove GraphQL listener before visiting detail pages
        page.remove_listener("response", collector.handle_response)

        # Process collected listings
        total_found = len(collector.listings)
        detail_visits = 0

        for listing in collector.listings:
            # Clean composite IDs like "12345:IN_MEMORY_..." to just the numeric part
            clean_id = listing["id"].split(":")[0] if ":" in listing["id"] else listing["id"]
            listing["id"] = clean_id
            mp_id = f"mp_{clean_id}"

            # Skip if already in DB
            if post_exists(conn, mp_id):
                continue

            # Build raw text from available data
            parts = []
            if listing.get("title"):
                parts.append(listing["title"])
            if listing.get("price_text"):
                parts.append(listing["price_text"])
            if listing.get("location_name"):
                parts.append(listing["location_name"])
            if listing.get("description"):
                parts.append(listing["description"])

            # Visit detail page if missing description OR images, and haven't hit limit
            needs_detail = not listing.get("description") or not listing.get("images")
            if needs_detail and detail_visits < visit_details:
                detail = await scrape_listing_detail(page, listing["id"], collector)
                if detail:
                    if detail.get("title") and not listing.get("title"):
                        listing["title"] = detail["title"]
                        parts.insert(0, detail["title"])
                    if detail.get("description"):
                        listing["description"] = detail["description"]
                        parts.append(detail["description"])
                    if detail.get("images"):
                        listing["images"] = detail["images"]
                    if detail.get("seller_name"):
                        listing["seller_name"] = detail["seller_name"]
                    if detail.get("seller_profile_url"):
                        listing["seller_profile_url"] = detail["seller_profile_url"]
                    if detail.get("price_text") and not listing.get("price_text"):
                        listing["price_text"] = detail["price_text"]
                    if detail.get("bedrooms") and not listing.get("bedrooms"):
                        listing["bedrooms"] = detail["bedrooms"]
                    if detail.get("bathrooms") and not listing.get("bathrooms"):
                        listing["bathrooms"] = detail["bathrooms"]
                    if detail.get("sqm") and not listing.get("sqm"):
                        listing["sqm"] = detail["sqm"]
                detail_visits += 1

            raw_text = "\n".join(parts) if parts else listing.get("title", "Marketplace listing")

            if len(raw_text) < 10:
                continue

            # Insert into DB
            permalink = f"https://www.facebook.com/marketplace/item/{listing['id']}/"

            inserted = insert_raw_post(
                conn,
                post_id=mp_id,
                group_id="marketplace",
                group_name="Facebook Marketplace",
                author_name=listing.get("seller_name") or None,
                raw_text=raw_text,
                image_urls=listing.get("images", []),
                timestamp=listing.get("created"),
                permalink=permalink,
                source="marketplace",
            )

            if not inserted:
                continue

            # Parse with the same parser used for group posts
            result = parse(raw_text, has_images=len(listing.get("images", [])) > 0)

            # Override parser results with structured Marketplace data where available
            if listing.get("bedrooms") and result.bedrooms is None:
                result.bedrooms = int(listing["bedrooms"])
            if listing.get("bathrooms") and result.bathrooms is None:
                result.bathrooms = float(listing["bathrooms"])

            # Process through the full agent + property pipeline
            agent_id, property_id = process_post(
                conn,
                post_id=mp_id,
                author_name=listing.get("seller_name") or None,
                fb_profile_url=listing.get("seller_profile_url") or None,
                raw_text=raw_text,
                image_urls=listing.get("images", []),
                result=result,
                source="marketplace",
            )

            new_inserted += 1
            price_str = listing.get("price_text", "?")
            seller = listing.get("seller_name", "?")
            log.info(f"  [MP] #{new_inserted}: {price_str} | {listing.get('location_name', '?')} | {seller[:25]} | {mp_id}")

            conn.commit()

        finish_scrape_log(conn, log_id, total_found, new_inserted, total_found - new_inserted, "success")

    except BrowserCrashError:
        log.error(f"Browser crashed during marketplace scraping — partial results saved")
        finish_scrape_log(conn, log_id, total_found, new_inserted, 0, "error", "browser_crash_epipe")
        raise  # Let caller handle browser relaunch
    except Exception as e:
        raise_if_browser_crash(e)  # Convert to BrowserCrashError if applicable
        log.error(f"Marketplace scraping error: {e}")
        finish_scrape_log(conn, log_id, total_found, new_inserted, 0, "error", str(e))

    return total_found, new_inserted


# ─── Standalone Entry Point ───

async def run_marketplace(config: Optional[ScraperConfig] = None):
    """Run the Marketplace scraper standalone."""
    if config is None:
        config = load_config()

    accounts_with_sessions = [a for a in config.accounts if not a.disabled and a.has_session()]
    if not accounts_with_sessions:
        log.error("No accounts with sessions. Run scraper.py setup first.")
        sys.exit(1)

    conn = get_connection()
    init_db(conn)

    account = accounts_with_sessions[0]
    log.info(f"Starting Marketplace scraper with account: {account.label}")
    log.info(f"DB stats before: {get_stats(conn)}")

    async with async_playwright() as p:
        from scraper import create_context, verify_session

        context = await create_context(p, account, config)
        page = await context.new_page()

        if not await verify_session(page, account):
            log.error(f"Session invalid for {account.label}")
            await context.browser.close()
            conn.close()
            sys.exit(1)

        try:
            total, new = await scrape_marketplace(page, conn, account)
        except BrowserCrashError:
            log.warning("Browser crashed during marketplace scrape — attempting recovery...")
            try:
                await context.browser.close()
            except Exception:
                pass
            # Relaunch browser and retry once
            try:
                context = await create_context(p, account, config)
                page = await context.new_page()
                if await verify_session(page, account):
                    log.info("Browser recovered — retrying marketplace scrape")
                    total, new = await scrape_marketplace(page, conn, account)
                else:
                    log.error("Session invalid after recovery — aborting marketplace")
                    total, new = 0, 0
            except Exception as e2:
                log.error(f"Recovery failed: {e2}")
                total, new = 0, 0

        # Save session
        try:
            await page.context.storage_state(path=str(account.get_session_path()))
        except Exception:
            pass

        try:
            await context.browser.close()
        except Exception:
            pass

    stats = get_stats(conn)
    conn.close()

    log.info("=" * 60)
    log.info(f"Marketplace scraper finished!")
    log.info(f"  Found: {total}, New: {new}")
    log.info(f"  Database: {stats}")
    log.info("=" * 60)

    return new


if __name__ == "__main__":
    asyncio.run(run_marketplace())
