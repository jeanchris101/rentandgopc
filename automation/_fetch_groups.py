"""One-time script: log into FB with cookies and list all groups the user is a member of."""
import json, time, random
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
COOKIES_SRC = Path.home() / "Downloads" / "fb-cookies.json"
COOKIES_DST = DATA_DIR / "fb-cookies.json"

# Copy cookies if needed
if not COOKIES_DST.exists() and COOKIES_SRC.exists():
    import shutil
    shutil.copy2(COOKIES_SRC, COOKIES_DST)
    print(f"Copied cookies from Downloads")

data = json.loads(COOKIES_DST.read_text(encoding="utf-8"))
cookies = data.get("cookies", data if isinstance(data, list) else [])

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=False)
    context = browser.new_context(
        viewport={"width": 1366, "height": 768},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    
    # Load cookies
    pw_cookies = []
    for c in cookies:
        cookie = {
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", ".facebook.com"),
            "path": c.get("path", "/"),
        }
        if c.get("expires") and c["expires"] > 0:
            cookie["expires"] = c["expires"]
        if c.get("secure"):
            cookie["secure"] = True
        if c.get("sameSite"):
            ss = c["sameSite"]
            if ss in ("Strict", "Lax", "None"):
                cookie["sameSite"] = ss
        pw_cookies.append(cookie)
    
    context.add_cookies(pw_cookies)
    page = context.new_page()
    
    print("Navigating to Facebook groups page...")
    page.goto("https://www.facebook.com/groups/joins", wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(3, 5))
    
    # Check if logged in
    if "login" in page.url.lower():
        print("ERROR: Not logged in. Cookies may be expired. Re-export from the extension.")
        browser.close()
        exit(1)
    
    # Try the groups feed page instead
    page.goto("https://www.facebook.com/groups/feed/", wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(3, 5))
    
    # Extract groups from the left sidebar or from the groups page
    groups = page.evaluate("""() => {
        const groups = [];
        // Try sidebar links
        const links = document.querySelectorAll('a[href*="/groups/"]');
        const seen = new Set();
        for (const link of links) {
            const href = link.href || '';
            const match = href.match(/facebook\.com\/groups\/([\w.-]+)/);
            if (!match) continue;
            const gid = match[1];
            if (seen.has(gid) || ['feed', 'discover', 'joins', 'settings', 'create'].includes(gid)) continue;
            seen.add(gid);
            const name = link.textContent?.trim() || link.getAttribute('aria-label') || gid;
            // Skip very short or generic names
            if (name.length < 2) continue;
            groups.push({id: gid, name: name.substring(0, 100), url: 'https://www.facebook.com/groups/' + gid});
        }
        return groups;
    }""")
    
    if not groups or len(groups) < 3:
        # Try the /groups/joins page which lists all groups
        print("Trying /groups/joins page...")
        page.goto("https://www.facebook.com/groups/joins", wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(4, 6))
        
        # Light scroll to load more
        for _ in range(3):
            page.mouse.wheel(0, 600)
            time.sleep(random.uniform(1.5, 2.5))
        
        groups2 = page.evaluate("""() => {
            const groups = [];
            const links = document.querySelectorAll('a[href*="/groups/"]');
            const seen = new Set();
            for (const link of links) {
                const href = link.href || '';
                const match = href.match(/facebook\.com\/groups\/([\w.-]+)/);
                if (!match) continue;
                const gid = match[1];
                if (seen.has(gid) || ['feed', 'discover', 'joins', 'settings', 'create'].includes(gid)) continue;
                seen.add(gid);
                const name = link.textContent?.trim() || gid;
                if (name.length < 2) continue;
                groups.push({id: gid, name: name.substring(0, 100), url: 'https://www.facebook.com/groups/' + gid});
            }
            return groups;
        }""")
        
        # Merge
        existing_ids = {g['id'] for g in groups}
        for g in groups2:
            if g['id'] not in existing_ids:
                groups.append(g)
                existing_ids.add(g['id'])
    
    browser.close()

print(f"\nFound {len(groups)} groups:\n")
for i, g in enumerate(groups, 1):
    print(f"  {i}. {g['name']}")
    print(f"     {g['url']}")

# Save to config
config_file = DATA_DIR / "group-assist-config.json"
if config_file.exists():
    config = json.loads(config_file.read_text(encoding="utf-8"))
else:
    config = {"groups": [], "settings": {"scans_per_day": 2, "delay_between_groups_min": 15, "delay_between_groups_max": 30, "max_posts_per_group": 25, "scroll": False}}

existing_ids = {g['id'] for g in config['groups']}
added = 0
for g in groups:
    if g['id'] not in existing_ids:
        config['groups'].append(g)
        added += 1

DATA_DIR.mkdir(parents=True, exist_ok=True)
config_file.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nAdded {added} new groups to config ({len(config['groups'])} total)")
print(f"Config saved to {config_file}")
