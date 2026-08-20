import sqlite3
conn = sqlite3.connect("/opt/data/fb_listings.db")
c = conn.cursor()

q1 = ("SELECT COUNT(*) FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
      "WHERE (LOWER(r.raw_text) LIKE '% solar %' OR LOWER(r.raw_text) LIKE '% terreno %') "
      "AND LOWER(r.raw_text) NOT LIKE '%panel solar%' "
      "AND LOWER(r.raw_text) NOT LIKE '%energia solar%' "
      "AND l.property_type != 'land' AND l.property_type IS NOT NULL")
c.execute(q1)
print("Remaining solar/terreno not land:", c.fetchone()[0], "(expected: casa+terreno combos stay villa)")

q2 = ("SELECT COUNT(*) FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
      "WHERE LOWER(r.raw_text) LIKE '% casa %' "
      "AND LOWER(r.raw_text) NOT LIKE '%apartamento%' "
      "AND l.property_type = 'condo'")
c.execute(q2)
print("Remaining casa as condo:", c.fetchone()[0])

conn.close()
