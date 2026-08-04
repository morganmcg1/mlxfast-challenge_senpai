#!/usr/bin/env python3
"""Analyze DARKBLOOM_ROUTE_HISTOGRAM output: rows-per-expert spread at prefill.

The repo's routed gather-GEMM tuning notes (quantized.cpp:1405-1415) record their
run-elision figures as "Simulated over uniform routing". This script measures the
real distribution and converts it into the two costs the expert-aligned kernel
actually pays: MMA row padding (rows are issued in SM-row fragments) and
per-expert threadgroup launches (grid.y = egroups regardless of occupancy).

Routing is a property of the model and prompt, not of the GPU, so these numbers
are host-independent and transfer from M4 to M5.

Usage:
  python3 research/route_histogram.py /tmp/routehist.err [--skip-forwards 1]
"""

import argparse
import ast
import statistics


def parse(path):
    """Return a list of per-layer count vectors, in emission order."""
    layers = []
    for line in open(path):
        if "routehist" not in line or "counts=" not in line:
            continue
        counts = ast.literal_eval(line.split("counts=", 1)[1].strip())
        rows = int(line.split("rows=", 1)[1].split()[0])
        layers.append((rows, counts))
    return layers


def ceil_div(a, b):
    return -(-a // b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--layers-per-forward", type=int, default=38)
    ap.add_argument("--skip-forwards", type=int, default=1,
                    help="drop leading warmup forwards (all-BOS -> degenerate routing)")
    args = ap.parse_args()

    layers = parse(args.path)
    per_fwd = args.layers_per_forward
    n_fwd = len(layers) // per_fwd
    drop = args.skip_forwards * per_fwd
    real = layers[drop:]
    print(f"parsed {len(layers)} layer records = {n_fwd} forward(s) x {per_fwd} MoE layers")
    print(f"dropping first {args.skip_forwards} forward(s) as warmup -> {len(real)} records\n")

    if not real:
        raise SystemExit("no non-warmup records; check --skip-forwards")

    rows = real[0][0]
    n_experts = len(real[0][1])
    assign = sum(real[0][1])
    print(f"rows={rows} experts={n_experts} assignments/layer={assign} "
          f"mean rows/expert={assign / n_experts:.2f}\n")

    # Pooled distribution over every (layer, forward) instance.
    pooled = sorted(c for _, counts in real for c in counts)
    n = len(pooled)

    def q(p):
        return pooled[min(n - 1, int(p * n))]

    zero_frac = sum(1 for c in pooled if c == 0) / n
    print("pooled rows-per-expert distribution (all layers x forwards)")
    print(f"  mean {statistics.mean(pooled):7.2f}   stdev {statistics.stdev(pooled):7.2f}")
    print(f"  zero-row experts {zero_frac * 100:5.1f}%   max {pooled[-1]}")
    for p in (0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99):
        print(f"  p{int(p * 100):<3d} {q(p):5d}")
    shares = []
    for _, counts in real:
        ranked = sorted(counts, reverse=True)
        shares.append([sum(ranked[:k]) / assign for k in (1, 8, 16, 32, 64)])
    for i, k in enumerate((1, 8, 16, 32, 64)):
        mean_share = statistics.mean(s[i] for s in shares)
        print(f"  busiest {k:<3d} experts hold {mean_share * 100:5.1f}% of a layer's assignments")
    print()

    # Cost model. For simdgroup-row granularity SM the kernel issues MMA in
    # SM-row fragments; for row-tile BM it walks ceil(c/BM) chunks per expert.
    print("issued-vs-useful MMA rows by simdgroup row granularity SM")
    print(f"  {'SM':>4} {'issued/useful':>14} {'wasted':>8}")
    for sm in (8, 16, 32, 64):
        issued = sum(sm * ceil_div(c, sm) for _, counts in real for c in counts)
        useful = sum(pooled)
        print(f"  {sm:>4} {issued / useful:>13.2f}x {1 - useful / issued:>7.1%}")
    print()

    print("per-expert threadgroup launches by row-tile BM (grid.y = 256 always)")
    print(f"  {'BM':>4} {'chunks/layer':>13} {'idle TGs':>9} {'busiest expert':>15}")
    for bm in (16, 32, 64, 128):
        chunks = statistics.mean(
            sum(ceil_div(c, bm) for c in counts) for _, counts in real)
        idle = statistics.mean(
            sum(1 for c in counts if c == 0) for _, counts in real)
        busiest = statistics.mean(
            max(ceil_div(c, bm) for c in counts) for _, counts in real)
        print(f"  {bm:>4} {chunks:>13.1f} {idle:>9.1f} {busiest:>15.1f}")
    print()

    # Load imbalance: with one threadgroup column per expert, the critical path
    # is the busiest expert, not the mean.
    print("load imbalance per layer (one TG column per expert)")
    maxc = [max(counts) for _, counts in real]
    meanc = [statistics.mean(counts) for _, counts in real]
    print(f"  mean of per-layer max rows   {statistics.mean(maxc):7.1f}")
    print(f"  mean of per-layer mean rows  {statistics.mean(meanc):7.1f}")
    print(f"  imbalance factor max/mean    {statistics.mean(maxc) / statistics.mean(meanc):7.2f}x")
    print(f"  worst layer max rows         {max(maxc):7d}")


if __name__ == "__main__":
    main()
