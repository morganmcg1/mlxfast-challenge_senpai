#!/usr/bin/env python3
"""Block until one PR170 probe submission reaches a terminal status.

Separate from the dispatch watcher on purpose. Dispatch arms the probe token for
a few seconds around a submit call; this script never touches the working tree,
so it is safe to run while editing research files.

The public per submission endpoint is the polling source: it carries the same
status as `mlxfast submissions` plus the `officialMetrics` block the reading
script needs, so one request settles both questions. The account scoped CLI row
is still sampled on each status change as a cross check. The full record is
written next to the arm notes once the status leaves the in flight set.

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
# The CLI colourises the status column, so an unstripped capture never matches
# IN_FLIGHT and every poll looks terminal.
ANSI = re.compile(r"\x1b\[[0-9;]*m")
POLL_SECONDS = 20.0


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
    for line in proc.stdout.splitlines():
        match = ROW.match(ANSI.sub("", line))
        if match and match.group(1) == prefix:
            return match.group(3)
    return None


def fetch_record(uuid):
    with urllib.request.urlopen(API % uuid, timeout=120) as response:
        return json.load(response)


def submission_of(record):
    """The per-submission endpoint wraps the row under a `submission` key."""
    inner = record.get("submission")
    return inner if isinstance(inner, dict) else record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("arm")
    parser.add_argument("uuid")
    parser.add_argument("--max-runtime-seconds", type=int, default=5400)
    args = parser.parse_args()

    prefix = args.uuid[:7]
    deadline = time.monotonic() + args.max_runtime_seconds
    log(f"awaiting receipt for arm {args.arm} submission {prefix}")

    record = None
    status = None
    last_logged = None
    while time.monotonic() < deadline:
        try:
            record = fetch_record(args.uuid)
        except Exception as exc:  # noqa: BLE001 - transient fetch, keep waiting
            log(f"fetch failed, retrying: {exc!r}")
            time.sleep(POLL_SECONDS)
            continue
        status = submission_of(record).get("status")
        if status not in IN_FLIGHT:
            log(f"TERMINAL {prefix} -> {status}")
            break
        if status != last_logged:
            log(f"{prefix} {status} (cli row: {row_status(prefix)!r})")
            last_logged = status
        time.sleep(POLL_SECONDS)
    else:
        log(f"deadline reached with {prefix} still {status!r}")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / f"tanjiro-pr170-receipt-{args.arm}.json"
    dest.write_text(json.dumps(record, indent=2, sort_keys=True))
    log(f"wrote {dest.relative_to(REPO)} ({dest.stat().st_size} bytes)")

    inner = submission_of(record)
    log(
        f"status={inner.get('status')} officialScore={inner.get('officialScore')} "
        f"rejectionReason={inner.get('rejectionReason')!r}"
    )
    metrics = inner.get("officialMetrics")
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
