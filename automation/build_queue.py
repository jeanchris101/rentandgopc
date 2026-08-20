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
  - Wording: the style's template is a SKELETON. Opener, closer, CTA and
    hashtag set come from styles[].parts[lang], and which two highlights show
    up, in what order and in what visual layout is picked too — all with a
    deterministic seed of date + property slug + style id. Same date, same
    text, always (the queue item must match what actually gets published).
    api/_lib/groups-plan.js runs the exact same algorithm for the group queue;
    its seed only adds the group code, so a Page post and a group post of the
    same property on the same day never come out with the same wording. If you
    change hash32/variant_seed/compose_template/pick_highlights here, change
    them there in the same commit or the two bots drift apart.
  - Language: this bot reads config.json content.languages. That key controls
    the PAGE only. The group queue has its own switch (`languages` in the
    groups settings blob, api/_lib/groups-settings.js): two different controls
    on purpose, because the Page is one general audience and the groups are 18
    audiences each with its own language.
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

# Placeholders a SKELETON (styles[].templates[lang]) may use. The five
# composition slots are filled from styles[].parts[lang] before any data
# placeholder is touched.
COMPOSITION_SLOTS = {"opener", "highlights", "closer", "hashtags", "cta"}
DATA_PLACEHOLDERS = {"name", "price", "neighborhood", "highlight_1", "highlight_2"}
ALLOWED_PLACEHOLDERS = DATA_PLACEHOLDERS | COMPOSITION_SLOTS | {"wa_link"}
# What a PART (opener/closer/cta) may reference. No {wa_link} and no
# composition slot: a part is a leaf, it never nests another part.
ALLOWED_PART_PLACEHOLDERS = DATA_PLACEHOLDERS
PART_POOLS = ("openers", "closers", "ctas", "hashtag_sets")
PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")

# Fallback if post-templates.json ever loses highlight_layouts. Matches the
# fallback in api/_lib/groups-plan.js.
DEFAULT_HIGHLIGHT_LAYOUTS = [{"id": "dash", "prefix": "- ", "join": "\n"}]

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


def load_templates() -> tuple[list[dict], list[dict]]:
    """Load and validate post-templates.json.

    Returns (styles, highlight_layouts). Exits on anything invalid: a broken
    template has to fail here, loudly, and not three steps later as a post
    with a literal "{opener}" on top of it.
    """
    data = load_json(TEMPLATES_FILE, {})
    if not isinstance(data, dict):
        data = {}
    styles = data.get("styles", [])
    if not styles:
        log.error("No styles found in %s", TEMPLATES_FILE)
        sys.exit(1)

    layouts = data.get("highlight_layouts") or DEFAULT_HIGHLIGHT_LAYOUTS
    if not isinstance(layouts, list) or not layouts:
        log.error("highlight_layouts in %s must be a non-empty list", TEMPLATES_FILE)
        sys.exit(1)

    for style in styles:
        sid = style.get("id")
        for lang, text in style.get("templates", {}).items():
            found = set(PLACEHOLDER_RE.findall(text))
            unknown = found - ALLOWED_PLACEHOLDERS
            if unknown:
                log.error("Style %r (%s) uses unknown placeholders: %s",
                          sid, lang, ", ".join(sorted(unknown)))
                sys.exit(1)
            if "wa_link" not in found:
                log.error("Style %r (%s) is missing the {wa_link} placeholder", sid, lang)
                sys.exit(1)
            missing_slots = COMPOSITION_SLOTS - found
            if missing_slots:
                log.error("Style %r (%s) skeleton is missing the slot(s): %s",
                          sid, lang, ", ".join("{%s}" % s for s in sorted(missing_slots)))
                sys.exit(1)

            # Every skeleton must end with {cta} then {wa_link}, each on its own
            # line. The group queue drops the {wa_link} line (rule 5: the link
            # goes in the first comment) and prints "details in the first
            # comment" in its place; if the CTA shared that line it would be
            # dropped with it and the group posts would lose the CTA entirely.
            tail = text.rstrip().split("\n")[-2:]
            if tail != ["{cta}", "{wa_link}"]:
                log.error("Style %r (%s) must end with {cta} and {wa_link} on separate lines; got %r",
                          sid, lang, tail)
                sys.exit(1)

            parts = (style.get("parts") or {}).get(lang)
            if not isinstance(parts, dict):
                log.error("Style %r has no parts for language %r", sid, lang)
                sys.exit(1)
            for pool in PART_POOLS:
                items = parts.get(pool)
                if not isinstance(items, list) or not items:
                    log.error("Style %r (%s) has an empty or missing %r pool", sid, lang, pool)
                    sys.exit(1)
                for item in items:
                    if pool == "hashtag_sets":
                        if not isinstance(item, list) or not item:
                            log.error("Style %r (%s): each hashtag_set must be a non-empty list",
                                      sid, lang)
                            sys.exit(1)
                        continue
                    bad = set(PLACEHOLDER_RE.findall(str(item))) - ALLOWED_PART_PLACEHOLDERS
                    if bad:
                        log.error("Style %r (%s) %s uses placeholders not allowed in a part: %s",
                                  sid, lang, pool, ", ".join(sorted(bad)))
                        sys.exit(1)
    return styles, layouts


# ---------------------------------------------------------------------------
# Message randomizer (deterministic)
#
# Repeated content is what Facebook flags as spam. Style x image alone is not
# enough variation, so every post also picks an opener, a closer, a CTA, a
# hashtag set, WHICH two highlights it shows, in what order, and in what visual
# layout.
#
# Deterministic on purpose: the seed is date + property slug + style id, so the
# same date always renders the same text. The queue item is written once and
# published later; if this rolled real dice, the log and the post would disagree.
#
# api/_lib/groups-plan.js has the byte-identical twin of every function below
# (hash32, variantSeed, pickVariant, composeTemplate, pickHighlights). Its seed
# additionally carries the group code. Keep the two in sync.
# ---------------------------------------------------------------------------


def hash32(text: str) -> int:
    """32-bit FNV-1a plus a final avalanche (MurmurHash3's fmix32).

    Same arithmetic, bit for bit, as hash32() in api/_lib/groups-plan.js.

    The avalanche is not decoration: in plain FNV-1a the lowest output bit is
    literally the XOR of the lowest input bits (the prime ends in 1), and this
    hash is only ever used modulo 3 or 4 — i.e. the low bits alone. Without
    mixing, near-identical seeds land on the same opener and the same closer far
    too often, which is the exact problem this randomizer exists to avoid.
    """
    h = 2166136261
    for ch in str(text):
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= h >> 16
    return h & 0xFFFFFFFF


def variant_seed(date_str: str, slug: str, style_id: str, group_code: str = "") -> str:
    """Base seed for a post. The Page bot has no group, hence the '-' slot."""
    return "|".join([str(date_str), str(group_code or "-"), str(slug), str(style_id or "")])


def pick_variant(items: list, seed: str, salt: str):
    """One item from `items`, chosen by (seed + salt).

    The salt is what stops the opener and the closer from moving together:
    without it every field would land on the same index and the real variation
    would be 4, not 4 x 4 x 4 x 3.
    """
    if not items:
        return None
    return items[hash32(f"{seed}|{salt}") % len(items)]


def render_highlights(highlights: list[str], seed: str, layouts: list[dict]) -> str:
    """The two highlights with their visual layout applied."""
    layout = pick_variant(layouts, seed, "layout") or layouts[0]
    prefix = str(layout.get("prefix", ""))
    join = str(layout.get("join", "\n"))
    return join.join(prefix + h for h in highlights)


def compose_template(style: dict, lang: str, highlights: list[str], seed: str,
                     layouts: list[dict]) -> str:
    """The style skeleton with its interchangeable pieces filled in.

    What is left afterwards are the data placeholders ({name}, {price},
    {neighborhood}, {wa_link}), which fill() resolves.
    """
    skeleton = style.get("templates", {}).get(lang)
    parts = (style.get("parts") or {}).get(lang) or {}
    opener = pick_variant(parts.get("openers"), seed, "opener")
    closer = pick_variant(parts.get("closers"), seed, "closer")
    cta = pick_variant(parts.get("ctas"), seed, "cta")
    tags = pick_variant(parts.get("hashtag_sets"), seed, "hashtags")
    if skeleton is None or None in (opener, closer, cta, tags):
        log.error("Style %r is missing a piece for language %r", style.get("id"), lang)
        sys.exit(1)

    hashtags = " ".join(tags) if isinstance(tags, list) else str(tags)
    # .replace(x, y, 1) mirrors String.replace(str, str) in JS, which also only
    # replaces the first occurrence.
    return (
        skeleton
        .replace("{opener}", opener, 1)
        .replace("{closer}", closer, 1)
        .replace("{cta}", cta, 1)
        .replace("{hashtags}", hashtags, 1)
        .replace("{highlights}", render_highlights(highlights, seed, layouts), 1)
    )


def fill(template: str, values: dict) -> str:
    """Replace {key} with values[key]; leave unknown placeholders untouched.

    Not str.format(): same semantics as fill() in groups-plan.js, and a stray
    brace in a highlight cannot raise here the way format() would.
    """
    return PLACEHOLDER_RE.sub(
        lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0),
        template,
    )


def highlight_count(n: int, seed: str) -> int:
    """How many highlights the post carries: 2 or 3.

    Always 2 when fewer than 4 are available (with 3 in total, showing 3 would
    mean showing them all every time and the rotation would be over). Not just
    visual variety: it multiplies the combination space by 5 without a single
    new line of copy.
    """
    if n < 4:
        return 2
    return 2 + (hash32(f"{seed}|hcount") % 2)


def pick_highlights(prop: dict, lang: str, seed: str) -> list[str]:
    """The post's highlights in its language: how many, which ones, what order.

    Uses highlights_<lang> (a parallel translation of highlights) when
    present, falling back to the English list, so es/fr posts never carry
    English bullets. CONFOTUR lines only if confotur == true — that filter is
    the single gate keeping CONFOTUR out of the four properties that do not
    have it, and it is never relaxed.

    The selection is a seeded PARTIAL Fisher-Yates: the space is the ORDERED
    arrangements of n taken 2 and 3 at a time (with 6 highlights: 30 + 120 =
    150), not the n fixed rotations it used to be. "Terrace + parking" does not
    read like "parking + terrace", and that difference now counts.
    """
    source = prop.get(f"highlights_{lang}") or prop.get("highlights", [])
    highlights = [
        h for h in source
        if prop.get("confotur") is True or "confotur" not in h.lower()
    ]
    n = len(highlights)
    if n < 2:
        log.error("Property %s needs at least 2 usable highlights (lang=%s)",
                  prop.get("slug"), lang)
        sys.exit(1)

    count = highlight_count(n, seed)
    idx = list(range(n))
    for k in range(count):
        j = k + (hash32(f"{seed}|h{k}") % (n - k))
        idx[k], idx[j] = idx[j], idx[k]
    return [highlights[i] for i in idx[:count]]


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

    styles, layouts = load_templates()
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
    if not style.get("templates", {}).get(lang):
        log.error("Style %r has no template for language %r", style.get("id"), lang)
        sys.exit(1)

    image_path = select_image(prop, rotation, target_date)
    image_url = f"{site_base_url}/{image_path}"

    ref = build_ref(prop["slug"], target_date)
    wa_link = build_wa_link(prop, lang, ref, wa_number)

    # Seed first: the highlights, the wording pieces and the visual layout all
    # hang off it. No group code — that is what keeps this post different from
    # the group posts of the same property on the same day.
    seed = variant_seed(date_str, prop["slug"], style.get("id"))
    highlights = pick_highlights(prop, lang, seed)

    message = fill(
        compose_template(style, lang, highlights, seed, layouts),
        {
            "name": prop["name"],
            "price": prop["price_display"],
            "neighborhood": prop.get(f"neighborhood_{lang}") or prop["neighborhood"],
            # {highlights} ya se resolvio en compose_template; estos dos siguen
            # disponibles por si una pieza los usa.
            "highlight_1": highlights[0],
            "highlight_2": highlights[1],
            "wa_link": wa_link,
        },
    )

    leftover = set(PLACEHOLDER_RE.findall(message))
    if leftover:
        log.error("Rendered message still has unfilled placeholders: %s",
                  ", ".join("{%s}" % p for p in sorted(leftover)))
        sys.exit(1)

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
