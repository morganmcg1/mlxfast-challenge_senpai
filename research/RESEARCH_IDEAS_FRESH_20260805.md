# Fresh Optimization Ideas — Laguna XS 2.1 NVFP4 Decode Path

**Date:** 2026-08-06 08:30 UTC
**Baseline score:** 2.5459 | Target: 2.5523 | Gap: 0.25%
**File:** `Sources/MLXFastModel/LagunaRuntimeModel.swift` (504,877 / 524,288 bytes; 19,411 headroom)
**Hardware:** M5 Max 128 GB — instruction-bound at ~89% capacity (NOT bandwidth-bound)

## Already Tried (DO NOT DUPLICATE)

| PR | Idea | Result |
|----|------|--------|
| #94 | simd_dot / dot()+simd_sum in attention score | MERGED |
| #84 | top-8 elimination in MoE | MERGED |
| #49 | Graph-visible KV cache position | MERGED |
| #97 | Prefill dispatch elimination | NEGATIVE (dispatch overhead negligible) |
| #93 | Down+residual register-prefetch | NEGATIVE (bandwidth-bound kernel) |
| #96 | Shared SwiGLU QMV prefetch | NEGATIVE (register pressure) |
| #74 | Prefetch depth 2→4 (routed R1) | NEGATIVE |
| #75 | TG input staging (routed R1) | NEGATIVE (L1 handles redundancy on M4) |
| #89 | Down+residual outputs_per_simd 4→8 | NEGATIVE (register pressure) |
| #95 | O-proj unroll sweep (DARKBLOOM_L5_UNROLL) | DEAD (unreachable code path) |
| #51 | LM head coarse pass | CLOSED (already maximally optimized) |

## In-Flight (DO NOT DUPLICATE)

| PR | Experiment | Mechanism |
|----|-----------|-----------|
| #102 | Attention threadGroup 1024→128 | Barrier latency, occupancy |
| #100 | O-proj depth-1 prefetch (gated affine INT8) | Memory latency hiding |
| #98 | Prefill O-proj affine INT8 | Prefill bandwidth reduction |

## Decode Path Anatomy (8 dispatches per sparse MoE layer × 39 layers)

| # | Dispatch | Kernel | Lines |
|---|---------|--------|-------|
| 1 | Norm+QKV+gate (INT8 affine) | `lagunaNormAffineQKV` | 5081–5130 |
| 2 | Fused attention (sliding/full) | `lagunaSlidingFusedAttention` / `lagunaFullFusedAttention` | 1389–1722 / 1841–2229 |
| 3 | Gated affine O-proj (INT8/NVFP4) | `lagunaGatedAffineOProj` / NVFP4 variant | 4032 / 4090–4244 |
| 4 | Residual+RMSNorm+router | `lagunaResidualRMSNormRouter` | 1056–1087 |
| 5 | Router top-8 | `lagunaDecodeRouterTop8` | 8237–8367 |
| 6 | Routed gate/up SwiGLU QMV (R1) | `lagunaRoutedSwiGLUQMVPackedTop8` | 7249–7364 |
| 7 | Shared gate/up SwiGLU QMV (R1) | `lagunaSharedSwiGLUQMV` | 6558–6627 |
| 8 | Routed+shared down+residual | `lagunaRoutedSharedDownResidual` | 7561–7670 |

Per decode step: ~280 kernel dispatches across 40 layers.

---

## TOP 5 FRESH OPTIMIZATION OPPORTUNITIES

---

### Idea 1: Attention Epilogue Double-Buffering — Eliminate 2 of 3 Barriers

**Kernel/function:** Fused attention epilogue in both sliding (`lagunaSlidingFusedAttentionKernel`, lines 1592–1663) and full (`lagunaFullFusedAttentionKernel`, lines 2104–2175) attention kernels.

**Current problem:**
The cross-simdgroup reduction epilogue uses 3 threadgroup barriers for a 4-plane exchange:
1. Write pair_o0[0..1], pair_o1[0..1] to `outputs[4*BN*BDP]` → **Barrier 1** (line 1608/2120)
2. Read transposed, simd_sum, compute pair_o0[0..1], pair_o1[0..1] → **Barrier 2** (line 1631/2143)
3. Write pair_o0[2..3], pair_o1[2..3] to same buffer → **Barrier 3** (line 1639/2151)
4. Read transposed, simd_sum, compute pair_o0[2..3], pair_o1[2..3]

The buffer is reused: pass 3 overwrites pass 1's data, requiring barrier 2 to separate them. The buffer is `outputs[4 * BN * BDP]` = 4 × 32 × 33 = 4,224 floats (16.5 KB).

**Optimization mechanism:**
Double the buffer to `outputs[8 * BN * BDP]` = 8,448 floats (33 KB, well within M5's 128 KB threadgroup memory limit). Write ALL 8 values (pair_o0[0..3], pair_o1[0..3]) in a single pass, then reduce all 8 in a single transposed read pass. This eliminates barriers 2 and 3, reducing from 3 barriers to 1.

**Bit-exact:** YES. Same arithmetic operations, same data, same ordering. Only the threadgroup memory layout and barrier count change. The simd_sum reductions and final divisions are computed identically.

**Estimated instruction/barrier reduction:**
- 2 barriers eliminated per attention dispatch × 40 layers = 80 barriers per decode step
- Each barrier at 1024 threads (current) or 128 threads (#102) costs ~50–100 cycles of stall
- At 128 threads (post-#102): ~2,000–4,000 cycles saved per step ≈ 2–4 µs/step
- Additional: 2 fewer write-pass loops (each iterating pair_planes=2) saves ~8 store instructions per dispatch × 40 = 320 instructions
- **~0.3–0.6% decode speedup** (barrier elimination is especially valuable on instruction-bound hardware where sync stalls block issue slots)

**Implementation complexity:** MEDIUM. Modify the threadgroup buffer declaration, the 3 exchange passes, and the 2 barrier sites in both kernel source strings. Must verify that 33 KB threadgroup allocation doesn't reduce occupancy (M5 should handle it with 128 threads per #102).

**Independence from in-flight PRs:** Independent from #102 (threadGroup size, not buffer layout), #100 (O-proj kernel), #98 (prefill). Composes with #102 (smaller threadgroup + fewer barriers = compounding gain).

---

### Idea 2: NVFP4 qdot — Replace 16 Scalar FMA with 4 `dot(float4,float4)` + 1 Add

**Kernel/function:** `laguna_nvfp4_qdot_codes_16` in the shared header `lagunaSharedSwiGLUQMVHeader` (lines 6454–6472). This function is called by ALL NVFP4 kernels: shared SwiGLU QMV (6558–6627), routed SwiGLU QMV R1 (7249–7364), routed+shared down+residual (7561–7670), and the NVFP4 O-proj (4246–4263).

**Current problem:**
The qdot inner loop uses deeply nested scalar FMA (lines 6429–6438):
```metal
accum = fma(input[0], v04.x, fma(input[1], v15.x,
         fma(input[2], v26.x, fma(input[3], v37.x, seed))));
accum = fma(input[4], v04.y, fma(input[5], v15.y,
         fma(input[6], v26.y, fma(input[7], v37.y, accum))));
```
This is 16 scalar FMA instructions per qdot call (8 per word × 2 words). Each FMA is a separate instruction even though they operate on float2 pairs (v04, v15, v26, v37 are all float2).

PR #94 proved that `dot(float4, float4)` compiles to fewer instructions than 4 scalar FMAs on Apple Silicon — it replaced 4 scalar FMA + simd_sum (5 ops) with dot() + simd_sum (2 ops) in the attention score. The same instruction reduction applies here.

**Optimization mechanism:**
Restructure the 16 scalar FMAs into 4 `dot(float4, float4)` calls + 3 adds:
```metal
float4 in0 = float4(input[0], input[1], input[2], input[3]);
float4 in1 = float4(input[4], input[5], input[6], input[7]);
float4 w0a = float4(v04.x, v15.x, v26.x, v37.x);
float4 w0b = float4(v04.y, v15.y, v26.y, v37.y);
accum = dot(w0a, in0) + dot(w0b, in1);
```
This is 4 dot + 1 add = 5 instructions instead of 16 FMA. (With seed elision, word 0 uses assignment instead of += 0.0f, so the first word is `dot(w0a, in0)` and the second is `dot(w0b, in1) + word0_result`.)

**Bit-exact:** NO — **numerical risk.** The scalar FMA chain uses left-to-right association: `((a*b + c*d) + e*f) + g*h`, with each FMA rounding once. `dot(float4,float4)` likely uses a balanced tree or hardware dot product with a different summation order, producing different intermediate rounding. The final result may differ by 1 ULP in some cases. The upstream equivalence test (`LagunaUpstreamEquivalence`) would determine if greedy tokens still match.

**Estimated instruction reduction:**
- 16 FMA → 4 dot + 1 add = 5 instructions per qdot (69% reduction in the dot product body)
- Total qdot calls per decode step: ~5.15 million across all NVFP4 kernels
- The dequant overhead (13 int ops per code word) is unchanged, so per-qdot total: ~21 ops → ~10 ops (~52% reduction)
- **~0.5–2.0% decode speedup** if correctness passes (this is the single highest-impact instruction reduction available)

**Implementation complexity:** MEDIUM. Modify `packedWordBody()` (lines 6415–6441) in the shared header string generator. The float4 constructions may be free if the compiler already packs values into vector registers. Must test bit-exactness via upstream equivalence.

**Independence from in-flight PRs:** Independent from #102 (attention threadGroup), #100 (O-proj prefetch — different code section of the same kernel), #98 (prefill). Note: #100 adds prefetch to the O-proj kernel body; #2 changes the shared header. They compose but both touch the O-proj kernel, so test composition carefully.

---

### Idea 3: Eliminate LAGUNA_RESCALE Branch — Always Call `fast::exp`

**Kernel/function:** `LAGUNA_RESCALE` macro in the header of both attention kernels (lines 1668–1676 sliding, 2178–2186 full). Called 4× per loop iteration (pair_factor0, pair_factor1 for both a-row and b-row) in the attention KV loop.

**Current problem:**
```metal
#define LAGUNA_RESCALE(dst, delta_expr)         \
  do {                                          \
    const float db_delta_ = (delta_expr);       \
    if (as_type<uint>(db_delta_) == 0u) {       \
      dst = float(1.0f);                        \
    } else {                                    \
      dst = metal::fast::exp(db_delta_);        \
    }                                           \
  } while (false)
```
This branch checks if delta is positive zero (all bits zero) and returns 1.0f without calling exp. But `metal::fast::exp(0.0f) == 1.0f` exactly on Apple Silicon (the GPU exp instruction follows IEEE 754 for the zero input case). So the branch is unnecessary: `exp(0.0f)` already returns 1.0f.

The branch ADDS instructions: `as_type<uint>` (1), comparison (1), conditional branch (1) = 3 extra instructions per call, to save 1 exp call that would return the correct result anyway. On instruction-bound hardware, this is a net loss.

**Optimization mechanism:**
Replace the entire macro with:
```metal
#define LAGUNA_RESCALE(dst, delta_expr) dst = metal::fast::exp(delta_expr);
```
Or as a single expression to avoid the do-while:
```metal
#define LAGUNA_RESCALE(dst, delta_expr) dst = metal::fast::exp(float(delta_expr));
```

**Bit-exact:** YES (with high confidence). `fast::exp(0.0f) == 1.0f` exactly on Apple Silicon GPUs. The current branch only fires for +0.0f (`as_type<uint>(0.0f) == 0u`); for -0.0f, the branch falls through to `exp(-0.0f) == 1.0f` anyway. So the branch never changes the result. Removing it produces identical values for all inputs. Verify with upstream equivalence.

**Estimated instruction reduction:**
- 3 instructions eliminated per call × 4 calls per loop iteration = 12 per iteration
- Sliding: 8 iterations × 12 = 96 per layer × 30 layers = 2,880 per step
- Full: ~10 iterations (N=640/64) × 12 = 120 per layer × 10 layers = 1,200 per step
- Total: ~4,080 instructions eliminated per decode step
- **~0.2–0.4% decode speedup** (small but zero-risk and trivially implementable)

**Implementation complexity:** LOW. One-line macro change in two kernel header strings (sliding + full).

**Independence from in-flight PRs:** Independent from #102 (threadGroup size), #100 (O-proj), #98 (prefill). The attention loop body is untouched by any in-flight PR. #94 changed the score computation (dot+simd_sum) but not the rescale macro.

---

### Idea 4: INT8 Affine QKV Inner Loop — Replace 8 Scalar FMA with `dot(float4,float4)` + Add

**Kernel/function:** `lagunaNormAffineQKVBody` inner loop (lines 4764–4772). This runs in dispatch #1 (norm+QKV+gate) on all 40 layers per decode step.

**Current problem:**
```metal
for (uint i = 0; i < values_per_thread; ++i) {
    accum += x_thread[i] * wl[i];  // wl[i] is uint8_t, promoted to float
}
```
With `values_per_thread = 8`, this is 8 scalar multiply-add operations per row per k-block. The k-loop runs `axis_size / block_size = 2048 / 256 = 8` iterations, with `results_per_simdgroup = 4` rows per iteration. Total: 8 × 4 × 8 = 256 scalar FMA per layer, 256 × 40 = 10,240 per decode step.

**Optimization mechanism:**
Replace the 8 scalar multiply-adds with 2 `dot(float4, float4)` calls + 1 add:
```metal
float4 x0 = float4(x_thread[0], x_thread[1], x_thread[2], x_thread[3]);
float4 x1 = float4(x_thread[4], x_thread[5], x_thread[6], x_thread[7]);
float4 w0 = float4(float(wl[0]), float(wl[1]), float(wl[2]), float(wl[3]));
float4 w1 = float4(float(wl[4]), float(wl[5]), float(wl[6]), float(wl[7]));
accum = dot(w0, x0) + dot(w1, x1);
```
This is 2 dot + 1 add = 3 instructions (plus the float4 constructions, which may be free if the compiler vectorizes) instead of 8 scalar FMA. The uint8→float conversions happen in the float4 constructor (batch-converted) rather than per-element in the scalar multiply.

**Bit-exact:** NO — **numerical risk.** Same as Idea 2: `dot()` may use a different summation tree than left-to-right scalar FMA. The affine INT8 format uses per-group scales and biases, so the accumulation is `result[row] += scale * accum + sum * bias`. The `accum` value may differ by 1 ULP. The upstream equivalence test would verify correctness.

**Estimated instruction reduction:**
- 8 FMA → 2 dot + 1 add = 3 instructions per row per k-block (62% reduction in the dot body)
- 256 FMA → ~96 instructions per layer, saving ~160 per layer × 40 = 6,400 per step
- Additional: 8 uint8→float conversions may be vectorized in float4 constructor (4 → 1 per group)
- **~0.3–0.5% decode speedup** if correctness passes

**Implementation complexity:** MEDIUM. Modify the inner loop in `lagunaNormAffineQKVBody` (line 4769–4771). Must handle the uint8_t→float4 conversion carefully. The prefetch variant (`lagunaNormAffineQKVPrefetchSource`) also uses this body and must be updated consistently. Test bit-exactness via upstream equivalence.

**Independence from in-flight PRs:** Independent from #102 (attention), #100 (O-proj), #98 (prefill). The QKV kernel is dispatch #1; no in-flight PR touches it.

---

### Idea 5: MoE Gate/Up R1 Kernel — Increase block_width 512→1024 to Halve Loop Overhead

**Kernel/function:** `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` (lines 7249–7364) and the shared SwiGLU QMV R1 kernel (`lagunaSharedSwiGLUQMVRows1Kernel`, lines 6558–6627). These are dispatches #6 and #7 on the MoE decode path.

**Current problem:**
The k-loop runs `input_width / block_width = 2048 / 512 = 4` iterations. Each iteration has loop overhead: branch (1), next-block pointer computation (3–4 instructions for gate/up code and scale pointers), next-block load staging (2 loads). This is ~5 overhead instructions per iteration that don't scale with data — they're pure loop control.

With 4 iterations per row per expert, that's 20 overhead instructions per row per expert. Across 512 rows × 9 experts (8 routed + 1 shared) × 39 MoE layers = 3,564,000 overhead instructions per decode step.

**Optimization mechanism:**
Double `block_width` from 512 to 1024, and double `values_per_lane` from 16 to 32. The k-loop now runs 2 iterations instead of 4. Each iteration does 2 qdot calls per row (for the two 16-element halves of the 32-value block) instead of 1. The total qdot count is unchanged — only loop overhead is halved.

Key changes:
- `block_width`: 512 → 1024
- `values_per_lane`: 16 → 32
- `input_values[16]` → `input_values[32]` (16 extra registers)
- Each block iteration: load 32 values (8 vec4 loads), do 2 qdot calls (gate+up × 2 halves)
- The depth-1 prefetch staging must also double (4 extra registers for next-block codes/scales)

**Bit-exact:** YES. The qdot calls process the same values in the same order. The accumulation order is unchanged (each qdot is independent; the results are summed in the same `gate_result += ...` order). Only the loop iteration count changes. The prefetch loads the same addresses, just doubled in count.

**Estimated instruction reduction:**
- 2 loop iterations eliminated per row per expert → ~10 overhead instructions saved
- 512 rows × 9 experts × 39 layers × 10 = 1,801,440 instructions saved per step
- **~0.3–0.8% decode speedup** (loop overhead is pure instruction count reduction, ideal for instruction-bound hardware)

**Register pressure risk:** MEDIUM. Current register usage ~28 registers per thread. With doubling: `input_values[32]` (+16), staged codes/scales (+4) = ~48 registers. M5 Max has 256 registers per thread — well within limits. The risk is that increased register usage may reduce occupancy (fewer threadgroups resident). However, the kernel's threadgroup is only 64 threads (2 simdgroups), so occupancy is already limited by threadgroup count, not registers. This is a different kernel from PR #89's down+residual (which uses result[outputs_per_simd] arrays causing much higher register pressure).

**Implementation complexity:** MEDIUM. Modify `block_width`, `values_per_lane`, and the input load loop in both the routed R1 kernel (7249–7364) and shared R1 kernel (6558–6627). The qdot function (`laguna_nvfp4_qdot_codes_16`) processes 16 values per call, so each block iteration needs 2 calls. The prefetch staging (gate_codes, up_codes, gate_sb, up_sb) must handle 2 code words per row per block instead of 1. Verify register pressure via `metal-disassemble` or occupancy calculation.

**Independence from in-flight PRs:** Independent from #102 (attention), #100 (O-proj), #98 (prefill). No in-flight PR touches the MoE gate/up R1 kernel. PR #74 (prefetch depth 2→4, NEGATIVE) was about deepening prefetch on this kernel, not changing block_width — different mechanism, different risk profile.

---

## Summary Ranking

| # | Idea | Mechanism | Bit-exact | Complexity | Est. Impact | Risk |
|---|------|-----------|-----------|------------|-------------|------|
| 1 | Attention epilogue double-buffer | Barrier elimination (3→1) | YES | MED | 0.3–0.6% | LOW (TG memory size) |
| 2 | NVFP4 qdot dot() vectorization | 16 FMA → 4 dot+1 add | NO (numerical) | MED | 0.5–2.0% | MED (correctness gate) |
| 3 | LAGUNA_RESCALE branch removal | Eliminate dead branch | YES | LOW | 0.2–0.4% | LOW (verify exp(0)=1) |
| 4 | INT8 QKV dot() vectorization | 8 FMA → 2 dot+1 add | NO (numerical) | MED | 0.3–0.5% | MED (correctness gate) |
| 5 | MoE gate/up block_width 512→1024 | Halve loop iterations | YES | MED | 0.3–0.8% | MED (register pressure) |

**Recommended assignment order:** #3 (quick, zero-risk warmup) → #1 (bit-exact, compounding with #102) → #5 (bit-exact, highest bit-exact impact) → #2 (highest potential, needs correctness test) → #4 (fill-in, needs correctness test).

**Composability notes:**
- #1 + #102: Compose safely (barrier count + threadGroup size = compounding)
- #1 + #3: Compose safely (epilogue + loop body, different code sections)
- #2 + #4: Both use dot() but in different kernels (shared header vs QKV body). Compose if both pass correctness independently.
- #2 + #100: Both touch O-proj NVFP4 kernel (header vs body). Test composition carefully.
- #5 + #2: Both touch MoE kernels (block_width vs qdot function). Test composition — #5 doubles the number of qdot calls per block, and #2 changes the qdot implementation.
