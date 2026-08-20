import sqlite3, json
conn = sqlite3.connect("/opt/data/fb_listings.db")
conn.row_factory = sqlite3.Row

# How many JMB listings?
rows = conn.execute(
    "SELECT l.post_id, l.price_usd, l.neighborhood, l.property_type, l.is_duplicate, "
    "SUBSTR(r.raw_text, 1, 100) as text_preview "
    "FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "JOIN agents a ON l.agent_id = a.id "
    "WHERE LOWER(a.name) LIKE '%juan manuel bosch%' "
    "AND l.is_spam = 0 "
    "ORDER BY l.is_duplicate, r.captured_at DESC"
).fetchall()

dupes = sum(1 for r in rows if r["is_duplicate"])
non_dupes = sum(1 for r in rows if not r["is_duplicate"])
print("JMB: %d unique, %d marked dup, %d total" % (non_dupes, dupes, len(rows)))

# Check unique prices among non-dupes
prices = set()
for r in rows:
    if not r["is_duplicate"]:
        prices.add(r["price_usd"])
print("Unique prices in non-dup:", prices)

# Show some text samples
print("\nSample non-dup texts:")
for r in rows[:5]:
    if not r["is_duplicate"]:
        print("  %s | $%s | %s | %s" % (r["post_id"], r["price_usd"], r["neighborhood"], r["text_preview"][:80]))
