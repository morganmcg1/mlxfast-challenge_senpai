#!/usr/bin/env python3
"""Rule 105.24 generator — repricing the dispatch-merge programme after the
discovery that MLX already encodes every compute pass with
MTL::DispatchTypeConcurrent and inserts a memoryBarrier only on a true RAW
hazard (device.cpp:325, :363-375, :545-548).

Deterministic, no I/O, no receipts. Prints the tables quoted in
research/advisor-rule-105-24-concurrency-repricing-and-integration-hazard-map.md
"""

import math

# ---------------------------------------------------------------- constants
P_PCT_PER_M5_US = 0.015228   # % of cs per M5 us/step (campaign constant, M5)
M4_GLUE_US = 1.2382          # #497 saturated per-dispatch addition price [M4]
K_DISPATCH = 1.890           # M4 -> M5 transfer for dispatch-like quantities
G0_PCT = 1.6359              # unbiased gap to the record, % of cs
SIGMA_PCT = 0.3016           # sd(ln cs) resubmission noise, % of cs
BAR_PCT = 0.4                # advisor draw bar
ARM_PCT = 1.0               # 105.22 effort-allocation threshold

# candidate k values and their provenance
K_GRID = [
    (0.0872, "#483 measured, 0.108 us/dispatch, CI [-0.221,+0.438] spans 0"),
    (0.2000, "tanjiro R108-L prior for the removal direction"),
    (0.3000, "advisor 'merge programme dead' threshold to frieren"),
    (0.5000, "beta, the latency transfer"),
    (0.8000, "advisor 'merge programme alive' threshold to frieren"),
    (1.0000, "105.17 conservative floor (no measurement supports it)"),
    (1.3950, "105.17 midpoint"),
    (1.8900, "rule 65 addition price applied in reverse (rule 68 forbids)"),
]

N_ONE_MERGE = 40    # family E: T2b gate_sp h64 (30) + T2b' gate_sp h48 (10)
N_TWO_MERGE = 79    # + routed || shared gate+up (39)
N_ALL_REMOVABLE = 158  # tanjiro R108-L 5.3 maximum independent removal


def phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def p_one_draw(x_pct):
    """P(a single resubmission of a tree carrying x% gain beats the record)."""
    return phi((x_pct - G0_PCT) / SIGMA_PCT)


def p_two_draws(x_pct):
    p = p_one_draw(x_pct)
    return 1.0 - (1.0 - p) ** 2


def gain_pct(n, k):
    """Score gain from removing n dispatches priced at k x the M4 glue."""
    return n * M4_GLUE_US * k * P_PCT_PER_M5_US


def slope_for_gain(n, target_pct):
    """M4 us/step per dispatch needed for n removals to be worth target_pct."""
    return target_pct / (n * K_DISPATCH * P_PCT_PER_M5_US)


def main():
    print("=" * 78)
    print("RULE 105.24 (a) - the merge programme repriced across the k axis")
    print("=" * 78)
    print(f"{'k':>7} {'us/disp[M4]':>12} {'n=40':>9} {'n=79':>9} {'n=158':>9} "
          f"{'P(2 draws|n=40)':>16}")
    for k, _ in K_GRID:
        g40 = gain_pct(N_ONE_MERGE, k)
        g79 = gain_pct(N_TWO_MERGE, k)
        g158 = gain_pct(N_ALL_REMOVABLE, k)
        print(f"{k:7.4f} {k*M4_GLUE_US:12.4f} {g40:8.4f}% {g79:8.4f}% "
              f"{g158:8.4f}% {p_two_draws(g40):16.4f}")

    print()
    print("provenance of each k:")
    for k, why in K_GRID:
        print(f"  k={k:7.4f}  {why}")

    print()
    print("=" * 78)
    print("RULE 105.24 (b) - what frieren's arm-F slope has to be")
    print("=" * 78)
    print("Delta%cs = n x s[M4 us/dispatch] x k_dispatch x P")
    print(f"        = n x s x {K_DISPATCH} x {P_PCT_PER_M5_US}")
    print()
    for n, label in ((N_ONE_MERGE, "one merge (family E, n=40)"),
                     (N_TWO_MERGE, "two merges (n=79)"),
                     (N_ALL_REMOVABLE, "every removable dispatch (n=158)")):
        s_bar = slope_for_gain(n, BAR_PCT)
        s_arm = slope_for_gain(n, ARM_PCT)
        s_g0 = slope_for_gain(n, G0_PCT)
        print(f"{label:38}  s(0.4%)={s_bar:6.4f}  s(1.0%)={s_arm:6.4f}  "
              f"s(g0={G0_PCT}%)={s_g0:6.4f}")
    print()
    print("cross-check: the thresholds sent to frieren (<=0.3 dead, >=0.8 alive)")
    print(f"  s=0.30 -> n=40 yields {N_ONE_MERGE*0.30*K_DISPATCH*P_PCT_PER_M5_US:.4f}% "
          f"(bar is {BAR_PCT}%)")
    print(f"  s=0.80 -> n=40 yields {N_ONE_MERGE*0.80*K_DISPATCH*P_PCT_PER_M5_US:.4f}% "
          f"(arming threshold is {ARM_PCT}%)")

    print()
    print("=" * 78)
    print("RULE 105.24 (c) - expected value of the whole night, by hypothesis")
    print("=" * 78)
    print("H_free  : concurrent-region dispatches are ~free (k<=0.2)")
    print("H_priced: 105.17 stands (k>=1.0)")
    print()
    print(f"{'programme':<34} {'H_free x%':>10} {'P2':>8} {'H_priced x%':>12} {'P2':>8}")
    for n, label in ((N_ONE_MERGE, "one merge"),
                     (N_TWO_MERGE, "two merges"),
                     (N_ALL_REMOVABLE, "every removable dispatch")):
        xf = gain_pct(n, 0.0872)
        xp = gain_pct(n, 1.0)
        print(f"{label:<34} {xf:9.4f}% {p_two_draws(xf):8.4f} "
              f"{xp:11.4f}% {p_two_draws(xp):8.4f}")
    print()
    print("prior-weighted EV of the merge programme (two merges), as a function")
    print("of the probability that H_free is true:")
    print(f"{'P(H_free)':>10} {'E[P(>=1 of 2 draws)]':>22}")
    for pf in (0.0, 0.25, 0.5, 0.75, 0.9, 1.0):
        ev = pf * p_two_draws(gain_pct(N_TWO_MERGE, 0.0872)) + \
             (1 - pf) * p_two_draws(gain_pct(N_TWO_MERGE, 1.0))
        print(f"{pf:10.2f} {ev:22.4f}")

    print()
    print("=" * 78)
    print("SELF-CHECKS")
    print("=" * 78)
    c1 = gain_pct(39, 1.890)
    print(f"39 dispatches at k=1.890 = {c1:.4f}% (105.17 says 1.3899%)  "
          f"{'OK' if abs(c1-1.3899) < 5e-4 else 'FAIL'}")
    c2 = gain_pct(30, 1.890)
    print(f"30 dispatches at k=1.890 = {c2:.4f}% (105.17 says 1.0691%)  "
          f"{'OK' if abs(c2-1.0691) < 5e-4 else 'FAIL'}")
    c3 = gain_pct(1, 0.0872) * 1000
    print(f"1 dispatch at k=0.0872   = {c3:.4f} milli-% (tanjiro says 1.6446)  "
          f"{'OK' if abs(c3-1.6446) < 2e-2 else 'FAIL'}")
    c4 = p_one_draw(0.1966)
    print(f"p(0.1966%) = {c4:.3e} (105.21/105.23 say 9.1e-07)  "
          f"{'OK' if abs(c4-9.1e-7) < 5e-8 else 'FAIL'}")
    c5 = G0_PCT / SIGMA_PCT
    print(f"g0/sigma = {c5:.2f} (105.21 says 5.42)  "
          f"{'OK' if abs(c5-5.42) < 5e-3 else 'FAIL'}")
    c6 = gain_pct(N_ALL_REMOVABLE, 0.0872)
    print(f"158 dispatches at k=0.0872 = {c6:.4f}% (tanjiro says 0.2599%)  "
          f"{'OK' if abs(c6-0.2599) < 3e-3 else 'FAIL'}")


if __name__ == "__main__":
    main()
