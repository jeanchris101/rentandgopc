"""Test post extraction — scroll and log what we find."""
import asyncio
import logging
from pathlib import Path
from patchright.async_api import async_playwright
from config import load_config
from scraper import extract_posts_from_page

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()


async def test():
    config = load_config()
    account = config.accounts[0]
    proxy = account.proxy

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": proxy.server, "username": proxy.username, "password": proxy.password},
        )
        ctx = await browser.new_context(
            storage_state=str(Path("/opt/fb_scraper/sessions/burner1.json")),
            viewport={"width": 1366, "height": 768},
            locale="en-US",
        )
        page = await ctx.new_page()

        url = "https://www.facebook.com/groups/realestatepuntacana/"
        log.info(f"Going to {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(6)

        seen_ids = set()
        for i in range(10):
            posts = await extract_posts_from_page(page, set())  # pass empty set to get ALL
            new_posts = [p for p in posts if p["postId"] not in seen_ids]

            log.info(f"Scroll {i}: {len(posts)} total, {len(new_posts)} new")
            for p in new_posts:
                author = p.get("authorName") or "?"
                text = p["rawText"][:80].replace("\n", " ")
                log.info(f"  NEW: {p['postId'][:15]:15s} | {author[:25]:25s} | {text}")
                seen_ids.add(p["postId"])

            # Scroll
            await page.evaluate("window.scrollBy(0, 700)")
            await asyncio.sleep(3)

        log.info(f"\nTotal unique posts found: {len(seen_ids)}")
        await browser.close()


asyncio.run(test())
