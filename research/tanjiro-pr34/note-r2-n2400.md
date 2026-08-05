# Measurement receipt: the per-dispatch cost and the dispatch slack of the M5 decode step

## Read this first: the instrument is ON BY DEFAULT in this candidate

The official runner sets no environment variables, so this candidate cannot be
configured from outside. Every knob it uses is a *default integer literal* in
`Sources/MLXFastModel/LagunaRuntimeModel.swift`. That is deliberate, and it is
the only way an official receipt can carry a measurement. Concretely, this
candidate issues extra GPU dispatches on purpose during every single-token
decode step, and it will therefore look *slower* than the promoted frontier by a
known, intended amount. That slowdown is the measurement. It is not a
regression, it is not a bug, and it must not be read as a speed attempt.

The final commit of the research branch resets those literals to zero, at which
point the file is byte-identical to the promoted base and the instrument is
inert. Nothing in this note asks for the instrumented candidate to be promoted.

## Why this submission exists

Two independent models of the single-token decode step disagree with the
measured step time by the same amount, and neither can be resolved on any host
we own.

The first is a byte-rate roofline. A steady decode step must read about 1794 MB
of NVFP4 weights, scales, KV rows and activations. At the achieved rates we
measured for the four largest real kernels in the previous round of receipts,
those bytes account for about 2.94 ms. The measured steady step is about
4.32 ms. About 1.38 ms per step, roughly 29% of decode, is not explained by any
byte-rate model, and decode carries 75% of the score weight.

The second is a dispatch-overhead model. The shipped decode step issues about
406 real GPU dispatches per token, grouped into 45 command buffers. On a local
M4 Pro we measured a host-side encode-and-commit cost of about 4.1 microseconds
per dispatch that is entirely invisible to GPU-side timing. If a comparable
per-dispatch cost were live on the ranked M5, 406 dispatches would cost about
1.665 ms per step, which is the same order as the unexplained residual. That
coincidence is the entire motivation for this receipt.

The coincidence is not proof. Overhead only *costs* time if the step is actually
waiting on it. A step can issue 406 dispatches and pay nothing for them if the
GPU or the encoder has spare capacity that absorbs the work. So the question
this receipt answers is not "what does a dispatch cost" in isolation. It is:

> How much spare dispatch capacity does the shipped M5 decode step have, and is
> the shipped step above or below the point where adding a dispatch starts to
> cost real time?

That single number decides whether an entire family of candidate optimisations
is worth building. Kernel fusion, reduction packing, and command-buffer
consolidation all pay in exactly one currency: fewer dispatches. If the shipped
step sits far below the saturation point, every one of them buys zero
milliseconds on the ranked host, and the effort belongs elsewhere. If the
shipped step sits at or above it, the family is the largest unexploited item on
the board. Publishing a negative answer is as valuable to us as a positive one,
and this receipt is designed so that both answers are legible.

## The law being fitted

We model the extra decode time caused by injecting `n` extra dispatches per step
as a piecewise-linear saturation law:

```
dT(n) = max(0, n * c - slack)
```

`c` is the marginal cost of one dispatch, in microseconds, once the step is
dispatch-bound. `slack` is the spare capacity, in milliseconds, that absorbs the
first injected dispatches for free. The knee sits at `n_knee = slack / c`
injected dispatches, which is an absolute dispatch count of `406 + n_knee`.

The law was fitted and validated on a local M4 Pro over `n` in [600, 8000] with
out-of-sample residuals of 0.03 ms at two held-out levels, giving `c = 2.607` us
and `slack = 3.152` ms, so `n_knee = 1209` on that host. The M4 shipped step is
therefore at 25% of its own knee: on M4, removing dispatches is worth nothing.
The M5 is 2.6x faster per decode step, and the M5 answer does not follow from
the M4 answer under any hypothesis we can defend, which is why this needs
official receipts.

We pre-registered three competing predictions, in a commit that landed before
any receipt in this series was submitted, so the fit cannot be retrofitted:

| hypothesis | mechanism | c (us) | slack (ms) | n_knee |
| --- | --- | --- | --- | --- |
| `H_sat` | M5 decode is already dispatch-bound | 2.0-2.6 | < 0.2 | < 80 |
| `H_gpu` | slack is GPU-idle-gap shaped, so it scales with step time | 2.61 | 1.20 | 461 |
| `H_cpu` | slack is a fixed dispatch count, independent of GPU work | 2.27 | 2.72 | 1200 |

`H_cpu` is the prediction we expect to hold, on the strength of a falsification
test run locally: adding 268 MB of genuine extra memory traffic to every M4
decode step, about +8% of GPU time, bought exactly zero additional free
dispatches. The knee did not move. Under a GPU-idle-gap reading it should have
released around 96 dispatches worth of slack.

## What the instrument actually does

The injected work is a single Metal kernel, `laguna_inject_empty_dispatch_v1`,
launched with 8 threadgroups of 256 threads. It loads one control word from a
scratch buffer and its only store is predicated on that word equalling
`0xFFFFFFFF`, which the host never writes. The store therefore never executes.
The kernel is chained through a dedicated tail buffer so the MLX graph forces
its execution rather than eliminating it, but nothing downstream ever reads the
result, so the scratch buffer is never a data dependency of any real tensor.

The injected dispatches are spread evenly across the 40 transformer layer
boundaries rather than bunched, so they are distributed over the existing 45
command buffers in the same proportion as the real work.

Consequences that matter for correctness: every emitted token is bit-identical
to the promoted base, the KV cache is untouched, no numerical value anywhere in
the model changes, logical and physical KV positions advance by exactly the
supplied input length, and no state survives an invocation. This is a pure
addition of null work to the dispatch stream. The receipt should report a
maximum absolute difference of zero against the reference, and if it does not,
the reading is void and we will say so.

Threadgroup count is held at 8, the minimum useful launch, so the injected
kernel's own GPU cost stays negligible relative to the per-dispatch cost we are
trying to measure. On M4 the fitted `c` was flat across threadgroup counts from
8 to 160 and only grew by about 11 nanoseconds per threadgroup above 160, which
bounds the injected GPU work at 0.09 us per dispatch at 8 threadgroups, under
3.5% of the smallest hypothesised `c`. Prefill injection is set to zero in every
receipt of this series, which makes the prefill figure a flat internal control
across all five receipts and keeps the prefill axis, whose dispatch behaviour we
previously found self-inconsistent, out of the fit entirely.

## How the numbers are read out

Each receipt yields two scalars. The prefill total is
`S = 512000 * prefill_seconds_per_token` milliseconds. The steady one-token
decode step is `T = 1000 * decode_seconds_per_token - S/128` milliseconds, which
removes the amortised 512-token seed prefill from the teacher-forced decode
average. `dT(n)` is `T(n) - T(0)` measured against the zero-injection receipt of
this same series, and every receipt also carries its own same-session paired
baseline, which we use to confirm the session did not drift before differencing.

The precision budget: the within-window standard deviation of `T` is about 0.4%,
so 0.017 ms, and a two-receipt difference has a standard deviation of about
0.024 ms. Fitting the slope from the top two levels gives a standard error on
`c` of about 0.030 us, which is 1.3%. Three replicate receipts of the
uninstrumented base in the previous series had a coefficient of variation of
0.149% on the normalised score, which corroborates that noise model
independently.

## Safety of the deliberate slowdown

The decode floor rejects a candidate slower than 1/0.95 of the pinned reference.
The pinned decode baseline is 0.013890 s/token and the frontier runs at about
5.087 ms/token, so there is about 9.53 ms per step of headroom before the floor
bites. The largest level in this series costs at most 6.26 ms at the largest
hypothesised `c`, so it stays inside the floor; `c` would have to exceed
3.97 us, half again the M4 value on faster silicon, for the top level to breach
it. A floor breach returns a rejected verdict together with the full timing
metrics, so even in that case no measurement is lost.

## Model attribution

The model actually executed is Poolside Laguna XS 2.1, NVFP4-quantised, MLX
format, as pinned by the challenge checkpoint. The candidate changes only the
dispatch stream of the inference runtime around it; no weight, quantisation
scheme, or numerical path is modified.

## This receipt

| setting | value |
| --- | --- |
| injected empty dispatches per single-token decode step | **2400** |
| threadgroups per injected dispatch | 8 (256 threads each) |
| injected dispatches per multi-token prefill forward | 0 |
| spread across the 40 layer boundaries | yes |
| shipped real dispatches per decode step | ~406 (unchanged) |
| absolute dispatches per step | ~2806 |

This is set by editing two default integer literals and nothing else:
`DARKBLOOM_INJECT_DECODE_EMPTY` = 2400 and `DARKBLOOM_INJECT_EMPTY_TG` = 8.

### Role of this level in the series

Upper slope point. Paired with the 1600 level it yields the slope `c = (dT(2400) - dT(1600)) / 800` with a standard error of about 0.030 us. It also bounds the knee from above: under every hypothesis this level is well past saturation, so a zero reading here would falsify the law itself rather than any one branch of it.

### Pre-registered prediction for this level

| hypothesis | predicted dT at 2400 injected dispatches, ms |
| --- | --- |
| `H_sat` | 5.42 |
| `H_gpu` | 5.06 |
| `H_cpu` | 2.73 |

These numbers were committed before this receipt was submitted, so whichever
reading comes back, the branch it selects was named in advance.
