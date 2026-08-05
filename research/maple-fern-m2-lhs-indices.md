# M2 — elide the routed-prefill row gather via `lhs_indices` on the sorted gather-GEMM

Student: maple-fern. PR #63. Assignment
`maple-2026-08-05h-lhs-indices-gather-elision`, revision `r1`.
Base branch `codex/mlxfast-maple-20260804-advisor`,
`BASE_SHA 929b5c439b41675c35d38ede227fd58220c40513`.

**This assignment has no W&B runs and no ranked `mlxfast` receipts.** The receipt
budget was zero (frieren holds the ranked channel), and there is no training
process to log. The entire evidence channel is this document plus
`research/maple-fern-m2-prereg.md` and the commits on
`maple-fern/lhs-indices-gather-elision`.

Host for every measurement below: AWS **Apple M4 Pro**, 20-core GPU, 48 GiB,
macOS 26.5.2, `arch=applegpu_g16s`, Apple GPU **generation 16** — therefore
`_nax` kernels are unreachable here. Low-memory startup profile active.

---

## 0. The hypothesis, and what it is made of

`gatherSort` materialises a sorted copy of the routed activations so the
sorted-rhs gather-GEMM can read expert-contiguous rows sequentially. For a
512-token prefill that copy is 4,096 rows x 4 kB = **16 MiB per routed layer**,
read from a 2 MiB source. MLX's `gather_qmm` already accepts `lhs_indices`, so
in principle the GEMM could read the *unsorted* 2 MiB activation through the
permutation and the copy could be deleted outright.

M2 therefore has two halves, and they must be priced separately:

- **half (a)** — the gather kernel itself disappears: 2 MiB read + 16 MiB write
  = **18 MiB/layer** of traffic removed.
- **half (b)** — the GEMM's activation read changes from a sequential 16 MiB
  stream to a permuted 2 MiB gather. In byte terms that looks like a further
  14 MiB/layer saved. **In behaviour it may cost**, because contiguous rows may
  be exactly why the block sustains its measured 408.4 GB/s
  (`research/CURRENT_RESEARCH_STATE.md:1909`). This sign risk was flagged in
  advance at `research/CURRENT_RESEARCH_STATE.md:1114-1118`.

Byte-budget arithmetic for the full mechanism (39 routed layers, `hiddenSize`
2048, 40 decoder layers with `mlp_only_layers=[0]`): 18 + 16 - 2 = 32 MiB/layer
x 39 = 1,248 MiB = **1.309 GB**. At the 651.8 GB/s reference rate that is
2.008 ms -> **+0.745 %**; at the in-situ 408.4 GB/s it is 3.205 ms ->
**+1.19 %**. Central **+0.95 %** — an **upper bound, not a forecast**.

This item was queued as #1 / rank 4
(`research/CURRENT_RESEARCH_STATE.md:1068-1118`, `:3450`) and had previously
been banked at **+0.4-0.5 %**, one of the "6 of 8 audited prices wrong" entries
(`:1046-1057`).

**Decode is out of scope by construction.** `SwitchGLU` sets
`doSort = indices.size >= 64` (`SwitchLayers.swift:484`); a one-token decode
step has `indices.size = 8`, so no sort and no gather happens. M2 is a
**prefill-only** mechanism, and prefill carries 25 % of the score weight.

---

## 1. Step 0 — branch reachability census (HARD STOP; did not fire)

The whole idea presupposes that the routed prefill GEMM actually enters the
`gather_qmm_rhs` branch of `GatherQMM::eval_gpu`
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp:2190-2285`).
That branch is the *only* one of the four that is passed `rhs_indices` and never
`lhs_indices`, so it is the only one where the elision is even a question.

Instrumentation was added as throwaway commit `f35291b` and hard-reset
afterwards. Worker build (57.85 s):

```
mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
```

Run (`run_training` id `1db39d4c-8656-41fe-b333-53b9ab38670c`, exit 0, 43.676 s):

```
/usr/bin/env DARKBLOOM_CENSUS_GQMM=1 python3 research/prefill_probe.py \
  --reps 1 --stderr /tmp/census.worker.err
```

```
prompt tokens: 512
load: 42.9 s
prefill 0: 546.96 ms (1068.28 us/token)
token=5991
peak_ram_gb 20.715
prefill warm median: 546.959 ms/forward
```

Census, 228 `GQMMCENSUS` lines, deduplicated with counts:

```
76 branch=gather_qmm_rhs M=1 B=4096 E=256 N=1024 K=2048 right_sorted=1 transpose=1 \
   vector_limit=18 mode=nvfp4 gs=16 bits=4 lhs_idx_size=4096 rhs_idx_size=4096
76 branch=gather_qmm_rhs M=1 B=4096 E=256 N=2048 K=512  right_sorted=1 transpose=1 \
   vector_limit=18 mode=nvfp4 gs=16 bits=4 lhs_idx_size=4096 rhs_idx_size=4096
76 swift site=9682 alignedGatherEnabled=false doSort=true arch=applegpu_g16s \
   sortedXShape=[4096, 1, 2048] gateUpShape=[4096, 1, 1024]
```

Findings:

1. **`gather_qmm_rhs` is the selected branch** for both the fused gate/up GEMM
   (`K=2048, N=1024`) and the down GEMM (`K=512, N=2048`). The Step 0 hard stop
   does not fire.
2. `alignedGatherEnabled=false` — as expected on generation 16. The
   expert-aligned `_nax` path needs `generation >= 17`
   (`LagunaRuntimeModel.swift:235-249`), so site `:9682` takes the
   `lagunaInterleavedSwiGLU` else-branch here and the aligned branch on M5.
3. **`lhs_idx_size=4096`.** A broadcast/synthesised lhs index array already
   arrives at `eval_gpu` even though the runtime passes `lhsIndices: nil`. This
   is `broadcast_with_indices` (`quantized.cpp:1616-1625`, with the comment at
   `:1612-1615` reading "If we are here that means lhs_indices were not
   provided..."). For our shape `4096 == 4096`, so it is a **pure no-op
   pass-through**.
4. **Landmine, recorded for whoever implements this.** `gather_qmm_rhs`
   (`:1943`) and `gather_qmm_rhs_nax` (`:1593-1700`) accept **only**
   `rhs_indices`; the sorted-rhs kernel has no `lhs_indices` parameter at all.
   The only `lhs_indices`-aware NAX kernels are the *vector* ones
   (`kernels/fp_quantized_nax.h:833-834`, `x_idx = lhs_indices[...]` at `:853`
   and `:858`, wrappers at `:1076-1077` and `:1141-1142`). So passing a non-nil
   `lhsIndices` **today** does not select a permuted read — it silently reads
   4,096 rows out of a 512-row array. Any implementation must guarantee that
   `gather_qmm_rhs` is never selected while a non-nil `lhsIndices` is dropped.

### 1a. The layer multiplier: 38 observed, 39 correct

76 swift-site lines = 38 per forward x 2 forwards, but `weights/config.json`
(`mlp_layer_types`) gives **39** sparse/routed decoder layers. Static analysis of
the guard at `LagunaRuntimeModel.swift:10078-10105` and of
`prepareFusedRoutedGateUp` (`:9740-9815`) found **no per-layer
differentiator**, and prior work measured the fused kernel across all 39
(`research/maple-fern-pr40-result.md:601`,
`research/CURRENT_RESEARCH_STATE.md:3496`), so the "38" is most likely an
instrumentation artefact rather than a real layer that skips the path.

It is moot for the multiplier either way: `SwitchGLU.callAsFunction`
(`SwitchLayers.swift:481-528`) computes `doSort = indices.size >= 64` at `:484`
and calls `gatherSort` at `:490` whenever true — identically whether the layer
is reached through the `switchMLP` fallback or through
`lagunaFusedSortedRoutedGateUp`, which calls the *same* `gatherSort` at
`LagunaRuntimeModel.swift:9655`. With `inds.size = 4096 >= 64` in prefill, **all
39 sparse layers produce the 16 MiB sorted copy on every path**. Multiplier
**39** is used throughout.

### 1b. Only half (a) is measurable on this host — and that is by design

Worth stating plainly, because it bounds what any Step 2 on an M4 could ever
prove:

- **half (a) is M4-legal.** The row gather is a plain MLX gather kernel, not a
  `_nax` kernel (Law 0.9.10 and its corollary). Its cost and its removal are
  therefore measurable on generation-16 hardware.
- **half (b) is not M4-legal.** It lives inside the sorted-rhs quantized GEMM,
  and the ranked M5 selects `gather_qmm_rhs_nax` (`quantized.cpp:1961`) while
  this host selects the non-nax `nvfp4_gather_qmm_rhs_nt` with
  `bm=16, bn=32, bk=32, wm=1, wn=2` (`:2018`). Those have different loaders,
  different tile shapes and different sensitivity to activation locality.
  `AGENTS.md` is explicit: an M4 prefill result is not evidence for a `_nax`
  change. My own roofline puts NAX-divergent kernels at **94.2 %** of prefill
  (`research/maple-fern-prefill-roofline.md`, 517.92 of 549.55 ms).

This is why the assignment made Step 1 a *pricing* gate using a kernel-family-
independent memory-movement probe rather than a harness A/B: the question "is
there 1 ms of M5 prefill in this at all?" can be answered on an M4, whereas
"does the permuted `_nax` GEMM read as fast as the sequential one?" cannot be.

It also adds a third, independent reason not to trust the standalone probe's
`half_b`: even a *good* M4 emulation of half (b) would be emulating the wrong
kernel family.

---

## 2. Step 1 — standalone probe (pre-registered, then largely invalidated)

Pre-registration and the full decision table are in
`research/maple-fern-m2-prereg.md` §1-§5, committed as `8ab8327` **before** the
timing run. Probe source `research/maple_fern_m2_gather_probe.swift`, built
with `xcrun swiftc -O ... -framework Metal -framework Foundation -o /tmp/m2probe`.

Raw results and the three reasons they cannot carry the decision are recorded in
prereg §6.1-§6.2. In summary:

- Regime A (18.0 MiB working set): `half_a = 188.17 us/layer`,
  `half_b = -4.25 us/layer`, combined M4 7.173 ms -> **M5 2.862 ms -> +1.062 %**.
- Regime B (144.0 MiB): `half_a = 168.03 us/layer`, `half_b = -29.00 us/layer`,
  combined M4 5.422 ms -> **M5 2.163 ms -> +0.803 %**. **D1 fired**
  (`t_seq` spread 1.314 > 1.20).

Three problems, all recorded before the follow-up run:

1. **`half_b` is negative in both regimes.** The permuted 2 MiB read costs more
   than the sequential 16 MiB read despite touching 8x fewer unique bytes. The
   pre-flagged sign risk is real: **half (b) of M2 costs.**
2. **My own D1 noise gate fired on regime B**, which had been designed as the
   *more* favourable regime and came back *less* favourable. §3 of my prereg
   says D1 is evaluated on every regime and any noisy arm kills the
   measurement, while §3 also says the decision uses the larger
   `converted_M5_ms` — which points at regime A. That is a real defect in my own
   pre-registration and I am reporting it rather than silently taking the
   convenient branch.
3. **The probe is not bandwidth-resolving.** All three arms land at
   100-137 GB/s against a measured M4 DRAM ceiling of 260.2 GB/s
   (`CURRENT_RESEARCH_STATE.md:3086`). 16 MiB at 260 GB/s is ~64 us, not 163 us.
   One `uint4` per thread across 4,096 threadgroups per layer makes these
   kernels load-issue/launch bound, not byte bound. So (a) `t_seq` and `t_perm`
   are forced within 2.6 % of each other by construction and the probe **cannot
   resolve half_b at all**, and (b) my §1 claim that `t_gather` is a *lower
   bound* on the real MLX gather is **wrong in sign** — the emulation carries
   fixed per-thread overhead the real kernel does not, so 188 us/layer is more
   likely an over-estimate.

Independent cross-check that the probe over-prices half (a): PR #11's roofline
(`research/maple-fern-prefill-roofline.md:35`) puts the *entire*
`laguna_*` + elementwise + rms + router + moe_tail + sort/scatter + lm_head
bucket at **18.09 ms of 549.55 ms** serial-equivalent M4 busy. A 7.33 ms
half_a would be 40.5 % of that whole bucket for the row gather alone. A
DRAM-bound estimate instead gives 39 x ~69 us = 2.69 ms M4 -> x0.399 =
**1.07 ms M5 -> +0.40 %**, straddling the 1.0 ms bar from below.

Conclusion: the standalone probe cannot decide this. Step 1b prices the **real**
kernel in situ.

---

## 3. Step 1b — in-situ additive duplication of the real gather

Pre-registered in prereg §6.3-§6.4, committed as `cee5b73` **before** the run.

<!-- STEP1B_RESULTS -->

---

## 4. Verdict

<!-- VERDICT -->
