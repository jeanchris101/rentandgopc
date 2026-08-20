"""Diagnose FB login page — what elements are visible."""
import asyncio
import json
from pathlib import Path
from patchright.async_api import async_playwright


async def diagnose():
    config = json.loads(Path("/opt/fb_scraper/config.json").read_text())
    account = config["accounts"][0]
    proxy = account.get("proxy")

    async with async_playwright() as p:
        launch_args = {"headless": True}
        if proxy:
            launch_args["proxy"] = {
                "server": proxy["server"],
                "username": proxy["username"],
                "password": proxy["password"],
            }
        browser = await p.chromium.launch(**launch_args)
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="en-US",
        )
        page = await context.new_page()

        print("Navigating to facebook.com...")
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)

        # Screenshot
        await page.screenshot(path="/opt/fb_scraper/diag_login.png")
        print("Screenshot saved to /opt/fb_scraper/diag_login.png")

        url = page.url
        print(f"URL: {url}")

        # Check for key selectors
        selectors = [
            'input#email', 'input[name="email"]',
            'input#pass', 'input[name="pass"]',
            'button[name="login"]', 'button[type="submit"]',
            'button[data-loginbutton="true"]', '#loginbutton',
            'input[value="Log In"]', 'input[type="submit"]',
        ]
        for sel in selectors:
            count = await page.locator(sel).count()
            if count > 0:
                print(f"  FOUND: {sel} (count={count})")

        # Get all buttons
        buttons = await page.evaluate("""
            () => Array.from(document.querySelectorAll('button, input[type=submit], [role=button]'))
                .slice(0, 15)
                .map(b => ({
                    tag: b.tagName,
                    type: b.type || '',
                    name: b.name || '',
                    text: (b.textContent || b.value || '').trim().substring(0, 60),
                    id: b.id || '',
                    'data-loginbutton': b.getAttribute('data-loginbutton') || ''
                }))
        """)
        print(f"\nAll buttons/inputs ({len(buttons)}):")
        for b in buttons:
            print(f"  {b}")

        # Page title
        title = await page.title()
        print(f"\nPage title: {title}")

        # Check for cookie consent
        cookie_elements = await page.locator('[data-cookiebanner], [data-testid*="cookie"]').count()
        print(f"Cookie banner elements: {cookie_elements}")

        await browser.close()


asyncio.run(diagnose())
