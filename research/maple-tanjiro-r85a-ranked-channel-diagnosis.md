# R85-A — Ranked channel diagnosis: the base was never broken

Student: maple-tanjiro. Assignment `maple-r85-a-ranked-channel-repair`
(revision `r85-a-rev1`). Base `cc5688d0dfd6347bde0efd624cd6e10fdd4cfd26`.

Research-only note. Nothing here is on the submitted surface.

## Verdict

The assignment's central premise — *"the base itself fails the M5 public
behavior gate, and every candidate inherits it"* — is **refuted** by
organizer-side evidence that is reachable without any privileged access.

Three independent exonerations:

1. **The base/frontier is exonerated.** Failing and scoring submissions from the
   same account were built on *pairwise identical* organizer frontier parents.
2. **The runner box is exonerated.** Both physical self-hosted M5 boxes both
   failed and scored within the same window.
3. **The account is exonerated.** Other solvers kept scoring normally on the same
   runner pool throughout the claimed outage.

What remains is content: the failing submissions form a single, content-distinct
family that is separable from the scoring family by an exact file-level
discriminator.

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

The three-question triage this supports, in order:

1. Do *other solvers* fail at the same time? → No ⇒ not the pool.
2. Do failing and scoring rows share a *parent frontier*? → Yes ⇒ not the base.
3. Do failing and scoring rows share a *runner host*? → Yes ⇒ not the box.

If all three come back that way, it is the submitted content, and the changed-path
sets will tell you whose.

## What this means for Maple

The Maple ranked channel is not broken and does not need repair. Maple's four
most recent ranked submissions all scored (2.5491, 2.5625, 2.5817, 2.5521); it
simply stopped submitting at 2026-08-07T09:36Z. Maple can resume ranked
submissions immediately.

The real programme risk is different and worth escalating: **the submitter
account is shared across campaigns and the ranked queue is serialized**, so one
campaign emitting a long run of gate-failing submissions consumes the shared
ranked channel and makes every other campaign's channel *look* dead from the
inside. Diagnosing that from a single campaign's view is what cost this round.
