import sqlite3, json

conn = sqlite3.connect("/opt/data/fb_listings.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("=== IMAGE STATS ===")
r = c.execute("""SELECT COUNT(*) as total,
    SUM(CASE WHEN r.image_urls IS NOT NULL AND r.image_urls != '' AND r.image_urls != '[]' THEN 1 ELSE 0 END) as wi,
    SUM(CASE WHEN r.image_urls IS NULL OR r.image_urls = '' OR r.image_urls = '[]' THEN 1 ELSE 0 END) as wo
FROM listings l JOIN raw_posts r ON l.post_id = r.post_id""").fetchone()
print("Total: %s, With images: %s, Without images: %s" % (r[0], r[1], r[2]))

print("\n=== SPAM STATS ===")
for row in c.execute("SELECT is_spam, COUNT(*) FROM listings GROUP BY is_spam"):
    print("is_spam=%s: %s" % (row[0], row[1]))

print("\n=== CONFIDENCE DISTRIBUTION ===")
for row in c.execute("""SELECT CASE WHEN confidence >= 0.8 THEN 'high(0.8+)'
    WHEN confidence >= 0.5 THEN 'medium(0.5-0.8)'
    WHEN confidence >= 0.3 THEN 'low(0.3-0.5)'
    ELSE 'very_low(<0.3)' END as tier, COUNT(*)
FROM listings GROUP BY tier"""):
    print("%s: %s" % (row[0], row[1]))

print("\n=== LISTINGS TABLE COLUMNS ===")
for col in c.execute("PRAGMA table_info(listings)"):
    print("  %s (%s)" % (col[1], col[2]))

print("\n=== RAW_POSTS TABLE COLUMNS ===")
for col in c.execute("PRAGMA table_info(raw_posts)"):
    print("  %s (%s)" % (col[1], col[2]))

print("\n=== SAMPLE IMAGE URLS ===")
for row in c.execute("SELECT image_urls FROM raw_posts WHERE image_urls IS NOT NULL AND image_urls != '[]' LIMIT 5"):
    urls = row[0]
    if urls:
        try:
            parsed = json.loads(urls)
            if parsed:
                print("  Count: %d, URL: %s" % (len(parsed), parsed[0][:140]))
        except:
            print("  Raw: %s" % urls[:150])

print("\n=== LISTING TYPE BREAKDOWN ===")
for row in c.execute("SELECT listing_type, COUNT(*) as c FROM listings WHERE listing_type IS NOT NULL GROUP BY listing_type ORDER BY c DESC"):
    print("  %s: %s" % (row[0], row[1]))

print("\n=== PROPERTY TYPE BREAKDOWN ===")
for row in c.execute("SELECT property_type, COUNT(*) as c FROM listings WHERE property_type IS NOT NULL GROUP BY property_type ORDER BY c DESC"):
    print("  %s: %s" % (row[0], row[1]))

print("\n=== VISIBLE IN PUNTA CANA TAB (is_listing filter) ===")
r = c.execute("""SELECT COUNT(*) FROM listings l JOIN raw_posts r ON l.post_id = r.post_id
WHERE (l.price_usd IS NOT NULL OR l.property_type IS NOT NULL OR l.bedrooms IS NOT NULL)
AND l.is_spam = 0 AND l.confidence >= 0.3""").fetchone()
print("Total matching is_listing: %s" % r[0])

print("\n=== NEEDS REVIEW ===")
r = c.execute("SELECT COUNT(*) FROM listings WHERE needs_review = 1").fetchone()
print("Needs review: %s" % r[0])

print("\n=== PROPERTIES TABLE IMAGE STATS ===")
r = c.execute("""SELECT COUNT(*) as total,
    SUM(CASE WHEN image_urls IS NOT NULL AND image_urls != '[]' THEN 1 ELSE 0 END) as wi
FROM properties""").fetchone()
print("Properties total: %s, with images: %s" % (r[0], r[1]))

print("\n=== LOW CONFIDENCE NON-SPAM SAMPLES (potential non-RE) ===")
for row in c.execute("""SELECT l.confidence, l.property_type, l.is_spam,
    SUBSTR(r.raw_text, 1, 150) as txt
FROM listings l JOIN raw_posts r ON l.post_id = r.post_id
WHERE l.confidence < 0.3 AND l.is_spam = 0
ORDER BY l.confidence ASC LIMIT 15"""):
    print("  conf=%.2f spam=%s type=%s | %s" % (row[0] or 0, row[2], row[1], row[3]))

print("\n=== SPAM FLAGGED SAMPLES ===")
for row in c.execute("""SELECT l.confidence, l.property_type, l.is_spam,
    SUBSTR(r.raw_text, 1, 150) as txt
FROM listings l JOIN raw_posts r ON l.post_id = r.post_id
WHERE l.is_spam = 1 LIMIT 10"""):
    print("  conf=%.2f type=%s | %s" % (row[0] or 0, row[1], row[3]))

print("\n=== MARKETPLACE IMAGE SOURCES ===")
domains = {}
for row in c.execute("SELECT image_urls FROM raw_posts WHERE image_urls IS NOT NULL AND image_urls != '[]' LIMIT 500"):
    try:
        urls = json.loads(row[0])
        for u in urls[:1]:
            if "scontent" in u:
                d = "scontent (FB CDN)"
            elif "fbcdn" in u:
                d = "fbcdn"
            elif "external" in u:
                d = "external (FB proxy)"
            else:
                parts = u.split("/")
                d = parts[2] if len(parts) > 2 else "unknown"
            domains[d] = domains.get(d, 0) + 1
            break
    except:
        pass
for d, cnt in sorted(domains.items(), key=lambda x: -x[1]):
    print("  %s: %d" % (d, cnt))

print("\n=== LISTINGS WITHOUT PRICE, TYPE, OR BEDROOMS (would be hidden by is_listing) ===")
r = c.execute("""SELECT COUNT(*) FROM listings
WHERE price_usd IS NULL AND property_type IS NULL AND bedrooms IS NULL""").fetchone()
print("Hidden posts (no price/type/beds): %s" % r[0])

print("\n=== AGENTS TABLE COLUMNS ===")
for col in c.execute("PRAGMA table_info(agents)"):
    print("  %s (%s)" % (col[1], col[2]))

print("\n=== PROPERTIES TABLE COLUMNS ===")
for col in c.execute("PRAGMA table_info(properties)"):
    print("  %s (%s)" % (col[1], col[2]))

conn.close()
