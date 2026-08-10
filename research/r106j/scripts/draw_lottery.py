#!/usr/bin/env python3
"""What is frieren's single last-call draw actually worth, per candidate tree?

Inputs are all campaign constants recorded in research/CURRENT_RESEARCH_STATE.md
and in this round's PR threads:

  sigma_score  = 0.3728 %   sd(ln officialScore), paired, at a FIXED tree
  gap_record   = 1.2846 %   ln-gap from the SHRUNK anchor 2.583106 to the record
  anchor_cs    = 2.583106   shrunk mean merit of our tree family (state doc 96.2)
  record       = 2.61650354381456  (officialScore of cc6ddc12)

⚠️ CONSTANT PAIRING. There are two sigmas in the campaign and two anchors, and
mixing them across spaces is the mistake this script exists to avoid:
  - sd(ln cs)           = 0.2276 %  pairs with a gap measured in cs
  - sd(ln officialScore)= 0.3728 %  pairs with the 1.2846 % gap, which is an
                                    officialScore gap
  - anchor 2.590559 is our best-ever *receipt*; it is a SELECTED MAXIMUM and
    using it as the merit of that tree is the winner's curse. State doc 96.2
    shrinks it to 2.583106 and that is the anchor a forward-looking decision
    must use. Quoting the 0.9965 % gap off the selected max overstates our
    position by 0.29 % — which is, not coincidentally, the same size as the
    effects this round is arguing about.

For a tree carrying true merit m (% of score, relative to the shrunk anchor), a
single draw beats the record iff  m + eps > gap_record,  eps ~ N(0, sigma_score).
We also price the heavy-tail alternative (Student-t), because the record itself
is one observation on the tail.
"""
import math

# --- Rule 101 (PR #597, frieren) constants: MEASURED at n=3 exact replicates.
# These SUPERSEDE the inferred 96.2 constants this script originally used.
SIGMA = 0.3016        # sd(ln officialScore) | fixed tree   (supersedes 0.3728)
GAP = 1.6359          # unbiased gap to the record, in officialScore space
ANCHOR_O = 2.574049   # geometric-mean officialScore of the 3 replicates
RECORD_O = 2.61650354381456
# Superseded values, retained only to quantify how wrong the old framing was:
OLD_SIGMA = 0.3728
OLD_GAP = 1.2846
BEST_CS = 2.590559    # a SELECTED MAX in `cs` space
ANCHOR_CS = 2.583106  # 96.2's inferred shrunk anchor, in `cs` space
MEAS_CS = 2.582463    # Rule 101's MEASURED 3-replicate mean `cs`


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def t_sf(z, nu):
    """Survival function of Student-t with nu dof, via the regularised incomplete beta."""
    x = nu / (nu + z * z)
    return 0.5 * betainc(nu / 2.0, 0.5, x) if z > 0 else 1.0 - 0.5 * betainc(nu / 2.0, 0.5, x)


def betacf(a, b, x, itmax=300, eps=3e-16):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < 1e-300:
        d = 1e-300
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < 1e-300:
            d = 1e-300
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < 1e-300:
            d = 1e-300
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


def betainc(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * betacf(a, b, x) / a
    return 1.0 - math.exp(lbeta + b * math.log(1.0 - x) + a * math.log(x)) * betacf(b, a, 1.0 - x) / b


print("=== SPACE CHECK: `cs` and `officialScore` are DIFFERENT quantities ===")
print(f"  4b0e051b receipt:  cs {BEST_CS:.6f}   officialScore 2.575377   "
      f"(differ by {100*math.log(BEST_CS/2.575377):.3f} %)")
print("  -> a gap of (record officialScore) / (our cs) is a UNIT ERROR, not a gap.\n")

gap_o = 100 * math.log(RECORD_O / ANCHOR_O)
print(f"record officialScore        {RECORD_O:.6f}")
print(f"our geo-mean officialScore  {ANCHOR_O:.6f}  (n=3 exact replicates, Rule 101)")
print(f"  -> unbiased gap {gap_o:.4f} %   (campaign constant {GAP} %)   z = {GAP/SIGMA:.2f}\n")

print("--- how wrong the superseded framing was ---")
print(f"  96.2 inferred shrunk anchor (cs)  {ANCHOR_CS:.6f}")
print(f"  101 MEASURED 3-replicate mean cs  {MEAS_CS:.6f}   "
      f"-> shrinkage was RIGHT to {100*math.log(ANCHOR_CS/MEAS_CS):+.4f} %")
print(f"  but the selected-max receipt      {BEST_CS:.6f}   "
      f"-> overstated by {100*math.log(BEST_CS/MEAS_CS):+.4f} %")
print(f"  old (sigma {OLD_SIGMA} %, gap {OLD_GAP} %) -> z {OLD_GAP/OLD_SIGMA:.2f}, "
      f"P {norm_sf(OLD_GAP/OLD_SIGMA):.3e}")
print(f"  new (sigma {SIGMA} %, gap {GAP} %) -> z {GAP/SIGMA:.2f}, "
      f"P {norm_sf(GAP/SIGMA):.3e}   "
      f"({norm_sf(OLD_GAP/OLD_SIGMA)/norm_sf(GAP/SIGMA):.0f}x more pessimistic)\n")

print(f"{'candidate tree':<34}{'merit %':>9}{'z':>8}{'P(beat record) Gaussian':>26}{'  t(4)':>12}")
print("-" * 92)
cands = [
    ("T0 = shipped best tree", 0.0),
    ("T0 + C2a (inert at default env)", 0.0),
    ("T0P  packing flip (measured)", -0.0606),
    ("T0P  if #308's corrected prior", +0.338),
    ("T0P  if #308's ORIGINAL claim", +0.562),
    ("hypothetical: clears the 0.4 % bar", +0.400),
    ("hypothetical: everything stacks", +1.000),
]
for name, m in cands:
    z = (GAP - m) / SIGMA
    print(f"{name:<34}{m:>9.4f}{z:>8.2f}{norm_sf(z):>26.3e}{t_sf(z,4):>12.3e}")

print()
print("E[draws to a record] at the Gaussian rate, for the shipped tree:")
z0 = GAP / SIGMA
p0 = norm_sf(z0)
print(f"  z = {z0:.2f}, P = {p0:.3e}, E[draws] = {1/p0:.3e}, hours at 2.7 draws/h = {1/p0/2.7:.3e}")
print("Under a t(4) tail:")
p0t = t_sf(z0, 4)
print(f"  P = {p0t:.3e}, E[draws] = {1/p0t:.1f}, hours at 2.7 draws/h = {1/p0t/2.7:.1f}")
print()
print("Merit needed for a single draw to have a given win probability (Gaussian):")
for target in (0.01, 0.05, 0.10, 0.50):
    # invert: gap - m = sigma * z_target
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if norm_sf((GAP - mid) / SIGMA) < target:
            lo = mid
        else:
            hi = mid
    print(f"  P = {target:>4.0%}  requires merit = {0.5*(lo+hi):+.3f} % of cs")
