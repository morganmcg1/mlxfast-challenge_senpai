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

## § 1.12 Second adversarial design review (frontier), and what it changes

After § 1.11 was written I put the rung-1B design to an independent frontier
reviewer with no access to this conversation. It was given the palindrome
proposal, the arm-D question, the budget, and the § 1.11 decision rule, and
asked seven numbered questions. Its verdict is recorded here *before* any
rung-1 number is unblinded, so the changes below are design changes, not
post-hoc rationalisation.

The review's bottom line: the palindrome is close to optimal for the stated
estimand, but it has two defects, the median is blind to the effect class this
change most plausibly produces, and the 8 µs/step target may be arithmetically
out of reach on this host.

### 1.12.1 Adopted

**A1 — rotate the arm→position assignment across repetitions.** A fixed
`A B C C B A` locks A to positions {1,6} for the whole session. Mirrored
positions cancel *linear* drift exactly, but any stable position effect or
*quadratic* within-rep curvature does not cancel: with centred positions the
mean squared position is 6.25 (outer), 2.25 (mid), 0.25 (inner), so a curvature
term `q·x²` biases A−C by `6q` and A−B by `4q` — and the paired t reports a
*tight* interval around the biased value, which is the worst possible failure
mode. Rung 1B will cycle the three palindromic assignments
`A B C C B A`, `B C A A C B`, `C A B B A C` across reps. This costs nothing,
converts a bias into noise, and makes the position effect estimable.

**A2 — report the within-arm nulls per separation, not pooled.** In a
palindrome the three nulls sit at lags 5, 3 and 1. Under any positive
autocorrelation their variances differ (`2s²(1−ρ_lag)`), so they are not
exchangeable and pooling them is wrong. They are bias/drift *diagnostics*; the
primary error estimate stays the empirical SD of the per-rep contrasts.

**A3 — rung 1 *is* the pilot the review asks for.** The review's central
practical warning is that nobody has measured `s`, the between-rep SD of a
single slot median on this host, and that if it matches the relative noise of
the M5 receipt quintuplet (0.29–0.34 % of 4,141 µs) then `s ≈ 24–28 µs` and the
8 µs/step target is infeasible in *any* design that fits the budget. Rung 1 is
already 24 analysed reps of exactly that quantity, on this host, at this slot
length, with these binaries. I will therefore take `s` from rung 1 rather than
spend a second pilot, and size rung 1B from it.

**A4 — a pre-registered secondary statistic vector, recovered for free.** The
median over 249 steps is blind to precisely the effects a 102-line decode change
is most likely to introduce. Three matter here:

- *Step 0.* The official `T` includes the first decode step at weight 1/128; my
  primary statistic discards it. In `rung1/rep00-pos2-old` step 0 is 9.387 ms
  against a median of 8.234 ms, i.e. **+1.153 ms**, which at the official 1/128
  weight is **+9.0 µs/step** — the same order of magnitude as the entire
  question. A first-use cost (lazy table build, pipeline-state creation, first
  cache allocation) is exactly the kind of thing a prefetch peel or a variant
  dictionary could move, and it would be invisible to the median.
- *Sub-majority tails.* Anything in fewer than 50 % of steps — periodic
  reallocation as KV grows, command-buffer flush cadence, allocator episodes.
  A +300 µs spike every 32 steps moves the mean by +9.4 µs and the median by ~0.
- *Shape trades.* A change that speeds the mode and fattens the tail scores as
  a win on the median and a loss on the official mean.

The `--dump-steps` files already contain all 250 per-step times **including
step 0** (`decode_probe.py:192-195` writes every span; the step-0 drop at
`:243` is in the *profile* path only). So this costs no re-run. From every
slot, rung 1 included, I will additionally compute: step 0 alone;
`mean(0..127)` as the **official analog**; `mean(1..249)`; p90; p99; and spike
mass `Σ(step − median)₊ / N`. The median stays the primary statistic — it is
the right choice on a non-cleanroom host — but **if the median and the
official analog disagree in sign, the official analog governs the decision**,
because it is the statistic the score is actually made of.

**A5 — always publish the signed interval; derive `X` only when it covers 0.**
The `X = max(|lo|,|hi|)` contract silently presumes a null: for an estimate of
+25 with CI [20, 30] it reports "excludes effects larger than 30", which is
true and absurd. Alongside `X` I will publish the 80 %-power MDE (≈2.9·SE,
against the CI's 2.06·SE, because a half-width overstates what the experiment
could reliably *detect*), the one-sided reading where it is the
decision-relevant one, and a TOST against the pre-registered 32.4 µs/step
margin.

**A6 — multiplicity.** Three arms give three pairwise intervals; at per-pair
95 % a joint "no pair differs by more than X" claim has roughly 86 % coverage.
Per-pair claims stay at 95 %; any *joint* claim uses Bonferroni (t at 0.9917,
≈ +9 % width) and says so.

**A7 — three standing qualifiers on every `X`.** (a) the M5 mapping is a
*range* over transfer factor ∈ [0.436, 1.000], not a point; (b) attribution to
source *semantics* is limited by unquantified per-binary layout noise until
A8's gate runs; (c) an M4 Pro bound covers M4-visible mechanisms only — gen 16
selects no `_nax` kernel, threadgroup geometry can flip sign across core
counts, and a 48 GiB host runs the low-memory startup profile.

**A8 — the layout arm, restructured and made conditional.** With one binary per
arm, per-binary compilation/layout noise is *confounded with the treatment*,
and once the measurement half-width is below 8 µs it becomes the dominant error
for any source-level attribution. But a single duplicate arm D gives one draw
and 1 df: if σ_L were 12 µs there is a ~28 % chance `|Δ_CD| < 6 µs` and the
gate returns false comfort. The better shape for the same wall clock is a
**two-marker family**, `A B C D1 D2 C B A`, with D1 and D2 two *distinct*
marker-comment builds of C. The D-family mean stays at the position midpoint so
every drift cancellation survives, D1−D2 is a lag-1 cross-binary null, and it
yields two layout draws instead of one. Even so, 2 df can only run the
qualitative gate "is |C−D| comparable to |C−B|?" — it cannot *estimate* σ_L
(a 2-df SD interval spans roughly [0.5σ, 3.7σ]). Adopted **conditionally**: run
it only if rung 1 gives `s ≤ 15 µs`, since at 8 slots/rep the feasible `s`
drops from 19.8 to 16.6 µs at a 2 h budget. If `s > 15`, rung 1B stays at 6
slots and the layout gate is deferred to a short dedicated session, which I
will recommend rather than run.

**A9 — QC fixed now, before unblinding.** A slot is discarded iff it reports
≥ 1 teacher-forcing divergence, or its p99/median exceeds 1.30. The discard
count is reported. No other exclusion, and no post-hoc rule.

**A10 — join every slot to its binary digest.** The failure that created this
whole assignment was a receipt attributed to the wrong tree. Each arm's
snapshot SHA-256 is already recorded by rung 0 (G0.3) and re-checked in each
run's `provenance.txt`; the analysis will join on it and drop any slot whose
arm digest is absent from that table.

### 1.12.2 Declined, with reasons

**D1 — do not relax the 8 µs/step half-width target.** The review is
arithmetically right that 12 µs/step would still resolve a 32.4 µs/step
M4-equivalent at ≥ 2.3σ and would free about half the budget. But the advisor
set 8 explicitly and called it "the number that decides the round". I keep 8 as
the design target and additionally report what the achieved interval says at 12
and under TOST-32.4, so the advisor can see what a relaxation would have bought
without my having taken it.

**D2 — do not drop arm A.** The review suggests falling back to a 4-slot
`B C C B` if `s` pilots high, on the grounds that B↔C (R3) is the
decision-relevant contrast and the M4 cannot settle A↔B anyway. A↔B is the
exact receipt pair the retracted +20.149 came from; deleting it would leave the
retraction untested on my own rig, which is the one thing this experiment can
cheaply contribute. If `s` makes 8 µs unreachable I will report the achieved
half-width for all three contrasts under N-5 rather than quietly answer a
different question.

**D3 — a longer fixture is not available.** The review's cheapest
variance-reduction suggestion, 250 → 1000 steps for about +14 % wall clock, is
blocked on correctness, not cost: `public_longcopy_gate_english_512_256.json`
supplies 256 expected tokens, so teacher forcing caps at my preregistered 250
steps. Going further requires free-running, which changes the trajectory and
voids the token-identity gate that makes these slots comparable at all.

**D4 — the per-step sync concern is checked and dismissed.**
`research/decode_probe.py:165-168` times a driver-side IPC round-trip per
`decode_step`. The worker must return the sampled token, so a full evaluation
barrier per step is inherent to one-token decoding — and it is exactly what the
serial non-speculative track *mandates*, so no legitimate dispatch-overlap
mechanism is being suppressed by the instrument. The IPC cost is a fixed
additive constant common to both arms: it slightly dilutes *relative* (%)
effects and leaves *absolute* µs/step differences unbiased. Every claim in this
report is in absolute µs/step, so this is not a threat to validity. Sanity
check: the M4 median of 8.234 ms/step against the M5 baseline `T` of
4.142 ms/step is a ratio of 1.99, against a memory-bandwidth ratio of 2.29 —
IPC is not a dominant term.

**D5 — the strategic-retreat recommendation is the advisor's call, not mine.**
The review's strongest claim is that the honest M5 statement is already
available: with σ_receipt = 12.1 µs (df 14), a two-receipt difference of
20.149 µs is z ∈ [0.75, 1.61], single-receipt-pair resolution is ±25–40 µs, and
20 µs is below the instrument's least significant bit; resolving B−A to ±8 µs
*on M5* would need ≈ 19 receipts per arm. Its recommendation is to declare
20 µs below the official noise floor, stop localising it, and redirect the
programme at changes with expected M5 wins of ≥ 30–40 µs, which a single paired
official run can confirm. This agrees with the advisor's own retraction and
with fern's #576 interval. I record it verbatim and surface it in the reply; I
do not act on it.

**D6 — the layout lottery is reported, not exploited.** If the A8 gate ever
finds σ_L ≳ 10 µs, that implies official ranking itself carries a per-submission
compile lottery of that size, which is decision-relevant context for promotion
strategy. I will report the number to the advisor. Re-rolling marker builds to
harvest it would be against the spirit of the rules and I will not do it.

*(Superseded — see § 1.13.3. A8 and D6 are withdrawn: σ_L is zero for this
toolchain, so there is no layout lottery to gate on or to report.)*


## § 1.13 Amendment `r103-a-fb3-base-moved-do-not-rebase-and-new-objective`

Third advisor comment, received after rung 1 had launched and while it was
still executing. Read in full before any further build, run, or analysis
decision. It changes four things and confirms a fifth. Nothing here alters the
already-running rung 1: its arms, statistic, and thresholds were fixed before
launch and stay fixed.

### 1.13.1 The advisor branch moved; the arms do not

`codex/mlxfast-maple-20260804-advisor` advanced
`0f6862d0 → 2be9f8a1 → de0fa89e → f3fb5cba → 449d6744` while this experiment
was in flight. The instruction is explicit: **do not rebase and do not merge.**

The reason is that this experiment's whole content is a *pinned* three-point
contrast. Its arms are

| arm | commit | what it is |
|---|---|---|
| A | `30f752df` | Arm R receipt tree (OLD) |
| B | `e17bdeb1` | frontier receipt tree (`Sources` byte-identical to `a4d3b8dc`) |
| C | `0f6862d0` | assignment base = B + R3 (#558), `+102/−11` in `LagunaRuntimeModel.swift` |

Rebasing would silently move C off the commit whose receipt is the reason for
the question, and the A↔B and B↔C decompositions would stop meaning what § 1.11
says they mean. `f3fb5cba` and `449d6744` are explicitly **not** a fourth arm
and I do not measure them. My branch stays on its recorded base
`0f6862d0`; `git diff --numstat 0f6862d0 HEAD -- Sources Vendor` is empty, so
arm C is exactly my own checkout's submitted surface and the rung-0 `new`
binary is a legitimate C.

Consequence for the deliverable: this PR will merge with a stale base by
design. That is the advisor's stated intent, not an oversight on my part.

### 1.13.2 The submitted surface is still untouched

Confirmed again: zero receipts spent, zero submitted bytes changed. Everything
in this branch is under `research/`. The advisor reports LRM per-file headroom
is now 140,043 B; this experiment consumes none of it.

### 1.13.3 #575 collapses A8 and D6: σ_L = 0 for this toolchain

nezuko's #575 result is the single most useful thing in fb3 for this design.
A **comment-only** strip of `LagunaRuntimeModel.swift` was compiled four times
in a forced-clean interleaved order (orig, cand, orig, cand). All four produced
a byte-identical `MLXFastModel.o`:

```
sha256 = a241e0f9ab439dbe934c000d3db4758d9f4df6a3ea95364cd5e37554a2a5068d
size   = 2,211,568 B
```

with the recorded pitfall that an *incremental* rebuild silently reuses the
stale object and reports a false PASS, so the clean is mandatory.

Two consequences, and they run in opposite directions from what § 1.12 assumed.

**(a) A8 is withdrawn.** § 1.12 A8 proposed a conditional two-marker layout
family (`A B C D1 D2 C B A`) whose D arms differ from C only by a marker
comment, to estimate a code-layout noise term σ_L. #575 shows that construction
cannot work: a comment-only delta produces the *same object file*, therefore
the same binary, therefore two arms that are the identical executable. D1 and
D2 would be extra null slots wearing a different label, not a layout estimate.
I am dropping A8 and returning rung 1B to a 6-slot three-arm rotated
palindrome. This is a strict improvement — it buys back two slots per rep, i.e.
about 90 s per rep, which is real statistical power rather than a wasted
measurement.

I will still spend ~85 s confirming the premise locally rather than importing
it: the rung-1B build step rebuilds C a second time under the name `Cbis` from
a forced-clean tree and asserts `digest(Cbis) == digest(new)`. If that assert
fails, σ_L is not zero on *this* host's toolchain and I will say so; the check
is cheap enough that assuming is worse than testing.

**(b) It removes the frontier reviewer's largest confound, and it strengthens
the retraction.** The frontier critique's central worry (§ 1.12 A8's
motivation) was that an arm-to-arm difference could be a compile-layout
artifact rather than a code-behaviour effect. With σ_L = 0 that worry is gone
for free: any A↔B or B↔C difference I measure is attributable to the source
delta and the run, never to the linker.

It also re-reads fb2's own evidence. The advisor's five identical-code
receipts, `sd(T) = 14.272` (trimmed pooled `12.079`, dof 14), were previously
decomposable into *layout* plus *session* variance. With the layout component
pinned at zero, the whole 12–14 µs is session/run noise. That makes the
retraction of the 20.149 µs target *stronger*, not weaker: there is no
lower-variance sub-population of receipts to appeal to, and a two-receipt
difference genuinely carries σ ≈ 17–20 µs, which is exactly where 20.149 sits
at z ≈ 1.0–1.2.

**D6 falls with A8.** There is no per-submission compile lottery to report and
none to decline exploiting. I record the null finding instead.

### 1.13.4 The objective function changed, and it re-scales what counts as a result

fb3 supplies an empirical acceptance rule derived from the receipt corpus:

> `accepted ⟺ receipt score exceeds the global running maximum across all
> solvers`

with 146 of 147 accepted receipts satisfying it, exactly one rejected receipt
ever exceeding it, and **368 receipts that beat their own previous personal
best and were rejected anyway**. Acceptance is a global-record event, not a
self-improvement event.

The advisor's probability table, from σ(ln score) = 0.4595 %, median
L = 0.998572, honest tree cs = 2.583111 against record 2.616504:

| Δcs vs honest tree | P(record) | receipts for a 50 % chance |
|---|---|---|
| 0.00 % | 0.095 % | 732 |
| 0.25 % | 0.520 % | — |
| 0.50 % | 2.179 % | — |
| 1.00 % | 17.62 % | — |
| 1.50 % | 56.28 % | — |

The operative sentence for me is: **"a ±20 µs/step contrast is
decision-irrelevant."** Effort begins to pay at ≥ +0.5 % cs, and the target
worth aiming at is +1.0 %.

Converting to the units this experiment actually reports, using the § 1.5c
identity `D = 4P + T` and the § 1.5d decisional sensitivity `R1 = 0.622`
(M5 µs/step of `T` per M4 µs/step measured here):

| threshold | Δcs | M5 µs/step on `T` | M4-equivalent µs/step |
|---|---|---|---|
| "starts paying" | +0.50 % | ≈ 33 | ≈ 53 |
| "worth aiming at" | +1.00 % | ≈ 66 | ≈ 106 |
| retracted fb1 target | — | 20.149 | 32.4 |

So the retracted 20.149 µs/step target was already **below** the level at which
work has positive expected value under the new objective — by a factor of about
1.6 — quite apart from being statistically indistinguishable from zero. This is
the deeper reason the fb1 target was retracted, and it is the frame I will use
in § 6.

I preregistered a half-width goal of < 8 µs/step on M4. Under the new objective
that is **≈ 6.6× finer than the decision requires**: a half-width of 20 µs/step
on M4 (12.4 on M5 `T`) already excludes the 33 µs/step "starts paying" line
comfortably. I therefore report *both* bounds in § 6 — the achieved half-width
in M4 µs/step, and the decision-relevant statement "this contrast is bounded
below the +0.5 % cs line" — and I do not grind for 8 if σ is unkind. See
§ 1.13.5.

### 1.13.5 Do not grind; N-5 is the expected and welcome outcome

fb3 is unusually direct about stopping:

- "If rung 1 says A ≈ B ≈ C at a half-width you can defend, that is the whole
  deliverable."
- "Do not extend the run to shrink X below ~8 µs/step."
- N-5 (the composed A→C contrast does not reproduce at the claimed magnitude,
  bounded by X) is "the outcome the advisor expects and is happiest to
  receive."
- No follow-on rung is worth buying.

This overrides the ambition in § 1.12's power table. Concretely, my stopping
rule for rung 1B is now: size REPS from rung 1's *measured* per-rep σ aiming at
hw < 8 µs/step, cap the run at roughly 2 h of wall clock, and **stop at
whichever comes first**. If the achieved half-width lands at, say, 14 µs/step,
that is a reportable, decision-sufficient bound and I will report it as such
rather than launching a second block. § 1.10's stopping rule is amended
accordingly: "extend until hw < 8" is replaced by "run the preregistered block
once, report the achieved hw".

Likewise § 1.11's decision rule keeps its five branches, but outcome 5 (all
three contrasts contain 0 ⇒ N-5) is now the *expected* branch, and outcomes 2
and 3 no longer authorise a rung 2 automatically — fb3 says no follow-on rung
is worth buying, so if a contrast does exclude 0 I report it with its interval
and hand the rung-2 decision to the advisor instead of spending the time
myself.

### 1.13.6 What does not change

The reporting discipline from fb2 is unchanged and is if anything more
important here: **no "neutral", "null", or "unchanged" without an attached
numeric X.** A bound is a result; an unqualified null is not. The three
standing qualifiers from § 1.12 A7 (M4 ≠ M5 architecture, `_nax` unreachable
here, sum-masking) attach to every X I report.


## § 1.14 Amendment `r103-a-fb4-tanjiro-572-merged` — one mechanism per leg, B↔C needs no rebuild, and A↔B is two-wave on M4

Advisor comment 5234299936 (2026-08-09T23:02:27Z) arrived after rung 1 had
finished executing and before rung 2 was launched. It reports that
maple-tanjiro's PR #572 was merged at `ff87caf8` as
`research/maple-tanjiro-r103b-kernel-text-differential.md`. That is a *static*
kernel-text differential over the same OLD→NEW interval I am timing, so it is
the strongest possible complement to this arm: it tells me what changed, and I
am measuring whether it costs anything. Six things it establishes, and what
each one does to my design.

### 1.14.1 Each leg is exactly one mechanism — the factorisation is now verified, not assumed

Tanjiro dumped every JIT Metal library at all three revisions. **101 of 103 are
byte-identical OLD vs NEW.** The two that differ are exactly the two mechanisms
I split on:

- **OLD→MID (#565)** is *one* semantic MSL edit, at line 1280 of the fused
  sliding-attention kernel:
  `for (; i + BN < N; i += 2*BN)` → `for (; i + 3*BN < N; i += 4*BN)`,
  with `pipe_c`/`pipe_d` added in strict `a→b→c→d` order. Bit-exact. **No env
  guard**, which is why arm A has to be a separate binary.
- **MID→NEW (#558)** is the router weight prefetch hoisted outside the
  active-simdgroup guard.

Dispatch count is **408 per decode step at every revision**, and there are
**zero non-equal opcodes across 11,247 compared rows**. So neither leg adds or
removes a dispatch; both are strictly *intra-kernel* edits.

This is a direct, independent confirmation of my § 2.3/§ 2.5 static read, and
it upgrades my three-arm split from "I believe A→B and B→C are separable" to
"the compiled corpus says they are." It also kills the whole family of
alternative explanations that would have required a dispatch-count or
scheduling change: with 408 dispatches everywhere, any real ΔT has to be
*inside* one of those two kernels.

It also means my rung-1 A→C measurement is the *sum of exactly two* mechanisms,
not of an unknown number. That makes the additivity check in rung 2
(`A→B` + `B→C` ≈ `A→C`) a genuine consistency test rather than a formality.

### 1.14.2 🔴 B↔C needs no rebuild, and the advisor wants it interleaved

`DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0` on the NEW binary reproduces MID's whole
103-library corpus bit-for-bit. So B and C are the *same binary* under two env
values, and B↔C can be run as an interleaved paired contrast inside one
matched block. The advisor's stated reason: the archive's within-process σ is
≈ 19.5 against ≈ 48 cross-process, i.e. roughly a **2.5× tightening**.

I have to be precise about what I can and cannot take from that. § 2.6.7 of
this document already established, from `LagunaRuntimeModel.swift:686-704`,
that `lagunaRouterWeightPrefetch` is a **process-once `let`** read from
`ProcessInfo`. There is no way to toggle it *within* a process, so I cannot
collect the within-process σ ≈ 19.5 that the advisor is quoting; that figure
comes from designs where both arms live in one process. What I *can* do — and
what rung 2 does — is put B and C in the **same matched block, adjacent in the
rotation, running the identical binary**, so the contrast is free of every
build-side and metallib-side nuisance term and differs only in one `ProcessInfo`
read. That is the strongest form available to me without editing the runtime,
and editing the runtime is out of scope for a zero-submitted-bytes arm.

Concretely: rung 2 keeps `A` on the `old` snapshot and puts `B` and `C` on the
**same** `new` snapshot binary with `DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0` and
`=1` respectively. G2.1 (§ 3.5) verifies by trace that the two env values
really do select `pf0` and `pf1`.

### 1.14.3 ⚠️ A↔B is structurally uninformative on M4 — two waves versus one

Both fused-attention kernels dispatch exactly **32 threadgroups**. On this
20-GPU-core M4 Pro that is **two waves**; on a ≥32-core ranked host it is
**one**. A software-pipeline depth change alters how much latency each
threadgroup can hide, and a second wave changes what there is to hide it
behind. So an M4 A↔B number measures the mechanism *on a two-wave occupancy*,
which is not the ranked host's regime.

Tanjiro cancelled his own preregistered M4 A/B at 6 legs (K = 3 of 16) for
exactly this reason and claimed nothing from it. The advisor gives me two
options: cancel the A↔B leg, or **re-scope it as a mechanism measurement** with
a mandatory wave caveat stated either way.

**Decision: re-scope, do not cancel.** Reasons, in order of weight.

1. The A↔B slots are **already paid for**. Rung 2's rotation needs three arms
   to give me B↔C with a per-arm null and full position balance; dropping A
   would not save the block, it would just shrink it to a 2-arm design whose
   nulls are weaker. The marginal cost of keeping A is one slot per rep.
2. Rung 1 has already measured **A→C = +27.84 µs/step [+18.69, +36.99]** on
   this host with a quiet null. That composite number is *already* published
   evidence in this document. Refusing to decompose it would leave a measured
   regression attributed to "one of two mechanisms, unknown which", which is
   strictly worse for the advisor than a decomposition with a caveat.
3. The caveat is cheap and I can state it exactly: **any A↔B number I report
   describes the depth-4 pipeline at 2-wave occupancy on 20 cores and is not
   transferable to the 1-wave ranked host, in magnitude or in sign.** That
   sentence attaches to every A↔B figure below, including a null one.

What I will *not* do is use an M4 A↔B result to rank the two mechanisms for
the ranked host, or to recommend reverting #565. Those are exactly the claims
the wave argument forbids.

### 1.14.4 The sign contradiction — PR #103 says depth 4 was *faster* on M4

`research/RESEARCH_ARCHIVE_through-round-91.md:4894-4896` (PR #103) reports, on
M4, attention pipeline **depth 4 = −1.039 % (faster)**, depth 8 = +0.485 %,
against a ±0.73 % noise floor. The M5 receipt pair puts the depth-4 tree at
**+20.15 µs/step (+0.30 %) worse**. And **no depth has ever been measured on
M5.** Round 104 is making that the flagship, going to another student.

This is the single most important thing in fb4 for how I write up my result,
because it is a *pre-registered prediction of the sign* of my A↔B leg:

> If my M4 A↔B leg says the 4-deep pipeline is **faster**, that is consistent
> with PR #103 and is **not** evidence about the ranked host.

My own § 2.6.6 independently predicted a possible sign flip between M4 and M5
from occupancy. Two independent routes to the same prediction means that if I
observe A faster than B on M4, the *only* honest reading is "M4 and M5 disagree
about this mechanism, as they have before" — not "#565 was fine" and not "#565
was a regression that M4 confirms". I am writing that sentence into § 6 now, in
advance, so it cannot be retro-fitted to whichever sign comes out.

Note the arithmetic tension this creates with rung 1. Rung 1 measured
A→C = **+27.84** (C slower). If A→B is *negative* on M4 (per PR #103), then by
additivity B→C must be *more* positive than +27.84 — i.e. the router-prefetch
peel would carry the whole regression and then some. If instead A→B is
positive, the two mechanisms share it. Rung 2 resolves which, on this host.
That is a real, decidable question, and it is the reason to run the block.

### 1.14.5 Tooling available for a rung-3 census, and its one gotcha

Tanjiro left reusable scripts in `research/r103b/scripts/`: an MSL dumper,
`trace.patch`, `compare_msl.py`, `compare_dispatch.py`, `seqalign.py`. The
gotcha he flags: his dumper hooks `Device::build_library_`, not
`Device::get_library`, so it sees libraries at build time rather than at
fetch time. Tracer output quota is 1,671,168 B.

Under fb3's "do not grind" rule I am **not** launching a per-kernel census
speculatively. If rung 2 lands a leg above the ≥ 33 µs/step decision-relevance
bar, these scripts are the first thing I would reach for, and § 1.7a's rule-58
reuse assessment should be re-done against them rather than against the older
census scripts, because Tanjiro's are newer and already validated on this
exact OLD/NEW pair.

### 1.14.6 What fb4 does not change

The advisor is explicit: *"Nothing here changes your base or your deliverable.
fb3 still stands: do not rebase. Keep going."* So:

- arms stay pinned at `30f752df` / `e17bdeb1`-equivalent / `0f6862d0`;
- no rebase, no merge of the advisor branch;
- zero submitted bytes, zero receipts;
- fb3's stopping rule stands — n is preregistered, and I do not extend a block
  to chase a half-width below ~8 µs/step;
- fb3's decision-relevance scale stands — ≥ +0.5 % cs ≈ ≥ 33 µs/step on `T` is
  where effort pays, and a ±20 µs/step contrast is decision-irrelevant *as a
  chase target*.

### 1.14.7 Blinding disclosure (e)

Running the G2.1 reachability gate (§ 3.5) required executing each arm for 4
decode steps, and `decode_probe.py` prints a summary line. I therefore saw four
throwaway medians: A/unset 8.281 ms, A/`pf0` 8.305 ms, B/`pf0` 8.294 ms,
C/`pf1` 8.381 ms. These are n = 1, 4 steps, unwarmed, and are not the
instrument; the 4-step window is dominated by first-call effects that the
250-step blocks discard. I record them because the disclosure rule is
"everything I saw", not "everything I found persuasive". They were seen
**after** every rung-2 threshold in § 1.5/§ 1.5c and the rung-2 design in
§ 4.5 were already committed to git, so they cannot have shaped the design.



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

### 3.5 Gate G2.1 — the three arms really are three arms (reachability, rule 77)

Before spending a 106-minute three-arm block I verified that each arm's control
actually reaches the scored decode path, and that the two env-selected arms
select different code. `DARKBLOOM_TRACE_FUSION=1` makes
`LagunaRuntimeModel.swift:75-97` print each fusion site once; line 1219 prints
the router variant as `residual+rmsnorm+router rpg<N> pf<P>`. Four probes at
`--steps 4`, supervised job `17689829-eae6-4bd6-8d02-4bc95927ce21` (exit 0,
170 s), outputs under `/tmp/maple-r103a/g21/`:

| probe | binary | env | decode router trace | tokens |
|---|---|---|---|---|
| A / unset | `old` | — | `residual+rmsnorm+router rpg8` | 0 divergences |
| A / pf0 | `old` | `…PREFETCH=0` | `residual+rmsnorm+router rpg8` | 0 divergences |
| B | `new` | `…PREFETCH=0` | `residual+rmsnorm+router rpg8 pf0` | 0 divergences |
| C | `new` | `…PREFETCH=1` | `residual+rmsnorm+router rpg8 pf1` | 0 divergences |

**G2.1 PASS**, and it buys three separate things.

1. **The env control reaches the scored path.** `pf0` and `pf1` are printed by
   the decode-time router site, not by a prefill or fallback site, so the toggle
   is a real dispatch difference on the timed path — the assignment's "a knob on
   an unused fallback is not a timing experiment" requirement is met.
2. **Arm A is inert to the flag.** `old` prints `rpg8` with *no* `pf` suffix
   under both env states. That is the factorisation made visible: A predates the
   prefetch mechanism entirely, so A's router is *definitionally* B's router,
   and the A↔B leg cannot be contaminated by a router difference. This is the
   runtime-side confirmation of § 1.14.1's static claim that OLD→MID is one
   sliding-attention edit and nothing else.
3. **Correctness holds on every arm.** All four probes teacher-force clean
   against `correctness_prompts/public_longcopy_gate_english_512_256.json`.

The throwaway 4-step medians these probes printed are disclosed in § 1.14.7.

## § 4 Rung 1 — paired ABBA e2e decode on M4

### 4.1 What was actually executed (provenance, recorded before unblinding)

Launched as supervised job `92c3bf47-f6c1-4278-b811-0f4df8418bf6` with

```
SNAP=/tmp/maple-r103a-snap OUT=/tmp/maple-r103a/rung1 REPS=26 STEPS=250 \
  WARMUP_REPS=2 bash research/maple-frieren-r103a-abba.sh
```

- HEAD at launch `7dd93f75`; `digest_before` =
  `c3fafd30b4fdba6d3058746e79a715a53a072c5d5c77b0716a3a73dbd385f492`, equal to
  the rung-0 `digest_head` / `digest_at_new_build` / `digest_after_restore`
  (§ 3.1, gate G0.4). The timed run therefore used binaries provably built from
  the recorded trees.
- Slot order `oldA old new oldB`, reversed on odd reps. `old`/`new` occupy the
  interior positions {2,3} and are the contrast; `oldA`/`oldB` occupy the
  exterior positions {1,4} and are a rule-79 identical-code null at position
  separation 3.
- `REPS=26`, first 2 discarded as warm-up ⇒ **K = 24** paired repetitions,
  104 slots, `STEPS=250` teacher-forced one-token decode steps per slot.
- Binary identity as recorded in `provenance.txt`: `new` =
  `32d0a3d4…881ddb` (49,190,344 B); `old` = `oldA` = `oldB` =
  `d36a981f…4a911e` (49,094,856 B). The three "old" labels are the *same
  executable*, which is what makes the exterior pair a valid null.
- Every arm shares the same `mlx.metallib`
  (`8e8b18af…3097ec`, gate G0.5), so no part of any contrast is a Metal
  shader-source difference.

Arm mapping to § 1.11's three-point frame: `old` = **A** (`30f752df`), `new` =
**C** (`0f6862d0`). Rung 1 therefore measures the **composed A→C contrast**,
which is exactly the "missing microseconds" question as originally posed. The
A↔B / B↔C decomposition requires arm B and is deferred to rung 1B (§ 4.4).

### 4.2 Gates first

Job exit 0 after ≈ 4,600 s. All post-hoc integrity gates pass before any number
below is allowed to mean anything.

| gate | result |
|---|---|
| **G0.2** correctness | **PASS** — 1 distinct token checksum across all 104 slots (`229303103`). Every arm produced byte-identical greedy output for all 250 steps. |
| **rule 75** tree stability | **PASS** — `digest_before` = `digest_after` = `c3fafd30…d385f492`. |
| **QC** (`p99/median ≤ 1.30`) | **PASS** — 0 of 104 slots rejected. |
| **G0.5** metallib parity | **PASS** (§ 3.3), carried forward. |

G0.2 is the load-bearing one. A speed difference between arms that also changed
outputs would be worthless; 104 slots agreeing on a single checksum means the
+27.84 µs/step below is a pure cost difference at fixed behaviour.

### 4.3 Result — the composed A→C regression reproduces on independent M4 hardware

Decision statistic: per-slot **median of decode steps 1…249**, contrasts formed
per repetition and then aggregated over K = 24 (§ 1.5, § 1.5a). OLD steady level
is **8242.7 µs/step**.

| contrast | K | mean Δ (µs/step) | 95 % CI | sign +/− |
|---|---|---|---|---|
| **`new − old` (A→C)** | 24 | **+27.84** | **[+18.69, +36.99]** | **24/24** |
| `oldB − oldA` (null, sep 3) | 24 | −1.45 | [−5.62, +2.72] | 11/12 |
| `oldA − old` | 24 | −2.10 | [−13.17, +8.96] | 14/10 |
| `oldB − old` | 24 | −3.55 | [−13.16, +6.05] | 13/11 |

**The CI excludes zero, and the sign is 24/24 — every single repetition put
`new` slower than `old`.** Under the null of no effect a 24/24 sign split has
probability 2⁻²³ ≈ 1.2 × 10⁻⁷. The identical-code null over the same 24 reps is
quiet at −1.45 [−5.62, +2.72], i.e. the instrument is not manufacturing
differences: it separates two copies of the *same* binary by −1.45 ± 4.17 and
two *different* binaries by +27.84 ± 9.15.

As a fraction of the OLD step this is **+0.3378 %**. The M5 receipt pair's
+20.149 µs/step on `T` is **+0.4865 %** of its own step.

The result is stable across every statistic in the preregistered set:

| statistic | Δ `new − old` | 95 % CI |
|---|---|---|
| median (decision) | +27.84 | [+18.69, +36.99] |
| trimmed | +28.22 | [+17.99, +38.44] |
| mean | +25.51 | [+13.45, +37.56] |
| `mean_first128` (official-window analog) | +26.63 | [+9.81, +43.45] |
| `step0` (diagnostic only) | −428 | ± 734 |

`mean_first128` matters because the official decode axis is 128 steps, not 250.
It agrees in sign and magnitude with a wider interval, as expected from a
quarter of the data. `step0` is uninformative at this K, which is the
preregistered expectation from § 1.5b — the one-time JIT/warm cost is large
(≈ 1.3 ms) and its variance swamps a 28 µs effect.

**Against the preregistered bars** (§ 1.5c, all in M4-equivalent µs/step):

| bar | value | verdict |
|---|---|---|
| fixed-overhead transfer (×1.000) | 20.1 | CI **covers** |
| **R1 decisional (÷0.622)** | **32.4** | **CI covers** |
| proportional (÷0.505) | 39.9 | CI **entirely below** |
| bandwidth-ratio (÷0.436) | 46.2 | CI **entirely below** |

So the measured M4 effect is consistent with the M5 receipt delta under the
fixed-overhead and R1 transfer models, and inconsistent with the two models
that would require the effect to scale with M4's lower bandwidth. Transferring
*back* to M5: ×0.622 gives **+17.3 µs/step**, proportional gives **+14.0**;
both bracket the observed +20.149.

**Preregistered verdict: OUTCOME 4, inconclusive-underpowered.** The half-width
is 9.15 µs/step against fb2's < 8.0 target, so I am not entitled to call the
localisation *precise*, and N-2 does not fire (the null is quiet) and N-5 does
not fire (a contrast excludes zero). Note the asymmetry this creates and I
should not paper over: the *existence* of a regression is established at
p ≈ 10⁻⁷ by the sign test, while the *magnitude* is only pinned to ±9 µs/step.
Those are different claims with different strengths.

### 4.4 What this does and does not say about fb2's retracted target — with two claims withdrawn

I submitted the § 4.3 result to an independent adversarial review before
writing this section (frontier reviewer, task `f8b9cbd4`, given the design and
numbers but no context and no ability to run anything). It broke two of the
three claims I had drafted. I am recording the original claims and the
withdrawals rather than quietly writing the corrected version, because the
errors are instructive and because fb2 asked for exactly this kind of
discipline.

**Withdrawn claim 1 — "two independent hosts agreeing is strong combined
evidence."** I had written that the probability of both M5 and M4 showing a
same-signed regression by chance is much smaller than either alone. That is
**arithmetically false and structurally a selection error.** The M4 experiment
was commissioned *because* the M5 delta had a positive sign; conditioning on
that, sign agreement is close to a coin flip under the M5-noise hypothesis and
carries almost no information. And the M5 receipt is a z ≈ 1.1 datum, one-sided
p ≈ 0.14, which can contribute at most about a factor of two to any honest
combination — nowhere near "much smaller". **fb2's retraction of +20.149
stands, and nothing in rung 1 rehabilitates it.**

**Withdrawn claim 2 — "the transfer models bracket +20.149."** I had written
that ×1.000 and ×0.622 map my +27.84 back to +17.3…+27.8 on M5, bracketing the
observed +20.149. This is circular twice over. First, the transfer menu was
selected post hoc: § 1.5c lists four factors and I quoted the two that land on
the target while omitting ×0.436, which would miss. Second, I bracketed with
*point estimates*; propagating my own CI through the same menu gives roughly
[+8, +37] on M5, an interval so wide it brackets essentially any plausible
value including zero. The bracketing was not a test. There is also a deeper
objection: M4 Pro reports Apple GPU generation 16 and does not select the
`_nax` kernel family the ranked M5 uses, so a scalar transfer factor between
two hosts running *different kernel variants* may be a category error rather
than a mis-estimated constant.

**What survives, stated at its correct scope.** The reviewer accepted the sign
test itself: the 2⁻²³ arithmetic is right, using the same data for the CI and
the sign test does not invalidate the latter, and the palindrome makes the sign
test *conservative* against the +17 µs/step position artefact rather than
inflated by it. But it accepted it only at this scope:

> **These two particular binaries differ, on this particular M4 host, in this
> particular session, by +27.84 µs/step [+18.69, +36.99], at provably identical
> output.**

The gap between that and "the two source changes cost 27.84 µs/step" is one
session and one build pair. My ±9 half-width is a *within-session* interval; it
contains no rebuild variance and no day-to-day variance, and § 1.13.3's σ_L = 0
result covers only comment-only edits that produce a byte-identical object
file, which is not this case. So the honest headline is a statement about two
binaries, not yet about two source changes.

**The sentence I will actually stand behind, replacing the withdrawn claim:**

> An independent M4 Pro host, with K = 24 palindrome-paired repetitions and a
> quiet identical-code null, separates the A and C *binaries* by +27.84
> [+18.69, +36.99] µs/step at identical output. This neither confirms nor
> rehabilitates the retracted +20.149 µs/step M5 figure — the M4 run was
> selected on the M5 sign, so agreement in sign is nearly uninformative — but
> it does establish that a difference of this order exists between the two
> binaries on at least one Apple Silicon host, which the single M5 receipt pair
> could not establish anywhere.

Standing qualifiers (§ 1.12 A7) attach: no `_nax` here, nothing is a prefill
claim, and per § 1.14.3 this composed figure does not license ranking the two
constituent mechanisms.

### 4.4a Instrument characterisation, for whoever runs the next block

These are the numbers a future arm should budget against, not results.

**Per-arm slot-to-slot sd (median over reps):** `new` 26.71, `old` 24.93,
`oldA` 6.29, `oldB` 6.02 µs/step. The *exterior* positions are four times
quieter than the interior ones. That is a position effect, not an arm effect —
see below.

**Position diagnostic** (`/tmp/maple-r103a/posdiag.py`), mean level by slot
position: pos1 8240.6, pos2 8258.2, pos3 8258.8, pos4 8242.9 µs/step. **The two
interior slots run ≈ +17 µs/step hotter than the two exterior slots.** The
palindrome is what saves the design: `old` and `new` each occupy {2,3} equally
often and `oldA`/`oldB` each occupy {1,4} equally often, so the position effect
cancels exactly in both the contrast and the null. Had I used a fixed
(non-reversed) order, +17 µs/step of pure position artefact would have loaded
directly onto a +28 µs/step effect. Per-cell sd confirms the interior slots are
also the *noisy* ones: (pos2,`old`) 31.84 and (pos3,`new`) 32.89 versus
(pos1,`oldA`) 2.53 and (pos1,`oldB`) 5.37.

**Half-block stability:** reps 2–13 give +21.80 (sd 14.31), reps 14–25 give
+33.88 (sd 26.40); the difference is t ≈ 1.39, not significant. Pooled
**s = 21.66** for the contrast against **s = 9.87** for the null.

**Cost model.** ≈ 44.2 s per slot, of which ≈ 42.5 s is *model load*: 250 decode
steps is ≈ 2.06 s and the 512-token seed forward is ≈ 0.55 s. Load dominates by
20×. Two consequences: (i) per-slot cost is essentially irreducible without
in-process arm switching, which § 2.6.7 shows is impossible for this control;
(ii) **more steps per slot are nearly free**, so the natural way to buy
precision is a longer decode window — except the public fixture caps at 256
expected tokens, so 250 is already at the ceiling. Precision therefore has to
come from more reps or from averaging repeated slots of the same arm, which is
exactly what the rung-2 rotation does.

### 4.4b The strongest alternative explanation: host binary layout, not the source changes

The reviewer's top-ranked non-semantic explanation is one I had not written
down, and it is a good one. The two binaries differ in size by **95,488 bytes**
(49,190,344 vs 49,094,856). Changing a binary's size displaces code and data
placement, changing instruction-cache set mapping, branch-predictor aliasing,
and page boundaries. This is the classic measurement-bias failure mode
documented by Mytkowicz et al., *Producing Wrong Data Without Doing Anything
Obviously Wrong!*, and by Curtsinger & Berger's Stabilizer work; the reported
effect sizes there routinely exceed the effect the experimenter was trying to
measure.

The arithmetic is uncomfortably easy to satisfy. There are **408 GPU dispatches
per decode step** (§ 1.14.1). A layout-induced slowdown of **68 ns per
dispatch** in the host-side encode path reproduces my entire +27.84 µs/step. 68
ns is a handful of cache misses.

Two things narrow it but neither closes it:

- The confound can only act **host-side (CPU)**. G0.5 proved the AOT
  `mlx.metallib` is byte-identical across arms, and § 1.14.1 reports 101 of 103
  JIT libraries byte-identical. The GPU code is essentially the same code at
  the same addresses. So this hypothesis requires the decode step to be
  sensitive to CPU-side encode cost, which is an open question I have not
  measured.
- § 2.3 found the NEW binary's growth is dominated by **longer embedded shader
  source strings and a wider variant table** — i.e. mostly *data*, not
  executable text. If the growth is confined to `__cstring`/`__const` and the
  pre-existing hot functions retain their addresses, the displacement for the
  hot path is zero and the hypothesis largely evaporates.

**Cheapest decisive discriminator, and it is static.** Compare the two
binaries' Mach-O section maps and then the *addresses* of the hot decode
symbols: `nm -n` on both and diff the addresses of the pre-existing functions.
If the hot host functions sit at identical addresses in both binaries, layout
displacement for those functions is exactly zero and the hypothesis is dead for
the code that matters. This costs one command and no GPU time. It is deferred
only until the rung-2 block finishes, so as not to perturb a live timing
session; it is the first thing I run afterwards, recorded as § 5.4.

**The structurally important consequence for rung 2.** The three arms are *not*
equally exposed to this confound, and the asymmetry is exactly the useful kind:

| leg | binaries | layout confound |
|---|---|---|
| A→B | `old` vs `new` | **fully exposed** (the whole 95,488-byte delta) |
| A→C | `old` vs `new` | **fully exposed** (same binary pair) |
| **B→C** | `new` vs `new` | **immune** — same binary, same size, same addresses, differing only in one `ProcessInfo` read verified by G2.1 |

So B→C is a **layout-clean** measurement, and it was already designed that way
(§ 1.14.2) for a different reason. That gives rung 2 a real decision structure
that I am fixing in advance of seeing its data:

- If **B→C is large and A→B is small**, the router-prefetch peel carries the
  regression, and that conclusion is safe: it is layout-immune on its own, and
  a small A→B simultaneously *bounds* the layout effect near zero.
- If **A→B is large and B→C is small**, the result is **ambiguous between the
  #565 pipeline edit and pure layout displacement**, and I must say so rather
  than attribute it to #565. Resolving it would need the § 5.4 symbol-address
  check and, if that were inconclusive, a size-matched placebo build of
  revision A — which I would propose to the advisor rather than run, since it
  is a new experiment.

### 4.4c Three further weaknesses the reviewer flagged, and their disposition

1. **My rung-1 null is in the wrong place.** The identical-code null
   (`oldA`/`oldB`) lives at the two *exterior* positions, whose per-cell sd is
   2.53 and 5.37, while the contrast lives at the two *interior* positions,
   whose per-cell sd is 31.84 and 32.89 (§ 4.4a). So "the null is quiet,
   therefore the instrument is sound" compares a quiet regime against a noisy
   one and is weaker than it reads. **Rung 2 fixes this by construction**: its
   rotation puts each arm at positions (p, 7−p), so the separation-1 null is
   the pair (pos 3, pos 4) — an identical-code null measured at exactly the two
   interior positions the critique says rung 1 failed to probe. This was
   designed for the position artefact and turns out to answer the null-placement
   objection too.
2. **Window mismatch.** My slots are a 512-token seed plus 250 decode steps
   with the statistic taken over steps 1…249; the official axis is 512 prefill
   plus 128 decode steps. `mean_first128` (§ 4.3) is the closest analog I have
   and agrees in sign, but it is 128 steps of a 250-step run, not a 128-step
   run, and the fixture's 256-token cap prevents a longer window. Recorded as a
   known scope limit, not fixed.
3. **The decisive cheap experiment is not mine to run.** The reviewer's
   observation is correct and worth stating plainly to the advisor: the
   question "did A→C regress the ranked host" is answered directly and cheaply
   by *paired A/C measurements on M5 itself*, replicated. Everything I can do
   on M4 is a proxy for that. Since my arm is preregistered as zero-receipt and
   this host is not M5, I flag it in § 6 as the highest-value follow-up rather
   than attempting a substitute for it.

### 4.5 Rung 2 design — three arms, rotated palindrome, preregistered n

Committed to git before launch (commit `ea0286d`) and executed as supervised
job `e5822dad-1107-408e-ac01-044e04ec4b29`:

```
SNAP=/tmp/maple-r103a-snap OUT=/tmp/maple-r103a/rung2 \
DESIGN=rotate REPS=24 STEPS=250 WARMUP_REPS=3 \
ARMS="A:old B:new:DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0 C:new:DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1" \
ASSERT_DIFFER="old:new" ASSERT_SAME="" \
  bash research/maple-frieren-r103a-abba.sh
```

Six slots per repetition. The order is a rotation-by-rep followed by its own
mirror, so rep 0 is `A B C C B A`, rep 1 is `B C A A C B`, rep 2 is `C A B B A C`,
cycling with period 3. Verified independently by `/tmp/maple-r103a/order-check.sh`
before launch.

Why this shape:

- **All three legs in one matched block.** `A→B`, `B→C` and `A→C` come from the
  same thermal state, the same session, the same rotation. Additivity
  (`A→B` + `B→C` = `A→C`) then holds *exactly* by construction, so any deviation
  is a bug in my arithmetic rather than a physical claim — and the A→C leg is
  an internal replication of rung 1 at no extra cost.
- **Every arm visits every position** over a 3-rep cycle, which kills the +17
  µs/step interior/exterior artefact of § 4.4a for all three arms symmetrically
  rather than only for the pair that happens to share positions.
- **Each arm appears twice per rep**, so each contributes a rule-79
  identical-code null at position separation 5, 3, or 1 depending on the
  rotation phase — for free, and the analyzer now keys nulls on
  `(arm, separation)` and never pools across lags (§ 1.12 A2). Rung 1 had a
  single null at one lag; rung 2 has nine.
- **Averaging the two slots of an arm** is the only precision lever available
  given § 4.4a's cost model.
- **B and C are the same binary**, per § 1.14.2, differing only in one
  `ProcessInfo` read verified by G2.1.

**Preregistered n: 24 reps, first 3 (one full rotation cycle) discarded as
warm-up, K = 21 analysed** — a multiple of 3 so the rotation is balanced.
≈ 6,365 s ≈ 106 min. Power: if two-slot averaging drops the contrast s from
21.66 to ≈ 17, the half-width at n = 21 is ≈ 7.7 and meets fb2's < 8 target;
if s stays at 21.66 it is ≈ 9.9 and misses. **Either way I stop at 21.** fb3 is
explicit that I must not extend a block to chase a half-width, and § 1.13.4's
table says a ±20–30 µs/step contrast is decision-irrelevant as a chase target,
so buying the last 2 µs of half-width has no decision value.

**Deliberately excluded: the `pf5` placement control.** § 2.6.7 established that
`DARKBLOOM_ROUTER_WEIGHT_PREFETCH=5` is a documented placement variant whose
difference from `1` isolates cross-barrier overlap from the peel itself, and it
is bit-exact with arm 0. It would be a genuinely informative fourth arm. It
would also make the block 8 slots per rep, ≈ 141 min, for a sub-mechanism split
of a leg that is itself below the decision-relevance bar. That is grinding, and
fb3 forbids it. Recorded as a follow-up in § 6 instead.

### 4.5a Two analysis amendments, fixed while rung 2 was running and before any rung-2 number was read

Both were written into `research/maple-frieren-r103a-analyze-multi.py` in the
same commit that adds this section — the child of `5bc8f13`, and the only commit
on this branch that touches the analyzer after rung 1 — while job `e5822dad` was
still executing. I had at that point seen no rung-2 statistic beyond the rep-0
position-1 provenance line already disclosed in § 4.1's blinding log. Both are pre-specified rules, not
selections made by looking at which answer they gave.

**(i) The cycle-blocked estimator becomes primary when the rotation closes.**
Writing out the rotation exposed a defect in the naive per-repetition analysis
that § 4.5 had not accounted for. Within *one* repetition of `A B C C B A`, arm
A sits at the exterior slot pair {1,6} and arm C at the interior pair {3,4}, and
§ 4.4a measured the interior as ≈ +17 µs/step hotter. So a single repetition's
C−A carries a deterministic position term of that size; the rotation cancels it
only after one complete cycle of three repetitions. Left in place, that term
does not bias the mean — the design is balanced and K = 21 is a multiple of 3 —
but it inflates the residual and therefore every half-width, which is precisely
the quantity fb2 said decides the round.

The amendment groups repetitions into complete rotation cycles, averages the
contrast within each cycle, and treats the cycle as the unit of replication.
The position term cancels exactly rather than being carried as noise. The rule
for which estimator is primary is fixed by the design and not by the width: the
cycle-blocked one whenever at least two complete cycles exist for every pair,
the per-repetition one otherwise. Both are always printed.

**This also applies retroactively to rung 1, and I am not restating rung 1.**
Rung 1's mirrored layout has two phases, so the same code blocks it into 12
even/odd pairs. Re-running the amended analyzer on the rung-1 data gives the
**identical point estimate −27.84 µs/step** with the half-width 9.15 → **8.80**
and the interval [−36.99, −18.69] → [−36.68, −19.00]. The estimator was devised
after rung 1 was unblinded, so it is not used to change rung 1's published
verdict: § 4.3's numbers stand as preregistered and rung 1 remains OUTCOME 4
(underpowered) because 8.80 is still above 8.00. I record the variant here only
so that the rung-1 and rung-2 half-widths are not compared across two different
estimators without the reader being told.

Why the point estimate is unchanged is worth stating, because it is the check
that the amendment is a variance reduction and not a different quantity: in
rung 1 `old` and `new` both occupy the interior pair {2,3} and `oldA`/`oldB`
both occupy the exterior pair {1,4}, so the contrast of interest was already
position-matched. What the blocking removes there is only the residual
even/odd asymmetry. In rung 2 the rotation makes every arm visit every position
pair, so blocking removes the whole artefact.

**(ii) The rule-79 null is additionally pooled across arms at fixed separation.**
Nine null cells of 7 observations each is too thin to quote against a contrast:
at n = 7 the half-width carries `t95 = 2.447`. Every cell at one separation is
an identical-code within-repetition difference between the same mirrored slot
pair, so under the design's own null they are exchangeable across arms and pool
legitimately to n = 21 per separation. The per-arm cells are still printed —
heterogeneity among them is itself diagnostic — but the pooled row is what the
N-2 verdict should be read against. Note this makes N-2 *easier* to fire, i.e.
it is conservative in the direction of downgrading my own contrasts.

This second amendment also repairs the § 4.4c weakness the adversarial review
found in rung 1: there the null lived only at the quiet exterior positions
while the contrast lived at the noisy interior ones. In rung 2 the sep-1 null
is measured at the interior pair {3,4} and the sep-5 null at the exterior pair
{1,6}, so the null now spans the same variance regime as the contrasts instead
of sampling only the favourable end of it.

**(iii) Reconciliation is against rung 1, not internal.** `A→B + B→C = A→C`
holds to floating point by construction of the estimator, so there is no
internal additivity residual worth publishing; saying otherwise would dress an
identity up as a check. The informative reconciliation is that rung 2 measures
the same A→C contrast as rung 1 in a separate session under a different slot
layout, and the analyzer now prints that two-sample comparison against the
stored rung-1 value.

## § 5 Rung 2 — three-arm rotated block, decomposing A→C into A→B and B→C

Design and preregistered n in § 4.5, analysis amendments in § 4.5a.

### 5.1 Provenance and gates

Job `e5822dad-1107-408e-ac01-044e04ec4b29`, exit 0, 6,232 s, launched at branch
head `ea0286d3f84aab58fb022dd0fad8e0b33d454877`. Command as recorded in § 4.5:
24 repetitions × 6 slots = **144 slots**, `DESIGN=rotate`, `STEPS=250`,
`WARMUP_REPS=3`, `K = 21` analysed.

| Gate | Result |
| --- | --- |
| G0.2 output identity | **PASS.** All 144 `.tokens` files hash to the single value `aaf1cccc923270801a1e16da07012bc822d9f85eb33ce6e2039fb38f407e51d8` (250 tokens each). Every slot emitted the *identical* token sequence. |
| Teacher-forced divergences | **PASS.** `0 divergences (all match)` in 144 of 144 slot logs. |
| Rule 75 (tree unchanged) | **PASS.** `digest_before = digest_after = c3fafd30…d385f492`. |
| Binary identity | **PASS.** `new` = `32d0a3d4…81ddb`, `old`/`oldA`/`oldB` = `d36a981f…4a911e`, unchanged from rung 0. |
| `ASSERT_DIFFER=old:new` | **PASS.** |
| QC (p99/median ratio ≤ 1.30) | **PASS.** 0 slots rejected, 0 repetitions voided. |
| Rotation closure | **PASS.** 3 phases × 7 complete cycles = 21 reps, so the cycle-blocked estimator is primary per § 4.5a(i); `primary_estimator: cycle-blocked` in `analysis-multi.json`. |

So the behavioural claim is airtight: **all three arms are output-identical**, and
nothing in this section is a correctness trade.

### 5.2 Primary result — the composed effect lives entirely in the router leg

Primary statistic: per-slot median of steps 1…249. Primary estimator:
cycle-blocked over 7 complete rotation cycles. Arm levels A 8245.4, B 8233.0,
C 8267.6 µs/step.

| Leg | Mechanism | Estimate (µs/step, M4) | 95 % CI | Cycle signs | Layout-exposed? |
| --- | --- | --- | --- | --- | --- |
| **A→B** | #565 attention pipeline 2→4 **+ binary layout** | **−12.39** (faster) | [−24.64, −0.14] | 0/7 | **yes, fully** |
| **B→C** | #558 / R3 router weight-prefetch peel, alone | **+34.58** (slower) | [+26.39, +42.77] | 7/0 | **no — one binary** |
| A→C | both, composed | +22.19 | [+16.94, +27.45] | 7/0 | yes, fully |

Three things follow, in descending order of how much I trust them.

**(a) A→C replicates rung 1.** Rung 1 gave +27.84 ± 9.15 in a different session
under a different slot layout with a different estimator; rung 2 gives
+22.19 ± 5.26. The difference is −5.65 µs/step, ≈ 1.15 sd of the difference
(se 4.92) — **consistent**. The A-versus-C binary-level difference on this host
is a real, repeatable phenomenon, and rung 2's half-width of **5.26 clears fb2's
< 8 µs/step precision bar** for this contrast.

**(b) The whole composed effect, and more, is the router leg — and that leg is
the one immune to the layout confound.** B→C = +34.58 is *larger* than the
composed A→C = +22.19, because A→B runs the other way. Since B and C are the
same binary at the same addresses selected by an environment variable, § 4.4b's
pre-committed rule lands on its favourable branch: **B→C large and A→B small
⇒ the router peel carries it and the conclusion is safe.** B→C is also the most
robust number in this whole document — positive in **21/21 repetitions** (sign
test p = 2⁻²⁰ ≈ 9.5 × 10⁻⁷), in 7/7 cycles, at all three slot-position pairs
(§ 5.3), and on all four statistics: median +34.58, trimmed +36.15, mean +35.96,
official-analog `mean_first128` +38.74 [+24.68, +52.80].

**(c) A→B is directionally faster but I am not claiming it.** Its CI barely
excludes zero (upper bound −0.14) and under the Bonferroni m = 3 adjustment
required for a joint three-leg claim (×1.2214 ⇒ hw 14.96) it **covers zero**:
[−27.35, +2.57]. § 5.4 then shows its layout contamination is maximal, and
fb4 § 3's two-wave argument says an M4 attention-kernel result cannot rank
mechanisms for the ranked host anyway. A→B is reported, not claimed.

Step-0 contrasts, which enter official `T` at weight 1/128, are all
insignificant and small in step-equivalent terms (A→B −5.55, A→C −2.26,
B→C +3.29 µs/step of `T`).

### 5.3 Position-matched cross-check (`research/maple-frieren-r103a-position-matched.py`)

Cycle-blocking removes the slot-position artefact by averaging. This script
removes it a second, more literal way, with an independently written parser:
it compares arms **only at the same slot-position pair**, using the one
repetition per cycle in which each arm occupies that pair. Three position-matched
estimates per leg, K = 7 each.

| Leg | at {3,4} | at {2,5} | at {1,6} | mean | spread | same sign? | primary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A→B | −8.32 | −12.19 | −16.91 | −12.47 | 8.59 | yes | −12.39 |
| A→C | +21.00 | +23.74 | +21.62 | +22.12 | 2.74 | yes | +22.19 |
| B→C | +29.32 (7/0) | +35.94 (7/0) | +38.53 (7/0) | +34.59 | 9.21 | yes | +34.58 |

The independent parser reproduces every primary point estimate to within
0.1 µs/step, and **no leg changes sign at any slot position**. B→C is positive in
7/7 cycles at each of the three pairs separately. The effects are not artefacts
of where in the block a slot ran.

### 5.4 Static layout check — the confound is real, maximal, and confined to the legs I am not claiming

Read-only comparison of the two workers (`/tmp/maple-r103a/layout/`), deliberately
run only after the timing job terminated. Segment map: `__TEXT` 22,953,984 →
23,019,520, `__text` 18,976,616 → **19,040,936 (+64,320 B)**, `__cstring`
1,560,409 → 1,568,025 (+7,616 B, consistent with the two edited MSL source
strings), no section added or removed.

`nm -n` address comparison over 142,976 common symbols:

| Symbol subset | n | identical address | same 16 KiB page offset | same cache-line offset |
| --- | --- | --- | --- | --- |
| all | 142,976 | 26.62 % | 33.65 % | 56.17 % |
| **`laguna` (scored runtime)** | 3,024 | **0.03 % (1 symbol)** | **4.53 %** | 11.77 % |
| **`mlxfastmodel`** | 2,182 | **0.00 % (none)** | 6.46 % | 11.92 % |
| `mlx_dispatch` | 4,964 | 67.95 % | 81.75 % | 95.23 % |
| `quantized` | 1,508 | 15.72 % | 21.88 % | 54.64 % |

The dominant address deltas are +64,320 (×26,981), +65,256, +65,536, +64,496,
+66,160 — i.e. roughly 64 KiB bulk shifts. 64,320 ≡ 0 (mod 64) but
≡ 15,168 (mod 16,384), which is exactly why cache-line offsets survive for most
symbols while **page offsets do not**; the other deltas are not multiples of 64
either. There are 154 symbols only in OLD and 295 only in NEW, and the private
mangling discriminator differs (`_6D73F25D…` vs `_31416BEF…`), confirming two
genuinely independent builds rather than one image plus a patch.

The conclusion is blunt and it goes against my own rung-1 headline: **the scored
Swift runtime is essentially 100 % relocated between arm A and arms B/C.** Not
one `MLXFastModel` symbol keeps its address and fewer than 5 % of `laguna`
symbols keep even their page offset. R2's arithmetic — 68 ns × 408 dispatches per
step = 27.7 µs/step — is therefore not a hypothetical; the displacement needed to
manufacture the entire A→C effect is present, and I have no way to bound its
contribution from static data alone. **Every A→B and A→C number in this document
is a statement about two binaries, not about the #565 source edit.**

The same check exonerates B→C completely: one binary, one image, one set of
addresses, one process-start environment read (§ 2.6.7: `lagunaRouterWeightPrefetch`
is a process-once `let`). There is no layout term in B→C to bound.

This is the outcome the pre-committed rule in § 4.4b was written for, and I want
to be explicit that the rule was fixed before these data existed: had A→B been
the large leg, this section would be saying the round produced an uninterpretable
result.

### 5.5 The preregistered N-2 trigger fired; here is the trigger and here is the multiplicity

**N-2 fires as literally specified.** One of the nine per-`(arm, separation)`
identical-code nulls excludes zero: `B@sep1 = +8.81 [+0.67, +16.95]`, sign 7/0.
Under the preregistered rule that downgrades **every** contrast to inconclusive,
and the precision check also **MISSES** (worst half-width 12.25 > 8.00, set by
A→B). I am not overriding the preregistration; the preregistered verdict is
recorded as such in § 6.

I owe the advisor the quantitative basis for reading it more softly, and equally
the reasons not to.

*Why the trigger is probably multiplicity.* The nine cells are three arms ×
three position pairs, and the three arms at a given pair are three estimates of
**one physical quantity** — the position-4-minus-position-3 term does not depend
on which arm measures it. Those three estimates are A +7.56, B +8.81, C −3.90;
B is not an outlier against A. Pooled across arms at fixed separation — the more
powerful summary § 4.5a(ii) added for exactly this purpose — **all three
separations cover zero**: sep 1 +4.15 [−2.58, +10.89], sep 3 +5.23
[−11.14, +21.60], sep 5 −12.18 [−29.29, +4.92]. With nine cells at α = 0.05 the
family-wise chance of at least one spurious exclusion is 1 − 0.95⁹ ≈ 37 %, and
the expected count is 0.45. Observing one is unremarkable.

*Why it does not touch the contrasts even if real.* These nulls are not an
instrument noise floor; each is a **deterministic slot-position contrast** (sep 1
is the interior pair {3,4}, sep 3 is {2,5}, sep 5 is the exterior pair {1,6}).
The cycle-blocked estimator removes that term by construction, and § 5.3
demonstrates empirically that it is removed: every leg keeps its sign and
magnitude at each position pair taken separately. A non-zero position term
inflated the per-repetition residual — which is precisely the defect § 4.5a(i)
was written to fix — rather than biasing any contrast.

*Why I still report the trigger.* The largest pooled null, sep 5 at
−12.18 ± 17.10, is comparable in magnitude to the A→B leg. So for **A→B**, N-2's
concern is live on its own terms and independently confirmed by § 5.4. For
**B→C** at +34.58, the widest null interval in the entire table reaches 78.13 in
one under-powered cell but the pooled bounds are ±29 at worst, and B→C's
robustness across four statistics, 21/21 repetitions, seven cycles and three
position pairs is not something a drift term reproduces.

Net: I treat the N-2 trigger as **disqualifying for A→B** and as **not
disqualifying for B→C**, and I flag that as my judgement layered on top of a
preregistered rule that says otherwise, so the advisor can discount it.

### 5.6 Decision relevance of the B→C leg, in fb3's units

Arm C is the **shipped default** (`DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1` at base
`0f6862d0`); arm B is `=0`, which § 2.6.7 and fb4 § 1 together identify as
selecting `_rpg8_keys_v1` — the *same* router kernel the pre-#558 revision A
uses. So B→C = +34.58 says, on this host: **the shipped router weight-prefetch
peel costs 34.58 µs/step, 0.418 % of the decode step, relative to not doing it,
at the current base.** My analyzer also records that there is **no official
same-base receipt for this leg** — #558 was promoted at an earlier base and the
pf0-versus-pf1 comparison has never been measured on the ranked host.

R1 withdrew scalar transfer as *evidence*, and I am not reinstating it. What
follows is a sensitivity, presented only to answer fb3's question "is this worth
anyone's attention", using fb3's own conversion Δcs % = ΔT / 65.7:

| Transfer assumption | ΔT on M5 | Δcs | P(accept) from fb3's table |
| --- | --- | --- | --- |
| fixed overhead (×1.000) | 34.58 | +0.53 % | ≈ 2.2 % |
| R1 decode-step ratio (×0.622) | 21.51 | +0.33 % | ≈ 0.8 % |
| proportional (×0.505) | 17.46 | +0.27 % | ≈ 0.6 % |
| bandwidth ratio (×0.436) | 15.08 | +0.23 % | ≈ 0.5 % |

Against the Δcs = 0 floor of 0.095 %, that is a **5× to 23× improvement in
acceptance odds**, and three of the four assumptions clear the +0.25 % row.
I want to state the defensible version precisely: **this is the first contrast
in this round whose M4 magnitude is large enough that no transfer factor in the
menu makes it decision-irrelevant.** That is a claim about magnitudes, not a
prediction of the M5 result, and § 6 says what would actually settle it.

Two caveats I have not resolved. First, fb4 § 3's wave argument was established
for the fused-attention kernels' 32 threadgroups; **I have not measured the
router kernel's threadgroup geometry**, so I cannot rule out that B→C is also
occupancy-structured and therefore host-specific. tanjiro's
`research/r103b/scripts/compare_dispatch.py` could establish this without any
timing. Second, the direction is a *regression of a promoted change*, which is
the pattern one expects from stale-frontier interaction rather than from a
mistake in #558 — the peel may well have won at its own base.

## § 6 Verdicts on N-1 … N-5

### 6.0 The preregistered verdict first, before my reading of it

§ 1.11's decision rule is ordered, and taken literally it terminates before it
reaches any localisation claim. I am recording that outcome in full before I
argue with it, because the whole point of preregistering was to stop me
selecting a favourable branch after seeing the numbers.

**Literal preregistered outcome.** Rule 4 fires: a per-cell null CI
(`B@sep1 = +8.81 [+0.67, +16.95]`, 7/7 signs) excludes zero at a magnitude
comparable to the A→B contrast (−12.39). Rule 4 is **OUTCOME 5 / N-2**:
drift contaminates, and no contrast from this block is trustworthy. The
precision gate independently reads **MISS** (worst half-width 12.25 > 8.00,
set by A→B), which under § 1.11's rung-1 wording is **OUTCOME 4,
inconclusive-underpowered**. Either route ends at "not trustworthy" or "not
precise enough", and **neither route licenses a localisation**. So the honest
one-line preregistered answer to the assignment's question — *which kernel
holds the missing ~19 µs/step* — is **it is not localised to a kernel by this
round**.

**N-5 does not fire.** The § 1.11 rule-5 trigger is "all three contrasts
contain 0". B→C = +34.58 [+26.39, +42.77] does not contain 0 and neither does
A→C = +22.19 [+16.94, +27.45], so the analyzer prints `n5_fires: no: at least
one contrast excludes zero`. fb3 called N-5 "the expected and most welcome
outcome"; I have to report that it is not what happened, and § 6.5 says what I
think the welcome-outcome-shaped part of this actually is.

### 6.1 N-1 — receipt noise. Verdict: **fires, and fb2 was right**

fb2 retracted +20.149 as a target on the basis of an identical-code replicate
(sd(T) = 14.272, trimmed pooled 12.079 on 14 dof ⇒ two-receipt σ 17.1–20.2,
z = 1.00–1.18). Nothing in rungs 1–2 rehabilitates it. My rung-2 A→B leg —
the contrast that corresponds to the #565 edit that the +20.149 receipt pair
straddles — comes out **−12.39 µs/step (faster)**, i.e. the *opposite sign*
from the M5 receipt delta, with a Bonferroni-corrected interval
[−27.35, +2.57] that covers zero. The frontier reviewer's arithmetic on fb2's
own numbers (z ≈ 1.1, p ≈ 0.14) is the correct summary: **the ~20 µs/step
"missing microseconds" is not established to exist.** I am not claiming I
disproved it either — see § 6.2 — I am claiming the target was never a
measurement.

This is the single most consequential verdict in the round and it retires the
assignment's premise rather than answering its question.

### 6.2 N-2 — thermal / session drift. Verdict: **fires; disqualifying for A→B, and I argue not for B→C**

The trigger and the multiplicity accounting are in § 5.5. The short version:

* One of **nine** per-`(arm, separation)` nulls excludes zero. Family-wise
  P(≥1 of 9) ≈ 37 % under a true global null, so a single exclusion is close
  to the modal outcome and is weak evidence of real drift.
* Every **pooled-at-fixed-separation** null covers zero: sep 1 +4.15
  [−2.58, +10.89], sep 3 +5.23 [−11.14, +21.60], sep 5 −12.18 [−29.29, +4.92].
  The pooled statistics are the ones with the sample size to see drift, and
  they are quiet.
* But the sep-5 pooled null's half-width (17.10) is **larger than the entire
  A→B leg** (12.39). Whatever drift exists is not measurably smaller than the
  A→B effect, so A→B is unrecoverable from this block regardless of how I read
  the trigger.
* B→C (+34.58, half-width 8.19, 7/7 cycles, 21/21 reps, p = 2⁻²⁰) is 2.0× the
  worst pooled-null half-width and 3.9× the largest per-cell null point
  estimate. § 5.3's position-matched cross-check reproduces it with the same
  sign at all three position pairs (+29.32, +35.94, +38.53, each 7/0) using an
  independent parser, which is exactly the structure drift cannot manufacture:
  drift is a function of position, and this contrast is estimated *within*
  position.

**Verdict I am acting on:** N-2 disqualifies A→B and does not disqualify B→C.
**Verdict the preregistration says:** N-2 disqualifies everything.
I am flagging the gap rather than hiding it, and I would rather the advisor
discount my judgement than not see that I exercised it.

### 6.3 N-3 — diffuse rather than one kernel. Verdict: **cannot be evaluated as written; superseded**

N-3's thresholds were defined against the corrected M5 target of 20.15 µs/step
(single kernel counts as localised above 5.04; residual above 10.1 means
diffuse). Three separate things broke the question:

1. **The target is retired** (§ 6.1), so the denominator of both thresholds no
   longer exists.
2. **N-3 presumed a `--profile` reconciliation of per-kernel time against the
   e2e delta.** I never reached that step: the round's budget went into
   getting a three-arm contrast that could survive its own nulls, and by the
   time A→B was disqualified there was nothing left to reconcile *to*. This is
   a work item I did not do, not a finding.
3. fb4 § 1 already answered the structural half of N-3 better than a profile
   could, and without timing: **101 of 103 JIT Metal libraries are
   byte-identical OLD vs NEW**, OLD→MID is a single MSL edit at line 1280, and
   there are **408 dispatches per decode step at every revision** with zero
   non-equal opcodes across 11,247 rows. So the OLD→NEW delta is *already*
   localised at the source level to two kernels. What is not established is
   that either of them costs anything.

The one thing I can say that N-3 was reaching for: **the composed A→C effect
does not distribute across the two mechanisms.** A→C = +22.19 and B→C = +34.58
with A→B = −12.39, so the router leg carries more than the whole composed
effect and the attention leg partially cancels it. If there is a real cost in
this OLD→NEW range on *this* host, it is in the router prefetch peel, not in
the K/V pipeline depth.

### 6.4 N-4 — the vendored comment carve. Verdict: **does not fire; excluded by two independent routes**

§ 2's static pre-read established the carve (`f720e9e7`, 176,468 B) touches
only `.swift` comment text and cannot change AOT codegen. #575 then closed it
empirically: a comment-only LRM strip produced a **byte-identical
`MLXFastModel.o`** across four forced-clean builds. fb4 § 1's finding that
101/103 JIT libraries are byte-identical OLD vs NEW is a third, independent
confirmation from the Metal side. N-4 is closed.

### 6.5 N-5 — all arms mutually indistinguishable. Verdict: **does not fire, but fb3's underlying prediction was half-right**

The trigger is not met (§ 6.0). I want to be careful about what that means,
because "N-5 did not fire" reads like "I found something", and only one of the
two legs supports that reading.

* On the leg fb3 was talking about — the ±20 µs/step A↔B contrast fb3 called
  "decision-irrelevant" — **fb3's prediction held**. A→B is −12.39 with a
  corrected interval covering zero, and it is additionally disqualified by
  N-2 and structurally uninformative on M4 by fb4 § 3's two-wave argument.
  Even the point estimate maps to |Δcs| ≈ 0.19 %, below the 0.25 % row of
  fb3's table. That leg is exactly the N-5-shaped result fb3 expected.
* On the leg nobody had preregistered — **B↔C, which fb2 promoted to co-equal
  and fb4 § 2 pointed out needs no rebuild** — the arms are *not*
  indistinguishable, and § 5.6 shows the magnitude survives every transfer
  factor in the menu.

So the accurate summary is: **the round found N-5 on the assigned contrast and
a candidate signal on the contrast that was added later.**

### 6.6 What I am and am not claiming, in one place

**Claiming, at scope "these two binaries, this M4 host, this session":**

* `DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1` (the shipped default at base
  `0f6862d0`) is **+34.58 µs/step slower** than `=0`, 0.418 % of the decode
  step, half-width 8.19, 7/7 cycles, 21/21 reps, reproduced at all three
  position pairs by an independent parser.
* The composed A→C effect (+22.19, half-width 5.26) **replicates rung 1**
  (+27.84 ± 9.15; difference −5.65 ≈ 1.15 sd) and is **entirely accounted for
  by the router leg**.
* Nothing in this round localises a cost to the #565 K/V pipeline-depth edit,
  and the sign of the A→B point estimate is opposite to the M5 receipt delta.

**Not claiming:**

* Not claiming the ~20 µs/step exists. Not claiming it does not — N-1 says the
  target was a difference of two single receipts and my A→B leg is disqualified
  by N-2, so **both directions are unsupported**.
* Not claiming A→B or A→C is a statement about the #565 *source edit*. § 5.4
  proves ~100 % relocation of the scored Swift symbols between the two
  binaries (`laguna` subset: 0.03 % identical addresses, 4.53 % same page
  offset; `mlxfastmodel`: 0.00 % / 6.46 %; `__text` +64,320 B), so those two
  legs are statements about two *binaries*. The frontier reviewer's
  displacement arithmetic — 68 ns × 408 dispatches = 27.7 µs — is the same
  order as the composed effect, and I did not build the size-matched placebo
  that would bound it.
* Not claiming B→C transfers to the ranked host. It is immune to the layout
  confound (same binary, one env var, § 5.4's confound cannot apply), which is
  a different and much stronger property than transferring.
* Not writing "neutral", "null", or "unchanged" anywhere without an attached
  X. The three X's for this round are: A→B not distinguishable from 0 at
  ±14.96 (Bonferroni), pooled drift nulls not distinguishable from 0 at
  ±6.74 / ±16.37 / ±17.10, and no pair differing by more than 15.0 µs/step M4
  jointly.
* Not claiming a sum-masked exoneration. A→B ≈ 0 does **not** exonerate the
  #565 edit: it is one aggregate over a two-wave-structured kernel on the
  wrong core count.

### 6.7 Follow-ups I did not implement, in priority order

**(a) Paired pf0-vs-pf1 probe on the ranked M5 host. Highest value by a wide
margin.** This is the one experiment that would convert § 5.6 from a
sensitivity into a decision. It needs **no rebuild** (fb4 § 2), **zero
submitted bytes** for the probe itself, and it is a single env-var toggle
across two runs of the same binary, so it is immune to § 5.4's layout
confound by construction. fb4 § 2's interleaved paired ABBA is the right
design (archive within-process σ ≈ 19.5 vs ≈ 48 cross-process). If pf0 wins
there, the receipt-generating change is a **one-line default flip** at
`Sources/MLXFastModel/LagunaRuntimeModel.swift:686-704` — the default in the
`ProcessInfo` read — which is a few submitted bytes against 140,043 B of LRM
per-file headroom. I did not do this because I have no M5 host and zero
receipts in scope.

**(b) Router-kernel threadgroup geometry, via tanjiro's
`research/r103b/scripts/compare_dispatch.py`.** § 5.6's first unresolved
caveat. fb4 § 3's two-wave argument was established for the fused-attention
kernels' 32 threadgroups; if the router kernel also dispatches ≤ 32
threadgroups then B→C is occupancy-structured and my M4 magnitude does not
rank it for a ≥32-core host either. **This costs no timing and no GPU
allocation** and should gate (a) rather than follow it.

**(c) Size-matched placebo build of revision A**, padding `__text` by
+64,320 B with dead code, to bound the layout-displacement term in A→B and
A→C. This is the Curtsinger & Berger *Stabilizer* remedy adapted to a single
draw. It would tell us how much of the composed A→C is displacement rather
than mechanism. Lower priority than (a)/(b) because A→B is already
disqualified by N-2 and structurally uninformative on M4, so the term it
bounds only matters if someone wants to resurrect the A legs.

**(d) A depth sweep on M5 to resolve fb4 § 4's sign contradiction.**
`RESEARCH_ARCHIVE_through-round-91.md:4894-4896` (PR #103) has K/V pipeline
depth 4 at **−1.039 % (faster) on M4** and depth 8 at +0.485 %, noise ±0.73 %;
the M5 receipts put depth 4 at +20.15 (+0.30 %) **worse**; and **no depth has
ever been measured on M5**. My A→B leg is a third M4 draw at −12.39 (−0.15 %),
which sits between the two archive M4 numbers and is consistent with the
archive's noise band. So the M4 evidence is now 2-of-2 "depth 4 is not slower"
and the M5 evidence is one unreplicated receipt pair. Somebody with M5 access
should measure depth directly.

**(e) `pf5` as a placement control.** `LagunaRuntimeModel.swift:1127` builds a
`_pf1c` variant and § 2.6.7 records `5` as a documented **PLACEMENT CONTROL**;
all 21 router variants are built eagerly at `:1120-1145`, so this is a third
arm at zero build cost. If pf5 lands with pf0 rather than pf1, the +34.58 is
about *where* the prefetch is placed relative to the active-simdgroup guard
(fb4 § 1's MID→NEW mechanism) rather than about prefetching at all. That is a
mechanism question and it would sharpen (a)'s interpretation, but it does not
gate it.

### 6.8 Cost of the round, for the advisor's budgeting

Three supervised jobs plus two short gates: rung 0 165 s, G2.1 170 s, rung 1
≈ 4,600 s (104 slots), rung 2 6,232 s (144 slots). Slot cost ≈ 44.2 s of
which ≈ 42.5 s is model load, so **96 % of wall-clock was process startup**
and the fixture caps a slot at ~250 steps. Any future round on this instrument
should use fb4 § 2's within-process interleaving instead: the archive's within-
process σ ≈ 19.5 against ≈ 48 cross-process means the same precision is
reachable at a small fraction of the wall-clock. My cross-process design was
chosen because A and B are different binaries; **B↔C does not have that
constraint and should never have been run cross-process.** That is the main
methodological thing I would do differently.

## § Reply

_Headline (R0) is written last, after § 5. R1 – R7 below are the parts of the
reply that do not depend on any rung-2 number, and were written while job
`e5822dad` was still executing._

### R0 Headline

**The assigned effect does not reproduce, and the round's one real finding is on
the leg fb2 added: the shipped router weight-prefetch default is slower than
turning it off, on this host, at this base.**

Three arms, 144 slots, rotated blocks, every gate green (single token hash
`aaf1cccc…` across all 144 slots, 144/144 `0 divergences`, tree digest
unchanged before and after, QC 0 rejected):

| leg | mechanism | Δ µs/step (median, cycle-blocked, K=7) | 95 % CI | cycle signs |
| --- | --- | --- | --- | --- |
| **A→B** | #565 K/V pipeline 2-way → 4-way | **−12.39** (faster) | [−24.64, −0.14]; Bonferroni [−27.35, **+2.57**] | 0/7 |
| **B→C** | #558 router weight-prefetch peel (pf0→pf1) | **+34.58** (slower) | [+26.39, +42.77], hw 8.19 | 7/7, reps 21/21 |
| **A→C** | both, composed | **+22.19** | [+16.94, +27.45], hw **5.26** | 7/0 |

**1. N-1 fires; the ~20 µs/step target is retired.** fb2 was right to retract
it, and my A→B leg is not just insignificant but **opposite in sign** to the M5
receipt delta. Combined with fb4 § 4's archive finding that depth 4 measured
**−1.039 % (faster) on M4** in PR #103, the M4 evidence is now 2-of-2 "depth 4
is not slower" against one unreplicated M5 receipt pair. I am not claiming I
disproved the M5 delta — I am claiming it was never a measurement.

**2. I accept fb3's ruling on the A legs, and § 5.4 gives a second, independent
reason to.** A ±20 µs/step A↔B contrast is decision-irrelevant, and fb4 § 3's
32-threadgroup two-wave argument makes an M4 A↔B result structurally unable to
rank mechanisms for a ≥32-core host. On top of that, my static layout check
found the two binaries share **0.03 % identical addresses** in the `laguna`
symbol subset and **0.00 %** in `mlxfastmodel` (`__text` +64,320 B). The
frontier reviewer's displacement arithmetic, 68 ns × 408 dispatches = **27.7 µs**,
is the same order as the whole composed effect. **A→B and A→C are statements
about two binaries, not about the #565 source edit.** I did not build the
size-matched placebo that would bound this.

**3. B→C is the leg that escapes all of that, and it is the one that moved.**
Same binary, one env var, so § 5.4's confound cannot apply and no rebuild was
needed (fb4 § 2). +34.58 µs/step = **0.418 % of the M4 decode step**, half-width
8.19, 7/7 cycles, 21/21 reps (p = 2⁻²⁰), and § 5.3's independent parser
reproduces it at all three position pairs (+29.32 / +35.94 / +38.53, each 7/0)
— a within-position structure that drift cannot manufacture. In fb3's units,
**every** transfer factor in the menu lands at or above the +0.25 % row
(+0.53 % / +0.33 % / +0.27 % / +0.23 %), i.e. 5×–23× the Δcs = 0 acceptance
floor. The defensible claim is narrow: **this is the first contrast this round
whose M4 magnitude is large enough that no transfer factor makes it
decision-irrelevant.** There is **no official same-base M5 receipt** for
pf0-vs-pf1; #558 was promoted at an earlier base.

**4. N-2 fired and I am flagging that I overrode it for one leg.** One of nine
per-cell drift nulls excludes zero (`B@sep1 = +8.81 [+0.67, +16.95]`);
family-wise that is ≈ 37 % under a true global null, and all three
pooled-at-fixed-separation nulls cover zero. Taken literally, § 1.11's rule 4
disqualifies **every** contrast in the block, and the precision gate
independently reads MISS (worst hw 12.25 > 8.00, set by A→B). I judge N-2
disqualifying for A→B and not for B→C, and I have recorded both the
preregistered verdict and my override in § 6.0 and § 6.2 so it can be
discounted. **N-5 does not fire** — B→C and A→C both exclude zero — but fb3's
prediction held on the leg fb3 was actually talking about.

**5. The single highest-value follow-up costs no rebuild and no submitted
bytes: a paired pf0-vs-pf1 probe on the ranked M5 host** (§ 6.7a), gated by a
zero-timing check of the router kernel's threadgroup geometry using tanjiro's
`compare_dispatch.py` (§ 6.7b) in case B→C is occupancy-structured too. If pf0
wins on M5, the receipt-generating change is a one-line default flip at
`LagunaRuntimeModel.swift:686-704`. I did not do this: no M5 host, zero
receipts in scope.

Contract kept: **zero submitted bytes** (everything under `research/`), **zero
receipts**, no rebase or merge of the advisor branch, arms pinned at
`30f752df` / `e17bdeb1` / `0f6862d0` as instructed by fb3.

### R1 I withdraw two claims I made about rung 1

fb2 retracted +20.149 as a target. I then went further than the evidence
allowed in the other direction, and an adversarial re-read of my own § 4.3
caught it. Both withdrawals are recorded in § 4.4; restating them here so they
are in the reply and not only in the body.

**Withdrawn (i): "two hosts agreeing is strong combined evidence."** This is a
selection error, not a combination of evidence. I ran the M4 experiment
*because* the M5 delta looked interesting and had the sign it had. Conditioned
on that selection, "M4 agrees in sign" is close to a coin flip under the
hypothesis that the M5 receipt is noise, so sign agreement carries almost no
information about whether the M5 receipt was noise. The M5 side remains a single
z ≈ 1.0–1.2 datum, one-sided p ≈ 0.14; it can contribute at most a factor of
about two to any honest combination, not the "much smaller than either alone"
I wrote. **fb2's retraction stands, and nothing in rung 1 or rung 2 rehabilitates
+20.149 as a target.**

**Withdrawn (ii): "the transfer models bracket 20.149."** Circular. I picked
×1.000 and ×0.622 from a four-entry menu that also contains ×0.436, which would
have missed, and I bracketed with point estimates while suppressing my own
±9 µs/step. Propagating the interval gives roughly [8, 37] µs/step on M5, which
brackets essentially any hypothesis in play and therefore discriminates nothing.
Worse, fb4 § 3 shows the two hosts may not even run the same kernel family, so a
scalar transfer factor may be a category error rather than merely imprecise.

What survives is narrower and I will state only this: **the 24/24 sign split is
a sound statement that these two binaries differ on this M4 in this session.**
It is not yet a statement that the two source changes regress performance — see
R2.

### R2 The alternative explanation I cannot yet exclude: binary layout

The two arms are separately-built 49,190,344 B and 49,094,856 B workers. They
differ by 95,488 bytes of machine code, which displaces symbol addresses, page
boundaries and cache-line alignment throughout the image. The measurement
literature on this is unambiguous that such displacement alone can produce
effects of the size I measured — Mytkowicz et al., *Producing Wrong Data Without
Doing Anything Obviously Wrong!* (ASPLOS 2009), and Curtsinger & Berger's
Stabilizer (ASPLOS 2013), both report layout-induced swings that exceed the
speedups the papers under study were claiming.

The arithmetic is uncomfortable: fb4 established **408 dispatches per decode
step at every revision**. 68 ns of extra per-dispatch cost — well under one page
fault, comfortably within an alignment-driven i-cache or branch-predictor
change — reproduces my entire A→C effect without any semantic difference
existing at all.

This is why rung 2 is not just a finer version of rung 1, and it produces an
asymmetry the advisor should hold me to:

| Leg | Binaries | Exposed to layout confound? |
| --- | --- | --- |
| A→B | `old` vs `new` | **Yes, fully** |
| A→C | `old` vs `new` | **Yes, fully** |
| B→C | `new` vs `new`, env flag only | **No — same bytes, same image, same addresses** |

So **B→C is the clean leg** and A→B is the contaminated one, which is the
opposite of the ordering my original assignment assumed. The pre-committed
reading (§ 4.4b, fixed before rung-2 data existed): if B→C is large and A→B
small, the router peel carries the effect and the conclusion is safe; if A→B is
large and B→C small, the result is **ambiguous between #565 and layout
displacement** and I will say exactly that rather than attribute it to #565.

§ 5.4 reports a static Mach-O section-map and `nm -n` symbol-address comparison
between the two workers, which is free and bounds how much displacement actually
occurred. A size-matched placebo build of revision A would settle it properly
and is listed in § 6 as a follow-up, not run.

### R3 On fb3's decision-relevance reframing — I accept it, and it changes the ask

fb3's acceptance table is the most useful thing I was sent, because it makes the
round's target legible in a way the µs/step framing did not: **P(accept) rises
from 0.095 % at Δcs = 0 to 0.520 % at +0.25 % and 2.179 % at +0.50 %**, so
effort only pays at **≳ +0.5 % cs ≈ ≳ 33 µs/step on T**, and "a ±20 µs/step
contrast is decision-irrelevant."

I accept this without reservation, and I have not tried to argue my way around
it by pointing out that my M4 point estimate happens to exceed 33 µs/step in
M4-equivalent units. That would be exactly the reasoning error fb3 was warning
against: the bar is on M5, on the ranked score, and R1 explains why I no longer
believe I can transfer an M4 number onto M5 at all.

Concretely this changed what I did, not just what I wrote. I stopped at the
preregistered K = 21 rather than extending, I did not pursue the sub-8 µs/step
half-width, and I dropped the `pf5` placement control (§ 4.5) even though it is
genuinely informative, because it would have cost ≈ 141 min to sub-divide a leg
that is already below the decision bar. **N-5 — "this contrast cannot be
resolved on M4 at a cost proportional to its decision value" — was the outcome I
expected going in**, and § 6 states which of N-1…N-5 actually fired.

### R4 On fb4 § 3, the two-wave argument — accepted, and it is the load-bearing caveat

tanjiro's finding that both fused-attention kernels dispatch exactly **32
threadgroups** is, I think, the single most important structural fact anyone has
produced about this round. A 20-core M4 runs that as **two waves**; a ≥ 32-core
ranked host runs it as **one**. A software-pipeline depth change interacts with
occupancy and latency hiding precisely through wave structure, so the M4 is not
a scale model of the ranked host for this edit — it is a qualitatively different
regime. tanjiro cancelled his own M4 A/B at six legs on this basis.

I did not cancel, for one reason: my assignment's A→C contrast composes the
pipeline edit with the router peel, and the **router peel leg is not subject to
the wave argument** (same binary, same kernel, an env-selected variant), so
rung 2 still buys a clean B↔C answer that transfers better than the A↔B leg
does. But I am treating the A↔B leg as **structurally uninformative for ranking
mechanisms on the ranked host**, and § 5 and § 6 carry that caveat attached to
every A↔B number rather than in a footnote.

### R5 On fb4 § 4, the sign contradiction — I did not resolve it and I do not think I can

The archive (`RESEARCH_ARCHIVE_through-round-91.md:4894-4896`, PR #103) has
pipeline depth 4 at **−1.039 % (faster) on M4** with noise ±0.73 %, and depth 8
at +0.485 %. The M5 receipts put depth 4 at +20.15 µs/step (+0.30 %), i.e.
**worse**. And, decisively, **no depth has ever been measured on M5** — the M5
side of that contradiction is two archived receipts at different revisions, not
a depth sweep.

So the contradiction is between an M4 measurement and an M5 revision-pair
difference, which R1 and R4 together say is not a like-for-like comparison in
the first place. Rung 2's A→B leg is a third M4 measurement of (in effect) the
same edit, and § 5 reports where it lands relative to the archive's −1.039 %,
but I want to be explicit that **a third M4 number cannot adjudicate an M4-vs-M5
disagreement**, and that the honest resolution is a depth sweep on M5, which is
a receipt-spending experiment I was not authorised to run and which § 6 lists as
the highest-value follow-up.

### R6 What I would spend the next receipts on

Not on M4. The decisive cheap experiment for the original question is **a paired
A/C receipt pair on M5 itself**, which is the only instrument that can turn a
z ≈ 1.1 single-receipt delta into a real measurement, and which fb2's own
replicate study already calibrated (σ of a two-receipt difference ≈ 17–20
µs/step, so distinguishing 20 from 0 needs several pairs, not one). Whether
that is worth its receipt cost is fb3's call and fb3's table already suggests
the answer is no. I am recording it as the right experiment, not requesting it.

### R7 Protocol compliance

- **No rebase, no merge** (fb3, fb4 § 6). Arms stay pinned to `30f752df` /
  `e17bdeb1` / `0f6862d0`; my base is still `0f6862d0` although the advisor
  branch has since moved to `449d6744`. Nothing in this branch's history
  touches the advisor branch.
- **Zero submitted bytes.** Every file I added is under `research/`.
- **Zero receipts consumed.**
- **Blinding log** is in § 4.1 and § 1.14.7 and lists every interim number I saw
  before the corresponding rule was frozen, including the ones that make me look
  worse.
- I have not written "neutral", "null", or "unchanged" anywhere without an
  attached exclusion bound X (fb2).

### R8 Where the evidence lives

**W&B run** (single run, both rungs, all gate outcomes, all artifacts):

- `r103a-three-arm-m4`, id `happqffd`
- <https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/happqffd>

Logged summary keys mirror this document rather than paraphrasing it: rung-2
contrast point estimates, half-widths, sign counts and Bonferroni-widened
intervals under `rung2/`; rung-1 under `rung1/`; the retraction flag
`m5_target_retracted=True`; fb3's conversion constants
(`cs_pct_per_us = 1/65.7`, `cs_effort_threshold_us = 32.8`) so the
decision-relevance arithmetic of § 5.6 can be recomputed without reading prose;
`n2_fires=True`, `n5_fires=False`, `precision=MISS`.

Uploaded artifacts, sufficient to re-derive every number here without the box:

| artifact | what it pins |
|---|---|
| rung-2 `analysis-multi.json` | all five statistics × contrasts/levels/nulls |
| rung-2 `provenance.txt` | tree digests before/after, binary hashes per arm |
| rung-2 `index.tsv` | the realised 144-slot `rep position arm tag` layout |
| rung-2 `tokens.cksum` | the single token-stream hash shared by all 144 slots |
| `position-matched.txt` | independent-parser cross-check (§ 5.3) |
| `layout.json` | the `nm -n` symbol displacement census (§ 5.4) |

**Exact reproduction.** Rung 2, the primary block, is one command against the
snapshot tree built by rung 0:

```bash
SNAP=/tmp/maple-r103a-snap OUT=/tmp/maple-r103a/rung2 \
DESIGN=rotate REPS=24 STEPS=250 WARMUP_REPS=3 \
ARMS="A:old B:new:DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0 C:new:DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1" \
ASSERT_DIFFER="old:new" ASSERT_SAME="" \
  bash research/maple-frieren-r103a-abba.sh
python3 research/maple-frieren-r103a-analyze-multi.py /tmp/maple-r103a/rung2 3
python3 research/maple-frieren-r103a-position-matched.py /tmp/maple-r103a/rung2 3
python3 research/maple-frieren-r103a-wandb.py   # needs WANDB_API_KEY
```

Cost, for whoever repeats it: 144 slots × ≈ 43 s ≈ 6,232 s wall on this host,
of which ≈ 42.5 s per slot is model load. Nothing in the chain takes the
benchmark lock, consumes a receipt, or touches a submitted path.
