# Negative Results Log (2026-08-05/06)

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
