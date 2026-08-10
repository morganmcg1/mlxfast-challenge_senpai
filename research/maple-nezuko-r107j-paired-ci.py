#!/usr/bin/env python3
"""maple-nezuko-r107j-paired-ci.py -- paired-difference CI + power curve for the
R107-J' local decode certification instrument.

Reads the TSV emitted by research/maple-nezuko-r107j-certify.sh and prints, for
every non-reference arm, the blocked paired-difference CI95 in three channels:

    (a) M4 us/token   -- the raw measured channel on THIS host
    (b) relative decode %  -- (a) / reference level
    (c) % of cs       -- (a) x k x 0.015228, the promoted M5 census channel

Channel (c) is the only channel the scoreboard cares about and it is the only
channel that needs an assumption. k is the M4->M5 transfer factor and it is
NOT a ratio of two measured levels (guard rail 2). Two priced values are
carried side by side per rule 105.12:
    k = 0.4369  bytes-priced  (alpha)
    k = 0.5000  latency-priced (beta)
Translation anchor supplied by the advisor: 0.4 % of cs = 26.27 M5 us/step
= 60.1 M4 us/step at alpha = 52.5 M4 us/step at beta.

Tagging, per the round's "host . epoch . census-or-marginal" requirement.  The
two kinds of number printed below are NOT the same kind:

  * LEVELS  (per-arm means, e.g. 8984.5 us/token) are  host=M4-Pro . epoch=R107
    . CENSUS -- each is a whole-model end-to-end decode rate over all 1023
    scored steps of ./benchmark.sh --local-submit.
  * DIFFERENCES (every D, CI, sd and power number) are  host=M4-Pro . epoch=R107
    . MARGINAL -- a paired difference of two arms of one binary, i.e. the
    increment attributable to the gate set, not a rate in its own right.

The distinction is load-bearing, and it is the reason for guard rail 3: a local
CENSUS level and a receipt CENSUS level are levels on DIFFERENT hosts, so their
ratio (e.g. 4925.255/8984.50 = 0.5482) is not the transfer factor k and must
never be used as one.  Only MARGINAL quantities are transferred, and only by
multiplying by k.  Nothing here came from a receipt.

Usage:  python3 research/maple-nezuko-r107j-paired-ci.py ROWS.tsv [ROWS2.tsv ...]
Env:    KREF=alpha|beta   which k to headline (default alpha, the smaller and
                          therefore the one that makes a candidate look WORSE
                          when converting a measured effect into % of cs)
"""
import math
import os
import sys
from collections import OrderedDict

# ---------------------------------------------------------------- constants
K_ALPHA = 0.4369          # M4->M5 transfer, bytes-priced
K_BETA = 0.5000           # M4->M5 transfer, latency-priced
PCS_PER_M5_US = 0.015228  # % of cs per M5 us/step  (0.4 % = 26.27 M5 us/step)

# Two-sided 97.5th percentile of Student t, by dof. No scipy on this host, so
# these are hardcoded from tables; ~1e-3 accurate, which is far below the
# sampling error of an sd estimated from <=20 blocks.
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
        14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
        20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
        26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042, 35: 2.030,
        40: 2.021, 45: 2.014, 50: 2.009, 60: 2.000, 80: 1.990, 100: 1.984}
# One-sided 80th percentile of Student t, for the 80 %-power column.
T80 = {1: 1.376, 2: 1.061, 3: 0.978, 4: 0.941, 5: 0.920, 6: 0.906, 7: 0.896,
       8: 0.889, 9: 0.883, 10: 0.879, 11: 0.876, 12: 0.873, 13: 0.870,
       14: 0.868, 15: 0.866, 16: 0.865, 17: 0.863, 18: 0.862, 19: 0.861,
       20: 0.860, 21: 0.859, 22: 0.858, 23: 0.858, 24: 0.857, 25: 0.856,
       26: 0.856, 27: 0.855, 28: 0.855, 29: 0.854, 30: 0.854, 35: 0.852,
       40: 0.851, 45: 0.850, 50: 0.849, 60: 0.848, 80: 0.846, 100: 0.845}


def _tbl(tbl, dof):
    if dof < 1:
        return float('nan')
    if dof in tbl:
        return tbl[dof]
    keys = sorted(tbl)
    if dof > keys[-1]:
        return tbl[keys[-1]]
    lo = max(k for k in keys if k < dof)
    hi = min(k for k in keys if k > dof)
    f = (dof - lo) / (hi - lo)
    return tbl[lo] + f * (tbl[hi] - tbl[lo])


def t975(dof):
    return _tbl(T975, dof)


def t80(dof):
    return _tbl(T80, dof)


def _gammp(a, x):
    """Regularised lower incomplete gamma P(a, x).  Numerical-Recipes split:
    series below the turning point, continued fraction above it.  Needed because
    this host has numpy but NOT scipy, and the power curve is only honest if the
    uncertainty of its own sd estimate is quantified -- which needs chi-square
    quantiles."""
    if x <= 0.0:
        return 0.0
    if x < a + 1.0:
        term = 1.0 / a
        total = term
        ap = a
        for _ in range(1000):
            ap += 1.0
            term *= x / ap
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        return total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    # continued fraction for Q(a, x), then P = 1 - Q
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    q = math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
    return 1.0 - q


def chi2_ppf(p, dof):
    """Inverse chi-square CDF by bisection on _gammp.  Bracket generously."""
    if dof <= 0:
        return float('nan')
    lo, hi = 1e-12, max(10.0 * dof, 100.0)
    while _gammp(dof / 2.0, hi / 2.0) < p:
        hi *= 2.0
        if hi > 1e12:
            return float('nan')
    for _ in range(300):
        mid = 0.5 * (lo + hi)
        if _gammp(dof / 2.0, mid / 2.0) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def sd_ci(s, dof, conf=0.95):
    """CI95 for a standard deviation: s*sqrt(dof/chi2_hi), s*sqrt(dof/chi2_lo).

    Reported because block counts scale as sd^2, so a 20 % error in the sd is a
    44 % error in the campaign plan.  Quoting a power curve from a dof-11 sd
    without this interval would overstate how well the plan is pinned down."""
    if dof < 1 or not math.isfinite(s):
        return float('nan'), float('nan')
    a = (1.0 - conf) / 2.0
    hi_q = chi2_ppf(1.0 - a, dof)
    lo_q = chi2_ppf(a, dof)
    if not (math.isfinite(hi_q) and math.isfinite(lo_q)) or lo_q <= 0:
        return float('nan'), float('nan')
    return s * math.sqrt(dof / hi_q), s * math.sqrt(dof / lo_q)


def mean(xs):
    return sum(xs) / len(xs)


def sd(xs):
    if len(xs) < 2:
        return float('nan')
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


# ---------------------------------------------------------------- load rows
def load(paths):
    rows = []
    hdr = None
    for p in paths:
        with open(p) as fh:
            for line in fh:
                line = line.rstrip('\n')
                if not line:
                    continue
                f = line.split('\t')
                if f[0] == 'session':
                    hdr = f
                    continue
                if hdr is None:
                    raise SystemExit('FATAL: %s has no header row' % p)
                rows.append(dict(zip(hdr, f)))
    return rows


def fnum(s):
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v


def main():
    paths = [a for a in sys.argv[1:] if not a.startswith('-')]
    if not paths:
        raise SystemExit(__doc__)
    kref = os.environ.get('KREF', 'alpha').lower()
    k_head = K_ALPHA if kref.startswith('a') else K_BETA
    k_name = 'alpha=0.4369 (bytes)' if kref.startswith('a') else 'beta=0.5000 (latency)'

    rows = load(paths)
    if not rows:
        raise SystemExit('FATAL: no data rows')

    arms = OrderedDict()
    for r in rows:
        arms.setdefault(r['arm'], []).append(r)
    labels = list(arms)
    ref = labels[0]

    print('=' * 78)
    print('R107-J\' paired local decode certification -- host=M4-Pro epoch=R107')
    print('tags      : per-arm LEVELS are CENSUS; all D / CI / sd / power are MARGINAL')
    print('instrument: ./benchmark.sh --local-submit (1023 decode steps), blocked+interleaved')
    print('sessions  : %s' % ','.join(sorted({r['session'] for r in rows})))
    print('head      : %s' % ','.join(sorted({r['head'] for r in rows})))
    print('rows      : %d over %d arms; reference arm = %s' % (len(rows), len(labels), ref))
    print('=' * 78)

    # ---------------------------------------------------- per-arm description
    print('\n--- per-arm within-arm description (us/token, local-submit) ---')
    print('%-6s %4s %12s %9s %8s  %-26s %s' %
          ('arm', 'n', 'mean', 'sd', 'cv%', 'gates', 'passed/golden'))
    lvl = {}
    for a in labels:
        v = [fnum(r['decode_s_per_token']) for r in arms[a]]
        v = [x * 1e6 for x in v if x is not None]
        lvl[a] = mean(v) if v else float('nan')
        s = sd(v)
        gts = sorted({r['gates'] for r in arms[a]})
        pas = sorted({r['passed'] for r in arms[a]})
        gld = sorted({r['golden'] for r in arms[a]})
        print('%-6s %4d %12.3f %9.3f %8.3f  %-26s %s / %s' %
              (a, len(v), lvl[a], s, 100.0 * s / lvl[a] if v else float('nan'),
               ','.join(gts)[:26], ','.join(pas), ','.join(gld)[:18]))
    for a in labels:
        ks = sorted({r['kernels'] for r in arms[a]})
        print('   arm %-4s kernels: %s' % (a, ' | '.join(ks)))
    bad = [r for r in rows if r['passed'] == 'false']
    print('correctness failures: %d%s' % (len(bad),
          '' if not bad else ' <-- ' + ','.join('%s#%s' % (r['arm'], r['idx']) for r in bad)))

    base = lvl[ref]

    def three(x_us):
        """(M4 us, relative decode %, % of cs at headline k)"""
        return (x_us, 100.0 * x_us / base, x_us * k_head * PCS_PER_M5_US)

    # ---------------------------------------------------- paired differences
    results = {}
    for a in labels[1:]:
        print('\n' + '-' * 78)
        print('PAIRED CONTRAST  %s - %s   (positive = %s SLOWER than %s)' % (a, ref, a, ref))
        print('-' * 78)
        blocks = sorted({int(r['block']) for r in arms[a]} & {int(r['block']) for r in arms[ref]})
        D, DP, POS, used = [], [], [], []
        for b in blocks:
            ra = [r for r in arms[a] if int(r['block']) == b]
            rr = [r for r in arms[ref] if int(r['block']) == b]
            if len(ra) != 1 or len(rr) != 1:
                print('  block %-3d SKIPPED (arm rows=%d ref rows=%d)' % (b, len(ra), len(rr)))
                continue
            va, vr = fnum(ra[0]['decode_s_per_token']), fnum(rr[0]['decode_s_per_token'])
            if va is None or vr is None:
                print('  block %-3d SKIPPED (missing decode level)' % b)
                continue
            d = (va - vr) * 1e6
            pa, pr = fnum(ra[0]['prefill_s_per_token']), fnum(rr[0]['prefill_s_per_token'])
            dp = (pa - pr) * 1e6 if (pa is not None and pr is not None) else float('nan')
            dpos = int(ra[0]['pos']) - int(rr[0]['pos'])
            D.append(d); DP.append(dp); POS.append(dpos); used.append(b)
            print('  block %-3d  %s=%10.3f  %s=%10.3f  D=%+9.3f us  dpos=%+d  dprefill=%+9.3f us'
                  % (b, a, va * 1e6, ref, vr * 1e6, d, dpos, dp))
        n = len(D)
        if n < 2:
            print('  INSUFFICIENT PAIRS (n=%d): no CI' % n)
            continue
        dof = n - 1
        m, s = mean(D), sd(D)
        se = s / math.sqrt(n)
        tc = t975(dof)
        hw = tc * se
        tstat = m / se if se else float('nan')
        print('\n  n_blocks=%d  dof=%d  t(0.975,%d)=%.3f' % (n, dof, dof, tc))
        print('  paired sd        = %9.3f us/token   (MEASURED, not inferred)' % s)
        print('  standard error   = %9.3f us/token' % se)
        print('  CI95 half-width  = %9.3f us/token' % hw)
        print('  t statistic      = %+9.3f' % tstat)
        print('  reference level  = %9.3f us/token' % base)
        print('  k (headline)     = %s ; %% of cs = us x k x %.6f' % (k_name, PCS_PER_M5_US))
        for nm, val in (('point estimate', m), ('CI95 low', m - hw), ('CI95 high', m + hw)):
            a3 = three(val)
            print('  %-15s %+10.3f us/token   %+8.4f %% decode   %+8.4f %% cs(a)   %+8.4f %% cs(b)'
                  % (nm, a3[0], a3[1], a3[2], val * K_BETA * PCS_PER_M5_US))
        covers0 = (m - hw) <= 0.0 <= (m + hw)
        print('  CI95 covers zero : %s' % ('YES' if covers0 else 'NO'))
        # prefill neutrality diagnostic (rule 105.4)
        dpv = [x for x in DP if x is not None and math.isfinite(x)]
        if len(dpv) >= 2:
            mp, sp = mean(dpv), sd(dpv)
            hwp = t975(len(dpv) - 1) * sp / math.sqrt(len(dpv))
            print('  prefill diag     : d=%+.3f us/token CI95 [%+.3f, %+.3f] -> %s'
                  % (mp, mp - hwp, mp + hwp,
                     'neutral (covers 0)' if (mp - hwp) <= 0 <= (mp + hwp)
                     else 'NOT NEUTRAL -- decode contrast is contaminated'))
        # position-confound check: OLS of D on within-block position offset
        if len(set(POS)) > 1:
            mx, my = mean(POS), mean(D)
            sxx = sum((x - mx) ** 2 for x in POS)
            sxy = sum((x - mx) * (y - my) for x, y in zip(POS, D))
            slope = sxy / sxx
            inter = my - slope * mx
            resid = [y - (inter + slope * x) for x, y in zip(POS, D)]
            rdof = n - 2
            if rdof >= 1:
                sr = math.sqrt(sum(r * r for r in resid) / rdof)
                sse = sr / math.sqrt(sxx)
                shw = t975(rdof) * sse
                print('  position OLS     : slope=%+.3f us/position CI95 [%+.3f, %+.3f] -> %s'
                      % (slope, slope - shw, slope + shw,
                         'no ordering confound' if (slope - shw) <= 0 <= (slope + shw)
                         else 'ORDERING CONFOUND present'))
                print('  position-adjusted intercept at dpos=0: %+.3f us/token' % inter)
        else:
            print('  position OLS     : skipped (dpos constant at %+d; blocks not a multiple of arm count)' % POS[0])
        results[a] = (n, m, s)

    # ---------------------------------------------------- the power curve
    # Built from the LARGEST measured paired sd across contrasts, so the curve
    # is the pessimistic one (rule 105.12: never headline the friendly side).
    if results:
        s_use = max(v[2] for v in results.values())
        s_src = max(results.items(), key=lambda kv: kv[1][2])[0]
    else:
        s_use, s_src = float('nan'), 'none'
    if not math.isfinite(s_use):
        print('\nno usable paired sd; power curve omitted')
        return
    # dof of the sd we actually quote: it belongs to the arm that supplied
    # s_use, NOT to whichever arm happens to have the largest mean diff.
    dof_use = results[s_src][0] - 1
    sd_lo, sd_hi = sd_ci(s_use, dof_use)

    print('\n' + '=' * 78)
    print('POWER CURVE of this instrument -- paired sd = %.3f us/token (measured, arm %s)' % (s_use, s_src))
    print('host=M4-Pro epoch=R107; half-widths are MARGINAL; reference CENSUS '
          'level %.3f us/token; k=%s' % (base, k_name))
    print('the sd is itself an estimate: chi-square CI95 on sd (dof %d) = '
          '[%.3f, %.3f] us/token' % (dof_use, sd_lo, sd_hi))
    print('  -> block counts scale as sd^2, so the planning numbers below carry')
    print('     a factor [%.2fx, %.2fx] of their own. Plan with the UPPER sd.'
          % ((sd_lo / s_use) ** 2, (sd_hi / s_use) ** 2))
    print('=' * 78)
    print('%6s %4s %7s %12s %11s %11s %11s   %11s' %
          ('blocks', 'dof', 't.975', 'hw us/token', 'hw %decode', 'hw %cs(a)', 'hw %cs(b)', 'runs(2 arms)'))
    for n in list(range(3, 21)) + [24, 30]:
        dof = n - 1
        tc = t975(dof)
        hw = tc * s_use / math.sqrt(n)
        print('%6d %4d %7.3f %12.3f %11.4f %11.4f %11.4f   %11d' %
              (n, dof, tc, hw, 100.0 * hw / base,
               hw * K_ALPHA * PCS_PER_M5_US, hw * K_BETA * PCS_PER_M5_US, 2 * n))

    print('\nBLOCKS NEEDED to certify a summed effect of a given size (CI excluding zero).')
    print('"resolve" = smallest n with CI95 half-width < the effect, i.e. an observed')
    print('  point estimate AT the target would have a CI that excludes zero (~50 % power).')
    print('"80 % power" = smallest n with effect >= (t.975 + t.80) * sd / sqrt(n).')
    print('%9s %13s %13s %9s %11s %9s %11s' %
          ('target', 'M4 us k=a', 'M4 us k=b', 'resolve', 'runs', '80%power', 'runs'))
    for tgt in (0.40, 0.30, 0.25, 0.20):
        for kname, kv in (('a', K_ALPHA), ('b', K_BETA)):
            eff = tgt / (kv * PCS_PER_M5_US)
            n_res = n_pow = None
            for n in range(2, 201):
                dof = n - 1
                hw = t975(dof) * s_use / math.sqrt(n)
                if n_res is None and hw < eff:
                    n_res = n
                if n_pow is None and eff >= (t975(dof) + t80(dof)) * s_use / math.sqrt(n):
                    n_pow = n
                if n_res and n_pow:
                    break
            if kname == 'a':
                ea, na, pa_ = eff, n_res, n_pow
            else:
                eb, nb, pb_ = eff, n_res, n_pow
        print('%8.2f%% %13.2f %13.2f %4s/%-4s %5s/%-5s %4s/%-4s %5s/%-5s' %
              (tgt, ea, eb, na, nb, 2 * na if na else '-', 2 * nb if nb else '-',
               pa_, pb_, 2 * pa_ if pa_ else '-', 2 * pb_ if pb_ else '-'))
    print('(resolve / 80%power columns are printed as  k=alpha / k=beta;')
    print(' runs columns are the same numbers x 2 arms. ~198 s per run on this host,')
    print(' so runs x 198 s is the wall clock: 20 runs ~= 66 min, 24 runs ~= 79 min.)')


if __name__ == '__main__':
    main()
