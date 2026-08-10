#!/usr/bin/env python3
"""R108-N stage 1: static issue-slot census of laguna_sliding_fused_attn_ring_v1.

Every count below is a source-level operation count against
Sources/MLXFastModel/LagunaRuntimeModel.swift at base 705484b9, with the line
range recorded in the note.  Slot expansions for composite operations
(simd_sum, exp, divide) are named explicitly so a later measurement can replace
an assumption instead of the whole table.

Host: M4 Pro (Apple GPU arch gen 16, no _nax).  Epoch: base 705484b9.
Anchors are the R107-D (#642) sliding fma dose on the same host and epoch.
"""

# ---------------------------------------------------------------- expansions
SIMD_REDUCE = 10   # 5 simd_shuffle_xor + 5 arithmetic, 32 lanes
EXP = 2            # mul by log2(e) + hardware exp2
DIV = 5            # reciprocal + refine + mul, fp32, default math mode
ROWS = 16          # 4 loop iterations x 4 unrolled row stages
ITERS = 4

# ------------------------------------------------------- measured anchors, M4
PROBE_BASE_US = 4.248 / 0.24503        # dose-16 arm: +4.248 us == +24.503 %
FMA_SLOT_US = 4.248 / 512.0           # us per fma-per-thread per dispatch
MEASURED_SLOTS = PROBE_BASE_US / FMA_SLOT_US
SLIDING_DISPATCHES = 30
T3A_M4_US_STEP = 618.9                # corrected value, rule 100.3
CS_PER_M5_US = 0.015228               # % of composite score per M5 us/step
K_ISSUE_LO, K_ISSUE_HI = 0.267, 0.654  # R107-G closure bracket
RULE100_CS_PER_FMA = 0.002097         # % of cs per fma-per-thread removed
BAR_CS = 0.4

# ------------------------------------------------------------------- classes
# (class, slots, removable-class, note)
#   removable-class 0 = irreducible
#                   1 = arithmetic-identical, source-level arguable
#                   2 = reassociation, needs a margin certificate
#                   3 = duration-only / architectural, not an instruction trim
#                   4 = different kernel family (simdgroup MMA)
rows = [
    # ---- main loop, per thread, 16 row stages -----------------------------
    ("main: device vec4 loads (K,V)", 2 * ROWS, 0, "bf16 64-bit loads"),
    ("main: ring-substitution predicate+branch", (3 + 4) * ITERS + 2 * ROWS, 1,
     "uniform test; hoistable by peeling the single widx row"),
    ("main: bf16->f32 converts", 8 * ROWS, 0, "cache is bf16, fma needs fp32"),
    ("main: QK fma", 8 * ROWS, 4, "4 dims x 2 heads; MMA-expressible"),
    ("main: simd_sum over 32 lanes (QK)", 2 * SIMD_REDUCE * ROWS, 4,
     "lane-per-dim layout forces a cross-lane reduce per row"),
    ("main: running max", 2 * ROWS, 0, ""),
    ("main: rescale predicate (sub+as_type cmp+branch)", 6 * ROWS, 0,
     "already an optimisation: skips exp when the max is unchanged"),
    ("main: rescale exp", 2 * EXP * ROWS, 0, ""),
    ("main: score exp (sub+exp)", 2 * (1 + EXP) * ROWS, 0, ""),
    ("main: softmax denominator fma", 2 * ROWS, 0, ""),
    ("main: accumulator rescale mul (o*f or e*v)", 8 * ROWS, 2,
     "multiply by exactly 1.0 whenever the max is unchanged"),
    ("main: accumulator fma", 8 * ROWS, 0, ""),
    ("main: pointer arithmetic + loop control", (6 + 2 + 3) * ITERS, 1,
     "strength-reduced already; 6 offsets vs 8 induction bumps is a wash"),
    # ---- prologue --------------------------------------------------------
    ("prologue: base pointers, q scale, zero init", 44, 0,
     "q premultiply by scale is already hoisted out of the loop"),
    ("phase A: K/Q RMSNorm+RoPE, sg<3, issue-amortised", 6, 3,
     "~60 slots on 3 of 32 simdgroups; redundant across the 4 TGs per kv head"),
    # ---- epilogue --------------------------------------------------------
    ("epilogue: threadgroup transpose stores/loads + index", 11, 1,
     "second transpose cannot be merged: 33.8 KB > 32 KB tg cap"),
    ("epilogue: simd_max", 2 * SIMD_REDUCE, 0, ""),
    ("epilogue: global-factor exp", 2 * (1 + EXP), 0, ""),
    ("epilogue: denominator simd_sum + mul", 2 * SIMD_REDUCE + 2 + 2, 0, ""),
    ("epilogue: output simd_sum (2 heads x 4 dims)", 8 * SIMD_REDUCE, 4, ""),
    ("epilogue: output scale mul", 8, 0, ""),
    ("epilogue: normalise divide + select", 8 * DIV + 8, 2,
     "8 divides by 2 distinct denominators; 2 reciprocals would do"),
    ("epilogue: barriers, bf16 stores (lane==0, amortised)", 4, 0, ""),
]

removable_net = {
    1: [("M2 ring-predicate peel", 40), ("M4 epilogue transpose merge", 4)],
    2: [("M1 factor==1 accumulator fast path", 96),
        ("M3 epilogue reciprocal", 24)],
    3: [("M5 cross-TG redundant K RMSNorm+RoPE", 5)],
    4: [("M7 simdgroup-MMA QK reduction", 275)],
}

total = sum(r[1] for r in rows)
print(f"{'class':58s} {'slots':>6s} {'%tot':>6s}  rem  note")
for name, slots, rc, note in sorted(rows, key=lambda r: -r[1]):
    print(f"{name:58s} {slots:6d} {100*slots/total:5.1f}%   {rc}   {note}")
print(f"{'TOTAL static census (issue slots/thread)':58s} {total:6d}")
print()
print(f"measured budget (R107-D fma dose, M4)      "
      f"{MEASURED_SLOTS:8.0f} slots/thread/dispatch")
print(f"  probe base                               {PROBE_BASE_US:8.3f} us/dispatch")
print(f"  shipped T3a per dispatch                 "
      f"{T3A_M4_US_STEP/SLIDING_DISPATCHES:8.3f} us/dispatch")
print(f"  fma slot price                           {FMA_SLOT_US:8.6f} us/slot")
print(f"  static census coverage of measured       {100*total/MEASURED_SLOTS:8.1f} %")
print()


def price(slots, label):
    d_m4 = slots * FMA_SLOT_US * SLIDING_DISPATCHES
    lo = d_m4 * K_ISSUE_LO * CS_PER_M5_US
    hi = d_m4 * K_ISSUE_HI * CS_PER_M5_US
    r100 = slots * RULE100_CS_PER_FMA
    print(f"{label:46s} {slots:5d} slots  {100*slots/total:5.1f}% static "
          f"{100*slots/MEASURED_SLOTS:5.1f}% measured  "
          f"{d_m4:6.1f} M4 us/step  cs {lo:.3f}..{hi:.3f} % (k) "
          f"| {r100:.3f} % (rule100)")


cum = 0
for rc in (1, 2, 3, 4):
    for name, slots in removable_net[rc]:
        price(slots, f"  {name}")
    cum += sum(s for _, s in removable_net[rc])
    price(cum, f"CUMULATIVE through removable-class {rc}")
    print()

need_lo = BAR_CS / (K_ISSUE_LO * CS_PER_M5_US) / SLIDING_DISPATCHES / FMA_SLOT_US
need_hi = BAR_CS / (K_ISSUE_HI * CS_PER_M5_US) / SLIDING_DISPATCHES / FMA_SLOT_US
need_r100 = BAR_CS / RULE100_CS_PER_FMA
print(f"slots/thread needed for the {BAR_CS} % bar:")
print(f"  k_issue=0.267 (conservative) {need_lo:7.1f}  "
      f"({100*need_lo/MEASURED_SLOTS:.1f} % of measured budget)")
print(f"  k_issue=0.654 (optimistic)   {need_hi:7.1f}  "
      f"({100*need_hi/MEASURED_SLOTS:.1f} % of measured budget)")
print(f"  rule-100 direct instrument   {need_r100:7.1f}  "
      f"({100*need_r100/MEASURED_SLOTS:.1f} % of measured budget); "
      f"implied k_issue = "
      f"{BAR_CS/(need_r100*FMA_SLOT_US*SLIDING_DISPATCHES*CS_PER_M5_US):.3f}")
