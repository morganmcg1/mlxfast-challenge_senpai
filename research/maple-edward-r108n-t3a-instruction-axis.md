# R108-N — T3a instruction-axis census: `N-T3A-NO-ISSUE-SLACK`

Student: maple-edward. PR #629, assignment `maple-r107-a-routed-gateup-packing`,
revision `r108-n-rev1`. Base epoch `705484b9e120d60a973d660fdbdd1ccc7cdfa124`.
Host for every number below: the single M4 Pro research Mac (Apple GPU
architecture generation 16, no `_nax` kernels). All probe numbers are taken with
`FERN_DEFEAT_SLOTS=64` per rule 98.9; a residency-held number would be ~30x
inflated and is not reported.

## Verdict

**`N-T3A-NO-ISSUE-SLACK` — stop at the Stage-1 gate.** This is the falsifier
firing, which the assignment defines as a successful outcome.

The gate was: removable instruction work below 15 % of T3a issue means stop.

| denominator | removable | gate | verdict |
| --- | --- | --- | --- |
| static census, every named candidate believed (classes 1-3) | **11.3 %** | 15 % | below |
| measured issue budget, same candidates | **7.9 %** | 15 % | below |
| **directly measured, paired probe, best arm** | **0.33 %** | 15 % | far below |

The directly measured number is the one to act on, and it is 45x below the gate.
Two of the three candidates measure *slower* than the base, and the third is a
deliberately-incorrect upper bound.

Worth of the best measured removal, both pricing routes:

| route | value |
| --- | --- |
| `k_issue = 0.267` (conservative, headline) | **+0.0073 % of cs** |
| `k_issue = 0.654` (optimistic end of the R107-G bracket) | +0.0179 % of cs |
| rule-100 direct instrument (0.002097 %/fma, implies k = 0.537) | +0.0147 % of cs |
| bar | 0.4 % of cs |

The best arm is **25x to 55x short of the bar** on every route, and it lands
*inside* rule 92's cap on pure scheduling/barrier gains (0.0198 %), which it
independently corroborates rather than escaping.

## Contract statements

- `git diff --numstat 705484b9 HEAD -- Sources Vendor benchmark.json Package.swift senpai`
  is **empty**. Stage 1 changed no submitted file. Every variant in this report
  is a scratch copy under `/tmp` consumed by a research probe binary.
- The branch reached this base by **merge, not rebase** (rule 97.0), commit
  `1e4494a7`.
- **Zero official receipts** were spent. No `--local-submit`, no `mlxfast submit`.
- No correctness claim in this report cites harness `max_abs_diff` or
  `golden_hash` (rule 105.15). The arms are timing probes; the correctness class
  of each mechanism is argued at source level below and none of them was
  promoted.
- Byte budget was not touched: no submitted file changed, so
  `senpai/check-editable-budget.sh` headroom is unchanged from the base
  (318,794 B total, `LagunaRuntimeModel.swift` 384,245 B of the 524,288 B cap).

## Instrument, and one correction to the pricing anchor

The census needs a price per issue slot. R107-D (#642) anchored 0.008297 µs per
fp32-fma-per-thread per sliding dispatch from a single dose point. A single dose
point cannot tell a real slot cost from a constant-folded chain, so I ran a
ladder and three extra instruction classes through
`research/maple-edward-r108n-class-dose-gen.sh` (a generalisation of tanjiro's
R107-D dose generator from one class to four).

fma ladder, 41 paired rounds each, M4, residency defeated:

| extra fma/thread/dispatch | paired `d_mean` µs | `t` |
| --- | --- | --- |
| 128 | +1.395 | +42.4 |
| 512 | +4.259 | +156.4 |
| 1024 | +9.061 | +131.0 |

Marginal slope over 128..1024 = **0.008556 µs per slot per thread per dispatch**,
with a +0.30 µs intercept that is the dose scaffold (eight register seeds and the
`1e-30` fold-back), not per-op cost. **R107-D's anchor is validated** — it sits
3 % below this slope. Rule 100's 0.002097 %/fma corresponds to `k_issue = 0.537`
on this slope, i.e. near the optimistic end of the R107-G bracket, so this report
headlines the conservative `k_issue = 0.267` and shows rule 100 alongside.

Two classes could not be priced or were priced as upper bounds:

| class | dose | measured | reading |
| --- | --- | --- | --- |
| `mul` (`dz *= 1.0000001`) | 128 | +0.233 µs | **invalid** |
| `mul` | 512 | +0.303 µs | 4x the dose, 1.3x the cost: fast math folds the constant-multiply chain to a single multiply, so this arm never priced a slot |
| `simd_sum` | 128 | +11.007 µs | 0.0774 µs each = **9.05 fma slots**; confirms the census's cross-lane reduce expansion (I lowered `SIMD_REDUCE` from 10 to the measured 9) |
| `simd_shuffle_xor` | 128 | +2.998 µs | 0.0234 µs = 2.74 fma slots; five of these would cost more than one `simd_sum`, so `simd_sum` lowers to a cheaper dedicated reduce |

`simd_sum` and `simd_shuffle_xor` doses have only eight independent chains, so
both are upper bounds that may include latency, not pure issue.

Measured issue budget at the null arm's base: 18.39 µs / 0.008556 =
**2,149 slots per thread per dispatch**. Shipped T3a is 20.63 µs/dispatch
(618.9 M4 µs/step over 30 sliding dispatches, rule 100.3 corrected value), so the
probe reproduces **89 %** of the shipped per-dispatch cost. Memory regime across
arms: `UNSATURATED`/`PARTIAL`, 33-41 % of the 266.3 GB/s measured peak,
amplification 12.7 — consistent with R107-D's `N-ISSUE-BOUND` finding.

## Static census

`laguna_sliding_fused_attn_ring_v1`, `Sources/MLXFastModel/LagunaRuntimeModel.swift:1515-1871`
at base `705484b9`; grid `((heads/2)*1024,1,1)`, threadgroup 1024 = 32
simdgroups, `head_dim=128`, `window=512`, `gqa=8`, `BN=BD=32`, 4 loop iterations
x 4 unrolled row stages = 16 rows per thread. Full auditable table:
`research/maple-edward-r108n-census.py`.

| class | slots/thread | % of census |
| --- | --- | --- |
| main: `simd_sum` over 32 lanes (QK) | 288 | 19.3 % |
| main: bf16->f32 converts | 128 | 8.6 % |
| main: QK fma | 128 | 8.6 % |
| main: accumulator rescale mul | 128 | 8.6 % |
| main: accumulator fma | 128 | 8.6 % |
| main: rescale predicate | 96 | 6.4 % |
| main: score exp | 96 | 6.4 % |
| epilogue: output `simd_sum` | 72 | 4.8 % |
| main: rescale exp | 64 | 4.3 % |
| main: ring-substitution predicate + branch | 60 | 4.0 % |
| epilogue: normalise divide + select | 48 | 3.2 % |
| main: pointer arithmetic + loop control | 44 | 2.9 % |
| prologue | 44 | 2.9 % |
| everything else (loads, max, denominator fma, `simd_max`, transposes, stores) | 171 | 11.4 % |
| **total** | **1,495** | 100 % |

Coverage of the measured 2,149-slot budget: **69.6 %**. The missing 30 % is
barrier waits, launch/teardown, the Phase-A critical path on `sg<3`, threadgroup
bank conflicts, and load-return stalls — none of it removable by editing
arithmetic.

The structural point the census makes before any measurement: **74 % of the
census is reduction, fma, convert and transcendental work the algorithm
requires.** The classic hoist-and-strength-reduce surface — ring predicate 60 +
loop control 44 + prologue 44 = 148 slots — is only **9.9 % of the census and
6.9 % of the measured budget**, i.e. below the gate on its own even if every slot
of it vanished for free. The `main: rescale predicate` block (96 slots) is
already an optimisation in the base: it skips the rescale `exp` whenever the
running max is unchanged.

## Directly measured arms

Three candidate removals, each generated by
`research/maple-edward-r108n-variant-gen.py` and measured paired against the
unmodified base by `research/maple-edward-r108n-variant-run.sh` (121 alternating
rounds of 200 dispatches, M4, residency defeated). `NULL` is a verbatim copy
through the same path and bounds instrument bias.

| arm | `d_mean` µs/dispatch | 95 % CI | bias-corrected | slots | cs+ (k=0.267) |
| --- | --- | --- | --- | --- | --- |
| NULL (verbatim copy) | −0.040 | [−0.075, −0.005] | — | — | bias floor |
| m1 factor==1 accumulator fast path | **+0.358** | [+0.297, +0.419] | +0.398 | +46.5 | **−0.0485 %** |
| m2 ring predicate forced off | **−0.100** | [−0.156, −0.044] | −0.060 | −7.0 | **+0.0073 %** |
| m3 epilogue reciprocal | +0.007 | [−0.026, +0.040] | +0.047 | +5.5 | −0.0057 % |
| m1+m2+m3 | +0.158 | [+0.098, +0.218] | +0.198 | +23.1 | −0.0242 % |

A 41-round run of the same suite gave m1 +0.390, m2 −0.167, m3 −0.063, combo
+0.069: m1's sign reproduces strongly, m2 is small and drifts between runs, m3
sits on the bias floor in both. Per-arm `base_min` ranged 16.4-18.7 µs across
arms in one session, which is exactly why only paired deltas are quoted.

### Why each candidate failed

**m1 — `factor == 1.0` fast path on the accumulator (the largest static item,
96 slots).** `LAGUNA_RESCALE` returns exactly `1.0` via an `as_type<uint>(delta)
== 0` shortcut, so in decode the accumulator is multiplied by exactly 1.0 for
most of the 16 rows, and the static count says one multiply per (dim, head, row)
is dead. It is not. The base statement `o = o*f + e*v` already lowers to one
multiply (`e*v`) plus one fma; the fast path `o = o + e*v` still needs the
multiply and then an add — **the same two slots**. The variant therefore removes
nothing and adds two uniform compares, two branches, and a doubled accumulator
block per stage (kernel source grows 356 -> 420 lines). Measured cost +0.398 µs.
This also settles the correctness question that would otherwise have needed
frieren's margin certificate: there is no reason to spend one.

**m3 — one reciprocal instead of four divides per head in the epilogue (24
slots).** Eight divides share two denominators, so the static count assumes eight
divide expansions. Measured effect is +0.047 µs, i.e. the bias floor: the
compiler already shares the reciprocal across the four divides per head, and
`DIV = 5` overstates what is actually issued. No gain to buy, and no reason to
pay for the reassociation certificate this arm would need.

**m2 — ring-substitution predicate (60 slots).** This arm forces the `substitute`
argument of `T_LOAD_K`/`T_LOAD_V` to `false`, deleting four compares per
iteration and the whole threadgroup path. That is **not correct** — it drops the
substitution the ring buffer needs, because only one of the four threadgroups
sharing a kv head writes the newest row (`head0 % gqa == 0 && sg == 0`), so the
other three must read it from threadgroup memory. It is measured only as an upper
bound on a correct peel, which would still need a post-loop fix-up for the single
`widx` row. Even as that upper bound it buys **0.060 µs/dispatch bias-corrected =
0.33 % of T3a issue = +0.0073 % of cs**.

### The calibration lesson

m2's static count predicts 40 removable slots = 0.34 µs/dispatch. It measures
0.060 µs — **a 5.7x over-prediction**. The dose instrument adds work that is
dependent on live registers and folds into the score, so it lands on the critical
path and prices at full slot cost. Removing existing work only pays when that
work is *itself* on the critical path; uniform predicates and loop overhead hide
under load-return latency. **Any future "slots removed x 0.008556 µs" estimate for
predicate, addressing or scheduling work should be treated as an optimistic upper
bound by roughly 5x.** That is the same conclusion rule 92 reached from a
different direction, and m2's +0.0073..0.0179 % sits inside rule 92's 0.0198 %
scheduling cap.

## What would clear 15 %, and why it is out of charge

Only one item in the census is large enough: the QK cross-lane reduction. The
current layout puts one head dimension per lane, so every row costs two
`simd_sum`s over 32 lanes — 288 slots, 19.3 % of the census, plus the 128 QK fma
slots and the 72 epilogue reduce slots. Re-expressing that as a simdgroup MMA
would remove ~275 net slots (18.4 % static, 12.8 % of the measured budget,
+0.287..0.703 % of cs) and is the only route in the census that reaches the bar.

It is not an instruction trim: it is a different kernel family, it is not
bit-exact (different accumulation order over 32 lanes), it needs a margin
certificate, and both the M4's absent `_nax` selection and its different core
count make M4 evidence weak for it. R108-N's charge is the instruction axis, so I
am reporting it as the only surviving direction rather than starting it.

Slots needed for the 0.4 % bar, for calibration: **383** at `k=0.267`, 156 at
`k=0.654`, 191 by rule 100 — against a best measured removal of **7.0 slots**.

## Reproduction

```bash
# instrument: fma ladder + class prices (~6 s each, no scored file touched)
ARMS="fma:4 fma:16 fma:32" bash research/maple-edward-r108n-class-dose-run.sh
ARMS="mul:0 mul:4 mul:16 sum:4 shf:4" bash research/maple-edward-r108n-class-dose-run.sh
# candidate removals, paired, 121 rounds (~11 s)
bash research/maple-edward-r108n-variant-run.sh
# census + pricing table
python3 research/maple-edward-r108n-census.py
```

All three scripts default to `FERN_DEFEAT_SLOTS=64`. They build
`research/fern_r100_attn_probe.swift` with `xcrun swiftc -O` and take the scored
source read-only.

## Caveats

- M4 only. The M4 Pro reports Apple GPU generation 16 and selects no `_nax`
  kernel, so these are directional numbers for an M5 ranked decision. They are
  used here only to *falsify* a hypothesis, which is the direction M4 evidence
  supports: a mechanism that cannot clear the bar by 25x on M4 issue accounting
  is not a candidate for a scarce M5 receipt.
- The probe reproduces 89 % of shipped per-dispatch cost, so it under-represents
  whatever the remaining 11 % is (cache state, neighbouring dispatches). It does
  not change any sign.
- `simd_sum` and `simd_shuffle_xor` class prices are latency-inclusive upper
  bounds (eight independent chains only).
- `k_issue` remains a bracket, not a number. Every conversion above is shown at
  both ends and against rule 100's independent instrument; all three agree on the
  verdict.

## Suggested follow-ups (not implemented)

1. **The QK reduction layout, as a genuinely new-family experiment.** Not an
   instruction trim; needs its own assignment, a margin certificate, and M5
   evidence. It is the only census item that reaches the bar.
2. **Retire dose-based slot pricing for removal estimates.** The 5.7x
   over-prediction above means the ledger's slot-to-microsecond conversion should
   be annotated as an addition-side price, valid for "what does adding work
   cost", not for "what does removing work save".
3. **`main: bf16->f32 converts` (128 slots, 8.6 %) was left unexplored.** If the
   QK fma could consume bf16 operands directly the converts might fold into the
   load, but that is a precision change outside the accepted attention
   quantization envelope, so it needs an envelope ruling before any measurement.
