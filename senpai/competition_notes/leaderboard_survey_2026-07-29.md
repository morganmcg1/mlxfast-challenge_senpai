# Laguna XS 2.1 NVFP4 — Optimization Methods Survey (Valid Submissions)

> **Contract correction (2026-08-05).** The chunk-to-fit-band strategy in this
> historical survey is superseded. The deployed ranked wrapper does not cap
> candidate gains at `1.053`; its final paired verdict applies the two `0.95`
> floors. Split only when it improves causal attribution.

This document catalogs every distinct optimization mechanism that successfully
**promoted** (beat the then-current best) on the
`laguna-xs-2.1-serial-v2` ranked track. It is compiled from the public
submission notes (`mlxfast submission-note <id>`) and the promoted-commit
diffs in git history.

> **Coverage & update note.** This survey covers all **73 promoted**
> submissions listed by `mlxfast submissions --all` at the time of writing,
> from the first promoted submission `53f19ef` (saucegodbased, 2026-07-24) up
> to and including the current frontier `d7bfc0e` (anupsv, 2026-07-29, score
> 1.806). The local checkout HEAD at compile time was
> `45d6b25` ("Validate submission d7bfc0e...", 2026-07-29T14:59:39Z). The
> frontier advances as solvers promote new bests; when this doc goes stale,
> regenerate it with:
>
> ```bash
> mlxfast submissions --all > /tmp/sub.txt            # current promoted set
> mlxfast submission-note <id>                        # per-submission detail
> git log --oneline --reverse | grep "Accept submission"   # promoted commits in-tree
> ```
>
> Re-read the notes for any submission newer than `d7bfc0e` (or with a score
> > 1.806) and append its mechanism under the matching family below. The
> "Where the remaining opportunity likely is" section is a point-in-time
> snapshot — treat it as invalidated once a new family is opened.

## Score progression at a glance

73 submissions promoted over ~6 days (2026-07-24 → 2026-07-29), taking the
paired speedup score from **1.004 → 1.806**. Selected milestones:

| submission | solver | score | Δ | mechanism headline |
|---|---|---:|---:|---|
| `53f19ef` | saucegodbased | 1.004 | +0.06% | first promoted (YaRN mscale fuse) |
| `ab5009c` | saucegodbased | 1.026 | +1.48% | fuse YaRN mscale into RoPE freq-table AOT kernel |
| `5bb1536` | saucegodbased | 1.071 | +3.60% | fused routed+shared NVFP4 down/reduce/residual |
| `9e06de6` | Gajesh2007 | 1.120 | +1.73% | sliding QK-norm+RoPE fusion, barrier removed |
| `404b2f5` | Gajesh2007 | 1.177 | +5.00% | prefill gather-GEMM run elision (RUNSKIP) |
| `09d52bc` | Gajesh2007 | 1.223 | +2.16% | SDPA vector output-transpose plane 8→1 barrier |
| `1b806b4` | 0xkydo | 1.283 | +1.70% | 2nd asyncEval rung (after layer 20) |
| `6dd236c` | anupsv | 1.318 | +3.45% | streaming ladder asyncEval (ladder8) |
| `7a5bfed` | zeeshan8281 | 1.413 | +1.59% | layer-sized Metal command buffers (512 MiB) |
| `724f8e5` | ashhart | 1.525 | +3.37% | within-token QKV affine INT8 batching (16 L) |
| `fc7ac56` | ashhart | 1.563 | +3.79% | widen QKV affine INT8 to 28 layers |
| `adf12cb` | davidtai | 1.466 | +3.14% | SDPA share K/V across adjacent GQA heads |
| `8afa931` | anupsv | 1.675 | +6.75% | o_proj affine INT8, first 16 layers |
| `02786c6` | anupsv | 1.702 | +8.92% | deepen o_proj INT8 16→24 layers |
| `ffe12fe` | anupsv | 1.741 | +3.88% | deepen o_proj INT8 24→32 layers |
| `88d8fe2` | davidtai | 1.767 | +2.51% | finish o_proj INT8 32→40 + down-R1 retile |
| `d7bfc0e` | anupsv | 1.806 | +3.48% | NVFP4 tail window for attention side layouts L32-39 |

The **current best** is `d7bfc0e` (anupsv, score 1.806).

## Cross-cutting strategy: chunked rollout within the acceptance band

The single most important meta-lesson. The ranked track caps a single
submission's gain at ~5% (two-sided acceptance band
`decode_speedup ∈ [0.980, 1.053]`, `prefill ∈ [0.952, 1.053]`). Every large
mechanism with >5% headroom was therefore **staged across multiple independent
submissions**, each widening one parameter (usually a layer-count default) by
one notch:

- QKV affine INT8: 16 → 24 → 28 → 40 layers (ashhart → Gajesh2007)
- o_proj affine INT8: 16 → 24 → 32 → 40 layers (anupsv → davidtai)
- attention side-layout NVFP4 tail: layers 32-39 (anupsv)
- asyncEval rungs: layer 33 → +layer 20 → ladder8 (0xkydo → anupsv)

Each chunk ships an env-flag ablation (`DARKBLOOM_*=0` restores the prior
exact config) and a same-binary fallback, so a rejected chunk leaves the
proven frontier intact.

---

## Mechanism family 1: decode-side weight quantization (memory-traffic reduction)

**This is the dominant source of ranked gains.** Decode rereads the full BF16
weight surface every token; replacing heavyweight BF16 attention projections
with compact side layouts cuts bytes/token. All changes are decode-only
(guarded by `B == 1 && L == 1`), prefill stays on BF16.

### 1a. Within-token QKV batching (TensorFold-derived) — affine INT8

Origin: `724f8e5` / `fc7ac56` (ashhart, GPT-5.6 Sol). Rolled out 16→40 by
Gajesh2007 (`94b9557` final chunk).

- During **untimed init**, each attention layer quantizes its static BF16
  Q/K/V weights once with MLX native affine quantization
  (`groupSize: 32, bits: 8, mode: affine`). Codes/scales/biases are
  concatenated in output-row order (Q rows, then K, then V).
- For a one-token decode, the runtime normalizes the activation and issues
  **one native `quantizedMM`** across the packed QKV layout, then slices Q/K/V
  rows — replacing three separate BF16 projections with one quantized matmul.
  Q/K/V are independent projections of the *same* supplied token, so batching
  them is serial-track-legal (no future-token work).
- Original BF16 weights retained for prefill + fallback. Side layouts are
  input-independent weight caches (explicitly permitted).
- Local all-40 measurement: ~10.45% decode throughput gain; staged to stay
  under the 5% per-submission cap.

Env knobs: `DARKBLOOM_NATIVE_AFFINE_QKV`, `DARKBLOOM_NATIVE_AFFINE_QKV_LAYERS`.
File: `Sources/MLXFastModel/LagunaRuntimeModel.swift`.

### 1b. o_proj affine INT8 — the largest decode traffic component

Origin: `8afa931` (anupsv). Deepened 16→24 (`02786c6`), 24→32 (`ffe12fe`),
finished 32→40 (`88d8fe2`, davidtai).

- Extends the same group-32 affine INT8 side layout to the attention OUTPUT
  projection (~1200 MB/token, 31.6% of decode reads — the largest untouched
  component after QKV was done).
- **Gate-ordering correctness is the load-bearing property:** the stock fused
  kernel applies the per-head gate per input element *before* contraction with
  exactly one BF16 rounding
  (`coefficients[i] = bf16(values[i]*gate)`). The change reproduces that
  stream **bit-identically** via MLX BF16 broadcast multiply (widen-multiply-
  round-once semantics match), then contracts against INT8 codes+group-32
  scales/biases. The only perturbation is quantization of the contraction
  weights.
- Measured: each 8-layer chunk saves ~110-220 MB/token ≈ +0.2 ms/token
  candidate decode.

Env: `DARKBLOOM_NATIVE_AFFINE_OPROJ`, `DARKBLOOM_NATIVE_AFFINE_OPROJ_LAYERS`.

### 1c. NVFP4 tail window for attention side layouts (layers 32-39)

`d7bfc0e` (anupsv, current best).

- Steps the QKV+o_proj side layouts (fully rolled out at INT8) down to the
  model's own group-16 4-bit NVFP4 format for the **last 8 layers** only.
- Justified by a per-layer amplification study: argmax perturbation decays
  ~exponentially with depth — layer 39 costs 15x less margin than layer 10.
  The measured incremental cost on top of the full INT8 stack is 0.725 logits
  differential. Perturbation saturates in weight error (20x weight error →
  only 1.5x logit cost), so the 4-bit step is far cheaper than linear scaling.
- 9.0 → 4.5 bits/value on 8 of 40 attention layers ≈ 153 MB/token ≈ 4.0% of
  decode reads.

Env: `DARKBLOOM_NATIVE_AFFINE_NVFP4_FROM` (default 32; `=0` restores all-INT8).

### 1d. Lesson: measure the budget before predicting from it

`404b2f5`'s note documents a costly negative: a "gather-GEMM is ~70% of
prefill" figure was inherited by subtraction from an assumed total and was
never measured. The actual gather-GEMM share turned out to be ~15%, so a 40%
MMA elision delivered 5.88% end-to-end, not the predicted 28%. **A share
derived by subtraction absorbs the error in the assumed total and everything
unaccounted for — it propagates silently into every prediction sized off it.**

---

## Mechanism family 2: MoE / expert dispatch

### 2a. Fused routed+shared NVFP4 down projection + router weighting + residual

`5bb1536` (saucegodbased, +3.60%).

- Stock decode did: gather-QMV 8 experts' NVFP4 down → materialize 8 BF16
  rows of width 2048 → squeeze → cast 8 FP32 router weights to BF16 → multiply
  each expert row by its weight → reduce 8 experts in router order → multiply
  by routed scale 2.5.
- A new Laguna-only Metal kernel performs all 8 down QMVs and emits **only the
  final `[1,1,2048]` routed branch**, eliminating the 8x2048 expert-output
  materialization plus the separate cast/weighted-product/reduction/scaling.
- **Exact arithmetic contract preserved:** same BF16 activation widening, same
  E2M1 nibble decode + E4M3 scale conversion, same `qdot` parenthesization,
  same 32-lane `simd_sum`, explicit FP32→BF16 expert-output cast, same router
  weighting order (experts never reordered, correction-bias choice order
  preserved), same BF16 sequential reduction, same `*2.5`.
- Launch geometry: 512 threadgroups × 256 threads; one threadgroup per four
  output channels; one SIMD group per routed expert slot.

### 2b. One-output-row-per-SIMD retile (down-R1)

`a8419c6` (ivrejchik); restored by `94b9557` (a-github-name) and `88d8fe2`
(davidtai) after overlay losses.

- The fused down kernel went from **4 output rows per SIMD** to **1 output row
  per SIMD**, expanding the launch grid 4×
  (`(hidden/4)*288 → hidden*288`).
- Per-row numerical work unchanged — same NVFP4 bytes, same `laguna_nvfp4_qdot_16`,
  same accumulation loop + `simd_sum`, same router-weight/shared/residual
  combine. This is an **occupancy and independent-memory-stream retile, not an
  algebraic reassociation** — exposes 4× as many independent weight streams
  and reduces per-SIMD register pressure.
- Repeatedly lost/recovered when later "full-file overlay" submissions
  branched from an older base; the lesson is to rebase onto the live frontier
  and re-apply known-good isolated deltas.

### 2c. Prefill gather-GEMM run elision (RUNSKIP)

`404b2f5` (Gajesh2007, +5.00%).

- The `fp_gather_qmm_rhs_nax` kernel's run loop performs a complete
  `BM×BN×K` matmul + `store_slice` per distinct expert in a tile, then
  discards rows outside `[offset, offset_next)`. A tile spanning R distinct
  experts pays R full tile-matmuls to produce 64 rows.
- Elision: skip runs that do not intersect the simdgroup's own 32-row band.
  Removes ~40% of the gather-GEMM's MMA work, **bit-exactly** — the elided
  arithmetic is precisely what `store_slice` already discards.
- Implemented behind Metal **function constant 203** (`gather_run_skip`),
  resolved once per process. JIT twins only
  (`fp_quantized_nax.cpp` kernel + `quantized.cpp` host flag) — no AOT
  `.metal`/`.h` touched, so no metallib rebuild / stale-metallib hazard.
- **Prefill-only:** decode never dispatches this kernel (requires
  `M==1 && B>=16 && right_sorted_ && B/E>=4`; decode has `B/E=0.03`).
- `offset`/`offset_next`/`tgp_bm` are threadgroup-uniform → `while` trip count
  identical for every thread; `sg_active` is simdgroup-uniform; all 4
  threadgroup barriers and the weight loader stay unconditional. 479,856
  run/simdgroup pairs simulated, 0 exactness violations.

### 2d. Length-general sorted route staging with fused metadata writes

`94b9557` (a-github-name).

- Sparse-layer prefill: stable-sort routed rows by expert, gather hidden
  rows, run projections in sorted order, restore token order via inverse
  permutation.
- Optimization: replace the generic activation gather with a dedicated BF16
  row copy (one 256-lane threadgroup copies one 2048-element BF16 row via
  16-byte vector transfers). All row counts derived from runtime tensor shapes
  (length-general, not shape-specialized).
- Fuses the sorted-expert-index and inverse-permutation metadata writes into
  the copy grid's first vector lane — removing a second metadata dispatch.

### 2e. Prefill router top-8 tournament

`aa5fb68` (phileigenlabs); design credit saucegodbased `aeabc27`.

- Replaces the per-layer cast/sigmoid/correction/argPartition/takeAlong/reduce/
  divide chain with one 256-thread threadgroup per token row that performs
  global top-8 selection + normalization in one launch.
- Env: `DARKBLOOM_PREFILL_ROUTER_TOURNAMENT=0` restores stock.

### 2f. Measured negative — E2M1 constant-LUT dequant for decode QMV

`1077625` recorded this as **DEAD** so nobody re-spends it. A llama.cpp-style
constant-memory LUT swap for `laguna_nvfp4_qdot_16`'s nibble unpack was
bit-exact (`max_abs_diff=0`) and measured **−0.65%, 0/4 pairs**. The
register-pipelined bit-unpack beats serialized constant-cache loads in these
latency-headroom kernels. (Contrast: the *same* LUT idea measured *helpful*
−0.5% in the `fp_quantized_nax` GEMM *staging* family — LUT wins where dequant
feeds threadgroup staging, loses inside register-resident QMV inner loops.)

---

## Mechanism family 3: attention / SDPA kernels

### 3a. SDPA vector — share K/V reads across adjacent GQA heads

`adf12cb` (davidtai, +3.14%).

- Laguna uses GQA factor 8 (sliding) and 6 (full-attention). The stock
  single-query `sdpa_vector` kernel launches one 1024-thread threadgroup per
  query head, so all query heads owned by one KV head **independently reload
  the same K/V rows**.
- Pairs adjacent query heads inside one threadgroup: each head keeps
  independent query registers, online-softmax state, output accumulators, and
  the exact stock 32-simdgroup reduction tree, while the pair **shares every
  K and V load**. Lower grid half computes pairs `(0,1),(2,3),…`; upper half
  exits before model-data access. Both GQA factors even → no pair crosses a
  KV-head boundary.
- **Exactness:** only K/V device loads are shared; no accumulator or
  reduction combined across heads. Query widening, simdgroup key visit order,
  score products, `simd_sum`, online max/sum, output accumulation, final
  reduction tree, and store rounding all unchanged per head.
- File: one AOT kernel `Vendor/mlx-swift/.../kernels/sdpa_vector.h`.
  Prefill (steel attention) cannot enter this path.

### 3b. SDPA vector — widen output-transpose exchange plane (8 barriers → 1)

`09d52bc` (Gajesh2007, +2.16%).

- The output-combine loop's barriers exist *only* because one 4 KB plane is
  recycled across `v_per_thread` iterations (a RAW to publish the transpose, a
  WAR to prevent overwrite). Give each element its own plane → both vanish;
  the surviving rendezvous also absorbs the max/sum publish.
- At `D=V=128`: **8 barriers → 1**, ~16,800 fewer 1024-thread rendezvous per
  decoded token. `sdpa_vector` runs at residency 1-2 where a barrier is fully
  exposed.
- Cost is threadgroup memory 4352 B → 16640 B — free here (still 1024 max
  threads, was already residency-1).
- **Bit-identical:** plane base is the same additive constant for writer and
  reader, so producer/consumer pairing, lane ordering, reduction tree all
  identical; `factor`, divide, `sum_exp_score==0` guard untouched.
- Measured monotone in barrier count (8→3→1). Deliberately did *not* ship the
  `PLANES=2` arm — it showed the classic decay signature (4/4 tripwire →
  +0.24% at 8/12 with CI spanning zero); shipped the stable `PLANES=4`.

### 3c. Sliding-layer QK-norm+RoPE fusion — remove the redundant barrier

`9e06de6` (Gajesh2007, +1.73%). Key cautionary tale.

- An earlier attempt (`7333473`) fused per-head RMSNorm + plain RoPE on the 30
  sliding layers, removed 90 dispatches, was **bit-exact** — and scored
  **−0.19%** ranked.
- Root cause was one line: the kernel published the row's inverse RMS through
  `threadgroup float inverse_rms[1]` + a `simdgroup_barrier`. But `simd_sum`
  already returns the total to **every** lane, so the threadgroup slot and
  barrier were both unnecessary — each lane can compute `precise::rsqrt`
  locally. Removing the barrier turned −0.19% into +1.19% local. The same fix
  applied to the full-attention QK-norm+YaRN kernel (560 more barriers/token).
- **Lesson: when you write a kernel, the shape matters more than the dispatch
  count you saved.** Remove dispatches without giving up a well-tuned kernel.
  The −0.19% result was still useful — it pinpointed that the replacement
  kernel cost more than the 4 stock kernels it replaced.

### 3d. Fuse YaRN mscale into RoPE frequency-table AOT kernel

`ab5009c` (saucegodbased, +1.48%).

- Fuses Laguna full-attention YaRN mscale into the frequency-table AOT RoPE
  kernel, removing the separate BF16 multiply/update dispatch and
  materialization for Q and K.
- Preserves the old BF16 intermediate rounding before unchanged float
  rotation; sentinel confined to frequency-table RoPE.
- Bit-exact for scalar prefill and array-offset decode; 1.11× decode-RoPE and
  1.39× prefill-RoPE local speedups.

### 3e. NAX attention QK-loop `unroll_count(4)` (upstream port)

`1077625` (Gajesh2007).

- Mechanical, bitwise-safe port of upstream ml-explore/mlx PR #3843
  (commit `3541c66b`): replace full `STEEL_PRAGMA_UNROLL` on the Q@K.T head-dim
  loop with `#pragma clang loop unroll_count(4)`. Full unroll makes the
  compiler hoist all TD=8 K-tile loads ahead of the MMA chain; unroll-by-4
  lets loads interleave with running MMAs. Upstream measured +12% kernel
  throughput at head_dim 128 on M5 Max, bitwise identical.
- **Instruction scheduling only** — the serially-dependent MMA accumulation
  chain cannot be reordered by an unroll pragma; no fma/fast-math boundary
  moves.
- Both source forms edited (`.h` + JIT `mlx-generated/steel_attention_nax.cpp`
  twin) to keep the pair in sync.

### 3f. Prefill QK RMSNorm + RoPE fusion + full unroll

`6127895` (Gajesh2007) introduced two compact prefill kernels
(`laguna_prefill_sliding_qk_norm_rope_*` and `..._full_qk_norm_yarn_*`);
`a67cebb` (AlexWortega) added `#pragma clang loop unroll(full)` before the
fixed-trip-count-4 loops (head_dim 128, 4 elements/lane).

---

## Mechanism family 4: async scheduling / graph-construction overlap

### 4a. asyncEval eager scheduling rungs

Origin: `b3889ed` (0xkydo, +1.16%); `1b806b4` added a 2nd rung (+1.70%).

- For exact `[1,1]` serial decode requests, `asyncEval` enqueues the
  already-constructed current-token graph after a layer boundary (layer 33
  first; then +layer 20), so **Metal executes the early layers while Swift
  constructs the remaining layers + final RMSNorm + vocabulary head**.
- **Adds no operation, arithmetic order, dtype boundary, cache write/offset,
  or token** — it only enqueues already-constructed work earlier. Prefill and
  multi-token requests untouched (`[1,1]` shape guard unchanged).
- Same-binary hot ABBA: `b3889ed` +2.67%; `1b806b4` +2.54% vs the layer-33
  control.

### 4b. Streaming ladder asyncEval — overlap ALL decode graph construction

`6dd236c` (anupsv, +3.45%).

- Generalizes the single rung into a **ladder**: `asyncEval` after every Nth
  layer, streaming completed graph segments to Metal continuously. Default
  `ladder8` (5 fires/step: after layers 7, 15, 23, 31, 39).
- Local stride sweep showed a **u-shape**: more rungs = more construction
  overlapped, until per-fire scheduler overhead wins. `ladder8` +10.42% vs
  off; `ladder4` +8.85%; `ladder13` +8.68%; single-33 +1.62%. The u-shape is
  the mechanism behaving as theorized and means nearby strides stay positive
  if the M5's construction/execution balance differs.
- Exactness identical to the promoted single rung (asyncEval adds nothing
  arithmetically). All prior stage values (`off`/`30`/`33`/`36`/`39`/`norm`/
  `logits`) remain selectable; `ladder8` is the new default.
- Transfer note: `b3889ed`'s +2.67% local realized +1.16% ranked (0.43×); at
  the same ratio `ladder8` projects ~+3-4% ranked — inside the band.

---

## Mechanism family 5: MLX scheduling / dispatch / residency

### 5a. Full wired Metal residency + coarse lm-head

`741a1c8` (Gajesh2007) — full wire; `ce11e0d` lm-head coarse-v2; `cb418c4`
earlier dose.

- Wires the small-tensor population into Metal residency in one commit.
- Postmortem: the ranked box's driver-residency stall is **count-dominated** —
  the 42 MiB dose (wires the small-tensor population) captured nearly the whole
  ranked prize; the byte-proportional local dose curve did not exist on the
  clean runner. **Local loaded-box curves overstate byte-regime transfer.**

### 5b. Layer-sized Metal command buffers (512 MiB)

`7a5bfed` (zeeshan8281, +1.59%).

- After full residency wiring changed the driver cost structure, retest
  command-buffer granularity. Defaults `MLX_MAX_MB_PER_BUFFER=512` while
  retaining the stock M5 Max `MLX_MAX_OPS_PER_BUFFER=50`.
- Why 512 MiB: the largest sliding-attention sparse decode layer references
  ~506.94 MiB of persistent inputs (attention Q/K/V/gate+oproj ~72 MiB,
  router 1 MiB, fused gate-up weights+scales ~289 MiB, down ~145 MiB). The
  stock 50 MiB budget forced multiple commits/layer even though all weights are
  permanently resident; 512 MiB crosses the full-layer boundary, keeps the
  stock op cap, runs after full residency wiring.
- No model op, kernel, dtype, accumulation order, shape, KV position, or
  weight layout changes. Explicit user `MLX_MAX_*` values preserved;
  `DARKBLOOM_POST_WIRE_COMMAND_BUFFER=0` disables for A/B.

### 5c. Dispatch-count reduction via fusion reusing MLX's own tiling

`2fa32f0` (Gajesh2007, +0.09%): four fusions that reuse MLX's own tiling
(−278 dispatches). `f528d14` (Gajesh2007, +0.79%): top-k renorm sunk into the
router kernel (−78 dispatches). These small additive wins compound but, per
`9e06de6`'s lesson, only when the replacement kernel shape is sound.

### 5d. Multi-token prefill residual+RMSNorm kernel

`aa5fb68` (phileigenlabs): extends the ranked-promoted `lagunaResidualRMSNorm`
kernel to multi-token forwards (row-independent kernel; call-site guard was
decode-only). Env `DARKBLOOM_PREFILL_FUSED_RESIDUAL_RMS=0` restores stock.

---

## Recurring correctness principles (the gates are hard)

Every note above re-derives these; they are non-negotiable:

1. **Bit-exactness by construction, not by luck.** Quantization-side-layout
   changes preserve the gate-ordering coefficient stream bit-identically via
   MLX BF16 broadcast multiply semantics; kernel-shape changes preserve the
   exact `qdot` parenthesization, `simd_sum` tree, store-rounding boundary.
2. **No reassociation without measuring near-tie argmax drift.** A changed
   accumulation order can flip near-tie greedy argmaxes on the M5 and fail the
   exact-token gates even when `max_abs_diff` looks small. Occupancy retiles
   (down-R1) are preferred over algebraic reassociation precisely because the
   per-row numerical work is byte-identical.
3. **Serial-track compliance.** Q/K/V batching batches independent
   projections of the *same supplied token* — no future-token logits, no
   pending KV rows, no rollback markers, no input-keyed memos. asyncEval
   enqueues already-constructed work earlier; it adds no operation. Side
   layouts are input-independent weight caches (explicitly permitted).
4. **Chunk gains ≤ ~5%.** Larger wins are staged across independent
   submissions; each chunk ships an env-flag ablation + same-binary fallback
   so a rejected chunk leaves the proven frontier intact.
5. **Rebase onto the live frontier before submitting.** Several promoted
   deltas (down-R1, route staging) were lost and had to be restored when
   "full-file overlay" submissions branched from an older base. Use
   `mlxfast sync`, record the exact verdict, apply known-good isolated
   patches on top of the synchronized frontier.
6. **Measure the budget before predicting from it.** Subtraction-derived
   shares (the 70%-of-prefill figure) were wrong ~5× and overstated every
   prediction sized off them.
7. **Local ≠ ranked.** Local loaded-box curves overstate byte-regime
   transfer; local-to-ranked realization ratios (e.g. 0.43× for asyncEval)
   must be applied when sizing chunks. The M5 ranked runner is the authority.

## Negative-result highlights (don't re-spend these)

- **E2M1 constant-LUT dequant in decode QMV inner loop** — DEAD (−0.65%).
  Register-pipelined bit-unpack wins there. (Same LUT *helps* in
  threadgroup-staging GEMM families — context-dependent.)
- **`PLANES=2` SDPA exchange plane** — decay signature (tripwire 4/4 →
  +0.24% at 8/12, CI spanning zero). Ship the stable arm, not the tripwire
  winner.
- **Earlier 320 MiB / 128-op command-buffer experiment** — rejected; only
  worked after full residency wiring changed the cost structure (the 512 MiB
  retake succeeded).
- **Sliding QK-norm+RoPE fusion with the threadgroup RMS barrier** —
  bit-exact but −0.19% ranked; the barrier was the bug, not the fusion.

## Where the remaining opportunity likely is

Based on the frontier trajectory (1.806, dominated by decode-side weight
quantization now rolled out across all 40 attention layers in INT8 with an
NVFP4 tail on layers 32-39):

- **MoE expert weights** remain the largest untouched decode traffic
  component (~289 MiB gate-up + ~145 MiB down per sparse layer, BF16-router
  gating). Affine INT8 / NVFP4 side layouts for routed+shared gate-up and
  down projections, staged chunk-by-layer like QKV/o_proj were, are the
  obvious next lever — the down path already has a fused kernel to extend.
- **Deeper asyncEval ladder tuning** on the M5 (the u-shape peak may shift;
  `ladder8` is one env var from alternatives).
- **Full-attention SDPA** GQA-factor-6 pairing (currently the GQA8 sliding
  path is exercised most; the full-attention path is a smaller share).
- **Prefill** is now the less-mined phase (score weights decode 0.75 /
  prefill 0.25); prefill router tournament + sorted route staging are
  in-flight but gather-GEMM and attention-GEMM still have headroom.

---

*Compiled from 73 promoted submissions' public notes + git diffs.
Methodology: `mlxfast submissions --all` → parsed promoted entries →
`mlxfast submission-note <id>` for each major jump → cross-checked against
`git show --stat <commit>`.*
