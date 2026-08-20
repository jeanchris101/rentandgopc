import sqlite3
conn = sqlite3.connect("/opt/data/fb_listings.db")
c = conn.cursor()

print("=== TRUE CAR/VEHICLE LISTINGS ===")
car_words = ["carro ", "vendo carro", "vehiculo", "camioneta", "motocicleta"]
for kw in car_words:
    r = c.execute(
        "SELECT COUNT(*) FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
        "WHERE (l.price_usd IS NOT NULL OR l.property_type IS NOT NULL OR l.bedrooms IS NOT NULL) "
        "AND l.is_spam = 0 AND l.confidence >= 0.3 "
        "AND LOWER(r.raw_text) LIKE ?", ("%" + kw + "%",)
    ).fetchone()
    if r[0] > 0:
        print("  '%s': %d" % (kw, r[0]))

print("")
print("=== MARKETPLACE NO-TYPE CHEAP ITEMS (probable non-RE) ===")
for row in c.execute(
    "SELECT l.price_usd, l.confidence, SUBSTR(r.raw_text, 1, 100) "
    "FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "WHERE r.group_name = 'Facebook Marketplace' "
    "AND l.property_type IS NULL "
    "AND l.is_spam = 0 AND l.confidence >= 0.3 "
    "AND l.price_usd IS NOT NULL AND l.price_usd < 500 "
    "ORDER BY l.price_usd ASC LIMIT 20"
):
    print("  $%.0f conf=%.2f | %s" % (row[0], row[1], row[2]))

print("")
print("=== MARKETPLACE TYPE=NONE COUNT (visible) ===")
r = c.execute(
    "SELECT COUNT(*) FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "WHERE r.group_name = 'Facebook Marketplace' "
    "AND l.property_type IS NULL "
    "AND l.is_spam = 0 AND l.confidence >= 0.3 "
    "AND l.price_usd IS NOT NULL"
).fetchone()
print("Marketplace visible, no type, has price: %d" % r[0])

print("")
print("=== ALL VISIBLE LISTINGS BY SOURCE GROUP (top 10) ===")
for row in c.execute(
    "SELECT r.group_name, COUNT(*) as cnt "
    "FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "WHERE (l.price_usd IS NOT NULL OR l.property_type IS NOT NULL OR l.bedrooms IS NOT NULL) "
    "AND l.is_spam = 0 AND l.confidence >= 0.3 "
    "GROUP BY r.group_name ORDER BY cnt DESC LIMIT 10"
):
    print("  %s: %d" % (row[0], row[1]))

print("")
print("=== POSTS WITH EXPIRED/BROKEN IMAGES (captured > 14 days ago) ===")
r = c.execute(
    "SELECT COUNT(*) FROM raw_posts "
    "WHERE image_urls IS NOT NULL AND image_urls != '[]' "
    "AND captured_at < datetime('now', '-14 days')"
).fetchone()
print("Posts older than 14 days with images: %d" % r[0])

r = c.execute(
    "SELECT COUNT(*) FROM raw_posts "
    "WHERE image_urls IS NOT NULL AND image_urls != '[]' "
    "AND captured_at >= datetime('now', '-14 days')"
).fetchone()
print("Posts within 14 days with images: %d" % r[0])

conn.close()
