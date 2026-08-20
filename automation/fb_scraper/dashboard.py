"""
FB Listings Dashboard — Real estate market intelligence viewer.
Single-file FastAPI app serving a modern visual dashboard for scraped FB group data.
Run: python3 dashboard.py (or uvicorn dashboard:app --host 0.0.0.0 --port 8050)
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
import uvicorn

DB_PATH = Path(__file__).parent.parent / "data" / "fb_listings.db"
CONSTRUCTORAS_PATH = Path(__file__).parent / "constructoras.json"
IMAGE_DIR = Path(__file__).parent.parent / "data" / "images"

app = FastAPI(title="Rent&Go PC — Real Estate Dashboard")


@app.get("/images/{filename}")
def serve_image(filename: str):
    """Serve locally cached images."""
    filepath = IMAGE_DIR / filename
    if filepath.exists() and filepath.stat().st_size > 0:
        return FileResponse(filepath, media_type="image/jpeg")
    from fastapi.responses import Response
    return Response(status_code=404)


@app.get("/imgproxy")
def proxy_image(url: str):
    """Proxy an external image URL through the VPS (FB CDN URLs are region-locked).
    Also caches the downloaded image locally for future requests."""
    import hashlib
    import httpx
    from fastapi.responses import Response
    if not url.startswith("https://"):
        return Response(status_code=400)
    # Check cache first (hash of URL)
    url_hash = hashlib.md5(url.encode()).hexdigest()[:16]
    cache_path = IMAGE_DIR / f"proxy_{url_hash}.jpg"
    if cache_path.exists():
        if cache_path.stat().st_size > 500:
            return FileResponse(cache_path, media_type="image/jpeg",
                                headers={"Cache-Control": "public, max-age=604800"})
        else:
            # Previously failed — don't retry
            return Response(status_code=404)
    try:
        r = httpx.get(url, timeout=8, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if r.status_code == 200 and len(r.content) > 500:
            # Cache locally
            cache_path.write_bytes(r.content)
            ct = r.headers.get("content-type", "image/jpeg")
            return Response(content=r.content, media_type=ct,
                            headers={"Cache-Control": "public, max-age=604800"})
    except Exception:
        pass
    # Mark as failed so we don't retry on every page load
    cache_path.write_bytes(b"EXPIRED")
    return Response(status_code=404)


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, str) and v.startswith("["):
            try:
                d[k] = json.loads(v)
            except (json.JSONDecodeError, ValueError):
                pass
    return d


def _safe_img_id(post_id: str) -> str:
    """Sanitize post_id for filename."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in (post_id or ""))


def _resolve_images(post_id: str, image_urls) -> list:
    """Return image URLs, preferring local cached files, falling back to FB CDN URLs."""
    if not image_urls:
        return []
    if isinstance(image_urls, str):
        try:
            image_urls = json.loads(image_urls)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(image_urls, list):
        return []

    safe_id = _safe_img_id(post_id)
    result = []
    for idx, url in enumerate(image_urls[:5]):
        fname = f"{safe_id}_{idx}.jpg"
        filepath = IMAGE_DIR / fname
        if filepath.exists() and filepath.stat().st_size > 0:
            result.append(f"/images/{fname}")
        elif url and isinstance(url, str) and url.startswith("http"):
            # Proxy through VPS — user's browser can't reach FB CDN directly
            from urllib.parse import quote
            result.append(f"/imgproxy?url={quote(url, safe='')}")
    return result


# ─── API Endpoints ───


NON_PC_CITIES = [
    'santo domingo', 'santiago', 'la romana', 'san pedro', 'puerto plata',
    'samana', 'samaná', 'sosua', 'sosúa', 'cabarete', 'jarabacoa', 'constanza',
    'bonao', 'la vega', 'azua', 'barahona', 'monte plata', 'hato mayor',
    'san cristobal', 'san cristóbal', 'nagua', 'moca', 'distrito nacional',
]


@app.get("/api/stats")
def api_stats():
    conn = get_db()
    # Exclude spam from all counts
    stats = {
        "total_posts": conn.execute("SELECT COUNT(*) FROM raw_posts").fetchone()[0],
        "total_listings": conn.execute(
            "SELECT COUNT(*) FROM listings WHERE is_spam = 0 AND is_duplicate = 0"
        ).fetchone()[0],
        "with_price": conn.execute(
            "SELECT COUNT(*) FROM listings WHERE price_usd IS NOT NULL AND price_usd > 0 AND is_spam = 0 AND is_duplicate = 0"
        ).fetchone()[0],
        "needs_review": conn.execute(
            "SELECT COUNT(*) FROM listings WHERE needs_review = 1 AND is_spam = 0 AND is_duplicate = 0"
        ).fetchone()[0],
        "agents": conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0],
        "pro_agents": conn.execute("SELECT COUNT(*) FROM agents WHERE is_agent = 1").fetchone()[0],
        "properties": conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0],
        "groups": conn.execute("SELECT COUNT(DISTINCT group_name) FROM raw_posts").fetchone()[0],
        "zones": {},
        "avg_price_by_zone": {},
        "property_types": {},
        "listing_types": {},
        "scrape_history": [],
        "group_stats": [],
    }

    rows = conn.execute(
        "SELECT neighborhood, COUNT(*) as c FROM listings WHERE neighborhood IS NOT NULL AND is_spam = 0 AND is_duplicate = 0 GROUP BY neighborhood ORDER BY c DESC"
    ).fetchall()
    stats["zones"] = {r["neighborhood"]: r["c"] for r in rows}

    rows = conn.execute(
        "SELECT neighborhood, ROUND(AVG(price_usd)) as avg_p, MIN(price_usd) as min_p, MAX(price_usd) as max_p, COUNT(*) as c "
        "FROM listings WHERE neighborhood IS NOT NULL AND price_usd > 1000 AND is_spam = 0 AND is_duplicate = 0 "
        "GROUP BY neighborhood ORDER BY avg_p DESC"
    ).fetchall()
    stats["avg_price_by_zone"] = {
        r["neighborhood"]: {"avg": r["avg_p"], "min": r["min_p"], "max": r["max_p"], "count": r["c"]}
        for r in rows
    }

    rows = conn.execute(
        "SELECT property_type, COUNT(*) as c FROM listings WHERE property_type IS NOT NULL AND is_spam = 0 AND is_duplicate = 0 GROUP BY property_type ORDER BY c DESC"
    ).fetchall()
    stats["property_types"] = {r["property_type"]: r["c"] for r in rows}

    rows = conn.execute(
        "SELECT listing_type, COUNT(*) as c FROM listings WHERE listing_type IS NOT NULL AND is_spam = 0 AND is_duplicate = 0 GROUP BY listing_type ORDER BY c DESC"
    ).fetchall()
    stats["listing_types"] = {r["listing_type"]: r["c"] for r in rows}

    rows = conn.execute(
        "SELECT group_name, posts_new, posts_captured, status, started_at, finished_at "
        "FROM scrape_log ORDER BY id DESC LIMIT 20"
    ).fetchall()
    stats["scrape_history"] = [dict(r) for r in rows]

    rows = conn.execute(
        """SELECT r.group_name, COUNT(*) as posts,
                  SUM(CASE WHEN l.price_usd IS NOT NULL AND l.price_usd > 0 AND COALESCE(l.is_duplicate,0) = 0 THEN 1 ELSE 0 END) as with_price,
                  SUM(CASE WHEN COALESCE(l.is_duplicate,0) = 0 AND COALESCE(l.is_spam,0) = 0 THEN 1 ELSE 0 END) as valid_listings,
                  MAX(r.captured_at) as last_scraped
           FROM raw_posts r LEFT JOIN listings l ON l.post_id = r.post_id
           GROUP BY r.group_name"""
    ).fetchall()
    stats["group_stats"] = [dict(r) for r in rows]

    conn.close()
    return stats


@app.get("/api/listings")
def api_listings(
    zone: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    bedrooms: Optional[int] = None,
    property_type: Optional[str] = None,
    listing_type: Optional[str] = None,
    group: Optional[str] = None,
    search: Optional[str] = None,
    has_price: Optional[bool] = None,
    needs_review: Optional[bool] = None,
    is_listing: Optional[bool] = None,
    pc_only: Optional[bool] = None,
    non_pc: Optional[bool] = None,
    exclude_ptype: Optional[str] = None,
    sort: str = "newest",
    limit: int = 24,
    offset: int = 0,
):
    conn = get_db()
    where = ["1=1"]
    params = []

    # Always exclude duplicates; exclude spam unless requesting review queue
    where.append("l.is_duplicate = 0")
    if needs_review is None or not needs_review:
        where.append("l.is_spam = 0")

    if zone:
        where.append("l.neighborhood = ?")
        params.append(zone)
    if min_price is not None:
        where.append("l.price_usd >= ?")
        params.append(min_price)
    if max_price is not None:
        where.append("l.price_usd <= ?")
        params.append(max_price)
    if bedrooms is not None:
        where.append("l.bedrooms = ?")
        params.append(bedrooms)
    if property_type:
        if property_type == "land":
            where.append("LOWER(COALESCE(l.property_type,'')) IN ('land','lot','solar','terreno')")
        else:
            where.append("l.property_type = ?")
            params.append(property_type)
    if listing_type:
        if listing_type == "rent":
            where.append("LOWER(COALESCE(l.listing_type,'')) IN ('rent','rental','alquiler')")
        elif listing_type == "short_term_rent":
            where.append("LOWER(COALESCE(l.listing_type,'')) IN ('short_term_rent','short-term','airbnb','nightly')")
        elif listing_type == "sale":
            where.append("LOWER(COALESCE(l.listing_type,'')) IN ('sale','venta','for sale')")
        else:
            where.append("l.listing_type = ?")
            params.append(listing_type)
    if has_price:
        where.append("l.price_usd IS NOT NULL AND l.price_usd > 0")
    if needs_review is not None:
        where.append("l.needs_review = ?")
        params.append(1 if needs_review else 0)
    if is_listing:
        where.append("(l.price_usd IS NOT NULL OR l.property_type IS NOT NULL OR l.bedrooms IS NOT NULL)")
        where.append("l.confidence >= 0.3")
    if group:
        where.append("r.group_name = ?")
        params.append(group)
    if search:
        where.append("r.raw_text LIKE ?")
        params.append(f"%{search}%")

    if exclude_ptype:
        excluded = []
        for et in exclude_ptype.split(","):
            et = et.strip().lower()
            if et == "land":
                excluded.extend(["land", "lot", "solar", "terreno"])
            elif et == "commercial":
                excluded.extend(["commercial", "local comercial", "oficina"])
            elif et:
                excluded.append(et)
        if excluded:
            placeholders = ",".join("?" for _ in excluded)
            where.append(f"(l.property_type IS NULL OR LOWER(l.property_type) NOT IN ({placeholders}))")
            params.extend(excluded)
        # Also exclude by text content — catches misclassified solares/terrenos
        if any(t in excluded for t in ["land", "lot", "solar", "terreno"]):
            where.append(
                "NOT (LOWER(SUBSTR(COALESCE(r.raw_text,''),1,200)) LIKE '%solar%' "
                "OR LOWER(SUBSTR(COALESCE(r.raw_text,''),1,200)) LIKE '%terreno%' "
                "OR LOWER(SUBSTR(COALESCE(r.raw_text,''),1,200)) LIKE '%solares%')"
            )

    if pc_only:
        non_pc_clauses = []
        for city in NON_PC_CITIES:
            non_pc_clauses.append(
                "LOWER(COALESCE(l.neighborhood,'') || ' ' || COALESCE(l.community,'') || ' ' || SUBSTR(COALESCE(r.raw_text,''),1,300)) NOT LIKE ?"
            )
            params.append(f"%{city}%")
        where.append("(" + " AND ".join(non_pc_clauses) + ")")

    if non_pc:
        # Only show listings from non-PC cities
        non_pc_or = []
        for city in NON_PC_CITIES:
            non_pc_or.append(
                "LOWER(COALESCE(l.neighborhood,'') || ' ' || COALESCE(l.community,'') || ' ' || SUBSTR(COALESCE(r.raw_text,''),1,300)) LIKE ?"
            )
            params.append(f"%{city}%")
        where.append("(" + " OR ".join(non_pc_or) + ")")

    order = {
        "newest": "r.captured_at DESC",
        "oldest": "r.captured_at ASC",
        "price_high": "COALESCE(l.price_usd, 0) DESC",
        "price_low": "CASE WHEN l.price_usd IS NULL OR l.price_usd = 0 THEN 1 ELSE 0 END, l.price_usd ASC",
        "confidence": "l.confidence DESC",
    }.get(sort, "r.captured_at DESC")

    where_clause = " AND ".join(where)

    count = conn.execute(
        f"SELECT COUNT(*) FROM listings l JOIN raw_posts r ON l.post_id = r.post_id WHERE {where_clause}",
        params,
    ).fetchone()[0]

    rows = conn.execute(
        f"""SELECT l.*, r.author_name, r.raw_text, r.image_urls as post_images,
                   r.group_id, r.group_name, r.captured_at, r.permalink, r.timestamp as post_time,
                   a.name as agent_name_full, a.fb_profile_url as agent_fb_url,
                   a.phones as agent_phones, a.whatsapp as agent_whatsapp,
                   a.total_listings as agent_total, a.is_agent as agent_is_pro,
                   p.image_urls as prop_images, p.zone as prop_zone
            FROM listings l
            JOIN raw_posts r ON l.post_id = r.post_id
            LEFT JOIN agents a ON l.agent_id = a.id
            LEFT JOIN properties p ON l.property_id = p.id
            WHERE {where_clause}
            ORDER BY {order}
            LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()

    results = []
    for r in rows:
        d = row_to_dict(r)
        # Resolve images: prefer local cached files over expired FB CDN URLs
        d["post_images"] = _resolve_images(d.get("post_id", ""), d.get("post_images"))
        results.append(d)
    conn.close()
    return {"total": count, "listings": results, "limit": limit, "offset": offset}


@app.get("/api/agents")
def api_agents(sort: str = "listings", limit: int = 50, offset: int = 0):
    conn = get_db()
    order = {
        "listings": "active_listings DESC",
        "name": "a.name ASC",
        "recent": "a.last_seen_at DESC",
    }.get(sort, "active_listings DESC")

    cols = [r[1] for r in conn.execute("PRAGMA table_info(agents)").fetchall()]
    pic_col = ", a.profile_pic_url" if "profile_pic_url" in cols else ", NULL as profile_pic_url"

    count = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]

    rows = conn.execute(
        f"""SELECT a.*{pic_col},
                   COUNT(DISTINCT r.group_name) as groups_active,
                   SUM(CASE WHEN COALESCE(l.is_duplicate,0) = 0 AND COALESCE(l.is_spam,0) = 0 THEN 1 ELSE 0 END) as active_listings
            FROM agents a
            LEFT JOIN raw_posts r ON r.agent_id = a.id
            LEFT JOIN listings l ON l.post_id = r.post_id
            GROUP BY a.id
            ORDER BY {order}
            LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()
    results = []
    for r in rows:
        d = row_to_dict(r)
        # Use live count excluding duplicates instead of stored total_listings
        d["total_listings"] = d.get("active_listings") or 0
        results.append(d)
    conn.close()
    return {"agents": results, "total": count, "limit": limit, "offset": offset}


@app.get("/api/groups")
def api_groups():
    conn = get_db()
    rows = conn.execute(
        """SELECT r.group_id, r.group_name,
                  COUNT(*) as total_posts,
                  SUM(CASE WHEN COALESCE(l.is_duplicate,0) = 0 AND COALESCE(l.is_spam,0) = 0 THEN 1 ELSE 0 END) as valid_listings,
                  SUM(CASE WHEN l.price_usd IS NOT NULL AND l.price_usd > 0 AND COALESCE(l.is_duplicate,0) = 0 THEN 1 ELSE 0 END) as priced_listings,
                  MIN(r.captured_at) as first_scraped,
                  MAX(r.captured_at) as last_scraped,
                  COUNT(DISTINCT r.agent_id) as unique_agents
           FROM raw_posts r
           LEFT JOIN listings l ON l.post_id = r.post_id
           GROUP BY COALESCE(r.group_id, r.group_name)
           ORDER BY total_posts DESC"""
    ).fetchall()
    results = [dict(r) for r in rows]
    conn.close()
    return {"groups": results}


@app.get("/api/constructoras")
def api_constructoras():
    if CONSTRUCTORAS_PATH.exists():
        data = json.loads(CONSTRUCTORAS_PATH.read_text(encoding="utf-8"))
    else:
        data = []
    return {"constructoras": data, "total": len(data)}


@app.get("/api/properties")
def api_properties(zone: Optional[str] = None, limit: int = 50):
    conn = get_db()
    where = ["1=1"]
    params = []
    if zone:
        where.append("p.zone = ?")
        params.append(zone)

    rows = conn.execute(
        f"""SELECT p.*, COUNT(pa.agent_id) as num_agents
            FROM properties p
            LEFT JOIN property_agents pa ON pa.property_id = p.id
            WHERE {" AND ".join(where)}
            GROUP BY p.id
            ORDER BY p.price_usd DESC NULLS LAST
            LIMIT ?""",
        params + [limit],
    ).fetchall()
    results = [row_to_dict(r) for r in rows]
    conn.close()
    return {"properties": results}


# ─── Dashboard HTML ───

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rent&Go PC — Punta Cana Real Estate</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0a0b10;
  --surface: #12141c;
  --surface2: #1a1d28;
  --surface3: #242836;
  --border: #282d3e;
  --border-hover: #3a4058;
  --text: #eaecf4;
  --text2: #8b90a8;
  --text3: #5a5f78;
  --accent: #6366f1;
  --accent2: #818cf8;
  --accent-glow: rgba(99,102,241,0.15);
  --green: #10b981;
  --green-bg: rgba(16,185,129,0.10);
  --yellow: #f59e0b;
  --yellow-bg: rgba(245,158,11,0.10);
  --red: #ef4444;
  --red-bg: rgba(239,68,68,0.10);
  --blue: #3b82f6;
  --blue-bg: rgba(59,130,246,0.10);
  --orange: #f97316;
  --orange-bg: rgba(249,115,22,0.10);
  --purple-bg: rgba(99,102,241,0.10);
  --gradient1: linear-gradient(135deg, #6366f1, #8b5cf6);
  --gradient2: linear-gradient(135deg, #10b981, #06b6d4);
  --gradient3: linear-gradient(135deg, #f59e0b, #f97316);
  --shadow: 0 8px 32px rgba(0,0,0,0.4);
  --shadow-sm: 0 2px 12px rgba(0,0,0,0.25);
  --radius: 14px;
  --radius-sm: 10px;
  --radius-xs: 7px;
}
* { margin:0; padding:0; box-sizing:border-box; }
html { scroll-behavior: smooth; }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--accent2); text-decoration: none; transition: color 0.2s; }
a:hover { color: #a5b4fc; }
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text3); }

/* ─── Navigation Bar ─── */
.navbar {
  position: sticky; top: 0; z-index: 100;
  background: rgba(10,11,16,0.92); backdrop-filter: blur(16px) saturate(180%);
  border-bottom: 1px solid var(--border);
  padding: 0 32px; height: 60px;
  display: flex; align-items: center; gap: 0;
}
.nav-brand {
  font-size: 19px; font-weight: 900; letter-spacing: -0.5px;
  margin-right: 32px; white-space: nowrap; cursor: pointer;
  display: flex; align-items: center; gap: 10px;
}
.nav-brand .logo-r { color: var(--accent2); }
.nav-brand .logo-go {
  background: var(--gradient1); -webkit-background-clip: text;
  -webkit-text-fill-color: transparent; background-clip: text;
}
.nav-brand .logo-pc { color: var(--text2); font-weight: 600; font-size: 13px; }
.nav-links { display: flex; align-items: center; gap: 0; flex: 1; }
.nav-link {
  padding: 18px 20px; cursor: pointer; border: none; background: none;
  color: var(--text2); font-size: 14px; font-weight: 600;
  position: relative; transition: color 0.2s; white-space: nowrap;
  font-family: inherit;
}
.nav-link:hover { color: var(--text); }
.nav-link.active { color: white; }
.nav-link.active::after {
  content: ''; position: absolute; bottom: 0; left: 16px; right: 16px;
  height: 2px; background: var(--accent); border-radius: 2px 2px 0 0;
}
.nav-admin {
  margin-left: auto; padding: 8px 14px; border-radius: var(--radius-sm);
  background: var(--surface2); border: 1px solid var(--border);
  color: var(--text2); cursor: pointer; font-size: 16px;
  transition: all 0.2s; display: flex; align-items: center; gap: 6px;
  font-family: inherit;
}
.nav-admin:hover { border-color: var(--accent); color: var(--text); }
.nav-admin.active { border-color: var(--accent); color: var(--accent2); background: var(--accent-glow); }
.nav-admin span { font-size: 12px; font-weight: 600; }

/* ─── Sub-pills ─── */
.sub-pills {
  display: flex; gap: 6px; padding: 4px; background: var(--surface);
  border-radius: var(--radius-sm); width: fit-content; margin-bottom: 20px;
}
.pill {
  padding: 8px 18px; border-radius: var(--radius-xs); border: none;
  background: none; color: var(--text2); font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all 0.2s; white-space: nowrap; font-family: inherit;
}
.pill:hover { color: var(--text); background: var(--surface2); }
.pill.active { color: white; background: var(--accent); }

/* ─── Container ─── */
.container { max-width: 1480px; margin: 0 auto; padding: 24px 32px; }
.section { display: none; }
.section.active { display: block; }

/* ─── Stat Cards ─── */
.stats-row {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px; margin-bottom: 24px;
}
.stat-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 18px 22px; position: relative; overflow: hidden;
  transition: border-color 0.2s;
}
.stat-card:hover { border-color: var(--border-hover); }
.stat-card::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
}
.stat-card:nth-child(1)::before { background: var(--gradient1); }
.stat-card:nth-child(2)::before { background: var(--gradient2); }
.stat-card:nth-child(3)::before { background: var(--gradient3); }
.stat-card:nth-child(4)::before { background: linear-gradient(135deg, #ec4899, #f43f5e); }
.stat-card:nth-child(5)::before { background: linear-gradient(135deg, #3b82f6, #06b6d4); }
.stat-card:nth-child(6)::before { background: linear-gradient(135deg, #8b5cf6, #a855f7); }
.stat-label {
  font-size: 10px; color: var(--text3); text-transform: uppercase;
  letter-spacing: 1.2px; font-weight: 700;
}
.stat-value { font-size: 32px; font-weight: 900; margin-top: 6px; letter-spacing: -1px; }
.stat-sub { font-size: 11px; color: var(--text3); margin-top: 2px; }

/* ─── Filters ─── */
.filters-bar {
  display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; padding: 16px 20px;
  background: var(--surface); border-radius: var(--radius); border: 1px solid var(--border);
  align-items: flex-end;
}
.fg { display: flex; flex-direction: column; gap: 5px; }
.fg label {
  font-size: 10px; color: var(--text3); text-transform: uppercase;
  letter-spacing: 1px; font-weight: 700;
}
.fg select, .fg input {
  background: var(--surface2); border: 1px solid var(--border); color: var(--text);
  padding: 9px 12px; border-radius: var(--radius-xs); font-size: 13px;
  min-width: 130px; outline: none; transition: border-color 0.2s;
  font-family: inherit;
}
.fg select:focus, .fg input:focus { border-color: var(--accent); }
.fg input[type="text"] { min-width: 200px; }
.btn {
  padding: 9px 18px; border-radius: var(--radius-xs); border: none; cursor: pointer;
  font-size: 13px; font-weight: 600; transition: all 0.2s; font-family: inherit;
}
.btn-primary { background: var(--accent); color: white; }
.btn-primary:hover { background: var(--accent2); transform: translateY(-1px); }
.btn-ghost { background: var(--surface2); color: var(--text2); border: 1px solid var(--border); }
.btn-ghost:hover { color: var(--text); border-color: var(--text2); }

/* ─── Property Cards Grid ─── */
.cards-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 18px;
}
.card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); overflow: hidden;
  transition: all 0.25s ease; cursor: pointer; position: relative;
}
.card:hover { border-color: var(--accent); transform: translateY(-3px); box-shadow: var(--shadow); }

/* Gallery */
.card-gallery {
  position: relative; height: 220px; overflow: hidden;
  display: grid; gap: 2px;
}
.card-gallery.g1 { grid-template-columns: 1fr; }
.card-gallery.g2 { grid-template-columns: 1fr 1fr; }
.card-gallery.g3 { grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; }
.card-gallery img {
  width: 100%; height: 100%; object-fit: cover; display: block;
  background: var(--surface2); transition: transform 0.3s;
}
.card:hover .card-gallery img { transform: scale(1.03); }
.card-gallery.g3 img:first-child { grid-row: 1 / 3; }
.card-gallery .photo-count {
  position: absolute; bottom: 8px; right: 8px;
  background: rgba(0,0,0,0.7); backdrop-filter: blur(4px);
  color: white; padding: 3px 10px; border-radius: 20px;
  font-size: 11px; font-weight: 600;
}
.card-placeholder {
  height: 220px; background: var(--surface2);
  display: flex; align-items: center; justify-content: center;
  color: var(--text3); font-size: 48px;
}

/* Card body */
.card-body { padding: 16px 18px 12px; }
.card-price-row {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;
}
.card-price { font-size: 22px; font-weight: 800; letter-spacing: -0.5px; }
.card-price.no-price { color: var(--text3); font-size: 14px; font-weight: 600; }
.card-price .period { font-size: 13px; color: var(--text2); font-weight: 400; }
.card-badges { display: flex; gap: 4px; flex-shrink: 0; flex-wrap: wrap; }
.card-location {
  font-size: 13px; color: var(--text2); margin-top: 6px; font-weight: 500;
  display: flex; align-items: center; gap: 5px;
}
.card-location svg { width: 13px; height: 13px; fill: var(--text3); flex-shrink: 0; }
.card-specs {
  display: flex; gap: 14px; margin-top: 8px;
  font-size: 13px; color: var(--text2); font-weight: 500;
}
.card-specs span { display: flex; align-items: center; gap: 4px; }
.card-specs .sep { color: var(--text3); }
.card-desc {
  font-size: 12.5px; color: var(--text2); line-height: 1.5; margin-top: 8px;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
  overflow: hidden; word-break: break-word;
}

/* Card footer */
.card-footer {
  padding: 12px 18px; border-top: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.card-agent { display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1; }
.card-agent-avatar {
  width: 30px; height: 30px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; color: white;
}
.card-agent-avatar img { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }
.card-agent-name { font-size: 12px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.card-agent-time { font-size: 11px; color: var(--text3); white-space: nowrap; }
.card-contact {
  display: flex; gap: 6px; flex-shrink: 0;
}
.card-contact a {
  padding: 5px 10px; border-radius: var(--radius-xs); font-size: 11px;
  font-weight: 600; transition: all 0.2s; text-decoration: none; white-space: nowrap;
}
.card-contact .wa { background: rgba(37,211,102,0.12); color: #25d366; }
.card-contact .wa:hover { background: rgba(37,211,102,0.25); }
.card-contact .call { background: var(--green-bg); color: var(--green); }
.card-contact .call:hover { background: rgba(16,185,129,0.2); }
.card-contact .fb { background: var(--blue-bg); color: var(--blue); }
.card-contact .fb:hover { background: rgba(59,130,246,0.2); }

/* ─── Expanded card ─── */
.card-expand {
  max-height: 0; overflow: hidden;
  transition: max-height 0.4s ease, padding 0.3s ease;
  border-top: 0px solid var(--border);
}
.card.expanded .card-expand {
  max-height: 2000px; padding: 16px 18px;
  border-top: 1px solid var(--border);
}
.card.expanded { transform: none; }
.card.expanded:hover { transform: none; }
.card-expand-inner { opacity: 0; transition: opacity 0.3s ease 0.1s; }
.card.expanded .card-expand-inner { opacity: 1; }
.expand-text {
  font-size: 13px; color: var(--text2); line-height: 1.7;
  white-space: pre-wrap; word-break: break-word; margin-bottom: 14px;
}
.expand-gallery {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 6px; margin-bottom: 14px;
}
.expand-gallery img {
  width: 100%; height: 120px; object-fit: cover; border-radius: var(--radius-xs);
  background: var(--surface2); cursor: pointer; transition: transform 0.2s;
}
.expand-gallery img:hover { transform: scale(1.05); }
.expand-meta {
  display: flex; flex-wrap: wrap; gap: 16px; font-size: 12px; color: var(--text2);
}
.expand-meta a { font-weight: 600; }

/* ─── Badges ─── */
.badge {
  display: inline-block; padding: 3px 9px; border-radius: 5px;
  font-size: 10px; font-weight: 700; letter-spacing: 0.3px; text-transform: uppercase;
}
.badge-green { background: var(--green-bg); color: var(--green); }
.badge-yellow { background: var(--yellow-bg); color: var(--yellow); }
.badge-red { background: var(--red-bg); color: var(--red); }
.badge-blue { background: var(--blue-bg); color: var(--blue); }
.badge-purple { background: var(--purple-bg); color: var(--accent2); }
.badge-orange { background: var(--orange-bg); color: var(--orange); }

/* ─── Loading / Spinner ─── */
.spinner-wrap {
  display: flex; justify-content: center; padding: 40px 0;
}
.spinner {
  width: 36px; height: 36px; border: 3px solid var(--border);
  border-top-color: var(--accent); border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Skeleton cards */
.skeleton-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 18px;
}
.skeleton-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); overflow: hidden;
}
.skeleton-img {
  height: 220px; background: linear-gradient(90deg, var(--surface2) 25%, var(--surface3) 50%, var(--surface2) 75%);
  background-size: 200% 100%; animation: shimmer 1.5s infinite;
}
.skeleton-body { padding: 16px 18px; }
.skeleton-line {
  height: 14px; border-radius: 4px; margin-bottom: 10px;
  background: linear-gradient(90deg, var(--surface2) 25%, var(--surface3) 50%, var(--surface2) 75%);
  background-size: 200% 100%; animation: shimmer 1.5s infinite;
}
.skeleton-line.w60 { width: 60%; }
.skeleton-line.w80 { width: 80%; }
.skeleton-line.w40 { width: 40%; height: 20px; }
@keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }

/* ─── Infinite scroll sentinel ─── */
.scroll-sentinel { height: 1px; }
.load-more-info {
  text-align: center; padding: 20px; font-size: 13px; color: var(--text3);
}

/* ─── Charts ─── */
.chart-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 18px; margin-bottom: 24px;
}
.chart-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 22px;
}
.chart-card h3 {
  font-size: 12px; text-transform: uppercase; letter-spacing: 1.2px;
  color: var(--text2); margin-bottom: 18px; font-weight: 700;
}
.bar-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.bar-label {
  width: 110px; font-size: 12px; text-align: right; color: var(--text2);
  flex-shrink: 0; font-weight: 500;
}
.bar-track { flex: 1; height: 28px; background: var(--surface2); border-radius: 6px; overflow: hidden; }
.bar-fill {
  height: 100%; border-radius: 6px; display: flex; align-items: center;
  padding-left: 10px; font-size: 11px; font-weight: 700; color: white;
  min-width: 36px; transition: width 0.6s ease;
}
.bar-value { font-size: 12px; width: 80px; text-align: right; color: var(--text2); flex-shrink: 0; font-weight: 600; }

/* ─── Agent cards ─── */
.agents-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px;
}
.agent-card {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 18px; display: flex; gap: 14px; transition: all 0.2s;
}
.agent-card:hover { border-color: var(--border-hover); }
.agent-avatar {
  width: 48px; height: 48px; border-radius: 14px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; font-weight: 800; color: white; overflow: hidden;
}
.agent-avatar img { width: 100%; height: 100%; object-fit: cover; }
.agent-info { flex: 1; min-width: 0; }
.agent-name { font-size: 15px; font-weight: 700; margin-bottom: 4px; }
.agent-meta {
  font-size: 12px; color: var(--text2); display: flex; flex-wrap: wrap; gap: 8px;
}

/* ─── Admin sub-tabs ─── */
.admin-tabs {
  display: flex; gap: 2px; margin-bottom: 20px; background: var(--surface);
  border-radius: var(--radius-sm); padding: 4px; width: fit-content;
}
.admin-tab {
  padding: 8px 18px; cursor: pointer; border: none; background: none;
  color: var(--text2); font-size: 12px; font-weight: 600;
  border-radius: var(--radius-xs); transition: all 0.2s; font-family: inherit;
}
.admin-tab:hover { color: var(--text); background: var(--surface2); }
.admin-tab.active { color: white; background: var(--accent); }
.admin-content { display: none; }
.admin-content.active { display: block; }

/* ─── Table ─── */
.table-wrap {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); overflow: hidden;
}
table { width: 100%; border-collapse: collapse; }
th {
  text-align: left; padding: 12px 16px; font-size: 10px;
  text-transform: uppercase; letter-spacing: 1px; color: var(--text3);
  background: var(--surface2); border-bottom: 1px solid var(--border); font-weight: 700;
}
td {
  padding: 10px 16px; border-bottom: 1px solid var(--border); font-size: 13px;
}
tr:last-child td { border-bottom: none; }
tr:hover { background: var(--surface2); }

/* ─── Results count ─── */
.results-info { font-size: 13px; color: var(--text2); margin-bottom: 14px; }

/* ─── Responsive ─── */
@media (max-width: 768px) {
  .navbar { padding: 0 16px; height: 56px; overflow-x: auto; }
  .nav-brand { margin-right: 16px; font-size: 16px; }
  .nav-link { padding: 16px 12px; font-size: 13px; }
  .cards-grid, .skeleton-grid { grid-template-columns: 1fr; }
  .agents-grid { grid-template-columns: 1fr; }
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .container { padding: 16px; }
  .filters-bar { padding: 12px; }
  .fg select, .fg input { min-width: 100px; }
  .sub-pills { overflow-x: auto; width: 100%; }
  .card-contact a span.label { display: none; }
}
@media (max-width: 480px) {
  .stats-row { grid-template-columns: 1fr; }
  .card-gallery { height: 180px; }
}

/* ─── Image lightbox ─── */
.lightbox {
  display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.9); z-index: 1000;
  align-items: center; justify-content: center; cursor: pointer;
}
.lightbox.open { display: flex; }
.lightbox img { max-width: 92vw; max-height: 92vh; border-radius: 8px; }
</style>
</head>
<body>

<!-- Navigation -->
<nav class="navbar">
  <div class="nav-brand" onclick="switchSection('buy')">
    <span><span class="logo-r">Rent</span><span style="color:var(--text2)">&</span><span class="logo-go">Go</span> <span class="logo-pc">PC</span></span>
  </div>
  <div class="nav-links">
    <button class="nav-link active" data-section="buy">Buy</button>
    <button class="nav-link" data-section="rent">Rent</button>
    <button class="nav-link" data-section="developments">Developments</button>
    <button class="nav-link" data-section="market">Market</button>
    <button class="nav-link" data-section="agents">Agents</button>
  </div>
  <button class="nav-admin" id="adminBtn" onclick="switchSection('admin')">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19.14,12.94c0.04-0.3,0.06-0.61,0.06-0.94c0-0.32-0.02-0.64-0.07-0.94l2.03-1.58c0.18-0.14,0.23-0.41,0.12-0.61 l-1.92-3.32c-0.12-0.22-0.37-0.29-0.59-0.22l-2.39,0.96c-0.5-0.38-1.03-0.7-1.62-0.94L14.4,2.81c-0.04-0.24-0.24-0.41-0.48-0.41 h-3.84c-0.24,0-0.43,0.17-0.47,0.41L9.25,5.35C8.66,5.59,8.12,5.92,7.63,6.29L5.24,5.33c-0.22-0.08-0.47,0-0.59,0.22L2.74,8.87 C2.62,9.08,2.66,9.34,2.86,9.48l2.03,1.58C4.84,11.36,4.8,11.69,4.8,12s0.02,0.64,0.07,0.94l-2.03,1.58 c-0.18,0.14-0.23,0.41-0.12,0.61l1.92,3.32c0.12,0.22,0.37,0.29,0.59,0.22l2.39-0.96c0.5,0.38,1.03,0.7,1.62,0.94l0.36,2.54 c0.05,0.24,0.24,0.41,0.48,0.41h3.84c0.24,0,0.44-0.17,0.47-0.41l0.36-2.54c0.59-0.24,1.13-0.56,1.62-0.94l2.39,0.96 c0.22,0.08,0.47,0,0.59-0.22l1.92-3.32c0.12-0.22,0.07-0.47-0.12-0.61L19.14,12.94z M12,15.6c-1.98,0-3.6-1.62-3.6-3.6 s1.62-3.6,3.6-3.6s3.6,1.62,3.6,3.6S13.98,15.6,12,15.6z"/></svg>
    <span>Admin</span>
  </button>
</nav>

<div class="container">
  <!-- BUY SECTION -->
  <div class="section active" id="sec-buy">
    <div class="stats-row" id="buyStats"></div>
    <div class="sub-pills" id="buyPills">
      <button class="pill active" data-ptype="">All</button>
      <button class="pill" data-ptype="apartment">Apartments</button>
      <button class="pill" data-ptype="villa">Villas</button>
      <button class="pill" data-ptype="condo">Condos</button>
      <button class="pill" data-ptype="penthouse">Penthouses</button>
    </div>
    <div class="filters-bar" id="buyFilters"></div>
    <div class="results-info" id="buyResultsInfo"></div>
    <div class="cards-grid" id="buyGrid"></div>
    <div class="spinner-wrap" id="buySpinner" style="display:none"><div class="spinner"></div></div>
    <div class="scroll-sentinel" id="buySentinel"></div>
    <div class="load-more-info" id="buyEndMsg" style="display:none">All listings loaded</div>
  </div>

  <!-- RENT SECTION -->
  <div class="section" id="sec-rent">
    <div class="stats-row" id="rentStats"></div>
    <div class="sub-pills" id="rentPills">
      <button class="pill active" data-rtype="">All</button>
      <button class="pill" data-rtype="rent">Long-Term</button>
      <button class="pill" data-rtype="short_term_rent">Short-Term</button>
    </div>
    <div class="filters-bar" id="rentFilters"></div>
    <div class="results-info" id="rentResultsInfo"></div>
    <div class="cards-grid" id="rentGrid"></div>
    <div class="spinner-wrap" id="rentSpinner" style="display:none"><div class="spinner"></div></div>
    <div class="scroll-sentinel" id="rentSentinel"></div>
    <div class="load-more-info" id="rentEndMsg" style="display:none">All rentals loaded</div>
  </div>

  <!-- DEVELOPMENTS SECTION -->
  <div class="section" id="sec-developments">
    <div class="stats-row" id="devStats"></div>
    <div class="cards-grid" id="devGrid" style="grid-template-columns:repeat(auto-fill,minmax(380px,1fr))"></div>
  </div>

  <!-- MARKET SECTION -->
  <div class="section" id="sec-market">
    <div class="stats-row" id="marketStats"></div>
    <div class="chart-grid" id="marketCharts"></div>
  </div>

  <!-- AGENTS SECTION -->
  <div class="section" id="sec-agents">
    <div class="results-info" id="agentsResultsInfo"></div>
    <div class="agents-grid" id="agentsGrid"></div>
    <div class="spinner-wrap" id="agentsSpinner" style="display:none"><div class="spinner"></div></div>
    <div class="scroll-sentinel" id="agentsSentinel"></div>
    <div class="load-more-info" id="agentsEndMsg" style="display:none">All agents loaded</div>
  </div>

  <!-- ADMIN SECTION -->
  <div class="section" id="sec-admin">
    <div class="admin-tabs">
      <button class="admin-tab active" data-atab="log">Scrape Log</button>
      <button class="admin-tab" data-atab="groups">Groups</button>
      <button class="admin-tab" data-atab="review">Review Queue</button>
      <button class="admin-tab" data-atab="regions">Other Regions</button>
    </div>
    <div class="admin-content active" id="atab-log">
      <div class="chart-card" id="scrapeLog"></div>
    </div>
    <div class="admin-content" id="atab-groups">
      <div class="agents-grid" id="groupsGrid"></div>
    </div>
    <div class="admin-content" id="atab-review">
      <div class="results-info" id="reviewInfo"></div>
      <div class="cards-grid" id="reviewGrid"></div>
      <div class="spinner-wrap" id="reviewSpinner" style="display:none"><div class="spinner"></div></div>
      <div class="scroll-sentinel" id="reviewSentinel"></div>
    </div>
    <div class="admin-content" id="atab-regions">
      <div class="results-info" id="regionsInfo"></div>
      <div class="cards-grid" id="regionsGrid"></div>
      <div class="spinner-wrap" id="regionsSpinner" style="display:none"><div class="spinner"></div></div>
      <div class="scroll-sentinel" id="regionsSentinel"></div>
    </div>
  </div>
</div>

<!-- Lightbox -->
<div class="lightbox" id="lightbox" onclick="this.classList.remove('open')">
  <img id="lightboxImg" src="">
</div>

<script>
/* ─── Utility ─── */
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const fmt = n => n == null ? '\u2014' : n.toLocaleString('en-US');
const fmtP = n => (!n || n <= 0) ? null : '$' + n.toLocaleString('en-US', {maximumFractionDigits:0});
const fmtDate = s => {
  if (!s) return '';
  try {
    const d = new Date(s.includes('T') ? s : s+'Z');
    return d.toLocaleDateString('en-US',{month:'short',day:'numeric'}) + ' ' + d.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit'});
  } catch(e) { return s; }
};
const timeAgo = s => {
  if (!s) return '';
  try {
    const d = new Date(s.includes('T') ? s : s+'Z');
    const diff = Date.now() - d.getTime();
    const mins = Math.floor(diff/60000);
    if (mins < 60) return mins + 'm ago';
    const hrs = Math.floor(mins/60);
    if (hrs < 24) return hrs + 'h ago';
    const days = Math.floor(hrs/24);
    if (days < 30) return days + 'd ago';
    return Math.floor(days/30) + 'mo ago';
  } catch(e) { return ''; }
};
const trunc = (s,n) => s && s.length > n ? s.substring(0,n)+'\u2026' : (s||'');
const initials = name => {
  if(!name) return '?';
  const p = name.trim().split(/\s+/);
  return p.length > 1 ? (p[0][0]+p[p.length-1][0]).toUpperCase() : name[0].toUpperCase();
};
const hashStr = s => { let h=0; for(let i=0;i<(s||'').length;i++){h=((h<<5)-h)+s.charCodeAt(i);h=h&h;} return h; };
const gradients = [
  'linear-gradient(135deg,#6366f1,#8b5cf6)','linear-gradient(135deg,#10b981,#06b6d4)',
  'linear-gradient(135deg,#f59e0b,#f97316)','linear-gradient(135deg,#ec4899,#f43f5e)',
  'linear-gradient(135deg,#3b82f6,#6366f1)','linear-gradient(135deg,#8b5cf6,#ec4899)',
];
const escHtml = s => (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

function openLightbox(url) {
  event.stopPropagation();
  $('#lightboxImg').src = url;
  $('#lightbox').classList.add('open');
}

/* ─── Skeleton Loader ─── */
function skeletons(n) {
  let h = '';
  for (let i = 0; i < n; i++) {
    h += '<div class="skeleton-card"><div class="skeleton-img"></div><div class="skeleton-body"><div class="skeleton-line w40"></div><div class="skeleton-line w80"></div><div class="skeleton-line w60"></div></div></div>';
  }
  return h;
}

/* ─── State ─── */
let stats = null;
let currentSection = 'buy';

const buyState = { items:[], offset:0, total:0, loading:false, done:false, ptype:'', filters:{zone:'',min_price:'',max_price:'',bedrooms:'',sort:'newest',search:''} };
const rentState = { items:[], offset:0, total:0, loading:false, done:false, rtype:'', filters:{zone:'',min_price:'',max_price:'',bedrooms:'',sort:'newest',search:''} };
const agentsState = { items:[], offset:0, total:0, loading:false, done:false };
const reviewState = { items:[], offset:0, total:0, loading:false, done:false };
const regionsState = { items:[], offset:0, total:0, loading:false, done:false };

/* ─── Navigation ─── */
function switchSection(name) {
  currentSection = name;
  $$('.nav-link').forEach(l => l.classList.toggle('active', l.dataset.section === name));
  $('#adminBtn').classList.toggle('active', name === 'admin');
  $$('.section').forEach(s => s.classList.toggle('active', s.id === 'sec-'+name));

  // Lazy-load section data
  if (name === 'buy' && buyState.items.length === 0) initBuy();
  if (name === 'rent' && rentState.items.length === 0) initRent();
  if (name === 'developments' && !$('#devGrid').innerHTML) loadDevelopments();
  if (name === 'market' && !$('#marketCharts').innerHTML) loadMarket();
  if (name === 'agents' && agentsState.items.length === 0) loadAgentsPage();
  if (name === 'admin') {
    if (!$('#scrapeLog').innerHTML) loadLog();
  }
}

$$('.nav-link').forEach(btn => btn.addEventListener('click', () => switchSection(btn.dataset.section)));

/* ─── Admin sub-tabs ─── */
$$('.admin-tab').forEach(tab => tab.addEventListener('click', () => {
  $$('.admin-tab').forEach(t => t.classList.toggle('active', t === tab));
  $$('.admin-content').forEach(c => c.classList.toggle('active', c.id === 'atab-'+tab.dataset.atab));
  if (tab.dataset.atab === 'log' && !$('#scrapeLog').innerHTML) loadLog();
  if (tab.dataset.atab === 'groups' && !$('#groupsGrid').innerHTML) loadGroups();
  if (tab.dataset.atab === 'review' && reviewState.items.length === 0) loadReviewPage();
  if (tab.dataset.atab === 'regions' && regionsState.items.length === 0) loadRegionsPage();
}));

/* ─── Card Rendering ─── */
function renderCard(l, opts) {
  opts = opts || {};
  const imgs = l.post_images || l.prop_images || [];
  const price = fmtP(l.price_usd);
  const agent = l.agent_name_full || l.author_name || 'Unknown';
  const ini = initials(agent);
  const grad = gradients[Math.abs(hashStr(agent)) % gradients.length];
  const zone = l.neighborhood || l.community || l.prop_zone || '';
  const rawText = escHtml(l.raw_text || '');
  const postUrl = l.permalink || (l.group_id ? 'https://www.facebook.com/groups/' + l.group_id + '/' : '');
  const agentPhones = Array.isArray(l.agent_phones) ? l.agent_phones.filter(Boolean) : [];
  const agentWa = Array.isArray(l.agent_whatsapp) ? l.agent_whatsapp.filter(Boolean) : [];
  const cardId = 'card-' + (l.post_id || Math.random().toString(36).substr(2,8));
  const isRental = opts.isRental || false;

  // Gallery
  var gallery = '';
  var totalImgs = imgs.length;
  if (totalImgs >= 3) {
    gallery = '<div class="card-gallery g3">'
      + '<img src="' + imgs[0] + '" loading="lazy" onerror="this.style.display=\'none\'">'
      + '<img src="' + imgs[1] + '" loading="lazy" onerror="this.style.display=\'none\'">'
      + '<img src="' + imgs[2] + '" loading="lazy" onerror="this.style.display=\'none\'">'
      + (totalImgs > 3 ? '<div class="photo-count">+' + (totalImgs-3) + ' photos</div>' : '')
      + '</div>';
  } else if (totalImgs === 2) {
    gallery = '<div class="card-gallery g2">'
      + '<img src="' + imgs[0] + '" loading="lazy" onerror="this.style.display=\'none\'">'
      + '<img src="' + imgs[1] + '" loading="lazy" onerror="this.style.display=\'none\'">'
      + '</div>';
  } else if (totalImgs === 1) {
    gallery = '<div class="card-gallery g1">'
      + '<img src="' + imgs[0] + '" loading="lazy" onerror="this.parentElement.outerHTML=\'<div class=card-placeholder>&#127968;</div>\'">'
      + '</div>';
  } else {
    gallery = '<div class="card-placeholder">&#127968;</div>';
  }

  // Badges
  var badges = '';
  if (l.listing_type) {
    var lt = (l.listing_type||'').toLowerCase();
    if (lt.indexOf('sale') >= 0 || lt.indexOf('venta') >= 0) badges += '<span class="badge badge-green">Sale</span>';
    else if (lt.indexOf('rent') >= 0 || lt.indexOf('alquiler') >= 0) badges += '<span class="badge badge-orange">Rent</span>';
    else if (lt.indexOf('short') >= 0 || lt.indexOf('airbnb') >= 0) badges += '<span class="badge badge-yellow">Short-Term</span>';
    else badges += '<span class="badge badge-blue">' + escHtml(l.listing_type) + '</span>';
  }
  if (l.property_type) badges += '<span class="badge badge-purple">' + escHtml(l.property_type) + '</span>';
  if (l.furnished) badges += '<span class="badge badge-green">' + escHtml(l.furnished) + '</span>';

  // Specs
  var specs = [];
  if (l.bedrooms) specs.push(l.bedrooms + ' bed');
  if (l.bathrooms) specs.push(l.bathrooms + ' bath');
  if (l.sqm) specs.push(l.sqm + ' m\u00b2');
  var specsHtml = specs.length ? '<div class="card-specs">' + specs.map(function(s){return '<span>'+s+'</span>';}).join('<span class="sep">|</span>') + '</div>' : '';

  // Contact buttons
  var contacts = '';
  if (agentWa.length) contacts += '<a class="wa" href="https://wa.me/' + agentWa[0].replace(/[^0-9]/g,'') + '" target="_blank" onclick="event.stopPropagation()">WhatsApp</a>';
  if (agentPhones.length) contacts += '<a class="call" href="tel:' + agentPhones[0] + '" onclick="event.stopPropagation()">Call</a>';
  if (postUrl) contacts += '<a class="fb" href="' + postUrl + '" target="_blank" onclick="event.stopPropagation()">FB</a>';

  // Price per sqm
  var priceSqm = '';
  if (l.price_usd > 0 && l.sqm > 0 && !isRental) {
    priceSqm = '<span style="font-size:12px;color:var(--text3);margin-left:8px">($' + Math.round(l.price_usd/l.sqm).toLocaleString() + '/m\u00b2)</span>';
  }

  // Expanded content
  var expandImgs = '';
  if (imgs.length > 0) {
    expandImgs = '<div class="expand-gallery">' + imgs.map(function(u){return '<img src="'+u+'" loading="lazy" onclick="openLightbox(\''+u.replace(/'/g,"\\'")+'\')" onerror="this.style.display=\'none\'">';}).join('') + '</div>';
  }

  var expandMeta = '';
  if (postUrl) expandMeta += '<span><a href="' + postUrl + '" target="_blank" onclick="event.stopPropagation()">View original FB post</a></span>';
  if (l.agent_fb_url) expandMeta += '<span><a href="' + l.agent_fb_url + '" target="_blank" onclick="event.stopPropagation()">Agent profile</a></span>';
  if (l.confidence) expandMeta += '<span>Confidence: ' + Math.round(l.confidence*100) + '%</span>';
  if (l.group_name) expandMeta += '<span>Group: ' + escHtml(l.group_name) + '</span>';

  return '<div class="card" id="' + cardId + '" onclick="toggleCard(\'' + cardId + '\')">'
    + gallery
    + '<div class="card-body">'
    + '<div class="card-price-row">'
    + '<div class="card-price ' + (price?'':'no-price') + '">'
    + (price || 'Contact for price') + (isRental && price ? '<span class="period"> /mo</span>' : '') + priceSqm
    + '</div>'
    + '<div class="card-badges">' + badges + '</div>'
    + '</div>'
    + (zone ? '<div class="card-location"><svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>' + escHtml(zone) + '</div>' : '')
    + specsHtml
    + (rawText ? '<div class="card-desc">' + rawText.substring(0, 200) + '</div>' : '')
    + '</div>'
    + '<div class="card-footer">'
    + '<div class="card-agent">'
    + '<div class="card-agent-avatar" style="background:' + grad + '">' + ini + '</div>'
    + '<div style="min-width:0">'
    + '<div class="card-agent-name">' + escHtml(trunc(agent,28)) + '</div>'
    + '<div class="card-agent-time">' + timeAgo(l.captured_at) + '</div>'
    + '</div>'
    + '</div>'
    + '<div class="card-contact">' + contacts + '</div>'
    + '</div>'
    + '<div class="card-expand"><div class="card-expand-inner">'
    + expandImgs
    + '<div class="expand-text">' + rawText + '</div>'
    + '<div class="expand-meta">' + expandMeta + '</div>'
    + '</div></div>'
    + '</div>';
}

function toggleCard(id) {
  var card = document.getElementById(id);
  if (!card) return;
  if (event && event.target.closest('a')) return;
  card.classList.toggle('expanded');
}

/* ─── BUY SECTION ─── */
async function initBuy() {
  if (!stats) stats = await (await fetch('/api/stats')).json();
  renderBuyStats();
  buildBuyFilters();
  loadBuyPage();
  setupInfiniteScroll('buySentinel', 'buySpinner', buyState, loadBuyPage);
}

function renderBuyStats() {
  var s = stats;
  $('#buyStats').innerHTML = ''
    + '<div class="stat-card"><div class="stat-label">Listings</div><div class="stat-value">' + fmt(s.total_listings) + '</div><div class="stat-sub">verified properties</div></div>'
    + '<div class="stat-card"><div class="stat-label">With Price</div><div class="stat-value">' + fmt(s.with_price) + '</div><div class="stat-sub">of ' + fmt(s.total_posts) + ' scraped</div></div>'
    + '<div class="stat-card"><div class="stat-label">Agents</div><div class="stat-value">' + fmt(s.agents) + '</div><div class="stat-sub">' + s.pro_agents + ' professional</div></div>'
    + '<div class="stat-card"><div class="stat-label">Zones</div><div class="stat-value">' + Object.keys(s.zones).length + '</div><div class="stat-sub">' + s.groups + ' groups monitored</div></div>';
}

function buildBuyFilters() {
  var zones = Object.keys(stats.zones).sort();
  var f = buyState.filters;
  $('#buyFilters').innerHTML = ''
    + '<div class="fg"><label>Search</label><input type="text" id="buySearch" placeholder="Keywords..." value="' + f.search + '"></div>'
    + '<div class="fg"><label>Location</label><select id="buyZone"><option value="">All Zones</option>' + zones.map(function(z){return '<option value="'+z+'" '+(f.zone===z?'selected':'')+'>'+z+'</option>';}).join('') + '</select></div>'
    + '<div class="fg"><label>Min $</label><input type="number" id="buyMin" placeholder="0" value="' + f.min_price + '" style="min-width:100px"></div>'
    + '<div class="fg"><label>Max $</label><input type="number" id="buyMax" placeholder="Any" value="' + f.max_price + '" style="min-width:100px"></div>'
    + '<div class="fg"><label>Beds</label><select id="buyBeds"><option value="">Any</option>' + [1,2,3,4,5,6].map(function(b){return '<option value="'+b+'" '+(f.bedrooms==b?'selected':'')+'>'+b+'+</option>';}).join('') + '</select></div>'
    + '<div class="fg"><label>Sort</label><select id="buySort">'
    + '<option value="newest" '+(f.sort==='newest'?'selected':'')+'>Newest</option>'
    + '<option value="price_high" '+(f.sort==='price_high'?'selected':'')+'>Price High</option>'
    + '<option value="price_low" '+(f.sort==='price_low'?'selected':'')+'>Price Low</option>'
    + '<option value="confidence" '+(f.sort==='confidence'?'selected':'')+'>Best Match</option>'
    + '</select></div>'
    + '<div class="fg"><label>&nbsp;</label><button class="btn btn-primary" onclick="applyBuyFilters()">Search</button></div>'
    + '<div class="fg"><label>&nbsp;</label><button class="btn btn-ghost" onclick="clearBuyFilters()">Clear</button></div>';
  $('#buySearch').addEventListener('keydown', function(e){ if(e.key==='Enter') applyBuyFilters(); });
}

function applyBuyFilters() {
  buyState.filters = {
    search: $('#buySearch').value, zone: $('#buyZone').value,
    min_price: $('#buyMin').value, max_price: $('#buyMax').value,
    bedrooms: $('#buyBeds').value, sort: $('#buySort').value,
  };
  resetState(buyState);
  $('#buyGrid').innerHTML = skeletons(6);
  loadBuyPage();
}

function clearBuyFilters() {
  buyState.filters = {zone:'',min_price:'',max_price:'',bedrooms:'',sort:'newest',search:''};
  buyState.ptype = '';
  $$('#buyPills .pill').forEach(function(p){ p.classList.toggle('active', p.dataset.ptype === ''); });
  resetState(buyState);
  buildBuyFilters();
  $('#buyGrid').innerHTML = skeletons(6);
  loadBuyPage();
}

// Buy sub-pills
$$('#buyPills .pill').forEach(function(pill) {
  pill.addEventListener('click', function() {
    $$('#buyPills .pill').forEach(function(p){ p.classList.remove('active'); });
    pill.classList.add('active');
    buyState.ptype = pill.dataset.ptype;
    resetState(buyState);
    $('#buyGrid').innerHTML = skeletons(6);
    loadBuyPage();
  });
});

async function loadBuyPage() {
  if (buyState.loading || buyState.done) return;
  buyState.loading = true;
  $('#buySpinner').style.display = 'flex';

  var f = buyState.filters;
  var url = '/api/listings?limit=24&offset=' + buyState.offset + '&sort=' + f.sort + '&pc_only=true&is_listing=true&listing_type=sale&exclude_ptype=land,commercial';
  if (buyState.ptype) url += '&property_type=' + encodeURIComponent(buyState.ptype);
  if (f.zone) url += '&zone=' + encodeURIComponent(f.zone);
  if (f.min_price) url += '&min_price=' + f.min_price;
  if (f.max_price) url += '&max_price=' + f.max_price;
  if (f.bedrooms) url += '&bedrooms=' + f.bedrooms;
  if (f.search) url += '&search=' + encodeURIComponent(f.search);

  try {
    var data = await (await fetch(url)).json();
    buyState.total = data.total;
    buyState.offset += data.listings.length;
    if (data.listings.length < 24) buyState.done = true;

    var html = '';
    for (var i = 0; i < data.listings.length; i++) {
      html += renderCard(data.listings[i]);
      buyState.items.push(data.listings[i]);
    }

    if (buyState.offset <= 24) {
      if (!data.listings.length) {
        $('#buyGrid').innerHTML = '<div style="text-align:center;padding:60px;color:var(--text3);grid-column:1/-1">No properties match your criteria</div>';
      } else {
        $('#buyGrid').innerHTML = html;
      }
    } else {
      $('#buyGrid').insertAdjacentHTML('beforeend', html);
    }

    $('#buyResultsInfo').textContent = data.total.toLocaleString() + ' propert' + (data.total!==1?'ies':'y') + ' found';
    $('#buyEndMsg').style.display = (buyState.done && buyState.items.length > 0) ? 'block' : 'none';
  } catch(e) { console.error('Buy load error:', e); }

  buyState.loading = false;
  $('#buySpinner').style.display = 'none';
}

/* ─── RENT SECTION ─── */
async function initRent() {
  if (!stats) stats = await (await fetch('/api/stats')).json();
  renderRentStats();
  buildRentFilters();
  loadRentPage();
  setupInfiniteScroll('rentSentinel', 'rentSpinner', rentState, loadRentPage);
}

function renderRentStats() {
  var lt = stats.listing_types;
  var rentCount = (lt['rent']||0) + (lt['rental']||0) + (lt['alquiler']||0);
  var shortCount = (lt['short_term_rent']||0) + (lt['short-term']||0) + (lt['airbnb']||0) + (lt['nightly']||0);
  $('#rentStats').innerHTML = ''
    + '<div class="stat-card"><div class="stat-label">Long-Term Rentals</div><div class="stat-value">' + fmt(rentCount) + '</div><div class="stat-sub">monthly lease</div></div>'
    + '<div class="stat-card"><div class="stat-label">Short-Term</div><div class="stat-value">' + fmt(shortCount) + '</div><div class="stat-sub">vacation / Airbnb</div></div>'
    + '<div class="stat-card"><div class="stat-label">Total Agents</div><div class="stat-value">' + fmt(stats.agents) + '</div><div class="stat-sub">active in rental market</div></div>';
}

function buildRentFilters() {
  var zones = Object.keys(stats.zones).sort();
  var f = rentState.filters;
  $('#rentFilters').innerHTML = ''
    + '<div class="fg"><label>Search</label><input type="text" id="rentSearch" placeholder="Keywords..." value="' + f.search + '"></div>'
    + '<div class="fg"><label>Location</label><select id="rentZone"><option value="">All Zones</option>' + zones.map(function(z){return '<option value="'+z+'" '+(f.zone===z?'selected':'')+'>'+z+'</option>';}).join('') + '</select></div>'
    + '<div class="fg"><label>Min $</label><input type="number" id="rentMin" placeholder="0" value="' + f.min_price + '" style="min-width:100px"></div>'
    + '<div class="fg"><label>Max $</label><input type="number" id="rentMax" placeholder="Any" value="' + f.max_price + '" style="min-width:100px"></div>'
    + '<div class="fg"><label>Beds</label><select id="rentBeds"><option value="">Any</option>' + [1,2,3,4,5,6].map(function(b){return '<option value="'+b+'" '+(f.bedrooms==b?'selected':'')+'>'+b+'+</option>';}).join('') + '</select></div>'
    + '<div class="fg"><label>Sort</label><select id="rentSort">'
    + '<option value="newest" '+(f.sort==='newest'?'selected':'')+'>Newest</option>'
    + '<option value="price_high" '+(f.sort==='price_high'?'selected':'')+'>Price High</option>'
    + '<option value="price_low" '+(f.sort==='price_low'?'selected':'')+'>Price Low</option>'
    + '</select></div>'
    + '<div class="fg"><label>&nbsp;</label><button class="btn btn-primary" onclick="applyRentFilters()">Search</button></div>'
    + '<div class="fg"><label>&nbsp;</label><button class="btn btn-ghost" onclick="clearRentFilters()">Clear</button></div>';
  $('#rentSearch').addEventListener('keydown', function(e){ if(e.key==='Enter') applyRentFilters(); });
}

function applyRentFilters() {
  rentState.filters = {
    search: $('#rentSearch').value, zone: $('#rentZone').value,
    min_price: $('#rentMin').value, max_price: $('#rentMax').value,
    bedrooms: $('#rentBeds').value, sort: $('#rentSort').value,
  };
  resetState(rentState);
  $('#rentGrid').innerHTML = skeletons(6);
  loadRentPage();
}

function clearRentFilters() {
  rentState.filters = {zone:'',min_price:'',max_price:'',bedrooms:'',sort:'newest',search:''};
  rentState.rtype = '';
  $$('#rentPills .pill').forEach(function(p){ p.classList.toggle('active', p.dataset.rtype === ''); });
  resetState(rentState);
  buildRentFilters();
  $('#rentGrid').innerHTML = skeletons(6);
  loadRentPage();
}

// Rent sub-pills
$$('#rentPills .pill').forEach(function(pill) {
  pill.addEventListener('click', function() {
    $$('#rentPills .pill').forEach(function(p){ p.classList.remove('active'); });
    pill.classList.add('active');
    rentState.rtype = pill.dataset.rtype;
    resetState(rentState);
    $('#rentGrid').innerHTML = skeletons(6);
    loadRentPage();
  });
});

async function loadRentPage() {
  if (rentState.loading || rentState.done) return;
  rentState.loading = true;
  $('#rentSpinner').style.display = 'flex';

  var f = rentState.filters;
  var ltype = rentState.rtype || 'rent';
  var url = '/api/listings?limit=24&offset=' + rentState.offset + '&sort=' + f.sort + '&pc_only=true&is_listing=true&listing_type=' + ltype + '&exclude_ptype=land,commercial';
  if (f.zone) url += '&zone=' + encodeURIComponent(f.zone);
  if (f.min_price) url += '&min_price=' + f.min_price;
  if (f.max_price) url += '&max_price=' + f.max_price;
  if (f.bedrooms) url += '&bedrooms=' + f.bedrooms;
  if (f.search) url += '&search=' + encodeURIComponent(f.search);

  try {
    var data = await (await fetch(url)).json();
    rentState.total = data.total;
    rentState.offset += data.listings.length;
    if (data.listings.length < 24) rentState.done = true;

    var html = '';
    for (var i = 0; i < data.listings.length; i++) {
      html += renderCard(data.listings[i], {isRental: true});
      rentState.items.push(data.listings[i]);
    }

    if (rentState.offset <= 24) {
      if (!data.listings.length) {
        $('#rentGrid').innerHTML = '<div style="text-align:center;padding:60px;color:var(--text3);grid-column:1/-1">No rentals match your criteria</div>';
      } else {
        $('#rentGrid').innerHTML = html;
      }
    } else {
      $('#rentGrid').insertAdjacentHTML('beforeend', html);
    }

    $('#rentResultsInfo').textContent = data.total.toLocaleString() + ' rental' + (data.total!==1?'s':'') + ' found';
    $('#rentEndMsg').style.display = (rentState.done && rentState.items.length > 0) ? 'block' : 'none';
  } catch(e) { console.error('Rent load error:', e); }

  rentState.loading = false;
  $('#rentSpinner').style.display = 'none';
}

/* ─── DEVELOPMENTS SECTION ─── */
async function loadDevelopments() {
  var data = await (await fetch('/api/constructoras')).json();
  var cs = data.constructoras;

  var active = cs.filter(function(c){ return c.status && c.status.toLowerCase().indexOf('active') >= 0; }).length;
  var masterDev = cs.filter(function(c){ return c.type === 'Master Developer'; }).length;
  var zoneSet = {};
  cs.forEach(function(c){ (c.zones||[]).forEach(function(z){ zoneSet[z]=1; }); });
  var zoneCount = Object.keys(zoneSet).length;

  $('#devStats').innerHTML = ''
    + '<div class="stat-card"><div class="stat-label">Developments</div><div class="stat-value">' + cs.length + '</div><div class="stat-sub">tracked projects</div></div>'
    + '<div class="stat-card"><div class="stat-label">Active</div><div class="stat-value">' + active + '</div><div class="stat-sub">building / selling</div></div>'
    + '<div class="stat-card"><div class="stat-label">Master Developers</div><div class="stat-value">' + masterDev + '</div><div class="stat-sub">large-scale</div></div>'
    + '<div class="stat-card"><div class="stat-label">Zones</div><div class="stat-value">' + zoneCount + '</div><div class="stat-sub">across PC region</div></div>';

  var typeColors = {
    'Master Developer': 'badge-orange', 'Developer': 'badge-purple',
    'Constructor': 'badge-blue', 'Resort Developer': 'badge-green',
    'Multiple Developers': 'badge-yellow',
  };

  var html = '';
  for (var i = 0; i < cs.length; i++) {
    var c = cs[i];
    var grad = gradients[Math.abs(hashStr(c.name)) % gradients.length];
    var ini = c.name.charAt(0).toUpperCase();
    var badge = typeColors[c.type] || 'badge-purple';
    var projects = (c.projects || []).map(function(p){
      return '<span style="display:inline-block;padding:2px 8px;margin:2px;border-radius:6px;background:var(--surface2);font-size:11px;color:var(--text2)">' + escHtml(p) + '</span>';
    }).join('');
    var zonesList = (c.zones || []).join(', ');

    var links = '';
    if (c.website) links += '<a class="fb" href="' + c.website + '" target="_blank" onclick="event.stopPropagation()">Website</a>';
    if (c.facebook) links += '<a class="fb" href="' + c.facebook + '" target="_blank" onclick="event.stopPropagation()">Facebook</a>';

    var contact = '';
    if (c.phone) contact += '<div style="margin-top:8px"><a href="tel:' + c.phone + '" style="color:var(--green);font-weight:600;font-size:12px">' + c.phone + '</a></div>';
    if (c.instagram) contact += '<div style="margin-top:4px;font-size:12px;color:var(--accent2)">' + c.instagram + '</div>';

    html += '<div class="card" ' + (c.website ? 'style="cursor:pointer" onclick="window.open(\'' + c.website + '\',\'_blank\')"' : 'style="cursor:default"') + '>'
      + '<div class="card-body" style="padding-top:20px">'
      + '<div style="display:flex;align-items:center;gap:14px;margin-bottom:14px">'
      + '<div class="agent-avatar" style="background:' + grad + ';width:44px;height:44px;border-radius:12px;font-size:20px">' + ini + '</div>'
      + '<div style="flex:1">'
      + '<div style="font-size:17px;font-weight:800;letter-spacing:-0.3px">' + escHtml(c.name) + '</div>'
      + '<div style="display:flex;gap:6px;margin-top:5px">'
      + '<span class="badge ' + badge + '">' + c.type + '</span>'
      + '<span class="badge ' + (c.status && c.status.toLowerCase().indexOf('active')>=0 ? 'badge-green' : 'badge-yellow') + '">' + (c.status || 'Unknown') + '</span>'
      + '</div></div></div>'
      + '<div style="font-size:13px;color:var(--text2);line-height:1.6;margin-bottom:12px">' + escHtml(c.description || '') + '</div>'
      + '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:10px">'
      + '<div style="font-size:12px;color:var(--text2);display:flex;align-items:center;gap:5px"><svg viewBox="0 0 24 24" style="width:13px;height:13px;fill:var(--text3)"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>' + (zonesList || 'Punta Cana') + '</div>'
      + (c.price_range ? '<div style="font-size:12px;color:var(--green);font-weight:700">' + c.price_range + '</div>' : '')
      + '</div>'
      + '<div style="margin-bottom:10px">' + projects + '</div>'
      + contact
      + '</div>'
      + '<div class="card-footer">'
      + '<div style="font-size:12px;color:var(--text3)">' + (c.projects||[]).length + ' project' + ((c.projects||[]).length!==1?'s':'') + '</div>'
      + '<div class="card-contact">' + links + '</div>'
      + '</div></div>';
  }

  $('#devGrid').innerHTML = html || '<div style="color:var(--text3);padding:40px;text-align:center;grid-column:1/-1">No developments found</div>';
}

/* ─── MARKET SECTION ─── */
async function loadMarket() {
  if (!stats) stats = await (await fetch('/api/stats')).json();
  var s = stats;

  $('#marketStats').innerHTML = ''
    + '<div class="stat-card"><div class="stat-label">Total Scraped</div><div class="stat-value">' + fmt(s.total_posts) + '</div><div class="stat-sub">FB posts processed</div></div>'
    + '<div class="stat-card"><div class="stat-label">Verified Listings</div><div class="stat-value">' + fmt(s.total_listings) + '</div><div class="stat-sub">real properties</div></div>'
    + '<div class="stat-card"><div class="stat-label">Properties DB</div><div class="stat-value">' + fmt(s.properties) + '</div><div class="stat-sub">unique properties</div></div>'
    + '<div class="stat-card"><div class="stat-label">Review Queue</div><div class="stat-value">' + fmt(s.needs_review) + '</div><div class="stat-sub">needs attention</div></div>';

  var html = '';

  // Price by zone
  var pz = Object.entries(s.avg_price_by_zone).sort(function(a,b){return b[1].avg-a[1].avg;}).slice(0,10);
  if (pz.length) {
    var mx = Math.max.apply(null, pz.map(function(z){return z[1].avg;}));
    html += '<div class="chart-card"><h3>Average Price by Zone</h3>';
    pz.forEach(function(item) {
      var z = item[0], d = item[1];
      html += '<div class="bar-row"><div class="bar-label">' + z + '</div><div class="bar-track"><div class="bar-fill" style="width:' + (d.avg/mx*100).toFixed(0) + '%;background:var(--gradient1)">' + fmtP(d.avg) + '</div></div><div class="bar-value">' + d.count + ' listings</div></div>';
    });
    html += '</div>';
  }

  // Zones distribution
  var zones = Object.entries(s.zones).sort(function(a,b){return b[1]-a[1];}).slice(0,10);
  if (zones.length) {
    var mx2 = Math.max.apply(null, zones.map(function(z){return z[1];}));
    html += '<div class="chart-card"><h3>Posts by Zone</h3>';
    zones.forEach(function(item) {
      html += '<div class="bar-row"><div class="bar-label">' + item[0] + '</div><div class="bar-track"><div class="bar-fill" style="width:' + (item[1]/mx2*100).toFixed(0) + '%;background:var(--gradient2)">' + item[1] + '</div></div><div class="bar-value"></div></div>';
    });
    html += '</div>';
  }

  // Property types
  var types = Object.entries(s.property_types).sort(function(a,b){return b[1]-a[1];});
  if (types.length) {
    var mx3 = Math.max.apply(null, types.map(function(t){return t[1];}));
    var colors = ['var(--gradient1)','var(--gradient2)','var(--gradient3)','linear-gradient(135deg,#ec4899,#f43f5e)','linear-gradient(135deg,#3b82f6,#6366f1)'];
    html += '<div class="chart-card"><h3>Property Types</h3>';
    types.forEach(function(item, idx) {
      html += '<div class="bar-row"><div class="bar-label">' + item[0] + '</div><div class="bar-track"><div class="bar-fill" style="width:' + (item[1]/mx3*100).toFixed(0) + '%;background:' + colors[idx%colors.length] + '">' + item[1] + '</div></div><div class="bar-value"></div></div>';
    });
    html += '</div>';
  }

  // Groups
  if (s.group_stats.length) {
    html += '<div class="chart-card"><h3>Groups Monitored</h3>';
    s.group_stats.forEach(function(g) {
      html += '<div style="display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border)">'
        + '<div><div style="font-weight:600;font-size:13px">' + (g.group_name||'?') + '</div><div style="font-size:11px;color:var(--text3)">Last: ' + fmtDate(g.last_scraped) + '</div></div>'
        + '<div style="text-align:right"><div style="font-weight:700;font-size:13px">' + (g.valid_listings||0) + ' listings</div><div style="font-size:11px;color:var(--green)">' + (g.with_price||0) + ' priced</div></div>'
        + '</div>';
    });
    html += '</div>';
  }

  $('#marketCharts').innerHTML = html;
}

/* ─── AGENTS SECTION ─── */
async function loadAgentsPage() {
  if (agentsState.loading || agentsState.done) return;
  agentsState.loading = true;
  $('#agentsSpinner').style.display = 'flex';

  var url = '/api/agents?sort=listings&limit=24&offset=' + agentsState.offset;
  try {
    var data = await (await fetch(url)).json();
    agentsState.total = data.total;
    agentsState.offset += data.agents.length;
    if (data.agents.length < 24) agentsState.done = true;

    var html = '';
    for (var i = 0; i < data.agents.length; i++) {
      var a = data.agents[i];
      var ini = initials(a.name);
      var grad = gradients[Math.abs(hashStr(a.name)) % gradients.length];
      var zones = Array.isArray(a.primary_zones) ? a.primary_zones.join(', ') : '';
      var phones = Array.isArray(a.phones) ? a.phones.filter(Boolean) : [];
      var wa = Array.isArray(a.whatsapp) ? a.whatsapp.filter(Boolean) : [];
      var fbLink = a.fb_profile_url ? '<a href="' + a.fb_profile_url + '" target="_blank">' + escHtml(a.name||'?') + '</a>' : escHtml(a.name||'?');

      var avatarHtml = a.profile_pic_url
        ? '<div class="agent-avatar" style="background:' + grad + '"><img src="' + a.profile_pic_url + '" onerror="this.remove();this.parentElement.textContent=\'' + ini + '\'"></div>'
        : '<div class="agent-avatar" style="background:' + grad + '">' + ini + '</div>';

      var phoneLines = '';
      if (phones.length) phoneLines += '<div style="margin-top:6px"><a href="tel:' + phones[0] + '" style="color:var(--green);font-weight:600;font-size:12px">' + phones.join(', ') + '</a></div>';
      if (wa.length) phoneLines += '<div style="margin-top:4px"><a href="https://wa.me/' + wa[0].replace(/[^0-9]/g,'') + '" target="_blank" style="color:#25d366;font-weight:600;font-size:12px">WA: ' + wa.join(', ') + '</a></div>';

      html += '<div class="agent-card">'
        + avatarHtml
        + '<div class="agent-info">'
        + '<div class="agent-name">' + fbLink + ' ' + (a.is_agent ? '<span class="badge badge-green">PRO</span>' : '') + '</div>'
        + '<div class="agent-meta">'
        + '<span><strong>' + (a.total_listings||0) + '</strong> listings</span>'
        + '<span><strong>' + (a.groups_active||0) + '</strong> groups</span>'
        + (zones ? '<span>' + trunc(zones,30) + '</span>' : '')
        + '</div>'
        + phoneLines
        + '</div></div>';
      agentsState.items.push(a);
    }

    if (agentsState.offset <= 24) {
      if (!data.agents.length) {
        $('#agentsGrid').innerHTML = '<div style="color:var(--text3);padding:40px;text-align:center;grid-column:1/-1">No agents found</div>';
      } else {
        $('#agentsGrid').innerHTML = html;
      }
    } else {
      $('#agentsGrid').insertAdjacentHTML('beforeend', html);
    }

    $('#agentsResultsInfo').textContent = data.total + ' agent' + (data.total!==1?'s':'') + ' tracked';
    $('#agentsEndMsg').style.display = (agentsState.done && agentsState.items.length > 0) ? 'block' : 'none';
  } catch(e) { console.error('Agents load error:', e); }

  agentsState.loading = false;
  $('#agentsSpinner').style.display = 'none';
}

/* ─── ADMIN: Scrape Log ─── */
async function loadLog() {
  if (!stats) stats = await (await fetch('/api/stats')).json();
  var html = '<h3 style="font-size:12px;text-transform:uppercase;letter-spacing:1.2px;color:var(--text2);font-weight:700;margin-bottom:16px">Recent Scrape Runs</h3>';
  html += '<div class="table-wrap"><table><thead><tr><th>Time</th><th>Group</th><th>Status</th><th>New</th><th>Total</th></tr></thead><tbody>';
  stats.scrape_history.forEach(function(e) {
    var badge = e.status==='success' ? '<span class="badge badge-green">OK</span>' : '<span class="badge badge-red">ERR</span>';
    html += '<tr>'
      + '<td style="color:var(--text2);white-space:nowrap">' + fmtDate(e.started_at) + '</td>'
      + '<td style="font-weight:500;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escHtml(e.group_name||'?') + '</td>'
      + '<td>' + badge + '</td>'
      + '<td style="font-weight:700">' + (e.posts_new||0) + '</td>'
      + '<td style="color:var(--text2)">' + (e.posts_captured||0) + '</td>'
      + '</tr>';
  });
  html += '</tbody></table></div>';
  $('#scrapeLog').innerHTML = html;
}

/* ─── ADMIN: Groups ─── */
async function loadGroups() {
  var data = await (await fetch('/api/groups')).json();
  var html = '';
  data.groups.forEach(function(g) {
    var groupUrl = g.group_id ? 'https://www.facebook.com/groups/' + g.group_id + '/' : '';
    var grad = gradients[Math.abs(hashStr(g.group_name||'')) % gradients.length];
    var ini = (g.group_name||'?').charAt(0).toUpperCase();
    var pctPriced = g.total_posts > 0 ? Math.round((g.priced_listings||0)/g.total_posts*100) : 0;

    html += '<div class="agent-card" ' + (groupUrl ? 'style="cursor:pointer" onclick="window.open(\'' + groupUrl + '\',\'_blank\')"' : '') + '>'
      + '<div class="agent-avatar" style="background:' + grad + '">' + ini + '</div>'
      + '<div class="agent-info">'
      + '<div class="agent-name">' + (groupUrl ? '<a href="' + groupUrl + '" target="_blank" onclick="event.stopPropagation()">' + escHtml(g.group_name||'Unknown') + '</a>' : escHtml(g.group_name||'Unknown')) + '</div>'
      + '<div class="agent-meta">'
      + '<span><strong>' + g.total_posts + '</strong> posts</span>'
      + '<span><strong>' + (g.valid_listings||0) + '</strong> listings</span>'
      + '<span style="color:var(--green)"><strong>' + (g.priced_listings||0) + '</strong> priced (' + pctPriced + '%)</span>'
      + '<span><strong>' + (g.unique_agents||0) + '</strong> agents</span>'
      + '</div>'
      + '<div style="margin-top:6px;font-size:11px;color:var(--text3)">First: ' + fmtDate(g.first_scraped) + ' &mdash; Last: ' + fmtDate(g.last_scraped) + '</div>'
      + '</div></div>';
  });
  $('#groupsGrid').innerHTML = html || '<div style="color:var(--text3);padding:40px;text-align:center;grid-column:1/-1">No groups found</div>';
}

/* ─── ADMIN: Review Queue ─── */
async function loadReviewPage() {
  if (reviewState.loading || reviewState.done) return;
  reviewState.loading = true;
  $('#reviewSpinner').style.display = 'flex';

  var url = '/api/listings?limit=24&offset=' + reviewState.offset + '&needs_review=true&sort=newest';
  try {
    var data = await (await fetch(url)).json();
    reviewState.total = data.total;
    reviewState.offset += data.listings.length;
    if (data.listings.length < 24) reviewState.done = true;

    var html = '';
    for (var i = 0; i < data.listings.length; i++) {
      html += renderCard(data.listings[i]);
      reviewState.items.push(data.listings[i]);
    }

    if (reviewState.offset <= 24) {
      $('#reviewGrid').innerHTML = html || '<div style="text-align:center;padding:60px;color:var(--text3);grid-column:1/-1">Review queue empty</div>';
    } else {
      $('#reviewGrid').insertAdjacentHTML('beforeend', html);
    }
    $('#reviewInfo').textContent = data.total + ' listing' + (data.total!==1?'s':'') + ' need review';
  } catch(e) { console.error('Review load error:', e); }

  reviewState.loading = false;
  $('#reviewSpinner').style.display = 'none';
}

/* ─── ADMIN: Other Regions ─── */
async function loadRegionsPage() {
  if (regionsState.loading || regionsState.done) return;
  regionsState.loading = true;
  $('#regionsSpinner').style.display = 'flex';

  var url = '/api/listings?limit=24&offset=' + regionsState.offset + '&non_pc=true&is_listing=true&sort=newest';
  try {
    var data = await (await fetch(url)).json();
    regionsState.total = data.total;
    regionsState.offset += data.listings.length;
    if (data.listings.length < 24) regionsState.done = true;

    var html = '';
    for (var i = 0; i < data.listings.length; i++) {
      html += renderCard(data.listings[i]);
      regionsState.items.push(data.listings[i]);
    }

    if (regionsState.offset <= 24) {
      $('#regionsGrid').innerHTML = html || '<div style="text-align:center;padding:60px;color:var(--text3);grid-column:1/-1">No listings from other regions</div>';
    } else {
      $('#regionsGrid').insertAdjacentHTML('beforeend', html);
    }
    $('#regionsInfo').textContent = data.total + ' listing' + (data.total!==1?'s':'') + ' outside Punta Cana';
  } catch(e) { console.error('Regions load error:', e); }

  regionsState.loading = false;
  $('#regionsSpinner').style.display = 'none';
}

/* ─── Infinite Scroll ─── */
function resetState(state) {
  state.items = [];
  state.offset = 0;
  state.total = 0;
  state.loading = false;
  state.done = false;
}

function setupInfiniteScroll(sentinelId, spinnerId, state, loadFn) {
  var sentinel = document.getElementById(sentinelId);
  if (!sentinel) return;
  var observer = new IntersectionObserver(function(entries) {
    if (entries[0].isIntersecting && !state.loading && !state.done) {
      loadFn();
    }
  }, { rootMargin: '400px' });
  observer.observe(sentinel);
}

/* ─── Init ─── */
async function init() {
  $('#buyGrid').innerHTML = skeletons(6);
  stats = await (await fetch('/api/stats')).json();
  initBuy();
  setupInfiniteScroll('agentsSentinel', 'agentsSpinner', agentsState, loadAgentsPage);
  setupInfiniteScroll('reviewSentinel', 'reviewSpinner', reviewState, loadReviewPage);
  setupInfiniteScroll('regionsSentinel', 'regionsSpinner', regionsState, loadRegionsPage);
}

init();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def dashboard():
    from fastapi.responses import HTMLResponse as HR
    return HR(content=DASHBOARD_HTML, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    })


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8050)
