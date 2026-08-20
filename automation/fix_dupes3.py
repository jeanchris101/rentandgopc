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

total_marked = 0
already_marked = set()

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
    for field in ['bedrooms', 'bathrooms', 'sqm', 'neighborhood', 'community', 'property_type']:
        if l.get(field):
            s += 3
    return s

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

# PASS A: Same price + bedrooms + neighborhood + property_type (very specific combo)
print("\n=== PASS A: price+beds+hood+type combo ===")
combo_groups = defaultdict(list)
for l in all_listings:
    price = l.get('price_usd')
    beds = l.get('bedrooms')
    hood = (l.get('neighborhood') or '').strip().lower()
    ptype = (l.get('property_type') or '').strip().lower()
    if price and beds and hood and ptype and price > 0 and beds > 0 and hood and ptype:
        key = (price, beds, hood, ptype)
        combo_groups[key].append(l)

pass_a = 0
for key, group in combo_groups.items():
    if len(group) > 1:
        pass_a += mark_dupes(group, "price_beds_hood_type")
print(f"  Marked: {pass_a}")

# PASS B: Same price + bedrooms + listing_type (sale/rent) - broader
print("\n=== PASS B: price+beds+listing_type (within same zone) ===")
combo2_groups = defaultdict(list)
for l in all_listings:
    if l['id'] in already_marked:
        continue
    price = l.get('price_usd')
    beds = l.get('bedrooms')
    hood = (l.get('neighborhood') or '').strip().lower()
    ltype = (l.get('listing_type') or '').strip().lower()
    sqm = l.get('sqm')
    if price and beds and hood and price > 0 and beds > 0 and hood:
        # Include sqm if available for tighter matching
        key = (price, beds, hood, ltype, sqm)
        combo2_groups[key].append(l)

pass_b = 0
for key, group in combo2_groups.items():
    if len(group) > 1:
        pass_b += mark_dupes(group, "price_beds_hood_ltype_sqm")
print(f"  Marked: {pass_b}")

# PASS C: Marketplace listings (None agent) - many are FB marketplace posts
# with very similar patterns like "DOP1,080,000 Santo Domingo..."
print("\n=== PASS C: None-agent marketplace dedup (first 50 alpha chars) ===")
none_listings = [l for l in all_listings if l['id'] not in already_marked and l.get('agent_name') is None]
print(f"  None-agent listings: {len(none_listings)}")

none_hash = defaultdict(list)
for l in none_listings:
    text = l.get('raw_text') or ''
    if len(text) < 15:
        continue
    stripped = re.sub(r'[^a-z0-9]', '', text.lower())[:50]
    if len(stripped) < 15:
        continue
    none_hash[stripped].append(l)

pass_c = 0
for h, group in none_hash.items():
    if len(group) > 1:
        pass_c += mark_dupes(group, "none_agent_text50")
print(f"  Marked: {pass_c}")

# PASS D: Raul Carrillo - check for "See more" truncated versions
# e.g., "Villa en Alquiler – Vista Cana V… See more" vs full text
print("\n=== PASS D: See-more truncation dedup (all agents) ===")
see_more = defaultdict(list)
for l in all_listings:
    if l['id'] in already_marked:
        continue
    text = l.get('raw_text') or ''
    # Remove "See more", "... See more", etc.
    cleaned = re.sub(r'\.{0,3}\s*See more\s*$', '', text, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'\u2026\s*$', '', cleaned).strip()  # Remove trailing ellipsis
    if len(cleaned) < 20:
        continue
    # Hash the cleaned version
    normalized = re.sub(r'\s+', ' ', cleaned.lower())[:100]
    h = hashlib.md5(normalized.encode()).hexdigest()
    see_more[h].append(l)

pass_d = 0
for h, group in see_more.items():
    if len(group) > 1:
        pass_d += mark_dupes(group, "see_more_dedup")
print(f"  Marked: {pass_d}")

# PASS E: Same contact_phone across any listings
print("\n=== PASS E: Same contact_phone field (exact) ===")
phone_field_groups = defaultdict(list)
for l in all_listings:
    if l['id'] in already_marked:
        continue
    phone = (l.get('contact_phone') or '').strip()
    if phone and len(phone) >= 7:
        clean = re.sub(r'[^\d]', '', phone)
        if len(clean) >= 7:
            phone_field_groups[clean[-10:]].append(l)

pass_e = 0
for phone, group in phone_field_groups.items():
    if len(group) <= 1:
        continue
    # Within same phone, group by beds+price for tighter matching
    sub_groups = defaultdict(list)
    for l in group:
        beds = l.get('bedrooms') or 0
        price_bucket = int((l.get('price_usd') or 0) / 100) * 100  # round to nearest 100
        sub_groups[(beds, price_bucket)].append(l)
    for sk, sg in sub_groups.items():
        if len(sg) > 1:
            pass_e += mark_dupes(sg, "phone_beds_price")
print(f"  Marked: {pass_e}")

conn.commit()

# Final stats
c.execute("SELECT COUNT(*) FROM listings WHERE (is_duplicate=0 OR is_duplicate IS NULL) AND (is_spam=0 OR is_spam IS NULL)")
final = c.fetchone()[0]
print(f"\n{'='*50}")
print(f"Total newly marked this pass: {total_marked}")
print(f"Final unique non-spam listings: {final}")

c.execute("""SELECT a.name, COUNT(*) as cnt FROM listings l LEFT JOIN agents a ON l.agent_id=a.id
    WHERE (l.is_duplicate=0 OR l.is_duplicate IS NULL) AND (l.is_spam=0 OR l.is_spam IS NULL)
    GROUP BY a.name ORDER BY cnt DESC LIMIT 15""")
print("\n=== REMAINING TOP AGENTS ===")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}")

c.execute("""SELECT COUNT(*) FROM listings l LEFT JOIN agents a ON l.agent_id=a.id
    WHERE (l.is_duplicate=0 OR l.is_duplicate IS NULL) AND (l.is_spam=0 OR l.is_spam IS NULL) AND a.name='Seller details'""")
print(f"\nSeller details remaining: {c.fetchone()[0]}")

c.execute("""SELECT COUNT(*) FROM listings l LEFT JOIN agents a ON l.agent_id=a.id
    WHERE (l.is_duplicate=0 OR l.is_duplicate IS NULL) AND (l.is_spam=0 OR l.is_spam IS NULL) AND a.name LIKE '%Raul%'""")
print(f"Raul Carrillo remaining: {c.fetchone()[0]}")

# Total dupes across all passes
c.execute("SELECT COUNT(*) FROM listings WHERE is_duplicate=1")
print(f"\nTotal duplicates in DB: {c.fetchone()[0]}")

conn.close()
