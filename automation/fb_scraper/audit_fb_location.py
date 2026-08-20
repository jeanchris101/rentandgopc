import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import paramiko

AUDIT_SCRIPT = '''
import sys, io, sqlite3, re, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = "/opt/data/fb_listings.db"

if not os.path.exists(DB_PATH):
    print(f"ERROR: Database not found at {DB_PATH}")
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 80)
print("FB LISTINGS DATABASE AUDIT - Location Errors & Duplicates")
print("=" * 80)

cur.execute("SELECT COUNT(*) FROM raw_posts")
raw_count = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM listings")
listing_count = cur.fetchone()[0]
print(f"\\nTotal raw_posts: {raw_count}")
print(f"Total listings:  {listing_count}")

cur.execute("PRAGMA table_info(listings)")
listing_cols = [r[1] for r in cur.fetchall()]
cur.execute("PRAGMA table_info(raw_posts)")
raw_cols = [r[1] for r in cur.fetchall()]
print(f"\\nlistings columns: {listing_cols}")
print(f"raw_posts columns: {raw_cols}")

PC_AREAS = [
    'bavaro', 'bavaro', 'punta cana', 'puntacana', 'cap cana', 'capcana',
    'cocotal', 'vista cana', 'vistacana', 'veron', 'higuey',
    'white sands', 'whitesands', 'cana rock', 'canarock', 'downtown pc',
    'downtown punta cana', 'el cortecito', 'cortecito', 'los corales', 'corales',
    'arena gorda', 'cabeza de toro', 'uvero alto', 'hard rock', 'palma real',
    'cana bay', 'cana pearl', 'cana zoe',
    'las canas', 'punta blanca',
    'macao', 'el dorado', 'hacienda del mar', 'the lake', 'village',
    'los altos', 'las iguanas', 'buena vista',
]

NON_PC_AREAS = [
    'santo domingo', 'santiago', 'la romana', 'san pedro', 'puerto plata',
    'sosua', 'cabarete', 'samana', 'las terrenas',
    'la vega', 'bonao', 'azua', 'barahona', 'monte cristi', 'nagua',
    'cotui', 'moca', 'san francisco de macoris', 'sfm',
    'jarabacoa', 'constanza', 'boca chica', 'juan dolio', 'bayahibe',
    'new york', 'miami', 'bogota', 'mexico', 'panama',
    'naco', 'piantini', 'gazcue', 'bella vista sd',
    'distrito nacional', 'zona colonial', 'los jardines',
    'la caleta', 'san isidro', 'los mina', 'villa mella',
    'ensanche naco', 'ensanche ozama',
]

def is_pc_area(text):
    if not text:
        return None
    t = text.lower().strip()
    for area in NON_PC_AREAS:
        if area in t:
            return False
    for area in PC_AREAS:
        if area in t:
            return True
    return None

def extract_location_from_text(text):
    if not text:
        return None, None
    t = text.lower()
    found_pc = []
    found_non_pc = []
    for area in PC_AREAS[:25]:
        if area in t:
            found_pc.append(area)
    for area in NON_PC_AREAS:
        if area in t:
            found_non_pc.append(area)
    return found_pc, found_non_pc

def snippet(text, length=150):
    if not text:
        return "(no text)"
    s = text.replace('\\n', ' ').replace('\\r', ' ')
    s = re.sub(r'\\s+', ' ', s).strip()
    return s[:length] + ('...' if len(s) > length else '')

# ============================================================
# 1. WRONG LOCATION - NOT PUNTA CANA
# ============================================================
print("\\n" + "=" * 80)
print("1. LISTINGS WITH NON-PUNTA CANA LOCATIONS")
print("=" * 80)

cur.execute("""
    SELECT l.id, l.post_id, l.neighborhood, l.community, l.property_type,
           l.listing_type, l.price_usd, l.agent_id, r.raw_text
    FROM listings l
    LEFT JOIN raw_posts r ON l.post_id = r.post_id
    WHERE l.neighborhood IS NOT NULL AND l.neighborhood != ''
""")

non_pc_listings = []
pc_listings = []
unknown_listings = []

for row in cur.fetchall():
    nb = row['neighborhood']
    is_pc = is_pc_area(nb)
    if is_pc is False:
        non_pc_listings.append(dict(row))
    elif is_pc is True:
        pc_listings.append(dict(row))
    else:
        comm = row['community']
        is_pc_comm = is_pc_area(comm) if comm else None
        if is_pc_comm is False:
            non_pc_listings.append(dict(row))
        else:
            unknown_listings.append(dict(row))

print(f"\\nListings with neighborhood set: PC area={len(pc_listings)}, Non-PC={len(non_pc_listings)}, Unknown={len(unknown_listings)}")

if non_pc_listings:
    print(f"\\n--- Non-PC listings (showing up to 30 of {len(non_pc_listings)}) ---")
    for row in non_pc_listings[:30]:
        print(f"\\n  post_id: {row['post_id']}")
        print(f"  neighborhood: {row['neighborhood']}")
        print(f"  community: {row['community']}")
        print(f"  type: {row['property_type']} / {row['listing_type']}")
        print(f"  price: ${row['price_usd']}")
        print(f"  text: {snippet(row['raw_text'])}")

# Check raw_text for non-PC mentions
print(f"\\n--- Checking raw_text for non-PC location mentions ---")
cur.execute("""
    SELECT l.id, l.post_id, l.neighborhood, r.raw_text, l.price_usd, l.property_type
    FROM listings l
    LEFT JOIN raw_posts r ON l.post_id = r.post_id
    WHERE r.raw_text IS NOT NULL
""")

text_mismatches = []
for row in cur.fetchall():
    pc_locs, non_pc_locs = extract_location_from_text(row['raw_text'])
    if non_pc_locs and not pc_locs:
        nb = row['neighborhood'] or '(NULL)'
        text_mismatches.append({
            'post_id': row['post_id'],
            'neighborhood': nb,
            'non_pc_in_text': non_pc_locs,
            'text': row['raw_text'],
            'price': row['price_usd'],
            'type': row['property_type'],
        })

print(f"Listings where raw_text mentions ONLY non-PC locations: {len(text_mismatches)}")
for item in text_mismatches[:30]:
    print(f"\\n  post_id: {item['post_id']}")
    print(f"  neighborhood: {item['neighborhood']}")
    print(f"  non-PC mentions in text: {item['non_pc_in_text']}")
    print(f"  text: {snippet(item['text'])}")

# ============================================================
# 2. DUPLICATES
# ============================================================
print("\\n" + "=" * 80)
print("2. DUPLICATE LISTINGS")
print("=" * 80)

print("\\n--- 2a. Same agent + similar price + same type + same neighborhood ---")
cur.execute("""
    SELECT l1.id as id1, l1.post_id as post_id1, l1.price_usd as price1,
           l2.id as id2, l2.post_id as post_id2, l2.price_usd as price2,
           l1.agent_id, l1.property_type, l1.neighborhood,
           l1.bedrooms, l1.bathrooms
    FROM listings l1
    JOIN listings l2 ON l1.agent_id = l2.agent_id
        AND l1.property_type = l2.property_type
        AND l1.neighborhood = l2.neighborhood
        AND l1.id < l2.id
    WHERE l1.agent_id IS NOT NULL
        AND l1.price_usd IS NOT NULL AND l2.price_usd IS NOT NULL
        AND l1.price_usd > 0 AND l2.price_usd > 0
        AND ABS(l1.price_usd - l2.price_usd) * 1.0 / l1.price_usd < 0.05
    ORDER BY l1.agent_id, l1.price_usd
    LIMIT 30
""")

agent_dupes = cur.fetchall()
print(f"Showing up to 30 agent-based duplicate pairs:")
for row in agent_dupes:
    print(f"\\n  agent: {row['agent_id']}")
    print(f"  post {row['post_id1']} (${row['price1']}) vs post {row['post_id2']} (${row['price2']})")
    print(f"  type: {row['property_type']}, neighborhood: {row['neighborhood']}")
    print(f"  beds/baths: {row['bedrooms']}/{row['bathrooms']}")

cur.execute("""
    SELECT COUNT(*) FROM (
        SELECT l1.id
        FROM listings l1
        JOIN listings l2 ON l1.agent_id = l2.agent_id
            AND l1.property_type = l2.property_type
            AND l1.neighborhood = l2.neighborhood
            AND l1.id < l2.id
        WHERE l1.agent_id IS NOT NULL
            AND l1.price_usd IS NOT NULL AND l2.price_usd IS NOT NULL
            AND l1.price_usd > 0 AND l2.price_usd > 0
            AND ABS(l1.price_usd - l2.price_usd) * 1.0 / l1.price_usd < 0.05
    )
""")
total_agent_dupes = cur.fetchone()[0]
print(f"\\nTotal agent-based duplicate pairs: {total_agent_dupes}")

print("\\n--- 2b. Near-exact text duplicates (first 200 chars) ---")
cur.execute("""
    SELECT SUBSTR(raw_text, 1, 200) as text_prefix, COUNT(*) as cnt,
           GROUP_CONCAT(post_id, ', ') as post_ids
    FROM raw_posts
    WHERE raw_text IS NOT NULL AND LENGTH(raw_text) > 50
    GROUP BY SUBSTR(raw_text, 1, 200)
    HAVING COUNT(*) > 1
    ORDER BY cnt DESC
    LIMIT 30
""")

text_dupes = cur.fetchall()
total_text_dupe_groups = len(text_dupes)
total_text_dupe_posts = sum(r['cnt'] for r in text_dupes) if text_dupes else 0
print(f"Found {total_text_dupe_groups} groups of text duplicates ({total_text_dupe_posts} total posts)")
for row in text_dupes[:30]:
    print(f"\\n  count: {row['cnt']}")
    print(f"  post_ids: {str(row['post_ids'])[:120]}")
    print(f"  text: {snippet(row['text_prefix'], 150)}")

print("\\n--- 2c. Same property_id across multiple posts ---")
cur.execute("""
    SELECT property_id, COUNT(*) as cnt, GROUP_CONCAT(post_id, ', ') as post_ids
    FROM raw_posts
    WHERE property_id IS NOT NULL AND property_id != ''
    GROUP BY property_id
    HAVING COUNT(*) > 1
    ORDER BY cnt DESC
    LIMIT 30
""")

prop_dupes = cur.fetchall()
print(f"Found {len(prop_dupes)} property_ids with multiple posts")
for row in prop_dupes[:15]:
    print(f"\\n  property_id: {row['property_id']}, count: {row['cnt']}")
    print(f"  post_ids: {str(row['post_ids'])[:150]}")

# ============================================================
# 3. NEIGHBORHOOD INCONSISTENCIES
# ============================================================
print("\\n" + "=" * 80)
print("3. NEIGHBORHOOD INCONSISTENCIES")
print("=" * 80)

print("\\n--- 3a. Same property_id, different neighborhoods ---")
cur.execute("""
    SELECT r.property_id,
           GROUP_CONCAT(DISTINCT l.neighborhood) as neighborhoods,
           COUNT(DISTINCT l.neighborhood) as nb_count,
           GROUP_CONCAT(DISTINCT l.post_id) as post_ids
    FROM listings l
    JOIN raw_posts r ON l.post_id = r.post_id
    WHERE r.property_id IS NOT NULL AND r.property_id != ''
        AND l.neighborhood IS NOT NULL AND l.neighborhood != ''
    GROUP BY r.property_id
    HAVING COUNT(DISTINCT l.neighborhood) > 1
    ORDER BY nb_count DESC
    LIMIT 30
""")

nb_inconsist = cur.fetchall()
print(f"Found {len(nb_inconsist)} properties with inconsistent neighborhoods")
for row in nb_inconsist:
    print(f"\\n  property_id: {row['property_id']}")
    print(f"  neighborhoods: {row['neighborhoods']}")
    print(f"  post_ids: {str(row['post_ids'])[:100]}")

print("\\n--- 3b. Neighborhood vs raw_text mismatch ---")
cur.execute("""
    SELECT l.post_id, l.neighborhood, r.raw_text, l.community
    FROM listings l
    JOIN raw_posts r ON l.post_id = r.post_id
    WHERE l.neighborhood IS NOT NULL AND l.neighborhood != ''
        AND r.raw_text IS NOT NULL
""")

nb_text_mismatch = []
for row in cur.fetchall():
    nb = row['neighborhood'].lower()
    text = row['raw_text'].lower() if row['raw_text'] else ''
    nb_in_text = nb in text
    if not nb_in_text and len(text) > 50:
        pc_in_text, non_pc_in_text = extract_location_from_text(text)
        other_areas = [a for a in (pc_in_text or []) if a not in nb and nb not in a]
        if other_areas:
            nb_text_mismatch.append({
                'post_id': row['post_id'],
                'neighborhood': row['neighborhood'],
                'community': row['community'],
                'text_locations': other_areas,
                'text': row['raw_text'],
            })

print(f"Listings where neighborhood differs from text location: {len(nb_text_mismatch)}")
for item in nb_text_mismatch[:30]:
    print(f"\\n  post_id: {item['post_id']}")
    print(f"  neighborhood: {item['neighborhood']}")
    print(f"  community: {item['community']}")
    print(f"  locations in text: {item['text_locations']}")
    print(f"  text: {snippet(item['text'])}")

# ============================================================
# 4. MISSING LOCATIONS
# ============================================================
print("\\n" + "=" * 80)
print("4. MISSING LOCATIONS (NULL neighborhood)")
print("=" * 80)

cur.execute("SELECT COUNT(*) FROM listings WHERE neighborhood IS NULL OR neighborhood = ''")
null_nb = cur.fetchone()[0]
total_listings = listing_count
print(f"\\nListings with NULL/empty neighborhood: {null_nb} / {total_listings} ({null_nb*100//max(total_listings,1)}%)")

cur.execute("""
    SELECT l.post_id, r.raw_text, l.price_usd, l.property_type, l.community
    FROM listings l
    JOIN raw_posts r ON l.post_id = r.post_id
    WHERE (l.neighborhood IS NULL OR l.neighborhood = '')
        AND r.raw_text IS NOT NULL AND LENGTH(r.raw_text) > 30
""")

extractable = []
no_location = []
for row in cur.fetchall():
    pc_locs, non_pc_locs = extract_location_from_text(row['raw_text'])
    if pc_locs or non_pc_locs:
        extractable.append({
            'post_id': row['post_id'],
            'pc_locs': pc_locs,
            'non_pc_locs': non_pc_locs,
            'community': row['community'],
            'text': row['raw_text'],
            'price': row['price_usd'],
            'type': row['property_type'],
        })
    else:
        no_location.append(dict(row))

print(f"NULL neighborhood but location extractable from text: {len(extractable)}")
print(f"NULL neighborhood and NO location found in text: {len(no_location)}")

if extractable:
    print(f"\\n--- Extractable locations (showing up to 30) ---")
    for item in extractable[:30]:
        print(f"\\n  post_id: {item['post_id']}")
        print(f"  community: {item['community']}")
        print(f"  PC locations in text: {item['pc_locs']}")
        print(f"  Non-PC locations in text: {item['non_pc_locs']}")
        print(f"  text: {snippet(item['text'])}")

# ============================================================
# SUMMARY
# ============================================================
print("\\n" + "=" * 80)
print("AUDIT SUMMARY")
print("=" * 80)

cur.execute("""
    SELECT neighborhood, COUNT(*) as cnt
    FROM listings
    WHERE neighborhood IS NOT NULL AND neighborhood != ''
    GROUP BY neighborhood
    ORDER BY cnt DESC
    LIMIT 25
""")
print("\\nTop 25 neighborhoods:")
for row in cur.fetchall():
    print(f"  {row['cnt']:4d}  {row['neighborhood']}")

print(f"\\n{'Category':<55} {'Count':>6}")
print("-" * 65)
print(f"{'Total raw_posts':<55} {raw_count:>6}")
print(f"{'Total listings':<55} {listing_count:>6}")
print(f"{'Non-PC area (by neighborhood)':<55} {len(non_pc_listings):>6}")
print(f"{'Non-PC area (by text only, no PC mention)':<55} {len(text_mismatches):>6}")
print(f"{'Unknown area (neighborhood set but unrecognized)':<55} {len(unknown_listings):>6}")
print(f"{'Agent-based duplicate pairs':<55} {total_agent_dupes:>6}")
print(f"{'Text duplicate groups':<55} {total_text_dupe_groups:>6}")
print(f"{'Text duplicate total posts':<55} {total_text_dupe_posts:>6}")
print(f"{'Properties with multiple posts':<55} {len(prop_dupes):>6}")
print(f"{'Properties with inconsistent neighborhoods':<55} {len(nb_inconsist):>6}")
print(f"{'Neighborhood vs text mismatch':<55} {len(nb_text_mismatch):>6}")
print(f"{'NULL/empty neighborhood':<55} {null_nb:>6}")
print(f"{'  ...extractable from text':<55} {len(extractable):>6}")
print(f"{'  ...no location found':<55} {len(no_location):>6}")

conn.close()
print("\\nAudit complete. NO data was modified.")
'''

# Connect to VPS
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
print("Connecting to VPS 144.172.100.16...")
ssh.connect('144.172.100.16', username='root', password='4K98JSaEoLDaP5', timeout=15)
print("Connected.")

# Upload script
sftp = ssh.open_sftp()
with sftp.open('/tmp/audit_location.py', 'w') as f:
    f.write(AUDIT_SCRIPT)
sftp.close()
print("Script uploaded to /tmp/audit_location.py")

# Execute
print("Running audit...\n")
stdin, stdout, stderr = ssh.exec_command('cd /opt/data && python3 /tmp/audit_location.py', timeout=120)
output = stdout.read().decode('utf-8', errors='replace')
errors = stderr.read().decode('utf-8', errors='replace')

if errors:
    print("STDERR:", errors)
print(output)

ssh.close()
