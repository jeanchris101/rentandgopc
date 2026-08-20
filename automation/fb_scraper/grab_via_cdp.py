"""Grab FB cookies by launching a new Chrome instance with a COPY of the user profile.
Chrome locks the cookie DB, so we copy the entire profile dir first."""
import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path


async def main():
    from playwright.async_api import async_playwright

    chrome_profile = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"

    # We can't copy the whole profile (too big + locked files).
    # Instead, launch a NEW browser, go to Facebook, and use JS to check login state.
    # If not logged in, we'll use a different approach.

    # Alternative: Launch Chrome with CDP and use Network.getAllCookies
    print("Launching new Chrome with remote debugging...")

    async with async_playwright() as p:
        # Launch a fresh browser, navigate to FB
        # The user is logged in on their regular Chrome - we need those cookies
        # Let's try connecting to an existing Chrome via CDP

        # First, let's try launching Chrome with the user's profile using a channel
        # that copies session storage
        browser = await p.chromium.launch(
            headless=False,
            channel="chrome",
            args=[
                f"--user-data-dir={chrome_profile}",
                "--profile-directory=Default",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )

        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(3)

        state = await context.storage_state()
        fb_cookies = [c for c in state.get("cookies", []) if "facebook.com" in c.get("domain", "")]

        print(f"Got {len(fb_cookies)} FB cookies")

        out = Path(__file__).parent / "sessions" / "burner1.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"cookies": fb_cookies, "origins": []}, indent=2))
        print(f"Saved to {out}")

        await browser.close()


asyncio.run(main())
