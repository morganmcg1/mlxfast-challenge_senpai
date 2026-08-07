# Fresh Optimization Ideas — 2026-08-07

Ranked list of fresh, untried optimization directions for the Laguna XS 2.1
NVFP4 M5 inference challenge. Generated from deep codebase analysis of the
scored decode/prefill paths, budget audit, and prior experiment history.

## Critical Budget Reality

| Constraint | Current | Limit | Headroom |
|---|---|---|---|
| Total editable surface | 2,973,616 B | 3,000,000 B | **26,384 B** |
| LagunaRuntimeModel.swift | 517,008 B | 524,288 B | **7,280 B** |
| Per-submission growth | — | 262,144 B | — |
| LagunaLmHeadPrune.swift | 46,738 B | 524,288 B | 477,550 B |
| fp_quantized_nax.h (vendor) | 76,817 B | 524,288 B | 447,471 B |
| quantized.cpp (vendor) | 82,721 B | 524,288 B | 441,567 B |

**LagunaRuntimeModel.swift is the binding constraint at 7,280 B headroom.**
Any idea touching kernel source strings in that file must be very small.
LagunaLmHeadPrune.swift and vendor kernel files have ample headroom.

## State of Scale Halving (verified against current HEAD c63f843)

All three primary decode MoE scale-halving paths are **ALREADY COMPLETE**
(contrary to the stale bandwidth audit):

| Kernel | scale_row_bytes | Halved? | Status |
|---|---|---|---|
| `lagunaSharedSwiGLUQMVKernel` | 64 | YES | `lane/2` indexing, escape wired |
| `lagunaSharedSwiGLUQMVRows1Kernel` | 64 | YES | `lane/2` indexing, escape wired |
| `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` | 16 | YES | `_halved` suffix, escape wired |
| `lagunaRoutedSharedDownResidualKernel` | 16 | YES | `_halved` suffix, escape wired |
| `lagunaSharedDownResidualKernel` (fallback) | 32 | **NO** | Fallback only, not default-on |

**Implication**: Decode scale halving is exhausted. Remaining opportunities
are in prefill (different kernel path) and non-scale-halving mechanisms.

---

## Idea 1: Prefill MoE Gather-QMM Scale Halving ★★★ HIGHEST

**Priority**: 1 (next assignment)
**Component**: Prefill (25% of score)
**Mechanism**: NVFP4 pairwise-constancy scale halving for the prefill MoE
gather-GEMM kernel (`fp_gather_qmm_rhs_expert_nax`), which is a COMPLETELY
DIFFERENT code path from the decode kernels. Decode halving (PR #180) does
NOT touch the prefill kernel.

**Target code**:
- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h`
  — `QuantizedBlockLoader` (L210–257): add `kHalvedScales` template parameter
- `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp`
  — generated twin (keep consistent per AGENTS.md)
- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`
  — `gather_qmm_rhs_nax` dispatch (L1958): pass halved scales + escape
- `Sources/MLXFastModel/LagunaRuntimeModel.swift` — prepare halved prefill
  scale tensors at init (~15 lines)

**Expected M5 signal**: ~4–6% prefill gain → ~1.0–1.5% composite score gain.
Prefill loads ALL 256 experts' weights (each used once across assigned
tokens). Scale traffic: ~1,872 MiB prefill; halving saves ~936 MiB.
At M5 651.8 GB/s: ~1.44 ms saved per ~25–30 ms prefill.

**Bit-exact risk**: LOW. Same pairwise-constancy invariant as PR #180
(`scale[2k]==scale[2k+1]` for k≥1). Same bit-exactness proof. Escape byte
handles the sole exception pair per expert.

**Budget impact**: ~60–75 lines across 4 files (~3–4 KB). fp_quantized_nax.h
has 447 KB headroom; quantized.cpp has 442 KB headroom. LagunaRuntimeModel.swift
contribution is ~15 lines (~600 B) — within the 7,280 B headroom. Total
surface growth ~3–4 KB — within the 26,384 B headroom.

**M4 testability**: NO. M4 Pro reports GPU gen 16 < 17 NAX threshold — the
`_nax` expert kernel is never compiled on M4. Must submit directly to M5.
Record kernel reachability and architecture before interpreting results.

**Why it's fresh**: The prefill MoE gather-QMM kernel (`fp_gather_qmm_rhs_expert_nax`)
has NOT been touched by any scale halving PR. Decode halving (PR #180) only
modifies custom decode kernels. This is a genuinely different code path.
Already designed in `research/THORFINN_NEXT_EXPERIMENT.md` but NOT yet
implemented or tested.

**Assignment recommendation**: Assign to Thorfinn (familiar with
`fp_quantized_nax.h` from BM128 work).

---

## Idea 2: Fuse Final RMSNorm into LM Head Coarse Kernel ★★☆ HIGH

**Priority**: 2
**Component**: Decode (75% of score)
**Mechanism**: The final `model.norm(hidden)` is the ONLY stock MLX primitive
dispatch on the decode path (every other op is a custom Metal kernel). It
runs as a separate dispatch before the 4-dispatch LM head pruner. Fuse the
RMSNorm computation into the coarse int5 GEMV kernel's first phase: the
coarse kernel already reads the hidden vector `x` element-by-element for
the GEMV; it can normalize `x` in threadgroup memory (sum of squares via
`simd_sum`, `rsqrt`, multiply) before starting the GEMV accumulation.

**Target code**:
- `Sources/MLXFastModel/LagunaLmHeadPrune.swift` L241 (coarse kernel source)
  — add RMSNorm prologue to the coarse int5 GEMV kernel
- `Sources/MLXFastModel/LagunaRuntimeModel.swift` L11027 — remove the
  separate `model.norm(hidden)` dispatch when the pruner is active

**Expected M5 signal**: 1 fewer dispatch per decode step. At ~328 dispatches
and ~2–5 μs dispatch overhead, saves ~2–5 μs/step. At ~5376 μs/step, that's
~0.04–0.09%. Small but non-zero, and eliminates the last stock MLX op
(reduces framework overhead and potential command-buffer fragmentation).

**Bit-exact risk**: MEDIUM. Must reproduce the exact RMSNorm computation
in Metal: `x * rsqrt(mean(x²) + 1e-6)`. The sum-of-squares reduction across
2048 elements needs cross-simdgroup reduction (threadgroup memory). The
`rsqrt` and per-element multiply must match MLX's implementation exactly.
The existing decode kernels already do this (the `lagunaNormInvMeanScratch`
prologue pattern at L760+), so the Metal code pattern is proven. Risk is
in matching MLX's RMSNorm rounding exactly for the coarse kernel's
downstream int5 quantization.

**Budget impact**: ~30–50 lines in LagunaLmHeadPrune.swift (477 KB headroom).
~5 lines in LagunaRuntimeModel.swift (guard the norm dispatch away when
pruner active) — ~200 B, within 7,280 B headroom.

**M4 testability**: YES. The final RMSNorm and LM head run on M4. The
pruner's bit-exactness certificate can be verified on M4 via
`--local-iterate` (max_abs_diff must remain 0) and upstream equivalence.

**Why it's fresh**: The decode audit (OPP-2a) noted this as an opportunity
but it was never assigned or attempted. No PR has touched the LM head
pruner's coarse kernel to fuse RMSNorm.

---

## Idea 3: INT8 Affine 4× Scale/Bias Dedup via simd_shuffle Broadcast ★★☆ MEDIUM-HIGH

**Priority**: 3
**Component**: Decode (75% of score)
**Mechanism**: Three INT8 affine (group-32) kernels index scales/biases with
`lane/SS` where `SS = GS/V = 32/8 = 4`. This means 4 consecutive lanes
(0-3, 4-7, ...) read the SAME scale and bias value from device memory — a
4× redundant device load. Loading once per lane-group (e.g., `lane%4==0`
loads, broadcast via `simd_shuffle`) saves 3/4 of scale+bias device reads
AND 3/4 of the load instructions.

**Target kernels** (all in `Sources/MLXFastModel/LagunaRuntimeModel.swift`):
1. `lagunaGateSoftplusSource` (L4326-4327): `sc=scales+orow*KG+lane/SS`,
   `bs=biases+orow*KG+lane/SS`. Runs on all 40 layers (g_proj path).
2. `lagunaNormAffineQKVSource` (L4802-4804): `simd_lid/scale_step_per_thread`.
   Runs on all 40 layers (QKV projection).
3. `lagunaGatedAffineOProjSource` (L3865-3871): same pattern. Runs on all
   40 layers (O-proj).

**Expected M5 signal**: Instruction reduction (fewer device load
instructions). Bandwidth savings are small (~450 KiB/step total across all
3 kernels × 40 layers). On instruction-bound M5, the instruction savings
matter more: each kernel does 4× redundant `bfloat` loads per block
iteration. With ~64 blocks per row and ~4 rows per simdgroup, that's ~256
redundant loads per simdgroup × 3 kernels × 40 layers. The broadcast via
`simd_shuffle` replaces 4 loads with 1 load + 1 shuffle.

**Bit-exact risk**: LOW. Each lane still computes with the identical float
value — the `simd_sum` reduction is unchanged. The load is broadcast, not
the accumulation. The same scale/bias value reaches each lane; only the
device access pattern changes.

**Budget impact**: ~15-25 lines per kernel source string × 3 kernels =
~60-75 lines (~2,500-3,000 B) in LagunaRuntimeModel.swift. This EXCEEDS
the 7,280 B headroom if done all at once. Must be done incrementally:
one kernel at a time (~800-1,000 B each), or combined with other changes
that REDUCE code size. **Budget risk is the main concern.**

**M4 testability**: YES. All 3 kernels run on M4 decode. Instruction
reductions may show on M4 if M4 is partially instruction-bound for these
small-kernel sections (even though overall M4 is bandwidth-bound).

**Why it's fresh**: Identified in bandwidth audit (Opportunity #3) but never
assigned or attempted. Different mechanism from scale halving (redundant
loads, not halved scales). Targets INT8 affine path (group-32), not NVFP4.

---

## Idea 4: Fuse LM Head Argmax + Threshold into One Dispatch ★☆☆ MEDIUM

**Priority**: 4
**Component**: Decode (75% of score)
**Mechanism**: The LM head pruner uses 4 dispatches: (1) coarse int5 GEMV,
(2) argmax stage 1 over coarse logits, (3) winner threshold computation,
(4) exact BF16 GEMV for candidates. Dispatches (2) and (3) are dependent
(argmax finds the winner, threshold computes the cutoff from the winner's
coarse logit). If the argmax kernel also writes the threshold value (from
the winning coarse logit), dispatch (3) is eliminated. The argmax is a
reduction over 100,352 elements; the threshold reads 1 element + computes
`bfloat(winner) - delta`. Fusing the threshold into the argmax's epilogue
is straightforward.

**Target code**:
- `Sources/MLXFastModel/LagunaLmHeadPrune.swift` — modify argmax stage 1
  kernel to also write the threshold value; remove the separate threshold
  dispatch call

**Expected M5 signal**: 1 fewer dispatch per decode step. Same magnitude as
Idea 2 (~2–5 μs/step, ~0.04–0.09%). Small but compounds with Idea 2 (total
2 fewer dispatches = ~4–10 μs/step).

**Bit-exact risk**: LOW. The threshold computation is
`threshold = bfloat(coarse_logit[winner]) - delta[winner]`. Moving this
computation into the argmax kernel's epilogue (after the argmax is found)
produces the identical float value. The argmax already reads the winner's
coarse logit; the threshold just subtracts a per-row delta. No reassociation
or rerounding.

**Budget impact**: ~20-30 lines in LagunaLmHeadPrune.swift (477 KB headroom).
No changes to LagunaRuntimeModel.swift. ~800-1,200 B. Well within budget.

**M4 testability**: YES. The LM head pruner runs on M4. Verify bit-exactness
via `--local-iterate` (max_abs_diff must remain 0, golden hash unchanged).

**Why it's fresh**: No PR has attempted to reduce the LM head pruner's
dispatch count. The 4-dispatch structure has been stable since the pruner
was introduced.

---

## Idea 5: Standalone Shared Down Kernel Scale Halving ★☆☆ LOW

**Priority**: 5
**Component**: Decode (75% of score) — FALLBACK path only
**Mechanism**: The standalone `lagunaSharedDownResidualKernel` (L6748) uses
`scale_row_bytes = 32` (NOT halved). The fused `lagunaRoutedSharedDownResidual`
is default ON and already halved. This standalone kernel only runs when the
fusion guard (`lagunaFusedRoutedSharedDownResidualEnabled`) declines. Apply
the same halving (scale_row_bytes 32→16, lane→lane/2, escape byte) for
consistency and to cover the fallback path.

**Target code**:
- `Sources/MLXFastModel/LagunaRuntimeModel.swift` L6748-6760 — modify
  `scale_row_bytes` 32→16, scale pointer `lane`→`lane/2`, add escape input

**Expected M5 signal**: NONE on default path (fusion guard always passes in
shipped config). Only relevant if the guard ever fails during scored runs.

**Bit-exact risk**: LOW. Same invariant as all other halved kernels.

**Budget impact**: ~10-15 lines (~400-600 B) in LagunaRuntimeModel.swift.
Within 7,280 B headroom but consumes scarce budget for a fallback path.

**M4 testability**: Only testable by disabling the fusion guard
(`DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL=0`), which changes the
scored path. Directional only.

**Why it's fresh**: Identified in bandwidth audit (Opportunity 2) but never
assigned. Low priority because it's a fallback path.

---

## Idea 6: DARKBLOOM_ROUTER_ROWS_PER_GROUP Sweep ☆☆☆ LOW (0-byte)

**Priority**: 6
**Component**: Decode (75% of score)
**Mechanism**: The router top-8 kernel's `DARKBLOOM_ROUTER_ROWS_PER_GROUP`
env var (default 8) controls how many router rows each threadgroup processes.
The comment at L827 says `=64` is "a null by construction" (known equivalent).
Values 16 and 32 are untested. On instruction-bound M5, fewer threadgroups
with more work per group could reduce dispatch overhead and improve
instruction throughput (fewer cross-threadgroup barriers).

**Target code**: None — pure env var change.

**Expected M5 signal**: Unknown. The router kernel is 1 dispatch of 256
threads — tiny compared to the 328 total. Even if the sweep helps, the
absolute gain is <0.1%. BUT: 0-byte cost, zero risk, trivial to test.

**Bit-exact risk**: LOW. The comment says `=64` is "a null by
construction" — the routing result is identical. Values 16 and 32 should
also be bit-exact (they only change the threadgroup tiling, not the sort
algorithm or accumulation order).

**Budget impact**: 0 bytes. Pure env var.

**M4 testability**: YES. Can be swept on M4 with `--local-iterate`.

**Why it's fresh**: The sweep was never performed. Only the default (8) and
the known-equivalent (64) have been characterized.

---

## Idea 7: Prefill Shared Expert Down via Custom Halved Kernel ★☆☆ LOW-MEDIUM

**Priority**: 7
**Component**: Prefill (25% of score)
**Mechanism**: The prefill shared expert down projection uses stock MLX
`QuantizedSwitchLinear` (not the custom halved down kernel). If we route
the prefill shared down through a custom kernel that uses halved scales
(mirroring the decode `lagunaSharedDownResidual` but for batched
multi-token input), we halve the prefill shared down scale traffic.

**Target code**:
- `Sources/MLXFastModel/LagunaRuntimeModel.swift` — new prefill shared
  down dispatch (or modify existing prefill path)
- `Sources/MLXFastTransform/Transform.swift` — prepare halved prefill
  shared down scales at transform time

**Expected M5 signal**: Small. The shared expert is 1 of 257 experts. Its
down scale traffic is ~64 KiB/layer × 39 layers = ~2.5 MiB prefill. Halving
saves ~1.25 MiB. At 651.8 GB/s: ~1.9 μs. Negligible vs ~25-30 ms prefill.

**Bit-exact risk**: LOW. Same halving invariant.

**Budget impact**: HIGH code cost. A new batched kernel for prefill shared
down would be ~50-100 lines (~2-4 KB). Combined with scale prep, ~3-5 KB.
Consumes significant budget for tiny gain.

**M4 testability**: YES (prefill shared expert uses non-_nax path).

**Why it's fresh**: No PR has attempted to halve the prefill shared expert
down path. But the gain is too small to justify the cost. Include only as
a "nice to have" if budget allows.

---

## Summary: Priority Ranking for Next Assignments

| # | Idea | Component | M5 Signal | Bit-Exact | Budget | M4? | Priority |
|---|---|---|---|---|---|---|---|
| 1 | Prefill MoE gather-QMM scale halving | Prefill 25% | ~1.0-1.5% composite | LOW | ~3-4 KB | NO (M5 only) | **1 — ASSIGN NEXT** |
| 2 | Fuse final RMSNorm into LM head coarse | Decode 75% | ~0.04-0.09% | MEDIUM | ~1 KB LRM + ~1 KB LLHP | YES | **2** |
| 3 | INT8 4× scale/bias dedup (3 kernels) | Decode 75% | Instruction reduction | LOW | ~2.5-3 KB LRM | YES | **3** (budget-constrained) |
| 4 | Fuse LM head argmax + threshold | Decode 75% | ~0.04-0.09% | LOW | ~1 KB LLHP | YES | **4** |
| 5 | Standalone shared down halving | Decode fallback | None (fallback) | LOW | ~0.5 KB LRM | Guard-gated | **5** (low) |
| 6 | ROUTER_ROWS_PER_GROUP sweep | Decode 75% | <0.1% | LOW | 0 B | YES | **6** (free) |
| 7 | Prefill shared down halving | Prefill 25% | Negligible | LOW | ~3-5 KB | YES | **7** (skip) |

**Key recommendations**:

1. **Assign Idea 1 (prefill MoE scale halving) immediately** — it's the only
   idea with a >1% composite signal estimate, it's already designed, vendor
   files have ample headroom, and it targets a completely untouched code path.
   M5-only (cannot test on M4) but the mechanism is proven by PR #180.

2. **Assign Idea 2 (fuse RMSNorm into LM head) + Idea 4 (fuse argmax+threshold)
   to one student** — both touch LagunaLmHeadPrune.swift (477 KB headroom),
   neither touches the tight LagunaRuntimeModel.swift budget significantly,
   and they compound (2 fewer dispatches/step). M4-testable for correctness.

3. **Idea 3 (INT8 4× dedup) is high-value but budget-constrained** — the 3
   kernel changes total ~3 KB in LagunaRuntimeModel.swift, which exceeds the
   7,280 B headroom if done all at once. Assign ONE kernel at a time (start
   with gate-softplus, the simplest). Each is ~800-1,000 B.

4. **Idea 6 (router sweep) is free** — test in parallel with any M4 run. No
   code change, no budget cost. Low expected gain but zero risk.

## What Was Ruled Out (and why)

- **Shared SwiGLU QMV gate/up scale halving**: ALREADY DONE. Both
  `lagunaSharedSwiGLUQMVKernel` and `lagunaSharedSwiGLUQMVRows1Kernel` have
  `scale_row_bytes = 64` and `lane/2` indexing with escape wired. The
  bandwidth audit was based on a pre-PR-180-v2 code state.

- **Merge shared gate/up into routed down+residual kernel**: Saves 39
  dispatches but is architecturally infeasible. The shared gate/up needs
  ~16K threadgroups of parallelism (2048→1024 GEMV); the down kernel's
  shared simdgroup has only 32 threads. Concentrating all gate/up work into
  one simdgroup would make it 16× slower than the routed simdgroups,
  creating a massive bottleneck. The dispatch overhead savings (~1.5-3.6%)
  don't justify the compute bottleneck.

- **Attention scale halving (PR #193 retry)**: DEAD at -2.7%. The escape
  mechanism overhead exceeds bandwidth savings. The active attention path
  is INT8 affine (group-32), which doesn't have NVFP4 pairwise constancy.
  Scale halving only applies to NVFP4 fallback paths, which aren't default-on.

- **Compiled decode**: Researched and killed. Disables fused Metal kernels,
  inflates full-attention K/V traffic 1.5-6.4×, compile() cannot fuse
  custom metalKernel dispatches. Would regress on M5.

- **asyncEval schedule optimization**: Already near-optimal. Current
  `at:0,1,7,15,23,31,39` (7 fires) = 1.0170, vs ladder1 (40 fires) = 1.0178.
  The remaining 0.0008 is within noise. asyncEval=off was -10.5% regression.

- **KV cache quantization**: NOT bit-exact. Falls outside the accepted
  attention quantization envelope (covers projection weights, not cache state).

- **LM head INT8 quantization**: Would break the pruner's certified
  bit-exactness (the certificate is built on exact BF16). High risk of
  failing correctness gates.

- **Instruction-count reductions composed with scheduling changes**: ALL
  prior M5 submissions with ops-800 or QHOIST were REJECTED (-7% to -14%).
  Pure instruction reductions (PR #194 simd_sum, no scheduling changes) is
  being tested on M5 now. Do NOT compose instruction reductions with any
  scheduling change.
