"""
backfill_images_v3.py — Download missing local images for all posts.
Only 3,013 files cached out of 9,101 posts with image URLs.
Run on VPS: python3 /opt/fb_scraper/backfill_images_v3.py
"""

import asyncio
import json
import sqlite3
import os
import sys
from pathlib import Path

# Reuse existing image_cache module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from image_cache import download_images, IMAGE_DIR, _filename

DB_PATH = Path(__file__).parent.parent / "data" / "fb_listings.db"


async def backfill():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Find posts with image URLs but missing local cache
    rows = conn.execute(
        "SELECT post_id, image_urls FROM raw_posts "
        "WHERE image_urls IS NOT NULL AND image_urls != '[]' "
        "ORDER BY captured_at DESC"
    ).fetchall()

    print(f"Total posts with image URLs: {len(rows)}")

    need_download = []
    for r in rows:
        post_id = r["post_id"]
        urls = json.loads(r["image_urls"] or "[]")
        if not urls:
            continue
        # Check if first image is already cached locally
        fname = _filename(post_id, 0)
        filepath = IMAGE_DIR / fname
        if not filepath.exists() or filepath.stat().st_size == 0:
            need_download.append((post_id, urls))

    print(f"Need download: {need_download}")
    print(f"Already cached: {len(rows) - len(need_download)}")

    downloaded = 0
    failed = 0
    batch_size = 10  # concurrent downloads

    for i in range(0, len(need_download), batch_size):
        batch = need_download[i:i + batch_size]
        tasks = [download_images(urls, post_id) for post_id, urls in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for (post_id, urls), result in zip(batch, results):
            if isinstance(result, Exception):
                failed += 1
            elif result:
                downloaded += 1
                # Update local_images in DB
                conn.execute(
                    "UPDATE raw_posts SET local_images = ? WHERE post_id = ?",
                    (json.dumps(result), post_id),
                )
            else:
                failed += 1

        conn.commit()

        done = i + len(batch)
        if done % 100 == 0 or done == len(need_download):
            print(f"  Progress: {done}/{len(need_download)} "
                  f"(downloaded={downloaded}, failed={failed})")

    conn.close()
    print(f"\nDone! Downloaded: {downloaded}, Failed: {failed}")
    print(f"Total local images now: {len(list(IMAGE_DIR.glob('*.jpg')))}")


if __name__ == "__main__":
    asyncio.run(backfill())
