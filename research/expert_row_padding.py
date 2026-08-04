import re, math, sys

lines = open('research/prefill-512-route-histogram.txt').read().strip().split('\n')
print("lines:", len(lines))
recs = []
for ln in lines:
    m = re.search(r'counts=\[([^\]]*)\]', ln)
    if not m:
        continue
    c = [int(x) for x in m.group(1).split(',')]
    recs.append(c)
print("records:", len(recs), "experts per rec:", set(len(c) for c in recs))
tot_useful = sum(sum(c) for c in recs)
print("total useful rows:", tot_useful)
allc = [n for c in recs for n in c]
nz = [n for n in allc if n > 0]
print("zero frac: %.4f  mean nonzero: %.2f  median nonzero: %d" % (
    1 - len(nz)/len(allc), sum(nz)/len(nz), sorted(nz)[len(nz)//2]))

def cost(BM, SM):
    """rows actually MMA'd, assuming per-expert chunking in BM blocks and
    per-simdgroup SM-band elision when the band is entirely beyond n_e."""
    rows = 0
    stagings = 0
    for c in recs:
        for n in c:
            if n == 0:
                continue
            chunks = math.ceil(n / BM)
            stagings += chunks
            for ch in range(chunks):
                lo = ch * BM
                valid = min(BM, n - lo)
                bands = math.ceil(valid / SM)
                rows += bands * SM
    return rows, stagings

print()
print("%-22s %12s %8s %12s" % ("config", "MMA rows", "x ideal", "stagings"))
for BM, WM in [(64,4),(64,2),(64,1),(128,4),(128,8),(128,2),(32,2),(32,1)]:
    SM = BM // WM
    r, st = cost(BM, SM)
    print("BM=%-3d WM=%-2d SM=%-3d %12d %8.3f %12d" % (BM, WM, SM, r, r/tot_useful, st))

# uniform-routing control to validate against the organizer's published model
print()
print("uniform control (every expert exactly 16 rows):")
for BM, WM in [(64,4),(64,2)]:
    SM = BM//WM
    n = 16
    bands = math.ceil(n/SM)
    print("  BM=%d SM=%d -> %d rows for 16 useful = %.3fx" % (BM, SM, bands*SM, bands*SM/16))
