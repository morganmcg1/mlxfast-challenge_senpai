#!/usr/bin/env python3
"""Pair a two-arch census TSV into one matched-null delta row per kernel.

Rule 42: static __compute bytes are admissible only as a matched-null
difference; never divide by 8. The floor correction is a bracket, not a scalar,
because control 2 showed the g16s-minus-g17s floor delta is -16 B for plain
kernels and 0 B once simdgroup/lane attributes are declared.

Usage: delta_table.py CENSUS_TSV [STUDY]
"""
import collections
import sys

path = sys.argv[1]
study = sys.argv[2] if len(sys.argv) > 2 else "r92_decode"

bytes_of = collections.defaultdict(dict)
with open(path) as fh:
    next(fh)
    for line in fh:
        s, arch, fn, nb = line.rstrip("\n").split("\t")
        bytes_of[(s, fn)][arch] = int(nb)

rows = []
for (s, fn), per_arch in bytes_of.items():
    if s != study:
        continue
    g16 = per_arch.get("applegpu_g16s")
    g17 = per_arch.get("applegpu_g17s")
    if g16 is None or g17 is None:
        print(f"INCOMPLETE\t{fn}\t{per_arch}")
        continue
    rows.append((fn, g16, g17, g17 - g16))

rows.sort(key=lambda r: -r[3])
print(f"{'kernel':66s}{'g16s':>8s}{'g17s':>8s}{'raw':>7s}{'pct':>8s}  verdict")
for fn, g16, g17, d in rows:
    lo, hi = d, d + 16  # floor correction bracket: -16 .. 0
    if abs(lo) <= 16 and abs(hi) <= 16:
        verdict = "noise"
    elif lo > 16:
        verdict = "POSITIVE"
    elif hi < -16:
        verdict = "negative"
    else:
        verdict = "bracket-spans-noise"
    print(f"{fn:66s}{g16:8d}{g17:8d}{d:7d}{100.0*d/g16:7.1f}%  {verdict}")
