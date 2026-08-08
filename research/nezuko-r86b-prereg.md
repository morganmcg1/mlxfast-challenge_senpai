# R86-B pre-registration — in-situ price of a DRAM round-trip boundary

- PR: #462 · assignment `maple-r86-b-insitu-boundary-price` · revision `r86-b-rev1`
- BASE_SHA: `7687c2e44e6975c181444ca8d3d151ee30480a72`
- Branch: `maple-nezuko/r86-insitu-boundary-price`
- Author: `maple-nezuko`
- **Committed before the first timing run.** Every number below is a prediction
  written with no R86-B measurement in hand.

Local host (all local numbers are M4, ranked hardware is M5 Max):
Apple M4 Pro, 48 GiB unified memory, macOS 26.5.2 (25F84), Apple GPU
generation 16. `_nax` prefill kernels are **unreachable** here; the decode path
under instrumentation **is** reachable.

Editable budget at base (recorded once, as required; nothing here is submitted):
`current=2891343/3000000 bytes headroom=108657 growth=0/262144 files=140
(base=140)`.

---

## 0. Facts I am correcting in the brief before I measure

- The brief says 32 decoder layers, so `insertsPerLayer ∈ {0,2,4,8,16}` gives
  `k ∈ {0,64,128,256,512}`. **Laguna has 40 decoder layers.** The same ladder
  points therefore give **`k ∈ {0, 80, 160, 320, 640}`** inserted boundaries per
  decode step. I keep the advisor's `insertsPerLayer` rungs (they set the lever
  arm) and report `k` on the true layer count. The top rung's lever arm is
  25 % larger than the brief assumed, which only helps.
- The hook site line number moved on this base: the layer loop in
  `LagunaRuntimeModelInner.callAsFunction` is at
  `Sources/MLXFastModel/LagunaRuntimeModel.swift:11534`, not `:11438`.

## 1. Prior art this ladder is the fourth estimate of

Per the advisor's required reconciliation (`research/CURRENT_RESEARCH_STATE.md`):

| source | method | µs per dependent pair |
|---|---|---|
| #268 `:497-505` | joint fit, n=288, 36 blocks, df=250 | barrier 1.3003 ± 0.0597, dispatch 0.1231 ± 0.0481, **pair 1.4234 ± 0.0256** |
| #269 `:513-518` | **real removal**, −117 dispatches/step, block-paired ABBA, t=+12.54 | **+1.233**, 95 % CI [0.920, 1.545] |
| R85-D (mine, PR #458) | injected ladder, isolated | **1.4140 ± 0.0093**; WIDE−TINY difference 1.2425 |

Three methods, one interval. **#269 is already an in-situ real-removal
estimate**, which is why my prior on transfer is high rather than open. What is
genuinely new in R86-B is (a) calibration on the *frontier* base, which every
number above predates, and (b) the WIDE/TINY differencing that separates
`c_issue` from `c_drain` **in situ** for the first time.

I therefore treat the ladder as a short calibration and pre-commit the bulk of
the round to §3 (census) and §4 (decomposition), per the advisor's §5.

## 2. Point predictions with 80 % intervals (written blind)

Units: µs of decode step per **inserted boundary** (i.e. per unit of `k`, not
per unit of `insertsPerLayer`).

| quantity | point prediction | 80 % interval |
|---|---|---|
| `slope(WIDE-insitu)` | **1.36** | [1.10, 1.62] |
| `slope(TINY-insitu)` | **0.17** | [0.06, 0.34] |
| `d = slope(WIDE) − slope(TINY)` | **1.19** | [0.92, 1.46] |
| WIDE:TINY slope ratio | 8.0× | [4×, 20×] |
| step time at `k = 0`, WIDE mode | 8230 µs | [8100, 8400] |
| step time at `k = 640`, WIDE mode | 9100 µs (+10.6 %) | [8800, 9450] |

Rationale for shading WIDE slightly *below* R85-D's 1.4140: in situ the
injected round trip sits between real quantized GEMMs that are already holding
the memory system busy, so I expect a small amount of genuine latency hiding —
but only a small amount, because the injected op is **dependent** on the live
hidden row and MLX submits it in order, so its latency cannot be overlapped
with the very GEMM that consumes its output. I predict the hiding is worth
≤ 0.1 µs, not ≥ 1.0 µs.

Interval on TINY is wide because R85-D found TINY was **not** a clean line: it
carried a one-time ≈ +315 µs step plus a shallow slope (0.1716 ± 0.0617 raw,
0.0989 ± 0.0318 with the step removed). I expect the same shape in situ and I
pre-commit to reporting **both** the raw and step-removed TINY slope, and to
using the **raw** TINY slope for `d` (the conservative choice, since it makes
`d` smaller and a NO-GO easier to reach).

## 3. Prior on the two reconciliations of the 144× discrepancy

- **(A) Regime difference — the ladder transfers.** A 4 KiB dependent round
  trip is *latency*-bound; PR #110's 0.015224 %/MB was fit deep in the
  bandwidth-bound regime on 25–96 MB weight planes. Both can be true at once
  because they are two different terms of the same cost function.
- **(B) Latency-hiding — the ladder over-states in situ.**

**P(A) = 0.85, P(B) = 0.15.**

In words: I think (A) is right and that the discrepancy is not a contradiction
at all but a *missing fixed term* in PR #110's ledger — PR #110 fit
`cost = β·bytes` with no intercept, so it necessarily attributes zero cost to a
boundary that moves almost no bytes. The strongest single reason for 0.85 is
that #269 removed **real** dispatches from the **real** decode step and
recovered 1.233 µs per pair, i.e. the transfer question already has one direct
answer. The 0.15 left for (B) is for the possibility that #269's removed ops
were unrepresentatively exposed (they were elementwise ops on the residual
stream, not ops wedged between two heavy GEMMs).

I pre-register the mechanism that would distinguish them **within this arm**:
see the size sweep in §5.

## 4. Decision thresholds, restated in my own words

Let `d = slope(WIDE-insitu) − slope(TINY-insitu)`, in µs per inserted boundary,
with TINY taken raw (not step-removed).

| measured `d` | what I will write |
|---|---|
| `d ≥ 1.00 µs` | **GO.** The isolated-ladder price survives contact with the real decode step. Eliminating a real dependent boundary is worth ≥ 0.0153 % of score each, the round-trip-elimination family stays open, and the census in §6 is the queue. |
| `0.35 ≤ d < 1.00 µs` | **PARTIAL.** I reprice the 40/120/240-boundary projections at the measured `d` and state plainly what a realistic fusion campaign is worth. I write the census **only** if the repriced 40-boundary value is ≥ 0.5 % of score. |
| `d < 0.35 µs` | **NO-GO.** I close the round-trip-elimination family, write it as a doctrine line for `CURRENT_RESEARCH_STATE.md` §8 with the explicit ladder-vs-in-situ ratio, and stop. |

**I pre-commit not to soften a NO-GO.** If `d` lands under 0.35 I will not
re-fit, re-window, drop a rung, switch to the step-removed TINY slope, or
appeal to M4-vs-M5 to rescue it. If `d` lands in a band boundary's confidence
interval I will report the verdict of the point estimate and state the
ambiguity explicitly rather than choosing the more convenient side.

Symmetrically: a GO does **not** license a fusion assignment on its own. §4.18
already shows one real 39-barrier harvest that ranked **−0.1488 %**. A GO says
the *gross* refund exists; the census's **net** column says whether anyone can
collect it.

## 5. Out-of-sample cross-prediction (chosen to remain resolvable by this arm)

My R85-D cross-prediction became unresolvable when the bisect was retired. This
time I pick a prediction that **this arm's own instrument resolves**, plus one
that the arm's own ladder resolves.

### CP-1 (primary): the size sweep separates a fixed boundary term from a bandwidth term

I add a third arm the brief did not ask for, because it is the *direct*
measurement of the advisor's "is `d` size-dependent?" question and it costs
~20 minutes of GPU: the same dependent chain run over scratch widths
`W ∈ {2 B, 64 B, 4 KiB, 64 KiB, 512 KiB, 4 MiB}` at `insertsPerLayer ∈ {0, 2}`.

I pre-register the model `price(W) = c_fixed + 2W / BW_eff` and predict:

1. `price(W)` is **flat within ±0.25 µs across W = 2 B … 64 KiB**, i.e. the
   4 KiB round trip is **not** paying for its bytes.
2. `price(4 MiB) ≥ 25 µs`, and the large-`W` limb yields
   `BW_eff ∈ [150, 450] GB/s`.
3. Converting that large-`W` limb into PR #110's units gives a %/MB figure
   **within a factor of 3 of 0.015224 %/MB**.

If all three hold, (A) is confirmed as *the ledgers measure different terms*,
and PR #110's ledger is correct but intercept-free. If instead `price(W)` rises
smoothly from 2 B and extrapolates back through ≈ 0 at `W = 0`, then the 4 KiB
price really is a byte price, the two ledgers genuinely contradict, and (B)
gains a lot of weight. **Falsifier for (A): points 1 and 2 both fail.**

### CP-2 (secondary): in-situ `d` lands inside #269's real-removal interval

`d` will fall inside #269's 95 % CI **[0.920, 1.545]**. This is a real
out-of-sample test because #269 used a different method (removal, not
injection), a different site (elementwise residual-stream ops, not the layer
boundary), and a different base. If `d` lands outside that interval in either
direction, at least one of the two is site-specific and I will say so.

### CP-3 (census/decomposition, resolvable in §7/§8 of the result)

Written before reading either subagent report:

- Of the top-10 boundaries by gross refund, **at most 3** will be
  redundancy-free (`R = 1`). *P = 0.7.*
- The dominant term in the −0.1488 % decomposition will be **redundant
  recomputation** (`R > 1`) with *P = 0.50*; occupancy / register pressure /
  threadgroup-memory loss *P = 0.25*; "the barrier was never actually removed
  on the ranked M5 path" (e.g. an `_nax` variant that the fusion did not
  cover) *P = 0.15*; prediction error in C1a itself *P = 0.10*.
- The single largest intermediate in the decode step by bytes is in the MoE
  path, not the attention path. *P = 0.8.*

## 6. What I will produce if the verdict is GO or a qualifying PARTIAL

The census table with all seven mandated columns (producer → intermediate with
**actual** bytes → consumer; gross refund at measured `d` in µs and %score;
redundancy multiplier `R` read from the consumer's real grid/threadgroup
decomposition with a line number; redundancy cost = producer cost × (R − 1);
**net**; redundancy-free YES/NO; occupancy risk), ranked by **net**, top 10.

Plus the §4 arithmetic decomposition of the ~1.0 point gap between C1a's
predicted +0.85–0.9 % and the ranked −0.1488 %, as a paper exercise on the
preserved `maple-fern/fused-norm-qkv-gate` artifacts.

## 7. Instrument and validity gates (pre-committed)

Instrument: a new file `Sources/MLXFastModel/LagunaR86BoundaryLadder.swift`
plus a **one-line** hook at the top of the layer-loop body in
`LagunaRuntimeModelInner.callAsFunction`. Nothing inside
`LagunaRuntimeDecoderLayer` or the MLP/MoE range is touched (`maple-fern` owns
that range in PR #456). Guarded to single-token decode (`[1,1,2048]` bf16), so
prefill is bit-identical and untouched.

- **WIDE**: `h = h * one` chained `insertsPerLayer` times on the live hidden
  row. bf16 `[1,1,2048]` ⇒ 4096 B read + 4096 B written per inserted dispatch.
- **TINY**: the same chain on a `[1]` bf16 scratch, folded back into `h` with a
  single broadcast add that is present at **every** `k` including `k = 0`, so
  the fold's cost lands in the intercept and not the slope.
- **SIZE**: TINY's structure with the scratch width swept.

All injected ops are exact identities in bf16 (`x * 1`, `x + 0`), so every
checked token must be unchanged.

Gates I will pass before quoting any slope:

1. **Dispatch count rises by exactly `k`** at every rung, via
   `DARKBLOOM_PROBE_CB_OPS` — counts shown in the result.
2. **The inserted op is a real global-memory round trip**, not a
   threadgroup-local pass-through: separate MLX ops cannot share threadgroup
   memory, each writes a distinct device allocation, and I will state the
   evidence.
3. **Bit-exact**: the 64-step drift tripwire at the maximum `k` with
   `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` **unset**.
4. **`k = 0` equals pristine `7687c2e4`**, measured as a matched pair.
5. **Linearity** characterised; a knee is reported as a finding, not smoothed.

Timing through `./benchmark.sh --local-iterate`, paired/ABBA ordering as in
`research/pr80_ladder_abba.sh`, and every mean reported with `n`, its
dispersion, and the dispersion kind per rule R20.6.

If a gate cannot be passed, I stop and report the failed gate as the result. I
will not quote a slope from an instrument I could not validate.

## 8. Cost pre-commitment

Ladder + size sweep ≤ 60 minutes of GPU. Everything after that goes to §3 and
§4. I will not spend a second ladder replicate to move a fifth decimal place on
a constant that three prior estimates already bracket.
