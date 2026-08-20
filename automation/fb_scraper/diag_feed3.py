"""Deep feed child analysis — understand the actual post DOM structure."""
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
        await asyncio.sleep(6)

        # Scroll to load posts
        for i in range(5):
            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(2)

        # Analyze the feed container children
        feed_analysis = await page.evaluate("""
            () => {
                const feed = document.querySelector('[role="feed"]');
                if (!feed) return {error: 'no feed'};

                const children = [];
                for (let i = 0; i < Math.min(feed.children.length, 15); i++) {
                    const child = feed.children[i];
                    const text = child.textContent || '';
                    const hasPostLink = !!child.querySelector('a[href*="/posts/"], a[href*="/permalink/"], a[href*="pfbid"]');
                    const hasAuthor = !!child.querySelector('h2 a, h3 a, strong a, a[role="link"][tabindex="0"]');
                    const hasSeeMore = text.includes('See more') || text.includes('Ver más');
                    const hasPrice = /\\$[\\d,]+|USD|\\d+K/.test(text);
                    const hasImages = child.querySelectorAll('img[src*="scontent"], img[src*="fbcdn"]').length;
                    const articles = child.querySelectorAll('[role="article"]').length;
                    const dirAuto = child.querySelectorAll('div[dir="auto"]').length;

                    // Get all links
                    const links = Array.from(child.querySelectorAll('a'))
                        .filter(a => a.href)
                        .map(a => ({href: a.href.substring(0, 120), text: a.textContent.trim().substring(0, 40)}))
                        .filter(a => a.href.includes('/posts/') || a.href.includes('/permalink/') || a.href.includes('pfbid') || a.href.includes('/user/') || a.href.includes('/profile'));

                    // Author candidates
                    const authorCandidates = Array.from(child.querySelectorAll('h2 a, h3 a, h4 a, strong a'))
                        .map(a => a.textContent.trim())
                        .filter(t => t.length > 1 && t.length < 60);

                    // Get readable text
                    const autoTexts = Array.from(child.querySelectorAll('div[dir="auto"]'))
                        .map(d => d.textContent.trim())
                        .filter(t => t.length > 15)
                        .slice(0, 5)
                        .map(t => t.substring(0, 100));

                    children.push({
                        i, tag: child.tagName,
                        textLen: text.length,
                        hasPostLink, hasAuthor, hasSeeMore, hasPrice, hasImages,
                        articles, dirAuto,
                        links: links.slice(0, 5),
                        authors: authorCandidates,
                        texts: autoTexts,
                    });
                }
                return {feedChildren: feed.children.length, analyzed: children};
            }
        """)

        print(f"\nFeed has {feed_analysis.get('feedChildren', 0)} children:")
        for child in feed_analysis.get('analyzed', []):
            is_post = child['hasPostLink'] or child['hasPrice'] or child['hasSeeMore']
            marker = " ** LIKELY POST **" if is_post else ""
            print(f"\n  Child #{child['i']} ({child['tag']}): textLen={child['textLen']}, imgs={child['hasImages']}, articles={child['articles']}, dirAuto={child['dirAuto']}{marker}")
            if child['authors']:
                print(f"    Authors: {child['authors']}")
            if child['links']:
                for l in child['links']:
                    print(f"    Link: {l['text'][:30]} -> {l['href']}")
            for t in child['texts'][:3]:
                print(f"    Text: {t}")

        await browser.close()


asyncio.run(diagnose())
