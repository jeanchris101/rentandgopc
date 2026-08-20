import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import paramiko

AUDIT_SCRIPT = r'''#!/usr/bin/env python3
import sqlite3, re, sys

DB = "/opt/data/fb_listings.db"
LIMIT = 30

def snippet(text, length=150):
    if not text:
        return "(empty)"
    t = text.replace("\n", " ").replace("\r", " ").strip()
    return t[:length] + ("..." if len(t) > length else "")

def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Check tables exist
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    print(f"Tables: {tables}")

    cur.execute("SELECT COUNT(*) FROM listings")
    total_listings = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM raw_posts")
    total_raw = cur.fetchone()[0]
    print(f"Total listings: {total_listings}, Total raw_posts: {total_raw}\n")

    # Join listings with raw_posts
    JOIN = """
        SELECT l.id, l.post_id, l.price_usd, l.price_original, l.currency,
               l.bedrooms, l.bathrooms, l.sqm, l.neighborhood, l.community,
               l.property_type, l.listing_type, l.confidence, l.is_spam,
               l.needs_review, l.agent_id, l.property_id,
               r.raw_text, r.group_name
        FROM listings l
        LEFT JOIN raw_posts r ON l.post_id = r.post_id
    """

    cur.execute(JOIN)
    rows = cur.fetchall()
    print(f"Joined rows: {len(rows)}\n")

    issues = {
        "land_with_bedrooms": [],
        "villa_is_apartment": [],
        "apartment_is_villa": [],
        "commercial_is_residential": [],
        "dop_as_usd": [],
        "price_too_low": [],
        "bedrooms_gt_10": [],
        "bathrooms_gt_bedrooms": [],
        "sqm_too_large_apt": [],
        "non_re_content": [],
        "too_short_text": [],
    }

    bed_pattern = re.compile(r'\b(bedroom|bedrooms|habitacion|habitaciones|hab|cuarto|cuartos|dormitorio|dormitorios|ba[nñ]o|ba[nñ]os|bathroom|bathrooms)\b', re.IGNORECASE)
    apt_pattern = re.compile(r'\b(apartamento|apto|aptos|apartment|penthouse|pent\s*house|studio)\b', re.IGNORECASE)
    villa_pattern = re.compile(r'\b(villa|villas|casa|casas|house|houses|chalet|chalets|townhouse)\b', re.IGNORECASE)
    commercial_residential = re.compile(r'\b(casa|apartamento|apto|bedroom|habitacion|dormitorio)\b', re.IGNORECASE)
    dop_pattern = re.compile(r'(RD\s*\$|DOP|pesos?\s*dominicano|pesos?\b)', re.IGNORECASE)
    non_re_pattern = re.compile(r'\b(carro|coche|vehiculo|veh[ií]culo|moto|motocicleta|empleo|trabajo|job|iphone|samsung|laptop|computadora|electrodom[eé]stico|lavadora|nevera|refrigerador|televisor|celular|tel[eé]fono)\b', re.IGNORECASE)

    for row in rows:
        raw = row["raw_text"] or ""
        raw_lower = raw.lower()
        ptype = (row["property_type"] or "").lower()
        price = row["price_usd"]
        beds = row["bedrooms"]
        baths = row["bathrooms"]
        sqm = row["sqm"]
        ltype = (row["listing_type"] or "").lower()
        pid = row["post_id"]

        rec = {
            "post_id": pid,
            "property_type": row["property_type"],
            "listing_type": row["listing_type"],
            "price_usd": price,
            "price_original": row["price_original"],
            "currency": row["currency"],
            "bedrooms": beds,
            "bathrooms": baths,
            "sqm": sqm,
            "neighborhood": row["neighborhood"],
            "snippet": snippet(raw),
        }

        # 1. Property type mismatches
        if ptype == "land" and bed_pattern.search(raw):
            rec["issue"] = "Classified as LAND but text mentions bedrooms/bathrooms"
            issues["land_with_bedrooms"].append(rec.copy())

        if ptype == "villa" and apt_pattern.search(raw) and not villa_pattern.search(raw):
            rec["issue"] = "Classified as VILLA but text says apartment/apto"
            issues["villa_is_apartment"].append(rec.copy())

        if ptype == "apartment" and villa_pattern.search(raw) and not apt_pattern.search(raw):
            rec["issue"] = "Classified as APARTMENT but text says villa/casa/house"
            issues["apartment_is_villa"].append(rec.copy())

        if ptype == "commercial" and commercial_residential.search(raw):
            rec["issue"] = "Classified as COMMERCIAL but text mentions residential keywords"
            issues["commercial_is_residential"].append(rec.copy())

        # 2. Price currency confusion
        if price and price >= 100000 and dop_pattern.search(raw):
            rec["issue"] = f"Price USD={price:,.0f} but text mentions RD$/DOP/pesos — likely DOP stored as USD"
            issues["dop_as_usd"].append(rec.copy())

        if price and price < 5000 and price > 0 and ptype in ("apartment", "villa", "house", "condo", "penthouse") and ltype == "sale":
            rec["issue"] = f"Sale price USD={price:,.0f} seems too low for {ptype}"
            issues["price_too_low"].append(rec.copy())

        # 3. Bedroom/bathroom sanity
        if beds and beds > 10:
            rec["issue"] = f"Bedrooms={beds} — likely parsing error"
            issues["bedrooms_gt_10"].append(rec.copy())

        if beds and baths and baths > beds + 2:
            rec["issue"] = f"Bathrooms={baths} > Bedrooms={beds}+2 — unusual"
            issues["bathrooms_gt_bedrooms"].append(rec.copy())

        if sqm and sqm > 5000 and ptype == "apartment":
            rec["issue"] = f"Apartment with sqm={sqm:,.0f} — likely sqft or terrain, not built area"
            issues["sqm_too_large_apt"].append(rec.copy())

        # 4. Spam / non-RE
        if non_re_pattern.search(raw) and not row["is_spam"]:
            rec["issue"] = "Non-RE content (cars, jobs, electronics) not flagged as spam"
            issues["non_re_content"].append(rec.copy())

        if len(raw.strip()) < 20 and len(raw.strip()) > 0:
            rec["issue"] = f"Very short text ({len(raw.strip())} chars): '{raw.strip()}'"
            issues["too_short_text"].append(rec.copy())

    # Print results
    print("=" * 100)
    print("AUDIT RESULTS — PROPERTY TYPE & PRICE ERRORS")
    print("=" * 100)

    category_labels = {
        "land_with_bedrooms": "1a. LAND classified but text mentions bedrooms/bathrooms",
        "villa_is_apartment": "1b. VILLA classified but text says apartment",
        "apartment_is_villa": "1c. APARTMENT classified but text says villa/casa",
        "commercial_is_residential": "1d. COMMERCIAL classified but text is residential",
        "dop_as_usd": "2a. DOP price likely stored as USD",
        "price_too_low": "2b. Sale price suspiciously low",
        "bedrooms_gt_10": "3a. Bedrooms > 10 (parsing error)",
        "bathrooms_gt_bedrooms": "3b. Bathrooms > Bedrooms + 2",
        "sqm_too_large_apt": "3c. Apartment sqm > 5000 (likely error)",
        "non_re_content": "4a. Non-RE content not flagged as spam",
        "too_short_text": "4b. Very short raw text (< 20 chars)",
    }

    total_issues = 0
    for key, label in category_labels.items():
        items = issues[key]
        total_issues += len(items)
        print(f"\n{'─' * 100}")
        print(f"  {label}: {len(items)} found")
        print(f"{'─' * 100}")
        for item in items[:LIMIT]:
            print(f"  post_id: {item['post_id']}")
            print(f"    type={item['property_type']}, listing={item['listing_type']}, "
                  f"price_usd={item['price_usd']}, currency={item['currency']}, "
                  f"beds={item['bedrooms']}, baths={item['bathrooms']}, sqm={item['sqm']}")
            print(f"    neighborhood={item['neighborhood']}")
            print(f"    ISSUE: {item['issue']}")
            print(f"    TEXT: {item['snippet']}")
            print()
        if len(items) > LIMIT:
            print(f"  ... and {len(items) - LIMIT} more")

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Total listings audited: {len(rows)}")
    print(f"Total issues found: {total_issues}")
    print()
    for key, label in category_labels.items():
        count = len(issues[key])
        pct = (count / len(rows) * 100) if rows else 0
        print(f"  {label}: {count} ({pct:.1f}%)")

    # Property type distribution
    print(f"\n{'─' * 60}")
    print("PROPERTY TYPE DISTRIBUTION")
    cur2 = conn.cursor()
    cur2.execute("SELECT property_type, COUNT(*) as cnt FROM listings GROUP BY property_type ORDER BY cnt DESC")
    for r in cur2.fetchall():
        print(f"  {r[0] or '(null)'}: {r[1]}")

    print(f"\n{'─' * 60}")
    print("LISTING TYPE DISTRIBUTION")
    cur2.execute("SELECT listing_type, COUNT(*) as cnt FROM listings GROUP BY listing_type ORDER BY cnt DESC")
    for r in cur2.fetchall():
        print(f"  {r[0] or '(null)'}: {r[1]}")

    print(f"\n{'─' * 60}")
    print("CURRENCY DISTRIBUTION")
    cur2.execute("SELECT currency, COUNT(*) as cnt FROM listings GROUP BY currency ORDER BY cnt DESC")
    for r in cur2.fetchall():
        print(f"  {r[0] or '(null)'}: {r[1]}")

    conn.close()

if __name__ == "__main__":
    main()
'''

# Connect and run
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
print("Connecting to VPS...")
ssh.connect("144.172.100.16", username="root", password="4K98JSaEoLDaP5", timeout=15)
print("Connected.")

# Write audit script to VPS
sftp = ssh.open_sftp()
with sftp.open("/tmp/audit_props.py", "w") as f:
    f.write(AUDIT_SCRIPT)
sftp.close()
print("Script deployed to /tmp/audit_props.py")

# Execute
print("Running audit...\n")
stdin, stdout, stderr = ssh.exec_command("python3 /tmp/audit_props.py", timeout=60)
out = stdout.read().decode("utf-8", errors="replace")
err = stderr.read().decode("utf-8", errors="replace")

if out:
    print(out)
if err:
    print("STDERR:", err)

ssh.close()
print("Done.")
