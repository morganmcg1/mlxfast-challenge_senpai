SENPAI-RESULT: {"terminal":false,"status":"in_progress","pending_arms":true,"wandb_run_ids":[],"primary_metric":{"name":"official_m5_score","available":false,"value":null},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

# R91-B — ranked M5 receipt for the current base, plus a fidelity control

- **Student / PR:** `maple-tanjiro` / [#486](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/486)
- **Assignment / revision:** `maple-r91-b-ranked-base-receipt` / `r91-b-rev1`
- **Decision:** *pending — receipts in flight*
- **`BASE_SHA`:** `30f752df890de58d9d98382505c95f2008591101`
- **Submitted candidate files:** **none.** Both arms are zero-edit.
- **Supporting files (research-only, not submitted):**
  `research/r91b-runs/note-armR.md`, `research/r91b-runs/note-armF.md`,
  `research/r91b-runs/log_wandb.py`, `research/r91b-runs/armR-local-submit.log`,
  `research/r91b-runs/armR-local-submit.metrics.json`, this report.
- **Official submission `--model` value:** `senpai` (accepted; no fallback required)
- **Explicit API model-value rejection:** none
- **Assignment-scope preflight:** not applicable — `senpai/validate-assignment-scope.sh`
  is unnecessary because the assignment forbids editing any `editablePaths` file
  and the diff over `Sources Vendor benchmark.json` is empty for both arms.
- **Editable bytes / headroom / growth:**
  `current=2891164/3000000 headroom=108836 growth=0/262144 files=141`
  (`senpai/check-editable-budget.sh 30f752df890de58d9d98382505c95f2008591101`)
- **Scored-path reachability:** not applicable — no control was introduced. The
  purpose of the experiment is measurement of an unmodified tree.

## 1. Arm identity

| arm | commit | role |
| --- | --- | --- |
| **R** | `30f752df890de58d9d98382505c95f2008591101` | research base at assignment time (organizer frontier + `float4` merge epilogue + source-file carve) |
| **F** | `6ada66c92d9c5007e8499cfbf43546720b015426` | pure organizer-frontier adoption; fidelity control |
| **C** | `8486638578a283de40369172f68c3a4d2d6a5365` | newest base = R + #475 router-weight cross-barrier prefetch |

**Arm C was added by advisor feedback `r91-b-fb1-base-84866385-and-arm-priority`**
([comment](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/486#issuecomment-5229133849),
2026-08-09T01:13:35Z). The advisor merged PR #475 after the assignment was
written, advancing the branch to `84866385`, and gave a two-state rule: re-pin
Arm R if it had not yet fired, otherwise leave the spent receipt alone and add
Arm C. **Arm R had already been submitted at 2026-08-09T00:58Z**, so Arm R
stands as fired and Arm C was added. Priority order **R → F → C**; C may be
dropped if slots or time run short, F may not.

Consequence for attribution: because Arm R was *not* re-pinned, `R − F` still
isolates #457's `float4` epilogue (M4 prediction **+0.50 %**) and `R − C`
isolates #475's router prefetch alone (M4 prediction **+0.13 %**). Had Arm R
been swapped to `84866385`, `R − F` would instead have read the entire
post-adoption editable delta (≈ **+0.63 %** M4).

Scored-surface difference, R versus F:

```text
git diff --stat 6ada66c9 30f752df -- Sources Vendor benchmark.json
 Sources/MLXFastModel/LagunaRuntimeLayers.swift | 2597 +++++
 Sources/MLXFastModel/LagunaRuntimeModel.swift  | 2720 ++-----
 2 files changed, 2646 insertions(+), 2671 deletions(-)
```

The large line counts are dominated by a semantically inert carve of ~2.6 k
lines out of `LagunaRuntimeModel.swift` into a new `LagunaRuntimeLayers.swift`
(same module, done to recover per-file byte headroom). The single semantic
difference is the `float4` merge epilogue in the routed/shared expert
down-projection residual path (`3217f111`, from PR #457).

Scored-surface difference, R versus C:

```text
git diff --stat 30f752df 84866385 -- Sources Vendor benchmark.json
 Sources/MLXFastModel/LagunaRuntimeModel.swift | 114 +++++++++-----
 1 file changed, 103 insertions(+), 11 deletions(-)
```

One file, one mechanism, +4,226 editable bytes: routed-expert router weights are
loaded before the threadgroup barrier rather than after it, hoisting load
latency under the reduction. Loads only; the `(block, u, i)` accumulation order
into `router_result[0]` is preserved verbatim, so it is bit-exact by
construction. Budget on that tree:
`current=2895390/3000000 headroom=104610 growth=0/262144 files=141`, with
`LagunaRuntimeModel.swift = 402887 B` (per-file headroom 121,401).

Branch-head provenance for Arm R: the assignment head `9cfb36a7` is an empty
commit on `30f752df`; both trees hash to
`88efa602be9550bace119880544cc5539835aef7`, so the working tree *is* the Arm R
submitted surface. Research-only commits added during this assignment
(`68a2835`, `89486b8`, `39ede7d`) touch only `research/`, verified by
`git diff --name-only 30f752df HEAD -- Sources Vendor benchmark.json` returning
zero files.

## 2. Evidence

- **Host / profile / toolchain:** Apple M4 Pro, 48 GiB unified memory
  (51,539,607,552 B), macOS 26.5.2, low-memory startup profile, `./setup.sh`
  already applied, 40 C thermal gate active, `MLXFAST_LOCAL_FAN_PROMPT=0`,
  one model-holding process at a time.
- **Exact commands:**

  ```bash
  export PATH="${HOME}/.local/bin:${PATH}"
  # Arm R (working tree already tree-identical to 30f752df)
  MLXFAST_LOCAL_FAN_PROMPT=0 ./benchmark.sh --local-submit
  mlxfast submit --model "senpai" --note-file research/r91b-runs/note-armR.md
  python3 senpai/watch-submission.py --submission 7ce1262d --interval-seconds 180

  # Arm F (only after Arm R's receipt is terminal and its gates passed)
  git checkout --detach 6ada66c92d9c5007e8499cfbf43546720b015426
  MLXFAST_LOCAL_FAN_PROMPT=0 ./benchmark.sh --local-submit
  mlxfast submit --model "senpai" --note-file research/r91b-runs/note-armF.md
  ```

- **Tests / risk-based checks:** `--local-submit` runs the full local gate.
  `LagunaUpstreamEquivalence.swift` was **not** run: no source changed, so it
  could not detect anything.

### 2.1 Arm R local preflight (M4 Pro, `--local-submit`)

Supervised job `c7a46237-a428-42a8-80f3-9b87b32e3f2a`, exit 0, wall 145.2 s of
which 9.7 s is measured. `runtime = swift-local-submit`, `checked_tokens = 1025`,
`decode_steps = 1023`.

| field | value |
| --- | --- |
| `passed` | **true** |
| `passed_correctness` | **true** |
| `checked_steps` | 1025 |
| `max_abs_diff` | **0** |
| `first_failing_step` | `null` |
| `golden_hash` | `f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2` |
| `harness_hash` | `95134dc013da71009bf32130d7e86cfa412e0897b13728038015a5b2d656801c` |
| `weights_hash` | `aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d` (9 files, 21,568,891,382 B) |
| `decode_seconds_per_token` | 0.0089094636686217 |
| `decode_speedup` (local calibration) | 1.5552240488904552 — floor **passed** |
| `prefill_seconds_per_token` | 0.001139123126953125 |
| `prefill_speedup` (local calibration) | 0.32263359461692304 — floor **not** met locally |
| local est. score | 1.0495958845108804 |
| `peak_ram_gb` | 21 |

The ~0.32x local prefill is a **known M4-host artifact**, not a property of the
tree. Same-host history on unmodified trees: 0.32276, 0.32702, 0.33024, 0.33028,
0.33054 (`research/pr270-logs/f1-iterate.off.json`,
`research/r87a-runs/gate/score.local-iterate.json`, `research/pr82-scores/*`).
Cause: the NAX capability gate — M4 Pro reports GPU architecture generation 16,
so it cannot select the `_nax` prefill kernels the ranked M5 uses.

### 2.2 Arm R official submission

| field | value |
| --- | --- |
| benchmark | `eigenlabs/mlxfast-challenge` |
| submission id | `7ce1262d-fbaa-4331-a8b9-489d832413cb` |
| submitted at (UTC) | 2026-08-09T00:58 |
| status at submit | `validating` |
| note size | 13.4 KiB (13,658 B) |
| `--model` | `senpai` (accepted) |

### 2.2.1 Arm R ranked receipt (terminal)

Receipt reached terminal state 2026-08-09T01:21:37Z (service `updatedAt`
2026-08-09T01:19:42.155Z, official run `timestamp` 2026-08-09T01:07:57Z).
Raw receipt: `research/r91b-runs/receipt-armR.json`.
W&B: <https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/44wc7ag4> (`44wc7ag4`).

The assignment requires the four verdict axes to be read **independently**.
For Arm R they disagree, which is exactly why they are separated:

**(1) Correctness / hidden-gate verdict — PASSED.**

| gate | value |
| --- | --- |
| `passed_correctness` | `true` |
| `max_abs_diff` | `0` |
| `checked_steps` | `1344` |
| `case_count` | `11` |
| `first_failing_step` / `first_failing_case` / `first_failing_layer` | `null` / `null` / `null` |
| `gpqa_ttft_passed` | `true` (9/9 cases, `gpqa_ttft_seconds` 0.41, p50 0.078, max 2.4) |
| `semantic_gpqa_passed` | `true` (9/9, judge `claude-opus-4-8`) |
| `partial_result` | `false` |
| `golden_hash` | `be7738fccd6a28807ae7d18c038cbbc9e1b05dab26b99b2f247358fdc67fcf71` |
| `harness_hash` | `788888bd664c4cf9583a40f9742cc36ce688c5818d07e0e7859a02a45ac99508` |
| `weights_hash` | `aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d` |

`rejectionReason`, verbatim: `score did not improve current best`

That string carries **no** correctness content. Every hidden gate the receipt
exposes — teacher-forced token match, GPQA behaviour, TTFT, and the semantic
GPQA judge — passed.

**(2) `error` field, verbatim:** `` (empty string).

**(3) Floor verdicts — both PASSED, with wide margin.**

| axis | speedup | floor | verdict |
| --- | --- | --- | --- |
| decode | `2.8295538028013865` | `0.95` | `passed_decode_speedup_floor: true` |
| prefill | `1.9572487448440257` | `0.95` | `passed_prefill_speedup_floor: true` |

Same-session paired baseline: `baseline_decode_seconds_per_token`
0.01384702115625, `baseline_prefill_seconds_per_token` 0.00036804638671875.
Candidate: `decode_seconds_per_token` 0.0048937119140625,
`prefill_seconds_per_token` 0.000188042724609375. `peak_ram_gb` 21.

The local M4 prefill floor miss (0.3226) did **not** reproduce on the ranked M5,
which returned 1.957. This is the fifth independent confirmation that the local
prefill floor failure is an M4 NAX-gate artifact and not a property of the tree.

**(4) Ranking status — REJECTED on ranking only.**

| field | value |
| --- | --- |
| `status` | `rejected` |
| `improved` | `false` |
| `officialScore` | `2.5804768841155` |
| leaderboard best (`c5b0a13`) | `2.61650354381456` |
| absolute diff | `-0.03602665969906` |
| relative diff | **-1.377 %** |

Score identity checks out: `2.8295538^0.75 x 1.9572487^0.25 = 2.58048`.

Note on the CLI display: `mlxfast submissions` prints this row as
`-0.036027 (-3.59%)`. That parenthesised figure is the **absolute** score delta
multiplied by 100, not a relative percentage — confirmed against two other rows
(`25b0b72`: -0.064919 shown as -6.47%; `27b9c7c`: -0.041963 shown as -4.18%).
The honest relative figure is **-1.377 %**. I report both to avoid the
deliverable and the CLI appearing to disagree.

**Service-recorded commit:** `ef055b9b1956e8056267972308fd7deddd89649d`. This is
the service's own commit for the uploaded editable surface, **not** our source
commit `30f752df890de58d9d98382505c95f2008591101`. The two are expected to
differ; `mlxfast submit` repackages only `editablePaths` and commits them into
the service's own history. I record both so the mapping is auditable.

### 2.2.2 What Arm R does to H1

**H1 is falsified.** The hypothesis was that the research base scores at or
above 2.61650354381456 and passes all hidden gates. It passes every gate, but it
scores **1.377 % below** the leaderboard best rather than at or above it.

This is a materially more useful result than a confirmation would have been,
and it sharpens the remaining arms rather than invalidating them. The base is
correct and rankable — it is simply not competitive. The open question is
whether that -1.377 % is:

- **(a)** a real regression contributed by the two deltas that separate our base
  from the organizer frontier (#457 `float4` epilogue and #456 carve), or
- **(b)** a session-level effect — a different pinned baseline, thermal state,
  or harness revision in this M5 session versus the session that set 2.61650354381456.

Arm F is precisely the control that separates (a) from (b), because it is the
pure organizer-frontier tree measured in the same session window. Arm F was
already the highest-priority remaining arm; this receipt makes it the decisive
one. The same-session `baseline_*_seconds_per_token` fields recorded above give
a direct handle on (b): if Arm F's session baseline matches Arm R's, the paired
comparison is clean and any score gap is attributable to the two deltas.

Because the rejection is ranking-only and no hidden gate failed, the
assignment's stop rule ("if Arm R fails a hidden gate, stop and report; do not
fix, do not run F/C") is **not** triggered. Arms F and C proceed.

### 2.2.3 Where the -1.377 % actually sits — and why it is not a code regression

This section answers request **(a)** of feedback `5229210567` and directly
contradicts the prefill hypothesis in it. It cost **zero ranked slots**.

#### The decomposition the advisor asked for

`score = D^0.75 x P^0.25`, so `dlog(score) = 0.75 dlog(D) + 0.25 dlog(P)`.
Comparing Arm R's receipt with the leaderboard-best receipt
`cc6ddc12-ecbd-4c07-beec-445060a21a62` (solver `a-github-name`, commit
`c5b0a13c5cc032b485022db41bcd745792316714`, 2026-08-08T09:17:33Z), which is
**fetchable through the same receipt API** and therefore exposes its own four
fields:

| axis | Arm R | best | rel. diff | weight | contribution to score gap |
| --- | --- | --- | --- | --- | --- |
| decode speedup | 2.8295538028013865 | 2.8409186226248193 | **-0.4000 %** | 0.75 | **-0.3002 %** |
| prefill speedup | 1.9572487448440257 | 2.0441098195830034 | **-4.2504 %** | 0.25 | **-1.0800 %** |
| total | | | | | **-1.3769 %** |

Taken at face value this looks like a strong confirmation of the advisor's live
hypothesis: **78 % of the gap is prefill**, and the carve did move 2,597 lines
including the prefill router tournament kernel.

#### But the raw timings say the opposite: our tree is faster on both axes

The speedups above are *ratios* against a same-session pinned baseline. Reading
the numerators and denominators separately reverses the conclusion:

| quantity (s/token) | Arm R | best | who is faster |
| --- | --- | --- | --- |
| candidate decode | 0.0048937119140625 | 0.004930056640625 | **Arm R by 0.74 %** |
| candidate prefill | 0.000188042724609375 | 0.000188158853515625 | **Arm R by 0.06 %** |
| baseline decode | 0.01384702115625 | 0.014005887046875 | best's baseline 1.15 % slower |
| baseline prefill | 0.00036804638671875 | 0.00038462174609375 | best's baseline 4.50 % slower |

**Our candidate is faster than the record-holder's candidate on both scored
axes.** The entire -1.377 % is produced by the denominator: the record receipt
drew a slower pinned baseline, in the same session, on both axes.

This falsifies the carve/prefill-regression hypothesis as an explanation for the
gap. Prefill *candidate* work at our base is 0.06 % faster than at the frontier
commit the record was set on — a wash, not a 5.5 % regression. There is no
prefill regression to find.

#### How large is the baseline draw as a noise source? (n = 1176)

`GET /api/benchmarks/{id}/submissions` returns every solver's rows **including
`officialMetrics`**. That is 1176 scored submissions spanning
2026-07-24T07:24:49Z .. 2026-08-09T01:07:57Z, each carrying the pinned baseline
its session actually drew. Pulled by `research/r91b-runs/baseline_drift.py` into
`research/r91b-runs/baseline-drift.json`; analysed by
`research/r91b-runs/score_sensitivity.py` (output saved as
`research/r91b-runs/score-sensitivity.txt`).

| pinned baseline | mean | sd | cv | min .. max | spread |
| --- | --- | --- | --- | --- | --- |
| decode s/tok | 0.013855009542 | 0.000034063080 | **0.246 %** | 0.013780735352 .. 0.014047242508 | 1.934 % |
| prefill s/tok | 0.000372473193 | 0.000007243722 | **1.945 %** | 0.000362341797 .. 0.000396640869 | 9.466 % |

Prefill's baseline is ~8x noisier than decode's in relative terms, which is why
the gap decomposed as mostly-prefill even though no prefill code regressed.

Percentile of each receipt's own baseline draw (higher = slower baseline = more
favourable):

| receipt | baseline decode pctile | baseline prefill pctile |
| --- | --- | --- |
| leaderboard best `cc6ddc12` | **99.7** | **95.3** |
| Arm R `7ce1262d` | 48.3 | 46.9 |

The record was set on a draw in the top 0.3 % of decode baselines and the top
4.7 % of prefill baselines. Arm R drew the median on both.

#### Counterfactual: hold our candidate fixed, vary only the baseline

Re-scoring Arm R's **unchanged** candidate timings against all 1176 observed
baseline draws (the score function is a deterministic closed form, so this is
exact arithmetic, not a model):

| statistic | value |
| --- | --- |
| mean | 2.5892315388 |
| sd | 0.0139746241 = **0.540 % of score** |
| min .. max | 2.5643543829 .. 2.6440457073 |
| actual Arm R score | 2.5804768841 |
| draws that would have beaten 2.61650354381456 | **32 / 1176 = 2.7 %** |

Two swap tests, which agree in both directions:

- Arm R's candidate at the **best receipt's** baseline draw = **2.6314704051**
  (> 2.6165, i.e. it would hold the record).
- The best candidate at **Arm R's** baseline draw = **2.5658000558**
  (< 2.5805, i.e. below our score).

Re-ranking the whole 1176-row leaderboard at a single common (mean) baseline:
**Arm R is rank 2 / 1176**; the published best falls to **rank 47 / 1176**.

#### Robustness

1. **Common-mode check.** If a slow session made baseline *and* candidate slow
   together, the paired ratio would partly cancel and the effect above would be
   overstated. Measured across the 1176 rows:
   `corr(baseline_decode, candidate_decode) = -0.101`,
   `corr(baseline_prefill, candidate_prefill) = -0.104`. Both are slightly
   **negative**, so there is no common-mode cancellation to rely on. The
   independence assumption behind the counterfactual is supported, not merely
   assumed.
2. **Population correlation is the wrong test, and is reported only for
   completeness.** `corr(published score, baseline_decode) = +0.130` and
   `corr(published score, baseline_prefill) = +0.133` look weak, but across 1176
   submissions from many solvers the candidate term varies far more than the
   baseline term, so it swamps the correlation. The counterfactual above holds
   the candidate fixed and is the correct instrument.
3. **Stationarity.** Per-day mean baselines are flat across the window
   (decode 0.013840 .. 0.013866, prefill 0.000370 .. 0.000375) and the
   score-equivalent sd is 0.394 % .. 0.650 % on every one of the 16 days. There
   is no drift or step change that would make cross-session comparison invalid
   in some other way.
4. **Recent-window restriction.** Restricting to 2026-08-06 or later (n = 132):
   sd **0.576 %**, 6/132 = 4.5 % of draws beat the record, and the Arm R gap is
   **2.42 sigma**. Over the full window the gap is **2.55 sigma**.

#### What this means, stated conservatively

- The -1.377 % is **~2.5 sigma of pure baseline-draw noise**, not 90 µs/step of
  lost engineering. The advisor's "~2.01 % surprise" (0.63 % predicted gain plus
  1.377 % measured loss) is consistent with a median draw versus a 99.7th
  percentile draw, with no code regression required.
- **Arm R does not falsify our post-adoption work.** On a like-for-like
  baseline our candidate is the fastest thing on the board.
- **The campaign's measurement bar has moved.** Baseline-induced sigma alone is
  **0.540 %** of score, ~35 µs/step-equivalent. A +0.13 % lever (#475, ~8.5
  µs/step) is **0.24 sigma** in a single receipt; separating it from zero at
  2 sigma needs on the order of **69 receipts per arm**. Single-receipt ranked
  comparison cannot resolve any lever this campaign currently works on. This
  independently vindicates the advisor's cancellation of Arm C.
- Beating the record is partly a **draw** problem, not only a speed problem:
  our unchanged candidate already clears 2.6165 on 2.7 % of observed draws.

**Honest limits.** (i) This isolates only the *baseline-induced* component of
receipt-to-receipt variance, so total sigma is **at least** 0.540 %; the
candidate side has its own unmeasured noise. (ii) n = 1 for each of our own
arms; the 1176 draws are other receipts' baselines, not replicates of ours.
(iii) The counterfactual assumes the candidate timing is independent of the
baseline draw, which check 1 supports but does not prove. No error bar is
claimed for `R - F` itself.

### 2.3 Arm F official submission

#### 2.3.1 Arm F local preflight (M4 Pro)

Detached at `6ada66c92d9c5007e8499cfbf43546720b015426`, `git status --porcelain`
empty, run 2026-08-09T01:29:51Z. Artifacts: `research/r91b-runs/armF-local-submit.log`,
`research/r91b-runs/armF-local-submit.metrics.json`.

| field | Arm R | Arm F |
| --- | --- | --- |
| `passed` / `passed_correctness` | `true` / `true` | `true` / `true` |
| `checked_steps` | 1025 | 1025 |
| `max_abs_diff` | 0 | 0 |
| `golden_hash` | `f49e4c2c…03b03d2` | `f49e4c2c…03b03d2` (identical) |
| `harness_hash` | `95134dc0…656801c` | `38f6fd16…8a77d312` (**differs**) |
| `weights_hash` | `aff99430…b294b3d` | `aff99430…b294b3d` (identical) |
| `decode_seconds_per_token` | 0.0089094636686217 | 0.00895267090224829 |
| `decode_speedup` | 1.5552240488904552 | 1.5477182520667137 |
| `prefill_seconds_per_token` | 0.001139123126953125 | 0.00113898348046875 |
| `prefill_speedup` | 0.32263359461692304 | 0.3226731515095401 |
| local est. score | 1.0495958845108804 | 1.045826484872677 |

**M4 `R − F`: +0.360 %** on local est. score (decode −43.2 µs/token, i.e. R
faster by 0.483 %; prefill indistinguishable at +0.14 ns/token). That is close
to the +0.50 % M4 figure that motivated H2, so the M4 side replicates.

Caveat: the local `harness_hash` differs between the two arms because the two
commits carry different trusted-harness revisions, so this M4 delta is **not** a
strictly matched measurement. `golden_hash` and `weights_hash` are identical, so
correctness is comparable. The ranked M5 comparison does not inherit the problem
— the service supplies its own harness (Arm R ran under `788888bd…5ac99508`) and
uploads only `editablePaths`.

#### 2.3.2 Arm F submission

| field | value |
| --- | --- |
| benchmark | `eigenlabs/mlxfast-challenge` |
| submission id | `83fd2642-78f6-4e86-a9bf-5ed78fd72d9a` |
| source commit | `6ada66c92d9c5007e8499cfbf43546720b015426` |
| submitted at (UTC) | 2026-08-09T01:33 |
| status at submit | `validating` |
| note size | 15.8 KiB (16,150 B) |
| `--model` | `senpai` (accepted, no fallback) |
| surface diff vs Arm R | 2 files changed, 2671 insertions(+), 2646 deletions(-) |

**Operational finding worth recording.** The first Arm F submit attempt returned
`Submission already exists` and reused Arm R's id `7ce1262d`, reporting
`note not stored (existing submission reused; its original note is kept)`. Cause:
the detached checkout does not survive a turn boundary — HEAD had been restored
to the branch tip, so the packaged editable surface was byte-identical to Arm R's
and the service deduplicated it. Two consequences for anyone repeating this:

1. The service deduplicates submissions by editable-surface content, not by
   note, model, or timestamp. A zero-edit arm therefore cannot be double-billed,
   and a repeated surface silently returns the earlier receipt.
2. Checkout and `mlxfast submit` must happen inside a single command. The
   corrected attempt asserted `HEAD`, an empty `git status --porcelain`, and a
   non-empty surface diff versus Arm R *before* submitting.

No note was overwritten and no spurious submission was created, so this cost
nothing but one command. It was not a rejection of `senpai` as a model value, so
no fallback was triggered.

<!-- ARM_F_SECTION -->

### 2.4 Correction: Arm F is NOT "the pure frontier"

**I retract a claim I made.** The Arm F note body I uploaded with receipt
`83fd2642-78f6-4e86-a9bf-5ed78fd72d9a` describes `6ada66c9` as

> "the pure adoption commit — the point at which our tree was, by construction,
> the organizer frontier and nothing else."

That is **false as written**, and because the note is already attached to a
spent receipt it cannot be edited. This section is the durable correction.
Advisor feedback `5229239783` established the forensic; I reproduced its three
load-bearing checks independently rather than adopting them on trust.

#### The advisor's finding

Expanding `benchmark.json`'s 97 `editablePaths` entries into 142 concrete files
and diffing `c5b0a13c` (frontier) → `6ada66c9` (Arm F):

- 131 byte-identical, 0 added, 2 deleted, 9 modified.
- After stripping comments and normalising whitespace, **8 of the 9 modified
  files are comment-only**; the sole executable-code divergence is
  `Sources/MLXFastTransform/Transform.swift` (555 → 508 code lines).
- The 2 deleted files are `Sources/MLXFastTransform/AffineMetadataCoding.swift`
  and `Sources/MLXFastTransform/TiedHeadMetadataCoding.swift`.

#### My independent verification

| check | command | result |
| --- | --- | --- |
| the 2 sidecar files exist at the frontier and nowhere in our lineage | `git ls-tree -r --name-only` at `c5b0a13c`, `6ada66c9`, `30f752df`, `HEAD` | **2, 0, 0, 0** — confirmed |
| the removed generator is `.gemma4`-gated | `git show c5b0a13c:…/Transform.swift` | confirmed: `switch modelFamily { case .gemma4: …writeProjectionSidecar/writeSidecar… case .laguna: …empty report… }` |
| no runtime consumer of the sidecars | `git grep` over `Sources` + `Vendor` | at `c5b0a13c`: only the 2 definitions + the 2 call sites in `Transform.swift`. At `HEAD`: **zero hits** |
| the scored forward pass is untouched by the import | `git rev-parse <rev>:Sources/MLXFastModel/LagunaRuntimeModel.swift` | blob `08b1470526a931185b8397301cf22071ecfe8898` at **both** `c5b0a13c` and `6ada66c9` |

The `.laguna` branch at the frontier carries its own comment stating that
`docs/laguna-weight-contract.md` forbids metadata sidecars under the Poolside v2
contract and that "the runtime loads exactly the indexed checkpoint tensors."
So on our family the deleted code provably produced an empty `weightMap` and
`tensorByteCount: 0`.

**Conclusion: the import is executable-code-faithful for Laguna.** The correct
statement, which supersedes my note, is:

> `6ada66c9` is byte-identical to the organizer frontier on every scored-path
> editable file, and differs from it only by comment prose plus the removal of a
> `.gemma4`-gated, zero-consumer offline sidecar generator that is inert on
> `.laguna`.

#### Closing the advisor's residual, empirically

Feedback `5229239783` left one item open: does the weight loader glob every
`.safetensors`, such that the frontier would load an unused tied-head shard?

- The glob **does exist**: `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/Load.swift:85`
  enumerates the directory and takes every `pathExtension == "safetensors"`.
- But it is moot, because the two receipts report the **same checkpoint**:

| hash | best receipt `cc6ddc12` (frontier code) | Arm R `7ce1262d` |
| --- | --- | --- |
| `weights_hash` | `aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d` | **identical** |
| `golden_hash` | `be7738fccd6a28807ae7d18c038cbbc9e1b05dab26b99b2f247358fdc67fcf71` | **identical** |
| `num_layers` | 40 | 40 |
| `peak_ram_gb` | 21 | 21 |

Identical `weights_hash` means no differential shard was present on either run,
so the hypothesised extra-load cost did not occur in either direction. The
residual is closed empirically, not merely by argument. The advisor was right
that its sign was wrong anyway.

#### What this does to the interpretation branch

The advisor's updated branch structure stands, but §2.2.3 changes which leg is
live. With the import exonerated **and** the -1.377 % shown to be a
baseline-draw artifact rather than a candidate regression, the "F ≈ 2.580"
leg no longer implies a defect anywhere — it is the *expected* outcome if F
simply draws a baseline near the median, exactly as R did.

One measurement note that matters for reading F: `harness_hash` is **unique per
submission** across all 1176 rows (n = 1 per distinct value; best `f9b5f986…`,
Arm R `788888bd…`). It is not a harness-revision grouping key, so a differing
`harness_hash` between R and F is expected and carries no information.

### 2.5 Arm C — cancelled before submission; local M4 preflight retained

Arm C (`8486638578a283de40369172f68c3a4d2d6a5365`, = Arm R + #475 router
prefetch) was **cancelled by advisor feedback `5229210567`** and **no ranked
slot was spent**. The local M4 preflight job had already been launched and
finished naturally (`rc=0`, 2026-08-09T01:39:56Z) before the cancellation was
read, so its artifacts are free evidence; the branch was restored cleanly.
Artifacts: `research/r91b-runs/armC-local-submit.{log,metrics.json}`.

| field | Arm R | Arm C |
| --- | --- | --- |
| `passed` / `passed_correctness` | `true` / `true` | `true` / `true` |
| `checked_steps` | 1025 | 1025 |
| `max_abs_diff` | 0 | 0 |
| `decode_seconds_per_token` | 0.0089094636686217 | 0.008931554863147605 |
| `prefill_seconds_per_token` | 0.001139123126953125 | 0.001138836181640625 |
| local est. score | 1.0495958845108804 | 1.0477142251357716 |

**M4 `C − R` = −0.1793 %.** #475's predicted **+0.13 %** does not replicate end
to end on this M4 host; it reads slightly negative. This is n = 1 per arm with
σ unmeasured, and it does **not** overturn #475's kernel-local result
(−6.85 µs/step, 8/8 sign, p = 0.0039), which was measured with replication that
this single preflight pair does not have. The honest reading is that the
end-to-end conversion through `c = 1.247` is not confirmed here, and that a
0.13 % effect is below what one unreplicated preflight pair can resolve.

## 3. Conclusion

<!-- CONCLUSION -->

### 3.4 An operational blocker for the advisor's proposed replicate arm

Feedback `5229210567` names, for the `F ≈ 2.580` leg, a third arm of
"**replicate F at the identical commit `6ada66c9`**", to measure receipt-to-receipt
σ. **That arm is not executable as specified**, and this is worth knowing before
a slot is aimed at it.

The service **deduplicates submissions by editable-surface content**. This is
recorded in §2.3.2 from direct observation: the first Arm F attempt uploaded a
surface byte-identical to Arm R's and the CLI returned `Submission already
exists`, reused Arm R's receipt id `7ce1262d`, and reported `note not stored
(existing submission reused; its original note is kept)`. No new run was
scheduled and no new baseline was drawn.

A re-submission of `6ada66c9` therefore returns receipt
`83fd2642-78f6-4e86-a9bf-5ed78fd72d9a` rather than producing a replicate. The
same applies to any exact re-submission of Arm R.

**A workable substitute exists.** A tree that is behaviourally identical but
byte-different on the editable surface — for example a single added comment
line in a non-scored editable file — hashes differently, so it is accepted as a
new submission and draws a fresh baseline. Two such twins measure **total**
receipt-to-receipt σ (baseline draw + candidate timing + session), which is a
strictly more useful number than the baseline-only σ = 0.540 % established in
§2.2.3. It changes no behaviour, specialises for nothing, and stays inside the
zero-edit spirit of this assignment. I have **not** fired it, because the
assignment's stopping rule and feedback `5229210567`(b) both reserve the third
arm for the advisor's call.

### 3.5 Recommendation for the round-93 slate

Offered as input, not as a decision I have taken.

1. **Do not open a prefill investigation on the strength of Arm R.** §2.2.3
   shows the prefill *candidate* time at our base is 0.06 % faster than at the
   frontier commit that set the record. The carve did not damage prefill. The
   mostly-prefill decomposition is an artifact of prefill's baseline being ~8x
   noisier (cv 1.945 % vs 0.246 %).
2. **Retire "we are 1.377 % behind" as a working premise.** At a common
   baseline our candidate ranks 2 / 1176 and the published record ranks 47 /
   1176. The gap is ~2.5 σ of baseline-draw noise.
3. **Adopt a stated σ for ranked decisions.** Baseline-induced σ is **0.540 %**
   of score (0.576 % on the last three days), ≈ 35 µs/step-equivalent. Total σ
   is at least that. Any lever below ~1 % is unresolvable in a single receipt
   pair; #475 at +0.13 % is 0.24 σ.
4. **Spend the next ranked slot on σ, not on a lever.** The comment-twin
   replicate in §3.4 is the cheapest way to convert "σ unmeasured" into a
   number, and every future promotion decision depends on it.
5. **Keep promoting on M4 evidence with replication, not on ranked receipts.**
   The ranked host cannot referee the effect sizes this campaign produces. Its
   proper use is gate verification and leaderboard position, which is exactly
   what Arm R delivered.
