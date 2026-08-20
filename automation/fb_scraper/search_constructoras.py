"""Search scraped FB posts for constructora/developer mentions."""
import sqlite3
import json

DB = "/opt/data/fb_listings.db"
c = sqlite3.connect(DB)

keywords = [
    "constructora", "constructor", "proyecto", "pre-venta", "preventa",
    "en construccion", "under construction", "new development", "nuevo proyecto",
    "Cana Rock", "Vista Cana", "Cap Cana", "Downtown Punta Cana",
    "entrega", "planos", "torre", "residencial", "condominio",
]

where = " OR ".join(["raw_text LIKE '%" + kw + "%'" for kw in keywords])
sql = "SELECT post_id, author_name, raw_text, group_name FROM raw_posts WHERE " + where + " LIMIT 40"
rows = c.execute(sql).fetchall()
print("Found %d posts with constructora keywords:" % len(rows))
print()
for r in rows:
    text = (r[2] or "")[:250].replace("\n", " ")
    print("  Author: %s" % (r[1] or "?"))
    print("  Group: %s" % r[3])
    print("  Text: %s..." % text)
    print()

print("\n=== TOP 20 AGENTS ===")
rows2 = c.execute(
    "SELECT name, phones, whatsapp, fb_profile_url, total_listings FROM agents ORDER BY total_listings DESC LIMIT 20"
).fetchall()
for r in rows2:
    phones = r[1] or ""
    wa = r[2] or ""
    print("  %s | listings: %s | phones: %s | wa: %s | fb: %s" % (r[0] or "?", r[4], phones, wa, r[3] or ""))
