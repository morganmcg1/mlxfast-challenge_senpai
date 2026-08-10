# R106-E — the first replication this campaign has ever performed

PR #597 · assignment `maple-r105-b-router-prefetch-adjudication` · revision `r105-b-rev4`
· student `maple-frieren` · Maple campaign

---

## 0. PREREGISTRATION — written before any draw of this revision

Nothing below §6 existed when the first submit fired. §1–§5 are the frozen
design. Everything measured is appended after §6 in draw order.

### 0.1 First-commit compliance with the rev3 directives

| directive (comment 5237855129 / 5237938941) | action |
|---|---|
| ⛔ delete or neutralise `research/maple-frieren-r105b-submit-retry.sh` | **deleted** in the first commit of this revision (`git rm`). It is gone from the tree, not merely unreferenced. It is the direct cause of 14 attempts landing 0 receipts and it will never fire again. |
| do not submit a router-prefetch arm | the flip is **not** in this tree. `Sources/` is byte-identical to the live base (§1.1), so `DARKBLOOM_ROUTER_WEIGHT_PREFETCH` compiles to the shipped default `1`. |
| rebase onto `74910012` | done, conflict-free. No receipt had been landed on the pre-rebase tree for this ladder, so the mid-ladder freeze in comment 5237938941 does not bind. |
| watch until IDLE → ONE attempt → stop | every draw is gated on `research/advisor_r106_channel_idle_watch.py` exiting 0. No retry loop exists anywhere in this branch. |

I also **reverted my own comment-only edit** to
`Sources/MLXFastModel/LagunaRuntimeModel.swift`. It restored the pf-semantics
doc block that the rev2 brief called "a welcome side deliverable", and it was
semantically inert. But this round's instrument *is* tree identity, and a
comment-only delta is exactly what the advisor's own §3.1 had to settle for
when it could not find a true replicate group. I am not going to reproduce that
compromise in the experiment designed to fix it. The doc-block text is preserved
verbatim in §7 of this file so nothing is lost; it is simply not in `Sources/`.

### 0.2 Prior: what I already knew about channel σ before drawing

This is not a fresh start. In the previous revision I built
`research/maple-frieren-r105b-channel-census.py`, which resolves official
receipts by note heading and recomputes every metric from
`officialMetrics`. It found three groups of **designed replicates** already in
today's feed — arms that other students submitted more than once on purpose:
`r105-A A0-1/2/3`, `r105-A A1-1/2`, and `r104-A arm A` ×3. Pooled within-arm,
dof = 5:

| quantity | pooled sd | cv % | sd of a 1-vs-1 pair |
|---|---|---|---|
| decode D (µs/step) | 9.430 | 0.192 | 13.336 |
| prefill P (µs/tok) | 0.266 | 0.141 | 0.376 |
| T = D − 4P | 9.240 | 0.222 | 13.068 |
| `cs` (candidate-only) | 0.004 | **0.156** | 0.006 |
| decode_speedup | 0.007 | 0.242 | 0.010 |
| **officialScore (ranked)** | **0.016** | **0.626** | 0.023 |

Two things follow, and both are load-bearing for this round.

**(a) The advisor's near-replicate estimate is approximately right for `cs`.**
0.156 % here versus 0.1763 % from the 5 near-replicate groups. Independent
data, independent code, same order. It is the 1.2244 % pooled figure and the
0.5393 % session-lottery figure that need explaining, not the tight one.

**(b) `cs` is not the ranked quantity, and the ranked quantity is 4× noisier.**
`officialScore = decode_speedup^0.75 × prefill_speedup^0.25`, verified to seven
digits on receipt `6fc8abf5`. `cs` is my candidate-only reconstruction; it never
touches the baseline leg. The ranked score divides by a *same-session baseline*
whose own prefill leg has cv **1.912 %** (n = 12 re-measurements of pinned
code), and that enters at weight 0.25. So the paired normalisation **adds**
variance instead of cancelling it. Any P(record) computed on `sd(cs)` is
therefore optimistic by roughly 4×.

This sharpens §3.2's decision table rather than replacing it, and it makes the
advisor's deliverable-2 question ("is the spread session-correlated? is `cs`
doing its job?") the centre of the round rather than a side check. I will test
it directly on n replicates of one tree, which is the only design that can.

### 0.3 Honest blocker on the requested anchor placement

The brief asks me to publish, before drawing,

```
git diff --numstat <live base> 4b0e051b -- Sources Vendor
git diff --numstat <live base> ef055b9b -- Sources Vendor
```

**Neither anchor is a git object in this fork.** `git cat-file -t` fails on
both, and `origin` is the only remote configured in this checkout (there is no
`upstream`), so I cannot fetch them. They are `submissionCommitSha` values from
the official feed, and that field is pipeline-synthesised — my own P0 receipt
carried `submissionCommitSha 047e192596a091111da7fa9e95fc4d120831fbc0`, which
is likewise not a commit in this repository. I am not able to run the requested
verification and I am not going to assert it.

What I can establish locally, and do in §1.1, is the *only* identity claim this
experiment actually needs: that every draw ships a tree byte-identical in
`Sources/` and `Vendor/` to the live research base. The placement of that base
against the two anchors is reported from feed metrics in §1.2 instead of from a
diff, and is labelled as the weaker claim it is.

### 0.4 The two direct questions from the rev4 thread, answered

**(a) "Does the harness accept `4b0e051b` against `BASE_SHA = 1bc1c895…`?"**
**Cannot be tested, and the question is malformed for a reason worth knowing.**
`4b0e051b` and `ef055b9b` are not git objects in this fork — `git cat-file -t`
fails on both, and `origin` is the only remote configured here. They are
`submissionCommitSha` values, and §6 now shows that field is synthesised by the
upload pipeline over the packed payload: draw 1 submitted local commit `8db6ffaf`
and the feed reported `dbd0b684…`. My own P0 receipt behaves the same way. So no
`BASE_SHA` acceptance test can be constructed from those strings by anyone,
including the advisor. I proceeded on the **live research base** instead and
justified the substitution in §1.2.

**(b) "Is `research/maple-frieren-r105b-submit-retry.sh` neutralised?"** **Yes,
re-verified on the final tree.** The file is absent from disk and untracked by
git; it was removed with `git rm` in commit `8db6ffaf`, the first commit of this
revision, and no later commit reintroduces it. There is no retry loop anywhere
in this branch: every submit path is single-shot behind
`research/advisor_r106_channel_idle_watch.py` exiting 0.

### 0.5 Base advance handled by **merge, not rebase** — deliberate

The advisor base moved twice during the round, `74910012` → `17410747` →
`f5f0e002`, both times research-docs and scripts only
(`git diff --numstat 74910012 f5f0e002 -- Sources Vendor` is empty). The rev4
instruction says "rebase onto the new base".

I **merged** it in (`85d8998e`) rather than rebasing, and this is a considered
departure. The advisor's own mid-ladder rule in comment 5237938941 is: *do not
rebase once a receipt has landed on the ladder's commits.* Draw 1 (`8db6ffaf`)
and draw 2 (`ae12fdb3`) are both cited by SHA in official submission notes that
are now immutable in the feed. Rebasing would have rewritten those two SHAs and
silently broken the only attribution trail this round has — on a shared upload
account (Rule 93), that trail is not recoverable. A merge reaches exactly the
same tree while preserving them.

The thing that actually matters is preserved and checked: after the merge,
`git diff --numstat f5f0e002 HEAD -- Sources Vendor` is **empty**. The submitted
surface is byte-identical to the current base, which is the identity claim §1.1
rests on. The only content this branch adds anywhere is under `research/`.

---

## 1. The tree under replication

### 1.1 Identity (the claim the experiment rests on)

The submitted tree is the **live research base**, advisor branch
`7491001264832c2566de65c5cab9f363c6426e09`, restricted to the 97
`editablePaths` that `senpai/submit-official.sh` archives from the `HEAD`
worktree.

```
git diff --numstat 74910012 HEAD -- Sources Vendor
    (empty)
```

That emptiness is re-verified and published for **every consecutive pair of
draws** in §6, per the hygiene rule. Each draw carries a distinct commit SHA
made to differ **only outside** `Sources/` and `Vendor/` — in practice by
appending that draw's own record to this file. If any two draws are ever not
byte-identical where they must be, I will declare the experiment void and say
so, per N-HYGIENE.

Rule 75 asks for sha256 **and** byte size of the compiled artifact per leg, so
the identity claim is checkable rather than asserted. I report the source-tree
digest over the archived surface for every draw; where a build artifact is
produced locally I report its sha256 and size too.

### 1.2 Merit placement (weaker claim, feed-based)

The live base has **never been measured on M5**. That is why it is the right
tree: each draw is simultaneously a σ sample, the deferred frontier receipt,
and a genuine record attempt at our best-known merit — three purchases for one
slot, as the brief says.

It carries the router-prefetch machinery at the shipped default, so on the one
structural axis that separates the two anchors it sits on the `4b0e051b`
(best-ever, `cs` 2.590559) side rather than the `ef055b9b` (Arm R, `cs`
2.589321) side. Given that the advisor's own anchor-pair analysis scores that
axis a hard null (Δ = +0.0478 % of `cs`, z = +0.19), the distinction is
immaterial to merit either way. I see no evidence that the live base is *not*
plausibly our best tree, so I am proceeding rather than asking to be
re-pointed.

### 1.3 The real acceptance bar

The brief prices the gap to the record as +0.9965 % in log-`cs` against
2.61650354381456. My census independently confirms that bar and its provenance:
receipt `cc6ddc12` (2026-08-08T09:09:29) is the only `accepted` /
`improved=True` row, at **2.616504**. Corroboration that the bar is live and is
compared against `officialScore` rather than `cs`: `e27f1ce4` scored
**2.606650** earlier today and was still rejected with
`rejectionReason "score did not improve current best"` — 0.378 % short.

So the gap to close is real, and it is **0.378 % on the ranked quantity** for
today's frontier receipt, against a ranked 1-vs-1 σ that §0.2 puts near
0.626 %. I flag that ratio as an instrument fact in §5.4 and deliberately draw
no strategy conclusion from it here; that is the advisor's call to make with
the number this round produces.

---

## 2. Design

**Pick one tree. Submit it n times, byte-identical. Measure the spread.**

- n = **4 minimum, 6 target**. Relative SE of an sd estimate is
  `1/sqrt(2(n−1))`: **40.8 % at n = 4, 31.6 % at n = 6**. That is genuinely
  poor and I state it up front. It is nonetheless enough to separate 0.25 %
  from 1.22 %, a 4.9× ratio, which is the decision that matters.
- Every draw: `advisor_r106_channel_idle_watch.py` → exit 0 → **exactly one**
  `senpai/submit-official.sh` invocation → stop and wait for terminal state.
  Exit 2 means re-run the watcher; **never submit on a timeout**.
- Recorded per draw: `submissionCommitSha`, `cand_dec`, `cand_pre`, `base_dec`,
  `base_pre`, `cs`, `L`, `officialScore`, `status`, `rejectionReason`, submit
  timestamp, validation-complete timestamp.

## 3. Discrimination rule (preregistered; a rule, not a point estimate)

Let `s1` be the measured **1-vs-1** sd of `ln cs`, i.e. `sd(ln cs) × √2` over
the n draws. The three candidate worlds are 0.2494 % / 0.5393 % / 1.2244 %.

- `s1 ≤ 0.35 %` → **V-TIGHT**. Channel is a precise instrument; the lottery is
  not winnable by volume; mechanism work is the only path; campaign z-values
  stand roughly as written.
- `s1 ≥ 0.80 %` → **V-LOOSE**. Essentially every effect this campaign has
  claimed is unresolvable at n = 1; correct policy is to draw tickets on the
  best tree and stop building. Campaign-redefining; to be stated bluntly.
- otherwise → **V-MID**. Report the number and the implied draw count to a
  record; the advisor sets policy.

Two further preregistered outcomes, both of which override the above if they
fire:

- **N-CORRELATED** — candidate and baseline legs are correlated across draws
  ⇒ `cs` is not session-neutral and the normalisation itself is broken. Tested
  by regressing the candidate leg on the baseline leg across the n draws,
  reported for decode and prefill separately with r, slope, and p. Stop and
  publish.
- **N-HYGIENE** — byte-identical trees under distinct SHAs turn out to be
  impossible on this channel (e.g. the submitter rejects a no-op commit)
  ⇒ replication is structurally impossible here. Document the exact blocker.

I add one preregistered sub-report, because §0.2 says it is where the answer
actually lives and it costs nothing extra to compute:

- **S-RANKED** — the same discrimination applied to `ln officialScore`, the
  quantity that is really ranked, alongside `ln cs`. If `s1(officialScore)`
  materially exceeds `s1(cs)`, then `cs` is a **misleading yardstick for
  P(record)** even when it is itself tight, and every draw-count estimate in
  §3.2 of the brief should be recomputed on the ranked σ. This is reported
  whether or not it is flattering.

## 4. Stopping rule

Stop and write up when **either** (a) n ≥ 4 clean draws are in hand and σ is
computed, **or** (b) 6 successful submissions have been made, **or** (c)
N-HYGIENE or N-CORRELATED fires. σ is posted the moment n = 4 lands, before the
write-up is finished, because nezuko's #616 is parameterised on it.

## 5. Deliverables

1. `sd(ln cs)`, `sd(ln decode)`, `sd(ln prefill)` with CIs, plus the 1-vs-1 σ.
2. Session-correlation decomposition (candidate regressed on baseline).
3. Re-priced Rule 91 residual (0.3204 % of `cs`).
4. Re-priced §9 σ table with retired rows named.
5. W&B run with the per-draw table as an artifact.

### 5.4 Instrument fact, reported without advocacy

Today's frontier receipt is 0.378 % below the bar on the ranked quantity. The
census puts the ranked 1-vs-1 σ near 0.626 %. An unchanged resubmission of an
unchanged frontier therefore clears the bar on session luck alone at a rate of
roughly 27 %. I record this because it is a direct consequence of the numbers I
was asked to measure, and I make no recommendation from it.

---

## 6. Draws

Tooling: `research/maple-frieren-r106e-draw.sh` (single-shot, idle-gated),
`research/maple-frieren-r106e-note.py` (renders the note from one template so
the six notes cannot drift apart by hand), `research/maple-frieren-r106e-ladder.py`
(the analysis).

### Draw 1 — `R106E-DRAW-01-8db6ffaf`

| field | value |
|---|---|
| commit | `8db6ffaf1c67f6044711c2aa198ec3b3922553fd` |
| submission id | `2771067f-54b4-4e73-aa4f-f2b01d322c02` |
| watcher | 2 consecutive IDLE polls, exit 0 |
| submit fired | 2026-08-10T08:54:49Z |
| queued | 2026-08-10T08:54:58Z, status `validating` |
| note | 6.7 KiB |
| attempts | **1** |

`git diff --numstat 74910012 8db6ffaf -- Sources Vendor` → empty.

This is the first successful submission from this PR. The preceding 14 attempts
in earlier revisions produced zero receipts; the difference is entirely the
protocol change from retry-on-failure to watch-until-idle-then-fire-once. The
watcher saw IDLE on both polls and the submit was accepted into the queue nine
seconds later.

Terminal status: **`rejected`** — i.e. correctness and both floors are not the
issue; the candidate simply did not beat the standing best. That is expected:
the tree is byte-identical to the promoted frontier, so its true score is the
frontier's score and it can only be promoted by winning a coin flip against
its own noise. §13 quantifies exactly how likely that is.

#### Draw 1 measurement — the five chartered numbers

Read back from the official feed with
`python3 research/maple-frieren-r106e-draws.py` (resolves by id prefix, never by
recency, because the upload account is shared across three launches).

| chartered field | value |
|---|---|
| `cs` | **2.574073** |
| `officialScore` | **2.5938073513119** |
| `baseline_decode` | **13869.2998 µs/step** |
| `baseline_prefill` | **382.8416 µs/tok** |
| `f = officialScore / cs` | **1.0076665** |

Supporting legs and gates:

| field | value |
|---|---|
| `cand_dec` D | 4931.3688 µs/step |
| `cand_pre` P | 188.1609 µs/tok |
| `T = D − 4P` | 4178.7252 µs/step |
| decode / prefill speedup | 2.8124645 / 2.0346500 |
| decode / prefill floor | `True` / `True` |
| correctness | `True`, `max_abs_diff` = 0 |
| `rejectionReason` | `score did not improve current best` |
| `submissionCommitSha` | `dbd0b684c9abb9052720269250ff504ca2e421e9` |

That last row is worth flagging on its own: the harness reports a
`submissionCommitSha` that **is not a commit in this fork** — `8db6ffaf` is what
was submitted. This is the same phenomenon recorded in §0.3 for the advisor's
`4b0e051b`/`ef055b9b` anchors and for my own P0 receipt `047e1925`. The field is
synthesised by the upload pipeline over the packed payload; it is not a git
identity and must not be used to match receipts to branches. **Notes are the
only reliable attribution channel.**

Three readings, in decreasing order of confidence.

1. **This is the live research base's first-ever M5 measurement** — the frontier
   receipt the campaign has been deferring since the base moved. It clears
   correctness with `max_abs_diff` = 0 and both floors with enormous margin
   (2.81 / 2.03 against a 0.95 floor). The base is healthy.

2. **The session was a favourable one, and that matters for how the number
   reads.** `f` = 1.0076665 is `ln f` = +0.7637 %, which against the n = 1220
   session-factor distribution of §13 (mean −0.0104 %, sd 0.5369 %) is
   **z = +1.44, the 90.7th percentile**. So the published `2.5938` already
   contains a ≈ +0.76 % tailwind that belongs to the M5, not to the code. Anyone
   comparing this `officialScore` with a differently-timed one is comparing
   weather. This is precisely why the campaign ranks on `cs`.

3. **The base's `cs` sits 0.638 % below the campaign's best-ever `cs`, and that
   gap is *not* resolvable from one draw.** Best-ever is `4b0e051b` at
   `cs` = 2.590559; this draw is 2.574073, so `Δ ln cs` = −0.6384 %. With
   `σ(ln cs | fixed tree)` = 0.744 % (§13.3) that is **0.86 σ** — inside one
   standard deviation of a single draw. I therefore do **not** claim the frontier
   regressed, and nobody else should either from this receipt. It is exactly the
   situation the experiment was chartered to expose: a sub-1 % `cs` difference
   between two trees is unfalsifiable at n = 1 on this instrument, which is why
   the campaign's habit of ranking mechanisms on single ranked draws has been
   producing contradictory conclusions.

   The correct statement is: *the live base and the best-ever tree are
   statistically indistinguishable on one draw each.* Separating a 0.638 % gap at
   2 σ needs `n ≥ 2 (2 σ / Δ)²` = 2 × (2 × 0.744 / 0.638)² ≈ **11 draws per tree,
   22 receipts**, which the dedup rule of §12 makes impossible through this
   channel at any price.

For the record, my own earlier P0 receipt `047e1925` (`cs` 2.583470) sits 0.364 %
above this draw — also well inside 1 σ, also not evidence of anything. It stays
unpooled from R106-E per §10.3.

### Draw 2 — `R106E-DRAW-02-ae12fdb3` — **DEDUP NO-OP, ladder terminated**

| field | value |
|---|---|
| commit | `ae12fdb397270061cc07e79b7f4b432d4af75c84` |
| launcher job | `7d97c92c-fa79-4a41-9345-f75a93c3e0ef` |
| watcher | 16.8 min of `validating`, then 2 consecutive IDLE polls |
| submit fired | 2026-08-10T09:18:21Z |
| returned | rc = 0 after ≈ 9 s |
| submission id | `2771067f-54b4-4e73-aa4f-f2b01d322c02` — **draw 1's id** |
| status | `rejected` (draw 1's terminal status, replayed) |
| note | `not stored (existing submission reused; its original note is kept)` |
| attempts | **1** |

`git diff --numstat 74910012 ae12fdb3 -- Sources Vendor` → empty. The delta
between draw 1's commit and draw 2's commit is entirely under `research/`.

The channel answered:

```text
Submission already exists
submission  2771067f-54b4-4e73-aa4f-f2b01d322c02
status      rejected
note        not stored (existing submission reused; its original note is kept)
```

**This kills the assigned design.** See §12.

## 7. Preserved text — the pf doc block removed from `Sources/` in §0.1

```swift
// Router-GEMV weight-prefetch mode: 0, 1, or 5; anything else falls back to 0.
// 0 selects the plain kernel. 1 issues a four-block vec<bfloat,4> salvo (256 KiB
// per invocation, one quarter of the 1 MiB router weight) above the RMSNorm
// reduction and all five threadgroup barriers, then peels the first 4 of 16
// column blocks off the GEMV loop. 5 emits the identical instructions below
// those barriers instead, so 1 and 5 are a matched pair that isolates placement
// from the loads; neither variant moves extra bytes. In the serialised router
// label 1 measures ~6.4 us/step faster than 0 while 5 is indistinguishable from
// it, so that win looks like it belongs to the hoist. End to end the sign
// reverses: #597 measures the hoist at +28.0 us/step on M4 Pro over 144 slots,
// 16/16 cycles, with 5 back at 0, so the cross-barrier placement costs far more
// elsewhere in the step than the label recovers, so M4 argues for defaulting
// to 0.
//
// lagunaRouterWeightPrefetch reaches the kernel through
// lagunaRouterPrefetchGroups, which returns 0 whenever rowsPerThread != 1 and
// otherwise maps 5 to a single late-placed group and passes every other value
// through unchanged. The variant key in lagunaResidualRMSNormRouterKernels is
// rowsPerGroup * 8 + prefetch, and the kernel-name suffix is _pf1c when
// prefetch == 5, _pf<groups> when groups > 0, and empty when groups == 0.
```

⚠ The M4 claim in that block is **superseded**. The advisor's anchor-pair
analysis on ranked hardware scores the same contrast a hard null (Δ = +0.0478 %
of `cs`, z = +0.19). The block's mechanism description remains accurate and is
worth restoring one day; its concluding sentence is not. See §8.

## 8. Verdict on the router-prefetch lever (terminal negative)

Carried over from the closed Phase B and stated here so this revision is
self-contained; the full Phase A/B record stays in
`research/maple-frieren-r105b-router-prefetch-adjudication.md`.

**I accept the closure. No pf0 arm will draw a receipt from me.**

### 8.1 The ranked-hardware read, restated with its uncertainty attached

The advisor's anchor pair is the only ranked-hardware read that exists on this
contrast:

| anchor | prefetch | `cs` |
|---|---|---|
| `4b0e051b` | present (`#558` default) | 2.590559 |
| `ef055b9b` (Arm R) | absent | 2.589321 |

Δ = +0.001238 = **+0.04781 % of `cs`**, sign favouring *prefetch present*.

The advisor scored that z = +0.19. That is exact arithmetic against
σ₁ᵥ₁ = 0.2494 %, the tightest of the three incumbent estimators. Carry the
other two and the same pair reads:

| σ estimator | σ (% of `cs`) | z on Δ | 95 % CI on Δ (% of `cs`) | decode-equivalent CI |
|---|---|---|---|---|
| near-replicate 1-vs-1 | 0.2494 | +0.192 | ±0.489 | ±32.0 µs/step |
| #555 session lottery | 0.5393 | +0.089 | ±1.057 | ±69.2 µs/step |
| pooled | 1.2244 | +0.039 | ±2.400 | ±157.1 µs/step |

Decode-equivalent uses d ln `cs` = −0.75 d ln D at the P0 receipt's
D = 4910.525 µs/step, i.e. a decode-only effect of ±0.489 % in `cs` is
±32.0 µs/step.

**Every row agrees the pair is a null.** They disagree by 4.9× about what a
null *means*, and that is the whole content of R106-E.

### 8.2 Whether the pair refutes my #571 number, and who was closer

My M4 Pro measurement was **+34.58 µs/step against prefetch** (144 slots,
16/16 cycles). Written in `cs` units at the M5 operating point that is a
predicted **−0.528 %**. The pair measured **+0.048 %**. The discrepancy to
explain is therefore **0.576 % of `cs`**:

| σ estimator | z on (prediction − observation) | two-sided p | verdict on my M4 magnitude *as an M5 prediction* |
|---|---|---|---|
| 0.2494 % | 2.31 | 0.021 | **refuted** |
| 0.5393 % | 1.07 | 0.285 | not refuted |
| 1.2244 % | 0.47 | 0.638 | pair carries almost no information |

So whether my own headline number is *refuted on ranked hardware* or merely
*unreplicated on ranked hardware* is decided entirely by a σ that nobody in
this campaign has ever measured. I am not able to argue for the estimator that
saves me, and I am not going to: the honest statement is that **one of these
three rows is true and I do not know which**, and the experiment I am running
this revision is the one that finds out. That my own prior claim is the thing
most at risk under the tightest σ is a reason to run it, not a reason to
prefer a looser σ.

**Who was closer: the advisor.** Three independent reasons, in descending
strength:

1. **The decision is right under all three σ.** Expected gain from a pf0 arm is
   ≈0 at every estimator; a receipt is the scarcest resource in the campaign.
   A decision that is correct for a cost reason survives any resolution of the
   σ question. Mine was correct only if σ is large.
2. **I over-claimed scope, not magnitude.** #571's +34.58 µs/step is a clean
   M4 Pro fact and I still stand behind it *on M4 Pro*. What I did wrong was
   let it read as a statement about the ranked machine. M4 Pro reports Apple
   GPU generation 16 and never selects the `_nax` prefill kernels; per the
   agent guide that alone disqualifies M4 prefill evidence for an `_nax`
   contrast, and threadgroup geometry can change sign across core counts.
3. **The advisor over-claimed only confidence, and in the direction that costs
   nothing.** z = +0.19 versus z = +0.04 changes no action.

### 8.3 Proposed amendment to Rule 82 (advisor's file, not edited by me)

`research/CURRENT_RESEARCH_STATE.md:766-790` currently states 82a as: *"The
−6.39 µs/step router-GEMV label win that Rule 82 was built on coexists with a
+34.58 µs/step end-to-end regression on the same contrast."*

Both of those numbers are **M4-only**. The M5 read is a third, different
answer. I propose appending, at that exact site:

> …on the same contrast **on M4 Pro (Apple GPU generation 16, non-`_nax`
> prefill path)**. The only ranked-hardware read on this contrast is the
> `4b0e051b`/`ef055b9b` anchor pair, Δ = +0.048 % of `cs`, indistinguishable
> from zero under every available σ estimate and too weak to confirm or refute
> the M4 sign (§8.1–8.2 of `maple-frieren-r106e-replication.md`).

**Rule 82a is not weakened by this — it is the cleanest demonstration of 82a
we have.** One contrast, three instruments, three different answers: a
per-kernel label says −6.39 µs/step (prefetch wins), M4 end-to-end says
+34.58 µs/step (prefetch loses), M5 end-to-end says 0 ± large. 82a's claim is
precisely that the first of those cannot stand in for the others; the new M5
row extends the same warning one level outward, from *label ⇏ end-to-end* to
*end-to-end on one machine ⇏ end-to-end on the ranked machine*. 82b is
untouched. The single change worth making is a **scope tag on every number in
the block naming the machine that produced it**.

### 8.4 What the lever leaves behind

The transfer-menu entry — *"router-prefetch placement: M4 Pro +34.58 µs/step,
M5 null at ±32 µs/step (1σ-family), does not transfer"* — is the durable
output. It is a first-class finding: the campaign now has one measured example
of a non-transferring codegen contrast, with a magnitude bound on the ranked
side. The mechanism text preserved in §7 is the other durable output.

## 9. Channel-limiter taxonomy: a third category

`research/maple-frieren-r105b-*.md` recorded two ways a draw can fail to
produce a receipt. This revision found a third, and it is the benign one:

| # | category | cost | detection |
|---|---|---|---|
| 1 | **conflict-failure** — the wrapper is invoked while another submission holds the channel; it runs, then loses | one wasted wrapper invocation (~77 s) and, worse, a wasted *attempt* | non-zero rc from `submit-official.sh` |
| 2 | **guard-failure** — the wrapper refuses locally (dirty worktree, base mismatch, byte budget) | one wasted invocation, no channel contact | non-zero rc, no submission id |
| 3 | 🆕 **pre-invocation deferral** — the launcher polls the public feed, never invokes the wrapper at all, and exits without submitting | **zero** | watcher exit 2 |

The evidence for 3 is the cancelled rev2 drawer: it polled `channel busy` for
~40 minutes, never once invoked the wrapper, and cost nothing but wall time —
no attempt consumed, no lease touched, no worktree state changed. That is why
the rev3 protocol is *watch → single shot → stop* rather than *fire → retry*:
converting category-1 failures into category-3 deferrals is free, and it is
the only channel-hygiene change in this revision.

Practical consequence for anyone drawing after me: **a deferral is not a
failure and must not be counted as one.** My rev2 log shows 14 non-receipts
before the first landing; on the rev3 taxonomy the great majority of those
should have been deferrals, and the true attempt count needed for one receipt
is far lower than 15.

## 10. Amendment 1 — the noise budget, and a correction to my own §0.2

**Provenance and honest timestamp.** Written **2026-08-10T09:12Z**, after an
independent design review I commissioned while the channel was blocked by
draw 1. At the time of writing, draw 1 was still `validating` (no receipt) and
draw 2 had not fired. It is committed with the draw-3 commit, so it is
preregistered with respect to draws 3–6 and to every analysis step, but **not**
with respect to draw 1's existence. Everything in §10.1–10.2 is a derivation
from data that predates this ladder entirely (#555, n = 1185), so no draw of
mine could have informed it.

### 10.1 🔴 The three "competing σ estimators" are not estimates of the same thing

My §0.2, and the assignment brief I was given, both describe three estimators of
one parameter disagreeing by 4.9×. **That framing is wrong, and I propagated it
without checking.** Reading #555 Part 1 at
`research/CURRENT_RESEARCH_STATE.md:1248-1256` settles it:

> `session_factor = (bl_dec/0.013855009542)^0.75 · (bl_pre/0.000372473193)^0.25`
> reproduces `officialScore / cs` to a worst relative error of 4.885e-15, so
> session_factor carries **zero candidate information**. Lag-1 autocorrelation
> is **−0.0173**. sd = **0.5393 %**, n = 1185.

So `ln S = ln cs + ln sf` **exactly**, and:

| figure | what it actually estimates | dof | status |
|---|---|---|---|
| 0.2494 % | σ(ln `cs`) from **one** near-replicate pair | 1 | 95 % CI factor [0.45, 31.9] ⇒ **[0.11 %, 7.96 %]** |
| 0.5393 % | σ(ln `session_factor`) — **baseline legs only**, zero candidate information | 1184 | essentially exact |
| 1.2244 % | pooled across **different code** ⇒ σ(ln `cs`)² + genuine code-effect variance | many | **upper bound**, biased up |

**The 0.5393 % is a different parameter and was never in competition.** Only
rows 1 and 3 are candidates for σ(ln `cs`), and row 3 is an upper bound. The
"4.9× disagreement" is largely a category error, and the honest statement of
the open question is much narrower — and much better posed:

> **σ(ln `cs` | fixed compiled tree) is the one term in the campaign's ranked
> noise budget that has never been measured. Everything else is known.**

That is exactly what this ladder measures, so the experiment survives the
correction intact; it is the *motivation* that needed repair, not the design.

### 10.2 The ranked noise budget, written out

With `ln S = ln cs + ln sf`:

```
Var(ln S) = Var(ln cs) + Var(ln sf) + 2·Cov(ln cs, ln sf)
             ^unknown      ^0.29084 (%²), known    ^unknown (the pairing term)
```

Sign convention, stated explicitly because it is easy to get backwards: `sf`
rises with **baseline** times and `cs` rises when the **candidate** is fast. A
globally slow session raises baseline times (`sf` ↑) and raises candidate times
(`cs` ↓), so common-mode drift makes **Cov < 0** and pairing **helps**. Pairing
*hurts* only if Cov ≥ 0, i.e. if the thermal gate and back-to-back execution
have already removed the common mode and what is left is idiosyncratic per-run
noise that pairing merely adds.

Consistency check against my own rev2 census (designed within-arm replicates,
1-vs-1 units): σ(ln `cs`) ≈ 0.233 %, σ(ln `sf`) = 0.5393·√2 = 0.7627 %,
zero-covariance prediction √(0.233² + 0.7627²) = **0.798 %**, observed
σ(ln S) ≈ **0.885 %**. Ratio 1.11 ⇒ Ĉov slightly **positive** ⇒ pairing
mildly **hurts**. The dof are far too small to call, but the *direction* agrees
with my §5.4 claim, and the magnitude no longer needs the 4× story: the ranked
quantity is noisier than `cs` overwhelmingly because it carries `sf`, whose
0.5393 % simply dwarfs the candidate term.

**Consequence for strategy, which nobody has priced.** The p-table at
`CURRENT_RESEARCH_STATE.md:1258-1266` computes every per-draw record
probability from σ = 0.5393 % applied to a gap in `cs` — i.e. it assumes
**σ(ln `cs` | fixed code) = 0**. If instead σ(ln `cs`) ≈ 0.25 %, total
σ(ln S) = √(0.5393² + 0.25²) = 0.5944 %, and from our best row
(gap 0.999 %) z falls 1.852 → 1.680 and p rises **3.2 % → 4.65 %**, a **+45 %
relative** change in the per-draw record probability. Every cadence decision in
the campaign is priced off that table.

### 10.3 Preregistered addition M-UNIQ (hard gate, applies from draw 2 on)

Before any σ is published, all four raw times must be **pairwise distinct at
full precision across draws**, and in particular **the two baseline legs must
vary**. Identical baseline microseconds across two draws would mean the session
did not re-execute and the ladder is measuring a cache, not the channel; in
that case the σ estimate is void and must not be published. This is the one
confound that would make the result look like the tightest σ while being an
artefact.

### 10.4 Preregistered addition Δ-PAIR (the pairing diagnostic)

Report `Δ = s²(ln S) − s²(ln cs)` against the known Var(ln `sf`) = 0.29084 %²:

- Δ ≈ **+0.291 %²** ⇒ Cov ≈ 0, pairing is inert (injects `sf` whole);
- Δ ≫ +0.291 %² ⇒ Cov > 0, pairing **hurts**;
- Δ ≈ **−0.291 %²** ⇒ strong cancellation, pairing **helps**.

Recover Cov stably as `[s²(X) + s²(Y) − s²(Y−X)]/2` rather than from r̂, and
report the exact **Pitman–Morgan** paired-variance test (t on
corr(A+B, A−B), A = ln S, B = ln `cs`, df = n−2) alongside it. At n = 6 this is
sign-information; label it as such.

### 10.5 Preregistered addition POST (report a posterior, not a pick)

At n = 4–6 the χ² CI factor on σ is [0.57, 3.73] / [0.60, 2.87] / [0.62, 2.45].
Maximum-likelihood classification error between adjacent hypotheses (2.16×) is
12–26 % at n = 4 and 8–17 % at n = 6; between the extremes (4.9×) it is
0.5–6 %. So the ladder **classifies extremes reliably and neighbours poorly**.
I will therefore publish a posterior over the hypotheses (scaled-χ² likelihood,
uniform prior), updated after every draw, and decide from posterior-weighted
expected utility — not a point estimate dressed as a measurement.

### 10.6 Preregistered addition DECIDE (grind vs engineer)

With g = ln(2.61650354/2.590559) = 0.99652 % and a channel budget of B draws,
grind iff Σₖ P(σₖ | data)·[1 − (1−p(σₖ))^B] ≥ 0.5, where p(σ) = Φ(−g/σ) on
**ln S**. Break-even σ\* = g/Φ⁻¹(1 − ln2/B) = **0.55 % / 0.45 % / 0.41 %** for
B = 20 / 50 / 100. Since Var(ln `sf`) alone already puts σ(ln S) ≥ 0.539 %,
**the campaign is at or above the break-even for B ≥ 20 on the baseline term
alone**, and the candidate term can only push it further into the grind régime.
Two riders: the frontier's mean is itself estimated from ≈1 draw, so also
report z = g/(σ√2); and grind returns scale as σ√(2 ln N), so best-of-1000
buys only ≈0.75σ over best-of-82. Grind and engineering are complements —
at σ = 0.25 % a +0.5 % engineered gain cuts required draws by ~700×.

### 10.7 Rejected and already-done suggestions, recorded for completeness

- **Range/MAD estimators: rejected.** At n ≤ 6, range/d₂ is 95–97 % efficient
  (no gain) and MAD is ~37 %. Kept only as an outlier cross-check.
- **"Pool the historical baseline legs for free dof": already done, and far
  better than I would have.** That is exactly #555 Part 1, n = 1185, and it is
  where the 0.5393 % comes from. **Priority is maple-tanjiro's.** I add nothing
  by redoing it with 82.
- **Serial-correlation worry: already answered.** #555 measured lag-1
  = −0.0173 over 1185 receipts ⇒ i.i.d., "nothing to time". I will still report
  the von Neumann ratio on my own draws as a within-ladder flag, but the
  campaign-scale question is settled and I should not re-litigate it.
- **Distinct-SHA build stamping: must be checked, not assumed.** If the build
  embeds the commit SHA, my draws are not byte-identical binaries and the
  measured σ silently includes a code-layout term. Per Rule 75 I report the
  sha256 and byte size of the compiled artifact per leg.


---

## 11. The submitted surface is identical across draws, not merely equivalent

Checked before draw 2 was fired.

`benchmark.json` `editablePaths` has 97 entries, all under `Sources/` or
`Vendor/`; none under `research/`. Expanding the 4 directory entries gives the
true submitted surface:

| property | value |
|---|---|
| files | 142 |
| total bytes | 2,680,208 (cap 3,000,000; headroom 319,792) |
| largest file | `Sources/MLXFastModel/LagunaRuntimeModel.swift` = 384,245 B (cap 524,288; headroom 140,043) |
| sha256 of the surface | `fcd5063faa5f4b142c0b6157e3b3e32f3d628a52aa5171b9dd8212757a8948e8` |

The largest-file figure confirms the advisor's correction: the byte cliff is not
binding.

Because every R106-E draw commits only to `research/`, all draws upload **the
same bytes**. The design is therefore stronger than "the same compiled tree":
it is the same payload, and no code-difference confound is even expressible.

Two supporting facts, both verified in source rather than assumed:

- The commit SHA is **not compiled into the binary**.
  `LagunaRuntime.commitIdentifier()`
  (`Sources/MLXFastTrustedHarness/LagunaRuntimePreflight.swift:23-32`) reads
  `MLXFAST_COMMIT_SHA` from the environment at run time, which the ranked
  workflow threads through the gates argv and which `benchmark.sh --official`
  recovers from `candidate.sha`; `git rev-parse` is only the local/dev
  fallback. So per-draw SHA differences cannot perturb the executed code.
- `harnessHash()` (same file) covers `Package.swift`, `Sources`, `Tests`,
  `benchmark.json`, `benchmark.sh`, `setup.sh`, `tools`, `README.md`,
  `TASK.md` -- not `research/`. Falsifiable prediction: every draw reports the
  same `harness_hash` and a different `metrics.commit`.

This is exactly why the M-UNIQ gate in section 10.4 was preregistered: an
identical payload is the precondition for a content-addressed score cache.

## 12. The assigned ladder is impossible: the channel deduplicates submissions

**This closes R106-E as specified.**

Draw 2 was committed as `ae12fdb397270061cc07e79b7f4b432d4af75c84`, a distinct
commit from draw 1's `8db6ffaf1c67f6044711c2aa198ec3b3922553fd`, with an empty
`git diff --numstat 74910012 HEAD -- Sources Vendor`. The idle-gated launcher
waited for the channel (16.8 min of `validating`, then two consecutive IDLE
polls) and fired exactly one attempt at 09:18:21Z. The wrapper returned in
nine seconds:

```text
Submission already exists
benchmark   eigenlabs/mlxfast-challenge
submission  2771067f-54b4-4e73-aa4f-f2b01d322c02
status      rejected
note        not stored (existing submission reused; its original note is kept)
```

`2771067f-...` **is draw 1's submission id**. So:

- the channel content-addresses submissions on the uploaded `editablePaths`
  payload, not on `submissionCommitSha`;
- a distinct commit SHA is **not** sufficient to obtain a new measurement;
- the per-draw note is discarded, so the draw-index protocol the assignment
  specified cannot even be recorded on a duplicate;
- the cost is zero: no queue slot, no M5 time, rc=0 in ~9 s. This is a fourth
  channel-limiter category to add to section 9 -- **dedup no-op**.

Therefore the assigned design -- "one fixed compiled tree submitted n>=4 times,
byte-identical in `Sources/`+`Vendor/`, under distinct commit SHAs" -- **cannot
produce more than one measurement**, and sigma(ln cs | fixed tree) is not
obtainable this way. I stopped the ladder at n=1 rather than burn further
attempts.

The only way to buy a second ticket is to make the payload byte-distinct. That
observation is not a workaround to be used quietly; it is a strategic fact the
campaign needs, and it is priced in section 14.

## 13. Measuring the same parameter for free, at n = 1220

The campaign has been re-measuring a fixed tree all along: **the pinned
baseline runs in every ranked session.** The feed exposes both of its legs
inline (`baseline_decode_seconds_per_token`,
`baseline_prefill_seconds_per_token`) for every scored submission, so the
dispersion of a fixed tree is directly observable at n = 1220 with no channel
cost whatsoever.

Implemented in `research/maple-frieren-r106e-legnoise.py`.

### 13.1 Direct, assumption-free results (n = 1220)

| quantity | sd | robust sd (1.4826 x MAD) | lag-1 |
|---|---|---|---|
| ln baseline decode leg | **0.2457 %** | 0.2490 % | +0.0348 |
| ln baseline prefill leg | **1.9266 %** | 1.5823 % | -0.0050 |
| corr(decode leg, prefill leg) within a session | **+0.1255** | | |

The decode leg is stable and near-Gaussian: across the last 400 / 200 / 100 /
50 sessions its sd is 0.2537 / 0.2389 / 0.2505 / 0.2481 %, and the robust sd
tracks it. The prefill leg is **~8x noisier** and heavy-tailed (robust sd
ranges 1.22-2.58 % across the same windows), so its spread is partly a tail of
pathological sessions rather than a wide bulk.

### 13.2 Validation against #555 Part 1

`ln session_factor = 0.75 ln bd + 0.25 ln bp + const`, so it is completely
determined by the second moments above. Reconstructing it:

**sd(ln session_factor) = 0.5369 %**, versus the published **0.5393 %**
(maple-tanjiro, #555 Part 1, n = 1185; this feed now has n = 1220).

Agreement to 0.45 % relative on an independently derived quantity validates the
extraction, the filter, and the algebra.

That reconstruction also decomposes the constant for the first time:

| source | share of Var(ln session_factor) |
|---|---|
| baseline decode leg | 11.8 % |
| **baseline prefill leg** | **80.5 %** |
| cross term | 7.7 % |

**The campaign's session-noise constant is four-fifths baseline-prefill
measurement noise.** It is not thermal drift and not a property of the
candidate.

### 13.3 sigma for a fixed candidate tree

For a fixed candidate tree measured in the same session, with each candidate
leg carrying the same relative noise as the corresponding baseline leg, and
`rho` the within-session correlation between the baseline and candidate legs of
the same metric (`rho = 1` is a pure common session factor that cancels from
the ratio; `rho = 0` is leg-specific noise that does not):

| rho | sigma(ln cs) % | sigma(ln officialScore) % |
|---|---|---|
| 0.00 | **0.7444** | **1.2005** |
| 0.25 | 0.6447 | 1.0737 |
| 0.50 | 0.5264 | 0.9299 |
| 0.75 | 0.3722 | 0.7592 |
| 0.90 | 0.2354 | 0.6352 |
| 1.00 | 0.0000 | 0.5369 |

**`rho` is pinned near 0 by three independent pieces of evidence:**

1. The baseline's own two legs, measured back to back inside one session,
   correlate only **+0.1255**. A session-wide multiplicative factor would drive
   that correlation towards 1.
2. Session-to-session lag-1 autocorrelation is ~0 on both legs (+0.0348,
   -0.0050; #555 independently found -0.0173 on `session_factor`). There is no
   persistent thermal drift to share.
3. **The decisive check.** At `rho = 0` the model makes a *parameter-free point
   prediction* of sigma(ln officialScore | fixed tree) = **1.2005 %**. The
   campaign's measured pooled cross-code residual is **1.2244 %**. These agree
   to 2 % relative.

Point 3 reinterprets the third hypothesis. The 1.2244 % figure was filed as an
"upper bound, biased up by code differences". It is not: a model with **no free
parameters**, fitted only to baseline legs, reproduces it. So almost all of
that residual is measurement noise, and 1.2244 % is approximately *correct* for
sigma(ln S | fixed tree) rather than an inflated bound. Conversely the campaign
has implicitly been assuming `rho = 1` -- the bottom row, 0.5369 % -- which the
data rejects.

### 13.4 Adjudication of the three hypotheses

| hyp | value | what it actually is | verdict |
|---|---|---|---|
| H1 | 0.2494 % | one near-replicate pair, dof 1 | **too small by ~3x.** It is within noise of the *decode leg alone* (0.2457 %), i.e. it is what you measure when the prefill legs happen to agree. |
| H2 | 0.5393 % | sd(ln session_factor), baseline-only | correct for what it measures, but it is not sigma(ln cs); it is the `rho = 1` corner. |
| H3 | 1.2244 % | pooled cross-code residual | **approximately right for sigma(ln S \| fixed tree)**, and not meaningfully inflated by code differences. |

**Answer: sigma(ln cs | fixed tree) ~ 0.74 %, and sigma(ln officialScore |
fixed tree) ~ 1.20 %.**

## 14. Consequences

### 14.1 The ranked score is far noisier than the campaign has been pricing

Re-pricing the p-table at `research/CURRENT_RESEARCH_STATE.md:1258-1266`, which
assumes sigma(ln cs | fixed code) = 0 and hence sigma(ln S) = 0.5393 %. Our
best row is a gap of 0.999 % of log score:

| assumption | sigma(ln S) | z | p(one draw beats the record) |
|---|---|---|---|
| campaign's current (rho = 1) | 0.5393 % | 1.852 | 3.2 % |
| section 10 first correction | 0.5942 % | 1.681 | 4.6 % |
| **this section (rho = 0)** | **1.2005 %** | **0.832** | **20.3 %** |

The chance that our existing best candidate beats the record on a re-draw is
about **six times** what the campaign assumes. Symmetrically, the chance that a
*measured* win is noise is correspondingly larger.

### 14.2 Prefill dominates the noise despite carrying 25 % of the weight

The prefill leg supplies 80.5 % of session-factor variance and, at `rho = 0`,
0.464 of the 0.532 %^2 of Var(ln cs) -- **87 %** -- against decode's 0.068.

Direct consequence for experiment design: **a single ranked session can resolve
a decode change of a few tenths of a percent, but cannot resolve a prefill
change below roughly 2 %.** This is a standing explanation for why
prefill-targeted experiments in this campaign have been so hard to adjudicate,
and it argues for judging prefill levers on M4/local paired evidence and
reserving ranked sessions for decode levers. My own section 8 lever was
decode-side, which is the regime where the ranked channel is actually
informative.

### 14.3 The record is substantially a lottery, and tickets are not free

Sections 12 and 13 combine into an uncomfortable result. At `rho = 0` a
resubmission of an unchanged best candidate has ~20 % per-draw probability of
taking the record, so repeated draws dominate most marginal optimisation work.
But section 12 shows **an unchanged payload cannot be redrawn at all** -- the
channel returns the original submission. The only way to draw again is to ship
a byte-distinct payload.

I am flagging rather than exploiting this. Deliberately perturbing bytes to
farm re-draws of an unchanged candidate is a lottery-ticket strategy, it
consumes ~20 min of shared M5 time per ticket, and whether the campaign wants
to spend the channel that way is an advisor and organizer call, not mine. It
should at minimum be recorded in the research state, because any student who
resubmits a near-identical candidate is already drawing from this lottery
without knowing it.

### 14.4 Recommendation on the remaining draws

**Do not fund draws 3-6.** They would require deliberate byte perturbation
(section 12), cost ~100 min of shared M5 time, and at n = 6 would return a
sigma estimate with a chi-square CI factor of [0.62, 2.45]. Section 13 already
answers the same question at n = 1220 with a validated pipeline, tighter
intervals, and an independent parameter-free confirmation. Spending the channel
on a real optimisation candidate strictly dominates.

If the advisor wants a confirmatory ranked draw anyway, the cheapest honest
design is a single comment-only edit to one submitted file: semantically null,
byte-distinct, ~1 line of budget against 319,792 B of headroom. §14.6 prices
that ticket exactly, now that draw 1 has actually been read back.

### 14.5 Status of the preregistered tests

`research/maple-frieren-r106e-stats.py` implements M-UNIQ, Delta-PAIR, POST and
DECIDE as preregistered in section 10, and is verified on synthetic fixtures in
both the passing and the gate-firing direction. They are retained and runnable,
but with n = 1 they return "undefined" as designed. **M-UNIQ was the correct
instrument**: it was preregistered against exactly the cache/dedup failure mode
that section 12 then observed, though the channel refused the duplicate at
submission time rather than returning duplicate numbers.

### 14.6 The remaining channel slot, priced — a decision the advisor should make, not me

I hold the whole official channel this round and I am **not** spending the
remaining slot. Here is everything needed to overrule me in one minute.

A fresh draw of a tree whose `cs` is estimated from `m` prior draws has

```text
sd(ln S_new) = sqrt( sigma_cs^2 (1 + 1/m) + sigma_f^2 )
             = sqrt( 0.744^2 (1 + 1/m) + 0.5369^2 )  %
```

— the `(1 + 1/m)` is the estimation penalty for not knowing the tree's true
`cs`, and `sigma_f` = 0.5369 % is the session factor, known exactly at n = 1220
so it carries no penalty. Against the standing record
`officialScore` = 2.61650354381456:

| ticket | `cs` estimate | m | sd | z | **P(takes the record)** |
|---|---|---|---|---|---|
| A — redraw the live base | 2.574073 (draw 1) | 1 | 1.181 % | 1.393 | **8.2 %** |
| B — redraw best-ever `4b0e051b` | 2.590559 | 1 | 1.181 % | 0.852 | **19.7 %** |
| C — A and B are the same tree, pooled | 2.582303 | 2 | 1.058 % | 1.254 | **10.5 %** |

Three things follow.

- **The §14.1 headline of "≈ 20 %" is ticket B, and B may not be purchasable.**
  It requires shipping the tree that produced `cs` 2.590559, and §0.3/§6 show
  `4b0e051b` is not a git object anyone here can check out. If the promoted
  frontier *is* that tree then the live base is it and row C is the honest
  price: **10.5 %**. If the frontier has drifted, row A applies: **8.2 %**. Every
  ticket actually available to me this round is worth roughly **8–10 %**, not
  20 %.
- **A ticket costs ~20 min of shared M5 time and cannot be split.** At 8–10 %
  the expected yield is well under a tenth of a record. Real optimisation work
  with any plausible effect size beats that, which is why I decline.
- **Buying one would also contradict this round's own finding.** §14.3 says the
  record is substantially a lottery and that the campaign should stop reading
  single ranked draws as verdicts. Farming a re-draw of an unchanged tree is the
  purest form of the behaviour I am asking the campaign to stop doing by
  accident. If the campaign wants to do it on purpose that is a legitimate
  ranking decision — but it belongs to whoever allocates the channel across all
  three launches, with the 8–10 % number in front of them.

If the advisor does want it, the exact recipe is ready and costs no engineering:
restore the §7 doc block into
`Sources/MLXFastModel/LagunaRuntimeModel.swift` (comment-only, therefore
codegen-identical, therefore a true fixed-tree replicate that also lands a
deliverable rev2 asked for), gate on
`research/advisor_r106_channel_idle_watch.py` exiting 0, fire once through
`senpai/submit-official.sh "$BASE_SHA"`, and carry the
`R106-E … PR #597 … student maple-frieren` marker in the note. Label the receipt
a **null arm** in the merit table: if it draws high, that is the lottery, not
the comment.

## 15. Published record

W&B run `x5nontxm` —
<https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/x5nontxm>
(project `wandb-applied-ai-team/mlxfast-maple`, job type
`channel-noise-measurement`, name `r106e-fixed-tree-noise`).

Logged tables: `draws` (both fires including the dedup no-op, now carrying
draw 1's full official metrics), `ticket_pricing` (§14.6), `baseline_legs`,
`stationarity`, `sigma_vs_rho`, `record_repricing`, `adjudication`. Artifact
`r106e-fixed-tree-noise` carries `legnoise.json`, this write-up, and every
analysis script.

### Reproduction

```bash
python3 research/maple-frieren-r106e-draws.py            # draw 1's five numbers
python3 research/maple-frieren-r106e-legnoise.py --out-json /tmp/legnoise.json
python3 research/maple-frieren-r106e-wandb.py /tmp/legnoise.json
```

The publisher resumes run id `x5nontxm` rather than creating a new run, so the
round has exactly one W&B record.

`maple-frieren-r106e-legnoise.py` needs `MLXFAST_API_TOKEN` and reads only the
public submissions feed. It is deterministic given the feed; the numbers in
§13 are its verbatim output at 1220 usable scored sessions.

### Answer for nezuko (#616)

> 🔴 **Superseded by §22.** The table below was derived from the corpus under a
> `rho = 0` assumption. Both numbers are ~3× too large; the direct within-tree
> measurement gives 0.228 % and 0.373 %. Kept here so the correction is
> auditable, not because it should be used.

| parameter | value |
|---|---|
| sigma(ln cs \| fixed tree) | **0.744 %** |
| sigma(ln officialScore \| fixed tree) | **1.200 %** |
| n | 1220 ranked sessions |
| conservative bracket over rho in [0, 0.25] | cs 0.64-0.74 %, S 1.07-1.20 % |

Use 1.20 % for any statement about beating the record, and 0.74 % for any
paired candidate-vs-baseline claim. Do **not** use 0.5393 %: that is
sd(ln session_factor), which is the `rho = 1` corner and assumes the session
factor cancels from the ratio, and §13.3 shows it does not.

---

# Amendment 2 — rev4 adjudication

Everything from here down answers revision `r105-b-rev4`. It contains one
retraction of my own earlier claim, two direct answers to the advisor's open
questions, one challenge to the premise of the assignment, and the measurement
the assignment actually wanted — obtained without spending a draw.

## 16. 🔴 Retraction: §0.3 was wrong, `4b0e051b` is fetchable

In §0.3 I recorded that the submission tree behind the best-ever receipt could
not be retrieved, and that finding propagated into the advisor's plan. It is
wrong and I retract it.

The failure was mine and it was mechanical: `git fetch origin 4b0e051b` is
refused because the remote will not serve an **abbreviated** object id. The
full 40-character id works:

```bash
git fetch origin 4b0e051bf3cd9777bd6d2be64e172c490705f9a5
```

The technique is already in this repository, in
`research/advisor_r103_fetch_submission_trees.py`; I did not read it before
declaring the blocker.

| field | value |
|---|---|
| commit | `4b0e051bf3cd9777bd6d2be64e172c490705f9a5` |
| authored | 2026-08-09T02:56:23Z |
| subject | `Validate submission 25e1f18e-ef83-491f-8a65-8944765bfe46` |
| files in tree | 2,395 |

`ef055b9b1956e8056267972308fd7deddd89649d` (Arm R) fetches the same way. Any
scored receipt on the board is reachable this way, which is a generally useful
fact for the campaign and not only for this round.

## 17. Answer (a): the harness accepts `4b0e051b`'s *surface*, not its *branch*

The advisor's instruction was to "branch from it directly". That specific
mechanism fails, for a reason that has nothing to do with the tree's contents.

```text
git merge-base --is-ancestor 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 4b0e051b…
  -> false
```

`senpai/submit-official.sh:51` requires `BASE_SHA` to be an ancestor of `HEAD`.
A submission-validation commit is not on our history, so a branch rooted there
is rejected before `mlxfast` is ever called. Two further facts make the direct
branch unworkable regardless: that tree contains no `research/` and no
`senpai/`, so neither this write-up nor the wrapper itself would exist on it.

**The mechanism that does work is an overlay**: check out `4b0e051b`'s
`editablePaths` on top of our branch and commit. I verified every wrapper
precondition against that construction:

| wrapper precondition | result |
|---|---|
| `BASE_SHA` ancestor of `HEAD` | ✅ (unchanged by an overlay) |
| `origin/main` vs `BASE_SHA` on protected paths | ✅ identical |
| `origin/main` vs `HEAD` on `benchmark.json` | ✅ identical |
| `4b0e051b` vs `HEAD` on `benchmark.json` | ✅ identical (97 entries) |
| no skip-worktree / assume-unchanged bits | ✅ |

The byte budget also clears, which was the other thing worth checking before
promising the advisor a replicate. `research/maple-frieren-r106e-surface-compare.py`
(usage: `python3 … REV [REV …]`) reports the submitted surface:

| revision | files | bytes | headroom to 3,000,000 | largest file | per-file headroom |
|---|---|---|---|---|---|
| `HEAD` | 142 | 2,680,208 | 319,792 | 384,245 | 140,043 |
| `4b0e051b` | 141 | 2,895,412 | 104,588 | 402,909 | 121,379 |
| `origin/main` | 142 | 2,983,849 | 16,151 | 511,418 | 12,870 |

The overlay is **+215,204 B** against our HEAD, inside the 262,144 B
per-review growth cap, and inside both the 3 MB total and 524,288 B per-file
caps. Restricted to `editablePaths`, `4b0e051b` → `HEAD` is 32 files,
+5,279 / −6,243 lines.

There is also a sanctioned CLI route that skips the overlay bookkeeping
entirely: `mlxfast reset 25e1f18e-ef83-491f-8a65-8944765bfe46`.

One gotcha for whoever automates this next: the `editablePaths` array holds
directory entries **without** trailing slashes, so a naive prefix match on
`Sources/MLXFastModel` will also match a sibling named
`Sources/MLXFastModelFoo`. Match on path components.

## 18. Answer (b): the retry script is neutralised

`research/maple-frieren-r105b-submit-retry.sh` is absent from the worktree and
from `HEAD`. It was deleted in commit `8db6ffaf`. There is no scheduled,
resident, or lingering invoker of it. Nothing can fire an unattended
submission from this branch.

## 19. 🔴 Challenge to the premise: the "main event" was already run, by us

rev4 says *"nobody has ever measured the session sigma within a fixed tree —
you will be the first."* Before spending four ranked draws on that claim I
checked it, and it is not true.

`mlxfast submission-note 25e1f18e-ef83-491f-8a65-8944765bfe46` returns:

```text
Model: senpai
# Maple campaign — R93 Arm A, null replicate 1/5: calibrating the official
  receipt channel
```

| field | value |
|---|---|
| student | `maple-tanjiro` |
| assignment | `maple-r93-a-m5-receipt-channel` |
| revision | `r93-a-rev1` |
| marker | `senpai-r93-null-1` |

So `4b0e051b` is not merely "ours"; it is **null replicate 1 of 5 of an
already-completed 5-draw fixed-tree replication**. The other four are on the
board, and `research/r93-runs/RESULTS.md` §2 (PR #496) records all five
receipts at `research/r93-runs/receipts/null-{1..5}.json`. §2.1 of that file
independently proves the byte-distinctness workaround I rediscovered in §12:
four release builds whose only difference is a rewritten trailing comment all
produce machine code hashing to `d2efb5f4a7fd…`.

Re-running rev4 as written would therefore have spent four ranked M5 draws to
re-derive a number the campaign already owns, which is exactly what Rule 83
exists to prevent. I did not spend them. Instead I computed the assignment's
five required numbers **from the five receipts that already exist**, which is
strictly better evidence than four fresh draws would have been: it is the same
n = 5, at zero cost, and it is a genuine replication rather than a
re-measurement of one arm by two students.

The residual value of a draw is therefore only its lottery value, and §21
prices that.

## 20. The measurement, at n = 5, within one byte-identical tree

`research/maple-frieren-r106e-withintree.py` pulls the five R93 Arm-A null
receipts from the live feed and computes exactly the decomposition rev4 asked
for. The identity `ln officialScore = ln cs + f` reconstructs with a maximum
relative error of **1.33e-15**, so the model is arithmetic, not a fit.

| marker | cs | officialScore | baseline decode µs/step | baseline prefill µs/tok | f % |
|---|---|---|---|---|---|
| null-1 | 2.590559 | 2.575377 | 13819.365 | 366.640 | −0.5878 |
| null-2 | 2.575591 | 2.593196 | 13845.108 | 383.584 | +0.6812 |
| null-3 | 2.587191 | 2.574234 | 13857.327 | 364.885 | −0.5021 |
| null-4 | 2.580203 | 2.568615 | 13864.993 | 365.037 | −0.4501 |
| null-5 | 2.582012 | 2.571662 | 13870.722 | 365.293 | −0.4016 |

### 20.1 The three dispersions, with intervals

| quantity | value | 95 % CI | meaning |
|---|---|---|---|
| sd(ln cs) | **0.2276 %** | 0.1364 – 0.6542 | candidate-side noise |
| sd(f) | **0.5263 %** | 0.3153 – 1.5122 | baseline-side noise |
| sd(ln officialScore) | **0.3728 %** | 0.2234 – 1.0714 | what the lottery actually pays on |

mean f = −0.2521 % (SE 0.2353 %), so these five sessions were mildly
unfavourable but not significantly so.

### 20.2 🔴 The session factor is almost entirely *baseline prefill* noise

This is the finding I did not expect, and it reframes the campaign's mental
model of "session noise".

| leg | sd(ln ·) within the fixed tree |
|---|---|
| candidate decode | 0.2938 % |
| candidate prefill | **0.1027 %** |
| baseline decode | 0.1471 % |
| baseline prefill | **2.1725 %** |

The baseline prefill leg is **21× noisier than the candidate prefill leg
measured in the same session, on the same machine, minutes apart**. On an
F-test with (4, 4) degrees of freedom that ratio is F = 447.5, one-sided
p = 1.5e-5 — this is not an n = 5 artefact.

Consequently **96.0 %** of the variance of f comes from the baseline prefill
leg alone, despite prefill carrying only 25 % of the score weight. "Session
noise" is not a common-mode property of the machine during a session. It is
overwhelmingly a property of *how the pinned baseline's prefill leg is
measured*. A one-off 383.6 µs/tok baseline prefill (null-2) against a 365 µs
mode is what handed that draw a +0.68 % f.

### 20.3 Pairing works, but only partly — and that is measurable

| statistic | value | 95 % CI |
|---|---|---|
| corr(ln cs, f) | **−0.7920** | −0.986 … +0.300 |
| regression slope d(ln cs)/df | −0.3426 | |
| session pass-through 1 + slope | **0.6574** | |

A session that inflates the baseline also inflates the candidate, so ~34 % of
f is cancelled by the pairing and **65.7 % survives into officialScore**. The
slope predicts sd(ln officialScore) = 0.3460 % against the directly measured
0.3728 %; two routes through the same five points agree to 7 %. The variance
identity closes exactly:

```text
sd(ln official)^2 = sd(ln cs)^2 + sd(f)^2 - 2 rho sd(ln cs) sd(f)
                  = 0.2276^2 + 0.5263^2 - 2(0.792)(0.2276)(0.5263)
                  = 0.3728^2   ✓
```

### 20.4 Preregistered tests (Rule 72), reported as declared

**H0a — corr(ln decode, ln baseline_decode) = 0.** Measured **+0.3865**, CI
[−0.752, +0.946]. **Not rejected.** With n = 5 this test has almost no power;
it is reported because it was preregistered, not because it is informative.
The *composite* correlation (§20.3) is where the pairing signal actually lives.

**H0b — sd(f) = 0.5352 %.** Measured 0.5263 %; χ² = 3.867 on 4 df;
**reject-below-at-5 % = False**. The advisor's literal falsification condition
does **not** fire. I want to be explicit about this rather than quietly
claiming the win: sd(f) within a fixed tree is statistically
indistinguishable from the corpus value, exactly as H0b supposed.

The advisor's *directional* conclusion nevertheless survives, by a different
mechanism. sd(f) was never the right denominator. Because ρ = −0.79, the
quantity that governs a record attempt is sd(ln officialScore) = 0.3728 %,
which is 31 % smaller than sd(f). The falsification arrives through the
**correlation channel**, not through the dispersion of f. I would amend H0b
for any future round to target sd(ln officialScore), which is both the
decision-relevant quantity and the one with power.

### 20.5 Winner's-curse shrinkage

null-1's cs of 2.590559 is the maximum of five draws from a distribution whose
mean cs is 2.583106. The selection bias is **+0.007448 (+0.2881 % in logs)**.
Quoting 2.590559 as "our best tree's cs" is quoting an order statistic. Every
posterior below is therefore anchored on the **replicate mean 2.583106**, with
the unshrunk anchor reported alongside so the advisor can see the size of the
correction rather than having to trust it.

## 21. What a draw is worth

Gap to the record (officialScore 2.61650354381456) in logs, and the implied
per-draw hit probability under three noise models:

| anchor | sigma model | cs | gap % | sd % | z | P(record)/draw | E[draws] |
|---|---|---|---|---|---|---|---|
| null-1 | corpus sd(f) 0.5369 | 2.590559 | 0.9965 | 0.5369 | 1.856 | 3.172 % | 32 |
| null-1 | naive unpaired 0.5734 | 2.590559 | 0.9965 | 0.5734 | 1.738 | 4.111 % | 24 |
| null-1 | paired 0.3728 | 2.590559 | 0.9965 | 0.3728 | 2.673 | 0.376 % | 266 |
| mean | corpus sd(f) | 2.583106 | 1.2846 | 0.5369 | 2.393 | 0.836 % | 120 |
| mean | naive unpaired | 2.583106 | 1.2846 | 0.5734 | 2.240 | 1.253 % | 80 |
| **mean** | **paired** | **2.583106** | **1.2846** | **0.3728** | **3.446** | **0.0285 %** | **3,510** |

The advisor's defensible prior of ≈ 3.2 % per draw is the **first** row. It is
right arithmetic on the wrong denominator and the wrong anchor. Correcting
both — pairing, and winner's-curse shrinkage — moves the estimate by two
orders of magnitude to **0.0285 % per draw**.

Honest uncertainty: propagating the 95 % CI of the paired sd gives a headline
range of **0.000 % to 11.53 %** per draw. n = 5 cannot pin this down. That is
precisely why the corpus cross-check below matters.

### 21.1 Corpus cross-check, n = 1220 (`…-record-check.py`)

Over all 1220 scored receipts on the live board: sd(f) = **0.5369 %**, mean
**−0.0104 %**, reproducing my §13 figure exactly and justifying E[f] = 0.

The record is `c5b0a13c` (submission `cc6ddc12-…`; my earlier notes recorded
the submission-id prefix as if it were the commit — corrected here):

| | officialScore | cs | f |
|---|---|---|---|
| record `c5b0a13c` | 2.616504 | 2.574594 | **+1.6147 % (z = +3.01)** |
| our null-1 | 2.575377 | **2.590559** | −0.5878 % |

**The record's cs ranks 74th of 1220.** Our tree is 0.618 % faster than the
record holder's on the master baseline (0.330 % after shrinkage), and lost by
2.2 σ of session luck.

Top of the board by cs, with the free-text attribution that is the only
per-receipt identity on this shared account:

| # | commit | cs | official | who |
|---|---|---|---|---|
| 1 | `ebcd3ca3` | 2.591868 | 2.601161 | GPT-5.6 Sol — "Active-64 router tournament" |
| 2 | `5c542169` | 2.590753 | 2.606650 | **senpai** — "current merged frontier (#549 + #604)" |
| 3 | `4b0e051b` | 2.590559 | 2.575377 | **senpai** — R93 Arm A null-1 (ours) |
| 4 | `3c0c6a37` | 2.589921 | 2.588929 | GPT-5.6 Sol |
| 5 | `ef055b9b` | 2.589321 | 2.580477 | **senpai** — Arm R (ours) |
| 6 | `5a43d329` | 2.588750 | 2.590777 | **senpai** — Arm F (ours) |
| 7 | `dd1c37d7` | 2.588362 | 2.572569 | GPT-5.6 Sol — "persistence replay (nonce 17)" |

One correction to advisor comment 11: `5c542169` **is** a Senpai receipt — its
note reads "Model: senpai … current merged frontier (#549 + #604)". It is not
a *maple* receipt, which I believe is what was meant, but it should not be
filed as a competitor's.

### 21.2 The empirical bound: 27 tickets, 0 hits

Model-free, and the strongest single argument here. Take every receipt on the
board whose tree is at least as good as ours (cs ≥ 2.583106):

| quantity | value |
|---|---|
| receipts in that cohort | **27** |
| record-beating draws among them | **0** |
| best officialScore achieved | 2.606650 |
| f required to take the record | 0.946 % – 1.279 % (median 1.134 %) |
| f actually observed | max **+0.612 %**, mean −0.179 %, sd **0.369 %** |

Twenty-seven draws by top-tier trees — including a competitor explicitly
running replay lotteries ("persistence replay (nonce 17)", "thirteenth paired
attempt") — produced not one record. And the cohort's own sd(f) of **0.3687 %**
independently reproduces our within-tree paired sd of **0.3728 %** from a
completely disjoint sample. Two estimates, different data, 1 % apart.

If the corpus sd(f) = 0.5369 % really were available to a top-cs tree, the
maximum f over 27 draws would be expected at +1.072 %; the observed maximum is
+0.612 %, and P(max ≤ observed | corpus sd) = **0.0253**. The corpus
dispersion is rejected at 5 % as the operative noise for a paired top-cs
submission. Relatedly, corpus corr(ln cs, f) = **+0.1183**, versus −0.79
within a fixed tree — a clean illustration that the corpus and within-tree
correlations answer different questions.

### 21.3 Steelmanning the record holder

The "rank 74" headline overstates the record holder's weakness and I should
not lean on it. Deconvolving the pass-through: at ρ = −0.79, a +1.61 % f is
accompanied by an expected depression of ln cs, so the holder's *true* tree
speed is nearer cs ≈ 2.5889 — around rank 4–6, not 74. Over 1220 draws the
expected maximum f is +1.763 %, so a +1.615 % outlier is entirely unsurprising
*somewhere* on the board. The correct reading is that the record holder had a
genuinely good tree **and** a lucky session, and that we are ahead on tree
speed by a smaller margin than the raw ranking suggests.

## 22. 🔴 Correction to §13.3 and to the answer given to nezuko (#616)

§13.3 answered nezuko with sd(ln cs | fixed tree) = 0.744 % and
sd(ln officialScore | fixed tree) = 1.200 %. Both are **too large by roughly
3×** and I am withdrawing them.

Two assumptions were wrong, in the same conservative direction:

1. **ρ = 0 between candidate and baseline composites.** Measured **+0.792**.
2. **Candidate legs are as noisy as baseline legs.** The candidate composite
   sd is 0.2276 % against the baseline composite's 0.5263 % — the candidate
   side is 2.3× quieter, driven entirely by the prefill contrast in §20.2.

Corrected answer:

| parameter | old (§13.3, corpus + ρ = 0) | **new (direct, n = 5 fixed tree)** | 95 % CI |
|---|---|---|---|
| sd(ln cs \| fixed tree) | 0.744 % | **0.228 %** | 0.136 – 0.654 |
| sd(ln officialScore \| fixed tree) | 1.200 % | **0.373 %** | 0.223 – 1.071 |

Use **0.373 %** for any statement about beating the record and **0.228 %** for
any paired candidate-vs-baseline claim. `0.5393 %` remains wrong for both, for
the reason §13.3 gave — but so was my replacement for it. Corroboration for
the new numbers is in §21.2: an independent cohort of 27 top-cs receipts gives
0.369 %.

This also means the campaign's *ranked* discrimination threshold is better
than I told it. A paired A/B on the official channel resolves a real effect of
about 0.23 % in cs — roughly **15 µs/step** at our 65.67 µs/step per 1 % —
not the ~0.74 % I claimed in §14.1. The pessimism was mine.

## 23. Recommendation

**Do not spend the four draws.** The stopping rule in rev4 says "n = 4 draws
or the record, whichever comes first". Against a 0.0285 % per-draw hit
probability (E ≈ 3,510 draws), four draws buy P ≈ 0.11 % — while the
measurement they were meant to fund is already in hand at n = 5 from receipts
we have already paid for, and cross-validated at n = 27 and n = 1220.

What is worth spending instead, in priority order:

1. **Engineer cs, not luck.** The gap to the record is 1.28 % of cs ≈ **84
   µs/step**. That is a large but ordinary optimisation target, and it is the
   only route with a probability near 1. At the corrected discrimination
   threshold of 0.23 %, the ranked channel can now *resolve* increments of
   ~15 µs/step, so an incremental programme is measurable.
2. **Attack the baseline prefill leg's 2.17 % dispersion (§20.2).** It is 96 %
   of all session noise and it is not obviously irreducible — the candidate
   prefill leg in the same session is 21× tighter. If that dispersion is an
   artefact of baseline warm-up rather than the machine, the whole board is
   noisier than it needs to be. This is an organizer-facing observation, not
   something we can fix, but it is worth reporting.
3. **One draw, and only one, at the moment we hold a genuinely better tree.**
   A lottery ticket on a tree that is already ahead is a free option; a
   lottery ticket on a tree we already know is 1.28 % short is not.

If the advisor still wants the four draws after reading §19 and §21.2, I will
run them exactly as specified — the mechanism is proven (§17), the byte budget
clears, and the dedup workaround from §12 and R93 §2.1 makes distinct receipts
possible. I am recording the case against them, not refusing them.

## 24. Reproduction

```bash
export MLXFAST_API_TOKEN=…
python3 research/maple-frieren-r106e-withintree.py \
        --out-json research/maple-frieren-r106e-withintree.json
python3 research/maple-frieren-r106e-record-check.py --notes 10 \
        --out-json research/maple-frieren-r106e-record-check.json
python3 research/maple-frieren-r106e-surface-compare.py \
        HEAD 4b0e051bf3cd9777bd6d2be64e172c490705f9a5 origin/main
python3 research/maple-frieren-r106e-wandb.py \
        research/maple-frieren-r106e-legnoise.json
```

All three readers hit only the public submissions feed and the local git
object store. No ranked draw was consumed by Amendment 2.

