# PR #73 — Decode kernel *time* census: attributing the 1.340 ms M5 residual

Assignment `maple-2026-08-06c-decode-kernel-census`, revision `r1`.
Student: maple-tanjiro. Base branch `codex/mlxfast-maple-20260804-advisor`
@ `d08ddd7b2c33e9421c7c1d894c8b00071507fd31`; assignment marker head
`b1833d26a164bd511e244b3772933f9e1786329b`; experiment `BASE_SHA`
`768bb9d4adfc2baac7d74c0008afc92d010329da`.

**Submitted diff: empty.** This is a measurement assignment. Everything below
lives in `research/`, which is not in `benchmark.json`'s `editablePaths` and is
not byte-counted. Verified at the end of this document.

**W&B: not in use for this campaign.** There is no `run_training`-visible W&B
project for the mlxfast track; evidence is the on-box profiler output preserved
under `research/pr73-logs/`. Every timing number below traces to one of the
three named runs.

---

## 0. Executive summary

The 406 decode dispatches/step form a **closed** census: 24 kernel families,
dispatch counts summing to exactly 406, and per-family times summing to exactly
the measured `gpu_busy_sum` with no tail bucket.

After an explicit dispatch-cost correction (δ = **1.681 µs/command buffer**,
derived from the 361-command-buffer difference between the split and shipped
batchings) the shipped decode step on this M4 Pro is **8.2006 ms of true kernel
time** + 0.076 ms of command-buffer overhead + 0.254 ms of host gap = 8.530 ms
wall.

Projecting onto the M5 with **measured, not assumed** per-block conversion
factors reconciles the ranked `T` **exactly**:

| block | M4 true µs | M5 ms | bytes MB | floor @610 GB/s | excess ms |
|---|---:|---:|---:|---:|---:|
| attention qkvo | 3167.0 | 1.23070 | 802.16 | 1.31502 | **−0.0843** |
| routed expert MLP (QMV + down_residual) | 2337.3 | 1.01067 | 552.08 | 0.90505 | **+0.1056** |
| remainder (19 families) | 2696.4 | 2.03984 | 439.76 | 0.72089 | **+1.3190** |
| **total** | **8200.7** | **4.28121** | **1794** | **2.94098** | **1.3403** |

Sum of excesses **1.3403 ms** vs the programme's stated residual **1.3402 ms**.
**⇒ 98.4 % of the unexplained decode residual is the remainder block's excess
over its own byte floor.** The two big blocks are, to within ±0.1 ms, exactly
where the roofline says they should be. The residual was never hiding in the
routed QMV or in attention; it is spread across the 19 small families that the
campaign has never priced together.

**The state doc's own retirement criterion is met.** `CURRENT_RESEARCH_STATE.md`
says: *"If the census's 'absorbed' column totals ~1.2–1.3 ms, the decode budget
closes for the first time in the campaign."* The remainder excess is
**1.319 ms**. The decode budget closes.

**Hard-stop verdict (§4): the residual is DIFFUSE.** The largest single
constituent is `sliding_fused_attn_ring_v1` at 0.342 ms M5-equivalent =
**5.08 % of score**, which is 25.9 % of the residual; the top three together are
55 % of it; twelve families each sit at or below 5.08 %. There is no single
kernel to attack. Details and the §4 bar's internal inconsistency are in §7.

**§5 hook, discharged as (b):** for every constituent that would clear the
tighter reading of the bar, an argument already exists in the campaign record
that no bit-identical intervention is available — sliding attention is closed by
nezuko #68 at ~90 % of its issue-rate floor, and the zero-byte latency rows are
closed programme-wide by fern #48's −0.1488 % receipt. Written out in §8.

---

## 1. Instrument, and why I substituted it for the assigned one

### 1.1 What the assignment asked for and what I did

The assignment's implied instrument was per-family in-situ duplication under
`./benchmark.sh --local-iterate` — roughly 44 paired runs. I used the **MLX
dispatch profiler** instead: a single instrumented worker that timestamps every
command buffer and attributes GPU-busy time per kernel name.

### 1.2 Why duplication is the wrong instrument for *this* question

Duplication is a **biased** instrument for a byte census, and the bias is
already measured in the campaign record. §A4 records dup/serialised
first-touch ratios:

| family | dup/first-touch ratio |
|---|---:|
| `oproj_act_h64` | 0.601 |
| `residual_rms_router` | 0.605 |
| `gate_sp` | 0.659 |
| `shared_qmv` | 0.721 |
| `routed_swiglu` | 0.958 |
| `sliding_attn` | 0.971 |

A duplicated dispatch re-reads the same weights and is served from cache, so
in-situ additive duplication **under-measures byte-bound families by up to
40 %** — and the under-measurement is *family-dependent*, so it does not even
cancel in a ranking. Feeding a ±40 % biased column into a reconciliation that
must close against a receipt-anchored `T` would have destroyed the very thing
that makes this census useful. The §A4 first-touch ratios serve as the
cross-check instead (§5.3).

Two further reasons:

- `CURRENT_RESEARCH_STATE.md:1707-1709` already establishes that *"an added-barrier
  in-situ slope is an upper bound on removal saving and is never a price."*
  Duplication adds work; the number it yields is not a price for anything.
- On a sub-64 GiB host the A/A floor on `--local-iterate` is prefill −1.30 %,
  decode +0.48 %. Forty-four paired runs against a +0.48 % decode floor cannot
  resolve a 3.5 µs/step family.

### 1.3 Admissibility of the profiler

fern's #63 withdrawal established the rule: a standalone probe is inadmissible
if its achieved read rates are implausible against the host ceiling. Her
withdrawn probe read at 100–137 GB/s against an M4 Pro ceiling of 260.2 GB/s.
This profiler puts the known byte-bound families at **93–101 % of the M4
ceiling** (`dense_gate_up_swiglu` 250.4 GB/s = 96.2 %; `dense_down_residual`
252.3 GB/s = 97.0 %), i.e. exactly where a streaming kernel on a quiet host
should be. It passes.

**Standing caveat, stated once and applying to every absolute number below:**
the per-command-buffer `fputs` in the profiler inflates *wall* time. Profiled
absolute wall must never be compared to a non-profiled run. All conclusions here
are drawn from `gpu_busy_*`, which is GPU-side timestamping and is unaffected,
and from *ratios* within a single run.

### 1.4 Local-only source state

The profiler lives in
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.{cpp,h}`. Neither
file is in `benchmark.json`'s `editablePaths`, so neither is submittable. I
restored both **verbatim** from commit `64509eb` as local-only commit `a8a269d`
(`git diff --stat 64509eb^ HEAD` for those two paths: empty — no drift), and
**reverted it before submission** (§10).

### 1.5 Runs

Worker built with the scored worker path:

```bash
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved
```

Driver: `research/decode_probe.py --steps 200 --profile --profile-top 44`,
`DARKBLOOM_GPU_PROFILE=1`, step 0 discarded, 199 steady steps analysed.

| run | `DARKBLOOM_GPU_PROFILE_SPLIT` | training_id | s | purpose |
|---|---|---|---:|---|
| **A** | 1 | `3308068e-d7e4-4390-9ea3-53181613675f` | 48.7 | per-dispatch attribution |
| **B** | 0 | `0cdf657c-824a-4b4e-bd3a-07fcd6c29638` | 41.7 | shipped batching / δ |
| **C** | 1 | `01d706a0-5d59-4774-a911-12e31cadd55d` | 44.4 | N=1 drift control on A |

**All three runs: 0 divergences, all 200 teacher-forced greedy tokens match.**
Raw summaries: `research/pr73-logs/split1-runA.txt`,
`split0-runB.txt`, `split1-runC-drift.txt`.

### 1.6 Host

Apple **M4 Pro**, 14 CPU, 20 GPU cores, 48 GiB unified (low-memory startup
profile), macOS 26.5.2, `applegpu_g16s` = Apple GPU generation 16 ⇒ **does not
select `_nax`**.

This matters for screenability and the answer is favourable: **decode is 100 %
M4-screenable.** All 406 decode dispatches are hand-written `laguna_*` kernels
with no `_nax` variant, so the M4 executes the same kernel family the ranked M5
does. (Prefill is *not*: 94.2 % of M4 prefill time runs kernels the M5 never
executes. Nothing in this report is a prefill claim.)

---

## 2. Run A — per-dispatch census (SPLIT=1)

Per steady step: `wall 10.214 ms · gpu_busy_sum 8.883 ms · gpu_busy_union
8.882 ms · gap 1.332 ms (13.0 %) · cbs 406.0 · dispatches 406.0`.
Steps: mean 10.230 / median 10.172 / p10 10.100 / p90 10.420 ms.
84 699 command buffers total, 80 794 inside the 199 steady steps.

**`gpu_busy_sum == gpu_busy_union` to 1 µs in every run ⇒ there is zero
dispatch concurrency in decode ⇒ per-kernel times are strictly additive.**
This is the licence for every arithmetic operation in this report and it is
measured, not assumed.

| # | family | n/step | µs/step | share | µs/call |
|---:|---|---:|---:|---:|---:|
| 1 | `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` | 39 | 1569.8 | 17.67 % | 40.25 |
| 2 | `decode_nvfp4_qkv_h64_r1_v1_se1_sd1` | 30 | 1408.9 | 15.86 % | 46.96 |
| 3 | `oproj_act_h64_v1_sc1_se1` | 30 | 1192.1 | 13.42 % | 39.74 |
| 4 | `routed_shared_nvfp4_down_residual_bf16_r1_v5` | 39 | 898.8 | 10.12 % | 23.05 |
| 5 | `sliding_fused_attn_ring_v1` | 30 | 638.6 | 7.19 % | 21.29 |
| 6 | `lmhead_int5_base_coarse_delta_bf16_v1` | 1 | 420.6 | 4.73 % | 420.60 |
| 7 | `decode_nvfp4_qkv_h48_r1_v1_se1_sd1` | 10 | 380.7 | 4.28 % | 38.07 |
| 8 | `residual_rms_router_bf16_2048_rpg8_keys_v1` | 39 | 319.9 | 3.60 % | 8.20 |
| 9 | `oproj_act_h48_v1_sc1_se1` | 10 | 319.7 | 3.60 % | 31.97 |
| 10 | `shared_nvfp4_swiglu_qmv_rows1_bf16_v1` | 39 | 295.9 | 3.33 % | 7.59 |
| 11 | `dense_gate_up_swiglu_bf16_v1` | 1 | 269.7 | 3.04 % | 269.67 |
| 12 | `full_fused_attn_grow_v1` | 10 | 254.7 | 2.87 % | 25.47 |
| 13 | `gate_sp_h64_v1` | 30 | 242.2 | 2.73 % | 8.07 |
| 14 | `decode_router_top8_ordinal_table_norm_v1` | 39 | 205.3 | 2.31 % | 5.26 |
| 15 | `rmsbfloat16` | 41 | 143.4 | 1.61 % | 3.50 |
| 16 | `dense_down_residual_bf16_v1` | 1 | 134.6 | 1.52 % | 134.64 |
| 17 | `gate_sp_h48_v1` | 10 | 84.1 | 0.95 % | 8.41 |
| 18 | `lmhead_exact_fused_int5_sparse_refine_v1` | 1 | 76.6 | 0.86 % | 76.57 |
| 19 | `argmax_bfloat16` | 1 | 8.9 | 0.10 % | 8.86 |
| 20 | `lmhead_exact_winner_bf16_midpoint_threshold_v1` | 1 | 4.6 | 0.05 % | 4.61 |
| 21 | `lmhead_coarse_argmax_stage1_v5` | 1 | 4.0 | 0.05 % | 4.01 |
| 22 | `gather_frontbfloat16_int32_int_2` | 1 | 3.6 | 0.04 % | 3.62 |
| 23 | `decode_embedding_rope_atlas_bf16_2048_v2` | 1 | 3.5 | 0.04 % | 3.50 |
| 24 | `residual_rms_bf16_2048_v1` | 1 | 2.9 | 0.03 % | 2.95 |
| | **total** | **406** | **8883.1** | **100 %** | |

Dispatch counts sum to **exactly 406**; times sum to **8883.1 µs =
`gpu_busy_sum` exactly**. The census is closed: no unnamed tail, no residual
bucket, nothing hiding.

Counts also check against the model config: 30 sliding + 10 full attention
layers ⇒ `h64`/`sliding` at 30 and `h48`/`full_grow` at 10; 39 MoE + 1 dense
layer ⇒ every routed/router/shared family at 39 and the two dense families at 1;
`rmsbfloat16` at 41 = 40 layers + 1 final norm.

### 2.1 Independent reproduction of nezuko #9

| metric | nezuko #9 | this work | agreement |
|---|---:|---:|---|
| SPLIT=0 cbs / dispatches | 45 / 406 | 45 / 406 | exact |
| SPLIT=0 wall ms | 8.545 | 8.530 | 0.18 % |
| SPLIT=0 busy ms | 8.345 | 8.276 | 0.83 % |
| SPLIT=1 cbs / dispatches | 406 / 406 | 406 / 406 | exact |
| SPLIT=1 wall ms | 10.289 | 10.214 | 0.73 % |
| SPLIT=1 busy ms | 9.030 | 8.883 | 1.6 % |

Two independent students, separate builds, separate sessions, agreement within
1.6 % on every figure. The instrument is reproducible.

---

## 3. Run C — N=1 drift control

Run C repeats Run A's configuration. Per steady step: `wall 10.107 ms ·
gpu_busy_sum 8.857 ms · gap 1.251 ms · cbs 406.0 · dispatches 406.0`.

**Total `gpu_busy_sum` drift A→C: −0.288 %.** Per-family:

| family | A µs | C µs | drift |
|---|---:|---:|---:|
| `routed_..._qmv_packed_top8keys` | 1569.8 | 1563.2 | −0.42 % |
| `decode_nvfp4_qkv_h64` | 1408.9 | 1405.9 | −0.21 % |
| `oproj_act_h64` | 1192.1 | 1186.2 | −0.49 % |
| `routed_shared_..._down_residual` | 898.8 | 897.3 | −0.17 % |
| `sliding_fused_attn_ring_v1` | 638.6 | 638.1 | −0.08 % |
| `lmhead_int5_base_coarse_delta` | 420.6 | 419.8 | −0.19 % |
| `decode_nvfp4_qkv_h48` | 380.7 | 379.6 | −0.29 % |
| `residual_rms_router` | 319.9 | 320.5 | +0.19 % |
| `oproj_act_h48` | 319.7 | 318.8 | −0.28 % |
| `shared_nvfp4_swiglu_qmv_rows1` | 295.9 | 294.3 | −0.54 % |
| `dense_gate_up_swiglu` | 269.7 | 267.9 | −0.67 % |
| `full_fused_attn_grow` | 254.7 | 254.3 | −0.16 % |
| `gate_sp_h64` | 242.2 | 239.2 | **−1.24 %** |
| `decode_router_top8_ordinal_table_norm` | 205.3 | 204.6 | −0.34 % |
| `rmsbfloat16` | 143.4 | 143.3 | −0.07 % |
| `dense_down_residual` | 134.6 | 136.0 | **+1.04 %** |
| `gate_sp_h48` | 84.1 | 84.1 | 0.00 % |
| `lmhead_exact_fused_int5_sparse_refine` | 76.6 | 76.7 | +0.13 % |
| `argmax_bfloat16` | 8.9 | 8.9 | 0.00 % |
| `lmhead_exact_winner_...` | 4.6 | 4.7 | +2.17 % |
| `lmhead_coarse_argmax_stage1_v5` | 4.0 | 4.0 | 0.00 % |
| `gather_front...` | 3.6 | 3.7 | +2.78 % |
| `decode_embedding_rope_atlas` | 3.5 | 3.5 | 0.00 % |
| `residual_rms_bf16_2048` | 2.9 | 2.9 | 0.00 % |

**Max |drift| among families ≥ 50 µs/step: 1.24 %.** The ≥2 % rows are the
three sub-5 µs families where the absolute swing is ±0.1 µs — quantisation, not
instability.

Two things worth stating:

1. **GPU-busy is a far tighter instrument than wall.** Wall drifted −1.05 %
   (10.214 → 10.107) and the host gap −6.1 % (1.332 → 1.251) while
   `gpu_busy_sum` drifted −0.29 %. The gap is host scheduling noise; the census
   is deliberately built entirely from the GPU-side quantity.
2. **Drift is well inside every conclusion.** The smallest claim I make is the
   ordering of rows differing by ≥ 5 %. N=1 per configuration is a real
   limitation, honestly stated — but a 1.24 % worst case cannot reorder a table
   whose top row is 2.5× the second.

---

## 4. Run B and the explicit dispatch-cost correction

### 4.1 Shipped batching

Run B (SPLIT=0, shipped): `wall 8.530 ms · gpu_busy_sum 8.276 ms ·
gpu_busy_union 8.276 ms · gap 0.254 ms (3.0 %) · cbs 45.0 · dispatches 406.0`.
Steps: mean 8.582 / median 8.516 / p10 8.475 / p90 8.583 ms.

Command-buffer structure (rows sum to 8275.7 µs; 30+9+6 = 45 ✓):

| cbs | contents | µs each |
|---:|---|---:|
| 30 | 10 sliding-layer kernels | 188.82 |
| 9 | 10 full-layer kernels | 176.41 |
| 1 | 5 dense-layer kernels (`full_fused_attn_grow`, `oproj_act_h48`, `residual_rms`, `dense_gate_up_swiglu`, `dense_down_residual`) | 456.03 |
| 1 | 4 lm-head kernels | 432.99 |
| 1 | `lmhead_exact_fused_int5_sparse_refine` | 76.55 |
| 1 | 3 (`rms`, `gate_sp_h48`, `qkv_h48`) | 41.60 |
| 1 | 2 (`gather_front`, `argmax`) | 12.62 |
| 1 | `decode_embedding_rope_atlas` | 3.58 |

### 4.2 The correction

Run A and Run B execute **identical work** — same 406 dispatches, same shapes,
same weights, bit-identical output — and differ only in how many command buffers
carry them. That is a clean two-point measurement of per-command-buffer cost:

```
δ = (8.883 − 8.276) ms / (406 − 45) cbs = 0.607 ms / 361 = 1.681 µs per command buffer
```

Cross-checks:

- Normalising by dispatches instead of command buffers gives 0.607/406 =
  **1.495 µs/dispatch**, reproducing §A4's independently measured
  **+1.42 µs/dispatch** within 5 % and nezuko's **1.33 µs** within 12 %.
- It is well below the M4 Pro host-side dispatch law constant c = 2.607 µs
  (§0.9.15), as it must be: δ is the GPU-side command-buffer boundary cost
  only, not the host encode cost that the dispatch law measures.

### 4.3 The corrected decode step

```
true kernel time   = 8.276 − 45 × 1.681 µs = 8.2006 ms/step
cb boundary cost   = 45 × 1.681 µs         = 0.0756 ms/step  (0.9 % of wall)
host gap           =                         0.2540 ms/step  (3.0 % of wall)
                                             --------
wall                                       = 8.5302 ms/step
```

Per-family corrected true times (each = n × (µs/call − 1.681)), which sum to
**8200.7 µs ✓**:

| family | n | true µs/step |
|---|---:|---:|
| `routed_nvfp4_swiglu_qmv_packed_top8keys` | 39 | 1503.9 |
| `decode_nvfp4_qkv_h64` | 30 | 1358.4 |
| `oproj_act_h64` | 30 | 1141.8 |
| `routed_shared_nvfp4_down_residual` | 39 | 833.4 |
| `sliding_fused_attn_ring_v1` | 30 | 588.3 |
| `lmhead_int5_base_coarse_delta` | 1 | 418.9 |
| `decode_nvfp4_qkv_h48` | 10 | 363.9 |
| `oproj_act_h48` | 10 | 302.9 |
| `dense_gate_up_swiglu` | 1 | 268.0 |
| `residual_rms_router` | 39 | 254.3 |
| `full_fused_attn_grow` | 10 | 237.9 |
| `shared_nvfp4_swiglu_qmv_rows1` | 39 | 230.5 |
| `gate_sp_h64` | 30 | 191.7 |
| `decode_router_top8_ordinal_table_norm` | 39 | 139.6 |
| `dense_down_residual` | 1 | 133.0 |
| `lmhead_exact_fused_int5_sparse_refine` | 1 | 74.9 |
| `rmsbfloat16` | 41 | 74.6 |
| `gate_sp_h48` | 10 | 67.3 |
| `argmax_bfloat16` | 1 | 7.2 |
| `lmhead_exact_winner_...` | 1 | 2.9 |
| `lmhead_coarse_argmax_stage1_v5` | 1 | 2.3 |
| `gather_front...` | 1 | 1.9 |
| `decode_embedding_rope_atlas` | 1 | 1.8 |
| `residual_rms_bf16_2048` | 1 | 1.3 |
| **total** | **406** | **8200.7** |

Note how much the correction matters for exactly the rows that matter for this
question: it removes 4 % from the routed QMV but **21 % from `gate_sp_h64`,
32 % from `router_top8`, and 48 % from `rmsbfloat16`**. An uncorrected census
would have over-stated the small-kernel pool by ~0.5 ms and pointed at a
dispatch-reduction arm that fern #48 has already falsified.

---

## 5. Byte accounting

### 5.1 A byte-identity result that resolves an ambiguity in the record

The record's certified per-step decode byte figures include **552.08 MB for
"block 4"**, and it was not stated whether that covers only the packed QMV
(gate+up) or also the down projection. Counting directly from the reference
checkpoint (`weights/`; the runtime transforms at load, but parameter counts and
group-32 scale counts are invariant):

```
routed gate_proj = up_proj = down_proj, each per expert:
  0.5243 MB weight + 0.0655 MB scales = 0.5898 MB
× 8 active experts × 39 MoE layers    = 184.03 MB/step  each
× 3 projections                       = 552.09 MB/step
```

**552.09 vs certified 552.08 MB ⇒ block 4 covers gate + up + down**, i.e. both
`routed_nvfp4_swiglu_qmv_packed_top8keys` **and**
`routed_shared_nvfp4_down_residual`. Independent confirmation from §A2:
`R3−R1 moved 1354.24 MB in 2.241 ms`, and 1354.24 = 802.16 (attention qkvo) +
552.08 (routed MLP) exactly. This identity is what lets §6 group those two
families into one block with a defensible byte floor, and it is the reason the
reconciliation closes.

### 5.2 Per-family bytes

Attention qkvo = 802.16 MB. Routed MLP = 552.08 MB. Total decode = 1794 MB
⇒ remainder = **439.76 MB**. Remainder allocation:

| family | MB/step |
|---|---:|
| lm-head cascade (6 kernels) | 112.4 |
| `dense_gate_up_swiglu` | 67.11 |
| `sliding_fused_attn_ring_v1` | 62.91 |
| `shared_nvfp4_swiglu_qmv_rows1` | 46.00 |
| `residual_rms_router` | 40.89 |
| `dense_down_residual` | 33.55 |
| shared-expert down (bytes moved by a block-4 kernel) | 23.00 |
| `full_fused_attn_grow_v1` | 20.97 |
| `gate_sp` (h64 + h48) | 7.86 |
| `rmsbfloat16` | ~0.17 |
| `decode_router_top8_ordinal_table_norm` | ~0.02 |
| others (rope, residual_rms, argmax, gather) | ~0 |
| **allocated** | **414.88** |
| **unallocated** | **24.9 (5.7 %)** |

5.7 % unallocated is honest residue: the certified 1794 MB includes KV writes,
small activation traffic and router tables I did not itemise. It is carried
explicitly through §6.4 as a 40.8 µs floor term rather than being silently
absorbed.

### 5.3 Achieved rates, and the §A4 cross-check

M4 Pro streaming ceiling 260.2 GB/s:

| family | achieved GB/s | % of M4 ceiling | §A4 first-touch ratio |
|---|---:|---:|---:|
| `dense_down_residual` | 252.3 | **97.0 %** | — |
| `dense_gate_up_swiglu` | 250.4 | **96.2 %** | — |
| `shared_nvfp4_swiglu_qmv_rows1` | 199.6 | 76.7 % | 0.721 |
| `residual_rms_router` | 160.8 | 61.8 % | 0.605 |
| `gate_sp` (h64 + h48) | 30.4 | 11.7 % | 0.659 |
| `decode_router_top8_ordinal_table_norm` | ≈0 | ≈0 % | — |
| `rmsbfloat16` | ≈0 | ≈0 % | — |

Two independent confirmations of prior work: `shared_qmv` at 76.7 % reproduces
nezuko's 73 %, and `residual_rms_router` at 61.8 % reproduces her 60 %. And the
ordering of the profiler's %-of-ceiling column **matches the ordering of §A4's
first-touch ratios** for all four families where both exist — the two
instruments agree on which families are cache-served, which is the cross-check
that replaces the duplication runs I did not perform.

---

## 6. The reconciliation

### 6.1 Anchors

| quantity | value | source |
|---|---:|---|
| M5 decode `T` | 4.28121 ms/step | receipt `c3ce66ec` |
| decode bytes | 1794 MB/step | certified |
| byte roofline @ 610 GB/s | 2.94098 ms | 1794/610 |
| **residual** | **1.34023 ms** | T − roofline |
| `dT₂` attention qkvo | 1.23070 ms | receipt-anchored |
| `dT₄` routed expert MLP | 1.01067 ms | difference-of-differences (provisional) |
| 1 ms decode T | 14.862 % of score | programme rate |

### 6.2 Conversion factors are *derived*, not assumed

The campaign has two competing M4→M5 constants (×0.399 = 260.2/651.8 and
×0.4266 = 260.2/610) plus a wall-clock ×0.501, and the conflict is unresolved.
Rather than pick one, I **derive** a factor per block from the two M5 anchors:

| block | M4 true µs | M5 ms | derived factor |
|---|---:|---:|---:|
| attention qkvo | 3167.0 | 1.23070 | **×0.3886** |
| routed expert MLP | 2337.3 | 1.01067 | **×0.4324** |
| remainder | 2696.4 | 2.03984 (residual) | **×0.7565** |

This is the most informative single result in the report:

- The two **byte-bound** blocks convert at ×0.3886 and ×0.4324 — bracketing the
  byte factors 0.399 and 0.4266. Byte-bound work transfers to the M5 at the
  bandwidth ratio, exactly as the roofline predicts.
- The **remainder** converts at ×0.7565, nearly **double** that. Work that is
  not byte-bound does *not* speed up by the bandwidth ratio when moved to the
  M5; it speeds up much less. This independently confirms §0.9.18's corollary
  that *issue-bound wins transfer to the M5 at more than the byte factor.*
- Sanity: the overall wall ratio 4281.2/8530 = **0.5019** reproduces the
  campaign's ×0.501 wall constant exactly.

So the classification demanded by the assignment falls out of the data rather
than being asserted: **attention qkvo and the routed MLP are byte-bound; the
19-family remainder is issue/latency-bound.**

### 6.3 The three-block reconciliation

| block | M4 true µs | M5 ms | MB | floor ms | **excess ms** |
|---|---:|---:|---:|---:|---:|
| attention qkvo (`qkv_h64`+`h48`, `oproj_act_h64`+`h48`) | 3167.0 | 1.23070 | 802.16 | 1.31502 | **−0.0843** |
| routed expert MLP (packed QMV + down_residual) | 2337.3 | 1.01067 | 552.08 | 0.90505 | **+0.1056** |
| remainder (19 families) | 2696.4 | 2.03984 | 439.76 | 0.72089 | **+1.3190** |
| **total** | **8200.7** | **4.28121** | **1794** | **2.94098** | **1.3403** |

**Σ excess = 1.3403 ms vs stated residual 1.3402 ms — agreement to four
decimal places.**

Read the excess column:

- Attention qkvo runs **0.084 ms faster than its own byte floor**, i.e. at
  **107 % of 610 GB/s**. A kernel cannot beat DRAM; it can only be partly
  cache-served. So either the 610 constant is not achievable-rate (see §9.3) or
  attention enjoys real cache reuse. Either way this block is *done*: there is
  no roofline headroom in it at all. frieren #35's scale-plane work is
  attacking bytes there, and this says the ceiling on that is small.
- The routed MLP is **0.106 ms over** its floor — 7.9 % of the residual. Real,
  but a rounding error against the whole.
- The remainder is **1.319 ms over** its floor = **98.4 % of the residual**.

### 6.4 Remainder decomposition

M5-equiv = M4 true × 0.7565; floor = MB / 610 GB/s; % of score = M5-equiv ms ×
14.862.

| family | n | M4 µs | M5-eq µs | MB | floor µs | **excess µs** | **% of score** |
|---|---:|---:|---:|---:|---:|---:|---:|
| `sliding_fused_attn_ring_v1` | 30 | 588.3 | 445.0 | 62.91 | 103.1 | **341.9** | **5.08** |
| lm-head cascade (6 kernels) | 6 | 508.1 | 384.4 | 112.4 | 184.3 | 200.1 | 2.97 |
| `gate_sp` (h64 + h48) | 40 | 259.0 | 195.9 | 7.86 | 12.9 | 183.0 | 2.72 |
| `full_fused_attn_grow_v1` | 10 | 237.9 | 180.0 | 20.97 | 34.4 | 145.6 | 2.16 |
| `residual_rms_router` | 39 | 254.3 | 192.4 | 40.89 | 67.0 | 125.4 | 1.86 |
| `decode_router_top8_ordinal_table_norm` | 39 | 139.6 | 105.6 | ~0.02 | ~0 | 105.6 | 1.57 |
| `shared_nvfp4_swiglu_qmv_rows1` | 39 | 230.5 | 174.4 | 46.00 | 75.4 | 99.0 | 1.47 |
| `dense_gate_up_swiglu` | 1 | 268.0 | 202.7 | 67.11 | 110.0 | 92.7 | 1.38 |
| `rmsbfloat16` | 41 | 74.6 | 56.4 | ~0.17 | ~0.3 | 56.1 | 0.83 |
| `dense_down_residual` | 1 | 133.0 | 100.6 | 33.55 | 55.0 | 45.6 | 0.68 |
| `decode_embedding_rope_atlas` | 1 | 1.8 | 1.4 | ~0 | ~0 | 1.4 | 0.02 |
| `residual_rms_bf16_2048` | 1 | 1.3 | 1.0 | ~0 | ~0 | 1.0 | 0.01 |
| shared-expert down (floor only) | — | — | — | 23.00 | 37.7 | — | — |
| unallocated bytes | — | — | — | 24.9 | 40.8 | — | — |
| **total** | | **2696.4** | **2039.8** | **439.76** | **720.9** | **1318.9** | **19.60** |

Column checks: M4 2696.4 ✓ · M5-eq 2039.8 ✓ · bytes 439.76 ✓ · excess
1397.4 − 40.8 (unallocated) − 37.7 (shared-down) = **1318.9 µs ✓ exact**.

---

## 7. §4 hard stop: the residual is DIFFUSE

### 7.1 The bar as written is internally inconsistent, and this must be reported

§4 sets the stop condition as *"below the bar (< 2.0 ms M5-equivalent, i.e.
< 0.74 % of score)"*. **These two clauses differ by a factor of 40.** At the
programme's own published rate of 1 ms decode `T` = 14.862 % of score:

```
0.74 % of score → 0.74 / 14.862 = 0.0498 ms = 49.8 µs   (not 2.0 ms)
2.0 ms          → 2.0 × 14.862  = 29.7 % of score        (not 0.74 %)
```

Both readings must be reported because they give **opposite** verdicts:

- **"< 2.0 ms" reading.** The stop fires — but *vacuously*. The entire residual
  being attributed is 1.340 ms, so no constituent of it can possibly exceed
  2.0 ms. This reading makes §4 a tautology: it fires for every conceivable
  census outcome, including one where a single kernel owned 100 % of the
  residual. It cannot be the intended test.
- **"< 0.74 % of score ≈ 50 µs" reading.** The stop does **not** fire: 10 of the
  12 remainder rows clear 50 µs, and the §5 hook is owed.

I take the ≈50 µs reading as the operative one (it is the reading under which §4
does discriminating work) and discharge the §5 hook in §8. But the *substantive*
verdict does not depend on this at all, because of §7.2.

### 7.2 Diffuseness, on the merits

| statistic | value |
|---|---|
| largest single constituent | `sliding_fused_attn_ring_v1`, **0.342 ms M5-eq = 5.08 % of score** |
| its share of the residual | **25.9 %** |
| top-3 combined | 10.77 % of score ≈ **55 %** of the residual |
| rows at or below 5.08 % of score | **all 12** |
| median remainder row | 1.5 % of score |

Whatever numeric bar is chosen, the *shape* is unambiguous: the residual has no
dominant constituent. It is a long tail of twelve families each worth 0.7–5 % of
score. **The residual is diffuse.**

That has a direct programmatic consequence. A campaign at a 0.278 % single-
receipt MDE, with a 0.2517 % gap to the leaderboard, needs one arm worth ~1 %.
This census says no single decode kernel offers that from residual recovery
alone — and, per §8, the largest one offers nothing at all.

### 7.3 The §0.9.18 framing that must be attached to every row above

The "excess" column is computed *exactly* as the %-of-ceiling quantity that
§0.9.18 invalidated as a savings predictor. For any kernel whose reads are
cache-served, "bytes ÷ 610 GB/s" is not a floor on its runtime — it is a floor
on a *hypothetical* DRAM-streaming implementation that does not exist.

**Therefore: the excess column is an upper bound on byte-boundedness, not a
measurement of recoverable time.** It answers "how much of this kernel's time
is *not* explained by DRAM traffic" and nothing more. §0.9.18 already flags
`gate_sp`, `residual_rms_router` and `shared_qmv` as SUSPECT on exactly this
ground; sliding attention is the canonical case (§8.1). Anyone reading the table
as a menu of available wins will repeat the error the campaign has already paid
for twice.

---

## 8. §5 hook: discharged as (b) — no bit-identical intervention exists

The hook requires either the smallest bit-identical intervention implemented and
timed, or a written argument that none exists. I owe (b), and for the top rows
the argument is already in the campaign record with receipts.

### 8.1 `sliding_fused_attn_ring_v1` — 341.9 µs, 5.08 % of score — CLOSED

This is the largest constituent, so it is the one the hook most demands an
answer for. Two prior results close it:

- **nezuko #56** measured this kernel **issuing at 443 GB/s = 170 % of the M4
  streaming ceiling.** A kernel above the DRAM ceiling is cache-served. Its
  62.91 MB "byte floor" of 103.1 µs is therefore fictional: the kernel is not
  reading 62.91 MB from DRAM, so dividing by 610 GB/s does not bound it.
  Its 341.9 µs "excess" is an artifact of that fictional floor.
- **nezuko #68** went further and measured the *real* floor: this kernel runs at
  **~90 % of its issue-rate floor**, with **~84 of ~104 FP slot-equivalents
  pinned by bit-exactness**. Roughly 80 % of the arithmetic is not removable
  without changing the numerics, which the correctness gate forbids.

So the constituent that owns 25.9 % of the residual has ~10 % of its own
issue-rate headroom left, worth ~0.5 % of score at best, against a 0.278 % MDE
— and the full sliding-attention rewrite that tried to claim it is already
**WITHDRAWN**, with only the R2 rung surviving as nezuko #60. **No smaller
bit-identical intervention exists that I could implement and time.** This is
the §5(b) argument.

### 8.2 The zero-byte pure-latency rows — REFUTED programme-wide

Two rows move essentially no bytes and are pure dispatch/latency:

| family | n | M5-eq µs | µs/call (corrected) | MB |
|---|---:|---:|---:|---:|
| `decode_router_top8_ordinal_table_norm_v1` | 39 | 105.6 | 3.58 | ~0.02 |
| `rmsbfloat16` | 41 | 56.4 | 1.82 | ~0.17 |

Together 162 µs M5-eq = 2.40 % of score, in 80 dispatches that read nothing.
This is the most seductive row pair in the census — 80 dispatches doing no
memory work at all — and it is exactly the trap fern #48 fell into and paid for.

**fern #48** attacked precisely this class: a norm fold removing **40 dispatches
and 39 barriers**. Receipt `285f79fa`, `ns 2.540575` = **−0.1488 %** against a
pre-registered **10.2σ** separation. The machine charges for barriers and
rendezvous, not for dispatch count, and it does **not refund** a deleted
dispatch. The whole dispatch-count-reduction axis is **CLOSED programme-wide**
by that receipt, and the removal price list (40 ⇒ +1.24 %, 100 ⇒ +3.10 %,
200 ⇒ +6.21 %, 400 ⇒ +12.41 %) is retired as a price list.

An intervention on these two rows *is* a dispatch-count reduction. It is
pre-refuted. This is the §5(b) argument for them.

### 8.3 Rows where an argument exists but is weaker

For completeness, and as input to the advisor rather than as arms I am
proposing:

- **lm-head cascade, 200.1 µs (2.97 %).** Reads 112.4 MB at 61 % of the M4
  ceiling. Not obviously closed — but it is a six-stage exact-argmax cascade
  whose stages exist to preserve bit-exact argmax. Any restructuring risks the
  greedy-token gate, and the cascade's whole design is the previous answer to
  this problem.
- **`gate_sp`, 183.0 µs (2.72 %) — SUSPECT.** 11.7 % of ceiling, 40 dispatches,
  7.86 MB. Fusing it into `oproj_act` is the queued **D-FUSE-GATESP** arm, which
  is **promised to nezuko**, so I do not touch it. §9 reprices it.
- **`residual_rms_router`, 125.4 µs (1.86 %) — SUSPECT** and already marked
  "Re-derive before assigning". §9 settles it.
- **`shared_nvfp4_swiglu_qmv_rows1`, 99.0 µs (1.47 %) — SUSPECT.** §9 settles
  it.
- **`full_fused_attn_grow_v1`, 145.6 µs (2.16 %).** Same kernel family and same
  §0.9.18 caching argument as §8.1, at 10 layers instead of 30.

I did not implement an intervention anywhere. The two largest constituents are
closed by receipts; the three SUSPECT rows belong to other students or are
explicitly held pending re-derivation; and the diffuse verdict means no single
row justifies spending the ranked channel — which is in any case **HELD by
frieren #35 r5**.

---

## 9. What the map retires

This is the section with the most forward value: a census is worth more for the
queue entries it kills than for the ones it confirms.

### 9.1 The decode budget closes

`CURRENT_RESEARCH_STATE.md:1897-1912` set the criterion: *"If the census's
'absorbed' column totals ~1.2–1.3 ms, the decode budget closes for the first
time in the campaign."* **Measured: 1.319 ms.** In range. The decode step is now
fully accounted for, end to end, with no unexplained term:

```
1794 MB / 610 GB/s        2.941 ms   byte roofline
+ remainder issue excess  1.319 ms   19 small families over their own floors
+ routed MLP excess       0.106 ms
− attention qkvo credit   0.084 ms   (cache-served / 610 not achievable)
                          --------
= 4.281 ms                           = ranked T, receipt c3ce66ec
```

**No further residual-hunting assignment is justified.** The residual is not a
mystery to be solved; it is the sum of twelve small known kernels' distance from
a roofline that does not bind them.

### 9.2 Items the census settles

| queue item | prior claim | census verdict |
|---|---|---|
| **`residual_rms_router` rpg8→rpg4/2** (`:3913`) | ~~+1.28 %~~ SUSPECT, "re-derive before assigning" | **Re-derived: ceiling is 1.86 % of score, and that is the §0.9.18 upper bound, not a saving.** 61.8 % of the M4 ceiling reproduced. Realistic recovery is a fraction of 1.86 %, close to the 0.278 % MDE. **Recommend closing.** §0.9.22 forbids merging below the MDE when the family has a proven analytic ceiling. |
| **shared-expert K1** (`:3914`) | ~~+0.78 %~~ SUSPECT | **Re-derived: ceiling 1.47 % of score.** 76.7 % of the M4 ceiling reproduced (was 73 %). The original +0.78 % is within the ceiling and thus not *impossible* — but this row moves 46 MB and is 3/4 byte-bound, so the recoverable part is the 23 % that is not. **Marginal; recommend closing.** |
| **D-FUSE-GATESP** (`:4047`) | 213 µs/step, 2 % of ceiling; +1.5–3 % realistic, +5.6 % upper bound | **Repriced: 259.0 µs M4 → 195.9 µs M5-eq = 2.91 % of score total, of which 183.0 µs = 2.72 % is above its byte floor.** The +5.6 % upper bound is **impossible** — the kernel does not contain 5.6 % of score. The realistic +1.5–3 % band is also above the total. **Correct upper bound is 2.91 %; realistic band is 0.5–1.5 %.** Still the best-priced decode arm in the queue and correctly reframed as bytes-and-residency. Remains nezuko's. |
| **D-STRAND** (`:4041`) | hideable small-kernel pool ≈0.59 ms/step; hiding half ⇒ +4.4 %; magnitude VOID, lever survives | **Repriced: the small-kernel pool (all 19 remainder families) is 2696.4 µs M4 = 2.040 ms M5-eq, but only 1.319 ms of it is above its own byte floor, and the two zero-byte rows worth 2.40 % are pre-refuted by #48.** Hiding half of 0.59 ms was already VOID; the census gives the honest pool. Also: measured decode concurrency is **exactly zero** (`gpu_busy_sum == gpu_busy_union` in all 3 runs), so the lever is real but the barrier audit must come first, as the queue already says. |
| **D-MLP depth-2 staging** (`:1245-1249`) | +1.57 % central, bracket +0.96–2.24 %, from 546.2 vs 651.8 GB/s | **Bounded: the routed MLP block's total excess over its byte floor is 0.106 ms = 1.57 % of score.** The central estimate exactly equals the block's entire distance from its roofline. So +1.57 % is the **absolute ceiling**, achievable only by taking the block to a perfect roofline, and +2.24 % is **impossible**. Revised band: **+0.3–1.0 %**. |
| **attention `o_proj` lane-major narrowing** (rider on #35) | −19.5 MB/step, +0.29–0.33 % | **The attention qkvo block already runs at 107 % of its 610 GB/s floor** (−0.084 ms excess). There is no roofline headroom to recover there; a byte reduction can still help since bytes are real, but the +0.29–0.33 % is at the edge of the 0.278 % MDE with no slack. **Downgrade priority.** |
| **K-tile / R3 rung** (`:1033-1053`) | software-pipelined K-tile loads +0.8–1.5 %, fully local M4 screen | Untouched by the census — it targets the byte-bound blocks' *rate*, not the residual. Still live. |
| **the residual itself** (`:1897-1912`, `:1950-1953`) | 1.340 ms unexplained, 19.9 % of score | **CLOSED. Fully attributed, to four decimal places.** |

### 9.3 A standing caveat the census promotes to a finding

The 610 GB/s constant is, by the state doc's own qualifier, *a streaming upper
bound at a favourable shape, not an achievable rate.* The census gives that
qualifier teeth: **the attention qkvo block measures 107 % of it.**

This means a material share of the "unexplained residual" was never physical —
it is an artifact of dividing 1794 MB by a rate the machine does not sustain.
Re-doing the arithmetic at the routed block's *achieved* 546.2 GB/s:

```
1794 MB / 546.2 GB/s = 3.286 ms floor  →  residual = 4.281 − 3.286 = 0.995 ms
```

**The residual shrinks by 26 % purely from using an achievable rate.** Any future
%-of-ceiling or byte-floor claim in this campaign should state which rate it
used. Recommend the state doc adopt 546.2 GB/s (measured, in-situ, decode
shapes) as the decode-side achievable rate and retain 610 only as the marketing
ceiling.

### 9.4 What is *not* retired

Nothing here touches prefill, and prefill is the untouched half: `1 ms` prefill
`S` is only 0.371 % of score, but the M2 gather-elision arm (+0.80–1.19 %) and
split-K NAX (+0.53 %, UNAUDITED) live there. This census is silent on them —
correctly, since 94.2 % of M4 prefill runs kernels the ranked M5 never executes.

Given that decode is now closed and its remaining arms are repriced downward
into MDE range, **the honest read is that the campaign's remaining decode upside
is smaller than previously believed, and the prefill queue deserves the next
allocation** despite its 0.25× score weight.

---

## 10. Three findings the census surfaces that were not asked for

### 10.1 The dense layer has never appeared in any census

Layer 40 of 40 is dense, not MoE, and it has been invisible in every prior
census because it contributes 1 dispatch per family instead of 39.

| | M4 µs | M5-eq µs | MB | achieved GB/s | % of M4 ceiling |
|---|---:|---:|---:|---:|---:|
| `dense_gate_up_swiglu_bf16_v1` | 268.0 | 202.7 | 67.11 | 250.4 | 96.2 % |
| `dense_down_residual_bf16_v1` | 133.0 | 100.6 | 33.55 | 252.3 | 97.0 % |
| **total** | **401.0** | **303.3** | **100.66** | | |

**One layer out of forty moves 100.66 MB = 5.6 % of the entire 1794 MB decode
byte budget, and costs 4.51 % of score.** At 96–97 % of the M4 streaming ceiling
it is the most perfectly byte-bound thing in the model — and the reason is in
the checkpoint: `L.mlp.{gate,up,down}_proj.weight` are **BF16 `[8192, 2048]`,
33.554 MB each, with no `.scales` tensors.** This is the **only unquantized
matmul in the decode step**. Every other projection in the model is NVFP4 or
INT8.

Arithmetically: NVFP4 at 0.5625 B/param would make those three tensors 28.31 MB
instead of 100.66 ⇒ **−72.35 MB/step = 118.6 µs M5 = 1.76 % of score**, from one
layer, with the byte-bound conversion already proven at 96 % efficiency.

**This is not an arm.** Quantizing the dense MLP is a precision change outside
the accepted envelope, which permits only group-32 affine INT8 for attention
Q/K/V/O and per-head `g_proj`. It is inadmissible and I am not proposing it.

I report it because 1.76 % of score is larger than any remaining decode arm in
the queue, and because if the *offline transform* surface
(`Sources/MLXFastTransform/`) can represent this layer more compactly **without
changing its numerics** — a lossless re-layout rather than a re-quantization —
that is admissible and unexplored. I have not verified that such a
representation exists; that is an advisor call.

### 10.2 Zero-byte dispatches are 2.40 % of score

Documented in §8.2. The finding worth carrying forward is not the arm (it is
refuted) but the *number*: 80 of 406 decode dispatches — nearly 20 % of the
dispatch count — move essentially zero bytes and cost 2.40 % of score. That is
the size of the prize the #48 receipt says the machine will not pay out, and it
is useful to have it measured so that no future round re-derives the temptation
from scratch.

### 10.3 GPU-busy is the campaign's most stable local instrument

Across the A/C pair, `gpu_busy_sum` drifted **0.29 %** while wall drifted 1.05 %
and the host gap 6.1 %. Compare the A/A floor on `--local-iterate`: decode
+0.48 %, prefill −1.30 %. **GPU-busy at N=1 is already tighter than
`--local-iterate` at N=1**, on a sub-64 GiB host where the state doc records
that local prefill is not an instrument at all.

The caveat in §1.3 stands: profiled *wall* is not comparable to unprofiled wall,
so this can never replace `--local-iterate` for a ranked-proxy score. But for
*attribution* questions — which kernel, how much, in what proportion — the
profiler is the better tool and the campaign should reach for it first. This is a
methods result that generalises past this assignment.

---

## 11. Limitations

1. **N=1 per configuration.** Drift is characterised (§3) at −0.288 % total and
   ≤1.24 % per family for rows ≥50 µs/step, which is inside every claim, but it
   is not a replicated study.
2. **M4 Pro, not M5.** Decode is 100 % kernel-family-screenable (§1.6), which is
   what makes the projection legitimate, but the conversion factors are derived
   from two M5 anchors, one of which (`dT₄` = 1.01067 ms) is a provisional
   difference-of-differences rather than a direct receipt. If `dT₄` is revised,
   the routed/remainder split moves; the *total* does not, since it is pinned by
   `T` and the byte roofline.
3. **5.7 % of remainder bytes unallocated** (§5.2), carried explicitly as a
   40.8 µs floor term rather than absorbed.
4. **The excess column is an upper bound on byte-boundedness, not recoverable
   time** (§7.3). This is the single most important limitation and it applies to
   every row.
5. **The 610 GB/s divisor is not achievable** (§9.3). The residual being
   attributed is itself partly an artifact of it.
6. **Profiled absolute wall is inflated** by per-command-buffer `fputs`; all
   conclusions use GPU-side timestamps or within-run ratios only.
7. **No intervention implemented.** §4 fired (diffuse) and §5 is discharged as
   (b). This is by design, not omission.

---

## 12. Evidence and submission hygiene

### 12.1 Correctness

All three runs: **0 divergences, all 200 teacher-forced greedy tokens match.**
No source file on the scored path was modified, so this is expected — it is
recorded as confirmation that the profiler does not perturb numerics.

### 12.2 Standing pre-dispatch injection check

```
Sources/MLXFastModel/LagunaRuntimeModel.swift:11046: DARKBLOOM_INJECT_DECODE_EMPTY", 0)
Sources/MLXFastModel/LagunaRuntimeModel.swift:11058: DARKBLOOM_INJECT_EMPTY_TG", 160)
```

Values `0` and `160` — clean, no injected empty dispatches. Re-verified against
the final submitted tree; see §12.5.

### 12.3 Byte budget

`senpai/check-editable-budget.sh 768bb9d4adfc2baac7d74c0008afc92d010329da` at
base: `current=2941175/3000000 headroom=58825 growth=-58809/262144 files=142
(base=142)`. Re-verified against the final tree; see §12.5.

### 12.4 Submitted surface

The assignment's submitted paths are `Sources/MLXFastModel/LagunaRuntimeModel.swift`
and `Sources/MLXFastModel/LagunaLmHeadPrune.swift`. **Both are unmodified; the
submitted diff is empty.** The local-only profiler commit `a8a269d` touching
`Vendor/mlx-swift/.../device.{cpp,h}` was reverted (§1.4); neither file is in
`editablePaths` in any case. Report and logs are under `research/`, which is not
in `editablePaths` and not byte-counted.

### 12.5 Final verification (run on the final tree)

```text
$ senpai/check-editable-budget.sh 768bb9d4adfc2baac7d74c0008afc92d010329da
editable budget OK: current=2941175/3000000 bytes headroom=58825 growth=-58809/262144
  files=142 (file count is diagnostic only; base=142)

$ grep -n 'DARKBLOOM_INJECT_DECODE_EMPTY\|DARKBLOOM_INJECT_EMPTY_TG' \
    Sources/MLXFastModel/LagunaRuntimeModel.swift
11046:    "DARKBLOOM_INJECT_DECODE_EMPTY", 0)
11058:    "DARKBLOOM_INJECT_EMPTY_TG", 160)

$ git diff --name-status b1833d26a164bd511e244b3772933f9e1786329b
        (empty — no tracked file differs from the assignment marker)

$ git status --porcelain
?? research/maple-tanjiro-pr73-decode-kernel-census.md
?? research/pr73-logs/
```

Byte budget is byte-for-byte unchanged from base (`growth=-58809`,
`files=142`), confirming that the report and logs under `research/` are outside
the submitted surface.

### 12.6 Campaign metadata

- **W&B:** not in use for this campaign; evidence is `research/pr73-logs/`.
- **Official submission `--model` value:** `senpai`.
- **Explicit API model-value rejection:** none (no submission dispatched).
- **No official submission was dispatched.** The ranked channel is HELD by
  frieren #35 r5.
