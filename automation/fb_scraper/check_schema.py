import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('144.172.100.16', username='root', password='4K98JSaEoLDaP5')

script = r'''
import sqlite3
conn = sqlite3.connect('/opt/data/fb_listings.db')
c = conn.cursor()

c.execute('PRAGMA table_info(listings)')
print('LISTINGS SCHEMA:')
for row in c.fetchall():
    print(row)

c.execute('PRAGMA table_info(raw_posts)')
print('\nRAW_POSTS SCHEMA:')
for row in c.fetchall():
    print(row)

c.execute('SELECT COUNT(*) FROM listings')
print(f'\nTotal listings: {c.fetchone()[0]}')
c.execute('SELECT COUNT(*) FROM raw_posts')
print(f'Total raw_posts: {c.fetchone()[0]}')
c.execute('SELECT COUNT(*) FROM listings WHERE needs_review=1')
print(f'Already needs_review=1: {c.fetchone()[0]}')
c.execute('SELECT COUNT(*) FROM listings WHERE listing_type IS NULL')
print(f'Missing listing_type: {c.fetchone()[0]}')
c.execute('SELECT COUNT(*) FROM listings WHERE neighborhood IS NULL')
print(f'Missing neighborhood: {c.fetchone()[0]}')
c.execute('SELECT COUNT(*) FROM listings WHERE is_spam=1')
print(f'Already is_spam=1: {c.fetchone()[0]}')

# Check if review_reason column exists
cols = [row[1] for row in c.execute('PRAGMA table_info(listings)').fetchall()]
print(f'\nListing columns: {cols}')
print(f'Has review_reason: {"review_reason" in cols}')

# Sample a few raw_texts to see format
c.execute('SELECT l.id, r.raw_text FROM listings l JOIN raw_posts r ON l.post_id = r.post_id LIMIT 3')
for row in c.fetchall():
    print(f'\n--- Listing {row[0]} ---')
    print(row[1][:300] if row[1] else 'NULL')

conn.close()
'''

# Write script to VPS and execute
sftp = ssh.open_sftp()
with sftp.file('/tmp/check_schema.py', 'w') as f:
    f.write(script)
sftp.close()

stdin, stdout, stderr = ssh.exec_command('python3 /tmp/check_schema.py')
print(stdout.read().decode('utf-8', errors='replace'))
err = stderr.read().decode('utf-8', errors='replace')
if err:
    print('STDERR:', err)
ssh.close()
