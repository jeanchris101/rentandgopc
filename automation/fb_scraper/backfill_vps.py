import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('144.172.100.16', username='root', password='4K98JSaEoLDaP5')

script = r'''
import sqlite3, re
from collections import Counter

conn = sqlite3.connect('/opt/data/fb_listings.db')
conn.execute("PRAGMA journal_mode=WAL")
c = conn.cursor()

# ============================================================
# TASK 1: Flag non-Punta Cana listings
# ============================================================
print("=" * 60)
print("TASK 1: Flag non-Punta Cana listings")
print("=" * 60)

pc_locations = [
    'bavaro', 'b\u00e1varo', 'punta cana', 'cap cana', 'cocotal',
    'vista cana', 'veron', 'ver\u00f3n', 'higuey', 'hig\u00fcey',
    'white sands', 'cana rock', 'downtown pc', 'el cortecito',
    'los corales', 'arena gorda', 'cabeza de toro', 'uvero alto',
    'macao', 'hard rock', 'palma real', 'san juan', 'anamuya'
]

non_pc_locations = [
    'santo domingo', 'santiago', 'la romana', 'san pedro',
    'puerto plata', 'sosua', 'sos\u00faa', 'cabarete', 'samana',
    'saman\u00e1', 'las terrenas', 'la vega', 'bonao', 'moca',
    'barahona', 'azua', 'san cristobal', 'san crist\u00f3bal',
    'monte plata', 'bayahibe', 'boca chica', 'zona colonial',
    'naco', 'piantini', 'gazcue', 'ensanche', 'villa mella',
    'los alcarrizos', 'herrera', 'alma rosa', 'pantoja', 'los mina'
]

# Get all listings joined with raw text (exclude already spam)
c.execute("""
    SELECT l.id, r.raw_text, l.is_spam, l.needs_review, l.review_reason
    FROM listings l
    JOIN raw_posts r ON l.post_id = r.post_id
    WHERE l.is_spam = 0
""")
rows = c.fetchall()
print(f"Checking {len(rows)} non-spam listings...")

flagged = []
non_pc_found = Counter()

for lid, raw_text, is_spam, needs_review, review_reason in rows:
    if not raw_text:
        continue
    text_lower = raw_text.lower()

    # Check if any PC location is mentioned
    has_pc = any(loc in text_lower for loc in pc_locations)

    # Check which non-PC locations are mentioned
    found_non_pc = [loc for loc in non_pc_locations if loc in text_lower]

    # Flag only if has non-PC locations but NO PC locations
    if found_non_pc and not has_pc:
        flagged.append((lid, found_non_pc))
        for loc in found_non_pc:
            non_pc_found[loc] += 1

print(f"\nFound {len(flagged)} listings with ONLY non-PC locations")
print(f"\nNon-PC location distribution:")
for loc, count in non_pc_found.most_common(20):
    print(f"  {loc}: {count}")

# Update: set needs_review=1 and review_reason='non_pc_location'
# Don't overwrite if already has a different review_reason
flagged_ids = [f[0] for f in flagged]
if flagged_ids:
    # Batch update
    for lid in flagged_ids:
        c.execute("""
            UPDATE listings
            SET needs_review = 1, review_reason = 'non_pc_location'
            WHERE id = ? AND (review_reason IS NULL OR review_reason = '' OR review_reason = 'non_pc_location')
        """, (lid,))
    # For those that already have a review_reason, append
    for lid in flagged_ids:
        c.execute("""
            UPDATE listings
            SET needs_review = 1, review_reason = review_reason || '; non_pc_location'
            WHERE id = ? AND review_reason IS NOT NULL AND review_reason != '' AND review_reason != 'non_pc_location'
            AND review_reason NOT LIKE '%non_pc_location%'
        """, (lid,))
    conn.commit()
    print(f"\nFlagged {len(flagged_ids)} listings with needs_review=1, review_reason='non_pc_location'")

    # Show a few examples
    print("\nExamples:")
    for lid, locs in flagged[:5]:
        c.execute("SELECT r.raw_text FROM listings l JOIN raw_posts r ON l.post_id = r.post_id WHERE l.id = ?", (lid,))
        row = c.fetchone()
        txt = (row[0][:150] if row[0] else 'NULL') if row else 'NOT FOUND'
        print(f"  ID {lid} [{', '.join(locs)}]: {txt}...")

# ============================================================
# TASK 2: Backfill missing listing types
# ============================================================
print("\n" + "=" * 60)
print("TASK 2: Backfill missing listing_type")
print("=" * 60)

sale_keywords = [
    'se vende', 'en venta', 'for sale', 'venta directa',
    'precio de venta', 'de oportunidad', 'a la venta', 'selling'
]
rent_keywords = [
    'se alquila', 'alquiler', 'for rent', 'en alquiler',
    'renta', 'rental', 'monthly', 'mensual', 'por mes',
    'per month', 'per night', 'por noche', 'airbnb'
]

c.execute("""
    SELECT l.id, r.raw_text
    FROM listings l
    JOIN raw_posts r ON l.post_id = r.post_id
    WHERE l.listing_type IS NULL
""")
null_type_rows = c.fetchall()
print(f"Checking {len(null_type_rows)} listings with NULL listing_type...")

type_counts = Counter()
updates = []

for lid, raw_text in null_type_rows:
    if not raw_text:
        continue
    text_lower = raw_text.lower()

    has_sale = any(kw in text_lower for kw in sale_keywords)
    has_rent = any(kw in text_lower for kw in rent_keywords)

    if has_sale and has_rent:
        updates.append(('sale_or_rent', lid))
        type_counts['sale_or_rent'] += 1
    elif has_sale:
        updates.append(('sale', lid))
        type_counts['sale'] += 1
    elif has_rent:
        updates.append(('rent', lid))
        type_counts['rent'] += 1

c.executemany("UPDATE listings SET listing_type = ? WHERE id = ?", updates)
conn.commit()

print(f"\nBackfilled {len(updates)} listing types:")
for t, count in type_counts.most_common():
    print(f"  {t}: {count}")

# Check remaining nulls
c.execute("SELECT COUNT(*) FROM listings WHERE listing_type IS NULL")
print(f"Still NULL listing_type: {c.fetchone()[0]}")

# ============================================================
# TASK 3: Backfill missing neighborhoods
# ============================================================
print("\n" + "=" * 60)
print("TASK 3: Backfill missing neighborhoods")
print("=" * 60)

# Order matters - check more specific/multi-word first
neighborhood_map = [
    ('punta cana', 'Punta Cana'),
    ('cap cana', 'Cap Cana'),
    ('vista cana', 'Vista Cana'),
    ('cana rock', 'Cana Rock'),
    ('white sands', 'White Sands'),
    ('el cortecito', 'El Cortecito'),
    ('los corales', 'Los Corales'),
    ('uvero alto', 'Uvero Alto'),
    ('arena gorda', 'Arena Gorda'),
    ('cabeza de toro', 'Cabeza de Toro'),
    ('hard rock', 'Hard Rock'),
    ('palma real', 'Palma Real'),
    ('downtown pc', 'Downtown PC'),
    ('bavaro', 'Bavaro'),
    ('b\u00e1varo', 'Bavaro'),
    ('cocotal', 'Cocotal'),
    ('veron', 'Veron'),
    ('ver\u00f3n', 'Veron'),
    ('higuey', 'Higuey'),
    ('hig\u00fcey', 'Higuey'),
    ('macao', 'Macao'),
    ('anamuya', 'Anamuya'),
    ('san juan', 'San Juan'),
]

c.execute("""
    SELECT l.id, r.raw_text
    FROM listings l
    JOIN raw_posts r ON l.post_id = r.post_id
    WHERE l.neighborhood IS NULL
""")
null_hood_rows = c.fetchall()
print(f"Checking {len(null_hood_rows)} listings with NULL neighborhood...")

hood_counts = Counter()
hood_updates = []

for lid, raw_text in null_hood_rows:
    if not raw_text:
        continue
    text_lower = raw_text.lower()

    for pattern, normalized in neighborhood_map:
        if pattern in text_lower:
            hood_updates.append((normalized, lid))
            hood_counts[normalized] += 1
            break  # first match wins

c.executemany("UPDATE listings SET neighborhood = ? WHERE id = ?", hood_updates)
conn.commit()

print(f"\nBackfilled {len(hood_updates)} neighborhoods:")
for hood, count in hood_counts.most_common():
    print(f"  {hood}: {count}")

c.execute("SELECT COUNT(*) FROM listings WHERE neighborhood IS NULL")
print(f"Still NULL neighborhood: {c.fetchone()[0]}")

# ============================================================
# FINAL SUMMARY
# ============================================================
print("\n" + "=" * 60)
print("FINAL SUMMARY")
print("=" * 60)
print(f"Task 1: Flagged {len(flagged_ids)} non-PC listings (needs_review=1, review_reason='non_pc_location')")
print(f"Task 2: Backfilled {len(updates)} listing types (sale={type_counts.get('sale',0)}, rent={type_counts.get('rent',0)}, sale_or_rent={type_counts.get('sale_or_rent',0)})")
print(f"Task 3: Backfilled {len(hood_updates)} neighborhoods")

# Final stats
c.execute("SELECT COUNT(*) FROM listings WHERE listing_type IS NULL")
remaining_type = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM listings WHERE neighborhood IS NULL")
remaining_hood = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM listings WHERE review_reason LIKE '%non_pc_location%'")
total_non_pc = c.fetchone()[0]
print(f"\nRemaining NULL listing_type: {remaining_type}")
print(f"Remaining NULL neighborhood: {remaining_hood}")
print(f"Total non-PC flagged: {total_non_pc}")

conn.close()
'''

# Write script to VPS and execute
sftp = ssh.open_sftp()
with sftp.file('/tmp/backfill_script.py', 'w') as f:
    f.write(script)
sftp.close()

stdin, stdout, stderr = ssh.exec_command('python3 /tmp/backfill_script.py', timeout=120)
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print(out)
if err:
    print('STDERR:', err)
ssh.close()
