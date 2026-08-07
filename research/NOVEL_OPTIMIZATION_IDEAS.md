# Novel Optimization Ideas for Laguna XS 2.1 NVFP4

## Research Context

- **Best score:** 2.5817 | **Leaderboard #1:** 2.6040 | **Gap:** +0.86%
- **Score formula:** decode_speedup^0.75 × prefill_speedup^0.25
- **M5 status:** bandwidth-bound, 89% GPU utilization, 11% idle
- **LRM budget:** 523,729 / 524,288 bytes (**559 bytes headroom**)
- **Vendor files:** fp_quantized_nax.h (79,620 / 524,288), quantized.cpp (84,865 / 524,288) — ample headroom

## Bandwidth Analysis

Per-decode-step weight read estimates (theoretical minimum at 1.0× amplification):

| Component | Per Layer | × Layers | Total | % of BW |
|-----------|-----------|----------|-------|---------|
| Attention QKV+gate (INT8) | 17 MB | 40 | 680 MB | 43% |
| Attention O-proj (INT8) | 4.3 MB | 40 | 172 MB | 11% |
| Routed gate/up (NVFP4) | 8 MB | 39 | 312 MB | 20% |
| Routed down (NVFP4) | 4.5 MB | 39 | 176 MB | 11% |
| Shared gate/up (NVFP4) | 1.1 MB | 39 | 43 MB | 3% |
| Shared down (NVFP4) | 0.6 MB | 39 | 23 MB | 1% |
| Router (BF16) | 1 MB | 39 | 39 MB | 2% |
| KV cache | ~0.3 MB | 40 | 12 MB | 1% |
| **Total** | | | **~1.6 GB** | |

At ~500 GB/s effective bandwidth: ~3.2 ms/step theoretical floor.
The 11% idle gap is the optimization ceiling.

## Key Findings

1. **Decode MoE kernels are custom LRM Metal kernels** (not vendor _nax). They're embedded as Swift string literals in LagunaRuntimeModel.swift. The vendor fp_quantized_nax.h kernel is the PREFILL expert kernel only.
2. **Weight read amplification is 1.0×** for all decode paths — each weight byte is read exactly once. Cannot reduce by improving access patterns.
3. **mergedSharedActivated (LRM:10497) is dead** — declared but never assigned. The shared gate/up QMV runs as a separate dispatch every step, but it overlaps the routed QMV on the GPU (documented at LRM:8022-8037). Savings from merging are dispatch-overhead only, not compute time.
4. **XMAJOR column-tile fold was removed** from fp_quantized_nax.h kernel arms but dispatch infrastructure remains. `darkbloom_gather_xmajor_ct()` at quantized.cpp:1589 hardcodes `return 0`. The code comment explicitly says "A revival target."
5. **The 11% GPU idle** is the primary optimization target. Reducing dispatch count, sync points, or increasing parallelism are the main levers since bandwidth is already at 1.0× amplification.

---

## Ranked Optimization Ideas

### Idea 1: Fuse RMSNorm + Router GEMV into Attention O-proj Kernel
**Path:** Decode (75% weight) | **Expected:** 0.3–1.2% score | **Risk:** Medium

**Mechanism:** Currently each attention layer has 2 dispatches:
1. `lagunaGatedAffineOProj` (LRM:6338) — fused softplus gate + INT8 O-proj GEMV
2. `lagunaResidualRMSNormRouter` (LRM:10850) — fused residual add + RMSNorm + router GEMV

The O-proj kernel already reads the full attention output. Adding the residual add + RMSNorm + router GEMV to this kernel would eliminate 1 dispatch per layer × 40 layers = 40 dispatches per step. At ~1 μs dispatch overhead: 40 μs/step, ~1.6% of step time. With 75% weight: ~1.2% score.

The router GEMV weight (256×2048 BF16 = 1 MB) is small relative to the O-proj weight (2048×2048 INT8 = 4.3 MB). The norm weight (2048 BF16 = 4 KB) is negligible. The residual input x (2048 BF16 = 4 KB) is already available as a layer input.

**Bit-exactness:** The RMSNorm reduction (sum of squares) must be computed in the same order as the existing `lagunaResidualRMSNormRouter` kernel. The existing kernel uses a per-thread partial sum + `simd_sum` reduction — this can be replicated exactly. The router GEMV is a simple matrix-vector product with the same accumulation order. The softplus gate in the O-proj is unaffected. **Bit-exact if the reduction order is preserved.**

**Budget impact:**
- Remove `lagunaResidualRMSNormRouter` kernel source + dispatch function: ~150 lines saved (~6 KB)
- Add norm + residual + router logic to `lagunaGatedAffineOProj` kernel source: ~100 lines added (~4 KB)
- **Net: ~2 KB byte-negative in LRM.** Frees budget for other ideas.
- 0 bytes in vendor files.

**M4 testability:** YES — custom LRM kernels run on M4. Run upstream equivalence check.

**Implementation sketch:**
1. In the O-proj kernel source, after computing the output projection, add:
   - Read residual input `x` from a new kernel input
   - Compute `residual = x + o_proj_output` (elementwise add, same order as existing)
   - Compute `rms = sqrt(mean(residual²) + eps)` — per-thread partial sum + simd_sum, same as existing
   - Compute `normalized = residual / rms * norm_weight`
   - Compute `router_logits = normalized @ router_weight.T` — simple dot product
2. Output both the O-proj result and the router logits + normalized hidden state
3. Remove the separate `lagunaResidualRMSNormRouter` dispatch
4. Update the layer call site (LRM:10850) to use the fused output

**Risk:** Medium. The O-proj kernel is affine INT8 with a complex gate. Adding FP32 norm and BF16 router to the same kernel requires careful register management. The kernel must produce 3 outputs (O-proj, normalized, router_logits) instead of 1. The threadgroup grid may need adjustment to cover both the 2048-wide O-proj output and the 256-wide router output.

---

### Idea 2: Merge Shared Expert Gate/Up QMV into Routed Dispatch
**Path:** Decode (75% weight) | **Expected:** 0.2–0.8% score | **Risk:** Medium

**Mechanism:** `mergedSharedActivated` (LRM:10497) is declared but never assigned, so the shared gate/up QMV (`lagunaSharedSwiGLUQMV`, LRM:7071) always runs as a separate dispatch. The comment at LRM:8022-8037 documents that the shared QMV already overlaps the routed QMV on the GPU (no intervening barrier), so the compute time is already hidden. The savings are dispatch-launch overhead only.

Eliminate 1 dispatch per MoE layer × 39 layers = 39 dispatches per step. At ~1 μs: 39 μs/step, ~1.5% of step time. With 75% weight: ~1.1% score. At ~100 ns launch overhead: 3.9 μs/step, 0.12% score — below threshold.

**Bit-exactness:** The shared expert computes the same gate/up QMV + SwiGLU. Merging into the routed kernel as a "9th expert slot" with a different weight bank is bit-exact — same arithmetic, same order.

**Budget impact:**
- Remove `lagunaSharedSwiGLUQMVKernel` source (~110 lines, ~4.5 KB)
- Remove `lagunaSharedSwiGLUQMVRows1Kernel` source (~80 lines, ~3.2 KB)
- Remove `lagunaSharedSwiGLUQMV` dispatch function (~30 lines, ~1.2 KB)
- Add shared expert handling to routed R1 kernel: ~60 lines (~2.4 KB)
- **Net: ~6.5 KB byte-negative in LRM.** Significant budget freed.
- 0 bytes in vendor files.

**M4 testability:** YES — custom LRM kernels run on M4.

**Implementation sketch:**
1. Extend `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` to accept shared expert weight/scales as additional inputs
2. Add a 9th "slot" in the grid (grid × 9/8 TGs) or add a conditional path for `expert_slot == 8` that reads from the shared weight bank
3. The shared expert has a fixed index (no gather needed), so the kernel can directly index its weight bank
4. Output the shared activation to a separate output array
5. Assign `mergedSharedActivated` at LRM:10497 with the shared output
6. `fusedSharedDownInputs` (LRM:8611) will then use the pre-computed activation instead of re-issuing the QMV

**Risk:** Medium. The routed kernel uses `expert = uint(indices[expert_slot])` for 8 slots. Adding a 9th slot with a different weight bank requires conditional weight pointer logic. The grid geometry changes (9/8 more TGs). Must ensure the shared weight bank is compatible with the routed bank layout (both NVFP4 fused gate/up, but potentially different packing).

---

### Idea 3: Revive XMAJOR Column-Tile Fold in Prefill Expert Kernel
**Path:** Prefill (25% weight) | **Expected:** 0.3–0.5% score | **Risk:** Medium-high

**Mechanism:** The `DARKBLOOM_GATHER_XMAJOR` fold was removed from fp_quantized_nax.h kernel arms, but the dispatch infrastructure (quantized.cpp:1986-1992) and JIT define injection (jit_kernels.cpp:1175-1187) remain. The comment at quantized.cpp:1590 says "A revival target."

With XMAJOR fold=2, each prefill expert threadgroup walks 2 adjacent BN=64 column tiles, loading the expert's x fragments once per k-tile and reusing them across both tiles. Grid shrinks from (N/bn=16, 256, 1) to (8, 256, 1). **x DRAM traffic halves** (each x fragment is loaded once instead of twice).

x bandwidth per prefill layer: ~64 MB → ~32 MB. Over 39 MoE layers: ~2.5 GB → ~1.25 GB. At 500 GB/s: ~2.5 ms prefill saving. With 25% weight: ~0.3–0.5% score.

**Bit-exactness:** x is read-only. The same x fragments are used for both column tiles. The MMA chain order is unchanged (k ascending, tiles in order). The store writes to disjoint output regions. **Bit-exact.**

**Budget impact:**
- Re-implement XMAJOR kernel arms in fp_quantized_nax.h: ~100–150 lines (~5 KB)
- Change `darkbloom_gather_xmajor_ct()` return value: 1 line
- 0 bytes in LRM
- fp_quantized_nax.h has ~444 KB headroom (79,620 / 524,288)

**M4 testability:** NO — M4 does not select `_nax` variants (gen < 17). Must test on M5.

**Implementation sketch:**
1. In `fp_gather_qmm_rhs_expert_nax` (fp_quantized_nax.h:1760), add a column-tile loop:
   ```metal
   #ifdef DARKBLOOM_GATHER_XMAJOR
   for (int xtile = 0; xtile < DARKBLOOM_GATHER_XMAJOR; ++xtile) {
     y_col = xtile * BN;
     // Reuse Atile from the same k-tile (already in registers)
     // Stage Ws for this column tile
     // MMA + store
   }
   #endif
   ```
2. The Atile (x fragments) are loaded once before the column-tile loop
3. Each column tile stages its own Ws from the expert weight bank
4. The SwiGLU reglocal epilogue handles each tile's output
5. Change `darkbloom_gather_xmajor_ct()` to return 2 (or parse env var)
6. Grid dispatch already divides by xmajor_ct (quantized.cpp:1992)

**Risk:** Medium-high. The kernel arms were deleted; re-implementing requires careful handling of the column-tile loop, weight staging per tile, and the SwiGLU reglocal store per tile. The Atile register pressure must accommodate 2 tiles' worth of x fragments (though they're the same fragments, just reused). Must verify bit-exactness with upstream equivalence check on M5.

---

### Idea 4: Prefill Expert Kernel — BK=32 Tile Reduction
**Path:** Prefill (25% weight) | **Expected:** 0.1–0.3% score | **Risk:** Low-medium

**Mechanism:** Currently BK=64 (2 SK=32 iterations per k-tile). The double-buffered Ws uses `BK_padded × BN × sizeof(bfloat) = 72 × 64 × 2 = 9,216 bytes` per buffer, 18,432 bytes for double-buffer. With BK=32: Ws = `40 × 64 × 2 = 5,120 bytes` per buffer, 10,240 bytes for double-buffer. This frees ~8 KB of threadgroup memory, potentially allowing more co-resident threadgroups on the M5's 40 cores.

Trade-off: BK=32 doubles the number of k-iterations (K/32 = 64 vs 32), adding loop overhead and more barriers. But on a bandwidth-bound system, the extra barriers may overlap with memory latency, and the improved occupancy could increase throughput.

**Bit-exactness:** Same K-reduction, same accumulation order (k ascending, kk1 ascending). The MMA fragments are the same 16×32×16 tiles. **Bit-exact.**

**Budget impact:**
- 0 bytes — BK is a template parameter; change `bk=64` to `bk=32` in the dispatch call (quantized.cpp:1701)
- Requires metallib rebuild for AOT kernels (but fp_quantized_nax.h is JIT-compiled, so no rebuild needed)
- The expert_aligned guard checks `bm==64 && wm==4` but does NOT check `bk`. Guard still passes.

**M4 testability:** NO — M4 doesn't select _nax.

**Implementation sketch:**
1. In `gather_qmm_rhs_nax` (quantized.cpp:1701), change `bk = 64` to `bk = 32`
2. Verify the template instantiation handles BK=32 (SK=32, so BK/SK = 1 iteration per k-tile)
3. The `kWsElems` calculation (fp_quantized_nax.h:1816) adjusts automatically
4. Run M5 timing to measure occupancy vs loop overhead tradeoff

**Risk:** Low-medium. Pure parameter change. If BK=32 is slower, revert. The main risk is that more barriers (64 vs 32) add overhead that exceeds the occupancy benefit.

---

### Idea 5: Decode asyncEval Ladder Tuning
**Path:** Decode (75% weight) | **Expected:** 0.1–0.3% score | **Risk:** Low

**Mechanism:** The decode asyncEval ladder (LRM:683) fires `asyncEval(h)` after layers 0, 1, 7, 15, 23, 31, 39 (default `DARKBLOOM_DECODE_ASYNC_STAGE=at:0,1,7,15,23,31,39`). Each asyncEval creates a sync point that forces partial graph materialization. The layer-0 firing (LRM:6008: `asyncEval(qkv, gateLogits)`) is early and may add an unnecessary barrier.

Experiment with:
- `at:1,7,15,23,31,39` (remove layer 0 — the layer-0 asyncEval fires before any overlap is possible)
- `at:7,15,23,31,39` (remove layers 0-1 — fewer early barriers)
- `ladder4` (fire every 4 layers — denser, more materialization)

**Bit-exactness:** asyncEval only affects scheduling/execution order, not computation. **Bit-exact.**

**Budget impact:** 0 bytes — env var configuration only.

**M4 testability:** YES — asyncEval behavior is the same on M4. However, M4 has different core count (10 cores vs 40), so the optimal ladder may differ. Directional evidence only.

**Risk:** Low. Pure env var tuning. Can be A/B tested without code changes.

---

### Idea 6: Prefill Expert Kernel — Scale Fetch Coalescing
**Path:** Prefill (25% weight) | **Expected:** <0.1% score | **Risk:** Low

**Mechanism:** In `QuantizedBlockLoader::load_unsafe_wide` (fp_quantized_nax.h:482-484) and `commit` (fp_quantized_nax.h:588-590), the scale is recomputed via `fp4nv_scale_x16384(read_scale(k0 / n_reads_per_scale))` per chunk. When `kWideChunks > 1` and multiple chunks share the same scale group (same `k0 / n_reads_per_scale`), the same scale byte is read and converted redundantly.

For the expert geometry (n_reads_per_scale=8, kSrcBytesPerChunk=4): `kWideChunks = kElemsPerThread / kWideElems`. If kWideChunks > 1, hoist the scale read + conversion outside the chunk loop when consecutive chunks share a scale group.

**Bit-exactness:** The scale value is identical whether read once or multiple times. **Bit-exact.**

**Budget impact:** ~5 lines in fp_quantized_nax.h. Negligible.

**M4 testability:** NO — _nax kernel only.

**Risk:** Low. Micro-optimization, small but free.

---

### Idea 7: Expert Weight Layout — Block Interleaving for L2 Cache
**Path:** Prefill (25% weight) + Decode (75% weight) | **Expected:** Unknown | **Risk:** High

**Mechanism:** Expert weights are stored as `[256, rows, k/8]` U32 — each expert's weight block is contiguous. For the decode gather QMV (8 experts) and prefill gather GEMM, the 8 selected experts' weight blocks are at non-contiguous memory locations (potentially 256×1 MB apart). This causes L2 cache thrashing if the 8 expert blocks don't fit in L2 cache simultaneously.

The M5's L2 cache is likely 8-16 MB. With 8 expert gate/up weights at ~1 MB each (8 MB total), they might fit. But combined with scales and down weights, the working set could exceed L2.

Proposed: Interleave expert weights in groups of 8 (experts 0-7 share contiguous memory, then 8-15, etc.). If the top-8 routing has locality (similar tokens select similar experts), the 8 selected experts are more likely to be in the same interleaved group, improving L2 cache hit rate.

**Bit-exactness:** The weight bytes are the same, just reordered. The kernel adjusts its gather index accordingly. **Bit-exact if the index computation is correct.**

**Budget impact:**
- Transform: In-place byte reorder (no new tensors needed). Must preserve name/dtype/shape — feasible since it's a within-tensor byte permutation.
- Kernel: Change `expert_weight = fused_weight + expert * fused_expert_bytes` to use the interleaved layout.
- LRM: ~10 lines for index computation. Needs budget.
- Transform: ~20 lines in MLXFastTransform.

**M4 testability:** YES for decode (custom LRM kernel). Partially testable.

**Risk:** High. The L2 cache benefit is speculative — depends on routing locality. If routing is random across all 256 experts, interleaving doesn't help. Hard to validate without M5 profiling.

---

## Summary Ranking

| Rank | Idea | Path | Expected | Bit-exact | LRM Budget | M4 Test | Risk |
|------|------|------|----------|-----------|------------|---------|------|
| 1 | Fuse norm+router into O-proj | Decode 75% | 0.3–1.2% | Yes (careful) | −2 KB | Yes | Medium |
| 2 | Merge shared QMV into routed | Decode 75% | 0.2–0.8% | Yes | −6.5 KB | Yes | Medium |
| 3 | Revive XMAJOR fold | Prefill 25% | 0.3–0.5% | Yes | 0 bytes | No | Med-high |
| 4 | BK=32 tile reduction | Prefill 25% | 0.1–0.3% | Yes | 0 bytes | No | Low-med |
| 5 | asyncEval ladder tuning | Decode 75% | 0.1–0.3% | Yes | 0 bytes | Yes | Low |
| 6 | Scale fetch coalescing | Prefill 25% | <0.1% | Yes | 0 bytes | No | Low |
| 7 | Expert weight interleaving | Both | Unknown | Yes (careful) | ~10 bytes | Partial | High |

## Recommended Strategy

1. **Start with Ideas 1+2 together** (both byte-negative in LRM, both decode 75% weight, both M4-testable). Together they could contribute 0.5–2.0% score and free ~8.5 KB of LRM budget for future ideas.

2. **In parallel, test Idea 5** (asyncEval tuning, 0 bytes, env var only) — quick A/B test.

3. **Then implement Idea 3** (XMAJOR fold) for prefill. This is the highest prefill-only impact and requires M5 testing.

4. **Idea 4** (BK=32) is a quick constant-change experiment if Idea 3 doesn't close the gap.

5. Ideas 6-7 are speculative or micro — pursue only if the gap remains.

**Combined potential:** Ideas 1+2+3+5 together could yield 0.5–2.5% score improvement, potentially closing the 0.86% gap.
