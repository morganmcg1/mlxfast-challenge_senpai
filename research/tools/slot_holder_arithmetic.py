#!/usr/bin/env python3
"""Re-verify every number that goes into the slot-holder decision brief.

Inputs are all quoted from research/maple_endgame_handoff_manifest.md with the
section that owns them; this script exists so no figure enters the brief by
transcription (manifest rule 8: verify inputs, not conclusions).
"""
import math

BAR = 2.6195531094824          # 1, leaderboard bar
BEST_DRAW = 2.60664970         # 4b, best-ever draw on the shared account (e27f1ce)
OUR_PROGRAM = 2.582263         # 6.5b, program-normalized mean behind BEST_DRAW (fern)
BAR_PROGRAM = 2.576540         # 6.5b, program-normalized mean behind BAR (fern)
DRAW_MEDIAN = 1.001830         # 6.5b, median draw factor over 1280 official rows
DRAW_SD = 0.00538              # 6.5b, sd of the draw component over the same rows
WITHIN_SD = (0.001860, 0.002276)  # 6.5b/§5, my within-program replicate sd band


def pct(x):
    return f"{x * 100:+.4f} %"


print("A. gap to bar, from the best draw we hold")
print("   ", pct(BAR / BEST_DRAW - 1), "(manifest 4b: +0.4950 %)")

print("B. the bar is itself a draw")
print("    bar draw factor        ", f"{BAR / BAR_PROGRAM:.6f}", "(6.5b: x1.016694, p99.3)")
print("    our best draw factor   ", f"{BEST_DRAW / OUR_PROGRAM:.6f}", "(6.5b: 1.009444, ~p96)")

print("C. program-vs-program, which is the headline")
print("    ours / bar-setter's    ", f"{OUR_PROGRAM / BAR_PROGRAM:.6f}",
      "=", pct(OUR_PROGRAM / BAR_PROGRAM - 1), "-> our code is AHEAD")

print("D. what one more draw of our own program must deliver")
need = BAR / OUR_PROGRAM
print("    multiplier needed      ", f"{need:.6f}", "(6.5b: 1.014441)")
z = (need - DRAW_MEDIAN) / DRAW_SD
p_norm = 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
print("    z (between-program sd) ", f"{z:.3f}", "-> normal p =", f"{p_norm*100:.2f} %",
      "(6.5b: z=2.344, 0.95 % normal / 1.48 % empirical)")
for name, sd in (("within-program low", WITHIN_SD[0]), ("within-program high", WITHIN_SD[1])):
    zz = (need - 1.0) / sd
    pp = 1.0 - 0.5 * (1.0 + math.erf(zz / math.sqrt(2.0)))
    print(f"    z ({name:<19}) {zz:.3f} -> normal p = {pp*100:.2f} %")

print("E. same question for re-firing the bar-setter's program instead")
need_bar = BAR / BAR_PROGRAM
z_bar = (need_bar - DRAW_MEDIAN) / DRAW_SD
p_bar = 1.0 - 0.5 * (1.0 + math.erf(z_bar / math.sqrt(2.0)))
print("    multiplier needed      ", f"{need_bar:.6f}", " z =", f"{z_bar:.3f}",
      "-> normal p =", f"{p_bar*100:.2f} %")
print("    ratio of odds ours/theirs:", f"{p_norm/p_bar:.1f}x")

print("F. cumulative odds over N draws at the empirical rate 1.48 % and normal 0.95 %")
for n in (1, 2, 3):
    print(f"    N={n}: empirical {100*(1-(1-0.0148)**n):.2f} %   normal {100*(1-(1-0.0095)**n):.2f} %")

print("G. delta sizes that change the answer (priced on our program, between-program sd)")
for d in (0.0026, 0.0050, 0.0100):
    z2 = (need / (1 + d) - DRAW_MEDIAN) / DRAW_SD
    p2 = 1.0 - 0.5 * (1.0 + math.erf(z2 / math.sqrt(2.0)))
    print(f"    delta {d*100:+.2f} % -> z {z2:+.3f} -> p {p2*100:5.2f} %")
