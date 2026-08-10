# R106-E — the first replication this campaign has ever performed

PR #597 · assignment `maple-r105-b-router-prefetch-adjudication` · revision `r105-b-rev3`
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
