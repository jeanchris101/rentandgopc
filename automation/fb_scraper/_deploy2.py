import paramiko
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

VPS = "144.172.100.16"
s = paramiko.SSHClient()
s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
s.connect(VPS, username='root', password='4K98JSaEoLDaP5', timeout=15)
print("SSH connected")

sftp = s.open_sftp()
sftp.put('C:/Claude/puntacana-properties/automation/fb_scraper/join_all.py', '/opt/fb_scraper/join_all.py')
sftp.close()
print("File uploaded")

def run(cmd, timeout=10):
    _, o, e = s.exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8', 'replace')

run('pkill -f "python3 join_all" 2>/dev/null')
run('echo > /var/log/join_groups.log')
run('mkdir -p /opt/data')

# Fire-and-forget: use transport channel
bg = 'cd /opt/fb_scraper && nohup xvfb-run --auto-servernum python3 join_all.py > /var/log/join_groups.log 2>&1 &'
transport = s.get_transport()
channel = transport.open_session()
channel.exec_command(bg)
time.sleep(2)
channel.close()
print("Script started in background")

time.sleep(5)
ps = run('ps aux | grep join_all | grep -v grep')
if ps.strip():
    print("RUNNING OK")
else:
    print("NOT RUNNING - checking log...")
    log = run('tail -10 /var/log/join_groups.log')
    print(log)
    s.close()
    sys.exit(1)

# Wait for first group search to complete
time.sleep(25)
log = run('tail -40 /var/log/join_groups.log')
print("LOG OUTPUT:")
print(log)

s.close()
