"""Deploy FB scraper to DigitalOcean VPS via SSH (paramiko)."""
import os
import sys
import time
from pathlib import Path

import paramiko

VPS_HOST = "144.172.100.16"
VPS_USER = "root"
VPS_PASS = "4K98JSaEoLDaP5"
REMOTE_DIR = "/opt/fb_scraper"
LOCAL_DIR = Path(__file__).parent

# Files to upload
FILES = [
    "scraper.py", "parser.py", "database.py", "config.py",
    "export.py", "config.json", "requirements.txt",
    "image_cache.py", "backfill_images.py", "dashboard.py",
]


def ssh_exec(ssh, cmd, timeout=300):
    """Execute command and print output in real-time."""
    print(f"  $ {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    exit_code = stdout.channel.recv_exit_status()
    if out:
        print(f"    {out[:500]}")
    if err and exit_code != 0:
        print(f"    [ERR] {err[:500]}")
    return exit_code, out, err


def main():
    print(f"=== Deploying FB Scraper to {VPS_HOST} ===\n")

    # Connect
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {VPS_HOST}...")
    ssh.connect(VPS_HOST, username=VPS_USER, password=VPS_PASS, timeout=30)
    print("Connected!\n")

    sftp = ssh.open_sftp()

    # Create directories
    print("1. Creating directories...")
    ssh_exec(ssh, f"mkdir -p {REMOTE_DIR}/sessions {REMOTE_DIR}/data")

    # Upload files
    print(f"\n2. Uploading {len(FILES)} files...")
    for fname in FILES:
        local_path = LOCAL_DIR / fname
        if local_path.exists():
            remote_path = f"{REMOTE_DIR}/{fname}"
            sftp.put(str(local_path), remote_path)
            print(f"    Uploaded: {fname}")
        else:
            print(f"    SKIP (not found): {fname}")

    # Check if wa_scraper.py exists and upload it too
    wa_path = LOCAL_DIR / "wa_scraper.py"
    if wa_path.exists():
        sftp.put(str(wa_path), f"{REMOTE_DIR}/wa_scraper.py")
        print(f"    Uploaded: wa_scraper.py")

    sftp.close()

    # Install system dependencies
    print("\n3. Installing system dependencies...")
    ssh_exec(ssh, "apt-get update -qq", timeout=120)
    ssh_exec(ssh, "apt-get install -y -qq python3-pip xvfb libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 2>/dev/null", timeout=120)

    # Install Python packages
    print("\n4. Installing Python packages...")
    ssh_exec(ssh, "pip3 install patchright --break-system-packages 2>/dev/null || pip3 install patchright", timeout=120)

    # Install Chromium
    print("\n5. Installing Chromium for Patchright...")
    ssh_exec(ssh, "python3 -m patchright install chromium", timeout=180)

    # Test parser
    print("\n6. Testing parser...")
    exit_code, out, _ = ssh_exec(ssh, f'cd {REMOTE_DIR} && python3 -c "from parser import parse; r = parse(\'Vendo apto en Cap Cana, 2 hab, USD 195K\'); print(f\'Zone: {{r.neighborhood}}, Price: {{r.price.amount if r.price else None}}, Confidence: {{r.confidence}}\')"')
    if exit_code == 0:
        print("    Parser OK!")
    else:
        print("    Parser test failed — check dependencies")

    # Auto-login
    print("\n7. Auto-login with burner account...")
    exit_code, out, err = ssh_exec(ssh, f"cd {REMOTE_DIR} && xvfb-run --auto-servernum --server-args='-screen 0 1366x768x24' python3 scraper.py setup burner1", timeout=120)
    if "Login confirmed" in out or "Session saved" in out or "Already logged in" in out:
        print("    Login successful!")
    else:
        print(f"    Login may need attention. Output: {out[:300]}")
        if err:
            print(f"    Errors: {err[:300]}")

    # Join groups
    print("\n8. Auto-joining groups...")
    exit_code, out, err = ssh_exec(ssh, f"cd {REMOTE_DIR} && xvfb-run --auto-servernum --server-args='-screen 0 1366x768x24' python3 scraper.py join", timeout=300)
    print(f"    Join output: {out[:500]}")

    # First scrape
    print("\n9. Running first scrape...")
    exit_code, out, err = ssh_exec(ssh, f"cd {REMOTE_DIR} && xvfb-run --auto-servernum --server-args='-screen 0 1366x768x24' python3 scraper.py scrape --max-scrolls 10 --max-posts 50", timeout=600)
    print(f"    Scrape output: {out[:500]}")

    # Set up daily cron
    print("\n10. Setting up daily cron (10 AM DR time)...")
    cron_line = f"0 14 * * * cd {REMOTE_DIR} && xvfb-run --auto-servernum --server-args='-screen 0 1366x768x24' python3 scraper.py scrape >> /var/log/fb_scraper.log 2>&1"
    ssh_exec(ssh, f'(crontab -l 2>/dev/null | grep -v fb_scraper; echo "{cron_line}") | crontab -')
    print(f"    Cron set: {cron_line}")

    ssh.close()

    print("\n" + "=" * 60)
    print("DEPLOYMENT COMPLETE!")
    print(f"  Scraper running at: {VPS_HOST}:{REMOTE_DIR}")
    print(f"  Daily cron: 10 AM DR time (14:00 UTC)")
    print(f"  Logs: /var/log/fb_scraper.log")
    print(f"  Export data: python3 export.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
