"""Per-arm wall / gpu_busy / gap decomposition for the r100-B census.

Reports the ABBA-paired delta of each channel so a wall movement can be
attributed to removed GPU work rather than to CPU-side gap drift.
"""

import glob
import os
import re
import statistics
import sys

PCT_PER_US_STEP = 0.015280
SLOT_RE = re.compile(r"^(\d+)-rep(\d+)-([a-z_0-9]+)\.log$")
PROF_RE = re.compile(
    r"per steady step: wall=([\d.]+) ms gpu_busy_sum=([\d.]+) ms "
    r"gpu_busy_union=([\d.]+) ms gap=([\d.]+) ms")

T95 = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447, 8: 2.365}


def main():
    slots = {}
    for path in sorted(glob.glob(sys.argv[1])):
        m = SLOT_RE.match(os.path.basename(path))
        if not m:
            continue
        with open(path) as fh:
            pm = PROF_RE.search(fh.read())
        if not pm:
            continue
        slots[int(m.group(1))] = (
            m.group(3), [float(pm.group(i)) * 1000.0 for i in (1, 2, 3, 4)])

    names = ("wall", "busy_sum", "busy_union", "gap")
    print(f"{'slot':>4} {'arm':>5} " + " ".join(f"{n:>11}" for n in names))
    for idx in sorted(slots):
        arm, vals = slots[idx]
        print(f"{idx:>4} {arm:>5} " + " ".join(f"{v:11.1f}" for v in vals))
    print()

    for j, name in enumerate(names):
        for arm in ("base", "cand"):
            vs = [v[j] for a, v in slots.values() if a == arm]
            print(f"  {name:>11} {arm}: mean {statistics.mean(vs):8.1f} "
                  f"SD {statistics.stdev(vs):6.1f} us/step (n={len(vs)})")
        keys = sorted(slots)
        deltas = []
        for i in range(0, len(keys) - 1, 2):
            a, b = slots[keys[i]], slots[keys[i + 1]]
            sign = 1.0 if a[0] == "base" else -1.0
            deltas.append(sign * (b[1][j] - a[1][j]))
        n = len(deltas)
        mean, sd = statistics.mean(deltas), statistics.stdev(deltas)
        half = T95[n] * sd / (n ** 0.5)
        print(f"  {name:>11} ABBA cand-base: {mean:+.2f} "
              f"[{mean-half:+.2f}, {mean+half:+.2f}] us/step  SD {sd:.2f}  n={n}")
        print()


if __name__ == "__main__":
    main()
