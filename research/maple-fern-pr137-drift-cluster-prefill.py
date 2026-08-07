#!/usr/bin/env python3
"""Sharper test of whether the day-scale prefill level shift is common mode.

The rho-over-11-days test in common_mode.py is uninformative because the
candidate axis is dominated by genuine code differences (detrended daily
spread 9.3% vs the 0.9% baseline signal we are trying to see).

Better probe: restrict to the dominant candidate-prefill cluster -- rows whose
candidate prefill code is effectively identical -- and watch how the baseline
and candidate daily medians move together *on the same rows*.  If a day-scale
machine level shift is common mode it must move both.
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
    recs.append((ts[:10], bp, cp, bd, cd))

print(f'rows with all four axes: {len(recs)}')

# dominant candidate-prefill cluster: mode of the last-3-day candidate prefill
recent = [r for r in recs if r[0] >= '2026-08-04']
med = st.median([r[2] for r in recent])
lo, hi = med * 0.995, med * 1.005
print(f'dominant candidate prefill mode (>=08-04) = {med:.9f}  band +-0.5% = [{lo:.9f},{hi:.9f}]')

clust = [r for r in recs if lo <= r[2] <= hi]
byday = defaultdict(list)
for r in clust:
    byday[r[0]].append(r)

print()
print('rows in the dominant candidate-prefill cluster, by day')
print(f'{"day":<12}{"n":>4}  {"base prefill":>14}{"cand prefill":>14}   {"base decode":>13}{"cand decode":>13}')
days = []
for d in sorted(byday):
    g = byday[d]
    if len(g) < 5:
        continue
    bp = st.median([x[1] for x in g])
    cp = st.median([x[2] for x in g])
    bd = st.median([x[3] for x in g])
    cd = st.median([x[4] for x in g])
    days.append((d, len(g), bp, cp, bd, cd))
    print(f'{d:<12}{len(g):>4}  {bp:>14.9f}{cp:>14.9f}   {bd:>13.9f}{cd:>13.9f}')

def cv(v):
    return 100.0 * st.stdev(v) / st.mean(v)

if len(days) >= 3:
    print()
    print(f'over these {len(days)} days, cv of the daily medians:')
    for name, idx in (('prefill', (2, 3)), ('decode', (4, 5))):
        b = cv([d[idx[0]] for d in days])
        c = cv([d[idx[1]] for d in days])
        print(f'  {name:<8} baseline {b:6.3f}%   candidate {c:6.3f}%   ratio cand/base {c/b:5.2f}')
    print()
    print('interpretation: a common-mode machine level shift moves both arms by')
    print('the same relative amount (ratio ~1).  A ratio << 1 on prefill means the')
    print('day-scale prefill shift lives in the baseline arm only.')

    # within-day white-noise expectation for the cluster medians
    print()
    print('white-noise floor for these daily medians (sd/sqrt(n), pooled):')
    for name, idx in (('prefill', (2, 3)), ('decode', (4, 5))):
        for arm, i in (('baseline', idx[0]), ('candidate', idx[1])):
            per = []
            for d in sorted(byday):
                g = byday[d]
                if len(g) < 5:
                    continue
                vals = [x[i - 1] for x in g]
                per.append(cv(vals) / (len(vals) ** 0.5))
            print(f'  {name:<8} {arm:<10} expected cv of daily median {st.mean(per):6.3f}%')
