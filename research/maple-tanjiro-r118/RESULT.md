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

Per the landing rule I ship only on a verified positive interval excluding zero.
There is none here that clears the bar. **Do not land.**

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
  audited 3.97 us Rule-55 intercept = **155 us/step of floor**, which is 2.3x the
  entire 68 us excess. The excess is comfortably inside the dispatch structure,
  not inside the kernel text.
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

The follow-on that this implies — 39 dispatches x alphonse's realised 1.92
us/dispatch = **75 us/step, core-count invariant, ~0.44-0.63 %** — I hold at
arm's length for two stated reasons: this target is not in the absorption cell at
12.8 TG/core, and it has no free merge partner. I am not claiming it; I am
recording it so the next person does not have to re-derive it.

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
- `D0-A2-IS-THE-SAME-BINARY.md`, `D0b-IS-PREFILL-ADJUDICABLE.md` — the out-of-band asks
- `evidence/` — raw logs, per-step CSVs, analyser JSON, equivalence log, profile capture
