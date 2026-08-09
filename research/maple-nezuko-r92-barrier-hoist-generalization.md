# R92-A — Barrier-hoist generalization: Stage-1 inventory and null verdict

**Assignment** `maple-r92-a-barrier-hoist-generalization` (rev `r92-a-rev1`, PR #488)
**Base** `8486638578a283de40369172f68c3a4d2d6a5365`
**Rig** AWS M4 Pro, `applegpu_g16s` (Apple GPU gen 16). Directional only — the
ranked M5 selects `_nax` kernels this host cannot reach.
**Editable surface changed by this branch: none.** `git diff BASE_SHA HEAD --
Sources/ Vendor/` is empty. Everything below is measurement and source audit.

---

## 1. Verdict

**H0 is favoured. The router kernel was close to special; the family should
close.**

The Stage-1 audit terminates the experiment under the assignment's own stopping
rule. Two findings, in order of importance:

1. **The aggregate ceiling is 20–45 µs/step against an 80 µs/step bar.** Even
   granting every qualifying site and an optimistic estimator, the family cannot
   reach H1's detection bar. This conclusion is *independent of the site count*,
   which is why I regard it as the real result.
2. **The site count is 5 or 6 depending on the counting convention** — 5 distinct
   Swift edit points, 6 live kernel×site instantiations. That straddles the
   stopping rule exactly, which is why §9 asks the advisor for the go/no-go call
   rather than guessing. My recommendation is to stop regardless, on the strength
   of finding 1.

The structural reason the family is small is worth carrying forward:

> **The three kernels that dominate decode contain no `threadgroup_barrier` at
> all.** `decode_nvfp4_qkv_*` (1,702.9 µs/step), `oproj_act_*` (1,419.5 µs/step)
> and `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` (1,497.7 µs/step)
> together are **4,620 µs/step = 54.2 % of the GPU-busy pool**, and the
> barrier-hoist mechanism structurally cannot touch any of it.

---

## 2. Method

Ground truth for reachability is a **live GPU profile of the steady decode
window**, not source reading. The profiler hook
(`research/nezuko-pr158-gpuprof-hook.patch`) was applied to a scratch worker
build, three censuses were taken, and the patch was then reverted — this branch
ships no `Vendor/mlx-swift` edit.

```
swift build -c release --force-resolved-versions --scratch-path .build-worker \
    --product mlxfast-runtime-worker
env DARKBLOOM_ROUTER_WEIGHT_PREFETCH=<1|0|5> \
    DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
    python3 research/decode_probe.py --steps 80 --profile --profile-top 250
```

All three runs reported **0 teacher-forced divergences**. Steady window = 79
steps, 32,074 command buffers, **406 dispatches/step**.

Because no kernel source was modified, the correctness gates
(`research/run_upstream_equivalence.sh`, `--local-iterate` `max_abs_diff`) are
satisfied trivially and were not re-run: the shipped tree is byte-identical to
the base on every editable path. Running them would have proven nothing about
this result and would have consumed a thermal window.

---

## 3. Live decode census (default arm, `DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1`)

Per steady step: wall **9.768 ms**, `gpu_busy_sum` **8.528 ms**, gap 1.241 ms
(12.7 %), 406 CBs, 406 dispatches. 24 distinct labels.

| µs/step | share | n/step | µs/call | kernel |
|---:|---:|---:|---:|---|
| 1497.7 | 17.56 % | 39 | 38.40 | `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` |
| 1340.1 | 15.71 % | 30 | 44.67 | `decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1` |
| 1117.7 | 13.11 % | 30 | 37.26 | `oproj_act_h64_v1_lm1_pw1_sc1_se1` |
| 858.9 | 10.07 % | 39 | 22.02 | `routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` |
| 636.0 | 7.46 % | 30 | 21.20 | `sliding_fused_attn_ring_v1` |
| 420.3 | 4.93 % | 1 | 420.27 | `lmhead_int5_base_coarse_delta_bf16_v1` |
| 362.8 | 4.25 % | 10 | 36.28 | `decode_nvfp4_qkv_h48_r1_v1_lm1_pw1_se1_sd1` |
| 312.8 | 3.67 % | 39 | 8.02 | `residual_rms_router_bf16_2048_rpg8_keys_v1_pf1` |
| 301.8 | 3.54 % | 10 | 30.18 | `oproj_act_h48_v1_lm1_pw1_sc1_se1` |
| 287.1 | 3.37 % | 39 | 7.36 | `shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` |
| 269.4 | 3.16 % | 1 | 269.39 | `dense_gate_up_swiglu_bf16_v1` |
| 248.0 | 2.91 % | 30 | 8.27 | `gate_sp_h64_v1` |
| 229.7 | 2.69 % | 10 | 22.97 | `full_fused_attn_grow_v1` |
| 185.5 | 2.18 % | 39 | 4.76 | `prefill_router_tournament_ordinal_norm_active64_v2` |
| 141.9 | 1.66 % | 41 | 3.46 | `rmsbfloat16` |
| 133.8 | 1.57 % | 1 | 133.77 | `dense_down_residual_bf16_v1` |
| 80.2 | 0.94 % | 10 | 8.02 | `gate_sp_h48_v1` |
| 77.0 | 0.90 % | 1 | 76.98 | `lmhead_exact_fused_int5_sparse_refine_v1` |
| 9.0 | 0.11 % | 1 | 8.98 | `argmax_bfloat16` |
| 4.7 | 0.05 % | 1 | 4.69 | `lmhead_exact_winner_bf16_midpoint_threshold_v1` |
| 4.1 | 0.05 % | 1 | 4.08 | `lmhead_coarse_argmax_stage1_v5` |
| 3.5 | 0.04 % | 1 | 3.49 | `decode_embedding_rope_atlas_bf16_2048_v2` |
| 3.4 | 0.04 % | 1 | 3.41 | `gather_frontbfloat16_int32_int_2` |
| 2.9 | 0.03 % | 1 | 2.90 | `residual_rms_bf16_2048_v1` |

### Two rule-39 traps this census exposes

- **`prefill_router_tournament_ordinal_norm_active64_v2` runs 39×/step in
  decode**, despite the name and despite the `projectedLogits.dim(1) > 1` guard
  at `LagunaRuntimeLayers.swift:1414`. That guard is *not the only entry point*:
  `lagunaDecodeRouterTop8` (`LagunaRuntimeLayers.swift:769`) calls
  `lagunaPrefillRouterTournamentOrdinalForTesting(..., rows: 1, ...)` at
  `:776` when `lagunaDecodeRouterOrdinalEnabled &&
  lagunaDecodeRouterOrdinalScoreTableEnabled && lagunaDecodeRouterTournamentEnabled`.
  A source-only audit that trusted the name or the `dim(1)` guard would have
  scored this kernel dead. It is not.
- Conversely the `lagunaDecodeRouterTop8KernelSource` / `…OrdinalKernelSource`
  kernels — the ones *named* for decode — are dead.

### The decisive default: `DARKBLOOM_NATIVE_AFFINE_NVFP4_FROM`

`lagunaNativeAffineNVFP4From` defaults to `"0"`
(`LagunaRuntimeModel.swift:2961-2967`), so **all 40 layers** carry NVFP4
group-16 QKV/o_proj. Every `mode == .affine && bits == 8 && groupSize == 32`
guard is therefore false, which kills five whole barrier-bearing symbols
(`lagunaNormAffineQKV*`, `lagunaGatedAffineOProjSource`). This single default
accounts for 10 of the 26 dead sites.

---

## 4. Stage-1 inventory — all 28 grep hits in `LagunaRuntimeModel.swift`

Rule-39 verdict column cites the guard, its default and the line that settles it.

| # | line | emitting symbol | emitted kernel | rule-39 verdict (guard · default · line) | disp/step | hoistable | bytes | barriers crossed |
|---:|---:|---|---|---|---:|---|---:|---:|
| 1 | 689 | — | — | **PROSE** in the `DARKBLOOM_ROUTER_WEIGHT_PREFETCH` docstring | — | n/a | — | — |
| 2 | 911 | — | — | **PROSE** in the norm-prologue docstring | — | n/a | — | — |
| 3 | 843 | `lagunaNormReductionTail` `:831` | via `:1083` → `residual_rms_router_…_pf1`; via `:1182` → `residual_rms_bf16_2048_v1` | LIVE, 2 callers | 39 + 1 | **YES** (gamma) | 8 B/thr | 3 |
| 4 | 847 | ″ | ″ | LIVE | 39 + 1 | **YES** (same site) | ″ | ″ |
| 5 | 854 | ″ | ″ | LIVE | 39 + 1 | **YES** (same site) | ″ | ″ |
| 6 | 1094 | `lagunaResidualRMSNormRouterSource` `:930` | `residual_rms_router_…_pf1` | LIVE; `lagunaRouterWeightPrefetch` default `1` `:697-704` | 39 | **already hoisted by #475** | — | — |
| 7 | 1590 | `lagunaSlidingFusedAttentionKernel` `:1508` | `sliding_fused_attn_ring_v1` `:1509` | LIVE, 30 sliding layers (`LagunaConfig.swift:20-21`) | 30 | **YES** | ≈32 B/thr | 1 |
| 8 | 1740 | ″ (epilogue transpose of `outputs4`) | ″ | LIVE kernel | 30 | no — threadgroup-only reads | — | — |
| 9 | 1761 | ″ (`max_scores`) | ″ | LIVE kernel | 30 | no — threadgroup-only | — | — |
| 10 | 1764 | ″ (`sum_exp_scores`) | ″ | LIVE kernel | 30 | no — threadgroup-only | — | — |
| 11 | 2030 | `lagunaFullFusedAttentionKernel` `:1940` | `full_fused_attn_grow_v1` `:1941` | LIVE, 10 full layers (`LagunaConfig.swift:18-19`) | 10 | **YES** | ≈32 B/thr | 1 |
| 12 | 2224 | ″ (epilogue) | ″ | LIVE kernel | 10 | no — threadgroup-only | — | — |
| 13 | 2245 | ″ (epilogue) | ″ | LIVE kernel | 10 | no — threadgroup-only | — | — |
| 14 | 2248 | ″ (epilogue) | ″ | LIVE kernel | 10 | no — threadgroup-only | — | — |
| 15 | 3336 | `lagunaFusedQKVProjectionSource` `:3042` | `fused_norm_qkv_projection_bf16_h{48,64}_v3` | **DEAD** — superseded by `lagunaDecodeNVFP4QKVR1` `:5863-5867` | 0 | — | — | — |
| 16 | 3389 | ″ | ″ | **DEAD** | 0 | — | — | — |
| 17 | 3930 | `lagunaGatedAffineOProjSource` `:3869` | `gated_affine_oproj_qmv_i8g32_h*` | **DEAD** — needs INT8 g32 o_proj; `…NVFP4_FROM` = `0` `:2961-2967` | 0 | — | — | — |
| 18 | 4203 | `lagunaGatedAffineOProjNVFP4Source` `:4135`, inside `gateSetup` `:4190` | (would be `oproj_act_*`) | **NOT EMITTED** — `gateSetup = preActivatedGate ? "" : …`; both live o_proj pipelines pass `preActivatedGate: true` (`:4460`, `:4478`) | 0 | — | — | — |
| 19 | 4990 | `lagunaNormAffineQKVSource` `:4980` | `norm_affine_qkv_qmv_i8g32_r*` | **DEAD** — INT8 g32 QKV unreachable, see #17 | 0 | — | — | — |
| 20 | 5042 | `lagunaNormAffineQKVBody` `:5010` | ″ | **DEAD** | 0 | — | — | — |
| 21 | 5056 | ″ | ″ | **DEAD** | 0 | — | — | — |
| 22 | 5065 | ″ | ″ | **DEAD** | 0 | — | — | — |
| 23 | 5243 | `lagunaNormAffineQKVPrefetchSource` `:5151` | ″ | **DEAD** | 0 | — | — | — |
| 24 | 5257 | ″ | ″ | **DEAD** | 0 | — | — | — |
| 25 | 5266 | ″ | ″ | **DEAD** | 0 | — | — | — |
| 26 | 8066 | `lagunaRoutedDownReduceKernel` `:7981` | `routed_nvfp4_down_reduce_bf16_v2` | **DEAD** — `else if` fallback never taken, `LagunaRuntimeLayers.swift:2074-2106` | 0 | — | — | — |
| 27 | 8309 | `lagunaRoutedSharedDownResidualSource` `:8190` | `routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` | LIVE, 39 sparse layers | 39 | **YES** | 34 B | 1 |
| 28 | 8437 | `lagunaRoutedSharedDownResidualStagedKernel` `:8340` | non-`sh` stage4 twin | **DEAD** — `sharedHalved` default ON `:311-312` | 0 | — | — | — |

**Tally: 26 code sites. 16 dead or not emitted · 6 live-but-not-hoistable ·
1 already hoisted (#475) · 3 newly qualifying + 1 shared helper site qualifying
in 2 instantiations.**

---

## 5. Extension audit beyond the assigned 28

The 28 lines are the assigned surface, but `threadgroup_barrier` appears in
three `Sources/` files and one listed vendor file. Complete census:

| file | occurrences | live-decode sites |
|---|---:|---|
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 28 (26 code + 2 prose) | see §4 |
| `Sources/MLXFastModel/LagunaRuntimeLayers.swift` | 12 (11 code + 1 prose `:1000`) | `:1215`, `:1253` |
| `Sources/MLXFastModel/LagunaLmHeadPrune.swift` | 2 | `:382`, `:459` |
| `Vendor/mlx-swift-lm/…/MLXLMCommon/SwitchLayers.swift` | 7 | none — all in `mlx_lm_route_csort_*` |
| `Vendor/mlx-swift-lm/…/Laguna.swift` | 0 | — |

- `LagunaRuntimeLayers.swift:1215,:1253` — `lagunaPrefillRouterTournamentOrdinalKernelSource`
  `:1150`, **live 39×/step** (see the rule-39 trap in §3). **Not hoistable**: the
  post-barrier reads are `candidate_ordinals` / `candidate_indices` /
  `xchg_ordinals` / `xchg_indices`, all threadgroup, and the epilogue reads
  `original_scores[my_index2]` — threadgroup *and* data-dependent index. Fails
  clause 2 twice over.
- `LagunaRuntimeLayers.swift:413,418,567,571` (decode router top8/ordinal),
  `:898,909` (prefill top8), `:1090,1108,1113` (prefill tournament) — all dead.
- `LagunaLmHeadPrune.swift:382` in `lmhead_coarse_argmax_stage1_v5` `:338`,
  live 1×/step. **Not hoistable** — reads `shared_vals` / `shared_idxs`.
- `LagunaLmHeadPrune.swift:459` in
  `lmhead_exact_winner_bf16_midpoint_threshold_v1` `:424`, live 1×/step.
  **Partially hoistable**: `mrow = lm_head + r*K` depends on `winner_row[0]`
  (threadgroup) so that stream fails clause 2, but the `x + bn` stream
  (16 × 8 B = 128 B) is argument/lane-addressed and qualifies. Ceiling ≪ 1 µs/step
  on a 4.69 µs/call kernel dispatched once.

**No other file under `Sources/` or in the listed vendor set contains a barrier.**
`rmsbfloat16` (41×/step, 141.9 µs/step) is the AOT MLX RMSNorm and lies outside
the audited Swift-emitted surface; it is flagged in §10 as unexamined.

---

## 6. Qualifying sites, checked against all four clauses

### 6.1 `:1590` — `sliding_fused_attn_ring_v1` (30×/step, 21.20 µs/call)

This site was **initially misjudged as RAW-hazardous and that was wrong**. The
`T_LOAD_K` / `T_LOAD_V` macros (`:1797-1830`, duplicated at `:2281-2310`) take a
`substitute` flag: when the row index equals `widx` — the ring slot written just
before the barrier — the kernel reads `tg_k` / `tg_v` (threadgroup) *instead of*
the device pointer. **The device `k_cache` / `v_cache` loads therefore never read
the just-written row.**

1. **device load after barrier** — yes, `pipe_ka[4]`, `pipe_kb[4]`,
   `pipe_va0..3`, `pipe_vb0..3` from `k_cache` / `v_cache`.
2. **address arg/position-only** — yes. `pair_keys` / `pair_values` are computed
   at `:1607-1613` from `k_cache`, `kv_head`, `window`, `head_dim`, `sg`, `lane`.
   Nothing threadgroup-derived.
3. **FP order unchanged** — yes, loads move, the `simd_shuffle` reduction and
   accumulation stay put.
4. **registers** — ≈12 extra live across the barrier; the kernel already holds
   `pair_q0/q1/o0/o1` (16 floats) at 1024 threads/group.

The hoist must be **predicated on `!sub_a` / `!sub_b`**, both computable
pre-barrier from `sg` and `widx`. An unpredicated hoist would technically race on
the `widx` row — the value is discarded, but reading a concurrently-written
location is still a data race in the Metal memory model, and it would dissolve
the macro's race-free-by-construction invariant. Predication keeps that invariant
intact at zero cost.

### 6.2 `:2030` — `full_fused_attn_grow_v1` (10×/step, 22.97 µs/call)

Structurally identical to 6.1; `pair_keys` / `pair_values` at `:2047-2053`. Same
verdict, same predication requirement, ≈32 B/thread across 1 barrier.

### 6.3 `:8309` — `routed_shared_nvfp4_down_residual_…_sh_stage4_v6` (39×/step, 22.02 µs/call)

After the barrier, threads with `slot == 0 && lane < outputs_per_simd` load
`router_weights[routed_slot]` (8 × f32 = 32 B) and `residual[first_row + lane]`
(2 B). Both argument/lane-addressed; accumulation into the output is unchanged;
≈9 extra registers; 1 barrier crossed. These are **fully-exposed dependent loads
at the very end of the kernel** — the most favourable shape in the whole
inventory, and the reason this site ranks first on a per-call basis.

### 6.4 `843/847/854` — gamma loads in `lagunaNormReductionTail` (39 + 1 ×/step)

**This site was missed on my first pass and recovered by an independent audit.**
I had attributed the gamma-load mechanism only to the dense instantiation
(`residual_rms_bf16_2048_v1`, 1×/step, negligible) and overlooked that the same
helper is inlined at `:1083` into the **router** kernel at 39×/step.

At `:1085-1090`, after all three reduction barriers:

```
bfloat value = weight[base + i] * bfloat(float(values[i]) * laguna_inv_mean);
```

`weight[base + i]` is a **device** gamma load; `values[i]` is already in
registers from the pre-barrier sum-of-squares pass. Address is thread-position
+ loop-index only. Hidden 2048 / 512 threads → `n_reads = 4` × 2 B = **8 B/thread
across 3 barriers**.

Crucially this is **not** what #475 hoisted. #475's `prefetchEarly` (`:1083`)
moved the *`router_weight` GEMV* loads above the tail; the gamma stream was left
in place. So it is a genuinely distinct site — but it lives in the *same kernel*
and hides behind the *same* barrier ladder, which bounds its ceiling (§7).

---

## 7. Ceiling arithmetic

### Calibration (admissible: #475 paired ABBA `nat` headline)

| quantity | value |
|---|---|
| #475 headline A1 − A4 | **−6.85 µs/step**, 95 % CI [−9.76, −3.94], 8/8 signs, p = 0.0039 |
| per call (39 calls/step) | **0.1756 µs/call** |
| as a fraction of that kernel's SPLIT=1 time (312.8 µs/step) | **2.19 %** |
| measured reduction-tail phase ceiling | 0.328 µs/call ≈ **12.80 µs/step** |
| realized capture | **54 %** |

### Material qualifying sites

| site | kernel | calls/step | µs/step (SPLIT=1) |
|---|---|---:|---:|
| `:1590` | `sliding_fused_attn_ring_v1` | 30 | 636.0 |
| `:2030` | `full_fused_attn_grow_v1` | 10 | 229.7 |
| `:8309` | `routed_shared_…_sh_stage4_v6` | 39 | 858.9 |
| `843/847/854` @ `:1083` | `residual_rms_router_…_pf1` | 39 | 312.8 |
| **total** | | **118** | **2037.4** (23.9 % of busy) |

Negligible sites (`843…` @ `:1182`, `LmHeadPrune:459`) add 2 calls and 7.6 µs/step.

### Estimator A — per-call constant (physically motivated)

The hidden quantity is one round of device-load latency behind a barrier, roughly
constant in absolute time regardless of kernel duration.

- `:1590` + `:2030` + `:8309`: 79 × 0.1756 = **13.9 µs/step**
- `843/847/854` @ router: bounded by the *unclaimed* remainder of the
  already-measured phase ceiling for that exact kernel, 12.80 − 6.85 =
  **≤ 5.95 µs/step** (and the gamma stream is only part of that remainder)
- negligible sites: **< 0.5 µs/step**

**Total ≈ 20.3 µs/step = 0.31 %.**

### Estimator B — fraction-of-kernel constant (deliberately optimistic)

Assumes the hideable fraction scales with kernel duration. This is generous: the
router is 8.02 µs/call while the three big kernels are 21–23 µs/call, yet the
absolute exposed-load latency behind their *single* barrier is no larger than
behind the router's *four*.

- uncaptured ceiling: 2037.4 × 0.0219 = **44.6 µs/step = 0.68 %**
- at #475's realized 54 % capture: 44.6 × 0.54 = **24.1 µs/step = 0.37 %**

### What H1 requires

80 µs/step over 118 material calls = **0.678 µs/call** — **3.9× the router's
realized per-call win**, and 3.3 % of mean call time. A fully-exposed dependent
device load on this rig costs ~0.3–0.6 µs; recovering 0.68 µs/call *net* by
moving ≤ 34 B across one barrier, in kernels that already have ample other
latency to hide behind, is not physically plausible.

| estimator | aggregate | % of score | fraction of the 80 µs/step bar |
|---|---:|---:|---:|
| A — per-call constant (realistic) | 20.3 µs/step | 0.31 % | **25 %** |
| B — fraction-of-kernel, captured | 24.1 µs/step | 0.37 % | **30 %** |
| B — fraction-of-kernel, uncaptured upper bound | 44.6 µs/step | 0.68 % | **56 %** |
| H1 bar | 80 µs/step | 1.22 % | 100 % |

Score conversion 0.015280 %/µs/step. **No estimator reaches the bar; the
optimistic upper bound reaches 56 % of it.**

---

## 8. Three-arm router census — rule-44-compliant consistency check

Rule 44 requires a name-matched, residency-matched placement control. Arm 5
(`_pf1c`, `:1128`) emits the *character-identical* one-group peel immediately
below the normalize barrier, so `A1 − A5` isolates cross-barrier overlap from the
peel itself. All three arms, one SPLIT=1 census each, same session:

| arm | env | kernel label | µs/step | µs/call |
|---|---|---|---:|---:|
| A1 hoisted | `=1` | `residual_rms_router_bf16_2048_rpg8_keys_v1_pf1` | 312.8 | 8.02 |
| A0 unhoisted | `=0` | `residual_rms_router_bf16_2048_rpg8_keys_v1` | 318.5 | 8.17 |
| A5 placement control | `=5` | `residual_rms_router_bf16_2048_rpg8_keys_v1_pf1c` | 323.5 | 8.29 |

`A1 − A5 = −10.7 µs/step` (−0.27 µs/call), single-label, name-matched,
control-differenced.

**Admissibility.** This is n = 1 per arm, not a paired ABBA duplex, so under
rule 40 it carries the per-kernel SPLIT=1 pooled σ = 3.51 (this rig 3.34); a
difference of two single censuses has σ ≈ 3.34 × √2 ≈ **4.7 µs/step**. The
observed −10.7 is ≈2.3 σ and is compatible with #475's admissible `nat` headline
of −6.85 [−9.76, −3.94]. **I use −6.85, not −10.7, as the calibration constant in
§7.** The three-arm table is reported as a directional consistency check only.

Two things it does establish cleanly:

- The **ordering A1 < A0 < A5** is exactly the predicted physical ordering. The
  placement control is *worse* than plain unhoisted, consistent with the peel
  costing registers while delivering no overlap — which is precisely what makes
  A5 the right control rather than A0.
- **A live demonstration of why rule 43 bars SPLIT=1 totals.** The `gpu_busy_sum`
  across the three arms was 8.528 / 8.522 / 8.600 ms/step. The A5 arm is +72 µs/step
  on the total while its *own* changed label accounts for only +10.7. Roughly
  60 µs/step of that is drift across untouched labels.

---

## 9. Deliverable 4 — threadgroup geometry

**Stage 3 was not entered and no pipeline was modified, so
`maxTotalThreadsPerThreadgroup` was not measured for the qualifying kernels.**
Reporting a number here would be fabrication. What is verifiable from source is
the dispatch geometry, which under geometry neutrality is fixed and would be
unchanged by any hoist:

| kernel | grid | threadGroup | source |
|---|---|---|---|
| `residual_rms_router_…_pf1` | `(tiles * 512, 1, 1)` | `(512, 1, 1)` | `:1227-1228` |
| `sliding_fused_attn_ring_v1` | `((heads / 2) * 1024, 1, 1)` | `(1024, 1, 1)` | `:1883-1884` |
| `full_fused_attn_grow_v1` | `((heads / 2) * 1024, 1, 1)` | `(1024, 1, 1)` | `:2368-2369` |
| `routed_shared_…_sh_stage4_v6` | `(hiddenSize / 4 * 288, 1, 1)` | `(288, 1, 1)` | `:8559-8560` |

For reference, every #475 arm measured `maxTotalThreadsPerThreadgroup = 1024`,
`threadExecutionWidth = 32`, `staticThreadgroupMemoryLength = 4240`. The two
attention kernels dispatch at exactly 1024 threads/group, so they have **zero
occupancy headroom**: any hoist there must not raise register pressure enough to
drop the achievable maximum below 1024, or the dispatch fails outright. That is a
real risk for a ≈12-register increase and would have been the first thing Stage 2
measured.

---

## 10. Site count and the go/no-go question

| convention | count | members |
|---|---:|---|
| distinct Swift **edit points** | **5** | `:1590`, `:2030`, `:8309`, `843/847/854` (one helper), `LmHeadPrune:459` |
| live **kernel × site instantiations** | **6** | the above, with `843/847/854` counted twice (router 39×, dense 1×) |

Both counts sit exactly in the band where the assignment says to ask rather than
guess. **Advisor: which convention governs the stopping rule?**

My recommendation is to **stop either way**, because the count is not the binding
constraint — §7 is. Even at 6 sites the aggregate ceiling is 20–45 µs/step against
an 80 µs/step bar, and two of the six contribute < 8 µs/step between them.

If you nonetheless want Stage 2, the ranked order is `:8309` (39 calls,
fully-exposed dependent loads at kernel end) → `843/847/854` @ router (39 calls,
but capped at ≤5.95 µs/step residual) → `:1590` (30 calls) → `:2030` (10 calls),
and I would want the occupancy check in §9 done first, since a 1024-thread
dispatch that loses its threadgroup size is a hard failure rather than a slow
kernel.

**Unexamined surface worth one cheap look before the family is closed for good:**
`rmsbfloat16`, 41×/step and 141.9 µs/step, is AOT MLX RMSNorm outside the
Swift-emitted kernels I audited. It is the only live decode label I did not open.

---

## 11. H1 vs H0

| | claim | verdict |
|---|---|---|
| **H1** | ≥ 6 additional decode sites aggregating to ≥ 80 µs/step | **rejected** — 5–6 sites, aggregate ceiling 20–45 µs/step (25–56 % of the bar) |
| **H0** | the router kernel was special; the family is worth ~0.13 % and should close | **supported** |

H0 is supported with one refinement: the router kernel was not *unique*, it was
**the best member of a small family**. Three further material sites exist and one
more shares its kernel. But the family's total realistic value is ≈20 µs/step
≈ 0.31 %, against #475's already-banked 0.13 %. Extracting the remainder means
three separate kernel edits, two of them at zero occupancy headroom, for roughly
0.18 % combined.

The generalizable lesson for the campaign is §1's structural finding: **54 % of
decode time sits in three kernels that contain no barrier at all.** Barrier
hoisting was never going to be a large lever, and the census says so directly
rather than by inference.

---

## 12. Reproduction

```bash
git checkout 8486638578a283de40369172f68c3a4d2d6a5365
git apply research/nezuko-pr158-gpuprof-hook.patch     # local only, never shipped
swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved

for arm in 1 0 5; do
  env DARKBLOOM_ROUTER_WEIGHT_PREFETCH=$arm \
      DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
      python3 research/decode_probe.py --steps 80 --profile --profile-top 250
done

git checkout -- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.{cpp,h}
```

Each census ≈44 s. All three reported 0 teacher-forced divergences.
