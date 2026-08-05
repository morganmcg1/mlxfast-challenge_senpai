# MoE Down Kernel — `outputs_per_simd` 1→2 Analysis

Date: 2026-08-05
Target: `laguna-xs-2.1-serial-v2` decode (NVFP4, M5 Max 128 GB)
Author: advisor research analyst (subagent)

## 1. Kernel location and the `outputs_per_simd` parameter

The **scored** decode MoE down kernel is the fused routed+shared down+residual
kernel, not the standalone routed-down-reduce fallback.

| Item | File:line |
|---|---|
| Kernel def `lagunaRoutedSharedDownResidualKernel` | `Sources/MLXFastModel/LagunaRuntimeModel.swift:7851` |
| **`constexpr uint outputs_per_simd = 1;`** | `Sources/MLXFastModel/LagunaRuntimeModel.swift:7872` |
| Row loop / `simd_sum` | `LagunaRuntimeModel.swift:7911-7923` |
| Cross-expert TG scratch + lane-0 write | `LagunaRuntimeModel.swift:7925-7933` |
| **The single `threadgroup_barrier`** | `LagunaRuntimeModel.swift:7934` |
| Cross-expert weighted-sum epilogue (slot 0, lane<ops) | `LagunaRuntimeModel.swift:7936-7956` |
| Dispatch grid (total threads) | `LagunaRuntimeModel.swift:8029` `grid: (hiddenSize * 288, 1, 1)`, `threadGroup: (288, 1, 1)` (`:8030`) |
| Swift entry `lagunaRoutedSharedDownResidual` | `LagunaRuntimeModel.swift:7962` |
| Scored-path call site (gated by `lagunaFusedRoutedSharedDownResidualEnabled`, default ON) | `LagunaRuntimeModel.swift:10318-10358` |

Geometry constants (`LagunaConfig.swift:17,30-33`): `hiddenSize=2048`,
`numExpertsPerTok=8`, `moeIntermediateSize=512`, `sharedExpertIntermediateSize=512`.

Threadgroup = 288 threads = **9 SIMDs × 32 lanes**. `slot = simdgroup_index_in_threadgroup`
(`:7882`): slots 0–7 = the 8 routed experts, slot 8 (`shared_slot`, `:7871`) = shared expert.
`lane = thread_index_in_simdgroup` (`:7883`): 0–31. `first_row = tile * outputs_per_simd` (`:7884`).

### What `outputs_per_simd` means here
Each SIMD ("slot") computes `result[row]` for `row` in `[0, outputs_per_simd)` by
calling `laguna_nvfp4_qdot_16` over the 512-wide expert activation (32 lanes ×
`values_per_lane=16` = 512), then `simd_sum` across the 32 lanes (`:7918-7922`).
So one tile produces `outputs_per_simd` output rows per expert slot.

### DARKBLOOM flag pattern (precedent)
Kernel-internal numeric/tiling levers in this file are gated by `DARKBLOOM_*`
env flags with a default-on arm and a "set 0/`v1` to restore stock" control,
always with a documented bit-exactness argument. Relevant nearby precedents:
- `DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL` (`:128-130`) — gates this whole kernel (default ON).
- `DARKBLOOM_SHARED_FIRST_DOWN` (`:7848-7849`) — A/B input-order arm of this same kernel; carries a new kernel name because the JIT cache keys signatures by name.
- `DARKBLOOM_NVFP4_QDOT_SEED_ELIDE` (`:6502-6503`) — a qdot internal lever with a closed-form bit-exactness proof and a CPU adversarial test `LagunaNVFP4QdotSeedTests`.
- `DARKBLOOM_NVFP4_NIBBLE_SPLIT` (`:6434-6440`) — multi-arm (0/1/2) control with bit-exactness by construction.

The established pattern for a change here would be: a new `DARKBLOOM_DOWN_OUTPUTS_PER_SIMD`
flag (default ON, "0" restores `=1`), a new kernel **name** (JIT cache keys by
name, cf. `:7852-7854`), and a bit-exactness argument.

## 2. Barrier count: `outputs_per_simd=1` vs projected `=2`

The kernel body has exactly **one** `threadgroup_barrier` (`:7934`), which
separates the per-expert qdot phase from the cross-expert reduce phase. The
barrier count therefore scales with the **number of tiles (threadgroups)** in
the grid, not with rows inside a tile.

MLXFast `grid` is total-threads; threadgroups = grid / threadGroup.
- `outputs_per_simd=1`: tiles = (hiddenSize·288) / 288 = **2048 tiles** → **2048 barrier instances** across the grid (1 barrier/tile).
- `outputs_per_simd=2`: tiles = 2048 / 2 = **1024 tiles** → **1024 barrier instances**.

**Barrier instances halve (2048 → 1024).** Dispatch/command-buffer overhead and
threadgroup-launch count also halve.

### Input reuse
`input_values[16]` (the 512 BF16 expert activation, lane-strided, `:7899-7909`)
is loaded **once per tile** and reused across the `outputs_per_simd` row loop
(`:7912`). With `=1` the 512 activation values fund 1 output row; with `=2` they
fund 2 output rows. **Activation read traffic per output row halves (2× reuse).**
Weight (the dominant, at-theoretical-minimum bandwidth term) is unchanged: each
output row still needs its own 256-byte packed row + 32-byte scale row per
expert, read exactly once.

## 3. Register pressure analysis

Per-thread live registers (dominant terms):
- `input_values[16]` — 16 FP32 regs, held across the row loop (`:7899`).
- `result[outputs_per_simd]` — ops floats: 1 reg (`=1`) / 2 regs (`=2`) (`:7911`).
- Per-row qdot transients (`accum`, `v04/v15/v26/v37` float2s) — transient, reused across iterations.

Decisive evidence: the **sibling shared-down-residual kernel already ships
`outputs_per_simd = 4`** with the identical `laguna_nvfp4_qdot_16` and the same
`values_per_lane = 16` (`lagunaSharedDownResidualKernel`, `:6876`, `outputs_per_simd`
at `:6885`), on the same M5 target. If `=4` fits, `=2` is strictly less register
pressure than an already-shipping kernel.

M5 per-thread: 128 GPRs; per-threadgroup register file 208 KiB. With 288
threads/tg and `=2`, the live footprint (`input_values[16]` + `result[2]` +
transients) is well within budget. **Register pressure is not a concern.**

## 4. Accumulation order / correctness risk — LOW

Trace of one output row `R` (identical for `=1` and `=2` because rows are
independent within a tile):

1. `result[row] = laguna_nvfp4_qdot_16(weight[R], input_values, scale[R])` — FP32 dot over 512 vals (`:7918`).
2. `result[row] = simd_sum(result[row])` — FP32 intra-SIMD tree reduction (`:7922`).
3. lane 0: `down_outputs[slot*ops+row] = bfloat(result[row] * 4194304.0)` — FP32→BF16 round (row-scale suffix, `:7931`).
4. **barrier** (`:7934`).
5. slot 0, `lane<ops`: `routed_total = Σ_{slot=0..7} bfloat(down_outputs[slot*ops+lane] * bfloat(router_weight[slot]))` — BF16 mul+add in slot order 0→7 (`:7938-7948`).
6. `routed = bfloat(routed_total * bfloat(2.5f))` (`:7949-7950`).
7. `shared = down_outputs[shared_slot*ops+lane]` (`:7951-7952`).
8. `r2 = bfloat(routed + shared)` — BF16 add (`:7953`).
9. `output[first_row+lane] = bfloat(residual[first_row+lane] + r2)` — BF16 add (`:7954-7955`).

Why `=2` is bit-exact per row:
- The qdot uses `output_row = first_row + row`, computed **per row** (`:7913-7917`); no cross-row sharing of partial sums.
- The row-scale BF16 round (`:7931`) is per row.
- The routed weighted sum loops over `routed_slot` 0..7 with identical association `(product + routed_total)` and identical **slot order** (`:7938-7948`); the row is selected by `lane`, not by the loop, so the per-row reduction order is unchanged.
- `shared`, `r2`, and the residual add are all per-row, indexed by `first_row + lane`.

So `=2` only batches **two independent output rows into one threadgroup**. The
per-row FP32 accumulation, every BF16 rounding boundary, and the routed-slot
association are all preserved. This is a pure tiling change, directly analogous
to the shipping `=4` sibling.

**Correctness risk: LOW.** The residual subtlety to validate empirically is
that `simd_sum`'s per-lane tree is unaffected by the tile batching (it is —
it is intra-SIMD, independent of rows-per-tile) and that the grid geometry is
updated consistently (below).

### Required edits (minimal, ~2 lines)
- `LagunaRuntimeModel.swift:7872`: `constexpr uint outputs_per_simd = 2;`
- `LagunaRuntimeModel.swift:8029`: `grid: (LagunaConstants.hiddenSize / 2 * 288, 1, 1)` (1024 tiles) — equivalently `hiddenSize * 144`.
- (Per DARKBLOOM convention) new kernel name string + an opt-in flag `DARKBLOOM_DOWN_OUTPUTS_PER_SIMD` so the `=1` stock arm remains as a control.

### Editable-surface budget
`Sources/MLXFastModel` is an `editablePaths` entry in `benchmark.json` (directory),
so `LagunaRuntimeModel.swift` is editable. File is **512,331 B** vs the
**524,288 B** per-file cap → **11,957 B** headroom. A 2-line constexpr/grid
change plus a flag/name string is well under 200 B. No budget risk.

## 5. Experiment design (if viable)

**Hypothesis:** Halving the tile count (2048→1024) for the scored decode
routed+shared down kernel reduces per-step barrier/dispatch overhead and
halves activation-read traffic, improving decode seconds/token, with bit-exact
greedy-token output.

**Scope guard:** `outputs_per_simd` is a `constexpr` inside the kernel source
and the grid total-thread count — both inside `LagunaRuntimeModel.swift`, on the
scored path (`:10348`). Validate with `senpai/validate-assignment-scope.sh` and
`senpai/check-editable-budget.sh` against `BASE_SHA` before building.

**Implementation (student):**
1. Add `DARKBLOOM_DOWN_OUTPUTS_PER_SIMD` flag (default ON, `"0"` restores `=1`),
   mirroring `DARKBLOOM_SHARED_FIRST_DOWN`'s name-suffix pattern (`:7848-7854`).
2. New kernel name e.g. `laguna_routed_shared_nvfp4_down_residual_bf16_r1_v4ops2`
   so the JIT cache does not collide with the `=1` arm.
3. Set `outputs_per_simd = lagunaDownOutputsPerSimdEnabled ? 2 : 1` (constexpr
   must be a literal — emit two source strings or a templated name; simplest is
   two near-identical kernel blocks selected by the flag, as `:7852-7865` already
   does for input order).
4. Grid: `hiddenSize / ops * 288` for the `=2` arm.

**Verification (must pass before timing):**
- `research/run_upstream_equivalence.sh` (vendored oracle; the harness repairs
  the debug metallib placement and refuses a zero-test pass) — this exercises
  numerical behavior / representation / dispatch changes, exactly the categories
  a tiling change touches.
- The public 64-step drift tripwire and a fresh unchanged-base baseline on the
  **same M5** host, same cool-floor window. M4 evidence is directional only and
  does not select `_nax` prefill kernels; this is decode-only so M4 may be used
  for relative A/B *if* baseline and candidate run back-to-back on a quiet host,
  but the official M5 result decides.

**Measurement:** `./benchmark.sh --local-iterate` (scored worker build + timing).
Compare fresh candidate seconds/token vs fresh unchanged baseline, same session.
Decode carries 75% of score weight (`score = decode^0.75 * prefill^0.25`); this
is decode-only, so any decode win compounds at 0.75 and prefill is unaffected
(prefill takes a different branch at `:10397+`).

**Expected magnitude:** The down kernel is at theoretical-minimum **weight**
bandwidth, so the activation-read halving is marginal (weights dominate). The
plausible win is the barrier/dispatch-overhead halving on the decode hot path.
If barrier/dispatch overhead is a small fraction of the weight-bound step time,
the gain may be sub-1%; if threadgroup-launch overhead is non-negligible at
2048 tiles/step across the sparse layers, it could be larger. Measure to find
out — the change is low-risk and cheap to test.

**Risk to watch:** none numerical (per §4). Operational: confirm the `=2` grid
arithmetic exactly covers rows 0..2047 with no OOB write to `output[]`, and
that `lane < outputs_per_simd` (`:7936`) correctly restricts the reduce to
lanes 0..1.
