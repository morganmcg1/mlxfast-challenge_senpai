#!/usr/bin/env python3
"""R105-B forensic decomposition of an r103a-abba output directory.

`maple-frieren-r103a-analyze-multi.py` reports one number per arm pair. That
number cannot distinguish a sustained per-step cost from a per-slot constant,
and it cannot show whether an effect survives at every slot position. Both
questions decide whether an arm contrast is physics or estimator structure, so
this script answers them directly from the per-step dumps:

  1. step-index profile   -- cross-slot median at each step index, so a
                             one-time or warm-up cost shows as a decaying
                             head and a real per-step cost shows as a plateau.
                             A constant C us added once per slot contributes
                             C/N to a mean and ~0 to a median; if the profile
                             is flat the arm difference cannot be that.
  2. per-position table    -- mean slot median at each (arm, position), so a
                             rotation-residual position effect is visible
                             instead of being averaged away.
  3. distribution overlap  -- min/max of each arm's slot medians. Disjoint
                             supports are a distribution-free result that no
                             drift model with exchangeable slots can produce.

Usage: maple-frieren-r105b-stepwise.py OUTDIR WARMUP_REPS [ARM_A ARM_B ...]
"""
from __future__ import annotations

import itertools
import statistics as stats
import sys
from collections import defaultdict
from pathlib import Path

# Step-index windows. Dense at the head because that is where a JIT compile,
# a shader-cache miss or a page-in would land, and wide at the tail because
# that is where a thermal or KV-growth interaction would land.
WINDOWS = ((0, 1), (1, 2), (2, 5), (5, 10), (10, 25), (25, 50),
           (50, 100), (100, 150), (150, 200), (200, 250))


def load(outdir: Path, warmup: int):
    """arm -> [(rep, position, [per-step us])], warm-up repetitions dropped."""
    slots: dict[str, list] = defaultdict(list)
    index = outdir / "index.tsv"
    for line in index.read_text().splitlines()[1:]:
        rep_s, pos_s, arm, tag = line.split("\t")
        if int(rep_s) < warmup:
            continue
        steps = outdir / f"{tag}.steps"
        if not steps.exists() or not steps.read_text().strip():
            print(f"  skip {tag}: missing or empty")
            continue
        # The harness writes milliseconds per step; every published number in
        # this family is microseconds per step.
        us = [float(x) * 1000.0 for x in steps.read_text().split()]
        slots[arm].append((int(rep_s), int(pos_s), us))
    return slots


def profile(runs, n_steps: int):
    return [stats.median(us[k] for _, _, us in runs) for k in range(n_steps)]


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    outdir = Path(sys.argv[1])
    warmup = int(sys.argv[2])
    slots = load(outdir, warmup)
    wanted = sys.argv[3:] or sorted(slots)
    arms = [a for a in wanted if a in slots]

    lengths = {len(us) for a in arms for _, _, us in slots[a]}
    if len(lengths) != 1:
        print(f"  WARNING: ragged step counts {sorted(lengths)}; "
              "truncating to the shortest")
    n_steps = min(lengths)
    for a in arms:
        slots[a] = [(r, p, us[:n_steps]) for r, p, us in slots[a]]

    print(f"########## R105-B stepwise forensics: {outdir} ##########")
    print(f"warmup_reps={warmup} steps_per_slot={n_steps} "
          + " ".join(f"{a}:n={len(slots[a])}" for a in arms))

    prof = {a: profile(slots[a], n_steps) for a in arms}

    print("\n########## 1. step-index profile (us/step) ##########")
    windows = [(lo, hi) for lo, hi in WINDOWS if lo < n_steps]
    header = "".join(f"{lo}-{min(hi, n_steps):>9}" for lo, hi in windows)
    print(f"  {'window':>16}{header}")
    for a in arms:
        cells = "".join(f"{stats.mean(prof[a][lo:min(hi, n_steps)]):11.1f}"
                        for lo, hi in windows)
        print(f"  {a + ' level':>16}{cells}")
    for x, y in itertools.combinations(arms, 2):
        cells = "".join(
            f"{stats.mean(prof[y][lo:min(hi, n_steps)]) - stats.mean(prof[x][lo:min(hi, n_steps)]):+11.2f}"
            for lo, hi in windows)
        print(f"  {y + '-' + x:>16}{cells}")

    print("\n  interpretation: a per-slot constant C us contributes C/"
          f"{n_steps} to the mean and about zero to the median profile, so a")
    print("  flat non-zero row is a sustained per-step cost, not a one-time"
          " cost.")

    print("\n########## 2. per-(arm, position) mean of slot medians ##########")
    positions = sorted({p for a in arms for _, p, _ in slots[a]})
    print(f"  {'arm':>6}" + "".join(f"{'pos' + str(p):>11}" for p in positions))
    permed: dict[str, dict[int, float]] = {}
    for a in arms:
        by_pos = defaultdict(list)
        for _, p, us in slots[a]:
            by_pos[p].append(stats.median(us))
        permed[a] = {p: stats.mean(v) for p, v in by_pos.items()}
        print(f"  {a:>6}" + "".join(
            f"{permed[a].get(p, float('nan')):11.1f}" for p in positions))
    for x, y in itertools.combinations(arms, 2):
        shared = [p for p in positions if p in permed[x] and p in permed[y]]
        deltas = [permed[y][p] - permed[x][p] for p in shared]
        print(f"  {y}-{x}: " + " ".join(f"{d:+.1f}" for d in deltas)
              + f"   | {sum(1 for d in deltas if d > 0)}/{len(deltas)} positive")

    print("\n########## 3. slot-median distributions ##########")
    dist = {a: sorted(stats.median(us) for _, _, us in slots[a]) for a in arms}
    for a in arms:
        xs = dist[a]
        sd = stats.stdev(xs) if len(xs) > 1 else float("nan")
        print(f"  {a:>6}: n={len(xs):3d} min {xs[0]:8.1f} q1 {xs[len(xs) // 4]:8.1f}"
              f" med {stats.median(xs):8.1f} q3 {xs[3 * len(xs) // 4]:8.1f}"
              f" max {xs[-1]:8.1f} sd {sd:6.1f}")
    for x, y in itertools.combinations(arms, 2):
        lo, hi = dist[x], dist[y]
        gap = min(hi) - max(lo)
        over = sum(1 for v in hi if v <= max(lo)) + sum(1 for v in lo if v >= min(hi))
        verdict = ("DISJOINT" if gap > 0 else
                   "DISJOINT(reversed)" if max(hi) < min(lo) else "overlapping")
        print(f"  {y} vs {x}: {verdict}, min({y})-max({x}) = {gap:+.1f},"
              f" {over} slot(s) in the overlap")

    print("\n########## 4. within-repetition paired contrast ##########")
    reps = defaultdict(dict)
    for a in arms:
        by_rep = defaultdict(list)
        for r, _, us in slots[a]:
            by_rep[r].append(stats.median(us))
        for r, v in by_rep.items():
            reps[r][a] = stats.mean(v)
    for x, y in itertools.combinations(arms, 2):
        d = [reps[r][y] - reps[r][x] for r in sorted(reps)
             if x in reps[r] and y in reps[r]]
        if len(d) < 2:
            continue
        pos = sum(1 for v in d if v > 0)
        print(f"  {y}-{x}: n={len(d)} mean {stats.mean(d):+8.2f}"
              f" median {stats.median(d):+8.2f} sd {stats.stdev(d):6.2f}"
              f" sign {pos}/{len(d)} positive")


if __name__ == "__main__":
    main()
