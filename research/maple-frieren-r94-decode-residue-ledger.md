# R94-A: the decode-step dispatch ledger closes to +0.004 %. There is no residue.

Student: maple-frieren. PR #502. Assignment `maple-r94-a-decode-residue-ledger`,
revision `r94-a-rev1`. Base `d549d31856953292b9b2b54905cf3f6f67ed27a4`
(`codex/mlxfast-maple-20260804-advisor`).

Host for all local work: **Apple M4 Pro, 48 GiB, macOS 26.5.2 (25F84)**
(`applegpu_g16s`, Apple GPU generation 16, `_nax` variants unreachable).

Reproduce every number in this note with:

```bash
python3 research/r94_ledger_build.py     # writes research/r94-artifacts/r94-dispatch-ledger.tsv
```

---

## Headline: the assignment's premise is falsified before any GPU is booked

The assignment asks me to find and close a **~1,186 µs/step (14.8 % of busy)
residue that "no named kernel accounts for"**. That residue does not exist. The
complete ledger already existed in-tree, and when it is added up it accounts for
**8528.3 µs of the 8528.0 µs reported busy time — a residual of +0.3 µs, or
+0.004 %** — across **406 of 406 dispatches**, with **zero** unattributed
dispatches.

The `1186.1` figure is an arithmetic artifact of two compounding errors:

1. **An incomplete subtotal.** The advisor's "named" table lists 10 rows summing
   to 6807.0 µs over 281 dispatches
   (`1702.9+1419.5+1497.7+858.9+636.0+312.8+229.7+141.9+4.7+2.9 = 6807.0`).
   The census it was drawn from has **24** rows. The **10 omitted rows are worth
   1721.3 µs over the other 125 dispatches** and are printed on the same page of
   the same document
   (`research/maple-nezuko-r92-barrier-hoist-generalization.md:70-100`).
2. **A cross-regime subtraction.** `1186.1 = 7993.1 − 6807.0` subtracts a
   `SPLIT=1` subtotal from a `nat`-regime busy total. Rule 43
   (`research/CURRENT_RESEARCH_STATE.md:290-296`) forbids exactly this: `SPLIT=1`
   is attribution-only, and magnitude must come from a `nat`-regime paired census.

Both errors point the same way, so they add rather than cancel: the missing
1721.3 µs of `SPLIT=1` rows minus the 534.9 µs of `SPLIT=1` instrument inflation
is 1186.4 µs — which is, to within rounding, the "residue".

Consequence for the campaign: **do not book M5 or M4 time to hunt this residue.**
The 24-label ledger below is the answer to Stages 0-2 of the assignment, and it
was obtained at zero GPU cost.

## Stage 0 — reconciling 363 with 406, exactly, with no new run

The assignment treats the 363-vs-406 dispatch-count gap as an open question
requiring a fresh scored-worker trace. It does not. The gap is **exactly the
three MLX stock/AOT kernels**, and the reconciliation is arithmetically closed:

| source | dispatches/step | what it can see |
| --- | --- | --- |
| PR #490 scored-worker emission trace (`research/r92-artifacts/r92-census-stage1prime.txt`) | **363** | only ops constructed with `verbose:` — i.e. only custom `MLXFast.metalKernel` dispatches (21 labels) |
| PR #488 `SPLIT=1` live decode census (`research/maple-nezuko-r92-barrier-hoist-generalization.md:70-100`) | **406** | every dispatch, including MLX stock/AOT ops (24 labels) |
| difference | **43** | `41× rmsbfloat16` + `1× argmax_bfloat16` + `1× gather_frontbfloat16_int32_int_2` |

`363 + 43 = 406`. Both figures are steady-state. The 363 figure was proven
steady in PR #490 by two byte-identical consecutive `Counter` multisets, and the
per-kernel counts (the 39/30/10/1 pattern) match the 406-dispatch census **row
for row**; the 21-label set is exactly the 24-label set minus the three stock
labels. So the gap is the *stock-op blind spot of the r92 verbose-dump vehicle* —
it is **not** warm-up, **not** amortised setup, and **not** `SPLIT=1` inflation.

Why the vehicle is blind here is structural, not incidental: MLX prints a custom
kernel's generated MSL only at op construction and only when `verbose: true`
(`Sources/MLXFastCLI/main.swift:315-318`), and stock/AOT kernels
(`rms`, `arg_reduce`, `gather`) never take that argument. No amount of extra
tracing with that vehicle can ever see them.

## A new, reusable `SPLIT=1` → `nat` busy deflator: 1.317 µs/dispatch

Rule 43 bars comparing `SPLIT=1` totals with `nat` totals, but it does not bar
*calibrating* the offset when both totals are known for the same configuration.
They are:

```
SPLIT=1 gpu_busy_sum   8528.0 µs/step   (PR #488, 79-step steady window, 32074 CBs)
nat     gpu_busy_sum   7993.1 µs/step   (local M4 Pro nat reference, #473 base binary)
difference              +534.9 µs/step over 406 dispatches = 1.317 µs/dispatch
```

**1.317 µs/dispatch sits inside the rule-41 boundary bracket** (WIDE 1.4064
[1.3163, 1.4964]; TINY 0.7258 [0.5275, 0.9241]) — i.e. `SPLIT=1` costs almost
exactly one extra wide dispatch boundary per dispatch, which is what a
one-dispatch-per-command-buffer instrument should cost. Separately,
`SPLIT=1` **wall** − `nat` **wall** is +1537.7 µs/step; that is the instrument
tax the assignment quotes as "1642", and it must never be attributed to kernels.

This gives a defensible per-row deflator: `nat_est(row) = us_split1 − n_calls × 1.317`.
Applied to all 24 rows the deflated total is **7993.4 µs** against a measured
`nat` busy of **7993.1 µs**, so the deflator is self-consistent to 0.004 %.
Every `us/step_nat` figure below uses it. It is an *estimate per row* — the
column that is measured is the `SPLIT=1` one — but the aggregate is anchored.

## Stage 1 — the complete ledger

`research/r94-artifacts/r94-dispatch-ledger.tsv` is the machine-readable form
(columns `label kind origin calls_per_step us_per_step us_per_call
bytes_touched_est notes`, plus an explicit `unattributed` row carrying the
+0.3 µs / 0 dispatches so the contract is met literally).

`score%_if_zero` uses the campaign conversion **1 µs/step decode = 0.015280 %
of score**.

| µs/step (SPLIT=1) | calls | µs/call | µs/step (nat est) | score % if zeroed | label |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1497.7 | 39 | 38.40 | 1446.3 | 22.100 | `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` |
| 1340.1 | 30 | 44.67 | 1300.6 | 19.873 | `laguna_decode_nvfp4_qkv_h64_…` |
| 1117.7 | 30 | 37.26 | 1078.2 | 16.475 | `laguna_oproj_act_h64_…` |
| 858.9 | 39 | 22.02 | 807.5 | 12.339 | `laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` |
| 636.0 | 30 | 21.20 | 596.5 | 9.114 | `laguna_sliding_fused_attn_ring_v1` |
| 420.3 | 1 | 420.30 | 419.0 | 6.402 | `laguna_lmhead_int5_base_coarse_delta_bf16_v1` |
| 362.8 | 10 | 36.28 | 349.6 | 5.342 | `laguna_decode_nvfp4_qkv_h48_…` |
| 312.8 | 39 | 8.02 | 261.4 | 3.994 | `laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1` |
| 301.8 | 10 | 30.18 | 288.6 | 4.410 | `laguna_oproj_act_h48_…` |
| 287.1 | 39 | 7.36 | 235.7 | 3.602 | `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` |
| 269.4 | 1 | 269.40 | 268.1 | 4.096 | `laguna_dense_gate_up_swiglu_bf16_v1` |
| 248.0 | 30 | 8.27 | 208.5 | 3.186 | `laguna_gate_sp_h64_v1` |
| 229.7 | 10 | 22.97 | 216.5 | 3.309 | `laguna_full_fused_attn_grow_v1` |
| 185.5 | 39 | 4.76 | 134.1 | 2.049 | `laguna_prefill_router_tournament_ordinal_norm_active64_v2` |
| 141.9 | 41 | 3.46 | 87.9 | 1.343 | `rmsbfloat16` (stock) |
| 133.8 | 1 | 133.80 | 132.5 | 2.024 | `laguna_dense_down_residual_bf16_v1` |
| 80.2 | 10 | 8.02 | 67.0 | 1.024 | `laguna_gate_sp_h48_v1` |
| 77.0 | 1 | 77.00 | 75.7 | 1.156 | `laguna_lmhead_exact_fused_int5_sparse_refine_v1` |
| 9.0 | 1 | 9.00 | 7.7 | 0.117 | `argmax_bfloat16` (stock) |
| 4.7 | 1 | 4.70 | 3.4 | 0.052 | `laguna_lmhead_exact_winner_bf16_midpoint_threshold_v1` |
| 4.1 | 1 | 4.10 | 2.8 | 0.043 | `laguna_lmhead_coarse_argmax_stage1_v5` |
| 3.5 | 1 | 3.50 | 2.2 | 0.033 | `laguna_decode_embedding_rope_atlas_bf16_2048_v2` |
| 3.4 | 1 | 3.40 | 2.1 | 0.032 | `gather_frontbfloat16_int32_int_2` (stock) |
| 2.9 | 1 | 2.90 | 1.6 | 0.024 | `laguna_residual_rms_bf16_2048_v1` |
| **8528.3** | **406** | | **7993.4** | | **total** (reported busy 8528.0 / nat busy 7993.1) |

Two identifications worth recording, because both label names lie:

- `laguna_prefill_router_tournament_ordinal_norm_active64_v2` **runs 39× in
  decode**. `lagunaDecodeRouterTop8` calls
  `lagunaPrefillRouterTournamentOrdinalForTesting(..., rows: 1, ...)` at
  `Sources/MLXFastModel/LagunaRuntimeLayers.swift:776`; the
  `projectedLogits.dim(1) > 1` guard at `:1414` is not the only entry point. The
  kernels actually *named* for the decode router are dead code.
- The advisor's table row "`LagunaLmHeadPrune` 1 @ 4.7" is
  `laguna_lmhead_exact_winner_bf16_midpoint_threshold_v1`.

Command-buffer structure is closed and is not re-litigated here: 45.0 CBs/step
in `nat`, set by `DARKBLOOM_DECODE_ASYNC_STAGE` default `at:0,1,7,15,23,31,39`
with `MLX_BFS_MAX_WIDTH=50`, `MLX_MAX_MB_PER_BUFFER=200`,
`MLX_MAX_OPS_PER_BUFFER=200` (`Sources/MLXFastModel/LagunaRuntimeWeights.swift:384-394`).

## Stage 2 — a roofline verdict for every row

Bytes come from `weights/config.json` (hidden 2048, `head_dim` 128, 8 KV heads,
`num_attention_heads_per_layer` = 30×64 sliding + 10×48 full, `mlp_only_layers`
`[0]` dense **bf16** at intermediate 8192, 39 sparse layers, 256 experts top-8,
`moe_intermediate` 512, shared expert 512, vocab 100352, NVFP4 bits 4
group_size 16), with NVFP4 charged at 0.5625 B/weight (4-bit element + one fp8
group scale per 16) and INT8 group-32 affine at 1 B/weight + 4 B/group. The
roofline is the **M4 Pro 273 GB/s** platform peak; an earlier local
copy-microbenchmark figure of 260.2 GB/s turns out to be a *floor* on achievable
rate, because several rows beat it.

| pool | µs/step (nat) | % of busy | labels | verdict |
| ---: | ---: | ---: | ---: | --- |
| bytes-bound (90-100 % of peak) | **6090.4** | **76.2 %** | 9 | irreducible without removing bytes |
| latency-bound attention | 813.0 | 10.2 % | 2 | KV stream at 105-109 GB/s; softmax serialization, not launches |
| partly bytes-bound (57-71 %) | 497.1 | 6.2 % | 2 | ~150 µs of theoretical headroom, needs a real kernel rewrite |
| **launch/ramp overhead** | **592.9** | **7.4 %** | 11 | the only pool a fusion can attack |
| total | 7993.4 | 100 % | 24 | nat busy 7993.1 |

Per-row achieved rates (nat-deflated):

| label | MB/step | GB/s | % of 273 | verdict |
| --- | ---: | ---: | ---: | --- |
| `decode_nvfp4_qkv_h64` | 353.9 | 272.1 | 100 % | bytes-bound |
| `decode_nvfp4_qkv_h48` | 94.4 | 269.9 | 99 % | bytes-bound |
| `oproj_act_h64` | 283.1 | 262.6 | 96 % | bytes-bound |
| `oproj_act_h48` | 70.8 | 245.2 | 90 % | bytes-bound |
| `routed_nvfp4_swiglu_qmv` | 368.1 | 254.5 | 93 % | bytes-bound |
| `routed_shared_down_residual` | 207.0 | 256.4 | 94 % | bytes-bound |
| `dense_gate_up_swiglu` | 67.1 | 250.3 | 92 % | bytes-bound (bf16, not NVFP4) |
| `dense_down_residual` | 33.6 | 253.3 | 93 % | bytes-bound |
| `lmhead_int5_base_coarse_delta` | 128.5 | 306.6 | 112 % | bytes-bound; see note |
| `sliding_fused_attn_ring` | 62.9 | 105.5 | 39 % | latency-bound |
| `full_fused_attn_grow` | 23.6 | 109.0 | 40 % | latency-bound |
| `residual_rms_router_…_pf1` | 40.9 | 156.4 | 57 % | partly bytes-bound |
| `shared_nvfp4_swiglu_qmv` | 46.0 | 195.2 | 71 % | partly bytes-bound |
| `gate_sp_h64` | 4.4 | 21.2 | 8 % | **overhead-bound** |
| `gate_sp_h48` | 1.1 | 16.5 | 6 % | **overhead-bound** |
| `prefill_router_tournament_…` | 0.04 | 0.3 | 0 % | **overhead-bound** |
| `rmsbfloat16` | 0.34 | 3.8 | 1 % | **overhead-bound** |
| 7 tail labels (lm-head stages, embedding, gather, layer-0 norm) | ~0 | ~0 | 0 % | **overhead-bound** |

The single most important line in this table for the campaign: **76.2 % of the
decode step already runs at 90-100 % of the M4 Pro memory-bandwidth peak.** No
dispatch-level or fusion-level trick can move it. The only remaining decode
levers are (a) reducing the *bytes* those nine kernels read, (b) attacking the
813 µs of attention serialization, and (c) the 592.9 µs launch/ramp pool.

### Three Stage-2 findings that correct the assignment brief

1. **The layer-0 dense MLP is bf16, not NVFP4** (`mlp_only_layers: [0]`), which
   is why 2 dispatches cost 400.6 µs. At 250-253 GB/s it is *already saturated*:
   **irreducible** without changing its representation, which is outside the
   accepted quantization envelope.
2. **The lm-head screening plane already reads less than the whole plane.** The
   nominal packed int5 plane is 100352 × 2048 × 5/8 = 128.5 MB, which at 419.0 µs
   implies 306.6 GB/s — 112 % of platform peak, i.e. impossible. So the
   "base coarse delta" kernel is reading roughly 109-115 MB, consistent with a
   coarse plane plus a sparse delta. The lm-head cluster is therefore **not** a
   6.4 % pool of naive full-vocab reads waiting to be pruned; it has already
   been pruned.
3. **The brief's "`rmsbfloat16` does a second pass over the same 2048 floats"
   hypothesis is wrong.** The 41 calls are 40 per-layer *input* norms plus 1
   final norm. They are not redundant with the 39× `residual_rms_router_…_pf1`
   (which is the *post-attention* residual+norm+router-logit kernel) nor with the
   1× `residual_rms_bf16_2048_v1` (layer-0 dense post-attention norm). 40 + 39 +
   1 + 1 = 81 norm-like operations for 40 layers × 2 norms + 1 final = 81. The
   count is exactly right; there is no duplicated norm. That family is in any
   case already capped at ≤ 35.0 µs/step recoverable by PR #483's input-norm→QKV
   fusion result.

### Ranked removable/fusable candidates in the 592.9 µs overhead pool

| candidate | µs/step (nat) | dispatches removable | boundary floor at 1.4064 µs | verdict |
| --- | ---: | ---: | ---: | --- |
| `gate_sp_h64` + `gate_sp_h48` | **275.5** | **40** | 56.3 | largest fusable item — but closed prior art, see Stage 3 |
| `prefill_router_tournament_…` into `residual_rms_router_…_pf1` | 134.1 | 39 | 54.9 | second choice; same 39-layer cadence, one is a 40 KB read |
| `rmsbfloat16` (input norms) into QKV | 87.9 | 40 | 56.3 | **closed** — PR #483 measured ≤ 35.0 µs/step actual recovery |
| 4 small lm-head stages | 89.6 | 4 | 5.6 | serially dependent screening cascade; not independently fusable |
| embedding + gather + layer-0 norm | 5.9 | 3 | 4.2 | below any detection bar |

Note the transfer-ratio discipline this table forces. PR #483 fused the input
RMSNorm into QKV: it removed a `SPLIT=1`-attributed 141.9 µs and recovered
**≤ 35.0 µs/step** in matched `nat` timing — a transfer ratio near **0.25**.
Applying that prior to `gate_sp` gives an honest expectation of **~70 µs/step**
(and a floor of 56.3 µs from pure dispatch boundaries), against a paired-ABBA
`nat` ratio-adjusted busy σ of 10.65 µs/step (±8.91 at n = 8) and a practical
`--local-iterate` wall detection bar near 80 µs/step. That is detectable by the
ABBA census but marginal on wall clock alone.

## Nomenclature flag: rules 45, 46 and 51 do not exist

The assignment cites "rule 45 (deletion probes unsound, price by bit-exact
addition)", "rule 46 (donation-preserving unary)" and "rule 51 (the oracle is a
numerical not a dispatch oracle)". **None of those numbers exist in
`research/CURRENT_RESEARCH_STATE.md` or anywhere else in the research corpus.**
The numbered rules end at 44 in `§6` (lines 263-307), with 47 and 48 introduced
separately in `research/advisor-r93-m5-receipt-channel-and-promotion-model.md`.
The *content* of all three is sound doctrine — and the oracle point is one I
established myself in PR #490, where the upstream-equivalence oracle loads dense
safetensors and fails the NVFP4 guards at
`Sources/MLXFastModel/LagunaRuntimeLayers.swift:2014-2060`, so it dispatches a
different kernel set. But the numbering should be fixed before it propagates
into another assignment as if it were indexed.

## Stage 3 — no fusion is shipped, and the reason closes the pool

**Verdict: the largest fusable cluster is not an unexplored win. It is
already-measured prior art with a negative M4 result and a negative ranked-M5
result, and the one cell that remains genuinely untested is bounded below this
host's detection floor. Nothing is shipped. The submitted surface of this PR is
byte-identical to the base commit `d549d31`.**

### 3.1 What Stage 2 nominated

Stage 2 leaves exactly one attackable pool: launch/ramp overhead, 592.9 µs/step,
7.4 % of the step, 11 labels. Inside it the ranking is unambiguous:

| candidate | nat µs | dispatches removable | status after Stage 3 |
|---|---:|---:|---|
| `gate_sp_h64` + `gate_sp_h48` | 275.5 | 40 | **closed — measured twice, both negative** |
| `prefill_router_tournament` → `residual_rms_router` | 134.1 | 39 | **closed — unsound, and out of file scope** |
| `rmsbfloat16` → QKV | 87.9 | 41 | **closed — capped ≤ 35.0 µs by #483** |
| 4 small lm-head stages | 89.6 | 3 | serially dependent cascade |
| embedding / gather / layer-0 norm | 5.9 | 3 | below any bar |

I built the top candidate, then found the prior art. Reporting both, in that
order, because the sequence is the finding.

### 3.2 The mechanism I implemented

Grid-concatenation of the standalone `laguna_gate_sp_h{64,48}_v1` gate dispatch
into `laguna_decode_nvfp4_qkv_h{64,48}_r1_v1_lm1_pw1_se1_sd1`: one kernel,
`grid = ((heads/8 + rows/2) * 64, 1, 1)`, threadgroup `(64,1,1)`,
`constexpr uint gate_tiles = heads/8`, body selected by
`if (tile < gate_tiles) { <gate body> return; } tile -= gate_tiles;`, two
outputs (`projected`, `gate_values`), 8 inputs, new name suffix `_gsp1` for
rule 33 and the name-keyed MLX JIT cache. The gate body was emitted through a
parametrised `lagunaGateSoftplusSource(heads:names:)` whose defaults reproduce
byte-identical MSL, preserving `V=8`, `BK=256`, the `simd_sum` tree, the
`float(bfloat(r))` bf16 round-trip and the NaN/Inf softplus branch.

I placed the gate tiles **first** on the reasoning that Metal issues
threadgroups roughly in index order, so trailing gate tiles would run with 8
threadgroups resident after the 5,120 QKV tiles retire — an exposed tail with
near-zero saving — whereas leading tiles enter during the QKV ramp and hide
behind saturated work.

**Every element of that paragraph, including the prepend reasoning, is a
re-derivation of `research/nezuko-pr9-dispatch-fusion.md`.** That arm shipped
`laguna_decode_nvfp4_qkv_gate_h<64|48>_r1_v1[_se1][_sd1]`, described at
`:31-38` as "one kernel whose grid concatenates the two tile spaces,
`((rows/2) + heads/8) * 64` threads at threadGroup 64…  the gate owns the
leading `heads/8` threadgroups **so it is scheduled first**", with "both Metal
bodies copied verbatim… the only edit is renaming the gate kernel's input
`input` -> `normalized`". That is my implementation, down to the rename.

### 3.3 The two measurements that close it

**(a) M4, this host class, better instrument than I have.** PR #9's
`research/sweep_qkv_gate_fuse.sh`, four arms, fresh worker each, 120
teacher-forced steps, step 0 discarded, GPU timestamps windowed to the steady
decode span (`nezuko-pr9-dispatch-fusion.md:44-52`):

| arm | cb/step | dispatch/step | wall/step | gpu_busy_union |
|---|---:|---:|---:|---:|
| FUSE=1 SPLIT=0 | 45 | 366 | 8.773 ms | 8.487 ms |
| FUSE=0 SPLIT=0 | 45 | **406** | **8.545 ms** | 8.345 ms |

Fusion is **+228 µs/step (+2.7 %)** at shipped batching on the median and
**+144 µs (+1.7 %)** on the per-arm minimum, with the arm order *favouring*
FUSE=1. Under `SPLIT=1` the same change reads **−506 µs/step** — opposite sign.
Correctness was green in all four arms (`max_abs_diff=0`), so this is a pure
timing rejection. Full `--local-iterate` was null: 13.604 ms/token for the
candidate against two identical-code baselines at 13.569 and 13.647, a 0.58 %
noise floor.

That −506 vs +228 sign flip is the origin of rule 43, and it is worth restating
in this ledger's own terms: **my Stage-1 attribution of 275.5 µs to `gate_sp` is
a `SPLIT=1` quantity, and `SPLIT=1` is exactly the regime that mispredicted this
fusion's sign.** The 1.317 µs/dispatch deflator I derived in Stage 0 converts
magnitude, not sign.

**(b) Ranked M5, superset of the mechanism.** PR #48 mode 2 (RMSNorm fold +
gate ride-along, −80 dispatches, 406 → 326) reached the official M5 as receipt
`285f79fa-089f-4184-b1ec-0647cb51e61b`, commit `3234ece1`, correctness fully
green (`checked_steps 1344`, `max_abs_diff 0`, GPQA 9/9 both gates), and scored
`ns 2.540575` against control `c3ce66ec` `2.544360` — **Δ = −0.1488 %, a
regression** (`RESEARCH_ARCHIVE_through-round-91.md:5900-5945`). It also
pre-registered the dispatch-count reading (80 × 2.1828 µs ⇒ +2.595 %) against a
+0.44 % alternative at 10.2 σ separation; the M5 came in below both. Reading A
was refuted outright. The archive's conclusion — "**ease of implementation was
never the constraint; the mechanism simply is not worth anything**".

Removing 80 dispatches bought −0.1488 %. My arm removes 40.

### 3.4 The residual cell, and why it cannot be adjudicated here

The archive is precise about what is left: "**the one genuinely untested cell**
is a *dispatch-only* gate merge (no norm fold) at the shipped
`num_simdgroups=2` geometry with gate tiles scheduled first — PR #48's mode 2
bundled the norm fold and its `QKV_R1_SIMDGROUPS=16` re-tiling, so the gate fold
was never isolated **on M5**." It then bounds it: "Expect **sub-0.5 %** … Frame
it only as a narrow pre-registered discriminator, never as an unexplored win."

Two things follow.

1. **The untested axis is the M5 measurement, not the mechanism.** PR #9 already
   isolated the dispatch-only merge and measured it on M4. My host is M4 Pro.
   There is no M4 information left to buy.
2. **Sub-0.5 % is below this host's floor.** 0.5 % of 8230.3 µs/step is 41 µs.
   The paired-ABBA `nat` ratio-adjusted busy σ is 10.65 µs/step, ±95 % ≈ ±8.91
   at n = 8 — but `--local-iterate`, the only instrument I have without the
   patch-only `DARKBLOOM_GPU_PROFILE` hook, resolves ±50 µs/step at n = 8
   (`nezuko-attention-merge-epilogue.md:1128-1140`), and its practical decode
   detection bar is ≈ 80 µs/step. A 41 µs upper bound sits at half the floor.
   PR #9's own `--local-iterate` null is the empirical demonstration.

So the honest costing of a Stage 3 timing arm on this host is: ~2 h of thermally
gated wall clock to reproduce a null that PR #9 already published, using a
strictly worse instrument, against a mechanism with a measured M4 regression and
a measured M5 regression. **I did not run it.** Spending the allocation would
have produced a wide null and no verdict, and I would rather report the closure.

### 3.5 What was done with the code

The implementation is complete but **not shipped, and not left in the tree**.
Reverting is the right call on four counts: it was default-ON
(`DARKBLOOM_DECODE_QKV_GATE_FUSED != "0"`), which would have put an unmeasured
kernel on the scored path; its call site was never wired, so it was dead code
and could not be evidence of anything; it consumed ~4.5 KB of a 104,610 B
editable headroom for zero value; and the mechanism is closed. The full diff is
preserved as research-only material at
`research/r94-artifacts/r94-qkv-gate-grid-concat-NOT-SHIPPED.patch`
(186 lines, `Sources/MLXFastModel/LagunaRuntimeModel.swift` only) so that a
future ranked-M5 discriminator slot can regenerate it without redoing the work.
If it ever is revisited, note that it already satisfies the archive's three
stated bit-exactness preconditions (`V`/`BK` preserved, byte-identical gate MSL
via the PR #48 `lagunaGateSoftplusBody` extraction pattern, verbatim bf16
boundary and softplus round-trip), and that the archive demands a **positive
reachability trace** because the upstream-equivalence oracle provably cannot
distinguish the fusion modes.

### 3.6 The pool is closed

With `gate_sp` closed by prior art, the other four entries fall to constraints
already established:

- **`prefill_router_tournament` → `residual_rms_router` (134.1 µs, 39
  dispatches)** is *unsound*, not merely unprofitable: the tournament consumes
  all 256 routed logits, which are produced across 32 sibling threadgroups, and
  Metal offers no cross-threadgroup barrier. Collapsing to a single threadgroup
  at `rpg256` would be 3-4× slower. It is also out of scope for this PR — every
  call site is in `Sources/MLXFastModel/LagunaRuntimeLayers.swift`
  (`lagunaResidualRMSNormRouter` at `:2353`/`:2450`, routed QMV/top-8 at
  `:2020-2034`), which is not in this assignment's submitted surface. The same
  file constraint kills the whole 497.1 µs partly-bytes-bound pool.
- **`rmsbfloat16` → QKV (87.9 µs, 41 dispatches)** is capped at ≤ 35.0 µs/step
  by #483, and Stage 1 of this ledger separately disproved the "second pass over
  the same 2048 floats" premise: 41 + 39 + 1 = 81 = 40×2 + 1 exactly, so there
  is no duplicate norm to delete.
- **The four lm-head stages (89.6 µs, 3 removable dispatches)** are a serially
  dependent cascade — coarse argmax → midpoint threshold → sparse refine — where
  each stage's grid depends on the previous stage's result. Grid concatenation
  cannot fuse a dependency chain.
- **Embedding / gather / layer-0 norm (5.9 µs)** is below any detection bar on
  any instrument in this campaign.

**Therefore the 592.9 µs launch/ramp pool contains no reachable win, and the
ledger's terminal conclusion is stronger than "the residue does not exist": the
decode step has no recoverable dispatch overhead at all.** 76.2 % of it runs at
90-100 % of M4 Pro peak bandwidth, 10.2 % is latency-bound attention, 6.2 % is
partly bytes-bound and out of file scope, and the 7.4 % that is overhead is now
individually closed, label by label. The next decode gain must come from
**removing bytes or restructuring attention**, not from removing dispatches.

## Suggested follow-ups (not implemented here)

1. **Retire the "residue" line of enquiry.** It is closed. Redirect the budget.
2. **Byte removal is now the only large decode lever.** 76.2 % of the step is at
   90-100 % of peak, so the next order-of-magnitude idea must remove bytes, not
   dispatches. Two concrete places: `oproj_act_h64` reads 283.1 MB/step of NVFP4
   o_proj at 96 % of peak — if `g_proj`'s gate could be folded so that o_proj
   reads a *pre-scaled* weight view, the read is unchanged, but any scheme that
   lets o_proj skip a head entirely removes 4.4 MB/head/step. Second: the routed
   top-8 gate/up read is 368.1 MB/step; the gate half is discarded for the
   inactive half of the SwiGLU only after both are read.
3. **Attention serialization is the second-largest non-bandwidth pool
   (813.0 µs, 10.2 %) and has never been profiled at the intra-kernel level.**
   Both fused attention kernels run at ~39-40 % of peak on a pure KV stream.
   Rule 41's finding that in-kernel `threadgroup_barrier` costs only
   0.0293 µs/barrier and saturates around 8 means the cost is *not* barriers; it
   is more likely the ring-buffer addressing and the softmax reduction shape.
   A dedicated intra-kernel study of `laguna_sliding_fused_attn_ring_v1` (30
   calls, 596.5 µs, 62.9 MB) is the highest-value unexplored target in the
   ledger.
4. **Fix the rule numbering** (45/46/51) in the assignment template.
5. **Fold the 1.317 µs/dispatch deflator into the research state** as a
   companion to rule 43, so future `SPLIT=1` censuses can be projected into
   `nat` magnitude without a fresh paired run.
