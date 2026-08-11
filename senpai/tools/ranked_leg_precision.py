#!/usr/bin/env python3
"""Which leg of the ranked receipt is the precise instrument?

Twelve advisor replay receipts, 2026-08-11 00:39Z .. 05:33Z, all the same
HEAD-class code except that the last four carry alphonse's merged fused
QKV+gate_sp grid-append (merge commit 484d03c0, 2026-08-11T04:03:39Z).

Two questions:
  1. Does the merged -0.591% M4 decode win appear in the ranked decode leg?
  2. Which candidate leg (decode or prefill) resolves a code change better,
     and where does the leaderboard noise actually live?

Every number here is a raw field of officialMetrics; nothing is modelled.
"""
from __future__ import annotations

import math
import statistics

# id, createdAt, cand_decode, cand_prefill, base_decode, base_prefill, score
PRE = [
    ("2aedeb87", "00:39:49", 0.0049312080078125, 0.000187987060546875,
     None, 0.00038832608984375, 2.60026627118063),
    ("ed40f3ee", "01:07:24", 0.0049282265625, 0.00018783740234375,
     None, 0.000364209880859375, 2.55785830244444),
    ("0531544b", "01:31:01", 0.00490711328125, 0.000187690509765625,
     None, 0.000368419921875, 2.57278074829225),
    ("cb4de9e0", "01:54:46", 0.004897051109375, 0.0001880314140625,
     None, 0.00036539094921875, 2.57646292274507),
    ("be958bcd", "02:23:20", 0.004930751296875, 0.0001880320625,
     None, 0.0003656519375, 2.56673464083483),
    ("cdf740c2", "03:05:59", 0.0049487503203125, 0.000187764974609375,
     None, 0.00036648836328125, 2.56844457398793),
    ("354c40c7", "03:30:50", 0.0049124921875, 0.00018799072265625,
     None, 0.00036610400390625, 2.56779644583209),
    ("53c8acac", "03:55:01", 0.0049052083359375, 0.00018798836328125,
     None, 0.000366796794921875, 2.57270888151077),
]
POST = [
    ("47fa4d85", "04:20:06", 0.00491371875, 0.00018780460546875,
     0.013860357421875, 0.00036736083984375, 2.57406646389338),
    ("db4fa283", "04:44:34", 0.0049317789765625, 0.00018789616015625,
     0.0138430084609375, 0.00036737687109375, 2.56429884092213),
    ("fc7a5447", "05:09:00", 0.0049159111328125, 0.000187699869140625,
     0.0138841650390625, 0.00037526692578125, 2.59063296787656),
    ("412aad2b", "05:33:15", 0.0049425778046875, 0.000187438638671875,
     0.01387612109375, 0.000384062419921875, 2.59490580799781),
]

# alphonse's merged M4 result, converted to a ranked-decode prediction
PREDICTED_DECODE_GAIN = 0.00591  # -0.591% of decode wall


def stats(xs):
    mu = statistics.fmean(xs)
    sd = statistics.stdev(xs) if len(xs) > 1 else float("nan")
    return mu, sd, sd / mu * 100.0


def welch(mu1, sd1, n1, mu2, sd2, n2):
    se = math.sqrt(sd1 * sd1 / n1 + sd2 * sd2 / n2)
    return (mu1 - mu2) / se, se


print("=" * 74)
print("1. CANDIDATE DECODE LEG  --  does the merged win appear on the ranked host?")
print("=" * 74)
pre_d = [r[2] for r in PRE]
post_d = [r[2] for r in POST]
mu_pre, sd_pre, cv_pre = stats(pre_d)
mu_post, sd_post, cv_post = stats(post_d)
print(f"pre-gate  n={len(pre_d)}  mean={mu_pre:.10f}  sd={sd_pre:.3e}  cv={cv_pre:.4f}%")
print(f"post-gate n={len(post_d)}  mean={mu_post:.10f}  sd={sd_post:.3e}  cv={cv_post:.4f}%")
obs = (mu_post / mu_pre - 1.0) * 100.0
print(f"observed shift            : {obs:+.4f}%   (negative = the win appeared)")
print(f"predicted shift from #700  : {-PREDICTED_DECODE_GAIN*100:+.4f}%")
t_null, se = welch(mu_post, sd_post, len(post_d), mu_pre, sd_pre, len(pre_d))
print(f"Welch SE of the difference : {se/mu_pre*100:.4f}%  (relative)")
print(f"t vs null (no change)      : {t_null:+.3f}")
print()
print("how much of the predicted win can we exclude?")
print(f"{'transfer':>9} {'predicted post mean':>21} {'t (obs - pred)':>15} {'excluded?':>11}")
for frac in (1.0, 0.75, 0.5, 0.4, 0.25, 0.1):
    pred_mu = mu_pre * (1.0 - frac * PREDICTED_DECODE_GAIN)
    t = (mu_post - pred_mu) / se
    print(f"{frac*100:>8.0f}% {pred_mu:>21.10f} {t:>+15.3f} "
          f"{'YES 2sig' if t > 2.0 else ('marginal' if t > 1.5 else 'no'):>11}")

print()
print("=" * 74)
print("2. WHICH LEG IS THE PRECISE INSTRUMENT?  (all 12 receipts, same code class)")
print("=" * 74)
allr = PRE + POST
rows = [
    ("candidate decode ", [r[2] for r in allr], 0.75),
    ("candidate prefill", [r[3] for r in allr], 0.25),
    ("baseline prefill ", [r[5] for r in allr], 0.25),
]
print(f"{'leg':18} {'n':>3} {'mean':>16} {'cv':>9} {'elasticity':>11} {'score cv':>9}")
for name, xs, elas in rows:
    mu, sd, cv = stats(xs)
    print(f"{name:18} {len(xs):>3} {mu:>16.10f} {cv:>8.4f}% {elas:>11.2f} {cv*elas:>8.4f}%")
print()
_, _, cvd = stats([r[2] for r in allr])
_, _, cvp = stats([r[3] for r in allr])
print(f"candidate decode cv / candidate prefill cv        = {cvd/cvp:.2f}x")
print("=> SNR for an equal RELATIVE code change: the elasticity multiplies")
print("   signal and noise alike and therefore cancels, so the resolution")
print(f"   advantage of the prefill leg is exactly {cvd/cvp:.2f}x, NOT")
print(f"   {0.75*cvd/(0.25*cvp):.2f}x. The larger ratio is only the ratio of the")
print("   two legs' contributions to published-score noise.")
print()
print("per-arm draw count to reach 2 sigma on a given relative code change:")
print(f"{'change':>8} {'via decode leg':>15} {'via prefill leg':>16}")
for chg in (1.0, 0.5, 0.25, 0.1):
    nd = 2.0 * (2.0 * cvd / chg) ** 2 / 2.0
    npf = 2.0 * (2.0 * cvp / chg) ** 2 / 2.0
    print(f"{chg:>7.2f}% {math.ceil(nd):>15} {math.ceil(npf):>16}")

print()
print("prefill leg, pre vs post gate (the gate is decode-only: a drift check)")
mu_pp, sd_pp, cv_pp = stats([r[3] for r in PRE])
mu_qq, sd_qq, cv_qq = stats([r[3] for r in POST])
print(f"  pre  n=8 mean={mu_pp:.10f} cv={cv_pp:.4f}%")
print(f"  post n=4 mean={mu_qq:.10f} cv={cv_qq:.4f}%")
print(f"  shift = {(mu_qq/mu_pp-1)*100:+.4f}%  (decode-only change, so this is"
      " the leg's own drift+noise floor over 5 hours)")

print()
print("=" * 74)
print("3. WHERE THE LEADERBOARD NOISE LIVES")
print("=" * 74)
scores = [r[6] for r in allr]
mu_s, sd_s, cv_s = stats(scores)
print(f"published officialScore : n={len(scores)} mean={mu_s:.6f} sd={sd_s:.6f} cv={cv_s:.4f}%")
_, _, cv_bp = stats([r[5] for r in allr])
print(f"variance budget, in score cv terms:")
print(f"  candidate decode  0.75 x {cvd:.4f}% = {0.75*cvd:.4f}%")
print(f"  candidate prefill 0.25 x {cvp:.4f}% = {0.25*cvp:.4f}%")
print(f"  baseline prefill  0.25 x {cv_bp:.4f}% = {0.25*cv_bp:.4f}%")
quad = math.sqrt((0.75*cvd)**2 + (0.25*cvp)**2 + (0.25*cv_bp)**2)
print(f"  quadrature total                    = {quad:.4f}%")
print(f"  observed published cv               = {cv_s:.4f}%")
print(f"  baseline-prefill share of variance  = "
      f"{((0.25*cv_bp)**2)/quad**2*100:.1f}%")

print()
print("correlation check: is the baseline leg an exploitable control?")
bp = [r[5] for r in allr]
sc = [r[6] for r in allr]
r_bp = statistics.correlation(bp, sc)
cd = [r[2] for r in allr]
r_cd = statistics.correlation(cd, sc)
print(f"  corr(baseline_prefill, score)  = {r_bp:+.3f}")
print(f"  corr(candidate_decode, score)  = {r_cd:+.3f}")
