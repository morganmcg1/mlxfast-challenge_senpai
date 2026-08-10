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
base. fern independently reported 319,792 B, a 998 B disagreement that is consistent with our
two working trees differing by a research file, not by anything submitted. Two agreeing readings
of the binding number is what matters, and both clear.

My own six files add **0 B** to that surface: everything I wrote this round is under
`research/`, which is not in `editablePaths`.

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

### 5.8 What this licenses, and what it does not

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
        BASE:MLXFAST_RUNTIME_WORKER_EXECUTABLE=/tmp/r107j-stage/BASE/mlxfast-runtime-worker \
        CAND:MLXFAST_RUNTIME_WORKER_EXECUTABLE=/tmp/r107j-stage/CAND/mlxfast-runtime-worker

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
There is nothing to certify, so per the brief I am not inventing a target. What I did instead
is spend the freed slot on the positive control of §3A, which serves the same end — it is the
test that converts "here is a power curve" into "here is a power curve I have shown to be
honest at the effect size that matters".

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
