# Negative Results Log (2026-08-05/06)

## PR #93 — Down+Residual Kernel: Register-Prefetch (Edward)
- **Hypothesis**: Adding depth-1 register-prefetch to the routed+shared down+residual kernel reduces kernel duration by overlapping weight loads with compute
- **Result**: FAILED — decode regressed ~0.48% (0.013351 → 0.013415 s/tok) over two matched runs
- **Correctness**: Passed (max_abs_diff=0, golden_hash matches)
- **Root cause**: The down+residual kernel's loop body (4 rows, 1 qdot each, pre-loaded input) provides insufficient compute to overlap prefetch with. The gate/up R1 kernel where the same pattern won -12% has 8 qdots and 16 float loads per iteration. Prefetch adds register pressure (4 extra thread variables) and address computation overhead with no compensating latency hiding.
- **W&B**: https://wandb.ai/wandb-applied-ai-team/mlxfast-birch/runs/3jhy0yb3
- **Lesson**: The down+residual kernel is NOT memory-latency-bound — it is compute/instruction-bound. Register prefetch only helps when there is substantial compute to hide it behind. Combined with PR #89 (4→8 SIMD groups also regressed via register pressure), the down+residual kernel is sensitive to register pressure and not amenable to tiling or prefetch changes.

## PR #95 — O-proj Unroll Sweep: DARKBLOOM_L5_UNROLL 2→4 (Askeladd)
- **Hypothesis**: Increasing DARKBLOOM_L5_UNROLL from 2 to 4 increases outstanding GPU loads per thread in the gated output projection decode kernel
- **Result**: DEAD HYPOTHESIS — DARKBLOOM_L5_UNROLL is a no-op on the scored decode path
- **Root cause**: DARKBLOOM_L5_UNROLL (line 3718) controls the BF16 gated output projection kernel selection (line 3753). This BF16 kernel is UNREACHABLE during decode because the native affine o_proj block (lines 5941-6046) always returns before the BF16 fallback at line 6047. With lagunaNativeAffineNVFP4From=0 (default), all 40 layers use the NVFP4 affine o_proj path.
- **Correctness**: Bit-exact (identical golden_hash b9509697c08a2cf3, max_abs_diff=0)
- **Timing**: Baseline decode=0.013123, candidate=0.013157 s/tok (+0.26% noise), prefill=0.001122 vs 0.001121 (-0.09% noise)
- **W&B**: https://wandb.ai/wandb-applied-ai-team/mlxfast-birch/runs/k0c3pi23
- **Lesson**: The code comment at line 3713 ("highest-information measurement left on this box") is misleading — the kernel it refers to is NOT on the scored path. Always trace the env var to the scored runtime path before timing. Follow-up: the NVFP4 affine o_proj kernel (line 4373) IS on the scored path but uses a different unroll mechanism — would need its own unroll sweep.

## PR #89 — Down+Residual Kernel: outputs_per_simd 4→8 (Thorfinn)
- **Hypothesis**: Doubling output rows per SIMD halves threadgroup count, increases input reuse, reduces decode latency
- **Result**: FAILED — decode regressed +2.39% (0.013211 → 0.013526 s/token)
- **Correctness**: Passed (max_abs_diff=0, golden hash matches)
- **Root cause**: Increased register pressure from 8 result arrays (vs 4), worse GPU occupancy. Kernel is memory-bound on NVFP4 weight reads, so input reuse gain is minimal relative to parallelism loss.
- **W&B**: https://wandb.ai/wandb-applied-ai-team/mlxfast-birch/runs/a7xnxujw
- **Lesson**: Do not revisit 4→8 tiling on the down+residual kernel. The down kernel is weight-bandwidth-bound, not input-bandwidth-bound.

## Eliminated Research Ideas (Pre-assignment analysis, 2026-08-06)

### 1. Register-resident scale pre-loading
- **Premise**: Pre-load NVFP4 scale factors into registers to avoid redundant DRAM reads
- **Finding**: Scales are NOT read redundantly — each block reads a distinct scale (pointer advances per block). Zero bandwidth savings. The latency-hiding variant (software pipelining) is ALREADY implemented: depth-1 in routed R1 kernel (default ON), depth-4 in QKV affine kernel (default ON, measured -11.9%).
- **Verdict**: DEAD — optimization already banked via prefetch

### 2. Threadgroup input staging for shared/routed SwiGLU QMV
- **Premise**: Stage 2048-element input to threadgroup memory to eliminate 2× read redundancy
- **Finding**: L1 cache handles 2× redundancy on M4 (PR #75 negative). Routed QMV has same 2× intra-TG redundancy — cross-TG and cross-expert redundancy can't be addressed by TG memory. Input is SLC-resident (4KB fits 16-48MB SLC). Bottleneck is LSU instruction pressure, not DRAM bandwidth.
- **Verdict**: DEAD — L1/SLC already handles the redundancy
- **Note**: Askeladd's PR #90 is testing this for the shared kernel specifically. Expect negative based on PR #75.

### 3. Router GEMV + top-8 fusion
- **Premise**: Fuse router matmul, softmax, and top-8 selection into single kernel
- **Finding**: ALREADY IMPLEMENTED in the darkbloom fork. lagunaResidualRMSNormRouter fuses residual+RMSNorm+router GEMV (1 dispatch). lagunaDecodeRouterTop8 uses custom bitonic sort (1 dispatch). Already collapsed ~10-11 dispatches → 2. All gated by DARKBLOOM_* flags, default ON.
- **Verdict**: DEAD — optimization already banked

### 4. Texture-backed NVFP4 weight storage
- **Premise**: Use MTLTexture for weight storage to improve cache behavior
- **Finding**: MLX has zero texture support. All kernels use device buffers. No texture injection point in dispatch API (MLXFastKernel only accepts buffers). Binding layer (metal_kernel.cpp, device.cpp) is NOT editable. Performance rationale is weak anyway — NVFP4 weights are read sequentially (buffer-optimal), textures help 2D spatial locality which doesn't match GEMV decode.
- **Verdict**: DEAD — no editable texture binding path + weak performance rationale
