#!/usr/bin/env python3
"""Grab the single official submission slot as soon as it frees, then submit.

The benchmark enforces "1 submission in flight per account", and the maple
account is shared by the advisor and every student, so a naive submit races and
loses with:

    {"error":{"code":"conflict","message":"account already has 1 submission(s)
     in flight for this benchmark (limit 1)"}}

This poller watches the official list endpoint for our solver's non-terminal
receipts and fires senpai/submit-official.sh the moment there are none. It
retries on conflict, because another maple role may win the same instant.

Usage:
  python3 research/fern_r109f_submit_when_free.py \
      --base-sha <BASE_SHA> --note-file <path> \
      [--solver morganmcg1] [--interval 60] [--max-wait 5400]

Exits 0 once a submission id is accepted by the service, non-zero otherwise.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

BENCH = "1854efdf-feba-4773-bae9-b80520881a74"
URL = "https://api.mlx.fast/api/benchmarks/%s/submissions" % BENCH
TERMINAL = {"rejected", "failed", "accepted", "cancelled"}


def fetch(token):
    req = urllib.request.Request(URL, headers={"Authorization": "Bearer %s" % token})
    with urllib.request.urlopen(req, timeout=60) as fh:
        doc = json.load(fh)
    return doc["submissions"] if isinstance(doc, dict) else doc


def inflight(rows, solver):
    out = []
    for r in rows:
        if r.get("solverUsername") != solver:
            continue
        if (r.get("status") or "").lower() not in TERMINAL:
            out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-sha", required=True)
    ap.add_argument("--note-file", required=True)
    ap.add_argument("--solver", default="morganmcg1")
    ap.add_argument("--interval", type=float, default=60.0)
    ap.add_argument("--max-wait", type=float, default=5400.0)
    args = ap.parse_args()

    token = os.environ.get("MLXFAST_API_TOKEN")
    if not token:
        print("FATAL: MLXFAST_API_TOKEN not in env", flush=True)
        return 2

    # Pre-flight the note BEFORE we ever claim the shared slot.  The API rejects
    # notes under 5 KiB, and a rejected submit still consumes a draw's worth of
    # wall clock on a per-account channel shared with every other maple student.
    # Ticket 7's first launch died this way at 3676 bytes; never again.
    MIN_NOTE_BYTES = 5 * 1024
    try:
        note_bytes = os.path.getsize(args.note_file)
    except OSError as exc:
        print(f"FATAL: cannot stat --note-file {args.note_file}: {exc}", flush=True)
        return 2
    if note_bytes < MIN_NOTE_BYTES:
        print(
            f"FATAL: note {args.note_file} is {note_bytes} bytes, "
            f"below the API minimum of {MIN_NOTE_BYTES}. "
            "Refusing to launch and waste a shared slot.",
            flush=True,
        )
        return 2
    print(f"note pre-flight OK: {note_bytes} bytes >= {MIN_NOTE_BYTES}", flush=True)

    started = time.time()
    attempts = 0
    while time.time() - started < args.max_wait:
        try:
            rows = fetch(token)
        except Exception as exc:  # transient network / service errors
            print("poll error: %r (retrying)" % exc, flush=True)
            time.sleep(args.interval)
            continue

        busy = inflight(rows, args.solver)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if busy:
            for r in busy:
                print(
                    "%s slot BUSY: %s %s created=%s"
                    % (stamp, r["id"][:8], r.get("status"), r.get("createdAt")),
                    flush=True,
                )
            time.sleep(args.interval)
            continue

        attempts += 1
        print("%s slot FREE -> submitting (attempt %d)" % (stamp, attempts), flush=True)
        proc = subprocess.run(
            [
                "bash",
                "senpai/submit-official.sh",
                args.base_sha,
                "--note-file",
                args.note_file,
            ],
            capture_output=True,
            text=True,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        print(out[-4000:], flush=True)
        if proc.returncode == 0:
            ids = re.findall(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", out
            )
            print("SUBMITTED ok; candidate ids seen: %s" % (ids[-3:] or "none"), flush=True)
            return 0
        if "in flight" in out or "conflict" in out:
            print("lost the race, will retry", flush=True)
            time.sleep(args.interval)
            continue
        print("submit failed for a non-conflict reason, aborting", flush=True)
        return 1

    print("max-wait exceeded without submitting", flush=True)
    return 3


if __name__ == "__main__":
    sys.exit(main())
