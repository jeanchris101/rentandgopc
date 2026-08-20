"""
reparse_all.py — Re-parse ALL existing listings using the updated parser + _to_usd.
Fixes: wrong DOP→USD conversions, missing zones/neighborhoods, wrong property types.
Runs directly on VPS against the live DB.

This re-processes raw_text from raw_posts through the parser, then updates
the listings table with corrected values.
"""

import json
import logging
import sqlite3
import sys
from pathlib import Path

# Add parent to path so we can import parser
sys.path.insert(0, str(Path(__file__).parent))

from parser import parse
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("reparse")

DB_PATH = Path("/opt/data/fb_listings.db")
BATCH_SIZE = 200
DRY_RUN = False  # Set True to preview without writing


def _to_usd(amount: float, currency: str, is_rental: bool = False) -> Optional[float]:
    """Same smart logic as database.py — duplicated here to avoid circular imports."""
    if currency == 'USD':
        return amount
    elif currency == 'DOP':
        if is_rental:
            if amount < 15_000:
                return amount
            elif amount > 80_000:
                return amount
            else:
                return round(amount / 58.0, 2)
        else:
            if amount < 2_000_000:
                return amount
            else:
                return round(amount / 58.0, 2)
    elif currency == 'EUR':
        return round(amount * 1.08, 2)
    elif currency == 'CAD':
        return round(amount * 0.74, 2)
    return None


def _to_sqm(value: float, unit: str) -> float:
    if unit == 'sqm':
        return value
    return round(value * 0.0929, 2)


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Get all raw posts that have listings
    total = conn.execute("""
        SELECT COUNT(*) FROM listings l
        JOIN raw_posts r ON l.post_id = r.post_id
        WHERE l.is_spam = 0
    """).fetchone()[0]

    log.info(f"Re-parsing {total} non-spam listings")

    updated = 0
    price_changed = 0
    zone_changed = 0
    type_changed = 0
    errors = 0
    offset = 0

    while offset < total:
        rows = conn.execute("""
            SELECT l.id, l.post_id, l.price_usd as old_price, l.price_original as old_original,
                   l.currency as old_currency, l.neighborhood as old_zone, l.community as old_community,
                   l.property_type as old_ptype, l.listing_type as old_ltype,
                   l.bedrooms as old_beds, l.bathrooms as old_baths, l.sqm as old_sqm,
                   r.raw_text, r.author_name
            FROM listings l
            JOIN raw_posts r ON l.post_id = r.post_id
            WHERE l.is_spam = 0
            ORDER BY l.id
            LIMIT ? OFFSET ?
        """, (BATCH_SIZE, offset)).fetchall()

        if not rows:
            break

        for row in rows:
            try:
                raw_text = row["raw_text"] or ""
                if not raw_text.strip():
                    continue

                result = parse(raw_text)

                # Calculate new values
                new_price_usd = None
                new_price_original = None
                new_currency = None
                if result.price:
                    new_price_original = result.price.amount
                    new_currency = result.price.currency

                    is_rental = False
                    if result.listing_type and ('rent' in result.listing_type.lower() or 'alquiler' in result.listing_type.lower()):
                        is_rental = True
                    elif result.price.is_monthly:
                        is_rental = True

                    new_price_usd = _to_usd(new_price_original, new_currency, is_rental=is_rental)

                new_zone = result.zone
                new_community = result.community
                new_ptype = result.property_type
                new_ltype = result.listing_type
                new_beds = result.bedrooms
                new_baths = result.bathrooms
                new_sqm = _to_sqm(result.area.value, result.area.unit) if result.area else None

                # Check what changed
                changes = {}
                if new_price_usd and new_price_usd != row["old_price"]:
                    changes["price_usd"] = new_price_usd
                if new_price_original and new_price_original != row["old_original"]:
                    changes["price_original"] = new_price_original
                if new_currency and new_currency != row["old_currency"]:
                    changes["currency"] = new_currency
                if new_zone and new_zone != row["old_zone"]:
                    changes["neighborhood"] = new_zone
                if new_community and new_community != row["old_community"]:
                    changes["community"] = new_community
                if new_ptype and new_ptype != row["old_ptype"]:
                    changes["property_type"] = new_ptype
                if new_ltype and new_ltype != row["old_ltype"]:
                    changes["listing_type"] = new_ltype
                if new_beds and new_beds != row["old_beds"]:
                    changes["bedrooms"] = new_beds
                if new_baths and new_baths != row["old_baths"]:
                    changes["bathrooms"] = new_baths
                if new_sqm and new_sqm != row["old_sqm"]:
                    changes["sqm"] = new_sqm

                if not changes:
                    continue

                # Track what kind of changes
                if "price_usd" in changes:
                    price_changed += 1
                    old_p = row["old_price"] or 0
                    new_p = changes["price_usd"]
                    # Log significant price changes
                    if old_p > 0 and abs(new_p - old_p) / old_p > 0.5:
                        log.info(f"  Price fix: ${old_p:,.0f} → ${new_p:,.0f} (post {row['post_id'][:25]})")
                if "neighborhood" in changes:
                    zone_changed += 1
                if "property_type" in changes or "listing_type" in changes:
                    type_changed += 1

                if not DRY_RUN:
                    set_clause = ", ".join(f"{k} = ?" for k in changes)
                    values = list(changes.values()) + [row["id"]]
                    conn.execute(f"UPDATE listings SET {set_clause} WHERE id = ?", values)

                updated += 1

            except Exception as e:
                errors += 1
                if errors <= 10:
                    log.warning(f"  Error on listing {row['id']}: {e}")

        conn.commit()
        offset += BATCH_SIZE
        log.info(f"Progress: {min(offset, total)}/{total} — updated: {updated}, prices: {price_changed}, zones: {zone_changed}, types: {type_changed}")

    conn.close()
    mode = "DRY RUN" if DRY_RUN else "APPLIED"
    log.info(f"Done ({mode}) — {updated} listings updated: {price_changed} prices, {zone_changed} zones, {type_changed} types, {errors} errors")


if __name__ == "__main__":
    if "--dry-run" in sys.argv:
        DRY_RUN = True
        log.info("DRY RUN MODE — no changes will be written")
    main()
