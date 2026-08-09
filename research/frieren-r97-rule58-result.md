# r97-d — rule 58 falsification: the seed prefill is charged to the decode timer

**VERDICT: PASS — rule 58 is confirmed, with the response ratio corrected from
16 to 4.** The 512-token seed prefill runs inside the decode timer, so
`decode_seconds_per_token = 4 * prefill_seconds_per_token + mean_step_seconds`.
Both terminal gates pass and the submitted surface changed by 0 bytes.

**The brief's predicted ratio of 16 is wrong by exactly 4x.** The correct
prediction under the hypothesis is **R = 4**, derived in §2. The measurement
below was preregistered against R = 4, and PASS additionally required the
interval to *exclude* 16.

---

## 1. What was asked, and what the answer is

Rule 58 claims the harness starts its decode wall clock *before* the 512-token
seed forward that populates the KV cache, so that a purely prefill-shaped cost
shows up in the decode metric that carries 75% of the score weight.

It does. Three independent lines of evidence agree:

1. **The harness says so in its own log.** Every `--local-iterate` run prints
   `decode measured start tokens=128 includes_seed_prefill=true` and then
   `decode seed prefill complete seconds=0.6 (charged to decode)`.
2. **The within-run arithmetic identity closes.** `implied_seed / prefill_window
   = 0.998`, 95% CI [0.992, 1.004], n = 16. Predicted 1 under H58, 0 under H0.
   (§4)
3. **The decode metric causally responds to prefill-only injected work at the
   predicted gain of 4.** `R = 3.85`, 95% CI [3.19, 4.49] over a 4-block
   randomised ladder — contains 4, excludes 0, excludes 16. (§5)

The practical consequence: **36.6% of the published decode number on this host
is the seed forward, not stepping** (§4), so the effective score exponent on
512-token forward cost is not 0.25 (§7).

---

## 2. The factor is 4, not 16

Let `S` be the wall time of one 512-token forward and `T_total` the wall time of
the 128 single-token steps, `T_bar = T_total/128`.

```
P = prefill_seconds_per_token = S / 512
D = decode_seconds_per_token  = (S + T_total) / 128 = 4*(S/512) + T_bar = 4P + T_bar
```

Now inject an extra output-neutral cost `d` into *every multi-token forward*
(and only those). The standalone prefill window grows by `d`, and the seed
forward inside the decode window grows by `d`:

```
dP = d / 512
dD = d / 128
R  = dD / dP = 512 / 128 = 4
```

The brief applies the 512/128 conversion twice — once when converting the
injected cost into a per-step delta and again when forming the ratio — and so
predicts 16 and `+62.5 us/step` at `d = 2 ms`. The correct figures are `R = 4`
and `+15.6 us/step`. Competing hypotheses:

| hypothesis | predicted R |
|---|---|
| H58: seed prefill inside the decode timer | **4** |
| H0: seed prefill outside the decode timer | 0 |
| leakage: injection also reaches single-token steps | ~512 |
| brief as written | 16 |

## 3. Harness topology (source of truth)

| what | official ranked harness | `--local-iterate` |
|---|---|---|
| file | `Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift` | `.../LagunaRuntimeLocalIterate.swift` |
| decode timer start | `decodePhaseStart` :966 | `decodePhaseStart` :583 |
| seed forward | `worker.beginDecode` :968 (**after**) | :587 (**after**) |
| decode divisor | 128 :1013 | `decodeSteps * timingRepeats` :674 |
| prefill window | :809-811, divisor 512 :837 | :549-558, divisor :672 |

The timer start strictly precedes the seed forward in **both** entry points, so
`--local-iterate` reproduces the ranked timer topology on this axis. This is
pure harness arithmetic: it is a property of where two `DispatchTime.now()`
calls sit relative to a function call, and it does not depend on the GPU.

## 4. PRIMARY RESULT — the within-run identity (needs no injection)

Each run logs both the seed-forward time and the final `mean_step_seconds`, so
within a single timed window, with no cross-run differencing and therefore no
exposure to host drift:

```
implied_seed = 128 * (D - T_bar)      compared against    prefill window = 512 * P
```

Under H58 the ratio is 1; under H0 it is 0.

Measured over all 16 stage-1 runs:

```
implied_seed / prefill_window = 0.9978   sd 0.0119   n = 16
                               95% CI [0.9920, 1.0037]      (t on the run mean)
                               range   [0.9763, 1.0203]
```

The interval contains 1 and misses 0 by roughly 330 standard errors. H0 is dead.

| idx | rung | seed logged (ms) | seed implied (ms) | prefill window (ms) | implied/window |
|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 600 | 585.5 | 583.8 | 1.003 |
| 2 | 10 | 600 | 592.1 | 606.5 | 0.976 |
| 3 | 20 | 600 | 644.2 | 635.5 | 1.014 |
| 4 | 40 | 700 | 673.6 | 671.4 | 1.003 |
| 5 | 20 | 600 | 623.9 | 635.7 | 0.981 |
| 6 | 10 | 600 | 605.2 | 606.6 | 0.998 |
| 7 | 40 | 700 | 671.8 | 676.5 | 0.993 |
| 8 | 0 | 600 | 586.7 | 593.4 | 0.989 |
| 9 | 20 | 600 | 629.4 | 628.6 | 1.001 |
| 10 | 40 | 700 | 686.6 | 672.9 | 1.020 |
| 11 | 0 | 600 | 586.7 | 591.9 | 0.991 |
| 12 | 10 | 600 | 607.9 | 608.3 | 0.999 |
| 13 | 10 | 600 | 607.6 | 605.9 | 1.003 |
| 14 | 20 | 600 | 629.9 | 635.2 | 0.992 |
| 15 | 40 | 700 | 662.7 | 671.1 | 0.988 |
| 16 | 0 | 600 | 593.0 | 584.7 | 1.014 |

`seed implied` is recovered purely from the two published metrics,
`128*(D - T_bar)`; `prefill window` is `512*P` from the separate prefill phase.
The harness's own `seed prefill complete seconds=` line is printed to one
decimal and is shown only as a coarse cross-check — the identity never uses it.

The same decomposition also quantifies how much of the headline decode number
is not stepping at all:

```
D_stepsonly = 8448.6 us/step   sd 29.1        (128 single-token steps only)
D           = 13085 .. 13699 us/step          (what the harness publishes)
seed share of D = 36.6%        range 35.0% .. 38.8%
```

Independently, `f = 4P/D` computed straight from the two published score fields
gives a 16-run mean of 0.3665 against a seed share of 0.3657 — agreement to
three digits, which is the identity closing a second time from a different pair
of inputs. (Both figures are inflated by the injected rungs; the uninjected
rung-0 runs give `f = 0.3513`, which is the number §7 uses for this host.)

## 5. SUPPORTING RESULT — the causal injection ladder

§4 is an accounting identity. It shows the published `D` is *arithmetically*
consistent with the seed forward being inside the window, but it reads only
numbers the harness chose to print. §5 asks the causal question instead: if I
add work that provably executes **only** in multi-token forwards, does the
decode metric move, and by how much per unit of prefill movement?

16 runs, 4 blocks of the 4 rungs {0, 10, 20, 40} injected matmuls, order
randomised within each block (seed 93), 60 s pre-cool, one 40 C-gated
`--local-iterate` run each. All 16 passed their correctness gate.

| rung | n | mean D (us/step) | mean P (us/token) | dD | dP | dD/dP |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 4 | 13085.3 | 1149.34 | — | — | — |
| 10 | 4 | 13135.8 | 1185.17 | 50.5 | 35.83 | 1.41 |
| 20 | 4 | 13379.4 | 1237.81 | 294.1 | 88.48 | 3.32 |
| 40 | 4 | 13699.4 | 1314.42 | 614.0 | 165.08 | 3.72 |

Preregistered estimators, 95% intervals from a bootstrap over whole blocks:

| estimator | R | CI low | CI high | half-width |
|---|---:|---:|---:|---:|
| **free_intercept_ols (PRIMARY)** | **3.846** | **3.186** | **4.491** | **0.653** |
| through_origin | 3.515 | 2.777 | 4.314 | 0.769 |
| nonzero_rungs_only | 4.386 | 3.488 | 5.396 | 0.954 |
| step_drift_adjusted *(exploratory)* | 4.073 | 3.520 | 4.628 | 0.554 |

Preregistered verdict flags on the primary estimator: contains 4 ✅, excludes
0 ✅, excludes 16 ✅, half-width < 0.8 ✅. **PASS.**

All four estimators sit in 3.5 .. 4.4. None comes within a factor of three of
the brief's 16, and none is consistent with 0.

### Why the ladder is looser than the identity

Block-paired deltas, each rung against its own block's rung-0 run:

| rung | block 0 | block 1 | block 2 | block 3 |
|---:|---:|---:|---:|---:|
| 10 | −0.96 | 3.70 | 3.79 | 0.69 |
| 20 | 3.98 | 3.07 | 4.28 | 2.17 |
| 40 | 3.73 | 3.73 | 4.75 | 2.72 |

The dispersion is concentrated at rung 10 and shrinks monotonically with rung.
That is the expected signature, not a defect: the ladder differences `D` across
runs, and `D = 4P + T_bar` passes any between-run drift in `T_bar` straight into
`ΔD` one-for-one. Across these 16 runs `T_bar` (`D_stepsonly` above) wanders over
8421 .. 8507 us/step, an 86 us/step band. At rung 10 the injected signal is only
about 4 × 36 = 143 us/step, so a single unlucky pairing can flip its sign — which
is exactly what block 0's rung-10 run did. At rung 40 the signal is ~660 us/step
and every block agrees.

This is also the reason §4, not §5, is the primary result: the within-run
identity conditions that drift term away entirely instead of differencing across
it.

## 6. Gate 0 — the instrument is valid

Both terminal gates were fixed in the preregistration and both **PASS**. Six
probe runs, order `0 32 8 0 32 8` so rung is not confounded with time.

| idx | rung | prefill ms | seed ms | step0 ms | steady ms | sd | div | token sha |
|---|---|---|---|---|---|---|---|---|
| 1 | 0 | 573.02 | 545.90 | 10.181 | 8.2363 | 0.0372 | 0 | `85332cc2758ce7c7` |
| 2 | 32 | 622.17 | 617.57 | 13.440 | 8.2154 | 0.0381 | 0 | `85332cc2758ce7c7` |
| 3 | 8 | 564.54 | 563.77 | 13.260 | 8.2045 | 0.0364 | 0 | `85332cc2758ce7c7` |
| 4 | 0 | 547.75 | 545.91 | 9.360 | 8.2431 | 0.0370 | 0 | `85332cc2758ce7c7` |
| 5 | 32 | 618.22 | 627.33 | 13.303 | 8.2115 | 0.0347 | 0 | `85332cc2758ce7c7` |
| 6 | 8 | 564.35 | 563.94 | 13.392 | 8.2245 | 0.0411 | 0 | `85332cc2758ce7c7` |

**GATE 0b — output-neutral: PASS.** Zero teacher-forced divergences at every
rung and a single distinct token hash `85332cc2758ce7c7` across all six runs.
The injected work does not touch any value the model produces.

**GATE 0a — prefill-only: PASS.** The injection must be invisible to the 128
single-token steps.

| rung | d_seed ms | d_prefill ms | ms/matmul | d_steady us/step | leak fraction | z |
|---|---|---|---|---|---|---|
| 8 | 17.95 | 4.06 | 2.244 | -25.2 | -0.00140 | -2.88 |
| 32 | 76.55 | 59.81 | 2.392 | -26.2 | -0.00034 | -2.99 |

Between-run steady sd is 8.8 us/step; worst \|z\| = 2.99, worst \|leak\| =
0.14% of the injected cost. The residual per-step offset is **flat across
rungs** (-25.2 vs -26.2 us for a 4x change in injected work, where genuine
leakage would scale by 4x) and it is **negative**. Neither is consistent with
injected work reaching the single-token steps; both are consistent with
ordinary between-run drift. **Calibration: 2.392 ms per injected matmul.**

### 6a. Gate 0's own direct confirmation of rule 58 (exploratory)

The probe logs the seed forward separately, so Gate 0 already answers the
question without any ratio estimator. Under H58 the injected cost should land in
the decode-timed seed forward at the *same* size as in the standalone prefill
window, i.e. `d_seed / d_prefill ~ 1`; under H0 it should be 0.

| rung | all 6 runs | warm only (drop idx 1) |
|---|---|---|
| 8 | 4.421 | **1.075** |
| 32 | 1.280 | **1.057** |

Read the warm-only column. The all-runs column is distorted by a single
artifact: idx 1 is the first run of the session and its *prefill* window is
573.02 ms against 547.75 ms for the other rung-0 run — a 25 ms warm-up
inflation that lands entirely in the rung-0 prefill baseline. The seed forward
is unaffected and is extraordinarily reproducible across those same two runs
(545.90 and 545.91 ms, 10 us apart), which is why only the prefill-derived
denominator moves.

So the seed forward inside the decode timer absorbs the prefill-only injected
cost essentially 1:1 (5-8% high), while the single-token steps absorb 0.14% of
it. That is rule 58 stated as directly as this instrument can state it.

**Honesty flags.** This sub-analysis and the warm-only exclusion were both
added *after* seeing the data; they were not preregistered, and n = 2 per rung.
They are reported as corroboration of the preregistered result in §4-5, not as
the primary evidence. The 5-8% excess is not explained here — plausible causes
are a slightly different cache/allocator state for the seed forward, or a small
bias in the two-run rung-0 baseline.

## 7. What this changes about the programme

### 7a. The scoring exponents are not 0.25 / 0.75

The score is `decode_speedup^0.75 * prefill_speedup^0.25`. Because
`D = 4P + T_bar`, the 512-token forward appears in **both** factors. Define the
fraction of the decode metric that is actually seed prefill:

```
f = 4P / D
```

Differentiating `log score` with respect to the two *physical* costs — the cost
of one 512-token forward, and the cost of one single-token step — gives:

```
d log score / d log(512-token forward cost) = -(0.25 + 0.75 f)
d log score / d log(single-token step cost) = -0.75 (1 - f)
```

These are the exponents that actually matter when choosing what to optimize.
`f` is readable from any score JSON with no extra measurement:
`f = 4 * prefill_seconds_per_token / decode_seconds_per_token`.

| host | P (us/tok) | D (us/step) | f | forward exponent | step exponent |
|---|---|---|---|---|---|
| **M5 pinned baseline (ranked)** | 367.5 | 13856.2 | **0.1061** | **0.3296** | **0.6704** |
| this M4 Pro host (rung-0 mean, n=4) | 1149.3 | 13085.3 | **0.3513** | 0.5135 | 0.4865 |

On the ranked M5 the multi-token forward path carries an effective exponent of
**0.330, not 0.25 — it is 31.8% more valuable than the nominal prefill weight
suggests**, and the single-token step path carries **0.670, not 0.75 — 10.6%
less valuable**. The exchange rate between the two on M5 is
`0.3296 / 0.6704 = 2.03`: a 1% cut in the 512-token forward is worth about the
same as a 2.03% cut in the single-token step.

Worked example: a change that makes the 512-token forward 10% *slower* but the
single-token step 5% *faster* is worth **+0.30%** score on M5. The naive
0.25/0.75 reading predicts **+1.48%** — off by 4.9x, and it is exactly the sort
of trade a decode-focused optimization makes.

### 7b. Practical consequences

1. **Anything that speeds up a 512-token forward is scored twice.** Prefill-shaped
   work — the `_nax` GEMM path, MoE gather-GEMM at 512 rows, the 512-row
   attention path — pays into the 0.25 prefill factor *and* into 10.6% of the
   decode factor on M5. Kernel work that is usually filed under "prefill only"
   is materially better than the nominal weight implies.
2. **A decode-only win is worth less than 0.75.** Any change that only touches
   the single-token step path (KV read patterns, single-row SDPA, per-step
   dispatch overhead) is scored at 0.670 on M5, not 0.75.
3. **A change that regresses the 512-token forward to help the step path faces a
   steeper bar than expected.** The breakeven point is `f = 1/3`; M5 sits well
   below it at 0.106, so on M5 the step path still dominates — but the margin
   is 2.03x, not the 3x that 0.75/0.25 suggests.
4. **`f` is strongly hardware-dependent and must be read from an M5 score JSON.**
   This M4 Pro host reports `f = 0.351`, essentially at breakeven, where the two
   paths are worth the *same*. Any exponent reasoning done from local numbers
   will be wrong. Only the identity `D = 4P + T_bar` transfers; `f` does not.

## 8. Honest limits

1. **Host.** All measurements are from one AWS M4 Pro (48 GiB, low-memory
   startup profile, Apple GPU generation 16, no `_nax` kernel selection). The
   *timer topology* result is harness arithmetic and transfers to M5 — it is a
   property of statement order in Swift source, confirmed by reading both entry
   points (§3). The *magnitude* `f` does not transfer and the M5 value in §7a is
   computed from the pinned baseline constants, not measured by me.
2. **`--local-iterate`, not the ranked binary.** I verified by source reading
   that both entry points start the decode clock before the seed forward, and
   that both use divisors 512 and 128. I did not run the ranked harness.
3. **The injection is an instrument, not a cost model.** Each injected matmul is
   512x8192 @ 8192x2048 bf16 = 8.59 G fma. That is roughly eight orders of
   magnitude above the free-ALU budget of about 96 fma per weight byte. This
   experiment deliberately measures *where a large, unambiguous, output-neutral
   cost is charged*; it says nothing about the price of cheap ALU work, and the
   calibration constant (2.392 ms per matmul) is a property of this host.
4. **Bound only, on the intercept.** The free-intercept estimator absorbs
   run-to-run drift into an intercept term; I quote that intercept only as a
   bound consistent with zero rather than as a measured offset.
5. **Single-token-step leakage is excluded, not proven absent.** Gate 0a shows
   the residual per-step offset is flat across rungs (a 4x rung increase does
   not scale it) and *negative*, which is inconsistent with leakage; it is
   consistent with ordinary between-run drift.
6. **Estimator choice was preregistered.** `free_intercept_ols` was named PRIMARY
   before the ladder ran (preregistration amendment §6b). The two alternates are
   reported for transparency, not for selection.

## 9. Reproduction

**Deliverable substitution note.** The assignment asked for a patch file
`research/frieren-r97-rule58-inject.patch`. No patch is shipped, because the
required instrument **is already committed and default-inert** on the base:
`lagunaInjectLayerWork` in `Sources/MLXFastModel/LagunaRuntimeModel.swift`
(call site :9128, body :9511-9556, prefill-only guard :9515-9516, rung-0
early-out :9507-9509), gated by `DARKBLOOM_INJECT_PREFILL_MATMULS` which
defaults to 0 (:9373-9374). Shipping a patch would have meant either
duplicating existing code or making a submitted-surface change for no reason.
**The submitted surface changed by 0 bytes** (`growth=0/262144`). What follows
is the recipe that replaces the patch.

```bash
# Stage 0 - instrument validation (6 runs, ~25 min)
OUT=research/r97-runs/stage0 ORDER="0 32 8 0 32 8" \
  bash research/frieren_r97_stage0_probe.sh
python3 research/frieren_r97_stage0_gates.py research/r97-runs/stage0

# Stage 1 - the ladder (16 runs, ~70 min)
RUNGS="0 10 20 40" BLOCKS=4 SEED=93 PRECOOL_SECONDS=60 \
  OUT=research/r97-runs/stage1 \
  bash research/frieren_r97_stage1_local_iterate.sh
python3 research/frieren_r97_analyze.py research/r97-runs/stage1

# Scoring exponents from any score JSON (no measurement needed)
python3 research/frieren_r97_score_weights.py research/r97-runs/stage1/*.score.json
```

A single run is `DARKBLOOM_INJECT_PREFILL_MATMULS=<rung> ./benchmark.sh
--local-iterate`. Rung 0 is the unmodified base. The knob passes through the
worker environment sanitiser (`LagunaRuntimeWorker.swift:1928-1958`).

| file | role |
|---|---|
| `research/frieren-r97-rule58-preregistration.md` | hypotheses, gates, estimators, fixed before measuring |
| `research/frieren_r97_stage0_probe.sh` | Gate 0 probe driver |
| `research/frieren_r97_stage0_gates.py` | Gate 0a/0b evaluator, exit 0 iff both pass |
| `research/frieren_r97_stage1_local_iterate.sh` | blocked, seeded ladder driver |
| `research/frieren_r97_analyze.py` | decomposition, ladder, three estimators, block bootstrap |
| `research/frieren_r97_score_weights.py` | effective-exponent calculator (§7a) |
| `research/frieren_r97_wandb_log.py` | W&B logging |
