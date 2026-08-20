"""Diagnose what the FB group feed looks like after navigation."""
import asyncio
import json
from pathlib import Path
from patchright.async_api import async_playwright


async def diagnose():
    config = json.loads(Path("/opt/fb_scraper/config.json").read_text())
    proxy_cfg = config["accounts"][0].get("proxy", {})

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

        url = "https://www.facebook.com/groups/realestatepuntacana/"
        print(f"Going to: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # Screenshot before clicking Discussion
        await page.screenshot(path="/opt/fb_scraper/diag_feed_1.png")
        print("Screenshot 1: initial page")
        print(f"URL: {page.url}")

        # Check for tabs
        tabs = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a'))
                .filter(a => /discussion|recent|new|post/i.test(a.textContent))
                .slice(0, 10)
                .map(a => ({text: a.textContent.trim().substring(0, 50), href: a.href?.substring(0, 100) || ''}))
        """)
        print(f"Tab-like links: {tabs}")

        # Scroll down a bit
        await page.evaluate("window.scrollBy(0, 500)")
        await asyncio.sleep(3)

        # Count articles
        article_count = await page.locator('[role="article"]').count()
        print(f"Articles found: {article_count}")

        # Get article details
        article_info = await page.evaluate("""
            () => {
                const articles = document.querySelectorAll('[role="article"]');
                const info = [];
                for (let i = 0; i < Math.min(articles.length, 10); i++) {
                    const a = articles[i];
                    const parentArticle = a.parentElement?.closest('[role="article"]');
                    const isNested = !!parentArticle;

                    // Get all links with /posts/ or /permalink/
                    const postLinks = Array.from(a.querySelectorAll('a'))
                        .filter(l => l.href && (l.href.includes('/posts/') || l.href.includes('/permalink/') || l.href.includes('pfbid')))
                        .map(l => l.href.substring(0, 120));

                    // Get text snippets
                    const divs = Array.from(a.querySelectorAll('div[dir="auto"]')).slice(0, 5);
                    const texts = divs.map(d => d.textContent.trim().substring(0, 80));

                    // Author
                    const headerLink = a.querySelector('h2 a, h3 a, strong a');
                    const author = headerLink ? headerLink.textContent.trim() : null;

                    info.push({
                        index: i,
                        nested: isNested,
                        postLinks: postLinks.slice(0, 3),
                        texts: texts,
                        author: author,
                        hasImages: a.querySelectorAll('img[src*="scontent"], img[src*="fbcdn"]').length,
                    });
                }
                return info;
            }
        """)

        for a in article_info:
            print(f"\n  Article #{a['index']}: nested={a['nested']}, author={a['author']}, imgs={a['hasImages']}")
            for link in a['postLinks']:
                print(f"    Link: {link}")
            for text in a['texts'][:3]:
                print(f"    Text: {text}")

        # Scroll more and screenshot
        await page.evaluate("window.scrollBy(0, 1000)")
        await asyncio.sleep(3)
        await page.screenshot(path="/opt/fb_scraper/diag_feed_2.png")
        print("\nScreenshot 2: after scroll")

        await browser.close()


asyncio.run(diagnose())
