#!/usr/bin/env python3
"""Percentile block bootstrap on the MEDIAN paired per-block delta for the
R125-C threads-per-threadgroup ladder.

Consumes the raw per-step CSVs written by research/edward_r125c_ladder.sh
(order_tag,block,run,arm,step,ms).

Unit of resampling is the BLOCK: arms are rotated inside a block, so one block
holds one observation of every arm under one common local machine state.
Resampling runs or steps instead would break the pairing and understate the
interval.

Per (block, arm) statistic = median of that arm's steady per-step wall inside
the block, pooled over the arm's runs in that block. Delta is reported as
(candidate - reference), so a NEGATIVE delta means the candidate is faster.

Usage: python3 research/edward_r125c_bootstrap.py RAW.csv [...] [--ref A]
Env:   B=20000  SEED=125  TRIM=16
Research-only; not on editablePaths.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import random
from collections import defaultdict


def median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return float("nan")
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="+")
    ap.add_argument("--ref", default="A")
    args = ap.parse_args()

    B = int(os.environ.get("B", "20000"))
    seed = int(os.environ.get("SEED", "125"))
    trim = int(os.environ.get("TRIM", "16"))

    samples = defaultdict(list)   # (block, arm) -> [ms]
    runs = defaultdict(set)       # (block, arm) -> {run}
    arms_seen = []
    for path in args.csv:
        with open(path) as fh:
            for rec in csv.DictReader(fh):
                if int(rec["step"]) <= trim:
                    continue
                arm = rec["arm"]
                if arm not in arms_seen:
                    arms_seen.append(arm)
                key = (int(rec["block"]), arm)
                samples[key].append(float(rec["ms"]))
                runs[key].add(int(rec["run"]))

    ref = args.ref
    blocks = sorted({b for (b, _a) in samples})
    print("=" * 78)
    print("R125-C block bootstrap -- CI95 on the MEDIAN paired per-block delta")
    print(f"files    : {' '.join(args.csv)}")
    print(f"reference: {ref}   arms: {', '.join(arms_seen)}")
    print(f"B={B}  seed={seed}  trim={trim} leading steps  unit=BLOCK")
    print("=" * 78)

    lvl = {}
    for b in blocks:
        for a in arms_seen:
            if (b, a) in samples:
                lvl[(b, a)] = median(samples[(b, a)])
    print("\nper-block arm level (us/token, median of steady per-step wall):")
    hdr = "  block " + "".join(f"{a:>14s}" for a in arms_seen)
    print(hdr)
    for b in blocks:
        row = f"  {b:<6d}"
        for a in arms_seen:
            v = lvl.get((b, a))
            row += f"{v * 1000.0:14.2f}" if v is not None else f"{'-':>14s}"
        print(row)

    for a in arms_seen:
        if a == ref:
            continue
        bs = [b for b in blocks if (b, a) in lvl and (b, ref) in lvl]
        D = [(lvl[(b, a)] - lvl[(b, ref)]) * 1000.0 for b in bs]
        n = len(D)
        if n == 0:
            continue
        print()
        print("-" * 78)
        print(f"PAIRED CONTRAST  {a} - {ref}   (negative = {a} FASTER)")
        print("-" * 78)
        for b, d in zip(bs, D):
            nr = len(runs[(b, a)]) + len(runs[(b, ref)])
            print(f"  block {b:<3d} {a}={lvl[(b, a)] * 1000:9.2f}  "
                  f"{ref}={lvl[(b, ref)] * 1000:9.2f}  D={d:+8.2f} us  (runs={nr})")
        med = median(D)
        mean = sum(D) / n
        rng = random.Random(seed)
        boot = sorted(median([D[rng.randrange(n)] for _ in range(n)])
                      for _ in range(B))
        lo = boot[int(0.025 * (B - 1))]
        hi = boot[int(0.975 * (B - 1))]
        neg = sum(1 for d in D if d < 0)
        pos = sum(1 for d in D if d > 0)
        m = neg + pos
        k = min(neg, pos)
        psign = min(1.0, 2.0 * sum(math.comb(m, i)
                                   for i in range(k + 1)) / (2.0 ** m)) if m else 1.0
        base = sum(lvl[(b, ref)] for b in bs) / n * 1000.0
        print()
        print(f"  n_blocks       = {n}")
        print(f"  median D       = {med:+8.2f} us/token   <-- POINT ESTIMATE")
        print(f"  mean   D       = {mean:+8.2f} us/token")
        print(f"  bootstrap CI95 = [{lo:+8.2f}, {hi:+8.2f}] us/token")
        print(f"  covers zero    : {'YES' if lo <= 0 <= hi else 'NO'}")
        print(f"  wrong-sign blk : {pos if med < 0 else neg} of {n}")
        print(f"  sign test      : {neg} neg / {pos} pos, exact two-sided p={psign:.4f}")
        print(f"  relative       : {-100.0 * med / base:+.4f} % decode speedup")
        print(f"  implied phi    : {(base / (base + med)) ** 0.75:.6f} "
              f"(decode-only, prefill held at 1.0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
