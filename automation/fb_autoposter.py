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
import sys
import time
import logging
import argparse
from datetime import datetime, timezone, timedelta
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
GRAPH_API_VERSION = _fb_config.get("api_version", "v21.0")
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Env var names from config (or defaults)
FB_PAGE_ID = os.environ.get(_fb_config.get("page_id_env", "FB_PAGE_ID"), "")
FB_PAGE_ACCESS_TOKEN = os.environ.get(
    _fb_config.get("access_token_env", "FB_PAGE_ACCESS_TOKEN"), ""
)

# Schedule config
_schedule = _config.get("schedule", {})
POSTING_TIMES_ET = ["09:00", "12:00", "18:00"]

# Rate limits
_content_config = _config.get("content", {})
MAX_POSTS_PER_DAY = _content_config.get("max_posts_per_day", 3)
MIN_INTERVAL_SECONDS = 300  # 5 minutes minimum between posts

# Languages to post (from config or default)
LANGUAGES = _content_config.get("languages", ["en", "es", "fr", "ru"])

# Default link to append if post has none
DEFAULT_SITE_LINK = "https://rentandgopc.com"

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


def posts_today(entries: list[dict]) -> int:
    """Count posts made today."""
    today = get_today_str()
    return sum(
        1 for e in entries
        if e.get("date", "").startswith(today) and e.get("status") == "posted"
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


def get_next_post(queue: list[dict], post_log: list[dict], lang: str | None = None) -> dict | None:
    """
    Get the next unposted item from the queue.
    Handles both direct and content-generator formats.
    """
    posted_ids = get_posted_ids(post_log)
    langs = [lang] if lang else LANGUAGES

    for item in queue:
        # Skip items already fully posted or explicitly marked
        if item.get("status") in ("posted", "failed", "skip"):
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
    """Verify the page access token is valid."""
    url = f"{GRAPH_API_BASE}/me"
    params = {"access_token": FB_PAGE_ACCESS_TOKEN}
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            log.info("Token valid. Page: %s (ID: %s)", data.get("name"), data.get("id"))
            return True
        log.error("Token verification failed: %s", resp.text)
        return False
    except requests.RequestException as e:
        log.error("Token verification request failed: %s", e)
        return False


def fb_post_text(message: str) -> dict:
    """POST /{page-id}/feed — text only."""
    url = f"{GRAPH_API_BASE}/{FB_PAGE_ID}/feed"
    payload = {"message": message, "access_token": FB_PAGE_ACCESS_TOKEN}
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fb_post_photo(message: str, image_url: str) -> dict:
    """POST /{page-id}/photos — image from URL with caption."""
    url = f"{GRAPH_API_BASE}/{FB_PAGE_ID}/photos"
    payload = {"message": message, "url": image_url, "access_token": FB_PAGE_ACCESS_TOKEN}
    resp = requests.post(url, data=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def fb_post_link(message: str, link: str) -> dict:
    """POST /{page-id}/feed — text with link attachment."""
    url = f"{GRAPH_API_BASE}/{FB_PAGE_ID}/feed"
    payload = {"message": message, "link": link, "access_token": FB_PAGE_ACCESS_TOKEN}
    resp = requests.post(url, data=payload, timeout=30)
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
            log.info("Posting photo (%s)", post_data.get("language"))
            return fb_post_photo(message, image_url)
        elif link:
            log.info("Posting with link (%s)", post_data.get("language"))
            return fb_post_link(message, link)
        else:
            log.info("Posting text (%s)", post_data.get("language"))
            return fb_post_text(message)
    except requests.HTTPError as e:
        error_msg = str(e)
        try:
            error_msg = e.response.json().get("error", {}).get("message", error_msg)
        except (ValueError, AttributeError):
            pass
        log.error("FB API error: %s", error_msg)
        return {"error": error_msg}
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
    if not dry_run and not validate_credentials():
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

    # Find next post
    post_data = get_next_post(queue, post_log, lang=lang)
    if not post_data:
        log.info("No pending posts in queue%s.", f" for lang={lang}" if lang else "")
        return

    log.info("Publishing: %s [%s / %s]",
             post_data["id"], post_data.get("language"), post_data.get("category"))

    result = publish(post_data, dry_run=dry_run)

    if dry_run:
        log.info("[DRY RUN] Complete.")
        return

    # Log and update queue
    source_id = post_data.get("source_id", post_data.get("id"))
    if "error" in result:
        post_log = append_log(post_log, post_data, result, "failed")
        log.error("Failed: %s", result["error"])
    else:
        fb_id = result.get("id") or result.get("post_id", "")
        post_log = append_log(post_log, post_data, result, "posted")
        log.info("Success. FB Post ID: %s", fb_id)

        # Check if all languages are posted for this source item
        posted_ids = get_posted_ids(post_log)
        all_langs_done = all(
            f"{source_id}-{l}" in posted_ids or normalize_queue_item(
                next((q for q in queue if q.get("id") == source_id), {}), l
            ) is None
            for l in LANGUAGES
        )
        if all_langs_done:
            queue = mark_queue_item(queue, source_id, "posted",
                                     posted_at=datetime.now(timezone.utc).isoformat())

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
    today_langs = [e.get("language") for e in post_log if e.get("date", "").startswith(today) and e.get("status") == "posted"]
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
        if validate_credentials():
            verify_token()
    elif args.schedule:
        cmd_schedule()
    else:
        cmd_post(dry_run=args.dry_run, lang=args.lang)


if __name__ == "__main__":
    main()
