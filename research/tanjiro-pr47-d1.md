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

## Status

Ladder launched (training `aee42e39-54c8-4811-a698-648f9aa0346c`), resumable:
`run_point` skips any cell whose JSON already exists. Numbers, fitted slopes,
offsets, the ratio with its CI, and an explicit direction statement land here on
completion.
