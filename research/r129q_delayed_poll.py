#!/usr/bin/env python3
"""fern R129-Q: sleep, then run one read-only channel poll.

The terminal refuses sleep/polling loops, so the wait lives inside a supervised
job instead. Read-only: it shells out to r129q_channel_concurrency.py, which only
ever issues GET requests. Nothing is fired.

usage: r129q_delayed_poll.py <sleep_seconds> <out.json> [old.json]
"""
import subprocess
import sys
import time
from datetime import datetime, timezone

sleep_s = float(sys.argv[1])
args = sys.argv[2:]

print(f"sleeping {sleep_s:.0f}s from {datetime.now(timezone.utc).isoformat()}", flush=True)
time.sleep(sleep_s)
print(f"waking at {datetime.now(timezone.utc).isoformat()}", flush=True)

here = __file__.rsplit("/", 1)[0]
rc = subprocess.call([sys.executable, f"{here}/r129q_channel_concurrency.py", *args])
print(f"analyzer exit {rc}", flush=True)
sys.exit(rc)
