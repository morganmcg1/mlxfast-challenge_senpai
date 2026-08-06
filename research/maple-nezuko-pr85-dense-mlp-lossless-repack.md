# PR #85 — Dense MLP lossless BF16 repack

Assignment `maple-2026-08-06g-dense-mlp-lossless-repack`, revision `r1`.
Student: maple-nezuko. Base `f2fedd584e6514569758d79e581402210306e77b`.

**Hypothesis.** The layer-0 dense MLP moves 100.66 MB of BF16 weight per decode
step and both of its kernels already sit at 96–97 % of this host's memory
ceiling. If those planes can be re-encoded to fewer bytes *without changing a
single emitted BF16 bit pattern*, decode time should fall in proportion to the
bytes removed.

**Result headline — NO-GO. The hypothesis is refuted.** The encoding works and
is provably lossless: 25.14 MB removed per step, 0 mismatching bit patterns over
50,331,648 weights, end-to-end `max_abs_diff: 0` on all 12 timed runs. But the
bytes do not buy time. On 6 v 6 paired runs the packed path is **+0.905 %
slower** to decode (95 % CI [+0.35 %, +1.46 %], exact permutation p = 0.0087),
i.e. a score change of **−0.71 %**, against a predicted **+0.59 %…+0.68 %**
gain. The unpack ALU costs ≈ 2.2× the bandwidth it buys on this host and ≈ 5.3×
on the ranked host (§6.5). Do not merge. Full timing analysis in §6; §6.6
withdraws the d = 5 follow-up on the same arithmetic.

---

## 1. Why this target

| kernel | M4 µs/step | MB/step |
|---|---|---|
| `dense_gate_up_swiglu_bf16_v1` | 268.0 | 67.11 |
| `dense_down_residual_bf16_v1`  | 133.0 | 33.55 |
| **total** | **401.0** | **100.66** |

100.66 MB is 5.61 % of the decode step's traffic, worth 4.51 % of score if it
could be removed entirely. Both kernels are bandwidth-bound at 96–97 % of the
achievable ceiling, so bytes are the only lever; arithmetic restructuring cannot
help.

Programme constants used throughout: 1 ms of decode `T` = 14.862 % of score;
MDE (95 %) on `ns` = 0.278 %; advisor acceptance bar ≈ 0.61 %; M4→M5 conversion
factor 0.399.

---

## 2. Weight census

Script: `research/nezuko_dense_census.py` (subcommands `value | gates | axis |
block | scheme | all`). Logs: `research/maple-nezuko-pr85/census-value.log`,
`census-gates.log`, `census-scheme.log`.

Tensors: `model.layers.0.mlp.{gate_proj,up_proj}.weight` BF16 `[8192, 2048]`;
`model.layers.0.mlp.down_proj.weight` BF16 `[2048, 8192]`.

**§0.9.33 admissibility.** Every quantity in this census is a property of the
checkpoint's bits, computed on CPU by `numpy`, with no GPU, no timer and no
dispatch involved. `pack_frac_row(W)`, `outliers_per_row(14)`, the `tz`
histogram, `distinct16`, the entropies and the escape rate are all determined
by the *algorithm applied to the weight file*, not by the machine that applied
it. Re-running this script on the ranked M5 against the same
`reference_weights/laguna-xs-2.1-nvfp4-mlx` would return **bit-identical
numbers**. That is what makes an M4 census a legitimate gate for an M5 change,
and it is why §7.1's host caveat applies to the *timing* in §6 but not to
anything in this section.

The derived byte counts in §5.1 are in the same transferring class — they are
counts, not rates. The *prices* in §5.1.1 are not: they multiply transferring
byte counts by a machine-determined GB/s, so they are labelled as estimates
and quoted over a rate range rather than as a single number.

### 2.1 Value census — mantissas are incompressible

| statistic | gate | up | down |
|---|---|---|---|
| exact zeros | 0 | 0 | 0 |
| subnormals | 0 | 0 | 0 |
| inf / nan | 0 | 0 | 0 |
| exponent range | [70, 126] | [71, 126] | [70, 126] |
| `H(exp)` bits | 3.1990 | 3.1813 | 3.1082 |
| `H(man)` bits | 6.972 | 6.972 | 6.972 |
| `H(sign)` bits | 1.0 | 1.0 | 1.0 |
| **lossless floor** | **11.171** | **11.153** | **11.080** |

`P(tz >= k)` is exactly geometric in `k`, i.e. the 7 mantissa bits are
indistinguishable from uniform random. **Any scheme that tries to compress the
mantissa is dead on arrival.** All available headroom is in the exponent, whose
entropy is ~3.2 bits against the 8 bits BF16 spends on it.

### 2.2 Gate ladder — which scheme is licensed

| gate | criterion | measured | verdict |
|---|---|---|---|
| SANITY | census self-consistency | — | **PASS** |
| GO-8 | `frac(tz>=4)` large enough for mantissa truncation | ≈ 1/16 (chance) | **FAIL** |
| GO-12 | `pack_frac_row(14) ≥ 0.85` | 0.7357 / 0.7424 / 0.7358 | **FAIL** |
| **GO-12e** | p99 `outliers_per_row(14) ≤ 8` | **2** | **PASS ← firing gate** |
| GO-13 | `pack_frac_row(30) = 1.0` | 1.000000 (max row span 26) | PASS |
| T8 | `distinct16` per 4096-tile ≤ 256 | 2114 / 2136 / 1797 | **FAIL** |

GO-12 fails but GO-12e passes: a 14-wide exponent window covers only ~74 % of
rows *completely*, yet the rows it misses miss by a **handful of weights**, not
by a broad tail. p99 outliers-per-row is 2 and the maximum is 4. That is exactly
the profile an escape-coded scheme wants.

Row exponent span: median 13, p90 16, p99 19, max 26 / 24 / 26.

### 2.3 Scheme table — choosing the delta width

| `d` (bits) | escape rate | bits/weight | vs BF16 | packed size |
|---|---|---|---|---|
| 3 | ~0.21 | 14.34–14.42 | 90 % | — |
| **4** | **.00015104 / .00014567 / .00014955** | **12.0063** | **75.04 %** | **25.179 MB** |
| 5 | 0.0 | 13.0039 | 81 % | — |

`d = 4` is the argmax. All rows report `guard_ok = True`.

### 2.4 Two dead alternatives, measured not assumed

- **Per-block bases (B = 128):** 12.1162 bits/weight, *worse* than per-channel
  12.0063. The block-base idea is dead — finer base granularity costs more in
  base storage than it recovers in window tightness.
- **Wrong-axis bases:** escape rate ≈ 0.95, catastrophic. The exponent structure
  lives along one specific axis only.
- **`base = min` without a window search:** escape rate 0.0546, ~360× worse than
  the searched placement. Window placement is essential, not incidental.

### 2.5 Deviation from the assignment brief

The brief anticipated reserving a code for exact zeros. The census found
**0 exact zeros** in all three tensors, so code 15 is used as the **escape**
instead (deltas occupy 0..14, giving a 15-wide window). This is strictly better
than the briefed design: it buys one extra exponent of window for free.

---

## 3. Encoding

Per plane, three arrays replace one BF16 array:

| array | width | contents |
|---|---|---|
| `M` | 1 B / weight | `sign << 7 \| mantissa7` |
| `D` | 4 b / weight | exponent delta; element `2b` in bits 0–3, `2b+1` in bits 4–7 |
| `base` | 1 B / channel | window base exponent |

Base granularity is per output row for `gate_proj` / `up_proj`, and per
reduction index for `down_proj` (read as `uchar4`).

**Decode**, one expression, no branch on the common path:

```
as_type<float>( ((M & 0x80) << 24) | ((base + d) << 23) | ((M & 0x7F) << 16) )
```

**Escape detection**, four deltas at a time from one packed `uint`:

```
((dq & (dq >> 1)) & ((dq >> 2) & (dq >> 3)) & 0x1111) != 0
```

This tests all four nibbles for the all-ones pattern (15) in three ANDs and
three shifts, without unpacking.

**Anti-hoist guard.** The escape path must read the stock BF16 plane, but the
compiler must not hoist that load onto the fast path. The pointer is made
conditional so the load is provably dead when no escape fires:

```
const device bfloat* p = LAGUNA_ANY_ESCAPE ? (stock + elt) : (const device bfloat*)0;
if (p) { ... }
```

### 3.1 Bit-identity argument for the reduction

The epilogue and reduction order are byte-identical to stock with one
exception: the fused gate/up kernel uses **two separate `for i` loops** instead
of stock's single interleaved loop. The two accumulator chains are mutually
independent — no value from the gate chain enters the up chain or vice versa —
so splitting the loop leaves **each chain's own summation order unchanged**.
Floating-point addition is order-sensitive but not interleaving-sensitive
across independent accumulators, so the result is bit-identical, and the
certificate in §5 confirms this empirically rather than resting on the argument.

---

## 4. Implementation

New file `Sources/MLXFastModel/LagunaDensePacked.swift` (18,462 B):

- `lagunaDensePackedEnabled` / `lagunaDensePackedVerifyEnabled` — env gates
- `struct LagunaDensePackedBank`, `final class LagunaDenseMLPBanks`
- `extension LagunaRuntimeMLP { func prepareDensePacked() -> [MLXArray] }`
- `lagunaDensePackPlane(_:baseAxis:)`, `lagunaDenseWindowCoverage(...)`
- `lagunaDensePackedReproduces(_:_:baseAxis:)` — the certificate
- `lagunaDensePackedDecodePrelude` (macros `LAGUNA_ANY_ESCAPE`, `LAGUNA_DECODE`)
- `lagunaDensePackedGateUpKernel` + `lagunaDensePackedGateUpSwiGLU(_:banks:)`
- `lagunaDensePackedDownKernel` + `lagunaDensePackedDownResidual(_:residual:banks:)`

Three minimal edits in `Sources/MLXFastModel/LagunaRuntimeModel.swift`:

1. `var _densePackedBanks: LagunaDenseMLPBanks?` (~L8215)
2. packed branch placed first in `fusedDenseDownResidual` (~L8424)
3. load hook (~L11021): prepend
   `fusedArrays.append(contentsOf: dense.prepareDensePacked())`, and add
   `dense._densePackedBanks == nil,` as the first condition of the stock
   `if lagunaFusedDenseGateUpSwiGLUEnabled, let fused = dense.prepareFusedDenseGateUp()`

Controls: `DARKBLOOM_DENSE_PACKED=0` disables the whole mechanism;
`DARKBLOOM_DENSE_PACKED_VERIFY=1` runs the certificate at load.

Style follows the #81 rule: Metal string literals are dedented to column 0 with
no `//` comments inside the literal.

### 4.1 Budget and scope

At assignment marker `1693ea1e21fefaa88d9316f79b91c693f3a7a7ad`:

```
current=2949380/3000000  headroom=50620  growth=19296/262144  files=143
```

`senpai/validate-assignment-scope.sh 1693ea1e… Sources/MLXFastModel/LagunaDensePacked.swift Sources/MLXFastModel/LagunaRuntimeModel.swift`
→ `assignment scope OK: 2 submitted path(s)`.

My allocation was 25 kB and I used 19,296 B of growth. The standing law that
`LagunaRuntimeModel.swift` keeps ≥ 20 kB of per-file margin is respected: the
new code lives in a separate file precisely so that margin is untouched.

---

## 5. Static-equivalence certificate — DISCHARGED

Run `a6151618-8b41-41bd-b923-60fc08f10361`. Log:
`research/maple-nezuko-pr85/certificate-run.log`. Score JSON:
`research/maple-nezuko-pr85/certificate-run.score.json`. This is the programme's
fourth full static-equivalence discharge.

Trace lines (with `DARKBLOOM_TRACE_FUSION=1`):

```
fusion active: dense packed gate/up 50348032B esc 4978 down 25174016B esc 2509
fusion active: dense gate/up packed GEMV + SwiGLU
```

`lagunaDensePackedReproduces` returned true on all three planes, i.e.
**0 mismatching BF16 bit patterns over 50,331,648 weights**.

### 5.1 Bytes moved per decode step

| plane | packed | breakdown | stock | saved |
|---|---|---|---|---|
| gate/up | 50,348,032 | 33,554,432 M + 16,777,216 D + 16,384 base | 67,108,864 | 16,760,832 |
| down | 25,174,016 | 16,777,216 M + 8,388,608 D + 8,192 base | 33,554,432 | 8,380,416 |
| **total** | **75,522,048** | | **100,663,296** | **25,141,248** |

**25.14 MB removed per decode step**, i.e. the dense MLP now moves 75.03 % of
what it moved before — matching the census prediction of 75.04 % to within
rounding.

Escape rates observed at runtime: gate/up 4,978 / 33,554,432 = **0.014836 %**;
down 2,509 / 16,777,216 = **0.014955 %**. Both match the census scheme table.

#### 5.1.1 Escape traffic, booked pessimistically

The table above is the *gross* ledger and it is not yet honest, because an
escaped element also costs a read from the stock BF16 plane, which stays
resident. The advisor asked me to copy frieren's #80 technique and book that
tax in the direction that can only hurt my own claim, so here are both bounds.

An escape is a **per-element** event in this design, not a per-row one. That
matters: the packed planes are always full-width regardless of escapes, so
escapes never cost me a whole row — they are a small additive tax on top of a
fixed gross saving. (A per-row escape scheme, which the brief anticipated,
would have forfeited entire rows.)

| bound | charge per escape | tax | net saved | effective |
|---|---:|---:|---:|---:|
| optimistic | 2 B (the BF16 word) | 14,974 B | 25,126,274 B (25.126 MB) | 75.04 % of stock |
| **pessimistic** | **128 B (a full cache line)** | **958,336 B** | **24,182,912 B (24.183 MB)** | **75.98 % of stock** |

The pessimistic bound assumes every one of the 7,487 escapes lands on its own
private 128 B cache line and shares that line with nothing else — false in
practice, since escapes cluster in the low-magnitude tail, but it is the bound
that cannot flatter me.

Re-pricing against §0.9.27's byte roofline at the exchange rate 14.862 %/ms:

| bound | @610 GB/s | @546.2 GB/s |
|---|---|---|
| optimistic | 41.19 µs → **+0.6122 %** (2.20× MDE) | 46.00 µs → **+0.6837 %** (2.46× MDE) |
| **pessimistic** | 39.64 µs → **+0.5892 %** (2.12× MDE) | 44.27 µs → **+0.6580 %** (2.37× MDE) |

**The honest predicted band is +0.589 % … +0.684 % of score**, i.e. 2.1–2.4×
the 0.278 % MDE, and the escape tax costs at most 3.8 % of the gross saving.
Note that the pessimistic figure still sits above the advisor's ≈ 0.61 %
acceptance bar at 546.2 GB/s and just below it at 610 GB/s, so the *rate*
assumption, not the escape tax, is what decides whether this clears the bar.

> **Superseded by measurement.** This whole prediction is a pure byte-roofline
> forecast: it prices the bytes removed and silently assumes the unpack
> arithmetic is free. §6.2 measures **−0.71 %** where this section predicts
> **+0.59 %…+0.68 %**, and §6.5 recovers the missing term — the unpack ALU costs
> ≈ 219.6 µs/step, roughly 2.2× the 100.6 µs of bandwidth it buys on this host.
> The escape tax, which this section works hard to bound, turns out to be
> irrelevant: it is at most 3.8 % of a saving that is itself swamped by an ALU
> cost 2.2× larger. Read §5.1.1 as a record of what the byte roofline predicts,
> not as a live claim.

### 5.2 §0.9.31 RAM allocation accounting

With the mechanism ON, the stock fused 67.11 MB BF16 bank is **not built**.

| arm | arrays | total |
|---|---|---|
| OFF | 1 | 67.11 MB |
| ON | 6 | 75.52 MB |
| **net** | | **+8.41 MB** |

The escape path still needs the stock plane resident, which is why ON is a net
allocation *increase* even though it is a per-step traffic *decrease*. At
`peak_ram_gb: 21` against 128 GB of ranked unified memory this is immaterial,
but it is recorded because the accounting rule requires it.

**Measured, not just predicted:** every one of the 12 campaign-A arms reports
`peak_ram_gb = 21.000` regardless of arm. The +8.41 MB delta is 0.04 % of the
21 GB peak and therefore sits **below the harness's own reporting resolution**
— the harness rounds to whole GB. So I can state the allocation delta from the
build accounting above and from the trace, but I cannot corroborate it from
`peak_ram_gb`; that field is simply not sensitive enough to see it. Recorded
this way rather than as "no RAM difference", per the §0.9.32 wording rule.

This is the §0.9.31 test the advisor handed me. My arm changes load-time
allocations by 5 extra arrays and +8.41 MB — a far larger allocation-image
perturbation than the null A/A arm, which changes them by exactly zero. §6
reports the prefill control for both, so if §0.9.31 is a real mechanism the
arm's prefill should move and the A/A's should not; if it is host noise they
should move alike.

### 5.3 End-to-end correctness in the certificate run

```
passed_correctness:       true
max_abs_diff:             0
checked_steps:            130
golden_hash:              b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63  (matches --local-iterate golden)
peak_ram_gb:              21  (20.715)
decode_seconds_per_token: 0.0133219   ← traced run, EXCLUDED from the timing pool
prefill_seconds_per_token: 0.0011258
prefill_speedup:          0.326 / floor=false   ← known host artefact, see §7.2
```

The decode number from this run is deliberately **not** used for timing: the run
had `DARKBLOOM_TRACE_FUSION=1` set, which perturbs the hot path.

---

## 6. Timing — NO-GO. The mechanism is a decode regression.

**The hypothesis is refuted.** Removing 25.14 MB/step of decode weight traffic
made decode **slower**, not faster, and by roughly the magnitude the byte
saving was predicted to gain. The unpack arithmetic costs about 2.2x the
bandwidth it buys.

### 6.1 Design

Campaign A, 12 runs, one build, within-binary `DARKBLOOM_DENSE_PACKED` switch,
no checkout or rebuild between runs. Arm order `on off off on off on on off on
off off on`. ON occupies slots {1,4,6,7,9,12} and OFF slots {2,3,5,8,10,11};
both sum to 39, so both arms have mean slot 6.5 and **arm is exactly
orthogonal to slot** by construction, not by luck.

`git diff --name-only 2a16e97 c708c77` touches only `research/` files, so every
slot ran a byte-identical binary. The varying `commit` field in the JSONs is
cosmetic and `analyze.py` warns rather than fails on it; I verified the span by
hand because an identical `golden_hash` is necessary but not sufficient.

Raw JSONs are committed as `research/maple-nezuko-pr85/a_*.json`; the two
analysis logs are `analysis-a.txt` and `covariate-a.txt`.

### 6.2 Result

```
decode: base(OFF) n=6 mean=0.0131405043 s/tok  sd=0.445%
decode: cand(ON)  n=6 mean=0.0132594788 s/tok  sd=0.528%
decode: change   +0.9054% SLOWER   SE 0.2833%   95% CI [+0.35%, +1.46%]
decode: exact permutation p(ON slower) = 8/924 = 0.0087
decode: drift-adjusted +0.9013%   (slot trend +0.0517%/run)
```

Conversion to the ranked axis, using the programme constants (M4->M5 factor
0.399; 1 ms of decode `T` = 14.862% of score):

| quantity | value |
|---|---|
| M4 us/step | **+118.97 slower** |
| M5 us/step (x0.399) | **+47.47 slower** |
| score impact | **-0.7055%** |
| predicted gain (§5.1.1) | +0.589% .. +0.684% |

The sign is wrong and the magnitude is comparable, so this is not a
"smaller-than-hoped win" — it is a loss of about the size of the hoped-for win.

### 6.3 The A/A null control, and why it is conservative here

```
decode OFF A/A null (20 balanced 3v3 splits): sd 0.3724%, 95th pct |d| 0.6875%
decode ON  A/A null (20 balanced 3v3 splits): sd 0.4424%, 95th pct |d| 0.8033%
```

The observed 0.905% clears both. It clears them by more than it appears to:
the A/A null is built from 3v3 splits, whose contrast SE is
`sd*sqrt(1/3+1/3)`, while the real comparison is 6v6 with SE
`sd*sqrt(1/6+1/6)`. The null is therefore inflated by `sqrt(2)` relative to
the statistic it is being compared against. Rescaled to a 6v6 contrast the
95% thresholds are ~0.486% (OFF) and ~0.568% (ON), and the effect clears both
comfortably.

I am stating this because it cuts against my own result's convenience: had the
effect been a *win* of 0.7%, the naive 3v3 comparison would have made me call
it noise when it was not.

### 6.4 The prefill null channel failed, and I checked whether that matters

Prefill is a **mechanism-null channel**. The packed path is gated on
`x.dims(1, 1, hidden)` (`LagunaRuntimeModel.swift:8405-8428`), so a 512-token
prefill provably never enters it and both arms execute byte-identical prefill
code. The only ON-vs-OFF difference prefill can see is the 5 extra resident
arrays and +8.41 MB of §0.9.31 residency.

That channel nonetheless moved:

```
prefill(control): change -1.0057% FASTER   SE 0.4388%   p = 24/924 = 0.0260
```

A nominally significant effect in a channel where the mechanism cannot act is
exactly the sort of thing that should reduce confidence in the primary result,
so I tested it rather than noting it:

```
within-run Pearson r(decode, prefill), n=12 = -0.1560
decode raw               = +0.9013%   p = 8/924  = 0.0087
decode prefill-adjusted  = +0.7856%   p = 14/924 = 0.0152
prefill (null channel)   = -1.0057%   p = 901/924
```

`r = -0.156` is weak, so the two channels are **not** one run-level see-saw —
a shared thermal or clock nuisance would move both in the same direction and
show strong positive `r`. Using prefill as a covariate and re-contrasting the
residuals retains **+0.7856% of the raw +0.9013%**, i.e. 87% of the regression
survives removing everything the null channel could explain, and it stays
significant.

So the decode regression is not an artifact of whatever moved prefill. The
most plausible reading of the prefill movement is the residency change itself:
+8.41 MB and 5 extra buffers perturb the MLX allocator, and that happens to
help a 512-token prefill while hurting a 1-token decode. I am not claiming the
prefill number as a win — it is a side effect of an arm I am recommending
against.

Adjusted score impact, if one prefers the covariate-adjusted figure:
**-0.6149%** instead of -0.7055%. Both are regressions.

### 6.5 Why this conclusion transfers off this host

§7.1 warns that a null on M4 Pro is weak evidence against a mechanism that
trades bytes for ALU, because this host is more likely ALU-limited than the
ranked M5 Max. That warning was written before the data and I have to apply it
honestly now. It does not rescue the result, for a reason the measurement
itself supplies: the experiment does not just give a sign, it gives the
**magnitude of the ALU cost**.

- Byte saving 25.14 MB/step. At this host's ~250 GB/s that is worth 100.6 us.
- Observed change: +118.97 us slower.
- Therefore the unpack arithmetic costs ~**219.6 us/step** on M4 Pro, i.e.
  ~2.2x the bandwidth it buys.

> **r2 correction.** §10.2 re-derives this from primary sources and gets
> **212-219 us**, so the paragraph below stands. But the M5 denominator used
> here was **610 GB/s**, which R12.5 forbids as a physical rate: it is
> definitional (`1794 MB / 2.941 ms`). The admissible measured M5 rates are
> 546.2 and 651.8 GB/s. Corrected figures are inlined below and derived in
> §10.4.

On the ranked M5 Max the same 25.14 MB is worth only **38.6-46.0 us**
(`25.141e6` at 651.8 / 546.2 GB/s), because higher bandwidth makes each saved
byte *cheaper*, not dearer. For the mechanism to break even on M5 the unpack
cost must fall from ~219 us to <=46 us — a **4.8x to 5.7x** improvement in ALU
throughput per unit of memory bandwidth relative to M4 Pro. M5 Max has more GPU
cores, but its bandwidth rises ~2.2-2.6x at the same time, so the ALU:bandwidth
ratio does not move anything like 5x in the required direction.

This is the case where the M4 host *can* settle the question: the byte saving
is fixed and known, the ALU cost is measured, and the ratio is far outside the
range that a generation change plausibly spans. A 20% error in either term
does not change the verdict.

### 6.6 The follow-up variant does not rescue it either

§9.1 proposed P13 (d=5, zero escapes, branch-free). Pricing it with the
measured ALU cost rather than with hope: it removes the escape branch, ~4 of
the ~9 integer ops per weight, but raises the code from 12.0063 to 13.0039
bits/weight, cutting the saving from 25.14 MB to ~18.8 MB.

- ALU cost ~`219.6 * 5/9` = ~122 us
- Byte saving on M4 = `18.8e6/250e9` = ~75 us
- Net: still ~47 us **slower** on M4.
- On M5 the saving is ~29-34 us (at 651.8 / 546.2 GB/s; the r1 text used the
  forbidden 610 divisor, see §6.5) against ~122 us of ALU, needing a 3.5-4.2x
  ALU improvement.

P13 is therefore also dead, and I am withdrawing it as a follow-up rather than
leaving it in §9 for someone to spend a session on.

### 6.7 The honest threat to this conclusion

The one reading that would overturn the NO-GO is that my kernel is *correct
but avoidably slow* — a missed vectorized load, an unnecessary barrier, or the
anti-hoist construct (`const device bfloat* p = LAGUNA_ANY_ESCAPE ? ... : 0;`)
defeating an optimization. Bit-exactness does not rule this out: every
correctness gate here proves the *outputs* are right, and none of them prove
the kernel is as fast as the encoding permits.

I am not claiming the encoding is unimplementable at lower ALU cost. I am
claiming that at 2.2x overshoot, closing the gap needs a >2x kernel
improvement merely to reach break-even on M4 and ~5x to win on M5, which is
not a plausible return on a straightforward GEMV unpack loop.

---

## 7. Controls and limitations

### 7.1 Host is not the ranked host

Every number in §6 comes from an AWS **M4 Pro** (`applegpu_g16s`, 48 GiB, Apple
GPU generation 16, low-memory startup profile, ~250 GB/s effective, idles at
~40.3 °C against a 40 °C cool gate). The ranked host is an **M5 Max** with
128 GB. This box does not select `_nax` kernels at all.

For *this* experiment the cross-machine risk is unusually structured: the
mechanism trades **bytes for integer ALU work** (roughly 9 extra integer ops per
weight to unpack), so whether the trade wins depends on the host's
bytes-per-ALU-op balance, and an M4 Pro at ~250 GB/s with fewer GPU cores is
*more* likely to be ALU-limited than an M5 Max.

Written before the campaign, that asymmetry was the reason to treat a *null*
here as weak evidence against the mechanism. **It does not rescue the result
that actually came back**, and §6.5 is what settles the question rather than
this section. The reason is that the M4 outcome is not a null but a large
signed regression whose magnitude can be converted: the 25.14 MB saved is worth
100.6 µs at 250 GB/s, the measured cost is +118.97 µs, so the unpack ALU is
≈ 219.6 µs — about **2.2× the bandwidth it buys**. Moving to the M5's
~610 GB/s makes the *numerator* worse, not better: the same bytes are then worth
only 41.2 µs, so the M5 needs the ALU term to fall by **5.3×** merely to break
even. The M5's advantage in ALU throughput over an M4 Pro is nowhere near that.
The host asymmetry is real and it points the right way, but it is roughly a
2× effect against a deficit that needs 5.3×, so the sign of the conclusion does
not change. I would still want the ranked host to confirm the exact number; I
do not think it can flip it.

### 7.2 Prefill is a control, not a claim

`prefill_speedup ≈ 0.327 / floor=false` appears in every run on this host,
**including the unchanged base**. It is the generation-16 / no-`_nax` artefact,
not a property of any candidate. I make no prefill claim in either direction.

Prefill is a *usable* control here for a specific, checkable reason rather than
by assumption. `fusedDenseDownResidual` opens with `guard x.dim(1) == 1`
(`LagunaRuntimeModel.swift:8404`), so on the 512-token prefill pass the whole
function returns `nil` and neither packed kernel is ever dispatched. The
mechanism is structurally unable to do work during prefill.

It is **not** a perfectly insulated control, and I will not claim it is. With
the mechanism ON the runtime keeps a different resident array set — six arrays
totalling 75.52 MB, and the stock fused BF16 bank is not built at all (§5.2) —
so allocator and page-mapping state differ between arms even though no packed
code runs. A small prefill difference between arms is therefore possible
without implying any prefill mechanism. The honest reading is: prefill should
be flat, and if it is not flat at full replication that is evidence of a
measurement confound to investigate, not evidence of a prefill win.

### 7.3 Timing pool hygiene

- The certificate run is excluded (traced).
- Campaign A is a single build with a within-binary env switch, so no
  build-to-build variation can contaminate the arms.
- The run order `on off off on off on on off on off off on` is counterbalanced
  against monotone thermal drift, and the analysis additionally fits a
  slot-ordered OLS drift term.
- An **A/A null control** is computed from the same data as a falsification
  check on the analysis itself.

---

## 8. Reproduction

### 8.1 ⚠ The mechanism is not present at this branch head

r2 reverted both submitted files, so **`HEAD` of this branch carries no kernel,
no `LagunaDensePacked.swift`, and no `DARKBLOOM_DENSE_PACKED` flag at all** —
the PR is research-only and its submitted surface is identical to base. Nothing
below runs against `HEAD`. The last commit that carries the implementation is
**`44f4992`**, and every timing/certificate command in §8.3 must be run from
there.

### 8.2 ⚠ Flag polarity changed twice; the recorded campaign used the first one

Three distinct polarities exist in this branch's history and confusing them
reproduces the wrong arm, so they are tabulated rather than described:

| tree | ON arm is spelled | OFF arm is spelled |
|---|---|---|
| campaign-A tree (`262efe4` and earlier; default **ON** as the brief specified) | unset | `DARKBLOOM_DENSE_PACKED=0` |
| `11facb6 … 44f4992` (default **OFF**, opt-in) | `DARKBLOOM_DENSE_PACKED=1` | unset |
| `cfbad24` = branch `HEAD` (r2 revert) | *does not exist* | *does not exist* |

Campaign A ran under row 1. Because §6 measures the mechanism as a
**regression**, leaving it default-ON would have meant that merging this branch
for its write-up silently cost ~0.7 % of score, so `11facb6` made it opt-in
(`LagunaDensePacked.swift:26-31` at `44f4992`). Nothing else about the
mechanism changed and the certificate is unaffected.

`run-campaign-a.sh` as originally committed hard-coded row 1 (`off` → `=0`,
`on` → unset). Against a row-2 tree that spells **both** arms OFF, which is a
silent A/A rather than an error. r2 fixes the script to row-2 polarity so that
running it against `44f4992` reproduces the recorded arms; the row-1 spelling
is retained in a comment as the historical record.

### 8.3 Commands

```bash
# census -- the only step that runs against HEAD
python3 research/nezuko_dense_census.py all

# everything below needs the implementation:
git checkout 44f4992

# certificate (single run, traced)
DARKBLOOM_TRACE_FUSION=1 DARKBLOOM_DENSE_PACKED=1 \
  DARKBLOOM_DENSE_PACKED_VERIFY=1 ./benchmark.sh --local-iterate

# timing campaign A (12 paired runs, ~40 min); opt-in polarity, matches 44f4992
bash research/maple-nezuko-pr85/run-campaign-a.sh

# analysis (runs against the committed JSONs, so HEAD is fine)
cd research/maple-nezuko-pr85 && python3 analyze.py a
cd research/maple-nezuko-pr85 && python3 covariate.py

# enable the packed path by hand (opt-in); omit the variable for stock
DARKBLOOM_DENSE_PACKED=1 ./benchmark.sh --local-iterate
```

---

## 9. Suggested follow-ups (not implemented)

This section was drafted before the campaign. §6 refuted the arm, so the list
below has been rewritten to say what is actually still worth a slot. §9.1 is
**withdrawn by my own measurement** and is kept, struck, so nobody re-opens it.

### 9.1 P13 branch-free — WITHDRAWN, do not run this

This was drafted as the strongest follow-up. **§6.6 kills it and I am
withdrawing it rather than leaving it on the list.**

The original argument: the census says `d=5` reaches **zero escapes** (§2.3), so
a 5-bit delta with a per-channel base covers every element of all three planes
with no exceptions. That costs 13.0039 b/w against P12's 12.0063 b/w — ~8 %
more bytes — but removes the `LAGUNA_ANY_ESCAPE` mask test and the anti-hoist
pointer dance (roughly 4 of the ~9 integer ALU ops per weight), removes the
resident stock plane (turning §5.2's +8.41 MB into roughly −33 MB), and makes
§5.1.1's escape tax identically zero.

Why it does not survive: P13 removes ~4 of ~9 ALU ops, so on the measured
≈ 219.6 µs unpack cost it would still spend ≈ 122 µs — while *reducing* the
byte saving to ~18.9 MB, worth ~75 µs on this host and only ~31 µs on the M5.
It is a smaller win on the term that is already losing and a smaller loss on
the term that is already too small. It is underwater by ~1.6× on M4 and ~3.9×
on M5, which is worse than P12 on M5. The three structural simplifications are
real and P13 is genuinely nicer code; none of that matters when the sign is
wrong. **Do not spend a slot on it.**

### 9.2 Interleave the M and D planes

The shipped scheme keeps mantissa bytes and delta nibbles in two separate
arrays, so each weight costs two loads from two streams. Packing 2 weights into
3 contiguous bytes gives one stream at the cost of byte-unaligned extraction.
It is a self-contained kernel-only change with an unchanged certificate.

**CLOSED by §10.6(b), not merely downgraded.** It attacks stream count, not the
term that lost. §6.5 puts the unpack ALU at ≈ 219 µs against ≈ 100.6 µs of
bandwidth bought (≈ 39–46 µs on M5); byte-unaligned extraction *adds* shift and
mask work, so the most optimistic reading is that it trades a little load-issue
pressure for a little more ALU on the side of the ledger that is already 2.2×
over. §10.6(b) then closes it outright: 1 B + 0.5 B in two planes and 3 B per
2 weights in one plane are the **same 1.5 B/weight**, so this arm removes
**zero** bytes while adding in-loop ops, and the break-even law rejects it for
every positive exchange rate without needing a measurement. Do not spend a slot
on it.

### 9.3 Do not chase P8 or T8 — both are closed

Recording these so nobody re-opens them:

- **P8 is dead.** GO-8 failed decisively: `frac(tz>=4) ≈ 1/16`, and
  `P(tz >= k)` is *exactly* geometric (§2.1), which is the signature of
  uniformly random mantissa bits. There is no mantissa headroom in this
  checkpoint at all. The 50.33 MB / +1.37 % line in the brief's pricing table
  is unreachable.
- **T8 is dead.** Max per-4096-tile `distinct16` is 1,797–2,136 against a bar
  of 256 — off by ~8×.
- **Block-shared bases are dead.** Measured at B=128 they need 12.1162 b/w,
  *worse* than the per-channel 12.0063 b/w, because a block spanning channels
  inherits the union of their exponent ranges (§2.4).
- **Wrong-axis bases are catastrophic**, escape rate ≈ 0.95.

All four were measured rather than assumed, which is the point of §2.4.

### 9.4 Where the same mechanism could apply next

This experiment consumed the only plain-BF16 MLP in the model — layer 0 is the
sole layer whose MLP is `Linear` rather than `QuantizedLinear`. So the exact
mechanism does not generalise to layers 1–39, whose MLPs are already NVFP4.
The transferable asset is the **census + certificate + counterbalanced-campaign
template**, now run twice (#72, #85), and the finding that this checkpoint's
BF16 exponents carry ~4 bits of exploitable structure per weight while its
mantissas carry none. Any future BF16 plane in this model should be priced at
**12 b/w with a per-channel base**, and should not be censused for mantissa
structure again.

### 9.5 Instrument work the programme needs more than it needs this arm

The measurement limit is asymmetric, and this campaign is a clean illustration
of both halves. A 0.6 % *win* cannot be confirmed on this host at n = 6 per arm:
the A/A null (§6.3) has p95 ≈ 0.69–0.80 %, so a true +0.6 % is inside the noise
floor. A ~0.9 % *regression* is a different matter — it cleared that same null
with an exact permutation p = 0.0087 and survived prefill adjustment (§6.4).
So the honest statement is that **this host can refute an arm it cannot
confirm**, and pre-screening for negatives is worth more here than
pre-screening for positives.

That asymmetry is worth building on rather than working around. Cheap, high
value: establish the A/A null *before* the arm rather than after it. My null
here is honest but post hoc — it comes from 20 within-arm 3 v 3 splits of the
same 12 runs (§6.3), so it costs no extra GPU time but the threshold was known
only after the result was. A pre-registered per-host null would cost one idle
campaign and would make every subsequent sub-1 % verdict on that host cheaper to
defend. More expensive
but more useful: if the programme wants local pre-screening to *confirm* sub-1 %
arms, it needs either many more repetitions per arm or a lower-variance
measurement than end-to-end `--local-iterate`. That is a programme-level
decision, not something to fix inside one experiment.

### 9.6 The generalisable finding, which is not about this arm

The transferable result is not "the repack failed" but a **priced exchange
rate**: on this model's dense BF16 planes, a per-channel-base delta scheme buys
25.14 MB/step at a cost of ≈ 212–219 µs of unpack ALU. Any future
bytes-for-arithmetic trade in this runtime can be screened against that number
before anyone writes a kernel. §6.6 shows that test correctly rejecting P13
without a run. I would rather the programme keep that constant than keep this
kernel.

**§10 is the finished form of this paragraph** and supersedes the rule of thumb
that stood here in r1. The screening constant is
`bits_removed_per_weight ≥ k × ops_per_element / G`, with `k ≈ 1 bit/op` on
M4 Pro and `k ∈ [0.94, 2.52]` on M5, and the amortisation factor `G` — not the
op count — is what decides most arms.

---

## 10. The break-even exchange rate for in-kernel unpacking

This is the r2 deliverable. §9.6 said the transferable asset is a priced
exchange rate; this section actually prices it, states it as a law with an
explicit interval, and applies it to the three arms currently queued behind it.

Per **§0.9.11** ("a banked price is not evidence") every input below is
re-derived from a primary source and cited. Two labelling notes for the record:
the banked-price rule is **§0.9.11**
(`CURRENT_RESEARCH_STATE.md:2417-2436`), not §0.9.13 (`:2622-2652`, which is
the 6-of-8 audit tally); and §6.5/§9.2/§9.6 as written in r1 quoted **610 GB/s**
as an M5 rate, which R12.5 (`:1096`) forbids — 610 is definitional
(`1794 MB / 2.941 ms`) and "must never be quoted as one". Those three places are
corrected below and in situ.

### 10.1 The advisor's derivation, and the one thing wrong with it

As given in PR #85 comment 5:

```text
unpack ALU ≈ (0.905 % + 1.133 %) × 8530 µs ≈ 174 µs
           ≈ +43 % on top of the ~401 µs stock dense pair
```

The construction is right and the second term checks out exactly: the byte
saving is `25,141,248 B / 260.2 GB/s = 96.62 µs`, and `96.62 / 8530 = 1.1327 %`.
So the 1.133 % term is the byte saving expressed as a fraction of an
**8530 µs** step.

The error is in the first term. My measured **+0.9054 % is a fraction of
D = 13,140.5 µs**, the `--local-iterate` `decode_seconds_per_token` on my AWS
M4 Pro (§6.1). The 8530 µs is a *different host and a different instrument*:
it is `wall 8.530 ms` from maple-tanjiro's instrumented `decode_probe.py`
census (`maple-tanjiro-pr73-decode-kernel-census.md:292`), whose own doc warns
at `:120-123` that profiled wall is `fputs`-inflated and must not be compared
against non-profiled runs. Multiplying my percentage by that step silently
rescales the measured delta from a 13.14 ms denominator onto an 8.53 ms one:

- advisor's implied delta: `0.905 % × 8530 = 77.2 µs`
- actual measured delta: **`0.9054 % × 13,140.5 = 118.97 µs`** (§6.1)

The delta is understated by 41.8 µs, so the ALU total is understated by the
same amount. **The fix is to never convert the measured effect through a
percentage at all** — the campaign yields an absolute delta, so use it.

### 10.2 The corrected ALU cost

```text
ALU_seconds = measured_delta_seconds + bytes_removed / R
```

Both terms are host-internal to my campaign except `R`, and `R` is bracketed:

| input | value | source |
|---|---|---|
| measured delta | **+118.97 µs/step** (95 % CI [+46, +192] µs) | §6.1, 12 counterbalanced runs |
| bytes removed, gross | **25,141,248 B/step** | §5.1, certificate |
| bytes removed, net of pessimistic escape tax | **24,182,912 B/step** | §5.1.1 (7,487 escapes × 128 B) |
| `R` host streaming ceiling | **260.2 GB/s** | `research/host_bandwidth_ceiling.swift` via `maple-fern-prefill-roofline.md:66` |
| `R` achieved by these two kernels | **~251.0 GB/s** (252.3 / 250.4, i.e. 96–97 % of ceiling) | `pr73-census.md:496-500` |

Four corners:

| bytes | `R` | value of bytes | ALU |
|---|---|---:|---:|
| gross | 260.2 | 96.62 µs | **215.6 µs** |
| gross | 251.0 | 100.16 µs | **219.1 µs** |
| net | 260.2 | 92.94 µs | **211.9 µs** |
| net | 251.0 | 96.35 µs | **215.3 µs** |

**Unpack ALU = 212–219 µs/step on M4 Pro**, ~24 % above the advisor's 174 µs
and consistent with the 219.6 µs §6.5 reported. The campaign CI widens this to
[143, 292] µs; the corner spread (±2 %) is negligible against it.

As a surcharge on the stock dense pair, the honest figure is an interval,
because the pair cost is measured on tanjiro's host and the ALU on mine:

- against the census pair as printed, `269.7 + 134.6 = 404.3 µs`
  (`pr73-census.md:191,196`): **+52 % to +54 %**
- against that pair scaled to my host's step, `404.3 × 13140.5/8530 = 622.9 µs`:
  **+34 % to +35 %**

So **+34 % to +54 %**, not +43 %. The advisor's +43 % happens to land inside
that interval, but by cancelling two errors — the understated delta and the
unscaled denominator — rather than by being right.

### 10.3 The rate

Divide by the work, not by the step. The three planes hold **50,331,648
weights** (§2), and the decode unpack expression is **~9 integer ops per
weight** (§6.6).

```text
t_op = ALU / (weights × ops_per_weight)
     = 212…219 µs / (50,331,648 × 9)
     = 0.468 … 0.484 ps per integer op per weight
```

One byte of stream costs `1/R`: 3.843 ps at 260.2 GB/s, 3.984 ps at 251.0 GB/s.
So the break-even constant is

```text
k = t_op × R   =   0.94 … 1.01 bits removed per weight, per added integer op
                    per weight, on M4 Pro
```

**≈ 1 bit per op.** Stated as a law:

```text
bits_removed_per_weight  ≥  k × ops_per_weight
```

Self-check against the arm that produced it: this scheme spends 9 ops/weight,
so it needs ≥ 8.5–9.1 bits/weight. It removes `16 − 12.0063 = 3.9937`
bits/weight. Short by **2.1–2.3×** — which is exactly the 2.2× overshoot §6.5
reports by a completely different route. The rate reproduces its own input.

### 10.4 The M5 interval, and why it must be an interval

**§0.9.36** (`CURRENT_RESEARCH_STATE.md:193-227`) is the governing rule: byte
removals transfer M4→M5 at **1.0–1.2×** (confirmed a third time at 1.18×), but
instruction- and occupancy-channel M4 wall residuals **do not transfer** and
have been over-stated by ~12× (M4 2.25 % vs M5 ranked 0.18 %). `k` is a ratio
of an instruction-channel term to a byte term, so its M5 value cannot be a
point.

The byte side is well determined. Per R12.5, the admissible M5 denominators are
the two *measured* rates — **546.2 GB/s** (routed block, the adopted decode
achievable rate) and **651.8 GB/s** (attention block) — never 610. This dense
BF16 MLP plane is neither, so it is bracketed by both:
`t_byte(M5) = 1.53 … 1.83 ps/B`, i.e. **a removed byte is worth 2.2–2.6× less
time on M5 than on M4**, not "2.4×" (§6.5, corrected).

The ALU side has no M5 measurement, so bound it by two principled assumptions:

| assumption | `t_op` on M5 | `k` on M5 |
|---|---|---|
| ALU seconds invariant (kernel is bandwidth-bound, unpack sits on the critical path) | 0.468–0.484 ps | **2.04 – 2.52 bits/op** |
| ALU throughput scales with bandwidth (M5's extra cores absorb it proportionally) | 0.19–0.22 ps | **0.94 – 1.01 bits/op** |

```text
k_M5  ∈  [0.94, 2.52]  bits/weight per added integer op/weight
```

That is a **2.7× interval and it is not narrowable from M4 data.** Worse, it is
not even a hard lower bound: §0.9.36's single calibrated instruction-channel
observation, taken literally, implies the ALU term can shrink ~12× as a
fraction of step — and because the M5 step is 3.07× shorter (4.28121 ms,
receipt `c3ce66ec`, `pr73-census.md:461`, vs my 13.1405 ms) that is ~38× in
absolute seconds, i.e. `k_M5 ≈ 0.05`. I do not treat that as a calibrated
bound, but it fixes how the interval may be used:

> **Use `k = 2.5 bits/op` to decide whether to *build* an unpacking scheme.
> Never use `k` to *kill* an arm whose byte side already clears the rate** —
> the instruction channel is the term M4 cannot bound from below.

Applying that to this experiment: at the neutral end my arm needs 8.5 bits and
removes 4.0, so it fails by ~2.1×; only a >2× instruction-channel transfer
discount would rescue it on M5. §6.5 declines to bet on that and §6.7 records
it as the honest residual threat. This section does not change the NO-GO; it
quantifies exactly how far outside the interval the arm sits.

### 10.5 The qualifier that makes the rate usable: amortisation and the critical path

`k` was measured on ops that sit in the **innermost per-weight loop**, where
they compete with load issue for the same registers. The general form is:

```text
bits_removed_per_weight  ≥  k × ops_per_element / G
```

where an *element* is the object being unpacked and `G` is the number of
weights it serves. My arm had `G = 1`, which is the worst possible case and is
why it is the only one of the queued arms the rate rejects. Two corollaries,
both load-bearing:

1. **`G` is the dominant term.** A group-32 scale-plane repack pays its ops
   once per 32 weights, so it clears the same `k` by 1–2 orders of magnitude.
2. **Hoisted ops are cheaper than `k` says.** An op lifted out of the inner
   loop is latency-hidden under the weight loads it precedes; §10.6(c) below is
   direct evidence that at `G = 32` the ALU term falls under the measurement
   floor entirely. So `k × ops/G` is an *upper* bound for hoisted work, and a
   tight estimate only for in-loop work.

### 10.6 Pricing the three queued arms

**(a) Fold the o_proj row base into the codes plane (#80).**
`maple-frieren-pr80-attn-scale-pairwise.md:1383-1384` records the `+1` byte per
row as **4 % of the pairwise o_proj row cost**. The element is a row: 8 bits
removed per element, `G` = the row length, and the fold is address arithmetic
of order 1–3 integer ops per row, hoisted entirely out of the inner loop.
Even ignoring `G` and pricing it as in-loop work, `2.5 × 3 = 7.5 bits` required
against **8 bits removed** — it clears, marginally, at the most conservative
point of the interval; with `G` in the hundreds it clears by two orders of
magnitude. **The rate does not block this arm.** It does supply one concrete
design constraint worth carrying into the brief: **keep the fold to ≤ 3 integer
ops per row and keep them hoisted**, because at 1 op per *weight* the same
8 bits/row would be nowhere near enough. The real risk for (a) is addressing
and occupancy, which this rate does not price (§10.7).

**(b) My own §9.2 M/D plane interleave.**
Priced properly it is not a byte arm at all: two planes at 1 B + 0.5 B per
weight and one plane at 3 B per 2 weights are the **same 1.5 B/weight**. So
`bits_removed_per_weight = 0` while `ops_per_weight > 0`, all of them
byte-unaligned shift/mask work in the innermost loop with `G = 1`. The law
rejects it for **every** `k > 0`, with no interval required and no measurement
needed. §9.2 downgraded it; this rate **closes** it. Its only conceivable
payoff is a load-issue/locality effect that `k` does not price, sitting on top
of a mechanism already refuted by 2.1–2.3×. Do not spend a slot on it.

**(c) ivanfioravanti's 12-bit/3-byte routed gate/up scale packing (`ae9ac90b`).**
`CURRENT_RESEARCH_STATE.md:4258-4266` and `nezuko-harvest-report.md:481-483`:
`scale_row_bytes` 32→24 (16 scales at 16 bits → 16 scales at 12 bits), i.e.
**4 bits removed per element**, ~10 MB/token over 39 layers, measured
4.444 vs 4.471 ms/token = −0.60 % steady ⇒ ≈ **+0.39 % of score**.

This arm is the section's most valuable calibration point, because **the
conservative end of the rate would have rejected it**: `2.5 × 2 ops = 5 bits`
required against 4 bits removed. It won anyway. The resolution is §10.5:
the element is a group-32 scale, so `G = 32`, the two unpack ops are hoisted
and latency-hidden, and the requirement is `2.5 × 2/32 = 0.16 bits/weight`
against `4/32 = 0.125 bits/weight` removed — which is the same near-tie, so
even the amortised form only just clears. The measurement settles it: at
`G = 32` **the ALU term is not resolvable at all**, and the arm delivers its
byte prediction.

Two honest flags on (c). Its observed −0.60 % *exceeds* the pure-byte
prediction (`10 MB / 546.2 GB/s = 18.3 µs` on a 4.471 ms step = **+0.41 %**) by
1.47×, above §0.9.36's 1.0–1.2 × transfer band. An ALU term can only subtract,
so either the 10 MB figure is understated or a second effect is present; I have
not resolved which, and the 10 MB is the number I would re-derive first. And
the 2-op estimate is mine, not measured — unlike my own 9, which came from
counting the shipped expression.

**Bearing on my next assignment.** The queued shared-expert group-32
scale-plane halving (7.67 MB/step, reusing `lagunaHalvedGroup32ScalePlane` from
#72) has the same shape as (c): `G = 32`, ~1–2 hoisted ops, 8 bits removed per
16-bit scale. Required at the conservative end: `2.5 × 2/32 = 0.16 bits/weight`
against `8/32 = 0.25 bits/weight` removed — it clears by ~1.6× on the amortised
form and by far more once the hoisting discount in (c) is admitted. **The rate
green-lights it**, and predicts the outcome will be set by whether the 7.67 MB
survives re-derivation, not by unpack cost.

### 10.7 What this rate does not price

Stating the scope so nobody over-applies it:

- **Stream count, locality and load issue.** §9.2's only remaining argument
  lives here and is invisible to `k`.
- **Occupancy and register-pressure cliffs.** A scheme can clear `k` on op
  count and still lose a threadgroup's worth of occupancy.
- **Prefill.** This is a decode-path constant. §6.4 found the prefill channel
  could not resolve the effect, and #91 §0.9.C
  (`maple-tanjiro-pr91-prefill-budget-census.md:129-139`) is an independent
  second observation that the prefill instrument is the weaker one.
- **Correctness cost.** `k` prices time, not the escape-handling, certificate
  or gate work an encoding needs.

### 10.8 The two "2.4×" factors are unrelated (r2 item 4)

r1's §6.5 said saved bytes are "worth 2.4× less on M5"; #91 §0.9.C says the
brief's mandated M4→M5 factors "overshoot prefill by 2.4×". They are not the
same number and neither supports the other.

§6.5's factor was a **bandwidth ratio**, `610/251 = 2.43` — and §10.4 has now
retired it twice over: 610 is the forbidden definitional divisor (R12.5), and
the correct bracket from the two measured rates is `546.2…651.8 / 251.0` =
**2.2–2.6×**. #91's factor is a **prediction-error ratio**: decode-derived
factors (×0.3886 attention, ×0.4324 routed, ×0.7565 remainder) predict ≥ 211 ms
against an actual S ≈ 97.95 ms. Its own underlying root ratio is the M4→M5
prefill wall ratio `97.95/545.0 = 0.180`, against decode's 0.5019 — a 2.79×
separation, not 2.4×.

Different constructions, different denominators, different quantities; the
agreement to two significant figures is a **coincidence**, and a near one at
that (2.2–2.6 vs 2.4). I checked for a shared factor and found none. Recording
it so the next reader does not spend the same half hour on it.

---

## 11. `SENPAI-RESULT`

**r2 status.** This revision is packaging-only: no new GPU time, no new timing
campaign, and no change to any measurement in §6. It rebases onto
`ea501bc8`, reverts both submitted files so the PR is research-only
(`growth=0`, `files=142`), adds §10 (the break-even exchange rate the advisor
asked for), corrects the forbidden 610 GB/s divisor wherever r1 used it, and
fixes the §8 reproduction polarity. The verdict is unchanged: **NO-GO**.

A git object cannot contain its own hash, so — keeping r1's convention —
`commit_sha` below names the **last commit touching a submitted path**, which
for r2 is `cfbad24`, the revert itself. The authoritative branch-head SHA is
carried by the typed Senpai transition. Note the consequence of that revert:
`cfbad24` is the last commit to *touch* a submitted path, but **no commit on
this branch now contributes to the submitted diff** — `git diff ea501bc8 HEAD
-- Sources/ Vendor/ Package.swift benchmark.json` is empty.

`runs` is empty and that is not an omission. This campaign has **no W&B runs**:
`wandb-applied-ai-team/mlxfast-maple` holds none for this PR or for any
round-6…17 experiment on this track (advisor, PR #85 comment 3). Evidence here
is ranked `mlxfast` receipt IDs plus the in-repo artifacts under
`research/maple-nezuko-pr85/`.

```json
SENPAI-RESULT
{
  "schema_version": 1,
  "status": "failed",
  "hypothesis": "Layer-0 dense MLP BF16 planes can be losslessly re-encoded as per-channel exponent-base + 4-bit delta + 7-bit mantissa (P12/GO-12e), cutting 25.14 MB/step of decode weight traffic for roughly +0.61% of official score.",
  "summary": "Hypothesis REFUTED by measurement, not by construction. The census fired GO-12e and the encoder is provably lossless (0 mismatching BF16 bit patterns over 50,331,648 weights, CPU memcmp), delivering the predicted 25,141,248 B/step. But the unpack ALU costs more than the bytes are worth: 12 counterbalanced same-binary runs give decode +0.9054% SLOWER (95% CI [+0.35%, +1.46%], exact permutation p = 8/924 = 0.0087), +0.7856% after prefill adjustment (p = 0.0152). That is -0.71% of score on M4 and worse on M5, where saved bytes are worth 2.2-2.6x less. r2 is packaging-only (no new GPU time): both submitted files are reverted so the PR is research-only (growth=0, files=142), and the deliverable is S10, the break-even exchange rate -- unpack ALU 212-219 us/step, k = 1 bit removed per weight per added in-loop integer op on M4 Pro and k in [0.94, 2.52] on M5, with the amortisation factor G deciding most arms. It closes S9.2, green-lights the o_proj row-base fold and the group-32 scale-plane arms, and explains why ae9ac90b won despite sitting at the same nominal rate.",
  "runs": [],
  "commit_sha": "cfbad24",
  "primary_metric": {
    "name": "same_host_paired_decode_ratio",
    "direction": "minimize",
    "baseline": 1.0,
    "candidate": 1.00905,
    "delta": 0.00905
  }
}
```

Gate ladder, answered in full: SANITY **PASS**; GO-8 **FAIL**; GO-12 **FAIL**;
GO-12e **PASS** (the firing gate); GO-13 **PASS**; T8 **FAIL**. See §2.
