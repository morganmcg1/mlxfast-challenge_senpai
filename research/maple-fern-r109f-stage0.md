# R109-F Stage 0 — official preflight de-risked on an unmodified tree

Assignment `maple-r109-f-integration-and-submission`, revision `r109-f-rev1`, PR #686.
Base `1a6761bf46c282fcabd0577b618f0c1206757e6c` (branch
`codex/mlxfast-maple-20260804-advisor`), assignment head
`278c1561db4a3fec179658d7446ea92543b75f14`.

Host: Apple **M4 Pro**, 48 GiB unified memory, macOS 26.5.2, Apple GPU
generation 16. Everything below is M4 evidence and is directional for the
ranked M5 only under the usual same-host/same-kernel-family caveat.

My role in this round is not a kernel arm. Stage 0 exists so that when a
landing arm is ready there is no unknown left in the official path: every
preflight command has been run on a tree that is byte-identical to base under
`Sources/` and `Vendor/`, and every failure mode has already been characterised
and priced.

---

## 0. Four things the advisor needs from this report

1. **The upstream-equivalence oracle is red on the unmodified base on this
   host.** Read as a gate it vetoes every arm in the round. §5 replaces it with
   a base-relative differential and states the exact no-worse-than-base
   signature.
2. **A paired local family resolves 0.250% on `ns` against a 0.378% ranked
   bar** — but only if the first replicate of each family is discarded, because
   rep1 is biased by 0.7–1.1%, which is more than the whole bar. Blocked
   designs are unusable this round (§3).
3. **The only byte cap with teeth is the per-file 524,288 B limit**, leaving
   140,043 B of shared headroom in `LagunaRuntimeModel.swift` against ~90 KB
   planned across five arms. Total budget and growth are both non-issues (§6.1).
4. **The NVFP4/fusion probe came back negative, decisively.** The bundled
   toggle is a **−16.6%** score regression, ~96% of it the NVFP4→INT8 bank
   flip; the fusion isolated at matched quantization is **−0.883% on `ns`**, not
   +1.40%. Recommend closing the line (§7.5).

---

## 1. Verdict summary

| # | Preflight gate | Command | Verdict on the unmodified tree |
|---|---|---|---|
| 1 | Correctness + local score | `MLXFAST_LOCAL_FAN_PROMPT=0 ./benchmark.sh --local-submit` | **PASS**, 5/5, exit 0 |
| 2 | Editable byte budget | `bash senpai/check-editable-budget.sh 1a6761bf…` | **PASS** `current=2681206/3000000 headroom=318794 growth=0/262144 files=142` |
| 3 | Assignment scope | `bash senpai/validate-assignment-scope.sh <BASE_SHA> Sources/MLXFastModel/LagunaRuntimeModel.swift` | **PASS**, exit 0 |
| 4 | Upstream equivalence | `bash research/run_upstream_equivalence.sh` | **FAILS ON THE UNMODIFIED BASE on this host** — see §5 |

Gate 4 is the important one and the reason Stage 0 was worth a full slot: on
this M4 Pro the equivalence oracle is red before anybody touches anything.
Read naively it would veto every arm in the round. §5 converts it into a usable
base-relative differential.

---

## 2. What the score actually has to move

Bar to beat, from the live receipt table (benchmark
`1854efdf-feba-4773-bae9-b80520881a74`):

* Leader **2.61650354381456**, commit `c5b0a13`, receipt `cc6ddc12`, promoted.
* Our best official **2.60664969895906**, receipt `e27f1ce`, commit
  `5c542169b5e6c295805f50fa65df3150816eb443`.

A successor must beat **our own** `e27f1ce`, not merely a fresh local baseline —
the three receipts we took after `e27f1ce` all scored worse (2.59380735,
2.58107302, 2.56572014), so "better than today's local base" has already
produced three wasted slots this campaign.

Required improvement over `e27f1ce`:

| Route | Multiplier | As a percentage | Equivalent absolute |
|---|---|---|---|
| Weighted (both axes move) | 1.003780272× | **0.378%** | — |
| Decode-only (prefill flat) | 1.005043536× | 0.504% | 24.543 µs/token |
| Prefill-only (decode flat) | 1.015207047× | 1.521% | 2.816 µs/token |

Both component floors (`0.95`) also have to hold; they are not the binding
constraint for anything in this round.

### 2.1 The `ns` proxy

Neither decode nor prefill seconds/token alone is the quantity that has to
move, so the ledger now reports the same weighted geometric mean the ranked
scorer uses, evaluated against the pinned reference constants:

```text
ns = (0.013890 / decode_s_per_token)^0.75 * (0.0003845 / prefill_s_per_token)^0.25
```

`ns` is not the ranked score — the ranked score uses the same-session paired M5
baseline, and the local harness constants (decode `0.01385621216015625`,
prefill `0.00036751938916015626`) are M5-calibrated while the measurement is
M4. `ns` is useful because *ratios* of `ns` between two locally paired families
are exactly the weighted combination that ranking cares about, with the
reference constants cancelling.

---

## 3. Stage-0 baseline family

Five `./benchmark.sh --local-submit` replicates on the unmodified tree. All
five: `passed_correctness=true`, `checked_steps=1025`, identical
`golden_hash f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2`,
`peak_ram_gb=21`.

| rep | decode s/tok | prefill s/tok | `ns` | harness score | ts (UTC) |
|---|---|---|---|---|---|
| 1 | 0.009022583 | 0.001123788 | 1.057016 | 1.043240 | 20:35:43 |
| 2 | 0.008956889 | 0.001112746 | 1.065452 | 1.051566 | 20:39:42 |
| 3 | 0.008934668 | 0.001112018 | 1.067613 | 1.053699 | 20:42:28 |
| 4 | 0.008954571 | 0.001111801 | 1.065885 | 1.051994 | 20:46:47 |
| 5 | 0.008986536 | 0.001111760 | 1.063050 | 1.049196 | 20:50:08 |

Reproduce: `python3 research/fern_r109_timing_ledger.py base` and
`python3 research/fern_r109_timing_ledger.py --drop-first base`.

### 3.1 Dispersion and detection floors

| Statistic | Full n=5 | Steady state (drop rep1, n=4) |
|---|---|---|
| decode median | 0.008956889 | **0.008955730** |
| decode spread / cv | 0.982% / 0.382% | 0.579% / **0.239%** |
| prefill median | 0.001112018 | **0.001111910** |
| prefill spread / cv | 1.082% / 0.472% | 0.089% / **0.041%** |
| `ns` median | 1.065452 | **1.065669** |
| `ns` cv | 0.388% | **0.177%** |
| 2σ paired floor, decode | 0.484% | **0.338%** |
| 2σ paired floor, prefill | 0.597% | **0.058%** |
| 2σ paired floor, `ns` | 0.490% | **0.250%** |

The `ns` floor is tighter than the decode floor because the prefill axis is
nearly noiseless on this host and enters with only 25% weight, so it damps the
combination rather than adding to it.

**This is the headline number for the round: with rep1 discarded, a paired
local family of n=4 usable replicates resolves 0.250% on `ns`, which is below
the 0.378% weighted ranked bar.** An arm that cannot show a `ns` gain above
0.25% here has not demonstrated anything, and an arm that shows 0.38%+ on `ns`
is measurable rather than noise. Replicates needed at 2σ: weighted bar n≥4,
decode-only tie n≥2. I will run **n=5 usable (6 runs) per family** for the
final stacked candidate to keep margin.

### 3.2 rep1 is a reproducible cold-start outlier

rep1 is slower than the steady-state median on **both** axes: decode +0.746%,
prefill +1.068%. That single-replicate bias is *larger than the entire ranked
bar* (0.378%).

Consequence for the round, and it is not a small one: **any blocked design —
all baseline replicates then all candidate replicates — hands whichever family
runs second a free ~0.7–1.1% advantage on its first replicate.** That is
enough to manufacture a win out of nothing, and it is the most likely way this
round produces a false positive. Every timing family in Stage 1 and Stage 2
will be **interleaved** (palindromic ABBA-style ordering) and will **discard
each family's first replicate**.

---

## 4. Gates 1–3, exactly as run

### 4.1 `--local-submit`

`MLXFAST_LOCAL_FAN_PROMPT=0 ./benchmark.sh --local-submit`, exit 0 on all five
replicates. Golden `correctness_prompts/public_longcopy_gate_english_512_1024.json`,
1025 checked steps. Note `--local-iterate` uses the *512_256* golden and checks
130 steps, so it is a much weaker correctness statement; correctness claims in
this round come from `--local-submit`.

Two local-only artefacts that must not be mistaken for failures:
`passed_prefill_speedup_floor: false` and the absolute local score are both
M4-vs-M5 calibration consequences of the pinned harness constants. They are
present on the unmodified base.

### 4.2 Editable byte budget

`current=2681206/3000000 headroom=318794 growth=0/262144 files=142`.

### 4.3 Assignment scope

`validate-assignment-scope.sh` exits **1** for research-only paths. Pass it
**only** the submitted paths; listing `research/…` support files makes a valid
assignment look invalid. Confirmed exit 0 for
`Sources/MLXFastModel/LagunaRuntimeModel.swift`.

Note the stale path in the brief: `Sources/MLXFastModel/LagunaRuntimeLayers.swift`
does not exist at HEAD. Actual `Sources/MLXFastModel/` contents are
`DenseTensorStore.swift`, `LagunaConfig.swift`, `LagunaLmHeadPrune.swift`,
`LagunaRuntimeModel.swift`, `LagunaRuntimeWeights.swift`,
`LagunaUpstreamEquivalence.swift`, `MLXTensorBridge.swift`,
`RuntimeStartupMemoryPolicy.swift`, `RuntimeWeightLoading.swift`.

---

## 5. Gate 4: the equivalence oracle is red on the unmodified base

`bash research/run_upstream_equivalence.sh` on a tree byte-identical to base
under `Sources/` and `Vendor/` **fails**, exit 1, 68 s. Archived at
`research/artifacts/fern-r109f/base-upstream-equivalence.log`.

The test really was selected — 1 test, report marker present,
`EQUIVALENCE_EXACT_STEPS=8` — so this is not the zero-test false pass the
wrapper is designed to refuse. The failure signature is:

```text
prefill  maximumAbsoluteLogitError = 0.125
prefill  meanAbsoluteLogitError    = 0.011933609
         runtimeToken == upstreamToken == 5991
decode   all 8 steps exactly 0
```

The greedy token still agrees; the disagreement is sub-decision prefill
numerical drift between the runtime and the vendored oracle on Apple GPU
generation 16.

**Therefore, for this round, gate 4 is a base-relative differential, not a
pass/fail gate.** The usable rule:

* Reproducing exactly `prefill max 0.125 / mean 0.011933609`, decode all-zero,
  `EXACT_STEPS=8` ⇒ the arm is **no worse than base** on this oracle.
* Any decode step ≠ 0, or a prefill error above those values ⇒ a **real
  regression**, and the arm is blocked pending investigation.

The one thing I will not do is treat "it also fails" as neutral without
comparing the numbers, which is how a genuine regression would slip through.

### 5.1 `max_abs_diff: 0` is a schema constant, never a measurement

Independently verified: every construction site passes a literal `0`.

```text
Sources/MLXFastTrustedHarness/LagunaRuntimeLocalIterate.swift:1050
Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift:1095, 1175
Sources/MLXFastCore/Score.swift:635
Sources/MLXFastHarness/LagunaRuntimeLocalIterate.swift:1038
Sources/MLXFastHarness/LagunaRuntimeBenchmark.swift:1079, 1159
```

So `max_abs_diff: 0` in any score JSON carries no information. The real signal
is `passed_correctness` together with a null `first_failing_*`. Likewise
`logit_delta == 0` and a matching `golden_hash` are **not** correctness claims
for a non-bit-exact arm — they are one prompt on one host.

### 5.2 The equivalence harness is not a margin substitute

`run_upstream_equivalence.sh` never calls `prepareFusedRuntimeWeights()`, and
it has previously reported 0.0 error on a candidate that the margin instrument
scored at 1.37× the safety-factor threshold
(`research/maple-frieren-margin-certificate-service.md` §8.7). For edward and
alphonse, which are not bit-exact by construction, a margin certificate is
required and the equivalence run does not stand in for it.

---

## 6. Operational questions, settled

### 6.1 The 998-byte budget discrepancy — 318,794 B is authoritative

The advisor independently confirmed the number; here is the mechanism, because
it will recur.

`check-editable-budget.sh` derives `current`/`headroom` from the **working
tree** (`find -type f` plus `wc -c`, which counts untracked *and gitignored*
files), while `growth` compares the **BASE_SHA git tree**. The two halves of
the report therefore measure different objects.

Committed editable totals: `1a6761bf`, `adfca1e5`, `1264d70c`, `d406439b` are
all **2,681,206**. `origin/main` `1bc1c895` is 2,983,849. The campaign base
`768bb9d4` is 2,999,984. A reading of 319,792 headroom implies a working total
of 2,680,208 = exactly **998 B less** than the committed base, i.e. it was
taken with an uncommitted deletion in the tree (most likely the r108
dedup-defeat probe; one stash exists, `stash@{0}` on
`maple-fern/r106-decode-serialisation-ledger`).

Two conclusions that matter for planning:

* **Growth is a non-issue.** Measured against `origin/main` the growth term is
  `-302643/262144` — we are 302,643 B *under* base, because `f720e9e7` and
  `8237f43b` deleted comment prose only.
* **The only cap with teeth is the per-file 524,288 B limit.**
  `LagunaRuntimeModel.swift` is **384,245 B**, leaving **140,043 B of shared
  headroom** in that one file against roughly 90 KB planned across five arms.
  That is the real contention, and it is why the one-new-file-per-arm layout
  below matters.

### 6.2 New-file layout is legal and is the right composition strategy

`editablePaths` contains two **directories** (`Sources/MLXFastModel`,
`Sources/MLXFastTransform`), so a brand-new `.swift` file under
`Sources/MLXFastModel/` validates, is submitted, and is auto-compiled. Each arm
puts its bulk in its own new file and leaves only minimal call-site edits in
`LagunaRuntimeModel.swift`. This keeps the LRM conflict surface small and dense
and keeps the per-file cap comfortable. The composition harness is built around
that layout.

### 6.3 `--model` must never be typed

`senpai/submit-official.sh` usage is `BASE_SHA [mlxfast submit arguments...]`
(lines 6–7); line 10 shifts `BASE_SHA`; lines 19–21 reject any `--model` or
`--model=*` with `official submit: model attribution is fixed to senpai` and
`exit 2`; line 109 is `exec mlxfast submit --model senpai "$@"`. Attribution is
already fixed, so passing it is a hard error, not a redundancy.

Correct form:

```bash
bash senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 --note-file <path>
```

Line 75 is the guard that aborts when the submitted snapshot at `BASE_SHA`
differs from current `origin/main`. If it fires I report to the advisor and do
**not** change `BASE_SHA` to make it pass. Notes are mandatory public Markdown,
5 KiB–100 KiB, no secrets, no local paths, no tokens.

### 6.4 Queue is idle, and the limit is per-account

Fresh REST pull of 1,794 rows: **0 non-terminal submissions benchmark-wide**.
The earlier `ccec94b4` `validating` row (account `newjordan`) has terminalised.

The in-flight limit is **per-account, not global**. The exact server string is:

```json
{"error":{"code":"conflict","message":"account already has 1 submission(s) in flight for this benchmark (limit 1)"}}
```

(`research/r93-runs/cadence-policy.md:8-15`, `research/r93-runs/RESULTS.md:46-51`,
`senpai/tools/pr34_inflight.py`.) Our account is `morganmcg1` (157 rows), shared
across sibling campaigns **and across all five students** ⇒ we have exactly one
slot in total. I re-verify immediately before firing, and I will never
retry-loop: at most one non-terminal submission at a time.

Receipt-reading recipe (the CLI truncates `metrics`; use REST):

```bash
curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
  "https://api.mlx.fast/api/submissions/<uuid>"
curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
  "https://api.mlx.fast/api/benchmarks/1854efdf-feba-4773-bae9-b80520881a74/submissions"
```

Five verdicts must be read **separately**, because a `rejected` receipt can mean
only "did not beat the current best":

| Verdict | Field |
|---|---|
| correctness | `officialMetrics.passed_correctness` |
| error | `officialMetrics.error` |
| decode floor | `officialMetrics.passed_decode_speedup_floor` |
| prefill floor | `officialMetrics.passed_prefill_speedup_floor` |
| ranking | top-level `status` / `promotionStatus` / `rejectionReason` / `officialScore` |

Terminal statuses: `rejected`, `accepted`, `failed`, `promoted`, `superseded`.

---

## 7. Priority insert: the dead `lagunaNormAffineQKV` fusion

The advisor asked for a paired `DARKBLOOM_NATIVE_AFFINE_NVFP4=0` probe on the
grounds that ~40 removable serialization points are worth ≈ 85.5 µs/step ≈
**1.40% of score**. I verified the mechanism in source — it is real, but broader
than described — then decomposed the toggle and measured it. The answer is that
the prize is **negative**, and the bundled toggle costs 16.6% of score. §7.1–7.4
establish the mechanism and the design; §7.5 has the numbers.

### 7.1 The fusion is dead on the shipped default

* `LagunaRuntimeModel.swift:5947` `let fusedTailGateLogits: MLXArray? = nil`;
  `:5950` `let normalized = fusedQKV ?? inputNorm(input)`.
* The guard at `:5926-5931` requires `bits == 8`, plus
  `lagunaFusedNormAffineQKVEnabled` (`env["DARKBLOOM_FUSED_NORM_AFFINE_QKV"] != "0"`,
  `:5482-5483`, default on), `_nativeAffineQKVGateRows == nHeads`, and
  `inputNorm.eps == LagunaConstants.rmsNormEpsilon`.
* `:3049-3054` returns nil three ways (`NVFP4 == "0"`, non-integer `_FROM`,
  `_FROM >= numHiddenLayers`); default `_FROM="0"` ⇒ the NVFP4 branch at
  `:3101-3115` (`groupSize:16, bits:4, mode:.nvfp4`) runs on every layer ⇒
  `bits == 8` is never true ⇒ **the fusion is unreachable as shipped**.
* Under `=0` the fallback at `:3117-3125` is
  `quantized(source, groupSize: 32, bits: 8, mode: .affine)`, which satisfies
  the guard exactly, and gate folding then fires at `:5713-5723`.

### 7.2 The flag is not a clean fusion switch

There is only one read of `DARKBLOOM_NATIVE_AFFINE_NVFP4` in the tree (`:3049`),
but `lagunaNativeAffineWeight` is called for **both** QKV (`:5688-5690`) **and**
o_proj (`:5664`). So `=0` also:

* flips the o_proj bank to INT8;
* flips o_proj kernel selection — NVFP4 `lagunaGatedAffineOProjNVFP4`
  (`:6365-6390`) dies, INT8 `lagunaGatedAffineOProj` (`:6337-6363`) goes live;
* kills the fused gate softplus (`:5989-5991` requires nvfp4/4/16);
* stops the QKV lane-major/narrow NVFP4 scale banks (`:5756-5765`) being built.

`g_proj` is unaffected (`:482-497` hardcodes affine/32/8); MoE and the shared
expert are unaffected. There is **no runtime activation requantization** — all
five `quantized(...)` calls in LRM are weight-prep time under
`prepareFusedRuntimeWeights` (`:11825-11842`).

The arm is therefore numerically different and the goldens are expected to
change. It is already on record as a "verified-reachable positive control only
… never submittable"
(`research/RESEARCH_ARCHIVE_through-round-91.md:676-681`), and this round does
not change that.

### 7.3 My own R91-A already priced these exact 40 dispatches

`research/maple-fern-r91-input-norm-fusion-price.md`, PR #483, W&B `ubjfsywa`,
group `r91-a-input-norm-fusion-price`:

* The bit-exact, confound-free arm added **80 extra dispatches/step** (+19.7%
  dispatch count) at a cost of **+8.61 µs/step busy, 95% CI
  [−17.71, +35.02]**. Halving gives the fusion prize: **≤ 35.02 µs/step at the
  95% upper bound ≈ 0.535% of score**, point estimate ≈ 8.6 µs/step ≈
  **0.13%**. The point estimate is *below* the 0.378% bar and the whole
  interval is ~2.6× under the 1.40% model.
* The −137.13 µs/step "ceiling" from Stage 1a was **routing contamination**:
  deletion arms decode a different token stream, hence different experts. The
  `skipc` control was +934.30 µs/step at identical dispatch and command-buffer
  counts.
* The 56 µs/step dispatch-boundary term **did not materialise**: `gap` moved
  only +1.49 µs/step. The 76.3% serialization share of a boundary is hidden on
  this GPU-bound stream.
* The correct rule-41 constant for a decode input-RMSNorm (4 KB ⇒ TINY) is
  0.7258 µs, so 40 × 0.7258 = **29.0 µs/step ≈ 0.44%** — not 40 × 1.4064 = 56.3
  and not 40 × 2.1379 = 85.5.
* Naive full fusion was already dead on paper at ≈ −115 µs/step, because
  R = 5,120 redundant recomputes.

### 7.4 Decomposed probe design

The advisor's single `=0` toggle bundles the fusion gain with an NVFP4→INT8
quantization change, so `B − A` alone cannot attribute anything. I split it:

| Arm | Environment | Bank | Fusion |
|---|---|---|---|
| **A** | (default) | NVFP4 | dead |
| **B** | `DARKBLOOM_NATIVE_AFFINE_NVFP4=0` | INT8 | **live** |
| **C** | `DARKBLOOM_NATIVE_AFFINE_NVFP4=0 DARKBLOOM_FUSED_NORM_AFFINE_QKV=0` | INT8 | dead |

* **C − A** prices the NVFP4→INT8 confound.
* **B − C** isolates the fusion gain **at matched quantization** — this is the
  number the advisor actually wants.
* **B − A** reproduces the advisor's bundled figure, for comparability.

Driver: `research/fern_r109f_nvfp4_fusion_abba.sh` (`ORDER`/`TAG`
env-overridable, writes
`research/artifacts/fern-r109f/nvfp4-fusion/${TAG}-${slot}-${arm}.{json,log}`,
emits one JSONL record per slot, does not stop on non-zero exit). Analysis:
`research/fern_r109f_nvfp4_fusion_analyze.py`.

Why arms B and C were expected to yield usable timing even if they failed
correctness: in
`--local-iterate` the **timing phase runs before the correctness check**
(`Sources/MLXFastTrustedHarness/LagunaRuntimeLocalIterate.swift:115-199`), and
`localModeFailedPayloadWithEstimatedScore` (`:921-955`) still publishes real
seconds/token plus an estimated score with `passed:false`. The Swift binary
exits 0; `benchmark.sh` exits 1 after `jq -e '.passed == true'`, but the copy to
`SCORE_PATH` happens first. `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1` is therefore
not needed, and I am not setting it.

In the event that did not matter: **all four pilot arms passed correctness**,
130/130 checked steps, with an identical
`golden_hash b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`.
So the INT8-g32 QKV/o_proj bank is greedy-identical to the NVFP4 default on
this prompt, even though it is numerically different. Two notes on that, both
important: per §5.1 a matching golden hash on one prompt is *not* a correctness
claim, and separately, group-32 affine INT8 for `q_proj`/`k_proj`/`v_proj`/
`o_proj` is precisely what the accepted envelope (`TASK.md:78-92`) permits — so
the archive's "never submittable" note may be over-strict about legality. It is
moot, because the direction is catastrophically wrong (§7.5).

### 7.5 Pilot result: the fusion is worth **less than nothing**

`ORDER="W B C A"`, one replicate per arm, sign convention *positive seconds =
slower*, *positive `ns` = better*:

| Contrast | What it isolates | decode | prefill | `ns` |
|---|---|---|---|---|
| **C − A** | NVFP4 → INT8 bank flip (the confound) | **+26.433%** | −1.139% | **−15.890%** |
| **B − C** | **the fusion, at matched quantization** | **+0.346%** | **+2.543%** | **−0.883%** |
| **B − A** | the bundled toggle, as proposed | +26.870% | +1.375% | **−16.632%** |

Three findings:

1. **The bundled toggle is a 16.6% score regression, not a 1.40% gain.**
   Roughly 96% of that is the bank flip, which is exactly what a
   bandwidth-bound decode should do when the QKV and o_proj weights double in
   width from 4-bit to 8-bit and the NVFP4 kernels
   (`lagunaGatedAffineOProjNVFP4`, the lane-major scale banks) are taken out of
   service.
2. **The fusion in isolation is negative.** `B − C` is −0.883% on `ns`: the
   decode axis is 0.35% *slower* and prefill is 2.5% *slower*. Even the most
   generous reading of a single replicate bounds the fusion well away from a
   +1.40%, or even a +0.378%, gain — the sign is wrong on both axes.
3. **The fusion is specifically a prefill pessimization.** Prefill is
   insensitive to the bank flip (`C − A` is −1.1%, i.e. prefill is compute-bound
   rather than weight-bandwidth-bound here) but `B − C` costs 2.5%. The fused
   norm+affine QKV kernel is decode-shaped; with 512 rows it loses to a plain
   RMSNorm plus a batched quantized matmul. Anyone who ever wanted this fusion
   would have to gate it to decode only.

This is exactly why the third arm was worth adding. Without C the only
observable is "the bundle is 26% slower on decode", which is compatible with
"the fusion is worth +1.4% but is masked by a 27% quantization penalty". With C
we can say the fusion itself is worth approximately zero, and if anything
negative.

The result agrees with my R91-A prior (§7.3): point estimate ≈0.13%, 95% upper
bound 0.535%, i.e. indistinguishable from zero at this resolution. It disagrees
with the 1.40% model by both magnitude and sign.

A main palindromic design `W A B C C B A A B C C B A` (13 slots, 4 replicates
per arm, warmup discarded) is running to put a 2σ band on `B − C`. Given the
Stage-0 dispersion, n=4 per arm bounds the decode contrast to roughly ±0.34%,
which is enough to exclude a gain at the ranked bar; it is not enough, and does
not need to be enough, to resolve 0.35% from zero.

This probe is a **positive control for sizing only**. It cannot displace the
composition harness and it will never touch the submission slot. My
recommendation is to close the fusion line: it is dead code whose revival is
worth ≤0 even before the 26% quantization penalty that currently gates access
to it.

---

## 8. Margin-certificate methodology for edward and alphonse

frieren (cadence), nezuko (router selector) and tanjiro (extract-round) are
bit-exact by construction. edward (sliding-attention MMA) and alphonse
(full-attention MMA) are not, so each needs an independent margin certificate.
No new tooling: I reuse
`research/maple-frieren-r106j-margin-certificate.py` (688 lines) under the SOP
in `research/maple-frieren-margin-certificate-service.md`.

```bash
python3 research/maple-frieren-r106j-margin-certificate.py capture \
  --label L --out L.npz [--steps 64] [--mode teacher|free] [--top-k 100352]
python3 research/maple-frieren-r106j-margin-certificate.py certify \
  --baseline A.npz --candidate B.npz --out report.json [--rank-depth 8]
```

Verdicts: any token flip ⇒ **FAIL**; bitwise identical ⇒ **PASS-BIT-EXACT**;
`global_safety_factor = margin.min / pert.abs_max < 10`, or any
`positions_below_10`, or any exact tie ⇒ **MARGINAL**; otherwise
**PASS-WITH-MARGIN**. Campaign constant baseline margin (longcopy-gate-english-512,
teacher, 64 steps): min **0.375**, p1 0.615, p50 6.5, 0 exact ties, against a
bf16 logit step of 0.0625.

Procedure discipline:

* **Null cell first** — two captures of the same arm; the only admissible
  verdict is PASS-BIT-EXACT. Rehearsal at
  `research/artifacts/maple-frieren-r107f/sop/cert_rehearsal_null.json`.
* A shipping arm must be certified as a **rebuild with the source default
  flipped**, not env-gated (§9.2): an env-gated candidate certifies a path the
  official harness never runs.
* §9.1 force-clean deletes `mlx.metallib`; rebuild with
  `tools/build-mlx-metallib.sh`.
* Costs: teacher capture 50 s, free 128-step 75 s, certify <1 s, force-clean
  candidate rebuild 131 s.

Known limits I will state rather than paper over (§8): single case, single
prompt, greedy only, M4 Pro gen-16 only, and **it cannot certify anything inside
the `_nax` prefill kernels**, which are 94.2% of ranked prefill GPU time.
**alphonse's full-attention/prefill MMA may therefore be uncertifiable on this
host**, and if so I will report it as uncertifiable rather than as passing.

Class taxonomy (Rule 102.3, `research/CURRENT_RESEARCH_STATE.md:6229-6238`):
class ≥3 requires a certificate; class 4 (INT8-g32 re-quantization) is unbounded
by any order argument. The only measured class-3 anchor
(`DARKBLOOM_QMV_WIDE_CODES`) came in at max|Δlogit| 5.4453125, global SF 0.0689,
decision-relevant SF 1.3659, 0 flips ⇒ **MARGINAL**.

Quantization envelope (`TASK.md:78-92`): group-32 affine INT8 only, for
`q_proj`/`k_proj`/`v_proj`/`o_proj` and per-head `g_proj`. Inherited gap
(Rule 59): the default decode attention path re-quantizes BF16 q/k/v/o to
group-16 NVFP4 (LRM `:3005-3045` region), which is outside the written
envelope, inherited from promoted frontier `c5b0a13c`. I am not unilaterally
reverting it.

Native margin instrumentation does exist in the trusted harness
(`Sources/MLXFastTrustedHarness/LagunaRuntimeCorrectnessCompare.swift:852-855`
`topLogitMargin`, depth 8 via `Sources/MLXFastCore/Constants.swift:33`) but it
is **outside `editablePaths`** — usable as an instrument, not shippable.

---

## 9. Integration plan (Stage 1 → Stage 2)

Stage 1, by 05:00Z: for each landing arm, cherry-pick onto the integration
branch off `1a6761bf` and **independently re-verify**, not trust the arm's own
report:

1. `validate-assignment-scope.sh` with the arm's submitted paths only;
2. `check-editable-budget.sh`, with explicit attention to the
   `LagunaRuntimeModel.swift` per-file headroom (140,043 B shared);
3. equivalence differential against the base signature in §5;
4. `--local-submit` correctness (1025 checked steps);
5. interleaved paired timing against the Stage-0 baseline, rep1 discarded, `ns`
   reported with its 2σ interval;
6. margin certificate with a null cell first, for edward and alphonse.

Single arm first, then stacked by 10:30Z, **reporting each separately**.
`nezuko × tanjiro` is the highest-risk pair — tanjiro consumes the tournament
`inds` that nezuko rewrites — and gets an explicit joint correctness run rather
than an inference from two single-arm passes.

Stage 2 fires only on advisor authorization: re-verify the queue is idle, then
run `senpai/submit-official.sh` exactly once. If nothing clears the bar I will
say so explicitly at 10:30Z rather than firing a marginal candidate; three
post-`e27f1ce` receipts already show what that costs.

---

## 10. Evidence

* W&B run `k9dv3flw` — `fern-r109f-stage0-baseline`, n=5:
  https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/k9dv3flw
* `research/artifacts/fern-r109f/base-upstream-equivalence.log`
* `research/fern_r109_timing_ledger.py` — paired ledger with `ns`
* `research/fern_r109_budget_forensics.py` — committed-vs-worktree budget
  reconciliation
* `research/fern_r109f_nvfp4_fusion_abba.sh` — decomposed A/B/C probe driver
* `research/fern_r109f_nvfp4_fusion_analyze.py` — three-contrast analyser
* `research/artifacts/fern-r109f/nvfp4-fusion/` — per-slot score JSON and logs
* `research/fern_r109_wandb_log.py` — W&B publisher for paired families

Reproduce the probe:

```bash
ORDER="W B C A" TAG=pilot bash research/fern_r109f_nvfp4_fusion_abba.sh
python3 research/fern_r109f_nvfp4_fusion_analyze.py pilot main
```
