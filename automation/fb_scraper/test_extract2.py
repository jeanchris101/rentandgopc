"""Debug extraction — log why each feed child is accepted or rejected."""
import asyncio
import logging
from pathlib import Path
from patchright.async_api import async_playwright
from config import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()


async def test():
    config = load_config()
    account = config.accounts[0]
    proxy = account.proxy

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": proxy.server, "username": proxy.username, "password": proxy.password},
        )
        ctx = await browser.new_context(
            storage_state=str(Path("/opt/fb_scraper/sessions/burner1.json")),
            viewport={"width": 1366, "height": 768},
            locale="en-US",
        )
        page = await ctx.new_page()

        url = "https://www.facebook.com/groups/realestatepuntacana/"
        log.info(f"Going to {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(6)

        # Scroll to load more
        for i in range(5):
            await page.evaluate("window.scrollBy(0, 700)")
            await asyncio.sleep(2)

        # Debug extraction for each feed child
        debug = await page.evaluate("""
            () => {
                const feed = document.querySelector('[role="feed"]');
                if (!feed) return [{error: 'no feed'}];

                const results = [];
                let idx = 0;
                for (const child of feed.children) {
                    idx++;
                    const text = child.textContent || '';
                    if (text.length < 30) {
                        results.push({idx, skip: 'text<30', textLen: text.length});
                        continue;
                    }

                    const articles = child.querySelectorAll('[role="article"]');
                    const hasOnlyComments = articles.length > 0 && !child.querySelector('div[dir="auto"]');
                    if (hasOnlyComments) {
                        results.push({idx, skip: 'only_comments', articles: articles.length});
                        continue;
                    }

                    // Try dir="auto"
                    const dirAutoDivs = child.querySelectorAll('div[dir="auto"]');
                    const parts = [];
                    for (const d of dirAutoDivs) {
                        if (d.closest('[role="article"]')) continue;
                        const t = d.textContent.trim();
                        if (t.length > 15) parts.push(t);
                    }
                    const unique = [...new Set(parts)];
                    let rawText = unique.join('\\n').trim();

                    // Fallback
                    let usedFallback = false;
                    if (rawText.length < 30) {
                        const clone = child.cloneNode(true);
                        clone.querySelectorAll('[role="article"], form, [role="button"]').forEach(el => el.remove());
                        const fullText = clone.textContent.replace(/\\s+/g, ' ').trim();
                        const cleaned = fullText
                            .replace(/(Like|Comment|Share|Reply|\\d+ Comments?|\\d+ Likes?|Most relevant|See more|Write a comment|\\d+[hmdw])/gi, '')
                            .trim();
                        if (cleaned.length > 30) {
                            rawText = cleaned.substring(0, 500);
                            usedFallback = true;
                        }
                    }

                    if (!rawText || rawText.length < 30) {
                        results.push({idx, skip: 'no_text_extracted', dirAutoCount: dirAutoDivs.length, textLen: text.length, partsFound: parts.length});
                        continue;
                    }

                    // Author
                    const headerLink = child.querySelector('h2 a, h3 a, h4 a, strong a');
                    const authorName = headerLink ? headerLink.textContent.trim() : null;

                    results.push({
                        idx,
                        ok: true,
                        fallback: usedFallback,
                        author: authorName ? authorName.substring(0, 40) : null,
                        text: rawText.substring(0, 120),
                        dirAutoCount: dirAutoDivs.length,
                        imgCount: child.querySelectorAll('img[src*="scontent"], img[src*="fbcdn"]').length,
                    });
                }
                return results;
            }
        """)

        for item in debug:
            if item.get("ok"):
                log.info(f"  OK #{item['idx']}: {item['author'][:30] if item.get('author') else '?':30s} | fallback={item['fallback']} dirAuto={item['dirAutoCount']} imgs={item['imgCount']}")
                log.info(f"    Text: {item['text']}")
            elif item.get("skip"):
                log.info(f"  SKIP #{item['idx']}: {item['skip']} {item}")
            elif item.get("error"):
                log.info(f"  ERROR: {item}")

        await browser.close()


asyncio.run(test())
