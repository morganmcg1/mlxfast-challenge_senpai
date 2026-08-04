#!/usr/bin/env python3
"""Renormalise mlxfast submission receipts against a pinned reference.

The published `officialScore` divides by a baseline measured in the same session,
which makes it a variance amplifier rather than a control: on byte-identical
content its pooled cv is 0.489% against 0.149% for the statistic computed here.
See research/nezuko-normalised-leaderboard.md for the derivation.

Definitions (BD/BP are the pinned reference baseline seconds/token):

    nd  = BD / decode_seconds_per_token          normalised decode speedup
    npf = BP / prefill_seconds_per_token         normalised prefill speedup
    ns  = nd**0.75 * npf**0.25                   renormalised composite score
    S   = 512 * 1000 * prefill_s_per_token       512-token seed forward, ms
    T   = 1000 * decode_s_per_token - S / 128    marginal decode step, ms
    draw = officialScore / ns                    how lucky this session was

`S` and `T` are the units the code actually moves: a 128-step teacher-forced
decode pass amortises one seed forward over 128 steps, so `decode_s_per_token`
silently contains S/128 and a prefill change leaks into the decode axis.

Usage
-----
    # fetch, then rank every scored receipt by renormalised ns
    python3 nezuko-renormalise.py fetch subs.json
    python3 nezuko-renormalise.py rank subs.json --top 20

    # price one arm against a control, each given as compile-identical receipts
    python3 nezuko-renormalise.py family subs.json \\
        --arm 5d522d6a,5e0e9cd1 --control f8502e12,71586bcf,f3cda678

    # how many receipts per arm does a given effect size need?
    python3 nezuko-renormalise.py power
"""
import argparse
import json
import math
import os
import statistics as st
import subprocess
import sys

BENCHMARK_ID = '1854efdf-feba-4773-bae9-b80520881a74'
API = f'https://api.mlx.fast/api/benchmarks/{BENCHMARK_ID}/submissions'

# Pinned reference: the mode of the byte-identical harness baseline over the
# 916 fully-instrumented receipts in the 2026-08-04 corpus snapshot.
BD = 0.013890
BP = 0.0003845

# Pooled within-identical-content cv, 7 byte-identical families, 27 dof.
CV = {'ns': 0.149, 'T': 0.222, 'S': 0.174, 'score': 0.489}


def fetch(path):
    token = os.environ['MLXFAST_API_TOKEN']
    out = subprocess.run(['curl', '-fsS', '-H', f'Authorization: Bearer {token}', API],
                         capture_output=True, text=True, check=True).stdout
    json.loads(out)
    with open(path, 'w') as fh:
        fh.write(out)
    return path


def load(path):
    rows = json.load(open(path))
    if isinstance(rows, dict):
        rows = rows.get('submissions') or rows.get('data')
    out = []
    for r in rows:
        om = r.get('officialMetrics') or {}
        dec = om.get('decode_seconds_per_token')
        pre = om.get('prefill_seconds_per_token')
        if not dec or not pre:
            continue
        rec = dict(sid=r['id'][:8], solver=r.get('solverUsername'),
                   status=r.get('status'), created=r.get('createdAt', '')[:19],
                   score=r.get('officialScore'), dec=dec, pre=pre,
                   bdec=om.get('baseline_decode_seconds_per_token'),
                   bpre=om.get('baseline_prefill_seconds_per_token'))
        rec['nd'] = BD / dec
        rec['npf'] = BP / pre
        rec['ns'] = rec['nd'] ** 0.75 * rec['npf'] ** 0.25
        rec['S'] = 512 * 1000 * pre
        rec['T'] = 1000 * dec - rec['S'] / 128
        rec['draw'] = rec['score'] / rec['ns'] if rec['score'] else None
        out.append(rec)
    return out


def pick(rows, prefixes):
    chosen = []
    for p in prefixes:
        hits = [r for r in rows if r['sid'].startswith(p)]
        if not hits:
            sys.exit(f'no scored receipt matches {p!r}')
        chosen.extend(hits)
    return chosen


def summarise(rows, label):
    n = len(rows)
    out = {'n': n, 'label': label}
    for k in ('S', 'T', 'nd', 'npf', 'ns', 'score'):
        v = [r[k] for r in rows if r[k] is not None]
        out[k] = st.mean(v)
        out[k + '_cv'] = (st.stdev(v) / st.mean(v) * 100) if len(v) > 1 else None
    return out


def cmd_rank(rows, args):
    rows = [r for r in rows if r['score']]
    rows.sort(key=lambda r: -r['ns'])
    print(f'{len(rows)} scored receipts, ranked by renormalised ns\n')
    hdr = ('rank', 'sid', 'ns', 'nd', 'npf', 'T ms', 'S ms', 'published', 'draw', 'solver')
    print(''.join(f'{h:>11}' for h in hdr[:-1]) + '  solver')
    for i, r in enumerate(rows[:args.top], 1):
        print(f'{i:>11}{r["sid"]:>11}{r["ns"]:>11.4f}{r["nd"]:>11.4f}'
              f'{r["npf"]:>11.4f}{r["T"]:>11.4f}{r["S"]:>11.3f}'
              f'{r["score"]:>11.4f}{r["draw"]:>11.5f}  {r["solver"]}')
    pub = sorted(rows, key=lambda r: -r['score'])
    print(f'\ntop published receipt is {pub[0]["sid"]} (ns rank '
          f'{rows.index(pub[0]) + 1} of {len(rows)}, draw {pub[0]["draw"]:.5f})')
    print(f'top content receipt is   {rows[0]["sid"]} (published rank '
          f'{pub.index(rows[0]) + 1} of {len(rows)}, draw {rows[0]["draw"]:.5f})')


def cmd_family(rows, args):
    arm = summarise(pick(rows, args.arm.split(',')), 'arm')
    ctl = summarise(pick(rows, args.control.split(',')), 'control')
    for f in (ctl, arm):
        print(f'{f["label"]:<8} n={f["n"]}   ns {f["ns"]:.6f}  T {f["T"]:.4f}  '
              f'S {f["S"]:.3f}  published {f["score"]:.6f}')
        if f['n'] > 1:
            print(f'{"":<8} within-family cv:  ns {f["ns_cv"]:.3f}%  '
                  f'T {f["T_cv"]:.3f}%  S {f["S_cv"]:.3f}%  '
                  f'published {f["score_cv"]:.3f}%')
    print()
    for key, cv in (('ns', CV['ns']), ('T', CV['T']), ('S', CV['S']),
                    ('score', CV['score'])):
        d = (arm[key] / ctl[key] - 1) * 100
        se = math.sqrt(cv ** 2 / arm['n'] + cv ** 2 / ctl['n'])
        print(f'  {key:<6} {d:+.3f}% +- {se:.3f}%   ({abs(d) / se:.1f} sigma)')
    det = 2 * CV['ns'] * math.sqrt(1 / arm['n'] + 1 / ctl['n'])
    print(f'\n  smallest ns effect these family sizes resolve at 2 sigma: {det:.3f}%')


def cmd_power(rows, args):
    print('receipts per arm for 2-sigma detection of a given true effect\n')
    print('  effect |' + ''.join(f'{m:>12}' for m in CV))
    for d in (0.15, 0.25, 0.35, 0.50, 0.75, 1.00):
        print(f'  {d:5.2f}% |' + ''.join(
            f'{max(1, math.ceil(8 * cv * cv / (d * d))):>12}' for cv in CV.values()))
    print('\n  the published score costs 8-11x more ranked runs than ns below 1%')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('fetch').add_argument('path')
    p = sub.add_parser('rank')
    p.add_argument('path')
    p.add_argument('--top', type=int, default=20)
    p = sub.add_parser('family')
    p.add_argument('path')
    p.add_argument('--arm', required=True, help='comma-separated receipt id prefixes')
    p.add_argument('--control', required=True, help='comma-separated receipt id prefixes')
    sub.add_parser('power')
    args = ap.parse_args()

    if args.cmd == 'fetch':
        print('wrote', fetch(args.path))
        return
    if args.cmd == 'power':
        cmd_power(None, args)
        return
    rows = load(args.path)
    {'rank': cmd_rank, 'family': cmd_family}[args.cmd](rows, args)


if __name__ == '__main__':
    main()
