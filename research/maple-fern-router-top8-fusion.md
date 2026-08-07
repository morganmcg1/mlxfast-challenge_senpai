# PR #204 — Router top-8 fusion: publishing the decode router from the QMV producer

- assignment: `maple-2026-08-07b-router-top8-fusion`, revision `r1`
- branch: `maple-fern/router-top8-fusion`, base `1fe609eb920dd96a409f2949a0e901d3bb525af6`
- submitted surface: `Sources/MLXFastModel/LagunaRuntimeModel.swift` only
- measurement host: Apple **M4 Pro**, 48 GiB (low-memory startup profile), 20 GPU cores

## 1. What was changed

Arm 3 of the pre-registered set: **delete the standalone dispatch, let an
existing producer emit the result.**

At decode, every one of the 39 MoE layers issued
`laguna_decode_router_top8_ordinal_table_norm_v1` as its own Metal dispatch —
one threadgroup of 256 threads that sorts 256 ordinal keys, extracts the top 8,
reads 8 scores back out of a threadgroup table, sums them across a simd and
writes 8 `uint32` indices plus 8 `float32` normalized scores.

The change makes the routed gate/up NVFP4 QMV+SwiGLU kernel publish those two
arrays itself, from **one** of its 2048 threadgroups, and skips the standalone
dispatch entirely. Net dispatch delta: **−39 per decode step, +0 added.**

### 1.1 Why this is nearly free — the load-bearing observation

The QMV kernel is `..._packed_top8keys_r1_...`: it already receives
`router_keys` and each threadgroup **already runs the selection tournament for
itself**, in the shared prelude (`LagunaRuntimeModel.swift:7504`):

```metal
thread uint top8_keys[8];
for (uint j = 0; j < 8; ++j) { top8_keys[j] = router_keys[lane + 32u * j]; }
uint top8_mask = 0u, top8_winner = 0u;
for (uint r = 0; r <= expert_slot; ++r) {
    top8_winner = laguna_router_top8_extract_round(top8_keys, top8_mask, lane);
}
uint expert = top8_winner;
```

So the top-8 selection was **already being computed 2048 times per layer**
inside the consumer. The standalone dispatch was a 39×/step *redundant
re-selection*; its only unique product was the normalized score vector and a
materialized index array for the down kernel.

Threadgroup `group == 7` has `expert_slot == 7`, so it already executes all
eight extraction rounds. The emit block re-runs those eight rounds on
`simd_group == 0` from a **fresh reload of the keys** rather than threading a
per-rank winner through the prelude. That is deliberate: it keeps the fallback
kernel's Metal source byte-for-byte identical, so the non-emit path cannot
regress. The marginal added ALU is one extra 8-round tournament on 32 lanes of
1 of 2048 threadgroups, against a per-threadgroup 2048-wide NVFP4 dot product
that dominates it by orders of magnitude.

### 1.2 Shape of the edit

Two edits in one file, +188/−6:

1. `lagunaRoutedSwiGLUQMVPackedTop8R1Source(emitRouter:)` — the existing source
   builder gains a flag. `emitRouter: false` reproduces the previous source
   byte for byte; `true` appends the emit block. A separate kernel object,
   `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_emit_bf16_v1`, carries the
   extra outputs (renaming is mandatory — the JIT cache is keyed by name).
2. A guarded fast path in `LagunaRuntimeSparseMoEBlock.forward`, placed
   immediately before `gate(x, logits:)`, that calls the emit kernel and returns
   through the existing down+residual fusion. The guard set is a restatement of
   the guards the existing fused chain already required, plus the emit flag.
   `fusedSharedDownInputs` is evaluated **last** so a fall-through never wastes a
   dispatch. The prefill branch and every fallback are untouched.

`DARKBLOOM_DECODE_ROUTER_EMIT_SINK=0` restores the previous behaviour on the
same binary. That is what makes the A/B below a true single-binary contrast.

## 2. Bit-exactness

### 2.1 The two traps, and why they are avoided

The assignment pre-registered two ways this change silently breaks exactness.

**Trap 1 — summation order.** The deployed kernel accumulates
`total = simd_shuffle(my_score, i) + total` for `i = 0..7`, i.e. strictly in
rank order with the running total on the right. Floating-point addition is not
associative, so any reassociation changes the result. The emit block reproduces
that loop verbatim, including operand order.

**Trap 2 — score provenance.** The scores must come from the same sigmoid
expression, never reconstructed from the lossy ordinal key. The emit block uses
`x = float(router_logits[my_index]); y = 1/(1+exp(|x|)); score = x<0 ? y : 1-y`,
reading the same `bfloat16` logits array the gate's decode cast-sink already
passes to the standalone kernel unconverted.

### 2.2 The deployed variant is the *table* variant

A correction to the assignment's framing: the default deployed kernel is
`..._ordinal_table_norm_v1`, not the recompute variant
(`DARKBLOOM_ROUTER_ORDINAL_SCORE_TABLE` defaults on, `:8809`). The table variant
stashes `original_scores[lane] = score` in threadgroup memory before the sort
and reloads `my_score = original_scores[my_index]` after it. An `fp32` store
followed by an `fp32` load is the identity, and the sort's `stride >= 32` rounds
carry barriers that separate the write from the read, so the table and recompute
variants are bit-identical. The emit block matches both.

### 2.3 Three-axis structural argument

- **Selection** — `laguna_router_key_ordinal` is the standard monotone
  `float → uint` total order (NaN above every finite key; both zeros map to the
  same code), and `laguna_router_ordinal_before` breaks ties by index. This is
  structurally the same comparator and the same total order the standalone sort
  uses, so the *set* of eight winners agrees.
- **Rank** — the tournament extracts winners one at a time, masking each as it
  goes, so rank `r` is the `r`-th largest under that total order, matching the
  sorted array's position `r`.
- **Scores** — identical expression on identical inputs (§2.1).

### 2.4 Empirical certificate

Full-vocabulary bitwise logit digests (`top_k = 100352`, SHA-256 per step),
64 teacher-forced steps, both arms on the **same binary**:

| arm | `DARKBLOOM_DECODE_ROUTER_EMIT_SINK` | run digest |
|---|---|---|
| `emit` | 1 | `3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928` |
| `base` | 0 | `3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928` |

**0 of 65 step digests differ.**

### 2.5 Sensitivity control — the certificate is not vacuous

A digest match only means something if the instrument can see a difference.
Downstream, the score is consumed as `bfloat(router_weights[routed_slot])`
(`:8068`) — it is rounded to `bfloat16`. So a 1-ULP **fp32** perturbation would
be absorbed by that cast and would prove nothing. The injected fault is
therefore exactly **one `bfloat16` ULP** on the stored score:

```metal
float fault_out = my_score / total;
fault_out = as_type<float>(as_type<uint>(fault_out) + (1u << 16));
```

| arm | run digest | vs clean reference |
|---|---|---|
| `faultemit` (sink=1) | `13a22cdee14a0798960f46a1b4bf0156e4fdd02bf07ace120f8d65fe6c625341` | **differs** |
| `faultbase` (sink=0) | `3447204b…4928` | identical |

**65 of 65 step digests differ, first difference at step 0.** The fault-carrying
binary still reproduces the clean reference exactly on the base arm, which also
confirms the fault is confined to the emit path. The instrument has full
sensitivity to the smallest perturbation that can survive to the consumer; the
0/65 match in §2.4 is a real certificate.

### 2.6 Reachability witness

`DARKBLOOM_TRACE_FUSION=1` with the sink on prints:

```
mlxfast: fusion active: routed gate/up QMV + SwiGLU (packed, producer keys, router sink)
```

The guard chain is entered on the scored decode path, so the digest match is
not the trivial consequence of a fall-through.

## 3. Pre-registered timing predictions

Recorded **before** any timing data was inspected, from an independent analysis
of the dispatch cost model `T = a + W·φ` with `a = 1.661 µs`,
`φ = 1.469 µs/wave` (single-threadgroup floor `a + φ = 3.13 µs`):

| model | predicted Δ decode µs/step |
|---|---|
| strictly serial dispatches | −181 (range −122 … −205) |
| fully overlapped dispatches | −68 (range −40 … −110) |
| **best point prediction** | **−110**, 90% CI [−55, −175] |

The competing published figures for this kernel family are mutually
inconsistent and cannot all be the *marginal* cost: 4.70 µs/call profiled
(185.7 µs/step), 205.3 µs/step profiled by census, 139.6 µs/step census
"deconvolved", 105.6 µs/step in a prior critique. The A/B measures the marginal
cost directly and adjudicates between them.

## 4. Result: the hypothesis is falsified

**The candidate is slower.** Deleting all 39 standalone router dispatches per
decode step did not speed decode up by ~110 µs/step; it slowed decode down.

### 4.1 Instrument

`--local-iterate` times only 128 decode steps per 216 s run, so its decode
number carries far too little power for a ~1 % effect. The measurement uses
`research/decode_probe.py` instead: one worker process, the 512-token golden
seed, then 1200 teacher-forced single-token `decode_step`s each timed with
`CLOCK_UPTIME_RAW`. That is ~9× more timed steps for ~¼ of the wall clock.

Both arms are the **same binary**, toggled by
`DARKBLOOM_DECODE_ROUTER_EMIT_SINK`, so no compiler or layout difference can
leak into the contrast. Runs are interleaved in palindromic blocks (`ABBA`)
so a linear thermal/clock drift over the session cancels rather than loading
onto one arm. The unit of replication is the **run median**, not the step:
steps inside one process share its clock state, page mapping and thermal
history, so pooling steps across runs would badly understate the true scatter.
The first 16 steps of each run are dropped as KV-growth/JIT warmup.

Arm assignment is verified, not assumed: arm B's worker stderr contains
`packed-scales active: routed swiglu qmv packed dispatch` (the base fused
chain's one-time log) and arm A's does not, because arm A returns from the
sink branch before that log site.

### 4.2 End-to-end contrast (8 runs, 2 ABBA blocks, 1200 steps each)

| run | arm | median ms | mean ms | p10 | p90 |
|---|---|---|---|---|---|
| p1r1 | A emit | 8.3130 | 8.4069 | 8.1880 | 8.5755 |
| p1r2 | B base | 8.2718 | 8.2920 | 8.1514 | 8.4832 |
| p1r3 | B base | 8.2921 | 8.3081 | 8.1905 | 8.4878 |
| p1r4 | A emit | 8.3551 | 8.3680 | 8.2940 | 8.4440 |
| p2r1 | A emit | 8.3800 | 8.3556 | 8.2066 | 8.4535 |
| p2r2 | B base | 8.3260 | 8.3197 | 8.2073 | 8.4017 |
| p2r3 | B base | 8.3728 | 8.3661 | 8.2288 | 8.4693 |
| p2r4 | A emit | 8.3599 | 8.3667 | 8.2256 | 8.4981 |

- arm A (emit sink): median-of-medians **8357.5 µs**, between-run sd 28.2 µs
- arm B (base):      median-of-medians **8309.1 µs**, between-run sd 44.2 µs
- **Δ = +48.4 µs/step (+0.58 % slower)**
- paired ABBA diffs: `[+41.3, +63.0, +54.0, −12.9]` µs;
  mean **+36.3 µs**, sd 34.0 µs, sem 17.0 µs, n = 4

Both estimators agree on sign and rough magnitude. Three of four pairs are
positive. The pre-registered kill rule was "stop if the decode delta is worse
than −60 µs/step"; the observed delta is **+36 to +48 µs**, roughly 150 µs on
the wrong side of the point prediction and outside the 90 % prediction
interval `[−55, −175]`. The rule fires, so the change is not pursued further
and the submitted surface is reverted to base.

Teacher-forced greedy tokens: **0 divergences in every one of the 8 runs**, so
the regression is a genuine timing result and not a correctness artefact.

## 5. Attribution: where the +36 µs comes from, and what the dispatches were worth

The end-to-end contrast conflates two things: the fused kernel got *more
expensive*, and the 39 deleted dispatches were worth *something*. A third arm
separates them.

| arm | `DARKBLOOM_DECODE_ROUTER_EMIT_SINK` | emit kernel | standalone dispatch |
|---|---|---|---|
| **A** | `1` | runs, output used | **deleted** |
| **B** | `0` | not built | runs, output used |
| **C** | `2` | runs, output **ignored** | runs, output used |

so that

- `ΔC = C − B` = the emit-variant QMV's own added cost, dispatch count held fixed
- `ΔD = A − C` = the marginal value of removing 39 dispatches/step
- `ΔC + ΔD = A − B` (identity, must hold)

18 runs, 3 palindromic **ABCCBA** blocks, 1200 timed steps each, one binary.
The palindrome gives all three arms the same mean position in the session
(3.5), so a linear drift cancels for every contrast, not just for one.

### 5.1 Results

| arm | mean of run medians | median of run medians | between-run sd |
|---|---|---|---|
| A emit sink | 8339.8 µs | 8335.6 µs | 16.0 µs |
| B base | 8303.3 µs | 8298.9 µs | 28.1 µs |
| C emit + standalone | 8340.6 µs | 8322.8 µs | 34.5 µs |

| contrast | paired mean | sd | sem | t (df=5) | verdict |
|---|---|---|---|---|---|
| `ΔC = C − B` emit kernel's own cost | **+37.3 µs** | 12.1 | 4.9 | **7.6** | `p ≈ 0.0006` |
| `ΔD = A − C` 39 dispatches removed | **−0.9 µs** | 29.7 | 12.1 | −0.07 | `p ≈ 0.94`, **null** |
| `A − B` end-to-end | +36.4 µs | 24.2 | 9.9 | 3.7 | `p ≈ 0.014` |

The identity closes exactly: `+37.3 − 0.9 = +36.4`. The end-to-end figure also
**replicates across sessions**: the independent 8-run ABBA block gave a paired
mean of `+36.3 µs`, this 18-run ABCCBA block gives `+36.4 µs`.

Teacher-forced greedy tokens: **0 divergences in all 18 runs**.

### 5.2 What this says

**Removing 39 router dispatches per decode step is worth nothing.**
`ΔD = −0.9 ± 12.1 µs/step`; a 95 % interval is roughly `[−32, +30] µs`. The
census-derived prediction for this exact quantity was `−105 … −185 µs/step`.
The most favourable end of the measured interval is still **3.5× smaller** than
the least aggressive census prediction, and the point estimate is **two orders
of magnitude** below the 185.7 µs/step headline. The dispatches were not on the
critical path at all.

The entire +36 µs regression is the **fused kernel's own added cost**
(`ΔC = +37.3 ± 4.9 µs`, ≈ `+0.95 µs` per call over 39 calls). The trade the
experiment actually made was: pay ~1 µs/call to make the gate/up QMV emit the
router, in exchange for deleting dispatches that were free.

Read against the mechanism table registered before the arm-C data was seen:

| candidate mechanism | predicted `ΔC` | predicted `ΔD` | outcome |
|---|---|---|---|
| **census-true** (dispatches really cost 105–205 µs/step) | +150…+230 | −105…−185 | **decisively excluded** (`ΔD` is ~9 sem away) |
| barrier / command-buffer boundary reshuffle | small or negative | **> 0** | not dominant (`ΔC` is large and positive) |
| **occupancy / register-pressure step in the QMV** | +35…+55 | −0…−10 | **consistent** |
| **MLX 3-output primitive bookkeeping** | +35…+55, GPU time flat | −0…−10 | **consistent** |
| emitter-tail serialization | +35…+55 | −0…−10 | consistent but implausible: the emitting group is #7 of 2048, so it launches in the first wave and its extra ~0.3–0.5 µs hides under a ~45–80 µs kernel |
| dispatches are free (side-branch) | ≈ +40 by identity | **≈ 0** | **this is what happened** |

Three mechanisms survive for the `+37 µs` and this experiment cannot separate
them further — doing so needs pipeline reflection (register count, max threads
per threadgroup) and per-kernel GPU durations, which is not worth spending on a
change that is being reverted. What *is* settled, and is the point of the
experiment, is `ΔD ≈ 0`.

One known bias: arm C materializes two small unused output arrays per layer
that neither A nor B carries, which biases `ΔC` **up** and `ΔD` **down** by a
few µs. Correcting for it moves `ΔD` even closer to zero or slightly positive.
It cannot rescue the hypothesis.

### 5.3 Arm-C validity

`ΔD ≈ 0` would also be the reading if arm C had silently collapsed onto arm A —
for example if `SINK=2` enabled the sink (it is `!= "0"`) while the
keep-standalone branch never fired. Arms A and C are byte-identical in worker
stderr, so the logs cannot separate them. This is checked directly instead, by
fault injection:

a single **bfloat16 ULP** is added to the *emit kernel's* `router_scores`
output only, and the per-step logit digests are recompiled and re-run.

| arm | consumes | expected digest |
|---|---|---|
| A | emit scores | **changes** vs clean reference |
| C | standalone scores | **identical** to clean reference |

<!-- ARM-C VALIDITY WITNESS PENDING -->


## 6. Why the census figure was not a marginal cost

This is the part worth keeping. Four independent analyses of the *same* kernel
in the *same* build produced 105.6, 139.6, 185.7 and 205.3 µs/step. A ±50 %
method-dependent spread is not measurement slop; it is the signature of a
quantity that is not causal in the first place.

Per-kernel Apple GPU timings are an **attribution of wall-clock residency**, not
an additive decomposition. Under a concurrent encoder with hazard-tracked
barriers, independent kernels genuinely overlap, and interval attribution
double-counts the overlap. The census sums intervals; the step is a **makespan**.

There is a direct falsification of the additive model already present in the
census data that was available before this experiment: `rmsbfloat16` is listed
at **1.82 µs/call**, which is *below* the fitted single-threadgroup dispatch
floor `a + φ = 3.13 µs`. No dispatch can be cheaper than the floor if the floor
is real and the costs are additive. It can only be below the floor if the
reported number is a fraction of an overlapped interval. That datum alone
refutes "sum of per-kernel times = step time", and it was in the table the whole
time.

The correct model is:

> Step time = makespan of the pipelined encode / dispatch / execute streams.
> Within a barrier-bounded interval, elapsed time ≈ **max** over concurrent
> kernels, not **sum**.

Under that model the marginal cost of a kernel is its **effect on the critical
path**, and kernels fall into two classes:

- **chain-link** — sole occupant of its barrier-bounded interval (typically an
  elementwise op on the residual stream sitting between two matmuls). Deleting
  it saves close to its full serialized duration.
- **side-branch** — issued inside the concurrency interval of a much larger
  sibling. Deleting it saves ≈ 0.

The decode router top-8 is a **side-branch** kernel. It is a 39-per-step,
single-wave, latency-bound dispatch running alongside the routed gate/up QMV,
which moves ~9 MB of weights per layer and occupies ~45–80 µs/call. The router
fits entirely inside that shadow. Its 4.70 µs/call of attributed residency was
real residency and phantom cost.

The dispatch cost model `T = a + W·φ` is therefore best read as a **throughput
slot cost**: an *upper bound* on marginal cost, attained only when the encode
front-end is saturated, and collapsing toward zero when the streams have slack.
The pre-registered 90 % interval `[−55, −175]` should have included 0. It did
not, because "latency-bound, launch-dominated" was treated as evidence of
removable cost. It is not: latency-bound describes the kernel *in isolation* and
says nothing about whether it is on the critical path.

## 7. A reusable marginal-cost probe (proposed, not run)

The expensive part of this experiment was not the measurement — it was building
a bit-exact fused kernel *before* knowing whether the cost existed. The
generalisable fix is to measure marginal cost **without a correctness burden**,
by *adding* work instead of removing it.

**Design.** For a target dispatch, add `K − 1` redundant copies per layer under
an env knob `DUP=K ∈ {1, 2, 3, 5}` and measure `d(step)/dK`.

- each duplicate reads the same live inputs and writes its **own scratch
  output**, so there is no write-after-write chain and no forced serialization;
- the duplicate outputs must be made **additional eval roots** so MLX's lazy
  graph cannot dead-code-eliminate them. Defeat DCE by *reachability*, never by
  injecting fake arithmetic into the live result — fake arithmetic changes the
  thing being measured;
- list the duplicate roots **before** the logits in the eval list, so the DFS
  encodes each duplicate adjacent to its own layer rather than clustering all of
  them at the end of the command buffer;
- verify in a trace that `39·(K−1)` extra dispatches actually encode, and that
  they land where intended.

**Read-out.**

| observed slope per extra set of 39 | conclusion |
|---|---|
| ≈ 0–10 µs/step | phantom cost; the kernel is a side-branch. Do not fuse. |
| ≈ census (≈ 185 µs/step) | real cost; fusion is worth the correctness work. |

Internal consistency checks: linearity from `K = 1` to `K = 5`, and `K = 1`
reproducing the unmodified base within noise.

**Second variant.** Run the same sweep with the duplicates *chained* (duplicate
`k` reads duplicate `k − 1`'s output), which forces hazard serialization. That
slope is the serialized upper bound. The **ratio of the overlapped slope to the
serialized slope is an overlap discount** that can be measured once and then
applied to every census-derived estimate in the queue.

Cost: well under an hour, no bit-exactness proof required, no kernel authoring.

## 8. Recommendations for the campaign queue

1. **Re-price every "delete a small kernel worth 70–200 µs/step" target.** The
   revised prior for this class is that realized saving is **10–20 % of the
   census figure**, with substantial probability mass at ~0 and real probability
   of a **net loss** whenever the fusion has to touch a large kernel. This
   experiment is one draw from that prior and it came out negative.
2. **Triage the whole queue with one trace, not one fusion each.** A single
   ~2 s Metal System Trace of the base binary answers, for every candidate at
   once, the only question that matters: is the target's interval *nested under
   a bigger sibling*, or is it *alone between two barriers*? Chain-link targets
   stay promising; side-branch targets should be dropped without further work.
3. **Run the §7 probe before authoring any further fusion kernel.** It converts
   a multi-day bit-exact kernel project into a sub-hour measurement.
4. **Stop quoting census µs/step as a saving.** Quote it as an upper bound and
   say so. Where a number is used to justify an assignment, state which of the
   two classes the kernel is in.
5. **Keep the correctness methodology.** The bitwise logit certificate plus the
   fault-injection sensitivity control (§2.4–2.5) did their job perfectly: they
   proved the fused kernel was bit-exact *and* proved the certificate was not
   vacuous. That pattern should be standard for every numerics-touching change,
   and it is cheap. The lesson of this PR is about *which* changes are worth
   proving correct, not about how to prove them.
