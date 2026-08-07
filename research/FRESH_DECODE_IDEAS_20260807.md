# Fresh Decode Optimization Ideas — 2026-08-07

Target: `Sources/MLXFastModel/LagunaRuntimeModel.swift` (505,554 bytes; 18,734 bytes per-file headroom)
and `Sources/MLXFastModel/LagunaLmHeadPrune.swift` (46,738 bytes; 477,550 bytes headroom)

Architecture: 40 layers (10 full-attn + 30 sliding), MoE (256 experts, top-8, 1 shared), NVFP4.
Layer 0 is dense BF16. Decode is single-token [1,1,2048]. M5 is bandwidth-bound at ~89% GPU util.

Current decode per sparse layer: 6 dispatches (norm+QKV, fused attn, gated OProj,
residual+RMSNorm+router, gate/up QMV, down+residual). ~245 total dispatches per decode step.

**LRM file has only 18KB per-file headroom — kernel source additions must be compact.
LM head pruner file has ample headroom (477KB).**

---

## Idea 1: Fuse final RMSNorm into LM head coarse pass

**Function:** `LagunaRuntimeModel.callAsFunction` (line 11130) + `LagunaLmHeadPruner.logits` (LagunaLmHeadPrune.swift:924)
**Also:** `LagunaRuntimeModelInner.norm` (RMSNorm at line 11088, stock `MLXFast.rmsNorm`)

**What to change:**
Currently `model.norm(lagunaLastTokenHidden(fullHidden))` is a separate stock `rms_single_row`
dispatch producing a BF16 normalized [1,1,2048] row, then the pruner's coarse kernel reads it.
Fold the RMSNorm into the coarse kernel: pass the raw hidden + norm weight as additional
inputs. The kernel computes the sum-of-squares reduction (same `simd_sum` + threadgroup
barrier pattern as `rms_single_row` and the existing `lagunaResidualRMSNormRouterSource`),
stores `inv_mean` in threadgroup memory, then normalizes each element to BF16 before
the coarse dot product.

**Why:**
Eliminates 1 dispatch per decode step (the final RMSNorm). The coarse kernel already
reads the full 2048-element hidden vector, so the sum-of-squares reduction reuses the
same loaded data. The norm weight (2048 BF16 = 4KB) is a one-time resident read.

**Bandwidth/dispatch savings:**
- 1 fewer dispatch per step (128 steps = 128 fewer dispatches)
- ~4KB write eliminated (normalized hidden materialization) + ~4KB input read saved
- Dispatch overhead reduction: ~0.4% of total decode time (at 245 dispatches/step)

**Bit-exactness:**
The stock `rms_single_row` kernel computes: `inv_mean = precise::rsqrt(sum(x²)/N + eps)`,
then `out[i] = bfloat(norm_weight[i] * bfloat(x[i] * inv_mean))`. The fused kernel must
reproduce this exactly: same FP32 sum-of-squares with `simd_sum` + threadgroup barrier
reduction, same `precise::rsqrt`, same per-element `bfloat(x[i] * inv_mean)` rounding
before the dot product. The existing `lagunaResidualRMSNormRouterSource` (line 760)
already proves this reduction pattern is bit-exact against stock RMSNorm. The coarse
kernel then receives the same BF16 normalized values it currently gets externally.

**Risk: MEDIUM**
The RMSNorm reduction must match MLX's `rms_single_row` exactly (same FP32 accumulation
order, same rsqrt). The pattern is proven in existing kernels but the coarse kernel has
different threadgroup geometry (512 threads vs 32-64). Need to verify the reduction
across 16 simdgroups matches the 1-simdgroup `simd_sum` in `rms_single_row`.

**Budget:**
~2-3KB new kernel source in `LagunaLmHeadPrune.swift` (477KB headroom — ample).
~200 bytes in `LagunaRuntimeModel.swift` (change call site to pass raw hidden + norm weight
instead of pre-normalized). Well within 18KB LRM headroom.

---

## Idea 2: Routed+shared down+residual kernel: double outputs_per_simd 8→16

**Function:** `lagunaRoutedSharedDownResidualKernel` (line 7776) + dispatch at line 7960

**What to change:**
Change `outputs_per_simd` from 8 to 16, halving the grid from `(2048/8)*288 = 73728`
threadgroups to `(2048/16)*288 = 36864`. Each simdgroup computes 16 output elements
instead of 8. Threadgroup memory grows from `9*8=72` BF16 (144B) to `9*16=144` BF16
(288B) — still tiny. Register usage: `float result[16]` instead of `float result[8]`
plus `float input_values[16]` (unchanged) = 32 floats = 128 bytes, within Metal limits.

**Why:**
Halves the threadgroup launch count for the MoE down+residual dispatch, the largest
single-kernel dispatch in the decode path (73728 threadgroups). Reduces command buffer
encoding overhead and may improve GPU scheduling by reducing threadgroup-launch bubbles.

**Bandwidth/dispatch savings:**
- Bandwidth: net zero (same total weight reads, just packed into fewer threadgroups)
- Dispatch count: unchanged (same 1 dispatch), but 50% fewer threadgroups
- Potential cache benefit: each threadgroup reads 16 contiguous weight rows per slot
  instead of 8, improving L2 cache line utilization

**Bit-exactness:**
Pure geometry change. Each output element is computed by the same code path: same
NVFP4 qdot, same `simd_sum`, same BF16 rounding, same threadgroup reduction and
router-weighted combine. The only difference is how many rows each simdgroup processes.
The `result[row]` array and the `down_outputs[slot * outputs_per_simd + row]` indexing
scale naturally. No arithmetic changes.

**Risk: MEDIUM**
Similar tiling doubling succeeded for NVFP4 OProj/QKV but the standalone down kernel's
4→8 doubling regressed. The fused kernel (9-slot, 288-thread) has different
characteristics: more simdgroups, shared threadgroup reduction. The regression on the
standalone kernel may not apply here, but it's a cautionary signal. Must measure on M4
before promoting.

**Budget:**
~50 bytes (constexpr change `8` → `16` and grid `2048/8` → `2048/16` in the existing
kernel source string). Well within 18KB LRM headroom.

---

## Idea 3: NVFP4 OProj kernel: double results_per_simdgroup 8→16

**Function:** `lagunaGatedAffineOProjNVFP4Source` (line 4053) + dispatch at line 4449/4460

**What to change:**
Change `results_per_simdgroup` from 8 to 16 and `num_simdgroups` from 2 to 2 (unchanged),
halving the grid from `(2048/16)*64 = 8192` threadgroups to `(2048/32)*64 = 4096`.
Each threadgroup produces 32 output elements (2 simdgroups × 16). Register usage:
`float result[16]` + `float x_thread[16]` = 32 floats = 128 bytes, within limits.

**Why:**
Halves the OProj threadgroup count. The NVFP4 OProj already had one successful tiling
doubling (4→8). The INT8 OProj doubling regressed (-2.84%), but the NVFP4 variant has
simpler per-element work (one qdot vs INT8's scale+bias+dot), so further doubling may
succeed where INT8 failed.

**Bandwidth/dispatch savings:**
- Bandwidth: net zero (same total weight reads)
- 50% fewer threadgroups for the OProj dispatch (per layer, 40 layers)
- Better cache line utilization: 16 contiguous weight rows per simdgroup

**Bit-exactness:**
Pure geometry change. Same NVFP4 qdot, same scale decode, same `simd_sum` reduction,
same BF16 epilogue. The `result[row]` and `projected[out_row + row]` indexing scales
naturally with `results_per_simdgroup`. No arithmetic changes.

**Risk: MEDIUM**
The INT8 OProj doubling regressed, but the NVFP4 variant is a different kernel with
lighter per-element compute. The NVFP4 OProj's first doubling (4→8) succeeded, suggesting
the kernel scales well. However, going to 16 doubles register pressure and may spill,
causing regression. Must measure on M4.

**Budget:**
~50 bytes (constexpr change in kernel source string). Well within 18KB LRM headroom.

---

## Idea 4: Routed gate/up R1 kernel: restructure to 9-simdgroup threadgroup for input sharing

**Function:** `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` (line 7412) + dispatch at line 7595

**What to change:**
Currently the kernel uses `threadGroup: (64, 1, 1)` (2 simdgroups), where each simdgroup
handles one expert slot. The 2048-element input vector is loaded independently by each
slot (9 total reads per tile). Restructure to `threadGroup: (288, 1, 1)` (9 simdgroups),
load the input once into threadgroup memory (2048 BF16 = 4KB), barrier, then each
simdgroup reads from threadgroup memory instead of device memory. This reduces input
reads from 9× to 1× per tile.

**Why:**
The input (hidden state, 2048 BF16 = 4KB) is identical across all 9 slots. Currently
each slot re-reads it from device memory. Sharing via threadgroup memory eliminates
8 redundant 4KB reads per tile. With 256 tiles per step, saves ~8MB/step of input reads.

**Bandwidth/dispatch savings:**
- Input bandwidth: 8 × 4KB × 256 tiles = 8MB/step saved (~1.1% of total ~708MB/step)
- Dispatch count: reduced (fewer threadgroups: total_threads / 288 instead of / 64)
- Threadgroup memory: 4KB for input (well within 32KB limit)

**Bit-exactness:**
The input values are loaded from device memory into threadgroup memory as BF16, then
each simdgroup reads them as BF16 — identical values. The weight reads, qdot, SwiGLU,
and output writes are unchanged. Only the input source changes from device to
threadgroup memory.

**Risk: MEDIUM-HIGH**
"Input-vector staging (barrier overhead)" was already tried and failed. This may be
the same idea. The failure could have been for a different kernel (QKV or attention),
or the barrier overhead of synchronizing 9 simdgroups for a 4KB load may outweigh the
bandwidth savings. The down+residual kernel successfully uses 9 simdgroups, but its
input is per-slot (different per simdgroup), so it doesn't have the same sharing pattern.
The barrier cost of one `threadgroup_barrier` after loading 2048 elements across 288
threads should be small (~1μs), but the failed experiment suggests it may not be.
**Recommendation:** Only try if the failed staging experiment was for a different kernel.

**Budget:**
~2-3KB of kernel source changes (restructure the input loading loop, add threadgroup
memory declaration and barrier). Tight but feasible within 18KB LRM headroom.

---

## Idea 5: Dense layer-0 down+residual kernel: increase rows_per_thread 4→8

**Function:** `lagunaDenseDownResidualKernel` (line 8078) + dispatch at line 8150

**What to change:**
Change `rows_per_thread` from 4 to 8 and `rows_per_group` from 16 to 32, halving the
grid from `(2048/16)*128 = 16384` total threads (128 threadgroups) to
`(2048/32)*256 = 16384` (64 threadgroups with 256 threads each = 8 simdgroups).
Each simdgroup computes 8 output rows instead of 4. Register usage: `float result[8]`
instead of `float result[4]` — modest increase.

**Why:**
Halves the threadgroup count for layer 0's down+residual dispatch. Layer 0 is only 1
of 40 layers, so the impact is small (~0.4% of total dispatches). Low-hanging fruit
if it doesn't regress.

**Bandwidth/dispatch savings:**
- Bandwidth: net zero
- 64 fewer threadgroups for 1 layer per step (128 steps = 8192 fewer launches)
- Very small overall impact

**Bit-exactness:**
Pure geometry change. Same BF16 dot product, same `simd_shuffle_down` reduction,
same residual add. The `result[row]` indexing scales naturally.

**Risk: LOW-MEDIUM**
The "down+residual outputs_per_simd 4→8 (regressed)" failure may have been about this
kernel or the standalone routed down kernel. If it was this kernel, the idea is dead.
If it was the routed down kernel, this is a different kernel (BF16 vs NVFP4, different
grid/threadgroup geometry) and may behave differently. Must verify which kernel
regressed before trying.

**Budget:**
~100 bytes (constexpr changes + grid adjustment). Well within 18KB LRM headroom.

---

## Summary ranking (by expected impact × feasibility):

| # | Idea | Risk | Impact | Budget |
|---|------|------|--------|--------|
| 1 | Fuse final RMSNorm into LM head coarse | MEDIUM | 1 dispatch/step saved | ~3KB (LMHead) + ~200B (LRM) |
| 2 | Down+residual outputs_per_simd 8→16 | MEDIUM | 50% fewer threadgroups (biggest dispatch) | ~50B |
| 3 | NVFP4 OProj results_per_simd 8→16 | MEDIUM | 50% fewer threadgroups (40 layers) | ~50B |
| 4 | Gate/up R1 9-simdgroup input sharing | MED-HIGH | ~8MB/step bandwidth saved | ~2-3KB |
| 5 | Dense down rows_per_thread 4→8 | LOW-MED | 64 fewer threadgroups (1 layer) | ~100B |

**Key constraint:** LRM file has only 18,734 bytes of per-file headroom. Ideas 2, 3, 5
are constexpr-only changes (~50-100 bytes each). Idea 1 puts most new code in the LM
head pruner file. Idea 4 is the tightest fit at ~2-3KB of kernel source.

**Note:** The M5 is bandwidth-bound at 89% GPU utilization. The remaining 11% is
dispatch/scheduling overhead. With ~245 dispatches per step, each dispatch contributes
~0.045% idle time. Ideas 1-3, 5 reduce dispatch/threadgroup overhead; idea 4 reduces
bandwidth. All savings are marginal individually but may compound.
