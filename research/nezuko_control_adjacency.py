#!/usr/bin/env python3
"""Does a *same-session* control actually buy anything on the ranked M5?

Advisor feedback #4 established a team-wide standing rule: every arm needs a
same-session byte-exact control, and "this costs a receipt; it is worth it".
That rule is only worth a receipt if receipt noise carries a session-common
component -- i.e. if two draws taken close together in time agree better than
two draws taken far apart.

`research/nezuko_receipt_noise_structure.py` already showed the *baseline* arm
is white (flat variogram, lag-1 r1 = +0.037 +/- 0.030). The obvious and fair
objection is that a contrast also contains the *candidate* arm, which that
script cannot see because candidate content varies across rows.

This script closes that gap using the only object in the corpus that is a real
two-draw contrast between near-identical candidates: the Instrument-B pairs.
Two candidates are paired when their candidate-side decode and prefill times
agree to 5e-4 / 5e-3 relative, which is far tighter than the session noise, so
the pair is a de-facto replicate. Each such pair has an essentially arbitrary
time gap, from minutes to weeks.

The test is a single question:

    does the paired delta sd grow with the pair's time gap?

  - flat in gap  => noise is white on the *contrast* itself, adjacency buys
                    nothing, and a dedicated same-session control receipt is
                    not recoverable spend;
  - grows in gap => adjacency genuinely helps and the standing rule is right.

Note the selection effect runs *against* the "flat" conclusion: if a
session-common component existed, temporally adjacent candidates would agree
better and would therefore be over-represented among pairs that pass the
matching threshold. A null here is thus conservative.

No GPU, no repo state. Reads a cached submissions JSON if given one on argv,
otherwise fetches the benchmark listing.
"""
import json
import math
import os
import random
import statistics as st
import subprocess
import sys
from datetime import datetime

BENCHMARK_ID = '1854efdf-feba-4773-bae9-b80520881a74'
MY_HARNESS = '18d98ccb4e65cb76e6edb4ffec6e3b3a4244953b1e0ef4041a53d40a3058d913'
MY_GOLDEN = 'be7738fccd6a28807ae7d18c038cbbc9e1b05dab26b99b2f247358fdc67fcf71'

# Instrument-B matching thresholds, identical to the noise-floor script.
MATCH_DEC = 5e-4
MATCH_PRE = 5e-3


def load():
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as fh:
            d = json.load(fh)
        return d.get('submissions', d) if isinstance(d, dict) else d
    tok = (os.environ.get('MLXFAST_API_TOKEN')
           or os.environ.get('YUKON_API_TOKEN')
           or os.environ.get('SUPABASE_ACCESS_TOKEN'))
    if not tok:
        sys.exit('NO_TOKEN_FOUND: set MLXFAST_API_TOKEN')
    url = f'https://api.mlx.fast/api/benchmarks/{BENCHMARK_ID}/submissions'
    d = json.loads(subprocess.run(
        ['curl', '-fsS', '-H', f'Authorization: Bearer {tok}', url],
        capture_output=True, text=True, check=True).stdout)
    return d.get('submissions', d) if isinstance(d, dict) else d


def ts(row):
    return datetime.fromisoformat(row['createdAt'].replace('Z', '+00:00'))


def sd_ci(vals):
    """Two-sided 95% interval on a population sd, chi-square-free normal
    approximation: se(sd) ~= sd / sqrt(2n)."""
    n = len(vals)
    s = st.pstdev(vals)
    se = s / math.sqrt(2 * n) if n > 1 else float('nan')
    return s, se


rows = load()
scored = []
for r in rows:
    m = r.get('officialMetrics') or {}
    if not m or not m.get('passed_correctness'):
        continue
    if not m.get('decode_seconds_per_token'):
        continue
    if not m.get('baseline_decode_seconds_per_token'):
        continue
    scored.append(r)

same = [r for r in scored
        if (r['officialMetrics'].get('harness_hash') == MY_HARNESS
            and r['officialMetrics'].get('golden_hash') == MY_GOLDEN)]
if len(same) < 8:
    same = scored

print(f'scored rows                     : {len(scored)}')
print(f'same harness_hash + golden_hash : {len(same)}')

hi = [r for r in same if r['officialMetrics']['decode_speedup'] > 2.5]
hi.sort(key=lambda r: r['officialMetrics']['decode_seconds_per_token'])

pairs = []
for a, b in zip(hi, hi[1:]):
    ma, mb = a['officialMetrics'], b['officialMetrics']
    dd = abs(ma['decode_seconds_per_token'] / mb['decode_seconds_per_token'] - 1)
    dp = abs(ma['prefill_seconds_per_token'] / mb['prefill_seconds_per_token'] - 1)
    if dd < MATCH_DEC and dp < MATCH_PRE:
        gap_h = abs((ts(b) - ts(a)).total_seconds()) / 3600.0
        d_ds = 100 * (mb['decode_speedup'] / ma['decode_speedup'] - 1)
        d_sc = 100 * (b['officialScore'] / a['officialScore'] - 1)
        pairs.append({'gap_h': gap_h, 'd_ds': d_ds, 'd_sc': d_sc,
                      'a': a['id'][:8], 'b': b['id'][:8]})

print(f'frontier-class receipts (ds>2.5): {len(hi)}')
print(f'near-identical candidate pairs  : {len(pairs)}')
if len(pairs) < 40:
    sys.exit('too few pairs to bin')

gaps = sorted(p['gap_h'] for p in pairs)
print(f'pair time gap (hours)           : min {gaps[0]:.3f}  '
      f'p25 {gaps[len(gaps)//4]:.2f}  median {gaps[len(gaps)//2]:.2f}  '
      f'p75 {gaps[3*len(gaps)//4]:.2f}  max {gaps[-1]:.1f}')

BINS = [(0.0, 0.5, '< 30 min  (same session)'),
        (0.5, 2.0, '30 min - 2 h'),
        (2.0, 12.0, '2 h - 12 h'),
        (12.0, 72.0, '12 h - 3 d'),
        (72.0, 1e9, '> 3 d')]

for key, label in (('d_ds', 'decode_speedup'), ('d_sc', 'officialScore')):
    allv = [p[key] for p in pairs]
    s_all, se_all = sd_ci(allv)
    print()
    print(f'=== paired {label} delta sd vs pair time gap ===')
    print(f'  pooled : n {len(allv):4d}  sd {s_all:.4f} %  '
          f'(se {se_all:.4f} %)  mean {st.fmean(allv):+.4f} %')
    print(f'  {"gap bin":<26} {"n":>4} {"sd %":>9} {"se %":>8} '
          f'{"vs pooled":>10} {"z":>7}')
    for lo, hi_, label_b in BINS:
        v = [p[key] for p in pairs if lo <= p['gap_h'] < hi_]
        if len(v) < 8:
            print(f'  {label_b:<26} {len(v):>4}      (too few)')
            continue
        s, se = sd_ci(v)
        ratio = 100 * s / s_all
        # z of this bin's sd against the pooled sd, using the bin's own se
        z = (s - s_all) / se
        print(f'  {label_b:<26} {len(v):>4} {s:>9.4f} {se:>8.4f} '
              f'{ratio:>9.1f}% {z:>+7.2f}')

    # trend test: correlation of |delta| with log10(gap)
    x = [math.log10(max(p['gap_h'], 1e-3)) for p in pairs]
    y = [abs(p[key]) for p in pairs]
    mx, my = st.fmean(x), st.fmean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    r = sxy / math.sqrt(sxx * syy)
    n = len(x)
    t = r * math.sqrt((n - 2) / max(1 - r * r, 1e-12))
    slope = sxy / sxx
    print(f'  trend  : corr(|delta|, log10 gap_h) r {r:+.4f}  t {t:+.2f}  '
          f'(n {n}, |t|>1.96 => significant)')
    print(f'           slope {slope:+.4f} % per decade of gap')

    # what an age difference actually costs, from the well-powered slope
    print(f'           => a 4-decade age difference (1 min vs 1 week) moves '
          f'|delta| by {4 * slope:+.4f} % against a {s_all:.4f} % sd '
          f'({400 * slope / s_all:+.1f} %)')

    # the decision-relevant contrast: same-session vs everything else.
    # The <30 min bin is small, so report a bootstrap interval rather than a
    # normal approximation -- an underpowered point estimate must not be
    # quoted as if it settled the question.
    for cut, cname in ((0.5, '<30 min'), (2.0, '<2 h')):
        near = [p[key] for p in pairs if p['gap_h'] < cut]
        far = [p[key] for p in pairs if p['gap_h'] >= cut]
        if len(near) < 8 or len(far) < 8:
            continue
        sn = st.pstdev(near)
        sf = st.pstdev(far)
        ratio = sn / sf
        rnd = random.Random(20260807)
        boot = []
        for _ in range(20000):
            bn = [near[rnd.randrange(len(near))] for _ in near]
            bf = [far[rnd.randrange(len(far))] for _ in far]
            sbf = st.pstdev(bf)
            if sbf > 0:
                boot.append(st.pstdev(bn) / sbf)
        boot.sort()
        lo = boot[int(0.025 * len(boot))]
        hi_b = boot[int(0.975 * len(boot))]
        print(f'  RULE   : adjacent {cname} sd {sn:.4f} % (n {len(near)}) '
              f'vs rest sd {sf:.4f} % (n {len(far)})')
        print(f'           sd ratio {ratio:.3f}  bootstrap 95% '
              f'[{lo:.3f}, {hi_b:.3f}]')
        print(f'           => adjacency buys {100 * (1 - ratio):+.1f} % of '
              f'contrast sd, 95% [{100 * (1 - hi_b):+.1f} %, '
              f'{100 * (1 - lo):+.1f} %]')
