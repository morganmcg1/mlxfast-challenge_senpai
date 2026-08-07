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

<!--RESULTS-->

## Step 4 — Correctness

<!--CORRECTNESS-->

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
