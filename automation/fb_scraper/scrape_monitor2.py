import paramiko
import time
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

HOST = '144.172.100.16'
USER = 'root'
PASS = '4K98JSaEoLDaP5'

def ssh_exec(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=15)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    return out, err

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASS, timeout=10)
    print("Connected to VPS (round 2).\n")

    db_cmd = """python3 -c "
import sqlite3
c=sqlite3.connect('/opt/data/fb_listings.db')
print('Posts:', c.execute('SELECT COUNT(*) FROM raw_posts').fetchone()[0])
print('Listings:', c.execute('SELECT COUNT(*) FROM listings').fetchone()[0])
" 2>&1"""

    for i in range(1, 21):
        print(f"=== Check {i}/20 ===")

        ps_out, _ = ssh_exec(client, 'ps aux | grep "scraper.py" | grep -v grep')
        scraper_running = bool(ps_out.strip())
        print(f"Scraper running: {scraper_running}")

        log_out, _ = ssh_exec(client, 'tail -5 /var/log/scraper_run.log 2>/dev/null || echo "(no log)"')
        print(f"Log: {log_out}")

        db_out, _ = ssh_exec(client, db_cmd)
        print(f"DB: {db_out}")

        if not scraper_running:
            print("\n*** Scraper finished! ***")
            print(f"Final counts: {db_out}")

            # Start join process
            print("\nStarting join_all.py...")
            join_cmd = 'cd /opt/fb_scraper && nohup xvfb-run --auto-servernum python3 join_all.py > /var/log/join_groups.log 2>&1 &'
            ssh_exec(client, join_cmd)
            time.sleep(3)

            ps_join, _ = ssh_exec(client, 'ps aux | grep "join_all.py" | grep -v grep')
            if ps_join:
                print("join_all.py confirmed running!")
                for line in ps_join.split('\n'):
                    parts = line.split()
                    if len(parts) > 10:
                        print(f"  PID {parts[1]}: {' '.join(parts[10:])}")
            else:
                print("WARNING: join_all.py not found. Checking log...")
                log_join, _ = ssh_exec(client, 'tail -5 /var/log/join_groups.log 2>/dev/null')
                print(log_join)

            client.close()
            print("\nDone.")
            return

        if i < 20:
            print(f"Sleeping 30s...\n")
            time.sleep(30)

    print("\n*** Timeout round 2. Scraper still running. ***")
    client.close()

if __name__ == '__main__':
    main()
