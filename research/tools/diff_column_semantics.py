#!/usr/bin/env python3
"""What does the `diff` column of `mlxfast submissions` actually mean?

Why this matters. The campaign's endgame arithmetic is denominated in "how far short
of the bar is a fire". The CLI prints, per receipt, an absolute diff and a percentage,
e.g. for 5fae2f1: score 2.57521511, diff `-0.044338 (-4.42%)`. But
2.57521511 + 0.044338 = 2.61955311 = the bar, and 0.044338 / 2.61955311 = 1.69%, not
4.42%. If the printed percentage is not diff/bar, then anyone reading it as "we are
4.4% short" is inflating the true relative gap, and any table that mixes CLI
percentages with score-relative percentages is wrong by that factor.

This script tests candidate denominators against every scored receipt and reports
which one reproduces the printed percentage.

Run:
    COLUMNS=4000 mlxfast submissions > dump.txt
    python3 research/tools/diff_column_semantics.py --dump dump.txt
"""

import argparse
import datetime as dt
import re
import statistics as st
import sys

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
ROW = re.compile(
    r"^(?P<sub>\w+)\s+(?P<solver>\S+)\s+(?P<status>\w+)\s+(?P<score>[\d.]+|n/a)\s+"
    # NB the sign must be optional AND allow '+': the one promoted receipt prints
    # '+0.03652 (+3.64%)', and a '-?'-only pattern silently drops exactly the row
    # that proves what the bar is.
    r"(?P<metrics>\S+)\s+(?P<diff>[-+]?[\d.]+)\s+\((?P<pct>[-+]?[\d.]+)%\)\s+"
    r"(?P<commit>\S+)\s+(?P<created>.+)$"
)


def parse_created(s):
    """'8/11/26, 12:16 PM' -> datetime, or None if unparseable."""
    for fmt in ("%m/%d/%y, %I:%M %p", "%m/%d/%Y, %I:%M %p"):
        try:
            return dt.datetime.strptime(s.strip(), fmt)
        except ValueError:
            pass
    return None


STATUSES = {"failed", "rejected", "promoted", "validating", "pending"}
ANY_ROW = re.compile(r"^(?P<sub>\w+)\s+\S+\s+(?P<status>\w+)\s")
CREATED_TAIL = re.compile(r"(\d{1,2}/\d{1,2}/\d{2},\s+\d{1,2}:\d{2}\s+[AP]M)\s*$")


def parse_all(text):
    """Every receipt row, including `failed` ones that print no diff at all."""
    out = []
    for line in ANSI.sub("", text).splitlines():
        m = ANY_ROW.match(line.strip())
        if not m or m.group("status") not in STATUSES:
            continue
        c = CREATED_TAIL.search(line)
        out.append({"sub": m.group("sub"), "status": m.group("status"),
                    "created": c.group(1) if c else "?",
                    "t": parse_created(c.group(1)) if c else None})
    return [r for r in out if r["t"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    args = ap.parse_args()

    text = open(args.dump).read() if args.dump != "-" else sys.stdin.read()
    rows = []
    for line in ANSI.sub("", text).splitlines():
        m = ROW.match(line.strip())
        if not m:
            continue
        try:
            score = float(m.group("score"))
        except ValueError:
            continue
        rows.append({
            "sub": m.group("sub"),
            "status": m.group("status"),
            "score": score,
            "diff": float(m.group("diff")),
            "pct": float(m.group("pct")),
            "created": m.group("created"),
        })

    print(f"rows with a parsed diff: {len(rows)}")
    if not rows:
        sys.exit("no rows parsed - check the dump format")

    # For each row, the denominator implied by diff and pct.
    print()
    print("== implied denominator = diff / (pct/100) ==")
    dens = [r["diff"] / (r["pct"] / 100.0) for r in rows if r["pct"]]
    print(f"  n={len(dens)}  min {min(dens):.5f}  median {st.median(dens):.5f}  "
          f"max {max(dens):.5f}  mean {st.fmean(dens):.5f}")
    print("  (a denominator pinned near 1.0 means the percentage is just the absolute")
    print("   diff times 100 - i.e. a percentage of unity, not of any score.)")
    print()

    # The printed percentage is rounded to 2 dp, so each row only constrains the
    # denominator to an interval. If a single constant lies in EVERY interval,
    # the percentage is diff/constant and nothing per-receipt enters it.
    print("== is one constant denominator consistent with every row? ==")
    lo, hi, binding = -float("inf"), float("inf"), (None, None)
    for r in rows:
        p = abs(r["pct"])
        d = abs(r["diff"])
        if p == 0:
            continue
        a = d / ((p + 0.005) / 100.0)   # smallest denominator still rounding to p
        b = d / ((p - 0.005) / 100.0)   # largest
        if a > lo:
            lo, binding = a, (r["sub"], binding[1])
        if b < hi:
            hi, binding = b, (binding[0], r["sub"])
    if lo <= hi:
        print(f"  YES - feasible interval [{lo:.6f}, {hi:.6f}], "
              f"width {hi - lo:.2e}; midpoint {(lo + hi) / 2:.6f}")
        print(f"  binding rows: lower {binding[0]}, upper {binding[1]}")
        print("  => the percentage is (absolute diff) / (that constant), so it carries")
        print("     NO information about the receipt's own score. Reading it as a")
        print("     score-relative shortfall inflates the real gap.")
    else:
        print(f"  NO - intervals do not intersect (lo {lo:.6f} > hi {hi:.6f}); the")
        print("  denominator genuinely varies per receipt.")
    print()

    print("== candidate denominators, mean |error| in percentage points ==")

    def err(name, den_fn):
        errs = []
        for r in rows:
            d = den_fn(r)
            if not d:
                continue
            errs.append(abs(100.0 * r["diff"] / d - r["pct"]))
        if errs:
            print(f"  {name:<28} mean {st.fmean(errs):.4f} pp   max {max(errs):.4f} pp")

    err("1.0 (percent of unity)", lambda r: 1.0)
    err("this receipt's score", lambda r: r["score"])
    err("score - diff (the bar)", lambda r: r["score"] - r["diff"])
    print()

    print("== worked examples ==")
    print(f"  {'sub':<9}{'score':>12}{'diff':>11}{'pct':>8}"
          f"{'diff/bar%':>11}{'ratio':>8}")
    for r in rows[:3] + rows[-5:]:
        bar = r["score"] - r["diff"]
        rel = 100.0 * r["diff"] / bar
        ratio = r["pct"] / rel if rel else float("nan")
        print(f"  {r['sub']:<9}{r['score']:>12.6f}{r['diff']:>11.6f}"
              f"{r['pct']:>7.2f}%{rel:>10.2f}%{ratio:>8.2f}")
    print()

    bars = [r["score"] - r["diff"] for r in rows]
    print("== is the diff taken against a single fixed bar, or a moving one? ==")
    print(f"  distinct (score - diff) values (rounded to 1e-6): "
          f"{len({round(b, 6) for b in bars})} over {len(bars)} rows")
    print(f"  min {min(bars):.9f}   max {max(bars):.9f}")
    for b in sorted({round(b, 6) for b in bars}):
        hits = [r for r in rows if round(r["score"] - r["diff"], 6) == b]
        first, last = hits[0]["created"], hits[-1]["created"]
        print(f"    bar {b:.6f}  n={len(hits):>3}  {first}  ..  {last}")
    print("  (adjacent values differing only in the 6th decimal are one bar seen")
    print("   through the CLI's rounded 6-dp diff; cluster them below.)")
    print()

    # --- bar trajectory in time order, clustering rounding twins -------------
    for r in rows:
        r["bar"] = r["score"] - r["diff"]
        r["t"] = parse_created(r["created"])
    ordered = sorted([r for r in rows if r["t"]], key=lambda r: r["t"])
    print("== bar trajectory (clustered at 1e-5, first appearance in time order) ==")
    print(f"  {'bar':>12}{'step':>11}{'first seen':>20}{'n':>5}")
    traj = []
    for r in ordered:
        if traj and abs(r["bar"] - traj[-1]["bar"]) < 1e-5:
            traj[-1]["n"] += 1
            continue
        traj.append({"bar": r["bar"], "t": r["t"], "created": r["created"], "n": 1})
    for i, s in enumerate(traj):
        step = "" if i == 0 else f"{s['bar'] - traj[i - 1]['bar']:+.6f}"
        print(f"  {s['bar']:>12.6f}{step:>11}{s['created']:>20}{s['n']:>5}")
    if len(traj) > 1:
        span_h = (traj[-1]["t"] - traj[0]["t"]).total_seconds() / 3600.0
        rise = traj[-1]["bar"] - traj[0]["bar"]
        print(f"  monotone non-decreasing: {all(traj[i]['bar'] >= traj[i-1]['bar'] - 1e-9 for i in range(1, len(traj)))}")
        print(f"  total rise {rise:+.6f} ({100.0 * rise / traj[0]['bar']:+.2f}%) "
              f"over {span_h:.1f} h = {rise / span_h * 24:+.6f}/day")
        # The average rate is dominated by the early days; what matters for
        # pricing an endgame fire is the CURRENT rate, so report the last step
        # and the trailing window that actually contains a step.
        h = (traj[-1]["t"] - traj[-2]["t"]).total_seconds() / 3600.0
        d = traj[-1]["bar"] - traj[-2]["bar"]
        print(f"  most recent step {d:+.6f} over {h:.1f} h = {d / h * 24:+.6f}/day")
        for win in (48, 72, 96):
            recent = [s for s in traj
                      if (traj[-1]["t"] - s["t"]).total_seconds() <= win * 3600]
            if len(recent) > 1:
                rh = (recent[-1]["t"] - recent[0]["t"]).total_seconds() / 3600.0
                rr = recent[-1]["bar"] - recent[0]["bar"]
                print(f"  trailing {win} h: {rr:+.6f} over {rh:.1f} h "
                      f"= {rr / rh * 24:+.6f}/day")
    print()

    print("== closest approaches to the CONTEMPORANEOUS bar ==")
    print(f"  {'sub':<9}{'score':>12}{'bar':>12}{'gap':>11}{'gap%':>9}  created")
    for r in sorted(rows, key=lambda r: r["diff"], reverse=True)[:8]:
        print(f"  {r['sub']:<9}{r['score']:>12.6f}{r['bar']:>12.6f}"
              f"{r['diff']:>11.6f}{100.0 * r['diff'] / r['bar']:>8.2f}%  {r['created']}")
    print()
    print("== the endgame target is a MOVING one ==")
    last_bar = ordered[-1]["bar"]
    best = max(rows, key=lambda r: r["score"])
    print(f"  latest observed bar        {last_bar:.6f}  (sampled {ordered[-1]['created']})")
    print(f"  this account's best score  {best['score']:.6f} ({best['sub']}, {best['created']})")
    need = last_bar - best["score"]
    print(f"  still needed vs that bar   {need:+.6f} ({100.0 * need / best['score']:+.2f}% of score)")
    print("  NOTE the bar is only sampled when this account fires, so every step time")
    print("  above is an upper bound and the bar may already have moved again.")
    print()

    # --- are we closing the gap or losing the race? -------------------------
    print("== race: our best-so-far vs the bar ==")
    run_max, curve = -float("inf"), []
    for r in ordered:
        if r["score"] > run_max:
            run_max = r["score"]
            curve.append(r)
    print(f"  {'sub':<9}{'best-so-far':>13}{'bar then':>11}{'gap%':>9}  created")
    for r in curve:
        print(f"  {r['sub']:<9}{r['score']:>13.6f}{r['bar']:>11.6f}"
              f"{100.0 * r['diff'] / r['bar']:>8.2f}%  {r['created']}")
    for win in (48, 72, 96, 168):
        pts = [r for r in curve
               if (ordered[-1]["t"] - r["t"]).total_seconds() <= win * 3600]
        if len(pts) > 1:
            h = (pts[-1]["t"] - pts[0]["t"]).total_seconds() / 3600.0
            flag = "  <- span too short to trust" if h < 12 else ""
            print(f"  our rate, trailing {win:>3} h: "
                  f"{(pts[-1]['score'] - pts[0]['score']) / h * 24:+.6f}/day "
                  f"({len(pts)} record(s) spanning {h:.1f} h){flag}")
        else:
            print(f"  our rate, trailing {win:>3} h: no new record in window")

    # The trailing-window rates are contaminated by the steep pre-promotion climb.
    # The cleanest read of "are we winning" starts at the last time we were ahead.
    promo = [r for r in ordered if r["status"] == "promoted"]
    if promo:
        p = promo[-1]
        h = (ordered[-1]["t"] - p["t"]).total_seconds() / 3600.0
        ours = (best["score"] - p["score"]) / h * 24
        theirs = (last_bar - p["bar"]) / h * 24
        print()
        print(f"== since the last promotion ({p['sub']}, {p['created']}, {h:.1f} h) ==")
        print(f"  our best   {p['score']:.6f} -> {best['score']:.6f}  = {ours:+.6f}/day")
        print(f"  the bar    {p['bar']:.6f} -> {last_bar:.6f}  = {theirs:+.6f}/day")
        print(f"  gap        {100.0 * p['diff'] / p['bar']:+.2f}% -> "
              f"{100.0 * (best['score'] - last_bar) / last_bar:+.2f}%")
        net = ours - theirs
        print(f"  net closure {net:+.6f}/day -> "
              + (f"gap closes in {(last_bar - best['score']) / net:.1f} days"
                 if net > 0 else "WE ARE LOSING GROUND at this rate"))

    # That window contains the failure burst, during which fires returned nothing.
    # Rerun the same comparison over only the window in which fires were scoring.
    failed = [r for r in parse_all(text) if r["status"] == "failed"]
    if failed:
        f0 = max(failed, key=lambda r: r["t"] or dt.datetime.min)
        after = [r for r in ordered if r["t"] > f0["t"]]
        if len(after) > 1:
            h = (after[-1]["t"] - after[0]["t"]).total_seconds() / 3600.0
            # Seed the running max with the best score achieved BEFORE the window,
            # so "record" means a genuine new account best, not just a local high.
            prior = [r["score"] for r in ordered if r["t"] <= f0["t"]]
            rm, curve2 = (max(prior) if prior else -float("inf")), []
            for r in after:
                if r["score"] > rm:
                    rm, _ = r["score"], curve2.append(r)
            print()
            print(f"== since the last FAILED receipt ({f0['sub']}, {f0['created']}) ==")
            print(f"  {len(after)} scored fires over {h:.1f} h, "
                  f"{len(curve2)} new best-so-far records")
            if len(curve2) > 1:
                hc = (curve2[-1]["t"] - curve2[0]["t"]).total_seconds() / 3600.0
                ours2 = (curve2[-1]["score"] - curve2[0]["score"]) / hc * 24
                theirs2 = (after[-1]["bar"] - after[0]["bar"]) / h * 24
                print(f"  our rate {ours2:+.6f}/day (records span {hc:.1f} h)")
                print(f"  bar rate {theirs2:+.6f}/day")
                net2 = ours2 - theirs2
                gap = after[-1]["bar"] - max(r["score"] for r in after)
                print(f"  net {net2:+.6f}/day -> "
                      + (f"gap {gap:.6f} closes in {gap / net2:.1f} days if this holds"
                         if net2 > 0 else "still losing ground"))
                stale = (ordered[-1]["t"] - curve2[-1]["t"]).total_seconds() / 3600.0
                print(f"  but no new record for {stale:.1f} h - the rate above is only")
                print("  real if fires resume producing records.")


if __name__ == "__main__":
    main()
