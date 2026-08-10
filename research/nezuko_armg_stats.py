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
import random
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

    names = sorted(out["arms"])
    out["contrasts"] = {}
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            out["contrasts"][f"{left}-{right}"] = contrast(
                out["arms"][left]["medians_ms"], out["arms"][right]["medians_ms"]
            )
    if {"A", "C"} <= set(out["arms"]):
        c = out["contrasts"]["A-C"]
        out["delta_ms"] = c["delta_ms"]
        out["delta_us"] = c["delta_us"]
        out["decode_speedup"] = c["ratio"]
        out["score_pct"] = c["score_pct"]
    print(json.dumps(out, indent=2))


def contrast(left, right, draws=20000, seed=20260810):
    lm = statistics.median(left)
    rm = statistics.median(right)
    rng = random.Random(seed)
    deltas = []
    for _ in range(draws):
        a = statistics.median([rng.choice(left) for _ in left])
        b = statistics.median([rng.choice(right) for _ in right])
        deltas.append(a - b)
    deltas.sort()
    lo = deltas[int(0.025 * (draws - 1))]
    hi = deltas[int(0.975 * (draws - 1))]
    return {
        "delta_ms": lm - rm,
        "delta_us": 1000.0 * (lm - rm),
        "ci95_us": [1000.0 * lo, 1000.0 * hi],
        "ratio": lm / rm,
        "score_pct": 100.0 * ((lm / rm) ** 0.75 - 1.0),
        "score_pct_ci95": [
            100.0 * (((rm + lo) / rm) ** 0.75 - 1.0),
            100.0 * (((rm + hi) / rm) ** 0.75 - 1.0),
        ],
    }


if __name__ == "__main__":
    main(sys.argv[1])
