import sqlite3, json, os

conn = sqlite3.connect("/opt/data/fb_listings.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT l.post_id, r.image_urls FROM listings l "
    "JOIN raw_posts r ON l.post_id = r.post_id "
    "WHERE l.is_spam=0 AND l.is_duplicate=0 "
    "ORDER BY r.captured_at DESC LIMIT 30"
).fetchall()

img_dir = "/opt/data/images"
has_local = 0
has_urls = 0
no_imgs = 0

for r in rows:
    pid = r["post_id"]
    imgs = json.loads(r["image_urls"] or "[]")
    local = any(os.path.exists(os.path.join(img_dir, pid + "_" + str(i) + ".jpg")) for i in range(5))
    if local:
        has_local += 1
    elif imgs:
        has_urls += 1
    else:
        no_imgs += 1
    status = "LOCAL" if local else ("FB_URL" if imgs else "NONE")
    print(pid + ": fb_urls=" + str(len(imgs)) + " " + status)

print("")
print("Last 30: " + str(has_local) + " local, " + str(has_urls) + " FB URL only, " + str(no_imgs) + " no images")

# Total coverage
total = conn.execute("SELECT COUNT(*) FROM listings WHERE is_spam=0 AND is_duplicate=0").fetchone()[0]
total_with_urls = conn.execute(
    "SELECT COUNT(*) FROM listings l JOIN raw_posts r ON l.post_id=r.post_id "
    "WHERE l.is_spam=0 AND l.is_duplicate=0 AND r.image_urls IS NOT NULL AND r.image_urls != '[]'"
).fetchone()[0]
print("Overall: " + str(total_with_urls) + "/" + str(total) + " have image URLs")

# Count local cache
files = [f for f in os.listdir(img_dir) if f.endswith(".jpg")]
unique_posts = set(f.rsplit("_", 1)[0] for f in files)
print("Local cache: " + str(len(unique_posts)) + " posts, " + str(len(files)) + " files")
