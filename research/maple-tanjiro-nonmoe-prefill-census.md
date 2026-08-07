# Non-MoE prefill census (PR #270, maple-tanjiro)

Marginal-cost ledger of the **~54.6 ms of the 97.895 ms M5 prefill that is not the
routed expert gather-GEMM**, one row per kernel family.

- Assignment: `maple-2026-08-07i-nonmoe-prefill-census`, revision `r1`, PR #270.
- Base: `b731a0fdc63ec544971f3c3e781491c2ca65c894`.
- **Submitted paths: none.** Everything here is research-only.
- No ranked slot was consumed. No W&B run exists.

---

## 0. Read this before using any number

The advisor's item 4 is binding, so every fact below is tagged:

| tag | meaning |
| --- | --- |
| **[STRUCT]** | dispatch counts, shapes, grid/threadgroup geometry, threadgroup memory, bound bytes, routing predicates. Derived from source or from a dispatch trace. **Transfers to M5** except where a HOST-DIVERGENT flag says otherwise. |
| **[M4-WALL]** | wall-clock measured on this M4 Pro host. **Not M5 evidence.** Used only to build ratios, never quoted as an M5 cost. |
| **[PROJ]** | an M5 millisecond obtained by scaling [M4-WALL] onto the measured M5 anchor `S = 97.89475 ms`. A projection, not a measurement. |
| **[M5-RCPT]** | a number from an official M5 receipt already in the record. |

Where a quantity is not measurable on this host I say so instead of substituting a
local timing. The three families that are literally unmeasurable here
(`_nax` gather-QMM tiles, `_nax` steel regular tiles, `sdpa_full_self_attention_nax`)
are marked **NOT MEASURABLE HERE**.

### Host

Apple **M4 Pro**, 20 GPU cores, 14 CPU cores, 48 GiB, macOS 26.5.2.
`applegpu_g16s`, Apple GPU **generation 16** ⇒ `is_nax_available() == false`
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:1021-1039` requires
macOS ≥ 26.2 **and** `gen >= 17`). `maxThreadgroupMemoryLength = 32768 B`.
< 64 GiB ⇒ forced `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`.

The ranked host is one M5 Max. Core count is not verifiable from this checkout;
every "threadgroups per core" figure for M5 below assumes **40 cores** and is
labelled as an assumption.

---

## 1. Definitional corrections (these change how the 54.6 ms should be read)

1. **`W = 43.2619 ± 0.402 ms` is not "the MoE staging portion".**
   The assignment brief calls it that, but the record
   (`research/maple-fern-pr40-result.md:58,604`;
   `RESEARCH_STATE_ARCHIVE_through-round-21.md:4622-4702`;
   `CURRENT_RESEARCH_STATE.md:220`) defines `W` as the **marginal wall of the
   `fp_gather_qmm_rhs_expert_nax` routed-expert GEMM alone**. So `R = S − W = 54.633 ms`
   still contains genuinely-MoE work: the route sort/scatter, the sorted MoE tail,
   the router GEMM and tournament, and the entire shared expert. This census
   itemises all of it rather than pretending `R` is "attention + glue".
   **[STRUCT]** `W` covers **38** routed blocks, not 39 — see §3.

2. **"94.2 % of prefill is NAX-divergent" is an M4 number with an M4 denominator**
   (`research/maple-fern-prefill-roofline.md:20-35`). It has drifted into three
   documents as a direct M5 claim
   (`RESEARCH_IDEAS_2026-08-06_09:00.md:189`, `PREFILL_LEDGER_INSTRUMENT.md:10`,
   `RESEARCH_STATE_ARCHIVE_through-round-21.md:5823`). The correct M5 statement is in §6.

3. **The 31.28 ms "unattributed pool" is not a measurement.**
   `CURRENT_RESEARCH_STATE.md:3530-3567` reproduces it only under an unstated
   500 GB/s + 20.26 % zero-row discount pair. Honest band 22.9–37.9 ms, central 27.88.
   This census independently reproduces **27.83 ms** (§5) and decomposes it.

4. **Command-buffer overhead cannot explain the residual.** M5 marginal cost is
   +27.177 µs/cb **[M5-RCPT]** (`research/nezuko-mbcap-up-prereg.md:80-82`,
   receipt `3e6fdcba`). The whole 81-command-buffer prefill boundary is O(2.1 ms).

---

## 2. Method

### 2.1 Instrumentation (LOCAL-ONLY, reverted before submission)

`research/pr91-gpuprof-hook.patch` re-applied to
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.{cpp,h}`. It emits

- `GPUPROF <gpu_start> <gpu_end> <nops> <input_bytes> <name>|<name>|…` per command buffer, and
- `GPUPSO <name> maxThreads=… execWidth=… tgMem=…` once per compiled pipeline state.

Plus a LOCAL-ONLY mirror of the pre-existing `darkbloom_steel_trace()` print into the
two **non-NAX** steel paths of `matmul.cpp` (regular ~`:521`, split-K ~`:645`), which
the upstream code only instruments on the `_nax` paths (`:358`, `:824`).

Both edits are inside the tree hashed by
`Sources/MLXFastTrustedHarness/VendoredMetalFingerprint.swift:19-21`, so
`./benchmark.sh` would refuse them. The census therefore drives the worker directly:

```
CLANG_MODULE_CACHE_PATH="$PWD/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved
bash research/tanjiro_prefill_census.sh     # DARKBLOOM_GPU_PROFILE=1, SPLIT in {0,1}
bash research/tanjiro_steel_trace.sh
```

Logs: `research/pr270-logs/{split0,split1,steeltrace}.worker.err`.

### 2.2 Two acquisition modes

| | SPLIT=0 (shipped batching) | SPLIT=1 (one dispatch per command buffer) |
| --- | ---: | ---: |
| wall | 545.718 ms | 548.885 ms |
| GPU busy, **sum** | 540.396 ms | 576.734 ms |
| GPU busy, **union** | 540.396 ms | 546.019 ms |
| command buffers | 81 | 1066 |
| dispatches | 1222 | 1222 |
| bound bytes | 24.717 GiB | 28.834 GiB |

**[M4-WALL]** All 12 forward passes emitted `token=5991`, matching the public golden.
Peak RAM 20.71 GB. Dispatch count 1222 is identical to PR #91's independent census.

Two facts fall straight out:

- At SPLIT=0, **sum ≡ union**: the shipped prefill is **strictly serial on the GPU**.
  There is no inter-kernel overlap and no gap to reclaim; host gap is 5.32 ms of 545.7.
- Union grows 5.62 ms over 985 extra command buffers ⇒ **5.7 µs/cb instrument tax**
  on this host, reconciling PR #91's independently measured 5.88 µs.

Consequence for attribution: SPLIT=1 per-kernel times sum to 576.7 ms, 36.3 ms more
than the serial truth, because kernels that overlap under the shipped batching are
each charged in full. The largest such kernel is `arangeuint32` (26.586 ms of
SPLIT=1 time) which at SPLIT=0 is **provably fully hidden** ⇒ its true marginal cost
is **0 ms**. The ledger below therefore drops `arangeuint32` and deflates every
remaining family by `540.396 / 550.148 = 0.982275` so the family column sums to the
serial anchor.

### 2.3 Score conversion

Prefill is worth **0.374750 % of score per millisecond** of `S`.
Paired single-run noise: σ(S) = 0.318 ms (n = 16), σ_Δ ≈ **0.4497 ms**,
so **3σ = 1.35 ms ≙ 0.506 % score** is the single-run detection floor.
Anything below that line is not testable in one ranked pair, no matter how real.

---

## 3. [STRUCT] Structural inventory — this is the part that transfers to M5

### 3.1 Layer census, reconciled three independent ways

- 39 × `steel_attention` + 1 × `sdpa_vector` = **40 attention layers** (layer 39 is the
  single-row terminal-fusion path).
- 29 × sliding QK-norm-RoPE + 10 × full QK-norm-YaRN + `rope` + `rope_single` = **41**.
- 39 × `laguna_residual_rms` + 1 × `…_router` variant = **40**.
- 38 × `laguna_prefill_router_tournament_ordinal_norm_v1`
  + 1 × `laguna_decode_router_top8_ordinal_table_norm_v1` = **39 MoE layers (1–39)**;
  layer 0 is dense.

**This settles the 38-vs-39 open item recorded at `CURRENT_RESEARCH_STATE.md:346`:**
38 MoE layers take the full sorted prefill path, layer 39 takes the single-row
terminal-fusion path. `nvfp4_gather_qmm_rhs_nt` fires 76 = 38 × 2 times, so **`W`
prices 38 routed blocks, not 39**. `arangeuint32` fires 76 = 38 × 2 for the same reason.

`_h1_` in the prefill QK kernel names confirms `lagunaPrefillQKHeadsPerGroup = 1`.
The 114 multi-row `nvfp4_qmm_t*` calls are the shared expert:
38 × (gate,up as two fused split-K + down).

### 3.2 Steel GEMM route table — measured ground truth, this host

From `research/pr270-logs/steeltrace.worker.err`, ÷2 forward passes. Totals reconcile
exactly against the dispatch census (split-K 155, regular 82).

| route | shape | n / prefill | grid (threadgroups) | group | dispatching site |
| --- | --- | ---: | --- | --- | --- |
| split-K `bm32_bn32_bk16_wm2_wn2` | M=512 N=1024 K=2048 parts=2 | **78** | (32,16,2) = 1024 | (32,2,2) = 128 | `wk` + `wv` (39 + 39) |
| split-K | M=512 N=256 K=2048 parts=2 | **38** | (8,16,2) = 256 | (32,2,2) | router GEMM |
| split-K | M=512 N=64 K=2048 **parts=4** | **29** | (2,16,4) = 128 | (32,2,2) | `g_proj`, sliding layers |
| split-K | M=512 N=48 K=2048 **parts=4** | **10** | (2,16,4) = 128 | (32,2,2) | `g_proj`, full layers (MN_naligned) |
| regular `bm64_bn64_bk16_wm2_wn2` | M=512 N=8192 K=2048 | **31** | (128,8,1) = 1024 | (32,2,2) | `wq` sliding 29 + layer-0 dense gate,up 2 |
| regular | M=512 N=2048 K=8192 | **30** | (32,8,1) = 256 | (32,2,2) | `wo` sliding 29 + layer-0 dense down 1 |
| regular | M=512 N=6144 K=2048 | **10** | (96,8,1) = 768 | (32,2,2) | `wq` full |
| regular | M=512 N=2048 K=6144 | **10** | (32,8,1) = 256 | (32,2,2) | `wo` full |
| regular | M=512 N=2048 K=2048 | **1** | (32,8,1) = 256 | (32,2,2) | layer-39 `[K;V]` bank |

Each split-K dispatch is followed by one `steel_gemm_splitk_accum` (155 total),
grid `(N, M, 1)` **threads**, block (32,32,1).

**Correction to the geometry table circulated earlier: `g_proj` uses `parts = 4`, not 2.**

### 3.3 The exact split-K predicate (`matmul.cpp:971-983`, `:1008-1010`)

```
_tm = ceil(M/16), _tn = ceil(N/16), _tk = K/16      // divisor is 16, NOT the tile
min_tmn_threshold = 2048            for devc == 's'

Case 1 (non-NAX, this host):
   !use_nax && batch==1 && _tm*_tn <= 2048 && _tk >= 8 && K >= max(M,N)
Case 2 (NAX, the ranked host):
   use_nax && batch==1 && ( K >= 3*max(M,N)
                            || (max(M,N) <= 1024 && K > 2*max(M,N)) )
```

Every route in §3.2 is reproduced exactly by Case 1 (e.g. N=2048 ⇒ `_tn`=128,
32×128 = 4096 > 2048 ⇒ regular).

### 3.4 [STRUCT] Derived M5 routing — the single most important divergence

Applying Case 2 to the same shapes:

| shape | M4 (Case 1) | M5 (Case 2) | why |
| --- | --- | --- | --- |
| `wk`, `wv` M=512 N=1024 K=2048 | **split-K**, parts 2 | **regular** | `K ≥ 3·max` fails; `max ≤ 1024` holds but `K > 2·max` is `2048 > 2048` = **false** — an exact tie |
| `wq` N=8192 / 6144 | regular | regular | — |
| `wo` K=8192 N=2048 | regular | **split-K** | `8192 ≥ 3·2048` |
| dense down K=8192 | regular | **split-K** | same |
| router N=256, `g_proj` N=64/48 | split-K | split-K | — |

M5 regular = 120 dispatches (wq 39 + dense gate/up 2 + `[K;V]` 1 + **wk 39 + wv 39**).
M5 split-K = 117 (+117 accum). Total M5 BF16 GEMM kernels **354** vs M4's 392.

M5 NAX regular tile is `bm64 bn128 wm2 wn4`, group (32,4,2) = 256 threads,
`swizzle_log = 2` (`matmul.cpp:228-238`, `:305-330`). So on M5:

| shape | M5 grid (threadgroups) | ×/prefill | TG per core @40 |
| --- | ---: | ---: | ---: |
| **`wk` / `wv`** N=1024 | **(8,8,1) = 64** | **78** | **1.6** |
| `wq` sliding N=8192 | (64,8,1) = 512 | 29 | 12.8 |
| `wq` full N=6144 | (48,8,1) = 384 | 10 | 9.6 |
| `g_proj` split-K | (16,1,1) = 16 | 39 | 0.4 |
| router split-K | (64,1,1) = 64 | 38 | 1.6 |

**78 of the 120 M5 regular GEMM dispatches launch 64 threadgroups onto a ~40-core
machine.** That is the structural headline of this census and the basis of F1 (§7).

### 3.5 [STRUCT] Pipeline-state ground truth

Measured with `MTL::ComputePipelineState` accessors at compile time (`GPUPSO` records
in `research/pr270-logs/split1.worker.err`). Steel GEMM and steel attention are
JIT-compiled from `mlx-generated`, so they appear in **no** static metallib and this is
the only route to their real numbers. `maxThreadgroupMemoryLength = 32768 B` on this host.

| kernel | maxThreads/TG | execWidth | tgMem B | TG resident per core, tgMem-limited |
| --- | ---: | ---: | ---: | ---: |
| `steel_gemm_fused_nt_…bm64_bn64_bk16_wm2_wn2…` | **128** | 32 | **6144** | 5 |
| `steel_gemm_splitk_nt_…bm32_bn32_bk16_wm2_wn2_MN_taligned…` | **128** | 32 | **3072** | 10 |
| `steel_gemm_splitk_nt_…MN_naligned_K_taligned` | 128 | 32 | 3072 | 10 |
| `steel_gemm_splitk_accum_bfloat16_float32` | 1024 | 32 | 0 | — |
| `steel_attention_bfloat16_bq32_bk16_bd128_wm4_wn1_maskbfloat16…` | **128** | 32 | **14848** | **2** |
| `sdpa_vector_bfloat16_t_128_128_nomask_qnt_nc_nosinks` | 1024 | 32 | **16896** | 1 |
| `nvfp4_gather_qmm_rhs_nt_…bm_16_bn_32_bk_32_wm_1_wn_2…` | 1024 | 32 | 3840 | 8 |
| `nvfp4_qmm_t_…gs_16_b_4_alN_true_batch_0` | 1024 | 32 | **5120** | 6 |
| `nvfp4_qmm_t_splitk_fused_…gs_16_b_4_alN_true` | 1024 | 32 | 5120 | 6 |
| `custom_kernel_laguna_prefill_router_tournament_ordinal_norm_v1…` | 1024 | 32 | **3584** | 9 |
| `custom_kernel_laguna_residual_rms_bf16_2048_v1…` | 1024 | 32 | **144** | — |
| `rmsbfloat16` | 1024 | 32 | 144 | — |
| `custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1…` | 1024 | 32 | 4240 | 7 |
| `custom_kernel_mlx_lm_route_csort_scatter_fused_m8_u32_v4…` | 1024 | 32 | **2080** | 15 |
| `custom_kernel_laguna_prefill_sliding_qk_norm_rope_bf16_128_h1_v2…` | 1024 | 32 | 0 | — |
| `custom_kernel_laguna_prefill_full_qk_norm_yarn_bf16_128_h1_v2…` | 1024 | 32 | 0 | — |
| `custom_kernel_laguna_prefill_sorted_moe_tail_bf16_v1…` | 1024 | 32 | 0 | — |
| `gather_frontbfloat16_uint32_int_2`, `arangeuint32`, all `g*_`/`v*_` elementwise, compiled SwiGLU | 1024 | 32 | 0 | — |
| `custom_kernel_laguna_lmhead_coarse_argmax_stage1_v5…` | 1024 | 32 | 256 | — |
| `custom_kernel_laguna_lmhead_exact_winner_bf16_midpoint_threshold_v1…` | 1024 | 32 | 16 | — |
| `gemv_al_bfloat16_bm8_…` / `bm4_…` (load-time) | 256 / 128 | 32 | 0 | — |

Notes that matter:

- The `maxThreads = 128 / 256` values are **declared** `[[max_total_threads_per_threadgroup]]`
  attributes (`WM*WN*32`), not register-limited ceilings. They are therefore useless as an
  occupancy proxy for the steel family — unlike the gather-QMM family, where 1024 is the
  API ceiling and equally uninformative. **No family in this prefill exposes a
  register-driven occupancy cliff through this API.**
- **`steel_attention` at 14848 B of threadgroup memory can hold only 2 threadgroups per
  core** (32768/14848), i.e. 256 threads = 8 simdgroups resident. That is the tightest
  occupancy constraint anywhere in the non-MoE prefill.
- Two source-derived figures circulated earlier are wrong and are corrected here:
  `laguna_residual_rms_bf16_2048_v1` is **144 B**, not 132 (alignment padding), and the
  lm-head exact-winner kernel is **16 B**, not 4.
- **No prefill family calls `setThreadgroupMemoryLength`.** All shared memory is
  statically declared, so `staticThreadgroupMemoryLength` is the whole story.
- Grid conventions differ and must not be mixed: `MLXFast.metalKernel(grid:)` (every
  `Sources/MLXFastModel` and `SwitchLayers` kernel) takes **total threads**; MLX steel
  GEMM/attention take **threadgroups**; MLX `gather` and split-K accum take **threads**.

### 3.6 [STRUCT] Geometry of the custom Laguna families

| family | grid | group | TGs | tgMem | source |
| --- | --- | --- | ---: | ---: | --- |
| prefill sliding QK-norm+RoPE | (2304, 512, 1) threads | (32,1,1) | **36 864** | 0 | def `LagunaRuntimeModel.swift:2422`, wrapper `:2686`, dispatch `:6036-6058` |
| prefill full QK-norm+YaRN | (1792, 512, 1) threads | (32,1,1) | **28 672** | 0 | def `:2602`, wrapper `:2731` |
| (unused 4-head twins) | — | (128,1,1) | 9216 / 7168 | 0 | `:2337` / `:2511` |
| residual RMSNorm 2048 | (262 144,1,1) threads | (512,1,1) | 512 | 144 | def `:1014-1052`, wrapper `:1098-1117`, prefill branch `:10383-10396` |
| router tournament (ordinal) | (256, rows, 1) threads | (256,1,1) | 512 | 3584 | def `:9379/:9388`, grid `:9430-9437`, selector `:9440-9456`, call `:9486` |
| sorted MoE tail | (512, rows, 1) threads | (256,1,1) | 1024 | 0 | def `:9643`, wrapper `:9709-9739`, call `:10230-10237` |
| fused counting-sort + scatter | (8192,1,1) threads | (256,1,1) | **32** | 2080 | `SwitchLayers.swift:249-317`, dispatch `:330-336` |
| row gather `gather_front…` | (1024, 4096) threads | (32,32,1) | 4096 | 0 | `SwitchLayers.swift:344/:364`, `indexing.cpp:57,:91-96,:118-128` |
| steel attention (non-NAX) | (16, H, 1) TGs, H=64 sliding / 48 full | (32,4,1) | 1024 / 768 | 14848 | `scaled_dot_product_attention.cpp:194-199`, grid `:323-326` |
| `sdpa_vector` (layer 39) | (B·H, qL, 1) TGs | (1024,1,1) | — | 16896 | `:329`, `:358-359` |

Two structural observations worth carrying forward:

- **The fused counting-sort/scatter launches only 32 threadgroups** (`routeSortTile = 128`,
  n = 4096) and **each of them scans all 4096 keys**, i.e. 131 072 key reads to sort 4096
  elements. On 20 cores that is 1.6 TG/core; on a 40-core M5 it is 0.8.
- **All 30 sliding layers attend over all 512 positions at prefill.**
  `createAttentionMask` returns `.causal` (`KVCache.swift:169`, rotating override `:807`),
  so the "sliding layers only need 512 positions" saving is decode-only and void here.
  Sliding layers cost more than full ones purely because H = 64 vs 48.

### 3.7 [STRUCT] Analytic work budget (`python3 research/prefill_budget.py --tokens 512`)

| stage | weight GB | act GB | GFLOP | % FLOP | FLOP/byte |
| --- | ---: | ---: | ---: | ---: | ---: |
| attn_proj_qkvo | 2.862 | 0.881 | 1465.3 | 51.8 | 391.5 |
| routed_experts | 17.666 | 1.799 | 1005.0 | 35.5 | 51.6 |
| attn_core | 0.000 | 0.713 | 161.4 | 5.7 | 226.3 |
| shared_expert | 0.069 | 0.225 | 125.6 | 4.4 | 427.4 |
| dense_mlp_layer0 | 0.101 | 0.029 | 51.5 | 1.8 | 396.4 |
| router | 0.041 | 0.092 | 20.9 | 0.7 | 157.5 |
| lm_head | 0.411 | 0.000 | 0.4 | 0.0 | 1.0 |
| norm_rope | 0.000 | 0.965 | 0.0 | – | – |
| moe_tail | 0.000 | 0.818 | 0.0 | – | – |
| embedding | 0.002 | 0.002 | 0.0 | – | – |
| **TOTAL** | **21.152** | **5.524** | **2830.2** | 100.0 | **106.1** |

Cross-check: analytic 26.676 GB = 24.84 GiB against the measured SPLIT=0 bound bytes
24.717 GiB. Agreement to 0.5 % validates both the trace and the model.

Per-site BF16 GEMM work, from §3.2: `wq` sliding 17.18 GFLOP each (498.2 total),
`wq` full 12.88 (128.8), `wo` sliding 17.18 (498.2), `wo` full 12.88 (128.8),
dense gate/up 17.18 (34.4), dense down 17.18 (17.2), `[K;V]` bank 4.295 (4.3),
**`wk`/`wv` 2.147 each (167.5 total)**, router 0.537 (20.4),
`g_proj` sliding 0.134 (3.9), `g_proj` full 0.101 (1.0). **Σ = 1502.7 GFLOP.**

---

## 4. The ledger

Anchors: `S = 97.89475 ms` **[M5-RCPT]**, `W = 43.2619 ± 0.402 ms` **[M5-RCPT]**,
`R = S − W = 54.633 ms`.

### 4.1 [M4-WALL] Measured family roll-up, deflated to the serial anchor

`arangeuint32` dropped (fully hidden ⇒ 0 marginal cost); remaining families ×0.982275
so the column sums to the SPLIT=0 serial busy time 540.396 ms.

| family | calls / prefill | M4 ms | % of M4 busy |
| --- | ---: | ---: | ---: |
| routed_gather_gemm (= `W`) | 76 | 260.907 | 48.3 |
| **steel_gemm_bf16** | **392** | **214.698** | **39.7** |
| attention_core | 40 | 27.630 | 5.1 |
| nvfp4_dense_qmm (shared expert) | 116 | 19.648 | 3.6 |
| elementwise | 234 | 4.648 | 0.9 |
| qk_norm_rope | 41 | 4.136 | 0.8 |
| sort_scatter (− arange) | 78 | 2.598 | 0.5 |
| moe_tail | 38 | 2.535 | 0.5 |
| rms_norm | 83 | 1.691 | 0.3 |
| router tournament | 40 | 0.940 | 0.2 |
| lm_head | 5 | 0.655 | 0.1 |
| other | 3 | 0.308 | 0.1 |
| **Σ** | **1146** | **540.394** | 100.0 |

### 4.2 [PROJ] Projection A — transfer factor anchored to `S`

The two hosts are not related by one scalar, because part of the prefill is
HOST-IDENTICAL (same kernel, same tiles, bandwidth-bound) and part is HOST-DIVERGENT
(different kernel family entirely). Projection A splits them:

- HOST-IDENTICAL glue (elementwise, sort/scatter, rms_norm, qk_norm_rope, moe_tail,
  router tournament, other) totals 17.511 ms on M4. It is bandwidth-bound, so it scales
  by the bandwidth ratio 546.2/260.2 = 2.099 ⇒ **8.34 ms** on M5.
- The remainder of `R` must then be 54.633 − 8.34 = **46.29 ms**, giving the
  HOST-DIVERGENT transfer factor 261.976/46.29 = **5.66×**.
- Sanity: the independently measured gather GEMM gives 260.907/43.262 = **6.03×**, and a
  naive uniform factor would be 279.487/54.633 = 5.12×. The three are mutually coherent;
  5.66× sits between the glue factor (2.10×) and the gather factor (6.03×) as it should.

| family | [PROJ] M5 ms | % of `S` | % of `R` |
| --- | ---: | ---: | ---: |
| routed_gather_gemm (`W`, measured) | 43.262 | 44.2 | — |
| **steel_gemm_bf16** | **37.93** | **38.7** | **69.4** |
| attention_core | 4.88 | 5.0 | 8.9 |
| nvfp4_dense_qmm | 3.47 | 3.5 | 6.4 |
| elementwise | 2.21 | 2.3 | 4.0 |
| qk_norm_rope | 1.97 | 2.0 | 3.6 |
| sort_scatter | 1.24 | 1.3 | 2.3 |
| moe_tail | 1.21 | 1.2 | 2.2 |
| rms_norm | 0.81 | 0.8 | 1.5 |
| router tournament | 0.45 | 0.5 | 0.8 |
| lm_head | 0.31 | 0.3 | 0.6 |
| other | 0.15 | 0.2 | 0.3 |
| **Σ over `R`** | **54.63** | **55.8** | **100.0** |

**Coverage: 1222 of 1222 dispatches and 540.396 of 540.396 ms of serial GPU busy time
are attributed. 100 % of `R` is allocated.** The stopping condition (≥ 85 %) is met with
margin; the binding uncertainty is the projection factor, not the attribution.

### 4.3 [PROJ] Projection B — hold achieved roofline efficiency

An independent cross-check that does not use a transfer factor. M4 achieved efficiency
against this host's ~8.0 TFLOP/s BF16 ceiling:

| family | GFLOP | M4 ms | TFLOP/s | % of M4 peak |
| --- | ---: | ---: | ---: | ---: |
| steel_gemm_bf16, all | 1502.7 | 214.698 | 7.00 | 87.5 |
| — regular path only | 1309.9 | 182.988 | 7.16 | 89.5 |
| — split-K path only | 192.8 | 35.584 | 5.42 | 67.7 |
| attention_core | 161.4 | 27.630 | 5.84 | 73.0 |
| nvfp4_dense_qmm | 125.6 | 19.648 | 6.39 | 79.9 |

Holding those efficiencies against the M5 ~60 TFLOP/s ceiling:
steel_gemm_bf16 **28.6 ms**, attention_core **3.68**, nvfp4_dense_qmm **2.62**,
HOST-IDENTICAL glue 8.34, gather GEMM 43.262 (measured) ⇒ **Σ = 86.50 ms**.

**Measured `S` is 97.895 ⇒ 11.40 ms of M5-specific loss (11.6 % of `S`, 20.9 % of `R`)
that has no M4 counterpart.** Projection A absorbs this loss into the transfer factor;
Projection B exposes it. Both are reported because the difference *is* the finding.

### 4.4 Where the 11.40 ms most plausibly lives

The tiny-N GEMM tail identified in §3.4. On M5, `g_proj` (39 × 16 TGs), the router GEMM
(38 × 64 TGs) and `wk`/`wv` (78 × 64 TGs) are **155 of the 237 BF16 GEMM dispatches while
carrying only 192.8 GFLOP = 12.8 % of the family's work**. At Projection B's assumed 87.5 %
efficiency they would cost 3.7 ms; at a more plausible 15 % of roofline for a 64-TG launch
on 40 cores they cost 21.4 ms — a **+17.7 ms** swing that comfortably brackets 11.40.

No other candidate brackets it: the command-buffer boundary is O(2.1 ms) (§1.4), and the
glue class is already at its byte floor (§5.2).

---

## 5. Headroom

### 5.1 Per-family floors and headroom

M5 per-family roofline floors at 546.2 GB/s from `PREFILL_NAX_ANALYSIS.md` §6.2.
`steel_gemm_bf16`'s floor is `attn_proj_qkvo` 24.42 (compute-bound) + `dense_mlp_layer0`
0.86 + router GEMM 0.35 = **25.63**.

| family | [PROJ] M5 ms | floor ms | headroom ms | **% score if fully recovered** | ≥ 3σ (1.35 ms)? |
| --- | ---: | ---: | ---: | ---: | :-: |
| **steel_gemm_bf16** | 37.93 | 25.63 | **12.30** | **4.61 %** | **yes** |
| attention_core | 4.88 | 2.69 | **2.19** | **0.82 %** | **yes** |
| nvfp4_dense_qmm | 3.47 | 2.09 | **1.38** | **0.52 %** | marginal |
| HOST-IDENTICAL glue, as a class | 8.04 | 7.94 | **≈ 0.10** | 0.04 % | no |
| lm_head | 0.31 | 0.75 | −0.44 | — | — |
| **total above floor in `R`** | | | **≈ 15.9** | **≈ 5.95 %** | |

For reference, the same subtraction against the pure analytic floor total
(Σ floors = 70.07 ms at 546.2 GB/s) gives `97.895 − 70.07 = ` **27.83 ms**, independently
reproducing the honest central value 27.88 from §1.3 and decomposing it into
**16.4 ms of ordinary kernel inefficiency already visible on M4 + 11.40 ms of
M5-specific loss**.

### 5.2 The glue class is already at its DRAM floor — an important negative

Summing bound bytes for the HOST-IDENTICAL families from the SPLIT=1 trace:
elementwise ≈ 1.60 GB, sort/scatter (in-forward) 0.687, moe_tail 0.837,
qk_norm_rope 0.730, rms_norm 0.472, router tournament 0.011 ⇒ **4.34 GB**.
At 546.2 GB/s that is a **7.94 ms** floor against **8.04 ms** projected.

**The entire HOST-IDENTICAL glue class runs at ~99 % of its bandwidth floor.**
There is no scheduling, occupancy or dispatch-overhead win available in it. The only
lever is *removing bytes* — epilogue fusion — and even a perfect fusion of the largest
component (elementwise, 1.6 GB of pure activation round-trips) is worth ~2.9 ms, which
would need to be delivered as a single bundled change to clear 3σ.

This retires the "non-GEMM glue ~9–12 ms" open item in `PREFILL_NAX_ANALYSIS.md` §H4 as
a *time* target and reframes it as a *bytes* target.

### 5.3 Measurability verdict

At σ_Δ = 0.4497 ms, exactly **three** families in `R` can host a single-run-detectable
experiment: `steel_gemm_bf16` (12.30 ms of headroom), `attention_core` (2.19),
and marginally `nvfp4_dense_qmm` (1.38). `steel_gemm_bf16` alone holds **77 %** of all
above-floor time in `R`. Everything else is below the detection floor individually and
can only be tested as a bundle.

---

## 6. Host-divergence flags

Gate: `device.cpp:1021-1039`; exactly **9** `is_nax_available()` call sites, verified
exhaustive. `MLX_METAL_NO_NAX` exists only on the CMake metallib path
(`kernels/CMakeLists.txt:161-163,176`) and is never reachable through SwiftPM, so
NAX cannot be forced off or on for a local A/B.

| family | flag | detail |
| --- | --- | --- |
| routed_gather_gemm | **HOST-DIVERGENT, different algorithm — NOT MEASURABLE HERE** | `quantized.cpp:2098`; local `nvfp4_gather_qmm_rhs_nt_…bm16_bn32_bk32` vs ranked `…gather_qmm_rhs_nax_…` (`:1653`), whose run/segment machinery is unreachable on gen 16 |
| steel_gemm_bf16 | **HOST-DIVERGENT, different route and tile** | §3.4: `wk`/`wv` flip split-K→regular, `wo`/dense-down flip regular→split-K; NAX tile bm64 bn128 wm2 wn4 group 256 vs local bm64 bn64 wm2 wn2 group 128 |
| attention_core (full layers) | **HOST-DIVERGENT — NOT MEASURABLE HERE** | `scaled_dot_product_attention.cpp:177`; ranked `sdpa_full_self_attention_nax` bq64 bk32 wm4 wn1, grid (8,H,1); local bq32 bk16, grid (16,H,1). Ranked tgMem is not obtainable on this host. |
| dense_mlp_layer0 down | HOST-DIVERGENT, different algorithm | `matmul.cpp:965` vs `:987-991` |
| dense_mlp_layer0 gate/up | HOST-DIVERGENT, name/tile only | `matmul.cpp:1024-1026` vs `:1052` |
| nvfp4_dense_qmm (shared expert) | HOST-DIVERGENT, name/tile only | `quantized.cpp:733`; caveat `nvfp4_qmm_t_nax_static_` (`:507-518`) is NAX-only with no gen-16 counterpart |
| Swift-visible SwiGLU layout | HOST-DIVERGENT | `LagunaRuntimeModel.swift:9821` takes a contiguous-prefix slice on M5 vs `lagunaInterleavedSwiGLU` locally |
| router GEMM, `g_proj` | **HOST-IDENTICAL** | both land on the non-NAX-gated `qmm_splitk` |
| lm_head | **HOST-IDENTICAL** | M = 1 at `:10958` |
| qk_norm_rope, rms_norm, moe_tail, router tournament, sort/scatter/gather, all elementwise, reduce, softmax, arange, arg_reduce | **HOST-IDENTICAL** | all 52 custom Laguna `MLXFast.metalKernel` kernels plus the stock MLX elementwise/reduce set |

Corrected form of the "94.2 % NAX-divergent" claim (§1.2): by **Projection A M5
milliseconds**, HOST-DIVERGENT families are `W` 43.262 + steel_gemm_bf16 37.93 +
attention_core 4.88 + nvfp4_dense_qmm 3.47 = 89.54 ms = **91.5 % of `S`**;
HOST-IDENTICAL is 8.34 ms = **8.5 %**. By **dispatch count** it is 624 of 1146 = 54.5 %.
Neither is 94.2 %, and the 94.2 % figure's denominator was M4 wall time.

Standing caveats: the M5 arch suffix `'s'` is *inferred* from the gen-18 `'p'` rule; all
per-shape M5 routing verdicts are read from predicates, not measured; no local timing can
validate any `_nax` edit; the M5 Max core count is not verifiable from this checkout.

---

## 7. Ranked follow-ups

### F1 — Fuse the attention input projections. Top priority, two steps.

**The finding.** `Sources/MLXFastModel/LagunaRuntimeModel.swift:108-114`:

```swift
lagunaFusedQKVEnabled = env["DARKBLOOM_FUSED_QKV"] == "1"   // default OFF
// "Ablation on the paired local benchmark showed a mild prefill cost with
//  no decode gain, so this ships opt-in."
```

`prepareFusedQKVWeight()` (`:5590-5610`) guards three bias-free `Linear`s of identical
dtype/width and returns `concatenated([wq.weight, wk.weight, wv.weight], axis: 0)`.
The use site (`:5881-5895`) is **prefill-only** (`_fusedQKVWeight != nil && L > 1`):
one `matmul(normalizedInput, fusedQKVWeight.T)` followed by three slices, documented
bit-exact. Registered at `prepareFusedRuntimeWeights()` `:11027`.

**Why the ablation that turned it off does not transfer.** Check the fused shape against
both predicates. M = 512, N = 10240, K = 2048:

- M4 Case 1: `_tm·_tn = 32·640 = 20480 > 2048` **and** `K = 2048 < 10240` ⇒ **regular**.
  So on M4, fusing *destroys* the split-K parallelism that `wk`/`wv` were getting
  (2 × 1024 TGs at parts=2 → folded into one regular launch). On a 20-core host that
  loses real parallelism — which is exactly the "mild prefill cost" that was measured.
- M5 Case 2: `K = 2048 ≥ 3·10240`? no. `max ≤ 1024`? no. ⇒ **regular**.
  But `wk`/`wv` were **already regular on M5** (§3.4, they fail Case 2 on the exact tie
  `2048 > 2048`), at **64 threadgroups each**. There is no split-K parallelism to lose.
  Fusing turns 3 launches of (512 + 64 + 64) = 640 TGs into **one launch of
  (80,8,1) = 640 TGs** — same total work, one well-shaped dispatch instead of two
  1.6-TG-per-core stragglers.

**The M4 null is an artefact of a routing decision that inverts on M5.** This is the
single clearest M4→M5 transfer trap found in this census.

**Step 0 — zero code.** Set `DARKBLOOM_FUSED_QKV=1` for one ranked paired prefill.
Removes 78 dispatches per prefill.
Prediction: **−0.5 to −4.0 ms, central −1.6 ms = +0.60 % score**, σ_Δ = 0.45 ⇒ ≈ 3.6σ.
Band rationale: `wk`/`wv` carry 167.5 GFLOP = 11.1 % of BF16 GEMM work. At par
efficiency they cost 4.2 ms and the only saving is 78 dispatch overheads (≈ 0.5 ms);
at half par they cost 8.4 ms and the saving is up to 4.2 ms.

**Step 1 — 4-way bank.** Extend `prepareFusedQKVWeight()` to `[Wq;Wk;Wv;Wg]` when
`gatePerHead && gProj != nil`. This is already precedented in-file:
`prepareLastPrefillProjectionWeights()` (`:5612+`) builds
`_lastPrefillQGateWeight = concat(wq, gProj)` and `_lastPrefillKVWeight` for the final
sliding layer — and that `[K;V]` bank **is** the lone N=2048 K=2048 regular GEMM found in
§3.2. So `g_proj` provably shares `wq`'s input and a 4-way bank is exact.
Fused N = 8192+1024+1024+64 = 10304 ⇒ (81,8,1) = 648 TGs, still regular under Case 2.
Collapses 156 M5 kernels (wq + wk + wv + `g_proj` split-K + accum) into 39, and removes
39 launches at **0.4 TG/core**.
Prediction: **an additional −0.3 to −1.5 ms**; F1 total central **−2.2 ms = +0.82 % score**.

Cost: ~60 lines in `LagunaRuntimeModel.swift` (per-file headroom is 55 952 B, ample).
Gates: `research/run_upstream_equivalence.sh` + the 64-step drift tripwire; slices must be
re-offset. Avoid the region fences at 5700–5800.

Risk to state up front: this is a *dispatch-shape* hypothesis validated by predicate
reading, not by timing. It **cannot** be falsified on this host — running it on M4 would
re-measure the original null for the original reason.

### F2 — HOST-IDENTICAL glue: a class verdict, not an experiment arm.

Do **not** assign a single glue-kernel optimisation. §5.2 shows the class runs at ~99 % of
its DRAM floor: 8.04 ms projected against a 7.94 ms floor over 4.34 GB. No individual
family (largest: elementwise 2.21 ms, qk_norm_rope 1.97) has detectable headroom, and
scheduling/occupancy changes cannot help a family that is already bandwidth-saturated.

The only viable form is **byte elimination via epilogue fusion, bundled to clear 3σ**.
Ranked by bytes removable: elementwise activation round-trips 1.60 GB (≈ 2.9 ms),
moe_tail 0.837 GB (≈ 1.5 ms), qk_norm_rope 0.730 GB (≈ 1.3 ms). A bundle reaching
≥ 1.35 ms of removed traffic is testable; anything smaller is not.

### F3 — `lagunaPrefillQKHeadsPerGroup = 4`. Cheap free-rider, sign uncertain.

The 4-head kernel twins already exist and are unused (`:2337`, `:2511`). Switching
collapses sliding 36 864 → 9 216 TGs/layer (×30) and full 28 672 → 7 168 (×10):
**1.39 M → 0.35 M threadgroup launches per prefill**. But §5.1 gives qk_norm_rope only
0.20 ms above floor, so the band is −0.1 to −0.8 ms with uncertain sign. Worth running
only bundled with F1 or F2 as a free rider. Needs its own equivalence check (separate
compiled kernel).

### F4 — Note only: `wo` migrates *into* NAX split-K on M5.

§3.4: `wo` (39) and dense down (1) satisfy Case 2 on M5 but not Case 1 on M4. That adds
40 accum passes and ~654 MB of FP32 round-trip ≈ **1.20 ms = 0.45 %**. Sign is genuinely
uncertain because split-K simultaneously raises occupancy from 256 to ~4096 TGs. Record
it; do not assign it ahead of F1.

---

## 8. What this census closes

- **38 vs 39 MoE layers** (`CURRENT_RESEARCH_STATE.md:346`): resolved — 38 sorted-path
  layers, layer 39 terminal-fusion. `W` prices 38 routed blocks.
- **`g_proj` split-K `parts`**: 4, not 2.
- **The layer-39 `[K;V]` bank**: identified as the lone M=512 N=2048 K=2048 regular GEMM.
- **`PREFILL_NAX_ANALYSIS.md` §H4 "non-GEMM glue ~9–12 ms"**: retired as a time target
  (projected 8.04 ms, floor 7.94 ms), reframed as a bytes target.
- **`PREFILL_NAX_ANALYSIS.md` §H3 "BF16 projection fragmentation 24.42 ms"**: F1 is now a
  concrete, source-grounded mechanism for it with a named default-OFF flag.
- **The 31.28 ms unattributed pool**: reproduced at 27.83 ms and decomposed into 16.4 ms
  of M4-visible kernel inefficiency + 11.40 ms of M5-specific loss localised to the
  tiny-N GEMM tail.

## 9. Reproduction

```bash
git checkout maple-tanjiro/nonmoe-prefill-census
git show 2d5af1a --stat          # LOCAL-ONLY GPUPROF hook (device.cpp/.h)
git show b0096e3 --stat          # LOCAL-ONLY non-NAX steel trace (matmul.cpp)
CLANG_MODULE_CACHE_PATH="$PWD/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved
bash research/tanjiro_prefill_census.sh   # -> pr270-logs/split{0,1}.worker.err
bash research/tanjiro_steel_trace.sh      # -> pr270-logs/steeltrace.worker.err
python3 research/prefill_budget.py --tokens 512
```

Both LOCAL-ONLY commits are reverted on this branch before submission; the reverting
commit restores `Vendor/mlx-swift/…/metal/{device.cpp,device.h,matmul.cpp}` byte-for-byte
so the `VendoredMetalFingerprint` hash is intact. Re-apply them only to re-measure.
