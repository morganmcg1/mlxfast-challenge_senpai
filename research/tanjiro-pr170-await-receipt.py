#!/usr/bin/env python3
"""Block until one PR170 probe submission reaches a terminal status.

Separate from the dispatch watcher on purpose. Dispatch arms the probe token for
a few seconds around a submit call; this script never touches the working tree,
so it is safe to run while editing research files.

`mlxfast submissions` is account scoped, self authenticating and not rate
limited, so it is the polling source. Once the row is terminal the full record,
including `officialMetrics`, is pulled from the public per submission endpoint
and written next to the arm notes for the reading script.

Usage
-----
    research/tanjiro-pr170-await-receipt.py <arm> <submission-uuid>

Run it under the supervised training tool, never as a terminal sleep loop.
"""

import argparse
import datetime
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "research" / "artifacts"
API = "https://api.mlx.fast/api/submissions/%s"

IN_FLIGHT = {"validating", "running", "queued", "pending", "benchmarking", "submitted"}
ROW = re.compile(r"^([0-9a-f]{7})\s+(\S+)\s+(\S+)\s")
POLL_SECONDS = 12.0


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def log(msg):
    print(f"[{now():%Y-%m-%dT%H:%M:%SZ}] {msg}", flush=True)


def row_status(prefix):
    proc = subprocess.run(
        ["mlxfast", "submissions"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if proc.returncode != 0:
        return None
    for match in map(ROW.match, proc.stdout.splitlines()):
        if match and match.group(1) == prefix:
            return match.group(3)
    return None


def fetch_record(uuid):
    with urllib.request.urlopen(API % uuid, timeout=120) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("arm")
    parser.add_argument("uuid")
    parser.add_argument("--max-runtime-seconds", type=int, default=5400)
    args = parser.parse_args()

    prefix = args.uuid[:7]
    deadline = time.monotonic() + args.max_runtime_seconds
    log(f"awaiting receipt for arm {args.arm} submission {prefix}")

    status = None
    last_logged = None
    while time.monotonic() < deadline:
        status = row_status(prefix)
        if status is None:
            log("submission row not found or listing failed; retrying")
        elif status not in IN_FLIGHT:
            log(f"TERMINAL {prefix} -> {status}")
            break
        elif status != last_logged:
            log(f"{prefix} {status}")
            last_logged = status
        time.sleep(POLL_SECONDS)
    else:
        log(f"deadline reached with {prefix} still {status}")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / f"tanjiro-pr170-receipt-{args.arm}.json"
    try:
        record = fetch_record(args.uuid)
    except Exception as exc:  # noqa: BLE001 - the status is the result that matters
        log(f"per-submission fetch failed: {exc!r}")
        return 2
    dest.write_text(json.dumps(record, indent=2, sort_keys=True))
    log(f"wrote {dest.relative_to(REPO)} ({dest.stat().st_size} bytes)")

    metrics = record.get("officialMetrics")
    log(f"status={record.get('status')} score={record.get('score')}")
    if isinstance(metrics, dict):
        for key in sorted(metrics):
            value = metrics[key]
            if not isinstance(value, (dict, list)):
                log(f"  {key} = {value}")
    else:
        log(f"  officialMetrics is {metrics!r}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
