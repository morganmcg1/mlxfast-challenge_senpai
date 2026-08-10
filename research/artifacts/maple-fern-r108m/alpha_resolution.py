import math

c4      = 263.29   # MEASURED M4 Pro DRAM read ceiling, this host
c4_lo   = 262.37
c4_hi   = 263.49
c4_tanj = 257.87   # tanjiro-geometry instrument, on M4, this host
c5_tanj = 610.0    # the published M5 constant from the SAME instrument
cache4  = 1675.96  # measured cache-served ceiling

alpha_c = 0.4369   # campaign alpha
beta_c  = 0.5
routed_demand = 597.1   # tanjiro N-DEGENERATE
qkvo_demand   = 677.1
tanj_bound    = 0.4454

print("=" * 74)
print("1. THE FOUR PUBLISHED M4 DENOMINATORS vs MEASUREMENT (c4 = %.2f)" % c4)
print("=" * 74)
for name, v in [("theoretical 273.0 (r94 census)", 273.0),
                ("hardcoded 266.3 (rule 55, fern_r100:71)", 266.3),
                ("roofline 260.6 (fern ledger:940)", 260.6),
                ("tanjiro pool-diff 237.4", 237.4)]:
    print("  %-42s %7.1f  = %6.2f%% of measured" % (name, v, 100 * v / c4))
print("  -> rule 55's bytes/266.3 is %.2f%% OPTIMISTIC (too much bandwidth assumed)"
      % (100 * (266.3 / c4 - 1)))

print()
print("=" * 74)
print("2. ALPHA: two independent, opposite-signed constraints")
print("=" * 74)
a_lo = c4_tanj / c5_tanj
print("  LOWER  instrument-paired (tanjiro geometry both hosts):")
print("         alpha = %.2f / %.1f = %.5f" % (c4_tanj, c5_tanj, a_lo))
a_hi = c4 / routed_demand
print("  UPPER  routed pool cannot exceed the measured M4 DRAM ceiling:")
print("         alpha <= %.2f / %.1f = %.5f" % (c4, routed_demand, a_hi))
print("  => alpha in [%.4f, %.4f]   (width %+.2f%% / %+.2f%% about campaign %.4f)"
      % (a_lo, a_hi, 100 * (a_lo / alpha_c - 1), 100 * (a_hi / alpha_c - 1), alpha_c))
print("  campaign alpha = %.4f  ->  INSIDE the interval: %s"
      % (alpha_c, a_lo <= alpha_c <= a_hi))
print("  tanjiro's alpha-free bound alpha < %.4f -> my upper bound %.5f is TIGHTER by %.2f%%"
      % (tanj_bound, a_hi, 100 * (1 - a_hi / tanj_bound)))

print()
print("=" * 74)
print("3. WHY THE TWO POOLS DISAGREE  (implied M4 achieved BW at campaign alpha)")
print("=" * 74)
for name, d in [("routed", routed_demand), ("qkvo", qkvo_demand)]:
    imp = d * alpha_c
    print("  %-7s demands M5 %.1f -> implied M4 achieved %.2f GB/s = %.1f%% of c4"
          % (name, d, imp, 100 * imp / c4))
f = 1 - c4 / (qkvo_demand * alpha_c)
print("  qkvo EXCEEDS the measured M4 DRAM ceiling by %.2f%% -> physically impossible"
      % (100 * (qkvo_demand * alpha_c / c4 - 1)))
print("  => at least %.1f%% of the qkvo pool's counted bytes must be CACHE-SERVED," % (100 * f))
print("     not DRAM.  Measured cache-served ceiling here is %.0f GB/s (%.1fx c4)."
      % (cache4, cache4 / c4))
print("  routed sits at %.1f%% of c4 -> fully consistent, so ROUTED identifies alpha."
      % (100 * routed_demand * alpha_c / c4))

print()
print("=" * 74)
print("4. RE-PRICE the two live alpha-dependent numbers")
print("=" * 74)
print("  tanjiro byte-axis price 15.10 MiB/step per 0.4%% of cs:")
for lbl, a in [("alpha_lo", a_lo), ("campaign", alpha_c), ("alpha_hi", a_hi)]:
    print("     %-9s alpha=%.4f -> %6.2f MiB/step per 0.4%%  (%+.2f%%)"
          % (lbl, a, 15.10 * alpha_c / a, 100 * (alpha_c / a - 1)))
print("  frieren barrier-drain 0.799-0.915%% at k in [alpha, beta]:")
for lbl, a in [("alpha_lo", a_lo), ("campaign", alpha_c), ("alpha_hi", a_hi)]:
    print("     %-9s alpha=%.4f -> low end %.4f%%  (high end %.3f%% at beta=%.1f, unchanged)"
          % (lbl, a, 0.799 * a / alpha_c, 0.915, beta_c))

print()
print("=" * 74)
print("5. DOES ANY VERDICT MOVE?  (section 9 draw model, sigma0 = 0.3016, gap 1.6359)")
print("=" * 74)
gap, sig = 1.6359, 0.3016
def P(g):
    return 0.5 * math.erfc((gap - g) / (sig * math.sqrt(2)))
for lbl, g in [("R108-K k=1.0, 30 disp", 0.5657), ("R108-K k=1.0, 39 disp", 0.7354),
               ("family E dispatch-only", 1.069), ("family E full fusion", 2.451)]:
    lo, hi = g * a_lo / alpha_c, g * a_hi / alpha_c
    print("  %-24s %.4f%% -> alpha band [%.4f, %.4f]%%   P: %.3e -> [%.3e, %.3e]"
          % (lbl, g, lo, hi, P(g), P(lo), P(hi)))
print()
print("  NOTE: these are LATENCY-regime prices carried at k >= 1.0, NOT at alpha.")
print("  Alpha rescaling shown only to bound the worst case; the real k is unchanged.")
