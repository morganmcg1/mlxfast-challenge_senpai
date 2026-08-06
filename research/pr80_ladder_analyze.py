#!/usr/bin/env python3
"""Analyse the PR #80 position-balanced M4 ladder.

Reads the pr80_ladder_abba.sh log and reports, per arm, the mean wall time per
decode step, plus the within-arm spread across repeated positions.

Programme law 0.9.32 requires the no-harm / significance bar to come from a
measured same-session A/A rather than a constant fixed in advance. The ladder
runs one binary and selects arms only by DARKBLOOM_* environment, so two
positions of the SAME arm are a genuine A/A: identical bytes, identical kernels,
identical session. The pooled within-arm standard deviation is therefore the
session's own noise floor, and a between-arm delta is only claimed when it
exceeds that floor.

Usage: python3 research/pr80_ladder_analyze.py LOGFILE
"""
import re
import sys
from statistics import mean, stdev

# Escape-adjusted per-step scale-plane read, from research/pr80_byte_ledger.py.
ARM_BYTES = {"S": 64_771_456, "B": 45_556_288, "C": 33_191_520, "D": 23_556_320}
M4_BW = 260.2e9

LINE = re.compile(r"\[(p\d+)-([A-Z])\] steps=(\d+) wall_ms_per_step=([\d.]+)")


def main() -> None:
    obs: dict[str, list[tuple[int, float]]] = {}
    for line in open(sys.argv[1]):
        m = LINE.search(line)
        if not m:
            continue
        pos, arm, _steps, wall = m.group(1), m.group(2), int(m.group(3)), float(m.group(4))
        if pos == "p00":
            continue  # thermal discard
        obs.setdefault(arm, []).append((int(pos[1:]), wall))

    if not obs:
        sys.exit("no measurements found")

    print(f"{'arm':<4} {'n':>2} {'mean ms':>9} {'sd us':>7} {'pos sum':>8}  positions")
    stats = {}
    resid = []
    for arm in sorted(obs):
        vals = [w for _, w in obs[arm]]
        pos = [p for p, _ in obs[arm]]
        m_, s_ = mean(vals), (stdev(vals) if len(vals) > 1 else float("nan"))
        stats[arm] = (m_, s_, len(vals))
        resid += [v - m_ for v in vals]
        print(f"{arm:<4} {len(vals):>2} {m_:>9.4f} {s_ * 1000:>7.1f} {sum(pos):>8}  "
              + " ".join(f"{v:.4f}" for v in vals))

    # Pooled within-arm sd = the measured A/A floor for this session.
    n_arms = len(stats)
    dof = len(resid) - n_arms
    pooled = (sum(r * r for r in resid) / dof) ** 0.5
    print(f"\nmeasured same-session A/A floor (pooled within-arm sd): "
          f"{pooled * 1000:.1f} us  (dof={dof})")
    print(f"2-sigma bar on a single arm-to-arm delta: {2 * pooled * 1000:.1f} us")

    print(f"\n{'delta':<10} {'observed us':>12} {'predicted us':>13} {'ratio':>7}  verdict")
    for a, b in (("S", "B"), ("B", "C"), ("C", "D"), ("B", "D")):
        if a not in stats or b not in stats:
            continue
        got = (stats[a][0] - stats[b][0]) * 1000.0
        pred = (ARM_BYTES[a] - ARM_BYTES[b]) / M4_BW * 1e6
        # sd of a difference of two means
        se = pooled * (1 / stats[a][2] + 1 / stats[b][2]) ** 0.5 * 1000.0
        verdict = "resolved" if got > 2 * se else ("null" if got > -2 * se else "REGRESSION")
        print(f"{a}->{b:<7} {got:>12.1f} {pred:>13.1f} {got / pred:>7.2f}  "
              f"{verdict} (2se={2 * se:.1f})")


if __name__ == "__main__":
    main()
