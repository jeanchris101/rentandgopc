"""Debug: screenshot Facebook group search results to see DOM."""
import asyncio
import json
from patchright.async_api import async_playwright

# We'll run this on VPS, save screenshot + page HTML

async def main():
    import sys
    sys.path.insert(0, '/opt/fb_scraper')
    from config import load_config

    config = load_config()
    account = config.accounts[0]
    proxy = account.proxy

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

        # Verify session
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)
        if "/login" in page.url:
            print("SESSION EXPIRED")
            await browser.close()
            return

        print("Session OK, URL:", page.url)

        # Try search
        url = "https://www.facebook.com/search/groups/?q=Punta%20Cana%20real%20estate"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(8)

        # Scroll
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(1.5)

        await page.screenshot(path="/opt/data/debug_search.png", full_page=True)
        print("Screenshot saved")

        # Dump all links with /groups/
        links = await page.evaluate("""
            () => {
                const results = [];
                const all = document.querySelectorAll('a[href*="/groups/"]');
                for (const a of all) {
                    results.push({
                        href: a.href,
                        text: a.textContent.trim().substring(0, 100),
                        parent_role: a.closest('[role]') ? a.closest('[role]').getAttribute('role') : null,
                    });
                }
                return results;
            }
        """)
        print(f"Found {len(links)} group links:")
        for l in links[:20]:
            print(f"  {l['href'][:80]} | {l['text'][:50]} | role={l['parent_role']}")

        # Also dump all role=main content
        main_html = await page.evaluate("""
            () => {
                const m = document.querySelector('div[role="main"]');
                if (m) return m.innerHTML.substring(0, 5000);
                return 'NO role=main FOUND';
            }
        """)
        with open('/opt/data/debug_main_html.txt', 'w') as f:
            f.write(main_html)
        print("Main HTML saved")

        # Check all hrefs on page
        all_hrefs = await page.evaluate("""
            () => {
                const hrefs = [];
                for (const a of document.querySelectorAll('a')) {
                    if (a.href && a.href.includes('group')) {
                        hrefs.push(a.href.substring(0, 100));
                    }
                }
                return [...new Set(hrefs)];
            }
        """)
        print(f"All group-related hrefs ({len(all_hrefs)}):")
        for h in all_hrefs[:30]:
            print(f"  {h}")

        await ctx.storage_state(path=str(account.get_session_path()))
        await browser.close()
        print("Done")


asyncio.run(main())
