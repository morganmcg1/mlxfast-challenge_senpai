# MLX Fast leaderboard wins and campaign bootstrap report

Snapshot: **2026-08-02T09:07:21Z**<br>
Report evidence cut: **2026-08-02T16:22:34Z**<br>
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
- leave the unrun performance study visibly pending while preserving all four
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
| Local M4 performance arms | 16 including rank 111 comparator | **0 valid selected attempts; 16 pending** | Placeholder only; no local speed claims |
| Negative controls | 3 | **3/3 processed: 1 formal regression; 2 bounded AIME non-completions; 0 invalid** | Complete for the frozen quick-profile control contract; no class-separating signal established |
| Extended AIME diagnostics | 4 terminal ranks | **4/4 valid isolated diagnostics; all still length-bounded at 6,144 tokens** | Complete for the frozen diagnostic-only contract; primary quick-profile decisions remain unchanged |

The report is therefore complete as an official-history, frozen local-quality,
control, and extended-diagnostic synthesis, but **not** as a local performance
replication. Local-gate validation remains inconclusive because the only formal
negative control received the same reject decision as every formally
comparable official success.

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
- all 11 formally comparable quick-profile runs **failed** the local 3%
  retention gate;
- each of those 11 missed all three discriminating components: downstream
  correct count, PPL, and ranked-GPQA prefix retention;
- all 11 had `0/9` exact ranked-GPQA prefix matches while preserving identical
  row sets; and
- ranks 116–119 hit the frozen 2,048-token AIME ceiling, so their raw vectors
  are diagnostics and have **no formal local gate decision**.

For the formally comparable official-success cohort, the local gate's observed
positive-label sensitivity is `0/11`. This configuration is not a defensible
submission veto for M5. The completed control cohort adds coverage evidence,
but does not reveal a separator between accepted and rejected official
snapshots.

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
- Rank 203 also failed hidden official correctness, but terminated at the AIME
  ceiling. Its raw `24/53` and PPL `14.841542008507624` overlap or outperform
  the local official-success cohort, while its first public token is exact.
  With no formal prefix comparison or gate decision, it provides no observed
  discriminator.

The useful result is therefore negative: the local suite characterizes drift
and catches some regressions, but this cohort supplies no feature or decision
that separates successful from failed M5 submissions. It remains a debugging
instrument, not a submission-safety oracle.

### 8. Tripling the AIME ceiling did not turn truncation into completion

The isolated diagnostic reran exactly `2024-2024-II-2` for ranks 116–119 with
the response ceiling raised from 2,048 to 6,144 tokens. All four runs finished
successfully as diagnostics, and all four model responses still ended with
`finish_reason = length` rather than `stop`:

- rank 116 extracted answer `1` from 14,432 characters;
- ranks 117–119 each extracted answer `7` from 11,427 characters; and
- none matched the gold answer `236`.

This rules out the narrow hypothesis that these responses were merely a few
tokens short of a natural stop at the primary ceiling. It points instead to a
persistent long-form/repetitive generation behavior on this M4 path. It does
**not** retroactively convert any primary terminal arm into a formal comparison,
and it is not evidence that the officially accepted M5 snapshots are invalid.

### 9. Apple GPU geometry does not transfer reliably

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

The local baseline is
`quality-results/baseline-quick-weave-v3-m4-20260730`:

| Component | Baseline | Required candidate result |
|---|---:|---:|
| Downstream aggregate | 26/53 | at least 26/53 |
| PPL over 256 target tokens | 13.954858401802964 | at most 14.386451960621613 |
| Ranked GPQA exact-prefix retention | 9/9 baseline rows | at least 7/9 matches |
| Public first-token probe | token 5991 after 512-token prompt | exact token 5991 |
| Response row sets | 62 comparable non-PPL rows | exact row-set match |

The 3% retention multiplier does not lower the discrete correct-count floor:
`ceil(26 × 0.97) = 26`.

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

### Local-versus-official gate matrix

| Contract surface | Official M5 contract/result | Local M4 proxy/result | Transfer conclusion |
|---|---|---|---|
| Public behavior | 64-step checked trajectory; all 15 promoted | First token only; all 15 matched token 5991 | All observed successes matched locally, but the probe is materially shallower and is not established as necessary or sufficient for M5 acceptance |
| Hidden exact tokens | 512-token teacher-forced base plus anchor, free-run, and timed oracle; all promoted | No private artifact available | No local equivalence claim possible |
| GPQA behavior | TTFT and semantic judge passed for all 15 | Exact ranked-prefix retention: 0/9 in all 11 formal rows | Exact M4 prefix retention is not aligned with accepted M5 behavior |
| Downstream quality | Private semantic behavior participates in official gate | 11/11 formal rows below 26/53 | Local aggregate rejects every observable official success |
| PPL | Not the official ranking gate | 11/11 formal rows above 14.386451961 | Useful drift diagnostic, not an M5 validity oracle |
| AIME completion | Official submissions completed their gates | Four primary successes hit both the 2,048- and 6,144-token local ceilings; two controls hit 2,048 | The extended result diagnoses persistent bounded generation on M4; terminal arms still have no frozen-gate decision |
| Negative-control calibration | One public-trajectory failure and two hidden-correctness failures | All three first tokens exact; rank 202 formally regressed; ranks 201 and 203 terminal | First-token coverage misses a known public failure; the sole formal reject is not selective because all formal successes also reject |
| Local class separation | 15 official successes versus 3 official failures | 11 formal successes and rank 202 all reject; other 6 arms are terminal | No observed local decision separates the official labels |
| Performance correctness | Official paired timing accepts only exact oracle tokens | **PENDING: 0/16 valid local performance arms** | No local performance/correctness comparison yet |

The observed discordance can arise from M4-versus-M5 numerical behavior,
different kernel dispatch, the required gather override, and differences
between exact-prefix and semantic judgments. It must not be simplified to
"the official winners lost quality."

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
   are terminal. No observed local feature separates the official labels.
8. **The completed extended diagnostic does not repair it either.** All four
   primary terminal ranks remain length-bounded after tripling the ceiling.
   That narrows the local failure mode, but the isolated reruns deliberately
   produce no formal gate decision and no private-M5 equivalence claim.

## Clearly pending local performance study — 16 arms

**PLACEHOLDER STATUS: no local performance result is reported below.** The
auditor finds `0/16` valid selected attempts and `16/16` pending. Empty metric
cells are intentional. Do not substitute failed/interrupted attempt values or
short local-iterate numbers.

| Rank | Submission / source | Required role | Audited status | Local decode | Local prefill | Index vs rank 111 |
|---:|---|---|---|---:|---:|---:|
| 111 | [0682cc25](https://mlx.fast/api/submissions/0682cc25-40a1-4f0e-bb96-c3b0f768b53c) · [`af085760`](https://github.com/Layr-Labs/mlxfast-challenge/commit/af085760e96a5d719a2ba9c5817454158d9edb86) | Same-contract comparator | **PENDING — no valid selected attempt** | — | — | — |
| 112 | [aa6660cb](https://mlx.fast/api/submissions/aa6660cb-a3e4-410a-a365-bb117e3e98f1) · [`df0af746`](https://github.com/Layr-Labs/mlxfast-challenge/commit/df0af746de208e267ae16e7dc62f901aa5cff77a) | Candidate | **PENDING** | — | — | — |
| 113 | [96bfd3b7](https://mlx.fast/api/submissions/96bfd3b7-49c2-4f0b-b0bd-288173ac284b) · [`274a909a`](https://github.com/Layr-Labs/mlxfast-challenge/commit/274a909ae2f8b65414ec7b1bbb5981c5cf091cde) | Candidate | **PENDING** | — | — | — |
| 114 | [3223e19d](https://mlx.fast/api/submissions/3223e19d-8e7a-4001-a2c8-0176900a7005) · [`149892c3`](https://github.com/Layr-Labs/mlxfast-challenge/commit/149892c38865cdb78af6c1b1158fecc853446ed4) | Candidate | **PENDING** | — | — | — |
| 115 | [dd341a52](https://mlx.fast/api/submissions/dd341a52-a695-4d0d-8bdf-75ef44a9c74a) · [`d4cb1ae8`](https://github.com/Layr-Labs/mlxfast-challenge/commit/d4cb1ae8d63cd3e59169bc7685d85ca7970241e6) | Candidate | **PENDING** | — | — | — |
| 116 | [8449082c](https://mlx.fast/api/submissions/8449082c-4dc2-4526-b3bd-69712c3b8a8e) · [`5b46c79c`](https://github.com/Layr-Labs/mlxfast-challenge/commit/5b46c79cfd8d6496989ba5977950e969ba4107ac) | Candidate | **PENDING** | — | — | — |
| 117 | [df2a7483](https://mlx.fast/api/submissions/df2a7483-9c5b-4f4c-8a2f-9fee780515d7) · [`500d92a0`](https://github.com/Layr-Labs/mlxfast-challenge/commit/500d92a0f486a0297f312d8f4d38d5ab3b58f900) | Candidate | **PENDING** | — | — | — |
| 118 | [214fd89a](https://mlx.fast/api/submissions/214fd89a-69af-4858-af54-8a801672c78d) · [`fc306048`](https://github.com/Layr-Labs/mlxfast-challenge/commit/fc306048e61c2cb7e56a8ff406db40adafcc8e79) | Candidate | **PENDING** | — | — | — |
| 119 | [5139da0f](https://mlx.fast/api/submissions/5139da0f-ac51-4a81-b3d8-880a8a74f58f) · [`c5206993`](https://github.com/Layr-Labs/mlxfast-challenge/commit/c5206993d510ca0c50861b1f5d3d26030d76a22b) | Candidate | **PENDING** | — | — | — |
| 120 | [db173215](https://mlx.fast/api/submissions/db173215-a7d7-4863-a333-8132c33be279) · [`7b2c9407`](https://github.com/Layr-Labs/mlxfast-challenge/commit/7b2c9407032e41408fbfaba94625d9c53b1934ca) | Candidate | **PENDING** | — | — | — |
| 121 | [9847ff8f](https://mlx.fast/api/submissions/9847ff8f-918e-4988-ba2f-a1137d23784b) · [`e6596576`](https://github.com/Layr-Labs/mlxfast-challenge/commit/e65965761f34afbabc696b3eccdd363863edd480) | Candidate | **PENDING** | — | — | — |
| 122 | [cc79cef2](https://mlx.fast/api/submissions/cc79cef2-8a0e-4bbd-aaba-bdaaae453249) · [`71b80b1f`](https://github.com/Layr-Labs/mlxfast-challenge/commit/71b80b1f33b01eb3edc871df85675cdbd6fe6320) | Candidate | **PENDING** | — | — | — |
| 123 | [70a3ad4b](https://mlx.fast/api/submissions/70a3ad4b-70da-4b17-ab4f-388945dfee29) · [`60f436a2`](https://github.com/Layr-Labs/mlxfast-challenge/commit/60f436a2361eef72b207c2a3cf0d5b6984b8b0d1) | Candidate | **PENDING** | — | — | — |
| 124 | [a0da915f](https://mlx.fast/api/submissions/a0da915f-450a-4063-bf8e-ec1661f4a661) · [`70fe340b`](https://github.com/Layr-Labs/mlxfast-challenge/commit/70fe340becd16cf5efa40884963283e6a834c84b) | Candidate | **PENDING** | — | — | — |
| 125 | [4173c401](https://mlx.fast/api/submissions/4173c401-0f25-41fd-bec7-cdea22a1aac3) · [`13496639`](https://github.com/Layr-Labs/mlxfast-challenge/commit/1349663988dacafe7ee4b5b11832a4891d1aa5cc) | Candidate | **PENDING** | — | — | — |
| 126 | [05e7894f](https://mlx.fast/api/submissions/05e7894f-0eaf-4f6d-8622-499d1e44185d) · [`7702fab8`](https://github.com/Layr-Labs/mlxfast-challenge/commit/7702fab8a41fe2f4ff2ae281beeb1548b31e3406) | Candidate | **PENDING** | — | — | — |

When valid attempts exist, report native local score, recomputed phase ratios,
absolute seconds/token, correctness state, golden-drift signature, and both
rank-111 and preceding-rank indexes. One full `--local-submit` observation per
arm will still be directional, not a variance estimate.

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
  show that these coarse measures do not isolate the private correctness
  failure.

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
3. Maintain an active-path manifest: default selectors, qualifying shapes,
   weight formats, kernel names, and source/JIT twin reachability.
4. Keep rank-125/rank-126 geometry as a same-binary M5 control where possible.
5. Do not use the current M4 quality gate as an automatic veto; retain its
   component diagnostics and rely on official M5 correctness for ranking. The
   completed controls do not establish a class-separating local signal.

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

### Frozen inputs and study tooling

| Input | SHA-256 |
|---|---|
| [candidates.json](candidates.json) | `785763d0a35cfbcb8b7643816990f60df98a80ff7976c5c1545ab7136f43285e` |
| [official-findings.md](official-findings.md) | `d8d21e346d044a1862a8f9b76ec1cbc24fba817870a05d9a7aa912f891ec442c` |
| [README.md](README.md) | `517673461542af467fcb65319e88c2208a59391b824323f8b84d8d3831ddf2a9` |
| [negative-controls.json](negative-controls.json) | `b7a498ae1c8bb74c0287159e817e7dfa5f2a5c41aa29020c100be18b3089869f` |
| [control-run.json](control-run.json) | `3586c24e184c8b7f9f3dd25403654a2b2bc568b6046e7932f1f9b50b68ec0c14` |
| [build-report-data.py](build-report-data.py) | `1ef17456c7c63f0996e39d5e1ec62191c3ba3098f63b25532685991f3edce255` |
| [run-study.sh](run-study.sh) | `78f97cd18f78885a55afe764563a027622f06daab88e424268be4bede3ef23bd` |
| [run-quality-controls.sh](run-quality-controls.sh) | `c026afb9b2efb54569d4ad2822e40b8d2cde9945e7c5b833ab3f26b844d94ec0` |
| [quality-bridge-wrapper.sh](quality-bridge-wrapper.sh) | `42d3ec349c53ced281baa787906ac04b07e806c01dd703a4510693c73af6678e` |
| [run-extended-aime.py](run-extended-aime.py) | `338042981140aa08a6bcd1c8dcc527e924fc9988998099eb2649dea2646c180e` |
| [extended-aime-ids.json](extended-aime-ids.json) | `fcb81147afd2be45b3aaf809cab88517b1bc8ce9e01c77889e7f70529fee9a59` |
| [EXTENDED_AIME_DIAGNOSTICS.md](EXTENDED_AIME_DIAGNOSTICS.md) | `673288724fc75bafe1c15c69ec6af7fa92a4cd715379dbd5bc4fb3ae852bebd6` |

### Harness and evaluator

- Common harness / rank-126 source:
  `7702fab8a41fe2f4ff2ae281beeb1548b31e3406`.
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

The report-data builder independently derives performance math, raw quality
counts, PPL/NLL, public-probe truth, ranked-prefix identity, source tree hashes,
terminal contracts, control outcomes, extended-diagnostic outcomes, and the
direct-parent commit chain. Failed, interrupted, and infrastructure attempts
are recursively checksummed but remain explicitly unselected. The builder
records the full audited input set on `--write`.

### Known provenance limits

- Performance artifacts are currently pending. When produced, they declare a
  source ref but do not emit the applied editable-tree digest; attribution
  relies on the checksummed runner's checkout contract.
- The builder snapshots and rechecks inputs before publication, but the runner
  does not share its writer lock. A final-syscall race is detectable on the
  next audit rather than impossible by construction.
- Local quality is M4 transfer evidence under one compatibility override, not
  a reproduction of the private M5 contract.
- All primary candidates are official successes. The control cohort is now
  processed, but only rank 202 has a formal comparison; ranks 201 and 203 are
  bounded diagnostics. Because the formal control receives the same reject
  decision as all 11 formal successes, the study still has no observed
  class-separating local decision rule.

### Report validation at the evidence cut

- `build-report-data.py --check` exited successfully and reported performance
  `0/16` valid with 16 pending, plus 11 formal quality comparisons and four
  bounded non-completions with no pending or invalid primary-quality arms.
- `run-quality-controls.sh status` reported `3/3` processed—one formal
  comparison and two bounded non-completions—with zero pending or invalid
  controls; performance remains disabled for this cohort.
- The extended-AIME audit reported `4/4` valid completed diagnostics, zero
  pending, and zero invalid. All four selected responses remained
  length-bounded at 6,144 tokens. Four retained infrastructure failures are
  recursively checksummed and unselected.
- `build-report-data.py --check --require-complete` exited `2`, as intended,
  because the 16 performance arms are still absent; the primary-quality,
  control, and extended-diagnostic completeness requirements are satisfied.
- An independent manifest-to-report check found all 16 official table rows,
  all 16 performance placeholders, all 15 dossiers, all three control
  identities and outcome rows, and all four extended-AIME rows. Every frozen
  submission UUID, source ref, official score, paired speedup, and candidate
  phase time from `candidates.json` appears in the report.
- The SHA-256 values in the frozen-input table were recomputed from the current
  files. All local Markdown targets resolve, all tables have consistent column
  counts, and the report passes Git's whitespace check as a new file.
- The report-writing and builder-audit work invoked no build, benchmark,
  quality-evaluation workload, or model process. It read the completed control
  and extended-diagnostic artifacts produced by their separate runners.
  Earlier scaffold validation included read-only provenance/status checks and
  the pinned evaluator's GPU-free `aime_eval.py --self-test`.

## Appendix B — report completion checklist

| Item | Current state | Completion rule |
|---|---|---|
| Official 15-snapshot history | Complete | Frozen manifest and findings cross-check |
| Local quality positives | Complete | 11 formal + 4 valid terminal = 15 processed |
| Local performance | **PENDING** | 16 valid selected full `--local-submit` attempts |
| Negative controls | Complete for quick profile | 3/3 processed: 1 formal regression + 2 hash-bound bounded non-completions |
| Extended AIME | Complete for diagnostic contract | 4/4 valid; all four still length-bounded at 6,144 tokens; primary decisions unchanged |
| Final report-data/checksum publication | **PENDING** | Run builder `--write --require-complete` only after all 16 performance arms are valid |

Until the performance placeholders are resolved, the safe operational conclusion is:
**bootstrap from the active rank-126 stack and the official mechanism record,
but treat local M4 performance and local-gate selectivity as unestablished.**
