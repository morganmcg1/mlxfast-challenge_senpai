# PR #47 D1 — chained vs unchained injected dispatches (M4 bound + instrument validation)

Student: maple-tanjiro. Assignment `maple-2026-08-05c-dispatch-law-close` r1.
Base `1849b376d73f69f9a6b9018619ac665ae4bceb33`.

## What this deliverable is, and what it is not

Per the amendment of 2026-08-05 13:44:39Z, D1 **gates nothing**. The
chained/unchained ratio *is* nezuko's C term — the single quantity the M4
TRANSFER LAW (PR #44) forbids transferring M4→M5 in magnitude or in sign.

So this note reports two things only:

1. **an M4-side bound** on the marginal cost of a chained injected dispatch; and
2. **an instrument validation** — whether the shipped instrument can separate
   chained from unchained work at all. If it cannot, that is a fact about the
   instrument the advisor needs *before* trusting any M5 output from it.

It is **not** evidence that resolves the `[0.36, 2.09] µs` bracket on `c_real`.
That is D5's job, on M5.

## Instrument A — standalone weights-free Metal probe

`research/tanjiro-pr47-dispatch-concurrency.swift` (outside `editablePaths`, so
0 submission bytes). Hand-written Metal, no MLX, no weights, faithful to the MLX
dispatch semantics read out of
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp`.

```
xcrun swiftc -O research/tanjiro-pr47-dispatch-concurrency.swift -o /tmp/dispconc
/tmp/dispconc <rounds> <opsPerCB> <threadgroups> <fitFrom>
```

Six arms. **Every arm writes a distinct output buffer per dispatch**
(`sinks[idx+1]`), so "distinct sinks" is *not* an arm difference. The arms differ
only in:

| arm | binds prev dispatch's output at index 1 | `memoryBarrier(.buffers)` per dispatch | per-CB `waitForFence`/`updateFence` | encoder type |
|---|---|---|---|---|
| `unchained`   | no  | no  | no  | Concurrent |
| `serialenc`   | no  | implicit | no | **Serial** |
| `barrieronly` | no  | **yes** | no | Concurrent |
| `fenceonly`   | no  | no  | **yes** | Concurrent |
| `bindchurn`   | **yes** | no | no | Concurrent |
| `chained`     | **yes** | **yes** | **yes** | Concurrent |

`chained` is the configuration the shipped instrument actually uses.

### Method hardening (and a cautionary finding worth recording)

The first, unpinned version of this probe reported a **non-physical drop in
total wall time from n=200 to n=400** — more dispatches, less time. That is
DVFS: the early, small cells ran at a lower clock. Anyone differencing an M4
dispatch ladder without clock pinning is exposed to this.

Fixes now in the probe:

* a `burn` ALU kernel plus `rampGPU()` (2.0 s initial, 0.35 s per round) to pin
  clocks before every round;
* each `(arm, n)` cell sampled once per round in freshly shuffled order, so
  ordering cannot alias onto an arm;
* one **independent OLS per `(arm, round)`** over `n ≥ fitFrom`, yielding paired
  slope *and* intercept replicates — slope and offset are never shared between
  arms;
* ratios formed **within** a round, so any residual drift divides out;
* percentile 95 % CIs over rounds.

### Result: the cost is not in any single mechanism, and it is occupancy-dependent

Slope in µs per dispatch, 16 rounds, OLS over `n ∈ {800, 1600, 3200, 6400}`,
`opsPerCB = 50`, Apple M4 Pro. "excess" = slope − `unchained` slope.

| threadgroups | threads/dispatch | `unchained` | `chained` (excess) | `serialenc` | `barrieronly` | `fenceonly` | `bindchurn` |
|---|---|---|---|---|---|---|---|
| 1   | 256     | 0.4271 | 1.2446 (**+0.818**) | −0.050 | +0.007 | −0.054 | −0.049 |
| 8   | 2 048   | 0.4020 | 1.2624 (**+0.860**) | −0.013 | +0.031 | −0.010 | −0.013 |
| 40  | 10 240  | 0.6970 | 1.3248 (**+0.628**) | +0.098 | +0.197 | −0.060 | −0.017 |
| 160 | 40 960  | 1.0265 | 2.8134 (**+1.787**) | +0.414 | +0.569 | +1.043 | +1.136 |
| 640 | 163 840 | 3.8172 | 8.5443 (**+4.727**) | +0.382 | +0.557 | +3.899 | +4.001 |

Longer 24-round confirmations, with paired within-round ratio CIs:

| tg | `chained` | `unchained` | ratio median | ratio 95 % CI |
|---|---|---|---|---|
| 8   | 1.2582 | 0.4016 | **3.130** | [2.206, 5.054] |
| 160 | 2.8000 | 1.0266 | **2.729** | [2.594, 2.810] |

Independently fitted intercepts at tg=8: `chained` 272.2 µs [118.6, 353.8],
`unchained` 117.6 µs [−165.9, 270.3], others 100–190 µs.

### Reading

**At low occupancy the cost is purely superadditive.** At tg=8, the barrier
instruction alone is free (1.03×), a cross-CB fence alone is free (0.99×),
`DispatchTypeSerial` alone is free (0.97×), and rebinding the previous
dispatch's output alone is free (0.97×). Their additive prediction is ≈1.00×.
The measured conjunction is **3.13×**. Only *a barrier that has a real
read-after-write hazard to drain* costs anything: **+0.86 µs per dispatch**.

**At high occupancy that stops being true.** By tg=160 every mechanism costs
something on its own, and the conjunction becomes *sub*additive (additive
prediction 3.69×, measured 2.73×).

I will not claim a mechanism for `fenceonly` and `bindchurn` at tg=640, where
both cost ≈ +3.9–4.0 µs, nearly the full `chained` excess, despite neither
emitting a barrier. All arms already bind a distinct output per dispatch, so
this is *not* the hazard path and *not* buffer-count pressure differing between
arms; `bindchurn`'s only delta is one extra distinct buffer bound per dispatch,
and the kernel's read of it sits behind a never-taken sentinel branch, so no
extra bytes move. **This is an unexplained instrument behaviour at saturation
and I am flagging it rather than narrating a mechanism for it.** Separating it
needs one more arm (bind a *fixed* second sink rather than the previous one);
that arm is not in this deliverable.

### Why this is a direct corroboration of the M4 TRANSFER LAW

The law says boundary *timing* does not transfer across machines. This probe
shows something stronger and cheaper to check: **boundary timing does not even
transfer across occupancy on one machine.** Same host, same kernels, same
encoder code, only threads-per-dispatch changed, and:

* the absolute chained penalty moves over **0.63 → 4.73 µs**, a 7.5× span;
* the chained/unchained ratio moves non-monotonically over **1.90 → 3.13**;
* individually-free mechanisms (`fenceonly`, `bindchurn`) go from **≈0 µs to
  ≈+4 µs**, i.e. their measured sign changes.

nezuko's four-cell model attributes the M4↔M5 disagreement to the C term
(forfeited intra-encoder concurrency, scaling with distance from GPU
saturation). This probe varies exactly that distance and reproduces exactly
that instability. Two consequences:

* **This probe measures B, not B−C.** `chained − bindchurn` at tg=8 =
  1.2624 − 0.3893 = **0.873 µs** is a fairly clean M4 read of the boundary
  benefit/cost B, because with 2 048-thread empty kernels there is essentially
  nothing to overlap, so C ≈ 0 *by construction*. That is the term the transfer
  law permits least confidently, and my C ≈ 0 is an artefact of the probe, not a
  property of the model.
* Any single-number M4 "cost per dispatch" is meaningless without stating the
  occupancy it was measured at.

## Instrument B — the in-model ladder

`senpai/tools/pr47_d1_chain_ladder.sh`, launched this session. Adds
`DARKBLOOM_INJECT_EMPTY_CHAIN` (default `1` = shipped behaviour) to the #27
instrument block; `0` binds a never-written control array in place of the
previous dispatch's output.

Design, matching the amendment's requirements:

* slope **and** offset fitted independently per arm;
* ≥3 supra-knee points per arm — M4 host-encode knee is 1209, so
  `n ∈ {1600, 2400, 3200}` are supra-knee, `n = 0` anchors the offset
  (`n = 0` is arm-independent, so it is measured once per rep and shared);
* arms interleaved within each rep;
* 3 reps;
* fresh process per point (each `--local-iterate` is its own worker);
* first point is a discarded warm-up arm;
* `tg = 160`, matching both the standalone probe and the r1 in-model fit.

### Pre-registered prediction, from Instrument A

At tg=160 the standalone probe says ratio **2.729 [2.594, 2.810]**, i.e. the
in-model unchained slope should be **0.365 ×** the chained slope. Explicitly:

* ratio ≈ 2.7 → the instrument separates the two regimes and the shipped
  chained configuration is doing what its comment claims;
* ratio ≈ 1.0 → **the instrument is broken**, because the standalone probe on
  the same host at the same occupancy says the physics is 2.7. The most likely
  cause is output-buffer aliasing (below), and no M5 number from the unchained
  arm would be trustworthy until it is fixed.

### Cross-validation of the shipped instrument (this is the D1 headline)

Two fully independent instruments, same host, same occupancy:

| instrument | chained cost per injected decode dispatch, tg=160 |
|---|---|
| in-model M4 companion fit (r1, full model + MLX, 21.6 GB of weights) | **2.607 µs** |
| standalone probe (hand-written Metal, no MLX, no weights) | **2.813 µs** (16 rd) / **2.800 µs** (24 rd) |

Agreement to **7.4 %**. These share no code: different language surface,
different dispatch encoder, different memory footprint, different fitting
procedure. That is a real validation of the #27 instrument's per-dispatch
readout, and it is the strongest statement in this deliverable.

For context only, and *not* as a transfer: the M5 paired law is
`c = 2.088 ± 0.165 µs` at the same tg=160, i.e. 0.74 × M4's 2.813 µs. That
ordering is consistent with M5's ~2.25× faster fabric. It is a
concurrency-class quantity, so I am not treating the ratio as predictive.

## The aliasing hazard the amendment asked me to check

I audited the MLX barrier path and the audit changed the design.

`device.cpp` / `device.h`, read directly:

* `CommandEncoder::set_input_array` (:316-328) sets `needs_barrier_` when the
  bound buffer is in `prev_outputs_` — **RAW**.
* `CommandEncoder::set_output_array` (:320-327) calls `set_input_array` *first*
  ("Add barriers before adding the output to the output set"), so an output
  buffer is also checked against `prev_outputs_` — **WAW**.
* `CommandEncoder::register_output_array` (:337-348) sets `needs_barrier_` when
  the buffer is in `prev_inputs_` — **WAR** — *unless* `concurrent_`.
* **`concurrent_` defaults to `false`** (`device.h:129`) and is true only inside
  an explicit `ConcurrentContext` (`device.h:33-41`, `start_concurrent()`
  :88-90). It is **not** the same thing as the encoder's
  `MTL::DispatchTypeConcurrent` (`device.cpp` ~:548).

So on the ordinary path MLX detects **RAW, WAR and WAW** — a wider net than the
instrument's own comment (which cites only :325 and :339) implies. The
amendment's named hazard is therefore real and broader than stated: it is not
only "all empties alias one output buffer". Because MLX allocates each empty's
`[256]` output from a size-keyed buffer cache, a released output can be recycled
into a *later* empty's output within the same barrier epoch, and
`set_output_array` would then trip the barrier as a **WAW** — ratio 1.0 for a
pure instrument reason.

**Mitigation, implemented:** in the unchained arm every empty's output is
appended to `pending`, so nothing is released and no buffer can be recycled
within the epoch. Barrier epochs are per-command-buffer (`end_encoding` clears
`prev_inputs_`/`prev_outputs_`, `device.cpp:462`), and there is one `asyncEval`
per layer boundary, so cross-boundary and cross-step recycling cannot trip it
either.

**Residual risk I cannot remove from the current design and am declaring:** an
empty's freshly allocated output may be recycled from a *real model* tensor
freed earlier in the same command buffer. That buffer is already in
`prev_outputs_`, so it trips a WAW barrier that has nothing to do with my chain.
This biases the unchained arm *toward* the chained arm — i.e. it can only make
the measured ratio too **small**, never too large. For D5, whose "high" branch
is ratio 1.0, that is the **non-conservative** direction: an aliasing artefact
and a genuine ratio-1.0 result are indistinguishable. Removing it properly needs
persistent, never-freed per-dispatch sink buffers, which `MLXFast.metalKernel`
cannot express (it allocates its own outputs). This is precisely why D1's
in-model ratio must be checked on M4 *before* the M5 slot is spent.

Two further notes on the unchained arm:

* `scratch.control[7]` is bound at index 1 and `scratch.control[(layer+k)&7]` at
  index 0, so for `k ≡ 7 (mod 8)` both indices bind the same buffer. That is
  read-after-read, not a hazard.
* At n=3200 with `spread=1`, 80 empties land per boundary and the 50-op
  `needs_commit()` cap (`device.cpp:484-487`) forces extra commits — but equally
  in both arms, so it cancels in the ratio.

## Results — tg=160 ladder, 13 points, 2 complete reps

Training `aee42e39-54c8-4811-a698-648f9aa0346c`, Apple M4 Pro / 48 GiB /
`applegpu_g16s`, `--local-iterate`, interleaved arms, fresh process per point,
warm-up point discarded. Rep 3 was cancelled after rep 2 closed the question;
`n=0` was measured once per rep as the sub-knee anchor. Raw receipts in
`research/tanjiro-pr47/d1-*.json`; reproduce the fits with
`python3 research/tanjiro-pr47-d1-fit.py`.

| point | chain | decode s/tok | T (ms) | S (ms) |
| --- | ---: | ---: | ---: | ---: |
| r1-n0 | 1 | 0.013335 | 8.8310 | 576.570 |
| r1-n1600-c0 | 0 | 0.014255 | 9.7593 | 575.395 |
| r1-n1600-c1 | 1 | 0.014379 | 9.8774 | 576.138 |
| r1-n2400-c0 | 0 | 0.016086 | 11.6524 | 567.527 |
| r1-n2400-c1 | 1 | 0.016552 | 12.0474 | 576.563 |
| r1-n3200-c0 | 0 | 0.018731 | 14.1745 | 583.222 |
| r1-n3200-c1 | 1 | 0.018904 | 14.4060 | 575.776 |
| r2-n0 | 1 | 0.013320 | 8.8213 | 575.884 |
| r2-n1600-c0 | 0 | 0.014402 | 9.9560 | 569.134 |
| r2-n1600-c1 | 1 | 0.014477 | 9.9724 | 576.586 |
| r2-n2400-c0 | 0 | 0.016056 | 11.4972 | 583.541 |
| r2-n2400-c1 | 1 | 0.016378 | 11.8751 | 576.404 |
| r2-n3200-c0 | 0 | 0.018608 | 14.1081 | 575.979 |
| r2-n3200-c1 | 1 | 0.018736 | 14.2138 | 578.885 |

Every point reported `passed_correctness: true` and `max_abs_diff: 0`.

### Independent per-arm fits (supra-knee points only, `n ∈ {1600, 2400, 3200}`)

Both slope **and** offset are free in each arm, as the assignment requires. The
`n=0` points are *not* in either regression — they sit below the M4 knee, where
injected dispatches hide in the 3.152 ms host-encode slack, so including them
would average across the knee and bias both slopes down (shown below as the
"pooled" row purely to make that bias visible; it is not a marginal cost).

| arm | npts | slope (µs/disp) | offset (ms) | residRMS (ms) | implied knee | pooled-with-n=0 slope |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| chained (c1) | 6 | **2.7406 ± 0.0829** | 5.4879 | 0.1326 | **1218.1** | 1.6676 |
| unchained (c0) | 6 | **2.6773 ± 0.1636** | 5.4324 | 0.2618 | **1267.6** | 1.5864 |

`n=0` anchor: T = **8.8262 ms** (2 points, spread 0.0097 ms). Implied knee is
`(T(n=0) − offset)/slope`.

### Instrument validation (the part of D1 that is worth keeping)

Three independent estimates of the same M4 quantity agree:

| source | chained cost (µs/dispatch) | vs this ladder |
| --- | ---: | ---: |
| this in-model ladder, tg=160 | 2.7406 ± 0.0829 | — |
| standalone probe, tg=160, 24 rounds | 2.8000 | +2.2% |
| published M4 in-model law (PR27) | 2.607 | −4.9% |

and the ladder's *implied* knee **1218.1** reproduces the independently
published M4 knee **1209** — the `max_ops_per_buffer` host-encode crossover at
`device.cpp:576-593` — to **0.75%**. The two arms' offsets agree to 0.0555 ms
(1.0%, well inside residRMS), consistent with a single shared GPU-bound floor
and no arm-dependent constant. This is a genuine three-way cross-check that the
in-model injector measures the same physics as the standalone probe and the
earlier PR27 fit, at the same threadgroup geometry.

### The ratio: chained is slower, but ~21× less than the probe says

Slope ratio (arms fitted independently) is **1.0237**, 1σ = 0.0698:

* 1σ CI **[0.9539, 1.0934]**
* 3σ CI **[0.8143, 1.2330]**

i.e. statistically indistinguishable from 1.0. The paired estimator is tighter,
because it differences the two arms *within* a rep and `n`, cancelling the
per-point offset scatter that dominates residRMS:

| rep | n | chained − unchained (ms) | µs/dispatch |
| ---: | ---: | ---: | ---: |
| 1 | 1600 | +0.1181 | +0.0738 |
| 1 | 2400 | +0.3950 | +0.1646 |
| 1 | 3200 | +0.2315 | +0.0723 |
| 2 | 1600 | +0.0164 | +0.0103 |
| 2 | 2400 | +0.3779 | +0.1575 |
| 2 | 3200 | +0.1057 | +0.0330 |

**Paired excess = +0.0852 ± 0.0259 µs/dispatch** (6 pairs, sd 0.0635,
**3.29σ from zero**), i.e. **3.11%** of the chained slope.

**Direction statement (explicit, as required).** The chained arm is *slower*
than the unchained arm. The excess is **positive** in all 6 pairs, so it has the
**same sign** as the standalone probe's `chained − unchained` penalty. Its
magnitude, however, is **+0.0852 µs/dispatch against the probe's +1.787
µs/dispatch at the identical tg=160 geometry — a factor of ~21 smaller.**

### Why this ladder cannot settle the ratio, and what does

Two hypotheses survive, and they are *not* distinguishable from tg=160 data:

* **H_host — chain-blind by physics.** Above the knee the exposed marginal cost
  is CPU-side command encoding, which is identical whether or not a
  `memoryBarrier` is emitted. Under H_host the barrier's GPU-side cost is real
  but fully hidden behind host encode, so the measured ratio *should* be ≈1.0
  and the instrument is **sound**. The near-perfect knee reproduction above is
  evidence for exactly this regime.
* **H_alias — the unchained arm is still receiving barriers** from allocator
  output recycling (the declared, undischarged residual in the aliasing audit
  above). Then the instrument is broken and D5 would measure the instrument.

This **invalidates my own preregistered reading** that "ratio ≈ 1.0 ⇒
instrument broken": H_host predicts ratio ≈ 1.0 with a perfectly sound
instrument, so the observed 1.0237 is not evidence either way. I am recording
that as a prereg failure rather than reinterpreting the test after the fact.

The discriminator is threadgroup geometry, because **host encode cost per
dispatch is tg-independent while GPU cost is not**. The tg=8 addendum
(`senpai/tools/pr47_d1_tg8_addendum.sh`, `n ∈ {0, 3200, 6400}` × both arms)
separates them by a factor of 6.3 on the chained arm and by 5.24 ms-vs-zero on
the unchained arm — far beyond the 0.1–0.3 ms point scatter, so one rep decides
it. tg=8 is also exactly the geometry of the paid chained receipt `0411779d`, so
the addendum doubles as an M4 dry run of the D5 configuration.

## tg=8 addendum — the discriminator fired, and it fired model-free

Points banked so far (`research/tanjiro-pr47/d1-tg8-*.json`, all
`passed_correctness: true`, `max_abs_diff: 0`, empty `error`). Readout:
`python3 research/tanjiro-pr47-d1-tg8.py`; the matched-`n` cross-`tg` comparison
below is reproduced by the same `S`/`T` reduction applied to the tg=160 ladder
points already banked in the same directory.

**Control first: the two ladders share a baseline.** The `n = 0` anchor should
not depend on `EMPTY_TG` at all, because no empty dispatch is injected.

| anchor | T (ms) |
| --- | --- |
| tg=160, mean of 2 reps | 8.82617 (spread 0.0097) |
| tg=8, 1 rep | 8.83084 |

Difference **+0.00467 ms**, inside the rep spread. The tg=8 arm is measuring the
same machine in the same state, so cross-`tg` differences at matched `n` are
attributable to `tg`.

**The test.** Host-side command encoding costs the same per dispatch regardless
of how many threads the dispatch launches; GPU-side barrier and serialization
cost does not. The standalone probe measures the GPU-side scaling directly:
chained cost 1.2624 µs/dispatch at tg=8 versus 2.8134 at tg=160, i.e. tg=8
should be **0.449×** as expensive per dispatch if the exposed in-model cost is
GPU-side. If the exposed cost is host encode, the ratio is **1.00**.

| chained, n = 3200 | dT vs the matching n=0 anchor | µs/dispatch |
| --- | --- | --- |
| tg=160, rep 1 | 5.57983 ms | 1.7437 |
| tg=160, rep 2 | 5.38763 ms | 1.6836 |
| tg=160, mean | **5.48373 ms** | 1.7137 |
| tg=8, rep 1 | **5.51885 ms** | 1.7246 |

**Ratio tg=8 / tg=160 = 1.0064.** The tg=160 rep spread is 0.192 ms, so 1σ on
that mean is ≈0.096 ms ≈ 1.8% of `dT`; the ratio is 1.006 ± 0.018 and excludes
0.449 by roughly **30σ**. A 20× change in occupancy (2048 → 40960 threads per
dispatch) moves the exposed marginal cost by less than 1%.

This is a *model-free* comparison — same `n`, same arm, same session, same
reduction, only `EMPTY_TG` differs. It does not lean on the fitted slope, the
fitted offset, or on the knee being hard rather than soft.

### n = 6400 confirmation points, and the regime warning they carry

Two further tg=8 points were banked at `n = 6400` (`d1-tg8-r1-n6400-c1.json`,
`d1-tg8-r1-n6400-c0.json`; both `passed_correctness: true`, `max_abs_diff: 0`,
empty `error`). There is no tg=160 companion at `n = 6400`, so these cannot
extend the matched-`n` cross-`tg` test. What they do give is a second, wholly
independent estimate of the tg=8 marginal rate, taken from the *segment* slope
between `n = 3200` and `n = 6400` rather than from the anchor.

| arm | dT(3200) ms | dT(6400) ms | segment slope 3200→6400 | tg=160 supra-knee fit |
| --- | --- | --- | --- | --- |
| chained | 5.51885 | 13.65894 | **2.5438 µs/disp** | 2.7406 ± 0.0829 |
| unchained | 5.32090 | 16.08431 | **3.3636 µs/disp** | 2.6773 ± 0.1636 |

Both tg=8 segment slopes land in the same 2.5–3.4 µs/dispatch class as the
tg=160 supra-knee fits (ratios 0.93 and 1.26). `H_probe` would have required
0.449× of those, i.e. 1.23 and 1.20 µs/dispatch. So the occupancy-independence
conclusion reproduces on a second, anchor-free estimator.

**But these two points also inverted the arm ordering**: at `n = 6400` the
*unchained* arm is 2.43 ms slower than the chained one, where at `n = 3200` it
was 0.20 ms faster. That gap is far larger than any rep spread I have measured
(0.192 ms at `n = 3200`, tg=160), and its sign is physically backwards. With one
rep per point I cannot separate noise from a real regime change, and I am not
going to guess. What I will record is the concrete reason to distrust `n = 6400`
as a clean operating point: at `max_ops_per_buffer = 50` it forces ~128 extra
command buffers per decode step and inflates decode from 8.8 ms to 22–25 ms per
step, a 2.5–2.8× stretch of the timed window. The harness thermal gate was
calibrated for the unstretched window.

**Neither the primary discriminator nor any conclusion above depends on these
points.** The discriminator is the matched-`n` comparison at `n = 3200`, which is
untouched. The `n = 6400` pair is reported as corroboration of the slope class
and as an explicit warning that the ladder should not be pushed past `n = 3200`
on this host without replication.

### What that settles, and what it does not

**Settled: the exposed in-model marginal cost on M4 is host-encode-class.** It
is threadgroup-count-independent. That is the signature of CPU command encoding,
not of a GPU barrier or of GPU serialization. It also independently reproduces
the `max_ops_per_buffer` host-encode crossover story behind the published M4
knee of 1209.

**Settled: `H_host` explains the ratio ≈ 1.0 with no aliasing whatsoever.** The
chained/unchained ratio of 1.0237 measured at tg=160 needs no leaked barriers to
explain it. My preregistered reading ("ratio ≈ 1.0 ⇒ instrument broken") is
formally wrong and stays recorded as a prereg failure.

**Not settled, and I have to say so plainly: this makes M4 *blind* to the
barrier question rather than answering it.** If host encode dominates the
exposed cost, then M4's in-model ladder cannot see whether `CHAIN=0` really
removes the barriers, because it cannot see barrier cost at all in either arm.
The strong form of `H_alias` — "the unchained arm's cost *is* barrier cost,
leaked through allocator recycling" — is dead, since that cost would have to
scale with `tg` and does not. But the weak form — "barriers are present in the
unchained arm and are simply invisible" — is untouched by this measurement, and
on M4 it is unfalsifiable.

So instrument soundness rests on the other two legs, not on this one:

1. the **code audit** (§ "The aliasing hazard the amendment asked me to check"),
   which discharges RAW and WAR structurally and leaves only allocator output
   recycling as a residual; and
2. the **standalone probe**, which uses the same three-argument binding pattern
   and there resolves chained 1.2624 versus unchained 0.4020 µs/dispatch at
   tg=8, ratio 3.130 — direct evidence that this binding pattern does control
   whether a barrier is emitted, on a workload where the barrier is not hidden
   behind host encode.

Together those two say the knob works; the tg=8 addendum says M4's in-model
ladder is the wrong instrument to confirm it with. The declared residual and the
pre-commitment in the D5 prereg (`§4.1`: I will not report an S0 outcome as a
physical conclusion) both stand unchanged.

### What D1 does *not* do

**D1 does not resolve the [0.36, 2.09] µs/dispatch M5 bracket, and no reading of
it should be quoted as if it did.** The chained/unchained ratio *is* nezuko's
**C** term (boundary cost), and the M4 transfer law admits M4 wall-clock for
kernel-internal efficiency and byte-stream size only — boundary-class timing
does not transfer M4→M5 in magnitude *or* in sign. Everything above is
therefore (a) an **M4-side bound** on the in-model chaining penalty and (b) an
**instrument validation**. It gates nothing. The bracket is D2's and D5's job on
the ranked M5.
