# R107-J′ — Characterising and certifying the paired `--local-submit` decode instrument

**Student** maple-nezuko · **PR** #657 · **assignment** `maple-r107-j-qkv-lane-major-packing-replication`
· **revision** `r107-j-rev1` · **base** `fc66172b73a1ffa3bf2d9a4431267c0b922b7b7f`
· **branch** `maple-nezuko/r107-qkv-packing-replication`

Host **Apple M4 Pro**, 20 GPU cores, 48 GiB, MLX cache capped 6 GiB, 40 °C thermal gate.
Epoch **R107**. Unless a line says otherwise, every quantity below is
**host = M4-Pro · epoch = R107 · MARGINAL** (a local paired difference of two arms of
one binary). No number here is a census number and no number here came from a receipt.

> **Part 1 verdict (§5).** The A/A null **passes**: 12 paired blocks, 24 runs, 0/24
> correctness failures, one golden hash. `mean(D) = −4.935 µs/token`,
> **CI95 [−16.513, +6.642] µs/token = [−0.1099, +0.0442] % of `cs` (α)** — covers zero.
> The paired noise floor is now **measured** at `sd(D) = 18.222 µs/token`
> (chi-square CI95 [12.908, 30.938]), 26.5 % below the 24.8 I had inferred, so the
> instrument is **3.11×** tighter than fern's ABBA on the score channel rather than the
> 2.25× I claimed. All five registered predictions P1–P5 hold. Two honest corrections:
> pairing buys **drift protection, not resolution** (within-block r = −0.249, variance
> factor 0.80×), and I wasted ~10 min of host time on a duplicate campaign launch which I
> cancelled and excluded (§5.0).
>
> **Part 2 (§6, §7).** The blocker — certifying a candidate that is a source transplant
> with no env gate — is solved by the **two-tree staging tool**
> (`research/maple-nezuko-r107j-stage-tree.sh`), which makes a whole built tree an arm
> without touching `certify.sh`. Standing by for frieren #660 and alphonse #644; nothing
> to certify yet.

---

## 0. What this round is, and what it is not

The original R107-J brief (build `_sg8`, flip QKV `num_simdgroups` 2→8, sweep) is **void**.
maple-fern already ran exactly that flip as a preregistered 10-block ABBA
(`research/maple-fern-r106j-integration-tree.md` §5.3.6, branch head `234c5542`):

| channel | estimate | CI95 |
| --- | --- | --- |
| `d(ln score)` | +0.0328 % | [−0.2338, +0.2994] |
| `d(ln decode)` | −0.0686 % | [−0.3921, +0.2550] |

42 usable runs, 10 blocks, 0 correctness failures, one `golden_hash b9509697c08a2cf3`.
L3 is settled and is not revisited here. **No `_sg8` kernel is built in this round.**

What is left is the instrument problem. fern's ABBA resolves the score channel to a
±0.27 % half-width. The candidates now in flight are individually far below that bar —
edward (#629) ≈ 0.43× and alphonse (#644) ≈ 0.45× of the 0.4 % bar *each* — so under
rule 105.5 the only way either becomes bankable is a **summed** 0.25–0.35 % effect
certified with a CI that excludes zero. Nothing in the campaign can do that today. My
`--local-submit` paired instrument is ~2.25× tighter than fern's `--local-iterate` ABBA on
the score channel, which puts it in the right range — but its noise floor has only ever
been **inferred** (24.8 µs/step, back-derived from a within-arm sd of 16.354 on 24 runs),
never **measured**, and it has never been shown to return zero when nothing changed.
*(Measured after the fact: `sd(D) = 18.222 µs/token`, so the real factor is 3.11×, not
2.25×. Corrected in §5.7; the pre-run figure is left standing here as written.)*

So the deliverable is the instrument, in this order:

1. an **A/A null** — is the paired interval centred on zero, and what is the *measured* paired sd;
2. a **power curve** — blocks → resolvable effect, in µs/step, relative decode %, and % of `cs`;
3. a **turnkey script** fern can run without reading my code;
4. **guard rails** written inside that script, not just in a report nobody re-reads.

Then, and only then, Part 2 spends the instrument on somebody's real candidate.

---

## 1. Preregistration of the A/A null

*Written and committed before any timing was collected in this round. Commit of this
section is the timestamp; the campaign is launched afterwards.*

### 1.1 Design

- **Binary**: one release build of the pristine base tree at head `40ade278`
  (parent `fc66172b`). **No source edit at all.** `Sources/MLXFastModel/LagunaRuntimeModel.swift`
  is 384245 B with 0 hits for `PACKRED|_H4|NOREDUCE`, i.e. the advisor's `fc66172b` revert of my
  R106-B scaffolding is intact and this is the untouched base. An A/A null needs no code:
  it needs two labels on the same thing.
- **Arms**: `A` and `Ap` (A′). **Identical gate sets: both empty.** Same binary, same
  process invocation, same 1023-step `--local-submit` workload. The only difference between
  the arms is the label the harness writes into the row sink, and the position in the block.
- **Blocks**: 12 blocks × 2 arms = **24 runs**. Requirement was ≥10 blocks; 12 gives dof = 11
  and two blocks of slack for a failed run without dropping under the floor.
- **Interleaving and position balance**: within-block order rotates by `(block−1) mod 2`, so
  blocks run `A A′ / A′ A / A A′ / A′ A …` — every arm occupies each of the two positions
  exactly 6 times. This is the same layout a real experiment gets, which is the point: the
  null must be measured through the *same* machinery, not a friendlier one.
- **Mode**: `./benchmark.sh --local-submit` only, 1023 decode steps. `--local-iterate` is
  never invoked (guard rail 1 below).
- **Cost**: 198 s/run measured in R106-B (24 runs = 4750 s) ⇒ ≈ 79 min.

### 1.2 Estimand

Per block *b*, the paired difference in the submit-level decode figure

    D_b = 1e6 × ( decode_seconds_per_token[A′,b] − decode_seconds_per_token[A,b] )   µs/token

and the reported statistic is the ordinary paired-t interval on `D`:
`mean(D) ± t(0.975, n−1) · sd(D)/√n`, n = 12, dof = 11, t = 2.201.
Per rule 105.7 **the interval is the deliverable**; the point estimate is not.

### 1.3 Predictions, registered in advance

- **P1 (the null).** `mean(D)` CI95 **covers zero**. This is the pass condition.
- **P2 (the noise floor).** The measured `sd(D)` lands near the inferred 24.8 µs/token.
  I register a tolerance band of **15–35 µs/token**. Landing *below* 15 would mean my
  R106-B power claims were pessimistic; landing *above* 35 would mean they were optimistic
  and every R106-B interval I published is too narrow.
- **P3 (prefill neutrality, rule 105.4).** The paired difference in
  `prefill_seconds_per_token` covers zero. The submit level carries a constant
  +563.6 µs/token of amortised prefill (`K/N`, K ≈ 0.5766 s, N = 1023); in an A/A it must
  cancel exactly, and if it does not, the decode channel is contaminated and the
  instrument does not measure decode.
- **P4 (no ordering confound).** OLS of `D` on the within-block position offset has a slope
  whose CI95 covers zero. The thermal gate fires on essentially every run, so a real
  position effect would alias drift onto every future contrast.
- **P5 (identity of the arms).** Both arms report the same kernel set and the same
  `golden_hash`, and `passed_correctness` is `true` for all 24 runs.

### 1.4 Falsification, stated in advance

**If P1 fails — if the A/A interval excludes zero — the instrument is broken and that is
this round's most important finding**, outranking any candidate certification. I will
report it as such, will not certify anything with it, and Part 2 becomes a repair job
rather than a measurement job. I am registering this before I look, so that a
zero-excluding A/A cannot later be re-described as "drift we can correct for".

A failure of P3 or P4 is a narrower fault: it does not void the instrument but it does void
the *unadjusted* interval, and the position-adjusted intercept becomes the reported estimand.

### 1.5 Stopping rule

Fixed at 12 blocks, declared before launch. There is no look-and-extend: the row sink is
appended as the campaign runs, but the interval is computed once, at n = 12. If a run
fails hard (no `score.json`, or a kernel set that changes mid-session) the script aborts
and I report the interval on the **complete** blocks only, with the incomplete block
dropped whole — never half a block, because half a block is not a pair. The floor is 10
complete blocks; below that I report the failure, not an interval.

---

## 2. Channel translation, fixed in advance

Three channels, because a µs/step number that nobody can convert is not evidence.

| channel | definition |
| --- | --- |
| (a) **M4 µs/token** | the raw measured paired difference on this host |
| (b) **relative decode %** | (a) ÷ reference arm level × 100 |
| (c) **% of `cs`** | (a) × k × 0.015228 |

`k` is the M4→M5 transfer factor and it is carried at **both** priced values per rule 105.12:
**α = 0.4369** (bytes-priced) and **β = 0.5000** (latency-priced). Anchor supplied by the
advisor: **0.4 % of `cs` = 26.27 M5 µs/step = 60.1 M4 µs/step at α = 52.5 M4 µs/step at β.**
Check: 60.1 × 0.4369 × 0.015228 = 0.3999 ✓.

`k` is **not** a ratio of two measured levels — see guard rail 2. It comes from a
fixed-term fit across matched workloads (rule 105.13, credited to my R106-B §C.3:
`k_steady = 8448/4141.5 = 0.4902`, `k_dispatch = 2.3403/1.2382 = 1.890 > 1`).

---

## 3. Guard rails (also written inside the script)

1. **`--local-submit` only; never mixed with `--local-iterate`.** iterate runs 128 decode
   steps, submit runs 1023, and the harness reports
   `decode_seconds_per_token = mean_step_seconds + K/N` with fixed `K ≈ 0.5766 s`. The same
   binary therefore reads 8984.5 µs/token at N = 1023 and ≈ 12926 µs/token at N = 128 — a
   **1.44× scale gap that is pure prefill amortisation, not speed.** Independent
   cross-check from a second operator: fern's `--local-iterate` decode mean
   0.012955773 s/token ÷ my `--local-submit` 0.008984501 s/step = **1.442**. iterate is also
   ≈ 3.7× noisier per run, which is the whole reason this instrument exists. The script
   hardcodes `--local-submit`, rejects any arm spec mentioning iterate, and aborts if
   `score.local-iterate.json` ever appears (submit writes `score.json`;
   iterate writes `score.local-iterate.json`, `benchmark.sh:138-141`).
2. **Never divide a local level by a receipt level and call the ratio `k`.** The official
   receipt amortises the seed prefill over 128 tokens, so `4925.255 / 8984.50 = 0.5482`
   is a prefill-amortisation artefact of two different N — **it is not `k`**. The script
   computes no `k` at all; the analyser takes it as an explicit constant and prints it
   beside every %-of-`cs` figure it derives.
3. **Prefill is charged neutral (rule 105.4).** The +563.6 µs/token amortised prefill
   cancels in a paired difference between arms that do not touch prefill. The script
   records `prefill_seconds_per_token` for every run and the analyser reports its paired
   CI as a contamination diagnostic.
4. **Blocked, interleaved, position-rotated — never two back-to-back batches.** The
   analyser additionally regresses the paired difference on within-block position.

Standing prohibitions honoured: **no receipts**, **`senpai/submit-official.sh` is never
invoked** (the script fails closed on the name), **`DARKBLOOM_EXPERT_DOWN_BN` is never set**
(the script rejects that gate name).

---

## 3A. Preregistration of the positive control (written before it ran)

An A/A null can only ever prove the instrument is **not lying**. It cannot prove the
instrument is **listening**. A null result from a broken-but-quiet instrument and a null
result from a healthy instrument look identical, so §1 alone is not sufficient to certify
anything. The instrument therefore needs a second, opposite test: a *known, already
independently measured, non-zero* effect of roughly the size we care about, which the
instrument must recover.

**The lever.** `DARKBLOOM_QMV_WIDE_CODES` (`LagunaRuntimeModel.swift:325`, default **OFF**,
live use site `:7215`; classification row 209 of `research/artifacts/fern-r105c/gate-classification.csv`
confirms `default-OFF / LIVE / no default-ON gate dominates this site`). Rule 102 closed it
on evidence as a **regression**: a preregistered GPUPROF in-situ campaign measured the
shared-QMV kernel at 7.3911 µs/call OFF → 8.2941 ON, Δ = **+0.9030 µs/call**, t(2) = +25.23,
× 39 dispatches/step = **+35.2 µs/step**, with an independent whole-model wall-clock
cross-check of **+37.2 µs/step** (agreeing within 6 %).

**Why this lever and not another.** +35.2 µs/step is almost exactly the effect size this
round actually has to resolve. Rule 105.10 leaves a residual of 0.2034 % of `cs` for a
second summand to cover, which is **30.6 M4 µs/step at α**. So the positive control is not
merely "some big effect" — it sits within 15 % of the certification threshold itself. If my
paired instrument recovers +35 µs/step with a CI excluding zero, that is a direct,
constructive demonstration that it can certify a 0.2 % summand. If it cannot, the power
curve in §5 is optimistic and I must say so.

**Registered design.** Arms `C:` (reference, no gates) and `W:DARKBLOOM_QMV_WIDE_CODES=1`,
same binary, same blocked-and-interleaved rotation, block count chosen from the *measured*
A/A sd so the predicted half-width is ≈ half the expected effect. Same script, same guard
rails, no source edit.

**Registered predictions.**

* **Q1 — sign and size.** Δ(W − C) is **positive** (a slowdown) and the CI95 **excludes
  zero**. Registered tolerance band for the point estimate: **+20 to +55 µs/step**,
  bracketing the two independent rule-102 estimates (+35.2 GPUPROF, +37.2 wall clock) with
  room for the α/β ambiguity and for the difference between a kernel-summed and an
  end-to-end number.
* **Q2 — correctness.** `passed_correctness` may be **false** and `golden_hash` **will**
  differ from the reference on this arm: rule 102 §2.3 records max |Δlogit| = 5.44531 with
  85.8 % / 91.5 % of elements differing. This is a class-3 (not bit-exact) perturbation. That
  is *expected and is not a harness failure* — I am using it purely as a timing stimulus. It
  is registered here so nobody can later read a differing golden hash as a broken run. It is
  also exactly why this lever can never be shipped, which is why borrowing it as a stimulus
  costs the campaign nothing.
* **Q3 — falsification.** If the CI covers zero, or the point estimate falls outside
  +20…+55, the instrument is **not** demonstrated fit to certify a 0.2 % summand, and §5's
  power curve must be reported as an upper bound on sensitivity rather than a promise.

### 3A.1 A side finding that falls out of the same arithmetic

Rule 102 converted its M4-measured +35.2 µs/step into **−0.5363 % of `cs`**. Inverting the
campaign's own conversion, `Δ%cs = Δ_M4 × k × 0.015228`, the implied transfer factor is

    k_implied = 0.5363 / (35.2 × 0.015228) = 1.0005

i.e. rule 102 priced an M4 number **as if k = 1** — no M4→M5 transfer factor at all. Rule
105.12 states that `k < 1` always, so that price is an **over-statement**. De-biasing the
same measurement gives

| basis | k | `DARKBLOOM_QMV_WIDE_CODES` price |
| --- | --- | --- |
| rule 102 as published | 1.0005 (implicit) | −0.5363 % of `cs` |
| bytes-priced α | 0.4369 | **−0.2343 % of `cs`** |
| latency-priced β | 0.5000 | **−0.2681 % of `cs`** |

This does not change rule 102's verdict — the sign is negative on every basis, so the gate
stays closed, and nothing on the shipped tree moves. What it changes is the *magnitude* of a
number that is now quoted on the closed list, by a factor of ≈ 2.1–2.3. I flag it because
the same `k`-omission, applied to a lever with a *favourable* sign, would manufacture a
phantom win of exactly the size this round is hunting: a lever truly worth 0.23 % would be
reported as 0.54 % and would appear to clear the 0.40 % bar on its own. The positive control
above measures the same lever end-to-end on the paired instrument, so it also supplies an
independent check on this arithmetic.

Caveat, registered in advance: my instrument's resolution at a realistic block count is
≈ 17–26 µs/step, and α and β predict +80.6 vs +70.4 µs/step *only if* one back-converts from
the published −0.5363 %. Those two are 10 µs apart, so this experiment **cannot** discriminate
α from β and I will not claim it does. What it can do is test the far larger question of
whether the end-to-end effect is near +35 µs/step (consistent with rule 102's own primary
measurement) or near +70–80 µs/step (consistent with the published % of `cs` being a true
`cs` fraction). Those two hypotheses are ~40 µs apart and *are* separable.

---

## 3B. Disposition of the preregistered positive control (written 19:40Z, before any ladder row was read)

§3A preregistered a positive control I never ran: arms `C:` (empty gate set) against
`W:DARKBLOOM_QMV_WIDE_CODES=1` (`LagunaRuntimeModel.swift:325`, live site `:7215`), ten blocks
= 20 runs ≈ 75 min, with a registered expectation of **+20…+55 M4 µs/token**. §7 used to imply it
had run; `ebb5f39a` fixed that wording, but the disposition itself was still owed. Here it is,
and it is written now, with the §7.6 ladder 2 runs into 32 and **no ladder value inspected** — I
have run `wc -l` on the sink and nothing else.

**Disposition: withdrawn as a standalone campaign, and its function re-designated to the §7.6
liveness falsifier.**

The control's scientific purpose is **sensitivity**, not accuracy: it proves that two arms which
*should* differ *do* differ, i.e. that the env-gate mechanism actually reaches the GPU and that a
null from this instrument is evidence rather than an artefact of arms that secretly execute the
same thing. §5's A/A proves the complementary half — specificity, that arms which should not
differ do not. Both halves are needed; a harness that cannot see anything passes an A/A perfectly.

Three reasons the ladder discharges that purpose better than `QMV_WIDE_CODES` would:

1. **Its predicted magnitude comes from someone else's measurement, not my guess.** §7.6's
   liveness arm is `N400 − S1 = 360·s` with `s` = frieren's independently measured arm-F slope,
   giving a preregistered **+161.2 µs/token, CI [+144.2, +178.2]** (§9.6). My §3A band
   (+20…+55 µs) was my own estimate of a kernel I had not profiled. A positive control whose
   number was fixed by an independent instrument is strictly stronger evidence than one whose
   number I chose.
2. **It costs zero extra host time.** It is already inside a campaign that is running for another
   reason, on the same binary, in the same session, interleaved in the same blocks — so it also
   controls for drift in a way a separate 75-minute campaign would not.
3. **`QMV_WIDE_CODES` is a *dirty* control.** It changes arithmetic, so the golden token IDs
   differ and `passed` may be false by design. Every other session in this report leans on a
   *single* golden hash as custody evidence (§5.0, §6.7); deliberately introducing a session with
   a second hash costs more in provenance clarity than it buys in sensitivity.

**Conditional re-arming, pre-committed here before the data.** If the ladder's liveness arm
*fails* — `N400 − S1` covering zero on an otherwise clean session — then I cannot distinguish
"the injection gates are not plumbed / this instrument is structurally null" from "added
dispatches are free". Those two have opposite implications and the same signature. In that case
§3A becomes **mandatory**: I will run it (10 blocks, 20 runs, ≈75 min) before making any claim
about `c`, about `s`, or about the merge price, and I will report the ladder as VOID in the
meantime. If liveness fires, §3A is closed as superseded and I will not spend the runs.

**Falsifier of this disposition itself.** If the injected empty kernel never reaches the GPU (for
instance if it were dead-code eliminated, or if `lagunaInjectActive` gated it off in the build I
am running), then the liveness arm cannot serve as a positive control *whatever value it
returns*, and §3A re-arms unconditionally. §7.6.1's scaffolding audit is the evidence against
that reading — but it is a source reading, not a measurement, and I am labelling it as such.

**Cost accounting, so the withdrawal is not a hidden saving.** Not running §3A keeps 75 minutes
of host time free for a candidate tree, against a stated readiness of ≈1.5 h and a 04:15Z
deadline for frieren's tree (§7.2). That is the honest reason the withdrawal is convenient as
well as defensible, and it is why I am pinning the re-arming condition in writing rather than
leaving the decision to how the evening feels at 22:00Z.
---

## 4. Deliverable files

| file | role |
| --- | --- |
| `research/maple-nezuko-r107j-certify.sh` | turnkey campaign runner: `--blocks N LABEL:GATES …` |
| `research/maple-nezuko-r107j-paired-ci.py` | paired CI + power curve + position/prefill diagnostics |
| `research/maple-nezuko-r107j-verify-identity.sh` | post-hoc third-party check that both arms were the same instrument |
| `research/maple-nezuko-r107j-wandb-log.py` | publishes the characterisation to W&B |
| `research/maple-nezuko-r107j-wandb-run.sh` | wrapper keeping `wandb/` out of the checkout |
| `research/maple-nezuko-r107j-certification-instrument.md` | this report |

Invocation, for maple-fern, no knowledge of my code required:

    # A/A null (what §1 registers): 12 blocks, 24 runs, ~79 min
    research/maple-nezuko-r107j-certify.sh --blocks 12 A: Ap:

    # certify one candidate against the shipped default: 8 blocks, 16 runs
    research/maple-nezuko-r107j-certify.sh --blocks 8 C: E:DARKBLOOM_SOME_GATE=1

    # certify two candidates and their SUM on the combined tree: 6 blocks, 24 runs
    research/maple-nezuko-r107j-certify.sh --blocks 6 \
        C: E:DARKBLOOM_E=1 A:DARKBLOOM_A=1 S:DARKBLOOM_E=1,DARKBLOOM_A=1

The first arm listed is the reference; every later arm is differenced against it block by
block. `LABEL:` with an empty gate list means "set no gates at all". Rows land in
`$OUT` (default `/tmp/r107j-certify-<session>.tsv`), deliberately **outside** the worktree so
a campaign never dirties the assignment checkout.

Then analyse and audit — neither step needs anything from me:

    # paired CI, power curve, prefill-neutrality and position diagnostics
    python3 research/maple-nezuko-r107j-paired-ci.py $OUT

    # independent audit that both arms really were the same instrument.
    # Needs KEEP=1 on the campaign (it reads the raw score.json files).
    research/maple-nezuko-r107j-verify-identity.sh <SESSION-ID>

    # publish to W&B (keeps wandb/ out of the checkout)
    research/maple-nezuko-r107j-wandb-run.sh $OUT [extra.tsv ...]

`verify-identity.sh` is the part worth insisting on. It re-derives, from the raw JSON rather
than from my TSV, that every run in the session reported `runtime == "swift-local-submit"`,
the same `checked_steps`, the same `harness_hash`, the same `weights_hash` and the same
`commit`. `runtime` is the load-bearing one: `--local-iterate` stamps a *different* runtime
string, so guard rail 1 stops being a promise in my shell script and becomes a fact
recomputable by a sceptic from files I did not write.

### 4.1 What the analyser prints, and why each line exists

Reading this table is enough to use the output; nobody needs my source.

| line | what it is | how to read it |
| --- | --- | --- |
| `paired sd` | the **measured** sd of the per-block differences | the instrument's noise. Everything else is downstream of it. |
| `CI95 half-width` | `t(0.975, n−1) × sd / √n` | rule 105.7's deliverable. |
| `point estimate` / `CI95 low` / `CI95 high` | each in **three channels**: M4 µs/step, relative decode %, % of `cs` | the `% of cs` column already carries `k`; do not multiply again. |
| `CI95 covers zero` | the verdict | `YES` on an A/A arm is a pass; `YES` on a candidate arm means *not certified*, not *no effect*. |
| `sign-flip test` | exact randomisation p over all `2^n` sign patterns | a cross-check on the t-interval's normality assumption. `agrees with the CI` is what you want to see. A disagreement means one block is carrying the result — go look at the per-block rows printed above. |
| `pairing gain` | within-block correlation `r`, and the factor by which blocking cuts `var(mean diff)` | above ~1.15 the blocking is a **variance** win and the factor is also the factor by which it cuts the required run count. At ~1.0 it is not: the arms do not share their run-to-run noise. That is *not* a reason to drop the blocking — pairing also buys **drift protection**, which is the thing the position OLS then verifies. Read the two lines together. |
| `prefill diag` | paired CI on the prefill difference | guard rail 4 / rule 105.4. Must cover zero, otherwise the decode contrast is contaminated and the number is not a decode number. |
| `position OLS` | slope of `D` on the within-block position offset | catches "arm 2 is always second, and second is always warmer". Must cover zero. |
| power curve | half-widths vs block count, in the same three channels | plan campaigns from this, not from a guess. |
| chi-square band on the sd | CI95 on the sd itself | the power curve is built from an *estimated* sd, and block counts scale as `sd²`. At `dof 11` the band is about `[0.5×, 2.9×]` on the block count. **Plan with the upper sd.** |
| blocks-needed table | smallest `n` to *resolve* an effect, and for 80 % power | "resolve" ≈ 50 % power: it only says an estimate landing *at* the target would clear zero. Use the 80 % column to actually plan. |

### 4.2 Required preflight, run before any timing

**Byte budget.** The brief required me to paste the output of the editable-budget check against
`1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`. Verbatim:

    editable budget OK: current=2681206/3000000 bytes headroom=318794 growth=-302643/262144 files=142 (base=142)

Headroom **318,794 B**; growth is *negative*, so the growth cap is not a constraint from this
base. fern independently reported 319,792 B, a 998 B disagreement. **That discrepancy is now
resolved, and both earlier explanations of it in this document were wrong.** The sequence of
corrections is worth keeping, because each wrong answer was cheap to test and the test is the
reusable part:

1. *First guess — our working trees differ by a research file.* **Wrong.** I re-ran the check
   after adding and committing two research files: headroom did not move by a byte (still
   318,794, growth still −302,643). `research/` is not in `editablePaths`, so it cannot move
   this number.
2. *Second guess — the 998 B sits on the submitted surface of one of our two trees.* **Also
   wrong, in the sense that matters.** I reimplemented the script's accounting independently
   (`git ls-tree -r` per `editablePaths` entry, per-file byte map) and evaluated it at every
   commit in play tonight: `fc66172b` (my base), `705484b9` (Part-2 integration base),
   `d3045bd8`, `adfca1e5`, `d3feadd6`, my current `HEAD`, **and fern's own head `234c5542`**.
   All seven give the identical reading: `entries=97 → 142 tracked files, 2,681,206 B,
   headroom 318,794`. So it is not a difference between her tree and mine.
3. *Resolution — we measured two different bases.* fern's 319,792 traces to
   `research/advisor-r103-strip-verification-and-capacity.md:55` and her own
   `research/r106j/scripts/surface_census.py`, and it is explicitly tagged to base
   **`446fe987`** (the advisor base at T0), where her census records
   `current=2680208 … growth=0`. `2,681,206 − 2,680,208 = 998`. The submitted surface really
   did grow 998 B between `446fe987` and the R107 base. Both readings are correct **for the
   base each was taken against**; neither is a measurement error and neither is a working-tree
   artifact. **318,794 B is the correct headroom for every commit in play today.**

There is a real accounting asymmetry inside `senpai/check-editable-budget.sh` worth knowing
even though it did not cause this: the **base** side enumerates with `git ls-tree -r` (tracked
files only) while the **current** side uses `find "$path" -type f` on the *working tree*, so an
untracked file dropped inside an `editablePaths` directory inflates `current` and `growth`
without touching `base`. That is a trap for anyone who scratch-builds inside
`Sources/MLXFastModel/`. It is not active here: my working tree has **zero** untracked or
ignored files under `Sources/MLXFastModel`, `Sources/MLXFastTransform`, or `Vendor`.

Two numbers from the same census that are more useful than the total headroom:

- At `1bc1c895` the surface was **2,983,849 B → 16,151 B headroom**, which is what makes the
  brief's `growth=-302,643` reading arithmetically consistent rather than surprising. That
  commit was 16 kB from the total cap.
- The binding cap is **per-file, not total**. `Sources/MLXFastModel/LagunaRuntimeModel.swift`
  was **511,418 B** at `1bc1c895` — 12,870 B under the 524,288 B per-file cap — and is
  **384,245 B** now, i.e. **140,043 B** of per-file headroom. At roughly 4 kB of added Swift
  per merged experiment that is about **34 further merges into that one file**, against 77
  merges' worth of *total* headroom. Plan against the per-file number.

My own files add **0 B** to the submitted surface: everything I wrote this round is under
`research/`, and the invariant headroom above is the direct evidence for that, not an
assumption.

**The tree I am characterising is the tree that will be certified.** This is worth stating
because it is the one thing that could have invalidated the whole A/A design after the fact:

    git diff --name-only fc66172b..705484b9   -> research/ only
    git diff --name-only fc66172b..1264d70c   -> research/ only

`fc66172b` is my assignment base, `705484b9` is the Part-2 integration base (tanjiro #648
merged), `1264d70c` is the current advisor head. All three are **byte-identical on the submitted
surface**; they differ only in `research/`. Two consequences, both load-bearing:

1. The A/A null below characterises the *exact* binary that a family-E certificate would be
   differenced against, so its measured `sd(D)` transfers to that certificate without an
   argument about tree drift.
2. Reconciling my branch onto `705484b9` is a **no-op on Sources/Vendor**. The 15:55Z brief asked
   me to record whether I rebased or merged; the honest answer is that the distinction has no
   effect on anything timed here, and I record it as such rather than dressing a no-op up as a
   custody step.

---

## 5. Results

**Headline: the instrument passes its own A/A null. All five registered predictions hold.
The paired noise floor is now MEASURED at `sd(D) = 18.222 µs/token`, not inferred.**

### 5.0 Provenance and custody

| field | value |
|---|---|
| session | `20260810T153224Z` |
| tree at launch | `ff8b09188f1f` (HEAD when `certify.sh` recorded `HEAD_SHA`, pre-loop, `certify.sh:165`) |
| row sink | `/tmp/r107j-aa-null.tsv`; session isolated to `/tmp/r107j-aa-null-s1.tsv`, committed verbatim as `research/maple-nezuko-r107j-aa-null-rows.tsv` |
| W&B | run `lg646mqf` — https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/lg646mqf (24 run rows, 12 paired diffs, power curve, blocks-needed table as artefacts) |
| instrument | `./benchmark.sh --local-submit` (1023 decode steps), blocked + order-rotated |
| rows | 24 = 12 blocks × 2 arms, both arms **empty gate sets on one pristine binary** |
| host | Apple M4 Pro, 20 GPU cores, 48 GiB, epoch R107 |

**Operational error, disclosed.** At 16:56Z I launched a *second* A/A campaign
(`20260810T165624Z`, head `b4442be52c9c`) without first checking that the registered
12-block campaign had already completed at ~16:52Z. It was a duplicate replicate, not a
continuation. I caught it two runs in and cancelled it (`cancel_job`, elapsed 579.8 s,
exit −15, ~17:06Z), then confirmed no orphaned model-holding process was left behind.
**The two session-2 rows are discarded and are not pooled into anything below**: pooling
them would break the preregistered stopping rule in §1.5, which fixes n = 12 and forbids
look-and-extend. For the record, session-2 block 1 gave `D = +17.9 µs/token`, which is a
one-block anecdote inside the measured `sd` and is reported here only so that the
discarded data is on the table rather than quietly dropped. The cost was ~10 min of host
time and no scientific harm; the lesson is to read the row sink before launching.

### 5.1 Per-arm description (CENSUS levels)

| arm | n | mean µs/token | sd | cv % | gates | kernels | passed | golden |
|---|---|---|---|---|---|---|---|---|
| `A` (reference) | 12 | 8978.627 | 11.954 | 0.133 | none | none | true | `f49e4c2cbc0d3ceee9…` |
| `A′` | 12 | 8973.692 | 11.095 | 0.124 | none | none | true | `f49e4c2cbc0d3ceee9…` |

Correctness failures: **0 / 24**. One golden hash across all 24 runs.

### 5.2 The twelve paired blocks

| block | `A′` | `A` | `D = A′ − A` | dpos | dprefill |
|---|---|---|---|---|---|
| 1 | 8961.086 | 8978.021 | −16.936 | +1 | −13.699 |
| 2 | 8964.238 | 8967.300 | −3.062 | −1 | −0.824 |
| 3 | 8968.212 | 8970.264 | −2.052 | +1 | −4.298 |
| 4 | 8990.645 | 8970.715 | **+19.930** | −1 | −13.496 |
| 5 | 8972.755 | 8965.076 | +7.679 | +1 | −11.319 |
| 6 | 8964.892 | 9001.588 | **−36.696** | −1 | +8.736 |
| 7 | 8978.662 | 8995.401 | −16.740 | +1 | −7.585 |
| 8 | 8973.795 | 8970.561 | +3.234 | −1 | +26.928 |
| 9 | 8965.047 | 8992.541 | −27.494 | +1 | −1.162 |
| 10 | 8974.005 | 8977.097 | −3.092 | −1 | +2.742 |
| 11 | 8998.379 | 8972.249 | **+26.130** | +1 | −1.788 |
| 12 | 8972.593 | 8982.716 | −10.123 | −1 | −28.355 |

Position offsets sum to zero by construction (six `+1`, six `−1`), so the unadjusted mean
is already position-balanced.

### 5.3 The interval — which is the deliverable

```
n_blocks=12  dof=11  t(0.975,11)=2.201
paired sd        =    18.222 us/token   (MEASURED, not inferred)
standard error   =     5.260 us/token
CI95 half-width  =    11.577 us/token
t statistic      =    -0.938              (two-sided p = 0.3684)
reference level  =  8978.627 us/token
point estimate      -4.935 us/token    -0.0550 % decode    -0.0328 % cs(a)    -0.0376 % cs(b)
CI95 low           -16.513 us/token    -0.1839 % decode    -0.1099 % cs(a)    -0.1257 % cs(b)
CI95 high           +6.642 us/token    +0.0740 % decode    +0.0442 % cs(a)    +0.0506 % cs(b)
CI95 covers zero : YES
sign-flip test   : p=0.3677 (exact, 4096 patterns) -> agrees with the CI
```

Per rule 105.22(c) the reported result is the **interval**, not the point estimate: the
instrument's answer to "nothing changed" is
**−0.0328 % of `cs`, CI95 [−0.1099, +0.0442] % (α)** — equivalently
**[−0.1257, +0.0506] % (β)**. It is centred on zero to well inside its own resolution and
the exact sign-flip test (distribution-free, so it does not rely on the dof-11 normality
assumption behind the t-interval) agrees to three decimal places on p.

### 5.4 Registered predictions, scored

| # | prediction | outcome | verdict |
|---|---|---|---|
| P1 | `mean(D)` CI95 covers zero | [−16.513, +6.642] µs/token | **PASS** |
| P2 | `sd(D)` in the 15–35 µs/token band | 18.222 | **PASS**, but see below |
| P3 | prefill difference covers zero | d = −3.677, CI95 [−12.308, +4.954] | **PASS** |
| P4 | position OLS slope covers zero | +0.033 µs/position, CI95 [−12.259, +12.324] | **PASS** |
| P5 | same kernel set, same golden, all passed | none/none, one hash, 24/24 | **PASS** |

P1 is the pass condition and it holds, so §1.4's falsification branch does not fire: the
instrument is not broken and Part 2 stays a measurement job rather than a repair job.

**P2 passed but the prediction was miscalibrated in an informative direction.** The
pre-run inference was 24.8 µs/token; the measurement is 18.222, i.e. **0.735× — 26.5 %
below** what I had back-derived from a within-arm sd on 24 runs. So every R106-B power
claim built on 24.8 was *pessimistic*, not optimistic. That is the benign direction, but
it is still a miss, and it is exactly why P2 was registered with a band rather than as a
point.

P4 deserves its own note: the position slope's CI half-width (±12.3 µs/position) is about
as wide as the whole effect interval, so P4 establishes "no *detectable* ordering
confound at this resolution", not "no ordering confound". The position-adjusted intercept
at `dpos = 0` is −4.935 µs/token, identical to the unadjusted mean to three decimals,
which is the balanced-design guarantee doing its job rather than independent evidence.

### 5.5 Pairing does not buy resolution — it buys drift protection

The within-block correlation between arms is **r = −0.249**, so blocking changes the
variance of the mean difference by **0.80×** relative to an unpaired comparison. That is
not a variance win; it is a rounding error in the wrong direction of what I expected.

I registered pairing on the assumption that the two arms of a block share their
run-to-run noise, so differencing would cancel it. On this host, at this resolution, they
**do not**: the dominant noise is per-run and independent, not per-block and common. I am
reporting this against my own prior because the honest version matters for anyone reusing
the design — and the conclusion is *keep the blocking anyway*. Its value is the guarantee
scored in P4: with order rotation, any monotone session drift (thermal, allocator, page
cache) lands on both arms equally and cannot alias into the contrast. Paying 1.25× in
variance for structural immunity to drift is a good trade when the alternative failure
mode is a confidently-signed artefact. What must **not** happen is anyone citing the
blocking as the reason the interval is tight. It is not.

### 5.6 Power curve, and the band on the power curve

| blocks | runs | hw µs/token | hw % decode | hw % `cs`(α) | hw % `cs`(β) |
|---|---|---|---|---|---|
| 4 | 8 | 28.990 | 0.3229 | 0.1929 | 0.2207 |
| 6 | 12 | 19.125 | 0.2130 | 0.1272 | 0.1456 |
| 8 | 16 | 15.236 | 0.1697 | 0.1014 | 0.1160 |
| **10** | **20** | **13.034** | **0.1452** | **0.0867** | **0.0992** |
| 12 | 24 | 11.577 | 0.1289 | 0.0770 | 0.0882 |
| 16 | 32 | 9.708 | 0.1081 | 0.0646 | 0.0739 |
| 20 | 40 | 8.528 | 0.0950 | 0.0567 | 0.0649 |
| 30 | 60 | 6.803 | 0.0758 | 0.0453 | 0.0518 |

Blocks needed to certify a summed effect (α / β):

| target | M4 µs (α) | M4 µs (β) | resolve (~50 %) | 80 % power | runs at 80 % |
|---|---|---|---|---|---|
| 0.40 % | 60.12 | 52.53 | 3 / 3 | 3 / 4 | 6 / 8 |
| 0.30 % | 45.09 | 39.40 | 4 / 4 | 4 / 4 | 8 / 8 |
| 0.25 % | 37.58 | 32.83 | 4 / 4 | 5 / 5 | 10 / 10 |
| 0.20 % | 30.06 | 26.27 | 4 / 5 | 6 / 6 | 12 / 12 |

**The `sd` is itself an estimate and I am not going to pretend otherwise.** The
chi-square CI95 on `sd` at dof 11 is **[12.908, 30.938] µs/token**. Half-widths scale
linearly in `sd` and block counts scale as `sd²`, so every row above carries a factor of
**[0.71×, 1.70×]** on its half-width and **[0.50×, 2.88×]** on its block count. Planning
uses the **upper** `sd`. Concretely: the ten-block half-width is 0.0867 % of `cs` (α) as
measured, but could be as poor as 0.1472 % if the true `sd` sits at the top of its band —
which is still inside the range that makes rule-105.5 summation decidable, so the plan
does not change. This is the interval-on-the-interval, and it is the number to quote when
someone asks how much the power curve can be trusted.

**Read this table as an upper bound on a staged-arm certificate, not as its estimate.** Every
row is built from the in-tree A/A sd of 18.222. §6.7 measured the same null with both arms
staged as prebuilt trees and got **sd 7.803** — 2.3× tighter, ≈5× in variance, with a
one-sided F-test at *p* = 0.037 against this table's sd. That is suggestive rather than
established (dof 5; its own chi-square CI spans a factor of 6 on block counts), so I am not
rewriting the table. But a certificate run staged-vs-staged should expect a ten-block
half-width nearer **5.6 µs/token = 0.0622 % of decode = 0.0371 % of `cs`(α)** than the
13.034/0.1452/0.0867 printed above, and the analyser will report which it actually got.

### 5.7 Correction to my own earlier claim

§0 and §7.1 were written before the measurement and say the instrument is **~2.25×**
tighter than fern's `--local-iterate` ABBA (±0.27 % of the score channel), with a
ten-block half-width of ≈0.1178 % of `cs`. Both figures came from the inferred `sd` of
24.8. On the measured `sd` of 18.222 the correct numbers are:

| quantity | pre-run claim (inferred sd 24.8) | measured (sd 18.222) |
|---|---|---|
| hw at 10 blocks, % `cs`(α) | 0.1178 | **0.0867** |
| tightness vs fern's ±0.27 % (α) | 2.25× | **3.11×** |
| tightness vs fern's ±0.27 % (β) | — | 2.72× |
| tightness at 12 blocks (α) | — | 3.51× |
| same, across the chi-square `sd` band (α) | — | 1.83× … 4.40× |

So the instrument is **better than advertised**, by about 38 %. I am recording the
correction rather than silently upgrading the claim, because the 2.25× figure has already
been quoted in this report and the provenance of the improvement matters: it is a smaller
measured noise floor, not a better design.

For scale against the standing bar: 0.4 % of `cs` is 60.12 M4 µs/token (α), and the
twelve-block half-width is 11.577 µs/token — **19.3 % of the bar**. The 0.25 % summation
target of rule 105.5 is 3.25× the half-width. Both are comfortably decidable in one
session, which is the whole point of building this.

### 5.8 The two questions the advisor asked the power curve to answer

**(a) alphonse's removal-symmetry ladder — how many blocks to resolve one dispatch?**

Rule 65 prices one dispatch at **2.3403 M5 µs/step**. On this instrument that is
**5.357 M4 µs/token = 0.0356 % of `cs` (α)**, and the answer is bad news stated plainly:

| rung | M5 µs/step | M4 µs/token | % `cs`(α) | blocks to resolve | blocks at 80 % power |
|---|---|---|---|---|---|
| 1 dispatch | 2.3403 | 5.357 | 0.0356 | **47** (94 runs, ≈5.2 h) | **93** (186 runs, ≈10.2 h) |
| 8 dispatches | 18.7224 | 42.853 | 0.2851 | **4** (8 runs, ≈26 min) | **4** (8 runs, ≈26 min) |

So, concretely, for alphonse: **do not run the n = 1 rung expecting a CI that excludes
zero.** One dispatch sits below even my 30-block half-width (0.0356 % vs 0.0453 %), and the
~47 blocks it would take is five hours of host time for a single point on a ladder — not
buyable tonight, and not a good trade even if it were. The **n = 8 rung is worth running**
and is cheap: four blocks, eight runs, ~26 min, with 80 % power. The right shape for the
ladder is therefore **fit the slope across the large rungs and read the per-dispatch price
off the fitted slope**, where the ladder's own leverage does the work my sd cannot. A slope
fitted across rungs at n = 8, 16, 32 buys per-dispatch resolution that no amount of
replication at n = 1 will.

**(b) rule 105.20's competing family-E price routes — can this instrument separate them?**

| route | % `cs` | M4 µs/token | half-widths at 10 blocks |
|---|---|---|---|
| A (dispatch elimination) | 1.069 | 160.7 | 12.3 |
| B (full fusion) | 1.690 | 254.0 | 19.5 |
| B − A (the discriminating gap) | 0.621 | 93.3 | **7.2** |

Yes, and not marginally: the two routes are **7.2 half-widths apart** at ten blocks, so a
single ten-block run distinguishes them at overwhelming confidence, and either route
individually is ≥12 half-widths from zero. This is the quantitative form of the advisor's
"only instrument sharp enough" claim, and it holds with room to spare — including at the
top of the chi-square `sd` band, where the gap is still 4.2 half-widths.

### 5.9 What this licenses, and what it does not

Licensed: quoting `sd(D) = 18.222 µs/token` (with its band) as the measured paired noise
floor of `--local-submit` decode on this host in epoch R107; using the §5.6 table to size
a certification campaign; and reporting a candidate contrast from this instrument as an
interval on the `cs` channel.

Not licensed: any claim that a *candidate* arm shares this noise floor. A candidate that
changes the kernel set, dispatch count, or memory traffic can have a different `sd`, and
P5 is precisely the check that would catch it — the campaign aborts if an arm's kernel set
moves mid-session. The A/A establishes the floor for two identical arms; a real
certification re-measures `sd` on the arms it actually ran, which is why the analyser
prints the measured `sd` every time rather than reusing this one.

---

## 6. Two-tree certification — the gap that would have stopped Part 2, and its fix

### 6.1 The gap

Everything in §1–§5 differentiates arms by **environment gates on one binary**. That is the
right shape for a knob, and it was the right shape for the void R107-J flip. It is the *wrong*
shape for every Part-2 target I was actually re-aimed onto at 15:55Z. Frieren's family-E
candidate (#660) is a **source transplant** — `lagunaGateSoftplus` (:4525) folded into
`lagunaDecodeNVFP4QKVR1` (:5002), ~+3,200 B. There is no env var that turns it on.

The obvious workaround is to ask the author to put her change behind a gate. **I am not going
to ask for that, because it would produce a weaker certificate, not a more convenient one.**
Rule 105.22(b) requires ten paired blocks *on the exact tree being submitted*. A default-off
gate means the arm I time is not the tree that ships: the shipped tree would carry a branch
the certified arm never executed, and the certified arm would carry a branch the shipped tree
never executes. Certifying a gated stand-in for a source change is exactly the "local-only
override as evidence that a candidate is rankable" that the challenge guide lists as a wrong
strategy.

### 6.2 The fix, and why it is legitimate rather than a trick

`benchmark.sh` already hands out the lever, in the trusted (non-editable) harness:

| line | mechanism |
| --- | --- |
| `benchmark.sh:212` | `RUNTIME_WORKER_BIN="${MLXFAST_RUNTIME_WORKER_EXECUTABLE:-.build-worker/release/mlxfast-runtime-worker}"` |
| `benchmark.sh:213` | `MLX_METALLIB="${MLXFAST_MLX_METALLIB:-$(dirname "${RUNTIME_WORKER_BIN}")/mlx.metallib}"` |
| `benchmark.sh:1543,1551` | the worker sandbox profile exec-allows exactly that absolute path |

Because the metallib is resolved *relative to the worker binary*, a directory containing
`{mlxfast-runtime-worker, mlx.metallib, mlx.metallib.fingerprint, *.bundle}` is a complete,
self-contained, immutable timing artifact — a **staged tree**. `research/maple-nezuko-r107j-stage-tree.sh`
builds the current working tree exactly as `benchmark.sh:2011-2023` does (`--scratch-path
.build-worker`, which is not optional: a bare `swift build -c release` writes `.build/release`
and the CLI deliberately prefers the `.build-worker` twin), then snapshots those artifacts and
writes a `SHA256SUMS` + `MANIFEST` recording head SHA, dirty-input count, and a **tree
fingerprint** over `git ls-files -s` plus `git diff HEAD` of `Package.*`, `Sources`, `Vendor`.

Certification then needs **no change at all** to `maple-nezuko-r107j-certify.sh`: arms are
already arbitrary `NAME=VALUE` assignments handed to `env` (`certify.sh:205`), so a tree *is*
an arm:

    research/maple-nezuko-r107j-certify.sh --blocks 10 \
        BASE:MLXFAST_RUNTIME_WORKER_EXECUTABLE=$STAGE_ROOT/BASE/mlxfast-runtime-worker \
        CAND:MLXFAST_RUNTIME_WORKER_EXECUTABLE=$STAGE_ROOT/CAND/mlxfast-runtime-worker

where `$STAGE_ROOT` **must not** be under `/tmp` or `/var` — see the measured correction in
§6.5, which is the difference between this working and every run failing.

Both arms are then real compiled trees, timed back to back inside one ABBA session, under one
thermal gate, with **no build between arms**. This is strictly stronger than gating: the
candidate arm executes the candidate's own default path, and the certificate attaches to a
binary whose sha256 is recorded.

### 6.3 Why staged copies must be *copies*, and three guard rails

Plain `cp` gives each staged artifact an mtime of *now*, newer than every build input. That is
load-bearing rather than incidental: it holds `swift_build_required()` (`benchmark.sh:1972`)
and `metallib_rebuild_required()` (`benchmark.sh:1937`) quiet for the whole campaign, so no arm
can silently rebuild and time a *third* binary mid-session. Build both trees first, stage
second, and the freshness gates stay closed.

Three guard rails, all encoded in the tool rather than left to my memory:

1. **`--diff-guard REF` refuses the shortcut where it is unfaithful.** `weights/` is
   regenerated from `Package.*`, `Sources/MLXFastCore`, `Sources/MLXFastTransform`
   (`source_hash()`, `benchmark.sh:~1585`), and both arms share **one** `weights/` directory.
   A transform-side candidate timed by worker swap would run the candidate binary against the
   *wrong* weights. The tool exits 3 and says so. Verified against a ref that does change those
   inputs (it lists `Package.swift`, `Sources/MLXFastCore/…`) and against `705484b9`, which
   does not — the latter reports `two-tree staging LEGAL`.
2. **AOT metallib changes are legal but noisy.** Each staged tree carries its own metallib, so
   an AOT-touching candidate *is* certifiable this way; but the trusted CLI will warn that the
   overridden metallib does not match the checked-out sources. The tool prints that the warning
   is expected, so nobody reads it as a defect — and, equally, so nobody dismisses a *real*
   fingerprint warning by reflex.
3. **Custody is rechecked, not assumed.** `--verify LABEL` re-runs `shasum -c` after the
   campaign. A certificate over a binary that changed under me is not a certificate.

The tool never runs `git`-mutating commands. The operator arranges the tree (checkout, merge,
cherry-pick) and then stages it, so tree custody stays auditable and the tool is never in the
business of restoring someone else's work tree.

### 6.4 What this does not fix

Staging costs one build per tree, which is minutes, and ~208 MB of scratch per tree. It cannot
certify a transform-side candidate (guard rail 1). And it does not make a two-tree comparison
*paired at the source level*: if the two trees differ in more than the one mechanism under
test, the interval is honest about the pair of trees and silent about which of their
differences caused it. That is a property of the trees, not of the instrument, so the operator
must state the diff. `--diff-guard` prints it.

### 6.5 Correction (post-publication, 17:41Z): the staging root may not live under `/tmp`

Part 1 was published at **17:30:36Z** describing the staged-tree lever as verified. That
verification covered `--diff-guard`, custody hashing, and the *plumbing* of
`MLXFAST_RUNTIME_WORKER_EXECUTABLE`; it did **not** cover a timed run through a staged worker.
At **17:32:20Z**, two minutes after publishing, I ran that missing test — one block, two staged
arms, staging root `/tmp/r107j-stage` — and **both runs failed**:

    runtime worker closed stdout before returning a response: exit_status=71
    stderr=sandbox-exec: execvp() of '/private/tmp/r107j-stage/dryrun_base/
    mlxfast-runtime-worker' failed: Operation not permitted

So the readiness claim in §6.2 was false *as staged*. The mechanism is now understood, and it
is a property of the **path**, not of staging: four links, each measured on this host at 17:41Z
rather than inferred from reading code.

| link | evidence |
| --- | --- |
| 1. the harness spells the exec literal as `/private/tmp/…` | `benchmark.sh:1524 write_runtime_worker_sandbox_profile()` uses `absolute_path()` (`benchmark.sh:1255`, `cd -P` / `pwd -P`), which resolves `/tmp` through the firmlink |
| 2. the trusted harness then **rebinds** the profile | `Sources/MLXFastTrustedHarness/LagunaRuntimeWorker.swift:1494-1538` (called `:1567`, `:1689`) strips every `(allow process-exec` line, appends `(deny process-exec*)` and exactly one `(allow process-exec (literal <resolved>))`, with `<resolved> = URL(fileURLWithPath:).standardizedFileURL.resolvingSymlinksInPath().path` |
| 3. Foundation **strips** the `/private` firmlink prefix | measured with a Swift snippet: `/private/tmp/X → /tmp/X`, `/private/var/Y → /var/Y`, `/Users/… → /Users/…` unchanged |
| 4. seatbelt matches `(literal …)` against the **firmlink-resolved** path | measured truth table below |

Truth table, same staged binary, hand-written profiles of the same shape the harness writes
(`(allow default)`, `(deny network*)`, `(deny process-fork)`, `(deny process-exec*)`, one
`literal` allowance):

| profile literal | `sandbox-exec` argv | result |
| --- | --- | --- |
| `/private/tmp/X` | `/private/tmp/X` | exit 0 |
| `/private/tmp/X` | `/tmp/X` | exit 0 |
| `/tmp/X` | `/private/tmp/X` | **EPERM (71)** |
| `/tmp/X` | `/tmp/X` | **EPERM (71)** |

A `/tmp`-spelled literal is unmatchable however `argv` is spelled, so links 2–3 write a literal
that link 4 can never match. The staged worker is otherwise perfectly executable: run directly,
`/tmp/r107j-stage/dryrun_base/mlxfast-runtime-worker --help` exits 0, and under a profile whose
literal is spelled `/private/tmp/…` it also exits 0. Nothing is wrong with the binary, the
staging, or the candidate tree; retrying cannot help, and each attempt costs a ~60 s run.

Two consequences, both now encoded in the tool rather than in my memory:

1. `STAGE_ROOT` **defaults** to `$(cd .. && pwd -P)/r107j-stage`, a sibling of the checkout —
   outside `git`, so the worktree stays clean for `run_job`, and outside the firmlinked
   prefixes.
2. `stage-tree.sh` **refuses** `/tmp`, `/var` and their `/private` spellings up front, printing
   the measured reason. `$TMPDIR` is refused too: on this host it lives under `/var/folders`.

This is the fourth guard rail of §6.3, and it is the one I would never have found by reading
code, because every step of links 1–3 looks correct in isolation.

### 6.6 Preregistration of the staged-tree A/A (written 18:05Z, mid-run, block 1 already seen)

§6.5 fixed the staging root but left the mechanism unproven: a staged worker had never once
executed. This is the run that proves or kills it. It is a **mechanism check, not a
certificate** — see the resolution caveat at the end.

**Disclosure first, because it weakens what follows.** The run was launched at **17:46:27Z** by
an earlier turn of this session and it is still executing as I write. Block 1 finished at
17:57:06Z and **I have read its three rows.** They are:

| block 1 | arm | decode µs/token | passed | golden |
| --- | --- | --- | --- | --- |
| pos 1 | `IN` | 8960.083 | yes | `f49e4c2c…` |
| pos 2 | `SB` | 8973.008 | yes | `f49e4c2c…` |
| pos 3 | `SC` | 8990.527 | yes | `f49e4c2c…` |

so I already know `SB−IN = +12.93`, `SC−IN = +30.44`, `SB−SC = −17.52` µs/token in block 1.
This is therefore a **partial** preregistration, and I am not going to dress it up as more.
Three things limit the damage, and a reader can check all three:

1. the predictions below are about **six-block intervals**; block 1 is one sixth of the data and
   a single block's difference has sd ≈ 18.2 µs/token (§5.2), so it constrains an interval very
   little;
2. the seen numbers are printed above, so anyone can ask whether the seen block drove the
   prediction. In fact it argues the other way: block 1's `SC−IN = +30.44` **already exceeds**
   the ±19.1 µs threshold that prediction R2 commits to, so seeing it made R2 *riskier*, not
   safer. The threshold comes from §5.2's sd, not from this run;
3. the commit carrying this text is timestamped before runs 4–18 exist. The commit graph is the
   evidence, as in §1 and §3A.

**Design, fixed before launch.** Session `20260810T174627Z`, head `0a1d70f81c25`,
`dirty_files=0`, `./benchmark.sh --local-submit`, `--blocks 6`, three arms interleaved within
block with block order randomised — 18 runs, ~213 s each, ≈64 min:

| arm | worker executable | role |
| --- | --- | --- |
| `IN` | in-tree (`--local-iterate` build dir, no gate) | reference (`labels[0]`) |
| `SB` | `…/workspace/r107j-stage/sb_base/mlxfast-runtime-worker` | staged tree #1 |
| `SC` | `…/workspace/r107j-stage/sb_copy/mlxfast-runtime-worker` | staged tree #2, byte-identical to #1 |

`SB` and `SC` are copies of the **same** build, so every contrast here is a null by
construction. The two contrasts answer different questions:

- **`SB−IN` and `SC−IN` — the staging offset.** In-tree exec versus staged exec. This
  confounds directory location, the copy itself, path length and any sandbox effect. It is a
  *nuisance* term.
- **`SB−SC` — the load-bearing null.** Two staged trees, identical bytes, different
  directories. This is exactly the contrast a two-tree certificate takes, and it is the one that
  must cover zero for §6.2's lever to be usable.

The analyser compares every arm to `labels[0]`, so it will print `SB−IN` and `SC−IN` only.
`SB−SC` will be obtained by filtering the rows to the `SB` and `SC` lines (keeping the header,
`SB` first so it becomes the reference) and re-running the *same unmodified* analyser. I will
**not** edit `maple-nezuko-r107j-paired-ci.py` while the job is live: `certify.sh` invokes it at
the end, so an edit now would change the instrument mid-measurement.

**Registered predictions.**

- **R1 (the one that matters).** `SB−SC` CI95 covers zero, and |point| < 19.1 µs/token.
- **R2.** |staging offset| < 19.1 µs/token on both `SB−IN` and `SC−IN`. I do **not** predict its
  sign. If both come back the same sign and outside the band, a real staging offset exists and
  must be disclosed — it still does not invalidate a certificate, by R4.
- **R3.** 18/18 correctness passes and exactly **one** golden hash, equal to the in-tree
  `f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2`. A staged worker that
  disagreed with the in-tree worker on a single token would end §6.2 outright.
- **R4 (decision rule, not a prediction — recorded so it cannot be chosen after the fact).** In
  any two-tree certificate **both arms must be staged, and `IN` must never be an arm.** A
  staging offset is common-mode across two staged arms and cancels in their contrast; against an
  in-tree arm it does not. R2 is therefore allowed to fail without costing the lever, and R1 is
  not.

**Resolution caveat — this run cannot show the offsets are zero, only bound them.** At six
blocks, with §5.2's paired sd of 18.222 µs/token, SE = 7.439 and t(0.975, 5) = 2.571:

```
CI95 half-width @ 6 blocks = 19.12 M4 us/token = 0.213 % rel. decode = 0.127 % of cs (alpha)
```

So a staging offset of up to ~0.21 % of decode would pass unnoticed. Worse, six blocks estimate
the *staged* contrast's own sd at dof 5, whose chi-square CI is [0.624, 2.453]× the point — so
this run does not pin the sd of a staged-arm certificate either. Ten blocks remain the
certificate size (§5.6). Six were bought because the run is a prerequisite check on an evening
in which frieren's tree may land at 21:00Z, and the certificate blocks are reserved for the
candidate.

### 6.7 The staged-tree A/A, scored against §6.6 (complete 18:51Z)

Session `20260810T174627Z`, head `0a1d70f81c252f66727ff6842ade79a6f70d0766`, `dirty_files=0`,
`./benchmark.sh --local-submit`, 6 blocks × 3 arms = **18 runs**, 17:46:27Z → 18:51Z, 205–232 s
per run. Raw rows: `research/maple-nezuko-r107j-staged-aa-rows.tsv`.

**Custody first, because it is what licenses the rest.** Both staged directories carry the
*same* fingerprint, and `--verify` re-run **after** all 18 runs still reproduces it:

    sb_base  tree_fingerprint=2ecee7d1... worker=829a8d4e... metallib=8e8b18af...
    sb_copy  tree_fingerprint=2ecee7d1... worker=829a8d4e... metallib=8e8b18af...

So `SB` and `SC` are **byte-identical binaries in different directories**. This is a true null:
any difference between them is instrument, placement or chance, and cannot be code.

| arm | n | mean µs/token | sd | cv% |
| --- | --- | --- | --- | --- |
| `IN` (in-tree, reference) | 6 | 8972.872 | 11.714 | 0.131 |
| `SB` (staged) | 6 | 8972.112 | 6.262 | 0.070 |
| `SC` (staged copy) | 6 | 8978.131 | 7.567 | 0.084 |

#### The three contrasts

| contrast | point µs/token | CI95 µs/token | % cs(α) point | covers 0 | paired sd | t | sign-flip p |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SC − SB` (staged vs staged) | **+6.019** | [−2.171, +14.209] | +0.0400 | **YES** | **7.803** | +1.889 | 0.156 |
| `SB − IN` | −0.761 | [−18.703, +17.182] | −0.0051 | YES | 17.094 | −0.109 | 0.969 |
| `SC − IN` | +5.258 | [−14.168, +24.685] | +0.0350 | YES | 18.508 | +0.696 | 0.500 |
| pooled staging offset `mean(SB,SC) − IN` | +2.249 | [−15.993, +20.491] | +0.0150 | YES | 17.383 | +0.317 | — |

Prefill was neutral on every contrast (all CIs cover zero), and every position OLS slope covers
zero, so no ordering confound. The `SC − SB` position slope is the closest to significant
(+3.880 µs/position, CI [−0.577, +8.338]), but **mean `dpos` is exactly 0 across the six
blocks** — the rotation balanced positions perfectly — so the point estimate is unbiased with
respect to position by construction, not by luck.

#### Scoring the four registered predictions

| # | prediction | outcome |
| --- | --- | --- |
| **R1** | `SB−SC` CI covers zero **and** \|point\| < 19.1 µs | **PASS.** CI [−2.171, +14.209] covers zero; \|point\| = 6.019 µs, well inside 19.1 and inside its own 8.190 half-width. |
| **R2** | \|staging offset\| < 19.1 µs, sign unpredicted | **PASS.** Pooled +2.249 µs (CI covers zero); each staged arm separately −0.761 and +5.258 µs. Staging a tree does not measurably change what it measures. |
| **R3** | 18/18 pass, one golden `f49e4c2c…` | **PASS.** 18/18 `passed=true`, 0 correctness failures, single golden `f49e4c2cbc0d3ceee9…`, all 18 `rc=0`. |
| **R4** | both arms staged; `IN` never an arm in a certificate | **HONOURED.** `IN` appeared here only as the in-tree reference needed to *measure* R2's staging offset. A real certificate uses two staged arms. |

All four pass. The mechanism §6 was built on is now measured, not merely argued: **a whole built
tree can be made an arm without perturbing its own timing, and two copies of one tree are
statistically indistinguishable.**

#### The finding I did not predict, and it is the most useful one

`SC − SB` has paired sd **7.803** µs/token. Both contrasts against the in-tree reference have
sd ≈ 17–18.5, and Part 1's in-tree-vs-in-tree A/A had **18.222**. The staged-vs-staged contrast
is about **2.2–2.4× tighter in sd, ≈5× in variance**:

| contrast type | paired sd | hw @ 10 blocks | as % decode | as % cs(α) |
| --- | --- | --- | --- | --- |
| in-tree vs in-tree (Part 1, dof 11) | 18.222 | 13.034 | 0.1453 | 0.0867 |
| staged vs in-tree (`SC−IN`) | 18.508 | 13.239 | 0.1476 | 0.0881 |
| **staged vs staged (`SC−SB`)** | **7.803** | **5.582** | **0.0622** | **0.0371** |

One-sided F-tests on the variance ratio (own `betainc`; both sanity checks reproduce the
tabulated `F(0.95,·,5)` to four decimals):

| against | F | df | p (one-sided) |
| --- | --- | --- | --- |
| Part 1 in-tree pair | 5.453 | (11, 5) | **0.0370** |
| same-session `SC−IN` | 5.626 | (5, 5) | **0.0405** |
| same-session `SB−IN` | 4.799 | (5, 5) | 0.0551 |

**Honest reading: suggestive, not established.** Two of three clear 0.05 and the third misses at
0.055; the three share one dof-5 denominator so they are not independent evidence. The
chi-square CI on the 7.803 itself is [4.871, 19.138] at dof 5 — a factor [0.39×, 6.02×] on
planned block counts. Nobody should plan a campaign against 0.0371 % cs(α) yet.

The mechanism is nonetheless plausible enough to state: when *both* arms are staged they carry
identical staging overhead — same code path through `MLXFAST_RUNTIME_WORKER_EXECUTABLE`, same
sibling-metallib resolution, same cold-start behaviour — so that overhead and its run-to-run
noise cancel in the difference. Against an in-tree reference it does not cancel, and it lands in
the residual. The pairing statistic corroborates this from the other direction: within-block
`r = +0.376` for `SC−SB` (blocking is a **1.58× variance win**), versus `r = −0.789` and
`−0.835` against `IN`, and `−0.249` in Part 1. **Blocking only helps when the two arms are the
same kind of thing.**

Two consequences worth acting on:

1. **Certificates must be staged-vs-staged, never staged-vs-in-tree.** §6.3 argued this from
   custody. It now has an independent variance argument, and the variance argument is the one
   that costs runs if ignored.
2. **Part 1's power curve is the conservative bound for a real certificate, not the estimate.**
   Every block count in §5.6 was computed from an in-tree-vs-in-tree sd. If the staged-vs-staged
   sd holds up, a ten-block certificate resolves ~0.037 % of `cs` rather than ~0.087 %. I am
   **not** revising §5.6 downward on dof 5; I am flagging that the next A/A should be
   staged-vs-staged at ten blocks so the sd that actually governs certificates is the one
   measured with real precision.

The one number I am least comfortable with is `SC − SB` = +6.019 with `t = +1.889` and 5 of 6
blocks positive (sign-flip p = 0.156). It covers zero, so R1 passes as written, but the lower
limit is only −2.17. Since the binaries are provably identical, a genuine effect here could only
be **placement** — directory position, page-cache or filesystem locality — which would be a real
and awkward instrument bias worth knowing about. Six blocks cannot separate that from an
ordinary 1-in-6 fluctuation. The staged-vs-staged ten-block A/A recommended above is exactly the
run that would settle it, and until it exists I treat +6 µs/token (≈0.04 % of `cs`) as the
instrument's honest placement-bias uncertainty rather than asserting it is zero.

---

## 7. Part 2: status of the certification targets

Part 2 was re-aimed twice. As originally written it asked me to certify edward's (#629) or
alphonse's (#644) candidate and then the sum on the combined tree; the 15:55Z re-aim stood
edward's T2c packing and alphonse's oproj amortisation down and pointed me at frieren's
family-E merge (#660) and alphonse's removal-symmetry ladder (#644) instead. The original
finding is preserved below because it is the reason the slot was free at all. Checked directly
against the remote, not inferred:

| branch | remote head | what is on it |
| --- | --- | --- |
| `maple-edward/r107-routed-gateup-packing` | `526881c4f6e2b879c1dfef67212b852cf5c9b7ed` | one commit, `assign maple-edward…`; its only diff vs the shared base `fc66172b` is **−25 lines** of `Vendor/…/quantized.cpp`, i.e. it is *behind* base, not ahead of it |
| `maple-alphonse/r107-decode-oproj-amortisation` | `f66a34b863ca2d9031ff800c946ae83d206bbf23` | one commit, `senpai assignment…`; no candidate |

Both SHAs were re-read from `origin` at **15:47Z** and were unchanged from my earlier check.
There is nothing to certify, so per the brief I am not inventing a target. The freed slot was
*intended* for the positive control of §3A, which serves the same end — it is the test that
converts "here is a power curve" into "here is a power curve I have shown to be honest at the
effect size that matters". **It did not run inside Part 1.** The A/A campaign consumed the
whole slot (24 runs, 15:32:24Z→17:03:09Z) and the positive control needs 20 more. §3B records
its disposition; this sentence used to read as though the control had run, which was wrong, and
is corrected here.

The instrument is ready the moment either lands. Certifying one candidate is a single command
with a gate list, and certifying **the sum** — the thing rule 105.5 actually requires, since
rule 105.12's live slate has no arm above 0.45× of the slot threshold on its own — is the same
command with a third arm that sets both gate sets at once:

    research/maple-nezuko-r107j-certify.sh --blocks 8 \
        C: E:<edward gates> A:<alphonse gates> S:<edward gates>,<alphonse gates>

That four-arm form is deliberate. It measures each part *and* the sum against one shared
reference in one interleaved session, so the summand CIs and the sum CI share a thermal
history and a block structure. Summing two separately-run point estimates and adding their
variances would be the cheaper thing to do and would be wrong: it assumes the two levers do
not interact, which is exactly the claim rule 105.5's "on the same integrated tree" wording
exists to stop anyone assuming. With §6 in hand the same argument holds for trees: the
four-arm form generalises to `BASE / A-tree / B-tree / merged-tree`, four staged directories,
one session.

### 7.1 The re-aimed targets, as of this session

| target | state | can I certify it, and how |
| --- | --- | --- |
| frieren family-E, #660 | head `c46b3934`, base `705484b9`. Advisor told her at 16:31Z **not to build yet** and to run a ~45-min barrier-region price probe (arm F free-region vs arm S serialising no-ops, `N ∈ {0,10,20,40,80}`) reporting **19:00Z**. So there is no candidate binary to certify yet, by instruction. | Yes — §6 two-tree. `--diff-guard 705484b9` already reports **LEGAL**: her mechanism is in `Sources/MLXFastModel`, not in the weights-generating inputs. Her head is not in my object store yet, so staging it needs one `git fetch` first. |
| alphonse removal-symmetry ladder, #644 | no candidate on the branch as of the last remote read. | Yes, same mechanism, subject to the same `--diff-guard`. |

Two facts from her Stage 0 change what a certificate would even be *for*, and I record them
because they bear on my own arithmetic rather than only on hers:

1. Her Stage 0 drove the per-removal dispatch-glue ceiling to **≤1.1937 M5 µs/dispatch**,
   `k_removal ∈ [0, 0.964]`. `k = 1.0` is *above* that ceiling, so **no candidate may be
   justified by dispatch count alone** any more. Certification by measurement is therefore not
   a nicety for family E; it is the only remaining route.
2. The advisor's correction that family E's n is **40, not 30** makes every earlier family-E
   figure 33 % low, and her §11.4 "+2.19–2.31 %" double-counts. I have deliberately not
   re-derived her number: my job this round is to supply the interval, not to supply a second
   prediction to be disappointed by.

Set against tanjiro's R108-L (`874e4917`), which priced removal at `k = 0.0872`, CI
[−0.221, +0.438] and returned `N-NO-MERGEABLE-PAIR`, the honest prior on family E is weak. That
is precisely the regime where a 3.11×-tighter instrument earns its keep: a weak prior plus a
wide instrument yields nothing, while a weak prior plus a **measured half-width of 0.0867 % of
`cs`** at ten blocks (§5.6; ≤0.1472 % at the top of the `sd` band) either clears the rule-105.21
arming threshold of a certified **+1.0 % of `cs`** or rules it out in a single session.

### 7.2 Standing readiness, and the hand-off constraint

Concretely, on this host, from the moment a candidate tree exists:

| step | cost |
| --- | --- |
| `--diff-guard` the candidate against its base | seconds |
| stage base tree, stage candidate tree (two builds) | ~10–20 min |
| ten paired ABBA blocks, `--local-submit`: 20 runs × ~198 s | **~66 min** |
| analyser + `--verify` custody on both trees | seconds |

So a full two-tree certificate is **~1.5 h wall-clock**. The timed part is identical to a gated
ten-block run — both are 20 `--local-submit` runs — so two-tree buys a stronger certificate for
the price of exactly two builds. Against the draw schedule (student hand-offs to fern **06:00Z**, integration freeze **07:00Z**,
draws **08:00Z / 08:25Z**, hard stop **09:00Z**) that means a candidate tree must exist by
roughly **04:15Z** for a certificate to reach the 06:00Z hand-off with any margin. It does
**not** fit if a tree lands after the freeze, and I will not certify a post-freeze tree by
shortening the block count — rule 105.22(b) fixes ten, and a six-block interval is a different,
wider instrument wearing the same name.

If nothing lands by **22:00Z** the brief tells me to report and stand down, and I will do that
rather than manufacture a target.

### 7.3 The target may not exist: frieren was re-aimed away from building the merge (16:31Z)

Read at 18:02Z on #660, after Part 1 was submitted, so it is recorded here rather than acted on.
The advisor's 16:31Z comment tells frieren **"do not build the merged kernel yet"** and replaces
her 21:00Z Stage-1 with a **barrier-region price probe reporting at 19:00Z**: two arms of no-op
dispatches, arm F joining the existing barrier-free concurrent region and arm S chained to
serialise, with the mechanism read out of `Vendor/mlx-swift/…/metal/device.cpp` — every MLX
compute encoder is `MTL::DispatchTypeConcurrent` (`:545-548`) and `maybeInsertBarrier()`
(`:363-375`) emits a barrier only on a true RAW hazard (`:325`). If QKV and gate_sp are already
in the same barrier-free region, merging them refunds nothing and risks PR #48's occupancy loss.
The stated decision rule is arm-F slope ≲0.3 M4 µs/dispatch ⇒ the merge programme is dead;
≥0.8 ⇒ build as briefed.

Two consequences for me, neither of which I get to choose:

1. **There may be no candidate tree tonight at all.** The 21:00Z slot I was holding open is now
   a probe result, not a tree, and on the low branch of that rule no family-E tree is ever built.
   My readiness posture is unchanged — the two-tree instrument is the same instrument whichever
   arm needs it — but I should not represent a certificate as scheduled.
2. **The probe is a slope, and a slope is a thing my instrument can measure.** Arm F sweeps
   `N ∈ {0, 10, 20, 40, 80}` no-op dispatches; that is a regression, not a paired contrast, and
   the quantity of interest is µs per dispatch. The units line up directly: the harness reports
   µs/**step**, and `N` is dispatches **per step**, so the slope is µs/dispatch with no transfer
   factor. With `N` as the arm label, five arms × six blocks (30 runs, ~1.8 h) and block fixed
   effects:

   ```
   sigma_within = 18.222 / sqrt(2)        = 12.885   (a paired difference of two runs is sqrt(2) x a run)
   sum (N - Nbar)^2 = 6 x (900+400+100+100+2500) = 24,000     (Nbar = 30)
   SE(slope) = 12.885 / sqrt(24,000)      = 0.083 M4 us/dispatch
   ```

   which separates the rule's 0.3 from its 0.8 by **6.0σ**, and would put a CI of ±0.19 (t≈2.06,
   dof 24) on either. That is a much sharper way to run the probe than a standalone
   microbenchmark, and it runs in the scored regime as the advisor asked. I am not offering to
   take her arm over; I am recording that the instrument covers it, so the offer exists if the
   19:00Z result lands ambiguous ("between the two ⇒ report both slopes with CIs and let me
   decide" is exactly the outcome an interval buys down).

   *(Corrected in place before publication: my first draft of this paragraph divided the
   paired-difference sd by √(6·Σ(N−N̄)²) and printed 0.0055, which is both the wrong sd and a
   slipped division — 18.2/154.9 is 0.118, not 0.0055. The conclusion survives at 6σ instead of
   the nonsensical 90σ.)*

### 7.4 Candidate-tree census (18:08Z): the epoch currently contains zero candidate trees

§7.3 argued from advisor instructions that my certification target *might* not exist. I then
measured it instead of arguing it. For every current-epoch head I fetched the ref explicitly
and diffed it against the Part-2 integration base restricted to the submitted surface:

    git fetch origin <branch>
    git diff --name-only 705484b9 <head> -- Sources/MLXFastModel Sources/MLXFastTransform Vendor

| branch | head | submitted paths changed vs `705484b9` |
| --- | --- | --- |
| `codex/mlxfast-maple-20260804-advisor` | `1264d70c` | **0** |
| `maple-frieren/r108-k-decode-dispatch-merge` | `c46b3934` | **0** |
| `maple-tanjiro/r108-l-adjacent-pair-dispatch-ledger` | `5333c9bc` | **0** |
| `maple-edward/r108-n-t3a-instruction-axis` | `b9adebcf` | **0** |
| `maple-fern/r108-m-bandwidth-probe-and-freeze-custody` | `d406439b` | **0** |
| `maple-nezuko/r107-qkv-packing-replication` (mine) | `e99bddd6` | **0** |

Every R108 branch is **byte-identical to `705484b9` on the submitted surface**; all six differ
only under `research/`. Frieren's branch in particular contains eight changed files, all of them
`research/` documents and scripts — consistent with the 16:31Z redirect away from building the
merged kernel, and confirming it at the level of bytes rather than inference.

**So as of 18:08Z there is nothing to certify.** Every live arm in the epoch is census, ledger,
probe, or instrument work. This is not a complaint: it is the correct state for an epoch that
is pricing mechanisms before building them, and it is the reason Part 2 delivers a *calibrated
instrument* rather than a certificate. It does mean nobody should read a scheduled certificate
into my readiness statement.

Three qualifications, so this is not over-read:

1. **It is a snapshot, not a guarantee.** A tree pushed at 18:30Z invalidates the table and not
   the readiness. Re-run the two commands above rather than trusting this row set.
2. **It cannot see uncommitted work.** Another student may have a candidate live in a working
   tree. That does not change my critical path: `stage-tree.sh` stages a *built* tree and
   `certify.sh` records `dirty_files`, so an uncommitted candidate is not stageable as a
   custody-checked arm until it is committed anyway.
3. **I only censused R108 and the advisor head.** The R107 branches are the previous epoch and
   are already dispositioned.

The transferable point is a repo rule made concrete. `AGENTS.md` says not to select the frontier
by pulling a remote branch or inferring it from a branch name. Here is the sharpest available
illustration, and it is measured rather than asserted: a branch named
`r108-k-decode-dispatch-merge` contains **no merged dispatch kernel**. The census above costs one
fetch and one diff per head and answers the question the name only gestures at.

Restating the deadline arithmetic from §7.2 against this census: guard + two builds + twenty
paired runs is about **1.5 h**, so a candidate tree must exist by roughly **04:15Z** to be
certified before the 06:00Z hand-off. I will not shorten the ten blocks to fit a later arrival;
a certificate with six blocks' resolution is a different and weaker claim, as §6.6 shows.

### 7.5 Frieren's price probe lands terminal (18:27Z, resubmitted 18:43Z) and changes the target's shape

PR #660 is now terminal with verdict **P-INDETERMINATE**: her slope landed inside the advisor's
undecided 0.3–0.8 band, so the 16:31Z decision rule returns "report both slopes with CIs" rather
than "build" or "kill". Her numbers, which I take as given input rather than re-deriving:

| quantity | value | CI95 |
| --- | --- | --- |
| `k`, dispatch price, unchained ladder | 0.4478 M4 µs/dispatch | [0.4006, 0.4950] |
| `k`, chained ladder | 0.465 | [0.417, 0.512] |
| barrier price at N=160 | −0.096 µs/barrier | [−0.213, +0.022] |
| M2 merge prize, repriced | 17.9 µs/step = 0.20 % decode | 0.15 % of score |

Three consequences for me. First, `k` is **4.2× cheaper** than the 1.890 µs/dispatch the merge
programme had been assuming, which is why the repriced merge prize (0.15 % of score) is below the
0.4 % draw bar of rule 105.21 and far below the +1.0 %-of-`cs` arming threshold of rule 105.23.
Second, she corrected the estimator: because `lagunaInjectLayerWork` guards `!pending.isEmpty`
before `asyncEval`, an injected arm pays `d(N) = N·k + 40·c`, and only a *difference of rungs*
cancels the `40c` term. Third, and this is the part I am acting on, that correction exposed an
intercept she flags but does not claim:

> `c ≈ −3.76` (unchained) to `−4.21` (chained) **M4 µs per layer**, i.e. `40c ≈ −150 to −168
> µs/step ≈ 1.7 % of decode ≈ 1.0 % of cs(α)`.

Her single-rung arm-F read is −0.491 [−0.654, −0.329] µs/dispatch, meaning the N=160 arm was
*faster* than control by about 78.6 µs/step. She states the caveats herself and I repeat them
rather than soften them: `c` is an N=0 extrapolation; the arms differ in tape-split structure as
well as dispatch count; her CIs are pooled within-arm with **B=4 at the 160 rung and B=1 at
1200**, so the true width is understated; the ladder is superlinear above 1200; and her own
4500 s job deadline truncated the campaign at ~18:18Z with run 17 of 19 discarded. It is her #1
follow-up.

This is the right Part-2 target for a certification instrument, for reasons that are about role
rather than appetite:

1. It is a **published result from another arm**, not a target I invented to keep busy. §7.4
   established that the epoch contains no candidate tree; this is the alternative that does not
   require one.
2. It is the author's own stated follow-up, so replicating it is service rather than poaching.
3. The effect size, ≈1.7 % of decode, is larger than every gap-scale lever currently in play
   (§7.1 records 1.6359 % as the whole remaining gap) and would clear the arming threshold.
4. The failure mode of her read is **exactly** the failure mode this instrument exists to fix:
   a quantity extracted from an unbalanced ladder with a B=1 rung, no position balance, and
   pooled within-arm variance. Putting a paired, position-balanced, blocked CI on it is the
   instrument's entire purpose.
5. It costs **zero editable bytes**. The injection scaffolding is already in my base tree, so
   there is nothing to submit and nothing to review.

What it is **not**: a shippable certificate. Injected no-op dispatches cannot ship. If `c` is
real, the shippable form is a *commit-cadence* change in the runtime — periodic `asyncEval` at
layer boundaries during decode on arrays the model already produces — and that is a different
change with its own price, its own correctness surface, and an overlap with the region frieren
already owns. I am measuring a price for the advisor's merge decision, not proposing a candidate.

### 7.6 Preregistration: the commit-cadence ladder (written 19:20Z, before the run)

#### 7.6.1 Scaffolding audit, so the mechanism is not assumed

Read in my own base tree, `Sources/MLXFastModel/LagunaRuntimeModel.swift`: call site `:11715`,
function `lagunaInjectLayerWork` `:12098`, share helper `lagunaInjectShare` `:12088`, activation
predicate `lagunaInjectActive` `:12094`. `LagunaConstants.numHiddenLayers = 40`
(`Sources/MLXFastModel/LagunaConfig.swift:20`). The four facts the design depends on:

- `lagunaInjectShare(total, layer) = (layer+1)*total/40 − layer*total/40`, so N=40 gives **exactly
  one** empty per layer and N=400 gives **exactly ten**; the integer division is exact at both
  rungs, with no ragged layer.
- `DARKBLOOM_INJECT_EMPTY_SPREAD=0` replaces that share with `layer == 0 ? total : 0`. Layers 1–39
  then compute `sweeps = matmuls = empties = 0`, `pending` is empty, and the function returns at
  `guard !pending.isEmpty` **before** `asyncEval`. So SPREAD=0 buys **exactly one** injected
  commit per decode step where SPREAD=1 buys **forty**, at identical total dispatch count.
- All decode knobs are gated on `isSingleTokenDecode`, and the prefill knobs stay at 0, so
  **prefill is untouched by construction** and serves as a built-in null channel.
- Injected arms allocate `LagunaInjectStore.scratch` (pool `1<<24` uint32 ≈ 67 MB) that control
  does not. Negligible against 48 GiB, disclosed because it is an arm asymmetry.

#### 7.6.2 Arms (reference first)

All arms share `DARKBLOOM_INJECT_EMPTY_TG=8` and `DARKBLOOM_INJECT_EMPTY_CHAIN=0` to match the
unchained ladder that produced frieren's headline `k`.

| arm | gates | dispatches/step | injected commits/step |
| --- | --- | --- | --- |
| `CTL` | *(none)* | 0 | 0 |
| `S1` | `DECODE_EMPTY=40, TG=8, CHAIN=0, SPREAD=1` | 40 | **40** |
| `S0` | `DECODE_EMPTY=40, TG=8, CHAIN=0, SPREAD=0` | 40 | **1** |
| `N400` | `DECODE_EMPTY=400, TG=8, CHAIN=0, SPREAD=1` | 400 | 40 |

#### 7.6.3 Estimators

- **`S1 − S0` = 39·c.** Dispatch count, injected arithmetic, threadgroup geometry and chain mode
  are held *exactly* equal; the only difference is how many layer boundaries commit. This is the
  clean isolation of commit cadence and it is the primary estimator.
- **`N400 − S1` = 360·k.** A low-rung dispatch price independent of `c`, and simultaneously the
  **liveness falsifier** (§7.6.6).
- `S1 − CTL` = 40k + 40c and `S0 − CTL` = 40k + c, reported as consistency checks against the
  two primaries.

#### 7.6.4 The two competing predictions, written down before the data

Using frieren's unchained `k = 0.4478` and `c = −3.76`, against the null `H_c0: c = 0` in which a
command-buffer commit is free:

| contrast | frieren's `c` | `H_c0` (`c = 0`) |
| --- | --- | --- |
| `S1 − CTL` | −132.5 µs/step | +17.9 |
| `S0 − CTL` | +14.2 | +17.9 |
| `N400 − CTL` | +28.7 | +179.1 |
| **`S1 − S0`** | **−146.6** | **0** |
| `N400 − S1` | +161.2 | +161.2 |

The two hypotheses differ by 146.6 µs/step on the primary. Against the in-tree eight-block
half-width of 15.24 µs from §5.6 that is **9.6σ**, and against the six-block 19.13 µs it is
7.7σ, so the session discriminates decisively in either direction. On `c` itself the eight-block
resolution is 15.24/39 = **0.39 M4 µs/layer**, about a ninth of the claimed magnitude.

#### 7.6.5 Design and cost

Eight blocks × four arms = **32 runs**. The rotation in `certify.sh` is `rot = (b−1) % NARM`, so
with `blocks` a multiple of the arm count every arm occupies **each of the four positions exactly
twice** — perfect position balance, which is the property frieren's ladder lacked. At the
staged-A/A rate of ~3.6 min/run including the 40 C thermal gate this is ≈115 min. Rows are
appended per run, so a truncated session still yields whole blocks; I will analyse complete
blocks only.

#### 7.6.6 Pre-committed kill switches

- **Liveness.** `N400 − S1` must be positive and near +161 µs. If its CI covers zero the
  injection is not firing and the **whole session is VOID**, reported as such. This is written
  before the run so it cannot become a post-hoc excuse.
- **Correctness.** All four arms must produce a **single golden hash**; the injected kernels write
  only scratch outputs the model never reads. Any golden divergence means an arm changed
  representation, and a representation change is not a price — session VOID.
- **Prefill null.** `prefill_s_per_token` must be a null across all four arms. A live prefill
  contrast is evidence of a session artefact and downgrades the decode read to indicative.
- **Reporting symmetry.** If `S1 − S0` covers zero at eight blocks while liveness holds, that is a
  positive refutation of `c` at 0.39 µs/layer resolution and the 1.7 %-of-decode story dies. I
  commit now to reporting that outcome with the same prominence as a confirmation.

#### 7.6.7 Known confound, disclosed in advance

`S0` puts all forty empties on layer 0 as independent roots, where `S1` spreads them one per
layer. Every MLX compute encoder is `MTL::DispatchTypeConcurrent`, so forty co-resident no-ops may
overlap more than forty serialised ones. This means `S1 − S0` mixes commit cadence with
dispatch-level parallelism. I expect the mixing to be second-order because at TG=8 each kernel is
2048 threads and `k` is dominated by CPU-side encode, whose count is identical across the two
arms — but it is a real confound and the clean break (a `CHAIN=1` pair, five arms) does not fit
the clock or the rotation. It is a limitation of this session, not of the design.

#### 7.6.8 Sign discipline

`c < 0` means *adding* commits makes decode faster, which is surprising enough to deserve a
pre-committed reading. The plausible mechanism is pipelining: forty small command buffers let the
GPU start on layer 0 while the CPU is still encoding layer 5, where one large buffer serialises
encode ahead of execute. That is a real effect and a real lever, and it is also **not** a licence
to claim 1.7 % is recoverable. Recovery needs a source change that adds commits without adding
work, and the price of that change has to be measured on its own.

---

## 8. Limitations, stated plainly

1. **This round certifies an instrument, not a speedup.** Nothing here moves the shipped tree.
   The deliverable is a CI and the ability to produce more of them (rule 105.7: the CI is the
   deliverable).
2. **The power curve is conditional on the A/A sd being stationary.** It is a projection made
   from one afternoon's thermal history on one host. A campaign run on a hotter machine, or
   with a different background load, will have a different sd and therefore a different block
   requirement. The honest use of the curve is *plan with it, then re-measure*; the analyser
   re-derives the sd from every session it is given, so drift shows up rather than hiding.
3. **`k` is still unresolved between α = 0.4369 and β = 0.5000.** I report every % of `cs`
   number on both bases and headline α, the smaller one, because it is the basis that makes a
   candidate look *worse*. Nothing in this round can close that degeneracy (§3A.1 explains why
   the positive control cannot either — the two hypotheses are only 10 µs apart, well inside my
   resolution).
4. **A/A is the weakest possible null.** It shares a binary, so it cannot detect a bias that
   depends on the *code* differing between arms — for instance a compile-order or
   binary-layout effect. It bounds run-to-run and position noise, which is what the power
   curve needs, and no more than that.
5. **Timings were taken at commit `ff8b0918`.** Later commits on this branch add documentation
   and analysis scripts only; `Sources/` is untouched throughout, which the identity verifier
   confirms independently by showing a single `commit` and a single `weights_hash` across the
   whole session.
6. **P5's "same kernel set" is verified by hashes, not by a kernel list.** The `kernels` column
   of my TSV reads `none` for every row: the harness log does not emit kernel names on this
   path, so my script has nothing to scrape. I am not going to dress that up — the column is
   dead weight and I say so rather than let a reader assume it was checked. What *does* carry
   the identity claim is `verify-identity.sh`, which shows a single `runtime`, `harness_hash`,
   `weights_hash`, `commit` and `checked_steps` across the whole session, and a `golden_hash`
   distribution. Those are strictly stronger than a kernel-name list for the A/A case (they
   pin the binary and the weights), and strictly weaker in one respect: they cannot tell you
   *which* kernels a gated arm actually took. For a gated arm, treat "the arms ran the same
   kernels" as unproven and rely on the `golden_hash` split instead.
7. **The power curve's block counts carry a factor of about `[0.5×, 2.9×]`.** The curve is
   built from an sd estimated at dof 11, block counts scale as `sd²`, and the chi-square CI on
   the sd is wide. This is a separate point from limitation 2: even with a perfectly stationary
   host, a 12-block estimate of the sd is not precise enough to promise a block count. The
   analyser prints the band and instructs the reader to plan with the upper sd; a campaign
   planned from the point sd has roughly even odds of coming in under-powered.
8. **Mid-round publication was not possible.** I hold no GitHub write credential: `gh` is
   unauthenticated, there is no PAT, and `respond_to_human_issue` refuses pull requests. The
   only push channel available to me is `submit_experiment_result`, which is terminal and ends
   the round. So the preregistration in §1 and §3A was committed **locally** before the
   corresponding data existed, in separate commits with their own messages, and the whole chain
   is pushed at once at the end. The commit graph, not a push timestamp, is the evidence that
   the predictions preceded the numbers.
9. **The staged-tree instrument's own sd is known only to dof 5, and one contrast in it is not
   comfortably null.** §6.7 passed all four preregistered predictions, but on six blocks:
   `SC − SB` came in at +6.019 µs/token with `t = 1.889` and 5 of 6 blocks positive. The two
   staged directories are byte-identical by hash before *and* after the runs, so any real
   effect there would be a **placement** bias (directory position, page-cache or filesystem
   locality), not a code difference. I therefore carry +6 µs/token (≈0.04 % of `cs`) as honest
   placement-bias uncertainty rather than claiming zero, and the 2.3× variance advantage of
   staged-vs-staged arms (§5.6) rests on the same dof-5 estimate. A ten-block staged-vs-staged
   A/A would settle both; it was not run because the evening's blocks were reserved for a
   candidate tree that never landed (§7.4).

---

## 9. Conversion audit (19:50Z): one measured dispatch slope prices at 0.12 %, 0.27 % or 0.52 % of `cs`, and the choice decides tonight's only surviving lever

*(§7.7 is reserved for the commit-cadence ladder's results, which do not exist yet. This section
is arithmetic and provenance only: no host time, no new runs, nothing here depends on a row I
have not read. It belongs logically next to §7.5.)*

### 9.1 What arrived while the ladder was running

Two inputs landed within two hours of each other and nobody has yet put them in the same
sentence:

1. **Rule 105.24** (`research/advisor-rule-105-24-concurrency-repricing-and-integration-hazard-map.md`,
   advisor branch `1264d70c`, written ≈16:45Z). MLX creates every compute encoder with
   `MTL::DispatchTypeConcurrent` (`device.cpp:545-548`) and emits `memoryBarrier` only on a true
   read-after-write hazard (`device.cpp:325`, `:363-375`). The advisor's conclusion: the
   dispatches the merge programme would remove are **already free**, five separate nulls collapse
   into one mechanism, and the programme's expected value falls from
   `P(≥1 of 2 draws) = 0.529` to **0.000**. §5 of that document: *"`H_free` does not merely reduce
   the merge programme's value; it makes it numerically zero to four decimal places… There is no
   'small win' branch. This is a binary."*
2. **Frieren's terminal #660** (§7.5): the arm-F slope, measured on M4 tonight, is
   `s = 0.4478` **M4 µs/step per added barrier-free dispatch**, CI95 **[0.4006, 0.4950]**;
   chained `0.465` [0.417, 0.512]; the barrier premium at N = 160 is `−0.096` [−0.213, +0.022].
   Her own headline priced the family-E merge at `40 × 0.4478 = 17.9` M4 µs/step **= 0.20 % of
   decode = 0.15 % of score**, "below the 0.4 % draw bar", verdict `P-INDETERMINATE`.

Both readings point the same way — the lever is dead — and **the second one is a conversion
error in the direction that hides a false negative.** That is worth ten minutes of arithmetic
before the 21:00Z go/no-go.

### 9.2 105.24 contains two conversion formulas that differ by exactly 1.890×

§3 of 105.24:

```
Δ%cs = n × 1.2382 [M4 µs] × k × 0.015228
```

§4 of the same document:

```
Δ%cs = n × s × 1.890 × 0.015228 ,   k = s / 1.2382 ,  s in M4 µs/step
```

The second carries the host transfer `k_dispatch = 1.890` and the first does not, so for any
**measured M4** price the two disagree by 1.890×. §4 is the intended contract, and its own
threshold table proves it: the advisor states that one merge (`n = 40`) needs `s = 0.3475` to
reach 0.4 % of `cs`, and `40 × 0.3475 × 1.890 × 0.015228 = 0.4001 %` reproduces it exactly. Under
§3's formula the same `s` would price at 0.2117 %. §3's table is therefore the `k_host = 1.0`
**floor**, not the contract — and its `k = 1.890` row makes the confusion visible by labelling
rule 65's *M5* number `2.3402` as "µs/dispatch **[M4]**".

105.24 §3's rows, re-run under §4's formula:

| price row | M4 µs/dispatch | §3 as printed, n=40 | §4 formula, n=40 | §4 formula, n=79 |
|---|---|---|---|---|
| #483 measured (`k`=0.0872) | 0.1080 | 0.0658 % | **0.1243 %** | 0.2455 % |
| tanjiro prior (0.2000) | 0.2476 | 0.1508 % | 0.2851 % | 0.5631 % |
| advisor "dead" (0.3000) | 0.3715 | 0.2263 % | 0.4276 % | 0.8446 % |
| **frieren, measured tonight (0.3616)** | **0.4477** | 0.2727 % | **0.5154 %** | **1.0180 %** |
| β (0.5000) | 0.6191 | 0.3771 % | 0.7127 % | 1.4076 % |
| 105.17 floor (1.0000) | 1.2382 | 0.7542 % | 1.4255 % | 2.8153 % |

§3's headline — *"removing every removable dispatch in the step at the measured price is
0.2598 %, which is 1.5× below the 0.4 % draw bar"* — becomes **0.4912 %**, i.e. *above* the bar,
under §4's formula with the same #483 input.

### 9.3 Frieren's measured slope against the advisor's own preregistered thresholds

| threshold (105.24 §4, n = 40) | `s` required | frieren's `s` = 0.4478 [0.4006, 0.4950] |
|---|---|---|
| 0.4 % draw bar | 0.3475 | **clears — the entire CI is above the threshold** |
| +1.0 % arming threshold | 0.8686 | misses |
| `g0` = 1.6359 % coin flip | 1.4210 | misses |

The same slope, priced four ways (point [CI95], % of `cs`):

| host transfer | one merge `n=40` | two merges `n=79` | everything removable `n=158` |
|---|---|---|---|
| α = 0.4369 (bytes) | 0.1192 [0.1066, 0.1317] | 0.2354 [0.2106, 0.2602] | 0.4707 [0.4211, 0.5203] |
| β = 0.5 (latency) | 0.1364 [0.1220, 0.1508] | 0.2694 [0.2410, 0.2977] | 0.5387 [0.4819, 0.5955] |
| **1.0 (105.13(c) conservative floor)** | **0.2728 [0.2440, 0.3015]** | 0.5387 [0.4819, 0.5955] | 1.0774 [0.9639, 1.1910] |
| **1.890 (`k_dispatch`, 105.13(c) point)** | **0.5155 [0.4612, 0.5699]** | **1.0182 [0.9108, 1.1255]** | 2.0363 [1.8217, 2.2510] |

Frieren's reported 0.15 % of score is the top row (my recomputation with α gives 0.1192 %; the
gap to her 0.15 % is a decode-vs-score base difference, not a disagreement about the slope).
**Rule 105.13(d) forbids exactly that choice for this quantity**: dispatch work converts at
`k > 1`, so pricing it with α or β understates it, and 105.13(d) names dispatch-count results
priced on a bare M4 number as *"the one population that can hide a false negative"*. The bar
translation makes the stakes concrete: 0.4 % of `cs` is 60.1 M4 µs/step in the bytes regime but
only **13.9 M4 µs/step in the dispatch regime** — 4.3× easier to clear, in the same units.

### 9.4 Why I will not simply assert 1.890 either

Three reasons the numerator and denominator of `k_dispatch` may not be the same functional, and
the first of them is in 105.24 itself:

1. `k_dispatch = 2.3403 / 1.2382 = 1.890` divides **rule 65's M5** added-dispatch price by
   **rule 57's M4** saturated per-dispatch glue (105.13(c)). 105.24 §2 then reinterprets rule 65
   as having priced *a serialising boundary, not a dispatch* — *"rule 65 already **is** the
   barrier price"*. If that reinterpretation is right, the ratio is a barrier price over a
   dispatch price and is not a host transfer at all. **The document that mandates the constant
   undermines its own derivation of it**, and neither half of the ratio was re-audited when it
   did so.
2. Frieren's M4 barrier-free slope, **0.4478**, is **2.77× below** rule 57's M4 **1.2382** for
   what is nominally the same quantity on the same host class. At most one of those two numbers
   is the marginal price of a barrier-free dispatch.
3. Frieren measured the M4 barrier premium as **−0.096 µs [−0.213, +0.022]** — i.e. *no*
   serialising premium on M4, contradicting 105.24 fact 2's prediction that arm S must exceed
   arm F. The advisor pre-committed that this outcome means *"my source reading is wrong and that
   is the more important finding"*. Taken at face value it also implies a host transfer of
   `2.3403 / 0.465 = 5.03`, which would put one merge at 1.37 % and two at 2.71 %. I record that
   as an arithmetic consequence, **not** as a claim: it compares two probe designs from different
   epochs, and I have not audited rule 65's provenance myself.

So the defensible bracket on the host transfer is **[1.0, 1.890]** — 105.13(c)'s own floor and
point estimate — and everything above 1.890 is unpriced rather than excluded.

### 9.5 What that does to the decision, stated in the advisor's own units

- One family-E merge (`n = 40`) is worth **0.27 %–0.52 % of `cs`**. It **brackets the 0.4 % draw
  bar**; it is not zero to four decimal places under any transfer that 105.13 permits for
  dispatch work.
- Two merges (`n = 79`) are worth **0.54 %–1.02 %**, so the top of the bracket **reaches the
  +1.0 % arming threshold** of 105.21.
- 105.24 §5's `P(≥1 of 2 draws) = 0.0000` rows are all at `k ≤ 0.5`. That is not a statement that
  the lever is free; it is a statement about what an M4 dispatch measurement is worth **if you
  price it with a bytes or latency transfer**. The merge programme is not dead — it is
  **unpriced**, and the unpricing is a factor of `1.890 / 0.4369 = 4.33` sitting in one constant.
- 🪤 **Direction discipline, and it cuts against me.** All of this prices *removal* with an
  *addition* slope (rule 68, which 105.24 reinterprets as a region-membership question rather
  than a direction question), measured with *injected no-op* dispatches rather than real merged
  kernels. #48 remains the monument: it removed dispatches and scored **−0.1488 %**. So
  0.27–0.52 % is an **upper bound on what one merge could pay**, not a prediction of what it will
  pay. It is enough to justify *building* the merge tonight. It is not a certificate, and I am
  not issuing one here.
- 🪤 **The intercept is the other half of frieren's own ladder, and it points the other way.** Her
  *single-rung* read — the total price of the added dispatches divided by their count — is
  **−0.491 µs/dispatch [−0.654, −0.329]**: at N = 160 the added dispatches made decode *faster*,
  because an intercept of ≈−150 µs/step swamps `160 × 0.4478 = +71.6 µs`. The marginal slope is
  the right estimator for removing 40 dispatches from a step that already carries ~408 **only if
  the merge leaves that intercept alone**. If a real merge also removes whatever generates the
  intercept — commits, encoder boundaries; §7.6 is measuring exactly that term — then the sign of
  its payoff is not determined by `s` at all. This is the strongest single reason not to convert
  §9.5's bracket into a promise, and it is why §7.6 was worth the host time.

### 9.6 What my instrument contributes to this, and by when

The ladder that has been running since 19:22Z (§7.6) was preregistered to measure the commit
intercept `c`. Its liveness arm turns out to be an **independent measurement of exactly the
constant this section turns on**:

```
N400 − S1  =  360 · s          (s = M4 µs/step per added barrier-free dispatch)
```

360× leverage, a different instrument, a different tree, a different estimator and a different
operator from frieren's ladder. At 8 blocks my half-width on `360·s` is 15.236 µs, so the
half-width on `s` is **±0.0423 µs/dispatch**, against frieren's ±0.0472 — comparable precision,
fully independent. Preregistered discrimination, written here before any row of that session has
been read:

| if `s` is | `N400 − S1` should be | separation from the others at 8 blocks |
|---|---|---|
| #483's 0.1080 | +38.9 µs | — |
| **frieren's 0.4478** | **+161.2 µs [+144.2, +178.2]** | 8.0 half-widths from #483 |
| rule 57's 1.2382 | +445.8 µs | 18.7 half-widths from frieren |

105.24 §5 calls collapsing `P(H_free)` *"the highest value-of-information figure this campaign has
produced"* (spread 0.529 of a campaign win, 45 minutes of probe). A second, independent collapse
of the same quantity is already on the host and lands ≈21:20Z.

And if frieren's tree does arrive: one merge's **M4** effect at her slope is 17.9 µs/step =
**1.37 half-widths at ten blocks, 2.10 at twenty**. So the *existence* of the merge's effect can
be certified on this instrument without settling the conversion at all — the transfer is needed
only to convert the certified M4 delta into a %-of-`cs` price for the draw decision.

### 9.7 What would change my mind

- **If rule 57's 1.2382 M4 and rule 65's 2.3403 M5 are shown to be the same functional measured
  the same way**, `k_dispatch = 1.890` is a clean transfer, §9.4's caveat dissolves, and the point
  value 0.5155 % for one merge stands as the estimate rather than the top of a bracket.
- **If the ladder returns `N400 − S1 ≈ +39 µs`**, the true price is #483's, one merge is
  0.12–0.24 %, and 105.24's verdict is right — established from my own instrument rather than
  from a source reading, which is the outcome the advisor asked frieren to make possible.
- **If liveness fails** (`N400 − S1` covers zero), §3B re-arms, the ladder is VOID, and nothing in
  §9.6 is claimable — but §9.2–§9.5 are unaffected, because they are arithmetic on numbers that
  are already published.
