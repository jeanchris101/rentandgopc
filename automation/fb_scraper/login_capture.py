"""Open a visible browser window for FB login, capture session cookies."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

EMAIL = "qchulomarketplace@gmail.com"
PASSWORD = "Wk2GgCxghFPEaNrNRiKz"
OUTPUT = Path(__file__).parent / "sessions" / "burner1.json"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            channel="chrome",
        )
        context = await browser.new_context(
            viewport={"width": 1100, "height": 700},
            locale="en-US",
        )
        page = await context.new_page()

        print("Opening Facebook login page...")
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

        # Dismiss cookie dialog if present
        try:
            allow_btn = page.get_by_role("button", name="Allow all cookies")
            if await allow_btn.count() > 0:
                await allow_btn.click()
                print("Dismissed cookie dialog")
                await asyncio.sleep(1)
        except Exception:
            pass
        try:
            decline_btn = page.get_by_role("button", name="Decline optional cookies")
            if await decline_btn.count() > 0:
                await decline_btn.click()
                print("Declined optional cookies")
                await asyncio.sleep(1)
        except Exception:
            pass

        # Pre-fill email and password
        try:
            email_el = page.locator('input#email, input[name="email"]')
            if await email_el.count() > 0:
                await email_el.first.fill(EMAIL)
                print("Pre-filled email")

            pass_el = page.locator('input#pass, input[name="pass"]')
            if await pass_el.count() > 0:
                await pass_el.first.fill(PASSWORD)
                print("Pre-filled password")
        except Exception as e:
            print(f"Pre-fill note: {e}")

        print()
        print("=" * 50)
        print("BROWSER IS OPEN — complete the login if needed.")
        print("If there's a CAPTCHA, solve it manually.")
        print("Once you see the News Feed, I'll capture the session.")
        print("=" * 50)
        print()

        # Wait for the user to complete login — poll for News Feed
        for i in range(120):  # Up to 2 minutes
            await asyncio.sleep(2)
            url = page.url

            # Check if on News Feed (logged in)
            if "facebook.com" in url and "/login" not in url and "checkpoint" not in url and "two_step" not in url:
                nav = await page.locator('[role="navigation"]').count()
                if nav > 0:
                    print("Login detected! Capturing session...")
                    await asyncio.sleep(2)  # Let cookies settle

                    state = await context.storage_state()
                    fb_cookies = [c for c in state.get("cookies", []) if "facebook.com" in c.get("domain", "")]

                    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
                    OUTPUT.write_text(json.dumps({"cookies": fb_cookies, "origins": []}, indent=2))

                    key_names = {"c_user", "xs", "fr", "datr", "sb"}
                    found = {c["name"] for c in fb_cookies} & key_names
                    print(f"Captured {len(fb_cookies)} cookies")
                    print(f"Key auth cookies: {found}")
                    print(f"Saved to: {OUTPUT}")

                    await browser.close()
                    return

            if i % 10 == 0 and i > 0:
                print(f"  Still waiting... ({i*2}s)")

        print("Timed out after 4 minutes. Saving whatever we have...")
        state = await context.storage_state()
        fb_cookies = [c for c in state.get("cookies", []) if "facebook.com" in c.get("domain", "")]
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps({"cookies": fb_cookies, "origins": []}, indent=2))
        print(f"Saved {len(fb_cookies)} cookies to {OUTPUT}")
        await browser.close()


asyncio.run(main())
