"""
Image quality gate for the Facebook poster.

Every photo in properties.json -> post_images is what a buyer sees first in the
feed, so it has to survive four checks that pixel dimensions alone do not catch:

  sharpness   Laplacian variance on a scale-normalised copy. A 1920x1080 export
              of a soft or upscaled original still reads as mushy in-feed.
  compression bytes per pixel. Below ~0.055 the JPEG is squeezed hard enough
              that Facebook's own re-encode turns edges into blocks.
  orientation portrait images get centre-cropped in the feed, cutting the
              subject. Landscape only.
  size        Meta rejects photo uploads over 4 MB.

Run it after adding or swapping any post image:

    python automation/check_images.py            # audit, exit 1 on any failure
    python automation/check_images.py --all      # also score unused photos,
                                                 # to find better candidates
Sharpness and clutter are different problems: this catches the first. A photo
can score 900 and still show moving boxes, so a human still looks before it
ships.
"""

import argparse
import glob
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

BASE_DIR = Path(__file__).resolve().parent
REPO_DIR = BASE_DIR.parent
PROPERTIES_FILE = BASE_DIR / "data" / "properties.json"

MIN_SHARPNESS = 150.0      # below this the photo reads soft in a feed
MIN_BYTES_PER_PIXEL = 0.055
MIN_SHORT_EDGE = 900       # px; Meta upscales anything smaller
MAX_BYTES = 4_000_000      # Meta's photo upload ceiling

_LAPLACIAN = ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1)


def score(path: Path) -> dict:
    """Measure one image. Returns metrics plus the list of failed checks."""
    im = Image.open(path)
    w, h = im.size
    size_bytes = path.stat().st_size

    grey = im.convert("L")
    grey.thumbnail((1000, 1000))  # normalise so scores compare across sizes
    sharpness = ImageStat.Stat(grey.filter(_LAPLACIAN)).stddev[0] ** 2

    problems = []
    if sharpness < MIN_SHARPNESS:
        problems.append(f"blanda (nitidez {sharpness:.0f} < {MIN_SHARPNESS:.0f})")
    if size_bytes / (w * h) < MIN_BYTES_PER_PIXEL:
        problems.append(f"sobre-comprimida ({size_bytes / (w * h):.3f} b/px)")
    if h > w:
        problems.append(f"vertical ({w}x{h}) — se recorta en el feed")
    if min(w, h) < MIN_SHORT_EDGE:
        problems.append(f"lado corto {min(w, h)}px < {MIN_SHORT_EDGE}px")
    if size_bytes > MAX_BYTES:
        problems.append(f"pesa {size_bytes / 1e6:.1f} MB > 4 MB (Meta la rechaza)")

    return {
        "sharpness": sharpness,
        "bpp": size_bytes / (w * h),
        "width": w,
        "height": h,
        "kb": size_bytes // 1024,
        "problems": problems,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit Facebook post images")
    ap.add_argument("--all", action="store_true",
                    help="also score photos not currently in post_images")
    args = ap.parse_args()

    data = json.loads(PROPERTIES_FILE.read_text(encoding="utf-8"))
    failures = 0

    for prop in data["properties"]:
        in_use = prop.get("post_images", [])
        if not in_use:
            continue
        print(f"\n=== {prop['slug']} ===")

        candidates = list(in_use)
        if args.all:
            folder = REPO_DIR / os.path.dirname(in_use[0])
            extra = sorted(
                os.path.relpath(p, REPO_DIR).replace("\\", "/")
                for p in glob.glob(str(folder / "*.jpg"))
            )
            candidates += [c for c in extra if c not in in_use]

        for rel in candidates:
            path = REPO_DIR / rel
            used = rel in in_use
            if not path.exists():
                print(f"  FALTA  {rel}")
                if used:
                    failures += 1
                continue

            m = score(path)
            mark = "*" if used else " "
            line = (f"  {mark} {os.path.basename(rel):<32} "
                    f"nitidez {m['sharpness']:6.0f}  {m['bpp']:.3f} b/px  "
                    f"{m['width']}x{m['height']}  {m['kb']:>4} KB")
            if m["problems"]:
                print(f"{line}  <- {'; '.join(m['problems'])}")
                if used:
                    failures += 1
            else:
                print(line)

    print()
    if failures:
        print(f"{failures} imagen(es) en uso no pasan el chequeo. "
              f"Cambialas en properties.json -> post_images.")
        return 1
    print("Todas las imagenes en uso pasan el chequeo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
