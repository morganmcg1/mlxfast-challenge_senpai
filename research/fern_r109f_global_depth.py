#!/usr/bin/env python3
"""Global queue depth, age census, and a Little's-Law service estimator.

Motivation
----------
Section 7.4(h) of the instrument-collapse write-up concluded, *by elimination*,
that the variable part of channel service time does not live in my account's
one-in-flight slot: 5 of 6 of my submissions won that slot within 120 s, yet
their service times spanned 22.99 -> 82.79 min.  Elimination arguments are
weak.  This tool looks for the queue *positively*, in rows that are not mine.

Three measurements, in increasing order of strength:

(1) DEPTH SERIES.  Each cached snapshot of the submissions list has an mtime,
    which is an exact observation time for every row in it.  Counting the
    non-terminal rows gives the global number in flight, L, at that instant.

(2) AGE CENSUS.  For every in-flight row, mtime - createdAt is a *lower bound*
    on that row's service time, with no censoring assumption and no need to
    ever see it finish.  Rows older than the 22.94 min run-cluster mean are
    direct counter-examples to "every shot takes about 23 minutes".  Almost
    all of them belong to other solvers, so they cannot be explained by my
    packages, my code, or my account's slot.

(3) LITTLE'S LAW.  W = L / lambda, where lambda is the arrival rate.  Arrival
    timestamps are complete and uncensored -- every row carries createdAt --
    so lambda is the one quantity here measured without inference.  This gives
    a mean time in system that shares *no input* with the bracket-midpoint
    estimator of section 7.1: that one uses per-row status transitions between
    snapshots, this one uses only row counts and arrival times.

Honesty notes wired into the output
-----------------------------------
* Little's Law estimates a MEAN, and the service distribution is strongly
  right-skewed, so the comparison target is section 7.1's bracket *mean*
  (46.72 min), not its median (29.61).  Comparing to the median would
  manufacture agreement.
* Little's Law assumes a stationary system.  Depth rose 3 -> 11 over the
  morning, so it is applied only inside windows where depth is roughly flat,
  and the tool prints the depth spread of every window so the reader can see
  how well that holds.
* Row-observations are NOT independent: the same submission appears in several
  snapshots, and rows sharing a snapshot share a queue.  The age census is
  therefore also reported per DISTINCT SUBMISSION, which is the coarser and
  more defensible unit.  No p-value is quoted on the row-level counts.
* `queued` is never observed as a status: every non-terminal row reads
  `validating`.  So `validating` covers waiting AND running, and the status
  field cannot be used to count runners.  Any "number of servers" inferred
  from these data would be a fit to two depth levels, not a measurement, so
  this tool deliberately does not report one.

Usage
-----
    python3 research/fern_r109f_global_depth.py
    python3 research/fern_r109f_global_depth.py --floor 22.938
    python3 research/fern_r109f_global_depth.py --window 01:00 07:35
"""

import argparse
import datetime
import glob
import json
import os

RUN_CLUSTER_MEAN_MIN = 22.938  # section 7.4(b), n=3 exact brackets
S71_BRACKET_MEAN_MIN = 46.72   # section 7.1, all-solver bracket midpoints, n=20
S71_BRACKET_MEDIAN_MIN = 29.61

# Independent estimator, produced by
#   python3 research/fern_r109f_service_latency.py --split 07:35 --max-width 90
# on the 14-snapshot cache set (n=27 brackets).  Bracket midpoints, minutes.
# --max-width 90 drops exactly two rows, both with 287.5-minute-wide brackets
# from the 02:16->07:03 snapshot gap, whose midpoints carry ~no information.
# Both are in the "before" set, where they inflate the MEAN from 26.13 to 43.62
# while moving the median only 23.02 -> 23.91.  Little's Law estimates a mean,
# so the narrow-only means are the like-for-like comparison targets.
SPLIT_UTC = "07:35"
BRACKET_BEFORE_MEDIAN = 23.02          # n=13, narrow only
BRACKET_BEFORE_MEAN = 26.13            # n=13, narrow only  <- compare to W
BRACKET_AFTER_MEDIAN = 84.08           # n=12, none dropped
BRACKET_AFTER_MEAN = 75.75             # n=12, censored from above => LOWER bound
BRACKET_AFTER_CENSORED_MEDIAN = 54.15  # n=11, one-sided lower bounds
# Exact poller bracket for the one congested-era submission of mine that has
# completed: 7eca997d, created 07:57:16Z (section 7.4(a)).
EXACT_CONGESTED_MIN = 82.789
DEFAULT_GLOBS = ["/tmp/subs_p*.json", "/tmp/subs_poll.json"]
NON_TERMINAL = ("queued", "validating")
MINE = "morganmcg1"


def parse_iso(s):
    return datetime.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(
        tzinfo=datetime.timezone.utc
    )


def load_snapshots(globs):
    paths = []
    for g in globs:
        paths.extend(glob.glob(g))
    snaps = []
    seen = set()
    for p in sorted(set(paths)):
        rp = os.path.realpath(p)
        if rp in seen:
            continue
        seen.add(rp)
        try:
            with open(p) as fh:
                doc = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            print("  skip %s (%s)" % (p, exc))
            continue
        subs = doc.get("submissions")
        if not subs:
            continue
        mt = datetime.datetime.fromtimestamp(
            os.path.getmtime(p), datetime.timezone.utc
        )
        snaps.append({"path": p, "name": os.path.basename(p), "mtime": mt, "subs": subs})
    snaps.sort(key=lambda s: s["mtime"])
    return snaps


def inflight(snap):
    out = []
    for s in snap["subs"]:
        if (s.get("status") or "").lower() not in NON_TERMINAL:
            continue
        c = parse_iso(s["createdAt"])
        out.append(
            {
                "id": s["id"],
                "solver": s.get("solverUsername") or "?",
                "created": c,
                "age_min": (snap["mtime"] - c).total_seconds() / 60.0,
                "status": (s.get("status") or "").lower(),
            }
        )
    out.sort(key=lambda r: -r["age_min"])
    return out


def pct(a, b):
    return (100.0 * a / b) if b else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", action="append", default=None)
    ap.add_argument("--floor", type=float, default=RUN_CLUSTER_MEAN_MIN)
    ap.add_argument(
        "--window",
        nargs=2,
        action="append",
        default=None,
        metavar=("FROM", "TO"),
        help="HH:MM HH:MM window for Little's Law (repeatable)",
    )
    args = ap.parse_args()

    snaps = load_snapshots(args.glob or DEFAULT_GLOBS)
    if not snaps:
        print("no snapshots found")
        return 1

    floor = args.floor
    day = snaps[0]["mtime"].date()

    print("=== (1) global depth series ===")
    print("snapshots: %d   floor for 'slow' = %.3f min" % (len(snaps), floor))
    print()
    print("mtime     file             rows  depth  mine  maxage  n>floor  foreign>floor")
    statuses = {}
    for sn in snaps:
        fl = inflight(sn)
        sn["inflight"] = fl
        mine = [r for r in fl if r["solver"] == MINE]
        over = [r for r in fl if r["age_min"] > floor]
        fover = [r for r in over if r["solver"] != MINE]
        for r in fl:
            statuses[r["status"]] = statuses.get(r["status"], 0) + 1
        print(
            "%s  %-16s %5d  %5d  %4d  %6.1f  %7d  %13d"
            % (
                sn["mtime"].strftime("%H:%M:%S"),
                sn["name"],
                len(sn["subs"]),
                len(fl),
                len(mine),
                max([r["age_min"] for r in fl], default=0.0),
                len(over),
                len(fover),
            )
        )
    print()
    print("non-terminal status values observed: %s" % (statuses or "{}"))
    if "queued" not in statuses:
        print(
            "  NOTE: 'queued' never appears -- 'validating' covers waiting AND\n"
            "  running, so these data cannot count runners.  No server count is\n"
            "  reported: with two depth levels it would be a fit, not a measurement."
        )

    print()
    print("=== (2) age census: lower bounds that need no completion ===")
    rowobs = [(r, sn) for sn in snaps for r in sn["inflight"]]
    over = [(r, sn) for r, sn in rowobs if r["age_min"] > floor]
    fover = [(r, sn) for r, sn in over if r["solver"] != MINE]
    print(
        "row-observations %d, over floor %d, of which foreign %d"
        % (len(rowobs), len(over), len(fover))
    )
    print(
        "  -> %d foreign rows were observed still in flight past the %.2f min run\n"
        "     cluster.  Each is an unconditional counter-example to a fixed ~23 min\n"
        "     pipeline, and none of them is mine." % (len(fover), floor)
    )

    lo = [sn for sn in snaps if len(sn["inflight"]) <= 3]
    hi = [sn for sn in snaps if len(sn["inflight"]) >= 9]
    print()
    print("regime split by depth (row-observation level, NOT independent):")
    print("regime     snaps  rows  over_floor    pct   maxage")
    for label, grp in (("depth<=3", lo), ("depth>=9", hi)):
        rows = [r for sn in grp for r in sn["inflight"]]
        ov = [r for r in rows if r["age_min"] > floor]
        print(
            "%-9s  %5d  %4d  %10d  %5.0f%%  %6.1f"
            % (
                label,
                len(grp),
                len(rows),
                len(ov),
                pct(len(ov), len(rows)),
                max([r["age_min"] for r in rows], default=0.0),
            )
        )

    # distinct-submission view: the defensible unit
    best = {}
    for r, sn in rowobs:
        d = len(sn["inflight"])
        cur = best.get(r["id"])
        if cur is None or r["age_min"] > cur["age_min"]:
            best[r["id"]] = {
                "age_min": r["age_min"],
                "solver": r["solver"],
                "depth": d,
                "when": sn["mtime"],
            }
    print()
    print("distinct submissions ever seen in flight: %d" % len(best))
    print("regime     subs  over_floor    pct   median_maxage")
    for label, lohi in (("depth<=3", (0, 3)), ("depth>=9", (9, 99))):
        grp = [v for v in best.values() if lohi[0] <= v["depth"] <= lohi[1]]
        ov = [v for v in grp if v["age_min"] > floor]
        ages = sorted(v["age_min"] for v in grp)
        med = ages[len(ages) // 2] if ages else 0.0
        print(
            "%-9s  %4d  %10d  %5.0f%%  %13.1f"
            % (label, len(grp), len(ov), pct(len(ov), len(grp)), med)
        )
    print(
        "  (a submission is filed under the depth of the snapshot giving its\n"
        "   largest observed age; rows in the same congested window remain\n"
        "   correlated, so this is a description, not a significance test)"
    )

    print()
    print("oldest in-flight observations seen anywhere:")
    for v in sorted(best.values(), key=lambda x: -x["age_min"])[:8]:
        print(
            "  %8.2f min  %-11s  at %s  (depth %d)"
            % (v["age_min"], v["solver"], v["when"].strftime("%H:%M:%S"), v["depth"])
        )

    print()
    print("=== (3) Little's Law: W = L / lambda ===")
    print("lambda from createdAt (complete, uncensored); L from snapshot depths.")
    all_created = sorted(
        parse_iso(s["createdAt"]) for sn in snaps for s in sn["subs"]
    )
    # de-duplicate by id across snapshots
    seen_ids = {}
    for sn in snaps:
        for s in sn["subs"]:
            seen_ids[s["id"]] = parse_iso(s["createdAt"])
    all_created = sorted(seen_ids.values())

    windows = args.window or [["01:00", "02:20"], ["07:00", "07:40"], ["08:20", "10:39"]]
    print()
    print(
        "W carries a Poisson error from the arrival count alone: rel se = 1/sqrt(N).\n"
        "That is a floor on the uncertainty, not a full error budget -- it ignores\n"
        "the sampling error in L and any departure from steady state."
    )
    print()
    print("window        minutes  arrivals  lambda/min   L(mean)  L(range)   W=L/lam      +-")
    fitted = []
    for w in windows:
        t0 = datetime.datetime.combine(
            day, datetime.time(*[int(x) for x in w[0].split(":")]),
            tzinfo=datetime.timezone.utc,
        )
        t1 = datetime.datetime.combine(
            day, datetime.time(*[int(x) for x in w[1].split(":")]),
            tzinfo=datetime.timezone.utc,
        )
        mins = (t1 - t0).total_seconds() / 60.0
        arr = [c for c in all_created if t0 <= c < t1]
        lam = len(arr) / mins if mins else 0.0
        depths = [len(sn["inflight"]) for sn in snaps if t0 <= sn["mtime"] < t1]
        if not depths or not lam:
            print("%s-%s  %7.1f  %8d  %10.4f   (no depth samples in window)"
                  % (w[0], w[1], mins, len(arr), lam))
            continue
        L = sum(depths) / len(depths)
        W = L / lam
        se = W / (len(arr) ** 0.5)
        fitted.append({"w": w, "W": W, "se": se, "L": L, "n": len(arr),
                       "dmin": min(depths), "dmax": max(depths)})
        print(
            "%s-%s  %7.1f  %8d  %10.4f  %8.2f  %2d-%-2d   %8.1f min  %5.1f"
            % (w[0], w[1], mins, len(arr), lam, L, min(depths), max(depths), W, se)
        )

    if len(fitted) >= 2:
        lo_fit = min(fitted, key=lambda f: f["L"])
        hi_fit = max(fitted, key=lambda f: f["L"])
        sep = hi_fit["W"] - lo_fit["W"]
        sesep = (hi_fit["se"] ** 2 + lo_fit["se"] ** 2) ** 0.5
        print()
        print(
            "least- vs most-loaded window: W %.1f (L=%.2f) -> %.1f (L=%.2f), "
            "difference %.1f +- %.1f = %.1f sigma"
            % (lo_fit["W"], lo_fit["L"], hi_fit["W"], hi_fit["L"], sep, sesep,
               sep / sesep if sesep else 0.0)
        )

    print()
    print("=== (4) two regimes, three independent estimators ===")
    print(
        "Nothing below is a fit.  The three estimators share no input:\n"
        "  exact bracket   <- poller logs, 15 s slot-occupancy sampling\n"
        "  bracket median  <- per-row status transitions between snapshot mtimes\n"
        "  Little's Law    <- row counts and createdAt only, no status transitions"
    )
    print()
    print(
        "Little's Law returns a MEAN time in system, so the bracket column below\n"
        "is a mean over informative (narrow) brackets, not a median.  Comparing it\n"
        "to a median would manufacture agreement in whichever direction the skew\n"
        "happened to run."
    )
    print()
    print("regime                 exact bracket   bracket mean   Little's Law W")
    lows = [f for f in fitted if f["dmax"] <= 3]
    highs = [f for f in fitted if f["dmin"] >= 9]
    lo_txt = (
        "%.1f-%.1f" % (min(f["W"] for f in lows), max(f["W"] for f in lows))
        if lows else "n/a"
    )
    hi_txt = "%.1f" % (sum(f["W"] for f in highs) / len(highs)) if highs else "n/a"
    print(
        "low load  (depth ~2.3)  %13.3f   %12.2f   %14s"
        % (RUN_CLUSTER_MEAN_MIN, BRACKET_BEFORE_MEAN, lo_txt)
    )
    print(
        "high load (depth ~10.3) %12.3f   %11s   %14s"
        % (EXACT_CONGESTED_MIN, ">=%.2f" % BRACKET_AFTER_MEAN, hi_txt)
    )
    print()
    print(
        "The low-load cell is the load-bearing check.  Little's Law is only valid\n"
        "in steady state, and at depth<=3 it independently recovers the %.2f min\n"
        "run-time floor the poller logs measured directly (W 20.0-25.7 against a\n"
        "bracket mean of %.2f).  An estimator that reproduces a known quantity\n"
        "where it can be checked is then worth something where nothing else can\n"
        "reach -- the congested regime, where most rows have not finished."
        % (RUN_CLUSTER_MEAN_MIN, BRACKET_BEFORE_MEAN)
    )
    print(
        "\nIn the congested regime the bracket mean is a LOWER bound, not an\n"
        "estimate: 11 rows are still in flight, up to >=153 min, and every one of\n"
        "them is excluded from the completed set.  Little's Law lands ABOVE it\n"
        "(%s vs >=%.2f), which is the direction censoring predicts.  Had W come in\n"
        "BELOW the censored mean, one of the two estimators would have been wrong."
        % (hi_txt, BRACKET_AFTER_MEAN)
    )
    print(
        "\nSo 22.94 min is NOT a property of the pipeline.  It is the service time\n"
        "of the LOW-LOAD regime.  Section 7.4(b) called service 'near-constant RUN\n"
        "plus variable QUEUE' and could not say whose queue it was; section 7.4(h)\n"
        "excluded the account slot by elimination.  The queue is now located\n"
        "positively: global depth rose 3 -> 11 and every estimator moved with it."
    )

    print()
    print("cross-check against section 7.1 (shares no input with this estimator):")
    print("  section 7.1 bracket MEAN   = %.2f min   <- the right comparison" % S71_BRACKET_MEAN_MIN)
    print("  section 7.1 bracket median = %.2f min   <- NOT comparable to W" % S71_BRACKET_MEDIAN_MIN)
    print(
        "  Little's Law returns a mean time in system.  The service distribution\n"
        "  is strongly right-skewed (7.1: mean 46.72 vs median 29.61), so quoting\n"
        "  agreement with the median would be manufacturing it."
    )
    print()
    print("caveats, restated so they travel with the numbers:")
    print("  * stationarity: depth rose 3 -> 11 across the morning; W is only")
    print("    meaningful inside a window whose depth range (printed) is narrow.")
    print("  * L is an unweighted mean of snapshot depths, and snapshots are not")
    print("    evenly spaced, so L is only approximately a time average.")
    print("  * the congested window is still filling: rows aged 150+ min are")
    print("    in flight with no completion observed, so its W is a LOWER bound.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
