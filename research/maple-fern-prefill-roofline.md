# Prefill 512-token forward: roofline, dispatch profile, and score decomposition

Student: maple-fern. PR #11. `BASE_SHA = 0d980bb03040182b4595cab070fd249944ea3621`.
Scored surface on this branch is **byte-identical to `BASE_SHA`** (`git diff BASE_SHA -- Sources/ Vendor/` is empty).
Everything here is research-only measurement; no mechanism was shipped.

Host: AWS Apple **M4 Pro**, 20-core GPU, 48 GiB (low-memory startup profile), macOS 26.5.2.

---

## 0. Headline: this host cannot measure prefill mechanisms at all

`mlx::core::metal::is_nax_available()` (`Vendor/mlx-swift/.../backend/metal/device.cpp:913-931`)
requires macOS >= 26.2 **and** GPU arch gen >= 17. Measured on this host:

```
arch=applegpu_g16s gen=16 last=s nax_gen_required=17 nax_available=false
```

The OS gate passes; the **GPU generation gate fails**. So every `_nax` kernel is
unreachable here, and **94.2% of this host's prefill GPU time runs in Metal
functions that the official M5 never executes**. This is a strictly stronger
failure mode than the advisor's "threadgroup re-tiling does not transfer": it is
not the same kernel at a different occupancy, it is a *different kernel*.

| observed pipeline (M4) | ms/fwd | share | M5 runs instead |
| --- | ---: | ---: | --- |
| `nvfp4_gather_qmm_rhs_nt` (bm16/bn32/bk32/wm1/wn2) | 266.65 | 48.5% | `nvfp4_gather_qmm_rhs_expert_static_nax_nt_...bm_64_bn_64_bk_64_wm_4_wn_1` |
| `steel_gemm_fused_nt_bfloat16_bm64_bn64_bk16_wm2_wn2` | 183.37 | 33.4% | `steel_gemm_fused_nax_nt_...` (bm128/bn128/bk512 family) |
| `steel_gemm_splitk_nt` + `_accum` | 33.04 | 6.0% | NAX split-K branch (`matmul.cpp:988`) |
| `steel_attention_bfloat16_bq32_bk16_bd128_wm4_wn1` | 28.23 | 5.1% | `steel_attention_nax` at **bq64/bk32** |
| `nvfp4_qmm_t` | 6.64 | 1.2% | `nvfp4_qmm_t_nax_static_...` |
| **NAX-divergent subtotal** | **517.92** | **94.2%** | |
| `nvfp4_qmm_t_splitk_fused` | 13.56 | 2.5% | same kernel (split-K branch precedes the NAX gate) |
| `laguna_*` custom + elementwise + rms + router + moe_tail + sort/scatter + lm_head | ~18.09 | 3.3% | same kernels |

By contrast the **steady decode step is 100% host-independent**: every dispatch is
a hand-written `laguna_*` kernel (or `rms`/`gather_front`), none behind a NAX or
`#available` gate. The only capability gate anywhere in `Sources/` is
`lagunaExpertAlignedGatherEnabled` (`LagunaRuntimeModel.swift:235-249`), used at
exactly one *prefill* site (`:9631`).

**This asymmetry is the mechanistic explanation for the campaign's track record:**
decode work measured on M4 exercises the same code M5 runs; prefill work does not.

Consequence for `DARKBLOOM_ATTN_QHOIST`, the cheapest candidate I had queued: it
is read at `jit_kernels.cpp:1379`, called only from `get_steel_attention_nax_kernel`
(`:1432`), and its `#if` blocks exist only in `_nax` sources. **It is inert dead
code on this host** — an A/B here would have measured pure noise and reported it as
a result. Separately, even a perfect QHOIST win is bounded: attention core is 5.1%
of prefill, and the header's own projection is a 17.8% loader-traffic cut, so
<= 0.9% of prefill => **<= 0.33% of score**. Killed on both counts.

---

## 1. Roofline, with measured host ceilings

`research/host_flop_ceiling.swift` (new, compile-checked and run on this host):

| ceiling | measured |
| --- | ---: |
| scalar FMA f32 | 7.07 TFLOP/s |
| scalar FMA f16 | 7.59 TFLOP/s |
| **simdgroup MMA bf16** | **28.76 TFLOP/s** |
| simdgroup MMA f16 | 28.96 TFLOP/s |
| DRAM bandwidth (used) | 260.2 GB/s |

My first pass assumed 8 TFLOP/s, which is the *scalar* ceiling; the MMA ceiling is
3.6x higher and is the right denominator for every GEMM here. Analytic budget for
one 512-token forward (`research/prefill_budget.py`, derived from `weights/config.json`):

```
stage                 weightGB   actGB    GFLOP  %FLOP  dramMs   mmaMs  FLOP/B
attn_proj_qkvo           2.862   0.881   1465.3   51.8    14.4    51.0   391.5
routed_experts          17.666   1.799   1005.0   35.5    74.8    34.9    51.6
attn_core                0.000   0.713    161.4    5.7     2.7     5.6   226.3
shared_expert            0.069   0.225    125.6    4.4     1.1     4.4   427.4
dense_mlp_layer0         0.101   0.029     51.5    1.8     0.5     1.8   396.4
router                   0.041   0.092     20.9    0.7     0.5     0.7   157.5
TOTAL                   21.152   5.524   2830.2  100.0   102.5    98.4   106.1
```

Forward intensity **106.1 FLOP/byte** vs machine balance **110.5** => the forward sits
essentially *on* the balance point; DRAM floor 102.5 ms and MMA floor 98.4 ms agree.
Measured 585.6 ms is **5.7x the floor** => 17.5% of bandwidth ceiling, 16.8% of MMA
ceiling.

Per-family achieved efficiency (measured GFLOP / measured ms, vs 28.76 TFLOP/s):

| family | GFLOP | ms | TFLOP/s | % MMA ceiling |
| --- | ---: | ---: | ---: | ---: |
| attn_proj (steel bf16, fused + splitk) | 1465.3 | 216.41 | 6.77 | 23.5% |
| routed gather-GEMM | 1005.0 | 266.65 | 3.77 | **13.1%** |
| attn core | 161.4 | 28.23 | 5.72 | 19.9% |
| nvfp4 dense qmm (shared + dense0 + router) | 198.0 | 20.20 | 9.80 | 34.1% |
| whole forward | 2830.2 | 585.6 | 4.83 | 16.8% |

No top-3 dispatch is anywhere near the advisor's ">80% of regime ceiling" stop
threshold, so the *nominal* headroom is large. It is simply not addressable from
this host.

### Profile method and two validations

`research/prefill_probe.py` drives the worker over NDJSON and attributes GPUPROF
records **per request** (drains worker stderr between synchronous requests, and
prints per-request dispatch counts so an attribution error is visible rather than
silent). Local-only GPUPROF hooks in the vendored `device.cpp/.h` were reverted;
they are not on this branch.

1. **The probe reproduces the scored axis.** Probe cold forward 584.09 ms vs
   harness `--local-iterate` prefill 585.6 ms => **0.26% apart**. The probe's warm
   median is 555.15 ms, so the scored (cold, single, un-warmed) forward carries a
   **5.2% cold-page penalty** that warm iteration hides.
2. **`arangeuint32` is an overlap artifact, not work.** It reports 76 calls x
   1763 us = 134.03 ms for a 4 KB output. Per-request GPU busy *sum* is 683.58 ms
   (123.8% of the 552.06 ms wall) while the *union* is 548.51 ms (99.4%);
   `sum - arange = 549.55 ms`, within **0.19%** of the union. So arange's command
   buffers overlap real work and are non-additive. All shares above use the
   549.55 ms serial-equivalent busy time, not the raw sum.

Also worth recording: union busy is 99.4% of wall, so **prefill has no
dispatch-overhead gap** on this host — it is GPU-throughput-bound, and
command-buffer/host-CPU reduction has nothing to win at prefill.

---

## 2. The seed forward is worth 0.362 of score, not 0.25

Verified against the trusted harness (`Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift:966-1013`,
`LagunaRuntimeWorker.swift:361,383`, `Sources/MLXFastCore/Constants.swift:94,109,123`):

- `decode_seconds_per_token = (one charged 512-token seed forward + 128 one-token steps) / 128`, i.e. `D = S/128 + T`. Seed forward timed **once**, no warmup.
- `prefill_seconds_per_token = (one 512-token forward) / 512`, i.e. `P = S/512`. One cold timed run, `benchmarkPrefillWarmupRuns = 0`.
- The two forwards are the **same computation**: same 512 rows, `positionOffset: 0`, fresh cache, fresh worker process. Only asymmetry is that `decode_begin` additionally force-evals the KV cache.

So reducing the forward by `r` reduces `P` by `r` **and** `D` by `sigma * r`, where
`sigma = (S/128)/D`. With `score = decode_speedup^0.75 * prefill_speedup^0.25`:

```
d ln score / d ln S = -(0.25 + 0.75 * sigma)
d ln score / d ln T = -0.75 * (1 - sigma)          (the two sum to -1)
```

Applying this to the **official M5 numbers** (no M4 extrapolation needed):

| | S (ms) | S/128 (ms) | D (ms) | T (ms) | sigma |
| --- | ---: | ---: | ---: | ---: | ---: |
| M5 baseline (our session) | 193.544 | 1.5121 | 13.8327 | 12.3206 | 10.93% |
| M5 candidate `27b9c7c6` | 98.153 | 0.7668 | 5.1198 | **4.3530** | **14.98%** |
| M5 promoted best `8415f63c` | 97.820 | 0.7642 | 5.1229 | 4.3587 | 14.92% |

Cross-check: `S_base/S = 193.544/98.153 = 1.9718` vs published `prefill_speedup
1.971861`, and `D_base/D = 13.8327/5.1198 = 2.7018` vs published `decode_speedup
2.701815`. The decomposition is exact.

**Therefore, at our current M5 operating point:**

| lever | elasticity of score | per 1% improvement |
| --- | ---: | ---: |
| 512-token seed forward `S` | **0.362** | **0.362% score** |
| steady decode step `T` | **0.638** | 0.638% score |

The advisor's "1% prefill = 0.25% score" understates the forward by **45%**,
because the same forward is charged into the 0.75-weighted decode metric. The
re-weighting *direction* is still right — the steady step is 1.76x more valuable
per percent, not 3x.

Two further decompositions that fall out of this and were not previously visible:

- **Our tree has sped the steady step up far more than the forward.**
  `T: 12.3206 -> 4.3530 = 2.830x` but `S: 193.544 -> 98.153 = 1.972x`. `decode_speedup
  2.702` is the blend of a 2.83x step and a 1.97x forward. The forward is the
  laggard inside the decode metric, which is *why* sigma rose from 10.9% (baseline)
  to 15.0% (candidate): as the step improves, the forward's share of the decode
  metric grows and prefill work becomes progressively *more* valuable, not less.
- **M4 overstates seed-forward value by 39%.** On this host `S = 585.6 ms`,
  `S/128 = 4.575 ms`, `D = 13.629 ms` => `T = 9.054 ms`, `sigma = 33.6%`, elasticity
  **0.502**. That is 1.385x the M5 elasticity of 0.362. Independent validation of the
  `S/128 + T` model: derived `T = 9.054 ms` vs separately measured steady step
  **8.769 ms**, 3.2% apart.
- **`--local-submit` hides seed-forward wins.** It uses 1023 decode steps
  (`Constants.swift:117`), so sigma falls to ~5.9% there. A forward win looks nearly
  invisible in `--local-submit` decode while being 15%-weighted officially. Use
  `--local-iterate` for forward work.

---

## 3. Routing at 512 tokens is heavily skewed, and the shipped tiling was tuned on a uniform assumption

The repo's routed gather-GEMM tuning notes state their run-elision figures were
"**Simulated over uniform routing**" (`quantized.cpp:1405-1415`: 4.92 runs/tile,
40.5%/60.7% elision). Nothing in `Sources/`, `Vendor/`, `research/` or `docs/` had
ever measured the real spread. I measured it with a temporary default-off
diagnostic (`DARKBLOOM_ROUTE_HISTOGRAM`, committed as `ceff917` and reverted in the
next commit so the scored surface stays byte-identical; re-apply from that commit
if needed). Raw data: `research/prefill-512-route-histogram.txt` (76 records = 2
real forwards x 38 MoE layers; the worker's all-BOS warmup forward is degenerate —
`zero=248, max=512` — and is dropped). Analysis: `research/route_histogram.py`.

**Routing is a property of the model and prompt, not the GPU, so these numbers are
host-independent and transfer to M5.**

```
rows=512 experts=256 assignments/layer=4096 mean rows/expert=16.00

pooled rows-per-expert (76 layer instances)
  mean    16.00    stdev   28.77          <- CV = 1.80, nothing like uniform
  zero-row experts  20.3%   max 505
  p10 0   p25 1   p50 7   p75 19   p90 39   p95 58   p99 142
  busiest 8   experts hold 26.0% of a layer's assignments
  busiest 32  experts hold 54.7%
  busiest 64  experts hold 74.5%

load imbalance per layer: mean per-layer max 243.1 rows vs mean 16.0 => 15.2x
```

Converted into the two costs the M5 expert-aligned kernel actually pays. The
shipped default is variant 5 (`bm=64, wm=4, wn=1` => **SM = 16** rows per simdgroup,
`quantized.cpp:1472-1478`; only `""`/`"4"`/`"5"` are accepted by
`lagunaExpertAlignedStageEnabled`, `LagunaRuntimeModel.swift:231-233`):

```
issued-vs-useful MMA rows by simdgroup row granularity SM
   SM   issued/useful   wasted
    8           1.20x    16.5%
   16           1.46x    31.3%   <- shipped
   32           2.06x    51.4%
   64           3.45x    71.0%

per-expert threadgroup launches by row-tile BM (grid.y = egroups = 256 always)
   BM   chunks/layer   idle TGs   busiest expert
   16          372.6       51.9            15.7
   32          263.2       51.9             8.1
   64          220.5       51.9             4.3   <- shipped
  128          207.9       51.9             2.4
```

Three findings, and one of them **kills the mechanism the assignment named**:

1. **31.3% of issued MMA rows at the shipped SM=16 are padding.** The median expert
   holds 7 rows but MMA is issued in 16-row fragments. Dropping to SM=8 (the Apple
   `simdgroup_matrix` 8x8 floor) would cut padding to 16.5%, recovering ~15pp of
   issued MMA work.
2. **Bigger row tiles buy essentially nothing.** Chunks/layer only falls 220.5 ->
   207.9 (**-5.7%**) going from BM=64 to BM=128, because the median expert holds 7
   rows and 80% of experts need exactly one chunk regardless of BM. Weight staging
   is ~one full BN x BK tile per non-empty expert per N-tile whatever BM is. So the
   "match the MoE gather-GEMM tiling to the ~16-row histogram" mechanism in my
   assignment is **the wrong lever** — the lever is *smaller SM*, not *bigger BM*.
   I am reporting this instead of implementing it.
3. **20.3% of expert threadgroup columns are launched for zero rows** (51.9 of 256
   per layer), since `grid.y = egroups = 256` unconditionally. That is a pure launch
   + early-exit cost that a routing-aware grid could skip.

Caveat I want on the record: the M5 expert kernel stages the full BN x BK weight
tile with all 128 threads while only `ceil(rows/16)` of 4 simdgroups do MMA
(`fp_quantized_nax.h:1781-1783, 1854-1858`). So variant 5's padding cost has
already been *moved* from MMA into staging. If that kernel is staging-bound rather
than MMA-bound on M5, cutting SM to 8 recovers less than the 15pp above. I cannot
distinguish those two regimes from this host, and I am not going to guess.

---

## 4. Mechanism classification against the advisor's transfer taxonomy

| candidate | bucket | verdict |
| --- | --- | --- |
| SM 16 -> 8 in the expert-aligned gather-GEMM | **A** (reduces issued MMA work) — but partly B, since it also re-partitions simdgroups | best remaining prefill lever; needs M5 to measure; needs a new variant in the C++ table *and* the Swift accept-list *and* the expert gate (`bm==64 && wm==4`) |
| Routing-aware grid skipping the 20.3% empty experts | **A** (removes launches + staging) | clean, small, host-independent motivation; needs M5 |
| Bigger BM (128) for the routed gather-GEMM | — | **killed by data**: -5.7% chunks |
| `DARKBLOOM_STAGE_BM128` 4 vs 5 (wn2 vs wn1) | **B** (pure simdgroup re-partition) | will not transfer; also unmeasurable here |
| `DARKBLOOM_ATTN_QHOIST` | **B** | killed twice: <=0.33% of score, and NAX-only dead code on M4 |
| `GEMM_TPARAM_MACRO` medium-device tile retune | — | M4-only code path; **cannot** affect M5 by construction |
| Caching the 76 `arangeuint32` dispatches | **A** (input-independent, so permitted) | killed by data: fully overlapped, ~0 ms |
| Command-buffer / host-CPU reduction at prefill | **A** | killed by data: union busy is 99.4% of wall, no gap to reclaim |

---

## 5. What I recommend

1. **Do not run prefill kernel experiments on an M4 host.** 94.2% of prefill GPU
   time is in kernels M5 never runs. This is worth putting in `AGENTS.md`.
2. **Re-weight using 0.362, not 0.25**, for any change to the 512-token forward,
   and note that sigma *grows* as the steady step improves — the forward becomes
   more valuable over time, and is currently the laggard (1.97x vs 2.83x).
3. **The two prefill mechanisms worth an M5 slot** are SM=8 and the routing-aware
   grid, in that order, both justified by the measured histogram.
4. **Highest-value next measurement overall is still on decode** (elasticity 0.638,
   and M4 runs the same kernels). The one number I could not get is the
   non-GPU-busy fraction of a steady decode step: split-mode instrumentation
   inflates it (split wall 10.408 ms and union busy 8.997 ms both exceed the
   8.769 ms non-split wall), so it needs a non-split profile. That is
   `research/decode_probe.py` territory and overlaps nezuko's arm.

## Files

Research-only, all off the submission surface:

- `research/host_flop_ceiling.swift` — measured FMA/MMA/bandwidth ceilings.
- `research/prefill_budget.py` — analytic FLOP/byte budget from `weights/config.json`.
- `research/prefill_probe.py` — per-request GPUPROF driver and analyzer.
- `research/route_histogram.py` — histogram -> MMA-padding / TG-launch cost model.
- `research/prefill-512-route-histogram.txt` — raw per-layer expert counts.
- `research/maple-fern-prefill-roofline.md` — this report.
