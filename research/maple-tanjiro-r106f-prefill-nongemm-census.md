# R106-F — Prefill non-GEMM census

**60.88 % of the 512-token prefill is NOT in `steel_gemm*`. That headline is a
trap: 52.05 pp of it is other matmul (routed gather-GEMM + NVFP4 dense QMM) and
5.13 pp is the attention core, which is also MMA work. True non-matmul glue is
3.18 % of prefill (17.463 ms of 548.386 ms on M4 Pro), and 14 % of even that
does not exist on the ranked M5.**

Verdict: **N-GEMM-DOMINATES**.

- Student: `maple-tanjiro` · PR #620 · assignment `maple-r106-f-prefill-nongemm-census` / `r106-f-rev1`
- Base: `9d424c167eae0a98e4c8c03e57be2f937ae0744a`
- Host: Apple **M4 Pro**, 14 CPU, 48 GiB. Apple GPU **generation 16 ⇒ `nax_available = false`**. macOS 26.5.2.
- Receipts consumed: **zero** (hard constraint honoured; `senpai/submit-official.sh` never invoked).
- W&B: [`nyvwbvb1`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/nyvwbvb1)
  (`wandb-applied-ai-team/mlxfast-maple`, state `finished`) — carries the full
  family table, the non-GEMM triage table, and every summary number below.
  Published by `research/r106f_wandb_log.py`.
- Candidate probes run: **zero of the one allowed** — the census answered the
  question without needing it, so the allowance is returned unspent.

---

## 1. Headline partition

| partition | ms | % of prefill |
|---|---|---|
| `steel_gemm*` (dense BF16 GEMM incl. split-K) | 214.513 | **39.12 %** |
| **everything else** | **333.873** | **60.88 %** |

Decomposition of that 60.88 %:

| component | ms | % of prefill | is it matmul? |
|---|---|---|---|
| routed gather-GEMM + NVFP4 dense QMM | 285.438 | 52.05 % | yes |
| attention core (`steel_attention` + `sdpa_vector`) | 28.133 | 5.13 % | yes (MMA) |
| **true non-matmul glue** | **17.463** | **3.18 %** | no |
| GPU-idle (unattributed) | 2.839 | 0.52 % | — |
| sum | 333.873 | 60.88 % | |

Rolled up:

- matmul (3 families) = 499.951 ms = **91.17 %**
- matmul + attention = 528.084 ms = **96.30 %**
- non-MMA glue + idle = 20.302 ms = **3.70 %**

The "non-GEMM" framing inflates the addressable surface by **19×** (60.88 % vs
3.18 %). Anyone quoting a non-GEMM share without naming which matmul kernels
they excluded is quoting a number that cannot be optimised.

---

## 2. Complete time-attributed inventory (sums to 100 %)

M4 Pro, one 512-token prefill, 8 reps with rep 0 discarded, warm median
per-rep **548.428 ms**, attribution wall **548.386 ms = 100.0 %**.
Greedy token **5991** identical in every rep. 1066 command buffers, 1222
dispatches per request. Peak RAM 20.715 GB.

`fair ms` is the overlap-corrected share (a dispatch that shares a bracket with
others is charged its concurrency-weighted slice); `excl ms` is time when the
family was the only one in flight; `concur` is the mean overlap factor.

| family | fair ms | %wall | excl ms | raw ms | concur | GB bound | GB/s | % of 260.2 |
|---|---|---|---|---|---|---|---|---|
| routed_gather_gemm | 265.440 | 48.4 | 265.440 | 265.440 | 1.00 | 18.968 | 71.5 | 27 |
| steel_gemm_bf16 | 214.513 | 39.1 | 212.256 | 218.628 | 1.02 | 4.552 | 21.2 | 8 |
| attention_core | 28.133 | 5.1 | 28.133 | 28.133 | 1.00 | 0.696 | 24.7 | 10 |
| nvfp4_dense_qmm | 19.998 | 3.6 | 19.998 | 19.998 | 1.00 | 0.652 | 32.6 | 13 |
| elementwise | 4.710 | 0.9 | 4.698 | 4.721 | 1.00 | 1.632 | 346.5 | 133 |
| qk_norm_rope | 4.194 | 0.8 | 4.191 | 4.197 | 1.00 | 0.768 | 183.1 | 70 |
| sort_scatter | 2.633 | 0.5 | 2.633 | 2.633 | 1.00 | 1.134 | 430.7 | 166 |
| moe_tail | 2.539 | 0.5 | 2.539 | 2.539 | 1.00 | 0.878 | 345.8 | 133 |
| rms_norm | 1.714 | 0.3 | 1.714 | 1.735 | 1.01 | 0.497 | 290.0 | 111 |
| router | 0.673 | 0.1 | 0.673 | 0.673 | 1.00 | 0.012 | 17.8 | 7 |
| lm_head | 0.667 | 0.1 | 0.667 | 0.667 | 1.00 | 0.959 | 1437.8 | 553 |
| other | 0.311 | 0.1 | 0.311 | 0.311 | 1.00 | 0.211 | 678.5 | 261 |
| MIXED (unsplittable brackets) | 0.022 | 0.0 | 0.022 | 0.000 | — | 0.000 | — | — |
| **GPU-idle (unattributed)** | **2.839** | **0.5** | | | | | | |
| **TOTAL** | **548.386** | **100.0** | | | | 28.834 GiB | | |

**The unattributed share is named explicitly: `GPU-idle (unattributed)` =
2.839 ms = 0.52 % of prefill.** It is the wall time in which no GPU bracket was
open — encode, commit, and completion-handler latency between command buffers.
Family sum 545.547 + 2.839 = 548.386 ✓. There is no residual "other kernels"
bucket hiding behind the total: `other` is itemised above at 0.311 ms.

### 2.1 Instrument validation, and one 57 ms lie the raw trace tells

Raw bracket sums come to **606.733 ms = 110.6 % of wall** — a 10.6 %
over-count. The union of brackets is **545.559 ms = 99.5 %**. The gap is one
family:

> `arangeuint32`: 76 calls × 750.8 µs = **57.057 ms (10.4 % of prefill)** while
> binding **0.016 MB**, at grid `th 4096 1 1 / 1024 1 1`.

A 16 KB kernel cannot occupy 10 % of a prefill. Its command buffers are
**99.98 % covered** by concurrently-executing GEMM buffers: the timestamps
measure the enclosing command buffer's residency, not the kernel's work. Its
true exclusive cost is ~0 ms. Offline re-adjudication dropping those 532
fully-covered buffers gives busy-sum **549.676 ms = 100.2 % of wall** against
union **545.547 ms** (essentially unchanged), which establishes that **prefill
is strictly serial on this GPU** and that the remaining attribution is sound.
`sort_scatter` collapses from an inflated figure to 78 calls / 2.633 ms,
reconciling with the independent earlier census (78 calls / 2.598 ms).

The offline replay reproduced the in-process numbers **exactly** (wall 548.386,
busy-sum 606.733, union 545.559, every family row identical), so the
adjudication is a transformation of the trace, not a re-measurement.

Two instrument controls worth recording:

- **`SPLIT=0` alone is unusable for attribution.** Shipped batching puts 1156
  of 1222 dispatches into a single `MIXED` bracket and mis-attributes families
  by up to **7.6×**. `SPLIT=1` (one command buffer per dispatch group) is what
  makes the table above possible.
- **`SPLIT=1` costs 0.24 % of wall** (547.055 ms → 548.386 ms). Never compare
  walls across `SPLIT` settings. The honest wall is the `SPLIT=0` figure, whose
  busy union is 542.127 ms = 99.1 %, i.e. GPU-idle 4.93 ms = 0.9 % — slightly
  more idle than `SPLIT=1`, as expected from fewer, larger buffers.

---

## 3. Roofline placement (Rule 77: measured bytes, derived FLOPs, real geometry)

### 3.1 Host constants — and a correction that flips a standing conclusion

| constant | value | provenance |
|---|---|---|
| M4 Pro BF16 SIMD MMA peak | **8.0 TFLOP/s** | 20 cores × 256 FLOP/clk × ~1.56 GHz = 7.94–8.19; cross-checked by the measured same-shape M4→M5 GEMM ratio (7.43 → 56 TFLOP/s = 7.54×, ⇒ 7.96 against the 60 reference) |
| M4 Pro DRAM peak | **260.2 GB/s** | Rule-80 bandwidth probe |
| machine balance | **30.7 FLOP/B** | 8.0e3 / 260.2 |

**`research/host_flop_ceiling.swift` reports 28.76 TFLOP/s and that number is
wrong.** Its FLOP arithmetic is correct (128 FLOP/thread/loop = 4 MMAs ×
8·8·8 × 2 ÷ 32 lanes, `:161`, `:179-185`; consistent 2-FLOP/FMA convention
`:174`; DCE guarded `:86-90`, `:43`, `:162`) — but `:101-110` feeds all four
`simdgroup_multiply_accumulate` calls **an identical compile-time-constant
A·B**. CSE/const-folding executes roughly one MMA while the host charges four.
28.76 / 4 = 7.19, which is bracketed by the probe's own scalar measurements of
7.07 and 7.59.

Corroborating checks:

- 28.76 TFLOP/s would demand ~928 FLOP/core/clk, which is the **NAX matrix
  rate**, physically unavailable on a `generation = 16, nax_available = false`
  host. The in-repo A19 calibration separates 257.5 (SIMD) from 1027 (NAX)
  FLOP/core/clk (`RESEARCH_ARCHIVE_through-round-91.md:2226-2244`).
- "Rule 80" is **bandwidth-only** (`research/CURRENT_RESEARCH_STATE.md:2085-2087`,
  `:3718-3722`) and carries **no TFLOP constant**. The 8.0 figure was never
  measured either: it enters the repo as an estimate at
  `research/maple-fern-prefill-roofline.md:68`, and
  `research/prefill_budget.py:32-33` falsely credits the probe for it (both
  landed in the same commit `3e8e4352`). The 60.0 figure is an explicit working
  assumption (`research/RESEARCH_IDEAS_steel-gemm-prefill.md:11`).
- Reductio: `steel_ms_attribution.py:165, :285-286` projects
  `m5_ms = m4_ms × M4_peak / 60`. At 28.76 the steel subset alone would project
  102.9 ms against a **measured whole-prefill of 97.895 ms**.

Consequences to publish loudly:

1. The 8.0 roof **restores the "H8 dead" verdict**: `steel_gemm` runs at 87.6 %
   of peak. It survives only for `M4_peak ≤ 8.08`
   (`advisor-r104-the-receipt-is-the-instrument.md:1373-1376`), so this is a
   genuinely tight call that the 28.76 figure had spuriously reopened.
2. It **removes the "attention has large headroom" reading** that a 28.76 roof
   would have implied (attention would have looked like 19 % of peak instead of
   70 %).
3. **Caveat:** the M4 clock is unmeasured. At 1.8 GHz the roof is ~9.2, which
   deflates every "% of peak" here by ~13 %. Cheapest test to retire the doubt
   (not run — it costs a build, and no conclusion below turns on it): give the
   probe four distinct runtime-sourced A_k/B_k pairs, or `xcrun metal -S` and
   count MMA opcodes.

### 3.2 MMA families

FLOPs are derived from model dims **and pinned by the trace's own dispatch
multiplicities**, not by an assumed layer count. Layer 39 is diverted to
`callLastPrefillRow` (`LagunaRuntimeModel.swift:11679-11681`), so only **38 MoE
layers** and **39 attention layers** run at full length — confirmed by 76 =
38 × 2 gather dispatches and 39 `steel_attention` + 1 `sdpa_vector`. (Prior art
quoting 1005.0 GFLOP for gather-GEMM assumed 39 MoE layers; the difference is
exactly one layer, 25.8 GFLOP.)

| family | GFLOP | TFLOP/s | % of 8.0 | AI (FLOP/B) | bound | floor | headroom |
|---|---|---|---|---|---|---|---|
| routed_gather_gemm | 979.3 | 3.69 | **46.1 %** | 51.6 | compute | 122.41 ms | **143.03 ms** |
| steel_gemm_bf16 | 1502.8 | 7.01 | **87.6 %** | 330.1 | compute | 187.85 ms | 26.66 ms |
| steel_gemm_bf16 (alt. 1465.3, incons. E) | 1465.3 | 6.83 | 85.4 % | 321.9 | compute | 183.16 ms | 31.35 ms |
| nvfp4_dense_qmm | 122.4 | 6.12 | 76.5 % | 187.7 | compute | 15.30 ms | 4.70 ms |
| attention_core | 156.8 | 5.57 | **69.7 %** | 225.2 | compute | 19.60 ms | 8.54 ms |

Every MMA family has arithmetic intensity far above the 30.7 FLOP/B machine
balance, so all four are **compute-bound**; their measured GB/s (8–27 % of DRAM
roof) is irrelevant to their ceiling.

Attention's 156.8 GFLOP **already includes causal halving** (39 layers × 2·L²/2·D
per head × 2 products, 10 layers at 48 q-heads and 29 at 64). This matters: the
often-quoted "19.9 % of peak" for prefill attention uses the un-halved
denominator and is a factor-of-2 artefact.

Trace-bound 18.968 GB for gather-GEMM against an analytic 19.465 GB is a 2.6 %
agreement, which is the best available cross-check that the byte accounting is
sound. **Caveat throughout: *bound* ≠ *read*** — see §3.4.

### 3.3 Glue families against the DRAM roof

Floor = bound bytes / 260.2 GB/s.

| family | GB | ms | GB/s | % of roof | floor | headroom |
|---|---|---|---|---|---|---|
| elementwise | 1.632 | 4.710 | 346.5 | **133 %** | 6.27 ms | 0.00 |
| qk_norm_rope | 0.768 | 4.194 | 183.1 | **70 %** | 2.95 ms | **1.24 ms** |
| sort_scatter | 1.134 | 2.633 | 430.7 | **166 %** | 4.36 ms | 0.00 |
| moe_tail | 0.878 | 2.539 | 345.8 | **133 %** | 3.37 ms | 0.00 |
| rms_norm | 0.497 | 1.714 | 290.0 | **111 %** | 1.91 ms | 0.00 |
| router | 0.012 | 0.673 | 17.8 | 7 % | 0.05 ms | (1.24→see below) |
| lm_head | 0.959 | 0.667 | 1437.8 | **553 %** | 3.69 ms | 0.00 |
| other | 0.211 | 0.311 | 678.5 | **261 %** | 0.81 ms | 0.00 |

Six of eight glue families run **at or above 100 % of the DRAM roof** — they
are cache-resident, so the roofline gives them **zero** distance to travel.
That leaves exactly two families with any nominal distance, and one of them is
a category error:

- **`router` is not DRAM-bounded.** It binds 12 MB across 39 tournament-select
  dispatches. Its roof is occupancy and selection latency, not bandwidth;
  charging it 0.63 ms of "DRAM headroom" is meaningless. 17 µs/call for a
  512 × 256 top-8 tournament is already tight.
- **`qk_norm_rope` holds the entire DRAM-addressable headroom: 1.24 ms**, at
  70 % of roof — and it is not a streaming kernel. It performs two RMS
  reductions plus RoPE, so 70 % is close to its practical ceiling.

**The decisive number.** Driving the *entire* glue surface to 100 % of the DRAM
roof — physically impossible — is worth:

| framing | M4 | M5 (bandwidth-scaled ÷2.10) | % of M5 prefill | % of score |
|---|---|---|---|---|
| nominal (incl. the router category error) | 1.87 ms | 0.89 ms | 0.91 % | 0.231–0.337 % |
| **DRAM-addressable (qk_norm_rope only)** | **1.24 ms** | **0.59 ms** | **0.60 %** | **0.153–0.224 %** |
| bar for +0.2 % of score | | 0.53–0.77 ms | 0.54–0.79 % | 0.2 % |

The honest ceiling on glue *tuning* is **0.59 ms of M5 prefill, straddling the
bar**, for a perfect-roof outcome on a reduction kernel. Glue tuning is dead.

### 3.4 Two byte-model corrections

1. **`qk_norm_rope`'s bound bytes overstate its traffic.** The full 4096-row
   RoPE angle atlas is bound as an input (`lagunaRoPEAngleAtlasLength = 4096`,
   `LagunaRuntimeModel.swift:806`), but the kernel indexes only
   `angles + (offsets[0] + t) * 2 * rotary_pairs` — 512 of 4096 rows. About
   1.75 MiB per sliding call and 0.875 MiB per full call is never touched. Do
   not chase "atlas bytes": the ~113 µs sliding cost is compute over q/k. This
   *reduces* the floor and so slightly *increases* the nominal headroom above,
   which is why I report the headroom as an upper bound.
2. **Generic-kernel byte model, established by reconciliation.** For
   `g2_*`/compiled elementwise kernels the traced MiB is **2 × output bytes**
   (stride-0 broadcast operands excluded); for custom kernels it is the **sum of
   all bound buffers**. All five glue families reconcile to three decimals
   under that model, which is what pins the source identifications in §5.

### 3.5 Dispatch geometry (Rule 77)

281 distinct `(kernel, grid, threadgroup)` shapes were captured. The
load-bearing ones:

| kernel | grid | threadgroup |
|---|---|---|
| `steel_attention_bfloat16_bq32_bk16_bd128_wm4_wn1_maskbfloat16_align_Q_t…` | `tg 16 48 1` / `tg 16 64 1` | `32 4 1` |
| `nvfp4_gather_qmm_rhs_nt_bfloat16_t_gs_16_b_4_bm_16_bn_32_bk_32_wm_1_wn_2_align_M_t_align_N_t_align_K_t` | `tg 32 256 1`, `tg 64 256 1` | `32 2 1` |
| `steel_gemm_fused_nt_…bm64_bn64_bk16_wm2_wn2…` | `tg 96 8 1`, `tg 32 8 1`, `tg 128 8 1` | `32 2 2` |
| `steel_gemm_splitk_nt_…bm32_bn32_bk16_wm2_wn2_MN_taligned_K_taligned` | `tg 32 16 2`, `tg 2 16 4`, `tg 8 16 2` | `32 2 2` |
| `steel_gemm_splitk_accum_bfloat16_float32` | `th 1024 512 1`, `th 256 512 1`, `th 64 512 1`, `th 48 512 1` | `32 32 1` |
| `nvfp4_qmm_t_splitk_fused_bfloat16_t_gs_16_b_4_alN_true` | `tg 16 16 1` | `32 2 2` |
| `arangeuint32` | `th 4096 1 1` | `1024 1 1` |

Attention geometry decodes cleanly: `NQ = 512/32 = 16`, `H = 48` (full layers)
or `64` (sliding), `B = 1`, 128 threads/TG — the classic M4 `bq32_bk16` tiling
for `bd=128` (`steel_attention.cpp:193-198`), not the M5 `_nax`
`bq64_bk32`/TG(32,4,1) shape.

### 3.6 ⚠️ The census ran a different gather kernel than the ranked M5 does

`nvfp4_gather_qmm_rhs_nt_…_bm_16_bn_32_bk_32_wm_1_wn_2` is the **non-aligned**
route (`quantized.cpp:1529`, `if (!expert_aligned)`). On the ranked M5,
`expert_aligned` is **true** and the kernel is the `bm 64 / wm 4` route with a
register-local SwiGLU epilogue.

The gate is `lagunaExpertAlignedGatherEnabled`
(`LagunaRuntimeModel.swift:253-267`): `DARKBLOOM_EXPERT_ALIGNED_GATHER != 0`,
`DARKBLOOM_STAGE_BM128 ∈ {"",4,5}`, **macOS ≥ 26.2**, and
`lagunaNAXAvailable` ⇒ GPU generation ≥ 17. This host is macOS 26.5.2 (passes)
but **generation 16 (fails)**. Verified two independent ways: by reading the
gate, and by the observed kernel name being the `!expert_aligned` variant.

This is a first-order M4→M5 non-transfer and it cuts **against** the non-GEMM
case, because the fused epilogue on the aligned route already deletes glue that
this trace still pays for — see §4.

---

## 4. Rule 90 — editability, and the M4-only artefact correction

### 4.1 Editability per family

`benchmark.json` lists 97 `editablePaths`. Mapping every family:

| family | implementation | Rule 90 |
|---|---|---|
| routed_gather_gemm | `quantized.cpp`, `kernels/fp_quantized{,_nax}.{h,metal}`, `mlx-generated/fp_quantized{,_nax}.cpp` | ✅ **live** |
| steel_gemm_bf16 | `kernels/steel/gemm` (dir), `mlx-generated/steel_gemm_{fused,splitk,gather}{,_nax}.cpp` | ✅ **live** |
| attention_core | `kernels/steel/attn` (dir, 104,529 B), `mlx-generated/steel_attention{,_nax}.cpp`, `jit_kernels.cpp` | ✅ **live** (⛔ but `backend/metal/scaled_dot_product_attention.cpp`, which holds the `_nax` tile constants, is **not** editable) |
| nvfp4_dense_qmm | as gather-GEMM | ✅ **live** |
| elementwise | `kernels/{copy,binary,unary,ternary}.{h,metal}` + generated twins; **call sites** in `Sources/MLXFastModel/` and `Vendor/mlx-swift-lm/…/SwitchLayers.swift` | ✅ **live** (⛔ the JIT `compiled*` fuser itself is not listed — fix at the Swift call site, not in the fuser) |
| qk_norm_rope | `Sources/MLXFastModel/LagunaRuntimeModel.swift` | ✅ **live** |
| sort_scatter | `Sources/MLXFastModel/` + `kernels/sort.{h,metal}` | ✅ **live** |
| moe_tail | `Sources/MLXFastModel/` | ✅ **live** |
| rms_norm | `Sources/MLXFastModel/` + `kernels/rms_norm.metal`, `kernels/reduce*` | ✅ **live** |
| router | `Sources/MLXFastModel/` | ✅ **live** |
| lm_head | `Sources/MLXFastModel/` | ✅ **live** |
| `arangeuint32` | not in `editablePaths` | ⛔ **dead on arrival** (moot: ~0 ms exclusive) |

**Editability kills nothing here.** Every glue family is editable, and the whole
`Sources/MLXFastModel` and `Sources/MLXFastTransform` trees plus
`SwitchLayers.swift` are in scope. The constraint that kills the non-GEMM case
is physics (§3.3), not the submission surface. That is worth stating plainly,
because a "dead on arrival" finding would have been a much weaker result.

### 4.2 The prefill glue surface is *unfused*, and part of it is M4-only

The decode path is comprehensively fused; the prefill path is not. Every
`laguna*fused*` epilogue is gated on `dims(1,1,hidden)` / `L == 1`:
`5897`, `6096-6104`, `6330-6337`, `6439`, `6457-6459`, `9026`, `9093`,
`9133-9138`, `10812`, `10835`, `10920`, `11175`. The prefill-live fused kernels
are only `laguna_prefill_{sliding,full}_qk_norm_*`, `laguna_residual_rms_*`,
`laguna_prefill_{sorted_,}moe_tail_*`, and `laguna_prefill_router_*`.

That asymmetry is why glue exists at all at 512 rows — and it is also why the
naive projection of glue to M5 is wrong. Glue scales with bandwidth (~2.10×),
not with the ~5.6× overall prefill speedup, so **the glue share roughly doubles
on M5**. But two glue items in this trace are **M4-only**, because the aligned
gather route's register-local SwiGLU epilogue
(`fp_quantized_nax.h:1942-1975`, `fuse_swiglu` when `kernel_N == 1024 &&
kernel_K == 2048`, reached via `quantized.cpp:1204-1209, 1294, 1380-1383`)
already deletes them on M5:

| item | M4 cost | on ranked M5 |
|---|---|---|
| `g2_copybfloat16bfloat16` (76 calls) — strided-view materialisation at `LagunaRuntimeModel.swift:10511-10512` | 1.689 ms | **gone** (`:10582-10585` takes a free contiguous view instead) |
| routed silu-product, 38 of the 77 `compiledSiluProduct` calls (`SwitchLayers.swift:7-14`) | 0.756 ms | **gone** |
| total | **2.445 ms = 14.0 % of measured glue** | |

So: M5-relevant glue = 15.018 ms at M4 clock → **7.154 ms = 7.31 % of M5
prefill** after bandwidth scaling. Glue's *share* doubles on M5 while its
*addressable headroom* does not.

---

## 5. Ranked triage

Ranking non-GEMM work by *(time share) × (distance from roof) × (editable)*
gives an almost empty list, so I present it **two ways** and label which
interpretation each ranking uses. Everything below is editable, so the third
factor is 1 throughout and does not discriminate.

### 5.1 Interpretation A — distance from roof (tuning the existing kernel)

| rank | family | share | distance from roof | score = share × distance |
|---|---|---|---|---|
| 1 | qk_norm_rope | 0.76 % | 1.24 ms (70 % of roof) | 1.24 ms |
| — | router | 0.12 % | **n/a** — latency-bound, not DRAM-bound | excluded |
| 3 | elementwise, sort_scatter, moe_tail, rms_norm, lm_head, other | 2.29 % | **0 ms** (all ≥ 111 % of roof) | 0 |

Ceiling for the whole interpretation: **0.59 ms of M5 prefill** (§3.3),
straddling the 0.53–0.77 ms bar, requiring a perfect-roof outcome. **Dead.**

### 5.2 Interpretation B — removable bytes (fusing the glue away)

This is the framing that actually has any prize in it, because six families are
above the DRAM roof and therefore cannot be *tuned* — only *deleted*. Ranked by
M5-live removable round-trip:

| rank | lever | M4 ms | M5 ms | % of score | M5-live? |
|---|---|---|---|---|---|
| **1** | fold per-head softplus gate into `o_proj` prologue (`g2_Multiplybfloat16`, 40 calls) | 1.328 | **0.633** | **0.164–0.239 %** | ✅ yes |
| 2 | fold shared-expert silu-product (39 of 77 `compiledSiluProduct`) | 0.776 | 0.370 | 0.096–0.140 % | ✅ yes |
| — | *ceiling: both at once* | 2.104 | 1.002 | 0.260–0.379 % | ✅ |
| n/a | `g2_copybfloat16bfloat16` strided-view removal | 1.689 | 0.805 | 0.209–0.304 % | ❌ **already gone on M5** |
| n/a | SwiGLU → gather-GEMM epilogue fusion | — | — | — | ❌ **already implemented and enabled on M5** |
| n/a | weighted combine → `moe_tail` | — | — | — | ❌ already 4-in-1 fused; irreducible |

Note how much of the apparent prize evaporates on inspection: the single
largest removable-byte item on *this host* (`g2_copy`, 0.805 ms M5, which would
have cleared the bar) is **already harvested on the ranked M5**, and both
epilogue-fusion ideas one would reach for next are **already implemented
upstream**. This is exactly the M4→M5 non-transfer trap of §3.6, and it is the
main reason this census does not hand back a candidate.

### 5.3 Desk price of the top candidate (one only, per the stopping rule)

**Lever:** fold the per-head softplus gate multiply into the `o_proj` prologue.
`output * gate[.ellipsis, .newAxis]` at `LagunaRuntimeModel.swift:6469-6472`
(gate from `lagunaCompiledSoftplusGate`, `:6467`) is consumed immediately by
`return wo(output)` at `:6478`. The decode-only analogue already exists as a
template at `:6330-6337` (`laguna_gated_affine_oproj_*`), so this is the
prefill twin of a shipped kernel. 40 dispatches, 0.584 GB, `[1,512,64,128] *
[1,512,64,1]` bf16 (29 sliding × 16 MiB + 10 full × 12 MiB + 1 last-row).

| quantity | value |
|---|---|
| measured M4 cost | 1.328 ms (0.24 % of M4 prefill) |
| M5 projection (bandwidth ÷2.10) | **0.633 ms** = 0.65 % of the 97.895 ms M5 prefill |
| prefill speedup | ×1.0065 |
| score value at 0.2592 %/ms (receipt-derived) | **+0.164 %** |
| score value at 0.3781 %/ms (prospective) | **+0.239 %** |
| bar (+0.2 % of score) | 0.53–0.77 ms of M5 prefill |
| verdict | **clears only under the optimistic conversion; fails under the receipt-derived one** |

Three reasons this does not justify a probe:

1. **It straddles the bar.** 0.164–0.239 % against a 0.2 % bar is not a
   decision, it is a coin flip on which conversion rate you adopt.
2. **It is smaller than the measurement noise it would have to beat.**
   Session-to-session prefill spread is ~±0.6 % (≈±0.6 ms), about **20×** the
   within-session CV of 0.0299 %. A 0.633 ms effect is inside cross-session
   drift, so a standalone submission could not distinguish it from thermal
   noise except in a tightly paired same-session A/B.
3. **It is a GEMM-kernel edit booked as a glue win.** The bytes are deleted by
   writing an `o_proj` prologue, and bit-exactness requires reproducing the
   current bf16 round-trip exactly (the multiply currently materialises to bf16
   before `wo`; a fused fp32-accumulate prologue would *not* be bit-identical).
   Charging this to "non-GEMM optimisation" would be mis-attribution.

For scale, the same engineering effort aimed at `routed_gather_gemm` addresses
**143.03 ms** of M4 headroom at 46.1 % of peak — **226× more** than this
lever's 0.633 ms.

---

## 6. Verdict — N-GEMM-DOMINATES

**N-GEMM-DOMINATES.** The 60.88 %-not-in-`steel_gemm*` headline is real but
non-actionable: 96.30 % of prefill is matmul-or-attention work, and the true
non-matmul surface is 3.18 % of M4 prefill (17.463 ms), of which 14 % does not
even exist on the ranked M5 because the aligned gather route's fused epilogue
already deletes it. Tuning that surface is bounded by 0.59 ms of M5 prefill
(0.153–0.224 % of score) and all of it sits in one reduction kernel already at
70 % of the DRAM roof, while six of eight glue families run *above* the roof and
therefore have literally zero distance to travel. Deleting bytes rather than
tuning them is the better framing, but its best single lever prices at 0.633 ms
M5 = 0.164–0.239 % of score — straddling the +0.2 % bar, inside the ±0.6 ms
cross-session drift, and payable only by writing a GEMM epilogue that must
reproduce a bf16 round-trip bit-exactly. V-ATTN is separately dead: with the
corrected 8.0 TFLOP/s roof the attention core runs at 69.7 % of peak on
causal-halved FLOPs, totals ~1.2 ms on M5, and its window/mask lever is already
fully harvested (both layer classes take the identical implicit-`.causal` SDPA
path at n=512, and last-layer row truncation is already implemented). Against
all of that, `routed_gather_gemm` holds 48.4 % of prefill at **46.1 % of peak**
with 143.03 ms of M4 headroom — two orders of magnitude more addressable time
than the entire non-GEMM surface combined. Prefill optimisation should return to
the gather-GEMM, and the correct next question is the one this census cannot
answer from an M4 host: what the *aligned* `bm 64 / wm 4` route achieves against
roof on the ranked M5.

Not **V-NONGEMM**: the whole surface is bar-marginal at best. Not **V-ATTN**:
69.7 % of peak, ~1.2 ms M5, mask lever exhausted. Not **N-INSTRUMENT**: the
instrument closed to 100.2 % of wall, the offline replay reproduced it exactly,
and the one 57 ms artefact was identified and removed with its mechanism
explained.

---

## 7. Prior art cleared (Rule 83)

Cleared before proposing anything, and each item is the reason a candidate was
*not* proposed:

| prior result | citation | effect here |
|---|---|---|
| Prefill attention already does per-simdgroup causal K-block elision, register Q-hoist, direct device loads, `mem_none` barriers | `PREFILL_NAX_ANALYSIS.md:128-132`; `steel_attention_nax.h:250-270, 318-338, 587-596` | V-ATTN has no easy mechanism left |
| "Any hypothesis whose premise is 'prefill attention is inefficient' is refuted before it starts" | `RESEARCH_STATE_ARCHIVE_through-round-21.md:4245-4249` | confirmed at 69.7 % of peak |
| Narrow `_nax` attention tiles: **+0.639 ms on M5** (regression) | #527, `R104B:1002-1016` | tile retuning is a known loss |
| `DARKBLOOM_ATTN_QHOIST` ≤ 0.33 % | prior round | below bar |
| Swizzle depth −0.0141 ms; arange caching ~0 ms; empty-expert TGs < 0.1 % | prior rounds | below bar; arange independently re-explained here as an overlap artefact |
| Split-K gate `matmul.cpp:922-924` not bit-exact | prior round | excluded by correctness gate |
| `bn=128` minimum-tile claim STRUCK; SM=8 unreachable (`kFragRows=16`) | prior rounds | not re-proposed |
| BM 64→128 gather-GEMM −5.7 % (merged) | prior round | the live direction, and it is a GEMM lever |
| "HOST-IDENTICAL glue" 17.511 ms M4 → 8.34 ms M5, priced 8.04 ms vs a 7.94 ms floor over 4.34 GB ⇒ ~101 % of its own roof | `NMPC:362-364, 450-461` | **independently reproduces this round's conclusion** from a different census |
| Union busy 99.4 % of wall | prior round | reproduced (99.5 % `SPLIT=1`, 99.1 % `SPLIT=0`) |
| M5 prefill S ≈ 96.15–98.15 ms ≈ half of both M5 rooflines | `PREFILL_NAX_ANALYSIS.md:3-4` | the projection denominator used throughout |
| M5 decomposition S = 97.895 = gather-GEMM 43.262 + non-MoE 54.633; 11.40 ms M5-specific residual ≈ 9.33 steel + 1.2 attention + 0.85 nvfp4 dense | `RESEARCH_IDEAS_steel-gemm-prefill.md:13-28`, `:219-221` | source of the "~1.2 ms M5 attention" figure |

No overlap with the excluded work: decode bytes / NVFP4 weight encoding (#615),
fern's #619, frieren's #597, nezuko's #616. This round touched prefill only and
shipped no runtime change.

---

## 8. Corrections to the record

1. **Ceiling (§3.1): 8.0 TFLOP/s, not 28.76.** `host_flop_ceiling.swift`
   const-folds its four MMAs into ~one. This flips fern's "large headroom"
   reading and restores the H8-dead verdict.
2. **The brief's "CV 0.0403 %" mis-cites the M5 `officialScore` CV.** The
   `prefill_ms` figure in that same source is 96.14921 ± 0.13681 (n=3, PR #592
   A0, `CURRENT_RESEARCH_STATE.md:528`) ⇒ prefill CV **0.142 %**. Local
   `prefill_probe` warm CV is **0.0299 %** (n=5). Session-to-session spread is
   ~±0.6 %, i.e. **~20× the within-session CV** — always A/B inside one session.
3. **The "hard 1,671,168 B tracer quota" is stale/retracted.** It was an
   unflushed `static std::ofstream` losing the final partial 4096 B page
   (408 × 4096). Use stderr
   (`maple-tanjiro-r104c-prefill-steel-census.md:88-110`, commit `d1517a80`).
   This census emitted 1,824,652 B / 15,313 records with no loss.
4. **`SPLIT=0` alone mis-attributes families by up to 7.6×** (§2.1).
5. **Gather-GEMM GFLOP: 979.3, not 1005.0** — the latter assumed 39 full-length
   MoE layers; the trace shows 38.
6. **`nvfp4_dense_qmm` is 122.4 GFLOP** (shared expert over 38 layers). This
   resolves the standing inconsistency **D**: the 198.0 GFLOP scoping would put
   it at 124 % of the 8.0 roof, i.e. impossible.
7. **The M4 census does not run the ranked gather kernel** (§3.6).

Unresolved inconsistencies in the record, flagged not fixed:

- **B** M5 MMA peak quoted as 56 (measured, `tanjiro-pr34-result.md:397-398`) /
  57 (inferred, `PREFILL_NAX_ANALYSIS.md:20`) / 60 (nominal) / 34.7
  (**withdrawn as circular**).
- **C** M5 DRAM quoted as 546.2 (an *achieved* decode rate, not a peak —
  `pr73-decode-kernel-census.md:735-743`) vs 610 (streaming upper bound `:729`)
  vs 500–550. I used 546.2, which makes the M5 glue projections **conservative**
  (a higher true peak shrinks them further).
- **E** steel GFLOP 1465.3 (attn_proj only) vs 1502.8 (incl. router/dense/
  g_proj). Both reported in §3.2; the verdict is unchanged either way (85.4 %
  vs 87.6 % of peak).
- **F** `r104c:579-590` markdown `site` labels contradict `steel_census_237.csv`
  (buckets 1/2/4/5 are `attn wo`/`wq`, not MoE/FFN). **The CSV is right.**
- **G** `qk_norm_rope` bytes 0.730 (trace) vs 0.965 (analytic); `moe_tail` 0.837
  vs 0.818. See §3.4 for the mechanism on the former.
- **H** dangling citation "`PREFILL_NAX_ANALYSIS.md` §6.2" — that section does
  not exist.
- **I** steel calls 392 = 237 GEMM + 155 split-K accumulate.
- **J** fern's ms are raw; census ms are deflated ×0.982275. **Do not mix.**

---

## 9. Reproduction

Instrumented worker (Rule 75), built from source state `cf82bb3a`:

```
swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
```

| artifact | value |
|---|---|
| path | `.build-worker/release/mlxfast-runtime-worker` |
| sha256 | `1bbe7cb7fabdc1a6799ff234611733d9416a132a1c73738ca9f0c2d896f06c9a` |
| bytes | `49,209,912` |
| build time | 33.7 s (incremental) |

Census (91.06 s, exit 0), one worker process:

```
env CENSUS_OUT=research/pr270-logs-r106f CENSUS_REPS=8 CENSUS_TOP=400 \
  bash research/tanjiro_prefill_census.sh
```

Offline adjudication (zero GPU cost, reproduces the in-process numbers exactly):

```
python3 research/prefill_census_adjudicate.py \
  --stderr research/pr270-logs-r106f/split1.worker.err \
  --cbs 1066 \
  --walls-ms 548.25,548.53,548.10,548.06,548.81,548.52,548.43 \
  --drop arangeuint32 --profile-top 6
```

Arithmetic in this document:

```
python3 research/r106f_nongemm_arith.py
```

Evidence: `research/pr270-logs-r106f/{split1.log,split0.log,adjudicated.log,arith.log}`.
Reusable tooling added this round (Rule 58): `research/prefill_census_adjudicate.py`
(overlap adjudication of any GPUPROF trace) and `research/r106f_nongemm_arith.py`.

The two `TEMP INSTRUMENT` commits (`dcf2c224`, `cf82bb3a`) that added the
`GPUPROF`/`GPUDIM` dispatch hooks are **reverted** at the end of this branch;
the regenerated hook lives in `research/pr91-gpuprof-hook.patch` for reuse.

---

## 10. Suggested follow-ups (not implemented)

1. **Measure the aligned `bm 64 / wm 4` gather route against roof on M5.** This
   census cannot reach it (§3.6) and it is where 48.4 % of prefill lives at
   46.1 % of peak. Gate on achieved-GB/s-vs-roof *before* proposing a tiling
   change. Average rows/expert is ~16 against BM=128 tiles — one useful 16-row
   fragment of eight — which is the specific inefficiency to price.
2. **Persistent-expert tile scheduling + offline NVFP4/scale interleave** for
   the gather-GEMM, continuing the validated BM 64→128 direction.
3. **Retire the ceiling doubt cheaply**: four distinct runtime-sourced A_k/B_k
   pairs in `host_flop_ceiling.swift`, or `xcrun metal -S` + MMA opcode count.
   Worth doing because the H8-dead verdict holds only for `M4_peak ≤ 8.08`.
4. **If a gather-GEMM epilogue change is written anyway**, bundle the §5.3 gate
   fold into it — 0.633 ms M5 is not worth its own submission but is nearly free
   alongside an epilogue edit that is already being made bit-exact.
5. **Fix the record**: correct the 28.76 TFLOP/s citation in
   `prefill_budget.py:32-33` and `maple-fern-prefill-roofline.md:68`, and the
   `site` labels at `r104c:579-590` (inconsistency **F**).
