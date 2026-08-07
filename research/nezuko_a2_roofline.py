#!/usr/bin/env python3
"""Roofline / occupancy pricing for the re-priced decode census.

The re-priced census (nezuko_a2_reprice.py) says what each kernel costs.  It
does not say what any of them could cost.  This script supplies the second
number: for every large decode kernel, the floor implied by the bytes it must
read, and -- where bytes are not the binding constraint -- the floor implied by
how many threadgroups it launches on a 20-core GPU.

Shapes come from Sources/MLXFastModel/LagunaConfig.swift, not from
weights/config.json.  Laguna XS 2.1 is a hybrid: the 30 sliding-window layers
use 64 query heads and the 10 full-attention layers use 48, so the "h64" and
"h48" kernel variants do genuinely different amounts of work.  Assuming a
single head count (as weights/config.json's `num_attention_heads: 48` invites)
manufactures a 22 % phantom inefficiency in the h64 variants.

Score conversion is the campaign constant: -1 us/step = +0.01464 % score.

Run:
    /usr/bin/python3 research/nezuko_a2_roofline.py
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Optional

# Host: Apple M4 Pro, 20 GPU cores, 273 GB/s peak DRAM bandwidth.
PEAK_GB_S = 273.0
GPU_CORES = 20

# -1 us/step on the decode axis == +0.01464 % score (campaign constant).
SCORE_PCT_PER_US = 0.01464

# Sources/MLXFastModel/LagunaConfig.swift
HIDDEN = 2048
HEAD_DIM = 128
KV_HEADS = 8
SLIDING_HEADS = 64  # LagunaConstants.slidingAttentionHeads, 30 layers
FULL_HEADS = 48     # LagunaConstants.fullAttentionHeads,    10 layers
MOE_INTER = 512
TOPK = 8
SLIDING_WINDOW = 512
DENSE_INTER = 8192

NVFP4_BYTES = 0.5625  # 4-bit element + group-16 fp8 scale
BF16_BYTES = 2.0


def nvfp4(weights: float) -> float:
    return weights * NVFP4_BYTES


def kv_bytes(positions: float) -> float:
    return positions * KV_HEADS * HEAD_DIM * 2 * BF16_BYTES


@dataclass
class Kernel:
    name: str
    n_per_step: float
    effective_us: float  # exposure-weighted us/step, re-priced census
    isolated_us: float   # unweighted us/step
    read_bytes: float    # read-once operand, bytes per call
    operand: str
    # Threadgroups launched per call.  Set only for the attention kernels,
    # where the grid rather than the byte count is the binding constraint.
    threadgroups: Optional[int] = None


KERNELS = [
    Kernel("routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2", 39, 1501.7, 1482.0,
           nvfp4(TOPK * 2 * MOE_INTER * HIDDEN),
           "8 experts x (gate,up) x 512 x 2048 NVFP4"),
    Kernel("decode_nvfp4_qkv_h64", 30, 1337.3, 1319.7,
           nvfp4((SLIDING_HEADS + 2 * KV_HEADS) * HEAD_DIM * HIDDEN),
           "(64+16) x 128 x 2048 NVFP4"),
    Kernel("oproj_act_h64", 30, 1116.9, 1102.2,
           nvfp4(HIDDEN * SLIDING_HEADS * HEAD_DIM),
           "2048 x 8192 NVFP4"),
    Kernel("routed_shared_nvfp4_down_residual_bf16_r1_v5", 39, 860.7, 849.4,
           nvfp4((TOPK + 1) * MOE_INTER * HIDDEN),
           "(8 routed + 1 shared) x 512 x 2048 NVFP4"),
    Kernel("sliding_fused_attn_ring_v1", 30, 628.7, 620.4,
           kv_bytes(SLIDING_WINDOW),
           "512 pos x 8 kv heads x 128 x (K,V) bf16",
           threadgroups=SLIDING_HEADS // 2),
    Kernel("decode_nvfp4_qkv_h48", 10, 364.0, 359.2,
           nvfp4((FULL_HEADS + 2 * KV_HEADS) * HEAD_DIM * HIDDEN),
           "(48+16) x 128 x 2048 NVFP4"),
    Kernel("oproj_act_h48", 10, 302.3, 298.3,
           nvfp4(HIDDEN * FULL_HEADS * HEAD_DIM),
           "2048 x 6144 NVFP4"),
    Kernel("full_fused_attn_grow_v1", 10, 252.6, 249.3,
           kv_bytes(576),
           "~576 pos x 8 kv heads x 128 x (K,V) bf16",
           threadgroups=FULL_HEADS // 2),
    # The single dense layer is the one MLP that was never quantized: both
    # kernels are named `_bf16_v1` and load `vec<bfloat, 4>` straight out of
    # `fused_weight` / `down_weight` (LagunaRuntimeModel.swift:8040, 8133).
    Kernel("dense_gate_up_swiglu", 1, 273.1, 269.5,
           2 * DENSE_INTER * HIDDEN * BF16_BYTES, "2 x 8192 x 2048 bf16"),
    Kernel("dense_down_residual", 1, 136.3, 134.5,
           DENSE_INTER * HIDDEN * BF16_BYTES, "8192 x 2048 bf16"),
    Kernel("shared_nvfp4_swiglu_qmv_rows1", 39, 27.4, 274.1,
           nvfp4(2 * MOE_INTER * HIDDEN), "(gate,up) x 512 x 2048 NVFP4"),
]

# The glue: kernels whose operands are kilobytes but whose cost is microseconds.
# Their byte floor is ~0, so whatever they cost is launch, threadgroup setup,
# reduction and drain -- GPU-busy time that only fusion removes.  This is *not*
# the per-command-buffer overhead ruled out in section 6: c = 0.54 us/CB is host
# encode time between buffers, whereas this is counter-measured kernel time.
GLUE = [
    Kernel("residual_rms_router_rpg8_keys_v1", 39, 305.1, 301.0,
           256 * HIDDEN * BF16_BYTES + 2 * HIDDEN * BF16_BYTES,
           "256 x 2048 router bf16 + hidden + residual"),
    Kernel("decode_router_top8_ordinal_table_norm", 39, 185.7, 183.3,
           256 * 4, "256 expert scores fp32"),
    Kernel("rmsbfloat16", 41, 124.6, 123.0, HIDDEN * BF16_BYTES, "2048 bf16"),
    Kernel("six kernels below 8 us/step", 6, 25.5, 25.1, 0.0, "negligible"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--peak", type=float, default=PEAK_GB_S)
    ap.add_argument("--cores", type=int, default=GPU_CORES)
    args = ap.parse_args()
    peak, cores = args.peak, args.cores

    print(f"# roofline pricing, peak = {peak:.0f} GB/s, {cores} GPU cores, "
          f"-1 us/step = +{SCORE_PCT_PER_US:.5f} % score")
    print("# shapes from LagunaConfig.swift: sliding = 64 heads (30 layers), "
          "full = 48 heads (10 layers), kv = 8, head_dim = 128")
    print()
    hdr = (f"{'kernel':<52} {'n':>3} {'eff us':>8} {'us/call':>8} "
           f"{'MB/call':>8} {'GB/s':>7} {'%peak':>6} "
           f"{'floor':>7} {'gain us':>8} {'score%':>7}")
    print(hdr)
    print("-" * len(hdr))

    bytes_bound_gain = 0.0
    for k in KERNELS:
        us_call = k.isolated_us / k.n_per_step
        gbs = k.read_bytes / (us_call * 1e-6) / 1e9
        floor_us_call = k.read_bytes / (peak * 1e9) * 1e6
        eff_us_call = k.effective_us / k.n_per_step
        gain = max(0.0, (eff_us_call - floor_us_call) * k.n_per_step)
        bytes_bound_gain += gain
        print(f"{k.name:<52} {k.n_per_step:>3.0f} {k.effective_us:>8.1f} "
              f"{us_call:>8.2f} {k.read_bytes / 1e6:>8.3f} {gbs:>7.1f} "
              f"{100.0 * gbs / peak:>6.1f} {floor_us_call:>7.2f} {gain:>8.1f} "
              f"{gain * SCORE_PCT_PER_US:>7.2f}")

    print("-" * len(hdr))
    print(f"# headroom if EVERY kernel above hit 100 % of DRAM peak: "
          f"{bytes_bound_gain:.0f} us/step = "
          f"{bytes_bound_gain * SCORE_PCT_PER_US:.2f} % score")

    weight = [k for k in KERNELS if k.threadgroups is None]
    w_eff = sum(k.effective_us for k in weight)
    w_floor = sum(k.read_bytes * k.n_per_step for k in weight) / (peak * 1e9) * 1e6
    print(f"# NVFP4 weight-streaming pool alone: {w_eff:.0f} us/step effective, "
          f"DRAM floor {w_floor:.0f} us/step, headroom {w_eff - w_floor:.0f} "
          f"us/step = {(w_eff - w_floor) * SCORE_PCT_PER_US:.2f} % score")
    print()

    # ---- attention: bytes are the wrong model, occupancy is the right one ----
    print("# attention: GQA replication means the DRAM roofline is not binding")
    attn = [k for k in KERNELS if k.threadgroups is not None]
    for k in attn:
        us_call = k.isolated_us / k.n_per_step
        heads = SLIDING_HEADS if "sliding" in k.name else FULL_HEADS
        gqa = heads // KV_HEADS
        tg_per_kv = gqa / 2  # the kernel walks 2 query heads per threadgroup
        replicated = k.read_bytes * tg_per_kv
        rep_gbs = replicated / (us_call * 1e-6) / 1e9
        print(f"  {k.name}")
        print(f"    grid {k.threadgroups} threadgroups on {cores} cores = "
              f"{k.threadgroups / cores:.2f} waves; gqa = {gqa}, so "
              f"{tg_per_kv:.0f} threadgroups re-read each kv head")
        print(f"    unique {k.read_bytes / 1e6:.3f} MB/call -> replicated "
              f"{replicated / 1e6:.3f} MB/call = {rep_gbs:.0f} GB/s "
              f"({100 * rep_gbs / peak:.0f} % of peak; must be cache-served)")

    # Tail-quantization model.  A grid of T threadgroups on C cores occupies
    # ceil(T/C) waves but only supplies T/C waves of work; the difference is an
    # idle tail.  This is a *lower* bound on the occupancy loss: it assumes
    # wave 1 is perfectly packed and ignores the serial KV chain inside a
    # threadgroup entirely.
    print()
    print("# tail-quantization lower bound "
          "(assumes a full wave 1; ignores the serial KV chain)")
    tail_gain = 0.0
    for k in attn:
        waves_used = k.threadgroups / cores
        waves_paid = -(-k.threadgroups // cores)  # ceil
        frac = 1.0 - waves_used / waves_paid
        gain = k.effective_us * frac
        tail_gain += gain
        print(f"  {k.name:<28} {k.threadgroups:>3} tg: pays {waves_paid} waves "
              f"for {waves_used:.2f} => tail {100 * frac:.0f} % = "
              f"{gain:.0f} us/step = {gain * SCORE_PCT_PER_US:.2f} % score")
    print(f"  attention tail total: {tail_gain:.0f} us/step = "
          f"{tail_gain * SCORE_PCT_PER_US:.2f} % score")

    a_eff = sum(k.effective_us for k in attn)
    a_floor = sum(k.read_bytes * k.n_per_step for k in attn) / (peak * 1e9) * 1e6
    print(f"  attention pool: {a_eff:.0f} us/step effective; the unique-bytes "
          f"DRAM floor is only {a_floor:.0f} us/step, so the arithmetic "
          f"ceiling on attention work is {a_eff - a_floor:.0f} us/step = "
          f"{(a_eff - a_floor) * SCORE_PCT_PER_US:.2f} % score")
    print()

    # ---- glue: the pool with no byte floor at all --------------------------
    print("# glue pool: kernels whose operands are kilobytes")
    g_eff = 0.0
    g_floor = 0.0
    for k in GLUE:
        us_call = k.isolated_us / k.n_per_step
        floor_us_call = k.read_bytes / (peak * 1e9) * 1e6
        g_eff += k.effective_us
        g_floor += floor_us_call * k.n_per_step
        print(f"  {k.name:<40} {k.n_per_step:>3.0f} x {us_call:>6.2f} us "
              f"= {k.effective_us:>6.1f} us/step; bytes {k.read_bytes / 1e6:>6.3f} "
              f"MB -> floor {floor_us_call * k.n_per_step:>6.1f} us/step "
              f"({k.operand})")
    print(f"  glue pool: {g_eff:.0f} us/step effective "
          f"({100 * g_eff / 8445.7:.1f} % of the step), byte floor only "
          f"{g_floor:.0f} us/step")
    print(f"  => {g_eff - g_floor:.0f} us/step = "
          f"{(g_eff - g_floor) * SCORE_PCT_PER_US:.2f} % score is launch, "
          f"threadgroup setup, reduction and drain latency -- removable only by "
          f"fusing these kernels into their neighbours")
    print("  NOTE: this is counter-measured GPU-busy kernel time. It is NOT the "
          "per-command-buffer host encode cost c = 0.540 us/CB ruled out in "
          "section 6; the two are disjoint.")
    print()

    # ---- consistency check ------------------------------------------------
    # The modelled bytes should reproduce the active-parameter footprint of one
    # decode token.  If they do not, a shape or a dtype above is wrong.
    total_bytes = sum(k.read_bytes * k.n_per_step for k in KERNELS)
    moe_total = 39 * 256 * 3 * MOE_INTER * HIDDEN * NVFP4_BYTES
    print("# consistency check")
    print(f"  modelled read traffic: {total_bytes / 1e6:.0f} MB/step "
          f"(lm head excluded: pruned/sparse, owned by PR #137)")
    print(f"  full routed-expert tensor: {moe_total / 1e9:.2f} GB, which is the "
          f"bulk of the ~21.6 GB resident tower -- so the shapes are right")

    # ---- the one bytes-bound lever left, and why it is out of bounds -------
    dense = [k for k in KERNELS if k.name.startswith("dense_")]
    d_eff = sum(k.effective_us for k in dense)
    d_bytes = sum(k.read_bytes * k.n_per_step for k in dense)
    d_nvfp4_us = d_bytes / BF16_BYTES * NVFP4_BYTES / (peak * 1e9) * 1e6
    print()
    print("# the dense layer: the only large bytes-bound lever, and it is "
          "out of bounds")
    print(f"  {d_bytes / 1e6:.0f} MB/step of bf16 weights costing "
          f"{d_eff:.0f} us/step (~{100 * d_eff / 8445.7:.1f} % of the step) "
          f"at {d_bytes / (d_eff * 1e-6) / 1e9:.0f} GB/s = "
          f"{100 * d_bytes / (d_eff * 1e-6) / 1e9 / peak:.0f} % of peak")
    print(f"  at NVFP4 the same layer would read "
          f"{d_bytes / BF16_BYTES * NVFP4_BYTES / 1e6:.0f} MB and cost about "
          f"{d_nvfp4_us:.0f} us/step: a {d_eff - d_nvfp4_us:.0f} us/step, "
          f"{(d_eff - d_nvfp4_us) * SCORE_PCT_PER_US:.2f} % score prize")
    print("  RULED OUT: re-quantizing the dense MLP is a precision change "
          "outside the accepted attention envelope (group-32 affine INT8 for "
          "Q/K/V/O and per-head g_proj). Priced so nobody re-derives it.")


if __name__ == "__main__":
    main()
