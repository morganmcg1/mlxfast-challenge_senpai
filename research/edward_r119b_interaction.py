#!/usr/bin/env python3
"""R119-B rev2: startup-memory-profile x gate interaction from the two wall cells.

Reads the auto (low-memory) and full campaign CSVs and prints, per order tag and
pooled, the absolute cell walls plus the interaction (delta_full - delta_auto)
with a Welch interval over per-block deltas.

Research-only; not on editablePaths.
  python3 research/edward_r119b_interaction.py --auto /tmp/r119b --full /tmp/r119b-full
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edward_r119b_stats as S  # noqa: E402
from edward_r119b_wandb import estimators  # noqa: E402

ORDERS = ("abba", "baab")


def paths_for(root: str, order: str):
    if order == "pooled":
        return [os.path.join(root, f"{o}_raw.csv") for o in ORDERS], True
    return [os.path.join(root, f"{order}_raw.csv")], False


def block_deltas(paths, pool):
    """Per-block mean(C) - mean(F) in microseconds; positive = candidate faster."""
    _, samples, meta, med = estimators(paths, pool=pool)
    by_block: dict = {}
    for run in sorted(samples):
        block, arm, _ = meta[run]
        by_block.setdefault(block, {}).setdefault(arm, []).append(med[run])
    out = []
    for _, arms in sorted(by_block.items()):
        if "C" in arms and "F" in arms:
            out.append(1000.0 * (np.mean(arms["C"]) - np.mean(arms["F"])))
    return np.asarray(out)


def cell_means(paths, pool):
    _, samples, meta, med = estimators(paths, pool=pool)
    out = {}
    for arm in ("C", "F"):
        vals = [med[r] for r in sorted(samples) if meta[r][1] == arm]
        out[arm] = (len(vals), 1000.0 * float(np.mean(vals)),
                    1000.0 * float(np.std(vals, ddof=1)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", default="/tmp/r119b")
    ap.add_argument("--full", default="/tmp/r119b-full")
    args = ap.parse_args()

    print("absolute cell walls (mean of per-run medians, us/step)")
    for profile, root in (("auto", args.auto), ("full", args.full)):
        for order in list(ORDERS) + ["pooled"]:
            paths, pool = paths_for(root, order)
            m = cell_means(paths, pool)
            print(f"  {profile:5s} {order:7s} "
                  f"C n={m['C'][0]:2d} {m['C'][1]:9.3f} sd={m['C'][2]:6.3f} | "
                  f"F n={m['F'][0]:2d} {m['F'][1]:9.3f} sd={m['F'][2]:6.3f} | "
                  f"F-C={m['F'][1] - m['C'][1]:+8.3f}")

    print("\nprofile shift (full - auto) per arm, us/step")
    for order in list(ORDERS) + ["pooled"]:
        pa, poola = paths_for(args.auto, order)
        pf, poolf = paths_for(args.full, order)
        ma, mf = cell_means(pa, poola), cell_means(pf, poolf)
        for arm in ("C", "F"):
            shift = mf[arm][1] - ma[arm][1]
            print(f"  {order:7s} arm {arm}: {shift:+8.3f} "
                  f"({100.0 * shift / ma[arm][1]:+.3f}%)")

    print("\ninteraction on the block estimator "
          "(delta = baseline - candidate; positive = candidate faster)")
    for order in list(ORDERS) + ["pooled"]:
        pa, poola = paths_for(args.auto, order)
        pf, poolf = paths_for(args.full, order)
        da, df = block_deltas(pa, poola), block_deltas(pf, poolf)
        inter, lo, hi, p, dof = S.welch(df, da)
        print(f"  {order:7s} blocks auto={da.size} full={df.size} "
              f"d_auto={da.mean():+8.2f} d_full={df.mean():+8.2f} "
              f"interaction={inter:+8.2f} CI[{lo:+.2f},{hi:+.2f}] "
              f"p={p:.3e} df={dof:.1f}")


if __name__ == "__main__":
    main()
