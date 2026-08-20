"""Grab Facebook cookies from Chrome and save as Playwright storage state."""
import json
import sqlite3
import shutil
import os
from pathlib import Path

# Chrome cookie DB path (Windows)
CHROME_COOKIE_DB = Path(os.environ["LOCALAPPDATA"]) / "Google/Chrome/User Data/Default/Network/Cookies"
OUTPUT = Path(__file__).parent / "sessions" / "burner1.json"

def get_chrome_cookies():
    """Read Facebook cookies from Chrome's SQLite DB."""
    # Chrome locks the DB, so copy it first
    tmp = Path(__file__).parent / "_cookies_tmp.db"
    shutil.copy2(CHROME_COOKIE_DB, tmp)

    conn = sqlite3.connect(str(tmp))
    cursor = conn.execute(
        "SELECT name, encrypted_value, value, host_key, path, is_secure, is_httponly, "
        "expires_utc, samesite FROM cookies WHERE host_key LIKE '%facebook.com%'"
    )

    cookies = []
    for name, encrypted_value, value, host, path, secure, httponly, expires, samesite in cursor.fetchall():
        # Chrome encrypts cookies on Windows via DPAPI
        # Try to decrypt using win32crypt
        actual_value = value
        if not actual_value and encrypted_value:
            try:
                import win32crypt
                decrypted = win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)
                actual_value = decrypted[1].decode('utf-8', errors='replace')
            except Exception:
                pass

            if not actual_value:
                try:
                    # Chrome v80+ uses AES-GCM with key from Local State
                    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                    import base64

                    local_state_path = Path(os.environ["LOCALAPPDATA"]) / "Google/Chrome/User Data/Local State"
                    with open(local_state_path, 'r') as f:
                        local_state = json.load(f)

                    encrypted_key = base64.b64decode(local_state['os_crypt']['encrypted_key'])
                    encrypted_key = encrypted_key[5:]  # Remove 'DPAPI' prefix

                    import win32crypt
                    key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]

                    # encrypted_value: v10 prefix (3 bytes) + nonce (12 bytes) + ciphertext + tag
                    nonce = encrypted_value[3:15]
                    ciphertext = encrypted_value[15:]

                    aesgcm = AESGCM(key)
                    actual_value = aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8')
                except Exception as e2:
                    print(f"  Could not decrypt {name}: {e2}")
                    continue

        if not actual_value:
            continue

        # Map samesite values
        samesite_map = {-1: "None", 0: "None", 1: "Lax", 2: "Strict"}

        cookie = {
            "name": name,
            "value": actual_value,
            "domain": host,
            "path": path,
            "secure": bool(secure),
            "httpOnly": bool(httponly),
            "sameSite": samesite_map.get(samesite, "None"),
        }
        if expires and expires > 0:
            # Chrome uses microseconds since 1601-01-01, convert to Unix epoch
            cookie["expires"] = (expires / 1000000) - 11644473600

        cookies.append(cookie)

    conn.close()
    tmp.unlink(missing_ok=True)
    return cookies


def main():
    print("Grabbing Facebook cookies from Chrome...")
    cookies = get_chrome_cookies()
    print(f"Found {len(cookies)} Facebook cookies")

    if not cookies:
        print("ERROR: No cookies found! Make sure you're logged into Facebook in Chrome.")
        return

    # Build Playwright storage state format
    storage_state = {
        "cookies": cookies,
        "origins": []
    }

    # Save
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(storage_state, indent=2))
    print(f"Saved to {OUTPUT}")

    # Show key cookies
    key_names = {"c_user", "xs", "fr", "datr", "sb"}
    found = {c["name"] for c in cookies} & key_names
    missing = key_names - found
    print(f"Key cookies found: {found}")
    if missing:
        print(f"Missing: {missing}")
    else:
        print("All key auth cookies present!")


if __name__ == "__main__":
    main()
