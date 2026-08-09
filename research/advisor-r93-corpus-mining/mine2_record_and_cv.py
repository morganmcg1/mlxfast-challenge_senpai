import json, statistics as st
from collections import defaultdict
from datetime import datetime

d = json.load(open('research/r91b-runs/baseline-drift.json'))
OURS_DEC, OURS_PRE = 0.0048937119140625, 0.000188042724609375
MB_D, MB_P = 0.013855009542, 0.000372473193
def cs(dec, pre): return (MB_D/dec)**0.75 * (MB_P/pre)**0.25

rows = [r for r in d if r.get('cand_dec') and r.get('cand_pre')]
for r in rows: r['dt'] = datetime.strptime(r['ts'], '%Y-%m-%dT%H:%M:%SZ')

rec = [r for r in rows if r['id'] == 'cc6ddc12']
print('=== RECORD RECEIPT cc6ddc12 ===')
for r in rec:
    print(f"  {r['solver']} dec={r['cand_dec']:.12f} pre={r['cand_pre']:.12f} bl_dec={r['bl_dec']:.12f} bl_pre={r['bl_pre']:.12f} pub={r['score']:.10f} cs={cs(r['cand_dec'],r['cand_pre']):.6f} {r['ts']}")

# ---- within-solver adjacent-pair differences (bounds candidate noise) ----
print('\n=== ADJACENT-SUBMISSION |delta| IN cand_dec, PER SOLVER (temporally sorted) ===')
print('solver              n   med|d%|  p10|d%|  p25|d%|   min|d%|   #pairs<0.05%')
bys = defaultdict(list)
for r in rows: bys[r['solver']].append(r)
for s, rs in sorted(bys.items(), key=lambda kv: -len(kv[1]))[:10]:
    rs.sort(key=lambda r: r['dt'])
    if len(rs) < 5: continue
    ds = [abs(rs[i+1]['cand_dec']/rs[i]['cand_dec'] - 1)*100 for i in range(len(rs)-1)]
    ds_s = sorted(ds)
    n = len(ds_s)
    p10 = ds_s[max(0,int(0.10*n)-1)]
    p25 = ds_s[max(0,int(0.25*n)-1)]
    small = sum(1 for x in ds if x < 0.05)
    print(f'{s:<18} {len(rs):<4} {st.median(ds):7.4f} {p10:8.4f} {p25:8.4f} {ds_s[0]:9.5f}   {small}/{n}')

print('\n=== SAME, cand_pre ===')
print('solver              n   med|d%|  p10|d%|  p25|d%|   min|d%|   #pairs<0.05%')
for s, rs in sorted(bys.items(), key=lambda kv: -len(kv[1]))[:10]:
    rs.sort(key=lambda r: r['dt'])
    if len(rs) < 5: continue
    ds = [abs(rs[i+1]['cand_pre']/rs[i]['cand_pre'] - 1)*100 for i in range(len(rs)-1)]
    ds_s = sorted(ds); n = len(ds_s)
    p10 = ds_s[max(0,int(0.10*n)-1)]; p25 = ds_s[max(0,int(0.25*n)-1)]
    small = sum(1 for x in ds if x < 0.05)
    print(f'{s:<18} {len(rs):<4} {st.median(ds):7.4f} {p10:8.4f} {p25:8.4f} {ds_s[0]:9.5f}   {small}/{n}')

# ---- our own 55 receipts: cand timing history ----
print('\n=== morganmcg1 RECEIPTS: 20 FASTEST BY cand_dec ===')
ours = sorted(bys['morganmcg1'], key=lambda r: r['cand_dec'])[:20]
for r in ours:
    print(f"  {r['id']} {r['ts'][:16]} dec={r['cand_dec']:.12f} ({(r['cand_dec']/OURS_DEC-1)*100:+.3f}%) pre={r['cand_pre']:.12f} ({(r['cand_pre']/OURS_PRE-1)*100:+.3f}%) cs={cs(r['cand_dec'],r['cand_pre']):.6f} pub={r['score']:.6f}")

# ---- baseline vs candidate: is session noise shared? split by day ----
print('\n=== BASELINE cv BY DAY vs LEADING-CANDIDATE cv BY DAY ===')
byday = defaultdict(list)
for r in rows: byday[r['ts'][:10]].append(r)
print('day         n    bl_dec cv%   bl_pre cv%   n_lead  lead cand_dec cv%  lead cand_pre cv%')
for day in sorted(byday):
    rs = byday[day]
    if len(rs) < 15: continue
    bd = [r['bl_dec'] for r in rs]; bp = [r['bl_pre'] for r in rs]
    lead = [r for r in rs if r['cand_dec'] < 0.00500]
    cd = [r['cand_dec'] for r in lead]; cp = [r['cand_pre'] for r in lead]
    ld = f"{st.pstdev(cd)/st.mean(cd)*100:7.4f}" if len(cd) > 3 else '      -'
    lp = f"{st.pstdev(cp)/st.mean(cp)*100:7.4f}" if len(cp) > 3 else '      -'
    print(f"{day}  {len(rs):<4} {st.pstdev(bd)/st.mean(bd)*100:9.4f}  {st.pstdev(bp)/st.mean(bp)*100:10.4f}   {len(lead):<5}  {ld}          {lp}")

# ---- promotion probability model ----
print('\n=== PROMOTION PROBABILITY vs RAW-TIMING IMPROVEMENT ===')
draws = [(r['bl_dec'], r['bl_pre']) for r in rows]
recent = [(r['bl_dec'], r['bl_pre']) for r in rows if r['ts'] >= '2026-08-06']
TARGET = 2.61650354381456
for label, D in (('all n=%d' % len(draws), draws), ('recent n=%d' % len(recent), recent)):
    print(f'  --- draws: {label} ---')
    for gd in (0.0, 0.005, 0.01, 0.015, 0.02, 0.03):
        dec = OURS_DEC * (1-gd); pre = OURS_PRE
        hits = sum(1 for bd, bp in D if (bd/dec)**0.75 * (bp/pre)**0.25 > TARGET)
        p = hits/len(D)
        k50 = ('%.1f' % (0.6931/-__import__('math').log1p(-p))) if p > 0 else 'inf'
        print(f'   decode -{gd*100:4.1f}%  P(beat)={p*100:6.2f}%  submissions for 50%={k50}')
    for gp in (0.005, 0.01, 0.02, 0.04):
        dec = OURS_DEC; pre = OURS_PRE * (1-gp)
        hits = sum(1 for bd, bp in D if (bd/dec)**0.75 * (bp/pre)**0.25 > TARGET)
        p = hits/len(D)
        k50 = ('%.1f' % (0.6931/-__import__('math').log1p(-p))) if p > 0 else 'inf'
        print(f'   prefill -{gp*100:4.1f}% P(beat)={p*100:6.2f}%  submissions for 50%={k50}')
