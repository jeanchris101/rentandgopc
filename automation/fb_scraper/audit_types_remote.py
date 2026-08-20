import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import paramiko

AUDIT_SCRIPT = r'''
import sqlite3, re, json

DB = "/opt/data/fb_listings.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

def snippet(text, n=150):
    if not text:
        return "(no text)"
    t = text.replace("\n", " ").replace("\r", " ").strip()
    return t[:n] + ("..." if len(t) > n else "")

def has_pattern(text, patterns):
    if not text:
        return False
    t = text.lower()
    for p in patterns:
        if re.search(p, t):
            return True
    return False

RENT_KEYWORDS = [
    r'\balquiler\b', r'\brenta\b', r'\bse alquila\b', r'\bfor rent\b',
    r'\bmonthly\b', r'\bmensual\b', r'\bper month\b', r'\bpor mes\b',
    r'\bavailable for rent\b', r'\b/mes\b', r'\bal mes\b',
    r'\bse renta\b', r'\ben renta\b', r'\ben alquiler\b'
]

SALE_KEYWORDS = [
    r'\bse vende\b', r'\bfor sale\b', r'\bventa directa\b',
    r'\bprecio de venta\b', r'\boportunidad de compra\b',
    r'\ben venta\b', r'\bvendo\b', r'\ba la venta\b'
]

LIMIT = 50
results = {}

# ---- Category 1: listing_type='sale' but text has rental keywords ----
print("=" * 80)
print("CATEGORY 1: Listed as SALE but raw_text has rental keywords")
print("=" * 80)
cur = conn.execute("""
    SELECT l.id, l.post_id, l.listing_type, l.price_usd, r.raw_text
    FROM listings l
    JOIN raw_posts r ON l.post_id = r.post_id
    WHERE l.listing_type = 'sale'
""")
cat1 = []
for row in cur:
    if has_pattern(row["raw_text"], RENT_KEYWORDS):
        cat1.append(row)
results["cat1_sale_has_rent_keywords"] = len(cat1)
for row in cat1[:LIMIT]:
    print(f"  post_id={row['post_id']} | type={row['listing_type']} | price=${row['price_usd']} | suggested=rent")
    print(f"    text: {snippet(row['raw_text'])}")
    print()
if not cat1:
    print("  (none found)")
print(f"  TOTAL: {len(cat1)}\n")

# ---- Category 2: listing_type='rent' but text has sale keywords AND price > $50k ----
print("=" * 80)
print("CATEGORY 2: Listed as RENT but raw_text has sale keywords AND price > $50,000")
print("=" * 80)
cur = conn.execute("""
    SELECT l.id, l.post_id, l.listing_type, l.price_usd, r.raw_text
    FROM listings l
    JOIN raw_posts r ON l.post_id = r.post_id
    WHERE l.listing_type = 'rent'
      AND l.price_usd > 50000
""")
cat2 = []
for row in cur:
    if has_pattern(row["raw_text"], SALE_KEYWORDS):
        cat2.append(row)
results["cat2_rent_has_sale_keywords_highprice"] = len(cat2)
for row in cat2[:LIMIT]:
    print(f"  post_id={row['post_id']} | type={row['listing_type']} | price=${row['price_usd']} | suggested=sale")
    print(f"    text: {snippet(row['raw_text'])}")
    print()
if not cat2:
    print("  (none found)")
print(f"  TOTAL: {len(cat2)}\n")

# ---- Category 3: listing_type is NULL/unknown but text clearly indicates sale or rent ----
print("=" * 80)
print("CATEGORY 3: listing_type is NULL/unknown but text indicates sale or rent")
print("=" * 80)
cur = conn.execute("""
    SELECT l.id, l.post_id, l.listing_type, l.price_usd, r.raw_text
    FROM listings l
    JOIN raw_posts r ON l.post_id = r.post_id
    WHERE l.listing_type IS NULL OR l.listing_type = '' OR l.listing_type = 'unknown'
""")
cat3_sale = []
cat3_rent = []
for row in cur:
    is_sale = has_pattern(row["raw_text"], SALE_KEYWORDS)
    is_rent = has_pattern(row["raw_text"], RENT_KEYWORDS)
    if is_sale and not is_rent:
        cat3_sale.append(row)
    elif is_rent and not is_sale:
        cat3_rent.append(row)
    elif is_sale and is_rent:
        # ambiguous - show but note
        cat3_sale.append(row)  # default to sale if both present
results["cat3_null_likely_sale"] = len(cat3_sale)
results["cat3_null_likely_rent"] = len(cat3_rent)

print(f"\n  --- Likely SALE ({len(cat3_sale)} found) ---")
for row in cat3_sale[:LIMIT]:
    print(f"  post_id={row['post_id']} | type={row['listing_type']} | price=${row['price_usd']} | suggested=sale")
    print(f"    text: {snippet(row['raw_text'])}")
    print()

print(f"\n  --- Likely RENT ({len(cat3_rent)} found) ---")
for row in cat3_rent[:LIMIT]:
    print(f"  post_id={row['post_id']} | type={row['listing_type']} | price=${row['price_usd']} | suggested=rent")
    print(f"    text: {snippet(row['raw_text'])}")
    print()
if not cat3_sale and not cat3_rent:
    print("  (none found)")
print(f"  TOTAL: {len(cat3_sale) + len(cat3_rent)}\n")

# ---- Category 4: Price anomalies ----
print("=" * 80)
print("CATEGORY 4: Price anomalies")
print("=" * 80)

# 4a: Rentals with price > $50,000
print("\n  --- 4a: Rentals with price_usd > $50,000 (probably sales) ---")
cur = conn.execute("""
    SELECT l.id, l.post_id, l.listing_type, l.price_usd, r.raw_text
    FROM listings l
    JOIN raw_posts r ON l.post_id = r.post_id
    WHERE l.listing_type = 'rent' AND l.price_usd > 50000
    ORDER BY l.price_usd DESC
    LIMIT ?
""", (LIMIT,))
cat4a = cur.fetchall()
results["cat4a_rent_over_50k"] = len(cat4a)
for row in cat4a:
    print(f"  post_id={row['post_id']} | type={row['listing_type']} | price=${row['price_usd']:,.0f} | suggested=sale")
    print(f"    text: {snippet(row['raw_text'])}")
    print()
if not cat4a:
    print("  (none found)")
# get full count
full_count = conn.execute("SELECT COUNT(*) FROM listings WHERE listing_type='rent' AND price_usd > 50000").fetchone()[0]
print(f"  TOTAL: {full_count}")
results["cat4a_rent_over_50k"] = full_count

# 4b: Sales with price < $100 and > 0
print("\n  --- 4b: Sales with $0 < price_usd < $100 (probably rentals or errors) ---")
cur = conn.execute("""
    SELECT l.id, l.post_id, l.listing_type, l.price_usd, r.raw_text
    FROM listings l
    JOIN raw_posts r ON l.post_id = r.post_id
    WHERE l.listing_type = 'sale' AND l.price_usd > 0 AND l.price_usd < 100
    ORDER BY l.price_usd ASC
    LIMIT ?
""", (LIMIT,))
cat4b = cur.fetchall()
results["cat4b_sale_under_100"] = len(cat4b)
for row in cat4b:
    print(f"  post_id={row['post_id']} | type={row['listing_type']} | price=${row['price_usd']:,.2f} | suggested=rent_or_error")
    print(f"    text: {snippet(row['raw_text'])}")
    print()
if not cat4b:
    print("  (none found)")
full_count = conn.execute("SELECT COUNT(*) FROM listings WHERE listing_type='sale' AND price_usd > 0 AND price_usd < 100").fetchone()[0]
print(f"  TOTAL: {full_count}")
results["cat4b_sale_under_100"] = full_count

# 4c: Sales with price > $10M
print("\n  --- 4c: Sales with price_usd > $10,000,000 (probably parsing error) ---")
cur = conn.execute("""
    SELECT l.id, l.post_id, l.listing_type, l.price_usd, r.raw_text
    FROM listings l
    JOIN raw_posts r ON l.post_id = r.post_id
    WHERE l.listing_type = 'sale' AND l.price_usd > 10000000
    ORDER BY l.price_usd DESC
    LIMIT ?
""", (LIMIT,))
cat4c = cur.fetchall()
results["cat4c_sale_over_10m"] = len(cat4c)
for row in cat4c:
    print(f"  post_id={row['post_id']} | type={row['listing_type']} | price=${row['price_usd']:,.0f} | suggested=parsing_error")
    print(f"    text: {snippet(row['raw_text'])}")
    print()
if not cat4c:
    print("  (none found)")
full_count = conn.execute("SELECT COUNT(*) FROM listings WHERE listing_type='sale' AND price_usd > 10000000").fetchone()[0]
print(f"  TOTAL: {full_count}")
results["cat4c_sale_over_10m"] = full_count

# 4d: Rentals with price > $100,000
print("\n  --- 4d: Rentals with price_usd > $100,000 (probably sales) ---")
cur = conn.execute("""
    SELECT l.id, l.post_id, l.listing_type, l.price_usd, r.raw_text
    FROM listings l
    JOIN raw_posts r ON l.post_id = r.post_id
    WHERE l.listing_type = 'rent' AND l.price_usd > 100000
    ORDER BY l.price_usd DESC
    LIMIT ?
""", (LIMIT,))
cat4d = cur.fetchall()
results["cat4d_rent_over_100k"] = len(cat4d)
for row in cat4d:
    print(f"  post_id={row['post_id']} | type={row['listing_type']} | price=${row['price_usd']:,.0f} | suggested=sale")
    print(f"    text: {snippet(row['raw_text'])}")
    print()
if not cat4d:
    print("  (none found)")
full_count = conn.execute("SELECT COUNT(*) FROM listings WHERE listing_type='rent' AND price_usd > 100000").fetchone()[0]
print(f"  TOTAL: {full_count}")
results["cat4d_rent_over_100k"] = full_count

# ---- Summary ----
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

# Overall stats
total = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
sales = conn.execute("SELECT COUNT(*) FROM listings WHERE listing_type='sale'").fetchone()[0]
rents = conn.execute("SELECT COUNT(*) FROM listings WHERE listing_type='rent'").fetchone()[0]
nulls = conn.execute("SELECT COUNT(*) FROM listings WHERE listing_type IS NULL OR listing_type='' OR listing_type='unknown'").fetchone()[0]
others = total - sales - rents - nulls

print(f"\nDatabase overview:")
print(f"  Total listings: {total}")
print(f"  Sales: {sales}")
print(f"  Rentals: {rents}")
print(f"  NULL/unknown type: {nulls}")
print(f"  Other types: {others}")

print(f"\nMisclassification issues found:")
for k, v in results.items():
    print(f"  {k}: {v}")

total_issues = sum(results.values())
print(f"\n  GRAND TOTAL potential issues: {total_issues}")

conn.close()
'''

# Connect to VPS and run
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
print("Connecting to VPS 144.172.100.16...")
ssh.connect("144.172.100.16", username="root", password="4K98JSaEoLDaP5", timeout=15)
print("Connected. Uploading audit script...")

# Write the script to the VPS
sftp = ssh.open_sftp()
with sftp.open("/tmp/audit_types.py", "w") as f:
    f.write(AUDIT_SCRIPT)
sftp.close()
print("Script uploaded. Executing...")

# Execute
stdin, stdout, stderr = ssh.exec_command("python3 /tmp/audit_types.py", timeout=60)
out = stdout.read().decode("utf-8", errors="replace")
err = stderr.read().decode("utf-8", errors="replace")

if out:
    print(out)
if err:
    print("STDERR:", err)

ssh.close()
print("Done.")
