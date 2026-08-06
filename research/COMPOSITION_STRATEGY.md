# Composition Strategy: 4 In-Flight Decode Experiments

**Date**: 2026-08-06
**Score**: 2.5459 (current best, M5) → 2.5523 (target lBroth). Gap: ~0.25%.
**Architecture**: M5 Max = instruction-bound at ~89% capacity. M4 Pro = bandwidth-bound.
**Score formula**: `decode_speedup^0.75 * prefill_speedup^0.25`. Both floors ≥ 0.95.

---

## 1. Conflict Matrix

Verified against `Sources/MLXFastModel/LagunaRuntimeModel.swift` (504,899 bytes, 11,132 lines).

### Layer / Dispatch Context (40 total layers)

| Dispatch | Kernel | Layers | Source lines | In-flight PR |
|----------|--------|--------|-------------|-------------|
| #1 Norm+QKV+Gate | `lagunaNormAffineQKVBody` | 40 (all) | L4681–4790 | #114 (body L4764–4772) |
| #2 Fused Attn | `laguna_sliding_fused_attn_ring_v2` (30 layers, L1382) + `laguna_full_fused_attn_grow_v2` (10 layers, L1842) | 40 (all) | Sliding score L1550; Full score L2013/2077. Sliding epilogue L1608–1680; Full epilogue L2105–2175 | #112 (epilogue) |
| #3 Gated O-proj NVFP4 | `lagunaGatedAffineOProjNVFP4Source` | 40 (all, default NVFP4From=0) | L4090–4244 (function), body L4190–4235, epilogue L4237–4242 | #100 (body) + #109 (epilogue) |
| #7 Shared SwiGLU QMV | `lagunaSharedSwiGLUQMVKernel` / `lagunaSharedSwiGLUQMVRows1Kernel` | 39 (layers 1–39) | Header L6334; kernel L6483 (v1) / L6535 (rows1); epilogue L6605–6617 | #109 (epilogue L6607–6608) |
| #8 Down+Residual | `laguna_routed_shared_nvfp4_down_residual_bf16_r1_v5[sf]` | 39 (layers 1–39) | L7548–7700, epilogue L7621–7633 | #109 (epilogue L7621–7633) |

### Conflict Matrix (code-section level)

| | #114 QKV body | #112 Attn epilogue | #100 O-proj body | #109 O-proj epi | #109 SwiGLU epi | #109 Down epi |
|---|---|---|---|---|---|---|
| **#114 QKV** | — | ✗ No | ✗ No | ✗ No | ✗ No | ✗ No |
| **#112 Attn** | ✗ No | — | ✗ No | ✗ No | ✗ No | ✗ No |
| **#100 O-proj body** | ✗ No | ✗ No | — | ⚠️ Same function | ✗ No | ✗ No |
| **#109 O-proj epi** | ✗ No | ✗ No | ⚠️ Same function | — | ✗ No | ✗ No |
| **#109 SwiGLU epi** | ✗ No | ✗ No | ✗ No | ✗ No | — | ✗ No |
| **#109 Down epi** | ✗ No | ✗ No | ✗ No | ✗ No | ✗ No | — |

### Key Findings

**1. PR #100 vs PR #109 (O-proj): SAME FUNCTION, DIFFERENT SECTIONS — LOW conflict risk**

- `lagunaGatedAffineOProjNVFP4Source` (L4090–4244) is one Swift function returning a Metal source string.
- **#100 (Edward)** modifies the inner loop body (L4190–4235): adds depth-1 weight prefetch behind compute within the `for (uint k = 0; k < in_vec_size; k += block_size)` loop. This touches `ws`, `sc`, `xp` pointer advancement and may add prefetch loads.
- **#109 (Askeladd)** modifies the epilogue (L4237–4242): replaces 4 scalar `simd_sum(result[row])` calls with a packed `vec4` simd_sum. These 6 lines are the reduction-and-write-back loop, structurally separated from the accumulation loop by a blank line (L4236).
- **Overlap**: None in terms of executable code. Both edit the same returned string literal, so a textual merge conflict IS possible if #100's prefetch code shifts line numbers near L4237. But the edits target logically disjoint regions (accumulation loop vs reduction epilogue). A clean rebase is likely; manual resolution if conflict markers appear.
- **Interaction**: The prefetch (#100) loads the next block's weight data into registers/L1 while the current block's qdot runs. The simd_sum packing (#109) reduces shuffle instructions in the epilogue. These compose: prefetch hides latency during accumulation, packing speeds up the reduction. No semantic conflict.

**2. PR #112 (Attn epilogue) vs merged #94 (Attn score): NO CONFLICT**

- Merged #94 changed score computation: replaced `4× scalar FMA + simd_sum` with `simd_sum(dot(float4,float4))` at L1550/2013/2077 (sliding v1→v2, full v1→v2). It hoisted `pq0`/`pq1` float4 vectors before the loop. Score computation is in the attention main loop (L1526–1600 sliding, L1990–2060 full).
- #112 changes the epilogue: the 2-pass / 3-barrier reduction at L1608–1680 (sliding) and L2105–2175 (full). This is the cross-simdgroup final softmax reduction and output write.
- **These are in completely different code regions of the same kernel.** Score loop ≈100 lines before epilogue. No textual or semantic overlap. Both changes are in the same kernel source string, so both must be applied to the same `v2` baseline. Since #94 already bumped `v1→v2`, #112 should start from the `v2` kernel (current frontier includes #94).

**3. PR #109 (shared SwiGLU epilogue) vs #114 (QKV body): NO CONFLICT**

- #109 modifies `simd_sum(gate_result)` and `simd_sum(up_result)` at L6607–6608 in `lagunaSharedSwiGLUQMVRows1Kernel`. #114 modifies the INT8 qmv inner loop at L4764–4772 in `lagunaNormAffineQKVBody`. Completely different functions, different dispatches (#7 vs #1).

**4. Merged #107 (qdot dot4) interaction with in-flight experiments:**

- #107 changed `packedWordBody()` inside `lagunaSharedSwiGLUQMVHeader` (L6395–6418). This header is used by ALL NVFP4 kernels that call `laguna_nvfp4_qdot_16` / `laguna_nvfp4_qdot_codes_16`:
  - Shared SwiGLU QMV kernels (L6483, L6535) — dispatches #7
  - Down+residual kernel (L7615) — dispatch #8
  - Routed SwiGLU kernels (L7138, L7245) — dispatch #7 variant
- **#107 does NOT affect:**
  - O-proj NVFP4 kernel (L4090–4244) — has its OWN inline qdot accumulation (`firstAccum` / `accum +=`), does NOT use `laguna_nvfp4_qdot_16`. #100 and #109's O-proj changes are independent of #107.
  - QKV kernel (L4681–4790) — INT8 affine, not NVFP4. #114 is independent of #107.
  - Attention kernels — BF16, not NVFP4. #112 is independent of #107.
- **#107 DOES affect #109's SwiGLU and Down+Residual epilogues indirectly**: #107 made the qdot body faster (62.5% instruction reduction), #109 makes the epilogue simd_sum faster. These compose multiplicatively in instruction reduction but operate on different phases of the same kernel (accumulation vs reduction). No conflict; they compound.

---

## 2. Recommended Merge Order

**Principle**: Merge bit-exact changes first (lowest verification cost), then non-bit-exact changes individually (each needs upstream equivalence test). Merge same-function changes in dependency order. Test composition at each step.

### Phase 1: Bit-exact, zero-risk (merge first, compound freely)

**Step 1: PR #109 (Askeladd) — simd_sum vectorization sweep**
- **Why first**: ZERO risk (bit-exact, same sum, fewer shuffles). All 3 target sections are independent. Merges cleanly onto current frontier (16f1dc5). No upstream equivalence needed — bit-exactness is provable.
- **Rebase**: The O-proj epilogue (L4237–4242) may shift if #100 merges first. Merge #109's O-proj epilogue change first to avoid that.
- **Verification**: Full test suite (456 tests) + upstream equivalence (should be exact since bit-exact). One M5 measurement.
- **Expected**: 0.2–1.0% decode. On instruction-bound M5, the 75% shuffle reduction should land in the upper range.

**Step 2: PR #100 (Edward) — O-proj depth-1 prefetch**
- **Why second**: LOW risk (bit-exact). Same function as #109's O-proj epilogue, but different section (body vs epilogue). Merge after #109 so the epilogue is already packed; #100's body prefetch then composes with the faster epilogue.
- **Rebase**: After #109's O-proj epilogue change, #100's body change targets L4190–4235 which is unchanged by #109. Clean rebase expected.
- **Verification**: Bit-exact (same computation, prefetch is a latency-hiding scheduling change). Full test + upstream equivalence. One M5 measurement.
- **Expected**: 0.3–1.5% decode. M5 instruction-bound, so prefetch that hides memory latency behind compute should help IF the kernel has spare ALU cycles to overlap. Note: prior #93 (down+residual prefetch) was NEGATIVE on M4 (bandwidth-bound), but O-proj has different geometry and M5 is instruction-bound. M4 null does not refute M5.

### Phase 2: Non-bit-exact, medium-risk (merge individually, test each)

**Step 3: PR #114 (Alphonse) — INT8 QKV dot4 vectorization**
- **Why third**: MEDIUM risk (not bit-exact — dot() may have different summation order). Independent code section (QKV kernel, dispatch #1). Composes with #109 and #100 (different kernels entirely).
- **Rebase**: Clean — QKV kernel (L4681–4790) is untouched by any other in-flight PR.
- **Verification**: MUST run upstream equivalence test (`research/run_upstream_equivalence.sh`). The dot(float4,float4) + simd_sum replaces 8 scalar FMA → 2 dot + 1 add. If summation order differs, logits may change. Upstream equivalence is the gate.
- **Expected**: 0.3–0.5% decode. Modest because QKV is already INT8 (fewer instructions than NVFP4). On M5 instruction-bound, still meaningful.

**Step 4: PR #112 (Thorfinn) — Attention epilogue 1-pass merge**
- **Why last**: MEDIUM risk (bfloat16 exchange may introduce tiny numerical differences). Highest complexity change (restructuring barrier synchronization). Most likely to need iteration. Merge last so if it fails equivalence, the other 3 are already banked.
- **Rebase**: Attention epilogue (L1608–1680 sliding, L2105–2175 full) is untouched by #109, #100, #114. Clean rebase. BUT: the kernel name is already `v2` (from merged #94). #112 should start from `v2` and may bump to `v3`.
- **Verification**: MUST run upstream equivalence test. The bfloat16 cross-simdgroup exchange replaces a float32 exchange in the 2-pass reduction. If the 3→1 barrier merge introduces rounding, decode logits may drift.
- **Expected**: 0.3–0.6% decode. 40 layers × 1 barrier saved per decode step. Barrier overhead on instruction-bound M5 is small but nonzero.

### Summary Merge Order

```
Frontier (16f1dc5, includes #107 + #94 + #98)
  → #109 (bit-exact, 3 sections, ZERO risk)     [Phase 1]
    → #100 (bit-exact, O-proj body, LOW risk)   [Phase 1]
      → #114 (not bit-exact, QKV, MED risk)     [Phase 2]
        → #112 (not bit-exact, attn epi, MED)   [Phase 2]
```

Each step: rebase → full test (456) → upstream equivalence (for #114, #112) → local-iterate timing → M5 submission.

---

## 3. Composition Risk Assessment

### 3a. Instruction Reduction Floor (bandwidth-bound transition)

**Current state**: M5 is instruction-bound at ~89% capacity. The instruction reductions from #107 (already merged, 62.5% in qdot body) + #109 (75% shuffle reduction) + #114 (62.5% in QKV) + #112 (barrier elimination) cumulatively reduce instruction count across multiple dispatches.

**Risk**: LOW-MEDIUM. Each experiment targets a DIFFERENT dispatch (#1, #2, #3, #7, #8). The instruction reductions don't stack on a single kernel — they're spread across the 8+ dispatches per decode step. Even if one dispatch becomes bandwidth-bound, the others remain instruction-bound. The decode step is bottlenecked by the SLOWEST dispatch, so reducing instructions on a non-bottleneck dispatch has diminishing returns but doesn't cause harm.

**Quantitative estimate**: If the bottleneck dispatch is O-proj (largest weight read: 1.2 GB across 40 layers), then:
- #100 (prefetch) hides memory latency → could shift O-proj from bandwidth-bound toward compute-bound
- #109 (O-proj epilogue packing) reduces epilogue instructions → frees ALU for prefetch overlap
- If O-proj becomes fully compute-bound, further instruction reduction (#109) helps; if it becomes bandwidth-bound, #109's gain shrinks but #100's prefetch becomes the binding constraint

**Conclusion**: No single composition will flip the M5 from instruction-bound to bandwidth-bound globally. Individual dispatches may shift, but that's expected and informative, not harmful.

### 3b. Register Pressure Accumulation

**Current state**: Each kernel has a fixed register budget. Prior experiments (#96, #89) showed register pressure regressions on shared SwiGLU and down+residual kernels.

**Risk analysis per experiment:**
- **#109 (simd_sum packing)**: REDUCES register pressure — fewer intermediate scalars, packed vec4 operations. This is a register pressure improvement, not a risk.
- **#100 (O-proj prefetch)**: MEDIUM risk — depth-1 prefetch requires holding an extra block of weight/scale data in registers. The O-proj kernel currently has `thread float x_thread[16]` and `thread float result[4]`. Adding prefetched weight data could push register usage. BUT: the kernel has `results_per_simdgroup = 4` and `num_simdgroups = 2` with `values_per_thread = 16` — moderate occupancy. The prefetch only needs 8 bytes (one code word) + 1 byte (scale) per lane. LOW-MEDIUM risk.
- **#114 (QKV dot4)**: LOW risk — replaces 8 scalar accumulations with 2 dot products. dot(float4,float4) uses the same register footprint as 4 scalars but computes 2 at once. Net register pressure: NEUTRAL or slightly reduced.
- **#112 (attn epilogue merge)**: LOW-MEDIUM risk — merging 2 passes into 1 means the 1-pass version must hold both the partial sums AND the final reduction state simultaneously. The bfloat16 exchange buffer is in threadgroup memory, not registers. The merged pass needs the same `pair_o0/pair_o1` arrays plus the reduction temporaries. If the 2-pass version freed registers between passes, the 1-pass version holds more simultaneously. MEDIUM risk on register pressure, but the attention kernel already runs with only 128 active threads (4 simdgroups) — low occupancy means high per-thread register budget.

**Cross-experiment accumulation**: #109 reduces pressure, #114 is neutral, #100 adds modest pressure, #112 adds modest pressure. Since they're on DIFFERENT kernels, register pressure does not accumulate across experiments. Each kernel's register budget is independent.

### 3c. Thermal Profile

**Current state**: The benchmark runs behind a 40C thermal gate. Candidate and baseline run back to back. Thermal throttling would affect both equally (same-session paired measurement).

**Risk**: LOW. Instruction-reduction changes (#109, #114, #112) reduce ALU work, which REDUCES heat generation. Prefetch (#100) may increase memory subsystem activity but the weight is already read regardless — prefetch only changes WHEN it's read, not how much. No experiment increases total memory traffic or sustained compute intensity.

The thermal gate measures the FULL decode pass (128 one-token steps). The instruction reductions are per-step and uniform across steps, so there's no thermal spike pattern change. The paired measurement design already controls for thermal drift.

**Conclusion**: No thermal risk from any composition.

---

## 4. Submission Strategy

### Recommendation: SUBMIT INDIVIDUALLY FIRST, THEN COMPOSE

**Rationale:**

1. **The gap is 0.25% (2.5459 → 2.5523).** Any single experiment landing at the upper end of its expected range could close it:
   - #109: 0.2–1.0% → upper range closes gap
   - #100: 0.3–1.5% → likely closes gap
   - #114: 0.3–0.5% → borderline
   - #112: 0.3–0.6% → borderline

2. **Individual submission gives clean M5 attribution.** Each experiment gets its own paired M5 measurement. We learn exactly which change moved the needle. This is critical for:
   - Identifying which mechanism transfers from M4 (bandwidth-bound) to M5 (instruction-bound)
   - Building the next wave of experiments on the confirmed winner
   - Avoiding the AGENTS.md warning: "Combining several unmeasured mechanisms before any one wins end to end"

3. **If no single experiment closes the gap, compose 2+.** The merge order above (Phase 1 first) gives the natural composition: #109 + #100 (both bit-exact, both O-proj-adjacent, ZERO+LOW risk). This composed submission would compound 0.5–2.5% expected decode, almost certainly closing the 0.25% gap.

4. **Do NOT compose all 4 at once.** If a composed submission fails correctness (e.g., #112's bfloat16 exchange drifts), we can't attribute the failure. Submit #109 + #100 composed (both bit-exact, guaranteed correct), then add #114 and #112 individually on top.

### Submission Sequence

| Step | What | M5 measurement | Risk | Expected decode gain |
|------|------|---------------|------|---------------------|
| 1 | #109 alone | Individual | ZERO | 0.2–1.0% |
| 2 | #100 alone | Individual | LOW | 0.3–1.5% |
| 3 | #109 + #100 composed | If steps 1-2 didn't close gap | ZERO+LOW | 0.5–2.5% (compounding) |
| 4 | #114 alone | Individual | MED | 0.3–0.5% |
| 5 | #112 alone | Individual | MED | 0.3–0.6% |
| 6 | Best composition of winners | Final push | Per-experiment | Compounding |

**Critical rule**: Never submit a composition that includes a non-bit-exact change (#114 or #112) unless that change has ALREADY passed upstream equivalence individually. The composition should only combine PROVEN-correct changes.

### Byte Budget Check

- `LagunaRuntimeModel.swift`: 504,899 / 524,288 bytes (19,389 bytes headroom)
- Total editable surface: 1,920,550 / 3,000,000 bytes (1,079,450 headroom)
- Growth per submission: 262,144 bytes max
- **All 4 experiments are instruction REDUCTIONS** (fewer instructions = fewer lines). Net byte change is NEGATIVE or near-zero. No byte budget risk from any composition.

---

## 5. Summary

| Question | Answer |
|----------|--------|
| Do #100 and #109 overlap? | Same function (L4090–4244), different sections (body L4190–4235 vs epilogue L4237–4242). No executable overlap; possible textual merge conflict on rebase — resolvable. |
| Do #112 and merged #94 conflict? | No. #94 = score computation (L1550/2013), #112 = epilogue (L1608–1680/2105–2175). Different regions of same kernel. |
| Are #109 SwiGLU and #114 QKV independent? | Yes. Different functions, different dispatches (#7 vs #1). |
| Does merged #107 interact with in-flight? | #107 (qdot header) affects SwiGLU + Down+Residual kernels (used by #109's changes). It does NOT affect O-proj (own inline qdot), QKV (INT8 not NVFP4), or attention (BF16). #107 + #109 compose (faster accumulation + faster reduction). |
| Optimal merge order? | #109 → #100 → #114 → #112 (bit-exact first, same-function adjacency, risk-ascending) |
| Composition risk (instruction floor)? | LOW-MEDIUM. Different dispatches, no global flip to bandwidth-bound. |
| Composition risk (register pressure)? | LOW. #109 reduces pressure, others neutral or modest on different kernels. |
| Composition risk (thermal)? | LOW. Instruction reductions decrease heat. Paired measurement controls drift. |
| Submit individually or composed? | Individual first (clean attribution), then compose #109+#100 (bit-exact pair) if gap not closed. Never compose unproven non-bit-exact changes. |
