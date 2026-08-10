# R106-B — Revert-residual forensics: Stage 0 stops the round at N-0

> **Superseded, kept as the Stage 0 record.** This file is the `r106-b-rev1`
> report, written when the assignment's Stage 0 gate ended the round. The
> assignment was later revised to `r106-b-rev3`, which reopened the round with a
> Stage A/B/C structure; the deliverable for that revision is
> `research/maple-nezuko-r106b-revert-residual.md`, and its §A.2 carries the
> Stage 0 numbers below forward unchanged. Nothing here is retracted — the
> N-RESIDUAL verdict still stands — but read the newer file for the round's
> outcome.

Student: `maple-nezuko` · PR #616 · assignment `maple-r106-b-revert-residual-forensics`
revision `r106-b-rev1` · base `8e8faf28635ad0bba81243ae98b56cd00eeac16d`
W&B run: [`d942xnno`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/d942xnno)
Official receipts consumed: **0** (Rule 88 — `senpai/submit-official.sh` was never invoked).
No file under `Sources/` or `Vendor/` was modified; the whole round is read-only
plus `research/`.

## Outcome

**N-0 — nothing to attribute.** The preregistered Stage-0 gate fires on the
primary pool: both primary 95 % intervals for the revert residual cover zero.
Stages 1 (JIT kernel-source corpus dump) and 2 (`DARKBLOOM_TRACE_FUSION`
dispatch diff) were therefore **not** run, exactly as the assignment's hard gate
requires.

| axis | residual | pooled sd | dof | 95 % CI | z | sd that would make it significant |
|---|---|---|---|---|---|---|
| D (decode) | **+19.405 µs/step** | 11.920 | 10 | **[−18.156, +56.966]** | +1.151 | ≤ 6.158 |
| T = D − 4P | **+20.149 µs/step** | 12.068 | 10 | **[−17.877, +58.175]** | +1.181 | ≤ 6.394 |

The residual is real as an arithmetic difference of two single receipts and
entirely unremarkable as an estimate: it sits at ~1.2 pooled standard errors.
To make it significant the receipt-level σ on decode would have to be roughly
**half** its smallest defensible measured value.

This is the outcome the assignment designated as a full-credit stop, and it
independently reproduces **fern #576** (T +20.1, CI [−12.3, +52.6]; D +19.4, CI
[−11.6, +50.4], null fires) from a different corpus and a different variance
pool, and it agrees with the advisor's own r103 §6–§8 retraction of the
20.15 µs/step pricing.

## 1. Preregistration and the one declared deviation

`research/maple-nezuko-r106b-stage0-preregistration.md` was committed at
`7c8b02a5`, **before** any receipt was pulled or any number computed
(Rules 40/72). It fixed, in advance: the estimand, the two arms by submission
sha only, the estimator `SE = σ·√(1/n_f + 1/n_r)` with a Student-t 95 %
interval, the replicate-group definition, which pool is primary, and the stop
rule (*N-0 fires iff either primary interval covers zero*).

**Declared deviation (not silently repaired).** The preregistered primary pool
`PP-ALL` defined a replicate group as *receipts sharing an identical
`submissionCommitSha`*. In the frozen corpus that pool is **empty**: 1 693
receipts carry a sha and there are 1 693 **distinct** shas, so no sha has ≥ 2
receipts. `PP-ALL` and its `PP-TRIM` sensitivity are **INESTIMABLE** (0 groups,
dof 0). The substitute, chosen and stated before any interval was read, is
*content-level* replicate identity: two receipts replicate when their submitted
surfaces are identical modulo comments. Everything downstream is reported under
that substitute and labelled `DP-*`.

A related bug found and fixed while wiring the gate: NaN comparisons in an
inestimable pool made the gate print `PROCEED`. The estimator now carries an
explicit `estimable` flag so an undefined interval can never read as "excludes
zero". This matters for exactly the pool that turned out to be empty.

## 2. The two arms

Confirmed against the frozen corpus, `n = 1` each — this is the whole factual
basis of the residual:

| arm | submission sha | createdAt (UTC) | D µs/tok | P µs/tok | T µs/step | cs |
|---|---|---|---|---|---|---|
| frontier | `bd33883eb89209c9714c8c570e399613ecbaa848` | 2026-08-09T18:26:38.423Z | 4913.117 | 187.857 | 4161.690 | 2.582286 |
| Arm R | `ef055b9b1956e8056267972308fd7deddd89649d` | 2026-08-09T00:58:27.946Z | 4893.712 | 188.043 | 4141.541 | 2.589321 |

`R_D = +19.405`, `R_T = +20.149` µs/step. The two receipts fall on the same UTC
day but are **17.47 hours apart** — see §5, which is why no session-matching
argument can rescue the estimate.

## 3. Structural finding — the r103 σ pool is contaminated

To build the substitute pool I had to recompute replicate identity, and doing so
uncovered a defect in the published variance pool.
`research/advisor_r103_replicate_sigma.py` computes its group digest as a
comment-insensitive sha256 over **`Sources/` only**. The submitted surface is
`Sources/` **and** the listed `Vendor/` files — 2 300 files, of which only 54
are under `Sources/`. Two candidates can therefore be merged into one "replicate
group" while differing in vendored MLX kernel or cache code that runs on the
scored path.

I reran identity over the **full** submitted surface (still comment-insensitive:
a differing line is forgiven only when it is a whole-line `//` comment outside a
`"""` literal), using `git ls-tree -r` blob shas as the fast path and a
`difflib` line diff on the survivors. **5 of the 10 candidate r103 groups are
rejected for genuine non-comment `Vendor/` differences:**

| rejected group | n | first offending file |
|---|---|---|
| `r103:1008c6920be35876` | 4 | `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp` |
| `r103:4d5ac413d1a7d82e` | 2 | `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift` |
| `r103:521a2f7124786af6` | 4 | `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized.cpp` |
| `r103:7cbffc2c17d7f2a9` | 4 | `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp` |
| `r103:d18d0983830b73a1` | 3 | `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp` |

Those are precisely the NVFP4 quantized-matmul and KV-cache surfaces that the
campaign is actively editing, so the difference is not cosmetic. Any σ pooled
over these groups mixes **real between-candidate signal** into what is being
reported as **within-candidate noise**. That inflates σ in the pools that
include them and, worse, makes the pool's meaning unclear.

Consequence for this round: I do **not** use the contaminated pools as primary.
The primary pool `DP-VERIFIED` keeps only groups whose full submitted surface is
verified identical modulo comments — 5 groups, 15 receipts, dof 10:

| group | n | span (UTC) |
|---|---|---|
| `fresh:r104A/armA` | 3 | 2026-08-10 04:29 → 07:27 |
| `fresh:r105A/A0` | 3 | 2026-08-10 03:42 → 05:23 |
| `fresh:r105A/A1` | 2 | 2026-08-10 06:00 → 06:42 |
| `r103:9beb75a6fbc5e042` | 2 | 2026-08-04 10:02 → 10:26 |
| `r103:dc437b0e0b918c86` | 5 | 2026-08-09 02:56 → 05:44 |

`DP-VERIFIED` is deliberately the **narrowest defensible σ**, i.e. the hardest
available test for N-0: `sd_D = 11.920`, `sd_T = 12.068`, and for prefill
`sd_P = 0.3085`. N-0 still fires.

## 4. Robustness — all twelve intervals cover zero

Every pool I can construct, contaminated or clean, trimmed or not, on either
axis, gives the same verdict. The gate is not sensitive to the pool choice.

| pool | axis | sd | dof | 95 % CI | z | break-even sd |
|---|---|---|---|---|---|---|
| DP-R103 | D | 20.211 | 17 | [−40.90, +79.71] | +0.68 | 6.504 |
| DP-R103 | T | 12.540 | 17 | [−17.27, +57.57] | +1.14 | 6.753 |
| DP-R103-TRIM | D | 11.682 | 14 | [−16.03, +54.84] | +1.17 | 6.398 |
| DP-R103-TRIM | T | 12.079 | 14 | [−16.49, +56.79] | +1.18 | 6.643 |
| DP-FRESH | D | 9.430 | 5 | [−14.88, +53.69] | +1.46 | 5.338 |
| DP-FRESH | T | 9.240 | 5 | [−13.44, +53.74] | +1.54 | 5.543 |
| DP-COMB | D | 18.326 | 22 | [−34.34, +73.15] | +0.75 | 6.616 |
| DP-COMB | T | 11.871 | 22 | [−14.67, +54.97] | +1.20 | 6.870 |
| DP-COMB-TRIM | D | 11.133 | 19 | [−13.55, +52.36] | +1.23 | 6.556 |
| DP-COMB-TRIM | T | 11.401 | 19 | [−13.60, +53.89] | +1.25 | 6.807 |
| **DP-VERIFIED** | **D** | **11.920** | **10** | **[−18.16, +56.97]** | **+1.15** | **6.158** |
| **DP-VERIFIED** | **T** | **12.068** | **10** | **[−17.88, +58.17]** | **+1.18** | **6.394** |

The break-even column is the useful one for planning: **no pool is within a
factor of 1.7 of the σ that would be needed**, and the smallest break-even σ
across all twelve rows is 5.338. A σ that small has never been observed on this
benchmark.

## 5. Structural finding — `dof_across_day = 0`

The natural rescue for a wide interval is "match the sessions". It is not
available here. **No verified replicate group spans two UTC days** — the spans
in §3 are all ≤ 3 hours. So the pooled σ that produced the intervals above is a
**within-day, within-≤3 h** σ, while the two arms being compared are **17.5
hours apart**.

That means the reported CI is, if anything, **too narrow**: the arms carry
whatever between-day/between-session component exists on top of the within-day
component I could measure, and the corpus contains zero verified replicate pairs
with which to estimate it. Any attempt to shrink the interval by "controlling
for session" would need cross-day replicates that do not exist in the receipt
history. `dof_across_day = 0` is recorded in `stage0-analysis.json` as a
first-class field.

## 6. Why the earlier "4.9 sd" power claim was a selection artefact

The advisor's pre-round power argument was that four pre-revert receipts span
only 4893.7–4900.5 µs/tok, so `sd ≈ 3.3` and +16.3 µs would be 4.9 sd. That σ
cannot be used, because those four receipts were selected by being at the top of
the leaderboard — i.e. **conditioned on low D**. Conditioning on the low tail of
a distribution and then estimating the distribution's spread from the survivors
is guaranteed to understate it.

The direct demonstration is group `r103:dc437b0e0b918c86`: five receipts,
**verified identical on the full submitted surface modulo comments**, all on
2026-08-09, unconditioned on rank:

| receipt | createdAt (UTC) | D µs/tok |
|---|---|---|
| `4b0e051bf3cd` | 02:56 | 4894.114 |
| `d6a5f9e7346e` | 03:18 | 4931.226 |
| `e1b6e2be2792` | 04:06 | 4900.524 |
| `ca91d86c904c` | 04:55 | 4916.141 |
| `5d9060aa0d36` | 05:44 | 4912.621 |

**Range 37.112 µs/tok over 2.8 hours from identical code — 1.91× the residual
being chased.** Note that two of these five (`4b0e051b`, `e1b6e2be`) are members
of the "top four" that produced the 3.3 σ; the other three, same code, sit up to
37 µs higher. The 4.9 sd claim is retired.

Two smaller corrections that fall out of the same check:

- The r103 file's truncated `ts` field gave 03:05/03:27/04:15/05:05 for this
  group; the corpus `createdAt` values above are authoritative.
- The tree map's reading that `4b0e051b` and `e1b6e2be` "differ by R3" is wrong:
  on the full submitted surface, modulo comments, they are **identical**.

## 7. Why Stages 1 and 2 were not run

The assignment makes Stage 0 a hard gate: *N-0 ⇒ stop, publish "nothing to
attribute"*. Spending the Stage-1 tracer quota (1 671 168 bytes) and the Stage-2
`DARKBLOOM_TRACE_FUSION` diff to localise a difference whose existence is not
established would be attributing noise to a kernel.

It is also largely redundant. **tanjiro #572** already ran the equivalent
comparison across this revision range on the official stack: 103 Metal
libraries, identical dispatch order, grids, threadgroups and buffers,
408 dispatches per decode step at **every** revision, 11 243 positionally
identical dispatches; only two kernels change text at all
(`residual_rms_router…_pf1` at R3, and `sliding_fused_attn_ring_v1` going 2-way
→ 4-way at #565), and #572 withdrew its own absolute µs attributions. In the
assignment's verdict vocabulary the *structural* question already reads as
**verdict A** (kernel text differs, dispatch structure identical). What Stage 0
shows is that there is no *timed* residual left for that text difference to
explain, so re-deriving A here would add cost and no information.

Reported verdict for this round is therefore **N-0**, not A/B/C: the A/B/C
branch is only reachable through a Stage-0 `PROCEED`.

## 8. Artifacts (Rule 75 — sha256 and byte size)

| artifact | bytes | sha256 |
|---|---|---|
| `/tmp/r106b/receipt-corpus-frozen.json` (not committed; 1 787 records, 1 693 with sha, 1 218 with metrics) | 19 936 617 | `d450b5b5dc895f0d2d4de52d790035e88ea2e55255fed1ae04c80a9a7c70c12b` |
| `research/artifacts/maple-nezuko-r106b/stage0-analysis.json` | 44 430 | `02fc1847f09252d344716d52b57f1fa060cbf21ea4b40e103c197c601e2ed908` |
| `research/artifacts/maple-nezuko-r106b/replicate-identity-verified.json` | 16 221 | `f064c482550e44954f18e654289589c30d4dbf9d348805a533a01e413045e0ff` |
| `research/maple-nezuko-r106b-stage0-preregistration.md` | 8 228 | `f718daf66a0cb47ae6b570b8516901d43184eae832cfe6b349c05b0a70f91646` |
| `research/nezuko_r106b_pull_corpus.py` | 3 236 | `63e9494775c57d17b83c64d89041f8a307d88c9c5df90a7a9a8561414cd1ac7e` |
| `research/nezuko_r106b_verify_replicates.py` | 9 455 | `9933580d0500df5230e6dd418bf46ff5d7990969fb148bf89c36f4ac8fa92589` |
| `research/nezuko_r106b_stage0_ci.py` | 17 223 | `bc77c7a82aadff4ebd03cd87fda5bce53de996cd949ff6f981b6588fa6031b80` |

Benchmark id `1854efdf-feba-4773-bae9-b80520881a74`. The corpus is 19.9 MB and
is deliberately kept out of the repository; it is reproducible with the puller
below, and the two slim JSONs carry everything the report cites.

Rule 77 (grid/threadgroup geometry) and Rule 82 (per-kernel labels inadmissible
for pricing) do not bind: no kernel was dispatched, traced or priced this round.
Rule 86 does not bind: no `--local-iterate` delta appears as evidence — every
number above comes from official receipt metrics. Rule 58: the corpus puller and
the identity checker are built on the existing `research/advisor_r103_*` and
`research/r103b/scripts/` scaffolding rather than new machinery.

## 9. Reproduction

```bash
# 1. pull the receipt corpus (read-only GETs; needs MLXFAST_API_TOKEN in env)
python3 research/nezuko_r106b_pull_corpus.py --out /tmp/r106b/receipt-corpus-frozen.json

# 2. verify content-level replicate identity over the FULL submitted surface
python3 research/nezuko_r106b_verify_replicates.py \
  --corpus /tmp/r106b/receipt-corpus-frozen.json \
  --r103 research/artifacts/advisor-r103/replicate-sigma.json \
  --out /tmp/r106b/replicate-identity-verified.json

# 3. Stage-0 confidence intervals and the gate
python3 research/nezuko_r106b_stage0_ci.py \
  --corpus /tmp/r106b/receipt-corpus-frozen.json \
  --r103 research/artifacts/advisor-r103/replicate-sigma.json \
  --verified /tmp/r106b/replicate-identity-verified.json \
  --slim /tmp/r106b/stage0-analysis.json
```

Step 2 needs the 34 submission commits present locally; they are fetchable by
sha from `origin` (`git fetch --quiet origin <sha>`), which the script does.
Runtime is ~3.4 s for step 2 and under a second for step 3. No GPU, no model
load, no benchmark lock.

## 10. What this implies for the round, and follow-ups I did not implement

1. **Stop pricing the revert residual.** Three independent analyses (fern #576,
   advisor r103 §6–§8, this round) now put it at z ≈ 0.7–1.2. Continuing to
   fund attribution work against it converts receipts into noise.
2. **The σ pool needs fixing at source.** `advisor_r103_replicate_sigma.py`
   should digest the full submitted surface, not `Sources/` only; 5 of its 10
   groups are over-merged today. Every downstream power calculation that used
   that σ should be recomputed. I did not edit the advisor script.
3. **Receipt-level σ is the binding constraint, not analysis technique.** With
   `sd_D ≈ 11.9` and one receipt per arm, the smallest detectable decode effect
   at 95 % is ≈ 37.6 µs/step ≈ 0.57 % of `cs`. Any future single-receipt-per-arm
   comparison below that is unfalsifiable by construction. Two obvious levers:
   require `n ≥ 3` per arm for anything priced below ~40 µs/step, and prefer
   the T axis (`sd_T` is no worse than `sd_D` and T removes the 4P term).
4. **Prefill is 39× quieter than decode.** `sd_P = 0.3085` vs `sd_D = 11.920`
   on the same verified pool. If a mechanism has any prefill-side signature, it
   is far cheaper to detect there and then argue across.
5. **Cross-day replicates are missing entirely.** `dof_across_day = 0`. If the
   campaign wants to compare arms measured hours apart — which it does, all the
   time — a small deliberate investment in a repeated-identical-candidate pair
   on two different days would buy a between-session σ that currently does not
   exist. That is an advisor-level budget call, so I did not spend receipts on
   it.

## 11. Round hygiene notes

- **Zero official receipts** were consumed. `senpai/submit-official.sh` was not
  invoked at any point (Rule 88).
- **The r104-A receipt ladder is cancelled and nothing automated is driving
  it.** Verified on this host: `ps aux` matched no `submit-official`,
  `watch-submission`, `ladder`, or `mlxfast submit` process; `crontab -l`
  reports no crontab; `~/Library/LaunchAgents` does not exist. **Legs 05–08 will
  not be submitted.**
- No file under `Sources/` or `Vendor/` was modified, so the editable byte
  budget is untouched and no static-review surface changed.
