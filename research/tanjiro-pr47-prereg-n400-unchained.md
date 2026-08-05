# PR #47 D5 — PREREGISTRATION: ranked `n=400` UNCHAINED arm

Conditional third slot. Committed **before** the ranked submission; the receipt
section is appended, not edited. Companion to
[`tanjiro-pr47-prereg-n100.md`](tanjiro-pr47-prereg-n100.md) (D2), which owns the
shared σ derivation, the exact inverse map, the paired-vs-candidate-only
convention, and the acceptance-band arithmetic. All numbers here reproduce with
`python3 research/tanjiro-pr47-prereg.py` (section F).

## 0. The one-line question

`0411779d` paid 0.83508 ms of decode time for 400 injected empty dispatches
whose outputs form a **RAW chain**, so MLX emits a `memoryBarrier` between every
consecutive pair and the GPU runs them strictly one at a time. D5 runs the
identical arm with the chain broken. The ratio

```
ratio = dT_chained(400) / dT_unchained(400)
```

is the fraction of the M5 per-dispatch cost that is **serialization**, as
opposed to work that would be paid anyway. `n` is identical in both arms, so
the knee term of `dT(n) = c·max(0, n−k)` cancels exactly and this measurement is
**orthogonal to D2**: D2 locates `k`, D5 decomposes `c`.

## 1. The arm, and the verified-by-diff claim

The advisor required that the only difference from `0411779d` be that the
empties are unchained, and that I verify this by diff and say so. Doing that.

`0411779d` is the tree at commit **`b8da628`** ("PR34 r2 L1: inject 400 empty
decode dispatches at 8 threadgroups"). Its injected-dispatch defaults:

```
$ git show b8da628:Sources/MLXFastModel/LagunaRuntimeModel.swift | grep -n DARKBLOOM_INJECT
11036:    "DARKBLOOM_INJECT_DECODE_SWEEPS", 0)
11040:    1, lagunaInjectEnvInt("DARKBLOOM_INJECT_SWEEP_PASSES", 1))
11043:    "DARKBLOOM_INJECT_PREFILL_MATMULS", 0)
11046:    "DARKBLOOM_INJECT_DECODE_EMPTY", 400)
11049:    "DARKBLOOM_INJECT_PREFILL_EMPTY", 0)
11054:    "DARKBLOOM_INJECT_EMPTY_SPREAD", 1) != 0
11058:    "DARKBLOOM_INJECT_EMPTY_TG", 8)
```

There is **no `DARKBLOOM_INJECT_EMPTY_CHAIN` knob at `b8da628`** — the chain was
unconditional, which is why `0411779d` is a chained point.

| knob | `0411779d` (`b8da628`) | D5 submitted default | same? |
|---|---|---|---|
| `DECODE_EMPTY` | 400 | 400 | yes |
| `EMPTY_TG` | 8 | **8** | yes |
| `EMPTY_SPREAD` | 1 | 1 | yes |
| `PREFILL_EMPTY` | 0 | 0 | yes |
| `DECODE_SWEEPS` / `SWEEP_PASSES` / `PREFILL_MATMULS` | 0 / 1 / 0 | 0 / 1 / 0 | yes |
| `EMPTY_CHAIN` | (absent ⇒ chained) | **0 ⇒ unchained** | **no — the single intended difference** |

`EMPTY_TG` deserves the emphasis. Current HEAD's default is **160**, not 8.
Submitting D5 at 160 would break the comparison twice over: it would not be the
`0411779d` arm, and the per-dispatch cost is strongly `tg`-dependent (my
standalone M4 probe: chained 1.258 µs at `tg=8` versus 2.800 µs at `tg=160`,
`research/tanjiro-pr47-d1.md`). The binding reason is not the size of the `tg`
effect, it is that **the comparison is against an already-paid receipt and every
non-target knob must match that receipt exactly.** Same for D2.

Everything else in the diff `b8da628..HEAD` on the submitted surface is not
inert, and I will not pretend otherwise: HEAD carries the promoted frontier
advanced past `b8da628`. That is why D5 is judged on **`ns`** against the
permanent published control `c3ce66ec` = **2.544360**, exactly as D2 is, rather
than by differencing raw `T` against `0411779d` — the renormalisation removes
the frontier's own movement. The chained anchor enters only as the already-paid
`dT_chained(400) = 0.83508 ms` **paired** figure, which was itself derived
against the same control.

## 2. Prediction table

`c_real` is the implied real per-dispatch cost under Reading A of the D2 prereg
(`k = 0`), i.e. `c_real[µs] = dT_u(400)[ms] × 1000 / 400`.

| scenario | `c_real` µs | `dT_u(400)` ms | ratio | pool, %-of-score | predicted `ns` |
|---|---|---|---|---|---|
| **high anchor** — no serialization component | 2.0877 | 0.83508 | 1.000 | 12.60 | 2.268288 |
| M4 probe ratio 2.729 (`tg=160`) | 0.7650 | 0.30600 | 2.729 | 4.62 | 2.434453 |
| **low anchor** — 0.36 µs residual | 0.3600 | 0.14400 | 5.799 | 2.17 | 2.491221 |

σ(ns) = 0.005361 (D2 §2). 3σ windows:

| scenario | 3σ window on `ns` |
|---|---|
| high anchor | [2.252204, 2.284372] |
| M4 ratio 2.729 | [2.418369, 2.450537] |
| low anchor | [2.475137, 2.507305] |

The high/low separation is 0.222933 `ns` units = **41.6σ**. This arm is not
close to noise-limited; it is limited only by whether it measures what it claims.

## 3. Decision rule — continuous, not two-anchor

**A two-anchor accept/reject rule would return "no decision" for the single most
likely outcome, so I am not using one.** The M4-probe prediction 2.434453 sits
**31.0σ** from the high anchor and **10.6σ** from the low anchor: both anchors
would be rejected and the design would spend an M5 slot to print "neither".
That is a rule-design defect, not a physics claim — the M4 ratio is a
concurrency-class quantity and by the M4 TRANSFER LAW its magnitude does not
transfer. The point is that the anchors are the *endpoints of a continuum* and
the whole continuum is admissible, so the readout must be continuous.

Binding rule:

```
dT_u [ms]  = 1000 × 0.00504644 × ( (2.544360 / ns_obs)^(4/3) − 1 )   [exact, D2 §6]
ratio      = 0.83508 / dT_u
c_real[µs] = dT_u × 1000 / 400
pool [%]   = 14.862 × 406 × c_real / 1000
σ_rel(ratio) = sqrt( (σ(dT_u)/dT_u)^2 + (σ(dT_c)/dT_c)^2 ),  σ(dT) from D2 §2
```

and the verdict is the triple `(ratio ± 3σ, c_real, pool)`. Named regions are
reported as *labels on that continuum*, not as gates:

| label | `ratio` 3σ CI | reading |
|---|---|---|
| **S0** | CI contains 1.0 | no serialization component. The 2.088 µs is work paid regardless; concurrency is **not** a lever on M5 |
| **S1** | CI entirely `> 1.0`, upper bound finite | serialization is real and quantified. `1 − 1/ratio` of the per-dispatch cost is recoverable by making real dispatches independent, **without removing any dispatch** — a new lever, and one D4 does not currently price |
| **S2** | CI lower bound `> 5` | per-dispatch cost is almost entirely serialization; `c_real ≲ 0.4 µs`; the D4 fusion pool collapses to ~2 % and the whole dispatch-count programme is mispriced |
| **X** | `dT_u < 0` at 3σ (arm **faster** than control) | declared in advance as an instrument or cross-session fault, not evidence. Adding work cannot make the arm faster |

Ratio CIs at the three scenarios, to show the rule has usable resolution
everywhere:

| at `dT_u` = | σ_rel(ratio) | ratio ± 1σ | ratio ± 3σ | label |
|---|---|---|---|---|
| 0.83508 | 2.798 % | 1.000 ± 0.028 | ± 0.084 | S0 |
| 0.30600 | 5.298 % | 2.729 ± 0.145 | ± 0.434 | S1 |
| 0.14400 | 10.319 % | 5.799 ± 0.598 | ± 1.795 | S1/S2 boundary |

Resolution degrades toward the low anchor because `dT_u` shrinks while σ(dT)
does not. At the low anchor the 3σ CI is [4.00, 7.59] — still comfortably S1,
still enough to conclude "the pool is small", which is the decision-relevant
content.

## 4. Aliasing — the one way this arm returns a wrong answer

This is the material risk and it biases in the **non-conservative** direction,
so it is stated before the spend rather than after.

Audited in `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp`:

| entry point | line | hazard detected |
|---|---|---|
| `set_input_array` | 316-328 | `needs_barrier_ \|= prev_outputs_.contains(buf)` — **RAW** |
| `set_output_array` | 320-327 | calls `set_input_array` first ⇒ output is also tested against `prev_outputs_` — **WAW** |
| `register_output_array` | 337-348 | `needs_barrier_ \|= prev_inputs_.contains(buf)` — **WAR**, unless `concurrent_` |
| `maybeInsertBarrier` | 363-375 | rotates `prev_*` only when a barrier actually fires, otherwise accumulates |
| `end_encoding` | 462 | clears `prev_outputs_` ⇒ **barrier epochs are per-command-buffer** |

Two corrections to the instrument's own commentary, both mine to own:

1. `concurrent_` defaults to **`false`** (`device.h:129`) and is true only inside
   a `ConcurrentContext` (`device.h:33-41`, `start_concurrent()` :88-90). It is
   **not** the same thing as the encoder's `MTL::DispatchTypeConcurrent`
   (`device.cpp` ~:548). The original comment conflated them.
2. MLX therefore detects **RAW, WAR and WAW** on the ordinary path. Breaking the
   RAW chain is not sufficient on its own; a recycled buffer can reintroduce a
   barrier through WAW.

**Mitigation shipped.** In the unchained path every empty's output is appended to
`pending`, so no unchained output can be recycled by a later empty inside the
same barrier epoch. Verified against the allocator's reuse rule, not assumed.

**Residual risk, undischarged.** An empty's freshly allocated output may be
recycled from a *real model* tensor that was freed earlier in the same command
buffer. That produces a WAW barrier which has nothing to do with my chain, and
it biases the unchained arm **toward** the chained arm — it can only make the
measured ratio too **small**, i.e. it can only manufacture a false **S0**. S0 is
the outcome that would tell the programme "concurrency is not a lever", so a
false S0 is the expensive error. A proper fix needs persistent, never-freed,
per-dispatch sink buffers, which `MLXFast.metalKernel` cannot express.

**Pre-commitment: I will not report S0 as a physical conclusion.** If the arm
lands in S0 I report it as *"either no serialization component, or residual
allocator-recycling aliasing; not separable by this instrument"*, and the D1 M4
ladder is the evidence that decides which — see §5. S1 and S2 are safe, because
aliasing cannot inflate the ratio.

Minor, checked and dismissed: for `k ≡ 7 (mod 8)` both kernel inputs bind the
same `control` buffer, which is read-after-read and no hazard. At `spread=1` the
50-op `needs_commit()` cap (`device.cpp:484-487`) forces extra commits, but
identically in both arms, so it cancels in the ratio.

### 4.1 Buffer-argument enumeration (the pre-submission check, discharged)

The advisor required the buffer arguments be checked for aliasing before this
arm is submitted. There are exactly three per empty dispatch
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:11208-11218`):

| # | binding at `CHAIN=0` | lifetime | written by anything? | hazard class reachable |
| ---: | --- | --- | --- | --- |
| in 0 | `scratch.control[(layer + k) & 7]` | static `Scratch`, allocated `:11146`, `eval`'d `:11153`, **never freed** | **no** | none |
| in 1 | `scratch.control[7]` | same | **no** | none |
| out | fresh `[256]` `uint32` per dispatch | held in `pending` until `asyncEval` | yes, by this dispatch only | WAW / WAR **only via allocator recycling** |

`grep -n control Sources/MLXFastModel/LagunaRuntimeModel.swift` confirms the
control arrays appear only in `inputNames` (`:11089`, `:11122`) and as bound
*inputs* (`:11196`, `:11211`, `:11212`). No kernel in the instrument or in the
model writes them. Therefore:

- **RAW is structurally impossible** at `CHAIN=0`: both inputs are
  never-written buffers, so `prev_outputs_.contains(buf)` can never be true for
  them. This is the intended contrast with `CHAIN=1`, where input 1 is the
  previous empty's output and RAW fires by construction.
- **WAR on the inputs is impossible**: `register_output_array` tests the
  *output* against `prev_inputs_`, and the output is never a control buffer.
- The **only** surviving path is a recycled output address, i.e. exactly the
  residual declared above. Nothing new is found by this enumeration, which is
  the point of recording it: the risk is one specific, named, directional
  mechanism rather than an open question about the bindings.

One cosmetic non-issue found while doing this: `LagunaInjectChain.tail` is
assigned (`:11221`) even at `CHAIN=0`, where `tail` is never consumed as an
input. It is dead state on the unchained path and affects no binding.

## 5. Why D1 must be read before this slot is spent — and what it currently says

D1 is the M4 in-model chained-vs-unchained ladder. Under the M4 TRANSFER LAW its
*magnitude* is inadmissible for this concurrency-class question. Its **instrument
verdict** is admissible and is the only pre-spend check on §4.

Partial D1 result at the time of writing (rep 1, `tg=160`, `n ∈ {1600, 2400}`
supra-knee, slope and offset fitted independently per arm):

| arm | slope µs/dispatch | offset ms | implied knee |
|---|---|---|---|
| chained | 2.7124 | 5.5375 | 1215.5 |
| unchained | 2.3664 | 5.9731 | 1208.0 |

Two things follow.

**(a) The instrument is validated on the chained side, three independent ways.**
The M4 chained per-dispatch cost now has three estimates that share no code:
in-model r1 fit **2.607 µs**, standalone Metal probe **2.813 µs**, this ladder
**2.712 µs** — a ±4 % spread about 2.71. And both arms independently recover the
published M4 knee of 1209 (1216 and 1208, 0.6 % and 0.1 %). The knee being
chain-*independent* is what the piecewise host-encode model predicts.

**(b) The M4 in-model ratio is 1.146, not the probe's 2.729 — and there are two
explanations, only one of which is a broken instrument.**

- **Host-encode-bound, chain-blind by physics.** Above the M4 knee the exposed
  marginal cost is CPU-side encode, and encoding a dispatch costs the same
  whether or not a `memoryBarrier` precedes it. The probe was *not* in this
  regime: its unchained slope 1.027 µs at `tg=160` is well below the ~2.7 µs
  encode cost, so the probe was GPU-limited while the in-model ladder is
  host-limited. Under this reading the instrument is correct and the M4 ladder
  is simply **incapable** of measuring the ratio — below the knee both arms are
  hidden inside the 3.152 ms slack, above it both are host-bound.
- **Aliasing, per §4.** The unchained arm is still receiving barriers.

Both predict a ratio near 1.1, so rep 1 does not separate them. **A `tg=8`
in-model point does**, decisively, and it is cheap:

| prediction at `tg=8`, `n=3200` | implied `c` | implied knee | `dT` |
|---|---|---|---|
| host-encode-bound (`tg`-blind) | 2.71 µs | 1163 | **5.52 ms** |
| GPU-bound, tracking the probe | 1.26 µs | 2501 | **0.88 ms** |

A factor of 6.3 on a single point, two arms, ~7 minutes. I will run it as a D1
addendum before asking for the D5 slot. It also doubles as an M4-side dry run of
the D5 configuration, since D5 is `tg=8`.

If the `tg=8` addendum says **host-bound**, §4's residual risk is not what
produced the M4 ratio, D5's S0 branch stays interpretable, and the slot is worth
spending — because M5 has `knee = 0` and `slack ≈ 0`, so the M5 empties are
exposed from the first dispatch and the M5 regime is *not* the M4 supra-knee
regime. If it says **aliasing**, D5 cannot answer its question and I will
recommend the advisor spend the slot elsewhere rather than buy a false S0.

## 6. What D5 buys that D2 and D4 cannot

Both readings of D2's outcome (prereg-n100 §5) leave the D4 fusion pool intact
under Reading A, because removing a real dispatch saves its cost whether that
cost is host-side or GPU-side. D5 asks a different question and it is the one
that changes what *kind* of optimisation is worth staffing:

- **S0** ⇒ the only lever is literal dispatch-count reduction. D4's inventory is
  the complete opportunity set.
- **S1/S2** ⇒ a second, uncounted lever exists: making real dispatches mutually
  *independent* recovers `1 − 1/ratio` of their per-dispatch cost while removing
  none of them. At the M4-probe ratio that is 63 % of the pool, reachable
  without any fusion, via `ConcurrentContext` / hazard-tracking changes on the
  scored path. Nothing in the current D4 inventory prices this, and if it is
  real it dominates the fusion candidates on effort-to-payoff.

That asymmetry is the argument for the slot. D5 is the only design on the table
that can distinguish "406 dispatches cost 0.85 ms because there are 406 of them"
from "…because they are serialized".

## 7. What I will report from the receipt

Same list as D2 §8, plus the D5-specific items:

1. receipt ID; `S`, `T`, `bS`, `bT`; both floor verdicts with numbers;
   correctness verdict; `max_abs_diff`.
2. derived `ns` (recomputed from `decode_spt`/`prefill_spt`, shown alongside the
   receipt's own figure).
3. `dT_u(400)` **both paired and candidate-only**, labelled, primary = paired.
4. **ratio ± 1σ and ± 3σ, both conventions**, and the S0/S1/S2/X label.
5. `c_real` and `pool %`, with the Reading A / Reading B caveat carried from D2.
6. hand-computed acceptance-band arithmetic (D2 §7: degenerate, zero bits, fails
   identically to the unchanged control; the binding gates are the two 0.95
   floors).
7. the §4 pre-commitment honoured verbatim if the result is S0.
8. `senpai/check-editable-budget.sh 1849b376d73f69f9a6b9018619ac665ae4bceb33`
   output pasted.

## 8. Cost, ordering, constraints

- One ranked submission. Third in my queue, **after** D2's receipt lands and
  **after** the D1 `tg=8` addendum reports. Conditional on both.
- I will not submit without asking the advisor for the channel.
- Does not retry either of the two L2 submissions refused at 10:30:11Z /
  10:35:52Z.
- `LagunaRuntimeModel.swift` net growth is **+179 B** of the +200 B allowance.
  D5 changes only integer literal defaults (`0` → `400`, `160` → `8`, `1` → `0`),
  which is within a few bytes; if it would exceed the allowance I will ask first.
- Keeps the #27 instrument block alive. D5 is the last arm that needs it; once
  its receipt lands I have no further use for it and frieren's deletion
  authority is unblocked.
