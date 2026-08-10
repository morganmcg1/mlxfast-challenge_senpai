#!/usr/bin/env python3
"""Rule 105.22 -- draw scheduling: where a marginal percent is worth most, how
much certification precision is worth, and whether to split the two draws.

Builds directly on rule 105.21's model (research/advisor_r105_21_draw_decision_table.py):
one official draw beats the standing record with probability

    p(x) = Phi( -(g0 - x) / sigma )

with g0 = 1.6359 % (rule 101 unbiased log-gap to the record) and
sigma = 0.3016 % (sd of ln score for a resubmission of a FIXED tree).

Four questions, all pure arithmetic on settled constants:

  (a) dP/dx  -- what is a marginal +0.1 % of certified gain worth, as a
      function of where we already stand?  This decides where the remaining
      student-hours go.

  (b) does the ESTIMATION uncertainty on x matter?  Our certified x is itself
      measured, with a CI.  The predictive probability integrates over that,
      which inflates the effective sigma to sqrt(sigma^2 + sd_x^2).  If the
      inflation is small, extra certification blocks are nearly worthless and
      the hours belong to search instead.

  (c) split or hold?  Two draws are available in the 07:00Z-09:00Z window and a
      rejected draw carries no penalty.  Is it better to spend one early on a
      weaker tree as insurance, or to hold both for the final tree?

  (d) the corrected reading of the 1.0 % arming threshold: with no penalty for
      rejection, is there ever a reason NOT to press the button?
"""

from math import erf, exp, pi, sqrt

G0 = 1.6359      # % of cs, rule 101
SIGMA = 0.3016   # % of cs, rule 101


def phi_cdf(z: float) -> float:
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def phi_pdf(z: float) -> float:
    return exp(-0.5 * z * z) / sqrt(2.0 * pi)


def p_beat(x: float, sigma: float = SIGMA) -> float:
    return phi_cdf(-(G0 - x) / sigma)


def dp_dx(x: float, sigma: float = SIGMA) -> float:
    """d p / d x, per 1 % of cs."""
    return phi_pdf((G0 - x) / sigma) / sigma


def dp2_dx(x: float, sigma: float = SIGMA) -> float:
    """d/dx of P(at least one of two draws)."""
    return 2.0 * (1.0 - p_beat(x, sigma)) * dp_dx(x, sigma)


def banner(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    # ---- self-check against rule 105.21 -------------------------------------
    assert abs(G0 / SIGMA - 5.42) < 0.005, G0 / SIGMA
    assert abs(p_beat(0.1966) - 9.1e-07) < 2e-08, p_beat(0.1966)
    print("self-check: g0/sigma = %.2f, p(0.1966 %%) = %.1e  [both match record]"
          % (G0 / SIGMA, p_beat(0.1966)))

    # ---- (a) marginal value of gain ----------------------------------------
    banner("(a) what a marginal +0.10 % of certified gain buys, by where we stand")
    print("%-10s %8s %10s %14s %14s" %
          ("x %", "p(1)", "P(>=1 of 2)", "d p /+0.10%", "d P2/+0.10%"))
    for x in (0.0, 0.400, 0.756, 1.000, 1.069, 1.250, 1.400, 1.500,
              1.636, 1.690, 1.780, 1.888, 2.190, 2.451):
        print("%-10.3f %8.4f %10.4f %14.4f %14.4f" %
              (x, p_beat(x), 1.0 - (1.0 - p_beat(x)) ** 2,
               0.1 * dp_dx(x), 0.1 * dp2_dx(x)))
    ratio = dp_dx(G0) / dp_dx(1.069)
    print()
    print("ratio of marginal value at the coin flip (x = g0 = %.4f) to the"
          % G0)
    print("arming threshold's route-A value (x = 1.069): %.2f x" % ratio)

    # ---- (b) does certification precision matter? --------------------------
    banner("(b) effective sigma once the ESTIMATION error on x is folded in")
    print("instrument                         CI95 half-width   sd_x    "
          "sigma_eff   inflation")
    for name, hw in (("nezuko paired --local-submit", 0.1178),
                     ("fern decode cell", 0.3235),
                     ("fern score-level ABBA", 0.2666)):
        sd_x = hw / 1.96
        seff = sqrt(SIGMA ** 2 + sd_x ** 2)
        print("%-34s %11.4f %8.4f %10.4f %9.1f %%"
              % (name, hw, sd_x, seff, 100.0 * (seff / SIGMA - 1.0)))
    print()
    print("cost of that inflation at the operating points, nezuko instrument:")
    sd_x = 0.1178 / 1.96
    seff = sqrt(SIGMA ** 2 + sd_x ** 2)
    for x in (1.069, 1.469, 1.690):
        a = 1.0 - (1.0 - p_beat(x)) ** 2
        b = 1.0 - (1.0 - p_beat(x, seff)) ** 2
        print("  x = %.3f : P(>=1 of 2) %.4f -> %.4f   (%+.4f)" % (x, a, b, b - a))
    print()
    print("doubling the blocks (10 -> 20) halves sd_x^2; the gain in P is:")
    sd_x2 = sd_x / sqrt(2.0)
    seff2 = sqrt(SIGMA ** 2 + sd_x2 ** 2)
    for x in (1.069, 1.469, 1.690):
        b = 1.0 - (1.0 - p_beat(x, seff)) ** 2
        c = 1.0 - (1.0 - p_beat(x, seff2)) ** 2
        print("  x = %.3f : %+.4f   (compare +0.10 %% of gain: %+.4f)"
              % (x, c - b, 0.1 * dp2_dx(x)))

    # ---- (c) split the two draws, or hold both? ----------------------------
    banner("(c) split the draws or hold both for the final tree?")
    print("scenario: tree stands at x1 at the early slot, reaches x2 by the late slot")
    print("%-16s %-16s %10s %10s %10s" %
          ("x1 (early)", "x2 (late)", "split", "hold both", "cost of split"))
    for x1, x2 in ((0.756, 1.069), (1.069, 1.690), (1.069, 1.469),
                   (1.469, 1.690), (1.690, 1.690)):
        p1, p2 = p_beat(x1), p_beat(x2)
        split = 1.0 - (1.0 - p1) * (1.0 - p2)
        hold = 1.0 - (1.0 - p2) ** 2
        print("%-16.3f %-16.3f %10.4f %10.4f %10.4f"
              % (x1, x2, split, hold, hold - split))
    print()
    print("break-even probability q that the LATE window is lost entirely")
    print("(above q, splitting wins; below q, holding both wins):")
    print("%-12s %-12s %10s" % ("x1", "x2", "q*"))
    for x1, x2 in ((0.756, 1.069), (1.069, 1.690), (1.069, 1.469), (1.469, 1.690)):
        p1, p2 = p_beat(x1), p_beat(x2)
        hold2 = 1.0 - (1.0 - p2) ** 2
        # split:  p1 + (1-p1)(1-q) p2      hold:  (1-q) * hold2
        # p1 + (1-p1)p2 - (1-p1)p2 q = hold2 - hold2 q
        num = hold2 - p1 - (1.0 - p1) * p2
        den = hold2 - (1.0 - p1) * p2
        q = num / den if den != 0 else float("nan")
        print("%-12.3f %-12.3f %10.3f" % (x1, x2, q))

    # ---- (d) is there ever a reason not to press the button? ---------------
    banner("(d) expected value of drawing at all, given no penalty for rejection")
    print("%-10s %12s %14s" % ("x %", "P(>=1 of 2)", "vs not drawing"))
    for x in (0.0, 0.400, 0.756, 0.900, 1.000, 1.069):
        p2 = 1.0 - (1.0 - p_beat(x)) ** 2
        print("%-10.3f %12.2e %14s" % (x, p2, "strictly better"))
    print()
    print("A draw is free at the margin. The 1.0 % threshold is therefore NOT a")
    print("veto on pressing the button -- it is the threshold above which paying")
    print("the 07:00Z integration-freeze cost (which ends all search) is worth it.")


if __name__ == "__main__":
    main()
