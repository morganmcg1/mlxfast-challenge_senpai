# SENPAI Research State

- 2026-08-04 03:00 UTC — advisor `meridian`, campaign `mlxfast-maple-20260804`
- Human research direction: four students, four distinct causal arms, all four
  authorized to dispatch official MLXFast submissions from the AWS Macs.
  `BASE_SHA=768bb9d4adfc2baac7d74c0008afc92d010329da`, organizer frontier
  `ORGANIZER_FRONTIER_SHA=afcb8320912aa1162f841f282442d7c093e6b2e5`. Keep the
  campaign isolated from parallel research branches.

## Where the frontier stands

Public frontier (rank 126, organizer commit `7702fab`): **score 2.4550**,
decode **5.249 ms/token** (2.6466x), prefill **0.1957 ms/token** (1.9593x).
126 promotions by 30 solvers took the board from 1.004 to 2.455 in ~9 days.

Attribution of those 126 promotions: 98 touched
`Sources/MLXFastModel/LagunaRuntimeModel.swift`, 44 touched a vendored
`mlx-swift` kernel, 20 touched `LagunaLmHeadPrune.swift`, and **0 touched
`Sources/MLXFastTransform/`**.

## Current research focus: the non-bandwidth 35-45% of decode

The campaign thesis, derived from `fixtures/poolside_laguna_xs_2_1_nvfp4_config.json`
and the shipped representation defaults (Q/K/V/O native NVFP4 group-16 on all
40 layers, `DARKBLOOM_NATIVE_AFFINE_NVFP4_FROM` default `0`; `g_proj` group-32
INT8):

| Component | Bytes / decode token |
| --- | ---: |
| Attention Q/K/V | 448 MB |
| Attention O | 353 MB |
| MoE routed 8/256 + shared + router, 39 layers | 632 MB |
| Dense layer-0 MLP | 28 MB |
| lm_head certified coarse screen | ~140 MB |
| KV cache (85 MiB resident, up to 315 MiB requested) | 89-330 MB |
| **Total** | **~1.65-1.9 GB** |

Verified host peaks (Apple product/support specs, 3 Mar 2026): the ranked host
is an M5 Max with 128 GB, which is the full-die part at **614.4 GB/s** (the
binned 32-core-GPU M5 Max is 460.8 GB/s but ships with 36 GB, so the 128 GB
ranked host must be the full die). Student hosts are M4 Pro / 48 GB at
**273 GB/s**.

| | value |
| --- | ---: |
| Decode byte budget | 1.65-1.9 GB/token |
| Official M5 Max achieved at frontier | 314-362 GB/s |
| Official M5 Max peak | 614.4 GB/s |
| **Fraction of peak** | **51-59%** |
| M5 Max DRAM floor at 1.65 GB/token | 2.69 ms/token |
| M5 Max actual at frontier | 5.249 ms/token |

So **41-49% of frontier decode wall time is not DRAM traffic**, and with ~324
kernel dispatches per decode step that is ~6-8 us per dispatch of non-bandwidth
time. A perfectly bandwidth-bound decode on the official host would be nearly
**2x** faster than the current frontier — a far larger remaining ceiling than
126 landed promotions would suggest.

The M4 Pro DRAM floor is 1.65 GB / 273 GB/s = 6.04 ms/token. If student
baselines land near 9.5-11 ms/token they are at ~55-65% of peak, i.e. **the
same fraction of peak as the M5 despite a 2.25x difference in peak**. Two hosts
at the same fraction of very different peaks is strong evidence the shared
limiter is machine-independent overhead — dispatch count, launch latency,
dependency serialization, host graph construction — rather than DRAM. This is
the falsifiable prediction PR #7 must check first; if a student baseline lands
materially outside that band, the byte budget is wrong and three arms need
re-scoping.

Consequence for the byte-cut arms (#5, #6): because neither host is
bandwidth-saturated, a byte reduction converts to wall-clock time
**sub-proportionally**. The byte fraction is an upper bound on an upper bound,
not an expected gain. Conversely, removing serial *dispatches* — especially in
the lm_head epilogue, which has nothing left to overlap against — is close to
fully realised.

The 126 published promotions were overwhelmingly *byte* reductions
(representation, certified pruning, residency wiring). The non-bandwidth
fraction has never been attacked systematically. That is this campaign's thesis
and it is unproven — `maple-nezuko`'s arm exists to turn the derivation into a
measurement.

Every large byte line except KV is now at its representation floor and read
exactly once. The accepted quantization envelope (group-32 affine INT8 for
Q/K/V/O and per-head `g_proj` only) is fully spent.

## Arms in flight

| PR | Student | Arm | Ceiling | Key risk |
| --- | --- | --- | --- | --- |
| #4 | maple-frieren | Decode non-bandwidth overhead: `MLX_MAX_OPS_PER_BUFFER` retune (currently 200 vs ~324 dispatches/step, so every step is split mid-stream), `asyncEval` ladder placement, per-step host waste (unconditional `NSLock`+String hash per sparse layer, thousands of `MLXArray.shape` heap allocations, duplicate `dim(1)` FFI calls, full-attention params atlas) | 1-5% decode | M4 Pro is nearer its bandwidth roof than M5, so a null end-to-end result may be a false negative; must measure GPU-busy vs wall time directly |
| #5 | maple-fern | Fused decode attention: one threadgroup owns a whole GQA KV group (8 sliding / 6 full) instead of 2 heads, removing the 3-4x KV re-request | up to 12-14% decode if KV is DRAM-bound | the ~2 MiB per-layer KV working set may be SLC-absorbed, making the whole line a no-op; and >5% must be split for the acceptance band |
| #6 | maple-tanjiro | Hierarchical certified LM-head screen: a rigorous block-level upper bound prunes row blocks before the existing planar coarse pass reads them | 1-3% decode | the recorded failure mode of this family is a p99 exact-tail blowup on unseen prompts |
| #7 | maple-nezuko | Decode roofline: measured per-dispatch time budget and achieved bandwidth; plus resident-footprint reduction (est. 35-38 GB resident vs a 21.6 GB checkpoint, on 48 GiB hosts) | measurement is the deliverable | footprint win may be a 48 GiB low-memory artifact that does not transfer to a 128 GB M5 |

## Hard constraints carried into this campaign

- Two-sided acceptance band against the pinned calibration reference caps a
  single accepted submission near **+5.3%**. Split large mechanisms along
  natural, independently correct boundaries. Never add a throttle or a
  benchmark-dependent switch to fit the band.
- Published speedups use the same-session paired baseline, so a headline delta
  can exceed the band. Session-to-session baseline drift is 1.47% decode /
  5.13% prefill — always record candidate decode, candidate prefill, and the
  same-session baseline for each.
- Score weighting makes 1% decode worth ~3x 1% prefill. Prefill kernel geometry
  is additionally a poor M4 arm because M4 does not select the `_nax` variants
  the M5 runs.
- M4 is a decent proxy for representation, byte, and dependency-graph changes;
  unreliable for occupancy, kernel geometry, SIMD ownership, and anything under
  ~1%. Student hosts are M4 Pro / 48 GB at 273 GB/s. Both M4 Pro and the M5 Max
  appear to sit at ~55-60% of their respective peaks, so neither is
  bandwidth-saturated and the M4 Pro is a better proxy for overhead work than I
  first assumed.
- Correctness boundaries are discrete and nonmonotonic; `max_abs_diff=0` in a
  layer trace can still flip a final argmax.
- Changed JIT kernels need fresh pipeline names (MLX's cache is name-keyed).
  AOT sources (RoPE, RMSNorm, `sdpa_vector`, `arg_reduce`) need
  `tools/build-mlx-metallib.sh`.
- The local quality panel is an amber drift alarm, not a submission veto: no
  monotone threshold separates accepted from rejected official entries.
- `Sources/MLXFastTransform/` looks like open space but is **not** a speed
  surface: the runtime copies every tensor out of the artifact into MLX-owned
  memory at load, so any offline layout is isomorphic to load-time preparation
  that already happens and is already unscored. A transform change also forces
  a full 21.6 GB weights regeneration.

## Potential next research directions

1. **Dispatch-count reduction (not dispatch-cost).** If `maple-nezuko`'s
   timeline shows a large launch-gap residual, the next tier is fusing
   dispatches that do not duplicate producer work. Note the two recorded
   negatives: fused norm+QKV+gate lost because it repeated a 2048-wide RMS
   reduction per output tile (+0.056 to un-fuse), and merging routed with
   shared gate/up lost because independent kernels overlap better (+0.010 to
   un-merge). The open question is whether `o_proj` -> residual -> RMSNorm ->
   router can be fused without a cross-threadgroup reduction.
2. **Graph-valued ring/cache index plus compiled multi-layer decode segments.**
   The prior campaign's P0 and highest published ceiling. Infrastructure
   already exists and is unused: `CompiledDecode.swift:125/168`,
   `CompilableKVCache.swift`, `CompilableRotatingKVCache.swift`,
   `DynamicSlice.swift`, `RoPEApplication.swift:27`. Blockers:
   `decodeRoPEAtlasPosition` rejects compilable subclasses by exact
   `type(of:)`, and the fused attention paths downcast to concrete cache types.
   Deliberately **not** assigned this round because it collides with PR #4's
   files; hold until #4 is terminal.
3. **Per-kernel roofline gaps in MoE.** Routed gate/up QMV is 9.4 MB per sparse
   layer and routed+shared down is 5.3 MB — 632 MB/token total with no byte
   lever left, so any win must come from achieved bandwidth. Waiting on #7's
   per-dispatch table.
4. **Full-attention kernel shape.** The full fused kernel uses a runtime-length
   loop with a single-row tail versus sliding's compile-time-constant 512-slot
   ring, so it gets less unrolling; and full skips fusion entirely on decode
   step 1.
5. **Cooperative KV-head retiling as a latency play.** If #5 shows KV is
   cache-absorbed, the fused attention dispatch is latency-bound, and the
   interesting question becomes occupancy and reduction depth rather than bytes.
6. **Source-budget reclamation.** The prior campaign reported the launch budget
   within kilobytes of its cap with ~60 dormant `DARKBLOOM_*` selectors
   present. Dormant default-off code still costs registers across the whole
   PSO. This is housekeeping that may unblock a new kernel family.

## Explicitly not to re-attempt

E2M1 constant-LUT NVFP4 dequant in decode QMV; runtime-parametrized hot-kernel
geometry; NVFP4 attention boundaries 18/19; SDPA `PLANES=2`; router groups < 8;
double-buffered gather staging; int4 lm-head coarse format; the historical
KV-write path; prompt/KV memoization of any kind (serial-track violation).
