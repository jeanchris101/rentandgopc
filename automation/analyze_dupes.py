
import sqlite3
import re
import hashlib
from collections import defaultdict

conn = sqlite3.connect('/opt/data/fb_listings.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Basic counts
c.execute('SELECT COUNT(*) FROM listings WHERE is_duplicate=0')
print('Unique:', c.fetchone()[0])
c.execute('SELECT COUNT(*) FROM listings')
print('Total:', c.fetchone()[0])
c.execute('SELECT COUNT(*) FROM listings WHERE is_duplicate=1')
print('Already dupes:', c.fetchone()[0])

# Schema
c.execute('PRAGMA table_info(listings)')
cols = [row[1] for row in c.fetchall()]
print('Columns:', cols)

# Agent breakdown (top 20)
print()
print('=== TOP AGENTS (non-dupe) ===')
c.execute("""SELECT agent_name, COUNT(*) as cnt FROM listings WHERE is_duplicate=0 
             GROUP BY agent_name ORDER BY cnt DESC LIMIT 20""")
for row in c.fetchall():
    print(f'  {row[0]}: {row[1]}')

# Seller details count
print()
c.execute("""SELECT COUNT(*) FROM listings WHERE is_duplicate=0 AND agent_name='Seller details'""")
print('Seller details unique:', c.fetchone()[0])

# Raul Carrillo count
c.execute("""SELECT COUNT(*) FROM listings WHERE is_duplicate=0 AND agent_name LIKE '%Raul%Carrillo%'""")
print('Raul Carrillo unique:', c.fetchone()[0])

# Pattern 1: Exact raw_text duplicates
print()
print('=== PATTERN 1: EXACT RAW_TEXT DUPES ===')
c.execute("""SELECT raw_text, COUNT(*) as cnt FROM listings WHERE is_duplicate=0 AND raw_text IS NOT NULL AND raw_text != ''
             GROUP BY raw_text HAVING cnt > 1 ORDER BY cnt DESC LIMIT 10""")
rows = c.fetchall()
print(f'Groups with exact same raw_text: showing top 10')
for row in rows:
    text_preview = row[0][:80].replace(chr(10), ' ')
    print(f'  count={row[1]}: {text_preview}...')

# Count total exact dupes
c.execute("""SELECT SUM(cnt-1) FROM (SELECT raw_text, COUNT(*) as cnt FROM listings WHERE is_duplicate=0 AND raw_text IS NOT NULL AND raw_text != '' GROUP BY raw_text HAVING cnt > 1)""")
print(f'Total exact raw_text dupes to remove: {c.fetchone()[0]}')

# Pattern 2: Hash of first 200 chars normalized
print()
print('=== PATTERN 2: FIRST-200-CHAR HASH DUPES ===')
c.execute("""SELECT id, raw_text, agent_name, confidence, price, local_images, created_at FROM listings WHERE is_duplicate=0 AND raw_text IS NOT NULL AND raw_text != ''""")
all_listings = c.fetchall()
hash_groups = defaultdict(list)
for row in all_listings:
    text = row[1]
    normalized = re.sub(r'\s+', ' ', text.strip().lower())[:200]
    h = hashlib.md5(normalized.encode()).hexdigest()
    hash_groups[h].append(dict(zip(['id','raw_text','agent_name','confidence','price','local_images','created_at'], row)))

dupe_count = 0
for h, group in sorted(hash_groups.items(), key=lambda x: -len(x[1])):
    if len(group) > 1:
        dupe_count += len(group) - 1
        if len(group) >= 3:
            print(f'  {len(group)} listings, agents: {set(g["agent_name"] for g in group)}')
            print(f'    text: {group[0]["raw_text"][:80]}...')
print(f'Total first-200-char hash dupes to remove: {dupe_count}')

# Pattern 3: Phone number extraction
print()
print('=== PATTERN 3: PHONE NUMBER DUPES ===')
phone_groups = defaultdict(list)
for row in all_listings:
    text = row[1]
    phones = re.findall(r'(?:\+?1[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}', text)
    phones += re.findall(r'\d{3}[-.]\d{4}', text)  # 7-digit
    phones += re.findall(r'809[-.]?\d{3}[-.]?\d{4}', text)  # DR phones
    phones += re.findall(r'849[-.]?\d{3}[-.]?\d{4}', text)
    phones += re.findall(r'829[-.]?\d{3}[-.]?\d{4}', text)
    d = dict(zip(['id','raw_text','agent_name','confidence','price','local_images','created_at'], row))
    for p in set(phones):
        clean = re.sub(r'[^0-9]', '', p)
        if len(clean) >= 7:
            phone_groups[clean].append(d)

phone_dupe_count = 0
for phone, group in sorted(phone_groups.items(), key=lambda x: -len(x[1])):
    if len(group) > 1:
        phone_dupe_count += len(group) - 1
        if len(group) >= 4:
            print(f'  Phone {phone}: {len(group)} listings, agents: {set(g["agent_name"] for g in group)}')
print(f'Total phone-based dupes (potential): {phone_dupe_count}')

# Pattern 4: Same sqm + bedrooms + zone
print()
print('=== PATTERN 4: SAME SQM+BED+ZONE ===')
c.execute("""SELECT id, sqm, bedrooms, zone, agent_name, confidence, price, local_images, created_at, raw_text
             FROM listings WHERE is_duplicate=0 AND sqm IS NOT NULL AND bedrooms IS NOT NULL AND zone IS NOT NULL
             AND sqm > 0 AND bedrooms > 0 AND zone != ''""")
prop_groups = defaultdict(list)
for row in c.fetchall():
    key = (row[1], row[2], row[3].strip().lower())
    prop_groups[key].append(dict(zip(['id','sqm','bedrooms','zone','agent_name','confidence','price','local_images','created_at','raw_text'], row)))

prop_dupe_count = 0
for key, group in sorted(prop_groups.items(), key=lambda x: -len(x[1])):
    if len(group) > 1:
        # Only count as dupes if different agents (same property listed by multiple agents)
        agents = set(g['agent_name'] for g in group)
        if len(agents) > 1 or len(group) > 2:
            prop_dupe_count += len(group) - 1
            if len(group) >= 3:
                print(f'  sqm={key[0]}, beds={key[1]}, zone={key[2]}: {len(group)} listings, agents: {agents}')
print(f'Total sqm+bed+zone dupes (potential): {prop_dupe_count}')

conn.close()
