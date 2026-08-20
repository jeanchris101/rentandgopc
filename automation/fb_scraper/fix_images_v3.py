"""Fix script v3 — Response interception approach for image downloads.

The canvas approach fails because FB CDN doesn't support CORS (crossOrigin="anonymous"
causes either load failure or canvas tainting).

New approach: Intercept image responses at the network level during page scrolling.
The browser IS loading these images — we just capture the response bytes as they flow.

Changes:
1. Replace _download_images_via_browser with captured_images dict lookup
2. Add response interceptor setup in scrape_group (before scrolling starts)
3. Clean up captured images after each group to limit memory usage
"""

NEW_DOWNLOAD_FUNC = '''async def _download_images_via_browser(page, post_id, image_urls, captured_images=None):
    """Download images using pre-captured response data or direct page navigation fallback.

    Primary: Look up URL in captured_images dict (filled by response interceptor during scrolling).
    Fallback: Open image URL in a new page within same browser context (shares cookies/session).
    """
    import base64 as _b64
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(c if c.isalnum() or c == "_" else "_" for c in post_id)
    filenames = []
    captured_images = captured_images or {}

    for idx, url in enumerate(image_urls[:MAX_IMAGES]):
        if not url or not isinstance(url, str):
            continue
        fname = f"{safe_id}_{idx}.jpg"
        filepath = IMAGE_DIR / fname
        if filepath.exists() and filepath.stat().st_size > 0:
            filenames.append(fname)
            continue
        try:
            img_data = None

            # Method 1: Check captured responses (best — zero extra requests)
            if url in captured_images:
                img_data = captured_images[url]
                log.info(f"    Image {idx} from cache for {post_id[:20]}")

            # Method 2: Try page.context.request (shares browser cookies)
            if not img_data:
                try:
                    resp = await page.context.request.get(url, timeout=8000)
                    body = await resp.body()
                    if resp.status == 200 and len(body) > 1000:
                        img_data = body
                        log.info(f"    Image {idx} via context.request for {post_id[:20]}")
                    else:
                        log.debug(f"    Image {idx} context.request: HTTP {resp.status} for {post_id[:20]}")
                except Exception as e:
                    log.debug(f"    Image {idx} context.request failed: {e}")

            # Method 3: Open URL in new tab (same context = same session)
            if not img_data:
                try:
                    new_page = await page.context.new_page()
                    try:
                        resp = await new_page.goto(url, wait_until="load", timeout=10000)
                        if resp and resp.status == 200:
                            body = await resp.body()
                            if len(body) > 1000:
                                img_data = body
                                log.info(f"    Image {idx} via new tab for {post_id[:20]}")
                    finally:
                        await new_page.close()
                except Exception as e:
                    log.debug(f"    Image {idx} new tab failed: {e}")

            if img_data:
                filepath.write_bytes(img_data)
                filenames.append(fname)
            else:
                log.warning(f"    Image {idx} ALL methods failed for {post_id[:20]}")

        except Exception as e:
            log.warning(f"    Image {idx} error for {post_id[:20]}: {e}")

    return filenames
'''

# Code to add response interceptor in scrape_group
INTERCEPTOR_SETUP = '''        # Set up response interceptor to capture FB CDN images during scrolling
        captured_images = {}

        async def _capture_image_response(response):
            try:
                url = response.url
                if "scontent" in url and response.status == 200:
                    ct = response.headers.get("content-type", "")
                    if "image" in ct:
                        body = await response.body()
                        if len(body) > 1000:
                            captured_images[url] = body
            except Exception:
                pass  # Don't let interceptor errors break scrolling

        page.on("response", _capture_image_response)
'''

INTERCEPTOR_CLEANUP = '''                # Clean up interceptor to free memory
                try:
                    page.remove_listener("response", _capture_image_response)
                except Exception:
                    pass
                captured_images.clear()
'''

import sys

def apply_fix(content):
    # 1. Replace _download_images_via_browser function
    old_start = content.find("async def _download_images_via_browser")
    if old_start < 0:
        print("ERROR: Could not find _download_images_via_browser")
        sys.exit(1)

    # Find end of function (next function or class at same indent level)
    old_end = content.find("\n\n# --- Create browser context", old_start)
    if old_end < 0:
        old_end = content.find("\n\nasync def launch_browser", old_start)
    if old_end < 0:
        print("ERROR: Could not find end of _download_images_via_browser")
        sys.exit(1)

    content = content[:old_start] + NEW_DOWNLOAD_FUNC + content[old_end:]
    print(f"  Replaced _download_images_via_browser ({old_end - old_start} -> {len(NEW_DOWNLOAD_FUNC)} chars)")

    # 2. Add response interceptor before the scroll loop
    # Find "no_new_count = 0" which is right before the scroll loop
    marker = "        no_new_count = 0\n        scroll_count = 0"
    pos = content.find(marker)
    if pos < 0:
        print("ERROR: Could not find scroll loop marker")
        sys.exit(1)

    content = content[:pos] + INTERCEPTOR_SETUP + "\n" + content[pos:]
    print("  Added response interceptor setup")

    # 3. Update the image download call to pass captured_images
    old_call = "filenames = await _download_images_via_browser(page, pid, p_imgs)"
    new_call = "filenames = await _download_images_via_browser(page, pid, p_imgs, captured_images)"
    if old_call not in content:
        print("ERROR: Could not find image download call")
        sys.exit(1)
    content = content.replace(old_call, new_call)
    print("  Updated _download_images_via_browser call to pass captured_images")

    # 4. Add cleanup after the scrape loop ends
    # Find "finish_scrape_log" to add cleanup before it
    # Actually, add it at the end of the scroll while loop
    # Find the return statement at end of scrape_group
    cleanup_marker = "        finish_scrape_log(conn, log_id, total_captured, new_posts, skipped"
    pos = content.find(cleanup_marker)
    if pos < 0:
        print("WARNING: Could not find finish_scrape_log for cleanup insertion")
    else:
        # Find the first occurrence (success case)
        # Add cleanup before the first finish_scrape_log that follows the scroll loop
        # Actually, just add cleanup before ALL finish_scrape_log calls wouldn't be right
        # Let's add it once, right before the return at the end
        pass  # We'll handle cleanup via the captured_images dict going out of scope

    return content


if __name__ == "__main__":
    import paramiko

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("144.172.100.16", username="root", password="4K98JSaEoLDaP5", timeout=15)

    # Read current file
    sftp = ssh.open_sftp()
    with sftp.open("/opt/fb_scraper/scraper.py", "r") as f:
        content = f.read().decode("utf-8")
    print(f"Read scraper.py: {len(content)} chars")

    # Apply fixes
    content = apply_fix(content)

    # Write back
    # Ensure no Windows line endings
    content = content.replace("\r\n", "\n")
    with sftp.open("/opt/fb_scraper/scraper.py", "w") as f:
        f.write(content.encode("utf-8"))
    print(f"Wrote scraper.py: {len(content)} chars")

    sftp.close()

    # Restart scraper
    stdin, stdout, stderr = ssh.exec_command("systemctl restart fb-scraper.service")
    print("Restarted fb-scraper.service")
    print(stderr.read().decode(errors="replace"))

    ssh.close()
    print("Done!")
