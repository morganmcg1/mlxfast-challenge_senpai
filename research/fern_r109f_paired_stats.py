#!/usr/bin/env python3
"""fern r109-f: paired statistics for an interleaved A/B over --local-submit.

Reads the two per-arm parsed JSON files written by fern_r109f_parse_ladder.py and
adjudicates on the RAW DECODE LEG, not on the local score.

Why not the score: the local host's prefill floor fails on every draw
(passed_prefill_speedup_floor false, prefill ~0.00111 vs REF 0.000368 = 0.33x)
under the 48 GiB low-memory startup profile, so the local `ns`/score is not
comparable to the official ~2.6 scale. The decode leg, by contrast, is measured
here at cv ~0.033%, which is what makes a 3-pair local A/B decisive: the score
elasticity on the decode leg is 0.75, so a +0.38% score effect is a -0.507%
decode move, i.e. ~15 sd.

Usage: fern_r109f_paired_stats.py <dir> <labelA> <labelB>
"""
from __future__ import annotations

import json
import math
import sys

REF_DECODE = 0.01385621216015625
REF_PREFILL = 0.00036751938916015626

# Two-sided 95% t quantiles by degrees of freedom.
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
       7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179}


def t95(df: int) -> float:
    if df <= 0:
        return float("nan")
    return T95.get(df, 1.96)


def mean(xs):
    return sum(xs) / len(xs)


def sd(xs):
    if len(xs) < 2:
        return float("nan")
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def ns(decode: float, prefill: float) -> float:
    return (REF_DECODE / decode) ** 0.75 * (REF_PREFILL / prefill) ** 0.25


def load(directory: str, label: str):
    with open(f"{directory}/{label}-parsed.json") as fh:
        return json.load(fh)


def describe(name, xs, unit="", pct_of=None):
    m, s = mean(xs), sd(xs)
    cv = 100.0 * s / m if m else float("nan")
    line = f"{name:<22} n={len(xs)} mean={m:.9g}{unit}"
    if len(xs) >= 2:
        line += f" sd={s:.4g} cv={cv:.4f}%"
    print(line)
    return m, s


def paired(name, a, b, lower_is_better=True):
    """b - a, paired by draw index."""
    n = min(len(a), len(b))
    d = [b[i] - a[i] for i in range(n)]
    rel = [100.0 * (b[i] - a[i]) / a[i] for i in range(n)]
    md, sdd = mean(d), sd(d)
    mr = mean(rel)
    sr = sd(rel)
    df = n - 1
    half = t95(df) * sdd / math.sqrt(n) if n >= 2 else float("nan")
    halfr = t95(df) * sr / math.sqrt(n) if n >= 2 else float("nan")
    print(f"\n{name}: paired B-A over n={n} pairs")
    print(f"  per-pair deltas   : {', '.join(f'{x:+.6g}' for x in d)}")
    print(f"  per-pair relative : {', '.join(f'{x:+.4f}%' for x in rel)}")
    print(f"  mean delta        : {md:+.6g}  95% CI [{md - half:+.6g}, {md + half:+.6g}]")
    print(f"  mean relative     : {mr:+.4f}%  95% CI [{mr - halfr:+.4f}%, {mr + halfr:+.4f}%]")
    if n >= 2 and sdd > 0:
        tstat = md / (sdd / math.sqrt(n))
        print(f"  t({df})            : {tstat:+.3f}   |t|>{t95(df):.3f} => significant at 95%")
        sig = abs(tstat) > t95(df)
    else:
        sig = False
    if sig:
        good = (md < 0) if lower_is_better else (md > 0)
        print(f"  VERDICT           : significant, {'IMPROVEMENT' if good else 'REGRESSION'}")
    else:
        print("  VERDICT           : not distinguishable from zero at 95%")
    return md, mr, half, halfr, sig


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    directory, la, lb = sys.argv[1], sys.argv[2], sys.argv[3]
    A, B = load(directory, la), load(directory, lb)
    n = min(len(A), len(B))
    if n < 1:
        print("no pairs")
        return 1
    A, B = A[:n], B[:n]

    print(f"=== paired A/B: A={la} (n={len(A)})  B={lb} (n={len(B)})  pairs={n} ===\n")

    # Correctness gate first: a perf win that changes numerics is not a win.
    bad = []
    for label, rows in ((la, A), (lb, B)):
        for r in rows:
            if r.get("max_abs_diff") != 0 or not r.get("pc"):
                bad.append(f"{label}:{r['log']} max_abs_diff={r.get('max_abs_diff')} pc={r.get('pc')}")
    print("correctness: " + ("ALL DRAWS max_abs_diff==0 and passed_correctness" if not bad
                             else "FAILED -> " + "; ".join(bad)))
    hashes = {r["golden_hash"] for r in A + B} | set()
    print(f"golden_hash unique across arms: {len(hashes)} -> {sorted(hashes)}")
    hh = {r["harness_hash"] for r in A + B}
    print(f"harness_hash unique across arms: {len(hh)} -> {sorted(hh)}")
    print("  (one harness_hash across both arms is expected and is the point: the arms")
    print("   differ only by DARKBLOOM_ env, so the submitted source is identical and an")
    print("   official run could not tell them apart -- env is an instrument, not a ship.)")

    print()
    for label, rows in ((la, A), (lb, B)):
        print(f"--- {label} ---")
        describe("decode s/tok", [r["decode"] for r in rows])
        describe("prefill s/tok", [r["prefill"] for r in rows])
        describe("harness score", [r["score"] for r in rows])
        describe("ns(harness consts)", [ns(r["decode"], r["prefill"]) for r in rows])
        print()

    dmd, dmr, _, dhalfr, dsig = paired(
        "DECODE LEG (primary)", [r["decode"] for r in A], [r["decode"] for r in B])
    paired("prefill leg", [r["prefill"] for r in A], [r["prefill"] for r in B])
    paired("harness score", [r["score"] for r in A], [r["score"] for r in B],
           lower_is_better=False)

    # Decode-only score implication: score elasticity on the decode leg is 0.75,
    # so a relative decode change r maps to (1+r)^-0.75 - 1 on the score.
    print("\n--- decode-only score implication (elasticity 0.75, prefill held fixed) ---")
    r = dmr / 100.0
    lo = (dmr - dhalfr) / 100.0
    hi = (dmr + dhalfr) / 100.0
    def sc(x):
        return 100.0 * ((1.0 + x) ** -0.75 - 1.0)
    print(f"  decode {dmr:+.4f}% -> score {sc(r):+.4f}%   "
          f"95% CI [{sc(hi):+.4f}%, {sc(lo):+.4f}%]")
    print(f"  frieren #714 claimed +0.38% score (= -0.507% decode). "
          f"{'CONSISTENT' if lo <= -0.507 <= hi else 'NOT consistent with this CI'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
