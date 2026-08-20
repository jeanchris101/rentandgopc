"""
backfill_images.py — One-time migration to download and cache FB CDN images
for all existing posts in raw_posts.

Processes in batches of 20 with delays to avoid hammering FB CDN.
Run: python3 backfill_images.py

Safe to re-run (idempotent) — skips already-cached images.
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import asyncio
import json
import logging
import sqlite3
import time
from pathlib import Path

# Adjust import path
sys.path.insert(0, str(Path(__file__).parent))
from image_cache import download_images, IMAGE_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("backfill_images")

DB_PATH = Path(__file__).parent.parent / "data" / "fb_listings.db"
BATCH_SIZE = 20
BATCH_DELAY = 2.0  # seconds between batches


async def backfill():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Ensure local_images column exists
    cols = [r[1] for r in conn.execute("PRAGMA table_info(raw_posts)").fetchall()]
    if "local_images" not in cols:
        conn.execute("ALTER TABLE raw_posts ADD COLUMN local_images TEXT")
        conn.commit()
        log.info("Added local_images column to raw_posts")

    # Get all posts with image_urls but no local_images (or empty local_images)
    rows = conn.execute("""
        SELECT post_id, image_urls FROM raw_posts
        WHERE image_urls IS NOT NULL
          AND image_urls != '[]'
          AND image_urls != ''
          AND (local_images IS NULL OR local_images = '' OR local_images = '[]')
        ORDER BY captured_at DESC
    """).fetchall()

    total = len(rows)
    log.info(f"Found {total} posts needing image backfill")
    log.info(f"Image directory: {IMAGE_DIR}")

    if total == 0:
        log.info("Nothing to do!")
        conn.close()
        return

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    failed = 0
    skipped = 0

    for batch_start in range(0, total, BATCH_SIZE):
        batch = rows[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

        log.info(f"Batch {batch_num}/{total_batches} ({batch_start+1}-{min(batch_start+BATCH_SIZE, total)} of {total})")

        for row in batch:
            post_id = row["post_id"]
            try:
                image_urls = json.loads(row["image_urls"])
            except (json.JSONDecodeError, TypeError):
                skipped += 1
                continue

            if not image_urls:
                skipped += 1
                continue

            try:
                filenames = await download_images(image_urls, post_id)
                if filenames:
                    conn.execute(
                        "UPDATE raw_posts SET local_images = ? WHERE post_id = ?",
                        (json.dumps(filenames), post_id),
                    )
                    downloaded += 1
                else:
                    failed += 1
            except Exception as e:
                log.error(f"Error processing {post_id[:20]}: {e}")
                failed += 1

        conn.commit()

        # Progress report
        done = min(batch_start + BATCH_SIZE, total)
        pct = done / total * 100
        log.info(f"  Progress: {done}/{total} ({pct:.0f}%) — {downloaded} cached, {failed} failed, {skipped} skipped")

        # Delay between batches to be nice to FB CDN
        if batch_start + BATCH_SIZE < total:
            log.info(f"  Waiting {BATCH_DELAY}s before next batch...")
            await asyncio.sleep(BATCH_DELAY)

    conn.close()

    log.info(f"\nBackfill complete!")
    log.info(f"  Total posts: {total}")
    log.info(f"  Downloaded:  {downloaded}")
    log.info(f"  Failed:      {failed}")
    log.info(f"  Skipped:     {skipped}")

    # Disk usage
    if IMAGE_DIR.exists():
        total_bytes = sum(f.stat().st_size for f in IMAGE_DIR.iterdir() if f.is_file())
        total_mb = total_bytes / (1024 * 1024)
        file_count = sum(1 for f in IMAGE_DIR.iterdir() if f.is_file())
        log.info(f"  Disk usage: {file_count} files, {total_mb:.1f} MB")


if __name__ == "__main__":
    asyncio.run(backfill())
