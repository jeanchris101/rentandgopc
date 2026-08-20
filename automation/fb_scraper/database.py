"""
database.py — SQLite database layer for FB listing scraper.
Expanded schema: raw_posts, listings, agents, properties, property_agents, scrape_log.
Includes agent dedup and property dedup logic.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from parser import ParseResult

DB_PATH = Path(__file__).parent.parent / "data" / "fb_listings.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrate_add_column(conn: sqlite3.Connection, table: str, column: str, definition: str):
    """Add a column to a table if it doesn't already exist. Safe for repeated calls."""
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        conn.commit()


def init_db(conn: Optional[sqlite3.Connection] = None):
    """Create all tables if they don't exist."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True

    conn.executescript("""
        -- Agents (poster/broker profiles)
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            fb_profile_url TEXT,
            fb_user_id TEXT,
            phones TEXT DEFAULT '[]',        -- JSON array
            whatsapp TEXT DEFAULT '[]',       -- JSON array
            emails TEXT DEFAULT '[]',         -- JSON array
            instagram TEXT,
            company TEXT,
            website TEXT,
            primary_zones TEXT DEFAULT '[]',  -- JSON array, auto-calculated
            total_listings INTEGER DEFAULT 0,
            first_seen_at TEXT,
            last_seen_at TEXT,
            avg_price_range TEXT,
            is_agent INTEGER DEFAULT 0,       -- 1 if multi-lister, 0 if likely owner
            notes TEXT
        );

        -- Properties (deduplicated physical properties)
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            zone TEXT,
            community TEXT,
            property_type TEXT,
            bedrooms INTEGER,
            bathrooms REAL,
            sqm REAL,
            price_usd REAL,                   -- latest asking price
            price_history TEXT DEFAULT '[]',   -- JSON array of {price, date, source_post_id}
            listing_type TEXT,
            furnished TEXT,
            amenities TEXT DEFAULT '[]',       -- JSON array
            description TEXT,                  -- best/longest description
            image_urls TEXT DEFAULT '[]',      -- JSON array collected across posts
            latitude REAL,
            longitude REAL,
            first_listed_at TEXT,
            last_seen_at TEXT,
            days_on_market INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',      -- active, sold, expired, price_reduced
            notes TEXT
        );

        -- Property-Agent links (many-to-many)
        CREATE TABLE IF NOT EXISTS property_agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL REFERENCES properties(id),
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            post_id TEXT,                      -- the specific post linking them
            price_listed REAL,
            first_posted TEXT,
            last_posted TEXT,
            UNIQUE(property_id, agent_id)
        );

        -- Raw posts (captured from FB or WhatsApp)
        CREATE TABLE IF NOT EXISTS raw_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id TEXT UNIQUE NOT NULL,
            group_id TEXT,
            group_name TEXT,
            author_name TEXT,
            raw_text TEXT NOT NULL,
            image_urls TEXT,                   -- JSON array
            timestamp TEXT,
            permalink TEXT,
            captured_at TEXT NOT NULL DEFAULT (datetime('now')),
            source TEXT DEFAULT 'facebook',    -- 'facebook' or 'whatsapp'
            agent_id INTEGER REFERENCES agents(id),
            property_id INTEGER REFERENCES properties(id)
        );

        -- Parsed listings (structured data per post)
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id TEXT UNIQUE NOT NULL REFERENCES raw_posts(post_id),
            price_usd REAL,
            price_original REAL,
            currency TEXT,
            bedrooms INTEGER,
            bathrooms REAL,
            sqm REAL,
            neighborhood TEXT,
            community TEXT,
            property_type TEXT,
            listing_type TEXT,
            furnished TEXT,
            amenities TEXT DEFAULT '[]',        -- JSON array
            contact_phone TEXT,
            contact_whatsapp TEXT,
            contact_email TEXT,
            contact_instagram TEXT,
            contact_company TEXT,
            contact_website TEXT,
            confidence REAL DEFAULT 0.0,
            is_spam INTEGER DEFAULT 0,
            needs_review INTEGER DEFAULT 0,
            review_reason TEXT,
            agent_id INTEGER REFERENCES agents(id),
            property_id INTEGER REFERENCES properties(id),
            source TEXT DEFAULT 'facebook',    -- 'facebook' or 'whatsapp'
            parsed_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- Scrape log
        CREATE TABLE IF NOT EXISTS scrape_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT,
            group_name TEXT,
            posts_captured INTEGER DEFAULT 0,
            posts_new INTEGER DEFAULT 0,
            posts_skipped INTEGER DEFAULT 0,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT DEFAULT 'running',
            error TEXT
        );

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_raw_posts_post_id ON raw_posts(post_id);
        CREATE INDEX IF NOT EXISTS idx_raw_posts_group_id ON raw_posts(group_id);
        CREATE INDEX IF NOT EXISTS idx_raw_posts_agent_id ON raw_posts(agent_id);
        CREATE INDEX IF NOT EXISTS idx_raw_posts_property_id ON raw_posts(property_id);
        CREATE INDEX IF NOT EXISTS idx_listings_neighborhood ON listings(neighborhood);
        CREATE INDEX IF NOT EXISTS idx_listings_needs_review ON listings(needs_review);
        CREATE INDEX IF NOT EXISTS idx_listings_agent_id ON listings(agent_id);
        CREATE INDEX IF NOT EXISTS idx_listings_property_id ON listings(property_id);
        CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name);
        CREATE INDEX IF NOT EXISTS idx_properties_zone ON properties(zone);
        CREATE INDEX IF NOT EXISTS idx_properties_community ON properties(community);
        CREATE INDEX IF NOT EXISTS idx_properties_status ON properties(status);
        CREATE INDEX IF NOT EXISTS idx_property_agents_prop ON property_agents(property_id);
        CREATE INDEX IF NOT EXISTS idx_property_agents_agent ON property_agents(agent_id);
        CREATE INDEX IF NOT EXISTS idx_raw_posts_source ON raw_posts(source);
        CREATE INDEX IF NOT EXISTS idx_listings_source ON listings(source);
        CREATE INDEX IF NOT EXISTS idx_listings_is_duplicate ON listings(is_duplicate);
    """)

    # Migrate: add source columns to existing tables if missing
    _migrate_add_column(conn, "raw_posts", "source", "TEXT DEFAULT 'facebook'")
    _migrate_add_column(conn, "listings", "source", "TEXT DEFAULT 'facebook'")
    # Migrate: add local_images column for cached FB CDN images
    _migrate_add_column(conn, "raw_posts", "local_images", "TEXT")
    # Migrate: add dedup columns
    _migrate_add_column(conn, "listings", "is_duplicate", "INTEGER DEFAULT 0")
    _migrate_add_column(conn, "listings", "duplicate_of", "TEXT")

    if close:
        conn.close()


# ============================================================
# Raw posts
# ============================================================

def post_exists(conn: sqlite3.Connection, post_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM raw_posts WHERE post_id = ?", (post_id,)).fetchone()
    return row is not None


def insert_raw_post(
    conn: sqlite3.Connection,
    post_id: str,
    group_id: str,
    group_name: str,
    author_name: Optional[str],
    raw_text: str,
    image_urls: list[str],
    timestamp: Optional[str],
    permalink: Optional[str],
    source: str = "facebook",
) -> bool:
    """Insert a raw post. Returns True if inserted, False if duplicate."""
    if post_exists(conn, post_id):
        return False
    conn.execute(
        """INSERT INTO raw_posts
           (post_id, group_id, group_name, author_name, raw_text, image_urls, timestamp, permalink, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (post_id, group_id, group_name, author_name, raw_text,
         json.dumps(image_urls), timestamp, permalink, source),
    )
    return True


# ============================================================
# Agent dedup + upsert
# ============================================================

def _normalize_text(text: str) -> str:
    """Normalize text for dedup comparison: lowercase, strip whitespace/punctuation, remove phone numbers/emojis."""
    import re
    if not text:
        return ""
    t = text.lower()
    # Remove phone numbers
    t = re.sub(r'[\+]?[\d\s\-\(\)]{7,15}', '', t)
    # Remove URLs
    t = re.sub(r'https?://\S+', '', t)
    # Remove emojis and special chars, keep letters/numbers/spaces
    t = re.sub(r'[^\w\s]', '', t, flags=re.UNICODE)
    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _json_list(val) -> list:
    """Parse a JSON string to list, or return empty list."""
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


def _merge_json_lists(existing_json: str, new_items: list) -> str:
    """Merge new items into an existing JSON array string, deduping."""
    existing = _json_list(existing_json)
    merged = list(existing)
    for item in new_items:
        if item and item not in merged:
            merged.append(item)
    return json.dumps(merged)


def find_or_create_agent(
    conn: sqlite3.Connection,
    name: Optional[str],
    fb_profile_url: Optional[str],
    phones: list[str],
    whatsapp: list[str],
    emails: list[str],
    instagram: Optional[str],
    company: Optional[str],
    website: Optional[str],
) -> Optional[int]:
    """
    Find an existing agent by dedup rules, or create a new one.
    Returns agent_id or None if no meaningful contact info.
    """
    if not name and not phones and not fb_profile_url:
        return None

    now = _now()
    agent_id = None

    # Rule 1: Match by FB profile URL (strongest signal)
    if fb_profile_url:
        row = conn.execute(
            "SELECT id FROM agents WHERE fb_profile_url = ?", (fb_profile_url,)
        ).fetchone()
        if row:
            agent_id = row["id"]

    # Rule 2: Match by phone number overlap
    if not agent_id and phones:
        all_agents = conn.execute("SELECT id, phones FROM agents").fetchall()
        for agent_row in all_agents:
            existing_phones = _json_list(agent_row["phones"])
            for phone in phones:
                if phone in existing_phones:
                    agent_id = agent_row["id"]
                    break
            if agent_id:
                break

    # Rule 3: Match by name + check for review (weaker signal — flag only)
    # We don't auto-merge on name alone to avoid false positives.
    # Just create new and let is_agent flag handle it.

    if agent_id:
        # Update existing agent — merge contact info
        agent = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()

        merged_phones = _merge_json_lists(agent["phones"], phones)
        merged_wa = _merge_json_lists(agent["whatsapp"], whatsapp)
        merged_emails = _merge_json_lists(agent["emails"], emails)
        new_ig = instagram or agent["instagram"]
        new_company = company or agent["company"]
        new_website = website or agent["website"]
        new_name = name or agent["name"]

        conn.execute(
            """UPDATE agents SET
               name=?, phones=?, whatsapp=?, emails=?, instagram=?,
               company=?, website=?, last_seen_at=?,
               total_listings = total_listings + 1
               WHERE id=?""",
            (new_name, merged_phones, merged_wa, merged_emails, new_ig,
             new_company, new_website, now, agent_id),
        )

        # Auto-flag as agent if 3+ listings
        count = conn.execute(
            "SELECT total_listings FROM agents WHERE id=?", (agent_id,)
        ).fetchone()["total_listings"]
        if count >= 3:
            conn.execute("UPDATE agents SET is_agent=1 WHERE id=?", (agent_id,))

    else:
        # Create new agent
        cur = conn.execute(
            """INSERT INTO agents
               (name, fb_profile_url, phones, whatsapp, emails, instagram,
                company, website, total_listings, first_seen_at, last_seen_at, is_agent)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 0)""",
            (name, fb_profile_url,
             json.dumps(phones), json.dumps(whatsapp), json.dumps(emails),
             instagram, company, website, now, now),
        )
        agent_id = cur.lastrowid

    return agent_id


def update_agent_zones(conn: sqlite3.Connection, agent_id: int):
    """Recalculate primary_zones and avg_price_range for an agent."""
    # Zones from their listings
    rows = conn.execute(
        "SELECT neighborhood, price_usd FROM listings WHERE agent_id = ? AND neighborhood IS NOT NULL",
        (agent_id,),
    ).fetchall()

    zones = {}
    prices = []
    for r in rows:
        zone = r["neighborhood"]
        if zone:
            zones[zone] = zones.get(zone, 0) + 1
        if r["price_usd"]:
            prices.append(r["price_usd"])

    # Top zones sorted by count
    sorted_zones = [z for z, _ in sorted(zones.items(), key=lambda x: -x[1])]

    # Price range
    price_range = None
    if prices:
        lo = min(prices)
        hi = max(prices)
        if lo >= 1000:
            price_range = f"${lo/1000:.0f}K-${hi/1000:.0f}K"
        else:
            price_range = f"${lo:.0f}-${hi:.0f}"

    conn.execute(
        "UPDATE agents SET primary_zones=?, avg_price_range=? WHERE id=?",
        (json.dumps(sorted_zones[:5]), price_range, agent_id),
    )


# ============================================================
# Property dedup + upsert
# ============================================================

def find_or_create_property(
    conn: sqlite3.Connection,
    zone: Optional[str],
    community: Optional[str],
    property_type: Optional[str],
    bedrooms: Optional[int],
    bathrooms: Optional[float],
    sqm: Optional[float],
    price_usd: Optional[float],
    listing_type: Optional[str],
    furnished: Optional[str],
    amenities: list[str],
    description: Optional[str],
    image_urls: list[str],
    post_id: str,
) -> Optional[int]:
    """
    Find an existing property by dedup rules, or create a new one.
    Returns property_id or None if insufficient data to dedup.
    """
    if not zone and not community:
        return None

    now = _now()
    property_id = None

    # Build candidates to check
    candidates = []

    if zone and bedrooms is not None and price_usd:
        # Rule 1: Same zone + same bedrooms + price within 10%
        lo = price_usd * 0.9
        hi = price_usd * 1.1
        rows = conn.execute(
            """SELECT id, price_usd, sqm, community FROM properties
               WHERE zone = ? AND bedrooms = ? AND price_usd BETWEEN ? AND ?
               AND status = 'active'""",
            (zone, bedrooms, lo, hi),
        ).fetchall()
        candidates.extend(rows)

    if zone and sqm and bedrooms is not None and not candidates:
        # Rule 2: Same zone + same sqm (within 5%) + same bedrooms
        sqm_lo = sqm * 0.95
        sqm_hi = sqm * 1.05
        rows = conn.execute(
            """SELECT id, price_usd, sqm, community FROM properties
               WHERE zone = ? AND bedrooms = ? AND sqm BETWEEN ? AND ?
               AND status = 'active'""",
            (zone, bedrooms, sqm_lo, sqm_hi),
        ).fetchall()
        candidates.extend(rows)

    if community and bedrooms is not None and price_usd and not candidates:
        # Rule 3: Same community + same bedrooms + price within 15%
        lo = price_usd * 0.85
        hi = price_usd * 1.15
        rows = conn.execute(
            """SELECT id, price_usd, sqm, community FROM properties
               WHERE community = ? AND bedrooms = ? AND price_usd BETWEEN ? AND ?
               AND status = 'active'""",
            (community, bedrooms, lo, hi),
        ).fetchall()
        candidates.extend(rows)

    # Deduplicate candidate IDs
    seen_ids = set()
    unique_candidates = []
    for c in candidates:
        if c["id"] not in seen_ids:
            seen_ids.add(c["id"])
            unique_candidates.append(c)

    if unique_candidates:
        # Pick best match (prefer same community if available)
        best = unique_candidates[0]
        if community:
            for c in unique_candidates:
                if c["community"] and c["community"].lower() == community.lower():
                    best = c
                    break
        property_id = best["id"]

    if property_id:
        # Update existing property
        prop = conn.execute("SELECT * FROM properties WHERE id = ?", (property_id,)).fetchone()

        # Update price + price history
        history = _json_list(prop["price_history"])
        if price_usd and price_usd != prop["price_usd"]:
            history.append({
                "price": price_usd,
                "date": now,
                "source_post_id": post_id,
            })
            # Detect price reduction
            if prop["price_usd"] and price_usd < prop["price_usd"]:
                conn.execute(
                    "UPDATE properties SET status='price_reduced' WHERE id=?", (property_id,)
                )

        # Merge image URLs
        existing_imgs = _json_list(prop["image_urls"])
        for url in image_urls:
            if url not in existing_imgs:
                existing_imgs.append(url)

        # Merge amenities
        existing_amenities = _json_list(prop["amenities"])
        for a in amenities:
            if a not in existing_amenities:
                existing_amenities.append(a)

        # Use longest description
        best_desc = prop["description"] or ""
        if description and len(description) > len(best_desc):
            best_desc = description

        # Calculate days on market
        first_listed = prop["first_listed_at"] or now
        try:
            first_dt = datetime.fromisoformat(first_listed.replace('Z', '+00:00'))
            now_dt = datetime.now(timezone.utc)
            dom = (now_dt - first_dt).days
        except Exception:
            dom = prop["days_on_market"] or 0

        new_price = price_usd if price_usd else prop["price_usd"]
        new_sqm = sqm if sqm else prop["sqm"]
        new_bathrooms = bathrooms if bathrooms else prop["bathrooms"]
        new_furnished = furnished if furnished else prop["furnished"]
        new_community = community if community else prop["community"]
        new_ptype = property_type if property_type else prop["property_type"]
        new_ltype = listing_type if listing_type else prop["listing_type"]

        conn.execute(
            """UPDATE properties SET
               price_usd=?, price_history=?, sqm=?, bathrooms=?,
               community=?, property_type=?, listing_type=?, furnished=?,
               amenities=?, description=?, image_urls=?,
               last_seen_at=?, days_on_market=?
               WHERE id=?""",
            (new_price, json.dumps(history), new_sqm, new_bathrooms,
             new_community, new_ptype, new_ltype, new_furnished,
             json.dumps(existing_amenities), best_desc, json.dumps(existing_imgs[:20]),
             now, dom, property_id),
        )

    else:
        # Create new property
        history = []
        if price_usd:
            history.append({"price": price_usd, "date": now, "source_post_id": post_id})

        cur = conn.execute(
            """INSERT INTO properties
               (zone, community, property_type, bedrooms, bathrooms, sqm,
                price_usd, price_history, listing_type, furnished, amenities,
                description, image_urls, first_listed_at, last_seen_at, days_on_market, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'active')""",
            (zone, community, property_type, bedrooms, bathrooms, sqm,
             price_usd, json.dumps(history), listing_type, furnished,
             json.dumps(amenities), description, json.dumps(image_urls[:20]),
             now, now),
        )
        property_id = cur.lastrowid

    return property_id


def link_property_agent(
    conn: sqlite3.Connection,
    property_id: int,
    agent_id: int,
    post_id: str,
    price_listed: Optional[float],
):
    """Create or update a property-agent link."""
    now = _now()
    existing = conn.execute(
        "SELECT id, first_posted FROM property_agents WHERE property_id=? AND agent_id=?",
        (property_id, agent_id),
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE property_agents SET last_posted=?, price_listed=?, post_id=? WHERE id=?",
            (now, price_listed, post_id, existing["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO property_agents
               (property_id, agent_id, post_id, price_listed, first_posted, last_posted)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (property_id, agent_id, post_id, price_listed, now, now),
        )


# ============================================================
# Listing insert (main entry point for post processing)
# ============================================================

def _to_usd(amount: float, currency: str, is_rental: bool = False) -> Optional[float]:
    if currency == 'USD':
        return amount
    elif currency == 'DOP':
        # Smart currency correction: agents in DR often post USD prices in the DOP field.
        # SALES: Real DOP sale prices start at ~DOP 2M+ ($34K+). If an agent posts
        #   "DOP 363,250" for a villa, they clearly mean $363,250 USD.
        #   Rule: DOP < 2M for a sale → treat as USD.
        # RENTALS: Real DOP rentals are typically DOP 15,000-80,000/mo ($260-$1,380).
        #   If an agent posts "DOP 825" or "DOP 1,300" for rent, they mean $825/$1,300 USD.
        #   Rule: DOP < 15,000 for a rental → treat as USD.
        #         DOP 15,000-80,000 → could be either, but lean DOP (legit local rental).
        #         DOP > 80,000 for rent → treat as USD (no rental is DOP 80K+/mo).
        if is_rental:
            if amount < 15_000:
                return amount  # e.g., DOP 825 → $825 USD/month
            elif amount > 80_000:
                return amount  # e.g., DOP 150,000 → $150,000 — clearly USD
            else:
                return round(amount / 58.0, 2)  # DOP 25,000 → ~$431 — legit DOP rental
        else:
            # Sale: anything under DOP 2M is almost certainly USD
            if amount < 2_000_000:
                return amount  # e.g., DOP 363,250 → $363,250 USD
            else:
                return round(amount / 58.0, 2)  # DOP 5,000,000 → ~$86K — could be real DOP
    elif currency == 'EUR':
        return round(amount * 1.08, 2)
    elif currency == 'CAD':
        return round(amount * 0.74, 2)
    return None


def _to_sqm(value: float, unit: str) -> float:
    if unit == 'sqm':
        return value
    return round(value * 0.0929, 2)


def process_post(
    conn: sqlite3.Connection,
    post_id: str,
    author_name: Optional[str],
    fb_profile_url: Optional[str],
    raw_text: str,
    image_urls: list[str],
    result: ParseResult,
    source: str = "facebook",
):
    """
    Full processing pipeline for a parsed post:
    0. Skip spam posts
    1. Find/create agent
    2. Find/create property (dedup)
    3. Insert listing (with confidence + is_spam)
    4. Link property-agent
    5. Update back-references on raw_posts
    """
    # --- Skip spam ---
    if result.is_spam:
        conn.execute(
            """INSERT OR REPLACE INTO listings
               (post_id, is_spam, confidence, needs_review, review_reason, source)
               VALUES (?, 1, 0.0, 0, ?, ?)""",
            (post_id, result.review_reason, source),
        )
        return (None, None)

    # --- Compute derived values ---
    price_usd = None
    price_original = None
    currency = None
    if result.price:
        price_original = result.price.amount
        currency = result.price.currency
        is_rental = result.listing_type and result.listing_type.lower() in ('rent', 'rental', 'alquiler')
        is_monthly = result.price.is_monthly or result.price.is_nightly if result.price else False
        price_usd = _to_usd(result.price.amount, result.price.currency, is_rental=is_rental or is_monthly)

    sqm = None
    if result.area:
        sqm = _to_sqm(result.area.value, result.area.unit)

    # --- Agent ---
    phones = result.contact.phones if result.contact else []
    whatsapp = result.contact.whatsapp if result.contact else []
    emails = result.contact.emails if result.contact else []
    ig = result.contact.instagram if result.contact else None
    company = result.contact.company if result.contact else None
    website = result.contact.website if result.contact else None

    agent_id = find_or_create_agent(
        conn,
        name=author_name,
        fb_profile_url=fb_profile_url,
        phones=phones,
        whatsapp=whatsapp,
        emails=emails,
        instagram=ig,
        company=company,
        website=website,
    )

    # --- Property dedup ---
    property_id = find_or_create_property(
        conn,
        zone=result.neighborhood,
        community=result.community,
        property_type=result.property_type,
        bedrooms=result.bedrooms,
        bathrooms=result.bathrooms,
        sqm=sqm,
        price_usd=price_usd,
        listing_type=result.listing_type,
        furnished=result.furnishing,
        amenities=result.amenities,
        description=raw_text[:2000],
        image_urls=image_urls,
        post_id=post_id,
    )

    # --- Check for duplicates before insert ---
    is_duplicate = 0
    duplicate_of = None

    if agent_id and property_id:
        # Same agent + same property = duplicate
        existing = conn.execute(
            """SELECT post_id FROM listings
               WHERE agent_id = ? AND property_id = ? AND is_duplicate = 0 AND is_spam = 0
               LIMIT 1""",
            (agent_id, property_id),
        ).fetchone()
        if existing:
            is_duplicate = 1
            duplicate_of = existing["post_id"]

    if not is_duplicate and agent_id and price_usd and result.property_type:
        # Same agent + same price + same property_type = duplicate (catches cross-group spam)
        existing = conn.execute(
            """SELECT post_id FROM listings
               WHERE agent_id = ? AND CAST(price_usd AS INTEGER) = CAST(? AS INTEGER)
               AND LOWER(property_type) = LOWER(?)
               AND is_duplicate = 0 AND is_spam = 0
               LIMIT 1""",
            (agent_id, price_usd, result.property_type),
        ).fetchone()
        if existing:
            is_duplicate = 1
            duplicate_of = existing["post_id"]

    if not is_duplicate and agent_id and not property_id:
        # No property_id — text similarity check against same agent's posts
        from difflib import SequenceMatcher
        normalized_new = _normalize_text(raw_text)
        if len(normalized_new) > 50:
            agent_posts = conn.execute(
                """SELECT l.post_id, r.raw_text FROM listings l
                   JOIN raw_posts r ON l.post_id = r.post_id
                   WHERE l.agent_id = ? AND l.is_duplicate = 0 AND l.is_spam = 0
                   ORDER BY l.parsed_at DESC LIMIT 50""",
                (agent_id,),
            ).fetchall()
            for ap in agent_posts:
                normalized_existing = _normalize_text(ap["raw_text"] or "")
                if len(normalized_existing) > 50:
                    ratio = SequenceMatcher(None, normalized_new, normalized_existing).ratio()
                    if ratio > 0.80:
                        is_duplicate = 1
                        duplicate_of = ap["post_id"]
                        break

    # --- Insert listing ---
    contact_phone = '; '.join(phones) if phones else None
    contact_wa = '; '.join(whatsapp) if whatsapp else None
    contact_email = '; '.join(emails) if emails else None

    conn.execute(
        """INSERT OR REPLACE INTO listings
           (post_id, price_usd, price_original, currency, bedrooms, bathrooms, sqm,
            neighborhood, community, property_type, listing_type, furnished, amenities,
            contact_phone, contact_whatsapp, contact_email, contact_instagram,
            contact_company, contact_website,
            confidence, is_spam, needs_review, review_reason, agent_id, property_id, source,
            is_duplicate, duplicate_of)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (post_id, price_usd, price_original, currency,
         result.bedrooms, result.bathrooms, sqm,
         result.neighborhood, result.community, result.property_type,
         result.listing_type, result.furnishing, json.dumps(result.amenities),
         contact_phone, contact_wa, contact_email, ig, company, website,
         result.confidence, 0,
         1 if result.needs_review else 0, result.review_reason,
         agent_id, property_id, source,
         is_duplicate, duplicate_of),
    )

    # --- Link property ↔ agent ---
    if property_id and agent_id:
        link_property_agent(conn, property_id, agent_id, post_id, price_usd)

    # --- Update raw_posts back-references ---
    conn.execute(
        "UPDATE raw_posts SET agent_id=?, property_id=? WHERE post_id=?",
        (agent_id, property_id, post_id),
    )

    # --- Update agent zones ---
    if agent_id:
        update_agent_zones(conn, agent_id)

    return agent_id, property_id


# ============================================================
# Scrape log (unchanged)
# ============================================================

def start_scrape_log(conn: sqlite3.Connection, group_id: str, group_name: str) -> int:
    cur = conn.execute(
        "INSERT INTO scrape_log (group_id, group_name, started_at) VALUES (?, ?, ?)",
        (group_id, group_name, _now()),
    )
    conn.commit()
    return cur.lastrowid


def finish_scrape_log(
    conn: sqlite3.Connection,
    log_id: int,
    posts_captured: int,
    posts_new: int,
    posts_skipped: int,
    status: str = "success",
    error: Optional[str] = None,
):
    conn.execute(
        """UPDATE scrape_log
           SET posts_captured=?, posts_new=?, posts_skipped=?, finished_at=?, status=?, error=?
           WHERE id=?""",
        (posts_captured, posts_new, posts_skipped, _now(), status, error, log_id),
    )
    conn.commit()


# ============================================================
# Stats
# ============================================================

def get_stats(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM raw_posts").fetchone()[0]
    parsed = conn.execute("SELECT COUNT(*) FROM listings WHERE is_spam = 0 AND is_duplicate = 0").fetchone()[0]
    review = conn.execute("SELECT COUNT(*) FROM listings WHERE needs_review=1 AND is_duplicate = 0").fetchone()[0]
    groups = conn.execute("SELECT COUNT(DISTINCT group_id) FROM raw_posts").fetchone()[0]
    agents = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    properties = conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
    pro_agents = conn.execute("SELECT COUNT(*) FROM agents WHERE is_agent=1").fetchone()[0]
    duplicates = conn.execute("SELECT COUNT(*) FROM listings WHERE is_duplicate = 1").fetchone()[0]
    return {
        "total_posts": total,
        "parsed_listings": parsed,
        "needs_review": review,
        "groups_scraped": groups,
        "agents": agents,
        "pro_agents": pro_agents,
        "properties": properties,
        "duplicates_hidden": duplicates,
    }
