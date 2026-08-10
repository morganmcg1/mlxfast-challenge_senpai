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
  4. paired contrast       -- within-repetition differences, sign count.
  5. KV-length scaling     -- because step index is also KV length, the window
                             profile identifies whether a contrast is a fixed
                             per-step cost or one proportional to KV traffic.
                             Only the second can be an interaction with the
                             attention stream, and only the second needs
                             rescaling before it is quoted at the scored
                             decode length.

Usage: maple-frieren-r105b-stepwise.py OUTDIR WARMUP_REPS [ARM_A ARM_B ...]
"""
from __future__ import annotations

import itertools
import os
import random
import statistics as stats
import sys
from collections import defaultdict
from pathlib import Path

# Step-index windows. Dense at the head because that is where a JIT compile,
# a shader-cache miss or a page-in would land, and wide at the tail because
# that is where a thermal or KV-growth interaction would land.
WINDOWS = ((0, 1), (1, 2), (2, 5), (5, 10), (10, 25), (25, 50),
           (50, 100), (100, 150), (150, 200), (200, 250))

# Teacher-forced seed length used by the benchmark decode axis, and the scored
# number of one-token steps. A research harness may run more steps than the
# scored window, which changes the mean KV length the contrast is measured at.
SEED_TOKENS = int(os.environ.get("SEED_TOKENS", "512"))
SCORED_STEPS = int(os.environ.get("SCORED_STEPS", "128"))
BOOT = int(os.environ.get("BOOT", "2000"))


def kv_fit(kv, gap):
    """(proportional R2, affine R2, us per KV token, elasticity at the mean).

    Compares gap = s*kv against gap = a + b*kv, both referenced to the
    constant-gap model. Window 0 is excluded by the caller because step 0
    carries one-time costs that are not a KV effect.
    """
    n = len(kv)
    if n < 3:
        return None
    gbar = sum(gap) / n
    sst = sum((g - gbar) ** 2 for g in gap)
    if sst <= 0.0:
        return None

    def r2(pred):
        return 1.0 - sum((g - p) ** 2 for g, p in zip(gap, pred)) / sst

    s = sum(k * g for k, g in zip(kv, gap)) / sum(k * k for k in kv)
    kbar = sum(kv) / n
    b = (sum((k - kbar) * (g - gbar) for k, g in zip(kv, gap))
         / sum((k - kbar) ** 2 for k in kv))
    a = gbar - b * kbar
    elas = b * kbar / gbar if gbar else float("nan")
    return r2([s * k for k in kv]), r2([a + b * k for k in kv]), b, elas


T95 = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447, 8: 2.365,
       9: 2.306, 10: 2.262, 12: 2.179, 15: 2.131, 20: 2.086, 25: 2.060,
       30: 2.042, 40: 2.021, 60: 2.000}


def t95(df: int) -> float:
    for k in sorted(T95):
        if df <= k:
            return T95[k]
    return 1.96


def ci(xs):
    """(mean, half-width) of a two-sided 95% t interval."""
    n = len(xs)
    m = stats.mean(xs)
    if n < 2:
        return m, float("nan")
    return m, t95(n - 1) * stats.stdev(xs) / (n ** 0.5)


def ols(xs, ys):
    """(intercept, slope) by least squares."""
    n = len(xs)
    xbar = sum(xs) / n
    ybar = sum(ys) / n
    sxx = sum((x - xbar) ** 2 for x in xs)
    b = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / sxx
    return ybar - b * xbar, b


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

    print("\n########## 5. KV-length scaling of each contrast ##########")
    print(f"  seed_tokens={SEED_TOKENS} (override with SEED_TOKENS=n)")
    print(f"  {'contrast':>16}{'mean us':>10}{'prop R2':>10}{'affine R2':>11}"
          f"{'us/KVtok':>10}{'elasticity':>12}{'scored haircut':>16}")
    fitw = [w for w in windows if w[0] > 0]
    kv = [SEED_TOKENS + (lo + min(hi, n_steps) - 1) / 2.0 for lo, hi in fitw]
    for x, y in itertools.combinations(arms, 2):
        g = [stats.mean(prof[y][lo:min(hi, n_steps)])
             - stats.mean(prof[x][lo:min(hi, n_steps)]) for lo, hi in fitw]
        fit = kv_fit(kv, g)
        if fit is None:
            continue
        prop_r2, aff_r2, slope, elas = fit
        cut = ((SEED_TOKENS + (SCORED_STEPS - 1) / 2.0)
               / (SEED_TOKENS + (n_steps - 1) / 2.0))
        mean_g = stats.mean(g)
        print(f"  {y + '-' + x:>16}{mean_g:+10.2f}{prop_r2:+10.3f}{aff_r2:+11.3f}"
              f"{slope:+10.5f}{elas:+12.2f}{mean_g * cut:+16.2f}")
    print("\n  A contrast whose cost is created by the routed GEMV alone has no"
          " reason to")
    print("  scale with KV length. Proportional R2 near the affine R2 with an"
          " elasticity")
    print("  near 1 means the cost tracks the growing attention stream rather"
          " than the")
    print("  router kernel in isolation. The last column rescales the contrast"
          " to the")
    print(f"  scored {SCORED_STEPS}-step window under that model.")

    print("\n########## 6. per-repetition KV regression (paired, with CI) "
          "##########")
    print("  Section 5 fits 9 window means that are not independent draws. Here"
          " each")
    print("  repetition supplies one slope and one intercept, so the interval is"
          " a")
    print("  paired t interval over repetitions and the estimand is well"
          " defined.")
    levels = defaultdict(dict)
    for a in arms:
        by_rep = defaultdict(list)
        for r, _, us in slots[a]:
            by_rep[r].append(us)
        for r, vs in by_rep.items():
            levels[r][a] = [stats.mean(c) for c in zip(*vs)]
    kstep = [float(SEED_TOKENS + i) for i in range(1, n_steps)]
    kbar_h = SEED_TOKENS + (n_steps - 1) / 2.0
    kbar_s = SEED_TOKENS + (SCORED_STEPS - 1) / 2.0
    print(f"\n  {'contrast':>16}{'slope us/KVtok':>22}{'intercept us':>22}"
          f"{'at KV=' + str(int(kbar_h)):>20}{'at KV=' + str(int(kbar_s)):>20}")
    for x, y in itertools.combinations(arms, 2):
        fits = [ols(kstep, [levels[r][y][i] - levels[r][x][i]
                            for i in range(1, n_steps)])
                for r in sorted(levels) if x in levels[r] and y in levels[r]]
        if len(fits) < 2:
            continue
        sm, sh = ci([f[1] for f in fits])
        im, ih = ci([f[0] for f in fits])
        hm, hh = ci([f[0] + f[1] * kbar_h for f in fits])
        sc, sch = ci([f[0] + f[1] * kbar_s for f in fits])
        print(f"  {y + '-' + x:>16}"
              f"{f'{sm:+.5f} +-{sh:.5f}':>22}"
              f"{f'{im:+.2f} +-{ih:.2f}':>22}"
              f"{f'{hm:+.2f} +-{hh:.2f}':>20}"
              f"{f'{sc:+.2f} +-{sch:.2f}':>20}")
    print("\n  A slope interval excluding zero establishes KV dependence. An"
          " intercept")
    print("  interval covering zero is consistent with strict proportionality,"
          " which")
    print("  is what an interaction with the growing attention stream predicts."
          " The")
    print(f"  last column is the value that may be quoted at the scored"
          f" {SCORED_STEPS}-step window.")

    print("\n########## 7. rep-level bootstrap of the pooled slope ##########")
    print("  Section 5 fits the cross-slot median profile, which is far less"
          " noisy than")
    print("  any single repetition but carries no interval. Section 6 gives a"
          " correct")
    print("  interval for a noisier per-repetition estimator. This resamples"
          " repetitions")
    print(f"  ({BOOT} draws) and refits the pooled median profile each time, so"
          " the")
    print("  estimator of section 5 finally gets its own interval.")
    rng = random.Random(20260804)
    reps_all = sorted(levels)
    haircut_label = f"haircut {SCORED_STEPS}/{n_steps}"
    print(f"\n  {'contrast':>10}  {'pooled slope us/KVtok':>32}"
          f"  {'pooled intercept us':>26}  {haircut_label:>26}")
    for x, y in itertools.combinations(arms, 2):
        usable = [r for r in reps_all if x in levels[r] and y in levels[r]]
        if len(usable) < 4:
            continue
        gaps = {r: [levels[r][y][i] - levels[r][x][i] for i in range(1, n_steps)]
                for r in usable}
        draws = []
        for _ in range(BOOT):
            pick = [rng.choice(usable) for _ in usable]
            prof_b = [stats.median(col) for col in zip(*(gaps[r] for r in pick))]
            a_b, b_b = ols(kstep, prof_b)
            draws.append((b_b, a_b, (a_b + b_b * kbar_s) / (a_b + b_b * kbar_h)
                          if a_b + b_b * kbar_h else float("nan")))
        cols = []
        for j in range(3):
            v = sorted(d[j] for d in draws)
            lo, hi = v[int(0.025 * BOOT)], v[int(0.975 * BOOT)]
            point = stats.median(v)
            fmt = ".5f" if j == 0 else (".2f" if j == 1 else ".4f")
            cols.append(f"{point:+{fmt}} [{lo:+{fmt}}, {hi:+{fmt}}]")
        print(f"  {y + '-' + x:>10}  {cols[0]:>32}  {cols[1]:>26}"
              f"  {cols[2]:>26}")
    print("\n  Only a slope interval that excludes zero in BOTH section 6 and"
          " section 7")
    print("  licenses a KV-proportional reading, and only then may the haircut"
          " column")
    print("  be applied to a headline number.")


if __name__ == "__main__":
    main()
