"""
scrape_agent_pics.py — Visit agent FB profiles and grab their profile picture URL.
Lightweight script that runs after the main scraper cycle.
Uses the same Patchright session.
"""

import asyncio
import json
import logging
import random
import sqlite3
from pathlib import Path

from patchright.async_api import async_playwright

from config import load_config
from database import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("agent_pics")

SESSIONS_DIR = Path(__file__).parent / "sessions"


async def scrape_profile_pics():
    config = load_config()
    accounts = [a for a in config.accounts if not a.disabled and a.has_session()]
    if not accounts:
        log.error("No accounts with sessions")
        return

    account = accounts[0]
    conn = get_connection()

    # Get agents with 3+ posts that have FB profile URLs but no profile pic
    # Skip low-activity agents (1-2 posts), ordered by most active first
    rows = conn.execute(
        """SELECT id, name, fb_profile_url, total_listings FROM agents
           WHERE fb_profile_url IS NOT NULL AND fb_profile_url != ''
           AND (profile_pic_url IS NULL OR profile_pic_url = '')
           AND total_listings >= 3
           ORDER BY total_listings DESC"""
    ).fetchall()

    if not rows:
        log.info("All agents already have profile pics")
        conn.close()
        return

    log.info(f"Scraping profile pics for {len(rows)} agents")

    async with async_playwright() as p:
        launch_args = {
            "headless": True,
            "args": ["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu",
                     "--js-flags=--max-old-space-size=256"],
        }
        if account.proxy:
            launch_args["proxy"] = {"server": account.proxy.server}
            if account.proxy.username:
                launch_args["proxy"]["username"] = account.proxy.username
            if account.proxy.password:
                launch_args["proxy"]["password"] = account.proxy.password

        browser = await p.chromium.launch(**launch_args)

        session_path = account.get_session_path()
        context_args = {
            "viewport": {"width": 1024, "height": 600},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "locale": "en-US",
            "timezone_id": "America/Santo_Domingo",
        }
        if session_path.exists():
            context_args["storage_state"] = str(session_path)

        context = await browser.new_context(**context_args)
        page = await context.new_page()

        updated = 0
        for row in rows:
            agent_id = row["id"]
            name = row["name"] or "?"
            profile_url = row["fb_profile_url"]

            try:
                log.info(f"  Visiting: {name} ({profile_url})")
                await page.goto(profile_url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(random.uniform(3, 6))

                # Extract profile picture — FB puts it in a specific SVG/image container
                pic_url = await page.evaluate("""
                    () => {
                        // Method 1: Profile photo image (large circular avatar)
                        const profilePics = document.querySelectorAll('image[*|href], svg image');
                        for (const img of profilePics) {
                            const href = img.getAttribute('xlink:href') || img.getAttribute('href') || '';
                            if (href && (href.includes('scontent') || href.includes('fbcdn')) && !href.includes('emoji')) {
                                return href;
                            }
                        }

                        // Method 2: Regular img tags — look for the profile avatar
                        // Profile pics are usually in an <a> with aria-label containing the person's name
                        const avatarLink = document.querySelector('a[aria-label*="profile picture" i], a[aria-label*="foto de perfil" i], a[aria-label*="avatar" i]');
                        if (avatarLink) {
                            const img = avatarLink.querySelector('img');
                            if (img && img.src && (img.src.includes('scontent') || img.src.includes('fbcdn'))) {
                                return img.src;
                            }
                        }

                        // Method 3: First large scontent image that's not a cover photo
                        const allImgs = document.querySelectorAll('img');
                        for (const img of allImgs) {
                            const src = img.src || '';
                            if (!src.includes('scontent') && !src.includes('fbcdn')) continue;
                            if (src.includes('emoji') || src.includes('rsrc')) continue;
                            const w = img.width || img.naturalWidth || 0;
                            const h = img.height || img.naturalHeight || 0;
                            // Profile pics are roughly square and 100-200px
                            if (w > 80 && w < 300 && h > 80 && Math.abs(w - h) < 50) {
                                return src;
                            }
                        }

                        // Method 4: Any reasonably-sized scontent image
                        for (const img of allImgs) {
                            const src = img.src || '';
                            if ((src.includes('scontent') || src.includes('fbcdn')) && !src.includes('emoji') && !src.includes('rsrc')) {
                                const w = img.width || img.naturalWidth || 0;
                                if (w > 60 && w < 400) return src;
                            }
                        }

                        return null;
                    }
                """)

                if pic_url:
                    # Clean up the URL — remove stp= for full size
                    try:
                        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
                        parsed = urlparse(pic_url)
                        params = parse_qs(parsed.query)
                        params.pop('stp', None)
                        clean_query = urlencode(params, doseq=True)
                        pic_url = urlunparse(parsed._replace(query=clean_query))
                    except Exception:
                        pass

                    conn.execute("UPDATE agents SET profile_pic_url = ? WHERE id = ?", (pic_url, agent_id))
                    conn.commit()
                    updated += 1
                    log.info(f"    Got pic for {name}")
                else:
                    log.info(f"    No pic found for {name}")

                # Human-like delay between profiles
                await asyncio.sleep(random.uniform(4, 8))

            except Exception as e:
                log.warning(f"    Error on {name}: {e}")
                continue

        # Save session
        try:
            await context.storage_state(path=str(session_path))
        except Exception:
            pass

        await browser.close()

    conn.close()
    log.info(f"Done — updated {updated}/{len(rows)} agent profile pics")


if __name__ == "__main__":
    asyncio.run(scrape_profile_pics())
