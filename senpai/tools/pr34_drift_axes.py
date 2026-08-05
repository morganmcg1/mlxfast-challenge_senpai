#!/usr/bin/env python3
"""Decompose cross-day officialScore drift into candidate and baseline axes.

Answers the advisor's "12.4 sd" drift claim (PR #34 comment 5190411291) by
attributing each pairwise score move to the four measured axes:

    S    = 512000 * prefill_seconds_per_token       (prefill forward, ms)
    D    = 1000 * decode_seconds_per_token           (full decode ms/token)
    T    = D - S/128                                 (steady decode step, ms)

    prefill_speedup = S_base / S_cand
    decode_speedup  = D_base / D_cand
    score           = decode_speedup**0.75 * prefill_speedup**0.25

To first order in small relative changes d(.) = dx/x:

    d(prefill_su) = d(S_base) - d(S_cand)
    d(decode_su)  = d(D_base) - d(D_cand)
    d(score)      = 0.75*d(decode_su) + 0.25*d(prefill_su)

so a score move can be assigned to a leg. A move dominated by d(S_base) is
re-measurement noise on the pinned reference model, not candidate drift.

Usage: pr34_drift_axes.py
"""

import itertools

# Four frontier-equivalent receipts, fetched from the official submissions API.
# (id, day-label, cand S ms, cand T ms, base S ms, base D ms/token, published score)
# The baseline decode field the API reports is the FULL ms/token, not the
# steady step; the candidate pair is (S, T) with T already seed-corrected.
RECEIPTS = [
    ("71586bcf", "8/4 10:02", 97.5129, 4.38283, 198.8970, 13.88149, 2.515950),
    ("c210d200", "8/4 11:38", 97.9730, 4.34279, 196.0282, 13.86295, 2.514743),
    ("b6032aeb", "8/4 20:11", 97.8643, 4.27468, 187.1734, 13.88424, 2.514911),
    ("c3ce66ec", "8/5 09:33", 97.9496, 4.28121, 190.0278, 13.89953, 2.523276),
]

# Pinned calibration reference used for the normalised score `ns`.
NS_DECODE_REF = 0.013890
NS_PREFILL_REF = 0.0003845


def step(S, T):
    """Full decode ms/token = steady step + amortised seed forward."""
    return T + S / 128.0


def speedups(cS, cT, bS, bD):
    prefill = bS / cS
    decode = bD / step(cS, cT)
    return prefill, decode


def score(prefill, decode):
    return decode**0.75 * prefill**0.25


def normalised(cS, cT):
    nd = NS_DECODE_REF / (step(cS, cT) / 1000.0)
    npf = NS_PREFILL_REF / (cS / 512000.0)
    return nd**0.75 * npf**0.25


def pct(new, old):
    return 100.0 * (new / old - 1.0)


def sd(xs):
    n = len(xs)
    m = sum(xs) / n
    return (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5, m


print("=" * 78)
print("1. Reconstructed speedups and score from the four measured axes")
print("=" * 78)
print(f"{'id':<10}{'when':<11}{'prefill_su':>11}{'decode_su':>11}"
      f"{'score':>11}{'published':>11}{'ns':>10}")
rows = []
for rid, when, cS, cT, bS, bD, pub in RECEIPTS:
    p, d = speedups(cS, cT, bS, bD)
    s = score(p, d)
    ns = normalised(cS, cT)
    rows.append((rid, when, cS, cT, bS, bD, p, d, s, ns))
    print(f"{rid:<10}{when:<11}{p:>11.5f}{d:>11.5f}{s:>11.6f}{pub:>11.6f}"
          f"{ns:>10.6f}")

print()
print("=" * 78)
print("2. Per-axis spread over all four (range % of mean, sd % of mean)")
print("=" * 78)
axes = {
    "cand S": [r[2] for r in rows],
    "cand T": [r[3] for r in rows],
    "cand D": [step(r[2], r[3]) for r in rows],
    "base S": [r[4] for r in rows],
    "base D": [r[5] for r in rows],
    "prefill_su": [r[6] for r in rows],
    "decode_su": [r[7] for r in rows],
    "score": [r[8] for r in rows],
    "ns": [r[9] for r in rows],
}
print(f"{'axis':<12}{'mean':>12}{'range %':>10}{'sd %':>9}")
for name, xs in axes.items():
    s, m = sd(xs)
    print(f"{name:<12}{m:>12.5f}{100.0*(max(xs)-min(xs))/m:>10.3f}"
          f"{100.0*s/m:>9.3f}")

print()
print("=" * 78)
print("3. Pairwise attribution: which leg moved the score?")
print("=" * 78)
for a, b in itertools.combinations(range(4), 2):
    ra, rb = rows[a], rows[b]
    dcS, dcT = pct(rb[2], ra[2]), pct(rb[3], ra[3])
    dbS, dbD = pct(rb[4], ra[4]), pct(rb[5], ra[5])
    dcD = pct(step(rb[2], rb[3]), step(ra[2], ra[3]))
    dp, dd = pct(rb[6], ra[6]), pct(rb[7], ra[7])
    ds = pct(rb[8], ra[8])
    pred_p, pred_d = dbS - dcS, dbD - dcD
    pred_s = 0.75 * pred_d + 0.25 * pred_p
    base_term = 0.25 * dbS + 0.75 * dbD
    cand_term = -(0.25 * dcS + 0.75 * dcD)
    print(f"{ra[0]} -> {rb[0]}   ({ra[1]} -> {rb[1]})")
    print(f"  cand S {dcS:+7.3f}%  cand T {dcT:+7.3f}%  cand D {dcD:+7.3f}%")
    print(f"  base S {dbS:+7.3f}%  base D {dbD:+7.3f}%")
    print(f"  prefill_su {dp:+7.3f}% (linear model {pred_p:+7.3f}%)")
    print(f"  decode_su  {dd:+7.3f}% (linear model {pred_d:+7.3f}%)")
    print(f"  score      {ds:+7.3f}% (linear model {pred_s:+7.3f}%)")
    print(f"    baseline leg {base_term:+7.3f}%  candidate leg {cand_term:+7.3f}%"
          f"  -> baseline share {100.0*base_term/pred_s if pred_s else float('nan'):.0f}%")
    print()

print("=" * 78)
print("4. Is the 0.026% score sd over the first three a real stability?")
print("=" * 78)
first3 = rows[:3]
s3, m3 = sd([r[8] for r in first3])
print(f"score  mean {m3:.6f}  sd {s3:.6f}  ({100.0*s3/m3:.3f}%)")
for name, idx in (("prefill_su", 6), ("decode_su", 7)):
    xs = [r[idx] for r in first3]
    s, m = sd(xs)
    print(f"{name:<11} mean {m:.5f}  sd {s:.5f}  ({100.0*s/m:.3f}%)"
          f"  range {100.0*(max(xs)-min(xs))/m:+.3f}%")
d_dec = pct(first3[2][7], first3[0][7])
d_pre = pct(first3[2][6], first3[0][6])
print(f"\nacross the first three: decode_su {d_dec:+.3f}%, prefill_su {d_pre:+.3f}%")
print(f"weighted: 0.75*({d_dec:+.3f}) + 0.25*({d_pre:+.3f}) = "
      f"{0.75*d_dec + 0.25*d_pre:+.3f}%")
print("-> the two weighted components anticorrelate and nearly cancel, so the")
print("   small score sd is an accidental cancellation, not measurement")
print("   stability. It is not a valid sd denominator for a drift z-score.")

print()
print("=" * 78)
print("5. L0 vs the first three, on score and on candidate axes")
print("=" * 78)
l0 = rows[3]
print(f"score: L0 {l0[8]:.6f} vs mean-of-3 {m3:.6f} = {pct(l0[8], m3):+.3f}%"
      f"  = {(l0[8]-m3)/s3:+.1f} sd of the (spurious) 0.026% sd")
for name, idx in (("cand S", 2), ("cand T", 3), ("ns", 9)):
    xs = [r[idx] for r in first3]
    s, m = sd(xs)
    z = (l0[idx] - m) / s if s else float("nan")
    print(f"{name:<8} L0 {l0[idx]:.5f} vs mean-of-3 {m:.5f} = "
          f"{pct(l0[idx], m):+.3f}%  ({z:+.1f} sd, sd={100.0*s/m:.3f}%)")
print("\nverifiable same-code pair only (b6032aeb -> c3ce66ec):")
ra, rb = rows[2], rows[3]
print(f"  cand S {pct(rb[2], ra[2]):+.3f}%   cand T {pct(rb[3], ra[3]):+.3f}%"
      f"   ns {pct(rb[9], ra[9]):+.3f}%   score {pct(rb[8], ra[8]):+.3f}%")

print()
print("=" * 78)
print("6. Monotone candidate T across the four receipts?")
print("=" * 78)
ts = [r[3] for r in rows]
print("  cand T:", "  ".join(f"{t:.5f}" for t in ts))
print("  strictly decreasing over the first three:",
      ts[0] > ts[1] > ts[2])
print("  cand S range over all four: "
      f"{100.0*(max(r[2] for r in rows)-min(r[2] for r in rows))/rows[0][2]:.3f}%")
print("-> flat S with monotone-falling T is the signature of promoted decode")
print("   work, so the first two receipts may not be the same scored code.")
