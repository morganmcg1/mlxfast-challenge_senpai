#!/usr/bin/env python3
"""Research-only reducer for research/fern_gap_probe.py output (PR #241).

Unit of replication is the SEGMENT MEDIAN. Every contrast is formed inside a
palindromic block so linear drift cancels. Unlike PR #218 the reference arm is
K=0 (instrument present but inert), so the K=0 -> K=1 step measures the cost of
*introducing* an injected boundary and the K>=1 slope measures the marginal
cost of one more chained dispatch on the same edge.

  python3 research/fern_gap_stats.py /tmp/fern241/gap_T0b_qkv.tsv --calls 40
"""
import argparse
import math
import statistics
from collections import defaultdict

PERCENT_PER_US = 0.015280
HOST_STEP_MS = 8.20
M5_STEP_MS = 4.143569


def t95(df):
    table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
             7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131,
             20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000}
    for k in sorted(table):
        if df <= k:
            return table[k]
    return 1.96


def read_tsv(path):
    header, rows, drop = "", [], 0
    with open(path) as fh:
        for line in fh:
            if line.startswith("#"):
                header = line.strip()
                for tok in line.split():
                    if tok.startswith("drop="):
                        drop = int(tok.split("=", 1)[1])
                continue
            seg, k, step, ms = line.split()
            if not seg.lstrip("-").isdigit():
                continue
            rows.append((int(seg), int(k), int(step), float(ms)))
    return header, rows, drop


def ols(xs, ys):
    xbar, ybar = statistics.mean(xs), statistics.mean(ys)
    sxx = sum((x - xbar) ** 2 for x in xs)
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / sxx
    icpt = ybar - slope * xbar
    df = len(xs) - 2
    resid = [y - (icpt + slope * x) for x, y in zip(xs, ys)]
    se = math.sqrt(sum(r * r for r in resid) / df / sxx)
    return slope, se, icpt, df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv")
    ap.add_argument("--calls", type=int, required=True)
    ap.add_argument("--label", default=None)
    args = ap.parse_args()

    header, rows, drop = read_tsv(args.tsv)
    seg_k, per_seg = {}, defaultdict(list)
    for seg, k, step, ms in rows:
        seg_k[seg] = k
        if step >= drop:
            per_seg[seg].append(ms)
    segs = sorted(per_seg)
    med = {s: statistics.median(per_seg[s]) for s in segs}
    ks = [seg_k[s] for s in segs]
    blen = next(n for n in range(2, len(segs) + 1)
                if len(segs) % n == 0
                and all(ks[i] == ks[i % n] for i in range(len(ks))))
    per_block = defaultdict(lambda: defaultdict(list))
    for s in segs:
        per_block[s // blen][seg_k[s]].append(med[s])
    blocks = sorted(per_block)
    arms = sorted({seg_k[s] for s in segs})

    label = args.label or args.tsv
    print(f"== {label}  calls/step={args.calls}  blocks={len(blocks)} "
          f"arms={arms} timed_steps/seg={len(per_seg[segs[0]])} ==")

    base = {}
    print(f"{'K':>3} {'d_vs_K0_us':>11} {'se':>7} {'t':>7} {'us/copy':>9}")
    for k in arms:
        d = [(statistics.mean(per_block[b][k])
              - statistics.mean(per_block[b][0])) * 1e3 for b in blocks]
        m = statistics.mean(d)
        se = statistics.stdev(d) / math.sqrt(len(d)) if len(d) > 1 else 0.0
        base[k] = (m, se)
        pc = m / (k * args.calls) if k else float("nan")
        tt = m / se if se else float("nan")
        print(f"{k:3d} {m:11.2f} {se:7.2f} {tt:7.2f} {pc:9.3f}")

    # Block-centred OLS over K>=1 only: marginal cost of one extra chained
    # dispatch on an edge that already carries one.
    for lo, tag in ((1, "K>=1"), (0, "K>=0")):
        xs, ys = [], []
        for b in blocks:
            ref = statistics.mean(per_block[b][max(lo, min(arms))])
            for k, vals in per_block[b].items():
                if k < lo:
                    continue
                for v in vals:
                    xs.append(float(k))
                    ys.append((v - ref) * 1e3)
        if len({x for x in xs}) < 2:
            continue
        sl, se, icpt, df = ols(xs, ys)
        h = t95(df) * se
        pc, pch = sl / args.calls, h / args.calls
        print(f"OLS {tag}: {sl:8.2f} +/- {se:5.2f} us per copy-set/step "
              f"(t={sl/se:6.1f})  -> {pc:6.3f} +/- {pch:.3f} us per boundary")
        if lo == 1:
            fixed = base[1][0] - sl
            print(f"  first-touch offset (K=0->1 minus slope): "
                  f"{fixed:.1f} us/step ({fixed/args.calls:.3f} us/call)")
    m5 = base.get(1, (0, 0))
    print(f"  if {args.calls} boundaries were removed at the K>=1 marginal "
          f"rate, host saving = {sl*args.calls/args.calls:.1f} us/step "
          f"= {sl/HOST_STEP_MS/1000*100:.3f}% of the host step")
    _ = m5


if __name__ == "__main__":
    raise SystemExit(main())
