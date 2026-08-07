# Attributing the decode "dispatch tax" (PR #268, maple-fern)

**Headline.** The tax is real and refundable, but it is **not a per-dispatch
cost**. It is a per-*barrier* cost: MLX charges ~1.30 µs each time it has to
close an intra-encoder wave with a `memoryBarrier`, and only ~0.12 µs for the
dispatch itself. Fusing two *dependent* kernels refunds
**+1.4234 µs/step (95 % CI [1.3732, 1.4736], n = 288 segments, 6 arms,
df = 250)**; removing a dispatch that does not delete a dependency edge refunds
**+0.123 µs (CI [0.029, 0.217])**, 12× less.
This reconciles PR #241's "1.4 µs/dispatch" and PR #269's removal-measured
1.233 µs/dispatch, and it predicts #269's headline number to within 0.95 σ.

A footprint sweep over four orders of magnitude gives a second, independent and
tighter estimate of the same constant — **1.3489 ± 0.0181 µs** at zero bytes —
with a byte slope that lands on this host's real DRAM bandwidth (§4.6). And the
cost is charged per unit of *serial depth*, not per dependency edge: 80 real RAW
edges arranged in parallel cost 4 barriers and nothing measurable (§4.9). That
last result also closes the tempting cheap exploit — you cannot refund barriers
by reordering graph construction, because MLX's scheduler already extracts the
available parallelism.

**Host:** Apple M4 Pro, 20 GPU cores, 48 GiB, macOS 26.5.2, Metal 4, Apple GPU
generation 16. **This is not the ranked host.** It never selects the `_nax`
kernel variants the ranked M5 Max uses, and its decode step is ~2x the M5's.
Every microsecond here is directional, not rankable.

**Workload:** the real teacher-forced golden decode — 512-token seed, one-token
steps — driven through the scored runtime, not a microbenchmark.

---

## 0. The question

PR #241 measured, off the critical path, "something like 1.4 µs per dispatch"
in decode. That number is the entire justification for the fusion programme:
if it is real and refundable, removing dispatches is the primary decode
direction; if it is an artefact, the programme is a mirage.

Two hypotheses:

* **H-MECH** — the tax is dominated by exactly one identifiable mechanism.
* **H-REFUND** — removing one dispatch from the live decode chain refunds
  ≥ 1.0 µs of wall-clock step time.

Candidate mechanisms:

| id | mechanism | signature if true |
|----|-----------|-------------------|
| E1 | CPU-side per-op encode starving the GPU | cost appears in the commit→complete **gap**, and tracks CPU work |
| E2 | GPU command-processor fixed launch cost | cost appears in **GPU-busy** time and tracks dispatch count |
| E3 | cache flush/invalidate scaling with dirty footprint | cost scales with **bytes** touched per dispatch |
| E4 | residency/bookkeeping scaling with distinct resources | cost scales with the number of **distinct buffers** live |
| E5 | command-buffer commit overhead | already refuted in PR #241 |

A sixth mechanism was not on the pre-registered list and emerged from the data
(§4.3, §4.4, §4.5). It is the one that survives:

| id | mechanism | signature if true |
|----|-----------|-------------------|
| E6 | loss of intra-encoder overlap at a `memoryBarrier` | cost tracks **barriers**, not dispatches; appears in GPU-busy; charged even when the dependency is dead |

## 1. Instrument

Two patches, applied only to build the research worker and never committed to
`Sources/` or `Vendor/` (see §7):

* `research/fern_tax_device_counters.patch` →
  `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp`.
  Counts `maybeInsertBarrier`, `dispatch_threadgroups`, `dispatch_threads`,
  `end_encoding`, `commit`, and accumulates per-command-buffer
  `GPUStartTime→GPUEndTime` (**gpu_ns**, GPU busy),
  `kernelStartTime→kernelEndTime` (**kernel_ns**, the CPU driver's own work)
  and `commit→completion` (**span_ns**). Exposed as one `extern "C"` read.
* `research/fern_tax_inject.patch` → `Sources/MLXFastModel/LagunaRuntimeModel.swift`.
  Adds `enum LagunaTaxProbe`, driven entirely by environment variables and
  defaulting to `mode=none`, which injects K extra dispatches per decoder layer
  at a live site, in several *shapes*.

The shapes are the experiment:

| mode | what it injects at each of the 40 layers | dispatches | barriers |
|------|------------------------------------------|-----------|----------|
| `chain40` | K dependent scalar multiplies, anchored in front of a live consumer | +K·40 | +K·40 |
| `fat40`   | K dependent adds, each re-reading one buffer of `--bytes` | +K·40·1.5 | same as dispatches |
| `dist40`  | as `fat40` but each add reads a **different** buffer from a pool of `--pool` | same as `fat40` | same |
| `fan40`   | K **mutually independent** slices of a live tensor, joined by one concat | same as `fat40` | **half** |
| `spin40`  | pure CPU busy-spin at the same 40 positions, no GPU work | 0 | 0 |
| `chain`/`indep`/`distinct`/`diamond1` | the same dispatch counts issued **off** the live chain | matched | varies |

`anchor=1` splices the injected value back into the live tensor as `x + (t - t)`,
so it is a true data dependency; `anchor=0` issues the identical dispatches with
no live dependency. That switch is the cleanest single contrast in the battery.

**Numerics.** The splice is exactly zero-preserving for finite inputs, and every
arm reported here ran the full golden teacher-forced decode with a per-step token
check: **0 divergences in every arm**. (Caveat: `a - a` would produce NaN on a
non-finite `a`, and `x + 0` flips `-0` to `+0`. Neither fired.)

## 2. Estimator

One reducer, `research/fern_tax_stats.py`, used for every number in this
document and for everything logged to W&B (`research/fern_tax_wandb.py` calls
its `fit()` rather than re-deriving points — PR #241 shipped two reducers that
disagreed by ~6% because they centred contrasts differently).

* unit of replication = one **segment median** (first `--drop` steps discarded)
* the K schedule is **palindromic** (`0,1,2,4,4,2,1,0`) and repeated `--blocks`
  times, so a monotone thermal/clock drift inside a block cancels
* both x and y are centred on their **block mean** before the slope is formed,
  so no arm acts as a privileged reference
* CI = classical OLS t interval on df = n_segments − n_blocks − 1
* passing several TSVs pools them with a **(file, block)** fixed effect, and
  prints each arm's own slope beside the pooled line — an arm off the pooled
  line falsifies that regressor

## 3. Baseline decode step on this host

| quantity | value |
|---|---|
| wall / step | 8.18 ms |
| dispatches / step | 406 |
| barriers / step | 247 |
| commits (command buffers) / step | 67–68 |
| encoders / step | 75–76 |
| GPU busy / step (`GPUEndTime−GPUStartTime`, summed) | 7.95 ms |
| GPU span / step (`min start → max end`) | 8.03 ms |
| CPU driver / step (`kernelEndTime−kernelStartTime`, summed) | 0.60 ms |
| GPU-busy fraction of wall | 0.971 |

Per layer that is 406/40 ≈ **10.2 dispatches** and 247/40 ≈ **6.2 barriers**.
The command-buffer partition (67–68 commits, 75–76 encoders) is stable to
±1 across every arm and every K in the battery, so no arm's slope is
contaminated by MLX re-partitioning the step into a different number of
command buffers.

Two facts frame everything below:

- The GPU is busy 97.1% of the wall clock. Only 0.24 ms/step of the 8.18 ms
  is *not* inside a command buffer's GPU execution window.
- The CPU driver spends 0.60 ms/step in `kernelStart→kernelEnd`, i.e.
  1.48 µs of *host driver* time per dispatch. That number is numerically
  close to the ~1.4 µs tax and is the single most seductive false lead in
  this experiment; §4 A2/A3 kill it.

## 4. Results

### 4.1 A2 — pure-CPU spin at the same encode position (direct E1 test)

`spin40` injects `K × 1400 ns` of real busy-wait (a `DispatchTime.now()`
deadline loop, not elidable) at each of the 40 in-chain sites, and issues
**zero** extra GPU work. Dispatch/barrier/commit counters are identical at
every K, confirming the arm is purely a CPU perturbation.

| K | injected CPU µs/step | wall ms | Δwall vs K=0 | dispatch | barrier |
|---|---|---|---|---|---|
| 0 | 0 | 8.1778 | — | 406 | 247 |
| 1 | 56 | 8.1971 | +19.3 µs | 406 | 247 |
| 2 | 112 | 8.1867 | +8.9 µs | 406 | 247 |
| 4 | 224 | 8.1940 | +16.3 µs | 406 | 247 |

**FE-OLS: +0.0497 ± 0.0293 µs of wall per injected CPU µs, 95% CI
[−0.009, +0.108], t=1.7, n=48.**

A CPU-paced step (E1) predicts slope ≈ 1.0. The measured slope is
**0.05**, and 1.0 is 32 standard errors away. 224 µs/step of extra host
work — 2.7% of the whole step — is absorbed almost completely. Whatever
paces this decode step, it is not host time spent in the layer loop.

*(Caveat, carried from the pre-registered critique: MLX is lazy, so this
spin delays the graph-building thread rather than MLX's encoding thread.
It bounds host slack on the call path, not encode-thread slack. The
decomposition in §4.2 is the stronger E1 test and agrees.)*

### 4.2 A3 — where does the added time land? (E1 vs E2, per barrier)

Same arms, same fit, but the response is swapped for the GPU-side
timestamps from the command-buffer completion handler. `gap_ms` is
`span − busy`: everything between the first command buffer starting and
the last one finishing that is *not* GPU execution, i.e. exactly the place
CPU starvation would show up.

| arm | y = wall | y = GPU busy | y = gap (span−busy) | y = CPU driver |
|---|---|---|---|---|
| `chain40` | **+1.3778 ± 0.0535** | +1.3696 ± 0.0450 | +0.0067 ± 0.0177 | +0.0236 ± 0.0479 |
| `dist40_8k` | **+1.4871 ± 0.0488** | +1.4898 ± 0.0444 | −0.0237 ± 0.0131 | +0.2141 ± 0.0346 |

(µs/step per added barrier, ± standard error, n=48 each.)

- **99.4%** (chain40) and **100.2%** (dist40) of the wall-clock tax
  reappears inside GPU busy time.
- The gap slope is **statistically zero** in both arms (|t| ≤ 1.8) and its
  CI excludes anything above 0.05 µs. The GPU is never left waiting.
- CPU driver time per added dispatch is 0.02–0.21 µs, **7–60× smaller**
  than the wall cost. The 1.48 µs/dispatch of baseline host driver time
  noted in §3 is real but is fully hidden behind GPU execution — it is a
  coincidence of magnitude, not the mechanism.

**E1 is refuted.** The tax is spent by the GPU, inside command buffers.

### 4.3 A1 — the tax is a *barrier* cost, not a *dispatch* cost

This is the central result and it changes what the number means.

Four in-chain arms add K units of work at the same 40 anchored sites, but
with different dependency structure, so they add barriers and dispatches in
different ratios:

| arm | what each unit is | Δdispatch @K=1/2/4 | Δbarrier @K=1/2/4 |
|---|---|---|---|
| `chain40` | `y = y * one`, K times, strictly serial | +40 / +80 / +160 | +40 / +80 / +160 |
| `fat40_8k` | K serial 8 KiB reductions off one buffer | +120 / +160 / +240 | +120 / +160 / +240 |
| `dist40_8k` | same, over a 256-buffer pool | +120 / +160 / +240 | +120 / +160 / +240 |
| `fan40` | K **mutually independent** anchored slices | +80 / +160 / +240 | +80 / +120 / **+120** |

Three of the four arms add barriers and dispatches in exactly 1:1, so they
cannot separate the two. `fan40` can: its added kernels are mutually
independent, so MLX only needs a barrier in front of the group, and between
K=2 and K=4 its barrier count stops growing while its dispatch count keeps
going.

Per-arm single-regressor fits, y = wall (µs/step):

| arm | per **dispatch** | per **barrier** |
|---|---|---|
| `chain40` | +1.3778 ± 0.0535 | +1.3778 ± 0.0535 |
| `fat40_8k` | +1.3469 ± 0.0593 | +1.3469 ± 0.0593 |
| `dist40_8k` | +1.4871 ± 0.0488 | +1.4871 ± 0.0488 |
| `fan40` | **+0.8020 ± 0.0581** | **+1.5582 ± 0.0658** |

Pooling all four with a (file, block) fixed effect and asking whether *one*
slope explains every arm:

| regressor | pooled slope | arms off the line |
|---|---|---|
| **barrier** | **+1.4266 ± 0.0282** (t=50.6, n=192) | **none** |
| dispatch | +1.2261 ± 0.0352 (t=34.9, n=192) | `dist40_8k`, `fan40` |

Read as a *dispatch* cost the arms disagree by 1.9× (0.80 → 1.49) and two of
four fall off the pooled line. Read as a *barrier* cost they agree within
15% (1.35 → 1.56) and all four sit on it.

The cleanest single piece of evidence is a within-arm contrast in `fan40`
that needs no pooling and no modelling at all:

| `fan40` K | dispatch | barrier | wall ms |
|---|---|---|---|
| 2 | 566 | 367 | 8.3631 |
| 4 | **646** (+80) | **367** (+0)| 8.3804 (+17.3 µs) |

**80 extra GPU dispatches, anchored to the live tensor, at the same encode
position, adding no barrier, cost 17.3 µs — 0.216 µs each.** The same 80
dispatches in `chain40` (where each one adds a barrier) cost 110 µs.

Pricing both regressors in one fixed-effects fit (`--joint`), pooled over
the four arms:

| regressor | µs/step | 95% CI | t |
|---|---|---|---|
| **dispatch** (barrier-free) | **+0.173** ± 0.085 | [+0.007, +0.339] | 2.0 |
| **barrier** | **+1.241** ± 0.095 | [+1.054, +1.427] | 13.0 |

`fan40` alone identifies the same split independently (dispatch
+0.137 ± 0.087, barrier +1.330 ± 0.158, n=48), because its
barrier-per-dispatch ratio collapses between K=2 and K=4.

**So the ~1.4 µs "per dispatch" is really 1.24 µs of barrier plus 0.17 µs
of launch.** The tax has been misnamed: 88% of it is the cost of a
*dependency edge*, not the cost of a *dispatch*.

### 4.4 Anchoring control — the barrier is charged even off the critical path

`fat40_8k_free` is `fat40_8k` with `DARKBLOOM_TAX_ANCHOR=0`: identical work at
identical encode positions, but the injected chain never feeds back into the
residual stream, so none of it is on the data-dependency path from this token's
input to this token's logits. MLX still emits the kernels, and — because they
alias the same scratch buffer — still emits barriers, but the barrier count no
longer tracks K:

| `fat40_8k_free` K | dispatch | barrier | wall ms | Δ vs K=0 |
|---|---|---|---|---|
| 0 | 406 | 247 | 8.1754 | — |
| 1 | 446 (+40) | 287 (+40) | 8.2486 | +73.2 µs |
| 2 | 486 (+80) | 287 (**+40**) | 8.2456 | +70.2 µs |
| 4 | 566 (+160) | 301 (+54) | 8.2664 | +91.0 µs |

The K=1→K=2 step is a second model-free contrast, in a different arm and a
different dependency regime from `fan40`, and it says the same thing:
**40 additional GPU dispatches that add no barrier cost −3.0 µs, i.e.
nothing.** The K=2→K=4 step adds 80 dispatches and 14 barriers for +20.8 µs,
or 1.49 µs per barrier with dispatches free.

Single-regressor fits: +0.478 ± 0.075 µs per dispatch (arms disagree),
+1.719 ± 0.155 µs per barrier. The joint fit on this arm alone gives
dispatch **−0.074 ± 0.101** (indistinguishable from zero) and barrier
**+1.903 ± 0.296**.

`dist40_8k_free` is the same control run against the 256-buffer pool instead of
a single scratch buffer, and it reproduces the counter pattern exactly
(406/446/486/566 dispatches against 247/287/287/301 barriers; wall 8.1808,
8.2561, 8.2424, 8.2815 ms). Its K=1→K=2 contrast is a *third* model-free
reading of a barrier-free dispatch: **+40 dispatches, +0 barriers, −13.7 µs**.
Its joint fit is dispatch **+0.013 ± 0.066** (t = 0.2, dead zero) and barrier
**+1.782 ± 0.193**.

Two things follow. First, the per-barrier price does **not** fall when the
injected work leaves the critical path — if anything it is higher here than
in-chain (1.78–1.90 vs 1.24 µs). A barrier is an intra-encoder
`memoryBarrier(BarrierScopeBuffers)`; it serializes *everything already
encoded in that command encoder*, so it is charged against the whole step
regardless of whether the tensor that caused it is live. Second, adding both
anchor-0 arms to the pooled joint fit sharpens rather than moves it:

| joint fit, 6 site arms (n=288, blocks=36, df=250) | µs/step | 95% CI | t |
|---|---|---|---|
| dispatch (barrier-free) | **+0.123** ± 0.048 | [+0.029, +0.217] | 2.6 |
| barrier | **+1.300** ± 0.060 | [+1.183, +1.417] | 21.8 |

Every pooling I tried lands on the same pair of numbers: the 4-arm in-chain fit
gives 0.173/1.241, the 5-arm fit 0.120/1.299, the 6-arm fit 0.123/1.300, and a
5-arm fit that swaps in the 256-byte footprint arm gives 0.180/1.223. The sum —
the refund for fusing a *dependent* pair — is 1.41–1.42 µs in all four.

### 4.5 Off-step asynchronous comparators — a barrier costs what it drains

The `chain` / `indep` / `distinct` / `diamond1` arms inject their whole batch in
`LagunaTaxProbe.endStep()` through `asyncEval`, i.e. *after* the token's logits
exist, in their own encoders, free to overlap with the next step. They price the
same dispatches and barriers in the opposite dependency regime.

| `indep` K | dispatch | barrier | wall ms | span ms |
|---|---|---|---|---|
| 0 | 406 | 247 | 8.1877 | 8.038 |
| 40 | 446 | 247 | 8.1852 | 8.032 |
| 80 | 486 | 247 | 8.1808 | 8.029 |
| 160 | 566 | **247** | 8.1821 | 8.029 |

| `chain` K | dispatch | barrier | wall ms | span ms |
|---|---|---|---|---|
| 0 | 406 | 247 | 8.1896 | 8.039 |
| 40 | 446 | 286 | 8.1717 | 8.022 |
| 80 | 486 | 325 | 8.1662 | 8.018 |
| 160 | 566 | **404** | 8.1467 | 7.998 |

`indep` is the fourth and cleanest model-free reading of a barrier-free
dispatch: **+160 dispatches, +0 barriers, wall −5.6 µs**. A 1.4 µs/dispatch tax
would have cost +224 µs here, roughly 40σ away from what happened. Whatever the
"1.4 µs per dispatch" is, it is not a per-dispatch charge.

`chain` is the interesting one. It adds **157 barriers** — more than the 160 the
K=4 site arms add across 40 layers — and wall goes **down** 42.8 µs
(FE-OLS −0.259 ± 0.033 µs per barrier, t = −7.8). So a barrier is not a fixed
charge either.

The reconciliation is that **a barrier costs what it drains**. MLX emits
`memoryBarrier(MTL::BarrierScopeBuffers)` into the *current* encoder
(`device.cpp:363-375`) and every encoder is `DispatchTypeConcurrent`
(`device.cpp:546-548`). The barrier's price is the overlap it destroys between
everything already encoded and everything after it — the ragged tail of the
preceding wave. Between the real per-layer NVFP4 GEMVs that tail is ~1.3 µs.
Among tiny 8 KiB kernels alone in a tail encoder that can slide into the next
step, it is zero.

Two consequences, one reassuring and one limiting:

* The number that matters for fusion is the in-step one. Fusing two dependent
  per-layer kernels removes exactly a barrier of the expensive kind, sitting
  between real work, which is what the 40-site arms measure.
* **1.30 µs/barrier is not a universal constant.** It is the price of a barrier
  placed one-per-layer inside the live decode chain. Do not apply it to
  barriers in prologue/epilogue code, in warmup, or anywhere the surrounding
  wave is small.

Caveat on this arm: `chain`'s `gpu_ms` counter rises by 717 µs while wall falls,
giving gpu/wall = 1.064. Summed `GPUStartTime→GPUEndTime` double-counts when
consecutive command buffers overlap, so `gpu_ms` is only trustworthy when
gpu/wall stays below 1 — it does in every site arm (0.970–0.972) including the
§4.2 decomposition, and it does not here.

### 4.6 E3 — dirty-footprint sweep

`fat40_<bytes>` holds mode, sites, anchoring and pool fixed and varies only the
operand size of each injected kernel, so the counter deltas are identical
(406/526/566/646 dispatches, 247/367/407/487 barriers at K = 0/1/2/4) and the
only thing that changes is how many bytes each added wave dirties.

| operand bytes | µs/step per added dependent pair | 95% CI |
|---|---|---|
| 256 | 1.3746 ± 0.0257 | [1.323, 1.426] |
| 8 192 | 1.3469 ± 0.0593 | [1.228, 1.466] |
| 65 536 | 1.6574 ± 0.0333 | [1.591, 1.724] |
| 262 144 | 2.4179 ± 0.0366 | [2.345, 2.491] |
| 4 194 304 | 18.8484 ± 0.9134 | [16.90, 20.79] |

A 32× increase in dirty footprint from 256 B to 8 KiB moves the price by
**−0.028 ± 0.065 µs (2 %, indistinguishable from zero)**. Above 8 KiB the price
does rise, but linearly in bytes and at an ordinary rate, not as the step
function a cache flush/invalidate would produce. OLS over the full five points —
a **16384× range of footprint** — gives

```
cost(bytes) = 1.3489 +/- 0.0181 us  +  4.172e-6 +/- 9.6e-9 us/byte
residuals: +0.025  -0.036  +0.035  -0.025  +0.001 us
```

Two things are worth stating plainly.

First, the fit is linear to within ±0.036 µs across four orders of magnitude,
and the marginal term is **4.172 µs per MiB of operand = 240 GB/s of footprint
moved per second**. This host's LPDDR5X peak is 273 GB/s, and an elementwise
`t = t + z` moves roughly one footprint of reads plus one of writes, so the
byte term is *exactly* ordinary DRAM traffic running at ~88 % of peak. That is a
free calibration of the whole instrument against a known physical constant: the
probe is measuring real work correctly, and whatever is left at zero bytes is
therefore genuinely overhead rather than mispriced traffic.

Second, extrapolating that line to zero footprint isolates the pure barrier cost
at **1.3489 ± 0.0181 µs**, which is the tightest of the three independent
estimates in this report and sits inside the joint fit's
[+1.3732, +1.4736] and PR #269's removal-measured [0.920, 1.545].

**E3 is refuted as an explanation of the tax.** The footprint-independent floor
is 1.349 µs and that floor is the whole tax at realistic sizes: a 3072-wide
bfloat16 decode activation is 6 KiB, contributing 0.025 µs to the bytes term.

The 4 MiB arm is also the one place in the battery where the injected work
perturbs the command-buffer partition (commits 68 → 78, gpu/wall 0.970 → 0.979,
barriers 367 → 363 at K = 1 because MLX splits the encoder earlier). It is
retained because it anchors the bytes slope over three extra octaves and its
residual is +0.001 µs, but it is not used for any barrier-price claim.

### 4.7 E4 — resource/heap-pool sweep

E4 said the tax is residency or argument-table work that grows with the number
of *distinct* buffers the encoder has to bind and keep resident. `dist40_pN`
holds bytes at 8 KiB and cycles the injected adds over a pool of `N` distinct
pre-allocated buffers, so the counters are identical across the sweep and the
only thing that varies is how many distinct allocations the step touches.

| distinct buffers | working set | µs/step per added dependent pair | 95% CI |
|---|---|---|---|
| 1 (`fat40_8k`) | 8 KiB | 1.3469 ± 0.0593 | [1.228, 1.466] |
| 4 (`dist40_p4`) | 32 KiB | 1.5201 ± 0.0320 | [1.456, 1.584] |
| 16 (`dist40_p16`) | 128 KiB | 1.5507 ± 0.0315 | [1.488, 1.614] |
| 64 (`dist40_p64`) | 512 KiB | 1.5472 ± 0.0290 | [1.489, 1.605] |
| 256 (`dist40_8k`) | 2 MiB | 1.4871 ± 0.0488 | [1.390, 1.585] |

Across the `dist40` family the price is flat over a **64× range of distinct
resources and a 64× range of working set**: 4 → 16 is +0.031 ± 0.045 µs,
4 → 64 is +0.027 ± 0.043 µs and 4 → 256 is **−0.033 ± 0.058 µs**, all zero, and
the sequence 1.520 / 1.551 / 1.547 / 1.487 is not monotone. A residency or
argument-encoding cost would have to grow somewhere in there.

The 1 → 4 step looks like +0.17 µs but is **confounded and should not be read
as an E4 signal**: `fat40` chains `t = t + z` against one hot buffer while
`dist40` chains `t = t + bases[cursor]`, pulling a fresh 8 KiB operand into
each add. That is more real memory traffic per wave, not more residency work,
and it is the same effect §4.6 already prices at 4.07 µs/MiB. The clean
within-mode contrast is the 4 → 256 row, and it is zero.

**E4 is refuted.** The tax does not scale with distinct buffers, allocations, or
working-set size.

### 4.8 Cross-validation against PR #269's removal experiment

PR #269 attacked the same question from the opposite direction: instead of
*injecting* dispatches it *removed* 117 real ones per step by turning
`v_copy | v_Sigmoid | vv_Add | v_Negative` into one fused kernel
(`DARKBLOOM_FUSED_ROUTER`, 39 gates/step × 3 removed dispatches). Their ABBA
design measured **+144.23 µs/step, sd 23.00, t = +12.54, CI [+107.6, +180.8]**
for putting those 117 dispatches back, which they published as
**+1.233 µs/dispatch, 95% CI [+0.920, +1.545]**.

That chain is a *dependent* chain: each of the 117 removed dispatches also
removed a dependency edge, hence a barrier. So this study's model predicts

```
barrier-free-dispatch-only model:  117 x 0.123 =  14 us   (refuted, 5.6 sigma low)
dependent-pair model:              117 x 1.423 = 166 us   (0.95 sigma high)
```

against their measured 144 µs. The two-parameter model built here from
injection on an M4 Pro predicts an M5 removal result it never saw, to within
one standard deviation; the one-parameter "dispatches cost 1.4 µs" model misses
it by an order of magnitude in the other direction. #269 and #268 are
independent confirmations of the same mechanism, and #269's 1.233 µs/dispatch
is best read as **1.233 µs per removed *dependent pair***, whose CI
[0.920, 1.545] brackets this study's 1.423 µs.

Their two other results also line up:

* Their negative control — a Divide-compiled kernel fused beside an *unchanged*
  `row_reduce_small_1_reduce_sum`, which MLX's `is_fusable` predicate refuses to
  absorb — removed **zero** dispatches and produced **zero** speedup. A fusion
  that does not delete a dependency edge refunds nothing, which is §6's rule 2.
* Their E1 refutation by removal is stronger than the injection version here:
  Δ(commit→complete gap) = 1 µs against Δ(GPU-busy) = 139 µs, and total gap is
  *anti*-correlated with dispatch count (406 dispatches → 355 µs gap;
  679 → 233 µs). §4.1 and §4.2 say the same thing with the opposite sign of
  perturbation.

The dispatch counter itself cross-validates: #269's independent kernel-family
census on an M5 finds **exactly 406 dispatches per decode step** for the default
scored path, which is the number this study's `device.cpp` atomic reports on an
M4 Pro. Two different instruments on two different machines agree exactly, so
the K = 0 baseline row here is not an artefact of my patch.

One instrument discrepancy is unresolved and worth stating: #269 counts
**45 command buffers per step**, this study's `device.cpp` counter reports
**67–68 commits and 75–76 encoder creations** per step on the same nominal
workload. These are different quantities measured with different methods on
different hardware (M5 vs M4 Pro, and their count is of dispatched command
buffers while mine counts `commit()` calls including empty and
synchronization-only buffers). Neither result depends on the absolute number —
both are stable across every arm and every K — but nobody should quote "45" and
"68" as if they measured the same thing.

### 4.9 Graph *shape*, not edge count: the currency is serial depth

Two further off-step arms separate "has a dependency edge" from "forces a wave
boundary", which the in-chain arms deliberately conflate.

`distinct` is `indep` with the 256-buffer pool: K independent
`bases[i % 256] * one` products. `diamond1` builds K independent two-op
*diamonds*, `d = b * one` then `y = d + d`, so every unit contains a genuine RAW
edge from its multiply to its add, and the units are independent of each other.

| arm | K | dispatches | RAW edges added | barriers | wall (ms) |
|---|---|---|---|---|---|
| baseline | 0 | 406 | 0 | 247 | 8.186 |
| `indep` | 160 | 566 | 0 | 247 | 8.1821 |
| `distinct` | 160 | 566 | 0 | 247 | 8.1829 |
| **`diamond1`** | **80** | **566** | **80** | **251** | **8.1760** |
| `chain` | 80 | 486 | 80 | 325 | 8.1662 |

`distinct` fits at **+0.0298 ± 0.0227 µs per dispatch** (CI [−0.016, +0.075],
n = 48) — a third independent replication that barrier-free dispatches are free,
and this one cannot be dismissed as MLX collapsing repeated work on one hot
buffer, because every product reads a different allocation.

`diamond1` fits at **−0.0070 ± 0.0212 µs per dispatch** (CI [−0.049, +0.035]).
Read the table row instead of the slope: **at exactly 566 dispatches, 80 real
RAW dependency edges cost 4 barriers and nothing measurable**, while the *same*
80 edges arranged as a serial chain cost 78 barriers.

The reason is visible in `device.cpp`. `set_input_array` (`:315-328`) trips
`needs_barrier_` when an op reads a buffer in `prev_outputs_`, and
`maybeInsertBarrier` (`:363-375`) *moves* `next_*` into `prev_*` when it fires,
discarding everything accumulated before. MLX's `eval` tape orders 40
independent diamonds breadth-first — all 40 multiplies, then all 40 adds — so the
first add trips one barrier, that barrier clears the producer set, and the
remaining 39 adds find nothing of theirs in `prev_outputs_`. Forty dependency
edges, one barrier.

**So the currency is neither dispatches nor dependency edges. It is serial
depth: the number of points at which MLX has no independent work left to put
between a producer and its consumer.**

That reframing has a consequence the programme should absorb before spending a
slot on it. The obvious cheap exploit — "don't write fused kernels, just
reorder graph construction so dependent pairs are separated by independent
work" — **is already done by MLX and is not available**. The tape order is chosen
by MLX's own breadth-first `eval`, not by Swift call order, and `diamond1` shows
that scheduler is good: given 40 parallel edges it finds the one-barrier
schedule. The corollary is that the 247 barriers in a real decode step are close
to the *true* serial depth of the decode graph rather than a scheduling failure,
which is independently consistent with §6's per-layer accounting (6.2 measured
waves against a ~7-wave structural budget). The only lever left is to shorten
serial depth by fusing — which is exactly what PR #269 did, and why it worked.


## 5. Verdict on E1–E5

**None of E1–E5 survives as stated, because all five were framed as
*per-dispatch* mechanisms and the tax is not per-dispatch.** The surviving
mechanism is a sixth one the brief did not list.

| id | mechanism | verdict | decisive evidence |
|----|-----------|---------|-------------------|
| E1 | CPU-side per-op encode starving the GPU | **refuted** | §4.1: 224 µs of real CPU busy-wait injected at the same 40 encode positions moves wall by +0.050 ± 0.029 µs per injected µs, 32 SE below the 1.0 a CPU-paced step requires. §4.2: 99–100 % of the injected cost lands inside GPU-busy, gap slope −0.024 ± 0.013 and +0.007 ± 0.018. #269 by removal: Δgap = 1 µs vs ΔGPU-busy = 139 µs. |
| E2 | GPU command-processor fixed launch cost | **refuted as the dominant term; survives as a 0.12 µs residue** | §4.3 `fan40`: +80 dispatches with +0 barriers cost +17.3 µs (0.216 µs each) where the same 80 in-chain cost 110 µs. §4.4 ×2: +40 barrier-free dispatches cost −3.0 and −13.7 µs. §4.5 `indep`: **+160 barrier-free dispatches cost −5.6 µs**, against +224 µs if the tax were per-dispatch; §4.9 `distinct` replicates that on 256 distinct allocations at +0.030 ± 0.023 µs/dispatch. Pooled joint fit: **+0.123 ± 0.048 µs/dispatch**, 8.6 % of the total. |
| E3 | cache flush/invalidate scaling with dirty footprint | **refuted** | §4.6: 32× footprint (256 B → 8 KiB) changes the price by −0.028 ± 0.065 µs. Over a 16384× sweep to 4 MiB the cost rises *linearly in bytes* at 4.172 µs/MiB = 240 GB/s of footprint, i.e. ordinary DRAM traffic at 88 % of this host's peak. Footprint-independent intercept **1.3489 ± 0.0181 µs**. |
| E4 | residency/bookkeeping scaling with distinct resources | **refuted** | §4.7: a 5-point sweep from 1 to 256 distinct scratch buffers (8 KiB → 2 MiB working set) is flat and non-monotone. |
| E5 | command-buffer commit overhead | **refuted (confirmed)** | §3 and every arm: commits 65–68 and encoder creations 75–76 per step, flat across all 17 arms and all K, while the tax moves by 580 µs. #269 independently reports a constant 45 command buffers/step. |
| **E6** | **loss of intra-encoder overlap at a `memoryBarrier`** | **SURVIVES** | The whole of §4.3–§4.5 and §4.9. Pooled joint fit **+1.300 ± 0.060 µs per barrier**, t = 21.8, n = 288, and no arm off the line at t = 50.6 in the single-regressor pooled fit against x = barrier while x = dispatch throws `dist40_8k` and `fan40` off. Independently pinned at 1.3489 ± 0.0181 µs by the zero-footprint intercept of §4.6. Cross-validated against #269's independent removal at 0.95σ (§4.8). |

### E6 stated precisely

MLX's `Device::maybe_insert_barrier` (`device.cpp:363-375`) emits a single
`memoryBarrier(MTL::BarrierScopeBuffers)` into the *current* compute encoder
whenever the next op has a RAW (`:323-325`) or WAR (`:346-348`) hazard against
anything already encoded there. Every encoder is created
`DispatchTypeConcurrent` (`device.cpp:546-548`), so between barriers the GPU is
free to overlap threadgroups from different dispatches. A barrier costs the
overlap it destroys: the machine must drain every threadgroup encoded before it
before starting anything after it, and the price is the ragged tail of that
drain.

Four properties follow, and all four are observed:

1. **It is charged per barrier, not per dispatch.** Adding dispatches into an
   already-open wave is free (0.12 µs); adding a dependency edge costs 1.30 µs.
2. **It is charged whether or not the dependency is live.** §4.4's two anchor-0
   arms pay 1.78–1.90 µs per barrier for work that never reaches the logits,
   because the barrier serializes the encoder, not the tensor.
3. **It costs what it drains.** §4.5's off-step async arms absorb 157 extra
   barriers for free because the wave being drained is tiny and can slide into
   the next step. The 1.30 µs figure is the price of a barrier placed
   one-per-layer *between real decode work*, which is exactly the fusion case.

4. **It is charged per unit of serial depth, not per dependency edge.** §4.9's
   `diamond1` adds 80 real RAW edges for 4 barriers and no measurable time,
   because MLX schedules independent edges breadth-first and one barrier clears
   all of them at once.

Note that inserting a barrier resets MLX's `prev_*` hazard sets
(`device.cpp:363-375`), so the counter measures **barrier-free waves**, not
dependency edges: several independent edges that resolve at the same point
cost one barrier between them. That is why `fan40` — K independent producers
joined by one concatenate — adds dispatches without adding barriers past K = 2,
and why it is the arm that breaks the per-dispatch model. It is also why the
barrier counter, not the dispatch counter, is the right thing to budget against:
it already reports the quantity that costs money.

### Answering the two hypotheses

**H-MECH holds**, with the mechanism restated: the tax is dominated by one
identifiable mechanism, E6, which accounts for 1.300 of the 1.423 µs
(**91 %**). The remaining 0.123 µs is a genuine but small per-dispatch launch
residue (E2), significant at t = 2.6 and not worth optimizing on its own.

**H-REFUND holds, conditionally.** Removing one dispatch from the live decode
chain refunds ≥ 1.0 µs **if and only if it also removes a dependency edge**. A
fusion that merges two dependent kernels refunds 1.42 µs on this host. A change
that merely reduces dispatch count without deleting an edge — batching
independent work, wider grids over the same wave, anything that lands in the
`fan40` / `indep` regime — refunds 0.12 µs per dispatch, 12× less, and will not
clear the ~80 µs/step decode significance floor at any realistic count.

## 6. Decision rule

**H-REFUND holds, for the fusion of *dependent* kernels.** Fusing two kernels
that are joined by a data dependency removes one dispatch *and* one barrier,
so it refunds

```
0.1231 (dispatch) + 1.3003 (barrier) = 1.4234 +/- 0.0256 us/step   [6 arms, n=288, df=250]
0.1727 (dispatch) + 1.2407 (barrier) = 1.4134 +/- 0.0287 us/step   [4 in-chain arms, n=192]
```

95 % CI **[1.3732, 1.4736]** for the 6-arm fit. Note that the *sum* is pinned
far tighter (SE 0.026) than either part (SE 0.048 and 0.060): dispatch and
barrier counts are near-collinear, so the fit is confident about the total and
much less confident about the split. The error bar on the sum must therefore be
computed from the full covariance, not as `sqrt(se_d² + se_b²) = 0.077`, which
would overstate it by 3×. `fe_ols2` returns it directly.

This is comfortably above the 1.0 µs bar the assignment set. But the
refund is *not* proportional to dispatches removed. Three different fusions
that all remove "one dispatch per layer" refund three very different amounts:

| what the fusion removes per layer | refund µs/step (×40 layers, this host) |
|---|---|
| 1 dependent pair → 1 dispatch **and** 1 barrier | **56.8** |
| 1 barrier only (make two siblings concurrent, keep both dispatches) | **52.0** |
| 1 barrier-free dispatch (fuse two already-co-encoded siblings) | **4.8** |

Projecting the barrier term to the ranked M5, using the 1.000× (fixed
overhead) to 0.506× (scales with step time) transfer band and
0.015280 % of score per µs of decode step:

| barriers removed per step | µs/step on M5 | % score | σ (15.34 µs) |
|---|---|---|---|
| 1 per layer (×40) | 28.9 .. 57.1 | 0.441 .. 0.872 | 1.9 .. 3.7 |
| 3 per layer (×40) | 86.6 .. 171.2 | 1.323 .. 2.616 | 5.6 .. 11.2 |
| 10 per layer (×40) | 288.6 .. 570.7 | 4.410 .. 8.720 | 18.8 .. 37.2 |

**Total size of the prize, and a bundling rule.** Applying the decomposition to
the whole step, the attributable overhead is
`247 barriers × 1.300 + 406 dispatches × 0.123 = 371 µs/step` on this host,
4.5 % of the 8.18 ms step. Transferred to M5 that is **188 .. 371 µs/step**,
which brackets the advisor's independent 283 µs/step estimate from the #269
removal, and it is **28–54 % of the ~682 µs/step honest decode pool** — again
consistent with the advisor's 41 %. The two methods agree on the size of the
target.

But that pool is not addressable one fusion at a time. Against the ~80 µs/step
decode significance floor:

| fusions landed | µs/step on M5 | clears 80 µs floor? |
|---|---|---|
| 1 barrier/layer | 28.9 .. 57.1 | **no**, at either end of the band |
| 2 barriers/layer | 57.8 .. 114.2 | only at the optimistic end |
| 3 barriers/layer | 86.6 .. 171.2 | **yes** |

So a single dependent fusion is a real win that is *individually unmeasurable*
on the ranked harness. The programme should develop fusions independently but
**bundle at least three barrier-removing fusions into one ranked submission**,
or accept that intermediate submissions will read as noise. §4.5's mechanism
also warns that the bundle is not guaranteed additive: once a wave is deleted
the next barrier drains a different amount of work.

So the operational rule for the decode programme is:

1. **Count barriers, not dispatches.** MLX inserts one intra-encoder
   `memoryBarrier` when the next op RAW/WAR-conflicts with anything encoded
   since the last barrier, and inserting it *resets* that conflict set
   (`device.cpp:323-375`). Barriers therefore count **waves** of
   mutually-non-conflicting work, not dependency edges. The decode step runs
   406 dispatches in 247 waves; per layer that is 10.2 dispatches in 6.2
   waves. **A fusion that does not reduce the wave count buys ≈ 0.12 µs and is
   not worth its risk.**
2. **The unit of profit is a *dependent* pair.** Fusing sibling kernels that
   already co-encode into the same wave (e.g. router top-8 into the router
   GEMV, or the shared expert into the routed gate/up) removes zero barriers
   and is worth ~0.1 µs per site. Fusing a producer into its consumer removes
   a wave and is worth ~1.4 µs per site.
3. **Prefer fused kernels over dispatch-side tricks.** Indirect command
   buffers, CPU/GPU encode overlap, and command-buffer batching all attack the
   0.12 µs launch term and the 0.60 ms CPU driver time that already hides
   under a 0.971 GPU-busy fraction (§3, §5/E1). They cannot touch the 1.3 µs
   barrier term, which is inside GPU-busy time.
4. **Ceiling check before building.** The per-layer wave budget is roughly
   `{input norm} {QKV, router-gate} {fused attention} {o_proj}
   {residual+post-norm+router} {top-8, routed gate/up, shared gate/up}
   {down+combine+residual}` = 7 waves, matching the 6.2 measured. The
   realistically fusable dependent pairs are the input RMSNorm into the QKV
   GEMV, and attention output into `o_proj`. At 1 wave per layer each that is
   0.44–0.87 % of score apiece on M5, and the RMSNorm→QKV fusion is the one
   with an existing kernel precedent (the INT8 g32 bank already has the fused
   form; the NVFP4 path declines it at
   `Sources/MLXFastModel/LagunaRuntimeModel.swift:5738-5745`). **A realistic
   near-term ceiling for this direction is ~0.9 % of decode, not the ~4 %
   implied by "406 dispatches × 1.4 µs".**
5. **`start_concurrent()` is out of reach.** The obvious way to delete a
   barrier without deleting a kernel is MLX's concurrent-encoding escape hatch
   (`device.h:33-46`, `device.cpp:343-345`), which today has exactly one user
   (`concat_gpu`, `slicing.cpp:35`). `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp`
   is **not** in `benchmark.json`'s `editablePaths`, so the barrier machinery
   itself cannot be changed by a submission. Only the kernel sources,
   `matmul.cpp`, `jit_kernels.cpp`, `kernels.h`, `quantized.cpp` and their
   `mlx-generated/*.cpp` twins are editable. This is why the answer is
   **(A) fuse dependent kernels**, not (B) restructure dispatch.
6. **Do not spend a slot on graph reordering.** The cheapest-looking exploit of
   rule 1 is to leave every kernel alone and merely separate dependent pairs
   with independent work so MLX stops inserting the barrier. §4.9 closes this:
   the tape order is chosen by MLX's own breadth-first `eval`, not by Swift call
   order, and given 40 parallel dependency edges that scheduler already finds
   the one-barrier schedule. The 247 barriers are close to the decode graph's
   true serial depth, which is why the 6.2 measured waves per layer sit just
   under the ~7-wave structural budget of rule 4. Reordering has no slack to
   recover; only fusion shortens serial depth.

## 7. Scope

No submitted paths. Everything in this experiment is research-only:

* `research/maple-fern-dispatch-tax-attribution.md` (this file)
* `research/fern_tax_probe.py`, `research/fern_tax_stats.py`,
  `research/fern_tax_wandb.py`, `research/fern_tax_campaign.sh`
* `research/fern_tax_inject.patch`, `research/fern_tax_device_counters.patch`

`git diff <base>..HEAD -- Sources Vendor benchmark.json` is empty. The
instrumented worker is built by applying the patches, building
`mlxfast-runtime-worker` into `.build-worker`, and then reverting the tree, so
the instruments exist only in a binary and never in the submitted surface.
Note that editing anything under `Vendor/mlx-swift/Source/Cmlx/{mlx,mlx-generated}`
changes the tree hash that `Sources/MLXFastTrustedHarness/VendoredMetalFingerprint.swift`
computes, so the trusted harness must not be run against a patched tree without
first re-running `tools/build-mlx-metallib.sh`.

### Reproduction

```bash
git apply research/fern_tax_device_counters.patch research/fern_tax_inject.patch
mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Sources Vendor            # instruments now live only in the binary
research/fern_tax_campaign.sh             # 17 arms, ~47 min, writes /tmp/fern268
python3 research/fern_tax_stats.py /tmp/fern268/{chain40,fat40_8k,dist40_8k,fan40,fat40_8k_free,dist40_8k_free}.tsv --joint
python3 research/fern_tax_wandb.py /tmp/fern268 --run-name fern-268-dispatch-tax-battery
```

W&B run for this campaign (all 17 arms, 315 summary scalars, one `arms` table
with every arm × regressor × response slope):
[`rcj6tohw`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/rcj6tohw).
The headline is `joint_all_sites/fusion_refund_us = 1.4234`
(`fusion_refund_ci95_half_us = 0.0502`).


## 8. Caveats

Ordered by how much they could change the verdict.

1. **The 1.4 µs has never been measured on the ranked M5.** Every number here
   is M4 Pro, Apple GPU generation 16, which never selects the `_nax` kernel
   variants. The transfer band (§6) brackets the two extreme assumptions
   rather than resolving them. The *sign* and the *decomposition* should carry
   — they are about how MLX partitions an encoder, which is architecture
   independent — but the magnitude is directional only.
2. **`spin40` bounds host slack on the graph-build thread, not MLX's encode
   thread.** MLX is lazy: the Swift call that `spin40` delays is graph
   construction, and the actual Metal encoding happens later inside `eval`.
   So §4.1 shows that the *call path* has ≥ 224 µs/step of slack, which is not
   quite the same statement as "the encode thread has slack". §4.2 is the
   stronger E1 test and it agrees: 99–100 % of the added wall time lands in
   GPU-busy, and the commit→complete gap slope is statistically zero. Note
   also the seductive coincidence that killed a day: baseline CPU driver time
   / dispatches = 0.60 ms / 406 = 1.48 µs, almost exactly the tax. It is a
   coincidence; the CPU time is not on the critical path.
3. **Barriers count waves, not edges, so "remove a barrier" is a claim about
   MLX's encoder partition, not about the model graph.** Inserting a barrier
   resets `prev_outputs_`/`prev_inputs_` (`device.cpp:363-375`), so a fusion
   that deletes a dependency edge only saves a barrier if that edge was the
   *first* conflict in its wave. §6's per-layer wave budget is my reading of
   the trace, not a proof; a fusion candidate should be re-counted with the
   `TAXCTR` instrument before it is built.
4. **Injected-work realism.** The injected units are cheap elementwise or
   small-reduction kernels. A real fused kernel replaces two *large* kernels,
   and the wave it deletes may have been partly hidden behind other work. The
   1.4 µs is therefore an upper bound on what one real fusion refunds, and the
   §6 ceiling should be read as optimistic.
5. **Splice numerics.** The anchor is `x + (t − t)`, which is bit-exact for
   finite `t` but maps −0 → +0 and would produce NaN for non-finite `t`. All
   17 arms ran the teacher-forced golden with **0 divergences** at every K, so
   this did not bite, but it means the arms are not literally identity
   transformations of the graph.
6. **The off-critical-path comparators understate cost.** `chain`, `indep`,
   `distinct` and `diamond1` inject at a batch boundary rather than inside a
   layer, where the injected work can overlap with real work. Their slopes are
   reported for completeness but the in-chain site arms are the ones the
   verdict rests on.
7. **Thermal drift and command-buffer partition.** Both are controlled rather
   than assumed: the K schedule is palindromic (`0,1,2,4,4,2,1,0`) inside each
   of 6 blocks and the estimator carries a per-block fixed effect, and commit
   and encoder counts were recorded for every arm at every K (67–68 commits,
   75–76 encoders, stable ±1 everywhere). No arm repartitions the stream, so
   E5 stays refuted.
8. **No prior art to calibrate against.** I could find no published
   per-dispatch or per-barrier microsecond figure for Apple M-series Metal.
   The nearest reference points are MLX PR #1773 (MTLFence 15–20 µs vs
   MTLSharedEvent 150–200 µs for *inter-encoder* sync — two orders of
   magnitude above the intra-encoder barrier measured here), wgpu#7712's
   ~48 µs empty-command-buffer floor, and the anukari devlog's ~50 µs
   per-encode figure. All of those are command-buffer-scale costs, consistent
   with this step's 67 commits being the expensive part of the *fixed*
   overhead and the barrier being the marginal one.
9. **`gpu_ms` double-counts when command buffers overlap.** The probe sums
   `GPUEndTime − GPUStartTime` per completed command buffer. When two buffers
   are in flight at once that sum exceeds wall time: the `chain` arm reaches
   `gpu/wall = 1.064`. In every in-chain site arm — the ones §4.2 and the
   verdict rest on — `gpu/wall` is 0.970–0.972, so the decomposition is safe
   there, but `gpu_ms` must not be read as an occupancy figure whenever the
   ratio approaches or exceeds 1.
10. **1.30 µs is not a universal per-barrier constant.** It is the price of a
    barrier inserted *between real dependent decode work*, once per layer,
    which is exactly the fusion case. §4.5 shows the same barrier costs
    *negative* time when the work it drains is off the critical path and can
    overlap into the next step. The correct statement is "a barrier costs what
    it drains"; 1.30 µs is what one drains in the scored decode step on this
    host, not a property of `memoryBarrier` alone.
11. **§4.9's "MLX already schedules optimally" conclusion is inferred, not
    directly re-counted on the real graph.** The breadth-first tape claim is
    established two ways — reading `eval`'s ordering together with
    `maybeInsertBarrier`'s `prev_*` reset, and the `diamond1` arm where 80 real
    RAW edges arranged in parallel cost 4 barriers instead of 78 — but
    `diamond1` is a *synthetic* graph of identical two-op diamonds, and the
    supporting "6.2 measured waves vs ~7 structural waves per layer" figure is
    the same trace reading flagged in caveat 3. The safe reading of rule 6 is
    therefore "reordering graph construction is very unlikely to pay, and must
    be `TAXCTR`-verified before a slot is spent on it", not "it is proven
    impossible".


---

## §9. r2 addendum — the site census resolves caveats 3 and 11

Revision r2 of this assignment ran a barrier-**site** census on top of the r1 rate
measurement. Full report:
[`research/maple-fern-decode-barrier-site-census.md`](maple-fern-decode-barrier-site-census.md).
Only the parts that revise this document are restated here.

**Caveats 3 and 11 are resolved.** Both rested on the "6.2 measured waves vs ~7
structural waves per layer" figure, which was a trace reading rather than a direct
re-count. r2 instruments `device.cpp` to emit, per dispatch, MLX's own resolved RAW
and WAR producer ordinals plus whether a `memoryBarrier` was charged, and measures
the fence count directly:

- **7.000 sparse fences per layer** under the ranked/full memory profile (7.103
  under the local low profile).

So the structural depth is exactly 7, the 6.2 figure was an artefact of the earlier
reading, and §4.9's breadth-first-tape conclusion is now supported by a direct count
on the real graph rather than only by the synthetic `diamond1` arm. Rule 6 can be
stated as measured: **MLX already collapses multi-producer and multi-consumer edges
onto single fences and absorbs the rest at command-buffer boundaries, refunding ~48%
of a naïve one-barrier-per-dependency model** (468 naïve sparse barriers vs 238–248
measured). Reordering graph construction still should not be expected to pay.

Caveat 10 is reinforced rather than resolved. r2 found that **`barrier ∧ cb = 0`**:
MLX never charges a barrier at a command-buffer boundary, because the commit already
provides the ordering. Which of the 7 chain edges pays its 1.30 µs is therefore a
function of where the byte-budget boundary happens to fall, not of the edge itself —
"a barrier costs what it drains" is right, and *whether* it is charged at all is a
separate, profile-dependent question.

Two facts from r2 that anyone re-running the r1 arms needs:

1. **`MLX_MAX_MB_PER_BUFFER` and `MLX_MAX_OPS_PER_BUFFER` are inert.**
   `Sources/MLXFastModel/RuntimeStartupMemoryPolicy.swift:170-183` force-sets both with
   `setenv(..., 1)`, so MLX's architecture table and any operator-supplied value are
   discarded. The working control is `DARKBLOOM_STARTUP_MEMORY_PROFILE=auto|full|low`.
2. **The ranked M5 runs the `full` profile** (128 GB ≥ 64 GiB): 320 MB / 128 ops,
   30 command buffers per step, **258** charged barriers — not the 247 measured locally
   under `low`. Total fences are near-invariant (287 vs 291), so this is absorption
   moving, not depth changing.

The r1 rate result itself is unchanged: barrier +1.3003 ± 0.0597 µs, dispatch
+0.1231 ± 0.0481 µs, dependent pair +1.4234 ± 0.0256 µs.

