#!/usr/bin/env python3
"""Deliverable 0 for PR #105: lm-head cascade survivor census + DRAM model.

Input: the archived stat lines (research/maple-fern-pr105-census-raw.txt), or a
raw --local-iterate log produced with DARKBLOOM_LMHEAD_PRUNE_STATS=1.

The probe is a host-side MLX mirror of the tier-1 screen, inserted in
LagunaLmHeadPruner.logits(...) just after `thr` is formed. For each k it counts
rows with (coarse + k*delta) >= thr and the number of live 4-row blocks. The
proposed 3+2 re-split exactly doubles the level-1 cell, so its tier-2 input set
is the k=2.0 column of the refine=true population.
"""
import re
import statistics as st
import sys

V = 100352
HID = 2048
LOG = sys.argv[1] if len(sys.argv) > 1 else "research/maple-fern-pr105-census-raw.txt"

seen = set()
rows = []
for line in open(LOG):
    if "call=" not in line or "k1.0=" not in line:
        continue
    line = line[line.index("call=") :].strip()
    if line in seen:  # --local-iterate starts two workers on identical weights
        continue
    seen.add(line)
    rows.append(
        (
            int(re.search(r"call=(\d+)", line).group(1)),
            re.search(r"refine=(\w+)", line).group(1) == "true",
            {
                float(m.group(1)): (int(m.group(2)), int(m.group(3)))
                for m in re.finditer(r"k([\d.]+)=(\d+)/(\d+)", line)
            },
        )
    )

# calls 1 and 3 are the two one-pass prefill passes; calls 4..131 are the 128
# teacher-forced decode steps of the timed window.
tru = [r for r in rows if r[1] and r[0] >= 4]
fal = [r for r in rows if not r[1]]
print(f"unique stat lines={len(rows)}  timed decode={len(tru)}  prefill={len(fal)}")


def summ(rs, label):
    print(f"\n--- {label} (n={len(rs)}) ---")
    print(
        f"{'k':>5} {'mean':>9} {'med':>8} {'min':>8} {'max':>8} {'%vocab':>7}"
        f" | {'blk_mean':>9} {'%blk':>6}"
    )
    for k in sorted(rs[0][2]):
        s = [r[2][k][0] for r in rs]
        b = [r[2][k][1] for r in rs]
        print(
            f"{k:>5} {st.mean(s):9.1f} {st.median(s):8.0f} {min(s):8d}"
            f" {max(s):8d} {100 * st.mean(s) / V:7.2f}"
            f" | {st.mean(b):9.1f} {100 * st.mean(b) / (V // 4):6.2f}"
        )


summ(tru, "refine=true  (decode: base-plane screen, cell = 1.0*sd)")
summ(fal, "refine=false (prefill one-pass: cell = 0.5*sd)")

m = {k: st.mean([r[2][k][0] for r in tru]) for k in sorted(tru[0][2])}

SC = HID // 32  # e8m0 scale plane, 1 byte per group of 32
B_S1_41 = HID * 4 // 8 + SC  # 4-bit base plane  + scales
B_S1_32 = HID * 3 // 8 + SC  # 3-bit base plane  + scales
B_R_41 = HID * 1 // 8 + SC  # 1-bit residual    + scales (re-read per row)
B_R_32 = HID * 2 // 8 + SC  # 2-bit residual    + scales
B_ONE = HID * 5 // 8 + SC  # pre-PR#20 single fused int5 pass

s1_41, s1_32, onepass = (b * V / 1e6 for b in (B_S1_41, B_S1_32, B_ONE))
r41 = m[1.0] * B_R_41 / 1e6
r32 = m[2.0] * B_R_32 / 1e6

print("\n=== decode per-step DRAM READ, mean over the 128 timed steps ===")
print(f"one-pass (pre-PR#20)   {onepass:8.2f} MB   ({B_ONE} B/row x {V})")
print(f"4+1 today   stage1 {s1_41:7.2f} + refine {r41:6.2f} = {s1_41 + r41:8.2f} MB")
print(f"3+2 propose stage1 {s1_32:7.2f} + refine {r32:6.2f} = {s1_32 + r32:8.2f} MB")

print("\n=== bytes REMOVED (positive = less traffic) ===")
for name, mb in (
    ("3+2 vs 4+1", (s1_41 + r41) - (s1_32 + r32)),
    ("4+1 vs one-pass (PR #20 retro)", onepass - (s1_41 + r41)),
):
    # R20.2 empirical transfer: +0.41% of score per 25.7 MB/step removed,
    # interval [0.25%, 0.70%]. Preferred over a roofline denominator (0.9.39).
    lo, mid, hi = (mb / 25.7 * x for x in (0.25, 0.41, 0.70))
    print(f"  {name:<32} {mb:+7.2f} MB/step")
    print(f"    R20.2 score delta {mid:+6.3f} %  interval [{lo:+.3f} %, {hi:+.3f} %]")

# Break-even: how many tier-2 survivors can 3+2 afford before it loses?
saved = (B_S1_41 - B_S1_32) * V
be = (saved + B_R_41 * m[1.0]) / B_R_32
worst = min(r[2][2.0][0] for r in tru)
best = max(r[2][2.0][0] for r in tru)
print(f"\n3+2 break-even survivors : {be:9.0f} rows ({100 * be / V:.2f} % of vocab)")
print(f"  measured k=2 mean      : {m[2.0]:9.1f} rows ({100 * m[2.0] / V:.2f} %)")
print(
    f"  measured k=2 min / max : {worst:9d} / {best} rows"
    f" ({100 * worst / V:.2f} % / {100 * best / V:.2f} %)"
)
print(f"  steps below break-even : {sum(1 for r in tru if r[2][2.0][0] < be)}/{len(tru)}")
print(f"  closest step overshoot : {worst / be:.3f}x the affordable survivor count")
kstar = 1.5 + 0.5 * (be - m[1.5]) / (m[2.0] - m[1.5])
print(f"  break-even cell radius : k* ~ {kstar:.2f} sd; 3+2 forces exactly k = 2.00")

net = [(saved + B_R_41 * r[2][1.0][0] - B_R_32 * r[2][2.0][0]) / 1e6 for r in tru]
print(
    f"\nper-step net REMOVED, 3+2 vs 4+1 (n={len(net)}): mean {st.mean(net):+.2f} MB"
    f"  range [{min(net):+.2f}, {max(net):+.2f}]"
    f"  half-range {(max(net) - min(net)) / 2:.2f}  sd {st.stdev(net):.2f}"
)
print(f"  steps where 3+2 removes any bytes: {sum(1 for x in net if x > 0)}/{len(net)}")
print(
    f"k=2 survivors (n={len(tru)}): mean {m[2.0]:.0f}"
    f"  half-range {(best - worst) / 2:.0f}"
    f"  sd {st.stdev([r[2][2.0][0] for r in tru]):.0f}"
)
