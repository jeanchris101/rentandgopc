"""
export.py — Export SQLite data to JSON for the dashboard.
Exports: properties, agents, listings (with joins), and stats.
Outputs to automation/data/listings-data.json.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from database import get_connection, init_db, _json_list

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "listings-data.json"


def export_listings():
    """Export full market intelligence data to JSON."""
    conn = get_connection()
    init_db(conn)

    # --- Properties ---
    prop_rows = conn.execute("""
        SELECT p.*,
            (SELECT COUNT(*) FROM property_agents pa WHERE pa.property_id = p.id) as agent_count,
            (SELECT COUNT(*) FROM listings l WHERE l.property_id = p.id) as post_count
        FROM properties p
        ORDER BY p.last_seen_at DESC
    """).fetchall()

    properties = []
    for r in prop_rows:
        properties.append({
            "id": r["id"],
            "zone": r["zone"],
            "community": r["community"],
            "propertyType": r["property_type"],
            "bedrooms": r["bedrooms"],
            "bathrooms": r["bathrooms"],
            "sqm": r["sqm"],
            "priceUsd": r["price_usd"],
            "priceHistory": _json_list(r["price_history"]),
            "listingType": r["listing_type"],
            "furnished": r["furnished"],
            "amenities": _json_list(r["amenities"]),
            "description": (r["description"] or "")[:1000],
            "imageUrls": _json_list(r["image_urls"])[:5],
            "firstListedAt": r["first_listed_at"],
            "lastSeenAt": r["last_seen_at"],
            "daysOnMarket": r["days_on_market"],
            "status": r["status"],
            "agentCount": r["agent_count"],
            "postCount": r["post_count"],
        })

    # --- Agents ---
    agent_rows = conn.execute("""
        SELECT * FROM agents ORDER BY total_listings DESC
    """).fetchall()

    agents = []
    for r in agent_rows:
        agents.append({
            "id": r["id"],
            "name": r["name"],
            "fbProfileUrl": r["fb_profile_url"],
            "phones": _json_list(r["phones"]),
            "whatsapp": _json_list(r["whatsapp"]),
            "emails": _json_list(r["emails"]),
            "instagram": r["instagram"],
            "company": r["company"],
            "website": r["website"],
            "primaryZones": _json_list(r["primary_zones"]),
            "totalListings": r["total_listings"],
            "firstSeenAt": r["first_seen_at"],
            "lastSeenAt": r["last_seen_at"],
            "avgPriceRange": r["avg_price_range"],
            "isAgent": bool(r["is_agent"]),
        })

    # --- Listings (posts with parsed data) ---
    listing_rows = conn.execute("""
        SELECT
            r.post_id, r.group_id, r.group_name, r.author_name,
            r.raw_text, r.image_urls, r.timestamp, r.permalink, r.captured_at,
            l.price_usd, l.price_original, l.currency,
            l.bedrooms, l.bathrooms, l.sqm,
            l.neighborhood, l.community, l.property_type, l.listing_type, l.furnished,
            l.amenities,
            l.contact_phone, l.contact_whatsapp, l.contact_email,
            l.contact_instagram, l.contact_company, l.contact_website,
            l.confidence, l.is_spam,
            l.needs_review, l.review_reason,
            l.agent_id, l.property_id,
            r.source
        FROM raw_posts r
        LEFT JOIN listings l ON r.post_id = l.post_id
        ORDER BY r.captured_at DESC
    """).fetchall()

    listings = []
    for r in listing_rows:
        listings.append({
            "postId": r["post_id"],
            "groupId": r["group_id"],
            "groupName": r["group_name"],
            "authorName": r["author_name"],
            "rawText": (r["raw_text"] or "")[:1000],
            "imageUrls": _json_list(r["image_urls"])[:5],
            "timestamp": r["timestamp"],
            "permalink": r["permalink"],
            "capturedAt": r["captured_at"],
            "priceUsd": r["price_usd"],
            "priceOriginal": r["price_original"],
            "currency": r["currency"],
            "bedrooms": r["bedrooms"],
            "bathrooms": r["bathrooms"],
            "sqm": r["sqm"],
            "neighborhood": r["neighborhood"],
            "community": r["community"],
            "propertyType": r["property_type"],
            "listingType": r["listing_type"],
            "furnished": r["furnished"],
            "amenities": _json_list(r["amenities"]),
            "contactPhone": r["contact_phone"],
            "contactWhatsApp": r["contact_whatsapp"],
            "contactEmail": r["contact_email"],
            "contactInstagram": r["contact_instagram"],
            "contactCompany": r["contact_company"],
            "contactWebsite": r["contact_website"],
            "needsReview": bool(r["needs_review"]),
            "reviewReason": r["review_reason"],
            "confidence": r["confidence"],
            "isSpam": bool(r["is_spam"]),
            "agentId": r["agent_id"],
            "propertyId": r["property_id"],
            "source": r["source"] or "facebook",
        })

    # --- Stats ---
    total_listings = len(listings)
    parsed_ok = sum(1 for l in listings if not l["needsReview"])
    needs_review = total_listings - parsed_ok

    neighborhoods = {}
    for l in listings:
        if l["neighborhood"]:
            neighborhoods[l["neighborhood"]] = neighborhoods.get(l["neighborhood"], 0) + 1

    property_types = {}
    for p in properties:
        if p["propertyType"]:
            property_types[p["propertyType"]] = property_types.get(p["propertyType"], 0) + 1

    listing_types = {}
    for p in properties:
        if p["listingType"]:
            listing_types[p["listingType"]] = listing_types.get(p["listingType"], 0) + 1

    export_data = {
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "totalPosts": total_listings,
            "parsedOk": parsed_ok,
            "needsReview": needs_review,
            "totalProperties": len(properties),
            "totalAgents": len(agents),
            "proAgents": sum(1 for a in agents if a["isAgent"]),
            "neighborhoods": dict(sorted(neighborhoods.items(), key=lambda x: -x[1])),
            "propertyTypes": property_types,
            "listingTypes": listing_types,
        },
        "properties": properties,
        "agents": agents,
        "listings": listings,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)

    conn.close()

    print(f"Exported to {OUTPUT_PATH}")
    print(f"  Properties: {len(properties)}")
    print(f"  Agents: {len(agents)} ({sum(1 for a in agents if a['isAgent'])} pro)")
    print(f"  Listings: {total_listings} ({parsed_ok} parsed, {needs_review} review)")
    print(f"  Top zones: {dict(sorted(neighborhoods.items(), key=lambda x: -x[1])[:10])}")

    return export_data


if __name__ == "__main__":
    export_listings()
