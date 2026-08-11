#!/usr/bin/env python3
"""r116 -- P(crown) is dominated by which sigma you believe.

Section 0P.13 built the campaign's EV table on a per-draw replication sd of
**0.6590 % relative (56 df)**, pooled across the whole field.  Section 0P.15
then measured the same quantity inside five byte-equivalent *maple* families
and got **0.4938 % (8 df)**.  I recorded those as "cross-validated" because
they are not significantly different -- F = (0.6590/0.4938)^2 = 1.78 on
(56, 8) df against a 5 % critical value of ~3.1.

That was the right test for the wrong question.  We are not asking whether the
two sigmas differ; we are asking for a **tail probability 1.5-2 sigma out**,
and a tail probability is exquisitely sensitive to sigma even when the sigmas
themselves are statistically indistinguishable.  A 33 % difference in sigma is
a 3x difference in P(crown).

This script prints the EV table under both sigmas so the sensitivity is
visible, and reports how much verified code gain is needed to reach a target
P(crown) under each.

Which sigma is the right one?  The quantity we need is the replication sd of
*our own fixed executable* drawn repeatedly.  That is definitionally the
within-family number (0.4938 %).  The field-pooled 0.6590 % additionally
absorbs cross-solver differences in rig, harness and executable, so it is an
upper bound.  Conclusion: treat 0.4938 % as the working value and 0.6590 % as
the optimistic bound -- and note that the *pessimistic* direction for sigma is
the *optimistic* direction for P(crown), which is a trap worth naming.
"""
from __future__ import annotations

import math

CROWN = 2.61650354381456
# maple HEAD executable class, n = 4 (section 0P.15)
HEAD_MEAN = 2.58989575
HEAD_N = 4

SIGMAS = {
    "0P.15 within-family (8 df)  [working value]": 0.004938,
    "0P.13 field-pooled  (56 df) [optimistic bound]": 0.006590,
}
GAINS = [0.0, 0.0025, 0.0050, 0.0100]
NS = [1, 5, 10, 20, 30, 40]

# Gauss-Hermite nodes for marginalising over the uncertainty in mu
GH_X = [-2.02018287, -0.95857246, 0.0, 0.95857246, 2.02018287]
GH_W = [0.01995324, 0.39361932, 0.94530872, 0.39361932, 0.01995324]
GH_NORM = math.sqrt(math.pi)


def phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def p_crown(gain_rel: float, sigma_rel: float, n: int) -> float:
    """E_mu[ 1 - Phi((crown - mu)/sigma)^n ], mu ~ N(mean*(1+gain), se^2)."""
    mu0 = HEAD_MEAN * (1.0 + gain_rel)
    sd = sigma_rel * HEAD_MEAN          # absolute score units
    se = sd / math.sqrt(HEAD_N)         # uncertainty in the class mean
    acc = 0.0
    for x, w in zip(GH_X, GH_W):
        mu = mu0 + math.sqrt(2.0) * se * x
        acc += w * (1.0 - phi((CROWN - mu) / sd) ** n)
    return acc / GH_NORM


def gain_for_target(sigma_rel: float, n: int, target: float) -> float:
    lo, hi = 0.0, 0.10
    if p_crown(hi, sigma_rel, n) < target:
        return float("nan")
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if p_crown(mid, sigma_rel, n) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def main() -> None:
    gap = (CROWN - HEAD_MEAN) / HEAD_MEAN
    print(f"crown              {CROWN:.8f}")
    print(f"maple HEAD class   {HEAD_MEAN:.8f}  (n={HEAD_N})")
    print(f"gap to crown       {gap*100:+.4f} %")
    for label, s in SIGMAS.items():
        print(f"  gap in sigma units, {label:46s} {gap/s:.3f}")
    print()

    for label, s in SIGMAS.items():
        print(f"== sigma = {s*100:.4f} %  --  {label} ==")
        hdr = "  verified gain | " + " | ".join(f"n={n:<3d}" for n in NS)
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for g in GAINS:
            cells = " | ".join(f"{p_crown(g, s, n)*100:5.1f}%" for n in NS)
            print(f"    {g*100:+6.2f} %     | {cells}")
        print()

    print("== how much verified code gain buys a given P(crown) at n=20 ==")
    for target in (0.50, 0.80, 0.90):
        parts = []
        for label, s in SIGMAS.items():
            g = gain_for_target(s, 20, target)
            parts.append(f"{label.split('(')[0].strip()}: {g*100:+.3f} %")
        print(f"  P >= {target*100:.0f}%   " + "   |   ".join(parts))
    print()

    print("== marginal value of the LAST 10 draws vs +0.25 % of verified code ==")
    for label, s in SIGMAS.items():
        d = (p_crown(0.0, s, 30) - p_crown(0.0, s, 20)) * 100
        c = (p_crown(0.0025, s, 20) - p_crown(0.0, s, 20)) * 100
        print(f"  {label.split('(')[0].strip():30s}"
              f" +10 draws: {d:+5.1f} pp   +0.25 % code: {c:+5.1f} pp"
              f"   ratio {c/d if d else float('nan'):.2f}x")


if __name__ == "__main__":
    main()
