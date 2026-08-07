#!/usr/bin/env python3
"""Research-only analysis for research/fern_dup_probe.py output (PR #218).

Unit of replication is the SEGMENT MEDIAN, never the individual step: steps
inside a segment share one cache, one allocator state and one thermal state, so
they are not independent draws. Each palindromic block contributes two segments
per arm, and every contrast is formed inside a block so linear drift cancels.

  python3 research/fern_dup_stats.py /tmp/t0a.tsv [--census 185.7] [--calls 39]
"""
import argparse
import math
import statistics
import sys
from collections import defaultdict

# Scored decode price at the promoted receipt: 1 us removed from the steady
# per-step time is worth this much of the official score (see the PR body).
PERCENT_PER_US = 0.015280
HOST_STEP_MS = 8.20   # measured M4 Pro steady one-token decode step
M5_STEP_MS = 4.143569  # promoted M5 receipt 97a5090


def student_t95(df: int) -> float:
    table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
             7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131,
             20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000}
    for k in sorted(table):
        if df <= k:
            return table[k]
    return 1.96


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv")
    ap.add_argument("--census", type=float, default=None,
                    help="GPUPROF us/step attributed to this family")
    ap.add_argument("--calls", type=int, default=None,
                    help="injected calls per step (DUPCOUNT census)")
    args = ap.parse_args()

    header, rows, drop = read_tsv(args.tsv)
    print(header.strip())

    seg_k, seg_med = {}, {}
    per_seg = defaultdict(list)
    for seg, k, step, ms in rows:
        seg_k[seg] = k
        if step >= drop:
            per_seg[seg].append(ms)
    for seg, vals in per_seg.items():
        seg_med[seg] = statistics.median(vals)

    segments = sorted(seg_med)
    arms = sorted({seg_k[s] for s in segments})
    block_len = detect_block_len([seg_k[s] for s in segments])
    print(f"\nsegments={len(segments)} arms={arms} block_len={block_len} "
          f"blocks={len(segments)//block_len} timed_steps_per_segment="
          f"{len(per_seg[segments[0]])}")

    per_block = defaultdict(dict)
    print(f"\n{'seg':>4} {'K':>3} {'block':>5} {'median_ms':>10}")
    for s in segments:
        print(f"{s:4d} {seg_k[s]:3d} {s//block_len:5d} {seg_med[s]:10.4f}")
        per_block[s // block_len].setdefault(seg_k[s], []).append(seg_med[s])

    blocks = sorted(per_block)
    print("\nblock-paired contrasts vs K=1 (total us added per step)")
    print(f"{'K':>3} {'mean_us':>10} {'se':>8} {'t':>7} {'ci95_lo':>9} "
          f"{'ci95_hi':>9}  per-block")
    contrasts = {}
    for k in arms:
        if k == 1:
            continue
        deltas = []
        for b in blocks:
            if 1 not in per_block[b] or k not in per_block[b]:
                continue
            deltas.append(
                (statistics.mean(per_block[b][k])
                 - statistics.mean(per_block[b][1])) * 1e3)
        if len(deltas) < 2:
            continue
        m = statistics.mean(deltas)
        se = statistics.stdev(deltas) / math.sqrt(len(deltas))
        t = m / se if se else float("inf")
        h = student_t95(len(deltas) - 1) * se
        contrasts[k] = (m, se, t)
        print(f"{k:3d} {m:10.2f} {se:8.2f} {t:7.2f} {m-h:9.2f} {m+h:9.2f}  "
              + " ".join(f"{d:.1f}" for d in deltas))

    # Within-block-centred OLS slope of segment median on K.
    xs, ys = [], []
    for b in blocks:
        if 1 not in per_block[b]:
            continue
        base = statistics.mean(per_block[b][1])
        for k, vals in per_block[b].items():
            for v in vals:
                xs.append(float(k))
                ys.append((v - base) * 1e3)
    xbar = statistics.mean(xs)
    sxx = sum((x - xbar) ** 2 for x in xs)
    ybar = statistics.mean(ys)
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / sxx
    intercept = ybar - slope * xbar
    df = len(xs) - len(blocks) - 1
    resid = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    s2 = sum(r * r for r in resid) / df
    se_slope = math.sqrt(s2 / sxx)
    h = student_t95(df) * se_slope
    print(f"\nOLS slope (block-centred, df={df}): "
          f"{slope:.2f} +/- {se_slope:.2f} us per extra copy-set per step, "
          f"95% CI [{slope-h:.2f}, {slope+h:.2f}], t={slope/se_slope:.2f}")
    frac = slope / (HOST_STEP_MS * 1000.0)
    print(f"share of the {HOST_STEP_MS:.2f} ms host decode step: "
          f"{frac*100:.2f} % (CI [{(slope-h)/(HOST_STEP_MS*10.0):.2f}, "
          f"{(slope+h)/(HOST_STEP_MS*10.0):.2f}] %)")
    # Cross-machine: hold the *fraction* of the step, not the microseconds,
    # then price the equivalent M5 microseconds. Directional only.
    print("  if that share transferred to the M5 ranked step: "
          f"{frac*M5_STEP_MS*1000.0*PERCENT_PER_US:+.3f} % of score "
          "(directional, not a ranked claim)")

    # Two-regime hinge: injected independent work is absorbed free until the
    # step's idle-GPU slack is exhausted, then passes through at a fixed rate.
    big = [k for k in arms if k in contrasts]
    if len(big) >= 2:
        k1, k2 = big[-2], big[-1]
        m1, m2 = contrasts[k1][0], contrasts[k2][0]
        rate = (m2 - m1) / float(k2 - k1)
        if rate > 0:
            knee = (k2 - 1) - m2 / rate
            print(f"\ntwo-regime hinge (arms K={k1},{k2}): saturated marginal "
                  f"cost {rate:.2f} us per copy-set; absorbed slack "
                  f"{knee:.2f} copy-sets")
            if args.census:
                print(f"  injected work absorbed free: "
                      f"{knee*args.census:.0f} us/step "
                      f"(census {args.census:.1f} us per copy-set)")
                print(f"  saturated pass-through: "
                      f"{100.0*rate/args.census:.1f}% of injected GPU us")
                print("  K needed to resolve this family unchained: "
                      f"{knee+1.0:.1f}")
            print(f"{'K':>4} {'injected_us':>12} {'measured_us':>12} "
                  f"{'hinge_pred_us':>14}")
            for k in arms:
                inj = (k - 1) * (args.census or float("nan"))
                meas = 0.0 if k == 1 else contrasts[k][0]
                pred = max(0.0, rate * ((k - 1) - knee))
                print(f"{k:4d} {inj:12.0f} {meas:12.1f} {pred:14.1f}")

    if 2 in contrasts and 5 in contrasts and contrasts[2][0]:
        early = contrasts[2][0]
        late = (contrasts[5][0] - contrasts[2][0]) / 3.0
        print(f"\nsaturation: K=1->2 costs {early:.2f} us/copy-set, "
              f"K=2->5 costs {late:.2f} us/copy-set (ratio {late/early:.2f})")

    resolution_k = None
    for k in arms:
        if k == 1 or k not in contrasts:
            continue
        m, se, _ = contrasts[k]
        if abs(m) > 2 * se:
            resolution_k = k
            break
    label = (f"first resolved at K={resolution_k}" if resolution_k
             else "never surfaced within the sweep")
    flag = "  [THIN MARGIN: M5 flip risk]" if resolution_k == 2 else ""
    print(f"\nresolution K: {resolution_k if resolution_k else '>' + str(arms[-1])} "
          f"-- {label}{flag}")

    if args.calls:
        print(f"per-call marginal cost: {slope/args.calls:.3f} us "
              f"({args.calls} injected calls/step)")
    if args.census:
        print(f"E = slope/census = {slope:.2f}/{args.census:.1f} = "
              f"{slope/args.census:.3f}")
    return 0


def detect_block_len(seq):
    for n in range(2, len(seq) + 1):
        if len(seq) % n:
            continue
        if all(seq[i] == seq[i % n] for i in range(len(seq))):
            return n
    return len(seq)


def read_tsv(path):
    header, rows, drop = "", [], 0
    with open(path) as fh:
        for line in fh:
            if line.startswith("#"):
                header = line
                for tok in line.split():
                    if tok.startswith("drop="):
                        drop = int(tok.split("=", 1)[1])
                continue
            if line.startswith("segment\t"):
                continue
            seg, k, step, ms = line.split("\t")
            rows.append((int(seg), int(k), int(step), float(ms)))
    return header, rows, drop


if __name__ == "__main__":
    sys.exit(main())
