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
`// senpai-r93-null-<n>` comment. Machine-code identity was verified for the
first pair. Statistic: sample standard deviation of `decode_seconds_per_token`
and `prefill_seconds_per_token` across the N candidate receipts, expressed as a
percentage of the mean, with a chi-square confidence interval, compared against
the corpus-derived upper bounds of **0.2924 % decode** and **0.2573 % prefill**.

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
  `"at:0,1,7,15,23,31,39"`, forcing at least 7 `asyncEval` sync points per step
  on top of that.
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
| 4 | null-3 | `05dd8bbf-c436-447c-99a8-8024d0fc023f` | 0 | 160 | in flight | | |

"all gates green" means `passed_correctness`, both speedup floor verdicts,
GPQA TTFT 9/9 and semantic GPQA 9/9, with `max_abs_diff = 0` over 1344 checked
steps. A `rejected` status with the reason "score did not improve current best"
is the expected and correct outcome for a null or a deliberately slowed ladder
rung; it is a ranking statement, not a correctness statement.
