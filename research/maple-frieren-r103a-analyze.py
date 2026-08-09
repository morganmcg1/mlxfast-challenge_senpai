#!/usr/bin/env python3
"""Research-only (PR #571, R103-A rung 1): paired analysis of the ABBA session.

Per-slot statistic (preregistered): the median of steps 1..N-1, dropping step 0
because the first decode step after the seed prefill is not a steady step.
The 10% trimmed mean and the raw mean over the same window are reported as
declared secondaries.

Contrasts, both paired within a repetition:

    real  =  new  - old     (interior slots, positions {2,3})
    null  =  oldB - oldA    (exterior slots, positions {1,4}, rule 79)

Usage: python3 research/maple-frieren-r103a-analyze.py OUTDIR [WARMUP_REPS]
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

# Two-sided 95% t quantiles, index = degrees of freedom.
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
        14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
        20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
        26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}


def t95(df: int) -> float:
    if df <= 0:
        return float("nan")
    if df in _T95:
        return _T95[df]
    return 1.96 + 2.4 / df


def trimmed_mean(xs: list[float], frac: float = 0.10) -> float:
    s = sorted(xs)
    k = int(len(s) * frac)
    core = s[k:len(s) - k] or s
    return statistics.mean(core)


def slot_stats(path: Path) -> dict[str, float]:
    """Per-step milliseconds, one per line. Returns microseconds."""
    steps = [float(x) * 1e3 for x in path.read_text().split()]
    steady = steps[1:]
    return {
        "median": statistics.median(steady),
        "trimmed": trimmed_mean(steady),
        "mean": statistics.mean(steady),
        # Mirrors the official metric's window: the harness times 128 steps
        # from the first one, so any one-time in-window cost is inside it.
        "mean_first128": statistics.mean(steps[:128]),
        "step0": steps[0],
        "n": len(steady),
        "sd": statistics.stdev(steady),
    }


def paired(diffs: list[float]) -> dict[str, float]:
    k = len(diffs)
    if k < 2:
        return {"k": k, "mean": float("nan"), "half_width": float("nan"),
                "lo": float("nan"), "hi": float("nan"), "sd": float("nan"),
                "pos": 0, "neg": 0}
    m = statistics.mean(diffs)
    sd = statistics.stdev(diffs)
    hw = t95(k - 1) * sd / math.sqrt(k)
    return {"k": k, "mean": m, "sd": sd, "half_width": hw,
            "lo": m - hw, "hi": m + hw,
            "pos": sum(1 for d in diffs if d > 0),
            "neg": sum(1 for d in diffs if d < 0)}


def verdict(real: dict[str, float]) -> tuple[str, str]:
    """The four preregistered rung-1 outcomes (§ 1.5), applied in order."""
    m, lo, hi = real["mean"], real["lo"], real["hi"]
    if hi < 0:
        return ("3", "sign flip: NEW faster than OLD on M4 -> report and stop")
    if m >= 20.0 and lo > 0:
        return ("1", "reproduced off-M5 -> proceed to rung 2")
    if hi < 20.0 and hi > 0:
        return ("2", "does not transfer at M5 magnitude -> M5-specific, "
                     "report and stop")
    return ("4", "inconclusive-underpowered -> report, no rung 2")


def main() -> None:
    out = Path(sys.argv[1])
    warmup = int(sys.argv[2]) if len(sys.argv) > 2 else 2

    rows = [ln.split("\t") for ln in
            (out / "index.tsv").read_text().strip().splitlines()[1:]]
    by_rep: dict[int, dict[str, dict]] = defaultdict(dict)
    positions: dict[str, list[int]] = defaultdict(list)
    for rep_s, pos_s, arm, tag in rows:
        rep, pos = int(rep_s), int(pos_s)
        f = out / f"{tag}.steps"
        if not f.exists():
            print(f"MISSING {f}", file=sys.stderr)
            continue
        st = slot_stats(f)
        st["position"] = pos
        by_rep[rep][arm] = st
        if rep >= warmup:
            positions[arm].append(pos)

    reps = sorted(r for r in by_rep if r >= warmup)
    result: dict = {"warmup_reps": warmup, "analysed_reps": reps,
                    "position_multiset": {a: sorted(p)
                                          for a, p in positions.items()}}

    # Warm-up repetitions are excluded from the verdict but retained here: a
    # one-time JIT or pipeline-cache cost would live in the discarded reps and
    # in step 0, exactly where the steady-state estimator cannot see it.
    warm = {}
    for name, hi_arm, lo_arm in (("real", "new", "old"),
                                 ("null", "oldB", "oldA")):
        for scope, sel in (("warmup_reps", [r for r in by_rep if r < warmup]),
                           ("all_reps", sorted(by_rep))):
            for stat in ("median", "step0", "mean_first128"):
                d = [by_rep[r][hi_arm][stat] - by_rep[r][lo_arm][stat]
                     for r in sel
                     if hi_arm in by_rep[r] and lo_arm in by_rep[r]]
                warm[f"{name}.{scope}.{stat}"] = paired(d)
    result["diagnostics"] = warm

    for stat in ("median", "trimmed", "mean", "mean_first128"):
        block = {}
        for name, hi_arm, lo_arm in (("real", "new", "old"),
                                     ("null", "oldB", "oldA")):
            diffs, pairs = [], []
            for r in reps:
                if hi_arm in by_rep[r] and lo_arm in by_rep[r]:
                    d = by_rep[r][hi_arm][stat] - by_rep[r][lo_arm][stat]
                    diffs.append(d)
                    pairs.append({"rep": r, "diff_us": round(d, 3),
                                  hi_arm: round(by_rep[r][hi_arm][stat], 2),
                                  lo_arm: round(by_rep[r][lo_arm][stat], 2)})
            block[name] = paired(diffs)
            block[name]["pairs"] = pairs
        old_level = statistics.mean(
            [by_rep[r][a][stat] for r in reps for a in ("old", "oldA", "oldB")
             if a in by_rep[r]])
        block["old_level_us"] = old_level
        block["real_relative_pct"] = 100.0 * block["real"]["mean"] / old_level
        result[stat] = block

    result["verdict_code"], result["verdict_text"] = verdict(
        result["median"]["real"])
    (out / "analysis.json").write_text(json.dumps(result, indent=2))

    print(f"reps analysed: {reps}  (warm-up discarded: {warmup})")
    print("position multiset per arm:",
          {a: sorted(p) for a, p in positions.items()})
    windows = {"median": "steps 1..N-1", "trimmed": "steps 1..N-1",
               "mean": "steps 1..N-1", "mean_first128": "steps 0..127"}
    for stat in ("median", "trimmed", "mean", "mean_first128"):
        b = result[stat]
        print(f"\n--- per-slot statistic: {stat} of {windows[stat]} ---")
        print(f"  OLD steady step level      : {b['old_level_us']:9.1f} us")
        for name in ("real", "null"):
            p = b[name]
            lbl = "new-old " if name == "real" else "oldB-oldA"
            print(f"  {lbl} k={p['k']:2d}  mean={p['mean']:+8.2f} us  "
                  f"95% CI [{p['lo']:+8.2f}, {p['hi']:+8.2f}]  "
                  f"hw={p['half_width']:6.2f}  +/-={p['pos']}/{p['neg']}")
        print(f"  real as % of OLD step      : "
              f"{b['real_relative_pct']:+.4f} %   (M5 target +0.4865 %)")
    print("\n--- diagnostics (not part of the outcome rule) ---")
    for key in sorted(warm):
        p = warm[key]
        print(f"  {key:34s} k={p['k']:2d}  mean={p['mean']:+9.2f} us  "
              f"95% CI [{p['lo']:+9.2f}, {p['hi']:+9.2f}]")

    print(f"\nPREREGISTERED OUTCOME {result['verdict_code']}: "
          f"{result['verdict_text']}")


if __name__ == "__main__":
    main()
