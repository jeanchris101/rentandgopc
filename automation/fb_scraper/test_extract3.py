"""Call the ACTUAL extract_posts_from_page function and log results."""
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

        # Scroll to load content
        for i in range(5):
            await page.evaluate("window.scrollBy(0, 700)")
            await asyncio.sleep(2)

        # Call ACTUAL extraction function
        posts = await extract_posts_from_page(page, set())
        log.info(f"extract_posts_from_page returned {len(posts)} posts:")
        for p2 in posts:
            author = p2.get("authorName") or "?"
            text = p2["rawText"][:100].replace("\n", " ")
            log.info(f"  {p2['postId'][:15]:15s} | {author[:30]:30s} | {text}")

        await browser.close()


asyncio.run(test())
