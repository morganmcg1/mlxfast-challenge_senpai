# Competitor Analysis — Top 3 Leaderboard

- **Date:** 2026-08-08 01:02 UTC
- **Our best:** 2.5888 (commit 3e165fa, promoted Aug 6 5:04 AM)
- **Leaderboard:**
  1. yudduy: 2.6063 (commit 01e247a, promoted Aug 7 5:58 PM)
  2. fyrsta7: 2.6040 (commit a13fdca, promoted Aug 7 7:22 AM)
  3. a-github-name: 2.5979 (commit ab17a99, promoted Aug 7 3:06 AM)
- **Gap to #1:** ~0.67% (2.5888 → 2.6063)

Source: `mlxfast submissions --all`, `mlxfast submission-note <id>`, `mlxfast notes search`.

---

## 1. yudduy — Score 2.6063 (submission 2054d45, commit 01e247a)

### Approach: Two-group SDPA decode attention schedule

yudduy's winning submission modifies a **single AOT Metal kernel header**:
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/sdpa_vector.h`

The promoted parent (a-github-name's db8b4df at 2.5901) already grouped adjacent
query heads in pairs to share K/V loads. yudduy extends this to **exactly two
active query groups per KV head**:

- GQA6 full-attention layers: two groups of three query heads (reduces K/V
  reads from 3x to 1x per KV head).
- GQA8 sliding-attention layers: two groups of four query heads (reduces K/V
  reads from 4x to 1x per KV head).

Key design decisions:
- **Host dispatch grid unchanged.** Only the first `2 * total_kv_heads`
  threadgroups execute; excess groups early-return before any memory access.
  This avoids editing the non-editable host dispatch code.
- **Threadgroup memory:** 25 KiB (six exchange planes + four-head max/sum),
  under the 32 KiB limit. Residency-one is preserved.
- **Compile-time restricted** to D=128, V=128, GQA factor 6 or 8, single-query
  decode (tpg.y==1). Falls through to generic path for any other shape.
- **Bit-exact:** Shares only immutable K/V loads; each query head keeps
  independent online-softmax state, registers, and output components.
- **AOT metallib rebuilt** with `tools/build-mlx-metallib.sh`.

### What this tells us
- yudduy is working on **decode attention K/V traffic reduction** — the 75%
  weighted component. The approach is incremental on a-github-name's pair
  schedule, going from 2-head groups to 3/4-head groups.
- The predicted decode improvement was ~0.14 ms/token (4.925 → 4.779 ms/token).
  Actual promotion gained +0.0023 score (2.5901 → 2.6063), confirming a real
  but modest decode win.
- **They are NOT using MLX compiled functions.** They edit raw Metal kernel
  headers directly and rebuild the AOT metallib. This is hand-tuned kernel work.

---

## 2. fyrsta7 — Score 2.6040 (submission b9ccb0b, commit a13fdca)

### Approach: Packed uint2 router shuffle in decode kernel

fyrsta7's submission is a **micro-optimization to the MoE router Top-8 selector**
inside `Sources/MLXFastModel/LagunaRuntimeModel.swift` (embedded Metal helper
`laguna_router_top8_extract_round`).

The change packs two 32-bit components (router ordinal + expert index) into a
single `uint2` and uses one vector `simd_shuffle_xor` instead of two scalar
`simd_shuffle_xor` calls per butterfly reduction step. This reduces shuffle
calls from 10 to 5 per extraction round.

Key design decisions:
- **One file changed**, one Metal helper function. No kernel name, signature,
  grid, threadgroup size, or dispatch changes.
- **Bit-exact:** Same comparator reads the same operands; only the transport
  mechanism changes (vector vs scalar lane permutation).
- **IR-verified:** Metal LLVM inspection confirmed the frontend emits
  `air.simd_shuffle_xor.u.v2i32` (one vector call) instead of two scalar
  `air.simd_shuffle_xor.u.i32` calls — the rewrite survives compilation.
- **Local M2 microbenchmark:** 1.0018x–1.0071x speedup (small, not transferable
  as M5 forecast, but consistent direction).
- Built on a-github-name's frontier (ab17a99, 2.5979).

### What this tells us
- fyrsta7 is doing **instruction-level optimization** on the serial dependency
  chain of the router selector — the path that gates expert-weight address
  resolution before the QMV can begin.
- This is an extremely granular change (vector packing of shuffle intrinsics).
  The gain is small (+0.0061 score) but real.
- **They explicitly considered and deferred** other mechanisms: pairwise NAX
  scale hoist specialization, shared gate/up QMV staging, QMV reduction
  packing, and relaxing an affine INT8 prefill guard. This shows they have a
  pipeline of single-variable experiments.
- **No MLX compiled functions used.** Direct Metal kernel string editing.

---

## 3. a-github-name — Score 2.5979 (submission f2b7ccc, commit ab17a99)

### Approach: Prefill scale-conversion hoist in M5 NAX expert loader

a-github-name (operating as "lBroth", using GPT-5.6 Sol) has the richest
optimization trajectory. Their promoted submissions span a wide range of
mechanisms. The latest promotion (f2b7ccc) hoists E4M3-to-float scale
conversion in the prefill NAX expert loader:

- Files: `fp_quantized_nax.cpp` (JIT twin) + `fp_quantized_nax.h` (AOT twin)
- Creates a thread-local `pair_scales` array; converts each physical pair scale
  byte to float once, then reuses the float across adjacent logical groups and
  wide chunks.
- **Common-subexpression elimination** over certified physical scale aliases —
  no numerical reassociation.
- Active only for multi-token pairwise expert NAX specializations (prefill);
  decode path unaffected.
- Bit-exact: same `fp4nv_scale_x16384` conversion on same authoritative byte.

### Their broader trajectory (from submission notes):
a-github-name's optimization history shows a systematic approach across many
promoted submissions:

1. **Fused sliding attention** (score ~2.029, submission 44076af): Custom Metal
   kernel fusing sliding-window decode attention with aligned vec4 SDPA loads.
   Required warmup isolation to avoid prefill regression from the full-attention
   twin's second constructor decode.
2. **Wide expert staging** (score ~2.063, submission be30991): Staging all four
   rows' code words and scale bytes before the first qdot in the fused
   routed-plus-shared down kernel — exposing memory-level parallelism.
3. **Lossless affine metadata indexing** (score ~2.118, submission aa6660c):
   Indexing repeated BF16 scale/bias pairs for group-32 affine INT8 QKV and
   output-projection banks, plus per-forward sharing of immutable UInt32 cache
   parameter arrays for fused attention kernels.
4. **Zero-copy prefill scale reuse** (score ~2.590, submission db8b4df):
   Reusing the certified compact routed gate/up scale bank in the M5 NAX
   expert-aligned prefill kernel via a bounded zero-stride marker view.
5. **Pairwise scale layout** (score ~2.598, submission f2b7ccc): Adjacent
   logical group-16 scale coordinates map to one certified physical byte;
   hoisting scale conversion to compute each pair once.

### What this tells us
- a-github-name works across **both decode AND prefill** paths, while yudduy
  and fyrsta7 focus on decode.
- They use **custom Metal kernels extensively** — fused attention, fused
  routed-plus-shared down, custom QMV kernels with per-simdgroup schedules.
- They maintain **environment-variable kill switches** (DARKBLOOM_* flags) for
  every mechanism, enabling same-binary A/B testing.
- They explicitly avoid MLX compiled functions for quantized matmul fusion
  (MLX.compile can't fuse quantizedMM — confirmed in our own negative result
  PR #349/351).
- **They do NOT avoid custom Metal kernels.** Their entire advantage is built
  on them. They edit both JIT C++ twins and AOT Metal headers.

---

## Key Insights: What They're Doing Differently

### 1. All three competitors use custom Metal kernels — none use MLX compiled functions

None of the top 3 are avoiding custom Metal kernels or using MLX's `compile()`
for the scored path. They all edit raw Metal kernel sources (`.metal` headers,
embedded Metal strings in Swift, JIT C++ twins). MLX compiled functions cannot
fuse quantized matmuls or Custom primitives with matmul — this is a known
limitation confirmed by our own negative results (PR #349, #351).

### 2. Optimization targets are differentiated

| Competitor | Primary axis | Score weight | Mechanism level |
|---|---|---|---|
| yudduy | Decode SDPA K/V traffic | 75% | Kernel-level (AOT header) |
| fyrsta7 | Decode router shuffle | 75% | Instruction-level (Metal string) |
| a-github-name | Both prefill & decode | 100% | Kernel + layout + metadata |

### 3. They are NOT reducing JIT kernel count

The competitors are adding and modifying JIT/AOT kernel specializations, not
eliminating them. a-github-name's notes explicitly describe maintaining JIT/AOT
twin pairs (`fp_quantized_nax.cpp` + `fp_quantized_nax.h`). The M5 JIT
compile-storm problem (our 28+ consecutive failures) appears to be **our
specific problem**, not a general competitor strategy of kernel reduction.

Our research state confirms: the organizer frontier (0 JIT kernels) always
passes, while our tree with ~55-82 JIT kernel definitions intermittently fails
the M5 runner timeout. Competitors with similar or higher kernel counts appear
to succeed — suggesting either their kernel compile is faster, or they manage
warmup/initialization differently.

### 4. Dispatch elimination is NOT their strategy

Public notes (metaspartan, note ad4d0e5) explicitly show that **single-
threadgroup launch folds are worthless-to-harmful** on the M5. The hardware
already overlaps tiny sibling dispatches within command buffers. Fusing small
dispatches into big kernels **extends the big dispatch's tail** and costs real
time to save concurrent time. This is a receipted negative result.

However, the **command-buffer ops cap** IS a real lever (metaspartan, note
1f891fe): raising `MLX_MAX_OPS_PER_BUFFER` from 200 to 400 promoted at 2.528
(+0.03 score). The op-count dimension pays; the buffer-size dimension does not
(MB 512 regressed). This is an environment variable, not a code change.

### 5. N-changing GEMM fusions flip near-ties on M5 (critical caution)

Public note (alvgeppetto, note 14a2352): Any fusion that changes a matmul's N
dimension changes which Metal kernel MLX dispatches, and hence the accumulation
order and rounding. On the exact-token benchmark, this is a **correctness/gate
failure on the M5** even when the fused kernel is bit-exact on your local
machine. This is why prefill bank fusions (e.g., [Wq;Wk;Wv;Wg]) fail hidden
gates. Decode fusions escape this because decode is M=1 (scalar per-row order).

### 6. The grid over-dispatch hypothesis is REFUTED

Our own note (morganmcg1, note 7e267f3) proposed that Metal kernels were
over-dispatched by `threadGroupSize`. Our research state confirms this was
**refuted**: MLX's MLXFast API uses `dispatchThreads(gridSize, threadgroupSize)`
where grid = TOTAL THREADS, not threadgroup count. The × threadGroupSize
multiplier is CORRECT. PR #333 was closed as invalid. Do not revisit.

### 7. Shared-expert prefill is at the hardware roofline

Public note (yoyo930021, note 1e74c0d): The 4.5× gap between shared-expert
gate/up and down prefill is because they use different hardware units —
`simdgroup_multiply_accumulate` (classic) vs `tile_matmad_nax` (M5 neural
accelerator). A dense BF16 GEMM at the same shape measures 97.33 µs vs the
shipped quantized kernel's 97.01 µs — 0.3% slower. **The shipped kernel is
already at the classic roofline.** No bit-exact route exists across the
hardware unit boundary.

### 8. Register pressure is the binding constraint for attention kernels

Public note (metaspartan, note b51a6ba): The fused attention kernels launch
1024 threads per threadgroup and sit EXACTLY at the 1024-thread register tier.
Adding even K-only prefetch (+8 live values) drops max threads to 832, refusing
the 1024-thread dispatch at runtime. **Prefetch is undispatchable, not just
slow** in the attention kernels.

### 9. Offline weight transforms are an unexplored vein

Public note (alvgeppetto, note 78341e4): GPT-5.6-Sol's max-effort search
concluded the register-neutral kernel-edit frontier is "picked over" (3rd
confirmation). The only credible standalone movers are **offline weight
transforms** (vocabulary permutation, expert ID co-location) which carry NO
register risk. The expert-permutation class was proven byte-faithful-realizable
but performance was noise-bound with a similarity proxy. A real per-layer
route co-occurrence permutation remains untried.

---

## Summary: Are They Doing Something Fundamentally Different?

**No.** All three competitors use the same fundamental approach as us: direct
Metal kernel editing with bit-exactness preservation. They are NOT:
- Using fewer JIT kernels (they maintain JIT/AOT twins)
- Using MLX compiled functions instead of custom kernels (MLX.compile can't
  fuse quantized matmuls)
- Avoiding custom Metal kernels (their advantage IS custom kernels)
- Eliminating dispatches (proven negative on M5)

**What they ARE doing that we may be missing:**
1. **Decode SDPA K/V traffic reduction** (yudduy): Grouping 3-4 query heads
   per K/V load instead of 2. This is on the AOT `sdpa_vector.h` header —
   requires metallib rebuild.
2. **Instruction-level Metal optimization** (fyrsta7): Vector-packing shuffle
   intrinsics in the router selector. Extremely granular but real.
3. **Prefill scale-conversion hoisting** (a-github-name): CSE over certified
   physical scale aliases in the NAX expert loader. Removes redundant E4M3
   conversions across 39 layers × 256 experts.
4. **Zero-copy prefill scale views** (a-github-name): Bounded zero-stride
   marker views to reuse compact scale banks without allocation.
5. **Wide row staging** (a-github-name): Staging all code/scale loads before
   the first qdot to expose memory-level parallelism in fused-down kernels.

**Our specific disadvantage:**
- Our 28+ consecutive M5 build failures (JIT compile-storm) mean we cannot
  get our optimizations measured. The competitors' trees apparently compile
  within the M5 timeout. Our JIT kernel consolidation effort (PR #350, #352,
  #358) reduced compile count from ~82 to ~55, but this may still be too many.
  The organizer frontier with 0 JIT kernels always passes.
- Our grid over-dispatch investigation (PR #333) was a dead end — refuted by
  MLX's dispatch API semantics.

**Highest-value unexplored directions from competitor evidence:**
1. Decode SDPA two-group schedule (yudduy's exact mechanism) — the single
   highest-scoring change on the leaderboard.
2. Prefill NAX scale-conversion hoist (a-github-name's mechanism) — prefill
   carries 25% of score and this is proven on M5.
3. Command-buffer ops cap tuning (metaspartan's finding) — environment
   variable, zero code cost, proven +0.03 score on M5.
4. Offline weight transforms (expert co-occurrence permutation) — no register
   risk, untried with real route traces.
