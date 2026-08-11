#!/usr/bin/env python3
"""maple-nezuko-r117-block-bootstrap.py

Percentile block-bootstrap CI95 on the MEDIAN of the paired per-block
difference, for the R107-J' certification TSV.

Why this exists separately from `maple-nezuko-r107j-paired-ci.py`:
that script reports a Student-t CI on the MEAN of the block differences.
The advisor's decision rule for R117 is explicitly a *bootstrap CI on the
median*, which is what this script computes.  The two are reported side by
side; if they disagree, the disagreement is the finding and is reported as
such rather than resolved by picking the friendlier one.

Resampling unit = the BLOCK, because the block is the unit of randomisation
in the instrument (arms are rotated within a block, so a block contains one
observation of every arm under one common local machine state).  Resampling
individual runs instead would break the pairing and understate the interval.

Point estimate  : median_b (arm_b - ref_b)
Interval        : percentile bootstrap, B resamples of blocks with replacement
Sign test       : exact two-sided binomial on sign(D_b), a distribution-free
                  cross-check that does not assume symmetry.

Usage:  python3 research/maple-nezuko-r117-block-bootstrap.py ROWS.tsv [...]
Env:    B=20000     bootstrap resamples
        SEED=117    RNG seed (fixed so the published interval is reproducible)
        REF=<label> reference arm (default: first arm seen in the file)
"""
import math
import os
import random
import sys
from collections import OrderedDict


def load(paths):
    rows = []
    for p in paths:
        with open(p) as fh:
            head = fh.readline().rstrip("\n").split("\t")
            for line in fh:
                if not line.strip():
                    continue
                parts = line.rstrip("\n").split("\t")
                rec = dict(zip(head, parts))
                rows.append(rec)
    return rows


def main():
    paths = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not paths:
        print("usage: maple-nezuko-r117-block-bootstrap.py ROWS.tsv [...]")
        return 2
    B = int(os.environ.get("B", "20000"))
    seed = int(os.environ.get("SEED", "117"))
    rows = load(paths)

    bad = [r for r in rows if r.get("passed") != "true"]
    goldens = sorted({r.get("golden", "") for r in rows if r.get("golden")})

    # arm order of first appearance; reference = first unless REF given
    arms = list(OrderedDict((r["arm"], None) for r in rows).keys())
    ref = os.environ.get("REF", arms[0])

    # block -> arm -> us/token   and   block -> arm -> position
    tab = {}
    pos = {}
    for r in rows:
        try:
            v = float(r["decode_s_per_token"]) * 1e6
        except (KeyError, ValueError):
            continue
        tab.setdefault(int(r["block"]), {})[r["arm"]] = v
        pos.setdefault(int(r["block"]), {})[r["arm"]] = int(r["pos"])

    print("=" * 78)
    print("R117 block bootstrap -- CI95 on the MEDIAN of the paired block difference")
    print(f"files      : {' '.join(paths)}")
    print(f"reference  : {ref}    arms: {', '.join(arms)}")
    print(f"B          : {B}   seed: {seed}   unit of resampling: BLOCK")
    print(f"correctness: {len(bad)} failed runs; distinct golden hashes: {len(goldens)}")
    for g in goldens:
        print(f"             golden {g[:24]}")
    print("=" * 78)

    for arm in arms:
        if arm == ref:
            continue
        blocks = sorted(b for b in tab if arm in tab[b] and ref in tab[b])
        D = [tab[b][arm] - tab[b][ref] for b in blocks]
        n = len(D)
        if n == 0:
            continue
        print()
        print("-" * 78)
        print(f"PAIRED CONTRAST  {arm} - {ref}   (negative = {arm} FASTER)")
        print("-" * 78)
        for b, d in zip(blocks, D):
            print(f"  block {b:<3d} {arm}={tab[b][arm]:10.3f}  {ref}={tab[b][ref]:10.3f}"
                  f"   D={d:+9.3f} us")
        srt = sorted(D)
        med = (srt[n // 2] if n % 2 else 0.5 * (srt[n // 2 - 1] + srt[n // 2]))
        mean = sum(D) / n
        rng = random.Random(seed)
        boot = []
        for _ in range(B):
            s = sorted(D[rng.randrange(n)] for _ in range(n))
            boot.append(s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2]))
        boot.sort()
        lo = boot[int(0.025 * (B - 1))]
        hi = boot[int(0.975 * (B - 1))]
        neg = sum(1 for d in D if d < 0)
        npos = sum(1 for d in D if d > 0)
        k = min(neg, npos)
        # exact two-sided sign test
        m = neg + npos
        if m:
            psign = 2.0 * sum(math.comb(m, i) for i in range(0, k + 1)) / (2.0 ** m)
            psign = min(1.0, psign)
        else:
            psign = 1.0
        print()
        print(f"  n_blocks        = {n}")
        print(f"  median D        = {med:+9.3f} us/token   <-- POINT ESTIMATE")
        print(f"  mean   D        = {mean:+9.3f} us/token")
        print(f"  bootstrap CI95  = [{lo:+9.3f}, {hi:+9.3f}] us/token")
        print(f"  covers zero     : {'YES' if lo <= 0 <= hi else 'NO'}")
        print(f"  |median| >= 10  : {'YES' if abs(med) >= 10.0 else 'NO'}")
        print(f"  sign test       : {neg} negative / {npos} positive, exact two-sided p={psign:.4f}")
        print(f"  relative        : {100.0 * med / (sum(tab[b][ref] for b in blocks) / n):+.4f} % of decode wall")

        # ---- order-balance sensitivity -------------------------------------
        # The instrument rotates arm order by one slot per block, so with A
        # arms the design is order-balanced only on a whole multiple of A
        # blocks.  Re-state the contrast on the largest balanced prefix; if the
        # two disagree, the difference is an order artefact and not an effect.
        A = len(arms)
        nb = (n // A) * A
        if 0 < nb < n:
            Db = D[:nb]
            sb = sorted(Db)
            mb = sb[len(sb) // 2] if len(sb) % 2 else 0.5 * (
                sb[len(sb) // 2 - 1] + sb[len(sb) // 2])
            print(f"  order-balanced  : first {nb} of {n} blocks "
                  f"({nb // A} complete rotations) median D = {mb:+9.3f} us")
        elif nb == n:
            print(f"  order-balanced  : all {n} blocks are order-balanced "
                  f"({n // A} complete rotations)")

    # ---- position diagnostic ----------------------------------------------
    print()
    print("-" * 78)
    print("POSITION DIAGNOSTIC (level by within-block slot, all arms pooled)")
    print("-" * 78)
    byslot = {}
    for b in tab:
        for a, v in tab[b].items():
            byslot.setdefault(pos[b][a], []).append(v)
    for s in sorted(byslot):
        vs = byslot[s]
        print(f"  slot {s}: n={len(vs):2d}  mean={sum(vs) / len(vs):10.3f} us/token")
    print("  arm-by-slot occupancy (an unbalanced table means order is confounded):")
    for a in arms:
        occ = {}
        for b in tab:
            if a in pos.get(b, {}):
                occ[pos[b][a]] = occ.get(pos[b][a], 0) + 1
        print(f"    {a:<4s} " + "  ".join(f"slot{s}={occ.get(s, 0)}"
                                          for s in sorted(byslot)))

    return 0


if __name__ == "__main__":
    sys.exit(main())
