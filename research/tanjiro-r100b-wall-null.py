"""Wall-clock adjacent-duplex contrast and same-arm null control for the r100-B census.

The r85-C wall stats driver only emits offset-0 (base|cand) duplexes. To decide
whether the wall signal clears the in-session noise floor we also need the
identical-code spread, i.e. adjacent duplexes whose two slots ran the same
binary. The ABBA order "base cand cand base" supplies those at offset 1.
"""

import glob
import os
import re
import statistics
import sys

PCT_PER_US_STEP = 0.015280
SLOT_RE = re.compile(r"^(\d+)-rep(\d+)-([a-z_0-9]+)\.steps$")


def load(pattern):
    slots = {}
    for path in sorted(glob.glob(pattern)):
        m = SLOT_RE.match(os.path.basename(path))
        if not m:
            continue
        idx, _rep, arm = int(m.group(1)), int(m.group(2)), m.group(3)
        with open(path) as fh:
            ms = [float(x) for x in fh if x.strip()]
        slots[idx] = (arm, [v * 1000.0 for v in ms[1:]])  # drop step 0, ms -> us
    return slots


def t95(n):
    table = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571,
             7: 2.447, 8: 2.365, 9: 2.306, 10: 2.262}
    return table.get(n, 1.96)


def duplexes(slots, offset):
    out = []
    keys = sorted(slots)
    for i in range(offset, len(keys) - 1, 2):
        a, b = keys[i], keys[i + 1]
        out.append((a, slots[a], b, slots[b]))
    return out


def report(title, pairs, same_arm):
    """Positive = candidate faster (a win). For same-arm pairs the label is
    arbitrary, so we report the raw spread magnitude instead."""
    deltas = []
    for ai, (aarm, av), bi, (barm, bv) in pairs:
        if same_arm and aarm != barm:
            continue
        if not same_arm and aarm == barm:
            continue
        am, bm = statistics.median(av), statistics.median(bv)
        if same_arm:
            d = bm - am
            tag = f"{aarm}->{barm}"
        else:
            sign = 1.0 if aarm == "base" else -1.0
            d = -sign * (bm - am)
            tag = f"{aarm}->{barm}"
        deltas.append(d)
        print(f"    slots {ai:2d}->{bi:2d}  {tag:11s}  {d:+8.2f} us/step")
    n = len(deltas)
    if n < 2:
        print(f"  {title}: n={n}, nothing to summarise")
        return
    mean = statistics.mean(deltas)
    sd = statistics.stdev(deltas)
    half = t95(n) * sd / (n ** 0.5)
    print(f"  {title}: n={n} mean {mean:+.2f} [{mean-half:+.2f}, {mean+half:+.2f}] "
          f"us/step  SD {sd:.2f}")
    print(f"    median {statistics.median(deltas):+.2f} us/step   "
          f"score {mean*PCT_PER_US_STEP:+.4f}% "
          f"[{(mean-half)*PCT_PER_US_STEP:+.4f}, {(mean+half)*PCT_PER_US_STEP:+.4f}]")
    print()


def main():
    slots = load(sys.argv[1])
    print(f"loaded {len(slots)} slots, "
          f"{len(next(iter(slots.values()))[1])} steady steps each\n")
    print("CONTRAST base|cand adjacent duplexes (offset 0), positive = cand faster")
    report("wall contrast", duplexes(slots, 0), same_arm=False)
    print("NULL identical-code adjacent duplexes (offset 1)")
    report("wall null", duplexes(slots, 1), same_arm=True)


if __name__ == "__main__":
    main()
