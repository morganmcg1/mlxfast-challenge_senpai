# R107-J′ — Characterising and certifying the paired `--local-submit` decode instrument

**Student** maple-nezuko · **PR** #657 · **assignment** `maple-r107-j-qkv-lane-major-packing-replication`
· **revision** `r107-j-rev1` · **base** `fc66172b73a1ffa3bf2d9a4431267c0b922b7b7f`
· **branch** `maple-nezuko/r107-qkv-packing-replication`

Host **Apple M4 Pro**, 20 GPU cores, 48 GiB, MLX cache capped 6 GiB, 40 °C thermal gate.
Epoch **R107**. Unless a line says otherwise, every quantity below is
**host = M4-Pro · epoch = R107 · MARGINAL** (a local paired difference of two arms of
one binary). No number here is a census number and no number here came from a receipt.

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

---

## 5. Results

*(populated after the campaign; §1 was committed before launch)*

---

## 7. Part 2: the certification targets do not exist yet

Part 2 asked me to certify edward's (#629) or alphonse's (#644) candidate, then the sum on the
combined tree, and to report the fact if neither had pushed. Neither has. Checked directly
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
exists to stop anyone assuming.

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
