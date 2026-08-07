#!/usr/bin/env python3
"""Paired analysis of the PR205 palindromic decode-probe sweep.

Unit of replication is the RUN MEDIAN step time (us), not the individual step.
The palindrome is folded into adjacent (A,B) pairs so that any monotone drift
in host state cancels within a pair.
"""
import os
import statistics as st
import sys

WARMUP = 16


def run_stats(path):
    with open(path) as fh:
        ms = [float(x) for x in fh if x.strip()]
    us = [1e3 * v for v in ms[WARMUP:]]
    return dict(n=len(us), median=st.median(us), mean=st.fmean(us),
                p10=sorted(us)[len(us) // 10], p90=sorted(us)[9 * len(us) // 10])


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp/nezprobe'
    seq = os.environ.get('SEQ', 'A B B A A B B A A B B A').split()
    runs = []
    for i, arm in enumerate(seq, 1):
        p = os.path.join(out, f'steps_{i:02d}_{arm}.txt')
        if not os.path.exists(p):
            print(f'MISSING {p}')
            continue
        s = run_stats(p)
        s.update(idx=i, arm=arm)
        runs.append(s)

    print(f'{"run":>4s} {"arm":>3s} {"n":>5s} {"median us":>11s} {"mean us":>11s}'
          f' {"p10":>10s} {"p90":>10s}')
    for r in runs:
        print(f'{r["idx"]:4d} {r["arm"]:>3s} {r["n"]:5d} {r["median"]:11.2f}'
              f' {r["mean"]:11.2f} {r["p10"]:10.2f} {r["p90"]:10.2f}')

    A = [r['median'] for r in runs if r['arm'] == 'A']
    B = [r['median'] for r in runs if r['arm'] == 'B']
    if not A or not B:
        print('not enough runs')
        return 1
    print()
    print(f'arm A (candidate) n={len(A)} median-of-medians {st.median(A):.2f} us'
          f'  sd {st.stdev(A) if len(A) > 1 else float("nan"):.2f}')
    print(f'arm B (base)      n={len(B)} median-of-medians {st.median(B):.2f} us'
          f'  sd {st.stdev(B) if len(B) > 1 else float("nan"):.2f}')

    # adjacent-pair folding of the palindrome: (1,2) (3,4) (5,6) ...
    diffs = []
    for a, b in zip(runs[0::2], runs[1::2]):
        if a['arm'] == b['arm']:
            continue
        # positive = candidate FASTER (saved us/step)
        if a['arm'] == 'A':
            d = b['median'] - a['median']
        else:
            d = a['median'] - b['median']
        diffs.append(d)
        print(f'  pair ({a["idx"]}{a["arm"]},{b["idx"]}{b["arm"]}) '
              f'saved {d:+8.2f} us/step')

    print()
    n = len(diffs)
    if n < 2:
        print('not enough pairs')
        return 1
    mu = st.fmean(diffs)
    sd = st.stdev(diffs)
    se = sd / n ** 0.5
    t = mu / se if se else float('nan')
    # 95% two-sided t critical values for df = n-1
    TCRIT = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
             7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201}
    tc = TCRIT.get(n - 1, 1.96)
    lo, hi = mu - tc * se, mu + tc * se
    ref = st.median(B)
    print(f'PAIRED n={n}  saved mean {mu:+.2f} us/step  sd {sd:.2f}  se {se:.2f}'
          f'  t {t:+.2f}')
    print(f'PAIRED 95% CI [{lo:+.2f}, {hi:+.2f}] us/step'
          f'   ({100*lo/ref:+.4f} % .. {100*hi/ref:+.4f} % of {ref:.0f} us)')
    print(f'PAIRED point estimate {100*mu/ref:+.4f} % of the decode step')

    PRED = 14.02
    print()
    print(f'PRE-REGISTERED M4 kernel-level projection: {PRED:+.2f} us/step saved')
    print(f'  inside the 95% CI ? '
          f'{"YES" if lo <= PRED <= hi else "NO  -- REJECTED"}')
    print(f'  zero inside the 95% CI ? '
          f'{"YES (null)" if lo <= 0 <= hi else "NO  (resolved effect)"}')
    print(f'  resolution of this probe (CI half-width) {tc*se:.2f} us/step')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
