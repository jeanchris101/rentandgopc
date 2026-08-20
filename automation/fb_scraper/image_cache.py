"""
image_cache.py — Download and cache Facebook CDN images locally.
FB CDN URLs expire after 24-48 hours, so we download at scrape time.
Images stored at /opt/data/images/{post_id}_{index}.jpg
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

import httpx

log = logging.getLogger("fb_scraper.image_cache")

# On VPS this is /opt/data/images, locally it adapts
IMAGE_DIR = Path(os.environ.get("IMAGE_DIR", "/opt/data/images"))
MAX_IMAGES_PER_POST = 5
DOWNLOAD_TIMEOUT = 10.0
MAX_RETRIES = 2
RETRY_DELAY = 1.0


def _ensure_dir():
    """Create image directory if it doesn't exist."""
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)


def _filename(post_id: str, index: int) -> str:
    """Generate a deterministic filename for a post image."""
    # Sanitize post_id — remove anything that's not alphanumeric or underscore
    safe_id = "".join(c if c.isalnum() or c == "_" else "_" for c in post_id)
    return f"{safe_id}_{index}.jpg"


async def download_images(image_urls: list, post_id: str) -> list:
    """
    Download FB CDN images to local disk.

    Args:
        image_urls: List of Facebook CDN URLs
        post_id: Unique post identifier

    Returns:
        List of local filenames (not full paths) for successfully downloaded images.
        If download fails for an image, it's excluded from the list.
    """
    _ensure_dir()

    if not image_urls:
        return []

    # Limit to first N images
    urls_to_download = image_urls[:MAX_IMAGES_PER_POST]
    filenames = []

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(DOWNLOAD_TIMEOUT),
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        },
    ) as client:
        for idx, url in enumerate(urls_to_download):
            fname = _filename(post_id, idx)
            filepath = IMAGE_DIR / fname

            # Skip if already downloaded (idempotent)
            if filepath.exists() and filepath.stat().st_size > 0:
                filenames.append(fname)
                continue

            # Download with retry
            success = False
            for attempt in range(MAX_RETRIES + 1):
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        content_type = resp.headers.get("content-type", "")
                        # Verify it's actually an image
                        if "image" in content_type or len(resp.content) > 1000:
                            filepath.write_bytes(resp.content)
                            filenames.append(fname)
                            success = True
                            break
                        else:
                            log.warning(f"Non-image response for {post_id}_{idx}: {content_type}")
                            break
                    elif resp.status_code in (403, 404, 410):
                        # URL expired or gone — no point retrying
                        log.debug(f"Image gone ({resp.status_code}) for {post_id}_{idx}")
                        break
                    else:
                        log.debug(f"HTTP {resp.status_code} for {post_id}_{idx}, attempt {attempt+1}")
                except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
                    log.debug(f"Download error for {post_id}_{idx}, attempt {attempt+1}: {e}")

                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)

            if not success:
                log.debug(f"Failed to download image {idx} for post {post_id[:20]}")

    if filenames:
        log.debug(f"Cached {len(filenames)}/{len(urls_to_download)} images for post {post_id[:20]}")

    return filenames


def get_image_urls(post_id: str, image_urls_json: str) -> list:
    """
    Get display URLs for a post's images — prefers local cached versions.

    Args:
        post_id: Unique post identifier
        image_urls_json: JSON string of original FB CDN URLs

    Returns:
        List of URLs — local path (/images/filename) if cached, original URL if not.
    """
    try:
        original_urls = json.loads(image_urls_json) if image_urls_json else []
    except (json.JSONDecodeError, TypeError):
        original_urls = []

    if not original_urls:
        return []

    result = []
    for idx, url in enumerate(original_urls[:MAX_IMAGES_PER_POST]):
        fname = _filename(post_id, idx)
        filepath = IMAGE_DIR / fname
        if filepath.exists() and filepath.stat().st_size > 0:
            result.append(f"/images/{fname}")
        else:
            result.append(url)

    return result


async def download_images_background(image_urls: list, post_id: str, conn_path: str = None):
    """
    Download images and update the local_images column in raw_posts.
    Designed to be fired as a background task after DB insert.
    """
    filenames = await download_images(image_urls, post_id)

    if filenames and conn_path:
        import sqlite3
        try:
            conn = sqlite3.connect(conn_path)
            conn.execute(
                "UPDATE raw_posts SET local_images = ? WHERE post_id = ?",
                (json.dumps(filenames), post_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            log.error(f"Failed to update local_images for {post_id}: {e}")

    return filenames
