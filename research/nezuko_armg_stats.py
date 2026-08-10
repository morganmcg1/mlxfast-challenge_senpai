#!/usr/bin/env python3
"""Summarise an Arm G rung-1b A/B block.

Usage: nezuko_armg_stats.py research/armg-runs/<block>

Position 0 is treated as a discarded warm-up. Reports per-position medians, the
arm-level median-of-medians, and the decode-only score ratio implied by the
median step time (decode weight 0.75, prefill unchanged).
"""
import glob
import json
import os
import statistics
import sys


def load(path):
    with open(path) as fh:
        return [float(line) for line in fh if line.strip()]


def main(block_dir):
    rows = []
    for path in sorted(glob.glob(os.path.join(block_dir, "p*-*.steps"))):
        tag = os.path.basename(path)[: -len(".steps")]
        pos, arm = tag.split("-")
        steps = load(path)
        # Drop the first step of every run: it carries one-time warm-up cost.
        body = steps[1:]
        rows.append(
            {
                "tag": tag,
                "pos": int(pos[1:]),
                "arm": arm,
                "n": len(body),
                "median_ms": statistics.median(body),
                "mean_ms": statistics.mean(body),
                "p10_ms": statistics.quantiles(body, n=10)[0],
                "p90_ms": statistics.quantiles(body, n=10)[8],
            }
        )

    kept = [r for r in rows if r["pos"] > 0]
    out = {"positions": rows, "arms": {}}
    for arm in sorted({r["arm"] for r in kept}):
        med = [r["median_ms"] for r in kept if r["arm"] == arm]
        out["arms"][arm] = {
            "n_runs": len(med),
            "medians_ms": med,
            "median_of_medians_ms": statistics.median(med),
            "min_ms": min(med),
            "max_ms": max(med),
            "spread_pct": 100.0 * (max(med) - min(med)) / statistics.median(med),
        }

    if {"A", "C"} <= set(out["arms"]):
        a = out["arms"]["A"]["median_of_medians_ms"]
        c = out["arms"]["C"]["median_of_medians_ms"]
        out["delta_ms"] = a - c
        out["delta_us"] = 1000.0 * (a - c)
        out["decode_speedup"] = a / c
        out["score_ratio"] = (a / c) ** 0.75
        out["score_pct"] = 100.0 * ((a / c) ** 0.75 - 1.0)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
