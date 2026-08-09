#!/usr/bin/env python3
"""Checks raised by the adversarial statistical review of section 9.

1. Attenuation: how much of the candidate spread in each correlation estimator
   is measurement noise rather than real code differences? A correlation
   estimated on a sample whose candidate variance is dominated by code changes
   is attenuated by sd_noise / sd_total and cannot detect even a large rho.
2. Break-even rho: pairing (dividing by the same-session baseline) only reduces
   variance if rho exceeds CV(bl) / (2 CV(cand)).
3. Empirical floor-trip rate: is the normal-theory "~6 % of the time" claim
   supported by the actual 1184-receipt baseline distribution?

Usage: python3 critique_checks.py receipts-latest.json
"""
import json
import math
import statistics as st
import sys


def load(path):
    out = []
    for r in json.load(open(path)):
        vals = (r.get('cand_dec'), r.get('cand_pre'), r.get('bl_dec'), r.get('bl_pre'))
        if not all(isinstance(x, (int, float)) and x > 0 for x in vals):
            continue
        d, p, bd, bp = vals
        out.append({'ts': r['ts'], 'solver': r.get('solver', '?'),
                    'commit': r.get('commit'),
                    'dec': d * 1e6, 'pre': p * 1e6,
                    'bl_dec': bd * 1e6, 'bl_pre': bp * 1e6})
    out.sort(key=lambda r: r['ts'] or '')
    return out


def cv(v):
    return 100 * st.stdev(v) / st.mean(v)


def main():
    rows = load(sys.argv[1])
    print('receipts %d' % len(rows))

    # candidate-side noise CV measured from our machine-code-identical nulls
    import glob
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    nd, np_ = [], []
    for f in sorted(glob.glob(os.path.join(here, 'receipts', 'null-*.json'))):
        s = json.load(open(f))
        s = s.get('submission', s)
        m = s['officialMetrics']
        nd.append(m['decode_seconds_per_token'] * 1e6)
        np_.append(m['prefill_seconds_per_token'] * 1e6)
    cv_noise_dec, cv_noise_pre = cv(nd), cv(np_)
    cv_bl_dec = cv([r['bl_dec'] for r in rows])
    cv_bl_pre = cv([r['bl_pre'] for r in rows])
    print('null-based candidate noise CV: decode %.4f%% (n=%d)  prefill %.4f%%'
          % (cv_noise_dec, len(nd), cv_noise_pre))
    print('corpus baseline CV:            decode %.4f%%          prefill %.4f%%'
          % (cv_bl_dec, cv_bl_pre))

    print()
    print('=' * 78)
    print('1. ATTENUATION OF EACH CORRELATION ESTIMATOR')
    print('=' * 78)
    print('   Var(cand) = Var(code) + Var(noise). A sample correlation between')
    print('   candidate and baseline can only see the noise part, so it is')
    print('   attenuated by  a = sd_noise / sd_total.  An observed |r| <= 0.08')
    print('   therefore only bounds the true noise correlation by |rho| <= 0.08/a.')

    # (a) solver-day de-meaned
    groups = {}
    for r in rows:
        day = (r['ts'] or '')[:10]
        groups.setdefault((r['solver'], day), []).append(r)
    resid = [x for g in groups.values() if len(g) >= 5
             for x in [(r['dec'] - st.mean([q['dec'] for q in g])) for r in g]]
    sd_tot_a = st.pstdev(resid)
    sd_noise_dec = cv_noise_dec / 100 * st.mean([r['dec'] for r in rows])
    print()
    print('   (a) solver-day de-meaned: sd(cand resid) = %.1f us' % sd_tot_a)
    print('       sd(noise) ~ %.1f us  =>  attenuation a = %.3f' %
          (sd_noise_dec, sd_noise_dec / sd_tot_a))
    print('       |r|<=0.08 only implies |rho| <= %.2f  -> UNINFORMATIVE'
          % min(1.0, 0.08 / (sd_noise_dec / sd_tot_a)))

    # (c) near-replicate groups, cand CV < 0.5 %
    for thresh in (0.5, 0.6):
        sub = [g for g in groups.values() if len(g) >= 3 and
               cv([r['dec'] for r in g]) < thresh]
        pts = [x for g in sub for x in
               [(r['dec'] - st.mean([q['dec'] for q in g])) for r in g]]
        if not pts:
            continue
        sd_c = st.pstdev(pts)
        a = min(1.0, sd_noise_dec / sd_c)
        print()
        print('   (c) near-replicate groups, cand CV < %.1f%%: %d groups, %d pts'
              % (thresh, len(sub), len(pts)))
        print('       sd(cand resid) = %.2f us  =>  attenuation a = %.3f'
              % (sd_c, a))
        print('       observed r ~ -0.018  =>  |rho| <= %.2f' % (0.08 / a))

    print()
    print('=' * 78)
    print('2. BREAK-EVEN CORRELATION FOR PAIRING TO PAY')
    print('=' * 78)
    print('   Var(log ratio) = CV(cand)^2 + CV(bl)^2 - 2 rho CV(cand) CV(bl).')
    print('   Pairing beats the raw candidate only if rho > CV(bl)/(2 CV(cand)).')
    for name, cc, cb in (('decode', cv_noise_dec, cv_bl_dec),
                         ('prefill', cv_noise_pre, cv_bl_pre)):
        be = cb / (2 * cc)
        print('   %-8s CV(cand) %.4f%%  CV(bl) %.4f%%  break-even rho = %.3f  %s'
              % (name, cc, cb, be,
                 '(IMPOSSIBLE, > 1)' if be > 1 else ''))

    print()
    print('=' * 78)
    print('3. EMPIRICAL PREFILL FLOOR-TRIP RATE')
    print('=' * 78)
    bp = [r['bl_pre'] for r in rows]
    mu = st.mean(bp)
    rel = sorted(x / mu for x in bp)
    print('   bl_pre/mean: min %.4f  p1 %.4f  p5 %.4f  p50 %.4f  max %.4f'
          % (rel[0], rel[len(rel) // 100], rel[len(rel) // 20],
             rel[len(rel) // 2], rel[-1]))
    for true_su in (0.98, 0.97, 0.96):
        need = 0.95 / true_su  # bl_pre must fall to this fraction of its mean
        emp = sum(1 for x in rel if x < need) / len(rel)
        z = (need - 1) / (cv_bl_pre / 100)
        norm = 0.5 * (1 + math.erf(z / math.sqrt(2)))
        print('   true prefill speedup %.2f -> trips 0.95 floor if bl_pre < %.4f'
              ' of mean:  empirical %.2f%%   normal-theory %.2f%%'
              % (true_su, need, 100 * emp, 100 * norm))
    print('   (baseline-only; ignores candidate-side noise, which is ~0.1%% CV)')

    print()
    print('=' * 78)
    print('4. CHI-SQUARE UNCERTAINTY ON A SMALL-n SIGMA')
    print('=' * 78)
    print('   Required n scales as sigma^2, so the CI on sigma^2 maps directly')
    print('   onto the receipt-count table.')
    # chi2 0.025/0.975 quantiles for small df
    q = {2: (0.0506, 7.378), 3: (0.2158, 9.348), 4: (0.4844, 11.143),
         5: (0.8312, 12.833), 7: (1.690, 16.013)}
    for df in (2, 3, 4):
        lo, hi = q[df]
        # CI on sigma^2: (df s^2 / chi2_hi, df s^2 / chi2_lo)
        print('   n=%d (df=%d): sigma in [%.2f, %.2f] x s ; required n scales by'
              ' [%.2f, %.1f]'
              % (df + 1, df, math.sqrt(df / hi), math.sqrt(df / lo),
                 df / hi, df / lo))


if __name__ == '__main__':
    main()
