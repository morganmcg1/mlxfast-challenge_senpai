# Compiled elementwise decode fusion — census, price, and a structural null

PR #269 · assignment `maple-2026-08-07h-compiled-elementwise-fusion` r1 ·
student maple-nezuko · host Apple M4 Pro, 48 GiB, macOS 26.5.2 (25F84).

## Hypothesis

> Wrapping genuinely elementwise segments of the scored decode path in MLX
> `compiled{}` removes N real dispatches per step and refunds ≥ 1.0 µs per
> removed dispatch, bit-exactly.
>
> Falsified if refund ≤ 0.3 µs/dispatch, or tokens change, or the fused kernel
> is slower.

**Verdict: falsified on the scored path, for a reason stronger than the refund
threshold — N = 0.** The scored decode path contains no `compiled{}`-fusable
segment at all, so no refund can be collected there. The mechanism itself was
then priced on a real off-default elementwise chain and does refund ≈ 1.2 µs
per removed dispatch, which is a calibration, not scored headroom.

## Step 1 — Reachability before null: the elementwise dispatch census

### 1a. Empirical census of the scored decode step

`research/nezuko-pr158-split1-kernels.txt` (GPUPROF hook, steady decode window):
**24 kernel families, exactly 406 dispatches/step, 8583.0 µs/step of GPU-busy
time.** Only three dispatches are not `custom_kernel_laguna_*`:

| kernel | n/step | µs/call | µs/step | MLX primitive |
| --- | ---: | ---: | ---: | --- |
| `rmsbfloat16` | 41 | 3.48 | 142.7 | `fast::RMSNorm` |
| `argmax_bfloat16` | 1 | 9.30 | 9.3 | `ArgReduce` |
| `gather_frontbfloat16_int32_int_2` | 1 | 3.58 | 3.6 | `Gather` |

The other 403 dispatches are hand-written fused Metal custom kernels. The
largest are `routed_nvfp4_swiglu_qmv` (39 × 38.48 = 1500.7 µs),
`decode_nvfp4_qkv_h64` (30 × 44.47 = 1334.2), `oproj_act_h64`
(30 × 37.22 = 1116.6), `routed_shared_nvfp4_down_residual`
(39 × 22.26 = 868.3), and `sliding_fused_attn_ring` (30 × 21.16 = 634.8).

**There is not one `binary*`, `unary*`, `ternary*`, or `copy*` dispatch in the
entire scored decode step.**

### 1b. Static confirmation on the MoE gate

On the default decode path (batch 1, seq 1) `LagunaRuntimeMoEGate.callAsFunction`
issues exactly **one** GPU dispatch, `laguna_decode_router_top8_ordinal_table_norm_v1`.
`sinkNormalization` is true, so the gate early-returns at
`LagunaRuntimeModel.swift:9572-9574` and never reaches the `normTopkProb`
sum-and-divide tail. `LagunaRuntimeDecoderLayer` likewise has zero plain-MLX
elementwise dispatches left: residual add + post-attention RMSNorm + router
GEMV collapse into `laguna_residual_rms_router_bf16_2048_rpg8_keys_v1`, and the
routed weighted reduce + scale + shared add + second residual add collapse into
`lagunaRoutedSharedDownResidual`.

### 1c. Source-level confirmation that N = 0 is structural, not incidental

`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/compile.cpp:77-79`:

```cpp
bool is_fusable(const Primitive& p) {
  return is_unary(p) || is_binary(p) || is_ternary(p) || is_broadcast(p);
}
```

`is_reduction` (`Reduce`, `ArgReduce`) is defined at `:72-74` and is
deliberately **excluded** from `is_fusable`. `Custom` kernels, `Gather`, and
`fast::RMSNorm` are not in any of the four fusable predicates either.

So the three stock primitives that survive on the scored path — RMSNorm,
argmax, gather — are each individually non-fusable, and the remaining 403
dispatches are opaque custom kernels. `compiled{}` has **zero** candidate
subgraphs on the scored decode path. This is a property of MLX's fuser and of
the promoted frontier's kernel coverage, not a sampling artefact of one census.

## Step 2 — Pricing the mechanism on a real off-default chain

Since the default path offers no target, the nearest *real* elementwise chain
is the stock router tail that `DARKBLOOM_FUSED_ROUTER=0` restores. It runs
39×/step (40 layers, layer 0 dense) on real shapes (256 FP32 scores per call)
and is a strict dependency chain:

```
AsType(bf16→f32) → Sigmoid → Add(bias) → Negative     [all fusable]
argPartition → takeAlong                              [not fusable]
Sum(axis:-1) → Divide                                 [Sum not fusable]
```

`DARKBLOOM_COMPILED_ROUTER_TAIL` (default on) wraps the two elementwise
segments (`LagunaRuntimeModel.swift:9467-9491`, call sites `9592-9611`):

* `lagunaCompiledRouterScores` — the 4-node fusable chain, 2 outputs, one
  `Compiled` kernel. Predicted removal **3 dispatches per gate call ×
  39 = 117/step**.
* `lagunaCompiledRouterNormalize` — `w / w.sum(-1)`. `Sum` is a `Reduce` and is
  **not** fusable, so this is predicted to remove **0**. It is kept as a
  negative control for the fuser's documented boundary.

The default scored path is untouched: it early-returns before this tail.

## Step 3 — Measured refund

### Design

`research/nezuko_compile_abba.sh` runs `B, (C U U C) × 4, B` — 18 separate
worker processes, one model-holding process at a time, 255 teacher-forced
decode steps each against
`correctness_prompts/public_longcopy_gate_english_512_256.json`, first 8 steps
discarded, n = 247 steady samples per run. The ABBA order cancels linear host
drift inside each block; the two `B` runs bracket the whole session.

* **B** — default scored path (both flags unset).
* **U** — `DARKBLOOM_FUSED_ROUTER=0`, `DARKBLOOM_COMPILED_ROUTER_TAIL=0`
  (stock elementwise tail, unfused).
* **C** — `DARKBLOOM_FUSED_ROUTER=0`, `DARKBLOOM_COMPILED_ROUTER_TAIL=1`
  (same tail, `compiled{}`).

Analysis: `python3 research/nezuko_compile_stats.py /tmp/nezuko_abba_r1 --warmup 8 --removed <N>`.

### Result

| arm | n runs | mean µs/step | sd of run means |
| --- | ---: | ---: | ---: |
| B (default, fused Metal router) | 2 | 8181.1 | (8174.7, 8187.0) |
| C (stock tail, `compiled{}`) | 8 | 8870.0 | 16.8 |
| U (stock tail, unfused) | 8 | 9014.3 | 32.6 |

Block-paired `U − C` over 4 ABBA blocks: **+124.1, +143.9, +176.5, +132.3 µs/step**

> **mean = +144.23 µs/step, sd 23.00, se 11.50, t = +12.54,
> 95% CI [+107.6, +180.8]**

Session drift is +12.3 µs/step between the two bracketing `B` runs over
13 minutes — 8.5% of the effect, and ABBA-cancelled within blocks.

### Measured dispatch count, and where the refund lands

`research/nezuko_compile_census.sh` re-ran all three arms under the GPUPROF
command-buffer hook (`research/nezuko-pr158-gpuprof-hook.patch`), 60 steps,
59 steady. **This is a separate, instrumented binary — it is a dispatch census,
not the timing evidence.** The hook costs ~55 µs/step, so its absolute numbers
sit above the clean-binary ABBA above.

| arm | dispatches/step | cbs/step | wall µs | GPU-busy union µs | gap µs |
| --- | ---: | ---: | ---: | ---: | ---: |
| B base (fused Metal router) | **406** | 45 | 8235 | 7880 | 355 |
| U stock tail, unfused | **679** | 45 | 8957 | 8724 | 233 |
| C stock tail, `compiled{}` | **562** | 45 | 8817 | 8585 | 232 |

`U − C = 117 dispatches/step`, i.e. **exactly the predicted 3 × 39**, with the
command-buffer count unchanged at 45. The kernel names confirm the mechanism
directly. The four separate kernels in `U` —

```
v_copybfloat16float32 | v_Sigmoidfloat32float32 | vv_Addfloat32 | v_Negativefloat32float32
```

become a single kernel in `C`:

```
Cf4IAsTypeADf4OSigmoidCEf4IBroadcastDBFf4IBroadcastBDGf4IAddEFHf4ONegativeG_VV_V2f4_…
```

The **negative control behaves exactly as `is_fusable` predicts.** The
normalize helper compiles to `Cf4IBroadcastABDf4IBroadcastBAEf4ODivideCD_…`,
which still sits *beside* an unchanged `row_reduce_small_1_reduce_sumfloat32`:
`Sum` is a `Reduce`, so it is not fusable, and the compiled region removes
**0** dispatches. Two dispatches in, two dispatches out. The `is_fusable`
source reading in Step 1c therefore predicts both arms correctly.

**The refund is GPU-side, not CPU-side.** `gap` (the CPU-side graph-construction
and submission time not covered by GPU work) is 233 µs in `U` and 232 µs in
`C` — a 1 µs difference. The entire `U − C` movement is in the GPU-busy union:
8724 → 8585 µs, **Δunion = 139 µs**, which agrees with the clean-binary ABBA
estimate of +144.23 ± 11.50 µs/step to within 0.4σ. Fusing these ops does not
make the host cheaper; it removes real serialized GPU kernel launches.

**The refund is uniform across command-buffer contexts.** Each of the eight
distinct command-buffer signatures contains exactly one router gate tail, so
each should shed exactly 3 dispatches:

| gate tails/step | U µs/call | C µs/call | Δ µs/call | Δ per removed dispatch |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 198.99 | 195.96 | 3.03 | 1.01 |
| 8 | 200.35 | 196.15 | 4.20 | 1.40 |
| 5 | 236.18 | 232.74 | 3.44 | 1.15 |
| 4 | 237.15 | 233.89 | 3.26 | 1.09 |
| 4 | 216.56 | 213.07 | 3.49 | 1.16 |
| 4 | 93.90 | 89.93 | 3.97 | 1.32 |
| 3 | 196.52 | 192.77 | 3.75 | 1.25 |
| 1 | 150.06 | 146.81 | 3.25 | 1.08 |

The tails sum to 39, as they must. The weighted total is **138.5 µs/step**,
reconciling with Δunion. Every signature lands in a tight 1.01–1.40 µs band
regardless of how much other work shares its command buffer — the signature of
**true elimination**, not of work relocating into a neighbouring kernel.

### Final refund

Using the measured `N = 117` with the clean-binary ABBA estimate:

> **refund = 144.23 / 117 = +1.233 µs per removed dispatch,
> 95% CI [+0.920, +1.545]**

The instrumented census independently gives 138.5 / 117 = **+1.18 µs**.
Both clear the +1.0 µs pre-registered bar; both are far above the +0.3 µs
falsification floor.

For scale, `B → U` adds 273 dispatches for +844 µs of union (3.09 µs each),
but that number conflates overhead with genuinely new work: the fused Metal
router `decode_router_top8_ordinal_table_norm_v1` does the sort, gather,
reduce and divide itself in one 5.18 µs kernel, so the stock tail is not
merely more dispatches, it is more arithmetic. Only the `U → C` contrast
isolates dispatch overhead at fixed arithmetic.

## Step 4 — Correctness

### The default scored path is untouched

The call site sits in the deepest `else` of `LagunaRuntimeMoEGate`, which is
reached only when `lagunaDecodeRouterTop8Enabled` is false — i.e. only under
`DARKBLOOM_FUSED_ROUTER=0`. With default environment the fused Metal router
`laguna_decode_router_top8_ordinal_table_norm_v1` runs and returns early, so
none of the new code executes. The census confirms this: the default arm still
issues **exactly 406 dispatches/step**, unchanged from the pre-registered
Step 1 census.

### The restructure is bit-exact by construction

The stock tail already computed `var logits = projectedLogits.asType(.float32)`
*before* the branch, so moving that same cast inside the compiled region is not
a precision change — it is the identical `AsType` node relocated so `is_fusable`
can absorb it. The rest is algebra:

| stock | mine |
| --- | --- |
| `scores = sigmoid(logits)` | `sigmoid(projectedLogits.asType(.float32))` |
| `scoresForChoice = scores + bias.asType(scores.dtype)` | `bias` is already f32, so `.asType` is a no-op |
| `argPartition(-scoresForChoice, …)` | `argPartition(negScoresForChoice, …)` with `negScoresForChoice = -(scores + bias)` |

MLX's laziness matters here: when my branch fires, the outer `logits` value is
never consumed, so its `AsType` is dead and never dispatched. That is why `U`
shows exactly one `v_copybfloat16float32` per gate and not two.

### Measured correctness

| gate | result |
| --- | --- |
| Golden teacher-forced, census arms (60 steps × base/U/C) | `0 divergences (all match)` on all three |
| Golden teacher-forced, ABBA (247 steps × 18 runs) | `golden_divergences = 0` on every run |
| **`C` vs `U` token streams** | **bit-identical**; each arm emitted exactly 1 distinct sequence across its 8 runs |
| Vendored-upstream equivalence (default path) | see below |

`bash research/run_upstream_equivalence.sh` on the candidate reports
`EQUIVALENCE_EXACT_STEPS=8`: all eight decode steps have
`maximumAbsoluteLogitError = 0` and every runtime token equals the upstream
token, including prefill (5991 == 5991). The test nevertheless exits 1 because
prefill shows `maximumAbsoluteLogitError = 0.125` against a `0.0` tolerance.

Following the AGENTS.md rule for a non-M5 host disagreeing with a public
golden, I re-ran the identical test on the **unchanged base** via a throwaway
control commit that reverted `LagunaRuntimeModel.swift` to `b731a0fd` (verified
by an empty `git diff BASE HEAD -- Sources/ Vendor/ benchmark.json`). The base
produces a **byte-identical report**, down to
`meanAbsoluteLogitError = 0.011933609` in all nine significant figures:

| arm | prefill maxAbsErr | prefill meanAbsErr | decode-0…7 maxAbsErr | tokens |
| --- | ---: | ---: | ---: | --- |
| base `b731a0fd` | 0.125 | 0.011933609 | all 0 | all match |
| candidate `09deba7` | 0.125 | 0.011933609 | all 0 | all match |

This is the pre-existing M4 Pro divergence AGENTS.md warns about: this host
reports Apple GPU generation 16, never selects the `_nax` prefill kernels, and
the public fixtures were generated on M5. **The candidate is numerically
identical to the base on this gate**, and the control commit was discarded
(`git reset --hard 09deba7`).

### Preflight at the current base

```
senpai/validate-assignment-scope.sh b731a0fd… Sources/MLXFastModel/LagunaRuntimeModel.swift
  → assignment scope OK: 1 submitted path(s)
senpai/check-editable-budget.sh b731a0fd…
  → editable budget OK: current=2952621/3000000 headroom=47379 growth=1766/262144
```

Per-file: 468,336 → 470,102 B, **54,186 B under the 524,288 B cap.** The
vendored-Metal fingerprint tree is untouched at HEAD (`git diff HEAD --
Vendor/mlx-swift/Source/Cmlx/` is empty); the GPUPROF hook used for the census
was applied to a scratch build only, reverted before commit, and the worker was
rebuilt clean afterwards. All timing evidence in Step 3 comes from the clean
binary (ABBA finished 12:21:15, the hooked binary was not built until
12:22:19).

## Interpretation

### Why this does not reopen the closed dispatch-count model

`CURRENT_RESEARCH_STATE.md` closes `(dispatches removed) × (µs/dispatch)` as a
predictor, on strong evidence: PR #48 removed 80 dispatches and measured
−0.1488% against a +2.595% prediction (10.2σ); PR #204 deleted 39 dispatches
for −0.9 ± 12.1 µs; my own PR #9 removed 40 of 406 dispatches bit-exactly for
0.0% on the full benchmark and **+228 µs/step slower** on a low-noise probe.

This result does not contradict any of that, because the two situations are
different operations on the GPU-busy union, which is the currency PR #32 r2
showed actually predicts wall time (`d(wall) = 1.0364 × d(union) + 2.10 µs`,
R² = 0.9985, **no usable dispatch-count term**):

* **Relocation** (#9, #48, #204): the work is moved into an existing kernel.
  The receiving kernel gets slower by roughly what the removed kernel cost, so
  Δunion ≈ 0 and sometimes worse. The dispatch *count* falls; the union does
  not.
* **Elimination** (this experiment): four serialized 256-element kernels become
  one. Three kernels' worth of GPU-busy interval, plus their barrier drains,
  leave the union outright. Δunion is genuinely negative.

MLX encodes with `MTL::DispatchTypeConcurrent`
(`Vendor/mlx-swift/.../backend/metal/device.cpp:548`) but inserts an
encoder-wide `memoryBarrier(BarrierScopeBuffers)` whenever a dispatch consumes
a previous dispatch's output (`device.cpp:324-326, 364-366`). A dependent chain
like `AsType→Sigmoid→Add→Negative` therefore serializes completely: nothing
overlaps it. And a 256-float kernel moves ~2 KB, which is nanoseconds of DRAM
traffic, so essentially all of its ~1.2 µs is fixed launch/barrier/latency
cost. Removing it removes that full ~1.2 µs.

That is the same number the sibling PR #241 obtained from the opposite
direction — **1.4 µs/dispatch (range 1.29–1.73)** by *adding* bit-exact identity
multiplies at 6 decode sites, with additivity 0.9608 ± 0.0500. Adding a
serialized tiny kernel costs ~1.4 µs; removing one refunds ~1.2 µs. The two
calibrations agree. What fails is not the price of a serialized tiny kernel —
it is the assumption that a *fusion-style* dispatch reduction eliminates one.

### Honest scope of this measurement

The refund is real, paired, bit-exact, and reproducible, but it was collected on
a path the promoted frontier already deleted. The hand-written
`laguna_decode_router_top8_ordinal_table_norm_v1` kernel beats the best
compiled stock tail by a large margin (see Step 3). `compiled{}` recovers only
a fraction of the penalty that turning the fused router off imposes.
`compiled{}` is therefore **strictly dominated** by the custom kernel that is
already on the scored path, and the refund measured here is not latent scored
headroom — it is the cost of an inefficiency the frontier does not have.

### What would still be worth pricing (not implemented here)

1. **Union/gap decomposition of the three arms.** Whether the 150 µs is Δunion
   or Δgap (CPU-side graph construction) decides whether the number transfers
   to any future path at all. Step 3 reports this.
2. **Command-buffer commit policy.** `needs_commit()` fires at
   ops > 50 **or** unique-input bytes > 50 MB (`device.cpp:484-487, 584-589`;
   `buffer_sizes_` accumulated at `:319-321`). At 406 dispatches in ~45 command
   buffers the model averages ~9 ops/buffer, so the *size* threshold is what
   actually commits — every ~9 dispatches touch >50 MB of NVFP4 weights. Both
   thresholds are env-tunable (`MLX_MAX_OPS_PER_BUFFER`, `MLX_MAX_MB_PER_BUFFER`,
   `mlx/utils.h:178-188`) and the defaults are on the editable surface. If the
   ~250 µs wall-minus-union gap is concentrated at the ~45 buffer boundaries
   (~5.6 µs each) rather than spread over 406 dispatches (~0.6 µs each), buffer
   count — not dispatch count — is the CPU-side lever. **This is a zero-code-change
   sweep and is the single cheapest untested idea I encountered.**
3. **Barrier-granularity / encode-order overlap.** Because the dependency
   barrier is encoder-wide, program order decides what overlaps. Reordering
   genuinely independent dispatches (shared-expert vs routed-expert
   projections) between the same barrier pair attacks the 8.27 ms union rather
   than the 0.25 ms gap. Speculative, and it is kernel-graph surgery, not
   `compiled{}`.

### Recommendation

Close `compiled{}` / MLX graph-level elementwise fusion as a scored-path
direction. `is_fusable` cannot see custom kernels, reductions, or gathers, and
the frontier has already replaced every fusable segment on the decode path with
a hand-written kernel that is faster than what the fuser would emit.
