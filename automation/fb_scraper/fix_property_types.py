"""
Fix misclassified property_type in listings and properties tables.
Rules (applied in priority order):
1. penthouse/PH -> penthouse (already correct, but enforce)
2. solar/terreno/solares/lote/parcela WITHOUT casa/villa/house -> land
3. local comercial / oficina / nave -> commercial
4. casa WITHOUT apartamento/apto -> villa
5. Also update the properties table to match
"""
import sqlite3

conn = sqlite3.connect("/opt/data/fb_listings.db")
c = conn.cursor()

# Backup counts before
c.execute("SELECT property_type, COUNT(*) FROM listings GROUP BY property_type ORDER BY COUNT(*) DESC")
print("=== BEFORE ===")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}")

counts = {}

# --- Fix 1: solar/terreno -> land (only if no casa/villa/house in text) ---
c.execute(
    "UPDATE listings SET property_type = 'land' "
    "WHERE post_id IN ("
    "  SELECT l.post_id FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "  WHERE ("
    "    LOWER(r.raw_text) LIKE '% solar %' OR LOWER(r.raw_text) LIKE '% terreno %' "
    "    OR LOWER(r.raw_text) LIKE '% solares %' OR LOWER(r.raw_text) LIKE '% lote %' "
    "    OR LOWER(r.raw_text) LIKE '% parcela %' OR LOWER(r.raw_text) LIKE '%terreno %' "
    "    OR LOWER(r.raw_text) LIKE '%solar %' OR LOWER(r.raw_text) LIKE '%solares %'"
    "  ) "
    "  AND LOWER(r.raw_text) NOT LIKE '%panel solar%' "
    "  AND LOWER(r.raw_text) NOT LIKE '%energia solar%' "
    "  AND LOWER(r.raw_text) NOT LIKE '%solar panel%' "
    "  AND LOWER(r.raw_text) NOT LIKE '% casa %' "
    "  AND LOWER(r.raw_text) NOT LIKE '%casa %' "
    "  AND LOWER(r.raw_text) NOT LIKE '% villa %' "
    "  AND LOWER(r.raw_text) NOT LIKE '% house %' "
    "  AND l.property_type != 'land'"
    ")"
)
counts["solar_to_land"] = c.rowcount
print(f"Fixed solar/terreno -> land: {c.rowcount}")

# --- Fix 2: local comercial / oficina / nave -> commercial ---
c.execute(
    "UPDATE listings SET property_type = 'commercial' "
    "WHERE post_id IN ("
    "  SELECT l.post_id FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "  WHERE ("
    "    LOWER(r.raw_text) LIKE '%local comercial%' "
    "    OR LOWER(r.raw_text) LIKE '% oficina %' "
    "    OR LOWER(r.raw_text) LIKE '%oficina %' "
    "    OR LOWER(r.raw_text) LIKE '% nave %' "
    "    OR LOWER(r.raw_text) LIKE '%nave industrial%'"
    "  ) "
    "  AND l.property_type != 'commercial'"
    ")"
)
counts["to_commercial"] = c.rowcount
print(f"Fixed -> commercial: {c.rowcount}")

# --- Fix 3: casa -> villa (only if no apartamento/apto, and currently condo/apartment/studio) ---
# Only fix types that are clearly wrong -- condo is the main culprit (residencial matched first)
c.execute(
    "UPDATE listings SET property_type = 'villa' "
    "WHERE post_id IN ("
    "  SELECT l.post_id FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "  WHERE ("
    "    LOWER(r.raw_text) LIKE '% casa %' OR LOWER(r.raw_text) LIKE '%casa %'"
    "  ) "
    "  AND LOWER(r.raw_text) NOT LIKE '%apartamento%' "
    "  AND LOWER(r.raw_text) NOT LIKE '% apto%' "
    "  AND LOWER(r.raw_text) NOT LIKE '%apto.%' "
    "  AND l.property_type IN ('condo', 'apartment', 'studio')"
    ")"
)
counts["casa_to_villa"] = c.rowcount
print(f"Fixed casa -> villa: {c.rowcount}")

conn.commit()

# Now fix the properties table too
c.execute(
    "UPDATE properties SET property_type = ("
    "  SELECT l.property_type FROM listings l WHERE l.property_id = properties.id LIMIT 1"
    ") WHERE id IN ("
    "  SELECT DISTINCT l.property_id FROM listings l WHERE l.property_id IS NOT NULL"
    ")"
)
props_fixed = c.rowcount
print(f"Properties table synced: {props_fixed} rows touched")

conn.commit()

# After counts
c.execute("SELECT property_type, COUNT(*) FROM listings GROUP BY property_type ORDER BY COUNT(*) DESC")
print("\n=== AFTER ===")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}")

total_fixed = sum(counts.values())
print(f"\n=== TOTAL RECLASSIFIED: {total_fixed} listings ===")
for k, v in counts.items():
    print(f"  {k}: {v}")

conn.close()
