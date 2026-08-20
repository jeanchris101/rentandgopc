# ============================================================
# CRITICAL: READ-ONLY MODE — NEVER WRITE TO WHATSAPP
# This scraper ONLY reads messages from WhatsApp groups via
# the WAHA REST API. It must NEVER send messages, react,
# or perform any write action on WhatsApp.
# The ONLY allowed actions are:
#   1. GET requests to read chats and messages
#   2. GET requests to download media
# Everything else is strictly observation.
# ============================================================

"""
wa_scraper.py — WhatsApp group scraper using WAHA REST API.
Reads messages from configured WhatsApp groups, parses with the same
parser.py, and stores in the same SQLite database as the FB scraper.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from database import (
    get_connection, init_db, post_exists, insert_raw_post,
    process_post, start_scrape_log, finish_scrape_log, get_stats,
)
from parser import parse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("wa_scraper")

CONFIG_PATH = Path(__file__).parent / "config.json"


# ============================================================
# WAHA API client (read-only)
# ============================================================

class WahaClient:
    """Minimal read-only client for the WAHA WhatsApp HTTP API."""

    def __init__(self, base_url: str, session: str = "default"):
        self.base_url = base_url.rstrip("/")
        self.session = session

    def _get(self, path: str, params: Optional[dict] = None) -> dict | list:
        """Make a GET request to WAHA API."""
        url = f"{self.base_url}{path}"
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
            if qs:
                url += f"?{qs}"

        req = Request(url, method="GET")
        req.add_header("Accept", "application/json")

        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            log.error(f"WAHA API error {e.code}: {body}")
            raise
        except URLError as e:
            log.error(f"WAHA connection error: {e.reason}")
            raise

    def get_chats(self) -> list[dict]:
        """List all chats (groups and contacts)."""
        return self._get(f"/api/{self.session}/chats")

    def get_messages(self, chat_id: str, limit: int = 100, download_media: bool = False) -> list[dict]:
        """Get messages from a specific chat."""
        params = {
            "chatId": chat_id,
            "limit": str(limit),
            "downloadMedia": str(download_media).lower(),
        }
        return self._get(f"/api/{self.session}/messages", params)

    def check_session(self) -> bool:
        """Check if the WAHA session is active."""
        try:
            sessions = self._get("/api/sessions")
            for s in sessions:
                if s.get("name") == self.session and s.get("status") == "WORKING":
                    return True
            return False
        except Exception as e:
            log.error(f"Failed to check WAHA session: {e}")
            return False


# ============================================================
# Config loading
# ============================================================

def load_wa_config() -> dict:
    """Load WhatsApp scraper config from config.json."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    return {
        "waha_url": raw.get("waha_url", "http://localhost:3000"),
        "waha_session": raw.get("waha_session", "default"),
        "whatsapp_groups": raw.get("whatsapp_groups", []),
    }


# ============================================================
# Message processing
# ============================================================

def _msg_to_post_id(msg: dict) -> str:
    """Generate a unique post_id from a WAHA message."""
    # WAHA message IDs are unique per chat
    msg_id = msg.get("id", {})
    if isinstance(msg_id, dict):
        # WAHA v2 format: {fromMe: bool, id: str, ...}
        return f"wa_{msg_id.get('id', msg_id.get('_serialized', ''))}"
    return f"wa_{msg_id}"


def _msg_timestamp(msg: dict) -> Optional[str]:
    """Extract ISO timestamp from a WAHA message."""
    ts = msg.get("timestamp")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
        except (ValueError, TypeError, OSError):
            pass
    return None


def _msg_author(msg: dict) -> Optional[str]:
    """Extract author name from a WAHA message."""
    # In group messages, _data.notifyName or from field
    return msg.get("_data", {}).get("notifyName") or msg.get("from")


def _msg_image_urls(msg: dict) -> list[str]:
    """Extract image URLs from a WAHA message."""
    urls = []
    media_url = msg.get("mediaUrl")
    if media_url:
        urls.append(media_url)
    return urls


# ============================================================
# Main scraper
# ============================================================

def scrape_wa_group(
    client: WahaClient,
    group_id: str,
    group_name: str,
    conn,
    limit: int = 100,
) -> tuple[int, int, int]:
    """
    Scrape a single WhatsApp group. Returns (total, new, skipped).
    """
    log.info(f"Scraping WA group: {group_name} ({group_id})")
    log_id = start_scrape_log(conn, group_id, group_name)

    total = 0
    new = 0
    skipped = 0

    try:
        messages = client.get_messages(group_id, limit=limit, download_media=False)
        log.info(f"  Fetched {len(messages)} messages from WAHA")

        for msg in messages:
            # Only process text messages (type 'chat')
            msg_type = msg.get("type")
            if msg_type not in ("chat", "image", "document"):
                continue

            body = msg.get("body", "").strip()
            if not body or len(body) < 30:
                continue

            post_id = _msg_to_post_id(msg)
            total += 1

            if post_exists(conn, post_id):
                skipped += 1
                continue

            author = _msg_author(msg)
            timestamp = _msg_timestamp(msg)
            image_urls = _msg_image_urls(msg)

            inserted = insert_raw_post(
                conn,
                post_id=post_id,
                group_id=group_id,
                group_name=group_name,
                author_name=author,
                raw_text=body,
                image_urls=image_urls,
                timestamp=timestamp,
                permalink=None,
                source="whatsapp",
            )

            if not inserted:
                skipped += 1
                continue

            result = parse(body, has_images=len(image_urls) > 0)

            if result.is_spam:
                process_post(
                    conn, post_id=post_id, author_name=author,
                    fb_profile_url=None, raw_text=body,
                    image_urls=image_urls, result=result, source="whatsapp",
                )
                skipped += 1
                log.debug(f"  [SPAM] {post_id[:30]}")
                continue

            agent_id, property_id = process_post(
                conn,
                post_id=post_id,
                author_name=author,
                fb_profile_url=None,
                raw_text=body,
                image_urls=image_urls,
                result=result,
                source="whatsapp",
            )
            new += 1

            conf = f"{result.confidence:.0%}"
            status = "OK" if not result.needs_review else "REVIEW"
            price_str = f"${result.price.amount:,.0f}" if result.price else "?"
            hood = result.zone or "?"
            prop_tag = f"P{property_id}" if property_id else "-"
            agent_tag = f"A{agent_id}" if agent_id else "-"
            log.info(f"  [{status} {conf}] #{new}: {price_str} | {hood} | {prop_tag} {agent_tag} | {post_id[:30]}")

        conn.commit()
        finish_scrape_log(conn, log_id, total, new, skipped, "success")
        log.info(f"  Done: {new} new, {skipped} skipped, {total} total from {group_name}")

    except Exception as e:
        log.error(f"  Error scraping WA group {group_name}: {e}")
        finish_scrape_log(conn, log_id, total, new, skipped, "error", str(e))

    return (total, new, skipped)


def run_wa_scraper(group_filter: Optional[str] = None):
    """Run the WhatsApp scraper across configured groups."""
    config = load_wa_config()

    if not config["whatsapp_groups"]:
        log.error("No WhatsApp groups configured in config.json. Add entries to 'whatsapp_groups' array.")
        log.info('Example: {"chat_id": "120363421942085763@g.us", "name": "RE Group", "limit": 100}')
        sys.exit(1)

    client = WahaClient(config["waha_url"], config["waha_session"])

    # Check session
    log.info(f"Connecting to WAHA at {config['waha_url']} (session: {config['waha_session']})")
    if not client.check_session():
        log.error(f"WAHA session '{config['waha_session']}' is not active. Start it first.")
        sys.exit(1)
    log.info("WAHA session is active")

    conn = get_connection()
    init_db(conn)

    log.info(f"DB stats before: {get_stats(conn)}")

    groups = config["whatsapp_groups"]
    if group_filter:
        groups = [g for g in groups if g["chat_id"] == group_filter]
        if not groups:
            log.error(f"Group '{group_filter}' not found in config")
            sys.exit(1)

    total_new = 0
    total_processed = 0

    for group in groups:
        chat_id = group["chat_id"]
        name = group.get("name", chat_id)
        limit = group.get("limit", 100)

        processed, new, skipped = scrape_wa_group(client, chat_id, name, conn, limit)
        total_new += new
        total_processed += processed

    stats = get_stats(conn)
    conn.close()

    log.info("=" * 60)
    log.info("WhatsApp scraper finished!")
    log.info(f"  This run: {total_new} new, {total_processed} total processed")
    log.info(f"  Database: {stats}")
    log.info("=" * 60)

    return total_new


# ============================================================
# Utility: list WhatsApp groups
# ============================================================

def list_wa_groups():
    """List all WhatsApp group chats via WAHA API."""
    config = load_wa_config()
    client = WahaClient(config["waha_url"], config["waha_session"])

    log.info(f"Connecting to WAHA at {config['waha_url']}")
    if not client.check_session():
        log.error("WAHA session not active")
        sys.exit(1)

    chats = client.get_chats()
    groups = [c for c in chats if c.get("id", {}).get("server") == "g.us" or str(c.get("id", "")).endswith("@g.us")]

    print(f"\nFound {len(groups)} WhatsApp groups:\n")
    for g in groups:
        chat_id = g.get("id")
        if isinstance(chat_id, dict):
            chat_id = chat_id.get("_serialized", str(chat_id))
        name = g.get("name", "Unknown")
        print(f"  {chat_id}  {name}")

    print(f"\nAdd groups to config.json 'whatsapp_groups' array:")
    print('  {"chat_id": "120363421942085763@g.us", "name": "Group Name", "limit": 100}')


# ============================================================
# CLI
# ============================================================

def main():
    ap = argparse.ArgumentParser(description="WhatsApp Group Scraper (WAHA API)")
    sub = ap.add_subparsers(dest="command", help="Command to run")

    # scrape
    scrape_p = sub.add_parser("scrape", help="Scrape configured WhatsApp groups")
    scrape_p.add_argument("--group", type=str, help="Scrape only this chat ID")
    scrape_p.add_argument("--limit", type=int, help="Override message limit per group")

    # list
    sub.add_parser("list", help="List all WhatsApp groups from WAHA")

    args = ap.parse_args()

    if args.command == "list":
        list_wa_groups()
        return

    if args.command == "scrape":
        group_filter = getattr(args, "group", None)
        run_wa_scraper(group_filter)
        return

    # Default: scrape
    run_wa_scraper()


if __name__ == "__main__":
    main()
