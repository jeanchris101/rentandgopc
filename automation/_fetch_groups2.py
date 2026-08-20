"""Fetch ALL groups the user is a member of — with deeper scrolling."""
import json, time, random, shutil
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
COOKIES_DST = DATA_DIR / "fb-cookies.json"
COOKIES_SRC = Path.home() / "Downloads" / "fb-cookies.json"

if not COOKIES_DST.exists() and COOKIES_SRC.exists():
    shutil.copy2(COOKIES_SRC, COOKIES_DST)

data = json.loads(COOKIES_DST.read_text(encoding="utf-8"))
cookies = data.get("cookies", data if isinstance(data, list) else [])

from playwright.sync_api import sync_playwright

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
    
    # Go to the "Your groups" page
    print("Opening your groups page...")
    page.goto("https://www.facebook.com/groups/joins", wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(3, 5))
    
    if "login" in page.url.lower():
        print("ERROR: Not logged in. Re-export cookies.")
        browser.close()
        exit(1)
    
    # Scroll deep to load all groups
    print("Scrolling to load all groups...")
    prev_count = 0
    stale_rounds = 0
    for i in range(20):
        page.mouse.wheel(0, random.randint(800, 1200))
        time.sleep(random.uniform(1.5, 2.5))
        
        # Count group links
        count = page.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="/groups/"]');
            const seen = new Set();
            for (const l of links) {
                const m = (l.href||'').match(/facebook\.com\/groups\/([\w.-]+)/);
                if (m && !['feed','discover','joins','settings','create'].includes(m[1])) seen.add(m[1]);
            }
            return seen.size;
        }""")
        
        if count == prev_count:
            stale_rounds += 1
            if stale_rounds >= 3:
                print(f"  No new groups after {i+1} scrolls. Done.")
                break
        else:
            stale_rounds = 0
            prev_count = count
        print(f"  Scroll {i+1}: {count} groups found")
    
    # Extract all groups
    groups = page.evaluate("""() => {
        const groups = [];
        const links = document.querySelectorAll('a[href*="/groups/"]');
        const seen = new Set();
        for (const link of links) {
            const href = link.href || '';
            const match = href.match(/facebook\.com\/groups\/([\w.-]+)/);
            if (!match) continue;
            const gid = match[1];
            if (seen.has(gid) || ['feed','discover','joins','settings','create'].includes(gid)) continue;
            seen.add(gid);
            // Get the name - try the link text, clean up "Last active" suffix
            let name = link.textContent?.trim() || gid;
            name = name.replace(/Last active.*$/i, '').trim();
            if (name.length < 2) continue;
            groups.push({id: gid, name: name.substring(0, 100), url: 'https://www.facebook.com/groups/' + gid});
        }
        return groups;
    }""")
    
    browser.close()

print(f"\nFound {len(groups)} groups total:\n")
for i, g in enumerate(groups, 1):
    print(f"  {i:2}. {g['name']}")
    print(f"      {g['url']}")

# Save full list for reference
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "all-groups-found.json").write_text(json.dumps(groups, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nFull list saved to {DATA_DIR / 'all-groups-found.json'}")
