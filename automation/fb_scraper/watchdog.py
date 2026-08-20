"""
watchdog.py — Remote watchdog for the FB scraper VPS.
Connects via SSH to check service health, detect EPIPE/crash errors,
and restart the service if needed. Logs results locally.
"""

import logging
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import paramiko
except ImportError:
    print("ERROR: paramiko not installed. Run: py -m pip install paramiko")
    sys.exit(1)

# VPS connection details
VPS_HOST = "144.172.100.16"
VPS_PORT = 22
VPS_USER = "root"
VPS_PASS = "4K98JSaEoLDaP5"

# Service and log paths
SERVICE_NAME = "fb-scraper.service"
SCRAPER_LOG = "/var/log/scraper_run.log"

# Crash patterns to look for in logs
CRASH_PATTERNS = [
    r"EPIPE",
    r"write EPIPE",
    r"broken pipe",
    r"Browser has been closed",
    r"Target closed",
    r"Protocol error",
    r"Connection closed",
    r"browser disconnected",
    r"BROWSER CRASH",
    r"OOM",
    r"out of memory",
    r"Killed",
    r"SIGKILL",
    r"SIGSEGV",
]

# Local log file
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "watchdog.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("watchdog")


def ssh_connect():
    """Create SSH connection to VPS."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(VPS_HOST, port=VPS_PORT, username=VPS_USER, password=VPS_PASS, timeout=15)
    return client


def run_cmd(client, cmd: str) -> tuple[str, str, int]:
    """Run a command over SSH and return (stdout, stderr, exit_code)."""
    stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
    exit_code = stdout.channel.recv_exit_status()
    return stdout.read().decode("utf-8", errors="replace"), stderr.read().decode("utf-8", errors="replace"), exit_code


def check_service_status(client) -> dict:
    """Check if fb-scraper.service is active."""
    out, err, code = run_cmd(client, f"systemctl is-active {SERVICE_NAME}")
    status = out.strip()

    # Get more details
    out2, _, _ = run_cmd(client, f"systemctl show {SERVICE_NAME} --property=ActiveState,SubState,NRestarts,ExecMainStartTimestamp")
    props = {}
    for line in out2.strip().split("\n"):
        if "=" in line:
            key, val = line.split("=", 1)
            props[key.strip()] = val.strip()

    return {
        "active": status == "active",
        "status": status,
        "state": props.get("ActiveState", "unknown"),
        "sub_state": props.get("SubState", "unknown"),
        "restarts": props.get("NRestarts", "0"),
        "start_time": props.get("ExecMainStartTimestamp", "unknown"),
    }


def check_recent_crashes(client, minutes: int = 15) -> list[str]:
    """Check scraper log for crash-related errors in the last N minutes."""
    # Get log lines from the last N minutes
    # Use journalctl for systemd logs AND check the scraper log file
    crashes = []

    # Check journalctl for service crashes
    out, _, _ = run_cmd(client, f"journalctl -u {SERVICE_NAME} --since '{minutes} min ago' --no-pager -q 2>/dev/null || echo ''")
    for line in out.split("\n"):
        line_lower = line.lower()
        for pattern in CRASH_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                crashes.append(f"[journalctl] {line.strip()}")
                break

    # Check the scraper log file
    out2, _, _ = run_cmd(client, f"tail -200 {SCRAPER_LOG} 2>/dev/null || echo ''")
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    for line in out2.split("\n"):
        line_lower = line.lower()
        for pattern in CRASH_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                crashes.append(f"[scraper_log] {line.strip()}")
                break

    return crashes


def restart_service(client) -> bool:
    """Restart the fb-scraper service."""
    log.info(f"Restarting {SERVICE_NAME}...")
    _, err, code = run_cmd(client, f"systemctl restart {SERVICE_NAME}")
    if code == 0:
        log.info(f"Service restarted successfully")
        return True
    else:
        log.error(f"Failed to restart service: {err}")
        return False


def check_system_health(client) -> dict:
    """Check VPS memory and disk usage."""
    # Memory
    out, _, _ = run_cmd(client, "free -m | grep Mem")
    mem = {}
    parts = out.split()
    if len(parts) >= 4:
        mem = {
            "total_mb": int(parts[1]),
            "used_mb": int(parts[2]),
            "free_mb": int(parts[3]),
        }

    # Disk
    out2, _, _ = run_cmd(client, "df -h / | tail -1")
    disk = {}
    parts2 = out2.split()
    if len(parts2) >= 5:
        disk = {
            "size": parts2[1],
            "used": parts2[2],
            "avail": parts2[3],
            "use_pct": parts2[4],
        }

    return {"memory": mem, "disk": disk}


def main():
    log.info("=" * 50)
    log.info("FB Scraper Watchdog Check")
    log.info("=" * 50)

    try:
        client = ssh_connect()
        log.info(f"Connected to {VPS_HOST}")
    except Exception as e:
        log.error(f"SSH connection failed: {e}")
        return

    try:
        # 1. Check service status
        status = check_service_status(client)
        log.info(f"Service status: {status['status']} (restarts: {status['restarts']}, started: {status['start_time']})")

        # 2. Check for recent crashes
        crashes = check_recent_crashes(client, minutes=15)
        if crashes:
            log.warning(f"Found {len(crashes)} crash-related log entries in last 15 min:")
            for c in crashes[:10]:  # Show max 10
                log.warning(f"  {c[:200]}")

        # 3. Check system health
        health = check_system_health(client)
        if health["memory"]:
            mem = health["memory"]
            log.info(f"Memory: {mem['used_mb']}MB / {mem['total_mb']}MB used ({mem['free_mb']}MB free)")
        if health["disk"]:
            disk = health["disk"]
            log.info(f"Disk: {disk['used']} / {disk['size']} ({disk['use_pct']} used)")

        # 4. Take action if needed
        needs_restart = False

        if not status["active"]:
            log.warning(f"Service is DOWN (status: {status['status']}) — restarting")
            needs_restart = True

        if crashes and status["active"]:
            # Service is running but had crashes — check if it's in a crash loop
            restart_count = int(status.get("restarts", "0"))
            if restart_count > 5:
                log.warning(f"Service has restarted {restart_count} times — possible crash loop")
            # Recent crashes while active means systemd auto-restarted. Log but don't restart again.
            log.info("Service is active despite recent crashes (systemd auto-restart working)")

        if needs_restart:
            success = restart_service(client)
            if success:
                # Verify it came back
                import time
                time.sleep(5)
                status2 = check_service_status(client)
                if status2["active"]:
                    log.info("Service confirmed running after restart")
                else:
                    log.error(f"Service failed to start: {status2['status']}")

        if not crashes and status["active"]:
            log.info("All clear — service is healthy, no recent crashes")

    except Exception as e:
        log.error(f"Watchdog check failed: {e}")
    finally:
        client.close()
        log.info("Disconnected from VPS")


if __name__ == "__main__":
    main()
