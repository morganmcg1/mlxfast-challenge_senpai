# R86-B §3 — Redundancy-ranked census of the surviving decode boundaries

Base `7687c2e44e6975c181444ca8d3d151ee30480a72`. Host: Apple M4 Pro, 48 GiB,
Apple GPU generation 16 (`_nax` families unreachable; the decode families in
this census are all reachable and were observed executing). Every line number
refers to `Sources/MLXFastModel/LagunaRuntimeModel.swift` unless another file
is named.

## 3.0 The dispatch ledger is closed

The GPU-profile census (`research/nezuko-r86b-artifacts/dispatch-census.txt`,
raw profile in `profile-off-arm.log`) measures **406.0 dispatches and 45.0
command buffers per steady decode step**. That total is fully accounted for:

| block | dispatches | detail |
| --- | ---: | --- |
| embedding | 2 | `gather_frontbfloat16_int32_int_2`, `decode_embedding_rope_atlas_bf16_2048_v2` |
| layer 0 (dense MLP) | 8 | `rmsbfloat16`, `decode_nvfp4_qkv_h48_r1_…`, `full_fused_attn_grow_v1`, `gate_sp_h48_v1`, `oproj_act_h48_…`, `residual_rms_bf16_2048_v1`, `dense_gate_up_swiglu_bf16_v1`, `dense_down_residual_bf16_v1` |
| layers 1–39 (sparse MoE) | 390 | 39 × {`rmsbfloat16`, `decode_nvfp4_qkv_h{48,64}_r1_…`, `{sliding_fused_attn_ring_v1, full_fused_attn_grow_v1}`, `gate_sp_h{48,64}_v1`, `oproj_act_h{48,64}_…`, `residual_rms_router_bf16_2048_rpg8_keys_v1`, `shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1`, `prefill_router_tournament_ordinal_norm_active64_v2`, `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`, `routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6`} |
| lm head | 5 | `rmsbfloat16`, `lmhead_int5_base_coarse_delta_bf16_v1`, `lmhead_coarse_argmax_stage1_v5`, `lmhead_exact_winner_bf16_midpoint_threshold_v1`, `lmhead_exact_fused_int5_sparse_refine_v1` |
| sampling | 1 | `argmax_bfloat16` |
| **total** | **406** | matches the measured 406.0 exactly |

No kernel outside this list executes at decode. The census below is therefore
complete, not a sample.

Command-buffer arithmetic that follows from the same profile (each row is
`n/step × [dispatches] @ us/call`; the sum of `n×[N]` is exactly 406):

```
MoE 5-kernel block (residual_rms_router → … → routed_shared_down_residual)   72.60 us/layer
attention tail h64 (attn + gate + oproj)                                     58.32 us/layer
rms + qkv h64                                                                46.05 us/layer
sparse h64 layer, total                                                     176.97 us/layer
rms + qkv48 + full_attn                                                      66.76 us/layer
gate48 + oproj48                                                             31.16 us/layer
sparse h48 layer, total                                                     170.52 us/layer
layer-0 dense tail (full_attn + oproj48 + residual_rms + gate_up + down)    455.44 us
lm-head cascade stages 1–4                                                  432.80 us
lm-head sparse refine                                                        76.80 us
embedding RoPE atlas                                                          3.60 us
gather_front + argmax                                                        12.58 us
```

`decode_embedding_rope_atlas_bf16_2048_v2` (3.60 µs) and
`lmhead_exact_fused_int5_sparse_refine_v1` (76.80 µs) are the only two kernels
that occupy a command buffer alone, so those two producer costs are directly
measured; every other producer cost above is a block total obtained by
differencing command-buffer signatures.

## 3.1 Redundancy multiplier R

`R` is the number of times a fused consumer would have to recompute the
producer's output, i.e. the number of consumer threadgroups that read the
*whole* intermediate rather than a private slice. Fusion replaces one producer
dispatch with `R` in-kernel recomputations, so

```
net = gross − producer_cost × (R − 1)
```

Because `gross ≤ 40 × price(4 KiB) ≈ 56 µs/step` for every per-layer row, and
because **no kernel in this model costs less than the measured 4 KiB boundary
price itself**, every row with `R ≥ 41` has `net < 0` without needing a precise
producer cost. That single inequality disqualifies every broadcast row below.

## 3.2 Census, ranked by net

Columns: producer → **named intermediate (bytes)** → consumer | ×/step |
consumer grid (TGs) | whole-or-slice | R (evidence) | producer µs/step | gross
µs/step | **net µs/step** | redundancy-free | occupancy risk.

### Tier 1 — redundancy-free (R = 1); the only fusible rows

| # | producer → **intermediate (bytes)** → consumer | ×/step | consumer TGs | R (evidence) | producer µs | net = gross | occupancy risk |
| --- | --- | ---: | ---: | --- | ---: | ---: | --- |
| C3 | `lmhead_int5_base_coarse_delta_bf16_v1` (`LagunaLmHeadPrune.swift:941-947`) → **`coarse` FP32[100352] = 401,408 B** → `lmhead_coarse_argmax_stage1_v5` (`:957-962`) | 1 | 128 (grid 224×128) | **1** — stage 1 partitions the vocab, each TG reduces a private 784-entry slice | in 432.80 block | `price(401408)` | low: both stages are already grid-partitioned |
| C4 | same producer → **`delta` BF16[100352] = 200,704 B** → same consumer | 1 | 128 | **1** — same partition | in 432.80 block | `price(200704)` | low |
| C8 | `lmhead_exact_fused_int5_sparse_refine_v1` → **`logits` BF16[100352] = 200,704 B** → `argmax_bfloat16` | 1 | reduction grid | **1** — argmax slices the vocab | 76.80 (measured alone) | `price(200704)` | low, but `logits` may be a required probe output |
| A3 | `residual_rms_router_bf16_2048_rpg8_keys_v1` (`:1102`, call `:11036`) → **`summed` BF16[2048] = 4,096 B** → `lagunaRoutedSharedDownResidual` (`:8496-8503`) | 39 | 512 (grid `(2048/4)*288`) | **1** — each TG owns 4 columns = 8 B | 72.60 (block) | `39 × price(4096)` | medium: producer is `rpg8`, consumer is a 288-thread 9-simdgroup kernel; merging changes both geometries |
| A4 | same producer → **`routerLogits` BF16[256] = 512 B** → `prefill_router_tournament_ordinal_norm_active64_v2` (`:10037-10043`) | 39 | **1** | **1** — a single consumer TG | 72.60 (block) | `39 × price(512)` | high: a 1-TG consumer fused into a many-TG producer needs a device-wide sync |
| C1 | last decoder layer output → **hidden BF16[2048] = 4,096 B** → head `rmsbfloat16` (`normalization.cpp:69-80`) | 1 | **1** | **1** | in 432.80 block | `price(4096)` | low |
| B2 | `residual_rms_bf16_2048_v1` (layer 0) → **`summed` BF16[2048] = 4,096 B** → `dense_down_residual_bf16_v1` (`:8687-8692`) | 1 | 128 (grid `(2048/16)*128`) | **1** — 16 columns = 32 B per TG | in 455.44 block | `price(4096)` | low |
| A | `decode_embedding_rope_atlas_bf16_2048_v2` → **hidden BF16[2048] = 4,096 B** → layer-0 `rmsbfloat16` (`:5805`) | 1 | **1** | **1** | 3.60 (measured alone) | `price(4096)` | low |

### Tier 2 — broadcast rows, R ≫ 1, net ≪ 0 (not fusible as written)

| # | producer → **intermediate (bytes)** → consumer | ×/step | consumer TGs = **R** (evidence) | gross µs | net |
| --- | --- | ---: | --- | ---: | --- |
| D1 | `rmsbfloat16` → **`normalized` BF16[2048] = 4,096 B** → `lagunaDecodeNVFP4QKVR1` (`:4857`, call `:5806`) | 40 | **5120** sliding / 4096 full — grid `((rows/2)*64,1,1)`, TG 64, every TG reads the whole row | `40 × price(4096)` | ≤ −7 000 |
| D2 | `rmsbfloat16` → same **4,096 B** → `lagunaGateSoftplus` (`:4380-4400`, call `:5849`) | 40 | **8** (h64) / 6 (h48), grid `((heads/8)*64,1,1)`, whole row per TG | `40 × price(4096)` | ≈ −(7…10) |
| A1 | `residual_rms_router_…` → **`normalized` BF16[2048] = 4,096 B** → routed gate/up QMV R1 (`:7899-7907`) | 39 | **2048** — grid `(8*256*64,1,1)`, TG 64 | `39 × price(4096)` | ≤ −140 000 |
| A2 | same → same **4,096 B** → shared QMV (`:7078-7083`) | 39 | **256** — grid `(tiles*64,1,1)`, tiles = 256 | `39 × price(4096)` | ≤ −18 000 |
| A5 | tournament → **`routerKeys` BF16[512] = 1,024 B** → routed QMV | 39 | **2048** — each TG re-derives top-8 from all 256 keys, `lagunaRouterTop8PrecomputedPrelude` (`:7735-7748`) | `39 × price(1024)` | ≤ −140 000 |
| A8 | routed QMV → **`routedActivated` BF16[1,1,8,1,512] = 8,192 B** → fused tail (`:8496-8503`) | 39 | **512**, fan-in 4:1 | `39 × price(8192)` | ≤ −35 000 |
| A9 | shared QMV → **`sharedActivated` BF16[512] = 1,024 B** → fused tail | 39 | **512** | `39 × price(1024)` | ≤ −35 000 |
| A6/A7 | tournament → **`inds` INT32[8] = 32 B** and **`weights` BF16[8]·f32 = 32 B** → fused tail | 39 | **512** each | small | ≤ −35 000 |
| B1 | `residual_rms_bf16_2048_v1` → **`normalized` BF16[2048] = 4,096 B** → `dense_gate_up_swiglu_bf16_v1` (`:8608-8613`) | 1 | **128** — grid `((8192/64)*512,1,1)` | `price(4096)` | ≤ −180 |
| B3 | `dense_gate_up_swiglu` → **`denseActivated` BF16[8192] = 16,384 B** → `dense_down_residual` | 1 | **128** | `price(16384)` | ≤ −180 |
| C2 | head `rmsbfloat16` → **`normed` BF16[2048] = 4,096 B** → `lmhead_int5_base_coarse_delta_bf16_v1` | 1 | **6272** — grid `((vocab/16)*512,1,1)` | `price(4096)` | ≤ −8 800 |
| C5/C6 | argmax stage 1 → **partials 512 B each** → `lmhead_exact_winner_bf16_midpoint_threshold_v1` (`:964-969`) | 1 each | **1** each, but the producer is a 128-TG grid → fusing needs a device sync | small | n/a |
| C7 | winner threshold → **`thr` FP32[1] = 4 B** → assemble/refine (`:973-986`) | 1 | **3136** — grid `((vocab/32)*256,1,1)`; each TG would have to redo the winner scan | `price(4)` | ≤ −4 400 |
| E | QKV QMV → **`qkv` = 20,480 B (sliding) / 16,384 B (full)** → `lagunaSlidingFusedAttention` (`:1766`) / `lagunaFullFusedAttention` (`:2267`) | 40 | 32/24 TGs but **slice-local** (the one Tier-2 row that is not a broadcast) | `40 × price(≈18000)` | the producer would have to be replicated per attention TG: R = 32/24 |
| F/G | gate (**128 B**/96 B) and attended (**16,384 B**/12,288 B) → `lagunaGatedAffineOProjNVFP4` (`:4441`, call `:6233`) | 40 each | **256** | — | ≤ −18 000 |
| I | full-attention layers only → **params 12 B** | 10 | small | — | — |

### Already fused — do not re-propose

QK-RMSNorm + RoPE/YaRN + KV-write + SDPA (`:1416`, `:1848`); softplus inside the
gate QMV; the gate product inside o_proj; residual + post-norm + router GEMV +
router keys in one kernel (`:1102`, `DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER` L580);
sigmoid + bias + top-8 + cast + renorm in one tournament kernel; routed
gate + up + SwiGLU with in-kernel top-8 re-derivation; shared gate + up + SwiGLU;
routed-down×8 + shared-down + weighting + ×2.5 scaling + residual in one
288-thread kernel; dense gate + up + SiLU and dense down + residual; the lm-head
4-stage cascade; embedding + RoPE (`:11194`); `lagunaLastTokenHidden` is a no-op
at L=1. Attention `mask` is `.none` at decode.

## 3.3 Why the two obvious attention glue boundaries are blocked

`DARKBLOOM_NATIVE_AFFINE_NVFP4_FROM` defaults to `"0"` (`:2903-2909`), so all 40
layers run the NVFP4 g16 QKV bank and `lagunaNormAffineQKV` can never fire.
`foldGateIntoBank` (`:5568-5579`) declines for the same reason, so `g_proj`
keeps its own dispatch. `_fusedQKVWeight` is prefill-only. That leaves exactly
two glue boundaries in attention — C→D1 and C→D2, 80 dispatches per step — and
both are Tier-2 broadcast rows.

One incidental observation from the profile: MLX orders `gate_sp_h48_v1`
*before* `decode_nvfp4_qkv_h48_…` inside one command buffer even though the
Swift call order at `:5806`/`:5849` is the reverse. They are independent
siblings of `normalized`, which is direct evidence that they could share a
single dispatch if the bank layout allowed it.

## 3.4 Byte census and what it rules out

Intermediate bytes written per step:

```
coarse            401,408
routedActivated   319,488  (39 × 8,192)
delta             200,704
logits            200,704
normalized        163,840  (40 × 4,096)
summed            163,840
layer output      163,840
qkv               ~745,000 (40 × ~18,600)
attended          ~633,000
sharedActivated    39,936
routerKeys         39,936
routerLogits       19,968
denseActivated     16,384
```

Against roughly **550 MB/step of dequantised weight traffic**, all decode
intermediates together are under 0.5 %. The programme consequence is blunt:
**further MoE-body fusion buys dispatch count and latency, never bandwidth.**
Only the lm-head cascade (`coarse` + `delta` + `logits` ≈ 803 KB/step) is a
first-order byte term among the redundancy-free rows, and it is still only
about 1 % of the head's own ~128 MB of int5 weight traffic.

This **contradicts pre-registered cross-prediction CP-3**, which predicted the
largest recurring intermediate would sit in the MoE path. It is `coarse`, in
the head. Scored as a miss.
