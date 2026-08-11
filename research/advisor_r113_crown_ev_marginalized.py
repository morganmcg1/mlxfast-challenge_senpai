#!/usr/bin/env python3
"""R113c -- P(we take the crown in n draws), marginalized over our unknown class mean.

The trap this script exists to avoid
------------------------------------
Every previous EV table on this campaign (five of them, all wrong) computed a
single per-draw probability p and then reported 1-(1-p)^n.  That formula is
only valid when p is KNOWN.  Here it is not: our HEAD executable class mean is
estimated from n=3 receipts, so p itself is uncertain -- and, crucially, all n
future draws share the SAME unknown mean.  They are conditionally independent
given mu, not independent.

Using the predictive p in 1-(1-p)^n therefore double-counts the mean
uncertainty in the wrong direction.  The correct quantity is

    P(max of n draws > crown) = E_mu [ 1 - Phi((crown - mu)/sigma)^n ]

which is what this script integrates.  For small n the two agree closely; for
large n they diverge sharply, because no amount of extra draws helps if our
true mean is low.  That divergence is the whole point: it tells us when extra
volume stops paying and only a real code gain will do.

Inputs, all measured, none inferred
-----------------------------------
sigma  = 0.6590% relative, 56 df -- pooled from four independent replay-like
         solvers on the public board whose class means agree to four decimals
         (a-github-name 2.57783 n=39, MyatKaung 2.57789 n=10,
          fyrsta7 2.57870 n=7, newjordan 2.57792 n=4).
x_bar  = 2.58643891, n=3 -- maple HEAD executable class
         (c1c0ba2 2.56974411, 2771067 2.59380735, 8858427 2.59576527).
crown  = 2.61650354381456, receipt cc6ddc1, solver a-github-name, STATIC since
         2026-08-08 09:09Z with 76+ subsequent draws from 10 solvers failing to
         beat it and the holder absent since 2026-08-08 17:52Z.
"""

from __future__ import annotations

import math

CROWN = 2.61650354381456
XBAR = 2.58643891
NOURS = 3
SIGMA_REL = 0.006590     # pooled, 56 df
FIELD_BASE_MEAN = 2.57783  # field's converged base-tree class mean


def norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def p_draw(mu: float, sigma_rel: float = SIGMA_REL) -> float:
    """P(one draw from a class with mean mu exceeds the crown)."""
    s = sigma_rel * mu
    return 1.0 - norm_cdf((CROWN - mu) / s)


def p_max_marginal(n: int, xbar: float = XBAR, nours: int = NOURS,
                   sigma_rel: float = SIGMA_REL, steps: int = 4001) -> float:
    """E_mu[1 - (1-p(mu))^n] with mu ~ N(xbar, (sigma/sqrt(nours))^2)."""
    se = sigma_rel * xbar / math.sqrt(nours)
    lo, hi = xbar - 6 * se, xbar + 6 * se
    h = (hi - lo) / (steps - 1)
    tot = 0.0
    wsum = 0.0
    for i in range(steps):
        mu = lo + i * h
        w = math.exp(-0.5 * ((mu - xbar) / se) ** 2)
        # Simpson-ish: trapezoid is plenty at 4001 points
        if i in (0, steps - 1):
            w *= 0.5
        tot += w * (1.0 - (1.0 - p_draw(mu, sigma_rel)) ** n)
        wsum += w
    return tot / wsum


def main() -> None:
    se = SIGMA_REL * XBAR / math.sqrt(NOURS)
    print("inputs")
    print(f"  crown                 {CROWN:.8f}")
    print(f"  our class mean        {XBAR:.8f}   (n={NOURS})")
    print(f"  gap                   {(CROWN-XBAR)/XBAR*100:.4f}%")
    print(f"  pooled per-draw sd    {SIGMA_REL*100:.4f}%  (56 df, 4 solvers, 60 draws)")
    print(f"  se of OUR class mean  {se/XBAR*100:.4f}%  <-- now the dominant unknown")
    print(f"  field base-class mean {FIELD_BASE_MEAN:.5f}  "
          f"(we are {(XBAR-FIELD_BASE_MEAN)/FIELD_BASE_MEAN*100:+.3f}% vs it)")

    print("\n== P(take the crown), naive vs correct ==")
    print("   n   naive 1-(1-p_pred)^n   CORRECT E_mu[...]   delta")
    s_pred = SIGMA_REL * math.sqrt(1 + 1.0 / NOURS)
    p_pred = 1 - norm_cdf((CROWN - XBAR) / (s_pred * XBAR))
    for n in (5, 10, 15, 20, 25, 30, 40, 60, 100):
        naive = 1 - (1 - p_pred) ** n
        corr = p_max_marginal(n)
        print(f"  {n:4d}      {naive*100:6.1f}%            {corr*100:6.1f}%       "
              f"{(corr-naive)*100:+6.1f} pp")

    print("\n  (naive per-draw predictive p = "
          f"{p_pred*100:.2f}%; the two agree at small n and diverge at large n,")
    print("   because extra draws cannot rescue a low true mean.)")

    print("\n== marginal value of the NEXT draw, at each point in the run ==")
    prev = 0.0
    for n in range(1, 41):
        cur = p_max_marginal(n)
        if n in (1, 2, 3, 5, 10, 15, 20, 25, 30, 35, 40):
            print(f"  draw {n:3d}:  cumulative {cur*100:5.1f}%   "
                  f"marginal +{(cur-prev)*100:4.2f} pp")
        prev = cur

    print("\n== what a LOCALLY-VERIFIED code gain buys (correct marginalization) ==")
    print("   gain    P@10    P@20    P@30    P@40")
    for g in (0.0, 0.0025, 0.005, 0.0075, 0.010):
        mu = XBAR * (1 + g)
        row = "  ".join(f"{p_max_marginal(k, xbar=mu)*100:5.1f}%"
                        for k in (10, 20, 30, 40))
        print(f"  {g*100:+5.2f}%  {row}")

    print("\n== downside check: what if our +0.33% edge over the field is n=3 luck? ==")
    print("   i.e. suppose our true mean is the field base mean 2.57783")
    for n in (10, 20, 30, 40):
        p = p_draw(FIELD_BASE_MEAN)
        print(f"   n={n:3d}: p/draw={p*100:.2f}%  P={100*(1-(1-p)**n):5.1f}%")
    print("   -> even in that pessimistic world volume still works, it just needs")
    print("      ~2x the draws.  This is the case a-github-name actually won from:")
    print("      39 draws at 1.14%/draw = 36% -- they were somewhat lucky.")


if __name__ == "__main__":
    main()
