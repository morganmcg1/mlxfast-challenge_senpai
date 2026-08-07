# PR #300 — Can a 64-thread threadgroup reproduce MLX's 512-lane `rms_bf16` reduction tree?

Student: `maple-fern` · branch `maple-fern/redundant-rmsnorm-tree` ·
base `69178729b154cbb648ea0ce6152e92dbfdb17cc6`
(`codex/mlxfast-maple-20260804-advisor`)

**Verdict: H1 SUPPORTED, and the question is already settled in the shipped
tree.** A 64-thread threadgroup reproduces the 512-lane FP32 reduction
bit-for-bit, this virtualised form *already runs in the scored decode path*,
and it has already passed ranked M5 correctness. Bit-exactness therefore
cannot be the reason PR #48's 2-rows/TG variant lost 0.1488%. Stage 2 shows
why: once realistic weight streaming is present, the redundant reduction is
statistically free, and the 8-rows/TG geometry is an occupancy/register
decision, not a numerics one.

Host for every measurement below: Apple M4 Pro, 48 GiB, macOS 26.5.2, Apple
GPU generation 16. All timings are directional only — no ranked submission was
made this round (the ranked pipeline has been down since 2026-08-07 09:59 UTC).

---

## Stage 0 — the reference reduction tree

The scored decode RMSNorm is `laguna_residual_rms_bf16_2048_v1`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:1014-1052`), dispatched at
512 threads per row (`:1156-1157`) with the shared reduction tail
`lagunaNormReductionTail(...)` (`:762-791`) and scratch `:756`.

Native geometry: `axis_size = 2048`, `n_reads = 4`, `simd_size = 32`,
`norm_threads = axis_size / n_reads = 512`, i.e. **16 simdgroups**.

The tree is:

1. Thread `t` (`0 <= t < 512`) reads the contiguous quad
   `residual[4t .. 4t+3]`, converts each `bfloat` to `float`, and accumulates
   `acc_t = sum_i x_i^2` in FP32 **in index order**.
2. `simd_sum(acc_t)` reduces 32 lanes inside each simdgroup. Metal's
   `simd_sum` is a fixed shuffle tree, so its result depends only on the
   *set of lanes* and their *lane index*, not on the enclosing threadgroup
   size.
3. Lane 0 of simdgroup `k` writes `local_sums[k]`, `k in [0,16)`.
4. Simdgroup 0 does `simd_sum(local_sums[simd_lid])` over the 32 slots (16
   live, 16 pre-zeroed) and computes
   `precise::rsqrt(total / 2048 + 1e-6f)`.

The load-bearing invariants are therefore only: (a) each thread squares its
own contiguous four elements in index order; (b) the partial for logical
simdgroup `k` lands in `local_sums[k]`; (c) the final 32-slot `simd_sum` sees
the same 32 values in the same slots. Nothing in that list mentions how many
*physical* threads the threadgroup has.

The in-file warning at `:1071-1078` ("The 512-thread threadgroup and
`n_reads == 4` are NOT knobs … moving either regroups the FP32 RMS summation
and forfeits bit-exactness") is correct about *regrouping*, but a 64-thread
threadgroup that virtualises 512 logical lanes does not regroup anything.

## Stage 1 — bit-comparison of the 64-thread virtualised tree

### 1a. The escape hatch already ships

`lagunaNormAffineQKVBody` (`:4910-5012`, prologue `:4937-4966`) already runs
exactly this reduction on **64 physical threads**:

```
constexpr uint norm_threads       = axis_size / n_reads;   // 512   :4917
constexpr uint real_threads       = 64;                    //       :4918
constexpr uint virtual_per_thread = norm_threads / real_threads; // 8 :4919
constexpr uint num_simdgroups     = 2;                     //       :4925
...
for (uint j = 0; j < virtual_per_thread; ++j) {            //       :4944
    uint base = (lid + j * real_threads) * n_reads;        //       :4945
    ... acc = simd_sum(acc);
    if (simd_lid == 0) local_sums[simd_gid + num_simdgroups * j] = acc; // :4953
}
```

Proof by index algebra that this is the same tree:

* Physical thread `lid in [0,64)`, iteration `j in [0,8)` handles logical lane
  `t = lid + 64j`, so `base = 4t` — identical quads, identical index order,
  identical FP32 `acc_t`. (b) of Stage 0 holds elementwise.
* Physical simdgroup `g = lid / 32 in {0,1}`, physical lane `l = lid % 32`.
  The `simd_sum` at iteration `j` therefore sums over logical lanes
  `{32(2j+g) + l : l in [0,32)}` — exactly logical simdgroup `k = 2j + g`,
  with logical lane `l` sitting at physical lane index `l`. Same lanes, same
  lane indices, same shuffle tree.
* Slot written is `simd_gid + num_simdgroups * j = g + 2j = k`. Same slot as
  the 512-thread kernel.
* `j` sweeps `[0,8)` and `g` sweeps `{0,1}`, so `k = 2j+g` sweeps `[0,16)`
  exactly once. All 16 live slots are filled, the other 16 stay pre-zeroed,
  and the final 32-slot `simd_sum` sees an identical array.

So the answer to the assignment's question is *yes by construction*, and it is
not hypothetical: this kernel is the default decode QKV path
(`DARKBLOOM_FUSED_NORM_AFFINE_QKV`, `:5295-5296`), it is what runs on the
ranked M5, and the in-file comment at `:5290-5292` already calls it
"Bit-exact (inline variant re-derives normalized values from L1-resident rows
with no occupancy cost)".

### 1b. Empirical bit-comparison

`research/fern_redundant_rmsnorm_bitwise.swift` is a standalone
Swift + Metal probe (no MLX build needed):

```bash
swiftc -O research/fern_redundant_rmsnorm_bitwise.swift \
  -o /tmp/fern_rmsnorm_bitwise -framework Metal -framework Foundation
/tmp/fern_rmsnorm_bitwise [real_rows.bin]
```

It compiles three kernels into one library with fast math disabled — matching
MLX's JIT
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:631`,
`setFastMathEnabled(false)`):

| kernel | geometry | role |
| --- | --- | --- |
| `tree_a_512` | 512 threads, 16 simdgroups | native control, verbatim from `:1014-1052` |
| `tree_b_64` | 64 threads, `virtual_per_thread = 8` | verbatim from the shipped `:4944-4966` |
| `tree_b_64_fault` | same as B plus `+1.0f` at `j==3 && lid==5` | comparator liveness control |

Comparison is exact `uint32` equality on the raw FP32 `acc` *and* on
`precise::rsqrt(acc/2048 + 1e-6)`, plus a ULP distance. A/B/A/B-fault run
interleaved in one Metal session against one shared input buffer, so a
scheduling or residency difference cannot masquerade as agreement.

Synthetic rows are SplitMix64-deterministic (seed `0x5EED1234ABCD0001`) and
deliberately adversarial for FP32 summation order: `gaussian-realistic`,
`wide-dynamic-range`, `cancellation-signs`, `bf16-denormals`, `signed-zeros`,
`all-equal`, `one-huge-among-tiny`, `overflow-to-inf`,
`mixed-magnitude-blocks`, `near-eps-rms`.

**Result** (`research/redundant-rmsnorm-logs/stage1-synthetic.log`),
1088 rows across 10 classes:

* clean arm: **0 acc mismatches, 0 rsqrt mismatches, worst ULP 0 in every
  class**;
* fault arm: **492 / 1088 acc mismatches and 487 rsqrt mismatches**, worst acc
  ULP 1 065 353 216 — the comparator can and does fail when the tree is
  perturbed by a single `+1.0f` in one lane of one virtual iteration;
* exit 0, `RESULT: H1 SUPPORTED`.

Note which classes the fault arm did *not* break (`wide-dynamic-range`,
`one-huge-among-tiny`, `overflow-to-inf`, `mixed-magnitude-blocks`): those are
rows where a `+1.0f` perturbation is absorbed by FP32 rounding or by an
already-infinite total. That is the expected behaviour of the control and is
why the clean arm needs the *other* six classes to be meaningful.

### 1c. Real decode rows

Synthetic rows are adversarial but they are not the distribution the kernel
actually sees, so the probe was rerun against **real** residual-stream rows
captured from a live decode.

`research/fern_hidden_dump.patch` adds a research-only hook to
`Sources/MLXFastModel/LagunaRuntimeModel.swift` that appends `outputs[0]` of
`lagunaResidualRMSNormRouter` / `lagunaResidualRMSNorm` — exactly the bf16
vector whose squares the 2048-wide reduction accumulates — to a file, capped at
512 rows and shape-gated to `summed.size == LagunaConstants.hiddenSize` so only
one-token decode rows are recorded. bf16 → Float32 is exact, so the top 16 bits
of each `Float32.bitPattern` round-trip the original bf16 pattern with no
re-rounding. **The patch is carried as a file and is not applied in the
submitted tree** (`git diff` against `BASE_SHA` over `Sources/` and `Vendor/`
is empty).

Two harness details cost real time and are worth recording:

* the runtime worker's environment is a **strict allowlist**
  (`Sources/MLXFastTrustedHarness/LagunaRuntimeWorker.swift:1936-2020`,
  `sanitizedRuntimeWorkerEnvironment`): it starts from an *empty* environment
  and readmits only ten exact keys plus the prefixes `DARKBLOOM_`, `DYLD_`,
  `LC_`, `METAL_`, `MLX_`, `MTL_`. A plain `FERN_HIDDEN_DUMP` is silently
  dropped; the variable must be named `DARKBLOOM_FERN_HIDDEN_DUMP`.
* the worker's default local Seatbelt profile
  (`Sources/MLXFastCLI/main.swift:1643-1656`) is `(deny file-write*)` with only
  `/dev/null` allowed, so the hook cannot create its file at all unless the run
  sets `MLXFAST_NO_SANDBOX=1`. This is a diagnostic capture only — no timing or
  rankability claim is derived from that run.

The capture run was
`.build/release/mlxfast-swift correctness --golden
correctness_prompts/public_longcopy_gate_english_512_256.json` with the patched
worker, and it **passed** (`passed: true`, `checked_steps: 64`, `error: ""`),
which is itself a small independent check that the hook does not perturb the
forward pass. It produced 2,097,152 bytes = 512 rows × 2048 × 2 B, stored as
`research/redundant-rmsnorm-logs/fern_real_rows.bin`.

Feeding those rows back through the same probe
(`research/redundant-rmsnorm-logs/stage1-real.log`, 1600 rows total):

| class | rows | acc≠ | rsqrt≠ | worst acc ULP | worst rsqrt ULP |
| --- | --- | --- | --- | --- | --- |
| `real-decode-hidden-state` (clean) | 512 | 0 | 0 | 0 | 0 |
| `real-decode-hidden-state` (fault) | 512 | 510 | 510 | 1048577 | 821718 |
| **TOTAL, all classes (clean)** | **1600** | **0** | **0** | **0** | **0** |
| TOTAL, all classes (fault) | 1600 | 1002 | 997 | 1065353216 | 38087278 |

The real rows are the *most* fault-sensitive class in the whole suite —
510/512 of them detect a single `+1.0f` injected into one lane of one virtual
iteration — and every one of them is bit-identical between the 512-thread and
64-thread trees. `RESULT: H1 SUPPORTED`, exit 0.

## Stage 2 — what the redundant reduction actually costs

### Corrected geometry (the assignment's row counts were off)

From `Sources/MLXFastModel/LagunaConfig.swift` and `weights/config.json`:
`hiddenSize = 2048`, `numHiddenLayers = 40`, `headDim = 128`,
`numKeyValueHeads = 8`, `slidingAttentionHeads = 64`,
`fullAttentionHeads = 48`; `layer_types` is 30 `sliding_attention` +
10 `full_attention`; all `gating_types` are `per_head`, so gate rows equal the
head count.

`kvRows = 2 * 8 * 128 = 2048`, and the fused `[Q;K;V;G]` bank is

| family | rows | TGs @ 8 rows/TG (shipped) | TGs @ 2 rows/TG (native) |
| --- | --- | --- | --- |
| sliding (30 layers) | `64*128 + 2048 + 64` = **10304** | 1288 | 5152 |
| full (10 layers) | `48*128 + 2048 + 48` = **8240** | 1030 | 4120 |

So the threadgroup collapse is **4×, not 8×**: the shipped fused kernel packs
`num_simdgroups (2) * results_per_simdgroup (4) = 8` rows/TG (`:4924-4925`,
grid `(rows/8)*64` at `:5339` and `:5352`), while the unfused
`lagunaDecodeNVFP4QKVR1` packs `num_simdgroups (2) * 1 = 2` rows/TG
(`:4656`, `:4665`, grid `(rows/2)*64` at `:4845`, `:4861`, `:4872`).
Crucially, `results_per_simdgroup = 4` is a *register-blocking* choice, not a
bit-exactness requirement — Stage 1 shows the reduction is bit-identical at
either width.

### Harness

`research/fern_redundant_rmsnorm_cost.swift`, driven by
`research/fern_rmsnorm_cost_wandb.py`. Two independent measurements:

1. **Isolated** — `redundant_norm_only` (the verbatim virtualised prologue,
   writing the rsqrt) minus `empty_tg` (same grid, same 64-thread TG width,
   no reduction). This isolates the reduction from launch/schedule cost but
   runs it with *zero* memory pressure.
2. **In-situ** — four macro-generated variants
   (`stream_r{8,2}_{norm,nonorm}`) that stream `rows_per_tg * 2048` INT8 code
   bytes per threadgroup, i.e. the same total 21.1 MB QKV weight bank at both
   geometries, over 4 rotating private slabs so back-to-back reps cannot be
   served from L2/SLC. `laguna_reduce` is the identical inline reduction.
   The `norm − nonorm` difference at a fixed geometry is the part of the
   reduction that does **not** hide behind the weight stream.

ABBA-interleaved, 12 rounds of 800 dispatches per buffer with round 0
discarded, per-config warm-up, GPU-timestamp timing, fast math disabled.

### Results

W&B: **`s97y6fdp`** —
<https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/s97y6fdp>
(raw: `research/redundant-rmsnorm-logs/stage2-cost.log`,
`research/redundant-rmsnorm-logs/stage2-cost.json`).
An earlier, noisier pre-in-situ run is `tjo00rhf`.

Per-dispatch GPU microseconds (n = 12 buffers × 800 dispatches, ± is SE):

| config | µs | ±SE |
| --- | --- | --- |
| `sliding_current_1288` (norm only) | 8.920 | 0.021 |
| `sliding_native_5152` (norm only) | 31.567 | 0.165 |
| `full_current_1030` (norm only) | 7.446 | 0.024 |
| `full_native_4120` (norm only) | 25.635 | 0.167 |
| `empty_sliding_current_1288` | 4.600 | 0.006 |
| `empty_sliding_native_5152` | 16.404 | 0.199 |
| `empty_full_current_1030` | 3.853 | 0.005 |
| `empty_full_native_4120` | 13.438 | 0.215 |
| `stream_r8_nonorm` | 85.484 | 0.502 |
| `stream_r8_norm` | 87.507 | 0.441 |
| `stream_r2_nonorm` | 82.112 | 0.322 |
| `stream_r2_norm` | 83.954 | 0.405 |

**Isolated reduction cost** (norm − empty at the same grid):

| grid | µs | ±SE |
| --- | --- | --- |
| sliding, 1288 TG | 4.320 | 0.022 |
| sliding, 5152 TG | 15.163 | 0.258 |
| full, 1030 TG | 3.593 | 0.025 |
| full, 4120 TG | 12.197 | 0.272 |

Scaled to one decode step (30 sliding + 10 full fused QKV dispatches):

* redundant reduction already paid today: **165.522 µs ± 0.704**
* extra if the geometry moved to 2 rows/TG: **411.335 µs ± 8.244**

**In-situ, with the 21 MB INT8 weight stream present:**

| quantity | µs/dispatch | ±SE |
| --- | --- | --- |
| reduction not hidden @ 8 rows/TG | 2.024 | 0.668 |
| reduction not hidden @ 2 rows/TG | 1.842 | 0.517 |
| **extra unhidden reduction (2 vs 8)** | **−0.182** | **0.845** |
| extra threadgroup/stream cost (2 vs 8) | −3.372 | 0.597 |
| **total 2-vs-8 rows/TG** | **−3.553** | **0.598** |

Scaled to one decode step: **−135.014 µs ± 22.736** — i.e. in this proxy the
finer 2-rows/TG geometry is *faster*, not slower.

### Reading these two numbers together

They differ by ~550 µs/step and both are correct measurements of different
things.

* Decomposing the isolated delta: the `empty_tg` floor alone rises by
  `(16.404−4.600)*30 + (13.438−3.853)*10 = 450 µs/step` when the grid
  quadruples. Almost all of the "cost" of 4× more threadgroups in the isolated
  arm is *launch and schedule* time for threadgroups that do no work — which
  is precisely the time a real kernel spends waiting on weight loads anyway.
* In-situ, the reduction's marginal cost of quadrupling the number of
  redundant reductions is **−0.182 ± 0.845 µs**, i.e. statistically
  indistinguishable from zero. Even the *absolute* unhidden reduction cost
  falls from 4.32 µs (isolated) to 2.02 µs (in-situ) at the shipped geometry.

The honest conclusion is that **the isolated number is a loose upper bound**
and the redundant 2048-element FP32 reduction is essentially free in the
memory-bound decode regime. The shipped code says the same thing at
`:5290-5292` ("no occupancy cost").

The harness's automated gate requires *both* deltas below 25 µs/step and
therefore printed `KILL`. I am reporting that verdict as the harness emitted
it, but the gate is mis-specified: it lets the zero-pressure isolated arm veto
a decision that the realistic arm answers the other way. See "Limits" below
for why the in-situ arm is also not sufficient on its own.

### Limits of the in-situ proxy

`stream_r{8,2}_*` streams the right *volume* of the right *dtype* with the
right per-TG blocking, but it is not the fused kernel: no group-32 dequant
math, no `results_per_simdgroup` accumulator array, no `pf_w/pf_s/pf_b`
prefetch registers (`:5127-5129`), and therefore not the real register
pressure or occupancy. Register pressure is exactly the mechanism by which
`results_per_simdgroup = 4` could be a genuine win, so the `−135 µs/step`
figure must **not** be read as "2 rows/TG would speed up decode". It should
be read as "the *reduction* is not what makes 2 rows/TG slower". Deciding the
geometry question needs the real kernel, which lives in the fenced region.

## Stage 3 — design-only patch recipe (not applied)

Lines 4623–5372 and 5700–5800 of `LagunaRuntimeModel.swift` are fenced for
PR #298 / `maple-nezuko`, so this stage is a recipe only. Nothing in this
branch touches `Sources/`.

**First, the reframing.** The original premise was "the redundant RMSNorm
forces 8 rows/TG because a 64-thread threadgroup cannot reproduce the 512-lane
tree". Stages 0–1 falsify that premise: the 64-thread tree is bit-exact and is
what already ships. There is therefore **no bit-exactness patch to write**.
The remaining lever is purely `results_per_simdgroup`.

If the owner of the fenced region wants to test the 2-rows/TG geometry:

1. `Sources/MLXFastModel/LagunaRuntimeModel.swift:4924` —
   `constexpr uint results_per_simdgroup = 4;` becomes a value interpolated
   from a new Swift constant, e.g.
   `constexpr uint results_per_simdgroup = \(rowsPerSimdgroup);`.
2. `:5105` — the same substitution in
   `lagunaNormAffineQKVPrefetchSource`. The prefetch register arrays at
   `:5127-5129` are already sized by `results_per_simdgroup`, so they follow
   automatically; the fixed initialiser at `:4980` /`:5171`
   (`thread float result[results_per_simdgroup] = {0.0f, 0.0f, 0.0f, 0.0f};`)
   must become `= {0.0f}` or a loop, otherwise the literal count no longer
   matches.
3. `:4969-4970` and `:5120-5121` — `out_row = tile * (num_simdgroups *
   results_per_simdgroup) + simd_gid * results_per_simdgroup` needs no edit;
   it is already parameterised.
4. `:5339` and `:5352` — `grid: ((rows / 8) * 64, 1, 1)` becomes
   `((rows / (numSimdgroups * rowsPerSimdgroup)) * 64, 1, 1)`.
5. Kernel-name suffix at `:5240-5243` and `:5271` must include the new width
   so the two variants cannot collide in MLX's kernel cache.
6. Divisibility guard: the comment at `:5228-5230` relies on all four row
   counts being multiples of 8. 10304 and 8240 are both divisible by 8, 4 and
   2, so widths 4/2/1 are safe; the guard should still be asserted rather than
   assumed, and `lagunaNormAffineQKV` should return `nil` (falling back to the
   exact two-dispatch chain) when it does not hold.
7. Gate: a new `DARKBLOOM_FUSED_NORM_AFFINE_QKV_ROWS` env knob defaulting to
   the current `4`, read next to `lagunaNormAffineQKVPrefetchDepth`. Opt-in
   only; the shipped default must be byte-identical to today's kernel source
   so an unset environment reproduces the current metallib exactly.
8. `normalized` is unaffected: the fused kernel never exports it — each
   threadgroup re-derives normalized values from L1-resident rows
   (`:5290-5292`) and only writes `projected`. Narrowing the tile changes how
   many output rows each TG produces, not what is exported downstream.
9. Validation: `research/run_upstream_equivalence.sh` at each width, then a
   matched `./benchmark.sh --local-iterate` A/B. Expect *no* numerical
   difference at any width — Stage 1 predicts bit-identity — so any golden
   drift would indicate a bug in the re-parameterisation, not a precision
   trade-off.

Given Stage 2, I would rank this a low-priority follow-up: it is a pure
occupancy/register experiment on the fenced kernel, and its upside is bounded
by the ~2 µs/dispatch of unhidden reduction, not by the 4.3–15.2 µs the
isolated measurement suggests.

## Answer to the assignment's question

> Can a 64-thread threadgroup reproduce MLX's 512-lane `rms_bf16` reduction
> tree bit-exactly?

**Yes.** Proven four ways: by index algebra (Stage 1a); by exhaustive
bit-comparison across 1088 adversarial synthetic rows with a working
fault-injection control (Stage 1b); on 512 real decode residual rows captured
from a passing correctness run, 510 of which detect the injected fault
(Stage 1c); and — most decisively — by the fact that the shipped,
ranked-M5-validated decode path already does it at
`LagunaRuntimeModel.swift:4937-4966`. Across all 1600 rows: **0 accumulator
mismatches, 0 `rsqrt` mismatches, worst ULP 0**.

**Consequence for PR #48.** Bit-exactness is not why the 2-rows/TG variant
regressed 0.1488%. Stage 2 further shows the redundant reduction is not why
either: quadrupling the number of redundant reductions costs
−0.182 ± 0.845 µs/dispatch once realistic weight traffic is present. The
regression must be attributed to register blocking, occupancy, or dispatch
count — and the isolated-microbenchmark intuition that "4× more reductions
costs 4× more" is wrong by roughly an order of magnitude in the regime that
matters.

## Reproduction

```bash
# Stage 1 (synthetic)
swiftc -O research/fern_redundant_rmsnorm_bitwise.swift \
  -o /tmp/fern_rmsnorm_bitwise -framework Metal -framework Foundation
/tmp/fern_rmsnorm_bitwise

# Stage 1 (real rows)
git apply research/fern_hidden_dump.patch
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved
# MLXFAST_NO_SANDBOX=1 is required: the worker Seatbelt profile is
# `(deny file-write*)` with only /dev/null allowed, so the hook cannot
# create its dump file under the default local profile. This is a
# diagnostic run only -- no timing or rankability claim is made from it.
MLXFAST_NO_SANDBOX=1 \
MLXFAST_RUNTIME_WORKER_EXECUTABLE="$PWD/.build-worker/release/mlxfast-runtime-worker" \
DARKBLOOM_FERN_HIDDEN_DUMP=/tmp/fern_real_rows.bin \
  .build/release/mlxfast-swift correctness \
  --weights ./weights --golden correctness_prompts/public_longcopy_gate_english_512_256.json
git checkout -- Sources/MLXFastModel/LagunaRuntimeModel.swift
/tmp/fern_rmsnorm_bitwise /tmp/fern_real_rows.bin

# Stage 2 (cost + W&B)
python3 research/fern_rmsnorm_cost_wandb.py 800
```

## Files

| path | role |
| --- | --- |
| `research/fern_redundant_rmsnorm_bitwise.swift` | Stage 1 bit-comparison probe + fault control |
| `research/fern_redundant_rmsnorm_cost.swift` | Stage 2 isolated + in-situ cost harness |
| `research/fern_rmsnorm_cost_wandb.py` | Stage 2 driver, logs to W&B |
| `research/fern_hidden_dump.patch` | Stage 1c decode-row dump hook (apply → run → revert) |
| `research/redundant-rmsnorm-logs/stage1-synthetic.log` | Stage 1b raw output |
| `research/redundant-rmsnorm-logs/stage1-real.log` | Stage 1c raw output |
| `research/redundant-rmsnorm-logs/stage2-cost.log` | Stage 2 raw output |
| `research/redundant-rmsnorm-logs/stage2-cost.json` | Stage 2 machine-readable results |
| `research/redundant-rmsnorm-logs/fern_real_rows.bin` | Stage 1c real decode rows (bf16 bit patterns) |

Submitted-surface growth for this branch: **0 bytes** (everything is under
`research/`; verified with
`senpai/check-editable-budget.sh 69178729b154cbb648ea0ce6152e92dbfdb17cc6`).
