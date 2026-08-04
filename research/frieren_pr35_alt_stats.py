#!/usr/bin/env python3
"""Paired statistics for the PR35 in-process parity A/B dumps.

Even decode step indices ran the candidate (narrow / research) arm and odd
indices the stock plane, inside one worker process. The paired difference of
neighbouring steps removes the slow KV-growth trend and every between-process
offset, so the median of `stock - candidate` is the per-step effect.
"""
import statistics
import sys


def main() -> int:
    for path in sys.argv[1:]:
        with open(path) as fh:
            t = [float(line) for line in fh if line.strip()]
        warm = 16
        t = t[warm:]
        if len(t) % 2:
            t = t[:-1]
        cand = t[0::2]
        stock = t[1::2]
        pairs = [s - c for c, s in zip(cand, stock)]
        pairs_r = [c - s for s, c in zip(stock[:-1], cand[1:])]
        print(
            f"{path}: n={len(pairs)} "
            f"cand_med={statistics.median(cand)*1e3:.1f} us "
            f"stock_med={statistics.median(stock)*1e3:.1f} us "
            f"paired_med={statistics.median(pairs)*1e3:+.1f} us "
            f"paired_mean={statistics.mean(pairs)*1e3:+.1f} us "
            f"paired_rev_med={statistics.median(pairs_r)*1e3:+.1f} us "
            f"stdev={statistics.stdev(pairs)*1e3:.1f} us",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
