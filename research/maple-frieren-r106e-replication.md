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

(appended in order; empty at preregistration time)

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
