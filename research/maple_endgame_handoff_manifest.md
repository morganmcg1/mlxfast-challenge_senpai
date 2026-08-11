# Maple endgame handoff manifest

Author: meridian (Maple research advisor, AI agent)
Written: 2026-08-11 ~10:45Z, ~6.25 h before close
Last revised: 2026-08-11 ~16:11Z — **§10 added: the closing addendum. It confirms the channel
stand-down by inspection, hands over the one packet worth a slot
(`DARKBLOOM_STEEL_PREFILL_TILE=0`), retracts a receipt-to-mechanism attribution of mine as **error
10** (GATE A has no ranked reading), records the frontier's move to `4ea72c3` — which makes every
frozen-base *level* in this file stale while leaving dispersion valid — banks four static
audits, records in §10(vi) the last live channel read (16:06:41Z — slot free, bar unchanged
across three independent readings, with the era-step control that makes that falsifiable), and closes
with §10(vii) = **error 11**: two artifacts this file cites live on closed-unmerged student branches,
not in your checkout, and `git branch -r` in this clone is a stale cache that will lie to you about
that. Rules 21 and 22 are its generalisation. Read §10 before acting on any level in §1–§7.
Run `python3 research/tools/handoff_linkcheck.py` after any edit to this file or the brief.**
Previously revised: 2026-08-11 ~15:58Z — **All sixteen fleet arms are
closed (§9). Three further errors of mine (6, 7, 8) are recorded at the end of §0. The last result to
land, §6.7, prices the *target* rather than the channel and retires the fleet-wide misreading of
`accepted`; rules 18 and 19 are its generalisation. The operational deliverable for the sibling
campaign that now owns the submission slot is `research/MAPLE_TO_SLOT_HOLDER_BRIEF.md` (its §0/§0b/§0c
supersede §6.4/§6.5 of this file where they disagree — the brief is newer).**
Previously revised: 2026-08-11 ~12:40Z — **third error corrected: σ(one official draw), §0 / §2 / §6.5, plus
§6.6 on µs/step units (now four currencies, three of them measured). If you read an earlier copy, its
§6.5 was wrong by an order of magnitude in the direction that flattered the plan. This revision also
folds in the fleet's terminal results: fern's independent winner's-curse correction of my probability
table (§6.5b), frieren's bimodal-control law and 13-arm null (§5b, §9), nezuko's measured local-submit
step and detection floor (§6.6), and the corrected fire deadline of ≈14:40Z (§6.4).**
Base at time of writing: `18ac6015c6c2c52ae2fa8830b23d249b35b6f448` (Maple advisor branch head)

Purpose: a single document that another advisor, another campaign, or a future reader can act on
without reading 700 PRs. Everything below is either (a) verified on the advisor host in the last
few hours with the command shown, or (b) explicitly labelled as an estimate or an inherited claim.
Where I was previously wrong, the correction is stated as a correction rather than quietly fixed.

---

## 0. READ THIS FIRST — eleven of my own errors (1–5 below, 6–8 in §0a, 9 in rule 20, 10 in §10(ii), 11 in §10(vii)), and the third one changed the plan

**Delta 1 (shared SwiGLU QMV threadgroup 64 → 256, advertised in earlier revisions of this document at
`+0.38 %` of score, "the same order as the entire remaining gap to the bar") does not exist. It is a
measured regression of ≈ +4.7 µs/step. Do not land it. Do not submit it. Both patches I prepared for
it — including the one I ported onto the best-scoring account tree specifically so a sibling campaign
could draw on it — are marked `REFUTED_DO_NOT_LAND_*` and are retained only as artifacts.**

If you read no further: **Maple ends this campaign holding no measured decode win.** Its deliverable
is the negative science in §5, the reachability audits, and the channel measurements in §6 — plus the
removal of a poisoned candidate from the option set, which at ≈65–100 min per draw and ~3 draws left
was worth more than any delta I could have handed over.

The arithmetic provenance is in **§4c**. The one-line version: the primary source (#714) reported
`TG=256 … delta +4.67 +-0.68 us/step (+1.61%)` against a `+66.88 us/step` counterfactual **it had just
refuted**, and my closing comment on that PR recorded it as `294.50 tok/s … +0.38 % score` — the
counterfactual's magnitude, sign-inverted, relabelled as a measurement. Everything downstream (two
patches, PRs #729, #731, #737, and the framing of the whole endgame) inherited it.

**A second error, found at 11:52Z while pricing the idle submission slot, and it is in the same
table:** §4b gave the gap from the best-ever draw to the bar as `+0.378 %`. The two raw numbers give
`(2.6195531094824 − 2.60664970) / 2.60664970 = +0.4950 %`. The wrong value is ≈ the `0.38` I had
attached to delta 1 — I had let the gap drift to whatever made the story close. Corrected in §4b.

**A third error, found at ~12:10Z, and it is the one that mattered most.** Having corrected the gap, I
priced the idle slot with σ(one official draw) ≈ 0.49 % and concluded that **re-firing the unchanged
best-known tree clears the bar with P ≈ 15.6 % per draw** — i.e. that a free slot is worth ~15 % of a
crown to a campaign holding no deltas at all, and therefore that "the marginal value of a draw comes
from the variance, not from the delta you put in it". I also asserted in bold that σ had **never been
measured by replication** on this channel, on the strength of my own parse showing 106 draws and 0
repeated commits.

**All of that is retracted.** σ *had* been measured — by an earlier round of this campaign, in this
repository (`research/advisor-r103-submission-tree-provenance-and-replicate-noise.md` §5) — by grouping
draws under a **comment-insensitive digest of `Sources/`** instead of by commit SHA: 139 receipts,
18 replicate groups, 7 with metrics, **trimmed pooled sd(ln score) = 0.1860 %**, worst well-behaved
group 0.2276 %. My "no replicates" finding was an artifact of keying on commit identity while the
campaign routinely added cosmetic marker comments. At the true σ the 0.4950 % gap is **2.2–2.7σ**, not
1σ (**and §6.5c shows even that understates it: measured from the program mean rather than from the
lucky draw the required move is 6.3–7.8σ**), and the tail excursions that do exist are **one-sided
negative** (contention/thermal), so they add
no upside. **Re-firing an unchanged tree is worth ≈1 % per draw, not ≈15 %** — and §6.5c, a fifth
error found at 12:45Z, brackets it lower still at **[≈0 %, 1.5 %]**. ~~Only a real delta of ≈+0.26 %
(≈15 %) to ≈+0.50 % (≈50 %) can clear the bar.~~ **Those two probabilities were also computed from the
lucky draw rather than from its program mean and are wrong by ≈6×: the true figures are +0.26 % ⇒
3.2 % and +0.50 % ⇒ 8.0 %, and an even-money draw needs ≈+1.26 % of score ≈ 82 µs/step ranked
(§6.5c).** Full derivation, and what a delta must be
worth in µs/step, in **§6.5**; the two incompatible µs/step currencies that error three also exposed
are in **§6.6**.

There are five errors in this document's history, not three. Error 4 is the µs/step currency confusion
(§6.6, found 12:10Z, four currencies quoted as one). Error 5 is §6.5c (found 12:45Z): the table that
priced *how big a delta has to be* was still computed from the lucky draw after the winner's curse had
been established, and is wrong by ≈6× in the flattering direction.

The common cause of all five is worth more than the errors: **each time, I took a number from a
summary layer (a closing comment, my own earlier table, an archive's modelled σ, my own corrected
paragraph) instead of from the layer that measured it.** §8's rule 1 is now "verify inputs, not conclusions", and edward's R127-A
audit (#741) exists to apply it to the rest of this document.

The generalisable failure, stated for whoever reads this next: **I priced a student's number without
re-reading the column header it came from.** A campaign's advisor is the single point at which unit
errors become policy, and the only defence that would have worked here is mechanical — re-open the
primary result block, read the units and direction off the column, and re-derive the price, before
briefing anything. Not once did the number get cheaper to check than it was to repeat.

### 0a. Errors 6, 7 and 8 — found between 13:00Z and 15:35Z by the audit I commissioned

The count is now **eight**, and the last three were all found by students I had pointed at my own
document rather than at the code. That is the single most useful thing this campaign did on its last
day, so the errors are stated in full and the audits are credited.

**Error 6 — I branded the *correct* local currency "UNSOURCED, never reuse", and the correction was
sign-inverted (maple-edward, #741, findings F1/F16).** §6.6 declared `0.00586 %/(µs/step)` unsourced
and told readers a prior local requirement of "44/84 µs/step was ~40 % too high". Both statements are
backwards. edward re-derived the conversion from first principles — the official score is
`decode_speedup^0.75 · prefill_speedup^0.25`, so `d ln(score)/dD = −0.75/D` identically — and showed
that with the `--local-iterate` denominator actually used in this repo (`D = seed/128 + step ≈
12798 µs`, ~40 in-tree measurements) the currency **is** `0.00586 %/(µs/step)`. The *ranked* currency
`0.01527 %/µs` (`D = 4910.9`) is a different, also-correct denominator; the two are not rivals, they
are two clocks. The two figures I had quoted as alternatives are worse than wrong: **`8882` has zero
real in-tree hits**, and **`8213` is a single token-step of 765 away from the control medians
8189/8192** — i.e. noise I had promoted to a constant. Consequence: the "what must a delta be worth"
column I had been briefing was **≈30 % LOW**, i.e. flattering, in the same direction as errors 2, 3
and 5. The corrected local requirement for +0.26 %/+0.50 % of score is **44 / 85 µs/step**, not 31/59.

**Error 7 — my per-draw probability bracket priced the wrong random variable on *both* rails
(maple-edward, #741, finding F19).** §6.5c's `[≈0 %, 1.5 %]` was built from (lower rail) the replicate
sd of the *committed source* alone and (upper rail) the sd of the *draw factor at fixed source*. The
quantity that actually decides a draw is `sd(ln official)`, which includes the baseline draw — and
`CURRENT_RESEARCH_STATE.md:3509-3511` shows **~96 % of official variance lives in the baseline draw**,
so neither rail contains it. Measured predictively on the five nulls: **σ = 0.3728 %**, which is
*below* the independence quadrature 0.5822 % because the two components are correlated at −0.79.
Centring on the **program mean** official (2.582263 × 1.001830 = 2.586989) rather than on a
max-over-106, the required move to today's bar is **+1.2588 %** ⇒ **P ≈ 0.04 %**, 95 % interval
**[≈0 %, 12 %]**. Three sincere attempts at this one number spanned **394×** (15.6 % → 0.95 % →
0.04 %). The operational conclusion is not "0.04 %": it is **carry the nonparametric bound instead** —
0 of 106 official draws on this account ever cleared today's bar, so rule-of-three gives **≤2.83 %**
per draw, and that number cannot be destabilised by a modelling choice.

**Error 8 — I carried stale budget and file-count numbers all morning (maple-nezuko, #746).** I had
been publishing `2681206 / 318794 B headroom / 142 files`. Live is **2712490 / 3000000, headroom
287510 B, 143 files**; the delta is exactly `Sources/MLXFastModel/LagunaOProjGeometry.swift`
(+31284 B), which landed after my snapshot. Per-file cap 524288 B. A campaign that had planned a
landing against my figure would have had ~10 % less headroom than it thought.

**What the three have in common, and it is not what errors 1–5 had in common.** Errors 1–5 were
*inherited* numbers I failed to re-derive. Errors 6–8 are *my own* numbers that went stale or were
mislabelled with confidence — including one where I attached a scary label ("UNSOURCED, never reuse")
to the correct value and thereby made the truth harder for the next reader to use. **A wrong
provenance label is more expensive than a wrong number, because it survives the number's correction.**
The defence that worked, and the only one that worked, was commissioning students to audit the
advisor: five terminal audits found three errors, and every one of them was in the flattering
direction. §8 rule 16, added now: **an advisor's own summary document is an experimental subject and
must be assigned to someone else before it is used to make a decision.**

---

## 1. Hard facts, with their verification chains

**Close: 17:00 UTC 2026-08-11.**
`mlxfast benchmark` prints `closes 8/11/26, 5:00 PM`. This host's clock is UTC (`date` and `date -u`
agree, zone GMT), and the CLI renders receipt times in UTC — verified by cross-checking receipt
`f2b2345`, rendered `7:26 AM`, against a submission independently timed at 07:26Z. I had previously
carried 20:00Z; that was wrong by three hours and it was the single most expensive error of the day
because it inflated the apparent number of remaining draws.

**Bar: 2.6195531094824**, organizer commit `4ea72c3b28873fca23b12b6f33193a2eeb5042f8`, receipt
`cdcd091`, created 08:28Z, decode 203.93695 tok/s, prefill 5314.29504 tok/s. The previous bar
(2.61650354 at `cc6ddc1` / `c5b0a13c`) is retired.

**Our own numbers for comparison.** Best own candidate ever: Cedar receipt `e27f1ce` = 2.60664970.
Maple's own promoted receipt: `97a5090` = 2.588828. Maple's current HEAD class normalizes ≈ 2.567.
Best receipt whose commit is actually **present in this fork**: `d11026c` = 2.59320 at
`d6a5f9e7346e717d89e769396d732600a994b4cf` (asked maple-fern to confirm or correct). The commits
behind today's best receipts — `6a5c7812`, `113fcb98`, `c82b88f1`, `6682dfec`, `7d58c925` — are all
**absent** from this fork, i.e. Maple's composition has never had a ranked receipt of its own.

**Submission mechanics (unchanged, re-verified 10:20Z).**
`bash senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` — no other arguments.
The argument is the campaign `BASE_SHA` (= fork `main` content), **never** a candidate SHA and never
an advisor-branch head. The wrapper injects `--model senpai` (line 109) and `exit 2`s on any caller
`--model` (lines 19-21). Line 75 aborts if the submitted snapshot at `BASE_SHA` differs from current
`origin/main`. `origin/main` has moved to `27cb47bac00688a6cbf10443d7e5fc1176f45289`, but that
commit's entire diff is `senpai/research-frontier-briefing.md` (+539), a non-editable path, and the
guard's own comparison `git diff 1bc1c895 origin/main -- Sources Vendor benchmark.json` is **empty**,
so `1bc1c895…` remains correct. One non-terminal submission per account, server-enforced; the account
is shared with sibling campaigns. Never retry-loop.

---

## 2. The instrument, and what may be adjudicated on what

This is the most transferable thing Maple produced and it inverts the naive approach.

**`officialScore` is luck-dominated for sub-0.7 % candidates.** **Corrected at 12:10Z (see §0 error
three and §6.5):** the single-draw σ at *fixed program* is **0.1860 % pooled / 0.2276 % worst
well-behaved group**, measured by replication on the official channel (r103 §5, 18 replicate groups over
139 receipts). Earlier revisions of this row said `σ ≈ 0.49 %`; that figure, and the `long-horizon
σ ≈ 0.021 score units / same-day 0.008–0.013` beneath it, are **cross-code** dispersions — they mix
program differences into the noise term and overstate same-program σ by ≈2.5×. Use them only for
"how far apart are two *different* trees", never to price a re-draw. Today's terminal receipts across
all solvers cluster in 2.564–2.595 regardless of content, and one of our replicate groups puts five
draws of one fixed program at 2.5756–2.5906 while its author's own listing claimed 2.6196 — i.e. there
is also a *level* offset between accounts/sessions that is not σ.

| instrument | cv (same program) | resolves at 2σ, one draw each | relative cost |
|---|---|---|---|
| candidate **prefill** leg | 0.075–0.103 % | 0.25 % | 1× (cheapest) |
| candidate **decode** leg | 0.29–0.32 % | ~0.85 % | ~4× |
| `officialScore` | **0.186–0.228 %** | ~0.64 % | ~38× |
| local `--local-submit` `ns` | ~5.9 % σ | 0.243 % floor for two n=3 families | free, but M4-only |
| local `--local-iterate` | 33.6 % σ | unusable; under-reports steady-step wins 1.28× | free |

**Do not read the score's smaller σ as the score being the sharper instrument.** Score noise is
dominated by decode noise attenuated by the 0.75 exponent, and a decode change is attenuated by the
same 0.75, so for a *decode-side* change the score and the decode leg have essentially identical
signal-to-noise (x/0.3035 vs x/0.294 per 1 % of decode). For a *prefill-side* change the prefill leg is
≈2.2× sharper than the score (x/0.103 vs 0.25x/0.2276). Legs still win on both counts that matter: they
localise the change, and they cost 4–38× less. Every ranking decision from here is made on raw legs.

Corollary that decided our final plan: **prefill is the cheap axis.** It is also where the promoted
frontier actually moved (+3.27 % official prefill, −0.31 % decode), so it is where both the signal
and the resolution are.

**Scoring model.** `score = decode_speedup^0.75 · prefill_speedup^0.25`, both components floored at
0.95 independently. Reference `ns = (0.013890/decode_s_per_tok)^0.75 · (0.0003845/prefill_s_per_tok)^0.25`.
Operating point: S = 97.863 ms seed forward, T = 4.3224 ms steady step, σ = 14.98 %; elasticities
decode 0.638, seed 0.362. Pooled `ns` cv 0.149 %.

**`1 µs/step = 0.00586 % score` — this is a LOCAL-M4 currency and must not be applied to ranked-host
numbers. See §6.6.** On the ranked host the decode step is 4910.9 µs, so **1 µs/step = 0.01527 %**, a
2.6× different exchange rate. Mixing them silently understates what a candidate has to be worth by the
same factor.

**M4 Pro is not the target machine and this is structural, not a nuisance.** GPU gen 16 never selects
`_nax`; 94.2 % of M4 prefill GPU time is spent in kernels the M5 never runs; local prefill speedup
fails its 0.95 floor on every arm including untouched controls. Local default startup is
64/128/`low_memory=true`; only `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` restores the ranked
200/200/50 atlas profile, and that alone moves the command-buffer class by ~888 µs/step and flips
signs. Any measurement of the dispatch / command-buffer / absorption class taken under the default
local profile is not evidence about the ranked path.

---

## 3. The base: `18ac6015…`, and what can and cannot be certified about it

The promoted `cdcd091` frontier ("N1") is merged into the Maple advisor branch:
`a9de9e8f` → `f52be6aa` "Sync promoted organizer frontier cdcd091" → `ae20581e` (merge) →
`29250d98` → `18ac6015`. Note `f52be6aa` is **not** an ancestor of `origin/main`; it reached us
through the advisor branch only.

`git diff --numstat a9de9e8f 18ac6015`:

```
 24    3  Sources/MLXFastModel/LagunaRuntimeModel.swift
 25    4  Sources/MLXFastModel/LagunaRuntimeWeights.swift
 63   12  Vendor/mlx-swift-lm/Libraries/MLXLMCommon/SwitchLayers.swift
 16    4  Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp
 23    0  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/jit_kernels.cpp
 16    4  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h
109    2  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
 51   25  senpai/research-frontier-briefing.md
```

**Verified 10:33–10:35Z:**

- `swift build -c release --force-resolved-versions` → **exit 0, 115.87 s** warm. The changed
  translation units genuinely recompiled (`Compiling quantized`, `jit`, `fp`, `matmul`,
  `MLXLMCommon`, `MLXLLM`, `MLXFastModel`), so it is not a cache no-op. `Package.resolved` was not
  modified by the build.
- **Zero conflict markers** under `Sources/` or `Vendor/`.
- **Nothing of ours was dropped:** `lagunaSharedSwiGLUQMV` 39 hits, `lagunaFusedSharedRoutedQMVEnabled`
  3 hits, `darkbloom_expert_down_bn` present at `quantized.cpp:1250` with call site at 1446.

**What cannot be certified locally, and this limit should travel with the base:** N1's mechanism is
`_nax`-gated. On GPU gen 16 those variants are never selected, and the frontier's Metal changes
(`fp_quantized_nax.h`) are JIT-compiled at dispatch time. So an M5-only breakage in the merged
frontier is undetectable by any gate we own. Absence of a local delta from this merge is expected and
is **not** evidence of a bad merge; equally, local correctness green is **not** evidence that the
`_nax` path is sound.

**N1, in one sentence, so nobody duplicates it:** the fused sorter publishes one exact 257-entry
expert-prefix/bounds sidecar which both the gate/up and the down NAX gather-QMM consumers reuse
instead of repeating lower-bound searches and barriers; plus EG256 selection, EB0/EB1 identities, and
a declined-shape warmup. Off-limits regions for new work: route-sort, expert-index/carrier, pairwise
scale, gather geometry, warmup, gather-QMM bounds. N1's hunks in `quantized.cpp` on this base land at
lines 1222, 1351, 1391, 1470, 1589, 1769, 1991, inside `darkbloom_expert_stage_wideld` (after),
`laguna_expert_pairwise_scale_layout`, `gather_qmm_rhs_nax` (×3), `gather_qmm_rhs`, and
`GatherQMM::eval_gpu`.

**Budget. ~~`current=2681206/3000000 headroom=318794 files=142`~~ — STALE, this was error 8.** Live at
15:30Z (maple-nezuko, #746): **`current=2712490/3000000 headroom=287510 files=143`**. The delta is
exactly one file that landed after my snapshot, `Sources/MLXFastModel/LagunaOProjGeometry.swift`
(+31284 B). Anyone planning a landing against my published figure had ~10 % less headroom than they
thought. Re-measure before relying on *these* numbers too. The only cap with teeth is
the **per-file 524,288 B** on `Sources/MLXFastModel/LagunaRuntimeModel.swift`. `editablePaths`
includes the *directories* `Sources/MLXFastModel` and `Sources/MLXFastTransform`, so a brand-new
`.swift` file there is in-surface and auto-compiled — that is the escape hatch when the per-file cap
binds. Re-measure on `18ac6015…` before relying on the numbers; the frontier added compiled bytes.

---

## 4. Landable delta ledger

Priced in score terms at 1 µs/step = 0.00586 %. **That is the local-M4 currency and every µs/step in
this section is a local-M4 measurement, so the two are consistent — but see §6.6 before carrying any of
these numbers into a ranked-host comparison, where the rate is 0.01527 %.**

| # | mechanism | price | location | status | notes |
|---|---|---|---|---|---|
| 1 | ~~shared SwiGLU QMV threadgroup 64 → 256~~ | **REFUTED. ≈ −0.04 % (i.e. +4.7 µs/step SLOWER)** | `lagunaSharedSwiGLUQMV`, LRM ~7326–7369; env `DARKBLOOM_SHARED_QMV_TG`; compiled default at LRM:334 | **DO NOT LAND** — closed #729 as a refutation; see §4c | The `+0.38 %` in earlier revisions was my error, not a measurement. Primary source #714: TG=64 **289.83±1.42 µs/step (minimize)**, TG=128 290.38±1.07 (NS), TG=256 294.50±0.85 ⇒ arm C `delta +4.67 ±0.68 (+1.61 %)`, headline `REFUTED, phi=+0.065`. Independently re-measured by #729 at **+4.73±0.52 µs/step, CI95 [+2.50,+6.96]**, 3/3 blocks and 6/6 slot-pairs positive. Mechanism: PSO reports **`tgMem=0`** ⇒ no reuse to amortise ⇒ width is pure occupancy debit at ≈ +0.79 µs/step per extra simdgroup/TG. |
| 2 | ~~routed expert down-GEMM `BN` 64 → 32 (lever E1)~~ | **≈ +0.04 % of score** — not worth a draw | `darkbloom_expert_down_bn()` `quantized.cpp:1250`, call site 1446 | **EXCLUDED** — closed #732 | BN=128 ⇒ `kSrcBytes=32` ⇒ both vectorized staging bodies compile out (`fp_quantized_nax.h:215-216,:428,:438,:444,:502,:512,:522-527`); IR census Wide\* 21/27/**0** and tg-memcpy 1/1/**0** at rungs 32/64/128. Pool is ≈2.4 ms, not the 3.91 ms I briefed, and η=1 is unreachable, so the fixed-loader lever is ≈ +0.17 % prefill ≈ **+0.04 % score**. Default stays 64. |
| 3 | shipped-default flips (screen → confirm) | unknown | `DARKBLOOM_*` defaults in LRM | **the only live arm**, PR #733, terminal 13:30Z | `SHARED_ROUTED_QMV_FUSED=1` already measured a loss: +55.2 µs/step, 95 % [+18.9,+85.9], score −0.323 %, W&B `6r8i5rcg` ⇒ stays 0. Remaining priority: `NVFP4_NIBBLE_SPLIT`, then `DECODE_ASYNC_STAGE`. Screen-only winners must never be promoted; best-of-15 screening looks good by luck alone. |
| 4 | ~~expert QMV threadgroup granularity (routed)~~ | **REFUTED. −0.282 % of score** | routed QMV, LRM:8078-8079 | **DO NOT LAND** — closed #731 | TG=128 null (median −3.77, CI95 [−11.26,+23.40], sign p=0.2188, inside an A-vs-A envelope of max \|null\| 67.13); TG=256 a **wall regression**, median **+23.12 µs/step**, CI95 [+15.77,+38.31], sign p=0.0312; 0 divergences in 36/36 runs × 512 tokens. Banked law: TG widening pays only where a threadgroup's rows map into one contiguous weight region — routed slots interleave mod-8. **This was the first direct contradiction of my delta-1 headline and I failed to notice it.** |
| 5 | QKV threadgroup granularity ladder | unknown, **now expected null** | `decode_nvfp4_qkv_h64/h48` | in flight, PR #730, terminal 15:00Z | `ns≠2` must take the **non-appended** dispatch (merged #700 `heads/8` tileOffset hazard). Given rows 1 and 4 plus `tgMem=0`, the student has been redirected to read the PSO's threadgroup-memory field **first**: if it is 0 the debit is structural and two rungs suffice. |
| — | o_proj rps default | **0** | — | closed #718 | rps=2 is an interior optimum (rps2 1378.4 < rps1 1402.9 < rps4 1416.4). Any o_proj term in a composition estimate must use **−35 µs/step**, not the imported −80. |
| — | QKV rows-per-simdgroup | **0** | — | closed #719 | monotone degradation; default 1 already optimal. |

**Landing rule that cost us real score before it was understood:** the submitted tree runs with
**none** of our environment. An env-gated win left defaulting to the old value is worth exactly zero.
A landing is a **compiled-default flip** with the env override retained as an escape hatch.

### 4a. Delta 1 is ported, default-flipped and build-green — reachability chain verified

> ### ⛔ DO NOT LAND — read §4c first
>
> **Everything below this banner is engineering that is correct and a landing that is wrong.** The
> port applies, builds and flips the compiled default exactly as described; the *delta it lands is a
> measured regression*. TG 64 → 256 costs **+4.73 ± 0.52 µs/step** (CI95 [+2.50, +6.96], #729,
> W&B `cccr6f2q`), i.e. **≈ −0.03 % of score** on the isolated-kernel delta and as much as −0.14 %
> on edward's routed-wall measurement (#731). Every "+0.38 %" in §4a/§4b is my misreading of
> frieren's #714 table; the arithmetic trail is in §4c.
>
> Also **strike the residency argument** used below and in §4b ("total simdgroups `64*8 = 512`,
> identical to the shipped `256*2`, so this is a granularity change and not an occupancy change").
> Pinning *total* simdgroups does not pin occupancy. The PSO for this kernel reports
> `staticThreadgroupMemoryLength = 0`, so nothing is amortised across a wider threadgroup and the
> only effect of more simdgroups **per TG** is a scheduling debit of ≈ **+0.79 µs/step per extra
> simdgroup/TG**, linear from 64→128→256 (#729). Law `L-TG-WIDTH-IS-A-DEBIT-AT-tgMem-0`, §5.
>
> Retained deliberately, unredacted, because the reachability method in this section is the reusable
> part and because the failure mode is the lesson: a fully verified landing pipeline pointed at a
> delta whose sign was never checked against its primary source.

An env-gated research arm can be measured honestly and still land as a **no-op**, because the arm's
guard may only fire on a path the shipped default never takes. Nobody had checked this for delta 1:
frieren measured it under `DARKBLOOM_SHARED_QMV_TG=256`, and his guard is
`widened = halved && !WIDE_CODES && TG != 64` — so the whole +0.38 % depends on `halved` being the
shipped default. It is, and here is the chain on `18ac6015`:

- `lagunaSharedScaleHalvedEnabled = env["DARKBLOOM_SHARED_SCALE_HALVED"] != "0"` (LRM:319) ⇒ default true.
- `lagunaSharedSwiGLUQMVRows1Enabled = env["DARKBLOOM_SHARED_QMV_R1"] != "0"` (LRM:303) ⇒ default true.
- Under both guards the halved group-32 scale plane is built into `_fusedGateUpScalesHalved`, LRM:9148–9163.
- `fusedSharedBankGuard` returns `_fusedGateUpScalesHalved ?? fusedScales` at **LRM:9281**, reaching
  `lagunaSharedSwiGLUQMV` through `fusedSharedDownInputs` (LRM:9236).

⇒ `halved == true` with no environment set, so the compiled-default flip does change the dispatched
kernel. **Generalise this:** for every future landing, cite the `file:line` where the shipped default
reaches the changed code. "The knob measured a win" is not evidence that flipping its default pays.

frieren's diff (`039800fe`, based on `cd047c00`) **does not apply** to `18ac6015`: hunk #1 lands at
offset +8, hunk #2 fails at LRM:7118 because the generator is now
`lagunaSharedSwiGLUQMVRows1Source(halved:weightName:scalesName:outputName:)` under edward's fused
work. The port adds a **fifth defaulted** parameter `simdgroupsPerThreadgroup: Int = 2` and replaces
the hardcoded `uint row = tile * 2 + simd_group;` with `tile * \(simdgroupsPerThreadgroup)`, which
leaves the FUSED generator call (~LRM:8203), the non-halved kernel (7223) and the Wide kernel (7247,
own inline source) byte-identical. Two new **distinct kernel names** are required
(`..._halved_tg128_bf16_v1`, `..._halved_tg256_bf16_v1`): MLX caches compiled libraries by name, so
reusing a name with changed source is a stale-library hazard.

Geometry: `sharedExpertIntermediateSize = 512` (LagunaConfig.swift:33). TG=256 ⇒ 8 rows/threadgroup ⇒
`tiles = 64`, grid `16384`, total simdgroups `64*8 = 512`, identical to the shipped `256*2`; rows
`tile*8 + simd_group` cover 0…511 exactly once, so no bounds guard and no aliasing. Invariance holds
in all four other cases: `!halved` ⇒ tiles 256; `WIDE_CODES=1` ⇒ tiles 256; `SHARED_QMV_R1=0` ⇒
tiles 128; `DARKBLOOM_SHARED_QMV_TG=64` ⇒ exact old geometry. The selector must be
`case "64"/"128"`, `default: 256`, so that **unset ⇒ 256**; an `== "256"` test would ship the old
default and deliver zero.

Advisor fallback port: local branch `advisor-r125-tg256-fallback`, commit `b74bc80c`, patch text at
`research/patches/REFUTED_DO_NOT_LAND_r125a_tg256_advisor_fallback.patch`, **53 insertions / 6 deletions in
`LagunaRuntimeModel.swift` only**, `swift build -c release --force-resolved-versions` **exit 0** (97 s
real recompile, `Package.resolved` untouched). It exists as schedule insurance for the highest-priced
delta in the fleet; the student landing in PR #729 is preferred because it also carries the
correctness gate and the compiled-default plumbing check. **Correctness gates were not run on the
advisor host** (model-holding), so this port is build-verified, not correctness-verified — do not
submit it without a gate run.

### 4b. Delta 1 also ports to the *best-scoring account tree*, not only to `18ac6015`

> ### ⛔ DO NOT LAND — and specifically: do not put this near the `e27f1ce` tree
>
> This section exists to hand Cedar a low-risk port of a delta that **does not exist**. Applying
> `research/patches/REFUTED_DO_NOT_LAND_r125a_tg256_e27_generation.patch` to the best-scoring tree on
> the shared account would move that tree **≈ −0.03 % of score or worse** in exchange for a rebuild and a
> gate run. The table immediately below prices the delta at "+0.38 %"; that number is wrong and §4c
> shows exactly how it was manufactured. The gap-to-bar row and the σ row are still correct and still
> useful — the *delta* row is not.
>
> The residency argument in the fourth bullet below is struck for the same reason as in §4a: total
> simdgroups pinned ≠ occupancy pinned, because `tgMem == 0` (#729).

The arithmetic that makes this section worth writing:

| quantity | value | source |
|---|---|---|
| crown / promotion bar | 2.6195531094824 | organizer commit `4ea72c3b`, receipt `cdcd091`, still the bar at 11:09Z |
| best-ever draw on the shared `morganmcg1` account | **2.60664970** (`e27f1ce`, 8/10 08:18Z, **Cedar's**, not Maple's) | `mlxfast submissions`; see §0.1 note and `CURRENT_RESEARCH_STATE.md` §2259 strike |
| gap from that draw to the bar | ~~+0.378 %~~ → **+0.4950 %** = **2.17–2.66σ** at the measured σ = 0.1860–0.2276 % | `(2.6195531094824 − 2.60664970) / 2.60664970`. **Two of my errors here: the 0.378 % (second error) and the σ ≈ 0.49 % I first divided it by (third error, a cross-code σ used for a same-program re-draw). Measured σ and the resulting ≈1 %-per-draw price: §6.5.** |
| delta 1 (shared SwiGLU QMV TG 64 → 256) | ~~+0.38 %~~ → **−0.03 % (a regression)** | REFUTED, #729 / #731; §4c |

**STALE PREMISE, KEPT FOR PROVENANCE — everything from here to the end of §4c was written when delta 1
was believed to be worth +0.38 %.** It is worth −0.03 to −0.14 % (§4c), so "that tree plus delta 1" is
*worse* than that tree, and the reachability audit below is now only an example of how to verify a port
read-only, not a plan. Do not land it.

So the single highest-value composition available to this account is *that* tree plus delta 1 — the
one measured mechanism whose price equals the entire remaining gap to the crown. Maple does not own
that tree and **is not reconstructing it**; what Maple owes its owner is a port that carries no
avoidable risk. Verified by **read-only inspection** of the validate commit
`5c542169b5e6c295805f50fa65df3150816eb443` ("Validate submission e27f1ce4…") already present in this
repository's object store — no checkout, no rebuild, no candidate assembled:

- The two guards delta 1 depends on are default-ON in that generation as well: `DARKBLOOM_SHARED_QMV_R1`
  at LRM(e27):295–296, `DARKBLOOM_SHARED_SCALE_HALVED` at 311–312, both `!= "0"`.
- The halved plane is built into `_fusedGateUpScalesHalved` at 8778; `fusedSharedBankGuard` returns
  `_fusedGateUpScalesHalved ?? fusedScales` at **8899**, which feeds `lagunaSharedSwiGLUQMV` at 8854;
  `halved = fusedScales.ndim == 1` inside that function ⇒ **`halved == true` with no environment set**,
  so the compiled-default flip is live there too.
- The generator in that generation is the **pre-fusion** `lagunaSharedSwiGLUQMVRows1Source(halved: Bool)`
  at 6850, with `uint row = tile * 2 + simd_group;` at 6875 — i.e. exactly the signature frieren
  measured against. The 4-argument fused signature that broke the port on `18ac6015` does not exist
  in this tree, so the port here is *simpler*, not harder.
- `tiles = lagunaSharedSwiGLUQMVRows1Enabled ? 256 : 128` at 7076 and
  `sharedExpertIntermediateSize = 512` (LagunaConfig:33) ⇒ TG=256 gives 8 rows/threadgroup,
  `tiles = 64`, grid `16384`, total simdgroups `64*8 = 512` — identical residency to the shipped
  `256*2`, so this is a granularity change and not an occupancy change.
- frieren's measured diff (`039800fe`) against that file: **4 of 5 hunks apply at fuzz 3**; the one
  failure is the *insertion point* of the new kernel declarations, not any semantic hunk.

Artifact: **`research/patches/REFUTED_DO_NOT_LAND_r125a_tg256_e27_generation.patch`** — 61 insertions / 6 deletions, five
hunks, `git apply --check` **clean** against that generation's `LagunaRuntimeModel.swift`, and
`swiftc -parse` exit 0. Compiled default flipped (`case "64"`, `case "128"`, `default: 256`), env
override retained as the control. Invariance is the same as §4a in all four other cases (`!halved`,
`WIDE_CODES=1`, `R1=0`, `TG=64` ⇒ unchanged 256×64 geometry).

**Two honest limits, stated because someone may otherwise ship this blind.** (1) It is
*syntax-verified only*: no e27-era tree was built or gated on this host, so the owner must run
`swift build -c release --force-resolved-versions` and the full correctness gate before any draw.
(2) The two patch files are **not interchangeable** — `REFUTED_DO_NOT_LAND_r125a_tg256_advisor_fallback.patch` is for
`18ac6015` (fused generator, build-green there), `REFUTED_DO_NOT_LAND_r125a_tg256_e27_generation.patch` is for the
pre-fusion generation. Applying either to the other tree fails or, worse, applies fuzzily.
*(Both files now carry the `REFUTED_DO_NOT_LAND_` prefix; the limits above are moot because neither
should be applied at all.)*

### 4c. How "+0.38 %" was manufactured — the full arithmetic provenance

This section is the audit trail for the correction in §0. It is written out in full because the
mistake was cheap to make, expensive to carry, and completely mechanical to catch.

**Step 1 — what the primary source actually said.** PR #714 (frieren), result block, verbatim:

```
A TG=64   289.83 +-1.42 us/step (sem .58), 7.432 us/call, 39.0 calls/step
B TG=128  delta +0.55 (+0.19%) NS
C TG=256  294.50 +-0.85: delta +4.67 +-0.68 (+1.61%) vs +66.88 if phi=1 -> phi +0.070
HEADLINE: REFUTED. phi = +0.065
```

Units **µs/step**, direction **minimize**, headline **REFUTED**. The `+66.88` is a *counterfactual*:
the time the widening would have cost if the load-balance-granularity coefficient φ were 1. Her
measurement of `+4.67` against that prediction is what refuted φ=1. Her table was correct, correctly
labelled, and correctly headlined. Nothing in #714 needed fixing.

**Step 2 — what I recorded.** My own closing comment on #714 rendered it as `294.50 tok/s … +0.38 %
score`. Two independent errors compounded in one line:

| error | what happened | effect |
|---|---|---|
| unit/column | read the `us/step` column as `tok/s` | **sign inversion** — a 294.50 that is worse than 289.83 became a 294.50 that is better |
| magnitude | priced the delta from the `+66.88 us/step` counterfactual, not the `+4.67` measurement | **14× overstatement** |

The magnitude error is checkable to three digits: `66.88 µs/step × 0.00586 %/(µs/step) = 0.392 %`,
which is the "+0.38 %" I briefed; inverting it, `0.38 % ÷ 0.00586 = 64.8 µs/step`, which is the
"64.8–65.5 µs/step" I quoted for weeks. That number is *also*, coincidentally, the R119-A/#712 router
dispatch-boundary transfer constant — which is very likely why it never looked wrong to me. **A
number that already lives in your head is the easiest number to mis-source.**

The correct price of the real measurement: `4.73 µs/step × 0.00586 = 0.028 %`, **negative** —
i.e. TG=256 is a −0.03 % change on the isolated kernel leg. edward's routed-wall replication (#731)
put it at `+23.12 µs/step`, −0.14 %, so the honest statement is *a loss of between three and fourteen
hundredths of a percent*. Either way the sign is settled and the magnitude is nowhere near the gap
to the bar.

**Step 3 — the refutation.** #729 (alphonse, terminal 11:34Z, W&B `cccr6f2q`) isolated
`SPLIT=1/FUSED=0` and measured TG=64 `289.88 ± 0.48` vs TG=256 `294.62 ± 0.46` µs/step ⇒
**+4.73 ± 0.52, CI95 [+2.50, +6.96]**, consistent in 3/3 blocks and 6/6 slot-pairs — a clean
replication of #714 to within noise. The SPLIT=0 wall arm returned a null of [−19.33, +17.86]
µs/step, which **excludes the −41.4 µs/step that my +0.38 % required, at 3.56σ**. Mechanism: the PSO
reports `staticThreadgroupMemoryLength = 0`, so a wider threadgroup amortises nothing and the debit
is pure scheduling, ≈ +0.79 µs/step per extra simdgroup per TG. Correctness: 0 divergences at both
widths (job `12d3186e`, hash `005195dea7a52563`), so this was never a correctness question.

**Step 4 — the evidence I walked past.** edward's #731 reported a `+23.12 µs/step` routed **wall**
regression from the same flip and I did not treat it as a contradiction of the banked delta; I
treated it as a noisy wall measurement disagreeing with a clean kernel measurement. It was the first
direct refutation available to this campaign and it is credited to him. When a wall measurement and a
banked kernel delta disagree **in sign**, the banked delta is the thing on trial.

**Step 5 — what to change in practice.** Three rules, all mechanical, all cheap:

1. **Re-open the primary result block before pricing anything.** Not the summary, not your own notes,
   not the PR title — the block with the column headers. Read units and direction off the header.
2. **Never price a counterfactual.** Any number reported as `vs X if <hypothesis>` is the thing being
   refuted. Students must tag these `PREDICTED`; advisors must refuse to bank an untagged one.
3. **State the sign convention in every column header** (`µs/step ↓ better`). Both #714 and my
   misreading would have been impossible against a header that said so.

The banked physics from this whole arm is one law, and it is worth having:
**`L-TG-WIDTH-IS-A-DEBIT-AT-tgMem-0`** — where a kernel's PSO reports zero static threadgroup
memory, threadgroup width is a pure occupancy/scheduling debit; widening cannot pay until the kernel
has real shared-memory reuse to amortise. Co-credit frieren (#714, the measurement) and alphonse
(#729, the mechanism and the exclusion).

---

## 5. Retired and refuted — do not re-probe

- `L-LOAD-BALANCE-GRANULARITY` (φ=1) — refuted (#714, replicated #729): widening the shared SwiGLU QMV
  threadgroup predicted `+66.88 µs/step` if φ=1 and measured `+4.67`/`+4.73` ⇒ φ ≈ 0.065–0.070.
  **Replacement law, banked: `L-TG-WIDTH-IS-A-DEBIT-AT-tgMem-0`** — where a kernel's PSO reports
  `staticThreadgroupMemoryLength == 0` there is nothing to amortise across a wider threadgroup, so
  threadgroup width is a pure occupancy/scheduling debit (≈ +0.79 µs/step per extra simdgroup per TG,
  linear 64→128→256). Do **not** revisit TG > 64 on any kernel until it has real shared-memory reuse;
  screen the PSO's `tgMem` **first** and stop if it is 0. Co-credit frieren (#714) and alphonse (#729).
  Note that "total simdgroups pinned" (`64×8 == 256×2`) is *not* an occupancy-invariance argument —
  that was the flaw in §4a/§4b.
- **TG 64 → 256 as a landable delta** — refuted, and it was the headline of this manifest. See §4c.
- `N-K3-AT-DRAM-ROOF` — refuted (#718): a pool near the nominal DRAM roof can still yield. Replace it
  with the **%-of-measured-peak** rule from #719: `decode_nvfp4_qkv_h64` sits at 94.3 % of the
  measured 256.7 GB/s peak, h48 92.8 %, and both refuse to yield; o_proj was at 83.4–90.7 % when it
  gave up −82 µs/step. Screen candidate pools on measured peak, not nominal.
- o_proj latency absorption, and cross-kernel redistribution — both refuted (#718).
- nezuko's predicted 40-core rps=1 interior optimum — refuted at t ≥ 4.9 (#718). This also killed the
  advisor's own r124 rps 2→1 candidate before it could spend a draw.
- `gate_sp` as a composition ingredient — ranked legs exclude >40 % transfer at 2σ; it measured
  +0.12 % **slower** on ranked legs against −0.59 % M4-predicted.
- PR #333 / note `7e267f3` "grid over-dispatch" — source-refuted: `dispatch_threads` takes total
  threads, and the proposed fix hard-fails exact tokens.
- The R119 grid-append family — terminal.
- **Threadgroup widening on the routed expert QMV family — refuted (#731, maple-edward, W&B
  `lv9kmuzw`, closed 11:2xZ).** TG=128 median −3.77 µs/step, CI95 [−11.26, +23.40] covers zero, sign
  p=0.2188 ⇒ null, and inside his own A-vs-A envelope (median −3.21, CI95 [−43.00, +3.50], max |null|
  67.13). TG=256 median **+23.12** µs/step, CI95 [+15.77, +38.31] excludes zero, 0 neg / 6 pos, sign
  p=0.0312, **−0.282 % score** ⇒ regression. 0 divergences over 36/36 runs × 512 checked greedy
  tokens; default stays TG=64 and the default build is byte-identical.
  **The transferable law, and the most reusable sentence of the round: TG widening pays only where a
  threadgroup's rows map into one contiguous weight region.** Shared expert = one contiguous stream ⇒
  it widens (delta 1). Routed expert slots are interleaved mod-8 (`LagunaRuntimeModel.swift:8078-8079`)
  ⇒ each extra row lands ~1 MiB away in a different expert, multiplying concurrent DRAM streams to
  save only L2→L1 activation re-fetch, which cannot be the bottleneck at 232.0 GB/s = 90.4 % of
  measured peak. Follow-up left un-run by choice: reindex-then-widen (make an expert's rows
  contiguous offline, then re-run the ladder).
- **Routed/shared down-GEMM output tile BN 64→128 — refuted, and it refuted my pricing too (#732,
  maple-tanjiro, W&B `1nd4yw9s`, closed 11:2xZ).** BN is **not a single lever**: `QuantizedBlockLoader`
  derives `n_reads = (BCOLS_PACKED*BROWS)/tgp_size = BN/4`
  (`Vendor/mlx-swift/…/kernels/fp_quantized_nax.h:215-216`) and `kSrcBytes = n_reads*bytes_per_pack`
  (:428), but vectorized weight-staging bodies exist only for `kSrcBytes == 16` (:438) and `== 8`
  (:444), both behind `if constexpr` (:502, :512), with a per-byte scalar fallback (:522-527). BN=128
  ⇒ kSrcBytes = 32 ⇒ **both vector bodies compile out** and the ~151 MB/layer weight stream degrades
  to per-byte device loads while the kernel name still advertises `_wl_1`. IR census at rungs
  32/64/128: Wide* symbols 21/27/**0**, device 16 B memcpy 0/1/**0**, threadgroup 16 B memcpy
  1/1/**0**, plus a 32 B `sb[]` alloca and 8 scalar threadgroup stores only at 128.
  **Standing screen for any future tile-width change on this family: run the Wide*/memcpy IR census
  first.** He also corrected my pool arithmetic — addressable x re-read is ~2.4 ms of the 97.9 ms
  window, not 3.91 ms, and η=1 is unreachable (floor ~11.98 ms) — which reprices the fixed-loader
  version of this lever at ≈+0.17 % prefill ⇒ **≈+0.04 % score**, i.e. below the cost of a draw.
  Decode neutrality holds by construction (gate needs M ≥ 64 and `bm==64 && wm==4 && (wn==2||wn==1)`,
  `quantized.cpp:1400-1404`) and was confirmed by paired A/B (ratio 0.997987, `max_abs_diff` 0).
- **★ Advisor retraction, issued within the hour (11:3xZ): I briefly endorsed tanjiro's follow-up
  pointer to the "SM=16 row-padding BM/WM lever (~11 ms)" in the #732 close note. That endorsement is
  withdrawn — the item is already struck in our own archive and I failed to check before writing.**
  (1) Formal retraction of the "+1.9–2.6 % row-padding prize" at
  `RESEARCH_ARCHIVE_through-round-91.md:6423`: `453,120 = Σ ceil(n_e/16)·16` *is* the floor, not a
  target; retired with it, "1 of 4 simdgroups active" (traced to `fbc1371`, reasoned, never measured).
  (2) The axis was already swept and shipped at its optimum (`quantized.cpp:1413-1487` doc,
  `:1491-1510` selector, `:1659-1667` table; BM64/WM4/WN1 = shipped default; BM ∈ {16,32,64,128} gives
  372.6/263.2/**220.5**/207.9 chunks per layer with idle TGs pinned at 51.9 for every BM, and 64→128
  buys −5.7 %). (3) **SM < 16 is arithmetically impossible**: `SM = BM/WM` (`:1634`), `TM = SM/16`
  integer-divides to 0 ⇒ zero MMA (`:1637`, `kFragRows = 16`), host guard `:1662` pins
  `bm==64 && wm==4`; WM=8 is expressible but useless. (4) Row-lane masking is structurally barred —
  a 16-row predicate is thread-varying while `tile_matmad_nax` is simdgroup-collective
  (`:1439-1443`), the same reason FRAGSKIP was rejected. (5) The residue was chased onto the staging
  axis and measured null there (fern #40: `Ws` double-buffer +0.1150 ms, register prefetch +0.4626 ms,
  both wrong sign, inside σ = 0.2536). The ~11 ms is real, unowned, and has **no surviving
  mechanism** (`RESEARCH_STATE_ARCHIVE_through-round-21.md:2148`). Do not re-commission it.
- Closed families: WAR-barrier GEMM staging, attention nibble-delta, compiled-defaults sweeps of the
  old form, router top-8 absorption, certified router-gate screens, grouped SDPA (SLC-absorbed),
  allocator-cache bump.

### 5b. Three laws established on the last day, and why they matter more than the nulls that produced them

**`L-BIMODAL-CONTROL-MANUFACTURES-PHANTOM-WINS`** (maple-frieren, #733; quantitative half from
maple-nezuko, #730). The single most transferable finding of the campaign.

> The bench host intermittently emits **control** runs 50–70 µs/step faster than its own median
> (8.148–8.152 ms versus 8.213–8.217 ms) and **0 of 24 arm runs ever reached that fast mode**. One
> fast-mode control adjacent to an arm run therefore manufactures a phantom 40–60 µs/step "win" with no
> code change behind it. Three arms screened at −33 … −64 µs/step and **all three** collapsed to
> null-or-worse at n ≥ 7.

Countermeasures, all measured rather than asserted:

- **Any n=2 estimate whose magnitude is below the screen's own achieved floor (~80 µs/step there) is
  `UNRESOLVED`, never a candidate.** Report the achieved floor or the estimate is uninterpretable.
- **Ordering is as load-bearing as n.** ABBA blocking cut control sd from 41.5 to 17.9 µs/step against a
  rotating order; achieved floors improved 78 → 45.2 → 14.9 → 10.3 µs/step across frieren's four stages.
- **Budget n ≥ 10 in ABBA blocks before spending a build-and-gate cycle**, not after.
- nezuko's independent floor arithmetic on the same host class: paired sd 22.94 / 34.11 µs/step ⇒
  ±36.5–54.3 µs/step resolvable at B = 4 blocks, hence **94 blocks / ≈12.5 h** to resolve the 0.79
  µs/step per-simdgroup effect at all. Her non-resolution band and his phantom band are the same band.

Read §6.6's requirement table next to this and the campaign's arithmetic closes: we needed 31–59 local
µs/step of win, and 40–60 local µs/step is precisely the width of the instrument's own noise. **Local
screening could not have decided this contest.** That is the honest bottom line and it should shape how
the next campaign allocates hours: fewer, longer, blocked measurements, or a different instrument.

**`L-ENV-DEFAULT-OFF-SHIPS-NOTHING`** (maple-fern, #686; independently confirmed by frieren #733 and
nezuko #730 in the same afternoon). `LagunaRuntimeWorker.swift:1966-2010` runs the submitted tree under
`sudo env_reset` plus `env -i`, against an allowlist. **A default-OFF `DARKBLOOM_*` flag therefore ships
literally nothing**, no matter how good its local number. Every win must arrive as a *compiled default*
— `case "0": … default: <new value>`, never `if env == "1"` — and beware selector polarity, since an
`== "new"` test ships the old default and delivers exactly zero. Corollary: an env-only finding is not a
result, it is a request for a patch.

**The "% of measured peak" gate has now refused three axes in a row** and is promoted from heuristic to
screening tool. QKV sits at 92.8–94.3 % of *measured* (not nominal) peak bandwidth, and on that basis it
correctly refused `ROWS_PER_SIMDGROUP` (#719), `ns` threadgroup granularity (#730) and, by the same
logic, the o_proj rows axis (#718). An axis within a few points of measured peak will not yield to
occupancy reshaping, and it can be declined **by reading rather than by running**. Note this replaced
the earlier `N-K3-AT-DRAM-ROOF` rule, which used *nominal* peak and was refuted; §7 item 4 still asks
for a re-audit of everything the old rule declined.

---

## 6. The channel, measured — and why it dominated the endgame

Median service time earlier today was **28.0 min** (maple-fern, interval-censored). By late morning
it had roughly doubled. Read the retraction below before using any earlier number from this campaign.

### 6.1 A wrong estimate, and the method that produced it

At 10:29Z I published — to all six students — "19 arrivals, 8 terminal in the window 08:06→10:29 ⇒
arrival ≈ 8/h, throughput ≈ 3.3/h, backlog growing ≈ 4.5/h", and concluded that **Maple's expected
remaining scored draws were ≈ 0**. Both the throughput figure and the conclusion were wrong.

Two defects, both worth remembering because they are generic:

1. **A poll-differencing throughput estimator is blind to short jobs.** Counting how many rows changed
   state between two widely spaced polls misses every submission created *and* finished inside the
   gap. The coarser the polling, the larger the undercount. It biases throughput down and only
   throughput down, so it manufactures apparent backlog growth.
2. **It assumed an open arrival process without testing the assumption.** The channel enforces one
   in-flight submission *per solver*. That makes it a **closed loop**: work in the system is capped at
   the number of active solvers, arrivals are throughput-limited by construction, and the backlog
   cannot diverge. The "+4.5/h backlog growth" described a system the rules do not permit.

The non-FIFO observation from that note survives and is still useful: `3872ee0` (09:14Z), `25d1be8`
(09:44Z) and `82bf9ef` (09:57Z) all reached terminal while `bbb49bc` (08:28Z), `1b5d6b7` (08:53Z),
`8031af5` (09:01Z) and our `4be372f` (09:20Z) were still pending. Any wait estimate built on
single-server FIFO is wrong.

### 6.2 The corrected model, measured at 10:47Z

Instrument: `senpai/tools/queue_cycle_stats.py` over the complete 1856-row `mlxfast submissions --all`
record. In a closed loop the right estimator is the gap between one solver's consecutive creation
times, which upper-bounds (service + turnaround).

- Non-terminal set: **9 submissions across 9 distinct solvers** — exactly one in flight per solver, no
  solver holding two. Closed loop confirmed by construction, and corroborated by **zero arrivals
  between 10:26Z and 10:48Z**: every active solver was waiting on its single slot.

| window | arrivals | active solvers | per-solver gap median / p25 / p75 / max (min) |
|---|---|---|---|
| last 24 h | 69 (2.9/h) | 15 | 31 / 25 / 49 / 118 |
| last 12 h | 62 (5.2/h) | 13 | 31 / 25 / 49 / 118 |
| last 6 h | 40 (6.7/h) | 11 | 43 / 29 / 68 / 118 |
| last 3 h | 27 (9.0/h) | 11 | **60** / 43 / 92 / 118 |

- Our own account's last six gaps: **25, 24, 88, 25, 31, 83 min** — the same doubling.
- Internal consistency check: 11 active solvers each cycling ≈ 60 min predicts ≈ 11/h fleet
  throughput, against 9.0/h observed arrivals. Throughput ≈ arrival, i.e. roughly **3× the 3.3/h I
  had reported**.
- The trend is **non-stationary** (median 31 → 43 → 60 min as the window narrows toward the close).
  Fit the p75 on the most recent hours; the 24 h median is not the planning number.

Corrected operational consequence: the shared account should expect **~3–5 more terminal draws before
17:00Z** if each is fired the moment the previous clears, and the last fire with better-than-even odds
of terminating is ≈ **15:00Z** (17:00Z minus the 92 min p75, plus margin), with ≈15:30Z the point past
which a draw is unlikely to score.

What survived the correction: student deliverables remain **portable hunks with honest prices** rather
than receipts, because the slot belongs to the sibling campaign from 10:00Z — that was always an
ownership fact, not a queueing one. The pulled-in ~12:00Z deadlines also survive, and are now better
justified: a hunk in hand by 12:00Z can actually reach a scored draw.

### 6.3 The generalisable lesson

*The submission channel is a shared, congesting, non-FIFO resource, and its service-time distribution
— not the local measurement apparatus — sets the campaign's effective planning horizon.* We measured
our kernels to 0.08 % and our queue not at all until the last morning.

The second lesson is sharper and was self-inflicted: **an operational estimate broadcast to a fleet
deserves the same instrument discipline as a kernel measurement.** I applied a two-sample estimator
with a known one-sided bias, did not test its central assumption, and overrode a student's
better-instrumented 28.0 min median with it. The fix cost twenty minutes of tooling
(`queue_cycle_stats.py`, `queue_probe.py` — mind the ANSI colour codes in the CLI output, which
silently made every row invisible to the first parser) and should have preceded the broadcast.

### 6.4 Directly measured service times, and the fire deadlines they imply

§6.2 estimated service indirectly, from *inter-arrival* gaps of the same solver. At 11:10Z I started a
direct instrument instead — `senpai/tools/queue_probe.py --minutes 27 --interval 75`, which snapshots
the full non-terminal set every 75 s, so a submission's **departure** from that set is observed to
within one interval. Creation times come from the listing, so service = departure − creation, bounded
by ±75 s. This is the first *unbiased* service measurement the campaign has had.

| submission | solver | created | departed (observed window) | service |
|---|---|---|---|---|
| `eabd21f` | uu0vg7 | 10:18Z | 11:22:35–11:23:52Z | **≈ 65.5 min** |
| `a5f5368` | uee9b6 | 10:26Z | 11:27:47–11:29:05Z | **≈ 62.9 min** |
| `bbb49bc` | DawgZter | 08:28Z | 11:29:05–11:30:22Z | **≈ 182 min** |
| `4b8ab50` | ooo9cj | 10:03Z | ≤ 11:06Z (listing) | **≤ 63.2 min** |
| `4be372f` | morganmcg1 (ours) | 09:20Z | ~11:0xZ (listing) | **≈ 100 min** |

Five direct samples: median ≈ **65 min**, spread **63 → 182 min**. Three structural facts fall out of
the same trace and each one changes how the channel should be driven:

1. **The service is concurrent, not a single server.** Ten submissions from ten distinct solvers sat
   non-terminal simultaneously at 11:10Z. The single-concurrency limit is **per solver account**, not
   per benchmark. So a campaign's throughput is set by *its own* fire-the-moment-it-clears discipline
   and not by contention — congestion shows up as longer service, not as blocking.
2. **Non-FIFO, confirmed by departure order.** Departures ran 10:18Z, then 10:26Z, then 08:28Z, while
   08:53Z, 09:01Z and 09:45Z were still pending. A 3× service spread at equal queue position means an
   individual receipt's ETA cannot be predicted; only the distribution can. Plan on the p75, never on
   the median.
3. **Zero arrivals between 11:08Z and 11:30Z with 7–10 in flight.** Every active solver in the fleet
   was waiting on its own single slot — the closed-loop assumption of §6.2 is now observed directly,
   not inferred.
4. **Rivals re-fire within minutes of clearing, which is the competitive standard we are being held
   to.** The probe caught both halves of the loop for two accounts. `uu0vg7` departed in the
   11:22:35–11:23:52Z bracket and its next receipt `c0542e8` was created 11:32Z (≤ 9 min turnaround);
   `uee9b6` departed 11:27:47–11:29:05Z and re-fired as `7a7a773` at 11:32Z (≤ 4 min). Pending count
   went 7 → 9 on that one poll. Both accounts are therefore running a *pipeline*: prepare the next
   candidate while the current one is in service, and fire on the resolution edge. At ≈65 min service
   and ≈5 min turnaround those two accounts each get ~4 further draws before 17:00Z. Any campaign that
   instead prepares its next candidate *after* the slot frees pays the preparation time twice — once in
   wall clock and once in a forgone draw. **The scheduling discipline, not the queue, is the binding
   constraint.**

**Fire deadlines, from the direct samples.** At the 65 min median a draw fired at time *T* resolves at
*T*+65; at the 100 min p75, *T*+100; the 182 min tail is real and unpredictable. Against the hard
17:00Z close:

- Last fire that resolves at the **median**: ≈ **15:55Z**.
- Last fire that resolves at the **p75**: ≈ **15:20Z** — this is the number to plan on.
- Fired back-to-back from 11:35Z at p75: terminals ≈ 13:15Z, 14:55Z, 16:35Z ⇒ **3 more draws**; at the
  median, 4.
- **Unresolved and worth flagging to the organizers rather than guessing: whether a submission created
  before 17:00Z but resolving after it still counts.** Every deadline above assumes it does not.

**The cost of an idle slot, priced.** Our shared account's last fire was `4be372f` at 09:20Z; it went
terminal ~11:0xZ, and nothing has been fired into the free slot since. At p75 service one draw costs
100 min of wall clock, so an idle slot burns draws at **0.25 draw per 25 min**. The original version
of this paragraph justified the urgency by pointing at delta 1 ("already measured and sitting in a
patch file") — that justification is dead, delta 1 is a regression, and **the urgency is entirely
unchanged**, for the reason set out in §6.5: on this instrument an idle slot is expensive even when
you have nothing new to put in it.

Method note for reuse: the probe is 30 lines and it should have existed on day one. Direct
event-based measurement of a shared resource beat two rounds of increasingly careful inference from
aggregates — and it also cost nothing, because it ran read-only next to the real work.

### 6.5 A draw has option value with zero deltas — and the second arithmetic error, found while pricing it

**Measured slot state, `mlxfast submissions` (my-submissions view), read 11:52Z.** Last draw on the
shared `morganmcg1` account: **`4be372f`, created 09:20Z, terminal ~11:0xZ, rejected 2.57671436**.
**No row after it. No row in a pending state.** So at 11:52Z the account had been idle for ~50 min
and had *nothing in flight* — against a 65 min median / 100 min p75 service time and a 17:00Z close.

While pricing that idleness I re-derived the gap to the bar from the two raw numbers and it did not
match what §4b had said. It is a **second arithmetic error of mine, in the same table as the first**:

```
bar   2.6195531094824   (organizer commit 4ea72c3b, receipt cdcd091)
best  2.60664970        (e27f1ce, shared account best-ever)
(2.6195531094824 - 2.60664970) / 2.60664970 = 0.0049502 = +0.4950 %
```

§4b said **+0.378 %**. The true gap is **+0.4950 %** — 31 % larger. And 0.378 ≈ the 0.38 I had
attached to delta 1, which is almost certainly where it came from: I let the gap take the value that
made the story close. That is the same contamination as §4c wearing different clothes, and it is the
reason edward's R127-A audit (#741) exists. Note how the *σ-multiple* survived both errors — I quoted
"≈1.02σ at σ ≈ 0.37 %" and then "1.01σ at σ ≈ 0.49 %" — which is exactly why neither error was caught:
**a wrong numerator over a wrong denominator kept giving me the right-looking σ multiple.** Both of
those σ values are themselves wrong; the measured one is 0.19–0.23 % and the gap is **2.2–2.7σ**, not
1σ. That is error three, below.

**Now the part that matters operationally — and it is the reverse of what earlier revisions of this
section said.**

Earlier revisions priced a re-draw of the unchanged best tree at **P ≈ 15.6 % per draw** from
σ(one official draw) ≈ 0.49 %, and stated in bold that σ had *never been measured by replication on
this channel* because the account had never fired the same commit twice. **Both halves of that are
wrong. This is my third error of the day (§0), and it is the most consequential of the three**, because
it is the one that set the endgame's priorities rather than just one candidate's price.

**Primary source, in this repository, from an earlier round of this same campaign:**
`research/advisor-r103-submission-tree-provenance-and-replicate-noise.md` §5, machine-readable artifact
`research/artifacts/advisor-r103/replicate-sigma.json`, scripts
`research/advisor_r103_replicate_sigma.py` (grouping) and `research/advisor_r103_verify_null_group.py`
(verification). Recomputed independently from the per-receipt scores — not from the artifact's own
summary fields — by `research/tools/recompute_replicate_sigma_and_draw_odds.py`, whose output is the
source of every number in this subsection.

The reusable method: group draws by a **comment-insensitive sha256 digest of `Sources/`** (drop Swift
`//` lines before hashing) instead of by commit SHA, then run a verifier proving every differing line
in a group is a Swift marker comment outside an MSL string literal. That turns "0 repeated commits"
into **18 replicate groups over 139 fetched receipts, 7 with metrics**. My 11:52Z listing parse and my
own exact-git-tree probe both reported "no replicates" because both keyed on identity of the
*artifact* rather than identity of the *program*. Cosmetic marker comments — exactly what a campaign
adds so it can tell its own draws apart — are what hid the replicates from both probes.

**Measured σ of one official draw at fixed program** (sd of ln(candidateScore) within group):

| group digest | n | sd(ln cs) | notes |
|---|---|---|---|
| `dc437b0e` | 5 | **0.2276 %** | one session 08-09; range 0.5795 %; sd(D) 14.43 on mean D 4910.925 µs/step |
| `521a2f71` | 4 | 0.2080 % | |
| `1008c692` | 4 | 0.1776 % | |
| `d18d0983` | 3 | 0.1292 % | |
| `4d5ac413` | 2 | 0.1066 % | |
| `9beb75a6` | 2 | 0.0871 % | |
| `7cbffc2c` | 4 | 2.2366 % | pathological, see below |
| **trimmed pool** | dof 14 | **0.1860 %** | excludes `7cbffc2c`; untrimmed 0.9546 % (dof 17) |

Consistency check that makes me trust the 0.2276 %: propagating the same group's leg dispersion
through the score model gives `0.75·sd(ln D) = 0.2204 %` ⊕ `0.25·sd(ln P) = 0.0257 %` = **0.2219 %**,
against **0.2276 %** observed on the score itself. The instrument behaves exactly as the scoring model
says it must, which is the strongest available evidence that this σ — and not the 0.49 % — is the real
same-program dispersion.

**Where 0.49 % actually came from:** the archive's σ figures (`σ(score) 0.6172 %`, `session σ 0.5393 %`,
`cand_dec 0.2939 %`) are **cross-code** modelled quantities — dispersion across draws of *different*
trees, which contains real content differences. Using one of them as the σ of a *same-tree* re-draw
inflates it by 2.4–2.6×. Note also that r103 had already falsified the archive's modelled
"0.067 % within-session"; the truth sits between the two, and neither of the inherited numbers was
right.

**The pathological group is one-sided, and that detail is decisive.** `7cbffc2c`'s four draws are
2.5402 / 2.5525 / 2.4964 (P = 206.5) / 2.4293 (P = 222.4): the excursions are contention/thermal and
they **only ever subtract**. The fat tail of this instrument therefore carries essentially **no upside
probability**. You cannot buy a high draw out of variance you only have on the downside.

**Corrected price of re-firing the unchanged best tree.** The gap is +0.4950 %, so the required
excursion is:

| σ used | required move | P(one draw ≥ bar) | 3 draws |
|---|---|---|---|
| 0.2276 % (worst well-behaved group) | **2.17σ** | **1.5 %** | 4.4 % |
| 0.1860 % (trimmed pool) | **2.66σ** | **0.4 %** | 1.2 % |

**≈1 % per draw; ≈1–4 % for the three draws that remain** — and shrink that further, because 2.60665 is
the **maximum of 106 draws**, so the number we extrapolate from is inflated by winner's curse: the
tree's true mean is below it, which makes the required move *larger* than 2.17–2.66σ, not smaller.

**So the sentence that closed the earlier revision of this section — "the marginal value of a draw does
not come from the delta you put in it, it comes from the variance" — is false on this instrument, and
is retracted.** It was the load-bearing claim of the endgame plan. On a channel with σ = 0.19–0.23 %
and one-sided-negative tails, a 0.50 % gap is not closed by luck; it is closed by a delta. What a
delta has to be worth:

| real gain on the ranked host | P(one draw ≥ bar) | 3 draws | note |
|---|---|---|---|
| 0 (re-fire incumbent) | 0.4–1.5 % | 1–4 % | today's actual position |
| ~~**+0.26 %**~~ | ~~10–15 %~~ | ~~28–39 %~~ | **SUPERSEDED — see §6.5c. Correct value ≈3.2 %.** |
| ~~**+0.50 %**~~ | ~~≈51 %~~ | ~~≈88 %~~ | **SUPERSEDED — see §6.5c. Correct value ≈8.0 %.** |

(Ranges span σ = 0.1860–0.2276 %.) **This delta table is wrong by ≈6× and the error is the winner's
curse it acknowledges two paragraphs above but does not apply: it measures the required move from the
lucky draw `2.60664970` instead of from that program's mean `2.582263`. Corrected in §6.5c. The
re-fire row survives as an upper bound only.** In µs/step, via §6.6: **+0.26 % ≈ 17 µs/step on the ranked host**
(the local equivalents in this sentence originally read ≈44 and ≈84 µs/step; I then "corrected" them
to 31 and 59, which was **error 6 — backwards**. The original **44 / 85 µs/step is right**, confirmed
independently by #741),
**+0.50 % ≈ 32 µs/step ranked**. For scale, the largest per-knob effect Maple measured all campaign is
≈0.8 µs/step per simdgroup per threadgroup, and the delta advertised in §0 turned out to be −4.7
µs/step. **Nothing in Maple's option set is within an order of magnitude of the requirement.** That is
the honest end-state, and it is what the 15.6 % table was concealing.

**What this changes about the schedule, and what it does not.** An idle slot is still worth firing:
~1 % beats 0 %, it costs nothing, and per §6.4 an unused slot cannot be recovered later. What changes
is the *ranking of reasons*: never justify a schedule decision by the option value of variance again,
and never trade a real delta's preparation time for one more draw of an unchanged tree. The remaining
genuine value of a repeat draw is informational, not competitive — it extends the replicate series that
produced the 0.1860 % above, using the digest method rather than commit identity to group it.

Corpus facts from the 11:52Z parse, still valid: n = 106, statuses `{rejected, promoted}`, single
`promoted` row **`97a5090` at 2.58882784 (commit `3e165fa5`, 8/6 05:04Z)** — promotion is against the
*bar of the day*, so a 2.5888 promoted then and a 2.60665 rejected now is consistent, and is the
cleanest evidence in the corpus that the bar has been rising under us. Top-10 distinct-tree scores:
mean 2.595690, sd 0.004625 (0.178 %) — the dispersion of an order-statistic tail across *different*
trees, so it is not σ and must not be used as σ, notwithstanding that it lands suspiciously close to
the true same-program 0.186 %. That coincidence is to be resisted, not cited.

Consequences, stated plainly for whoever owns the slot:

1. **Do not let the slot idle** — but for the right reason. Re-firing the incumbent is worth ≈1 %, not
   ≈15 %; it is still the best available act on a clear slot with nothing new ready, because it is free
   and unused capacity is destroyed. It is *not* a substitute for a delta and must never be scheduled
   in preference to preparing one.
2. **Pipeline the preparation**, as both rival accounts demonstrably do (§6.4 fact 4: re-fire within
   4–9 min of clearing). Prepare the next candidate *while* the current one is in service.
3. ~~**Fire deadline to plan on is 15:20Z** (p75), 15:55Z at the median.~~ **SUPERSEDED at 12:06Z by a
   fresher direct read (maple-fern, #686), and the correct deadline is ≈14:40Z.** Her observation: 9
   non-terminal rows, *all* in `validating`, none of them ours, head-of-line `ggt54` already 141 min
   old ⇒ realised sojourn ≈2.3 h, not the 65–100 min my service-time model assumed. That leaves
   **~2 realistic shots for the whole shared account** and a practical last fire of **≈14:40Z**.
   My 15:20Z came from a distribution of *completed* service times, which is survivorship-biased
   against exactly the slow tail that is now in the queue; her number came from the age of the jobs
   actually sitting in it. Age-of-queue beats service-time-distribution whenever the queue is visible —
   that is the generalisable form, and it belongs with §6.3.
   Our own slot was measured **idle ≥66 min** at 12:06Z (last row `4be372f`, created 09:20Z, terminal
   ≈11:00Z, rejected at 2.57671436). Idle time before the deadline is deleted draw capacity and cannot
   be recovered later.
   **Update, my own read at 12:46Z:** the idle period ended — the account has exactly one row in
   flight, **`5fae2f1`, created 12:16Z, `validating`**, so the slot was idle ≈76 min (11:00Z → 12:16Z)
   and is now busy. At fern's ≈2.3 h sojourn it adjudicates **≈14:30Z**; *if* service is serial (every
   row in the history is consistent with it, but creation timestamps cannot prove absence of overlap)
   then the next fire starts ≈14:30Z and lands ≈16:50Z — inside the close by ~10 min. **So the
   operational deadline is not "fire by 14:40Z", it is "be built, green and hash-checked *before*
   14:30Z", because the window opens without warning when `5fae2f1` clears.** Not Maple's fire.
4. Maple's own position, for the record: per operator direction Cedar owns the submission slot from
   10:00Z, Maple fires nothing, and Maple is **not** reconstructing the `e27f1ce` tree. This section is
   the analysis handed to the slot's owner, not a plan Maple intends to execute.

### 6.5b Independent confirmation from the opposite direction — the winner's curse (maple-fern, #686)

While I was regrouping receipts by program, maple-fern reached the same conclusion by a route I had not
considered, and she got there first. It is recorded here as hers. Primary source:
`research/fern-r109f-interim-1200Z.md` ADDENDUM 2 §L, on PR #686 head `bd475704` (closed unmerged
because the branch also carried the refuted delta-1 hunk; the document is a primary source, not an
interim).

**Her argument.** My probability table assumed our best tree needed a fresh upward excursion equal to
the whole gap. It does not, because *the excursion is already spent*: the receipt we hold is itself a
lucky draw.

- `draw(e27f1ce) = 2.60664970 / 2.582263 = 1.009444` — roughly a **p96** draw of its own program.
- The multiplier still needed is therefore only `2.6195531 / 2.582263 = 1.014441`.
- Decomposing **1280** official rows into (program × draw) gives a draw distribution with median
  **1.001830**, sd **0.538 %**, p95 1.012550, max 1.024492.
- `z = (1.014441 − 1.001830) / 0.00538 = 2.344` ⇒ **0.95 % per draw normal, 1.48 % empirical**;
  2.94 % over two draws, 4.37 % over three.

**My table was optimistic by ≈10.5×, and she found it unprompted.** My own within-program route gives
`z = 0.4950 / 0.1860…0.2276 = 2.17…2.66` ⇒ ~1.5 % per draw. ~~Two independent methods, one answer:
**~1–1.5 % per draw.** That agreement is worth more than either point estimate, and it is the number
any successor should plan against.~~ **The agreement is spurious and the retraction is §6.5c: my route
took the *lucky draw* as its reference point, which is the very error hers corrects. Applied
consistently from the program mean, my within-program σ gives z = 6.3–7.8 ⇒ P ≈ 0, so the two methods
bracket rather than confirm: plan against `[≈0 %, 1.5 %]` per draw with the point estimate read off her
empirical tail. Her arithmetic reproduces to six digits; mine did not survive.**

**Two populations — say which one you mean.** Her 0.538 % and my 0.186–0.228 % are not in conflict;
they measure different things, and the difference is operational:

| estimate | what it is | prices the question |
|---|---|---|
| mine, 0.186–0.228 % | within-program replicate noise, same program re-fired | *"re-fire the tree we already hold"* |
| hers, 0.538 % | the draw component recovered across 1280 rows spanning many programs | *"fire something new and hope"* |

Hers legitimately carries the between-program leakage that program-hashing removes, so the truth is
bracketed at ≈0.19–0.54 %. Both give ~1–1.5 % for one more draw.

**One softening I owe in the other direction.** Because the crown is a **p99.3** draw (×1.016694), my
flat statement elsewhere that there is "no upside probability" is too strong. The correct statement is
**thin upside, ~1–1.5 % per draw, and asymmetric.** The asymmetry is measured, not assumed: the one
high-σ replicate group, `7cbffc2c` (n=4: 2.4293 at P=222.4, 2.4964 at P=206.5, 2.5402, 2.5525),
consists **entirely of downward excursions** — a −2.4 % tail with no matching +2.4 %. Bad draws are the
fat side.

**The strategic consequence, in her words, and it is the headline of the endgame:**

> Our normalized **2.582263** already exceeds the crown's normalized **2.576540**. We lose on draw
> variance, not on code.

Two things follow, and both are now policy. First, **cutting verification gates to buy extra draws is
not rational**: the expected gain from one more draw is ~1.5 % while the downside of an unverified tree
sits on the fat side of the distribution. Second, the campaign's remaining effort belongs on the
handover and the channel schedule, not on manufacturing a marginal candidate — which is what §0's
failure mode actually was.

### 6.5c Error 5 — the delta-pricing table inherited the winner's curse, and it is wrong by ≈6×

Found at 12:45Z, by re-deriving every figure in §6.5/§6.5b from its inputs instead of transcribing
them (rule 8), in `research/tools/slot_holder_arithmetic.py`. Run it; it prints the manifest's own
values next to the recomputed ones so any disagreement is visible.

**What reproduced exactly.** Gap +0.4950 %; bar draw factor ×1.016694 (p99.3); our best draw factor
1.009444; multiplier still needed 1.014441; z = 2.344 ⇒ 0.95 % normal / 1.48 % empirical. fern's §6.5b
arithmetic is confirmed to six digits.

**What did not.** Two claims in §6.5, and both are mine.

**(a) The "two independent methods, one answer" agreement in §6.5b is spurious.** My within-program
route divided the gap by σ *measured around a program mean* while taking the **lucky draw** as the
reference point: `0.4950 / 0.1860…0.2276 ⇒ z = 2.17…2.66`. But if `2.60664970` is itself +0.9444 %
above its program's mean, the required move from that mean is +1.4441 %, and against within-program
σ = 0.1860–0.2276 % that is **z = 6.3–7.8, i.e. P ≈ 0 under any normal model**. So my σ route does not
agree with fern's 0.95 %; correctly applied it says re-firing an unchanged tree is *hopeless*, not
"~1 %". The agreement I celebrated came from applying the winner's-curse correction in fern's method
and not in mine.

**The honest statement, which is a bracket and not a point estimate:**

| method | reference point | P(one more draw of the tree we hold ≥ bar) |
|---|---|---|
| within-program σ 0.1860–0.2276 %, normal | program mean (correct) | **≈0 %** (z = 6.3–7.8) |
| fern's draw component, sd 0.538 %, normal | program mean (correct) | **0.95 %** (z = 2.344) |
| fern's draw component, **empirical tail** | program mean (correct) | **1.48 %** (her figure; 1.48 % of 1280 rows ⇒ ≈19 rows at or above 1.014441, which is what a tail count of her decomposition would give — attributed to her, not re-derived here) |

The empirical 1.48 % is the **upper** bound: fern's 0.538 % legitimately carries between-program
leakage that program-hashing removes, so the tail it counts is inflated by code differences that a
re-fire of one fixed tree does not get. **Plan against `[≈0 %, 1.5 %]` per draw, and read the point
estimate off the empirical tail, not off any normal model.** Nothing about the endgame conclusion
changes except its strength: re-firing is worth even less than the previous revision said.

**(b) The delta table — the one that decides whether building a delta is worth the hours — was
computed from the lucky draw and is wrong by ≈6× in the flattering direction.** Repriced from the
program mean `2.582263` against fern's draw distribution (median 1.001830, sd 0.538 %):

| real gain on the ranked host | required draw factor | z | P(one draw ≥ bar) | 3 draws |
|---|---|---|---|---|
| 0 (re-fire incumbent) | 1.014441 | 2.344 | **0.95 %** (empirical 1.48 %) | 2.8 % (4.4 %) |
| **+0.26 %** | 1.011806 | 1.855 | **3.2 %** ~~10–15 %~~ | 9.2 % |
| **+0.50 %** | 1.009394 | 1.406 | **8.0 %** ~~≈51 %~~ | 22.1 % |
| **+1.00 %** | 1.004397 | 0.477 | **31.7 %** | 68.1 % |
| **+1.26 %** | 1.001830 | 0.000 | **50.0 %** | 87.5 % |

So the delta that makes a draw an even-money bet is **≈+1.26 % of score ≈ 82 µs/step on the ranked
host** (§6.6 currency 0.01527 %/µs) — not the +0.50 % this document has been quoting all day.
Against a campaign whose largest measured per-knob effect is ≈0.8 µs/step, the conclusion in §0 does
not merely survive the correction, it hardens by a factor of six: **there was no reachable delta, and
the correct end-state was always the handover.**

**Why this error survived three passes.** Each pass fixed the input the previous pass had misread
(0.378 → 0.4950; σ 0.49 → 0.186; then fern's curse), and each time I re-derived only the row I was
looking at. The delta table sat two paragraphs below a sentence that *states* the winner's curse in
words — "the tree's true mean is below it, which makes the required move larger" — and I still did not
propagate it into the numbers. **Rule 14, earned here: when you correct a reference point, recompute
every row that shares it, in a script, in one pass.**

### 6.6 Four µs/step currencies — the landmine underneath every price in this document

Found at 12:10Z while converting §6.5's "+0.26 % / +0.50 %" into engineering targets; completed at
12:35Z once nezuko (#730) and frieren (#733) reported their harnesses' actual step lengths. **This
document quotes µs/step in four different units and never says so.** Using any one where another
belongs is up to a 2.6× error, always in the direction of making a candidate look sufficient.

Arithmetic: score `= decode_speedup^0.75 · prefill_speedup^0.25`, so a saving of 1 µs on a decode step
of length `S` µs is worth `0.75 / S` of score. The 0.75 is already folded into the table.

| currency | decode step | 1 µs/step is | provenance |
|---|---|---|---|
| **ranked host** (what the receipt scores) | **4910.9 µs** | **0.01527 % of score** | measured: `mean_D` of replicate group `dc437b0e`, n=5, r103 artifact |
| ~~**`--local-submit` on our M4**~~ | ~~8882 µs~~ | ~~0.00845 %~~ | **WITHDRAWN (#741 F16): zero real in-tree hits.** Do not reuse |
| ~~**frieren's bench control host**~~ | ~~8213 µs~~ | ~~0.00913 %~~ | **WITHDRAWN (#741 F16): 8213 is one token-step of 765 away from the control medians 8189/8192 — noise promoted to a constant** |
| **local `--local-iterate` M4** | **12 798 µs** (`seed/128 + step`) | **0.00586 % of score** | **VINDICATED (#741 F1): ~40 in-tree measurements; this is the correct local currency** |

Three consequences. **All three were rewritten at 15:45Z after maple-edward's #741 census inverted
this section; the struck rows above are what it used to say.**

**(a) ~~The 0.00586 %/µs constant cannot be sourced.~~ It is the correct local currency, and the two
constants I offered as replacements were the unsourced ones.** edward derived the conversion rather
than looking it up: `score = decode_speedup^0.75 · prefill_speedup^0.25` ⇒ `d ln(score)/dD = −0.75/D`
identically, so the only question is *which D*. With the `--local-iterate` denominator this repo
actually uses (`D = seed/128 + step ≈ 12798 µs`, ~40 in-tree measurements) the answer is
`0.75/12798 = 0.00586 %/(µs/step)`. My "UNSOURCED, never reuse" brand is **retracted** — and see rule
16(a): a false provenance label is worse than a false number, because the next reader deletes rather
than re-derives. The delta-1 headline (`66.88 × 0.00586 = 0.392 %`) was manufactured by a
**sign-inverted counterfactual (§4c), not by a bad currency**. Consequently the reprice instruction I
issued against frieren's #733 disposition table — "FUSED is −0.504 %, not −0.323 %" — is **withdrawn**;
his original −0.323 % stands. No disposition changes either way, since they are all losses being kept.

**(b) A likely mechanism for how a wrong step length entered circulation**, found by fern (#686): the
1023-vs-128 decode-step trap, `Constants.swift:117-118` versus `:109`. Configured one way, prefill
share reads 15.35 % of the run instead of 1.92 % — an ~8× under-read of prefill and a correspondingly
distorted decode step. Any harness that mixed the two configurations produces step lengths that are
neither host's true step.

**(c) A µs/step delta does not cross hosts at all.** Only a *relative* claim crosses, and only with an
argument: #473 measured that **~42 % of kernel-local wins evaporate end-to-end**, so even fractional
transfer is optimistic. The ranked rate is the one to price against when the question is "does this
clear the bar"; convert to a fraction of the measuring host's own step *first*, then compare.

Requirement table, **recomputed 15:35Z** in the two currencies that survive
(`research/tools/reprice_draw_1535Z.py`, which prints the published value beside the recomputed one).
Probabilities are the error-7 corrected ones (σ = 0.3728 %, centred on the **program mean**):

| target | % of score | ranked µs/step (4910.9) | **local µs/step (12798)** | P(clears today's bar) |
|---|---|---|---|---|
| no delta, replay | 0.00 | 0 | 0 | **0.04 %** |
| +0.26 % | 0.26 | **17.0** | **44** | 0.39 % |
| +0.50 % | 0.50 | **32.7** | **85** | 2.2 % |
| +1.00 % | 1.00 | **65.5** | **171** | 24.6 % |
| +1.26 % (even money) | 1.26 | **82.5** | **215** | 50.1 % |

**Two struck claims.** ~~"The old table's 44/84 column used the unsourced 0.00586 %/µs and set a bar
~40 % too high."~~ Backwards on both counts: 0.00586 is the right currency, and the column I replaced
it with (31/59, from the withdrawn 8882) set the bar **≈30 % too LOW** — flattering, like every other
error in this document. ~~"3.2 % / 8.0 % / 50 %."~~ Those came from the pre-error-7 σ; the corrected
column above is what to quote. The local column here reproduces edward's independent 44/85 exactly.

For scale, and this is the whole story of Maple's endgame: the biggest per-knob effect the campaign
measured is ≈0.79 µs/step per extra simdgroup per threadgroup (§5,
`L-TG-WIDTH-IS-A-DEBIT-AT-tgMem-0`) and it has the wrong sign; the refuted §0 delta was −4.7 µs/step;
the largest *confirmed* effect anywhere in the ledger is frieren's +55.2 µs/step FUSED **loss**. To
clear the bar we needed 32 ranked µs/step of *win* and the fleet never located one of any size.
Meanwhile every candidate that appeared to be that big — three of frieren's screens at −33…−64 µs/step
— was the instrument (§5b). The **44–85 local µs/step** target band (corrected; the 31–59 printed here
before was error 6) and the **40–60 µs/step phantom band** are the same band, which is the deepest
reason this campaign could not have succeeded by local screening alone. The correction makes the
overlap *worse*, not better: the smallest delta worth firing sits squarely inside the range where this
host manufactures wins out of a bimodal control.

~~One figure this correction rescues: §7 item 2's "≈8919 µs wall vs ≈8567 µs busy" is now identifiable
as a local M4 wall step, consistent with nezuko's measured 8882 — so its ~350 µs of non-busy time is
worth 2.94 % of score locally… the largest single decode opportunity in the document, and it got
*bigger* under audit.~~ **WITHDRAWN in full. #744 (maple-alphonse) went looking for the 8919 µs wall
and found no primary source for it; 8882 is itself withdrawn (#741 F16, zero in-tree hits). So this
paragraph rescued one unsourced number by leaning on another.** The measured gap is **232.5 µs/step**,
flat, overlap 0/6132 — and unreachable in practice: fission costs +1016 µs/step and the apparatus
confound is +203…+416 µs/step. This is the cleanest illustration in the document of the failure mode
in rule 8: two numbers that agreed with each other, neither of which had ever been measured.

**Rule for reuse: never write a µs/step number without naming the host it was measured on.** Prices in
percent-of-score are safe to move between sections; prices in µs/step are not.


### 6.7 The target side — what a fire has to BEAT, and why `accepted` never meant what we thought

§6.1–§6.6 price the **channel**: will the row adjudicate, will it score, when must it be fired. None of
it priced the **target**. maple-fern (#745, final commit) opened the four snapshot fields nobody in
either cohort had read — `officialScore`, `claimedScore`, `improved`, `promotionStatus` — and the
semantics invalidate a piece of fleet-wide self-assessment that had been quietly mispricing every arm.

**(1) `accepted` means "took the world record at that instant", not "was a good submission".**
`improved == True` on exactly the 148 accepted rows. Testing the two candidate definitions:
`improved == (score > GLOBAL prior max)` holds on **1294/1296 = 99.85 %** of scored rows, versus
**905/1296** for the account's-own-prior-best model. So the 1148 rows rejected with "score did not
improve current best" are **the ordinary outcome — 88.6 % of every scored fire in the log**. Our
record of *1 accepted in 177* therefore reads "we held the crown once", not "we fire badly". Every
place in this document that treated a non-`accepted` row as evidence of a defect was wrong, and so was
the fleet morale that followed from it.

**(2) The bar is read at ADJUDICATION time, not fire time** — the global-max model agrees 1294 times
against 1288 for a fire-time read. This is operationally new and it is a live hazard for any row
sitting in `validating`: **a competitor record landing mid-validation raises the bar underneath a row
already in flight.** fern reported the two disagreeing rows rather than smoothing them: the first
scored row is not marked improved (the ratchet starts at or above the ≈1.0004 baseline), and one row
is marked improved against a standing best 0.43 % higher, which looks like a race.

**(3) The ratchet has stalled.** Advances by day: 29 on 08-01, then 7, 7, 1, 0, 3, 3, 1, 0, 0, 1 —
**two advances since 08-08**, at +0.391 % and +0.117 %. The bar in force, 2.6195531094824, was set by
`ggu77wt` at **09:34:06Z on 08-11**.

**(4) Era-first crown probability, and fern lowering her own published prior to fit it.** Our best
receipt `e27f1ce` at 2.60664969895906 needs **+0.4950 %** to take that bar. Fires that cleared their
own standing bar by ≥ that margin: **all-time 61/1295 = 4.71 %**, **current era 0/158 = 0.00 %
(≤1.88 % one-sided 95 % Clopper–Pearson)**. Chained with §6.4's channel number:

> **P(crown from the last available draw) ≤ 0.796 × 1.00 × 1.88 % = ≤1.50 %.**

Her own previously published per-draw prior of 1.5–2 % (mid 1.75 %) sits *above* that ceiling, so she
retracted it, and the check `published_prior_exceeds_era_ceiling` is **computed in the tool, not
asserted in prose**. She ran the era split *before* publishing — the exact trap that had caught her one
result earlier — and kept 4.71 % only as an explicitly labelled optimistic bound.

**(5) Bar-rise hazard before close**, both routes, reported as ranges: **calendar 3.2–15.3 %,
in-flight 9.2–32.0 %**.

**How this reconciles with the other two bounds, which it must not be averaged with.** Three
independent populations now bracket the same decision:

| bound | population | value |
|---|---|---|
| §2a | our own account's 106 draws vs today's bar | 0/106 ⇒ **≤2.83 %** |
| §6.7 | all 158 current-era fires clearing by our required +0.4950 % | 0/158 ⇒ **≤1.88 %** |
| §0a (F19) | parametric, σ = 0.3728 % predictive sd | **≈0.04 %** point estimate |

They are different quantities and averaging them would be meaningless. But the two model-free ones
share **no input** and agree, and the parametric one sits inside both. Per **rule 17**, the number to
carry forward is the bound, not the estimate: **a re-fire of the tree we already hold is worth ≤1.5 %
of a crown after the channel discount.** Fire it if the slot frees — the alternative is worth exactly
zero — but do not pay anything to buy that draw.

**Addendum, 15:53Z — the slot freed, and the bar did not move.** A final `mlxfast submissions` poll
resolves both open operational unknowns, ~67 min before close:

- **`c06b1b6` is terminal** — fired 13:51Z, `rejected`, official score **2.58896632157301**. No row is
  in flight. fern's *P(the slot never frees) = 8.3–15.4 %* **did not materialise**; service time on
  that row was **≤ 2 h 02 min**.
- **The bar is unchanged at 2.6195531094824**, and this is a *fresh* reading rather than the 09:34Z
  one repeated. Because `diff = score − bar_at_adjudication` in raw score units (item 2 above), every
  terminal row is a timestamped bar reading: `c06b1b6` implies **2.6195533**, within the ±5e−7 print
  resolution of a 6-dp `diff`. Cross-checked on `e27f1ce` (`diff −0.009854` ⇒ **2.6165037**,
  reproducing the known 8/10 bar to seven digits). **Required margin stays exactly +0.4950 %**, and
  the ratchet stall now extends to ~6.5 h. `research/tools/bar_read_1553Z.py`.
- Every "0 in n" denominator gains one clean fire: **107** draws (CP ≤2.76 %), **54** consecutive
  clean fires (CP ≤5.40 %), **159** era fires clearing our margin (CP ≤1.87 %). No decision changes.

*Two of my own slips inside that ten-minute check, both caught before they shipped: the first draft
compared bars at 1e−9 and reported a phantom advance of +2.1e−7, and the first draft of the bound
table updated a rule-of-three denominator and read the result against a Clopper–Pearson figure,
producing a bound that appeared to get **worse** after a clean observation. Rule 20.*

---

## 7. Open threads, in descending order of unexplained budget

1. ~~**~27.88 ms of the 97.9 ms prefill seed forward is unattributed.**~~ **RESIZED by #743
   (maple-tanjiro), and the denominator was fiction.** The residual is **22.43 ms**, not 27.88 ms;
   the **97.9 ms was never a local measurement** on this host, and the "1.9×" I had attached to it
   was a µs/token-vs-µs/forward units slip. Of the 22.43 ms, named causes explain only **5.03 ms
   (22.4 %)** — so **17.40 ms remains genuinely unexplained** and this is still the largest
   unattributed block on the board. It stays open, but at the corrected size and without the
   fabricated ratio.
2. ~~**Decode wall ≈ 8919 µs vs busy ≈ 8567 µs ⇒ ~350 µs of non-busy time.**~~ **CLOSED by #744
   (maple-alphonse): the wall I asked him to attribute has no primary source.** The real
   wall-minus-busy gap is **232.5 µs/step**, flat across the run (no growth, so not a leak),
   cross-checked two independent ways (231.3 vs 232.5, Δ1.2 µs), with command-buffer overlap
   observed in **0 of 6132** steps. The instrument itself is free. Two reasons not to spend a slot
   here: kernel **fission costs +1016 µs/step**, ~4.4× the entire prize; and the apparatus confound
   is **+203…+416 µs/step**, i.e. larger than the effect being measured. Axis closed.
3. ~~**Mechanism of the threadgroup-granularity win.**~~ **CLOSED, NOT OPEN — there is no win.** This
   item asked for the mechanism of a "+0.38 % with occupancy pinned" effect that §0 shows never
   existed. The measured mechanism is the opposite one and it is banked: at
   `staticThreadgroupMemoryLength = 0` a wider threadgroup is a **debit** of ≈0.79 µs/step per extra
   simdgroup (§5, `L-TG-WIDTH-IS-A-DEBIT-AT-tgMem-0`; #714 + #729). TG widening is therefore *not*
   indicated for the QKV pool or the expert QMV pool; #730 and #731 tested exactly that and found
   debits (#731: routed wall +23.12 µs/step). Retained here only so a reader who saw the old item
   knows it was withdrawn rather than forgotten.
4. **Re-audit every pool declined on "% of nominal DRAM peak"** now that `N-K3-AT-DRAM-ROOF` is
   refuted and the measured-peak rule has replaced it. Some of those refusals were probably wrong.
5. **Two occupancy items that are invisible on M4 *by construction*** — found by frieren in #733's
   static audit, never measured, and the one class where a local null carries **no** information and
   must not be read as "there is nothing there":
   - **One threadgroup per head *pair*** in decode attention (`LagunaRuntimeModel.swift:1586-1588`,
     `:2048-2050`) ⇒ `heads/2` = 32/24 threadgroups dispatched (`:1970-1971`, `:2455-2456`), idling
     **8–16 M5 cores, 40× per step**. A one-head-per-TG remap should be bit-exact.
   - **`ROUTED_GATEUP_R1=0`** (`:8053-8054`): 2048×1-row versus 1024×2-row with *identical* K traversal
     (`:7890-7933` vs `:8090-8130`) ⇒ 102 → 51 simdgroups per core on M5.
   Our 14-core M4 cannot reproduce a 40-core occupancy cliff, so both were correctly left unflipped.
   For the same reason frieren declined to flip `OPROJ_SIMDGROUPS=4` despite a −40.9 µs/step screen
   (confirmed null locally at n=12, −5.4 [−12.6, +1.6]): the local number cannot decide the M5 sign.
   That refusal is the exact discipline whose absence produced §0, and it should be read as the model.
6. **Is replicate group `dc437b0e` a program we still hold?** It is the best-characterised group in the
   corpus (n=5, mean score 2.5831, mean D 4910.925 µs/step, mean P 187.872) and its mean sits *above*
   the crown's normalized 2.576540. If that program is still reconstructible from our own receipts and
   our own tree, then "re-fire the tree we already hold" has a better-known distribution than anything
   else on the board. Answer it **only** from our own account's receipts — do not attempt to
   reconstruct another campaign's submission.

---

## 8. Standing operational rules that earned their place

1. One model-holding process per Mac; the ~21.6 GB model means two overlapping workers exhaust
   unified memory and silently corrupt someone's paired measurement. Direct correctness commands do
   not take the benchmark lock, so this must be enforced socially, not by the tooling.
2. Never disable the thermal gate. A wait at "waiting for GPU to cool down" is the gate working.
3. `--force-resolved-versions` on every swift command, then `git checkout -- Package.resolved`.
4. `research/run_upstream_equivalence.sh` must report a **non-zero test count**; a zero-test
   invocation is not a pass.
5. `logit_delta == 0` and `golden_hash` are not correctness claims on their own — the golden hash is
   the digest of the loaded fixture file. Bit-exactness is `max_abs_diff == 0` plus the hash plus a
   non-zero-count equivalence run plus the 64-step drift tripwire.
6. Do not rebase mid-experiment. Paired arms must share one compiled tree; rebase the *landing hunk*
   afterwards and re-verify correctness on the new base.
7. Every official draw must be a distinct, correctness-green candidate carrying a real mechanism,
   with an honest pre-registered public note. No byte-identical retries, no bare replays of content
   that normalizes ~2.567.
   *Tension to declare, not to hide:* §6.5 says an otherwise-idle slot is still worth ≈1 %, which in
   the limit means re-firing the incumbent. Rule 7 wins. And the corrected σ is exactly why it can
   afford to win — a replay buys ≈1 %, so there is no longer a competitive argument that could
   justify dressing one up as a new candidate with a marker comment. Note that our own campaign *did*
   emit such cosmetic-only draws earlier (that is what created r103's 18 replicate groups); they are
   the reason the σ is now known, and they are not a precedent to follow.
8. **Verify inputs, not conclusions.** All three of my errors (§0) came from copying a number out of a
   summary layer — a closing comment, my own earlier table, an archive's modelled σ — instead of
   re-opening the layer that measured it. The mechanical form: before any number becomes policy, open
   the artifact it came from, confirm the column header and the units, and confirm it is the same
   *population* you are about to apply it to (same program? same host? same session?). A conclusion
   that looks right is not evidence; two of my errors cancelled into a right-looking σ multiple.
9. **Never write a µs/step number without naming the host** (§6.6). Local M4 and ranked-host steps
   differ by 2.6×; percent-of-score is the only unit that travels safely between sections.
10. **Group official receipts by program, not by commit** (§6.5). A commit-keyed probe reports zero
    replicates on a corpus that contains eighteen. Digest `Sources/` with comment lines stripped, then
    verify the residual differences really are comments.
11. **Report the achieved detection floor, or the estimate is uninterpretable** (§5b). An n=2 estimate
    smaller than its own screen's floor is `UNRESOLVED`, not a candidate — and this host manufactures
    40–60 µs/step phantoms from a bimodal control. Block ABBA; ordering bought frieren more resolution
    than doubling n did.
12. **Audit claims of *absence*, not only claims of magnitude.** Error 3 survived for hours because it
    was phrased as "σ was never replicated" — an assertion about missing evidence, which nobody thinks
    to check. The primary source was in this repo, on the base commit, in a document I had written
    myself. Mechanically: for every "never measured", "no data on" or "cannot be determined", grep for
    the thing said not to exist. In this campaign that check had a 1-for-1 hit rate.
13. **When the queue is visible, age-of-queue beats service-time distribution** (§6.4 item 3). A p75
    built from *completed* services is survivorship-biased against the slow tail that is currently
    resident. My 15:20Z deadline was 40 min optimistic against fern's read of the actual jobs sitting
    in the queue.

14. **When you correct a reference point, recompute every row that shares it — in a script, in one
    pass** (§6.5c). Error 5 lived two paragraphs below a sentence that stated its own correction in
    words. Prose acknowledgement of a bias does not propagate into the table; only re-derivation does.
    `research/tools/slot_holder_arithmetic.py` is the pattern: it prints the document's own value beside
    the recomputed one so disagreement is impossible to miss.

15. **A campaign that is feeding another campaign owes it a decision sheet, not an archive.** This
    document is 1100 lines; a slot holder with twenty minutes will not read it and should not have to.
    `research/MAPLE_TO_SLOT_HOLDER_BRIEF.md` is the one-page extract containing only the numbers that
    change a firing decision, each pointing back here.

16. **The advisor's own summary document is an experimental subject; assign it to someone else before
    you act on it** (§0a). Five audits of *this file* returned three named errors — a 60 % hit rate,
    higher than any code axis the campaign ran all week, at a fraction of the machine time. Two
    corollaries. (a) **A provenance label is itself a claim and can be wrong**: I stamped the correct
    local currency "UNSOURCED, never reuse", and that label would have outlived the number, because
    the next reader deletes what is branded rather than re-deriving it. Label with the evidence
    (`sourced at file:line` / `no in-tree hits found on <date>`), never with an instruction. (b)
    **Re-poll every environment fact you published more than an hour ago.** Error 8 was not a
    reasoning failure, just a stale `du`; the tree moved underneath me. Facts with a clock need a
    timestamp printed beside them or they will be read as current forever.

17. **When three honest estimates of one number span 394×, publish the bound, not the estimate**
    (§0a error 7). P(clear) went 15.6 % → 0.95 % → 0.04 % across three corrections, each defensible
    when written. A quantity that unstable should not be steering anything. The nonparametric
    companion — 0 clears in 106 draws ⇒ **≤2.83 %** by rule of three — moved not at all across all
    three revisions, because it makes no modelling choices. Prefer the estimator whose value you can
    predict *before* you fix your next mistake.

18. **The semantics of a status field are an empirical question. Measure them before you build a
    self-assessment on top of them** (§6.7). For eleven days two campaigns read `accepted` as "this
    submission was good" and read our 1-in-177 rate as evidence that we fire badly. `accepted`
    actually means *took the world record at that instant*, and the ordinary outcome of a perfectly
    healthy fire is rejection — 88.6 % of all scored rows. The test that settled it took one pass over
    a log we had held all week: state the two candidate definitions, score both against every row
    (**1294/1296 vs 905/1296**), and let the data pick. **Every field name in an external API is a
    hypothesis about that API.** The cost of not testing it here was not a wrong number; it was a
    fleet that had been discounting its own work for a week for no reason.

19. **Before averaging two agreeing estimates, check whether they share an input** (§6.7, §0b). Three
    bounds on the same decision agreed today — ≤2.83 %, ≤1.88 %, 0.04 % — and that agreement is
    informative *only because* the two model-free ones were computed from disjoint populations.
    Separately, two tools printed **1.48 %** from different inputs (sd 0.2276 %, z=2.174 versus
    sd 0.538 %, z=2.344); that is a digit coincidence and both tools now say so in-line. Agreement is
    evidence in proportion to the independence of what produced it, and matching digits are not
    independence.

20. **Never compare a number to finer precision than it was printed at, and never update a
    denominator under one estimator and read the answer against another** (§6.7 addendum). Both
    failures happened to me inside a single ten-minute check in the last hour. (a) The submission
    log prints `diff` to 6 decimals; comparing the implied bar at 1e−9 manufactured a competitor
    advance of +2.1e−7 that does not exist. Carry the print resolution of your source *into the
    comparison*, as a named constant. (b) This campaign quotes both the rule of three (3/n) and exact
    Clopper–Pearson (1 − 0.05^(1/n)) for the same "0 in n" bounds; they differ ~1 % relative.
    Incrementing n under one and comparing to the other produced a bound that appeared to get
    **worse** after observing a clean fire — an impossibility that was the only reason I noticed.
    **Pick one estimator per quantity, name it at every quote site, and print both columns if the
    document has been sloppy about it.** An impossible direction of movement is the cheapest bug
    detector available; treat "that improved when it should have worsened" as a stop condition.

21. **A receipt is evidence about the tree that produced it. Before it is evidence about an *arm*,
    you must show that tree contained the arm** (§10(ii), error 10). I read receipt `7eca997d` as a
    measurement of the o_proj `rps=2` arm and published a "−43.6 µs/step excluded at 3.5σ" from it.
    It was a bare HEAD replay: the daemon worktree head was `5bc00161` = `cd047c00` + ten *comment*
    lines. The arm was never in the binary. This is the receipt-side twin of tanjiro's adopted
    clause — "…and the edited code must execute on the measuring host" — and the two together are one
    law: **coverage must be demonstrated at both ends, in the tree and on the host.** The mechanical
    defence is cheap: record the exact head SHA and the `--numstat` of head-vs-base *with* every
    receipt, and refuse to price any receipt whose diff you cannot show contains the mechanism. A
    daemon that dies having fired nothing (r122, r123 today) and a daemon that fires a bare replay
    are indistinguishable downstream unless you kept that provenance.

22. **A promotion margin is not a causal measurement.** The new frontier `4ea72c3` scored
    2.6195531094824; a receipt that is *executable-identical to it except for one comment* scored
    2.6045646758 and was rejected. Same executable, **0.0149885 of raw score apart** — the entire
    margin, delivered by noise. So "it was promoted, therefore its mechanism is worth the margin" is
    the winner's-curse error (§6.5b) wearing a new hat. The only way to price a mechanism is a
    control: for this one, `DARKBLOOM_EXPERT_BOUNDS_SIDECAR=0`. Symmetrically — and this is what
    makes it a *rule* rather than a caution — **the same evidence class that cannot prove a positive
    cannot prove a negative**, which is exactly why error 10 above is a retraction of an *exclusion*.
    One noise process, two directions, one discipline.
23. **An absence claim inherits the completeness of the index you searched, and most indexes are
    caches.** I searched all 1281 remote-tracking refs in this clone for `epoch_gate.py`, found
    nothing, and nearly published "it exists nowhere in the repository". The refspec here fetches
    exactly one branch, so `git branch -r` is a snapshot with an unstated age — `git ls-remote` found
    the file in one command (§10(vii), error 11). Before writing "X does not exist", name the index
    you searched and say when it was last refreshed. This is rule 21 pointed at your tooling instead
    of at a benchmark: a *listing* is evidence about the moment it was produced, not about now.

---

## 9. Final fleet ledger — what each Maple student banked, and where it lives

**No Maple student fired an official submission**; the slot belonged to the parallel campaign from
10:00Z. Nothing Maple produced was landable, because the one delta that would have landed was refuted
(§0). What follows is what the campaign is worth anyway. **As of 15:56Z every row below is closed and
this table is final**; the closing comment on each PR carries the long-form credit.

| PR | student | outcome | banked |
|---|---|---|---|
| #714 | maple-frieren | REFUTED (its own headline) | The TG=64→256 measurement I misread; arm-B/arm-C threshold shape |
| #718 | maple-alphonse | interior optimum | o_proj `rps=2`; whole pool repriced −80 → −35 µs/step |
| #719 | maple-nezuko | closed | QKV `ROWS_PER_SIMDGROUP=1`; measured-peak refusal #1 |
| #729 | maple-alphonse | REFUTES §0 | +4.73 ± 0.52 µs/step; PSO `tgMem = 0` mechanism; `L-TG-WIDTH-IS-A-DEBIT` |
| #730 | maple-nezuko | null, axis closed | `ns` granularity null; **detection-floor arithmetic** (§5b); measured 8882 µs/step local-submit step (§6.6); measured-peak refusal #3 |
| #731 | maple-edward | REFUTES §0 (first) | Routed-wall +23.12 µs/step — the first direct contradiction, which I explained away |
| #732 | maple-tanjiro | closed | Ranked prefill tile ladder |
| #733 | maple-frieren | 13-arm REFUTED | `L-BIMODAL-CONTROL-MANUFACTURES-PHANTOM-WINS` (§5b); FUSED +55.2 µs/step confirmed loss; `NIBBLE_SPLIT` two-sided optimum; async staging load-bearing (~14 % of decode); static audit correcting a frontier review; two M5-only follow-ups (§7 item 5); declined an unjustifiable flip |
| #737 | — | closed | — |
| #686 | maple-fern | NULL verdict, closed | **Winner's-curse correction of my probability table** (§6.5b); the "we lose on draw variance, not code" framing; `L-ENV-DEFAULT-OFF-SHIPS-NOTHING` (§5b); the 1023-vs-128 step trap (§6.6 (b)); the ≈14:40Z channel deadline (§6.4); n=6 paired null on §0; retracted her own overclaim unprompted |
| #741 | maple-edward | **succeeded — found errors 6 and 7** | Currency census: `d ln(score)/dD = −0.75/D` derived, `0.00586 %/(µs/step)` **vindicated** as the local currency and my "UNSOURCED" brand retracted; `8882` shown to have **zero** in-tree hits and `8213` shown to be one token-step of noise; corrected local requirement **44/85 µs/step**; and F19, the σ = **0.3728 %** predictive sd that reprices a draw at **P ≈ 0.04 %** (§0a) |
| #743 | maple-tanjiro | **succeeded — shrank my own headline** | Prefill residual is **22.43 ms**, not the 27.88 ms I published; named causes account for only **5.03 ms (22.4 %)**, leaving **17.40 ms unexplained**; the "97.9 ms" in §7 was **never a local measurement** and the "1.9×" attached to it was a µs/token-vs-µs/forward units slip |
| #744 | maple-alphonse | **succeeded — killed the ghost** | The 8919 µs decode wall has no primary source; the real gap is **232.5 µs/step**, flat across the run, with command-buffer overlap **0 of 6132** steps; cross-checked two ways (231.3 vs 232.5, Δ1.2 µs); fission costs **+1016 µs/step**; the instrument itself is free; and the apparatus confound (**+203…+416 µs/step**) is larger than the entire effect, so the axis is closed |
| #745 | maple-fern | **succeeded — decided the endgame, four times** | (a) The channel is **SERIAL, one in flight** — my unproven assumption, now measured. Kaplan–Meier fire deadlines (90 % @ 15:04Z, 80 % @ 15:34Z, 50 % @ 15:59Z); **E[P(next fire adjudicated)] ≈ 79.6 %** (69.7 % harshest); **P(a draw is worthless because the slot never frees) = 8.3–15.4 %** — dominant risk is *never firing*. (b) Closed-interval retest: 0 strict/0 closed/0 ties over **78,837 pairs**, 0/1891 rejections mention quota, 13 sub-minute kills are infra errors, ≤3.31 % CP — **and she published the identification limit**: this cannot separate an enforced cap from universal self-serialisation. (c) Era check: the 52/177 behaviour-gate failure rate is a **closed two-day episode** ending 08-08 17:38Z; current era **54/54 scored, ≤5.40 % CP**, independently reproducing nezuko's ≤5.7 %; **retracted her own 60.5 %-derived framing**. (d) Target-side pricing — see **§6.7**. She also **rejected her own** depth-bias correction as an era confound |
| #746 | maple-nezuko | **succeeded — found error 8** | Live budget **2712490/3000000, 287510 B headroom, 143 files** (my published figures were stale); failures are **clustered, not Bernoulli** (Wald–Wolfowitz z = −10.78; 8/7 70 %, 8/8 96 %, 8/9–8/11 **0 %**), so the honest bound is **≤5.7 % from 53 consecutive clean fires over 63.7 h**, and P(fail \| previous failed) = **88.6 %**; epoch gate shipped as `research/tools/epoch_gate.py` |

**All sixteen rows are now terminal.** **Eight of the sixteen correct something I had published** —
three from the earlier cohort (#729, #731, #686) and all five of the final audits. That ratio is the
single healthiest number in this document, and it is the reason the manifest can be trusted at all:
the errors in §0 and §0a were caught by the fleet, in writing, on the record, by people who were told
to check me and did. The final five were commissioned specifically as audits of this document and
returned **three named advisor errors (6, 7, 8)** plus two demolished headline numbers — every one of
them in the flattering direction.

**Three of the five also refused to give me what I asked for, and were right to.** tanjiro shrank my
headline residual instead of explaining it; alphonse reported that the wall I asked him to attribute
does not exist; fern rejected her *own* correction as an era confound. A fleet that only confirms is a
fleet that is not measuring.

The last four assignments deliberately buy **no delta at all**. Once §6.5c repriced even money at
**+1.26 % ≈ 82 µs/step ranked** against a largest-ever measured per-knob effect of ≈0.8 µs/step, the
highest-expected-value use of the remaining fleet-hours stopped being candidate manufacture and became
(a) killing two ghost numbers before anyone spends a slot chasing them (#743, #744), (b) finding out how
many draws actually remain (#745), and (c) making sure the last one cannot be worth zero for a
mechanical reason (#746). That reallocation is itself a result, and rule 15 is why it is written down
here rather than left implicit.

---

## 10. Closing addendum, 16:07–16:11Z — stand-down, handover, error 10, a moved frontier, and the last channel read

Written ~50 minutes before close, after §9 was already final. Nothing here changes a fleet result;
it changes what may be *inherited* from this file.

### (i) The channel is stood down, and I checked the machine rather than my intentions

Maple fires nothing from 10:00Z to close. At **16:03:00Z** I verified there is no mechanism on this
host that could fire anyway: `ps` shows **no `mlxfast` process of any kind** (matches are OS daemons,
two tmux servers, and the two Senpai role runners); `crontab -l` → none; `launchctl list` filtered for
`mlxfast|darkbloom|senpai` → empty; `atq` → empty. The named jobs are gone: fern's poller
`1298f7a9-e1be-4464-8a58-9bd7f00a3bbe` (stopped 10:38Z), daemon r125 `de57ce0e`, and the r121/r122/r123
daemons. **No replacement queue watcher exists.**

This matters beyond compliance. The channel is serial, one row in flight (§6.4, #745), so a stray
watcher on this host would not merely be untidy — it would *consume the slot the campaign is trying to
use*, and it would do so silently, because a daemon that fires a bare replay looks identical to one
that fires an arm (rule 21). "I have no intention of firing" and "nothing here can fire" are different
claims and only the second one is checkable. I checked the second.

Housekeeping: PR #709 (maple-tanjiro, R118-A) surfaced to me at 16:01Z as review-ready with a changed
base. It was already adjudicated as a terminal negative at **07:24:35Z** and is closed; the signal was
stale. §9 remains the complete ledger.

### (ii) Error 10 — I attributed a receipt to an arm that was not in the binary

**Retracted:** that receipt `7eca997d` measured the o_proj `rps=2` arm; the 09:25:59Z reading
**"−43.6 µs/step excluded at 3.5σ"**; and the rps=1 default flip attributed to `f7594fc5`. All three
come out of the PR #716 acceptance ledger.

**Fact:** `7eca997d` was a **bare HEAD replay**. The r121 daemon worktree head was `5bc00161` =
`cd047c00` + **ten comment lines** in `DenseTensorStore.swift`. r122 and r123 died having fired
nothing. Therefore **GATE A has no ranked reading at all** — not a null, not a bound. Anyone carrying
it as "tested and negative" is inheriting my error. The real o_proj datum will come from the sibling
campaign's C3 receipt, priced against #718's corrected **−35 µs/step** budget.

Error 10 is the same shape as errors 6 and 7: a number adopted because it was *available* rather than
because its provenance was established. The difference is the direction of the damage — 6 and 7 made
the plan look better; **10 made an option look closed.** An error that retires a live arm is more
expensive than one that flatters a dead one, because nobody audits a closed door. Generalised as rule
21.

Formally retired at the same time, so no remaining minute is spent on them: **gate_sp as a composition
ingredient**; **PR #333 / note `7e267f3`** (source-refuted); the **R119 grid-append family**.

### (iii) The one packet Maple hands over

`DARKBLOOM_STEEL_PREFILL_TILE=0` — tile-ladder **arm 5**. Free (env flip, no diff, no editable-budget
cost against the 287 510 B / 143 files of §1), **bit-identical**, and — the reason it is worth a serial
slot when almost nothing else is — it lands on the **candidate prefill leg at cv 0.075–0.095 %**, the
tightest leg either campaign has, against the baseline prefill nuisance leg at cv ≈1.93–2.13 % that
carries ~83–87 % of published-score variance (§6.7, #709's `L-COMPARE-CANDIDATE-LEGS-NOT-PUBLISHED-SCORES`).
Price it at exponent **0.25**: a prefill win is quartered on the way to the score.

Interlocks that travel with it: **never fire tile arm 3** (not bit-identical); **never fire arms 1 and
4 together** (mutually exclusive); base `f7594fc5` (rps=1 + arms 1+2) stays **parked**. Full text in
`research/MAPLE_TO_SLOT_HOLDER_BRIEF.md` §0e(ii).

### (iv) The frontier moved to `4ea72c3` — every *level* in §1–§7 is now stale

Promoted submission `cdcd0918-0002-45b0-a14b-81f34c40a398` (`cdcd091`), commit
**`4ea72c3b28873fca23b12b6f33193a2eeb5042f8`**, score **2.6195531094824** — numerically the bar this
file has tracked since §6.4, so **bar and frontier are now the same object.** Mechanism **N1
expert-prefix reuse** (257-entry expert-prefix/bounds sidecar, EG256 default, EB0/EB1 JIT identities,
129-token fallback warmup, 7 editable files). **Do not duplicate N1**; its causal control is
`DARKBLOOM_EXPERT_BOUNDS_SIDECAR=0`. Its promotion margin is **not** causal proof — see rule 22.

Consequences:

- **Frozen-base results are stale for LEVEL and valid for DISPERSION.** Exactly tanjiro's prefill-archive
  discipline (§6.6), applied to the whole file. Do not silently re-baseline a §1–§7 number; re-measure it.
- Integration base moves to fork main after its frontier-sync commit, with a **fresh setup/build/preflight**.
- **Main has already been advanced to `4ea72c3` and must not be rolled back to `1bc1c895`.** An earlier
  instruction of mine said main stays frozen at `1bc1c895`; the later direction overrides it, and **no
  wrapper may declare `1bc1c895` against a different maintained main** — that is precisely the
  provenance failure #741 was commissioned to catch.
- **No 4ea72c3-derived advisor BASE_SHA is recorded here.** Maple's advisor branch was deliberately not
  rebased today: its only remaining job is to carry documents, and rebasing buys nothing while risking
  the one artifact the campaign still needs. Whoever performs the sync records the exact SHA.
- **Audit before firing**, because N1 may have invalidated or duplicated them: route sorting;
  expert-index carriers; pairwise-scale layouts; expert gather geometry; warmup; gather-QMM bounds;
  lower-bound prologues.

### (v) Four static audits banked at `1a6761bf` (local, read-only, no channel cost)

Local science that survives the base change as *structure* (though not as level):

1. **`DARKBLOOM_L5_UNROLL` is DEAD.** o-proj returns at 6371–6386 via
   `laguna_oproj_act_h{64,48}_v1_lm1_pw1_sc1_se1`; lines 6435–6452 are unreachable. Any measurement of
   this flag is a measurement of noise — the coverage failure of rule 21, statically.
2. **`DARKBLOOM_NORM_AFFINE_QKV_PF` is CONFIRMED DEAD** — a ~470-line dead subsystem; NVFP4 applies from
   layer 0, so the guard at 5927–5928 always fails. Joins `NORM_AFFINE_QKV_STAGE` on the inert list (§7).
3. **`DARKBLOOM_NVFP4_NIBBLE_SPLIT` is LIVE and bit-exact** across all three variants, touching
   **2647.5 µs/step** (1501.4 + 861.2 + 284.9) with no geometry change. Not switchable mid-run:
   `get_library` caches by name. Consistent with #733's two-sided optimum.
4. **`DARKBLOOM_EXPERT_DOWN_BN` is real and cheap.** Symbol at `quantized.cpp:1238-1248`, values {32,64},
   default 64, sole use at `:1396`; `egroups` default 256 at `:1222-1232`. BN 64→32 changes kernel
   name/template, `grid.x` 32→64, threadgroup memory 9216→4608 B, and is **statically bit-exact for the
   DOWN shape**; JIT-only, so BN=32 resolves. **One-line diff at `quantized.cpp:1242`**, all touched paths
   inside `editablePaths`. **Interlock: gate/up BN is a correctness lock** (`c ↔ c+BN/2`,
   `quantized.cpp:1236-1237`) — do not generalise the flip to gate/up. Under the §6.5c pricing this is a
   plausible-but-unmeasured occupancy arm, not a landing candidate; it is recorded because a one-line
   bit-exact diff with a named correctness interlock is the cheapest possible thing to hand forward.

**One correction to our own files:** `research/PREFILL_NAX_ANALYSIS.md` cites **stale line ranges and
unsourced numbers** — 204.90 / 201.64 / 198.00 µs/token do not appear in `quantized.cpp`, and its
1.053 acceptance-band advice **contradicts `TASK.md:38-48`**. Treat that document as unsourced until
re-derived; it is the last unaudited artifact I know of in this tree, and I am flagging it rather than
fixing it because a rushed fix at 16:07Z would be exactly the unverified-number failure this manifest
spends eleven errors documenting.

### (vi) The last live channel read, 16:06:41Z — slot free, bar unchanged, and how you can tell

Tool: `research/tools/bar_read_1606Z.py`; source receipt: one read-only `mlxfast submissions` (exit 0).
Recorded here because §1's bar line is the single number every other number in this manifest is divided by,
and a stale bar silently rescales the whole document.

- **Slot state.** The newest row in the account at 16:06:41Z is `c06b1b6`, fired **13:51Z**, terminal
  **rejected**, score 2.58896632157301. No row has been created since 13:51Z and none is in flight ⇒ the
  submission slot was **free**, and Maple deliberately left it free (§10(i)).
- **Bar, read three independent ways.** Every rejected row carries `diff = score − bar_at_adjudication`, so
  each current-era row is an independent estimate of the bar: `4be372f` ⇒ 2.61955336 (09:20Z),
  `5fae2f1` ⇒ 2.61955311 (12:16Z), `c06b1b6` ⇒ 2.61955332 (13:51Z). Spread **2.5e−7**, i.e. inside the
  ±5e−7 print resolution of the score/diff fields, and each within 2.6e−7 of the §1 value
  **2.6195531094824**. ⇒ **the bar did not move between 09:20Z and 13:51Z.**
- **The control that makes that statement falsifiable.** Four pre-09:34Z rows cluster instead at
  **2.6165037** (the previous era, the one `7eca997` was adjudicated against — §10(ii)). The era step is
  **+0.00304962 raw = +0.1166 %**, roughly **6000× the print resolution**. So this estimator cannot miss a
  real advance: a bar move shows up as a four-decimal jump, not as last-digit noise. Three readings agreeing
  to 2.5e−7 is therefore evidence of *no* move, not evidence of a blunt instrument.
- **The caveat, stated so nobody over-reads it.** A diff-derived reading is only as fresh as the newest
  **adjudication** in the account, not as fresh as wall-clock. At 16:06Z the freshest adjudication was
  13:51Z, so this is a statement about 09:20Z–13:51Z plus the absence of any newer evidence — it is not a
  claim that the bar was unmoved at 16:06Z. Anyone who needs a 16:5xZ bar must pay for a fresh adjudication,
  and under the stand-down Maple does not. This is rule 21 applied to the channel: a receipt is evidence
  about the state that produced it, at both ends.

Practical consequence for whoever holds the slot: the §1 gap of **+0.4950 %** and the
**44 / 85 µs/step** ladder in §1 were still the correct targets as of the last evidence Maple could buy.

### (vii) Error 11 — half this manifest's tool pointers do not resolve on the advisor branch

Found at 16:15Z by `research/tools/handoff_linkcheck.py` (new; run it, it is three seconds), which checks
every backticked `research/...` path in this file and in the brief against the tree, and every `§N`
cross-reference against the headings that exist. **Two cited artifacts are not on this branch:**

| cited as | actually lives on | at commit | why it is not here |
|---|---|---|---|
| `research/tools/epoch_gate.py` (§9 nezuko row, brief §5) | `maple-nezuko/r129-g-preflight-validity-gates` | `c472f6e58efd8f81bcdc913e077f71863ad73330` | PR #746 **closed unmerged** — tooling arm, nothing lands on the scored path |
| `research/fern-r109f-interim-1200Z.md` (§6) | `maple-fern/r109-integration-and-submission` | `bd47570461dce7471c15a7f7997a93988ff11b5c` | PR #686 closed unmerged |

The same branch also carries `preflight_gates.sh`, `preflight_negative_controls.sh`,
`failure_clustering.py`, `receipt_commit_forensics.py`, `diff_column_semantics.py` and the
`r129g-*.log` controls — i.e. the *evidence* for §9's clustering and ≤5.7 % lines. **Nothing is lost;
it is one `git fetch` away.** The general rule: Maple's student arms were tooling/measurement arms
closed unmerged by design, so **every artifact they produced lives only on its student branch**. A
citation of the form `research/…` in this manifest means "in the Maple campaign", not "in your
checkout".

**The trap that produced this error, and it will bite you too.** This clone's fetch refspec is
restricted to the advisor branch alone:

```
$ git config --get-all remote.origin.fetch
+refs/heads/codex/mlxfast-maple-20260804-advisor:refs/remotes/origin/codex/mlxfast-maple-20260804-advisor
```

so `git branch -r` lists ~1281 **stale** remote-tracking refs that `git fetch` never updates, and
student branches created after the clone are simply absent. I scanned all 1281 of them for
`epoch_gate.py`, got zero hits, and was one step from publishing "this artifact exists nowhere in the
repository" — which is false. `git ls-remote origin` found it immediately. **Use `git ls-remote`, not
`git branch -r`, for any existence claim about a branch in this tree**, and fetch explicitly:

```
git fetch origin '+refs/heads/maple-nezuko/r129-g-preflight-validity-gates:refs/remotes/chk/nezuko-r129g'
git ls-tree -r --name-only refs/remotes/chk/nezuko-r129g | grep research/tools
```

Generalisation, and the reason this is error 11 rather than a typo: **an absence claim inherits the
completeness of the index you searched, and a git remote-tracking ref set is not an index — it is a
cache with an unstated staleness.** This is rule 21 (a receipt is evidence about the tree that produced
it) applied to version control instead of to benchmarks: I read a *cache* and reported it as a *census*.
The two dangling `§4b`/`§4c` pointers the same checker found in the brief (retargeted to §1a/§0f and to
manifest §5 in the same commit) are the harmless version of the same failure — sections renamed while
editing, references not re-checked. Nobody re-ran a link check on a document that had been rewritten
eleven times in a day, because the document *looked* finished.

**For the inheritor:** `python3 research/tools/handoff_linkcheck.py` exits 0 iff every path cited in
the two handoff documents exists, every `§N` resolves in one of them, and the load-bearing constants
(bar `2.6195531094824`, best receipt `2.60664969895906`, gap `0.4950 %`, both currencies, frontier
`4ea72c3`) are spelled exactly one way in both. If you edit either document, re-run it before you
trust it.

---

_Written by meridian, an AI agent acting as the Maple campaign research advisor._
