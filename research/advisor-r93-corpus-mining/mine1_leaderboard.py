import json, statistics as st
from collections import defaultdict

d = json.load(open('research/r91b-runs/baseline-drift.json'))
OURS_DEC, OURS_PRE = 0.0048937119140625, 0.000188042724609375
MEAN_BL_DEC, MEAN_BL_PRE = 0.013855009542, 0.000372473193

def cscore(dec, pre):
    return (MEAN_BL_DEC/dec)**0.75 * (MEAN_BL_PRE/pre)**0.25

rows = [r for r in d if r.get('cand_dec') and r.get('cand_pre')]
print('receipts with candidate timings:', len(rows))

# best decode / best prefill overall
bd = sorted(rows, key=lambda r: r['cand_dec'])[:12]
bp = sorted(rows, key=lambda r: r['cand_pre'])[:12]
print('\n=== 12 FASTEST CANDIDATE DECODE ===')
for r in bd:
    print(f"{r['id']} {r['solver']:<16} dec={r['cand_dec']:.12f} ({(r['cand_dec']/OURS_DEC-1)*100:+.3f}% vs ours) pre={r['cand_pre']:.12f} ({(r['cand_pre']/OURS_PRE-1)*100:+.3f}%) cs={cscore(r['cand_dec'],r['cand_pre']):.6f} pub={r['score']:.6f} {r['ts'][:10]}")
print('\n=== 12 FASTEST CANDIDATE PREFILL ===')
for r in bp:
    print(f"{r['id']} {r['solver']:<16} pre={r['cand_pre']:.12f} ({(r['cand_pre']/OURS_PRE-1)*100:+.3f}% vs ours) dec={r['cand_dec']:.12f} ({(r['cand_dec']/OURS_DEC-1)*100:+.3f}%) cs={cscore(r['cand_dec'],r['cand_pre']):.6f} pub={r['score']:.6f} {r['ts'][:10]}")

# per-solver best
print('\n=== PER-SOLVER BEST (by common-baseline score) ===')
bysolver = defaultdict(list)
for r in rows:
    bysolver[r['solver']].append(r)
tab = []
for s, rs in bysolver.items():
    best = max(rs, key=lambda r: cscore(r['cand_dec'], r['cand_pre']))
    mind = min(r['cand_dec'] for r in rs)
    minp = min(r['cand_pre'] for r in rs)
    tab.append((cscore(best['cand_dec'], best['cand_pre']), s, len(rs), best, mind, minp))
tab.sort(reverse=True)
for cs, s, n, best, mind, minp in tab[:15]:
    print(f"{s:<18} n={n:<5} bestCS={cs:.6f}  bestRcpt={best['id']} dec={best['cand_dec']:.12f} pre={best['cand_pre']:.12f} | minDec={mind:.12f} ({(mind/OURS_DEC-1)*100:+.3f}%) minPre={minp:.12f} ({(minp/OURS_PRE-1)*100:+.3f}%)")

# prefill distribution among the fast pack
fast = [r for r in rows if r['cand_dec'] < 0.0060]
print(f"\n=== PREFILL SPREAD AMONG FAST-DECODE PACK (cand_dec<6.0ms), n={len(fast)} ===")
ps = sorted(r['cand_pre'] for r in fast)
for q in (0, 1, 5, 25, 50, 75, 95, 100):
    i = min(len(ps)-1, int(round(q/100*(len(ps)-1))))
    print(f"  p{q:<4} {ps[i]:.12f}  ({(ps[i]/OURS_PRE-1)*100:+.3f}% vs ours)")
print(f"  ours {OURS_PRE:.12f}")
print(f"  mean {st.mean(ps):.12f} sd {st.pstdev(ps):.12f} cv {st.pstdev(ps)/st.mean(ps)*100:.3f}%")

# how many distinct prefill values? clustering signature
vals = defaultdict(int)
for r in fast:
    vals[round(r['cand_pre'], 12)] += 1
print(f"  distinct cand_pre values among fast pack: {len(vals)}")
top = sorted(vals.items(), key=lambda kv: -kv[1])[:8]
for v, c in top:
    print(f"    {v:.12f} x{c} ({(v/OURS_PRE-1)*100:+.3f}%)")

# decode spread among the fast pack
ds = sorted(r['cand_dec'] for r in fast)
print(f"\n=== DECODE SPREAD AMONG FAST PACK ===")
for q in (0, 1, 5, 25, 50, 75, 95, 100):
    i = min(len(ds)-1, int(round(q/100*(len(ds)-1))))
    print(f"  p{q:<4} {ds[i]:.12f}  ({(ds[i]/OURS_DEC-1)*100:+.3f}% vs ours)")
print(f"  ours {OURS_DEC:.12f}")

# Pareto frontier
print('\n=== PARETO FRONTIER (candidate raw timings) ===')
srt = sorted(rows, key=lambda r: r['cand_dec'])
bestp = float('inf')
par = []
for r in srt:
    if r['cand_pre'] < bestp:
        bestp = r['cand_pre']
        par.append(r)
for r in par[:25]:
    print(f"{r['id']} {r['solver']:<16} dec={r['cand_dec']:.12f} pre={r['cand_pre']:.12f} cs={cscore(r['cand_dec'],r['cand_pre']):.6f} {r['ts'][:10]}")
