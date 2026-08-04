# SENPAI Research State

- 2026-08-04 08:00 UTC — advisor `meridian`, campaign `mlxfast-maple-20260804`
- Human research direction: four students, four distinct causal arms, all four
  authorized to dispatch official MLXFast submissions from the AWS Macs. Keep
  the campaign isolated from parallel research branches.
- **Frontier `BASE_SHA=0d980bb03040182b4595cab070fd249944ea3621`** (round 2).
  Round-1 base was `768bb9d4`; organizer frontier
  `ORGANIZER_FRONTIER_SHA=afcb8320912aa1162f841f282442d7c093e6b2e5`.

## Round 1 outcome: 3 merged, 1 closed, 1 official submission in flight

| PR | Student | Disposition | Result |
| --- | --- | --- | --- |
| #7 | maple-nezuko | **merged** | **decode −6.8% on M4 Pro** (0.0146282 → 0.0136301 s/token, 1.0732x), prefill 1.0022, bit-exact, 4 lines, +4 bytes |
| #4 | maple-frieren | **merged** | bit-exact, **−333 surface bytes**, −3.4% host CPU (invisible in M4 wall time by design) |
| #5 | maple-fern | **merged** | clean negative + `senpai/tools/sliding-attn-probe` (2 s screen vs 8 min pair, 0.77% prediction error) |
| #6 | maple-tanjiro | **closed** | clean negative that retired the whole certified-screen family; produced the 44,971 B reclaim recipe |

Official submission **`27b9c7c6`** (nezuko's #7 alone, note 15.2 KiB, model
attribution `Claude Opus 5`) — status `validating`. Frieren's #4 is merged into
the frontier but deliberately **not** in that submission, so submission 2 can
read its M5 effect cleanly.

Published M5 frontier being attacked: score **2.4550**, decode **5.249092
ms/token** (2.6466x), prefill **0.195665 ms/token** (1.9593x).

## The campaign thesis was tested and REFUTED — this is the round's biggest result

Round 1's premise was that 35–45% of decode wall time is dispatch/command-buffer
overhead. Measured on M4 Pro, it is not:

| measurement | value |
| --- | --- |
| measured host read ceiling (not spec 273) | **260.2 GB/s** |
| bytes per steady decode step (measured, not estimated) | **1.7929 GB** |
| DRAM floor | 6.891 ms/step |
| steady wall / GPU busy | 9.816 / 9.498 ms |
| **step is GPU-busy** | **96.7%** — host/queue gap only 0.322 ms |
| achieved | 188.8 GB/s = **72.5% of ceiling** |
| dispatches / command buffers per step | **406** (not ~324) / 45 |
| all 45 command buffers cost | **60 µs/step = 0.6%** |
| host CPU H vs GPU-bound G (M4) | 4.7 ms vs 9.87 ms ⇒ **5.2 ms host slack** |

`gpu_busy_sum == gpu_busy_union` to 6 ns ⇒ dispatches are **fully serialized**;
there is no overlap to reclaim. So the overhead tier is worth 60–322 µs of a
9.8 ms step. **The real gap is individual kernels below their own roofline**, and
87% of it is now named. Dispatch *count* is a lever; dispatch *cost* is not.

M5 differs in one important way: host CPU is ~3.7–4.1 ms of a 4.47 ms step
(83–92%), so on the ranked host host-side work is a **prerequisite** for
realizing further GPU wins, not a score in itself.

## Measured per-dispatch decode budget — the current map

Post-#7 headroom ranking, µs/step recoverable if each kernel reached ceiling:

| kernel | n/step | µs/step | %ceil | headroom | owner |
| --- | ---: | ---: | ---: | ---: | --- |
| `routed_shared_down_residual` | 39 | 896 | **89%** | *cashed by #7* | — |
| `sliding_fused_attn_ring_v1` | 30 | 661 | 37% | 419 | **closed by #5** |
| `shared_nvfp4_swiglu_qmv_rows1` | 39 | 242 | 73% | 64 | #9 nezuko |
| `residual_rms_router` | 39 | 266 | 60% | 107 | #10 tanjiro (geometry) |
| `full_fused_attn_grow_v1` | 10 | 235 | 43% | 134 | #10 tanjiro |
| `gate_sp_h64_v1` / `_h48_v1` | 40 | 266 | **2%** | 146 | #9 nezuko |
| `decode_router_top8_ordinal_table_norm` | 39 | 148 | **0%** | 148 | #9 nezuko |
| `lmhead_exact_inline_mask_block_v1` | 1 | 77 | latency | 74 | unassigned |
| `oproj_act_h48_v1` | 10 | 303 | 90% | 37 | #10 tanjiro |
| already at ceiling (no headroom) | | | 93–101% | — | routed QMV, QKV h64/h48, `oproj_act_h64`, `lmhead_int5_inline_coarse_v5`, dense layer-0 |

Byte budget: weights 1.5703 GB (87.4%), lm_head coarse plane 134.9 MB (7.5%),
KV reads 84–89 MB (4.8%), activations/norms/router 3.6 MB (0.2%).

## Current research focus

**Tier 1 — close the per-kernel roofline gap.** #7 proved the mechanism (rows
per simdgroup ⇒ more memory in flight per barrier-bounded threadgroup). ~1.59
ms/step of gap remains, of which ~0.66 ms sits in four near-zero-bandwidth
dispatches. Arms #9 and #10.

**Tier 2 — the unexplored axis: the 512-token forward pass.** The harness
charges the 512-token seed prefill into the reported decode figure and divides
by 128. With M5 elasticity 0.64 steady / 0.36 prefill-class:

```
512-token forward weight = 0.75×0.36 + 0.25 = 0.52
steady decode step weight = 0.75×0.64      = 0.48
```

A 1% prefill-class win is worth marginally **more** score than a 1% steady-step
win, and the prefill path has never been profiled once in this campaign. Arm
#11. Leading hypothesis: at 512 tokens, top-8 of 256 experts gives ~16 tokens
per expert against 32–64-row GEMM tiles, so routed-MoE prefill may be doing
mostly wasted tile work.

**Tier 0 (enabler) — surface bytes.** The editable surface is capped at
3,000,000 raw bytes with `fileCount` pinned at 142; round 1 started with **16
bytes of headroom** and three students independently hit it. Now 345 bytes.
Arm #8 reclaims ~45 KB. Until it lands nobody can add code.

## Arms in flight (round 2)

| PR | Student | Arm | Expected | Key risk |
| --- | --- | --- | --- | --- |
| #8 | maple-frieren | Reclaim ≥40 KB surface (v4/MXFP8 arm in `LagunaLmHeadPrune.swift`, 44,971 B) + stop rebuilding 28.7 KB of Metal kernel source on every apply (~363 applies/step ⇒ ~1.16 MB alloc+copy/step) | ≥40 KB + 100–200 µs/step host | host win invisible in M4 wall time; must use spin-injected pair. v4 arm is not pure dead code — backs a live `init?` guard |
| #9 | maple-nezuko | Fuse the four near-zero-bandwidth dispatches: `mergedSharedActivated` (declared, never assigned ⇒ 39 needless dispatches), `gate_sp_h64/h48`, router ordinal table | ~0.66 ms/step ⇒ ~4.0% M4 / 5.0% M5 decode | barriers are encoder-wide; fusing can lengthen the critical path. Two recorded negatives in this family already |
| #10 | maple-tanjiro | Generalize the #7 rows-per-simdgroup remap to `full_fused_attn_grow_v1` (43%), `residual_rms_router` (60%), `oproj_act_h48` (90%) | ~278 µs/step ⇒ ~1.7% M4 / 2.1% M5 | wider per-lane loads break `simd_sum` association ⇒ not bit-exact. Occupancy/prefetch already null per #5 |
| #11 | maple-fern | Profile the 512-token forward pass; then routed-MoE prefill tile efficiency vs the measured per-expert token histogram | ~2.1% of total score if routed prefill is ~40% and 10% improvable | token grouping that reorders accumulation is not bit-exact; prefill may already be at its regime ceiling (a valuable close) |

Coordination: #9 and #10 both touch `residual_rms_router` and `oproj_act` —
#10 owns internal geometry, #9 owns what work is folded in. Merge sequencing is
mine.

## Hard constraints (corrected this round)

- **The 1.053 acceptance-band upper edge is NOT enforced on the ranked timing
  path.** This reverses round-1 guidance and was audited from source:
  `Sources/MLXFastCore/Constants.swift:150-166` states the `officialBaseline*`
  constants are not the ranked denominator; the harness pass that would enforce
  the band runs under `MLXFAST_BENCHMARK_SKIP_TIMED=1`
  (`.github/workflows/benchmark.yml:1511`) so its speedups are 1.0 by
  construction; the only trusted judge of measured timing is
  `.github/scripts/overlay-paired-timing.sh:129-169`, which applies the 0.95
  floors and nothing else. Empirically decisive: 120 of 126 promoted receipts
  are faster than any pinned-reference band permits, and rank 119 → 120 was an
  accepted single submission with a **+7.86% decode step**. `mlxfast skill`
  states the operative rule: *"A submission is only accepted and promoted if it
  beats the current best."* **Never throttle, stage, or split a win to fit a
  band.** Residual risk: `measure-job.sh` is box-owned and unreadable here.
- Editable surface ≤ 3,000,000 bytes total, ≤ 524,288 per file,
  `fileCount == 142` pinned by `Tests/BenchmarkScriptTests.swift:2557`.
  Enforcement is **asymmetric**: `MLXFastCLI/main.swift:1394-1402` warns
  locally but throws under `MLXFAST_OFFICIAL_BENCHMARK_RUN=1`, and
  `run-submission-static-review.sh:140-143` exits 1 unconditionally. A
  candidate can be green in every local mode and refused on M5.
- Score elasticity for de-rating a per-step win: 1% of a steady step = 0.51% of
  the M4 decode term, 0.64% on M5; 1% prefill-class = 0.47% M4 / 0.36% M5.
  Baseline decode split: seed 546 ms (29.2%), 128 steady steps 1265 ms (67.5%),
  IPC 61 ms (3.3%).
- Harness noise floor ~±1% per pair (from a causally impossible 1.1% prefill
  move); the same probe variant varies ~10% across processes.
- Changed JIT kernels need fresh pipeline names (MLX's cache is name-keyed).
  AOT sources (RoPE, RMSNorm, `sdpa_vector`, `arg_reduce`) need
  `tools/build-mlx-metallib.sh`.
- `LagunaUpstreamEquivalence.swift` reports prefill max-abs 0.125 and exits 1
  **byte-identically on the unmodified base** — pre-existing, cannot gate.
  Judge the decode-path logit error, which must be exactly 0.
- The local quality panel is an amber drift alarm, not a submission veto.
- The accepted quantization envelope (group-32 affine INT8 for Q/K/V/O and
  per-head `g_proj` only) is fully spent.
- `Sources/MLXFastTransform/` is not a speed surface: the runtime copies every
  tensor into MLX-owned memory at load, so offline layout is isomorphic to
  load-time preparation that is already unscored. 0 of 126 promotions touched it.
- `MLX_MAX_OPS_PER_BUFFER` is **inert**: MLX's 40 MB-per-buffer byte limit trips
  first (a sparse layer touches ~38 MB), and it cannot be swept below 64 GiB
  because the low-memory profile forces 64/128 as asserted contract.

## Potential next research directions

1. **`lmhead_exact_inline_mask_block_v1`, 76.6 µs/step, launch-latency tail.**
   Unassigned. A fusion question, not a pruning question — #6 closed pruning.
2. **Resident footprint.** `mlx_peak_gb` 35.61 vs `recommendedMaxWorkingSetSize`
   37.4 GiB against a 21.6 GB checkpoint. Scoped in #7 and deliberately not
   landed because a release path needs hundreds of surface bytes. Revisit once
   #8 reclaims. May be a 48 GiB low-memory artifact that does not transfer.
3. **Graph-valued ring/cache index plus compiled multi-layer decode segments.**
   Unused infrastructure exists: `CompiledDecode.swift:125/168`,
   `CompilableKVCache.swift`, `DynamicSlice.swift`, `RoPEApplication.swift:27`.
   Blockers: `decodeRoPEAtlasPosition` rejects compilable subclasses by exact
   `type(of:)`; fused attention downcasts to concrete cache types. Now that #4
   is terminal this is unblocked, but the 96.7% GPU-busy measurement means its
   ceiling is the 0.322 ms host/queue gap on M4 — small here, larger on M5.
4. **Multi-output QKV kernel** to remove ~120 slice nodes/step, and memoizing
   the full-attention `MLXArray([writeIdx, writeIdx+1, capacity])` (~30–60 µs).
5. **M5-specific re-sweep.** M5 selects `_nax` variants and has 614.4 GB/s; #7's
   `outputs_per_simd` argmax of 4 should be re-checked against 8 there.
6. **Re-examine the sliding attention kernel with a different lens.** #5 closed
   KV amplification, threadgroup memory, and prefetch depth, yet it still sits
   at 37% of ceiling with 419 µs of headroom — the largest single unexplained
   gap on the map. Something is limiting it that we have not named.

## Explicitly not to re-attempt

Certified LM-head screens at any bound looseness m ≥ 2, and the block-level
Hölder / Cauchy–Schwarz / mean-row+residual-norm family (#6: per-row members
already retain 100%). Sliding-attention KV-group widening w4/w8 and its
threadgroup-memory and prefetch-depth knobs (#5). Split-K / flash-decode
partition at N=512. Wider per-lane loads in the down kernel (breaks `simd_sum`
association). Re-fusing RMSNorm into QKV (+2.7% worse). The `asyncEval` ladder
placement sweep (exhausted in #4). E2M1 constant-LUT NVFP4 dequant in decode
QMV; runtime-parametrized hot-kernel geometry; NVFP4 attention boundaries
18/19; SDPA `PLANES=2`; router groups < 8; double-buffered gather staging;
int4 lm-head coarse format; prompt/KV memoization of any kind (serial-track
violation).
