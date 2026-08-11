import re, datetime, statistics as st

rows = []
for line in open('/tmp/subs_all.txt'):
    p = line.split()
    if len(p) < 4:
        continue
    sub, solver, status, score = p[0], p[1], p[2], p[3]
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

# The leader's replay cluster: a-github-name, scores >= 2.59, from 8/7 onward
lead = [r for r in rows if r['solver'] == 'a-github-name' and r['score'] and r['dt'] >= datetime.datetime(2026, 8, 7)]
print("=== a-github-name submissions since 8/7 (%d) ===" % len(lead))
for r in lead:
    print("  %s %s %.10f %s" % (r['dt'], r['sub'], r['score'], r['status']))

hi = [r['score'] for r in lead if r['score'] >= 2.59]
print("\n--- top cluster (>=2.59), n=%d ---" % len(hi))
if len(hi) > 1:
    m, sd = st.mean(hi), st.stdev(hi)
    print("mean=%.8f  sd=%.8f  relsd=%.4f%%  max=%.8f" % (m, sd, sd / m * 100, max(hi)))

# maple HEAD class
maple = [2.56974410819947, 2.59380735131190, 2.59576526895414]
mm, ms = st.mean(maple), st.stdev(maple)
print("\n=== maple HEAD class n=3 ===")
print("mean=%.8f  sd=%.8f  relsd=%.4f%%" % (mm, ms, ms / mm * 100))

CROWN = 2.61650354381456
print("\n=== P(one maple draw > crown %.8f) ===" % CROWN)
import math
def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))
for label, sd_rel in [("maple own sd 0.5603%", ms / mm), ("pooled 0.45%", 0.0045), ("conservative 0.70%", 0.0070)]:
    z = (CROWN - mm) / (sd_rel * mm)
    p = norm_sf(z)
    print("  %-22s z=%.3f  p=%.4f (%.2f%%)" % (label, z, p, p * 100))
    for n in (10, 20, 36, 57, 100):
        print("       n=%3d -> P(win)=%.1f%%" % (n, (1 - (1 - p) ** n) * 100))

print("\n=== if we improve the mean by X%, p per draw (sd=0.5603%) ===")
for gain in (0.0, 0.25, 0.5, 0.86, 1.16):
    mu = mm * (1 + gain / 100)
    z = (CROWN - mu) / (ms / mm * mu)
    p = norm_sf(z)
    print("  +%.2f%% -> mu=%.5f z=%.2f p=%.2f%%/draw   n=20 -> %.1f%%" % (gain, mu, z, p * 100, (1 - (1 - p) ** 20) * 100))
