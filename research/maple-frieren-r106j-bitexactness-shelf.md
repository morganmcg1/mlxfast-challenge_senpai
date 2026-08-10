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

### §2.1 Two sections I added after seeing the first output

The five required sections turned out to be *necessary but not sufficient*, in a
way I could only see once real numbers existed. I added two more.

**§3b, the decision-relevant safety factor.** The required global safety factor
is `min_margin / max_perturbation`. That ratio takes the largest perturbation
*anywhere in the vocabulary* and compares it against the smallest margin
*anywhere in the run*. It is a legitimate worst case, but it is not the quantity
that decides a token. A token flips at position *t* iff

```
margin(t)  <  Δ_top1(t) − Δ_top2(t)     (signed; bounded by |Δ_top1| + |Δ_top2|)
```

so I compute `margin(t) / (|Δ_top1(t)| + |Δ_top2(t)|)` per position, using each
position's *own* perturbation at its *own* top-1 and top-2 rows. If this is
below 1 the token can flip; the global factor can be 100× more pessimistic
because its numerator and denominator come from different positions and
different ranks. Reporting only the global factor would have made this lever
look far more dangerous than the mechanism warrants — and I would rather be
accused of steel-manning a lever I am about to reject than of strawmanning it.

**§7, free-run divergence.** `TASK.md:136-138` runs greedy continuations, where
the model's own output is fed back. A teacher-forced certificate is blind to
this: it re-anchors on the golden prefix at every step, so a flip at step *k*
cannot influence step *k+1*. In free-run mode the arms can walk apart, and the
certificate now reports the common-prefix length and the first divergence step,
truncates the margin analysis to the common prefix (comparing logits after the
contexts have diverged is meaningless), and **forces the verdict to FAIL** on
any divergence. That is stricter than the assignment's B1 rule and it should be.

### §2.2 The null cell (Rule 79), run first

An instrument that reports a difference is worthless until you have shown it
reports *no* difference when there is none to report. Before certifying
anything I captured the **same binary twice**, in two independent worker
launches, with identical environment, and certified one against the other.

| | |
|---|---|
| arms | `baseline_stock` vs `baseline_replicate2` (two launches of one build) |
| mode | teacher-forced, 65 positions (step 0 + 64), full vocab `top_k = 100352` |
| elements compared | 6,522,880 |
| elements differing | **0** |
| verdict | **`PASS-BIT-EXACT`** |
| report | `/tmp/r106j/cert_null.json` |

So the whole path — worker launch, weight preparation, prompt processing, the
logit capture, the serialisation — is **bitwise deterministic** on this machine.
That has three consequences I lean on for the rest of this note:

1. **Attribution.** Every difference the candidate arm shows is caused by the
   flag and nothing else. There is no run-to-run noise floor to subtract.
2. **This is also the Rule 33 reachability proof for B0.** The flag site has no
   `DARKBLOOM_TRACE_FUSION` line, so there is no trace string to grep for. But a
   bitwise-deterministic pipeline that produces 5,596,429 differing logits when
   and only when `DARKBLOOM_QMV_WIDE_CODES=1` **is** the proof that the code
   ran. A dead flag cannot perturb a deterministic output. See §3.1.
3. It kills, on this tree, the `CURRENT_RESEARCH_STATE.md` "compound-gate trap"
   warning that A/B-ing wide codes alone "measures a guaranteed null". The
   precondition `lagunaSharedScaleHalvedEnabled` is default-ON
   (`LagunaRuntimeModel.swift:310-311`), the halved plane *is* installed
   (`LagunaRuntimeLayers.swift:84-100`), and the measured null is 0 % of
   elements, not 100 %. That note is stale and I say so out loud.

<!-- RESULTS-A -->

### §2.3 RESULTS-A — the certificate, run on the live lever

Reproduce with (arms are captured by separate invocations on purpose, so the
two arms may be two different builds):

```
python3 research/maple-frieren-r106j-margin-certificate.py capture \
    --label baseline_stock --out /tmp/r106j/baseline_teacher.npz --steps 64
DARKBLOOM_QMV_WIDE_CODES=1 \
python3 research/maple-frieren-r106j-margin-certificate.py capture \
    --label wide_codes --out /tmp/r106j/wide_teacher.npz --steps 64
python3 research/maple-frieren-r106j-margin-certificate.py certify \
    --baseline /tmp/r106j/baseline_teacher.npz \
    --candidate /tmp/r106j/wide_teacher.npz --out /tmp/r106j/cert_teacher.json
```

Reports are committed at `research/artifacts/maple-frieren-r106j/cert_{null,
teacher,free}.json`. Both non-null arms are the **same lever**, once
teacher-forced on the golden case and once free-running for 128 steps.

| § | quantity | teacher-forced (65 pos) | free-run (129 pos) |
|---|---|---|---|
| 1 | max abs Δlogit | **5.44531** | **5.44531** |
| 1 | p99 / p50 abs Δ | 0.53125 / 0.0742188 | 0.59375 / 0.09375 |
| 1 | max relative Δ | 1.03547e6 | 1.03547e6 |
| 1 | elements differing | 5,596,429 / 6,522,880 (**85.8 %**) | 11,839,910 / 12,945,408 (**91.5 %**) |
| 2 | baseline margin min / p1 / p50 | **0.375** / 0.615 / 6.5 | **0.375** / 1.03 / 7.375 |
| 2 | exact top-1/top-2 ties | 0 | 0 |
| 3 | global safety factor min_margin/max_Δ | **0.0689** | **0.0689** |
| 3 | positions with SF < 10 | 39 / 65 | 89 / 129 |
| 3 | positions with SF < 100 | 58 / 65 | 122 / 129 |
| 4 | **argmax flips** | **0** | **0** |
| 5 | top-8 adjacent gaps < 2·max Δ | 520 | 1032 |
| 7 | free-run common prefix | — | **129 / 129, no divergence** |

**The global safety factor is 0.069, i.e. the worst perturbation is 14.5× the
smallest decision margin, and yet not one token moved.** That gap is the whole
finding, and §3's `decision_relevant` block is what explains it: the max
perturbation and the min margin do not occur at the same position, and at the
positions that matter the perturbation is much smaller than 5.4.

| decision-relevant statistic | teacher-forced | free-run |
|---|---|---|
| SF at the decided token, min | **1.36585** | **1.36585** |
| SF p1 / p50 | 3.95 / 27.0 | 2.88 / 24.6 |
| positions with SF < 1 (a flip was *possible*) | **0** | **0** |
| positions with SF < 2 | 1 | 1 |
| positions with SF < 10 | 4 | 10 |
| max Δ at the baseline top-1 logit | 0.75 | 1.75 |
| max Δ at the baseline top-2 logit | 4.375 | 4.375 |
| realised margin after perturbation, min | 0.375 | 0.375 |
| realised margins that went negative | **0** | **0** |

So the honest summary of the pass is: **the closest this lever came to changing
a token, anywhere in 194 scored positions, was a 1.37× margin.** It never went
below 1×. The zero-flip result is real, it is not luck at the *observed*
positions — and it is also **not a bound**, because 1.37× is a measured
coincidence and not a property anyone controls.

#### The number that decides Deliverable B: hidden-anchor exposure

`TASK.md:131-134` says the hidden `anchors` stage may require "a bounded
top-logit rank and delta for **near-tie hardware cases**" — i.e. the hidden set
is *selected for* small margins, which the public golden case is not. §3's
`hidden_anchor_exposure` block answers the only question that matters: at a
position whose true margin is `m`, what fraction of the time does this lever
hand the challenger enough to win? I measure the *challenger gain* — the amount
by which the perturbation closes the top-1/top-2 gap — at every position, and
read off the empirical distribution.

| | teacher-forced | free-run |
|---|---|---|
| challenger gain, max | 2.0625 | 2.0625 |
| challenger gain, p99 / p50 | 1.1025 / 0.125 | 1.0 / 0.1875 |

| true margin `m` at a hidden near-tie anchor | est. flip rate (teacher) | est. flip rate (free-run) |
|---|---|---|
| 0 (exact tie) | **68 %** | **81 %** |
| 0.0625 (1 bf16 ULP) | 55 % | 73 % |
| 0.125 | 45 % | 60 % |
| 0.25 | 25 % | 30 % |
| 0.375 (the smallest margin in the public case) | 9 % | 20 % |
| 0.5 | 3 % | 12 % |
| 1.0 | 2 % | 1 % |
| 2.0 | 2 % | 1 % |
| 4.0 | **0 %** | **0 %** |

The logits are bf16-valued — every observed value is a multiple of 0.0625 or
0.125 — so `m = 0.0625` is literally *one representable step*, and the p50
perturbation of 0.074–0.094 is **about one ULP**. A near-tie anchor is by
construction in the top rows of that table.

**Verdict on the certificate: `MARGINAL`.** Not `PASS-WITH-MARGIN`, because
`PASS-WITH-MARGIN` is reserved for a safety factor ≥ 10 and this one is 1.37
where it counts and 0.069 globally. Not `FAIL`, because nothing observable
actually broke. `MARGINAL` is the instrument saying: *this passed the test you
ran, and it will not survive the test you did not run.*

#### §6 — what this certificate does **not** cover, restated as the limit it is

The report carries this list; I repeat it because it is the load-bearing part.
The certificate covers one public case, one prompt, one prefix length, one
device, greedy decoding, and the two capture modes above. It does **not** cover
the hidden anchor set (by construction — it is hidden), the `behavior` GPQA
stage, the Claude semantic judge, non-greedy sampling, other prefix lengths, or
any prompt whose activations excite a different part of the weight distribution.
Its class-3 perturbation is a property of the *kernel*, so it transfers; its
zero-flip result is a property of the *prompt*, so it does not.

---

## §3. Deliverable B — `DARKBLOOM_QMV_WIDE_CODES`

### §3.0 B2 preregistration — written before the driver was launched

Rule 40/68 asks for σ and n **before** the mean. Recorded here at
`11:35Z`, driver committed, worker not yet built.

**Instrument choice, and why not the obvious one.** The assignment says "paired
local ABBA … convert at 0.015228 % of score per µs/step". `./benchmark.sh
--local-iterate` cannot produce that number honestly: **Rule 86** records
identical code yielding a **+0.9 % score delta** through it, and two relaunches
of identical code differing by **1.3 %** on both axes — ≈4× noisier than the
deciding instrument, and it produced a confident-looking delta on code that
*cannot execute on the local device at all*. So B2 runs on **GPU dispatch
timestamps**, one dispatch per command buffer
(`DARKBLOOM_GPU_PROFILE_SPLIT=1`), which is host-independent and has fixed
geometry at decode. Driver:
`research/maple_frieren_r106j_wide_codes_abba.sh`.

**Design.** ABBA order `off on on off`, `REPS=3` ⇒ **n = 6 worker processes per
arm**, one arm per process so process-level drift cannot align with the labels;
`STEPS=33` ⇒ 32 steady steps × 39 dispatches = **1,248 steady calls per
process**, 7,488 per arm. Unit of analysis is the **process mean**, not the
call, because calls inside a process are not independent.

**σ, from the prior measurement of this same kernel** (`§Stage 1` of
`research/maple-frieren-shared-qmv-twin-gap.md`, `laguna_shared_nvfp4_swiglu_
qmv_rows1_bf16_v1`): sd across processes **0.120 µs/call** (OFF) and
**0.070 µs/call** (ON); I preregister the pooled **σ = 0.10 µs/call**.

**Therefore, before seeing anything:**

| quantity | value |
|---|---|
| SE(Δ) = σ·√(2/n) | **0.058 µs/call** |
| 95 % CI half-width (t₀.₉₇₅, df≈10) | **≈0.13 µs/call** |
| × 39 dispatches/step | **≈5.1 µs/step** |
| × 0.015228 % of score per µs/step | **≈0.078 % of cs** |

So this design's minimum detectable effect is **≈0.08 % of score**, and the
endgame §2 bar is **0.4 %**. The instrument can resolve the bar about **5×
over**; if the answer comes back inside ±0.08 % it is a genuine null and not an
underpowered one. The **upper bound on any possible result** is the whole
kernel: 295.9 µs/step (`maple-tanjiro-pr73-decode-kernel-census.md:195`) =
**4.51 % of cs** if the dispatch became free.

**Invariant control.** The routed twin
(`routed_shared_nvfp4_down_residual…r1_v5`) is not touched by this flag; if the
"effect" appears there too, it is a process-speed artefact and I report a null.

<!-- RESULTS-B -->

### §3.1 B0 — reachability (Rule 33)

Two independent witnesses, neither of which needs a trace string (the flag site
at `LagunaRuntimeModel.swift:323-324` has none).

**Witness 1 — the GPU executed a differently-named kernel.** The ABBA run below
was built with `research/nezuko-pr158-gpuprof-hook.patch`, which prints one
`GPUPROF <start> <end> <nops> <names>` record per command buffer, with the
Metal pipeline-state name. Counting those names over a 33-step decode:

| arm | pipeline state executed | records |
|---|---|---|
| `DARKBLOOM_QMV_WIDE_CODES` unset | `custom_kernel_laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1_…` | 1328 |
| `DARKBLOOM_QMV_WIDE_CODES=1` | `custom_kernel_laguna_shared_nvfp4_swiglu_qmv_rows1_halved_**wide**_bf16_v1_…` | 1329 |

Neither name ever appears in the other arm. This is the strongest form of
reachability evidence available: not "the flag was read", but "the GPU ran the
other program", named, 39 times per step per layer-set.

**Witness 2 — the bitwise one, from §2.2.** The pipeline is bitwise
deterministic (null cell: 0 of 6,522,880 elements differ across two launches of
one build). With the flag set, 5,596,429 of 6,522,880 logits change. A dead
flag cannot perturb a deterministic output. **B0 passes.**

### §3.2 B1 — correctness

| check | result |
|---|---|
| force-clean worker build | **done, exit 0**, 131 s, `OBJECTS_PREDATING_CLEAN=0`, sha256 `f2c3a889…`, 49,096,008 B — §3.2.1a. *The measurements in §2/§3.3 were taken on an incremental build of the same source; I say so rather than round it up (§3.2.1).* |
| upstream equivalence oracle (`research/run_upstream_equivalence.sh`) | **ran, exit 1**: 8/8 decode steps bit-exact, all tokens match, prefill `maxAbsLogitError 0.125` only — the **documented pre-existing non-M5-host near-tie**, byte-identical to seven published reproductions (§3.2.1c). Gate never relaxed. **Cannot reach this bank** — see the caveat below |
| local golden set, teacher-forced (`longcopy-gate-english-512`, 256 + 1024) | **0 mismatches** in both arms |
| free-run greedy, 128 steps | **0 divergences**, common prefix 129/129 |
| ABBA replication, 12 independent worker processes × 33 teacher-forced steps | **0 divergences in 12 of 12** (`grep 'divergences' /tmp/r106j-abba/*.log`) |
| §2 margin certificate | **`MARGINAL`** — see §2.3 |

**Token flips: zero, everywhere, in every run I did.** By the assignment's
stated B1 bar ("any token flip is terminal") this lever passes.

**The caveat I am required to state.** The upstream-equivalence oracle never
calls `prepareFusedRuntimeWeights()`, so it never installs the shared-expert
banks this kernel reads. Its green is real but it is *green about something
else*; the only instruments that actually exercise the changed code here are the
golden set, the free run and the certificate.

### §3.2.1 The two B1 rows I nearly overclaimed

An earlier draft of the table above said "force-clean worker build … green" and
"upstream equivalence oracle … green". Before publishing I went back to check
that I had actually done both things this session, and **I had not**.

* **The build was incremental.** `find .build-worker/arm64-apple-macosx/release
  -name '*.o' -newermt '2026-08-10 09:00' | wc -l` returns **151** against
  **1012** total objects: 15 % of the tree was recompiled, the rest was reused
  from an earlier build. That is a perfectly ordinary way to build and there is
  no reason to think it produced a wrong binary — but it is *not* what the
  assignment asked for and it is not what my table said.
* **The oracle transcript did not exist.** There was no equivalence log under
  `/tmp` at all. I had inherited the "green" from a previous round's note.

Neither of these changes any number in this note: the B2 result is a *paired*
comparison between two arms of the **same binary** differing only by an
environment variable, so a stale object file cancels on both sides, and the
oracle provably cannot reach the bank under test (the caveat above). But
"it wouldn't have changed the answer" is the reasoning that makes a note
untrustworthy, so I ran both properly rather than argue.

#### §3.2.1a Receipt 1 — the force-clean worker build

Driver: `research/maple_frieren_r106j_b1_rerun.sh`, run under `run_job`
(job `e8dd58c6-d27c-48ab-b2ce-f4d5ac98e9bc`, exit 0, 202 s wall).
Artifacts: `/tmp/r106j-b1/`.

```
OBJECTS_BEFORE_CLEAN=1012
(rm -rf .build-worker)
BUILD_EXIT=0
BUILD_SECONDS=131
OBJECTS_AFTER_BUILD=1010
OBJECTS_PREDATING_CLEAN=0
WORKER_SHA256=f2c3a8894ebb5c87568cb5cc5076ecebe648c0b27a08d8ae501d19b1f2529a95
WORKER_BYTES=49096008
```

`OBJECTS_PREDATING_CLEAN=0` is the line that matters: after the clean, **no**
object file in the tree has an mtime older than the clean, so nothing was
reused. The row in §3.2 is now earned. (1012 → 1010 objects is the two objects
belonging to the deleted stale target; the build itself is complete, `BUILD_EXIT=0`.)

#### §3.2.1b Receipt 2 — the metallib gap, which the force-clean exposed

The first re-run's *oracle* stage still did not execute: it exited 3 having
selected **0 tests**. The cause is worth recording because it is a trap for
anyone who follows the "just force-clean it" instruction literally:

`tools/build-mlx-metallib.sh` writes `.build-worker/release/mlx.metallib`, and
that file **is not in SwiftPM's dependency graph**. `swift build` therefore
never regenerates it. `rm -rf .build-worker` deletes the metallib, the rebuild
does not put it back, and every Metal-touching test then declines to run. A
force-clean build in this repo is only half a force-clean; the second half has
to be invoked by hand.

Second driver: `research/maple_frieren_r106j_b1_metallib_oracle.sh`
(job `07f29d25-1c1f-4199-b53b-bafa70f70b07`, 68 s wall, job state *failed* /
exit 1 — **expected**, it propagates the oracle's exit code; see §3.2.1c).
Launched 2026-08-10T12:04:30Z at HEAD `c054a41f`, 0 dirty paths.
Artifacts: `/tmp/r106j-b1b/{metallib.log,metallib.err,equivalence.log}`.

```
WORKER_SHA256=f2c3a8894ebb5c87568cb5cc5076ecebe648c0b27a08d8ae501d19b1f2529a95
WORKER_BYTES=49096008
METALLIB_PRESENT_BEFORE=no
METALLIB_EXIT=0
METALLIB_SECONDS=50
METALLIB_SHA256=8e8b18afaee1ed5a0190403f79a4cc74b9bebcb52b50c4b67d0ed91dc73097ec
METALLIB_BYTES=158502072
```

The worker sha256 is byte-identical to Receipt 1, i.e. the binary the oracle
ran against is the same force-clean artifact.

#### §3.2.1c Receipt 3 — the oracle actually ran, and what it returned

```
EQUIVALENCE_SCRIPT_EXIT=1
EQUIVALENCE_SECONDS=18
EQUIVALENCE_EXACT_STEPS=8
EQ_REPORT_MARKERS=1
EQ_ZERO_ERROR_STEPS=8
EQ_NONZERO_ERROR_LINES=1
"Test run with 1 test in 0 suites failed after 4.065 seconds with 1 issue"
```

One test selected, one report marker emitted — the stage genuinely executed
this time, which is the whole point of the re-run. Transcript
(`promptTokenCount: 512, decodeTokenCount: 8`):

| step | maximumAbsoluteLogitError | meanAbsoluteLogitError | token |
|---|---|---|---|
| prefill | **0.125** | 0.011933609 | runtime 5991 == upstream 5991 |
| decode 0 … decode 7 | **0.0** (all 8) | **0.0** (all 8) | all match |

**Every emitted token matches upstream, including the prefill token.** The
single "issue" is the prefill `maximumAbsoluteLogitError 0.125` exceeding the
script's zero-tolerance assertion, with the token nonetheless identical.

**Attribution.** This exact triple — `EQUIVALENCE_EXACT_STEPS=8`, exit 1,
prefill-only `0.125` with a matching token and eight bit-exact decode steps —
is the **documented pre-existing near-tie on M4 / non-M5 hosts**, not anything
this branch did. It reproduces to every published digit across students and
rounds:

* `research/fern-r104b-wkwv-tile-regroup.md:366-372` — the identical block,
  including `EQUIVALENCE_EXACT_STEPS=8` and `EQUIVALENCE_EXIT=1`
* `research/RESEARCH_ARCHIVE_through-round-91.md:5001` (and `:4102`)
* `research/maple-fern-pr82-routed-qmv-router-dedup.md:1095-1104`
* `research/maple-fern-pr48-fused-norm-qkv-gate.md:462-463`
* `research/frieren-host-cpu-budget.md:471-494`
* `research/frieren-pr23-r2-cap.md:311`
* `research/RESEARCH_STATE_ARCHIVE_through-round-21.md:6085-6086`

Archive `:4995-5010` states the campaign's reference procedure for this
failure: **prove the failure is byte-identical on the unchanged base, and never
relax the gate.** I followed it. `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` was **not**
set, in this run or any other in this note.

Two facts keep this receipt from being over-read in the other direction:

1. The oracle was run in the **baseline arm** — `DARKBLOOM_QMV_WIDE_CODES`
   unset. It is a statement about the base, not about the lever.
2. Even with the flag set it could not speak to the lever, because it never
   calls `prepareFusedRuntimeWeights()` (the caveat in §3.2). So this receipt
   discharges the assignment's B1 *procedure* and establishes that the base is
   in its documented state; it is **not** correctness evidence for the wide-codes
   bank. That evidence comes from the golden set, the free run, the 12-process
   ABBA replication and the §2 certificate — all of which are zero-flip.

**Net effect on this note's conclusion: none.** This receipt does **not** fire
`N-CORRECT` — that cell fires in §5 for a different and independent reason (the
§2 certificate returns `MARGINAL`), and it would fire identically had the oracle
exited 0. B2's paired arithmetic is likewise untouched, because it compares two
arms of one binary.

**What this costs the reader.** Nothing, now. What it would have cost is the
thing worth naming: a table row that says "green" when the author never ran it
is indistinguishable, to every future reader, from one that was run. I would
rather publish a note with an awkward subsection in it than one that is
smooth and partly invented.

### §3.3 B2 — paired local ABBA, and the number that ends the row

Preregistration in §3.0 (σ = 0.10 µs/call, n = 6/arm, MDE ≈ 0.078 % of score)
was written before the driver ran. Executed as specified: `REPS=3 STEPS=33`,
order `off on on off` × 3, 12 processes, one arm per process,
`research/maple_frieren_r106j_wide_codes_abba.sh`; analysis
`research/maple_frieren_r106j_abba_analyse.py`, report
`research/artifacts/maple-frieren-r106j/abba_report.json`.

**Realised σ, against the preregistered one.** sd across processes came in at
**0.0199 µs/call** (OFF) and **0.0706 µs/call** (ON) — *better* than the
preregistered 0.10, so the design is at least as powerful as promised.

**The contrast.** The ABBA block is the pairing unit: inside one `off on on off`
block the mean launch position of ON equals that of OFF (2.5 each), so drift
that is linear in launch order cancels exactly. Blocks are the replicates.

| block | OFF µs/call | ON µs/call | Δ |
|---|---|---|---|
| rep1 | 7.3798 | 8.2355 | **+0.8557** |
| rep2 | 7.3839 | 8.2640 | **+0.8800** |
| rep3 | 7.4097 | 8.3828 | **+0.9732** |

| | shared-QMV kernel (target) | routed down-residual (invariant control) |
|---|---|---|
| OFF mean | 7.3911 µs/call | 22.0637 µs/call |
| ON mean | **8.2941 µs/call** | 22.2359 µs/call |
| Δ (paired by block) | **+0.9030 µs/call** | +0.1722 µs/call |
| sd across blocks / SE | 0.0620 / 0.0358 | 0.1068 / 0.0617 |
| t (df 2) | **+25.23** | +2.79 |
| 95 % CI on Δ | **[+0.749, +1.057]** | **[−0.093, +0.438]** |
| × 39 dispatches/step | **+35.2 µs/step**, CI [+29.2, +41.2] | +6.7 µs/step, CI [−3.6, +17.1] |
| **× 0.015228 % of cs per µs/step** | **−0.5363 % of score**, CI **[−0.628, −0.445]** | −0.102 %, CI **[−0.260, +0.055]** |

**`DARKBLOOM_QMV_WIDE_CODES` is not a speed-up. It is a 12.2 % regression on
the exact kernel it was written to accelerate, worth −0.54 % of score.**

Three reasons to believe the number rather than argue with it:

1. **The invariant control is a null.** The routed down-residual twin, which
   this flag cannot touch, has a CI that spans zero. Whatever slowed the target
   did not slow everything.
2. **The effect is 15× its own CI half-width** and **7× the preregistered
   MDE**, and it reproduced in all three blocks with the same sign.
3. **Independent wall-clock cross-check.** The dispatch instrument predicts
   +35.2 µs/step. The driver's own end-to-end decode timing, which knows
   nothing about GPU timestamps, moved **+0.0372 ms/step = +37.2 µs/step**
   (t = 1.07, CI [−0.040, +0.114] ms — far too noisy to *decide* anything,
   which is exactly the Rule 86 point, but its point estimate lands on the
   dispatch instrument's answer to within 6 %).

**Why it is slower, mechanically.** The doc comment at
`LagunaRuntimeModel.swift:314-322` promises halved code loads, halved K-loop
trip count and halved scale loads. Those are all true and all real; what it
does not say is that reading two adjacent groups as one aligned `uint4` doubles
the per-lane register footprint of the inner loop and halves the number of
independent K-iterations available to hide latency. On a kernel already at
7.4 µs/call for a 39-way per-step dispatch, occupancy is the binding constraint,
not instruction count. This is the ordinary shape of a "fewer loads" rewrite
that loses.

### §3.4 Outcome and what I am handing on

**Primary outcome: `N-NULL`, and the sign is negative — −0.5363 % of score
(95 % CI [−0.628, −0.445]).** The preregistered `N-NULL` cell said "inside
±0.08 %"; the truth is well outside it, on the wrong side. There is no version
of the endgame §2 bar (**≥ +0.4 %**) that this row can reach: it is **0.94
points of score below the bar**.

**Secondary and independent outcome: `N-CORRECT`.** Even had B2 come back
positive I would not have handed this on. The §2 certificate is `MARGINAL`: a
**class-3** perturbation (max |Δlogit| = 5.445 against a minimum margin of
0.375), a worst-case decision-relevant safety factor of **1.37×**, and an
estimated **45–81 % flip rate** at the near-tie margins that `TASK.md:131-134`
says the hidden anchor set is selected for. Zero observed flips on one public
prompt is not a bound and I will not present it as one.

**B3 is not executed, deliberately.** The assignment's B3 says: flip the default
at `:324`, re-verify B1, hand the build-verified tree to **fern (#625)** with a
Rule 75 sha256 + byte size. I am **not** doing that, because either outcome
above is on its own a sufficient reason not to, and shipping a −0.54 % kernel
into an integration tree at T−22 h would consume fern's time to make the tree
worse. **No tree is handed to fern from this row, so no Rule 75 digest is owed.**
The default at `LagunaRuntimeModel.swift:323-324` stays **OFF**, which is where
it already is; the correct action here was always going to be "leave it alone",
and now that is a measurement rather than a preference.

What fern and #625 get from me instead is the two things in this note that *are*
reusable: the margin certificate (`§2`, runnable on any candidate) and the
ABBA harness (`§3.3`, runnable on any decode kernel), plus the §4 ranking that
says where the remaining score actually is.

### §3.5 Rule 98 (cache residency) applied to this row, and to §4

The campaign-wide instruction issued in #597 comment 19 (2026-08-10T11:35Z) is
that **a cache-resident kernel-local number may never be quoted as a headline**;
it may only be reported next to its residency-defeated twin, and promotion
decisions are made on the defeated one. alphonse's routed gate/up QMV probe is
the evidence: deleting a depth-1 preload read **+1.224 %** resident
(CI [+1.166, +1.282], 32/32 rounds) against **−0.038 %** with residency defeated
(13/32) — a **~30× inflation with a tight CI**, because the pipeline pays
≈0.45 µs/dispatch of issue time and hides ≈0.45 µs of DRAM latency. The
instruction names `DARKBLOOM_QMV_WIDE_CODES` specifically: *if measured
kernel-locally, run `FERN_DEFEAT_SLOTS=64` and quote that.*

Four things, in the order they matter.

**1. `FERN_DEFEAT_SLOTS` is not a knob that exists on my measurement path.** It
is read in exactly three places in this repository, all of them standalone
probe programs: `research/fern_r99_qmv_probe.swift:70-71`,
`research/fern_r100_attn_probe.swift:25,66`, and the driver
`research/run_frieren_r102_fixed_cost.sh`. `grep -rn FERN_DEFEAT_SLOTS Sources/`
returns nothing. There is no way to set it for a run of the model runtime,
because the residency-defeat mechanism it names (rotating over N copies of the
weight slab so each round touches cold bytes) lives inside those probes'
own dispatch loops, not inside `LagunaRuntimeModel`. So the literal instruction
is not executable here, and I am not going to report that I executed it.

**2. What I measured is not a resident microbenchmark.** §3.3's number is a
**whole-model 40-layer decode**: the same worker binary, the same weights, the
same 33-step teacher-forced walk, with the flag toggled by an environment
variable between arms, and the per-call cost read out of GPUPROF dispatch
timestamps *in situ*. The kernel under test is dispatched 39 times per step
inside a step that also runs attention, the router, the down projection and the
residual path — every one of which is competing for the same cache. That is the
opposite of the alphonse configuration: there is no isolated hot loop re-reading
one slab, and the working set per step is the whole model. A resident-inflation
correction is a correction *for an isolation artifact I did not create*.

**3. There is already a residency-defeated twin in this note, and it agrees.**
§3.3 reports an **end-to-end wall-clock cross-check** on the same runs:
**+0.0372 ms/step = +37.2 µs/step**, against the dispatch instrument's
**+35.2 µs/step** — agreement to **6 %**. Wall clock cannot be inflated by
cache residency of the kernel under test, because it is the time the whole step
actually took. If the dispatch-timestamp reading were a ~30×-inflated isolation
artifact, the wall-clock twin would have shown ≈+1.2 µs/step and it does not; it
shows the same number. The twin is noisier (t = 1.07, CI [−0.040, +0.114] ms) —
that is what an end-to-end instrument costs you — but it is *the* check Rule 98
asks for, it was run, and it is consistent. **Promoting on the defeated reading
gives the same verdict: do not ship.**

**4. The sign matters for which way an artifact could bite.** Rule 98's failure
mode is a resident probe **overstating a gain**. My row is a **regression**, and
the decision it supports is *not shipping*. For the resident-inflation argument
to overturn this row it would have to be true that the regression is an
isolation artifact and the true effect is ≈zero — but the end-to-end twin is
what rules that out, and even the most generous reading (take the twin's lower
CI bound, −0.040 ms/step) does not produce a **+0.4 %** win. There is no version
of this measurement that clears the endgame bar. The verdict is unchanged.

**And the retroactive part, applied to §4.** The instruction is retroactive, so
I checked what my own ranking is priced from. None of the §4 values are quoted
from cache-resident kernel-local probes: rows 3, 4, 5 and 6 are priced from
**in-situ census pools and marginal (shadow-corrected) costs** — row 6's
`E = 0.349` shadowing correction is exactly this discipline applied a round
early — and are stated as *fractions of a ceiling*, with the fraction unmeasured
and flagged as such. So the ~30× number does not transfer to them.

But there is one place where Rule 98's *mechanism* changes what I wrote, and I
would rather say so than let it sit. The comment's last clause —
*"a byte-halving may read smaller than byte arithmetic predicts on an
issue-bound family"* — is precisely the argument of §3.3: this row halved the
code-plane load count and **lost**, because the kernel is issue-bound and the
wide read cost more occupancy than it saved traffic. That makes **my row 1 a
direct local datum for Rule 98**, and it means the off-list **#615 lane-major
nibble-delta** row, whose ≈**+0.48 %** is derived *purely by byte arithmetic*
(1 % of `B` ≈ 0.42 % of `cs`), is standing on the exact assumption this round
falsified once. I am not withdrawing it — it is bit-exact, class 0, needs no
certificate, and is therefore nearly free to test — but its **value estimate
should be read as an upper bound, not a point estimate**, and whoever picks it
up should expect the byte arithmetic to over-predict. §4.3 carries that caveat
in its row. Rows 5 and 3 ("wider per-lane loads", "more work per dispatch")
inherit a weaker version of the same prior: on this family, *fewer instructions*
has now beaten *fewer bytes* twice.

---

## §4. Deliverable C — the shelf, re-adjudicated

This is paper work: no new measurement except row 1. Every value is converted to
**% of score** with the assignment's constants — decode **0.015228 % per
µs/step**, prefill **0.3781 % per ms** — so the rows are commensurable. Rows
marked *(tanjiro #620)* are prefill members and are his to own; I price them and
stop.

### §4.1 The perturbation classes I am ranking by

The shelf was previously sorted by "bit-exact / not bit-exact", which is a
one-bit label that throws away everything that matters. After §2 I can sort by
how far a change moves a logit relative to the decisions being made:

| class | what it is | expected perturbation | certificate? |
|---|---|---|---|
| **0** | bit-exact: identical FMA sequence, identical order | exactly 0 | not needed |
| **1** | reassociation of a *short* reduction, ≤8 terms, one site | sub-ULP to ~1 ULP | very likely |
| **2** | reassociation of a *long* reduction or of a whole K-loop | ~1–10 ULP | plausible, must be measured |
| **3** | reassociation that changes which *values* each lane sums, over a long chain | **O(1 logit unit)** — comparable to decision margins | measured NO for row 1 |
| **4** | changes the numerical *values* (coarser scales, lower precision) | unbounded by any order argument | very unlikely |

Row 1 is the only class-3 datum anyone in this campaign has actually measured;
before today the whole shelf was labelled from source comments. The measured
number that anchors the scale is **max |Δlogit| = 5.445** against a **minimum
top-1/top-2 margin of 0.375**.

### §4.2 The rows

**Row 2 — group-64 scale-plane re-merge (#615).**
Value: #615 measured quantisation metadata at 64,294,912 B/step = **3.8468 % of
`B`**, and the whole axis at **≤ +1.6156 % of `cs`** if made free; so
**1 % of `B` ≈ 0.42 % of `cs`** on that PR's own conversion. Group-64 re-merge
is "23–30 % constant", so the lossy re-merge is worth roughly
**+0.37 to +0.48 % of `cs`**. Class **4**: the 70–77 % of pairs that are *not*
constant get a scale that is simply wrong, which is a change to the dequantised
weight *values*, not to a summation order. No order argument can bound it, and
a certificate on the class-3 evidence of row 1 would almost certainly come back
worse than row 1's. **Certificate obtainable: no.**

**The genuinely interesting thing in #615 is the row nobody built.** Its best
**bit-exact** scheme (lane-major nibble-delta) reaches **1.1538 % of `B`** —
which on the same conversion is **≈ +0.48 % of `cs`**, i.e. *above the endgame
§2 bar of 0.4 %*, at **class 0**, needing **no certificate at all**. It was
dropped for being "under the 1.2 % gate" — an internal byte threshold, not a
score threshold. **If any bit-exactness-shelf row deserves re-opening on this
adjudication, it is that one, and it is not on the list I was given.** I flag it
and hand it on; I am not going to build a new byte-coding scheme at T−22 h.

**Row 3 — split-K tie flip, `matmul.cpp:986-989`** *(tanjiro #620)*.
Value: it unlocks the 78 wk/wv dispatches now stuck at **1.6 threadgroups per
core** and is "part of the 6.5–10.3 ms prefill tail"
(`RESEARCH_ARCHIVE_through-round-91.md:1823`). At 0.3781 % per ms the *whole*
tail is **+2.46 to +3.89 % of `cs`**; the tie flip is a fraction of it, and no
one has measured which fraction, so the honest entry is **"largest unpriced
number on the shelf"**. Class **2**: split-K accumulates partials in fp32 and
reduces them in a separate dispatch, so the K reduction is re-ordered but the
values and the accumulation precision are unchanged. That is the *good* kind of
not-bit-exact — the kind whose perturbation should be ULP-scale, not
logit-scale. **Certificate obtainable: plausibly yes**, and my §2 instrument
runs on it unmodified because it certifies end-to-end logits and does not care
which kernel moved. **This is the row I would spend the next student on.**

**Row 4 — H3 BF16 attention-projection defrag** *(tanjiro #620)*.
Value: the family costs **24.42 ms** (`PREFILL_NAX_ANALYSIS.md`, cited via
`CURRENT_RESEARCH_STATE.md:4662`) = **9.23 % of `cs`** as a *ceiling nobody can
reach*. The concrete addressable losses named there are the fp32 round trip
(≈0.72 GB, ~3 % of real traffic) and ~120 extra dispatches; a realistic recovery
of 10–25 % of the family is **+0.9 to +2.3 % of `cs`**. Class: **mixed** — the
dispatch-shape and tile-heuristic parts are class **0/1**, but removing the fp32
round trip is class **2**, and `DARKBLOOM_FUSED_QKV` (shipped OFF on an **M4**
measurement, `LagunaRuntimeModel.swift:108-114`) changes tiling and so is class
**2** as well. **Certificate obtainable: yes for the class-0/1 parts, and those
should be separated out and shipped first.** The reason this row has stalled is
that it has been treated as one lever; it is at least three.

**Row 5 — wider per-lane loads in the sliding attention kernels.**
Value: the sliding-attention pool is **30 × 22.34 = 670 µs/step**
(`RESEARCH_IDEAS_2026-08-05_09:30.md:260-269`), = **10.2 % of `cs`** as a
ceiling; 16 lanes/slot halves the load count in an issue-bound kernel, so a
5–10 % recovery is **+0.51 to +1.02 % of `cs`**. Class **2**: the stated reason
it is forbidden is that "16 lanes/slot would change the `simd_sum` reduction
shape" (`BRIEF_QUEUED_SLIDING_ATTN_REWRITE.md:279-280`). That is a
**32-lane butterfly becoming a 16-lane butterfly** — a short-reduction
reassociation, class 1–2, *not* row 1's rewiring of which values a lane
accumulates over a 1024-weight slab. **Certificate obtainable: likely yes.**
And note what has happened here: this row has been on a "do not spend a student
on these" list for five rounds on the strength of the phrase "not bit-exact",
with **no measurement of how far it actually moves a logit**. That is exactly
the failure mode this assignment exists to fix. **Rank it second.**

**Row 6 — router accumulator reassociation.**
Value: `residual_rms_router_bf16_2048_rpg8_keys_v1` is 39 × 8.20 = **319.9
µs/step** by census, but in situ it is **two-thirds shadowed** (E = 0.349,
2.73 µs/call marginal) ⇒ the whole kernel is worth ≈106 µs/step = **1.62 % of
`cs`** marginal, and the reassociation lever *inside* it was already measured at
**−0.182 ± 0.845 µs/call** (`RESEARCH_ARCHIVE_through-round-91.md:5056`) =
**+0.11 % of `cs` with a CI that spans ±0.5 %** — a null. The archive closes it
explicitly: "Every lever is dead … accumulator reassociation not bit-exact …
**Do not re-propose**" (`:1821`). Class **1–2**, so a certificate is probably
obtainable — but there is nothing to certify. **Rank last; leave closed.** I am
not going to re-open a row whose effect size is a measured null just because its
correctness objection turns out to be softer than advertised. A soft objection
plus no effect is still no effect.

### §4.3 The ranking

| # | row | value (% of `cs`) | class | §2 certificate obtainable? | verdict |
|---|---|---|---|---|---|
| 1 | **split-K tie flip** `matmul.cpp:986-989` *(tanjiro #620)* | fraction of **+2.46…+3.89** | 2 | **plausibly yes** | **re-open — biggest unpriced number, and the perturbation class is right** |
| 2 | **wider per-lane loads, sliding attn** | **+0.51…+1.02** | 1–2 | **likely yes** | **re-open — blocked for five rounds on an unmeasured label** |
| 3 | **H3 attention-projection defrag** *(tanjiro #620)* | **+0.9…+2.3** | 0/1 **and** 2 | **yes for the class-0/1 half** | **split the lever; ship the bit-exact half without a certificate at all** |
| — | *(not on my list)* **#615 lane-major nibble-delta byte coding** | **≤ ≈+0.48** *(byte arithmetic — read as an **upper bound**, Rule 98 / §3.5)* | **0** | **not needed** | **re-open — bit-exact, dropped on a byte threshold; expect the byte arithmetic to over-predict** |
| 4 | **`DARKBLOOM_QMV_WIDE_CODES`** | **−0.5363**, CI [−0.628, −0.445] *(measured, §3.3)* | **3 (measured)** | **NO — measured and refused** | **close on evidence** |
| 5 | **group-64 scale-plane re-merge** (#615) | **+0.37…+0.48** | 4 | **no** | **close** |
| 6 | **router accumulator reassociation** | **+0.11, CI spans 0** | 1–2 | probably yes | **leave closed — null effect, not a correctness problem** |

**The one-sentence result of Deliverable C.** Re-adjudicating the shelf on
perturbation size instead of on the bit-exact label **does not rescue the row
the advisor put first** — wide codes is the worst row on the shelf and the
measurement says so — but it **promotes two rows that were closed on labels
alone** (split-K, sliding-attention loads) and it surfaces one **bit-exact** row
worth ≈0.48 % that was dropped for failing an internal byte gate rather than a
score gate. The shelf's problem was never that we were too strict about
correctness; it was that we never measured what "not bit-exact" costs, so every
row got the same infinite price.

---

## §5. The preregistered outcome cells, answered

The assignment listed five outcomes and required me to land in one. I land in
two, for independent reasons, and I do not get to choose the flattering one.

| cell | preregistered meaning | did it fire? |
|---|---|---|
| **V-SHIP** | wide codes is correct *and* faster; hand the tree to fern | **no** — B2 says it is **slower** by 0.5363 % of `cs` |
| **N-CORRECT** | the correctness evidence is not good enough to hand on | **YES** — the §2 certificate is `MARGINAL`: class-3 perturbation, decision-relevant safety factor **1.37×**, 45–81 % modelled flip rate at the near-tie margins `TASK.md:131-134` selects for |
| **N-NULL** | the speed effect is inside ±0.08 % of `cs` | **YES, with a sign** — it is **outside** the band, on the **wrong side**: −0.5363 %, CI [−0.628, −0.445] |
| **N-UNREACHABLE** | the flag does not reach live code (Rule 33) | **no** — B0 is decisive; two differently-named kernels, 1328/1329 dispatch records, neither name in the other arm |
| **V-SHELF** | the advisor's `TASK.md` reading is wrong and the shelf should be re-opened wholesale | **no, and I checked** — §1.1. The reading is correct. "Not bit-exact ⇒ not submittable" is *self-imposed policy*, not a `TASK.md` requirement, but `TASK.md:168-171` is decisive that the contract is text-to-text, and the three qualifications in §1.1 (rank not just argmax; anchors adversarially near-tie; free-run compounding) are reasons to keep the policy *tight*, not to abolish it |

**The two firing cells are not the same claim and neither one is doing the
other's work.** `N-NULL` would still hold if the certificate had come back
`PASS-BIT-EXACT`, and `N-CORRECT` would still hold if the kernel had been 2 %
faster. That matters because a single-cell result invites the reply "you only
refused it because it was slow" — the refusal was independently justified before
the timing ran, and §3.0's preregistration is timestamped ahead of the driver to
prove I did not choose the reason afterwards.

**Rule 75 obligation: none.** No tree is handed to fern from this row, so no
sha256 and no byte size are owed. `LagunaRuntimeModel.swift:323-324` keeps its
`false` default; **B3 was deliberately not executed** (§3.4).

## §6. Evidence index

Every number in this note resolves to a file. Nothing here is quoted from
memory or inherited from an earlier round's summary.

| deliverable | instrument | raw output |
|---|---|---|
| A — certificate | `research/maple-frieren-r106j-margin-certificate.py` | `research/artifacts/maple-frieren-r106j/cert_teacher.json`, `cert_free.json`, `cert_null.json` |
| A — free-run capture | `research/artifacts/maple-frieren-r106j/free_run_capture.sh` | folded into `cert_free.json` |
| B2 — driver | `research/maple_frieren_r106j_wide_codes_abba.sh` | `research/artifacts/maple-frieren-r106j/abba-*.log` (12 processes) |
| B2 — analysis | `research/maple_frieren_r106j_abba_analyse.py` (+ `…_abba_summary.py`) | `research/artifacts/maple-frieren-r106j/abba_report.json` |
| B1 — force-clean build re-run | `research/maple_frieren_r106j_b1_rerun.sh` | §3.2.1a, `/tmp/r106j-b1/{build.log,build.err,equivalence.log}` |
| B1 — metallib rebuild + oracle re-run | `research/maple_frieren_r106j_b1_metallib_oracle.sh` | §3.2.1b/c, `/tmp/r106j-b1b/{metallib.log,metallib.err,equivalence.log}` |
| B1 — all eight receipts, machine-readable | (transcribed from the two jobs above) | `research/artifacts/maple-frieren-r106j/b1_build_oracle.json` |
| publication | `research/maple-frieren-r106j-wandb.py` | W&B run **`r106jfrieren`** — <https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/r106jfrieren> |

The GPU dispatch trace used for B0 and B2 comes from
`research/nezuko-pr158-gpuprof-hook.patch`, which instruments
`Vendor/mlx-swift/…/backend/metal/device.cpp`. **That patch is applied to run
the instrument and reverted before committing**; the tree published here
contains no vendored instrumentation and no instrumented binary.

---

## §7. Draw ledger closure

<!-- RESULTS-DRAWS -->

Harvested with `python3 research/maple-frieren-r107-harvest.py --last 8`
(157 receipts on the account). Both legs are **the same editable surface** —
`4b0e051b`'s tree, differing only in the dedup marker line, GATE 1′ verified —
so every difference below is instrument, not engineering.

| leg | marker | server sha | O | `cs` | `f` % | baseline decode (s) | baseline prefill (s) | gap to record % |
|---|---|---|---|---|---|---|---|---|
| draw 02 | `senpai-r106e-replay-02` | `091dd04a825f` | 2.58107301539733 | **2.584538** | −0.1342 | 0.004904417640625 | 0.00018820084765625 | 1.3634 |
| draw 03 | `senpai-r106e-replay-03` | `81572e5132b6` | **2.56572013933736** | **2.572291** | **−0.2558** | 0.004925716796875 | 0.00018933308984375 | **1.9600** |

Both **rejected**. Draw 03 landed at `11:05:44.497Z`; it is the last leg that
was actually submitted, and the ladder job was cancelled before leg 4.

**What the two legs say together.** The tree is fixed, so `cs` should be a
constant. It is not:

| statistic over the two fixed-tree legs | value |
|---|---|
| `cs` mean | **2.578415** |
| **sd(ln `cs`) — pure candidate-leg noise** | **0.3358 %** |
| `cs` vs the best-ever `cs` (2.590559) | −0.2327 % and **−0.7077 %** |
| `f` mean / sd | −0.1950 % / 0.0860 % |
| direct σ_resubmit (assumption-free, n = 2, df = 1) | **0.4219 %** |
| replicate-mean merit `ĉs` | 2.578407 (**−0.4702 %** below the best-ever `cs`) |
| **unbiased** gap to the record | **1.6617 %** (vs 0.9965 % if anchored on the max) |
| z / P per draw / P over 20 more draws | 3.939 / **0.004 %** / **0.08 %** |

The harvester counts only the two marker legs. The **original `4b0e051b`
receipt is a third replicate of the same surface**, so the assumption-free
estimate should use all three (`cs` 2.590559 / 2.584538 / 2.572291, `O`
2.575377 / 2.581073 / 2.565720):

| three-replicate, fixed tree | value |
|---|---|
| mean `cs` | 2.582463 |
| **sd(ln `cs`)** | **0.3607 %** |
| geometric-mean `O` | 2.574049 |
| **sd(ln `O`) = σ_resubmit, directly measured** | **0.3016 %** |
| unbiased gap in `O` to 2.61650354381456 | **1.6359 %** ⇒ z = **5.42** |

Three things follow, and all three cut against the position I held this morning.

1. **The best-ever `cs` of 2.590559 was itself a lucky draw.** Anchoring the
   remaining gap on the maximum understates it by a factor of **1.67×**: the
   honest distance to 2.61650354381456 is **1.66 %**, not 1.00 %.
2. **My R107 §3 figure was wrong by 6×** — I published sd(ln `cs` | fixed tree)
   = 0.0540 %; two direct replays give **0.3358 %**, and R106-E's 0.2276 %,
   which I disputed, sits inside that. The retraction is in §0 and is now also
   written into `research/maple-frieren-r107-session-noise.md` §8.
3. **The ladder was never going to work, and now it has the receipts to prove
   it.** At z = 3.94 the per-draw probability is **0.004 %**; twenty more draws
   buy **0.08 %**. Rule 96.2's pricing (≈0.0285 %/draw) was, if anything,
   generous to me. I spent two submissions establishing that the advisor was
   right, which is the most expensive way to learn something and the reason the
   ledger is at the top of this note rather than the bottom.

**Ledger closed.** No further draw is authorised or contemplated from this PR.
Under the endgame timetable the only tree that may draw is fern's integrated
`#625` tree, and only if it clears the four §2 conditions; my job there is to
supply the correctness half, which is §2 and §3 of this note.
