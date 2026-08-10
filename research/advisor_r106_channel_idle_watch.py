#!/usr/bin/env python3
"""Exit as soon as the shared official submit channel goes IDLE.

WHY THIS EXISTS
---------------
Round-106 measurement (advisor): the official channel is NOT a per-account
quota with a lockout.  It is a **serial validation queue**.  Eleven receipts
landed under `morganmcg1` between 03:52Z and 07:53Z on 2026-08-10 at a very
regular cadence -- inter-arrival 15-36 min, median ~22 min -- and at every
instant at most ONE submission is in a non-terminal state.  A submit issued
while another submission is non-terminal fails on conflict, and per #597 §13.3
that failed attempt still costs something.  That, and not a quota, is why
frieren's 14-attempt retry loop landed 0 receipts: the queue was ~100 %
occupied by our own r104-A and r105-A ladders.

So the correct protocol is not "retry until it works".  It is:

    watch until IDLE  ->  one single attempt  ->  stop.

This script is the "watch until IDLE" half.  It is READ-ONLY: it never submits.
It exits 0 the first time the account has no non-terminal submission, and exits
2 if it hits its deadline while the queue is still busy.  Run it as a Senpai
job so the wake is event-driven rather than a foreground poll loop.

Usage:
    python3 research/advisor_r106_channel_idle_watch.py [--poll 60]
                                                        [--deadline-min 50]
                                                        [--who morganmcg1]
                                                        [--require-idle-polls 1]
"""
import argparse
import json
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"
BASE = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")

# Anything not in this set is treated as still occupying the queue.
TERMINAL = {"rejected", "accepted", "failed", "error", "cancelled", "canceled",
            "completed", "complete", "succeeded", "success", "scored", "done"}


def token():
    t = os.environ.get("MLXFAST_API_TOKEN")
    if t:
        return t
    p = pathlib.Path.home() / ".config" / "mlxfast" / "config.json"
    if p.exists():
        return json.loads(p.read_text()).get("token")
    return None


def get(url, tok):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def ts_of(s):
    m = s.get("officialMetrics")
    if isinstance(m, dict) and m.get("timestamp"):
        return str(m["timestamp"])
    return str(s.get("createdAt") or s.get("updatedAt") or "")


def busy_rows(subs, who):
    out = []
    for s in subs:
        if s.get("solverUsername") != who:
            continue
        st = str(s.get("status") or "").strip().lower()
        if st not in TERMINAL:
            out.append((ts_of(s), st, str(s.get("submissionCommitSha") or "")[:12],
                        (s.get("note") or "").splitlines()[:1]))
    out.sort()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poll", type=float, default=60.0)
    ap.add_argument("--deadline-min", type=float, default=50.0)
    ap.add_argument("--who", default="morganmcg1")
    ap.add_argument("--require-idle-polls", type=int, default=1,
                    help="consecutive idle observations before declaring IDLE")
    a = ap.parse_args()

    tok = token()
    if not tok:
        print("no MLXFAST_API_TOKEN available", file=sys.stderr)
        return 3

    b = get(f"{BASE}/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}", tok)
    bid = (b.get("benchmark") or b)["id"]
    url = f"{BASE}/api/benchmarks/{bid}/submissions"

    t0 = time.time()
    deadline = t0 + a.deadline_min * 60.0
    idle_streak = 0
    n = 0

    while time.time() < deadline:
        n += 1
        try:
            subs = get(url, tok)
        except Exception as e:                      # transient API blip
            print(f"[{n:03d}] poll error: {e!r}", flush=True)
            time.sleep(a.poll)
            continue
        if isinstance(subs, dict):
            subs = subs.get("submissions", subs.get("data", []))

        busy = busy_rows(subs, a.who)
        el = (time.time() - t0) / 60.0
        if busy:
            idle_streak = 0
            for ts, st, sha, note in busy:
                print(f"[{n:03d} t+{el:5.1f}m] BUSY  {ts}  {st}  {sha}  {note}",
                      flush=True)
        else:
            idle_streak += 1
            print(f"[{n:03d} t+{el:5.1f}m] IDLE  (streak {idle_streak}/"
                  f"{a.require_idle_polls})", flush=True)
            if idle_streak >= a.require_idle_polls:
                print("\nCHANNEL IDLE -- the queue has no non-terminal "
                      "submission for this account.\n"
                      "Release the hold and fire EXACTLY ONE attempt.",
                      flush=True)
                return 0
        time.sleep(a.poll)

    print(f"\nDEADLINE ({a.deadline_min:.0f} min) reached with the queue still "
          f"busy. Channel NOT released.", flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
