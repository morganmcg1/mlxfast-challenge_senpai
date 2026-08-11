#!/usr/bin/env python3
"""r116 -- block until the morganmcg1 submission slot is free, then exit 0.

Only one submission per account may be in flight.  The in-flight status word is
``validating`` (never ``pending``/``running``/``queued``).  This poller reads the
receipt feed directly rather than shelling out to ``mlxfast submissions``,
because that CLI intermittently returns a single empty line with exit 0 and a
poller must never mistake that for "slot free".

Exit codes::

    0  slot is free -- fire now
    2  timed out with the slot still busy
    3  the feed could not be read enough times to be trusted
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BENCH = os.environ.get("MLXFAST_BENCHMARK_REF", "eigenlabs/mlxfast-challenge")
API = os.environ.get("MLXFAST_API_URL", "https://api.mlx.fast").rstrip("/")
SOLVER = "morganmcg1"
IN_FLIGHT = "validating"


def fetch() -> list:
    token = os.environ.get("MLXFAST_API_TOKEN", "")
    if not token:
        raise RuntimeError("MLXFAST_API_TOKEN is not set")
    url = f"{API}/api/benchmarks/{urllib.parse.quote(BENCH, safe='')}/submissions"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("submissions", [])
    if not isinstance(payload, list):
        raise RuntimeError(f"unexpected feed shape: {type(payload).__name__}")
    return payload


def main() -> int:
    interval = float(os.environ.get("R116_INTERVAL", "45"))
    max_minutes = float(os.environ.get("R116_MAX_MINUTES", "26"))
    deadline = time.time() + max_minutes * 60.0
    consecutive_failures = 0

    while True:
        try:
            rows = fetch()
            consecutive_failures = 0
        except (urllib.error.URLError, RuntimeError, ValueError, TimeoutError) as exc:
            consecutive_failures += 1
            print(f"[{time.strftime('%H:%M:%SZ', time.gmtime())}] feed read failed "
                  f"({consecutive_failures}): {exc}", flush=True)
            if consecutive_failures >= 6:
                return 3
            time.sleep(interval)
            continue

        mine = [r for r in rows if r.get("solverUsername") == SOLVER]
        busy = [r for r in mine if str(r.get("status", "")).lower() == IN_FLIGHT]
        stamp = time.strftime("%H:%M:%SZ", time.gmtime())
        if not busy:
            recent = sorted(mine, key=lambda r: str(r.get("createdAt", "")))[-1:]
            last = recent[0] if recent else {}
            print(f"[{stamp}] SLOT FREE -- feed={len(rows)} mine={len(mine)} "
                  f"last={str(last.get('id',''))[:7]} status={last.get('status')} "
                  f"score={last.get('officialScore')}", flush=True)
            return 0
        ids = ",".join(str(r.get("id", ""))[:7] for r in busy)
        print(f"[{stamp}] busy: {len(busy)} in flight ({ids}); feed={len(rows)}",
              flush=True)

        if time.time() >= deadline:
            print(f"[{stamp}] TIMEOUT with slot still busy", flush=True)
            return 2
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
