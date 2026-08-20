import paramiko
import time
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

HOST = '144.172.100.16'
USER = 'root'
PASS = '4K98JSaEoLDaP5'

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASS, timeout=10)
    print("Connected to VPS.")

    # Use bash -c with disown to avoid blocking
    join_cmd = 'bash -c "cd /opt/fb_scraper && nohup xvfb-run --auto-servernum python3 join_all.py > /var/log/join_groups.log 2>&1 &"'

    # Use get_transport().open_session() to fire and forget
    transport = client.get_transport()
    channel = transport.open_session()
    channel.exec_command(join_cmd)

    print("Join command sent. Waiting 5s for process to start...")
    time.sleep(5)

    # Now check with a fresh exec
    stdin, stdout, stderr = client.exec_command('ps aux | grep "join_all.py" | grep -v grep', timeout=10)
    ps_out = stdout.read().decode('utf-8', errors='replace').strip()

    if ps_out:
        print("join_all.py confirmed running!")
        for line in ps_out.split('\n'):
            parts = line.split()
            if len(parts) > 10:
                print(f"  PID {parts[1]}: {' '.join(parts[10:])}")
    else:
        print("join_all.py not found in process list. Checking log...")
        stdin, stdout, stderr = client.exec_command('tail -10 /var/log/join_groups.log 2>/dev/null', timeout=10)
        log_out = stdout.read().decode('utf-8', errors='replace').strip()
        print(log_out if log_out else "(no log output)")

    # Also show scraper final summary
    stdin, stdout, stderr = client.exec_command('tail -10 /var/log/scraper_run.log', timeout=10)
    log_out = stdout.read().decode('utf-8', errors='replace').strip()
    print(f"\nScraper final log:\n{log_out}")

    client.close()
    print("\nDone.")

if __name__ == '__main__':
    main()
