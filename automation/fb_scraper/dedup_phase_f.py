"""
dedup_phase_f.py — Additional dedup: same agent + same price + same property_type.
Catches agents who spam the same listing across multiple groups with scrambled text.
Run on VPS: python3 /opt/fb_scraper/dedup_phase_f.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "fb_listings.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def pick_best(conn, post_ids):
    """Pick best listing: prefer local images > highest confidence > most recent."""
    import os
    img_dir = "/opt/data/images"
    best_id = None
    best_score = (-1, -1, "")
    for pid in post_ids:
        row = conn.execute(
            "SELECT l.post_id, l.confidence, r.captured_at "
            "FROM listings l JOIN raw_posts r ON l.post_id = r.post_id "
            "WHERE l.post_id = ?", (pid,)
        ).fetchone()
        if not row:
            continue
        # Check local images
        has_local = 1 if os.path.exists(os.path.join(img_dir, pid + "_0.jpg")) else 0
        conf = row["confidence"] or 0
        cap = row["captured_at"] or ""
        score = (has_local, conf, cap)
        if score > best_score:
            best_score = score
            best_id = pid
    return best_id


def phase_f(conn):
    """Same agent + same price + same property_type = duplicate (keeps 1 per combo)."""
    print("=== Phase F: Same agent + price + property_type ===")

    groups = conn.execute(
        "SELECT agent_id, price_usd, property_type, "
        "GROUP_CONCAT(post_id) as post_ids, COUNT(*) as cnt "
        "FROM listings "
        "WHERE agent_id IS NOT NULL AND price_usd IS NOT NULL "
        "AND property_type IS NOT NULL "
        "AND is_spam = 0 AND is_duplicate = 0 "
        "GROUP BY agent_id, CAST(price_usd AS INTEGER), LOWER(property_type) "
        "HAVING cnt > 1"
    ).fetchall()

    total_dupes = 0
    for g in groups:
        post_ids = g["post_ids"].split(",")
        best = pick_best(conn, post_ids)
        if not best:
            continue
        dupes = [pid for pid in post_ids if pid != best]
        for pid in dupes:
            conn.execute(
                "UPDATE listings SET is_duplicate = 1, duplicate_of = ? WHERE post_id = ?",
                (best, pid)
            )
        total_dupes += len(dupes)

    conn.commit()
    print("  Marked %d duplicates across %d groups" % (total_dupes, len(groups)))

    # Show top offenders
    top = conn.execute(
        "SELECT a.name, COUNT(*) as duped "
        "FROM listings l JOIN agents a ON l.agent_id = a.id "
        "WHERE l.is_duplicate = 1 AND l.is_spam = 0 "
        "GROUP BY a.id ORDER BY duped DESC LIMIT 10"
    ).fetchall()
    print("\nTop deduped agents:")
    for r in top:
        print("  %s: %d duplicates hidden" % (r["name"], r["duped"]))

    return total_dupes


def main():
    conn = get_db()

    before = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE is_spam = 0 AND is_duplicate = 0"
    ).fetchone()[0]
    print("Before: %d unique listings" % before)

    f = phase_f(conn)

    after = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE is_spam = 0 AND is_duplicate = 0"
    ).fetchone()[0]
    print("\nAfter: %d unique listings (-%d)" % (after, before - after))

    # Check JMB specifically
    jmb = conn.execute(
        "SELECT COUNT(*) FROM listings l "
        "JOIN agents a ON l.agent_id = a.id "
        "WHERE LOWER(a.name) LIKE '%juan manuel bosch%' "
        "AND l.is_spam = 0 AND l.is_duplicate = 0"
    ).fetchone()[0]
    print("Juan Manuel Bosch: %d unique (was 90)" % jmb)

    conn.close()


if __name__ == "__main__":
    main()
