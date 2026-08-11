#!/usr/bin/env python3
"""Re-read the standing bar from the diff field of terminal rows, 16:02Z 2026-08-11.

Finding (fern, #745 / manifest 6.7): the CLI `diff` column is *score - bar_at_adjudication*
in RAW score units, and the printed percent is a units bug (|diff| / 1.003405, i.e. the raw
gap read as a fraction of ~1.0034 instead of of the bar ~2.61).

That makes every terminal row a *timestamped bar reading*. Verify on two rows, then use the
newest one to answer the only question that matters in the last hour: has the bar moved?
"""

BAR_0934Z = 2.6195531094824  # set by ggu77wt at 09:34:06Z 2026-08-11
BEST_RECEIPT = 2.60664969895906  # e27f1ce, our best-ever official score

# (label, score, diff as printed, printed pct, fire time UTC)
ROWS = [
    ("e27f1ce", 2.60664969895906, -0.009854, 0.98, "08-10 08:18Z"),
    ("c06b1b6", 2.58896632157301, -0.030587, 3.05, "08-11 13:51Z"),
]

print("=" * 78)
print("BAR RE-READ FROM TERMINAL ROWS  (poll at 2026-08-11 16:02Z)")
print("=" * 78)
for label, score, diff, pct, t in ROWS:
    implied_bar = score - diff  # diff is negative when below the bar
    true_rel_gap = -diff / implied_bar * 100.0
    pct_reconstructed = -diff / 1.003405 * 100.0
    print(f"\n{label}  fired {t}")
    print(f"  official score        {score:.14f}")
    print(f"  diff printed          {diff:+.6f}")
    print(f"  implied bar           {implied_bar:.13f}")
    print(f"  CLI pct printed       {pct:.2f} %")
    print(f"  CLI pct reconstructed {pct_reconstructed:.2f} %   "
          f"(|diff|/1.003405 -> {'MATCHES' if abs(pct_reconstructed - pct) < 0.02 else 'MISMATCH'})")
    print(f"  TRUE relative gap     {true_rel_gap:.4f} %   (|diff|/bar)")

newest_bar = ROWS[-1][1] - ROWS[-1][3 - 2]  # score - diff
newest_bar = ROWS[-1][1] - ROWS[-1][2]
print("\n" + "-" * 78)
print("HAS THE BAR MOVED SINCE 09:34Z?")
print("-" * 78)
# `diff` is printed to 6 decimal places, so the implied bar is only resolved to
# +/- 5e-7. Anything smaller than that is rounding, not a bar move. Comparing at
# 1e-9 would report a phantom advance of +2.1e-7 -- exactly the false precision
# this campaign spent the day removing from other people's numbers.
RESOLUTION = 5e-7
delta = newest_bar - BAR_0934Z
print(f"  bar set by ggu77wt 09:34:06Z   {BAR_0934Z:.13f}")
print(f"  bar seen by c06b1b6 (adjudicated <=2 h 11 min ago)  {newest_bar:.13f}")
print(f"  difference                     {delta:+.13f}")
print(f"  print resolution of `diff`     +/-{RESOLUTION:.1e}  (6 dp)")
if abs(delta) < RESOLUTION:
    print("  VERDICT: UNCHANGED -- difference is inside the print resolution.")
    print("           The bar has not advanced in the ~6.5 h since 09:34Z.")
else:
    print(f"  VERDICT: MOVED by {delta:+.7f} (exceeds print resolution).")

req = (newest_bar / BEST_RECEIPT - 1.0) * 100.0
print(f"\n  margin our best receipt e27f1ce still needs:  +{req:.4f} %")

print("\n" + "-" * 78)
print("COUNTS THAT MOVE BECAUSE c06b1b6 IS NOW TERMINAL AND SCORED")
print("-" * 78)


import math


def rule_of_three(n):
    """Approximation: upper 95 % bound on p given 0/n."""
    return 3.0 / n * 100.0


def clopper_pearson_zero(n):
    """EXACT one-sided 95 % upper bound on p given 0 successes in n: 1 - 0.05**(1/n).

    fern quotes CP; the rule of three is the small-p approximation to it and runs
    ~1 % relative high. Print both so the brief and the source agree on which is
    which -- mixing the two is how 1.88 % turns into 1.89 % and looks like a
    bound that got WORSE after a clean observation.
    """
    return (1.0 - math.exp(math.log(0.05) / n)) * 100.0


print(f"  {'quantity':<52}{'n':>10}   {'rule of 3':>11}   {'exact CP':>9}")
for name, before_n, after_n in [
    ("our draws clearing today's bar (0 clears)", 106, 107),
    ("consecutive clean fires, no validity failure", 53, 54),
    ("current-era fires clearing by >= required margin (0)", 158, 159),
]:
    print(f"  {name:<52}{before_n:>10}   {rule_of_three(before_n):>10.2f} %   "
          f"{clopper_pearson_zero(before_n):>7.2f} %")
    print(f"  {'  -> after c06b1b6':<52}{after_n:>10}   {rule_of_three(after_n):>10.2f} %   "
          f"{clopper_pearson_zero(after_n):>7.2f} %")

print("\n  All three bounds tighten. None of them change a decision: the answer was")
print("  'very unlikely' before and is 'very unlikely' now. Reported so the numbers in")
print("  the brief match the log a reader can pull for themselves.")
print("=" * 78)
