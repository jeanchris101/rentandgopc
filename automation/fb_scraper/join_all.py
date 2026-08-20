"""
Join Facebook groups — improved approach:
1. Visit /groups/joins/ to get list of already-joined groups
2. Use /search/groups/?q=QUERY with longer waits + scroll for results
3. Extract only from main content area (skip sidebar/notifications)
"""
import asyncio
import random
import json
import logging
import sys
import urllib.parse
from pathlib import Path
from patchright.async_api import async_playwright
from config import load_config, JOIN_GROUP_ANSWERS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger()

GROUPS_TO_JOIN = [
    "Clasificados Bávaro Punta Cana",
    "Alquiler y Venta en Higüey Bávaro y Punta Cana",
    "Clasificado Punta Cana",
    "Ventas en Bávaro Punta Cana",
    "Dominican Expats Buy Sell or Rent",
    "Real Estate Dominican Republic",
    "Condo maison à louer ou à vendre en République Dominicaine",
    "Gente que vive en Cocotal",
    "Los Buenos Vecinos de Cocotal",
    "Alquileres y Ventas De INMUEBLES en COCOTAL Palma Real Villas",
    "Cocotal ventas",
    "Gente que vive en Cocotal Residents of Cocotal",
    "Expats in Bavaro",
    "Expats living in The Dominican Republic",
    "Canadien et Québécois en République Dominicaine",
    "Les Snowbirds Quebecois de la République Dominicaine",
    "Québécois en République Dominicaine",
    "Québécois à Punta Cana",
    "Residentes de Costa Bávaro IFA Villas Bávaro",
    "Vecinos De IFA y Costa Bavaro",
]

DATA_DIR = Path("/opt/data")
JOINED_PATH = DATA_DIR / "joined_groups.json"
FAILED_PATH = DATA_DIR / "failed_groups.json"


def load_existing_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return []


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


async def get_already_joined(page):
    """Visit /groups/joins/ and extract all joined group slugs."""
    log.info("Fetching already-joined groups from /groups/joins/ ...")
    already = set()
    try:
        await page.goto(
            "https://www.facebook.com/groups/joins/",
            wait_until="commit",
            timeout=45000,
        )
        await asyncio.sleep(5)

        # Scroll a few times to load more
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(1.5)

        slugs = await page.evaluate("""
            () => {
                const results = new Set();
                const links = document.querySelectorAll('a[href*="/groups/"]');
                for (const a of links) {
                    const href = a.href || '';
                    const m = href.match(/\\/groups\\/([^/?#]+)/);
                    if (!m) continue;
                    const slug = m[1].toLowerCase();
                    if (['feed', 'discover', 'joins', 'search', 'create', 'notifications'].includes(slug)) continue;
                    results.add(slug);
                }
                return [...results];
            }
        """)
        for s in slugs:
            already.add(s)
        log.info("  Found %d already-joined groups", len(already))
    except Exception as e:
        log.warning("  Could not fetch joined groups: %s", e)
    return already


async def search_for_group(page, group_name):
    """
    Search Facebook for a group by name.
    Returns list of {url, name, gid} dicts from the main results area.
    """
    encoded = urllib.parse.quote(group_name)
    search_url = "https://www.facebook.com/search/groups/?q=" + encoded
    log.info("  Searching: %s", search_url)

    try:
        await page.goto(search_url, wait_until="commit", timeout=45000)
    except Exception as e:
        log.error("  Failed to load search: %s", e)
        # Try to wait anyway in case page partially loaded
        await asyncio.sleep(3)
        current_url = page.url
        if "search/groups" not in current_url:
            return []

    # Wait longer for results to load fully
    await asyncio.sleep(random.uniform(7, 9))

    # Scroll down to trigger lazy-loaded results
    for _ in range(3):
        await page.evaluate("window.scrollBy(0, 600)")
        await asyncio.sleep(1.5)

    # Extract groups from search results
    # Key insight: search result group links have role="presentation" and text content
    # Notification links have notif_id/comment_id in URL - skip those
    results = await page.evaluate("""
        () => {
            const groups = [];
            const seen = new Set();
            const skipSlugs = new Set(['feed', 'discover', 'joins', 'search', 'create', 'notifications']);

            // Get ALL group links on the page
            const links = document.querySelectorAll('a[href*="/groups/"]');
            for (const a of links) {
                const href = a.href || '';

                // Skip notification/comment links
                if (href.includes('notif_id') || href.includes('comment_id') || href.includes('post_id')) continue;
                // Skip search URL itself
                if (href.includes('/search/groups/')) continue;

                const m = href.match(/\\/groups\\/([^/?#]+)/);
                if (!m) continue;
                const gid = m[1];
                const lower = gid.toLowerCase();
                if (seen.has(lower) || skipSlugs.has(lower)) continue;

                // Get the link text
                let name = a.textContent.trim();
                // Skip empty or very short text (these are thumbnail links)
                if (name.length < 3) continue;
                // Skip if starts with "Unread" (notification text)
                if (name.startsWith('Unread')) continue;
                // Skip pure numbers
                if (/^\\d+$/.test(name)) continue;

                seen.add(lower);
                groups.push({
                    url: 'https://www.facebook.com/groups/' + gid + '/',
                    name: name.substring(0, 150),
                    gid: gid,
                });
            }
            return groups.slice(0, 10);
        }
    """)
    return results


def name_similarity(a, b):
    """Simple word-overlap similarity between two group names."""
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    overlap = wa & wb
    return len(overlap) / max(len(wa), len(wb))


async def join_group_page(page, group_url, group_name):
    """
    Navigate to a group page and click Join.
    Returns status string: joined, already_member, pending, no_button, error
    """
    try:
        await page.goto(group_url, wait_until="commit", timeout=45000)
        await asyncio.sleep(random.uniform(4, 6))
    except Exception as e:
        log.error("  Failed to navigate to group: %s", e)
        # Try waiting anyway -- page may partially load
        await asyncio.sleep(3)
        if "/groups/" not in page.url:
            return "error"

    # Check page validity
    try:
        body_text = await page.text_content("body", timeout=5000) or ""
    except Exception:
        body_text = ""

    if "This content isn't available" in body_text or "Page Not Found" in body_text:
        log.warning("  Group page not accessible")
        return "not_found"

    # Check if already a member
    membership = await page.evaluate("""
        () => {
            const btns = document.querySelectorAll('div[role="button"], button');
            for (const btn of btns) {
                const t = btn.textContent.trim().toLowerCase();
                if (t === 'joined' || t === 'miembro' || t === 'leave group' || t === 'salir del grupo') return 'member';
                if (t.includes('pending') || t.includes('pendiente') || t.includes('cancel request')) return 'pending';
            }
            return null;
        }
    """)
    if membership == "member":
        log.info("  Already a member!")
        return "already_member"
    if membership == "pending":
        log.info("  Already have a pending request")
        return "pending"

    # Find and click Join button
    join_found = await page.evaluate("""
        () => {
            const btns = document.querySelectorAll('div[role="button"], button');
            for (const btn of btns) {
                const t = btn.textContent.trim().toLowerCase();
                if (t === 'join group' || t === 'join' || t === 'unirse al grupo' || t === 'unirse') {
                    return true;
                }
            }
            return false;
        }
    """)

    if not join_found:
        log.info("  No Join button found (invite-only or already member)")
        return "no_button"

    # Click the join button using locator
    join_btn = page.locator(
        'div[role="button"]:has-text("Join group"), '
        'div[role="button"]:has-text("Join Group"), '
        'div[role="button"]:has-text("Unirse al grupo"), '
        'div[role="button"]:has-text("Unirse"), '
        'button:has-text("Join group"), '
        'button:has-text("Join Group"), '
        'button:has-text("Join")'
    )
    try:
        if await join_btn.count() > 0:
            await join_btn.first.click()
            log.info("  Clicked JOIN button")
            await asyncio.sleep(random.uniform(3, 5))
        else:
            log.warning("  Join button located by JS but not by locator")
            return "no_button"
    except Exception as e:
        log.error("  Error clicking join: %s", e)
        return "error"

    # Handle membership questions dialog
    try:
        await asyncio.sleep(2)
        textareas = page.locator("textarea")
        ta_count = await textareas.count()
        if ta_count > 0:
            answer = random.choice(JOIN_GROUP_ANSWERS)
            log.info("  Answering %d membership question(s)", ta_count)
            for k in range(ta_count):
                try:
                    await textareas.nth(k).click()
                    await asyncio.sleep(0.3)
                    await textareas.nth(k).fill(answer)
                    await asyncio.sleep(random.uniform(0.5, 1.0))
                except Exception:
                    pass

            # Also check for radio buttons / checkboxes (agree to rules)
            checkboxes = page.locator('input[type="checkbox"]')
            cb_count = await checkboxes.count()
            for k in range(cb_count):
                try:
                    await checkboxes.nth(k).click()
                    await asyncio.sleep(0.3)
                except Exception:
                    pass

            # Submit answers
            submit = page.locator(
                'div[role="button"]:has-text("Submit"), '
                'button:has-text("Submit"), '
                'div[role="button"]:has-text("Enviar"), '
                'button:has-text("Enviar")'
            )
            if await submit.count() > 0:
                await submit.first.click()
                log.info("  Submitted answers")
            await asyncio.sleep(2)
    except Exception as e:
        log.info("  Questions handling note: %s", e)

    log.info("  JOIN request sent for: %s", group_name)
    return "joined"


async def process_group(page, group_name, already_joined_slugs, idx, total):
    """Search for group, pick best match, join it."""
    log.info("")
    log.info("[%d/%d] Processing: %s", idx, total, group_name)

    results = await search_for_group(page, group_name)

    if not results:
        log.warning("  No search results found")
        # Save debug screenshot
        debug_name = group_name.replace(" ", "_")[:30]
        debug_path = "/opt/data/debug_search_" + debug_name + ".png"
        try:
            await page.screenshot(path=debug_path)
            log.info("  Debug screenshot: %s", debug_path)
        except Exception:
            pass
        return "not_found", None

    # Log results
    for r in results[:5]:
        log.info("  Result: %s -> %s", r["name"][:60], r["url"])

    # Check if any result is already joined
    # Pick the best match by name similarity
    best = None
    best_score = -1
    for r in results:
        slug = r["gid"].lower()
        score = name_similarity(group_name, r["name"])
        if score > best_score:
            best_score = score
            best = r

    if not best:
        best = results[0]

    log.info("  Best match (%.0f%%): %s", best_score * 100, best["name"][:60])

    # Check if already joined via slug
    if best["gid"].lower() in already_joined_slugs:
        log.info("  Already joined (from /groups/joins/ list)")
        return "already_member", best["url"]

    # Navigate and join
    status = await join_group_page(page, best["url"], best["name"])

    if status == "joined" or status == "already_member":
        already_joined_slugs.add(best["gid"].lower())

    return status, best["url"]


async def main():
    config = load_config()
    account = config.accounts[0]
    proxy = account.proxy

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Load previous results
    joined_list = load_existing_json(JOINED_PATH)
    failed_list = load_existing_json(FAILED_PATH)

    proxy_opts = {}
    if proxy:
        proxy_opts = {"server": proxy.server}
        if proxy.username:
            proxy_opts["username"] = proxy.username
        if proxy.password:
            proxy_opts["password"] = proxy.password

    async with async_playwright() as p:
        launch_args = {"headless": True}
        if proxy_opts:
            launch_args["proxy"] = proxy_opts

        browser = await p.chromium.launch(**launch_args)
        ctx = await browser.new_context(
            storage_state=str(account.get_session_path()),
            viewport={"width": 1366, "height": 768},
            locale="en-US",
        )
        page = await ctx.new_page()

        # Verify session (with retry)
        log.info("Verifying Facebook session...")
        for attempt in range(3):
            try:
                await page.goto("https://www.facebook.com/", wait_until="commit", timeout=45000)
                await asyncio.sleep(4)
                break
            except Exception as e:
                log.warning("Session verify attempt %d failed: %s", attempt + 1, e)
                if attempt == 2:
                    log.error("Could not load Facebook after 3 attempts")
                    await browser.close()
                    return
                await asyncio.sleep(5)
        if "/login" in page.url:
            log.error("Session expired! Cannot proceed.")
            await browser.close()
            return

        log.info("Session OK. Starting group join process...")

        # Dismiss any notification popover/overlay
        try:
            await page.evaluate("""
                () => {
                    // Click away from any popover
                    const close = document.querySelector('div[aria-label="Close"], div[aria-label="Cerrar"]');
                    if (close) close.click();
                }
            """)
        except Exception:
            pass

        # Step 1: Get already-joined groups
        already_joined_slugs = await get_already_joined(page)

        # Step 2: Process each group
        stats = {}
        for i, name in enumerate(GROUPS_TO_JOIN):
            if i > 0:
                delay = random.uniform(30, 55)
                log.info("--- Waiting %.0fs before next group ---", delay)
                await asyncio.sleep(delay)

            try:
                status, url = await process_group(page, name, already_joined_slugs, i + 1, len(GROUPS_TO_JOIN))
            except Exception as e:
                log.error("  Unexpected error: %s", e)
                status = "error"
                url = None

            stats[status] = stats.get(status, 0) + 1

            if status in ("joined", "already_member", "pending"):
                entry = {"name": name, "url": url, "status": status}
                if not any(j.get("name") == name for j in joined_list):
                    joined_list.append(entry)
            elif status in ("error", "not_found", "no_button"):
                entry = {"name": name, "reason": status, "url": url}
                if not any(f.get("name") == name for f in failed_list):
                    failed_list.append(entry)

            # Save incrementally after each group
            save_json(JOINED_PATH, joined_list)
            save_json(FAILED_PATH, failed_list)
            sys.stdout.flush()

        # Save session
        try:
            await ctx.storage_state(path=str(account.get_session_path()))
            log.info("Session saved.")
        except Exception as e:
            log.warning("Could not save session: %s", e)

        await browser.close()

    # Save results
    save_json(JOINED_PATH, joined_list)
    save_json(FAILED_PATH, failed_list)

    log.info("")
    log.info("=" * 50)
    log.info("RESULTS:")
    for k, v in sorted(stats.items()):
        log.info("  %s: %d", k, v)
    log.info("Joined list: %s (%d entries)", JOINED_PATH, len(joined_list))
    log.info("Failed list: %s (%d entries)", FAILED_PATH, len(failed_list))
    log.info("=" * 50)


asyncio.run(main())
