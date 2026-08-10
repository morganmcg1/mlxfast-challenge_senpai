#!/usr/bin/env python3
"""R107-G addendum: test my per-family regime census against rule 105.13.

Rule 105.13 supplies, for the first time, a *measured* same-quantity M4 and M5
whole-decode pair:

    T_M4 = 8448.0 us/step   (maple-nezuko R106-B control mean, n=6, sd 16.35)
    T_M5 = 4141.5 us/step   (rule 58)
    k_steady = 0.4902

and a third conversion regime for dispatch glue:

    rule 57  M4 marginal per-dispatch glue : 1.2382 us
    rule 65  M5 marginal per-dispatch cost : 2.3403 us
    k_dispatch = 1.890

My census (this report, sections 3.2 / 3.3) assigns a *measured* regime label to
five decode families and inherits B.0.3's labels for the rest. That makes the
whole-decode budget a closure test with no free parameters outside the
advisor's own brackets:

    T_M5 = alpha * SUM(bytes families, M4)
         + beta  * SUM(latency families, M4)
         + k_i   * SUM(issue families, M4)
         + k_r   * residue(M4)

Everything is printed; nothing is fitted except the two unknowns k_i and k_r,
which are reported as a feasible set and compared to independent brackets.
"""

ALPHA = 0.4369
BETA = 0.5
T_M4 = 8448.0
T_M5 = 4141.5
K_DISPATCH = 2.3403 / 1.2382
M4_GLUE_PER_DISPATCH = 1.2382
M5_COST_PER_DISPATCH = 2.3403
# rule 105: dPct_cs = d_M4 * k * 0.015228  =>  1 M5 us/step = 0.015228 %cs
PCT_PER_M5_US = 0.015228
M5_US_PER_PCT = 1.0 / PCT_PER_M5_US
DRAW_BAR_PCT = 0.40

# B.0.3, M4 column. regime: my measured label where I have one, else B.0.3's.
# T3a / T3a' M4 figures corrected per the B.0.3 staleness caveat (636.0 -> 618.9)
# and relabelled ISSUE per rule 100.3 + my own R107-D (#642) measurement.
FAMILIES = [
    # name,                       calls, M4 us/step, regime,  source of label
    ("T2c routed gate+up qmv",       39, 1497.7, "bytes",   "MEASURED here (family D)"),
    ("T0b(a) qkv h64",               30, 1340.1, "bytes",   "MEASURED here (family C)"),
    ("T3b oproj h64",                30, 1117.7, "bytes",   "MEASURED here (family A)"),
    ("T2d routed+shared down+resid", 39,  858.9, "bytes",   "MEASURED here (family B)"),
    ("T3a sliding fused attn",       30,  618.9, "issue",   "rule 100.3 + my #642"),
    ("T1c lmhead int5",               1,  420.3, "bytes",   "B.0.3"),
    ("T0b(b) qkv h48",               10,  362.8, "bytes",   "B.0.3"),
    ("T1a residual/rms/router",      39,  312.8, "latency", "B.0.3"),
    ("T2a shared gate+up qmv",       39,  287.1, "latency", "B.0.3"),
    ("T3c oproj h48",                10,  301.8, "bytes",   "B.0.3"),
    ("T2b gate_sp h64",              30,  248.0, "latency", "MEASURED here (family E)"),
    ("dense gate_up (layer 0)",       1,  269.4, "bytes",   "B.0.3"),
    ("T3a' full fused attn",         10,  229.7, "issue",   "rule 100.3 + my #642"),
    ("dense_down (layer 0)",          1,  133.8, "bytes",   "B.0.3"),
    ("T2b' gate_sp h48",             10,   80.2, "latency", "B.0.3"),
]


def pool(regime):
    return sum(f[2] for f in FAMILIES if f[3] == regime)


def rule(title):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main():
    rule("0. Inputs")
    print(f"  alpha (bytes)          = {ALPHA}")
    print(f"  beta  (latency)        = {BETA}")
    print(f"  k_dispatch (rules 57/65) = {K_DISPATCH:.4f}")
    print(f"  T_M4 (rule 105.13a)    = {T_M4:.1f} us/step")
    print(f"  T_M5 (rule 58)         = {T_M5:.1f} us/step")
    print(f"  k_steady = T_M5/T_M4   = {T_M5 / T_M4:.4f}")
    print(f"  1 %cs                  = {M5_US_PER_PCT:.3f} M5 us/step")
    print(f"  0.40 %cs draw bar      = {DRAW_BAR_PCT * M5_US_PER_PCT:.2f} M5 us/step")

    rule("1. The census pools, by regime label")
    b, l, i = pool("bytes"), pool("latency"), pool("issue")
    census = b + l + i
    residue = T_M4 - census
    for name, calls, m4, reg, src in FAMILIES:
        print(f"  {name:32s} {calls:3d} calls  {m4:7.1f} M4 us  {reg:8s}  {src}")
    print(f"  {'BYTES pool':32s}     {'':10s} {b:7.1f} M4 us/step")
    print(f"  {'LATENCY pool':32s}     {'':10s} {l:7.1f} M4 us/step")
    print(f"  {'ISSUE pool':32s}     {'':10s} {i:7.1f} M4 us/step")
    print(f"  {'census total':32s}     {'':10s} {census:7.1f} M4 us/step"
          f"  = {100 * census / T_M4:.1f} %% of T_M4")
    print(f"  {'residue (non-census)':32s}     {'':10s} {residue:7.1f} M4 us/step"
          f"  = {100 * residue / T_M4:.1f} %% of T_M4")

    rule("2. Closure test: does the census reproduce the measured T_M5?")
    fixed = ALPHA * b + BETA * l
    need = T_M5 - fixed
    print(f"  alpha*BYTES + beta*LATENCY            = {fixed:8.1f} M5 us/step")
    print(f"  remainder that ISSUE+residue must supply = {need:8.1f} M5 us/step")
    print(f"  ISSUE+residue M4                      = {i + residue:8.1f} M4 us/step")
    print(f"  => implied blended k for ISSUE+residue = {need / (i + residue):.4f}")
    print()
    print("  Feasible (k_issue, k_residue) pairs on the closure line:")
    print("    k_issue   k_residue   note")
    for ki in (ALPHA, 0.50, 0.55, 0.60, 0.654, 0.70):
        kr = (need - ki * i) / residue
        note = ""
        if 1.0 <= kr <= K_DISPATCH:
            note = "INSIDE rule 105.13c bracket [1.0, 1.89]"
        elif kr < 1.0:
            note = "below the 105.13c conservative floor"
        else:
            note = "above k_dispatch"
        print(f"    {ki:7.4f}   {kr:8.4f}   {note}")

    rule("2b. The two headline readings of the closure line")
    ki_phys = ALPHA
    kr_phys = (need - ki_phys * i) / residue
    print("  (i) PHYSICALLY MOTIVATED k_issue. Between an M4 Pro and the ranked M5")
    print("      both DRAM bandwidth and ALU throughput scale with the same")
    print("      core-count / fabric width, so k_issue should sit near alpha, not")
    print("      near beta. Setting k_issue = alpha:")
    print(f"        => k_residue = {kr_phys:.4f}")
    print("      That lands inside rule 105.13(c)'s independently derived bracket")
    print("      [1.0, 1.89] and NEARER the k_dispatch end than the floor. This is")
    print("      an INDEPENDENT corroboration of the third regime: 105.13(c) got")
    print("      [1.0, 1.89] from a difference of two column totals (one derived);")
    print("      this route uses a regime-labelled census against a MEASURED T_M4.")
    print()
    print("      Why the third regime is REQUIRED, not optional: under a PURE")
    print("      alpha/beta model there is no assignment of the ISSUE and residue")
    print("      pools that reaches the measured k_steady = 0.4902 --")
    for ki, kr, tag in ((ALPHA, BETA, "issue=alpha, residue=beta"),
                        (BETA, BETA, "issue=beta,  residue=beta (max under a/b)"),
                        (ALPHA, ALPHA, "issue=alpha, residue=alpha (min)")):
        pred = (ALPHA * b + BETA * l + ki * i + kr * residue) / T_M4
        print(f"        {tag:42s} k_steady = {pred:.4f}")
    print(f"      -- every one falls short of {T_M5 / T_M4:.4f}. The shortfall is")
    print("      the residue's k > 1.")
    print()
    print("  (ii) BOUND ON k_issue. Imposing 105.13(c)'s bracket on k_residue:")
    ki_hi = (need - 1.0 * residue) / i
    ki_lo = (need - K_DISPATCH * residue) / i
    print(f"        k_residue = 1.00  => k_issue = {ki_hi:.4f}  (upper bound)")
    print(f"        k_residue = 1.89  => k_issue = {ki_lo:.4f}  (lower bound)")
    print(f"      => k_issue in [{ki_lo:.3f}, {ki_hi:.3f}]. NOBODY SHOULD PRICE AN")
    print(f"      ATTENTION-SIDE (issue-regime) M4 SAVING ABOVE {ki_hi:.3f}x.")
    print("      In particular beta = 0.5 is inside this range but 1.0 is not:")
    print("      issue-regime savings do NOT carry over one-for-one to M5.")

    rule("2c. Sensitivity of the (i) reading to the measured T_M4")
    sd, n = 16.35, 6
    sem = sd / (n ** 0.5)
    print(f"  T_M4 = {T_M4:.1f} +/- {sd:.2f} (sd, n={n}) => sem {sem:.2f} us/step")
    num = need - ki_phys * i
    for mult, tag in ((0.0, "point"), (1.0, "+/-1 sem"), (2.0, "+/-2 sem")):
        lo = num / (residue + mult * sem)
        hi = num / (residue - mult * sem)
        if mult == 0.0:
            print(f"    {tag:9s} k_residue = {lo:.4f}")
        else:
            print(f"    {tag:9s} k_residue in [{lo:.4f}, {hi:.4f}]"
                  f"   {'INSIDE' if lo >= 1.0 and hi <= K_DISPATCH else 'CROSSES'}"
                  " the [1.0, 1.89] bracket")

    rule("3. Can the closure REJECT an ISSUE label on the four big GEMV families?")
    gemv = sum(f[2] for f in FAMILIES[:4])
    print(f"  the four GEMV families total {gemv:.1f} M4 us/step")
    print("  Counterfactual: move them from BYTES to ISSUE and re-solve the SAME")
    print("  closure line, again imposing k_residue in [1.0, 1.89]:")
    need_cf = T_M5 - ALPHA * (b - gemv) - BETA * l
    i_cf = i + gemv
    cf_hi = (need_cf - 1.0 * residue) / i_cf
    cf_lo = (need_cf - K_DISPATCH * residue) / i_cf
    print(f"    k_issue in [{cf_lo:.4f}, {cf_hi:.4f}]")
    print(f"  My labels required   k_issue in [{ki_lo:.4f}, {ki_hi:.4f}]")
    print("  These OVERLAP. So, stated honestly:")
    print("  ** THE WHOLE-DECODE CLOSURE DOES NOT DISCRIMINATE BYTES FROM ISSUE **")
    print("  ** ON THE GEMV BLOCK. It is a consistency check, not the evidence.  **")
    print("  The reason is structural: a one-equation, two-unknown line cannot")
    print("  separate two pools whose candidate k values are ~0.44 vs ~0.46.")
    print()
    print("  What DOES discriminate is the direct measurement in this report:")
    print("   - family D dose ladder: exposed ALU 1.10 %% of dispatch time, two")
    print("     independent residency-defeated sessions (section 2.4)")
    print("   - all four GEMV families at 85.5-91.0 %% of their geometry-matched")
    print("     bandwidth ceiling, a 5.5 pp band (section 3.2)")
    print("   - agreement with section B.1's independent M4 GPU-timer census to")
    print("     -0.84 pp and +1.29 pp on the two families it also measured (3.2.1)")
    print("  The closure's role is to confirm that the labels, once measured, are")
    print("  ARITHMETICALLY CONSISTENT with the only measured whole-decode k we")
    print("  have -- and they are, with no free parameter outside 105.13's bracket.")
    print()
    print("  One thing the counterfactual DOES establish: the ISSUE relabelling is")
    print(f"  only survivable if k_issue <= {cf_hi:.3f}. An issue-bound GEMV block")
    print("  priced at beta = 0.5 or at 1.0 breaks the whole-decode budget:")
    for ki in (0.50, 0.654, 1.0):
        pred = ALPHA * (b - gemv) + BETA * l + ki * i_cf + 1.0 * residue
        print(f"    k_issue {ki:6.3f} (k_r at floor 1.0) => T_M5 {pred:8.1f}"
              f"  {100 * (pred / T_M5 - 1):+7.2f} %% vs measured")

    rule("4. Re-pricing family E's full-fusion prize under the third regime")
    e_calls = 30
    e_prize_m4 = (8.27 - 0.984) * e_calls
    glue_m4 = e_calls * M4_GLUE_PER_DISPATCH
    rest_m4 = e_prize_m4 - glue_m4
    old = e_prize_m4 * BETA
    new = rest_m4 * BETA + glue_m4 * K_DISPATCH
    print(f"  family E above-byte-floor time    = {8.27 - 0.984:.3f} us/dispatch")
    print(f"  x {e_calls} dispatches                    = {e_prize_m4:.1f} M4 us/step")
    print(f"  of which rule-57 dispatch glue    = {glue_m4:.1f} M4 us/step")
    print(f"  remainder (in-kernel latency)     = {rest_m4:.1f} M4 us/step")
    print(f"  OLD pricing, all at beta          = {old:.1f} M5 us/step"
          f"  = {old * PCT_PER_M5_US:.3f} %cs = {old * PCT_PER_M5_US / DRAW_BAR_PCT:.2f} bars")
    print(f"  NEW pricing, glue at k_dispatch   = {new:.1f} M5 us/step"
          f"  = {new * PCT_PER_M5_US:.3f} %cs = {new * PCT_PER_M5_US / DRAW_BAR_PCT:.2f} bars")
    d_only = e_calls * M5_COST_PER_DISPATCH
    print(f"  dispatch-elimination component alone (rule 65, already M5):")
    print(f"    {e_calls} x {M5_COST_PER_DISPATCH} = {d_only:.2f} M5 us/step"
          f" = {d_only * PCT_PER_M5_US:.3f} %cs"
          f" = {d_only * PCT_PER_M5_US / DRAW_BAR_PCT:.2f} bars")
    print("  ERRATUM: an earlier revision of this report quoted that component as")
    print("  0.535 %cs by applying beta to rule 65's number. Rule 65 is ALREADY an")
    print("  M5 price; converting it again halved it. Correct value is above.")

    rule("5. Are my GEMV STOP verdicts invariant to the third regime?")
    print("  My floor is  floor_us = bytes/266.3 + 3.97, i.e. it already CREDITS")
    print("  each dispatch with the measured fixed intercept. Rule 57's marginal")
    print("  M4 dispatch glue is 1.2382 us, so dispatch glue sits BELOW my floor:")
    print(f"    intercept 3.970 us/dispatch, of which glue {M4_GLUE_PER_DISPATCH} us"
          f" = {100 * M4_GLUE_PER_DISPATCH / 3.970:.0f} %%")
    print("  => the reported non-byte slack is in-kernel time, not dispatch glue,")
    print("     and cannot be priced at k_dispatch. Worst case it prices at beta:")
    slack = [("D T2c", 0.963, 39), ("A T3b", 0.794, 30),
             ("C T0b(a)", 0.055, 30), ("B T2d", -0.774, 39)]
    print("    family     slack us/disp   M4 us/step   at alpha %cs   at beta %cs   beta bars")
    for name, s, calls in slack:
        per = s * calls
        print(f"    {name:10s} {s:11.3f} {per:12.1f} {per * ALPHA * PCT_PER_M5_US:13.3f}"
              f" {per * BETA * PCT_PER_M5_US:13.3f} {per * BETA * PCT_PER_M5_US / DRAW_BAR_PCT:11.2f}")
    print("  All four remain below the 0.40 %cs draw bar even at beta. VERDICTS HOLD.")
    print()
    print("  What 105.13 DOES open, on my own numbers: the intercept itself.")
    for name, calls in (("D T2c", 39), ("A T3b", 30), ("C T0b(a)", 30),
                        ("B T2d", 39), ("E T2b gate_sp", 30)):
        g = calls * M5_COST_PER_DISPATCH
        print(f"    {name:14s} {calls:3d} dispatches -> {g:7.2f} M5 us/step"
              f" = {g * PCT_PER_M5_US:.3f} %cs if MERGED AWAY entirely")
    print("  That is 105.13(e)'s own headline, restated per family. It is a")
    print("  dispatch-COUNT lever (deconflicted to #48), reachable only by kernel")
    print("  merging, and my census says family E is the cheapest merge target:")
    print("  262 KB/dispatch, 88.1 %% latency, 8.27 us/dispatch, nothing to stream.")


if __name__ == "__main__":
    main()
