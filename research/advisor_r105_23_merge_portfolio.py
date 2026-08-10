#!/usr/bin/env python3
"""Rule 105.23 -- the merge portfolio: a SECOND dispatch merge is worth more
than resolving the price of the first.

Rule 105.20 priced the family-E merge (gate_sp folded into the lane-major QKV
kernel) by three mutually inconsistent routes:

    route C  0.756 %   105.16's measured non-byte slack for family E
    route A  1.069 %   30 dispatches x rule 65's 2.3403 M5 us
    route B  1.690 %   family-cost recovery, T2b = 124.0 M5 us/step

Rule 105.21/105.22 converted a certified gain into P(beat the record).  This
file asks the portfolio question: given that the merge is a TEMPLATE and not a
one-off, how does the outcome distribution move when a second (or third)
adjacent-pair merge lands, versus when we merely learn which price route is
right?

Dispatch counts per family (rule 105.17): D 39, B 39, A 30, C 30, E 30, out of
319 per step.  Rule 65's added-dispatch cost 2.3403 M5 us/step is ALREADY M5.
Campaign price: 0.015228 % of cs per M5 us/step.
"""

from math import erf, sqrt

G0 = 1.6359
SIGMA = 0.3016

PRICE_PER_M5_US = 0.015228      # % of cs per M5 us/step
DISPATCH_M5_US = 2.3403         # rule 65, already M5

ROUTE = {"C": 0.756, "A": 1.069, "B": 1.690}


def phi(z: float) -> float:
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def p_beat(x: float) -> float:
    return phi(-(G0 - x) / SIGMA)


def p2(x: float) -> float:
    return 1.0 - (1.0 - p_beat(x)) ** 2


def dispatch_value(n: int) -> float:
    """% of cs from removing n per-layer dispatches at rule 65's M5 cost."""
    return n * DISPATCH_M5_US * PRICE_PER_M5_US


def main() -> None:
    # self-checks against the settled record
    assert abs(dispatch_value(39) - 1.390) < 0.002, dispatch_value(39)
    assert abs(dispatch_value(30) - ROUTE["A"]) < 0.002, dispatch_value(30)
    assert abs(p_beat(0.1966) - 9.1e-07) < 2e-08
    print("self-checks: 39 dispatches = %.4f %%, 30 dispatches = %.4f %%, "
          "p(0.1966) = %.1e" % (dispatch_value(39), dispatch_value(30),
                                p_beat(0.1966)))

    print()
    print("=" * 78)
    print("(a) one merge, priced three ways vs two merges priced the SAME way")
    print("=" * 78)
    print("%-8s %10s %10s %12s | %10s %10s %12s"
          % ("route", "1 merge", "p(1 draw)", "P(>=1 of 2)",
             "2 merges", "p(1 draw)", "P(>=1 of 2)"))
    for r in ("C", "A", "B"):
        x1 = ROUTE[r]
        x2 = 2.0 * x1
        print("%-8s %10.3f %10.4f %12.4f | %10.3f %10.4f %12.4f"
              % (r, x1, p_beat(x1), p2(x1), x2, p_beat(x2), p2(x2)))

    print()
    print("The comparison that decides tonight's allocation:")
    print("  two merges at the MOST PESSIMISTIC price (2 x 0.756 = %.3f %%)"
          % (2 * ROUTE["C"]))
    print("     -> P(>=1 of 2 draws) = %.4f" % p2(2 * ROUTE["C"]))
    print("  one merge at the CENTRAL price (1 x 1.069 = %.3f %%)"
          % ROUTE["A"])
    print("     -> P(>=1 of 2 draws) = %.4f" % p2(ROUTE["A"]))
    print("  ratio: %.1f x in favour of the second merge."
          % (p2(2 * ROUTE["C"]) / p2(ROUTE["A"])))

    print()
    print("=" * 78)
    print("(b) portfolio ladder -- merges by family, priced at route A")
    print("=" * 78)
    print("%-46s %9s %9s %12s" % ("portfolio", "x %", "p(1)", "P(>=1 of 2)"))
    ladder = [
        ("nothing", 0),
        ("E only (30 dispatches)", 30),
        ("E + A or C (30+30)", 60),
        ("E + D or B (30+39)", 69),
        ("E + A + C (30+30+30)", 90),
        ("E + D + B (30+39+39)", 108),
        ("all five families (30+30+30+39+39)", 168),
    ]
    for name, n in ladder:
        x = dispatch_value(n)
        print("%-46s %9.3f %9.4f %12.4f" % (name, x, p_beat(x), p2(x)))

    print()
    print("=" * 78)
    print("(c) what is each ADDITIONAL merge worth, in P(>=1 of 2)?")
    print("=" * 78)
    prev = 0.0
    print("%-24s %9s %12s %14s" % ("after k merges (route A)", "x %",
                                   "P(>=1 of 2)", "marginal"))
    for k in range(0, 4):
        x = k * ROUTE["A"]
        cur = p2(x)
        print("%-24s %9.3f %12.4f %14.4f" % (k, x, cur, cur - prev))
        prev = cur

    print()
    print("=" * 78)
    print("(d) value of RESOLVING the price route vs LANDING a second merge")
    print("=" * 78)
    print("Resolving the route does not change the tree; it only tells us which")
    print("row we were already on. Expected P over the three routes, one merge:")
    ev1 = sum(p2(ROUTE[r]) for r in ROUTE) / 3.0
    print("   E[P | one merge, route unknown, uniform] = %.4f" % ev1)
    print("   best case (route B)                      = %.4f" % p2(ROUTE["B"]))
    print("   worst case (route C)                     = %.4f" % p2(ROUTE["C"]))
    print("   spread the route ambiguity covers        = %.4f"
          % (p2(ROUTE["B"]) - p2(ROUTE["C"])))
    ev2 = sum(p2(2 * ROUTE[r]) for r in ROUTE) / 3.0
    print("Landing a second merge, route still unknown:")
    print("   E[P | two merges, route unknown]         = %.4f" % ev2)
    print("   gain from the second merge               = %+.4f" % (ev2 - ev1))
    print()
    print("A second merge raises the expectation under EVERY route. Resolving")
    print("the route raises nothing at all -- it only sharpens our forecast.")

    print()
    print("=" * 78)
    print("(e) resource check -- is a second merge affordable?")
    print("=" * 78)
    lrm_headroom = 524288 - 384245
    per_merge_bytes = 4096
    print("LagunaRuntimeModel.swift headroom to the per-file cap: %d B"
          % lrm_headroom)
    print("estimated cost of one merge (105.20): ~%d B" % per_merge_bytes)
    print("merges affordable on the byte axis: %d" % (lrm_headroom // per_merge_bytes))
    print("=> the byte budget is NOT the binding constraint; the clock is.")

    print()
    print("=" * 78)
    print("(f) THE CRITICAL TEST -- the two models disagree by ~5x on the")
    print("    programme total, and frieren's Stage-1 number decides between them")
    print("=" * 78)
    # rule 105.16 measured non-byte slack, in 0.4 %-of-cs "bars", by family
    bars = {"D": 0.71, "A": 0.45, "C": 0.03, "B": 0.0, "E": 1.89}
    total_bars = sum(bars.values())
    slack_ceiling = 0.4 * total_bars
    all_dispatches = 30 + 30 + 30 + 39 + 39
    dispatch_ceiling = dispatch_value(all_dispatches)
    print("105.16 measured non-byte slack, by family (bars of 0.4 % of cs):")
    for k in ("D", "A", "C", "B", "E"):
        print("    family %s : %5.2f bars = %6.3f %%" % (k, bars[k], 0.4 * bars[k]))
    print("    TOTAL    : %5.2f bars = %6.3f %%  <-- ceiling on the WHOLE"
          " merge programme" % (total_bars, slack_ceiling))
    print()
    print("105.17 dispatch accounting, same programme (%d per-layer dispatches):"
          % all_dispatches)
    print("    %d x 2.3403 M5 us x 0.015228 = %6.3f %%" %
          (all_dispatches, dispatch_ceiling))
    print()
    print("    the two models differ by %.2f x on the programme total"
          % (dispatch_ceiling / slack_ceiling))
    print()
    print("Outcome under each model, playing the programme to exhaustion:")
    print("    105.16 slack ceiling  x = %6.3f %%  p = %.4f  P(>=1 of 2) = %.4f"
          % (slack_ceiling, p_beat(slack_ceiling), p2(slack_ceiling)))
    print("    105.17 dispatch model x = %6.3f %%  p = %.4f  P(>=1 of 2) = %.4f"
          % (dispatch_ceiling, p_beat(dispatch_ceiling), p2(dispatch_ceiling)))
    print()
    print("Note that route B's price for ONE merge (%.3f %%) already exceeds the"
          % ROUTE["B"])
    print("105.16 ceiling for ALL FIVE families (%.3f %%). The models are not"
          % slack_ceiling)
    print("merely imprecise; at least one of them is wrong.")
    print()
    print("DECISION RULE. frieren's Stage-1 paired measurement of the family-E")
    print("merge is a critical test:")
    print("  * measures ~0.756 %% -> 105.16 stands, programme ceiling %.3f %%,"
          % slack_ceiling)
    print("    a second merge buys at most %+.3f %% and P tops out at %.3f;"
          % (slack_ceiling - ROUTE["C"], p2(slack_ceiling)))
    print("    STOP the merge programme and spend the night elsewhere.")
    print("  * measures >= 1.0 % -> 105.16's family-E slack figure is falsified,")
    print("    the dispatch accounting holds, and a second merge is worth")
    print("    %+.4f in P(>=1 of 2). START merge #2 the same hour."
          % (p2(2 * ROUTE["A"]) - p2(ROUTE["A"])))


if __name__ == "__main__":
    main()
