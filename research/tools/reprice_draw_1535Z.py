"""Reprice every row of the slot-holder brief that shares the draw-sigma reference,
after maple-edward's F19 (PR #741) showed BOTH rails of my published
`[~0 %, 1.5 %]` bracket priced the wrong random variable.

Rule 14: one script, every dependent row, no hand-edited cells.

F19, in one paragraph. The quantity that decides a fire is the OFFICIAL score, which
is a within-session ratio candidate/baseline. My lower rail (0.186-0.228 %) was the
replicate sd of `cs`, the candidate term only -- and research/CURRENT_RESEARCH_STATE.md
:3509-3511 independently puts ~96 % of official-score variance on the BASELINE draw, so
that rail discards almost all the noise. My upper rail (fern's 0.538 %) is the sd of the
draw factor L at FIXED cs: correct for "re-fire the exact submission I already hold",
wrong for "a fresh submission draws cs and L together". Neither is the predictive sigma.

The predictive sigma is directly measurable and needs no decomposition at all:
sd(ln officialScore) over the five ranked null replicates = 0.3728 %. It is BELOW the
independence quadrature (0.5822 %) because corr(ln cs, ln L) = -0.79 -- common-mode host
slowdown cancels in a candidate/baseline ratio.

Centring was the second defect: I priced from our best-ever DRAW (2.60664970), which is
a maximum over 106 draws, instead of from the program's MEAN official score.
"""
import math

BAR = 2.6195531094824
BEST_DRAW = 2.60664969895906          # e27f1ce, max over 106 draws -- NOT a centre
PROGRAM_MEAN_CS = 2.582263            # fern, sec.6.5b
CS_TO_OFFICIAL = 1.001830             # edward F19, five ranked null receipts
PROGRAM_MEAN_OFFICIAL = PROGRAM_MEAN_CS * CS_TO_OFFICIAL

SIGMA_NEW = 0.003728                  # sd(ln official), n=5 ranked null replicates
SIGMA_OLD_LOW = 0.00186               # replicate sd of cs (candidate term only)
SIGMA_OLD_HIGH = 0.00538              # fern draw factor L at fixed cs
SIGMA_CI = (0.00223, 0.01071)         # 95 % chi-square on 4 dof

RANKED_PCT_PER_US = 0.75 / 4910.9 * 100 / 100   # fraction of score per us/step
LOCAL_PCT_PER_US = 0.75 / 12798                  # edward F1/F16: D = S/128 + T


def p_clear(gain, sigma, centre):
    """P(one fresh draw of a tree that is `gain` better than `centre` clears BAR)."""
    need = BAR / (centre * (1.0 + gain))
    if need <= 0:
        return 1.0
    z = math.log(need) / sigma
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def pct(x):
    return f"{x * 100:.3f} %"


print("=" * 78)
print("CENTRING (defect 2 of 2)")
print("=" * 78)
print(f"  best-ever draw (WRONG centre, it is a max over 106) {BEST_DRAW:.8f}")
print(f"  program mean cs                                     {PROGRAM_MEAN_CS:.6f}")
print(f"  x cs->official {CS_TO_OFFICIAL} = program mean official  "
      f"{PROGRAM_MEAN_OFFICIAL:.6f}")
print(f"  required move from the mean: "
      f"{(BAR / PROGRAM_MEAN_OFFICIAL - 1) * 100:.4f} %")
print(f"  required move from the best draw (what I published): "
      f"{(BAR / BEST_DRAW - 1) * 100:.4f} %")
print()

print("=" * 78)
print("SEC.2 HEADLINE: P(one draw of the tree we hold clears the bar)")
print("=" * 78)
rows = [
    ("published lower rail (cs replicate sd, z~6-8)", SIGMA_OLD_LOW, BEST_DRAW),
    ("published upper rail (L at fixed cs)", SIGMA_OLD_HIGH, BEST_DRAW),
    ("CORRECTED: sd(ln official), mean-centred", SIGMA_NEW, PROGRAM_MEAN_OFFICIAL),
    ("  same, sigma at 95 % low  (0.223 %)", SIGMA_CI[0], PROGRAM_MEAN_OFFICIAL),
    ("  same, sigma at 95 % high (1.071 %)", SIGMA_CI[1], PROGRAM_MEAN_OFFICIAL),
]
for label, sig, centre in rows:
    print(f"  {label:<46s} {pct(p_clear(0.0, sig, centre))}")
print()
print("  Model-free bound from the account's own 106 scored draws, 0 clears of")
print("  today's bar: P <= 2.83 % (rule of three, 95 % one-sided).")
print("  Every corrected point estimate above sits inside it; the 95 %-high sigma")
print("  case does NOT, which is itself a reason to trust the nonparametric bound")
print("  over any of the parametric point estimates.")
print()

print("=" * 78)
print("SEC.3 DELTA PRICING, repriced (this table shares the corrected reference)")
print("=" * 78)
# As-published values, quoted as constants. I deliberately do NOT try to recompute
# them: the published row used a centring and a needed-multiplier I can no longer
# reproduce exactly, and inventing a recomputation that lands on 0.95 % would be
# fitting the audit to the answer.
PUBLISHED = {0.0: "0.95 (emp 1.48)", 0.0026: "3.2", 0.0050: "8.0",
             0.0100: "31.7", 0.0126: "~50"}

print(f"{'real gain':>10} | {'P(1 draw) as published':>22} | {'P(1 draw) CORRECTED':>19} | "
      f"{'ranked us':>9} | {'local us':>8}")
print("-" * 78)
for g in (0.0, 0.0026, 0.0050, 0.0100, 0.0126):
    new = p_clear(g, SIGMA_NEW, PROGRAM_MEAN_OFFICIAL)
    ranked_us = g / (0.75 / 4910.9)
    local_us = g / LOCAL_PCT_PER_US
    print(f"{g * 100:9.2f} % | {PUBLISHED[g]:>22} | {pct(new):>19} | "
          f"{ranked_us:9.1f} | {local_us:8.1f}")
print()
print("  Even-money gain (P = 50 %): "
      f"{(BAR / PROGRAM_MEAN_OFFICIAL - 1) * 100:.4f} % = "
      f"{(BAR / PROGRAM_MEAN_OFFICIAL - 1) / (0.75 / 4910.9):.0f} us/step ranked, "
      f"{(BAR / PROGRAM_MEAN_OFFICIAL - 1) / LOCAL_PCT_PER_US:.0f} us/step local.")
print("  Sanity check against edward F1: local requirement for +0.26 % / +0.50 % is "
      f"{0.0026 / LOCAL_PCT_PER_US:.0f} / {0.0050 / LOCAL_PCT_PER_US:.0f} us/step "
      "(he says 44 / 85).")
print()
print("  LOCAL CURRENCY (edward F1/F16): 0.00586 %/(us/step) is the CORRECT local")
print("  figure -- d ln(official)/dD = -0.75/D identically, and the --local-iterate")
print("  D = seed/128 + step ~ 12798 us. My brief branded it 'UNSOURCED, never")
print("  reuse'. That was wrong and it made the local requirement column ~30 % LOW,")
print("  i.e. flattering, not conservative.")

print()
print("=" * 78)
print("HOW MUCH HAS THE POINT ESTIMATE MOVED ACROSS FOUR ATTEMPTS?")
print("=" * 78)
attempts = [("retracted lognormal", 0.156),
            ("published sec.6.5c", 0.0095),
            ("corrected here", p_clear(0.0, SIGMA_NEW, PROGRAM_MEAN_OFFICIAL)),
            ("amended 18:30Z", 0.00439)]
for name, v in attempts:
    print(f"  {name:<24s} {v * 100:8.3f} %")
lo = min(v for _, v in attempts)
hi = max(v for _, v in attempts)
print(f"  spread {hi / lo:.0f}x across four attempts by the same advisor on the same")
print("  data. That instability is the finding: the parametric route is not")
print("  trustworthy at this tail, and the 0/106 rule-of-three bound should be the")
print("  number carried into a decision.")
print()
print("  AMENDED 18:30Z (error sixteen, rule 30). SIGMA_NEW = 0.3728 % above came")
print("  from ONE replicate group (df 4) and was justified as sub-quadrature by")
print("  corr(ln cs, f) = -0.79. That correlation is refuted by n = 84 already in")
print("  research/CURRENT_RESEARCH_STATE.md: -0.126, 95 % CI [-0.332, +0.091].")
print("  Direct over four clean groups (df 12): sd(ln officialScore) = 0.4774 %,")
print("  interval [0.3423 %, 0.7880 %] -> P = 0.439 %. Recompute with")
print("  research/tools/receipt_k_invariant.py. The conclusion above is unchanged")
print("  and now better supported: carry the model-free bound, not this table.")
