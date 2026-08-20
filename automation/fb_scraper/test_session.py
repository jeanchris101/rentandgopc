"""Test FB session on VPS — verify cookies work."""
import asyncio
import json
from pathlib import Path
from patchright.async_api import async_playwright


async def test():
    config = json.loads(Path("/opt/fb_scraper/config.json").read_text())
    proxy_cfg = config["accounts"][0].get("proxy", {})
    session = json.loads(Path("/opt/fb_scraper/sessions/burner1.json").read_text())
    print(f"Loaded {len(session['cookies'])} cookies")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy={
                "server": proxy_cfg["server"],
                "username": proxy_cfg["username"],
                "password": proxy_cfg["password"],
            },
        )
        context = await browser.new_context(
            storage_state="/opt/fb_scraper/sessions/burner1.json",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = await context.new_page()
        print("Navigating to Facebook...")
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        url = page.url
        print(f"URL: {url}")
        nav = await page.locator("[role=navigation]").count()
        print(f"Navigation elements: {nav}")
        if nav > 0 and "/login" not in url:
            print("SESSION WORKS! Logged in on VPS!")
            await context.storage_state(path="/opt/fb_scraper/sessions/burner1.json")
            print("Session re-saved with updated cookies")
        else:
            await page.screenshot(path="/opt/fb_scraper/session_test.png")
            title = await page.title()
            print(f"Title: {title}")
            print("NOT logged in. Screenshot saved.")
        await browser.close()


asyncio.run(test())
