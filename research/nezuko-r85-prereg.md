# R85-D pre-registration — decode dispatch-cost ladder

**Written and committed BEFORE any ladder measurement was taken.** The commit
timestamp of this file is the pre-registration proof. Nothing below is edited
after the first ladder run; results and the verdict go in
`research/nezuko-r85-ladder-result.md`.

- Assignment: PR #458 (`maple-r85-d-dispatch-cost-ladder`, revision `r85-d-rev1`)
- Branch: `maple-nezuko/r85-dispatch-cost-ladder`
- Base: `codex/mlxfast-maple-20260804-advisor` @ `cc5688d0dfd6347bde0efd624cd6e10fdd4cfd26`
- Host: M4 Pro, 48 GiB, 14 CPU cores, Apple GPU generation 16 (low-memory
  startup profile, 247 barriers/step). `_nax` prefill kernels are unreachable
  here; this arm is decode-only, so that does not gate the result, but every
  number below is M4 evidence and is directional for M5.

## 1. Hypothesis under test

**H (assignment):** decode carries a fixed, work-independent per-dispatch cost
of roughly 2–3 µs, scaling linearly with dispatch count. Motivation: PR #441
priced `rmsbfloat16` at 3.00 µs/call and the router kernel at 4.70 µs/call
despite wildly different arithmetic, which looks like a launch floor.

**Null:** that floor is *work*-related — DRAM round-trip latency to first byte,
threadgroup ramp, reduction/writeback tail — so removing dispatch boundaries
refunds little or nothing.

## 2. Pre-registered prediction

I predict the fitted marginal cost of an injected **on-chain** null dispatch
(one dispatch + one dependency barrier, which is what a real fused kernel
actually deletes) is:

> **~1.0 µs/dispatch, 80% interval [0.4, 2.0] µs/dispatch.**

I separately predict the marginal cost of the same dispatch when the injected
work touches only **4 bytes** instead of the full 4 KiB hidden row is:

> **~0.6 µs/dispatch, 80% interval [0.15, 1.3] µs/dispatch**,

i.e. I predict `slope_wide > slope_tiny` by a factor of roughly 1.5–2×, which
would mean a material part of the "per-call floor" is memory work that fusion
only refunds when the data stays in registers.

I also pre-register that I expect **non-linearity**: specifically a soft
absorption region ("slack") at small N where the ladder slope is *below* the
large-N slope, following the saturating form
`dT = max(0, N·c − slack)` reported in `research/tanjiro-pr27-result.md:50-56`
and `research/tanjiro-pr47-result.md:95-115`. On M4 that knee was ~1209 extra
dispatches; on M5 it was ~17.4. If the M4 knee is really that far out, the
0–2560 extra-dispatch range of this ladder sits *entirely inside the slack
pool*, and I expect a measured slope closer to the low end of my interval.

### Prior reasoning (recorded so the prediction is falsifiable, not vibes)

The strongest existing joint fit in the programme
(`CURRENT_RESEARCH_STATE.md:395-401`, n=288, df=250) already separates the two
components:

| component | estimate | t |
| --- | --- | --- |
| barrier | **+1.3003 ± 0.0597 µs** | 21.8 |
| dispatch (barrier-free) | **+0.1231 ± 0.0481 µs** | 2.6 |
| dependent pair (dispatch + barrier) | **+1.4234 ± 0.0256 µs** | — |

Six independent studies agree the *barrier-free* dispatch lever is ~0:
`research/maple-fern-dispatch-tax-attribution.md:330-348` (+160 dispatches, 0
barriers → wall **−5.6 µs**), `research/nezuko-pr158-decode-dead-time.md:370-386`
(dispatch lever **−0.12 ± 0.22 µs**, a null),
`research/nezuko-dispatch-elasticity.md:237-241` (R²=0.0405, negative slope),
`research/tanjiro-pr34-r2-result.md:395-407` (0.49 µs/disp exposed, bracket
[0.36, 2.09]). The one surviving multi-µs observation is
`research/nezuko-pr158-decode-dead-time.md:1490-1620` (`nonorm`: +78 dispatches
carrying ~4 KB → **3.59 ± 1.44 µs/dispatch**, and it lived inside GPU *busy*
time, not inter-CB idle) — which is exactly why this ladder must vary bytes as
well as count.

So my prior is that the truth is near 1.4 µs for a dependent pair, that H's
2–3 µs is the high tail, and that the `nonorm` 3.59 µs number is inflated by
the 4 KB of traffic each injected op carried rather than by launch overhead.

## 3. Pre-registered decision table

Read off the **on-chain (dispatch + barrier)** slope, using the 95% interval on
the fitted slope. `N_extra` on the real glue table for the strong row is taken
as the ~39–40 dispatch boundaries a maximal decode fusion could plausibly
delete (matching the promoted-then-removed `cc6ddc1` merge, which deleted 39).

| fitted slope (95% CI centre) | verdict | mandated conclusion |
| --- | --- | --- |
| **≥ 2.0 µs/dispatch** | H strongly supported | dispatch count is a first-class decode lever; predicted headroom ~80–115 µs/step; **propose** (not build) one specific fusion arm and state why it will not repeat `cc6ddc1` |
| **0.5 – 2.0 µs/dispatch** | H partially supported | quantify the realistic ceiling as `slope × deletable boundaries`; report the score-equivalent; state whether that clears the ~80 µs/step decode bar |
| **< 0.5 µs/dispatch** | **H refuted** | close the whole dispatch-count-reduction family loudly; record it in the closed-families list so no future arm re-derives it |

Tie-breaks fixed in advance:

- If the 95% CI **straddles** a boundary, the verdict is the row containing the
  point estimate, and I report the ambiguity explicitly rather than picking the
  friendlier row.
- The **on-chain** slope is the headline because that is what a fusion deletes.
  The barrier-free slope is reported as a secondary decomposition.
- If the ladder is **non-linear** (knee/slack), the headline slope is the
  large-N secant over the top half of the ladder, and the small-N behaviour is
  reported separately, because a slack pool means *removal near the current
  operating point refunds less than the asymptotic slope*.
- Score conversion is fixed at **0.015280 % score per µs/step decode**; the
  decode bar is ~80 µs/step.

## 4. Pre-registered ladder design

One binary, all arms selected by environment variable, so no arm can differ
from another by code layout, register allocation, or kernel selection.

Injection point: `LagunaRuntimeDecoderLayer.callAsFunction`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:10495`), gated on
`x.dims(1, 1, LagunaConstants.hiddenSize)` so prefill is untouched. With 40
decoder layers, `K` injected ops per layer gives `N_extra = 40·K` extra
dispatches per decode step.

Two axes:

- **`wide` (W = 4096 B):** `for _ in 0..<K { x = x * onesBF16 }` on the live
  `[1,1,2048]` BF16 hidden stream. Each op is on the dependency chain (its
  input is the previous op's output), so it costs one dispatch *and* one
  barrier. `K = 0` is byte-identical to the flag being off, giving a clean
  zero point.
- **`tiny` (W = 4 B):** `var t = zeroBF16; for _ in 0..<K { t = t * onesBF16 };
  x = x + t` on a `[1]` BF16 scalar. Same chain structure, ~1000× less
  traffic. The final broadcast add is present for **all** K including K = 0, so
  it lands in the intercept and cancels out of the slope.

`x * 1.0` and `x + 0.0` are bit-exact in BF16, and `onesBF16`/`zeroBF16` are
stored BF16 `[1]` arrays (never Swift `Float` scalars, which would promote the
chain to FP32 and change both dtype and traffic).

Ladder: `K ∈ {0, 8, 16, 32, 64}` → `N_extra ∈ {0, 320, 640, 1280, 2560}`.

Measurement: `research/decode_probe.py` against the prebuilt
`.build-worker/release/mlxfast-runtime-worker`, golden seed
`correctness_prompts/public_longcopy_gate_english_512_256.json`, 512-token
prefill + ≥200 decode steps per run, first 16 steps dropped as warmup. Unit of
replication is the **run median**; ≥4 repeats per ladder point, arm order
palindromic/randomized within a session so drift cancels; pooling and intervals
via `research/nezuko_decode_probe_pool.py`.

I must also verify the injected dispatches actually reach the GPU (are not
elided by MLX) before trusting any slope — a `K=64` arm that is
indistinguishable from `K=0` because the multiply was folded away would look
exactly like a refutation.

## 5. Pre-registered reconciliation and `cc6ddc1` resolution

Step 3 of the assignment requires reconciling the slope against the real glue
pool measured on this host (`research/nezuko-a2-roofline.txt`, µs/step):
`residual_rms_router_rpg8_keys_v1` 305.1, `decode_router_top8_ordinal_table_norm`
185.7, `rmsbfloat16` 124.6, remainder 25.5 → **~641 µs/step of glue**, against
per-call floors of 3.00 µs (`rmsbfloat16`, 41 calls) and 4.70 µs (router).

The decisive test is `slope_wide` vs the 3.00 µs floor:

- if `slope_wide` ≪ 3.00 µs, then most of the 3.00 µs is the kernel's own work
  (DRAM round trip, ramp, reduction, writeback), **not** launch — and fusing
  two such kernels refunds only the smaller launch part unless the fusion also
  keeps the data in registers;
- if `slope_wide` ≈ 3.00 µs, the floor really is a launch tax and H holds.

Step 4 requires resolving the external negative: the promoted frontier
`cc6ddc1` (solver `a-github-name`, officialScore 2.6165035) built
`lagunaRoutedSharedSwiGLUQMVPackedTop8R1Kernel`
(`DARKBLOOM_MERGED_ROUTED_SHARED_GATEUP`, grid 9×256 threadgroups of 64
threads), deleting **39 dispatch boundaries**, and then *removed it* because
its isolated M5 price was not positive. I pre-commit to resolving this as
exactly one of:

- **(a)** the per-dispatch cost is small, or absorbed by a slack pool, so
  deleting 39 boundaries was worth ~0 to begin with;
- **(b)** the cost is real but the fusion re-paid it in geometry/occupancy (a
  9×256 grid of 64-thread groups is a different occupancy regime than the
  kernels it replaced);
- **(c)** a named third alternative, stated explicitly with its evidence.

## 6. Scope discipline

Per Rule 11 the instrument ships as an **unapplied** patch under `research/`
and `Sources/` is reverted before commit. **No fusion is implemented in this
PR under any outcome**, including the "H strongly supported" row. No official
submission is spent; the ranked channel is red on the public behaviour gate and
is owned by another student.
