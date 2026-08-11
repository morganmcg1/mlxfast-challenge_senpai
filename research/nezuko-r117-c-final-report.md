# R117-C — Final report: the attention scale plane is a byte floor

Student: maple-nezuko · PR #707 · assignment `maple-r117-c-attn-scale-plane-byte-floor`
Branch: `maple-nezuko/r117-attn-scale-plane-byte-floor`
Host: Apple M4 Pro, 20 GPU cores, 48 GiB. All levels are `--local-submit`, 1023 decode steps.

> **Read this first if you read nothing else.** The assignment asked me to shrink the
> attention NVFP4 scale plane from 8-bit to 5-bit or 6-bit codes and priced those at
> **+0.560 %** and **+0.374 %**. Both prices were computed against a **stock 8-bit plane
> that does not exist in this tree**. The narrow/pairwise/lane-major encoders shipped
> before this round already removed **66.38 MB/step (+2.37 %)**; the *surviving* plane is
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
| F7 | o_proj activation re-read geometry / `B_act` | <!--F7-STATUS--> | <!--F7-STATUS2--> |

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
| family time | **3123.5 µs/step** |
| achieved bandwidth | **236.0 GB/s = 91.9 % of 256.7 GB/s peak** |
| surviving scale plane | **24.02 MB/step = 3.26 %** |
| payload (irreducible) | **96.74 %** |
| already banked by shipped encoders | **66.38 MB/step = +2.37 %** |
| whole-plane-vanishes ceiling at τ=1 | **101.8 µs/step = +0.855 %** |

The family runs at **91.9 % of peak bandwidth**. There is no compute slack to trade against.

### 1.3 The span histogram kills the fallbacks

`research/nezuko-r117-attn-scale-span.py` → `research/data/nezuko-r117-attn-scale-span.json`,
139,264 rows, all 40 layers. Written up as the ADDENDUM at line 337 of
`research/nezuko-r117-stage0-attn-byte-floor.md`.

- ≤15 span eligibility: **96.0–99.2 %** ⇒ escape rate **1.0–4.0 %**
  (contrast: edward's routed-expert planes escape at 0.02–0.16 % — routed and attention
  planes are **not** the same statistical object, and the assignment treated them as one)
- break-even escape rate: **7.7–7.8 %**

Therefore **b=4 is the family optimum, b=3 is negative, and b=5 / b=6 — the assignment's two
fallbacks — ADD bytes** relative to the shipped pairwise-nibble encoding, because the shipped
encoder already spends 4 bits/group and the escape tail is far below break-even.

### 1.4 The arithmetic that closes it

Even under the *maximally generous* counterfactual — the entire surviving plane vanishing, no
escape list, no addressing cost — the ceiling is **+0.855 % at τ=1** and **+0.667 % at the
measured τ=0.780**.

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
| τ restated at achieved 235.6 GB/s | +0.850 | — |
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

## 5. F7 — o_proj activation re-read geometry

<!--F7-BODY-->

---

## 6. What I did not do, and why

- **I did not build a 5-bit or 6-bit encoder.** §1.3 shows both add bytes against the shipped
  plane. Building one to measure a known-negative would have burned the round.
- **I did not touch edward's territory.** K1/K4, `lagunaLaneMajorNVFP4ScaleBank`,
  `lagunaHalvedGroup32ScalePlane` are his (#704). All my source work is in a new file,
  `Sources/MLXFastModel/LagunaOProjGeometry.swift`, plus anchored edits in
  `LagunaRuntimeModel.swift` that are inert at default gate values.
- **I did not stop the ladder early.** Block counts were pre-registered
  (`research/nezuko-r117-oproj-geometry-preregistration.md`, amendments 9/10/11 timestamped
  before each launch) and run to completion.
- **The prefill view `lagunaPackedPrefillScaleView` is untouched and bit-identical.**

## 7. Reproduction

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
