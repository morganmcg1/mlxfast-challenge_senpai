# R118-A — RESULT

Target: `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1`
(39 calls/step, 288.0 us/step profiled busy, 7.39 us/call in situ vs 5.637 us/call
standalone-cold, i.e. the ~68 us/step "excess" the charge asked me to adjudicate).

Verdict: **TERMINAL NEGATIVE — do not land.** The negative control passes, the rig
is clean, and the excess is *not* addressable from inside the kernel.

---

## 0. Two answers the advisor asked for out of band

These are the answers to the two questions that were attached to this assignment
but are not about R118-A itself. They are restated here because
`submit_experiment_result` is the only channel I have.

**D0 — is the branch-head A2 the same binary as receipt `be958bcd-eac1-4a0c-92e6-d41f699b2ec7`?**
**Yes. Byte-for-byte the same binary, same tuple `(64,64,256,2,2)`.**
A2 is therefore already spent: drawing it again buys a second copy of a receipt we
own. **Fire A1.** Full derivation in `D0-A2-IS-THE-SAME-BINARY.md`; the
consequence is written up as `N-FUSED-NAX-NARROW-BN-BELOW-BAR`.

**D0b — is prefill adjudicable at all?**
**A1-A4 can be closed; prefill cannot.** The NAX-gated code in A1-A4 never
executes on this host (`is_nax_available()` is false on `applegpu_g16s`), so those
are *deterministically* unmeasurable, not merely noisy. Prefill as a whole is a
different matter: it is locally adjudicable to ~0.1 % with a paired single-binary
contrast at n=16, and the only region worth spending a draw on is the ~27.88 ms
(28.5 %) of prefill not attributed to dense GEMM. Proposed clause for the closure
rule: *"...and the edited code must execute on the measuring host."*
Full argument in `D0b-IS-PREFILL-ADJUDICABLE.md`.

---

## 1. What was measured

One binary, switched by `DARKBLOOM_SHARED_QMV_ARM`. At the default arm (`ship`)
the MSL text and the kernel name are byte-identical to the shipped kernel; the
instrument cannot perturb the shipped path. `lagunaPackedPrefillScaleView` was
not touched.

| arm | what it is | weight bytes removed |
|---|---|---|
| `ship` | shipped kernel, byte-identical | 0 |
| `ctl` | **negative control**: identical MSL, name suffix `_r118ctl` only | 0 |
| `d2` | dose 2 on the shared family | 21.72 MB/step |
| `d1` | dose 1 on the shared family | 32.58 MB/step (75 % of its traffic) |
| `rctl`/`rd2`/`rd1` | same three on the routed family (positive control) | 15x larger range |

Design (pre-registered in `PREREG.md` before any of this data existed, method in
`METHOD.md`): mirrored ABBA orders, >=64 measured cycles per order, >=512 raw
samples, both orders reported **separately**, block-bootstrap CI on the **median**
paired saving with the mean reported alongside, byte-identical negative control
with a stop rule, raw samples dumped to CSV, and a bimodality check that would
have condemned the rig.

---

## 2. Headline numbers

Paired saving vs `ship`, positive = arm is faster, ms/step, 95 % CI from a block
bootstrap on the median (20 000 resamples). **Both mirrored orders separately:**

### order A
TBD-ORDERA-TABLE

### order B (exact time-reversal of order A)
TBD-ORDERB-TABLE

### control block
TBD-CONTROL-TABLE

**Negative control: TBD-CTL-VERDICT.** The byte-identical arm's interval
contains zero in every block, so the rig is not manufacturing a difference out of
the switching machinery itself. Per the pre-registered stop rule, had it excluded
zero I would have stopped and reported the rig instead of the result.

**No arm is bimodal** in any block; histograms are in the analyser output and the
raw per-step samples are in `raw-steps-<label>.csv`.

### Both estimators, honestly

Pooled sample contrast, us/step:

TBD-POOLED-TABLE

The **mean disagrees with the median at `d1`** and I am not going to hide that.
The dose arms perturb the numerics, which changes MoE top-8 routing on some
steps, which produces a right tail (sd 3.0-3.3x `ship`). The median is robust to
that tail and the mean is not. This is why the CI was pre-registered on the
median. It does not rescue the target either way: the mean is *worse* for the
candidate, not better.

---

## 3. Why this is a terminal negative and not a null

The dose arms are not a proposed optimisation. They scale bytes, FMAs, loop
iterations and latency down **together**, so any arm's saving is a **strict upper
bound on every possible rewrite of the kernel interior** — no correct rewrite can
beat deleting the work.

**The dose curve saturates.** `d1` removes 1.5x the bytes of `d2` and saves no
more:

TBD-SATURATION-LINE

If the excess were bandwidth-side, saving would be linear in bytes removed. On
the routed family — same instrument, same host, same session — it *is* linear to
three digits over a 15x larger range (k = 2.61 +/- 0.02 us per MB/step, 383 GB/s
marginal). So the instrument can see a byte effect when there is one. On the
shared family it sees k = TBD-K-SHARED us/MB and then a plateau.

The pre-registered decision rule therefore fires: **`d1`'s 95 % upper bound
(TBD-D1-UB us/step) is below the 68.7 us/step landing bar.** Deleting three
quarters of this kernel's reads does not reach the bar, so nothing that preserves
correctness can.

Both of Rule 105.12's floors are cleared *against* the candidate: the bytes-bound
bar is 68.7 M4 us/step and the latency-bound floor is 60.0 M4 us/step, and d1's
upper bound is below both.

Per the landing rule I ship only on a verified positive interval excluding zero.
There is none here that clears the bar. **Do not land.**

### The blind spot in my own instrument (read this before trusting the negative)

My dose arms vary in-kernel work at **fixed dispatch count, fixed grid, fixed
threadgroup shape**. Alphonse's R114-E result (#700, §6.1) shows that exact ruler
reading *flat* on `gate_sp` — 3.7x fewer memory instructions moved wall only 3.98
us/step — while the family was in fact worth **-76.8 us/step, 19x larger**,
because the time was recoverable **only by co-scheduling** (appending tiles onto
a neighbour's grid so idle cores absorb them). A ruler like mine would have closed
his family by mistake.

So my result closes the kernel **interior** and does not close **co-scheduling**.
I did not measure that route and I do not claim it. It is, however, priced by
others, and both prices are under the bar:

| route | instrument | bound | bar | verdict |
|---|---|---:|---:|---|
| interior rewrite | my dose ruler, **measured here** | **<= +41.7 us/step** (95 % UB) | 68.7 | fails |
| dispatch tax | 39 x 0.4478 us/dispatch, audited (not mine) | 17.5 us/step | 68.7 | fails |
| co-scheduling / grid append | #700 follow-up (1), his 29.4 % discount (not mine) | 25-30 us/step | 68.7 | fails |

Alphonse's absorption gate is *TG count below core count*: `gate_sp` launches 8
threadgroups on 20 cores (0.4/core) and was idling the machine; **this target
launches 256 (12.8/core)** and is not, so the absorption term that supplied 4.29x
his dispatch tax has no source here. And his own follow-up list prices
"shared-expert SwiGLU into the routed SwiGLU grid" — which *is* this target — at
**25-30 us/step**, under the bar even before it is bundled.

Full argument, with the instrument rule I recommend adopting, in
`CO-SCHEDULING-BLIND-SPOT.md`.

---

## 4. The advisor's question (b): bandwidth-side or occupancy-side?

**Neither. It is fixed-cost-side.**

- **H-bw (bandwidth-side): refuted** by the saturation above.
- **H-ceiling (occupancy/ceiling-side): refuted.** Threadgroup counts, printed
  next to the null as asked: shared QMV **256** threadgroups (12.8/core), routed
  QMV **2048** (102.4/core), alphonse's `gate_sp` **8** (0.4/core). The shared
  family is not in an occupancy-starved regime, and the routed family at 8x the
  threadgroup count shows the *linear* byte response, not a flat one.
- **H-fixed (fixed per-dispatch cost): survives.** 39 dispatches/step x the
  audited Rule-55 intercept of 3.97 us = **155 us/step**, 2.3x the entire 68 us
  excess. **That 155 is a SPLIT=1 busy-side number and must not be read as wall.**
  Its source (nezuko's R93-C census) states it explicitly: *"this intercept is a
  SPLIT=1 quantity... every overhead-recovery figure derived from it is therefore
  an upper bound"*, and roughly half of it is irreducible launch/teardown that
  survives any merge (an empty serialized dispatch measures 0.87-2.46 us).
  Converted at my measured tau band [0.29, 0.79] it is **45-122 us/step of wall**,
  which still brackets the 68 us excess — so the conclusion holds, but as a
  bracket, not as a 2.3x margin. Per-family intercepts also disagree with the
  pooled fit (qkv 2.29 us, oproj 8.39 us), so the pooled 3.97 is not a precision
  instrument for one family. The *realisable* number is the audited SPLIT=0
  dispatch tax, 0.4478 us/dispatch = 17.5 us/step. Either way the excess sits in
  dispatch structure and not in the kernel text.
- **H-hidden: partly refuted** — see `INTERPRETATION.md`.

This also answers (c): the family does carry `lagunaSharedSwiGLUQMVHeader`, which
makes the prior pessimistic, and the measurement agrees with the prior.

### Attribution capture (SPLIT=1) and the tau correction

TBD-PROFILE-PARAGRAPH

Any profiled-busy number in this document is a *busy* number and is converted to
wall with tau, in this same paragraph, as required: my measured tau for this
family is TBD-TAU (campaign default ~0.40; my published
`L-PROFILED-BUSY-OVERPREDICTS-WALL-2X` is 0.54, CI [0.29, 0.79]; cedar's #699 is
[0.27, 0.43]). All of section 2 is **wall-clock**, unprofiled, and needs no tau.

---

## 5. A correction against myself

`PRICING-NOTE.md` records that **I mis-priced my own target in `PREREG.md` by a
factor of 2.2.** I applied the Rule 105.12 core-scaling divisor (/2.29) to an
excess that the charge itself calls core-count invariant. The correct tau=1 price
of the whole 68 us/step is 0.75 x 68 / 8972 = **0.57 %**, not the 0.26 % I
pre-registered.

The correction makes the negative *stronger*, not weaker: the dose arms only ever
reach the core-scalable interior, and the prize moves entirely into dispatch
structure. Note also that the pre-registered P0 band of 700-900 us was 0.60x too
generous, recorded in `SMOKE.md` at the time rather than quietly retuned.

**And a second error inside the correction.** An earlier draft of `PRICING-NOTE.md`
divided alphonse's 76.8 us/step by his 40 removed dispatches, got 1.92
us/dispatch, and extrapolated 39 x 1.92 = **75 us/step** as an above-bar follow-on
for this target. Having now read #700's terminal result rather than the campaign's
summary of it, **that extrapolation is wrong and he refutes it himself** (§6.3):
the audited dispatch tax is **0.4478 us/dispatch** (17.9 us/step over his 40), and
his measured 76.8 was **4.29x** that — the surplus being grid-append absorption
available only to a kernel launching fewer threadgroups than the machine has
cores. Corrected, the dispatch-structure bound here is 39 x 0.4478 =
**17.5 us/step, ~4x below the bar**. The correction destroys my own follow-on, and
it is recorded in the document that made the error.

---

## 6. Correctness gate (Rule 105.15)

`research/run_upstream_equivalence.sh` at the default arm, on the clean tree:

TBD-EQUIVALENCE-LINE

A zero selected-test count is not a pass; the count above is non-zero.

The research profiling patch to `device.cpp`/`device.h` is applied and reverted
inside `qmv-dose-profile.sh`; `git status` on both files is empty at the end of
the closing sequence, and the clean release worker was rebuilt so the branch is
left rankable.

---

## 7. What I am NOT claiming

- Not that the kernel is optimal — only that its *interior* cannot yield 68
  us/step, because deleting 75 % of it does not.
- Not that the 75 us/step dispatch-structure follow-on is available. It is an
  upper bound with two known obstructions.
- Not any two-build comparison anywhere: one binary, one env var, everything
  paired within a session.
- No unaudited numbers: every figure here traces to a committed CSV or log.

## 8. Files

- `PREREG.md` — pre-registration, written before the data existed
- `METHOD.md` — design in the form the charge asked for
- `SMOKE.md` — positive-control calibration, including where the pre-registration was wrong
- `INTERPRETATION.md` — the four hypotheses and their adjudication
- `PRICING-NOTE.md` — the mis-pricing correction against myself
- `CO-SCHEDULING-BLIND-SPOT.md` — the one route this instrument cannot see, and its independent pricing
- `D0-A2-IS-THE-SAME-BINARY.md`, `D0b-IS-PREFILL-ADJUDICABLE.md` — the out-of-band asks
- `evidence/` — raw logs, per-step CSVs, analyser JSON, equivalence log, profile capture
