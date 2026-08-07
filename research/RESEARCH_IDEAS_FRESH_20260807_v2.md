# Fresh Optimization Ideas v2 — 2026-08-07

Ranked list of fresh, untried optimization directions for the Laguna XS 2.1
NVFP4 M5 inference challenge. Generated from deep codebase analysis of the
scored decode/prefill paths, vendor kernel dispatch, MoE memory access
patterns, and prior experiment history.

## Critical Budget Reality (updated for 11-change frontier at 4702eaa)

| Constraint | Current | Limit | Headroom |
|---|---|---|---|
| Total editable surface | ~2,973K B | 3,000,000 B | ~26K B |
| LagunaRuntimeModel.swift | 522,275 B | 524,288 B | **2,013 B** |
| Per-submission growth | — | 262,144 B | — |
| LagunaLmHeadPrune.swift | 43,506 B | 524,288 B | **480,782 B** |
| fp_quantized_nax.h (vendor) | 78,351 B | 524,288 B | **445,937 B** |
| quantized.cpp (vendor) | 83,766 B | 524,288 B | **440,522 B** |
| fp_quantized_nax.cpp (generated) | ~81K B | 524,288 B | **~443K B** |

**LagunaRuntimeModel.swift is the binding constraint at 2,013 B headroom.**
Any idea touching kernel source strings in that file must be very small.
LagunaLmHeadPrune.swift and vendor kernel files have ample headroom.

## Decode Bandwidth Breakdown (calculated)

| Component | Per Layer | × Layers | Total | % of Step |
|---|---|---|---|---|
| Dense MLP (layer 0, BF16) | 96.0 MiB | 1 | 96 MiB | **8.5%** |
| Sparse MoE (NVFP4, 9 experts) | 9.6 MiB | 39 | 374 MiB | 33.0% |
| Attention (INT8 group-32) | 16.5 MiB | 40 | 660 MiB | 58.5% |
| **Total** | — | — | **~1,130 MiB** | 100% |

Attention dominates at 58.5% but uses INT8 (group-32) — no pairwise
constancy, scale halving dead (PR #193: -2.7%). MoE at 33% already has scale
halving applied. Dense MLP at 8.5% is BF16 (no quantization, no scales).

## PR #198 / M5 Submission 0781a45 Failure Analysis

**Commit 0781a45** (9-change frontier at 215e45f) failed on M5 with a
build/runtime error (no score produced). Commit is not in this checkout.

**PR #198 changes** (4 files, all in editable surface):
1. `fp_quantized_nax.h`: Added `kHalvedScales` template param + `escape`
   buffer arg (kernel input 3) to `fp_gather_qmm_rhs_expert_nax` and
   `QuantizedBlockLoader`. New `read_scale(i)` method.
2. `fp_quantized_nax.cpp`: Matching generated twin — verified consistent
   with `.h` (same line-by-line changes).
3. `quantized.cpp`: `halved_scales` detection via
   `scales.shape(-1) == K/(group_size*2)`. Always passes 5 buffers on
   expert path (scales dummy when non-halved).
4. `LagunaRuntimeModel.swift`: Prepare halved fused gate/up scales at init.

**Correctness assessment**: The halving math is bit-exact by design (NVFP4
pairwise-constancy, same invariant as PR #180). The `.h` and generated `.cpp`
twins are consistent. One latent risk: when `fixed_N==0` (non-static shapes),
`up_row_tile` collapses to 0, so up-row-0 never gets its escape → silent
correctness bug. **However**, `DARKBLOOM_STATIC_NVFP4_SHAPES` defaults to ON
(empty string `!= "0"`), so `static_expert_shape` is true on M5 and
`fixed_N > 0`. The escape logic IS correct on M5 with default settings.

**Most plausible M5 failure cause**: The expert kernel now unconditionally
takes 5 buffer args (x, w, scales, escape, indices) instead of 4. When
`expert_aligned && !halved_scales`, the code passes `scales` as the escape
dummy (quantized.cpp:1979). If the Metal JIT rejects the null default
parameter in `QuantizedBlockLoader`'s constructor
(`const device uint8_t* escape_ = nullptr`), or if the kernel template
instantiation fails for the `_hs_0` (non-halved) variant, the build would
fail. **Recommend**: test the `_hs_0` (non-halved) path explicitly — it may
never have been compiled on M5 because the Swift runtime always sends
halved scales when the prefill halving flag is on.

---

## Idea 1: Dense MLP (Layer 0) Threadgroup Geometry Optimization ★★★ HIGHEST

**Priority**: 1 (next assignment)
**Component**: Decode (75% of score) — 8.5% of decode bandwidth
**Mechanism**: The dense MLP (layer 0) uses BF16 weights totaling 96 MiB
(gate/up: 64 MiB, down: 32 MiB) — 10× the bandwidth of a single sparse MoE
layer and 8.5% of total decode bandwidth. This is the single largest
per-layer bandwidth consumer.

The current dense gate/up kernel (`lagunaDenseGateUpSwiGLUKernel`,
LagunaRuntimeModel.swift:7984) uses:
- 512-thread threadgroups (16 simdgroups × 32 lanes)
- `rows_per_thread = 4`, so 64 rows per threadgroup
- 128 threadgroups total (8192 rows / 64)
- `simd_shuffle_down` reduction (delta 16→1, only 16 of 32 lanes
  participate — the other 16 lanes' compute is wasted)
- `block_width = 128`, 16 blocks of 128 elements per row

The `simd_shuffle_down` with delta starting at 16 means only lanes 0-15
contribute to the final sum — lanes 16-31 compute results that are
shuffled away. This is a 2× waste of weight load bandwidth: half the weight
bytes loaded by lanes 16-31 are never used in the final output.

**Fix**: Switch from `simd_shuffle_down` (5-step manual reduction, 16-lane
effective) to `simd_sum` (full 32-lane reduction). This doubles the useful
work per lane, halving the effective weight bandwidth. Each lane would
process `values_per_thread = 4` elements from a 128-element block — the same
FMA count, but the full simdgroup contributes to the result instead of half.

Additionally, increase `rows_per_thread` from 4 to 8 (matching the
sparse MoE kernel pattern at L6658) to amortize input loads over more
output rows. This reduces input-vector reloads by 2×.

**Target code**:
- `Sources/MLXFastModel/LagunaRuntimeModel.swift:7984-8060` (gate/up kernel)
- `Sources/MLXFastModel/LagunaRuntimeModel.swift:8081-8155` (down kernel)

**Expected M5 signal**: The `simd_shuffle_down→simd_sum` change halves the
number of weight loads needed per output element (from 2 lanes computing
redundantly to 1 lane computing productively). Weight traffic drops from
96 MiB to ~48 MiB for the dense layer. At M5 651.8 GB/s: saves ~0.074 ms
per decode step. At ~5.4 ms/step, that's ~1.4% decode gain. Combined with
the `rows_per_thread` increase (input amortization), total ~1.5-2%.

**Bit-exact risk**: LOW. `simd_sum` produces the same result as
`simd_shuffle_down` for the full 32-lane reduction (the shuffle_down with
delta 16→1 only sums 16 lanes; adding the 16-31 lanes' contributions via
`simd_sum` produces the same final value because the FMA accumulation is
the same per-lane, and the cross-lane reduction is a simple sum). The
`rows_per_thread` change only affects tiling, not arithmetic.

**Budget impact**: ~0 bytes net — replacing `simd_shuffle_down` with
`simd_sum` is same-length or shorter. Changing `rows_per_thread = 4` to `8`
requires updating the grid and threadgroup but is ~0 bytes net. **Within
the 2,013 B headroom.**

**M4 testability**: YES. The dense MLP runs on M4. Verify bit-exactness
via `--local-iterate` (max_abs_diff must remain 0) and upstream equivalence.

**Why it's fresh**: The existing RESEARCH_IDEAS file mentions "Dense MoE
layer (layer 0): simd_shuffle_down→simd_sum, scalar FMA→dot(float4)" as a
known idea, but frames it as instruction-count reduction. The KEY insight
here is that `simd_shuffle_down` with delta=16 **wastes 50% of loaded
weight bandwidth** — lanes 16-31 load weights and compute FMAs that are
discarded by the 16-step shuffle. This is a BANDWIDTH reduction, not an
instruction-count reduction. The 96 MiB of dense layer weight traffic is
effectively doubled to ~192 MiB by the wasted lanes, and fixing it
recovers ~96 MiB of bandwidth — the largest single bandwidth saving
available.

---

## Idea 2: Input-Vector Staging to Threadgroup Shared Memory in Decode MoE Kernels ★★☆ MEDIUM-HIGH

**Priority**: 2
**Component**: Decode (75% of score)
**Mechanism**: The routed expert gate/up QMV kernel
(`lagunaRoutedSwiGLUQMVPackedTop8R1Kernel`, L7458) re-reads the 2048-element
BF16 input vector (4096 bytes) from device memory once per block (4 blocks
of 512) per threadgroup. With grid = 8 experts × 256 tiles × 64 threads =
2048 threadgroups, this generates 2048 × 4 = 8192 device-load operations for
the input vector per layer. While the input is an L1/L2 cache hit after the
first load, the 8192 device-load instructions consume LSU throughput that
competes with weight loads.

On the bandwidth-bound M5, the LSU is the bottleneck for issuing memory
transactions. Cache-hit loads still consume LSU instruction slots, delaying
weight loads. Staging the input into threadgroup shared memory once at
kernel start and reading from shared memory in the block loop eliminates
3 of 4 device-load sequences per threadgroup, reducing LSU pressure.

The shared kernel (`lagunaSharedSwiGLUQMVRows1Kernel`, L6737) has the same
pattern with 256 threadgroups.

**Fix**: At kernel start, cooperatively load the 2048-element input (4096
bytes) into threadgroup shared memory. 64 threads × 16 values = 1024 values
per round, 2 rounds for 2048. Then in the block loop, read from
`threadgroup float*` instead of `device` pointer.

Threadgroup memory cost: 4096 bytes per threadgroup. Current decode kernels
use NO threadgroup memory for weights (all in registers). 4096 bytes is well
within the 32 KB threadgroup memory limit.

**Target code**:
- `Sources/MLXFastModel/LagunaRuntimeModel.swift:7458-7610` (routed Top8 R1)
- `Sources/MLXFastModel/LagunaRuntimeModel.swift:6737-6815` (shared R1)

**Expected M5 signal**: Reduces ~6144 device-load instructions per
threadgroup (3 of 4 blocks × 2048 values/2048 elements) to ~1024 shared-
memory loads. Net: -5120 device loads × 2048 threadgroups × 39 layers =
~411M fewer device-load instructions per decode step. On M5 where LSU
throughput limits bandwidth utilization, freeing LSU capacity for weight
loads could improve throughput by ~0.5-1.5%.

**Bit-exact risk**: LOW. The input values are the same bytes loaded from
the same addresses, just staged through shared memory. No arithmetic
change. The `float4(input_vectors[i])` conversion is identical whether
reading from device or shared memory.

**Budget impact**: ~15-20 lines of Metal source per kernel × 2 kernels =
~600-800 B. **Exceeds the 2,013 B headroom if both kernels are modified
simultaneously.** Must do one kernel at a time (~300-400 B each), or find
code to compress elsewhere in LRM. Alternatively, the shared kernel
modification is ~300 B and can fit.

**M4 testability**: YES. Both kernels run on M4. Verify via
`--local-iterate` (max_abs_diff = 0).

**Why it's fresh**: No PR has attempted threadgroup staging of the input
vector in the decode MoE kernels. Prior work focused on weight staging
(PR #116, #128) and scale halving (PR #180). The input vector reload has
been noted in bandwidth audits but never addressed because it was assumed
to be a "free" cache hit. The M5 bandwidth-bound insight reframes it as
LSU pressure that delays weight loads.

---

## Idea 3: Fold Shared Expert Gate/Up QMV into Routed Gate/Up Dispatch ★★☆ MEDIUM-HIGH

**Priority**: 3
**Component**: Decode (75% of score)
**Mechanism**: The shared expert's gate/up SwiGLU QMV runs as a SEPARATE
dispatch per sparse layer because `mergedSharedActivated` (L10185) is
declared but never assigned non-nil. The shared QMV is issued inside
`fusedSharedDownInputs` (L8334) when `sharedActivation` is nil, producing
one extra GPU dispatch per sparse layer × 39 layers = 39 extra dispatches
per decode step.

The routed gate/up Top8 kernel (`lagunaRoutedSwiGLUQMVPackedTop8R1Kernel`)
already processes 8 expert slots. Extending it to 9 slots (8 routed + 1
shared) eliminates the separate shared QMV dispatch. The shared expert
has the same architecture (fused gate/up, same intermediate size 512, same
input x), so it fits naturally as a 9th slot.

**Fix**: Add the shared expert's fused weight bank and halved scales as
additional kernel inputs. Extend the kernel to process slot 8 as the
shared expert (same weight layout, same scale halving with escape). The
router weight for slot 8 is the shared expert's scaling factor (applied
in the down+residual kernel, not the gate/up kernel).

**Target code**:
- `Sources/MLXFastModel/LagunaRuntimeModel.swift:7458-7610` (kernel source)
- `Sources/MLXFastModel/LagunaRuntimeModel.swift:10185-10270` (dispatch)

**Expected M5 signal**: Eliminates 39 dispatches per decode step. Each
dispatch has ~3-5 μs overhead. If the GPU is idle between the routed gate/up
and shared gate/up dispatches (they're on the critical path — the
down+residual kernel needs both), this saves ~117-195 μs per decode step.
At ~5400 μs/step, that's ~2.2-3.6%. However, if asyncEval overlaps the
shared QMV with the routed QMV (both use the same input x), the saving is
just the dispatch overhead (~0.2-0.4%).

Additionally, the shared expert's input x is already L1/L2-resident from
the routed kernel's load, so the shared QMV's input loads are cache hits.
Fusing eliminates even the cache-hit load instructions for the shared QMV's
input.

**Bit-exact risk**: LOW. The shared expert's gate/up computation is
identical to a routed expert's — same SwiGLU, same NVFP4 dequantization,
same scale halving. The only difference is the weight bank and scale bank.
Adding a 9th slot with its own weight/scale pointers produces the same
result as the separate dispatch.

**Budget impact**: ~20-30 lines of kernel source modification (add shared
weight/scale/escape as inputs, add slot 8 processing) + ~10 lines of
dispatch modification = ~1200-2000 B. **Very tight against the 2,013 B
headroom.** Must be extremely compact or combined with other changes that
reduce code size. Risk of exceeding budget.

**M4 testability**: YES. The shared expert runs on M4. Verify via
`--local-iterate` (max_abs_diff = 0) and upstream equivalence.

**Why it's fresh**: The `mergedSharedActivated` dead-code path (L10185) has
been noted in the decode audit but never fixed. The dispatch-path agent
confirmed it's never assigned non-nil. No PR has attempted to fold the
shared gate/up into the routed dispatch. The dead code comment at L10181-
10184 anticipates this fusion but no code implements it.

---

## Idea 4: DARKBLOOM_EXPERT_GATHER_GROUPS Sweep (Prefill, 0-byte) ★☆☆ LOW-MEDIUM

**Priority**: 4
**Component**: Prefill (25% of score)
**Mechanism**: The prefill MoE gather-QMM kernel
(`fp_gather_qmm_rhs_expert_nax`) spreads 256 experts over `egroups`
threadgroups (default 128, meaning 2 experts per threadgroup). The
`DARKBLOOM_EXPERT_GATHER_GROUPS` env var controls this (quantized.cpp:1379).
Value 64 was the old default (4 experts per TG); 128 is the promoted
default. Values 256 (1 expert per TG) and 32 (8 experts per TG) are
untested.

Fewer experts per threadgroup (256) means each threadgroup processes one
expert's full output, potentially improving L2 reuse of the input x
fragments (loaded once per k-tile instead of once per expert within the
TG). More experts per threadgroup (32) means more input reuse across
experts in the same TG, but less parallelism (fewer TGs).

**Fix**: Pure env var change — `DARKBLOOM_EXPERT_GATHER_GROUPS=256` or `=32`.
0 bytes of code change. Must be tested on M5 only (M4 doesn't compile the
`_nax` expert kernel).

**Target code**: None — pure env var.

**Expected M5 signal**: Unknown. The kernel comment says each setting
compiles exactly one pipeline. The egroups=128 setting was promoted from
64, suggesting more threadgroups (fewer experts/TG) was better. egroups=256
extends this trend. Expected ~0-2% prefill kernel gain if L2 reuse improves.

**Bit-exact risk**: LOW. The routing result and computation are identical
— only the threadgroup tiling changes. Same experts, same weights, same
accumulation order within each expert.

**Budget impact**: 0 bytes. Pure env var.

**M4 testability**: NO. M4 Pro (gen 16 < 17) never compiles the `_nax`
expert kernel. Must submit directly to M5.

**Why it's fresh**: Only 64 and 128 have been tested. 256 and 32 are
untried. The comment at L1365 says "64 restores the promoted" (old default).
The sweep is free (0-byte) and can be combined with any M5 submission.

---

## Idea 5: Prefill Expert Kernel `_hs_0` (Non-Halved) Path Verification and Fix ★☆☆ MEDIUM

**Priority**: 5
**Component**: Prefill (25% of score) — correctness/safety
**Mechanism**: PR #198 added `kHalvedScales` as a template parameter to
`fp_gather_qmm_rhs_expert_nax`, creating two kernel variants: `_hs_1`
(halved) and `_hs_0` (non-halved). The `_hs_0` variant is compiled when
`halved_scales` is false (quantized.cpp:1726), but it still takes the
`escape` buffer argument (kernel input 3).

When `expert_aligned && !halved_scales`, the dispatch passes `scales` as
the escape dummy (quantized.cpp:1979):
```cpp
compute_encoder.set_input_array(scales, c++);
```
This passes the scales pointer where the kernel expects `escape`. When
`kHalvedScales` is false, the kernel's `read_scale()` method ignores
`escape` entirely (returns `scales[i]`), so the dummy is never read. This
is safe in principle, but:

1. **The `_hs_0` path may never have been compiled on M5** because the
   Swift runtime always sends halved scales when
   `DARKBLOOM_PREFILL_FUSED_GATE_UP_HALVED` is on (default). If the
   `_hs_0` template instantiation has a compile error (e.g., the
   `escape_ = nullptr` default parameter in `QuantizedBlockLoader`'s
   constructor is rejected by the Metal JIT), it would fail at runtime
   when the halved flag is OFF.

2. **The M5 submission 0781a45 failure** (build/runtime error, no score)
   may have been caused by this: if any layer's prefill MoE dispatch
   encountered non-halved scales (e.g., during the 512-token seed prefill
   where shapes differ), the `_hs_0` kernel would be JIT-compiled and
   could fail.

**Fix**: Verify the `_hs_0` path compiles on M5 by temporarily disabling
halving (`DARKBLOOM_PREFILL_FUSED_GATE_UP_HALVED=0`). If it fails, fix the
`QuantizedBlockLoader` constructor to not use a default `nullptr` parameter
(Metal JIT may reject default parameters on device pointers). Instead,
always pass the escape pointer explicitly from the kernel function body.

**Target code**:
- `Vendor/mlx-swift/.../fp_quantized_nax.h:249-250` (constructor default params)
- `Vendor/mlx-swift/.../fp_quantized_nax.cpp:394-396` (twin)
- `Vendor/mlx-swift/.../quantized.cpp:1975-1980` (dispatch)

**Expected M5 signal**: Not a speed optimization — a correctness/safety fix
that prevents build failures. If 0781a45 failed due to this, fixing it
unblocks the 11-change frontier for M5 submission.

**Bit-exact risk**: N/A (fixes a build failure, no numerical change).

**Budget impact**: ~50-100 B (remove default params, add explicit pass).
Within vendor file headroom (445K B in fp_quantized_nax.h).

**M4 testability**: NO. `_nax` expert kernel never compiles on M4.

**Why it's fresh**: No one has verified the `_hs_0` path compiles on M5.
The M5 submission failure at 0781a45 may be caused by this. This is a
prerequisite for safe M5 submission of the prefill MoE scale halving.

---

## Summary: Priority Ranking for Next Assignments

| # | Idea | Component | M5 Signal | Bit-Exact | Budget | M4? | Priority |
|---|---|---|---|---|---|---|---|
| 1 | Dense MLP threadgroup geometry (simd_sum) | Decode 8.5% | ~1.5-2% | LOW | ~0 B LRM | YES | **1 — ASSIGN NEXT** |
| 2 | Input-vector staging to TG shared mem | Decode 75% | ~0.5-1.5% | LOW | ~300-800 B LRM | YES | **2** |
| 3 | Fold shared gate/up into routed dispatch | Decode 75% | ~0.2-3.6% | LOW | ~1200-2000 B LRM | YES | **3** (budget-tight) |
| 4 | EXPERT_GATHER_GROUPS sweep (prefill) | Prefill 25% | ~0-2% | LOW | 0 B | NO | **4** (free) |
| 5 | `_hs_0` path verification/fix | Prefill 25% | Safety fix | N/A | ~50-100 B vendor | NO | **5** (prerequisite) |

**Key recommendations**:

1. **Assign Idea 1 (Dense MLP simd_sum) immediately** — it's the largest
   bandwidth saving available (96 MiB → ~48 MiB effective), costs ~0 bytes
   in the tight LRM budget, is bit-exact, and is M4-testable. The
   `simd_shuffle_down` with delta=16 wastes 50% of loaded weight bandwidth
   because only lanes 0-15 contribute to the result.

2. **Assign Idea 5 (_hs_0 verification) as a prerequisite** — if the M5
   submission 0781a45 failed due to the `_hs_0` path, fixing it unblocks the
   entire 11-change frontier. Test by disabling halving and checking if the
   non-halved expert kernel compiles on M5.

3. **Idea 4 (EXPERT_GATHER_GROUPS sweep) is free** — include with any M5
   submission. 0-byte cost, no M4 testability, but safe to sweep.

4. **Ideas 2 and 3 are budget-constrained** — LRM has only 2,013 B
   headroom. Idea 2 (input staging) is ~300-400 B per kernel. Idea 3
   (shared fusion) is ~1200-2000 B. Do Idea 2 first (smaller, lower risk),
   then Idea 3 if budget allows.

---

## What Was Ruled Out (and why)

- **Transform-time layout changes**: The transform (`Transform.swift`) is
  contractually a byte-identical pass-through. The runtime enforces exact
  912-tensor + dtype-count validation. No transform-time reordering is
  viable. All bandwidth-reducing layout optimizations already happen at
  runtime load time in `prepareFusedRuntimeWeights()`.

- **DARKBLOOM_STAGE_RUNBAR + NOVOL**: These function constants (fc 206, 207)
  only reach the NON-expert `fp_gather_qmm_rhs_nax` kernel, not the
  expert-aligned path that M5 uses by default. Flipping them measures their
  own control (the expert kernel never sees them). Irrelevant for the
  scored M5 path.

- **DARKBLOOM_GATHER_XMAJOR**: Dead — kernel arms removed, function pinned
  to return 0. Was designed to fold adjacent column tiles to reuse input x,
  but was abandoned.

- **Attention K/V packing**: Interleaving K and V in the KV cache would not
  help because SDPA loads all K first (QK^T phase) then all V (AV phase).
  Interleaving would evict useful data during each phase.

- **Expert weight L2 reuse across threadgroups**: Each threadgroup reads
  unique weight rows (no data sharing). L2 caching doesn't help for expert
  weight reads because each row is accessed by exactly one threadgroup.

- **Scale load vectorization (decode kernels)**: Scale bytes are already
  coalesced (32 contiguous bytes per row = one transaction). Scale traffic
  is 1/8 of weight traffic and already halved. Further optimization is
  marginal.

- **RUNSKIP pct change**: Already at P=100 (full elision). The shipped
  default `kDarkbloomDefaultRunSkipPct = 100` provides maximum elision.
  No further gain available.

- **Dense MLP dot(float4) vectorization**: Listed in prior ideas as an
  instruction-count optimization. On M5 (bandwidth-bound), the key insight
  is not the instruction count but the wasted bandwidth from
  `simd_shuffle_down` (Idea 1 covers this). The `dot(float4)` change is
  orthogonal and can be combined, but the bandwidth saving from `simd_sum`
  is the primary lever.

- **Non-expert prefill kernel optimization**: The non-expert
  `fp_gather_qmm_rhs_nax` path is not used on M5 (the expert-aligned path
  is the default). Optimizing it would not affect scored timing.

- **Prefill shared expert down halving**: Shared expert is 1 of 257
  experts. Its down scale traffic is ~2.5 MiB prefill. Halving saves
  ~1.25 MiB. At 651.8 GB/s: ~1.9 μs. Negligible vs ~25-30 ms prefill.
