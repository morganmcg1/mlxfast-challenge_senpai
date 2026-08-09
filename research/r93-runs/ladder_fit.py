#!/usr/bin/env python3
"""Arm B regression: microseconds of decode per injected empty dispatch.

Reads every receipt in receipts/ plus manifest.json (which maps submission-id
prefix -> K) and fits decode us/token on K three ways:

  OLS        equal weights
  WLS        weights 1/mu^2, the right weighting if noise is multiplicative
             (section 9.5 of RESULTS.md finds CV roughly constant in mean)
  segments   pairwise marginal slopes, which need no linearity assumption

It also runs a lack-of-fit F-test against the pure-error estimate from the
K=0 replicates, and reports the prefill internal control (prefill must not
move, since the injection is decode-only).

Usage: python3 ladder_fit.py
"""
import glob
import json
import math
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))

# t(0.975, df)
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
        7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131,
        20: 2.086, 30: 2.042}

# F(0.95, df1, df2) for the small (df1, df2) pairs this design can produce
FCRIT95 = {(1, 2): 18.51, (1, 3): 10.13, (1, 4): 7.71, (1, 5): 6.61,
           (1, 6): 5.99, (2, 2): 19.00, (2, 3): 9.55, (2, 4): 6.94,
           (2, 5): 5.79, (2, 6): 5.14, (3, 3): 9.28, (3, 4): 6.59,
           (3, 5): 5.41, (3, 6): 4.76}


def t975(df):
    if df <= 0:
        return float('nan')
    keys = sorted(T975)
    for k in keys:
        if df <= k:
            return T975[k]
    return 1.96


def load():
    manifest = json.load(open(os.path.join(HERE, 'manifest.json')))
    ladder = manifest.get('ladder', {})
    pts = []
    for path in sorted(glob.glob(os.path.join(HERE, 'receipts', '*.json'))):
        raw = json.load(open(path))
        sub = raw.get('submission', raw)
        m = sub.get('officialMetrics') or {}
        dec = m.get('decode_seconds_per_token')
        pre = m.get('prefill_seconds_per_token')
        if dec is None:
            continue
        sid = (sub.get('id') or '')[:8]
        name = os.path.basename(path)[:-5]
        k = 0 if name.startswith('null') else ladder.get(sid)
        if k is None:
            print('  ! no K for %s (%s); skipping' % (name, sid))
            continue
        pts.append({'name': name, 'sid': sid, 'K': k,
                    'dec': dec * 1e6, 'pre': pre * 1e6,
                    'bl_dec': m.get('baseline_decode_seconds_per_token', 0) * 1e6,
                    'bl_pre': m.get('baseline_prefill_seconds_per_token', 0) * 1e6})
    pts.sort(key=lambda p: (p['K'], p['name']))
    return pts


def fit(xs, ys, ws=None):
    n = len(xs)
    if ws is None:
        ws = [1.0] * n
    sw = sum(ws)
    mx = sum(w * x for w, x in zip(ws, xs)) / sw
    my = sum(w * y for w, y in zip(ws, ys)) / sw
    sxx = sum(w * (x - mx) ** 2 for w, x in zip(ws, xs))
    sxy = sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, xs, ys))
    b = sxy / sxx
    a = my - b * mx
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    df = n - 2
    s2 = sum(w * r * r for w, r in zip(ws, resid)) / df
    se_b = math.sqrt(s2 / sxx)
    return a, b, se_b, resid, df, math.sqrt(s2)


def main():
    pts = load()
    print('=' * 78)
    print('ARM B LADDER: %d receipts' % len(pts))
    print('=' * 78)
    print('  %-14s %-9s %5s %12s %10s %12s' %
          ('marker', 'sid', 'K', 'decode us', 'prefill us', 'bl_dec us'))
    for p in pts:
        print('  %-14s %-9s %5d %12.3f %10.4f %12.3f' %
              (p['name'], p['sid'], p['K'], p['dec'], p['pre'], p['bl_dec']))

    xs = [p['K'] for p in pts]
    ys = [p['dec'] for p in pts]

    print()
    print('-' * 78)
    print('1. OLS (equal weights)')
    a, b, se, resid, df, s = fit(xs, ys)
    t = t975(df)
    print('   slope    = %.4f us/dispatch   se %.4f   95%% CI [%.4f, %.4f]  (df=%d)'
          % (b, se, b - t * se, b + t * se, df))
    print('   intercept= %.3f us            residual s = %.3f us' % (a, s))
    for p, r in zip(pts, resid):
        print('     K=%-5d %-14s resid %+8.2f us' % (p['K'], p['name'], r))

    print()
    print('-' * 78)
    print('2. WLS, weights 1/mu^2 (multiplicative-noise model, section 9.5)')
    ws = [1.0 / (y * y) for y in ys]
    aw, bw, sew, residw, dfw, sw_ = fit(xs, ys, ws)
    tw = t975(dfw)
    print('   slope    = %.4f us/dispatch   se %.4f   95%% CI [%.4f, %.4f]'
          % (bw, sew, bw - tw * sew, bw + tw * sew))
    print('   intercept= %.3f us' % aw)
    print('   shift vs OLS: %+.4f us/dispatch (%+.2f%%)' % (bw - b, 100 * (bw - b) / b))

    print()
    print('-' * 78)
    print('3. Segment marginals (no linearity assumption)')
    byk = {}
    for p in pts:
        byk.setdefault(p['K'], []).append(p['dec'])
    ks = sorted(byk)
    means = {k: st.mean(v) for k, v in byk.items()}
    for k in ks:
        print('   K=%-5d n=%d  mean %10.3f us%s' %
              (k, len(byk[k]), means[k],
               ('  sd %.3f' % st.stdev(byk[k])) if len(byk[k]) > 1 else ''))
    for i in range(len(ks) - 1):
        k0, k1 = ks[i], ks[i + 1]
        print('   K %4d -> %4d : %.4f us/dispatch' %
              (k0, k1, (means[k1] - means[k0]) / (k1 - k0)))

    print()
    print('-' * 78)
    print('4. Lack-of-fit F-test (pure error from replicated K levels)')
    pe_ss, pe_df = 0.0, 0
    for k in ks:
        v = byk[k]
        if len(v) > 1:
            mu = st.mean(v)
            pe_ss += sum((x - mu) ** 2 for x in v)
            pe_df += len(v) - 1
    sse = sum(r * r for r in resid)
    lof_ss = sse - pe_ss
    lof_df = len(pts) - 2 - pe_df
    if pe_df > 0 and lof_df > 0:
        F = (lof_ss / lof_df) / (pe_ss / pe_df)
        print('   pure error  SS %.2f  df %d  (s = %.3f us)' %
              (pe_ss, pe_df, math.sqrt(pe_ss / pe_df)))
        print('   lack of fit SS %.2f  df %d' % (lof_ss, lof_df))
        crit = FCRIT95.get((lof_df, pe_df))
        if crit:
            print('   F(%d,%d) = %.3f   crit(0.95) = %.2f   -> %s' %
                  (lof_df, pe_df, F, crit,
                   'NO detectable curvature' if F < crit else 'CURVATURE DETECTED'))
        else:
            print('   F(%d,%d) = %.3f' % (lof_df, pe_df, F))
        print('   Note: with this little replication the test has very low power.')
        print('   "no detectable curvature" is NOT evidence of linearity; the')
        print('   segment marginals in block 3 are the honest statement.')
    else:
        print('   not enough replication (pe_df=%d, lof_df=%d)' % (pe_df, lof_df))

    print()
    print('-' * 78)
    print('5. Prefill internal control (injection is decode-only)')
    nulls = [p['pre'] for p in pts if p['K'] == 0]
    rungs = [p['pre'] for p in pts if p['K'] > 0]
    if nulls and rungs:
        mn, mr = st.mean(nulls), st.mean(rungs)
        print('   K=0   n=%d mean %.4f us%s' %
              (len(nulls), mn, ('  sd %.4f' % st.stdev(nulls)) if len(nulls) > 1 else ''))
        print('   K>0   n=%d mean %.4f us%s' %
              (len(rungs), mr, ('  sd %.4f' % st.stdev(rungs)) if len(rungs) > 1 else ''))
        print('   shift %+.4f us = %+.4f%%' % (mr - mn, 100 * (mr - mn) / mn))
        if len(nulls) > 1 and len(rungs) > 1:
            sp = math.sqrt(((len(nulls) - 1) * st.stdev(nulls) ** 2 +
                            (len(rungs) - 1) * st.stdev(rungs) ** 2) /
                           (len(nulls) + len(rungs) - 2))
            se_d = sp * math.sqrt(1 / len(nulls) + 1 / len(rungs))
            dfd = len(nulls) + len(rungs) - 2
            print('   t = %.3f on %d df (|t|>%.3f would be significant)' %
                  ((mr - mn) / se_d, dfd, t975(dfd)))

    print()
    print('-' * 78)
    print('6. Same-session baselines (health check, not a covariate)')
    bl = [p['bl_dec'] for p in pts]
    print('   bl_dec n=%d mean %.3f us sd %.3f  CV %.4f%%' %
          (len(bl), st.mean(bl), st.stdev(bl), 100 * st.stdev(bl) / st.mean(bl)))
    bp = [p['bl_pre'] for p in pts]
    print('   bl_pre n=%d mean %.3f us sd %.3f  CV %.4f%%' %
          (len(bp), st.mean(bp), st.stdev(bp), 100 * st.stdev(bp) / st.mean(bp)))


if __name__ == '__main__':
    main()
