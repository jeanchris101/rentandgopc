"""Use Playwright to connect to Chrome user data dir and export FB session cookies."""
import asyncio
import json
from pathlib import Path

OUTPUT = Path(__file__).parent / "sessions" / "burner1.json"

async def main():
    # Use patchright if available, else playwright
    try:
        from patchright.async_api import async_playwright
    except ImportError:
        from playwright.async_api import async_playwright

    # Chrome user data directory
    import os
    chrome_user_data = str(Path(os.environ["LOCALAPPDATA"]) / "Google/Chrome/User Data")

    print("Launching Chrome with your existing profile...")
    print("(This will use your logged-in session — browser may flash briefly)")

    async with async_playwright() as p:
        # Launch with existing user data to get logged-in cookies
        # Use a temporary context that reads the Chrome profile
        context = await p.chromium.launch_persistent_context(
            chrome_user_data,
            headless=True,
            channel="chrome",
            viewport={"width": 1366, "height": 768},
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = context.pages[0] if context.pages else await context.new_page()

        print("Navigating to Facebook...")
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(3)

        url = page.url
        print(f"URL: {url}")

        # Check if logged in
        nav = await page.locator('[role="navigation"]').count()
        if nav > 0:
            print("Logged in! Exporting session...")
        else:
            print(f"May not be logged in (nav elements: {nav}). Exporting anyway...")

        # Export storage state (cookies + localStorage)
        state = await context.storage_state()

        # Filter to only facebook.com cookies
        fb_cookies = [c for c in state.get("cookies", []) if "facebook.com" in c.get("domain", "")]
        state["cookies"] = fb_cookies

        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(state, indent=2))

        key_names = {"c_user", "xs", "fr", "datr", "sb"}
        found = {c["name"] for c in fb_cookies} & key_names
        print(f"Exported {len(fb_cookies)} Facebook cookies")
        print(f"Key auth cookies: {found}")
        missing = key_names - found
        if missing:
            print(f"Missing (may be ok): {missing}")
        else:
            print("All key auth cookies present!")

        print(f"Saved to: {OUTPUT}")
        await context.close()


asyncio.run(main())
