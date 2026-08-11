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
import re
import subprocess
import sys
import time

NON_TERMINAL = ("validating", "queued", "running", "pending", "evaluating")
TERMINAL = ("rejected", "accepted", "failed", "scored", "completed", "promoted")

# BUGFIX 2026-08-11T00:10Z. `mlxfast submissions` colourises the status column,
# so the raw third whitespace field is "\x1b[31mrejected\x1b[39m", which matched
# NEITHER tuple above. The 2026-08-10T23:31Z watcher run therefore logged
# "UNUSABLE POLL" on all 29 minutes of polls and COULD NOT HAVE FIRED. Strip
# SGR sequences before classifying. Lesson: an alarm whose "cannot classify"
# branch is silent-by-design is indistinguishable from an alarm that is working.
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


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
    rows = [ln for ln in strip_ansi(out.stdout).splitlines() if ln.strip()]
    if not rows:
        return ("ERROR empty output", "unknown")
    last = rows[-1]
    fields = last.split()
    status = fields[2].strip().lower() if len(fields) > 2 else "unknown"
    return (last[:160], status)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=120.0)
    ap.add_argument("--idle-exit-polls", type=int, default=3)
    ap.add_argument("--max-minutes", type=float, default=90.0)
    ap.add_argument("--unusable-exit-polls", type=int, default=3)
    ap.add_argument(
        "--selftest",
        action="store_true",
        help="classify one live poll and exit; regression guard for the ANSI bug",
    )
    args = ap.parse_args()

    if args.selftest:
        row, status = poll()
        ok = status in NON_TERMINAL or status in TERMINAL
        print(f"selftest status={status!r} classified={ok} | {row}", flush=True)
        return 0 if ok else 2

    deadline = time.time() + args.max_minutes * 60.0
    idle_streak = 0
    unusable_streak = 0

    while time.time() < deadline:
        row, status = poll()
        if status in NON_TERMINAL:
            idle_streak = 0
        elif status in TERMINAL:
            idle_streak += 1
        else:
            # Unrecognised status (e.g. an auth failure) is NOT evidence of an
            # idle queue, so it must not raise the IDLE alarm. But it must not
            # be silent either: the 23:31Z run spent 29 minutes here and looked
            # healthy. Fail loudly after a few consecutive unusable polls.
            unusable_streak += 1
            print(
                f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] "
                f"UNUSABLE POLL #{unusable_streak} status={status!r} | {row}",
                flush=True,
            )
            if unusable_streak >= args.unusable_exit_polls:
                print(
                    "ALARM (BLIND): the watcher cannot classify submission "
                    f"status after {unusable_streak} consecutive polls. It is "
                    "NOT reporting an idle queue -- it is reporting that it "
                    "can no longer tell. Inspect `mlxfast submissions` by hand.",
                    flush=True,
                )
                return 2
            time.sleep(args.interval)
            continue
        unusable_streak = 0
        print(
            f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] "
            f"status={status} idle_streak={idle_streak} | {row}",
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
