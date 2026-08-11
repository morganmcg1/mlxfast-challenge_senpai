#!/usr/bin/env python3
"""Ratio-normalize post-fused-gate draws against a common reference.

normalized_i / normalized_j = (d_j/d_i)**0.75 * (p_j/p_i)**0.25
so every receipt can be placed on one scale once a single anchor is fixed.
Anchor: draw 1 (47fa4d85) ratio-normalized = 2.568950 (computed earlier).
"""
import math
import statistics

ANCHOR_NORM = 2.568950

draws = [
    # id, commit, decode, prefill, baseline_decode, baseline_prefill, officialScore
    ("47fa4d85", "9073a5d2", 0.00491371875, 0.00018780460546875,
     0.013860357421875, 0.00036736083984375, 2.57406646389338),
    ("db4fa283", "b0360ea9", 0.0049317789765625, 0.00018789616015625,
     0.0138430084609375, 0.00036737687109375, 2.56429884092213),
    ("fc7a5447", "c82b88f1", 0.0049159111328125, 0.000187699869140625,
     0.0138841650390625, 0.00037526692578125, 2.59063296787656),
    ("412aad2b", "6a5c7812", 0.0049425778046875, 0.000187438638671875,
     0.01387612109375, 0.000384062419921875, 2.59490580799781),
]

# HEAD-class (pre-gate) reference
HEAD_CLASS_NORM = 2.566890
PREGATE_DECODE = [0.0049487503203125, 0.0049312080078125, 0.0049282265625,
                  0.004930751296875, 0.00490711328125, 0.004897051109375,
                  0.0049124921875, 0.0049052083359375]

d0, p0 = draws[0][2], draws[0][3]

print("post-fused-gate draws, ratio-normalized to a common reference")
print(f"{'id':10} {'decode':>18} {'prefill':>20} {'official':>16} {'normalized':>11} {'draw':>9} {'vs HEAD':>9}")
norms = []
for did, commit, d, p, bd, bp, score in draws:
    norm = ANCHOR_NORM * (d0 / d) ** 0.75 * (p0 / p) ** 0.25
    norms.append(norm)
    draw_factor = score / norm
    vs_head = (norm / HEAD_CLASS_NORM - 1.0) * 100.0
    print(f"{did:10} {d:>18.16f} {p:>20.20f} {score:>16.8f} "
          f"{norm:>11.6f} {draw_factor:>9.6f} {vs_head:>+8.3f}%")

mean_norm = statistics.fmean(norms)
print()
print(f"mean normalized over {len(norms)} post-gate draws : {mean_norm:.6f}")
print(f"HEAD-class (pre-gate) normalized             : {HEAD_CLASS_NORM:.6f}")
print(f"pooled shift vs HEAD-class                   : "
      f"{(mean_norm / HEAD_CLASS_NORM - 1.0) * 100.0:+.3f}%")

# decode-leg comparison: post-gate decode vs pre-gate pool
mu = statistics.fmean(PREGATE_DECODE)
sd = statistics.stdev(PREGATE_DECODE)
print()
print(f"pre-gate decode pool n={len(PREGATE_DECODE)} mean={mu:.10f} sd={sd:.10f} cv={sd/mu*100:.4f}%")
for did, commit, d, p, bd, bp, score in draws:
    print(f"  {did}: decode {d:.13f}  z vs pre-gate pool = {(d - mu) / sd:+.3f}")
post_d = [x[2] for x in draws]
mu_post = statistics.fmean(post_d)
print(f"  post-gate decode mean = {mu_post:.10f}  "
      f"delta vs pre-gate = {(mu_post/mu - 1.0)*100:+.4f}% (negative = faster)")

# power: single ranked normalized sd = 0.370%
SD_RANKED = 0.370
for n in (2, 4, 8, 16, 32):
    print(f"  SE of mean normalized at n={n:2d}: {SD_RANKED/math.sqrt(n):.3f}%")

# what luck is now required for the crown
CROWN = 2.61650354381456
print()
print(f"crown score                    : {CROWN:.8f}")
print(f"required luck factor at n=2 mean normalized {mean_norm:.6f} : "
      f"{CROWN/mean_norm:.6f}")
print(f"required luck factor at HEAD-class {HEAD_CLASS_NORM:.6f}    : "
      f"{CROWN/HEAD_CLASS_NORM:.6f}")
