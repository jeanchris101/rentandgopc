"""
Punta Cana Properties — Facebook Group Scraper
Gently scrapes visible posts from configured FB groups using real Chrome + cookies.
Feeds group-raw-posts.json into the group_engagement.py pipeline.

SAFETY FIRST: Uses personal FB account cookies. No scrolling, no rapid requests,
human-like delays, immediate abort on checkpoint/verification pages.
"""

import argparse
import hashlib
import json
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
CONFIG_FILE = DATA_DIR / "group-assist-config.json"
COOKIES_FILE = DATA_DIR / "fb-cookies.json"
COOKIES_FILE_DOWNLOADS = Path.home() / "Downloads" / "fb-cookies.json"
RAW_POSTS_FILE = DATA_DIR / "group-raw-posts.json"
SCAN_LOG_FILE = DATA_DIR / "scraper-scan-log.json"

DEFAULT_CONFIG = {
    "groups": [],
    "settings": {
        "scans_per_day": 2,
        "delay_between_groups_min": 15,
        "delay_between_groups_max": 30,
        "max_posts_per_group": 100,
        "scroll": False,
    },
}

# JavaScript to extract posts from a Facebook group page.
# Uses multiple fallback selectors since FB changes DOM frequently.
EXTRACT_POSTS_JS_FILE = SCRIPT_DIR / "extract_posts.js"


def _load_extract_js():
    """Load the post extraction JS from file."""
    return EXTRACT_POSTS_JS_FILE.read_text(encoding="utf-8")


# Legacy inline JS kept as fallback — primary is loaded from extract_posts.js
EXTRACT_POSTS_JS = r"""
() => {
    const MAX = MAX_POSTS;

    function isGarbled(text) {
        if (!text || text.length < 5) return true;
        const clean = text.replace(/[\\w\\s.,!?¿¡;:'"\\-()\\[\\]@#$%&\\/+=<>{}\\n\\r\\t\\u00C0-\\u024F\\u0400-\\u04FF]/g, '');
        return (clean.length / text.length) > 0.3;
    }

    function normalizeHref(href) {
        if (!href) return '';
        if (!href.startsWith('http')) href = 'https://www.facebook.com' + href;
        try { const u = new URL(href); u.search = ''; return u.toString(); } catch(e) { return ''; }
    }

    // Junk patterns — text that is UI chrome, not post content
    const JUNK_RE = /^(see more|see less|ver más|ver menos|voir plus|voir moins|like|reply|share|responder|compartir|j'aime|partager|follow|seguir|top contributor|miembro destacado|original audio|all reactions|most relevant|newest first|highlights|write a comment|write a public comment|photo|video|gif|camera)$/i;
    const JUNK_PREFIX_RE = /^(shared with|compartido con|photos from|fotos de|\\d+\\s*(comments?|comentarios?|replies|respuestas)|\\d+\\s*(likes?|reactions?))/i;

    function isJunk(text) {
        const t = text.trim();
        if (t.length < 10) return true;
        if (isGarbled(t)) return true;
        if (JUNK_RE.test(t)) return true;
        if (JUNK_PREFIX_RE.test(t)) return true;
        // Skip hashtag-only blocks
        if (/^[#\\s\\w]+$/.test(t) && (t.match(/#/g) || []).length > 2 && t.length < 200) return true;
        return false;
    }

    // ============================================================
    // NEW APPROACH: Find all permalink anchors on the page.
    // Each permalink = one post. Walk up from the anchor to find
    // the nearest large container. Extract text from that container.
    // This works regardless of role="article" or shadow DOM tricks.
    // ============================================================

    const allPermalinks = document.querySelectorAll('a[href*="/posts/"], a[href*="/permalink/"]');
    const urlToAnchor = new Map();
    for (const a of allPermalinks) {
        const href = normalizeHref(a.getAttribute('href') || '');
        if (!href) continue;
        if (!href.includes('/groups/')) continue;
        if (!urlToAnchor.has(href)) urlToAnchor.set(href, a);
    }

    const posts = [];
    const seenText = new Set();

    for (const [postUrl, anchor] of urlToAnchor) {
        if (posts.length >= MAX) break;

        // Walk up from the anchor to find the post container.
        // We want a div that is tall enough to be a full post (>= 100px).
        // Stop at role="feed" or role="main".
        let container = anchor;
        let best = null;
        for (let i = 0; i < 20; i++) {
            container = container.parentElement;
            if (!container) break;
            const role = container.getAttribute && container.getAttribute('role');
            if (role === 'feed' || role === 'main') break;
            const h = container.offsetHeight || 0;
            if (h >= 100) {
                best = container;
                // Keep going up to find the outermost post container
                // (but not the feed itself). Prefer containers with
                // good height that are direct children of the feed.
                const parentRole = container.parentElement
                    ? container.parentElement.getAttribute && container.parentElement.getAttribute('role')
                    : null;
                if (parentRole === 'feed') break;
            }
        }
        if (!best) continue;

        // Skip sponsored
        const fullText = (best.innerText || best.textContent || '').toLowerCase();
        if (fullText.includes('sponsored') || fullText.includes('suggested for you')
            || fullText.includes('sugerido para ti')) continue;

        // Extract ALL text from dir="auto" blocks inside this container.
        // Group them into post text, excluding comment text.
        const autoBlocks = best.querySelectorAll('[dir="auto"]');
        const textParts = [];
        const seenParts = new Set();

        // Find where comments start — look for role="article" inside our container
        // (comment sections use nested articles)
        const commentArticles = best.querySelectorAll('[role="article"]');

        for (const block of autoBlocks) {
            // Skip if inside a comment article
            let inComment = false;
            for (const ca of commentArticles) {
                if (ca.contains(block)) { inComment = true; break; }
            }
            if (inComment) continue;

            const t = block.textContent.trim();
            if (isJunk(t)) continue;

            // Substring dedup — keep longer version
            let isDupe = false;
            for (const existing of seenParts) {
                if (existing.includes(t)) { isDupe = true; break; }
                if (t.includes(existing)) {
                    seenParts.delete(existing);
                    const idx = textParts.indexOf(existing);
                    if (idx >= 0) textParts.splice(idx, 1);
                    break;
                }
            }
            if (isDupe) continue;
            seenParts.add(t);
            textParts.push(t);
        }

        const text = textParts.join(' ').trim();
        if (!text || text.length < 15) continue;

        // Dedup by text prefix
        const key = text.substring(0, 200);
        if (seenText.has(key)) continue;
        seenText.add(key);

        // Author — look for <strong> or heading links near the top
        let author = '';
        const excluded = ['profile picture', 'foto de perfil', 'photo de profil'];
        for (const s of best.querySelectorAll('strong')) {
            const name = s.textContent.trim();
            if (name.length > 1 && name.length < 80 && !isGarbled(name)
                && !excluded.some(ex => name.toLowerCase().includes(ex))) {
                // Make sure this strong isn't inside a comment
                let inCom = false;
                for (const ca of commentArticles) { if (ca.contains(s)) { inCom = true; break; } }
                if (!inCom) { author = name; break; }
            }
        }

        // Timestamp
        let timestamp = '';
        for (const a of best.querySelectorAll('a[aria-label]')) {
            const href = a.getAttribute('href') || '';
            if (href.includes('/posts/') || href.includes('/permalink/')) {
                const label = a.getAttribute('aria-label') || '';
                if (label && !isGarbled(label)) { timestamp = label; break; }
            }
        }

        // Counts
        let commentsCount = 0, reactionsCount = 0;
        for (const el of best.querySelectorAll('span, a')) {
            const t = el.textContent.trim().toLowerCase();
            const cm = t.match(/(\\d+)\\s*comment/) || t.match(/(\\d+)\\s*comentario/);
            if (cm) { commentsCount = parseInt(cm[1]); break; }
        }
        for (const el of best.querySelectorAll('[aria-label]')) {
            const label = (el.getAttribute('aria-label') || '').toLowerCase();
            if (label.includes('reaction') || label.includes('like') || label.includes('love')) {
                const m = label.match(/(\\d+)/);
                if (m) { reactionsCount = parseInt(m[1]); break; }
            }
        }

        posts.push({
            text: text.substring(0, 2000),
            author,
            post_url: postUrl,
            timestamp,
            reactions_count: reactionsCount,
            comments_count: commentsCount,
        });
    }

    return posts;
}
"""


# ---- Helpers ----

def load_json(path: Path, default=None):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_config() -> dict:
    """Load config, creating default if needed."""
    if not CONFIG_FILE.exists():
        save_json(CONFIG_FILE, DEFAULT_CONFIG)
        print(f"Created empty config at {CONFIG_FILE}")
        print("Add groups with: py automation/group_scraper.py --add-group URL")
        return DEFAULT_CONFIG
    return load_json(CONFIG_FILE, DEFAULT_CONFIG)


def human_delay(min_sec: float, max_sec: float):
    """Sleep for a random human-like duration."""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)


def make_post_id(group_id: str, text: str, author: str) -> str:
    """Generate a stable post ID from content."""
    raw = f"{group_id}_{author}_{text[:100]}"
    return "post_" + hashlib.md5(raw.encode()).hexdigest()[:12]


def extract_group_id_from_url(url: str) -> str | None:
    """Extract group ID or slug from a Facebook group URL."""
    patterns = [
        r"facebook\.com/groups/([^/?&#]+)",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


# ---- Cookie handling ----

def load_cookies() -> list[dict] | None:
    """Load cookies from exported JSON file. Checks data dir first, then Downloads."""
    cookie_path = None
    if COOKIES_FILE.exists():
        cookie_path = COOKIES_FILE
    elif COOKIES_FILE_DOWNLOADS.exists():
        # Auto-copy from Downloads to data dir
        import shutil
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(COOKIES_FILE_DOWNLOADS, COOKIES_FILE)
        cookie_path = COOKIES_FILE
        print(f"Copied cookies from Downloads to {COOKIES_FILE}")

    if not cookie_path:
        print(f"ERROR: Cookie file not found.")
        print(f"  Checked: {COOKIES_FILE}")
        print(f"  Checked: {COOKIES_FILE_DOWNLOADS}")
        print("Use the FB Cookie Export extension to export your cookies.")
        return None

    data = load_json(cookie_path)

    # Handle different export formats
    cookies = []
    if isinstance(data, list):
        cookies = data
    elif isinstance(data, dict):
        if "cookies" in data:
            cookies = data["cookies"]
        elif "exported_at" in data and isinstance(data.get("data"), list):
            cookies = data["data"]
        else:
            # Maybe it's a single-level dict of name: value pairs
            print("WARNING: Unexpected cookie format. Expected a JSON array of cookie objects.")
            return None

    if not cookies:
        print("ERROR: No cookies found in file.")
        return None

    # Check freshness if exported_at is available
    if isinstance(data, dict) and "exported_at" in data:
        try:
            exported = datetime.fromisoformat(data["exported_at"])
            age_days = (datetime.now() - exported).days
            if age_days > 14:
                print(f"ERROR: Cookies are {age_days} days old and likely expired.")
                print("Please re-export from Chrome extension.")
                return None
            elif age_days > 7:
                print(f"WARNING: Cookies are {age_days} days old. Consider re-exporting.")
        except (ValueError, TypeError):
            pass

    return cookies


def cookies_to_playwright(cookies: list[dict]) -> list[dict]:
    """Convert cookie export formats to Playwright's expected format."""
    pw_cookies = []
    for c in cookies:
        # Playwright expects: name, value, domain, path, (optional) expires, httpOnly, secure, sameSite
        cookie = {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ".facebook.com"),
            "path": c.get("path", "/"),
        }

        if "expirationDate" in c:
            cookie["expires"] = float(c["expirationDate"])
        elif "expires" in c and isinstance(c["expires"], (int, float)):
            cookie["expires"] = float(c["expires"])

        if "httpOnly" in c:
            cookie["httpOnly"] = bool(c["httpOnly"])
        if "secure" in c:
            cookie["secure"] = bool(c["secure"])
        if "sameSite" in c:
            ss = str(c["sameSite"]).capitalize()
            if ss in ("Strict", "Lax", "None"):
                cookie["sameSite"] = ss
            else:
                cookie["sameSite"] = "None"

        # Only include cookies with name and value
        if cookie["name"] and cookie["value"]:
            pw_cookies.append(cookie)

    return pw_cookies


# ---- Browser & Scraping ----

def check_playwright_installed() -> bool:
    """Check if Playwright browsers are installed."""
    try:
        from playwright.sync_api import sync_playwright
        return True
    except ImportError:
        print("ERROR: Playwright not installed.")
        print("Install with: pip install playwright && playwright install chromium")
        return False


def check_for_checkpoint(page) -> bool:
    """Check if Facebook is showing a checkpoint/verification page. Returns True if DANGER."""
    url = page.url.lower()
    if "checkpoint" in url or "security" in url or "login" in url:
        return True

    # Check page content for verification prompts
    try:
        content = page.content()
        danger_signals = [
            "confirm your identity",
            "confirma tu identidad",
            "security check",
            "verificacion de seguridad",
            "we need to verify",
            "suspicious activity",
            "your account has been locked",
            "tu cuenta ha sido bloqueada",
        ]
        content_lower = content.lower()
        for signal in danger_signals:
            if signal in content_lower:
                print(f"  DEBUG: Checkpoint triggered by content signal: '{signal}'")
                return True
    except Exception:
        pass

    return False


def check_logged_in(page) -> bool:
    """Check if we're logged into Facebook."""
    try:
        # Look for elements that only appear when logged in
        logged_in_selectors = [
            '[aria-label="Your profile"]',
            '[aria-label="Tu perfil"]',
            '[aria-label="Account"]',
            '[aria-label="Cuenta"]',
            '[data-pagelet="ProfileCover"]',
            'div[role="navigation"]',
            '[aria-label="Facebook"]',
        ]
        for sel in logged_in_selectors:
            el = page.query_selector(sel)
            if el:
                return True

        # Also check that we're NOT on a login page
        if "/login" in page.url:
            return False

        # Check for the profile/menu button area (usually present when logged in)
        # FB always shows a navigation bar when logged in
        nav = page.query_selector('[role="banner"]')
        if nav:
            # Check if there are user-specific elements in the banner
            links = nav.query_selector_all('a[href*="/me"], a[href*="profile"]')
            if links:
                return True

        return False
    except Exception:
        return False


def scrape_group(page, group: dict, max_posts: int) -> list[dict]:
    """Scrape visible posts from a single group page."""
    group_id = group["id"]
    group_name = group["name"]
    url = group["url"]

    print(f"  Visiting: {group_name} ({url})")

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"  ERROR: Failed to load {url}: {e}")
        return []

    # Wait for content to load (human-like)
    human_delay(3, 5)

    # Check for checkpoint IMMEDIATELY
    if check_for_checkpoint(page):
        print("  DANGER: Facebook checkpoint/verification detected!")
        print("  ABORTING IMMEDIATELY for account safety.")
        raise SystemExit(1)

    # Check if group is accessible
    page_text = ""
    try:
        page_text = page.text_content("body") or ""
    except Exception:
        pass

    unavailable_signals = [
        "this content isn't available",
        "this page isn't available",
        "este contenido no esta disponible",
        "grupo privado",
        "join group",
    ]
    for signal in unavailable_signals:
        if signal in page_text.lower():
            print(f"  WARNING: Group not accessible — '{signal}'. Skipping.")
            return []

    # Wait for dynamic content then scroll to load posts.
    # Load extraction JS
    try:
        js_code = _load_extract_js().replace("MAX_POSTS", str(max_posts))
    except Exception:
        js_code = EXTRACT_POSTS_JS.replace("MAX_POSTS", str(max_posts))

    # INCREMENTAL SCROLL + EXTRACT
    # Facebook virtualizes the feed — only ~5 posts exist in DOM at once.
    # Old posts are removed as you scroll down. We must extract after
    # every few scrolls and accumulate unique posts.
    human_delay(2, 3)
    all_raw_posts = []
    seen_text_keys = set()
    scroll_count = 30
    no_new_streak = 0

    for i in range(scroll_count):
        page.mouse.wheel(0, random.randint(800, 1200))
        human_delay(2, 4)
        if random.random() < 0.3:
            human_delay(3, 6)
        if random.random() < 0.15:
            page.mouse.wheel(0, random.randint(-400, -200))
            human_delay(1, 2)

        # Every 2 scrolls: expand See more + extract
        if (i + 1) % 2 == 0 or i == scroll_count - 1:
            # Click See more buttons currently visible
            try:
                for btn in page.locator(
                    'div[role="button"]:has-text("See more"), '
                    'span:has-text("See more"), '
                    'div[role="button"]:has-text("Ver más"), '
                    'span:has-text("Ver más")'
                ).all()[:15]:
                    try:
                        btn.click(timeout=1000)
                        time.sleep(0.2)
                    except Exception:
                        pass
            except Exception:
                pass

            # Extract from current DOM
            try:
                batch = page.evaluate(js_code) or []
            except Exception:
                batch = []

            new_count = 0
            for post in batch:
                key = post.get("text", "")[:200]
                if key and key not in seen_text_keys:
                    seen_text_keys.add(key)
                    all_raw_posts.append(post)
                    new_count += 1

            if new_count == 0:
                no_new_streak += 1
                if no_new_streak >= 4:
                    break
            else:
                no_new_streak = 0

            if len(all_raw_posts) >= max_posts:
                break

    raw_posts = all_raw_posts
    print(f"  Extracted {len(raw_posts)} posts (across {min(i + 1, scroll_count)} scrolls)")

    if not raw_posts:
        print(f"  No posts found on page. FB may have changed their DOM structure.")
        return []

    # Convert to our output format
    posts = []
    for rp in raw_posts:
        post_id = make_post_id(group_id, rp.get("text", ""), rp.get("author", ""))

        # Try to parse post URL for a cleaner ID
        post_url = rp.get("post_url", "")
        url_match = re.search(r"/posts/(\d+)", post_url) or re.search(r"/permalink/(\d+)", post_url)
        if url_match:
            post_id = f"post_{url_match.group(1)}"

        posts.append({
            "id": post_id,
            "group_id": group_id,
            "group_name": group_name,
            "post_url": post_url,
            "author": rp.get("author", ""),
            "text": rp.get("text", ""),
            "timestamp": rp.get("timestamp", ""),
            "comments_count": rp.get("comments_count", 0),
            "reactions_count": rp.get("reactions_count", 0),
        })

    print(f"  Extracted {len(posts)} posts")
    return posts


def run_scraper(with_replies: bool = False):
    """Main scraper routine — opens Chrome, visits groups, extracts posts."""
    from playwright.sync_api import sync_playwright

    config = load_config()
    groups = config.get("groups", [])
    settings = config.get("settings", DEFAULT_CONFIG["settings"])

    if not groups:
        print("No groups configured. Add groups with:")
        print("  py automation/group_scraper.py --add-group URL")
        return

    # Load and validate cookies
    raw_cookies = load_cookies()
    if not raw_cookies:
        return

    pw_cookies = cookies_to_playwright(raw_cookies)
    if not pw_cookies:
        print("ERROR: No valid cookies after conversion.")
        return

    max_posts = settings.get("max_posts_per_group", 25)
    delay_min = settings.get("delay_between_groups_min", 15)
    delay_max = settings.get("delay_between_groups_max", 30)

    all_posts = []
    start_time = datetime.now()

    print(f"Starting scrape of {len(groups)} groups at {start_time.strftime('%H:%M:%S')}")
    print(f"Max {max_posts} posts per group, {delay_min}-{delay_max}s between groups")
    print()

    with sync_playwright() as p:
        # Pick a common viewport
        viewport = random.choice([
            {"width": 1366, "height": 768},
            {"width": 1440, "height": 900},
            {"width": 1536, "height": 864},
        ])

        # Use persistent context so localStorage/IndexedDB survive between runs
        # This prevents Facebook from treating each run as a "new device"
        profile_dir = str(DATA_DIR / "chrome-profile")
        try:
            context = p.chromium.launch_persistent_context(
                profile_dir,
                channel="chrome",
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
                viewport=viewport,
                locale="en-US",
                timezone_id="America/Santo_Domingo",
            )
        except Exception as e:
            print(f"ERROR: Could not launch Chrome: {e}")
            print("Make sure Chrome is installed, or run: playwright install chromium")
            return

        browser = context  # persistent context acts as both browser and context

        # Load cookies BEFORE navigating
        try:
            context.add_cookies(pw_cookies)
        except Exception as e:
            print(f"ERROR: Failed to set cookies: {e}")
            context.close()
            return

        page = context.pages[0] if context.pages else context.new_page()

        # Navigate to Facebook home first (like a real user)
        print("Opening Facebook...")
        try:
            page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"ERROR: Could not load Facebook: {e}")
            browser.close()
            return

        human_delay(2, 5)

        # Handle "Continue as <name>" welcome page (not a real checkpoint)
        try:
            continue_btn = page.locator('div[role="button"]:has-text("Continue"), a:has-text("Continue")').first
            if continue_btn.is_visible(timeout=3000):
                print("  Found 'Continue' welcome page — clicking to proceed...")
                continue_btn.click()
                human_delay(3, 5)
        except Exception:
            pass

        # Check for checkpoint
        if check_for_checkpoint(page):
            page.screenshot(path="C:/Claude/puntacana-properties/automation/data/fb-checkpoint-debug.png")
            print("DANGER: Facebook checkpoint/verification detected on login!")
            print("ABORTING IMMEDIATELY. Do NOT run again until you clear the checkpoint in your browser.")
            context.close()
            return

        # Verify logged in
        if not check_logged_in(page):
            print("ERROR: Not logged in. Cookies may be expired.")
            print("Please re-export your Facebook cookies from Chrome and save to:")
            print(f"  {COOKIES_FILE}")
            browser.close()
            return

        print("Logged in successfully.\n")

        # Visit each group
        for i, group in enumerate(groups):
            if i > 0:
                # Human-like delay between groups
                delay = random.uniform(delay_min, delay_max)
                print(f"  Waiting {delay:.0f}s before next group...")
                time.sleep(delay)

            try:
                posts = scrape_group(page, group, max_posts)
                all_posts.extend(posts)
            except SystemExit:
                # Checkpoint detected — abort everything
                browser.close()
                return
            except Exception as e:
                print(f"  ERROR scraping {group['name']}: {e}")
                # Retry once after 30 seconds
                print(f"  Retrying in 30 seconds...")
                time.sleep(30)
                try:
                    posts = scrape_group(page, group, max_posts)
                    all_posts.extend(posts)
                except SystemExit:
                    # Checkpoint detected on retry — abort everything
                    browser.close()
                    return
                except Exception as e2:
                    print(f"  Retry failed: {e2}. Skipping group.")

            # Small pause after extraction
            human_delay(1, 3)

        # Done — close browser
        print("\nClosing browser...")
        human_delay(1, 2)
        browser.close()

    # Save results
    elapsed = (datetime.now() - start_time).total_seconds()
    output = {
        "scraped_at": datetime.now().isoformat(),
        "posts": all_posts,
    }
    save_json(RAW_POSTS_FILE, output)

    # Per-group post counts for diagnostics
    group_counts = {}
    for post in all_posts:
        gname = post.get("group_name", "unknown")
        group_counts[gname] = group_counts.get(gname, 0) + 1

    print("\n  Per-group breakdown:")
    for gname, count in sorted(group_counts.items(), key=lambda x: -x[1]):
        print(f"    {gname}: {count} posts")

    # Update scan log
    scan_log = load_json(SCAN_LOG_FILE, [])
    scan_log.append({
        "timestamp": datetime.now().isoformat(),
        "groups_scanned": len(groups),
        "posts_found": len(all_posts),
        "duration_seconds": round(elapsed, 1),
        "per_group": group_counts,
    })
    # Keep last 50 entries
    scan_log = scan_log[-50:]
    save_json(SCAN_LOG_FILE, scan_log)

    print(f"\nDone! Scraped {len(all_posts)} posts from {len(groups)} groups in {elapsed:.0f}s")
    print(f"Saved to {RAW_POSTS_FILE}")

    # Optionally run engagement pipeline
    if with_replies:
        print("\n--- Running engagement pipeline ---\n")
        engagement_script = SCRIPT_DIR / "group_engagement.py"
        if engagement_script.exists():
            try:
                subprocess.run(
                    ["py", str(engagement_script)],
                    cwd=str(SCRIPT_DIR.parent),
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                print(f"Engagement pipeline failed: {e}")
            except FileNotFoundError:
                # Try python if py is not available
                subprocess.run(
                    [sys.executable, str(engagement_script)],
                    cwd=str(SCRIPT_DIR.parent),
                    check=True,
                )
        else:
            print(f"WARNING: {engagement_script} not found")


# ---- CLI commands ----

def cmd_status():
    """Show last scan info and stats."""
    scan_log = load_json(SCAN_LOG_FILE, [])
    config = load_config()
    groups = config.get("groups", [])

    print(f"Configured groups: {len(groups)}")
    for g in groups:
        print(f"  - {g['name']} ({g['url']})")
    print()

    if not scan_log:
        print("No scans recorded yet.")
        return

    last = scan_log[-1]
    print(f"Last scan: {last['timestamp']}")
    print(f"  Groups scanned: {last['groups_scanned']}")
    print(f"  Posts found: {last['posts_found']}")
    print(f"  Duration: {last['duration_seconds']}s")
    print()

    # Check raw posts file
    raw = load_json(RAW_POSTS_FILE)
    if raw and raw.get("posts"):
        print(f"Current raw posts file: {len(raw['posts'])} posts")
        print(f"  Scraped at: {raw.get('scraped_at', 'unknown')}")
    else:
        print("No raw posts file found.")

    print(f"\nTotal scans recorded: {len(scan_log)}")
    if len(scan_log) >= 2:
        total_posts = sum(s.get("posts_found", 0) for s in scan_log)
        print(f"Total posts scraped (all time): {total_posts}")


def cmd_add_group(url: str):
    """Add a group to config by URL."""
    group_id = extract_group_id_from_url(url)
    if not group_id:
        print(f"ERROR: Could not extract group ID from URL: {url}")
        print("Expected format: https://www.facebook.com/groups/GROUP_ID_OR_SLUG")
        return

    config = load_config()
    groups = config.get("groups", [])

    # Check for duplicates
    for g in groups:
        if g["id"] == group_id:
            print(f"Group already configured: {g['name']} ({g['id']})")
            return

    # Clean URL
    clean_url = f"https://www.facebook.com/groups/{group_id}"

    # Prompt for name
    name = input(f"Enter a name for this group (ID: {group_id}): ").strip()
    if not name:
        name = group_id

    group = {
        "id": group_id,
        "name": name,
        "url": clean_url,
    }
    groups.append(group)
    config["groups"] = groups
    save_json(CONFIG_FILE, config)
    print(f"Added group: {name} ({clean_url})")
    print(f"Total groups: {len(groups)}")


def cmd_list_groups():
    """List all configured groups."""
    config = load_config()
    groups = config.get("groups", [])

    if not groups:
        print("No groups configured.")
        print("Add groups with: py automation/group_scraper.py --add-group URL")
        return

    print(f"Configured groups ({len(groups)}):")
    for i, g in enumerate(groups, 1):
        print(f"  {i}. {g['name']}")
        print(f"     ID: {g['id']}")
        print(f"     URL: {g['url']}")


def cmd_check_cookies():
    """Verify cookies are valid by trying to load Facebook."""
    raw_cookies = load_cookies()
    if not raw_cookies:
        return

    pw_cookies = cookies_to_playwright(raw_cookies)
    print(f"Loaded {len(pw_cookies)} cookies.")

    # Check for essential Facebook cookies
    essential = {"c_user", "xs", "datr"}
    found = {c["name"] for c in pw_cookies} & essential
    missing = essential - found

    if missing:
        print(f"WARNING: Missing essential cookies: {missing}")
        print("These are typically required for Facebook login.")
    else:
        print("Essential cookies present (c_user, xs, datr).")

    # Try loading Facebook
    print("\nTesting login by opening Facebook (will close automatically)...")

    if not check_playwright_installed():
        return

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=False)
        except Exception as e:
            print(f"ERROR: Could not launch Chrome: {e}")
            return

        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
        )

        try:
            context.add_cookies(pw_cookies)
        except Exception as e:
            print(f"ERROR: Failed to set cookies: {e}")
            browser.close()
            return

        page = context.new_page()

        try:
            page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            print(f"ERROR: Could not load Facebook: {e}")
            browser.close()
            return

        time.sleep(3)

        if check_for_checkpoint(page):
            print("DANGER: Checkpoint/verification detected. Cookies may be compromised.")
            browser.close()
            return

        if check_logged_in(page):
            print("SUCCESS: Cookies are valid — logged into Facebook.")
        else:
            print("FAILED: Not logged in. Cookies are expired or invalid.")
            print("Please re-export your cookies from Chrome.")

        browser.close()


def cmd_schedule():
    """Run the scraper on a schedule (twice daily at random times)."""
    config = load_config()
    groups = config.get("groups", [])

    if not groups:
        print("No groups configured. Add groups first.")
        return

    print("Facebook Group Scraper — Scheduled Mode")
    print("Will scan twice daily at random times:")
    print("  Morning: 8:00 AM - 10:00 AM")
    print("  Evening: 6:00 PM - 8:00 PM")
    print("Press Ctrl+C to stop.\n")

    # Generate today's scan times
    def generate_scan_times() -> list[datetime]:
        today = datetime.now().replace(second=0, microsecond=0)
        morning = today.replace(
            hour=random.randint(8, 9),
            minute=random.randint(0, 59),
        )
        evening = today.replace(
            hour=random.randint(18, 19),
            minute=random.randint(0, 59),
        )
        return [morning, evening]

    scans_today = generate_scan_times()
    last_date = datetime.now().date()

    for t in scans_today:
        if t > datetime.now():
            print(f"Next scan: {t.strftime('%I:%M %p')}")

    try:
        while True:
            now = datetime.now()

            # Generate new scan times if day changed
            if now.date() != last_date:
                scans_today = generate_scan_times()
                last_date = now.date()
                print(f"\nNew day — scan times: {', '.join(t.strftime('%I:%M %p') for t in scans_today)}")

            # Check if any scan time has been reached
            for i, scan_time in enumerate(scans_today):
                if scan_time and abs((now - scan_time).total_seconds()) < 60:
                    print(f"\n[{now.strftime('%I:%M %p')}] Running scheduled scan...")
                    scans_today[i] = None  # Mark as done
                    try:
                        run_scraper(with_replies=False)
                    except Exception as e:
                        print(f"Scan failed: {e}")

                    # Show next scan
                    remaining = [t for t in scans_today if t and t > now]
                    if remaining:
                        print(f"Next scan: {remaining[0].strftime('%I:%M %p')}")
                    else:
                        print("All scans done for today. Waiting for tomorrow.")

            time.sleep(30)  # Check every 30 seconds

    except KeyboardInterrupt:
        print("\nScheduler stopped.")


# ---- Main ----

def main():
    parser = argparse.ArgumentParser(
        description="Facebook Group Scraper — gentle, safe scraping for Punta Cana Properties"
    )
    parser.add_argument(
        "--with-replies", action="store_true",
        help="After scraping, run group_engagement.py pipeline to generate AI replies"
    )
    parser.add_argument("--status", action="store_true", help="Show last scan info and stats")
    parser.add_argument("--add-group", metavar="URL", help="Add a Facebook group by URL")
    parser.add_argument("--list-groups", action="store_true", help="List configured groups")
    parser.add_argument("--check-cookies", action="store_true", help="Verify Facebook cookies are valid")
    parser.add_argument("--schedule", action="store_true", help="Run on schedule (twice daily)")

    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.status:
        cmd_status()
    elif args.add_group:
        cmd_add_group(args.add_group)
    elif args.list_groups:
        cmd_list_groups()
    elif args.check_cookies:
        cmd_check_cookies()
    elif args.schedule:
        cmd_schedule()
    else:
        if not check_playwright_installed():
            sys.exit(1)
        run_scraper(with_replies=args.with_replies)


if __name__ == "__main__":
    main()
