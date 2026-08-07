#!/usr/bin/env python3
"""PR #218 duplicate-injection ledger statistics (research-only).

Reads the per-step millisecond dumps produced by `research/fern_dup_run.sh`
and prices one decode dispatch family's marginal cost.

File naming contract (produced by `research/fern_dup_ab.sh`):

    <OUTDIR>/b<block>_p<pos>_k<K>.steps.txt

`block` is a palindromic replication block, `pos` the arm's position inside it,
and `K` the number of copies of the target dispatch issued per call.

Reduction (pre-registered):
  * drop the first `--warmup` steps of every run (default 16);
  * the run MEDIAN is the unit of replication -- never an individual step;
  * arms are contrasted only within a block, so a linear session drift cancels;
  * the reported slope is OLS of block-paired run medians on K.

Definitions:
  marginal cost  us/step per copy-set = d(step time)/dK
  exposure E     = marginal cost / census cost (census supplied by --census)
  shadow ratio   = smallest K whose paired contrast against K=1 is significant
                   (>1 means the family is hidden behind a longer concurrent
                   path and only surfaces once duplicated that many times;
                   1 means it is on the critical path already)
"""
import argparse
import math
import os
import re
import statistics
import sys
from collections import defaultdict

NAME = re.compile(r"^b(\d+)_p(\d+)_k(\d+)\.steps\.txt$")


def load(path, warmup):
    with open(path) as fh:
        vals = [float(x) for x in fh.read().split()]
    return vals[warmup:]


def welch(a, b):
    """Return (mean diff b-a, se, t, df) for two independent samples."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return statistics.mean(b) - statistics.mean(a), float("nan"), float("nan"), 0
    va, vb = statistics.variance(a), statistics.variance(b)
    se = math.sqrt(va / na + vb / nb)
    diff = statistics.mean(b) - statistics.mean(a)
    if se == 0:
        return diff, 0.0, float("inf"), na + nb - 2
    df = (va / na + vb / nb) ** 2 / (
        (va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    return diff, se, diff / se, df


def ols(xs, ys):
    """Slope, intercept, slope standard error."""
    n = len(xs)
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0 or n < 3:
        return float("nan"), float("nan"), float("nan")
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    resid = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    s2 = sum(r * r for r in resid) / (n - 2)
    return slope, intercept, math.sqrt(s2 / sxx)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--warmup", type=int, default=16)
    ap.add_argument("--census", type=float, default=None,
                    help="isolated GPU us/step for this family, for exposure E")
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    runs = []  # (block, pos, K, median_ms, n_steps)
    for fn in sorted(os.listdir(args.outdir)):
        m = NAME.match(fn)
        if not m:
            continue
        block, pos, k = int(m.group(1)), int(m.group(2)), int(m.group(3))
        vals = load(os.path.join(args.outdir, fn), args.warmup)
        if len(vals) < 32:
            print(f"WARNING: {fn} has only {len(vals)} timed steps", file=sys.stderr)
        runs.append((block, pos, k, statistics.median(vals), len(vals)))
    if not runs:
        print("no matching b<block>_p<pos>_k<K>.steps.txt files", file=sys.stderr)
        return 2

    ks = sorted({r[2] for r in runs})
    blocks = sorted({r[0] for r in runs})
    print(f"== {args.label or args.outdir} ==")
    print(f"K arms: {ks}   blocks: {blocks}   runs: {len(runs)}   "
          f"warmup dropped: {args.warmup}")
    print(f"\n{'K':>3} {'runs':>5} {'median of run-medians (ms)':>28} "
          f"{'spread p100-p0 (us)':>20}")
    by_k = defaultdict(list)
    for b, p, k, med, n in runs:
        by_k[k].append(med)
    for k in ks:
        v = sorted(by_k[k])
        print(f"{k:>3} {len(v):>5} {statistics.median(v):>28.6f} "
              f"{(v[-1]-v[0])*1e3:>20.1f}")

    # Block-paired contrasts against K=1.
    if 1 not in by_k:
        print("\nno K=1 arm; cannot form paired contrasts", file=sys.stderr)
        return 2
    print(f"\nblock-paired contrast vs K=1 "
          f"(per block: median(K) - median(K=1), us/step)")
    print(f"{'K':>3} " + " ".join(f"{'b'+str(b):>9}" for b in blocks)
          + f" {'mean':>9} {'se':>8} {'t':>7} {'us/copy':>9}")
    paired = defaultdict(list)  # K -> [per-block delta us]
    for k in ks:
        if k == 1:
            continue
        cells = []
        for b in blocks:
            base = [r[3] for r in runs if r[0] == b and r[2] == 1]
            arm = [r[3] for r in runs if r[0] == b and r[2] == k]
            if not base or not arm:
                cells.append(float("nan"))
                continue
            d = (statistics.median(arm) - statistics.median(base)) * 1e3
            cells.append(d)
            paired[k].append(d)
        good = [c for c in cells if not math.isnan(c)]
        mean = statistics.mean(good) if good else float("nan")
        se = (statistics.stdev(good) / math.sqrt(len(good))
              if len(good) > 1 else float("nan"))
        t = mean / se if se and not math.isnan(se) and se > 0 else float("nan")
        print(f"{k:>3} " + " ".join(f"{c:>9.1f}" for c in cells)
              + f" {mean:>9.1f} {se:>8.1f} {t:>7.2f} {mean/(k-1):>9.1f}")

    # OLS on every run median (K as regressor), plus block-mean-centred version.
    xs = [r[2] for r in runs]
    ys = [r[3] * 1e3 for r in runs]
    slope, _, se = ols(xs, ys)
    print(f"\nOLS slope over raw run medians: {slope:.1f} +- {se:.1f} us/step "
          f"per copy-set   95% CI [{slope-1.96*se:.1f}, {slope+1.96*se:.1f}]")

    centred_x, centred_y = [], []
    for b in blocks:
        rows = [r for r in runs if r[0] == b]
        if len(rows) < 2:
            continue
        my = statistics.mean(r[3] * 1e3 for r in rows)
        mx = statistics.mean(r[2] for r in rows)
        for r in rows:
            centred_x.append(r[2] - mx)
            centred_y.append(r[3] * 1e3 - my)
    cslope, _, cse = ols(centred_x, centred_y)
    print(f"OLS slope, block-centred (drift-cancelling): "
          f"{cslope:.1f} +- {cse:.1f} us/step per copy-set   "
          f"95% CI [{cslope-1.96*cse:.1f}, {cslope+1.96*cse:.1f}]")

    # Saturation: per-copy increment in the low-K and high-K regimes.
    if len(ks) >= 3:
        lo, hi = ks[1], ks[-1]
        mid = ks[len(ks) // 2]
        def per_copy(a, b):
            if a not in by_k or b not in by_k:
                return float("nan")
            return ((statistics.median(by_k[b]) - statistics.median(by_k[a]))
                    * 1e3 / (b - a))
        print(f"\nsaturation check: K=1->{lo} costs {per_copy(1, lo):.1f} us/copy, "
              f"K={mid}->{hi} costs {per_copy(mid, hi):.1f} us/copy "
              f"(equal => linear, no saturation)")

    # Shadow ratio: first K whose paired contrast clears 2 sigma.
    shadow = None
    for k in ks:
        if k == 1:
            continue
        d = paired.get(k, [])
        if len(d) > 1:
            m = statistics.mean(d)
            s = statistics.stdev(d) / math.sqrt(len(d))
            if s > 0 and m / s > 2:
                shadow = k
                break
    print(f"shadow ratio (first K with a >2 sigma paired increase): "
          + (f"{shadow}" if shadow else f">{ks[-1]} (never surfaced)")
          + ("   FLAG: <3, thin margin, M5 could flip this row"
             if shadow is not None and shadow < 3 and shadow > 1 else ""))

    if args.census:
        e = cslope / args.census
        elo = (cslope - 1.96 * cse) / args.census
        ehi = (cslope + 1.96 * cse) / args.census
        print(f"\nexposure E = marginal/census = {cslope:.1f}/{args.census:.1f} "
              f"= {e:.3f}   95% CI [{elo:.3f}, {ehi:.3f}]")
        print(f"verdict: " + ("chain-link (E > 0.5)" if e > 0.5
                              else "side-branch (E < 0.5)"))
        print(f"score value of deleting it outright: "
              f"{cslope * 0.015280:.3f}% (at 0.015280 %/us)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
