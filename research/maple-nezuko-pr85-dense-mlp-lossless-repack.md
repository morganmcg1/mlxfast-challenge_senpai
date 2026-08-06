# PR #85 — Dense MLP lossless BF16 repack

Assignment `maple-2026-08-06g-dense-mlp-lossless-repack`, revision `r1`.
Student: maple-nezuko. Base `f2fedd584e6514569758d79e581402210306e77b`.

**Hypothesis.** The layer-0 dense MLP moves 100.66 MB of BF16 weight per decode
step and both of its kernels already sit at 96–97 % of this host's memory
ceiling. If those planes can be re-encoded to fewer bytes *without changing a
single emitted BF16 bit pattern*, decode time should fall in proportion to the
bytes removed.

**Result headline.** The encoding works and is provably lossless — 25.14 MB
removed per step, 0 mismatching bit patterns over 50,331,648 weights, end-to-end
`max_abs_diff: 0`. The timing verdict is in §6.

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

## 6. Timing

<!-- FILLED IN AFTER CAMPAIGN A -->

---

## 7. Controls and limitations

### 7.1 Host is not the ranked host

Every number in §6 comes from an AWS **M4 Pro** (`applegpu_g16s`, 48 GiB, Apple
GPU generation 16, low-memory startup profile, ~250 GB/s effective, idles at
~40.3 °C against a 40 °C cool gate). The ranked host is an **M5 Max** with
128 GB. This box does not select `_nax` kernels at all.

For *this* experiment the cross-machine risk is unusually structured, and cuts
in a specific direction: the mechanism trades **bytes for integer ALU work**
(roughly 9 extra integer ops per weight to unpack). Whether that trade wins
depends entirely on the host's bytes-per-ALU-op balance. An M4 Pro at ~250 GB/s
with fewer GPU cores is *more* likely to be ALU-limited than an M5 Max. So a
null or negative result here is **weaker** evidence against the mechanism on M5
than a positive result here would have been for it.

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

<!-- FILLED IN AFTER CAMPAIGN A -->
