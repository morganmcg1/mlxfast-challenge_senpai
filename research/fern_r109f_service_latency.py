#!/usr/bin/env python3
"""Bracket the official channel's *service* time from a series of cache snapshots.

Why this exists
---------------
A submission row carries `createdAt` but no `updatedAt`, so the leaderboard API
never tells you how long validation actually took.  Every latency number I had
before this tool was an *inter-arrival* gap between consecutive `createdAt`
values for one solver -- which, under a 1-in-flight-per-account limit, is
service time PLUS whatever idle time the solver left on the table.  That
conflation is exactly the kind of thing that has burned this campaign before
(see CORRECTION 4: a ratio whose denominator was a small-sample noise
estimate).  So: measure the thing directly.

Method
------
Each cached snapshot file is an observation of the whole table at a known wall
time -- the file's mtime.  For a row that is non-terminal in an early snapshot
and terminal in a later one, the completion instant is bracketed by those two
observation times.  Subtract `createdAt` and you get a bracketed service
duration:

    lo = t_last_seen_nonterminal - createdAt      (it was still running then)
    hi = t_first_seen_terminal   - createdAt      (it had finished by then)

Rows still non-terminal in the newest snapshot give a one-sided lower bound
(`>= age`), which is reported separately and is the load signal that matters
most when the queue is backing up.

Rows that were never observed while non-terminal (created and finished inside a
single inter-snapshot gap) yield only `hi`; they are counted but excluded from
the bracketed statistics, because including them would bias the estimate
downward -- they are precisely the fast ones.

Usage
-----
    python3 research/fern_r109f_service_latency.py                # all /tmp/subs_p*.json
    python3 research/fern_r109f_service_latency.py --since 07:00  # busy regime only
    python3 research/fern_r109f_service_latency.py --solver morganmcg1
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import statistics
import sys

TERMINAL = {"rejected", "failed", "accepted", "cancelled"}
NONTERMINAL = {"queued", "validating"}


def parse_iso(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_snapshots(patterns: list[str]) -> list[tuple[dt.datetime, str, dict]]:
    """Return [(observed_at, path, {id: status})] sorted by observation time."""
    snaps = []
    seen_paths = set()
    for pat in patterns:
        for path in glob.glob(pat):
            if path in seen_paths:
                continue
            seen_paths.add(path)
            try:
                with open(path) as fh:
                    rows = json.load(fh)["submissions"]
            except Exception as exc:  # noqa: BLE001
                print(f"  skip {path}: {exc}", file=sys.stderr)
                continue
            observed = dt.datetime.fromtimestamp(os.path.getmtime(path), dt.timezone.utc)
            snaps.append((observed, path, rows))
    snaps.sort(key=lambda t: t[0])
    return snaps


def pct(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    idx = q / 100.0 * (len(s) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def describe(name: str, values: list[float]) -> None:
    if not values:
        print(f"  {name:28s} n=0")
        return
    print(
        f"  {name:28s} n={len(values):3d}  "
        f"median={statistics.median(values):7.2f}  mean={statistics.fmean(values):7.2f}  "
        f"p10={pct(values, 10):7.2f}  p90={pct(values, 90):7.2f}  "
        f"min={min(values):7.2f}  max={max(values):7.2f}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", action="append", default=None,
                    help="snapshot glob (repeatable); default /tmp/subs_p*.json")
    ap.add_argument("--solver", default=None, help="restrict to one solverUsername")
    ap.add_argument("--since", default=None,
                    help="only rows created at/after this UTC time (HH:MM or full ISO)")
    ap.add_argument("--split", default=None,
                    help="UTC HH:MM boundary; report two regimes around it")
    args = ap.parse_args()

    patterns = args.glob or ["/tmp/subs_p*.json", "/tmp/subs_poll.json"]
    snaps = load_snapshots(patterns)
    if len(snaps) < 2:
        print("need at least two snapshots", file=sys.stderr)
        return 2

    print("=== snapshots (observation time = file mtime) ===")
    for observed, path, rows in snaps:
        nonterm = sum(1 for r in rows if r["status"] in NONTERMINAL)
        print(f"  {observed:%Y-%m-%dT%H:%M:%SZ}  rows={len(rows):5d}  non-terminal={nonterm:3d}  {os.path.basename(path)}")
    gaps = [(snaps[i + 1][0] - snaps[i][0]).total_seconds() / 60 for i in range(len(snaps) - 1)]
    print(f"  inter-snapshot gaps (min): min={min(gaps):.1f} median={statistics.median(gaps):.1f} max={max(gaps):.1f}")

    day = snaps[-1][0].date()

    def cut(spec: str) -> dt.datetime:
        if len(spec) <= 5 and ":" in spec:
            h, m = spec.split(":")
            return dt.datetime.combine(day, dt.time(int(h), int(m)), dt.timezone.utc)
        return parse_iso(spec)

    since = cut(args.since) if args.since else None

    # ---- fold the snapshot series into per-row observation windows -------------
    created: dict[str, dt.datetime] = {}
    solver: dict[str, str] = {}
    last_nonterm: dict[str, dt.datetime] = {}
    first_term: dict[str, dt.datetime] = {}
    ever_nonterm: set[str] = set()
    final_status: dict[str, str] = {}

    for observed, _path, rows in snaps:
        for r in rows:
            rid = r["id"]
            created.setdefault(rid, parse_iso(r["createdAt"]))
            solver.setdefault(rid, r["solverUsername"])
            st = r["status"]
            final_status[rid] = st
            if st in NONTERMINAL:
                ever_nonterm.add(rid)
                last_nonterm[rid] = observed
            elif rid not in first_term:
                first_term[rid] = observed

    def keep(rid: str) -> bool:
        if args.solver and solver[rid] != args.solver:
            return False
        if since and created[rid] < since:
            return False
        return True

    bracketed: list[tuple[str, str, dt.datetime, float, float]] = []
    onesided: list[tuple[str, str, dt.datetime, float]] = []
    unobserved = 0
    for rid in created:
        if not keep(rid):
            continue
        c = created[rid]
        if rid in ever_nonterm and rid in first_term and first_term[rid] > last_nonterm[rid]:
            lo = (last_nonterm[rid] - c).total_seconds() / 60
            hi = (first_term[rid] - c).total_seconds() / 60
            bracketed.append((rid, solver[rid], c, lo, hi))
        elif rid in ever_nonterm and rid not in first_term:
            onesided.append((rid, solver[rid], c, (last_nonterm[rid] - c).total_seconds() / 60))
        elif rid in first_term:
            unobserved += 1

    print("\n=== bracketed service times (non-terminal in one snapshot, terminal in a later one) ===")
    print(f"  {'id':10s} {'solver':12s} {'createdAt':22s} {'>= min':>8s} {'<= min':>8s} {'width':>7s}")
    for rid, sv, c, lo, hi in sorted(bracketed, key=lambda t: t[2]):
        print(f"  {rid[:8]:10s} {sv[:12]:12s} {c:%Y-%m-%dT%H:%M:%SZ}  {lo:8.1f} {hi:8.1f} {hi - lo:7.1f}")

    if onesided:
        print("\n=== still non-terminal at the newest observation (one-sided lower bounds) ===")
        for rid, sv, c, lo in sorted(onesided, key=lambda t: t[2]):
            print(f"  {rid[:8]:10s} {sv[:12]:12s} {c:%Y-%m-%dT%H:%M:%SZ}  >= {lo:.1f} min")

    los = [lo for _, _, _, lo, _ in bracketed]
    his = [hi for _, _, _, _, hi in bracketed]
    mids = [(lo + hi) / 2 for _, _, _, lo, hi in bracketed]

    print("\n=== statistics (minutes) ===")
    describe("lower bounds", los)
    describe("upper bounds", his)
    describe("bracket midpoints", mids)
    if onesided:
        describe("one-sided (censored) >=", [lo for _, _, _, lo in onesided])
    print(f"  rows created+finished inside one gap (excluded, biased fast): {unobserved}")

    if args.split:
        boundary = cut(args.split)
        print(f"\n=== two regimes around {boundary:%H:%M}Z ===")
        for label, sel in (("before", lambda c: c < boundary), ("after", lambda c: c >= boundary)):
            sub = [(lo + hi) / 2 for _, _, c, lo, hi in bracketed if sel(c)]
            describe(f"{label} midpoints", sub)
            cens = [lo for _, _, c, lo in onesided if sel(c)]
            if cens:
                describe(f"{label} censored >=", cens)

    # ---- what it means for the shot budget ------------------------------------
    if mids:
        print("\n=== shot budget implied by measured service time ===")
        now = snaps[-1][0]
        deadline = dt.datetime.combine(day, dt.time(20, 0), dt.timezone.utc)
        remain = (deadline - now).total_seconds() / 60
        censored = [lo for _, _, _, lo in onesided]
        est = {
            "bracket median": statistics.median(mids),
            "bracket p90": pct(mids, 90),
        }
        if censored:
            est["censored median (lower bd)"] = statistics.median(censored)
            est["censored max (lower bd)"] = max(censored)
        print(f"  remaining wall clock to {deadline:%H:%M}Z: {remain:.0f} min")
        for label, per_shot in est.items():
            if per_shot <= 0:
                continue
            solo = remain / per_shot
            print(f"  at {per_shot:6.1f} min/shot ({label:28s}): {solo:5.1f} shots solo, "
                  f"{solo / 3:5.1f} at a 1/3 account share")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
