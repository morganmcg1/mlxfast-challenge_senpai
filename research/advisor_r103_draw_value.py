#!/usr/bin/env python3
"""What is a receipt worth, once identical-code replicate noise is priced in?

Two channels of randomness stand between a tree and the leaderboard:

  score = cs * L

  * L  -- the baseline draw. Empirical, 1,205 observations in the frozen corpus.
  * cs -- the candidate draw. Measured on BYTE-IDENTICAL code:
          sd(ln cs) = 0.2276 % (08-09 quintuplet), 0.1860 % (trimmed pooled).

Every previous p(record)/draw number in this campaign integrated only L, i.e. it
answered "given this REALISED cs, what is the chance of the record?".  The
planning question is different: "given a tree whose TRUE cs is mu, what is the
chance that one more submission of it takes the record?"  That convolves both
channels, and because the tail is convex it is strictly larger.
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "artifacts", "advisor-r103", "receipt-corpus-frozen.json")

RECORD = 2.61650354381456  # a-github-name, 2026-08-08T09:17:33Z

rows = json.load(open(CORPUS))
Ls = sorted(r["L"] for r in rows if r.get("L"))
n = len(Ls)
mL = sum(math.log(x) for x in Ls) / n
sL = math.sqrt(sum((math.log(x) - mL) ** 2 for x in Ls) / (n - 1))
print(f"empirical L: n={n}  median={Ls[n//2]:.6f}  sd(ln L)={100*sL:.4f}%")

# Gauss-Hermite-ish: a fixed symmetric grid on the cs-noise axis is plenty here.
GRID = [(-3.0, 0.0044), (-2.5, 0.0180), (-2.0, 0.0540), (-1.5, 0.1295),
        (-1.0, 0.2420), (-0.5, 0.3521), (0.0, 0.3989), (0.5, 0.3521),
        (1.0, 0.2420), (1.5, 0.1295), (2.0, 0.0540), (2.5, 0.0180),
        (3.0, 0.0044)]
STEP = 0.5
WSUM = sum(w for _, w in GRID) * STEP


def p_record(mu, sd_ln_cs):
    """P(one submission of a tree with true cs=mu beats RECORD)."""
    if sd_ln_cs <= 0:
        return sum(1 for L in Ls if mu * L > RECORD) / n
    acc = 0.0
    for z, w in GRID:
        cs = mu * math.exp(z * sd_ln_cs)
        hits = sum(1 for L in Ls if cs * L > RECORD)
        acc += w * STEP * hits / n
    return acc / WSUM


def draws_for(p, target=0.5):
    if p <= 0:
        return float("inf")
    return math.log(1 - target) / math.log(1 - p)


SD_Q = 0.002276   # 08-09 quintuplet
SD_P = 0.001860   # trimmed pooled

CANDS = [
    ("honest mean of the r93-null quintuplet", 2.583111),
    ("  its 95% CI low", 2.577962),
    ("  its 95% CI high", 2.588271),
    ("realised max of that group (2.590559)", 2.590559143419936),
    ("Arm R receipt 7ce1262d", 2.5893213006341584),
    ("merged frontier e08d759f", 2.582286297407117),
    ("post-revert control 59bd72a3", 2.575633169483906),
    ("corpus max cs (MyatKaung)", 2.591868),
    ("hypothetical +0.3% on the honest mean", 2.583111 * math.exp(0.003)),
    ("hypothetical +1.0% on the honest mean", 2.583111 * math.exp(0.010)),
]

print(f"\nrecord to beat: score = {RECORD}")
print("\n                                          p(record)/draw          "
      "draws for 50%")
print("  tree                                  L-only  +sd.186% +sd.228%   "
      "L-only  +sd.228%")
for name, mu in CANDS:
    p0 = p_record(mu, 0.0)
    p1 = p_record(mu, SD_P)
    p2 = p_record(mu, SD_Q)
    d0 = draws_for(p0)
    d2 = draws_for(p2)
    print(f"  {name:38s} {100*p0:6.3f}% {100*p1:7.3f}% {100*p2:7.3f}%   "
          f"{d0:7.0f} {d2:8.0f}")

print("\n=== marginal value of real work vs. more draws ===")
base = 2.583111
p_base = p_record(base, SD_Q)
for gain_pct in (0.1, 0.2, 0.3, 0.5, 1.0):
    mu = base * math.exp(gain_pct / 100.0)
    p = p_record(mu, SD_Q)
    print(f"  a genuine +{gain_pct:.1f}% of cs multiplies p/draw by "
          f"{p/p_base:5.2f}x  ({100*p_base:.3f}% -> {100*p:.3f}%), "
          f"i.e. it is worth {draws_for(p_base)-draws_for(p):.0f} draws "
          f"of the current tree")

print("\n=== how big must a REAL effect be to be worth chasing? ===")
print("  1% of cs = 65.67 us/step of T; decode price 0.015228 %/us-step")
for us in (10, 20, 30, 50, 100):
    print(f"  {us:4d} us/step of T = {us*0.015228:.4f}% of cs -> "
          f"p/draw {100*p_record(base*math.exp(us*0.015228/100), SD_Q):.3f}%")
