"""Does candidate-side relative noise depend on how fast the candidate is?

Section 9 extrapolates the baseline's CV (measured at 13855 us decode) toward our
regime (~4900 us). That is only legitimate if noise is multiplicative rather than
additive. Residuals are taken within solver-day groups so that code differences
are absorbed.
"""
import json
import statistics as st
import sys
from collections import defaultdict

r = json.load(open(sys.argv[1] if len(sys.argv) > 1
                   else "research/r93-runs/receipts-latest.json"))
g = defaultdict(list)
for x in r:
    g[(x["solver"], x["ts"][:10])].append(x)

for axis, ka in [("decode", "cand_dec"), ("prefill", "cand_pre")]:
    pts = []
    for v in g.values():
        if len(v) < 4:
            continue
        a = [x[ka] * 1e6 for x in v]
        m = st.mean(a)
        # near-replicate groups only: otherwise the "residual" is real code change
        if 100 * st.stdev(a) / m >= 0.6:
            continue
        for z in a:
            pts.append((m, z - m))
    if len(pts) < 40:
        print("%s: too few near-replicate points (%d)" % (axis, len(pts)))
        continue
    pts.sort()
    k = 4
    per = len(pts) // k
    print("=" * 74)
    print("%s  (near-replicate solver-day groups, n=%d points)" % (axis, len(pts)))
    print("  %-22s %-6s %-12s %-12s" % ("group-mean band (us)", "n", "resid sd", "resid CV"))
    for i in range(k):
        chunk = pts[i * per:(i + 1) * per] if i < k - 1 else pts[i * per:]
        mm = st.mean([c[0] for c in chunk])
        sd = st.pstdev([c[1] for c in chunk]) * (len(chunk) / (len(chunk) - 1)) ** 0.5
        print("  %8.1f - %8.1f    %-6d %-12.3f %.4f%%"
              % (chunk[0][0], chunk[-1][0], len(chunk), sd, 100 * sd / mm))
    print("  If resid CV is roughly flat across bands, noise is multiplicative and")
    print("  the baseline CV extrapolates to our regime. If resid sd is flat")
    print("  instead, noise is additive and the CV extrapolation overstates it.")
    print()
