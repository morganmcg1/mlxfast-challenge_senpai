# TOP 3 Decode Optimization Opportunities — Alphonse Next Experiment

**Date:** 2026-08-06
**Analyst:** Metal kernel optimization subagent
**Target:** `Sources/MLXFastModel/LagunaRuntimeModel.swift` (504,934 / 524,288 bytes; 19,354 bytes headroom)
**Score gap:** 2.5459 (current best) vs 2.5523 (target lBroth) = ~0.25%
**Hardware:** M5 Max — **instruction-bound** at ~89% GPU capacity (M4 is bandwidth-bound)

---

## In-Flight Experiments (avoided)

| PR | Description | Code touched |
|----|-------------|-------------|
| #102 | threadGroup 1024→128 in attention kernels | Swift dispatch params only |
| #100 | depth-1 prefetch in O-proj decode kernel | O-proj kernel weight loop (L4202-4235) |
| #98 | prefill O-proj affine INT8 extension | Merged (b6a0889) |
| #107 | NVFP4 qdot dot4 vectorization in **shared header** | `lagunaSharedSwiGLUQMVHeader` packedWordBody (L6415-6441) |

## Prior Results (avoided)

#94 (merged: simd_dot attention), #97 (negative: prefill shared dispatch), #96 (negative: shared SwiGLU register prefetch), #93 (negative: down+residual register prefetch), #95 (dead: O-proj unroll env unreachable), #75 (negative: TG input staging routed R1 on M4), #74 (negative: prefetch depth 2→4 routed R1), #89 (negative: down+residual 4→8 SIMD groups), #51 (closed: LM-head coarse pass).

---

## Opportunity #1: Vectorize `simd_sum` in routed+shared down+residual kernel

**Kernel:** `lagunaRoutedSharedDownResidualKernel` — `laguna_routed_shared_nvfp4_down_residual_bf16_r1_v5`
**Lines:** L7621–7633 (epilogue reduction loop)
**Dispatch:** grid=`(2048/4)*288=147,456` TGs, threadGroup=`(288,1,1)` = 9 simdgroups/TG
**Runs:** 39 MoE layers × 1 dispatch/layer = 39 invocations/step

### Current code (L7621–7633)
```metal
thread float result[outputs_per_simd] = {0.0f};
for (uint row = 0; row < outputs_per_simd; ++row) {
    uint output_row = first_row + row;
    const device uint8_t* weight =
        expert_weight + output_row * packed_row_bytes + lane * 8;
    const device uint8_t* scale =
        expert_scales + output_row * scale_row_bytes + lane;
    result[row] = laguna_nvfp4_qdot_16(
        weight,
        input_values,
        laguna_nvfp4_scale(scale[0]));
    result[row] = simd_sum(result[row]);   // ← 4 separate scalar simd_sum calls
}
```

### Proposed change
Replace the 4-iteration loop's scalar `simd_sum` with a single vectorized
`simd_sum(vec<float,4>)`, mirroring the **already-proven** pattern in
`lagunaRoutedDownReduceKernel` (L7468–7475):

```metal
thread float result[outputs_per_simd] = {0.0f};
for (uint row = 0; row < outputs_per_simd; ++row) {
    uint output_row = first_row + row;
    const device uint8_t* weight =
        expert_weight + output_row * packed_row_bytes + lane * 8;
    const device uint8_t* scale =
        expert_scales + output_row * scale_row_bytes + lane;
    result[row] = laguna_nvfp4_qdot_16(
        weight,
        input_values,
        laguna_nvfp4_scale(scale[0]));
}
{
    const vec<float, 4> packed_rows = simd_sum(
        vec<float, 4>(result[0], result[1], result[2], result[3]));
    result[0] = packed_rows.x;
    result[1] = packed_rows.y;
    result[2] = packed_rows.z;
    result[3] = packed_rows.w;
}
```

### Why it helps on M5 (instruction-bound)
- **4 scalar `simd_sum` → 1 vector `simd_sum(vec4)`.** Each scalar `simd_sum`
  issues ~5 shuffle/reduce instructions (log₂32 = 5 steps). The vec4 variant
  performs 4 independent horizontal reductions in the same 5-step shuffle
  sequence, so 20 instructions → 5 instructions per threadgroup.
- The down+residual kernel runs 147,456 threadgroups × 9 simdgroups =
  1,327,104 simdgroups per invocation. 39 layers/step → ~51.8M simdgroups/step.
  Savings: ~777M fewer shuffle instructions/step (15/20 × 51.8M × 5).
- The `lagunaRoutedDownReduceKernel` at L7468–7475 already uses this exact
  vectorized pattern in the same codebase, proving correctness.

### Bit-exactness: YES (class A)
`simd_sum(vec<float,4>(a,b,c,d))` performs 4 independent per-component
horizontal sums across 32 lanes — each component gets the identical
shuffle-reduction sequence as a standalone scalar `simd_sum`. The per-element
result is bitwise identical. The lagunaNvfp4RowScaleSuffix multiply and the
bfloat cast in the epilogue (L7638–7642) operate on the same post-reduction
values in the same order.

### Estimated byte cost
~+150 bytes (replace 2-line loop epilogue with 8-line vec4 block, minus the
scalar simd_sum line). Well within 19,354 bytes headroom.

### Conflict check
- **#107 (qdot dot4):** Changes the `lagunaSharedSwiGLUQMVHeader`'s
  `packedWordBody` function. This change is in the **kernel body** (the
  `lagunaRoutedSharedDownResidualKernel` source string), not the header. No
  overlap.
- **#100 (O-proj prefetch):** Different kernel entirely. No overlap.
- **#102 (attention TG):** Different kernel. No overlap.

---

## Opportunity #2: Vectorize `simd_sum` + scale multiply in NVFP4 O-proj kernel epilogue

**Kernel:** `lagunaGatedAffineOProjNVFP4Kernels` / `lagunaActivatedOProjKernels` —
`laguna_gated_affine_oproj_nvfp4_qmv_h{heads}_v1`
**Lines:** L4237–4242 (epilogue reduction + cast)
**Source:** `lagunaGatedAffineOProjNVFP4Source()` (L4090–4243) — has its **own**
inline nibble extraction and FMA accumulation, NOT the shared qdot header.
**Dispatch:** grid=`(2048/8)*64=16,384` TGs, threadGroup=`(64,1,1)` = 2 simdgroups/TG
**Runs:** 40 layers × 1 dispatch/layer = 40 invocations/step

### Current code (L4237–4242)
```metal
for (uint row = 0; row < results_per_simdgroup; ++row) {
    result[row] = simd_sum(result[row] * 4194304.0f);  // 4 separate scalar simd_sum
    if (simd_lid == 0) {                              //   + 4 scalar multiplies
        projected[out_row + row] = bfloat(result[row]);
    }
}
```

### Proposed change
```metal
{
    const vec<float, 4> scaled = vec<float, 4>(
        result[0], result[1], result[2], result[3]) * 4194304.0f;
    const vec<float, 4> reduced = simd_sum(scaled);
    if (simd_lid == 0) {
        projected[out_row + 0] = bfloat(reduced.x);
        projected[out_row + 1] = bfloat(reduced.y);
        projected[out_row + 2] = bfloat(reduced.z);
        projected[out_row + 3] = bfloat(reduced.w);
    }
}
```

### Why it helps on M5 (instruction-bound)
- **4 scalar multiplies → 1 vec4 multiply.** `vec4 * scalar` is a single
  vector instruction vs 4 scalar FMUL.
- **4 scalar `simd_sum` → 1 vec4 `simd_sum`.** Same mechanism as Opportunity #1:
  20 shuffle instructions → 5.
- **4 conditional branches → 1.** The `if (simd_lid == 0)` is evaluated once
  instead of 4 times, reducing branch divergence overhead.
- Total: 16,384 TGs × 2 simdgroups = 32,768 simdgroups × 40 layers =
  1,311,040 simdgroups/step. Savings: ~15 instructions/simdgroup × 1.3M =
  ~19.7M fewer instructions/step.
- This kernel runs on **all 40 layers** (both sliding and full attention
  heads), making it the highest-throughput NVFP4 kernel in the decode path.

### Bit-exactness: YES (class A)
- `vec4 * scalar`: per-component multiply, identical to 4 scalar multiplies.
- `simd_sum(vec4)`: per-component horizontal reduction, identical to 4
  scalar simd_sums (same argument as Opportunity #1).
- The `bfloat()` cast operates on the same post-reduction values.

### Estimated byte cost
~+120 bytes (replace 6-line loop with 10-line vec4 block). Negligible.

### Conflict check
- **#107 (qdot dot4):** The O-proj kernel has its **own** inline nibble
  extraction (L4133–4142) and FMA accumulation (L4214–4227) — it does NOT use
  the shared `lagunaSharedSwiGLUQMVHeader` that #107 modifies. **No overlap.**
- **#100 (O-proj prefetch):** #100 adds depth-1 prefetch to the **weight
  loading loop** (L4202–4235, inside the `for k` loop). This change is in the
  **epilogue** (L4237–4242, after the loop). Different code section of the
  same kernel source string — a merge conflict is possible but trivially
  resolvable (no line overlap). **Low conflict risk.**
- **#102 (attention TG):** Different kernel. No overlap.

---

## Opportunity #3: Vectorize `simd_sum` in shared SwiGLU QMV kernel (rows1 variant)

**Kernel:** `lagunaSharedSwiGLUQMVRows1Kernel` — `laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1`
**Lines:** L6612–6613 (epilogue reduction)
**Dispatch:** grid=`(256*64)=16,384` TGs (when rows1 enabled, which is the
default), threadGroup=`(64,1,1)` = 2 simdgroups/TG
**Runs:** 39 MoE layers × 1 dispatch/layer = 39 invocations/step

### Current code (L6612–6613)
```metal
gate_result = simd_sum(gate_result);   // scalar
up_result = simd_sum(up_result);       // scalar
```

### Proposed change
```metal
const vec<float, 2> reduced = simd_sum(
    vec<float, 2>(gate_result, up_result));
gate_result = reduced.x;
up_result = reduced.y;
```

### Why it helps on M5 (instruction-bound)
- **2 scalar `simd_sum` → 1 vec2 `simd_sum`.** Each scalar simd_sum is ~5
  shuffle instructions; the vec2 variant does both in 5 steps. Saves 5
  instructions per simdgroup.
- 16,384 TGs × 2 simdgroups × 39 layers = 1,278,912 simdgroups/step.
  Savings: ~6.4M fewer shuffle instructions/step.
- Smaller absolute savings than #1 and #2, but the shared SwiGLU QMV is on
  the critical decode path for every MoE layer and the change is trivially
  safe.

### Bit-exactness: YES (class A)
`simd_sum(vec<float,2>(a,b))` performs 2 independent per-component horizontal
sums — each component's reduction is bitwise identical to a standalone
scalar `simd_sum`. The SwiGLU activation (exp/abs/sigmoid) operates on the
same post-reduction values in the same order.

### Estimated byte cost
~+80 bytes (replace 2 lines with 4 lines). Negligible.

### Conflict check
- **#107 (qdot dot4):** #107 modifies `lagunaSharedSwiGLUQMVHeader`'s
  `packedWordBody`. This change is in the **kernel body** source string
  (`lagunaSharedSwiGLUQMVRows1Kernel`), not the header. However, both are in
  the same Swift file. The kernel body uses the header via the `header:`
  parameter; the simd_sum epilogue is separate source. **Low conflict risk**
  (different code regions within the same file).
- **#100 (O-proj prefetch):** Different kernel. No overlap.
- **#102 (attention TG):** Different kernel. No overlap.

---

## Summary Comparison

| # | Kernel | Lines | Mechanism | Bit-exact | Byte cost | In-flight conflict | Est. instructions saved/step |
|---|--------|-------|-----------|-----------|-----------|--------------------|-----------------------------|
| 1 | Routed+shared down+residual | L7621–7633 | 4× scalar simd_sum → 1× vec4 | YES | ~150 B | None | ~777M (15/TG × 51.8M TGs) |
| 2 | NVFP4 O-proj epilogue | L4237–4242 | 4× scalar simd_sum + mul → 1× vec4 | YES | ~120 B | Low (#100, diff section) | ~19.7M (15/SG × 1.3M SGs) |
| 3 | Shared SwiGLU QMV rows1 | L6612–6613 | 2× scalar simd_sum → 1× vec2 | YES | ~80 B | Low (#107, body vs header) | ~6.4M (5/SG × 1.3M SGs) |

All three are **bit-exact** (class A), target the decode path (75% of score
weight), and are independent or low-conflict with in-flight experiments.

### Priority recommendation
**Bundle #1 + #2 + #3 as a single "simd_sum vectorization sweep" experiment.**
All three apply the same proven pattern (vec simd_sum) that already ships in
`lagunaRoutedDownReduceKernel` (L7468–7475). They touch three different kernel
bodies with no cross-dependency. Combined byte cost ~350 bytes. Combined
instruction savings ~803M/step, concentrated in the three highest-throughput
NVFP4 decode kernels. On an instruction-bound M5 at 89% utilization, this
sweep targets the epilogue reduction overhead that serializes behind the
qdot compute in every threadgroup.

If only one can be assigned due to student availability, **#1 (down+residual)**
has the largest absolute instruction savings and zero conflict risk.

---

## Additional candidates considered but rejected

### Attention value accumulation vec4 (L1567–1601, L2030–2064)
8 scalar FMA → 2 vec4 FMA per KV pair. Bit-exact in principle, but the
construction overhead (`float4(pair_o0[0..3])` from a `thread float[4]`) may
cancel the savings unless `pair_o0` is refactored from `float[4]` to `float4`
throughout (medium-complexity, touches epilogue exchange at L1617–1622 and
L2114–2119). The Metal compiler may also already auto-vectorize these
independent scalar FMAs. Uncertain net gain. **Deferred.**

### O-proj inline FMA → dot4 (L4214–4227)
Same mechanism as #107 but for the O-proj's own inline accumulation. Would
replace 8 scalar mul+add with 2 `dot(float4,float4)`. NOT bit-exact (dot4
may use FMA internally, changing rounding). Needs upstream equivalence
validation. Conflicts with #100 (same kernel body). **Deferred** — natural
follow-up after #107 validates the dot4 approach on M5.

### SwiGLU fast::exp (L7353, L6617, L6543)
Replace `metal::exp` with `metal::fast::exp` in SwiGLU activation. NOT
bit-exact (fast::exp is an approximation). Only executed by lane==0 (1/32
threads), so instruction savings are minimal. Risk of failing correctness
gates outweighs benefit. **Rejected.**

### Nibble extraction pattern sweep (L6349–6382)
Three bit-manipulation patterns for NVFP4 nibble decode, all producing
identical results. Testing which compiles to fewest instructions on M5.
Speculative — compiler may already canonicalize. Conflicts with #107
(same header). **Deferred.**

### Merge shared QMV into routed QMV dispatch
Eliminates the separate shared SwiGLU QMV dispatch (1 fewer dispatch/layer
× 39 layers). Complex: requires 9-slot kernel with mixed input widths.
Previously attempted as PR #50 (closed, unresponsive). Conflicts with
#102 (attention TG) scheduling assumptions. **Deferred** — high-complexity,
not bit-exact-trivial.
