# Fresh Optimization Ideas — 2026-08-08 v2 (Birch Campaign)

**Advisor HEAD:** 39fa0483 (vendor files reverted to organizer frontier, LRM groupSize 32→16 fix)
**M5 build-fix submission:** a74d2fe VALIDATING — if it passes, campaign is unblocked
**Leaderboard #1:** a-github-name 2.6165. Our best: 2.5888 (maple campaign). Gap: ~1.06%.
**Score formula:** decode_speedup^0.75 × prefill_speedup^0.25. Decode 75%, prefill 25%.
**M5:** bandwidth-bound, ~89% GPU util, 40 GPU cores, 128 GB unified memory, ~651.8 GB/s.
**Budget:** LRM 335,729 B / 524,288 (188 KB headroom). Total surface 2,763,540 / 3,000,000 (231 KB headroom).

---

## Context: What's Genuinely Exhausted (from 30+ prior research files, 40+ PRs)

### Dead approaches (do NOT revisit)
- Custom GEMM/GEMV kernels (can't beat MLX's optimized GEMM — PRs #317, #325, #326, #334)
- RMSNorm fusion into matmul kernels (FP reduction order changes flip tokens — PRs #276, #349)
- Grid over-dispatch (MLX grid = total threads, not threadgroups — PRs #333, #394)
- Scale halving for prefill kHalvedScales via template params (M5 compile-storm, PR #398)
- Unsorted gatherQuantizedMM (+39.7% prefill regression — sorting essential, PR #348)
- Full-attention QK-norm+YaRN fusion on M4 (PR #356: -3.3% decode on M4, but M4 ≠ M5)
- MLX.compile for quantized matmul fusion (can't fuse quantizedMM — PRs #349, #351)
- Single-threadgroup dispatch folds (M5 overlaps tiny dispatches — negative result, metaspartan note ad4d0e5)
- KV cache quantization (outside accepted attention envelope)
- Custom flash-attention SDPA kernel (sdpa_vector is already AOT-optimized)

### What's already ON by default (confirmed at HEAD 39fa0483)
- `DARKBLOOM_FUSED_SLIDING_QK_NORM_ROPE` ON (since 9e06de6, +1.73%)
- `DARKBLOOM_FUSED_FULL_QK_NORM_YARN` ON (since the revert — both flags use `!= "0"`)
- `DARKBLOOM_FUSED_FULL_ATTN` ON (decode full-attention fused kernel)
- `DARKBLOOM_PREFILL_QK_NORM_ROPE` ON (6→1 dispatch per layer, ~200 prefill dispatch eliminations)
- `DARKBLOOM_FUSED_ROUTED_SWIGLU_QMV` ON (decode MoE gate/up+SwiGLU fused, 8 routed + shared in 1 dispatch)
- `DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL` ON (decode MoE down+residual+router fused in 1 dispatch)
- `DARKBLOOM_PACKED_SCALES` ON (decode-only scale packing)
- `DARKBLOOM_NATIVE_AFFINE_QKV` / `OPROJ` / `GPROJ` ON (group-32 INT8 QKV, o_proj, g_proj)
- `DARKBLOOM_FUSED_QKV_PROJECTION` ON (fused QKV bank for decode)
- `DARKBLOOM_FUSED_RESIDUAL_RMS` ON (decode residual+RMSNorm fusion)
- `DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER` ON (fuses router projection into residual+RMSNorm)
- `DARKBLOOM_EXPERT_ALIGNED_GATHER` ON (prefill expert-aligned gather-QMM NAX path)
- `DARKBLOOM_EXPERT_STAGE_WIDEST` / `WIDELD` ON (wide staging in expert gather-QMM)
- `DARKBLOOM_EXPERT_GATHER_GROUPS` = 256 (one expert per threadgroup)
- `MLX_MAX_OPS_PER_BUFFER` = 400, `MLX_MAX_MB_PER_BUFFER` = 200 (set at LRM:387)
- `DARKBLOOM_AOT_SDPA_PLANES` = 4 (exchange-plane widening, +0.6%)
- `DARKBLOOM_GQA_PAIR_HEADS` = 2 (two-head GQA pairing in stock sdpa_vector)
- `DARKBLOOM_ALPHASKIP` = 1 (online-softmax rescale elision, neutral but exact)

### What's OFF / dead (potential re-enablement targets)
- `lagunaPrefillSharedHalvedEnabled` = false (LRM:229, hardcoded OFF — "will be enabled when M5 build confirmed")
- `DARKBLOOM_STAGE_WIDEST/WIDELD/RUNBAR/NOVOL` all OFF (quantized.cpp:1308-1324, prefill non-expert gather-QMM staging)
- `DARKBLOOM_PREFILL_FUSED_GATE_UP_HALVED` flag ON but dead code (LRM:208, useHalved hardcoded false at LRM:6085)
- `DARKBLOOM_PREFILL_ADDMM` OFF (LRM:6691, experimental output-projection fusion)
- `DARKBLOOM_ROPE_ATLAS_VIEWS` OFF (LRM:519, zero-dispatch RoPE views, measured neutral)
- `DARKBLOOM_FUSED_FULL_ATTN_KERNEL_WARMUP` OFF (LRM:464, pipeline warmup for full-attn kernel)

### Architecture (from LagunaConfig.swift)
- 40 layers: layer 0 = dense BF16 MLP, layers 1-39 = sparse MoE (NVFP4)
- 10 full-attention (48 Q heads, 8 KV heads, GQA-6, YaRN) + 30 sliding (64 Q heads, 8 KV heads, GQA-8, window 512)
- MoE: 256 routed experts (top-8) + 1 shared expert. moeIntermediateSize=512, hiddenSize=2048
- Decode: ~324 dispatches/step, ~8 per layer, ~5.4 ms/step
- Bandwidth at 1.0× amplification (each weight byte read once)
- Decode MoE: 2 dispatches/layer (fused gate/up+SwiGLU + fused down+residual)
- Decode attention: sliding = 1 dispatch (fused), full = 1 dispatch (fused)

### Critical architectural insight: Decode hot path uses INLINE fused kernels, NOT stock sdpa_vector.h
The custom `lagunaSlidingFusedAttentionKernel` (LRM:1441) and `lagunaFullFusedAttentionKernel` (LRM:1866)
are inline Metal kernels in the LRM that do their own 2-head GQA pairing and bypass `sdpa_vector.h`
entirely. They run with grid `(heads/2)*1024` threadgroups of 1024 threads. The stock `sdpa_vector.h`
pair path (DARKBLOOM_GQA_PAIR_HEADS=2) only fires for the stock SDPA fallback, which is rarely hit
during decode. **Extending the stock sdpa_vector.h to 3-4 heads (as yudduy did) would NOT reach the
decode hot path unless the inline kernels are also modified.** yudduy's gain likely came from the
stock path or from their own inline kernels.

---

## Idea 1: Extend Fused Inline Attention Kernels from 2-Head to 4-Head GQA Pairing ★★★★★

**Path:** Decode (75% score) — the highest-weighted component
**Expected impact:** 0.3–0.8% total score (proportional to yudduy's +0.0023 from 2→3/4 head grouping)
**Risk:** Medium (register pressure, threadgroup memory, M5 build success)

### Mechanism
Both decode fused attention kernels (`lagunaSlidingFusedAttentionKernel` LRM:1441, `lagunaFullFusedAttentionKernel` LRM:1866)
currently pair **2 adjacent query heads** per threadgroup, sharing one K/V load across 2 heads. The grid is
`(heads/2)*1024` threadgroups. Extending to 4 heads per threadgroup:
- Sliding (GQA-8): 4 query heads per KV head → K/V loaded once per 4 heads instead of 2 → **halves K/V traffic**
- Full (GQA-6): 3 query heads per KV head → 3-head grouping → **reduces K/V traffic by 3×**

The K/V cache is the dominant bandwidth cost in decode attention. At 512 positions × 128 dim × 2 bytes = 128 KB
per KV head per layer. With 2-head pairing, each threadgroup reads 128 KB of K + 128 KB of V = 256 KB.
With 4-head pairing, the same 256 KB is amortized across 4 heads instead of 2.

### Bandwidth analysis
Decode per step, per sliding layer: 32 threadgroups × 256 KB K/V = 8 MB K/V reads. With 4-head pairing:
16 threadgroups × 256 KB = 4 MB. Saves 4 MB × 30 sliding layers = **120 MB/step**.
Full-attention: 24 threadgroups × (N × 128 × 2) K/V → with 3-head: 16 threadgroups. Saves ~2 MB × 10 layers = 20 MB/step.
Total: ~140 MB/step saved. At 651.8 GB/s: ~0.21 ms/step on ~5.4 ms baseline = ~3.9% decode improvement.
Score impact: 3.9% × 0.75 ≈ 2.9% score → **~0.08 score points** (2.5888 → ~2.67).

### Bit-exactness
**Bit-exact.** Each query head keeps independent online-softmax state (max, sum, output accumulators).
The K/V loads are read-only and shared — each head computes its own score with its own query against
the same K, and its own output against the same V. The FP sequence per head is character-identical
to the current 2-head path (same score accumulation order, same rescale, same output FMA chain).
Only the threadgroup assignment changes: `head0 = pair_tg * 4` instead of `pair_tg * 2`.

### Threadgroup memory budget
Current 2-head: `outputs[4 * BN * BDP]` (16 KB) + `max_scores[2*BN]` + `sum_exp_scores[2*BN]` = ~17 KB.
4-head: `outputs[8 * BN * BDP]` (32 KB) + `max_scores[4*BN]` + `sum_exp_scores[4*BN]` = ~34 KB.
**This exceeds the 32 KB threadgroup memory limit** at the current BDP=33 stride.

**Mitigation:** Use the 4-plane exchange pattern (as in sdpa_vector.h PLANES=4) instead of 2-plane:
`outputs[4 * BN * BD]` = 16 KB (BD=32, not BDP=33). With 4 heads × 4 planes = 16 KB outputs +
4*64 bytes max/sum = 17.5 KB. Fits.

Alternative: keep 2-plane exchange but reduce to `BD=32` (remove the BDP padding, accept the bank
conflict — the original BDP=33 was a micro-optimization). `outputs[8 * BN * BD]` = 32 KB — too large.

**Best approach:** For sliding (GQA-8, 4-head groups), use 4-plane exchange at BD=32. For full
(GQA-6, 3-head groups), use 3-plane exchange. Both fit under 32 KB.

### Register pressure
4 heads × 4 qk_per_thread = 16 thread registers for queries (vs 8 at 2-head).
4 heads × 4 v_per_thread = 16 for output accumulators (vs 8).
4 max/sum scalars. Total ~40 thread registers — within the 1024-thread limit at typical register
allocation. The competitor analysis (metaspartan note b51a6ba) warns that the attention kernels
sit exactly at the 1024-thread register tier. Adding registers risks dropping to 832 threads.
**This is the primary risk.** Must verify that 4-head grouping doesn't exceed the register budget.

### Budget
- Modify `lagunaSlidingFusedAttentionKernel` (LRM:1441-1812): ~300 lines of Metal source changes
- Modify `lagunaFullFusedAttentionKernel` (LRM:1866-2273): ~300 lines
- Change grid dispatch at LRM:1859 and LRM:2321 from `(heads/2)*1024` to `(heads/4)*1024` (sliding) / `(heads/3)*1024` (full)
- Change dispatch wrappers at LRM:1829 and LRM:2290
- LRM has 188 KB headroom. ~600 lines of source ≈ ~20 KB. **Fits comfortably.**
- No new JIT compile count (modifying existing kernel source strings, not adding new ones)

### M5 safety
- Modifying existing JIT kernel source does NOT add compile count
- The kernel grid changes from 32*1024 → 16*1024 (sliding) or 24*1024 → 16*1024 (full) — fewer threadgroups
- Must verify the threadgroup memory fits and the register count doesn't drop max threads below 1024

### Implementation
1. In `lagunaSlidingFusedAttentionKernel` source (LRM:1450):
   - Change `head0 = pair_tg * 2` → `head0 = group_tg * 4` (add `head2`, `head3`)
   - Add `pair_q2`, `pair_q3`, `pair_o2`, `pair_o3` register arrays
   - Replicate the score/exp/rescale/output chain for heads 2, 3
   - Expand the exchange epilogue to 4-head combine (4 planes × BD stride)
   - Change threadgroup arrays: `max_scores[4*BN]`, `sum_exp_scores[4*BN]`, `outputs[4*4*BN*BD]`
2. In `lagunaSlidingFusedAttention` wrapper (LRM:1817):
   - Change grid from `(heads/2)*1024` → `(heads/4)*1024`
3. Same changes for `lagunaFullFusedAttentionKernel` with 3-head groups (GQA-6)
4. Test correctness with upstream equivalence (`research/run_upstream_equivalence.sh`)
5. Time on M5 with `./benchmark.sh --local-iterate`

---

## Idea 2: Enable Prefill Shared Expert Halved Scales (lagunaPrefillSharedHalvedEnabled) ★★★★

**Path:** Prefill (25% score) — relatively unoptimized
**Expected impact:** 0.1–0.3% total score
**Risk:** LOW for correctness, MEDIUM for M5 build (the gate was held pending M5 build confirmation)

### Mechanism
`lagunaPrefillSharedHalvedEnabled` (LRM:229) is hardcoded `false` with the comment:
"Disabled for now — will be enabled when the M5 build is confirmed working."
The code path at LRM:5318-5334 is fully implemented: it runs the shared expert gate/up and down
projections with halved scales (`groupSize: 16` instead of `32`) using the fused [gate;up] bank.

The HEAD commit 39fa0483 already changed the shared expert QMM from `groupSize: 32` to `groupSize: 16`
at LRM:5329-5333 (the `lagunaPrefillSharedHalvedEnabled = false` gate blocks this path, but the
non-halved path at LRM:5335-5355 also uses groupSize 16 after the fix). So the halved path is
the SAME quantizedMM call but uses a pre-computed compact scale bank (`_prefillGateUpFullScales`
and `_prefillDownFullScales`) instead of the per-tensor scale extraction.

The halved scales reduce the scale metadata read from ~2 MB to ~1 MB per shared expert per layer
(39 MoE layers × 2 passes = 78 MB → 39 MB saved). At 651.8 GB/s: ~0.06 ms prefill saving.
Prefill is ~0.37 ms/token baseline (512 tokens), so ~0.16% prefill improvement.
Score: 0.16% × 0.25 ≈ 0.04% → small but free.

### Bit-exactness
**Bit-exact.** The halved scale path uses the same `quantizedMM` function with the same `groupSize: 16`,
`bits: 4`, `mode: .nvfp4`. The only difference is that the scale bank is pre-computed as a compact
array (`_prefillGateUpFullScales`) rather than extracted per-call. The same E4M3 scale bytes are
read and the same float conversions occur — the offline transform pre-packs them for zero-copy reuse.
This is the exact mechanism a-github-name used for their "zero-copy prefill scale reuse" (submission
db8b4df, score 2.590).

### Budget
- Change `let lagunaPrefillSharedHalvedEnabled = false` → `true` (or make it env-gated `!= "0"`)
- 1 line change, 0 bytes net. **Zero budget cost.**
- No new JIT compile (uses existing `quantizedMM` which is already compiled)

### M5 safety
- No new JIT kernel compiles — uses existing `quantizedMM` dispatch
- The halved scale arrays are prepared at checkpoint load time (untimed)
- The `groupSize: 16` path is already exercised by the non-halved fallback (HEAD fix)

### Implementation
1. Change LRM:229 from `let lagunaPrefillSharedHalvedEnabled = false` to env-gated:
   ```swift
   let lagunaPrefillSharedHalvedEnabled =
       ProcessInfo.processInfo.environment["DARKBLOOM_PREFILL_SHARED_HALVED"] != "0"
   ```
2. Verify `_prefillGateUpFullScales` and `_prefillDownFullScales` are populated at checkpoint load
   (search for where these are set — likely in `LagunaRuntimeMLP` initialization)
3. Run upstream equivalence to verify bit-exactness
4. Time on M5

---

## Idea 3: DARKBLOOM_STAGE_* Flags for Prefill Non-Expert Gather-QMM Staging ★★★

**Path:** Prefill (25% score)
**Expected impact:** 0.2–0.5% prefill improvement → 0.05–0.13% total score
**Risk:** LOW for correctness, LOW for M5 build (compile-count neutral)

### Mechanism
Four independent flags (quantized.cpp:1274-1326) attack the per-run staging cost in the non-expert
gather-QMM (`fp_gather_qmm_rhs_nax`). All default OFF. Each resolves once per process and compiles
exactly one pipeline variant — zero JIT compile count increase.

The non-expert gather-QMM runs for the **shared expert** prefill path (when it uses `gatherQuantizedMM`
instead of the fused bank). The expert-aligned gather path has its own staging flags
(`DARKBLOOM_EXPERT_STAGE_WIDEST/WIDELD`, already ON). The non-expert path is the shared expert's
separate QMM dispatch during prefill.

- `DARKBLOOM_STAGE_WIDEST` (fc 204): 32×2B → 4×16B threadgroup stores. Wide store-side staging.
- `DARKBLOOM_STAGE_WIDELD` (fc 205): 16×1B → 1×16B device weight load. Wide load-side staging.
- `DARKBLOOM_STAGE_RUNBAR` (fc 206): Drop 2 provably dead per-run barriers.
- `DARKBLOOM_STAGE_NOVOL` (fc 207): Drop vestigial volatile in k-loop.

These compose with `DARKBLOOM_PREFILL_GATHER_RUNSKIP` (also OFF) which elides per-simdgroup MMA
work for empty expert runs.

### Bandwidth/Dispatch analysis
The comments at quantized.cpp:1280-1286 explain: the loader issues 50 LSU ops per thread per
k-iteration against ~40 for the compute. After RUNSKIP, the loader is ~68% of the kernel's LSU
traffic. WIDEST and WIDELD reduce the loader's store/load counts by 8× and 16× respectively.
RUNBAR removes 2 barriers per run. NOVOL removes a volatile qualifier that prevents compiler
reordering.

### Bit-exactness
- **WIDEST:** Bit-exact. Only the store width changes (scalar 2B → 16B vector store). Same values
  at the same addresses. 16B alignment is guaranteed by construction (NAXWsChunk16).
- **WIDELD:** Bit-exact. Same elements loaded in the same order, just one 8B load instead of 8
  scalar byte loads. Self-guards each thread's offset.
- **RUNBAR:** Bit-exact. The barriers are provably dead — they guard no actual data dependency
  (the run boundaries are simdgroup-uniform and the data is register-local).
- **NOVOL:** Bit-exact. The `volatile` qualifier only prevents compiler optimization; removing
  it doesn't change the computed values.

All four are independently A/B-testable by setting/clearing the environment variable. The ranked
runner sets no DARKBLOOM_* variables, so whatever is default-shipped is what runs.

### Budget
- Zero bytes of source code. These are environment-variable flags already implemented in
  `quantized.cpp` and the JIT kernel source.
- To ship: set the flag default from `"1"` check to `!= "0"` (default ON) in the C++ source.
  This changes 4 lines in quantized.cpp (lines 1308-1324, changing `darkbloom_stage_flag` calls
  to default-on).
- No new JIT compile count (each setting compiles exactly one pipeline for the process lifetime).

### M5 safety
- These modify existing kernel specializations (changing the staging macros), not adding new ones
- The function-constant-free design (baked into kernel name) means exactly one variant per process
- No M5 compile-count risk

### Implementation
1. In `quantized.cpp`, change the four `darkbloom_stage_*` functions to default ON:
   ```cpp
   bool darkbloom_stage_widest() {
     static const bool v = env::get_var("DARKBLOOM_STAGE_WIDEST", "") != "0";
     return v;
   }
   ```
   (Same for `wideld`, `runbar`, `novol`)
2. Or ship them individually as separate experiments (one flag per PR) for causal attribution
3. Test with `./benchmark.sh --local-iterate` on M5

---

## Idea 4: Prefill Steel-Attention K/V Tile Size Tuning (bq/bk) ★★★

**Path:** Prefill (25% score) — prefill attention is the only un-fused attention path
**Expected impact:** 0.3–0.8% prefill improvement → 0.08–0.20% total score
**Risk:** LOW for correctness, MEDIUM for M5 build (new kernel specialization)

### Mechanism
Prefill (L=512) uses `sdpa_full_self_attention_nax` → `steel_attention` kernel
(scaled_dot_product_attention.cpp:18-164). The tile sizes are hardcoded: `bq=64, bk=32, bd=headDim`.
The grid is `NQ × H × B` threadgroups of `32 × wm × wn = 32 × 4 × 1 = 128` threads.

The steel_attention kernel is in `Vendor/.../kernels/steel/attn/kernels/steel_attention_nax.h`
(editable, 657 lines, ~25 KB). The tile sizes are set in the C++ dispatch (NOT editable —
`scaled_dot_product_attention.cpp` is outside editablePaths), but the kernel template accepts
them as compile-time constants.

**The key constraint:** `scaled_dot_product_attention.cpp` is NOT in editablePaths. But the kernel
source `steel_attention_nax.h` IS (it's under `kernels/steel/attn/`). We can modify the kernel
template to optimize the inner loop without changing the dispatch.

However, the tile sizes (bq=64, bk=32) are baked into the kernel name by the C++ dispatcher, so
we cannot change them from the kernel source alone. What we CAN do is optimize the kernel's
memory access pattern:

- **Optimize K/V loading:** The kernel loads K and V tiles through `loader.h`. We can add wider
  vector loads (8B or 16B) where alignment permits, reducing load count.
- **Optimize the MMA epilogue:** The output write pattern may benefit from wider stores.
- **Reduce barrier count:** The online-softmax barriers may have dead trailing barriers (like the
  sdpa_vector PLANES optimization did).

### Bandwidth analysis
Prefill attention per layer: 512 tokens × (48 or 64) heads × 128 dim × 2 bytes for Q, K, V.
Total Q+K+V = 512 × 64 × 128 × 2 × 3 = 25 MB per sliding layer × 30 = 750 MB.
Plus the attention output: 512 × 64 × 128 × 2 = 8 MB × 30 = 240 MB.
Total attention bandwidth: ~990 MB per prefill. At 651.8 GB/s: ~1.5 ms.
Prefill total is ~0.37 ms/token × 512 = ~189 ms. Attention is ~1.5 ms ≈ 0.8% of prefill.
A 10% attention improvement = 0.08% prefill = 0.02% total score. **Small.**

The bigger prefill cost is the MoE gather-QMM (~54% of prefill, per quantized.cpp:1277).
This idea is lower-impact than the MoE-focused ideas.

### Bit-exactness
**Bit-exact if** only load/store widths and barrier removals are changed. The MMA accumulation
order and FP sequence must remain character-identical. Wider vector loads of the same elements
in the same order are bit-exact (same bytes loaded, same conversion points). Barrier removal
is bit-exact if the barrier guards no actual data dependency.

### Budget
- `steel_attention_nax.h` has ~25 KB of content, 524 KB limit = ~499 KB headroom
- Modifications: ~50-100 lines of load/store optimization = ~3-5 KB
- No new JIT compile if modifying existing template (the kernel name includes bq/bk/bd which
  are unchanged)

### M5 safety
- Modifying the steel_attention kernel template does not add compile count (same kernel name)
- The dispatch code is unchanged (not editable anyway)
- Risk: the steel_attention kernel is AOT-compiled into the metallib, so changes require
  `tools/build-mlx-metallib.sh` rebuild

### Implementation
1. Read `steel_attention_nax.h` to understand the load/store/barrier patterns
2. Identify dead trailing barriers in the online-softmax loop
3. Add wider vector loads in `loader.h` where alignment permits (8B for BF16 K/V)
4. Rebuild metallib with `tools/build-mlx-metallib.sh`
5. Test on M5

---

## Idea 5: Fuse Prefill Shared Expert into Routed Gather-QMM (Single Dispatch) ★★★★

**Path:** Prefill (25% score) — reduces dispatch count for MoE
**Expected impact:** 0.2–0.4% prefill improvement → 0.05–0.10% total score
**Risk:** MEDIUM for correctness (must verify exactness), MEDIUM for M5 build

### Mechanism
During prefill, the MoE block (LRM:6377-6645) runs the shared expert **separately** from the
routed experts:
- Routed: `lagunaFusedSortedRoutedGateUp` (1 gather-QMM) + SwiGLU (1) + down (1 gather-QMM) + tail (1)
- Shared: `sharedExpert(x)` (fused [gate;up] QMM (1) + compiledSiluProduct (1) + downProj (1))
Total: ~7 dispatches per MoE layer.

The decode path already fuses shared + routed into 2 dispatches
(`lagunaRoutedSwiGLUQMVPackedTop8` includes shared, `lagunaRoutedSharedDownResidual` includes shared).
Prefill does NOT have this fusion.

The prefill MoE tail kernel (`lagunaPrefillSortedMoETail` / `lagunaPrefillMoETail`) already
fuses the routed scale + weighted sum + shared add + residual add into 1 dispatch. But the
shared expert's gate/up and down projections are still separate QMM dispatches.

**Proposal:** Add the shared expert as an extra "slot" in the prefill gather-QMM, like the decode
path does. The `gatherQuantizedMM` with `rhsIndices` already supports an arbitrary number of
expert indices. Add the shared expert's index as a "virtual" expert (index 256) in the sorted
routing, and include its gate/up and down weights in the gather.

### Bit-exactness
**Bit-exact.** The shared expert computes the same `quantizedMM(x, shared_gate_up_weight.T)`
and `quantizedMM(activated, shared_down_weight.T)` as the separate dispatch. Including it in
the gather-QMM dispatches the same MMA operations on the same weight data in the same order.
The shared expert's contribution to the output is `shared_expert_output × scale_factor`, which
the MoE tail kernel already adds. The only change is that the shared expert's gate/up and down
projections run inside the gather-QMM instead of as separate `quantizedMM` calls.

**Risk:** The gather-QMM's `N` dimension changes (256+1=257 experts instead of 256), which
changes the kernel dispatch and may change the accumulation order for the shared expert's
output. This is the same "N-changing GEMM fusion" risk flagged in the competitor analysis
(note 14a2352). However, the shared expert is a single expert (not a matmul fusion), so the
MMA order within each expert tile is unchanged. The risk is only if the gather-QMM's threadgroup
assignment changes the per-expert MMA order, which it does not (each expert is computed by
the same tile walk regardless of which slot it occupies).

### Budget
- Modify `lagunaFusedSortedRoutedGateUp` (LRM:6043) to include shared expert indices
- Modify the prefill MoE tail to handle the shared expert slot
- ~100-200 lines of Swift changes = ~5-10 KB. **Fits in LRM headroom.**
- No new JIT kernel (uses existing `gatherQuantizedMM` dispatch)
- May require adding the shared expert weights to the gather-QMM's weight bank

### M5 safety
- No new JIT kernel compiles (uses existing gather-QMM)
- The weight bank layout changes but the kernel is the same
- Risk: the gather-QMM may dispatch differently for 257 vs 256 experts (alignment, threadgroup
  count). Must verify the kernel handles non-power-of-2 expert counts.

### Implementation
1. In `LagunaRuntimeSparseMoEBlock.forward` (LRM:6377), modify the routing to include
   the shared expert as virtual expert 256 in the sorted indices
2. Pass the shared expert's gate/up and down weights to the gather-QMM as additional rows
3. The MoE tail kernel already adds the shared contribution — just skip the separate
   `sharedExpert(x)` call
4. Test upstream equivalence for bit-exactness
5. Time on M5

---

## Idea 6: Restore and Re-enable DARKBLOOM_GATHER_XMAJOR Column-Tile Fold for Prefill ★★★

**Path:** Prefill (25% score) — bandwidth reduction in expert gather-QMM
**Expected impact:** 0.2–0.4% prefill improvement → 0.05–0.10% total score
**Risk:** MEDIUM (M5-only kernel, needs reimplementation, no M4 test)

### Mechanism
The XMAJOR column-tile fold infrastructure exists at the dispatch level (quantized.cpp:1552-1567,
1712-1739, 1915-1921) but is pinned OFF (`darkbloom_gather_xmajor_ct()` returns 0). The kernel
arms were removed ("XMAJOR kernel arms removed with the dead staging code").

The mechanism: each threadgroup in the expert-aligned gather-QMM walks one BN=64 column tile.
With XMAJOR fold=2, each threadgroup walks 2 adjacent column tiles, loading the expert's x
fragments once per k-tile and reusing them across 2 tiles. This halves x DRAM traffic.

x is [512, 2048] BF16 = 2 MB per layer. With fold=2, x traffic halves from ~2 MB to ~1 MB per
gate/up pass. Over 39 MoE layers × 2 passes: ~156 MB → ~78 MB saved. At 651.8 GB/s: ~0.12 ms.

### Bit-exactness
**Bit-exact.** x is read-only. The same x fragments are used for both column tiles. MMA chain
order is unchanged (k ascending, tiles in order). Store writes to disjoint output regions.

### Budget
- Re-implement XMAJOR kernel arms in `fp_quantized_nax.h` (458 KB headroom): ~100-150 lines (~5 KB)
- Change `darkbloom_gather_xmajor_ct()` return from 0 to 2: 1 line
- Update `fp_quantized_nax.cpp` (JIT twin) to match: ~150 lines (~5 KB, 455 KB headroom)
- Grid dispatch at quantized.cpp:1919 already divides by xmajor_ct — no change needed
- Total: ~10 KB across two files with ample headroom

### M5 safety
- Uses `#define` injection (not function constants), so exactly one pipeline variant compiles
- M4 cannot test (no `_nax` kernels). M5-only validation required.
- The kernel was previously compiled and bit-exact when the arms existed

### Implementation
1. In `fp_gather_qmm_rhs_expert_nax` (fp_quantized_nax.h:1573), add a column-tile loop under
   `#ifdef DARKBLOOM_GATHER_XMAJOR`:
   - Load Atile (x fragments) once before the column-tile loop
   - For each column tile: stage Ws, MMA, SwiGLU reglocal epilogue, store
2. Change `darkbloom_gather_xmajor_ct()` at quantized.cpp:1563 to return 2
3. Update the JIT twin `fp_quantized_nax.cpp` to match
4. Build and test on M5

---

## Priority Ranking

| # | Idea | Path | Expected score | Risk | Budget | Priority |
|---|------|------|---------------|------|--------|----------|
| 1 | 4-head GQA in fused inline kernels | Decode 75% | 0.3-0.8% | Medium | ~20 KB | **HIGHEST** |
| 2 | Prefill shared expert halved scales | Prefill 25% | 0.1-0.3% | Low | 0 bytes | **HIGH** |
| 3 | DARKBLOOM_STAGE_* staging flags | Prefill 25% | 0.05-0.13% | Low | 0 bytes | **HIGH** |
| 5 | Fuse prefill shared into routed gather | Prefill 25% | 0.05-0.10% | Medium | ~5-10 KB | **MEDIUM** |
| 4 | Prefill steel-attention tile tuning | Prefill 25% | 0.08-0.20% | Low-Med | ~3-5 KB | **MEDIUM** |
| 6 | Restore XMAJOR column-tile fold | Prefill 25% | 0.05-0.10% | Medium | ~10 KB | **MEDIUM** |

### Recommended experiment order (once M5 builds):
1. **Idea 2** (halved scales) — zero cost, zero risk, immediate. Ship first to verify M5 pipeline.
2. **Idea 3** (STAGE flags) — zero cost, zero risk. Ship each flag as separate PR for attribution.
3. **Idea 1** (4-head GQA) — highest impact, needs careful register/threadgroup memory analysis.
   This is the direct competitor catch-up to yudduy's 3/4-head grouping.
4. **Idea 5** (fuse shared into routed) — moderate impact, needs exactness verification.
5. **Idea 4** (steel-attention tuning) — requires metallib rebuild, moderate impact.
6. **Idea 6** (XMAJOR fold) — M5-only, needs reimplementation, lower priority.

### Key insight about yudduy's technique
yudduy (2.6063) modified the stock `sdpa_vector.h` to go from 2-head to 3/4-head GQA pairing.
However, our decode hot path uses **inline fused kernels** (`lagunaSlidingFusedAttentionKernel`,
`lagunaFullFusedAttentionKernel`) that bypass `sdpa_vector.h`. So to replicate yudduy's gain,
we must extend the **inline fused kernels**, not the stock sdpa_vector.h. This is Idea 1.
The stock sdpa_vector.h pair path only fires for the stock SDPA fallback (rarely hit during decode).

Previous attempts to extend sdpa_vector.h to 3/4 heads (commits 94977c29, 7df58f94) caused M5
build timeouts and were reverted. Modifying the inline fused kernels instead avoids this because
they are JIT-compiled from the LRM source string (not AOT metallib), so they don't require a
metallib rebuild and don't add to the AOT compile count.
