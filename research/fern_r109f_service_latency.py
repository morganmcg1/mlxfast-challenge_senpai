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
    ap.add_argument("--exclusion-check", action="store_true",
                    help="test the run-time floor against the excluded rows' upper bounds")
    ap.add_argument("--floor", type=float, default=22.9,
                    help="run-time floor in minutes to falsify (default 22.9, from poller brackets)")
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
    excluded_ub: list[tuple[str, str, float]] = []
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
            # A row never seen non-terminal was created and finished inside a
            # single snapshot gap.  Its service is bounded above by the time
            # from creation to the snapshot that first showed it terminal.
            excluded_ub.append((rid, final_status[rid], (first_term[rid] - c).total_seconds() / 60))

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
    print(f"  rows created+finished inside one gap (excluded): {unobserved}")
    print("  RETRACTION (2026-08-11): earlier revisions of this tool called the excluded")
    print("  rows 'biased fast', i.e. excluded BECAUSE they are quick.  That is wrong.  The")
    print("  median inter-snapshot gap is of the same order as the measured run-time floor")
    print("  (~22.9 min) and many gaps are far larger, so a floor-length row fits inside")
    print("  almost any gap.  The exclusion is driven by SNAPSHOT SPARSITY, not row speed.")
    print("  Run with --exclusion-check to test that claim against the excluded rows.")

    if args.split:
        boundary = cut(args.split)
        print(f"\n=== two regimes around {boundary:%H:%M}Z ===")
        for label, sel in (("before", lambda c: c < boundary), ("after", lambda c: c >= boundary)):
            sub = [(lo + hi) / 2 for _, _, c, lo, hi in bracketed if sel(c)]
            describe(f"{label} midpoints", sub)
            cens = [lo for _, _, c, lo in onesided if sel(c)]
            if cens:
                describe(f"{label} censored >=", cens)

    # ---- falsification test for the run-time floor ----------------------------
    # The poller logs give three exact service brackets clustered at 22.7-23.1 min
    # (mean 22.938, sd 0.176), which reads as a fixed-work pipeline rather than a
    # queue.  That cluster is a sample MINIMUM over 3 observations, so it is an
    # UPPER bound on the population minimum -- it licenses "no observed shot cost
    # less than 22.7 min", never "22.7 is a hard floor".
    #
    # The 1818 excluded rows are a free, much larger test of the same claim.  Each
    # carries ub = first_terminal_snapshot - createdAt, a HARD upper bound on its
    # service.  If a run-time floor near 22.9 min exists, essentially no row that
    # actually ran the benchmark legs may have ub < floor.  Many such rows would
    # falsify the floor on 1818 observations instead of 3.
    #
    # One confound has to be removed first: `failed` rows abort the pipeline early
    # (build error, correctness gate), so they never pay for the two benchmark legs
    # and are LEGITIMATELY allowed below the floor.  Only rows that reached a score
    # -- accepted/rejected -- can falsify it.
    if args.exclusion_check and excluded_ub:
        floor = args.floor
        print(f"\n=== exclusion check: does the ~{floor:.1f} min run-time floor survive the excluded rows? ===")
        ubs = [u for _, _, u in excluded_ub]
        describe("excluded upper bounds", ubs)
        vacuous = sum(1 for u in ubs if u >= floor)
        print(f"  ub >= floor (bound is vacuous, exclusion says nothing about speed): "
              f"{vacuous}/{len(ubs)} = {100 * vacuous / len(ubs):.1f}%")

        by_status: dict[str, list[float]] = {}
        for _rid, st, u in excluded_ub:
            by_status.setdefault(st, []).append(u)
        print("  by final status:  (violations = rows provably faster than the floor)")
        for st in sorted(by_status, key=lambda s: -len(by_status[s])):
            vals = by_status[st]
            bad = [u for u in vals if u < floor]
            print(f"    {st:10s} n={len(vals):5d}  min ub={min(vals):7.2f}  "
                  f"median ub={statistics.median(vals):7.2f}  ub<floor: {len(bad):4d} "
                  f"({100 * len(bad) / len(vals):5.1f}%)")

        # `failed` rows are exempt: they exit before the benchmark legs run.
        scored = [(rid, st, u) for rid, st, u in excluded_ub if st != "failed"]
        viol = sorted((u, rid, st) for rid, st, u in scored if u < floor)
        print(f"\n  rows that reached a score (accepted/rejected), i.e. paid for both legs: {len(scored)}")
        print(f"  of those, provably faster than the floor (ub < {floor:.1f}): {len(viol)}")
        if viol:
            print("  ten fastest violations (each is a hard counter-example to the floor):")
            for u, rid, st in viol[:10]:
                print(f"    {rid[:8]:10s} {st:10s} ub={u:7.2f} min")
        # ---- POWER CHECK ------------------------------------------------------
        # A test that cannot fail is not evidence.  A row can only contradict the
        # floor if its ub can dip below it, so if min(ub) over the whole set already
        # exceeds the floor, the count of violations is forced to zero a priori and
        # carries no information whatever about run time.
        min_ub = min(ubs)
        print(f"\n  POWER CHECK: smallest upper bound anywhere in the excluded set = {min_ub:.2f} min")
        if min_ub >= floor:
            print(f"    {min_ub:.2f} >= {floor:.1f}, so NOT ONE of the {len(ubs)} rows was even capable of")
            print("    falsifying the floor.  The zero violations above are a foregone conclusion,")
            print("    not a confirmation.  Power of the whole-set test = 0.")
        else:
            print(f"    some rows could dip below {floor:.1f}, so the whole-set test has real power.")

        # ---- the properly powered test ----------------------------------------
        # Reframing recovers real power.  An excluded row terminated before the very
        # next snapshot after its creation, so for excluded rows ub is EXACTLY
        # (next snapshot) - created.  Therefore "ub < floor" happens precisely when a
        # row was created within `floor` minutes before a snapshot and was already
        # terminal at it.  That turns the question into a directly checkable one:
        #
        #   look at every (row, snapshot) pair where the row is younger than `floor`
        #   at that snapshot.  If a run-time floor exists, EVERY such row must still
        #   be non-terminal.  Any terminal one is a hard counter-example.
        #
        # The number of such pairs is the test's power, and it no longer depends on
        # how loose the historic bounds are.
        print(f"\n  POWERED TEST: rows observed while younger than {floor:.1f} min")
        print("  (a floor forbids any of these from being terminal already)")
        seen: set[str] = set()
        opp_nonterm = 0
        nonterm_ages: list[float] = []
        opp_failed: list[tuple[float, str]] = []
        opp_viol: list[tuple[float, str, str]] = []
        for observed, _path, rows in snaps:
            for r in rows:
                rid = r["id"]
                if args.solver and r["solverUsername"] != args.solver:
                    continue
                age = (observed - parse_iso(r["createdAt"])).total_seconds() / 60
                if not (0 <= age < floor) or rid in seen:
                    continue
                seen.add(rid)
                st = r["status"]
                if st in NONTERMINAL:
                    opp_nonterm += 1
                    nonterm_ages.append(age)
                elif st == "failed":
                    opp_failed.append((age, rid))
                else:
                    opp_viol.append((age, rid, st))
        n_opp = opp_nonterm + len(opp_failed) + len(opp_viol)
        print(f"    observations of rows younger than the floor: n={n_opp}")
        print(f"      still non-terminal (consistent with a floor):        {opp_nonterm}")
        print(f"      already 'failed' (exempt: aborts before the legs):   {len(opp_failed)}")
        print(f"      already scored accepted/rejected (COUNTER-EXAMPLES): {len(opp_viol)}")
        for age, rid, st in sorted(opp_failed)[:5]:
            print(f"        exempt  {rid[:8]:10s} {st:10s} scored terminal at age {age:6.2f} min")
        for age, rid, st in sorted(opp_viol)[:10]:
            print(f"        VIOLATION {rid[:8]:10s} {st:10s} terminal at age {age:6.2f} min")

        # How much the test actually establishes depends on HOW OLD those rows were
        # when seen running: a row still running at age a proves its service > a, so
        # only observations with a close to the floor constrain a floor near it.
        if nonterm_ages:
            describe("  ages when seen running", nonterm_ages)
            print("    each row still running at age a proves that row's service exceeded a:")
            for thr in (5.0, 10.0, 15.0, 20.0, floor):
                k = sum(1 for a in nonterm_ages if a >= thr)
                print(f"      rows proven to exceed {thr:5.1f} min: {k:3d}/{len(nonterm_ages)}")
            print(f"    strongest single lower bound from this test: {max(nonterm_ages):.2f} min")

        print("\n  VERDICT:")
        print("    (1) On the RETRACTION -- settled, decisively.  The upper bound is vacuous")
        print(f"        for {100 * vacuous / len(ubs):.1f}% of excluded rows, with a median of {statistics.median(ubs):.0f} min ({statistics.median(ubs) / 1440:.1f} days),")
        print("        because those rows were created long before the first snapshot.  Rows")
        print("        are excluded because I started watching late -- SNAPSHOT SPARSITY --")
        print("        and NOT because they are the fast ones.")
        print("    (2) On the naive whole-set count: vacuous by construction, power 0.")
        if n_opp == 0:
            print(f"    (3) On the FLOOR: the powered test is also empty -- no row was ever observed")
            print(f"        younger than {floor:.1f} min.  The floor still rests on the n=3 poller brackets.")
        elif opp_viol:
            print(f"    (3) On the FLOOR: FALSIFIED.  {len(opp_viol)} of {n_opp} rows observed younger than")
            print(f"        {floor:.1f} min had already been scored.  The fastest was {min(opp_viol)[0]:.2f} min, so the")
            print("        pipeline can finish well under the supposed floor.  Treat 22.9 min as a")
            print("        mode, not a minimum, and do not let the shot budget rely on it.")
        else:
            n20 = sum(1 for a in nonterm_ages if a >= 20.0)
            n10 = sum(1 for a in nonterm_ages if a >= 10.0)
            print(f"    (3) On the FLOOR: SURVIVES, with GRADED power.  All {n_opp} rows seen younger")
            print(f"        than {floor:.1f} min were still running, and this is independent of the 3")
            print("        poller brackets -- it reads row ages inside snapshots, not completions.")
            print("        But the power is not uniform across candidate floors.  It is decisive")
            print(f"        against a short pipeline ({n10} rows proven to exceed 10 min) and only")
            print(f"        weak right at the claimed value ({n20} rows exceed 20 min; strongest single")
            print(f"        bound {max(nonterm_ages):.2f} min).  So: a service of a few minutes is firmly excluded,")
            print(f"        while '{floor:.1f} exactly' is consistent-but-not-pinned by this test, and the")
            print("        cluster's tightness (sd 0.18 min) is still carried by n=3 alone.")
        print("    Caveat that does not go away: all of this bounds the RUN, not the QUEUE.")
        print("    Wall-clock cost per shot is run + queue wait, and the queue is the variable")
        print("    part (exact services observed from 22.7 to 82.8 min).")

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
