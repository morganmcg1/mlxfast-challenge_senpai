#!/usr/bin/env python3
"""Paired statistics for the R119-A routed-grid append ABBA.

Consumes the per-step CSV dumps written by
`research/maple-alphonse-r119-gridappend-abba.sh` (one millisecond value per
line, one file per worker process) and reports, for one candidate arm against
the `C`/`N` reference arm:

  * per-run trimmed medians and the bimodality screen on the raw samples;
  * block deltas (mean of the candidate runs minus mean of the reference runs
    inside each mirrored quadruple);
  * adjacent-pair deltas (disjoint neighbouring reference/candidate runs);
  * a Welch two-sample interval over the per-run medians; and
  * a bootstrap interval on the median paired saving.

Usage:
  research/maple-alphonse-r119-gridappend-stats.py OUTDIR [--arm F] [--ref C]
"""
import argparse
import glob
import math
import os
import random
import re
import statistics
import sys

WARMUP = int(os.environ.get("R119_WARMUP_STEPS", "16"))
# The R114-E QKV+gate_sp append absorbed 76.8 us/step. The advisor's joint
# point estimate for instances 2 and 3 is 60 us/step and the interim stop rule
# is 30 us/step.
BAR_US = 30.0

T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
       14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
       20: 2.086, 24: 2.064, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}


def t95(df: int) -> float:
    if df <= 0:
        return float("nan")
    for k in sorted(T95):
        if df <= k:
            return T95[k]
    return 1.960


def load_run(path):
    with open(path) as fh:
        vals = [float(x) for x in fh if x.strip()]
    return vals


def bimodality(vals):
    """Bimodality coefficient; > 5/9 is the classical bimodal flag."""
    n = len(vals)
    m = statistics.mean(vals)
    sd = statistics.pstdev(vals)
    if sd == 0:
        return float("nan")
    g1 = sum(((v - m) / sd) ** 3 for v in vals) / n
    g2 = sum(((v - m) / sd) ** 4 for v in vals) / n - 3.0
    return (g1 * g1 + 1.0) / (g2 + 3.0 * (n - 1) ** 2 / ((n - 2) * (n - 3)))


def interval(deltas, label, n_eff=None):
    n = len(deltas)
    if n < 2:
        print(f"  {label}: n={n} (need >= 2)")
        return
    mean = statistics.mean(deltas)
    sd = statistics.stdev(deltas)
    se = sd / math.sqrt(n)
    df = n - 1 if n_eff is None else n_eff
    half = t95(df) * se
    lo, hi = mean - half, mean + half
    verdict = "EXCLUDES ZERO" if lo * hi > 0 else "includes zero"
    bar = "clears bar" if hi < -BAR_US else "does not clear bar"
    print(f"  {label}: n={n} mean={mean*1e3:+.1f} us sd={sd*1e3:.1f} "
          f"se={se*1e3:.1f} 95%CI=[{lo*1e3:+.1f}, {hi*1e3:+.1f}] us "
          f"-> {verdict}, {bar}")


def bootstrap_median(ref, cand, reps=20000, seed=20260811):
    rng = random.Random(seed)
    base = statistics.median(cand) - statistics.median(ref)
    draws = []
    for _ in range(reps):
        r = [rng.choice(ref) for _ in ref]
        c = [rng.choice(cand) for _ in cand]
        draws.append(statistics.median(c) - statistics.median(r))
    draws.sort()
    lo = draws[int(0.025 * reps)]
    hi = draws[int(0.975 * reps)]
    verdict = "EXCLUDES ZERO" if lo * hi > 0 else "includes zero"
    print(f"  bootstrap(median of per-run medians): delta={base*1e3:+.1f} us "
          f"95%CI=[{lo*1e3:+.1f}, {hi*1e3:+.1f}] us -> {verdict}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--arm", default="F")
    ap.add_argument("--ref", default="C")
    ap.add_argument("--passlen", type=int, default=10,
                    help="runs per pass through the arm sequence")
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.outdir, "*.steps.csv")))
    if not paths:
        print(f"no per-step CSVs under {args.outdir}", file=sys.stderr)
        return 2

    runs = []  # (index, arm, samples)
    for p in paths:
        m = re.search(r"_(\d+)_([A-Z])\.steps\.csv$", p)
        if not m:
            continue
        vals = load_run(p)
        if len(vals) <= WARMUP:
            print(f"run {p} has {len(vals)} samples <= warmup {WARMUP}",
                  file=sys.stderr)
            return 2
        runs.append((int(m.group(1)), m.group(2), vals[WARMUP:], p))
    runs.sort()

    print(f"warmup discarded per run: {WARMUP} steps")
    print(f"arm={args.arm} vs ref={args.ref}\n")
    print("per-run summary (measured samples only):")
    for idx, arm, vals, p in runs:
        bc = bimodality(vals)
        flag = "  BIMODAL?" if bc == bc and bc > 5 / 9 else ""
        print(f"  {idx:02d} {arm} n={len(vals)} median={statistics.median(vals):.4f} ms "
              f"mean={statistics.mean(vals):.4f} ms "
              f"p10={statistics.quantiles(vals, n=10)[0]:.4f} "
              f"p90={statistics.quantiles(vals, n=10)[8]:.4f} "
              f"bimodality={bc:.3f}{flag}")

    sel = [r for r in runs if r[1] in (args.arm, args.ref)]
    med = {idx: statistics.median(vals) for idx, _, vals, _ in sel}
    ref_idx = [idx for idx, arm, _, _ in sel if arm == args.ref]
    cand_idx = [idx for idx, arm, _, _ in sel if arm == args.arm]
    if not ref_idx or not cand_idx:
        print("arm or ref missing from this directory", file=sys.stderr)
        return 2

    print("\nestimators on per-run medians (candidate minus reference):")
    # Block deltas: one block per pass through the arm sequence. Consecutive
    # passes alternate between the forward order and its mirror, so a block
    # delta is immune to drift that is linear across a pass.
    order = [(idx, arm) for idx, arm, _, _ in sel]
    all_idx = sorted(idx for idx, _, _, _ in runs)
    pass_of = {idx: (n // args.passlen) for n, idx in enumerate(all_idx)}
    blocks = []
    for p in sorted(set(pass_of.values())):
        r = [med[i] for i, a in order if a == args.ref and pass_of[i] == p]
        c = [med[i] for i, a in order if a == args.arm and pass_of[i] == p]
        if r and c:
            blocks.append(statistics.mean(c) - statistics.mean(r))
    interval(blocks, f"block deltas (one per pass of {args.passlen} runs)")

    print("  per-order breakdown (even pass = forward, odd pass = mirror):")
    for name, keep in (("forward", 0), ("mirror", 1)):
        r = [med[i] for i, a in order if a == args.ref and pass_of[i] % 2 == keep]
        c = [med[i] for i, a in order if a == args.arm and pass_of[i] % 2 == keep]
        if r and c:
            d = (statistics.mean(c) - statistics.mean(r)) * 1e3
            print(f"    {name}: nref={len(r)} ncand={len(c)} "
                  f"ref_median={statistics.median(r):.4f} ms "
                  f"cand_median={statistics.median(c):.4f} ms delta={d:+.1f} us")

    # Adjacent disjoint reference/candidate pairs.
    pairs = []
    i = 0
    while i < len(order) - 1:
        (i0, a0), (i1, a1) = order[i], order[i + 1]
        if a0 != a1:
            d = med[i1] - med[i0] if a1 == args.arm else med[i0] - med[i1]
            pairs.append(d)
            i += 2
        else:
            i += 1
    interval(pairs, "adjacent-pair deltas")

    # Welch over per-run medians.
    r = [med[i] for i in ref_idx]
    c = [med[i] for i in cand_idx]
    if len(r) >= 2 and len(c) >= 2:
        vr, vc = statistics.variance(r), statistics.variance(c)
        se = math.sqrt(vr / len(r) + vc / len(c))
        dfw = ((vr / len(r) + vc / len(c)) ** 2
               / ((vr / len(r)) ** 2 / (len(r) - 1)
                  + (vc / len(c)) ** 2 / (len(c) - 1))) if se > 0 else 0
        delta = statistics.mean(c) - statistics.mean(r)
        half = t95(int(dfw)) * se
        lo, hi = delta - half, delta + half
        verdict = "EXCLUDES ZERO" if lo * hi > 0 else "includes zero"
        bar = "clears bar" if hi < -BAR_US else "does not clear bar"
        print(f"  welch (unpaired, per-run medians): nref={len(r)} ncand={len(c)} "
              f"delta={delta*1e3:+.1f} us df={dfw:.1f} "
              f"95%CI=[{lo*1e3:+.1f}, {hi*1e3:+.1f}] us -> {verdict}, {bar}")

    bootstrap_median(r, c)
    print(f"\nbar for the interim stop rule: {BAR_US:.1f} us/step")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
