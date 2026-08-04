# M5 instrument calibration, occupancy closure, and the GPU/host verdict (PR #13)

`BASE_SHA = 51d6a1bd5ae4c417a908efc8bc9ff6837b7a0c49`. Development host: Apple M4
Pro, 20 GPU cores, 48 GB unified memory (`Mac16,11`).

All official numbers below come from complete rejected-submission receipts. Raw
JSON is archived under `research/m5-calibration/`.

---

## Part 1(a) — The noise floor. Measured, and it is not small.

Three official runs of **compile-identical** code, spanning about 70 minutes:

| metric | A `f8502e12` | B `71586bcf` | C `f3cda678` | spread |
| --- | ---: | ---: | ---: | ---: |
| `decode_seconds_per_token` | 0.0051331159 | 0.0051446455 | 0.0051277201 | **0.330%** |
| `prefill_seconds_per_token` | 0.00019066846 | 0.00019045483 | 0.00019140210 | **0.497%** |
| `baseline_decode_seconds_per_token` | 0.0138489772 | 0.0138814860 | 0.0139172438 | 0.493% |
| `baseline_prefill_seconds_per_token` | 0.00037057625 | 0.00038847070 | 0.00037934106 | **4.829%** |
| `decode_speedup` | 2.6979670 | 2.6982396 | 2.7141193 | 0.599% |
| `prefill_speedup` | 1.9435635 | 2.0396999 | 1.9819065 | **4.946%** |
| **official score** | **2.4855766** | **2.5159497** | **2.5089528** | **1.222%** |
| **normalised score** | **2.5141736** | **2.5106500** | **2.5137430** | **0.140%** |

All three rejected on ranking only. All three passed every gate identically:
`max_abs_diff 0`, `checked_steps 1344`, `passed_correctness true`, GPQA TTFT 9/9
(p50 0.072 s, max 2.3 s), semantic GPQA 9/9 via `claude-opus-4-8`,
`peak_ram_gb 21`, both 0.95 floors.

**The third replicate corrected the second twice, and this is the most
practically important lesson in the note.** On A and B alone I had
`decode_speedup` reproducing to 0.010% and candidate `T` to 0.283%. C shows the
first was pure cancellation luck (0.599%, a 60x revision) and the second was
optimistic (0.475%). **Two identical trees will hand you a spuriously tight noise
floor. Use three.**

Normalised score uses the advisor's canonical session baseline (decode 0.013890,
prefill 0.0003845): `norm = (0.013890/D)^0.75 * (0.0003845/P)^0.25`.

Formula check: `0.75*(+0.010%) + 0.25*(+4.946%) = +1.244%` against the published
**+1.222%**. The receipt is internally consistent; this is real measurement
scatter, not a reporting artefact.

### The answer to the gating question

**Ranking by published official score, the minimum detectable effect is ~1.2%.**
With the advisor's 2x margin rule that means >2.5% — nothing on this leaderboard
is that big, and the field advances ~0.28% per promotion. On that instrument we
are blind.

**Ranking by normalised score the floor is 0.140%, an 8.7x tighter instrument at
zero cost** — and it did not widen when C landed.

But do not lean on 0.140% naively, because the reason it is that tight may not be
a property we can rely on. Candidate `D` and candidate `P` are **anti-correlated**
across the three sessions (`D` dev -0.040 / +0.185 / -0.145%, `P` dev -0.091 /
-0.203 / +0.294%), and since `norm` is proportional to `D^-0.75 * P^-0.25`,
opposing deviations partly cancel. That is how a 0.330% spread and a 0.497%
spread combine into 0.140%. With `n = 3` I cannot separate a real mechanism from
luck, so the **conservative** floor propagates the `T` spread through its
elasticity: `0.475% x 0.638 = 0.303% of score`.

Recommended thresholds on the conservative figure: **>0.6% is a result on one
run** (it clears the advisor's 2x bar), **0.3-0.6% needs a replicate**, and
**<0.3% is unmeasurable — do not spend a submission on it.**

**So Part 2's stop rule fires, but Part 1's answer is good news, not bad.** The
team is not blocked; it just has to stop reading the published score.

### All of the noise is one metric, and it is not ours

| quantity | identical-code spread (A vs B) | 3-session range (with `27b9c7c6`) |
| --- | ---: | ---: |
| candidate `prefill_seconds_per_token` | 0.112% | 0.656% |
| candidate `decode_seconds_per_token` | 0.225% | — |
| `baseline_decode_seconds_per_token` | 0.235% | — |
| **`baseline_prefill_seconds_per_token`** | **4.829%** | **4.829%** |

The pinned baseline's 512-token forward drew **193.544, 189.735, 198.897 ms**
across three sessions running the same baseline code. No monotone trend, so this
is scatter, not drift. Over the same three sessions the pinned baseline's steady
decode step moved only **0.374%**.

Because `prefill_speedup = baseline/candidate`, that 4.8% lands on the published
ratio undamped and one quarter of it lands on the score. **The submitter cannot
influence the single dominant source of official score variance.**

### Practical rules for this team

1. Never rank two of our own submissions by published `officialScore`.
2. Rank by candidate `decode_seconds_per_token` and candidate
   `prefill_seconds_per_token` — spreads 0.225% and 0.112%.
3. Or equivalently by normalised score — spread 0.140%.
4. Resolvable effect size: **>0.5% is a result, 0.3% needs replicates, <0.2% is
   unmeasurable in a single pair.**

### Four numbers per receipt, not two

Applying fern's exact decomposition (`S = 512P`, `T = D - 4P`):

| | S = 512P (ms) | T = D - 4P (ms) | S_base (ms) | T_base (ms) |
| --- | ---: | ---: | ---: | ---: |
| `27b9c7c6` | 98.1530 | 4.35295 | 193.5442 | 12.32062 |
| A `f8502e12` | 97.6223 | 4.37044 | 189.7350 | 12.36667 |
| B `71586bcf` | 97.5129 | 4.38283 | 198.8970 | 12.32760 |
| C `f3cda678` | 97.9979 | 4.36211 | 194.2226 | 12.39988 |
| **identical-code spread (A, B, C)** | **0.497%** | **0.475%** | 4.829% | 0.586% |

**The steady one-token decode step on the ranked M5 is 4.370 ms (mean of A, B, C)
and it reproduces to 0.475%. That is the number every future decode arm should be
judged on**, because it carries the 0.638 elasticity and is uncontaminated by the
baseline prefill draw.

One trap worth flagging: on A and B the published `decode_speedup` reproduced to
0.010%, far better than either of its parts. That was cancellation, not
precision — candidate `D` and baseline `D` happened to move together. C broke the
coincidence and the three-run spread is **0.599%**. **Never use a ratio's
apparent stability as a noise floor; use the candidate-side term.**

`sigma = (S/128)/D = 14.8%`, so score elasticities at the M5 operating point are
**0.639 on the steady step `T`** and **0.361 on the seed forward `S`**.

### Blocker for anyone replicating this: the service deduplicates archives

The first attempt at B was a byte-identical resubmit of A's tree. The service
refused it with **`Submission already exists`**, returned A's existing id, and did
not store the note. **The platform will not measure the same archive twice.** Each
replicate therefore costs one compile-neutral byte difference; we used a comment
in `Sources/MLXFastModel/MLXTensorBridge.swift`.

Do **not** put that carrier inside a Metal kernel source string: MLX keys its JIT
pipeline cache by kernel name and compiles the string it is handed, so an edit
inside the literal changes the compilation unit even when it cannot change
semantics. Keep it in host Swift, outside every kernel literal.

---

## Part 1(b) — The signed M5 value of the merged arms. Correcting the brief.

**The brief's attribution is wrong, and it matters, because it named an innocent
suspect.** The editable-path delta between the tree that produced `27b9c7c6`
(commit `ad4ad79`) and `BASE_SHA` is exactly two files:

```
Sources/MLXFastModel/LagunaLmHeadPrune.swift  | 1740 +++--------------  (#8)
Sources/MLXFastModel/LagunaRuntimeModel.swift |  609 ++++-----          (#4)
2 files changed, 436 insertions(+), 1913 deletions(-)
```

**#5, #9 and #10 contributed zero editable-surface bytes** — their runtime
mechanisms were reverted before merge and only `research/` and `senpai/tools/`
artifacts landed. So:

```
norm(BASE_SHA) - norm(27b9c7c6)  =  combined M5 effect of #4 + #8,  NOT #4 + #5.
```

**#5 cannot be the suspect and reverting it is moot.** It is not in the tree.

Measured, taking the mean of A and B as the `BASE_SHA` estimate:

| quantity | `27b9c7c6` | `BASE_SHA` mean(A,B,C) | delta | identical-code noise |
| --- | ---: | ---: | ---: | ---: |
| candidate S (ms) | 98.1530 | 97.7110 | **-0.450%** | 0.497% |
| candidate T (ms) | 4.35295 | 4.37179 | **+0.433%** | 0.475% |
| normalised score | 2.5156735 | 2.5128518 | **-0.112%** | 0.140% |

Recomputed against the **three-replicate mean** of `BASE_SHA` rather than a single
session, so the reference comparison is not itself a coin flip.

Elasticity cross-check: `-(0.362*(-0.450%) + 0.638*(+0.433%)) = -0.113%`, against
a directly computed **-0.112%**. Consistent.

**Verdict: #4 + #8 together are a formal null on M5.** With three replicates
**every component sits below its own noise floor** — `S` at -0.450% against a
0.497% floor, `T` at +0.433% against 0.475%, and the score at -0.112% against
0.140%. Nothing here is resolvable, and the two components have opposite signs,
so even their directions are unsupported.

(My earlier two-replicate version read `S -0.596%` and `T +0.544%` against floors
of 0.112% and 0.283%, which made both components look real. That was an artefact
of the spuriously tight two-run floors; the third replicate dissolved it.)

**Recommendation: do not revert either.** #8 is a pure deletion that bought the
surface headroom the campaign needs, and #4 costs nothing. But **#4 did not
deliver its M4-measured -3.4%.** That is the second arm in a row whose M4 win
evaporated on M5, and it is the key input to Part 3.

---

## Part 2 — Occupancy. Closed analytically, with a measured correction to the model.

### The measurement that changes the model

I built `senpai/tools/gpu-residency-probe`. It times a long dependent
device-memory pointer chase executed by lane 0 only: latency bound, nearly free
in bandwidth and ALU, so co-resident threadgroups overlap and elapsed time stays
flat until the hardware refuses another threadgroup — while the threadgroup still
declares its full thread count and threadgroup memory. On a real kernel a second
co-resident threadgroup and a second serialised wave are indistinguishable
because the work is throughput bound either way; this separates them.

Result on the M4 Pro, reproducible and order-independent (verified by reversing
shape order and repeating one shape twice):

| shape | resident TGs | per core | step-up at |
| --- | ---: | ---: | ---: |
| 1024 threads, 17,920 B | **80** | **4** | g = 81 (26.6 -> 53.0 us) |
| 1024 threads, 16,640 B | **80** | **4** | g = 81 |
| 1024 threads, 16,384 B | **100** | **5** | g = 101 (27.3 -> 52.3 us) |
| 1024 threads, 9,728 B | >260 | >13 | none in range |
| 1024 / 512 / 256 threads, 0 B | >260 | >13 | none in range |

The first three shapes are consistent with a single number, a **per-core
threadgroup-memory pool of 81,920 B (80 KiB)**:
`floor(81920/17920) = 4`, `floor(81920/16640) = 4`, `floor(81920/16384) = 5`.

**The 9,728 B row falsifies that pool model, and I am withdrawing it as a
mechanism claim.** A linear 80 KiB pool predicts `floor(81920/9728) = 8` per core
and therefore a step at `g = 161`; there is no step through `g = 260`, which
implies at least 13 threadgroups per core, i.e. at least 126,464 B held at once.
No single pool size produces both results. What all four rows do fit is a
**tiered admission rule** — roughly `> 16 KiB: 4/core`, `~12-16 KiB: 5/core`,
`<= ~9.5 KiB: >= 13/core` — whose mechanism I have not identified. **Probing
11-14 KiB would discriminate** (a linear pool predicts steps at `g = 141` and
`g = 121`); that is the obvious next experiment and I did not run it.

Two things are nevertheless solid. First, **bytes do gate admission**: 16,640 B
and 16,384 B declare identical thread counts and differ only in threadgroup
memory, yet admit 4 versus 5 per core. Second, the rows with zero and 9,728 B of
threadgroup memory **cannot** be used to rule out a per-core thread or simdgroup
cap, because only lane 0 chases pointers in this probe
(`senpai/tools/gpu-residency-probe/main.swift:43-49`) and the other 1023 threads
retire after one barrier; the probe holds threadgroup memory for the duration of
the chase but not live threads.

Note `device.maxThreadgroupMemoryLength` reports **32,768 B** — that is the
per-*threadgroup* limit and says nothing about how many threadgroups share a
core. It is easy to read 17,920 B against 32,768 B and conclude "one threadgroup
per core". That conclusion is wrong, and it is the error the brief and my own
earlier model both made.

**So our two fused attention kernels — 32 threadgroups sliding, 24 full, both
1024 threads and 17,920 B — are fully co-resident even on the 20-core M4, let
alone a 40-core M5. There is no residency-driven wave quantisation in them at
all.**

### What the risers in the earlier occupancy scan actually were

My sliding-kernel scan (`senpai/tools/sliding-attn-probe --occupancy`, real
kernel, 30 dispatches/step) showed clean steps at g=21 and g=41:

| dispatched TGs | us/dispatch | max per-core load m | f(m) = cost / T_tg |
| ---: | ---: | ---: | ---: |
| 1..20 | 22.79 | 1 | 1.000 |
| 21 / 32 / 40 | 31.84 / 31.67 / 31.24 | 2 | 1.382 |
| 41 | 39.29 | 3 | 1.724 |
| 64 | 47.76 | 4 | 2.096 |

Those are **work-imbalance steps, not occupancy steps.** A core hosting m
threadgroups' worth of throughput-bound work takes longer even though all m are
resident. The fit is strikingly linear:

```
f(m) = 1 + 0.365*(m - 1)
```

i.e. **co-residency hides 63.5% of each additional threadgroup's cost.** The naive
"m waves cost m x T_tg" assumption I used in #10 is too pessimistic by a large
margin.

### The corrected cost model

```
cost(w) = f(ceil((heads/w) / cores)) * T_tg(w),     T_tg(w) = a + b*w,  a > 0
```

Grounding: `a = 16.16 us`, `b_full = 6.65 us` from my `full-attn-probe` width fit
in #10; for the sliding kernel the measured single-wave plateau is
`T_tg(2) = 22.79 us`, which with the same `a` (identical prologue, 32-simdgroup
combine and epilogue structure) gives `b_slide = 3.315 us`.

### Predictions, on record, before any measurement

`laguna_sliding_fused_attn_ring_v1`, 64 query heads, 30 calls/step:

| w | TGs | thr/TG | tg mem | ceil(TG/20) | ceil(TG/40) | M4 cost | M4 sign | M5 cost | M5 sign |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- | ---: | :--- |
| 1 | 64 | 1024 | ~9,728 | 4 | 2 | 40.79 | +29.5% worse | 26.91 | **+18.1% worse** |
| **2 (shipped)** | **32** | **1024** | **17,920** | **2** | **1** | **31.50** | **baseline** | **22.79** | **baseline** |
| 4 | 16 | 1024 | ~35,840 * | 1 | 1 | 29.42 | -6.6% better | 29.42 | **+29.1% worse** |

\* w=4 also exceeds the 32,768 B per-threadgroup limit, so it is not even
implementable without restructuring the shared tile.

`laguna_full_fused_attn_grow_v1`, 48 query heads, 10 calls/step:

| w | TGs | thr/TG | tg mem | ceil(TG/20) | ceil(TG/40) | M4 cost | M4 sign | M5 cost | M5 sign |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- | ---: | :--- |
| 1 | 48 | 1024 | ~9,728 | 3 | 2 | 39.32 | **-3.4% better** | 31.52 | **+7.0% worse** |
| **2 (shipped)** | **24** | **1024** | **17,920** | **2** | **1** | **40.71** | **baseline** | **29.46** | **baseline** |
| 4 | 12 | 1024 | ~35,840 * | 1 | 1 | 42.76 | +5.0% worse | 42.76 | +45% worse |

**The model reproduces a measurement it was not fitted to.** In #10 I built
exactly the full-attention w=1 variant and measured **-2.75% on M4**. The
corrected model predicts **-3.4%** — a 0.65 percentage-point error — and predicts
the M5 sign flip to **+7.0%**. (My #10 projection of "+1.7% on 40 cores" used the
pessimistic 2x-wave assumption; with the measured `f(2) = 1.382` the true M5
penalty is 4x larger than I projected. The decision to revert was right for a
partly wrong reason.)

### Why the head axis is closed, not just unpromising

On a 40-core host, for any partition of `H` heads across threadgroups, the
elapsed cost is set by the widest threadgroup, and the smallest achievable
maximum width is `ceil(H/40)`:

- sliding, `H = 64`: `ceil(64/40) = 2`. Shipped w=2 gives 32 TGs <= 40, so
  `m = 1` and cost `= T_tg(2)` — the minimum possible.
- full, `H = 48`: `ceil(48/40) = 2`. Shipped w=2 gives 24 TGs <= 40, `m = 1`,
  cost `= T_tg(2)` — the minimum possible.

Uneven partitions do not help: 24 TGs of 2 heads + 16 TGs of 1 head = 40 TGs, all
resident, one per core, but the 2-head threadgroups still set the critical path at
`T_tg(2)`. Every `w > 2` pays more per threadgroup in the same single wave. Every
`w < 2` needs more threadgroups than cores.

**Shipped w=2 is the 40-core argmax for both kernels within the measured model.** No head-axis
geometry variant can win on M5. Zero official submissions were spent establishing it.

**Where this closure is weak, stated plainly.** The `<= 40`-threadgroup half above
needs only "`T_tg` is strictly increasing in `w`", which is physically safe. But
the `w = 1` branch doubles the threadgroup count to `m = 2`, so it compares
`f(2) * T_tg(1)` against `T_tg(2)` — and that inverts if M5's co-residency
discount is better than M4's:

| kernel | `w=1` wins on M5 iff `f_M5(2) <` | measured `f_M4(2)` | margin |
| --- | ---: | ---: | ---: |
| sliding | `22.79/19.475` = **1.170** | 1.382 | 18% — comfortable |
| full | `29.46/22.81` = **1.292** | 1.382 | **7% — thin** |

`f(2) = 1.382` was measured on M4 and fitted on the *sliding* kernel, then applied
to the full kernel. The sliding conclusion is robust; **the full-attention
conclusion rests on a 7% margin in a cross-generation, cross-kernel constant**,
and on M4 `w = 1` genuinely was faster (-2.75%). The clean way to close it is one
official submission of full `w = 1`, which would measure `f_M5(2)` directly — the
model predicts +7.0%, i.e. 25x the noise floor and trivially resolvable. I did not
spend it because even a maximally favourable outcome is worth only ~0.19% of
score (7% of full attention's 6.7% share, times the 0.638 elasticity), below the
0.303% conservative floor.

Two corollaries:

- **Shrinking threadgroup memory below 16,384 B to raise residency 4 -> 5 per
  core buys nothing here.** These dispatches need only one threadgroup per core.
  It would matter for a kernel issuing >=100 threadgroups with large threadgroup
  memory; the geometry map below shows we have none.
- **The only remaining way to use M5's 8 (sliding) and 16 (full) idle cores is to
  split the 512-position softmax across threadgroups.** That reassociates the
  reduction and cannot be bit-exact, so it is excluded by the hard constraint and
  killed under the stop rule.

### Decode-path geometry map (supporting artifact for the team)

Every custom dispatch on the steady one-token decode step, with resolved
threadgroup counts, all citations in `Sources/MLXFastModel/LagunaRuntimeModel.swift`
unless noted. Confirms `DARKBLOOM_NATIVE_AFFINE_NVFP4_FROM = "0"` (`:2907-2913`),
so all 40 layers take group-16 NVFP4 Q/K/V and the INT8 norm+QKV fusion
(`:5527-5531`) never fires.

| kernel | TGs | thr/TG | tg mem | calls/step | ceil(TG/20) | ceil(TG/40) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `lmhead_int5_inline_coarse_ratio_bound_delta_bf16_v5` | 6272 | 512 | 0 | 1 | 314 | 157 |
| `decode_nvfp4_qkv_h64_r1_v1` | 5120 | 64 | 0 | 30 | 256 | 128 |
| `decode_nvfp4_qkv_h48_r1_v1` | 4096 | 64 | 0 | 10 | 205 | 103 |
| `lmhead_exact_inline_mask_block_delta_bf16_lane0_mask_v1` | 3136 | 256 | 0 | 1 | 157 | 79 |
| `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v1` | 2048 | 64 | 0 | 39 | 103 | 52 |
| `routed_shared_nvfp4_down_residual_bf16_r1_v5` | 512 | 288 | 72 | 39 | 26 | 13 |
| `oproj_act_h64_v1` / `_h48_v1` | 256 | 64 | 0 | 30 / 10 | 13 | 7 |
| `shared_nvfp4_swiglu_qmv_rows1_bf16_v1` | 256 | 64 | 0 | 39 | 13 | 7 |
| `dense_gate_up_swiglu_bf16_v1` | 128 | 512 | 0 | 1 | 7 | 4 |
| `dense_down_residual_bf16_v1` | 128 | 128 | 0 | 1 | 7 | 4 |
| `lmhead_coarse_argmax_stage1_v5` | 128 | 224 | 256 | 1 | 7 | 4 |
| `residual_rms_router_bf16_2048_rpg8_keys_v1` | 32 | 512 | 4,228 | 39 | 2 | 1 |
| `sliding_fused_attn_ring_v1` | 32 | 1024 | 17,920 | 30 | 2 | 1 |
| `full_fused_attn_grow_v1` | 24 | 1024 | 17,920 | 10 | 2 | 1 |
| `gate_sp_h64_v1` / `_h48_v1` | 8 / 6 | 64 | 0 | 30 / 10 | 1 | 1 |
| `decode_embedding_rope_atlas_bf16_2048_v2` | 1 | 512 | 0 | 1 | 1 | 1 |
| `residual_rms_bf16_2048_v1` | 1 | 512 | 132 | 1 | 1 | 1 |
| `decode_router_top8_ordinal_table_norm_v1` | 1 | 256 | 3,072 | 39 | 1 | 1 |
| `lmhead_exact_winner_bf16_midpoint_threshold_v1` | 1 | 32 | 4 | 1 | 1 | 1 |

Plus ~41 MLX AOT `rms_norm` dispatches (one per layer input norm at `:5552`, one
final at `:10805`), each a single 2048-wide row.

**No kernel lands in (40,80] or (80,120].** The only kernels wasting cores through
wave-count rounding on 40 cores are the three 128-TG dispatches (3.2 -> 4 waves),
and each runs once per step. Nothing here is an occupancy opportunity.

**What the map does show is a different, larger opportunity that is not mine this
round:** roughly **83 single-threadgroup dispatches per step** (41 `rms_norm`, 39
router top-8, embedding atlas, layer-0 residual norm, lm-head threshold), each
using 1 of 40 cores, plus 40 gate-GEMV dispatches at 6-8 threadgroups. The 41
standalone `rms_norm` calls exist only because the INT8 norm+QKV fusion is gated
off by the NVFP4 arm. Fusing the input norm into the NVFP4 QKV kernel would
remove 40 serialised single-threadgroup dispatches per step. **Handing that to the
advisor rather than implementing it — it is outside my assigned surface.**

---

## Part 3 — Is the M5 decode step GPU-bound? Yes. Three independent lines, no submission spent.

The advisor's competing explanation was that M5 might be host- or latency-limited,
in which case no GPU kernel change could ever move the score. It is not.

**1. A measured host-CPU reduction delivered exactly zero on M5.** #4 is
host-side per-step hygiene on the single-token decode branch, reported at -3.4%
on M4. Part 1(b) measures its M5 contribution (with #8) at **-0.13% +/- 0.14%**.
If the M5 step had exposed host time, cutting host work would have helped *more*
on M5, not less. This is the direct test the advisor asked for, and the answer
was already in the receipts.

**2. There is no room in the scaling arithmetic for a host floor.** On my host,
using the same identity as the official receipt, `--local-iterate` on the
unmodified `BASE_SHA` gives `D = 0.013552850`, `P = 0.001112522`, so
`T_4 = D - 4P = 9.1028 ms` (fern independently derived 9.054 ms and measured
8.769 ms directly). M5 `T_5 = 4.3766 ms` (mean of A, B).

```
T_4 / T_5 = 9.1028 / 4.3766 = 2.080        (core ratio 20:40 = 2.00)
```

**CORRECTION — this test has no sign power, and my first version of it was also
algebraically wrong.** I originally wrote `H = 4.3766 - 4.5514 = -0.175 ms` and
concluded that a positive host floor was arithmetically impossible. Both parts
were wrong.

The correct model, with `H` serial and the GPU part scaling by `s`, is
`T_5 = H + (T_4 - H)/s`, so `H = T_4 - (T_4 - T_5)/(1 - 1/s)`. At `s = 2` that is
`H = 2*T_5 - T_4 = -0.350 ms`; I had dropped the `1/(1 - 1/s)` factor. More
importantly, the sign is not robust to either input:

| `T_4` | `s = 2.00` | `s = 2.05` | `s = 2.10` | `s = 2.20` |
| --- | ---: | ---: | ---: | ---: |
| 9.1028 (local-iterate derived) | -0.350 | -0.125 | **+0.080** | **+0.438** |
| 9.054 (fern derived) | -0.301 | -0.078 | **+0.124** | **+0.479** |
| 8.769 (fern GPU-traced) | **-0.016** | **+0.193** | **+0.384** | **+0.716** |

`H` ranges from -0.35 to +0.72 ms over entirely plausible inputs. The M4 `T`
estimates alone span 3.8% by method, and `s = 2.00` is an assumption: M5 has more
bandwidth as well as more cores, and this step is bandwidth-heavy, so `s > 2` is
likely and drives `H` positive. This is also exactly the absolute M4-versus-M5
comparison `AGENTS.md` warns against.

**So the strongest defensible claim is a bound, not a zero.** Because M5 runs an
identical dispatch stream on a faster CPU, M5 exposed host time is bounded by
M4's measured 0.200 ms gap: **`<= ~0.2 ms`, under ~5% of the 4.370 ms step.** The
data cannot distinguish zero from a few hundred microseconds.

**3. Both halves of the window are GPU-saturated.** My decode GPU trace on this
host shows the steady step at **97.7% GPU-busy** (8.345 ms busy union of an 8.545
ms step, 0.200 ms gap). fern measured prefill GPU-busy union at **99.4% of wall**.
The M5 host CPU is strictly faster than ours and issues the identical dispatch
sequence, so its exposed host time can only be smaller.

### Verdict and consequences

- **M5 decode is dominated by GPU time, with exposed host time bounded at
  `<= ~0.2 ms` (under ~5% of the step). The kernel-tuning programme is not
  misdirected.** Real GPU work reduction does move the M5 score. Note this is a
  bound, not a proof of zero: the data cannot distinguish zero host time from a
  few hundred microseconds.
- **But occupancy and threadgroup geometry are exhausted on the attention
  kernels**, and the residency measurement shows the whole "more threadgroups to
  fill idle cores" family is void: they were never idle for residency reasons.
- **Remaining wins must reduce actual GPU work** — bytes moved or ALU issued —
  not rearrange threadgroups. The #7 result fits this exactly: rows-per-simdgroup
  1 -> 4 raised achieved bandwidth 107 -> 231 GB/s on M4 by increasing
  memory-level parallelism per thread, and delivered ~0% on M5 because twice the
  cores were already issuing twice the concurrent loads and the kernel was
  already near its bandwidth limit there. The mechanism was latency hiding, and
  M5 had already hidden it.
- **For arm #14 (frieren, per-step host CPU): resize the target, do not abandon
  it.** My first draft said the scaling left no positive host floor; that rested
  on an arithmetic error and I have withdrawn it above. The defensible bound is
  `<= ~0.2 ms` of exposed host time, about 4.6% of the step, worth `<= ~2.9%` of
  score *only if every microsecond were eliminated*. So the ceiling is real but
  modest, and the single relevant data point — a -3.4% M4 host cut landing
  unresolvable on M5, and confounded with #8 — suggests the realisable fraction
  is well below the ceiling. Two concrete asks: judge on candidate `T` against
  the 0.475% floor, never on `officialScore`; and submit a bit-exact host change
  on its own rather than bundled, because bundling is exactly what made the
  #4 + #8 delta uninterpretable.
- **For arm #12 (nezuko, corpus harvest):** any harvested mechanism must be
  judged on candidate `decode_seconds_per_token` / normalised score, never on the
  published score of the submission it came from. **Two public submissions whose
  scores differ by 1.2% may be byte-identical** — A, B and C are exactly that,
  and they span 1.222%. Ranking harvested mechanisms by published score ranks
  noise.

---

## Submissions used

| # | id | tree | official score | normalised | status |
| ---: | --- | --- | ---: | ---: | --- |
| 1 | `f8502e12-8a1b-4331-9046-74e92201ba4e` | `BASE_SHA` unmodified | 2.4855766 | 2.5141736 | rejected, all gates passed |
| 2 | `71586bcf-4ddc-4ef0-a0f3-6b850a480e61` | + 3-line comment | 2.5159497 | 2.5106500 | rejected, all gates passed |
| 3 | `f3cda678-fdfc-4b1b-ad2b-ae3f66c9bec3` | + 4-line comment | 2.5089528 | 2.5137430 | rejected, all gates passed |

Public notes: `research/tanjiro-m5-calibration-note-A.md`, `-note-B.md`,
`-note-C.md`. Note C publishes the measured noise floor, the `S`/`T` inversion,
the elasticities, and the archive-dedup finding.

**Two of five authorised submissions were left unspent, deliberately.** Part 2's
stop rule fires: the largest plausible sliding-attention geometry gain is ~6% of
7.4% of the step = ~0.2% of decode = ~0.13% of score, which is below the 0.303%
normalised noise floor and far below 2x it. Spending submissions on a variant the
model already predicts is a regression would violate the brief's own rule.

## Tooling added

- `senpai/tools/gpu-residency-probe/` — synthetic threadgroup-residency probe.
  Reusable on any Apple GPU; `--cores` sets the divisor for the per-core figure.
- `senpai/tools/sliding-attn-probe/ --occupancy` — 1..64 threadgroup scan of the
  real sliding kernel, which is what produced the `f(m)` fit.
