# SENPAI Research State

- **2026-08-04 (round 4 in flight)** — advisor `meridian`, campaign
  `mlxfast-maple-20260804`
- Most recent human research direction: operator authorised the advisor and all
  four students to dispatch official `mlxfast submit` runs from the AWS Macs.
- Base branch: `codex/mlxfast-maple-20260804-advisor` @
  `aecc470edecf01cbf9cb708bdc5ad69b90c73754`
- Students: `maple-frieren`, `maple-fern`, `maple-tanjiro`, `maple-nezuko`
  (M4 Pro / 48 GB / 20-core GPU). Official host: M5 Max / 128 GB / ~40 cores.
- Goal: maximise `score = decode_speedup^0.75 * prefill_speedup^0.25`.
- Companion documents: `research/FIELD_MECHANISM_MAP.md` (public corpus,
  session-draw distribution, promotion arithmetic),
  `research/nezuko-decode-roofline.md` (byte budget),
  `research/tanjiro-m5-instrument-calibration.md` and
  `research/nezuko-harvest-report.md` (measurement floors).

> **This target has no W&B integration.** Every `runs` array in every result is
> empty by design; the `runs` URLs we do record are mlxfast submission API
> endpoints. Evidence is code, matched local harness pairs, and official M5
> submission metrics.

---

## THE FOUR THINGS TO READ FIRST

### 1. Decode is DRAM-saturated. Score is a byte budget.

Two independent derivations (nezuko `research/nezuko-decode-roofline.md`, plus an
independent audit) agree to within rounding: one steady decode step reads

| stream | MB/token | share |
| --- | ---: | ---: |
| attention q/k/v/o (NVFP4 g16) + per-head `g_proj` (INT8 g32) | 807.7 | 45.0% |
| routed experts, top-8 of 256 (NVFP4 g16) | 552.1 | 30.8% |
| lm_head int5 coarse screening plane | 134.9 | 7.5% |
| layer-0 dense MLP (BF16, intermediate 8192) | 100.7 | 5.6% |
| KV cache (BF16) | 84–89 | 4.7% |
| routers (BF16, 40 × 2048 × 256) | 40.9 | 2.3% |
| embeddings, norms, activations | ~3.6 | 0.2% |
| **total** | **~1794** | |

```
1794 MB / 8.769 ms (M4 --local-iterate step) = 204.6 GB/s
measured M4 Pro DRAM ceiling                 = 260.2 GB/s
                                    ratio    = 78.6%
```

The steady step runs at **78.6% of the measured hardware bandwidth ceiling**.
Nothing else in the campaign is close to its ceiling. Therefore the operative
conversion for the 75%-weighted axis is:

```
score gain  =  0.638 * (MB removed per token) / 1794
```

(0.638 is the measured M5 steady-step elasticity; see finding 2.)

| bytes removed | score gain | promotion odds |
| ---: | ---: | --- |
| 10 MB | 0.36% | — |
| 25 MB | 0.89% | — |
| **33 MB** | **1.17%** | **~1-in-12 shot** |
| **59 MB** | **2.10%** | **~coin flip** |
| 105 MB | 3.73% | promotes |

**Consequences that should govern every assignment:**

- A decode change that does not remove bytes, or does not improve bytes/second,
  is worth approximately nothing. Dispatch counts, host CPU, fusion, occupancy
  and instruction mix have all now been individually falsified (below), and the
  roofline explains why: they were never the binding constraint.
- The remaining decode levers are exactly two: **remove logical bytes** and
  **close the 21.4% efficiency gap** (finding 4).
- Precision is *not* a lever. `AGENTS.md` forbids precision changes outside the
  attention INT8 envelope, and that envelope is **backwards for us**: the
  frontier already runs Q/K/V/O at NVFP4 g16 (0.5625 B/param) where the envelope
  permits group-32 INT8 (1.125 B/param). Adopting the envelope would *add*
  ~802 MB/step. This is a compliance oddity inherited from organizer frontier
  commit `99b974c`, not something we introduced, and it has passed official
  gates repeatedly. Leave it alone and do not treat it as headroom.

### 2. The exact score decomposition, and the M4→M5 transfer factors

```
D = decode_seconds_per_token       P = prefill_seconds_per_token
S = 512 * P                        (seed 512-token forward wall time)
T = D - S/128                      (marginal steady 1-token step)
sigma = (S/128) / D                (seed share of the decode measurement)

d ln score / d ln S = -(0.25 + 0.75 * sigma)
d ln score / d ln T = -0.75 * (1 - sigma)        # the two sum to -1
```

| context | S | T | sigma | elasticity on S | elasticity on T |
| --- | ---: | ---: | ---: | ---: | ---: |
| **official M5 (ours)** | 98.153 ms | 4.3530 ms | 14.98% | **0.362** | **0.638** |
| official M5 (pinned baseline) | 193.544 ms | 12.3206 ms | | | |
| M4 `--local-iterate` | 585.6 ms | 8.769 ms | 33.6% | 0.502 | 0.498 |
| M4 `--local-submit` (1023 steps) | | | ~5.9% | 0.294 | 0.706 |

**Transfer corrections a student must apply to M4 `--local-iterate` numbers:**

- a pure steady-step (T) win is **under-reported by 1.28×**;
- a pure seed-forward (S) win is **over-reported by 1.385×** — multiply forward
  deltas by 0.72 before quoting a score effect.

### 3. Rank by renormalised `ns`, never by `officialScore`. Three receipts.

Canonical normalisation, mandatory for every cross-session comparison:

```
norm_decode_su  = 0.013890  / decode_seconds_per_token
norm_prefill_su = 0.0003845 / prefill_seconds_per_token
ns              = norm_decode_su**0.75 * norm_prefill_su**0.25
draw            = officialScore / ns
```

nezuko's #12 measured, on **byte-identical content across 7 families, 27 dof**:

| quantity | pooled cv | runs to resolve 0.25% at 2σ |
| --- | ---: | ---: |
| renormalised `ns` | **0.489%** → 0.149% | **3** |
| `officialScore` | 0.489% | **31** |

`officialScore` is **3.3× noisier than `ns` on identical content**, because it
carries the session baseline draw. The 2σ floor for comparing two n=3 families
is **0.243% on `ns`**; the advisor's 2× bar for accepting a claim is therefore
**0.61%**.

Per-axis floors (tanjiro #13, 3 byte-identical official runs — superseded for
`ns` by the 27-dof numbers above, still the best we have per-axis):

| axis | floor |
| --- | ---: |
| `ns` | 0.140% |
| candidate `D` | 0.330% |
| candidate `T` | 0.475% |
| candidate `S` | 0.497% |
| `baseline_decode` | 0.493% |
| `baseline_prefill` | **4.829%** (bimodal, 3.61% gap between the two modes) |
| `prefill_speedup` | 4.946% |
| `decode_speedup` | 0.599% |
| conservative score floor | 0.303% |

Rules:

- **Never rank by `officialScore`.** Never use a *ratio's* apparent stability as
  a noise floor: tanjiro's A/B pair alone gave `decode_speedup` 0.010% purely by
  numerator/denominator cancellation luck, a 60× underestimate.
- Report per receipt: submission id, `officialScore`, `ns`, and
  `S = 512000 * prefill_s_per_tok` ms, `T = 1000 * decode_s_per_tok - S/128` ms.
- The service **dedupes byte-identical archives** ("Submission already exists"),
  so our base already ships a free 3-receipt control: `f8502e12`, `71586bcf`,
  `f3cda678`.

### 4. The 21.4% of the decode step that logical bytes do not explain

```
1794 MB at the measured 260.2 GB/s ceiling  =  6.89 ms
measured M4 --local-iterate step            =  8.77 ms
                              unexplained   =  1.88 ms  (21.4%)
```

frieren's amplification caps (≤28.4 MB of KV waste, ≤16.9 MB of full-attention
inefficiency) account for only ~0.17 ms of that. **The remaining ~1.7 ms is the
single largest unpriced quantity in the campaign — worth up to 13.6% of score if
recoverable, or a proof that 78.6% is the practical ceiling and the campaign is
purely a byte-removal exercise from here.** This is tanjiro's #21 and is the
highest-information open question we have.

Leading candidates, in the order tanjiro is testing them: NVFP4 group-16 scale
traffic read as a second, poorly-coalesced stream; per-kernel low-occupancy
ramp-up/ramp-down tails inside the ~600 dispatches per step (Metal counters call
a kernel "busy" while a single threadgroup runs, so frieren's 97.7% GPU-busy
figure does **not** exclude this); and N=1 GEMV read efficiency on the packed
NVFP4 layout.

---

## Current research focus

Round 4, all four arms derived from the byte budget:

| PR | student | arm | mechanism and target |
| --- | --- | --- | --- |
| #20 | nezuko | **lm_head cascade** | the 134.9 MB int5 screening plane is 7.5% of the step. Drop the two inert commits (`9c1ad1c`, `6ca0c71`), then land a coarser first-level screen. First direct test of the DRAM-saturation model. Immediate target 25.7 MB (0.9%); structural ceiling if the plane can be replaced by a hierarchical screen is ~105 MB (3.7%) |
| #21 | tanjiro | **price the 21.4% residual** | finding 4. Part 1 needs no submissions: find the realistic bytes/second ceiling. Part 2 attacks the worst stream if a recoverable gap exists |
| #22 | fern | **`Sources/MLXFastTransform/`** | the only axis in 1372 public submissions with **zero** attempts. Part 0 is a hard kill check: is `weights_hash` pinned on the ranked path, and does the official run execute our transform at all? |
| #14 r2 | frieren | land research only | his host-CPU and KV findings are first-class; the minifier in the same PR is worth 0.0% and conflicts with #12. Drop it and ship the findings |

Pre-announced next arm for frieren: the **exposed head-latency term** —
0.29–0.32 ms measured on M4, against a 4.353 ms M5 step, so ≤2.9% of score. His
3 unspent submissions carry forward.

Cross-arm dependency the advisor is policing: tanjiro's #21 Part 1 case (2)
separate-scale-buffer vs case (3) interleaved NVFP4 read is the **gate** for
fern's #22 implementation. If the two differ by less than ~10%, fern pivots to
#22 Part 3 (pre-permute / pre-transpose / routing metadata) or closes the arm.

### Promotion target

Promotion requires `officialScore > 2.53921`, and `officialScore = ns × draw`.

| our ns | required draw | expected submissions to promote |
| ---: | ---: | ---: |
| 2.5157 (today) | 1.00934 | never observed |
| 2.5260 | 1.00523 | ~303 |
| 2.5331 | 1.00241 | ~130 |
| 2.5400 | 0.99969 | ~28 |
| **2.5450** | **0.99772** | **~12** |
| 2.5686 | 0.98847 | ~2 |

**Target `ns` >= 2.545, i.e. +1.16% on today's tree.** Resubmission is a
measurement channel, not a strategy.

### The strategic fact that defines this campaign

Normalising all 909 scored public submissions: ours sits at nd 2.7130 (91st
percentile), npf 2.0057 (88th percentile), ns 2.5157. The field records are
nd **2.739127** (`ae9ac90b`) and npf **2.0220** (`e2822dc1`).

```
naive union of both field maxima:  ns = 2.739127^0.75 * 2.0220^0.25 = 2.5390
promotion needs                    ns = 2.5392 at draw 1.000
```

So the *naive* union of everything the entire public field has ever achieved
lands one part in ten thousand short of promotion at a median-plus draw. nezuko
then de-biased those maxima for the winner's curse (measured directly on family
A, n=18: nd +0.494%, ns +0.413%) and obtained a **true field ceiling of
2.5281–2.5318** — 0.5–0.7% short of even a 1-in-12 shot.

**Conclusion: harvesting the field cannot promote us. We need a mechanism the
field does not have.** That is why every round-4 arm targets a byte stream or an
efficiency gap rather than a public diff.

---

## Established facts (do not re-derive)

### Model configuration (`Sources/MLXFastModel/LagunaConfig.swift:14-35`)

vocab 100352, hidden 2048, 40 layers, headDim 128, 8 KV heads. **48 query heads**
on the 10 full-attention layers (indices 0, 4, 8, …, 36) and **64 query heads**
on the 30 sliding-window layers (window 512). 256 routed experts, top-k 8,
MoE + shared-expert intermediate 512, dense MLP intermediate 8192 on layer 0
only. NVFP4 config `{"group_size":16,"bits":4,"mode":"nvfp4"}`.

Precision by class, with the byte rates used in the budget:

| class | representation | B/param |
| --- | --- | ---: |
| q/k/v/o | BF16 on disk (`LagunaCheckpointValidation.swift:355-358`), re-quantised at load to **NVFP4 g16** (`LagunaRuntimeModel.swift:2960-2974`, `:5302-5305`) | 0.5625 |
| `g_proj` | group-32 affine INT8 (`LagunaRuntimeModel.swift:431-448`) | 1.125 |
| routed + shared experts | NVFP4 g16 on disk | 0.5625 |
| lm_head, embeddings, routers, dense-0, norms | BF16 | 2.0 |
| KV cache | BF16 (`KVCache.swift:375-376`, `:629-630`); `RotatingKVCache(maxSize: 512, keep: 0)` at `LagunaRuntimeModel.swift:10840-10845` | 2.0 |
| lm_head int5 screening plane | 1344 B per vocab row | |

### The NAX gate — a programme-level constraint (fern #11)

`mlx::core::metal::is_nax_available()`
(`Vendor/mlx-swift/.../backend/metal/device.cpp:913-931`) requires macOS >= 26.2
**and GPU arch gen >= 17**. Our M4 Pro hosts report `applegpu_g16s gen=16`: the
OS gate passes, the generation gate fails.

- **94.2% of prefill GPU time on a student host runs Metal functions the official
  M5 never executes** — different kernels, not the same kernel at different
  occupancy: `nvfp4_gather_qmm_rhs_nt` 48.5%, `steel_gemm_fused_nt_bm64_bn64_bk16`
  33.4%, split-K 6.0%, `steel_attention_bfloat16_bq32_bk16` 5.1%,
  `nvfp4_qmm_t` 1.2%. Only 5.8% of prefill is host-generation-independent.
- The **steady decode step is 100% host-independent**: every dispatch is a
  hand-written `laguna_*` kernel (or `rms`/`gather_front`). The only capability
  gate in all of `Sources/` is `lagunaExpertAlignedGatherEnabled`
  (`LagunaRuntimeModel.swift:235-249`), used at exactly one **prefill** site
  (`:9631`).
- Never run a prefill *kernel* experiment on a student host. Local timing there
  is not weak evidence; it is evidence about different code.
- `fp_gather_qmm_rhs_expert_nax` is **JIT-only**, built at runtime from
  `mlx-generated/fp_quantized_nax.cpp`. Editing the header alone changes nothing
  at runtime; the generated `.cpp` must be edited too, and the header kept
  identical because the AOT metallib compiles it for other kernels.
- Three silent-failure modes on that kernel: odd `TN>1` yields an empty
  `tile_matmad_nax`; `SM<16` yields `TM=0` and no MMA at all; falling off the
  `bm==64 && wm==4` gate (`quantized.cpp:1668-1671`) silently dispatches the
  non-expert kernel. Any arm here needs a positive "MMA actually executed"
  assertion.
- `SM 16→8` is impossible: `TM = SM/16` (`fp_quantized_nax.h:1719`),
  `kFragRows = 16` (`steel/gemm/nax.h:28,540,547`). The resulting 31.3% MMA row
  padding is a hardware floor.

### Forward-pass budget (fern #11)

2830.2 GFLOP and 26.68 GB per 512-token forward = 106.1 FLOP/byte. Shares:
`attn_proj_qkvo` 51.8%, `routed_experts` 35.5%, `attn_core` 5.7%,
`shared_expert` 4.4%, `dense_mlp_layer0` 1.8%, `router` 0.7%.

- M4 forward: 4.83 TFLOP/s (16.8% of MMA ceiling) and 45.6 GB/s (17.5% of DRAM).
  **Neither bound on M4** — which is why M4 prefill timing is uninformative.
- M5 forward: S = 98.153 ms → **28.8 TFLOP/s and 271.8 GB/s**, roughly half of
  each M5 roofline. This is the least-understood region of the whole problem and
  is where the field's prefill record has stood unbeaten for 102 submissions.

### Measured M4 Pro ceilings

scalar FMA f32 7.07 / f16 7.59 TFLOP/s; simdgroup MMA bf16 28.76 / f16 28.96
TFLOP/s; DRAM **260.2 GB/s**.

### Routing histogram at 512 tokens (host-independent, `research/prefill-512-route-histogram.txt`)

mean 16.00 rows per (layer, expert), stdev 28.77 (**CV 1.80**), p50 7, p75 19,
p90 39, p95 58, p99 142, max 505, **20.3% of pairs receive zero rows**. Busiest
8 experts hold 26.0% of assignments, busiest 32 hold 54.7%. Per-layer max/mean =
15.2×. The shipped expert tile parameters were "Simulated over uniform routing"
(`quantized.cpp:1405-1415`) — empirically false.

### Harness and gate facts

- **The acceptance band `[0.980, 1.053]` is NOT enforced.** `Constants.swift:150-166`,
  `benchmark.yml:1511` and `overlay-paired-timing.sh:129-169` apply only the two
  0.95 floors. **Never throttle a win to fit the band.**
- **TTFT is not gated.** `gpqa_ttft_max_seconds` is `seconds.max() ?? 0`
  (`LagunaRuntimeCorrectness.swift:230-232`); no max-seconds threshold exists.
  Init-time headroom is effectively unbounded.
- `metal_kernel.cpp` and MLX `device.cpp` dispatch entry are **not** in
  `editablePaths` → concurrent encoder dispatch is permanently closed.
- A/A noise floor on M4 `--local-iterate`: prefill −1.30%, decode +0.48%. A
  sub-1.5% single-run prefill delta on M4 is noise. Local `prefill_speedup ≈ 0.33`
  is the M4/M5 hardware ratio against the pinned
  `officialBaselinePrefillSecondsPerToken = 0.00036751938916015625`, not a
  regression.
- Submission surface after #12: totalBytes 2,912,613 of 3,000,000; `fileCount`
  pinned at 142; ~87 KB of headroom. `editablePaths` = 97 entries.

### Integrity rulings (fern refused to ship both; upheld)

Pre-touching a live buffer pool across the phase boundary, and pre-boosting the
GPU clock across the hello→request boundary, are both **circumvention**, not
optimisation.

---

## Closed families — do not re-litigate

| family | verdict | evidence |
| --- | --- | --- |
| **In-loop host CPU** | **CLOSED** | frieren #14: injecting 2.0 ms/step of per-layer host spin *reduced* wall 8.903→8.669 ms (fully absorbed), while identical spin at the *step head* passed through 1:1. Therefore `wall ≈ head_latency + GPU_total`. M4 decode is 97.7% GPU-busy with a 0.29–0.32 ms exposed gap. A −3.7% main-thread / −30.6% source-byte cut moved `T` by 0.0% ±0.2% |
| **KV re-request amplification** | **REFUTED** | frieren #14 slope method. Sweep A (seeds 512..6144, only the 10 full-attention layers grow): 27.03 ns/pos/layer, no curvature over 21–252 MB. Sweep B (below 512, all 40 layers, 16 palindromic runs): 828.6 ± 56.2 ns/pos → sliding 18.61 ns/pos/layer. Amplification ≤1.72× full, ≤1.18× sliding; waste ≤ +28.4 MB (≤1.01% of score). The 190 MB claim is ≥6.9σ out. **Replacement finding:** the full-attention path is the least bandwidth-efficient stream at 58.2% of peak vs the 78.6% step average, capped at 16.9 MB/step ≈ 0.6% of score |
| **Attention / sliding occupancy** | **CLOSED** | tanjiro #13: 80 threadgroups co-reside at the real 17920 B / 1024-thread shape on 20 M4 cores. The g=21/41 risers are **work imbalance**, `f(m) ≈ 1 + 0.365(m-1)`, not occupancy. `w=2→1` is model-closed as an M5 loss; `w>=4` exceeds the 32768 B threadgroup-memory limit. He withdrew his own 81920 B linear-pool model |
| **Harvesting the public field** | **CLOSED** | nezuko #12: de-biased field ceiling 2.5281–2.5318, below a 1-in-12 shot |
| **Advisor axis-coverage tables** | **RETRACTED** | nezuko #12: note-length artifacts. Median \|axis-mean nd − overall\| = 0.220%, inside noise. **Only survivor: `Sources/MLXFastTransform/` = 0 of 147 swept diffs, the only genuinely zero-attempt axis** (fern #22) |
| **First-touch prewarm** | **CLOSED** | fern #19: six back-to-back forwards 544.72 / 546.68 / 546.11 / 547.48 / 546.81 / 546.74 ms — the *first* is fastest. Cache exactly 0 B at timed entry, 35.75 GB live, 39.07 GB peak. `cacheLimit=0` vs 6 GiB indistinguishable. On a ≥96 GiB M5 the constructor already wires ~31.4 GiB via `set_wired_limit` before hello (`LagunaRuntimeWeights.swift:546-580`). `argmax_bfloat16` PSO compile (~0.23 s) is already outside scored prefill (`:499-510`) |
| **Attention INT8 envelope** | **DEAD, BACKWARDS** | the frontier already runs Q/K/V/O at NVFP4 g16 (0.5625 B/param) vs the envelope's group-32 INT8 (1.125). Adopting it adds ~802 MB/step |
| Dispatch count / fusion for latency | closed | nezuko #9: deleting 40 of 406 dispatches/step returned exactly zero |
| Concurrent encoder dispatch | closed | `gpu_busy_sum == gpu_busy_union` to 6 ns; entry files not editable |
| Sliding-window KV re-read | closed | #5 |
| Certified LM-head screening (old form) | closed | #6 |
| M4-argmax geometry as evidence | closed | #10 |
| Routed-MoE BM widening; sub-16 SM | closed | hardware floor, see NAX gate |
| Zero-row expert skip | closed | DRAM-bound; no bytes removed |
| `arangeuint32` caching | closed | the 76 dispatches were a command-buffer overlap artifact, ~0 ms real |
| Prefill host CPU / command buffers | closed | prefill GPU-busy union is 99.4% of wall |
| `DARKBLOOM_ATTN_QHOIST`, `GEMM_TPARAM_MACRO` | closed | no effect |

---

## Submission ledger (official M5)

| id | tree | published / renorm `ns` | note |
| --- | --- | --- | --- |
| `27b9c7c6-14bf-…` | frontier + #7 | 2.49724 / 2.5152 | rejected; all gates passed |
| `f8502e12`, `71586bcf`, `f3cda678` | BASE_SHA, byte-identical ×3 | — | tanjiro control family |
| `5d522d6a` | nezuko harvest tip | 2.491470 / 2.520600 | rejected |
| `5e0e9cd1` | same tip | 2.500092 / 2.513024 | rejected |
| `c210d200` | same tip | 2.514743 / 2.521103 | rejected |

nezuko's harvest tip vs the control family: `ns` **+0.214% ± 0.122%**,
`T` **−0.468% ± 0.181% (2.6σ)**, `S` +0.236% ± 0.142%, `officialScore`
−0.056% ± 0.399%. A real `T` win, near-zero on `ns`. She recommended dropping
`9c1ad1c` (cap-400, the suspected `S` regression) and `6ca0c71` (both
individually inert); that is the first commit of #20.

**The promoted best is not a good tree.** `8415f63c` posted `officialScore`
2.53921 but **ranks 92nd of 919 on content**: its +1.483% lead over us decomposes
into **−0.063% content and +1.547% luck** (draw 1.00896 = p100). The cleanest
proof in the corpus is `0c83fa3e`, which holds the **3rd-lowest `T` of 919** with
no runtime mechanism whatsoever — one environment integer changed 200→160 plus
two inert `static_assert` deletions — while simultaneously carrying a +1.464%
prefill regression.

**The board is frozen.** 2026-08-04 saw 41 submissions and 0 acceptances. Corpus:
139 accepted, 769 rejected, 463 failed.

---

## Potential next research directions

Ordered by expected value, given that decode is a byte budget and prefill is the
field's frozen axis.

1. **M5 prefill is the field's blind spot and it sits at ~50% of both rooflines.**
   S = 98.153 ms → 28.8 TFLOP/s and 271.8 GB/s on a host whose MMA peak is
   ≥57 TFLOP/s (plus NAX) and whose DRAM peak is ≥500 GB/s. Elasticity on S is
   0.362, so a 10% S win is 3.6% of score — larger than any decode arm we have.
   The field's prefill record has stood for 102 submissions **not because prefill
   is physically hard but because nobody can execute a `_nax` kernel on non-gen-17
   hardware**: the only prefill instrument in existence is a 35-minute official
   submission returning one scalar. That is a measurement wall, not a physics
   wall, and it is the largest asymmetry available to us. Requires
   host-independent reasoning (routing statistics, static kernel analysis, byte
   arithmetic) validated by 3-receipt official families. Analysis in progress:
   `research/PREFILL_NAX_ANALYSIS.md`.
2. **Deepen the lm_head cascade beyond nezuko's first 25.7 MB.** The int5 plane is
   134.9 MB = 7.5% of the step. A hierarchical screen (very coarse bound over all
   100352 rows → int5 on ~10³ survivors → exact rescore) could take the plane to
   ~30 MB, i.e. ~105 MB removed = 3.7% of score, which promotes on its own. Must
   be split into independently correct ≤5% increments per the calibration band.
3. **Routing-aware two-regime expert dispatch.** The shipped tile is tuned for
   uniform routing that does not occur (CV 1.80, 20.3% empty, busiest 32 experts
   = 54.7%). Row-tile widening and sub-16 SM are both closed, but a *two-regime*
   split — short tail and long tail dispatched differently — has never been
   costed. Needs a mechanism proposal, not a knob. Prefill-side, so official
   measurement only.
4. **`attn_proj_qkvo` is 51.8% of forward FLOP** and the largest single block in
   the seed forward — larger than routed experts — running at 23.5% of the M4 MMA
   ceiling. On M5 it is the `steel_gemm_fused_nax` (bm128/bn128/bk512) family.
   Nobody in the campaign has looked at it.
5. **If tanjiro's #21 finds the 21.4% residual is recoverable**, that becomes the
   top priority immediately: up to 13.6% of score, the largest single number in
   the campaign. If he finds it is not, close decode-efficiency permanently and
   put all four students on byte removal and prefill.
6. **Unassigned decode item with an unresolved contradiction:**
   `lmhead_exact_inline_mask_block_v1` costs 76.6 µs/step on M4, but 76.6 µs at
   260.2 GB/s can move at most ~20 MB — irreconcilable with a 134.9 MB plane read.
   Folded into nezuko's #20 as a required explanation.
7. **~83 single-threadgroup dispatches per decode step** (tanjiro, unassigned);
   fusing RMSNorm into QKV removes 40. Low expected value now that decode is
   known DRAM-bound — hold unless #21 revives it. Note that frieren's low-memory
   host caps command buffers, so his ~45/step is **not** the ranked count.
8. **Minify the remaining 71 Metal literals in `LagunaRuntimeModel.swift`**
   (−54,251 B of surface). Worth 0.0% of score; only relevant if we ever run out
   of the ~87 KB of surface headroom.
