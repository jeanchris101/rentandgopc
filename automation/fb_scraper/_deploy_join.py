"""Upload join_all.py to VPS and run it in background."""
import paramiko
import os

VPS_HOST = "144.172.100.16"
VPS_USER = "root"
VPS_PASS = "4K98JSaEoLDaP5"

LOCAL_FILE = os.path.join(os.path.dirname(__file__), "join_all.py")
REMOTE_FILE = "/opt/fb_scraper/join_all.py"
LOG_FILE = "/var/log/join_groups.log"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(VPS_HOST, username=VPS_USER, password=VPS_PASS, timeout=15)
print("Connected to VPS")

# Upload file
sftp = ssh.open_sftp()
sftp.put(LOCAL_FILE, REMOTE_FILE)
print(f"Uploaded {LOCAL_FILE} -> {REMOTE_FILE}")
sftp.close()

# Ensure /opt/data exists and log file is clean
stdin, stdout, stderr = ssh.exec_command("mkdir -p /opt/data && echo '' > " + LOG_FILE)
stdout.read()

# Kill any existing join_all.py process
stdin, stdout, stderr = ssh.exec_command("pkill -f 'python3 join_all.py' 2>/dev/null; echo done")
stdout.read()
print("Killed any existing join_all.py process")

# Run in background with nohup
cmd = (
    "cd /opt/fb_scraper && "
    "nohup xvfb-run --auto-servernum --server-args='-screen 0 1366x768x24' "
    "python3 join_all.py > /var/log/join_groups.log 2>&1 &"
)
stdin, stdout, stderr = ssh.exec_command(cmd)
stdout.read()
print("Started join_all.py in background")

# Verify it's running
import time
time.sleep(2)
stdin, stdout, stderr = ssh.exec_command("ps aux | grep 'join_all.py' | grep -v grep")
ps_out = stdout.read().decode()
if ps_out.strip():
    print("Process is running:")
    print(ps_out.strip())
else:
    print("WARNING: Process may not have started. Checking log...")
    stdin, stdout, stderr = ssh.exec_command("tail -20 " + LOG_FILE)
    print(stdout.read().decode())

# Show first few lines of log
import time
time.sleep(3)
stdin, stdout, stderr = ssh.exec_command("tail -30 " + LOG_FILE)
log_out = stdout.read().decode()
print("\nLog output so far:")
print(log_out)

ssh.close()
print("\nDone. Monitor with: ssh root@144.172.100.16 'tail -f /var/log/join_groups.log'")
