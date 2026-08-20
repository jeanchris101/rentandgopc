"""Read Chrome cookies using immutable SQLite mode (no lock needed)."""
import sqlite3
import json
import os
import base64
from pathlib import Path

cookie_db = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data" / "Default" / "Network" / "Cookies"
local_state_path = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data" / "Local State"

# Build proper file URI for Windows
db_path = str(cookie_db).replace("\\", "/")
uri = f"file:///{db_path}?immutable=1"

print(f"Cookie DB: {cookie_db}")
print(f"Exists: {cookie_db.exists()}")

conn = sqlite3.connect(uri, uri=True)
cursor = conn.execute(
    "SELECT name, encrypted_value, value, host_key, path, is_secure, is_httponly, "
    "expires_utc, samesite FROM cookies WHERE host_key LIKE '%facebook.com%'"
)
rows = cursor.fetchall()
conn.close()
print(f"Raw FB cookie rows: {len(rows)}")

# Decrypt Chrome cookies (Windows DPAPI + AES-GCM)
try:
    import win32crypt
    with open(local_state_path, "r") as f:
        local_state = json.load(f)
    encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
    encrypted_key = encrypted_key[5:]  # Remove DPAPI prefix
    key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
    print(f"Got Chrome encryption key ({len(key)} bytes)")
    has_key = True
except Exception as e:
    print(f"Cannot get Chrome key: {e}")
    has_key = False

cookies = []
for name, encrypted_value, value, host, path, secure, httponly, expires, samesite in rows:
    actual_value = value
    if not actual_value and encrypted_value and has_key:
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            # v10/v20 prefix (3 bytes) + nonce (12 bytes) + ciphertext
            nonce = encrypted_value[3:15]
            ciphertext = encrypted_value[15:]
            aesgcm = AESGCM(key)
            actual_value = aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
        except Exception as e:
            # Try old DPAPI method
            try:
                decrypted = win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)
                actual_value = decrypted[1].decode("utf-8", errors="replace")
            except Exception:
                pass

    if not actual_value:
        continue

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
        cookie["expires"] = (expires / 1000000) - 11644473600
    cookies.append(cookie)

print(f"Decrypted {len(cookies)} cookies")

key_names = {"c_user", "xs", "fr", "datr", "sb"}
found = {c["name"] for c in cookies} & key_names
print(f"Key auth cookies: {found}")
missing = key_names - found
if missing:
    print(f"Missing: {missing}")
else:
    print("All key auth cookies present!")

# Save as Playwright storage state
storage_state = {"cookies": cookies, "origins": []}
out = Path(__file__).parent / "sessions" / "burner1.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(storage_state, indent=2))
print(f"Saved to: {out}")
