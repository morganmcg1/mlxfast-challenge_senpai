# SENPAI Research State
- 2026-08-06T22:32Z (updated by advisor session)
- Campaign mlxfast-birch-20260805. Advisor HEAD at 13fdaf6 (origin/mlxfast-birch-20260805-advisor).
  Scored code frontier: 13fdaf6 (includes #165 ops-per-buffer 800, #166 dense MoE simd_sum,
  #160 register float4, #159 max_threads, #156 fused down float4, #152 top-8 elimination, etc.)

## CRITICAL: Submission History Analysis
  Promoted submission 97a5090: score 2.5888, +3.64%, submitted 8/6 05:04 UTC.
  Promoted code surface at commit 12a712d: PR #84 (top-8 elimination), FMA-optimized dequant,
  STAGE2_GATHER, LM_HEAD_PRUNE, MoE down ops2 disabled. NO dot4/simd_sum/float4/max_threads.

  ALL post-promotion submissions REJECTED or FAILED:
    00de2d3 (11:23): FAILED (15-PR composed, no ops-per-buffer)
    26dc269 (12:11): rejected -7.21%
    c95b4e4 (14:35): rejected -9.16%
    57d8f08 (18:26): FAILED (3-PR composed)
    4b06e93 (21:30): rejected -14% (15-PR + QHOIST)
    0e43085 (22:09): VALIDATING (unknown contents, ~80+ min in queue)

  KEY FINDING: The promoted submission was submitted BEFORE ALL dot4/simd_sum/float4/max_threads changes.
  These instruction-count reductions are COUNTERPRODUCTIVE on M5. M5 is bandwidth-bound for these kernel sizes.

  STRATEGY: Isolate ops-per-buffer 800 on CLEAN promoted code (12a712d) for M5 submission.
  This is the HIGHEST PRIORITY experiment (PR #172, Edward).
  Metaspartan proved 200→400 alone promoted at 2.5282. 200→800 should be even better.

  PR #165 merged: MLX_MAX_OPS_PER_BUFFER 200→800. Bit-exact, 0 bytes growth.
  PR #166 merged: dense MoE simd_shuffle_down→simd_sum. Bit-exact, -6 bytes.
  PR #160 merged: thread float[N]→thread float4[N/4]. Bit-exact, -1160 bytes.

## CURRENT WAVE (Wave 12)
  PR #172 (Edward) — Clean ops-per-buffer 800 on promoted code 12a712d. HIGHEST PRIORITY.
    Isolates the scheduling change from all dot4/simd_sum/float4 kernel changes.
    Target: beat 2.5888 on M5. One-line change, bit-exact.
  PR #169 (Askeladd) — Scale plane halving (BANDWIDTH reduction, 39 MiB/step saved).
    Extends NVFP4 scale halving to QKV+O-proj. Bit-exact. In progress.
  PR #167 (Alphonse) — tail_nvfp4_qdot dot4. Instruction-count reduction — likely dead end
    given strategy shift. Let finish, then close as dead.
  PR #161 (Thorfinn) — tg input sharing. Mixed instruction/bandwidth. Let finish, evaluate.

## READY-TO-ASSIGN EXPERIMENTS
  1. MLX_METAL_FAST_SYNCH=1: One-line setenv, fast fence sync. Bit-exact. M5-specific.
  2. MoE scale-plane halving: Extend attention scale halving to MoE experts (~33 MB/step).
  3. Packed walk-order down-scales: Add DARKBLOOM_PACKED_SCALES to 3 down kernels.
  4. QHOIST prefill isolated: ~17.8% prefill LSU reduction, needs isolated M5 testing.

## CRITICAL FINDING: Command Buffer Ops-Per-Buffer (metaspartan public note)
  The highest-value non-kernel optimization is raising MLX_MAX_OPS_PER_BUFFER from 200 to 800.
  Our code (LagunaRuntimeWeights.swift:387) sets MLX_MAX_OPS_PER_BUFFER=200, but metaspartan
  proved that 200→400 promoted at 2.5282, and 400→800 gave another ~10us decode improvement.
  The M5 loses ~282us/step (5.2% of decode) at command-buffer boundaries. This is a ONE-LINE
  change in an EDITABLE file. Bit-exact (scheduling only, no numerical change).
  MLX_MAX_MB_PER_BUFFER should stay at 200 (larger hurts prefill +3.4%).
  Also: MLX_METAL_FAST_SYNCH=1 is not set by our code (defaults to 0). Could reduce sync overhead.
  Source: metaspartan public note 1f891fe, same organizer frontier bca94c5.

- **WAVE 9 RESULTS** (4 PRs, all resolved):
  PR #159 (Edward) — max_total_threads_per_threadgroup: MERGED. Bit-exact occupancy hint, M4 decode +0.47% (noise), prefill +1.65%.
  PR #160 (Alphonse) — Register-resident float4: WIP (no result yet).
  PR #161 (Thorfinn) — Threadgroup input sharing: WIP (no result yet).
  PR #162 (Askeladd) — is_shared branch elimination: CLOSED. DEAD — Metal compiler already optimizes uniform ternary.
  PR #147 (Alphonse) — CPU Guard Hoisting: CLOSED (incomplete, no result submitted).
  PR #155 (Thorfinn) — Attention Epilogue 1-pass: CLOSED (incomplete, no result submitted).

- **WAVE 9 ASSIGNED** (4 students, BASE_SHA=5ec8550, all bit-exact, all distinct arms):
  PR #159 (Edward) — H1: max_total_threads_per_threadgroup attribute. Add Apple-recommended
    occupancy hint to ALL decode MoE kernels (R1 gate/up: 64 threads, shared SwiGLU: 64,
    fused down+residual: 288, QKV, O-proj, gate-softplus). #1 priority: 5-15% decode on M5.
    Bit-exact. References: Apple Tech Talks 10580, WWDC20, MLX discussion #3801.
  PR #160 (Alphonse) — H4: Thread-local array → register-resident float4 values. Replace
    `thread float input_values[16]` with explicit float4 variables in qdot inner loops.
    WWDC16 warns stack arrays force spills. 0-10% if compiler is spilling. Bit-exact.
  PR #161 (Thorfinn) — H5: Threadgroup input sharing across simdgroups. Both simdgroups in
    R1 gate/up kernel load same input independently. Share via threadgroup memory + barrier.
    Eliminates 2.1M redundant bfloat→float conversions per step. 3-5% gate/up kernel. Bit-exact.
  PR #162 (Askeladd) — H8: Eliminate is_shared branch in 9-slot down+residual kernel. Use
    select() or split shared expert into separate template. 1-2% decode. Bit-exact.

- **M5 SUBMISSION**: 4b06e931 (composed 15 decode PRs + QHOIST prefill).
  Status: VALIDATING (submitted 8/6 ~21:30 UTC). Bit-exact, all merged PRs + QHOIST.
  Previous: 57d8f08 (3-PR composed): FAILED. 00de2d3 (15-PR): FAILED.
  27b9c7c: rejected, 2.4972. 97a5090 (maple): promoted, 2.5888.
  Next: Wave 9 winners (pending) or Dense MoE (Wave 10 target).

- **WAVE 7 RESULTS** (complete, all merged):
  PR #144 (Edward) — R1 Gate/Up float4 input_values: MERGED. Bit-exact, 312x/step.
  PR #146 (Askeladd) — Prefill MoE BM128 Variant 4: MERGED. Bit-exact, +17.47% kernel-level prefill.
  PR #140 (Alphonse) — float4 input_values shared SwiGLU: MERGED. Bit-exact.
  PR #134 (Askeladd) — Fused down+residual packed simd_sum: MERGED. Bit-exact, 39 layers.
  PR #145 (Thorfinn) — QKV+gate dot4: CLOSED. DEAD — dot4 NOT bit-exact for shared-float accumulation.

- **WAVE 5 RESULTS** (complete, all merged):
  PR #131 (Edward) — NVFP4 O-proj packed simd_sum: MERGED. Bit-exact, M4 inconclusive.
  PR #132 (Alphonse) — Affine QKV packed simd_sum: MERGED. Bit-exact.
  PR #133 (Thorfinn) — Shared SwiGLU down packed simd_sum: MERGED. Bit-exact, M4 inconclusive.

- **WAVE 4 RESULTS** (complete):
  PR #130 (Alphonse) — Gate-softplus dot4: MERGED. Bit-exact, +1.44% decode M4.
  PR #129 (Edward) — INT8 O-proj dot4: MERGED. Bit-exact, M4 inconclusive.
  PR #128 (Thorfinn) — Fused down+residual weight staging: MERGED. Bit-exact, +1.14% decode M4.
  PR #124 (Askeladd) — Gate-Scale Fold in O-proj: CLOSED. Dead: non-bit-exact prefill.

- **RESEARCH AGENT FINDINGS (Wave 8 intelligence)**:
  1. CPU GUARD HOISTING: 5 invariant guard chains (L351-428, L5495-5514, L10265/10314/10327,
     L5696-5747, L10769-10771) re-evaluated 5120 times/step. All depend only on static layer
     identity + startup flags. Precomputable into per-layer `struct LagunaDecodeLayerPlan`.
  2. ASYNC-EVAL: sharedExpert(x) has ZERO data dependency on routed path. Prefill builds ~400-op
     graph with GPU idle until final eval. asyncEval(y) between L10108 and L10129 overlaps routed
     down/scatter with shared gate/up dispatch. mergedSharedActivated (L9938) is dead/nil.
  3. ATTENTION EPILOGUE: Two decode-only fused kernels (L1381-1670, L1841-2176). 3 barriers in
     epilogue (A/B/C). Exchange is float32. 1-pass merge IS bit-exact if buffer doubled to 8
     planes (all 4 pair_o0/o1 reduced in one loop). Constraint: ~33KB vs ~32KB threadgroup limit.
     Alternative: transpose-free reduction via quad_shuffle — changes reduction tree order.
  4. REMAINING FLOAT4: Only 1 DEFAULT-path target left — lagunaRoutedSharedDownResidualKernel
     (L7691). qdot already uses dot4 internally, conversion is bit-exact. All remaining scalar
     FMA loops are shared-float accumulation — NOT bit-exact for dot4 (PR #145 proof).
     Dense gate/up SwiGLU (L7841) is NOT clean — same PR #145 structure.
  5. dot(float4) IS bit-exact for per-word NVFP4 qdot (independent accumulators) but NOT for
     shared-float cross-iteration accumulation (single FP32 register, sequential adds).

- **WAVE 10 PLAN** (4 distinct experiments, highest-value first):
  P1 (Edward): MLX_MAX_OPS_PER_BUFFER 200→800 in LagunaRuntimeWeights.swift:387.
    One-line setenv change. Bit-exact scheduling optimization. Expected 3-5% decode on M5.
    This is the HIGHEST-VALUE change — proven by metaspartan public note 1f891fe.
    Also test MLX_METAL_FAST_SYNCH=1 if time permits. Submit ALONE to isolate effect.
  P2 (Alphonse): V-accumulate float4 in fused sliding attention kernel (L1567-1601).
    Pack pair_o0/pair_o1 into float4 temporaries, use vector FMA instead of 8 scalar FMAs
    per K-iteration. Bit-exact (same FMA per lane, scalar broadcast). 30 layers × 256 K-iters.
    Expected 1-3% decode on M5 (instruction-bound). Also update tail (L1607-1614).
  P3 (Thorfinn): V-accumulate float4 in fused FULL attention kernel (L2030-2064).
    Same pattern as P2 but for the 9 full-attention layers. Also update tail (L2094-2101).
    Bit-exact. Independent code path from P2.
  P4 (Askeladd): Dense MoE simd_shuffle_down→simd_sum (L7889-7896).
    Replace 5-iter simd_shuffle_down loop with simd_sum(). Bit-exact cross-lane reduction.
    Dense gate/up + down kernels, 2 dispatches/step. Lower value but safe bit-exact win.
    NOTE: Dense MoE dot4 is NOT bit-exact (shared-float accumulation, same as PR #145).

- **SCALE PLANE HALVING (Wave 11 target, VERIFIED)**:
  MLX quantizer has a pairwise-constancy invariant for NVFP4 (group_size=16): scale[2k]==scale[2k+1]
  for all k>=1 in each flattened weight matrix. Only k=0 (first 32 elements) can differ.
  Our attention weights are ALL NVFP4 (DARKBLOOM_NATIVE_AFFINE_NVFP4 default ON, NVFP4_FROM=0).
  Current scale traffic: ~89 MB/step. Halving via pairwise-constancy packing: ~45 MB/step.
  Implementation: transform-time packing (store 1 nibble per pair) + kernel read packed format.
  Exact escape for k=0 exceptions (~1 per matrix, ~160 total). Bit-exact (lossless re-encoding).
  Budget: ~4K bytes needed, 32K headroom available. Two files: LagunaRuntimeModel.swift + LagunaRuntimeWeights.swift.
  Expected gain: +0.63-0.76% score (byte channel) + instruction savings (strided load elimination).
  QKV scale: 128 B/row × 128 groups, 4 k-blocks/row. O-proj: 384-512 B/row, 12-16 k-blocks/row.
  Kernel access: QKV L4598-4612 (sc[0] per block, advance 32). O-proj L4197-4233 (sc[row*in_vec_size_g]).

- **POTENTIAL NEXT DIRECTIONS (beyond Wave 10)**:
  - Scale plane halving via quantizer invariant (see above — Wave 11 top priority)
  - tail_nvfp4_qdot scalar→dot4: LAST remaining scalar NVFP4 qdot kernel (L4536-4572).
    Runs 40× per decode step (all attention layers). ~1600 instructions saved/thread/step.
    Bit-exact (same pattern as O-proj L4224-4227 and MoE qdot L6508). HIGH PRIORITY.
  - JIT attention pair_planes 2→4: collapse 3 barriers to 1 per attention layer (L1610/2106).
    80 fewer barriers per decode step. ~0.4% decode. Bit-exact (same as stock PLANES=4).
    Threadgroup 8960 bytes (within 32KB limit). MEDIUM PRIORITY.
  - Packed simd_sum(float2) for paired QK scores in JIT fused kernels (L1550-1551).
    ~520 instructions saved per decode step. Bit-exact (per-component independence). LOW PRIORITY.
  - H2: Pre-interleaved weight layout (transform-time, 6-10% gate/up) — after H1/H4 results
  - H3: Fused gate/up+down single-dispatch kernel (saves ~39 dispatches/step, 2-5% decode)
  - H6: Instruction diversity / interleaved load+convert+FMA in qdot (0-5%, pipeline overlap)
  - H7: Half2 FMA accumulation (5-8% but HIGH risk — precision change, likely fails exactness)
  - Transpose-free attention reduction via quad_shuffle
  - MLX_METAL_FAST_SYNCH=1 (fast fence sync, needs Metal 3.2+ / macOS 15+)
  - LAGUNA_RESCALE branch elimination in SDPA vector kernel
  - CPU Guard Hoisting (re-attempt with simpler implementation)
  - Dense MoE layer (layer 0): simd_shuffle_down→simd_sum, scalar FMA→dot(float4).
    BF16 weights, 96 MB/step read, 1/40 layers but largest single-layer bandwidth consumer.
    Bit-exact, same proven patterns as routed kernels. 2 dispatches/step.

- **PREFILL LEVER ANALYSIS** (DARKBLOOM env vars in editable vendored MLX):
  All DARKBLOOM levers audited. Only ONE unenabled lever on the scored M5 path:
  - ATTN_QHOIST: DEFAULT OFF (env "" == "1"). Pure hoist of loop-invariant Q fragments
    in steel_attention_nax prefill kernel. Bit-exact (same pointer/offset/stride/mma order,
    NO float arithmetic touched). Risk: +28 registers/thread, +16KB/threadgroup. Expected
    ~17.8% LSU traffic reduction in prefill attention. M4 CANNOT test (gen 16 < 17 NAX
    threshold — NAX kernel never compiled on M4). Must submit directly to M5.
    File: Vendor/mlx-swift/.../jit_kernels.cpp L1385. Change: default "" → "1". ~20 bytes.
    PREPARED but NOT YET SUBMITTED (blocked by 57d8f08 in queue).
  Already shipping (DEFAULT ON): STAGE2_GATHER (v1), SWIGLU_REGLOCAL, BSEARCH_HOIST,
    QBLOCK_MAJOR, QBLOCK_ZIGZAG. Dead: GATHER_XMAJOR (hardcoded OFF, arms removed).
  Operator submissions with STAGE2_GATHER variant changes (26dc269 -7.21%, c95b4e4 -9.16%)
  both regressed — do NOT change STAGE2_GATHER variant from default 1.

- **LEADERBOARD**: Current promoted best: 2.5888 (maple campaign, submission 97a5090).
  Target: beat 2.5888. All component speedups must be ≥ 0.95.
  Birch campaign best: 2.5459 (rejected, -0.64%). All birch submissions so far below 2.5888.
  15-PR composed HEAD (5c28822) pending submission — blocked by 57d8f08 validating.
- **FRONTIER**: Advisor HEAD at 62380ed (meta). Scored code at 5c28822 (639646a + 15 merges #107→#156).
- **BUDGET**: ~2,964K / 3,000,000 bytes total. LagunaRuntimeModel.swift: ~510K / 524K per file.
  Headroom: ~36K total, ~14K per file. Wave 9 changes are small (<600 bytes each).
- **KEY FINDINGS**:
  1. Attention main loop is MEMORY-BOUND (PR #122). Do NOT pursue attention ALU optimization.
  2. Metal compiler optimizes thread float[N] scatter to registers (PR #123).
  3. Weight staging pre-loading codes/scales before qdot is PROVEN (PR #116, #128).
  4. dot(float4) vectorization is PROVEN for per-word qdot (PRs #107, #114, #119, #129, #130).
  5. dot(float4) is NOT bit-exact for shared-float cross-iteration accumulation (PR #145).
  6. M5 is instruction-bound at ~89%. M4 is bandwidth-bound. M4 evidence directional only.
  7. Gate-scale fold is NOT bit-exact for prefill (PR #124). Folding changes BF16 rounding point.
  8. NVFP4 code pre-expansion inconclusive (PR #121). 4x memory traffic risk.
  9. LM head int4 DEAD — bandwidth-bound, zero saving.
  10. Scale Decode LUT closed dead (PR #125). Core bet: constant-cache load vs ALU on M5.
  11. input_values[16]→float4[4] is bit-exact when qdot uses dot4 internally (PRs #140, #144).
  12. asyncEval adds no operation — only enqueues already-constructed work earlier (L656-658).
  13. mergedSharedActivated (L9938) is dead/nil — never assigned, plumbing unconnected.
  14. Prefill builds ~400-op graph with GPU idle until final eval (comment L719-730).

## Prior Results (DO NOT REPEAT)

| PR | Student | Idea | Result |
|----|---------|------|--------|
| #162 | Askeladd | is_shared branch elimination (select()) | IN PROGRESS (Wave 9). Bit-exact. |
| #161 | Thorfinn | Threadgroup input sharing across simdgroups | IN PROGRESS (Wave 9). Bit-exact. |
| #160 | Alphonse | Register-resident float4 input_values | IN PROGRESS (Wave 9). Bit-exact. |
| #159 | Edward | max_total_threads_per_threadgroup | IN PROGRESS (Wave 9). Bit-exact. |
| #156 | Askeladd | Fused down+residual float4 input_values | MERGED. Bit-exact, +1.03% decode M4. |
| #154 | Edward | async-eval shared expert | CLOSED. DEAD — MLX already overlaps. |
| #147 | Alphonse | CPU guard hoisting | CLOSED (incomplete, no result). |
| #146 | Askeladd | Prefill MoE BM128 variant 4 | MERGED. Bit-exact, +17.47% kernel prefill. |
| #145 | Thorfinn | QKV+gate dot4 | CLOSED. DEAD — not bit-exact (shared-float accum). |
| #144 | Edward | R1 gate/up float4 input_values | MERGED. Bit-exact, 312x/step. |
| #140 | Alphonse | float4 input_values shared SwiGLU | MERGED. Bit-exact. |
| #134 | Askeladd | Fused down+residual packed simd_sum | MERGED. Bit-exact, +0.83% decode M4. |
| #133 | Thorfinn | Shared SwiGLU down packed simd_sum | MERGED. Bit-exact. |
| #132 | Alphonse | Affine QKV packed simd_sum | MERGED. Bit-exact. |
| #131 | Edward | NVFP4 O-proj packed simd_sum | MERGED. Bit-exact. |
| #130 | Alphonse | Gate-softplus dot4 + simd_sum | MERGED. Bit-exact, +1.44% decode M4. |
| #129 | Edward | INT8 O-proj dot4 + simd_sum | MERGED. Bit-exact, M4 inconclusive. |
| #128 | Thorfinn | Fused down+residual weight staging | MERGED. Bit-exact, +1.14% decode M4. |
| #124 | Askeladd | Gate-scale fold in O-proj | CLOSED. Dead: no speedup, non-bit-exact prefill. |
| #121 | Edward | NVFP4 code pre-expansion | CLOSED. Inconclusive, 4x memory traffic risk. |
| #119 | Alphonse | NVFP4 O-proj dot4 | MERGED. Bit-exact. |
| #116 | Edward | Shared SwiGLU staging | MERGED. Bit-exact. |
| #114 | Alphonse | INT8 QKV dot4 | MERGED. Bit-exact. |
| #107 | Alphonse | NVFP4 qdot dot4 | MERGED. Bit-exact. |
| #122 | Thorfinn | Attention ALU optimization | CLOSED. Memory-bound. |
| #123 | Thorfinn | Scatter-to-float4 | CLOSED. Compiler already optimizes. |
| #102 | Thorfinn | Attention threadGroup 1024→128 | CLOSED. Speedup was from doing half the work. |
| #97 | Edward | Prefill dispatch elimination | NEGATIVE. Dispatch overhead negligible. |
| #96 | Thorfinn | Register-prefetch shared SwiGLU | NEGATIVE. Register pressure regression. |
| #93 | Edward | Register-prefetch down+residual | NEGATIVE. Bandwidth-bound. |
| #74 | Edward | Prefetch depth 2→4 | NEGATIVE. Bandwidth-bound. |
| #98 | Askeladd | Prefill O-proj affine | MERGED then reverted (cc63c1c). |
| #125 | Alphonse | Scale Decode LUT | CLOSED dead. |

Note: Orphan PRs (#69, #83, #86, #92, #99, #108, #111, #113, #115, #126) are broken from
prior sessions. Cannot close via close_experiment. Ignore.
