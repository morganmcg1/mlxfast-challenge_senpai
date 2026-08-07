# SENPAI Research State
- 2026-08-07T02:00Z (updated by advisor session)
- Campaign mlxfast-birch-20260805. Advisor HEAD: 7b0f3a9 (pushed to origin).
  Clean scored code frontier: 12a712d (pre-QHOIST, pre-BM128-v4, pre-dot4/simd_sum/float4).
  QHOIST (#183) + BM128-v4 (#185) REVERTED — M5 submission 89521f6 REJECTED at -11.48% (score 2.4822).
  PR #186 (edward, MLX_METAL_FAST_SYNCH): CLOSED. DEAD — no decode/prefill gain. Fence overhead ~0.5%.
  PR #169 (askeladd, QKV+O-proj scale halving): CLOSED. DEAD — attention scale traffic too small (~0.2-0.5%).
  PR #180 (alphonse, MoE scale halving): Revision v2 requested (baseline advanced to 7b0f3a9).
    GREEN v1 result (~0.6-1.4% M4 decode gain, bit-exact).
    DEAD CODE: _halvedFusedGateUpScales built but never wired to shared SwiGLU QMV kernel.
    v2: fix shared SwiGLU QMV halving + rebase to 7b0f3a9.
  PR #188 (thorfinn, packed down-scales): CLOSED. DEAD — 1.2-1.6% slower. Down scales already coalesced.
    KEY FINDING: Down path's per-expert scale access is ALREADY coalesced (32 contiguous bytes/row).
    Gate/up packed bank works because it fixes a within-expert ROW REMAP; down path has no remap to fix.
    IMPLICATION: QKV (PR #191) and O-proj (PR #192) packed-scales also likely dead — their scale
    accesses are also contiguous (32 lanes × 1 byte = 32 contiguous bytes). Students warned + redirected.
  PR #193 (thorfinn, attention scale halving): ASSIGNED. Re-test prematurely closed PR #169 hypothesis.
    QKV+O-proj scale traffic = ~90 MiB/step (corrected from earlier 0.2-0.5% estimate → 0.76% of step time).
    First step: verify pairwise constancy in QKV/O-proj scale tensors. If >50%, implement halving.
  PR #191 (edward, QKV packed-scales): WIP, redirected to QKV scale halving.
  PR #192 (askeladd, O-proj packed-scales): WIP, redirected to O-proj scale halving.
  Bandwidth audit complete: see research/BANDWIDTH_AUDIT_20260807.md.
  PR #187 (thorfinn, duplicate marker): IGNORE — PR #188 replaces it.

## M5 SUBMISSION STATUS
  QHOIST+BM128-v4 (89521f6): REJECTED at -11.48% (score 2.4822). Prefill-only changes regressed on M5.
  Last: 4f546a8 (PR #171, KV cache rotating): REJECTED at -12.98% (score 2.4671).
  Previous: 2278bd8 (ops-800): REJECTED at -7.23%. All post-promotion submissions REJECTED.
  Promoted: 97a5090 (maple campaign), score 2.5888 (+3.64%), committed 8/6 05:04 UTC.
  Birch clean base (12a712d): score 2.5459 on M5. Gap to beat: +1.69%.
  STRATEGY: DECODE bandwidth reductions only. Prefill M4 gains do NOT transfer to M5.
    Wave 5 (current): 4 decode bandwidth experiments, all bit-exact.
      PR #180 v2 (alphonse): MoE scale halving + shared SwiGLU fix (~1% M4 decode gain).
      PR #191 (edward): QKV packed-scales → REDIRECTED to QKV scale halving (coalescing already optimal).
      PR #192 (askeladd): O-proj packed-scales → REDIRECTED to O-proj scale halving (coalescing already optimal).
      PR #193 (thorfinn): Attention QKV+O-proj scale halving (~0.76% decode, re-test of PR #169).
    All 4 target PURE BANDWIDTH REDUCTION (halving scale bytes, not coalescing).
    NO instruction-count reductions. NO prefill changes. NO scheduling changes.
    KEY FINDING: Scale COALESCING is exhausted — QKV, O-proj, and down paths are ALL already coalesced.
    Scale HALVING is the remaining bandwidth opportunity: MoE (~1% decode) + attention (~0.76% decode).
    Next submission: compose winning scale-halving experiments from clean base (12a712d).
    Submit from CLEAN base + decode scale halving only. NO prefill changes.
    FALLBACK: If Wave 5 fails, re-test instruction-count reductions PURE on clean base
      (no ops-800, no QHOIST, no prefill). Start with packed simd_sum (lowest risk).
      Research finding: no pure instruction-reduction submission was EVER tested on M5.
      ALL rejections included ops-800 or QHOIST. ops-800 alone (no instruction changes)
      was rejected at -7.23%, proving ops-800 was the cause, not instruction reductions.
    KEY INSIGHT: M5 is bandwidth-bound, NOT instruction-bound. The "89% ALU" includes
      stall cycles (ALU active but waiting for memory). NVFP4 decode is ~2 FLOP/byte
      vs 27 FLOP/byte ridge point — 13x below arithmetic intensity ridge.
  CRITICAL: QHOIST+BM128-v4 REVERTED from advisor branch. Prefill changes are TOXIC on M5.
  BANDWIDTH AUDIT KEY FINDINGS:
    1. Shared SwiGLU QMV halving: ~2.43 MiB/step, bit-exact, primary decode path (PR #180 dead code).
    2. Gate-softplus/g_proj: NOT applicable (group_size=32, not NVFP4 pairwise constancy).
    3. Dense MoE (layer 0): NOT applicable (BF16, no quantization).
    4. Fallback kernel halving: LOW priority (fallback paths, not default-on).
    5. NVFP4 code packing: already maximally packed (4-bit, 2-per-byte in uint32).
    6. KV cache: already minimal (fused in-place reads).

## CRITICAL: Submission History Analysis
  Promoted submission 97a5090: score 2.5888, +3.64%, submitted 8/6 05:04 UTC.
  Promoted code surface at commit 12a712d (CLEAN — no dot4/simd_sum/float4).

  ALL post-promotion submissions REJECTED or FAILED:
    00de2d3 (11:23): FAILED (15-PR composed, no ops-per-buffer)
    26dc269 (12:11): rejected -7.21%
    c95b4e4 (14:35): rejected -9.16%
    57d8f08 (18:26): FAILED (3-PR composed)
    4b06e93 (21:30): rejected -14% (15-PR + QHOIST)
    0e43085 (22:09): rejected -12.91% (composed kernel changes at 13fdaf6)
    2278bd85 (23:10): rejected -7.23% (clean ops-800 only)

  KEY FINDING: Instruction-count reductions (dot4, simd_sum, float4, max_threads) are
  COUNTERPRODUCTIVE on M5. M5 is bandwidth-bound for these kernel sizes despite 89% ALU
  utilization. The 89% ALU figure includes stall cycles — the ALU is active but waiting
  for memory. The ops-800 submission (clean scheduling change only) was ALSO rejected,
  suggesting scheduling changes that increase buffer sizes may also be counterproductive.

  COMPILED DECODE: RESEARCHED AND KILLED. Research agent confirmed compiled decode
  would DISABLE fused Metal kernels (CompilableKVCache ≠ KVCacheSimple, stale offset
  breaks fusedRingPrepare guard), inflate full-attention K/V traffic 1.5-6.4×, and
  compile() cannot fuse custom metalKernel dispatches (81 uses, opaque to MLX fusion).
  Verdict: "Likely to HURT on a bandwidth-bound M5." Do NOT assign compiled decode.

  STRATEGY PIVOT: Focus on bandwidth reduction (scale halving) and command buffer
  optimization (MB tuning). Test each ISOLATED on the current advisor base.
  Correctness: ALL PASSED (local-iterate, local-submit 1025 steps, upstream equiv 8/8, swift test 456/456)
  M4 timing: -0.91% decode (EXPECTED — M4 bandwidth-bound, M5 is decisive)
  Submitted: 2026-08-06T23:10 UTC as 2278bd85-01a1-41df-97dc-f744335ad3c4
  Previous submission 0e43085: REJECTED at -12.91% (score 2.4606, composed kernel changes)

## CRITICAL: Submission History Analysis
  Promoted submission 97a5090: score 2.5888, +3.64%, submitted 8/6 05:04 UTC.
  Promoted code surface at commit 12a712d (CLEAN — no dot4/simd_sum/float4/max_threads).

  ALL post-promotion submissions REJECTED or FAILED:
    00de2d3 (11:23): FAILED (15-PR composed, no ops-per-buffer)
    26dc269 (12:11): rejected -7.21%
    c95b4e4 (14:35): rejected -9.16%
    57d8f08 (18:26): FAILED (3-PR composed)
    4b06e93 (21:30): rejected -14% (15-PR + QHOIST)
    0e43085 (22:09): rejected -12.91% (composed kernel changes at 13fdaf6)

  KEY FINDING: Instruction-count reductions (dot4, simd_sum, float4, max_threads) are
  COUNTERPRODUCTIVE on M5. M5 is bandwidth-bound for these kernel sizes despite 89% ALU utilization.
  The 89% ALU figure includes stall cycles — the ALU is active but waiting for memory.

  STRATEGY PIVOT: Focus on scheduling (ops-per-buffer, BFS width, fast synch) and
  bandwidth reduction (scale halving). Test each ISOLATED on clean promoted code (12a712d).

## CURRENT WAVE (Wave 15 — Bandwidth + Scheduling + Prefill, 2026-08-07T00:35Z)

  PR #169 (Askeladd) — Scale-plane halving for QKV+O-proj. IN PROGRESS.
    Bandwidth reduction: halve NVFP4 scale traffic for attention kernels.
    Bit-exact. Targets ~39 MiB/step savings. RIGHT direction for bandwidth-bound M5.

  PR #179 (Thorfinn) — MLX_MAX_MB_PER_BUFFER 200→800. IN PROGRESS.
    Allow asyncEval segments to fit in one command buffer (weight buffers count
    toward buffer_sizes_, so 200 MB limit may cause premature commits within
    segments). Bit-exact scheduling change. Tests if byte limit is binding.
    NOTE: ops=800 was rejected at -7.23% on M5. MB per buffer is a DIFFERENT
    parameter (byte limit vs op count limit) — still worth testing.

  PR #180 (Alphonse) — MoE scale-plane halving. IN PROGRESS.
    Extend pairwise-constancy scale packing to MoE gate/up+down kernels.
    Bandwidth reduction: halve MoE scale traffic (~10 MiB/step).
    Bit-exact. Targets the DOMINANT decode cost center.
    Independent of PR #169 (different kernels), composable if both win.

  PR #181 (Edward) — Revert MLX_MAX_OPS_PER_BUFFER 800→200. MERGED (fc6f78d).
    CORRECTIVE: ops-800 (PR #165) was rejected at -7.23% on M5. Restoring
    promoted ops=200 value eliminates the handicap for future M5 submissions.
    Bit-exact. This was a corrective merge, not an optimization.

  PR #183 (Edward) — Enable DARKBLOOM_ATTN_QHOIST. JUST ASSIGNED.
    Hoist loop-invariant Q fragments in M5 prefill attention (steel_attention_nax).
    Saves ~17.8% of prefill attention loader traffic. Bit-exact (pure hoist).
    M5-SPECIFIC: M4 doesn't select _nax kernels, so M4 shows NO timing signal.
    Risk: +28 registers/thread could cross occupancy threshold.
    Independent of decode experiments (targets prefill 25%, not decode 75%).

  Closed in this session:
    PR #167 (Alphonse, tail dot4) — CLOSED: instruction-count reduction, counterproductive on M5.
    PR #124 (Askeladd, gate-scale fold) — CLOSED: no speedup + non-bit-exact prefill.
    PR #175 (Edward, BFS width 50→100) — CLOSED: dead hypothesis, M4 noise, BFS only affects MLX primitive op fusion (custom kernels opaque).
    PR #181 (Edward, ops revert) — MERGED: corrective, restored ops=200.
    PRs #128, #129, #130 — already merged (counterproductive changes in composed submission).

  DEAD EXPERIMENTS (do NOT reassign):
    - Compiled decode: research confirms regression (disables fused kernels, 6.4× traffic).
    - asyncEval=off: measured -10.5% regression (overlap is worth +9.7%).
    - BFS width 50→100: M4 noise, BFS only affects MLX primitive op fusion (custom kernels opaque).
    - All instruction-count reductions (dot4, simd_sum, float4): counterproductive on M5.
    - INT8 KV cache: NOT in accepted quantization envelope (KV cache is BF16, not a "projection").

## NEW: Research Agent Scheduling Findings (2026-08-06T23:22)
  Research agent identified 5 NEW scheduling/bandwidth opportunities:

  1. **Whole-step compiled decode** (HIGHEST IMPACT, Medium-High complexity)
     Scored decode path calls model UNCOMPILED with non-compilable caches.
     CompiledDecode.swift:87-92 isEnabled=true but only invoked by GenerationBatch
     (scored worker doesn't use it). Fix: make newCache() return CompilableKVCache/
     CompilableRotatingKVCache + wrap decode in compile(). Fuses entire 40-layer graph.
     Files: LagunaRuntimeModel.swift, CompilableKVCache.swift, CompilableRotatingKVCache.swift

  2. **Zero asyncEval fires** (DARKBLOOM_DECODE_ASYNC_STAGE=off, Trivial)
     With ops-per-buffer=800, entire 40-layer decode (~400 ops) fits in ONE command buffer.
     Default fires asyncEval at 7 layers (at:0,1,7,15,23,31,39), splitting into 7 buffers
     with 7 fence pairs. On bandwidth-bound M5, GPU rarely idle — fence/boundary cost
     may exceed overlap benefit. Bit-exact (only changes enqueue timing, not computation).
     ASSIGN TO ALPHONSE NEXT.

  3. **MLX_MAX_MB_PER_BUFFER tuning** (Trivial, needs instrumentation)
     200 MB limit may force premature auto-commit before 800 ops reached (weight buffers
     count toward buffer_sizes_). Check which limit fires first (ops vs bytes).
     If byte-count fires first, increase MB to 1000-2000. Bit-exact.

  4. **MLX_METAL_FAST_SYNCH=1** (PR #173, IN FLIGHT, Trivial)
     Only relevant if asyncEval fires remain. With 7 fires/step, saves 7 Event round-trips.
     If asyncEval=off wins, this becomes moot for decode. Bit-exact.

  5. **NO_SIMPLIFY compile mode** (Speculative, depends on #1, Medium)
     If whole-step compiled decode enabled, compile() runs 3 simplify passes on full
     40-layer graph. Skip simplify with MLX_COMPILE_MODE_NO_SIMPLIFY to keep only fuse.
     Needs C bridge (not exposed in Swift MLX). Bit-exact (simplify only applies
     algebraic identities). Low-Medium impact.

## Potential Next Research Directions
  1. Compose bandwidth winners (scale halving decode + QHOIST prefill) for cumulative M5 gain
  2. Revert dot4/simd_sum/float4 changes before M5 submission to eliminate counterproductive handicap
  3. Explore further prefill _nax kernel optimizations (steel_attention_nax.cpp is editable)
  4. Test asyncEval=off with ops=200 (previous test was with ops=800 — different regime)
  5. Investigate MLX_METAL_FAST_SYNCH=1 for fence overhead reduction

## READY-TO-ASSIGN EXPERIMENTS (Next Wave)
  1. **DARKBLOOM_STAGE_BM128 variant 5→4** (PREFILL MoE tiling, bit-exact, HIGH priority)
     - One-line change in quantized.cpp: `return 5` → `return 4`
     - Variant 4: WM=4, WN=2, SM=16, SN=32, 256 thr/TG, Dtile=16
     - Variant 5: WM=4, WN=1, SM=16, SN=64, 128 thr/TG, Dtile=32
     - Variant 4 measured +17.47% vs variant 5 at kernel level (ABBA, 4/4 pairs, 342-371 vs 414-434 µs)
     - Decode flat (-0.18%). Gain is prefill (MoE gather-GEMM staging latency 39.5% of prefill)
     - Works on BOTH M4 and M5 (not _nax-specific). M4 can measure timing!
     - Bit-exact: same SN=32, TN=2, TK=2, same per-row K partition, same accumulation order
     - Reverted with the clean frontier restore. Needs to be re-enabled and tested in isolation.
     - Expected: ~8.7% prefill improvement × 25% score weight = ~2.2% overall
     - INDEPENDENT of QHOIST (different kernels: MoE gather-GEMM vs attention)
     - Composes with QHOIST if both win (both prefill, different kernels)

  2. MLX_METAL_FAST_SYNCH=1: One-line setenv, fast fence sync. Bit-exact. M5-specific.
  3. Packed walk-order down-scales: Add DARKBLOOM_PACKED_SCALES to 3 down kernels.

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
| #186 | Edward | MLX_METAL_FAST_SYNCH=1 fence mode | CLOSED. DEAD — no gain. Fence overhead ~0.5%. |
| #185 | Thorfinn | BM128 v5→v4 prefill tiling | MERGED then REVERTED. M5 rejected at -11.48% with QHOIST. |
| #183 | Thorfinn | QHOIST prefill attention | MERGED then REVERTED. M5 rejected at -11.48%. Prefill M4→M5 doesn't transfer. |
| #171 | (various) | KV cache rotating fused-prepare | REJECTED -12.98% on M5. |
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
