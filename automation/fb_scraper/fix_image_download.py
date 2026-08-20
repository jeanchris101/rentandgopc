"""Fix script — replaces _download_images_via_browser with canvas-based approach on VPS."""
import re

with open("/opt/fb_scraper/scraper.py") as f:
    content = f.read()

# Find the old function
old_start = content.find("async def _download_images_via_browser")
old_end = content.find("\n\n# --- Create browser context", old_start)

if old_start < 0 or old_end < 0:
    print(f"Could not find function: start={old_start} end={old_end}")
    exit(1)

new_func = '''async def _download_images_via_browser(page, post_id, image_urls):
    """Download images by having the browser draw them to canvas and extract base64.
    This works because the images are already loaded in the DOM with valid session tokens."""
    import base64 as _b64
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(c if c.isalnum() or c == "_" else "_" for c in post_id)
    filenames = []

    for idx, url in enumerate(image_urls[:MAX_IMAGES]):
        if not url or not isinstance(url, str):
            continue
        fname = f"{safe_id}_{idx}.jpg"
        filepath = IMAGE_DIR / fname
        if filepath.exists() and filepath.stat().st_size > 0:
            filenames.append(fname)
            continue
        try:
            # Use JS to load image via DOM (uses browser cookies) and extract as base64
            b64_data = await page.evaluate("""
                async (url) => {
                    return new Promise((resolve) => {
                        const img = new Image();
                        img.crossOrigin = "anonymous";
                        img.onload = () => {
                            try {
                                const canvas = document.createElement("canvas");
                                canvas.width = img.naturalWidth;
                                canvas.height = img.naturalHeight;
                                canvas.getContext("2d").drawImage(img, 0, 0);
                                resolve(canvas.toDataURL("image/jpeg", 0.85).split(",")[1]);
                            } catch(e) { resolve(null); }
                        };
                        img.onerror = () => resolve(null);
                        setTimeout(() => resolve(null), 6000);
                        img.src = url;
                    });
                }
            """, url)

            if b64_data:
                filepath.write_bytes(_b64.b64decode(b64_data))
                filenames.append(fname)
                log.info(f"    Cached image {idx} for {post_id[:20]}")
        except Exception as e:
            log.debug(f"    Image {idx} error for {post_id[:20]}: {e}")

    return filenames
'''

content = content[:old_start] + new_func + content[old_end:]

with open("/opt/fb_scraper/scraper.py", "w") as f:
    f.write(content)

print(f"Replaced function ({old_end - old_start} chars old -> {len(new_func)} chars new)")
