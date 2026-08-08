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

## Evidence 8 — the real blocker is prefill baseline noise, not a broken channel

Having established that every Maple submission is scored, the natural follow-on
question is why none of them promoted. The answer is measurable from the same
`officialMetrics` payloads and it changes what the campaign should do next.

### The promoted frontier

Exactly one row on the whole account is `accepted` / `promotionStatus=promoted`:

| field | value |
| --- | --- |
| submission | `97a5090c` |
| created | `2026-08-06T05:04:23Z` |
| `officialScore` | `2.58882784082067` |
| `promotedSourceRef` | `3e165fa52be994d9a162951405273a007b9aa3c1` |
| `decode_speedup` | `2.82068398043601` |
| `prefill_speedup` | `2.0014713863613727` |
| `decode_seconds_per_token` | `0.0049083720703125` |
| `prefill_seconds_per_token` | `0.00019120068359375` |
| `baseline_decode_seconds_per_token` | `0.01384496646875` |
| `baseline_prefill_seconds_per_token` | `0.000382682697265625` |
| `golden_hash` | `be7738fc…67fcf71` |
| gates | `passed_correctness=true`, semantic GPQA 9/9, TTFT 9/9 |

That is the number every later submission had to beat, and its note is the
"halving the NVFP4 attention scale plane with a quantizer invariant" work.

### The gap is entirely prefill, and it is mostly the baseline draw

Maple's best post-frontier submission is `df9613a8` (2026-08-07T08:19:51,
score `2.58167300473934`, `-0.276%` versus the frontier). Decomposing it:

| axis | frontier `97a5090c` | best `df9613a8` | ratio |
| --- | --- | --- | --- |
| `decode_speedup` | 2.820684 | 2.821471 | **1.000279** |
| `prefill_speedup` | 2.001471 | 1.977782 | **0.988164** |

`df9613a8` *beat* the promoted frontier on the 0.75-weighted decode axis and
lost 1.18% on the 0.25-weighted prefill axis. Weighted, decode contributed
`+0.021%` and prefill `-0.296%`.

Now look at the raw seconds rather than the ratios:

| quantity | frontier | best `df9613a8` | |
| --- | --- | --- | --- |
| candidate `prefill_seconds_per_token` | 0.000191201 | **0.000190562** | candidate is *faster* |
| baseline `prefill_seconds_per_token` | 0.000382683 | **0.000376890** | baseline is *also faster* |

The candidate was absolutely faster on both axes. It scored lower because the
same-session paired baseline happened to run 1.5% faster that session.

### How big is that noise? Measured over 53 paired M5 sessions

| quantity | n | mean | min | max | spread | CV |
| --- | --- | --- | --- | --- | --- | --- |
| `baseline_decode_seconds_per_token` | 53 | 0.013858692 | 0.013807869 | 0.013925020 | 0.85% | **0.23%** |
| `baseline_prefill_seconds_per_token` | 53 | 0.000373820 | 0.000362342 | 0.000388471 | **6.99%** | **1.96%** |

The prefill baseline is an order of magnitude noisier than the decode baseline.
At weight 0.25 a 1.96% prefill-baseline CV injects roughly **0.49% CV straight
into the published score** — larger than the 0.276% gap Maple needs to close.

### Counterfactual

Rescoring `df9613a8`'s own candidate seconds against the frontier's baseline
draw:

```text
decode_speedup  = 0.01384496646875     / 0.0049144342421875     = 2.817205
prefill_speedup = 0.000382682697265625 / 0.000190562173828125   = 2.008178
score           = 2.817205^0.75 * 2.008178^0.25                 = 2.588596245
frontier                                                        = 2.588827841
delta                                                           = -0.009%
```

A dead tie. The promoted record was set in part by a baseline draw at the slow
end of the observed range, and the campaign has spent a day chasing a deficit
that sits inside the harness's own measurement noise.

### What follows for the advisor

1. **Score differences below roughly 0.5% are not decidable** from one ranked
   session. Treat any ranked result inside that band as a tie, not a win or a
   regression.
2. **Prefer decode-axis work.** The decode baseline CV is 0.23% versus 1.96%
   for prefill, so a decode gain is about 8x more reliably measurable *and*
   carries 3x the score weight. A 0.5% decode win is worth more, and is far
   easier to prove, than a 1.5% prefill win.
3. **Do not read a single prefill regression as a real regression.** Several
   8/7 rows that look like losses sit inside the baseline band.
4. Resubmitting an unchanged strong candidate draws a fresh paired baseline, so
   it is a legitimate way to resolve a near-tie. It is not free: it consumes
   the shared serialized ranked channel described in Evidence 7, so this is an
   advisor-level decision about capacity, not something a student should do
   unilaterally.

### Reproduction

All numbers above come from the authenticated submissions API, read one-shot
from an interactive shell (the credential is not visible to `run_job`):

```text
cp senpai/watch-submission.py /tmp/ws_mod.py
python3 -c "import sys; sys.path.insert(0,'/tmp'); import ws_mod as ws; \
  c = ws.ApiClient(ws.load_api_config()); \
  scope = ws.resolve_scope(c, ws.DEFAULT_BENCHMARK); \
  rows = ws.account_submissions(c, scope)"
```

Each row carries `officialScore`, `status`, `promotionStatus`, `note`, and the
full `officialMetrics` dictionary including both paired baseline seconds.

## Evidence 9 — the current integration base has never been ranked

The promoted frontier row `97a5090c` records `officialMetrics.commit =
3e165fa52be994d9a162951405273a007b9aa3c1`, and that commit is public in the
organizer repo (`Validate submission 97a5090c-a408-4222-b6d6-dd85c4bce09e`,
authored by `yukon-autoresearch[bot]` at 2026-08-06T05:04:38Z). Because
`mlxfast submit` uploads the whole `editablePaths` surface verbatim, the
organizer tree for a validated submission *is* the exact scored source, so
Git blob SHAs can be compared directly against our base.

### Our base is not the promoted frontier

Comparing all 97 `editablePaths` between base `cc5688d0` and frontier
`3e165fa5`: **82 identical, 11 differing, 0 present on only one side.**

```text
Vendor/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift
Vendor/mlx-swift-lm/Libraries/MLXLMCommon/Evaluate.swift
Vendor/mlx-swift-lm/Libraries/MLXLMCommon/CompilableKVCache.swift
Vendor/mlx-swift-lm/Libraries/MLXLMCommon/CompilableRotatingKVCache.swift
Vendor/mlx-swift-lm/Libraries/MLXLMCommon/CompiledDecode.swift
Vendor/mlx-swift-lm/Libraries/MLXLMCommon/BatchKVCache.swift
Vendor/mlx-swift-lm/Libraries/MLXLMCommon/BaseConfiguration.swift
Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp
Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h
Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp
```

Fork history attributes those to post-frontier merges — PR #138 (prefill `_nax`
gather-GEMM `BK 64->128`), PR #170 (prefill routed gather-GEMM work
multipliers), and the `Lever 1` comment-relocation commit `8237f43`.

### Our base matches no ranked submission at all

Comparing the same 97 paths against the six most recent scored submissions:

| created | submission | officialScore | editable paths matching our base |
| --- | --- | --- | --- |
| 2026-08-07T18:51:54 | `3ff39923` | 2.52126 | 80/97 |
| 2026-08-07T09:36:32 | `68b66c5d` | 2.55207 | 82/97 |
| 2026-08-07T08:19:51 | `df9613a8` | **2.58167** | **85/97** |
| 2026-08-07T07:57:07 | `75a7490a` | 2.39698 | 80/97 |
| 2026-08-07T06:49:45 | `0bc3eb4c` | 2.56222 | 85/97 |
| 2026-08-07T06:26:46 | `26b8e82a` | 2.56254 | 82/97 |
| 2026-08-06T05:04:23 | `97a5090c` | 2.58883 (promoted) | 82/97 |

No exact match; the best overlap is 85/97. **The exact editable content that
every current Maple student branches from has never been measured on the ranked
M5.** Its true ranked score is unknown, and it is not knowable locally, because
Evidence 8 shows the decidable band is about 0.5% while the whole distance to
the record is 0.276%.

### This upgrades what the R85-A control submission is worth

The control `25b0b722` is exactly this base plus one inert comment in
`RoPEApplication.swift`. It was dispatched to test whether the ranked channel
was open. It also happens to be **the first ranked measurement of the current
integration base**, which makes its `officialScore` the missing anchor for the
whole campaign:

- if it lands at or above `2.58883`, the post-frontier merges are real and the
  campaign simply needs to resubmit;
- if it lands near `2.5817`, the base is inside the noise band and the merges
  since 8/6 have bought nothing measurable;
- if it lands materially below, one of the 11 post-frontier files is a ranked
  regression that local M4 evidence could not see, and the differing list above
  is the bisection set.

### The process risk worth naming

Post-frontier work was merged into the integration base on local M4 Pro
evidence, in a regime where Evidence 8 shows sub-0.5% ranked differences are
undecidable and where the `_nax` prefill kernels touched by #138 and #170 are
**not reachable on the M4 Pro research host at all**. That combination — merging
prefill `_nax` changes on evidence from a host that cannot execute them — is the
most likely way for the base to have drifted below the frontier without anyone
noticing. Evidence 9 does not prove that happened; it proves nobody has checked,
and it identifies the 11-file set to check first.

