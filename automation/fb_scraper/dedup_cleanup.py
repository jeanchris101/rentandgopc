"""
dedup_cleanup.py — One-time script to mark existing duplicate listings.

Phase A: Same agent + same property_id (exact structural dupes)
Phase B: Text similarity for listings WITHOUT property_id (same agent)
Phase C: Cross-agent text similarity (same text, different agent_id)
Phase D: Merge duplicate agent records (same person, multiple FB profiles)

Run on VPS: python3 /opt/fb_scraper/dedup_cleanup.py
"""

import json
import re
import sqlite3
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "fb_listings.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def normalize_text(text: str) -> str:
    """Normalize text for dedup comparison."""
    if not text:
        return ""
    t = text.lower()
    t = re.sub(r'[\+]?[\d\s\-\(\)]{7,15}', '', t)
    t = re.sub(r'https?://\S+', '', t)
    t = re.sub(r'[^\w\s]', '', t, flags=re.UNICODE)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def pick_best(conn, post_ids):
    """Pick the best listing from a group: prefer has images > highest confidence > most recent."""
    best_id = None
    best_score = (-1, -1, "")
    for pid in post_ids:
        row = conn.execute(
            """SELECT l.post_id, l.confidence, r.captured_at, r.local_images, r.image_urls
               FROM listings l JOIN raw_posts r ON l.post_id = r.post_id
               WHERE l.post_id = ?""", (pid,)
        ).fetchone()
        if not row:
            continue
        has_local = 1 if row["local_images"] else 0
        has_images = 1 if row["image_urls"] and row["image_urls"] != "[]" else 0
        img_score = has_local * 2 + has_images
        conf = row["confidence"] or 0
        cap = row["captured_at"] or ""
        score = (img_score, conf, cap)
        if score > best_score:
            best_score = score
            best_id = pid
    return best_id


def phase_a(conn):
    """Same agent + same property_id → keep best, mark rest as duplicates."""
    print("\n=== Phase A: Same agent + same property_id ===")
    groups = conn.execute(
        """SELECT agent_id, property_id, GROUP_CONCAT(post_id) as post_ids, COUNT(*) as cnt
           FROM listings
           WHERE agent_id IS NOT NULL AND property_id IS NOT NULL
             AND is_spam = 0 AND is_duplicate = 0
           GROUP BY agent_id, property_id
           HAVING cnt > 1"""
    ).fetchall()

    total_dupes = 0
    for g in groups:
        post_ids = g["post_ids"].split(",")
        best = pick_best(conn, post_ids)
        dupes = [pid for pid in post_ids if pid != best]
        for pid in dupes:
            conn.execute(
                "UPDATE listings SET is_duplicate = 1, duplicate_of = ? WHERE post_id = ?",
                (best, pid)
            )
        total_dupes += len(dupes)

    conn.commit()
    print(f"  Marked {total_dupes} duplicates across {len(groups)} groups")
    return total_dupes


def phase_b(conn):
    """Text similarity for same agent, no property_id."""
    print("\n=== Phase B: Text similarity (same agent, no property_id) ===")

    # Get agents with multiple no-property listings
    agents = conn.execute(
        """SELECT agent_id, COUNT(*) as cnt
           FROM listings
           WHERE agent_id IS NOT NULL AND property_id IS NULL
             AND is_spam = 0 AND is_duplicate = 0
           GROUP BY agent_id
           HAVING cnt > 1"""
    ).fetchall()

    total_dupes = 0
    for agent_row in agents:
        agent_id = agent_row["agent_id"]
        posts = conn.execute(
            """SELECT l.post_id, r.raw_text
               FROM listings l JOIN raw_posts r ON l.post_id = r.post_id
               WHERE l.agent_id = ? AND l.property_id IS NULL
                 AND l.is_spam = 0 AND l.is_duplicate = 0
               ORDER BY r.captured_at ASC""",
            (agent_id,)
        ).fetchall()

        # Normalize all texts
        texts = [(p["post_id"], normalize_text(p["raw_text"] or "")) for p in posts]
        texts = [(pid, t) for pid, t in texts if len(t) > 50]

        if len(texts) < 2:
            continue

        # Cluster similar texts
        clusters = []  # list of lists of post_ids
        used = set()
        for i, (pid_i, text_i) in enumerate(texts):
            if pid_i in used:
                continue
            cluster = [pid_i]
            used.add(pid_i)
            for j in range(i + 1, len(texts)):
                pid_j, text_j = texts[j]
                if pid_j in used:
                    continue
                ratio = SequenceMatcher(None, text_i, text_j).ratio()
                if ratio > 0.80:
                    cluster.append(pid_j)
                    used.add(pid_j)
            if len(cluster) > 1:
                clusters.append(cluster)

        for cluster in clusters:
            best = pick_best(conn, cluster)
            dupes = [pid for pid in cluster if pid != best]
            for pid in dupes:
                conn.execute(
                    "UPDATE listings SET is_duplicate = 1, duplicate_of = ? WHERE post_id = ?",
                    (best, pid)
                )
            total_dupes += len(dupes)

    conn.commit()
    print(f"  Marked {total_dupes} text-similarity duplicates across {len(agents)} agents")
    return total_dupes


def phase_c(conn):
    """Cross-agent text similarity — same text posted by different agent_ids."""
    print("\n=== Phase C: Cross-agent text similarity ===")

    posts = conn.execute(
        """SELECT l.post_id, l.agent_id, r.raw_text
           FROM listings l JOIN raw_posts r ON l.post_id = r.post_id
           WHERE l.is_spam = 0 AND l.is_duplicate = 0
           ORDER BY r.captured_at ASC"""
    ).fetchall()

    # Group by normalized text hash (first 200 chars)
    hash_groups = defaultdict(list)
    for p in posts:
        norm = normalize_text(p["raw_text"] or "")
        if len(norm) < 50:
            continue
        key = norm[:200]
        hash_groups[key].append(p["post_id"])

    total_dupes = 0
    for key, post_ids in hash_groups.items():
        if len(post_ids) < 2:
            continue
        # Verify with full text comparison
        full_texts = {}
        for pid in post_ids:
            row = conn.execute("SELECT raw_text FROM raw_posts WHERE post_id = ?", (pid,)).fetchone()
            if row:
                full_texts[pid] = normalize_text(row["raw_text"] or "")

        # Cluster within this hash group
        used = set()
        for i, pid_i in enumerate(post_ids):
            if pid_i in used or pid_i not in full_texts:
                continue
            cluster = [pid_i]
            used.add(pid_i)
            for j in range(i + 1, len(post_ids)):
                pid_j = post_ids[j]
                if pid_j in used or pid_j not in full_texts:
                    continue
                ratio = SequenceMatcher(None, full_texts[pid_i], full_texts[pid_j]).ratio()
                if ratio > 0.85:  # stricter for cross-agent
                    cluster.append(pid_j)
                    used.add(pid_j)
            if len(cluster) > 1:
                best = pick_best(conn, cluster)
                dupes = [pid for pid in cluster if pid != best]
                for pid in dupes:
                    conn.execute(
                        "UPDATE listings SET is_duplicate = 1, duplicate_of = ? WHERE post_id = ?",
                        (best, pid)
                    )
                total_dupes += len(dupes)

    conn.commit()
    print(f"  Marked {total_dupes} cross-agent duplicates")
    return total_dupes


def phase_d(conn):
    """Merge duplicate agent records (same person, different FB profiles)."""
    print("\n=== Phase D: Merge duplicate agents ===")

    agents = conn.execute("SELECT * FROM agents ORDER BY total_listings DESC").fetchall()

    # Group by normalized name
    name_groups = defaultdict(list)
    for a in agents:
        if not a["name"]:
            continue
        norm_name = a["name"].strip().lower()
        # Remove extra spaces
        norm_name = re.sub(r'\s+', ' ', norm_name)
        name_groups[norm_name].append(dict(a))

    merged_count = 0
    for name, group in name_groups.items():
        if len(group) < 2:
            continue

        # Verify they should be merged: check phone overlap or same FB groups
        # Sort by total_listings desc — keep the one with most listings
        group.sort(key=lambda a: a["total_listings"], reverse=True)
        canonical = group[0]
        canonical_id = canonical["id"]

        for dup in group[1:]:
            dup_id = dup["id"]

            # Check if they share phones
            canonical_phones = set(json.loads(canonical.get("phones") or "[]"))
            dup_phones = set(json.loads(dup.get("phones") or "[]"))

            # Check if they post in same groups
            canonical_groups = set(r[0] for r in conn.execute(
                "SELECT DISTINCT group_name FROM raw_posts WHERE agent_id = ?", (canonical_id,)
            ).fetchall())
            dup_groups = set(r[0] for r in conn.execute(
                "SELECT DISTINCT group_name FROM raw_posts WHERE agent_id = ?", (dup_id,)
            ).fetchall())

            # Merge if: phone overlap OR posting in overlapping groups
            has_phone_overlap = bool(canonical_phones & dup_phones) if canonical_phones and dup_phones else False
            has_group_overlap = bool(canonical_groups & dup_groups)

            if not has_phone_overlap and not has_group_overlap:
                continue

            # Merge: update all references from dup to canonical
            conn.execute("UPDATE listings SET agent_id = ? WHERE agent_id = ?", (canonical_id, dup_id))
            conn.execute("UPDATE raw_posts SET agent_id = ? WHERE agent_id = ?", (canonical_id, dup_id))

            # Merge property_agents (handle unique constraint)
            dup_links = conn.execute(
                "SELECT * FROM property_agents WHERE agent_id = ?", (dup_id,)
            ).fetchall()
            for link in dup_links:
                existing = conn.execute(
                    "SELECT id FROM property_agents WHERE property_id = ? AND agent_id = ?",
                    (link["property_id"], canonical_id)
                ).fetchone()
                if existing:
                    conn.execute("DELETE FROM property_agents WHERE id = ?", (link["id"],))
                else:
                    conn.execute(
                        "UPDATE property_agents SET agent_id = ? WHERE id = ?",
                        (canonical_id, link["id"])
                    )

            # Merge contact info into canonical
            merged_phones = json.loads(canonical.get("phones") or "[]")
            for p in json.loads(dup.get("phones") or "[]"):
                if p not in merged_phones:
                    merged_phones.append(p)
            merged_wa = json.loads(canonical.get("whatsapp") or "[]")
            for w in json.loads(dup.get("whatsapp") or "[]"):
                if w not in merged_wa:
                    merged_wa.append(w)
            merged_emails = json.loads(canonical.get("emails") or "[]")
            for e in json.loads(dup.get("emails") or "[]"):
                if e not in merged_emails:
                    merged_emails.append(e)

            new_total = canonical["total_listings"] + dup["total_listings"]
            conn.execute(
                """UPDATE agents SET phones=?, whatsapp=?, emails=?, total_listings=?
                   WHERE id=?""",
                (json.dumps(merged_phones), json.dumps(merged_wa), json.dumps(merged_emails),
                 new_total, canonical_id)
            )

            # Delete the duplicate agent
            conn.execute("DELETE FROM agents WHERE id = ?", (dup_id,))
            merged_count += 1

            # Update canonical for next iteration
            canonical["phones"] = json.dumps(merged_phones)
            canonical["whatsapp"] = json.dumps(merged_wa)
            canonical["emails"] = json.dumps(merged_emails)
            canonical["total_listings"] = new_total

    conn.commit()
    print(f"  Merged {merged_count} duplicate agent records")
    return merged_count


def phase_e_swap_canonical(conn):
    """Ensure canonical (kept) listings have the best images. If a duplicate has images
    but the canonical doesn't, swap which one is canonical."""
    print("\n=== Phase E: Swap canonical to listings with images ===")

    # Find canonical listings with no local images that have duplicates WITH images
    canonicals_without_images = conn.execute(
        """SELECT l.post_id, l.agent_id, l.property_id
           FROM listings l
           JOIN raw_posts r ON l.post_id = r.post_id
           WHERE l.is_duplicate = 0 AND l.is_spam = 0
             AND (r.local_images IS NULL OR r.local_images = '' OR r.local_images = '[]')
           AND EXISTS (
               SELECT 1 FROM listings l2
               JOIN raw_posts r2 ON l2.post_id = r2.post_id
               WHERE l2.duplicate_of = l.post_id
                 AND r2.local_images IS NOT NULL AND r2.local_images != '' AND r2.local_images != '[]'
           )"""
    ).fetchall()

    swaps = 0
    for canon in canonicals_without_images:
        # Find the best duplicate with images
        best_dup = conn.execute(
            """SELECT l2.post_id FROM listings l2
               JOIN raw_posts r2 ON l2.post_id = r2.post_id
               WHERE l2.duplicate_of = ?
                 AND r2.local_images IS NOT NULL AND r2.local_images != '' AND r2.local_images != '[]'
               ORDER BY l2.confidence DESC
               LIMIT 1""",
            (canon["post_id"],)
        ).fetchone()

        if not best_dup:
            continue

        new_canonical = best_dup["post_id"]
        old_canonical = canon["post_id"]

        # Swap: new canonical becomes non-duplicate, old canonical becomes duplicate
        conn.execute(
            "UPDATE listings SET is_duplicate = 0, duplicate_of = NULL WHERE post_id = ?",
            (new_canonical,)
        )
        conn.execute(
            "UPDATE listings SET is_duplicate = 1, duplicate_of = ? WHERE post_id = ?",
            (new_canonical, old_canonical)
        )
        # Update all other dupes to point to new canonical
        conn.execute(
            "UPDATE listings SET duplicate_of = ? WHERE duplicate_of = ? AND post_id != ?",
            (new_canonical, old_canonical, old_canonical)
        )
        swaps += 1

    conn.commit()
    print(f"  Swapped {swaps} canonical listings to ones with images")
    return swaps


def main():
    print(f"Database: {DB_PATH}")
    conn = get_db()

    # Ensure columns exist
    cols = [r[1] for r in conn.execute("PRAGMA table_info(listings)").fetchall()]
    if "is_duplicate" not in cols:
        conn.execute("ALTER TABLE listings ADD COLUMN is_duplicate INTEGER DEFAULT 0")
    if "duplicate_of" not in cols:
        conn.execute("ALTER TABLE listings ADD COLUMN duplicate_of TEXT")
    conn.commit()

    # Pre-stats
    total = conn.execute("SELECT COUNT(*) FROM listings WHERE is_spam = 0").fetchone()[0]
    already_duped = conn.execute("SELECT COUNT(*) FROM listings WHERE is_duplicate = 1").fetchone()[0]
    print(f"\nBefore: {total} non-spam listings, {already_duped} already marked as duplicates")

    # Reset any previous dedup run
    conn.execute("UPDATE listings SET is_duplicate = 0, duplicate_of = NULL WHERE is_duplicate = 1")
    conn.commit()

    a = phase_a(conn)
    b = phase_b(conn)
    c = phase_c(conn)
    d = phase_d(conn)
    e = phase_e_swap_canonical(conn)

    # Post-stats
    remaining = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE is_spam = 0 AND is_duplicate = 0"
    ).fetchone()[0]
    duped = conn.execute("SELECT COUNT(*) FROM listings WHERE is_duplicate = 1").fetchone()[0]
    print(f"\nAfter: {remaining} unique listings, {duped} duplicates hidden")
    print(f"Breakdown: Phase A={a}, Phase B={b}, Phase C={c}, Phase D agents merged={d}, Phase E image swaps={e}")

    # Check Raul Carrillo
    raul = conn.execute(
        """SELECT COUNT(*) FROM listings l
           JOIN agents a ON l.agent_id = a.id
           WHERE LOWER(a.name) LIKE '%raul carrillo%'
             AND l.is_spam = 0 AND l.is_duplicate = 0"""
    ).fetchone()[0]
    raul_total = conn.execute(
        """SELECT COUNT(*) FROM listings l
           JOIN agents a ON l.agent_id = a.id
           WHERE LOWER(a.name) LIKE '%raul carrillo%'
             AND l.is_spam = 0"""
    ).fetchone()[0]
    print(f"\nRaul Carrillo: {raul} unique / {raul_total} total (was 182)")

    conn.close()
    print("\nDone! Deploy dashboard to see results.")


if __name__ == "__main__":
    main()
