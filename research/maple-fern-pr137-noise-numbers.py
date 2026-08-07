#!/usr/bin/env python3
"""Every number quoted in section 13, recomputed in one place."""
import json
import statistics as st
from collections import defaultdict

NORM_DECODE = 0.013890
NORM_PREFILL = 0.0003845
rows = json.load(open('feed.json'))

good = []
for r in rows:
    m = r.get('officialMetrics') or {}
    d = m.get('decode_seconds_per_token')
    p = m.get('prefill_seconds_per_token')
    bd = m.get('baseline_decode_seconds_per_token')
    bp = m.get('baseline_prefill_seconds_per_token')
    s = r.get('officialScore')
    if not (d and p and bd and bp and s):
        continue
    good.append({'id': r['id'][:8], 'solver': r.get('solverUsername'),
                 'day': r['createdAt'][:10], 'ts': r['createdAt'],
                 'status': r['status'], 'd': d, 'p': p, 'bd': bd, 'bp': bp,
                 'score': s, 'dspd': m['decode_speedup'],
                 'pspd': m['prefill_speedup']})

print(f"[A] feed rows {len(rows)}   rows with full metrics {len(good)}")
print(f"    span {good[0]['ts'][:10]} .. {good[-1]['ts'][:10]}")

buckets = defaultdict(list)
for g in good:
    buckets[(g['solver'], g['day'])].append(g)
clusters = [v for v in buckets.values()
            if len(v) >= 4
            and (max(x['d'] for x in v) - min(x['d'] for x in v)) / st.mean(
                [x['d'] for x in v]) < 0.015]
print(f"[B] clusters {len(clusters)}  rows {sum(len(c) for c in clusters)}")

# --- correlation between candidate and its paired baseline, within cluster
for lab, ck, bk in (('decode', 'd', 'bd'), ('prefill', 'p', 'bp')):
    xs, ys = [], []
    for c in clusters:
        mc = st.mean([x[ck] for x in c])
        mb = st.mean([x[bk] for x in c])
        for x in c:
            xs.append(x[ck] / mc - 1)
            ys.append(x[bk] / mb - 1)
    n = len(xs)
    sx = (sum(v * v for v in xs) / n) ** 0.5
    sy = (sum(v * v for v in ys) / n) ** 0.5
    rho = (sum(a * b for a, b in zip(xs, ys)) / n) / (sx * sy)
    print(f"[C] rho(candidate,baseline) {lab:8} = {rho:+.3f}   n={n}")

# --- variance decomposition of the score
sd_cd = st.median([100 * st.stdev([x['d'] for x in c]) / st.mean([x['d'] for x in c]) for c in clusters])
sd_cp = st.median([100 * st.stdev([x['p'] for x in c]) / st.mean([x['p'] for x in c]) for c in clusters])
sd_bd = st.median([100 * st.stdev([x['bd'] for x in c]) / st.mean([x['bd'] for x in c]) for c in clusters])
sd_bp = st.median([100 * st.stdev([x['bp'] for x in c]) / st.mean([x['bp'] for x in c]) for c in clusters])
parts = {'cand decode': (0.75 * sd_cd) ** 2, 'base decode': (0.75 * sd_bd) ** 2,
         'cand prefill': (0.25 * sd_cp) ** 2, 'base prefill': (0.25 * sd_bp) ** 2}
tot = sum(parts.values())
print(f"[D] score variance budget (predicted sd {tot ** 0.5:.3f} %)")
for k, v in sorted(parts.items(), key=lambda kv: -kv[1]):
    print(f"      {k:14} {100 * v / tot:5.1f} %")

# --- drift test on the paired baseline
byday = defaultdict(list)
for g in good:
    if g['ts'] >= '2026-07-31':
        byday[g['day']].append(g['bd'])
print("[E] baseline decode by day (ms)")
means = []
within = []
for day in sorted(byday):
    v = byday[day]
    means.append(st.mean(v))
    if len(v) > 2:
        within.append(st.stdev(v) / st.mean(v))
    print(f"      {day}  n={len(v):4}  mean {1000 * st.mean(v):.5f}"
          f"  sd {100 * st.stdev(v) / st.mean(v):.3f} %")
sd_means = 100 * st.stdev(means) / st.mean(means)
sd_within = 100 * st.median(within)
n_med = st.median([len(v) for v in byday.values()])
print(f"    sd of daily means      {sd_means:.3f} %")
print(f"    median within-day sd   {sd_within:.3f} %")
print(f"    expected sd of daily means under white noise "
      f"{sd_within / n_med ** 0.5:.3f} %  (median n = {n_med:.0f})")

seq = [g['bd'] for g in good if g['ts'] >= '2026-07-31']
mu = st.mean(seq)
r1 = (sum((a - mu) * (b - mu) for a, b in zip(seq, seq[1:]))
      / sum((a - mu) ** 2 for a in seq))
print(f"    lag-1 autocorrelation  {r1:+.3f}  (0 = white noise)")

# --- the acceptance bar as an order statistic
last300 = good[-300:]
med_p = st.median([g['pspd'] for g in last300])
print(f"[F] median prefill_speedup of the last 300 scored rows {med_p:.5f}")
acc = [g for g in good if g['status'] == 'accepted'][-8:]
allp = sorted(g['pspd'] for g in last300)
print("    accepted rows, their prefill draw, and their score at the median draw")
for g in acc:
    pct = 100.0 * sum(1 for v in allp if v <= g['pspd']) / len(allp)
    cf = g['dspd'] ** 0.75 * med_p ** 0.25
    print(f"      {g['id']} {g['ts'][5:16]}  score {g['score']:.5f}"
          f"  pspd {g['pspd']:.5f} (p{pct:.0f})  ->  {cf:.5f}"
          f"  ({100 * (g['score'] / cf - 1):+.2f} % inflation)")

# --- how far apart are the two top rows really
a = [g for g in good if g['id'] == 'db8b4df1'][0]
b = [g for g in good if g['id'] == '97a5090c'][0]
print(f"[G] db8b4df1 vs 97a5090c")
print(f"      score {a['score']:.5f} vs {b['score']:.5f}  ({100 * (a['score'] / b['score'] - 1):+.3f} %)")
print(f"      dspd  {a['dspd']:.5f} vs {b['dspd']:.5f}  ({100 * (a['dspd'] / b['dspd'] - 1):+.3f} %)")
print(f"      pspd  {a['pspd']:.5f} vs {b['pspd']:.5f}  ({100 * (a['pspd'] / b['pspd'] - 1):+.3f} %)")
print(f"      cand decode {1000 * a['d']:.5f} vs {1000 * b['d']:.5f} ms")

# --- sigma table
BAR = 2.59018571539341
EFF = 63.7 * 0.01464
tbl = [('officialScore', 0.753, EFF), ('ns (fixed norms)', 0.425, EFF),
       ('decode_speedup', 0.334, EFF / 0.75),
       ('cand decode / nsd', 0.294, EFF / 0.75)]
print(f"[H] effect size in sigma, single receipt vs a single-draw reference")
print(f"    (a full-transfer effect is {EFF:.3f} % of score, {EFF / 0.75:.3f} % of decode)")
print(f"    {'statistic':20} {'1 sd':>6} {'sd(diff)':>9} {'t=.50':>7} {'t=.75':>7} {'t=1.0':>7} {'sd_t':>6}")
for name, sd, eff in tbl:
    sdd = sd * 2 ** 0.5
    print(f"    {name:20} {sd:6.3f} {sdd:9.3f}"
          f" {0.50 * eff / sdd:7.2f} {0.75 * eff / sdd:7.2f} {1.00 * eff / sdd:7.2f}"
          f" {sdd / eff:6.2f}")
for lab, v in (('bar', BAR), ('KILL', 2.5919), ('GO', 2.6045)):
    print(f"    {lab:5} {v}  = {100 * (v / BAR - 1):+.3f} %  = "
          f"{(v / BAR - 1) * 100 / 0.753:.2f} sigma of one officialScore draw")
