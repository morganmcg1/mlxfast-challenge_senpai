#!/usr/bin/env python3
"""Is the drift cluster of 13.12 the leading frontier, or a slower plateau?

And can the same drift measurement be made on the frontier family itself
(candidate decode ~4.9084 ms, which is where 97a5090c and our candidate live)?
"""
import json, statistics as st
from collections import defaultdict

rows = json.load(open('/tmp/pr137_submit/feed.json'))
recs = []
for r in rows:
    m = r.get('officialMetrics') or {}
    cd, cp = m.get('decode_seconds_per_token'), m.get('prefill_seconds_per_token')
    bp = m.get('baseline_prefill_seconds_per_token')
    ts = m.get('timestamp') or r.get('createdAt') or ''
    if cd and cp and bp and ts:
        recs.append((ts[:10], cd, cp, bp))

PROMOTED = 0.0049083720703125
DOMINANT = 0.005111863
print(f'frontier (97a5090c) candidate decode {PROMOTED*1000:.4f} ms')
print(f'dominant cluster of 13.12            {DOMINANT*1000:.4f} ms'
      f'   -> {(DOMINANT/PROMOTED-1)*100:+.2f} % slower, so NOT the frontier')
print()

# histogram of candidate decode over the last week, 0.5% bins
recent = [r for r in recs if r[0] >= '2026-08-01']
bins = defaultdict(int)
for r in recent:
    bins[round(r[1] * 1000, 2)] += 1
print('candidate decode ms histogram (>=08-01, 0.01 ms bins), top 12:')
for k, v in sorted(bins.items(), key=lambda kv: -kv[1])[:12]:
    mark = ''
    if abs(k / (PROMOTED * 1000) - 1) < 0.003:
        mark = '  <-- frontier family'
    if abs(k / (DOMINANT * 1000) - 1) < 0.003:
        mark = '  <-- 13.12 cluster'
    print(f'  {k:7.2f} ms  n={v:4d}{mark}')
print()

NORM_D, NORM_P = 0.013890, 0.0003845
def cvp(v):
    return 100.0 * st.stdev(v) / st.mean(v)

for label, centre, tol in (('frontier family', PROMOTED, 0.004),
                           ('13.12 cluster', DOMINANT, 0.003)):
    clust = [r for r in recs if abs(r[1] / centre - 1) <= tol]
    byday = defaultdict(list)
    for r in clust:
        byday[r[0]].append(r)
    days = [(d, g) for d, g in sorted(byday.items()) if len(g) >= 4]
    print(f'{label}: {len(clust)} rows, {len(days)} days with n>=4')
    if len(days) < 3:
        print('  too few days for a drift estimate')
        print()
        continue
    med_d = [st.median([x[1] for x in g]) for _, g in days]
    med_p = [st.median([x[2] for x in g]) for _, g in days]
    med_b = [st.median([x[3] for x in g]) for _, g in days]
    for d, g in days:
        print(f'    {d}  n={len(g):3d}  decode {st.median([x[1] for x in g])*1000:.5f} ms'
              f'  prefill {st.median([x[2] for x in g])*1e6:.3f} us'
              f'  base prefill {st.median([x[3] for x in g])*1e6:.3f} us')
    for name, med, idx in (('cand decode', med_d, 1),
                           ('cand prefill', med_p, 2),
                           ('base prefill', med_b, 3)):
        obs = cvp(med)
        floor = st.mean([cvp([x[idx] for x in g]) / (len(g) ** 0.5) for _, g in days])
        exc = (obs ** 2 - floor ** 2) ** 0.5 if obs > floor else 0.0
        print(f'  {name:<13} daily-median cv {obs:6.3f}%  floor {floor:6.3f}%  excess {exc:6.3f}%')
    nsv = [(NORM_D / d) ** 0.75 * (NORM_P / p) ** 0.25 for d, p in zip(med_d, med_p)]
    print(f'  {"ns":<13} daily-median cv {cvp(nsv):6.3f}%')
    print()
