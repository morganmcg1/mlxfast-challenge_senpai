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

<!-- ARM_R_RECEIPT -->

### 2.3 Arm F official submission

<!-- ARM_F_SECTION -->

## 3. Conclusion

<!-- CONCLUSION -->
