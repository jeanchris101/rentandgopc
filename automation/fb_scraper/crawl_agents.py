# ============================================================
# CRITICAL: READ-ONLY MODE — NEVER WRITE TO FACEBOOK
# This crawler ONLY reads agent profile pages to discover
# new groups and listings. It must NEVER post, comment, like,
# react, message, or share anything.
# ============================================================

"""
crawl_agents.py — Crawl Facebook agent profiles to discover new listings and groups.

Snowball effect: visits each known agent's profile, scrolls their recent activity,
extracts group URLs they've posted in and any property-related posts.
Saves discovered groups to /opt/data/discovered_groups.json.
Saves new posts to raw_posts table via database.py.
"""

import asyncio
import json
import logging
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from patchright.async_api import async_playwright, Page, BrowserContext

from config import load_config, ScraperConfig, AccountConfig
from database import get_connection, init_db, insert_raw_post, process_post, post_exists
from parser import parse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("agent_crawler")

SESSIONS_DIR = Path(__file__).parent / "sessions"
DISCOVERED_GROUPS_PATH = Path("/opt/data/discovered_groups.json")
DB_PATH = Path("/opt/data/fb_listings.db")

# ============================================================
# READ-ONLY SAFETY GUARD (same as scraper.py)
# ============================================================

READONLY_GUARD_JS = """
() => {
    if (window.__readonlyGuardInstalled) return;
    window.__readonlyGuardInstalled = true;

    const BLOCKED_LABELS = [
        'post', 'publish', 'publicar', 'comment', 'comentar', 'reply', 'responder',
        'share', 'compartir', 'send', 'enviar', 'like', 'love', 'haha', 'wow',
        'sad', 'angry', 'me gusta', 'submit', 'enviar mensaje',
    ];

    const ALLOWED_LABELS = [
        'log in', 'log into', 'iniciar sesión', 'login',
        'join group', 'join', 'unirse', 'unirse al grupo',
        'accept', 'allow', 'aceptar', 'permitir',
        'continue', 'continuar', 'next', 'siguiente',
    ];

    document.addEventListener('click', (e) => {
        const el = e.target.closest('button, [role="button"], a[role="button"]');
        if (!el) return;

        const text = (el.textContent || '').trim().toLowerCase();
        const ariaLabel = (el.getAttribute('aria-label') || '').trim().toLowerCase();
        const combined = text + ' ' + ariaLabel;

        for (const allowed of ALLOWED_LABELS) {
            if (text === allowed || ariaLabel === allowed) return;
        }

        for (const blocked of BLOCKED_LABELS) {
            if (combined.includes(blocked)) {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                console.error('[READONLY GUARD] Blocked click on: ' + text + ' / aria: ' + ariaLabel);
                return;
            }
        }
    }, true);
}
"""


async def install_readonly_guard(page: Page) -> None:
    """Install the read-only safety guard on a page."""
    try:
        await page.evaluate(READONLY_GUARD_JS)
    except Exception:
        pass


# ============================================================
# Helpers
# ============================================================

def extract_user_id(fb_profile_url: str) -> Optional[str]:
    """Extract numeric user ID from /groups/{gid}/user/{uid}/ or /profile.php?id={uid} URLs."""
    # Pattern: /user/{userId}/
    m = re.search(r'/user/(\d+)', fb_profile_url)
    if m:
        return m.group(1)
    # Pattern: profile.php?id={userId}
    m = re.search(r'profile\.php\?id=(\d+)', fb_profile_url)
    if m:
        return m.group(1)
    return None


def load_discovered_groups() -> dict:
    """Load existing discovered groups from JSON file."""
    if DISCOVERED_GROUPS_PATH.exists():
        try:
            with open(DISCOVERED_GROUPS_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"groups": {}, "last_updated": None}


def save_discovered_groups(data: dict) -> None:
    """Save discovered groups to JSON file."""
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    DISCOVERED_GROUPS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DISCOVERED_GROUPS_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info(f"Saved {len(data['groups'])} discovered groups to {DISCOVERED_GROUPS_PATH}")


def get_agents_sorted(conn) -> list[dict]:
    """Load all agents with fb_profile_url, sorted by total_listings desc."""
    rows = conn.execute(
        """SELECT id, name, fb_profile_url, total_listings, fb_user_id
           FROM agents
           WHERE fb_profile_url IS NOT NULL AND fb_profile_url != ''
           ORDER BY total_listings DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


# ============================================================
# Browser context creation (mirrors scraper.py)
# ============================================================

async def create_context(
    playwright_instance,
    account: AccountConfig,
    config: ScraperConfig,
) -> BrowserContext:
    """Create a browser context with session state, proxy, and UA."""
    ua = random.choice(config.user_agents)

    launch_args = {
        "headless": config.headless,
        "args": ["--disable-dev-shm-usage", "--no-sandbox"],
    }

    if account.proxy:
        launch_args["proxy"] = {"server": account.proxy.server}
        if account.proxy.username:
            launch_args["proxy"]["username"] = account.proxy.username
        if account.proxy.password:
            launch_args["proxy"]["password"] = account.proxy.password

    browser = await playwright_instance.chromium.launch(**launch_args)

    context_args = {
        "viewport": {"width": config.viewport_width, "height": config.viewport_height},
        "user_agent": ua,
        "locale": "en-US",
        "timezone_id": "America/Santo_Domingo",
    }

    session_path = account.get_session_path()
    if session_path.exists():
        context_args["storage_state"] = str(session_path)
        log.info(f"Loading session from {session_path}")
    else:
        log.warning(f"No session file for {account.label} — run 'setup_account' first")

    context = await browser.new_context(**context_args)
    return context


# ============================================================
# Profile page extraction
# ============================================================

async def extract_groups_from_page(page: Page) -> list[dict]:
    """Extract group URLs from all links on the current page."""
    return await page.evaluate("""
        () => {
            const groups = [];
            const seen = new Set();
            const links = document.querySelectorAll('a[href*="/groups/"]');
            for (const link of links) {
                const href = link.href || '';
                // Extract group ID or slug from URL
                const m = href.match(/facebook\\.com\\/groups\\/([^/?#]+)/);
                if (!m) continue;
                const groupIdOrSlug = m[1];
                // Skip non-group pages (user profiles within groups, etc.)
                if (groupIdOrSlug === 'feed' || groupIdOrSlug === 'discover' || groupIdOrSlug === 'joins') continue;
                if (seen.has(groupIdOrSlug)) continue;
                seen.add(groupIdOrSlug);
                // Get the link text as a potential group name
                let name = link.textContent.trim();
                if (name.length > 100) name = name.substring(0, 100);
                if (name.length < 2) name = groupIdOrSlug;
                groups.push({
                    group_id: groupIdOrSlug,
                    url: 'https://www.facebook.com/groups/' + groupIdOrSlug + '/',
                    name: name,
                });
            }
            return groups;
        }
    """)


async def extract_posts_from_profile(page: Page) -> list[dict]:
    """Extract post content from an agent's profile page."""
    return await page.evaluate("""
        () => {
            const results = [];
            const seenTexts = new Set();

            // Look for post containers — on profile pages, posts are in the feed
            const feed = document.querySelector('[role="feed"]');
            const container = feed || document.body;

            // Get all div[dir="auto"] elements which contain post text
            const textDivs = container.querySelectorAll('div[dir="auto"]');

            for (const div of textDivs) {
                // Skip if inside a comment (role="article" is comments)
                if (div.closest('[role="article"]')) continue;

                const text = div.textContent.trim();
                if (text.length < 30) continue;

                // Skip UI elements
                if (/^(Like|Comment|Share|See more|See More|Write a comment)$/i.test(text)) continue;
                if (/^(Facebook|Suggested for you|People you may know)/i.test(text)) continue;

                // Dedup by content prefix
                const key = text.substring(0, 100);
                if (seenTexts.has(key)) continue;
                seenTexts.add(key);

                // Try to find a permalink near this post
                let permalink = null;
                let postId = null;
                const parent = div.closest('[class]');
                if (parent) {
                    const links = parent.querySelectorAll('a');
                    for (const link of links) {
                        const href = link.href || '';
                        if (href.includes('/posts/')) {
                            permalink = href;
                            const pm = href.match(/\\/posts\\/(\\d+)/);
                            if (pm) postId = pm[1];
                            break;
                        }
                        if (href.includes('/permalink/')) {
                            permalink = href;
                            const pm = href.match(/\\/permalink\\/(\\d+)/);
                            if (pm) postId = pm[1];
                            break;
                        }
                        if (href.includes('pfbid')) {
                            permalink = href;
                            const pm = href.match(/(pfbid[\\w]+)/);
                            if (pm) postId = pm[1];
                            break;
                        }
                    }
                }

                // Generate hash-based ID if no permalink found
                if (!postId) {
                    let hash = 0;
                    const input = text.substring(0, 300);
                    for (let i = 0; i < input.length; i++) {
                        hash = ((hash << 5) - hash) + input.charCodeAt(i);
                        hash = hash & hash;
                    }
                    postId = 'agent_' + Math.abs(hash).toString(36);
                }

                // Extract group context from permalink if present
                let groupId = null;
                if (permalink) {
                    const gm = permalink.match(/\\/groups\\/(\\d+)/);
                    if (gm) groupId = gm[1];
                }

                // Images
                const imageUrls = [];
                if (parent) {
                    const imgs = parent.querySelectorAll('img');
                    for (const img of imgs) {
                        if (img.closest('[role="article"]')) continue;
                        const src = img.src || '';
                        if (!src) continue;
                        if (src.includes('/emoji/') || src.includes('/rsrc.php') || src.includes('static')) continue;
                        if ((src.includes('scontent') || src.includes('fbcdn')) && img.width > 100) {
                            imageUrls.push(src);
                        }
                    }
                }

                // Timestamp
                let timestamp = null;
                if (parent) {
                    const timeLinks = parent.querySelectorAll('a');
                    for (const link of timeLinks) {
                        const lt = link.textContent.trim();
                        const relMatch = lt.match(/^(\\d+)\\s*([hmdwHMDW])$/);
                        if (relMatch) {
                            const val = parseInt(relMatch[1]);
                            const unit = relMatch[2].toLowerCase();
                            const ms = { h: 3600000, m: 60000, d: 86400000, w: 604800000 };
                            timestamp = new Date(Date.now() - val * (ms[unit] || 0)).toISOString();
                            break;
                        }
                        if (/^just now$/i.test(lt)) { timestamp = new Date().toISOString(); break; }
                        if (/^yesterday/i.test(lt)) { timestamp = new Date(Date.now() - 86400000).toISOString(); break; }
                    }
                }

                results.push({
                    postId: postId,
                    rawText: text.substring(0, 3000),
                    permalink: permalink,
                    groupId: groupId,
                    imageUrls: imageUrls,
                    timestamp: timestamp,
                });
            }
            return results;
        }
    """)


# Real estate keywords to filter relevant posts
RE_PROPERTY_KEYWORDS = re.compile(
    r'\b('
    r'venta|sale|alquiler|rent|apartamento|apartment|apto|villa|casa|house|'
    r'penthouse|ph|terreno|lot|solar|land|'
    r'habitaci[oó]n|bedroom|bed|bath|ba[ñn]o|'
    r'USD|US\$|RD\$|DOP|\$\d|precio|price|'
    r'piscina|pool|amueblado|furnished|'
    r'Cap\s*Cana|Bavaro|B[aá]varo|Punta\s*Cana|Cocotal|Vista\s*Cana|'
    r'Cana\s*Rock|Veron|Ver[oó]n|Uvero\s*Alto|Macao|Higuey|Hig[uü]ey|'
    r'Cortecito|Los\s*Corales|Friusa|Downtown'
    r')\b', re.I
)


def is_property_related(text: str) -> bool:
    """Check if text looks like a real estate post."""
    matches = RE_PROPERTY_KEYWORDS.findall(text)
    return len(matches) >= 2  # At least 2 real estate keywords


# ============================================================
# Session verification
# ============================================================

async def verify_session(page: Page) -> bool:
    """Navigate to FB and verify we're logged in."""
    try:
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
        await install_readonly_guard(page)
        await asyncio.sleep(random.uniform(2.0, 4.0))

        url = page.url
        if "/login" in url or "login.php" in url:
            log.error("Session expired — need to re-setup")
            return False
        if "/checkpoint/" in url or "/checkpoint?" in url:
            log.error("Checkpoint detected — account may be locked")
            return False

        log.info("Session verified — logged in")
        return True
    except Exception as e:
        log.error(f"Session verification failed: {e}")
        return False


# ============================================================
# Human-like scrolling
# ============================================================

async def scroll_profile(page: Page, max_scrolls: int = 10) -> None:
    """Scroll down a profile page with human-like behavior."""
    for i in range(max_scrolls):
        # Occasional upward scroll
        if i > 0 and i % random.randint(6, 10) == 0:
            up_dist = random.randint(150, 350)
            await page.evaluate(f"window.scrollBy(0, -{up_dist})")
            await asyncio.sleep(random.uniform(0.5, 1.2))

        dist = random.randint(400, 800)
        await page.evaluate(f"window.scrollBy(0, {dist})")

        # Variable delays
        delay = random.uniform(2.0, 4.0)
        if i > 0 and i % random.randint(3, 5) == 0:
            delay = random.uniform(4.0, 8.0)

        await asyncio.sleep(delay)


# ============================================================
# Main crawl logic
# ============================================================

async def crawl_agent_profile(
    page: Page,
    agent: dict,
    conn,
    discovered_groups: dict,
    known_group_ids: set[str],
) -> tuple[int, int]:
    """
    Crawl a single agent's profile page.
    Returns (new_groups_found, new_posts_found).
    """
    user_id = extract_user_id(agent["fb_profile_url"])
    if not user_id:
        log.warning(f"  Could not extract user ID from: {agent['fb_profile_url']}")
        return 0, 0

    profile_url = f"https://www.facebook.com/profile.php?id={user_id}"
    agent_name = agent.get("name") or f"Agent#{agent['id']}"
    log.info(f"Crawling agent: {agent_name} (ID: {user_id}, listings: {agent.get('total_listings', 0)})")

    try:
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        await install_readonly_guard(page)
        await asyncio.sleep(random.uniform(3.0, 5.0))

        # Check if profile is accessible
        url = page.url
        if "/login" in url or "login.php" in url:
            log.warning(f"  Redirected to login — session issue")
            return 0, 0
        if "/checkpoint/" in url:
            log.warning(f"  Checkpoint detected — stopping")
            return -1, -1  # Signal to stop crawling

        # Check for private/unavailable profile
        body_text = await page.text_content("body", timeout=5000) or ""
        private_indicators = [
            "this content isn't available",
            "este contenido no está disponible",
            "this page isn't available",
            "esta página no está disponible",
            "the link you followed may be broken",
        ]
        for indicator in private_indicators:
            if indicator.lower() in body_text.lower():
                log.info(f"  Profile unavailable/private — skipping")
                return 0, 0

        # Scroll to load more content
        log.info(f"  Scrolling profile page...")
        await scroll_profile(page, max_scrolls=8)

        # Extract groups from page links
        new_groups = 0
        groups_found = await extract_groups_from_page(page)
        for group in groups_found:
            gid = group["group_id"]
            if gid not in discovered_groups["groups"] and gid not in known_group_ids:
                discovered_groups["groups"][gid] = {
                    "url": group["url"],
                    "name": group["name"],
                    "discovered_from_agent": agent_name,
                    "discovered_from_agent_id": agent["id"],
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                }
                new_groups += 1
                log.info(f"  NEW GROUP: {group['name']} ({group['url']})")

        # Extract posts from profile
        new_posts = 0
        posts = await extract_posts_from_profile(page)
        log.info(f"  Found {len(posts)} text blocks on profile")

        for post in posts:
            raw_text = post.get("rawText", "")
            post_id = post.get("postId", "")

            if not raw_text or not post_id:
                continue

            # Only save property-related posts
            if not is_property_related(raw_text):
                continue

            # Check if post already exists
            if post_exists(conn, post_id):
                continue

            # Determine group context
            group_id = post.get("groupId") or "agent_profile"
            group_name = f"Agent Profile: {agent_name}"

            # Insert raw post
            inserted = insert_raw_post(
                conn=conn,
                post_id=post_id,
                group_id=group_id,
                group_name=group_name,
                author_name=agent_name,
                raw_text=raw_text,
                image_urls=post.get("imageUrls", []),
                timestamp=post.get("timestamp"),
                permalink=post.get("permalink"),
                source="facebook",
            )

            if inserted:
                new_posts += 1
                log.info(f"  NEW POST: {post_id} ({raw_text[:80]}...)")

                # Parse and process the post
                try:
                    result = parse(raw_text, has_images=bool(post.get("imageUrls")))
                    if not result.is_spam:
                        process_post(
                            conn=conn,
                            post_id=post_id,
                            author_name=agent_name,
                            fb_profile_url=agent["fb_profile_url"],
                            raw_text=raw_text,
                            image_urls=post.get("imageUrls", []),
                            result=result,
                            source="facebook",
                        )
                except Exception as e:
                    log.warning(f"  Failed to parse post {post_id}: {e}")

                conn.commit()

        log.info(f"  Agent {agent_name}: {new_groups} new groups, {new_posts} new posts")
        return new_groups, new_posts

    except Exception as e:
        log.error(f"  Error crawling agent {agent_name}: {e}")
        return 0, 0


async def main():
    """Main entry point — crawl all agent profiles."""
    log.info("=" * 60)
    log.info("AGENT PROFILE CRAWLER — Snowball Discovery")
    log.info("=" * 60)

    # Load config and find first active account
    config = load_config()
    active_accounts = [a for a in config.accounts if not a.disabled and a.has_session()]
    if not active_accounts:
        log.error("No active accounts with sessions found. Run scraper setup first.")
        sys.exit(1)

    account = active_accounts[0]
    log.info(f"Using account: {account.label}")

    # Database
    conn = get_connection()
    init_db(conn)

    # Load agents
    agents = get_agents_sorted(conn)
    if not agents:
        log.error("No agents with fb_profile_url found in database.")
        conn.close()
        sys.exit(1)
    log.info(f"Found {len(agents)} agents to crawl (sorted by activity)")

    # Load existing discovered groups
    discovered_groups = load_discovered_groups()
    existing_discovered = len(discovered_groups["groups"])
    log.info(f"Previously discovered groups: {existing_discovered}")

    # Load known group IDs from config (groups we already monitor)
    known_group_ids = set()
    for g in config.groups:
        if g.group_id:
            known_group_ids.add(g.group_id)
    log.info(f"Currently monitoring {len(known_group_ids)} groups")

    # Totals
    total_new_groups = 0
    total_new_posts = 0
    agents_crawled = 0
    agents_skipped = 0

    # Launch browser
    async with async_playwright() as p:
        context = await create_context(p, account, config)
        page = await context.new_page()

        # Verify session
        if not await verify_session(page):
            log.error("Session verification failed. Aborting.")
            await context.browser.close()
            conn.close()
            sys.exit(1)

        # Crawl each agent
        for i, agent in enumerate(agents):
            user_id = extract_user_id(agent["fb_profile_url"])
            if not user_id:
                log.warning(f"Skipping agent {agent.get('name', '?')}: no user ID in URL")
                agents_skipped += 1
                continue

            new_groups, new_posts = await crawl_agent_profile(
                page=page,
                agent=agent,
                conn=conn,
                discovered_groups=discovered_groups,
                known_group_ids=known_group_ids,
            )

            # Checkpoint detected — stop immediately
            if new_groups == -1:
                log.error("Checkpoint detected — stopping crawl to protect account")
                break

            total_new_groups += new_groups
            total_new_posts += new_posts
            agents_crawled += 1

            # Save discovered groups periodically (every 5 agents)
            if agents_crawled % 5 == 0:
                save_discovered_groups(discovered_groups)

            # Wait between agents (30-60s, human-like)
            if i < len(agents) - 1:
                wait = random.uniform(30.0, 60.0)
                log.info(f"  Waiting {wait:.0f}s before next agent... ({i+1}/{len(agents)})")
                await asyncio.sleep(wait)

        # Save session state
        try:
            session_path = account.get_session_path()
            await context.storage_state(path=str(session_path))
            log.info(f"Session saved to {session_path}")
        except Exception as e:
            log.warning(f"Failed to save session: {e}")

        await context.browser.close()

    # Final save
    save_discovered_groups(discovered_groups)
    conn.close()

    # Summary
    log.info("=" * 60)
    log.info("CRAWL COMPLETE — Summary")
    log.info("=" * 60)
    log.info(f"Agents crawled:     {agents_crawled}")
    log.info(f"Agents skipped:     {agents_skipped}")
    log.info(f"New groups found:   {total_new_groups}")
    log.info(f"New posts found:    {total_new_posts}")
    log.info(f"Total discovered groups: {len(discovered_groups['groups'])}")
    log.info(f"Discovered groups saved to: {DISCOVERED_GROUPS_PATH}")
    log.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
