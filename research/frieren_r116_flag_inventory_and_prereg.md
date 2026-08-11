# R116-A — shipped compiled defaults: flag inventory, τ filter, and preregistration

Student: maple-frieren · PR #705 · assignment `maple-r116-a-shipped-defaults-audit`
rev `r116-a-rev1` · base `93688bfa1c6e658ef4394c07a9463c79b4af3130`
Written 2026-08-11 ~02:30Z, **before any R116 timing was collected**.

---

## 0. Instrument preconditions (carried from r109, non-negotiable here)

`Sources/MLXFastModel/RuntimeStartupMemoryPolicy.swift` `apply()` (:170-190)
force-sets, with overwrite=1:

| profile | selected when | allocator cache | `MLX_MAX_MB_PER_BUFFER` | `MLX_MAX_OPS_PER_BUFFER` | warmup clear |
|---|---|---|---|---|---|
| low | host < 64 GiB | 6 GiB | 128 | 64 | yes |
| full | host ≥ 64 GiB, or `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` | 32 GiB | 320 | 128 | no |

This host is a 48 GB M4 Pro, so the **default profile is `low` — half the ranked
command-buffer budget.** My r109 Stage-2 factorial proved that this exact axis
carries a **+887.9 ± 51.9 µs/step (t = +17.09)** interaction: a change can flip
sign between the two profiles. Neither profile declares any
`environmentOverrides` (both are `[:]`) and feature flags use
`setenv(..., 0)`, so **no `DARKBLOOM_*` value is disturbed by either profile**;
the profile only moves the buffer caps.

⇒ **Every R116 arm, control included, exports
`DARKBLOOM_STARTUP_MEMORY_PROFILE=full`, and every block is gated on
`@@LOWMEM_NOTICES == 0`.** A measurement taken under `low` is not evidence
about the ranked M5.

Second precondition, from the assignment: MLX caches compiled libraries by
kernel *name* (`Vendor/mlx-swift/.../metal/device.cpp:602,770`). Flags that
substitute kernel **source** without changing the **name** must therefore be set
before process start. All arms below are set in the child environment of a fresh
`./benchmark.sh --local-iterate`, so the hazard is avoided by construction; if a
source-substitution family nonetheless lands inside ±0.05 %, this is the first
thing to suspect.

---

## 1. Enumeration

`grep -rn 'DARKBLOOM_[A-Z0-9_]*' Sources/ Vendor/` → **159 distinct symbols**,
of which **128 are read from the environment** at a definition site. The
remainder are AOT `#define`s, trace strings, or macro names with no env read.

The τ filter from the assignment:

* **TAU106** — flipping changes arithmetic performed, instructions executed, or
  bytes moved. Worth ~106 % harvest.
* **TAU1** — flipping only changes threadgroup counts, grid shapes, dispatch
  counts, commit cadence, warmup, or async staging. Worth ~1 %. r109 already
  spent a full round proving this class is not fundable (`N-CADENCE-OPTIMAL`).
* **DEAD** — the consumer is unreachable on the scored decode path, so the flag
  cannot be priced at all (`L-RANKED-REACHABILITY`).

---

## 2. TAU106 flags that reach the scored **decode** path

Prices are per-kernel busy µs/step from `research/r87a-runs/ceiling.json`
(406 dispatches/step, busy_sum 8559.4 ± 13.2 µs).

### 2a. NVFP4 SwiGLU-QMV header family — `lagunaSharedSwiGLUQMVHeader` (LRM:6764-6904)

One header string is spliced into **three** decode kernels:
routed swiglu qmv (1499.5 µs, header spliced at :8025), routed shared down
residual (862.6 µs, :8574), and the **shared QMV (284.9 µs, :7088)** — the one
kernel in the assignment's slack list. Total coverage **2,647 µs/step = 31 % of
decode busy**. Every member is pure source substitution: no kernel name changes,
no geometry changes, so the PR #7 geometry ban does not apply.

| flag | def | values | **actual default** | what the flip changes | verdict |
|---|---|---|---|---|---|
| `DARKBLOOM_NVFP4_SCALE_FOLD` | LRM:6606 | `"0"`/other | **ON** (`!= "0"`) | master switch: folds the 2^22 weight scale into the return (`* 4194304.0f`) instead of `converted *= 256.0` + `* 16384.0f` at each use | TAU106, SOURCE_SUBST |
| `DARKBLOOM_NVFP4_NIBBLE_SPLIT` | LRM:6653 | `0`/`1`/`2` | **1** | three different bit-twiddling sequences that unpack two FP4 nibbles into a `half2`; consumed at exactly one `switch` (:6779) | TAU106, SOURCE_SUBST |
| `DARKBLOOM_NVFP4_SCALE_CARRY` | LRM:6668 | `"0"`/other | **ON** | `scaleCarryActive = SCALE_CARRY && SCALE_FOLD` (:6816); carries the group scale through the accumulator instead of applying per group | TAU106, SOURCE_SUBST |
| `DARKBLOOM_NVFP4_QDOT_SEED_ELIDE` | LRM:6720 | `"0"`/other | **ON** | elides the accumulator seed in the quantised dot product | TAU106, SOURCE_SUBST |
| `DARKBLOOM_NVFP4_SCALE_DEFER` | LRM:6753 | `"0"`/other | **ON** (∧ SCALE_FOLD) | defers the row scale to a `* 4194304.0f` suffix (:6762) and enables the `lowScaleFastPath` (:6831) | TAU106, SOURCE_SUBST |

Static ALU op count for the `NIBBLE_SPLIT` switch, counted from the emitted
source: variant 0 = **19** ops, variant 1 (default) = **13**, variant 2 = **19**.
Variant 1 is already the minimum, so my prior for both alternatives is
null-to-worse. It is still screened because it is the assignment headline and
costs two arms.

### 2b. NVFP4 QMV family — the **documented-default mismatch**

| flag | def | doc says | code says | reaches |
|---|---|---|---|---|
| `DARKBLOOM_NVFP4_QMV_SIGN_CARRY` | LRM:4131 | "(default OFF)" | `!= "0"` ⇒ **ON** | changes the *kernel name* (`_sc1` suffix at :4425,:4448,:4552,:4571) ⇒ genuinely distinct compiled kernel, no name-cache hazard |
| `DARKBLOOM_NVFP4_QMV_SEED_ELIDE` | LRM:4159 | "(default OFF)" | `!= "0"` ⇒ **ON** | NVFP4 QMV accumulator seed |
| `DARKBLOOM_E4M3_SIGN_DOMAIN` | LRM:4147 | — | `!= "0"` ⇒ ON | sign-domain handling in the same family |

**This mismatch is the direct evidence for the assignment's thesis.** A flag
whose prose says OFF and whose code says ON was written as an opt-in experiment
and then shipped enabled. The A/B that would have justified the ON state was
either never run or never recorded. These are the two flags whose *shipped*
state has the weakest evidentiary support in the whole tree.

### 2c. Shared-expert path (the 284.9 µs kernel and its neighbours)

| flag | def | actual default | effect | verdict |
|---|---|---|---|---|
| `DARKBLOOM_SHARED_QMV_R1` | LRM:296 | ON | rows=1 shared QMV specialisation | TAU106 |
| `DARKBLOOM_SHARED_SCALE_HALVED` | LRM:312 | ON | the `halved` in `..._qmv_rows1_halved_bf16_v1` — one scale byte per 32 weights | TAU106 |
| `DARKBLOOM_FUSED_SHARED_SWIGLU_QMV` | LRM:129 | ON | fuses shared gate/up + SwiGLU into one QMV | TAU106 |
| `DARKBLOOM_SHARED_FIRST_DOWN` | LRM:8219 | **OFF** (`== "1"`) | swaps kernel name `..._v5` → `..._v5sf` *and* the `inputNames` list (:8231-8260, :8428-8560, :8635): shared-expert contribution enters the down-residual reduction first | TAU106 |
| `DARKBLOOM_FUSED_DOWN_ROW_STAGING` | LRM:8227 | ON | row staging in the fused down kernel | TAU106 |
| `DARKBLOOM_QMV_WIDE_CODES` | LRM:325 | **OFF** | wide code loads | **CLOSED by r109: +35.2 µs/step slower, t = +25.23** |
| `DARKBLOOM_ROUTED_GATEUP_R1` | LRM:7913 | ON | rows=1 routed gate/up | TAU106 |

`SHARED_FIRST_DOWN` is the only unexplored OFF-by-default TAU106 flag on the
assignment's named kernel family. It reorders a floating-point reduction, so it
is **not** bit-exact by construction — if it wins it needs a full equivalence
run, not a golden-hash comparison.

### 2d. Other TAU106 decode flags (inventoried, not screened this round)

Attention scale banks — `ATTN_SCALE_NARROW_QKV` (LRW:678),
`ATTN_SCALE_NARROW_OPROJ` (:681), `ATTN_SCALE_PAIRWISE_QKV` (:719),
`ATTN_SCALE_PAIRWISE_OPROJ` (:722), `ATTN_SCALE_LANEMAJOR` (:694) — all ON,
all TAU106, all decode. `ATTN_SCALE_NARROW` (:674, block form) and
`ROPE_ATLAS_VIEWS` (LRM:627, OFF) are **fallback arms shadowed by their
default-ON siblings** (LANEMAJOR, `ROPE_ANGLE_ATLAS` LRM:604), so measuring
either requires disabling the sibling — a two-factor design, out of scope for a
zero-build screen.

Router — `ROUTER_ORDINAL` (LRM:9480, ON), `ROUTER_ORDINAL_SCORE_TABLE` (:9486,
ON, SOURCE_SUBST), `ROUTER_PRECOMPUTED_KEYS` (:172, ON, SOURCE_SUBST),
`DECODE_ROUTER_TOURNAMENT` (:9532, ON). All TAU106 decode. r109 already closed
`ROUTER_ROWS_PER_GROUP` (`rpg` retiling) and
`ROUTER_WEIGHT_PREFETCH` (`N-ROUTER-PREFETCH-CLOSED-BY-M5-NULL`).

LM head — `LM_HEAD_PRUNE` (LagunaLmHeadPrune.swift:79, ON),
`LMHEAD_FUSED_REFINEMENT` (:96, ON). TAU106 decode.

`GQA_PAIR_HEADS` (`sdpa_vector.h:15-16`, value 2) is **not an env var** — it is
an AOT `#define` requiring `tools/build-mlx-metallib.sh`. TAU106 decode, but it
is a build-round experiment, not a zero-build screen arm.

---

## 3. TAU1 — filtered out, will not be priced

`PARAMS_ATLAS` (LRM:1999, host-side ring-index staging, identical kernel work),
`WARM_GREEDY_ARGMAX` (LRW:517, warmup),
`ATTN_QBLOCK_MAJOR` / `ATTN_QBLOCK_ZIGZAG` (jit_kernels.cpp:1319/1332, both ON,
self-described in `steel_attention_nax.h:142-154` as "a pure permutation of
threadgroups"), `EXPERT_DOWN_BN` (quantized.cpp:1240, N-tile width → grid shape),
`DECODE_ASYNC_STAGE` (LRM:746), `ATTN_PROJECTION_ASYNC` (:784),
`PREFILL_ASYNC_LADDER` (:800), `FUSED_FULL_ATTN_WHOLE_MODEL_WARMUP` (:1855).

r109 spent one whole round on this class and closed it: `N-CADENCE-OPTIMAL`,
`N-BFS-WIDTH-NULL-AT-RANKED-CADENCE`, `N-DENSITY-SATURATED`. At τ ≈ 1 % the
ceiling of the entire class is +0.035 % of score. Not fundable.

## 4. DEAD — cannot be priced (`L-RANKED-REACHABILITY`)

| flag | why unreachable |
|---|---|
| `DARKBLOOM_L5_UNROLL` | decode o-projection returns at LRM:6371-6386, so `lagunaGatedOutputProjection` (:6435-6452) is never entered |
| `DARKBLOOM_NORM_AFFINE_QKV_PF` / `_STAGE` | QKV bank is NVFP4 g16/bits4 from layer 0 (:3047-3054, :3098-3113, :5740-5744), so the guard at :5927-5928 always fails. Do **not** revive `lagunaNormAffineQKV` (~+560 µs/step) |
| `DARKBLOOM_AFFINE_METADATA_INDEXED` | consumers (:5666, :5746, :6343) require `mode == .affine`, bits 8, gs 32; `lagunaNativeAffineWeight` returns NVFP4 g16/b4 for every layer while `NATIVE_AFFINE_NVFP4 != "0"` |
| `DARKBLOOM_BSEARCH_HOIST` | gated by `sorted_rhs = M==1 && B>=16` (quantized.cpp:1904); decode `B = 8 < 16` (`LagunaConfig.swift:31`) |
| `DARKBLOOM_GATHER_XMAJOR` | `darkbloom_gather_xmajor_ct()` is a hardcoded `return 0` (quantized.cpp:1306-1308); no `#if` consumer exists in any kernel source |
| `DARKBLOOM_STAGE2_GATHER` | injects a `#define` + trace print that no kernel source tests |
| `DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE` | dominated: the residual arm (:10902-10920) holds whenever `FUSED_ROUTED_SHARED_DOWN_RESIDUAL` (ON), non-nil `residual`, non-nil `fusedSharedDownInputs`, and bf16 `(1,1,hidden)` shape all hold; the reduce arm is the `else if` at :10933 |

**Prefill-only** (real, but 0.25 weight and outside this round's decode target):
`ROUTE_COUNTING_SORT`, `ROUTE_FUSED_SCATTER`, `INVERSE_SCATTER` (all gated
`n % 128 == 0` / `doSort = indices.size >= 64` at LRM:10538; decode n = 8),
`EXPERT_ALIGNED_GATHER`, `STATIC_NVFP4_SHAPES`, `TERMINAL_FUSION`,
`PREFILL_*`. Decode routed MoE goes through the fused SwiGLU-QMV Swift kernel
(LRM:10833) and **never** calls `gatherQuantizedMM`, so every C++ gather flag is
prefill-only. `ATTN_QHOIST` is settled OFF (+4.484 % of candidate prefill,
19.7 σ, receipt `e407882`).

---

## 5. PREREGISTRATION

Per the assignment, **two flags are named here, before any R116 timing exists.**
A third-place argmax from the screen is someone else's hypothesis and will be
reported as exploratory, not confirmed.

> **P1 — `DARKBLOOM_NVFP4_QMV_SEED_ELIDE` (LRM:4159), tested at `=0`.**
> **P2 — `DARKBLOOM_NVFP4_QMV_SIGN_CARRY` (LRM:4131), tested at `=0`.**

Rationale, stated in advance: these are the only two flags in the tree whose
prose documents them as "(default OFF)" while the code reads `!= "0"` and ships
them **ON**. That mismatch is direct evidence that their shipped state was never
A/B-confirmed, which is exactly the assignment's thesis. Both are TAU106 and
both reach decode NVFP4 QMV. P2 additionally changes the kernel name (`_sc1`),
so its two arms are genuinely distinct compiled kernels and it is immune to the
name-keyed library-cache hazard.

**Direction of the prediction is deliberately not asserted.** These are audits:
the finding "the shipped ON state is confirmed faster" is a publishable closure
(`N-DEFAULTS-ALREADY-OPTIMAL`) and the finding "OFF is faster" is a landing.

Stated prior for the headline, so it cannot be retro-fitted: **`NIBBLE_SPLIT`
0 and 2 will both come out null-to-worse**, because variant 1 emits 13 ALU ops
against 19 for each alternative. It is screened because the advisor asked for
the three points at the shared QMV, not because I expect it to win.

## 6. Screen design (locked before launch)

Nine arms, control first, blocked ABBA (`research/frieren_r109_env_ab.sh`
reverses arm order on even blocks), `./benchmark.sh --local-iterate`, one
model-holding process, 40 C gate, every arm carrying
`DARKBLOOM_STARTUP_MEMORY_PROFILE=full`.

| arm | override | family |
|---|---|---|
| `ctl` | *(profile only)* | shipped defaults |
| `ns0` | `NVFP4_NIBBLE_SPLIT=0` | §2a headline |
| `ns2` | `NVFP4_NIBBLE_SPLIT=2` | §2a headline |
| `sc0` | `NVFP4_SCALE_CARRY=0` | §2a |
| `qse0` | `NVFP4_QDOT_SEED_ELIDE=0` | §2a |
| `sd0` | `NVFP4_SCALE_DEFER=0` | §2a |
| `qmvse0` | `NVFP4_QMV_SEED_ELIDE=0` | **P1** |
| `qmvsc0` | `NVFP4_QMV_SIGN_CARRY=0` | **P2** |
| `sfd1` | `SHARED_FIRST_DOWN=1` | §2c |

`MLXFAST_SPLIT_DISPATCH` is **0** (unset) for this wall ranking. SPLIT=1 is for
per-kernel attribution only — nezuko measured SPLIT=1 wall at +19.6 % and
mis-ranking 2 of 4 arms.

Argmax debiasing is mandatory on the screen: with m = 8 non-control arms,
`bias = sigma_contrast * sqrt(1 - rho) * E[max of 8 iid N(0,1)]`, and
`E[max of 8] = 1.4236`. Raw and debiased argmax are both reported.

Conversion for pricing: **0.0084 % of score per M4 wall µs/step** (decode
elasticity 0.750, R² = 1.0000000 over 1,232 paired receipts). `--local-iterate`
under-reports steady-step wins by **1.28×**.

Escalation trigger from the assignment: any bit-exact flag moving the paired
steady step by ≥ 50 µs is reported immediately, before validation.
