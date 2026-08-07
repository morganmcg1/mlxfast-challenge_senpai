#!/usr/bin/env python3
"""PR284 step 1 analysis: price every coarser bit-plane tier from the captured
certificate-slack histogram.

Reads research/artifacts/nezuko-pr284-slack-hist.txt (one
`SLACKHIST c1 c2 c3 c5 c7 c9 c13 c17 c25 c33` line per decode step) and reports,
for each candidate tier-0 bit width, the mean bytes moved per decode step and
the projected M5 saving against the 80 us/step significance floor.
"""
import statistics
import sys

CUTS = [1, 2, 3, 5, 7, 9, 13, 17, 25, 33]
V = 100352
SCALES = 64          # e8m0 group scales, bytes/row
PLANE = 256          # bytes/row per stored bit of the 5-bit code (2048/8)
M5_BPS = 433e9       # advisor's measured M5 decode bandwidth
FLOOR_US = 80.0      # 3-sigma decode significance floor
DECODE_US = 4143.569335937499
SENS_PCT_PER_US = 0.015280   # score % per us/step saved

path = sys.argv[1] if len(sys.argv) > 1 else \
    "research/artifacts/nezuko-pr284-slack-hist.txt"
rows = [[int(v) for v in ln.split()[1:]] for ln in open(path)
        if ln.startswith("SLACKHIST")]
if not rows:
    raise SystemExit("no SLACKHIST lines in " + path)

col = {c: [r[i] for r in rows] for i, c in enumerate(CUTS)}
print(f"{len(rows)} decode steps captured\n")
print(f"{'R<=T':>6} {'mean':>9} {'median':>9} {'min':>8} {'max':>8} "
      f"{'%vocab':>8}")
for c in CUTS:
    v = col[c]
    print(f"{c:>6} {statistics.mean(v):9.1f} {statistics.median(v):9.1f} "
          f"{min(v):8d} {max(v):8d} {100*statistics.mean(v)/V:8.3f}")

S1 = statistics.mean(col[1])
S9 = statistics.mean(col[9])
S17 = statistics.mean(col[17])
S5 = statistics.mean(col[5])

# Today: 4-bit plane for every row, then the residual bit for R<=1 survivors.
today = V * (4 * PLANE + SCALES) + PLANE * S1


def report(name, tier0_bits, extra):
    """extra: list of (bytes_per_row, mean_row_count) for each refinement tier."""
    tot = V * (tier0_bits * PLANE + SCALES) + sum(b * n for b, n in extra)
    saved = today - tot
    us = saved / M5_BPS * 1e6
    verdict = "LIVE" if us >= FLOOR_US else "DEAD"
    print(f"{name:<34} bytes/step {tot/1e6:8.2f} MB  saved {saved/1e6:7.2f} MB"
          f"  {us:7.1f} us  {us*SENS_PCT_PER_US:+6.2f}%  {verdict}")


print(f"\nbaseline (4-bit tier-0) bytes/step {today/1e6:.2f} MB"
      f"  = {today/M5_BPS*1e6:.1f} us on M5 @ {M5_BPS/1e9:.0f} GB/s"
      f"  ({today/M5_BPS*1e6/DECODE_US*100:.2f}% of decode step)\n")
print(f"{'design':<34} {'':>18} {'':>13} {'M5 save':>9} {'score':>7}")
report("3-bit tier-0 -> +1b @R<=5 -> +1b @R<=1",
       3, [(PLANE, S5), (PLANE, S1)])
report("2-bit tier-0 -> +2b @R<=9 -> +1b @R<=1",
       2, [(2 * PLANE, S9), (PLANE, S1)])
report("1-bit tier-0 -> +1b @R<=17 -> +2b @R<=9 -> +1b @R<=1",
       1, [(PLANE, S17), (2 * PLANE, S9), (PLANE, S1)])
report("2-bit side plane (keep lo/hi, reread 4b @R<=9)",
       2, [(4 * PLANE, S9), (PLANE, S1)])

print(f"\nfloor: a design must save >= {FLOOR_US:.0f} us/step "
      f"({FLOOR_US*SENS_PCT_PER_US:+.2f}% score) to be measurable on M5.")

# Robustness. The drop bracket above is the sound one: level j drops row r only
# if thr - c_1 > B_1 + 2*B_j, i.e. R > 1 + 2^j, because c_j is bounded away
# from the measured c_1 only through the triangle inequality via the true
# logit. If instead the c_j - c_1 difference is assumed to concentrate (it is a
# 2048-term signed sum, so ~1/sqrt(2048) of its worst case), the bracket
# collapses to the unsound-but-optimistic R > B_j/delta = 2^(j-1). Both are
# reported: if even the optimistic bracket misses the floor, no accounting of
# the c_j - c_1 term can rescue the design.
print("\noptimistic bracket (UNSOUND upper bound on what any coarser tier-0 "
      "could achieve):")
opt = {3: 2, 2: 4, 1: 8}
for bits, cut in opt.items():
    nearest = min(CUTS, key=lambda c: abs(c - cut))
    kept = statistics.mean(col[nearest])
    tot = V * (bits * PLANE + SCALES) + (4 - bits) * PLANE * kept + PLANE * S1
    us = (today - tot) / M5_BPS * 1e6
    print(f"  {bits}-bit tier-0, drop if R>{cut} (using measured R<={nearest}): "
          f"{V-kept:8.0f} rows drop -> {us:7.1f} us  "
          f"{'LIVE' if us >= FLOOR_US else 'DEAD'}")

print(f"\nrequirement for ANY cheaper tier-0: to drop 90% of rows its certified "
      f"bound must be under ~the 10th percentile of thr-c_1, which the "
      f"histogram places between 1x and 2x today's delta. Halving the code "
      f"width multiplies the bound by 4x. The family is off by ~10x.")
