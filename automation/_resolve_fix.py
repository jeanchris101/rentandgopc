"""Resolve 5 group IDs that failed due to encoding issues."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import json, time, random
from pathlib import Path
from playwright.sync_api import sync_playwright

DATA_DIR = Path(__file__).parent / "data"
COOKIES_DST = DATA_DIR / "fb-cookies.json"

data = json.loads(COOKIES_DST.read_text(encoding="utf-8"))
cookies = data.get("cookies", data if isinstance(data, list) else [])

# The 5 IDs that crashed with charmap encoding error
failed_ids = [
    "1803616020245169",
    "878923082826821",
    "895913871631541",
    "271641656703550",
    "429272671315684",
]

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=False)
    context = browser.new_context(
        viewport={"width": 1366, "height": 768},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )

    pw_cookies = []
    for c in cookies:
        cookie = {"name": c["name"], "value": c["value"], "domain": c.get("domain", ".facebook.com"), "path": c.get("path", "/")}
        if c.get("expires") and c["expires"] > 0: cookie["expires"] = c["expires"]
        if c.get("secure"): cookie["secure"] = True
        if c.get("sameSite") and c["sameSite"] in ("Strict", "Lax", "None"): cookie["sameSite"] = c["sameSite"]
        pw_cookies.append(cookie)

    context.add_cookies(pw_cookies)
    page = context.new_page()

    # Quick login check
    page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=15000)
    time.sleep(2)

    for gid in failed_ids:
        url = f"https://www.facebook.com/groups/{gid}"
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=10000)
            time.sleep(random.uniform(1.0, 2.0))

            name = page.evaluate("""() => {
                const h1 = document.querySelector('h1');
                if (h1 && h1.textContent.trim().length > 2) return h1.textContent.trim();
                const title = document.title || '';
                return title.replace(' | Facebook', '').trim();
            }""")

            if name and len(name) > 2 and name != "Facebook":
                print(f"  {gid} -> {name}")
                results.append({"id": gid, "name": name, "url": url})
            else:
                print(f"  {gid} -> ??? (could not resolve)")
        except Exception as e:
            print(f"  {gid} -> ERROR: {e}")

        time.sleep(random.uniform(1, 1.5))

    browser.close()

# Save results
out = DATA_DIR / "resolved-fix.json"
out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nResolved {len(results)}/{len(failed_ids)} groups -> {out}")
