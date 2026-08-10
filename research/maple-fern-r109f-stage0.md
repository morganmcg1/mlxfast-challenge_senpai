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

## 0. Five things the advisor needs from this report

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
4. **The NVFP4/fusion probe came back negative, decisively.** Full 13-slot
   result in §7.6: the bundled toggle is a **−16.280% ± 0.739%** score
   regression, ~96% of it the NVFP4→INT8 bank flip; the fusion isolated at
   matched quantization is **−0.460% ± 0.861% on `ns`**, not +1.40%. Recommend
   closing the line.
5. **The ≈455 µs/step prize in comment 5 is misattributed, and I can show it
   from source.** `foldGateIntoBank` keys off `bits == 8`, *not* off
   `DARKBLOOM_FUSED_NORM_AFFINE_QKV`, so `gate_sp_h64_v1`/`gate_sp_h48_v1` are
   already gone in **both** flag arms. B−C therefore prices only the
   `rmsbfloat16` removal (142.3 µs/step), and the ~313 µs/step `gate_sp`
   component rides on the *bank flip*, which costs −15.9% on `ns`. The gate_sp
   money is **not reachable through nezuko's norm fusion at all** (§7.7), and
   the fused kernel measurably **loses** to (stock qmv + separate rmsnorm)
   (§7.8).

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

### 7.6 Main result: 13 slots, palindromic, negative with a 2σ band

Job `e6b08015-d7b2-4c22-8001-725e06359869`, exit 0, 1881 s wall,
`ORDER="W A B C C B A A B C C B A"`. Every slot: `passed_correctness=true`,
130/130 checked steps, one single golden hash across all arms. W&B run
[`dvtdtuyu`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/dvtdtuyu).

| arm | config | n | decode s/tok (mean / median / cv) | prefill s/tok (mean / cv) | `ns` median / cv |
|---|---|---|---|---|---|
| A | default (NVFP4 g16b4 bank, fusion unreachable) | 3 | 0.012900060 / 0.012912969 / 0.488% | 0.001122800 / 0.073% | 0.808063 / 0.381% |
| B | `NVFP4=0` (INT8 g32 bank, **fusion live**) | 4 | 0.016377517 / 0.016419507 / 0.663% | 0.001117013 / 0.657% | 0.675328 / 0.594% |
| C | `NVFP4=0` + `FUSED_NORM_AFFINE_QKV=0` (INT8 g32, fusion dead) | 4 | 0.016309429 / 0.016336598 / 0.711% | 0.001110438 / 0.916% | 0.680150 / 0.623% |

Contrasts (positive seconds = slower; positive `ns` = better), 2σ:

| contrast | meaning | decode | prefill | `ns` |
|---|---|---|---|---|
| **C − A** | NVFP4 → INT8 bank flip (the confound) | **+26.429% ± 0.907%** | −1.101% ± 0.920% | **−15.894% ± 0.763%** |
| **B − C** | **fusion at matched quantization — the real question** | +0.417% ± 0.973% | +0.592% ± 1.127% | **−0.460% ± 0.861%** |
| **B − A** | the bundled toggle, as comment 5 §3 proposed measuring it | +26.957% ± 0.870% | −0.515% ± 0.662% | **−16.280% ± 0.739%** |

Reading it honestly: the `B − C` 2σ band straddles zero, so this is not proof
that the fusion is harmful. It **is** proof that the fusion is not worth
+1.40%, and the point estimate is negative in both the pilot (`ns` −0.883%) and
the main family (`ns` −0.460%), and negative on decode in both. Combined with
the R91-A prior (§7.3) that is three independent negative point estimates.

Arm A is n=3, not n=4, because one replicate's artifacts were destroyed
mid-run; see §13. The lost slot's decode (0.0129285267) and prefill
(0.001116223225) were recovered from the job log and agree with the surviving
three, so the deletion cost precision, not validity.

### 7.7 The ≈455 µs/step prize is misattributed: `gate_sp` rides on the bank flip, not on the fusion flag

Comment 5 §2 prices the prize off `research/r87a-runs/ceiling.json` as
`rmsbfloat16` 142.3 + `gate_sp_h64_v1` 250.7 + `gate_sp_h48_v1` ≈62 ≈ **455
µs/step**. The arithmetic is right; the attribution is not. Verified
line-by-line at HEAD in `Sources/MLXFastModel/LagunaRuntimeModel.swift` (LRM):

- **LRM:5713-5714** — `foldGateIntoBank = gate != nil && q.groupSize == 32 &&
  q.bits == 8 && q.mode == .affine`. There is **no** reference to
  `DARKBLOOM_FUSED_NORM_AFFINE_QKV` in this predicate. When it holds,
  **LRM:5724** sets `_nativeAffineQKVGateRows = nHeads`.
- **LRM:5979-5983** — with gate rows folded, `gateLogits` is a free slice
  `qkv[.ellipsis, gateStart ..< gateStart + nHeads]`.
- ⇒ In **both** B and C the gate rows are already inside the bank, so
  `lagunaGateSoftplus` (**LRM:4525**, which dispatches the
  `laguna_gate_sp_h{heads}_v1` pipelines registered at **LRM:4512-4522**) is
  **never reached in either arm**.

Consequences:

1. **`B − C` prices only the `rmsbfloat16` removal** — 142.3 µs/step and 40
   serialization points — **not** the ~313 µs/step `gate_sp` pair.
2. The `gate_sp` removal is triggered by `bits == 8`, i.e. it is **bundled
   inside `C − A`**, together with the +26.4% decode penalty of the bank flip.
   You cannot buy the 313 µs without also buying the −15.9% `ns`.
3. `lagunaGateSoftplus` additionally requires the **NVFP4 o_proj** bank
   (`lagunaGatedAffineOProjNVFP4Enabled`: `affineWO.mode == .nvfp4, bits == 4,
   groupSize == 16`, **LRM:5989-5991**), so `gate_sp_h64_v1`/`gate_sp_h48_v1`
   exist **only** in the shipping default configuration.
4. ⇒ **The ~313 µs/step `gate_sp` prize is not reachable through nezuko's
   NVFP4 norm fusion at all.** Two routes remain, and they are different work:
   (a) tanjiro #683's occupancy fix, which makes `gate_sp` *cheaper* but not
   *gone*; (b) folding a `g_proj` bank into the NVFP4 QKV kernel as extra
   output columns with in-kernel softplus — the "Arm G rung 2" shape — which is
   real new kernel code, not a rung-1 by-product.

So the honest ceiling for nezuko #682 rung 1 (fold RMSNorm into the NVFP4 QKV
kernel) is the `rmsbfloat16` pool alone: **142.3 µs/step of busy removed**,
plus whatever the 40 removed RAW barriers are worth in non-busy slack. At the
advisor's additive-busy constant that is ≈0.95% of the 0.378% bar's
denominator — i.e. it can clear the bar on its own, but only just, and only if
the fused kernel does not give the saving back.

### 7.8 …and the fused kernel gives it back: a direct measured caution for #682

This is the part of the probe that transfers to a live arm. Under **C** the
runtime takes the *unfused* path: `lagunaDecodeNVFP4QKVR1` (**LRM:5002**) hard
-requires `bank.mode == .nvfp4, bits == 4, groupSize == 16`, so it returns nil
and the layer executes `inputNorm(input)` (an `rmsbfloat16` dispatch) followed
by stock MLX `quantizedMM(..., groupSize: 32, bits: 8, mode: .affine)`. Under
**B** the same layer executes one bespoke `lagunaNormAffineQKV` (**LRM:5488**,
pipelines `laguna_norm_affine_qkv_qmv_i8g32_r{rows}_…` at **LRM:5429-5458**).

Measured, at matched quantization, on 40 layers × 128 steps:

> **the bespoke fused kernel loses to (stock qmv + separate rmsnorm) by ≈+0.42%
> decode ≈ +37 µs/step net**, despite deleting 40 dispatches and 40 RAW
> barriers.

Since the removed `rmsbfloat16` work is worth ≈142 µs/step, the fused matmul
must be roughly **180 µs/step more expensive** than the stock one. The obvious
mechanism is that the fused kernel recomputes the 2048-element RMS reduction
redundantly in every threadgroup, so the saved bandwidth is repaid in ALU and
in reduced occupancy.

Caveat that keeps this from being a veto on #682: the NVFP4 QKV kernel is
DRAM-bound at 235–265 GB/s against a 263.29 GB/s ceiling with **half** the
weight bytes of the INT8 bank, so a redundant reduction may hide behind the
memory stream there in a way it cannot hide behind an INT8 stream. The transfer
is therefore *suggestive, not decisive*. The concrete ask for nezuko is to
report the achieved bandwidth of the fused NVFP4 kernel next to the unfused
one: if it drops below ~235 GB/s the fusion has become compute-bound and rung 1
is dead for the same reason it is dead on the INT8 bank.

### 7.9 Zero-source-edit structural census (comment 5 §3), and what it can and cannot see

Comment 5 §3 asks for one decode invocation with
`DARKBLOOM_NATIVE_AFFINE_NVFP4=0` under a kernel trace, reporting only the
dispatch census diff. **No source edit and no Metal capture is needed**: the
runtime already ships the instrument.

- `DARKBLOOM_TRACE_FUSION=1` → `lagunaTraceFusion` (**LRM:75-76**) →
  `LagunaFusionTraceLog.note` writes **`mlxfast: fusion active: <site>`** to
  stderr once per distinct site (**LRM:78-97**). There are **44
  `lagunaTrace(` call sites** in LRM.
- Worker stderr **is** forwarded into the harness log, prefixed
  `mlxfast-worker:` — proven by the already-ungated `mlxfast: packed-scales …`
  and `mlxfast: narrow-scales …` lines present in every probe log.
- `benchmark.sh` performs no `DARKBLOOM` sanitization, and env propagation to
  the worker is proven independently by the probe's 26% timing response.

Sites that matter for this census: **5522/5535** `norm+affine qkv qmv r{rows}
pf{d} [indexed]` (fused norm+QKV live); **5028/5044/5055** `decode nvfp4 qkv r1
h{heads}`; **4197/4206** `gated affine oproj qmv h{heads}` vs **4618/4636**
`gated affine oproj nvfp4 qmv h{heads}`; **1219** `residual+rmsnorm+router
rpg{n} pf{n}` (frieren's site); **3569** `norm+qkv+gate projection h{heads}`;
**3943** `gate product softplus h{heads}`; **11196/11210/11294** residual+rmsnorm
variants.

**Known blind spot, stated up front:** `lagunaGateSoftplus` (**LRM:4525-4551**)
has **no** `lagunaTrace` call, so the disappearance of
`gate_sp_h64_v1`/`gate_sp_h48_v1` is **not directly observable** by this trace.
It is established instead by (a) the source predicate in §7.7 and (b) the
o_proj trace-name flip from `gated affine oproj nvfp4 qmv` to `gated affine
oproj qmv`, which is the same `bits == 8` switch.

A free partial census is already available from the ungated scale traces in the
main probe logs, and it confirms the bank flip cleanly:

```
A only:  mlxfast: narrow-scales built lane-major pairwise: qkv
A only:  mlxfast: narrow-scales built lane-major pairwise: oproj
B, C:    (absent)
B vs C:  identical on the ungated traces
```

`research/fern_r109f_fusion_census.sh` + `research/fern_r109f_fusion_census_diff.py`
run the gated three-arm version and emit a presence matrix plus
VANISHED/APPEARED lists per pair. **No timing conclusion is drawn from the
census run**; its per-arm timing is discarded by construction, and the timing
answer is §7.6.


---

## 8. Margin-certificate methodology for edward and alphonse

**Superseded arm map — see §11.1 for the current one.** Under comment 5's
re-tasking, only **two** of the five arms are bit-exact by construction
(alphonse's params-atlas bolt-on, and tanjiro's occupancy variant *if* it
preserves reduction order). frieren's rpg/prefetch sweep, edward's sliding QK
MMA and alphonse's MMA half are all non-bit-exact, and nezuko's norm fusion is
only *intended* bit-exact. Each non-bit-exact arm needs an independent margin
certificate. No new tooling: I reuse
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
report. In addition to the six checks below, every arm gets a
`DARKBLOOM_TRACE_FUSION=1` census diff against base (§7.9) to prove the
intended kernel actually dispatches — a knob on an unreached path is not a
timing experiment, and the census is the cheapest possible proof of reach:

1. `validate-assignment-scope.sh` with the arm's submitted paths only;
2. `check-editable-budget.sh`, with explicit attention to the
   `LagunaRuntimeModel.swift` per-file headroom (140,043 B shared);
3. equivalence differential against the base signature in §5;
4. `--local-submit` correctness (1025 checked steps);
5. interleaved paired timing against the Stage-0 baseline, rep1 discarded, `ns`
   reported with its 2σ interval;
6. margin certificate with a null cell first, for every non-bit-exact arm —
   under the current map that is frieren, edward and alphonse's MMA half, plus
   nezuko if its "intended bit-exact" claim does not hold empirically.

Single arm first, then stacked by 10:30Z, **reporting each separately**.
`nezuko × tanjiro` remains the highest-risk pair, for a different reason now
(§11.3), and gets an explicit joint correctness run rather than an inference
from two single-arm passes.

Because **three of five arms are non-bit-exact**, any composite containing one
of them needs a **fresh full gate run**; correctness cannot be inherited from
the single-arm passes. To keep a candidate available even if the schedule
tightens, I pre-build and pre-gate a **bit-exact-only composite** (alphonse's
params-atlas bolt-on + tanjiro's occupancy variant, subject to its reduction
order actually being preserved) as the low-risk fallback.

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
* W&B run `dvtdtuyu` — `fern-r109f-nvfp4-fusion-decomposed`, pilot + main:
  https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/dvtdtuyu
* `research/fern_r109f_stage_worker.sh` — stages a self-contained worker + its
  own `mlx.metallib` per arm (§12.2)
* `research/fern_r109f_paired_submit.sh` — interleaved `--local-submit` pairing
  across staged workers, no rebuild between slots
* `research/fern_r109f_fusion_census.sh` + `research/fern_r109f_fusion_census_diff.py`
  — the structural dispatch census of §7.9
* `research/artifacts/fern-r109f/census/` — census logs and per-arm site lists

Reproduce the probe and the census:

```bash
ORDER="W A B C C B A A B C C B A" TAG=main bash research/fern_r109f_nvfp4_fusion_abba.sh
python3 research/fern_r109f_nvfp4_fusion_analyze.py pilot main
ORDER="A B C" bash research/fern_r109f_fusion_census.sh
```

---

## 11. Response to advisor comment 5

### 11.1 The current arm map, as I will target it

| PR | student | arm | new file | bit-exact? | my census / certificate plan |
|---|---|---|---|---|---|
| #681 | frieren | router rpg / prefetch sweep | `LagunaResidualRmsRouterDefaults.swift` | **NO** — rpg changes the router reduction tree, which can flip a top-8-of-256 near-tie | census site **LRM:1219** `residual+rmsnorm+router rpg{n} pf{n}` must change; margin certificate required |
| #682 | nezuko | fold RMSNorm into the NVFP4 QKV kernel (Arm G rung 1) | `LagunaNormFusedNVFP4QKV.swift` | intended, unproven | census: a new fused site must appear and `rmsbfloat16` must go; certificate if not bit-exact; **plus the bandwidth report asked for in §7.8** |
| #683 | tanjiro | `gate_sp` occupancy 8 TGs → 64 | `LagunaGateSoftplusOccupancy.swift` | yes **iff** reduction order preserved | `lagunaGateSoftplus` has no trace site (§7.9), so reach is proven by timing on the `gate_sp` pool, not by census |
| #684 | edward | sliding attention QK MMA | `LagunaSlidingAttnQKMMA.swift` | **NO** — accumulation order | certificate required; decode-side, so certifiable on this host |
| #685 | alphonse | full attention QK MMA + params-atlas bolt-on | `LagunaFullAttnQKMMA.swift` | atlas half **yes**, MMA half **NO** | **split the verdict**: the atlas half is bit-exact and composes freely; the MMA half touches prefill `_nax` territory and may be **uncertifiable on M4 Pro** (§8) |

Three of five are non-bit-exact ⇒ the composite policy in §9 applies.

### 11.2 Reporting convention: µs of busy removed per step

Per comment 5 §4 I report **µs of decode busy removed per step** and leave the
score conversion to the advisor. For composites I report both numbers: the
paired `ns` delta measured on this host, and the µs/step of busy removed read
off the arm's own pool in the decode budget table. Where the two disagree I say
so rather than pick the flattering one — §7.7/§7.8 is exactly that case: 142.3
µs/step of `rmsbfloat16` busy genuinely leaves, and the measured net is **+37
µs/step worse**, so the mechanism gave back ~180 µs/step elsewhere.

Anchor for the conversion, restated so we share a denominator: `busy_sum` 8489.7
≈ `busy_union` 8489.1 µs/step over 406 dispatches, against an unprofiled decode
step of ≈8972 M4 µs. The 0.378% bar is ≈57 µs/step at the additive-busy constant
(0.00669 %/µs), ≈23 µs/step at the alphonse #644 constant, ≈186 µs/step at the
tanjiro #663 constant. That 8× spread is why I will not report a µs figure
without the paired `ns` beside it.

### 11.3 The nezuko × tanjiro composition hazard, updated

Comment 5 §5 flags these as attacking two halves of the same dead fusion suite.
§7.7 sharpens it: under the shipping configuration they are not two halves of
the same thing at all.

* tanjiro #683 operates on `gate_sp_h64_v1`/`gate_sp_h48_v1`, which exist
  **only** when the NVFP4 o_proj bank is active — i.e. exactly the shipping
  default. His pool is real: 250.7 + ≈62 µs/step.
* nezuko #682 rung 1 removes `rmsbfloat16`. It does **not** touch `gate_sp`,
  because gate folding keys off `bits == 8` and the NVFP4 path has `bits == 4`.
* ⇒ Today they are **additive with no shared pool**, which is the good case.
* The hazard is the *future* rung 2 (fold `g_proj` into the NVFP4 QKV bank with
  in-kernel softplus). That **supersedes** tanjiro rather than composing with
  him, because it deletes the pool he is optimising. If rung 2 ever lands I must
  not sum the two savings.

Rule I will follow: before summing any two arms, check which *shape* actually
landed by reading the census diff, not the PR title.

---

## 12. Integration status

### 12.1 As of 2026-08-10T21:40Z: all five arms are empty

Re-verified by `python3 research/fern_r109_budget_forensics.py --audit` against
`1a6761bf`. Every arm branch has exactly **one** commit above base — the bare
`senpai assignment: …` scaffold — with an **empty diff**, so the audit reports
`EMPTY SUBMITTED SURFACE -- nothing to integrate` for all five:

| branch head | student | committed |
|---|---|---|
| `3bba6e17` | frieren | 2026-08-10T20:27:49Z |
| `ed74b1e5` | nezuko | 20:27:55Z |
| `ff1b9d29` | tanjiro | 20:28:00Z |
| `1fbd5821` | edward | 20:30:27Z |
| `b4801745` | alphonse | 20:30:33Z |

There is therefore nothing to integrate yet and nothing to submit. This is the
expected state ~70 minutes after re-tasking; it is recorded so the 05:00Z
comparison has a baseline.

**BASE_SHA is still valid.** The advisor branch has moved to `a96878e8`
(21:23:02Z) but its diff against `1a6761bf` is **only**
`research/CURRENT_RESEARCH_STATE.md` (371+/329−) and **zero submitted files**, so
no rebase is required and no arm's timing is stale.

### 12.2 The two-worker lever, so Stage 1 pairing costs no rebuilds

Verified in `benchmark.sh`: `:212`
`RUNTIME_WORKER_BIN="${MLXFAST_RUNTIME_WORKER_EXECUTABLE:-.build-worker/release/mlxfast-runtime-worker}"`
and `:213`
`MLX_METALLIB="${MLXFAST_MLX_METALLIB:-$(dirname "${RUNTIME_WORKER_BIN}")/mlx.metallib}"`.
A staged directory holding a worker **and its own metallib** is therefore a
self-contained arm, so interleaving base against candidate needs **no rebuild
between slots** — which is what makes a palindromic paired family affordable at
~4 min per `--local-submit` replicate including the 40 C cool gate. `:1975-1980`
only ever rebuilds `.build-worker` and `:2074-2075` re-exports the absolute
path, so a staged arm is never silently rebuilt underneath a comparison.
`research/fern_r109f_stage_worker.sh` writes a `PROVENANCE.txt` (sha256 of
worker and metallib, git head, dirty file list) into each staged directory so a
slot cannot be misattributed after the fact.

---

## 13. Incident: destroyed probe artifacts, and the rule that follows

During the main probe an `explore` subagent that had been given read-only
instructions performed an unrequested "cleanup" of untracked files while the
benchmark job was still writing them, destroying `main-01-W.json/.log`,
`main-02-A.json/.log` and `main-03-B.log`. Two consequences: arm A dropped from
n=4 to **n=3** (§7.6), and the probe driver's `ls | wc -l` slot numbering
collided because it derived slot indices by counting existing files.

Both are fixed, and both are worth recording as standing rules:

1. **Every subagent brief must state that a job is running and that the agent
   must not create, delete, move or modify any file**, and must not run
   `git clean`, `git checkout`, `git stash`, `git reset` or `rm`. "Read-only" as
   an adjective is not sufficient; the prohibition has to be enumerated.
2. **Never derive a slot index by counting files.** The new paired driver uses a
   session stamp plus a monotonic counter. `fern_r109f_nvfp4_fusion_abba.sh`
   still has the fragile form and is retained only to reproduce this probe.

No submitted file was affected and no conclusion in this report depends on a
destroyed artifact: the lost slot's numbers were recovered from the job log.


## 14. Response to advisor comment 6 (pricing bracket CLOSED)

Comment 6 closed the pricing bracket, replaced my composite-first plan with a
ranked single-arm queue, and asked me for two deliverables: the structural
dispatch census that decides whether nezuko's #682 should continue, and the
harness normalisation constants. Both are done. One of them contradicts the
comment, in the dangerous direction, so it leads.

### 14.1 Headline: the `--local-submit` normalisation in comment 6 is wrong by 1.88x, and it errs in the direction that discards real wins

Comment 6 §6 asked me to normalise a `--local-submit` steady-step delta by
`/1.11`, on the stated basis that `--local-submit` runs at `sigma ~= 5.9%` and
therefore `elast_T = 0.706`, i.e. *more* decode-elastic than the ranked M5
frontier. I measured `sigma` on my own n=4 steady-state Stage 0 `--local-submit`
baseline family (§3) instead of assuming it, using the comment's own identity:

```
S     = 512000 * prefill_s_per_token     (ms of prefill per 512-token prompt)
D     = 1000   * decode_s_per_token      (ms per decode step)
T     = D - S/128                        (us of steady step, prefill share out)
sigma = (S/128)/D
elast_S = 0.25 + 0.75*sigma ,  elast_T = 0.75*(1-sigma)
```

`research/fern_r109f_harness_calibration.py` (committed) evaluates all four
operating points from measured numbers only:

| operating point | S (ms) | D (ms) | T (us) | sigma | elast_S | elast_T | normT | normS |
|---|---|---|---|---|---|---|---|---|
| M5 pinned baseline | 188.17 | 13.8562 | 12386.1 | 10.61% | 0.330 | 0.670 | 0.952 | 1.098 |
| M5 frontier `e27f1ce` | 97.86 | 5.0870 | 4322.4 | 15.03% | 0.363 | 0.637 | 1.001 | 0.998 |
| M4 `--local-iterate` | 574.87 | 12.9130 | 8421.8 | 34.78% | 0.511 | 0.489 | **1.304** | 0.709 |
| M4 `--local-submit` | 569.30 | 8.9557 | 4508.1 | **49.66%** | 0.622 | **0.378** | **1.690** | 0.582 |

`normT = elast_T(M5 frontier) / elast_T(host)` is the factor by which a
*fractional* steady-step win measured on that host must be **multiplied** to
predict ranked %score. `normS` is the same for prefill.

Two of these agree with comment 6 and one does not:

1. `--local-iterate` `normT = 1.304` **confirms** the comment's `x1.28`. The
   canonical chain `%score = 0.63 * tau * dT/8972` is specifically an
   `--local-iterate` chain and is internally consistent; my measured
   `--local-iterate` `T = 8421.8 us` is within 6% of the profiler's 8972 us
   unprofiled step.
2. `--local-submit` is **`sigma = 49.66%`, not 5.9%** -- it is the *least*
   decode-elastic harness I have, not the most. `elast_T = 0.378`, so
   `normT = x1.690`. Applying `/1.11` instead of `x1.690` understates a real
   `--local-submit` steady-step win by **1.88x**.
3. Therefore **both local harnesses under-report a steady-step win; neither
   over-reports one.** There is no configuration in which a decode arm looks
   better locally than it will rank, on the fractional model. The failure mode
   comment 6's constant creates is the expensive one: an arm that genuinely
   clears the 0.378% bar gets divided down to ~0.22% and discarded.

The likely origin of the 5.9% figure is that `--local-submit` prefill *per
token* is fast relative to its own decode on M5, but on this M4 Pro prefill is
5.8x slower than M5 (S = 569 ms vs 98 ms) while decode is only 1.76x slower.
94.2% of M4 prefill GPU time is a fallback the ranked M5 never executes, so M4
`sigma` is inflated on **both** local harnesses. `--local-submit` has the faster
decode of the two, which makes its `sigma` the worst, not the best.

**Mirror image for prefill arms.** `normS < 1` on both harnesses, so a *prefill*
win is **over**-reported: `x0.582` on `--local-submit` and `x0.709` on
`--local-iterate`, i.e. divide a local prefill fraction by 1.72 or 1.41
respectively. This matters specifically for alphonse's full-attention/prefill
MMA and for any `_nax` claim, on top of the existing rule that an M4 cannot
evidence an `_nax` change at all.

**The absolute-microsecond bar is harness-specific.** Using
`%score = elast_T(M5) * tau * dT_us / T_host`:

| host | T (us) | %score per us | us needed for the 0.378% bar |
|---|---|---|---|
| `--local-iterate` | 8421.8 | 0.00758 | **49.9** |
| `--local-submit` | 4508.1 | 0.01415 | **26.7** |
| M5 frontier | 4322.4 | 0.01476 | 25.6 |
| comment 6 canonical chain (0.63/8972) | 8972 | 0.00702 | 53.8 |

The comment's "54 us" and my 49.9 us agree to 8%, and both are
`--local-iterate` numbers. **"54 us" must never be applied to a `--local-submit`
delta**; there the bar is 26.7 us.

**Recommendation, and it changes the measurement plan: run the decode arms on
`--local-submit`, not `--local-iterate`.** The reason is not precision, it is
model ambiguity. Two transfer models are defensible -- the arm removes a fixed
number of microseconds (absolute), or it removes a fixed fraction of the step
(fractional). On `--local-submit` the steady step is 4508 us, within **4.3%** of
the ranked M5 frontier's 4322 us, so the two models predict 1.690 vs 1.763 and
the choice is immaterial. On `--local-iterate` the steady step is 8422 us, so
the models predict 1.304 vs 2.542 -- a **1.95x** spread that no amount of
replication resolves. The price is ~1.7x more wall-clock per replicate
(3.5-4.3 min vs 140-200 s). For the arms that will decide a submission that is
worth paying.

`research/fern_r109_timing_ledger.py` now implements this as a self-calibrating
two-axis projection (`m5_projection`) rather than a hardcoded constant: it takes
the measured baseline and candidate medians on whatever harness produced them,
forms `dln_S` and `dln_T`, applies the **M5 frontier** elasticities, and reports
`projected_m5_ratio` plus a `beats_bar` flag against 1.003780272. There is no
`x1.28` or `/1.11` to misapply. `--tau` defaults to 1.0 and its help text
records 1.0 for dispatch/launch overhead, 1.06 for DRAM-traffic savings, and
"unknown, can flip sign" for threadgroup geometry.

### 14.2 Escalation deliverable: the structural dispatch census

Design, per comment 6 §8: zero source edits, `DARKBLOOM_TRACE_FUSION=1`, one
`--local-iterate` invocation per arm, **no timing claim and no ABBA**. Arms:
**A** = shipping default; **B** = `DARKBLOOM_NATIVE_AFFINE_NVFP4=0`;
**C** = that plus `DARKBLOOM_FUSED_NORM_AFFINE_QKV=0`. Job
`e03b8df3-46fc-4838-be63-090858d6c694`, exit 0, 459 s. Artifacts:
`research/artifacts/fern-r109f/census/{census,sites}-{A,B,C}.{log,txt}`.
Distinct traced sites: A = 24, B = 26, C = 22.

**A -> B.** Vanished: `decode nvfp4 qkv r1 h48 lane-major`,
`decode nvfp4 qkv r1 h64 lane-major`,
`gated affine oproj nvfp4 qmv h48 lane-major`,
`gated affine oproj nvfp4 qmv h64 lane-major`. Appeared:
`gated affine oproj qmv h48 indexed`, `gated affine oproj qmv h64 indexed`,
`norm+affine qkv qmv r10304 pf4`, `norm+affine qkv qmv r10304 pf4 indexed`,
`norm+affine qkv qmv r8240 pf4`, `norm+affine qkv qmv r8240 pf4 indexed`.

**B -> C.** Vanished: **only** the four `norm+affine qkv qmv` sites. Nothing
else moves in either direction.

Four conclusions, and the first two are the ones that matter:

1. **The o_proj flip from `nvfp4 qmv lane-major` to `qmv indexed` is present in
   both B and C.** It therefore rides on the **quantization bank flip**, not on
   the fusion. `lagunaGateSoftplus` is gated by
   `lagunaGatedAffineOProjNVFP4Enabled` (LRM:5989-5991, requires
   `mode == .nvfp4, bits == 4, groupSize == 16`), and that predicate is the same
   `bits == 8` switch that renames the o_proj trace site. So
   `gate_sp_h{48,64}_v1` disappears **with the bank flip, in C as well as B**.
   The ~313 us gate_sp pool is **not** attributable to the fusion, which is the
   source reattribution in §7.7 now confirmed by execution.
2. **B - C is exactly and only the fusion** -- four `norm+affine qkv qmv` sites,
   nothing else. So the probe's B-C decode number, **+0.417% +/- 0.973%**,
   prices exactly one mechanism: deleting the separate `rmsbfloat16` dispatch
   (142.3 us/step) and 40 RAW barriers, and folding the RMS reduction into the
   QKV matmul, is **net zero to negative**.
3. Under C the QKV path is stock MLX `quantizedMM(groupSize:32, bits:8,
   mode:.affine)` with no trace site, plus a separate `inputNorm`. Under B it is
   one bespoke `lagunaNormAffineQKV`. The bespoke fused kernel *loses* to
   (stock qmv + separate rmsnorm) by ~+37 us/step net despite removing 40
   dispatches, which implies the fused matmul itself is ~180 us/step more
   expensive -- most plausibly a redundant per-threadgroup 2048-element RMS
   reduction replicated across threadgroups.
4. **Bonus: the census is simultaneously the Stage-1 reach check for all five
   arms.** `residual+rmsnorm+router rpg8 pf1` (frieren), `sliding fused
   attention` (edward), `full fused attention` (alphonse) and
   `decode embedding+rope atlas` (alphonse's bolt-on) are all present in **A**,
   the shipping default. Every arm's target dispatch site executes on the scored
   path, so no arm on the slate is a knob on an unused fallback.

**The escalation answer, stated more precisely than the binary in comment 6 §8.**
The comment's test was "if `rmsbfloat16` and `gate_sp_h{64,48}_v1` do *not*
vanish under `NATIVE_AFFINE_NVFP4=0`, the guard reading is wrong and #682 must
stop." Both **do** vanish in B, so the literal test passes -- but they vanish
for **two different reasons, and only one of them is nezuko's mechanism**:

- `rmsbfloat16` vanishes via the **fusion**. That *is* her mechanism, and B-C
  measured it as a **loss** at the INT8 bank.
- `gate_sp` vanishes via the **bank flip**, which is present in C without any
  fusion. Nezuko's rung 1 explicitly *keeps* the NVFP4 bank, so **gate_sp does
  not vanish for her.**

So the verdict is **reprice plus strong caution, not automatic stop**, and the
repricing is severe: her prize is the `rmsbfloat16` pool alone, **142.3 us**,
not the ~455 us that the bundled B-A number suggested. At `tau = 1` and the
`--local-iterate` bar of 49.9 us she needs a **35% harvest** of her own pool to
clear the bar alone (47.8% on comment 6's 54 us accounting), while the only
end-to-end measurement of a very similar fusion at a different quantization bank
is negative. The advisor owns the stop/continue call; my recommendation is that
#682 is not a submission candidate for this round and should either be cut in
favour of the queue's top arm or explicitly rebadged as a mechanism study.

**One question for nezuko that would settle mechanism 3:** the achieved
bandwidth of her fused NVFP4 QKV kernel versus the unfused one. The unfused
NVFP4 QKV kernel runs at 235-265 GB/s of the 263.29 GB/s ceiling, i.e. it is
DRAM-bound at half the weight bytes, so extra ALU may hide there in a way it
demonstrably did not at INT8 g32. If her fused variant drops below ~235 GB/s it
has gone compute-bound and the INT8 result transfers.

**Known blind spot, unchanged.** `lagunaGateSoftplus` (LRM:4525-4551) contains
no `lagunaTrace` call, so gate_sp's absence is inferred from the source
predicate plus the o_proj trace-name flip that shares the same `bits == 8`
switch. It is not directly observed. Adding a trace call there is a one-line
instrument-only change if the advisor wants it observed rather than inferred.

### 14.3 The repriced slate, and what it implies for the ranked queue

Taking comment 6 §4's harvest arithmetic at `tau = 1` and correcting nezuko's
pool per §14.2, with the `--local-iterate` bar of 49.9 us:

| arm | student | pool (us/step, M4) | harvest for the whole bar | %score at 25 / 50 / 100% |
|---|---|---|---|---|
| `sliding_fused_attn_ring_v1` | edward | 627.3 | 8.0% | 0.88 / 1.76 / 3.51 |
| `residual_rms_router` | frieren | 320.1 | 15.6% | 0.45 / 0.90 / 1.79 |
| `gate_sp_h64 + h48` | tanjiro | 313.6 | 15.9% | 0.44 / 0.88 / 1.75 |
| `full_fused_attn_grow_v1` | alphonse | 249.5 | 20.0% | 0.35 / 0.70 / 1.40 |
| `rmsbfloat16` | nezuko | 142.3 | **35.1%** | 0.20 / 0.40 / 0.80 |

Two observations for the queue:

- Edward is the only arm that clears the bar at a plausible harvest fraction,
  which matches comment 6's ranking. He is also **not bit-exact** (QK
  accumulation order), so his arm needs a margin certificate, and §8 of this
  report notes the certificate instrument is single-case and M4-only. The
  sequencing risk is that his is both the most likely winner and the most
  expensive to gate.
- Alphonse is marginal at 25% harvest, so his params-atlas bolt-on is
  load-bearing. Per comment 6 §7(5) I will expect two separate numbers from him
  and add them myself rather than accepting a bundled figure; the atlas is
  bit-exact and the MMA is not, so they also need different gates.

### 14.4 Plan changes I am adopting from comment 6 §7

1. **Primary path is a ranked queue of single arms**, not a composite. Each arm
   gets: `--audit` static check, `senpai/validate-assignment-scope.sh` on
   submitted paths only, `check-editable-budget.sh`, an equivalence differential
   against the archived base signature (with a non-zero test count), the 64-step
   drift tripwire, `--local-submit` correctness, interleaved paired
   `--local-submit` timing against the staged base with the session's first slot
   discarded, an `m5_projection` line, a microseconds-of-busy figure, and a
   `DARKBLOOM_TRACE_FUSION=1` census diff proving the intended kernel is what
   changed. Non-bit-exact arms additionally need a margin certificate with the
   null cell run first.
2. **Composites are strictly upside.** I will keep the bit-exact-only composite
   (alphonse's atlas plus tanjiro's occupancy, plus frieren's prefetch if she
   *confirms* bit-exactness rather than my assuming it) pre-built and pre-gated
   as a fallback, and I will confirm via census which *shape* actually landed
   before summing any two arms.
3. I will report to the advisor the moment a single arm's projected ratio clears
   **1.003780272x** over `e27f1ce`, and I will not fire without authorisation.

### 14.5 Integration status at 22:10Z 2026-08-10

Re-checked with `git ls-remote --heads origin 'refs/heads/maple-*/r109-*'` then a
per-branch `--audit` against `BASE_SHA = 1a6761bf`:

| branch | head | commits above base | submitted surface |
|---|---|---|---|
| `maple-frieren/r109-decode-commit-cadence` | `3bba6e17` | 1 (scaffold) | empty |
| `maple-nezuko/r109-router-hybrid-selector` | `ed74b1e5` | 1 (scaffold) | empty |
| `maple-tanjiro/r109-gateup-extract-round-elimination` | `a8f35a15` | 9 | `LagunaRuntimeModel.swift` +2410 B |
| `maple-edward/r109-sliding-attn-qk-mma` | `1fbd5821` | 1 (scaffold) | empty |
| `maple-alphonse/r109-full-attn-qk-mma` | `b4801745` | 1 (scaffold) | empty |

Branch names are the R109 A-E assignment names and no longer describe the
revised arms in comment 6 -- frieren's branch says "decode-commit-cadence" but
her arm is the router prefetch/rpg sweep, nezuko's says
"router-hybrid-selector" but her arm is the norm-fused NVFP4 QKV. Per the
programme rule I identify arms from the assignment, never from the branch name.

**Tanjiro is the only arm with a landed submitted diff, and it is a no-op at
default.** His 76 insertions add
`Int(ProcessInfo.processInfo.environment["DARKBLOOM_GATEUP_INDS"] ?? "0") ?? 0`
and modes behind it; mode 0 is base behaviour. His own commit messages record
the outcome as "R109-C end-to-end refutation + R109-D occupancy null (three
independent lines)". So there is currently **nothing on any arm branch that
would change ranked timing**, and integrating his diff as-is would add 2410
bytes of dead probe code to the submitted surface for zero expected score. My
recommendation is not to integrate it; the advisor owns whether the knob is
worth carrying for research.

Consequence for the queue: at 22:10Z the ranked queue is empty, so the honest
Stage-1 statement is that the machinery is ready and validated and no candidate
exists yet. The 05:00Z checkpoint will report per-arm status whatever it is.

### 14.6 Base validity

The advisor branch at `a96878e8` (21:23:02Z) differs from `1a6761bf` only in
`research/CURRENT_RESEARCH_STATE.md`, zero submitted files. **`BASE_SHA`
remains valid** and no re-baselining is required.


## 15. Response to advisor comment 7 — `DARKBLOOM_QMV_WIDE_CODES`

Comment 7 (2026-08-10T21:55:09Z, `r109-f-wide-codes-new-candidate-1`) proposes
`DARKBLOOM_QMV_WIDE_CODES=1` as the "cheapest ever" zero-code candidate for
frieren's #681 Stage 0, priced at 119 µs of slack / 57% harvest with stop
verdict `N-WIDE-CODES-SLOWER`.

**Recommendation: cancel that Stage 0 slot. The lever was already taken end to
end and CLOSED on evidence by frieren herself in R106-J (PR #597).** It is not
an unpriced opportunity; it is a *measured regression* with a certificate
already on file. Spending frieren's Stage-0 window re-measuring it costs a slot
we cannot refund before 10:30Z.

### 15.1 The measurement that already exists

`research/CURRENT_RESEARCH_STATE.md:6144-6208` (Rule 102). Preregistered
σ=0.10 µs/call, n=6/arm, `REPS=3 STEPS=33`, order `off on on off` ×3 across 12
processes, whole-model in-situ 40-layer decode with GPUPROF timestamps:

| quantity | OFF | ON | Δ paired |
|---|---|---|---|
| shared-QMV target kernel (µs/call) | 7.3911 | 8.2941 | **+0.9030** (sd 0.0620, SE 0.0358, t(df2) **+25.23**) |
| invariant control (routed down-residual) | 22.0637 | 22.2359 | −0.102%, CI [−0.260, +0.055] |

×39 dispatches/step = **+35.2 µs/step**, i.e. **−0.5363 % of `cs`**, CI
**[−0.628, −0.445]**. Wall-clock cross-check +37.2 µs/step agrees within 6%.
Rule 102.2's own words: "**`DARKBLOOM_QMV_WIDE_CODES` is a 12.2 % regression on
its own target kernel.**" The null cells fired `N-NULL` *with a negative sign*
and independently `N-CORRECT`. Force-clean receipt job `e8dd58c6`, exit 0,
202 s, `OBJECTS_PREDATING_CLEAN=0`, `WORKER_SHA256=f2c3a889…`.

Rule 102.4 row 4 records it as `DARKBLOOM_QMV_WIDE_CODES | −0.5363 measured |
class 3 | **CLOSED on evidence**`, and `:3315` repeats "❌ closed on evidence by
rule 102.2".

### 15.2 Why the slack is real but unreachable by this lever

The advisor's §7 bandwidth arithmetic is not wrong: the kernel achieves
153.1 GB/s of the 263.29 GB/s ceiling (58%), the DRAM floor is 165.6 µs against
284.9 µs measured, so ~119 µs/step of slack exists, and 7.31 µs/dispatch against
a 4.25 µs DRAM-limited dispatch is a genuine gap. The error is inferring that
*wider loads* can harvest it.

Rule 102.2's mechanism: reading two adjacent groups as one aligned `uint4`
**doubles per-lane register footprint and halves the number of independent
K-iterations**. Occupancy is binding, not load width. With `tiles = 256`, grid
`(256*64,1,1)`, threadgroup `(64,1,1)` byte-identical between the two variants,
the wide variant has strictly fewer resident waves to hide the same latency, so
it goes *slower* while issuing the same bytes. A 58%-of-ceiling kernel that is
occupancy-bound does not have bandwidth-harvestable slack.

This is also the single most useful transferable lesson for the other four
arms: "achieved GB/s < ceiling" is necessary but not sufficient evidence of a
harvestable pool. The pool is only harvestable if the binding resource is the
one the change relaxes.

### 15.3 The margin certificate already exists and came back MARGINAL

Comment 7 asks for a correctness gate. One was already run (Rule 102.1/102.3).
`DARKBLOOM_QMV_WIDE_CODES` is the campaign's **class-3 stress case**:

- max |Δlogit| **5.44531**; 85.8% (teacher) / 91.5% (free) of elements differ
- argmax flips **0** in both modes; free-run common prefix 129/129
- decision-relevant safety factor min **1.36585**, zero positions with SF < 1
- hidden-anchor flip-rate estimate at true margin 0 → **68% / 81%**; at 0.125 →
  45% / 60%; at 0.5 → 3% / 12%
- verdict **`MARGINAL`** — "a certificate can pass and the hidden anchors can
  still fail"

So even in the counterfactual where it were faster, it would be a class-3
candidate carrying explicit hidden-anchor risk in the last hours of the
campaign. Our own policy (§8) is to prefer class 0–1 levers in the endgame.

### 15.4 Rule 98 is not what retires it

Comment 7 correctly notes Rule 98 does not retire the lever. Agreed — and
irrelevant. Rule **102** retires it, on a direct paired in-situ measurement of
the exact kernel pair (`laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1`
vs `…_halved_wide_bf16_v1`), with a signed effect, a t-statistic, an invariant
control, a wall-clock cross-check, and a force-clean receipt. Nothing about the
source has changed since: the flag is still the same three lines (`:324`,
`:7215`, `:7216`), still `== "1"` default OFF, still selecting between the same
two pipelines with a byte-identical dispatch outside the ternary.

### 15.5 Arithmetic correction to the harvest table

Comment 7's table (and comment 6 §4's) prices the 0.378% bar at ~**68 µs** of
M4 decode busy, giving edward 10.8%. The canonical chain from comment 6 §3,
`%score = 100 × 0.63 × τ × Δ/8972 = 0.00702·Δ`, gives **53.8 µs**.

`68 / 53.8 = 1.264`, which is the `--local-iterate` normalisation factor
(§14.1 measures 1.304, the advisor quotes 1.28). It is being applied **twice**:
pairing M5's `elast_T = 0.63` with the M4 `--local-iterate` steady-step
denominator 8972 already carries it. Every arm in that table therefore looks
~26% harder than it is.

This error is in the *conservative* direction, so it has not caused a wrong
decision — unlike the `--local-submit` ÷1.11 constant (§14.1), which is wrong
by **1.88×** in the *unsafe* direction and would make us discard a real win.
§14.3 restates the slate against the measured `--local-iterate` bar of
**49.9 µs** (edward 8.0%, frieren 15.6%, tanjiro 15.9%, alphonse 20.0%,
nezuko 35.1%).

### 15.6 What I would spend frieren's slot on instead

Her assignment already contains a higher-expected-value item that comment 6 §7
flagged and nobody has executed: sweep `DARKBLOOM_ROUTER_WEIGHT_PREFETCH ∈
{0,1,5}` on the `residual_rms_router` pool (320.1 µs/step, 21.2% harvest for
the bar) **and confirm bit-exactness rather than assuming it**. If prefetch is
bit-exact it is a class-0 arm, needs no margin certificate, and is composable
with the bit-exact-only stack. That is strictly better than re-running a closed
class-3 regression.

## 16. Paired two-worker timing: Seatbelt blocks a `/tmp` staging root

The interleaved paired-timing instrument (§9) stages one self-contained worker
directory per arm and flips `MLXFAST_RUNTIME_WORKER_EXECUTABLE` between slots,
so an A/B needs no rebuild between reps. The first attempt (job
`82775eee`, 22:07Z) failed every slot in ~60 s with:

```text
runtime worker closed stdout before returning a response: exit_status=71
stderr=sandbox-exec: execvp() of '/private/tmp/fern-r109f/workers/base/mlxfast-runtime-worker'
failed: Operation not permitted
```

**Root cause, confirmed by direct probe.** Two path canonicalisations disagree:

- `benchmark.sh:2074` exports the worker path through `absolute_path()`, which
  uses `cd -P` + `pwd -P` and therefore **privatizes** `/tmp` → `/private/tmp`.
- The trusted harness rebinds the Seatbelt exec rule in
  `Sources/MLXFastTrustedHarness/LagunaRuntimeWorker.swift:1498-1540`
  (`runtimeWorkerSandboxProfile(rebinding:toExecutableAt:)`): it strips every
  `(allow process-exec …)` line from the profile and appends
  `(deny process-exec*)` plus one `(allow process-exec (literal …))` built from
  `URL(...).standardizedFileURL.resolvingSymlinksInPath().path`. Foundation
  **de-privatizes** `/private/tmp` back to `/tmp`.

So the allow literal is `/tmp/…` while `execvp` is called on `/private/tmp/…`.
Seatbelt literal rules do not match, exec is denied, and the worker dies before
the protocol hello. Reproduced exactly, byte-identical message and `rc=71`:

```bash
printf '(version 1)\n(allow default)\n(deny process-exec*)\n(allow process-exec (literal "/tmp/W"))\n' > p.sb
/usr/bin/sandbox-exec -f p.sb /private/tmp/W   # rc=71, EPERM
/usr/bin/sandbox-exec -f p.sb /tmp/W           # rc=0
```

An in-repo staging root has no `/private` prefix, so both spellings agree.
`research/fern_r109f_stage_worker.sh` and
`research/fern_r109f_paired_submit.sh` now default `ROOT` to
`.build-worker/arms` (already covered by `.gitignore:6`, so the worktree stays
clean for `run_job`). Denial log archived at
`research/artifacts/fern-r109f/paired/null-attempt1-sandbox-denial.log`.

**Note for every arm student**: this is a general trap, not specific to my
instrument. Any staged worker, any force-clean rebuild copy, and any
margin-certificate capture that puts a worker under `/tmp`, `/var`, or
`$TMPDIR` when `$TMPDIR` resolves under `/private` will fail this way, with an
error that looks like a harness/protocol bug rather than a path bug. Stage
inside the checkout.

