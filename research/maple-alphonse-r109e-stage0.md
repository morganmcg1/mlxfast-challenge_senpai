# R109-E Stage-0 post — maple-alphonse

Cut at 2026-08-10 22:42Z, against the 23:00Z Stage-0 gate in PR #685 comment
5246312084. I have no interim PR-comment tool, so this file *is* the post; it is
committed on `maple-alphonse/r109-full-attn-qk-mma` and will be quoted verbatim
in the typed terminal result.

Evidence: `research/maple-alphonse-r109e-qk-ceiling.md` (§4.6, §7),
`research/maple-alphonse-r109e-params-memo.md`,
`research/maple-alphonse-r109e-qk-ceiling-combined.txt` (raw analyser output),
`/tmp/r109e-qk-ceiling-main.tsv` + `/tmp/r109e-qk-swap.tsv` (n=32 raw rows).

## Headline

**`N-FULL-QK-CHEAP`.** The QK reduction in the full fused attention decode
kernel is **11.4%** of my 249.5 µs/step pool. The advisor's own slate says I need
a 27.2% harvest of that pool to clear the 0.378 %score bar. The mechanism is
structurally **2.4×** too small, so I am stopping R109-E before writing any MMA
kernel — and landing the params-atlas bolt-on as instructed.

The stronger statement is in **§7.1 of the ceiling memo**: a sourced static
instruction census plus the ruler prices *all* in-loop ALU in this kernel at
≈90.8 busy µs/step = 36.4% of the pool = **1.34× the bar**. Deleting every
arithmetic instruction in the hot loop — not just the reduction — would barely
clear it. That retires in-loop ALU micro-optimization for this kernel as a
class, and it points the residual 29–63% of the pool at something that is not
arithmetic. §7.1.4 names threadgroup quantization (the dispatch is exactly 24
threadgroups) as the leading unmeasured suspect and gives an 8-run test.

## Item 1 — reduce-vs-load, µs of M4 removed off the 249.5 µs pool

Combined n=32 (main block `CXDPPDXC`×3 plus mirrored confirmation block
`PXDCCDXP`). Busy µs = wall µs / 0.8, taken from the advisor's own pair
(0.0070 %score per M4 wall µs/step, 0.0056 per M4 busy µs/step).

| estimate | raw ns/step per issue slot | µs/step M4 **wall** | ×1.28 corrected | µs/step M4 **busy** | %score @ τ=1 | vs 54 µs bar |
|---|---|---|---|---|---|---|
| synthetic ladder ruler, point | **2268.6** (se 384.2) | **22.69** | **29.04** | 28.36 | 0.159 | **0.42×** |
| synthetic ladder ruler, 95% upper | 3021.9 | 30.22 | 38.68 | 37.78 | 0.212 | 0.56× |
| direct removal probe P−C, point saving | — | **+6.16** | 7.88 | 7.70 | 0.043 | 0.11× |
| direct removal probe P−C, 95% upper saving | — | **+56.27** | 72.03 | 70.34 | 0.394 | **1.04×** |

The ×1.28 correction is applied as instructed. Its derivation is in the omitted
middle of comment 5246312084; I have not independently checked it, and it
changes no sign and no verdict.

**As a share of the pool: 11.4%, ruler 95% upper 15.1%, against a 27.2%
requirement.**

Unit note, because I got this wrong in an earlier draft: the 249.5 µs/step pool
the advisor handed me is in **busy** units (68/249.5 = 27.2% reproduces the
slate's harvest exactly, 54/249.5 = 21.6% does not). So the pool share must be
computed from the **busy** column, 28.36/249.5 = 11.4%, not from the wall column,
22.69/249.5 = 9.1%. The verdict is unchanged; the shortfall is 2.4×, not 3×.

Two instruments, deliberately independent:

- **Ruler** — arms D (ladder + 1 synthetic issue slot) and X (+10) add
  `simd_shuffle_xor` slots to the same kernel and price one slot by regression.
  Marginal 2268.6 ns/step per slot; fixed step cost +37.6 µs/step with
  se 30.0, i.e. indistinguishable from zero, so the curve is linear and the
  ruler is usable. Ten ladder slots ⇒ 22.69 µs/step.
- **Direct probe** — arm P replaces the reduction with `simd_broadcast_first`,
  keeping the dispatch, the operand loads and the control flow, and deleting
  only the reduction arithmetic. It fails the token check *by construction* and
  that is the design; the decode loop is teacher-forced
  (`LagunaRuntimeLocalIterate.swift:613`, `:622-628` records `failureStep` and
  does not `break`), so every arm does identical work and P's timing is valid.

**I withdraw one claim from my previous draft.** I had written that both
estimators exclude a bar-clearing saving at 95%. The confirmation block does not
support that. Only the ruler excludes it (95% upper 30.22 wall / 38.68
corrected, both below 54). The direct probe's 95% upper is +56.27, which sits
just *above* the bar; it is simply too noisy to resolve a 54 µs/step effect at
n=32 with sd ≈ 50 µs/step per run. Resolving it would take ~110 runs ≈ 5.5 h of
box time and I do not recommend spending it: the ruler answers the same question
with ≈7× the power, and the §6 design analysis independently projects the MMA
rewrite as a **regression** (best mapping 32 slots/key vs 28 today, ≈+5% worse;
filling an 8-row `simdgroup_bfloat8x8` tile needs ≥6 query rows, which requires
the grid change I was explicitly not signed off for; break-even needs M5 MMA
≥1.5× scalar FMA, publicly unverified).

## Item 2 — params-atlas bolt-on, priced separately

**Landed**, commit `2e9cd4f5`, `Sources/MLXFastModel/LagunaRuntimeModel.swift`.
42 added / 3 removed lines: a static memo store, two `ProcessInfo` gates, and
`lagunaFullFusedAttentionParams(writeIdx:capacity:)`. Release build clean.

The full-attention params array is rebuilt on every one of the 10 full-attention
layer calls per decode step, always with the same `(writeIdx, capacity)`. The
memo hits 9/10 ⇒ **9 host allocations removed per step, ~1152 over the 128-step
window.** Bit-exact: same three `UInt32`s, same kernel input, so
`passed_correctness` must stay `true` in every arm.

**The separate µs number is in flight** — 16-run four-arm dose experiment
(job `2db82418-f16f-48c6-905a-34eec2654e95`, order `OABMMBAOMBAOOABM`, ~50 min,
launched 22:40Z). Arms: M memo on (1 alloc/step), O shipped (10), A (110),
B (1010). The A–B contrast prices one host construction with 100× the signal;
9× that price is the memo's ceiling. All four arms are bit-exact.

**Pricing, stated now so the measurement cannot be read into the wrong family.**
Host encode is the **τ ≈ 1%** class in the advisor's own taxonomy. Even a
generous 20 µs/step M4 measurement prices at
`0.0070 × 20 × 0.01 = 0.0014 %score`, about **1/270th of the bar**. Under the
dispatch-family constant 0.00203 it is 0.041 %score, still 1/9th of the bar.
So: **land it — it is free, bit-exact and ~30 lines — but do not book it against
the 0.378% bar, and do not add it to item 1.** Different τ classes are not
commensurable and summing them would be the exact error §5 of the ceiling memo
was written to stop.

I also note, without needing it: nezuko's two pre-registrations for this same
mechanism ("10–30 ns per construction" and "11 µs/step") are mutually
inconsistent by ~50× — 9 × 30 ns is 0.27 µs/step, not 11.

## Item 3 — confirmation that the grid is unchanged

Proven, not asserted:

```
git diff 1a6761bf -- Sources Vendor benchmark.json Package.swift \
  | grep -c '^[+-].*\(grid:\|threadGroup:\|outputShapes\|outputDTypes\)'
0
```

The full-attention dispatch is still `grid ((heads/2)*1024, 1, 1)`,
`threadGroup (1024, 1, 1)` — 24 threadgroups × 1024 threads, one per head pair.
Every probe arm rewrites **in-kernel statements only**; all four arms share one
dispatch shape, one output shape and one output dtype.

## Item 4 — non-empty submitted-surface diff

```
git diff --numstat 1a6761bf -- Sources Vendor benchmark.json Package.swift
147  16  Sources/MLXFastModel/LagunaRuntimeModel.swift
```

**Deviation from the brief, stated plainly:** the brief asked for the bulk in a
new `Sources/MLXFastModel/LagunaFullAttnQKMMA.swift` with only registration and
dispatch selection in LRM. I did not create that file, because the verdict is
`N-FULL-QK-CHEAP` and **no MMA kernel is being written** — the file would be an
empty shell added only to satisfy a shape check. The LRM delta is the probe
instrument (three probe-source rewriters, a dose-kernel generator, a selector)
plus the params memo. Everything except the params memo is inert when its
environment variables are unset, and the params memo is bit-exact.

## Instrument finding the programme should act on regardless of my verdict

The first run of a block on this host is slower than the rest. With the mirrored
block it is identified at **+53.59 µs/step, se 29.88, 95% CI [−4.98, +112.16]**
— one whole decision bar at the point estimate. It is *not* significant at
n=32 and I say so; the argument does not need significance. A nuisance term
whose plausible range is [0, +112] µs/step must not sit **aliased onto the
control**, because then it is indistinguishable from a candidate win.

Six drivers in this tree always put the control in slot 1, so their historical
deltas are biased toward **manufacturing local wins**:
`research/maple_r85c_epilogue_ab.sh`, `maple_r88a_two_regime_ab.sh`,
`maple_r91a_input_norm_ab.sh`, `maple-nezuko-r106b-h4-paired.sh`,
`nezuko_epilogue_abba.sh`, `tanjiro-r100b-census.sh`.
`maple-nezuko-r106b-packred-paired.sh` and `maple_r85_placement_arms.sh`
already rotate and are fine. Fix: mirror the arm order across blocks, or drop
slot 1. One extra block, and it is the cheapest fix available.

Also, for the record: `FERN_DEFEAT_SLOTS` does **not** exist on the
`benchmark.sh` path. It appears only in `research/fern_r99_qmv_probe.swift`.
Any campaign note that treats it as a live knob on the scored path is wrong.

And one candidate mechanism is ruled out for free by the §7.1 census: **K and V
reach this kernel as raw `bfloat16`** (`LagunaRuntimeModel.swift:2569`,
`:2369-2371`, `:2387-2389`). There is no in-kernel dequantization in the full
fused attention path, so "remove the dequant from the KV read" is not an
available saving here. Anyone scoping that should stop before building it.

## What I recommend instead of Stage 1 on this mechanism

**Occupancy, not arithmetic.** This kernel launches 24 threadgroups, one per
head pair. That is already above the 20 GPU cores of this M4 Pro and far below
an M5 Max, so on the ranked machine most of the GPU is idle for the whole
duration of the kernel. A split-K or head-splitting launch is a much larger
lever than anything inside the inner loop, and it is measurable *before* it is
implemented: one M5 GPU-counter capture on a single decode step settles it. It
needs the grid carve-out I was not granted, which is exactly why it should be an
advisor decision rather than a student one.

The size argument, from §7.1.4 and stated as a prior rather than a measurement:
24 threadgroups are indivisible, so on 20 cores the makespan is 2 scheduling
units where the ideal is 1.2 — **60% efficiency, 40% wasted ≈ 100 busy µs/step
≈ 1.47× the bar**, from one launch-shape change and no arithmetic at all. On an
M5 Max the same quantization caps utilization at `min(24, cores)/cores`. That
single hypothesis is larger than the entire in-loop ALU budget (1.34× bar) that
R109-E was scoped to attack, and it is the only thing I found that is both big
enough and untested.

Cheapest decisive test, which needs no new kernel: dispatch `2 × (heads/2)`
threadgroups of 512 threads with the key range split per head pair, then one
ABBA block of 8 runs (~25 min) on the existing harness. If the launch-shape
change alone moves decode by ≳100 µs/step, the residual is occupancy and the
programme should spend Stage 1 there.
