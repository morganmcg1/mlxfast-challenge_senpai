import re, datetime
from collections import Counter

rows = []
for line in open('/tmp/subs_all.txt'):
    parts = line.split()
    if len(parts) < 4:
        continue
    sub, solver, status, score = parts[0], parts[1], parts[2], parts[3]
    if not re.fullmatch(r'[0-9a-f]{7}', sub):
        continue
    try:
        s = float(score)
    except ValueError:
        s = None
    m = re.search(r'(\d+/\d+/\d+, \d+:\d+ [AP]M)\s*$', line)
    dt = datetime.datetime.strptime(m.group(1), '%m/%d/%y, %I:%M %p') if m else None
    rows.append(dict(sub=sub, solver=solver, status=status, score=s, dt=dt))

rows = [r for r in rows if r['dt']]
rows.sort(key=lambda r: r['dt'])

prom = [r for r in rows if r['status'].startswith('promot') and r['score']]
print("=== LAST 25 PROMOTIONS (frontier history) ===")
for r in prom[-25:]:
    print("%s  %s  %-20s %.10f" % (r['dt'], r['sub'], r['solver'], r['score']))
print("total promotions: %d" % len(prom))

crown = max(prom, key=lambda r: r['score'])
print("\nCROWN: %s %s %.12f at %s" % (crown['sub'], crown['solver'], crown['score'], crown['dt']))

after = [r for r in rows if r['dt'] > crown['dt']]
sc = [r for r in after if r['score']]
print("submissions AFTER crown: %d (scored %d)" % (len(after), len(sc)))
if sc:
    print("  max score since crown: %.10f" % max(r['score'] for r in sc))
beat = [r for r in sc if r['score'] > crown['score']]
print("  beating crown: %d" % len(beat))
print("  distinct solvers active since crown: %d" % len(set(r['solver'] for r in after)))
print("  last submission overall: %s" % rows[-1]['dt'])

# how close did anyone get since the crown
top_since = sorted(sc, key=lambda r: -r['score'])[:12]
print("\n=== TOP 12 SINCE CROWN ===")
for r in top_since:
    gap = (crown['score'] - r['score']) / crown['score'] * 100
    print("%s %-20s %.10f   gap %.3f%%   %s" % (r['sub'], r['solver'], r['score'], gap, r['dt']))

# per-solver best, to see the real competitive field
best = {}
for r in rows:
    if r['score'] and (r['solver'] not in best or r['score'] > best[r['solver']]):
        best[r['solver']] = r['score']
print("\n=== TOP 15 SOLVERS BY BEST-EVER SCORE ===")
for k, v in sorted(best.items(), key=lambda kv: -kv[1])[:15]:
    n = sum(1 for r in rows if r['solver'] == k)
    print("%-22s best=%.10f  n=%d" % (k, v, n))

# daily submission volume, last 8 days
print("\n=== DAILY VOLUME (all solvers) ===")
c = Counter(r['dt'].date() for r in rows)
for d in sorted(c)[-9:]:
    cm = Counter(r['dt'].date() for r in rows if r['solver'] == 'morganmcg1')
    print("%s  total=%3d   morganmcg1=%d" % (d, c[d], cm.get(d, 0)))
