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
    ("routed_shared_nvfp4_down_residual", 39, 48.5, 5.311, 32, "1 k-block, 4 rows/simd"),
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

# The profile sums to gpu_busy_union 9.498 ms; the wall step is 8.769 ms.
PROFILE_MS = 9.498
STEP_MS = 8.769
FRAME = STEP_MS / PROFILE_MS

print(f"{'dispatch':38} {'n':>3} {'MB':>7} {'GB/s':>6} {'ceil':>6} "
      f"{'us/call':>8} {'pred':>7} {'gap/step':>9}")
total_measured = total_predicted = 0.0
gaps = []
for name, n, us, mb, inflight, note in DISPATCHES:
    achievable = interp(SIZE_CURVE, mb) * interp(INFLIGHT_CURVE, inflight)
    predicted = max(DISPATCH_FLOOR_US, mb * 1.048576e6 / (achievable * 1e3))
    gap = max(0.0, us - predicted) * n
    total_measured += us * n
    total_predicted += min(us, predicted) * n
    gaps.append((gap, name, note))
    print(f"{name:38} {n:3d} {mb:7.3f} {mb * 1.048576e6 / (us * 1e3):6.1f} "
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
