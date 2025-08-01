#!/usr/bin/env python3
"""
Keep NetEm impairment on interface ens8 except during 03:00–04:00 UTC daily.

Impairment: 520ms delay, 1% loss.
Healthy window: 03:00–04:00 UTC (no impairment).
Run with sudo (needs root to call `tc`).
"""

import subprocess
import time
import signal
import sys
from datetime import datetime, timezone, timedelta  # <--- added timedelta

IFACE = "ens8"
IMPAIR_CMD = ["tc", "qdisc", "add", "dev", IFACE, "root", "netem", "delay", "520ms", "loss", "1%"]
HEAL_CMD = ["tc", "qdisc", "del", "dev", IFACE, "root"]

# Healthy window: from 03:00 UTC inclusive to 04:00 UTC exclusive
HEALTHY_START_HOUR = 3
HEALTHY_END_HOUR = 4

CHECK_INTERVAL = 30  # seconds between reevaluating state around boundaries

def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def has_netem() -> bool:
    try:
        out = subprocess.check_output(["tc", "qdisc", "show", "dev", IFACE], text=True)
        return "netem" in out
    except subprocess.CalledProcessError:
        return False

def impair():
    if has_netem():
        return
    print(f"{datetime.now(timezone.utc).isoformat()} [+] Applying impairment")
    try:
        run(IMPAIR_CMD)
    except subprocess.CalledProcessError as e:
        print(f"    failed to apply impairment: {e}", file=sys.stderr)

def heal():
    if not has_netem():
        return
    print(f"{datetime.now(timezone.utc).isoformat()} [+] Removing impairment")
    try:
        run(HEAL_CMD)
    except subprocess.CalledProcessError as e:
        if e.returncode != 2:
            print(f"    failed to remove impairment: {e}", file=sys.stderr)

def in_healthy_window(now_utc: datetime) -> bool:
    h = now_utc.hour
    return HEALTHY_START_HOUR <= h < HEALTHY_END_HOUR

def main():
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    print("=== NetEm scheduler started (Ctrl-C to stop) ===")
    while True:
        now = datetime.now(timezone.utc)
        if in_healthy_window(now):
            heal()
            next_transition = now.replace(hour=HEALTHY_END_HOUR, minute=0, second=0, microsecond=0)
            if next_transition <= now:
                time.sleep(CHECK_INTERVAL)
            else:
                delta = (next_transition - now).total_seconds()
                print(f"    healthy window active; sleeping {int(delta)}s until {HEALTHY_END_HOUR}:00 UTC")
                time.sleep(delta + 1)
        else:
            impair()
            next_start = now.replace(hour=HEALTHY_START_HOUR, minute=0, second=0, microsecond=0)
            if next_start <= now:
                next_start += timedelta(days=1)
            delta = (next_start - now).total_seconds()
            sleep_duration = min(delta, CHECK_INTERVAL)
            time.sleep(sleep_duration)

if __name__ == "__main__":
    main()
