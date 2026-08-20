import sqlite3, json, os

conn = sqlite3.connect("/opt/data/fb_listings.db")
c = conn.cursor()

print("=== NON-RE CONTENT VISIBLE IN PUNTA CANA TAB ===")
keywords = ["car", "vehicle", "honda", "toyota", "iphone", "samsung", "laptop", "motorcycle", "moto", "scooter", "boat", "yate", "furniture", "sofa", "lavadora", "nevera"]
for kw in keywords:
    r = c.execute(
        "SELECT COUNT(*) FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
        "WHERE (l.price_usd IS NOT NULL OR l.property_type IS NOT NULL OR l.bedrooms IS NOT NULL) "
        "AND l.is_spam = 0 AND l.confidence >= 0.3 "
        "AND LOWER(r.raw_text) LIKE ?", ("%" + kw + "%",)
    ).fetchone()
    if r[0] > 0:
        print("  '%s' matches: %d" % (kw, r[0]))

print("")
print("=== FB CDN IMAGE URL AGE CHECK ===")
r = c.execute(
    "SELECT MIN(r.captured_at) as oldest, MAX(r.captured_at) as newest "
    "FROM raw_posts r WHERE r.image_urls IS NOT NULL AND r.image_urls != '[]'"
).fetchone()
print("Oldest post with images: %s" % r[0])
print("Newest post with images: %s" % r[1])

print("")
print("=== IMAGE COUNT PER LISTING ===")
counts = {}
for row in c.execute("SELECT r.image_urls FROM raw_posts r"):
    urls = row[0]
    if not urls or urls == "[]" or urls == "":
        n = 0
    else:
        try:
            n = len(json.loads(urls))
        except:
            n = 0
    key = str(n) if n <= 5 else "6+"
    counts[key] = counts.get(key, 0) + 1
for k in sorted(counts.keys()):
    print("  %s images: %d posts" % (k, counts[k]))

print("")
print("=== MARKETPLACE PROPERTY TYPES (visible, is_listing) ===")
for row in c.execute(
    "SELECT l.property_type, COUNT(*) as cnt "
    "FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "WHERE r.group_name = 'Facebook Marketplace' "
    "AND (l.price_usd IS NOT NULL OR l.property_type IS NOT NULL OR l.bedrooms IS NOT NULL) "
    "AND l.is_spam = 0 AND l.confidence >= 0.3 "
    "GROUP BY l.property_type ORDER BY cnt DESC LIMIT 15"
):
    print("  type=%s: %d" % (row[0], row[1]))

print("")
print("=== MARKETPLACE SAMPLE WITH IMAGES (check for non-RE) ===")
for row in c.execute(
    "SELECT l.property_type, l.listing_type, l.price_usd, l.confidence, "
    "SUBSTR(r.raw_text, 1, 100) as txt "
    "FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "WHERE r.group_name = 'Facebook Marketplace' "
    "AND (l.price_usd IS NOT NULL OR l.property_type IS NOT NULL OR l.bedrooms IS NOT NULL) "
    "AND l.is_spam = 0 AND l.confidence >= 0.3 "
    "AND l.confidence < 0.6 "
    "ORDER BY l.confidence ASC LIMIT 20"
):
    print("  conf=%.2f $%s type=%s for=%s | %s" % (
        row[3] or 0, row[2] or "?", row[0] or "?", row[1] or "?", row[4]
    ))

print("")
print("=== RENTALS IN DB ===")
for row in c.execute(
    "SELECT listing_type, COUNT(*) FROM listings "
    "WHERE listing_type IN ('rent','rental','alquiler','short_term_rent') "
    "GROUP BY listing_type"
):
    print("  %s: %d" % (row[0], row[1]))

print("")
print("=== CONSTRUCTORAS FILE ===")
path = "/opt/fb_scraper/constructoras.json"
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
    print("Total constructoras: %d" % len(data))
    if data:
        print("Sample keys: %s" % list(data[0].keys()))
else:
    print("File not found at %s" % path)

print("")
print("=== PC_ONLY FILTER: non-PC cities that leak through ===")
non_pc = ["santo domingo", "santiago", "la romana", "san pedro", "puerto plata", "samana", "sosua", "cabarete"]
for city in non_pc:
    r = c.execute(
        "SELECT COUNT(*) FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
        "WHERE (l.price_usd IS NOT NULL OR l.property_type IS NOT NULL OR l.bedrooms IS NOT NULL) "
        "AND l.is_spam = 0 AND l.confidence >= 0.3 "
        "AND (LOWER(COALESCE(l.neighborhood,'')) LIKE ? "
        "OR LOWER(SUBSTR(COALESCE(r.raw_text,''),1,300)) LIKE ?)",
        ("%" + city + "%", "%" + city + "%")
    ).fetchone()
    if r[0] > 0:
        print("  '%s': %d listings" % (city, r[0]))

print("")
print("=== SALE vs RENT not separated in PC tab ===")
r = c.execute(
    "SELECT l.listing_type, COUNT(*) as cnt "
    "FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "WHERE (l.price_usd IS NOT NULL OR l.property_type IS NOT NULL OR l.bedrooms IS NOT NULL) "
    "AND l.is_spam = 0 AND l.confidence >= 0.3 "
    "GROUP BY l.listing_type ORDER BY cnt DESC"
).fetchall()
for row in r:
    print("  %s: %d" % (row[0] or "NULL/unknown", row[1]))

conn.close()
