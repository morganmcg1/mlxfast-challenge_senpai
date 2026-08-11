#!/usr/bin/env python3
"""Poll `mlxfast submissions --all` and record state transitions with wall-clock
timestamps, so submission-channel service time can be measured instead of guessed.

Usage:
  python3 senpai/tools/queue_probe.py --minutes 28 --interval 90 --out /tmp/queue_probe.jsonl

Output: one JSON object per poll containing the observed non-terminal set plus any
transition detected since the previous poll (submission id, prior state, new state,
creation time, observed service time in minutes).

Why this exists: on 2026-08-11 the advisor broadcast an arrival/throughput estimate
derived from two widely spaced polls. That method cannot distinguish a growing
backlog from a closed loop in which every solver holds exactly one in-flight
submission. Transition timestamps settle it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time

TERMINAL = {"promoted", "rejected", "failed"}
ROW = re.compile(
    r"^([0-9a-f]{7})\s+(\S+)\s+(promoted|rejected|failed|validating|queued|running|pending)\s+(.*)$"
)
CREATED = re.compile(r"(\d+/\d+/\d+,\s+\d+:\d+\s+[AP]M)\s*$")
# The CLI colours the status column; strip ANSI before matching or every row misses.
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def poll() -> dict[str, dict[str, str]]:
    out = subprocess.run(
        ["mlxfast", "submissions", "--all"],
        capture_output=True,
        text=True,
        timeout=240,
    ).stdout
    rows: dict[str, dict[str, str]] = {}
    for line in out.splitlines():
        m = ROW.match(ANSI.sub("", line).strip())
        if not m:
            continue
        sid, solver, status, rest = m.groups()
        c = CREATED.search(rest.strip())
        rows[sid] = {
            "solver": solver,
            "status": status,
            "created": c.group(1) if c else "",
        }
    return rows


def parse_created(s: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(s, "%m/%d/%y, %I:%M %p")
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=28.0)
    ap.add_argument("--interval", type=float, default=90.0)
    ap.add_argument("--out", default="/tmp/queue_probe.jsonl")
    args = ap.parse_args()

    deadline = time.time() + args.minutes * 60.0
    prev: dict[str, dict[str, str]] = {}
    with open(args.out, "a", buffering=1) as fh:
        while time.time() < deadline:
            now = dt.datetime.now(dt.timezone.utc)
            try:
                rows = poll()
            except Exception as exc:  # noqa: BLE001
                fh.write(json.dumps({"t": now.isoformat(), "error": str(exc)}) + "\n")
                time.sleep(args.interval)
                continue

            pending = {
                sid: r for sid, r in rows.items() if r["status"] not in TERMINAL
            }
            transitions = []
            arrivals = []
            for sid, r in rows.items():
                if sid not in prev:
                    if prev and r["status"] not in TERMINAL:
                        arrivals.append({"id": sid, **r})
                    continue
                if prev[sid]["status"] != r["status"]:
                    created = parse_created(r["created"])
                    svc = None
                    if created is not None:
                        svc = round(
                            (now.replace(tzinfo=None) - created).total_seconds() / 60.0, 1
                        )
                    transitions.append(
                        {
                            "id": sid,
                            "solver": r["solver"],
                            "from": prev[sid]["status"],
                            "to": r["status"],
                            "created": r["created"],
                            "observed_service_min_upper_bound": svc,
                        }
                    )
            rec = {
                "t": now.isoformat(),
                "n_pending": len(pending),
                "n_distinct_pending_solvers": len({r["solver"] for r in pending.values()}),
                "pending": [
                    {"id": sid, "solver": r["solver"], "created": r["created"]}
                    for sid, r in sorted(pending.items(), key=lambda kv: kv[1]["created"])
                ],
                "transitions": transitions,
                "arrivals": arrivals,
            }
            fh.write(json.dumps(rec) + "\n")
            print(
                f"{now:%H:%M:%S}Z pending={len(pending)} "
                f"solvers={rec['n_distinct_pending_solvers']} "
                f"transitions={len(transitions)} arrivals={len(arrivals)}",
                flush=True,
            )
            for tr in transitions:
                print("  TRANSITION " + json.dumps(tr), flush=True)
            for ar in arrivals:
                print("  ARRIVAL " + json.dumps(ar), flush=True)
            prev = rows
            time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
