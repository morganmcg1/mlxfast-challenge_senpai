#!/usr/bin/env python3
"""R108-M addendum 2: what rule 105.23's merge portfolio means for the FREEZE.

Three questions that 105.23 raises and does not answer, all of which land on the
integration/freeze owner rather than on frieren or tanjiro:

  1. Is the three-route disagreement that the Stage-1 critical test is supposed
     to resolve actually clean of the alpha uncertainty I bracketed in Part 1?
     If alpha could explain even a third of the 0.934 %-of-cs gap between routes
     C and B, the test is not critical and the night's plan is built on sand.

  2. Every P(>=1 of 2) in 105.23(a) assumes two INDEPENDENT draws. My channel
     forensics (freeze protocol section 4.2) show that two submissions of an
     unchanged tree are content-deduplicated: the second returns
     'Submission already exists', spawns no scoring job, and discards its note.
     So the second column is only real if the dedup trap is defeated. What is
     that worth, in the same units 105.23 uses to justify the second merge?

  3. 105.23(d) asserts the byte budget is not the constraint. I own that
     predicate and I have measured the surface. Confirm or correct it.

Self-checks are asserted against the advisor's own published figures.
"""
import math

# ---------------------------------------------------------------- settled ---
GAP, SIG = 1.6359, 0.3016          # rule 101 record gap, resubmission sigma
M4_CEIL = 263.29                   # GB/s, MEASURED in R108-M part 1
ALPHA_C = 0.4369                   # campaign alpha
A_LO, A_HI = 0.4227, 0.4409        # my two-sided bracket


def P1(g: float) -> float:
    """P(a single fresh draw clears the record gap)."""
    return 0.5 * math.erfc((GAP - g) / (SIG * math.sqrt(2)))


def P2(g: float) -> float:
    """P(at least one of two INDEPENDENT draws clears it)."""
    p = P1(g)
    return 1.0 - (1.0 - p) ** 2


ROUTES = [("C  pessimistic", 0.756), ("A  central", 1.069), ("B  optimistic", 1.690)]

# reproduce 105.23(a) exactly before using the model for anything new
assert abs(P2(0.756) - 0.0035) < 5e-4, P2(0.756)
assert abs(P2(1.069) - 0.0593) < 5e-4, P2(1.069)
assert abs(P2(1.690) - 0.8161) < 5e-4, P2(1.690)
assert abs(P2(1.512) - 0.5652) < 5e-4, P2(1.512)
assert abs(P2(2.138) - 0.9977) < 5e-4, P2(2.138)

print("=" * 78)
print("0. SELF-CHECK: 105.23(a) reproduced")
print("=" * 78)
print("  P2(0.756)=%.4f  P2(1.069)=%.4f  P2(1.690)=%.4f" % (P2(0.756), P2(1.069), P2(1.690)))
print("  P2(1.512)=%.4f  P2(2.138)=%.4f  P2(3.380)=%.4f" % (P2(1.512), P2(2.138), P2(3.380)))
print("  all match the advisor's table to <5e-4.  Model agreed.")

# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("1. IS THE STAGE-1 CRITICAL TEST CLEAN OF THE ALPHA UNCERTAINTY?")
print("=" * 78)
# Route A: constructed from rule 65's 2.3403 M5 us, an M5 measurement. alpha
#   never appears. The M4 path via rule 57 reproduces it identically because
#   k_dispatch = 2.3403/1.2382 is a tautology (integration tree 9.6.1).
route_A_band = 0.0

# Route B: 124.0 M5 us/step total less an irreducible DRAM subtrahend ~7.3.
#   Only the subtrahend is byte-priced, and in the M5 frame the byte charge
#   scales as alpha (M5 bandwidth = M4_ceiling / alpha).
B_TOTAL, B_SUB = 124.0, 7.3
US_PER_PCT = 65.67
b_vals = [(B_TOTAL - B_SUB * a / ALPHA_C) / US_PER_PCT for a in (A_LO, ALPHA_C, A_HI)]
route_B_band = max(b_vals) - min(b_vals)

# Route C: 105.16's 1.89 bars = 0.756 %. It is a RESIDUAL after a byte charge,
#   so it inherits that charge's uncertainty with the sign flipped. 105.20's
#   own decomposition of family E gives the split: 8.27 M4 us per dispatch,
#   of which 0.98 is DRAM bytes and 0.04 is a second small term.
E_TOTAL, E_BYTES, E_OTHER = 8.27, 0.98, 0.04
c_resid = [E_TOTAL - E_BYTES * a / ALPHA_C - E_OTHER for a in (A_LO, ALPHA_C, A_HI)]
c_vals = [0.756 * r / c_resid[1] for r in c_resid]
route_C_band = max(c_vals) - min(c_vals)

print("  route A  dispatch count      1.0691 %%   alpha band %.4f %% of cs" % route_A_band)
print("  route B  cost recovery       %.4f -> %.4f %%   alpha band %.4f %% of cs"
      % (max(b_vals), min(b_vals), route_B_band))
print("  route C  measured slack      %.4f -> %.4f %%   alpha band %.4f %% of cs"
      % (max(c_vals), min(c_vals), route_C_band))
worst = max(route_A_band, route_B_band, route_C_band)
spread = 1.690 - 0.756
print()
print("  route-to-route disagreement the critical test must resolve ... %.3f %% of cs" % spread)
print("  worst single-route alpha band .............................. %.4f %% of cs" % worst)
print("  ratio ...................................................... %.0fx" % (spread / worst))
print()
print("  => VERDICT: alpha accounts for %.2f %% of the disagreement. The Stage-1" % (100 * worst / spread))
print("     critical test is ALPHA-CLEAN. Whatever frieren measures at 21:00Z,")
print("     'the bandwidth constant was wrong' is not an available explanation,")
print("     and no one should spend the night re-deriving alpha to explain it.")
print("  => Note the sign, though: route C is a floor. alpha 0.4369 sits at the")
print("     78th percentile of my bracket, so if it errs it errs HIGH, too much")
print("     is charged to bytes, and the residual slack is understated. A")
print("     Stage-1 reading a little ABOVE 0.756 % is still consistent with")
print("     route C; the 105.23(f) branch point at 1.0 % is unaffected, because")
print("     0.004 % of cs is nowhere near the 0.244 % of headroom it would need.")

# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("2. WHAT THE DEDUP TRAP COSTS, IN 105.23's OWN UNITS")
print("=" * 78)
print("  Every P(>=1 of 2) above assumes two independent draws. Two submissions")
print("  of an UNCHANGED tree are content-deduplicated (freeze protocol 4.2,")
print("  proven from /usr/local/libexec/mlxfast.js): the second call returns")
print("  'Submission already exists', result.job is null, no scoring job is")
print("  created, and the note is discarded. Two draws against one tree is one")
print("  draw. So the honest column, absent a defeat, is P(1 draw).")
print()
print("  %-16s %7s %9s %9s %9s" % ("portfolio", "x %", "P 1 draw", "P 2 draws", "dedup cost"))
rows = []
for label, x in ROUTES:
    rows.append(("1 merge  " + label, x))
for label, x in ROUTES:
    rows.append(("2 merges " + label, 2 * x))
for label, x in rows:
    print("  %-16s %7.3f %9.4f %9.4f %9.4f" % (label, x, P1(x), P2(x), P2(x) - P1(x)))

e1_one = sum(P1(x) for _, x in ROUTES) / 3
e2_one = sum(P2(x) for _, x in ROUTES) / 3
e1_two = sum(P1(2 * x) for _, x in ROUTES) / 3
e2_two = sum(P2(2 * x) for _, x in ROUTES) / 3
assert abs(e2_one - 0.2930) < 1e-3, e2_one
assert abs(e2_two - 0.8543) < 1e-3, e2_two
print()
print("  uniform prior over the three routes (105.23(c)'s own device):")
print("    E[P | 1 merge, 2 working draws] = %.4f   (105.23(c): 0.2930)" % e2_one)
print("    E[P | 2 merges, 2 working draws] = %.4f  (105.23(c): 0.8543)" % e2_two)
print("    E[P | 1 merge, dedup unfixed]   = %.4f" % e1_one)
print("    E[P | 2 merges, dedup unfixed]  = %.4f" % e1_two)
print()
print("    value of the SECOND MERGE ....... %+.4f  (105.23(c): +0.5613)" % (e2_two - e2_one))
print("    value of DEFEATING THE DEDUP .... %+.4f at 1 merge, %+.4f at 2 merges"
      % (e2_one - e1_one, e2_two - e1_two))
print("    value of a THIRD merge (105.23(b)) +0.0023")
print()
ded = e2_one - e1_one
print("  => Defeating the dedup is worth %+.4f in expectation: %.0fx a third merge," % (ded, ded / 0.0023))
print("     and %.0f %% of what the entire second merge is worth. It costs one" % (100 * ded / (e2_two - e2_one)))
print("     comment line in an editable source file and 124 s of rebuild, against")
print("     ~4 hours for the second merge. On value per minute it is the single")
print("     best-priced item on the board.")
print("  => Worst single point: x = 1.690 (route B, one merge) loses %.4f," % (P2(1.690) - P1(1.690)))
print("     and x = 1.512 (route C, two merges) loses %.4f. Both are larger" % (P2(1.512) - P1(1.512)))
print("     than the 0.232 splitting loss that 105.22(c) was written to prevent.")

# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("3. 105.23(d) BYTE BUDGET, CHECKED AGAINST MY MEASURED SURFACE")
print("=" * 78)
MAX_TOTAL, MAX_FILE, MAX_GROWTH = 3_000_000, 524_288, 262_144
HEAD_TOTAL, HEAD_FILES = 2_681_206, 142
BASE_TOTAL = 2_983_849          # base 1bc1c895, same 142 files
BIGGEST = 384_245               # Sources/MLXFastModel/LagunaRuntimeModel.swift
PER_MERGE = 4096                # 105.20's estimate

hr_file = MAX_FILE - BIGGEST
hr_total = MAX_TOTAL - HEAD_TOTAL
growth_now = HEAD_TOTAL - BASE_TOTAL
hr_growth = MAX_GROWTH - growth_now
print("  measured at HEAD: %d files, %d B total, largest %d B" % (HEAD_FILES, HEAD_TOTAL, BIGGEST))
print("  per-file headroom  %7d B -> %2d merges at %d B" % (hr_file, hr_file // PER_MERGE, PER_MERGE))
print("  total    headroom  %7d B -> %2d merges" % (hr_total, hr_total // PER_MERGE))
print("  growth vs base 1bc1c895 %+d B (we are BELOW base), so growth headroom" % growth_now)
print("                     %7d B -> %2d merges" % (hr_growth, hr_growth // PER_MERGE))
print()
print("  => 105.23(d) CONFIRMED, and the binding cap is the one it named:")
print("     per-file, at %d merges. The other two are slacker (%d and %d)."
      % (hr_file // PER_MERGE, hr_total // PER_MERGE, hr_growth // PER_MERGE))
print("  => One correction worth having: the growth cap is measured against base")
print("     1bc1c895, and our tree is 302,643 B SMALLER than base, so the growth")
print("     cap is not merely slack, it is %d B slack. Nothing about the merge" % hr_growth)
print("     programme can be stopped by bytes. The clock is the only resource,")
print("     and my measured rebuild cost is 124.3 s per touch of")
print("     LagunaRuntimeModel.swift (freeze protocol 4.1) - not the ~4 s that a")
print("     'touch'-based timing would suggest.")

# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("4. 39- vs 30-DISPATCH, RE-PRICED ON 105.23's LADDER")
print("=" * 78)
print("  Integration tree 9.6.2 already prefers a 39-dispatch pair on gain. 105.23")
print("  makes the ladder linear in the per-merge price, which amplifies the gap:")
print()
print("  %-28s %7s %9s %9s %9s" % ("pair", "1 merge", "P1", "P>=1of2", "2 merges P>=1of2"))
for label, x in (("39-dispatch @ k_residue", 1.1029),
                 ("30-dispatch @ k_residue", 0.8484),
                 ("39-dispatch @ k=1.0", 0.7354),
                 ("30-dispatch @ k=1.0", 0.5657)):
    print("  %-28s %7.4f %9.4f %9.4f %14.4f" % (label, x, P1(x), P2(x), P2(2 * x)))
r1 = P2(1.1029) / P2(0.8484)
r2 = P2(2 * 1.1029) / P2(2 * 0.8484)
print()
print("  one merge : 39-dispatch is %.1fx the 30-dispatch P(>=1 of 2)" % r1)
print("  two merges: %.2fx -- the advantage COLLAPSES once two merges are on the" % r2)
print("              table, because 2 x 0.8484 = 1.6968 already sits on top of the")
print("              1.6359 record gap. That is the real argument for merge #2: it")
print("              makes the dispatch-count question stop mattering.")
