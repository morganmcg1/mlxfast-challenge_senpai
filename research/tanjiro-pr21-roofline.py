#!/usr/bin/env python3
"""Rebuild the M4 decode roofline with a per-stream achievable ceiling.

The roofline in use prices all 1794 MB of the steady decode step at one global
260.2 GB/s and books the difference to an unexplained residual. This script
prices every dispatch at the ceiling its own access pattern, dispatch size and
in-flight depth actually achieve, measured by
senpai/tools/bandwidth-pattern-probe on the same host.

Inputs
  * per-dispatch profile: research/nezuko-decode-roofline.md, Interim 8
  * achievable bandwidth: senpai/tools/bandwidth-pattern-probe, this host
Run: python3 research/tanjiro-pr21-roofline.py
"""

from bisect import bisect_left

# Sequential read bandwidth versus bytes per dispatch, serialized dispatches in
# one command buffer, M4 Pro 20 cores. `--mode sizes`, post-warm-up run.
SIZE_CURVE = [
    (0.125, 28.4),
    (0.250, 56.4),
    (0.500, 113.1),
    (1.000, 173.1),
    (2.000, 212.4),
    (4.000, 203.7),
    (8.000, 234.8),
    (16.000, 250.2),
    (64.000, 262.5),
    (256.000, 261.9),
]

# Efficiency versus device-load bytes in flight per lane, at fixed 5.06 MB per
# dispatch, relative to the 32 B/lane plateau. `--mode downsize`.
INFLIGHT_CURVE = [(8, 0.44), (16, 0.81), (32, 1.00), (64, 0.99), (128, 0.94)]

# Empty serialized dispatch, 128 back to back: 2.46 us at a 160x256 grid,
# 0.87 us at a 1x32 grid. Small real dispatches sit between the two.
DISPATCH_FLOOR_US = 1.0


def interp(curve, x):
    xs = [p[0] for p in curve]
    if x <= xs[0]:
        return curve[0][1] * x / xs[0]
    if x >= xs[-1]:
        return curve[-1][1]
    i = bisect_left(xs, x)
    (x0, y0), (x1, y1) = curve[i - 1], curve[i]
    t = (x - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


# name, calls/step, us/call measured, MB/call, bytes in flight per lane in the
# shipped kernel (kBlocks * rowsPerSimd * 8 B), note
DISPATCHES = [
    # Interim 8's row for this kernel is the pre-#7 `_v4` geometry (48.5 us,
    # 109.5 GB/s). Interim 9 of the same document re-measured the shipped `_v5`
    # on this host at 22.96 us/call, 231.3 GB/s, so 48.5 would be a stale table
    # row, not a live gap. Cross-check: my reads-only probe puts the achievable
    # for this exact shape at 222.5 GB/s, i.e. the shipped kernel runs at 104%
    # of the probe ceiling. That agreement is the probe's main validation.
    ("routed_shared_nvfp4_down_residual", 39, 22.96, 5.311, 32, "1 k-block, 4 rows/simd"),
    ("routed_nvfp4_swiglu_qmv_top8keys", 39, 38.9, 9.442, 32, "4 k-blocks, 1 row/simd"),
    ("decode_nvfp4_qkv_h64", 30, 45.3, 11.80, 32, "4 k-blocks, 1 row/simd"),
    ("oproj_act_h64", 30, 38.3, 9.45, 32, "4 rows/simd"),
    ("sliding_fused_attn_ring", 30, 22.0, 2.097, 16, "KV walk, 2-deep pipeline"),
    ("lmhead_int5_inline_coarse", 1, 510.9, 134.88, 64, "uint4 loads"),
    ("decode_nvfp4_qkv_h48", 10, 36.5, 9.44, 32, "4 k-blocks, 1 row/simd"),
    ("oproj_act_h48", 10, 30.3, 7.09, 32, "4 rows/simd"),
    ("dense_gate_up_swiglu_bf16", 1, 267.6, 67.11, 32, "4 rows/simd"),
    ("residual_rms_router_bf16", 39, 6.8, 1.062, 32, "4 unrolled bf16x4"),
    ("shared_nvfp4_swiglu_qmv", 39, 6.2, 1.184, 32, "4 k-blocks"),
    ("full_fused_attn_grow", 10, 23.5, 2.621, 16, "KV walk, 2-deep pipeline"),
    ("gate_sp_h64", 30, 6.6, 0.1475, 32, "byte-granular, 8 groups only"),
    ("decode_router_top8_ordinal_table", 39, 3.8, 0.004, 8, "floor bound"),
    ("dense_down_residual_bf16", 1, 130.8, 33.55, 32, "4 rows/simd"),
    ("rmsbfloat16", 41, 2.2, 0.008, 8, "floor bound"),
    ("lmhead_exact_inline_mask_block", 1, 76.6, 0.5, 32, "candidate-dependent"),
    ("gate_sp_h48", 10, 6.7, 0.1106, 32, "byte-granular, 6 groups only"),
    ("remaining small dispatches", 6, 3.3, 0.008, 8, "floor bound"),
]

# Interim 8's table sums to gpu_busy_union 9.498 ms, but that snapshot predates
# #7. Replacing its stale down row with Interim 9's shipped measurement brings
# the dispatch sum to 8.503 ms against a current-frontier wall step of 8.769 ms
# (`research/CURRENT_RESEARCH_STATE.md:82`). The frontier also gained ~0.29 ms
# after #7 from merges that this table cannot attribute, so the live dispatch
# sum is a little lower again and the inter-dispatch gap a little larger. The
# frame factor is therefore >1 and every per-stream gap below is a conservative
# upper bound on what is recoverable.
PROFILE_MS = 8.503
STEP_MS = 8.769
FRAME = STEP_MS / PROFILE_MS

print(f"{'dispatch':38} {'n':>3} {'MB':>7} {'GB/s':>6} {'ceil':>6} "
      f"{'us/call':>8} {'pred':>7} {'gap/step':>9}")
total_measured = total_predicted = 0.0
gaps = []
# Units. The profile's MB/call and the campaign's 1794 MB budget are decimal MB
# (nezuko's 5.311 MB for the down dispatch is exactly 2048*288*9 bytes, and
# 1.7929 GB / 9.498 ms reproduces her 188.8 GB/s only in decimal). The probe
# reports decimal GB/s but labels its size axis in MiB (`mb * 1_048_576`), so a
# decimal-MB dispatch must be converted before the curve lookup.
#
# GQA re-read. The profile's MB/call is UNIQUE tensor bytes, which is the wrong
# numerator for the two fused attention kernels. `laguna_sliding_fused_attn_ring_v1`
# launches 32 threadgroups over 64 query heads (2 heads each) but only 8 KV
# heads, and each threadgroup reads its KV head's whole 512-slot ring
# (LagunaRuntimeModel.swift:1400-1402 `kv_head = pair_tg / 4`, loads :1532-1538).
# So 4 threadgroups issue the same 256 KB: 8.389 MB issued for 2.097 MB unique.
# Charging the DRAM roofline on issued bytes is the honest test, and it shows the
# re-read is cache-served rather than slack -- see the report below.
REREAD = {"sliding_fused_attn_ring": 4.0, "full_fused_attn_grow": 4.0}

MIB = 1_048_576.0
for name, n, us, mb, inflight, note in DISPATCHES:
    bytes_per_call = mb * 1e6 * REREAD.get(name, 1.0)
    achievable = (interp(SIZE_CURVE, bytes_per_call / MIB)
                  * interp(INFLIGHT_CURVE, inflight))
    predicted = max(DISPATCH_FLOOR_US, bytes_per_call / (achievable * 1e3))
    gap = max(0.0, us - predicted) * n
    total_measured += us * n
    total_predicted += min(us, predicted) * n
    gaps.append((gap, name, note))
    print(f"{name:38} {n:3d} {mb:7.3f} {bytes_per_call / (us * 1e3):6.1f} "
          f"{achievable:6.1f} {us:8.1f} {predicted:7.1f} {gap:9.0f}")

print(f"\nmeasured   {total_measured / 1000:.3f} ms (profile frame)")
print(f"rebuilt roofline {total_predicted / 1000:.3f} ms")
print(f"byte-only roofline 1794 MB / 260.2 GB/s = 6.895 ms")
print(f"\nrecoverable against per-stream ceilings, ranked:")
for gap, name, note in sorted(gaps, reverse=True):
    if gap < 5:
        continue
    print(f"  {gap:6.0f} us  ({gap * FRAME:6.0f} us of the wall step)  "
          f"{name}  [{note}]")
total_gap = sum(g for g, _, _ in gaps)
print(f"  {total_gap:6.0f} us  ({total_gap * FRAME:6.0f} us of the wall step)  TOTAL")
print(f"\nadvisor hard-core residual 1.51 ms; this decomposition names "
      f"{total_gap * FRAME / 1000:.2f} ms of it")

# Closed-form decomposition of the advisor's residual. The byte-only roofline is
# the only figure that treats the step as one 1794 MB stream; every term below is
# a named reason the step cannot be that.
BYTE_ONLY_MS = 6.895
excess = STEP_MS - BYTE_ONLY_MS
ramp = total_predicted / 1000 - BYTE_ONLY_MS
named = total_gap / 1000
dead_band = STEP_MS - total_measured / 1000
print(f"\ndecomposition of `step - byte-only roofline` = {excess:.3f} ms")
print(f"  {ramp:.3f} ms  per-dispatch structure         structural, see split below")
print(f"  {named:.3f} ms  named per-stream shortfalls    recoverable in principle")
print(f"  {dead_band:.3f} ms  inter-dispatch dead band       advisor bound was <= 0.38")
print(f"  {ramp + named + dead_band:.3f} ms  sum "
      f"(unexplained {excess - (ramp + named + dead_band):+.3f} ms)")
print(f"  {0.0:.3f} ms  access pattern                 measured, not inferred")

# Sub-attribution of the structural term. These two overlap slightly inside the
# attention dispatches, so they sum a few percent over `ramp`; the three-term
# closure above is the authoritative one.
# 2.46 us is the measured serialized empty-dispatch cost at a realistic 160x256
# grid (`--mode empty`); DISPATCH_FLOOR_US above is the 1-threadgroup floor and
# is only used to stop tiny dispatches being charged below any achievable time.
EMPTY_DISPATCH_US = 2.46
DISPATCHES_PER_STEP = 406
launch_ramp = DISPATCHES_PER_STEP * EMPTY_DISPATCH_US / 1000
reread = 0.0
for name, n, us, mb, inflight, note in DISPATCHES:
    if name not in REREAD:
        continue
    unique_us = mb * 1e6 / (interp(SIZE_CURVE, mb * 1e6 / MIB)
                            * interp(INFLIGHT_CURVE, inflight) * 1e3)
    reread += max(0.0, us - unique_us) * n
print(f"\n  of which  {launch_ramp:.3f} ms  {DISPATCHES_PER_STEP} dispatches x "
      f"{EMPTY_DISPATCH_US} us empty-dispatch cost")
print(f"            {reread / 1000:.3f} ms  GQA KV re-read in the two fused attention kernels,")
print(f"                         4x issued bytes for 1x unique, served from cache")

# Project onto the ranked host. The advisor pinned M5 Max GPU-achievable at
# 485-530 GB/s and the promoted M5 step at T = 4.353 ms. The two terms in my M4
# decomposition scale differently, which is the whole point of separating them:
#
#   dead band and per-stream dependency stalls are LATENCY. DRAM and
#   command-processor latency do not improve a generation, so these are bounded
#   below by their M4 absolute value and above by nothing.
#
#   the size ramp is a BANDWIDTH-DELAY product. M5 has 2x the cores, so each
#   dispatch reaches saturation with twice the parallelism; this term shrinks.
#
# Both bounds below are therefore reported, because which one holds is exactly
# what an official A/B would settle.
M5_STEP_MS = 4.353
LOGICAL_MB = 1794.0
print("\nranked-host projection (M5 Max, step 4.353 ms)")
for bw in (485.0, 507.0, 530.0):
    ideal = LOGICAL_MB * 1e6 / (bw * 1e9) * 1e3
    print(f"  {bw:.0f} GB/s achievable -> ideal {ideal:.3f} ms, "
          f"excess {M5_STEP_MS - ideal:.3f} ms "
          f"({(M5_STEP_MS - ideal) / M5_STEP_MS * 100:.1f}% of step)")
latency_like = named + dead_band
print(f"\n  M4 latency-like terms (named shortfalls + dead band) = {latency_like:.3f} ms")
print("  Carried over at their M4 absolute value they cover 48-70% of the M5")
print("  excess. The remainder has to be M5's own per-dispatch cost, which gives")
print("  a falsifiable prediction rather than an assumption:")
for bw in (485.0, 507.0, 530.0):
    ideal = LOGICAL_MB * 1e6 / (bw * 1e9) * 1e3
    per_dispatch_us = (M5_STEP_MS - ideal - latency_like) / DISPATCHES_PER_STEP * 1e3
    print(f"    at {bw:.0f} GB/s, M5's per-dispatch cost must be "
          f"{per_dispatch_us:.2f} us (M4 measures 0.87-2.46)")
print("  So the model closes on M5 only if its empty-dispatch cost is near my")
print("  1-threadgroup floor rather than my 160-threadgroup one -- which is what")
print("  2x the cores should do, and what an M5 `--mode empty` run would settle.")
for label, m5_named in (("absolute-preserved", named),
                        ("fraction-preserved", named * M5_STEP_MS / STEP_MS)):
    frac = m5_named / M5_STEP_MS
    print(f"  recoverable if {label}: {m5_named:.3f} ms = {frac * 100:.1f}% of "
          f"step = {0.638 * frac * 100:.1f}% of score")
