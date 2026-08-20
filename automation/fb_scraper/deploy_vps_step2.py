"""Step 4-5: Start new scrape and verify."""
import sys
import io
import time
import paramiko

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

HOST = "144.172.100.16"
USER = "root"
PASS = "4K98JSaEoLDaP5"

def run_cmd(ssh, cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    if err:
        print(f"  [stderr] {err}")
    return out

def run_bg(ssh, cmd):
    """Run a background command without waiting for output."""
    transport = ssh.get_transport()
    channel = transport.open_session()
    channel.exec_command(cmd)
    time.sleep(1)
    channel.close()

def main():
    print(f"Connecting to {HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASS, timeout=15)
    print("Connected.\n")

    # Confirm scraper is not running
    ps_out = run_cmd(ssh, "ps aux | grep scraper.py | grep -v grep")
    if ps_out:
        print(f"WARNING: Scraper still running:\n{ps_out}")
        print("Killing it...")
        run_cmd(ssh, "pkill -f 'python3 scraper.py'")
        time.sleep(2)
    else:
        print("Confirmed: scraper is NOT running.\n")

    # Step 4: Start new scrape (use run_bg to avoid blocking)
    print("=== STEP 4: Start NEW scrape ===")
    start_cmd = "cd /opt/fb_scraper && nohup xvfb-run --auto-servernum python3 scraper.py > /var/log/scraper_run.log 2>&1 &"
    run_bg(ssh, start_cmd)
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
