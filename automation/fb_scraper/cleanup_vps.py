"""
VPS Database Cleanup — Flag garbage and non-RE spam in fb_listings.db
Runs remotely via SSH on 144.172.100.16
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import paramiko
import textwrap

VPS_HOST = '144.172.100.16'
VPS_USER = 'root'
VPS_PASS = '4K98JSaEoLDaP5'
DB_PATH = '/opt/data/fb_listings.db'

CLEANUP_SCRIPT = '''
import sqlite3

db = sqlite3.connect("''' + DB_PATH + '''")
cur = db.cursor()

results = {}

# =============================================================
# TASK 1: Purge garbage rows
# =============================================================

# 1a. bathrooms=74 (known La Pulga garbage)
cur.execute("UPDATE listings SET is_spam=1, review_reason='garbage_bath74' WHERE bathrooms=74 AND is_spam=0")
results['bath74'] = cur.rowcount

# 1b. "no products" text
cur.execute("""
    UPDATE listings SET is_spam=1, review_reason='garbage_no_products'
    WHERE is_spam=0 AND post_id IN (
        SELECT r.post_id FROM raw_posts r
        WHERE LOWER(r.raw_text) LIKE '%there are currently no products%'
           OR LOWER(r.raw_text) LIKE '%no hay productos%'
    )
""")
results['no_products'] = cur.rowcount

# 1c. bedrooms > 50 (parsing garbage)
cur.execute("UPDATE listings SET is_spam=1, review_reason='garbage_bed_high' WHERE bedrooms > 50 AND is_spam=0")
results['bed_high'] = cur.rowcount

# 1d. Very short raw_text (<15 chars) with no price
cur.execute("""
    UPDATE listings SET is_spam=1, review_reason='garbage_short_text'
    WHERE is_spam=0 AND COALESCE(price_usd, 0) = 0 AND post_id IN (
        SELECT r.post_id FROM raw_posts r
        WHERE length(COALESCE(r.raw_text, '')) < 15
    )
""")
results['short_text'] = cur.rowcount

task1_total = sum(results.values())
print("=== TASK 1: Garbage purge ===")
for k, v in results.items():
    print(f"  {k}: {v} rows flagged")
print(f"  TOTAL Task 1: {task1_total}")

# =============================================================
# TASK 2: Flag non-RE content as spam
# =============================================================

RE_KEYWORDS = [
    'casa', 'apartamento', 'apto', 'villa', 'terreno', 'solar',
    'venta', 'alquiler', 'rent', 'sale', 'habitacion', 'habitaciones',
    'bedroom', 'bath', 'sqm', 'm2', 'piso', 'penthouse',
    'condominio', 'condo', 'residencial', 'inmueble', 'propiedad',
    'lote', 'parcela', 'finca', 'duplex', 'townhouse', 'studio',
    'estudio', 'amueblado', 'furnished', 'piscina', 'pool',
    'dormitorio', 'recamara', 'alcoba', 'edificio',
    'bienes raices', 'real estate', 'inmobiliaria',
]

SPAM_CATEGORIES = {
    'vehicles': [
        'carro', 'vehiculo', 'camioneta', 'toyota', 'honda', 'hyundai',
        'kia', 'nissan', 'mitsubishi', 'motor ', 'moto ', 'motocicleta',
        'jeepeta', 'pickup', 'camion'
    ],
    'electronics': [
        'samsung', 'iphone', 'telefono', 'celular', 'laptop',
        'computadora', 'televisor', ' tv '
    ],
    'services': [
        'salon de', 'peluqueria', 'unas acrilicas', 'barberia',
        'tour ', 'excursion', 'submarine', 'scuba'
    ],
    'jobs': [
        'empleo', 'trabajo disponible', 'vacante', 'se busca personal',
        'se necesita personal', 'hiring', 'oferta de trabajo',
        'solicitamos', 'estamos buscando'
    ],
    'other_non_re': [
        'comida', 'restaurante', 'delivery de', 'ropa de',
        'zapatos', 'juego de video', 'game console', 'controller',
        'playstation', 'xbox', 'nintendo'
    ],
}

cur.execute("""
    SELECT l.id, l.post_id, LOWER(COALESCE(r.raw_text, ''))
    FROM listings l
    JOIN raw_posts r ON l.post_id = r.post_id
    WHERE l.is_spam = 0
""")
rows = cur.fetchall()
print(f"\\n=== TASK 2: Non-RE content flagging ===")
print(f"  Checking {len(rows)} non-spam listings...")

category_counts = {cat: 0 for cat in SPAM_CATEGORIES}
flagged_ids = []

for lid, post_id, text in rows:
    if not text:
        continue

    has_re = any(kw in text for kw in RE_KEYWORDS)
    if has_re:
        continue

    for cat, keywords in SPAM_CATEGORIES.items():
        matched = False
        for kw in keywords:
            if kw in text:
                matched = True
                break
        if matched:
            flagged_ids.append((lid, f'spam_{cat}'))
            category_counts[cat] += 1
            break

for lid, reason in flagged_ids:
    cur.execute("UPDATE listings SET is_spam=1, review_reason=? WHERE id=?", (reason, lid))

task2_total = len(flagged_ids)
for cat, count in category_counts.items():
    if count > 0:
        print(f"  {cat}: {count} rows flagged")
print(f"  TOTAL Task 2: {task2_total}")

db.commit()

cur.execute("SELECT is_spam, COUNT(*) FROM listings GROUP BY is_spam")
print(f"\\n=== Final distribution ===")
for row in cur.fetchall():
    status = "spam" if row[0] == 1 else "clean"
    print(f"  {status}: {row[1]}")

cur.execute("SELECT review_reason, COUNT(*) FROM listings WHERE is_spam=1 GROUP BY review_reason ORDER BY COUNT(*) DESC")
print(f"\\n=== Spam breakdown by reason ===")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

print(f"\\nGRAND TOTAL flagged this run: {task1_total + task2_total}")

db.close()
'''


def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VPS_HOST, username=VPS_USER, password=VPS_PASS)

    # Upload script
    sftp = ssh.open_sftp()
    with sftp.file('/tmp/cleanup_db.py', 'w') as f:
        f.write(CLEANUP_SCRIPT)
    sftp.close()

    # Run it
    stdin, stdout, stderr = ssh.exec_command('python3 /tmp/cleanup_db.py')
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')

    print(out)
    if err:
        print('STDERR:', err)

    ssh.close()


if __name__ == '__main__':
    main()
