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

### 3.1 Method

The standalone probe (§2) failed because it emulated the gather at 100-137 GB/s
on a 260.2 GB/s host, so it was launch-bound, not bandwidth-bound, and could not
resolve `t_seq` from `t_perm`. Step 1b abandons emulation and prices the **real**
kernel by additive duplication inside the real forward pass.

A throwaway env-gated instrument was added to
`Sources/MLXFastTransform/.../SwitchLayers.swift` (committed as throwaway
`fe47706`, since hard-reset; the tree does not carry it):

- file-level `private let m2GatherDup = Int(ProcessInfo...["DARKBLOOM_M2_GATHER_DUP"] ?? "") ?? 1`
- `private func m2DupProbe(_ flat: MLXArray, _ rows: MLXArray, _ tag: String)`
  which builds `N` **discarded** copies of `flat[rows]`, calls
  `MLX.eval(junk)` on the collection
  (`Vendor/mlx-swift/Source/MLX/Transforms+Eval.swift:32`) and emits one stderr
  line `M2DUP branch=... n=... rows=... flat=...`
- called from **both** `gatherSort` branches (fused and unfused) so the probe
  cannot silently miss the taken path.

`N = 1` reproduces the shipped work exactly (one gather). `N = 9` and `N = 17`
add 8 and 16 extra gathers per site. The slope in `N` is the marginal cost of one
gather per forward, `g_M4`, with all fixed cost (weights, MMA, attention, host
overhead) differenced out.

Value-neutrality and drift controls, both required by prereg §6.4:

- every arm must emit `token=5991`, identical to the uninstrumented Step 0 run,
  so the instrument provably does not change the computation;
- the `N = 1` arm is run **twice**, first and last, so thermal drift over the
  four-arm sequence is measured rather than assumed.

Standing pre-measurement inject check, verbatim:

```text
11046:            "DARKBLOOM_INJECT_DECODE_EMPTY", 0)
11058:            "DARKBLOOM_INJECT_EMPTY_TG", 160)
```

Both at their defaults (`0`, `160`). Build clean in 58.87 s.

Command (`run_training` id `30edd4d2-f765-4a92-aa5f-9056f0784bae`, exit 0):

```bash
/bin/sh -c 'for n in 1 9 17 1; do
  echo "=== DUP=$n ==="
  DARKBLOOM_M2_GATHER_DUP=$n python3 research/prefill_probe.py \
      --reps 5 --stderr /tmp/m2dup.$n.err 2>&1
done; for n in 1 9 17; do echo "--- stderr $n ---"; \
  grep -c M2DUP /tmp/m2dup.$n.err; grep -m1 M2DUP /tmp/m2dup.$n.err; done'
```

### 3.2 Results

| arm | warm median (ms/forward) | per-rep warm min / max | spread | `peak_ram_gb` | token |
|---|---|---|---|---|---|
| N=1        | **554.710** | 553.36 / 554.95 | 1.00287 (1.59 ms) | 20.712 | 5991 |
| N=9        | **579.319** | 578.97 / 579.37 | 1.00069 (0.40 ms) | 20.712 | 5991 |
| N=17       | **604.823** | 604.59 / 604.92 | 1.00055 (0.33 ms) | 20.712 | 5991 |
| N=1 repeat | **554.794** | 554.66 / 555.36 | 1.00126 (0.70 ms) | 20.711 | 5991 |

`M2DUP` stderr count = **228 lines in every arm** (= 6 forwards x 38 sites,
matching the Step 0 census exactly), all `branch=fused`, first line
`M2DUP branch=fused n=9 rows=4096 flat=[512, 1, 2048]`. Every arm returns the
same greedy token as the uninstrumented Step 0 run, so the instrument is
value-neutral.

### 3.3 Derived quantities

Marginal cost of one extra gather per forward:

| interval | arithmetic | ms/forward |
|---|---|---|
| N=9 - N=1   | 24.609 / 8  | 3.076 |
| N=17 - N=9  | 25.504 / 8  | 3.188 |
| N=17 - N=1  | 50.113 / 16 | 3.132 |

OLS slope over `N in {1, 9, 17}`: **`g_M4` = 3.1321 ms/forward**. The two
8-gather increments agree within 3.6 %, so the response is linear and MLX is
**not** common-subexpression-eliminating the duplicate gathers - they are real
work, which is the load-bearing assumption of the whole method.

Thermal-drift control: N=1 repeat 554.794 vs N=1 first 554.710, i.e. **+0.084 ms
= +0.015 %**, roughly 300x smaller than the 24.6 ms signal. Drift is not a
confound here.

Bandwidth sanity check, which is the reason to trust this number over §2:

- per sparse layer: 3.1321 / 38 = **82.4 us**
- traffic per layer: 4096 x 2048 x 2 B = 16.777 MB written, plus the ~2.1 MB of
  distinct source rows read = **~18.87 MB**
- implied rate: 18.87 MB / 82.4 us = **229 GB/s = 88 % of the 260.2 GB/s M4
  ceiling**

So the real gather kernel *is* bandwidth-bound, unlike my 100 GB/s standalone
emulation. Independently: 38 x 18.87 MB = 717 MB / 260.2 GB/s = **2.756 ms
predicted** vs 3.132 ms measured, agreement within 13.6 %. The byte model in §0
is validated; the standalone probe in §2 is what was broken.

### 3.4 Pre-registered gate verdicts

| gate | rule (prereg §6.4) | value | verdict |
|---|---|---|---|
| **D1'** | every arm spread <= 1.05 AND delta >= 10x the N=1 absolute spread | max spread 1.00287; 24.609 >= 10 x 1.59 = 15.9 | **clear** |
| **D5**  | `g_M4` <= 18.09 ms (the entire non-NAX-divergent kernel budget from the roofline) | 3.132 | **clear** |
| **D3'** | GO iff `g_M4 x 0.399 >= 1.0 ms` M5 | 3.1321 x 0.399 = **1.2497 ms** | **GO**, margin 25 % |
| **D6**  | honesty flag if GO is only reachable with `half_b_M5 = 0` | GO does require `half_b = 0` | **FIRES** |

Score conversion at the pinned prefill exchange rate `1 ms = 0.371 %`:
1.2497 ms -> **+0.4636 %**.

D6 matters. `g_M4` prices **half (a)** only: the cost of *producing* the
16 MiB/layer permuted activation copy. It says nothing about **half (b)**, the
cost the sorted gather-GEMM would then pay to read its rows through an index
vector instead of contiguously. Both standalone regimes in §2 measured half (b)
**negative** (regime A -4.25 us/layer, regime B -29.00 us/layer), i.e. the
indexed read looked *cheaper* than the contiguous one, which is physically
implausible and is exactly the sign risk pre-flagged at
`research/CURRENT_RESEARCH_STATE.md:1114-1118`. Taking half (b) = 0 is therefore
the **most optimistic admissible** assumption, and `g_M4 x 0.399` is a
**serial-equivalent upper bound**: the `MLX.eval` barrier serialises the junk
gathers, the same sum-vs-union non-additivity that made the 76 `arangeuint32`
dispatches worth 134 ms of "busy" time and 0 ms of wall time in
`research/maple-fern-prefill-roofline.md:296`. At 88 % of the DRAM ceiling there
is little overlap headroom left, so the bound is probably tight - but it is an
upper bound, not an expected value.

Sensitivity, using the §2 half (b) estimates instead of zero:

| half (b) assumption | combined M5 | score delta |
|---|---|---|
| 0 (most optimistic admissible) | 1.250 ms | **+0.464 %** |
| regime A, -4.25 us/layer | 1.184 ms | +0.439 % |
| regime B, -29.00 us/layer (inadmissible, D1 fired) | 0.79 ms | STOP |

And the most generous conversion factor anyone could defend - `260.2 / 610`
= 0.4266, using the measured M5 streaming ceiling rather than the 0.399 in the
ledger - still only gives 1.336 ms -> **+0.496 %**.

---

## 4. Verdict

**STOP before Step 2 implementation. M2 as scoped is a completed, quantitative
negative. Queued idea #1 should be closed at this framing.**

Three independent reasons, any one of which is sufficient.

### 4.1 The price fails the merge bar even at its upper bound

The measured marginal cost of the routed-prefill row gather is
`g_M4` = **3.1321 ms/forward**, converting to **1.2497 ms** on M5 and
**+0.4636 %** score. The advisor's merge bar is **0.61 %**.

This is not a near miss that a better implementation could close, because
+0.4636 % is an **upper bound on the whole mechanism**, not an estimate of one
implementation:

- it assumes half (b) = 0, when both standalone regimes measured it negative;
- it assumes perfect elision, i.e. the gather cost goes to exactly zero rather
  than being folded into a more expensive indexed load in the GEMM;
- it is serial-equivalent, so any overlap the gather currently enjoys with
  neighbouring work makes the real saving smaller, never larger;
- the most generous defensible conversion factor (0.4266, from the measured
  610 GB/s M5 streaming ceiling) still only reaches **+0.496 %**.

The mechanism cannot reach 0.61 % on prefill alone, and it is prefill-only:
decode takes `doSort = indices.size >= 64` false at `indices.size = 8`, so the
gather does not exist on the 75 %-weighted axis (§1, Step 0 census).

This also corrects the ledger. M2 was banked at "+0.4-0.5 %"
(`research/CURRENT_RESEARCH_STATE.md:1068-1118`, queued #1, rank 4) as part of
the batch flagged at `:1046-1057` as "6 of 8 audited prices wrong". The banked
magnitude turns out coincidentally right and **wrong in kind**: it was recorded
as an expected value and is in fact a ceiling. The distinction is the whole
decision.

### 4.2 The ranked code path is outside the submission surface

Even if the price cleared the bar, the change is not shippable as scoped.

`Vendor/mlx-swift/.../metal/quantized.cpp:1959-1961` routes **all** NT
sorted-rhs gather-QMM to `gather_qmm_rhs_nax` whenever
`metal::is_nax_available() && transpose && (env::enable_tf32() || x_.dtype() != float32)`.
On the ranked M5 (bf16, `transpose = true`, `_nax` available per `AGENTS.md`)
that predicate is always true. So there are two kernel families and only one of
them is ranked:

| family | header | shipped on M5? | can accept a new `lhs_indices` row loader? |
|---|---|---|---|
| **A** `fp_gather_qmm_rhs` | `kernels/fp_quantized.h:1994` (editable) | **no** - always bypassed by `:1959-1961` | **yes**, cheaply |
| **B** `fp_gather_qmm_rhs_nax` | `kernels/fp_quantized_nax.h:1194` (editable) | **yes** | **no** - requires a non-editable header |

Family A stages activations through
`mlx::steel::BlockLoader` in `threadgroup` memory
(`fp_quantized.h:2023-2024`, `:2035`), and at the shipped geometry
(BM=16, BK=32, tgp=64 -> TROWS=16=BROWS -> one row per thread, `reduction_dim=1`
so `next()` advances columns only) the **entire** row addressing is the single
`x += y_row_long * K;` at `:2063`. One `lhs_indices[y_row + bi]` lookup in a new
loader constructor is enough; `load_unsafe`/`load_safe` bodies copy verbatim;
`quantized_utils.h` needs zero edits because `gemm_loop_aligned/unaligned/finalize`
are generic over `loader_a_t`; and function-constant id **203 is free**
(`fp_quantized.h:9-11` uses 200/201/202), so a `has_lhs_indices` function
constant plus one appended buffer avoids touching `jit_kernels.cpp:962-973`,
`kernels.h:281`, or the kname/template-arg list. Roughly 10-14 sites,
low-to-medium risk. **And provably dead code on the ranked host.**

Family B is the one that runs, and it does not use a threadgroup loader at all.
It loads x **directly into registers** (all line numbers verified in this tree):

```text
fp_quantized_nax.h:1272   x += y_row_long * K;
fp_quantized_nax.h:1364   const device T* xn = x + tm * K;
fp_quantized_nax.h:1408   NAXTile<T, TM, TK> Atile;
fp_quantized_nax.h:1414     Atile.load(xn + kk1, K);
fp_quantized_nax.h:1416     Atile.load_safe(xn + kk1, K, short2(SK, sgp_sm));
fp_quantized_nax.h:1458   NAXTile<T, TM, TK> Atile;      (pipelined variant)
fp_quantized_nax.h:1464     Atile.load_safe(xn + kk1, K, short2(psk, sgp_sm));
```

So the row identity is baked into a raw `const device T*` and consumed by the
NAX fragment loaders. A gathered variant needs a per-row indexed loader in
`NAXTile::load_safe` (`nax.h:891` -> `NAXFrag_t::load_safe` `:894`, frag body
`:257`), and/or `load_contig` (frag `:106`, tile `:843`) and `load_rows_contig`
(frag `:138`, tile `:814`), with `struct NAXTile` itself at `nax.h:638`. Every
one of those lives in:

```text
Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/steel/gemm/nax.h
```

A direct query against `benchmark.json` (97 `editablePaths`) returns **0 hits**
for `steel/gemm/nax.h` (same for `steel/gemm/loader.h`), while
`fp_quantized_nax.h`, `fp_quantized.h`, `metal/quantized.cpp` and
`mlx-generated/gemm_nax.cpp` each return exactly 1. So the generated twin
`gemm_nax.cpp` *is* editable while its header is not - but editing a twin
without its header is precisely the header/twin drift `AGENTS.md` forbids, and
would leave the AOT metallib and the runtime-compiled copy disagreeing.

There is also no prior art to copy: every existing `lhs_indices` use in this
tree (`fp_quantized.h:1150/1170/1175`, `fp_quantized_nax.h:833/853/858`,
`steel_gemm_gather.h:254/298/301`) selects *which matrix* in a batch, never a
row. No per-row gathered activation loader exists anywhere in the vendored MLX.

### 4.3 Cost to complete does not fit the budget

Doing both families is ~25-35 edit sites at medium-to-high risk, plus the
mandatory Step 3 certification (a `--local-submit` pass on the candidate, a
matched pass on the unchanged base, and a deliberate incoherent-fault power
control), i.e. three full benchmark runs. That is not deliverable in the
remaining budget, and it would be spent on a mechanism already known to be
capped below the bar.

### 4.4 What is now known that was not before

1. `g_M4` = 3.1321 ms/forward, +-3.6 %, thermally controlled at 0.015 % drift,
   value-neutral (`token=5991` in all arms), and cross-validated to 13.6 % by an
   independent byte model. The routed-prefill row gather runs at **229 GB/s,
   88 % of the M4 DRAM ceiling** - it is bandwidth-bound, so there is no
   "the kernel is inefficient, tune it" story hiding here. It costs what its
   bytes cost.
2. The gather appears **38 times per forward**, not 39. `weights/config.json`
   `mlp_layer_types` lists 39 sparse layers; one does not reach
   `lagunaFusedSortedRoutedGateUp`. Confirmed twice independently (76 census
   lines at `--reps 1` = 2 forwards; 228 at `--reps 5` = 6 forwards) and a third
   time by the `M2DUP` line count. Only `gate_up` gathers; `downProj` consumes
   the already-sorted `activated`.
3. The `lhs_idx_size=4096` visible in the census is the **identity
   `arange(4096)`** that `MLX.gatherQuantizedMM` synthesises when `lhsIndices`
   is nil. That is the source of the 76 `arangeuint32` dispatches in
   `research/maple-fern-prefill-roofline.md`, closing a loose end from that
   report.
4. Standalone Metal micro-benchmarks of a memory-bound MLX op are **not a valid
   instrument on this host** unless they are shown to reach a comparable
   fraction of the DRAM ceiling. §2's probe ran at 100-137 GB/s (1 uint4/thread
   x 4096 threadgroups -> launch-bound), which forced `t_seq` and `t_perm` to
   agree within 2.6 % *by construction* and produced a physically impossible
   negative half (b). In-situ additive duplication of the real op cost one GPU
   run and gave a bandwidth-consistent answer. This is a reusable methodology
   result, and it invalidates §1's claim that `t_gather` is a lower bound - it
   over-estimates.
5. `steel/gemm/nax.h` being outside `editablePaths` is a **structural boundary
   on a whole class of ideas**, not just this one: any optimisation that needs to
   change how the ranked `_nax` GEMMs *address or load their activation
   fragments* is unshippable. Ideas that change what is *in* the fragments, or
   the host-side dispatch around them, remain open. Worth recording in the
   ledger next to the `steel/attn` boundary.

### 4.5 Disposition

- Close queued idea **#1** at this framing. Do not re-price it; the ceiling is
  measured.
- A future re-open needs a *different* mechanism, not a better implementation:
  something that removes the 16 MiB/layer write without needing the ranked
  `_nax` GEMM to read gathered rows. The obvious candidate is making the
  **producer** of `sortedX` cheaper or fused rather than eliding it - e.g. having
  `routeCountingSortFused` emit the permuted activations directly in one pass
  instead of emitting `rowOrder` and then paying a separate `flat[rowOrder]`.
  That is a host-plus-editable-kernel change and does not touch
  `steel/gemm/nax.h`. It is capped by the same +0.46 % ceiling, so it is only
  worth doing if it is cheap.
- No submitted file was modified by this experiment. The byte budget is
  unchanged, which the budget check below confirms with `growth=0`.

---

## 5. Standing checks

### 5.1 Editable byte budget

```text
$ senpai/check-editable-budget.sh 929b5c439b41675c35d38ede227fd58220c40513
editable budget OK: current=2941175/3000000 bytes headroom=58825 growth=0/262144 files=142 (file count is diagnostic only; base=142)
```

`growth=0`, and the **sign is non-negative**, so nothing on the submitted
surface was silently reverted. `current` and `files` are byte-identical to the
base, consistent with this branch touching only `research/`:

```text
$ git diff --name-only 929b5c4 HEAD
research/maple-fern-m2-lhs-indices.md
research/maple-fern-m2-prereg.md
research/maple_fern_m2_gather_probe.swift
```

Intersection of those three paths with the 97 `editablePaths`: **empty**. The
+8,000 B net cap assigned for this experiment is therefore unused and returns to
the pool (frieren #35 reserved 13,037 B, nezuko #60 reserved 2,000 B).

### 5.2 Base advance during the experiment

The assigned base `929b5c4` advanced to `fae11f9` while this ran (17 files, all
`research/`: nezuko PR60 pipeline artifacts, tanjiro gather-GEMM co-residency and
band-ratio notes, and a `CURRENT_RESEARCH_STATE.md` update). Per the standing
rule, intersecting `git diff --name-only 929b5c4 fae11f9` with the 97
`editablePaths` gives **empty**, so this is a docs-only advance: accepted, no
rebase, no advisor query.

### 5.3 Reproduction

```bash
# worker build used by every probe in this report
mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved

# Step 0 branch census (needs the throwaway DARKBLOOM_CENSUS_GQMM instrument)
DARKBLOOM_CENSUS_GQMM=1 python3 research/prefill_probe.py --reps 1 \
  --stderr /tmp/census.worker.err

# Step 1 standalone probe (superseded by Step 1b; kept for the negative result)
xcrun swiftc -O research/maple_fern_m2_gather_probe.swift \
  -framework Metal -framework Foundation -o /tmp/m2probe && /tmp/m2probe

# Step 1b in-situ duplication (needs the throwaway DARKBLOOM_M2_GATHER_DUP
# instrument in SwitchLayers.swift; see §3.1)
for n in 1 9 17 1; do
  DARKBLOOM_M2_GATHER_DUP=$n python3 research/prefill_probe.py --reps 5 \
    --stderr /tmp/m2dup.$n.err
done
```

Both instruments were throwaway commits (`f35291b`, `fe47706`), hard-reset after
each measurement; the branch carries neither. `git status` is clean and the
submitted surface is untouched.

### 5.4 Evidence channel

This assignment had a **zero ranked-receipt budget** (the `mlxfast` channel was
held by frieren), and no W&B runs - the target has no W&B integration for this
work. All evidence is therefore local M4 GPU measurement plus source-level
verification, recorded in this file and in
`research/maple-fern-m2-prereg.md`. Every quantitative claim above is either a
pasted command output or arithmetic over one.

Per `AGENTS.md`, an M4 prefill result is **not** evidence for an `_nax` change.
That does not weaken this report, because the measured quantity is the cost of a
plain gather kernel that is *not* `_nax` (Law 0.9.10) and the M5 conversion is
applied explicitly with a stated, conservative byte-arm factor. It does mean
§4.2's family-A implementation sketch could never have been certified here even
if it had been worth building.
