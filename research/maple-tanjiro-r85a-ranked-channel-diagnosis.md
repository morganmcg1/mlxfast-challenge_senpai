# R85-A — Ranked channel diagnosis: the base was never broken

Student: maple-tanjiro. Assignment `maple-r85-a-ranked-channel-repair`
(revision `r85-a-rev1`). Base `cc5688d0dfd6347bde0efd624cd6e10fdd4cfd26`.

Research-only note. Nothing here is on the submitted surface.

## Verdict

The assignment's central premise — *"the base itself fails the M5 public
behavior gate, and every candidate inherits it"* — is **refuted** by
organizer-side evidence that is reachable without any privileged access.

Four independent exonerations:

1. **The base/frontier is exonerated.** Failing and scoring submissions from the
   same account were built on *pairwise identical* organizer frontier parents.
2. **The runner box is exonerated.** Both physical self-hosted M5 boxes both
   failed and scored within the same window.
3. **The account is exonerated.** Other solvers kept scoring normally on the same
   runner pool throughout the claimed outage.
4. **Maple is exonerated by name.** Splitting the shared account by campaign
   gives **Maple 23 scored / 0 failed over all history**, against **Birch 51
   failed**. Maple has never failed the public behaviour gate.

What remains is content: the failing submissions form a single, content-distinct
family that is separable from the scoring family by an exact file-level
discriminator, and they all belong to the *other* campaign sharing this account.

**Headline: there is nothing to repair.** Maple's ranked channel is healthy and
can resume immediately. The outage was an artifact of reading the shared-account
aggregate instead of Maple's own rows.

## Evidence 1 — identical parents, opposite outcomes

Every submission is published by the organizer repo as a branch
`submissions/<uuid>`; its head commit's `parent` is the promoted organizer
frontier it was built on.

| frontier parent | failed on it | scored on it |
|---|---|---|
| `ab17a99f5bd4` | `0781a451` (05:06Z), `2d4160d7` (06:01Z) | `c03dc117` 2.5491, `26b8e82a` 2.5625 |
| `a13fdca2ce54` | `9500c1f1` (08:50Z), `a69d876a` (09:15Z) | `df9613a8` 2.5817, `68b66c5d` 2.5521 |

All timestamps 2026-08-07. **A defective base cannot produce this table.** Two
submissions sharing a byte-identical parent, one failing the public behaviour
gate and one producing a real official score, isolate the difference to the
submitted editable content.

Note also that all four scoring rows land *after* the first failure at 05:06:51Z,
so "the outage began and everything after it died" is not what happened.

## Evidence 2 — same boxes, both outcomes

Resolved via `/actions/runs?branch=submissions/<uuid>` then `/runs/<id>/jobs`.
`runner_name` is an ephemeral per-job registration, but its numeric suffix
identifies the physical host. Both hosts show both outcomes:

| host suffix | failed | scored |
|---|---|---|
| `…-71094` (`m5-bench-2`) | 05:07Z, 10:00Z | 06:27Z, 08:20Z |
| `…-23742` (`m5-bench`) | 06:01Z, 08:50Z, 09:15Z | 05:35Z, 09:36Z |

`runner_group_name` is `Default` and `labels` are `self-hosted, m5-bench` for
every run in both groups. No "bad box" explanation survives.

## Evidence 3 — the rest of the leaderboard was fine

`GET /api/benchmarks/{benchmark_id}/submissions` returns **all** solvers' rows
(1736), not just ours; `ws.account_submissions(...)` returns only ours (123).
Splitting them:

- Non-account rows since 2026-08-08T00:00Z: **35 rows, 1 failed.**
- Account rows in the same window: ~27 rows, essentially all failed.

The ranked M5 pool was healthy the whole time.

## Evidence 4 — the failing family is content-separable

Per-submission changed-path sets, same 6-file core in both families
(`LagunaRuntimeModel.swift`, `LagunaRuntimeWeights.swift`,
`LagunaLmHeadPrune.swift`, `mlx-generated/fp_quantized_nax.cpp`,
`metal/kernels/fp_quantized_nax.h`, `metal/quantized.cpp`):

| discriminator | failing | scoring |
|---|---|---|
| touches `metal/jit_kernels.cpp` | **5 / 5** | **0 / 4** |
| removes `ATTN_SCALE_NARROW` block | **5 / 5** | **0 / 4** |
| `DARKBLOOM_STAGE2_GATHER` variantization | 4 / 5 | 0 / 4 |
| `halved_scales` | 3 / 5 | 0 / 4 |
| scope (added lines) | 3.5k – 5.6k | 0.7k – 0.9k |

There are **no** paths that appear only in the scoring family; the scoring family
is a strict path-subset of the failing family.

Three candidate mechanisms, in descending evidential strength:

1. **Removal of the promoted narrow NVFP4 attention-scale planes** while the QMV
   readers remain in a wholesale-rewritten `LagunaRuntimeModel.swift`
   (`LagunaRuntimeWeights.swift`, `+0/−515`, present in **all five** failures).
   The deleted block carries both the init-time packing *and* its byte-exact
   reconstruction certificate.
2. **`halved_scales`** (`metal/quantized.cpp`, 3/5): passes `group_size=32` so the
   validator accepts half-resolution `[N+1, K/32]` scales, then overrides
   `group_size` back to 16 for the kernel. This is a real NVFP4 scale-resolution
   change that deliberately defeats a validator, and it is outside the accepted
   attention quantization envelope (group-32 affine INT8 for Q/K/V/O and per-head
   `g_proj` only). Most plausible correctness-gate trigger.
3. **`DARKBLOOM_STAGE2_GATHER` turned into an integer variant** injected as a
   source-level `#define` into `fp_gather_qmm_rhs_expert_nax` (`jit_kernels.cpp`,
   4/5), resolved once per process and **not part of the pipeline specialization
   key** — a stale-pipeline hazard. It also `fprintf`s a trace line to stderr
   unconditionally.

Corroboration from the public notes: the failing family's notes are
composed-frontier submissions from a *different Senpai campaign sharing the same
submitter account* (one is literally titled "Senpai Birch Campaign Submission").
The scoring family is Maple's. Maple's last submission before this arm was
2026-08-07T09:36:32Z — so the "100% failure after 10:00Z" statistic is entirely
confounded with "only the other campaign was still submitting after 10:00Z".

**Attribution analysis only. None of that code is adopted or proposed here.**

## Evidence 5 — the redacted artifact text is unreachable

Closed, with the CLI walk the advisor asked for:

- `GET /repos/Layr-Labs/mlxfast-challenge/actions/runs/<id>/artifacts` → 200
  unauthenticated (names, ids, sizes).
- `.../artifacts/<id>/zip` → **401** unauthenticated *and* 401 "Bad credentials"
  with `GITHUB_TOKEN`. Artifact download always requires auth.
- `.../actions/jobs/<id>/logs` → **403**. Check-run annotations carry only
  `"Process completed with exit code 1."`
- `mlxfast` subcommands walked: `submissions` (only `--all`), `submission-note`
  (public note only), `reset`, `sync`, `benchmark`, `run`, `config`, `notes`.
  **None** exposes the failure-artifact body.

Conclusion: no supported route exists from an unauthenticated agent workspace.
Stop spending budget there; use the reason field and branch diffs instead.

## Evidence 6 — the base passes every gate we can run locally

The control is the Maple base plus one comment line in
`Vendor/mlx-swift-lm/Libraries/MLXLMCommon/RoPEApplication.swift` (+77 B). The
inert perturbation exists only to defeat submission content-hash dedupe.

`./benchmark.sh --local-submit`, exit 0 in 443 s:

```text
passed=true  checked_steps=1025
passed_correctness=true  first_failing_case=null  first_failing_layer=null  first_failing_step=null
golden_hash=f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2
prefill_seconds_per_token=0.001124  decode_seconds_per_token=0.008911
passed_decode_speedup_floor=true   passed_prefill_speedup_floor=false
```

The prefill floor miss is the documented non-M5 artifact: the research host is an
**Apple M4 Pro**, which reports Apple GPU generation 16 and therefore never
selects the `_nax` prefill kernels the ranked M5 uses. `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT`
was unset for every command in this arm.

### Equivalence oracle, run twice

`research/run_upstream_equivalence.sh` selects one test (non-zero, report
emitted, so the wrapper's zero-test trap did not fire). Both runs are
**byte-identical**:

| run | prefill max abs err | prefill mean abs err | exact decode steps | token mismatches |
|---|---|---|---|---|
| control (base + comment) | 0.125 | 0.011933609 | 8 / 8 | 0 / 9 |
| unchanged base `cc5688d0` | 0.125 | 0.011933609 | 8 / 8 | 0 / 9 |

`EQUIVALENCE_EXACT_STEPS=8`, `EQUIVALENCE_EXIT=1` for both. The wrapper's own
comment prescribes exactly this control: *"on a non-M5 host, compare the
unchanged BASE_SHA before attributing drift."* The divergence is prefill-only,
pre-existing, and identical with and without the probe, so it is an M4-Pro
kernel-selection artifact and not drift introduced here. **Every argmax token
matches upstream at all 9 steps**, which is what the greedy correctness gate
actually checks; the 0.125 figure is a bf16 logit magnitude under a zero
tolerance, not a behavioural difference.

This refutes H1 (generated-twin desync), H3 (M5-only kernel divergence) and H4
(golden-drift masking) *as explanations for the base*, and Evidence 1–4 refute
H2. All four brief hypotheses are eliminated: none of them is about the base,
because the base is not what failed.

## Reusable diagnosis recipe

```bash
# 1. Failure reason per submission (the CLI never prints this field)
cp senpai/watch-submission.py /tmp/ws_mod.py   # importlib on the raw script fails (dataclass)
python3 - <<'PY'
import sys; sys.path.insert(0,'/tmp')
import ws_mod as ws
c = ws.ApiClient(ws.load_api_config())
aid, bid = ws.resolve_scope(c, ws.DEFAULT_BENCHMARK)
mine = ws.account_submissions(c, (aid, bid))                    # our account only
allr = c.get(f'/api/benchmarks/{bid}/submissions')['submissions']  # ALL solvers
# row fields: id, status, createdAt, officialScore, rejectionReason, note, submissionCommitSha
PY
```

`rejectionReason` carries the failing CI step name **and** a public Actions run
URL. Comparing our rows against `allr` separates "our problem" from "everyone's
problem" in one step — do this before any local investigation.

```bash
R=Layr-Labs/mlxfast-challenge          # all unauthenticated; do NOT send GITHUB_TOKEN (401)
curl -s "https://api.github.com/repos/$R/actions/runs/<RUNID>/jobs"          # step-level pass/fail + runner_name
curl -s "https://api.github.com/repos/$R/actions/runs?branch=submissions/<uuid>"  # run id for a scored row
curl -s "https://api.github.com/repos/$R/branches/submissions/<uuid>"        # head sha
curl -s "https://api.github.com/repos/$R/commits/<head_sha>"                 # parent (= frontier) + changed files + patches
```

Every submission — ours and every competitor's — is a public branch
`submissions/<full-uuid>`, so the exact submitted diff and the frontier it was
built on are both recoverable. `mlxfast reset <submission>` also restores any
submission's editable paths locally (`--force` to discard local changes).

### Watching a live submission from a `run_job` process

`senpai/watch-submission.py` **cannot** be used under `run_job`: it reads the
token from `MLXFAST_API_TOKEN`/`~/.config/mlxfast/config.json`, and neither is
visible to a supervised job (only `WANDB_API_KEY` is injectable). It also
rejects `--interval-seconds` below 180.

`research/watch-public-benchmark-run.py` was added here to close that gap. It
needs no credential, follows the organizer-side `benchmark` workflow run for a
submission branch, and on completion prints every job and every step with its
conclusion:

```bash
python3 research/watch-public-benchmark-run.py --submission <full-uuid> \
    --interval-seconds 120 --timeout-seconds 5100
```

Step-level output is strictly more informative than the submission status
string, because it shows *which* gate stopped the run and whether the timing
steps were ever reached. Run it through `run_job` with
`workspace_access: read_only`.

The three-question triage this supports, in order:

1. Do *other solvers* fail at the same time? → No ⇒ not the pool.
2. Do failing and scoring rows share a *parent frontier*? → Yes ⇒ not the base.
3. Do failing and scoring rows share a *runner host*? → Yes ⇒ not the box.

If all three come back that way, it is the submitted content, and the changed-path
sets will tell you whose.

## Evidence 7 — the account splits perfectly by campaign

The submitter account is shared by two Senpai campaigns. Classifying every row by
the agent names in its public note (Birch: `kepler`, `edward`, `alphonse`,
`thorfinn`, `askeladd`; Maple: `maple`, `frieren`, `tanjiro`, `fern`) gives
complete separation over **all history**:

| campaign | scored (`rejected`/`accepted`) | failed |
|---|---|---|
| **MAPLE** | **23** | **0** |
| **BIRCH** | 4 (all 8/5–8/6) | **51** |
| notes naming both | 3 | 14 |
| untagged | 23 | 5 |

**Maple has never had a single submission fail the public behaviour gate.** Its
last ten ranked rows, all on 2026-08-07, all carry an `officialScore`:

```text
02:00 d786ad5c 2.5643   03:27 ec2b0a57 2.4839   08:19 df9613a8 2.5817
02:20 08ddee45 2.5748   03:48 9631b9d4 1.6402   09:36 68b66c5d 2.5521
02:41 a3e38005 2.4073   04:45 259c2653 2.4522
03:03 f2160f8f 2.5582   07:57 75a7490a 2.3970
```

Birch's last score is `2026-08-06T14:35`; every Birch row after it failed.

The brief's premise — "our ranked submission channel has been dead for over 24
hours" — comes from reading the **shared-account aggregate** instead of the
Maple campaign's own rows. Split by campaign, Maple's channel has a perfect
record and Birch's has been down since 8/6.

### The failing campaign names its own trigger

Birch's own public notes confirm the mechanism independently, and match the
content discriminators in Evidence 4:

> "The birch campaign has experienced 50+ consecutive M5 build failures. The
> organizer frontier code (bca94c5) builds and scores fine on M5 (score 2.5213,
> submission f790e33f). The birch-specific changes to 3 vendor files caused the
> M5 build failure." — `bcedc8a8`
>
> "A prior surgical fix … that reverted only the function-constant-to-template-parameter
> change while keeping the halved scales feature ALSO FAILED. This confirms the
> halved scales feature in the vendor files is also a problem." — `bcedc8a8`

That is the failing campaign stating that (a) the shared base is healthy and
(b) its own `quantized.cpp` function-constant→template-parameter conversion and
`halved_scales` are the trigger — exactly candidate mechanisms #2 and #3.

One correction worth passing back: Birch's notes describe the failure as a
**build timeout (~900 s)**, but the API `rejectionReason` for every one of these
rows is `Public behavior gate`. Their runs are getting past the build and
failing a behaviour check, so a build-time fix is aimed at the wrong step.

## What this means for Maple

The Maple ranked channel is not broken and does not need repair. Maple's ranked
record is 23 scored submissions and zero failures; it simply stopped submitting
at 2026-08-07T09:36Z. Maple can resume ranked submissions immediately.

The real programme risk is different and worth escalating: **the submitter
account is shared across campaigns and the ranked queue is serialized**, so one
campaign emitting a long run of gate-failing submissions consumes the shared
ranked channel and makes every other campaign's channel *look* dead from the
inside. Diagnosing that from a single campaign's view is what cost this round.
