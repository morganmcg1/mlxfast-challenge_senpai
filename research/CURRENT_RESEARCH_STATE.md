# SENPAI Research State

- **2026-08-06 20:40 UTC** — round 22 closed, **round 23 launched**. #143 and
  #138 merged; the base advanced to `9dd2eec3`. Round 22's governing rule
  ("every arm has a free offline falsifier that runs FIRST") paid three times:
  #142, #143 and #137's Step 0 each reached a terminal verdict for **zero
  receipts**. Two whole byte families are now permanently closed by exhaustive
  offline evidence (§8), and the programme's centre of gravity moves from
  **bytes** to **time**: three of the four round-23 arms attack the §4.1
  contradiction directly. #137 pivoted off its refuted hypothesis into the
  round's first genuine green arm and holds the receipt slot.
- **2026-08-06 21:00 UTC** — no receipts yet; all four round-23 arms still
  `status:wip`. Two things changed. (1) A **human operator** amended
  `senpai/program.md` (`bdb77bb0`) to define a **cross-instance submission
  queue**; this closes §R21.7, retires our ~35 min per-receipt price, and
  reprices receipt-free work upward (§6, §10). (2) An audit of the **offline
  transform surface** found that 123 of our 142 editable files have never been
  touched, that the Laguna transform is a byte-identical CoW pass-through, and
  that its output is pinned by **no** golden digest — but also that editing
  `Sources/MLXFastTransform/` flips `source_hash()` and forces a full 21.6 GB
  regeneration on the official host, against 49/1399 submissions already dead
  on timeout. Recorded as §9 item 12 behind a null-layout cost probe.
- **2026-08-06 21:55 UTC** — two corrections that change how we assign work.
  (1) The human operator **replaced** the day-old queue rule with `55ab1b2`,
  "Let submitters manage validation retries": there is now **no queue owner**
  and each dispatcher owns its own retries (§10). (2) Direct source reading
  found that our **M4 prefill per-kernel census measures kernels the M5 never
  executes** — the long-standing "94.2% of prefill is `_nax`" claim is
  *inverted* (§3a). That closes the row-tile axis of the gather GEMM and
  **retracts its banked +1.9–2.6% prize** (§8), and it establishes that the
  steady decode step is **100% host-independent**, while an M4 host can still
  validate a prefill kernel change's implementation, correctness and
  reachability — only its *timing* is not M5 ranking evidence.
- **2026-08-06 21:55 UTC (operator `eae07f01`, "Soften Maple research
  heuristics")** — a direct critique of this advisor's posture: **we have been
  closing families too fast and applying numeric gates too rigidly.** Six
  binding changes, all recorded in §0a: the **+0.61% advisor acceptance bar is
  deleted**; 0.243% is noise context, **not** a submission or promotion
  threshold; **one receipt can justify a clear win**; student-host prefill
  experiments are **endorsed** for implementation/correctness/reachability
  validation; `officialScore` **is** authoritative for ranking (`ns` remains
  the attribution instrument); and a closed family may be reopened by a **new
  mechanism or new evidence**, not merely a repeat. The same commit
  independently confirms our §3a census correction ("94.2% of prefill GPU time
  on the M4 student hosts runs kernels the M5 never executes") and records
  that the public field has been stuck on the prefill axis for **102
  consecutive submissions**.
- **Most recent human research direction:** `3fbbd2d3`, "Soften Maple attention
  precision guidance" (2026-08-06 22:04:20 UTC), the second of two consecutive
  softening commits after `eae07f01` (21:55:23 UTC). Both are recorded in §0a;
  `55ab1b2`'s submitter-owns-retries rule remains in force (§10). **Read the
  pattern, not just the diffs: two operator commits inside ten minutes, both
  loosening prohibitions this advisor had hardened.** Standing campaign rules
  remain: every official submission goes out as
  `mlxfast submit --model "senpai"`; advisor and all four students are
  authorized to dispatch; **launch isolation from the parallel `birch`
  campaign is absolute** — do not inspect, cite, or borrow from it. Isolation
  is a *research* boundary, not a resource one: we share account-scoped
  validation capacity with that instance even though we must not share
  findings.
- **This is a living document.** It was 6,874 lines and had become an archive.
  Everything prior to round 22 now lives in
  [`RESEARCH_STATE_ARCHIVE_through-round-21.md`](RESEARCH_STATE_ARCHIVE_through-round-21.md).
  Read that only when you need the derivation behind a number quoted here.
  Keep *this* file short. Prune it every round.

---

## 0a. Operator `eae07f01` — the heuristics that were softened

`eae07f01` ("Soften Maple research heuristics", mmcguire, 2026-08-06 21:55:23
UTC) edits `senpai/program.md` only (+66 / −55) and is now the remote head of
the advisor branch. Read it as a critique of *this* advisor: we have been
**too quick to close families and too rigid about numeric gates**. Each row
below is binding; the "was" column exists so nobody re-derives the old rule
from an older document.

| # | was | is now |
| --- | --- | --- |
| 1 | thread re-tiling "does **not** transfer; an M4 measurement is not evidence" | "is core-count sensitive; interpret M4 timing with **wave analysis** rather than presenting it as sufficient M5 evidence" |
| 2 | "**Never** run a prefill kernel experiment on a student host" | "**Use** student-host prefill experiments to validate implementation, correctness, reachability, or a hypothesis"; only their *timing* is not `_nax` ranking evidence |
| 3 | S/T decomposition mandatory "for every official run" | decompose "**when identifying where its gain came from**" |
| 4 | every submission needs "a family of at least three" | "**one receipt can justify a clear win or follow-up**"; repeat only for a marginal effect near observed variance |
| 5 | "**Never** rank by `officialScore`" | `officialScore` **is authoritative for leaderboard ranking**; it and the raw `*_speedup` fields are only *noisy for attributing a small mechanism across sessions* |
| 6 | 0.243% noise floor, "the advisor's acceptance bar is 2× that, **0.61%**" | that clause is **deleted**. 0.243% is "noise context, **not a universal submission or promotion threshold**" |
| 7 | a closed decode arm is "worth approximately nothing… do not reopen" | "**starts with low expected value**… revisit one when a proposal **identifies a new mechanism or new evidence**" |
| 8 | precision "not a lever in either direction" | "within the permitted envelope and current frontier, precision is not an *evidenced* lever; a new proposal must first show a compliant byte or math advantage" |
| 9 | attention precision "a **dead lever** … do not treat as headroom in either direction" (`3fbbd2d3`) | "a **low-priority direction** … **revisit** only when a mechanism stays inside the accepted envelope and shows a **net byte or math advantage**" |

`3fbbd2d3` ("Soften Maple attention precision guidance", 2026-08-06 22:04:20
UTC) is a second operator commit in the same direction, also touching
`senpai/program.md` only. The arithmetic is unchanged and still fatal to the
naive move: Q/K/V/O already run **NVFP4 group-16 at 0.5625 B/param** where the
envelope permits **group-32 affine INT8 at 1.125 B/param**, so *adopting* the
envelope adds ~802 MB/token — ~28% of the decode axis. What changed is the
verdict on the *family*: it is now open to a proposal that finds a **net** byte
or math advantage inside the envelope, rather than forbidden outright. The
unchanged prohibition: **do not propose taking any other class below its
current representation.**


**What this changes operationally.**

1. **The +0.61% advisor acceptance bar is retired as a universal gate.** Three
   leads were killed by it alone and are legitimate to revive on their own
   merits: the prefill `PREFILL_ASYNC_LADDER` stride sweep (**+0.34%**, one
   literal, bit-exact, byte-neutral, §9), the shared-expert SwiGLU epilogue
   (**+0.040%**, plus a **+0.028%** zero-byte sub-lead, §7), and the lm-head
   cascade fusion remainder (**+0.060%**). None of these is large; each is
   cheap, and the field has moved less than that per round.
2. **Receipt families are sized to the decision, not to a constant.** A
   designed effect that is large and unmissable needs one or two receipts. An
   effect within ±0.243% on `ns` still needs repetition, because that is what
   the noise says — but that is now a *statement about the effect*, not a
   standing tax on every submission.
3. **`officialScore` for ranking, `ns` for attribution.** Both statements are
   true simultaneously. Quote `officialScore` when the question is "did we
   move on the board"; quote `ns` when the question is "did mechanism X pay".
4. **An M4-only student may be assigned a prefill kernel change** whose
   deliverable is implementation, correctness, bit-exactness, reachability and
   *wave analysis* — with the ranking verdict deferred to an M5 receipt. This
   supersedes the stricter phrasing this document carried at §3a item 4.
5. **Closure is provisional.** §8 remains the record of what has been
   falsified, but a genuinely new mechanism or new evidence reopens any row in
   it. Repeating a closed arm unchanged still does not.

Also recorded by the same commit, and consistent with our own findings: on the
M5 the 512-token forward runs at ~28.8 TFLOP/s and ~272 GB/s — roughly **half
of each M5 roofline** — and the public field has been stuck on that axis for
**102 consecutive submissions**.

---

## 1. Where we stand

**We are rank 1.**

| field | value |
| --- | --- |
| receipt | `97a5090` |
| commit | `3e165fa` |
| officialScore | **2.58882784082067** |
| status | promoted |
| origin | PR #80 (frieren, attention pairwise scale halving) |

Later leaderboard receipts `26dc269`, `c95b4e4`, `00de2d3` and the in-flight
`57d8f082` are **birch**, not ours. Do not read them as competition from a
third party and do not chase them.

Advisor branch HEAD / **round-23 BASE_SHA**:
**`9dd2eec38a11d0e0bc7bcdbc5aec46e3436f284f`**
(`ORGANIZER_FRONTIER_SHA=afcb8320912aa1162f841f282442d7c093e6b2e5`). #143 (zero
scored bytes) and #138 (+5,164 scored bytes) merged into it. Students must not
rebase onto later advisor commits; the advisor supplies `accepted_base_sha` at
merge. **#148 in particular must not rebase** — its doses are instruments, and
the invariant is that every dose shares one base.

### Byte budget at BASE_SHA

```
current=2926911/3000000   headroom=73089   growth=0/262144   files=142
Sources/MLXFastModel/LagunaRuntimeModel.swift = 467167/524288  (headroom 57121 B)
```

Headroom is a real constraint, and **`LagunaRuntimeModel.swift` is the binding
one**: all four round-23 students touch it and it has only 57,121 B of per-file
room. There is **no `.metal` file in `Sources/MLXFastModel/`** — the decode MSL
is embedded as Swift string literals, which is why that one file is 467 KB.
Prefer `quantized.cpp` (listed) for new kernel source. `device.h` is **not**
listed. `senpai/check-editable-budget.sh` requires a full 40-char SHA; it
rejects `HEAD`.

---

## 2. The score model (memorise this; do not re-derive it)

From the promoted receipt's **candidate** arm:

| quantity | value |
| --- | --- |
| prefill wall `S` | **97.89475 ms** |
| decode per-step `T` | **4.143569335937499 ms** |
| `sigma` (prefill share of log-score) | 0.15582 |
| normalized score `ns` | 2.5982163 |

Paired baseline arm: prefill 382.682697265625 µs, decode 13.84496646875 ms
(these are the harness's per-token units; `S` and `T` above are the wall
figures).

**Elasticities:**

| lever | elasticity | practical rate |
| --- | --- | --- |
| prefill `S` | **−0.3669** | **−1 ms of S = +0.362%** |
| decode `T` | **+0.6331** | **−1 µs of T = +0.01464%** |

Ratio 1.726 — decode is worth more *per proportional unit*, prefill is 23.6×
larger *in absolute time*.

Worked prefill points: −3.13 ms = **+1.20%**; −7.82 ms = **+3.10%**;
−15 ms = **+6.4%**.

> An earlier advisor note put the 3.13 ms figure at "+2.08%". **That was
> wrong.** Use the table above.
>
> ⚠️ **A previous version of this line quoted "−31.28 ms = +15.17%". That
> number is withdrawn — see §9a.** 31.28 ms was never measured; it is a
> subtraction residual against a derived roofline floor, and
> `research/maple-tanjiro-pr91-prefill-budget-census.md:845` already adjudicates
> that exact value as **mis-sourced / CLOSED**. The elasticity arithmetic is
> fine; the 31.28 ms input was not.

### The single most important strategic fact

**The entire remaining decode byte inventory, removed at a physically
impossible 100%, is worth +2.85%** — 4.50% of `T`. Decode byte-shaving as a
*family* is near exhaustion. That is why round 22 is a **prefill pivot**.

> ⚠️ **Scope this correctly.** +2.85% is a **byte-removal ceiling at the
> current schedule and layout**. It is *not* a time floor on `T`, and it must
> stop being quoted as a reason decode gets no work — decode still carries
> **75% of the score weight**. Three of our own numbers say schedule and layout
> have more authority over `T` than the byte inventory does: forcing decode
> serialization costs **+5.49%**; the marginal byte price spans **463.5 → 968.4
> GB/s across planes on the same DRAM** (so "% of achievable bandwidth" is
> partly circular, since layout sets the denominator); and a barrier-serialized
> dispatch is priced at **1.980 ± 0.044 µs** on the M5. **`Σ(marginal per-family
> cost)` versus `T` has never been measured on the M5.** #148's decode axis is
> now co-primary precisely to read it (§9.7).

### The byte-price law (replaces two retired constants)

**RETIRED — do not use, do not quote, delete on sight:** `0.0272 %/MB` and
`14.862 %/ms`. Both appeared throughout the archive (old §0.9.36, §R20.2) and
both are wrong because they assume a single global bandwidth.

**In force:**

```
Δscore% = 15.2800 × MB_removed / R_marg[GB/s]
```

Unpriced plane ⇒ use the interval **[463, 969] GB/s** and report both ends.

Measured `R_marg`:

| plane | R_marg (GB/s) | n |
| --- | --- | --- |
| lm-head base | **968.4** (σ 0.269) | 6 |
| routed MoE g32 | 700.3 | 1 |
| attention scale | 524.1 | 1 |
| attention pairwise | 463.5 | 1 |

Corrections adopted: `gate_sp` unique DRAM is **5.5296 MB/step** (nezuko #110),
superseding PR #73's 7.86. PR #72's **+0.834%** anchor is **retired as
circular**.

Only two decode kernels remain unsaturated: `residual_rms_router` at **61.8%**
of achievable bandwidth, and `gate_sp` at 30.4 GB/s = **11.7%** (latency-bound,
not bandwidth-bound). Everything else sits at 94.6–100.2%.

---

## 3. Measurement doctrine (binding on every assignment)

1. **Local M4 `--local-iterate` MDE is ±0.73%.** Established empirically by
   tanjiro in PR #103 §11.2 using byte-identical Sources. No win *or* loss may
   be claimed inside that band.
2. **`officialScore` for ranking, `ns` for attribution** (revised by `eae07f01`,
   §0a row 5). `officialScore` *is* the authoritative leaderboard number; what
   it and the raw `*_speedup` fields are bad at is attributing a small
   mechanism across sessions. Use `ns` for that.
   Pooled cv: `ns` **0.149%**, `officialScore` **0.553%**. The gap is entirely
   the paired baseline's prefill arm, which is **bimodal** (sd 1.933%,
   p50 368.5 µs / p90 382.9 µs). The **candidate** arm's prefill redraw sd is
   only **0.260%**, i.e. **0.065% of `ns`** — so `ns` is a *precise prefill
   instrument*: a genuine +1.2% prefill arm lands at roughly **8σ**.
3. **Receipt channel.** Round budget ≤10 receipts total. **Size the family to
   the decision, not to a constant** (`eae07f01`, §0a row 4): one receipt can
   justify a clear win or a follow-up; an effect inside ±0.243% on `ns` needs
   repetition because that is what the noise says. 0.243% is noise context —
   **not** a submission or promotion threshold, and the old "advisor acceptance
   bar = 0.61%" is deleted. The old "~35 min per receipt,
   single queue-owner" model is **RETIRED** — see §10 for the rule now in force.
   The per-receipt price is currently **un-remeasured**; every dispatch must
   record dispatch time, first "capacity occupied" response, admission time and
   receipt time so we can rebuild it.
4. **M4 vs M5.** Students are on M4 Pro, Apple GPU **generation 16**, which
   **cannot execute `_nax` kernels at all**. The official M5 selects `_nax`.
   Any `_nax` arm is therefore M4-blind and needs the safety rig in §5.
   Every writeup must state which kernel family the local run actually
   selected. **Exception:** hand-written decode MSL is executed identically by
   both hosts, so M4 timing *is* admissible there. See §3a for the strengthened
   form of both halves of this rule.
5. **The greedy-token gate is structurally blind to sub-token logit drift.**
   Measured, not assumed: fern's 1-ULP fault-injection control in #137 made
   **64 of 65** per-step logit digests differ and still reported
   `token_mismatches: 0`. A passing token gate is therefore **not** evidence of
   bit-exactness. Any arm claiming bit-exactness must carry a **bitwise logit
   digest** (`top_k = 100352`, all 64 steps) **and** a deliberately perturbed
   control that is *shown to fire* on that digest. A digest test with no firing
   control is vacuous. This raises the evidentiary bar for every future
   precision-relaxation arm, H1 included.

### 3a. ⚠️ CORRECTION (round 24): our M4 prefill census measures kernels the M5 never runs

This is the most consequential correction of the campaign so far. It invalidates
a claim we have been restating for several rounds, and it simultaneously
*strengthens* the decode half of our transfer doctrine.

**The evidence.** `research/maple-fern-prefill-roofline.md:15-40` records the
capability probe taken on the student host:

```text
arch=applegpu_g16s  gen=16  last=s  nax_gen_required=17  nax_available=false
```

The OS gate passes; the **GPU generation gate fails**. Every `_nax` kernel is
unreachable on an M4 Pro. Fern's own words: this is "a strictly stronger failure
mode than the advisor's 'threadgroup re-tiling does not transfer': it is not the
same kernel at a different occupancy, it is a *different kernel*."

**The inverted claim.** We have repeatedly written "94.2% of prefill is `_nax`".
The truth is the exact opposite: **94.2% of the M4 prefill census is *not*
`_nax`, and every one of those kernels is NAX-divergent** — the M5 runs a
different Metal function for it.

| observed pipeline on M4 | ms/fwd | share | what the M5 runs instead |
|---|---:|---:|---|
| `nvfp4_gather_qmm_rhs_nt` (bm16/bn32/bk32/wm1/wn2) | 266.65 | 48.5% | `nvfp4_gather_qmm_rhs_expert_static_nax_nt_…bm_64_bn_64_bk_64_wm_4_wn_1` |
| `steel_gemm_fused_nt_bfloat16_bm64_bn64_bk16_wm2_wn2` | 183.37 | 33.4% | `steel_gemm_fused_nax_nt_…` (bm128/bn128/bk512 family) |
| `steel_gemm_splitk_nt` + `_accum` | 33.04 | 6.0% | NAX split-K branch (`matmul.cpp:988`) |
| `steel_attention_bfloat16_bq32_bk16_bd128_wm4_wn1` | 28.23 | 5.1% | `steel_attention_nax` at bq64/bk32 |
| `nvfp4_qmm_t` | 6.64 | 1.2% | `nvfp4_qmm_t_nax_static_…` |
| **NAX-divergent subtotal** | **517.92** | **94.2%** | |
| `nvfp4_qmm_t_splitk_fused` | 13.56 | 2.5% | same kernel (split-K precedes the NAX gate) |
| `laguna_*` custom + elementwise + rms + router + moe_tail + sort/scatter + lm_head | ~18.09 | 3.3% | same kernels |

Note in particular that the routed gather GEMM on M4 runs at
**bm16/bn32/bk32/wm1/wn2** — a 16-row tile — while the M5 runs a **64-row**
tile. Any tiling, occupancy or row-padding arithmetic derived from the M4
census is arithmetic about the wrong kernel.

**Four programme consequences.**

1. Correct the drifted restatements wherever they are cited:
   `RESEARCH_IDEAS_2026-08-06_09:00.md:189`,
   `PREFILL_LEDGER_INSTRUMENT.md:10`, `RESEARCH_STATE_ARCHIVE:5823`.
2. **Absolute M4 prefill per-kernel times, and every tiling/occupancy
   conclusion drawn from them, do not transfer to M5.** Only the ~3.3% tail of
   hand-written `laguna_*`/elementwise/rms/router/sort work is common to both
   hosts. This does *not* invalidate M4 *wall-clock* prefill A/B when the arm
   changes host-side dispatch structure rather than kernel internals — but it
   does mean an M4 kernel-internals result is not evidence.
3. **The steady decode step is 100% host-independent.** Every decode dispatch is
   a hand-written `laguna_*` kernel (or `rms`/`gather_front`); none sits behind
   a NAX or `#available` gate. The only capability gate anywhere in `Sources/`
   is `lagunaExpertAlignedGatherEnabled`
   (`LagunaRuntimeModel.swift:235-249`), which decode never reaches. Our
   existing "hand-written decode MSL transfers M4→M5" exception is therefore
   not an exception at all — it is the general rule for decode.
4. **Assignment policy** (softened by `eae07f01`, §0a rows 1–2). An M4-only
   student **may** be assigned a prefill kernel change. What the student host
   delivers is implementation, correctness, bit-exactness, kernel-reachability
   and **wave analysis**; what it cannot deliver is a ranking verdict for the
   M5 `_nax` surface. Every such writeup must state which kernel family the
   local run actually selected, and must defer the ranking claim to one of
   (a) an M5 receipt, or (b) an argument with a ≥100× margin that survives the
   kernel substitution. Decode still carries 75% of the score weight and is
   host-independent, so it remains the cheaper place to *close* a question —
   but that is an expected-value statement, not a prohibition.

### Resubmission variance-harvesting: formally REFUTED

Tested directly this session. Our 2.588828 sits at the **85.7th percentile of
its own null** (+0.632% above the expected 2.5726). Therefore:

- E[one resubmission] = **−0.63%**
- P(beat) = **12.7% per ticket**; ~8 tickets needed for even odds
- the service **dedupes byte-identical archives**
  (`senpai/experiment-runbook.md:195-198`), so every ticket needs a
  byte-distinct tree
- there is **no rate limit** anywhere, and the leaderboard keeps the **best**
  (`TASK.md:44`)

It is a losing lottery against a channel we need for real arms.
**Decision: we do not do it.** Do not re-propose.

---

## 4. The mechanism that now organises our thinking

MLX opens encoders `MTL::DispatchTypeConcurrent` (`device.cpp:548`) and inserts
barriers **only on a real RAW/WAR hazard** (`device.cpp:318-375`). Forcing
serialization costs **+5.49%** [+4.70, +6.28], p = 0.029.

Consequences:

- **A hazard-free kernel is shadowed.** Its cost can be entirely hidden behind
  a concurrent neighbour. This is why the `gate_sp` occupancy arm (#101)
  measured null despite a correct local mechanism.
- **A RAW-dependent cascade cannot be shadowed.** MLX *must* barrier, so the
  stages are genuinely serial, so **fusing them pays**.

So #101, which reads as a null result, is actually **the theory that predicts
fern's lm-head cascade fusion (#137) works.** Negative results that identify a
selection rule are worth more than marginal positives.

**Corollary now owed to the programme:** every banked "µs/step saved" claim
measured *in isolation* rather than *in situ* is suspect for shadow-execution
over-attribution. Re-audit as they come up.

### 4.1 ✅ RESOLVED (round 23, #157 + #158): the residency-ceiling law

The shadow-model contradiction is closed. Two independent PRs agree, so per the
rule below no single receipt was needed and none was spent.

> **THE RESIDENCY-CEILING LAW (#157 D2).** Two independent kernels overlap when
> their **combined** threadgroup count is at or below the machine's concurrent-TG
> residency ceiling (**~480 on a 20-core M4 Pro = 24 TG/core; ~960 on a 40-core
> M5 Max**), and essentially not at all above it.

Measured `concurrent_1cb` GEMM ladder with duration held ≈20 ms: 16 TGs →
`overlap_eff` **1.0112**; 80 → 0.1192; 2048 → 0.0426; 9792 → 0.0128.
Complementary `alu/mem`: 2 TGs → 0.4954 … 9792 → 0.0259. So overlap is a
**spare-capacity** property, not a scheduler property.

Resolution of the three candidate readings:

- **(a) the instrument is blind — CONFIRMED.** `gpu_busy_union` is computed
  **per command buffer** (`research/decode_probe.py:147-192`, merge `:177-186`;
  prefill twin `research/prefill_probe.py:148-165`) from a CB completion
  handler. MLX packs 20–50 ops per CB on one queue, so `union == sum` is
  *guaranteed by construction* and carries zero information. Control:
  `concurrent_1cb` reports union-overlap 0.000000 while wall 13.954 ms against
  an isolated sum of 27.939 ms — **perfect hiding, invisible to the metric.**
  Worse, PR #73's run A used `DARKBLOOM_GPU_PROFILE_SPLIT` (`cbs=406
  dispatches=406`), which makes that evidence self-refuting.
- **(b) no shadowing at real width — SEPARATELY TRUE**, but for a different
  reason than we assumed. #157 D5 measured prefill-512 geometry: MoE per layer
  compacts to **9,798 TGs** (490× the M4 ceiling, 245× the M5 ceiling);
  attention is 384–512 TGs. Nothing in the scored graph runs under the ceiling.
  #158 confirms this independently at **decode** width: capping dispatches per
  CB leaves `gpu_busy_sum` flat at 7.99 ± 0.06 ms while CBs go 45 → 204, so
  hidden decode work is **≤ 0.06 ms/step (< 1%)**.
- **(c) M4 ≠ M5 — not needed.** The 245× margin transfers safely.

**Programme consequences (binding):**

1. **`gpu_busy_union` is RETIRED programme-wide.** Every "nothing overlaps
   because sum == union" claim is withdrawn
   (`nezuko-decode-roofline.md:193-202`, `nezuko-terminal-report.md:221-225`,
   `maple-tanjiro-pr73-decode-kernel-census.md:721`). **`gpu_busy_sum` and the
   per-CB intervals remain valid.** Delete the union column from new reports.
2. **Attack B (graph-level overlap / co-residency) is CLOSED for prefill**, and
   closed for decode by #158's flat-`sum` control. Any future "hide X behind Y"
   proposal must **first** show that X or Y leaves the machine under-occupied
   (< ~480 combined TGs on M4 Pro, < ~960 on M5 Max). Prefill tail-fill upside
   is bounded at O(0.5%) ≈ 0.5 ms ≈ **+0.18%** — below bar.
3. **The decode host gap is PROPORTIONAL, not absolute** (#158 §1.1: slope
   +0.0594 ± 0.0191 on injected work, 3.10σ nominal — treat as ~1.5–2σ, see the
   caveat below). Either way the whole dispute is bounded at **gap/wall =
   3.01%** and the two models differ by only 0.33% of wall. The qualitative
   conclusion is the one that matters: **there is no host-side pool to harvest;
   wall time must be bought by removing GPU work.** The hoped +4.7% host-gap
   pool does not exist.
4. **#158 §2 headline caveat.** Do **not** promote "406 dispatches × 1.9 µs =
   771 µs of dead time" as a programme constant. It is a *level* extrapolated
   from a slope measured at three sites where dispatches were added as whole
   small kernels carrying their own traffic; additivity is untested for the 138
   large byte-bound dispatches that are 58% of busy. The two "independent"
   routes are not independent (Route B is a single unreplicated run in a regime
   the report itself excludes), the retained marginals are mutually
   inconsistent at ~5σ, and the joint 4-knob arm gives 1.57 µs. Honest band:
   **1.6–2.4 µs/dispatch ⇒ 640–990 µs ⇒ 8–12% of busy**, i.e. **9.3% of wall**
   (8.27 ms), not 9.6%. Arithmetic fix: per-CB de-inflation is
   `576/(406−45) = 1.596`, not `576/406 = 1.419`. The strongest defence of the
   instrument, which the report never states, is that the hook is one
   completion handler **per CB** and CBs stay at 45–46 while dispatches go
   406 → 601, so it cannot manufacture a per-dispatch inflation.

#### 4.1a The real, transferable finding from #158: the fusion price table

Read backwards, #158's unfuse sweep is a **retrospective measurement of four
already-shipped fusions worth ≈1.17 ms/step ≈ 14% of decode busy**. That prices
fusion directly, and far better than any flat floor:

| fusion (measured by reversing it) | dispatches removed | µs saved (busy) | **µs per dispatch removed** |
|---|---:|---:|---:|
| `DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER` | 39 | 259.5 | **6.65** |
| `DARKBLOOM_FUSED_ROUTED_SWIGLU_QMV` | 195 | 471.5 | **2.42** |
| `DARKBLOOM_FUSED_SHARED_SWIGLU_QMV` | 195 | 371.5 | **1.91** |
| `DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL` | 39 | 71.5 (wall only +20.5) | **1.83** (wall 0.53) |
| all four jointly | 429 | 673.0 | **1.57** |

Each arm n=1 (±0.36 µs/disp on the 39-dispatch arms, ±0.07 on the 195-dispatch
arms); all arms showed 0 token divergences.

> **RULE: price a prospective fusion by its traffic delta, not by a flat
> per-dispatch floor.** Fusions that eliminate a *materialised intermediate*
> have measured **1.6–6.7 µs per dispatch removed**; a fusion that only removes
> a launch is worth much less, and `rsdr` shows a busy saving of 71.5 µs
> converting to only 20.5 µs of **wall** — always check the wall marginal.

**Cheapest reads that would firm this up** (ranked, from the audit): (1)
replicate `SPLIT=1` at least ×2 — the entire per-kernel census rests on one run;
(2) rerun the unfuse sweep with the hook **off** and compare wall marginals,
which also settles `rsdr`; (3) one **true fusion** arm that removes a dispatch
*without* changing traffic — the only measurement that licenses the level
interpretation.

---

## 5. `_nax` safety rig (mandatory for any `_nax` arm)

Because M4 cannot execute these kernels, a broken `_nax` change measures as a
clean flat local result and then fails or silently falls back on M5. Required:

1. Environment kill-switch for in-binary A/B.
2. Offline MSL compile + pipeline-statistics check **proving a non-empty MMA**
   (`research/nax_msl_compile_check.sh`).
3. A **positive kernel-selection assert** — prove the `_nax` path was taken.

Known silent-failure modes:

- odd `TN>1` ⇒ empty `tile_matmad_nax`
- `SM<16` ⇒ `TM=0`
- the accept gate at `quantized.cpp:1660-1671` requires `bm==64 && wm==4` and
  **silently falls back** otherwise

Keep `mlx-generated/*.cpp` twins consistent with their `.metal`/header source;
that embedded source is what gets compiled at runtime.

---

## 6. Round 23 — in flight

**BASE_SHA `bdb77bb0f54f232ddaa4ebd2ff735441fd2dcb2e`.** All four PRs were
rebased onto it by the controller at 20:41 UTC; the head SHAs are now #137
`922020b9`, #148 `b055f970`, #157 `e30a8320`, #158 `b446fff8`. The commit is a
human-operator edit to `senpai/program.md` alone — **six lines, zero scored
bytes** — so it invalidates no completed local timing and no dose. All four are
still on one shared base, which is what the #148 dose ledger needs. Students
were told: the controller moved you, do not rebase again on your own
initiative, do not re-run anything because of it.

**Governing rule this round: attack the §4.1 contradiction.** Round 22 proved
the free-offline-falsifier rule works; it also proved we have run out of cheap
*byte* arms. Three of four arms below therefore measure **time structure** —
overlap, dead time, dispatch cost — rather than bytes. Every arm still opens
with a falsifier or a pre-registered kill rule.

| PR | student | arm | falsifier / kill rule (runs first) | expected | state |
| --- | --- | --- | --- | --- | --- |
| **#137** | maple-fern | **lm-head S4 row-major re-geometrization** (pivot; the assigned fusion hypothesis was refuted by its own Step 0) | Step 0 injection slope: fusion worth **5.2 µs = +0.060%**, 5× below the 25 µs STOP ⇒ refuted | S4 **77.4 → 13.7 µs**; wall Δ **112.5 µs** paired | **wip r2 — receipt #1 authorized, dispatching** |
| **#148** | maple-frieren | **prefill *and decode* ledger** by calibrated bit-exact work injection, read off the receipt's `officialMetrics` | R1 Step 0 **M4 elision check is now his and is non-optional** — no receipt until a dose shows measurable M4 slowdown | resolves §4.1 and prices the two axes | wip r1 — **slot #2** |
| **#157** | maple-tanjiro | **graph-level co-residency falsifier** (frontier "Attack B" gate), then two-chunk wavefront prefill only on GO | instrument validation first (positive control must show `union < sum`; negative control `union ≈ sum`), then 4 dispatch patterns × 3 sizes. Pre-registered table; **all four outcomes count as success** | GO ⇒ 0…+4% prefill; NO-GO closes a whole structural family | r1 — free, no receipt |
| **#158** | maple-nezuko | **decode dead time** (frontier "Attack A"): is the 322 µs/step host gap absolute or proportional? + re-geometrization of `gate_sp` / `residual_rms_router` | kill rule: if useful-lane fraction >50% and threadgroups are not oversubscribed, **say so and stop** | gap fully closed ≈ **+4.7%** | r1 — slot #4 |

**Receipt channel order this round: fern (#137) → frieren (#148) →
tanjiro (#157, only on GO) → nezuko (#158).**

**The ~35 min per-receipt price is now RETIRED and must be re-measured.** As of
`bdb77bb0` (§10) our channel order is only the **inner** serialisation of a
**shared outer queue**: maple and the other Senpai instance draw on the same
account-scoped validation capacity, and we can neither see nor control the
outer ordering. Treat per-receipt wall-clock as longer than 35 min with
unknown variance until frieren's per-dose queue-wait numbers come back. Two
consequences that change how I rank work:
1. **A family whose value needs several receipts in a row is worth less than
   it was last round.** #148 is the only round-23 arm in that category; I have
   told him to pre-register which single dose would most change my mind and
   dispatch that one first, so a starved family still leaves the informative
   half rather than an arbitrary half.
2. **Receipt-free work is repriced upward.** #157's Step 0 and #158's §1.1/§1.2
   are now the highest-value items on the board precisely because they cannot
   be queue-starved. #158 has been told to plan on the assumption that he may
   get **no receipt at all** this round, and that this is not a demotion.

**Only the queue owner polls, once per ten minutes.** Within maple the queue
owner is the single student actually holding the receipt slot — currently fern.
The other three were explicitly told **not** to poll `mlxfast submissions`,
because two maple agents polling would blow the shared budget with neither of
them able to detect it.

**The question all four now bear on:** `Δwall / Δgpu_busy`. #137 measured
62 µs of `gpu_busy` reduction against 112.5 µs of paired wall reduction —
**1.8×**. If that ratio is a law, decode wall time contains a large
compressible non-busy component and §4.1 resolves toward "the M4 `union`
instrument is blind". If it is 1.0×, fern's excess was perturbation or noise.
Synthesise as soon as any two of the four report.

### Region fence (four students in adjacent code)

| student | owns |
| --- | --- |
| fern | `Sources/MLXFastModel/LagunaLmHeadPrune.swift` + the lm-head cascade call site (~`LagunaRuntimeModel.swift:10920-11053`) |
| tanjiro | prefill: `_nax` kernel geometry / accept gate ~`quantized.cpp:1634-1671`, and prefill chunking in `LagunaRuntimeModel.swift` |
| frieren | the #148 injected-work call sites only |
| nezuko | the single-token decode step: hand-written decode MSL, `gate_sp`, `residual_rms_router` |

Advisor arbitrates any overlap; students must not edit each other's region.
With only 57,121 B of per-file room in `LagunaRuntimeModel.swift`, whoever
merges first consumes headroom for the rest — report byte deltas in every PR.

---

## 7. Held for round 24

- **H1 row-adaptive dual-path gather kernel.** Biggest single arm on the board
  at **+1.4…+2.9%** — but it is **not bit-exact** and it is **M4-blind**. Needs
  a correctness story and the `_nax` safety rig before it can be assigned.
  **Its bar just rose:** §3.5 means a passing greedy-token gate proves nothing
  about logit drift, so H1 needs an argument about *how far* the logits move,
  not a token-equality demonstration.
- **Shared-expert SwiGLU epilogue in prefill.** *Re-scoped after a pricing pass
  refuted the first version of this lead; the earlier "58.5 + 24 = 82.5 MiB by
  flipping two guards" framing is **wrong** and is retained nowhere.* Corrected
  position:
  - The shipped `fuse_swiglu` predicate lives inside the **routed-expert gather
    kernel** (`fp_quantized_nax.h:1797`) and needs `lhs_indices`/`rhs_indices`
    plus `M>=64 && bm==64 && wm==4`. **Neither candidate site can dispatch to
    it.** There is no guard to flip.
  - **Dense layer 0 is closed.** `N=16384` fails the predicate *and* the weights
    are plain bf16 `Linear` (`LagunaRuntimeModel.swift:8438-8446`) — no
    quantized kernel exists to extend. The `x.dim(1)==1` guard at `:8423` is
    **load-bearing correctness**: it protects single-row GEMVs with hard
    `precondition`s that crash at `M=512`.
  - **Shared expert is still worth a slot.** The concatenated NVFP4 `[gate; up]`
    bank already exists (`prepareFusedSharedGateUp()` `:8248-8276`, default on),
    so **no `MLXFastTransform` work is needed**. The prefill guard is at
    **`:8463`** (not `:8503`) and is conservative scoping, not correctness.
  - **But the real work is adding a new epilogue to `fp_qmm_t_nax_static`**,
    which ships `wm=2, wn=2` ⇒ `SN=32` ⇒ `kSwigluRegLocal` false. Threadgroup
    and register budget are **free** (9,224 B of 32,768; the stage is a cast
    alias). Value **78.0 MiB written+read** (2.000 MiB × 39 layers) + 78 fewer
    dispatches. Lifting the guard *alone* saves **zero bytes**, only 39
    dispatches ≈ **+0.028%** — below MDE, stepping stone only.
  - **Prefill-only.** Both sites are already fused in decode, so this cannot
    touch the 75%-weight axis.
  - Top bit-exactness risk: the fused epilogue's bf16 sigmoid under
    `fp contract(off)` vs `MLXNN.silu(gate)*up` under `compile(shapeless:)`.
    Greedy-token gates prove token equality, **not** bit-exactness.
  Full corrected evidence:
  [`h5-per-expert-fused-ffn-closure.md`](h5-per-expert-fused-ffn-closure.md) §6.
- **Incidental occupancy datum from the same investigation:** average rows per
  expert is 16 (route-histogram mean = 16.00) against `SM=16`, so on the average
  expert **only 1 of 4 simdgroups is active** in the gather GEMM. Independent of
  the above; consistent with tanjiro's #138 line of attack.
- **Post-merge cleanup PR**, now genuinely owed — #138 shipped **+5,164 scored
  bytes** and headroom is down to 73,089 B. Three concrete targets, deletion as
  the explicit default:
  1. the **dead BK128 machinery** in `_nax` (#138, default off, unreachable on
     M4) if no `_nax` arm adopts it within ~2 rounds;
  2. tanjiro's **9 near-duplicate `.metal` variants**;
  3. fern's **`DARKBLOOM_LMHEAD_ROWMAJOR_REFINE` dual-arm flag** and the
     superseded S4 kernel, the moment #137 merges.

---

## 8. Closed families — do not repeat, but reopening is allowed

**Closure here is provisional** (`eae07f01`, §0a row 7). A closed family
"starts with low expected value"; it is reopened by a proposal that
**identifies a new mechanism or new evidence**, and is *not* reopened by
re-running the same arm or by hoping for a different draw. Read each row for
*what was falsified*, then ask whether your proposal actually attacks that.

The full evidence table lives in the archive
([`RESEARCH_STATE_ARCHIVE_through-round-21.md`](RESEARCH_STATE_ARCHIVE_through-round-21.md),
"Closed families"). Consult it before proposing anything below. Summary index:

**Closed this session:**

- **The row-tile / row-lane-occupancy axis of the prefill gather GEMM —
  CLOSED, and its banked prize RETRACTED.** I had queued a round-24 assignment
  on "25% row-lane utilisation in the (16,256) grid". Direct source reading
  killed it on three independent grounds:
  - *The premise was arithmetically wrong.* `grid.y` is **one threadgroup per
    expert**, not per (expert, row-chunk) (`quantized.cpp:1960`,
    `fp_quantized_nax.h:1691-1697`); row chunks are an **inner serial loop**
    (`:1713-1716`). An inactive simdgroup does no MMA (`sg_active`,
    `:1717-1719`) though it still runs the K-loop, both barriers and the
    cooperative weight stage. So the real waste is **≈1.29× MMA padding** and
    **≈1.08× weight re-staging**, not 4×.
  - *The axis was already swept and shipped at its optimum.* A measured 6-arm
    `DARKBLOOM_STAGE_BM128` variant sweep lives in editable source
    (`quantized.cpp:1413-1487` doc, `:1491-1510` selector, `:1659-1667` table):
    BM64/WM2/WN2 (control) · BM128/WM4 · BM128/WM2 (regression) · BM128/WM8 ·
    BM64/WM4/WN2 (+15.40%) · **BM64/WM4/WN1 = shipped default**. A separate
    BM ∈ {16,32,64,128} sweep gives chunks/layer 372.6 / 263.2 / **220.5** /
    207.9 with idle TGs pinned at 51.9 for *every* BM; 64→128 buys only −5.7%.
    "The lever is smaller SM, not bigger BM." **SM<16 is impossible**
    (`TM = SM/16` integer-divides to 0 ⇒ zero MMA; `kFragRows=16`), and
    **WM=8 is expressible but useless** (only form is bm128/wm8 ⇒ SM=16,
    identical to shipped).
  - *Row-lane masking is structurally barred.* A 16-row predicate is
    thread-varying while `tile_matmad_nax` is a simdgroup-collective op that
    cannot be lane-masked (`quantized.cpp:1439-1443`; this is why FRAGSKIP was
    rejected).

  **Formal retraction:** the banked **"+1.9–2.6% row-padding prize" is
  withdrawn.** `453,120 = Σ ceil(n_e/16)·16` *is* the floor, not a target.
  Also retired with it: "1 of 4 simdgroups active" (traced to commit `fbc1371`,
  **reasoned, never measured**), and the idea of cashing it in — variant 5
  deliberately moved padding *out of MMA into staging*, so the prize would have
  to be won on the **staging** axis, which is exactly what fern's #40 measured
  null (`Ws` double-buffer dS = **+0.1150 ms**, register prefetch **+0.4626
  ms**, both the wrong sign, inside σ = 0.2536, on 3 same-session M5 receipts
  with `max_abs_diff = 0`).

  Empty threadgroups are priced at **0.355 ms — below the ±0.73% MDE** — and
  `DARKBLOOM_EXPERT_GATHER_GROUPS` self-refutes coarsening (256/128/64/32 give
  empty-TG 20.26/4.77/0.33/0.00% but makespan 40.777/40.838/41.386/42.344 ms),
  so 256 is optimal. Production never operates in the swept occupancy region:
  gate/up is 4,096 TGs (102/core on a 40-core M5), down 8,192 (205/core), and
  the binding occupancy term is **96 simdgroups/core, not threadgroup bytes**
  (#57 + #138; at ≥128 thr/TG, 1 KB / 9,232 / 17,424 / 32,768 B all yield 480
  TGs). **Only two descendants survive**, both listed in §9: routing-aware
  two-régime dispatch (needs a *mechanism proposal, not a knob*), and register
  pressure per simdgroup (never run).
- **The entire checkpoint-compression family — CLOSED by exhaustive offline
  evidence** (nezuko, #143, merged; zero scored bytes, zero receipts). A
  full-byte hash of **all 60,582 slabs / 21,561,408,512 B**:
  - **H4 slab dedup is refuted at 0.0000%.** Routed removable **0 / 59,904**.
    Whole-checkpoint removable 38 slabs = 38 KiB = **0.0002%**. The only
    multi-member class is `router.e_score_correction_bias`, byte-identical
    across 39 layers (and all-zero — a bit-exact micro-win, not queued).
  - **NVFP4 mantissa compression is closed permanently.** All 16 nibble codes
    occur in every routed role ⇒ **0%** fixed-width headroom; pooled nibble
    entropy 3.9417–3.9527 of 4 bits ⇒ **≤ +0.144%** for *any* global memoryless
    code. Best case for whole-checkpoint lossless compression is +9.09%, and
    that is unreachable.
  - **Routed scale-plane recode is closed by a repricing, not by entropy.**
    Scale entropies are 2.4723/2.6002/2.6112 with 42/50/57 distinct codes ⇒
    6-bit, not 4-bit; per-slab maxima 35/38/41 with 705/2,247/1,301 slabs above
    16 codes ⇒ a uniform 4-bit recode is **impossible**. Critically, **PR #72
    already halves the routed scale plane at load** (`scale_row_bytes` 32→16),
    so runtime routed scale traffic is **30.67 MB/step, not 61.34**. Uniform
    6-bit is therefore worth **+0.167%** (below the 0.243% 2σ noise line) and
    mixed 4/6-bit **+0.310%**. Note that this family is *not* closed by a
    numeric bar — the 0.61% bar is deleted (§0a) — it is closed by the entropy
    census showing a uniform 4-bit recode is arithmetically impossible.
  - Routed experts are 39 × 256 × 3 = 29,952 mantissa + 29,952 scale slabs =
    **16.45 GiB = 81.94%** of the checkpoint, so this closure covers the
    overwhelming majority of the bytes.
  - **H6 `residual_rms_router` transpose was pre-mortem refuted from source:**
    the router gemv is *already* float4-coalesced (32 lanes × 8 B = 256
    contiguous B per load). Do not spend a dose or a slot on it.
  - Also delivered and reusable: the **wall-time census** (n = 1,082; last-20
    medians wall 52 s / correctness 39 s / timed 45.5 s ⇒ #148 R1 wall risk LOW,
    but the +70 ms design ceiling *does* leave the envelope, so R2/R3 must not
    be bundled), and the **shadow-execution over-attribution audit** — 10
    HIGH-RISK rows whose "savings" were derived from isolated kernel durations,
    largest `D-FUSE-GATESP` at 213 µs/step. Treat those numbers as upper bounds
    on an unshadowed machine, never as predicted slopes.
- **lm-head cascade dispatch fusion — CLOSED** (fern, #137 Step 0). The
  calibrated injection slope priced the assigned fusion at **5.2 µs = +0.060%**
  on M4, **5× below** the pre-registered 25 µs STOP. Command-buffer batching
  across the four cascade stages is already optimal. The cascade census that
  produced this also produced the round's best arm (see §6): S1 419.8 µs,
  S2 2.3 µs, S3 2.9 µs, **S4 77.4 µs**.
- **`_nax` BK 64→128 — merged as infrastructure, perf arm DEFAULT OFF**
  (tanjiro, #138; `inconclusive`, no receipt spent). Two durable results:
  - **Finding D — a latent correctness-adjacent bug, now fixed.** BK=128
    silently disabled the widened device load: `kSrcBytes` went 16→32 while
    `kWideLoadShapeOk` hard-required `== 16`, so `load_ok` was false and
    `store_ok` true ⇒ **32 scalar byte loads per thread per k-iteration**
    instead of two 16 B vector loads. It compiled, linked and produced correct
    numbers. Fixed by admitting `kSrcBytes == 32` plus two `static_assert`s;
    provably inert at BK=64 (**BK=64 AIR is byte-identical to base**).
  - **⚠️ Doctrine correction — PR #57's occupancy claim was measured on a
    broken probe.** The old probe bound a *dynamic* threadgroup pointer, so
    `setThreadgroupMemoryLength` never bound anything. Repaired: at the real
    geometry (128 threads/TG) 1 KB / 9,232 / 17,424 / 32,768 B **all** give 480
    TGs (24.0/core) ⇒ BK=128 costs zero occupancy on M4; but the 32-threads/TG
    falsification control **does** bind (95.0 → 63.0 TG/core). So "threadgroup
    memory is not the occupancy currency; 96 simdgroups/core is the ceiling" is
    **true at ≥128 threads/TG and FALSE at 32 threads/TG**. Cite it scoped.
  - Why default off: unreachable locally (gen 16 vs `is_nax_available()`,
    `quantized.cpp:1994`); estimated 0.03–0.08% against a ±0.73% MDE; and
    BK=128 needs 34,816 B of threadgroup memory, which **forecloses** the
    BK=64 double-buffered tile (18,432 B). The successor "BK=64 +
    double-buffered weight tile on both shapes" was **formally declined** as a
    re-proposal of the closed `_nax` staging/prefetch/double-buffer/overlap
    axis (#24/#37/#40, arms C1/C2).
  - Reusable: `research/nax_safety_rig.sh` (6 checks, all PASS vs
    `BASE_REV=a36a29c`) + `research/nax_twin_check.py`, plus a **positive**
    kernel-selection assert at `quantized.cpp:1698` verified live as a string
    in `quantized.cpp.o`.
- **Expert-scheduling reordering — CLOSED AS A FAMILY** (frieren, #142, merged).
  Graham's additive bound `makespan ≤ Σp/m + p_max·(1 − 1/m)` with `p_max ≈ 32`
  units against ~353 per core, 9728 tasks over 40–160 slots, caps **any**
  reordering — LPT, SJF, work-stealing, priority queues, static schedules — at
  ~9% of the tail term. The argument is **distribution-free**, not
  trace-specific. Best plausible total 0.458 ms = **+0.166%**, below our ±0.73%
  MDE.
  Two premises of my own assignment were **wrong** and are corrected here:
  (i) there is no worst-case-rows grid — `quantized.cpp:1917-1923` sets
  `grid.y` to a **constant 256** on the expert path and compact otherwise, so
  the recoverable quantity was the 20.26% empty-threadgroup fraction, not a
  15.19× imbalance; (ii) indirect dispatch is **out of surface** —
  `device.h:56` exposes only `dispatch_threadgroups(MTL::Size, MTL::Size)`,
  `get_command_encoder()` is private at `device.h:105`, and `device.h` is not
  among the 97 `editablePaths`. A persistent worker-pool kernel (fixed grid +
  atomic counter) *would* emulate it in-surface, so the rejection is
  cost-benefit rather than impossibility.
  Also self-refuted: `DARKBLOOM_EXPERT_GATHER_GROUPS` coarsening. 256/128/64/32
  groups give 20.26/4.77/0.33/0.00% empty threadgroups, but imbalance grows
  faster than the empty-TG saving (C=80: 40.777/40.838/41.386/42.344 ms).
  **Default 256 is optimal.**
  Merged campaign infrastructure:
  `research/artifacts/route-histogram-prefill512.csv` (9728 rows = 38 sparse
  layers × 256 experts; sum 155648, zero 1971 = 20.26%, median 7, mean 16.00,
  p99 142, max 505, `chunks_bm64` = 8379 ⇒ 1.0802 re-read),
  `-stats.json`, `README-route-histogram.md`,
  `research/lpt_expert_queue_sim.py`,
  `research/pr142-lpt-expert-queue-refutation.md`. Already used twice.
- **H5 per-expert fused FFN — CLOSED, and it was never worth +3.6%.**
  `gate_up → SwiGLU` is **already fused register-locally** and on by default
  (`fp_quantized_nax.h:1797-1798, 1800-1836, 1656-1657`; `quantized.cpp:1581-1584`;
  `jit_kernels.cpp:1205`), decode twins included. The only remaining boundary is
  `SwiGLU → down` (prefill `LagunaRuntimeModel.swift:9829`, decode `:7796-7806`),
  and fusing it needs `64×512×2 + 64×72×2 = 74,752 B` of threadgroup memory =
  **2.28× the 32 KB limit** (current usage 9,224 B); the register alternative is
  512 f32/thread against a ~128 ceiling. Only `BM=16` fits, which forces `WM=1`
  and 32 threads/TG — a **different kernel family**, not a fusion, and it would
  have to re-win the `bm==64 && wm==4` accept gate at `quantized.cpp:1660-1671`.
  Separately the **SLC-absorption bound partly holds**: the governing figure is
  **8 MiB per layer** (the 312 MiB aggregate is never simultaneously resident),
  which is comfortably served by a ~24 MiB M4-Pro or ≥48 MB M5-Max-class SLC, so
  the promised DRAM saving is largely illusory. Decode traffic is only
  ~0.6 MiB/step, so H5 was **only ever a prefill arm**. Full write-up and the
  replacement lead: [`h5-per-expert-fused-ffn-closure.md`](h5-per-expert-fused-ffn-closure.md).
- **lm-head 3+2 re-split — DEAD.** Measured **−0.377%**, CI [−0.644, −0.230].
  It adds **+23.64 MB/step** and needs 44.74% survivors against an observed
  **85.65%**. Nezuko's "#105 GO +0.405%" was the *pricing constant* applied to
  a stale pre-result assumption. **There is no shippable lm-head byte arm.**
- **BN 64→32 (promoted arm C2) is WRONG, not slow.** Default variant 5 is
  BM64/WM4/**WN1** (`quantized.cpp:1468-1478`); `kSwigluRegLocal` requires
  `BN==64` (`fp_quantized_nax.h:1656-1657`); fused gate_up pairs gate column
  `c` with up column `c+32` inside one 64-wide tile, so BN=32 makes in-kernel
  swiglu **impossible** for N=1024/K=2048. Admissible **down-only**.
- **Resubmission variance-harvesting** — see §3.

**Previously closed (top re-proposal risks — a fresh idea generator will
suggest these):**

per-kernel decode residual recovery ("find the big one") · the routed-QMV
byte/bandwidth framing · baseline-draw timing exploitation · the entire `_nax`
staging / prefetch / double-buffer / overlap axis · the in-kernel
`threadgroup_barrier` family · batched reduction and chain-shortening as a
general tactic (three independent arms died at their own analytic ceiling) ·
`sliding_fused_attn_ring_v1` as a byte target (443 GB/s = 170% of the M4 DRAM
ceiling, ~90% of its issue floor) · offline codes/scales interleave (closed
twice) · attention byte de-amplification / head packing · `MLX_MAX_OPS_PER_BUFFER`
(inert ≥40) · `MLX_METAL_FAST_SYNCH` (inert) · decode graph repartitioning ·
in-loop host CPU · decode head latency · first-touch prewarm · *naive* attention
INT8 envelope adoption (backwards — adds ~802 MB/step; the **family** is only
low-priority now, reopenable by a net byte/math advantage inside the envelope,
§0a row 9) · certified lm-head screening ·
NVFP4 scale-plane amplification (A = 1.000) · quantized attention weights in
prefill · prefill overlap C1/C2 · `DARKBLOOM_STAGE_BM128` · **attributing** a
small mechanism from `officialScore` (it remains authoritative for *ranking*,
§0a row 5) · `./probe` on the M5 (impossible — no shell on the ranked
host; the only M5 channel is a submitted candidate plus its receipt `metrics`).

**`MLX_MAX_MB_PER_BUFFER` — CLOSED, and it is our canonical M4→M5 inversion.**
Earlier notes said "no M5 datum exists"; that is **false**. 200 → 50 was
submitted (receipt `3e6fdcb`, commit `1ce8373`, `research/nezuko-mb50-receipt.md`)
and returned **`ns` −1.608%** on the M5 — `S` +2.193%, `T` +1.316% — against
**two independent balanced M4 confirmations of −1.76% and −1.99% wall/step,
monotone in the cap.** Opposite sign. Do not re-propose it, and cite it whenever
a student wants to treat M4 agreement as M5 evidence.

**Still open in the archive but reopened / unresolved:** prefill glue (old C5),
shared-expert overlap (old 5b).

---

## 9a. ⚠️ CORRECTION: what we actually know about prefill time

Two numbers this programme has been quoting as measurements are not
measurements. Both were audited to primary sources on 2026-08-06; correct them
wherever you see them.

**1. The "31.28 ms unattributed prefill pool" does not exist as a measured
quantity.** It is a *subtraction residual* — measured M5 wall minus a **derived
roofline floor**, with no per-kernel attribution behind it.
`research/maple-tanjiro-pr91-prefill-budget-census.md:845` already adjudicates
the exact 31.28 value as **mis-sourced / CLOSED**: it is reproducible only under
an unstated 500 GB/s assumption plus a 20.26% zero-row discount (`:106-112`).
The census's own honest statement is **UNATTRIBUTED = 22.9–37.9 ms, central
27.88 ms at 546.2 GB/s** (`:657-658`), explicitly labelled "an **upper bound on
recoverable time, not recoverable time**" (`:666-667`).
`RESEARCH_STATE_ARCHIVE_through-round-21.md:1172-1181, :6365` had already
refuted the related CLAIM C and withdrawn a 15.4 ms overlap pool.

The only *direct* prefill wall-vs-busy measurement we own says the opposite of a
large pool. `research/pr91-logs/step1-split0.log:15-19` (M4, shipped cap): wall
**545.242 ms**, `gpu_busy_sum` **540.455 ms = 99.1% of wall**, gap ≈ **4.79 ms
(0.9%)**, **81 command buffers, 1222 dispatches**, 24.717 GiB bound. Archive
closure `:6374` says the same at 99.4%. And the M5-measured marginal command
buffer cost is **+27.177 µs/cb** for prefill (2147 µs / 79 cb,
`research/nezuko-mbcap-up-prereg.md:80-82`, ranked receipt `3e6fdcba`) — so the
*entire* 81-CB prefill boundary cost on M5 is **O(2.1 ms)**. CB overhead cannot
be 31 ms. (Caveat from `RESEARCH_STATE_ARCHIVE:3277`: do not quote the
+27.2 µs/cb rate *above* the shipped cap.)

**2. "94.2% of M5 prefill is `_nax`" is an M4 measurement, and its denominator
is the M4 per-kernel census total (~550 ms), not M5 wall.** Origin
`research/maple-fern-prefill-roofline.md:20-35`: `nvfp4_gather_qmm_rhs_nt`
266.65 ms (48.5%) + `steel_gemm_fused_nt` 183.37 (33.4%) + `steel_gemm_splitk_nt`
+ accum 33.04 (6.0%) + `steel_attention` 28.23 (5.1%) + `nvfp4_qmm_t` 6.64 (1.2%)
= 517.92 ms = 94.2%. The correct reading is *"these are the M4 kernels that M5
replaces with `_nax` variants"*. It drifted into a direct M5 claim at
`RESEARCH_IDEAS_2026-08-06_09:00.md:189`, `PREFILL_LEDGER_INSTRUMENT.md:10` and
`RESEARCH_STATE_ARCHIVE_through-round-21.md:5823`. The related "~66 ms M5 busy"
is doubly inferred (`census:998` = 97.95 − 31.28).

**What is actually solid about prefill:**

| fact | value | source |
|---|---|---|
| M5 prefill wall (ranked, promoted arm) | **97.895 ms** | receipt `97a5090` |
| M4 prefill wall / busy / gap | 545.24 / 540.46 / 4.79 ms (**99.1% busy**) | `pr91-logs/step1-split0.log:15-19` |
| command buffers @ shipped 200 MB cap | **81** prefill, 34 decode/step | `nezuko-mbcap-up-prereg.md:31-37`, **reproduces measured M5 counts exactly** (`-receipt.md:34,:186`) |
| dispatches | **1222** prefill, 406 decode/step | same |
| M5 marginal CB cost | prefill **+27.177 µs/cb**, decode **+1.1045 µs/cb** | ranked receipt `3e6fdcba` |
| honest unattributed band | **22.9–37.9 ms, upper bound only** | `pr91-...-census.md:657-667` |

**The instrument blind spot, and the cheapest fix.** The PR91 hook captures only
`GPUStartTime()` / `GPUEndTime()` (`research/pr91-gpuprof-hook.patch:137-141`).
There is **no host-side timestamp and no `addScheduledHandler` anywhere in the
repo**, so "host is slow building the graph" cannot be separated from "GPU is
waiting on the driver". `kernelStartTime()` / `kernelEndTime()` are already
declared in
`Vendor/mlx-swift/Source/Cmlx/metal-cpp/Metal/MTLCommandBuffer.hpp:165,167` and
used **nowhere**. Adding those two plus a host clock read at the `commit()` site
is the smallest instrument upgrade that would answer the causal question, and it
costs zero receipts.

**Parser bug, free to fix.** The hook emits **six** whitespace-separated fields:
`GPUPROF <start_s> <end_s> <nops> <input_bytes> <name>|<name>...`.
`research/prefill_probe.py:48` uses `split(" ", 5)` — correct.
`research/decode_probe.py:160` and `research/nezuko_cb_idle.py:40` use
`split(" ", 4)` — **buggy**: the byte count is prepended to the kernel-name
string. Wall/busy/gap totals are unaffected; per-kernel names are corrupted.
Whoever next touches decode probing must fix both.

**The one measurement that would settle prefill:** a single M5 session with the
PR91 hook attached. It either kills the pool outright or converts it into a real
target. Until then, treat every prefill kernel-level number as M4 evidence about
a code path M4 does not execute the same way.

---

## 9. Potential next research directions

Ordered by expected value, not by ease.

> **Structural criticism to keep in view (round-23 frontier review).** Every one
> of the 20+ families in §8 is either a kernel-micro-optimisation or a
> byte-currency argument. We have never tested a *graph-level execution
> structure* change — how the forward pass is decomposed into dispatches,
> chunks and command buffers — and we have never spent a round on decode
> **dead time** as opposed to decode **bytes**. Directions 1, 3 and 4 below
> exist to break that monoculture. Two of them (1, 3) are falsifiable on M4
> for free, which is rare on this programme.

1. **Decode dead-time programme (frontier "Attack A") — the top pick on the
   75%-weight axis. → ASSIGNED as #158 (nezuko).** §2's "+2.85% even at 100%
   removal" is a *byte-removal
   ceiling at fixed schedule and layout*; it is silent about time that is not
   spent moving bytes (§4.1). Three independent numbers say that time is not
   small: forced serialization costs **+5.49%** [+4.70,+6.28]; a
   barrier-serialized dispatch was priced at **1.980 ± 0.044 µs** on M5 (PR #34
   r2) and the decode step has ~150–250 RAW boundaries, i.e. **300–500 µs =
   7–12% of `T = 4.1436 ms`**; and the M4 profile shows a **0.322 ms host/queue
   gap (3.3%)** plus 45 command buffers at 1.33 µs each (60 µs/step).
   The programme is: enumerate every RAW-dependent chain on the scored decode
   path, rank by exposed serial time, and attack the top ones with the #137
   fusion pattern plus encode-order changes that let hazard-free work be
   enqueued between the two halves of a hazard. This *subsumes and replaces the
   old standalone "fusion selected by RAW-dependence" direction* — that was the
   rule, this is the systematic sweep.
   Expected +2–5%. Decisive advantages: it is **incremental** (each fused chain
   is a separate small commit, so a partial result still ships), it is
   **M4-falsifiable end to end** (decode kernels are hand-written MSL/QMV, not
   `_nax`, so M4 executes the whole path — the one axis where local timing is
   real evidence), and it sits on the 75% weight. Sequencing: gated on #148's
   decode-axis verdict (§4.1 decision rule). If the ledger's residual
   `T − Σ(slopes)` is ≈ 0, decode really is execution-saturated and this
   direction dies cheaply; if it is ≥ 300 µs, this direction owns the next two
   student rounds.
2. **Close the prefill *and decode* ledger with the receipt-channel duplication
   instrument. → IN FLIGHT as #148 (frieren).** Full spec:
   [`PREFILL_LEDGER_INSTRUMENT.md`](PREFILL_LEDGER_INSTRUMENT.md).
   §2 says the decode inventory is worth at most +2.85% even at 100% removal,
   while prefill's unattributed remainder is 31.28 ms ≈ **+15.17%**. We are
   blind to it because 94.2% of M5 prefill is `_nax` and M4 Pro (GPU gen 16)
   cannot execute those kernels at all — so every prefill arm we assign,
   #138 included, is currently a *guess*. The instrument fixes that: duplicate
   one kernel family's pure work bit-exactly (`0.5*(y1+y2)`), submit a
   deliberately-slow candidate, and read the shift off the candidate arm's raw
   `prefill_seconds_per_token`.
   **The channel is verified open, not assumed:** a receipt rejected *on
   ranking* publishes full `officialMetrics` (all 1399 feed submissions), and
   our own PR #34 r2 already ran an openly-documented injection probe through
   static review and every hidden gate. Floor headroom is ~97 ms against a
   ≤70 ms injection budget; the binding risk is the workflow timeout, not the
   floors. A floor/correctness/gate failure, by contrast, publishes **nothing**.
   Three receipts resolve a strategic fork we cannot otherwise resolve: if the
   residual `R = S₀ − Σx̂ᵢ ≈ 0`, the 31.28 ms is *inside* the measured kernels
   (work programme: inner loops, tile geometry); if `R ≈ 20–30 ms` it is
   *between* them (work programme: dispatch structure).
   **Owner: frieren, PR #148** — he wrote "`T_gather ≈ 25 ms` is asserted, never
   measured" in #142, so he fills the hole he found. Nezuko was told on #143 that
   he no longer owns this. **Do not let two students probe concurrently** — one
   shared in-flight slot.
   Refinements added since the spec was written:
   **(a) The decode axis is now co-primary, not a bonus row.**
   `prefill_seconds_per_token` and `decode_seconds_per_token` publish
   independently, so **every** receipt must carry a decode row, not only
   both-phase families such as `routed_gather_gemm`. The decode row probably
   matters more (75% weight): the "decode is exhausted at +2.85%" claim is a
   **bandwidth** argument from per-kernel roofline utilisation (94.6–100.2%),
   and roofline utilisation says nothing about **gap time between kernels**.
   The decode slope gives Σ(kernel time) directly; the residual
   `T − Σ(slopes)` against `T = 4.1436 ms/step` is the number that arbitrates
   §4.1 and gates direction 1. "Host gap is absolute" predicts ≈322 µs (7.8% of
   the M5 step); "host gap is proportional" predicts ≈137 µs — 185 µs apart,
   comfortably resolvable.
   **(a′) Multi-dose linearity is mandatory.** Each family must be injected at
   ≥2 levels and reported as a **slope in absolute µs/step per duplicated copy**,
   plus the linearity residual. A slope that does not scale with dose is not a
   measurement of that kernel; it is a measurement of the schedule, and that
   disagreement is itself a publishable shadow-execution finding. Predict the
   M4 slope ≈ 1.0× the kernel's isolated GPU duration before running; a slope
   materially below that means the duplicate was elided and the probe is invalid.
   Prefer large-isolated-duration families for dose 1, and include at least one
   #48-style *hazard-free* family, because hazard-free vs hazard-bearing is
   exactly what discriminates §4.1 resolution (a) from (b).
   **(b) Wall-time trap.** Injection also multiplies work in the hidden
   correctness suite, anchors, free runs and GPQA checks — far more forward
   passes than the timed window. Project
   `wall ≈ wall_median + (injected fraction)×correctness_seconds + prefill Δ +
   128×decode Δ` and size the multiplier to ≤70% of the timeout. **Escape hatch:**
   gate the injection on `seq_len > 1` (prefill only). A shape gate is legal under
   the serial non-speculative rule — it branches on the supplied input's length,
   not on token values, and is the same legal class as the existing
   prefill-vs-decode kernel selection.
   **Elision is the probe's existence risk:** MLX is lazy and may CSE the
   duplicate away, which looks identical to `T_gather = 0`. The M4 must show a
   measurable slowdown first; CSE is a graph-layer property, so the non-`_nax` M4
   path is a valid test despite M4 being unable to execute `_nax`.
   Fold bit-exactly as `0.5*(y1+y2)` — exact in IEEE-754 including subnormals;
   the **only** hazard is bf16 overflow to inf. Never `y1 + (y2 − y2)`. Never
   double-append KV. **Rejected design:** Hadamard/compressed-sensing
   multiplexing of several families into one receipt — dominated, since the
   signals are already ~60σ.
3. **Graph-level two-chunk wavefront prefill (frontier "Attack B") — the
   monoculture-breaker, and it has a free falsifier. → ASSIGNED as #157
   (tanjiro), gated on the falsifier.** Today prefill runs one
   512-token chunk through layer *i* completely before starting layer *i+1*, so
   the bf16 attention block and the NVFP4 routed GEMMs never co-reside on the
   GPU. Split the prompt into two 256-token chunks and software-pipeline them
   (chunk A at layer *i+1* while chunk B is at layer *i*) so the two very
   different kernel families overlap. **This is legal**: every row still
   corresponds to a token supplied in the same invocation, which the serial
   non-speculative rule explicitly permits for multi-row kernels.
   Arithmetic: the tax is re-reading the ~17.7 GB of routed expert banks at
   roughly 1.7–1.9× (two chunks of 256 rows touch nearly the same expert set as
   one chunk of 512), ≈ **+24 ms** on `S`; the prize is hiding 25–35 ms of bf16
   attention behind GEMM time. Net **−1 to +11 ms**, i.e. **0 to +4%** — a
   fat-tailed bet, not a favourite. What makes it worth a slot anyway is the
   **zero-receipt M4 falsifier**: tape-interleave two independent large GEMMs
   and check whether `gpu_busy_union < gpu_busy_sum`. §4.1 records that in the
   *measured* decode profile these are equal to 6 ns — nothing overlaps — so if
   an explicitly interleaved pair also fails to overlap, Apple's scheduler does
   not co-resident-execute distinct kernel families at all and **the entire
   family dies for one student-day and no receipts**. Run that falsifier first,
   always.
4. **Offline cross-tensor expert-slab re-pack in consumption order (frontier
   "Attack C").** The byte-price law (§2) shows the same DRAM delivering
   968.4 GB/s to the lm-head plane but only 700.3 GB/s to the routed MoE g32
   plane. That 27.7% gap is a *layout* property, not a bandwidth property.
   Re-pack the routed expert banks offline so that bytes are laid out in the
   order the gather kernel consumes them across tensors. If the routed plane
   cleared at the lm-head rate, 553 MB/step × (1/700.3 − 1/968.4) ≈ **219 µs**,
   a **+3.2%** cap; realistically **+1–2%**. Values are untouched, so this is
   bit-exact by construction and is pure `MLXFastTransform` + metadata work.
   **Distinct from two closed families:** the twice-closed offline interleave
   was *within-tensor* (codes and scales of one tensor), and #71 was *in-kernel*
   staging. This is *cross-tensor ordering*.
   > **⚠️ DOWNGRADED — do not assign without a premise test first.** Reading the
   > actual layout after #143: routed `gate` and `up` are **already fused into
   > one per-expert-contiguous bank**, and `down[e]` is consumed by a
   > *different dispatch*. There is therefore very little cross-tensor locality
   > left to exploit *within* a dispatch, and none is exploitable *across*
   > dispatches. The 700.3 vs 968.4 GB/s deficit is real but this is not yet a
   > demonstrated explanation of it. Step 0 for any future assignment is to
   > **explain the deficit** — gather-index scatter, per-expert row counts below
   > a full tile, scale-plane stride, or SLC behaviour — before proposing a
   > re-pack. Also gate on #148 publishing a gather-plane row.
5. **Prefill arms generally.** Same +15.17% logic, but until direction 2 lands
   these are unguided. Tanjiro #138 is the pathfinder; the `_nax` safety rig
   (§5) is enabling infrastructure for the whole direction, not a side quest.
6. **Close the 24.9 MB / 5.7% unallocated census remainder.** An unexplained
   5.7% of the byte inventory is the most likely place a missed arm is hiding.
   Assigned as a secondary to nezuko.
7. **Occupancy / tile geometry on the two unsaturated kernels only.**
   `residual_rms_router` (61.8%) and `gate_sp` (30.4 GB/s, latency-bound).
   Everything else is at 94.6–100.2% and is not worth an arm.
8. **Scheduling rather than arithmetic — narrowed, not closed.** #142 closed
   *reordering* (§8: Graham's bound caps it distribution-free). What survives is
   the rest of the launch layer: encoder construction, command-buffer
   partitioning, barrier placement, and the number of dispatches. That layer is
   generation-independent, so M4 evidence is admissible — its main advantage over
   every prefill arm. On the decode side this is direction 1; on the prefill
   side direction 2's `R` verdict decides its worth: `R ≈ 20–30 ms` makes it the
   round-23 headline, `R ≈ 0` demotes it.
9. **Deletion as an optimization.** Nezuko's 259-line deletion is the only
   scored-byte movement in four rounds, and headroom is down to 78,253 B.
   Reclaiming dead scaffolding is cheap, safe, and buys room for real arms.
   Candidate: tanjiro's 9 near-duplicate `.metal` variants.
10. **Shared-expert prefill SwiGLU epilogue.** Held detail in §7. Prefill-only,
    78.0 MiB/step of written+read traffic across 39 sparse layers plus 78 fewer
    dispatches; the concatenated NVFP4 `[gate;up]` bank already exists so there
    is no `MLXFastTransform` work. The real task is adding a SwiGLU epilogue to
    `fp_qmm_t_nax_static`, and the dominant risk is bf16 bit-exactness of the
    fused sigmoid against `compiledSiluProduct`. Dense layer 0 is **closed** —
    bf16 `Linear`, `N=16384`, and its `x.dim(1)==1` guard is load-bearing
    correctness.
11. **Bit-exactness relaxation, carefully.** H1 (row-adaptive dual-path gather
    kernel, +1.4…+2.9%) is the largest single arm we have and it is blocked on
    correctness, not on mechanism. The only permitted re-quantization is
    group-32 affine INT8 for Q/K/V/O and per-head `g_proj` (see TASK.md's
    accepted envelope) — and adopting that envelope for attention is already
    closed as *backwards*. So H1 needs a different correctness argument,
    specifically a bit-exactness proof rather than an envelope appeal. It is
    also M4-blind, so it needs a receipt slot to evaluate at all.

12. **The offline transform surface — an untouched 87% of the submittable
    board (advisor audit, 2026-08-06).** Verified facts, each checked against
    source rather than inferred:
    - `editablePaths`' 97 entries expand to **142 files**, and **123 of them
      (87%) have never been modified by this team** on any branch. All five
      files of `Sources/MLXFastTransform/` are among them, as is every file
      under `steel/attn` and all of `steel/gemm` except `nax.h`.
    - **On Laguna the transform is a pass-through.** `Transform.swift:219-226`
      APFS CoW-clones each reference shard byte-identically; `:250-269`
      explicitly returns *empty* metadata reports for Laguna, so
      `AffineMetadataCoding.swift` and `TiedHeadMetadataCoding.swift`
      (~32 KB combined) are dead on our path and reachable only from the
      `.gemma4` branch.
    - **The transform output is not pinned by a golden digest.** Every pinned
      SHA-256 in `fixtures/poolside_laguna_xs_2_1_nvfp4_tensor_inventory.json`
      and `Tests/MLXFastTests/LagunaArtifactContractTests.swift:275-300` hashes
      the **input** reference checkpoint. The only trusted output check is
      `Sources/MLXFastTrustedHarness/TransformVerification.swift:78-91`, which
      re-runs *our own submitted* transform and byte-compares — a determinism
      check, not a fixed digest — and it is opt-in
      (`MLXFAST_VERIFY_TRANSFORM`, `benchmark.sh:2150`, workflow default
      false). The only hard output constraint is the 25 GiB cap in
      `Sources/MLXFastCore/Constants.swift:176`.
    - AGENTS.md sanctions this explicitly: "Use transform metadata or layout
      changes that let the runtime skip real work without changing behavior."

    **Two findings that cut the other way, and they are why this is item 12
    and not item 1:**
    - **Editing `Sources/MLXFastTransform/` forces a full 21.6 GB
      regeneration on the official host.** `source_hash()`
      (`benchmark.sh:1579-1586`) hashes `Package.swift`, `Package.resolved`,
      `Sources/MLXFastCore` and `Sources/MLXFastTransform`; a mismatch against
      `SOURCE_HASH_PATH` triggers the regenerate branch at `:2125-2135`. Today
      that branch is nearly free because it is a CoW clone. A real re-layout
      must *read and rewrite* the whole checkpoint. Worse, the paired session
      runs a pristine-transform baseline and our candidate, so the hash flips
      **twice** and the cost may be paid twice. Against a base rate of
      **49/1399 submissions dead on timeout**, that is a first-order risk, not
      a footnote.
    - **`docs/laguna-weight-contract.md:131` says the `switch_mlp` tensors
      "must not be split into per-expert tensors."** Read in context that
      paragraph describes the *input* schema, and the trusted tests
      (`LagunaArtifactContractTests.swift:344,368`) only pin
      `LagunaCheckpointValidation.expectedTensorInventory()` to the public 912
      and require it to reject input mutations. But the prose is ambiguous and
      a static review could read it as governing the output. **Nobody spends a
      receipt on a re-layout until this is resolved.**

    **Therefore: Step 0 is a null-layout legality-and-cost probe, not a
    re-layout.** Change the transform so the output is semantically identical
    (same 912 tensor names, dtypes, shapes and bytes) but the *source hash
    changes* and the write path is a real copy rather than a CoW clone. Measure
    the added session wall-clock on the M5 and confirm the receipt still
    publishes. Kill rule: **if the paired session grows by more than ~40 s, or
    any run times out, the entire offline-layout direction is dead** and we
    have bought that knowledge for one receipt instead of a round.

    **And note what this direction does *not* yet have: a mechanism.** The
    audit found an opportunity surface, not a lever. The most attractive
    candidate target is the **700.3 vs 968.4 GB/s marginal-rate deficit**
    (§9.4) — closing it on 552.1 MB/step of routed traffic would be
    `552.1/700.3 = 788 µs` falling to `552.1/968.4 = 570 µs`, i.e. **218 µs =
    +3.19%**, larger than the entire remaining byte-removal ceiling. But
    within-tensor code/scale interleave is already closed (§8), so the deficit
    must first be *explained* — alignment, gather indirection, wave
    quantisation at M=1, or two disjoint streams per expert are all live and
    they imply completely different fixes.

    **Cheap side-benefit, worth taking whenever someone is in that module:**
    deleting the ~32 KB of Laguna-dead sidecar coders would lift global surface
    headroom from 73,089 B to ~105,000 B (+44%). It does **not** relieve the
    binding constraint, which is the 57,121 B remaining inside
    `LagunaRuntimeModel.swift`, and it requires also removing the `.gemma4`
    branch that calls them — check `Tests/MLXFastTests/TransformTests.swift`
    first.

---

## 10. Open programme issues

- **Submission lifecycle — CURRENT RULE (supersedes `bdb77bb0`).** Commit
  **`55ab1b2`** on `main`, "Let submitters manage validation retries" (mmcguire,
  2026-08-06 21:28:52 UTC), rewrites `senpai/program.md` §5. It is propagated to
  every branch (advisor `ad57f32`, fern `f13d659`, frieren `c5c8c6d`,
  nezuko `1a014f5`). The previous "queue owner / once-per-ten-minutes" model in
  `bdb77bb0` is **retired**; do not apply it. What is in force:
  - **There is no queue owner and no queue manager.** Any authorised advisor,
    student, or human operator holding a committed, preflighted candidate may
    dispatch, and **owns that candidate's submission lifecycle end to end,
    including retries**. Never wait for another agent's permission and never
    hand a candidate off.
  - If validation capacity is occupied: preserve the exact commit and note, keep
    doing useful work, recheck periodically **without a tight polling loop** and
    never sooner than the server's own retry guidance, then retry the
    *identical* `mlxfast submit --model "senpai"`.
  - **Before retrying after a timeout or ambiguous response, first check whether
    the first request already created a submission.**
  - "Capacity occupied" is **not** a rejection and carries **zero** information
    about the candidate. Never fall back to another `--model` value for a
    capacity, timeout, network, or validation condition — the campaign fallback
    is authorised **only** on an explicit rejection of `senpai` as a model
    value, and must then be recorded in the public note.
  - The **~35 min per-receipt price is retired and un-remeasured.** Every
    dispatch must record dispatch time, first "occupied" response, admission
    time and receipt time so the programme can rebuild that constant.
  - Operator broadcast `<!-- senpai-submission-lifecycle-correction:v1 -->` was
    posted to PR #137 and PR #148 at 2026-08-06T21:32Z. That notification item
    is **discharged**; round-24 assignments carry the rule in their body.
- The prior blocker text is retained for provenance: there is still **no typed
  transition to open a new GitHub issue**, so cross-campaign coordination
  continues to require a human operator. `bdb77bb0` is the precedent for how
  that arrives — as a commit to `senpai/program.md` on the advisor branch,
  surfaced to me as a `baseline_advanced` event. **Always diff an unexplained
  `baseline_advanced` SHA before assuming it is machine noise.**
- **`gh` CLI has no token** in the advisor shell, by design. All GitHub
  mutation goes through typed transitions. Field notes on their required fields:
  `create_assignment` needs `revision_id` **and** `expected_base_sha`, and uses
  `head_branch` (not `branch`); `send_assignment_feedback` needs
  `expected_head_sha`, must **omit** `student`, and is **refused unless the PR is
  `status:wip`** — so post review feedback *before* a student flips to
  `status:review`, or carry it into the next assignment body (as was done for
  #142 → #148 §9); `push_branch` needs both `expected_head_sha` and
  `expected_remote_sha`; `request_revision` takes
  `pr_number, assignment_id, expected_head_sha, revision_id, comment` and flips
  the PR back to `status:wip` — which is also how to re-open the feedback
  channel on a PR that has already gone to review; `merge_experiment` takes
  `pr_number, assignment_id, expected_head_sha, accepted_base_sha, merge_method`
  and has **no `reason`/`body` field** (`close_experiment` does take `reason`).
  Multiple distinct `feedback_id`s per revision are accepted.
  `git ls-remote origin 'refs/heads/...'` works without a token and is the
  cheapest way to see whether a student has pushed.
- **Delegation:** prefer **leaf** agents (`explore`, `search`, `bash-runner`)
  for research. `general-purpose` children that spawn their own helpers have
  repeatedly died with "uncollected descendants". Two leaf agents closed H5 this
  session at zero cost. A `frontier` / `general-purpose` child with
  `include_context=false` **does** complete cleanly when it is explicitly told
  not to spawn sub-agents — that is how to buy a fresh structural critique.
- `rg` is **not installed** on the advisor host; use `grep -rn`.
- Merges may return "mergeability unknown"; this is transient and resolves
  after a few minutes. Retry rather than working around it.
- Cascading `baseline_advanced` events are normal when merging several PRs in
  a session; supply `accepted_base_sha` explicitly.
- A **post-merge cleanup PR** is owed as soon as an arm actually ships bytes
  (prune stale experiment flags and dead paths; make the winning behaviour the
  single clear main path).
- Owed to students from #101/#103: the 7.86 → 5.5296 MB/step correction is
  recorded above; the shadow-execution re-audit (§4) is open; the D5
  golden/harness-hash receipt is satisfiable by a no-op because `harnessHash()`
  excludes `research/`; the MDE floor is now explicitly ±0.73%.
