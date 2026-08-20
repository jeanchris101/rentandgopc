import sqlite3, json

conn = sqlite3.connect("/opt/data/fb_listings.db")
c = conn.cursor()
results = {}

# 1. solar/terreno classified as condo
c.execute(
    "SELECT COUNT(*) FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "WHERE l.property_type='condo' "
    "AND (LOWER(r.raw_text) LIKE '% solar %' OR LOWER(r.raw_text) LIKE '% terreno %' "
    "OR LOWER(r.raw_text) LIKE '% solares %' OR LOWER(r.raw_text) LIKE '%terreno %' "
    "OR LOWER(r.raw_text) LIKE '%solar %') "
    "AND LOWER(r.raw_text) NOT LIKE '%panel solar%' "
    "AND LOWER(r.raw_text) NOT LIKE '%energia solar%' "
    "AND LOWER(r.raw_text) NOT LIKE '%solar panel%'"
)
results["solar_as_condo"] = c.fetchone()[0]

# 2. All solar/terreno not classified as land
c.execute(
    "SELECT l.property_type, COUNT(*) FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "WHERE (LOWER(r.raw_text) LIKE '% solar %' OR LOWER(r.raw_text) LIKE '% terreno %' "
    "OR LOWER(r.raw_text) LIKE '% solares %' OR LOWER(r.raw_text) LIKE '%terreno %') "
    "AND LOWER(r.raw_text) NOT LIKE '%panel solar%' "
    "AND LOWER(r.raw_text) NOT LIKE '%energia solar%' "
    "AND LOWER(r.raw_text) NOT LIKE '%solar panel%' "
    "AND l.property_type != 'land' AND l.property_type IS NOT NULL "
    "GROUP BY l.property_type"
)
results["solar_not_land"] = c.fetchall()

# 3. casa posts not villa
c.execute(
    "SELECT l.property_type, COUNT(*) FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "WHERE LOWER(r.raw_text) LIKE '% casa %' "
    "AND LOWER(r.raw_text) NOT LIKE '%apartamento%' "
    "AND LOWER(r.raw_text) NOT LIKE '% apto%' "
    "AND l.property_type != 'villa' AND l.property_type IS NOT NULL "
    "GROUP BY l.property_type"
)
results["casa_not_villa"] = c.fetchall()

# 4. penthouse misclassified
c.execute(
    "SELECT l.property_type, COUNT(*) FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "WHERE LOWER(r.raw_text) LIKE '%penthouse%' "
    "AND l.property_type != 'penthouse' AND l.property_type IS NOT NULL "
    "GROUP BY l.property_type"
)
results["penthouse_wrong"] = c.fetchall()

# 5. commercial misclassified
c.execute(
    "SELECT l.property_type, COUNT(*) FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
    "WHERE (LOWER(r.raw_text) LIKE '%local comercial%' OR LOWER(r.raw_text) LIKE '%oficina%') "
    "AND l.property_type != 'commercial' AND l.property_type IS NOT NULL "
    "GROUP BY l.property_type"
)
results["commercial_wrong"] = c.fetchall()

# 6. distribution
c.execute("SELECT property_type, COUNT(*) FROM listings GROUP BY property_type ORDER BY COUNT(*) DESC")
results["distribution"] = c.fetchall()

# 7. total
c.execute("SELECT COUNT(*) FROM listings")
results["total"] = c.fetchone()[0]

print(json.dumps(results, indent=2))
conn.close()
