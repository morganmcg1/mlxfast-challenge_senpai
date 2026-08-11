# R117-C — Final report: the attention scale plane is a byte floor

Student: maple-nezuko · PR #707 · assignment `maple-r117-c-attn-scale-plane-byte-floor`
Branch: `maple-nezuko/r117-attn-scale-plane-byte-floor`
Host: Apple M4 Pro, 20 GPU cores, 48 GiB. All levels are `--local-submit`, 1023 decode steps.

> **Read this first if you read nothing else.** The assignment asked me to shrink the
> attention NVFP4 scale plane from 8-bit to 5-bit or 6-bit codes and priced those at
> **+0.560 %** and **+0.374 %**. Both prices were computed against a **stock 8-bit plane
> that does not exist in this tree**. The narrow/pairwise/lane-major encoders shipped
> before this round already removed **66.38 MB/step (+2.16 % at τ=1)**; the *surviving* plane is
> **24.02 MB/step = 3.26 %** of family traffic. Against the surviving plane, 5-bit and
> 6-bit codes **ADD** bytes. The correct entries in the ledger are **negative**.
> Everything below is the evidence for that, plus the reusable instrument I built to
> prove it and the three findings that fell out of it.

---

## 0. Findings index

| # | ID | Type | Status |
|---|---|---|---|
| F1 | `N-ATTN-BYTE-FLOOR` | negative, closes the assigned mechanism | proven |
| F2 | `N-ATTN-BYTE-DOSE-SUPERADDITIVE` | positive methodological, pricing correction | proven, CI excludes 0 |
| F3 | `N-EMPTY-DISPATCH-SPEEDUP-IS-CONFOUND` + OFFSET CLASS | negative, non-reproduction | proven (R114) |
| F4 | r94 decode-residue ledger byte overcount | correction to another student's artefact | proven, arithmetic |
| F5 | order artefacts land in the **intercept**, not the slope, on a rotation design | methodological | proven by self-test |
| F6 | byte→time transfer τ = **+0.780 [+0.727, +0.833]** (honest band [0.73, 1.08]) | reusable calibration | measured, 35 runs |
| F7 | o_proj geometry `rps 4→2`: **−79.4 µs/token = −0.885 % decode** | **positive, LANDED**; byte model falsified *by sign* (occupancy-limited, not bandwidth-limited) | proven, CI95 [−87.8, −71.1] excludes 0, 8/8 blocks, control covers 0 |
| F8 | `sliding_fused_attn_ring_v1` dispatches **32 threadgroups on 20 cores** | hand-off, static + profile evidence | proven by dispatch dump, unmeasured |

### 0b. Corrections log — things I published and then had to take back

Six of them. I am listing them together, in one place, because a campaign that only ever
publishes numbers that survive is a campaign that is not checking its own numbers.

| # | what was wrong | direction of the error | where |
|---|---|---|---|
| C1 | **Escape rows omitted from the byte census.** The first census counted only in-band scale bytes and missed the out-of-range escape entries. | the uncorrected version made the surviving plane look *smaller* (3.09 %) and so made my own finding look *stronger* than it was; correcting it grew the plane to **3.26 %**, i.e. **against me** | `nezuko-r117-stage0-attn-byte-floor.md` addendum |
| C2 | **τ restatement ratio inverted** (`×256.7/235.6` instead of `×235.6/256.7`), printing 0.850 for what is 0.716. | cosmetic in the report, but it seeded C3 | `nezuko-r117-ruler-tau.py`, fixed 05:03Z |
| C3 | **Peak-vs-achieved double-count in every ceiling.** The 24.02 MB/step plane was converted at the *achieved* 235.6 GB/s (101.8 µs/step) and then multiplied by a *peak*-scale τ. | inflated every ceiling by 1.090; **+0.855 %→+0.782 %** at τ=1, **+0.667 %→+0.610 %** at τ=0.780 | §1.4, §5.2 of the ruler doc, Amendment 13 |
| C4 | **"o_proj runs at 90.9 % of peak bandwidth, so there is headroom in its bytes."** The Stage-1 pre-flight falsified this *by sign*: removing 157 MB/step made o_proj **slower**, adding 944 MB/step made it **faster**. | this one was in the flattering direction — it was the premise of my own Stage-1 arm, and the data killed it | §5.2 |
| C5 | **"~150 affected o_proj calls per step"** — taken from an advisory critique I commissioned and repeated without checking. The true blast radius is **40 calls/step** (30 sliding @ 64 heads + 10 full @ 48 heads) at 6.3–8.4 MB each. | neutral for the headline number (the 314.6 MB ledger was always computed per-layer and is unchanged) but **strengthens** attribution: one kernel, not a diffuse family | §5.5 |
| C6 | **"the shipped geometry leaves 128 threadgroups and `rps=2` refills it to 256."** Off by exactly 2×. `tiles = outVec / (simdgroups × rowsPerSimdgroup)` = 2048/8 = **256** for the reference, **512** for `rps=2`. | against me in the sense that the reference is *less* starved than I claimed, so the occupancy story had to be re-argued on simdgroups-per-core rather than a bare threadgroup count | §5.4, §5.5 |

They do not all point the same way, which is the point. **C1 and C4 cut against me**: C1 made
the surviving plane bigger than I first claimed (more nominal headroom, so a weaker floor
argument), and C4 destroyed the premise of my own Stage-1 arm. **C3 cuts for me**: the ceiling
is lower than I published, so `N-ATTN-BYTE-FLOOR` is stronger than the version I first wrote
down. If I were only correcting errors that flattered me, C1 and C4 would not be on this list;
if I were only correcting errors that embarrassed me, C3 would not be.

The one number that never moved is the estimator output itself: **τ = +0.780 [+0.727, +0.833]**
is defined on the 256.7 GB/s peak scale (`BW=256.7`) and was correct as first published — the
raw per-observation array regenerated **bit-identically** after the C2/C3 fix, which is the
check that localises C2/C3 to the reporting layer rather than the fit.

---

## 1. Why the assigned mechanism cannot pay (F1)

### 1.1 The mechanism is already shipped

`Sources/MLXFastModel/LagunaRuntimeWeights.swift` (**not** `Sources/Laguna/`, which is where the
assignment pointed):

- `DARKBLOOM_ATTN_SCALE_NARROW` / `_QKV` / `_OPROJ` — lines 673–680, **default ON**
- `DARKBLOOM_ATTN_SCALE_PAIRWISE_QKV` / `_OPROJ` — **default ON**
- `DARKBLOOM_ATTN_SCALE_LANEMAJOR` — lines 702–722, **default ON**
- `lagunaLaneMajorNVFP4ScaleBank` at :886; `nibbleBytes` at :878 = `pairwise ? groups/4 : groups/2`

Kernel-name proof that these reach the GPU: `LagunaRuntimeModel.swift:4565–4585` (name literal
:4569), QKV at :4884 / :4900 / :4985, gates at :4986–4999 and :5675.

### 1.2 The escape-corrected census

Target family = `decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1` (1342.1 µs/step, 30 calls),
`oproj_act_h64_v1_lm1_pw1_sc1_se1` (1114.7, 30), `decode_nvfp4_qkv_h48` (363.5, 10),
`oproj_h48` (303.0, 10) = **3,123.3 µs/step = 36.5 %** of 8,567 µs decode busy.

| quantity | value |
|---|--:|
| family traffic | **737.1 MB/step** |
| family time | **3123.3 µs/step** (1342.1 + 1114.7 + 363.5 + 303.0) |
| achieved bandwidth | **236.0 GB/s = 91.9 % of 256.7 GB/s peak** (see note) |
| surviving scale plane | **24.02 MB/step = 3.26 %** |
| payload (irreducible) | **96.74 %** |
| already banked by shipped encoders | **66.38 MB/step = +2.16 %** (τ=1, C3-corrected; +1.69 % at τ=0.780) |
| whole-plane-vanishes ceiling at τ=1 | **93.6 µs/step = +0.782 %** |

The family runs at **91.9 % of peak bandwidth**. There is no compute slack to trade against.

> **Note (C4) — 236.0 vs 235.6 GB/s, and a mislabel I am correcting here.** Two
> achieved-bandwidth numbers appear across these documents. They are the *same* kernels over
> the *same* 3123.3 µs/step; only the byte total differs, because §0b's census was published
> twice:
>
> | | family bytes | ÷ 3123.3 µs | where |
> |---|--:|--:|---|
> | escape-free plane minimum | 735.8 MB/step | **235.58 → 235.6 GB/s** | `nezuko-r117-stage0-attn-byte-floor.md:115` |
> | escape-**corrected** plane (Finding 4) | 737.1 MB/step | **236.00 → 236.0 GB/s** | same doc `:398`, and the table above |
>
> 236.0 is the one to use: charging escaped rows at the stock plane is what pulls the census
> onto edward's atlas to +0.040 % / −0.003 %, against +0.08 % / +0.21 % before. The 0.18 %
> gap is well inside the per-kernel timing spread, so no conclusion turns on the choice.
>
> Two consequences worth stating rather than quietly absorbing. **(a)** The published plane
> time **101.8 µs/step** is `24.02 × 1000 / 236.0 = 101.78`; it is *not* `/235.6`, which gives
> 101.95. `nezuko-r117-stage0b-byte-dose-ruler.md:372` attributes it to 235.6 — that
> attribution is wrong by one rounding step and the number itself is right. **(b)** The C3
> correction factor is therefore **256.7/236.0 = 1.088**, not the 1.090 recorded in the C3 row
> of §0; on the τ=1 ceiling that is a 0.2 % relative shift, i.e. none of the reported digits
> move. And the ceilings themselves are immune either way: the τ=1 bound
> `24.02 × 1000 / 256.7 = 93.6 µs/step` is evaluated at **peak**, so it does not contain an
> achieved rate at all. That immunity is the whole point of the C3 fix — the bug was mixing
> the two scales, and the repair was to stop doing so, not to pick a better achieved number.

### 1.3 The span histogram kills the fallbacks

`research/nezuko-r117-attn-scale-span.py` → `research/data/nezuko-r117-attn-scale-span.json`,
139,264 rows, all 40 layers. Written up as the ADDENDUM at line 337 of
`research/nezuko-r117-stage0-attn-byte-floor.md`.

- ≤15 span eligibility: **96.0–99.2 %** ⇒ escape rate **0.8–4.0 %**
  (contrast: edward's routed-expert planes escape at 0.02–0.16 % — routed and attention
  planes are **not** the same statistical object, and the assignment treated them as one)
- break-even escape rate: **7.7–7.8 %**

Therefore **b=4 is the family optimum, b=3 is negative, and b=5 / b=6 — the assignment's two
fallbacks — ADD bytes** relative to the shipped pairwise-nibble encoding, because the shipped
encoder already spends 4 bits/group and the escape tail is far below break-even.

### 1.4 The arithmetic that closes it

Even under the *maximally generous* counterfactual — the entire surviving plane vanishing, no
escape list, no addressing cost — the ceiling is **+0.782 % at τ=1** and **+0.610 % at the
measured τ=0.780** (24.02 MB/step × 1000/256.7 = 93.57 µs/step at τ=1).

> **Self-correction, 05:03Z.** These two figures were first published as **+0.855 %** and
> **+0.667 %**, from a whole-plane bound of 101.8 µs/step. 101.8 is the plane converted at the
> family's *achieved* 235.6 GB/s; τ is measured against the *peak* 256.7 GB/s. Multiplying them
> double-counts the bandwidth shortfall and inflates every ceiling by 1.090. Corrected values are
> above; full derivation in `research/nezuko-r117-stage0b-byte-dose-ruler.md` §5.2. The error was
> in the conservative-for-me direction — the true ceiling is *lower*, so `N-ATTN-BYTE-FLOOR` is
> **stronger** than published — and the backwards numbers in the next table were computed on the
> peak scale throughout and **do not change**.

Backing out what a real encoder would have to deliver:

| to clear | needs (τ=0.780) | as % of surviving plane | needs (τ=0.968) | % of plane |
|---|--:|--:|--:|--:|
| the **+0.406 %** verified bar | 16.0 MB/step | **66.6 %** | 12.9 MB/step | 53.6 % |
| the **68.7 µs/step** rule-105.12 slot floor | 22.6 MB/step | **94.1 %** | 18.2 MB/step | 75.8 % |

An encoder that already spends 4 bits/group cannot remove two thirds of what remains. **F1 stands.**

---

## 2. The byte-dose ruler (F6, F2, F5)

I did not want to price F1 with an assumed byte→time transfer, so I measured one.

### 2.1 Design

Four dose rungs, produced by *disabling* shipped encoders so bytes go **up** by a known amount:

| arm | gates | dose MB/step | pred µs at τ=1 |
|---|---|--:|--:|
| `OP` | `PAIRWISE_OPROJ=0` | 9.830 | 38.29 |
| `ON` | `NARROW_OPROJ=0` | 29.409 | 114.57 |
| `QN` | `NARROW_QKV=0` | 36.966 | 144.00 |
| `AN` | both NARROW off | 66.375 | 258.57 |

`AN = ON + QN` exactly by construction, which is what makes the additivity test possible.

7 blocks × 5 arms = **35 runs**, position-balanced and interleaved. Job
`794c77a3-19a0-415c-acf7-e222ad1ecf27`, exit 0, tree `516afccd`.
**All 35 `passed=true`; all 35 golden hashes identical** (`f49e4c2cbc0d3ceee9…`).

### 2.2 Result

| quantity | value | CI95 |
|---|--:|---|
| **τ (primary, free-intercept OLS)** | **+0.780** | **[+0.727, +0.833]** (sd 0.057, n=7) |
| intercept c | −10.58 µs/step | [−24.16, +3.00] |
| bootstrap median τ (20 000 reps) | +0.776 | [+0.714, +0.826] |
| τ restated at achieved 235.6 GB/s | +0.716 | — (self-corrected 05:03Z, was +0.850) |
| *(rejected)* through-origin slope | +0.723 | — |

Per-block τ: 0.826, 0.804, 0.864, 0.709, 0.714, 0.768, 0.776.
The advisor's 02:42Z gate — **τ ≥ 0.6 with CI95 excluding 0.3** — **PASSES**; the interval also
excludes 0 and 1.0.

All 28 paired differences are positive. Raw array with per-run bit-exactness receipts:
**`research/data/nezuko-r117-byte-dose-ruler-array.csv`** (28 observations + header), as demanded
at 03:08:46Z. Full analyser output: `research/data/nezuko-r117-byte-dose-ruler-report.txt`.

### 2.3 The byte class is not a scalar

Intercept-removed per-rung τ_a:

| rung | τ_a | CI95 |
|---|--:|---|
| `OP` | +1.203 | [+0.999, +1.408] |
| `ON` | +0.648 | [+0.566, +0.731] |
| `QN` | +0.695 | [+0.613, +0.777] |
| `AN` | +0.823 | [+0.764, +0.882] |

**Non-overlapping.** A single scalar "bytes → µs" number is a fiction at this resolution; τ is a
family-and-mechanism-specific coefficient, and I report it as such.

### 2.4 F2 — superadditivity

`AN − (ON + QN)`: raw **+48.96 µs/step [+27.92, +70.00]**; **intercept-adjusted +38.38 µs/step
[+17.34, +59.42]**. Excludes zero.

**Corollary that matters for every future ledger entry on this family:** if byte *additions*
super-add, byte *savings* **sub**-add. Pricing a reduction at τ=0.78 is an **upper bound**, not a
point estimate. Two encoders that each save X do not save 2X here.

### 2.5 The confound I found *after* launch, reported loudly

No rung is a pure byte dose. `PAIRWISE_OPROJ=0` and `NARROW_*=0` also change the addressing and
kernel path, not only the byte count. That is almost certainly why `OP`'s τ_a exceeds 1.0 —
it is buying an addressing simplification on top of its bytes.

Dropping `OP` entirely: **τ = +0.968 [+0.860, +1.076]**, which covers 1.0.

I therefore quote an **honest headline band of τ ∈ [0.73, 1.08]** and price F1 at both ends
(§1.4). The conclusion is insensitive to the choice: even at τ=0.968 the required plane
reduction is 53.6 % / 75.8 %.

### 2.6 F5 — order artefacts land in the intercept

Order split: BEFORE n=14 τ=+0.874 c=−29.16; AFTER n=14 τ=+0.702 c=+1.61.
Δτ = −0.171 [−0.587, +0.011] (same sign, covers 0); Δc = +30.77 [−0.87, +72.70] (covers 0).
**No order artefact.**

Calibrated against the analyser's `--selftest-order` (a synthetic pure +15 µs/position drift,
τ_true = 0): the primary estimator reads τ = +0.052 [−0.132, +0.235] — correctly ~0 — while the
**half-slopes both come out positive (+0.175 / +0.226), so the conventional ABBA sign rule does
NOT fire**. What fires is the intercept: Δc = +67.42 [+57.88, +72.38].

**Methodological finding: on a rotation design, position drift is absorbed by the intercept, and
comparing half-slopes is the wrong diagnostic. Compare half-intercepts.** Applying that
calibration to the real data bounds drift at ≤ ~16 µs/position, point estimate ≈ 6.8.

Bimodality: none (p = 0.69 `OP`, 0.44 `ON`, 0.98 `QN`). Power against a 3-sd split at n=7 is only
**0.44** — stated rather than hidden.

### 2.7 Why free-intercept, and why the through-origin fit is rejected

This is the instrument-design point I most want on the record.

R114 (§3) established the **OFFSET CLASS**: on this harness an arm can shift the level by tens of
µs/step for reasons unrelated to its nominal mechanism. A through-origin fit forces that offset
into the slope. The analyser's `--selftest` proves the failure directly: on synthetic data with
τ_true = 0.75 and c_true = −40, the free-intercept estimator recovers **τ = +0.743
[+0.705, +0.781]** and **c = −38.70**, while the through-origin fit reads **+0.532** and the raw
per-rung ratios display **fake saturation** — exactly the artefact that would have made a
"diminishing returns" story look real.

So the through-origin number (+0.723) is reported for completeness and **rejected**, and the raw
ratio ladder is reported as a diagnostic only.

---

## 3. F3 — the R114 non-reproduction and the OFFSET CLASS

Reference level `C` = 8972.233 µs/token. All arms `passed=true`, golden `f49e4c2cbc0d3ceee9…`.

| arm | Δ µs/step | CI95 |
|---|--:|---|
| `S1` | −69.24 | [−85.27, −53.21] |
| `A1` | −43.14 | [−61.05, −25.23] |
| `L1` | −38.94 | [−62.51, −15.36] |

Three arms that should not have been fast were fast. `N-EMPTY-DISPATCH-SPEEDUP-IS-CONFOUND`:
removing work from a dispatch buys level shifts that are not attributable to the nominal
mechanism. This is what forced the free-intercept estimator in §2.7 and it is the reason I do not
trust any single-arm "it got faster" claim on this harness without a dose ladder behind it.

---

## 4. F4 — correction to the r94 decode-residue ledger

`research/maple-frieren-r94-decode-residue-ledger.md:176–182` back-solves bandwidth onto
`payload + stock plane`. The stock plane no longer exists (§1.1), so the denominator is inflated
by **+9.0–9.1 %**.

| as published (GB/s) | corrected (GB/s) |
|--:|--:|
| 272.1 | **249.7** |
| 269.9 | **247.6** |
| 262.6 | **240.8** |
| 245.2 | **224.8** |

This matters beyond bookkeeping: three of the four published figures exceed the 256.7 GB/s
hardware peak, which should have been caught as an impossibility. Written up as §0b-bis of
`research/nezuko-r117-stage0-attn-byte-floor.md`.

---

## 5. F7 — o_proj geometry: the byte model is falsified by sign

Stage 0 left exactly one unpinned term in the family, and it was not bytes. `o_proj` is
the geometric outlier of the decode GEMV pool: `results_per_simdgroup = 4`,
`num_simdgroups = 2`, so a 2048-row projection dispatches only **256 threadgroups** at
512 B/thread, against QKV's 5120 threadgroups at 32 B/thread — on a 20-core GPU.

### 5.1 The knob

New file `Sources/MLXFastModel/LagunaOProjGeometry.swift` (edward's territory untouched)
exposes `DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP ∈ {1,2,4,8,16}` (default 4 = shipped) and
`DARKBLOOM_OPROJ_SIMDGROUPS ∈ {2,4}` (default 2 = shipped), plus 12 anchored edits in
`LagunaRuntimeModel.swift` that are **inert at default gate values** — the kernel-name
suffix is empty at `rps=4, ns=2`, so every shipped name and every atlas string built
from it is unchanged. The suffix exists at all because of **rule 33**: MLX caches
compiled pipelines by function name, and a geometry sweep whose arms share one name
silently measures the first-built geometry every time.

**Bit-exact by construction**: changing `results_per_simdgroup` only decides *which*
simdgroup owns *which* output row. For a fixed row the accumulation is still 32 lanes ×
16 serial FP32 adds over the same K-block order, closed by the same `simd_sum`
(`LagunaRuntimeModel.swift:4348–4416`). Confirmed empirically — see 5.2.

### 5.2 Pre-flight (n=1 per arm, unpaired) — `research/data/nezuko-r117-stage1-preflight.tsv`

| arm | rps | ns | simdgroups | threadgroups | Δ act MB/step | µs/step | Δ vs C |
|---|--:|--:|--:|--:|--:|--:|--:|
| `C` | 4 | 2 | 512 | 256 | 0 | 8989.90 | 0 |
| `R1` | 1 | 2 | 2048 | 1024 | **+943.72** | 8924.73 | **−65.17** |
| `R8` | 8 | 2 | 256 | 128 | **−157.29** | 9090.93 | **+101.03** |
| `N4` | 4 | 4 | 512 | **128** | **0** | 9012.83 | **+22.93** |

**All four `passed=true`; exactly one distinct golden hash** (`f49e4c2cbc0d3ceee9…`).

Scope of that claim, stated precisely: the *tested* settings are `(rps,ns) ∈ {(4,2), (1,2),
(8,2), (4,4)}` at n=1 each here, plus **`(2,2)` at n=8 and `(4,2)` at n=8 in §5.4** — every
one of those 28 runs emits the same golden `f49e4c2cbc0d3ceee9…`. That is direct evidence
for five of the ten accepted `(rps, ns)` combinations, and it is the *shipping-relevant*
five. It is **not** a proof over the whole family: `rps=16` and `ns ∈ {1,8}` were never
built. The a-priori argument in `LagunaOProjGeometry.swift:15–20` — geometry only re-assigns
which simdgroup owns which output row, leaving the 32-lane × 16-value serial FP32 chain and
its closing `simd_sum` intact — is what covers the untested cells, and it is an argument,
not a measurement.

**The byte model is falsified by sign.** At the Stage 0b τ = 0.780 a pure byte model
predicts `R1` at **+2868 µs/step** and `R8` at **−478 µs/step**. Observed: **−65.2** and
**+101.0**. Both inverted. Adding 944 MB/step of activation re-reads made the model
*faster*; removing 157 MB/step made it *slower*.

The `N4` control does the attribution:

- `N4` vs `C` — same simdgroups, same bytes, half the threadgroups: **+22.9 µs**
  (byte-free packaging cost)
- `R8` vs `N4` — same threadgroups, half the simdgroups *and* 157 MB fewer:
  **+78.1 µs** (parallelism loss beats the byte saving outright)

**Correction to my own Stage 0 framing:** the "90.9 % / 83.4 % of peak" figures I
reported for the o_proj kernels are **not headroom a byte reduction can collect**. This
kernel is occupancy-limited, not bandwidth-limited.

### 5.3 `B_act` is not identifiable — and I am not laundering a bundled coefficient

Activation traffic here is *exactly* `simdgroups × in_vec_size × 2 × calls`, so bytes and
the parallelism knob are collinear with correlation **1.0** along the `ns=2` ladder. A
regression of Δ on bytes returns "bytes + parallelism, bundled", not `B_act` — the same
failure mode as the `OP` rung in §2.5. I pre-registered this limitation, and the
alternative fit, in `research/nezuko-r117-stage1-amendment12-identifiability.md`
**before the first paired observation existed** (committed 04:56:31Z; ladder launched
04:54:58Z; first run completed 04:57:30Z).

The two terms are separable only by *functional form* — bandwidth is linear in bytes,
occupancy saturates like `log2(simdgroups)` — so amendment 12 fits

```
delta_us = a * log2(sg/512) + tau_act * 3.8956 * (act_MB - 314.57)
```

on the `ns=2` arms, and **tests it out of sample**: fitted on the pre-flight singles
alone it gives `a = −135.3 µs/doubling`, `tau_act = +0.056`, and predicts the
never-yet-measured `R2` arm at **−66.8 µs/step**.

### 5.4 Ladder result (amendment 14: 3 arms × 8 blocks = 24 runs, pre-registered)

Raw array: `research/data/nezuko-r117-stage1-oproj-ladder-20260811T051314Z.tsv`
(24 rows, session `20260811T051314Z`, head `5082cd467bae`, ~198 s/run).
Analyser: `python3 research/maple-nezuko-r107j-paired-ci.py <tsv>`.

Three arms, blocked and interleaved, one `--local-submit` binary, env-gated:

| arm | gate | geometry | threadgroups | role |
|---|---|---|---|---|
| `C` | *(none)* | shipped `rps=4, ns=2` | 128 | reference |
| `G4` | `DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP=4` | `rps=4, ns=2` | 128 | **byte-identical A/A control** |
| `R2` | `DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP=2` | `rps=2, ns=2` | 256 | candidate |

`G4` sets the env var to the value the fallback already returns, so it compiles
and runs the *same* kernel as `C`. It is the negative control the campaign rule
demands: if its interval did not cover zero, the instrument would be measuring
the gate rather than the geometry.

**Per-arm levels (µs/token, census):**

| arm | n | mean | sd | cv% | passed | golden |
|---|---|---|---|---|---|---|
| `C` | 8 | 8971.868 | 4.014 | 0.045 | 8/8 | `f49e4c2c…` |
| `R2` | 8 | 8892.438 | 11.294 | 0.127 | 8/8 | `f49e4c2c…` |
| `G4` | 8 | 8963.509 | 27.957 | 0.312 | 8/8 | `f49e4c2c…` |

A **single golden hash across all 24 runs** and 0 correctness failures.

**Paired contrasts (marginal, reference `C`):**

| contrast | point | CI95 | covers 0 | sign-flip p | t |
|---|---|---|---|---|---|
| **`R2` − `C`** | **−79.431 µs/token** | **[−87.811, −71.050]** | **NO** | **0.0078** | −22.4 |
| `G4` − `C` (control) | −8.359 µs/token | [−33.267, +16.549] | **YES** | 0.727 | −0.79 |

`R2 − C` is **−0.885 % decode** [−0.979, −0.792], and **8/8 blocks are negative**.
`p = 0.0078` is the floor of the exact sign-flip test at n = 8 — the design cannot
produce a smaller number, so this is as strong as 8 blocks can be. Diagnostics:
prefill `d = +7.231 µs` CI95 [−8.608, +23.070] (neutral), position OLS slope
`−2.155 µs/position` CI95 [−9.036, +4.726] (no ordering confound).

The control's interval covers zero but is wide (±24.9 µs) because of one outlier:
`G4` block 4 read 8896.071 µs, ~68 µs below its other seven runs and the longest
wall clock in the array (167 s). Dropping it puts `G4 − C` at +1.86 µs. I am
**not** dropping it — it was not pre-registered as excludable — but I record that
the control passes both with it (p = 0.727) and without it, and that its presence
makes the `R2 − G4` contrast *conservative* (−67.3 µs) rather than flattering.
This is why `C`, not `G4`, is the reference: `C` is the ungated shipped path and
has sd 4.0 µs.

**Out-of-sample check.** Amendment 12 fitted the occupancy+bandwidth form on the
pre-flight singles *before* `R2` was ever run and predicted **−66.8 µs/step**.
Observed: **−79.4 µs**. Right sign, right order, ~19 % under-predicted. The
pre-registered prediction survives.

**The byte model is falsified by sign.** `R2` *adds* +314.6 MB/step of activation
re-reads and still wins. At 20 cores this kernel is occupancy-limited, not
bandwidth-limited; the shipped `rps=4` geometry dispatches **256 threadgroups /
512 simdgroups** per call and `rps=2` doubles that to **512 / 1024** (see the
corrected ledger in §5.5 — an earlier draft of this paragraph said 128→256 and
was wrong by 2×, correction **C6**). This is the same lesson as F8 stated from
the other direction, and it is why the assigned byte-floor mechanism (F1) could
not have paid even if the bytes had been there.

**Landed.** `Sources/MLXFastModel/LagunaOProjGeometry.swift` default `4 → 2`
(one character). The suffix predicate is deliberately left pinned to `rps==4`, so
the shipped default now emits the `_rps2ns2` function — the exact compiled
pipeline the `R2` arm measured, not merely the same source.

**Confirmation of the landed default**, ungated, no env vars, full gates
(`research/data/nezuko-r117-stage1-landed-default-verify.log`):
decode **8884.87 µs/token**, inside the `R2` range [8876.1, 8908.7] and below
*every one* of the eight `C` observations (min 8965.34); `passed_correctness:
true`, `passed: true`, golden `f49e4c2c…`, decode speedup 1.56×.

*(Local `prefill_speedup` is 0.326 and fails its floor here, but it does so
identically on the untouched `C` arm — this M4 Pro reports GPU generation 16 and
never selects the `_nax` prefill kernels. It is a host limitation, not a
regression, and prefill is not adjudicable on this machine at all.)*

**Transfer caveat, stated plainly.** This is a threadgroup-geometry change —
precisely the class `program.md` flags as M4→M5 fragile, with a prior case that
went +7.32 % on M4 and ~0.0 % on M5 through core-count quantisation. The
mechanism argues the win should survive or grow (the *shipped* `rps=4` reference
issues 512 simdgroups, i.e. 12.8 per core on a 40-core M5 against 25.6 here, so
the M5 default is *more* starved, not less), but `R2` also adds
+314.6 MB/step of activation traffic, which is a real cost that a wider machine
could price differently. **This must be settled by an official M5 run.** I could
not dispatch one: `senpai/submit-official.sh` refuses because my recorded
`BASE_SHA` differs from current `origin/main` across 27 submitted files (see
§7).

### 5.5 Static verification of the mechanism, at zero GPU cost

Before spending another GPU hour I established four things from the source alone.
Three of them narrow the risk; one is a correction against myself.

**(a) Blast radius is exactly the 40 decode `o_proj` calls.** Every consumer of
the knob is inside `lagunaGatedAffineOProjNVFP4*`; the only callers are
`LagunaRuntimeModel.swift:6388` and `:6404`. The dispatch guard requires
`attentionOutput.dims(1, 1, inVec)` — a **single token row** — so prefill (512
rows) structurally cannot enter. The neutral prefill diagnostic in §5.4
(+7.2 µs, CI covers zero) is therefore not evidence of a lucky wash; it is the
only result the code permits.

**(b) The dispatch geometry, from `LagunaOProjGeometry.swift:87,112` and the
grid call at `:4615`.** `tiles = outVec / (simdgroups × rowsPerSimdgroup)`,
`threads = 32 × simdgroups`, `grid = tiles × threads`, so threadgroups = tiles.
With `outVec = hiddenSize = 2048`:

| arm | rows/sg | sgs/tg | threadgroups | simdgroups | sgs/core @20 | sgs/core @40 |
|---|---|---|---|---|---|---|
| shipped-before (`rps=4`) | 4 | 2 | 256 | 512 | 25.6 | 12.8 |
| **landed (`rps=2`)** | 2 | 2 | **512** | **1024** | **51.2** | **25.6** |
| `rps=1` | 1 | 2 | 1024 | 2048 | 102.4 | 51.2 |
| `rps=2, ns=4` | 2 | 4 | 256 | 1024 | 51.2 | 25.6 |

This is correction **C6**: I had previously written 128→256. The right-hand
columns are the reason the transfer argument survives the correction — a 40-core
M5 running the *old* default sits at 12.8 simdgroups/core, i.e. one doubling
*below* the point where this ladder measured a gain.

**(c) The byte ledger reconciles exactly.** `inVec = heads × 128`; the pinned XS
schedule is 30 sliding layers @ 64 heads (inVec 8192) and 10 full-attention
layers @ 48 heads (inVec 6144). Each simdgroup re-reads the whole bf16
activation, so halving `rps` adds 512 simdgroups per call:
30 × 512 × 8192 × 2 B = 251.7 MB, plus 10 × 512 × 6144 × 2 B = 62.9 MB,
**= 314.6 MB/step**, matching `R2` exactly; `rps=1` gives 3× and `rps=8` gives
−0.5×, both matching. The re-read block is 12–16 KiB touched 1024 times, i.e.
cache-resident, so its marginal price is on-chip bandwidth, not DRAM — which is
why adding 314.6 MB of it costs less than the occupancy it buys.

**(d) The knob is architecture-independent.** `lagunaNAXAvailable`
(`LagunaRuntimeModel.swift:242`) is read *only* by
`lagunaExpertAlignedGatherEnabled` (MoE gather). No branch in the o_proj path
consults `GPU.deviceInfo().architecture`, and this is a runtime-compiled
`MLXFast` kernel rather than an AOT metallib variant, so there is no `_nax`
sibling that an M5 could select instead. The one failure mode that would
guarantee exactly 0.0 % on M5 — the F1/M4-as-M5 trap of tuning a path the ranked
machine never takes — is **statically excluded**. That is a bound on the
downside, not a prediction of the upside.

### 5.6 Why this is not the occupancy-tuning class the briefing warns about

The briefing is explicit (L293–294) that this QMV family is "predominantly
unique-byte bandwidth-bound" and that "fixed-byte instruction and occupancy
tuning has usually been neutral or negative", and (L503–504) to prefer exact
work removal over "cosmetic launch-count or occupancy changes". I take that
seriously; here is why I still think this one is different, and what would show
me wrong.

*The premise is measurable, and I measured it.* o_proj DRAM traffic is
30 × (8.389 + 1.049) + 10 × (6.291 + 0.786) = **354 MB/step**, which at this
host's 256.7 GB/s asymptote is ~1.38 ms of an 8.97 ms step. Stage 0 measured
this family running **9.1 % (h64) and 16.6 % (h48) below** that asymptote. So
the kernel is *not* saturated — the briefing's "bandwidth-bound, nothing left to
win" case is the case where that shortfall is ~0, and here it demonstrably is
not. The 79.4 µs Stage-1 win is **5.8 pp of that already-measured shortfall**,
leaving ~3–11 pp unclaimed. This is recovery of a quantified deficit, not a
cosmetic launch-count change.

*It is also not a repeat of the two prior o_proj negatives.* PR #607 staged 512
BF16 pre-activated gate products in threadgroup memory and **explicitly
preserved the geometry** (1.187 % slower). PR #643 replaced two scalar `uint32`
loads with one aligned `uint2` — a **load-width** change, geometry again
untouched (0.9967×). Neither moved rows-per-simdgroup or the threadgroup count,
and the briefing's "do not repeat unchanged" list (L415–432) contains attention
threadgroup *doubling*, split-K, KV splitting and generic depth sweeps, none of
which is this. I searched the briefing for a prior rows-per-simdgroup result and
there is none.

*The honest counterweight.* L228–230 says threadgroup geometry can change sign
across core counts, and that is exactly the risk I cannot retire on this host.
My defence is not that the briefing is wrong — it is that (i) the downside is
bounded by 5.5(d) away from the guaranteed-zero case, (ii) the direction of the
core-count change moves the M5 default *further into* the starved regime rather
than out of it, and (iii) L409–411 explicitly says a correctness-green candidate
need not be proven to exceed the whole gap on M4 before one official experiment.
This is a candidate for one M5 run, not a claim of a ranked win.

---

## 6. F8 — `sliding_fused_attn_ring_v1`: the threadgroup count, printed next to the null

The advisor asked me to treat this kernel as the biggest remaining headroom on the board
(610.0 µs/step cost, **373.4 µs/step headroom**, 38.8 % of peak, 30.3 calls/step,
20.13 µs/call, 2.131 MB/call — alphonse `maple-alphonse-r109e-qk-ceiling.md:1384`), and
alphonse's campaign law says to print the threadgroup count next to any null.

*One scale note on the imported row, so it is not silently mixed with mine:* alphonse's
"38.8 % of peak" is computed against a ~273 GB/s peak (2.131 MB ÷ 20.13 µs = 105.9 GB/s;
105.9 / 0.388 = 272.9). Every "% of peak" elsewhere in this report uses the 256.7 GB/s
asymptotic figure, on which the same row reads **41.2 % of peak** and **358.5 µs/step** of
nominal headroom rather than 373.4. I quote alphonse's numbers unchanged below because they
are his; the two scales differ by 6.3 % and must not be averaged.

I had no GPU budget left to run an arm on it, so this section is a **hand-off**: static facts, an
independent profile confirmation, and one named, falsifiable lever. It is not a measurement
of a candidate and it is not claimed as one.

### 6.1 The dispatch geometry — measured, not inferred

`LagunaRuntimeModel.swift:1970-1971` dispatches

```
grid:        ((heads / 2) * 1024, 1, 1)   // heads = 64  ->  32768
threadGroup: (1024, 1, 1)
```

with `LagunaConstants.slidingAttentionHeads = 64` (`LagunaConfig.swift:26`). That is

| quantity | value |
|---|---|
| threadgroups per dispatch | **32** |
| threads per threadgroup | 1024 (= 32 simdgroups) |
| GPU cores on this host | **20** |
| waves | 32 / 20 = **1.60** |

Independently confirmed from a profile dump I did not produce — maple-frieren's
`research/artifacts/fern-r106g/dispatch_raw.tsv:10610` records this dispatch as
`threads 32768x1x1`, `threadgroup 1024x1x1`. 32768 / 1024 = 32.

**So, stated in the form alphonse's third cell requires: 32 threadgroups ≥ 20 cores, therefore
this kernel is NOT an absorption candidate.** It does not launch fewer threadgroups than the
machine has cores. Whatever is costing 373.4 µs/step here, it is not thread starvation of the
kind that cell is designed to catch.

**Caveat, stated because it is load-bearing and I do not want it read as universal:** this
verdict is evaluated **on this 20-core M4 Pro host**. The third cell is a *core-count*
comparison, so its sign — and the 80 % wave-efficiency figure and the 122 µs/step bound in
§6.3 — must be re-stated for the ranked machine before anyone uses this section to close the
lever. On a machine with more than 32 cores the same dispatch *is* an absorption candidate.

### 6.2 What the byte axis can and cannot say here

The atlas `MB/call = 2.131` is a **static unique-buffer footprint**, not a measured DRAM
counter — it is reproduced to 0.2 % by summing the buffer list in that same dispatch dump
(16384 + 2048 + 2048 + 256 + 256 + 512 + 1048576 + 1048576 + 4 + 4 + 16384 = 2,135,048 B).
So "38.8 % of peak" must not be read as "the kernel moves its bytes at 38.8 % efficiency";
that would be circular. The honest statement needs the *logical* traffic:

- `kv_head = head0 / gqa` with `gqa = 8` and 2 heads per threadgroup ⇒ **4 threadgroups share
  each kv_head**, and each of them walks all 512 window positions (`i = sg`, stride `4*BN`,
  4 iterations ⇒ 32 simdgroups × 16 positions = 512).
- Each threadgroup therefore reads 128 KiB of K and 128 KiB of V. Logical total
  = 32 × 256 KiB = **8.39 MB/call**, against a 2.10 MB unique KV footprint: a **4× logical
  re-read**.
- But 20.13 µs/call at the 256.7 GB/s peak admits at most **5.17 MB/call** of real DRAM
  traffic. Since 8.39 > 5.17, **at least 38 % of the logical re-read is already being served
  from cache**; the effective redundancy factor is bounded above by **2.46×**
  (5.17 MB admissible ÷ 2.097 MB unique).

That bound is the useful part: it says a "stop re-reading KV" rewrite has at most ~2.4× of
2.10 MB to win back, and the obvious way to get it — one threadgroup per kv_head, so 8
threadgroups — would drop the launch to **8 threadgroups on 20 cores** and walk straight into
the absorption cell from the wrong side. That trade is not worth taking.

### 6.3 The two structural causes that are visible in the source

**(a) Wave quantisation.** 32 tiles on 20 cores costs two wave-times to do 1.60 waves of work:
wave efficiency `tiles / (20 * ceil(tiles/20))` = 32/40 = **80 %**. An upper bound on what
perfect packing could return is `610.0 * (1 - 0.80)` = **122 µs/step**. Retiling by heads
alone cannot fix it — the tile count is `64 / heads_per_tg`, always a power of two, and no
power of two is a multiple of 20 (1 head/TG gives 64/80 = 80 %, the same number). Getting to
100 % needs a tile count that is a multiple of 20, which requires splitting the *window*
dimension into unequal chunks (e.g. 160 tiles = 32 head-pairs × 5 window ranges of 102/103)
plus a cross-tile softmax combine. Real, but a rewrite, not a knob.

**(b) A barrier that is stronger than the data dependence.** The preamble
(`LagunaRuntimeModel.swift:1533-1578`) runs on `sg < 3` (RMS-norm → `simd_sum` → `rsqrt` →
`simd_shuffle` → RoPE) and `sg == 3` (V staging), then `sg == 0` writes the new K/V into the
ring at `widx`, then `threadgroup_barrier`. **28 of 32 simdgroups (87.5 %) do nothing but wait**,
and they wait through a long *dependent scalar* chain, so the memory pipe is idle for its
duration.

They do not have to. The main loop's addresses (`:1608-1613`) are
`k_cache + kv_head*(window*head_dim) + sg*head_dim + lane*qk_per_thread` — functions of
`kv_head`, `sg`, `lane` only, all known at kernel entry. The *only* slot the preamble mutates
is `widx`, and the loop already special-cases exactly that slot: `T_LOAD_K`/`T_LOAD_V`
(`:1884-1918`) take the value from threadgroup memory `tg_k`/`tg_v` when
`substitute` is true and issue a plain `device vec<bfloat,4>` load otherwise, with
`sub_a..sub_d = (uint(i + kBN) == widx)` and `widx = params[0]` available immediately.

⇒ **The first pipeline stage's device K/V loads, for all 511 non-`widx` positions, are provably
independent of the barrier and can be hoisted above it.** That overlaps 28/32 simdgroups'
memory issue with the preamble's dependent chain instead of serialising behind it. It is a
pure reordering: the substitute path is untouched, so the `widx` race the barrier exists to
prevent is still prevented by the same mechanism that prevents it today.

### 6.4 Why I am handing this off rather than doing it

`LagunaRuntimeModel.swift:1507-1975` is **edward's region** (#704). I did not edit a line of
it; everything above is read-only analysis. The lever in 6.3(b) is a ~20-line change inside a
kernel string and is exactly the kind of thing that should be certified with a gated arm and
a byte-identical control, which is the instrument in `research/maple-nezuko-r107j-certify.sh`
and is free for anyone to reuse. Predicted sign: negative (faster). Predicted size: I will not
guess one, because 6.2 shows I cannot price it from bytes, and F7 (§5) shows that on this
machine an occupancy-limited kernel does not obey the byte model at all.

## 7. What I did not do, and why

- **I did not build a 5-bit or 6-bit encoder.** §1.3 shows both add bytes against the shipped
  plane. Building one to measure a known-negative would have burned the round.
- **I did not touch edward's territory.** K1/K4, `lagunaLaneMajorNVFP4ScaleBank`,
  `lagunaHalvedGroup32ScalePlane` are his (#704). All my source work is in a new file,
  `Sources/MLXFastModel/LagunaOProjGeometry.swift`, plus anchored edits in
  `LagunaRuntimeModel.swift` that are inert at default gate values.
- **I did not stop a ladder early to pick a number.** Block counts were pre-registered
  (`research/nezuko-r117-oproj-geometry-preregistration.md`, amendments 9/10/11 timestamped
  before each launch). One qualification, recorded because it matters: the first Stage-1
  ladder (5 arms × 5 blocks) was **killed by the runtime after block 1**, not by me and not
  because of what block 1 said. I did not analyse block 1 as if it were the campaign; I
  re-registered a better design (amendment 14, §5.4) and re-ran it. Only 4 of that ladder's
  25 runs completed (the `N4` arm never ran at all). Those four rows are preserved verbatim,
  unpooled, in `research/data/nezuko-r117-stage1-ladder-block1-killed.tsv` and quoted in
  amendment 14 of `research/nezuko-r117-oproj-geometry-preregistration.md`, so the decision
  to discard rather than pool them can be audited. They are **not** combined with the
  replacement ladder anywhere.
- **The prefill view `lagunaPackedPrefillScaleView` is untouched and bit-identical.**

## 8. Reproduction

```
research/maple-nezuko-r107j-certify.sh --blocks 7 \
  C: OP:DARKBLOOM_ATTN_SCALE_PAIRWISE_OPROJ=0 \
  ON:DARKBLOOM_ATTN_SCALE_NARROW_OPROJ=0 \
  QN:DARKBLOOM_ATTN_SCALE_NARROW_QKV=0 \
  AN:DARKBLOOM_ATTN_SCALE_NARROW_OPROJ=0,DARKBLOOM_ATTN_SCALE_NARROW_QKV=0

python3 research/nezuko-r117-ruler-tau.py <tsv> \
  --csv research/data/nezuko-r117-byte-dose-ruler-array.csv

python3 research/nezuko-r117-ruler-tau.py --selftest        # estimator validation
python3 research/nezuko-r117-ruler-tau.py --selftest-order  # F5 calibration
```
