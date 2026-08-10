#!/usr/bin/env python3
"""Pooled two-replicate contrast: mean(P1, P1B) - P0, per repetition.

P1 and P1B are byte-identical code (DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1), so
pooling them is a legitimate 2x-precision estimate of the same quantity.
"""
import json
import math
import statistics
import sys
from pathlib import Path

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = Path(ARGS[0] if ARGS else "/tmp/maple-r105b/phaseA")
WARMUP = int(ARGS[1]) if len(ARGS) > 1 else 2


def slot_median(tag):
    vals = [float(x) * 1000.0 for x in (OUT / f"{tag}.steps").read_text().split()]
    return statistics.median(vals)


rows = [l.split("\t") for l in (OUT / "index.tsv").read_text().splitlines()[1:] if l.strip()]
by_rep = {}
for rep, pos, arm, tag in rows:
    rep = int(rep)
    if rep < WARMUP:
        continue
    by_rep.setdefault(rep, {}).setdefault(arm, []).append(slot_median(tag))


def tcrit(df):
    table = {3: 3.182, 4: 2.776, 5: 2.571, 8: 2.306, 10: 2.228,
             15: 2.131, 16: 2.120, 20: 2.086, 30: 2.042}
    keys = sorted(table)
    for k in keys:
        if df <= k:
            return table[k]
    return 1.96


def ci(xs):
    n = len(xs)
    m = statistics.mean(xs)
    sd = statistics.stdev(xs) if n > 1 else 0.0
    hw = tcrit(n - 1) * sd / math.sqrt(n)
    return n, m, sd, hw


reps = sorted(by_rep)
pooled, single1, singleb, p5 = [], [], [], []
for r in reps:
    a = by_rep[r]
    p0 = statistics.mean(a["P0"])
    x1 = statistics.mean(a["P1"])
    xb = statistics.mean(a["P1B"])
    pooled.append((x1 + xb) / 2.0 - p0)
    single1.append(x1 - p0)
    singleb.append(xb - p0)
    p5.append(statistics.mean(a["P5"]) - p0)

SERIES = (("pooled(P1,P1B) - P0", pooled), ("P1  - P0", single1),
          ("P1B - P0", singleb), ("P5  - P0", p5))


def cell(xs):
    n, m, sd, hw = ci(xs)
    pos = sum(1 for v in xs if v > 0)
    return {"k": n, "mean": m, "sd": sd, "half_width": hw,
            "lo": m - hw, "hi": m + hw, "pos": pos, "neg": n - pos}


def cycles(xs, width=4):
    return [statistics.mean(xs[i:i + width])
            for i in range(0, len(xs) - width + 1, width)]


def show(name, c):
    print(f"{name:28s} {c['k']:3d} {c['mean']:+8.2f} {c['sd']:7.2f} "
          f"{c['half_width']:7.2f} {c['lo']:+8.2f} {c['hi']:+8.2f}  "
          f"{c['pos']}/{c['neg']}")


if "--json" in sys.argv:
    print(json.dumps({
        "reps_analysed": len(reps), "warmup": WARMUP,
        "per_repetition": {name: cell(xs) for name, xs in SERIES},
        "cycle_blocked": {name: cell(cycles(xs)) for name, xs in SERIES},
    }, indent=2))
    raise SystemExit(0)

print(f"reps analysed: {len(reps)}  (warmup {WARMUP})")
print(f"{'contrast':28s} {'K':>3s} {'mean':>8s} {'sd':>7s} {'95% hw':>7s} "
      f"{'lo':>8s} {'hi':>8s}  signs")
for name, xs in SERIES:
    show(name, cell(xs))

print()
print("cycle-blocked (4 reps per rotation cycle, the primary estimator):")
for name, xs in SERIES:
    show(name, cell(cycles(xs)))

n, m, sd, hw = ci(pooled)
CS_US_PER_PCT = 65.67
SIGMA_PCT = 0.5393
print()
print(f"headline pooled estimate: {m:+.2f} us/step M4  CI [{m - hw:+.2f}, {m + hw:+.2f}]")
print(f"  = {m / CS_US_PER_PCT:+.3f} % of composite score "
      f"= {m / CS_US_PER_PCT / SIGMA_PCT:.2f} session sigma")
print(f"  #571 rung-2 prediction +34.58 -> reproduction ratio {m / 34.58:.2f}")
