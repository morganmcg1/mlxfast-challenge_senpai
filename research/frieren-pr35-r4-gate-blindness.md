# PR #35 r4 — coherent-addressing blindness of the correctness gate

Student `maple-frieren`, assignment `maple-2026-08-04j-scale-code-width`,
branch `maple-frieren/scale-code-width`.

> **Erratum (r5).** Five `LagunaRuntimeModel.swift` line citations in this
> document were wrong and are corrected in place: the `lagunaDecodeNVFP4QKVR1`
> call site `:5907`→**`:5858`**, `prepareFusedRuntimeWeights()`
> `:11302`→**`:11211`**, `prepareNativeAffineQKVWeight()` `:5683`→**`:5592`**,
> the `fused.laneMajorScales` assignment `:5755`→**`:5664`**, and the
> lane-major guard `:5003`→**`:4921`**. These were **not** commit drift: checked
> against this document's own commit `5baec67f`, `:5683` was already
> `guard _fusedQKVWeight == nil,`, `:5003` was `constexpr uint real_threads = 64;`
> and `:5907` was `affineGate.packedCodes,`. They were mis-transcribed when
> written. `LagunaRuntimeWeights.swift:637` was correct.
>
> Every **conclusion** below was re-verified symbolically at r5 and stands. But
> the defect is worth naming: unreliable citation is the same carelessness that
> produced the vacuous r4 gate this document reports on. The r5-A certificate
> ([`frieren-pr35-r5a-certificate.md`](frieren-pr35-r5a-certificate.md)) replaces
> that gate with a measured one.

The submission surface (`Sources/` + `Vendor/`) is
`b3319dfb5c13d7c3c669424139d50acaac044f70` and is untouched by this document:
`git diff --stat b3319dfb5c13d7c3c669424139d50acaac044f70 HEAD -- Sources/
Vendor/` is empty, and the only files this and the following research commits
add or modify are under `research/`. Every timing number attributed to
`b3319dfb` therefore stands unchanged at `HEAD`. All SHAs quoted here were
resolved with `git rev-parse --disambiguate` / `git cat-file -t` rather than
copied from prose — the prefix `b3319dfb` resolves to `…5c13…`, not the
`…fc13…` that an earlier draft of my own notes carried.

All evidence in this document is local harness output on `Mac16,11` / 48 GiB /
macOS 26.5.2. There are no W&B runs for this arm; every number below is
reproducible with the commands in [§7](#7-reproduction).

## 0. Why this document exists

Two independent ranked arms have now shipped a *faulted* kernel through the
public correctness gate and come back with `max_abs_diff 0`:

* fern's faulted run (advisor r4 note), and
* my own mode-5 lane-code reversal, silent over 1025 teacher-forced steps
  (`research/frieren-pr35-r3-b-verification.md`).

The advisor's reading is that "the gate's blindness is coherence, not
magnitude". This document tests that claim directly, and reports the three r4
deliverables: the one-hot flag rate, the exact silent subspace, and the
constant-quadruple fraction.

Two candidate explanations had to be separated:

1. **Null perturbation.** The fault did not actually change any reconstructed
   scale, so the gate had nothing to see. Under this reading the gate is fine.
2. **Coherent blindness.** The fault changed many reconstructed scales, but
   coherently — every row displaced by the same amount — and the greedy argmax
   survived. Under this reading the gate has a real, structured blind spot.

The census in [§2](#2-census-of-the-decode-qkv-scale-plane) kills (1) for mode 5.
Explanation (2) is **not** what the evidence supports either: the sweep in
[§4](#4-the-one-hot-coherent-addressing-sweep) and probe 132 in
[§3.4](#34-what-probes-128-and-131-do-not-establish) show the gate is equally
silent when the displacement is made *incoherent* at matched magnitude and
matched fault count, so "coherence" is the wrong axis. The supported claim is
weaker in structure and broader in scope: on this golden, over 64 teacher-forced
steps, the gate does not react to a displacement-class scale fault of the §2.6
magnitude at all.

### 0.1 Headline results

| r4 deliverable | Result |
| --- | --- |
| One-hot flag rate | **0 / 128 = 0.0 %** (§4.2) |
| Exact silent subspace | the **entire** index space; 64 odd `L` are informative (72.08–75.40 % of rows faulted each, all silent), 63 even `L ≥ 2` are structurally null, `L = 0` is near-null (§4.2) |
| Constant-quadruple fraction | **537,269 / 12,373,312 = 4.3422 %** (§2.4) — so mode 5 was non-null in 95.66 % of lane words; explanation (1) is dead |
| Probe 132 (coherence discriminator) | **silent** — coherence is not the blind axis (§3.4) |
| Exact perturbation magnitude | **23.11 % mean / 32.66 % RMS** relative scale error on odd groups; 31.67 % / 38.23 % conditional on changing (§2.6) |
| Dispatch decision under the r4 rule | **stop and post.** "Every probe flags" is unsatisfiable by construction *and* empirically 0/128 (§4.1, §4.2) |

Three findings that were not on the r4 assignment and correct standing programme
beliefs:

1. **`max_abs_diff` is a hardcoded literal `0`** at every construction site and
   is computed nowhere (§3.3). Every "bit-exact, `max_abs_diff 0`" claim in this
   programme, including my own r3 claim and the r4 assignment's reasoning, rests
   on a constant.
2. **`LagunaUpstreamEquivalence` never builds the prepared decode layouts**
   (§3.5), so a green oracle run is vacuous for this arm and for every
   `DARKBLOOM_FUSED_*` / native-affine layout on the frontier.
3. **An exhaustive fail-closed reconstruction certificate over all 49,807,360
   plane entries already ships** in `lagunaLaneMajorNVFP4ScaleBank` (§3.6), which
   is why the gate probes measure the gate rather than the arm.

## 1. Kernel reachability (prerequisite)

A silence result is worthless unless the faulted kernel actually runs on the
checked decode steps. Established, in order:

| Evidence | Result |
| --- | --- |
| Call-site census | `lagunaDecodeNVFP4QKVR1` has exactly one caller, `Sources/MLXFastModel/LagunaRuntimeModel.swift:5858`, inside the `lagunaFusedQKVProjectionEnabled && B == 1 && L == 1` decode block. `fusedQKV` is `nil` for the NVFP4 group-16 bank (it only fires for `.affine` 8/32), so `decodeNVFP4QKVR1` *is* the `qkv` path. |
| Probe 129 (`fatalError` on first lane-major dispatch) | Aborted: `LM_PROBE_REACH: lane-major decode QKV dispatched h48`. Branch reached. |
| Probe 130 (`fatalError` at dispatch #2000) | Aborted: `... dispatch #2000 h64`. At least 2000 lane-major dispatches occur inside the gated region; warmup alone does not plausibly reach that count. |

Both head-count specialisations dispatch, because the tower is mixed:
`LagunaConfig.swift` gives `hiddenSize 2048`, `numKeyValueHeads 8`,
`headDim 128`, `fullAttentionHeads 48`, `slidingAttentionHeads 64`. Fused QKV
bank rows are therefore 8192 for a full-attention layer and 10240 for a sliding
layer, and the census row histogram is exactly `{8192: 10, 10240: 30}` — 10 full
and 30 sliding layers, 389,120 rows total. (An earlier r3 note claimed all 40
layers had 8192 rows; that was wrong, only the 10 full-attention layers do.)

A separate and important operational finding: **worker stderr is captured into
the harness JSON `error` field.** `lagunaTrace` / `note()` output such as
`mlxfast: narrow-scales built lane-major: qkv` is observable there. This
supersedes the earlier belief that worker stderr was unavailable, and is how the
probe assertions above were read.

## 2. Census of the decode QKV scale plane

Instrument: `lagunaLaneMajorCensus(plane:fits:rows:groups:site:layer:)` in
`Sources/MLXFastModel/LagunaRuntimeWeights.swift`, called from
`lagunaLaneMajorNVFP4ScaleBank` immediately after `let fits = span .<= 15`,
guarded on `groups == 128`, output path from `DARKBLOOM_LM_CENSUS`. Raw data:
`/tmp/pr35_lm_census.csv`, 5,160 records = 40 layers × (1 `quad` + 128 `disp`).
Aggregation script: `research/frieren_pr35_census_agg.py`.

### 2.1 Shape

| Quantity | Value |
| --- | --- |
| Layers instrumented (site `qkv`) | 40 |
| Bank rows | 389,120 (`8192 × 10 + 10240 × 30`) |
| Groups per row | 128 (group-16 over 2048 inputs) |
| Scale-plane entries | 49,807,360 |
| Fitting rows (`span ≤ 15`) | 386,666 |
| Escaped rows (`span > 15`) | 2,454 = **0.6307 %** |

### 2.2 The plane is pairwise constant — effective granularity is group-32

`disp[g]` counts rows where `code[g] != code[(g+1) & 127]`.

| Group class | `disp` | Fraction of 389,120 rows |
| --- | --- | --- |
| even `g`, 2 ≤ g ≤ 126 (63 groups) | **exactly 0** | 0 |
| `g = 0` | 89 | 0.0229 % |
| all 64 odd `g` | 280,494 (min, g=87) … 293,382 (max, g=9) | **72.08 % … 75.40 %** |

The zero set is identical in the fitting arm and over all rows. No odd `g` is
anywhere near zero.

This is a structural discovery independent of the correctness question: the
group-16 NVFP4 scale plane of the fused QKV bank is **pairwise constant**, so its
effective granularity is group-32. That is a further 2× compression of the scale
plane on top of deliverable B, and it is reported as a follow-up, not
implemented here.

### 2.3 A whole-plane rotation is not a null perturbation

Summing `disp` over all `g`: 18,176,949 displaced entries of 49,807,360, i.e. a
whole-plane `g → g+1` rotation changes the reconstructed scale of **36.49 %** of
all plane entries (36.45 % restricted to fitting rows). Mode 128 in
[§3](#3-controls-the-gate-does-see-this-kernel) is that rotation.

### 2.4 Constant-quadruple fraction (r4 deliverable 3)

Mode 5 reversed the four codes a lane packs into one `ushort`, i.e. the
quadruple `{l, l+32, l+64, l+96}`. It is a null perturbation only where that
quadruple is constant.

| Quantity | Value |
| --- | --- |
| Lane words examined (fitting rows × 32 lanes) | 12,373,312 |
| Constant quadruples | 537,269 |
| **Constant-quadruple fraction** | **0.043422 = 4.3422 %** |
| Per-layer range | 2.73 % … 13.33 % |
| Per-layer, first 8 layers | 0.0903, 0.1063, 0.0412, 0.0357, 0.0425, 0.1333, 0.0634, 0.0310 |

**Mode 5 was non-null in 95.66 % of lane words.** The advisor's alternative
hypothesis — that mode 5 was silent because it did nothing — is refuted. What
its 1025-step run actually established is narrower than r3 claimed, because
`max_abs_diff` is not a measurement at all (§3.3).

### 2.5 How large is one code step? A mantissa step, not an octave

Every claim about "how big" an addressing fault is depends on what one unit of
the 4-bit code is worth in the value domain. The scale codes are **uint8 E4M3**,
not E8M0:

- `Sources/MLXFastModel/LagunaConfig.swift:41` — "NVFP4-packed, with one E4M3
  scale per group of 16 values."
- `Sources/MLXFastModel/LagunaRuntimeWeights.swift:721` and `:823` — both narrow
  banks hold "the same uint8 E4M3 scale codes as a stock NVFP4 scale plane."
- The nibble is a *linear byte-pattern offset* from a per-row base
  (`sb[b] = row_base + nibble`), so one code step is one E4M3 byte-pattern step.
- The dequantization arithmetic is explicit and is bias-7 E4M3:
  `as_type<half>((bits & 127) << 7) * 256`
  (`Vendor/mlx-swift/.../kernels/fp8.h:32-37`, runtime twin
  `laguna_nvfp4_scale` at `LagunaRuntimeModel.swift:6872`). `group_size == 16`
  is what selects `fp8_e4m3` in the first place
  (`Vendor/.../kernels/fp_quantized.h:31-38`, `fp_quantized_nax.h:47`, and the
  `mlx-generated` twin), and `LagunaConfig.swift:42-49` pins group 16 / nvfp4.

E4M3 has 3 mantissa bits, so 8 byte patterns span one octave and one step in the
**normal** range (`code ≥ 8`) is a mantissa step of
**×1.0667 … ×1.125 (6.7 % … 12.5 %)**. The in-tree whole-checkpoint census at
`LagunaRuntimeModel.swift:4050-4062` corroborates the scale independently: over
all 234 U8 scale tensors (1,970,601,984 bytes) the bytes measured **min 1, max
73**, and this decode maps byte 1 to `2^-9` and byte 73 (exp 9, mant 1) to `4.5`
— 11.2 octaves across 72 code steps, i.e. 6.4 codes per octave. Under E8M0 the
same range would span 72 octaves with every magnitude below `5.6e-17`, which is
impossible for a real weight tensor, so the encoding question is settled.

That `1 … 73` range is the union over *all* 234 scale tensors on disk. The
runtime-derived fused-QKV plane that deliverable B actually re-encodes is
narrower: 36 distinct codes, `0 … 35` (§2.6).

Two caveats on the wording, both material:

- **Codes 1…7 are subnormal** (`value = code · 2^-9`) and step *additively*, so
  `1 → 2` is exactly `×2`. The checkpoint does contain code 1. The `×1.0667 …
  ×1.125` figure therefore holds only above the subnormal boundary, and the
  aggregate relative error has to be measured rather than assumed — which is why
  the census emits exact per-entry ratios (§2.6) instead of a `2^(Δ/8)`
  approximation.
- **"No sign bit" is a property of this checkpoint's data, not of E4M3.** The
  format has a sign bit; the census measured it as zero in every scale byte.

Two consequences, and the second one cuts against this document's own thesis:

1. A row's `span ≤ 15` fitting condition is a **1.9-octave** dynamic-range
   window, which is why 99.37 % of rows fit (§2.1). That is a property of the
   representation, not a lucky draw.
2. ~~**The whole-plane rotation of probe 128 is a much smaller perturbation than
   the octave reading implies.** Under E4M3 the per-entry error is a few mantissa
   steps.~~ **Withdrawn — §2.6 measured this and it is false.** 80.31 % of the
   plane's codes are E4M3 *subnormals*, where the step is additive and therefore
   large in relative terms, so the exact mean relative error is 23.1 %, roughly
   twice the `2^(Δ/8)` estimate and comparable to what an octave reading would
   have implied. Keep the epistemic point that this paragraph was making — that
   "the gate is tolerant of this magnitude" competes with "the gate is silent
   under coherent displacement" — but the magnitude arm is now the weaker of the
   two, and §3.4's probe 132 removes the coherence arm as well.

### 2.6 Exact size of the probe-128 perturbation

Approximating one code step as `2^(1/8)` is invalid below the subnormal
boundary, so the census decodes both codes exactly with the bias-7 E4M3 rule and
accumulates the per-entry relative error
`rel = s[(g+1) & 127] / s[g] - 1` directly, split by the parity of `g` (the
`derr` records), alongside the full 256-bucket code histogram (`chist`).

Second census pass, `/tmp/pr35_lm_census2.csv`, 7,681 records, same run
configuration as §2.1 (all shape and displacement figures reproduced exactly):

```
derr even_g n=24740138 zero_denom=163542 mean|rel|=0.000002 rms_rel=0.000997 max|rel|=1.6667
derr  odd_g n=24740138 zero_denom=163542 mean|rel|=0.231141 rms_rel=0.326622 max|rel|=16.6000
derr  all_g n=49480276 mean|rel|=0.115571 rms_rel=0.230958
chist n=49807360 distinct=36 min=0 max=35 zero=0.006567 subnormal(1..7)=0.803132 signbit=0.000000
chist top codes: 6:0.2111 5:0.1991 4:0.1488 7:0.1425 8:0.0929 3:0.0711 9:0.0454 10:0.0251 2:0.0246 11:0.0115
```

**The `2^(Δ/8)` approximation understates the true error by about a factor of
two, and §2.5's consequence 2 was wrong.** The reason is in `chist`:
**80.31 % of the plane's scale codes are E4M3 subnormals (codes 1…7)**, where the
step is additive, so `5 → 6` is `×1.20` and `1 → 2` is `×2.00`. The plane uses
only 36 distinct codes, `0 … 35`; no sign bit is ever set; 0.657 % of entries are
code 0 (exact zero), which the ratio excludes as `zero_denom`.

| Quantity for the probe-128 displacement | Approximated `2^(Δ/8)` | **Exact E4M3** |
| --- | --- | --- |
| mean `abs(rel)`, odd `g` | 0.1159 | **0.2311** |
| RMS `rel`, odd `g` | 0.1703 | **0.3266** |
| max `abs(rel)`, odd `g` | — | **16.60** |
| mean `abs(rel)`, all `g` | 0.0579 | **0.1156** |

Conditioning on entries that actually change (26.99 % of odd-`g` entries are
unchanged within a constant pair, §2.2): mean `abs(rel)` = 0.2311 / 0.7299 =
**0.3167**, RMS = 0.3266 / √0.7299 = **0.3823**.

So probe 128 is *not* a few-mantissa-step nudge. It multiplies the decode scale
of ~73 % of the 389,120 fused-QKV bank rows by a factor whose mean deviation
from 1 is **23 %** (32 % conditional on changing, RMS 38 %, worst case 17.6×),
and the 64-step teacher-forced gate reports an exact token match. On the even-`g`
side the same accounting confirms §2.2 independently: the only nonzero even-`g`
deltas are the 89 `g = 0` rows (fraction 3.6e-6, max ratio 2.667 = code 3 → 8).

This materially strengthens the first of the two readings in §2.5's
consequence 2 and weakens the second; §3.4's probe 132 then removes the
remaining coherence explanation.

## 3. Controls: the gate *does* see this kernel

The mode 2/3/5 faults of r3 were measured through the *benchmark* harness
(`research/frieren_pr35_lm_gate_pair.sh`, whose `classify()` reads `.metrics`),
not through `mlxfast correctness`. Before drawing any conclusion about the
correctness gate, both directions had to be nailed down against
`mlxfast correctness` itself.

How that gate works — `compareTeacherForcedWithWorker`,
`Sources/MLXFastHarness/LagunaRuntimeCorrectnessCompare.swift:59` — is a real
single-token decode loop: one `beginTeacherForcedCorrectness(promptTokens:)`
512-token prefill, then `teacherForcedCorrectnessStep(previousToken:)` for steps
1…63. A step passes on exact match or a validated true top-logit tie within
`correctnessLogitTieTolerance`. On mismatch it returns immediately, so a
flagging probe exits after 2–3 steps.

| Probe | Perturbation | Verdict |
| --- | --- | --- |
| **131** (negative control) | force every fitting-row code to `0` | **FLAGS.** `passed false`, `checked_steps 2`, `first_failing_step 1`, `first_failing_case longcopy-gate-english-512`, `expected_token 509`, `actual_token 83`, `error "teacher-forced token mismatch"` |
| **128** (coherent control) | whole-plane `g → g+1` rotation, both arms — 36.49 % of plane entries displaced (§2.3) | **SILENT.** `passed true`, `checked_steps 64`, `first_failing_step null` |

These two lines are the core result. The gate is wired to this kernel's output
on checked decode steps — probe 131 proves it — and yet a coherent
scale-*addressing* displacement of 36.49 % of plane entries passes 64/64 checked
steps.

Golden hash for both: `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`.

### 3.3 `max_abs_diff` is a hardcoded `0`, not a measurement

This is the most consequential finding of r4 and it invalidates evidence used
across this programme, including my own r3 write-up and the advisor's r4 brief.

`grep -rn "max_abs_diff\|maxAbsDiff" Sources/` finds the field written as the
literal `0` at **every** construction site, and computed nowhere:

```
Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift:1095      maxAbsDiff: 0,
Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift:1175      maxAbsDiff: 0,
Sources/MLXFastTrustedHarness/LagunaRuntimeLocalIterate.swift:1050   maxAbsDiff: 0,
Sources/MLXFastHarness/LagunaRuntimeBenchmark.swift:1079             maxAbsDiff: 0,
Sources/MLXFastHarness/LagunaRuntimeBenchmark.swift:1159             maxAbsDiff: 0,
Sources/MLXFastHarness/LagunaRuntimeLocalIterate.swift:1038          maxAbsDiff: 0,
Sources/MLXFastCore/Score.swift:635                                  maxAbsDiff: 0,
```

`Score.swift:243/368/517/597` are the declaration and `Codable` keys;
`Score.swift:727` (`maxAbsDiff: r(maxAbsDiff)`) is a rounding pass-through. The
only real computation of such a quantity in the repository is
`Tests/MLXFastTests/NAXSplitKGEMMTests.swift:119`, an unrelated local
`maxAbsoluteDifference`.

**Therefore `max_abs_diff 0` carries exactly zero information about numerical
agreement, in every receipt, for every candidate, including the pinned
baseline's.** Specific corrections that follow:

- My r3 claim that a 1025-step faulted run "held `max_abs_diff 0`" is not
  evidence of anything. The real evidence in that run is `passed_correctness`
  plus `checked_steps`.
- The advisor's r4 §"256-entry LUT discriminator" argument — that fern's receipt
  "independently establishes that `max_abs_diff 0` is not a numerical bound" —
  reaches the right conclusion for the wrong reason. It is not that a faulted run
  happened to keep the field at 0; the field is a constant and could not have
  done otherwise. No receipt from either student is a second data point.
- `senpai/program.md:98` and the `senpai/competition_notes/*` entries that read
  `max_abs_diff = 0` as bit-exactness should be corrected. PR #7's bit-exactness
  claim, for example, rests on its upstream-oracle logit error, not on this
  field.
- My own fault-injection harness had **unsatisfiable detection logic**:
  `research/frieren_pr35_lm_fault_gate.sh` accepted "`passed:false` **or**
  `max_abs_diff != 0`" as fault detection, so its second disjunct could never
  fire. Both that script and `research/frieren_pr35_lm_gate_pair.sh` are
  corrected in place. This is worth stating plainly: the field's appearance in a
  detector is exactly how a constant gets mistaken for a measurement.

The two correctness signals that *are* real: `passed_correctness` with
`checked_steps` (exact token match or validated top-logit tie, per §3), and the
separate `LagunaUpstreamEquivalence` tensor oracle — but see §3.5: that oracle
never builds the prepared decode layouts, so for *this* arm it is vacuous too.

This section was independently audited from the source by a second agent with no
access to my reasoning, which confirmed every construction site above and found
no path — including cross-process JSON decode from the runtime worker, whose
producers are the same literal-`0` constructors — that ever assigns a computed
value.

### 3.4 What probes 128 and 131 do *not* establish

Probe 131 is a catastrophic-magnitude fault (all codes forced to `0`). Under the
bias-7 E4M3 decode of §2.5 code `0` is not the smallest positive scale — it
decodes to exactly `0.0`, so probe 131 zeroes every fitting row's dequantized
weight rather than shrinking it. Probe 128 is a coherent displacement of
the magnitude measured in §2.6. The pair therefore differs in **both**
magnitude and coherence, so it cannot attribute the silence to either one. The
claim "the gate's blindness is coherence, not magnitude" is not yet supported by
any measurement in this programme — mine or the advisor's.

Probe **132** is the discriminator: even output rows displace `+1` group, odd
rows `-1`. Per-entry `|delta|` is drawn from the same adjacent-group distribution
as probe 128, so magnitude is matched by construction, while the displacement no
longer aligns across neighbouring rows. Because the plane is pairwise constant
(§2.2), `+1` faults the odd groups of even rows and `-1` faults the even groups
of odd rows, so the *count* of faulted entries is also matched; only the sign
pattern across rows differs.

| Pre-registered outcome | Reading |
| --- | --- |
| 128 silent, 132 flags | coherence is the blind axis; the advisor's framing is confirmed |
| **both silent** | the gate tolerates a scale perturbation of the §2.6 magnitude regardless of its row coherence; "coherence" is the wrong axis and the correct claim is weaker and broader |
| 132 flags with a *smaller* displaced fraction than 128 | row-alignment structure, not fault count, drives detectability |

**Result: probe 132 is silent.** `/tmp/pr35_probe132.json`: `passed true`,
`checked_steps 64`, `first_failing_step null`, `first_failing_case null`,
`error ""`, `golden_hash b9509697…8d7a63` (identical to every other run in this
document). The unperturbed census run in the same driver pass
(`/tmp/pr35_census2.json`) is the matched control and also passes.

So the middle row is what happened, and the advisor's "coherence is the blind
axis" framing is **not** supported: destroying row coherence at matched magnitude
and matched fault count changes nothing. Combined with §2.6 and probe 131, the
gate's sensitivity threshold for this fault class is bracketed only very loosely:

| Injected fault | Gate |
| --- | --- |
| 23 % mean (38 % conditional RMS, worst 17.6×) multiplicative scale error on ~73 % of 389,120 QKV bank rows, coherent (probe 128) | silent, 64/64 steps |
| the same magnitude and count, incoherent across rows (probe 132) | silent, 64/64 steps |
| all fitting rows' scales forced to `0`, i.e. weights annihilated (probe 131) | flags at step 1 |

A detector whose threshold lies somewhere between "a third of the QKV scale plane
is off by ~30 %" and "the QKV weights are all zero" is not a usable
representation check for deliverable B. That is the finding, and it is
independent of whether deliverable B is in fact correct.

Three further reasons the public gate is a weak detector here, all structural:

1. **Teacher forcing suppresses accumulation.** The 512-token seed KV cache is
   built by *prefill* kernels, which read the original plane; only the ≤63 rows
   appended by decode steps are faulted. At step 63 that is ≤11 % of cache rows,
   and because the next input token is supplied rather than sampled there is no
   trajectory feedback.
2. **The only public golden is a long-copy task**
   (`longcopy-gate-english-512`). Copying an in-context span produces enormous
   greedy top-1 margins by construction, which is close to the worst case for
   detecting a small logit perturbation.
3. **A validated top-logit tie also passes**, so the gate accepts a perturbation
   that reorders logits within `correctnessLogitTieTolerance`.

None of this transfers automatically to the hidden gates. Hidden **free runs**
sample their own next token, so faulted KV compounds and a per-step tolerance
argument does not apply. Nothing here licenses shipping a fault.

### 3.5 The upstream-equivalence oracle cannot see this arm at all

`LagunaUpstreamEquivalence.compare`
(`Sources/MLXFastModel/LagunaUpstreamEquivalence.swift:41-123`) constructs
`LagunaRuntimeModel(runtimeConfig)` directly (`:74`), installs the checkpoint
with `update` + `eval` (`:76-89`), and calls the model. It never goes through
`LagunaRuntimeWeightCache`.

Every fused / native-affine decode layout — including this arm's lane-major
scale bank — is built in `LagunaRuntimeModel.prepareFusedRuntimeWeights()`
(`LagunaRuntimeModel.swift:11211`), which reaches
`prepareNativeAffineQKVWeight()` (`:5592`) and assigns `fused.laneMajorScales`
at `:5664`. The **sole** caller of `prepareFusedRuntimeWeights()` in the whole
tree is `LagunaRuntimeWeightCache.loadLibraryModel`
(`LagunaRuntimeWeights.swift:637`).

Therefore, inside the oracle `bank.laneMajorScales` is `nil`, the guard at
`LagunaRuntimeModel.swift:4921` fails, and the lane-major kernel is never
dispatched. **The oracle exercises the fallback path, not deliverable B.** A
green oracle report is not evidence about this arm.

The correctness gate, by contrast, does reach it:
`Sources/MLXFastHarness/LagunaRuntimeCorrectnessCompare.swift:27` builds a
`LagunaRuntimeWeightCache` and `:341` calls `requireLibraryModel()`. That is
consistent with probes 129/130/131 firing.

This is a programme-level correction, not an arm-specific one. `AGENTS.md`
instructs running the oracle "when a change affects numerical behavior,
representation, dispatch, or layout"; for any change confined to a prepared
layout it is structurally vacuous, which covers every `DARKBLOOM_FUSED_*` and
native-affine layout already on the frontier. One `prepareFusedRuntimeWeights()`
call after `LagunaUpstreamEquivalence.swift:89` would fix it for all of them —
but that file is inside `editablePaths` (6,501 B today), so the fix spends
submission bytes and belongs to whoever owns the shared surface, not to this
arm.

### 3.6 What actually establishes this arm's correctness: an exhaustive fail-closed certificate

The arm's correctness argument does not rest on gate silence, and never did.
`lagunaLaneMajorNVFP4ScaleBank` refuses to install the bank unless
`lagunaLaneMajorScaleBankReproducesScales(bank, scales)` returns true
(`LagunaRuntimeWeights.swift:1001-1012`); on failure it returns `nil` and the
runtime keeps the wide path. The certificate (`:1014-1036`) decodes every
`(row, group)` pair and counts mismatches against the reference plane:

```swift
let nib = bank.nibbles.asType(.int32).reshaped([rows, groups / 2, 1])
let nibValues = concatenated([nib & 0x0F, (nib >> 4) & 0x0F], axis: 2)
    .reshaped([rows, 32, groups / 32])
let decoded = contiguous(
    (bank.bases.asType(.int32).reshaped([rows, 1, 1]) + nibValues)
        .transposed(0, 2, 1)
).reshaped([rows, groups]).asType(.uint8)
let escaped = (bank.bases .== MLXArray(UInt8(0xFF))).reshaped([rows, 1])
let mismatches = (which(escaped, scales, decoded) .!= scales)
    .asType(.int32).sum().item(Int32.self)
return mismatches == 0
```

That is an exhaustive equality check over all 389,120 × 128 = **49,807,360**
entries, on the real checkpoint, on every run, failing closed.

It is stronger than a round-trip test, because its decode reproduces the
*kernel's* index map rather than an abstract one:

- host: `[rows, 64, 1]` low/high concat → `[rows, 64, 2]` → `[rows, 32, 4]` →
  `transposed(0, 2, 1)`, so group `g = 32b + s` reads flat nibble `4s + b`,
  where flat `2j` is the low nibble of byte `j` and `2j + 1` the high nibble.
- kernel: `packed = nb0[simd_lid]` is the little-endian `ushort` covering bytes
  `2s` and `2s + 1`; `sb[b] = row_base + ((packed >> (b << 2)) & 0xF)` selects
  flat nibble `4s + b` under the same low-then-high convention.

The two maps are identical and were derived independently, in different
languages, against different primitives. A systematic addressing error would
have to be replicated exactly in MLX array algebra and in Metal bit shifts.

What the certificate does **not** cover: that the compiled Metal kernel executes
its source's intent (threadgroup geometry, `simd_lid`/`simd_gid` binding,
escape-sentinel branch selection), and the escaped arm's `sc[b * (block_size /
16)]` stride, which the certificate models as a straight `scales` passthrough
rather than re-deriving. Those need a direct kernel A/B (§8, item 1).

The consequence for r4 is the important one: **the gate probes measure the gate,
not the arm.** Probe silence is uninformative about deliverable B in either
direction, because the arm's guarantee is a host-side exhaustive equality, not
an end-to-end token comparison.

**Provenance note for §3.5 and §3.6.** Both sections were established by my own
direct source inspection, with every call site read and every `grep` for
alternative callers run over the whole tree. I dispatched two independent audit
agents to re-derive them from scratch — one for the oracle-vacuity claim, one for
the host/kernel index map — and **both failed on their inherited deadline and
returned no result**, so neither section carries independent confirmation. Treat
them as single-reviewer findings. §3.3 by contrast was independently audited and
confirmed. The claim most worth a second pair of eyes is the sole-caller
argument in §3.5, because it is what makes a green
`LagunaUpstreamEquivalence` run uninformative about every `DARKBLOOM_FUSED_*`
and native-affine layout on the frontier, not just about mine.

## 4. The one-hot coherent-addressing sweep

Driver: `research/frieren_pr35_lm_probe_sweep.sh`. For probe index `L`, group
`L`'s reconstructed scale is replaced by group `(L+1) & 127`'s scale in **both**
the fitting arm (`sb[L/32]` at `simd_lid == L%32`, source nibble
`nb0[M%32] >> ((M/32)<<2)`) and the escaped arm
(`(weight_scales + out_row*in_vec_size_g)[M]`). `L` arrives through
`DARKBLOOM_LM_PROBE`, is interpolated into the JIT kernel source, and suffixes
the kernel name `_probe<L>`, so no rebuild is needed between values and
`Sources/` is byte-identical across the whole sweep. `L = -1` (unset) leaves the
shipped kernel byte-identical.

The census gives the per-probe perturbation size *a priori*, which is what makes
the sweep interpretable at all. Probe `L` displaces `disp[L]` of the 389,120
rows:

| `L` class | count of `L` | rows displaced per probe | share of rows |
| --- | --- | --- | --- |
| odd | 64 | 280,494 … 293,382 | 72.08 % … 75.40 % |
| `L = 0` | 1 | 89 | 0.023 % |
| even, `L ≥ 2` | 63 | 0 | 0 % |

### 4.1 The sweep's design flaw, stated before its result

Because the plane is pairwise constant (§2.2), **63 of the 128 probes are
provably bit-identical no-ops**: `disp[L] = 0` means the substituted code equals
the code it replaces, so the kernel emits the same bytes and the run is not a
fault injection at all. `L = 0` faults 89 rows in 389,120, which is a
perturbation of the same order as no fault.

The advisor's submission precondition — *every probe flags* — is therefore
**unsatisfiable by construction**, independently of how the gate behaves. This
was knowable from the census before the sweep was launched and is a property of
the plane, not a result. The rule's other branch (*any silent class ⇒ stop and
post*) is the one that applies, and it applied the moment §2.2 was measured.

Consequently the sweep cannot change the dispatch decision. It is run to
completion only because the 64 odd-`L` probes are genuinely informative about
the gate, and because a flag anywhere would be important news.

### 4.2 Result

The sweep ran to completion: driver pid 78034 exited cleanly after
`elapsed 01:24:22`, 5,765 s of wall clock, 26–47 s per probe, no orphaned
workers afterwards (`ps -eo pid,etime,comm | grep -c mlxfast` = 0). Integrity of
`/tmp/pr35_lm_sweep.csv` was checked before it was read: 128 rows, all 128
distinct `L` present, no gap in `0…127`.

| Field | Value across all 128 probes |
| --- | --- |
| `passed` | `true` × 128 |
| `checked_steps` | `64` × 128 |
| `first_failing_step` | `null` × 128 |
| `first_failing_case` | `null` × 128 |

**Flag rate: 0 of 128 = 0.0 %.** Splitting by the a-priori classes of §4:

| `L` class | probes | rows faulted per probe | flags |
| --- | --- | --- | --- |
| odd (informative) | 64 | 280,494 … 293,382 (72.08 % … 75.40 %) | **0 / 64** |
| `L = 0` (near-null) | 1 | 89 (0.023 %) | 0 / 1 |
| even, `L ≥ 2` (structurally null) | 63 | 0 | 0 / 63 — expected, these are bit-identical no-ops |

Only the 64 odd-`L` rows are evidence. Each of them replaces the decode scale of
roughly three quarters of the 389,120 fused-QKV bank rows with a neighbouring
group's scale, in both the fitting and the escaped arm, and the 64-step
teacher-forced gate reports an exact token match every time.

Two readings were open before §2.6 and probe 132 reported:

1. the gate has little sensitivity to a coherent one-group index displacement of
   this magnitude on this golden; or
2. a perturbation whose measured relative size is that of §2.6 is simply inside
   the greedy margin of a long-copy task.

Probe 132 (§3.4) held magnitude and fault count fixed and destroyed the
coherence; it is also silent. §2.6 then measured the magnitude exactly at 23 %
mean / 38 % conditional RMS relative scale error. Together those retire reading 1
as a *coherence-specific* story and leave a single weaker, broader claim: **on
this golden, over 64 teacher-forced steps, the gate does not react to a
displacement-class scale fault of this size at all, however it is arranged across
rows.** What the sweep additionally establishes is
the negative operational fact the r4 rule turns on: **no probe in the index space
flags**, so the "every probe flags ⇒ submit" branch is not merely unsatisfiable
by construction (§4.1) — it is also empirically unmet by the widest possible
margin.

The converse inference is not available either. Because the outcome is
all-silent, a silent sweep is equally likely under "the representation is
correct" and under "the gate cannot see this class of representation fault": the
likelihood ratio between those hypotheses is ≈ 1, so **the sweep supplies no
positive evidence that deliverable B's addressing is right**. That is the
substantive reason §8.1 asks for a direct wide-vs-lane-major kernel A/B instead
of more gate probes.

## 5. Byte budget at head `5baec67`

Two candidate bases were in play and the budget is reported against **both**, so
the number does not depend on which one is authoritative:

- **declared assignment base** `eaedee8430f1e2779b235a7fbc296ee20ef3e44b` —
  resolved with `git cat-file -t` → `commit`; real, and an ancestor of my head;
- **merge-base** `git merge-base fae11f91… origin/maple-frieren/scale-code-width`
  = `1849b376d73f69f9a6b9018619ac665ae4bceb33`, a *later* ancestor.

An earlier version of this section measured growth against `5178d452`, which is
neither; that figure is withdrawn.

`senpai/check-editable-budget.sh <base>` run in a clean detached worktree at
`5baec67` (the instrumented worktree is *not* the submission surface, and
`5baec67`'s `Sources/` + `Vendor/` are byte-identical to the evidence head
`b3319dfb`) gives the **same** output for both bases:

```
editable budget OK: current=2966629/3000000 bytes headroom=33371 growth=25656/262144 files=142 (file count is diagnostic only; base=142)
```

That identity is not a coincidence: `eaedee84` and `1849b376` carry the same
blob for the only `editablePaths` file that differs between them and my head, so
every byte-budget quantity is invariant to the choice.

| Limit | Value | Headroom |
| --- | --- | --- |
| Total surface | 2,966,629 / 3,000,000 | **33,371 B** |
| Growth vs base (either) | 25,656 / 262,144 | 236,488 B |
| `LagunaRuntimeModel.swift` per file | **521,566** / 524,288 | 2,722 B |
| `LagunaUpstreamEquivalence.swift` | 6,501 B | — inside the submitted surface (`editablePaths` lists `Sources/MLXFastModel/` as a directory), so hardening the oracle spends submission bytes |

The binding constraint for the programme is now the **33,371 B total-surface
headroom**, not the per-file cap. My contract stands: nothing new goes into
`LagunaRuntimeModel.swift`; new code goes to `LagunaRuntimeWeights.swift`;
`LagunaRuntimeModel.swift` stays ≤ 523,000 B at submission and at merge.

With the temporary probe instruments present, `LagunaRuntimeModel.swift` is
524,432 B and `mlxfast-swift` prints
`warning: editable file ... is 524432 bytes, above the per-file static review
limit 524288`. Every instrument edit in this document is reverted before any
submission, and the disappearance of that warning is the check.

## 6. Pre-dispatch inject guard (mandatory, r4)

The advisor's r4 note prices a −3.24 % landmine on the advisor integration
branch `5178d452`: `DARKBLOOM_INJECT_DECODE_EMPTY` defaults to `100` and
`DARKBLOOM_INJECT_EMPTY_TG` to `8` there, `lagunaInjectActive` is therefore
`true` with no env var set, and `lagunaInjectLayerWork(...)` is called
unconditionally from the scored per-layer loop — 100 chained empty dispatches
per single-token decode step over 40 layers.

My head is clean, verified against the exact submission commit:

```
$ git show b3319dfb5c13d7c3c669424139d50acaac044f70:Sources/MLXFastModel/LagunaRuntimeModel.swift \
    | grep -n "DARKBLOOM_INJECT_DECODE_EMPTY\|DARKBLOOM_INJECT_EMPTY_TG"
11342:    "DARKBLOOM_INJECT_DECODE_EMPTY", 0)
11354:    "DARKBLOOM_INJECT_EMPTY_TG", 160)
```

`0` and `160` as required. This check is re-run against the actual submission
commit immediately before dispatch and both lines are pasted into the
submission note. No rebase, merge, or cherry-pick from the advisor branch
happens before the receipt; the base is accepted via `accepted_base_sha`.

## 7. Reproduction

```bash
swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved
export MLXFAST_RUNTIME_WORKER_EXECUTABLE="$PWD/.build-worker/release/mlxfast-runtime-worker"

# census pass 1 (quad + disp only)
MLXFAST_NO_SANDBOX=1 DARKBLOOM_LM_CENSUS=/tmp/pr35_lm_census.csv \
  ./.build/release/mlxfast-swift correctness --weights weights \
  --golden correctness_prompts/public_longcopy_gate_english_512_256.json
python3 research/frieren_pr35_census_agg.py

# census pass 2 (adds exact derr + chist; needs the instrumented worker rebuilt)
MLXFAST_NO_SANDBOX=1 DARKBLOOM_LM_CENSUS=/tmp/pr35_lm_census2.csv \
  ./.build/release/mlxfast-swift correctness --weights weights \
  --golden correctness_prompts/public_longcopy_gate_english_512_256.json
python3 research/frieren_pr35_census_agg.py /tmp/pr35_lm_census2.csv

# single named probe (128 = coherent whole-plane rotation,
# 131 = scales annihilated, 132 = incoherent matched-magnitude displacement)
MLXFAST_NO_SANDBOX=1 DARKBLOOM_LM_PROBE=132 \
  ./.build/release/mlxfast-swift correctness --weights weights \
  --golden correctness_prompts/public_longcopy_gate_english_512_256.json

# one-hot sweep (no rebuild between values)
research/frieren_pr35_lm_probe_sweep.sh $(seq 0 127)
```

Each `correctness` invocation is roughly 45 s and does not take the benchmark
lock, so the census pass and a probe can be chained in one background script
(`/tmp/pr35_run_census_and_132.sh` did exactly that, log
`/tmp/pr35_c132_driver.log`). Surviving artifacts:

| artifact | content |
|---|---|
| `/tmp/pr35_lm_census.csv` | census pass 1, 5,160 records |
| `/tmp/pr35_lm_census2.csv` | census pass 2, 7,681 records (adds `derr`, `chist`) |
| `/tmp/pr35_census2.json`, `/tmp/pr35_census2.err` | unperturbed control run for pass 2 (`passed true`, 64/64) |
| `/tmp/pr35_probe128.json` | coherent whole-plane rotation — silent |
| `/tmp/pr35_probe131.json` | scales annihilated — flags at step 1 |
| `/tmp/pr35_probe132.json` | incoherent matched-magnitude displacement — silent |
| `/tmp/pr35_lm_sweep.csv`, `/tmp/pr35_sweep_probe*.json` | the 128-probe one-hot sweep |
| `/tmp/pr35_sweep_driver.log` | sweep driver log, `elapsed 01:24:22` |

`MLXFAST_NO_SANDBOX=1` is required only for the census file write: the CLI's
Seatbelt profile (`writeRuntimeWorkerSandboxProfile`,
`Sources/mlxfast-swift/main.swift:1612-1659`) contains `(deny file-write*)` with
only `/dev/null` allowed. It is legal locally and rejected officially; no timed
or ranked number in this document depends on it. The worker environment is a
strict allowlist (`sanitizedRuntimeWorkerEnvironment`,
`LagunaRuntimeWorker.swift:~1996`): `DARKBLOOM_*`, `DYLD_*`, `LC_*`, `MTL_*`,
`METAL_*`, `MLX_*` propagate and every `MLXFAST_*` is stripped, which is why the
probe index travels as `DARKBLOOM_LM_PROBE`.

Note that `mlxfast correctness` prints a trailing non-JSON note line after the
JSON object, so parsing must `raw_decode` from the first `{` rather than
`json.loads(t[t.find('{'):])`.

## 8. Follow-ups (not implemented)

1. **Direct kernel A/B — the test that should replace the gate sweep.** Run
   `lagunaDecodeNVFP4QKVR1`'s wide path and its lane-major path on the same
   inputs and compare the `projected` tensors elementwise, on the real plane and
   on synthetic planes constructed to be *injective* in the group index (so any
   address permutation shows up). Bit-identical output is the expectation, since
   the two paths perform the same arithmetic on the same reconstructed codes;
   this is the only test that covers what §3.6 leaves open (compiled threadgroup
   geometry, `simd_lid`/`simd_gid` binding, escape-branch selection, and the
   escaped arm's `sc[b * (block_size / 16)]` stride). It costs **zero submission
   bytes** if it lives under `Tests/`, which is not in `editablePaths`. It was
   proposed in the r3 write-up and has still not been run; it should be run
   before the gate-blindness line of work is extended any further.
2. **Harden the upstream-equivalence oracle** (§3.5): one
   `prepareFusedRuntimeWeights()` call after
   `LagunaUpstreamEquivalence.swift:89` makes the oracle actually cover every
   prepared decode layout on the frontier, not just this arm's. It costs
   submission bytes on a shared file, so it is an advisor/frontier decision.
3. **Group-32 scale plane.** §2.2 shows the QKV group-16 plane is pairwise
   constant, so the nibble string can be halved again on top of deliverable B:
   ~32 B → ~16 B of a ~1,089 B per-row scale payload, i.e. roughly half of
   B's own byte saving, order 12 MB/step ≈ −14 µs/step ≈ +0.1 … +0.2 % on
   `ns`. Correctness is not the risk — the per-row escape sentinel plus the
   §3.6 certificate already fail closed, and 89 of 389,120 rows *already*
   violate the invariant at pair `(0, 1)`, so it must be treated as data, never
   assumed. The real cost is opportunity and byte budget; it ranks below the
   `attn.o` extension.
4. **Remaining fault-injection axes** — only if the advisor still wants the
   gate characterised after item 1. The incoherent axis is *done* (probe 132,
   §3.4: silent), so the two probes left from the earlier ranking are a
   **base-byte row offset** (`row_base` from a neighbouring row, which perturbs
   the octave rather than the mantissa and so escapes the 1.9-octave `span ≤ 15`
   window) and a **Q-rows-only** fault (which tests whether the gate's
   insensitivity is uniform across the fused bank's Q/K/V row ranges rather
   than an artifact of averaging over all three). Both are strictly less
   valuable than item 1: they can only ever move the *gate*'s sensitivity
   bound, and §3.4 already brackets that bound between "23 % mean / 38 %
   conditional-RMS multiplicative error on ~73 % of rows ⇒ silent 64/64" and
   "all scales zeroed ⇒ flags at step 1". No further probe can turn a silent
   sweep into evidence that B's addressing is correct.
5. **`o_proj` instruction-issue discriminator.** Zero-byte 256-entry-LUT
   variant for the r1 narrow-`o_proj`-alone anomaly (+69.5 µs/step at 4.1× its
   byte roofline). Held until after the receipt.
6. **`attn.o` lane-major extension** (−19.6 MB/step). Held.
