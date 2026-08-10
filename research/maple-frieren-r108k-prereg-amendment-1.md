# R108-K preregistration amendment 1 — the barrier-region price probe

- Assignment `maple-r108-k-decode-dispatch-merge`, revision `r108-k-rev1`, PR #660,
  student maple-frieren, host AWS M4 Pro (`applegpu_g16s`, gen 16, `nax_available=false`).
- Written **2026-08-10 17:0xZ, before any timing run of this probe**, in response to
  PR #660 comment 6 (16:31Z, "STOP BEFORE YOU BUILD"), which supersedes the
  build-the-merge plan and replaces rule 105.23(f)'s decision rule.
- The original §0 preregistration in `research/maple-frieren-r108k-decode-dispatch-merge.md`
  fixed a four-word outcome vocabulary — `N-MERGE-UNREACHABLE`, `Y-MERGE-CLASS1`,
  `Y-MERGE-CLASS2`, `N-REMOVAL-ASYMMETRIC` — for a *merge* deliverable. **None of the
  four is a legal verdict for a price probe.** Rather than silently reinterpret one of
  them after seeing the timings, this amendment adds a disjoint verdict set for the
  probe and leaves the original four untouched and still owned by deliverable B.
  The original four are not redefined, reweighted, or retired here.

## 1. What is being measured, and why the instrument needs zero source bytes

The probe needs N no-op GPU dispatches per decode step in two variants: one whose
only buffer input is *not* in the Metal command encoder's `prev_outputs_` set (so
`CommandEncoder::maybeInsertBarrier()` emits nothing and the no-ops overlap), and
one whose input *is* the previous no-op's output (so a
`memoryBarrier(MTL::BarrierScopeBuffers)` fires between every pair).

That facility is already in the base tree and is already switchable from the
environment. Verified at HEAD `c46b3934`, `Sources/MLXFastModel/LagunaRuntimeModel.swift`:

| line | fact |
|---|---|
| 11930 | `lagunaInjectEnvInt(_:_:)`, accepts `value >= 0` |
| 11963 | `DARKBLOOM_INJECT_DECODE_EMPTY`, default 0 — N no-ops per decode step |
| 11966 | `DARKBLOOM_INJECT_PREFILL_EMPTY`, default 0 — left at 0, prefill untouched |
| 11971 | `DARKBLOOM_INJECT_EMPTY_SPREAD`, default 1 — spread over all 40 layers |
| 11975 | `DARKBLOOM_INJECT_EMPTY_TG`, default 160 |
| 11980 | `DARKBLOOM_INJECT_EMPTY_CHAIN`, default 1 |
| 12040 | `lagunaInjectEmptyKernel` = `laguna_inject_empty_dispatch_v1`, inputs `["control","prev"]`, output `["sink"]`, body `if (control[0] == 0xFFFFFFFFu) { sink[gid & 255u] = gid + prev[0]; }` — writes nothing at runtime |
| 12105 | `lagunaInjectLayerWork(layer:isSingleTokenDecode:)`, called from the forward at 11715 inside `for (i, layer) in layers.enumerated()` |
| 12130 | **the dependency edge:** `lagunaInjectEmptyChain ? tail : scratch.control[7]` |

So `DARKBLOOM_INJECT_EMPTY_CHAIN=0` binds `prev` to `LagunaInjectStore.scratch.control[7]`,
a constant `MLXArray` materialised once at store construction and never written by a
kernel again — therefore never in `prev_outputs_`, therefore no barrier. `CHAIN=1`
binds `prev` to the previous no-op's own output — a true RAW hazard on
`device.cpp:325`'s `needs_barrier_ |= (prev_outputs_.find(r_buf) != prev_outputs_.end())`.
**`CHAIN=1` is the default, and therefore the configuration in which rule 65's
+2.3403 M5 µs/added-dispatch was measured.** No `Sources/` byte is spent by this probe
and the assignment's editable-byte budget is untouched.

Both arms are byte-, grid- and threadgroup-matched by construction (same kernel, same
`EMPTY_TG`, same count, same per-layer `asyncEval`); only the dependency edge differs.
Both are correctness-green by construction: the sink is never read by the model.
`passed_correctness` is recorded per run anyway and any `false` voids that row.

## 2. Arms (fixed here, before any run)

Executed by `research/maple-frieren-r108k-barrier-region-price.sh`, committed in the
same commit as this amendment. All arms are `./benchmark.sh --local-submit`
(1023 decode steps; rule 86 forbids treating a `--local-iterate` delta as evidence).

| arm | `DECODE_EMPTY` | `EMPTY_TG` | `EMPTY_CHAIN` | role |
|---|---|---|---|---|
| C | 0 | — | — | control anchor, one per block |
| F | 160 | 8 | 0 | decision rung, no barriers |
| S | 160 | 8 | 1 | decision rung, barrier per no-op |
| H | 1200 | 8 | 0 | mechanism rung, no barriers |
| J | 1200 | 8 | 1 | mechanism rung, barrier per no-op |
| G | 2400 | 8 | 1 | **positive control / gauge, run first** |

Order, fixed: `GCFSCSFCHJCFSCSFCJH`. Blocks 1,2,4,5 are the 160 rung; blocks 3,6 are
the 1200 rung; within each rung the injected arm sits in block position 2 as often as
position 3. The 1200 rung is at block 3, not last, so truncation still leaves a
mechanism block.

`EMPTY_TG=8` is chosen to match r93-A and the historical M5 ladder exactly, so this
campaign's slopes are directly comparable with rule 65 and with
`research/r93-runs/knee-results.md` rather than to a new grid geometry.

**Why two rungs.** r93-A already measured the *chained* ladder on this host: K=240 and
K=480 are free (segment slopes −0.43 and −0.03 M4 µs/dispatch), the curve only turns
positive past ~480 (+0.58, +0.73, +1.98, +2.36). r93-A therefore *predicts* that arm S
at N=160 is free as well, and that a null at the 160 rung would say nothing about
barriers. The 160 rung answers the **decision** question — what does one dispatch cost
where production actually sits, at ~411 dispatches/step. The 1200 rung answers the
**mechanism** question — r93-A puts the chained 1200 rung at +374 µs/step, so if H is
null while J reproduces ≈+374 µs/step, the barrier is the price and the launch is free.

**Why N = 160 and not 40.** The family-E merge removes 40 dispatches/step. nezuko's
paired instrument resolves ≈24.8 µs/step of paired-difference sd, i.e. CI95 half-width
≈48.6/√B µs/step, so a 40-wide lever is ±0.76/√B µs/dispatch — it cannot separate 0.3
from 0.8 at any affordable block count. At N=160 the same instrument gives
±0.30/√B µs/dispatch (±0.15 at B=4, ±0.12 at B=6). **Linearity between 40 and 160 is a
declared assumption**, supported by r93-A's −0.43 and −0.03 segment slopes over
0→480 but not proven at 40; it is stated as a limitation, not hidden.

## 3. Gauge (the provenance guard, declared before the run)

G reproduces r93-A's steepest measured rung: K=2400 chained measured 11.344 ms vs
8.223 ms at K=0, i.e. **+3121 µs/step = +38 %**.

- **Gauge passes** if `mean(G) − mean(C) ≥ +500 µs/step`. This is deliberately far
  below the +3121 µs prediction so that the guard tests *channel liveness*, not the
  exact reproduction of a cross-epoch number.
- **Gauge fails** otherwise. On a gauge failure every other arm in this campaign is a
  fabricated zero and the probe reports `P-INSTRUMENT-DEAD` with no slope at all. I
  will not report a null from a channel I cannot show is live.

## 4. Estimands and analysis, fixed before the numbers exist

Level for every run is `metrics.decode_seconds_per_token × 1e6`, in M4 µs/step, from
`score.json`. Blocks are the unit of analysis; the control anchor in the same block is
the comparator, so slow drift and thermal state are differenced out.

- For each 160-rung block b: `dF(b) = F(b) − C(b)`, `dS(b) = S(b) − C(b)`.
- For each 1200-rung block b: `dH(b) = H(b) − C(b)`, `dJ(b) = J(b) − C(b)`.
- Point estimates `mean_b d·`; CI95 = `mean ± t(0.975, B−1) · sd/√B`, Student t, no
  normal approximation at B ≤ 6.
- Slopes in M4 µs per injected dispatch: `dF/160`, `dS/160`, `dH/1200`, `dJ/1200`.
- Separation, tested paired within block, not by comparing two CIs:
  `dS(b) − dF(b)` on the 160 rung and `dJ(b) − dH(b)` on the 1200 rung.
- No outlier rejection. No arm is dropped after the fact. Rows with
  `passed_correctness != true` or a missing `score.json` are voided and named.
- Both the M4 slope and its M5 equivalent are reported. Rule 105.13's
  `k_dispatch = 1.890` and my own §1 ceiling `k_removal ∈ [0, 0.964]` are *not*
  applied to convert; the M4 number is the measured one and the M5 conversion is
  labelled as a conversion.

**Stopping rule, declared:** stop after the last block that completes before 18:20Z,
minimum four blocks. Rows are appended per run, so truncation after any completed
block leaves the recorded blocks valid. If fewer than four blocks complete, the probe
reports `P-INDETERMINATE-UNDERPOWERED` with the blocks it has and the achieved CI.

## 5. Probe verdict vocabulary (new, disjoint from deliverable B's four)

Exactly one of these is reported. The mapping to action is the advisor's, from #660
comment 6, and is fixed here so that it cannot be reinterpreted after the fact.

| verdict | trigger | consequence |
|---|---|---|
| `P-INSTRUMENT-DEAD` | gauge fails (§3) | no slope reported; the probe is void, not null |
| `P-FREE-REGION-CONFIRMED` | gauge passes **and** arm F slope CI95 upper bound ≲ 0.3 M4 µs/dispatch | the dispatch-count merge programme is dead; this probe is my terminal result for R108-K; rules 105.17 / 105.20(g)-route-A / 105.23's two-merge portfolio all lose their price basis |
| `P-LAUNCH-TAX-CONFIRMED` | gauge passes **and** arm F slope CI95 lower bound ≳ 0.8 M4 µs/dispatch | 105.17 survives; build the family-E merge; 105.23's two-merge portfolio is back on |
| `P-INDETERMINATE` | gauge passes and arm F's slope or its CI straddles the 0.3–0.8 band | report both slopes with CIs and let the advisor decide; do not pick a side |
| `P-INDETERMINATE-UNDERPOWERED` | fewer than four blocks complete | as above, plus the achieved half-width |
| `P-READING-REFUTED` | gauge passes and the paired `dJ − dH` separation CI includes zero on the 1200 rung, i.e. chaining costs no more than not chaining where r93-A says chaining costs +374 µs/step | the advisor's `device.cpp` reading of `maybeInsertBarrier` does not control end-to-end decode time; he asked to be told immediately |

`P-READING-REFUTED` and one of the slope verdicts can both be true; in that case both
are reported, `P-READING-REFUTED` first, because it is the one he asked to hear
immediately.

A null at the 160 rung with a *simultaneous* null on `dS − dF` at that rung is **not**
`P-READING-REFUTED`. r93-A predicts exactly that, because at N=160 both arms sit
inside the host-absorbed region. That is why the 1200 rung exists and why the
refutation test is defined only there.

## 6. What is deliberately not measured, and not faked

- **Rule 98.9's residency-defeated arm is unavailable.** `FERN_DEFEAT_SLOTS` is a knob
  of fern's standalone desk microbenchmark only; `grep` over `Sources/` and over every
  `*.sh` outside `research/` finds no reader. Exporting it around `./benchmark.sh`
  would be inert and would manufacture a null. Declared as a limitation of this probe,
  not worked around.
- **Prefill is untouched.** `emptyTotal = isSingleTokenDecode ? decodeEmpty : prefillEmpty`
  is an internal control, and `DARKBLOOM_INJECT_PREFILL_EMPTY` stays 0.
  `prefill_seconds_per_token` is recorded as a falsification check: it must not move.
- **No `Sources/` edit, no build variation.** `./benchmark.sh` rebuilds both products
  itself; every arm runs the same binary, so the arms differ only in environment.
  `git checkout -- Package.resolved` after each run keeps the checkout clean.

## 7. Two advisor self-corrections carried into the report

1. Rule 105.20 priced family E at `n = 30`; the correct `n` is **40** (30 h64 calls +
   10 h48 calls), so every family-E figure in 105.20 is 33 % low. My R108-K Stage 0
   report already used 40.
2. My R107-F §11.4 headline "one merge total **+2.19–2.31 %**" **double-counts** and is
   retracted here: rule 65's 2.3403 µs was itself measured with *dependent* probes, so
   the barrier-drain term is a decomposition *of* the dispatch term, not an addition to
   it. The sum is not carried forward anywhere in R108-K.

## 8. Amendment 2 — stopping-rule wall clock (declared 2026-08-10T17:11Z)

Declared **before any treatment row existed**. At the moment of writing, the row sink
`/tmp/r108k-barrier-price.tsv` held exactly one data row, `idx=1 arm=G` (the gauge), and
zero rows for arms C, F, S, H, or J. No difference, slope, or separation had been
computed or observed. The amendment is therefore outcome-independent by construction,
and it is committed ahead of the first control row so the commit timestamp proves
precedence.

**Change.** §4's stopping rule read "stop after the last block completing before
**18:20Z**, minimum four blocks". The wall clock moves to **18:25Z**. Nothing else
changes: the minimum of four blocks, the fixed arm order, the block-paired estimator,
the Student-t interval, the §5 verdict vocabulary, and the 19:00Z report deadline all
stand.

**Reason.** The gauge run measured 383 s of wall clock per run, a figure not available
when §4 was written. At that pace the 12th run — the third and last run of block 4 —
completes at ≈18:20:03, three seconds after the original line. The 18:20Z figure was
never a scientific quantity: it was a budget back-computed from the 19:00Z report
deadline. Holding it literally would discard a complete, already-paid block and force
`P-INDETERMINATE-UNDERPOWERED` on a rounding artifact, which is the worse error. 18:25Z
still leaves 35 minutes for analysis, write-up, byte-budget preflight, and submission,
and it does **not** reach block 5 (run 15, ≈18:39Z) at any plausible pace, so the
amendment cannot be a disguised licence to keep sampling until a threshold is crossed.

**Bound.** The probe is stopped at 18:25Z regardless of state. A block that has not
completed all three of its runs by then is discarded whole; partial blocks are never
analysed, because the estimator is defined only against a block's own control anchor.
If four blocks are still not complete, `P-INDETERMINATE-UNDERPOWERED` is reported with
the achieved half-width, exactly as §4 requires.
