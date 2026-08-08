#!/usr/bin/env python3
"""Research-only analysis for the PR #441 decode router tournament ABBA.

  python3 research/nezuko_q12_stats.py /tmp/nezq12/orderA /tmp/nezq12/orderB [--trim 0.05]

Reuses the estimator, interference screen, block-paired contrast, and two-way
fixed-effects solver from `research/nezuko_pr309_stats.py`. Every extra output
directory is a separate `ORDER` direction (standing rule 36); its blocks are
renumbered into a disjoint range so the block dummies absorb the order effect
and every arm contrast is estimated strictly within a block.
"""
import argparse
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nezuko_pr309_stats as S  # noqa: E402

DISPATCHES_PER_STEP = 39  # sparse MoE layers, research/nezuko-a2-roofline.txt:36-37
DECODE_PCT_PER_US = 0.015280

S.ARMS = ["off", "on", "inert"]
S.REF = "off"
S.ARM_DESC = {
    "off": "incumbent full-256 bitonic network (12 charged TG barriers)",
    "on": "two-phase block tournament, 8x32 then 64 (3 charged TG barriers)",
    "inert": "incumbent network, distinct kernel name + no-op MSL suffix (rule 3)",
}
S.CONTRASTS = [
    ("on-off", "on", "off", "HEADLINE: tournament vs incumbent"),
    ("inert-off", "inert", "off", "NULL: identical work, distinct pipeline object"),
    ("on-inert", "on", "inert", "tournament net of the pipeline-identity null"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdirs", nargs="+")
    ap.add_argument("--warmup", type=int, default=8)
    ap.add_argument("--trim", type=float, default=0.0)
    args = ap.parse_args()

    runs = []
    for d, outdir in enumerate(args.outdirs):
        got = [r for r in S.load(outdir, args.warmup, args.trim) if r[1] > 0]
        print(f"{os.path.basename(outdir)}: {len(got)} usable runs")
        runs += [(r[0], r[1] + 100 * d, *r[2:]) for r in got]
    if not runs:
        print("no usable runs", file=sys.stderr)
        return 1
    runs.sort()
    blocks = sorted({r[1] for r in runs})
    est = "mean" if args.trim <= 0 else f"upper-{args.trim:.0%}-trimmed mean"
    print(f"\n{len(runs)} runs over blocks {blocks}, warmup={args.warmup} dropped, "
          f"{runs[0][5]} steps/run kept, per-run estimator = {est}")
    S.interference_report(runs)

    print("\narm     n  mean_us   sd_of_run_means  within_run_sd   description")
    for arm in S.ARMS:
        ms = [r[3] for r in runs if r[2] == arm]
        ws = [r[4] for r in runs if r[2] == arm]
        sd = statistics.stdev(ms) if len(ms) > 1 else float("nan")
        print(f"{arm:<5} {len(ms):>3} {statistics.mean(ms):9.1f} {sd:14.1f} "
              f"{statistics.mean(ws):14.1f}   {S.ARM_DESC[arm]}")

    per, deltas = S.block_paired(runs, blocks)
    print("\nper-block arm means (us/step)")
    print("block " + "".join(f"{a:>10}" for a in S.ARMS))
    for blk in blocks:
        row = "".join(f"{statistics.mean(per[(blk, a)]):10.1f}"
                      if (blk, a) in per else f"{'-':>10}" for a in S.ARMS)
        print(f"{blk:>5} {row}")

    effect, se_diff, odf, rsd = S.ols(runs, blocks)
    print(f"\ntwo-way fixed effects: residual sd {rsd:.1f} us over {odf} df")

    print("\ncontrast      block-paired (us/step)              fixed-effects (us/step)")
    print(f"{'':<12} {'mean':>8} {'sd':>7} {'t':>6} {'95% CI':>18}    "
          f"{'mean':>8} {'se':>6} {'t':>6} {'95% CI':>18}   meaning")
    fx = {}
    for name, a, b, desc in S.CONTRASTS:
        d = deltas.get(name, [])
        m = statistics.mean(d)
        sd = statistics.stdev(d)
        se = sd / math.sqrt(len(d))
        h = S.t95(len(d) - 1) * se
        bp = f"{m:8.1f} {sd:7.1f} {m / se:6.2f}  [{m - h:7.1f},{m + h:7.1f}]"
        om = effect(a) - effect(b)
        ose, _ = se_diff(a, b)
        oh = S.t95(odf) * ose
        fx[name] = (om, oh)
        print(f"{name:<12} {bp}    {om:8.1f} {ose:6.1f} {om / ose:6.2f} "
              f" [{om - oh:7.1f},{om + oh:7.1f}]   {desc}")

    print(f"\nconversion ({DISPATCHES_PER_STEP} dispatches/step, "
          f"{DECODE_PCT_PER_US} %/us of score)")
    print(f"{'contrast':<12} {'us/step':>9} {'95% CI':>20} {'us/call':>9} "
          f"{'%score':>8} {'95% CI':>18}")
    for name, _, _, _ in S.CONTRASTS:
        m, h = fx[name]
        print(f"{name:<12} {m:9.1f}  [{m - h:8.1f},{m + h:8.1f}] "
              f"{m / DISPATCHES_PER_STEP:9.3f} {-m * DECODE_PCT_PER_US:8.3f} "
              f" [{-(m + h) * DECODE_PCT_PER_US:7.3f},"
              f"{-(m - h) * DECODE_PCT_PER_US:7.3f}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
