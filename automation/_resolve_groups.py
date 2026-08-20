"""Visit numeric group IDs to resolve their real names."""
import json, time, random, shutil
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
COOKIES_DST = DATA_DIR / "fb-cookies.json"

data = json.loads(COOKIES_DST.read_text(encoding="utf-8"))
cookies = data.get("cookies", data if isinstance(data, list) else [])

# These are the numeric IDs we need to resolve
# Excluding already-known groups and clearly unrelated ones (crypto, vegan, poker)
unknown_ids = [
    "127319757381903",
    "1803616020245169",
    "1502081570566337",
    "795575505315883",
    "240857305389274",
    "1180491786364712",
    "293893131726725",
    "891558926265185",
    "3474701412856852",
    "878923082826821",
    "1641874669356890",
    "213138242597239",
    "435849243282131",
    "480318466440980",
    "171071510976684",
    "587885753186026",
    "709518516460301",
    "604142596286067",
    "895913871631541",
    "1439107519489439",
    "271641656703550",
    "566538520131901",
    "339282416279056",
    "429272671315684",
    "670552130398142",
    "1019262982189624",
    "1838130369633274",
    "135915263778647",
    "1520320671606607",
    "103771743755671",
    "426973424124745",
    "2382720238632839",
    "200985427679951",
    "781337178563502",
    "2047287342257788",
    "639228149745280",
    "1196128140497288",
    "735596799929711",
]

from playwright.sync_api import sync_playwright

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
    
    for gid in unknown_ids:
        url = f"https://www.facebook.com/groups/{gid}"
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=10000)
            time.sleep(random.uniform(1.5, 2.5))
            
            # Try to get group name from h1 or page title
            name = page.evaluate("""() => {
                // Try h1 first
                const h1 = document.querySelector('h1');
                if (h1 && h1.textContent.trim().length > 2) return h1.textContent.trim();
                // Try title
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
        
        time.sleep(random.uniform(1, 2))
    
    browser.close()

# Save results
(DATA_DIR / "resolved-groups.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nResolved {len(results)}/{len(unknown_ids)} groups")
