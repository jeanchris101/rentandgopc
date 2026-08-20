"""
backfill_images_v2.py — Mass-download images for existing posts.
Tries all posts with image_urls but no local_images cached.
Runs directly on VPS. Handles expired URLs gracefully.
"""

import asyncio
import json
import logging
import sqlite3
import time
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("backfill_images")

DB_PATH = Path("/opt/data/fb_listings.db")
IMAGE_DIR = Path("/opt/data/images")
MAX_IMAGES_PER_POST = 5
DOWNLOAD_TIMEOUT = 8.0
BATCH_SIZE = 50
# Process most recent posts first (they're most likely to still have valid URLs)
CONCURRENCY = 10  # parallel downloads per batch


def _safe_id(post_id: str) -> str:
    return "".join(c if c.isalnum() or c == "_" else "_" for c in post_id)


async def download_one(client: httpx.AsyncClient, url: str, filepath: Path) -> bool:
    """Download a single image. Returns True if successful."""
    if filepath.exists() and filepath.stat().st_size > 0:
        return True
    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            ct = resp.headers.get("content-type", "")
            if "image" in ct or len(resp.content) > 1000:
                filepath.write_bytes(resp.content)
                return True
        return False
    except Exception:
        return False


async def process_post(client: httpx.AsyncClient, post_id: str, image_urls: list) -> list:
    """Download images for one post. Returns list of filenames."""
    safe_id = _safe_id(post_id)
    filenames = []
    for idx, url in enumerate(image_urls[:MAX_IMAGES_PER_POST]):
        if not url or not isinstance(url, str):
            continue
        fname = f"{safe_id}_{idx}.jpg"
        filepath = IMAGE_DIR / fname
        ok = await download_one(client, url, filepath)
        if ok:
            filenames.append(fname)
    return filenames


async def main():
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Get posts with image URLs but no local images, newest first
    rows = conn.execute("""
        SELECT post_id, image_urls FROM raw_posts
        WHERE image_urls IS NOT NULL AND image_urls != '' AND image_urls != '[]'
        AND (local_images IS NULL OR local_images = '' OR local_images = '[]')
        ORDER BY captured_at DESC
    """).fetchall()

    total = len(rows)
    log.info(f"Found {total} posts needing image download")

    if not total:
        conn.close()
        return

    downloaded = 0
    failed = 0
    skipped = 0
    consecutive_failures = 0

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(DOWNLOAD_TIMEOUT),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=CONCURRENCY, max_keepalive_connections=5),
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    ) as client:
        for batch_start in range(0, total, BATCH_SIZE):
            batch = rows[batch_start:batch_start + BATCH_SIZE]

            # Stop if too many consecutive failures (all URLs expired)
            if consecutive_failures > 100:
                log.warning(f"100+ consecutive failures — remaining URLs likely all expired. Stopping.")
                break

            tasks = []
            post_ids = []
            for row in batch:
                post_id = row["post_id"]
                try:
                    urls = json.loads(row["image_urls"])
                except (json.JSONDecodeError, TypeError):
                    continue
                if not urls:
                    continue
                post_ids.append(post_id)
                tasks.append(process_post(client, post_id, urls))

            if not tasks:
                continue

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Update DB with results
            for pid, result in zip(post_ids, results):
                if isinstance(result, Exception):
                    failed += 1
                    consecutive_failures += 1
                    continue

                if result:  # got at least one image
                    conn.execute(
                        "UPDATE raw_posts SET local_images = ? WHERE post_id = ?",
                        (json.dumps(result), pid)
                    )
                    downloaded += 1
                    consecutive_failures = 0
                else:
                    failed += 1
                    consecutive_failures += 1

            conn.commit()

            processed = batch_start + len(batch)
            log.info(f"Progress: {processed}/{total} — downloaded: {downloaded}, failed: {failed}")

            # Small delay between batches to be nice
            await asyncio.sleep(0.5)

    conn.close()
    log.info(f"Done — downloaded images for {downloaded} posts, {failed} failed out of {total}")


if __name__ == "__main__":
    asyncio.run(main())
