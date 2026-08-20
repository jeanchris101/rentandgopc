import paramiko
import time
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

HOST = '144.172.100.16'
USER = 'root'
PASS = '4K98JSaEoLDaP5'

def ssh_exec(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
    return stdout.read().decode('utf-8', errors='replace').strip()

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASS, timeout=10)
    print("Connected.")

    # Kill the duplicate (second set of PIDs)
    print("Killing duplicate join_all.py (PID 596263, 596264, 596278)...")
    ssh_exec(client, 'kill 596263 596264 596278 2>/dev/null')
    time.sleep(2)

    # Verify only one set remains
    ps = ssh_exec(client, 'ps aux | grep "join_all.py" | grep -v grep')
    print(f"Remaining processes:\n{ps}")

    # Check early log
    log = ssh_exec(client, 'tail -10 /var/log/join_groups.log 2>/dev/null')
    print(f"\nJoin log:\n{log}")

    # Also check if scraper restarted (saw new log entries)
    ps_scraper = ssh_exec(client, 'ps aux | grep "scraper.py" | grep -v grep')
    if ps_scraper:
        print(f"\nWARNING: scraper.py also running:\n{ps_scraper}")
    else:
        print("\nScraper is NOT running (good).")

    client.close()
    print("\nDone.")

if __name__ == '__main__':
    main()
