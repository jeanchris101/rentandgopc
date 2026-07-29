"""
Facebook Page Auto-Poster for Rent & Go PC.

Reads posts from content-queue.json (produced by content_generator.py),
publishes to Facebook Page via Graph API, tracks posted items, and logs activity.

Supports two queue formats:
  1. Content generator format: {id, type, topic, content: {en: {text, hashtags}, ...}, status}
  2. Direct format: {id, message, image_url, link, language, category, status}

Usage:
    python fb_autoposter.py              # Post next scheduled item
    python fb_autoposter.py --dry-run    # Preview without posting
    python fb_autoposter.py --status     # Show queue and log status
    python fb_autoposter.py --schedule   # Run in schedule mode (continuous)
    python fb_autoposter.py --lang en    # Post next item in specific language only
    python fb_autoposter.py --init       # Create sample queue for testing
    python fb_autoposter.py --verify     # Verify Facebook access token
"""

import json
import os
import re
import sys
import time
import logging
import argparse
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration (reads from config.json where available)
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = BASE_DIR / "config.json"
QUEUE_FILE = DATA_DIR / "content-queue.json"
LOG_FILE = DATA_DIR / "post-log.json"

# Load config.json if it exists
_config = {}
if CONFIG_FILE.exists():
    with open(CONFIG_FILE, "r", encoding="utf-8") as _f:
        _config = json.load(_f)

_fb_config = _config.get("facebook", {})
GRAPH_API_VERSION = _fb_config.get("api_version", "v25.0")
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Env var names from config (or defaults).
# .strip() because a secret pasted with a trailing newline is invisible in the
# CI log (the value is masked) and produces a "does not exist" Graph error that
# looks like a permissions problem.
FB_PAGE_ID = os.environ.get(_fb_config.get("page_id_env", "FB_PAGE_ID"), "").strip()
FB_PAGE_ACCESS_TOKEN = os.environ.get(
    _fb_config.get("access_token_env", "FB_PAGE_ACCESS_TOKEN"), ""
).strip()

# Schedule config
_schedule = _config.get("schedule", {})
POSTING_TIMES_ET = ["09:00", "12:00", "18:00"]

# Rate limits
_content_config = _config.get("content", {})
MAX_POSTS_PER_DAY = _content_config.get("max_posts_per_day", 3)
MIN_INTERVAL_SECONDS = 300  # 5 minutes minimum between posts

# After this many failed log entries for the same queue item, the item is
# marked "failed" in the queue so it stops blocking the head of the queue.
MAX_CONSECUTIVE_FAILURES = 3

# Languages to post (from config or default)
LANGUAGES = _content_config.get("languages", ["en", "es", "fr", "ru"])

# Graph API error codes (https://developers.facebook.com/docs/graph-api/guides/error-handling)
THROTTLE_ERROR_CODES = {80001, 4, 17, 613}   # rate limit / too many calls
POLICY_ERROR_CODE = 368                       # temporarily blocked for policy violation
DUPLICATE_ERROR_CODE = 506                    # duplicate post

# Max image size accepted before publishing (Graph rejects large photos)
MAX_IMAGE_BYTES = 4_000_000

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fb_autoposter")


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def load_json(path: Path, default=None):
    """Load JSON file, return default if missing or invalid."""
    if default is None:
        default = []
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        log.warning("Failed to parse %s, returning default", path)
        return default


def save_json(path: Path, data) -> None:
    """Save data to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def load_queue() -> list[dict]:
    """Load the content queue. Handles both list and dict formats."""
    data = load_json(QUEUE_FILE, [])
    if isinstance(data, dict):
        return data.get("posts", [])
    return data


def save_queue(queue: list[dict]) -> None:
    """Save the content queue (preserves original format)."""
    raw = load_json(QUEUE_FILE, [])
    if isinstance(raw, dict):
        raw["posts"] = queue
        save_json(QUEUE_FILE, raw)
    else:
        save_json(QUEUE_FILE, queue)


def load_post_log() -> list[dict]:
    """Load the post log."""
    data = load_json(LOG_FILE, {"entries": []})
    if isinstance(data, dict):
        return data.get("entries", [])
    return data


def save_post_log(entries: list[dict]) -> None:
    """Save the post log."""
    save_json(LOG_FILE, {"entries": entries})


def get_now_et() -> datetime:
    """Get current datetime in ET (EDT=-4, adjust to -5 for EST)."""
    return datetime.now(timezone.utc) + timedelta(hours=-4)


def get_today_str() -> str:
    return get_now_et().strftime("%Y-%m-%d")


def entry_date_et(entry: dict) -> str:
    """Date (ET) of a log entry whose timestamp was written in UTC.

    Log timestamps are stored with datetime.now(timezone.utc); comparing
    their raw date part against the ET "today" makes a post published
    20:00-00:00 ET count for the NEXT day and silently eats the next
    morning's slot. Convert to ET before comparing.
    """
    raw = entry.get("date", "")
    try:
        dt = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return str(raw)[:10]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt.astimezone(timezone.utc) + timedelta(hours=-4)).strftime("%Y-%m-%d")


def posts_today(entries: list[dict]) -> int:
    """Count posts made today (ET)."""
    today = get_today_str()
    return sum(
        1 for e in entries
        if e.get("status") == "posted" and entry_date_et(e) == today
    )


# ---------------------------------------------------------------------------
# Queue item normalization
#
# content_generator.py produces items like:
#   {id, type: "social_post", topic, content: {en: {text, hashtags}, ...}, status: "draft"}
#
# We normalize these into a flat posting format per language.
# ---------------------------------------------------------------------------


def normalize_queue_item(item: dict, lang: str) -> dict | None:
    """
    Normalize a queue item into a flat posting dict for a given language.

    Returns None if the item doesn't have content for this language or is
    not a social post.
    """
    # Already in flat/direct format (has "message" key)
    if "message" in item:
        if item.get("language", lang) != lang:
            return None
        return item

    # Content generator format: {content: {en: {text, hashtags}, ...}}
    content = item.get("content", {})
    lang_content = content.get(lang)
    if not lang_content:
        return None

    # Skip blog articles — they're not for Facebook posting
    if item.get("type") == "blog_article":
        return None

    text = lang_content.get("text", "")
    hashtags = lang_content.get("hashtags", [])

    if not text:
        return None

    # Assemble the message: text + hashtags
    message = text
    if hashtags:
        message += "\n\n" + " ".join(hashtags)

    return {
        "id": f"{item['id']}-{lang}",
        "source_id": item.get("id"),
        "message": message,
        "image_url": item.get("image_url", ""),
        "link": item.get("link", ""),
        "language": lang,
        "category": item.get("topic", item.get("category", "unknown")),
    }


def get_posted_ids(post_log: list[dict]) -> set[str]:
    """Get set of all successfully posted queue IDs."""
    return {
        e.get("queue_id")
        for e in post_log
        if e.get("status") == "posted" and e.get("queue_id")
    }


def count_failed(post_log: list[dict], queue_id: str) -> int:
    """Number of failed log entries recorded for a queue id."""
    return sum(
        1 for e in post_log
        if e.get("queue_id") == queue_id and e.get("status") == "failed"
    )


# Direct items whose date is older than this many days are considered stale and
# are never published: a property listing is evergreen, but posting "yesterday's"
# generated item as if it were today's — which happens if the poster was blocked
# (no token, throttle) for a stretch — floods the page with backdated posts the
# moment it recovers. Stale items are skipped in-place, not published.
STALE_POST_MAX_AGE_DAYS = 2

_DATE_IN_ID = re.compile(r"-(\d{4})-(\d{2})-(\d{2})-")


def _item_date(item: dict) -> "date | None":
    """Extract the YYYY-MM-DD embedded in a direct item's id, if present."""
    m = _DATE_IN_ID.search(item.get("id", ""))
    if not m:
        return None
    try:
        return datetime(int(m[1]), int(m[2]), int(m[3])).date()
    except ValueError:
        return None


def get_next_post(queue: list[dict], post_log: list[dict], lang: str | None = None) -> dict | None:
    """
    Get the next unposted item from the queue.
    Handles both direct and content-generator formats.

    Stale direct items (id date older than STALE_POST_MAX_AGE_DAYS) are skipped:
    they are marked "skip" by cmd_post's stale sweep before this runs, but the
    guard here is belt-and-suspenders in case that sweep is bypassed.
    """
    posted_ids = get_posted_ids(post_log)
    langs = [lang] if lang else LANGUAGES
    today = get_now_et().date()

    for item in queue:
        # Skip items already fully posted or explicitly marked
        if item.get("status") in ("posted", "failed", "skip"):
            continue

        # Skip stale direct items (generated on a prior day and never posted).
        d = _item_date(item) if "message" in item else None
        if d is not None and (today - d).days > STALE_POST_MAX_AGE_DAYS:
            continue

        for l in langs:
            flat = normalize_queue_item(item, l)
            if flat and flat["id"] not in posted_ids:
                return flat

    return None


# ---------------------------------------------------------------------------
# Facebook Graph API
# ---------------------------------------------------------------------------


def validate_credentials() -> bool:
    """Check that FB credentials are set."""
    if not FB_PAGE_ID:
        log.error("FB_PAGE_ID environment variable not set")
        return False
    if not FB_PAGE_ACCESS_TOKEN:
        log.error("FB_PAGE_ACCESS_TOKEN environment variable not set")
        return False
    return True


def verify_token() -> bool:
    """Check the token is live AND that it can actually reach FB_PAGE_ID.

    /me alone is not enough: a system user token answers it with the system
    user's own name, so it looks healthy even when FB_PAGE_ID is the wrong
    number or the Page was never assigned to that user. Both of those fail only
    at publish time, which for a cron job means a silent gap. So we also read
    the Page itself and report its real name back.
    """
    try:
        resp = requests.get(
            f"{GRAPH_API_BASE}/me",
            params={"access_token": FB_PAGE_ACCESS_TOKEN},
            timeout=10,
        )
        if resp.status_code != 200:
            log.error("Token verification failed: %s", resp.text)
            return False
        me = resp.json()
        log.info("Token identity: %s (ID: %s)", me.get("name"), me.get("id"))
    except requests.RequestException as e:
        log.error("Token verification request failed: %s", e)
        return False

    if not FB_PAGE_ID:
        log.error("FB_PAGE_ID is not set — cannot confirm Page access")
        return False

    try:
        resp = requests.get(
            f"{GRAPH_API_BASE}/{FB_PAGE_ID}",
            params={"fields": "id,name,category", "access_token": FB_PAGE_ACCESS_TOKEN},
            timeout=10,
        )
    except requests.RequestException as e:
        log.error("Page check request failed: %s", e)
        return False

    if resp.status_code != 200:
        err = _parse_graph_error(resp)
        log.error(
            "Token cannot reach Page %s — %s",
            FB_PAGE_ID, err.get("message") or resp.text,
        )
        # The value itself is masked in CI logs, so describe its SHAPE instead:
        # a trailing newline or a pasted label is invisible otherwise, and both
        # produce this same "does not exist" error.
        raw = os.environ.get("FB_PAGE_ID", "")
        log.error(
            "FB_PAGE_ID shape: length=%d, digits_only=%s, has_whitespace=%s, "
            "leading_or_trailing_space=%s",
            len(raw), raw.strip().isdigit(), any(c.isspace() for c in raw),
            raw != raw.strip(),
        )
        # Which of the two causes is it? Listing the Pages this token *can*
        # reach separates "wrong FB_PAGE_ID" from "Page never assigned". Page
        # IDs are public information, so printing them here is safe.
        try:
            acc = requests.get(
                f"{GRAPH_API_BASE}/me/accounts",
                params={"fields": "id,name", "access_token": FB_PAGE_ACCESS_TOKEN},
                timeout=10,
            )
            if acc.status_code == 200:
                pages = acc.json().get("data", [])
                if pages:
                    log.error("This token CAN reach these Pages — use one of these IDs as FB_PAGE_ID:")
                    for p in pages:
                        log.error("    %s  ->  %s", p.get("id"), p.get("name"))
                else:
                    log.error(
                        "This token can reach NO Pages at all. In Business settings -> "
                        "Users -> System users -> rentandgo-bot -> Add assets -> Pages, "
                        "assign the Page and enable the 'Manage Page' / 'Create content' task."
                    )
            else:
                log.error(
                    "Could not list Pages either (%s). The token is likely missing the "
                    "pages_show_list permission — regenerate it with pages_show_list, "
                    "pages_read_engagement and pages_manage_posts checked.",
                    _parse_graph_error(acc).get("message") or acc.text,
                )
        except requests.RequestException as e:
            log.error("Page listing request failed: %s", e)
        return False

    page = resp.json()
    log.info("Page reachable: %s (ID: %s, %s)",
             page.get("name"), page.get("id"), page.get("category"))
    return True


def _to_int(value) -> int | None:
    """Coerce a value to int, returning None when not possible."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_graph_error(resp: requests.Response) -> dict:
    """
    Extract the Graph API error object from a response body.

    Returns {} when the body has no "error" key; otherwise a dict with
    keys: code (int | None), subcode (int | None), message (str), type (str).
    """
    try:
        error = resp.json().get("error", {})
    except (ValueError, AttributeError):
        return {}
    if not error:
        return {}
    return {
        "code": _to_int(error.get("code")),
        "subcode": _to_int(error.get("error_subcode")),
        "message": error.get("message", ""),
        "type": error.get("type", ""),
    }


def _log_usage_header(resp: requests.Response) -> None:
    """Log the X-Business-Use-Case-Usage header when Facebook returns it."""
    usage = resp.headers.get("X-Business-Use-Case-Usage")
    if usage:
        log.info("X-Business-Use-Case-Usage: %s", usage)


def _graph_error_result(graph_error: dict) -> dict:
    """Convert a parsed Graph error into the {error: ...} result shape."""
    return {
        "error": graph_error["message"] or "Unknown Graph API error",
        "error_code": graph_error["code"],
        "error_subcode": graph_error["subcode"],
    }


def classify_graph_error(result: dict) -> str:
    """
    Classify a publish() result into an action for cmd_post.

    Returns one of:
      "ok"        — no error
      "throttle"  — rate limited (codes 80001, 4, 17, 613): abort the run
      "policy"    — policy violation (code 368): mark failed, abort the run
      "duplicate" — duplicate post (code 506): mark skip, try next item
      "gone"      — target object no longer exists: abort the run
      "failed"    — any other error: mark failed, stop normally
    """
    if "error" not in result:
        return "ok"
    code = result.get("error_code")
    subcode = result.get("error_subcode")
    message = (result.get("error") or "").lower()
    if code in THROTTLE_ERROR_CODES:
        return "throttle"
    if code == POLICY_ERROR_CODE:
        return "policy"
    if code == DUPLICATE_ERROR_CODE:
        return "duplicate"
    if (code == 100 and subcode == 33) or (code == 10 and "does not exist" in message):
        return "gone"
    return "failed"


def assert_images_public(urls: list[str]) -> str | None:
    """
    Verify image URLs are publicly reachable before hitting the Graph API.

    Sends a HEAD request to each URL and requires HTTP 200 with a numeric
    Content-Length below MAX_IMAGE_BYTES. Returns None when every URL passes,
    or a description of the first failure. The caller records the failure in
    the post log (so a broken image leaves a trace and stops blocking the
    queue after MAX_CONSECUTIVE_FAILURES) and exits 1, so a broken image
    never reaches Facebook.
    """
    for url in urls:
        try:
            resp = requests.head(url, timeout=15, allow_redirects=True)
        except requests.RequestException as e:
            return f"Image URL check failed ({url}): {e}"
        if resp.status_code != 200:
            return f"Image URL not public (HTTP {resp.status_code}): {url}"
        content_length = _to_int(resp.headers.get("Content-Length"))
        if content_length is None or content_length >= MAX_IMAGE_BYTES:
            return (
                f"Image Content-Length missing or >= {MAX_IMAGE_BYTES} bytes "
                f"(got {resp.headers.get('Content-Length')}): {url}"
            )
    log.info("Image check passed for %d URL(s).", len(urls))
    return None


def fb_post_text(message: str) -> dict:
    """POST /{page-id}/feed — text only."""
    url = f"{GRAPH_API_BASE}/{FB_PAGE_ID}/feed"
    payload = {"message": message, "access_token": FB_PAGE_ACCESS_TOKEN}
    resp = requests.post(url, data=payload, timeout=30)
    _log_usage_header(resp)
    graph_error = _parse_graph_error(resp)
    if graph_error:
        return _graph_error_result(graph_error)
    resp.raise_for_status()
    return resp.json()


def fb_post_photo(message: str, image_url: str) -> dict:
    """POST /{page-id}/photos — image from URL with caption."""
    url = f"{GRAPH_API_BASE}/{FB_PAGE_ID}/photos"
    payload = {"message": message, "url": image_url, "access_token": FB_PAGE_ACCESS_TOKEN}
    resp = requests.post(url, data=payload, timeout=60)
    _log_usage_header(resp)
    graph_error = _parse_graph_error(resp)
    if graph_error:
        return _graph_error_result(graph_error)
    resp.raise_for_status()
    return resp.json()


def fb_post_link(message: str, link: str) -> dict:
    """POST /{page-id}/feed — text with link attachment."""
    url = f"{GRAPH_API_BASE}/{FB_PAGE_ID}/feed"
    payload = {"message": message, "link": link, "access_token": FB_PAGE_ACCESS_TOKEN}
    resp = requests.post(url, data=payload, timeout=30)
    _log_usage_header(resp)
    graph_error = _parse_graph_error(resp)
    if graph_error:
        return _graph_error_result(graph_error)
    resp.raise_for_status()
    return resp.json()


def publish(post_data: dict, dry_run: bool = False) -> dict:
    """Publish a normalized post to Facebook. Returns {id: ...} or {error: ...}."""
    message = post_data.get("message", "").strip()
    image_url = post_data.get("image_url", "").strip()
    link = post_data.get("link", "").strip()

    if not message:
        return {"error": "Empty message"}

    if dry_run:
        log.info("[DRY RUN] Would post (%s / %s):", post_data.get("language"), post_data.get("category"))
        log.info("[DRY RUN] %s", message[:120].replace("\n", " "))
        if image_url:
            log.info("[DRY RUN] Image: %s", image_url[:80])
        if link:
            log.info("[DRY RUN] Link: %s", link[:80])
        return {"id": "dry-run"}

    try:
        if image_url:
            # The message already contains any link (wa.me etc.). The Graph
            # photos endpoint drops a separate link param when an image is
            # attached, so we intentionally never pass one here.
            log.info("Posting photo (%s)", post_data.get("language"))
            return fb_post_photo(message, image_url)
        elif link:
            log.info("Posting with link (%s)", post_data.get("language"))
            return fb_post_link(message, link)
        else:
            log.info("Posting text (%s)", post_data.get("language"))
            return fb_post_text(message)
    except requests.HTTPError as e:
        # Graph JSON errors are parsed in fb_post_*; this catches non-JSON
        # HTTP failures (proxies, HTML error pages, etc.).
        log.error("FB API HTTP error: %s", e)
        return {"error": str(e)}
    except requests.RequestException as e:
        log.error("Request failed: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Post log helpers
# ---------------------------------------------------------------------------


def append_log(post_log: list, post_data: dict, result: dict, status: str) -> list:
    """Append an entry to the post log."""
    post_log.append({
        "date": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "queue_id": post_data.get("id"),
        "source_id": post_data.get("source_id", post_data.get("id")),
        "language": post_data.get("language", "unknown"),
        "category": post_data.get("category", "unknown"),
        "fb_post_id": result.get("id") or result.get("post_id"),
        "message_preview": post_data.get("message", "")[:120],
        "had_image": bool(post_data.get("image_url")),
        "had_link": bool(post_data.get("link")),
        "error": result.get("error"),
        "error_code": result.get("error_code"),
        "error_subcode": result.get("error_subcode"),
    })
    return post_log


def mark_queue_item(queue: list, source_id: str, status: str, **extra) -> list:
    """Update the status of a queue item by its original ID."""
    for item in queue:
        if item.get("id") == source_id:
            item["status"] = status
            item.update(extra)
            break
    return queue


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_post(dry_run: bool = False, lang: str | None = None) -> None:
    """Post the next item from the queue."""
    if not dry_run:
        if not validate_credentials():
            sys.exit(1)
        if not verify_token():
            log.error("Access token verification failed. Aborting.")
            sys.exit(2)

        # Fail closed on a corrupt post log: falling back to an empty history
        # would wipe the dedup / daily-limit protections and re-publish every
        # historic item, one per run.
        if LOG_FILE.exists():
            try:
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    json.load(f)
            except (json.JSONDecodeError, IOError):
                log.error(
                    "%s exists but cannot be parsed. Posting with an empty "
                    "history would re-publish old items - fix or restore the "
                    "file first. Aborting.", LOG_FILE,
                )
                sys.exit(1)

    queue = load_queue()
    post_log = load_post_log()

    if not queue:
        log.info("Queue is empty. Run content_generator.py first or use --init.")
        return

    # Daily limit check
    today_count = posts_today(post_log)
    if today_count >= MAX_POSTS_PER_DAY and not dry_run:
        log.warning("Daily limit reached (%d/%d). Try tomorrow.", today_count, MAX_POSTS_PER_DAY)
        return

    # Minimum interval check
    if not dry_run:
        posted_entries = [e for e in post_log if e.get("status") == "posted"]
        if posted_entries:
            last_time = datetime.fromisoformat(posted_entries[-1]["date"])
            elapsed = (datetime.now(timezone.utc) - last_time).total_seconds()
            if elapsed < MIN_INTERVAL_SECONDS:
                log.warning("Too soon. Wait %d seconds.", int(MIN_INTERVAL_SECONDS - elapsed))
                return

    # Find and publish the next post. Duplicates (Graph code 506) are marked
    # "skip" and we move on to the next candidate; throttle, policy and
    # gone-object errors abort the entire run.
    changed = False

    while True:
        post_data = get_next_post(queue, post_log, lang=lang)
        if not post_data:
            log.info("No pending posts in queue%s.", f" for lang={lang}" if lang else "")
            break

        log.info("Publishing: %s [%s / %s]",
                 post_data["id"], post_data.get("language"), post_data.get("category"))

        source_id = post_data.get("source_id", post_data.get("id"))

        if not dry_run and post_data.get("image_url", "").strip():
            image_error = assert_images_public([post_data["image_url"].strip()])
            if image_error:
                # Leave a trace in the post log so the failure is diagnosable
                # and the item stops blocking the queue after repeated runs.
                post_log = append_log(post_log, post_data, {"error": image_error}, "failed")
                if count_failed(post_log, post_data["id"]) >= MAX_CONSECUTIVE_FAILURES:
                    queue = mark_queue_item(queue, source_id, "failed")
                    log.error("Item %s failed %d times - marked failed in the queue.",
                              source_id, MAX_CONSECUTIVE_FAILURES)
                save_queue(queue)
                save_post_log(post_log)
                log.error("%s - aborting run.", image_error)
                sys.exit(1)

        result = publish(post_data, dry_run=dry_run)

        if dry_run:
            log.info("[DRY RUN] Complete.")
            return

        action = classify_graph_error(result)

        if action == "throttle":
            post_log = append_log(post_log, post_data, result, "failed")
            save_queue(queue)
            save_post_log(post_log)
            log.error("Graph API throttle (code %s): %s — aborting run.",
                      result.get("error_code"), result.get("error"))
            sys.exit(1)

        if action == "policy":
            queue = mark_queue_item(queue, source_id, "failed")
            post_log = append_log(post_log, post_data, result, "failed")
            save_queue(queue)
            save_post_log(post_log)
            log.critical("Policy violation (code 368): %s — item %s marked failed. Aborting run.",
                         result.get("error"), source_id)
            sys.exit(1)

        if action == "gone":
            post_log = append_log(post_log, post_data, result, "failed")
            save_queue(queue)
            save_post_log(post_log)
            log.error("Target object no longer exists (code %s, subcode %s): %s — aborting run.",
                      result.get("error_code"), result.get("error_subcode"), result.get("error"))
            sys.exit(1)

        if action == "duplicate":
            queue = mark_queue_item(queue, source_id, "skip")
            post_log = append_log(post_log, post_data, result, "skip")
            changed = True
            log.warning("Duplicate post (code 506): %s marked skip. Trying next item.", source_id)
            continue

        if action == "failed":
            # Exit non-zero so the workflow run goes red: a silent break would
            # leave the pipeline stuck (item still pending at the head of the
            # queue) with weeks of green runs and zero posts. After
            # MAX_CONSECUTIVE_FAILURES the item is marked failed so the next
            # run moves on to the next item instead of retrying forever.
            post_log = append_log(post_log, post_data, result, "failed")
            if count_failed(post_log, post_data["id"]) >= MAX_CONSECUTIVE_FAILURES:
                queue = mark_queue_item(queue, source_id, "failed")
                log.error("Item %s failed %d times - marked failed in the queue.",
                          source_id, MAX_CONSECUTIVE_FAILURES)
            save_queue(queue)
            save_post_log(post_log)
            log.error("Failed: %s - aborting run.", result.get("error"))
            sys.exit(1)

        # Success
        fb_id = result.get("id") or result.get("post_id", "")
        post_log = append_log(post_log, post_data, result, "posted")
        changed = True
        log.info("Success. FB Post ID: %s", fb_id)

        original = next((q for q in queue if q.get("id") == source_id), None)
        if original is not None and "message" in original:
            # Direct-format items carry a single language: one successful post
            # completes them. (The multi-language check below would never
            # match their ids and would leave them pending forever.)
            queue = mark_queue_item(queue, source_id, "posted",
                                    posted_at=datetime.now(timezone.utc).isoformat())
        else:
            # Generator format: check if all languages are posted for this item
            posted_ids = get_posted_ids(post_log)
            all_langs_done = all(
                f"{source_id}-{l}" in posted_ids or normalize_queue_item(
                    original or {}, l
                ) is None
                for l in LANGUAGES
            )
            if all_langs_done:
                queue = mark_queue_item(queue, source_id, "posted",
                                        posted_at=datetime.now(timezone.utc).isoformat())
        break

    if changed:
        save_queue(queue)
        save_post_log(post_log)
        log.info("Queue and log saved.")


def cmd_status() -> None:
    """Show queue and log status."""
    queue = load_queue()
    post_log = load_post_log()

    total = len(queue)
    pending = sum(1 for p in queue if p.get("status") in (None, "pending", "draft", "scheduled"))
    posted = sum(1 for p in queue if p.get("status") == "posted")
    failed = sum(1 for p in queue if p.get("status") == "failed")

    print(f"\n--- Queue ({QUEUE_FILE}) ---")
    print(f"  Total items:   {total}")
    print(f"  Pending/Draft: {pending}")
    print(f"  Posted:        {posted}")
    print(f"  Failed:        {failed}")

    today_count = posts_today(post_log)
    print(f"\n--- Today ({get_today_str()}) ---")
    print(f"  Posts today:   {today_count}/{MAX_POSTS_PER_DAY}")

    print(f"\n--- Post Log ({LOG_FILE}) ---")
    print(f"  Total entries: {len(post_log)}")
    if post_log:
        last = post_log[-1]
        print(f"  Last post:     {last.get('date', 'N/A')}")
        print(f"  Last status:   {last.get('status', 'N/A')}")
        print(f"  Last preview:  {last.get('message_preview', 'N/A')[:60]}...")

    # Languages posted today
    today = get_today_str()
    today_langs = [e.get("language") for e in post_log
                   if e.get("status") == "posted" and entry_date_et(e) == today]
    if today_langs:
        print(f"  Languages:     {', '.join(today_langs)}")

    # Next up
    next_post = get_next_post(queue, post_log)
    if next_post:
        print(f"\n--- Next Up ---")
        print(f"  ID:       {next_post.get('id')}")
        print(f"  Language: {next_post.get('language')}")
        print(f"  Category: {next_post.get('category')}")
        print(f"  Preview:  {next_post.get('message', '')[:80]}...")
    else:
        print("\n  No pending posts.")
    print()


def cmd_schedule() -> None:
    """Run in continuous schedule mode, posting at configured times."""
    if not validate_credentials():
        sys.exit(1)
    if not verify_token():
        log.error("Token invalid. Check FB_PAGE_ACCESS_TOKEN.")
        sys.exit(1)

    log.info("Schedule mode started. Posting times (ET): %s", POSTING_TIMES_ET)
    log.info("Press Ctrl+C to stop.\n")

    posted_slots: set[str] = set()

    while True:
        try:
            now = get_now_et()
            current_time = now.strftime("%H:%M")
            current_date = now.strftime("%Y-%m-%d")
            slot_key = f"{current_date}_{current_time}"

            # Reset on new day
            if not any(s.startswith(current_date) for s in posted_slots) and posted_slots:
                posted_slots.clear()
                log.info("New day. Cleared posted slots.")

            if current_time in POSTING_TIMES_ET and slot_key not in posted_slots:
                log.info("Posting slot: %s ET", current_time)
                cmd_post(dry_run=False)
                posted_slots.add(slot_key)

            time.sleep(60)

        except KeyboardInterrupt:
            log.info("Schedule mode stopped.")
            break


def cmd_init_sample() -> None:
    """Create a sample content-queue.json matching content_generator.py output format."""
    if QUEUE_FILE.exists():
        existing = load_queue()
        if existing:
            log.warning("Queue already has %d items. Use --status to see them.", len(existing))
            return

    sample = [
        {
            "id": f"social-{get_today_str()}-lifestyle",
            "type": "social_post",
            "topic": "lifestyle",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "draft",
            "content": {
                "en": {
                    "text": "This is what your morning looks like at Cocotal Golf:\n\n7:00 AM - Coffee on your terrace, golf course below\n8:30 AM - Walk to Melia Hotel for a swim\n10:00 AM - Beach day at Melia's private beach\n\nThis isn't a vacation. This is your daily life.\n\n2BR, 144 sqm. $315,000. DM me to see the property.",
                    "hashtags": ["#PuntaCana", "#RealEstate", "#CocotalGolf", "#Caribbean"]
                },
                "es": {
                    "text": "Asi se ve tu manana en Cocotal Golf:\n\n7:00 AM - Cafe en tu terraza con vista al golf\n8:30 AM - Caminas al Hotel Melia para la piscina\n10:00 AM - Dia de playa en la playa del Melia\n\nEsto no es una vacacion. Es tu vida diaria.\n\n2 hab, 144 m2. US$315,000. Escribeme.",
                    "hashtags": ["#PuntaCana", "#BienesRaices", "#CocotalGolf", "#Caribe"]
                },
                "fr": {
                    "text": "Voici a quoi ressemble ton matin a Cocotal Golf:\n\n7h00 - Cafe sur ta terrasse, vue sur le golf\n8h30 - Marche jusqu'au Melia pour la piscine\n10h00 - Journee plage au Melia\n\nC'est pas des vacances. C'est ta vie.\n\nCondo 2 chambres, 144 m2. US$315,000. Ecris-moi.",
                    "hashtags": ["#PuntaCana", "#Immobilier", "#CocotalGolf", "#Caraibes"]
                },
                "ru": {
                    "text": "Vot kak vyglyadit vashe utro v Cocotal Golf:\n\n7:00 - Kofe na terrasse, vid na golf\n8:30 - Progulka do Melia, kupanie v bassejne\n10:00 - Den na plyazhe Melia\n\nEto ne otpusk. Eto vasha zhizn.\n\n2 spalni, 144 kv.m. US$315,000. Napishite.",
                    "hashtags": ["#PuntaCana", "#Nedvizhimost", "#CocotalGolf", "#Kariby"]
                }
            }
        },
        {
            "id": f"social-{get_today_str()}-roi",
            "type": "social_post",
            "topic": "roi",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "draft",
            "content": {
                "en": {
                    "text": "Your tenants pay your mortgage while you sleep.\n\nPeak season: $180-250/night, 85%+ occupancy\nLow season: $120-150/night, 60% occupancy\n\nNet annual income: $21,000-$31,500\nThat's 6.7-10% NET on a $315K property.\n\nWant the full projection? DM me.",
                    "hashtags": ["#PuntaCana", "#RealEstateInvesting", "#AirbnbHost", "#PassiveIncome"]
                },
                "es": {
                    "text": "Tus huespedes pagan tu hipoteca mientras duermes.\n\nTemporada alta: $180-250/noche, 85%+ ocupacion\nBaja: $120-150/noche, 60% ocupacion\n\nIngreso neto anual: $21,000-$31,500\nEso es 6.7-10% NETO sobre US$315,000.\n\nQuieres la proyeccion? Escribeme.",
                    "hashtags": ["#PuntaCana", "#Inversiones", "#Airbnb", "#IngresosPasivos"]
                },
                "fr": {
                    "text": "Tes locataires payent ton hypotheque pendant que tu dors.\n\nHaute saison: $180-250/nuit, 85%+ occupation\nBasse saison: $120-150/nuit, 60% occupation\n\nRevenu net annuel: $21,000-$31,500\nCa fait 6.7-10% NET sur US$315,000.\n\nTu veux la projection? Ecris-moi.",
                    "hashtags": ["#PuntaCana", "#Investissement", "#Airbnb", "#RevenusPassifs"]
                },
                "ru": {
                    "text": "Vashi arendatory platyat ipoteku poka vy spite.\n\nVysokij sezon: $180-250/noch, 85%+ zagruzka\nNizkij: $120-150/noch, 60% zagruzka\n\nChistyj godovoj dohod: $21,000-$31,500\nEto 6.7-10% CHISTO na US$315,000.\n\nHotite proektsiyu? Napishite.",
                    "hashtags": ["#PuntaCana", "#Investitsii", "#Airbnb", "#PassivnyjDohod"]
                }
            }
        }
    ]

    save_json(QUEUE_FILE, sample)
    log.info("Created sample queue with %d items at %s", len(sample), QUEUE_FILE)
    log.info("Each item has 4 language variants (EN/ES/FR/RU).")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Facebook Page Auto-Poster — Rent & Go PC"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview next post without publishing")
    parser.add_argument("--status", action="store_true",
                        help="Show queue and posting status")
    parser.add_argument("--schedule", action="store_true",
                        help="Run in continuous schedule mode")
    parser.add_argument("--init", action="store_true",
                        help="Create sample content-queue.json")
    parser.add_argument("--verify", action="store_true",
                        help="Verify Facebook Page access token")
    parser.add_argument("--lang", type=str, default=None,
                        choices=["en", "es", "fr", "ru"],
                        help="Post only in this language")

    args = parser.parse_args()

    if args.init:
        cmd_init_sample()
    elif args.status:
        cmd_status()
    elif args.verify:
        # Exit non-zero on failure: without this the CI step goes green on a
        # broken token, which is the exact silent success we are trying to
        # avoid by having a verify mode at all.
        if not validate_credentials() or not verify_token():
            sys.exit(1)
    elif args.schedule:
        cmd_schedule()
    else:
        cmd_post(dry_run=args.dry_run, lang=args.lang)


if __name__ == "__main__":
    main()
