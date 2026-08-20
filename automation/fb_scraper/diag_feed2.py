"""Deep DOM diagnosis — what does FB group feed actually look like."""
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

        # Scroll down to load more posts
        for i in range(3):
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(2)

        # Get ALL links that look like post links
        all_post_links = await page.evaluate("""
            () => {
                const links = document.querySelectorAll('a');
                const results = [];
                for (const a of links) {
                    const href = a.href || '';
                    if (href.includes('/posts/') || href.includes('/permalink/') || href.includes('pfbid')) {
                        results.push({
                            href: href.substring(0, 150),
                            text: a.textContent.trim().substring(0, 60),
                            hasCommentId: href.includes('comment_id'),
                        });
                    }
                }
                return results;
            }
        """)
        print(f"\nAll post/permalink links ({len(all_post_links)}):")
        for link in all_post_links[:20]:
            marker = " [COMMENT]" if link['hasCommentId'] else ""
            print(f"  {link['text'][:40]:40s} {marker}")
            print(f"    {link['href']}")

        # Look at articles more carefully
        article_detail = await page.evaluate("""
            () => {
                const articles = document.querySelectorAll('[role="article"]');
                const info = [];
                for (let i = 0; i < Math.min(articles.length, 15); i++) {
                    const a = articles[i];
                    const parent = a.parentElement?.closest('[role="article"]');

                    // Get ALL links in this article
                    const links = Array.from(a.querySelectorAll('a'))
                        .filter(l => l.href && (l.href.includes('/posts/') || l.href.includes('/permalink/') || l.href.includes('pfbid')))
                        .map(l => ({
                            href: l.href.substring(0, 150),
                            hasCommentId: l.href.includes('comment_id'),
                            text: l.textContent.trim().substring(0, 40),
                        }));

                    // Get text content
                    const allText = a.textContent.substring(0, 200);

                    // Author
                    const h = a.querySelector('h2, h3, h4');
                    const hText = h ? h.textContent.trim() : null;
                    const strong = a.querySelector('strong');
                    const strongText = strong ? strong.textContent.trim() : null;

                    info.push({
                        i, nested: !!parent,
                        links: links.slice(0, 5),
                        heading: hText,
                        strong: strongText,
                        textSnippet: allText.replace(/\\s+/g, ' ').substring(0, 150),
                    });
                }
                return info;
            }
        """)

        print(f"\nArticle details ({len(article_detail)}):")
        for a in article_detail:
            print(f"\n  #{a['i']}: nested={a['nested']}, heading={a['heading']}, strong={a['strong']}")
            print(f"    Text: {a['textSnippet']}")
            for link in a['links']:
                cm = " [COMMENT]" if link['hasCommentId'] else " [POST]"
                print(f"    Link{cm}: {link['text'][:30]} -> {link['href']}")

        # Also check: does this page have a feed container?
        feed_info = await page.evaluate("""
            () => {
                const feed = document.querySelector('[role="feed"]');
                if (!feed) return {hasFeed: false};
                return {
                    hasFeed: true,
                    childCount: feed.children.length,
                    articleCount: feed.querySelectorAll('[role="article"]').length,
                };
            }
        """)
        print(f"\nFeed container: {feed_info}")

        await browser.close()


asyncio.run(diagnose())
