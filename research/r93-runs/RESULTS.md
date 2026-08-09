# R93-A/B — Calibrating the ranked M5 receipt channel

Assignment `maple-r93-a-m5-receipt-channel`, revision `r93-a-rev1`, PR #496.
Base `codex/mlxfast-maple-20260804-advisor` @ `17a4bad4`.

Everything below is measured on the **official M5 receipt channel** unless a
line explicitly says M4 Pro. Local M4 Pro numbers are used only to design the
experiment and to explain mechanism, never as evidence about M5 timing.

> **Status: draft in progress.** Sections marked *(pending)* are filled in as
> official receipts land. The submission ledger at the bottom is authoritative
> for what has actually been measured.

---

## 0. What this experiment is for

Every ranked decision we make is a comparison of two numbers that came out of
the M5 receipt channel. We have been treating that channel as if a difference
of a few tenths of a percent were meaningful. Nobody had measured its
candidate-side noise directly, and nobody had priced one GPU dispatch on the
ranked machine. Without those two numbers we cannot say whether a proposed
optimisation is worth a submission slot, and we cannot convert a local M4
measurement into an expected M5 outcome.

Two arms:

- **Arm A — true null.** Submit several candidates that are *machine-code
  identical* and differ only by a trailing Swift comment. Any spread in their
  reported timings is pure channel noise. This gives `sigma(cand_dec)` and
  `sigma(cand_pre)` from our own repeats rather than from other people's
  near-duplicate submissions.
- **Arm B — dispatch ladder.** Submit candidates that add a known number `K` of
  extra, bit-exact, decode-only GPU dispatches, carried as a **source
  constant** so the ranked host actually compiles them. Regressing decode time
  on `K` prices one M5 dispatch in microseconds. Prefill is untouched and acts
  as an internal control.

---

## 1. Channel facts discovered before any measurement

These are properties of the submission channel itself and constrain every
future study.

### 1.1 The channel is strictly serial — one submission in flight

`mlxfast submit` refuses a second concurrent dispatch:

```json
{"error":{"code":"conflict","message":"account already has 1 submission(s) in flight for this benchmark (limit 1)"}}
```

The refusal does **not** consume a slot, so it is safe to probe. Measured
turnaround for null-1: queued 02:56:02Z, terminal 03:16:50Z = **20.8 minutes**,
of which the benchmark itself is only ~52 s of wall clock (39 s correctness
plus 45 s timed). The remaining ~20 minutes is queue, thermal gating and
harness overhead that we cannot compress.

**Consequence:** an *n*-receipt study costs about `21n` minutes of exclusive
calendar time for the whole campaign, not just for the student running it.
An 8-receipt study is ~2.8 hours during which no other student can submit.
This is the single most important input to the cadence policy in
[`cadence-policy.md`](cadence-policy.md).

### 1.2 The injected-dispatch cost is convex on M4 Pro, and the low-K region is free

See [`knee-results.md`](knee-results.md) for the full sweep. On this M4 Pro,
120 teacher-forced steps per point, TG=8, zero token divergences everywhere:

| K | mean ms | segment slope (us/dispatch) |
|---|---|---|
| 0 | 8.223 | |
| 240 | 8.131 | -0.43 |
| 480 | 8.125 | -0.03 |
| 800 | 8.456 | +0.58 |
| 1200 | 8.597 | +0.73 |
| 1600 | 9.409 | +1.98 |
| 2400 | 11.344 | +2.36 |
| 0 (repeat) | 8.218 | open/close controls agree to 0.02 % |

The first few hundred injected dispatches are **free**, and K=240 is even
marginally *faster* than K=0, reproducibly.

A command-buffer-split control (disable MLX's `MLX_MAX_OPS_PER_BUFFER` and
`MLX_MAX_MB_PER_BUFFER` limits) moves nothing, so buffer packing is not the
cause. The surviving explanation is CPU/GPU overlap: a single-token decode step
spends on the order of a millisecond building and encoding the MLX graph on the
CPU, and the injected chain is hazard-free — it binds only its own
control/prev/sink buffers, never a model tensor, so MLX inserts no `MTLFence`
wait — therefore a few hundred extra GPU dispatches finish inside that CPU
shadow at no cost.

**Consequence for interpreting Arm B:** the empty ladder prices a *hazard-free*
dispatch. That is a **lower bound** on the value of deleting a real, serialising
dispatch from the scored path. It is not an upper bound and must not be read as
"dispatches are cheap, stop removing them".

### 1.3 The historical M5 ladder has no free region

Three M5 receipts from the 2026-08-05 solver tree (TG=8) with the same
injection mechanism:

| K | submission | cand decode us | cand prefill us | baseline decode us |
|---|---|---|---|---|
| 0 | `c3ce66ec` | 5046.44 | 191.308 | 13899.53 |
| 100 | `57306132` | 5232.25 | 190.698 | 13840.31 |
| 400 | `0411779d` | 5835.83 | 190.657 | 13919.36 |

OLS: **1.9823 us/dispatch**, intercept 5041.12 us, linear from K=0 with no free
region. Prefill control spread 0.341 %.

That is a qualitative contradiction with the current-tree M4 shape, and it is
why Arm B is worth running on M5 rather than extrapolated from M4. It is also
consistent with the mechanism in 1.2: a machine with a shorter CPU shadow
relative to its GPU sees the injected chain immediately.

### 1.4 Design change: rungs moved to K in {240, 800, 1600}

The brief proposed `K` in {40, 120, 240}. All three of those sit inside the
free region measured in 1.2, so on the M4-shaped hypothesis all three would
return the same number and the ladder would have no leverage.

The chosen rungs make K=240 a **~33 sigma discriminator**: the
historical-linear hypothesis predicts +476 us (+9.7 %) at K=240, the M4-shape
hypothesis predicts ~0, and the channel noise floor is ~0.29 %. Whichever way
K=240 lands, we learn which machine model is right.

Floor safety at the worst case (1.98 us/dispatch against a session baseline of
13 819 us) predicts decode speedups of 2.57 / 2.13 / 1.71 for K = 240 / 800 /
1600 — all far above the 0.95 hard floor. Prefill is untouched.

### 1.5 The rung is carried by a source constant, not the environment

The knee sweep drove `K` through the environment, which the ranked host never
sets. Before spending official slots we rebuilt with the rung compiled in and
ran the probe with **no injection environment at all**
([`verify-source-constant.log`](verify-source-constant.log)):

| source constant | worker sha256 | median ms | tokens |
|---|---|---|---|
| K=2400, TG=8 | `2ad01385…` | 11.276 | 0 divergences |
| K=0, TG=160 (base) | `53fae224…` | 8.199 | 0 divergences |
| K=240, TG=8 | `d98dfe80…` | 8.136 | 0 divergences |

Source-constant K=2400 reproduces the env-driven K=2400 point to 0.15 %. The
ladder therefore measures what the ranked host will actually compile.

---

## 2. Arm A — candidate-side channel noise *(pending, n growing)*

Method: N submissions whose scored source differs only in a trailing
`// senpai-r93-null-<n>` comment. Statistic: sample standard deviation of `decode_seconds_per_token`
and `prefill_seconds_per_token` across the N candidate receipts, expressed as a
percentage of the mean, with a chi-square confidence interval, compared against
the corpus-derived upper bounds of **0.2924 % decode** and **0.2573 % prefill**.

### 2.1 The nulls really are machine-code identical

The whole arm rests on the claim that a trailing comment changes nothing that
executes, so this was verified rather than assumed
([`identity_check.sh`](identity_check.sh)). Four consecutive release builds of
`mlxfast-runtime-worker` from the same scratch directory:

| build | source state | sha256 |
|---|---|---|
| A | as submitted (`// senpai-r93-null-4`) | `d2efb5f4a7fd…` |
| B | untouched, `touch`ed to force a rebuild | `d2efb5f4a7fd…` |
| C | marker rewritten to `// senpai-r93-identity-probe` | `d2efb5f4a7fd…` |
| D | marker restored | `d2efb5f4a7fd…` |

All four are byte-identical. B==A establishes that the build itself is
deterministic, which is what makes C==A meaningful: the comment edit is not
merely *tolerated*, it leaves no trace in the binary at all. The ranked host
compiles from the submitted source, so the same argument transfers.

Two honest limits on that. First, this is the M4 toolchain; the ranked host
compiles independently and the determinism control cannot be run there. Second,
the K=0/TG=160 hash recorded in section 1 during the knee sweep (`53fae224…`)
does *not* equal today's `d2efb5f4…`, even though `git diff` against `BASE_SHA`
confirms the source is identical apart from the two trailing marker lines.
Cross-*session* build hashes are therefore not comparable — most likely a
clean-versus-incremental scratch-directory artifact. Section 1's comparison is
unaffected because those three builds were made back to back in one session,
but no cross-session hash equality should be read from this report.

*(table and CI pending)*

## 3. Minimum resolvable decode difference *(pending)*

Derived from the Arm A sigma: for a paired two-arm comparison with `n`
receipts per arm, `se = sigma * sqrt(2/n)` and the 95 % detectable difference
is `t(0.975, 2n-2) * se`, reported in both percent and microseconds per step.

*(table for n = 4, 6, 8 pending)*

## 4. Arm B — M5 microseconds per dispatch *(first rung landed)*

**The M4 free region does not exist on M5. The discriminator fired cleanly.**

| quantity | value |
|---|---|
| null mean candidate decode (n=2) | 4912.670 us |
| ladder-K240 candidate decode | 5506.517 us |
| difference | **+593.85 us (+12.09 %)** |
| implied cost | **2.474 us per dispatch** |
| predicted by M4 shape | ~0 us (K=240 sits inside the M4 free region) |
| predicted by historical M5 OLS (1.9823 us/disp) | +475.8 us |
| null-to-null spread, same quantity | 37.1 us |

The observed step is **16x the entire null-to-null spread** and about 23 sigma
on the n=2 sigma estimate. There is no reading of this data in which K=240 is
free on M5.

So the two machines disagree qualitatively, exactly as section 1.3 warned:

- M4 Pro absorbs the first ~480 hazard-free dispatches at zero cost and only
  reaches ~2 us/dispatch beyond K~1600.
- M5 charges ~2.5 us/dispatch from K=0 with no free region at all.

This is the mechanism from section 1.2 seen from the other side. The free
region on M4 is CPU shadow: the injected GPU chain hides under the ~1 ms of
CPU-side MLX graph building per decode step. The ranked M5 is a faster GPU
behind a faster CPU, and on that machine the shadow is not long enough to hide
even 240 dispatches.

**Practical consequence for the campaign:** on the ranked machine a saved GPU
dispatch is worth ~2.5 us of decode time, and that is a *lower bound* because
the injected kernels are hazard-free while a real removed dispatch usually also
removes a fence wait. At a session baseline of ~13 830 us and a candidate of
~4913 us, removing 100 real dispatches per token is worth roughly 0.25 ms/token,
i.e. about 5 % of candidate decode. Dispatch-count reduction is therefore a
first-class optimisation target on M5 even though local M4 iteration will
report it as worthless.

Our measured 2.474 us/dispatch is ~25 % above the 1.9823 us/dispatch OLS slope
from the 2026-08-05 historical receipts. Both are the same order and both
exclude a free region; the remaining rungs (K=800, K=1600) will say whether the
current-tree M5 response is linear and will tighten the slope CI.

Prefill control across the three receipts so far: 187.637 / 187.734 /
187.888 us, a total spread of 0.13 %. The ladder moves decode only, as designed.

### 4.1 Second design change: third rung moved from K=1600 down to K=60

The rungs were originally re-planned to {240, 800, 1600} because on M4 anything
below ~480 was free and would have carried no information (section 1.4). The
K=240 receipt destroys that premise for the ranked machine: M5 is linear from
K=0, so a low rung is informative again.

K=1600 is therefore dropped and replaced by **K=60**. Reasoning:

- Nobody will ever remove 1600 dispatches from the decode path. The number this
  experiment produces will be applied at the scale of tens of dispatches, so the
  slope needs to be validated *there*, not extrapolated down to it from 1600.
- {60, 240, 800} still spans a 13x range in K, which is ample lever arm for the
  slope and for a linearity test, and combines with the K=0 null anchor to give
  four points.
- Predicted step at K=60 is +148 us (+3.0 %) against a null-to-null spread of
  37 us, i.e. roughly 5 sigma. Comfortably resolvable without being a waste of
  a slot on an already-obvious effect.

Final rung set: **K = 60, 240, 800** (plus K=0 from the nulls).

*(K=800 and K=60 rungs, OLS slope with CI, and the formal linearity check are
still pending.)*

### 4.2 What the slope is worth: the decode dispatch census

A microseconds-per-dispatch number is only actionable if we know how many
dispatches the scored decode step actually issues. That count was derived
statically from the runtime source at BASE_SHA `17a4bad4`, evaluating every
branch at its *default* configuration (no environment overrides), because the
ranked M5 run sets no `DARKBLOOM_*` or `laguna*` variables.

**Result: about 404 GPU dispatches per decoded token** (range 395-440 once the
optional paths below are admitted).

| Site | Per layer | Layers | Dispatches |
|---|---|---|---|
| input RMSNorm | 1 | 40 | 40 |
| `lagunaDecodeNVFP4QKVR1` (fused Q/K/V) | 1 | 40 | 40 |
| `lagunaGateSoftplus` | 1 | 40 | 40 |
| `lagunaSliding/FullFusedAttention` | 1 | 40 | 40 |
| `lagunaGatedAffineOProjNVFP4` | 1 | 40 | 40 |
| dense MLP (layer 0 only) | 3 | 1 | 3 |
| `lagunaResidualRMSNormRouter` | 1 | 39 | 39 |
| `lagunaDecodeRouterTop8` | 1 | 39 | 39 |
| `lagunaRoutedSwiGLUQMVPackedTop8` | 1 | 39 | 39 |
| `lagunaSharedSwiGLUQMV` | 1 | 39 | 39 |
| `lagunaRoutedSharedDownResidual` | 1 | 39 | 39 |
| embed + both RoPE angle rows (fused) | - | - | 1 |
| decode mask | - | - | 0 |
| final norm | - | - | 1 |
| lm head (3-level screen + refinement) | - | - | 4 |
| argmax | - | - | 0 |
| **total** | | | **404** |

Structural facts behind the table (`LagunaConfig.swift:15`,
`LagunaRuntimeModel.swift`, `LagunaLmHeadPrune.swift:924`):

- 40 hidden layers; layer 0 dense, layers 1-39 sparse MoE, so attention costs
  5 dispatches per layer and the sparse tail costs 5 more (10 per layer, 8 for
  layer 0).
- `i % 4 == 0` selects full attention (10 layers, 48 heads); the other 30 are
  sliding-window (64 heads, window 512). Both are single fused dispatches, so
  the split does not change the count.
- `lagunaNativeAffineNVFP4From` defaults to `"0"`, so **all 40 layers** take the
  NVFP4 g16 QKV + o_proj path. The group-32-only fused norm+QKV kernel declines
  everywhere, which is why the input RMSNorm survives as its own dispatch on
  every layer.
- `lagunaRoPEAngleAtlasEnabled` defaults ON, which is what folds embedding and
  both RoPE angle rows into a single dispatch.
- `makeMask` returns `.none` at n == 1, so decode issues no mask kernel.
- MoE always takes 8 of 256 routed experts plus the shared expert, and
  `normTopkProb` is always true.

Honest bounding caveats, all of which move the number *up*:

- A KV-growth reallocation step fires roughly once every 128 positions and adds
  an estimated 20-30 dispatches on that step only.
- If the sliding-window `fusedRingPrepare()` fast path ever declines, the 30
  sliding layers fall back to a 2-3 dispatch sequence: +60 to +90.
- A non-fp32 `eScoreCorrectionBias` would add one cast per sparse layer: +39.
- `compile(...)` call sites exist in the runtime but are unreachable at
  defaults, so none of them collapse the count.

**Consequence.** At the K=240 slope of 2.474 us per hazard-free dispatch,
404 x 2.474 us = **1.00 ms**, against a candidate decode of 4913 us per step:

> roughly **20 % of ranked M5 decode time is per-dispatch fixed overhead**, not
> arithmetic.

Two qualifications that keep this from being oversold:

1. 2.474 us prices a *hazard-free* dispatch (section 1.2's hazard test: the
   injected kernels bind only their own control/prev/sink buffers, so MLX
   inserts no `MTLFence` between them). A real dispatch that participates in the
   dependency graph costs at least this much, so 1.00 ms is a **lower bound** on
   the fixed overhead, and removing one real dispatch should save **at least**
   2.474 us.
2. The slope is currently from a single rung pair. The K=800 and K=60 receipts
   will give it a confidence interval; the 20 % figure should be restated with
   that CI once they land.

Two related facts worth recording for whoever acts on this:

- MLX caps a command buffer at `max_ops_per_buffer_ = 50` on M5 Max
  (architecture name ending in `'s'`), so 404 dispatches is **8-9 command
  buffers per decoded token**. `lagunaDecodeAsyncStage` defaults to
  `"at:0,1,7,15,23,31,39"`, giving 7 `asyncEval` fire points per step. **Those
  are not overhead and must not be attacked** - see section 8.2, rejection 3:
  they add zero dispatches and are a measured 0.9 ms *win*.
- An exact dispatch counter already exists in the vendored MLX
  (`CommandEncoder::buffer_ops_`, `Vendor/mlx-swift/.../backend/metal/device.h:113`,
  incremented only at `device.cpp:381` and `:389`), but `device.cpp/.h` are
  **not** in `editablePaths`, so it can be used for local research only and
  never shipped. On the ranked M5 the cheapest legitimate confirmation of which
  branches fire is `DARKBLOOM_TRACE_FUSION=1`, which prints one stderr line the
  first time each fused site is taken (it is a set, not a counter).

## 5. Submission cadence policy

Written up in full in [`cadence-policy.md`](cadence-policy.md).

## 6. Re-derived #137 M4 to M5 transfer factor

Written up in full in [`pr137-transfer-factor.md`](pr137-transfer-factor.md).
Headline: using **raw paired timings** rather than scores, the M5 effect of the
#137 lm-head cascade is **+16.590 us = +0.3375 %** (drift-cancelling form
+0.3795 %), against a corrected balanced M4 census of **-64.5 us = -0.785 %**,
giving a transfer factor of **T ~ -0.48** (range -0.43 to -0.49). This replaces
the score-based estimate of -0.40 +/- 0.24. The brief's suggested pairing of
"+0.803 % vs `7ce1262d`" is invalid because those two receipts are 49 hours
apart.

---

## 7. Submission ledger

| # | marker | submission id | K | TG | status | all gates | W&B |
|---|---|---|---|---|---|---|---|
| 1 | null-1 | `25e1f18e-ef83-491f-8a65-8944765bfe46` | 0 | 160 | rejected (score did not improve best) | green | [`3szqrztf`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/3szqrztf) |
| 2 | null-2 | `d11026c9-25c5-498c-936f-ed3db3335c30` | 0 | 160 | rejected (score did not improve best) | green | [`0doaq0w0`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/0doaq0w0) |
| 3 | ladder-K240 | `99309c61-2b7e-4ce8-bb74-52bd3da8a03c` | 240 | 8 | rejected (score did not improve best) | green | [`fpi2ynyl`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/fpi2ynyl) |
| 4 | null-3 | `05dd8bbf-c436-447c-99a8-8024d0fc023f` | 0 | 160 | rejected (score did not improve best) | green | [`fvm3v67i`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/fvm3v67i) |
| 5 | ladder-K800 | `f8719c48-8df6-4570-abf1-1c9a369c64e0` | 800 | 8 | rejected (score did not improve best) | green | [`qaempae6`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/qaempae6) |

"all gates green" means `passed_correctness`, both speedup floor verdicts,
GPQA TTFT 9/9 and semantic GPQA 9/9, with `max_abs_diff = 0` over 1344 checked
steps. A `rejected` status with the reason "score did not improve current best"
is the expected and correct outcome for a null or a deliberately slowed ladder
rung; it is a ranking statement, not a correctness statement.

## 8. Follow-up: what the 2.474 us actually buys, and what it does not

Sections 4 and 4.2 establish a price and a count. This section audits what can
actually be *removed*, done independently against the source at BASE_SHA. It is
deliberately separated from the measurement above because none of it is measured
by this experiment - it is the shortlist R93 exists to enable, not a result of
R93.

The most important thing here is the rejection list. The naive reading of
"404 dispatches x 2.474 us = 1.00 ms" is that any fusion is free money. That
reading is wrong, and the code already contains the counter-example.

### 8.1 Independent confirmation of the census

The audit reproduced 404 exactly from source, by the same decomposition: 200
attention + 195 MoE + 3 layer-0 dense + 6 non-layer. It also confirmed the three
structural claims carrying the most weight: decode fused attention really does
absorb QK-norm, RoPE, KV-append and SDPA into one dispatch
(`LagunaRuntimeModel.swift:6077`, `:6103`); decode masks really are 0-dispatch
at L == 1; and the router correction-bias cast is already sunk into the top-8
kernel (`LagunaRuntimeLayers.swift:805-809`), so the "+39 if non-fp32" caveat in
section 4.2 does not fire.

One documentation defect found: `LagunaRuntimeModel.swift:610-611` describes the
fused embed+angle-atlas kernel as "default OFF (-0.23 %)", but `:596-605` shows
it default **ON** since the 2026-08-02 r=1 re-sweep. Doc rot, not a census error
- the census read the code, not the comment.

### 8.2 Rejected, with reasons (the valuable half)

1. **Fuse the 40 input RMSNorms into the NVFP4 QKV kernel.** This is the obvious
   40-dispatch, ~99 us idea, and it has **already been implemented and then
   removed after re-measuring at +2.7 %**
   (`LagunaRuntimeModel.swift:5856-5860`). Every threadgroup in the fused kernel
   must re-read the 2048-wide row and recompute the RMS reduction, so the
   redundant arithmetic costs more than the launch it saves. The surviving fused
   norm+QKV path is guarded to INT8 g32 (`:5839-5845`), which never fires at the
   default `lagunaNativeAffineNVFP4From=0`.

   **This is the discipline the 2.474 us number needs.** Dispatch count is one
   axis; a fusion that duplicates work across threadgroups can lose on the other
   axis by more than it wins on this one. The price tag says how much a removed
   dispatch is *worth*, not that removing it is *cheap*.

2. **Switch QKV to INT8 g32 to reach that fused path.** Permitted by the
   quantization envelope, but it roughly doubles QKV weight bytes (~+10 MB per
   layer, ~+20-25 us of bandwidth) to save ~5 us of dispatch. Net loser, and it
   explains why NVFP4-everywhere is the default.

3. **Reduce the `asyncEval` sync points.** I had flagged the 7 fire points as a
   possible cost in section 4.2. That was wrong and is corrected there.
   `asyncEval` adds **zero** GPU dispatches, cache rows, dtype boundaries or
   tokens - it only enqueues already-constructed work earlier, so every schedule
   is bit-exact and the choice is purely a measurement. Verified directly at
   `LagunaRuntimeModel.swift:722-745` (`notes/52`, two Latin squares, 66 runs,
   66/66 `passed_correctness`): `off` is **10.3735 ms** against **9.4533 ms**
   for the older `ladder8` 5-fire schedule, so overlap alone was worth +9.7 %,
   and the current default is a further ~1.7 % on top of `ladder8`. Fewer fires
   is strictly worse, and a *lone* fire at layer 1 is the worst schedule tested
   (0.9476). Keep `at:0,1,7,15,23,31,39`. Do not attack.

4. **Collapse the 4-dispatch lm-head screen back to one dispatch.** The stock
   single dispatch reads the full 411 MB BF16 `[100352, 2048]` row set (~800 us);
   the 3-level screen reads ~110 MB. Break-even is +3 dispatches = 7.4 us against
   500-600 us of bandwidth saved. Overwhelmingly keep the 4 dispatches. This is
   the cleanest illustration that minimising dispatch count is not the objective.

5. **A whole-step or whole-MoE megakernel.** router -> QMV -> down needs
   device-wide ordering and Metal offers no intra-dispatch global sync.

6. **Further cross-layer hoisting.** Exhausted. Embedding and both RoPE angle
   rows are already one fused dispatch (`:8913-8926`), angle tables are shared
   across all 40 layers, masks are free, and all fused banks and atlases are
   built at load in `prepareFusedRuntimeWeights` (`:9152+`). Every remaining
   per-layer dispatch consumes layer-specific weights or state.

### 8.3 Surviving candidates, ranked

Nominal us uses 2.474 us/dispatch and is an **average**, not a critical-path
marginal cost - see 8.4.

| # | Idea | Saved | Nominal us | Risk | Size |
|---|---|---|---|---|---|
| A | Fold the per-head INT8-g32 gate QMV into the NVFP4 QKV dispatch, deferring softplus to the o_proj kernel | **40** | 99 (-2.0 %) | med (see caveat) | M |
| B | Delete `lagunaDecodeRouterTop8`: the packed QMV already re-derives top-8 in-dispatch, so have it also emit (inds, weights) | **39** | 96 (-2.0 %) | med | S/M |
| C | Merge the shared-expert gate/up QMV into the routed packed top-8 QMV | **39** | 96 (-2.0 %) | med | M |
| D | Fold lm-head argmax stage-1 into the coarse kernel | 1 | 2.5 | low | S |
| E | Fold the final RMSNorm into layer-39 down-residual or lm-head coarse | 1 | 2.5 | high | M |

**A is the recommended first experiment.** Crucially it is *not* rejection 1 in
disguise: it does not fuse the norm, because the gate consumes the same
`normalized` tensor the QKV kernel already reads, so no reduction is duplicated.
The added rows are 64 of 10304, about 0.6 % more work in a dispatch that already
exists. Both endpoints already exist in tree: the INT8 path's gate rows already
ride the fused bank's single dispatch (`:5892-5896`), and o_proj already has a
`!gateIsActivated` NVFP4 variant that applies softplus in-kernel (`:6302-6316`).
The open risk is replicating the softplus rounding boundary bit-exactly.

**Attribution caveat on A, which I want on the record.** The removed kernel of
rejection 1 was norm+QKV **+ gate** - all three were bundled into the one
dispatch (`LagunaRuntimeModel.swift:5856-5860`). The +2.7 % that killed it was
therefore measured against the *bundle*, and cannot be cleanly attributed to the
norm term. The argument above - "the norm was the expensive part, so a gate-only
fold will win" - is an **inference from the mechanism, not a measurement**. It is
a plausible inference: folding the norm forces the QKV dispatch to redo a
whole-row reduction per threadgroup, whereas the gate rows consume the
`normalized` tensor the QKV kernel already reads and duplicate no reduction. But
Idea A is precisely the *untested residual* of a bundle that lost, so it should
be sized as a genuine unknown rather than as a de-risked variant of a known
result. If the next slot is spent on A, the honest prior is roughly even odds,
and the run is worth doing mostly because it also *resolves the attribution*: a
win says the norm carried the +2.7 %, a loss says the gate fold itself is the
loser and rejection 1 was correct for a second reason.

**B** has the smallest new-math surface: the selection is already derived inside
the packed QMV (`:7812`, `:7938`), and only the fp32 weight formula needs
replicating, against two existing tested references
(`LagunaRuntimeLayers.swift:727-746`, `:748-768`). `lagunaDecodeRouterTop8` is a
single 256-thread threadgroup whose outputs are consumed *only* by the
down-residual kernel.

**C** is designed-but-absent rather than new: `mergedSharedActivated`
(`LagunaRuntimeLayers.swift:2001-2005`) is documented as "set when the routed and
shared gate/up QMVs were issued as one dispatch below" but is never assigned, and
the helper `fusedSharedBanks` (`:144-154`) is never called. That plumbing arrived
through a frontier sync, so it is either unfinished **or** a quietly defused
loser. Unlike the norm+QKV fusion it carries no negative note, but the frontier
notes should be checked for a defusion receipt before anyone spends a slot on it.

B and C together take the MoE tail from 5 dispatches to 3: -78 per token,
~193 us, ~3.9 % nominal.

### 8.4 The caveat that governs all of the above

2.474 us is the **average** cost of a hazard-free injected dispatch. A real
dispatch's marginal cost depends on where it sits in the schedule, and the tree
contains precedent in both directions: two removed RoPE-probe dispatches were
worth approximately zero in the old regime because they were off the critical
path (`LagunaRuntimeModel.swift:614-626`), while the same family re-measured at
about -0.6 %, i.e. roughly 13 us per dispatch, under the current r=1 regime.

So the honest statement of what R93 delivers is:

> 2.474 us/dispatch is a **calibrated floor** for what a removed decode dispatch
> is worth on the ranked M5, and 404 is the count it applies to. Realised gains
> should be expected anywhere from ~0.5x to ~2x nominal, and every candidate
> above still needs its own fresh-baseline paired measurement.

What R93 changes is not that these ideas become free - it is that they stop
being unmeasurable. Before this experiment a 40-dispatch reduction was
indistinguishable from noise on the M4 iteration host (section 1.2: the first
~480 injected dispatches are literally free there), so no local result could have
justified the work. It is now a predicted -2.0 % on the machine that scores,
which is well above the minimum resolvable decode difference in section 3.

## 9. The channel measured from the corpus itself (n = 1184)

Arms A and B buy candidate-side replicates one submission at a time. There is a
much larger null sample already in the public corpus that costs nothing, and I
had been walking past it.

**Every receipt carries its own same-session paired baseline.** That baseline is
the *pinned* baseline: identical code, identical prompts, on every one of the
1184 receipts spanning 2026-07-24 to 2026-08-09. So `bl_dec` and `bl_pre` are a
16-day, n=1184 null sample of the ranked measurement channel itself - exactly
the quantity Arm A is chartered to estimate, at 200x the sample size and zero
submission cost.

Reproduce with `python3 research/r93-runs/channel_noise.py
research/r93-runs/receipts-latest.json`.

### 9.1 The channel's own repeatability

| statistic | mean | sd | CV | 95 % CI on CV |
|---|---|---|---|---|
| `bl_dec` | 13854.895 us | 34.004 us | **0.2454 %** | [0.2359 %, 0.2557 %] |
| `bl_pre` | 372.479 us | 7.245 us | **1.9451 %** | [1.8698 %, 2.0267 %] |

The decode figure sits just under the 0.2924 % corpus bound the assignment gave
me, which is reassuring: the assignment's bound was derived from *candidate*
receipts, which are heterogeneous in code, so it should over-estimate. It does,
by about 19 %.

The prefill figure does the opposite, and it is the surprise of this section.
The assignment's prefill bound was 0.2573 %. The channel's actual prefill
repeatability is **1.9451 %, roughly 7.5x worse**. Section 2 already showed that
my own machine-code-identical candidates repeat prefill to 0.0643 %. Both are
true, and section 9.3 explains why they are not in conflict.

Daily buckets show no trend: daily `bl_dec` means run 13839-13866 us across 14
days, a total spread of 0.2 %, with daily CVs of 0.12-0.28 %.

### 9.2 The channel is white - there is no drift to correct for

If the host drifted, receipts close in time would resemble each other more than
receipts far apart, and same-session pairing would cancel that drift.

| series | mean abs diff, adjacent receipts | mean abs diff, random pairs | ratio |
|---|---|---|---|
| `bl_dec` | 37.730 us | 37.412 us | **1.0085** |
| `bl_pre` | 8.155 us | 8.073 us | **1.0102** |

A ratio of 1 means no temporal structure whatsoever. Restricting to adjacent
pairs less than 30 minutes apart (n=1064) gives 1.0167. The 40 C thermal gate is
doing its job completely: **two receipts taken a week apart are as comparable as
two taken ten minutes apart.**

This is a practical licence. My nulls and rungs were bought over a ~2 hour
window and I had been treating elapsed time as a threat to the design. It is not
one. It also means there is no reason to interleave nulls with rungs for drift
control, which frees the remaining budget to be spent purely on whichever
estimate is weakest.

### 9.3 The paired baseline buys health checking, not precision

Pairing only reduces variance if the two members of a pair are positively
correlated. Estimated by de-meaning within solver-day groups of 5 or more
receipts (77 groups, 942 receipts), so that code changes are absorbed into the
group mean and what remains is measurement noise:

| axis | corr(candidate, same-session baseline) | 95 % CI |
|---|---|---|
| decode | **-0.0485** | [-0.1121, +0.0154] |
| prefill | **+0.0054** | [-0.0585, +0.0692] |

Both are indistinguishable from zero, which is what section 9.2 predicts: with
no shared drift there is no shared component to cancel.

The de-meaning estimator can be attenuated toward zero if a solver's candidate
timing trends within a day while the baseline does not, so
`research/r93-runs/corr_robustness.py` re-estimates it three more ways:

| estimator | decode rho | prefill rho |
|---|---|---|
| (a) solver-day de-meaned, n>=5 (n=942) | -0.0485 | +0.0054 |
| (b) first differences within solver-day (n=963) | -0.0532 | +0.0287 |
| (c) near-replicate groups only, candidate CV < 0.5 % (n=311/259) | -0.0175 | -0.0746 |
| (d) consecutive same-solver pairs <= 60 min apart (n=621) | -0.0472 | +0.0451 |

First differencing removes any linear within-day trend, and (c) restricts to
solver-days where the candidate barely moved, which is the least confounded of
the four. All four land inside +/- 0.08. Since pairing can reduce variance by at
most `1 - rho^2`, a correlation this small saves under 1 % of variance while the
ratio adds 100 % of the baseline's. **Pairing is a net loss for precision.**

The consequence runs opposite to the intuition behind paired designs. With
rho = 0 the published speedup is *noisier* than the raw candidate number,
because it adds the baseline's noise instead of cancelling it:

> CV(published speedup)^2 = CV(candidate)^2 + CV(baseline)^2

So for research comparisons the correct statistic is the **raw candidate
microseconds**, not the published speedup. Using my measured candidate-side CVs
from section 2, the minimum resolvable difference at 95 % confidence, two-sided,
comparing two variants with n receipts each:

**Decode** (candidate CV 0.4041 %, baseline CV 0.2454 %, published-speedup CV 0.4728 %)

| n per arm | raw candidate us | published speedup | sharpening |
|---|---|---|---|
| 2 | 1.7389 % | 2.0345 % | 1.2x |
| 3 | 0.8074 % | 0.9447 % | 1.2x |
| 4 | 0.5961 % | 0.6974 % | 1.2x |
| 6 | 0.4601 % | 0.5383 % | 1.2x |
| 8 | 0.3960 % | 0.4634 % | 1.2x |

**Prefill** (candidate CV 0.0643 %, baseline CV 1.9451 %, published-speedup CV 1.9461 %)

| n per arm | raw candidate us | published speedup | sharpening |
|---|---|---|---|
| 2 | 0.2766 % | 8.3742 % | **30.3x** |
| 3 | 0.1284 % | 3.8883 % | **30.3x** |
| 4 | 0.0948 % | 2.8706 % | **30.3x** |
| 6 | 0.0732 % | 2.2157 % | **30.3x** |
| 8 | 0.0630 % | 1.9072 % | **30.3x** |

The decode gain is a modest 1.2x. The prefill gain is **30x**, and it resolves
the apparent contradiction in section 9.1: the candidate side of a prefill
measurement is one of the most repeatable numbers in this whole system
(0.0643 %), while the *published prefill speedup* is nearly worthless for
detecting anything under about 3 %, because the pinned baseline's single
512-token prefill pass is 30x noisier than ours.

Two concrete implications:

1. **Never evaluate a prefill change using `prefill_speedup`.** A real +1 %
   prefill win is invisible in the published ratio at any budget we can afford,
   and clearly visible in `prefill_seconds_per_token` with n=2.
2. **The 0.95 prefill floor is checked against a statistic with ~1.95 % CV.** A
   candidate whose true prefill speedup is 1.00 is safe, but one genuinely
   sitting at 0.98 would trip the floor by chance roughly 6 % of the time even
   though it is compliant. Anything that spends prefill headroom to buy decode
   should keep margin well above the floor rather than shaving it.

### 9.4 The baseline decode distribution has a heavy right tail

| series | skew | excess kurtosis | full CV | 5 %-trimmed CV | IQR-robust CV |
|---|---|---|---|---|---|
| `bl_dec` | +0.927 | +1.937 | 0.2454 % | 0.1919 % | 0.2575 % |
| `bl_pre` | +0.525 | -1.074 | 1.9451 % | 1.7574 % | 2.5235 % |

Decode is right-skewed with a fat tail: occasional slow sessions, no fast ones.
Trimming 5 % from each end drops the CV by 22 %, from 0.2454 % to 0.1919 %.

This is the expected shape for a contended machine and it has a direct
consequence for cadence: with n >= 3 receipts per variant a **median or trimmed
mean is materially more efficient than the plain mean**, and it protects against
the one-slow-session failure mode in which a genuinely good candidate is
rejected by a single unlucky receipt. It also means the section 2 candidate-side
sigma, a plain sd over a handful of points, should be read as an upper bound.

### 9.5 Noise is multiplicative, and fast candidates are relatively noisier

Section 9.1 measures the channel at the baseline's speed (13855 us decode) and
sections 9.3 and 9.6 extrapolate toward ours (~4900 us). That is only legitimate
if the noise is multiplicative. `research/r93-runs/hetero.py` checks it on
near-replicate solver-day groups (candidate CV < 0.6 %, so residuals are noise
rather than code change), binned by group mean:

**Decode** (357 points)

| group-mean band | n | residual sd | residual CV |
|---|---|---|---|
| 4912 - 5100 us | 89 | 21.745 us | **0.4358 %** |
| 5100 - 5121 us | 89 | 13.529 us | 0.2648 % |
| 5121 - 6877 us | 89 | 15.934 us | 0.3017 % |
| 6877 - 11879 us | 90 | 32.451 us | 0.3819 % |

The residual *sd* rises with the mean while the residual *CV* stays inside
0.26-0.44 %, so decode noise is multiplicative and the CV does extrapolate.

The first row is the more useful result. That band, 4912-5100 us, **is our
regime**, and it is measured on 89 near-replicate points from other solvers.
Its 0.4358 % agrees closely with the 0.4041 % I measured on my own
machine-code-identical nulls, and both sit clearly above the baseline channel's
0.2454 %.

That settles a puzzle from section 2. My candidate-side decode sigma came out
*above* the assignment's 0.2924 % corpus bound, which was surprising because a
heterogeneous corpus bound should over-estimate. It is not a small-n artifact:
**fast candidates really are relatively noisier than the slow pinned baseline**,
by roughly 1.7x in CV. At 4900 us per token a larger share of the step is
CPU-side dispatch and scheduling jitter, which averages out less well over 128
steps than bulk GPU compute does. The practical reading is that as the frontier
gets faster, its relative measurement noise gets *worse*, so cadence
requirements tighten over the life of the campaign rather than relaxing.

**Prefill** (281 points)

| group-mean band | n | residual sd | residual CV |
|---|---|---|---|
| 187.8 - 191.0 us | 70 | 0.457 us | 0.2416 % |
| 191.0 - 191.2 us | 70 | 0.305 us | 0.1595 % |
| 191.2 - 195.4 us | 70 | 0.667 us | 0.3441 % |
| 195.4 - 377.5 us | 71 | 0.977 us | 0.4039 % |

Prefill tells the opposite story about the baseline, and it is decisive for
section 9.3. A candidate near 190 us repeats to 0.16-0.24 % even with small code
differences mixed in, and to 0.0643 % when the code is machine-code identical.
The pinned baseline at 372 us repeats to only 1.9451 %. If the noise were purely
a property of the machine, multiplicative scaling would predict similar CVs.
It does not: **the baseline's prefill pass is specifically about 8x noisier in
relative terms than a fast candidate's.** The prefill noise problem belongs to
the baseline code path, not to the M5, and no improvement on our side can reduce
it. That is why the published prefill speedup cannot be rescued by better
candidate engineering and must simply not be used as a research statistic.

### 9.6 What this did and did not replace

It did not replace Arm A. The corpus baseline measures the channel under the
*baseline's* code, which is roughly 2.8x slower at decode and 2x slower at
prefill than ours; noise need not scale identically. Arm A's
machine-code-identical candidates measure the channel under the code we actually
ship, and section 2's prefill result - 0.0643 % against the baseline's 1.9451 %
- is exactly the sort of divergence that justifies having bought them.

What it did replace is the *precision* requirement on Arm A. Section 3's
minimum-resolvable-difference table no longer rests on a 3-to-6 point sd whose
CI spans an order of magnitude, because the baseline-side term in every one of
those figures is now pinned to +/- 4 % relative. The remaining budget is better
spent on Arm B rungs, and on confirming the candidate-side decode sigma, than on
grinding the sigma CI down with more nulls.

