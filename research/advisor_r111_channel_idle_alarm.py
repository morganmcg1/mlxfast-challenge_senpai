#!/usr/bin/env python3
"""Round-111 channel-idle alarm.

The single largest measured loss of this campaign was an idle official
submission queue (8/10 11:05 AM -> 11:03 PM, ~12 h, ~32 unfired shots).
This watcher polls `mlxfast submissions` and EXITS as soon as the queue has
held no non-terminal submission for `--idle-exit-polls` consecutive polls,
so the supervising advisor conversation is woken and can chase the dispatcher.

Read-only: it never submits anything.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

NON_TERMINAL = ("validating", "queued", "running", "pending", "evaluating")


def poll() -> tuple[str, str]:
    """Return (last_row, status_word) for the newest submission row."""
    out = subprocess.run(
        ["mlxfast", "submissions"],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if out.returncode != 0:
        return (f"ERROR rc={out.returncode} {out.stderr.strip()[:200]}", "unknown")
    rows = [ln for ln in out.stdout.splitlines() if ln.strip()]
    if not rows:
        return ("ERROR empty output", "unknown")
    last = rows[-1]
    fields = last.split()
    status = fields[2] if len(fields) > 2 else "unknown"
    return (last[:160], status)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=120.0)
    ap.add_argument("--idle-exit-polls", type=int, default=3)
    ap.add_argument("--max-minutes", type=float, default=90.0)
    args = ap.parse_args()

    deadline = time.time() + args.max_minutes * 60.0
    idle_streak = 0

    while time.time() < deadline:
        row, status = poll()
        busy = status in NON_TERMINAL
        idle_streak = 0 if busy else idle_streak + 1
        print(
            f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] "
            f"status={status} busy={busy} idle_streak={idle_streak} | {row}",
            flush=True,
        )
        if idle_streak >= args.idle_exit_polls:
            print(
                "ALARM: official submission queue has been terminal/idle for "
                f"{idle_streak} consecutive polls "
                f"(~{idle_streak * args.interval / 60.0:.1f} min). "
                "A shot is being wasted every ~22 min. Chase maple-fern or "
                "fire an honest nonce-variant replay.",
                flush=True,
            )
            return 0
        time.sleep(args.interval)

    print("watcher window elapsed with the queue busy; no idle alarm", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
