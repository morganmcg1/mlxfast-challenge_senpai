#!/usr/bin/env python3
"""Research-only ABBA statistics for the compiled-elementwise-fusion probe.

  python3 research/nezuko_compile_stats.py <outdir> [--warmup 8] [--removed N]

Reports per-arm steady-state us/step, the block-paired U-minus-C contrast with
a Student t interval, and (when --removed is given) the refund in us per
removed GPU dispatch.
"""
import argparse
import glob
import json
import math
import os
import statistics
import sys


T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
        7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 15: 2.131, 20: 2.086}


def t_quantile(df):
    return T975.get(df, 1.96 if df > 30 else 2.2)


def steady_us(rec, warmup):
    return [v * 1e3 for v in rec["step_ms"][warmup:]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--warmup", type=int, default=8)
    ap.add_argument("--removed", type=float, default=None,
                    help="dispatches removed per decode step by the C arm")
    args = ap.parse_args()

    runs = []
    for path in sorted(glob.glob(os.path.join(args.outdir, "s*_*.json"))):
        with open(path) as fh:
            rec = json.load(fh)
        arm = os.path.basename(path).split("_")[1].split(".")[0]
        runs.append((arm, rec, steady_us(rec, args.warmup)))

    tokens = {}
    for arm, rec, _ in runs:
        tokens.setdefault(arm, set()).add(tuple(rec["produced_tokens"]))
    print("token identity:")
    for arm in sorted(tokens):
        div = max(r["golden_divergences"] for a, r, _ in runs if a == arm)
        print(f"  arm {arm}: {len(tokens[arm])} distinct sequence(s), "
              f"max golden_divergences={div}")
    if "C" in tokens and "U" in tokens:
        same = tokens["C"] == tokens["U"]
        print(f"  C vs U bit-identical token stream: {same}")

    print("\nper-run steady-state us/step:")
    for arm, rec, us in runs:
        print(f"  {rec['label']:>10s} arm={arm} n={len(us)} "
              f"mean={statistics.mean(us):9.2f} "
              f"median={statistics.median(us):9.2f} "
              f"sd={statistics.stdev(us):7.2f}")

    per_arm = {}
    for arm, _, us in runs:
        per_arm.setdefault(arm, []).append(statistics.mean(us))
    print("\nper-arm run means (us/step):")
    for arm in sorted(per_arm):
        v = per_arm[arm]
        line = f"  {arm}: n={len(v)} mean={statistics.mean(v):9.2f}"
        if len(v) > 1:
            line += f" sd={statistics.stdev(v):7.2f}"
        print(line + "  " + " ".join(f"{x:.1f}" for x in v))

    cu = [(a, m) for a, m in
          ((arm, statistics.mean(us)) for arm, _, us in runs) if a in ("C", "U")]
    blocks = [cu[i:i + 4] for i in range(0, len(cu) - len(cu) % 4, 4)]
    deltas = []
    for blk in blocks:
        c = [m for a, m in blk if a == "C"]
        u = [m for a, m in blk if a == "U"]
        if len(c) == 2 and len(u) == 2:
            deltas.append(statistics.mean(u) - statistics.mean(c))
    if deltas:
        d = statistics.mean(deltas)
        print(f"\nblock-paired (U - C) us/step over {len(deltas)} ABBA block(s): "
              + " ".join(f"{x:+.1f}" for x in deltas))
        if len(deltas) > 1:
            sd = statistics.stdev(deltas)
            se = sd / math.sqrt(len(deltas))
            t = d / se if se else float("nan")
            half = t_quantile(len(deltas) - 1) * se
            print(f"  mean={d:+.2f} sd={sd:.2f} se={se:.2f} t={t:+.2f} "
                  f"95%CI~[{d - half:+.2f}, {d + half:+.2f}]")
        else:
            print(f"  mean={d:+.2f} (single block, no interval)")
        if args.removed:
            print(f"  refund = {d / args.removed:+.3f} us per removed dispatch "
                  f"({args.removed:g} removed/step)")
            if len(deltas) > 1:
                print(f"           CI ~ [{(d - half) / args.removed:+.3f}, "
                      f"{(d + half) / args.removed:+.3f}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
