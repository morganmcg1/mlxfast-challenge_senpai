#!/usr/bin/env python3
"""Pool adjacent-pair savings across several palindromic decode-probe sessions.

Each session directory holds `steps_<NN>_<arm>.txt` dumps written by
`research/decode_probe.py`. Pairing is done strictly WITHIN a session and only
between adjacent runs, so a between-session level shift cannot bias the pooled
mean; it only enters as extra variance if the effect itself differs by session.

usage: nezuko_decode_probe_pool.py DIR [DIR ...]
"""
import glob
import math
import os
import re
import statistics
import sys

WARMUP = 16
PREREG_US = 14.02

T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
       14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
       20: 2.086, 24: 2.064, 29: 2.045, 30: 2.042}


def t95(df):
    if df in T95:
        return T95[df]
    keys = sorted(T95)
    return T95[min(keys, key=lambda k: abs(k - df))]


def run_median_us(path):
    with open(path) as fh:
        ms = [float(x) for x in fh.read().split() if x.strip()]
    return statistics.median(1e3 * v for v in ms[WARMUP:])


def session_pairs(d):
    runs = []
    for p in sorted(glob.glob(os.path.join(d, 'steps_*.txt'))):
        m = re.search(r'steps_(\d+)_([AB])\.txt$', os.path.basename(p))
        if m:
            runs.append((int(m.group(1)), m.group(2), run_median_us(p)))
    runs.sort()
    pairs = []
    for i in range(0, len(runs) - 1, 2):
        (i1, a1, m1), (i2, a2, m2) = runs[i], runs[i + 1]
        if {a1, a2} != {'A', 'B'}:
            continue
        # positive = candidate (A) faster than base (B)
        saved = (m1 - m2) if a2 == 'A' else (m2 - m1)
        pairs.append((i1, i2, saved))
    return runs, pairs


def report(label, saved):
    n = len(saved)
    mean = statistics.mean(saved)
    sd = statistics.stdev(saved) if n > 1 else float('nan')
    se = sd / math.sqrt(n)
    half = t95(n - 1) * se
    lo, hi = mean - half, mean + half
    print(f'\n{label}: n={n} pairs')
    print(f'  saved mean {mean:+.2f} us/step  sd {sd:.2f}  se {se:.2f}  '
          f't {mean / se:+.2f}')
    print(f'  95% CI [{lo:+.2f}, {hi:+.2f}] us/step   half-width {half:.2f}')
    print(f'  pre-registered {PREREG_US:+.2f} inside CI ? '
          f'{"YES" if lo <= PREREG_US <= hi else "NO -- REJECTED"}')
    print(f'  zero inside CI ? {"YES (null)" if lo <= 0 <= hi else "NO"}')
    return mean, se


def main():
    dirs = sys.argv[1:]
    pooled = []
    for d in dirs:
        runs, pairs = session_pairs(d)
        print(f'=== {d}: {len(runs)} runs, {len(pairs)} pairs ===')
        for i1, i2, s in pairs:
            print(f'  pair ({i1:02d},{i2:02d}) saved {s:+8.2f} us/step')
        pooled.extend(s for _, _, s in pairs)
        if len(pairs) > 1:
            report(f'session {d}', [s for _, _, s in pairs])
    if len(dirs) > 1:
        report('POOLED across sessions', pooled)


if __name__ == '__main__':
    main()
