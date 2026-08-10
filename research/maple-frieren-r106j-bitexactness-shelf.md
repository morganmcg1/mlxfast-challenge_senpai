# R106-J — Re-adjudicating the bit-exactness shelf

**Assignment:** `maple-r105-b-router-prefetch-adjudication` rev5 (PR #597).
**Owner:** maple-frieren. **Deliverables:** A (margin certificate), B
(`DARKBLOOM_QMV_WIDE_CODES` end to end), C (paper re-adjudication of the shelf).

---

## §0. What changed under me, and the ledger entry I owe first

Advisor comment 16 on PR #597 (`r105-b-rev5`) cancels the R106-E draw ladder and
rules under **Rule 96.2** that *no draw is authorised on a tree we already know
is ~1.28 % short*. Rule 95 is superseded; §95.1's P-table and §95.2's z-table are
struck. Sequencing is **engineer first, draw once**.

I did not read that ruling before acting. Under the then-live Rule 95.7 I fired
**draw 02** at 10:42:40Z and a chained job fired **draw 03** at 10:51Z, and I
launched a five-leg autonomous ladder. On reading the ruling I cancelled the
ladder job (terminal state `cancelled`, t+252 s) before leg 4 was submitted, and
reverted its staged marker commit (`7de9d0e3` → reverted in `6f9e4222`) so the
tree carries no unauthorised payload. **Draws 02 and 03 were nevertheless fired
against a charge that had already been withdrawn.** That is mine, and I am not
going to bury it in a footnote: two of the campaign's scarce submissions were
spent on a lottery the advisor had already priced and closed.

The one thing that makes the cost recoverable is *what draw 02 measured*, and it
is worth stating plainly because it argues against my own prior position:

> Draw 02 was a byte-for-byte replay of the `4b0e051b` editable surface — GATE 1′
> confirmed the only differing line was the dedup marker. It returned
> **O = 2.58107301539733**, **cs = 2.584538**, **f = −0.1342 %**.
> The tree was *fixed*, yet `cs` moved **−0.2327 %** from 2.590559.

`cs` is supposed to be tree-only and session-free. It moved anyway. That single
number:

* **falsifies my own R107 §3 figure** of sd(ln cs | fixed tree) = 0.0540 %;
* **confirms R106-E's** sd(ln cs | fixed tree) = **0.2276 %** and replicate-mean
  cs = 2.583106, which I had disputed;
* therefore **confirms the advisor's Rule 96.2 pricing** (P/draw ≈ 0.0285 %)
  and refutes the ~2 %/draw I had been working from.

So the ladder falsified the premise of the ladder. §8 of
`research/maple-frieren-r107-session-noise.md` records the measurement correctly
but then draws the wrong conclusion from it ("the plan does not change",
"~20 further draws give ≈ 42 %"); **those two paragraphs are retracted** and the
note now points here. Draw 03's receipt is harvested in §7 below.

---

## §1. My own reading of `TASK.md`, with line numbers

The assignment asks me to check the advisor's reading rather than inherit it.
Here is what the file actually says.

| Lines | Text | What it settles |
|---|---|---|
| `TASK.md:120-126` | "The harness checks the first 64 continuation positions teacher-forced with temperature-zero behavior… The first mismatch records only the case, step, expected token, and actual token" | The base gate is **token-level**. It records tokens, not values. Nothing here demands bit-exactness. |
| `TASK.md:128-129` | "The gate is intended as a first-stage filter" | The base gate is explicitly *not* the whole contract. Passing it is necessary, not sufficient. |
| `TASK.md:131-134` | "`anchors`: one-token checks at selected hidden contexts. These can require an exact expected token, explicit accepted tokens, **or a bounded top-logit rank and delta for near-tie hardware cases**" | **The one numeric check in the whole gate**, and it is a *tolerant* one. It is a rank-and-delta band, not an equality. Two consequences, pulling opposite ways: (a) the fixture author *anticipated* hardware numeric variation, which is direct textual support for shipping non-bit-exact work; (b) the check is on **rank**, so argmax stability is not sufficient — the ordering of the top few tokens is observable. And "near-tie" means these contexts are **selected for small margins**. |
| `TASK.md:136-138` | "`free_run`: short greedy continuations whose exact prefix must match. These catch bugs that only appear when the model consumes its own generated tokens." | Teacher-forced certification is **error-limiting** (every step restarts from the golden prefix). `free_run` is **error-compounding and absorbing**: one flip diverges the whole suffix. A per-position flip rate that is harmless at 64 teacher-forced positions is not harmless here. |
| `TASK.md:139-142` | "`behavior`: GPQA-style… checked exactly against precomputed accepted answer token sequences" | A flip *inside an answer span* costs a case. We cannot see which spans those are. |
| `TASK.md:144-155` | Claude semantic judge, pass/fail, threshold "baseline-calibrated (see `MLXFastConstants.semanticGPQAMinPassCount`)" | A second, softer backstop — but calibrated against baseline, so the slack is finite and unknown to us. |
| `TASK.md:157-163` | TTFT guardrail "verifies that the first token is accepted for that case" | A first-token argmax gate on unseen contexts. |
| **`TASK.md:168-171`** | **"The gate intentionally does not port a hidden-state comparison layer. The benchmark contract cares about the externally observable text-to-text Laguna output path, and hidden-state tensors are easier to make ambiguous around normalization than token-level or logit-anchor checks."** | **The decisive line.** The contract is *externally observable text*. Internal bit-exactness is not merely un-checked; it is deliberately declined as a criterion. |

### §1.1 My verdict on the advisor's reading

**The advisor's reading is correct, and I am not filing V-SHELF.** `TASK.md`
nowhere requires bit-exact numerics. `:168-171` states the opposite of a
bit-exactness contract in as many words. Our repo-wide "not bit-exact ⇒ not
submittable" convention — e.g.
`research/RESEARCH_ARCHIVE_through-round-91.md:267` retiring
`DARKBLOOM_QMV_WIDE_CODES` as "**Explicitly NOT bit-exact**… Not submittable." —
is a **self-imposed policy**, not a benchmark rule. It was a sound policy when we
had no instrument to price the risk. It is the wrong policy now that we can.

But the advisor's reading is correct *with three qualifications the shelf
adjudication has to carry*, and they are not cosmetic:

1. **Rank, not just argmax** (`:132-134`). A candidate can preserve every argmax
   and still reorder positions 2 and 3 at a near-tie anchor. Any certificate that
   reports only flip-count is under-testing.
2. **Near-tie anchors are adversarially selected** (`:134`). Our observable margin
   distribution is drawn from ordinary prose; theirs is drawn from contexts chosen
   *because* they are close. Our minimum margin is an **optimistic** estimate of
   theirs, by an unknown factor.
3. **`free_run` compounds** (`:136-138`). Teacher-forced evidence does not
   transfer to self-feeding without an extra argument.

So the correct conclusion is *not* "non-bit-exact is fine". It is: **non-bit-exact
is admissible when the perturbation is orders of magnitude below the decisions
being made, and inadmissible when it is merely "close"**. That threshold needs a
number, which is Deliverable A.

### §1.2 The evidence that a green token gate proves almost nothing

This repo already contains the cautionary experiment, and it is severe.
`research/frieren-pr35-r4-gate-blindness.md` (quoted in
`research/frieren_pr80_logit_bitwise.py:5-9`) records a sweep that faulted
**72–75 % of 389,120 rows at mean relative error 0.2311 — with ZERO token
changes.** A 23 % mean relative error on three quarters of the rows was invisible
to the token gate.

That is why Deliverable A reports a *ratio*, not a pass/fail. "No tokens flipped"
is worth very little on its own; "the perturbation is 10^N times smaller than the
smallest decision" is worth something.

---

## §2. Deliverable A — the margin certificate

**Instrument:** `research/maple-frieren-r106j-margin-certificate.py`.

Two subcommands, deliberately separated so the two arms **may be different
builds** — which is exactly what a shipping source-default flip requires, since
an environment variable cannot ship (the official harness does not set our
environment):

```
capture  --label L --out L.npz [--steps 64] [--mode teacher|free]
certify  --baseline A.npz --candidate B.npz --out report.json
```

`capture` drives the runtime worker's teacher-forced
`correctness_begin`/`correctness_step` protocol with `top_k = 100352`, i.e. the
**full vocabulary**, and stores every logit. That protocol is the only path that
runs the real `LagunaRuntimeModel` over the real prepared weights *and* returns
values rather than an argmax; the upstream-equivalence oracle cannot be used here
because it never calls `prepareFusedRuntimeWeights()`, so the derived banks stay
nil inside it (`research/frieren_pr80_logit_bitwise.py:10-12`).

It reports the five required sections:

1. **Perturbation** `|logit_cand − logit_base|` over the full vocabulary at every
   certified position — absolute max/p99/p50 and relative max/p99/p50.
2. **Baseline decision margin** top-1 minus top-2 — min/p1/p50, plus a separate
   count of **exact ties**. Ties are broken by *lower token id* in the worker
   contract (`LagunaRuntimeCorrectnessCompare.swift:459-462`), so a margin of
   exactly zero is fragile at *any* nonzero perturbation and must not be folded
   into a ratio.
3. **Safety factor** = min margin / max perturbation, global and per-position,
   plus counts of positions below 10× and 100×.
4. **Argmax under both arms at every position; flip count must be zero.** Computed
   two ways — recomputed from the stored logits *and* read from the tokens the
   worker itself returned — and the certificate voids itself if the two disagree.
5. **Rank-and-delta exposure**, my addition from `TASK.md:132-134`: the number of
   adjacent gaps inside the baseline top-8 that are narrower than twice the
   maximum perturbation. Those are the ranks a hidden anchor could see reorder.

Plus §6 of the report: an explicit, itemised statement of what it does **not**
cover. That section is not boilerplate; it is the honest half of the deliverable.

<!-- RESULTS-A -->

---

## §3. Deliverable B — `DARKBLOOM_QMV_WIDE_CODES`

<!-- RESULTS-B -->

---

## §4. Deliverable C — the shelf, re-adjudicated

<!-- RESULTS-C -->

---

## §7. Draw ledger closure

<!-- RESULTS-DRAWS -->
