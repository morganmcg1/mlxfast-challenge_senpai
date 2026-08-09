# R103-A — reproduce the missing ~19 µs/step off-M5 and localise it to a kernel

Student: maple-frieren · PR #571 · branch `maple-frieren/r103-missing-microseconds-localize`
Assignment `maple-r103-a-missing-microseconds-localize`, revision `r103-a-rev1`
Base `0f6862d099252d40a807df30abfbbd7c9cd596ae`

Measurement host: **Apple M4 Pro**, 14 CPU, 48 GiB unified memory, peak memory
bandwidth **266.3 GB/s** (M5 Max reference: 610 GB/s measured / 614 GB/s
nominal). The ranked host is M5 Max; every number below is off-M5 evidence and
is labelled as such.

---

## § 1 Preregistration

**Written and committed before any timed run.** Commit history is the proof:
this section is committed in isolation, ahead of the build and timing commits.

### 1.1 The quantity under test

Two official receipts bracket the round-100 frontier adoption plus the three
restorations that followed it:

| | revision | receipt | decode µs/step | prefill µs/token |
|---|---|---|---|---|
| OLD | `30f752df` (merge of PR #481) | `7ce1262d` | 4893.712 | 188.043 |
| NEW | `0f6862d0` (this assignment's base) | `e08d759f` | 4913.117 | 187.857 |

The published decode metric is not the marginal step. The teacher-forced decode
axis is a 512-token seed prefill `S` followed by 128 one-token steps `T`, and
the reported figure is `(S + 128·T)/128 = S/128 + T`. Using the prefill axis to
price `S = 512 × prefill_µs_per_token`:

```
S_old  = 512 × 188.043 = 96,278.0 µs      S_old/128  =  752.172 µs
S_new  = 512 × 187.857 = 96,182.8 µs      S_new/128  =  751.428 µs

T_old  = 4893.712 − 752.172 = 4141.540 µs/step
T_new  = 4913.117 − 751.428 = 4161.689 µs/step

ΔT     = T_new − T_old      = +20.149 µs/step
ΔT/T_old                    = +0.4865 %
```

The reported decode delta is +19.405 µs/step, and prefill actually *improved*
(ΔS = −95.2 µs, worth −0.744 µs/step on the decode axis). Removing that prefill
credit shows the regression concentrated in the marginal step is **larger** than
the headline: **+20.149 µs/step, +0.4865 % of the OLD steady step**. This is the
quantity R103-A must reproduce. Prefill is explicitly *not* under test — the
frontier is already ahead of Arm R there.

### 1.2 Revisions

* **OLD** `30f752df` — confirmed present in this checkout, `git cat-file -e` OK.
* **NEW** `0f6862d0` — the assignment base; the branch head `657e9ba5` carries an
  empty diff against it (assignment metadata only), so the working tree already
  *is* NEW.
* 318 commits separate them. Fallback anchors if OLD refuses to build, in
  order: `74e89d71` → `e510bb3d` → `6ada66c9`. `74e89d71` and `6ada66c9` are
  ancestors of OLD; `e510bb3d` is not, and using it would change the contrast's
  meaning, so it is a last resort and would be reported as such.

### 1.3 Instrument and why not `--local-iterate`

`./benchmark.sh --local-iterate` reports `S/128 + T`, so it dilutes the effect
under test with a prefill axis that moved the other way, and it costs a thermal
gate per measurement. The instrument is instead
`research/decode_probe.py` steady-step wall time against snapshotted worker
binaries: it measures `T` directly, drops step 0, and is teacher-forced against
`correctness_prompts/public_longcopy_gate_english_512_256.json` (512 prompt
tokens, 256 expected tokens). At `--steps 250` every step is teacher-forced
(the probe free-runs only past index 254), so the token stream is fixed by the
fixture and identical across arms by construction.

Both arms run the **shipped** runtime end to end. Consequences:

* **Rule 77** (reproduce shipped dispatch geometry and name it) is satisfied by
  construction — the geometry is whatever `LagunaRuntimeModel.swift` dispatches
  in each revision, not a re-authored harness. Rung 2 names the geometry per
  kernel from the in-situ census.
* **Rule 71** (SLC-resident *and* SLC-defeat modes) is satisfied by
  construction for an in-situ measurement: the working set is the real
  21.6 GB resident text tower, which is neither an artificially SLC-resident
  microbenchmark footprint nor an artificial SLC-defeating one. No synthetic
  footprint is introduced at either rung, so there is no second mode to run.
* **Rule 80** (bandwidth always divided by host peak in the same sentence) —
  rungs 1 and 2 report wall time, not bandwidth. If any GB/s figure appears it
  will carry `÷ 266.3 GB/s` in the same sentence.

### 1.4 Design: 4-slot position-matched ABBA with an embedded null

Four snapshotted binaries per repetition:

```
SLOTS = [oldA, old, new, oldB]
order = SLOTS  if rep is even  else  reversed(SLOTS)
```

`oldA` and `oldB` are **byte-identical copies of the OLD binary**. Over any even
number of repetitions:

| arm | positions occupied | mean position |
|---|---|---|
| `old` | {2, 3} | 2.5 |
| `new` | {3, 2} | 2.5 |
| `oldA` | {1, 4} | 2.5 |
| `oldB` | {4, 1} | 2.5 |

So the **real contrast** `new − old` is position-matched on the two *interior*
slots, and the **rule-79 identical-code null** `oldB − oldA` is position-matched
on the two *exterior* slots, in the same session, sharing the same drift.

The asymmetry is deliberate and is declared here: exterior slots absorb more
session drift than interior ones, so the null is a **conservative upper bound**
on the noise floor that applies to the real contrast. A null that is tight
therefore certifies the real contrast; a null that is wide does not by itself
condemn it, and that case will be reported rather than spun.

`REPS = 26`. The **first two repetitions are discarded** (one full even/odd
cycle, so the discard cannot unbalance position matching), leaving
**K = 24 paired observations** for each of the real contrast and the null —
above the K ≥ 16 floor. `--steps 250` per slot.

### 1.5 Preregistered thresholds — fixed now, not after seeing data

> **Superseded in one place by § 1.5c.** The `+20.0 µs/step` magnitude bar in the
> table below is raised to `+32.4 µs/step` on advisor instruction
> ([feedback `r103-a-fb1-reconcile-against-T-not-D`][fb1], 2026-08-09T21:45:56Z).
> Everything else in § 1.5 — the precision target, the four outcome codes, the
> secondary relative read — stands exactly as written. The original text is left
> untouched so the amendment is auditable.
>
> [fb1]: https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/571#issuecomment-5234001934

**Precision target.** Paired 95 % CI half-width on the real contrast
**< 8 µs/step**. The achieved half-width is reported whatever it is; if it lands
≥ 8 µs/step that is stated as a power failure and the verdict is downgraded
accordingly, not quietly widened.

**Decision rule** on `ΔT_M4 = mean(T_new − T_old)`, 95 % CI from the paired
t-distribution on K = 24 pairs:

| # | condition | verdict | action |
|---|---|---|---|
| 1 | point estimate ≥ **+20.0 µs/step** *and* CI lower bound > 0 | reproduced off-M5 | proceed to rung 2 |
| 2 | CI **upper** bound < **+20.0 µs/step** and CI upper bound > 0 | does not transfer at M5 magnitude → M5-specific | **report and stop** |
| 3 | CI upper bound < 0 | sign flip, NEW faster on M4 | **report and stop** |
| 4 | CI contains +20.0 but point estimate < +20.0, or CI contains 0 while spanning +20.0 | underpowered | report as **inconclusive-underpowered**; no rung 2 |

Outcome 4 exists so that an ambiguous CI cannot be argued into outcome 1 after
the fact.

**Secondary read (relative transfer).** The M5 effect is +0.4865 % of the steady
step. `T_old` on M4 is not yet known, so the relative equivalent of the 20 µs
bar cannot be fixed in absolute terms in advance; the *relative* effect
`ΔT_M4 / T_old_M4` and its CI are reported alongside, and compared with
0.4865 %. This is a descriptive companion, **not** a second chance at outcome 1:
the primary decision uses the absolute +20.0 µs/step bar from the assignment
exactly as written. If the two disagree — e.g. the absolute bar is missed but
the relative effect matches M5 — that disagreement is reported as the finding.

### 1.5a Addendum — per-slot statistic (declared before any timed run)

§ 1.3 said only "drops step 0". Fixing the rest of the estimator now, before
any timing data exists, so it cannot be chosen to suit the answer:

* **Primary per-slot statistic: the median of steps 1 … 249** (0-indexed;
  step 0 is the first decode after the seed prefill and is not a steady step).
  The median is used because a decode slot is occasionally interrupted by the
  OS, and a single 50 ms outlier moves a 250-sample mean by 200 µs — two orders
  of magnitude above the effect under test.
* **Declared secondaries, reported alongside whatever they say:** the 10 %
  trimmed mean and the raw mean over the same window.
* The preregistered outcome in § 1.5 is decided on the **median** contrast. The
  secondaries are reported for transparency and any disagreement between them
  is reported as a finding, not resolved by picking a favourite.

This addendum is committed after the rung-0 build and before the rung-1 timing
job starts; the commit order is verifiable from history.

### 1.5b Addendum — retained one-time-cost diagnostics (declared before any timed run)

An independent design critique pointed out a real blind spot in § 1.3: a
fresh worker process per slot plus a steady-state estimator plus discarded
warm-up repetitions is a design that *cannot see* a one-time in-window cost.
That matters, because one of the candidate mechanisms for the M5 regression is
exactly that: `ΔT × 128 = 2.58 ms`, which is the order of a handful of extra
Metal pipeline creations or a JIT compile inside the timed window. Under the
§ 1.5 estimator such a mechanism reads as a clean null, and a clean null would
then be over-interpreted.

The design is not changed — the outcome rule still runs off the steady median,
and the warm-up repetitions are still excluded from the verdict. What is added
is that the discarded data is **kept and reported**:

* **`step0`** — the first decode step of each slot, paired the same way.
* **`mean_first128`** — the mean of steps 0 … 127, which mirrors the window the
  official harness actually times, so a one-time cost that the official metric
  amortises over 128 steps appears here at the same dilution.
* Both contrasts are additionally reported over the **discarded warm-up
  repetitions** and over **all repetitions**, not only the analysed ones.

These are diagnostics, not decision variables: they do not enter § 1.5 and
cannot change the outcome code. Their purpose is to stop a null on the steady
median from being written up as "there is nothing here" when the instrument was
never able to see a one-time cost in the first place. The corresponding
analyser change is committed before the rung-1 timing job starts.

The 40-step pipeline smoke test run before this commit is validation of the
driver and the parser only. Its numbers back no verdict and are not used
anywhere in §§ 3–6.

### 1.5c Addendum — advisor correction: the contrast is in `T`, and the bar rises to 32.4 µs/step (declared before unblinding)

Advisor feedback `r103-a-fb1-reconcile-against-T-not-D` arrived at
2026-08-09T21:45:56Z, after the rung-1 job started and before any aggregate
statistic had been computed. It makes three changes, all adopted.

**(a) The target quantity is `T`, not `D`.** This experiment was already
specified in `T`: § 1.1 derived `D = 4P + T` from the harness definition
`decode_s_per_token = (S + 128·T)/128` with `S = 512·P`, computed
`T_old = 4141.540`, `T_new = 4161.689` and **`ΔT = +20.149 µs/step`**
independently of the advisor, and § 1.3 rejected `./benchmark.sh
--local-iterate` precisely because it reports `D` and dilutes the effect. So
there is nothing to repair in the design — but the number in the arm's title
(“~19 µs/step”) is the `D`-delta and the reconciliation target is **20.15**.
Every § 4/§ 5 figure is against 20.15.

**(b) The M4 instrument measures `T` directly; no `D → T` conversion is
applied.** `research/decode_probe.py` runs the 512-token seed prefill, then
times **each** subsequent single-token decode step individually and prints the
per-step distribution. The per-slot statistic (§ 1.5a) is the median of steps
1 … 249, i.e. steady post-prefill steps with the first one dropped. Seed
prefill is outside the measured window entirely, so the M4 numbers in § 4 are
`T` and are directly comparable with the M5 `T` figures — the failure mode the
advisor names, silently comparing an M4 `T` against an M5 `D`, cannot occur
here.

*Limitation, stated rather than papered over:* the probe does not print a
prefill time, so this report cannot publish an M4 `P` or a synthetic M4 `D`.
Adding that would mean discarding the running rung-1 session, which is not a
trade worth making for a quantity the primary contrast does not use. It is
recorded as a follow-up in § 6.

**(c) The magnitude bar rises from +20.0 to +32.4 µs/step M4-equivalent.**
`ΔT_M5 = 20.149` at the R1 M4→M5 transfer factor 0.622 gives
`20.149 / 0.622 = 32.39 µs/step` on M4. The § 1.5 table's `+20.0 µs/step` is
replaced by **`+32.4 µs/step`** everywhere it appears; the four outcome codes,
the < 8 µs/step precision target and the relative secondary are unchanged.

| # | condition (amended) | verdict | action |
|---|---|---|---|
| 1 | point estimate ≥ **+32.4 µs/step** *and* CI lower bound > 0 | reproduced off-M5 at M5 magnitude | proceed to rung 2 |
| 2 | CI **upper** bound < **+32.4 µs/step** and CI upper bound > 0 | does not transfer at M5 magnitude → M5-specific | **report and stop** |
| 3 | CI upper bound < 0 | sign flip, NEW faster on M4 | **report and stop** |
| 4 | CI contains +32.4 but point estimate < +32.4, or CI contains 0 while spanning +32.4 | underpowered | **inconclusive-underpowered**; no rung 2 |

**Disclosure (required, and it cuts against me).** Before this amendment I had
seen the interim per-slot medians of **rep00 only**, scrolled from the running
job's log: oldA 8239, old 8234, new 8261, oldB 8242 µs, i.e. a single-rep real
contrast of about +27 µs and a single-rep null of about +3 µs. One repetition
out of 24 has no decision value and no CI, but I am not blind and the record
should say so. Two things bound the damage: the amendment is **mandated by the
advisor**, not chosen by me, and it moves the bar **strictly upward** — from
+20.0 to +32.4 — which can only make outcome 1 *harder* to reach. A glimpse of
a +27 µs single rep cannot have been used to manufacture a positive by raising
the threshold above it. Had the correction moved the bar downward I would have
had to say the preregistration was compromised.

*Second, smaller disclosure, for completeness.* While polling the running job
for progress I also saw one further single-slot summary line in passing
(`rep10-pos2-old`, median 8.237 ms). It is one arm of one repetition, not a
contrast, and it was seen **after** the +32.4 bar was already committed to git
(`97f5ae1`), so it cannot have influenced the threshold. From that point on I
polled with `grep -c` on the slot-completion and divergence lines only, so no
further timing values entered my view before the analyser ran. The audit trail
is the commit order: bar first, data second.

**Two declared secondary reads, neither a decision variable.**

1. *Proportional scaling.* The M5 effect is 0.4865 % of the M5 steady step. If
   the effect scales with the step time rather than by the R1 factor, the M4
   equivalent is `0.004865 × T_old_M4`, which at the observed M4 step of about
   8 200 µs is roughly **40 µs/step** — meaningfully above the 32.4 bar. The
   relative contrast `ΔT_M4 / T_old_M4` and its CI are reported against
   0.4865 % alongside the absolute result. A disagreement between the R1-factor
   bar and the proportional bar is reported as a finding.
2. *Any-regression flag.* Whether the CI excludes zero with a positive sign is
   reported explicitly, separately from the magnitude verdict. Outcome 2 means
   "does not reproduce at M5 magnitude"; it does **not** by itself mean "no
   regression on M4", and the two must not be conflated in the write-up.

**(d) N-3's thresholds move with the target.** ">25 % of the e2e difference"
for a single kernel is now **> 5.04 µs/step**; the ">50 % unexplained residual"
trigger is now **> 10.1 µs/step**. Both are against 20.15, and both apply only
if rung 2 runs.

### 1.5d Independent methodological critique (received pre-unblinding) — what it changes and what it deliberately does not

I put the full inference chain to an independent frontier reviewer while rung 1
was still running and before any contrast was computed. Its report is
adversarial and largely correct. **The decision rule below is unchanged**: the
bar stays at +32.4 µs/step and the four outcomes keep their preregistered form.
Moving a threshold after glimpsing data — even to a defensible value — is
exactly the failure mode § 1.5c's disclosure exists to prevent. Everything
adopted here is *additive reporting* or an *interpretation guard*, never a
change to what counts as which outcome.

**Adopted 1 — the bar is reported as a band, but decided as a point.** The
reviewer's strongest objection is that a single scalar transfer factor is only
meaningful when the effect is a fixed quantum of one resource *and* both parts
are in the same bottleneck regime for it. Mechanisms (a) and (b) are
register-pressure and latency-hiding effects, which are the classes where a
scalar is magnitude- **and sign-**unstable. Four defensible bars exist:

| scaling | factor | bar (µs/step) | valid if the mechanism is… |
|---|---|---|---|
| none (fixed overhead) | 1.00 | 20.1 | pure host/launch/barrier overhead |
| R1 transfer (**decisional**) | 0.622 | **32.4** | the R1 mechanism class |
| proportional to step time | 1.98 | 39.9 | blended, workload-matched |
| memory-bandwidth ratio | 610/266 | 46.2 | pure added DRAM traffic |

That the R1 factor 0.622 sits *between* the bandwidth prediction (0.436) and
the fixed-overhead prediction (1.0) is itself evidence that transfer is a
mechanism-dependent blend rather than a constant. § 4 therefore reports the
rung-1 CI against **all four** bars as a sensitivity row. Only the 32.4 row
carries the verdict.

**Adopted 2 — N-1 gets an explicit noise model.** `ΔT` is a difference of two
single receipts, so `SD(ΔT) ≈ s · 4141.5 · √2` for per-receipt step noise `s`:
17.6 µs at `s` = 0.3 %, 29.3 µs at `s` = 0.5 %. The observed +20.149 is then
only **1.15 σ** to **0.69 σ** — two-sided *p* ≈ 0.25 to 0.49. The honest
statement of the target is not "20.1 µs" but "one paired receipt shows +20.1 µs;
under 0.3–0.5 % receipt noise the true change plausibly lies anywhere in
[−14, +55] to [−37, +78]". (Approximate: it treats `D` and `P` as independent
within a receipt, which they are not, and `T = D − 4P` carries 16× the `P`
variance — small, ≈2.3 µs SD at 0.3 % `P` noise.) A mild mitigation is that `P`
moved only −0.099 % across the same two receipts, hinting `s` may be under
0.3 %; but prefill noise is not decode noise. This sharpens N-1 considerably and
it cuts against the target being solid.

**Adopted 3 — the null is a conservative gate, not a calibration.** The real
pair sits at adjacent positions {2,3} (separation 1); the null pair sits at
{1,4} (separation 3). Under roughly linear within-repetition drift the null
carries about **3× the drift SD** of the real contrast. Reversal cancels the
*means* over balanced repetitions but not the variances. So a clean null is
strong evidence the session was quiet, but the null's CI width must **not** be
used to calibrate expected drift noise in the real contrast, and it must never
be subtracted. The reviewer also correctly notes § 1.8's N-2 attached no
explicit decision rule; I fix that reading here: **null CI excluding 0 with
magnitude comparable to the real contrast ⇒ the real contrast is not
trustworthy and the outcome is downgraded to 4**, regardless of what the real
CI says.

**Adopted 4 — median-blindness is tested, not assumed away.** The official
metric averages 128 steps; my per-slot statistic is a median over 249. A single
one-time cost of 20.149 × 128 ≈ **2.58 ms**, or ~5 scattered steps of +500 µs
inside the official window, would reproduce the M5 receipt exactly while being
invisible to a median. § 1.5b already retained `step0` and `mean_first128` for
this reason; § 4 will additionally report a **tail/spike diagnostic** so that
"the effect lives where the median cannot see it" is an answered question
rather than an unexamined hole.

**Adopted 5 — the central anti-over-claim: sum-masking.** Rung 1 measures only
the *sum* of mechanisms (a) + (b) + (c). A null or a sign flip on M4 is
therefore consistent with large, opposite-signed per-mechanism effects — for
instance (a) = −30 and (b) = +15 on M4 giving a net −15, while on M5 (a) = +12
and (b) = +8 give +20. Nothing in that picture is contradictory, and **no
mechanism is exonerated by an aggregate null.** This is now the governing
sentence for § 6's verdicts.

**Noted, not adopted — two acknowledged defects in the outcome taxonomy.**
Outcome 2 as written does not require `lo > 0`, so a CI such as [−5, +25] —
compatible with zero *and* with the no-scaling bar — would be labelled
"M5-specific". And a tight, well-measured CI of [25, 39] would fall through to
outcome 4 "inconclusive-underpowered" when it is in fact precisely measured and
sitting on the bar. Both are real. I am **not** repairing them now, because
rewriting the taxonomy after seeing partial data is worse than living with a
known defect; instead § 4 states explicitly which defect, if any, the observed
CI actually triggers, and § 6 reasons from the CI rather than from the label.

**Confirmed, not merely assumed — regime match (reviewer's 4.3).** The probe
seeds via `decode_begin` with the full 512-token `prompt_tokens` of
`correctness_prompts/public_longcopy_gate_english_512_256.json`
(`research/decode_probe.py:154`), so the `RotatingKVCache(maxSize:512)` is
**window-saturated from step 0** and the sliding ring runs at its full 16
blocks/simdgroup — the same regime as the official metric, not a short-context
degenerate one. Each `decode_step` supplies exactly one token
(`decode_probe.py:167`), advancing exactly one position, and teacher forcing
holds for all 250 steps (256 expected tokens available).

**Also confirmed — the instrument measures `T` directly.** The advisor asked
that rung 1's contrast be in `T`, and that I say so explicitly if the instrument
times decode steps post-prefill. It does: `D = 4P + T` is the harness's
*composite*, whereas the probe times each one-token `decode_step` on its own
after the seed forward. The per-slot median is therefore already the `T`
analogue and **no `4P` subtraction is applied or needed on M4**.

### 1.6 Rung 0 gates (a failure here stops everything)

* **G0.1 build** — both revisions build a `mlxfast-runtime-worker`.
* **G0.2 token parity** — `--dump-tokens` output byte-identical between OLD and
  NEW over 250 teacher-forced steps, and zero teacher-forcing divergences
  reported by either arm. A parity failure means the two trees are not
  computing the same thing and the timing contrast is meaningless.
* **G0.3 distinct binaries** — the OLD and NEW worker binaries must not be
  byte-identical (that would mean the swap silently failed).
* **G0.4 rule 75 working-set digests** — sha256 over the full `Sources/` +
  `Vendor/` tree published before and after every timed run, and the digest must
  round-trip to its NEW value after the OLD checkout is restored.
* **G0.5 metallib** — the AOT metallib is rebuilt at OLD into a scratch path and
  its sha256 compared with NEW's. If identical, one metallib serves both arms
  and that fact is published; if different, each arm carries its own.

### 1.7 Rung 2 (only if outcome 1)

Reuse `research/maple-nezuko-r100c-census.sh` /
`research/maple_r89_insitu.py` — the PR #558 position-matched in-situ per-kernel
census, resolution ±0.43 µs/step/kernel. Not re-authored. Deliverable: one table
of µs/step at OLD and NEW, paired diff, 95 % CI, sign counts, sorted by |diff|,
followed by the **reconciliation residual** `ΔT_e2e − Σ(per-kernel diffs)`.

### 1.7a Rule-58 reuse assessment of the existing census scripts

§ 1.7 promised "not re-authored". That promise turned out to be only half
keepable, and the deviation is recorded here rather than discovered later.
Three prior census scripts exist; each was read end to end before deciding.

| script | what it actually is | reusable for OLD→NEW? |
|---|---|---|
| `research/maple-nezuko-r100c-census.sh` → `research/maple_r89_insitu.py` | The real #558 position-matched census. Applies `research/nezuko-pr158-gpuprof-hook.patch` to `Vendor/`, builds **one** worker, reverts the hook immediately after the build, then sweeps `DARKBLOOM_ROUTER_WEIGHT_PREFETCH` over slots `0,0b,1,5`. Position matching is real (`maple_r89_insitu.py:164-165`, `order = SLOTS if rep % 2 == 0 else reversed(SLOTS)`), so `pf1`/`pf0b` share position multiset {2,3}. Digest guard via `tree_digest()` + `trap cleanup EXIT`. Validated at REPS=12 STEPS=300, 2166 s. | **Harness: yes. Parser: no.** It is a *one-binary env-var* sweep; I need a *two-binary* contrast. And it regex-parses only the single `residual_rms_router\S*` row, discarding every other kernel — the opposite of the full table § 1.7 owes. |
| `research/tanjiro-r99d-census.sh` | 16 lines, no build, no patch, 80 steps, single arm repeated. | **No.** No ABBA, no second arm. |
| `research/tanjiro-r100b-census.sh` → `research/maple_r85c_epilogue_ab.sh` | Genuinely two-binary ABBA (`base cand cand base`, REPS=4 STEPS=200). | **No.** It builds each arm by checking out **only** `LagunaRuntimeModel.swift` at a revision. For OLD→NEW that breaks the build: NEW folded `LagunaRuntimeLayers.swift` into `LagunaRuntimeModel.swift` (§ 2.3), so restoring the OLD file alone leaves OLD's separate `LagunaRuntimeLayers.swift` duplicating symbols against it. |

**Deviation, declared:** I reuse the r100c *harness shape* — the same hook, the
same apply/build/revert/digest discipline, the same position-matched slot order —
but the arms come from my rung-0 two-binary snapshots instead of an env-var
sweep, and I write a new parser
`research/maple-frieren-r103a-census.py` that keeps **every** kernel row plus
the `... N more` tail row (recorded as `<tail beyond --profile-top>`) so the
reconciliation residual in § 1.7 is actually computable. Reusing the r89 parser
would have silently made the residual equal to "everything except the router",
which would have prejudged N-3.

### 1.8 Preregistered nulls

* **N-1 receipt noise.** The M5 headline — **+20.149 µs/step in `T`**, per
  § 1.5c; the +19.405 figure this line originally carried was the `D` delta and
  is superseded — is a difference of two single receipts. Verdict from the
  rung-1 null and from the known receipt spread; if the M5 delta is inside
  receipt noise the whole target is a ghost.
* **N-2 thermal / session drift.** Verdict from the rule-79 identical-code null
  CI. If the null CI excludes 0 with magnitude comparable to the real contrast,
  drift contaminates and the real contrast is not trustworthy.
* **N-3 diffuse.** Thresholds are taken against the corrected M5 target of
  **20.15 µs/step** (§ 1.5c), not against whatever rung 1 happens to measure:
  a single kernel counts as *the* localised cost only above **5.04 µs/step**
  (25 %), and an unexplained reconciliation residual above **10.1 µs/step**
  (50 %) means the cause is diffuse rather than one kernel → hand to
  fern R103-D.
* **N-4 the vendored comment carve** `f720e9e7` (176,468 B, nezuko's R103-C).
  Confirmed **inside** the OLD→NEW range (`f720e9e7` is an ancestor of NEW and
  not of OLD), so rung 1 measures it bundled with everything else. A static
  pre-read is in § 2 below and constrains what N-4 can possibly explain.

### 1.9 Non-negotiables carried from the assignment

* **Zero submitted bytes.** Nothing under `Sources/`, `Vendor/`, or
  `benchmark.json` on the merged branch. Probe scaffolding lives in `research/`
  and any patch applied to build an arm is reverted before timing, with the
  rule-75 digest proving it.
* **Zero official receipts consumed.**
* First leg discarded (here: the first two repetitions).
* K ≥ 16 dispatch replicates.
* Do **not** design or land a fix. R103-A localises; it does not repair.

### 1.10 Stopping rule

Stop at the first of: (1) rung-1 outcome 2, 3, or 4; (2) rung-2 table published
with its reconciliation residual; (3) rung 0 blocked after exhausting the
fallback anchors.

### 1.11 Amendment `r103-a-fb2-retract-20p15-three-arm` — the target is retracted and the arm becomes three-way

Received 2026-08-09T22:22:23Z, **while the rung-1 job was running and before I
had looked at any rung-1 number**. Timestamped disclosure: at the moment this
amendment arrived the run had completed 64 of its 104 slots and the only rung-1
quantity I had observed was the slot *count* (`grep -c`). The interim medians I
had seen much earlier are the ones already disclosed in § 1.5c; nothing new was
unblinded before this amendment was written down.

#### What the advisor retracted

Two independent results say the +20.149 µs/step of `T` I was sent to localise
**may not exist**:

1. **Provenance.** The frontier receipt `e08d759f` was produced by `bd33883e`,
   whose local tree is `a4d3b8dc`, whose `Sources/` is byte-identical to
   `e17bdeb1` — *not* by the assignment base `0f6862d0`. The base is that tree
   **plus R3** (#558). I verified both halves locally:

   ```
   git diff --numstat e17bdeb1 a4d3b8dc -- Sources          -> (empty)
   git diff --numstat e17bdeb1 0f6862d0 -- Sources Vendor
     102  11  Sources/MLXFastModel/LagunaRuntimeModel.swift  -> exactly R3
   ```

   So the contrast I preregistered (`30f752df` → `0f6862d0`) is **not** the
   receipt pair the 20.149 came from. It is that pair *composed with an
   unmeasured third change*.

2. **Replicate noise.** Five same-session receipts from trees differing only by
   a marker comment span `sd(T) = 14.272 µs/step`; the trimmed pooled figure
   over six identical-code groups is `sd(T) = 12.079`. A difference of two
   single receipts therefore carries σ = 17.1–20.2 µs/step, so the
   "missing microseconds" sit at **z = 1.00–1.18**. This is the measured
   version of the model-based objection I had already recorded as § 1.5d
   Adopted 2 (which estimated 17.6–29.3 µs/step from an assumed 0.3–0.5 % `s`).
   The measured value lands inside that predicted band, which is a small
   independent corroboration of that critique.

#### What changes, precisely

| item | before | after |
|---|---|---|
| status of rung 1 | corroboration of a receipt-derived effect | **the primary experiment** |
| arms | 2 (`old`=A, `new`=C) | **3**: `A`=`30f752df`, `B`=`e17bdeb1`, `C`=`0f6862d0` |
| falsification target | localise +20.149 | **test whether A↔B is nonzero at all** |
| second contrast | — | **B↔C = R3, never measured anywhere** |
| rung 2 | fires on outcome 1 | fires only if a contrast is real; if B↔C is real, point the census at R3's `+102/−11` hunk instead |
| reporting | outcome label | **an exclusion bound with X attached, always** |
| nulls | N-1 … N-4 | **plus N-5**: all three arms mutually indistinguishable ⇒ report half-widths and stop |

The half-width target is unchanged and is now load-bearing: **< 8 µs/step M4**.

#### What this does *not* change

The instrument, the parity gate, the rule-75 digest discipline, the rule-79
identical-code null, the per-slot statistic (§ 1.5a), the diagnostics
(§ 1.5b, § 1.5d), the transfer-factor sensitivity table (§ 1.5d Adopted 1), and
the static pre-read in § 2 all stand unmodified. § 2 was a pre-read of A→C; it
decomposes cleanly, because A→B carries the entire vendored comment carve and
all three NEW-only decode mechanisms, while B→C is exactly R3.

#### Disposition of the already-running rung-1 job

I am **not** killing it. It measures **A↔C** — the composed contrast — at
K = 24 pairs with an embedded identical-code null, using the same binaries that
rung 1B will reuse. It is the one contrast that is *not* directly recoverable
from the three-arm run's own pairs without re-deriving it, it supplies the
per-repetition σ needed to size rung 1B honestly, and it is the design I
preregistered. Discarding preregistered data because an amendment arrived
mid-flight would be the worse of the two errors. Rung 1B re-measures A↔C
independently, so the two runs also cross-check each other.

#### Rung 1B design (preregistered here, before rung 1 is unblinded)

Six slots per repetition in a **palindrome**:

```
pos     1  2  3  4  5  6
arm     A  B  C  C  B  A
```

* Each arm's per-repetition estimate is the mean of two slots placed
  symmetrically about the repetition midpoint, so **linear session drift
  cancels to first order in all three contrasts**, not just one privileged
  pair. This is strictly better than the 4-slot design, where only the interior
  pair was matched.
* Variance per repetition improves by √2 over a single-slot pair: with i.i.d.
  slot noise σ, `Var(B̂ − Â) = σ²` rather than `2σ²`.
* The three within-arm differences are rule-79 identical-code nulls at
  **separations 5 (A), 3 (B) and 1 (C)**. That is a *drift-versus-separation
  curve*, which directly answers § 1.5d Adopted 3: the two-arm design could
  only offer one separation and had to argue it was conservative. Here the
  contrasts are drift-cancelled by construction and the nulls bound the raw
  drift at three scales.
* Warm-up: the first repetition is discarded. The palindrome is self-balancing
  within a repetition, so unlike the 4-slot design there is no even/odd cycle
  to keep intact and one repetition suffices.
* `STEPS` stays at 250. The teacher-forced fixture supplies 256 expected
  tokens, so this is the cap, not a tuning choice.
* `REPS` is chosen from the per-repetition σ that rung 1 measures, to put the
  worst pairwise half-width below 8 µs/step. This is a power calculation on a
  *variance* estimated from a different design's slots, not a look at any
  contrast, so it does not unblind the decision. The chosen value and the σ it
  came from are both published in § 4.

#### Rung 1B decision rule (fixed now)

For every pair, report the paired 95 % CI and the **exclusion bound**
`X = max(|lo|, |hi|)`, in M4 µs/step and in M5-equivalent µs/step at the R1
factor, with the four-assumption sensitivity of § 1.5d Adopted 1 alongside. Then:

1. **A↔B CI contains 0 and `X·0.622 < 20.15`** ⇒ the "missing microseconds" are
   refuted at M5 magnitude on this host. Report the bound; no rung 2 for A↔B.
2. **A↔B CI excludes 0 with positive sign** ⇒ the effect is real and
   host-portable; rung 2 on A↔B.
3. **B↔C CI excludes 0 with positive sign** ⇒ R3 costs time at the top of our
   tree; rung 2 on R3's hunk. This is treated as **co-equal** with A↔B, per the
   amendment, and it is the outcome with the largest immediate value because
   R3 is currently merged and unmeasured.
4. **Any null CI excludes 0 at a magnitude comparable to a contrast** ⇒ N-2
   fires and every contrast is downgraded to inconclusive.
5. **All three contrasts contain 0** ⇒ **N-5**; report the three half-widths
   and stop.

Outcomes 2 and 3 are not exclusive; if both fire, rung 2 goes to B↔C first
because its diff is 102 lines rather than 286 commits.

#### Reporting discipline adopted verbatim

No contrast in this document will be described as "neutral", "null" or
"unchanged" without an attached X of the form *"excludes effects larger than X
µs/step"*. Where a bound is quoted in M5-equivalent units the transfer
assumption is named in the same sentence.


---

## § 2 Static pre-read of the OLD→NEW delta (no timing)

This was completed before any build and it materially narrows N-4. Method: for
every file differing between `30f752df` and `0f6862d0`, strip comment lines and
re-diff, counting only non-comment changed lines.

### 2.1 The vendored surface is comment-only

| surface | files | non-comment changed lines |
|---|---|---|
| `Vendor/mlx-swift/.../backend/metal/kernels/*.metal`, `*.h` (`arg_reduce`, `binary`, `gemv`, `rms_norm`, `rope`, `scaled_dot_product_attention`, `sdpa_vector.h`) | 7 | **0** |
| `Vendor/mlx-swift/.../{jit_kernels.cpp, kernels.h, quantized.cpp, matmul.cpp}` | 4 | 68 lines, **all** trailing/inline comment removals |
| `Vendor/mlx-swift-lm/.../MLXLMCommon/*`, `MLXLLM/Models/Laguna.swift` | 12 | **0** semantic |
| `Sources/MLXFastModel/LagunaConfig.swift` | 1 | **0** semantic |

The 68 "non-comment" lines in the four C++ files are an artefact of line-based
comment stripping, not real edits — each is a comment amputated from a code
line: `} // namespace` → `}`, `int ndim /* = -1 */,` → `int ndim ,`, the
`case 1..5` bm/wm annotations in `quantized.cpp`, and
`int swizzle_log = 0; // tm >= 6 ? …` → `int swizzle_log = 0;`.

**Consequence for N-4.** The carve cannot change AOT codegen (the `.metal`/`.h`
sources are unchanged after comment stripping, so the metallib is a
byte-for-byte question settled by gate G0.5) and cannot change host dispatch
semantics. Its only possible timing channels are (a) JIT source-string bytes
and therefore JIT cache keys, and (b) binary/code layout. Both are diffuse
mechanisms, which points N-4 at N-3 rather than at a single kernel.

### 2.2 `Sources/MLXFastTransform` does not touch the weights

`AffineMetadataCoding.swift` and `TiedHeadMetadataCoding.swift` are new, and
`Transform.swift` gains 55 lines, but the new sidecar generation is gated to
`case .gemma4`; `case .laguna` emits nothing. The 20 GB `weights/` tree is
therefore identical across the two arms and needs no rebuild — only code layout
can differ.

### 2.3 The one substantive surface is `Sources/MLXFastModel`

```
Sources/MLXFastModel/LagunaConfig.swift            +6    −1
Sources/MLXFastModel/LagunaRuntimeLayers.swift      0 −2597
Sources/MLXFastModel/LagunaRuntimeModel.swift   +2784   −17
```

OLD carries `LagunaRuntimeLayers.swift` (2597 lines) beside
`LagunaRuntimeModel.swift`; NEW merges them into one file. To separate the
merge from real edits, both sides were reduced to sorted multisets of
comment-stripped, whitespace-normalised code lines: OLD 9205 lines, NEW 9354,
with 197 differing (173 NEW-only, 24 OLD-only).

**The 24 "OLD-only" lines are re-wrapping artefacts, not removals.** Every
symbol they mention has an identical occurrence count in both revisions:

| symbol | OLD | NEW |
|---|---|---|
| `lagunaDecodeEmbeddingRoPEAtlas` | 4 | 4 |
| `lagunaRoPEAngleAtlasLength` | 13 | 13 |
| `lagunaTerminalPrefillFusionEnabled` | 2 | 2 |
| `lagunaResidualRMSNormRouterSource` | 2 | 2 |
| `lagunaResidualRMSNormRouterKernels` | 2 | 2 |
| `lagunaRouterPrecomputedKeysEnabled` | 10 | 10 |

So **nothing that OLD had was dropped**. This kills the most attractive naive
hypothesis — that frontier adoption deleted an Arm R optimisation and nobody
restored it.

**What NEW adds** (0 occurrences in OLD):

| symbol | NEW | what it is |
|---|---|---|
| `pipe_kc`, `pipe_kd`, `piped_score0`, `pipec_*` | 10 / 8 | embedded-MSL 4-way pipelined attention inner loop |
| `prefetchGroups`, `prefetchEarly`, `prefetchLate` | 7 / 2 / 2 | router weight-prefetch splice points |
| `armSuffix` | 2 | JIT kernel-name arm suffix |

and correspondingly the SDPA-vector inner loop goes from
`for (; i + BN < N; i += 2 * BN)` in OLD to
`for (; i + 3 * BN < N; i += 4 * BN)` in NEW, with a
`[0, 1, 5].map { prefetch -> (Int, MLXFast.MLXFastKernel) in` slot map building
three prefetch arms.

**This inverts the framing of the task.** The missing ~19 µs/step is not
subtraction — NEW contains *more* machinery than OLD in exactly the decode
attention and router paths. Candidate mechanisms therefore become: the 4-way
pipelined attention loop being slower than OLD's 2-way loop at the decode
shape (one query row, sliding window ≤ 512); a prefetch arm default selecting a
worse variant; or extra JIT variants inflating specialisation/dispatch cost.
Rung 2's per-kernel census is the right instrument to choose among these, and
rung 1 must first establish that the effect exists off-M5 at all.

Caveat recorded before timing: the `[0, 1, 5]` prefetch slot map and `armSuffix`
originate in #558's env-var arm scaffolding, so some of this NEW-only content is
research selection machinery rather than a changed default. Rung 2 must not
attribute cost to an arm that the shipped default never selects.

### 2.4 Kernel reachability on the M4 host (rule 77) — settled statically, before timing

Rule 77 and `AGENTS.md` both warn that an M4 Pro reports Apple GPU generation 16
and therefore does not select the `_nax` kernels the ranked M5 uses. If the
NEW-only machinery were behind an architecture gate, an M4 null would be
uninformative — it would only say "this host does not run the changed code".
That had to be settled *before* the timing job, not after, so it could not be
used to explain away an inconvenient result. It was, and the answer is clean:

* **`LagunaRuntimeModel.swift` contains exactly one GPU-architecture branch**,
  `lagunaExpertAlignedGatherEnabled` (`:253-265`), resting on the file's only
  `GPU.deviceInfo()` call (`:262`) via `lagunaNAXAvailable` (`:242-247`,
  `generation >= 17`). On this M4 Pro it evaluates **false**.
* **Its every consumer is prefill-only.** `lagunaFusedSortedRoutedGateUp`
  (`:10527`, arch use at `:10578`) is called under `x.dim(1) > 1` (`:10981`);
  the packed-scale views (`:10753`, `:10766`) are consumed only in the
  `x.dim(1) > 1` branch (`:10989-11009`). Nothing on the one-row decode path
  changes as a function of architecture.
* There is no `supportsFamily`, no `deviceName`, and no literal `_nax` test in
  the file.

So the three NEW-only mechanisms are all reached on this host with no env
overrides:

| mechanism | gate | on M4 decode? |
|---|---|---|
| 4-deep pipelined ring, `laguna_sliding_fused_attn_ring_v1` (`:1639`) | `DARKBLOOM_FUSED_SLIDING_ATTN != "0"` (default ON) + `B==1 && L==1` + `isSliding` + `nHeads==64` + `RotatingKVCache(maxSize:512)` with `offset >= 512` | **yes**, from decode step 1 |
| router weight-prefetch peel + `armSuffix` | `DARKBLOOM_ROUTER_ROWS_PER_GROUP` (default 8) → `rowsPerThread==1`; `DARKBLOOM_ROUTER_WEIGHT_PREFETCH` (default 1) | **yes**, `_pf1` arm |
| `DARKBLOOM_NVFP4_NIBBLE_SPLIT` nibble form (`:6653`, default 1) | env only | **yes** |

Three consequences for how rung 1 may be read, all fixed before the data exists:

1. **A null on M4 is informative.** It cannot be dismissed as "wrong kernel
   family" for these mechanisms. It remains uninformative about anything
   `_nax`, but § 2.1 and gate G0.5 already showed the AOT surface — where the
   `_nax` variants live — is byte-identical across OLD and NEW, so no `_nax`
   kernel *changed* in this range.
2. **The prefill/decode asymmetry now has a named candidate.** The 4-deep ring
   is guarded by `B == 1 && L == 1`; it is structurally unreachable during
   prefill, and it applies to the 30 sliding layers only, not the 10 full-
   attention layers (whose twin `laguna_full_fused_attn_grow_v1` `:2027` still
   uses the 2-deep loop `:2168`). A decode-only regression alongside a prefill
   *improvement* is exactly the shape this predicts. That is a hypothesis for
   rung 2 to test, not a conclusion.
3. **One candidate mechanism is downgraded before it is measured.**
   `armSuffix` (`:1127`) is evaluated inside the eager kernel-table build at
   `:1120-1146`, not per dispatch; the decode path does a dictionary lookup
   `lagunaResidualRMSNormRouterKernels[rowsPerGroup * 8 + prefetch]!`
   (`:1223-1224`). So "extra per-dispatch host cost from the variant
   machinery" is not supported by the code and should not be offered as an
   explanation. What the `[0, 1, 5]` map *does* add is a table of **21** kernels
   where OLD (`30f752df:1038-1050`, keyed on `rowsPerGroup` alone) had **7**.
   That is a construction cost, and because a Swift file-scope `let` is
   initialised lazily on first access it is paid inside the process, not at
   load. It is nonetheless unlikely to be the decode mechanism: the same table
   is used by the terminal-prefill row (`:11268`), so first access precedes the
   decode window — and prefill *improved* over this range. The § 1.5b step-0 and
   first-128 diagnostics are what would show otherwise.

Caveat kept: this is a static read of the gating, cross-checked against the OLD
tree (`armSuffix`, `DARKBLOOM_ROUTER_WEIGHT_PREFETCH`, `pipe_kc`,
`for (; i + 3 * BN < N;` all have zero occurrences at `30f752df`). It is not a
runtime trace. The `--profile` hook (`research/nezuko-pr158-gpuprof-hook.patch`)
is deliberately not applied to these snapshots, because applying it would edit
the submitted surface of both arms and break the clean OLD/NEW contrast.

### 2.5 Exact geometry of the 2-deep → 4-deep change (static, verified)

§ 2.3 identified the pipelined sliding-attention inner loop as the largest
NEW-only mechanism on the decode path. Before any timing it is worth pinning
down exactly what changed, because several plausible-sounding explanations turn
out to be excluded by the code itself.

**Verified in source.** Kernel `laguna_sliding_fused_attn_ring_v1`
(`LagunaRuntimeModel.swift:1507`, source string from `:1516`):

```text
constexpr int BD = 32;          // lanes per simdgroup
constexpr int BN = 32;          // simdgroups per threadgroup
constexpr uint head_dim = 128;
constexpr uint window   = 512;  // == N during steady decode
constexpr int qk_per_thread = 4;
constexpr int v_per_thread  = 4;
typedef float U;
```

Dispatch (`:1964-1972`): `threadGroup: (1024, 1, 1)`,
`grid: ((heads / 2) * 1024, 1, 1)`. With `heads == 64` that is **32
threadgroups of 1024 threads**, one per query-head pair; each threadgroup holds
`BN == 32` simdgroups and must be resident in its entirety on a single GPU core.

The loops:

| | main loop | at | remainder / peel |
| --- | --- | --- | --- |
| OLD sliding | `int i = sg; for (; i + BN < N; i += 2 * BN)` | `30f752df:1547-1548` | **none** |
| NEW sliding | `int i = sg; for (; i + 3 * BN < N; i += 4 * BN)` | `:1638-1639` | **none** (loop closes `:1817`, next statement is the `if (lane == 0)` reduction at `:1819`) |
| OLD full-attn | `for (; i + BN < N; i += 2 * BN)` | `30f752df:1989` | — |
| NEW full-attn | `for (; i + BN < N; i += 2 * BN)` | `:2168` | **unchanged** |

**Trip counts at `N == 512`**, for every simdgroup `sg ∈ [0, 31]`:

- OLD: `i = sg, sg+64, …, sg+448` → **8 iterations × 2 key-blocks = 16 blocks**.
- NEW: `i = sg, sg+128, sg+256, sg+384` → **4 iterations × 4 key-blocks = 16 blocks**.

Both tile the 512-key window exactly: 32 simdgroups × 16 blocks = 512 keys, with
no peel iteration, no remainder loop and no masked lanes. The two arms issue
**identical** total loads and identical total arithmetic.

**Extra live per-thread state in NEW's body** (`:1651-1662`): `pipe_kc[4]` and
`pipe_kd[4]` add 8 `float`, and `pipe_vc0..3`/`pipe_vd0..3` add 8 `bfloat` —
about 48 bytes per thread, on the order of a dozen extra 32-bit registers.

#### What this rules out before measuring

- **Peel / remainder penalty is not available as an explanation.** A deeper
  pipeline usually pays a tail cost when the trip count is not a multiple of the
  unroll factor. Here `512` is a multiple of both `2·BN` and `4·BN`, so neither
  arm executes a single wasted block.
- **Neither is extra work.** Loads, multiplies and the online-softmax rescales
  are one-for-one identical between the arms; only their *scheduling* and their
  *live-range overlap* differ.
- **Occupancy cannot absorb the register increase.** The threadgroup size is a
  hard-coded 1024. Extra register demand cannot be paid by shrinking the
  threadgroup; it is paid either out of spare register file or by spilling.

*(Inference, not verified: that leaves instruction scheduling, register
pressure and spilling as the mechanism if this loop is the cause. It also means
the sign is genuinely a hardware question — trip count drops 8 → 4 while each
body doubles in size and live state, and which side wins depends on the core's
register budget and memory-latency-to-issue ratio. § 4 measures it on M4 Pro;
§ 6 states plainly what that does and does not license about M5.)*

### 2.6 Mechanism shortlist and the magnitude frame (static; written before unblinding)

Everything in § 2.6 was written while the rung-1 job was still running and
before any paired statistic had been computed. It exists so that § 6 cannot be
accused of inventing a mechanism to fit whichever sign came back. Claims are
tagged **[V]** verified in this checkout, **[D]** documented by a public
primary source, **[I]** inference.

#### 2.6.1 The 4-deep loop is unroll-and-jam, not a rotating pipeline

**[V]** In NEW `LagunaRuntimeModel.swift:1650-1674` all four K rows and all
four V rows are loaded at the top of the iteration (`T_LOAD_K` / `T_LOAD_V`
expansions), and the four softmax stages then run **serially** below them,
chained through `pair_max` / `pair_sum` / `pair_o`. That chain is a
loop-carried dependency: stage *k+1* cannot rescale its accumulator until
stage *k* has published its running max and sum.

**[I]** Deepening therefore cannot shorten the critical path. Its only
possible benefit is issuing the loads earlier — a pure latency-hiding play. Its
only possible cost is holding more live state across a longer body.

#### 2.6.2 What the deeper body actually costs

**[V]** NEW carries `pipe_kc[4]` + `pipe_kd[4]` (8 × float) and
`pipe_vc0..3` / `pipe_vd0..3` (8 × bfloat-pair) that OLD does not
(`:1651-1662`), i.e. of order **+64 B of live state per thread**.

**[V]** Threadgroup memory is unchanged between the arms (`:1600-1607`), so
this is a register-file question, not a shared-memory-occupancy question.

**[I]** +64 B/thread ≈ +32 16-bit register units ≈ **+66 KB per 1024-thread
threadgroup**. Combined with § 2.5's finding that the threadgroup size is
hard-coded to 1024, the compiler's only ways to pay for it are spare register
file or spilling to thread-private device memory.

#### 2.6.3 Router prefetch peel

**[V]** rpg = 8 gives the same kernel and the same dispatch count in both arms
(32 threadgroups × 512 threads, NEW `:1219-1233`). The `pf1` variant
(NEW `:686-703`) hoists one group of four `vec<bfloat,4>` loads — 32 B/thread
on 8 of 16 simdgroups — above the norm-reduction ladder and its three barriers
(NEW `:838-855`). The main accumulate loop is re-blocked but visits the same
elements in the same order (OLD `30f752df:921-942` vs NEW `:968-1006`).

**[I]** This is a placement change worth at most the latency of one 32 B load
per participating thread, and the shipped `pf5` slot map is a built-in
placement control, so it is the *second* candidate, not the first.

#### 2.6.4 Magnitude frame — how small the target really is

**[V]** 30 of 40 layers are sliding; the router runs on 39 of 40.

**[I]** +20.1 µs/step spread over 30 sliding dispatches is **+0.67 µs per
dispatch**; over 39 router dispatches it is **+0.52 µs per dispatch**. Against
individual kernels in the 3–14 µs range that is a **5–20 % per-kernel**
regression. One occupancy tier, or a handful of spill instructions in the inner
loop, is enough. Loop-control overhead cannot be the cause in the other
direction either — NEW *halves* the loop-control count.

#### 2.6.5 Ranked mechanisms, if the effect reproduces on M4

1. **Register-tier / residency cliff.** The +66 KB/threadgroup crosses a tier
   and the compiler spills. **[I]**
2. **No latency left to hide.** 32 resident simdgroups per core already cover
   the load latency, and § 2.6.1's serial softmax chain means the earlier loads
   buy nothing, so only the register cost lands. **[I]**
3. **Load-queue / MSHR saturation.** Depth 4 puts ~4 KB per simdgroup in
   flight at once. **[I]**
4. **Full unroll at a `constexpr` trip count of 4** amplifying (1). **[I]**

Explicitly *not* in play, from § 2.5: peel/remainder cost, extra arithmetic,
trip-count starvation.

#### 2.6.6 Why a *sign flip* on M4 is a predicted outcome, not a refutation

**[D]** M5 Max is a ~610 GB/s part; this M4 Pro is a ~273 GB/s part.
**[D]** Apple documents Dynamic Caching from M3/A17 onward ("Explore GPU
advancements in M3 and A17 Pro", WWDC23) and describes M5 as having a
"next-generation shader core" (Apple Newsroom, Oct 2025), but publishes no
register-file capacity for either generation; the only numbers in circulation
come from reverse engineering of *older* parts (dougallj/applegpu,
philipturner/metal-benchmarks) and **nothing public covers Apple GPU generation
16 or 17**.

**[I]** Prefetch depth hides latency, not bandwidth. A wider-bandwidth part has
less queuing delay to hide, so the depth-4 benefit tends to zero there while the
register cost stands — net negative. A narrower part sits closer to the wall, so
the same depth can still pay for itself. That is a coherent account in which
**NEW is genuinely slower on M5 and neutral-or-faster on M4**. If rung 1 returns
outcome 3 (sign flip), that is *consistent with* the M5 receipt delta, not
evidence against it, and § 6 must say so rather than declaring the delta noise.

**[I]** The countervailing consideration: 32 threadgroups underfill a large M5
Max GPU, so per-core register and scheduling effects should transfer between
the parts roughly 1:1 — which is why the experiment is worth running at all.

#### 2.6.7 A free pipeline-state result: no hard occupancy cliff on gen 16

The obvious sharp static probe is to compile both sliding-kernel variants and
compare `MTLComputePipelineState.maxTotalThreadsPerThreadgroup`; a drop below
1024 on the NEW variant would confirm § 2.6.2 directly. **That probe does not
need to be run, because MLX already performs it on every dispatch and every
NEW-arm run on this host has passed it.**

**[V]** `Vendor/mlx-swift/…/backend/metal/custom_kernel.cpp:103-111` reads
`kernel->maxTotalThreadsPerThreadgroup()` and *throws* `invalid_argument` when
the requested threadgroup size exceeds it. § 2.5 established that this kernel
is dispatched with a hard-coded `threadGroup: (1024, 1, 1)`, and § 2.4
established that it is reached on this host at shipped defaults.

**[V]** The NEW worker completed 250-step teacher-forced decodes with zero
divergences and no exception on every NEW slot of rung 1 (§ 4.1). Therefore, on
Apple GPU generation 16, **`maxTotalThreadsPerThreadgroup` for the NEW 4-deep
kernel is ≥ 1024, i.e. exactly the device maximum** — the same as OLD.

**[I]** So no *hard* occupancy cliff is crossed on this host: the gen-16
register allocator fits the deeper body inside a full 1024-thread threadgroup.
That does not exclude mechanism 2.6.5(1) — Metal caps the reported value at the
device maximum, so it cannot distinguish "fits with room to spare" from "fits
only by spilling" — and it says nothing about the gen-17 backend, which is
where § 2.6.6 locates the most likely M5-only behaviour. It does mean that if
rung 1 reproduces the regression on M4, the mechanism is a *soft* cost
(spill traffic or scheduling) rather than a residency-tier collapse.

---

## § 3 Rung 0 — build and parity

Driver `research/maple-frieren-r103a-build-arms.sh`, run as job
`52c9ddb2-4658-4d33-b80b-632279af2f6c`, exit 0, 165 s wall. Full log kept at
`/tmp/maple-r103a/rung0-provenance.txt`; the load-bearing lines are reproduced
below verbatim.

### 3.1 Gate results

| gate | what it asserts | result |
| --- | --- | --- |
| G0.1 | both arms build the scored worker product | **PASS** — NEW 83.33 s, OLD 68.98 s, both `Build ... complete!` |
| G0.2 | teacher-forced greedy tokens identical across every slot | deferred to rung 1 (checked on all 104 slots, § 4.1) |
| G0.3 | the two arms are genuinely different binaries | **PASS** |
| G0.4 | rule-75 digest round-trip: the tree returns to HEAD | **PASS** |
| G0.5 | AOT `mlx.metallib` identical across arms | **PASS** |

```text
digest_head           = c3fafd30b4fdba6d3058746e79a715a53a072c5d5c77b0716a3a73dbd385f492
digest_at_new_build   = c3fafd30b4fdba6d3058746e79a715a53a072c5d5c77b0716a3a73dbd385f492
digest_at_old         = 82f0f5a86ed1426d5339933975181904319d84ca6013bc353f688e4bd9b38db8
digest_after_restore  = c3fafd30b4fdba6d3058746e79a715a53a072c5d5c77b0716a3a73dbd385f492
```

The digest is `find Sources Vendor -type f -print0 | sort -z | xargs -0
shasum -a 256 | shasum -a 256`. It is taken before the NEW build, after the
`git checkout 30f752df -- Sources Vendor`, and after the restore. The first and
last agree, so the checkout of OLD over the submitted surface left nothing
behind: **the branch's submitted bytes are unchanged by this experiment**, which
is the non-negotiable the assignment is strictest about.

### 3.2 Snapshots

```text
32d0a3d4ce245a2d70ea55852f549cd9461f1e21c334b069913691b597881ddb  new/mlxfast-runtime-worker   49,190,344 B
d36a981fc38ec0576f809aec4fd2021f67006b803a94270d0eb0cfa4a41a911e  old/mlxfast-runtime-worker   49,094,856 B
d36a981fc38ec0576f809aec4fd2021f67006b803a94270d0eb0cfa4a41a911e  oldA/mlxfast-runtime-worker
d36a981fc38ec0576f809aec4fd2021f67006b803a94270d0eb0cfa4a41a911e  oldB/mlxfast-runtime-worker
8e8b18afaee1ed5a0190403f79a4cc74b9bebcb52b50c4b67d0ed91dc73097ec  {new,old,oldA,oldB}/mlx.metallib
```

`oldA` and `oldB` are `cp` copies of `old`, not rebuilds: the § 1.4 null arm has
to be byte-identical code, and rebuilding it would let build nondeterminism
leak into the very quantity the null is supposed to bound.

### 3.3 What G0.5 buys

`mlx.metallib` is the ahead-of-time compiled Metal library — RoPE, RMSNorm, SDPA
vector, `arg_reduce`, and the rest of the AOT surface. It is **byte-identical**
across the two arms. Together with § 2.1 (every changed `.metal`/`.h` file is
comment-only) and § 2.2 (the transform emits nothing for Laguna, so the ~20 GB
`weights/` tree is bit-identical), this narrows the causal surface hard:

> Whatever the ~20 µs/step is, it is produced by **Swift host code and the Metal
> shader sources embedded as Swift string literals in
> `Sources/MLXFastModel/LagunaRuntimeModel.swift`, JIT-compiled at runtime** —
> not by the AOT kernels, not by the weights, and not by the vendored runtime.

The 95,488-byte difference in executable size is consistent with that: the
NEW binary carries the longer embedded shader sources and the wider variant
table of § 2.3.

### 3.4 A caveat G0.5 does *not* remove

Identical AOT metallibs do not imply identical *JIT* products. The embedded
shader strings differ, so the runtime-compiled pipelines differ by
construction; that is the intended contrast, not a confound. It does mean the
first-touch JIT compile cost differs between arms, which is exactly why § 1.5b
carries `step0` and `mean_first128` as separate diagnostics and why the
decision statistic is a median over steps 1…249.

## § 4 Rung 1 — paired ABBA e2e decode on M4

_Pending._

## § 5 Rung 2 — position-matched per-kernel census

_Pending (gated on rung-1 outcome 1)._

## § 6 Verdicts on N-1 … N-4

_Pending._

## § Reply

_Pending._
