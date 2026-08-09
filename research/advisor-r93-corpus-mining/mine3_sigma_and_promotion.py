import json, math, statistics as st
from collections import defaultdict
from datetime import datetime

d = json.load(open('research/r91b-runs/baseline-drift.json'))
OURS_DEC, OURS_PRE = 0.0048937119140625, 0.000188042724609375
MB_D, MB_P = 0.013855009542, 0.000372473193
TARGET = 2.61650354381456
rows = [r for r in d if r.get('cand_dec') and r.get('cand_pre')]
for r in rows: r['dt'] = datetime.strptime(r['ts'], '%Y-%m-%dT%H:%M:%SZ')
bys = defaultdict(list)
for r in rows: bys[r['solver']].append(r)

# --- candidate noise from RAPID adjacent resubmissions (<20 min apart) ---
print('=== |delta| FOR ADJACENT PAIRS WITHIN 20 MINUTES (likely trivial content change) ===')
dec_d, pre_d, bl_d, blp_d = [], [], [], []
for s, rs in bys.items():
    rs.sort(key=lambda r: r['dt'])
    for i in range(len(rs)-1):
        gap = (rs[i+1]['dt']-rs[i]['dt']).total_seconds()
        if 0 < gap <= 1200:
            dec_d.append((rs[i+1]['cand_dec']/rs[i]['cand_dec']-1)*100)
            pre_d.append((rs[i+1]['cand_pre']/rs[i]['cand_pre']-1)*100)
            bl_d.append((rs[i+1]['bl_dec']/rs[i]['bl_dec']-1)*100)
            blp_d.append((rs[i+1]['bl_pre']/rs[i]['bl_pre']-1)*100)
print(f'  n pairs = {len(dec_d)}')
for name, v in (('cand_dec', dec_d), ('cand_pre', pre_d), ('bl_dec', bl_d), ('bl_pre', blp_d)):
    a = sorted(abs(x) for x in v)
    n = len(a)
    # robust sigma of the DIFFERENCE from the median |diff| of a half-normal: med = 0.6745*sqrt(2)*sigma
    sig_pair = st.median(a)/0.6745
    print(f'  {name:<9} med|d|={st.median(a):7.4f}%  p25={a[n//4]:7.4f}%  p10={a[n//10]:7.4f}%  '
          f'implied sigma_single={sig_pair/math.sqrt(2):7.4f}%')

# --- baseline pair differences over ALL adjacent pairs (baseline is a FIXED binary) ---
print('\n=== BASELINE (FIXED BINARY) PAIR DIFFERENCES, ALL ADJACENT PAIRS ===')
abl, ablp = [], []
for s, rs in bys.items():
    rs.sort(key=lambda r: r['dt'])
    for i in range(len(rs)-1):
        abl.append((rs[i+1]['bl_dec']/rs[i]['bl_dec']-1)*100)
        ablp.append((rs[i+1]['bl_pre']/rs[i]['bl_pre']-1)*100)
for name, v in (('bl_dec', abl), ('bl_pre', ablp)):
    a = sorted(abs(x) for x in v); n = len(a)
    print(f'  {name}: n={n} med|d|={st.median(a):.4f}% implied sigma_single={st.median(a)/0.6745/math.sqrt(2):.4f}%')

# --- promotion probability, full grid ---
def k50(p):
    if p <= 0: return 'inf'
    if p >= 1: return '1.0'
    return '%.1f' % (math.log(0.5)/math.log1p(-p))
draws = [(r['bl_dec'], r['bl_pre']) for r in rows]
recent = [(r['bl_dec'], r['bl_pre']) for r in rows if r['ts'] >= '2026-08-06']
print('\n=== PROMOTION PROBABILITY GRID (P that one draw beats %.6f) ===' % TARGET)
print(' decode gain | prefill gain |  P(all n=%d) | k50 |  P(recent n=%d) | k50' % (len(draws), len(recent)))
for gd in (0.0, 0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02):
    for gp in (0.0, 0.0025, 0.005):
        dec = OURS_DEC*(1-gd); pre = OURS_PRE*(1-gp)
        pa = sum(1 for bd,bp in draws if (bd/dec)**0.75*(bp/pre)**0.25 > TARGET)/len(draws)
        pr = sum(1 for bd,bp in recent if (bd/dec)**0.75*(bp/pre)**0.25 > TARGET)/len(recent)
        print(f'   -{gd*100:5.2f}%    |   -{gp*100:5.2f}%     |   {pa*100:6.2f}%     | {k50(pa):>5} |   {pr*100:6.2f}%       | {k50(pr):>5}')

# --- how many us/step is each % ---
print('\n=== UNIT CONVERSIONS AT OUR CURRENT TIMINGS ===')
print(f'  1.00% decode  = {OURS_DEC*1e6*0.01:8.2f} us/step   (ours = {OURS_DEC*1e6:.1f} us/step)')
print(f'  0.50% decode  = {OURS_DEC*1e6*0.005:8.2f} us/step')
print(f'  0.25% decode  = {OURS_DEC*1e6*0.0025:8.2f} us/step')
print(f'  1.00% prefill = {OURS_PRE*1e6*0.01:8.4f} us/token = {OURS_PRE*512*1e6*0.01:.1f} us over 512')
