"""
Deterministic daily queue builder for Rent & Go PC.

Selects one property, language, template style and image per day (all derived
from the target date and the posting history) and appends a DIRECT-format item
to content-queue.json — the item carries a "message" key, so
fb_autoposter.normalize_queue_item() publishes it untouched.

Rules:
  - Property: least recently published according to post-log.json, with a
    14-day cooldown per property. Still-pending queue items count toward the
    cooldown too, so a poster outage cannot re-queue a property early. If
    every active property is inside the cooldown window, a
    {"starved": true, ...} entry is written to the log (once per date) and
    the run exits 0 without queueing anything. The cooldown is never relaxed
    silently.
  - Language: rotates en/es/fr by date (config.json content.languages).
    Highlights and neighborhood come from the per-language fields in
    properties.json (highlights_es/fr, neighborhood_es/fr) with fallback to
    the English values, so es/fr posts never mix in English bullets.
  - Style: deterministic templates in data/post-templates.json (no LLM),
    rotated by date. A style may restrict itself to property types via
    "types" (daily_life is condo-only); the rotation advances to the next
    style when the day's property is not allowed. All figures come from
    properties.json placeholders. CONFOTUR highlights are dropped unless the
    property has confotur == true.
  - Image: rotates inside the property's post_images[]; the same image is not
    reused for the same property within 30 days (state in image-rotation.json,
    updated when the item is queued — accepted tradeoff: an item that later
    ends up skip/failed still burns its image for the window; the fallback in
    select_image covers exhaustion with an explicit warning).
  - The wa.me link (per-language prefilled message carrying the tracking ref)
    is embedded at the END of the message. The "link" field stays empty:
    publish() drops the link when an image is attached, so it must travel
    inside the message.
  - Old content-generator items (no "message" key) in the queue are ignored,
    never deleted.

Usage:
    python build_queue.py                    # queue today's item (ET)
    python build_queue.py --dry-run          # preview without writing
    python build_queue.py --date 2026-07-23  # build for a specific date
"""

import argparse
import json
import logging
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

# ---------------------------------------------------------------------------
# Configuration (reads from config.json where available)
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = BASE_DIR / "config.json"
QUEUE_FILE = DATA_DIR / "content-queue.json"
LOG_FILE = DATA_DIR / "post-log.json"
PROPERTIES_FILE = DATA_DIR / "properties.json"
TEMPLATES_FILE = DATA_DIR / "post-templates.json"
IMAGE_ROTATION_FILE = DATA_DIR / "image-rotation.json"

COOLDOWN_DAYS = 4         # min days between two posts of the same property.
                          # Owner decision 2026-07-21: daily posting with 5 active
                          # properties requires cooldown <= 4 (14 would starve the
                          # queue 9 days out of every 14). Style x language x image
                          # rotation (15 combos/property) keeps repeats non-identical.
IMAGE_REUSE_DAYS = 30     # min days before reusing an image for a property

# Tracking ref: RG-<PROP>-F<base36 of YYMMDD>. F = organic Page post.
REF_SOURCE = "F"
REF_CODES = {
    "cocotal-2bdr": "A301",
    "paseo-cocotal": "PB202",
    "karen-los-corales": "KLC1",
    "land-autovia-este": "LAUT",
    "land-cepm-vistacana": "LCEP",
}

# Short prefilled WhatsApp message per language (urlencoded into the wa.me link)
WA_PREFILL = {
    "en": "Hi! I'm interested in {short_name} ({price}). (Ref: {ref})",
    "es": "Hola! Me interesa {short_name} ({price}). (Ref: {ref})",
    "fr": "Bonjour! Je m'interesse a {short_name} ({price}). (Ref: {ref})",
}

ALLOWED_PLACEHOLDERS = {"name", "price", "neighborhood", "highlight_1", "highlight_2", "wa_link"}
PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")

# Load config.json if it exists
_config = {}
if CONFIG_FILE.exists():
    with open(CONFIG_FILE, "r", encoding="utf-8") as _f:
        _config = json.load(_f)

LANGUAGES = _config.get("content", {}).get("languages", ["en", "es", "fr"])

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("build_queue")


# ---------------------------------------------------------------------------
# Data helpers (same file formats as fb_autoposter.py)
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


def get_today_et() -> date:
    """Current date in ET (same clock as fb_autoposter)."""
    return (datetime.now(timezone.utc) + timedelta(hours=-4)).date()


def parse_iso_date(value) -> date | None:
    """Parse the date part of an ISO string; None if missing or invalid."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Tracking ref and wa.me link
# ---------------------------------------------------------------------------


def to_base36(n: int) -> str:
    """Encode a non-negative integer in base36 (uppercase)."""
    digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if n == 0:
        return "0"
    out = []
    while n:
        n, r = divmod(n, 36)
        out.append(digits[r])
    return "".join(reversed(out))


def build_ref(slug: str, target_date: date) -> str:
    """RG-<PROP>-F<base36 of YYMMDD>: property code + source F (organic Page)."""
    return f"RG-{REF_CODES[slug]}-{REF_SOURCE}{to_base36(int(target_date.strftime('%y%m%d')))}"


def build_wa_link(prop: dict, lang: str, ref: str, wa_number: str) -> str:
    """wa.me link with a short prefilled message carrying the tracking ref."""
    prefill = WA_PREFILL.get(lang, WA_PREFILL["en"]).format(
        short_name=prop.get("short_name", prop.get("name", "")),
        price=prop.get("price_display", ""),
        ref=ref,
    )
    return f"https://wa.me/{wa_number}?text={quote(prefill, safe='')}"


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def load_templates() -> list[dict]:
    """Load and validate post-templates.json. Exits on any invalid template."""
    data = load_json(TEMPLATES_FILE, {})
    styles = data.get("styles", []) if isinstance(data, dict) else []
    if not styles:
        log.error("No styles found in %s", TEMPLATES_FILE)
        sys.exit(1)

    for style in styles:
        for lang, text in style.get("templates", {}).items():
            found = set(PLACEHOLDER_RE.findall(text))
            unknown = found - ALLOWED_PLACEHOLDERS
            if unknown:
                log.error("Style %r (%s) uses unknown placeholders: %s",
                          style.get("id"), lang, ", ".join(sorted(unknown)))
                sys.exit(1)
            if "wa_link" not in found:
                log.error("Style %r (%s) is missing the {wa_link} placeholder",
                          style.get("id"), lang)
                sys.exit(1)
    return styles


def pick_highlights(prop: dict, target_date: date, lang: str) -> tuple[str, str]:
    """Two date-rotated highlights in the post's language.

    Uses highlights_<lang> (a parallel translation of highlights) when
    present, falling back to the English list, so es/fr posts never carry
    English bullets. CONFOTUR lines only if confotur == true.
    """
    source = prop.get(f"highlights_{lang}") or prop.get("highlights", [])
    highlights = [
        h for h in source
        if prop.get("confotur") is True or "confotur" not in h.lower()
    ]
    if len(highlights) < 2:
        log.error("Property %s needs at least 2 usable highlights (lang=%s)",
                  prop.get("slug"), lang)
        sys.exit(1)
    i = target_date.toordinal() % len(highlights)
    return highlights[i], highlights[(i + 1) % len(highlights)]


def select_style(styles: list[dict], prop: dict, target_date: date) -> dict:
    """Date-rotated style, skipping styles not suited to the property type.

    A style may declare "types" (e.g. ["condo"]); when the day's property is
    not allowed, the rotation advances deterministically to the next style
    (daily_life applied to development land reads absurd).
    """
    n = len(styles)
    start = target_date.toordinal() % n
    for offset in range(n):
        style = styles[(start + offset) % n]
        allowed = style.get("types")
        if not allowed or prop.get("type") in allowed:
            return style
    log.error("No style in %s accepts property type %r", TEMPLATES_FILE, prop.get("type"))
    sys.exit(1)


# ---------------------------------------------------------------------------
# Rotation: property, image
# ---------------------------------------------------------------------------


def last_posted_dates(props: list[dict], post_log: list[dict]) -> dict[str, date]:
    """Most recent successful post date per property slug, from post-log.json.

    Queue ids look like post-YYYY-MM-DD-<slug>-<lang>, so the slug is matched
    with surrounding dashes. Entries from the old content generator
    (social-...) simply never match.
    """
    latest: dict[str, date] = {}
    for entry in post_log:
        if entry.get("status") != "posted":
            continue
        queue_id = str(entry.get("queue_id") or "")
        d = parse_iso_date(entry.get("date"))
        if d is None:
            continue
        for p in props:
            slug = p["slug"]
            if f"-{slug}-" in queue_id and (slug not in latest or d > latest[slug]):
                latest[slug] = d
    return latest


def pending_item_dates(props: list[dict], queue: list[dict]) -> dict[str, date]:
    """Most recent date each property appears in a pending direct-format item.

    Counts toward the cooldown alongside post-log dates: a queued-but-not-yet
    published item must block re-queueing the same property, otherwise a
    poster outage of a few days would cycle the catalog and publish the same
    property twice only days apart once the backlog drains.
    """
    latest: dict[str, date] = {}
    for item in queue:
        if "message" not in item or item.get("status") != "pending":
            continue
        item_id = str(item.get("id", ""))
        m = re.match(r"post-(\d{4}-\d{2}-\d{2})-", item_id)
        d = parse_iso_date(m.group(1)) if m else None
        if d is None:
            continue
        slug = item.get("property_slug") or next(
            (p["slug"] for p in props if f"-{p['slug']}-" in item_id), None)
        if slug and (slug not in latest or d > latest[slug]):
            latest[slug] = d
    return latest


def select_property(props: list[dict], posted_last: dict[str, date],
                    pending_last: dict[str, date], target_date: date) -> dict | None:
    """Least recently used active property outside the 14-day cooldown.

    Both published posts (post-log.json) and still-pending queue items count
    toward the cooldown, so a poster outage cannot re-queue a property early.
    Returns None when every property is inside the cooldown (starved).
    Ties (e.g. nothing posted yet) break deterministically, rotating the
    starting index by date.
    """
    eligible: list[tuple[date, int, dict]] = []
    n = len(props)
    for idx, prop in enumerate(props):
        slug = prop["slug"]
        recent = max(
            (d for d in (posted_last.get(slug), pending_last.get(slug)) if d is not None),
            default=None,
        )
        if recent is not None and (target_date - recent).days < COOLDOWN_DAYS:
            continue
        eligible.append((recent or date.min, (idx - target_date.toordinal()) % n, prop))
    if not eligible:
        return None
    eligible.sort(key=lambda t: (t[0], t[1]))
    return eligible[0][2]


def select_image(prop: dict, rotation: dict, target_date: date) -> str:
    """Least recently used image from post_images[], skipping any image used
    for this property within the last 30 days. If every image was used within
    the window (should not happen at the current cadence), reuse the least
    recent one with an explicit warning.
    """
    slug = prop["slug"]
    images = prop.get("post_images") or [prop.get("hero_image", "")]
    used = rotation.get(slug, {})
    ranked = sorted(
        (parse_iso_date(used.get(img)) or date.min, idx, img)
        for idx, img in enumerate(images)
    )
    fresh = [r for r in ranked
             if r[0] == date.min or (target_date - r[0]).days >= IMAGE_REUSE_DAYS]
    if fresh:
        return fresh[0][2]
    log.warning("All %d images for %s were used within %d days; reusing the least recent one.",
                len(images), slug, IMAGE_REUSE_DAYS)
    return ranked[0][2]


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def cmd_build(target_date: date, dry_run: bool = False) -> None:
    """Build the queue item for target_date and append it to the queue."""
    catalog = load_json(PROPERTIES_FILE, {})
    props = [p for p in catalog.get("properties", []) if p.get("active", True)]
    if not props:
        log.error("No active properties in %s", PROPERTIES_FILE)
        sys.exit(1)

    missing = [p["slug"] for p in props if p["slug"] not in REF_CODES]
    if missing:
        log.error("No ref code for slug(s): %s. Add them to REF_CODES.", ", ".join(missing))
        sys.exit(1)

    site_base_url = str(catalog.get("site_base_url", "")).rstrip("/")
    wa_number = str(catalog.get("whatsapp_number", ""))
    if not site_base_url or not wa_number:
        log.error("properties.json must define site_base_url and whatsapp_number")
        sys.exit(1)

    styles = load_templates()
    queue = load_queue()
    post_log = load_post_log()
    rotation = load_json(IMAGE_ROTATION_FILE, {})
    if not isinstance(rotation, dict):
        rotation = {}

    date_str = target_date.isoformat()

    # Deduplication: never write two items for the same day.
    prefix = f"post-{date_str}-"
    if any(str(item.get("id", "")).startswith(prefix)
           for item in queue if "message" in item):
        log.info("Queue already has an item for %s; nothing to do.", date_str)
        return

    # Property: least recently published, 14-day cooldown from post-log.json.
    posted_last = last_posted_dates(props, post_log)
    pending_last = pending_item_dates(props, queue)
    prop = select_property(props, posted_last, pending_last, target_date)
    if prop is None:
        log.warning(
            "STARVED: all %d active properties were posted or queued within the "
            "last %d days. Not queueing anything - the cooldown is never relaxed.",
            len(props), COOLDOWN_DAYS,
        )
        if not dry_run:
            if any(e.get("starved") and e.get("target_date") == date_str
                   for e in post_log):
                log.info("Starved entry for %s already in the log; not writing another.",
                         date_str)
            else:
                post_log.append({"starved": True, "target_date": date_str,
                                 "date": datetime.now(timezone.utc).isoformat()})
                save_post_log(post_log)
                log.info("Starved entry written to %s", LOG_FILE)
        sys.exit(0)

    # Language and style rotate deterministically by date (styles unsuited to
    # the property type are skipped, see select_style).
    lang = LANGUAGES[target_date.toordinal() % len(LANGUAGES)]
    style = select_style(styles, prop, target_date)
    template = style.get("templates", {}).get(lang)
    if not template:
        log.error("Style %r has no template for language %r", style.get("id"), lang)
        sys.exit(1)

    image_path = select_image(prop, rotation, target_date)
    image_url = f"{site_base_url}/{image_path}"

    ref = build_ref(prop["slug"], target_date)
    wa_link = build_wa_link(prop, lang, ref, wa_number)
    highlight_1, highlight_2 = pick_highlights(prop, target_date, lang)

    message = template.format(
        name=prop["name"],
        price=prop["price_display"],
        neighborhood=prop.get(f"neighborhood_{lang}") or prop["neighborhood"],
        highlight_1=highlight_1,
        highlight_2=highlight_2,
        wa_link=wa_link,
    )

    item = {
        "id": f"post-{date_str}-{prop['slug']}-{lang}",
        "message": message,
        "image_url": image_url,
        "link": "",
        "language": lang,
        "category": "property_spotlight",
        "property_slug": prop["slug"],
        "ref": ref,
        "status": "pending",
    }

    log.info("Built item %s [style=%s, image=%s, ref=%s]",
             item["id"], style.get("id"), image_path, ref)

    if dry_run:
        log.info("[DRY RUN] Would append this item to %s:", QUEUE_FILE)
        print(json.dumps(item, indent=2, ensure_ascii=False))
        log.info("[DRY RUN] Nothing written (queue, image rotation untouched).")
        return

    queue.append(item)
    save_queue(queue)
    rotation.setdefault(prop["slug"], {})[image_path] = date_str
    save_json(IMAGE_ROTATION_FILE, rotation)
    log.info("Queued %s (%d items now in queue). Image rotation updated.",
             item["id"], len(queue))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_date_arg(value: str) -> date:
    """argparse type for --date."""
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"invalid date {value!r}, expected YYYY-MM-DD") from e


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic daily queue builder — Rent & Go PC"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be queued without writing")
    parser.add_argument("--date", type=parse_date_arg, default=None,
                        metavar="YYYY-MM-DD",
                        help="Build for this date instead of today (ET)")

    args = parser.parse_args()
    cmd_build(args.date or get_today_et(), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
