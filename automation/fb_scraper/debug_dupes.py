import sqlite3, json
conn = sqlite3.connect("/opt/data/fb_listings.db")
conn.row_factory = sqlite3.Row

# Marino solar listings
rows = conn.execute(
    "SELECT l.post_id, l.price_usd, l.property_type, l.neighborhood, l.is_duplicate, "
    "SUBSTR(r.raw_text, 1, 120) as txt "
    "FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "JOIN agents a ON l.agent_id = a.id "
    "WHERE LOWER(a.name) LIKE '%marino%' AND l.is_spam = 0 AND l.is_duplicate = 0 "
    "ORDER BY r.captured_at DESC LIMIT 20"
).fetchall()
print("=== Marino non-dup listings ===")
for r in rows:
    print(r["post_id"], "|", r["price_usd"], "|", r["property_type"], "|", r["neighborhood"], "|", str(r["txt"] or "")[:80])

# Stewdy listings
rows = conn.execute(
    "SELECT l.post_id, l.price_usd, l.property_type, l.neighborhood, l.is_duplicate, "
    "SUBSTR(r.raw_text, 1, 120) as txt "
    "FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "JOIN agents a ON l.agent_id = a.id "
    "WHERE LOWER(a.name) LIKE '%stewdy%' AND l.is_spam = 0 AND l.is_duplicate = 0 "
    "ORDER BY r.captured_at DESC LIMIT 20"
).fetchall()
print("")
print("=== Stewdy non-dup listings ===")
for r in rows:
    print(r["post_id"], "|", r["price_usd"], "|", r["property_type"], "|", r["neighborhood"], "|", str(r["txt"] or "")[:80])

# Condos with "solar" in text
solar_condos = conn.execute(
    "SELECT COUNT(*) FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "WHERE LOWER(l.property_type) = 'condo' AND LOWER(r.raw_text) LIKE '%solar%' "
    "AND l.is_spam = 0 AND l.is_duplicate = 0"
).fetchone()[0]
print("")
print("Condos with solar in text:", solar_condos)

# NULL price same-agent groups
rows = conn.execute(
    "SELECT l.agent_id, l.property_type, COUNT(*) as cnt "
    "FROM listings l "
    "WHERE l.price_usd IS NULL AND l.is_spam = 0 AND l.is_duplicate = 0 "
    "AND l.agent_id IS NOT NULL "
    "GROUP BY l.agent_id, LOWER(COALESCE(l.property_type,'')) "
    "HAVING cnt > 1 ORDER BY cnt DESC LIMIT 10"
).fetchall()
print("")
print("Top NULL-price same-agent groups:")
for r in rows:
    a = conn.execute("SELECT name FROM agents WHERE id=?", (r["agent_id"],)).fetchone()
    name = a["name"] if a else "?"
    print("  %s | type=%s | count=%d" % (name, r["property_type"], r["cnt"]))

# Total NULL-price dupes potential
total_null = conn.execute(
    "SELECT SUM(cnt - 1) FROM ("
    "SELECT COUNT(*) as cnt FROM listings l "
    "WHERE l.price_usd IS NULL AND l.is_spam = 0 AND l.is_duplicate = 0 "
    "AND l.agent_id IS NOT NULL "
    "GROUP BY l.agent_id, LOWER(COALESCE(l.property_type,'')) "
    "HAVING cnt > 1)"
).fetchone()[0]
print("Total NULL-price duplicates to clean:", total_null)
