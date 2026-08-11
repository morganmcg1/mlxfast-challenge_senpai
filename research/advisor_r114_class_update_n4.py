#!/usr/bin/env python3
"""R114 -- fold the 4th HEAD-class replay (2aedeb8) into the crown EV model.

This is a pure update of research/advisor_r113_crown_ev_marginalized.py with
one more receipt.  Nothing about the model changed; only the class estimate did.

New receipt: 2aedeb8, 2026-08-11 00:39Z, rejected, score 2.60026627118063.
It is HEAD-executable-class by construction (comment-only nonce over the
advisor-branch editable surface), so it joins c1c0ba2 / 2771067 / 8858427.

Two things this script is careful about:

  1. It reports the class sd BUT DOES NOT USE IT.  n=4 gives 3 df; a 3-df sd
     is worthless as a scale estimate (its own relative se is ~41%).  The
     scale stays the pooled 56-df field sigma = 0.6590% from R113.  Using our
     own 3-df sd here would be the classic "estimate the noise from the same
     four points you are testing" error.
  2. Marginalizing over mu ~ N(xbar, sigma^2/n) still uses the POOLED sigma
     for the standard error, not the class sd, for the same reason.
"""

from __future__ import annotations

import math

CROWN = 2.61650354381456
SIGMA_REL = 0.006590          # pooled across 4 field replay solvers, 56 df
FIELD_BASE_MEAN = 2.57783     # field's converged base-tree class mean

CLASS_N3 = [2.56974410819947, 2.59380735131190, 2.59576526895414]
NEW = [("2aedeb8", 2.60026627118063)]
CLASS_N4 = CLASS_N3 + [v for _, v in NEW]


def norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def p_draw(mu: float, sigma_rel: float = SIGMA_REL) -> float:
    s = sigma_rel * mu
    return 1.0 - norm_cdf((CROWN - mu) / s)


def p_max_marginal(n: int, xbar: float, nours: int,
                   sigma_rel: float = SIGMA_REL, steps: int = 4001) -> float:
    """E_mu[1 - (1-p(mu))^n] with mu ~ N(xbar, (sigma/sqrt(nours))^2)."""
    se = sigma_rel * xbar / math.sqrt(nours)
    lo, hi = xbar - 6.0 * se, xbar + 6.0 * se
    h = (hi - lo) / (steps - 1)
    total = 0.0
    wnorm = 0.0
    for i in range(steps):
        mu = lo + i * h
        w = math.exp(-0.5 * ((mu - xbar) / se) ** 2)
        # Simpson weights
        sw = 1.0 if i in (0, steps - 1) else (4.0 if i % 2 else 2.0)
        w *= sw
        total += w * (1.0 - (1.0 - p_draw(mu, sigma_rel)) ** n)
        wnorm += w
    return total / wnorm


def mean_sd(xs):
    n = len(xs)
    m = sum(xs) / n
    if n < 2:
        return m, float("nan")
    v = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, math.sqrt(v)


def main() -> None:
    m3, s3 = mean_sd(CLASS_N3)
    m4, s4 = mean_sd(CLASS_N4)

    print("=" * 74)
    print("R114 -- maple HEAD executable class, n=3 -> n=4")
    print("=" * 74)
    print(f"  n=3 mean {m3:.8f}   class sd {s3:.6f} ({100*s3/m3:.4f}% rel, 2 df)")
    print(f"  n=4 mean {m4:.8f}   class sd {s4:.6f} ({100*s4/m4:.4f}% rel, 3 df)")
    print(f"  shift  {100*(m4-m3)/m3:+.4f}% of score from one draw")
    print()
    print(f"  pooled field sigma (56 df, USED)     {100*SIGMA_REL:.4f}%")
    print(f"  our own class sd  (3 df, NOT USED)   {100*s4/m4:.4f}%"
          f"   [own rel se ~{100/math.sqrt(2*3):.0f}%]")
    print()
    print(f"  class mean vs field base tree {FIELD_BASE_MEAN}:"
          f" {100*(m4-FIELD_BASE_MEAN)/FIELD_BASE_MEAN:+.4f}%")
    print(f"  se of class mean (pooled sigma / sqrt 4) ="
          f" {100*SIGMA_REL/math.sqrt(4):.4f}% rel")
    print(f"  gap to crown {CROWN}: {100*(CROWN-m4)/m4:+.4f}%"
          f"  = {(CROWN-m4)/(SIGMA_REL*m4):.3f} per-draw sigma")
    print()

    print("-" * 74)
    print("P(take the crown in n further draws), marginalized over unknown mu")
    print("-" * 74)
    ns = [1, 5, 10, 20, 30, 40]
    print(f"{'gain':>8} | " + " | ".join(f"n={n:<3}" for n in ns))
    for gain in (0.0, 0.0025, 0.0050, 0.0075, 0.0100):
        xb = m4 * (1.0 + gain)
        row = [f"{100*p_max_marginal(n, xb, 4):5.1f}%" for n in ns]
        print(f"{100*gain:+7.2f}% | " + " | ".join(f"{r:<5}" for r in row))
    print()

    print("-" * 74)
    print("Marginal value of the next draw at +0.00% gain (n=4 class)")
    print("-" * 74)
    prev = 0.0
    for n in range(1, 13):
        p = p_max_marginal(n, m4, 4)
        print(f"  draw {n:>2}: cumulative {100*p:5.2f}%   marginal {100*(p-prev):+5.2f} pp")
        prev = p
    print()

    print("-" * 74)
    print("What one draw is worth vs what code is worth (from the n=4 class)")
    print("-" * 74)
    base20 = p_max_marginal(20, m4, 4)
    for gain in (0.0025, 0.0050):
        g20 = p_max_marginal(20, m4 * (1 + gain), 4)
        print(f"  a verified {100*gain:+.2f}% code gain, over 20 draws:"
              f" {100*base20:.1f}% -> {100*g20:.1f}%  ({100*(g20-base20):+.1f} pp)")
    d20 = p_max_marginal(27, m4, 4) - base20
    print(f"  7 extra draws (20 -> 27), no code gain:"
          f" {100*d20:+.1f} pp")
    print()
    print("  DOWNSIDE CHECK: if our class mean is really the field base tree")
    print(f"  ({FIELD_BASE_MEAN}) and the +{100*(m4-FIELD_BASE_MEAN)/FIELD_BASE_MEAN:.2f}%"
          " is luck:")
    for n in (20, 40):
        print(f"    P@{n} = {100*p_max_marginal(n, FIELD_BASE_MEAN, 4):.1f}%")


if __name__ == "__main__":
    main()
