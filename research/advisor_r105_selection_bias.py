#!/usr/bin/env python3
"""Rule 105.10 — selection bias on argmax-of-sweep effect sizes.

The campaign de-biases *receipts* for the winner's curse (rules 93.3, 101.4,
nezuko-normalised-leaderboard §5.6) but has never de-biased a *candidate
effect size* that was selected as the argmax of a parameter sweep.  L3
(`research/tanjiro_packing_default_flip.patch`) is exactly that object:
#308 swept S in {2,4,8,16,32} and reported the interior argmax S=8 at
-36.9 us/step vs S=2, CI [-61.0, -12.9], with {4,8,16} *statistically tied*.

Selecting the max of m exchangeable arms inflates the reported effect by
    bias = sigma_contrast * sqrt(1 - rho) * E[max of m iid N(0,1)]
where rho is the correlation induced by the shared S=2 baseline.

Run:  python3 research/advisor_r105_selection_bias.py
"""
import math
from statistics import NormalDist

ND = NormalDist()

# ---------------------------------------------------------------- constants
PRICE = 0.015228          # %cs per us/step, M5 epoch (rule 105 host correction)
ALPHA = 0.4369            # bytes-regime M5/M4 factor (primary)
ALPHA_LO = 0.389          # bytes-regime sensitivity (B.0.6)
BETA = 0.5                # latency-regime M5/M4 factor
BAR = 0.4                 # %cs draw bar (rule 105.5)

# #308 L3 contrast, M4 paired ABBA
L3_POINT = 36.9           # us/step improvement (sign flipped to positive-good)
L3_CI = (12.9, 61.0)      # us/step, improvement convention


def emax(m: int) -> float:
    """E[max of m iid standard normals], by numerical integration."""
    if m == 1:
        return 0.0
    lo, hi, n = -12.0, 12.0, 200000
    h = (hi - lo) / n
    tot = 0.0
    for i in range(n + 1):
        z = lo + i * h
        # d/dz of Phi(z)^m = m Phi^{m-1} phi
        w = 1.0 if i in (0, n) else (4.0 if i % 2 else 2.0)
        tot += w * z * m * ND.cdf(z) ** (m - 1) * ND.pdf(z)
    return tot * h / 3.0


def pct(us: float, factor: float) -> float:
    return us * factor * PRICE


sigma = (L3_CI[1] - L3_CI[0]) / 2.0 / 1.959964
print(f"L3 contrast sigma (M4 us/step)            = {sigma:.3f}")
print(f"L3 as reported                            = {L3_POINT:.1f} us/step"
      f"  = {pct(L3_POINT, ALPHA):.4f} %cs (alpha={ALPHA})")
print()

print("selection-bias correction, m tied arms, rho = shared-baseline corr")
print(f"{'m':>3} {'rho':>5} {'E[max]':>8} {'bias us':>8} {'debiased us':>12}"
      f" {'%cs a=.4369':>12} {'%cs a=.389':>11}")
rows = []
for m in (2, 3, 4, 5):
    for rho in (0.0, 0.5):
        b = sigma * math.sqrt(1.0 - rho) * emax(m)
        d = L3_POINT - b
        rows.append((m, rho, b, d))
        print(f"{m:>3} {rho:>5.2f} {emax(m):>8.4f} {b:>8.3f} {d:>12.3f}"
              f" {pct(d, ALPHA):>12.4f} {pct(d, ALPHA_LO):>11.4f}")

# primary: m=3 ({4,8,16} tied), rho=0.5 (all contrasts share the S=2 arm)
bias = sigma * math.sqrt(0.5) * emax(3)
l3_deb = L3_POINT - bias
l3_pct = pct(l3_deb, ALPHA)
print()
print(f"PRIMARY (m=3, rho=0.5): bias = {bias:.2f} us/step "
      f"({100*bias/L3_POINT:.1f} % of the reported effect)")
print(f"  de-biased L3 = {l3_deb:.1f} us/step = {l3_pct:.4f} %cs "
      f"(alpha={ALPHA}); {pct(l3_deb, ALPHA_LO):.4f} %cs (alpha={ALPHA_LO})")
print(f"  vs rule 105.3's selected value {pct(L3_POINT, ALPHA):.4f} %cs")

# ------------------------------------------------- residual to the 0.4 % bar
print()
print("residual a second, different-family summand must supply (rule 105.5)")
for label, l3v in (("L3 as reported (105.3)", pct(L3_POINT, ALPHA)),
                   ("L3 de-biased  (105.10)", l3_pct),
                   ("L3 fails to replicate ", 0.0)):
    resid = BAR - l3v
    print(f"  {label}: L3={l3v:.4f} %  residual={resid:.4f} % "
          f"= {resid/(ALPHA*PRICE):>6.1f} us/step bytes"
          f" / {resid/(BETA*PRICE):>6.1f} us/step latency")

print()
print("residual as a fraction of each family's own M4 cost (de-biased L3)")
resid = BAR - l3_pct
fams = [("T2c  decode routed gate/up (edward #629)", 1497.7, "bytes"),
        ("T0b(a) qkv h64            (L3 site)     ", 1340.1, "bytes"),
        ("T3b  oproj h64            (alphonse #644)", 1117.7, "bytes"),
        ("T2d                                     ", 858.9, "bytes"),
        ("T1a                       (frieren #597)", 312.8, "latency"),
        ("T2b  gate_sp                            ", 248.0, "latency")]
for name, m4, regime in fams:
    f = ALPHA if regime == "bytes" else BETA
    need = resid / (f * PRICE)
    full = BAR / (f * PRICE)
    print(f"  {name} {regime:>7}: need {need:5.1f} us/step = "
          f"{100*need/m4:5.2f} % of own M4 cost "
          f"(was {full:5.1f} us = {100*full/m4:5.2f} % standalone)")

# ------------------------------------------- uncertainty of the summed bar
print()
print("uncertainty of a two-summand sum that just reaches the bar")
s_l3 = sigma * ALPHA * PRICE
for s2_us in (5.0, 10.0, 15.0):
    s2 = s2_us * ALPHA * PRICE
    ssum = math.hypot(s_l3, s2)
    lo = BAR - 1.959964 * ssum
    print(f"  sd(summand2)={s2_us:4.1f} us/step -> sd(sum)={ssum:.4f} % ;"
          f" 95% CI of a 0.400 % sum = [{lo:.4f}, {BAR + 1.959964*ssum:.4f}] %")

# ------------------------------------------------------- draw value, rule 101.5
print()
print("P(beat record on one draw) vs realised improvement g (gap 1.6359 %, "
      "sigma_resubmit 0.3016 %)")
for g in (0.0, 0.2, l3_pct, 0.4, 0.6, 0.8, 1.0):
    z = (1.6359 - g) / 0.3016
    print(f"  g = {g:.4f} %  ->  z = {z:5.3f}  P = {ND.cdf(-z):.3e}")
