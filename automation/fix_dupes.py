import sqlite3
import re
import hashlib
from collections import defaultdict

conn = sqlite3.connect("/opt/data/fb_listings.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Load all non-duplicate, non-spam listings with raw_text
c.execute("""
    SELECT l.id, l.post_id, l.price_usd, l.bedrooms, l.bathrooms, l.sqm,
           l.neighborhood, l.community, l.property_type, l.listing_type,
           l.confidence, l.agent_id, l.parsed_at, l.contact_phone, l.contact_whatsapp,
           l.is_duplicate,
           r.raw_text, r.local_images, r.author_name,
           a.name as agent_name
    FROM listings l
    LEFT JOIN raw_posts r ON l.post_id = r.post_id
    LEFT JOIN agents a ON l.agent_id = a.id
    WHERE (l.is_duplicate = 0 OR l.is_duplicate IS NULL)
    AND (l.is_spam = 0 OR l.is_spam IS NULL)
""")
all_listings = [dict(row) for row in c.fetchall()]
print(f"Starting with {len(all_listings)} unique non-spam listings")

# Score a listing for canonical selection - Higher = better
def score_listing(l):
    s = 0
    if l.get('local_images') and l['local_images'] not in ('', '[]', None):
        s += 100
    if l.get('price_usd') and l['price_usd'] > 0:
        s += 50
    s += (l.get('confidence') or 0) * 10
    agent = l.get('agent_name') or ''
    if agent and agent != 'Seller details':
        s += 20
    if l.get('parsed_at'):
        s += 5
    for field in ['bedrooms', 'bathrooms', 'sqm', 'neighborhood', 'community', 'property_type']:
        if l.get(field):
            s += 3
    return s

total_marked = 0
already_marked = set()

def mark_dupes(group, reason):
    global total_marked
    remaining = [l for l in group if l['id'] not in already_marked]
    if len(remaining) <= 1:
        return 0
    remaining.sort(key=score_listing, reverse=True)
    canonical = remaining[0]
    marked = 0
    for l in remaining[1:]:
        c.execute("UPDATE listings SET is_duplicate=1, duplicate_of=? WHERE id=?",
                  (str(canonical['id']), l['id']))
        already_marked.add(l['id'])
        marked += 1
    total_marked += marked
    return marked

# PASS 1: Exact raw_text match
print("\n=== PASS 1: Exact raw_text duplicates ===")
text_groups = defaultdict(list)
for l in all_listings:
    text = l.get('raw_text') or ''
    if len(text) < 20:
        continue
    text_groups[text].append(l)

pass1_count = 0
for text, group in text_groups.items():
    if len(group) > 1:
        pass1_count += mark_dupes(group, "exact_text")
print(f"  Marked: {pass1_count}")

# PASS 2: First 200 chars hash
print("\n=== PASS 2: Text hash (first 200 chars normalized) ===")
hash_groups = defaultdict(list)
for l in all_listings:
    if l['id'] in already_marked:
        continue
    text = l.get('raw_text') or ''
    if len(text) < 20:
        continue
    normalized = re.sub(r'\s+', ' ', text.strip().lower())[:200]
    h = hashlib.md5(normalized.encode()).hexdigest()
    hash_groups[h].append(l)

pass2_count = 0
for h, group in hash_groups.items():
    if len(group) > 1:
        pass2_count += mark_dupes(group, "text_hash_200")
print(f"  Marked: {pass2_count}")

# PASS 3: Same agent, text similarity (first 100 chars)
print("\n=== PASS 3: Same agent, text similarity (first 100 chars) ===")
agent_groups = defaultdict(list)
for l in all_listings:
    if l['id'] in already_marked:
        continue
    agent = l.get('agent_name') or 'Unknown'
    agent_groups[agent].append(l)

pass3_count = 0
for agent, listings in agent_groups.items():
    if len(listings) < 2:
        continue
    sub_hash = defaultdict(list)
    for l in listings:
        text = l.get('raw_text') or ''
        if len(text) < 15:
            continue
        normalized = re.sub(r'\s+', ' ', text.strip().lower())[:100]
        h = hashlib.md5(normalized.encode()).hexdigest()
        sub_hash[h].append(l)
    for h, group in sub_hash.items():
        if len(group) > 1:
            pass3_count += mark_dupes(group, "agent_text_100")
print(f"  Marked: {pass3_count}")

# PASS 4: "Seller details" cross-agent dedup
print("\n=== PASS 4: Seller details cross-agent dedup ===")
seller_listings = [l for l in all_listings if l['id'] not in already_marked
                   and (l.get('agent_name') or '') == 'Seller details']
other_listings = [l for l in all_listings if l['id'] not in already_marked
                  and (l.get('agent_name') or '') != 'Seller details']

other_hash_index = defaultdict(list)
for l in other_listings:
    text = l.get('raw_text') or ''
    if len(text) < 20:
        continue
    for n in [100, 150]:
        normalized = re.sub(r'\s+', ' ', text.strip().lower())[:n]
        h = hashlib.md5(normalized.encode()).hexdigest()
        other_hash_index[(n, h)].append(l)

pass4_count = 0
for sl in seller_listings:
    text = sl.get('raw_text') or ''
    if len(text) < 20:
        continue
    for n in [100, 150]:
        normalized = re.sub(r'\s+', ' ', text.strip().lower())[:n]
        h = hashlib.md5(normalized.encode()).hexdigest()
        matches = other_hash_index.get((n, h), [])
        if matches:
            best_match = max(matches, key=score_listing)
            if sl['id'] not in already_marked:
                c.execute("UPDATE listings SET is_duplicate=1, duplicate_of=? WHERE id=?",
                          (str(best_match['id']), sl['id']))
                already_marked.add(sl['id'])
                pass4_count += 1
                total_marked += 1
            break
print(f"  Marked: {pass4_count}")

# PASS 5: Same sqm + bedrooms + neighborhood
print("\n=== PASS 5: Same sqm+bedrooms+neighborhood ===")
prop_groups = defaultdict(list)
for l in all_listings:
    if l['id'] in already_marked:
        continue
    sqm = l.get('sqm')
    beds = l.get('bedrooms')
    hood = (l.get('neighborhood') or '').strip().lower()
    if sqm and beds and hood and sqm > 0 and beds > 0:
        key = (sqm, beds, hood)
        prop_groups[key].append(l)

pass5_count = 0
for key, group in prop_groups.items():
    if len(group) > 1:
        prices = [l['price_usd'] for l in group if l.get('price_usd') and l['price_usd'] > 0]
        if len(prices) >= 2:
            min_p, max_p = min(prices), max(prices)
            if max_p > min_p * 1.5:
                continue
        pass5_count += mark_dupes(group, "property_match")
print(f"  Marked: {pass5_count}")

# PASS 6: Same phone + same zone
print("\n=== PASS 6: Same phone + same zone ===")
def extract_phones(l):
    phones = set()
    for field in ['contact_phone', 'contact_whatsapp']:
        v = l.get(field) or ''
        for m in re.findall(r'[\d]+', v):
            clean = re.sub(r'[^\d]', '', m)
            if len(clean) >= 7:
                phones.add(clean[-10:])
    text = l.get('raw_text') or ''
    digits_only = re.sub(r'[^\d]', '', text)
    for m in re.finditer(r'(?:809|829|849)\d{7}', digits_only):
        phones.add(m.group()[-10:])
    return phones

phone_zone_groups = defaultdict(list)
for l in all_listings:
    if l['id'] in already_marked:
        continue
    phones = extract_phones(l)
    hood = (l.get('neighborhood') or '').strip().lower()
    if not hood:
        hood = 'unknown'
    for p in phones:
        phone_zone_groups[(p, hood)].append(l)

pass6_count = 0
for key, group in phone_zone_groups.items():
    if len(group) > 1:
        pass6_count += mark_dupes(group, "phone_zone")
print(f"  Marked: {pass6_count}")

# PASS 7: Short marketplace text dedup
print("\n=== PASS 7: Short marketplace text dedup ===")
short_groups = defaultdict(list)
for l in all_listings:
    if l['id'] in already_marked:
        continue
    text = l.get('raw_text') or ''
    if len(text) < 10:
        continue
    normalized = re.sub(r'\s+', ' ', text.strip().lower())
    if len(normalized) < 80:
        short_groups[normalized].append(l)

pass7_count = 0
for text, group in short_groups.items():
    if len(group) > 1:
        pass7_count += mark_dupes(group, "short_text_exact")
print(f"  Marked: {pass7_count}")

# Commit
conn.commit()

# Final counts
c.execute("SELECT COUNT(*) FROM listings WHERE (is_duplicate=0 OR is_duplicate IS NULL) AND (is_spam=0 OR is_spam IS NULL)")
final_unique = c.fetchone()[0]
print(f"\n{'='*50}")
print(f"Total newly marked as duplicate: {total_marked}")
print(f"Final unique non-spam listings: {final_unique}")

# Remaining top agents
print("\n=== REMAINING TOP AGENTS ===")
c.execute("""
    SELECT a.name, COUNT(*) as cnt
    FROM listings l
    LEFT JOIN agents a ON l.agent_id = a.id
    WHERE (l.is_duplicate=0 OR l.is_duplicate IS NULL) AND (l.is_spam=0 OR l.is_spam IS NULL)
    GROUP BY a.name ORDER BY cnt DESC LIMIT 20
""")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}")

# Seller details remaining
c.execute("""
    SELECT COUNT(*) FROM listings l
    LEFT JOIN agents a ON l.agent_id = a.id
    WHERE (l.is_duplicate=0 OR l.is_duplicate IS NULL) AND (l.is_spam=0 OR l.is_spam IS NULL)
    AND a.name = 'Seller details'
""")
print(f"\nSeller details remaining: {c.fetchone()[0]}")

# Raul Carrillo remaining
c.execute("""
    SELECT COUNT(*) FROM listings l
    LEFT JOIN agents a ON l.agent_id = a.id
    WHERE (l.is_duplicate=0 OR l.is_duplicate IS NULL) AND (l.is_spam=0 OR l.is_spam IS NULL)
    AND a.name LIKE '%Raul%Carrillo%'
""")
print(f"Raul Carrillo remaining: {c.fetchone()[0]}")

conn.close()
