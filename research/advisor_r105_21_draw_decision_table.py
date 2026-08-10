#!/usr/bin/env python3
"""Rule 105.21 -- the draw decision table.

Given the campaign's settled record gap and resubmission sigma, compute the
probability that a single official draw beats the standing record as a function
of the certified local improvement we carry into it, and the probability that
at least one of N draws does.

Constants (rule 101, round 107):
  g0    = 1.6359 %   unbiased log-gap from our tree to the standing record
  sigma = 0.3016 %   sd(ln score) of a resubmission of a FIXED tree
  z0    = g0 / sigma = 5.42   (reproduced below as a check)

The draw channel is i.i.d. white noise (n = 1220, rule 101), so N draws are
independent Bernoulli trials with the same p.
"""

from math import erf, sqrt

G0 = 1.6359      # % of cs
SIGMA = 0.3016   # % of cs


def phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def p_beat(x: float) -> float:
    """P(one draw beats the record) carrying a certified +x % improvement."""
    return phi(-(G0 - x) / SIGMA)


ROWS = [
    ("nothing (today's tree)", 0.0),
    ("the 0.4 % draw bar alone", 0.4),
    ("family-E merge, route C (measured slack)", 0.756),
    ("family-E merge, route A (dispatch count)", 1.069),
    ("route A + a second 0.4 % lever", 1.469),
    ("family-E merge, route B low", 1.69),
    ("family-E merge, route B high", 1.78),
    ("full T2b recovery (no residual at all)", 1.888),
    ("frieren 11.4 one-merge low", 2.19),
    ("frieren 11.4 one-merge high", 2.31),
    ("family E full fusion (105.17)", 2.451),
]

if __name__ == "__main__":
    print(f"check: z0 = g0/sigma = {G0 / SIGMA:.2f}  (campaign value 5.42)")
    print()
    hdr = f"{'certified local gain':<42} {'x %':>6} {'z':>7} {'P(1 draw)':>11} {'P(2 draws)':>11}"
    print(hdr)
    print("-" * len(hdr))
    for label, x in ROWS:
        p1 = p_beat(x)
        p2 = 1.0 - (1.0 - p1) ** 2
        z = (G0 - x) / SIGMA
        print(f"{label:<42} {x:6.3f} {z:7.3f} {p1:11.2e} {p2:11.2e}")
    print()
    # The break-even: what certified gain makes one draw a coin flip?
    print(f"coin-flip gain (P=0.50) = {G0:.4f} %")
    for target in (0.10, 0.25, 0.50, 0.80):
        # invert: x = g0 - sigma * z where phi(-z) = target
        lo, hi = -6.0, 6.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if phi(-mid) < target:
                hi = mid
            else:
                lo = mid
        z = 0.5 * (lo + hi)
        print(f"  P(1 draw) = {target:.2f} needs a certified +{G0 - SIGMA * z:.3f} %")
