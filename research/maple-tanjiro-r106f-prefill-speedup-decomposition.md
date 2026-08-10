# R106-F′ — Why is prefill only 1.98× when decode is 2.83×?

**Student** maple-tanjiro · **PR** #620 · **assignment** `maple-r106-f-prefill-nongemm-census`
· **revision** `r106-f-rev2` · **base** `3241e5e55b17a1902cac47b01f186f7281391ca5`
· **receipts consumed: 0**

---

## 0. Verdict

> **78.02 % of baseline M4 prefill time (474.079 of 607.644 ms) sits in stages whose
> candidate speedup is ≈1.0× — stage A dense BF16 attention projections (1.101×) and
> stage B NVFP4 expert GEMM (0.929×).**

**Verdict: `V-UNTOUCHED`** — qualified, and the qualification matters more than the label.

Of the two ≈1.0× stages, exactly one is a real finding and one is an artifact of this host:

| stage | base share | ratio | class | reading |
| --- | ---: | ---: | --- | --- |
| A dense BF16 attn proj (q,k,v,o,g) | 38.85 % | 1.101× | **2 — never touched** | **LIVE.** ≈57 % of A's FLOPs provably execute the identical kernel with identical tiles in both trees on the ranked M5. |
| B NVFP4 expert GEMM + epilogue | 39.17 % | 0.929× | **3 — M4 artifact** | **DEAD as evidence.** Every candidate mechanism in B is inside an `_nax` branch that Apple GPU gen 16 cannot reach. Its ≈1.0× carries no M5 information. |

So the honest one-line answer to the assignment's question is:

**Prefill is 1.98× and not 2.83× principally because the largest genuinely
host-transferable prefill family — the dense BF16 attention projections — is
substantially untouched by the fork, and the one place the fork does touch it
(`o_proj`, via `darkbloom_steel_prefill_tile`) is a single tile-shape override that
leaves q/k/v/g on the stock upstream tile heuristic.**

And one correction to my own headline before anyone quotes it: **78.02 % is a
*baseline-share* number measured on M4, and M4 systematically inflates baseline shares**
(§3.9). The corresponding M5 baseline share for stage A is ≈19.9 %, not ≈39 %. The
transferable statement is the *candidate*-side share and the *identity* argument in §4,
not the 78 % itself.

---

## 1. Assignment, host, and discipline

### 1.1 The question

Round 106-F′ asks why the two scored halves diverge so far:

| half | harness baseline (pinned) | ours | speedup |
| --- | ---: | ---: | ---: |
| decode | 13 855.01 µs/step | 4 893.71 | **2.8312×** |
| prefill | 372.473 µs/token (190.706 ms / 512) | 187.791 (96.149 ms / 512) | **1.9834×** |

`2.8312^0.75 · 1.9834^0.25 = 2.59026`, which is our best-ever `cs 2.590559`. Lifting
prefill to decode's ratio is worth `0.25·ln(2.8312/1.9834) = +8.894 %` in log-score, i.e.
**+9.302 % multiplicatively**. (Rule 94.1 quotes "+9.3 %", the brief quotes "8.90 %";
these are the same quantity in the two conventions — see §6.2.)

### 1.2 Host

Apple **M4 Pro**, 14 CPU, **48 GiB** unified, macOS 26.5.2 (25F84).
Apple GPU generation **16** ⇒ `nax_available = false` (`device.cpp:1083-1101`;
`can_use_nax &= gen >= (arch=='p' ? 18 : 17)`, and the `p`/`g`/`s`/`d` suffix map at
`device.cpp:355-372` puts M4 Pro at `g`). The ranked host is an M5 Max ⇒ `s` + gen 17 ⇒
`nax_available = true`. **This single bit dominates the interpretation of every number
below** and is the reason Stage 2 exists.

### 1.3 Four-tag discipline

Every quantitative claim in this document carries one of four tags:

- **[STRUCT]** — a structural fact (source identity, kernel reachability, gate arithmetic,
  FLOP shares) that transfers M4 → M5 unchanged.
- **[M4-WALL]** — a wall-clock measurement on this M4 Pro. Does **not** transfer.
- **[PROJ]** — a projection onto M5 through a stated model. Transfers only as well as the
  model does; every projection here names its factor.
- **[M5-RCPT]** — a number that came from an official M5 receipt.

### 1.4 Receipts

**Zero official receipts consumed.** `senpai/submit-official.sh` was never invoked in this
revision. All M5 numbers are [M5-RCPT] quotations of already-published receipts, or
[PROJ] projections that say so.

---

## 2. Stage 0 — Calibration: does the fork's decode:prefill asymmetry reproduce on M4?

### 2.1 Why Stage 0 had to exist at all

Before this revision, **nobody in this campaign had ever timed the pinned ranked baseline
tree on any host.** That is not an oversight; the local harness structurally cannot do it.
Three separate mechanisms are all called "baseline" locally and none of them is a
measurement of the baseline code:

1. **Pinned constants.** `Sources/MLXFastCore/Constants.swift:168-169` hardcodes
   `MB_D`/`MB_P`-shaped values. `docs/benchmark-window-freeze.md:150-172` states these are
   the mean of four ranked M5 runs (`30011903540`, `30015338806`, `30022640438`,
   `30027994180`) against baseline `15852ee5`, and explicitly that they are **not** the
   ranked denominator.
2. **A jq diff against a saved candidate score.**
   `benchmark.sh:256-287,291-380,2193` compares against
   `score.local-iterate.baseline.json` — a previously saved *candidate* run.
3. **Env-injected ranked numbers.** `Sources/MLXFastTrustedHarness/BenchmarkSupport.swift:25-82`.

Evidence that these are constants and not measurements: all 25 `research/**/score*.json`
in the tree carry byte-identical baseline constants — zero variance across dozens of runs
on multiple hosts. A measurement has variance.

Related structural facts established while locating the denominator:

- **The ranked denominator is commit `15852ee52858def42ddd4f32bca7e59d275e020e`**
  ("Pin Poolside v2 private benchmark artifacts (#756)", anupsv, 2026-07-22).
  `.github/workflows/benchmark.yml:147` sets `MLXFAST_BASELINE_COMMIT`, verified at
  `:318-328`; `MLXFAST_BASELINE_WS=/opt/bench-runner/baseline/laguna-xs-2.1-serial-v2/current`;
  corroborated by `docs/benchmark-window-freeze.md:159,176-190` and
  `docs/private-benchmark-security.md:192`.
- **Vendored `Laguna.swift` is never clocked.** Its only construction site is
  `Sources/MLXFastModel/LagunaUpstreamEquivalence.swift:75`, and that file is 165 lines of
  pure logit comparison driven only by `research/run_upstream_equivalence.sh`. It is an
  oracle, not a baseline.
- `MB_D`/`MB_P` as *names* appear only under `research/` (~40 hits): they are a corpus mean
  over n = 1176 receipts (decode CV 0.246 %, prefill CV 1.945 %).

So Stage 0 built and timed `15852ee5` for the first time.

### 2.2 Baseline-tree compatibility — all checks PASS [STRUCT]

| check | result |
| --- | --- |
| `15852ee5` is a local git object and an ancestor of HEAD | yes |
| `Package.swift` / `Package.resolved` unchanged `15852ee5..HEAD` | yes — same frozen dependency graph |
| `device.cpp` blob identical at `15852ee5` and at base `3241e5e5` | yes, `2a8e15afd7082edf740a97d2e78793cc840c0d4d` ⇒ the GPUPROF instrument patch applies verbatim to both trees |
| worker request kinds present in both | `correctness`, `correctness_begin`, `correctness_step`, `prefill`, `decode_begin`, `decode_step`, `decode_block`, `phase_diagnostics` (baseline lines 277/296/332/366/388/429/461/530); the `prefill` and `decode_begin` handlers are **byte-identical** |
| both trees read the same on-disk `weights/` | yes — `Transform.swift` diff is comment-only, `Safetensors.swift` diff is a one-word comment |
| both honour `DARKBLOOM_STARTUP_MEMORY_PROFILE` | yes (`RuntimeStartupMemoryPolicy.swift:28` base, `:36` HEAD) |
| AOT Metal sources | **DIVERGE** `15852ee5..3241e5e5`: `kernels/` 13 files +2550/−265, `mlx-generated/` 6 files +1923/−128 ⇒ **each tree was given its own metallib**, built per-worktree |

Baseline `Sources/MLXFastModel/LagunaRuntimeModel.swift` is **430 lines with zero
`DARKBLOOM_` occurrences**: plain `Linear` for `q/k/v/o/g_proj` (`:75-79`, `:99-106`,
calls `:130-132`, `:166`), `attentionWithCacheUpdate` (`:141`), `SwitchGLU` routed MoE
(`:232-251`), dense MLP `Linear` (`:173-180`), `lm_head` `Linear` (`:362-370`),
`embedTokens.asLinear` (`:401`). Our HEAD equivalent is >6 000 lines.

### 2.3 Stage-0 measurement [M4-WALL]

Job `e70247a6-e808-4d9c-a4dc-0163b467f688`, exit 0, 195 s. ABBA order
`cand base base cand`, `REPS=6`, `DECODE=40`, `SETTLE=20 s`,
`DARKBLOOM_STARTUP_MEMORY_PROFILE=full`, **no** GPU profile (clean walls).
Archived: `research/pr270-logs-r106f/stage0.calib.log`; arithmetic
`research/r106f_stage0_arith.py` → `research/pr270-logs-r106f/stage0.arith.log`.

| slot | arm | prefill warm median (ms/512) | decode (ms/step) | peak_ram_gb | token |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | cand | 548.673 | 8.046 | 20.7193 | 5991 |
| 2 | base | 612.125 | 23.101 | 20.7075 | 5991 |
| 3 | base | 611.593 | 22.967 | 20.7059 | 5991 |
| 4 | cand | 544.143 | 8.202 | 20.7184 | 5991 |

ABBA means: cand decode **8.1240**, base decode **23.0340**, cand prefill **546.4080**,
base prefill **611.8590** ms. A-vs-B spreads within arm: 1.920 % / 0.582 % / 0.829 % /
0.087 %. Both arms emit the same greedy token (5991) and match on peak RAM to 0.06 %.

### 2.4 The decisive result

| half | M4 speedup [M4-WALL] | ranked M5 [M5-RCPT] | agreement |
| --- | ---: | ---: | ---: |
| **decode** | **2.8353×** | **2.8312×** | **+0.15 % — REPRODUCES** (100.1 % of the M5 log-gain) |
| **prefill** | **1.1198×** | **1.9834×** | **−43.54 % — DOES NOT REPRODUCE** (only 16.5 % of the M5 log-gain is visible) |

M4→M5 hardware factor, per tree:

| half | baseline M4→M5 | candidate M4→M5 | cand/base |
| --- | ---: | ---: | ---: |
| decode | 1.6626× | 1.6601× | **0.999** |
| prefill | 3.2084× | 5.6831× | **1.771** |

Implied combined score: M5 `cs` 2.590188, M4 **2.24784**. The asymmetry statistic
`0.25·ln(dec/pre)` is **+8.90 % on M5** but **+23.23 % on M4**.

### 2.5 Why this is a *feature* of the experiment, not a failure

The logical structure is the whole point and must not be collapsed:

- Decode agreeing to **0.15 %** is a **positive control on the baseline build**. If the
  baseline worktree, metallib, weights, or probe harness were wrong, decode would not land
  within 0.15 % of a corpus mean over 1176 M5 receipts.
- Therefore the prefill discrepancy **cannot** be a build error. It is a statement about
  kernel families and hardware.

Mechanism, stated crisply [STRUCT]:

- **Decode is nax-invariant.** The kernels that carry decode — `gemv`, `qmv`/`qvm`,
  `sdpa_vector` — have **no** `_nax` variants at all. `matmul.cpp:1252-1253` short-circuits
  `min(M,N)==1` to `gemv` *before* any nax dispatch, and quantized matvec
  (`quantized.cpp:238,420`, dispatch `:1808-1841`) has no nax form. So the candidate's
  decode wins are the same code on both hosts, and the 2.83× transfers.
- **Prefill is 94.3 % nax-divergent** (`research/maple-tanjiro-pr91-prefill-budget-census.md`
  §2.4, 520.712 of 552 ms). Several of the candidate's largest prefill mechanisms live
  *only inside* nax branches and are therefore **unreachable on this host**:
  `darkbloom_steel_prefill_tile()` (`matmul.cpp:82-88`, applied `:674-677`),
  `darkbloom_stage_bm128_variant()` (`quantized.cpp:1234`),
  `darkbloom_expert_aligned_gather()` (`quantized.cpp:1204`), the Laguna pairwise-scale
  layout / `_expert_static_nax_` family (`quantized.cpp:1361-1400`, `:1459-1463`, `:1566`),
  and the outer `pairwise_contract` predicate (`quantized.cpp:1879-1884`).

### 2.6 Four alternative explanations, stated and dismissed

| alternative | dismissal |
| --- | --- |
| (a) the baseline build is wrong | Refuted by decode reproducing to 0.15 %. A broken baseline cannot be right on one axis and 44 % wrong on the other. |
| (b) the M5 prefill anchors are wrong | `MB_P` is a corpus mean over 1176 receipts with CV 1.945 %; a 43.5 % error is 22σ. The candidate 96.149 ms is our own published receipt. |
| (c) probe-harness asymmetry | Both trees are driven through the same worker `prefill` request kind, and the two handlers are byte-identical (§2.2). |
| (d) memory-profile asymmetry | Both trees honour `DARKBLOOM_STARTUP_MEMORY_PROFILE`; measured peaks agree to 0.06 %. |

### 2.7 Consequence for the rest of the document

Stage 0 does **not** trip the brief's "STOP AND REPORT" clause: the calibration target was
the decode ratio, and it reproduced. But it converts Stages 1–3 from *measurement* into
*measurement plus mandatory reachability triage*. That is Stage 2, and it is why stage B's
0.929× is thrown away rather than reported as a finding.

---

## 3. Stage 1 — Paired per-family prefill census

### 3.1 Method

One 512-token frozen prefill, both trees, same host, same session, GPU profile on.
Instrumented via the GPUPROF hook in `Vendor/mlx-swift/.../metal/device.cpp` (+`device.h`),
applied identically to both worktrees (the blob is identical at both commits, §2.2), and
**reverted before submission** (§10, final commit).

Inputs: `research/pr270-logs-r106f/census.base.split1.log`,
`research/pr270-logs-r106f/census.cand.split1.log`.
Analysis: `research/r106f_paired_families.py` →
`research/pr270-logs-r106f/stage1.paired.log`.

```
python3 research/r106f_paired_families.py \
  research/pr270-logs-r106f/census.base.split1.log \
  research/pr270-logs-r106f/census.cand.split1.log \
  > research/pr270-logs-r106f/stage1.paired.log
```

The paired census job (`fc2f53ba-f1ad-4778-9183-16d44461fee1`) was cancelled at a
controller boundary after slots 1–2 completed with `exit=0`; slots 3/4 (a second
`split0` replicate) never ran. **Decision: proceed without split0.** Its only role was a
second replicate of the same pair, and Stage 0 already supplies clean *uninstrumented*
walls (546.408 / 611.859) that bracket the instrumented ones to ~1 %. This is recorded as
a reduction in replication, not as a gap in the deliverable.

### 3.2 Headers [M4-WALL]

| quantity | baseline `15852ee5` | candidate HEAD | Δ |
| --- | ---: | ---: | ---: |
| warm median prefill | 607.643 ms | 548.242 ms | −9.8 % |
| instrumented wall | 607.644 ms | 548.441 ms | |
| busy union | 601.918 ms (99.1 %) | 545.579 ms (99.5 %) | GPU is saturated in both |
| **command buffers** | **2126** | **1066** | **−1060 (−49.9 %)** |
| **dispatches** | **2637** | **1222** | **−1415 (−53.7 %)** |
| bound bytes | 31.552 GiB | 28.834 GiB | −8.6 % |

Work-identity checks (the candidate is not doing less *mathematical* work):
`steel_gemm_bf16` n 401 → 392 (**−2.2 %**); `attention_core` n 40 → 40 (**+0.0 %**);
`routed_gather_gemm` n 117 → 76 (**−35.0 %**, expert-loop restructuring).

The striking pair is **−53.7 % dispatches for −9.8 % wall**: on this host the candidate has
already removed half the launches and it buys almost nothing, because the residual is
GEMM-bound, not launch-bound.

### 3.3 Attribution repairs (nothing left in `other`, nothing left MIXED)

The profiler brackets concurrent dispatches; the census attributes overlap by fair share
and reports a `MIXED` residue plus an `other` bucket. The brief requires both to be zero.

Baseline `MIXED` 97.026 ms redistributed by bracket weight:
`nvfp4_dense_qmm` +71.343 (bracket 175.899), `steel_gemm_bf16` +17.593 (43.377),
`sort_scatter` +7.565 (18.651), `qk_norm_rope` +0.302 (0.745), `elementwise` +0.223 (0.551).
Baseline `other` → `lm_head` +1.678 (`gemv_bfloat16_bm8_bn1_sm1_sn32_tm4_tn4_nc0_axpby0`).

Candidate `MIXED` 0.022 → `steel_gemm_bf16` +0.022, `rms_norm` +0.000.
Candidate `other` → `lm_head` +0.143 + 0.143 (`gemv_al_bfloat16_bm4/bm8_…`),
`nvfp4_dense_qmm` +0.023 (`laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_…`).

That the baseline has 97 ms of MIXED and the candidate 0.022 ms is itself a result: the
baseline overlaps many small dispatches, the candidate runs long serial GEMMs. It also
warns that baseline fair-share attribution is softer than candidate attribution — handled
in §3.6.

### 3.4 Functional mapping (stated, as required)

Stages are defined by **function**, not by kernel name:

| stage | families |
| --- | --- |
| A dense BF16 attn projections | `steel_gemm_bf16` |
| B NVFP4 expert GEMM + epilogue | `routed_gather_gemm` + `nvfp4_dense_qmm` + `moe_tail` |
| C routing | `sort_scatter` + `router` |
| D attention core (SDPA) | `attention_core` |
| E norm + RoPE | `rms_norm` + `qk_norm_rope` |
| F elementwise glue | `elementwise` |
| G lm_head + argmax | `lm_head` |
| I GPU idle | wall − busy union |

`OTHER_ROUTES` used to empty the `other` bucket: `^gemv` → `lm_head`;
`routed_shared|shared_nvfp4` → `nvfp4_dense_qmm`.

### 3.5 PRIMARY TABLE — sorted by **baseline** share [M4-WALL]

| stage | base ms | base % | cand ms | cand % | ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| **B NVFP4 expert GEMM + epilogue** | 238.025 | 39.17 | 256.290 | 46.73 | **0.929 ≈1.0×** |
| **A dense BF16 attn proj (q,k,v,o,g)** | 236.054 | 38.85 | 214.488 | 39.11 | **1.101 ≈1.0×** |
| C routing (sort/scatter/gather) | 65.773 | 10.82 | 40.287 | 7.35 | 1.633 |
| D attention core (SDPA) | 28.777 | 4.74 | 22.946 | 4.18 | 1.254 |
| F elementwise glue | 23.418 | 3.85 | 4.711 | 0.86 | 4.971 |
| E norm + RoPE | 8.173 | 1.35 | 5.906 | 1.08 | 1.384 |
| I GPU idle | 5.725 | 0.94 | 2.862 | 0.52 | 2.000 |
| G lm_head + argmax | 1.697 | 0.28 | 0.952 | 0.17 | 1.783 |
| **TOTAL** | **607.642** | 100.00 | **548.442** | 100.00 | **1.108** |

**Ledger closure: baseline −0.002 ms, candidate +0.001 ms.** Each column sums to its own
tree's instrumented wall; nothing is in `other`.

Near-band definition used for "≈1.0×": `0.85 ≤ ratio ≤ 1.18`.

**HEADLINE: 78.02 % of baseline prefill time (474.079 of 607.644 ms) is in ≈1.0× stages.**

### 3.6 Sensitivity: the `arangeuint32` null-work slice

Both trees issue an `arangeuint32` dispatch whose fair share lands in the routing stage but
whose real purpose is to feed the expert gather (base 25.788 ms, cand 38.248 ms). Crediting
it to `routed_gather_gemm` instead:

| stage | base ms | base % | cand ms | cand % | ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| B | 263.813 | 43.42 | 294.538 | 53.70 | **0.896** |
| A | 236.054 | 38.85 | 214.488 | 39.11 | **1.101** |
| C | 39.984 | 6.58 | 2.039 | 0.37 | 19.614 |
| D/E/F/G/I | unchanged | | unchanged | | unchanged |
| TOTAL | 607.642 | | 548.442 | | 1.108 |

**HEADLINE under sensitivity: 82.26 % (499.867 of 607.644 ms).** The headline is robust:
whichever way the null-work slice is booked, ≳78 % of baseline prefill time is in ≈1.0×
stages, and stage A's 1.101× is untouched by the choice.

### 3.7 Fair-share-free cross-check (the most important table in Stage 1)

Fair-share attribution can manufacture a ratio when the two trees have different
concurrency structure — and §3.3 showed they do (97 ms vs 0.02 ms MIXED). So the census
also reports each family's **exclusive** time (dispatches with no concurrent sibling) and
its **raw** bracket sum:

| family | b excl | c excl | excl ratio | b raw | c raw | raw ratio | b GB | c GB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **steel_gemm_bf16** | **208.877** | **212.228** | **0.984** | 230.303 | 218.533 | 1.054 | 4.658 | 4.552 |
| routed_gather_gemm | 15.726 | 201.965 | 0.078 | 336.453 | 265.444 | 1.268 | 20.122 | 18.968 |
| nvfp4_dense_qmm | 0.814 | 20.007 | 0.041 | 183.365 | 20.007 | 9.165 | 0.458 | 0.652 |
| sort_scatter | 3.501 | 2.613 | 1.340 | 180.334 | 76.612 | 2.354 | 2.534 | 1.135 |
| elementwise | 11.837 | 4.695 | 2.521 | 36.594 | 4.728 | 7.740 | 3.575 | 1.632 |
| attention_core | 28.727 | 17.746 | 1.619 | 28.828 | 28.146 | 1.024 | 0.713 | 0.696 |
| rms_norm | 6.160 | 1.725 | 3.571 | 6.175 | 1.747 | 3.535 | 0.695 | 0.497 |
| qk_norm_rope | 1.704 | 4.159 | 0.410 | 2.449 | 4.203 | 0.583 | 0.713 | 0.768 |
| moe_tail | 0.000 | 2.555 | — | 0.000 | 2.555 | — | 0.000 | 0.878 |
| router | 0.000 | 0.674 | — | 0.000 | 0.673 | — | 0.000 | 0.012 |
| lm_head | 0.019 | 0.666 | 0.029 | 0.019 | 0.666 | 0.029 | 0.000 | 0.959 |
| other | 1.678 | 0.309 | 5.430 | 1.678 | 0.309 | 5.430 | 0.411 | 0.211 |

★ **`steel_gemm_bf16` costs 208.877 ms exclusive in the baseline and 212.228 ms exclusive
in the candidate — ratio 0.984.** Stage A's apparent 1.101× fair-share gain is
**attribution bias**: the baseline runs stage-A GEMMs alongside more concurrent siblings,
so fair share hands part of A's bracket to its neighbours. On the cleanest available
measure — same kernel, alone on the GPU, both trees — **stage A is a dead heat, and if
anything the candidate is marginally slower.**

This strengthens the verdict rather than weakening it: A is not "1.10× and hard to
improve", it is "1.00× and not addressed".

Instrument cost: instrumented prefill ratio 1.1079× vs clean 1.1198× ⇒ the GPUPROF hook
costs ~1 % and does so slightly asymmetrically. Acceptable for a share decomposition;
Stage 0's clean walls are the ones quoted for speedups.

### 3.8 Cross-machine candidate-share check — and its circularity

The transferable form of a share statement is the **candidate** share, because the
candidate is the tree we actually run on both hosts.

- Candidate M4: stage A = 214.488 / 548.442 = **39.11 %**.
- Candidate M5 [PROJ]: `research/maple-tanjiro-nonmoe-prefill-census.md:374` gives
  `steel_gemm_bf16` = 37.93 ms of a 96.149 ms prefill = **39.45 %**.
- Agreement: **0.87 %**.

**I audited this and it is largely circular. Do not use it as independent corroboration.**
`research/maple-tanjiro-nonmoe-prefill-census.md:356-370` derives 37.93 ms by scaling the
M4 census: HOST-IDENTICAL glue is scaled by the bandwidth ratio 546.2/260.2 = 2.099, and
the HOST-DIVERGENT remainder — which includes `steel_gemm_bf16` — by a single factor
**5.66×**. Indeed `214.513 / 5.66 = 37.900 ≈ 37.93`. Since the divergent factor 5.66 is
within 0.8 % of the overall wall factor `548.386/96.149 = 5.70`, **any** share of the
divergent block is preserved by construction. The 0.87 % agreement therefore measures the
internal consistency of the projection, not a cross-machine fact.

What *is* non-circular is §4: the identity argument that q/k/v/g run the stock upstream
kernel with the stock upstream tile in both trees on M5. That is source-level, not
projected.

### 3.9 The M4 baseline-share inflation caveat (important)

On M5 the baseline prefill is 1.98× slower than the candidate; on M4 it is only 1.12×
slower. So the M4 baseline wall is "too small" relative to M5 by a factor of ~1.77, and
**every M4 baseline-share statement is inflated for stages the candidate did not speed up**
and deflated for stages it did.

Concretely, for stage A: M4 baseline share 38.85 %, but [PROJ] M5 baseline share
`37.93 / 190.706 = 19.89 %`. The 78.02 % headline is therefore a correct statement about
*this host* and a misleading one about the ranked host. The claims I carry forward are:

1. [M4-WALL] 78.02 % (82.26 % under sensitivity) of baseline M4 prefill is in ≈1.0× stages.
2. [M4-WALL] Stage A's exclusive time is identical in both trees to 1.6 % (ratio 0.984).
3. [STRUCT] On M5, ≈57 % of stage A's FLOPs execute the identical kernel with identical
   tiles in both trees. **This is the transferable finding.**

---

## 4. Stage 2 — Reachability triage of the ≈1.0× stages

### 4.1 Classes

Per the brief: **1** = at its roof in both trees; **2** = never touched (interesting);
**3** = M4 artifact (`use_nax` unconditional for BF16 at `matmul.cpp:957-1026`).
Plus **live / dead-on-arrival under Rule 90** (is the surface editable?).

### 4.2 Model configuration [STRUCT]

From `weights/config.json`: hidden 2048, head_dim 128, **num_attention_heads 48**,
num_key_value_heads 8, 40 layers, intermediate 8192, moe_intermediate 512,
shared_expert_intermediate 512, 256 experts, top-8, vocab 100352, sliding_window 512,
rope_scaling None, quantization `{bits 4, group_size 16, mode nvfp4}`, layer 0 dense MLP
then all sparse, per-head gating, full attention every 4th layer.

Prefill BF16 projection shapes at M = 512:

| projection | N | K | GFLOP/layer | share of A |
| --- | ---: | ---: | ---: | ---: |
| q_proj | 6144 | 2048 | 12.885 | 42.71 % |
| **o_proj** | **2048** | **6144** | 12.885 | 42.71 % |
| k_proj | 1024 | 2048 | 2.147 | 7.12 % |
| v_proj | 1024 | 2048 | 2.147 | 7.12 % |
| g_proj | 48 | 2048 | 0.101 | 0.33 % |
| Σ | | | **30.165 / layer** | 100 % |

Over 40 layers: **1206.6 GFLOP**. **q + k + v + g = 57.29 % of stage A's FLOPs.**
If the layer-0 dense MLP (34.36 GFLOP, once) also lands in this family, o_proj's share
falls 42.71 → 41.5 %, so the conclusion is insensitive.

⚠️ Honest discrepancy: the rev1 probe-derived family total was **1502.8 GFLOP**, +21 % vs
the 1241 GFLOP implied here. I flag it and do not rely on it; the argument below turns on
*shares*, which are stable, not on the absolute GFLOP.

### 4.3 The fork does not touch stage A on the runtime axis [STRUCT]

- Baseline `LagunaRuntimeModel.swift` uses plain `Linear` for all five projections
  (`:75-79`, `:99-106`, `:130-132`, `:166`).
- Candidate HEAD *also* uses plain BF16 `Linear` for the 512-token prefill:
  `DARKBLOOM_FUSED_QKV` is default **OFF** (`LagunaRuntimeModel.swift:114`, `== "1"`), and
  `DARKBLOOM_FUSED_QKV_PROJECTION` is decode-only (`:338`, guarded `:5896-5913` by
  `B==1, L==1`). The live prefill path is `:5607`, `:5634-5641`, fallback `:6085-6094`.
  Independently confirmed at
  `research/maple-tanjiro-pr91-prefill-budget-census.md:815-823`.
- Corroborating source fact: **baseline `15852ee5` contains ZERO `darkbloom` occurrences in
  `matmul.cpp` and ZERO in `quantized.cpp`** (HEAD has 10 and 55). The `matmul.cpp` diff
  `15852ee5..HEAD` is 63 insertions / 216 deletions in one file.

So on the runtime axis stage A is **class 2 — never touched**. The only remaining question
is whether the *kernel* axis touches it, which requires the M5 dispatch routing.

### 4.4 M5 routing of stage A — exact gate arithmetic [STRUCT]

Relevant `matmul.cpp` (HEAD) map: `darkbloom_steel_prefill_tile()` `:82`;
`darkbloom_steel_trace()` `:91`; **`steel_matmul_regular_axpby_nax` `:186`** (tile
`:213-222`, trace `:335`); `steel_matmul_regular_axpby` `:348`; `steel_gemm_splitk_axpby`
`:496`; **`steel_gemm_splitk_axpby_nax` `:645`** (tile `:674-677`, trace `:773`);
`steel_matmul_axpby` `:827`; `gemv_axbpy` `:1014`; `gemv` `:1166`; `Matmul::eval_gpu`
`:1206`; `AddMM::eval_gpu` `:1295`; `BlockMaskedMM::eval_gpu` `:1418`; `gather_mm_rhs`
`:1771`; `gather_mm_rhs_nax` `:1892`; `gather_mv` `:2023`; `gather_mm` `:2133`;
`GatherMM::eval_gpu` `:2264`; `segmented_mm` `:2308`; `SegmentedMM::eval_gpu` `:2471`.

**Regular nax tile selection, `matmul.cpp:213-222`, verbatim logic:**

```
int bm = 128, bn = 128, bk = 512;  int wm = 4, wn = 4;
char devc = d.get_architecture().back();
if (devc=='s' || devc=='c' || devc=='d') {
    bk = (K >= 8192 && K > (M+N)) ? 64 : 256;
    bm = 64;  wm = 2;
}
```

⇒ On M5 Max (`s`): **bm 64 × bn 128 × bk 256, wm 2 / wn 4.** There is no M/N/K awareness
beyond the one `K >= 8192 && K > M+N` case, and **no darkbloom knob anywhere in this
function** (the only darkbloom reference inside it is a trace `printf` at `:335`, which
changes no behaviour).

**Split-K nax tile selection, `matmul.cpp:674-677`:** defaults `bm=bn=128, bk=512,
wm=wn=4`, `split_k_partition_size=4096`; if `(M+N)/2 < 512 || K <= 4096` → `bm=bn=64,
bk=256, wm=wn=2`; then

```
if (darkbloom_steel_prefill_tile() && (M+N)/2 >= 512 && K > 4096) { bm=bn=64; wm=wn=2; }
```

— note it changes **only** bm/bn/wm/wn; `bk` and the split-K partition count are untouched.

**Gates.** nax split-K (`:~921-925`):
`use_nax && batch_size_out==1 && (K >= 3*max(M,N) || (max(M,N) <= 1024 && K > 2*max(M,N)))`.
Non-nax split-K (`:900-901`):
`!use_nax && batch==1 && (_tm*_tn) <= min_tmn_threshold && _tk >= 8 && K >= max(M,N)`,
with `min_tmn_threshold = (devc=='s'||devc=='d') ? 2048 : 1024` (`:897-898`) and `use_nax`
at `:894-896`.

**Resulting M5 routing:**

| projection | max(M,N) | K | nax split-K gate | tile knob fires? | verdict |
| --- | ---: | ---: | --- | --- | --- |
| q_proj | 6144 | 2048 | no (K < 3·6144, max > 1024) | n/a | **regular nax fused — identical in both trees** |
| k_proj | 1024 | 2048 | no (needs `K > 2·1024` strictly) | n/a | **regular nax fused — identical** |
| v_proj | 1024 | 2048 | no | n/a | **regular nax fused — identical** |
| **o_proj** | **2048** | **6144** | **yes** (6144 ≥ 3·2048) | **YES** (K > 4096, (M+N)/2 = 1280 ≥ 512) | **the ONLY part of A the candidate touches on M5**: bm64/bn64/wm2/wn2 vs baseline bm128/bn128/wm4/wn4 |
| g_proj | 512 | 2048 | yes (2048 ≥ 1536) | no (K ≤ 4096) | identical |
| router (N=256) | 512 | 2048 | yes | no (K ≤ 4096) | identical |

**[M4-WALL] M4 routing, for contrast:** `use_nax = false`, so q_proj has
`_tm·_tn = 8·192 = 1536 > 1024 = min_tmn_threshold` ⇒ regular non-nax; k/v (`8·32=256`),
o (`8·64=512`) and g (`8·2=16`) all take non-nax split-K ≈ 4 split-K pairs per layer,
matching the observed 159 pairs / 40 layers ≈ 3.98 (83 regular + 318 MIXED split-K
dispatches = 401). **Every stage-A dispatch is a different kernel on M4 than on M5.**

### 4.5 Stage A classification

**Stage A = class 2 (never touched) on the runtime axis, with a class-1-flavoured exception
at the kernel axis for `o_proj` only.**

- q + k + v + g = **57.29 % of A's FLOPs** are provably the identical kernel with the
  identical tile in both trees on M5.
- o_proj (42.71 %) is touched by exactly one mechanism: a tile-shape override.
- **LIVE under Rule 90.** `benchmark.json` has 97 `editablePaths`, including
  `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp`,
  `…/kernels/steel/gemm` (directory ⇒ `nax.h`), `…/kernels/steel/attn`,
  `…/backend/metal/quantized.cpp`, the `kernels/{quantized*,fp_quantized*}` set, and the
  `mlx-generated/{gemm*,steel_gemm_fused*,steel_gemm_splitk*,steel_gemm_gather*,steel_attention*}`
  twins. A class-2 finding on `steel_gemm_bf16` is **actionable**.

### 4.6 Stage B classification

**Stage B = class 3 [M4-WALL] — dead as evidence.** Every candidate mechanism in B is
inside an nax branch that gen 16 cannot reach: `darkbloom_expert_aligned_gather`
(`quantized.cpp:1204`), `_expert_static_nax_nt_` (`:1459-1463`), the pairwise-scale layout
(`:1361-1400`, `:1566`), `fuse_swiglu` (`fp_quantized_nax.h:1942-1975`),
`darkbloom_stage_bm128_variant` (`:1234`), and the outer `pairwise_contract` predicate
(`:1879-1884`). The M4 trace confirms it ran the *non-aligned* gather kernel
`nvfp4_gather_qmm_rhs_nt_bfloat16_t_gs_16_b_4_bm_16_bn_32_bk_32_wm_1_wn_2_align_M_t_align_N_t_align_K_t`
(`quantized.cpp:1529`). B's 0.929× is a measurement of a code path the ranked host never
executes. **Dead-on-arrival for this analysis** (not dead as a surface — `quantized.cpp`
is editable — but this experiment produced no M5 information about it).

Independent corroboration that B *is* addressed on M5: on M5 `fuse_swiglu` already deletes
`g2_copybfloat16bfloat16` (76 calls, 1.689 ms on M4) and 38 of 77 `compiledSiluProduct`
⇒ 2.445 ms of the M4 glue is M4-only.

### 4.7 The other stages

C 1.633×, D 1.254×, E 1.384×, F 4.971×, G 1.783×, I 2.000× are all outside the ≈1.0× band
and are therefore out of Stage 2's scope by construction. Note D (SDPA) is nax-divergent
too (`bq32/bk{16,32}` vs `bq64/bk{32,64}`; gate `scaled_dot_product_attention.cpp:177-179`,
tiles `:31-36`, `:194-199`), so its 1.254× is also not an M5 statement — but since it is
not in the near band, it is not a Stage-2 item.

---

## 5. Stage 3 — Rank the class-2 items and desk-price the top one

### 5.1 Ranking

Rank = (baseline share) × (1 − speedup) × (editable). The class-2 set has exactly one live
member, so the ranking is short:

| rank | item | base share | 1 − speedup | editable | score |
| ---: | --- | ---: | ---: | --- | --- |
| **1** | **stage A, untouched q/k/v/g sub-slice on the regular nax fused path** | 38.85 % (M4) / 19.89 % (M5 [PROJ]) | 0.016 (exclusive) to 0.000 (identity) | **yes** — `matmul.cpp`, `kernels/steel/gemm`, `mlx-generated/steel_gemm_fused_nax.cpp` | **live, top** |
| — | stage B | 39.17 % | 0.071 | yes | **excluded, class 3** |

Per the brief, **top one only** is priced.

### 5.2 Mechanism (desk answer)

**Mirror the `o_proj` precedent into the regular nax path.**
`steel_matmul_regular_axpby_nax` (`matmul.cpp:186`) selects tiles at `:213-222` with a
two-branch *device-class* heuristic and no shape awareness. The fork has already
demonstrated, in the sibling split-K function, that a shape-conditioned tile override is
both legal and profitable (`darkbloom_steel_prefill_tile`, `:674-677`). The regular path
never received the same treatment.

Two distinct sub-levers, with different physics:

**(i) narrow-N k/v_proj — an occupancy problem.** N = 1024 at bn = 128 gives
`ceil(512/64) × ceil(1024/128) = 8 × 8 = 64` threadgroups for the whole GEMM. On a
~40-core M5 Max that is only ~1.6 threadgroups per core: the tail is the whole kernel.
Dropping to bn = 64 gives 8 × 16 = **128 threadgroups**, restoring occupancy. This is the
same defect #270 `:415-419` measured on M4 as the "k/v narrow-launch bracket" (`wk`/`wv`
78 × 64 TGs; 155 of 237 BF16 dispatches carrying only 12.8 % of the work; 3.7 ms at 87.5 %
efficiency vs 21.4 ms at 15 % of roofline — a ±17.7 ms swing that brackets the 11.40 ms
M5-specific loss).

**(ii) wide-N q_proj — not an occupancy problem.** N = 6144 gives 8 × 48 = **384
threadgroups**, which is occupancy-fine. Its lever is therefore *not* tile shape but
staging: double-buffered `Ws_storage` (#91 §6.4 item C1; `Ws_storage` is 9.2 KB with no
double buffering, and staging serialisation accounts for 39.5 % of prefill). That is a
larger, separate change and I do not price it here beyond noting it is the correct lever
for the 42.71 %-of-A q_proj slice.

Note the asymmetry this predicts: k/v are only 14.24 % of A's FLOPs but ~65 % of A's
*dispatch count* on the split-K M4 path, so a k/v-only fix is cheap to implement and cheap
to measure.

### 5.3 Ceiling in ms, priced under both score conventions

M5 floors from #91 §6.2 at 546.2 GB/s give `attn_proj_qkvo` 24.42 ms + `dense_mlp_layer0`
0.86 + router 0.35 = **25.63 ms floor** for stage A (#270 `:431`), against a [PROJ]
37.93 ms actual ⇒ **12.30 ms above floor**, which #270 §5.3 notes is **77 % of all
above-floor time in `R`**.

| slice | ms | % of score (partial, 0.2592 %/ms) | % of score (total, 0.3781 %/ms) |
| --- | ---: | ---: | ---: |
| stage A, all above-floor | **12.30** | 3.20 % | 4.65 % (#270 says 4.61 %) |
| untouched q/k/v/g sub-slice (57.29 %) | **7.06** | 1.84 % | 2.67 % |
| k/v-only sub-slice (14.24 %) | **1.75** | 0.46 % | 0.66 % |

Both bars are cleared even by the smallest slice: the 3σ detection bar is **1.35 ms**
(σ_Δ = 0.4497 ms, Rule 94.4) and the "+0.2 % of score" non-starter floor is **0.77 ms
(today) / 0.53 ms (end-state)**.

### 5.4 Bit-exactness

**bm / bn / wm / wn changes are bit-exact; `bk` and split-K partition-count changes are
not.** Tile *shape* in M and N repartitions which threadgroup computes which output tile,
but each output element still accumulates over K in the same fp32 order. Changing `bk`
changes the K-blocking, and changing the split-K partition count changes the number of
partial sums that are later summed — both reorder floating-point accumulation.

Corroboration from the fork itself: the shipped `darkbloom_steel_prefill_tile` override
deliberately sets only `bm`, `bn`, `wm`, `wn` and leaves `bk` and
`split_k_partition_size` alone — exactly the bit-exact subset. That is strong evidence the
same discipline was already required and observed.

Any such change must still pass `LagunaUpstreamEquivalence` via
`research/run_upstream_equivalence.sh` (which repairs the debug metallib placement and
refuses to call a zero-test invocation a pass), plus the 64-step drift tripwire.
Recall also from AGENTS.md that M4 cannot reach these code paths at all, so **an M4
equivalence pass is not evidence for an `_nax` tile change** — this experiment would need
an M5 correctness run.

### 5.5 What I deliberately do **not** propose

**F1 / `DARKBLOOM_FUSED_QKV` is pre-cleared dead** (`CURRENT_RESEARCH_STATE.md:4509-4534`)
and I am not resurrecting it. For the record, I re-adjudicated it this round and confirm
the closure: gate `LagunaRuntimeModel.swift:112-114`, prefill use site `:6068`. Document A
(`research/maple-tanjiro-nonmoe-prefill-census.md:534-546`) predicted −1.6 ms; Document B
(`research/maple-tanjiro-pr91-prefill-budget-census.md:784-790,821-822`) has MDE 0.278 % =
0.75 ms against a 0.17 ms effect ⇒ refuted as sub-MDE. **Document B survives.** On M5 the
net is ≈0 ms because −78 steel dispatches are cancelled by +78 `g2_copy` slices
(`research/maple-tanjiro-pr270-r2-f1-preclearance.md:228-234`). Measured on M4 this round:
wall 548.985 → 545.315 (−0.67 %) but paired `--local-iterate` decode_speedup 1.0786 →
**0.7705**, which fails the 0.95 floor outright
(runs `1247bd17-6fdc-409e-9488-3230d218ee4e`, `09c4ed52-53e8-4315-8cf6-6c5afaa55320`).

Also not proposed: the prefill INT8-attention-weights lever, dead per Rule 94.3 because
`attn_proj_qkvo` has AI = **391.5 FLOP/B** and is compute-limited at its 24.42 ms floor —
cheaper weights cannot help a compute-bound GEMM.

---

## 6. Audit of the advisor's numbers (invited)

### 6.1 The four ratios

All four check out arithmetically:
`13855.01/4893.71 = 2.83119`; `372.473/187.791 = 1.98344`;
`190.706 = 372.473 × 512 / 1000`; `96.149 = 187.791 × 512 / 1000`;
`2.83119^0.75 × 1.98344^0.25 = 2.590188`, versus best-ever receipt `cs 2.590559`
(`4b0e051b`) — a 0.014 % gap, consistent with the corpus mean being used for the baseline.

### 6.2 "8.90 %" vs "+9.3 %" — same quantity, two conventions

`0.25 · ln(2.8312 / 1.9834) = 0.08894` (log-gain) and `exp(0.08894) − 1 = 0.09302`
(multiplicative). The brief's 8.90 % and Rule 94.1's +9.3 % are the same prize. Worth
stating because a reader comparing them would otherwise suspect one is wrong.

### 6.3 The two %-of-score-per-ms conventions — reconciled

Two different prefill prices circulate and both are correct in their own frame:

| convention | value | derivation | frame |
| --- | ---: | --- | --- |
| **partial** | **0.2592–0.2600 % / ms** | `0.25 / 96.1–96.5 ms` | marginal value of 1 ms **against today's candidate** |
| **total** | **0.3781 % / ms** | `0.25 / 66.1 ms` | marginal value **at the ~66 ms roofline floor** (end-state) |

Cross-checks that confirm both are in live use:

- 3σ bar 1.35 ms → **0.351 % (partial) / 0.510 % (total)**.
- "+0.2 % of score" non-starter floor → **0.77 ms (partial) / 0.53 ms (total)** — exactly
  #270's quoted "0.53–0.77 ms promotion bar", i.e. that range *is* the two conventions.
- Rule 94.4's "1 GB = 1.831 ms = +0.69 %" uses the total convention:
  `1.831 × 0.3781 = 0.692`.

Recommendation: quote both, or name the convention. §5.3 above quotes both.

### 6.4 Standing audit finding — `PREFILL_NAX_ANALYSIS.md` §6.2 does not exist

Reaffirmed this round. `research/PREFILL_NAX_ANALYSIS.md` is 262 lines with **no numbered
`6.x` headings**, and `grep -n "546.2\|19.465\|35.6\|7.6 ms\|43.2619"` returns nothing.
`research/maple-tanjiro-nonmoe-prefill-census.md:429` cites "`PREFILL_NAX_ANALYSIS.md`
§6.2" as the source of the M5 floors, and Rule 94.4's "`W` 43.2619 ms vs 19.465 GB floor
(35.6 ms) ⇒ ≈7.6 ms ≈ +2.9 % of score" exists **only** in Rule 94.4. The M5 floor table
that is actually reachable is `research/maple-tanjiro-pr91-prefill-budget-census.md`
§6.2 `:618-636` (Σ = 70.07 ms). I believe the citation is a cross-file slip and the numbers
are #91's, but the chain should be repaired before anyone builds on it.

### 6.5 A genuine sign flip worth recording [STRUCT]

`routed_gather_gemm` (`W`) has measured arithmetic intensity **51.6 FLOP/B**
(979.3 GFLOP / 18.968 GB). M4's machine balance is 30.7 FLOP/B ⇒ `W` is **compute-bound on
M4**. M5's balance is 63.5 FLOP/B (at 34.7 TFLOP/s) or 104 (at 57) ⇒ `W` is **DRAM-bound on
M5**. The same family sits on opposite sides of the roofline knee on the two hosts, which
is an independent reason M4 prefill conclusions must never be transferred by scaling.
(`979.3 GFLOP / 43.2619 ms = 22.64 TFLOP/s` achieved on M5.)

---

## 7. What transfers and what does not

**[STRUCT] — transfers M4 → M5 unchanged**

- The ranked denominator is `15852ee5`; the local harness never times any baseline tree.
- Baseline `LagunaRuntimeModel.swift` is 430 lines with zero `DARKBLOOM_`; baseline
  `matmul.cpp`/`quantized.cpp` have zero `darkbloom`.
- Both trees run the 512-token Q/K/V/O/`g_proj` prefill through plain BF16 `Linear`.
- On M5: q/k/v/g take the regular nax fused path with a *device-class-only* tile heuristic
  (`matmul.cpp:213-222`) and no darkbloom knob; only o_proj takes nax split-K where
  `darkbloom_steel_prefill_tile` fires.
- q + k + v + g = 57.29 % of stage A's FLOPs.
- `nax_available` predicate, kill switch, suffix map, and the per-family nax divergence
  table (§2.5, §4.4).
- Rule-90 editability of `matmul.cpp`, `kernels/steel/gemm`, `quantized.cpp` and their
  `mlx-generated` twins.
- bm/bn/wm/wn are bit-exact; bk and split-K partition count are not.

**[M4-WALL] — does not transfer**

- Every millisecond in §3: 611.859 / 546.408 clean walls, the 607.644 / 548.441
  instrumented walls, the primary and sensitivity tables, the exclusive-time table.
- The 78.02 % / 82.26 % headlines (baseline-share, inflated on M4 — §3.9).
- prefill 1.1198×, and stage B's 0.929×.
- Dispatch/command-buffer counts (2637→1222, 2126→1066): the M4 kernel families differ.

**[PROJ] — model-dependent**

- Stage A = 37.93 ms on M5, and hence the 12.30 / 7.06 / 1.75 ms ceilings. Derived by
  scaling the M4 census by 1/5.66 (§3.8) — **not** an independent measurement.
- The 25.63 ms stage-A floor and the Σ 70.07 ms prefill floor (from #91 §6.2 at
  546.2 GB/s), which Rule 94.5 warns may be over-estimates because #619 showed binding
  bytes overstate traversal by 11.5× on decode.

**[M5-RCPT]**

- decode 13 855.01 µs/step, prefill 372.473 µs/token (corpus mean, n = 1176).
- candidate 4 893.71 µs/step and 96.149 ms/512 (our own receipts;
  `prefill_ms 96.14921 ± 0.13681`, n = 3, CV 0.142 %).
- best-ever ours `4b0e051b`, `cs 2.590559`.

**Bottom line on transfer:** decode's 2.83× transferred to M4 within 0.15 % because decode
runs identical kernels on both hosts. Prefill's 1.98× did not transfer at all because
94.3 % of it is nax-divergent. Any future prefill experiment that cannot reach `_nax` code
on its host is measuring a different program.

---

## 8. Reproduction

```bash
# Stage 0 — build and time the pinned ranked baseline against HEAD (ABBA, clean walls)
BASE_COMMIT=15852ee52858def42ddd4f32bca7e59d275e020e \
  research/r106f_build_base_worker.sh          # WT=/tmp/r106f-base DEST_DIR=/tmp/r106f/base
ORDER="cand base base cand" REPS=6 DECODE=40 SETTLE=20 \
  research/r106f_calibrate.sh                 # -> research/pr270-logs-r106f/stage0.calib.log
python3 research/r106f_stage0_arith.py        # -> .../stage0.arith.log

# Stage 1 — paired instrumented per-family census
ORDER="cand:1 base:1" REPS=5 TOP=60 SETTLE=20 \
  BASE_WORKER=/tmp/r106f/base/mlxfast-runtime-worker \
  CAND_WORKER=.build-worker/release/mlxfast-runtime-worker \
  research/r106f_census_paired.sh
python3 research/r106f_paired_families.py \
  research/pr270-logs-r106f/census.base.split1.log \
  research/pr270-logs-r106f/census.cand.split1.log \
  > research/pr270-logs-r106f/stage1.paired.log

# W&B publication
python3 research/r106f_stage1_wandb_log.py
```

### Artifacts (Rule 75)

| artifact | sha256 | bytes |
| --- | --- | ---: |
| candidate worker `.build-worker/release/mlxfast-runtime-worker` | `6e9c1078ad2d2d693c4347776218f96c417ef965852f3cfbe687130031918420` | 49 209 912 |
| baseline worker `/tmp/r106f/base/mlxfast-runtime-worker` | `c1c8cbe27752912a40c33613d022e166cb5578b5e3503bf2a36187c378ed450f` | 49 904 344 |
| candidate `mlx.metallib` | `8e8b18afaee1ed5a0190403f79a4cc74b9bebcb52b50c4b67d0ed91dc73097ec` | 158 502 072 |
| baseline `mlx.metallib` | `4695bfeeaeaf4e598df1d163af776a1c1a8e8288273f2a1e2ee9441e5f3aa17d` | 157 739 544 |

Metallib fingerprints: candidate
`mlxfast-metallib-fingerprint-v1 f1fe2c81f720850656ea5a42953d0c6d4028fd6b37204e15155d91150b75e589`;
baseline
`mlxfast-metallib-fingerprint-v1 71f28be208e298ab6e417155f7f0e91030c320c999286a70a2996b05550dcf4e`.

Committed logs under `research/pr270-logs-r106f/`: `stage0.calib.log`, `stage0.arith.log`,
`census.base.split1.log`, `census.cand.split1.log`, `stage1.paired.log`.
The two ~1.7 MB `*.worker.err` traces are **not** committed (raw per-dispatch dumps); they
are regenerable from the commands above.

---

## 9. Open items, gaps, and follow-ups

### 9.1 Gaps in this deliverable — stated plainly

1. **No M5 measurement of the baseline tree exists anywhere.** Every M5 baseline-share
   number in this document is [PROJ] through a factor (§3.8) that is not independent of the
   M4 census. **The smallest resolving measurement is a paired instrumented prefill census
   run on the ranked M5**, which I cannot perform from this host.
2. **The cross-machine share agreement (0.87 %) is circular** and I have said so rather
   than banking it (§3.8).
3. **Split0 replicate missing.** The paired census job was cancelled at a controller
   boundary after the split1 pair completed; only one replicate of the instrumented pair
   exists. Stage 0's clean walls partially compensate.
4. **The 1206.6 vs 1502.8 GFLOP discrepancy** in stage A's FLOP total (+21 %) is unresolved
   (§4.2). Shares, not absolutes, carry the argument.
5. **Instrument asymmetry ~1 %** (1.1079× instrumented vs 1.1198× clean).
6. **`d.get_architecture()` on the ranked M5 has never been printed.** The whole §4.4
   routing table depends on the returned suffix being `s`. This is a one-line trace on an
   M5 run and would convert a derivation into an observation.
7. **No frontier strategy consult informed the Stage-3 ranking.** See §10.

### 9.2 Suggested follow-ups (not implemented)

1. **k/v narrow-N tile override in `steel_matmul_regular_axpby_nax`** — the ranked item.
   Smallest coherent change: a shape-conditioned `bn = 64` when `N ≤ 1024`, restoring
   64 → 128 threadgroups. Ceiling ≈1.75 ms = 0.46–0.66 % of score; bit-exact by §5.4;
   needs an M5 correctness run because M4 cannot reach the code.
2. **Double-buffered `Ws_storage` staging for wide-N q_proj** (#91 §6.4 C1). Larger, and
   the correct lever for the 42.71 % of A that is *not* an occupancy problem. Priced in #91
   as the highest-value open item.
3. **Print `d.get_architecture()` and the selected tile tuple on the ranked host** (a
   `darkbloom_steel_trace`-style one-liner already exists at `matmul.cpp:335`/`:773`).
   Converts §4.4 from derivation to observation for the price of one receipt.
4. **Repair the `PREFILL_NAX_ANALYSIS.md` §6.2 citation chain** (§6.4).
5. **Adopt the convention-named score price** in Rule 94.4 (§6.3) so "0.2592" and "0.3781"
   stop looking like a contradiction.

---

## 10. Rule-compliance ledger

| rule / constraint | status |
| --- | --- |
| Receipts consumed | **0.** `senpai/submit-official.sh` never invoked. |
| Scope fence: prefill **time** only | Held. Prefill **bytes** belongs to maple-fern (R106-I, PR #625) and is cited, never duplicated. No work touching frieren #597, nezuko #616, or decode bytes (#615, #619). |
| Rule 75 (artifact hashes) | §8: sha256 + byte size for all four compiled artifacts, plus both metallib fingerprints. |
| Rule 86 (`--local-iterate` deltas are not evidence) | Held. The only `--local-iterate` numbers quoted are in §5.5 as *negative* evidence against a pre-cleared-dead lever, explicitly labelled. All positive claims come from the direct paired probe. |
| Rule 90 (editability) | §4.5: the ranked surface is verified against `benchmark.json`'s 97 `editablePaths`. |
| Rule 94.0 (three greps before calling anything novel) | Applied to `darkbloom_steel_prefill_tile`, the nax tile-selection sites, and F1 before making any novelty claim. |
| Rule 94.3 (F1 dead, INT8 attention weights dead) | Both honoured and re-affirmed in §5.5. |
| Four-tag discipline | Every table and claim tagged; consolidated in §7. |
| "Build nothing new without a new revision" | Held. Only the pre-existing GPUPROF instrument and a per-tree metallib build were used; no new runtime mechanism was written. |
| Instrument reverted before submission | Final commit: `device.cpp` and `device.h` restored to `3241e5e5`, `git diff --stat 3241e5e5 HEAD -- Sources/ Vendor/` empty. |
| Frontier strategy consult | **FAILED and recorded.** Sub-agent `563209e9-b073-5aa7-916f-e6585fd3da2d` (batch `r106f-stage0-strategy-1`, key `transfer-strategy`, frontier general-purpose) terminated with `SystemExit: 143`. Its five questions — M4→M5 transfer taxonomy, discriminating experiments, harmonic-mean algebra of the two halves, and an independent strategy ranking — were never answered. **The Stage-3 ranking in §5.1 is therefore my own, uncorroborated by any independent strategy review.** A rerun of that consult is the cheapest way to challenge it. |
| Sub-agent consults that did succeed | nax kernel-selection map (`709422d7-2fec-5b25-9711-3b121e18b812`), F1 adjudication (`89b9c697-…`). Both are cited inline. |
