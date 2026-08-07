#!/usr/bin/env python3
"""Cross-session sigma of the CANDIDATE arm, which is the only arm ns touches.

ns = (0.013890/d)^0.75 * (0.0003845/p)^0.25 uses *fixed* normalisers, so it is
a single-arm statistic on the candidate.  Its cross-session error budget is
therefore the candidate arm's own day-to-day movement, measured here on rows
whose candidate code is effectively identical (clustered on both axes).
"""
import json, statistics as st
from collections import defaultdict

rows = json.load(open('/tmp/pr137_submit/feed.json'))

recs = []
for r in rows:
    m = r.get('officialMetrics') or {}
    bp = m.get('baseline_prefill_seconds_per_token')
    cp = m.get('prefill_seconds_per_token')
    bd = m.get('baseline_decode_seconds_per_token')
    cd = m.get('decode_seconds_per_token')
    ts = m.get('timestamp') or r.get('createdAt') or ''
    if not (bp and cp and bd and cd and ts):
        continue
    recs.append((ts[:10], ts, bp, cp, bd, cd))

recent = [r for r in recs if r[0] >= '2026-08-03']
mp = st.median([r[3] for r in recent])
md = st.median([r[5] for r in recent])
print(f'dominant recent candidate mode: prefill {mp:.9f}  decode {md:.9f}')

clust = [r for r in recs
         if abs(r[3] / mp - 1) <= 0.005 and abs(r[5] / md - 1) <= 0.003]
byday = defaultdict(list)
for r in clust:
    byday[r[0]].append(r)

NORM_D, NORM_P = 0.013890, 0.0003845
def ns(d, p):
    return (NORM_D / d) ** 0.75 * (NORM_P / p) ** 0.25
def nsd(d):
    return (NORM_D / d) ** 0.75

print()
print('rows with effectively identical candidate code, by day')
print(f'{"day":<12}{"n":>4}  {"cand decode":>13}{"cand prefill":>14}   {"ns":>10}{"nsd":>10}   {"base prefill":>14}')
days = []
for d in sorted(byday):
    g = byday[d]
    if len(g) < 4:
        continue
    cd = st.median([x[5] for x in g])
    cp = st.median([x[3] for x in g])
    bp = st.median([x[2] for x in g])
    days.append((d, len(g), cd, cp, bp, [x for x in g]))
    print(f'{d:<12}{len(g):>4}  {cd:>13.9f}{cp:>14.9f}   {ns(cd,cp):>10.6f}{nsd(cd):>10.6f}   {bp:>14.9f}')

def cvp(v):
    return 100.0 * st.stdev(v) / st.mean(v)

if len(days) >= 3:
    print()
    print(f'over these {len(days)} days:')
    for name, vals, floor_vals in (
        ('cand decode', [d[2] for d in days], 5),
        ('cand prefill', [d[3] for d in days], 3),
        ('base prefill', [d[4] for d in days], 2),
    ):
        obs = cvp(vals)
        per = [cvp([x[floor_vals] for x in byday[d[0]]]) / (len(byday[d[0]]) ** 0.5)
               for d in days]
        floor = st.mean(per)
        exc = (obs ** 2 - floor ** 2) ** 0.5 if obs > floor else 0.0
        print(f'  {name:<13} cv of daily medians {obs:6.3f}%   white-noise floor {floor:6.3f}%   excess {exc:6.3f}%')

    nsv = [ns(d[2], d[3]) for d in days]
    nsdv = [nsd(d[2]) for d in days]
    print(f'  {"ns":<13} cv of daily medians {cvp(nsv):6.3f}%')
    print(f'  {"nsd":<13} cv of daily medians {cvp(nsdv):6.3f}%')
