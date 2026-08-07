#!/usr/bin/env python3
"""4-way per-arm op census over the probe metallib IR, reusing a2_census.classify."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tanjiro_ir_census_lib import classify, FUNC_RE  # noqa: E402
from collections import Counter  # noqa: E402

AXES = ["mma", "barrier", "dev_load", "tg_load", "tg_store", "int_alu", "float_alu"]
ARMS = {0: "pb0 (control)", 1: "pb1 M2", 2: "pb2 S2", 3: "pb3 B2"}


def census(path):
    funcs, cur = {}, None
    for line in open(path):
        m = FUNC_RE.match(line)
        if m:
            cur = m.group(1)
            funcs.setdefault(cur, Counter())
            continue
        if line.startswith("}"):
            cur = None
            continue
        if cur is None:
            continue
        for ax in classify(line):
            funcs[cur][ax] += 1
    return funcs


def shape_of(name):
    for s in ("2048x1024", "512x2048"):
        if s in name:
            return s
    return None


rows = {}
for p in ARMS:
    for name, c in census(f"/tmp/naxpb{p}/unit.ll").items():
        if "gather_qmm_rhs" not in name:
            continue
        sh = shape_of(name)
        if sh:
            rows[(p, sh)] = c

hdr = "| arm | shape | " + " | ".join(AXES) + " |"
print(hdr)
print("|" + "---|" * (len(AXES) + 2))
for p in sorted(ARMS):
    for sh in ("2048x1024", "512x2048"):
        c = rows.get((p, sh))
        if c is None:
            print(f"| {ARMS[p]} | {sh} | MISSING |")
            continue
        print(f"| {ARMS[p]} | {sh} | " + " | ".join(str(c[a]) for a in AXES) + " |")

print("\n## delta vs pb0 (both shapes must agree for a clean axis)")
for p in (1, 2, 3):
    changed, same = [], []
    for a in AXES:
        d = {sh: rows[(p, sh)][a] - rows[(0, sh)][a] for sh in ("2048x1024", "512x2048")}
        (changed if any(d.values()) else same).append(
            f"{a}{'' if not any(d.values()) else '(' + ','.join(f'{v:+d}' for v in d.values()) + ')'}"
        )
    print(f"\n{ARMS[p]}:")
    print(f"  CHANGED   : {', '.join(changed) or 'none'}")
    print(f"  UNCHANGED : {', '.join(same) or 'none'}")
