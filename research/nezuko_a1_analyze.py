#!/usr/bin/env python3
"""Compute A1 exposure factors E = dS/dI from a nezuko_a1_exposure.sh output dir.

dI is the knob-off-minus-on change in the SPLIT=1 isolated per-kernel census:
every dispatch owns a command buffer there, so nothing overlaps and the constant
per-buffer overhead cancels in the difference.

dS is the knob-off-minus-on change in decode step wall time with the profiling
hook off, i.e. the currency the score is paid in.

E ~ 1 means the kernel is on the critical path. E ~ 0 means it is already hidden
underneath a sibling dispatch and speeding it up buys nothing.

Usage: nezuko_a1_analyze.py <dir> [--top 12]
"""
from __future__ import annotations

import argparse
import itertools
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nezuko_a0_analyze import load_run  # noqa: E402


def perm_p(a, b):
    """Two-sided exact permutation p on the difference of medians."""
    pool = list(a) + list(b)
    n = len(a)
    obs = abs(statistics.median(b) - statistics.median(a))
    idx = range(len(pool))
    hits = tot = 0
    for combo in itertools.combinations(idx, n):
        left = [pool[i] for i in combo]
        right = [pool[i] for i in idx if i not in combo]
        tot += 1
        if abs(statistics.median(right) - statistics.median(left)) >= obs - 1e-12:
            hits += 1
    return hits / tot, tot


def summarize(vals):
    if not vals:
        return float("nan"), float("nan")
    return statistics.median(vals), (max(vals) - min(vals)) / 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    runs = [load_run(p) for p in sorted(Path(args.dir).glob("*.txt"))
            if not p.name.endswith(".steps.txt")]
    runs = [r for r in runs if r.get("n_steps") or r.get("busy_sum_ms")]

    groups = defaultdict(lambda: defaultdict(list))
    for r in runs:
        parts = r["tag"].split("_")
        if len(parts) < 4:
            continue
        knob, phase, arm = "_".join(parts[:-3]), parts[-3], parts[-1]
        groups[(knob, phase)][arm].append(r)

    bad = [(r["tag"], r["divergences"]) for r in runs if r.get("divergences")]
    print(f"runs={len(runs)}  token divergences: "
          + ("NONE" if not bad else repr(bad)))

    knobs = sorted({k for k, _ in groups})
    results = {}

    for knob in knobs:
        print(f"\n{'=' * 74}\n{knob}\n{'=' * 74}")

        # ---- dS: hook-off wall ----
        wall = groups.get((knob, "wall"), {})
        on = [r["wall_median_ms"] for r in wall.get("on", []) if "wall_median_ms" in r]
        off = [r["wall_median_ms"] for r in wall.get("off", []) if "wall_median_ms" in r]
        dS = float("nan")
        if on and off:
            mon, hon = summarize(on)
            moff, hoff = summarize(off)
            dS = (moff - mon) * 1000.0
            line = (f"  dS  wall  on={mon:.4f}+-{hon:.4f} ms (n={len(on)})  "
                    f"off={moff:.4f}+-{hoff:.4f} ms (n={len(off)})  "
                    f"dS={dS:+.1f} us/step")
            if len(on) == len(off) >= 3:
                p, tot = perm_p(on, off)
                line += f"  perm p={p:.4f} (of {tot})"
            print(line)

        # ---- dI: SPLIT=1 isolated census ----
        cens = groups.get((knob, "cens"), {})
        con = [r for r in cens.get("on", [])]
        cof = [r for r in cens.get("off", [])]
        dI = float("nan")
        if con and cof:
            son = statistics.median([sum(r["kernels"].values()) for r in con])
            sof = statistics.median([sum(r["kernels"].values()) for r in cof])
            dI = sof - son
            bon = statistics.median([r["busy_sum_ms"] for r in con]) * 1000
            bof = statistics.median([r["busy_sum_ms"] for r in cof]) * 1000
            print(f"  dI  census sum on={son:.1f} off={sof:.1f} us/step  "
                  f"dI={dI:+.1f} us/step   (busy_sum check {bof - bon:+.1f} us)")

            per = defaultdict(lambda: [0.0, 0.0])
            for r in con:
                for k, v in r["kernels"].items():
                    per[k][0] += v / len(con)
            for r in cof:
                for k, v in r["kernels"].items():
                    per[k][1] += v / len(cof)
            movers = sorted(per.items(), key=lambda kv: -abs(kv[1][1] - kv[1][0]))
            print(f"  {'on us/step':>11} {'off us/step':>11} {'delta':>9}  kernel")
            for k, (a, b) in movers[:args.top]:
                if abs(b - a) < 0.5:
                    break
                print(f"  {a:11.1f} {b:11.1f} {b - a:+9.1f}  {k[:70]}")

        if dS == dS and dI == dI and abs(dI) > 1e-9:
            E = dS / dI
            print(f"\n  EXPOSURE  E = dS/dI = {dS:+.1f} / {dI:+.1f} = {E:.3f}")
            results[knob] = (dS, dI, E)

    if results:
        print(f"\n{'=' * 74}\nSUMMARY\n{'=' * 74}")
        print(f"  {'knob':<28} {'dI us':>9} {'dS us':>9} {'E':>7}")
        for k, (dS, dI, E) in sorted(results.items(), key=lambda kv: -kv[1][2]):
            print(f"  {k:<28} {dI:9.1f} {dS:9.1f} {E:7.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
