"""Deploy improved scraper to VPS and restart scraping."""
import sys
import io
import time
import paramiko

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

HOST = "144.172.100.16"
USER = "root"
PASS = "4K98JSaEoLDaP5"
LOCAL_SCRAPER = r"C:\Claude\puntacana-properties\automation\fb_scraper\scraper.py"
REMOTE_SCRAPER = "/opt/fb_scraper/scraper.py"

def run_cmd(ssh, cmd, timeout=30):
    """Run command and return stdout."""
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    if err:
        print(f"  [stderr] {err}")
    return out

def main():
    print(f"Connecting to {HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASS, timeout=15)
    print("Connected.\n")

    # Step 1: Upload scraper via SFTP
    print("=== STEP 1: Upload improved scraper ===")
    sftp = ssh.open_sftp()
    # Ensure directory exists
    run_cmd(ssh, "mkdir -p /opt/fb_scraper")
    sftp.put(LOCAL_SCRAPER, REMOTE_SCRAPER)
    remote_size = sftp.stat(REMOTE_SCRAPER).st_size
    sftp.close()
    print(f"Uploaded {LOCAL_SCRAPER} -> {REMOTE_SCRAPER} ({remote_size} bytes)\n")

    # Step 2: Check if scraper is running
    print("=== STEP 2: Check if scraper is running ===")
    ps_out = run_cmd(ssh, "ps aux | grep scraper.py | grep -v grep")

    if ps_out:
        print(f"Scraper IS running:\n{ps_out}\n")

        # Check progress
        log_tail = run_cmd(ssh, "tail -5 /var/log/scraper_run.log")
        print(f"Last 5 log lines:\n{log_tail}\n")

        # Wait up to 5 minutes
        max_wait = 300  # 5 min
        waited = 0
        while waited < max_wait:
            print(f"Waiting for scraper to finish... ({waited}s / {max_wait}s)")
            time.sleep(30)
            waited += 30
            ps_out = run_cmd(ssh, "ps aux | grep scraper.py | grep -v grep")
            if not ps_out:
                print("Scraper finished naturally!")
                break
            else:
                log_tail = run_cmd(ssh, "tail -3 /var/log/scraper_run.log")
                print(f"  Still running. Log: {log_tail}")

        # If still running after 5 min, kill it
        if ps_out:
            print("\nScraper still running after 5 min. Killing it...")
            run_cmd(ssh, "pkill -f 'python3 scraper.py'")
            time.sleep(2)
            ps_check = run_cmd(ssh, "ps aux | grep scraper.py | grep -v grep")
            if ps_check:
                print("Force killing...")
                run_cmd(ssh, "pkill -9 -f 'python3 scraper.py'")
                time.sleep(1)
            print("Scraper killed.\n")
    else:
        print("Scraper is NOT running.\n")

    # Step 3: Check final counts
    print("=== STEP 3: Check DB counts ===")
    count_cmd = """python3 -c "
import sqlite3
c = sqlite3.connect('/opt/data/fb_listings.db')
total = c.execute('SELECT COUNT(*) FROM raw_posts').fetchone()[0]
print(f'Total posts: {total}')
rows = c.execute('SELECT group_name, COUNT(*) FROM raw_posts GROUP BY group_name ORDER BY COUNT(*) DESC').fetchall()
for r in rows:
    print(f'  {r[0]}: {r[1]}')
c.close()
" """
    counts = run_cmd(ssh, count_cmd)
    if counts:
        print(counts)
    else:
        print("(No data or DB not found yet)")
    print()

    # Step 4: Start new scrape
    print("=== STEP 4: Start NEW scrape ===")
    start_cmd = "cd /opt/fb_scraper && nohup xvfb-run --auto-servernum python3 scraper.py > /var/log/scraper_run.log 2>&1 &"
    run_cmd(ssh, start_cmd)
    print("Scrape command issued.\n")

    # Step 5: Wait 15s and verify
    print("=== STEP 5: Verify scraper started (waiting 15s) ===")
    time.sleep(15)

    ps_out = run_cmd(ssh, "ps aux | grep scraper.py | grep -v grep")
    if ps_out:
        print(f"Scraper IS running:\n{ps_out}\n")
    else:
        print("WARNING: Scraper process NOT found!\n")

    log_tail = run_cmd(ssh, "tail -20 /var/log/scraper_run.log")
    print(f"Log output:\n{log_tail}\n")

    ssh.close()
    print("Done. SSH connection closed.")

if __name__ == "__main__":
    main()
