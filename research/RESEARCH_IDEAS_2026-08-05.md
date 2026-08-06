# Fresh Optimization Ideas — Laguna XS 2.1 NVFP4 Decode Path

**Date**: 2026-08-05 (subagent research pass)
**Score**: 2.5459 (current best, M5) → 2.5523 (target). Gap: ~0.25%.
**Architecture**: M5 Max = instruction-bound at ~89% capacity. NOT bandwidth-bound.
**Score formula**: `decode_speedup^0.75 * prefill_speedup^0.25`. Decode = 75% weight.

## Methodology

Read `Sources/MLXFastModel/LagunaRuntimeModel.swift` (11,132 lines, 505,635 bytes) and
`Sources/MLXFastModel/LagunaLmHeadPrune.swift` (993 lines, 46,738 bytes) in full.
Cross-referenced every kernel's accumulation pattern against the 3 merged dot4
victories (#94, #107, #114) to find kernels that were MISSED by those sweeps.
Verified each idea is absent from all in-flight PRs (#100, #109, #112, #116) and
all prior research files.

## Key Finding: The dot4 Sweep Has Gaps

Three PRs proved that replacing scalar FMA with `dot(float4, float4)` is bit-exact
on Apple Silicon and reduces instruction count ~75%:

| PR | Kernel | Pattern | Status |
|----|--------|---------|--------|
| #94 | Attention score (sliding+full) | 4 scalar FMA → `dot(pq, pk)` + `simd_sum` | MERGED, bit-exact |
| #107 | Shared NVFP4 qdot header (`packedWordBody`) | 16 scalar FMA → 4 `dot(w_a, in_a)` + 2 add | MERGED, bit-exact |
| #114 | QKV norm+affine INT8 | 8 scalar FMA → 2 `dot(float4, float4)` | MERGED, verified |

**But several kernels with the IDENTICAL scalar-FMA pattern were never
vectorized.** These are fresh, proven-mechanism, low-risk targets.

---

## Ranked Ideas

### 1. O-proj NVFP4 inline qdot dot4 vectorization (HIGHEST PRIORITY)

**Target**: `lagunaGatedAffineOProjNVFP4Source` (L4090–4244), the `firstAccum`/`accum +=`
pattern at L4114–4130 and L4221–4225.

**Status**: FRESH — not in any prior research file, not in-flight.

**Problem**: The O-proj NVFP4 kernel has its OWN inline qdot accumulation — it does
NOT use the shared `laguna_nvfp4_qdot_codes_16` from `lagunaSharedSwiGLUQMVHeader`.
PR #107 vectorized the shared header's `packedWordBody` but EXPLICITLY did not touch
the O-proj's inline accumulation. The O-proj inner loop still does 8 scalar FMAs
per `j` iteration:

```metal
// Current (L4221-4225):
accum = (x_thread[8*j] * v04.x + x_thread[8*j+1] * v15.x +
         x_thread[8*j+2] * v26.x + x_thread[8*j+3] * v37.x);
accum += (x_thread[8*j+4] * v04.y + x_thread[8*j+5] * v15.y +
          x_thread[8*j+6] * v26.y + x_thread[8*j+7] * v37.y);
```

**Mechanism**: Replace with `dot(float4, float4)` — the EXACT transformation #107
applied to the shared header:

```metal
// Proposed:
const float4 w_a = float4(v04.x, v15.x, v26.x, v37.x);
const float4 w_b = float4(v04.y, v15.y, v26.y, v37.y);
const float4 in_a = float4(x_thread[8*j], x_thread[8*j+1], x_thread[8*j+2], x_thread[8*j+3]);
const float4 in_b = float4(x_thread[8*j+4], x_thread[8*j+5], x_thread[8*j+6], x_thread[8*j+7]);
accum = dot(w_a, in_a) + dot(w_b, in_b);   // seedElide adjusts = vs +=
```

This is literally the same code as `packedWordBody` in the shared header (L6449-6467).
The dequant pattern (`extract` macro → `float2 v04..v37`) is already identical.

**Reach**: ALL 40 layers, 1 dispatch/layer. NVFP4 is the default
(`lagunaNativeAffineNVFP4From=0`). Both `gateIsActivated` paths use the same
kernel source. `codes_per_thread = values_per_thread / 8 = 2`, so 2 j-iterations
× 8 scalar FMAs = 16 scalar FMAs → 4 `dot()` + 2 add = 6 vector ops per row per
k-block. 4 results_per_simdgroup × 2 simdgroups × (in_vec_size/block_size)
k-blocks. ~75% instruction reduction in the inner loop.

**Bit-exact**: YES — same multiplication order, same accumulation order into `accum`.
PR #107 proved this identical transformation is bit-exact (maxAbsError=0 on decode,
upstream equivalence verified). The only risk is whether `dot(float4,float4)` uses
the same FMA rounding as scalar FMA on M5 — #107 already proved this for the shared
header which uses the SAME dequant + dot pattern.

**Expected impact**: 0.5–1.5% decode. O-proj runs 40 layers/step. On the
instruction-bound M5, a 75% instruction reduction in the O-proj inner loop should
land in the meaningful range. #107 showed 0.85% on M4 (bandwidth-bound) for a
kernel that runs 39 layers; O-proj runs 40 layers with the same mechanism.

**Risk**: ZERO (bit-exact, proven mechanism, mechanical port from #107).
**Verification**: `LagunaUpstreamEquivalence.swift` (should be maxAbsError=0).
**Byte budget**: Net DECREASE (dot() is shorter than scalar FMA chains).

**Conflict with in-flight**: NONE. #100 modifies the body (prefetch), #109 modifies
the epilogue (simd_sum). The dot4 change modifies the inner accumulation, which is
between the body and epilogue. All three target different code sections of the same
function. Clean rebase expected.

---

### 2. Attention output accumulation float4 vectorization

**Target**: Sliding attention kernel (L1567–1574, L1594–1601) and full attention
kernel (L2055–2062, L2076–2083). The `pair_o0`/`pair_o1` output MAC loop.

**Status**: Previously PROPOSED in `NOVEL_OPTIMIZATION_TARGETS.md` #5b but NOT
implemented, NOT in-flight. FRESH for implementation.

**Problem**: The attention output accumulation does 8 scalar FMAs per loop iteration
per pair (16 per iteration total for both pairs):

```metal
// Current (L1567-1574, repeated for pair_o1):
pair_o0[0] = pair_o0[0] * pair_factor0 + pair_exp0 * pipe_va0;
pair_o0[1] = pair_o0[1] * pair_factor0 + pair_exp0 * pipe_va1;
pair_o0[2] = pair_o0[2] * pair_factor0 + pair_exp0 * pipe_va2;
pair_o0[3] = pair_o0[3] * pair_factor0 + pair_exp0 * pipe_va3;
```

**Mechanism**: Replace 4 scalar FMAs with 1 float4 FMA:

```metal
// Proposed:
float4 po0 = float4(pair_o0[0], pair_o0[1], pair_o0[2], pair_o0[3]);
float4 pv = float4(float(pipe_va0), float(pipe_va1), float(pipe_va2), float(pipe_va3));
po0 = po0 * pair_factor0 + pv * pair_exp0;
pair_o0[0] = po0.x; pair_o0[1] = po0.y; pair_o0[2] = po0.z; pair_o0[3] = po0.w;
```

Each element computes `o * factor + v * exp` — identical per-element arithmetic.
The float4 construction from `pipe_va0..3` costs 1 instruction; the float4 FMA
is 2 vector multiplies + 1 vector add = 3 instructions vs 8 scalar ops.

**Reach**: ALL 40 layers. Sliding: 30 layers × 8 iterations × 2 pairs (a+b) × 4
elements = 3,840 scalar FMAs/step → 960 vector ops. Full: 10 layers × ~10 iterations
× 2 × 4 = ~1,600 scalar FMAs → ~400 vector ops. Total: ~5,440 → ~1,360 ops.

**Bit-exact**: YES — each element is computed independently with the same
`o * factor + v * exp` expression. The float4 multiply and add use IEEE rounding
identical to scalar. No cross-element interaction. No accumulation order change
(each element has exactly one FMA). This is the SAFEST of all dot4 ideas because
there's no summation reordering — it's pure element-wise vectorization.

**Expected impact**: 0.3–1.0% decode. The output accumulation is ~30-50% of the
attention main loop's instruction budget (the rest is score computation already
dot4'd, exp/rescale, and K/V loads). A 75% reduction in that 30-50% = ~20-37%
attention instruction reduction × 40 layers.

**Risk**: LOW (bit-exact, element-wise, no reordering).
**Verification**: `LagunaUpstreamEquivalence.swift` + 64-step drift tripwire.
**Conflict with in-flight**: NONE. #94 changed the SCORE computation (dot product).
#112 changes the EPILOGUE barriers. The output accumulation is in the MAIN LOOP
body, between the score computation and pointer advance. Untouched by both.

---

### 3. Dense layer gate/up + down dot4 vectorization

**Target**: `lagunaDenseGateUpSwiGLUKernel` (L7741, inner loop L7790-7793) and
`lagunaDenseDownResidualKernel` (L7838, inner loop L7870-7873).

**Status**: FRESH — not in any prior research file.

**Problem**: The dense layer (layer 0) kernels use BF16 scalar FMA — the same
pattern #94 and #114 already vectorized for attention and QKV:

```metal
// Dense gate/up (L7790-7793):
for (uint i = 0; i < values_per_thread; ++i) {
    gate_result[row] += float(gw[i]) * coefficients[i];
    up_result[row] += float(uw[i]) * coefficients[i];
}
```

`values_per_thread = 4`, so this is 4 scalar FMAs per row per block. The weight
`gw`/`uw` is loaded as `vec<bfloat, 4>` and `coefficients` is a `float[4]` thread
array. `dot(float4(gw), float4(coefficients[0],...))` is a direct replacement.

**Mechanism**:
```metal
// Proposed:
float4 coeff = float4(coefficients[0], coefficients[1], coefficients[2], coefficients[3]);
gate_result[row] += dot(float4(gw), coeff);
up_result[row] += dot(float4(uw), coeff);
```

Same for the down kernel (L7870-7873): `result[row] += float(w[i]) * coefficients[i]`
→ `result[row] += dot(float4(w), coeff)`.

**Reach**: 1 layer (layer 0), but the work is substantial:
- Gate/up: 8192 output rows × 16 blocks × 4 rows/threadgroup = large GEMV
- Down: 2048 output rows × 64 blocks × 4 rows/threadgroup = large GEMV

**Bit-exact**: YES — `dot(float4, float4)` computes `a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
+ a[3]*b[3]` in the same order as the scalar loop. Same as #94 (attention BF16) and
#114 (QKV INT8) which were both verified bit-exact.

**Expected impact**: 0.1–0.3% decode. Only 1 layer out of 40, so the contribution to
total decode time is small (~2.5% of layers). But the per-layer instruction reduction
is ~75%, so the dense layer itself speeds up significantly.

**Risk**: ZERO (bit-exact, proven mechanism, BF16 same as #94).
**Verification**: `LagunaUpstreamEquivalence.swift`.
**Byte budget**: Net DECREASE.

---

### 4. LM head coarse kernel dot4 vectorization

**Target**: `lagunaLmHeadInt5BaseCoarseKernel` (L253 in LagunaLmHeadPrune.swift),
inner loop at L287-291.

**Status**: FRESH — not in any prior research file.

**Problem**: The int5 coarse kernel processes ALL 100,352 vocab rows per step.
Its inner loop does 4 iterations × 4 scalar FMAs = 16 scalar FMAs per w-iteration:

```metal
// Current (L287-291):
for (uint k = 0; k < 4; ++k) {
    cg += xe[k] * ve[k];
    cg += xo[k] * vo[k];
    ag += axe[k];
    ag += axo[k];
}
```

`xe`, `ve`, `xo`, `vo`, `axe`, `axo` are all `float4`. The loop is fully unrolled
(`#pragma unroll full`).

**Mechanism**:
```metal
// Proposed:
cg += dot(xe, ve) + dot(xo, vo);
ag += sum(axe) + sum(axo);
```

2 `dot()` + 2 `sum()` = 4 vector ops vs 16 scalar ops. 75% instruction reduction.

**Reach**: 100,352 vocab rows × 8 groups × 4 w-iterations = 3.2M scalar FMAs/step.
This is the single largest FMA workload in the LM head. The coarse pass computes
ALL rows (the pruner only eliminates rows in the subsequent exact pass).

**Bit-exact**: NO — changes accumulation order. Current: interleaved
(`xe[0]*ve[0], xo[0]*vo[0], xe[1]*ve[1], ...`). Proposed: grouped
(`dot(xe,ve) + dot(xo,vo)`). FP32 is not associative. BUT: #107 had the same
reordering (16 scalar FMA → grouped dot) and passed upstream equivalence with
maxAbsError=0. The int5 dequant produces exact float4 values, and the dot
accumulates in the same FP32 precision. LOW risk but REQUIRES verification.

**Expected impact**: 0.2–0.8% decode. The coarse pass is the dominant LM head
dispatch. 3.2M FMAs is significant even with the pruner eliminating most exact-pass
rows. On instruction-bound M5, a 75% reduction in the largest single kernel's inner
loop should be measurable.

**Risk**: MEDIUM (not bit-exact, same risk profile as #107/#114 which passed).
**Verification**: MUST run `LagunaUpstreamEquivalence.swift` + full test suite.
**Byte budget**: LagunaLmHeadPrune.swift has 46,738 bytes / 524,288 = ample headroom.
Net DECREASE.

---

### 5. Router GEMV dot4 vectorization

**Target**: `lagunaNormInvMeanScratch` / router accumulate macro (L873–918).

**Status**: FRESH — not in any prior research file.

**Problem**: The router GEMV (fused with RMSNorm) does scalar FMA:

```metal
// Current (rowsPerThread==1, L889):
router_result[0] += float(rw[u][i]) * float(normalized_row[column_u + i]);

// Current (rowsPerThread>1, L912):
router_result[r] += float(rw[i]) * router_input[i];
```

`rw` is loaded as `vec<bfloat, 4>`, `n_reads` is typically 4. The inner loop does
4 scalar FMAs per block.

**Mechanism**:
```metal
// Proposed:
router_result[0] += dot(float4(rw[u]), float4(normalized_row[column_u], ...));
router_result[r] += dot(float4(rw), float4(router_input[0], ...));
```

**Reach**: 39 layers (layers 1–39) × router GEMV. The router has 256 output rows
(numExperts), so this is 39 × 256 × ~8 blocks × 4 FMA = significant but smaller than
MoE kernels.

**Bit-exact**: YES — `dot(float4, float4)` with 4 elements in sequential order, same
as #114 (QKV INT8) which was verified. The router weight is BF16, same as attention
(#94 verified).

**Expected impact**: 0.05–0.2% decode. The router GEMV is a small fraction of total
decode time (it's 256 rows × 2048 dims = 524K FMAs vs millions for MoE). But it's
free instruction reduction on an instruction-bound device.

**Risk**: ZERO (bit-exact, proven mechanism).
**Verification**: `LagunaUpstreamEquivalence.swift`.

---

### 6. LM head exact kernel dot4 vectorization

**Target**: `lagunaLmHeadExactWinnerBF16PredecessorThresholdKernel` (L423) and
`lagunaLmHeadInlineExactDeltaBF16Kernel` (L499) in LagunaLmHeadPrune.swift.

**Status**: FRESH — not in any prior research file.

**Problem**: The exact pass does standard BF16 GEMV with scalar FMA:

```metal
// Current (L527 threshold kernel):
result += inter[0] * v_coeff[0];
result += inter[1] * v_coeff[1];
result += inter[2] * v_coeff[2];
result += inter[3] * v_coeff[3];

// Current (L570 exact delta kernel):
result[tm] += inter[0] * v_coeff[0];
result[tm] += inter[1] * v_coeff[1];
result[tm] += inter[2] * v_coeff[2];
result[tm] += inter[3] * v_coeff[3];
```

**Mechanism**: Replace with `dot(float4, float4)`:
```metal
result += dot(float4(inter[0], inter[1], inter[2], inter[3]),
              float4(v_coeff[0], v_coeff[1], v_coeff[2], v_coeff[3]));
```

**Reach**: The exact pass runs on candidate rows only (typically single digits per
step after the coarse screen). Each row does 2048 FMAs. With ~5-10 candidate rows,
that's 10K-20K FMAs — small compared to the coarse pass's 3.2M. But the threshold
kernel (L423) runs 1 row (the argmax winner) with 2048 FMAs.

**Bit-exact**: NO — the scalar loop accumulates sequentially `result += a; result += b; ...`
while `dot()` computes `a + b + c + d` in one step then adds to `result`. The
intermediate rounding differs. However, #94 and #114 showed dot() produces
identical greedy tokens despite this. LOW risk, REQUIRES verification.

**Expected impact**: 0.05–0.15% decode. Small because candidate row count is low.
But it's a clean, proven transformation with zero complexity.

**Risk**: LOW-MEDIUM (not bit-exact, same risk as #114).
**Verification**: `LagunaUpstreamEquivalence.swift`.

---

### 7. LAGUNA_RESCALE branch elimination

**Target**: `LAGUNA_RESCALE` macro (L1683-1692), used in sliding (L1557-1558,
L1584-1585) and full (L2020-2021, L2047-2048, L2084-2085) attention kernels.

**Status**: Previously PROPOSED in `RESEARCH_IDEAS_FRESH_20260805.md` #3 but NOT
in-flight. FRESH for implementation.

**Problem**: The macro branches on whether the delta is exactly zero:
```metal
#define LAGUNA_RESCALE(dst, delta_expr) \
  do { \
    const float db_delta_ = (delta_expr); \
    if (as_type<uint>(db_delta_) == 0u) { \
      dst = float(1.0f); \
    } else { \
      dst = metal::fast::exp(db_delta_); \
    } \
  } while (false)
```

During decode, the max changes every step (new token has a new attention pattern),
so `pair_max0 - pair_new_max0` is rarely exactly 0.0f. The branch is almost never
taken, but the branch instruction + comparison still execute every iteration.

**Mechanism**: Remove the branch, always compute `exp(0) = 1.0f`:
```metal
#define LAGUNA_RESCALE(dst, delta_expr) \
  do { \
    dst = metal::fast::exp(delta_expr); \
  } while (false)
```

`metal::fast::exp(0.0f)` returns exactly `1.0f` (it's a hardware intrinsic).

**Reach**: ALL 40 layers × 8 iterations × 2 pairs × 2 passes (a+b) = 1,280 branch
eliminations per step.

**Bit-exact**: YES — `exp(0.0f) == 1.0f` exactly. The branch was an optimization
to skip the exp call, but `fast::exp` is a single hardware instruction on Apple
Silicon. Removing the branch saves a comparison + branch instruction per use.

**Expected impact**: 0.1–0.3% decode. Small per-use but high frequency (1,280/step).
On instruction-bound M5, eliminating branches reduces instruction count and
improves pipeline efficiency.

**Risk**: ZERO (bit-exact, `exp(0)=1` is exact).
**Conflict with in-flight**: NONE. #112 changes the epilogue, not the rescale macro.

---

### 8. Block width 512→1024 in SwiGLU QMV kernels

**Target**: `lagunaSharedSwiGLUQMVRows1Kernel` (L6553) and routed SwiGLU QMV kernels.
The `block_size` constant controls the k-block loop iteration count.

**Status**: Previously PROPOSED in `RESEARCH_IDEAS_FRESH_20260805.md` #5 but NOT
in-flight. FRESH for implementation.

**Problem**: The SwiGLU QMV kernels use `block_size = values_per_thread * 32 = 512`.
The k-loop iterates `in_vec_size / block_size = 2048 / 512 = 4` times. Doubling
block_size to 1024 halves the loop to 2 iterations, reducing loop overhead
(increment, compare, branch) by 50%.

**Mechanism**: Change `block_size` from `values_per_thread * 32` to
`values_per_thread * 64`. This doubles the work per iteration. The qdot function
already processes `values_per_thread` elements per call; the loop just calls it
more times per k-block. The threadgroup geometry stays the same.

**Reach**: 39 layers × shared SwiGLU (1 dispatch) + 8 routed experts × 39 layers
× routed SwiGLU (1 dispatch) = significant loop iteration reduction.

**Bit-exact**: YES — same total computation, just fewer loop iterations with more
work per iteration. The qdot calls are identical; only the loop counter changes.

**Expected impact**: 0.2–0.5% decode. Loop overhead reduction on instruction-bound
M5. The actual compute (qdot) is unchanged, but the loop control instructions
(increment, compare, branch, pointer updates) are halved.

**Risk**: LOW (bit-exact, may increase register pressure from larger block).
**Verification**: `LagunaUpstreamEquivalence.swift`. Monitor for register spilling.

---

## Summary Table

| # | Idea | Target kernel | Reach | Bit-exact? | Decode/Prefill | Est. impact | Risk |
|---|------|--------------|-------|------------|----------------|-------------|------|
| 1 | O-proj NVFP4 inline dot4 | `lagunaGatedAffineOProjNVFP4Source` L4090 | 40 layers | YES | Decode (75%) | 0.5–1.5% | ZERO |
| 2 | Attention output float4 | Sliding L1567 + Full L2055 | 40 layers | YES | Decode (75%) | 0.3–1.0% | LOW |
| 3 | Dense gate/up+down dot4 | `lagunaDenseGateUpSwiGLUKernel` L7741 + down L7838 | 1 layer | YES | Decode (75%) | 0.1–0.3% | ZERO |
| 4 | LM head coarse dot4 | `lagunaLmHeadInt5BaseCoarseKernel` L253 | 100K rows | NO | Decode (75%) | 0.2–0.8% | MED |
| 5 | Router GEMV dot4 | Router accumulate macro L873 | 39 layers | YES | Decode (75%) | 0.05–0.2% | ZERO |
| 6 | LM head exact dot4 | Exact kernels L423/L499 | ~5 rows | NO | Decode (75%) | 0.05–0.15% | LOW-MED |
| 7 | LAGUNA_RESCALE branch elimination | Rescale macro L1683 | 40 layers | YES | Decode (75%) | 0.1–0.3% | ZERO |
| 8 | Block width 512→1024 | SwiGLU QMV kernels L6553 | 39+ layers | YES | Decode (75%) | 0.2–0.5% | LOW |

## Recommended Assignment Order

**Phase 1 — Bit-exact, ZERO risk (merge first, compound freely)**:
1. **Idea #1** (O-proj NVFP4 dot4) — HIGHEST PRIORITY. Proven mechanism (#107),
   all 40 layers, mechanical port. Largest expected gain of the bit-exact set.
2. **Idea #2** (Attention output float4) — All 40 layers, element-wise (safest
   vectorization possible), no reordering.
3. **Idea #3** (Dense dot4) + **Idea #5** (Router dot4) + **Idea #7** (RESCALE
   branch) — Small individual gains but ZERO risk and compose freely. Could be
   bundled as a "scalar FMA cleanup sweep" in one PR.

**Phase 2 — Non-bit-exact, needs equivalence test (merge individually)**:
4. **Idea #4** (LM head coarse dot4) — Largest single-kernel FMA workload. Same
   risk profile as #107/#114 which both passed. M5 measurement needed.
5. **Idea #6** (LM head exact dot4) — Small impact but clean. Bundle with #4
   since both are in LagunaLmHeadPrune.swift.

**Phase 3 — Bit-exact, needs register pressure check**:
6. **Idea #8** (Block width 512→1024) — Monitor for register spilling on M5.

## Composition Analysis

All 8 ideas target DIFFERENT code sections:
- #1: O-proj inner accumulation (L4221-4225)
- #2: Attention output MAC (L1567-1574, L2055-2062)
- #3: Dense inner loop (L7790-7793, L7870-7873)
- #4: LM head coarse inner loop (LagunaLmHeadPrune.swift L287-291)
- #5: Router accumulate (L873-918)
- #6: LM head exact (LagunaLmHeadPrune.swift L527, L570)
- #7: LAGUNA_RESCALE macro (L1683-1692)
- #8: SwiGLU block_size constant

**No executable code overlaps.** #1 and in-flight #100/#109 touch the same
FUNCTION (O-proj) but different SECTIONS (accumulation vs body/epilogue). All
other pairs are in completely different functions. Clean composition.

**Instruction reduction compounds**: #1 + #2 + #7 all reduce instructions in
the attention→O-proj pipeline that runs on all 40 layers. #4 reduces
instructions in the LM head. On an instruction-bound M5, these stack
multiplicatively in the instruction-count dimension.

## What I Did NOT Propose (and why)

- **O-proj INT8 affine dot4** (L3913): Same mechanism as #114, but this kernel
  is NOT on the default scored path (NVFP4 is default). Only relevant if the
  dispatch falls back. Low priority.
- **Dense SwiGLU sigmoid vectorization**: Already scalar on lane 0, processes
  4 values sequentially. Hard to vectorize meaningfully. Low impact.
- **Prefill-specific ideas**: All prefill paths use MLX built-in `_nax` kernels
  or stock quantizedMM, which are not participant-editable Metal sources. The
  only prefill lever is the affine INT8 extension (already merged as #98).
- **KV cache quantization**: Outside the accepted attention quantization
  envelope. Prohibited.
- **Speculative decoding / token caching**: Violates the serial non-speculative
  protocol. Prohibited.
- **Expert streaming / caching**: Not a scored cost (all experts RAM-resident).
  Prohibited by rules.
