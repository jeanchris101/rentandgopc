"""
Punta Cana Properties — Facebook Auto-Poster
Reads from content-queue.json and posts to Facebook Page via Graph API.
Supports text + image posts with rate limiting.
"""

import os
import sys
import json
import time
from datetime import datetime, date
from pathlib import Path

import requests

# --- Config ---
GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
DATA_DIR = Path(__file__).parent / "data"
QUEUE_FILE = DATA_DIR / "content-queue.json"
POST_LOG_FILE = DATA_DIR / "facebook-post-log.json"

# Facebook rate limits: max 25 posts/day per page, but we target 2-3
MAX_POSTS_PER_RUN = 3
MIN_DELAY_BETWEEN_POSTS = 30  # seconds


def load_json(path: Path, default=None):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else []


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_page_token() -> str | None:
    token = os.environ.get("FACEBOOK_PAGE_TOKEN")
    if not token:
        print("Error: FACEBOOK_PAGE_TOKEN environment variable not set")
        print("Get one at: https://developers.facebook.com/tools/explorer/")
        print("Required permissions: pages_manage_posts, pages_read_engagement")
    return token


def get_page_id() -> str | None:
    page_id = os.environ.get("FACEBOOK_PAGE_ID")
    if not page_id:
        print("Error: FACEBOOK_PAGE_ID environment variable not set")
    return page_id


def post_text(page_id: str, token: str, message: str) -> dict | None:
    """Publish a text-only post to the Facebook Page."""
    url = f"{GRAPH_API_BASE}/{page_id}/feed"
    resp = requests.post(url, data={
        "message": message,
        "access_token": token,
    }, timeout=30)

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Posted: {data.get('id', 'unknown')}")
        return data
    else:
        print(f"  Error {resp.status_code}: {resp.text}")
        return None


def post_photo(page_id: str, token: str, message: str, image_url: str) -> dict | None:
    """Publish a photo post to the Facebook Page."""
    url = f"{GRAPH_API_BASE}/{page_id}/photos"
    resp = requests.post(url, data={
        "message": message,
        "url": image_url,
        "access_token": token,
    }, timeout=60)

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Posted photo: {data.get('id', 'unknown')}")
        return data
    else:
        print(f"  Error {resp.status_code}: {resp.text}")
        return None


def format_social_post(content: dict, lang: str = "en") -> str:
    """Format a social post content dict into a publishable string."""
    lang_content = content.get(lang, content.get("en", {}))
    text = lang_content.get("text", "")
    hashtags = lang_content.get("hashtags", [])
    if hashtags:
        text += "\n\n" + " ".join(f"#{tag.lstrip('#')}" for tag in hashtags)
    return text


def get_posts_today(post_log: list) -> int:
    today = date.today().isoformat()
    return sum(1 for e in post_log if e.get("date") == today)


def publish_queue_items(page_id: str, token: str, language: str = "en"):
    """Read content queue, publish draft social posts, update statuses."""
    queue = load_json(QUEUE_FILE, [])
    post_log = load_json(POST_LOG_FILE, [])

    posts_today = get_posts_today(post_log)
    if posts_today >= MAX_POSTS_PER_RUN:
        print(f"Already posted {posts_today} times today. Skipping.")
        return

    drafts = [item for item in queue
              if item.get("type") == "social_post"
              and item.get("status") == "draft"]

    if not drafts:
        print("No draft social posts in queue.")
        return

    posted = 0
    for item in drafts:
        if posted >= MAX_POSTS_PER_RUN:
            break
        if posts_today + posted >= MAX_POSTS_PER_RUN:
            break

        message = format_social_post(item["content"], language)
        if not message:
            continue

        image_url = item.get("image_url")
        print(f"Publishing: {item['id']} ({language})")

        if image_url:
            result = post_photo(page_id, token, message, image_url)
        else:
            result = post_text(page_id, token, message)

        if result:
            item["status"] = "posted"
            item["posted_at"] = datetime.now().isoformat()
            item["fb_post_id"] = result.get("id") or result.get("post_id")

            post_log.append({
                "date": date.today().isoformat(),
                "timestamp": datetime.now().isoformat(),
                "queue_id": item["id"],
                "fb_post_id": item.get("fb_post_id"),
                "language": language,
                "topic": item.get("topic"),
            })

            posted += 1
            if posted < len(drafts):
                time.sleep(MIN_DELAY_BETWEEN_POSTS)
        else:
            item["status"] = "failed"
            item["failed_at"] = datetime.now().isoformat()

    save_json(QUEUE_FILE, queue)
    save_json(POST_LOG_FILE, post_log)
    print(f"\nPosted {posted} items. Total today: {posts_today + posted}")


def schedule_post(page_id: str, token: str, message: str, scheduled_time: int) -> dict | None:
    """Schedule a post for a future time (Unix timestamp, must be 10min-30days in future)."""
    url = f"{GRAPH_API_BASE}/{page_id}/feed"
    resp = requests.post(url, data={
        "message": message,
        "scheduled_publish_time": scheduled_time,
        "published": "false",
        "access_token": token,
    }, timeout=30)

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Scheduled: {data.get('id', 'unknown')} for {datetime.fromtimestamp(scheduled_time)}")
        return data
    else:
        print(f"  Error {resp.status_code}: {resp.text}")
        return None


def main():
    page_token = get_page_token()
    page_id = get_page_id()
    if not page_token or not page_id:
        sys.exit(1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Default to English posts; pass --lang es/fr/ru for other languages
    lang = "en"
    if len(sys.argv) > 1 and sys.argv[1] == "--lang" and len(sys.argv) > 2:
        lang = sys.argv[2]
        if lang not in ("en", "es", "fr", "ru"):
            print(f"Unsupported language: {lang}. Use en, es, fr, or ru.")
            sys.exit(1)

    print(f"Facebook Auto-Poster — Language: {lang}")
    publish_queue_items(page_id, page_token, lang)


if __name__ == "__main__":
    main()
