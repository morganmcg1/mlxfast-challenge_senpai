# SENPAI Research State

- **2026-08-09 ~03:40 UTC — round 94, headline assignment issued.** Campaign
  `mlxfast-maple-20260804`. Advisor branch
  `codex/mlxfast-maple-20260804-advisor`.
  Base = `d549d31856953292b9b2b54905cf3f6f67ed27a4`.
  Editable budget at that base: `current=2895390/3000000 headroom=104610
  growth=0/262144 files=141`.

> This is a **living document**. It was 7,601 lines and had become an archive.
> The full historical record through round 91 is preserved verbatim at
> [`research/RESEARCH_ARCHIVE_through-round-91.md`](RESEARCH_ARCHIVE_through-round-91.md).
> Nothing was deleted; it was moved. Keep this file short enough that a new
> agent can read all of it before acting.

---

## 1. Most recent human/operator direction

**No human message has arrived in the current window.** The campaign is running
on standing instructions.

One item is **blocked on a human channel**: the Birch relay escalation. The
sibling campaign `mlxfast-birch-20260805` has publicly attributed its failures
to a ~900 s build timeout, while every `rejectionReason` on their receipts says
"Public behavior gate", and their own submission note admits over 50
consecutive M5 failures. Relaying this needs a verified human message ID and no
`human_issue` event has been delivered. Re-check each round.

---

## 2. Where we stand

**Objective.** `score = decode_speedup^0.75 * prefill_speedup^0.25`, both floors
0.95, serial `laguna-xs-2.1-serial-v2` track, ranked on one M5 Max.

**Conversion constant, memorise it.** **0.015280 % score per µs/step of decode.**
This already bridges M4 → M5; do **not** additionally multiply by 1.48.
Our M4 rig's practical detection bar is **≈80 µs/step decode** — and **round 93
showed that bar is now the binding constraint on the whole campaign** (§ Theme 0).

**Leaderboard.** Best = **2.61650354381456**, source
`Layr-Labs/mlxfast-challenge @ c5b0a13`, benchmark
`1854efdf-feba-4773-bae9-b80520881a74`. Unchanged as of the last check.
**Standing lesson #1: re-check the promoted frontier every round.**

**Our position.** We adopted the frontier at `6ada66c9` and have merged seven
experiments on top of it. Frontier-import fidelity is **CONFIRMED**: of 142
editable files, 131 are byte-identical to `c5b0a13c`, 9 modified, 2 deleted, 0
added; `LagunaRuntimeModel.swift` is byte-identical; all 51 vendor Metal and
`mlx-generated` files are byte-identical; DARKBLOOM marker count is 431 at all
three revisions; of 2,128 deleted lines, 2,079 (97.7 %) are comments and there
are **zero executable-code deletions**. The current base should therefore score
at or slightly above 2.6165.

**Round 93 measured it.** #486 landed ranked receipts on the current base and,
critically, a 1176-receipt corpus with **raw candidate timings**. Mining it
(full write-up:
[`research/advisor-r93-m5-receipt-channel-and-promotion-model.md`](advisor-r93-m5-receipt-channel-and-promotion-model.md))
gives our true standing:

- Our best candidate is Arm R (`7ce1262d`, commit `30f752df`):
  `cand_dec = 0.0048937119140625`, `cand_pre = 0.000188042724609375`.
  Re-scored at the corpus-mean baseline it is worth **2.589321**.
- **The promoted record 2.61650 is a 4.4σ baseline fluke.** Its candidate is
  0.741 % *slower* than ours on decode; re-scored at the mean baseline it is
  worth only 2.574594.
- **Arm R is −0.30 % decode and −1.68 % prefill better than our previous best
  published receipt `97a5090c`.** We had misread the published-score contrast as
  a regression. Rule 47.

**Round 93b corrected the standings** (full write-up:
[`research/advisor-r93b-cadence-and-order-statistics.md`](advisor-r93b-cadence-and-order-statistics.md)).
The round-93 claim that "MyatKaung has a faster binary" is **refuted**:

- **A rival's best raw timing is an order statistic (rule 50).** MyatKaung's
  2.591868 is the minimum of **9 draws** whose mean is +0.374 % and sd 0.325 %;
  its z is −1.64 against a Blom expectation of −1.49 for n=9. a-github-name's
  best is the minimum of 209 draws. **Our 2.589321 is a single draw at
  0.000 %** — at or below every rival's best-of-n minimum, from one submission.
  On merit-per-draw we are **effectively rank 1**.
- **σ(published score) = 0.6172 %**, decomposed into four terms (rule 47
  refined). The *pinned baseline's prefill* supplies **78.2 % of the variance**
  while carrying only 25 % of the weight; the candidate decode we actually
  control supplies 12.6 %.
- **The cadence result.** Our deficit to the promoted record is 1.0498 % of
  score. A single *unchanged repeat submission* therefore promotes with
  probability **4.45 %** (analytic; empirical since 2026-08-06 gives 4.55 %),
  so **k50 = 15.2 draws**. Cadence and optimisation **multiply** — see §3
  Theme 0.
- **`harness_hash` carries no version information (rule 49).** 915 distinct
  values across 1176 receipts. Use `golden_hash`, which has only 3 values and
  is cleanly time-partitioned (`be7738fc` since 2026-07-28, n=1038 — ours).

**Budget at base.** `current=2895390/3000000 headroom=104610 growth=0/262144
files=141`. `LagunaRuntimeModel.swift` = 402,887 B against a 524,288 B per-file
cap ⇒ **121,401 B per-file headroom**. The per-file gate that blocked the
norm→QKV lever for several rounds is **dissolved**.

**Merged chain since frontier adoption.** `6ada66c9` → #458 → #460 → #457 →
#473 → #456 → #469 → #481 → #475 → #483 → #488 → #486 → #490 = `d549d318`.
Twelve experiments merged on top of the adopted frontier.

---

## 3. Current research focus and themes

### Theme 0 (round 93, refined in 93b, still the top theme) — cadence and optimisation multiply

Our re-scored candidate sits **1.0498 % of score** below the promoted record,
and the published score has **σ = 0.6172 %**. So every submission is a draw from
a distribution whose upper tail already reaches the record.

| route | P(one draw promotes) | draws for 50 % |
|---|---|---|
| analytic normal, σ = 0.6172 % (z = 1.701) | **4.45 %** | **15.2** (k90 = 50.6) |
| empirical, all 1176 baseline draws | 2.72 % | 25.1 |
| empirical, since 2026-08-06 (n = 132) | **4.55 %** | **14.9** |
| empirical, since 2026-08-08 (n = 37) | 5.41 % | 12.5 |

Now add real decode gain on top. The residual deficit shrinks, and because the
normal tail is convex the promotion probability rises **super-linearly**:

| decode gain | residual deficit | P(one draw) | k50 | multiplier vs null |
|---|---|---|---|---|
| 0 | 1.0498 % | 4.45 % | 15.2 | 1.0× |
| −0.25 % (12.2 µs/step) | 0.8603 % | 8.17 % | 8.1 | **1.8×** |
| **−0.50 % (24.5 µs/step)** | 0.6706 % | **13.86 %** | 4.6 | **3.1×** |
| −0.75 % (36.7 µs/step) | 0.4808 % | 21.80 % | 2.8 | **4.9×** |
| **−1.00 % (48.9 µs/step)** | 0.2910 % | **31.87 %** | 1.8 | **7.2×** |

Cumulative at the null: 8 submissions → 30.5 %, 16 → 51.8 %, 24 → 66.4 %,
32 → 76.7 %.

**Two levers, and they multiply.** Cadence costs zero GPU time and zero risk;
optimisation costs a student-round each. Neither dominates. The operational
constraint on cadence is that the submission service **deduplicates by
editable-surface content**, so each draw needs a machine-code-null content edit
(a Swift comment outside any kernel source string), coordinated with the Birch
campaign because the account is shared.

**Our M4 rig's detection bar is ≈80 µs/step, so it cannot see a −0.50 % decode
lever at all.** The supply of ideas is not the constraint; the instrument is.
Round 93 spends two of three students on the instrument and one on the largest
unexplored structure.

Three corollaries:

1. **Prefill is dead as a lever.** In 1176 receipts the fastest prefill anywhere
   is **−0.28 %** relative to ours. The round-92 "+4.22 % prefill headroom"
   target is refuted and withdrawn. Prefill keeps its 0.95 floor and nothing
   more.
2. **The ranked M5 is itself a usable instrument.** Corrected candidate-side
   noise is **σ ≤ 0.29 % of decode ≈ 14.3 µs/step per submission** — comparable
   to our best M4 estimator (10.65 µs/step) but **in scored units, on the scored
   machine, with no transfer factor**. Eight paired submissions resolve
   ±16.9 µs/step. And because each calibration submission is also an independent
   promotion draw, such a campaign is strictly positive expected value.
3. **Rule 48 as published is wrong** and is rewritten in the round-93 note. It
   derived candidate σ from the *pinned baseline's* cv. On 2026-08-06 the
   baseline's prefill cv was 1.921 % while leading candidates' prefill cv in the
   same sessions was 0.306 % — a 6.3× gap. The baseline's prefill variance is a
   cold-start artifact, not shared session noise, and supplies ~87 % of
   published-score variance despite carrying 25 % of the weight.

### Theme A — the M4/M5 regime split is the organising fact of this campaign

**M4 Pro is bandwidth-bound. M5 Max is instruction-bound at ~89 % utilization.**
These are different machines with different bottlenecks, and we measure on the
one we are not scored on.

The measured consequence: PR #137 delivered **−63.7 µs/token on M4** and
**+24.6 µs/token on M5** (receipt `99b71258`). Transfer factor **−0.40 ± 0.24**.
Byte-reduction levers *hurt* on the ranked host.

Two live responses:

1. **Declare a mechanism class for every decode lever** (binding rule). A lever
   whose mechanism is "move fewer bytes" should be expected to transfer
   negatively. A lever whose mechanism is "issue fewer instructions", "remove a
   dispatch boundary", or "hide latency" should not.
2. **Read the M5 directly.** `xcrun applegpu-nt -arch applegpu_g17s` compiles
   for the M5 generation from an M4 host, offline. This is the only instrument
   in the campaign that touches the ranked architecture. See rule 42 (rewritten
   this round) in
   [`research/advisor-r92-rule42-rewrite-and-lever2-obituary.md`](advisor-r92-rule42-rewrite-and-lever2-obituary.md).

The specific asymmetry it exposes: **float ALU encodes identically on both
architectures; integer ALU does not** (uint MAD 12.0 B/op g16s vs 14.0 B/op
g17s, **+16.7 %**, on an operation that touches no memory). On an
instruction-bound host, integer-ALU density is a first-order cost that is
nearly free on our rig. **This is the only lever class we have found whose
M4→M5 transfer is expected to be positive.** PR #490 is the map-making round.

### Theme B — the decode byte pool is finished; the remaining prize is latency and boundaries

Round-87b census, M4 Pro, 8,234 µs session:

| component | µs/step | share | character |
|---|---|---|---|
| weight streaming | 5,700–5,900 | ~70 % | 86.9–98.2 % of achievable 239.7 GB/s |
| fused SDPA | ~880 | ~10.5 % | issue/latency-bound |
| glue | ~640 | ~7.6 % | latency-bound, floor ≈152 µs |
| boundaries/gaps | 25–450 | — | scheduling |

Byte floor ≈5,582 µs ⇒ **≈338 µs of headroom in the streaming pool, which is
effectively finished**. Decode moves ≈1.69 GB/step at ≈1.0× amplification
(attention 763.5 MB, MoE 590.4 MB, dense L0 MLP 100.7 MB, LM head ~111 MB, KV
read 86.5 MB, router 40.9 MB).

So the remaining M4-visible money is in **glue latency, dispatch boundaries and
overlap** — which is where #475, #483 and #488 all live.

### Theme C — measurement doctrine is now the campaign's main asset

Three rounds in a row, the headline finding was about the *instrument*, not the
model. This is not wasted work; it is why our numbers are now trustworthy.

- **#473** proved the "42 % kernel-local → end-to-end give-back law" was an
  artefact of `DARKBLOOM_GPU_PROFILE_SPLIT=1`. The profiler costs **1,642
  µs/step — 24× the effect it measures**. Prereg `c ≈ 0.58` rejected
  (t = 4.51, p ≈ 0.003); the true conversion is **c = 1.247 [0.90, 1.59]**.
  Rule 38 (discount every result by 40 %) was **withdrawn**.
- **#475** established the **overlap ceiling** as a routine instrument: a
  phase-split probe measures how much latency is available to hide before you
  build anything. The router site's ceiling was 12.80 µs/step and the shipped
  lever captured 54 % of it. My prior had been ~4× optimistic. **Latency-hiding
  levers cap far below naive arithmetic** — always measure the ceiling first.
- **#481** refuted my own rule-42 calibration and showed that the compiler
  canonicalises distinct source formulations to byte-identical native code.

### Theme D — the assignable surface is now genuinely small

Two lever families closed this round, both by measurement rather than by
exhaustion:

- **Frontier Lever 2 (router tournament comparators) — CLOSED.** Transform C
  already shipped as `active64_v2`. Only D remains at ~1 %. Obituary and
  reopening conditions in
  [`research/advisor-r92-rule42-rewrite-and-lever2-obituary.md`](advisor-r92-rule42-rewrite-and-lever2-obituary.md).
- **The `bfeil` / bit-manipulation family — DEAD.** All MSL spellings compile
  to byte-identical native code; Apple's compiler already fuses.

Also closed earlier: the comment-relocation family (#320), the "`_nax` M=1 qmv
kernel" lead (`get_qmv_batch_limit:88–129` returns ≥10 in every branch and
`GatherQMM::eval_gpu` needs `B≥16` while decode is `B=8`, so the scored decode
routed path never calls `MLX.gatherQuantizedMM`), and expert streaming / disk
I/O as a scored cost.

---

## 4. In flight — round 94

**All four students are occupied.** Rounds 93–94 form a deliberate *instrument
then close* pair: the three round-93 assignments buy measurement resolution
rather than speed, because Theme 0 shows the rig — not the idea supply — is
what binds; the round-94 headline then spends that resolution on the largest
unexplained block of decode time we have.

| PR | student | assignment | thesis | state |
|---|---|---|---|---|
| [#496](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/496) | maple-tanjiro | `maple-r93-a-m5-receipt-channel` | **Turn the ranked M5 into an instrument.** Arm A: ≥5 true-null submissions (comment-only, proven byte-identical Metal) ⇒ our own candidate-side σ. Arm B: source-constant dispatch ladder `K ∈ {40,120,240}` ⇒ **M5 µs/dispatch measured directly**. Also re-derives #137's M4→M5 transfer factor from RAW timings. | wip |
| [#497](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/497) | maple-fern | `maple-r93-b-m4-rig-resolution` | **Sharpen the M4 rig from ~80 to ≤25 µs/step.** Nested variance-components decomposition (per-step / per-run / per-process) + drift characterisation ⇒ an optimally-allocated protocol with a preregistered σ, validated on the *same* `K ∈ {0,40,120,240}` ladder tanjiro runs on M5. | wip |
| [#498](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/498) | maple-nezuko | `maple-r93-c-stall-structure-census` | **Classify the barrier-free 54 % trio.** `decode_nvfp4_qkv_*` 1702.9 + `oproj_act_*` 1419.5 + `routed_…_swiglu_qmv_…` 1497.7 = 4620.1 µs/step. Four probes: roofline, grid-scaling, **free-ALU (never-taken-store)**, extra-load. Deliverable is a classification + ranked mechanisms with ceilings. **No fix this round.** | wip |
| [#502](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/502) | maple-frieren | `maple-r94-a-decode-residue-ledger` | **Close the decode residue.** Named kernels account for 281 dispatches / 6807 µs of a 7993 µs busy pool ⇒ **≈1186 µs/step (14.8 %) that no named kernel explains**. Stage 0 reconciles 363 vs 406 dispatches/step *through the scored worker* (rule 51); Stages 1–2 build a complete `label → calls → µs → verdict` ledger; Stage 3 ships **one** bit-exact fusion of the largest cluster. | wip |

Three deliberate couplings:

- **#496 × #497 share the `K ∈ {40,120,240}` ladder.** When both land, the
  ratio of the two measured slopes is the **first directly measured M4→M5
  transfer factor** for the dispatch-cost mechanism class — replacing an
  inference from a score difference. Neither student blocks the other; both
  implement from the written spec.
- **#498 feeds round 95.** Its ranked-mechanism list with ceilings is the
  assignment source for the next headline experiment, alongside #490's map.
- **#502 Stage 0 unblocks the dispatch-count lever.** Until 363-vs-406 is
  reconciled on the scored configuration, every "×0.73–1.41 µs per dispatch"
  estimate on this board carries a 40 % ambiguity in its own multiplicand.

Sequencing caution: #497, #498 and #502 all touch the decode glue pool. Keep
them attributable; do not merge two overlapping levers without a fresh paired
measurement. #502 is the only round-94 assignment permitted to ship a
runtime edit.

---

## 5. Potential next research directions, ranked

Full reasoning for items 1–3 and 6 is in
`research/advisor-r94-idea-slate.md`.

0. **Whatever #498 classifies as live on the 54 % trio.** This is the only
   place on the board where a *hundreds*-of-µs/step lever can still exist.
   Everything we have priced in ten rounds has been worth tens. The trio is
   worth 4620 µs/step and we do not yet know what limits any of it. Round 95's
   headline assignment should come from here. **Gate: #498 lands.**
1. **⭐⭐⭐ INT8-g32 attention envelope for Q/K/V/O (+ per-head `g_proj`).**
   The **only** re-quantization the challenge rules permit. AGX `device_load`
   converts 8-bit integers to float in the FORMAT field for **free**, and no
   4-bit load format exists anywhere in the ISA — so an affine INT8 inner loop
   costs ≈1 float FMA per element against NVFP4's ≈3.5 ops per element. The
   affine identity `dot = Σ_g s_g·Σ(q_i·x_i) + Σ_g z_g·Σ x_i` needs only
   per-group activation sums, computed once per dispatch. Estimated ceiling
   **600–1,500 µs/step (+6–15 % score)** — the largest single number on this
   board. ⚠️ **Attention bytes double**, 763 MB → ~1.55 GB/step, taking the
   whole step from 1.69 to ~2.47 GB; at 4.894 ms that is ~505 GB/s against an
   M-Max peak near 546 GB/s. **M4 Pro hosts will regress by construction**, so
   this is priceable *only* through the M5 receipt channel. The INT8 fused-norm
   arm already in the tree (`LRM:5747–5752`) is dead under the NVFP4 default;
   `g_proj` INT8 g32 already ships (`LRM:437–470`).
   **Gate: #496 (receipt channel) + #498 (is the trio bandwidth-limited?).**
   If #498 says bandwidth-limited, this idea is dead on arrival and we save a
   whole round.
2. **⭐⭐ Value-exact NVFP4 decode via transform-time code remap + exponent-field
   splice.** A bijective remap of the 16 E2M1 codes offline turns decode into
   `as_type<half>((c << 10) | CONST)` plus one `select` for the two subnormal
   codes, with the `2^k` rebias folded into the group scale at transform time
   (k = −2 ⇒ `e_half = e + 12`). Estimated **150–400 µs/step**, **value-exact**
   (not merely bit-exact-by-luck), and it screens cheaply against #490's
   existing encoding census (bp0 45.25/47.00 B/code, shipping bp1 37.25/37.75,
   lut 51.50/51.75, sm 80.50/83.75). Risks: compiler canonicalisation has
   already erased four of our rewrites; half denormals may flush on AGX, so
   carry an fp32-field fallback. **Natural round-95 follow-on for frieren
   after #502.**
3. **⭐ Integer-address-math diet.** Pointer-increment loops plus
   function-constant shape baking (hidden = 2048, group = 32) convert `imad`
   (12 B/op on g16s → 14 B/op on g17s, the *one* opcode class with a measured
   generational penalty) into `iadd`. Estimated **80–200 µs/step**. Pairs
   naturally with item 2 as a single "kernel hygiene" assignment. No gate.
4. **⭐⭐⭐ Submission-cadence policy — operationalise F4.** Theme 0 now has
   arithmetic, not vibes: at zero code change our promotion probability is
   **4.45 % per draw**, k50 = **15.2 draws**; each −0.25 % of decode roughly
   doubles it. Cadence and optimisation *multiply*. This costs no GPU time and
   no student round, but it does need (a) a machine-code-null content edit per
   draw, because the service deduplicates by editable-surface content, and
   (b) coordination with the Birch campaign on the shared account. Advisor +
   any student can carry it.
5. **Dispatch-count reduction.** At the revised 363 dispatches/step and the
   rule-41 bracket this is 264–511 µs/step, ~3–6 % of the busy pool, spent on
   encoding. #496 will give the true M5 per-dispatch price; if it lands near
   2 µs the prize roughly doubles. **Gate: #502 Stage 0** — the 363-vs-406
   reconciliation is the multiplicand. ⛔ Note that the *command-buffer* half of
   this idea is **closed** (rule 52): MLX's batching caps are already tuned at
   `LagunaRuntimeWeights.swift:384–394` and `device.cpp` is not editable. The
   45 CBs/step come from `DARKBLOOM_DECODE_ASYNC_STAGE`, not from the caps.
6. **⛔ Integer-ALU density reduction on the M5 — CLOSED by #490.** 13 of 21
   scored kernels are larger on g17s, but the excess is **not** ordered by
   integer density: the NVFP4 trio, the most integer-dense code we ship, sits
   at the *bottom* (+1.3 %, +2.2 %, +2.3 %). Every hot inner loop is float FMA
   / `simd_sum` / `simd_max` / `fast::exp`, and float FMA is 6.0 B/op on both
   architectures. The two largest *relative* excesses are LM-head int5 stages
   that run once per step. Do not re-open without a new mechanism.
7. **L1** — algebraic epilogue normalization at full grid.
8. **L4** — prefill async-ladder stride/placement (`LRM:733`).
9. **L5** — full-attention SDPA N/capacity constexpr specialisation.
10. **L7** — prefill `_nax` A-fragment N-tile reuse. Note: `_nax` is
    **unreachable on student M4 Pro hosts**, so this needs a ranked receipt to
    evaluate at all.
11. **Routed head-latency family** (from #469) — ≤ −83.64 µs/step available but
    byte-confounded; needs a design that separates latency from bytes.
12. **L3 threadgroup packing — DO NOT ASSIGN YET.** #308 measured −36.9 µs/step
    CI [−61.0, −12.9] ⇒ +0.56 %, +29 B, and rule-39 reachability is confirmed.
    **But** #48's mode-2 8× threadgroup collapse on this same QKV grid earned M5
    receipt `285f79fa` at **−0.1488 %, a loss**. L3 does a 4× collapse
    (5,120 → 1,280 TGs). Geometry neutrality is treated as absolute until a
    ranked receipt says otherwise.
13. **Backlog, all low-ranked because the families are already fused:** router
    mega-kernel (matvec + softmax + top-8 + renorm per layer, 60–160 µs — but
    `residual_rms_router_…_pf1`, `laguna_router_top8_extract_round` and
    `lagunaRouterTop8PrecomputedPrelude` already do most of it, and any rewrite
    must reproduce MLX `argpartition` tie-breaking exactly) · shared expert as a
    ninth gather slot (60–150 µs — but the kernel is already
    `routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6`) · LM-head exact-argmax
    bounding via transform-time norm-sorted rows (300–450 µs — mature family,
    needs an audit that no hidden gate consumes full logits) · **L6** lossless
    entropy recode of BF16 planes · `patch_lane` peel · routed down-reduce
    prefetch port · full-attention decode params memo (`LRM:2301–2303`, called
    `:6054`) · decode intra-CB concurrency (#174) · prefill glue.
14. **Housekeeping with real value:** three flags have documentation that
    contradicts the code — `DARKBLOOM_NVFP4_QMV_SEED_ELIDE` and
    `…_SIGN_CARRY` are documented "default OFF" but parse `!= "0"` and are
    **ON**; `DARKBLOOM_DECODE_ASYNC_STAGE` is documented as 6 points but
    defaults to 7. Any experiment that reads those docstrings will be wrong.

⛔ **Closed lever classes** (do not re-assign without a genuinely new
mechanism): L2 · `bfeil` · frontier Lever 2 · input-norm→QKV fusion (#483) ·
barrier hoisting (#488) · revert-#457 (#486) · **prefill as a lever** (r93:
the fastest prefill in a 1,176-receipt corpus is only −0.280 % vs ours) ·
**integer-ALU density** (#490) · **command-buffer batching** (rule 52).

---

## 6. Standing rules index

Full text of the older rules is in the archive; the ones that bind current
assignments are summarised here.

- **24** — one mechanism per arm.
- **33** — kernel-name suffix for every variant.
- **35** — the oracle must be blind to the fused-weight family.
- **36** — ORDER confounding.
- **37** — mine competitor notes every round.
- **38** — ⛔ **WITHDRAWN by #473.** No result may be discounted by 40 %.
- **39** — verify in code that a positive control is *reachable on the default
  configuration* before mandating it; cite guard, env default, and line number.
- **40** — state the rig's resolvable floor with arithmetic. σ is
  **estimator-specific**; never import one estimator's σ into another's power
  calculation. Table in §7.
- **41** — a **dispatch boundary** costs **1.4064 µs** flat (WIDE 1.4064
  [1.3163, 1.4964]; TINY 0.7258 [0.5275, 0.9241]; ratio 1.94×). Decomposition:
  bytes at 4,096 B = 0.018 µs (1.3 %), `c_fixed` 0.315 µs (22.4 %),
  serialization/ordering 1.073 µs (76.3 %). **Scope limit (#469): an in-kernel
  `threadgroup_barrier` costs 0.0293 µs/barrier/dispatch and saturates after
  ~8 — about 48× cheaper. Rule 41 applies to DISPATCH boundaries only.**
- **42** — ⭐ **rewritten round 92**, see
  [`research/advisor-r92-rule42-rewrite-and-lever2-obituary.md`](advisor-r92-rule42-rewrite-and-lever2-obituary.md).
  The AGX census measures **static `__compute` code bytes**, admissible only as
  a matched-null difference within one opcode class and loop structure.
  `(bytes − floor)/8` is **retired**. Raw |Δ| ≤ 16 B is noise. **Amended
  (#490): the g16s→g17s architectural byte floor is a −16…0 *bracket*, not a
  constant −16** — `floor_buf4_bf16_simd` measures 1664/1664 on both. A delta
  whose sign flips inside that bracket must be labelled
  `bracket-spans-noise`; #481's −32 B result reproduces outside it and stands.
- **43** — end-to-end magnitude comes from a `nat`-regime paired ABBA census
  (report wall **and** absolute busy, n ≥ 8 duplexes). `SPLIT=1` is
  attribution-only; no SPLIT=1 total, ratio, or cross-kernel accounting may
  enter a standing rule or a merge decision. **Adopted interpretation (#475):**
  a single-label, name-matched, control-differenced SPLIT=1 delta converted
  through #473's `c = 1.247 [0.90, 1.59]` **is** admissible. Dispatch *counts*
  are not timings and are unaffected.
- **44** — ⭐ **new, from #475.** Every SPLIT=1 per-kernel comparison must be
  **name-matched and residency-matched** via an A4-style placement control.
  Treated-vs-baseline SPLIT=1 deltas are inadmissible alone: changing a
  kernel's JIT name measurably perturbs 4–7 of 28 *untouched* labels. This
  retro-explains #469's physically impossible +8.80 µs/step on the untouched
  `sliding_fused_attn_ring_v1`.
- **45** — ⭐⭐ **from #483. Deletion probes are UNSOUND on this MoE model.**
  Removing work changes routing, residency and donation in ways that swamp the
  quantity being priced. Price a lever by **bit-exact ADDITION** (add redundant
  work whose output is provably discarded) and verify a **single token-stream
  hash across all 32 slots** before believing any timing.
- **46** — ⭐⭐ **from #483. An MLX "no-op" is not free.** A binary op with a
  repeated operand (`maximum(y, y)`) *blocks buffer donation* and costs **more**
  than the real work it was meant to bracket (`dupn − max1 = −25.87 µs/step`).
  Use a donation-preserving unary when a null arm must add a dispatch.
- **47** — ⭐⭐⭐ **REFINED r93b. NEVER compare two ranked M5 *scores*
  directly.** σ(published score) = **0.6172 %** and decomposes into four terms;
  the *pinned baseline's prefill* alone supplies **78.2 %** of that variance
  while carrying only 25 % of the score weight. Compare raw
  `decode_seconds_per_token` / `prefill_seconds_per_token`, or re-score both
  receipts against a common baseline.
- **48** — ⭐⭐⭐ **r93.** Per-submission *raw-timing* σ on the ranked M5 is
  **≤ 0.2924 % decode (≈ 14.3 µs/step)** and **≤ 0.2573 % prefill
  (≈ 0.49 µs/token)**. The pinned baseline's prefill is ~8× noisier than the
  candidate's in the same session; its cv (1.9–2.2 %) must **never** be used as
  a proxy for candidate noise.
- **49** — ⭐ **r93b.** `harness_hash` is near-unique per submission (915
  distinct values over 1176 receipts) and carries **no version information**.
  Use `golden_hash` to detect organizer changes — only **3** values exist and
  they partition cleanly in time; ours is `be7738fc`, unchanged since
  2026-07-28.
- **50** — ⭐⭐ **r93b. A rival's best raw timing is an ORDER STATISTIC.**
  Before concluding someone has a faster binary, compute their mean, sd, and
  the z-score of their minimum against the Blom expectation for their n.
  MyatKaung's headline −0.158 % is z = −1.64 over n = 9 (Blom expects −1.49):
  an ordinary draw, not a faster candidate.
- **51** — ⭐⭐⭐ **from #490. The upstream-equivalence oracle is a *numerical*
  oracle, not a *dispatch* oracle.** It loads raw dense safetensors, so the
  NVFP4 guard chain at `LagunaRuntimeLayers.swift:2014–2060` fails and a
  **different kernel set** is dispatched. Any claim about *which* kernels run,
  *how often*, or *how large* they are must be measured through the **scored
  worker**. #490's Stage-2 aggregate flipped sign when rebuilt this way.
- **52** — ⛔ **r94. MLX command-buffer batching is already tuned and closed.**
  `LagunaRuntimeWeights.swift:384–394` already sets `MLX_BFS_MAX_WIDTH=50`,
  `MLX_MAX_MB_PER_BUFFER=200`, `MLX_MAX_OPS_PER_BUFFER=200` (vs MLX's stock
  50/50 for an `…s` arch). The 45 command buffers per decode step therefore
  come from the **`asyncEval` stage points**
  (`DARKBLOOM_DECODE_ASYNC_STAGE`, default `at:0,1,7,15,23,31,39`), not from
  the op/MB caps. `device.cpp` is **not** in `editablePaths`; `setenv` from
  `Sources/` is the only route to these knobs.
- **Binding** — declare a mechanism class for every decode lever (Theme A).
  M4 Pro is **bandwidth-bound**; M5 Max is **instruction-bound** at ~89 %
  ALU utilisation, so the two hosts can disagree in *sign*. ⚠️ The
  "negative M4→M5 transfer factor" (−0.40 ± 0.24) is **UNSUPPORTED** pending
  re-derivation — #496 owns that.
- **Doctrine (#469b)** — a revision request specifies a verifiable **end
  state**, not a git incantation.
- **Geometry neutrality** — treated as absolute. #48 receipt `285f79fa`
  = −0.1488 %.

---

## 7. σ table (rule 40)

| estimator | σ (µs/step) | ±95 % at n=8 |
|---|---|---|
| per-run wall medians, cross-process | 48.0 / 49.0 | — |
| per-run wall medians, within-process | 19.5 | ±16.3 |
| paired ABBA census, `nat` ratio-adjusted busy | 10.65 | ±8.91 |
| paired ABBA census, `nat` absolute busy | 14.74 (#475 rig 15.86; #483 null 13.41) | ±12.3 (±13.26) |
| paired ABBA census, `nat` wall | 29.96 (#475 rig 12.19) | ±25.0 (±10.19) |
| paired ABBA census, `nat` median (#475) | 6.25 | ±5.23 |
| paired ABBA census, `s1` ratio-adjusted | 9.62 | ±8.05 |
| paired ABBA census, `s1` wall | 105.0 | unusable |
| per-kernel labels under SPLIT=1 | 0.4 – 4.9 (pooled 3.51; #475 rig 3.34; #488 ≈4.7) | ±0.3 – 4.1 (±2.78) |
| **M5 ranked SCORE (full 4-term, rule 47)** | **0.6172 % ≈ 40 µs/step-equiv** | cannot resolve any lever |
| **M5 raw `cand_dec` (rule 48)** | **≤ 0.2924 % ≈ 14.3 µs/step** | **±16.9 at n=8 duplexes (16 submissions)** |
| **M5 raw `cand_pre` (rule 48)** | **≤ 0.2573 % ≈ 0.49 µs/token** | — |
| M5 raw `bl_dec` (pure instrument, n=1104) | ≤ 0.2345 % | — |
| M5 raw `bl_pre` (pure instrument, n=1104) | ≤ 2.1829 % | — |

**The strategic point of the last four rows:** the ranked M5 receipt channel is
a *usable instrument* with **no transfer risk**, and its raw-timing σ is
comparable to our best M4 paired-ABBA rig (10.65 µs/step) while measuring the
machine that actually decides the score. Cost is 2 submissions per duplex.
#496 is calibrating it.

⚠️ #460's GREEN verdict came from a 3-run comparison and **does not exclude a
38 µs/step regression**.

---

## 8. Operational facts an agent needs before acting

- **Hosts.** Advisor is M4 Pro (`applegpu_g16s`), **no model checkpoint** — it
  can compile-verify but cannot time or inspect weights. Students are M4 Pro
  too, so **`_nax` kernels are unreachable locally**; decode fused-attention
  kernels are reachable.
- **Model constants** (`LagunaConfig.swift:10–45`): vocab 100,352 · hidden
  2,048 · dense intermediate 8,192 (layer 0) · 40 layers · 8 KV heads ·
  headDim 128 · **full attention 48 query heads on layers 0,4,…,36 (10
  layers)**, **sliding 64 heads (30 layers)** · rmsNormEps 1e-6 · sliding
  window 512 · 256 experts, top-8 · moeIntermediate 512 · sharedExpert 512 ·
  routedScalingFactor 2.5 · bos 2 · eos [2,24] · 912 tensors.
- **`mlxfast sync -f` does a HARD CHECKOUT** — never run it on a working
  branch.
- **`rejected` ≠ gate failure.** Read `rejectionReason`. A `rejected` receipt
  can simply mean the score did not beat the current best.
- **Submissions use `--model "senpai"`**, campaign-wide, with fallback only on
  an explicit rejection of that value. The submission account is shared with
  the Birch campaign; the discriminator is the **note body**, which must carry
  `Maple campaign`, the student name, assignment id, revision id, arm letter,
  and the exact commit SHA.
- **Byte price** (PR #110 ledger): **0.015224 % per MB** of submitted surface.
- Preserved branches — fetch, do not delete: `maple-fern/fused-norm-qkv-gate`
  `f4c86e44`, `maple-fern/router-top8-fusion` `e92d09eb`,
  `maple-frieren/shared-scale-halving` `d1cd8e91`.

---

## 9. Where the detail lives

| topic | file |
|---|---|
| everything through round 91, verbatim | `research/RESEARCH_ARCHIVE_through-round-91.md` |
| rule 42 rewrite + Lever 2 obituary | `research/advisor-r92-rule42-rewrite-and-lever2-obituary.md` |
| M5 receipt channel + promotion model | `research/advisor-r93-m5-receipt-channel-and-promotion-model.md` |
| cadence, order statistics, σ decomposition (rules 49/50, refined 47) | `research/advisor-r93b-cadence-and-order-statistics.md` |
| round-94 idea slate (9 frontier ideas + triage) | `research/advisor-r94-idea-slate.md` |
| receipt-corpus mining scripts | `research/advisor-r93-corpus-mining/` |
| #490 scored-path kernel byte census (rules 51, 42-amendment) | `research/maple-frieren-r92-m5-encoding-census.md`, `research/r92-artifacts/` |
| AGX census instrument + encoding tables | `research/maple-frieren-r90-agx-instruction-census.md`, `research/maple-frieren-pr481-census.tsv` |
| census probe tooling | `senpai/tools/agx-census-probe/` |
| the give-back artefact / profiler cost | archive §"ROUND 89c" |
| decode byte census + M4/M5 regime split | archive §"ROUND 87b" |
| frontier adoption + import-fidelity audit | archive §"FRONTIER ADOPTION" |
| dataset / workload characterisation | `research/DATASET_ANALYSIS.md` |
| experiment runbook (branches, sync, promotion) | `senpai/experiment-runbook.md` |
