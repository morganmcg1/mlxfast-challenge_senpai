#!/usr/bin/env python3
"""Which receipt channel is a PRECISE instrument: decode (T) or prefill (P)?

######################################################################
# SUPERSEDED -- AUDIT TRAIL ONLY.  DO NOT QUOTE THIS SCRIPT'S POOLED
# PREFILL NUMBER.  Use research/advisor_r104_receipt_as_instrument.py.
#
# This script pools ALL 7 verified identical-code replicate groups.  One
# of them, group 7cbffc2c17d7 (n=4), has sd(P) = 13.4882 us/tok -- 20x to
# 1000x every other group -- and it dominates the pooled variance.  The
# untrimmed pooled sd(P) = 5.6906 us/tok (= 2.9136 ms on the 512-token
# wall) that this script prints is therefore CONTAMINATED and understates
# the prefill channel's precision by roughly an order of magnitude.
#
#   per-group sd(P), us/tok:
#     dc437b0e0b91  n=5   0.1929
#     521a2f712478  n=4   0.4211
#     7cbffc2c17d7  n=4  13.4882   <-- outlier, excluded downstream
#     1008c6920be3  n=4   1.0231
#     d18d0983830b  n=3   0.4704
#     9beb75a6fbc5  n=2   0.6698
#     4d5ac413d1a7  n=2   0.0121
#
# The trimmed analysis (6 groups, dof = 14) in
# advisor_r104_receipt_as_instrument.py is authoritative:
#     sd(T) = 12.079 us/step   sd(P) = 0.5802 us/tok = 0.2970 ms
# and it reverses this script's conclusion: prefill is 1.64x the MORE
# precise channel per unit of score, not the less precise one.
#
# Retained because the untrimmed pooled decode figure is unaffected
# (sd(T) = 12.540 us/step, dof 17, vs 12.079 trimmed) and because the
# per-group breakdown above is the evidence that motivated the trim.
######################################################################

Round 103 established that the receipt channel cannot resolve a 20 us/step
decode contrast: identical-code sd(T) = 12-14 us/step, so z ~ 1.  That verdict
was formed entirely on the DECODE side.  Prefill was never priced the same way.

This script measures, on verified identical-code replicate groups:
  sd(P)  -- prefill us/token dispersion
  sd(T)  -- steady-state decode us/step dispersion
and converts each into "how big a lever does one receipt pair resolve", and
into score terms via the established prices.

Prices (established, research/maple-r99-*): prefill total 0.3781 %/ms of the
512-token prefill wall; decode 0.015228 %/us-step.  1 % of cs = 65.67 us/step.

Inputs: research/artifacts/advisor-r103/{receipt-corpus-frozen.json,
replicate-sigma.json, our-receipts-provenance.json}
"""
import json
import math
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "artifacts", "advisor-r103")
CORPUS = json.load(open(os.path.join(ART, "receipt-corpus-frozen.json")))
SIGMA = json.load(open(os.path.join(ART, "replicate-sigma.json")))
PROV = json.load(open(os.path.join(ART, "our-receipts-provenance.json")))

digest_of = SIGMA["digests"]

PCT_PER_MS_PREFILL = 0.3781      # % of score per ms off the 512-tok prefill wall
PCT_PER_US_DECODE = 0.015228     # % of score per us/step off decode
US_STEP_PER_PCT_CS = 65.67


def sd(xs):
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


# ---- group our receipts by exact Sources/ tree digest ----------------------
groups = defaultdict(list)
for r in PROV:
    d = digest_of.get(r.get("sub_sha") or "")
    if not d:
        continue
    D = r.get("D")
    P = r.get("P")
    if D is None or P is None:
        continue
    groups[d].append({"id": r["id8"], "D": D, "P": P, "T": D - 4.0 * P})

groups = {k: v for k, v in groups.items() if len(v) >= 2}

print("identical-code replicate groups (>=2 receipts):", len(groups))
print()
print(f"{'digest':14s} {'n':>2s} {'sd(T) us/step':>13s} {'sd(P) us/tok':>12s} "
      f"{'sd(P) as ms':>11s} {'sd(lnP) %':>9s}")

pool_T = []   # (deviations, dof)
pool_P = []
for d, rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    Ts = [r["T"] for r in rows]
    Ps = [r["P"] for r in rows]
    sT, sP = sd(Ts), sd(Ps)
    mP = sum(Ps) / len(Ps)
    # 512-token prefill wall in ms
    sP_ms = sP * 512.0 / 1000.0
    print(f"{d[:12]:14s} {len(rows):2d} {sT:13.3f} {sP:12.4f} {sP_ms:11.4f} "
          f"{100.0*sP/mP:9.4f}")
    mT = sum(Ts) / len(Ts)
    pool_T.append((sum((t - mT) ** 2 for t in Ts), len(Ts) - 1))
    pool_P.append((sum((p - mP) ** 2 for p in Ps), len(Ps) - 1))

ssT = sum(a for a, _ in pool_T); dofT = sum(b for _, b in pool_T)
ssP = sum(a for a, _ in pool_P); dofP = sum(b for _, b in pool_P)
sdT = math.sqrt(ssT / dofT)
sdP = math.sqrt(ssP / dofP)
meanP = sum(r["P"] for v in groups.values() for r in v) / sum(len(v) for v in groups.values())

print()
print(f"POOLED (dof {dofT}):  sd(T) = {sdT:.3f} us/step")
print(f"POOLED (dof {dofP}):  sd(P) = {sdP:.4f} us/tok  = "
      f"{sdP*512.0/1000.0:.4f} ms on the 512-tok wall  = {100.0*sdP/meanP:.4f} %")
print(f"mean P = {meanP:.4f} us/tok -> prefill wall {meanP*512.0/1000.0:.3f} ms")

# ---- sigma of a DIFFERENCE of two single receipts --------------------------
dT = sdT * math.sqrt(2.0)
dP_ms = sdP * math.sqrt(2.0) * 512.0 / 1000.0
print()
print(f"sigma of a 1-vs-1 difference:  decode {dT:.2f} us/step | "
      f"prefill {dP_ms:.4f} ms")

# ---- what does one receipt pair resolve, in SCORE terms? -------------------
print()
print("Minimum detectable effect at |z|=2 from ONE receipt pair:")
mde_dec_us = 2.0 * dT
mde_pre_ms = 2.0 * dP_ms
print(f"  decode : {mde_dec_us:8.2f} us/step  = {mde_dec_us*PCT_PER_US_DECODE:6.3f} % of score")
print(f"  prefill: {mde_pre_ms:8.4f} ms       = {mde_pre_ms*PCT_PER_MS_PREFILL:6.3f} % of score")

# ---- z for the archive's named live prefill levers -------------------------
print()
print("Archive-sized prefill levers, priced and powered on ONE receipt pair:")
for name, ms in [("§4.15 realistic ceiling (low)", 3.0),
                 ("§4.15 realistic ceiling (high)", 6.0),
                 ("§4.15 central expectation", 4.5),
                 ("H6 plane separation (low)", 4.4),
                 ("H8 dense NAX audit", 5.9),
                 ("+0.5 % score bar", 0.5 / PCT_PER_MS_PREFILL),
                 ("+1.0 % score target", 1.0 / PCT_PER_MS_PREFILL)]:
    z = ms / dP_ms
    print(f"  {name:34s} {ms:6.3f} ms  -> {ms*PCT_PER_MS_PREFILL:6.3f} % score, z = {z:7.1f}")

print()
print("Decode levers for comparison:")
for name, us in [("frontier-ArmR residual", 20.15),
                 ("revert cost", 30.09),
                 ("+0.5 % score bar", 0.5 * US_STEP_PER_PCT_CS),
                 ("+1.0 % score target", 1.0 * US_STEP_PER_PCT_CS)]:
    z = us / dT
    print(f"  {name:34s} {us:6.2f} us/step -> {us*PCT_PER_US_DECODE:6.3f} % score, z = {z:7.1f}")

# ---- precision ratio -------------------------------------------------------
print()
eq_dec_pct = dT * PCT_PER_US_DECODE
eq_pre_pct = dP_ms * PCT_PER_MS_PREFILL
print(f"1-vs-1 noise expressed in SCORE %:  decode {eq_dec_pct:.4f} % | "
      f"prefill {eq_pre_pct:.4f} %")
print(f"=> the receipt channel is {eq_dec_pct/eq_pre_pct:.1f}x more precise "
      f"per unit of SCORE on the prefill side than on the decode side.")

# ---- corpus-wide cross-check (all solvers, not just ours) ------------------
allP = [r["cand_pre"] for r in CORPUS if r.get("cand_pre")]
allD = [r["cand_dec"] for r in CORPUS if r.get("cand_dec")]
if allP:
    mp = sum(allP) / len(allP)
    print()
    print(f"corpus-wide (mixes code, upper bound): n={len(allP)} "
          f"sd(P)={sd(allP):.3f} ({100*sd(allP)/mp:.3f} %), "
          f"sd(D)={sd(allD):.2f}")
