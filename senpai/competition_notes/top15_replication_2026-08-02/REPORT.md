# MLX Fast leaderboard wins and campaign bootstrap report

Snapshot: **2026-08-02T09:07:21Z**<br>
Report evidence cut: **2026-08-03T06:44:30Z**<br>
Track: `laguna-xs-2.1-serial-v2`<br>
Official runner: **Apple M5 Max**<br>
Local transfer host: **Apple M4 Max, 128 GB, Mac16,6**<br>
Study: `mlxfast-top15-replication-2026-08-02`

This report turns the fastest 15 promoted submissions in the frozen leaderboard
snapshot into a practical starting point for our own optimization campaign. Its
purpose is deliberately balanced:

- preserve proven ideas, arithmetic contracts, failed experiments, and source
  lineage so we do not pay to rediscover them;
- separate complete-snapshot evidence from isolated causal evidence;
- state exactly where M4 transfer results disagree with official M5 outcomes;
- preserve the completed negative-control calibration without overstating what
  one formal comparison and two bounded diagnostics can prove;
- establish rank 126 as a same-host incremental quality baseline without
  rewriting any frozen primary comparison;
- preserve the stopped partial performance campaign without converting five
  invalid selected candidate results into speed claims, while retaining all four
  completed extended-AIME diagnostics; and
- retain search breadth beyond the mechanisms already explored by the leaders.

The frozen official analysis is in [official-findings.md](official-findings.md),
the exact identities and measurements are in [candidates.json](candidates.json),
and the local protocol is in [README.md](README.md). The [live
leaderboard](https://mlx.fast/) can move after this report's frozen snapshot.

## Status at a glance

| Evidence stream | Expected | Audited result at evidence cut | Report treatment |
|---|---:|---|---|
| Official promoted snapshots | 15 | 15/15 accepted on M5 | Complete; authoritative ranking evidence |
| Local M4 quality comparisons | 15 | 11 formal comparisons; 4 bounded AIME non-completions; 0 invalid | Complete for the frozen quick-profile contract |
| Rank-126-relative quality diagnostic | 15 | **10 retrospective: 6 retain / 4 regress; 1 rank-126 self-control; 4 bounded no-decisions** | Complete, offline, and useful for future incremental drift only |
| Local M4 performance arms | 16 including rank 111 comparator | **1 historically valid receipt, 0 current-contract receipts; 5 invalid selected candidate results; 10 pending** | Partial and stopped; rank 111 must be refreshed before any candidate comparison |
| Negative controls | 3 | **3/3 processed: 1 formal regression; 2 bounded AIME non-completions; 0 invalid** | Complete for the frozen quick-profile control contract; no class-separating signal established |
| Extended AIME diagnostics | 4 terminal ranks | **4/4 valid isolated diagnostics; all still length-bounded at 6,144 tokens** | Complete for the frozen diagnostic-only contract; primary quick-profile decisions remain unchanged |

The report is therefore complete as an official-history, frozen local-quality,
control, and extended-diagnostic synthesis, but **not** as a local performance
replication. Only rank 111 has a credible historical timing receipt. An
external ephemeral launcher/watchdog transcript indicates a manual 80% fan
hold and inherited environment, but that transcript is not bound into the
retained attempt; it is not a same-policy comparator for the repaired auto-fan campaign. The attempted
candidate timings are retained as rejected diagnostics after an implausible
`1.5C` telemetry value was allowed through the original gate. The calibration
has a two-part conclusion: the current composite
M4 gate is decisively unsuitable as a veto on this cohort because it rejects
every formally comparable official success; the choice of a replacement rule
and any inference about the private M5 gate remain inconclusive because only
one selected official failure produced a formal local comparison. The
rank-126-relative diagnostic nevertheless gives our own campaign a practical
same-host baseline and shows that response identity—not the 3% numeric
terms—separates the early and late formal lineage clusters.

## Executive findings

### 1. The official gain is real, cumulative, and overwhelmingly decode-led

From rank 111 to rank 126, the official score rose from
`2.09306570699382` to `2.4549506212825`, a gain of
**17.2897063422%**. Candidate decode time fell from
`6.4278893203125` to `5.249092125` ms/token, **18.3387911112% lower**,
while candidate prefill fell only **0.5801036940%** from
`0.1968064765625` to `0.195664794921875` ms/token.

On the additive log-score scale, the paired decode movement accounts for
**97.2831470646%** of the gain and prefill for **2.7168529354%**. This is the
first campaign-level prior: optimize single-token decode unless a prefill idea
has unusually strong evidence.

### 2. The largest reusable win was to read half as many attention-weight bytes

Ranks 116, 117, and 120 moved attention Q/K/V and output projection weights
from a group-32 affine INT8 side representation at `1.125` bytes/parameter to
the checkpoint's group-16 NVFP4 representation at `0.5625`
bytes/parameter. Coverage widened from layers `32...39`, to `24...39`, to
`17...39`, and finally to all 40 layers.

Along the conceptual rank-113-to-rank-120 branch, official score rose
**11.8150034686%** and candidate decode fell **14.3698394409%**. The three
attention-representation promotions account for **60.2771067789%** of the
window's chronological score movement. The final all-layer snapshot at rank
120 was the largest single promotion in the window.

This ladder is now landed at its legal endpoint. Repeating the same boundary
sweep is low-value unless a new representation or kernel changes the
correctness surface.

### 3. Fusion is not a goal; eliminating duplicated work is the goal

Rank 123's split-K fusion won by eliminating a real intermediate and replaying
the original BF16/FP32 boundaries. Rank 124 won more by turning a different
fusion off: the fused norm/QKV/gate kernel repeated the same 2,048-element RMS
reduction in every output-tile threadgroup. Computing RMSNorm once and letting
separate projections consume the 4 KiB BF16 row was faster.

The practical rule is to count producer multiplicity, barriers, input rereads,
live registers, threadgroup memory, and occupancy. Dispatch count alone is not
a sufficient objective.

### 4. Source history is a branching experiment graph, not a list of additive patches

The platform promotion commits are linear, but the submissions were developed
from conceptual side branches. Rank 113 replaces rank 112; ranks 114, 115, and
116 are alternatives from rank 113; ranks 118, 119, and 120 are alternatives
from rank 117. Rank 121 explicitly restores router work removed by rank 120's
whole-file overlay.

Chronological leaderboard deltas are ranking facts. They are not isolated
mechanism effects when the conceptual base differs. Our campaign should keep
an explicit active-path manifest after every promotion.

### 5. Exactness boundaries are discrete and nonmonotonic

The rank-117 local boundary sweep passed at NVFP4 start layers 24, 20, 17;
failed at 19, 18, 16; and ultimately promoted layer 17. A sequential search
that stopped at the first failure would have missed the faster exact boundary.

Near-tie argmax gates do not create a smooth approximation curve. Preserve
payload bit patterns, signed-zero behavior, tie ordering, BF16 materialization
points, and reduction order, then test each candidate boundary independently.

### 6. M4 quality transfer is strongly discordant with the official M5 labels

All 15 candidate snapshots passed the official M5 gates. Locally:

- all 15 matched the checked public first token (`5991`);
- all 11 formally comparable quick-profile runs **failed** the composite local
  gate: the 3% downstream/PPL terms, the separate 7/9 ranked-prefix rule, and
  the exact public first-token rule;
- each of those 11 missed all three nontrivial predeclared decision components:
  downstream correct count, PPL, and ranked-GPQA prefix retention;
- all 11 had `0/9` exact ranked-GPQA prefix matches while preserving identical
  row sets; and
- ranks 116–119 hit the frozen 2,048-token AIME ceiling, so their raw vectors
  are diagnostics and have **no formal local gate decision**.

Conditional on producing a formal comparison, observed acceptance of an
official success is `0/11`; four other successes are censored by the frozen
AIME ceiling. This configuration is not a defensible submission veto for M5.
The completed control cohort adds coverage evidence, but is insufficient to
calibrate a replacement threshold or infer unpublished private-gate policy.

### 7. Completed controls expose probe gaps, not useful discrimination

The three frozen official failures are now processed locally. Two hit the same
2,048-token AIME ceiling as several successful snapshots, so they have raw
diagnostics but no formal local decision. The remaining control, rank 202, is
a valid local regression. That sounds encouraging in isolation, but it is not
selective evidence:

- Rank 201 failed the official 64-step public behavior gate, yet matched the
  local first token `5991`. It then truncated on AIME item `2025-I-01`, leaving
  no local retention decision. This demonstrates that a one-token probe can
  miss the known failure; it does not tell us whether the divergence occurs
  later in the trajectory or only on M5.
- Rank 202 failed hidden official correctness and is a formal local regression,
  but its `24/53` downstream count is **higher** than every formally comparable
  official success (`22/53` or `23/53`). Its PPL,
  `14.903492398049115`, is exactly equal at the reported value to successful ranks
  120–122, and both the control and those successes have `0/9` ranked-prefix
  matches plus the exact public first token. The threshold rejects both
  classes; it does not identify the known failure.
- On all four predeclared gate components, rank 202 is at least as strong as
  successful ranks 120–126: it has more downstream answers correct, equal or
  lower PPL, the same `0/9` ranked-prefix result, and the same exact public
  token. Any componentwise-monotone threshold rule that admits ranks 120–126
  must also admit this known failure. Tightening or loosening the percentages
  alone cannot repair the surrogate.
- Rank 203 also failed hidden official correctness, but terminated at the AIME
  ceiling. Its raw `24/53` and PPL `14.841542008507624` overlap or outperform
  the local official-success cohort, while its first public token is exact.
  With no formal prefix comparison or gate decision, it provides no observed
  discriminator.

The useful result is therefore bounded but actionable: none of the predeclared
components or validated decision rules separates the formally comparable
labels, so the current composite remains a debugging instrument rather than a
submission-safety oracle. Post-hoc combinations on this small selected cohort
would be overfit, not evidence of a calibrated replacement.

### 8. Tripling the AIME ceiling did not turn truncation into completion

The isolated diagnostic reran exactly `2024-2024-II-2` for ranks 116–119 with
the response ceiling raised from 2,048 to 6,144 tokens. All four runs finished
successfully as diagnostics, and all four model responses still ended with
`finish_reason = length` rather than `stop`:

- rank 116 extracted answer `1` from 14,432 characters;
- ranks 117–119 each extracted answer `7` from 11,427 characters; and
- none matched the gold answer `236`.

This rules out the narrow hypothesis that these responses were merely a few
tokens short of a natural stop at the primary ceiling. It establishes
persistent length-bounded generation for these four snapshots on this M4 path;
the report does not quantify repetition. At the primary 2,048-token ceiling,
known-failing control 203 also stopped on `2024-2024-II-2`, so that event is not
specific to the accepted class. The 6,144-token rerun contains accepted
snapshots only and therefore cannot test class separation. It does **not**
retroactively convert any primary terminal arm into a formal comparison, and it
is not evidence that the officially accepted M5 snapshots are invalid.

### 9. Rank 126 is a useful incremental baseline, but response identity is the separator

An offline, provenance-checked recomparison uses the completed rank-126 M4
artifact as a forward-looking baseline for our own autoresearch. Its 3%
numeric bounds are `22/53` downstream and PPL no worse than
`15.43371157578533`, with the unchanged `7/9` ranked-GPQA and exact public-token
requirements.

Ranks 120–122 retain at exactly `7/9`, while ranks 123–125 retain at `9/9` and
are response-identical; rank 126 is the tautological `9/9` self-control. Ranks
112–115 have **better** downstream count and PPL than rank 126 but regress
because they match `0/9` ranked-GPQA responses. Thus loosening or tightening
the 3% numeric terms would miss the observed lineage boundary; behavior
identity carries the signal. Ranks 116–119 remain censored.

This establishes a practical same-host baseline for future candidates, not an
official/private-gate surrogate. Applying a future rank-126 reference backward
to earlier promotions is diagnostic only.

### 10. Apple GPU geometry does not transfer reliably

Rank 126's one-row-per-SIMD down retile was roughly 12% slower on another Apple
GPU but about 0.4% faster in isolated official M5 candidate time. The local
study also requires `DARKBLOOM_EXPERT_ALIGNED_GATHER=0` because these historical
snapshots predate the architecture-aware gather predicate.

Representation and dependency-graph ideas may transfer. Occupancy, SIMD
ownership, register pressure, and `_nax` scheduling must be re-established on
the official M5.

## Evidence model

Every conclusion in this report should be read through the following tiers.

| Tier | Evidence | What it establishes | What it does not establish |
|---|---|---|---|
| A | Promoted official M5 snapshot with complete gate record | The complete snapshot was valid and achieved the recorded paired score | Every bundled edit helped; the named mechanism alone caused the delta |
| B | Narrow diff plus same-binary control, repeated bracket, or independent official candidate-phase receipt | Stronger causal support for a mechanism on the tested M5 path | Portability to another Apple GPU or a different frontier |
| C | Audited formal M4 quick-profile comparison | Exact result under this harness, M4 override, evaluator, weights, and local baseline | Equivalence to private M5 token/semantic gates or M5 performance |
| D | Hash-bound terminal or isolated extended M4 diagnostic | The preserved command ran and the exact bounded-generation outcome is auditable | A formal local retention decision, a private-M5 correctness verdict, or a promotion claim |
| E | Planned or pending arm | Experimental intent and required evidence fields | Any result whatsoever |

Mechanism notes are useful source-grounded hypotheses, not automatically Tier
B causal proofs. One of the strongest late results is rank 124 because its path
reachability, same-binary control, and producer-duplication explanation agree.
Ranks 112, 118, and 125 are bundles and deserve more conservative attribution.

## Official optimization lineage and waves

### Conceptual lineage

```text
rank 111  af08576
├── rank 112  metadata indexing + shared attention carriers
└── rank 113  metadata indexing only
    ├── rank 114  inline top-8 routed-QMV prologue
    ├── rank 115  SG4/PF2 affine-QKV geometry
    └── rank 116  NVFP4 boundary 32 → 24
        └── rank 117  NVFP4 boundary 24 → 17
            ├── rank 118  top-8 + unpacked R1 routed QMV + SG4/PF2
            ├── rank 119  producer-computed router keys
            └── rank 120  NVFP4 boundary 17 → 0 + fusion eligibility
                └── rank 121  restore producer-computed router keys
                    └── rank 122  exact fused-tail scale/sign fold
                        └── rank 123  fused split-K prefill + dead-arm deletion
                            └── rank 124  separate attention norm/QKV/gate
                                └── rank 125  uchar4 affine loads + layer-0 async
                                    └── rank 126  one-row-per-SIMD down retile
```

### Wave 1 — exact metadata and dependency experiments, ranks 112–115

The durable lesson is not a particular surviving kernel. It is the method:
compress metadata without changing its bits, remove dependency windows rather
than merely dispatches, and tune ownership geometry together with prefetch and
live-state pressure.

- Ranks 112–113 indexed exact BF16 `(scale,bias)` payload pairs through a
  UInt16 table. Rank 113 is the cleaner metadata-only receipt.
- Rank 114 computed the strict top-8 winner inside routed QMV so that the QMV
  no longer waited on the standalone selector. The selector remained for
  later consumers.
- Rank 115 paired four-SIMD ownership with prefetch depth two. SG4 with the old
  depth four was locally negative.

These branches were later displaced or made hot-path-irrelevant by all-layer
NVFP4, but the exactness and dependency-graph techniques remain reusable.

### Wave 2 — checkpoint NVFP4 attention, ranks 116, 117, and 120

This is the dominant landed wave. It halved decode-side attention-weight bytes
and moved numerics toward the checkpoint representation rather than adding a
new approximation. Ranks 118 and 119 are useful alternatives from rank 117,
not intermediate steps toward rank 120.

The endpoint is active at rank 126: all 40 attention QKV/O banks use checkpoint
NVFP4. The affine INT8 side representation is now a fallback/control.

### Wave 3 — reconcile the all-NVFP4 frontier, ranks 121–126

- Rank 121 restored producer-computed router ordinals.
- Rank 122 simplified exact E4M3 scale/sign handling, but that fused path is
  default-off after rank 124.
- Rank 123 fused split-K prefill while reproducing the old numerical boundaries.
- Rank 124 removed duplicated RMSNorm by un-fusing attention input projection.
- Rank 125 combined aligned `uchar4` loads and layer-0 `asyncEval`.
- Rank 126 retiled fused down+residual to expose four times as many independent
  weight streams, with an architecture-sensitive result.

## Exact official leaderboard record

Decode and prefill cells show `paired speedup / candidate ms-token`. The
conceptual base is the source-history base, not necessarily the preceding
leaderboard row.

| Rank | Submission / source / PR | Base | Score | Decode x / ms-token | Prefill x / ms-token | Mechanism |
|---:|---|---:|---:|---:|---:|---|
| 111 | [0682cc25](https://mlx.fast/api/submissions/0682cc25-40a1-4f0e-bb96-c3b0f768b53c) · [`af085760`](https://github.com/Layr-Labs/mlxfast-challenge/commit/af085760e96a5d719a2ba9c5817454158d9edb86) | — | 2.09306570699382 | 2.1520609555455104 / 6.4278893203125 | 1.9256073909692932 / 0.1968064765625 | Immediate comparator; not a mechanism claim |
| 112 | [aa6660cb](https://mlx.fast/api/submissions/aa6660cb-a3e4-410a-a365-bb117e3e98f1) · [`df0af746`](https://github.com/Layr-Labs/mlxfast-challenge/commit/df0af746de208e267ae16e7dc62f901aa5cff77a) · [PR 971](https://github.com/Layr-Labs/mlxfast-challenge/pull/971) | 111 | 2.11750832958454 | 2.181236387388597 / 6.3409827421875 | 1.9372796103266816 / 0.196908529296875 | Indexed affine metadata + shared attention arrays |
| 113 | [96bfd3b7](https://mlx.fast/api/submissions/96bfd3b7-49c2-4f0b-b0bd-288173ac284b) · [`274a909a`](https://github.com/Layr-Labs/mlxfast-challenge/commit/274a909ae2f8b65414ec7b1bbb5981c5cf091cde) · [PR 973](https://github.com/Layr-Labs/mlxfast-challenge/pull/973) | 111 | 2.11953731302476 | 2.1895445992266027 / 6.3250559921875 | 1.922661713712948 / 0.19706990625 | Metadata-only re-land |
| 114 | [3223e19d](https://mlx.fast/api/submissions/3223e19d-8e7a-4001-a2c8-0176900a7005) · [`149892c3`](https://github.com/Layr-Labs/mlxfast-challenge/commit/149892c38865cdb78af6c1b1158fecc853446ed4) · [PR 983](https://github.com/Layr-Labs/mlxfast-challenge/pull/983) | 113 | 2.12281334772927 | 2.19030925055764 / 6.32126790625 | 1.9325508351309963 / 0.1967543125 | Inline exact top-8 in routed QMV |
| 115 | [dd341a52](https://mlx.fast/api/submissions/dd341a52-a695-4d0d-8bdf-75ef44a9c74a) · [`d4cb1ae8`](https://github.com/Layr-Labs/mlxfast-challenge/commit/d4cb1ae8d63cd3e59169bc7685d85ca7970241e6) · [PR 985](https://github.com/Layr-Labs/mlxfast-challenge/pull/985) | 113 | 2.12365737170721 | 2.199289573232799 / 6.28067903125 | 1.9120117300597668 / 0.19681005859375 | Four-SIMD affine norm/QKV, PF2 |
| 116 | [8449082c](https://mlx.fast/api/submissions/8449082c-4dc2-4526-b3bd-69712c3b8a8e) · [`5b46c79c`](https://github.com/Layr-Labs/mlxfast-challenge/commit/5b46c79cfd8d6496989ba5977950e969ba4107ac) · [PR 986](https://github.com/Layr-Labs/mlxfast-challenge/pull/986) | 113 | 2.1640759452478 | 2.2736319629228885 / 6.0902330703125 | 1.8660767105710185 / 0.197249185546875 | NVFP4 boundary 32 → 24 |
| 117 | [df2a7483](https://mlx.fast/api/submissions/df2a7483-9c5b-4f4c-8a2f-9fee780515d7) · [`500d92a0`](https://github.com/Layr-Labs/mlxfast-challenge/commit/500d92a0f486a0297f312d8f4d38d5ab3b58f900) · [PR 995](https://github.com/Layr-Labs/mlxfast-challenge/pull/995) | 116 | 2.23332009444833 | 2.3707153235296095 / 5.85775065625 | 1.8670918086319037 / 0.196566080078125 | NVFP4 boundary 24 → 17 |
| 118 | [214fd89a](https://mlx.fast/api/submissions/214fd89a-69af-4858-af54-8a801672c78d) · [`fc306048`](https://github.com/Layr-Labs/mlxfast-challenge/commit/fc306048e61c2cb7e56a8ff406db40adafcc8e79) · [PR 999](https://github.com/Layr-Labs/mlxfast-challenge/pull/999) | 117 | 2.2414044139947 | 2.384968779200647 / 5.8330843046875 | 1.8605133763413995 / 0.197362142578125 | Top-8 + unpacked R1 QMV + SG4/PF2 |
| 119 | [5139da0f](https://mlx.fast/api/submissions/5139da0f-ac51-4a81-b3d8-880a8a74f58f) · [`c5206993`](https://github.com/Layr-Labs/mlxfast-challenge/commit/c5206993d510ca0c50861b1f5d3d26030d76a22b) · [PR 1002](https://github.com/Layr-Labs/mlxfast-challenge/pull/1002) | 117 | 2.26148968661582 | 2.3764347227699028 / 5.841873375 | 1.9489503612125283 / 0.197732177734375 | Producer-computed router keys |
| 120 | [db173215](https://mlx.fast/api/submissions/db173215-a7d7-4863-a333-8132c33be279) · [`7b2c9407`](https://github.com/Layr-Labs/mlxfast-challenge/commit/7b2c9407032e41408fbfaba94625d9c53b1934ca) · [PR 1003](https://github.com/Layr-Labs/mlxfast-challenge/pull/1003) | 117 | 2.36996072007723 | 2.5682349829553703 / 5.4161556015625 | 1.862345783592638 / 0.1969033203125 | All-layer NVFP4 + fusion eligibility |
| 121 | [9847ff8f](https://mlx.fast/api/submissions/9847ff8f-918e-4988-ba2f-a1137d23784b) · [`e6596576`](https://github.com/Layr-Labs/mlxfast-challenge/commit/e65965761f34afbabc696b3eccdd363863edd480) · [PR 1014](https://github.com/Layr-Labs/mlxfast-challenge/pull/1014) | 120 | 2.37074944628857 | 2.565469122263709 / 5.3976897734375 | 1.870864160764886 / 0.1969623203125 | Restore producer-computed router keys |
| 122 | [cc79cef2](https://mlx.fast/api/submissions/cc79cef2-8a0e-4bbd-aaba-bdaaae453249) · [`71b80b1f`](https://github.com/Layr-Labs/mlxfast-challenge/commit/71b80b1f33b01eb3edc871df85675cdbd6fe6320) · [PR 1017](https://github.com/Layr-Labs/mlxfast-challenge/pull/1017) | 121 | 2.38717668655054 | 2.5506483303610423 / 5.424066078125 | 1.956980526474057 / 0.196989095703125 | Exact E4M3 sign + scale fold |
| 123 | [70a3ad4b](https://mlx.fast/api/submissions/70a3ad4b-70da-4b17-ab4f-388945dfee29) · [`60f436a2`](https://github.com/Layr-Labs/mlxfast-challenge/commit/60f436a2361eef72b207c2a3cf0d5b6984b8b0d1) · [PR 1024](https://github.com/Layr-Labs/mlxfast-challenge/pull/1024) | 122 | 2.39434519974008 | 2.5759627244533863 / 5.3932425078125 | 1.9227744102278264 / 0.196256265625 | Exact fused split-K prefill |
| 124 | [a0da915f](https://mlx.fast/api/submissions/a0da915f-450a-4063-bf8e-ec1661f4a661) · [`70fe340b`](https://github.com/Layr-Labs/mlxfast-challenge/commit/70fe340becd16cf5efa40884963283e6a834c84b) · [PR 1027](https://github.com/Layr-Labs/mlxfast-challenge/pull/1027) | 123 | 2.45073250313311 | 2.6492948985023403 / 5.2904329375 | 1.9399598118033108 / 0.19554093359375 | Separate RMSNorm/QKV/gate |
| 125 | [4173c401](https://mlx.fast/api/submissions/4173c401-0f25-41fd-bec7-cdea22a1aac3) · [`13496639`](https://github.com/Layr-Labs/mlxfast-challenge/commit/1349663988dacafe7ee4b5b11832a4891d1aa5cc) · [PR 1051](https://github.com/Layr-Labs/mlxfast-challenge/pull/1051) | 124 | 2.45196981458518 | 2.6402444474889513 / 5.2711627578125 | 1.963939313525582 / 0.195565998046875 | `uchar4` loads + layer-0 `asyncEval` |
| 126 | [05e7894f](https://mlx.fast/api/submissions/05e7894f-0eaf-4f6d-8622-499d1e44185d) · [`7702fab8`](https://github.com/Layr-Labs/mlxfast-challenge/commit/7702fab8a41fe2f4ff2ae281beeb1548b31e3406) · [PR 1056](https://github.com/Layr-Labs/mlxfast-challenge/pull/1056) | 125 | 2.4549506212825 | 2.6466235994572105 / 5.249092125 | 1.9592709649968867 / 0.195664794921875 | One-row-per-SIMD fused-down retile |

All 15 candidate rows passed the official correctness stack. The official
records report 1,344 checked steps, `max_abs_diff = 0`, 9/9 GPQA TTFT cases,
and `semantic_gpqa_passed = true` for every row. Displayed semantic counts were
8/9 for ranks 112, 113, 114, 117, 118, 120, and 122; 9/9 for the other eight.
That observation does not reveal unpublished judge policy.

## Audited M4 quality transfer

### Frozen local gate

The numeric quality reference is the July 30 untouched M4 baseline at
`quality-results/baseline-quick-weave-v3-m4-20260730`. Its clean checkout is
commit `eec3f82c9adebc99e3ed15c74138e1ab8032d9cd`, with editable-source SHA-256
`a6b9b9f177b8f36c664fdf3df06341c3780a96c6a7309247cd92809bee1c21e9`,
transform-source SHA-256
`5929dfd16cedf35645e5a2bab62baa06ae4908382eae16917f1594bafb3715ec`,
and change label `untouched-baseline-weave-v3`. It ran on the recorded
`Mac16,6` M4 Max under the pinned evaluator. This quality reference is neither
leaderboard rank 111 nor rank 126; candidate arms use the common rank-126
harness with each promoted editable overlay restored.

| Component | Baseline | Required candidate result |
|---|---:|---:|
| Downstream aggregate | 26/53 | at least 26/53 |
| PPL over 256 target tokens | 13.954858401802964 | at most 14.386451960621613 |
| Ranked GPQA exact-prefix retention | 9/9 baseline rows | at least 7/9 matches |
| Public first-token probe | token 5991 after 512-token prompt | exact token 5991 |
| Response row sets | 62 comparable non-PPL rows | exact row-set match |

The formal decision is a **composite**, not a single 3% threshold. After exact
row-set agreement establishes comparability, a local retain requires all of:

1. the 3% numeric terms—downstream correct count at least `26/53` and PPL at
   most `14.386451960621613`;
2. at least `7/9` exact ranked-GPQA prefix matches; and
3. the exact public first token `5991`.

The 3% multiplier does not lower the discrete correct-count floor:
`ceil(26 × 0.97) = 26`. Because there is no rank-111 quality arm, this study
cannot localize how much observed M4 drift predates rank 112.

### Per-rank local result matrix

`†` marks raw terminal diagnostics. They are not formal comparisons and must
not be counted as local gate failures or passes.

| Rank | Local status | Correct | PPL | MMLU | GPQA-g | GPQA-s | AIME | GSM8K | Ranked prefix | Public | Local gate |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 112 | Formal | 23/53 | 14.613698880 | 8/20 | 5/9 | 3/9 | 4/9 | 3/6 | 0/9 | pass | **FAIL** |
| 113 | Formal | 23/53 | 14.613698880 | 8/20 | 5/9 | 3/9 | 4/9 | 3/6 | 0/9 | pass | **FAIL** |
| 114 | Formal | 23/53 | 14.613698880 | 8/20 | 5/9 | 3/9 | 4/9 | 3/6 | 0/9 | pass | **FAIL** |
| 115 | Formal | 23/53 | 14.613698880 | 8/20 | 5/9 | 3/9 | 4/9 | 3/6 | 0/9 | pass | **FAIL** |
| 116 | Terminal AIME | 23/53† | 14.778296654† | 9/20† | 6/9† | 4/9† | 1/9† | 3/6† | n/e† | pass | **NOT EVALUATED** |
| 117 | Terminal AIME | 22/53† | 14.963476719† | 7/20† | 6/9† | 3/9† | 3/9† | 3/6† | n/e† | pass | **NOT EVALUATED** |
| 118 | Terminal AIME | 22/53† | 14.963476719† | 7/20† | 6/9† | 3/9† | 3/9† | 3/6† | n/e† | pass | **NOT EVALUATED** |
| 119 | Terminal AIME | 22/53† | 14.963476719† | 7/20† | 6/9† | 3/9† | 3/9† | 3/6† | n/e† | pass | **NOT EVALUATED** |
| 120 | Formal | 22/53 | 14.903492398 | 9/20 | 4/9 | 4/9 | 2/9 | 3/6 | 0/9 | pass | **FAIL** |
| 121 | Formal | 22/53 | 14.903492398 | 9/20 | 4/9 | 4/9 | 2/9 | 3/6 | 0/9 | pass | **FAIL** |
| 122 | Formal | 22/53 | 14.903492398 | 9/20 | 4/9 | 4/9 | 2/9 | 3/6 | 0/9 | pass | **FAIL** |
| 123 | Formal | 22/53 | 14.970700229 | 9/20 | 4/9 | 4/9 | 2/9 | 3/6 | 0/9 | pass | **FAIL** |
| 124 | Formal | 22/53 | 14.970700229 | 9/20 | 4/9 | 4/9 | 2/9 | 3/6 | 0/9 | pass | **FAIL** |
| 125 | Formal | 22/53 | 14.970700229 | 9/20 | 4/9 | 4/9 | 2/9 | 3/6 | 0/9 | pass | **FAIL** |
| 126 | Formal | 22/53 | 14.970700229 | 9/20 | 4/9 | 4/9 | 2/9 | 3/6 | 0/9 | pass | **FAIL** |

All 11 formal rows also had exact response row-set agreement. Ranks 112–115
matched 13/62 baseline response texts; ranks 120–126 matched 11/62. The ranked
prefix test was `0/9` throughout the formal set.

### Output clusters

The audited results form five exact metric clusters:

| Ranks | Status | Shared signature |
|---|---|---|
| 112–115 | Formal | 23/53; PPL 14.613698880455747; ranked 0/9; 13/62 response matches |
| 116 | Terminal | 23/53 raw; PPL 14.77829665389895; AIME 1/9; one length stop |
| 117–119 | Terminal | 22/53 raw; PPL 14.963476718728943; AIME 3/9; one length stop |
| 120–122 | Formal | 22/53; PPL 14.903492398049115; ranked 0/9; 11/62 response matches |
| 123–126 | Formal | 22/53; PPL 14.970700228511769; ranked 0/9; 11/62 response matches |

Within-cluster identity is evidence that several structural optimizations
preserve the observed M4 behavior of their conceptual branch. It is not proof
of equivalence to the M5 path or private oracle.

### Rank-126-relative incremental diagnostic

The completed rank-126 artifact is now frozen as the same-host quality baseline
for future autoresearch candidates. It records `22/53`, PPL
`14.970700228511769`, the exact public token, and nine ranked-GPQA responses.
Under the same composite contract, a future retain requires at least `22/53`,
PPL at most `15.43371157578533`, at least `7/9` ranked-GPQA matches, and the
exact public token.

[`derive-rank126-quality.sh`](derive-rank126-quality.sh) recomputes ten
retrospective comparisons plus the rank-126 self-control offline under the
frozen evaluator and records the four bounded arms without inventing
comparisons. It writes a separate ignored result tree and never replaces the
primary `comparison.json` files.

| Ranks | Evidence | Rank-126-relative outcome | Numeric terms | Ranked GPQA | Full response identity |
|---|---|---|---|---:|---:|
| 112–115 | Formal | **REGRESSION** | Pass: 23/53; PPL 14.613698880 | 0/9 | 11/62 (17.7%) |
| 116–119 | Bounded | **NO FORMAL DECISION** | Not comparable | — | — |
| 120–122 | Formal | **RETAIN** | Pass: 22/53; PPL 14.903492398 | 7/9 | 60/62 (96.8%) |
| 123–125 | Formal retrospective | **RETAIN** | Pass: 22/53; PPL 14.970700229 | 9/9 | 62/62 (100%) |
| 126 | Self-control | **RETAIN** | Pass: 22/53; PPL 14.970700229 | 9/9 | 62/62 (100%) |

The numeric terms pass for every formal row. The decision boundary is entirely
behavioral: ranks 112–115 differ from the late lineage, ranks 120–122 sit at the
declared prefix floor, ranks 123–125 are identical under this profile, and rank
126 verifies the self-comparison path. This does not calibrate the private M5
judge, but it gives our campaign a much more relevant incremental drift alarm
than comparing every future experiment only to the older July 30 checkout.

The rank-111 quality anchor remains pending. It is isolated in
[`quality-anchor-run.json`](quality-anchor-run.json) and
[`run-quality-anchor.sh`](run-quality-anchor.sh), so running it later will not
change the frozen 15-arm manifest or its artifacts.

### Calibration by official label

The local outcome table is a two-class by three-decision calibration, not a
population confusion matrix:

| Frozen official label | Local regression | Local retain | No formal decision |
|---|---:|---:|---:|
| Success, ranks 112–126 | 11 | 0 | 4 |
| Failure, controls 201–203 | 1 | 0 | 2 |

Formal-decision coverage is `11/15` (73.3%) for successes, `1/3` (33.3%) for
selected failures, and `12/18` (66.7%) overall. All 12 formally evaluable arms
receive the same local-regression decision. Thus `0/11` is the conditional
observed acceptance of official successes, not an estimate of population
sensitivity.

Control 202 also rules out threshold-only repair over the predeclared
components. It records `24/53`, PPL `14.903492398049115`, `0/9` ranked-prefix
matches, and the exact public token. Ranks 120–122 record `22/53`, the same PPL,
`0/9`, and the exact token; ranks 123–126 record `22/53`, worse PPL
`14.970700228511769`, `0/9`, and the exact token. Control 202 therefore
componentwise dominates ranks 120–126. Any monotone threshold rule over these
four components that accepts those official successes must accept the known
failure too.

These counts have important dependence and missingness limits. The 11 formal
positive rows are a connected promotion lineage, not independent trials; they
collapse to three metric signatures and two baseline response-match counts;
the later two metric clusters both match `11/62` baseline responses but do not
have identical response text. The controls were deliberately selected for
available official failure evidence, not sampled from all failures, and only
one of three is formally comparable. Six of 18 arms abstain because of AIME
length, so the missingness may be informative. One pass per arm provides no run-to-run
variance estimate. Do not infer population sensitivity, specificity, or
false-pass rates from this table.

### Local-versus-official gate matrix

The 3% number applies only to the local downstream/PPL terms. The composite
also contains a separate `7/9` exact-response identity rule and an exact
one-token public probe. None reproduces the private M5 contract.

| Contract surface | Official M5 contract/result | Local M4 proxy/result | Transfer conclusion |
|---|---|---|---|
| Public behavior | 64-step checked trajectory; all 15 promoted | First token only; all 15 successes and all 3 controls matched token 5991 | A shallow subset, not an established surrogate for the official trajectory; it misses control 201's known public failure |
| Hidden exact tokens | 512-token teacher-forced base plus anchor, free-run, and timed oracle; all promoted | No local analogue; private artifacts unavailable | No equivalence or threshold inference is possible |
| GPQA behavior | TTFT plus semantic judging passed for all 15 | Exact string/prefix identity against an M4 baseline: 0/9 in all 12 formal arms | These are different predicates; 0/9 exact identity does not imply semantic failure |
| Downstream quality | No direct official aggregate or threshold analogue | 11/11 formal successes and the formal failure below the local 26/53 floor | Advisory semantic drift only; not an M5 validity oracle |
| PPL | No official PPL correctness gate | 11/11 formal successes and the formal failure above 14.386451961 | Advisory distributional drift only; not an M5 validity oracle |
| AIME completion | No official AIME gate in the published correctness stack | Four primary successes hit both the 2,048- and 6,144-token local ceilings; two controls hit 2,048 | Persistent local bounded generation, not evidence about an official AIME predicate; terminal arms have no frozen-gate decision |
| Negative-control calibration | One public-trajectory failure and two hidden-correctness failures | All three first tokens exact; rank 202 formally regressed; ranks 201 and 203 terminal | First-token coverage misses a known public failure; the sole formal reject is not selective because all formal successes also reject |
| Local class separation | 15 official successes versus 3 selected official failures | 11 formal successes and rank 202 all reject; other 6 arms are terminal | No predeclared component or validated local rule separates the formally comparable labels |
| Performance correctness | Official paired timing accepts only exact oracle tokens | Rank 111 passed 1,025 checked steps behind credible `40.0C`/`39.9C` gates; ranks 113–117 passed the same correctness check but their timing gates accepted implausible `1.5C` samples | Correctness execution worked, but there is no valid candidate performance comparison |

The observed discordance can arise from M4-versus-M5 numerical behavior,
different kernel dispatch, the required gather override, and differences
between exact-prefix and semantic judgments. It must not be simplified to
"the official winners lost quality," nor can the two contracts be ordered on a
single stricter-versus-looser axis.

## M4 versus M5 transfer limits

1. **The official M5 is the ranking authority.** Paired candidate/baseline
   timing on the same cooled machine controls host drift. M4 absolute timings
   cannot reproduce M5 occupancy or `_nax` scheduling.
2. **The expert-gather override changes the selected local path.** Every local
   arm sets only `DARKBLOOM_EXPERT_ALIGNED_GATHER=0` to avoid a pre-NAX layout
   mismatch in historical snapshots.
3. **Public goldens are M5-generated.** Near-tie argmax changes can be correct
   for a different Apple generation yet fail exact local continuation checks.
4. **Geometry is architecture-sensitive.** Rank 126 is direct sign-reversal
   evidence. SIMD ownership and register-pressure ideas need M5 receipts.
5. **The quick profile is a proxy, not the private gate.** Its first-token
   public check and exact ranked prefixes neither reproduce the 64-step public
   trajectory nor the hidden semantic stack.
6. **Current M4 gate behavior is too false-negative-heavy for veto use.** Use
   it to characterize drift and preserve evidence, not to discard an M5-safe
   optimization without an official check.
7. **The completed controls do not repair that calibration.** Rank 202 is a
   formal true negative, but it is locally stronger than accepted neighbors on
   downstream count and identical to ranks 120–122 on PPL. Ranks 201 and 203
   are terminal. No predeclared component or validated decision rule separates
   the formally comparable official labels.
8. **The completed extended diagnostic does not repair it either.** All four
   primary terminal ranks remain length-bounded after tripling the ceiling.
   That narrows the local failure mode, but the isolated reruns deliberately
   produce no formal gate decision and no private-M5 equivalence claim.
9. **Rank 126 is useful for incremental drift, not private-gate inference.**
   All ten retrospective rows pass its numeric bounds, while response
   identity splits ranks 112–115 from ranks 120–126. Use that contract for
   future same-host comparisons and keep its meaning local.
10. **The stopped performance run exposed a fail-open local telemetry path.**
   Rank 111 genuinely gated at `40.0C` and `39.9C`. Starting with rank 112,
   `macmon` intermittently returned an impossible `1.5C`; the old helper
   warned and then accepted it because `1.5 <= 40`. Candidate timings produced
   after that event are rejected. The ordinary fixed local gate tolerates two
   transient bad samples and fails on the third; the audited study runner is
   stricter—it rejects the first missing or implausible sample and stops the
   whole campaign on a thermal or telemetry failure.
   Similar erroneous M4 temperatures have been reported upstream in
   [`macmon` issue #12](https://github.com/vladkens/macmon/issues/12), which
   supports a reader/IOReport failure rather than benchmark arithmetic, though
   the exact `1.5C` mechanism is not recoverable because the old run retained
   no raw reader JSON. The repaired runner now adds a persistent five-sample
   responsiveness check before model load and retains that raw receipt.

## Campaign correctness policy pending M5 calibration

The completed study supports a hard-versus-advisory policy, not a retuned
percentage:

| Treatment | Evidence | Campaign action |
|---|---|---|
| Hard validity stop | Source, editable-overlay, artifact, protocol, or exact row-set mismatch; incomplete/terminal run | Repair or rerun; never convert an invalid or censored result into a pass or regression |
| Hard correctness evidence | Exact public trajectory, upstream-equivalence check, or correctness trace against a matched reference and path | Block promotion until explained; on non-M5 hardware, first reproduce the same divergence on the unchanged frontier to distinguish hardware drift |
| Advisory quality evidence | Downstream correct count, PPL, ranked-prefix identity, response-text clusters, one-token public probe, and extended AIME diagnostics on M4 | Record and investigate drift, but do not veto an otherwise exact candidate from these signals alone |
| Final authority | Official M5 public, hidden-token, GPQA, timed-oracle, and thermal gates | Decide rankability and promotion |

Do not loosen or tighten the 3% terms from this cohort: control 202 proves that
monotone threshold adjustment cannot separate it from ranks 120–126. Add a
rank-111 quality arm to locate inherited drift. Rank 126 is now established as
the same-host incremental quality baseline for autoresearch, while the July 30
untouched baseline remains the cumulative reference. Whether the pending
anchor and future same-host comparisons yield a predictive local surrogate
remains an experiment, not a conclusion of this report.

## Stopped partial local performance study — 16 arms

**Conclusion boundary:** this study does not show that M5 speedups failed to
transfer to M4. It contains zero valid candidate-versus-rank-111 performance
comparisons. A refreshed same-M4 baseline can still make this host a useful
directional filter, especially for architecture-neutral work; M5-specific
occupancy, SIMD ownership, `_nax`, and small kernel-geometry effects still need
official M5 evidence.

The audited historical state is **1/16 valid, 5/16 invalid, and 10/16 pending**,
but the restart contract is **0/16 current-contract**. Rank 111 is the sole
credible historical local timing; it must be rerun before it can normalize new
candidates. Ranks 113–117 are retained, hash-bound
correctness-passing attempts, but they are invalid for performance because
both timed phases accepted implausible `1.5C` telemetry. Rank 112 failed its
original decode cool-down; its repaired attempt 2 then cooled plausibly from
`50.1C` to `45.4C`, reheated to `48.0C`, and was stopped at the still-blocked
prefill gate before any timing. Rank 118 was interrupted during the prefill
gate when the original campaign was stopped; ranks 119–126 did not start.

The intended executable local comparator is rank 111, submission
`0682cc25-40a1-4f0e-bb96-c3b0f768b53c` at source
`af085760e96a5d719a2ba9c5817454158d9edb86`. It is distinct from both the July
30 quality baseline above and the organizer's pinned calibration source. Local
`--local-submit` is a directional transfer measurement with a 1,023-step
decode path and one repeat, while the official frozen timing window uses 128
decode steps. It is not a direct reproduction of the private official run.
External ephemeral launcher/watchdog evidence indicates that the selected
rank-111 attempt used a manual 80% fan policy, whereas repaired attempts
declare macOS automatic fan control. The old attempt itself does not bind that
controller transcript. In either case, the policy provenance differs and the
attempt cannot be mixed with auto-fan candidates in an A/B comparison.

The `0.305–0.426` scores printed by the harness are comparisons between this
M4 and the organizer's pinned **M5** calibration constants. Rank 111 itself
prints only `0.426050`, so those values are not the study's intended
same-M4 comparison and do not mean the snapshots achieved only 30–40% of rank
111. The runner now labels that number as a pinned-M5 calibration estimate and
prints the separate rank-111-normalized index.

Rank 111 is a grandfathered pre-cutover historical receipt. Its original metadata did not
bind the runner, thermal helper, reader, or log hashes; the repaired validators
therefore admit that one legacy comparator only by source identity, finish-time
cutover, exact ordered gate transcript, and frozen log SHA-256
`f324d48d983efb427326c13caf0bc3dd0cc5b5e71a786f4f06c4c492270c4130`.
No candidate result receives that exception, and the exception no longer lets
the runner skip `perf baseline`, unlock a rank-specific candidate, or compute a
new rank-111-normalized index.

| Rank | Submission / source | Required role | Audited status | Local decode | Local prefill | Index vs rank 111 |
|---:|---|---|---|---:|---:|---:|
| 111 | [0682cc25](https://mlx.fast/api/submissions/0682cc25-40a1-4f0e-bb96-c3b0f768b53c) · [`af085760`](https://github.com/Layr-Labs/mlxfast-challenge/commit/af085760e96a5d719a2ba9c5817454158d9edb86) | Intended comparator | **HISTORICAL VALID / REFRESH REQUIRED** — credible gates and correctness, but legacy env + external, non-receipt-bound manual-80 indication | 20.5638 ms/token | 3.4124 ms/token | historical 1.0000× |
| 112 | [aa6660cb](https://mlx.fast/api/submissions/aa6660cb-a3e4-410a-a365-bb117e3e98f1) · [`df0af746`](https://github.com/Layr-Labs/mlxfast-challenge/commit/df0af746de208e267ae16e7dc62f901aa5cff77a) | Candidate | **PENDING / NO RESULT** — attempt 1 decode cool-down failed; repaired attempt 2 stopped at hot prefill gate before timing | — | — | — |
| 113 | [96bfd3b7](https://mlx.fast/api/submissions/96bfd3b7-49c2-4f0b-b0bd-288173ac284b) · [`274a909a`](https://github.com/Layr-Labs/mlxfast-challenge/commit/274a909ae2f8b65414ec7b1bbb5981c5cf091cde) | Candidate | **INVALID TIMING** — `1.5C` accepted; correctness passed | 20.8950 ms/token† | 4.0655 ms/token† | 0.9458×† |
| 114 | [3223e19d](https://mlx.fast/api/submissions/3223e19d-8e7a-4001-a2c8-0176900a7005) · [`149892c3`](https://github.com/Layr-Labs/mlxfast-challenge/commit/149892c38865cdb78af6c1b1158fecc853446ed4) | Candidate | **INVALID TIMING** — `1.5C` accepted; correctness passed | 21.3053 ms/token† | 3.8188 ms/token† | 0.9468×† |
| 115 | [dd341a52](https://mlx.fast/api/submissions/dd341a52-a695-4d0d-8bdf-75ef44a9c74a) · [`d4cb1ae8`](https://github.com/Layr-Labs/mlxfast-challenge/commit/d4cb1ae8d63cd3e59169bc7685d85ca7970241e6) | Candidate | **INVALID TIMING** — `1.5C` accepted; correctness passed | 21.1201 ms/token† | 3.8492 ms/token† | 0.9511×† |
| 116 | [8449082c](https://mlx.fast/api/submissions/8449082c-4dc2-4526-b3bd-69712c3b8a8e) · [`5b46c79c`](https://github.com/Layr-Labs/mlxfast-challenge/commit/5b46c79cfd8d6496989ba5977950e969ba4107ac) | Candidate | **INVALID TIMING** — `1.5C` accepted; correctness passed | 21.9334 ms/token† | 3.7576 ms/token† | 0.9301×† |
| 117 | [df2a7483](https://mlx.fast/api/submissions/df2a7483-9c5b-4f4c-8a2f-9fee780515d7) · [`500d92a0`](https://github.com/Layr-Labs/mlxfast-challenge/commit/500d92a0f486a0297f312d8f4d38d5ab3b58f900) | Candidate | **INVALID TIMING** — `1.5C` accepted; correctness passed | 30.6693 ms/token† | 3.8998 ms/token† | 0.7166×† |
| 118 | [214fd89a](https://mlx.fast/api/submissions/214fd89a-69af-4858-af54-8a801672c78d) · [`fc306048`](https://github.com/Layr-Labs/mlxfast-challenge/commit/fc306048e61c2cb7e56a8ff406db40adafcc8e79) | Candidate | **PENDING / INTERRUPTED** — stopped during prefill gate | — | — | — |
| 119 | [5139da0f](https://mlx.fast/api/submissions/5139da0f-ac51-4a81-b3d8-880a8a74f58f) · [`c5206993`](https://github.com/Layr-Labs/mlxfast-challenge/commit/c5206993d510ca0c50861b1f5d3d26030d76a22b) | Candidate | **PENDING** | — | — | — |
| 120 | [db173215](https://mlx.fast/api/submissions/db173215-a7d7-4863-a333-8132c33be279) · [`7b2c9407`](https://github.com/Layr-Labs/mlxfast-challenge/commit/7b2c9407032e41408fbfaba94625d9c53b1934ca) | Candidate | **PENDING** | — | — | — |
| 121 | [9847ff8f](https://mlx.fast/api/submissions/9847ff8f-918e-4988-ba2f-a1137d23784b) · [`e6596576`](https://github.com/Layr-Labs/mlxfast-challenge/commit/e65965761f34afbabc696b3eccdd363863edd480) | Candidate | **PENDING** | — | — | — |
| 122 | [cc79cef2](https://mlx.fast/api/submissions/cc79cef2-8a0e-4bbd-aaba-bdaaae453249) · [`71b80b1f`](https://github.com/Layr-Labs/mlxfast-challenge/commit/71b80b1f33b01eb3edc871df85675cdbd6fe6320) | Candidate | **PENDING** | — | — | — |
| 123 | [70a3ad4b](https://mlx.fast/api/submissions/70a3ad4b-70da-4b17-ab4f-388945dfee29) · [`60f436a2`](https://github.com/Layr-Labs/mlxfast-challenge/commit/60f436a2361eef72b207c2a3cf0d5b6984b8b0d1) | Candidate | **PENDING** | — | — | — |
| 124 | [a0da915f](https://mlx.fast/api/submissions/a0da915f-450a-4063-bf8e-ec1661f4a661) · [`70fe340b`](https://github.com/Layr-Labs/mlxfast-challenge/commit/70fe340becd16cf5efa40884963283e6a834c84b) | Candidate | **PENDING** | — | — | — |
| 125 | [4173c401](https://mlx.fast/api/submissions/4173c401-0f25-41fd-bec7-cdea22a1aac3) · [`13496639`](https://github.com/Layr-Labs/mlxfast-challenge/commit/1349663988dacafe7ee4b5b11832a4891d1aa5cc) | Candidate | **PENDING** | — | — | — |
| 126 | [05e7894f](https://mlx.fast/api/submissions/05e7894f-0eaf-4f6d-8622-499d1e44185d) · [`7702fab8`](https://github.com/Layr-Labs/mlxfast-challenge/commit/7702fab8a41fe2f4ff2ae281beeb1548b31e3406) | Candidate | **PENDING** | — | — | — |

† Rejected diagnostic only—these values are shown to explain the terminal log,
not as evidence that the candidate regressed. All five are below rank 111 in
the discarded observation; rank 117 is the largest apparent loss. Snapshot
application was independently checked: refs, harness bindings, hashes, weights,
correctness, runtime binary changes, and the rank-117 mechanism-consistent
memory shift all indicate that the candidate code did run. The plausible
explanations are invalid thermal conditions, M4-specific transfer, and
long-window/lazy-kernel effects—not a failure to apply the snapshots.

Any resumed campaign may first use the standalone model-free
`thermal-preflight` as a readiness diagnostic, then must create
a fresh auto-fan/current-contract rank-111 attempt, then run rank 112 as a
canary before the remaining cohort. One
full `--local-submit` observation per arm will still be directional, not a
variance estimate. The repaired runner reinstalls a content-pinned, local-only
trusted `benchmark.sh` and fan helper after every reset to the rank-126 model
harness, pins `macmon 0.7.2`, starts the benchmark under a clean `env -i`
allowlist, rejects the first bad telemetry sample, aborts the cohort on a bad
receipt, samples one persistent five-record reader stream after installing each
arm's snapshot and before model load, requires changing plausible GPU
temperatures with ordered timestamps, binds the receipt to the exact
rank/submission/commit/attempt with a 30-second handoff ceiling, verifies
automatic fan mode before and after every arm, and binds the preflight plus
runner/tool/log hashes into new attempt metadata. The two in-benchmark phase
gates independently require fresh responsive streams as timing begins. Every
real telemetry reader has a 15-second wall-clock deadline and an isolated
TERM-to-KILL cleanup path. The benchmark itself is likewise supervised as one
isolated process group; HUP/INT/QUIT/TERM and normal exits with surviving
descendants cannot return while a model-holding worker remains. No
candidate timing has passed the post-cutover integration yet. Rank-112 attempt
2 exercised an earlier intermediate clean-environment, plausible-telemetry,
fail-closed gate, then exited `130` with no score or integrity receipt while
still above 40C. It predates and therefore does not validate the final
attempt-bound preflight, responsive phase-gate, or process-group contract. The
runner now also disables interactive fan prompts explicitly, and the helper
requires foreground terminal ownership, so an audited subprocess cannot be
suspended indefinitely by `SIGTTIN`.
The separate rank-111 quality anchor must be sequenced outside this performance
campaign because its evaluator lock is distinct and both paths can hold the
full model.

## Completed negative-control cohort — 3 arms

The controls are frozen in [negative-controls.json](negative-controls.json)
and [control-run.json](control-run.json). They are separate from the 15
promoted candidates. All three exact source commits resolve to verified Git
commit objects, and the isolated control runner reports **3/3 processed: one
formal regression, two bounded non-completions, zero pending, zero invalid**.

### Identity and official failure class

| Rank | Official label | Submission / source | Mechanism |
|---:|---|---|---|
| 201 | `public_gate_token_mismatch` | [e40e4013](https://mlx.fast/api/submissions/e40e4013-5757-4be4-89ab-e46bd2e03bad) · [`ddbac7da`](https://github.com/Layr-Labs/mlxfast-challenge/commit/ddbac7dae50a6318fe350791fe825c594d8425c2) | Native-affine attention-tail boundary 24 → 16 |
| 202 | `correctness_failed`; official public gate passed | [7c9eac6d](https://mlx.fast/api/submissions/7c9eac6d-37b4-46ef-aaaa-35c9a999b582) · [`6e991d4b`](https://github.com/Layr-Labs/mlxfast-challenge/commit/6e991d4b70e0ad631eaefd9b583cddd9442920fd) | Bind NVFP4 split-K dispatch to small-M prefill shapes |
| 203 | `correctness_failed`; official public gate passed | [81f43490](https://mlx.fast/api/submissions/81f43490-f699-4d45-b2c1-18c9b3fbaf85) · [`df76fdf9`](https://github.com/Layr-Labs/mlxfast-challenge/commit/df76fdf99b192f3043639cba82f9c86438c8f792) | All-reference NVFP4 attention + corrected router keys + shared-expert prefill gate/up fusion |

### Audited M4 outcomes

`n/e†` means the ranked task ran, but the terminal arm has no formal
baseline-prefix comparison. Raw task correctness was `0/9` for both terminal
arms. Their raw vectors remain diagnostic only.

| Rank | Local status | Correct | PPL | MMLU | GPQA-g | GPQA-s | AIME | GSM8K | Ranked prefix | Public first token | Local decision |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 201 | Bounded AIME | 21/53† | 14.46127697721767† | 9/20† | 4/9† | 4/9† | 1/9† | 3/6† | n/e† | exact `5991` | **NOT EVALUATED** |
| 202 | Formal | 24/53 | 14.903492398049115 | 12/20 | 4/9 | 4/9 | 1/9 | 3/6 | 0/9 | exact `5991` | **REGRESSION** |
| 203 | Bounded AIME | 24/53† | 14.841542008507624† | 10/20† | 4/9† | 5/9† | 2/9† | 3/6† | n/e† | exact `5991` | **NOT EVALUATED** |

Rank 202 is a valid exit-3 comparison with exact row sets. It fails downstream
retention (`24/53`, required `26/53`), PPL retention (`14.903492398049115`,
maximum `14.386451960621613`), and ranked-prefix retention (`0/9`, required
`7/9`); only 9/62 response texts match the baseline. Its public first token is
exact. The operative artifact field is
`local_retention_gate_passed = false`; the generic `quality_gate_passed` field
is `null` and must not be substituted for that decision.

The two terminal records are complete, hash-bound bounded diagnostics, not
failed comparisons:

| Rank | Truncated AIME item | Finish | Extracted answer | Sample chars | Formal consequence |
|---:|---|---|---:|---:|---|
| 201 | `2025-I-01` | `length` | 81 | 4,064 | No prefix comparison and no local retention decision |
| 203 | `2024-2024-II-2` | `length` | 4 | 5,033 | No prefix comparison and no local retention decision |

Control 203 stops on the same `2024-2024-II-2` item as successful ranks
116–119 at the primary ceiling. The shared event across official labels makes
the 2,048-token length stop non-discriminative on this observed cohort.

### What the controls prove—and what they do not

- They prove that the complete local quick-profile path can process these exact
  snapshots with frozen source, harness, evaluator, wrapper, model, and host
  provenance.
- Rank 201 proves the local first-token probe does not cover the known official
  public failure: local token 1 matches, whereas the official 64-step M5
  trajectory rejects. It does not locate the divergent step or distinguish a
  later-token coverage gap from an M4/M5 path difference.
- Rank 202 is a concordant negative in the narrow sense that a known official
  failure also receives a local regression decision. It does **not** establish
  discrimination: all 11 formally comparable official successes receive the
  same decision, rank 202 has more downstream answers correct than any of
  them, and its PPL exactly matches successful ranks 120–122.
- Rank 203 cannot be counted as a detected regression or a pass. Its stronger
  raw aggregate than the successful local cohort and exact first token further
  show that these predeclared coarse measures do not isolate the private
  correctness failure in this comparison.

Accordingly, the control cohort supplies coverage and non-selectivity evidence,
not a calibrated safety classifier. Hardware, dispatch reachability, public
probe depth, exact-prefix versus semantic judging, and the two AIME ceilings
remain confounders.

### Control artifact anchors

| Artifact | SHA-256 |
|---|---|
| Rank 201 `terminal-noncompletion.json` | `6e83baa0ee3141dca80e06e0c98e57256fe21f3f410b3f2da6e31e9571a7ff03` |
| Rank 202 `summary.json` | `00ba5f95bef76b6e9c2bb1604217907c1452d8aaf1afa160f4881c6912dad0ee` |
| Rank 202 `comparison.json` | `8d79b5031d20bbe955dd40e13ead7c76b546958795818990209a8d57c1521bb9` |
| Rank 203 `terminal-noncompletion.json` | `f12612a8c9989037dd084d763fa4fc4932a4e684b4da0bf30234aa1fe4bd46b9` |

## Completed isolated extended AIME diagnostics

The fixed quick profile stops generation at 2,048 response tokens. The four
primary terminal markers preserve complete raw diagnostics but intentionally
record no formal comparison. The separate contract in
[EXTENDED_AIME_DIAGNOSTICS.md](EXTENDED_AIME_DIAGNOSTICS.md) revalidated each
hash-bound terminal marker and reran only `2024-2024-II-2`, changing only the
response ceiling to 6,144 tokens.

The report-data audit finds **4/4 valid completed diagnostics, zero pending,
and zero invalid**. Here, “completed diagnostic” means that the isolated run
and its artifact protocol completed cleanly. It does not mean that the model
response reached a natural stop: every response remained length-bounded.

| Rank / submission | Quick answer · chars | Diagnostic attempt | 6,144-token answer · chars | Finish | Audited outcome |
|---|---:|---|---:|---|---|
| [116 · 8449082c](https://mlx.fast/api/submissions/8449082c-4dc2-4526-b3bd-69712c3b8a8e) | 9 · 5,080 | `attempt-3` | 1 · 14,432 | `length` | `still_length_bounded_at_6144` |
| [117 · df2a7483](https://mlx.fast/api/submissions/df2a7483-9c5b-4f4c-8a2f-9fee780515d7) | 3 · 4,041 | `attempt-1` | 7 · 11,427 | `length` | `still_length_bounded_at_6144` |
| [118 · 214fd89a](https://mlx.fast/api/submissions/214fd89a-69af-4858-af54-8a801672c78d) | 3 · 4,041 | `attempt-1` | 7 · 11,427 | `length` | `still_length_bounded_at_6144` |
| [119 · 5139da0f](https://mlx.fast/api/submissions/5139da0f-ac51-4a81-b3d8-880a8a74f58f) | 3 · 4,041 | `attempt-1` | 7 · 11,427 | `length` | `still_length_bounded_at_6144` |

The gold answer is `236`; the reported answers above are extractions from
truncated partial responses and must not be treated as stable correctness
judgments. Ranks 117–119 produced byte-identical 11,427-character response
texts (SHA-256 `695e0b6b7c68b33c51a944581b7217c9556a0ac20652042516bfd901b58d2fae`),
while rank 116 followed a different but still unbounded trajectory. The narrow
diagnostic question now has a clear answer: tripling the ceiling did **not**
convert any of the four responses to `finish_reason = stop`.

The extracted answers also move with the censoring boundary: rank 116 changes
from `9` to `1`, and ranks 117–119 change from `3` to `7`. That instability is
another reason not to score length-bounded extractions. Known-failing control
203 stopped on the same item at 2,048 tokens, but no rejected control was run
under the isolated 6,144-token contract. The extended cohort is therefore
one-class-only: it establishes persistence for these four accepted snapshots,
not a difference between accepted and rejected submissions.

This is useful failure-mode evidence, not a new quality gate. The primary
quick-profile terminal markers remain unchanged; there is still no formal
baseline-prefix comparison or local retention decision for ranks 116–119, and
no claim about their private M5 behavior. Four earlier infrastructure failures
remain recursively checksummed and explicitly unselected.

### Extended-diagnostic artifact anchors

| Rank | `completed.json` SHA-256 | Selected result SHA-256 |
|---:|---|---|
| 116 | `11e948500cb63c49be98c779417d7ffb45cc4dcfb9686f8aed406f6851839c87` | `a1bd20e9673eaa4fc5638a8b68255c691cfaf7721ea74763428a8fdf2f7beac0` |
| 117 | `c17d1969d8439790613f197d2eb81d01f418e991baf26bc5e44abbe231fa8d26` | `c84b58769f52cfff5dd157d60ca7cbde92cdc0a75af082cd74443ea46d5ca8b0` |
| 118 | `ed013c17504016df50346918656d1c0c5a8c6fc09e92edab518bd970b0d1ee14` | `31656be8670241f06136256c40436000123aff69991a139acbc902a02a980f5b` |
| 119 | `17f074e99db090e591132132581560a8428c3089e228e1ce66fce1ce27006034` | `565f72d363888de6a813af6e3b4943eb4c2fc9839713362337b0d283c3604e75` |

## What is active at rank 126

Rank 126 is the campaign starting point. Historical mechanisms should not be
blindly replayed on top of it.

| Status | Mechanism | Provenance | Rank-126 meaning |
|---|---|---|---|
| Active | All 40 attention QKV/O banks use checkpoint NVFP4 | 116 → 117 → 120 | Dominant byte reduction; affine INT8 is fallback/control |
| Active | Producer-computed exact router ordinals | 119, restored 121 | Avoids repeated nonlinear key reconstruction across routed consumers |
| Active | Exact fused split-K prefill | 123 | Removes intermediate/reduction dispatches with old BF16/FP32 boundaries replayed |
| Active | Separate RMSNorm, NVFP4 QKV, affine gate | 124 | Fused norm/QKV/gate is compiled but default-off |
| Active | Aligned `uchar4` affine-code loads | 125 | Wider load, same sequential multiply-add order |
| Active | Layer-0 projection-ready `asyncEval` | 125 | Enqueues already-built GPU work during remaining Swift graph construction |
| Active | R1 fused routed/shared down + residual | 126 | Positive M5 geometry; architecture-sensitive |
| Superseded | Shared fused-attention parameter carriers | 112 | Removed by metadata-only rank-113 branch |
| Effectively superseded | Indexed affine QKV/O metadata | 112–113 | Code remains, but default QKV/O banks are NVFP4 |
| Superseded | Consumer-local top-8 variants | 114, 118 | Replaced by producer ordinals/current packed consumer |
| Superseded | SG4 affine-QKV geometry | 115, 118 | Displaced by alternatives and then all-layer NVFP4 |
| Subsumed | NVFP4 boundaries 24 and 17 | 116–117 | Rollout evidence; final boundary is zero |
| Default-off | Fused-tail sign/scale fold | 122 | Lives in fused norm/QKV/gate path disabled at rank 124 |
| Default-off | All-layer fused norm/QKV/gate schedule | 120, reversed 124 | Format eligibility remains; separate schedule is faster at current multiplicity |

### Rank-126 day-one code map

This map is pinned to [`7702fab8a41fe2f4ff2ae281beeb1548b31e3406`](https://github.com/Layr-Labs/mlxfast-challenge/tree/7702fab8a41fe2f4ff2ae281beeb1548b31e3406),
not to whatever `main` contains later. Every path below is covered by
`benchmark.json` `editablePaths`; directory entries such as
`Sources/MLXFastModel` cover the files named beneath them. `Twin` means the
source copies that must move together for the edit to reach the ranked worker.
For confidence, **H** means narrow or independently bracketed official
evidence, **M** means a bundle or noisy marginal receipt, and **L** means an
untested hypothesis. Portability risk refers mainly to changing Apple GPU
generation, not to correctness risk. In the twin column, `kernels/X` expands
to `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/X`, and
`mlx-generated/X` expands to
`Vendor/mlx-swift/Source/Cmlx/mlx-generated/X`.

| State and mechanism | Exact rank-126 source and symbols | Phase and selected path | Twin obligation | Causal confidence / portability | Next falsifier |
|---|---|---|---|---|---|
| Active — all 40 attention QKV/O banks use NVFP4 | [`Sources/MLXFastModel/LagunaRuntimeModel.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Sources/MLXFastModel/LagunaRuntimeModel.swift#L2939-L3009): `lagunaNativeAffineNVFP4From`, `lagunaNativeAffineWeight`; same file at `prepareNativeAffineQKVWeight`, `prepareNativeAffineOProjWeight`, and `prepareFusedRuntimeWeights` | Decode selected path; default `DARKBLOOM_NATIVE_AFFINE_NVFP4_FROM=0`. The banks are prepared for every layer, but the native QKV/O call-site guards require `B=L=1`; prefill retains its BF16/fused projection path. | Swift selection has no twin. Any downstream NVFP4 kernel edit must keep `kernels/fp_quantized{,_nax}.h` synchronized with `mlx-generated/fp_quantized{,_nax}.cpp`; the `_nax` pair matters on M5. | **H** byte win; **M** portability/numerical-boundary risk. | Do not reopen the exhausted 32 → 24 → 17 → 0 ladder without a changed kernel or arithmetic contract. If reopened, test each boundary independently under exact-token M5 gates; the pass/fail surface was nonmonotonic. |
| Active — producer-computed router ordinals | [`LagunaRuntimeModel.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Sources/MLXFastModel/LagunaRuntimeModel.swift#L898-L1141): `lagunaResidualRMSNormRouterSource`, `lagunaResidualRMSNormRouter`; consumer at `lagunaRoutedSwiGLUQMVPackedTop8` and `LagunaRuntimeSparseMoEBlock.forward` | Decode only. `DARKBLOOM_ROUTER_PRECOMPUTED_KEYS` defaults on; one 256-key producer feeds the packed routed consumer. | Metal is embedded in this Swift file through `MLXFast.metalKernel`; no AOT/JIT twin. | **M–H** mechanism, **L–M** portability risk. The restored official marginal was small but the fan-out reduction is explicit. | Repeated cool decode bracket with `DARKBLOOM_ROUTER_PRECOMPUTED_KEYS=0`; require unchanged prefill, exact top-8/tie order, and a trace proving the producer-key consumer actually fired. |
| Active — exact fused split-K | [`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp#L812-L894): `qmm_splitk`, reached from `QuantizedMatmul::eval_gpu`; kernel [`fp_quantized.h`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized.h#L1805-L1922): `fp_qmm_t_splitk_fused` | Prefill only on the scored path: transposed, unbatched, non-affine QMM with eligible 32-aligned matrix shapes. Decode's `M=1` routes to QMV, so its movement in the receipt is not causal evidence for this kernel. | Required pair: `kernels/fp_quantized.h` + runtime-effective `mlx-generated/fp_quantized.cpp`. This rank-126 kernel has no separate `_nax` body; audit both variants before broadening shared code. | **H** exact fusion, **M** portability risk. | Same-binary 512-token prefill bracket with `DARKBLOOM_QMM_SPLITK_FUSED=0`; log the qualifying shapes/kernel name and replay the old BF16 partition stores plus FP32 reduction order exactly. |
| Active — separate RMSNorm, NVFP4 QKV, affine gate | [`LagunaRuntimeModel.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Sources/MLXFastModel/LagunaRuntimeModel.swift#L5518-L5675): `LagunaRuntimeAttention.callAsFunction`; control source at `lagunaTailNormQKVGate` | Decode. Default branch is `inputNorm(input)` then NVFP4 `quantizedMM` QKV and affine `quantizedMM` gate. | The schedule edit is Swift-only. Its generic QMV consumers use the `fp_quantized` and `quantized` AOT-header/generated-JIT pairs if their kernels are changed. | **H** negative evidence for the fused schedule; **M** portability risk. Rank 124 had strong same-binary brackets and a clear repeated-producer cause. | Re-enable only with a design that computes RMS once, then bracket `DARKBLOOM_TAIL_NORM_QKV_GATE=1` against default while counting RMS reductions and barriers. |
| Active — aligned `uchar4` affine-code loads | [`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/quantized.h`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/quantized.h#L192-L292): `qdot<..., bits == 8>` | Decode-dominant affine QMV work, notably the attention gate; one aligned four-byte load retains four sequential multiply-adds. | Required pair: `kernels/quantized.h` + runtime-effective `mlx-generated/quantized.cpp`. Rank 125 did not change the `_nax` pair. | **M–H** bundled but independently positive on M5; **M** portability/alignment risk. | Add a distinct scalar-load control PSO without changing the four-FMA order; compare repeated M5 decode and inspect generated loads. There is no shipped environment selector that isolates this change. |
| Active — layer-0 projection-ready `asyncEval` | [`LagunaRuntimeModel.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Sources/MLXFastModel/LagunaRuntimeModel.swift#L748-L785): `lagunaAttentionProjectionAsyncEnabled`; call site in `LagunaRuntimeAttention.callAsFunction` after `qkv` and `gateLogits` construction | Decode only; layer 0, `B=L=1`. It enqueues an already-built graph and does not add model work. | Swift scheduling only; no kernel twin. | **M–H** bundled but independently positive on M5; **M–H** scheduler/driver portability risk. | Bracket `DARKBLOOM_ATTN_PROJECTION_ASYNC=0` with command-buffer/timeline evidence; confirm the layer-0 projection starts earlier and prefill is stationary. |
| Active — R1 fused routed/shared down + residual | [`LagunaRuntimeModel.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Sources/MLXFastModel/LagunaRuntimeModel.swift#L7844-L8021): `lagunaRoutedSharedDownResidualKernel`, `lagunaRoutedSharedDownResidual`; dispatch in `LagunaRuntimeSparseMoEBlock.forward` | Decode only. `outputs_per_simd=1`, 4× the rank-125 grid, nine expert slots, exact BF16 reduction/residual boundaries. | Metal is embedded in Swift; no AOT/JIT twin. | **H on M5**, **H portability risk**: roughly +0.4% M5 but about 12% slower on another Apple GPU. | Preserve a distinct rank-125 `outputs_per_simd=4` PSO in the same binary and bracket on M5. Turning the whole fusion off is not a causal geometry control. |
| Default-off — fused-tail sign/scale fold | [`LagunaRuntimeModel.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Sources/MLXFastModel/LagunaRuntimeModel.swift#L4282-L4311): `lagunaTailNVFP4ScaleFoldEnabled`, `lagunaTailNVFP4ScaleDecode`, `lagunaTailNVFP4QDotReturn` inside `lagunaTailNormQKVGateSource` | Decode, but unreachable on defaults because the owning fused norm/QKV/gate schedule is off. | Embedded Metal in Swift; no twin. | **H** arithmetic equivalence, **L** timing causality; **L–M** portability risk. | First force the owning fused path reachable, verify its trace, then toggle `DARKBLOOM_TAIL_NVFP4_SCALE_FOLD=0/1`. Measuring the fold while the owner remains off is a null experiment. |
| Default-off — all-layer fused norm/QKV/gate schedule | [`LagunaRuntimeModel.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Sources/MLXFastModel/LagunaRuntimeModel.swift#L4419-L4665): `lagunaTailNormQKVGateSource`, `lagunaTailNormQKVGateKernels`, `lagunaTailNormQKVGateEnabled`, `lagunaTailNormQKVGate` | Decode. Compiled kernel is selected only with `DARKBLOOM_TAIL_NORM_QKV_GATE=1`; default is the faster separate schedule. | Embedded Metal in Swift; no twin. | **H** evidence to leave it off; **M–H** occupancy/multiplicity portability risk. | Treat the current fused kernel as a negative control. A successor must amortize the 2,048-element norm producer once; measure producer count, barriers, and candidate decode before promotion. |

The twin rule is asymmetric by design: the vendored MLX package executes the
generated C++ source strings for JIT families, while `MLXFast.metalKernel`
source embedded in Swift has only one authored copy. AOT-only SDPA/RoPE/RMS
edits instead require rebuilding `mlx.metallib`.

### First campaign targets, wired to code

These are search entry points, not claims that the named edit will win. The
first experiment in each row is meant to falsify reachability or the proposed
bottleneck before a large implementation is attempted.

| Priority / avenue | Exact editable entry points | Phase and twin rule | Confidence / portability | First falsifier |
|---|---|---|---|---|
| P1 — MoE gather-GEMM and routed/shared traffic | Decode: [`LagunaRuntimeModel.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Sources/MLXFastModel/LagunaRuntimeModel.swift#L9949-L10315), `LagunaRuntimeSparseMoEBlock.forward`, `lagunaRoutedSwiGLUQMVPackedTop8`, `lagunaRoutedSharedDownResidual`. Prefill fallback: [`SwitchLayers.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Vendor/mlx-swift-lm/Libraries/MLXLMCommon/SwitchLayers.swift#L360-L407), `QuantizedSwitchLinear.callAsFunction`; [`quantized.cpp`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp#L612-L1024), `gather_qmm(_nax)`, plus `gather_qmm_rhs(_nax)` later in the same file | Both; decode has Swift-embedded kernels, prefill uses `fp_gather_qmv*` / `fp_gather_qmm_{t,n,rhs}`. For the latter, update `fp_quantized{,_nax}.h` and both matching generated `.cpp` strings; M5 selects `_nax` where eligible. | **H** hotspot, **L** for any new marginal; **H** geometry portability risk. | Trace exact frozen-window kernel names, shapes, bytes, and barriers first. Then change one of layout, qdot reuse, router weighting, or down epilogue ownership in a same-binary PSO; preserve expert order and every BF16 boundary. |
| P1 — KV-cache handling | [`LagunaRuntimeModel.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Sources/MLXFastModel/LagunaRuntimeModel.swift#L5789-L5851): fused-attention cache branches; `LagunaRuntimeModel.newCache`. [`KVCache.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Vendor/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift#L327-L735): `KVCacheSimple.update`, `fusedAppendPrepare/Advance`, `RotatingKVCache.update`, `updateInPlace`, `fusedRingPrepare/Advance`. [`AttentionUtils.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Vendor/mlx-swift-lm/Libraries/MLXLMCommon/AttentionUtils.swift#L59-L109): `attentionWithCacheUpdate` | Decode-primary plus prefill-to-decode transition; Swift logic and embedded fused kernels have no twin. | **M** bottleneck hypothesis; **M** portability, **H** logical-position correctness risk. | The steady 512-row sliding ring is already fused. Trace the frozen 512+128 window to isolate remaining growth, contiguization, temporal-order, or full-cache append work; test offsets 511/512/wrap and exact logical/physical advance before optimizing. |
| P1/P2 — attention scheduling and full-attention kernels | [`LagunaRuntimeModel.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Sources/MLXFastModel/LagunaRuntimeModel.swift#L1244-L2360): `lagunaFullQKNormYaRN`, `lagunaSlidingQKNormRoPE`, `lagunaSlidingFusedAttention`, `lagunaFullFusedAttention`; dispatch in `LagunaRuntimeAttention.callAsFunction`. Generic boundary: [`AttentionUtils.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Vendor/mlx-swift-lm/Libraries/MLXLMCommon/AttentionUtils.swift#L59-L109) `attentionWithCacheUpdate` and [`RoPEApplication.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Vendor/mlx-swift-lm/Libraries/MLXLMCommon/RoPEApplication.swift#L43-L75) `applyRotaryPosition` | Both. Decode custom kernels are Swift-embedded. AOT `scaled_dot_product_attention.metal` + `sdpa_vector.h` has no generated twin and requires a metallib rebuild. Steel prefill edits must synchronize `kernels/steel/attn/` with `mlx-generated/steel_attention{,_nax}.cpp`; include `_nax` on M5. | **M** hotspot, **L** new marginal; **H** architecture and numerical-reassociation risk. | Capture per-layer dispatch for sliding versus full at the frozen lengths before editing. Attribute duplicated GQA broadcast, YaRN partial-RoPE, mask, or reduction work to a concrete kernel; bracket one producer/ownership change with exact cache offsets and tokens. |
| P1 — value-graph fan-out | [`LagunaRuntimeModel.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Sources/MLXFastModel/LagunaRuntimeModel.swift#L898-L1141): proven producer pattern; search consumers in `LagunaRuntimeAttention.callAsFunction`, `LagunaRuntimeSparseMoEBlock.forward`, and `LagunaRuntimeDecoderLayer.callAsFunction` | Decode-primary, possibly both. Swift graph edits and embedded Metal have no twin. | **M** pattern transfer, **L** for each candidate; **L–M** portability unless it changes occupancy. | Use graph/dispatch tracing to count identical small producers and consumer threadgroups. Hoist only a bit-exact, input-current value with at least three real consumers; the control must restore rank-126 dependency edges in the same binary. |
| P1 — MLX scheduling and graph construction | [`LagunaRuntimeModel.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Sources/MLXFastModel/LagunaRuntimeModel.swift#L684-L785): `lagunaDecodeAsyncStage`, `lagunaAttentionProjectionAsyncEnabled`, `lagunaPrefillAsyncLadderStride`; execution in `LagunaRuntimeModelInner.callAsFunction` and `LagunaRuntimeModel.callAsFunction` | Both; Swift scheduling only, no kernel twin. | **M** transferred evidence; **H** scheduler/driver portability risk. | Change one enqueue rung at a time using `DARKBLOOM_DECODE_ASYNC_STAGE`, `DARKBLOOM_ATTN_PROJECTION_ASYNC`, or `DARKBLOOM_PREFILL_ASYNC_LADDER`; collect command-buffer overlap, synchronization, peak memory, and both scored phases. |
| P2 — deepen exact split-K prefill | Same `qmm_splitk` / `fp_qmm_t_splitk_fused` path mapped above | Prefill. Required `fp_quantized.h` + `mlx-generated/fp_quantized.cpp` pair; audit `_nax` before moving shared helpers. | **M** remaining headroom; **M** portability and **H** rounding-contract risk. | Profile only the frozen `M=512` qualifying shapes. Name the remaining intermediate or barrier, then replay partition-store BF16 rounding and FP32 order in a direct control before claiming removal. |
| P2 — offline transform metadata | [`Sources/MLXFastTransform/Transform.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Sources/MLXFastTransform/Transform.swift#L98-L305): `SwiftTransform.run`; [`LagunaCheckpointValidation.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Sources/MLXFastTransform/LagunaCheckpointValidation.swift#L41-L230) `LagunaCheckpointValidation.validateSelectedTensors` | Untimed producer with possible prefill/decode consumer benefit; Swift only. Rank 126's `.laguna` branch deliberately emits no projection/tied-head sidecar. | **L** performance hypothesis; **L** hardware portability but **H** artifact-policy risk. | First prove the proposed metadata is allowed by the Laguna transform/validation contract and is consumed on the scored path. Reject any idea that only speeds untimed loading or creates an unused sidecar. |
| P2 — weight views and input-independent preparation | [`LagunaRuntimeModel.swift`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/Sources/MLXFastModel/LagunaRuntimeModel.swift#L11118-L11183): `newCache`, `prepareFusedRuntimeWeights`; producers such as `prepareNativeAffineQKVWeight`, `prepareNativeAffineOProjWeight`, `preparePackedRoutedGateUpBank`, and `prepareRoPEAngleAtlases` | Both, only if preparation removes a scored-path materialization. Swift layout work has no twin; changing a consuming kernel reintroduces that family's twin obligation. | **M** reachability, **L** new marginal; **M** memory/architecture risk. | Trace per-token `contiguous`, gather, reshape-copy, and lazy materialization work after warmup. Promote only a load-time view/layout whose consumer proves one of those scored operations disappeared; report resident-memory cost. |

The fastest first week is therefore diagnostic rather than imitative: trace
rank 126, preserve direct controls, and attack the remaining producer or byte
movement actually observed. The map prevents redoing landed work without
turning the historical winners into a mandatory search vocabulary.

## Per-submission dossiers

### Rank 112 — [indexed metadata plus shared carriers](https://mlx.fast/api/submissions/aa6660cb-a3e4-410a-a365-bb117e3e98f1)

- Source: [`df0af746`](https://github.com/Layr-Labs/mlxfast-challenge/commit/df0af746de208e267ae16e7dc62f901aa5cff77a), [PR 971](https://github.com/Layr-Labs/mlxfast-challenge/pull/971); conceptual base rank 111.
- Official: score `2.11750832958454`; candidate decode `6.3409827421875`
  ms/token; candidate prefill `0.196908529296875` ms/token.
- Change: exact UInt16 affine-metadata indexing plus shared immutable attention
  parameter arrays.
- Evidence reading: successful two-mechanism snapshot; metadata had stronger
  isolation than carrier sharing.
- Rank-126 status: carriers superseded; metadata code largely off the default
  attention hot path after all-layer NVFP4.
- M4 quality: formal `23/53`, PPL `14.613698880455747`, ranked `0/9`, public
  token pass; local gate failed.
- Campaign use: reuse the exact bit-cast/table technique for metadata still on
  hot paths, not for default QKV/O banks that no longer use affine metadata.

### Rank 113 — [metadata-only re-land](https://mlx.fast/api/submissions/96bfd3b7-49c2-4f0b-b0bd-288173ac284b)

- Source: [`274a909a`](https://github.com/Layr-Labs/mlxfast-challenge/commit/274a909ae2f8b65414ec7b1bbb5981c5cf091cde), [PR 973](https://github.com/Layr-Labs/mlxfast-challenge/pull/973); conceptual base rank 111, not rank 112.
- Official: score `2.11953731302476`; decode `6.3250559921875` ms/token;
  prefill `0.19706990625` ms/token.
- Change: metadata indexing alone with fail-closed raw fallback beyond 65,536
  distinct pairs.
- Evidence reading: the cleanest official isolation for the metadata idea.
- Rank-126 status: effectively superseded for default attention QKV/O.
- M4 quality: identical to ranks 112, 114, 115; formal local gate failed.
- Campaign use: preserve as a pattern for exact metadata compression and
  fallback design.

### Rank 114 — [top-8 inside routed QMV](https://mlx.fast/api/submissions/3223e19d-8e7a-4001-a2c8-0176900a7005)

- Source: [`149892c3`](https://github.com/Layr-Labs/mlxfast-challenge/commit/149892c38865cdb78af6c1b1158fecc853446ed4), [PR 983](https://github.com/Layr-Labs/mlxfast-challenge/pull/983); base rank 113.
- Official: score `2.12281334772927`; decode `6.32126790625` ms/token;
  prefill `0.1967543125` ms/token.
- Change: reproduce strict total-order top-8 in routed QMV so that QMV and the
  standalone selector can overlap.
- Evidence reading: a clear dependency-window reduction, but a small
  single-run movement.
- Rank-126 status: early consumer-local variant superseded.
- M4 quality: formal `23/53`, PPL `14.613698880455747`, ranked `0/9`; failed.
- Campaign use: inspect other serialized windows where exact work can move
  into an existing producer or consumer without changing later dependencies.

### Rank 115 — [SG4/PF2 affine QKV](https://mlx.fast/api/submissions/dd341a52-a695-4d0d-8bdf-75ef44a9c74a)

- Source: [`d4cb1ae8`](https://github.com/Layr-Labs/mlxfast-challenge/commit/d4cb1ae8d63cd3e59169bc7685d85ca7970241e6), [PR 985](https://github.com/Layr-Labs/mlxfast-challenge/pull/985); base rank 113, not rank 114.
- Official: score `2.12365737170721`; decode `6.28067903125` ms/token;
  prefill `0.19681005859375` ms/token.
- Change: four SIMD groups share exact RMSNorm work over 16 projection rows;
  prefetch depth two controls live state.
- Evidence reading: geometry and prefetch form one tuned unit; SG4/PF4 was
  locally negative.
- Rank-126 status: displaced by all-layer NVFP4.
- M4 quality: same formal failure signature as ranks 112–114.
- Campaign use: tune geometry and prefetch/register pressure jointly, using
  compile-time variants rather than runtime knobs.

### Rank 116 — [NVFP4 layers 24–39](https://mlx.fast/api/submissions/8449082c-4dc2-4526-b3bd-69712c3b8a8e)

- Source: [`5b46c79c`](https://github.com/Layr-Labs/mlxfast-challenge/commit/5b46c79cfd8d6496989ba5977950e969ba4107ac), [PR 986](https://github.com/Layr-Labs/mlxfast-challenge/pull/986); base rank 113.
- Official: score `2.1640759452478`; decode `6.0902330703125` ms/token;
  prefill `0.197249185546875` ms/token.
- Change: halve QKV/O bytes for eight more layers using checkpoint NVFP4.
- Evidence reading: strong representation and bandwidth evidence.
- Rank-126 status: subsumed by all-layer NVFP4.
- M4 quality: terminal AIME; raw `23/53`, PPL `14.77829665389895`; no formal
  gate. The primary response hit 2,048 tokens with answer 9; the isolated
  6,144-token rerun also hit `length` (answer 1; 14,432 characters).
- Campaign use: treat the byte comparison as proven; do not rerun the old
  boundary ladder absent a changed numerical/kernel surface.

### Rank 117 — [NVFP4 layers 17–39](https://mlx.fast/api/submissions/df2a7483-9c5b-4f4c-8a2f-9fee780515d7)

- Source: [`500d92a0`](https://github.com/Layr-Labs/mlxfast-challenge/commit/500d92a0f486a0297f312d8f4d38d5ab3b58f900), [PR 995](https://github.com/Layr-Labs/mlxfast-challenge/pull/995); base rank 116.
- Official: score `2.23332009444833`; decode `5.85775065625` ms/token;
  prefill `0.196566080078125` ms/token.
- Change: one boundary default, layer 24 → exact-tested layer 17.
- Evidence reading: exceptionally narrow delta; strongest lesson is the
  nonmonotonic pass/fail boundary sweep.
- Rank-126 status: subsumed by boundary zero.
- M4 quality: terminal AIME; raw `22/53`, PPL `14.963476718728943`; no formal
  gate. The isolated 6,144-token rerun remained length-bounded (answer 7;
  11,427 characters).
- Campaign use: test numerical boundaries independently instead of stopping
  after the first exact-token failure.

### Rank 118 — [exact scheduling recomposition](https://mlx.fast/api/submissions/214fd89a-69af-4858-af54-8a801672c78d)

- Source: [`fc306048`](https://github.com/Layr-Labs/mlxfast-challenge/commit/fc306048e61c2cb7e56a8ff406db40adafcc8e79), [PR 999](https://github.com/Layr-Labs/mlxfast-challenge/pull/999); base rank 117.
- Official: score `2.2414044139947`; decode `5.8330843046875` ms/token;
  prefill `0.197362142578125` ms/token.
- Change: compose exact top-8, unpacked one-row routed QMV, and SG4/PF2.
- Evidence reading: a three-mechanism bundle, not an isolated marginal result.
- Rank-126 status: superseded by current producer ordinals and packed routed
  consumer; affine-QKV geometry displaced.
- M4 quality: same terminal raw signature as ranks 117 and 119; no gate. Its
  isolated 6,144-token response was byte-identical to theirs and remained
  length-bounded (answer 7; 11,427 characters).
- Campaign use: composition can recover several exact ideas, but demand
  component receipts before attributing the bundle.

### Rank 119 — [producer-computed router keys](https://mlx.fast/api/submissions/5139da0f-ac51-4a81-b3d8-880a8a74f58f)

- Source: [`c5206993`](https://github.com/Layr-Labs/mlxfast-challenge/commit/c5206993d510ca0c50861b1f5d3d26030d76a22b), [PR 1002](https://github.com/Layr-Labs/mlxfast-challenge/pull/1002); base rank 117, not 118.
- Official: score `2.26148968661582`; decode `5.841873375` ms/token;
  prefill `0.197732177734375` ms/token.
- Change: compute corrected ordinals once beside router logits rather than
  rebuilding nonlinear keys across 1,024 routed-QMV threadgroups.
- Evidence reading: strong value-graph fan-out hypothesis; cross-row paired
  prefill movement is not causal evidence for a decode-only change.
- Rank-126 status: erased by 120, restored by 121, active now.
- M4 quality: terminal `22/53`, PPL `14.963476718728943`; no formal gate. Its
  isolated 6,144-token rerun remained length-bounded (answer 7; 11,427
  characters), byte-identical to ranks 117 and 118.
- Campaign use: continue looking for small exact values multiplied by large
  consumer fan-out.

### Rank 120 — [all-layer NVFP4](https://mlx.fast/api/submissions/db173215-a7d7-4863-a333-8132c33be279)

- Source: [`7b2c9407`](https://github.com/Layr-Labs/mlxfast-challenge/commit/7b2c9407032e41408fbfaba94625d9c53b1934ca), [PR 1003](https://github.com/Layr-Labs/mlxfast-challenge/pull/1003); base rank 117, not 119.
- Official: score `2.36996072007723`; decode `5.4161556015625` ms/token;
  prefill `0.1969033203125` ms/token.
- Change: boundary 17 → 0 and format-aware fusion eligibility.
- Evidence reading: largest result in the window and endpoint of the legal
  representation-byte ladder. It also removed rank-119 router keys.
- Rank-126 status: all-layer NVFP4 active; its fused norm/QKV/gate schedule
  reversed at rank 124.
- M4 quality: formal `22/53`, PPL `14.903492398049115`, ranked `0/9`; failed.
- Campaign use: start here for representation; search beyond boundary widening.

### Rank 121 — [restore router keys](https://mlx.fast/api/submissions/9847ff8f-918e-4988-ba2f-a1137d23784b)

- Source: [`e6596576`](https://github.com/Layr-Labs/mlxfast-challenge/commit/e65965761f34afbabc696b3eccdd363863edd480), [PR 1014](https://github.com/Layr-Labs/mlxfast-challenge/pull/1014); base rank 120.
- Official: score `2.37074944628857`; decode `5.3976897734375` ms/token;
  prefill `0.1969623203125` ms/token.
- Change: restore the producer/consumer router dependency on all-layer NVFP4.
- Evidence reading: small official delta, large process lesson—overlay state is
  replaceable, not automatically cumulative.
- Rank-126 status: active.
- M4 quality: identical formal failure signature to ranks 120 and 122.
- Campaign use: diff every promotion against the active-path manifest and
  explicitly restore orthogonal wins.

### Rank 122 — [exact NVFP4 scale/sign fold](https://mlx.fast/api/submissions/cc79cef2-8a0e-4bbd-aaba-bdaaae453249)

- Source: [`71b80b1f`](https://github.com/Layr-Labs/mlxfast-challenge/commit/71b80b1f33b01eb3edc871df85675cdbd6fe6320), [PR 1017](https://github.com/Layr-Labs/mlxfast-challenge/pull/1017); base rank 121.
- Official: score `2.38717668655054`; decode `5.424066078125` ms/token;
  prefill `0.196989095703125` ms/token.
- Change: carry E4M3 sign directly and fold exact powers of two into `2^22`;
  all 256 scale bytes were checked.
- Evidence reading: strong correctness proof, weak causal timing because both
  raw candidate phases were slower than rank 121.
- Rank-126 status: default-off with the fused input-projection path.
- M4 quality: same `22/53`, PPL `14.903492398049115`, ranked `0/9` failure.
- Campaign use: retain the proof technique; do not optimize a default-off path
  without first changing reachability.

### Rank 123 — [exact fused split-K prefill](https://mlx.fast/api/submissions/70a3ad4b-70da-4b17-ab4f-388945dfee29)

- Source: [`60f436a2`](https://github.com/Layr-Labs/mlxfast-challenge/commit/60f436a2361eef72b207c2a3cf0d5b6984b8b0d1), [PR 1024](https://github.com/Layr-Labs/mlxfast-challenge/pull/1024); base rank 122.
- Official: score `2.39434519974008`; decode `5.3932425078125` ms/token;
  prefill `0.196256265625` ms/token.
- Change: replay each split-K partition's loader/MMA schedule, BF16
  intermediate rounding, FP32 reduction order, and final tile store in one
  dispatch. Dormant LM-head arms were removed for source budget.
- Evidence reading: narrow active fusion with favorable raw movement in both
  phases; runtime-parametric QMV geometry was a recorded negative.
- Rank-126 status: active.
- M4 quality: formal `22/53`, PPL `14.970700228511769`, ranked `0/9`; failed.
- Campaign use: fuse only when the old boundaries can be replayed exactly;
  prefer compile-time PSOs to runtime hot-kernel branches.

### Rank 124 — [un-fuse attention input projection](https://mlx.fast/api/submissions/a0da915f-450a-4063-bf8e-ec1661f4a661)

- Source: [`70fe340b`](https://github.com/Layr-Labs/mlxfast-challenge/commit/70fe340becd16cf5efa40884963283e6a834c84b), [PR 1027](https://github.com/Layr-Labs/mlxfast-challenge/pull/1027); base rank 123.
- Official: score `2.45073250313311`; decode `5.2904329375` ms/token;
  prefill `0.19554093359375` ms/token.
- Change: compute RMSNorm once, then use separate NVFP4 QKV and affine gate
  consumers instead of repeating RMS reduction per output tile.
- Evidence reading: one of the strongest late causal wins, supported by path
  reachability and same-binary brackets.
- Rank-126 status: active default; fused path retained as control.
- M4 quality: same formal failure signature as ranks 123, 125, and 126.
- Campaign use: audit producer multiplicity before designing more fusion.

### Rank 125 — [aligned loads plus layer-0 enqueue](https://mlx.fast/api/submissions/4173c401-0f25-41fd-bec7-cdea22a1aac3)

- Source: [`13496639`](https://github.com/Layr-Labs/mlxfast-challenge/commit/1349663988dacafe7ee4b5b11832a4891d1aa5cc), [PR 1051](https://github.com/Layr-Labs/mlxfast-challenge/pull/1051); base rank 124.
- Official: score `2.45196981458518`; decode `5.2711627578125` ms/token;
  prefill `0.195565998046875` ms/token.
- Change: one aligned `uchar4` load for four affine bytes while retaining four
  sequential FMAs; `asyncEval` after layer-0 projection construction.
- Evidence reading: two-piece bundle, but each piece had an independent
  positive M5 candidate-phase receipt. Dense-256 geometry was excluded after
  a negative official result.
- Rank-126 status: both active.
- M4 quality: formal `22/53`, PPL `14.970700228511769`, ranked `0/9`; failed.
- Campaign use: pursue load-width and graph-overlap micro-optimizations only
  with isolated receipts.

### Rank 126 — [one row per SIMD in fused down](https://mlx.fast/api/submissions/05e7894f-0eaf-4f6d-8622-499d1e44185d)

- Source: [`7702fab8`](https://github.com/Layr-Labs/mlxfast-challenge/commit/7702fab8a41fe2f4ff2ae281beeb1548b31e3406), [PR 1056](https://github.com/Layr-Labs/mlxfast-challenge/pull/1056); base rank 125.
- Official: score `2.4549506212825`; decode `5.249092125` ms/token; prefill
  `0.195664794921875` ms/token.
- Change: one output row per SIMD, four times the grid, fewer live
  accumulators, same row/weight/scale/reduction/residual mapping.
- Evidence reading: isolated positive M5 receipt plus a roughly 12% negative
  result on another Apple GPU.
- Rank-126 status: active campaign frontier.
- M4 quality: formal `22/53`, PPL `14.970700228511769`, ranked `0/9`, public
  pass; local gate failed.
- Campaign use: preserve as the M5 frontier, but bracket any further ownership
  geometry on M5 and keep a same-binary rank-125 control.

## Bootstrap priorities for our campaign

### Priority 0 — establish the real frontier before changing it

1. Start from rank 126 commit `7702fab8a41fe2f4ff2ae281beeb1548b31e3406`.
2. Record a fresh same-machine baseline after syncing to current main.
3. Add a rank-111 quality arm to locate inherited M4 drift, then preserve a
   same-host rank-126 quality baseline for incremental autoresearch; keep the
   July 30 untouched quality baseline as the cumulative reference.
4. Maintain an active-path manifest: default selectors, qualifying shapes,
   weight formats, kernel names, and source/JIT twin reachability.
5. Keep rank-125/rank-126 geometry as a same-binary M5 control where possible.
6. Do not use the current M4 quality gate as an automatic veto; retain its
   component diagnostics and rely on official M5 correctness for ranking. The
   completed controls do not establish a replacement rule; do not retune the
   3% terms from this cohort.

### Priority 1 — high-value unexplored decode work

1. **MoE gather-GEMM and routed/shared expert traffic.** The attention byte
   ladder is exhausted, while eight routed experts plus one shared expert per
   sparse layer dominate decode work. Measure packed gather layout, qdot reuse,
   router weighting, down epilogues, and residual write ownership.
2. **KV-cache handling.** The sliding-window layers need only the last 512
   positions. Investigate tighter ring-buffer indexing, update/materialization
   work, and cache-aware attention dispatch without changing logical position.
3. **Attention scheduling beyond representation.** Audit GQA broadcast,
   partial-rotary YaRN on full-attention layers, mask/RoPE materialization, and
   duplicated small producers. Do not revisit the already-landed NVFP4 boundary
   without new evidence.
4. **Value-graph fan-out.** Search for exact metadata or transforms repeated
   across hundreds of consumer threadgroups, as rank 119 did for router keys.
5. **MLX scheduling and graph construction.** Extend the rank-125 overlap idea
   to already-constructed independent work, while measuring synchronization
   and pipeline-cache side effects.

### Priority 2 — prefill and transform opportunities

1. Profile the active fused split-K path at the frozen 512-token prefill shape;
   look for additional removable intermediates with explicit rounding replay.
2. Audit full-attention steel kernels at head dimension 128 and GQA grouping,
   including whether tile ownership duplicates RoPE, mask, or reduction work.
3. Use the offline transform to emit metadata that removes runtime shape,
   format, or indexing decisions without enlarging the artifact beyond policy.
4. Investigate weight-view construction and input-independent preparation only
   where it changes scored-path materialization—not untimed loading for its own
   sake.

### Priority 3 — architecture-specialized experiments

1. Create compile-time M5 `_nax` variants for ownership geometry rather than
   runtime-parametric branches that inflate register allocation.
2. Treat local M4 direction as a hypothesis filter, not an expected sign.
3. Require an official candidate-phase receipt before adopting sub-1% geometry
   changes, and preserve the old PSO as a direct control.

### Search budget

A practical initial allocation is:

- 50% to MoE/routed decode and epilogues;
- 20% to KV-cache/attention scheduling beyond representation;
- 15% to graph scheduling and synchronization;
- 10% to prefill and transform metadata; and
- 5% to deliberate high-variance ideas not suggested by the leaderboard.

This allocation is a campaign proposal, not a measured result. It prevents the
historical record from collapsing the search onto attention alone.

## Practices to carry forward

1. **One concept per causal submission.** Bundles may rank, but narrow diffs
   teach.
2. **Same-binary controls.** Selectors should restore the current frontier
   without changing compilation or pipeline-cache state.
3. **Reachability first.** Confirm the scored path, selected format, shape, and
   AOT/JIT twin before optimizing a kernel.
4. **Arithmetic-contract notes.** Record bit casts, tie order, signed zero,
   BF16 stores, partition order, and reduction topology beside the code.
5. **Compile-time specialization.** Avoid runtime knobs in hot kernels unless
   register/resource effects are explicitly measured.
6. **Paired interpretation.** Official paired ratios rank; raw candidate phases
   corroborate; cross-session deltas do not isolate causality.
7. **Small staged gains.** The acceptance band caps a single submission near
   5%; chunk larger improvements into independently diagnosable steps.
8. **Promotion diff audit.** After each accepted overlay, verify that every
   intended orthogonal mechanism remains active.
9. **Negative result ledger.** Preserve runtime-parametric geometry regressions,
   excluded dense-256 arms, and architecture sign reversals.
10. **Breadth reserve.** Keep capacity for hypotheses outside the leaders'
    attention/MoE kernel vocabulary.

## Ideas not to re-invent blindly

- Do not repeat the 32 → 24 → 17 → 0 NVFP4 attention boundary ladder. The
  endpoint is already active.
- Do not default-enable fused norm/QKV/gate without fixing its duplicated RMS
  producer. Rank 124 is strong contrary evidence.
- Do not reintroduce SG4 affine-QKV geometry on the default attention path;
  all-layer NVFP4 displaced it.
- Do not optimize the rank-122 fused-tail fold while its owning path is
  default-off.
- Do not remove the standalone router selector merely because routed QMV can
  reproduce top-8; other consumers still need it.
- Do not assume an M4 occupancy win or loss predicts M5.
- Do not infer causal prefill effects from a decode-only change across paired
  sessions.
- Do not memoize repeated whole prompts or compute unsupplied future tokens;
  those violate the serial single-pass track.

## Measurement and decision framework

For each proposed optimization, record:

| Field | Required content |
|---|---|
| Hypothesis | Bytes, instructions, barriers, producer repetitions, live state, or scheduling window expected to change |
| Scored path | Exact Swift dispatch and Metal AOT/JIT source pair reached |
| Shapes/formats | Prefill/decode dimensions, quantization group, layer classes, M5 variant |
| Arithmetic contract | Preserved order, rounding, ties, signed-zero, cache-position behavior |
| Control | Selector or PSO restoring rank-126 behavior in the same binary |
| Local evidence | Repeated cool brackets; component times; correctness signature; hardware label |
| Official evidence | Candidate and paired phase metrics, gates, thermal validity, source/submission link |
| Promotion audit | Active mechanisms retained, superseded, default-off, or restored |
| Decision | Adopt, reject, split, or investigate; confidence tier and next falsifier |

For sub-1% results, one scalar is not enough. Require repeated brackets where
the hardware is transferable, inspect absolute candidate phases alongside the
paired baseline, and prefer independent official receipts.

## Appendix A — provenance and integrity

### Frozen study inputs

| Input | SHA-256 |
|---|---|
| [candidates.json](candidates.json) | `785763d0a35cfbcb8b7643816990f60df98a80ff7976c5c1545ab7136f43285e` |
| [official-findings.md](official-findings.md) | `d8d21e346d044a1862a8f9b76ec1cbc24fba817870a05d9a7aa912f891ec442c` |
| [README.md](README.md) | `f11f947fa024221884b206a18c1d19e6917b2dcd6f219adcef5a126b80fa262c` |
| [negative-controls.json](negative-controls.json) | `b7a498ae1c8bb74c0287159e817e7dfa5f2a5c41aa29020c100be18b3089869f` |
| [control-run.json](control-run.json) | `3586c24e184c8b7f9f3dd25403654a2b2bc568b6046e7932f1f9b50b68ec0c14` |
| [run-quality-controls.sh](run-quality-controls.sh) | `c026afb9b2efb54569d4ad2822e40b8d2cde9945e7c5b833ab3f26b844d94ec0` |
| [quality-bridge-wrapper.sh](quality-bridge-wrapper.sh) | `42d3ec349c53ced281baa787906ac04b07e806c01dd703a4510693c73af6678e` |
| [run-extended-aime.py](run-extended-aime.py) | `338042981140aa08a6bcd1c8dcc527e924fc9988998099eb2649dea2646c180e` |
| [extended-aime-ids.json](extended-aime-ids.json) | `fcb81147afd2be45b3aaf809cab88517b1bc8ce9e01c77889e7f70529fee9a59` |
| [EXTENDED_AIME_DIAGNOSTICS.md](EXTENDED_AIME_DIAGNOSTICS.md) | `673288724fc75bafe1c15c69ec6af7fa92a4cd715379dbd5bc4fb3ae852bebd6` |
| [derive-rank126-quality.sh](derive-rank126-quality.sh) | `0a55adefd8a071c8fef40d13dc469ca75d7cc86af925796dd4aee97cee1031c9` |
| [quality-anchor-run.json](quality-anchor-run.json) | `6307b05475e4b27d578ede5197d241070867ad18eb49993b90decf54508339e3` |
| [run-quality-anchor.sh](run-quality-anchor.sh) | `c2bcb99ea78454594abc42533e80be02f5ca9c72b4fd75239bd1b39aaed0a755` |

### Campaign-executed performance tooling

| Input | SHA-256 |
|---|---|
| Campaign runner from local commit `5bb0682` | `78f97cd18f78885a55afe764563a027622f06daab88e424268be4bede3ef23bd` |
| [Legacy workspace `benchmark.sh` at `7702fab8`](https://github.com/Layr-Labs/mlxfast-challenge/blob/7702fab8a41fe2f4ff2ae281beeb1548b31e3406/benchmark.sh) | `7f9bd39ae5cdec18b9eda69da24db21ff29dab3c2b642c94151011e4c420d68e` |

The legacy workspace benchmark is the code that admitted the impossible
`1.5C` samples. The root checkout already contained later cooling work, but
each study arm's `reset --hard 7702fab8…` replaced it before execution.

### Current stopped-state audit and resume tooling

| Input | SHA-256 |
|---|---|
| [build-report-data.py](build-report-data.py) | `db88f9500547fc71bc3f0266d64df9cbdfbfb6eb0fe0ad5d1eca543321d14b8a` |
| [run-study.sh](run-study.sh) | `6f38585f324c8588d9eaa6eefabe0b36e5b498f0dc80e120f3492385ac2fbd84` |
| [Fail-closed `benchmark.sh`](../../../benchmark.sh) | `05d60dd7b8dec7490f32802f201496407fd4687c55f0bf3c28a2bc55fc1c3877` |
| [`tools/fan-control.sh`](../../../tools/fan-control.sh) | `d0281dd62612d5c3371904e317045ed9ae2e7d14021aee65e5b889ee1e46f84a` |
| Pinned local `macmon 0.7.2` | `495da8787023c9ebcd62d19e348cd6f1dec5dba3ef2d4f1ff55d9e2079860e19` |

### Harness and evaluator

- Common participant/model harness and rank-126 source:
  `7702fab8a41fe2f4ff2ae281beeb1548b31e3406`. Pre-cutover arms also executed
  that commit's legacy trusted `benchmark.sh`; post-cutover attempts retain
  its model/editable surface but receive the local-only fail-closed trusted
  wrapper listed above after every reset. No post-cutover candidate timing
  receipt has completed; repaired rank-112 attempt 2 loaded the model but never
  crossed the prefill thermal gate.
- Evaluator commit: `dbb0a1d13223adf15b092dd88ed92ef6abdd4b8f`.
- Evaluator SHA-256:
  `647af7530d7c9bf88801fd92146439fdba5f75407bbee6a363b1a3ede1c90150`.
- Required local environment:
  `DARKBLOOM_EXPERT_ALIGNED_GATHER=0`.
- Public fixture SHA-256:
  `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`.

### Model identity

- Frozen transformed model identity:
  `aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d`.
- Files: `9`.
- Bytes: `21,568,891,382`.
- Baseline run SHA-256:
  `e5dde060e5e31ad3ed08399234a3575f772de3ab269870d27e4b972223838313`.
- Baseline summary SHA-256:
  `ddfc03f285f15479bb4323f13284687e72961eb6d312d1e422b9d09a64a4316a`.

### Rank-126-relative quality anchors

The derived tree is local and ignored, but its source artifact and aggregate
receipts are frozen here:

| Evidence | SHA-256 |
|---|---|
| Rank-126 `run.json` | `49fd632c6162eb69d64dcea6a2221f9a9cd02138ee788b98fbcc218187a13d80` |
| Rank-126 `summary.json` | `9289828718a598d382b7a15b7d06b4a7ec95604c6f44ce3c5a27b21ba862c492` |
| Rank-126 `responses.jsonl` | `63cdc5f58ddfdc6dbd18048fe6f4f1e6247203073f04b93955e5bb737c4fade0` |
| Derived `primary-status.txt` | `f9d1691172bf7fc3e814ef33019e498c604bae8af737ff6e749623b062c8cc7e` |
| Derived `summary.json` | `99a6eba0ad4116441af1e67f2a027d06eac05cfd26e4977b890b0566c5de302e` |
| Derived `checksums.sha256` | `17de13803e63be979211432cc9cfc522bb8475ab862fe67562217f1424e7fb8b` |

The derivation ran with `UV_OFFLINE=1`, matched evaluator bundle SHA-256
`647af7530d7c9bf88801fd92146439fdba5f75407bbee6a363b1a3ede1c90150`,
validated compatibility for all ten retrospective comparisons and the rank-126
self-control, ran from a fresh snapshot of the pinned evaluator commit, retained
the primary status audit plus each formal arm's source-binding hashes, and
checksummed the exact expected receipt file set. It loaded no model and made no
network request.

The report-data builder independently derives performance math, raw quality
counts, PPL/NLL, public-probe truth, ranked-prefix identity, source tree hashes,
terminal contracts, control outcomes, extended-diagnostic outcomes, and the
direct-parent commit chain. Failed, interrupted, and infrastructure attempts
are recursively checksummed but remain explicitly unselected. On `--write`,
the builder records the full primary/control/extended input set plus the
tracked rank-126 derivation and rank-111 anchor definitions. The ignored
rank-126-relative output tree remains a separate execution receipt whose
hashes are frozen above.

### Known provenance limits

- Performance is partial: rank 111 is historically valid, five selected candidate attempts
  are rejected for implausible telemetry, and ten arms remain pending. The
  legacy rank-111 metadata does not bind its runner/tool/log hashes; its exact
  log hash is frozen above and it is the only pre-cutover historical exception.
  External ephemeral controller evidence indicates manual-80 fans, but that
  evidence is outside the retained attempt checksum set; the policy mismatch
  still makes the receipt unsuitable as a resumed comparator. New
  attempts bind the runner, local benchmark, fan helper, macmon, clean-env and
  automatic-fan policies, pre/post fan status, persistent telemetry receipt,
  and log, but still do not emit an applied editable-tree digest;
  snapshot attribution relies on the checksummed runner's checkout contract.
- The builder snapshots and rechecks inputs before publication, but the runner
  does not share its writer lock. A final-syscall race is detectable on the
  next audit rather than impossible by construction.
- Local quality is M4 transfer evidence under one compatibility override, not
  a reproduction of the private M5 contract.
- The quality reference is the July 30 clean checkout at
  `eec3f82c9adebc99e3ed15c74138e1ab8032d9cd`, not rank 111 or rank 126. There
  is no completed rank-111 quality arm, so pre-rank-112 drift is not localized.
  Rank 126 is a separate incremental baseline for future candidates, not a
  replacement cumulative reference.
- All primary candidates are connected official-success snapshots, not
  independent trials. The controls were deliberately selected, and only rank
  202 has a formal comparison; ranks 201 and 203 are bounded diagnostics. All
  12 formal arms reject, six arms abstain, and one pass per arm provides no
  variance estimate. The study establishes that the current veto is unusable
  on this cohort, but not a replacement rule or a population error rate.

### Report validation at the evidence cut

- `build-report-data.py --check` reported performance `1/16` historically
  valid, `0/16` current-contract, 5 invalid, and 10 pending; every invalid arm
  names implausible GPU telemetry. It also
  reported 11 formal quality comparisons and four bounded non-completions with
  no pending or invalid primary-quality arms.
- `run-quality-controls.sh status` reported `3/3` processed—one formal
  comparison and two bounded non-completions—with zero pending or invalid
  controls; performance remains disabled for this cohort.
- The extended-AIME audit reported `4/4` valid completed diagnostics, zero
  pending, and zero invalid. All four selected responses remained
  length-bounded at 6,144 tokens. Four retained infrastructure failures are
  recursively checksummed and unselected.
- `derive-rank126-quality.sh` validated ten retrospective comparisons, one
  rank-126 self-control, and four bounded no-decisions: ranks 120–125 retain,
  ranks 112–115 regress on response identity, rank 126 retains against itself,
  and ranks 116–119 remain censored. Its checksum manifest passed in full and
  the evaluator ran offline without model compute.
- `run-quality-anchor.sh status` reported performance disabled and `0/1`
  quality arms processed. The isolated rank-111 anchor remains pending explicit
  authorization to resume model compute.
- `build-report-data.py --check --require-complete` remains non-zero, as
  intended, because performance is incomplete and contains rejected attempts;
  the primary-quality, control, and extended-diagnostic requirements are
  satisfied.
- `swift test --force-resolved-versions` passed all 454 tests in six suites on
  a clean full rerun. The two focused repaired-runner tests also passed. An
  earlier highly parallel pass recorded transient issues that did not
  reproduce on the subsequent complete run.
- An independent manifest-to-report check found all 16 official table rows,
  all 16 performance rows, all 15 dossiers, all three control
  identities and outcome rows, and all four extended-AIME rows. Every frozen
  submission UUID, source ref, official score, paired speedup, and candidate
  phase time from `candidates.json` appears in the report.
- Static-input and current-tool SHA-256 values were recomputed from their
  named files; campaign-executed hashes were reproduced from the stated Git
  objects. All local Markdown targets resolve, all tables have consistent
  column counts, and the report passes Git's whitespace check.
- The rank-126 derivation invoked only the evaluator's file comparison path; it
  loaded no model. A separate repaired rank-112 canary did load the model but
  never entered a timed phase: the plausible prefill gate remained above 40C,
  and the attempt exited `130` with no score or integrity receipt. Its log and
  metadata hashes are `8b74e9035c49107db7992ecb0046ee12831e9e1828b0678f45cbf1543da7b23e`
  and `36add9e227cad06e6316a783c664b9caf2fb956ce2e95786df2e8194facffa5e`.

## Appendix B — report completion checklist

| Item | Current state | Completion rule |
|---|---|---|
| Official 15-snapshot history | Complete | Frozen manifest and findings cross-check |
| Local quality positives | Complete | 11 formal + 4 valid terminal = 15 processed |
| Rank-126 incremental baseline | Complete | 10 provenance-checked retrospective comparisons + 1 self-control + 4 bounded no-decisions; checksum manifest valid |
| Rank-111 quality anchor | **PENDING: 0/1** | Run isolated quality-only arm after model compute is explicitly resumed |
| Local performance | **PARTIAL: 1 historical valid / 0 current-contract / 5 invalid / 10 pending** | 16 current-contract selected full `--local-submit` attempts behind responsive preflights and two credible thermal gates |
| Negative controls | Complete for quick profile | 3/3 processed: 1 formal regression + 2 hash-bound bounded non-completions |
| Extended AIME | Complete for diagnostic contract | 4/4 valid; all four still length-bounded at 6,144 tokens; primary decisions unchanged |
| Final report-data/checksum publication | **PENDING** | Run builder `--write --require-complete` only after all 16 performance arms are valid |

Until the performance cohort is valid and complete, the safe operational conclusion is:
**bootstrap from the active rank-126 stack and the official mechanism record,
but treat local M4 performance and local-gate selectivity as unestablished.**
