#!/usr/bin/env python3
"""Compare per-kernel GPUPROF tables across DARKBLOOM_NVFP4_NIBBLE_SPLIT arms.

Reads the logs written by nibble-split-profile.sh (`p<i>_<arm>.log`), averages
the reps of each arm, and prints the kernels whose us/step moves most between
the pooled treatment P = {0, 2} and the shipped default 1.

Arms 0 and 2 compile to a byte-identical metallib (nibble-split-isa.sh), so the
row-by-row |0 - 2| spread is the profiler's own reproducibility floor.  A
[P - 1] row is only interesting if it clears that floor.

ATTRIBUTION ONLY: these runs carry the SPLIT=1 hook, which inflates wall by
~19.6 % and mis-ranks arms.  Never quote a number from here as a ranking.

    research/maple-tanjiro-r110/nibble-split-profile-diff.py OUT_DIR
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

ROW = re.compile(r"^\s*([0-9.]+)\s+([0-9.]+)%\s+([0-9.]+)\s+([0-9.]+)\s\s+(.*)$")
HDR = re.compile(r"^\s*us/step\s+share\s+n/step")
SUMMARY = re.compile(r"^per steady step: (.*)$")


def parse(path):
    kern, summary, in_tbl = {}, "", False
    for line in path.read_text(errors="replace").splitlines():
        m = SUMMARY.match(line)
        if m:
            summary = m.group(1)
        if HDR.match(line):
            in_tbl = True
            continue
        if in_tbl:
            m = ROW.match(line)
            if not m:
                if line.strip() and "more" not in line:
                    in_tbl = False
                continue
            kern[m.group(5).strip()] = float(m.group(1))
    return kern, summary


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/r116b-prof")
    per_arm = defaultdict(list)
    for p in sorted(out.glob("p*_*.log")):
        arm = p.stem.rsplit("_", 1)[1]
        kern, summary = parse(p)
        if not kern:
            print(f"!! {p.name}: no kernel table")
            continue
        per_arm[arm].append(kern)
        print(f"{p.name}  arm={arm}  {summary}")
    if not per_arm:
        sys.exit("no parsable logs")

    def mean_of(arms):
        acc, n = defaultdict(float), 0
        for a in arms:
            for k in per_arm.get(a, []):
                n += 1
                for name, us in k.items():
                    acc[name] += us
        return {name: us / n for name, us in acc.items()} if n else {}

    a0, a1, a2 = mean_of("0"), mean_of("1"), mean_of("2")
    pool = mean_of("02")
    names = sorted(set(a0) | set(a1) | set(a2),
                   key=lambda nm: -max(a0.get(nm, 0), a1.get(nm, 0)))

    print(f"\n{'P(0,2)':>9} {'arm1':>9} {'P-1':>8} {'|0-2|':>8}  kernel")
    tot_p = tot_1 = 0.0
    for nm in names:
        p, one = pool.get(nm, 0.0), a1.get(nm, 0.0)
        ctl = abs(a0.get(nm, 0.0) - a2.get(nm, 0.0))
        tot_p += p
        tot_1 += one
        print(f"{p:9.1f} {one:9.1f} {p - one:8.1f} {ctl:8.1f}  {nm}")
    print(f"{tot_p:9.1f} {tot_1:9.1f} {tot_p - tot_1:8.1f} {'':>8}  TOTAL (top rows)")

    fam = [nm for nm in names if "swiglu_qmv" in nm or "nvfp4" in nm]
    fp = sum(pool.get(nm, 0.0) for nm in fam)
    f1 = sum(a1.get(nm, 0.0) for nm in fam)
    fc = sum(abs(a0.get(nm, 0.0) - a2.get(nm, 0.0)) for nm in fam)
    print(f"\nNVFP4 family ({len(fam)} rows): P={fp:.1f} arm1={f1:.1f} "
          f"P-1={fp - f1:+.1f} us/step, negative-control |0-2| sum={fc:.1f}")


if __name__ == "__main__":
    main()
