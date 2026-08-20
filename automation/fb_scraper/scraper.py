# ============================================================
# CRITICAL: READ-ONLY MODE — NEVER WRITE TO FACEBOOK
# This scraper ONLY reads/captures data from group feeds.
# It must NEVER post, comment, like, react, message, or
# share anything. The burner account is for observation only.
# Any write action risks the account AND the groups we monitor.
# The ONLY allowed "write" actions are:
#   1. Login form (setup command only)
#   2. Join Group button + membership answers (join command only)
#   3. Scrolling (reading)
# Everything else is strictly observation.
# ============================================================

"""
scraper.py — Patchright-based Facebook group scraper.
Uses saved session state (no automated login). Human-like scroll behavior.
Scrolls target groups, captures posts, parses with regex, stores in SQLite.
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

from config import load_config, ScraperConfig, AccountConfig, GroupConfig
from database import (
    get_connection, init_db, post_exists, insert_raw_post,
    process_post, start_scrape_log, finish_scrape_log, get_stats,
)
from parser import parse
try:
    from image_cache import download_images_background
except ImportError:
    download_images_background = None  # image caching not available on this host

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fb_scraper")


# ============================================================
# Browser crash detection and recovery
# ============================================================

# Error messages that indicate the browser process has died
BROWSER_CRASH_PATTERNS = [
    "browser has been closed",
    "target closed",
    "protocol error",
    "connection closed",
    "write epipe",
    "broken pipe",
    "browser disconnected",
    "browser.newcontext: target page, context or browser has been closed",
    "page.goto: target page, context or browser has been closed",
    "ns_error_connection_refused",
    "session closed",
    "execution context was destroyed",
    "page closed",
    "net::err_",
]


class BrowserCrashError(Exception):
    """Raised when a browser/page operation fails due to browser death (EPIPE, etc.)."""
    pass


def is_browser_crash(error: Exception) -> bool:
    """Check if an exception indicates the browser process has died."""
    msg = str(error).lower()
    return any(pattern in msg for pattern in BROWSER_CRASH_PATTERNS)


def raise_if_browser_crash(error: Exception) -> None:
    """Re-raise as BrowserCrashError if the error indicates browser death."""
    if is_browser_crash(error):
        log.error(f"BROWSER CRASH DETECTED: {error}")
        raise BrowserCrashError(str(error)) from error

SESSIONS_DIR = Path(__file__).parent / "sessions"


# ============================================================
# READ-ONLY SAFETY: Block dangerous interactions at runtime.
# Inject JS that intercepts clicks on Post/Comment/Share/Like
# buttons and prevents them from firing.
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

    // Allowlist for login/join flows (exact lowercase matches)
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

        // Allow if it matches the allowlist
        for (const allowed of ALLOWED_LABELS) {
            if (text === allowed || ariaLabel === allowed) return;
        }

        // Block if it matches a dangerous label
        for (const blocked of BLOCKED_LABELS) {
            if (combined.includes(blocked)) {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                console.error('[READONLY GUARD] Blocked click on: ' + text + ' / aria: ' + ariaLabel);
                return;
            }
        }
    }, true);  // capture phase to intercept before FB handlers
}
"""


async def install_readonly_guard(page: Page) -> None:
    """Install the read-only safety guard on a page. Safe to call multiple times."""
    try:
        await page.evaluate(READONLY_GUARD_JS)
    except Exception:
        pass  # Page may not be ready yet; guard will be retried


# --- Post extraction from page ---

async def extract_posts_from_page(page: Page, known_ids: set[str]) -> list[dict]:
    """Extract all visible posts from the group feed.

    Facebook's modern group feed uses [role="feed"] with plain <div> children.
    Posts do NOT have [role="article"] — that's only used for comments.
    We iterate over feed children and extract text, author, images from each.
    Post IDs come from /posts/ links, /permalink/ links, or content hash fallback.
    """
    posts = await page.evaluate(r"""
        () => {
            const feed = document.querySelector('[role="feed"]');
            if (!feed) return [];

            const results = [];
            const seenIds = new Set();
            const _debug = [];

            for (const child of feed.children) {
                // Skip empty/tiny elements (spacers, loading indicators)
                const text = child.textContent || '';
                if (text.length < 30) {
                    _debug.push({skip: 'text<30', len: text.length});
                    continue;
                }

                // Skip elements that are just comment sections (contain [role="article"])
                const articles = child.querySelectorAll('[role="article"]');
                const dirAutoExists = !!child.querySelector('div[dir="auto"]');
                const hasOnlyComments = articles.length > 0 && !dirAutoExists;
                if (hasOnlyComments) {
                    _debug.push({skip: 'comments_only', articles: articles.length});
                    continue;
                }

                // Extract post ID from links
                let permalink = null;
                let postId = null;
                let authorProfileUrl = null;

                // First try: standard post links (/posts/, /permalink/, pfbid)
                const postLinks = child.querySelectorAll('a');
                for (const link of postLinks) {
                    const href = link.href || '';
                    if (href.includes('comment_id') || href.includes('reply_comment_id')) continue;

                    if (href.includes('/posts/')) {
                        permalink = href;
                        const m = href.match(/\\/posts\\/(\\d+)/);
                        if (m) postId = m[1];
                        break;
                    }
                    if (href.includes('/permalink/')) {
                        permalink = href;
                        const m = href.match(/\\/permalink\\/(\\d+)/);
                        if (m) postId = m[1];
                        break;
                    }
                    if (href.includes('pfbid')) {
                        permalink = href;
                        const m = href.match(/(pfbid[\\w]+)/);
                        if (m) postId = m[1];
                        break;
                    }
                }

                // Fallback: timestamp links (relative time text like "2h", "1d", "March 10")
                // These are the post permalink in modern FB group feeds
                if (!permalink) {
                    for (const link of postLinks) {
                        const href = link.href || '';
                        if (!href.includes('facebook.com/groups/')) continue;
                        if (href.includes('/user/') || href.includes('/profile')) continue;
                        const lt = (link.textContent || '').trim();
                        // Match timestamp-like text: "2h", "1d", "3w", "Just now", "Yesterday", "March 10"
                        if (/^(\d+\s*[hmdwHMDW]|Just now|Yesterday|[A-Z][a-z]+ \d{1,2})/i.test(lt)) {
                            permalink = href.split('?')[0];
                            // Try to extract post ID from the URL
                            const pm = href.match(/\/(\d{10,})(?:[/?]|$)/);
                            if (pm) postId = pm[1];
                            break;
                        }
                    }
                }

                // Extract author profile URL (for agent tracking)
                for (const link of postLinks) {
                    const href = link.href || '';
                    if (href.includes('/user/') || (href.includes('/profile.php') && !href.includes('comment'))) {
                        authorProfileUrl = href.split('?')[0];
                        break;
                    }
                }

                // Post ID will be generated AFTER text extraction if no link found
                // (need the actual post content for a unique hash, not the wrapper textContent)

                // We'll set postId later if still null

                // Extract main post text
                let rawText = '';
                const msgEl = child.querySelector('[data-ad-preview="message"]')
                             || child.querySelector('[data-ad-comet-preview="message"]');
                if (msgEl) {
                    rawText = msgEl.textContent.trim();
                } else {
                    // Strategy 1: dir="auto" divs (standard post text)
                    const parts = [];
                    const divs = child.querySelectorAll('div[dir="auto"]');
                    for (const d of divs) {
                        if (d.closest('[role="article"]')) continue;
                        const t = d.textContent.trim();
                        if (t.length > 15) parts.push(t);
                    }
                    const unique = [...new Set(parts)];
                    rawText = unique.join('\\n').trim();

                    // Strategy 2: If dir="auto" found nothing, try spans and
                    // paragraphs with meaningful content
                    if (rawText.length < 30) {
                        const candidates = child.querySelectorAll('span[dir="auto"], p, div[data-ad-preview], div[data-ad-comet-preview]');
                        const spans = [];
                        for (const el of candidates) {
                            if (el.closest('[role="article"]')) continue;
                            const t = el.textContent.trim();
                            if (t.length > 30 && !t.match(/^(Facebook)+$/) && !t.match(/^(Like|Comment|Share)/)) {
                                spans.push(t);
                            }
                        }
                        rawText = [...new Set(spans)].join('\\n').trim();
                    }

                    // Strategy 3: Last resort — full text of non-UI descendants
                    if (rawText.length < 30) {
                        const clone = child.cloneNode(true);
                        clone.querySelectorAll('[role="article"], form, [role="button"], [role="toolbar"], img, svg, [aria-hidden="true"]').forEach(el => el.remove());
                        const fullText = clone.textContent.replace(/\\s+/g, ' ').trim();
                        // Remove FB UI noise
                        const cleaned = fullText
                            .replace(/(Facebook)+/g, '')
                            .replace(/(Like|Comment|Share|Reply|\\d+ Comments?|\\d+ Likes?|Most relevant|See more|See More|Write a comment|Write a public comment|\\d+[hmdw]|All reactions:)/gi, '')
                            .replace(/\\s+/g, ' ')
                            .trim();
                        if (cleaned.length > 30) {
                            rawText = cleaned.substring(0, 2000);
                        }
                    }
                }

                if (!rawText || rawText.length < 30) {
                    _debug.push({skip: 'no_text', rawLen: rawText?.length || 0, textLen: text.length, dirAuto: child.querySelectorAll('div[dir="auto"]').length});
                    continue;
                }

                // Generate post ID from content hash if we don't have one from a link
                if (!postId) {
                    const hashInput = (authorProfileUrl || '') + '|' + rawText.substring(0, 300);
                    let hash = 0;
                    for (let i = 0; i < hashInput.length; i++) {
                        hash = ((hash << 5) - hash) + hashInput.charCodeAt(i);
                        hash = hash & hash;
                    }
                    postId = 'h_' + Math.abs(hash).toString(36);
                }

                if (seenIds.has(postId)) {
                    _debug.push({skip: 'dup_id', postId: postId});
                    continue;
                }
                seenIds.add(postId);

                // Author name
                let authorName = null;
                const headerLink = child.querySelector('h2 a, h3 a, h4 a, strong a');
                if (headerLink) {
                    const name = headerLink.textContent.trim();
                    if (name.length > 1 && name.length < 80 &&
                        !name.includes('Suggested') && !name.includes('Join') &&
                        !/^\\d+$/.test(name)) {
                        authorName = name;
                    }
                }

                // Images — skip profile pics (small), emojis, and FB UI assets
                // Get full-size URLs by removing Facebook's size/crop parameters
                const imageUrls = [];
                const seenUrls = new Set();
                const imgs = child.querySelectorAll('img');
                for (const img of imgs) {
                    if (img.closest('[role="article"]')) continue;
                    let src = img.src || img.getAttribute('data-src') || img.dataset.src || '';
                    if (!src) continue;
                    if (src.includes('/emoji/') || src.includes('/rsrc.php') || src.includes('static')) continue;
                    // Accept if it's a Facebook CDN image — check width OR natural dimensions
                    // img.width can be 0 for lazy-loaded images, so also check naturalWidth and attributes
                    const w = img.width || img.naturalWidth || parseInt(img.getAttribute('width') || '0');
                    if ((src.includes('scontent') || src.includes('fbcdn')) && (w > 80 || w === 0)) {
                        // Skip tiny profile pics (usually 40x40 or 36x36)
                        if (w > 0 && w < 80) continue;
                        // Remove stp= parameter to get full-size image
                        try {
                            const u = new URL(src);
                            u.searchParams.delete('stp');
                            src = u.toString();
                        } catch(e) {}
                        if (!seenUrls.has(src)) {
                            seenUrls.add(src);
                            imageUrls.push(src);
                        }
                    }
                }
                // Also check for background-image on divs (FB gallery uses this)
                const bgDivs = child.querySelectorAll('div[style*="background-image"]');
                for (const div of bgDivs) {
                    const style = div.getAttribute('style') || '';
                    const m = style.match(/url\(["']?(https:\/\/[^"')]+)["']?\)/);
                    if (m && (m[1].includes('scontent') || m[1].includes('fbcdn'))) {
                        let src = m[1];
                        try { const u = new URL(src); u.searchParams.delete('stp'); src = u.toString(); } catch(e) {}
                        if (!seenUrls.has(src)) {
                            seenUrls.add(src);
                            imageUrls.push(src);
                        }
                    }
                }

                // Timestamp — look for relative time text in links
                let timestamp = null;
                for (const link of postLinks) {
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
                    // Match "March 10", "Mar 10", etc.
                    if (/^[A-Z][a-z]+ \\d{1,2}/.test(lt) && lt.length < 20) {
                        try { timestamp = new Date(lt + ' ' + new Date().getFullYear()).toISOString(); } catch(e) {}
                        if (timestamp) break;
                    }
                }

                results.push({
                    postId,
                    permalink: permalink || null,
                    rawText,
                    authorName,
                    authorProfileUrl: authorProfileUrl || null,
                    imageUrls,
                    timestamp,
                });
            }
            return {results: results, _debug: _debug, feedChildren: feed.children.length};
        }
    """)

    if isinstance(posts, dict):
        feed_children = posts.get("feedChildren", 0)
        actual_posts = posts.get("results", [])
        log.debug(f"  Feed: {feed_children} children, {len(actual_posts)} extracted")
        posts = actual_posts

    return [p for p in posts if p["postId"] not in known_ids]


# --- Checkpoint detection ---

async def check_checkpoint(page: Page, account: AccountConfig) -> bool:
    """Check if FB redirected to a checkpoint. Returns True if checkpoint detected."""
    url = page.url
    if "/checkpoint/" in url or "/checkpoint?" in url:
        log.warning(f"CHECKPOINT detected for {account.label}: {url}")
        # Save session state before stopping
        try:
            session_path = account.get_session_path()
            await page.context.storage_state(path=str(session_path))
            log.info(f"  Session saved to {session_path}")
        except Exception as e:
            log.error(f"  Failed to save session on checkpoint: {e}")
        return True

    # Also check page content for checkpoint indicators
    try:
        body = await page.text_content("body", timeout=3000) or ""
        checkpoint_phrases = [
            "confirm your identity",
            "confirma tu identidad",
            "security check",
            "we need to verify",
            "account has been locked",
            "tu cuenta ha sido bloqueada",
        ]
        for phrase in checkpoint_phrases:
            if phrase.lower() in body.lower():
                log.warning(f"CHECKPOINT content detected for {account.label}: '{phrase}'")
                return True
    except Exception:
        pass

    return False


# --- Human-like scrolling ---

async def human_scroll(page: Page, scroll_count: int) -> None:
    """Perform a human-like scroll with variable behavior."""

    # Occasional upward scroll every ~10 scrolls
    if scroll_count > 0 and scroll_count % random.randint(8, 12) == 0:
        up_dist = random.randint(200, 400)
        log.debug(f"  Scroll UP {up_dist}px (natural behavior)")
        await page.evaluate(f"window.scrollBy(0, -{up_dist})")
        await asyncio.sleep(random.uniform(0.5, 1.5))

    # Aggressive scrolling — we need 3 months of history
    if scroll_count == 0:
        dist = random.randint(800, 1200)
    else:
        dist = random.randint(1200, 2000)

    await page.evaluate(f"window.scrollBy(0, {dist})")

    # Fast but human-like delays
    delay = random.uniform(1.5, 3.0)

    # Every 8-12 scrolls: medium pause 3-5s
    if scroll_count > 0 and scroll_count % random.randint(8, 12) == 0:
        delay = random.uniform(3.0, 5.0)
        log.debug(f"  Medium pause: {delay:.1f}s")

    # Every 25-35 scrolls: longer pause 8-15s
    if scroll_count > 0 and scroll_count % random.randint(25, 35) == 0:
        delay = random.uniform(8.0, 15.0)
        log.info(f"  Long pause: {delay:.0f}s (human-like)")

    await asyncio.sleep(delay)


# --- Download images using browser session (FB CDN URLs are session-tied) ---

IMAGE_DIR = Path("/opt/data/images")
MAX_IMAGES = 3  # limit per post to keep scraping fast


async def _download_images_via_browser(page: Page, post_id: str, image_urls: list) -> list:
    """Download images using the Playwright page context (has FB session cookies).
    Returns list of local filenames saved to IMAGE_DIR."""
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(c if c.isalnum() or c == "_" else "_" for c in post_id)
    filenames = []

    for idx, url in enumerate(image_urls[:MAX_IMAGES]):
        if not url or not isinstance(url, str):
            continue
        fname = f"{safe_id}_{idx}.jpg"
        filepath = IMAGE_DIR / fname
        if filepath.exists() and filepath.stat().st_size > 0:
            filenames.append(fname)
            continue
        try:
            resp = await page.context.request.get(url, timeout=8000)
            body = await resp.body()
            if resp.ok and len(body) > 1000:
                filepath.write_bytes(body)
                filenames.append(fname)
        except Exception:
            pass  # skip failed downloads silently

    return filenames


# --- Create browser context for an account ---

async def launch_browser(
    playwright_instance,
    account: AccountConfig,
    config: ScraperConfig,
):
    """Launch a single browser instance. Reuse across groups to save memory."""
    launch_args = {
        "headless": config.headless,
        "args": ["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu", "--js-flags=--max-old-space-size=256"],
    }

    if account.proxy:
        launch_args["proxy"] = {"server": account.proxy.server}
        if account.proxy.username:
            launch_args["proxy"]["username"] = account.proxy.username
        if account.proxy.password:
            launch_args["proxy"]["password"] = account.proxy.password

    return await playwright_instance.chromium.launch(**launch_args)


async def create_context(
    playwright_instance,
    account: AccountConfig,
    config: ScraperConfig,
    browser=None,
) -> BrowserContext:
    """Create a browser context with session state, proxy, and UA.
    If browser is provided, reuses it instead of launching a new one.
    """
    ua = random.choice(config.user_agents)

    if browser is None:
        browser = await launch_browser(playwright_instance, account, config)

    context_args = {
        "viewport": {"width": config.viewport_width, "height": config.viewport_height},
        "user_agent": ua,
        "locale": "en-US",
        "timezone_id": "America/Santo_Domingo",
    }

    # Load saved session state if available
    session_path = account.get_session_path()
    if session_path.exists():
        context_args["storage_state"] = str(session_path)
        log.info(f"Loading session from {session_path}")
    else:
        log.warning(f"No session file for {account.label} — run 'setup_account' first")

    context = await browser.new_context(**context_args)
    return context


# --- Verify session is logged in ---

async def verify_session(page: Page, account: AccountConfig) -> bool:
    """Navigate to FB and verify we're logged in via saved session."""
    log.info(f"Verifying session for {account.label}...")

    try:
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
        await install_readonly_guard(page)
        await asyncio.sleep(random.uniform(2.0, 4.0))

        # Checkpoint check
        if await check_checkpoint(page, account):
            return False

        url = page.url
        # If redirected to login page, session is invalid
        if "/login" in url or "login.php" in url:
            log.warning(f"Session expired for {account.label} — need to re-setup")
            return False

        # Look for logged-in indicators (profile link, notifications, etc.)
        logged_in = await page.evaluate("""
            () => {
                // Check for elements only visible when logged in
                const profileLink = document.querySelector('[aria-label="Your profile"], [aria-label="Tu perfil"]');
                const nav = document.querySelector('[role="navigation"]');
                const composer = document.querySelector('[aria-label="Create a post"], [aria-label="Crear una publicación"]');
                return !!(profileLink || (nav && composer));
            }
        """)

        if logged_in:
            log.info(f"Session valid for {account.label}")
            return True

        # Fallback: if we're on facebook.com (not login), assume OK
        if "facebook.com" in url and "/login" not in url:
            log.info(f"Session appears valid for {account.label} (URL check)")
            return True

        log.warning(f"Session invalid for {account.label}")
        return False

    except Exception as e:
        log.error(f"Session verification failed for {account.label}: {e}")
        return False


# --- Scrape a single group ---

async def scrape_group(
    page: Page,
    group: GroupConfig,
    conn,
    account: AccountConfig,
) -> tuple[int, int, int]:
    """
    Scrape a single FB group. Returns (total_captured, new_posts, skipped).
    """
    log.info(f"Scraping group: {group.name} ({group.url})")
    log_id = start_scrape_log(conn, group.group_id or "", group.name)

    total_captured = 0
    new_posts = 0
    skipped = 0

    # Load existing post IDs for this group
    rows = conn.execute(
        "SELECT post_id FROM raw_posts WHERE group_id = ?", (group.group_id,)
    ).fetchall()
    known_ids = {r["post_id"] for r in rows}
    log.info(f"  Already have {len(known_ids)} posts from this group")

    try:
        await page.goto(group.url, wait_until="domcontentloaded", timeout=30000)
        await install_readonly_guard(page)
        await asyncio.sleep(random.uniform(3.0, 5.0))

        # Checkpoint check after navigation
        if await check_checkpoint(page, account):
            finish_scrape_log(conn, log_id, 0, 0, 0, "error", "checkpoint_detected")
            return (0, 0, 0)

        # Check accessibility — only flag truly inaccessible groups
        body_lower = (await page.text_content("body") or "").lower()
        inaccessible_signals = [
            "this content isn't available",
            "this content isn\u2019t available",
            "don't have permission",
            "don\u2019t have permission",
            "need to be a member",
            "no longer a member",
            "group does not exist",
            "content not found",
        ]
        is_blocked = any(sig in body_lower for sig in inaccessible_signals)

        if is_blocked:
            log.warning(f"  Cannot access group: {group.name} (group_not_accessible)")
            finish_scrape_log(conn, log_id, 0, 0, 0, "error", "group_not_accessible")
            return (0, 0, 0)

        # Ensure we're on the Discussion tab (not Chats, Members, etc.)
        # Click "Discussion" tab if visible
        try:
            discussion_tab = page.locator('a[href*="/discussion"], a:has-text("Discussion"), a:has-text("Discusión")')
            if await discussion_tab.count() > 0:
                await discussion_tab.first.click()
                await asyncio.sleep(random.uniform(2.0, 3.0))
                log.info("  Switched to Discussion tab")
        except Exception:
            pass

        # Get group name from page (but ONLY if it looks like a real group name,
        # not a tab name like "Chats", "Members", "Discussion", etc.)
        SKIP_H1 = {"chats", "members", "discussion", "discusión", "about", "media", "events", "files", ""}
        try:
            h1 = await page.locator("h1").first.text_content(timeout=5000)
            if h1 and h1.strip().lower() not in SKIP_H1 and len(h1.strip()) > 3:
                group.name = h1.strip()
                log.info(f"  Group name from page: {group.name}")
        except Exception:
            pass

        no_new_count = 0
        scroll_count = 0
        prev_scroll_height = 0

        # Verify feed exists before scrolling
        try:
            feed = page.locator('[role="feed"]')
            if await feed.count() == 0:
                log.warning("  No [role='feed'] found — page may be on wrong tab")
                # Try clicking Discussion tab again
                try:
                    disc = page.locator('a:has-text("Discussion"), a:has-text("Discusión"), a:has-text("Publicaciones")')
                    if await disc.count() > 0:
                        await disc.first.click()
                        await asyncio.sleep(3)
                        log.info("  Retried Discussion tab click")
                except Exception:
                    pass
        except Exception:
            pass

        while scroll_count < group.max_scrolls and new_posts < group.max_posts:
            # Expand "See more" links to get full post text
            try:
                see_more_links = page.locator('[role="feed"] div[role="button"]:has-text("See more"), [role="feed"] div[role="button"]:has-text("Ver más")')
                sm_count = await see_more_links.count()
                for sm_i in range(min(sm_count, 10)):
                    try:
                        btn = see_more_links.nth(sm_i)
                        if await btn.is_visible():
                            await btn.click()
                            await asyncio.sleep(random.uniform(0.3, 0.8))
                    except Exception:
                        pass
            except Exception:
                pass

            # Extract posts
            posts = await extract_posts_from_page(page, known_ids)

            # Count how many are actually NEW (not in known_ids)
            new_in_batch = sum(1 for p in posts if p["postId"] not in known_ids)
            log.debug(f"  Scroll {scroll_count}: {len(posts)} extracted, {new_in_batch} new")

            # Check if page is still loading (scrollHeight growing)
            try:
                cur_height = await page.evaluate("document.body.scrollHeight")
            except Exception:
                cur_height = prev_scroll_height

            if new_in_batch == 0:
                # If scrollHeight grew, content is still loading — don't count as empty
                if cur_height > prev_scroll_height + 200:
                    log.debug(f"  Page still loading (height {prev_scroll_height}->{cur_height}), not counting as empty")
                else:
                    no_new_count += 1
                if no_new_count >= 15:
                    log.info(f"  No new posts after 15 consecutive empty scrolls — feed exhausted")
                    break
            else:
                no_new_count = 0

            prev_scroll_height = cur_height

            newly_inserted = []  # Track new posts for image caching
            for post_data in posts:
                post_id = post_data["postId"]
                if post_id in known_ids:
                    skipped += 1
                    continue

                inserted = insert_raw_post(
                    conn,
                    post_id=post_id,
                    group_id=group.group_id or "",
                    group_name=group.name,
                    author_name=post_data.get("authorName"),
                    raw_text=post_data["rawText"],
                    image_urls=post_data.get("imageUrls", []),
                    timestamp=post_data.get("timestamp"),
                    permalink=post_data.get("permalink"),
                )

                if inserted:
                    post_images = post_data.get("imageUrls", [])
                    if post_images:
                        newly_inserted.append((post_id, post_images))
                    result = parse(post_data["rawText"], has_images=len(post_images) > 0)

                    if result.is_spam:
                        # Still record it but don't count as new listing
                        process_post(conn, post_id=post_id, author_name=post_data.get("authorName"),
                                     fb_profile_url=None, raw_text=post_data["rawText"],
                                     image_urls=post_images, result=result)
                        known_ids.add(post_id)
                        skipped += 1
                        log.debug(f"  [SPAM] {post_id[:20]}")
                        continue

                    agent_id, property_id = process_post(
                        conn,
                        post_id=post_id,
                        author_name=post_data.get("authorName"),
                        fb_profile_url=post_data.get("authorProfileUrl"),
                        raw_text=post_data["rawText"],
                        image_urls=post_images,
                        result=result,
                    )
                    known_ids.add(post_id)
                    new_posts += 1

                    conf = f"{result.confidence:.0%}"
                    status = "OK" if not result.needs_review else "REVIEW"
                    price_str = f"${result.price.amount:,.0f}" if result.price else "?"
                    hood = result.zone or "?"
                    prop_tag = f"P{property_id}" if property_id else "-"
                    agent_tag = f"A{agent_id}" if agent_id else "-"
                    log.info(f"  [{status} {conf}] #{new_posts}: {price_str} | {hood} | {prop_tag} {agent_tag} | {post_id[:20]}")
                else:
                    skipped += 1

                total_captured += 1

            conn.commit()

            # Download images for new posts using the browser's session
            # FB CDN URLs are session-tied and expire instantly for external clients
            if newly_inserted:
                for pid, p_imgs in newly_inserted:
                    try:
                        filenames = await _download_images_via_browser(page, pid, p_imgs)
                        if filenames:
                            conn.execute(
                                "UPDATE raw_posts SET local_images = ? WHERE post_id = ?",
                                (json.dumps(filenames), pid)
                            )
                    except Exception as img_err:
                        log.debug(f"Image download failed for {pid[:20]}: {img_err}")
                conn.commit()

            # Progress log every 10 scrolls
            if scroll_count > 0 and scroll_count % 10 == 0:
                log.info(f"  Progress: scroll {scroll_count}/{group.max_scrolls}, {new_posts} new posts, {skipped} skipped")

            # Human-like scroll
            await human_scroll(page, scroll_count)
            scroll_count += 1

            # Check for checkpoint periodically
            if scroll_count % 10 == 0:
                if await check_checkpoint(page, account):
                    log.error(f"  Checkpoint mid-scrape — stopping group {group.name}")
                    finish_scrape_log(conn, log_id, total_captured, new_posts, skipped, "error", "checkpoint_mid_scrape")
                    return (total_captured, new_posts, skipped)

        # Save session state after successful scrape
        try:
            session_path = account.get_session_path()
            await page.context.storage_state(path=str(session_path))
        except Exception:
            pass

        finish_scrape_log(conn, log_id, total_captured, new_posts, skipped, "success")
        log.info(f"  Done: {new_posts} new, {skipped} skipped, {total_captured} total from {group.name}")
        return (total_captured, new_posts, skipped)

    except BrowserCrashError:
        log.error(f"  Browser crashed while scraping {group.name} — will attempt recovery")
        finish_scrape_log(conn, log_id, total_captured, new_posts, skipped, "error", "browser_crash_epipe")
        raise  # Let run_scraper handle browser relaunch
    except Exception as e:
        raise_if_browser_crash(e)  # Convert to BrowserCrashError if applicable
        log.error(f"  Error scraping {group.name}: {e}")
        finish_scrape_log(conn, log_id, total_captured, new_posts, skipped, "error", str(e))
        return (total_captured, new_posts, skipped)


# --- Main scraper orchestration ---

async def run_scraper(config: Optional[ScraperConfig] = None):
    """Run the full scraper across all configured groups."""
    if config is None:
        config = load_config()

    if not config.accounts:
        log.error("No Facebook accounts configured. Set FB_EMAIL + FB_PASSWORD env vars or add to config.json.")
        sys.exit(1)

    if not config.groups:
        log.error("No groups configured. Add groups to config.json.")
        sys.exit(1)

    # Filter to active accounts with sessions
    active_accounts = [a for a in config.accounts if not a.disabled]
    if not active_accounts:
        log.error("All accounts are disabled.")
        sys.exit(1)

    accounts_with_sessions = [a for a in active_accounts if a.has_session()]
    if not accounts_with_sessions:
        log.error("No accounts have session files. Run 'py scraper.py setup <label>' for each account first.")
        sys.exit(1)

    conn = get_connection()
    init_db(conn)

    # Track which groups we've completed so we can resume from where we left off
    progress_file = Path(__file__).parent / ".scraper_progress.json"
    completed_groups = set()
    try:
        if progress_file.exists():
            prog = json.loads(progress_file.read_text())
            # Only use progress from the last 2 hours (stale progress = start over)
            if prog.get("timestamp") and (datetime.now(timezone.utc) - datetime.fromisoformat(prog["timestamp"])).total_seconds() < 7200:
                completed_groups = set(prog.get("completed", []))
                log.info(f"Resuming — {len(completed_groups)} groups already done this cycle")
    except Exception:
        pass

    # Sort groups: uncompleted first, then completed (for deeper re-scraping)
    groups_to_scrape = [g for g in config.groups if g.url not in completed_groups]
    groups_already_done = [g for g in config.groups if g.url in completed_groups]
    ordered_groups = groups_to_scrape + groups_already_done

    log.info(f"Starting scraper — {len(ordered_groups)} groups ({len(groups_to_scrape)} new, {len(groups_already_done)} re-scrape), {len(accounts_with_sessions)} accounts")
    log.info(f"DB stats before: {get_stats(conn)}")

    total_new = 0
    total_captured = 0

    # Pick a random account with a valid session
    account = random.choice(accounts_with_sessions)
    log.info(f"Using account: {account.label}")

    # Per-group timeout: 8 minutes max to prevent hangs
    GROUP_TIMEOUT = 480

    async with async_playwright() as p:
        browser = await launch_browser(p, account, config)
        context = await create_context(p, account, config, browser=browser)
        page = await context.new_page()

        # Verify session
        if not await verify_session(page, account):
            log.warning(f"Session invalid for {account.label}, trying other accounts...")
            await context.close()

            # Try other accounts
            logged_in = False
            for alt in accounts_with_sessions:
                if alt.email == account.email:
                    continue
                log.info(f"Trying account: {alt.label}")
                # Close old browser if proxy changes
                if alt.proxy != account.proxy:
                    await browser.close()
                    browser = await launch_browser(p, alt, config)
                context = await create_context(p, alt, config, browser=browser)
                page = await context.new_page()
                if await verify_session(page, alt):
                    account = alt
                    logged_in = True
                    break
                await context.close()

            if not logged_in:
                log.error("No valid sessions found. Run setup_account for each account.")
                await browser.close()
                conn.close()
                sys.exit(1)

        # Scrape each group with timeout protection
        for i, group in enumerate(ordered_groups):
            if i > 0:
                delay = random.uniform(
                    config.between_groups_delay_min,
                    config.between_groups_delay_max,
                )
                log.info(f"Waiting {delay:.0f}s before next group...")
                await asyncio.sleep(delay)

            # Wrap each group in a timeout + try/except for crash resilience
            captured, new, skipped = 0, 0, 0
            try:
                captured, new, skipped = await asyncio.wait_for(
                    scrape_group(page, group, conn, account),
                    timeout=GROUP_TIMEOUT,
                )
                total_new += new
                total_captured += captured
                log.info(f"  [{i+1}/{len(ordered_groups)}] {group.name}: {new} new, {skipped} skipped")

                # Mark group as completed in progress file
                completed_groups.add(group.url)
                try:
                    progress_file.write_text(json.dumps({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "completed": list(completed_groups),
                        "total_new": total_new,
                    }))
                except Exception:
                    pass

            except asyncio.TimeoutError:
                log.warning(f"  TIMEOUT after {GROUP_TIMEOUT}s on {group.name} — moving to next group")
                completed_groups.add(group.url)
                conn.commit()
            except BrowserCrashError as e:
                log.error(f"  BROWSER CRASH on {group.name}: {e} — recovering browser...")
                conn.commit()
                # Go straight to browser recovery (skip about:blank navigation)
                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    await browser.close()
                except Exception:
                    pass
                try:
                    browser = await launch_browser(p, account, config)
                    context = await create_context(p, account, config, browser=browser)
                    page = await context.new_page()
                    if not await verify_session(page, account):
                        log.error("  Could not recover browser session after crash")
                        break
                    log.info("  Browser relaunched successfully after crash")
                except Exception as e2:
                    log.error(f"  Browser recovery failed after crash: {e2}")
                    break
                continue  # Skip the about:blank cleanup below, go to next group
            except Exception as e:
                if is_browser_crash(e):
                    log.error(f"  BROWSER CRASH on {group.name}: {e} — recovering browser...")
                    conn.commit()
                    try:
                        await context.close()
                    except Exception:
                        pass
                    try:
                        await browser.close()
                    except Exception:
                        pass
                    try:
                        browser = await launch_browser(p, account, config)
                        context = await create_context(p, account, config, browser=browser)
                        page = await context.new_page()
                        if not await verify_session(page, account):
                            log.error("  Could not recover browser session after crash")
                            break
                        log.info("  Browser relaunched successfully after crash")
                    except Exception as e2:
                        log.error(f"  Browser recovery failed after crash: {e2}")
                        break
                    continue
                log.error(f"  CRASH on {group.name}: {e} — moving to next group")
                conn.commit()

            # Free DOM memory between groups — navigate to blank page
            try:
                await page.goto("about:blank", timeout=10000)
                await asyncio.sleep(2)
                import gc; gc.collect()
            except Exception:
                # Browser might have crashed — try to recover
                log.warning("  Browser may have crashed, attempting recovery...")
                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    # Try reusing existing browser first
                    context = await create_context(p, account, config, browser=browser)
                    page = await context.new_page()
                    if not await verify_session(page, account):
                        log.error("  Could not recover browser session")
                        break
                    log.info("  Browser recovered successfully")
                except Exception:
                    # Browser itself is dead — relaunch
                    log.warning("  Browser dead, relaunching...")
                    try:
                        await browser.close()
                    except Exception:
                        pass
                    try:
                        browser = await launch_browser(p, account, config)
                        context = await create_context(p, account, config, browser=browser)
                        page = await context.new_page()
                        if not await verify_session(page, account):
                            log.error("  Could not recover after relaunch")
                            break
                        log.info("  Browser relaunched successfully")
                    except Exception as e2:
                        log.error(f"  Browser recovery failed: {e2}")
                        break

            # If checkpoint was detected, rotate account
            if captured == 0 and new == 0:
                last_log = conn.execute(
                    "SELECT status, error FROM scrape_log ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if last_log and "checkpoint" in (last_log["error"] or ""):
                    log.warning(f"Checkpoint on {account.label} — rotating account")
                    await context.close()

                    # Find next account
                    remaining = [a for a in accounts_with_sessions if a.email != account.email and a.has_session()]
                    if remaining:
                        account = random.choice(remaining)
                        log.info(f"Rotated to: {account.label}")
                        # Relaunch browser if proxy changes
                        if account.proxy != accounts_with_sessions[0].proxy:
                            await browser.close()
                            browser = await launch_browser(p, account, config)
                        context = await create_context(p, account, config, browser=browser)
                        page = await context.new_page()
                        if not await verify_session(page, account):
                            log.error(f"Rotated account {account.label} also invalid")
                            break
                    else:
                        log.error("No more accounts to rotate to")
                        break

        # ─── Marketplace scraping (after all groups) ───
        try:
            from marketplace import scrape_marketplace
            log.info("Starting Marketplace scrape...")
            # Free memory first
            try:
                await page.goto("about:blank", timeout=10000)
                await asyncio.sleep(2)
                import gc; gc.collect()
            except Exception:
                # Browser may have crashed before marketplace — try to recover
                log.warning("  Browser may be dead before marketplace, recovering...")
                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    await browser.close()
                except Exception:
                    pass
                browser = await launch_browser(p, account, config)
                context = await create_context(p, account, config, browser=browser)
                page = await context.new_page()
                if not await verify_session(page, account):
                    log.error("  Could not recover browser for marketplace")
                    raise Exception("Browser recovery failed for marketplace")
                log.info("  Browser recovered for marketplace")

            mp_total, mp_new = await asyncio.wait_for(
                scrape_marketplace(page, conn, account, max_listings=150, visit_details=20),
                timeout=900,  # 15 min max for marketplace
            )
            total_new += mp_new
            log.info(f"  Marketplace: {mp_new} new listings from {mp_total} found")
        except asyncio.TimeoutError:
            log.warning("  Marketplace timed out after 15 min")
        except Exception as e:
            log.error(f"  Marketplace error: {e}")

        # Final session save
        try:
            await page.context.storage_state(path=str(account.get_session_path()))
        except Exception:
            pass

        await browser.close()

    # Clear progress file after full cycle
    try:
        progress_file.unlink(missing_ok=True)
    except Exception:
        pass

    stats = get_stats(conn)
    conn.close()

    log.info("=" * 60)
    log.info(f"Scraper finished full cycle!")
    log.info(f"  This run: {total_new} new posts, {total_captured} total processed")
    log.info(f"  Groups completed: {len(completed_groups)}/{len(ordered_groups)}")
    log.info(f"  Database: {stats}")
    log.info("=" * 60)

    return total_new


# --- Setup account (manual login) ---

async def setup_account(label: str, auto_login: bool = True):
    """Login to Facebook and save session state. Auto-login if no 2FA."""
    config = load_config()

    # Find account by label
    account = None
    for a in config.accounts:
        if a.label == label:
            account = a
            break

    if not account:
        log.error(f"Account '{label}' not found in config. Available: {[a.label for a in config.accounts]}")
        sys.exit(1)

    session_path = account.get_session_path()
    log.info(f"Setting up account: {account.label} ({account.email})")
    log.info(f"Session will be saved to: {session_path}")

    async with async_playwright() as p:
        launch_args = {
            "headless": False,
            "args": ["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu", "--js-flags=--max-old-space-size=256"],
        }

        if account.proxy:
            launch_args["proxy"] = {"server": account.proxy.server}
            if account.proxy.username:
                launch_args["proxy"]["username"] = account.proxy.username
            if account.proxy.password:
                launch_args["proxy"]["password"] = account.proxy.password

        browser = await p.chromium.launch(**launch_args)

        context_args = {
            "viewport": {"width": config.viewport_width, "height": config.viewport_height},
            "locale": "en-US",
            "timezone_id": "America/Santo_Domingo",
        }

        # Load existing session if present
        if session_path.exists():
            context_args["storage_state"] = str(session_path)
            log.info(f"Loading existing session from {session_path}")

        context = await browser.new_context(**context_args)
        page = await context.new_page()
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(2.0, 4.0))

        # Check if already logged in from saved session
        url = page.url
        if "facebook.com" in url and "/login" not in url and "checkpoint" not in url:
            logged_in = await page.evaluate("""
                () => {
                    const nav = document.querySelector('[role="navigation"]');
                    return !!nav;
                }
            """)
            if logged_in:
                log.info("Already logged in from saved session!")
                await context.storage_state(path=str(session_path))
                log.info(f"Session saved to {session_path}")
                await browser.close()
                return

        # Auto-login: fill email + password and submit
        if auto_login:
            log.info("Attempting auto-login...")
            try:
                # Accept cookie dialog if present
                try:
                    cookie_btn = page.locator('button[data-cookiebanner="accept_button"], button:has-text("Allow"), button:has-text("Accept")')
                    if await cookie_btn.count() > 0:
                        await cookie_btn.first.click()
                        await asyncio.sleep(random.uniform(1.0, 2.0))
                except Exception:
                    pass

                # Fill email
                email_input = page.locator('input#email, input[name="email"]')
                await email_input.fill(account.email)
                await asyncio.sleep(random.uniform(0.5, 1.5))

                # Fill password
                pass_input = page.locator('input#pass, input[name="pass"]')
                await pass_input.fill(account.password)
                await asyncio.sleep(random.uniform(0.5, 1.0))

                # Click login button
                login_btn = page.locator('button[name="login"], button[type="submit"], button:has-text("Log In"), button:has-text("Log in")')
                await login_btn.first.click()
                log.info("Login form submitted, waiting for response...")

                # Wait for navigation
                await asyncio.sleep(random.uniform(5.0, 8.0))

                # Check result
                url = page.url
                if "/checkpoint" in url:
                    log.warning("Checkpoint detected after login! Manual intervention needed.")
                    log.info("Complete the checkpoint in the browser, then press Ctrl+C to save session.")
                elif "/login" in url or "login.php" in url:
                    log.warning("Still on login page — credentials may be wrong or FB wants verification.")
                    log.info("Check the browser and complete login manually. Press Ctrl+C when done.")
                else:
                    log.info("Auto-login successful!")
                    await context.storage_state(path=str(session_path))
                    log.info(f"Session saved to {session_path}")

                    # Verify we're actually logged in
                    await asyncio.sleep(2.0)
                    logged_in = await page.evaluate("""
                        () => {
                            const nav = document.querySelector('[role="navigation"]');
                            const profileLink = document.querySelector('[aria-label="Your profile"]');
                            return !!(nav || profileLink);
                        }
                    """)
                    if logged_in:
                        log.info("Login confirmed — News Feed is visible.")
                        await browser.close()
                        return
                    else:
                        log.info("Page loaded but can't confirm login. Keeping browser open...")

            except Exception as e:
                log.error(f"Auto-login failed: {e}")
                log.info("Falling back to manual login. Complete in the browser.")

        log.info("Browser open — complete any remaining steps, then press Ctrl+C to save and exit.")

        try:
            # Wait indefinitely — user closes when ready
            while True:
                await asyncio.sleep(5)
                # Periodically check if logged in
                url = page.url
                if "facebook.com" in url and "/login" not in url and "checkpoint" not in url:
                    # Auto-save session periodically
                    await context.storage_state(path=str(session_path))
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            # Save final session state
            log.info("Saving session state...")
            await context.storage_state(path=str(session_path))
            log.info(f"Session saved to {session_path}")
            await browser.close()

    log.info(f"Setup complete for {account.label}. You can now run the scraper.")


# --- Auto-join groups ---

async def join_groups(config: Optional[ScraperConfig] = None):
    """Navigate to each group and click Join. Handle membership questions."""
    if config is None:
        config = load_config()

    active = [a for a in config.accounts if not a.disabled and a.has_session()]
    if not active:
        log.error("No accounts with sessions. Run setup_account first.")
        sys.exit(1)

    account = random.choice(active)
    log.info(f"Joining groups with account: {account.label}")

    from config import JOIN_GROUP_ANSWERS

    async with async_playwright() as p:
        context = await create_context(p, account, config)
        page = await context.new_page()

        if not await verify_session(page, account):
            log.error(f"Session invalid for {account.label}")
            await context.browser.close()
            sys.exit(1)

        for i, group in enumerate(config.groups):
            if i > 0:
                delay = random.uniform(15.0, 30.0)
                log.info(f"Waiting {delay:.0f}s before next group...")
                await asyncio.sleep(delay)

            log.info(f"Navigating to: {group.name} ({group.url})")
            await page.goto(group.url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(3.0, 5.0))

            if await check_checkpoint(page, account):
                log.error("Checkpoint — stopping joins")
                break

            # Check if already a member
            body = await page.text_content("body") or ""
            if "Joined" in body or "Member" in body:
                log.info(f"  Already a member of {group.name}")
                continue

            # Look for Join button
            try:
                join_btn = page.locator('button:has-text("Join group"), button:has-text("Join Group"), button:has-text("Unirse al grupo")')
                if await join_btn.count() > 0:
                    await join_btn.first.click()
                    log.info(f"  Clicked Join for {group.name}")
                    await asyncio.sleep(random.uniform(2.0, 4.0))

                    # Check for membership questions
                    textareas = page.locator('textarea, input[type="text"]')
                    count = await textareas.count()
                    if count > 0:
                        answer = random.choice(JOIN_GROUP_ANSWERS)
                        log.info(f"  Answering {count} membership question(s): '{answer}'")
                        for j in range(count):
                            await textareas.nth(j).fill(answer)
                            await asyncio.sleep(random.uniform(0.5, 1.0))

                        # Submit answers
                        submit_btn = page.locator('button:has-text("Submit"), button:has-text("Enviar"), button[type="submit"]')
                        if await submit_btn.count() > 0:
                            await submit_btn.first.click()
                            log.info(f"  Submitted answers for {group.name}")
                        await asyncio.sleep(random.uniform(2.0, 3.0))

                    log.info(f"  Join request sent for {group.name} (may be pending approval)")
                else:
                    log.info(f"  No Join button found for {group.name} — may need manual join")
            except Exception as e:
                log.error(f"  Error joining {group.name}: {e}")

        # Save session
        await context.storage_state(path=str(account.get_session_path()))
        await context.browser.close()

    log.info("Group join process complete.")


# --- CLI entry point ---

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Facebook Group Listing Scraper (Patchright)")
    sub = ap.add_subparsers(dest="command", help="Command to run")

    # scrape command (default)
    scrape_p = sub.add_parser("scrape", help="Scrape configured groups")
    scrape_p.add_argument("--visible", action="store_true", help="Run with visible browser")
    scrape_p.add_argument("--group", type=str, help="Scrape only this group URL")
    scrape_p.add_argument("--max-scrolls", type=int, default=50, help="Max scrolls per group")
    scrape_p.add_argument("--max-posts", type=int, default=200, help="Max posts per group")
    scrape_p.add_argument("--account", type=str, help="Use specific account label")

    # setup command
    setup_p = sub.add_parser("setup", help="Setup account — manual login to save session")
    setup_p.add_argument("label", type=str, help="Account label (from config)")

    # join command
    join_p = sub.add_parser("join", help="Auto-join configured groups")

    args = ap.parse_args()

    if args.command == "setup":
        asyncio.run(setup_account(args.label))
        return

    if args.command == "join":
        asyncio.run(join_groups())
        return

    # Default: scrape
    config = load_config()

    if hasattr(args, 'visible') and args.visible:
        config.headless = False

    if hasattr(args, 'group') and args.group:
        m = re.search(r'/groups/([^/?#]+)', args.group)
        gid = m.group(1) if m else "unknown"
        config.groups = [GroupConfig(
            url=args.group,
            name=gid,
            group_id=gid,
            max_scrolls=args.max_scrolls if hasattr(args, 'max_scrolls') else 50,
            max_posts=args.max_posts if hasattr(args, 'max_posts') else 200,
        )]

    if hasattr(args, 'max_scrolls'):
        for g in config.groups:
            g.max_scrolls = args.max_scrolls
    if hasattr(args, 'max_posts'):
        for g in config.groups:
            g.max_posts = args.max_posts

    asyncio.run(run_scraper(config))


if __name__ == "__main__":
    main()
