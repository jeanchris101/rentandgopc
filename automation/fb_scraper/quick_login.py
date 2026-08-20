"""Quick FB login — WITH proxy, diagnostic output."""
import asyncio
import json
from pathlib import Path
from patchright.async_api import async_playwright

EMAIL = "qchulomarketplace@gmail.com"
PASSWORD = "Wk2GgCxghFPEaNrNRiKz"
SESSION_PATH = "/opt/fb_scraper/sessions/burner1.json"


async def login():
    config = json.loads(Path("/opt/fb_scraper/config.json").read_text())
    proxy_cfg = config["accounts"][0].get("proxy", {})

    async with async_playwright() as p:
        launch_args = {"headless": True}
        if proxy_cfg:
            launch_args["proxy"] = {
                "server": proxy_cfg["server"],
                "username": proxy_cfg["username"],
                "password": proxy_cfg["password"],
            }
            print(f"Using proxy: {proxy_cfg['server']}")

        browser = await p.chromium.launch(**launch_args)
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        print("1. Going to facebook.com (with proxy)...")
        try:
            await page.goto("https://www.facebook.com/", timeout=30000)
        except Exception as e:
            print(f"   goto timeout (may be ok): {str(e)[:100]}")
        await asyncio.sleep(4)

        url = page.url
        print(f"2. Current URL: {url}")
        title = await page.title()
        print(f"   Title: {title}")

        # Screenshot
        await page.screenshot(path="/opt/fb_scraper/proxy_before_login.png")
        print("   Screenshot: proxy_before_login.png")

        # Check if already logged in
        nav = await page.locator('[role="navigation"]').count()
        if nav > 0 and "/login" not in url:
            print("3. Already logged in! Saving session.")
            await context.storage_state(path=SESSION_PATH)
            await browser.close()
            return

        # Dismiss cookie dialog — MUST happen before we can click login form
        try:
            # Try multiple approaches to find the cookie accept button
            cookie_selectors = [
                'button[data-cookiebanner="accept_button"]',
                'button[data-cookiebanner="accept_only_essential"]',
                'div[role="dialog"] button:nth-child(2)',  # "Allow all cookies" is usually 2nd
            ]
            dismissed = False
            for sel in cookie_selectors:
                c = await page.locator(sel).count()
                if c > 0:
                    await page.locator(sel).first.click()
                    print(f"   Dismissed cookies via: {sel}")
                    dismissed = True
                    break

            if not dismissed:
                # Try by text
                allow_btn = page.get_by_role("button", name="Allow all cookies")
                if await allow_btn.count() > 0:
                    await allow_btn.click()
                    print("   Dismissed cookies via text match")
                    dismissed = True

            if not dismissed:
                # Last resort: click "Decline optional cookies"
                decline_btn = page.get_by_role("button", name="Decline optional cookies")
                if await decline_btn.count() > 0:
                    await decline_btn.click()
                    print("   Declined optional cookies")
                    dismissed = True

            if dismissed:
                await asyncio.sleep(2)
            else:
                print("   No cookie dialog found or couldn't dismiss")
        except Exception as e:
            print(f"   Cookie dismiss error: {e}")

        # Fill email
        email_el = page.locator('input#email, input[name="email"]')
        count = await email_el.count()
        print(f"3. Email inputs found: {count}")
        if count > 0:
            await email_el.first.click()
            await asyncio.sleep(0.3)
            # Type character by character for more human-like behavior
            for char in EMAIL:
                await email_el.first.press(char)
                await asyncio.sleep(0.05)
            print(f"   Typed email")
            await asyncio.sleep(0.5)

        # Fill password
        pass_el = page.locator('input#pass, input[name="pass"]')
        count = await pass_el.count()
        print(f"4. Password inputs found: {count}")
        if count > 0:
            await pass_el.first.click()
            await asyncio.sleep(0.3)
            for char in PASSWORD:
                await pass_el.first.press(char)
                await asyncio.sleep(0.04)
            print("   Typed password")
            await asyncio.sleep(0.5)

        # Click login button
        btn_selectors = [
            'button[name="login"]',
            'button[data-loginbutton="true"]',
            '#loginbutton',
            'input[value="Log In"]',
            'button[type="submit"]',
        ]
        clicked = False
        for sel in btn_selectors:
            c = await page.locator(sel).count()
            if c > 0:
                print(f"5. Clicking: {sel}")
                await page.locator(sel).first.click()
                clicked = True
                break

        if not clicked:
            print("5. No button, pressing Enter...")
            await pass_el.first.press("Enter")

        print("6. Waiting for navigation...")
        await asyncio.sleep(10)

        url = page.url
        print(f"7. Post-login URL: {url}")
        title = await page.title()
        print(f"   Title: {title}")

        await page.screenshot(path="/opt/fb_scraper/proxy_after_login.png")
        print("   Screenshot: proxy_after_login.png")

        page_text = await page.text_content("body") or ""
        if "complete a challenge" in page_text.lower() or "arkose" in page_text.lower():
            print("   CAPTCHA challenge detected after login!")
        elif "/checkpoint" in url:
            print("   CHECKPOINT detected!")
        elif "/login" in url:
            print("   Still on login page.")
        else:
            print("   Login appears successful!")
            await context.storage_state(path=SESSION_PATH)
            print(f"   Session saved to {SESSION_PATH}")

        await browser.close()
        print("Done.")


asyncio.run(login())
