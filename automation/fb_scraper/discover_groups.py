"""
discover_groups.py — Navigate to FB groups page and extract all joined group URLs.
Outputs a JSON file with group names and URLs for config.
"""

import asyncio
import json
import logging
import random
from pathlib import Path

from patchright.async_api import async_playwright

from config import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("discover_groups")

SESSIONS_DIR = Path(__file__).parent / "sessions"
OUTPUT_FILE = Path(__file__).parent / "discovered_groups.json"


async def discover_groups():
    config = load_config()
    accounts = [a for a in config.accounts if not a.disabled and a.has_session()]
    if not accounts:
        log.error("No accounts with sessions")
        return

    account = accounts[0]
    log.info(f"Using account: {account.label}")

    async with async_playwright() as p:
        launch_args = {
            "headless": True,
            "args": ["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu",
                     "--js-flags=--max-old-space-size=256"],
        }
        if account.proxy:
            launch_args["proxy"] = {"server": account.proxy.server}
            if account.proxy.username:
                launch_args["proxy"]["username"] = account.proxy.username
            if account.proxy.password:
                launch_args["proxy"]["password"] = account.proxy.password

        browser = await p.chromium.launch(**launch_args)

        session_path = account.get_session_path()
        context_args = {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "locale": "en-US",
            "timezone_id": "America/Santo_Domingo",
        }
        if session_path.exists():
            context_args["storage_state"] = str(session_path)

        context = await browser.new_context(**context_args)
        page = await context.new_page()

        # Verify login
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # Navigate to groups page
        log.info("Navigating to groups page...")
        await page.goto("https://www.facebook.com/groups/joins/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # Scroll down to load all groups
        for i in range(10):
            await page.evaluate("window.scrollBy(0, 1500)")
            await asyncio.sleep(random.uniform(1.5, 3.0))
            log.info(f"  Scroll {i+1}/10")

        # Extract all group links
        groups = await page.evaluate("""
            () => {
                const results = [];
                const seen = new Set();
                // Find all links that point to group pages
                const links = document.querySelectorAll('a[href*="/groups/"]');
                for (const link of links) {
                    const href = link.href || '';
                    // Extract group URL (clean it)
                    const match = href.match(/facebook\\.com\\/groups\\/([^/?]+)/);
                    if (!match) continue;
                    const groupSlug = match[1];
                    // Skip non-group pages
                    if (['joins', 'discover', 'feed', 'create', 'settings'].includes(groupSlug)) continue;
                    if (seen.has(groupSlug)) continue;
                    seen.add(groupSlug);

                    // Try to get the group name from nearby text
                    let name = '';
                    const parent = link.closest('[role="listitem"]') || link.closest('[class]') || link;
                    const spans = parent.querySelectorAll('span');
                    for (const span of spans) {
                        const t = span.textContent.trim();
                        if (t.length > 3 && t.length < 100 && !t.includes('visited') && !t.includes('ago')) {
                            name = t;
                            break;
                        }
                    }
                    if (!name) name = link.textContent.trim().split('\\n')[0];

                    results.push({
                        name: name || groupSlug,
                        url: `https://www.facebook.com/groups/${groupSlug}/`,
                        slug: groupSlug,
                    });
                }
                return results;
            }
        """)

        log.info(f"Found {len(groups)} groups")
        for g in groups:
            log.info(f"  {g['name']} -> {g['url']}")

        # Save to file
        OUTPUT_FILE.write_text(json.dumps(groups, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info(f"Saved to {OUTPUT_FILE}")

        # Save session
        try:
            await context.storage_state(path=str(session_path))
        except Exception:
            pass

        await browser.close()


if __name__ == "__main__":
    asyncio.run(discover_groups())
