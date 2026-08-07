#!/usr/bin/env python3
"""Dispatch one PR170 probe arm the moment this account's in-flight slot clears.

Why a watcher is needed
-----------------------
The `morganmcg1` account is shared by four Senpai students and the benchmark
permits one in-flight submission per account. Measured handoff gaps between one
receipt completing and the next claim, taken from the account's own history, are
6, 25, 29, 38 and 45 seconds. An agent that checks the queue and then decides
never wins that race, because a single conversation turn is far longer than the
gap.

The submit endpoint is separately rate limited to five attempts per clock hour,
resetting on the hour. Two rate-limit replies observed at 01:32:28Z and 01:37:15Z
named retry-after values of 1651 s and 1362 s, both landing on 01:59:5xZ, and the
second attempt did not push the deadline out. So retrying blindly is useless: it
burns the hourly budget without improving the odds, and an exhausted budget at
the moment the slot opens costs a whole cycle.

The winning strategy is therefore to poll a *free* status source frequently and
spend a rate-limited submit attempt only when the slot is genuinely free.
`mlxfast submissions` is that source: it is scoped to this account, it needs no
API token of its own, and one call takes about nine seconds, which paces the loop
without hammering anything.

Safety properties
-----------------
* `mlxfast submit` packages the working tree rather than git HEAD, so the three
  submitted paths are verified byte-identical to HEAD before anything is armed.
* The probe token is written immediately before a submit call and reverted
  immediately after it returns, on every exit path. The armed window is seconds
  rather than the lifetime of the watcher, which bounds the damage if the process
  is killed uncleanly.
* The loop stops on the first accepted submission, so a receipt is never spent
  twice, and it refuses to start if a probe token is already present.

Usage
-----
    research/tanjiro-pr170-dispatch.py m2 [--max-runtime-seconds N]

Run it under the supervised training tool, never as a terminal sleep loop.
"""

import argparse
import datetime
import pathlib
import re
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
SELECTOR = "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp"
HEADER = "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h"
GENERATED = "Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp"
SUBMITTED_PATHS = (SELECTOR, HEADER, GENERATED)

DISARMED = 'kNaxGatherProbeDefault = ""'
ARMED = 'kNaxGatherProbeDefault = "%s"'

# One submission per account may be in flight. The slot is free only when every
# row has reached a status known to be terminal; anything else -- including a
# status token this script has never seen -- counts as in flight. Guessing
# "free" wrongly costs a conflict and an account-wide rate-limit attempt shared
# with three other students, while guessing "busy" wrongly only costs waiting.
TERMINAL = {"promoted", "rejected", "failed", "accepted", "error", "cancelled"}
ROW = re.compile(r"^([0-9a-f]{7})\s+(\S+)\s+(\S+)\s")
# `mlxfast submissions` colours the status column, so the raw third field looks
# like "\x1b[36mvalidating\x1b[39m" and never compares equal to a bare token.
ANSI = re.compile(r"\x1b\[[0-9;]*m")

POLL_SECONDS = 3.0  # on top of the ~9 s each `mlxfast submissions` call costs


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def log(msg):
    print(f"[{now():%Y-%m-%dT%H:%M:%SZ}] {msg}", flush=True)


def git(*args):
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=False
    )


def submitted_surface_dirty():
    return git("status", "--porcelain", "--", *SUBMITTED_PATHS).stdout.strip()


def arm(token):
    path = REPO / SELECTOR
    text = path.read_text()
    if DISARMED not in text:
        raise RuntimeError(f"disarmed probe default not found in {SELECTOR}")
    path.write_text(text.replace(DISARMED, ARMED % token, 1))


def restore():
    git("checkout", "--", SELECTOR)
    dirty = submitted_surface_dirty()
    if dirty:
        log(f"!!! submitted surface still dirty after restore: {dirty}")
        return False
    return True


def slot_state():
    """Return (free, detail). `free` is None when the status could not be read."""
    proc = subprocess.run(
        ["mlxfast", "submissions"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if proc.returncode != 0:
        return None, f"mlxfast submissions exited {proc.returncode}"
    lines = ANSI.sub("", proc.stdout).splitlines()
    rows = [(m.group(1), m.group(3)) for m in map(ROW.match, lines) if m]
    if not rows:
        return None, "no submission rows parsed"
    busy = [r for r in rows if r[1] not in TERMINAL]
    if busy:
        return False, f"{busy[-1][0]} {busy[-1][1]}"
    return True, f"newest {rows[-1][0]} {rows[-1][1]}"


def attempt_submit(arm_name, note):
    """Arm, submit, disarm. Returns (outcome, text)."""
    arm(arm_name)
    try:
        proc = subprocess.run(
            ["mlxfast", "submit", "--model", "senpai", "--note-file", note],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
        out = "\n".join(
            line
            for line in (proc.stdout + proc.stderr).splitlines()
            if line.strip() and not line.startswith("Pushing traces")
        )
    finally:
        restore()

    if '"code":"conflict"' in out:
        return "conflict", out
    if "Rate limit reached" in out:
        return "rate-limited", out
    if proc.returncode != 0:
        return "error", out
    return "submitted", out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("arm", choices=["m2", "s2", "b2", "s3"])
    parser.add_argument("--max-runtime-seconds", type=int, default=3480)
    args = parser.parse_args()

    note = f"research/artifacts/tanjiro-pr170-note-{args.arm}.md"
    if not (REPO / note).is_file():
        log(f"missing note file {note}")
        return 2

    dirty = submitted_surface_dirty()
    if dirty:
        log(f"refusing to start, submitted surface is dirty:\n{dirty}")
        return 3
    if DISARMED not in (REPO / SELECTOR).read_text():
        log("refusing to start, probe default is not disarmed at HEAD")
        return 3

    deadline = time.monotonic() + args.max_runtime_seconds
    log(f"watching for a free slot to dispatch arm {args.arm} with note {note}")

    cooldown_until = 0.0
    was_free = None
    while time.monotonic() < deadline:
        free, detail = slot_state()
        if free is None:
            log(f"status unavailable ({detail}); retrying")
        elif not free:
            if was_free is not False:
                log(f"slot busy: {detail}")
            was_free = False
        else:
            if was_free is not True:
                log(f"slot FREE: {detail}")
            was_free = True
            remaining = cooldown_until - time.monotonic()
            if remaining > 0:
                log(f"slot free but rate limited for another {remaining:.0f} s")
            else:
                outcome, out = attempt_submit(args.arm, note)
                log(f"submit -> {outcome}: {out}")
                if outcome == "submitted":
                    log(f"DISPATCHED arm {args.arm}")
                    return 0
                if outcome == "conflict":
                    # The status source said free and the server disagreed. Back
                    # off rather than retrying every poll, because each attempt
                    # spends from an hourly budget shared across the account.
                    cooldown_until = time.monotonic() + 120
                    log("slot was not actually free; backing off 120 s")
                elif outcome == "rate-limited":
                    m = re.search(r"in (\d+) seconds", out)
                    wait = int(m.group(1)) if m else 300
                    cooldown_until = time.monotonic() + wait
                    log(f"hourly submit budget exhausted; next attempt in {wait} s")
                elif outcome == "error":
                    log("unrecognised submit response; stopping rather than guessing")
                    return 4
        time.sleep(POLL_SECONDS)

    log(f"deadline reached without dispatching arm {args.arm}")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        restore()
        sys.exit(130)
