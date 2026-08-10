#!/usr/bin/env python3
"""R108-M addendum: which of rule 105.20's three routes actually depend on alpha?

My Part 1 table rescaled all four live gains by the alpha bracket. That was a
deliberate worst case and it was labelled as such, but rules 105.21/105.22 have since
made those numbers decision-critical, so the worst case is no longer good enough --
a spuriously wide band on route A or B would misinform the arming decision.

This works out the true exposure route by route, and picks up an independent
corroboration of alpha that fell out of 105.20's own arithmetic.
"""
import math

# --- settled constants -------------------------------------------------------
M4_CEIL = 263.29        # GB/s, MEASURED this round (range [262.37, 263.49])
ALPHA_C = 0.4369        # campaign value
A_LO, A_HI = 0.4227, 0.4409   # my two-sided bracket
US_PER_PCT = 65.67      # M5 us/step per 1 % of composite score (rule 105)
DISPATCH_M5 = 2.3403    # rule 65: one added dispatch, already in M5 us
GAP, SIG = 1.6359, 0.3016

def P1(g):
    return 0.5 * math.erfc((GAP - g) / (SIG * math.sqrt(2)))

def P2(g):
    p = P1(g)
    return 1.0 - (1.0 - p) ** 2

print("=" * 78)
print("1. INDEPENDENT CORROBORATION OF ALPHA FROM RULE 105.20")
print("=" * 78)
# 105.20 route B derives, from tanjiro's byte price 15.10 MiB/step per 0.4 %:
#   0.5748 MiB per M5 us/step  =>  ~603 GB/s effective M5 bandwidth.
# alpha is the M4/M5 bandwidth ratio, so my measured M4 ceiling predicts it.
M5_FROM_105_20 = 603.0
print(f"  105.20's effective M5 bandwidth, from the byte price ... {M5_FROM_105_20:.1f} GB/s")
print(f"  my MEASURED M4 ceiling ......................... {M4_CEIL:.2f} GB/s")
implied_M5 = M4_CEIL / ALPHA_C
print(f"  M4_ceiling / alpha_campaign = implied M5 ....... {implied_M5:.2f} GB/s")
print(f"  disagreement .................................. {100*(implied_M5/M5_FROM_105_20 - 1):+.3f} %")
alpha_from_105_20 = M4_CEIL / M5_FROM_105_20
print(f"  alpha implied by 105.20's 603 GB/s ............ {alpha_from_105_20:.5f}")
print(f"  campaign alpha ................................ {ALPHA_C:.5f}")
print(f"  inside my bracket [{A_LO}, {A_HI}]? ........... "
      f"{'YES' if A_LO <= alpha_from_105_20 <= A_HI else 'NO'}")
print()
print("  => This is a THIRD, independent line of evidence for alpha, derived from a")
print("     byte price I did not use in the bracket. It is not a bound, it is a point")
print("     estimate, and it lands 0.06 % from the campaign value.")

print()
print("=" * 78)
print("2. TRUE ALPHA EXPOSURE, ROUTE BY ROUTE")
print("=" * 78)

# --- route A: pure dispatch count, constructed entirely in M5 units -----------
routeA = 30 * DISPATCH_M5 / US_PER_PCT
print(f"\n  ROUTE A -- dispatch count: 30 x {DISPATCH_M5} M5 us / {US_PER_PCT} = {routeA:.4f} %")
print("    alpha appears NOWHERE in this construction. Rule 65's 2.3403 is already an")
print("    M5 measurement; the M4 route via rule 57 (1.2382 us) x k_dispatch reproduces")
print("    it identically because k_dispatch = 2.3403/1.2382 is a tautology (9.6.1).")
print("    EXPOSURE: exactly zero. Report 1.069 % with no alpha band.")

# --- route B: M5-measured family cost minus a byte-priced floor ---------------
T2B = 124.0        # M5 us/step, measured
D0 = 7.3           # M5 us/step of irreducible gate-bank DRAM, priced at 603 GB/s
print(f"\n  ROUTE B -- family-cost recovery: {T2B} M5 us/step less ~{D0} of irreducible DRAM")
print("    Only the subtrahend is byte-priced, and it scales linearly with alpha:")
print("      D(alpha) = D0 * alpha/alpha_c   (since M5_bw = M4_ceiling/alpha)")
rb = []
for lbl, a in [("alpha_lo ", A_LO), ("campaign ", ALPHA_C), ("alpha_hi ", A_HI)]:
    D = D0 * a / ALPHA_C
    g = (T2B - D) / US_PER_PCT
    rb.append(g)
    print(f"      {lbl} alpha={a:.4f}  D={D:.3f} M5 us  ->  {g:.4f} %")
print(f"    TOTAL SPREAD ACROSS THE WHOLE ALPHA BRACKET: {max(rb)-min(rb):.4f} % of cs")
print("    EXPOSURE: negligible (< 0.005 %). The main term is measured in M5 units;")
print("    alpha only moves a 6 % subtrahend. Report 1.69-1.78 % with no alpha band.")

# --- route C: the one that IS exposed ----------------------------------------
print("\n  ROUTE C -- 105.16 measured slack, 1.89 bars = 0.756 %")
print("    This one IS alpha-exposed, and structurally so: 'non-byte slack' is a")
print("    RESIDUAL after subtracting a byte-priced term. A residual inherits the full")
print("    uncertainty of what was subtracted, with the sign flipped -- alpha too HIGH")
print("    means too much was charged to bytes and the non-byte slack is UNDERSTATED.")
print("    Since my bracket says 0.4369 errs high if it errs, route C is if anything")
print("    a floor. That is the same direction 105.20 already suspects (C collapses")
print("    into B), and it is one more reason not to headline 0.756 %.")

print()
print("=" * 78)
print("3. WHAT THIS DOES TO THE ARMING DECISION (105.21 / 105.22)")
print("=" * 78)
print(f"  {'route':<34}{'x %':>8}{'P(1 draw)':>12}{'P(>=1 of 2)':>14}  arming")
for lbl, g in [("A  dispatch count", routeA),
               ("B  family-cost recovery (low)", 1.690),
               ("B  family-cost recovery (high)", 1.780),
               ("C  measured slack", 0.756)]:
    arm = "FREEZE at 07:00Z" if g >= 1.25 else ("advisor's call" if g >= 1.0 else "no early freeze")
    print(f"  {lbl:<34}{g:>8.3f}{P1(g):>12.4f}{P2(g):>14.4f}  {arm}")
print()
print("  The alpha bracket moves none of these rows across a threshold, and for A and B")
print("  it does not move them at all. Alpha is settled as an input to the arming")
print("  decision; the decision now turns entirely on WHICH ROUTE IS TRUE, which is")
print("  frieren's Stage-1 measurement at 21:00Z and not a question about bandwidth.")
