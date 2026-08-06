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

On the ranked M5 Max the same 25.14 MB is worth only `25.141e6/610e9` =
**41.2 us**, because higher bandwidth makes each saved byte *cheaper*, not
dearer. For the mechanism to break even on M5 the unpack cost must fall from
219.6 us to <=41.2 us — a **5.3x** improvement in ALU throughput per unit of
memory bandwidth relative to M4 Pro. M5 Max has more GPU cores, but its
bandwidth rises ~2.4x at the same time, so the ALU:bandwidth ratio does not
move anything like 5.3x in the required direction.

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
- On M5 the saving is `18.8e6/610e9` = ~31 us against ~122 us of ALU, needing
  a 4x ALU improvement.

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

```bash
# census
python3 research/nezuko_dense_census.py all

# certificate (single run, traced)
DARKBLOOM_TRACE_FUSION=1 DARKBLOOM_DENSE_PACKED_VERIFY=1 ./benchmark.sh --local-iterate

# timing campaign A (12 paired runs, ~40 min)
bash research/maple-nezuko-pr85/run-campaign-a.sh

# analysis
cd research/maple-nezuko-pr85 && python3 analyze.py a

# kill switch
DARKBLOOM_DENSE_PACKED=0 ./benchmark.sh --local-iterate
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

**Downgraded, and I would not run it either.** It attacks stream count, not the
term that lost. §6.5 puts the unpack ALU at ≈ 219.6 µs against ≈ 100.6 µs of
bandwidth bought (≈ 41.2 µs on M5); byte-unaligned extraction *adds* shift and
mask work, so the most optimistic reading is that it trades a little load-issue
pressure for a little more ALU on the side of the ledger that is already 2.2×
over. This is only worth revisiting if someone first shows the unpack can be
made ~5× cheaper, in which case the stream count becomes the next thing to fix
rather than the first.

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
25.14 MB/step at a cost of ≈ 219.6 µs of unpack ALU. Any future
bytes-for-arithmetic trade in this runtime can be screened against that number
before anyone writes a kernel. Concretely, a decode-path unpack scheme is only
worth building if it costs under ~4 integer ops per weight *and* saves more than
~25 % of its plane — and on the ranked M5, where saved bytes are worth 2.4×
less, the ALU budget is roughly **5× tighter still**. §6.6 shows that test
correctly rejecting P13 without a run. I would rather the programme keep that
constant than keep this kernel.
