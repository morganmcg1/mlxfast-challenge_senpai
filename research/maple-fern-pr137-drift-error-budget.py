#!/usr/bin/env python3
"""Error budget for a CROSS-SESSION paired comparison (our receipt vs 97a5090c).

Within-session sigmas come from the two identical-tree replicate triplets
(section 13.11).  Cross-session excess comes from common_mode3.py, measured on
rows whose candidate code is effectively identical across four days.
"""
import math

# within-session, identical-tree triplets, 4 dof (section 13.11)
W_SCORE, W_NS, W_NSD = 0.559, 0.138, 0.148

# cross-session excess, candidate arm, identical candidate code (common_mode3)
EX_CAND_DECODE = 0.100      # upper bound: includes cluster-composition drift
EX_CAND_PREFILL = 0.017
EX_BASE_PREFILL = 0.715

EFFECT = 0.933              # full M4->M5 transfer, in percent of ns
GO_MARGIN = 0.242           # GO threshold above the anchor, percent
KILL_MARGIN = -0.243

def q(*xs):
    return math.sqrt(sum(x * x for x in xs))

ex_ns = 0.75 * EX_CAND_DECODE
ex_nsd = 0.75 * EX_CAND_DECODE
ex_score = 0.25 * EX_BASE_PREFILL      # officialScore's only *uncancelled* term

print('cross-session excess implied by the candidate-arm drift')
print(f'  ns   0.75 x {EX_CAND_DECODE:.3f} = {ex_ns:.3f}%   (measured directly: 0.076%)')
print(f'  nsd  0.75 x {EX_CAND_DECODE:.3f} = {ex_nsd:.3f}%   (measured directly: 0.081%)')
print(f'  officialScore 0.25 x {EX_BASE_PREFILL:.3f} = {ex_score:.3f}%  (baseline prefill, NOT common mode)')
print()

print(f'{"axis":<16}{"within":>9}{"x-sess":>9}{"total":>9}{"paired":>9}{"GO":>8}{"effect":>9}{"sd on t":>9}')
for name, w, ex in (('ns', W_NS, ex_ns),
                    ('nsd', W_NSD, ex_nsd),
                    ('officialScore', W_SCORE, ex_score)):
    tot = q(w, ex)
    pair = tot * math.sqrt(2)
    print(f'{name:<16}{w:>8.3f}%{ex:>8.3f}%{tot:>8.3f}%{pair:>8.3f}%'
          f'{GO_MARGIN/pair:>7.2f}s{EFFECT/pair:>8.2f}s{pair/EFFECT:>9.3f}')

pair_ns = q(W_NS, ex_ns) * math.sqrt(2)
pair_score = q(W_SCORE, ex_score) * math.sqrt(2)
print()
print(f'ns is {pair_score/pair_ns:.2f}x tighter than officialScore cross-session'
      f' (was {W_SCORE/W_NS:.2f}x within-session)')
print()
print('separation of the two pre-registered transfer hypotheses on ns:')
for t0, t1 in ((0.50, 1.00), (0.50, 0.75)):
    print(f'  t={t0:.2f} vs t={t1:.2f}: {(t1-t0)*EFFECT/pair_ns:.2f} sigma')
