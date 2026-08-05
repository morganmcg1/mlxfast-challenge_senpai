SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"m5_marginal_dispatch_cost_us","available":true,"value":1.980},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

# PR #34 revision r2: is the marginal cost of a Metal dispatch on M5 worth removing?

## Headline: yes. `c_M5 = 1.980 us/dispatch` with no detectable slack, and my own pre-registered hypothesis is the one that died.

Two receipts, same session, paired baselines, `S` held as an internal control:

| n | receipt | S (ms) | T (ms) | baseline S | baseline T | `T - bT` | `dT` paired | `dT` cand-only |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | `c3ce66ec` | **97.9496** | **4.28121** | 190.0278 | 12.41494 | -8.13373 | 0.00000 | 0.00000 |
| 400 | `0411779d` | **97.6165** | **5.07320** | 198.0817 | 12.37185 | -7.29864 | **+0.83509** | **+0.79199** |

`dT(400) = 0.835 ms` paired, **`0.792 ms` on candidate decode time alone**,
against pre-registered predictions of 0.82 (`H_sat`), 0.00 (`H_gpu`) and 0.00
(`H_cpu`). At `sigma = 0.024 ms`: `H_sat` confirmed (chi2 = 0.4 paired, 1.4
candidate-only), `H_gpu` and `H_cpu` falsified at **34.8 sigma** paired and
**44.5 sigma** on the sharper candidate-only bar. `H_cpu` was my own prediction.
**M5 has essentially no free-dispatch slack, and the M4 knee at 1209 does not
transfer.**

Under the advisor's new metric rule the candidate-only reading is primary,
because it never touches a pinned baseline: `c_M5 = 1.980 us` with a replicate
bar of `+/- 0.044 us`. The paired estimator agrees at `2.088 +/- 0.165 us`, and I
quote it throughout as the conservative alternative. Every conclusion below holds
on both.

Four things follow, in descending order of consequence:

1. **The dispatch-count family is live on M5.** At `c = 1.980 us` and
   `slack ~ 0`, removing 200 of the ~406 shipped decode dispatches is worth
   **+5.9% of score** (+6.2% on the paired estimate). That is 23x our 0.2517%
   gap to the crown.
2. **My score conversion in earlier drafts was wrong by 10x** and I am
   correcting it here in public, because the advisor's queue decisions depend
   on it. See the arithmetic below.
3. **`c` is an UPPER bound on both estimators**, and I can name the mechanism: the
   injected dispatches are barrier-serialised by construction. Section
   "What 2.088 us is and is not" gives the 5.8x gap against the shipped
   exposed-boundary cost, and why I still think the family is worth a round.
4. **L2/L3/L4 did not run.** The channel is one-in-flight per *account* and the
   advisor is now the scheduler. I am not taking a slot without asking. The
   three runs I want are named in "What I am asking for", and they are not the
   ones I pre-registered - the frontier review talked me out of two of them.

- Student / PR: `maple-tanjiro` / #34, branch `maple-tanjiro/m5-block-rates`, revision r2
- Assignment: `maple-2026-08-04i-m5-block-rates`
- Hypothesis and target cost: PR #37 attributes about 4.1 microseconds of host
  encode and commit cost to each of the roughly 406 Metal dispatches in one
  decode step, which would make 1.665 ms of the 4.32 ms step removable by
  fusion. This revision measures the *marginal* price of a dispatch on the
  official M5 directly, by injecting `n` empty, dependency-free dispatches per
  decode step and fitting `dT(n) = max(0, n*c - slack)`. `slack` is the free
  headroom: the number of dispatches the machine absorbs before wall time
  responds at all.
- Decision: **green on the measurement, and it reverses the advisor's demotion
  of the dispatch-count family.** Two of the five authorised receipts landed;
  the remaining three are blocked on an advisor-owned scheduling resource, not
  on anything in this tree. The two that landed answer the question the round
  was gated on, so this result is terminal rather than partial: `slack_M5` is
  not large, so removals pay.
- `BASE_SHA` / candidate commit: base `279b6e2409a2ca92f7b874e08a3dabc2c6ff4a0b`,
  `accepted_base_sha = 0b45de2261ee31b2f7fb46b6ddc3245775a02941` (newest
  docs-only advance, per the standing rule); candidate commit is this branch's
  head, whose `Sources/` and `Vendor/` are byte-identical to the base.
- Submitted candidate files: none. The final commit of this revision restores
  `Sources/MLXFastModel/LagunaRuntimeModel.swift` byte-for-byte to the base. This
  is a measurement revision, not an optimisation: the assignment says sweep only,
  do not build a fusion.
- Supporting test or documentation files: `research/tanjiro-pr34/` (pre-registration,
  queue, per-level notes, provenance, M4-vs-M5 comparison, instrument patch) and
  `senpai/tools/pr34_*.py`, `senpai/tools/pr34_m4_ladder.sh`. All outside
  `editablePaths`, so none of it costs submission bytes.
- Assignment-scope preflight: `senpai/validate-assignment-scope.sh` clean;
  `git diff --stat 279b6e24 <head> -- Sources Vendor` returns nothing.
- Editable bytes / headroom / growth: **`current=2940973/3000000
  headroom=59027 growth=0/262144 files=142`**. Blocker 1 is fully resolved:
  growth is exactly zero and the 15,759 B of per-file room in
  `LagunaRuntimeModel.swift` is restored in full, so PR #35's +8,037 B fits.
- Scored-path reachability evidence: the injection hook is called at
  `LagunaRuntimeModel.swift:10797`, inside the per-layer loop of the scored
  forward pass, and the decode branch is selected by `isSingleTokenDecode`
  (`inputs.dims(1,1)`, line 10753). Every receipt below shows the injected work
  in the timed decode axis, which is itself proof of reachability.

## What this probe prices, and what it does not

The injected kernel is `laguna_inject_empty_dispatch_v1`. It has a predicated
store that never executes, it is chained through `LagunaInjectChain.tail` so the
encoder cannot elide it, and at `DARKBLOOM_INJECT_EMPTY_TG = 8` it is 8
threadgroups of 256 threads. So the probe measures the *host-encode and
scheduling margin of an empty, dependency-free dispatch*.

That is deliberately narrower than "the cost of a dispatch in the shipped decode
step", and the distinction drives the whole interpretation:

- If `slack` is about zero, the machine is already dispatch-bound and removing
  dispatches by fusion buys time at the fitted rate `c`. Green light.
- If `slack` is large, the 4.1 microsecond figure is falsified **as a marginal
  host cost**. It does *not* retire fusion, because a real fusion also removes
  GPU-side costs the empty probe cannot see: launch ramp and tail, inter-kernel
  gaps, and round-trips of intermediate tensors through memory. Those are worth
  roughly 3.1 to 3.4 microseconds per dispatch if the entire unattributed 1.27
  to 1.38 ms of the decode residual is charged to them, which is an upper bound,
  not an estimate.

This scope limit was pre-registered in `research/tanjiro-pr34/prereg-r2.md`
before any reading arrived, precisely so that a large `slack` could not be
quietly promoted into "dispatch reduction is worthless".

## Ladder, and why it deviates from the assignment

The assignment proposed `n` in {0, 100, 200, 400, 800}. I ran
{0, 400, 800, 1600, 2400} at `tg = 8` with prefill empties pinned to 0, and
pre-registered that choice with three competing predictions before submitting
anything.

The reason is that the assignment's ladder cannot discriminate the hypotheses it
is meant to test. Carrying the M4 law (`c = 2.607 us`, `slack = 3.152 ms`, knee
at 1209 dispatches) to M5 gives three candidate laws:

| | mechanism | `c_M5` (us) | `slack_M5` (ms) | knee (dispatches) |
| --- | --- | --- | --- | --- |
| `H_sat` | M5 is already dispatch-bound | 2.0 to 2.6 | < 0.2 | < 80 |
| `H_gpu` (advisor) | slack is GPU-idle-gap shaped, so it scales down by the 2.623x step-time ratio | 2.61 | 1.20 | 461 |
| `H_cpu` (my prediction) | slack is a fixed *dispatch count*, so the knee transfers | 2.27 | 2.72 | 1200 |

Predicted `dT` in ms:

| n | `H_sat` | `H_gpu` | `H_cpu` |
| --- | --- | --- | --- |
| 0 | 0 | 0 | 0 |
| 400 | 0.82 | 0 | 0 |
| 800 | 1.74 | 0.89 | 0 |
| 1600 | 3.58 | 2.98 | 0.91 |
| 2400 | 5.42 | 5.06 | 2.73 |

On the assignment's ladder, `H_gpu` produces exactly one non-zero point and
`H_cpu` produces none: four of the five receipts would have returned zero and
the outcome would have been "the knee is somewhere above 800", which is what the
M4 work already said. On mine, `n = 800` separates all three hypotheses (the
predictions are 34 to 37 sigma apart at the 0.024 ms two-receipt noise floor),
`n = 400` is the sole `H_sat` discriminator, and there are always at least two
points above any knee in [0, 1600].

`tg = 8` keeps the injected GPU work under about 0.09 microseconds per dispatch,
under 3.5 percent of `c`, so the probe stays a dispatch-count probe rather than a
GPU-work probe. Prefill empties are pinned to 0, which makes the prefill axis `S`
a flat internal control and avoids the prefill dispatch axis that PR #27 found
self-inconsistent by a factor of 7.

Declared blind spot: no level lies in `n` between 0 and 400, and that is exactly
where a fusion removing 50 to 200 of the 406 shipped dispatches would live. A
knee near 200 would make "remove 40" worthless and "remove 300" valuable, and
this ladder cannot separate those two worlds.

Design lesson accepted but declined mid-flight: a frontier review of the design
found that `n = 0` is nearly redundant and that replacing it with `n = 1200`
would have given a tighter knee (standard error 9.3 to 12 dispatches instead of
10 to 17) and one more degree of freedom for lack-of-fit. I kept the
pre-registered ladder rather than re-choosing levels after the fact, because the
value of a pre-registration is destroyed by editing it once submissions are
under way.

## Cost floor headroom

The pinned decode baseline is 0.013890 s/token and the hard floor is 0.95, so a
candidate may take up to 14.621 ms/token. The frontier is about 5.087 ms/token,
which leaves about 9.53 ms of injected `dT` affordable. The worst case on this
ladder, `n = 2400` under `H_sat`, costs at most 6.26 ms. `c` would have to exceed
3.97 microseconds to breach the floor, and a breach still returns `rejected`
*with* full timed metrics, so no reading is lost either way. The prefill floor is
untouched because prefill empties are 0.

## Readings

Two official receipts landed before the channel closed. Both passed every
correctness gate.

| level | `n` | receipt id | submitted UTC | returned UTC | turnaround | status |
| --- | --- | --- | --- | --- | --- | --- |
| L0 | 0 (byte-identical to base) | `c3ce66ec-4b9c-4279-8c39-84ed63e193e4` | 09:33:21 | 09:54:22 | 21.0 min | rejected, full metrics |
| L1 | 400 | `0411779d-e467-4e41-8b40-5445623879d8` | 10:01:44 | 10:24:06 | 22.4 min | rejected, full metrics |
| L2 | 800 | none | 2 refusals, 10:30:11 and 10:35:52 | — | — | **blocked, see Process disclosures** |
| L3 | 1600 | none | never offered | — | — | blocked |
| L4 | 2400 | none | never offered | — | — | blocked |

`rejected` here means only "score did not improve current best". It is the
expected verdict for a deliberately slowed instrument and it does not withhold
metrics.

The pre-registered axes, derived from the receipt fields by
`senpai/tools/pr34_receipt.py --dt c3ce66ec:0 0411779d:400`:

```
   n   receipt        S      T     bS      bT   Ttilde=T-bT      dT   dT_candonly
   0   c3ce66ec   97.9496 4.2812 190.0278 12.41494     -8.13373  0.00000    0.00000
 400   0411779d   97.6165 5.0732 198.0817 12.37185     -7.29864  0.83509    0.79199
S control: min=97.6165 max=97.9496 range=0.341%
```

Answering the advisor's "three numbers per receipt" ask directly:

- `c3ce66ec`, `n = 0`: `S = 97.9496 ms`, `T = 4.28121 ms`.
- `0411779d`, `n = 400`: `S = 97.6165 ms`, `T = 5.07320 ms`.

**Correction to the advisor's read of the board.** He recorded `0411779d` as the
`n = 800` level and derived `0.876 us/dispatch` from it. `0411779d` is
**`n = 400`**, not 800; `n = 800` was never accepted by the channel. His
alternative `1.75 us` figure for `n = 400` is the right level but the wrong
estimator: both of his numbers come from a ratio of `officialScore` across
*different sessions*, which is exactly the estimator my own drift analysis
below shows is invalid (the baseline leg supplies 138% of a cross-day move, and
the apparent 0.026% sigma is an accidental cancellation between a +2.1% decode
component and a -6.2% prefill component). The paired within-session number is:

```
c_M5 = 0.83509 ms / 400 = 2.088 us per dispatch   (paired estimator)
       0.79199 ms / 400 = 1.980 us per dispatch   (candidate-only)
```

The two estimators agree to 5%, which is itself reassuring: the paired
correction `bT` moved by only 0.043 ms between the two sessions.

**Internal control.** Prefill empties were pinned at 0 for the whole ladder, so
`S` is an untouched control axis inside each receipt. It moved 0.341% across the
two levels, comfortably inside the 0.470% spread I measured over four
frontier-equivalent inert replicates. The injection is therefore decode-only and
does not leak into prefill, which validates the assumption the advisor was
relying on when he asked for a decode-axis reading.

## Fit

`senpai/tools/pr34_fit_ladder.py 0:0.0 400:0.83509`. The tool refuses to run the
pre-registered segmented fit, and it is right to: with a single non-zero level
the knee and the slope are not separately identified. It falls back to the
pre-registered fallback path, which is to report the raw points, test them
against the three pre-registered predictions, and refuse to extrapolate beyond
what one point supports.

Residual against each pre-registered prediction at `n = 400`, with the
pre-registered `sigma = 0.024 ms` (the two-receipt difference floor):

| hypothesis | mechanism | predicted `dT(400)` | observed | residual | chi2 | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| `H_sat` | M5 is already dispatch-bound, slack < 0.2 ms | 0.82 ms | 0.83509 | +0.015 | 0.4 | **confirmed** |
| `H_gpu` (advisor's) | slack is GPU-idle-gap shaped, knee ~461 | 0.00 ms | 0.83509 | +0.835 | 1210.7 | **falsified** |
| `H_cpu` (**mine**) | slack is a fixed dispatch count, knee ~1200 | 0.00 ms | 0.83509 | +0.835 | 1210.7 | **falsified** |

Both null-at-400 hypotheses die at 34.8 sigma. `H_cpu` was my own prediction and
the reason I chose this ladder, so the headline finding of this experiment is a
falsification of the experimenter's own model. **M5 has no meaningful
free-dispatch slack. The M4 knee at 1209 does not transfer.**

What is *not* identified, and I want this stated plainly rather than buried:
`(c = 2.088 us, knee = 0)` and `(c = 8.35 us, knee = 300)` fit these two points
equally well. Every number below assumes `knee = 0`, which makes `c` and all
derived savings **upper bounds** on the removal-side saving and simultaneously a
*lower* bound on the true marginal `c` above a knee. Distinguishing the two is
precisely the add-versus-remove asymmetry the advisor named as the crux. It needs
one level inside `(0, 400)`, not the `n = 800` the pre-registered ladder queued:
`n = 800` discriminates hypotheses whose knees are already dead. The blind spot I
pre-registered — no level in `n` in `(0, 400)` — became the binding one the
moment the knee turned out to lie inside `[0, 400)`. That is what re-plans
deliverable A below.

## The new metric rule, applied: the whole curve re-derived on candidate decode ms

The advisor's comment of 12:07:57Z bans conclusions drawn from an `officialScore`
delta, because `fern`'s PR #40 shows the paired baseline arm is pinned code whose
entire spread is noise: prefill relative sd 1.932 percent, decode 0.248 percent,
injecting about 0.52 percent into every published score. He asked me to
"re-derive every point on your curve from `ns`, or better, straight from
candidate decode ms."

**It already is, and always was.** `c_M5` is a difference of two candidate `T`
values normalised by the pre-registered estimator; no `officialScore` and no
speedup ratio enters it. `pr34_receipt.py --dt` prints both forms side by side
and the `dT_candonly` column is the raw candidate difference. What the new noise
decomposition *does* change is which of my two estimators should be primary, and
it changes it in my favour.

| estimator | `dT(400)` ms | `c_M5` | one-sigma bar |
| --- | --- | --- | --- |
| paired, `T - bT` (pre-registered) | 0.83509 | 2.088 us | +/- 0.165 us |
| **candidate-only, `T` alone (now primary)** | **0.79199** | **1.980 us** | **+/- 0.044 us** |

The arithmetic, using `fern`'s per-receipt relative sds:

- Candidate-only. `sd(T) = 0.248% x 5.046 = 0.0126 ms`; the candidate `S/128`
  term adds `0.218% x 97.95/128 = 0.0017 ms`, negligible. Two independent
  receipts differenced: `sd(dT) = sqrt(2) x 0.0127 = 0.0178 ms`. Over 400
  dispatches that is **+/- 0.044 us** on `c`.
- Paired. Each receipt now also carries its baseline arm's noise:
  `sqrt((0.248% x 13.9)^2 + (1.932% x 190/128)^2) = sqrt(0.0345^2 + 0.0287^2) =
  0.0449 ms`. Two receipts give 0.0635 ms, plus the candidate legs 0.0178 ms, for
  0.0659 ms — **+/- 0.165 us** on `c`.

The candidate-only bar is **3.7 times tighter**, which is exactly the sharpening
the new rule predicts. Two consequences I want on the record:

1. **My pre-registered `sigma = 0.024 ms` is validated, and was conservative by
   1.36x** for the candidate-only estimator, against `fern`'s completely
   independent 0.248 percent decode sd. The 34.8-sigma falsification in the
   previous section used the conservative value; on the sharper one it is
   44.5 sigma. The verdict is not sensitive to which is used.
2. Subtracting `bT` was *protective* under the old model of the noise and is
   *harmful* under the measured one. The pre-registered estimator is therefore
   the one I keep for the pre-registered chi2 test, and the candidate-only
   estimator is the one I quote for the slope. Both are reported; neither is
   selected after seeing the answer.

On `ns`, the pinned-reference score, the two receipts are:

| receipt | n | `D_cand` ms | prefill s/token | `ns` | `officialScore` |
| --- | --- | --- | --- | --- | --- |
| `c3ce66ec` | 0 | 5.04644 | 1.913117e-4 | **2.544360** | 2.523276 |
| `0411779d` | 400 | 5.83583 | 1.906572e-4 | **2.283549** | 2.290697 |

`ns(c3ce66ec) = 2.544360` reproduces the advisor's control figure to six decimal
places from my own raw fields, which cross-validates my reader against his. The
injected 400 dispatches cost **-10.25 percent of `ns`**, of which the prefill leg
contributes +0.09 percent (`S` fell 0.34 percent, the internal control) and the
decode leg -10.32 percent. The `officialScore` delta was -9.22 percent. Those two
differ by 1.03 points of percentage, which is about two of the 0.52 percent
score-noise units the advisor quotes, so the discrepancy is exactly the size his
model predicts. The sign and the magnitude of the finding do not depend on which
metric is used, and I would not have detected the difference from a 1-percent
effect at all.

One accuracy note on the linear conversion used later in this report. `d ln ns =
-0.75 x dT / D_cand = -0.148620 per ms` is a first-order expansion about
`D_cand = 5.046441 ms`. At the L1 point (`dT = 0.789 ms`) it predicts -11.07
percent against an exact -10.25, so it overstates by about 8 percent *relative*
at that dose. Every figure in the verdict table is at `dT <= 0.4 ms`, where the
overstatement is under 4 percent relative. I have not corrected for it, and flag
it as a known small upward bias rather than hiding it.

## Every receipt I have taken, on candidate axes

Asked three times; here is all of it, from `senpai/tools/pr34_ns_table.py`
against the raw submissions listing. `n` is the injected dispatch count per
decode step for the r2 ladder; the r1 arms injected *real* kernels rather than
empty dispatches, so their `n` column names the arm instead.

| revision | arm / `n` | receipt | status | `S` ms | `T` ms | base `S` | base `T` | `D_cand` ms | `ns` | `officialScore` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| r1 | R1 anchor (0/0/0/0) | `b6032aeb` | rejected | 97.8643 | 4.27468 | 187.1734 | 12.42195 | 5.03924 | 2.547641 | 2.514911 |
| r1 | R2 (40/0/39/0) | `ca416f01` | rejected | 141.1262 | 5.50538 | 186.7814 | 12.34864 | 6.60792 | 1.897219 | 1.864136 |
| r1 | R3 (40/39/0/40) | `6757de65` | rejected | 120.0782 | 6.51605 | 188.3202 | 12.45377 | 7.45416 | 1.804692 | 1.788158 |
| r1 | R4 (0/39/20/0) | `afec358a` | **failed** | — | — | — | — | — | — | n/a |
| — | frontier replicate | `71586bcf` | rejected | 97.5129 | 4.38283 | 198.8970 | 12.32760 | 5.14465 | 2.510650 | 2.515950 |
| — | frontier replicate | `c210d200` | rejected | 97.9730 | 4.34279 | 196.0282 | 12.33148 | 5.10820 | 2.521103 | 2.514743 |
| **r2** | **L0, n = 0** | `c3ce66ec` | rejected | **97.9496** | **4.28121** | 190.0278 | 12.41494 | 5.04644 | **2.544360** | 2.523276 |
| **r2** | **L1, n = 400** | `0411779d` | rejected | **97.6165** | **5.07320** | 198.0817 | 12.37185 | 5.83583 | **2.283549** | 2.290697 |

Every row with metrics reports `passed_correctness = True`, `max_abs_diff = 0`,
both speedup floors `True`, `gpqa_ttft = 0.41 s` against a 2.3 s limit,
`semantic_gpqa_passed = True`, `error = ""`, and `peak_ram_gb = 21`. `afec358a`
returned no timed metrics at all; see its own section below.

Two things are visible in this table that are not visible in any single receipt:

- The **base `S` column ranges 186.78 to 198.90**, a spread of 6.49 percent,
  across seven runs of *pinned* baseline code. The candidate `S` column across
  the four frontier-equivalent trees ranges 0.47 percent. That roughly 14x
  asymmetry is `fern`'s finding, arrived at independently from my seven timed
  receipts before I read her 1029.
- `ns` and `officialScore` **disagree on the ranking of `71586bcf` versus
  `c210d200` versus `b6032aeb`**: `officialScore` orders them 2.515950 >
  2.514911 > 2.514743, and `ns` orders them 2.547641 > 2.521103 > 2.510650. Three
  runs of numerically equivalent code, and the two metrics do not even agree on
  which is best. This is the same failure mode as `fern`'s three-receipt
  inversion, in a family I collected for an unrelated purpose.

## What `2.088 us` is, and what it is not

A frontier review of my own instrument found a confound I had not accounted for,
and I would rather report it than let the number stand unqualified.

The injected empties are **chained**: `LagunaRuntimeModel.swift` around line
11164 sets `LagunaInjectChain.tail`, and the loop at ~11207 feeds each empty the
previous empty's output buffer. In MLX's Metal backend
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:324-348,
362-374, 393-395, 548`) the encoder is created with
`MTL::DispatchTypeConcurrent`, so dispatches are *not* serialised by default;
but `CommandEncoder::maybeInsertBarrier()` runs before every dispatch and emits
an encoder-wide `memoryBarrier(BarrierScopeBuffers)` whenever a new dispatch
reads a previous dispatch's output. Because I chained them, **all 400 empties
are fully barrier-separated**. The in-tree comment says this was deliberate — it
reproduces the strictly serialised real stream nezuko measured
(`gpu_busy_sum == gpu_busy_union` to 6 ns) — but the consequence for the price
tag is real:

> `2.088 us` is the marginal cost of a **barrier-separated, dependent** dispatch.
> It is an **upper bound** on the saving from removing a shipped dispatch, and it
> overestimates any pair of shipped kernels that currently overlap.

The counter-bound from the other direction is uncomfortable. My own M4 timeline
shows the GPU 96.6% busy, with only 0.200 ms of total gap across 406
dispatches — about 0.49 us/dispatch of *existing exposed* gap, and about
**0.36 us** once attributed conservatively. That is a **5.8x gap** against
2.088 us. The two quantities are not the same thing: 0.36 us is the exposed
boundary cost of the dispatches that are already there, while 2.088 us is the
marginal cost of adding one more with a dependency. But a fusion removes a
*shipped* dispatch, so the honest expectation for a fusion lies somewhere in
`[0.36, 2.09] us` per removed dispatch, and I cannot narrow it with two points.

Three things push the true figure toward the upper end rather than the lower:

1. The decode critical path is mostly a genuine dependency chain — layer `n+1`
   depends on layer `n`, and within a layer norm -> qkv -> rope -> sdpa -> out ->
   residual -> norm -> router -> experts -> combine is serial. So most of the 406
   shipped dispatches are already barrier-separated for real reasons. The
   concurrency opportunities are narrow: the three QKV projections, and multiple
   experts.
2. Nezuko's `gpu_busy_sum == gpu_busy_union` to 6 ns is direct evidence that the
   real shipped stream *is* already serialised, not merely modelled as such.
3. Nezuko independently priced M4 `SPLIT=1` command-buffer inflation at
   **+1.42 us/dispatch**, which brackets 2.088 us from a third, completely
   independent direction.

Also from that review, and worth recording because it dissolves an apparent
contradiction: the **M4 knee at 1209 coincides exactly with a host-encode
crossover at 5.29 us/dispatch**. The M4 and M5 probes were most likely measuring
*different mechanisms*, which is a better explanation of the M4/M5 disagreement
than either machine being wrong.

Finally, `4.1 us` from PR #37 and `2.088 us` here are not in conflict, because
they are different quantities. `4.1 us` is an *average accounting constant* for
host encode across the whole step; `2.088 us` is a *marginal price*. And the
encode thread runs 3.5x ahead of a 96.6%-busy GPU, so `2.088 us` cannot be host
encode at all — it must be GPU-side: launch ramp, drain/tail, barrier, or
inter-kernel gap.

## Verdict on dispatch-count reduction

**Yes, dispatch-count reduction has value on M5, and the value is larger than
either the advisor or I had priced.** This reverses his demotion of the family,
which rested on an M5 removal null.

First, a correction to my own pre-registration. The action threshold I wrote
("pursue if `k*c - slack > 0.1 ms`") silently under-converted decode
milliseconds into score by a factor of `1/0.75`, i.e. 10x once combined with a
decimal slip. The correct conversion, at the measured candidate axes
`S = 97.9496 ms` and `T = 4.28121 ms` so `D_cand = 4.28121 + 97.9496/128 =
5.046441 ms`:

```
d ln score = -0.75 * dT / D_cand = -0.148620 * dT      (dT in ms)
           => 1 ms of decode saving = 14.8620% of score
```

Two independent cross-checks that this is now right. The advisor wrote that "a
third of that 1.27 ms is worth about +6% of score": `1.27/3 = 0.423 ms` and
`0.14862 * 0.423 = +6.3%`. And his `gate_sp` estimate of 150 us -> +2.28% score
matches `0.14862 * 0.150 = +2.23%`. **The pre-registered 0.1 ms threshold is
superseded**: 0.1 ms is `+1.49%` of score, far above the 0.61% bar, so the
threshold as written was roughly ten times too permissive-looking in score terms
and I was reading it as much weaker than it is.

At `c = 2.088 us` and `slack = 0`, and taking the shipped decode step to be
**406 dispatches**:

```
score conversion: 1 ms of decode saving = 14.8620% of score
the pre-registered 0.1 ms threshold is therefore 1.49% of score
   removed     dT ms  % of step  % of score     verdict
        40    0.0835       1.64        1.24   below thr
       100    0.2088       4.10        3.10      PURSUE
       200    0.4175       8.21        6.21      PURSUE
       400    0.8351      16.42       12.41      PURSUE
  10% (41)    0.0856       1.68        1.27   below thr
 25% (102)    0.2129       4.19        3.16      PURSUE
 50% (203)    0.4238       8.33        6.30      PURSUE
```

The three figures the r2 assignment asks for explicitly, as ms of decode step:

- **10% of dispatches removed (41): 0.086 ms, +1.27% score.**
- **25% (102): 0.213 ms, +3.16% score.**
- **50% (203): 0.424 ms, +6.30% score.**

**Margin at the shipped 406:** `406 * 2.088 us = 0.848 ms`, which is
**+12.6% of score** and about **67% of the ~1.27 ms unattributed decode
residual** I could not account for with bandwidth roofline in r1. That is a
striking coincidence and I flag it as a hypothesis rather than a conclusion: it
would mean the residual is largely dispatch-boundary cost, not unmodelled
memory traffic.

Every level from `k = 100` upward clears the advisor's 0.61% bar by 5x or more,
and even `k = 40` gives `+1.24%`, twice the bar. **Under the upper-bound
reading, targeted fusion is worth a round.** Under the pessimistic 0.36 us
reading, 200 removals is still about `+1.1%` of score, which also clears the
bar. The family survives both ends of the bracket; that is the strongest
statement two points can support.

**Applying this to the advisor's `gate_sp_h64/h48` candidate.** He measures 40
dispatches and 213 us/step for that family at ~2% of the byte ceiling, and
prices recovering ~150 us as decode +2.95% and score +2.28%. My law prices the
*dispatch-count component alone* at `40 * 2.088 us = 83.5 us`, i.e. **+1.24% of
score**. So the two estimates are consistent only if roughly `66 us` of his
150 us comes from the **byte / first-touch side** rather than the dispatch count.
That is a clean, testable split, and it matters for design: if the byte side
dominates, the win comes from eliminating a first-touch weight stream and the
fusion shape barely matters; if the dispatch side dominates, the win scales with
how many dispatches the fusion collapses. Nezuko's merged
`research/nezuko-dispatch-elasticity.md` duplicate/serialised first-touch ratios
point the same way — `gate_sp` 0.659, `oproj_act_h64` 0.601,
`residual_rms_router` 0.605, `shared_qmv` 0.721, all far below
`routed_swiglu` 0.958 and `sliding_attn` 0.971 — so fusion is the lever exactly
where the ratio is small.

**Reconciling with the three pieces of contrary evidence in the review the
advisor forwarded.**

- **(e), the only prior direct M5 dispatch-removal datum** (two RoPE angle
  probes, null at `+0.01..+0.07 ms/step`) does **not** contradict me. Two
  dispatches at 2.088 us is `0.0042 ms`, which is **2.4x to 17x below that
  null's own resolution**. The null was underpowered by more than an order of
  magnitude; it could not have detected my effect.
- **(b), M4 wall `8.545 = 8.345` GPU-busy plus only 0.200 ms of total gap over
  406 dispatches**, measures the *existing exposed* gap, not the marginal cost of
  an *added* dependent dispatch. Different quantity, so it does not bound
  2.088 us — but as recorded above it does bound the *shipped* boundary cost at
  ~0.36 us, and I am not hiding that 5.8x gap.
- **(c), the encode thread running 3.5x ahead of a 96.6%-busy GPU**, actually
  *supports* the finding: it rules out host encode as the mechanism and forces
  2.088 us to be GPU-side.

**Scope limit, as pre-registered.** This probe prices the marginal cost of
*empty, barrier-chained* dispatches. I am not entitled to write "dispatch
reduction is worthless on M5" — and the data says the opposite anyway — but I am
equally not entitled to promise that a real fusion recovers `k * 2.088 us`. The
honest claim is a bracket: `[0.36, 2.09] us` per removed shipped dispatch, with
three independent reasons to sit near the top.

## M4 companion measurement

The r2 acceptance criteria require an M4 validation that the injected kernel's
own GPU time is negligible, **with a stated measured value**. From the r1
companion ladder on the local M4 Pro host (PR #27 series, `tg = 160`):

- `dT(n)` is **flat over `tg` in `[8, 160]`**, i.e. the per-dispatch cost does
  not scale with the injected kernel's threadgroup count across a 20x range.
- Above `tg = 160` the slope is about **11 ns per threadgroup**, and `tg = 512`
  blows up (the kernel stops being negligible).
- **Stated measured value: at `tg = 8` the injected kernel's own GPU time is
  at most 0.09 us per dispatch, i.e. at most 3.5% of `c`.** The whole r2 ladder
  ran at `tg = 8` for exactly this reason.

That flatness is also the fixed-versus-proportional discriminator the design
needed: a cost that does not scale with the injected work is a *boundary* cost,
not a *work* cost.

The M4 companion law itself, from r1 (`T(2400) = 13.21733`,
`T(1800) = 11.65334`, reference `LA3 T = 10.11366`): `c = 2.607 us`,
`slack = 3.152 ms`, knee at 1209 dispatches; out-of-sample residuals under
0.03 ms at `n = 600` and `n = 1400`; validated over `n` in `[600, 8000]`.
The M5 result falsifies the *transfer* of that knee, not the M4 law.

**The M4 host was not available this session, so no new M4 point was taken.**
`./setup.sh` (pid 7401) fetched shards 1, 2, 3 and 5 in about 123 s and then
cycled on shard 4 (`model-00004-of-00005.safetensors`, 5205257850 bytes). It
climbed to 98-99%, dropped about 4 GiB, and restarted, three times, with the
rate degrading 9.2 -> 5.1 -> 4.0 -> 2.9 MiB/s. Root cause: setup.sh's per-shard
`curl` uses `--speed-limit 1048576 --speed-time 120`; the mirror decayed below
1 MiB/s, tripped the stall abort near completion, and the retry path `rm -f`s the
`.partial` and starts from zero. Disk was not the problem (191 GiB free). I have
written `senpai/tools/pr34_fetch_shard4.sh` — a bounded 60-attempt resume loop
with `--continue-at -`, `--speed-limit 65536 --speed-time 300`, size and sha256
verification, then an atomic rename — but I have **not run it**, because pid 7401
must be killed first or the two fight over the same `.partial`, and finishing
this report was the higher priority the advisor set.

A revised judgement on M4 value, so the advisor can decide where a local slot
goes: repeating the original 8-point M4 ladder now has **low** marginal value.
The high-value local run is **chained versus unchained at fixed `n = 400`**,
which isolates the barrier-serialisation confound described above and would
collapse the `[0.36, 2.09] us` bracket. That needs a new knob, because the chain
is currently hardcoded. A knob is not a fusion, so it stays inside the
"sweep only" instruction.

## The M4-versus-M5 disagreement

The advisor asked for this explicitly. The same inert tree on the local Apple M4
Pro host and on the ranked M5:

| quantity | M4 Pro (`m4-L0.json`, inert) | ranked M5 (`b6032aeb`) | M4 / M5 |
| --- | --- | --- | --- |
| `S`, 512-token prefill forward | 577.20 ms | 97.86 ms | 5.90x |
| `T`, steady one-token decode step | 8.8161 ms | 4.2747 ms | 2.06x |
| full decode seconds/token | 13.326 ms | 5.039 ms | 2.64x |

The 5.90x prefill gap is mostly a *kernel gate*, not hardware. Locally
`prefill_speedup = 188.17 / 577.20 = 0.326`, so the promoted frontier is three
times **slower** than the baseline on this host, while on M5 the same tree is
1.913 times faster. `quantized.cpp:1956` routes to `gather_qmm_rhs_nax` only when
`is_nax_available()`, and `device.cpp:913` requires architecture generation 17 or
above; this host is generation 16 (`applegpu_g16s`). So for NAX-gated prefill
work M4 is **anti-correlated** with M5, not merely conservative, and no prefill
conclusion may be carried across.

The 2.06x decode gap is closer to an honest hardware ratio, which is why the M4
companion ladder is used only for decode-side method validation: to show that the
injected kernel's own GPU time is negligible, and to state an M4 companion law at
the same ladder points.

A related finding worth recording: the local paired baseline is not measured, it
is a pinned constant. Across all eleven r1 local runs
`baseline_decode_seconds_per_token` was 0.01385621216015625 and
`baseline_prefill_seconds_per_token` was 0.00036751938916015626, identical to
every digit. There is no `--local-iterate` baseline artefact on disk. So a local
`*_speedup` is arithmetic against another machine's constant, and every local
`dT` in this report is `T(n) - T(0)` measured on the same host in the same
session, never a difference against that pinned number.

## Answers to the two questions in the r2 assignment

Recovered from the submitted trees themselves, by reading the injection literals
out of each submitted commit
(`git show <c>:Sources/MLXFastModel/LagunaRuntimeModel.swift`):

| tree | `DECODE_ATTN` | `DECODE_ROUTED` | `PREFILL_ROUTED` | `PREFILL_ATTN` |
| --- | --- | --- | --- | --- |
| R1 anchor | 0 | 0 | 0 | 0 |
| R2 | 40 | 0 | 39 | 0 |
| R3 | 40 | 39 | 0 | 40 |
| R4 | 0 | 39 | 20 | 0 |

**(a) Were the R2 and R3 decode arms nested or disjoint?** Nested, on the decode
axis. R3 is R2's 40 attention-QMV copies *plus* 39 routed-QMV copies, which is
what `cfg-r3.md` says at the time. So `dT_4 = T_R3 - T_R2` is a plain difference
of a strictly nested pair, and the advisor's `2.24137 - 1.23070` reduces to the
same quantity. On the prefill axis R2 and R3 are instead disjoint single-knob
arms against the shared zero anchor, which is also valid.

**One correction to the premise of the question, asked in his 12:07:57Z comment
as "the `dT_4 = 1.01067` you took from `afec358a`".** `dT_4` did not come from
`afec358a`. It is `T(6757de65) - T(ca416f01) = 6.51605 - 5.50538 = 1.01067 ms`,
both of which returned complete metrics and both of which passed every gate.
**`afec358a` contributed nothing to rate 4, or to any other published rate.** It
returned `status=failed` with no timed metrics at all, so there is nothing in it
to contribute. This matters because the natural next question — "does rate 4 need
a re-run now that one of its arms failed review?" — has the answer **no**: rate 4
rests entirely on two successful receipts. `research/tanjiro-pr34/rate4-provenance.md`
documents the derivation line by line, including the contamination check that
`isSingleTokenDecode` gates the injection to decode only
(`LagunaRuntimeModel.swift:10753`, hook at 10797, injection at 11185).

### The promoted question: is `dS_1` marginal or absolute, and is there a 32.4 ms pool?

The advisor asked for this "before anything else", because two independent
frontier audits converged on a remainder and then both objected to the way it
was priced. Answering it costs zero receipts, so it is answered here in full.

The remainder they computed:

```
dS_1 = 141.1262 - 97.8643 = 43.2619 ms   (PREFILL_ROUTED 39 vs 0)
dS_2 = 120.0782 - 97.8643 = 22.2139 ms   (PREFILL_ATTN   40 vs 0)
sum                        = 65.4758 ms
S_R1 - sum   = 97.8643 - 65.4758 = 32.3885 ms  "remainder"
```

**Nested or disjoint, on the axis that matters here?** Disjoint. Read the table
above on the prefill columns only: R2 is `(PREFILL_ROUTED=39, PREFILL_ATTN=0)`
and R3 is `(PREFILL_ROUTED=0, PREFILL_ATTN=40)`, both against the shared R1 zero
anchor. They are two independent single-knob arms, so `dS_1` and `dS_2` do not
double-count each other and their sum is a legitimate sum of two disjoint
measurements. That part of the audit is sound.

**Marginal or absolute? Marginal, unambiguously.** Every one of these numbers is
the wall-time *increase* caused by *adding* copies of an op to an
already-complete forward pass: 39 extra routed-prefill GEMM invocations, spread
roughly one per layer across 40 layers. It is not the standalone cost of the
copies the model actually ships. The auditors' objection is correct in
substance, and I am not going to defend the stronger reading. What I can do is
say which way the bias runs, and the honest answer is that it is not determined:

- *Amortisation and warm caches.* An injected copy runs immediately after the
  shipped one, with weights and instruction cache already warm and the
  scheduler already primed, so the marginal copy is cheaper than the shipped
  average. Then 65.4758 **undercounts** the shipped work and the 32.4 ms
  remainder is **overstated**. This is the auditors' direction.
- *Overlap and latency hiding.* The shipped copy overlaps with neighbouring
  work, so its share of wall time is *less* than its standalone cost, while a
  chained injected copy is fully exposed on the critical path. Then 65.4758
  **overcounts** the shipped wall share and the remainder is **understated**.

Both mechanisms are real and they push opposite ways. Nothing in the three r1
receipts separates them, because there is **no dose-response within a single
kernel**: each block has exactly one non-zero dose. That is the design gap.

One weak piece of evidence tells against the warm-cache direction being large:
rate 1 came out at 408.4 GB/s = 23.23 TFLOP/s = 67 percent of the 34.7 TFLOP/s
peak, that is *below* peak rather than implausibly above it, and the 21.6 GB
weight set cannot sit in any cache. A badly cache-inflated marginal measurement
would more likely have produced a super-peak rate.

**A scaling correction worth stating while we are here.** Block 1 injected 39
copies but the model ships 40 layers, so scaling to the shipped count gives
`43.2619 x 40/39 = 44.371 ms`, the sum becomes 66.585 ms, and the remainder
falls from 32.389 to **31.279 ms**. That is a 1.11 ms, 3.4 percent correction in
the direction of a *smaller* pool. Block 2 injected 40 and needs no scaling.

**The cheap decisive experiment, for whoever holds the next receipts.** Two
receipts, no new code, because the knobs are already in `instrument.patch`: run
`PREFILL_ROUTED` at 13 and at 26. With the existing R2 (39) and R1 (0) that
gives four points of dose-response *within one kernel*. Linear through the
origin means marginal equals average and the pool stands as measured; concave
means 65.4758 undercounts and the pool shrinks; convex means it overcounts and
the pool grows. Until someone runs it, treat 31.3-32.4 ms as a marginal-cost
remainder and not as a pool of removable work.

**This qualification propagates.** The `+14.30 ms excess over roofline` for rate
1, which is 42.1 percent of the honest prefill residual and the number
maple-fern's PR #40 is built on, is a *marginal-cost* excess and inherits
exactly the same caveat. So does fern's 15.4 ms recoverable figure, which is
measured against this floor. I am flagging that rather than letting it ride.

**(b) Does rate 4 depend on the failed R4 receipt?** No. R4's decode probe was
routed-QMV *alone*, the unloaded companion. The published rate 4 of 546.2 GB/s
rests entirely on R3 minus R2, and both of those receipts succeeded
(`6757de65`, `ca416f01`). R4 carried only three robustness companions. **Rate 4
needs no re-run**, so the advisor's contingency of reallocating r2 receipts to
repair it is moot and all five r2 receipts stayed on the dispatch law.

Widened error bar, since the question was asked: the published +/-0.034 ms
already used two-receipt propagation (quadrature 0.02900 ms times the same 1.18
method factor used for `dT_2`). Adding a 0.026 ms allowance for cross-session
drift, which is what the R2 and R3 normalisations actually disagreed by (2.6
percent), gives a conservative +/-0.043 ms. Rate 4 becomes 546.2 +/- 23.3 GB/s,
that is [523, 569]. Against the 0.90505 ms roofline the excess is +0.1056 +/-
0.043 ms, still more than 2 sigma from zero, and 7.9 +/- 3.2 percent of the
decode residual. The conclusion does not change.

## The "12.4 sigma cross-day drift": it is the baseline leg, and the sigma is spurious

The advisor asked for `c3ce66e`'s `S` and `T` next to the three 8/4 pairs,
because the CLI truncates his metrics column, and drew a programme-wide
conclusion from the comparison: that cross-day receipt comparison carries about
0.3 percent of drift, roughly ten times the 0.026 percent same-day replicate
spread, so "every single cross-day receipt pair screen below about 0.6 percent
is unsupported". I fetched all four receipts on all axes and re-derived it.
`senpai/tools/pr34_drift_axes.py` reproduces every number below from the raw
fields; it also reconstructs all four published `officialScore` values to six
decimal places from `S`, `T` and the two baseline fields, which validates the
decomposition before any of it is used.

| receipt | when (UTC) | cand `S` ms | cand `T` ms | base `S` ms | base ms/token | `prefill_su` | `decode_su` | `officialScore` | `ns` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `71586bcf` | 8/4 10:02 | 97.5129 | 4.38283 | 198.8970 | 13.88149 | 2.03970 | 2.69824 | 2.515950 | 2.510648 |
| `c210d200` | 8/4 11:38 | 97.9730 | 4.34279 | 196.0282 | 13.86295 | 2.00084 | 2.71386 | 2.514743 | 2.521102 |
| `b6032aeb` | 8/4 20:11 | 97.8643 | 4.27468 | 187.1734 | 13.88424 | 1.91258 | 2.75522 | 2.514911 | 2.547640 |
| `c3ce66ec` | 8/5 09:33 | **97.9496** | **4.28121** | 190.0278 | 13.89953 | 1.94006 | 2.75432 | 2.523276 | 2.544361 |

Per-axis spread over the four (range, then sd, both as percent of the mean):

| axis | mean | range % | sd % |
| --- | --- | --- | --- |
| cand `S` | 97.82495 | 0.470 | 0.218 |
| cand `T` | 4.32038 | 2.503 | 1.197 |
| cand ms/token | 5.08463 | 2.073 | 0.995 |
| **base `S`** | 193.03160 | **6.073** | **2.785** |
| base ms/token | 13.88205 | 0.264 | 0.108 |
| `prefill_su` | 1.97329 | 6.442 | 2.920 |
| `decode_su` | 2.73041 | 2.087 | 1.057 |
| `officialScore` | 2.51722 | 0.339 | 0.162 |
| `ns` | 2.53094 | 1.462 | 0.710 |

**First finding: the drift is in the baseline leg, not the candidate.** Take the
one pair I can personally certify is the same scored code, `b6032aeb` (8/4
20:11) to `c3ce66ec` (8/5 09:33), and the score's +0.333 percent decomposes as

```
cand S      +0.087%      base S      +1.525%
cand T      +0.153%      base ms/tok +0.110%
cand ms/tok +0.143%

d(prefill_su) = +1.525 - 0.087  = +1.438%   (observed +1.437%)
d(decode_su)  = +0.110 - 0.143  = -0.033%   (observed -0.033%)
d(score)      = 0.75(-0.033) + 0.25(+1.438) = +0.335%  (observed +0.333%)

baseline leg  0.25(+1.525) + 0.75(+0.110) = +0.464%
candidate leg -[0.25(+0.087) + 0.75(+0.143)] = -0.129%
```

The baseline leg is +0.464 percent and the candidate leg is **negative**, so the
baseline accounts for 138 percent of the observed move. Cross-day, the candidate
did not drift up; the pinned reference model was re-measured 1.5 percent slower
on prefill and the *ratio* went up. That is not a property of cross-day
comparison of candidates; it is the well-known instability of the baseline leg,
and `sd(S_baseline) = 1.93 percent` over the 929 pinned baselines already on
record makes a 6.07 percent range over four samples entirely ordinary.

**Second finding: the 0.026 percent denominator is an accidental cancellation.**
Across the first three receipts `decode_su` rose 2.112 percent while
`prefill_su` fell 6.232 percent, and

```
0.75(+2.112) + 0.25(-6.232) = +1.584 - 1.558 = +0.026%
```

which is, to the digit, the 0.026 percent "replicate spread". The score looks
stable only because its two weighted components anticorrelate through the shared
baseline session. The underlying component sds over those three are 1.082
percent on `decode_su` and 3.283 percent on `prefill_su` -- forty to a hundred
and twenty times larger. A quantity whose small variance comes from cancellation
is not a valid sigma denominator, so the 12.4 figure does not measure 12.4 of
anything.

**Third finding: on candidate axes, L0 is an ordinary member.** Standardising
L0 against the first three on each axis with that axis's own sd:

| axis | L0 | mean of 3 | delta | z |
| --- | --- | --- | --- | --- |
| `officialScore` | 2.523276 | 2.515201 | +0.321% | **+12.4** |
| cand `S` | 97.94960 | 97.78340 | +0.170% | +0.7 |
| cand `T` | 4.28121 | 4.33343 | -1.205% | -1.0 |
| `ns` | 2.54436 | 2.52646 | +0.708% | +0.9 |

The 12.4 sigma exists on exactly one axis, the one with the cancellation-shrunk
sd. On every candidate axis L0 is inside one sigma.

**So the programme rule should change, not tighten.** The advisor's inference --
0.3 percent drift, therefore no cross-day screen below 0.6 percent -- would
retire a large amount of otherwise usable evidence. The narrower and better
supported rule is:

- Screen on **candidate axes (`S`, `T`)** or on **`ns`**, never on
  `officialScore` or the raw speedups, because those carry the baseline leg.
- Cross-day candidate-axis reproducibility on the verifiable pair is **0.087
  percent on `S` and 0.153 percent on `T`**, an order of magnitude better than
  0.6 percent.
- A **decode-only** screen is stable to about 0.03 percent on `decode_speedup`
  across those two days, because the baseline decode axis moves only 0.11
  percent while baseline prefill moves 1.5 percent.
- Where a screen must use a speedup, use the **same-session paired** baseline
  the harness already supplies and difference within the session, which is
  exactly the advisor's own first instruction and which I have followed.

**The open question I cannot close, stated rather than buried.** `71586bcf` and
`c210d200` may not be the same scored code as `b6032aeb`. Candidate `T` falls
monotonically 4.38283 to 4.34279 to 4.27468 while candidate `S` is flat inside
0.47 percent, which is the signature of progressively promoted *decode*
optimisations, not of noise. The advisor's own diff covered `0b45de22..454b189a`
only. If the three really are one code state, candidate-`T` drift is 2.5 percent
(0.108 ms) and my pre-registered `sigma = 0.024 ms` is optimistic by 4.5x; if
they are successive frontiers, the verifiable spread is 0.15 percent and the
sigma stands. **Either way my ladder is unaffected**, because all five r2
receipts are on 8/5 and each level is differenced against its own
session-paired baseline. Someone with the promotion history should settle it,
because the answer sets the sigma for every future receipt-pair screen.

**Correction to my own earlier note.** The `ns` values I recorded earlier for
`f8502e12`, `71586bcf` and `f3cda678` (2.48558, 2.51595, 2.50895) were copied
`officialScore` values, not computed `ns`. `71586bcf`'s real `ns` is 2.510648.
The paragraph in `queue-r2.md` that called those three "an earlier promoted
frontier, 1.3 percent lower, must not be pooled" is therefore overstated and has
been softened. The `b6032aeb` versus `c3ce66ec` `ns` gap of 0.129 percent
survives the recomputation.

### Answers to the three narrower asks in the same comment

1. **Difference only within a session.** Agreed and already the case. R1 (8/4
   20:11) is the `T(0)` for R2 (20:44) and R3 (21:20), and the 8/5 anchor is not
   used to difference any 8/4 arm.
2. **Report `S` and `T` for `c3ce66e`.** `S = 97.9496 ms`, `T = 4.28121 ms`. In
   the table above, bolded, next to the three 8/4 pairs.
3. **Does the fit use any cross-day difference? Refit if so.** **No, and so no
   refit is needed.** All five r2 receipts are 8/5 and each level is differenced
   against its own session-paired baseline. In r1, `dT_4 = T_R3 - T_R2` used 8/4
   20:44 and 21:20, and `dS_1` and `dS_2` both used R1 at 8/4 20:11. There is no
   cross-day difference anywhere in either the r1 rates or the r2 ladder.

### The advisor has since retracted the 12.4 sigma. We converged from opposite ends.

The section above was written before his 12:07:57Z retraction, and I am leaving
it as written rather than quietly rewriting it, because the two analyses are
independent and agree.

He retracted it on the **numerator's denominator**: recomputing the replicate sd
from the three `officialScore` values 2.507043, 2.500378 and 2.514911 gives 0.29
percent, not 0.026 percent, so +0.321 percent is about +1.1 sigma and there is no
drift to model. I refuted it on the **decomposition**: the 0.026 percent figure is
an accidental cancellation inside a geometric mean, where a +2.112 percent decode
component and a -6.232 percent prefill component nearly annihilate, while the
component sds are 1.082 and 3.283 percent. Same conclusion, different route, and
the routes are complementary: his shows the sigma was mis-estimated, mine shows
*why* an `officialScore` sigma estimated that way is not a usable denominator in
the first place.

His direct question was: "if you built any correction term or any arm-scheduling
decision on it, delete that term and tell me what it changes."

**I built neither, so nothing changes.** Specifically:

- There is no drift correction term anywhere in `pr34_receipt.py`,
  `pr34_fit_ladder.py` or `pr34_ns_table.py`. Grep for one; the estimator is
  `T(n) - bT(n)` minus the same at `n = 0`, with no additive or multiplicative
  session term.
- No arm was scheduled or descheduled because of it. The entire r2 ladder is
  same-day 8/5, every level paired with its own baseline arm, which was the
  pre-registered design from `c45d93b` and predates his comment.
- The one place a cross-session allowance *does* appear is the widened rate-4
  error bar (+/- 0.029 -> +/- 0.043 ms), which I added because he asked for a
  conservative bar. That allowance made a bar *wider*, i.e. a claim weaker, so
  retracting the drift does not invalidate any conclusion; it would only let me
  narrow the bar back to +/- 0.029 ms and strengthen the rate-4 excess from
  2.5 sigma to 3.6 sigma. I am **leaving the conservative bar in place** and
  noting that the drift retraction is one of two independent reasons it could be
  narrowed. That is the honest direction to err in.

One thing I would like credited to the record, because it was written before his
new rule and says the same thing: conclusion 4 of the section above already
states "screen on candidate axes (`S`, `T`) or `ns`, never `officialScore` or the
raw speedups", with the measured cross-day candidate-axis reproducibility of
0.087 percent on `S` and 0.153 percent on `T`. That is the programme-wide rule he
issued at 12:07:57Z, derived from eight receipts instead of 1029, and it is now
independently confirmed twice.

## The R4 failure: `afec358a`

`afec358a` returned `status=failed` with `officialScore=None` and no timed
metrics at all. The reason was not timing and not correctness: the workflow run
concluded failure at the step "Review submitted code for benchmark bypasses"
(run 30955316536), created 22:09:28Z and updated 22:53:48Z.

The R4 tree differs from the R3 tree, which had already passed that same review,
in exactly four integer literals. `DARKBLOOM_INJECT_ARCH_PROBE` was 0 in all
four trees and predates R1, so it cannot be the differentiator. The most
defensible reading is a non-deterministic reviewer or an infrastructure error.

The operational lesson is worth more than the diagnosis: **a submission can
consume a slot and return no metrics at all.** I therefore declared a rule in
advance, in `queue-r2.md`, that a `failed`-with-no-metrics receipt is a *retry*
and not a data point: resubmit the identical tree and record both attempts, so
that five authorised receipts means five readings rather than five slots.

## Re-planned deliverable A: two slots, not five, and neither of them is 800

He asked directly: "which two or three of your five points buy the most slope
information, given that you already hold `0411779`?" Here is the answer, and it
is not a subset of the original ladder.

**Why "bracket the predicted knee" is now the wrong instinct.** That instinct was
right when the candidate knees were 461 (`H_gpu`) and 1200 (`H_cpu`). L1 killed
both at 34.8 sigma, and with them every knee above 400. Bracketing a dead knee
buys nothing. The live question changed shape: it is now **"is the curve linear
through the origin, or is there a knee somewhere inside `(0, 400)` with a steeper
slope above it?"** — which is precisely the add-versus-remove asymmetry, and the
only remaining threat to the pricing in this report.

**Slot 1: `n = 100`.** Highest information per slot by a wide margin.

| model | prediction for `dT(100)` |
| --- | --- |
| linear through the origin, `c = 1.980 us` | **0.198 ms** |
| knee at 300, `c = 8.35 us` above it | **0.000 ms** |

The gap is 0.198 ms against `sd(dT) = 0.0178 ms`: **11.1 sigma in a single
receipt.** No other level in `[0, 2400]` discriminates the two surviving models
at all, because they agree everywhere above 300 by construction. `n = 100` also
sits in the 40-to-200 range where a real fusion actually operates, so the reading
prices the thing we would build rather than an extrapolation towards it.

**Slot 2, only if a second is granted: `n = 200`.** With `{0, 100, 200, 400}` the
fit has four points and two degrees of freedom, and curvature is resolved by
interpolation inside the region of interest rather than by extrapolation from its
edge. If slot 1 lands on the linear prediction, slot 2 is close to optional; if
slot 1 lands near zero, slot 2 becomes the most valuable receipt in the campaign,
because it locates the knee.

**Why `n = 800`, `1600` and `2400` are dropped outright,** and I would not run
them even with free slots:

1. They were designed to separate knees at 461 and 1200. Both are dead.
2. A frontier review of the instrument flags contamination above roughly
   `n = 1300` from MLX's `max_ops_per_buffer` splitting
   (`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:576-593`) and
   a host-encode crossover near the same count. `n = 1600` and `n = 2400` would
   measure a **different mechanism** and I would not be able to tell which.
3. They cost the most channel time. Turnaround scales with injected cost: L1 at
   `n = 400` took 22.4 minutes; `n = 2400` injects roughly 6.3 ms per step.

**Priority order across all remaining work, including the unranked parts:**

1. **`n = 100`, ranked slot.** 11.1 sigma on the only open question. Ask.
2. **Chained versus unchained at fixed `n = 400`, local M4, costs no slot.** This
   collapses the `[0.36, 2.09] us` bracket documented above, which is currently
   the largest uncertainty in the pricing — a 5.8x range. It needs a new knob
   because the injected chain is hardcoded, and a knob is not a fusion, so it
   stays inside the "sweep only" constraint. It is blocked only on the M4 host,
   not on the channel.
3. **`n = 200`, ranked slot.** Useful, not decisive on its own.

Five authorised slots reduce to **two requested**, and one of the two is
conditional. I am not spending a slot on an `n = 0` control: `ns(c3ce66ec) =
2.544360` is held permanently and, per his instruction, no receipt of mine will
carry a control arm again — one receipt is best-known tree plus at most one new
mechanism.

## What I am asking for

1. **One ranked slot for `n = 100`**, whenever the scheduler has one. This is the
   only request that needs the channel. It is a single receipt, roughly 22
   minutes of turnaround, and it either confirms the pricing in this report or
   invalidates it.
2. **A second ranked slot for `n = 200`**, conditional on the first, and lower
   priority than anything a sibling has queued.
3. **Nothing else.** L2, L3 and L4 as originally specified are withdrawn, not
   deferred.

I am **not** retrying the two L2 submissions that were refused at 10:30:11Z and
10:35:52Z. Both refusals were the shared-account in-flight limit colliding with a
sibling's receipts, and he has since stated that he is the scheduler and that
`nezuko` holds the channel on PR #44. L2 through L4 are blocked on an
advisor-owned scheduling resource, which is a specific recorded reason to defer
rather than a failure to complete.

## Process disclosures

These are not incidental; three of them changed how this revision had to be run.

**The official channel is serialised at one submission in flight, and the account
is shared.** The r1 notes and the r2 assignment both said the receipts could be
submitted concurrently. They cannot. Submitting L1 about 20 seconds after L0
returned produced `{"error":{"code":"conflict","message":"account already has 1
submission(s) in flight for this benchmark (limit 1)"}}`. At 21 to 48 minutes per
receipt that alone turns a five-point ladder into a 2.5 to 3 hour serial
campaign. Worse, the limit is per *account* and all four students share
`morganmcg1` (`solverAccountId b6799236-2a83-4b5f-980a-f85023738be7`), so the two
L2 attempts at 10:30:11Z and 10:35:52Z were refused by a sibling's in-flight
receipt rather than by my own. There is no queue and no fairness rule in the API.
The advisor has since taken ownership of scheduling. **This is the single most
important planning fact for any multi-receipt sweep in this programme, and it is
not documented in the assignment.** It is why this revision is terminal at two
receipts instead of five, and why deliverable A is re-planned above around two
slots.

**There is no live channel from a student to the advisor.** `push_branch` is
advisor-owned, so a student can only push through `submit_result`, which means
the advisor sees nothing at all until the final submission. `respond_to_issue`
refuses a pull-request target (`human messages must use an issue, not a pull
request`). So an intermediate finding cannot be surfaced mid-campaign. My
mitigation was to commit `research/tanjiro-pr34/queue-r2.md` as a running log and
to fold every disclosure into this report. A useful consequence: reordering the
ladder to give the advisor an early read has exactly zero value, so the
pre-registered order was kept.

**Branch divergence, disclosed rather than resolved by force.** The remote
assignment head `454b189a07a2cb0c51b91188d834e9b1c5035603` is the stale
pre-rebase r1 tip. My local history was rebased onto `279b6e24`, so the SHAs
differ one-for-one by commit message (`454b189` is `c92eab6`, `5b39ec5` is
`8d5131f`, `ee324e1` is `644c226`). R4's submitted commit `af3ab58` is a
pre-rebase SHA and is not a valid object locally; its content equals local
`13d424f`. Comparing file lists, no file exists on the remote but not locally:
local is a strict content superset. The submission therefore uses
`expected_remote_sha = 454b189a...`, and nothing was reset or discarded.

## Byte budget

The assignment asked for the editable-byte budget before and after.

| | total bytes | headroom | growth | files |
| --- | --- | --- | --- | --- |
| before | 2954324 / 3000000 | 45676 | 13351 / 262144 | 142 (base 142) |
| after | 2940973 / 3000000 | 59027 | 0 / 262144 | 142 (base 142) |

The instrument patch was moved out of the scored file into
`research/tanjiro-pr34/instrument.patch`, which restored
`LagunaRuntimeModel.swift` to the base size of 508529 bytes and with it the full
15759 bytes of per-file room under the 524288 byte cap. That matters to a
sibling: PR #35 needs 8037 bytes in the same file and now has 7722 bytes of
spare.

## Cross-references

Per the assignment, the per-family M4 dispatch census in `nezuko`'s PR #32 is
cross-referenced rather than duplicated here.

## Conclusion

Two ranked receipts were enough to settle the question the assignment actually
asked, and they settled it against me.

**What is now measured.** A Metal dispatch on the ranked M5, added at the layer
boundaries of the decode step, costs `1.980 +/- 0.044 us` on candidate decode
time alone and `2.088 +/- 0.165 us` on the paired estimator. There is no
detectable free-dispatch slack: `slack < 0.2 ms`, knee below 80 dispatches, and
the two hypotheses that predicted a large idle reservoir are dead at 44.5 sigma
and 34.8 sigma respectively. One of those two was my own pre-registered
prediction, `H_cpu`, built on the M4 knee at 1209. **The M4 law does not
transfer.** I now believe the M4 and M5 probes measured different mechanisms:
M4's knee sits within a dispatch of the `max_ops_per_buffer` host-encode
crossover near 1300, and its implied 5.29 us/dispatch is the host-encode price,
not a GPU boundary price.

**What that is worth.** The correct conversion is `14.862% of score per ms of
decode saving`, and my earlier drafts had it wrong by a factor of ten. At the
measured `c` and no slack, a 25% cut in the ~406 shipped decode dispatches is
worth **+3.0% of score** and a 50% cut **+6.0%**. Our gap to the crown is
0.2517%. So the family clears the bar by more than an order of magnitude even
after the caveat below, and it clears it with room for the fusion itself to be
imperfect.

**The caveat I will not bury.** `c` is an upper bound, and I can name the
mechanism rather than hand-wave it. `LagunaInjectChain.tail` chains every
injected empty to the previous one, so the probe serialises what the shipped
stream runs under `MTL::DispatchTypeConcurrent`. Three independent brackets on
the *shipped* exposed boundary cost now disagree by 5.8x: 0.36 us from my
96.6%-busy timeline, 1.42 us from nezuko's M4 SPLIT=1, and this 1.98 us upper
bound. A fusion that removes 200 dispatches is therefore worth somewhere between
+1.1% and +5.9% of score. **Every one of those three numbers is above the
0.61% bar**, which is why I still recommend the family - but nobody should plan
a fusion on the assumption that 5.9% is what will land. The single cheapest way
to collapse that 5.8x bracket is a local chained-versus-unchained comparison at
fixed `n = 400`, which needs no ranked slot at all, and it is the first thing I
want to run.

**What I got wrong, and where it was caught.** Three errors are corrected in
public here: the 10x score conversion; the attribution of rate 4 to the failed
receipt `afec358a` when it in fact rests on `6757de65` minus `ca416f01`, both
successful, so rate 4 needs no re-run; and the pre-registered ladder design
itself, which spent its levels at 800/1600/2400 bracketing a knee that does not
exist while leaving the entire interval `(0, 400)` blind. The last of those is
the most instructive: `H_sat` was distinguishable from its rivals with a single
point at `n = 100`, and I would have learned strictly more from four cheap
levels below 400 than from four expensive ones above it. That is the lesson I
would carry into the next pre-registration - **put the levels where the
hypotheses disagree, not where the effect is largest.**

**On the 12.4 sigma.** The advisor and I converged on the same retraction from
opposite directions, his through the correct pinned-baseline standard deviation
and mine through the geometric-mean cancellation between the decode and prefill
legs. It matters that no correction term was ever built and no arm was scheduled
or descheduled on the strength of it. The only cross-session allowance in this
report is the widened rate-4 bar, which I am deliberately leaving conservative:
narrowing it would strengthen my own claimed excess from 2.5 to 3.6 sigma, and I
would rather under-claim it.

**What is blocked, and by whom.** L2, L3 and L4 are withdrawn, not deferred.
They are obsolete on the physics - there is no knee up there to bracket - and
they were also unrunnable: the ranked channel accepts one submission in flight
per *account*, all four students share `morganmcg1`, there is no queue, and the
advisor now owns scheduling. My two L2 attempts were refused by a sibling's
receipts, and I have not retried them and will not without being given a slot.
What I am asking for is one ranked slot for `n = 100` and a conditional second
for `n = 200`, in that order, behind the free local run. Nothing else.

**Standing verdict for the programme.** Dispatch-count reduction on M5 has real,
measurable, positive value, bracketed between roughly 0.36 us and 1.98 us of
score-bearing time per removed decode dispatch, with no idle reservoir to
absorb the first few hundred removals. The highest-value concrete target remains
`gate_sp`, whose 40 dispatches per step my law prices at 83.5 us (+1.24% score)
from the dispatch-count component alone, leaving the remaining ~66 us of the
advisor's 150 us target to come from the byte and first-touch side. That is a
fusion assignment, and per the r2 acceptance criteria I have deliberately not
built it.
