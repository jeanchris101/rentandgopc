import sqlite3
import re
import hashlib
from collections import defaultdict

conn = sqlite3.connect("/opt/data/fb_listings.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Load remaining non-duplicate, non-spam listings
c.execute("""
    SELECT l.id, l.post_id, l.price_usd, l.bedrooms, l.bathrooms, l.sqm,
           l.neighborhood, l.community, l.property_type, l.listing_type,
           l.confidence, l.agent_id, l.parsed_at, l.contact_phone, l.contact_whatsapp,
           r.raw_text, r.local_images, r.author_name,
           a.name as agent_name
    FROM listings l
    LEFT JOIN raw_posts r ON l.post_id = r.post_id
    LEFT JOIN agents a ON l.agent_id = a.id
    WHERE (l.is_duplicate = 0 OR l.is_duplicate IS NULL)
    AND (l.is_spam = 0 OR l.is_spam IS NULL)
""")
all_listings = [dict(row) for row in c.fetchall()]
print(f"Starting with {len(all_listings)} listings")

# Examine Seller details listings
seller_listings = [l for l in all_listings if (l.get('agent_name') or '') == 'Seller details']
print(f"\n=== SELLER DETAILS: {len(seller_listings)} listings ===")
for sl in seller_listings[:10]:
    text = (sl.get('raw_text') or '')[:120].replace('\n', ' ')
    print(f"  id={sl['id']} beds={sl['bedrooms']} sqm={sl['sqm']} hood={sl['neighborhood']} price={sl['price_usd']}")
    print(f"    text: {text}")

# Check "Seller details" for internal dupes using broader text similarity
# Strip all non-alphanumeric, take first 80 chars
print("\n=== SELLER DETAILS: internal dedup (stripped alpha 80 chars) ===")
seller_hash = defaultdict(list)
for sl in seller_listings:
    text = sl.get('raw_text') or ''
    if len(text) < 10:
        continue
    # Very aggressive normalization
    stripped = re.sub(r'[^a-z0-9]', '', text.lower())[:80]
    if len(stripped) < 10:
        continue
    seller_hash[stripped].append(sl)

dupe_count = 0
for h, group in seller_hash.items():
    if len(group) > 1:
        print(f"  Group of {len(group)}: {h[:50]}...")
        # Keep the one with best data
        group.sort(key=lambda l: (
            1 if l.get('price_usd') else 0,
            1 if l.get('bedrooms') else 0,
            l.get('confidence') or 0
        ), reverse=True)
        canonical = group[0]
        for l in group[1:]:
            c.execute("UPDATE listings SET is_duplicate=1, duplicate_of=? WHERE id=?",
                      (str(canonical['id']), l['id']))
            dupe_count += 1
print(f"Seller details internal dupes marked: {dupe_count}")

# Now check Raul Carrillo - look at his remaining listings
raul = [l for l in all_listings if l.get('agent_name') and 'raul' in l['agent_name'].lower()]
print(f"\n=== RAUL CARRILLO: {len(raul)} listings ===")
raul_hash = defaultdict(list)
for rl in raul:
    text = rl.get('raw_text') or ''
    if len(text) < 10:
        continue
    stripped = re.sub(r'[^a-z0-9]', '', text.lower())[:80]
    if len(stripped) < 10:
        continue
    raul_hash[stripped].append(rl)
    print(f"  id={rl['id']} beds={rl['bedrooms']} sqm={rl['sqm']} price={rl['price_usd']} conf={rl['confidence']}")
    print(f"    hash: {stripped[:60]}")

raul_dupes = 0
for h, group in raul_hash.items():
    if len(group) > 1:
        group.sort(key=lambda l: (
            1 if l.get('price_usd') else 0,
            l.get('confidence') or 0
        ), reverse=True)
        canonical = group[0]
        for l in group[1:]:
            c.execute("UPDATE listings SET is_duplicate=1, duplicate_of=? WHERE id=?",
                      (str(canonical['id']), l['id']))
            raul_dupes += 1
print(f"Raul Carrillo dupes marked: {raul_dupes}")

# PASS: Cross-agent dedup using aggressive text normalization (alpha-only, 60 chars)
print("\n=== CROSS-AGENT: aggressive alpha-60 dedup ===")
alpha_groups = defaultdict(list)
for l in all_listings:
    text = l.get('raw_text') or ''
    if len(text) < 30:
        continue
    stripped = re.sub(r'[^a-z0-9]', '', text.lower())[:60]
    if len(stripped) < 20:
        continue
    alpha_groups[stripped].append(l)

cross_count = 0
already_done = set()
for h, group in alpha_groups.items():
    if len(group) <= 1:
        continue
    # Filter out already-marked
    remaining = [l for l in group if l['id'] not in already_done]
    if len(remaining) <= 1:
        continue
    # Score and pick canonical
    remaining.sort(key=lambda l: (
        100 if l.get('local_images') and l['local_images'] not in ('', '[]', None) else 0,
        50 if l.get('price_usd') and l['price_usd'] > 0 else 0,
        20 if l.get('agent_name') and l['agent_name'] != 'Seller details' else 0,
        (l.get('confidence') or 0) * 10
    ), reverse=True)
    canonical = remaining[0]
    for l in remaining[1:]:
        c.execute("UPDATE listings SET is_duplicate=1, duplicate_of=? WHERE id=?",
                  (str(canonical['id']), l['id']))
        already_done.add(l['id'])
        cross_count += 1
print(f"Cross-agent alpha-60 dupes marked: {cross_count}")

conn.commit()

# Final count
c.execute("SELECT COUNT(*) FROM listings WHERE (is_duplicate=0 OR is_duplicate IS NULL) AND (is_spam=0 OR is_spam IS NULL)")
final = c.fetchone()[0]
print(f"\nFinal unique non-spam listings: {final}")

# Remaining key agents
c.execute("""
    SELECT a.name, COUNT(*) as cnt
    FROM listings l LEFT JOIN agents a ON l.agent_id = a.id
    WHERE (l.is_duplicate=0 OR l.is_duplicate IS NULL) AND (l.is_spam=0 OR l.is_spam IS NULL)
    GROUP BY a.name ORDER BY cnt DESC LIMIT 15
""")
print("\n=== REMAINING TOP AGENTS ===")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}")

c.execute("""SELECT COUNT(*) FROM listings l LEFT JOIN agents a ON l.agent_id=a.id
    WHERE (l.is_duplicate=0 OR l.is_duplicate IS NULL) AND (l.is_spam=0 OR l.is_spam IS NULL) AND a.name='Seller details'""")
print(f"\nSeller details remaining: {c.fetchone()[0]}")

c.execute("""SELECT COUNT(*) FROM listings l LEFT JOIN agents a ON l.agent_id=a.id
    WHERE (l.is_duplicate=0 OR l.is_duplicate IS NULL) AND (l.is_spam=0 OR l.is_spam IS NULL) AND a.name LIKE '%Raul%'""")
print(f"Raul Carrillo remaining: {c.fetchone()[0]}")

conn.close()
