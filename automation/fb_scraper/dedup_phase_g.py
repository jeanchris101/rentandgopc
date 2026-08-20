"""
dedup_phase_g.py — Fix remaining duplicates:
  G1: Same agent + NULL price + same property_type (keeps 1 per combo)
  G2: Same agent + similar text (first 150 chars normalized), regardless of price
Run on VPS: python3 /opt/fb_scraper/dedup_phase_g.py
"""

import os
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "fb_listings.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def normalize_text(text):
    if not text:
        return ""
    t = text.lower()
    t = re.sub(r'[\+]?[\d\s\-\(\)]{7,15}', '', t)
    t = re.sub(r'https?://\S+', '', t)
    t = re.sub(r'[^\w\s]', '', t, flags=re.UNICODE)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def pick_best(conn, post_ids):
    img_dir = "/opt/data/images"
    best_id = None
    best_score = (-1, -1, "")
    for pid in post_ids:
        row = conn.execute(
            "SELECT l.post_id, l.confidence, l.price_usd, r.captured_at "
            "FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
            "WHERE l.post_id = ?", (pid,)
        ).fetchone()
        if not row:
            continue
        has_local = 1 if os.path.exists(os.path.join(img_dir, pid + "_0.jpg")) else 0
        has_price = 1 if row["price_usd"] else 0
        conf = row["confidence"] or 0
        cap = row["captured_at"] or ""
        score = (has_price, has_local, conf, cap)
        if score > best_score:
            best_score = score
            best_id = pid
    return best_id


def mark_dupes(conn, cluster):
    best = pick_best(conn, cluster)
    if not best:
        return 0
    dupes = [pid for pid in cluster if pid != best]
    for pid in dupes:
        conn.execute(
            "UPDATE listings SET is_duplicate = 1, duplicate_of = ? WHERE post_id = ?",
            (best, pid)
        )
    return len(dupes)


def phase_g1(conn):
    """Same agent + NULL price + same property_type = duplicate."""
    print("=== Phase G1: Same agent + NULL price + same type ===")
    groups = conn.execute(
        "SELECT agent_id, property_type, GROUP_CONCAT(post_id) as pids, COUNT(*) as cnt "
        "FROM listings "
        "WHERE agent_id IS NOT NULL AND price_usd IS NULL "
        "AND is_spam = 0 AND is_duplicate = 0 "
        "GROUP BY agent_id, LOWER(COALESCE(property_type, '')) "
        "HAVING cnt > 1"
    ).fetchall()

    total = 0
    for g in groups:
        post_ids = g["pids"].split(",")
        total += mark_dupes(conn, post_ids)

    conn.commit()
    print("  Marked %d duplicates" % total)
    return total


def phase_g2(conn):
    """Same agent + similar text prefix (first 150 chars normalized)."""
    print("=== Phase G2: Same agent + similar text prefix ===")

    # Get all non-dup, non-spam listings grouped by agent
    agents = conn.execute(
        "SELECT agent_id, COUNT(*) as cnt FROM listings "
        "WHERE agent_id IS NOT NULL AND is_spam = 0 AND is_duplicate = 0 "
        "GROUP BY agent_id HAVING cnt > 1"
    ).fetchall()

    total = 0
    for agent_row in agents:
        agent_id = agent_row["agent_id"]
        posts = conn.execute(
            "SELECT l.post_id, SUBSTR(r.raw_text, 1, 300) as txt "
            "FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
            "WHERE l.agent_id = ? AND l.is_spam = 0 AND l.is_duplicate = 0 "
            "ORDER BY r.captured_at ASC",
            (agent_id,)
        ).fetchall()

        # Group by normalized text prefix (first 150 chars)
        prefix_groups = defaultdict(list)
        for p in posts:
            norm = normalize_text(p["txt"])[:150]
            if len(norm) < 30:
                continue
            prefix_groups[norm].append(p["post_id"])

        for prefix, pids in prefix_groups.items():
            if len(pids) > 1:
                total += mark_dupes(conn, pids)

    conn.commit()
    print("  Marked %d duplicates" % total)
    return total


def main():
    conn = get_db()

    before = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE is_spam = 0 AND is_duplicate = 0"
    ).fetchone()[0]
    print("Before: %d unique listings" % before)

    g1 = phase_g1(conn)
    g2 = phase_g2(conn)

    after = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE is_spam = 0 AND is_duplicate = 0"
    ).fetchone()[0]
    print("")
    print("After: %d unique (-%d)" % (after, before - after))
    print("G1=%d, G2=%d" % (g1, g2))

    # Check specific agents
    for name in ['marino', 'stewdy', 'raul carrillo', 'seller details']:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM listings l JOIN agents a ON l.agent_id = a.id "
            "WHERE LOWER(a.name) LIKE ? AND l.is_spam = 0 AND l.is_duplicate = 0",
            ('%' + name + '%',)
        ).fetchone()
        print("  %s: %d unique" % (name, row["c"]))

    conn.close()


if __name__ == "__main__":
    main()
