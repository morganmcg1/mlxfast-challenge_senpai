#!/usr/bin/env python3
"""Position-matched cross-check of the rung-2 contrasts.

The primary cycle-blocked estimator removes the slot-position artefact by
averaging a complete rotation cycle. This script removes it a second, more
literal way: it compares arms only at the *same* slot-position pair, using the
one repetition per cycle in which each arm occupies that pair. Three independent
position-matched estimates per contrast (one per position pair) must agree with
each other and with the primary estimate; if the primary effect were an artefact
of a particular slot position it would not survive here.

Deliberately an independent parser, so a bug in the main analyzer cannot be
reproduced identically here.

Usage: maple-frieren-r103a-position-matched.py OUTDIR [WARMUP_REPS]
"""
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

T95 = {2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
       9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 20: 2.086}


def t95(dof):
    if dof in T95:
        return T95[dof]
    return 1.96 if dof > 30 else 2.2


def slot_median(path):
    vals = [float(x) for x in path.read_text().split()]
    return statistics.median(vals[1:-1]) * 1000.0


def main():
    out = Path(sys.argv[1])
    warmup = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    rows = [l.split("\t") for l in
            (out / "index.tsv").read_text().splitlines()[1:] if l.strip()]
    # rep -> arm -> position -> median
    data = defaultdict(lambda: defaultdict(dict))
    for rep, pos, arm, tag in rows:
        rep, pos = int(rep), int(pos)
        if rep < warmup:
            continue
        data[rep][arm][pos] = slot_median(out / f"{tag}.steps")

    reps = sorted(data)
    arms = sorted({a for r in reps for a in data[r]})

    # A rep's layout signature identifies its rotation phase.
    def sig(rep):
        return tuple(sorted((a, tuple(sorted(data[rep][a]))) for a in arms))

    phases = {}
    for r in reps:
        phases.setdefault(sig(r), []).append(r)
    order = sorted(phases, key=lambda s: min(phases[s]))
    ncyc = min(len(phases[s]) for s in order)
    cycles = [[phases[s][i] for s in order] for i in range(ncyc)]

    print(f"# position-matched cross-check  ({out})")
    print(f"rotation phases: {len(order)}   complete cycles: {ncyc}   "
          f"reps used: {ncyc * len(order)} of {len(reps)}")

    # pair -> arm -> [one value per cycle]
    bypair = defaultdict(lambda: defaultdict(list))
    for cyc in cycles:
        for rep in cyc:
            for arm in arms:
                pos = tuple(sorted(data[rep][arm]))
                bypair[pos][arm].append(
                    sum(data[rep][arm].values()) / len(data[rep][arm]))

    pairs = sorted(bypair, key=lambda p: p[1] - p[0])
    print("\nper-arm level at each position pair (mean over cycles, us/step):")
    hdr = "  pair        " + "".join(f"{a:>12}" for a in arms)
    print(hdr)
    for p in pairs:
        line = f"  {{{p[0]},{p[1]}}} sep{p[1]-p[0]}  "
        for a in arms:
            line += f"{statistics.mean(bypair[p][a]):12.1f}"
        print(line)

    print("\nposition-matched contrasts (same slot pair, paired by cycle):")
    print("    contrast      pair   K      mean    95% hw        lo        hi"
          "  sign +/-")
    agg = defaultdict(list)
    for i, x in enumerate(arms):
        for y in arms[i + 1:]:
            for p in pairs:
                d = [b - a for a, b in zip(bypair[p][x], bypair[p][y])]
                m = statistics.mean(d)
                hw = (t95(len(d) - 1) * statistics.stdev(d) / math.sqrt(len(d))
                      if len(d) > 1 else float("nan"))
                pos = sum(1 for v in d if v > 0)
                print(f"     {x}->{y}   {{{p[0]},{p[1]}}} sep{p[1]-p[0]}  "
                      f"{len(d):2d}  {m:8.2f}  {hw:8.2f}  {m-hw:8.2f}  "
                      f"{m+hw:8.2f}   {pos}/{len(d)-pos}")
                agg[(x, y)].append(m)
            print()

    print("agreement of the three position-matched estimates with each other:")
    for (x, y), ms in agg.items():
        spread = max(ms) - min(ms)
        print(f"     {x}->{y}: {' '.join(f'{v:+.2f}' for v in ms)}   "
              f"mean {statistics.mean(ms):+.2f}   spread {spread:.2f}   "
              f"all same sign: {'yes' if min(ms) * max(ms) > 0 else 'NO'}")


if __name__ == "__main__":
    main()
