#!/usr/bin/env python3
"""Research-only reducer for research/fern_tax_probe.py output (PR #268).

ONE reducer, one convention.  PR #241 shipped two that disagreed by ~6%
(fern_gap_stats.py centred every contrast on the K=1 arm, fern_gap_wandb.py
centred on the block mean).  This file uses exactly one estimator and every
number in the deliverable comes from it:

  WITHIN-BLOCK (FIXED-EFFECTS) OLS ON SEGMENT MEDIANS.

  * unit of replication  = one segment median (steps < --drop discarded)
  * the palindromic schedule is repeated `blocks` times; a block is one
    full pass of the schedule
  * both the regressor x and the response y are centred on their own
    BLOCK MEAN before the slope is formed, so any linear thermal/clock
    drift inside a block cancels and no single arm acts as the reference
  * the reported CI is the classical OLS t interval on the within-block
    residual degrees of freedom (n_segments - n_blocks - 1)

The regressor is chosen with --x:
  k          nominal injected dispatch groups per step (schedule value)
  dispatch   MEASURED dispatch count/step from the device.cpp counters
  barrier    MEASURED memoryBarrier count/step
  spin_us    nominal injected CPU busy-spin microseconds per step

Preferring x=dispatch over x=k is the whole point of the counter
instrument: it prices a real dispatch, not an intended one.

  python3 research/fern_tax_stats.py /tmp/fern268/chain.tsv --x dispatch
"""
import argparse
import math
import statistics
from collections import defaultdict

# From the assignment's frozen score model -- do not re-derive.
PERCENT_PER_US_DECODE = 0.015280   # % of score per us/step on M5
M5_STEP_MS = 4.143569
M5_DECODE_SIGMA_US = 15.34         # cross-session decode sigma, us/step
N_LAYERS = 40                      # weights/config.json num_hidden_layers


def t95(df):
    table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
             7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131,
             20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000,
             120: 1.980}
    for k in sorted(table):
        if df <= k:
            return table[k]
    return 1.96


def read_timing(path):
    meta, rows, drop = {}, [], 0
    with open(path) as fh:
        for line in fh:
            if line.startswith("#"):
                for tok in line.lstrip("# ").split():
                    if "=" in tok:
                        a, b = tok.split("=", 1)
                        meta[a] = b
                drop = int(meta.get("drop", 0))
                continue
            if line.startswith("segment"):
                continue
            seg, k, step, ms = line.split()
            if step.isdigit() and int(step) >= drop:
                rows.append((int(seg), int(k), float(ms)))
    return meta, rows


def read_counters(path):
    out = {}
    try:
        fh = open(path)
    except OSError:
        return out
    with fh:
        head = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            rec = dict(zip(head, parts))
            out[int(rec["segment"])] = {k: float(v) for k, v in rec.items()
                                        if k != "segment"}
    return out


def block_length(seg_k, segs):
    ks = [seg_k[s] for s in segs]
    for n in range(2, len(segs) + 1):
        if len(segs) % n == 0 and all(ks[i] == ks[i % n]
                                      for i in range(len(ks))):
            return n
    return len(segs)


def fe_ols(points, n_blocks):
    """points: list of (block, x, y).  Returns slope, se, df, n."""
    by_block = defaultdict(list)
    for b, x, y in points:
        by_block[b].append((x, y))
    sxx = sxy = 0.0
    centred = []
    for b, pts in by_block.items():
        xb = statistics.mean(p[0] for p in pts)
        yb = statistics.mean(p[1] for p in pts)
        for x, y in pts:
            cx, cy = x - xb, y - yb
            sxx += cx * cx
            sxy += cx * cy
            centred.append((cx, cy))
    if sxx == 0:
        return float("nan"), float("nan"), 0, len(points)
    slope = sxy / sxx
    df = len(points) - n_blocks - 1
    if df <= 0:
        return slope, float("nan"), 0, len(points)
    ssr = sum((cy - slope * cx) ** 2 for cx, cy in centred)
    se = math.sqrt(ssr / df / sxx)
    return slope, se, df, len(points)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv")
    ap.add_argument("--x", default="dispatch",
                    choices=["k", "dispatch", "barrier", "spin_us"])
    ap.add_argument("--label", default=None)
    ap.add_argument("--tsv-out", default=None,
                    help="append one summary row to this file")
    args = ap.parse_args()

    meta, rows = read_timing(args.tsv)
    ctr = read_counters(args.tsv + ".ctr.tsv")
    spin_ns = float(meta.get("spin_ns", 0))

    seg_k, per_seg = {}, defaultdict(list)
    for seg, k, ms in rows:
        seg_k[seg] = k
        per_seg[seg].append(ms)
    segs = sorted(per_seg)
    med = {s: statistics.median(per_seg[s]) for s in segs}
    blen = block_length(seg_k, segs)
    n_blocks = len(segs) // blen
    arms = sorted({seg_k[s] for s in segs})

    label = args.label or args.tsv.rsplit("/", 1)[-1]
    print(f"== {label}  mode={meta.get('mode')} bytes={meta.get('bytes')} "
          f"x={args.x} ==")
    print(f"   {len(segs)} segments, block={blen}, blocks={n_blocks}, "
          f"arms={arms}, timed steps/seg={len(per_seg[segs[0]])}, "
          f"divergences={meta.get('divergences')}")

    if not ctr:
        print("   WARNING: no counter file; only x=k / x=spin_us are usable")

    def xval(s):
        if args.x == "k":
            return float(seg_k[s])
        if args.x == "spin_us":
            return seg_k[s] * 40 * spin_ns / 1e3
        c = ctr.get(s)
        if c is None:
            raise SystemExit(f"segment {s} has no counters; use --x k")
        return c[args.x]

    # ---- per-arm table (means over segments sharing the same K) -----------
    print(f"\n{'K':>5} {'x':>10} {'ms':>9} {'d_us_vs_min':>12} "
          f"{'disp':>8} {'barr':>8} {'commit':>7} {'gpu_ms':>8} "
          f"{'kern_ms':>8} {'span_ms':>8} {'gpu/wall':>9}")
    arm_ms, arm_x = {}, {}
    for k in arms:
        ss = [s for s in segs if seg_k[s] == k]
        arm_ms[k] = statistics.mean(med[s] for s in ss)
        arm_x[k] = statistics.mean(xval(s) for s in ss)
    ref = arm_ms[min(arms)]
    for k in arms:
        ss = [s for s in segs if seg_k[s] == k]
        c = [ctr[s] for s in ss if s in ctr]
        g = statistics.mean(x["gpu_ns"] for x in c) / 1e6 if c else float("nan")
        kn = statistics.mean(x["kernel_ns"] for x in c) / 1e6 if c else float("nan")
        sp = statistics.mean(x["span_ns"] for x in c) / 1e6 if c else float("nan")
        d = statistics.mean(x["dispatch"] for x in c) if c else float("nan")
        b = statistics.mean(x["barrier"] for x in c) if c else float("nan")
        cm = statistics.mean(x["commit"] for x in c) if c else float("nan")
        print(f"{k:5d} {arm_x[k]:10.1f} {arm_ms[k]:9.4f} "
              f"{(arm_ms[k]-ref)*1e3:12.1f} {d:8.0f} {b:8.0f} {cm:7.0f} "
              f"{g:8.3f} {kn:8.3f} {sp:8.3f} {g/arm_ms[k]:9.3f}")

    # ---- the single estimator --------------------------------------------
    pts = [(i // blen, xval(s), med[s] * 1e3) for i, s in enumerate(segs)]
    slope, se, df, n = fe_ols(pts, n_blocks)
    half = t95(df) * se if se == se else float("nan")
    unit = {"k": "per K", "dispatch": "per dispatch", "barrier": "per barrier",
            "spin_us": "per injected CPU us"}[args.x]
    print(f"\nFE-OLS within block: {slope:+.4f} +/- {se:.4f} us/step {unit}"
          f"   (t={slope/se:+.1f}, df={df}, n={n})")
    print(f"  95% CI [{slope-half:+.4f}, {slope+half:+.4f}] us {unit}")

    if args.x == "dispatch":
        print(f"  -> measured refund of removing ONE dispatch/step on THIS "
              f"host: {slope:.3f} us [{slope-half:.3f}, {slope+half:.3f}]")
        # This host is not the ranked host. Report both ends of the transfer
        # assumption instead of pretending one of them is the answer: 1:1
        # (per-dispatch cost is fixed overhead, upper bound) and step-time
        # scaled (per-dispatch cost shrinks with the machine, lower bound).
        ratio = M5_STEP_MS / (arm_ms[min(arms)] or M5_STEP_MS)
        print(f"     M5 transfer band: 1.000x (fixed overhead) to "
              f"{ratio:.3f}x (scales with step time)")
        print(f"     {'removed dispatches':34s} {'us/step':>18} "
              f"{'% score':>15} {'sigma':>13}")
        for n_disp, tag in ((1, f"1 per layer (x{N_LAYERS})"),
                            (3, f"3 per layer (x{N_LAYERS})"),
                            (10, f"10 per layer (x{N_LAYERS})")):
            hi = slope * n_disp * N_LAYERS
            lo = hi * ratio
            print(f"     {tag:34s} {lo:8.1f}..{hi:-8.1f} "
                  f"{lo*PERCENT_PER_US_DECODE:6.3f}..{hi*PERCENT_PER_US_DECODE:-6.3f} "
                  f"{lo/M5_DECODE_SIGMA_US:5.2f}..{hi/M5_DECODE_SIGMA_US:-5.2f}")
    if args.x == "spin_us":
        print(f"  slope ~1 => CPU-paced (E1 encode starvation); "
              f"slope ~0 => GPU-paced")

    if args.tsv_out:
        with open(args.tsv_out, "a") as fh:
            fh.write(f"{label}\t{meta.get('mode')}\t{meta.get('bytes')}\t"
                     f"{args.x}\t{slope:.5f}\t{se:.5f}\t{half:.5f}\t{df}\t"
                     f"{n}\t{meta.get('divergences')}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
