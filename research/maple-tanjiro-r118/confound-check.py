#!/usr/bin/env python3
"""R118-A: two checks the pre-registration did not contain, added after an
adversarial read of the draft.

1.  DIVERGENCE CONFOUND.  A dose arm perturbs the shared expert's output, so the
    router's top-8 *selection* can change on some steps.  The trajectory does not
    change (decode_probe.py is teacher-forced) and the dispatch shapes do not
    change (top-8 is top-8), but the gathered expert *addresses* do, which is a
    cache-locality effect that could cost time.  If it does, then the dose arm's
    measured saving UNDERSTATES the value of deleting the interior, and my 95 %
    upper bound is biased low -- against my own conclusion.  So: within each arm,
    regress the run's median step time on the run's divergence count.  A slope
    indistinguishable from zero bounds the confound.

2.  EXACT SIGN TEST on the paired block differences, as a distribution-free
    companion to the block bootstrap (which has only 6-10 exchangeable units).

Reads the abba.tsv written by qmv-dose-abba.sh.  No model, no GPU, no build.
"""
import argparse
import csv
import math
import os
import sys
from collections import defaultdict


def read_tsv(path):
    rows = []
    with open(path) as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                rows.append({
                    "idx": int(r["idx"]),
                    "arm": r["arm"],
                    "mean_ms": float(r["mean_ms"]),
                    "median_ms": float(r["median_ms"]),
                    "diverg": int(r["diverg"]),
                })
            except (ValueError, KeyError):
                continue
    return rows


def ols(xs, ys):
    """Slope, intercept, r, and a t-statistic for slope=0."""
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0.0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    b = sxy / sxx
    a = my - b * mx
    resid = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    dof = n - 2
    se = math.sqrt(resid / dof / sxx) if dof > 0 and resid > 0 else 0.0
    t = b / se if se > 0 else float("inf") if b != 0 else 0.0
    r = sxy / math.sqrt(sxx * syy) if syy > 0 else 0.0
    return {"slope": b, "intercept": a, "r": r, "t": t, "se": se, "n": n,
            "xspan": (min(xs), max(xs))}


def binom_two_sided(k, n):
    """Exact two-sided sign-test p-value for k successes out of n at p=0.5."""
    def c(n, r):
        return math.comb(n, r)
    tail = sum(c(n, i) for i in range(0, min(k, n - k) + 1))
    p = 2.0 * tail / (2.0 ** n)
    return min(1.0, p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--ref", default="ship")
    args = ap.parse_args()

    tsv = os.path.join(args.dir, "abba.tsv")
    rows = read_tsv(tsv)
    if not rows:
        print(f"no usable rows in {tsv}")
        return 1
    print(f"=== {tsv}: {len(rows)} runs")

    arms = []
    for r in rows:
        if r["arm"] not in arms:
            arms.append(r["arm"])

    # ---- 1. divergence confound -------------------------------------------
    print("\n--- divergence confound: median_ms ~ diverg, within arm ---")
    print(f"{'arm':>6} {'n':>3} {'diverg span':>14} {'slope us/diverg':>16} "
          f"{'t':>7} {'r':>7}  reading")
    for arm in arms:
        sub = [r for r in rows if r["arm"] == arm]
        xs = [r["diverg"] for r in sub]
        ys = [r["median_ms"] * 1000.0 for r in sub]   # us
        span = f"{min(xs)}..{max(xs)}"
        if len(set(xs)) < 2:
            print(f"{arm:>6} {len(sub):>3} {span:>14} {'--':>16} {'--':>7} "
                  f"{'--':>7}  constant divergence, no confound to fit")
            continue
        f = ols(xs, ys)
        if f is None:
            print(f"{arm:>6} {len(sub):>3} {span:>14} {'--':>16}")
            continue
        # how much of the arm's whole divergence range could the fit explain?
        swing = f["slope"] * (f["xspan"][1] - f["xspan"][0])
        reading = ("no measurable divergence cost" if abs(f["t"]) < 2.0
                   else f"SLOPE SIGNIFICANT: {swing:+.1f} us over the range")
        print(f"{arm:>6} {len(sub):>3} {span:>14} {f['slope']:+16.4f} "
              f"{f['t']:+7.2f} {f['r']:+7.3f}  {reading}")

    # ---- 2. exact sign test on paired block differences --------------------
    # A block is a consecutive group of len(arms) runs containing each arm once.
    k = len(arms)
    blocks = defaultdict(dict)
    for r in rows:
        blocks[(r["idx"] - 1) // k][r["arm"]] = r
    good = [b for b in sorted(blocks) if len(blocks[b]) == k]
    print(f"\n--- exact sign test on {len(good)} complete blocks "
          f"(paired saving vs {args.ref}, positive = arm faster) ---")
    print(f"{'arm':>6} {'blocks':>7} {'pos':>4} {'median us':>11} "
          f"{'p (two-sided)':>14}")
    for arm in arms:
        if arm == args.ref:
            continue
        diffs = []
        for b in good:
            if args.ref not in blocks[b] or arm not in blocks[b]:
                continue
            d = (blocks[b][args.ref]["median_ms"]
                 - blocks[b][arm]["median_ms"]) * 1000.0
            diffs.append(d)
        if not diffs:
            continue
        pos = sum(1 for d in diffs if d > 0)
        n = sum(1 for d in diffs if d != 0)
        diffs.sort()
        m = (diffs[len(diffs) // 2] if len(diffs) % 2
             else 0.5 * (diffs[len(diffs) // 2 - 1] + diffs[len(diffs) // 2]))
        p = binom_two_sided(pos, n) if n else 1.0
        print(f"{arm:>6} {len(diffs):>7} {pos:>4} {m:>+11.2f} {p:>14.4f}")
    print("\n(Sign test is on per-run medians, so it is coarser than the "
          "step-level bootstrap; it is here because it needs no distributional "
          "assumption and stays exact at n=6..10.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
