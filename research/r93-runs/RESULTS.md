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

## 2. Arm A — candidate-side channel noise

**Result (n=5).** The candidate decode channel has a standard deviation of
**0.2939 %** of the mean and the candidate prefill channel **0.1027 %**. Decode
lands essentially exactly on the assignment's 0.2924 % corpus bound (ratio
1.005); prefill is 2.5x *below* its 0.2573 % bound. Neither is *confirmed*
below its bound at n=5, because a five-point chi-square interval on a standard
deviation is three-fold wide.

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

### 2.2 Why the null arm was extended past the required five

The assignment asks for at least five nulls. Five is enough to *report* a sigma
but not enough to *test* one, because the width of a chi-square interval on a
standard deviation collapses very slowly in `n`:

| nulls `n` | df | 95 % CI on sigma, as a multiple of the point estimate |
|---|---|---|
| 4 | 3 | [0.567, 3.729] |
| 5 | 4 | [0.599, 2.874] |
| 6 | 5 | [0.624, 2.453] |
| 7 | 6 | [0.644, 2.202] |
| 8 | 7 | [0.661, 2.035] |

The assignment's stated corpus bounds are 0.2924 % decode and 0.2573 % prefill,
and the question worth answering is whether the candidate-side sigma is
*provably below* them. With the measured n=5 prefill sigma of 0.1027 %, the
upper limit is 0.295 % at n=5 — still above the bound, so five nulls cannot
confirm it. Holding the point estimate, it first drops below 0.2573 % at
**n=6** (0.252 %) and clears it comfortably at n=7 (0.226 %) and n=8 (0.209 %).
Decode is hopeless on this arm at any affordable `n`: its point estimate is
already at the 0.2924 % bound, so its upper limit is roughly 0.60 % even at n=8.

So the null arm was planned to n=6-8 for one specific, decisive reason: n=6 is
the smallest `n` at which the **prefill** bound can be confirmed rather than
merely quoted, and n=7-8 buys margin against the point estimate drifting up.
That asymmetry — prefill confirmable, decode not — is itself a
result, and it is the same asymmetry section 9 finds from the corpus. Budget
was redirected to Arm C (section 10) instead, which is the honest trade: two
more nulls would have tightened a confidence interval, whereas Arm C prices a
risk the whole programme is exposed to.

### 2.3 Measured result, n = 5 machine-code-identical nulls

Raw per-token microseconds read straight off the receipts
([`null_stats.py`](null_stats.py), receipts in [`receipts/`](receipts)):

| marker | cand decode us | cand prefill us | bl decode us | bl prefill us |
|---|---|---|---|---|
| `null-1` | 4894.114 | 187.6373 | 13819.365 | 366.640 |
| `null-2` | 4931.226 | 187.7340 | 13845.108 | 383.584 |
| `null-3` | 4900.524 | 187.8772 | 13857.327 | 364.885 |
| `null-4` | 4916.141 | 188.1166 | 13864.993 | 365.037 |
| `null-5` | 4912.621 | 187.9936 | 13870.722 | 365.293 |

| channel | mean us | sd us | **CV** | 95 % CI on CV | corpus bound | verdict |
|---|---|---|---|---|---|---|
| candidate decode | 4910.925 | 14.431 | **0.2939 %** | [0.176 %, 0.844 %] | 0.2924 % | on the bound; consistent, not confirmed |
| candidate prefill | 187.872 | 0.1929 | **0.1027 %** | [0.062 %, 0.295 %] | 0.2573 % | 2.5x below; consistent, not confirmed |
| baseline decode | 13851.503 | 20.366 | 0.1470 % | [0.088 %, 0.423 %] | — | matches the 1185-receipt corpus (0.2453 %) |
| baseline prefill | 369.088 | 8.133 | 2.2036 % | [1.320 %, 6.332 %] | — | matches the corpus (1.9451 %) |

Three things follow.

1. **The channel is exactly as noisy as the corpus said it was.** The
   assignment's decode bound of 0.2924 % was derived from historical receipts;
   five true nulls put the candidate decode sigma at 0.2939 %, a 0.5 %
   discrepancy. That is an independent corroboration of rule 48's number from a
   completely separate estimator. It should not be over-read: with a n=5 sigma
   whose interval spans [0.176 %, 0.844 %], agreement to 0.5 % is partly luck,
   and the same design would have "agreed" with anything from 0.18 % to 0.84 %
   had that been the corpus figure. The corroboration is real but the *tightness*
   of it is not evidence.
2. **Decode cannot be shown to be *below* the bound and never will be on this
   arm.** The chi-square interval at n=5 spans a factor of five. This is not a
   failure of the experiment; it is the arithmetic of estimating a standard
   deviation from five points, tabulated in advance in section 2.2.
3. **The four channels are ordered exactly as the multiplicative-noise model in
   section 9.5 predicts.** Prefill on the candidate side (fast, 188 us) is the
   quietest at 0.10 %; prefill on the baseline side (slow, 369 us) is the
   loudest at 2.20 %. That is not a contradiction — it is what makes the
   published *prefill speedup* almost useless as a discriminator while the raw
   candidate prefill number is superb.

The practical consequence for the campaign is in the last row pair. A claim
about prefill should be made on **raw candidate microseconds**, never on the
published prefill speedup: the candidate channel is 21x quieter than the
baseline channel that the ratio drags in.

## 3. Minimum resolvable decode difference

Derived from the Arm A sigma: for a comparison of two arms with `n`
receipts each, `se = sigma * sqrt(2/n)` and the 95 % detectable difference is
`t(0.975, 2n-2) * se`. "In dispatches" divides by the Arm B slope of
2.3403 us/dispatch (section 4), which converts the noise floor into the unit
the campaign actually plans in.

| n per arm | df | t(.975) | min &#124;delta&#124; | in us/step | in dispatches |
|---|---|---|---|---|---|
| 2 | 2 | 4.303 | 1.2644 % | 62.10 | 26.5 |
| 3 | 4 | 2.776 | 0.6660 % | 32.71 | 14.0 |
| **4** | 6 | 2.447 | **0.5084 %** | **24.97** | **10.7** |
| **6** | 10 | 2.228 | **0.3780 %** | **18.56** | **7.9** |
| **8** | 14 | 2.145 | **0.3152 %** | **15.48** | **6.6** |

Replanned on the section 9.5 near-replicate sigma of 0.4261 %, which is the
number this report recommends for *planning* because it is measured over real
code changes rather than over comment-only nulls:

| n per arm | min &#124;delta&#124; | in us/step | in dispatches |
|---|---|---|---|
| 4 | 0.7373 % | 36.21 | 15.5 |
| 6 | 0.5481 % | 26.92 | 11.5 |
| 8 | 0.4570 % | 22.44 | 9.6 |

**Correction to a number this report published earlier.** The first version of
[`channel_noise.py`](channel_noise.py) looked up its t critical values in a
table that was tabulated by `n` but indexed by `df`, which returned
`t(0.975, 20) = 2.086` where `t(0.975, 6) = 2.447` was required. Every
minimum-resolvable figure was therefore about 15 % too optimistic at small `n`
(for example n=4 decode read 0.4334 % instead of 0.5084 %). The table is now
keyed by degrees of freedom and the numbers above are the corrected ones. The
cadence recommendation in section 5 is unaffected, because it is driven by the
larger near-replicate sigma and the receipt counts did not move.

The headline is the right-hand column. Even at a generous n=8 — four hours of
serial channel time for one comparison — the channel cannot see a change
smaller than about **7 decode dispatches out of 404**. Section 8 uses this to
kill a family of otherwise attractive micro-optimisations: they are real, but
they are unmeasurable on the only instrument that counts.

## 4. Arm B — M5 microseconds per dispatch

> **Direction warning (added after section 8.0).** Everything in this section
> is measured by *adding* hazard-free dispatches. PR #502 (rule 53) later showed
> that *removing* real decode dispatches recovers approximately nothing. Read
> section 4 as the price of dispatches a candidate would add, and section 8.0
> before acting on any subtraction-direction sentence below.

**The M4 free region does not exist on M5.** Eight receipts — five
machine-code-identical K=0 nulls plus rungs at K=60, 240 and 800 — put the cost
of one extra hazard-free decode dispatch on the ranked M5 at

> **2.3403 us/dispatch, 95 % CI [2.2766, 2.4040]** (OLS, df=6, intercept
> 4918.09 us, residual s = 19.31 us).

| K | n | mean candidate decode (us) | marginal vs previous rung |
|---|---|---|---|
| 0 | 5 | 4910.925 (sd 14.431) | — |
| 60 | 1 | 5077.024 | 2.768 us/disp |
| 240 | 1 | 5506.517 | 2.386 us/disp |
| 800 | 1 | 6780.945 | 2.276 us/disp |

Three independent checks say the slope is real and is not an artifact of the fit:

1. **It is not driven by the long rung.** K=800 carries leverage h = 0.923, so
   the single-fit CI above is largely that one point's noise. Dropping it
   entirely and refitting on K <= 240 gives **2.488 us/dispatch, CI [2.316,
   2.660]** — which *contains* the full-range slope. The high-leverage point is
   confirming the low rungs, not creating them.
2. **Weighting is not load-bearing.** WLS with 1/mu^2 weights (the
   multiplicative-noise model of section 9.5) gives 2.348, a +0.32 % shift.
3. **The injection really is decode-only.** Prefill across the same eight
   receipts moves by -0.113 us (-0.060 %), t = -0.501 on 6 df. This is an
   internal control, not an assumption: the same receipts that show a 38 %
   decode swing show no prefill effect.

**Is it linear?** The segment marginals fall monotonically — 2.768, 2.386,
2.276 — which hints that the *first* dispatches cost slightly more than later
ones. The formal lack-of-fit test cannot resolve it (F(2,4) = 3.37 against a
6.94 critical value), and with one replicated level it never will at this
budget. So do not claim linearity — and note that each rung is a *single*
receipt, so the first marginal step sits only ~1.4 standard errors above the
pooled slope. The direction is worth recording rather than believing: **the
low-K marginal is the highest one**, and low-K is exactly where real work
happens — a candidate removes tens of dispatches, not hundreds. Quoting the
pooled 2.3403 for a small-K change is therefore conservative.

So the two machines disagree qualitatively, exactly as section 1.3 warned:

- M4 Pro absorbs the first ~480 hazard-free dispatches at zero cost and only
  reaches ~2 us/dispatch beyond K~1600.
- M5 charges 2.3-2.8 us/dispatch from K=0 with no free region at all.

This is the mechanism from section 1.2 seen from the other side. The free
region on M4 is CPU shadow: the injected GPU chain hides under the ~1 ms of
CPU-side MLX graph building per decode step. The ranked M5 is a faster GPU
behind a faster CPU, and on that machine the shadow is not long enough to hide
even 240 dispatches.

> **SUPERSEDED by section 8.0 (rule 53, PR #502).** The paragraph below was the
> original practical read-out. It assumed the addition price reverses in sign.
> PR #502 removed real decode dispatches and recovered ~0 us, so **do not** plan
> work against "234 us per 100 dispatches removed". The surviving statement is
> the addition-direction one: adding 100 hazard-free dispatches costs ~234 us.

~~**Practical consequence for the campaign:** on the ranked machine a saved GPU
dispatch is worth ~2.34 us of decode time, and that is a *lower bound* because
the injected kernels are hazard-free while a real removed dispatch usually also
removes a fence wait. At a candidate decode of ~4918 us, removing 100 real
dispatches per token is worth 234 us [228, 240], i.e. **4.8 % of candidate
decode**. Dispatch-count reduction is therefore a first-class optimisation
target on M5 even though local M4 iteration will report it as worthless.~~

The 2.3403 us/dispatch measured here is ~18 % above the 1.9823 us/dispatch OLS
slope from the 2026-08-05 historical receipts (section 1.3). Both are the same
order and both exclude a free region. The gap is not surprising — the historical
fit used three points from a different tree with no replicated level — but it is
the right size to keep in mind as the uncertainty that matters. **Treat 2.3 us
as the planning number and 2.0-2.5 us as its practical range**; the formal CI
[2.264, 2.413] is narrower than the honest cross-tree spread.

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

This turned out to be the single most valuable design change in the experiment.
K=60 is what makes the robustness check in section 4 possible: without it,
dropping the h=0.925 K=800 point would have left a two-level fit with no
interior support, and the slope would have rested entirely on one receipt.
With K=60 in hand, the K<=240 subfit stands on its own and agrees.

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

**Consequence.** At the fitted slope of 2.3403 us per hazard-free dispatch
(95 % CI [2.2766, 2.4040], section 4), 404 x 2.3403 us = **945.5 us [919.7,
971.2]**, against a candidate decode of 4918 us per step:

> **19.2 % of ranked M5 decode time [18.7 %, 19.7 %] is per-dispatch cost that
> is hidden, not arithmetic.** Section 8.0 shows it is *not* recoverable by
> removing dispatches, so read "hidden" rather than "recoverable overhead".

Two qualifications that keep this from being oversold:

1. 2.3403 us prices a *hazard-free* dispatch (section 1.2's hazard test: the
   injected kernels bind only their own control/prev/sink buffers, so MLX
   inserts no `MTLFence` between them). A real dispatch that participates in the
   dependency graph costs at least this much, so 945.5 us is a **lower bound**
   on the fixed cost of the dispatches present. ~~and removing one real dispatch
   should save **at least** 2.34 us.~~ **SUPERSEDED by section 8.0**: PR #502
   removed real decode dispatches and recovered ~0 us. The addition price does
   not run backwards.
2. The CI above is the formal interval from eight receipts in one tree. The
   2026-08-05 historical ladder gave 1.98 us/dispatch (section 1.3), so the
   honest cross-tree range is nearer 2.0-2.5 us, i.e. **17-20 % of decode**. The
   qualitative claim — that a fifth of M5 decode is dispatch overhead — survives
   the whole range; the second decimal place does not.

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

### 4.3 The M4 to M5 dispatch-cost transfer rule

Both hosts were driven with the identical instrument (the same source constant,
the same empty TG=8 kernel), so the two ladders are directly comparable and
yield a transfer rule specific to dispatch-count changes. It is not the same
quantity as the section 6 `#137` transfer factor, which is about one particular
kernel restructure.

| host | K=0 | marginal us/dispatch, low K | marginal us/dispatch, saturated |
| --- | --- | --- | --- |
| M4 Pro (local, 48 GB) | 8223 us | **~0** (K=0 to 480 is flat, even slightly negative) | 1.81 (K 800 to 2400), 2.29 (K 1200 to 2400) |
| M5 Max (ranked) | 4911 us | **2.78** (K=0 to 60), 2.39 (K 60 to 240) | 2.28 (K=240 to 800) |

The saturated marginal costs agree to within about 20 % (1.8-2.3 us on M4 Pro
versus 2.28 us on M5 Max), which is unsurprising: both are per-dispatch
driver and encoder work, and neither host is doing any arithmetic in the
injected kernel. What does **not** transfer is the *offset*:

> M4 Pro absorbs its first ~480 injected dispatches for free. M5 Max charges
> from the first one.

The mechanism is visible in the K=0 column. The M4 Pro step is 8.2 ms against
the M5's 4.9 ms, and the local hazard test (section 1.2, job `528661f0`) showed
the free region is not a command-buffer-granularity effect - raising
`MLX_MAX_OPS_PER_BUFFER` and `MLX_MAX_MB_PER_BUFFER` to 10^6 changed nothing.
What survives is a CPU shadow: MLX spends roughly 1 ms per step building the
graph on the CPU, and on the slower M4 GPU that CPU work is fully hidden behind
GPU execution, so a hazard-free injected chain slots into slack that already
exists. The M5 GPU finishes its real work sooner, the slack is gone, and every
injected dispatch is on the critical path.

The operational rule for the campaign:

- **A dispatch-count reduction measured on M4 Pro will read as approximately
  zero and must not be discarded on that basis.** ~~For the two live candidates
  in section 8.3 (B and C, -78 dispatches per token), M4 Pro predicts ~0 us and
  M5 predicts ~180-195 us, or 3.7-4.0 % of decode.~~ **SUPERSEDED by section
  8.0**: PR #502 ran that experiment on M5 and the removal recovered ~0 us, so
  the M4-reads-zero rule is correct but the M5 prediction attached to it was
  not. What survives is the *addition* trap: a change that adds dispatches will
  read free on M4 and be charged on M5.
- The converse also holds and is the more dangerous direction: a change that
  *adds* dispatches, for example splitting a fused kernel to simplify code, is
  free on the local host and is charged in full on the ranked host.
- Any local A/B whose only mechanism is dispatch count should be run with the
  `DARKBLOOM_INJECT_DECODE_EMPTY` ladder as a calibrated yardstick, or moved
  straight to the official channel, where section 5 says a >= 2 % effect
  confirms in one receipt.


## 5. Submission cadence policy

Written up in full in [`cadence-policy.md`](cadence-policy.md) as twelve rules
(P1-P12) plus a worked budget. The quantitative core is the table below:
how many official receipts a decode hypothesis of a given size needs, at 95 %
two-sided confidence and 80 % power, computed by
[`channel_noise.py`](channel_noise.py) from the **recommended planning sigma**:
sigma(raw candidate decode) = 0.4261 % and sigma(published decode speedup) =
0.4917 %. That sigma is the corpus near-replicate residual at our own decode
speed, not the five-point null sd; the paragraphs after the table explain why
that choice matters more than any other number in this section.

| true decode delta | est. ref, raw us | est. ref, published | fresh ref, raw us | fresh ref, published |
| --- | --- | --- | --- | --- |
| 0.5 % | 6 | 8 | 12 | 16 |
| 1.0 % | 2 | 2 | 3 | 4 |
| 2.0 % | 1 | 1 | 1 | 1 |
| 4.0 % | 1 | 1 | 1 | 1 |

"Estimated reference" assumes a well-characterised control already exists from
earlier receipts; "fresh reference" assumes the control must also be paid for
inside this experiment. At ~21 minutes of exclusive channel time per receipt,
a 2 % decode win is a 21-minute confirmation and a 0.5 % decode win is a
2-4 hour commitment. The three rules that follow from this and that most change
day-to-day behaviour are P2 (read raw candidate timings, never cross-session
scores), P4 (interleaving is optional because the channel has no drift, section
9.2) and P10 (mine the receipt corpus before spending a slot, section 9).

**These counts are point estimates and the table hides how soft they are.**
Required `n` scales as `sigma^2`, so the chi-square uncertainty on a small-sample
sigma maps straight onto the receipt counts. `critique_checks.py` prints the
multipliers:

| sigma from | df | 95 % CI on sigma | multiplier on required n |
|---|---|---|---|
| n=3 nulls | 2 | [0.52, 6.29] x s | **[0.27, 39.5]** |
| n=4 nulls | 3 | [0.57, 3.73] x s | [0.32, 13.9] |
| **n=5 nulls (delivered)** | 4 | [0.60, 2.87] x s | [0.36, 8.3] |

At the n=3 sigma this table originally used, "6 receipts" honestly meant
"somewhere between 2 and 203". At the n=5 sigma actually delivered it means
"between 2 and 50". A five-point sd cannot pin a cadence table, and no
affordable number of nulls will: getting the multiplier inside `[0.7, 1.5]`
would take about n=30, which is 11 hours of exclusive channel time spent
measuring nothing.

`channel_noise.py` therefore prints the cadence table three times, and the
difference between them is the real finding:

| sigma used | value | 0.5 % claim, fresh ref, published su | 1.0 % | 2.0 % |
|---|---|---|---|---|
| n=5 null point estimate | 0.2939 % | 10 receipts | 3 | 1 |
| n=5 null, chi-square upper 95 % | 0.8444 % (x2.87) | **49** | 13 | 4 |
| **corpus near-replicate (recommended)** | **0.4261 %** | **16** | 4 | 1 |

The middle row is what the nulls alone can guarantee, and it is useless for
planning. The bottom row is the number to actually use, and it comes from a
completely different place: solver-day groups in the receipt corpus with at
least 4 points and internal CV below 0.6 %, restricted to group means at or
below 5100 us so the estimate is taken at our own decode speed. That is
**119 points across 8 groups**, roughly 111 degrees of freedom instead of 4, so
its own chi-square interval is **[0.884x, 1.151x], i.e. about +/-13 %**, rather
than the factor of nearly three the nulls carry. (An earlier draft said "a few
percent wide"; that understated it and is corrected here.) It agrees with
section 9.5's banded estimate (0.4358 %) computed by the same residual method in
`hetero.py`.

Three caveats on the recommended sigma, and — contrary to an earlier draft —
**they do not all point the same way**:

1. *Upward bias.* It is measured under small code differences rather than none,
   so on that account alone it is an **upper bound** on the pure channel sigma.
2. *Downward bias.* The cells are selected by requiring internal CV below 0.6 %,
   which is a truncation on the very statistic being estimated. Any solver-day
   that happened to draw a noisy set of receipts is excluded, so this selection
   pushes the estimate **down**. The two biases oppose each other and we cannot
   claim to know which dominates; the honest reading is that 0.4261 % is a
   plausible central value with roughly +/-13 % sampling error on top of an
   unquantified selection term, not a conservative bound.
3. *Transferability.* It is measured on other solvers' submissions, so it assumes
   the channel treats their receipts and mine alike — which section 9.1's
   pinned-baseline analysis supports, since every receipt in the corpus times the
   same baseline code and still spreads by 0.2453 %.

One further point of comparability. Section 3's minimum-resolvable table is a
**least significant difference**: the effect size that would land exactly on the
significance threshold, which is 50 % power by construction. This section's
cadence table sizes for **80 % power**, which is why its receipt counts are
larger for a nominally similar effect. `channel_noise.py`'s `need()` also uses
normal z-quantiles rather than t; that is justified here only because the corpus
sigma carries ~111 degrees of freedom, and it would be wrong if the same routine
were fed the n=5 null sigma.

The honest summary is that **the nulls verify the channel is well-behaved but
cannot size it; the corpus sizes it.** Read the recommended row as "this order
of magnitude, rounded up": a 2 % decode effect is a one-receipt question, 1 % is
a small-handful question, and 0.5 % is a half-day question. The boundaries
between those regimes are firm; the exact integers are not.

## 6. Re-derived #137 M4 to M5 transfer factor

Written up in full in [`pr137-transfer-factor.md`](pr137-transfer-factor.md).
Headline: using **raw paired timings** rather than scores, the M5 effect of the
#137 lm-head cascade is **+16.590 us = +0.3375 %** (drift-cancelling form
+0.3795 %), against a corrected balanced M4 census of **-64.5 us = -0.785 %**,
giving a transfer factor of **T ~ -0.48** (range -0.43 to -0.49). This replaces
the score-based estimate of -0.40 +/- 0.24. The brief's suggested pairing of
"+0.803 % vs `7ce1262d`" is invalid because those two receipts are 49 hours
apart.

**How much of this is real, given section 2.3.** The M5 side of that ratio is a
single receipt against a single receipt. The measured candidate-side decode CV
of 0.2939 % makes the 95 % resolution of a one-versus-one comparison
`1.96 * 0.2939 * sqrt(2) = +/- 0.81 %`, or about +/- 40 us per step. The measured
M5 effect is **+0.34 % = +16.6 us, comfortably inside that interval**, so the
*sign* of the M5 effect is not established by these two receipts and neither is
the precise value of T.

What the data does support is the weaker but still decisive claim: a change that
the M4 census says is worth **-0.79 %** produced an M5 effect that is
statistically indistinguishable from zero and certainly not -0.79 %. Whether T
is -0.48, 0, or +0.2, the operational conclusion is the same and is the one the
campaign needs — **M4 census gains do not transfer to the ranked machine at
anything like face value**. Establishing the sign of T would take roughly n=4
per arm on both sides, which at 8 slots is more than this transfer factor is
worth; the honest headline is `|T| < 0.5` rather than `T = -0.48`.

---

## 7. Submission ledger

| # | marker | submission id | K | TG | status | all gates | W&B |
|---|---|---|---|---|---|---|---|
| 1 | null-1 | `25e1f18e-ef83-491f-8a65-8944765bfe46` | 0 | 160 | rejected (score did not improve best) | green | [`3szqrztf`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/3szqrztf) |
| 2 | null-2 | `d11026c9-25c5-498c-936f-ed3db3335c30` | 0 | 160 | rejected (score did not improve best) | green | [`0doaq0w0`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/0doaq0w0) |
| 3 | ladder-K240 | `99309c61-2b7e-4ce8-bb74-52bd3da8a03c` | 240 | 8 | rejected (score did not improve best) | green | [`fpi2ynyl`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/fpi2ynyl) |
| 4 | null-3 | `05dd8bbf-c436-447c-99a8-8024d0fc023f` | 0 | 160 | rejected (score did not improve best) | green | [`fvm3v67i`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/fvm3v67i) |
| 5 | ladder-K800 | `f8719c48-8df6-4570-abf1-1c9a369c64e0` | 800 | 8 | rejected (score did not improve best) | green | [`qaempae6`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/qaempae6) |
| 6 | null-4 | `ab6a15a1-4d79-4c51-ac46-bd97fde2e1bf` | 0 | 160 | rejected (score did not improve best) | green | [`0ecng8mc`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/0ecng8mc) |
| 7 | ladder-K60 | `b835a980-9c6a-48f3-a9d0-c5961ed1aac4` | 60 | 8 | rejected (score did not improve best) | green | [`xlaup9j4`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/xlaup9j4) |
| 8 | null-5 | `4fec8e2d-3fa1-4a99-a9a5-e6883aee7497` | 0 | 160 | rejected (score did not improve best) | green | [`92snii58`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/92snii58) |
| 9 | probe-routed-fma-24 | `ecd89cac-b21e-4948-b619-5ac106c8fe48` | `routed:fma:24` | — | rejected (score did not improve best) | green | [`59o0mk6y`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/59o0mk6y) |
| 10 | probe-routed-fma-64 | `ab3a2433-2553-4946-8502-d04814565e17` | `routed:fma:64` | — | rejected (score did not improve best) | green | [`fotwz1v2`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/fotwz1v2) |

Per-receipt metrics for rows 1-8 are in section 2.3 (nulls) and section 4
(ladder rungs); row 9 is in section 10.5 and row 10 in section 10.8.

"all gates green" means `passed_correctness`, both speedup floor verdicts,
GPQA TTFT 9/9 and semantic GPQA 9/9, with `max_abs_diff = 0` over 1344 checked
steps. A `rejected` status with the reason "score did not improve current best"
is the expected and correct outcome for a null or a deliberately slowed ladder
rung; it is a ranking statement, not a correctness statement.

## 8. Follow-up: what the 2.339 us actually buys, and what it does not

Sections 4 and 4.2 establish a price and a count. This section audits what can
actually be *removed*, done independently against the source at BASE_SHA. It is
deliberately separated from the measurement above because none of it is measured
by this experiment - it is the shortlist R93 exists to enable, not a result of
R93.

The most important thing here is the rejection list. The naive reading of
"404 dispatches x 2.339 us = 0.95 ms" is that any fusion is free money. That
reading is wrong, and the code already contains the counter-example.

### 8.0 Reconciliation with rule 53: this slope is an *affordability* price, not a fusion budget

Round-93 PR #502 (W&B `ut3wdjct`) established rule 53: **there is no decode
dispatch residue.** A 24-label ledger closes to +0.3 us across all 406 decode
dispatches, so removing a dispatch on the ranked M5 recovers approximately
nothing. That is the exact opposite sign of the naive reading of section 4.2,
and it has to be addressed head-on rather than left as a footnote.

> **On 404 versus 406.** Section 4.2's source audit reproduces **404** dispatches
> per decoded token; #502's instrumented ledger counts **406**. The two are not
> the same census: #502 labels every dispatch the profiler emits, including two
> that our static decomposition folds into their neighbours. A 0.5 % discrepancy
> is immaterial to every number here (404 x 2.3403 = 945.5 us versus
> 406 x 2.3403 = 950.2 us, well inside the slope's own CI), so we keep each
> section's own count rather than silently harmonising them. Nothing in either
> conclusion turns on the difference.

Both results are correct, and they are not in conflict, because they measure
two different quantities:

| | this experiment (Arm B) | #502 (rule 53) |
|---|---|---|
| operation | **add** N bit-exact dispatches | **account for** the existing 406 |
| what moves | wall-clock grows by 2.339 us per added dispatch | ledger closes to +0.3 us total |
| what is being priced | the *marginal* cost of new work injected into a saturated pipeline | the *recoverable* cost of work already overlapped |

The mechanism that makes both true is the one section 1.2 and the
command-buffer-split control already isolated: the decode step is a producer /
consumer pipeline in which the CPU spends roughly 1 ms per step building the MLX
graph while the GPU drains it. The existing 406 dispatches are *already* hidden
inside that shadow and inside each other's tails - so deleting one exposes
nothing and recovers nothing, which is rule 53. But the shadow has finite
capacity. Injecting a fresh, hazard-free chain past that capacity is not hidden,
and it costs 2.339 us each, which is Arm B.

The consequence for this report is concrete and I am stating it as a
**retraction of the practical framing of section 8.3, not of its arithmetic**:

- The shortlist in 8.3 is priced with the *addition* slope. Under rule 53 that
  price does **not** run in reverse. A fusion that removes 39 or 78 dispatches
  per token should be expected to recover **~0 us**, not 91 or 182 us, unless it
  also removes DRAM bytes or ALU work.
- Therefore candidates **B** (delete `lagunaDecodeRouterTop8`), **D** (lm-head
  argmax stage-1) and **E** (final RMSNorm) are **retired**: their entire claimed
  benefit was dispatch-count reduction, and rule 53 says that benefit is zero.
- Candidates **A** (fold the per-head INT8-g32 gate QMV into NVFP4 QKV) and **C**
  (merge the shared-expert QMV into the routed packed top-8 kernel) survive only
  on their *byte* argument, not their dispatch argument: both delete a separate
  read of an activation tensor that the absorbing kernel already has resident.
  They should be re-costed in MB/step against the #512 / #513 methodology and
  re-ranked there. If the re-cost shows no byte saving, they are dead too.

What the 2.339 us number remains good for is the direction it was actually
measured in: **an affordability test for optimizations that add dispatches.**
Concretely - a fused-kernel rewrite that trades one large dispatch for three
smaller ones, a mask or table precompute that adds a decode-time launch, or a
router screen that adds a pre-pass, all pay 2.339 us [2.26, 2.41] per added
dispatch on M5 and must clear that from the byte or ALU saving before they are
worth anything. Section 3's resolvability table converts that directly: at n=4
receipts the channel can only see about 10.5 added dispatches, so anything
adding fewer than ~10 is free *within the measurement*, which is a trap worth
knowing about explicitly.

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

   **This is the discipline the 2.339 us number needs.** Dispatch count is one
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

> **Superseded by rule 53 - read 8.0 first.** The "Nominal us" column below runs
> the addition slope backwards, which #502 has since shown is invalid. B, D and E
> are retired; A and C survive only on their byte argument. The table is kept
> because the dispatch counts and code locations are still correct and still
> useful to whoever re-costs A and C in MB/step.

Nominal us uses 2.339 us/dispatch and is an **average**, not a critical-path
marginal cost - see 8.4.

| # | Idea | Saved | Nominal us | Risk | Size |
|---|---|---|---|---|---|
| A | Fold the per-head INT8-g32 gate QMV into the NVFP4 QKV dispatch, deferring softplus to the o_proj kernel | **40** | 94 (-1.9 %) | med (see caveat) | M |
| B | Delete `lagunaDecodeRouterTop8`: the packed QMV already re-derives top-8 in-dispatch, so have it also emit (inds, weights) | **39** | 91 (-1.9 %) | med | S/M |
| C | Merge the shared-expert gate/up QMV into the routed packed top-8 QMV | **39** | 91 (-1.9 %) | med | M |
| D | Fold lm-head argmax stage-1 into the coarse kernel | 1 | 2.3 | low | S |
| E | Fold the final RMSNorm into layer-39 down-residual or lm-head coarse | 1 | 2.3 | high | M |

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
~182 us, ~3.7 % nominal.

### 8.4 The caveat that governs all of the above

2.339 us is the **average** cost of a hazard-free injected dispatch. A real
dispatch's marginal cost depends on where it sits in the schedule, and the tree
contains precedent in both directions: two removed RoPE-probe dispatches were
worth approximately zero in the old regime because they were off the critical
path (`LagunaRuntimeModel.swift:614-626`), while the same family re-measured at
about -0.6 %, i.e. roughly 13 us per dispatch, under the current r=1 regime.

So the honest statement of what R93 delivers is:

> 2.339 us/dispatch is a **calibrated floor** for what a removed decode dispatch
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
my own machine-code-identical candidates repeat prefill to 0.1027 %. Both are
true, and section 9.3 explains why they are not in conflict.

Daily buckets show no trend: daily `bl_dec` means run 13839-13866 us across 14
days, a total spread of 0.2 %, with daily CVs of 0.12-0.28 %.

*Caveat on the CI.* Both intervals are chi-square intervals, which assume
normality. Section 9.4 shows `bl_dec` has excess kurtosis +1.94, and the
sampling variance of a variance grows with kurtosis roughly as `(2 + kurt)`, so
the true `bl_dec` interval is about `sqrt((2 + 1.94)/2) = 1.4x` wider than
printed — call it [0.232 %, 0.259 %]. `bl_pre` has *negative* excess kurtosis
(-1.07), so its interval is if anything conservative. Neither correction changes
any conclusion drawn from these numbers, but the decode CI should not be quoted
to four digits as if it were exact.

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

All four land inside +/- 0.08 — but **three of the four cannot support the
conclusion**, and it is worth being precise about why, because the naive reading
of this table is wrong.

**The attenuation trap.** `corr(candidate, baseline)` can only ever see the
*noise* part of the candidate's variance; the part driven by the code change is
pure attenuating ballast. If the candidate residuals in an estimator have
standard deviation `sd_total` while only `sd_noise` of that is measurement
noise, the observable correlation is the true noise correlation multiplied by
`a = sd_noise / sd_total`. `research/r93-runs/critique_checks.py` computes `a`
for each estimator:

A measured `r` bounds the true noise correlation only through its **Fisher 95 %
upper limit** divided by `a` — using the point estimate would ignore the
sampling error in `r` itself. `sd(noise)` is the null CV (0.2939 %) times the
mean decode time *of the cell being analysed*, per the multiplicative model of
section 9.5, not a single global microsecond figure.

| estimator | mean decode | sd(cand resid) | sd(noise) | attenuation `a` | measured `r` | Fisher 95 % upper | bound on \|rho\| |
|---|---|---|---|---|---|---|---|
| (a) solver-day de-meaned (77 groups, 943 pts) | 6783 us | 328.38 us | 19.93 us | **0.061** | -0.0492 | +0.0147 | **<= 0.24** (model-dependent) |
| (c) near-replicate, cand CV < 0.5 % (36 groups, 335 pts) | 5767 us | 18.13 us | 16.95 us | **0.935** | -0.0160 | +0.0913 | **<= 0.10** |
| (c) near-replicate, cand CV < 0.6 % (41 groups, 384 pts) | 5992 us | 22.08 us | 17.61 us | **0.797** | +0.0160 | +0.1159 | **<= 0.15** |

Estimators (a), (b) and (d) pool solver-days in which the candidate code
genuinely changed. Their residual spread is ~328 us — roughly 16x the ~20 us of
channel noise — so they are attenuated by a factor of 16 and would report
`r ~ 0.06` even if the underlying noise correlation were a perfect `rho = 1`.
Their large `n` still yields a numerically small bound (0.24), but that number
is only as good as the attenuation model itself, which assumes the code-driven
variance is uncorrelated with baseline noise. We do not rest anything on it.
Only estimator (c), which restricts to solver-days whose candidate barely moved
so that `sd_total ~ sd_noise`, is close to unattenuated and can bound `rho`
without leaning on that assumption.

**The bound that matters is not zero, it is the break-even.** Pairing does not
need `rho = 0` to lose; it needs `rho` below the point where the cancelled
covariance repays the baseline variance it imports. From
`Var(log ratio) = CV_c^2 + CV_b^2 - 2 rho CV_c CV_b`, pairing beats the raw
candidate only when

> `rho > CV(baseline) / (2 CV(candidate))`

| axis | CV(candidate) | CV(baseline) | break-even rho | measured bound |
|---|---|---|---|---|
| decode | 0.2939 % | 0.2453 % | **0.417** | \|rho\| <= 0.15 (estimator (c), CV < 0.6 % cell) |
| prefill | 0.1027 % | 1.9451 % | **9.47** | — |

The **prefill conclusion needs no correlation estimate at all**: the break-even
correlation is 9.47, and correlations cannot exceed 1. No conceivable coupling
between candidate and baseline can make the published prefill speedup as precise
as the raw candidate microseconds. That is an arithmetic impossibility, not a
statistical inference.

The **decode conclusion is a genuine inference** and rests on estimator (c)
alone: its near-unattenuated Fisher bound `|rho| <= 0.15` sits below the 0.417
break-even, so pairing loses. The honest margin is **about 2.8x** using the more
inclusive CV < 0.6 % cell, or 4.2x using the tighter CV < 0.5 % cell; we quote
the former because the tighter cell is more exposed to the truncation bias of
section 9.4. This is the one claim in section 9 that better data could overturn:
it would take a true `rho` above 0.417 — roughly three times our bound — to
reverse it, which is not a comfortable margin so much as a defensible one. The
prefill conclusion, by contrast, cannot be overturned at all.

The consequence runs opposite to the intuition behind paired designs. With
rho = 0 the published speedup is *noisier* than the raw candidate number,
because it adds the baseline's noise instead of cancelling it:

> CV(published speedup)^2 = CV(candidate)^2 + CV(baseline)^2

So for research comparisons the correct statistic is the **raw candidate
microseconds**, not the published speedup. Using my measured candidate-side CVs
from section 2, the minimum resolvable difference at 95 % confidence, two-sided,
comparing two variants with n receipts each:

**Decode** (candidate CV 0.2939 % from the n=5 nulls, baseline CV 0.2453 %,
published-speedup CV 0.3828 %; us column at our 4910.9 us decode step, dispatch
column at the section 4 slope of 2.3403 us)

| n per arm | raw candidate | in us/step | in dispatches/token | published speedup | sharpening |
|---|---|---|---|---|---|
| 2 | 1.2647 % | 62.1 us | 26.5 | 1.6473 % | 1.3x |
| 3 | 0.6662 % | 32.7 us | 14.0 | 0.8677 % | 1.3x |
| 4 | 0.5085 % | 25.0 us | 10.7 | 0.6624 % | 1.3x |
| 6 | 0.3781 % | 18.6 us | 7.9 | 0.4924 % | 1.3x |
| 8 | 0.3152 % | 15.5 us | 6.6 | 0.4106 % | 1.3x |

**Prefill** (candidate CV 0.1027 %, baseline CV 1.9451 %, published-speedup CV
1.9478 %; us column at our 187.9 us prefill step)

| n per arm | raw candidate | in us/token | published speedup | sharpening |
|---|---|---|---|---|
| 2 | 0.4419 % | 0.83 us | 8.381 % | **19.0x** |
| 3 | 0.2328 % | 0.44 us | 4.415 % | **19.0x** |
| 4 | 0.1777 % | 0.33 us | 3.370 % | **19.0x** |
| 6 | 0.1321 % | 0.25 us | 2.506 % | **19.0x** |
| 8 | 0.1101 % | 0.21 us | 2.089 % | **19.0x** |

The decode gain is a modest 1.3x. The prefill gain is **19.0x**, and it resolves
the apparent contradiction in section 9.1: the candidate side of a prefill
measurement is one of the most repeatable numbers in this whole system
(0.1027 %), while the *published prefill speedup* is nearly worthless for
detecting anything under about 3 %, because the pinned baseline's single
512-token prefill pass is ~19x noisier than ours.

The dispatch column is the practically useful one. Even at n=8 — more than my
entire submission budget spent on a single comparison — the decode resolution
floor is **~7 injected dispatches per token**. Every candidate in section 8.3 is
comfortably above that (the smallest, -39 dispatches, is 5.5x the n=8 floor and
1.6x the n=2 floor), which is the concrete reason those candidates are worth
submitting at all.

Two concrete implications:

1. **Never evaluate a prefill change using `prefill_speedup`.** A real +1 %
   prefill win is invisible in the published ratio at any budget we can afford,
   and clearly visible in `prefill_seconds_per_token` with n=2.
2. **The 0.95 prefill floor risk is a cliff, not a gradient — and it is
   narrower than normal theory says.** The floor is checked against a statistic
   with ~1.95 % CV, which under a normal model would trip a truly-compliant 0.98
   candidate about 6 % of the time. That normal model is wrong here.
   `critique_checks.py` evaluates the trip rate directly against all 1185
   observed `bl_pre` draws:

   | true prefill speedup | needs `bl_pre` below | empirical trip rate | normal-theory rate |
   |---|---|---|---|
   | 0.98 | 0.9694 x mean | **0.00 %** (0 / 1185) | 5.78 % |
   | 0.97 | 0.9794 x mean | 7.34 % | 14.46 % |
   | 0.96 | 0.9896 x mean | **50.38 %** | 29.61 % |

   The observed `bl_pre` distribution is short-tailed on the left — its minimum
   is only 2.7 % below the mean, versus the 5.1 % a normal tail would reach — so
   a genuine 0.98 has **never** tripped the floor in the entire public record.
   But the left edge is a wall, not a taper: one further percent of true prefill
   loss takes the risk from 0 % to 7 %, and the next from 7 % to over 50 %,
   *faster* than the normal model predicts. The operational rule is therefore
   sharper and simpler than "keep margin": **a true prefill speedup of 0.98 or
   better is effectively safe, and 0.96 is a coin flip.** Any decode-for-prefill
   trade should be sized against its true prefill cost, measured in raw
   candidate microseconds per the table above, not against the published ratio.

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

**This table selects on relative spread, which could manufacture its own
answer**, so it must not be trusted on its own. A `CV < 0.6 %` cut admits a
larger absolute sd from a group with a larger mean, which is exactly the
`sd ~ mean` pattern the table then reports. `hetero.py` therefore also fits the
scaling directly, regressing `log(group sd)` on `log(group mean)` across groups
weighted by degrees of freedom, where slope 1 is purely multiplicative and
slope 0 purely additive:

| axis | group cut | groups | slope | se | 95 % CI |
|---|---|---|---|---|---|
| decode | CV < 0.6 % | 32 | **+1.078** | 0.301 | [+0.475, +1.680] |
| decode | CV < 1.0 % | 43 | +1.160 | 0.361 | [+0.438, +1.881] |
| decode | **sd < 40 us (absolute)** | 32 | **+0.720** | 0.373 | [-0.027, +1.466] |
| prefill | CV < 0.6 % | 30 | +2.310 | 0.645 | [+1.020, +3.599] |
| prefill | sd < 1.0 us (absolute) | 22 | +0.311 | 3.113 | uninformative |

The decode fit lands on **+1.08, excluding the additive model (slope 0) and
sitting right on the multiplicative one (slope 1)**. The absolute-sd cut is the
artifact-immune control: an absolute microsecond threshold cannot induce
`sd ~ mean`, and in fact biases *against* it by preferentially discarding the
high-sd, high-mean groups. It still returns +0.72, so the multiplicative
conclusion survives its own selection rule.

The prefill fit is steeper than multiplicative (+2.31), which is not noise about
1 — it is the same effect section 9.3 depends on, seen from another angle: the
slower the prefill path, the *relatively* noisier it gets, so the pinned
baseline's slow prefill is disproportionately bad. Its absolute-cut control has
too little lever arm to say anything.

The first row of the banded table is the more useful practical result. That
band, 4912-5100 us, **is our regime**, and it is measured on 89 near-replicate
points from other solvers. Its 0.4358 % is consistent with the 0.2939 % I
measured on my own machine-code-identical nulls — as it should be, since those
89 points still contain small code differences and mine contain none — and both
sit clearly above the baseline channel's 0.2453 %.

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
differences mixed in, and to 0.1027 % when the code is machine-code identical.
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
ship, and section 2's prefill result - 0.1027 % against the baseline's 1.9451 %
- is exactly the sort of divergence that justifies having bought them.

What it did replace is the *precision* requirement on Arm A. Section 3's
minimum-resolvable-difference table no longer rests on a 3-to-6 point sd whose
CI spans an order of magnitude, because the baseline-side term in every one of
those figures is now pinned to +/- 4 % relative. The remaining budget is better
spent on Arm B rungs, and on confirming the candidate-side decode sigma, than on
grinding the sigma CI down with more nulls.


## 10. Arm C — is the ranked M5 in the same bandwidth regime as M4 Pro?

### 10.1 Why this arm exists, and why it nearly did not happen

Round 93 produced two results that only matter together:

- **Rule 55** (#498, W&B `mhhosz20`): the three dominant decode kernels are
  bandwidth-bound **on M4 Pro**. Added bytes cost the full 227 - 240 GB/s
  streaming rate, while added ALU costs only 3.5 - 16.5 % of its issue-limited
  price. Spending arithmetic to remove bytes is therefore nearly free *on M4*.
- Two in-flight experiments, **#512** (MoE router top-8 screen, -40.9 MB/step)
  and **#513** (layer-0 dense block-exponent compaction, -100.7 MB/step), are
  both built on exactly that trade.

The unpriced risk is that rule 55 is an M4 statement. The M5 Max has roughly
546 GB/s of peak bandwidth and the trio's implied working rate puts it near
345 GB/s, i.e. about 63 % of peak rather than M4's 92 %. If M5 is *not*
saturated, then it has spare bandwidth and *less* memory stall to hide
arithmetic in - so the ALU that #512 and #513 spend would be charged at
something much closer to full issue price, and both could lose on the ranked
host while winning locally.

The assignment made Arm C conditional, with an explicit drop rule: *if Arm A
shows the channel is noisier than rule 48 predicts, drop Arm C.* **That
condition did not fire.** Rule 48 budgets sigma(cand_dec) <= 0.2924 %, and the
five machine-code-identical nulls of section 2.3 measure **0.2939 %** — a 0.5 %
discrepancy, which is as close to an exact reproduction as a five-point sd can
give. Arm A's headline finding is precisely that the channel is *as quiet as
advertised*, so Arm C proceeded on its pre-registered condition rather than in
spite of it.

Two secondary numbers are worth separating from that verdict so the trigger is
not mis-read later:

- Section 9's **corpus near-replicate sigma of 0.4261 %** is larger than the
  rule 48 budget, but it is not the quantity the drop rule names. It is measured
  across *other solvers' small code differences*, so it is an upper bound on the
  channel and is deliberately used only for planning (section 5). Reading it as
  a channel-health failure would retire an arm on a statistic that was designed
  to be conservative.
- The n=5 chi-square interval on the null sigma is `[0.176 %, 0.844 %]`. That
  interval contains the budget, so the nulls are *consistent with* rule 48 and
  cannot *refute* it either. Section 2.2 shows that no affordable `n` changes
  this for decode. A drop rule keyed on a five-point sigma can therefore only
  fire on a gross violation, and nothing near one occurred.

Even had the trigger fired, the arm would still have been the right spend, and
the reason is worth recording because it generalises. The drop rule is a proxy
for "the channel cannot resolve this arm", and that proxy is only correct for a
*small* arm. Section 3's resolvability table says a single receipt against the
n = 5 null mean resolves about **0.89 %** of decode. The arm below is predicted
to move decode by **~1.6 % under the M4 hypothesis and ~5.6-11 % under the
issue-bound hypothesis** (section 10.3 derives both) — the two hypotheses are
2.4-3.5x apart and both sit above that floor. A noisy channel does not forbid a
loud experiment; it forbids a quiet one.

### 10.2 Porting the #498 probe: the env-var blocker and the fix

`research/nezuko-r93-probes.patch` does not exist in this experiment's base. It
lives on `maple-nezuko/r93-stall-structure-census` at
`af96720db142387f3138d153f64c1c6777f261c0`, and is vendored here as
`research/r93-runs/nezuko-r93-probes.patch`. It applies **cleanly** to
BASE_SHA `17a4bad4` with a plain `git apply`, despite being cut against
`ca920bbe`.

The blocker is that the upstream probe is selected by
`NEZUKO_R93_PROBE=<target>:<kind>:<n>`. **Environment variables do not reach the
ranked host**, so on M5 the probe would silently be off in every arm and the
whole ladder would read as a flat null - the same failure mode section 1.5
already had to fix for Arm B. The port is the same one: the knob becomes a
source constant inside the submitted file.

```swift
let nezukoR93ProbeSpec: NezukoR93ProbeSpec? = {
    // senpai-r93-armc-spec: "" | "<target>:<kind>:<n>"
    let raw = ""
    ...
```

`research/r93-runs/set_probe.sh <spec>` rewrites that one literal and rebuilds
the scored worker, exactly as `set_ladder.sh` does for the Arm B rung. With the
empty spec the probe emits no kernel-name suffix, binds no probe pool and adds
no statements, so the default state is byte-identical to base.

Three properties of the upstream probe carry over unchanged, and they are what
make the arm admissible:

1. **Bit-exact addition (rule 45).** Every ladder terminates in a sink store
   guarded by `if (nz_sum > 3.0e38f)`, which is never true at runtime. Nothing
   the probe computes reaches a logit.
2. **Name- and residency-matched control (rule 44).** Level `n = 0` *also*
   changes the kernel name to `_pzfma0` and *also* binds the 128 MiB probe pool.
   It is the correct control for level `n = 24`; the unmodified base is not,
   because it differs by a pipeline object and a buffer binding as well.
3. **One kernel-name suffix per arm (rule 33).** The suffix is a single
   `_pz<kind><n>` token.

Two limitations found during the port and worth recording:

- The probe supports **one target at a time**. A combined three-kernel arm would
  need new code. I used the single largest-headroom target, `routed` (16.5 % of
  issue-limited on the float ladder, 50.1 % on the integer ladder), which is also
  the largest decode-time consumer of the three.
- The 128 MiB `uint32` pool is allocated for *every* kind, so the binding
  signature is identical across kinds and levels. On the 128 GB ranked host that
  is immaterial next to the 21.6 GB resident model.

### 10.3 Arm design and what each outcome means

Anchor numbers from #498 section 5.2, `routed` / `fma`, measured on M4 Pro:
levels `0:1505  2:1509  4:1509  8:1535` us/step, OLS slope **3.8 us/n**
(95 % CI +/- 1.8), against an issue-limited price of **22.8 us/n**. The ladder
was never driven past `n = 8`, so the absorption knee is only known to be
**>= 8**; the assignment's "300 % of knee" therefore lands at `n = 24`, which is
what I used.

| arm | spec | role |
|---|---|---|
| C0 | `""` | base; the section 2 nulls already supply it at n = 5 |
| C2 | `routed:fma:24` | super-knee free-ALU load |
| C0' | `routed:fma:0` | name- and residency-matched placement control; promoted after section 10.4, then **superseded by C3 — see section 10.7**, which obtains a placement-free slope without spending this receipt |
| C3 | `routed:fma:64` | probe maximum; liveness test and placement-free slope against C2 |

Predicted M5 decode deltas against the 4910.9 us null mean of section 2.3. The
M4 row is not extrapolated from #498 — it is the effect **measured directly on
this host** in section 10.4, expressed as a fraction of the decode step so it can
be carried across machines with different absolute step times:

| hypothesis | basis | vs `n = 0` | vs probe-off |
|---|---|---|---|
| M5 behaves like M4 (rule 55 transfers) | section 10.4 local anchor: +205 us on an 8151 us step | **~+2.5 %** | **~+1.6 %** |
| M5 is issue- or latency-bound (rule 55 does **not** transfer) | same ALU at PR #498's sub-knee issue price of 22.8 us per `n`, i.e. 24 x 22.8 = 547 us | **~+6 % to +12 %** | **~+5.6 % to +11.1 %** |

The two reference columns differ because section 10.4 measured a real placement
term: on M4, `n = 0` is 0.88 % faster than probe-off, so the same injected load
reads +2.51 % against the matched control and +1.62 % against the base. The
first receipt (C2) can only be read against the null mean, i.e. the probe-off
column; C0' converts it to the matched-control column. The gap between the two
hypotheses is 2.4-3.5x either way, so the placement term cannot flip the verdict
-- it only sets how precisely the low branch can be quantified.

The issue-bound row is a band, not a point, and it is worth being explicit about
how it is built because the first version of this section got it wrong.

The clean way to price "the ALU is not free" is to use a *measured* issue price
rather than to divide a measured absorbed cost by a headroom ratio. PR #498
measured both on M4 Pro at the same nominal `routed`/`fma` condition: the
absorbed slope was 3.8 us per `n` (+/- 1.8) below the knee, while the
issue-limited price of the same instructions was 22.8 us per `n`. At `n = 24`
the issue-limited load is therefore 24 x 22.8 = **547 us**. Charged unchanged
against M5's 4911 us step that is **+11.1 %**; halved, to allow for M5 issuing
arithmetic roughly twice as fast, it is **+5.6 %**. The band is therefore
[+5.6 %, +11.1 %] against probe-off, and the read-out below is keyed on its
lower edge.

(The earlier derivation divided the section 10.4 anchor of 8.54 us per `n` by
rule 55's 16.50 % headroom ratio to get 1242 us. That mixes regimes: 8.54 us is
already a *super-knee* absorbed price, and dividing it by a *sub-knee* headroom
ratio implies 51.8 us per `n`, 2.3x the measured issue price. The number was
too large and the "+11 % conservative lower edge" quoted from it was, awkwardly,
outside its own stated [13 %, 25 %] range. The corrected band is smaller, which
makes the pre-registered separation weaker, not stronger — see the note after
the read-out rule.)

Read-out rule, fixed before the receipt:

- **delta <= ~3 %** - M5 absorbs free ALU like M4 does. Rule 55 transfers, #512
  and #513 are not exposed to a regime change, and the ALU-for-bytes trade is
  live on the ranked host. The `routed:fma:0` control is then worth one more
  receipt, because at that size the measured 0.88 % placement term of section
  10.4 is more than half the signal.
- **delta >= ~6 %** - M5 charges arithmetic much closer to issue price. Rule 55
  is an M4-only statement, ALU-for-bytes is **not** free on the ranked host, and
  #512 / #513 need their ALU cost re-priced on M5 before either is trusted. The
  placement control is unnecessary at that size.
- **anything in between** - inconclusive in one receipt; report the interval
  rather than a verdict.

**How decisive was this design, honestly?** Under the corrected issue-bound band
the two hypotheses are 2.4-3.5x apart, not 4x, and the low edge (+5.6 %) sits
only just above the 6 % high trigger. The single-receipt resolution of this
channel is 0.89 % (section 3: `2.776 * 0.2939 % * sqrt(1 + 1/5)`, n = 1 against
the n = 5 null mean), so a single receipt separates +1.6 % from +5.6 % only if
the truth is near one edge or the other; a result at +4 % would have landed in
the declared inconclusive zone. The design was adequate rather than comfortable.
As it happened the measured value (section 10.5) is +0.67 % with a 95 % upper
limit of +1.56 %, which is 3.6x below even the low edge of the corrected band,
so the verdict is robust — but it is robust because the effect was tiny, not
because the pre-registered thresholds were far apart.

### 10.4 Local M4 anchor

`research/r93-runs/armc_local_sweep.sh` rebuilds the scored worker at each spec
and free-runs 200 decode steps. Run as job `7a5df9c8`, exit 0, on the M4 Pro /
48 GiB host under the low-memory startup profile:

| spec | median ms/step | mean ms/step | worker sha256 (first 16) |
|---|---|---|---|
| `""` (probe off) | 8.223 | 8.238 | `9ad8f9a9a94ca8bd` |
| `routed:fma:0` | 8.151 | 8.168 | `6290ce668f455224` |
| `routed:fma:24` | 8.356 | 8.377 | `5062ebb8ccd6dfd4` |

Three distinct binaries, so the source constant demonstrably reaches the scored
worker and is not being folded away.

**Bit-exactness is confirmed empirically, not just argued.** All three arms
produced `tokens_sha256 = d2280c5620491895db7723f3bfb7c1d4ef74b6eedc65a9ffa50ad66ee1be48fe`
over the dumped free-run token stream (free-run hash `d64c9e79356695a9`, 79
distinct tokens). Rule 45's sink-store argument therefore holds in practice on
this host as well as on paper.

**The measured price.** Against the placement control:

`(8.356 - 8.151) / 8.151 = +2.51 %`, i.e. **+205 us on an 8151 us step, or
8.54 us per injected fma**.

Against the probe-off arm the same load reads +1.62 %, and the difference
between those two readings is the whole reason the control exists: **`n = 0` is
0.88 % *faster* than probe-off**. That is the opposite sign from a pure overhead
model — binding a 128 MiB pool and renaming the pipeline should cost a little,
not save 0.88 %. I have no mechanism for it, and 0.88 % is well above this
host's run-to-run spread, so I am not going to explain it away. The operational
consequence is what matters and it is unambiguous: **the M5 comparison must be
made against `routed:fma:0`, not against probe-off**, or the placement artefact
contaminates the estimate by a third of the M4-hypothesis signal.

That is also why C0' was promoted from "run only if C2 lands close to the M4
prediction" to a likely second receipt: on M4 the placement term is not small
relative to the effect, and there is no reason to assume it is smaller on M5.

**How stable is this anchor?** Not very, and that is worth saying before it is
used as a transfer prediction. PR #498 measured the *same* `routed`/`fma` probe
on the same M4 Pro at levels `n = 0, 2, 4, 8` and fitted **3.8 us per `n`
(+/- 1.8)**; this sweep, at `n = 0` and `n = 24`, reads **8.54 us per `n`**.
Those differ by 2.2x and the smaller estimate's own interval does not reach the
larger. Two mechanisms could explain it and we cannot separate them with the
data in hand: (i) #498's levels are all at or below its measured knee of `n >= 8`,
so it may be pricing a partly-absorbed region while `n = 24` is past it, which
would make the price genuinely superlinear; or (ii) one or both slopes are
simply noisy two-to-four point fits on a shared host. The consequence is that
the "M4 hypothesis" band in section 10.3 should be read as an order of
magnitude, not a calibrated prediction — which is exactly how the pre-registered
read-out in section 10.3 treats it, and why the decisive test is whether the M5
result is *near zero* rather than whether it matches a specific M4 number.

### 10.5 M5 result at n = 24

> **Superseded in part by section 10.8.** The n = 64 receipt fired the
> pre-registered "M4 price after all" branch: the placement-free marginal price
> on M5 is **8.07 us per injected op**, which contains the M4 anchor of 8.54.
> The measurement below is unchanged and correct; the *interpretation* — "M5
> absorbs free ALU" — does not survive as a general statement. Read section
> 10.8 before using anything in this subsection.

Receipt `ecd89cac-b21e-4948-b619-5ac106c8fe48`, marker `senpai-r93-probe-routed-fma-24`,
spec `routed:fma:24`, W&B [`59o0mk6y`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/59o0mk6y),
official timestamp 2026-08-09T06:24:07Z.

**Gates first, because a correctness failure here would mean a broken instrument
rather than a fact about M5.** `passed_correctness = true`, `max_abs_diff = 0`
over `checked_steps = 1344` in 11 cases, `error = ""`, both speedup floors
passed, `gpqa_ttft_passed` 9/9, `semantic_gpqa_passed` 9/9. The probe is
bit-exact on the ranked host, as rule 45's sink-store argument requires and as
section 10.4 already showed on M4.

| quantity | value |
|---|---|
| candidate decode | **4943.6468 us/token** |
| section 2.3 null mean (n = 5) | 4910.9253 us/token |
| **delta** | **+32.72 us = +0.6663 %** |
| se of one draw against a mean of 5, `sd*sqrt(1+1/5)` | 15.81 us |
| t, df = 4 | 2.07 (two-sided crit 2.776) |
| 95 % CI on delta | [-11.2, +76.6] us = **[-0.23 %, +1.56 %]** |
| candidate prefill | 187.8604 us/token (**-0.006 %** vs the null mean) |

**The verdict is the low branch, and it is not close.** The corrected
issue-bound band of section 10.3 is +5.6 % to +11.1 % against probe-off, i.e.
**+275 us to +547 us**. The measured effect is +32.7 us. The *upper* end of the
95 % interval, +76.6 us, is still 3.6x below even the **low** edge of that band
and 7.1x below its high edge. The read-out rule fires unambiguously:

> **M5 absorbs free ALU. Rule 55 transfers to the ranked host. #512 and #513 are
> not exposed to a regime change, and the ALU-for-bytes trade is live on M5.**

Four details worth stating plainly:

1. **The injected load is not a token amount.** The ladder sits *inside* the kernel's
   main K loop (`nezukoR93LoopBody`, line 4207), so `n = 24` is 24 x 4 = **96
   fma per K iteration**, not 96 fma per dispatch. M5 swallowed that for an
   effect it cannot distinguish from zero.
2. **The effect is not individually significant** (t = 2.07 < 2.776). I am not
   claiming M5 charges +0.67 %; I am claiming it charges far less than +5.6 %,
   the low edge of the issue-bound band. That is the question the arm was built
   to answer, and a one-sided bound is all the read-out needed.
3. **The M4 hypothesis was transferred as a fraction, not as microseconds.**
   +205 us on M4's 8151 us step is +2.51 %; carried across as a *fraction* that
   is +2.5 % of M5's 4911 us step, or +123 us. Carried across as *absolute
   microseconds* it would be +205 us = +4.2 %, which straddles the 3 % low
   trigger. The measured +0.67 % is below both conventions, so the choice did
   not decide the verdict here — but the pre-registration should have said which
   convention it was using, and it did not.
4. **The prefill control behaved.** -0.006 % against the null mean, versus the
   0.103 % prefill sigma of section 2.3 — a decode-only injection produced a
   decode-only effect, which is the same internal control that validated Arm B.

**M5 absorbs more than M4 does, not less.** Per injected fma the M4 anchor is
8.54 us (section 10.4) against 1.36 us here — and M4 is the machine at 92.2 % of
sequential-read peak while the advisor's figure for M5 is ~63 %. A machine with
*more* spare bandwidth absorbing free arithmetic *better* is the wrong way round
for a pure bandwidth story. The consistent reading is that the M5 decode step is
**latency-bound** rather than throughput-bound: dependent-load latency, not
bandwidth or ALU issue, sets the step time, and free arithmetic hides in the
same stalls. That distinction matters for how #512 and #513 should be read, and
section 10.6 states it as a caveat rather than a result, because this arm was
not designed to measure it.

### 10.6 What one receipt could and could not license (superseded by 10.8)

> This subsection is kept as written before the n = 64 receipt, because its
> first paragraph is exactly the claim that receipt overturned and the record
> should show that. **Section 10.8 carries the operative licensing statement.**

**Provisionally licensed, on n = 24 alone.** Spending ALU to avoid DRAM traffic
is not charged on M5 at the scale these experiments contemplate. #512's top-8
router screen and #513's layer-0 block-exponent compaction both trade
arithmetic for bytes; neither is exposed to the regime change this arm was
built to detect. *(Section 10.8 withdraws this as a general statement: above a
threshold below n = 64, M5 charges 8.07 us per injected op.)*

**Not licensed.** This arm shows that *adding* arithmetic is nearly free. It
says nothing about whether *removing* bytes pays back proportionally. If the
decode step is latency-bound rather than bandwidth-bound, byte reductions that
do not also shorten the dependent-load chain may return less than their
byte-count suggests. That is exactly the asymmetry section 8.0 found on the
dispatch axis, where addition cost 2.34 us/dispatch but rule 53 showed removal
recovering approximately nothing. **The symmetric mistake would be to read this
receipt as a prediction that #512 and #513 will win.** It is a statement that
they will not *lose* on the ALU they spend. *(This paragraph survives 10.8
intact, and its caution is now the main finding rather than a hedge.)*

**The open question this arm leaves.** One receipt at one load cannot separate
"M5 absorbs free ALU" from "the probe did not execute on M5", because both
predict a near-zero delta. Two things bear on it. The argument: `routed` is
injected at a single runtime-built kernel site (lines 7977-8112) with no
architecture-conditional variant, so M5 compiles the same source M4 does; the
`_nax` selection AGENTS.md warns about applies to MLX's built-in prefill
kernels, not to this custom decode gather-GEMM. The evidence: section 10.7.

### 10.7 Liveness and slope at n = 64 (pre-registered before submission)

Written before the receipt was requested, for the same reason section 10.3 was.

The n = 24 result is a bound, not a measurement, and it shares its signature
with a dead instrument. `routed:fma:64` — the probe's maximum, 2.67x the load —
resolves both:

| outcome at n = 64 | reading |
|---|---|
| **~+1.8 %** (+87 us, 5.5 null sd) | probe live and scaling linearly; the n = 24 bound is real and the M5 per-fma price is ~1.4 us |
| **~+6.7 %** | M5 charges at the M4 per-fma price after all; the n = 24 point was a low draw |
| **~0 %** | probe inert on M5; section 10.5 must be withdrawn |

This is a strictly better use of the slot than the C0' placement control, and it
replaces it:

- C0' cannot detect a dead probe — `n = 0` and `n = 24` read identically under
  both "absorbed" and "inert".
- **n = 24 and n = 64 carry the identical pipeline object and the identical
  128 MiB pool binding, so the slope between them is placement-free by
  construction.** That is precisely what C0' was for, obtained without spending
  a receipt on it.
- The n = 64 point is predicted at 5.5 null sd, comfortably above the 0.89 %
  single-receipt floor, whereas C0's expected ~0.9 % placement term sits *at*
  that floor and would have been unmeasurable in one receipt anyway.

Arm C therefore spends 2 of its 6 permitted receipts, not 3.

*(Written before the receipt. It came back on the `~+6.7 %` branch, which
reinstated C0' for a reason section 10.7 did not anticipate — see 10.8. Arm C
spends 3.)*

### 10.8 M5 result at n = 64: the pre-registered reversal

Receipt `ab3a2433-2553-4946-8502-d04814565e17`, marker
`senpai-r93-probe-routed-fma-64`, spec `routed:fma:64`, official commit
`68ab5ce2`, W&B [`fotwz1v2`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/fotwz1v2),
official timestamp 2026-08-09T06:58:58Z.

Gates: `passed_correctness = true`, `max_abs_diff = 0` over 1344 checked steps
in 11 cases, `error = ""`, both floors passed, GPQA TTFT 9/9, semantic GPQA 9/9.
Baseline health is inside the section 2.3 null envelope on both axes
(13831.36 us decode against a null range of 13819.4-13870.7; 371.09 us prefill
against 364.9-383.6), so this is not a bad-baseline draw.

| quantity | n = 24 | n = 64 |
|---|---|---|
| candidate decode | 4943.6468 us | **5266.4297 us** |
| delta vs the n = 5 null mean | +32.72 us = +0.6663 % | **+355.50 us = +7.2391 %** |
| t against the null (4 df, crit 2.776) | +2.070 | **+22.489** |
| 95 % CI on the delta | [-0.2273 %, +1.5599 %] | **[+6.3455 %, +8.1326 %]** |
| prefill control | -0.0061 % | -0.2462 % (t = -2.19, ns) |

**Estimator 2, the placement-free slope.** n = 24 and n = 64 carry the identical
pipeline object and the identical 128 MiB pool binding, so their difference
prices injected ALU with the placement term algebraically removed:

```
(5266.4297 - 4943.6468) / (64 - 24) = +8.0696 us per injected op
                        95 % CI      [ +6.6532, +9.4859 ]
    shift +322.78 us = +6.5292 % of the n = 24 step,  t = +15.816 (4 df)
```

**The pre-registered read-out fires the second branch.** Section 10.7, written
before this receipt was requested, named +1.8 % for "live and linear at the
n = 24 price", ~0 % for "inert", and **~+6.7 % for "M5 charges at the M4 per-fma
price after all"**. The observed rung-to-rung shift is **+6.53 %**. The M4
anchor of 8.54 us/op (section 10.4) lies inside the [6.65, 9.49] CI.

Two things follow immediately, and the second one is the arm's real result.

1. **The probe is live on the ranked M5.** +355 us is 24.6 null standard
   deviations. Every "the probe silently did nothing on M5" reading of section
   10.5 is dead, which is exactly what this receipt was bought for.
2. **Section 10.5's headline does not survive.** "M5 absorbs free ALU" is not
   true as a general statement. There is a load — below n = 64 — beyond which
   M5 charges the full M4 price per injected op.

#### Why n = 24 and n = 64 disagree, and what is still open

The two M5 points are mutually consistent only if the response is not a straight
line through the null. Extrapolating the placement-free slope back to n = 0
gives 4749.98 us, which is **160.95 us (3.28 %) below** the null mean. A
positive-cost injection cannot make the kernel faster, so one of two things is
true:

| reading | mechanism | implication |
|---|---|---|
| **(A) knee** | placement term ~0; the response is convex, with the first ~24 ops absorbed at 1.36 us/op and the next 40 charged at 8.07 us/op (5.9x) | M5 has a *higher* ALU absorption threshold than M4, whose knee is already below n = 24; small ALU additions really are free on M5 |
| **(B) placement** | the response is linear at ~8.07 us/op from n = 0, and the probe-instrumented kernel is 3.28 % *faster* than base at n = 0 | ALU is charged from the first op on M5; every byte-for-ALU trade must be costed at 8.07 us/op |

Reading (B) is not a stretch: **section 10.4 measured a placement term of the
same sign directly on M4**, where `routed:fma:0` ran 0.88 % faster than
probe-off. It only has to be 3.7x larger in relative terms on M5.

A useful intermediate: if M5's placement term merely *equalled* M4's -0.88 %
(-43.2 us), the implied 0 -> 24 segment slope would be (32.72 + 43.2) / 24 =
**3.16 us/op**, still 2.6x below the 24 -> 64 slope. **A knee therefore survives
unless M5's placement term is roughly four times M4's.**

**This is what reinstates C0'.** Section 10.7 was right that n = 64 replaces
C0' for *liveness* and for the *marginal slope*, and wrong that it replaces it
entirely: it cannot decompose the n = 24 point. C0' now measures the placement
term directly, and it is a well-powered test rather than the marginal one
section 10.7 declined:

- reading (A) predicts C0' ~ **4910.9 us** (the null);
- reading (B) predicts C0' ~ **4750.0 us**;
- the separation is 160.9 us = **11.2 null sd**, which is 3.7x the 0.89 %
  single-receipt resolution floor of section 3.

Submitted as `a000a397-68cc-4514-8cfe-b2a9837d49e7`, spec `routed:fma:0`,
commit `c5471a71`; read out in section 10.9.

#### The comparison that should worry the programme most

Expressed as a fraction of each machine's decode step:

| machine | slope | step | cost per op, as % of step |
|---|---|---|---|
| M4 Pro (section 10.4, segment 0 -> 24) | 8.5417 us/op | 8151 us | 0.1048 % |
| M5 Max (this receipt, segment 24 -> 64) | 8.0696 us/op | 4910.9 us | **0.1643 %** |

Injected ALU costs the **same absolute microseconds** on both machines, so on
the 1.66x shorter M5 step it costs **1.57x more as a fraction**. Two caveats,
both real:

- **The segments do not match.** M4 was measured over 0 -> 24 and M5 over
  24 -> 64. If M4 is also convex, its 24 -> 64 slope is larger and the ratio
  shrinks. The fix costs no submission slot: `bash
  research/r93-runs/armc_local_sweep.sh 200 routed:fma:0 routed:fma:24
  routed:fma:64` on this host. It is listed as a follow-up rather than run
  because the local benchmark lock was held by the C0' receipt watcher.
- **The ladder is built to be throughput-limited, not latency-limited.**
  `nezukoR93LoopBody` emits four independent accumulator chains precisely so
  that it prices issue throughput. A throughput-limited addition costing the
  same wall time on 40 cores as on 20 is not what a core-count model predicts;
  it should be roughly halved. Candidate explanations — none tested here — are
  that the batch-1 routed gather-GEMM does not fill M5's extra cores, so the
  added work serializes on the same occupied subset, or that the added issue
  rate is clock- rather than core-limited. **This is flagged, not claimed.**

#### Operative licensing statement (replaces 10.6)

**Validated, and this is the useful half.** ALU cost transfers from M4 to M5 *in
absolute microseconds* at the margin: 8.07 us/op [6.65, 9.49] against M4's 8.54.
Rule 55's M4-only provenance is no longer a reason to distrust ALU-side pricing
for the ranked host. That was the "single largest unpriced risk in the
programme", and the answer is that the M4 evidence base is usable.

**Withdrawn.** "Spending ALU to avoid DRAM traffic is not charged on M5." It is
charged, at 8.07 us per unit of `n` — where one unit of `n` is 4 fma per K
iteration per thread — which is **0.164 % of the M5 decode step per unit**.

**Actionable for #512 and #513.** Both trade arithmetic for bytes. Neither is
refuted by this arm, but both should now be quoted with their added fma per K
iteration so the ALU side can be priced at 8.07 us per `n`-equivalent and set
against the bytes removed. Whether the absorption threshold of reading (A)
covers their addition is precisely what C0' decides.

**Still not licensed, and unchanged from 10.6.** This arm prices *adding* ALU.
Section 8.0 and rule 53 showed on the dispatch axis that addition and removal
are wildly asymmetric — 2.34 us/dispatch to add, approximately nothing recovered
on removal. Nothing here predicts that removing bytes pays back proportionally.

---

## 11. Wrap-up

### 11.1 Deliverables

| # | Assignment deliverable | Where | Status |
|---|---|---|---|
| 1 | Arm A: >= 5 machine-code-identical candidates through the official channel | section 2, ledger rows 1/2/4/6/8 | done, n = 5 |
| 2 | Arm B: >= 3 rungs of a monotone cost ladder, prefill as internal control | section 4, ledger rows 3/5/7 (+ 5 nulls as the K = 0 rung, n = 8 fit) | done |
| 3 | Minimum resolvable decode delta at n = 4, 6, 8 | section 3 | done |
| 4 | Written submission-cadence policy | section 5 and `cadence-policy.md` | done |
| 5 | Re-derived PR #137 M4 -> M5 transfer factor | section 6 and `pr137-transfer-factor.md` | done |
| 6 | Every submission logged to W&B | section 11.3 | done, 10 runs |

Arm C (M5 regime ladder) was added by advisor revision and is reported in
section 10. Its stopping rule did not fire (section 10.1), so it ran.

### 11.2 Headline numbers

| quantity | value | evidence |
|---|---|---|
| **True-null decode CV of the official channel** | **0.2939 %** (95 % CI [0.176 %, 0.844 %], n = 5, exact chi-square) | section 2.2 |
| True-null prefill CV | 0.1027 % (95 % CI [0.062 %, 0.295 %]) | section 2.2 |
| Baseline decode CV (same 5 receipts) | 0.1470 % | section 2.2 |
| Baseline prefill CV (same 5 receipts) | 2.2036 % | section 2.2 |
| **Min resolvable decode delta, n = 4 / 6 / 8** | **0.508 % / 0.378 % / 0.315 %** | section 3 |
| Min resolvable decode delta, single receipt vs the n = 5 null | 0.89 % | section 3 |
| **M5 price of one extra decode dispatch** | **2.3403 us** (95 % CI [2.277, 2.404], n = 8, R^2 > 0.999) | section 4 |
| Whole-token dispatch census priced at that slope | 945.5 us = **19.2 %** of decode | section 8.1 |
| PR #137 M4 -> M5 transfer factor | **\|T\| < 0.5**, sign not resolved | section 6 |
| **M5 price of one injected fma in the routed gather-GEMM, n = 24 -> 64** | **8.07 us** (95 % CI [6.65, 9.49]) - placement-free, matches the M4 price of 8.54 us | section 10.8 |
| Same price read as a single point at n = 24 against the null | 1.36 us (95 % CI [-0.46, +3.19]) - **superseded**, confounded with placement | section 10.5, 10.8 |

### 11.3 W&B runs

Project `wandb-applied-ai-team/mlxfast-maple`. One run per official submission,
each carrying the receipt's candidate and baseline decode/prefill seconds per
token, both speedups, the official score, the correctness gate fields, and the
delta against the n = 5 null reference.

| # | marker | W&B run | submission id |
|---|---|---|---|
| 1 | null-1 | [`3szqrztf`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/3szqrztf) | `25e1f18e-ef83-491f-8a65-8944765bfe46` |
| 2 | null-2 | [`0doaq0w0`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/0doaq0w0) | `d11026c9-25c5-498c-936f-ed3db3335c30` |
| 3 | ladder-K240 | [`fpi2ynyl`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/fpi2ynyl) | `99309c61-2b7e-4ce8-bb74-52bd3da8a03c` |
| 4 | null-3 | [`fvm3v67i`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/fvm3v67i) | `05dd8bbf-c436-447c-99a8-8024d0fc023f` |
| 5 | ladder-K800 | [`qaempae6`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/qaempae6) | `f8719c48-8df6-4570-abf1-1c9a369c64e0` |
| 6 | null-4 | [`0ecng8mc`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/0ecng8mc) | `ab6a15a1-4d79-4c51-ac46-bd97fde2e1bf` |
| 7 | ladder-K60 | [`xlaup9j4`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/xlaup9j4) | `b835a980-9c6a-48f3-a9d0-c5961ed1aac4` |
| 8 | null-5 | [`92snii58`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/92snii58) | `4fec8e2d-3fa1-4a99-a9a5-e6883aee7497` |
| 9 | probe-routed-fma-24 | [`59o0mk6y`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/59o0mk6y) | `ecd89cac-b21e-4948-b619-5ac106c8fe48` |
| 10 | probe-routed-fma-64 | [`fotwz1v2`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/fotwz1v2) | `ab3a2433-2553-4946-8502-d04814565e17` |

All ten receipts passed every correctness gate: `passed_correctness = true`,
`max_abs_diff = 0`, 1344 checked steps over 11 cases, both 0.95 floors true,
GPQA TTFT 9/9, semantic GPQA 9/9. Every one is `rejected` for ranking, which for
this arm is the intended outcome: `rejected` here means only "did not beat the
current best", and section 8.2 records that separation explicitly.

### 11.4 Responses to advisor feedback

**"The PR looks unstarted."** It was not. Every commit on
`maple-tanjiro/r93-m5-receipt-channel` was local until this submission, because
the student role pushes only through `submit_experiment_result`. Ten official
receipts had already been collected when that comment was written. Nothing was
blocked; only the advisor's view was stale.

**Budget raised to 14-18, Arm C <= 6.** 11 slots used: 5 Arm A, 3 Arm B, 3
Arm C. Section 10.7 pre-registered the n = 64 point as a saving of the third
receipt; the result reversed the n = 24 reading instead, which reinstated the
C0' placement control as the arm's decisive point. Arm C therefore spends 3 of
its 6, not 2.

**Rule 53 (#502): no decode dispatch residue.** Reconciled in section 8.0. The
2.3403 us/dispatch slope is the price of *adding* a dispatch; #502 shows
*removing* one recovers approximately nothing. Both are true and the asymmetry
is the finding. Section 8.3 retires the three follow-up candidates that rested
on dispatch-count reduction and keeps only the two that rest on bytes.

**Rule 55 (#498): three dominant decode kernels bandwidth-bound on M4 Pro.**
Section 10 tests whether that transfers to M5, which is the question the rule's
M4-only provenance leaves open. The answer changed once the second rung landed.
At n = 24 the injected ALU looked nearly free on M5 (+0.67 %, not significant);
at n = 64 it is not free at all (+7.24 %, t = +22.5). The placement-free
segment price is 8.07 us per injected fma, which is statistically
indistinguishable from the M4 Pro price of 8.54 us. Section 10.8 replaces the
provisional licence issued in section 10.6: **M5 does not have a wider
free-ALU allowance than M4 Pro over the range this arm can see.** The remaining
open question is whether the free region below n = 24 is a genuine knee or an
artefact of the probe's placement cost, which is exactly what the C0' control
in section 10.9 answers.

**Arm C as "the single largest unpriced risk in the programme".** Priced, at
3 receipts. See sections 10.8 and 10.9 for the verdict.

### 11.5 Reproduction

Every number in this document regenerates from committed receipts with no
network access and no GPU:

```bash
python3 research/r93-runs/null_stats.py      # section 2 (Arm A)
python3 research/r93-runs/ladder_fit.py      # sections 4, 6, 8.1 (Arm B)
python3 research/r93-runs/probe_slope.py     # section 10 (Arm C)
python3 research/r93-runs/channel_noise.py research/r93-runs/receipts-latest.json
python3 research/r93-runs/critique_checks.py research/r93-runs/receipts-latest.json
```

`receipts/*.json` holds the ten official receipts;
`receipts-latest.json` is the 1185-point programme corpus used in section 9.
`manifest.json` maps every marker to its submission id, source commit, probe
spec, and W&B run.

The scored file `Sources/MLXFastModel/LagunaRuntimeModel.swift` is restored to
the assignment base in the final commit: this arm measures the channel, and
merges no runtime change.

