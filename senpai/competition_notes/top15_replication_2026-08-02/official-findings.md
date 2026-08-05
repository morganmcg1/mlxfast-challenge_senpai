# Official findings for leaderboard ranks 112–126

> **Contract correction (2026-08-05).** The interpretation below that a large
> jump does not disprove a candidate acceptance cap is superseded by deployed
> wrapper evidence. The final paired verdict applies the two `0.95` floors and
> accepts candidate gains above `1.053`; the historical receipts remain valid.

Snapshot: **2026-08-02T09:07:21Z**<br>
Track: `laguna-xs-2.1-serial-v2`<br>
Official runner: Apple M5 Max<br>
Frozen source: [`candidates.json`](candidates.json)

This document analyzes the 15 fastest promoted submissions in the frozen
snapshot. It records what each complete source snapshot achieved, what the
submitter said it changed, what the promoted diff actually contains, and how
the snapshots relate conceptually.

The central interpretive rule is that a promoted result proves a **complete
snapshot** passed the official gates and improved the leaderboard. It does not
prove that every item in a bundle was independently beneficial. Several of
these submissions were prepared from an older promoted base while another
submission was in flight, so chronological leaderboard order and conceptual
source lineage are not the same thing.

Companion sources:

- [Live leaderboard](https://mlx.fast/)
- [Exhaustive promotion ledger](../leaderboard_promotions_2026-08-02.md)
- [Campaign brief](../leaderboard_campaign_brief_2026-08-02.md)
- [Local replication contract](README.md)

## Executive findings

From the immediate pre-window comparator at rank 111 to rank 126:

| Metric | Rank 111 | Rank 126 | Derived movement |
|---|---:|---:|---:|
| Score | 2.09306570699382 | 2.4549506212825 | +0.36188491428867975; **+17.2897063422%** |
| Paired decode speedup | 2.1520609555455104 | 2.6466235994572105 | +0.49456264391170013; **+22.9808845626%** |
| Candidate decode | 6.4278893203125 ms/token | 5.249092125 ms/token | −1.1787971953125 ms; **18.3387911112% lower** |
| Candidate decode throughput | 155.5720626427 token/s | 190.5091349487 token/s | **+22.4571633959%** |
| Paired prefill speedup | 1.9256073909692932 | 1.9592709649968867 | +0.03366357402759346; **+1.7482054850%** |
| Candidate prefill | 0.1968064765625 ms/token | 0.195664794921875 ms/token | −0.001141681640625 ms; **0.5801036940% lower** |

The score movement was overwhelmingly decode-led. Because

```text
score = decode_speedup^0.75 * prefill_speedup^0.25
```

the paired-speedup changes contribute factors of **1.1678261865** from decode
and **1.0043421504** from prefill. On the additive log-score scale, decode
accounts for **97.2831470646%** of the gain and prefill for **2.7168529354%**.

The dominant mechanism wave was the attention representation rollout at ranks
116, 117, and 120. Along its actual conceptual branch, rank 113 to rank 120,
score rose from 2.11953731302476 to 2.36996072007723 (**+11.8150034686%**),
candidate decode fell from 6.3250559921875 to 5.4161556015625 ms/token
(**14.3698394409% lower**), and candidate prefill moved by only
0.0001665859375 ms/token (**0.0845313933% lower**). In chronological
leaderboard-delta accounting, those three promotions explain **60.2771067789%**
of this 15-row score increase. That percentage is a frontier accounting, not
a causal Shapley value.

The four largest chronological increments—ranks 120, 117, 124, and 116—sum
to **75.8586635575%** of the window's score movement. They correspond to two
large ideas: read far fewer attention-weight bytes, and stop duplicating
RMSNorm work inside every attention output tile.

## Official gate outcome

All 15 rows were accepted and promoted. Every one reports:

- `passed_correctness = true`;
- 1,344 checked steps;
- `max_abs_diff = 0`;
- 9/9 GPQA first-token/TTFT cases;
- `semantic_gpqa_passed = true`;
- approximately 21 GB peak RAM; and
- the same 21,568,891,382-byte, nine-file transformed weight set.

The displayed semantic-GPQA count was 8/9 for ranks 112, 113, 114, 117, 118,
120, and 122, and 9/9 for the other eight rows. Thus an official semantic pass
did not require the public metric to display 9/9 on every successful run.
This observation should not be converted into a claim about unpublished judge
policy; it is only what these accepted records show.

## Conceptual lineage

The platform promotion commits form a linear chain because each accepted
snapshot is overlaid onto the live branch. The submissions themselves do not.
Public notes and promoted diffs establish this conceptual lineage:

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

Consequences:

- Rank 113 is an alternative to rank 112, not a clean increment on it.
- Ranks 114, 115, and 116 are three alternatives from rank 113.
- Ranks 118, 119, and 120 are three alternatives from rank 117.
- Rank 121 explicitly restores a router optimization erased by rank 120's
  whole-file overlay.

The `Δ vs prior leaderboard` column below remains useful—it is the ranking
record—but it must not be described as the isolated effect of the named
mechanism where the conceptual base differs.

## Exact official metrics

`Δ score vs prior` is the raw score difference from the immediately preceding
leaderboard row, using rank 111 as the predecessor of rank 112. Decode and
prefill cells are `paired speedup / candidate milliseconds per token`.

| Rank | Submission / source | Conceptual base | Official score | Δ score vs prior | Decode x / ms-token | Prefill x / ms-token | Concise mechanism |
|---:|---|---:|---:|---:|---:|---:|---|
| 112 | [aa6660cb](https://mlx.fast/api/submissions/aa6660cb-a3e4-410a-a365-bb117e3e98f1) · [`df0af746`](https://github.com/Layr-Labs/mlxfast-challenge/commit/df0af746de208e267ae16e7dc62f901aa5cff77a) · [PR 971](https://github.com/Layr-Labs/mlxfast-challenge/pull/971) | 111 | 2.11750832958454 | +0.024442622590719942 | 2.181236387388597 / 6.3409827421875 | 1.9372796103266816 / 0.196908529296875 | Lossless affine-metadata indexing plus shared tiny fused-attention parameter arrays. |
| 113 | [96bfd3b7](https://mlx.fast/api/submissions/96bfd3b7-49c2-4f0b-b0bd-288173ac284b) · [`274a909a`](https://github.com/Layr-Labs/mlxfast-challenge/commit/274a909ae2f8b65414ec7b1bbb5981c5cf091cde) · [PR 973](https://github.com/Layr-Labs/mlxfast-challenge/pull/973) | 111 | 2.11953731302476 | +0.002028983440220067 | 2.1895445992266027 / 6.3250559921875 | 1.922661713712948 / 0.19706990625 | Re-landed metadata indexing alone on the rank-111 midpoint-threshold source. |
| 114 | [3223e19d](https://mlx.fast/api/submissions/3223e19d-8e7a-4001-a2c8-0176900a7005) · [`149892c3`](https://github.com/Layr-Labs/mlxfast-challenge/commit/149892c38865cdb78af6c1b1158fecc853446ed4) · [PR 983](https://github.com/Layr-Labs/mlxfast-challenge/pull/983) | 113 | 2.12281334772927 | +0.003276034704509989 | 2.19030925055764 / 6.32126790625 | 1.9325508351309963 / 0.1967543125 | Exact top-8 expert selection inside the routed QMV prologue. |
| 115 | [dd341a52](https://mlx.fast/api/submissions/dd341a52-a695-4d0d-8bdf-75ef44a9c74a) · [`d4cb1ae8`](https://github.com/Layr-Labs/mlxfast-challenge/commit/d4cb1ae8d63cd3e59169bc7685d85ca7970241e6) · [PR 985](https://github.com/Layr-Labs/mlxfast-challenge/pull/985) | 113 | 2.12365737170721 | +0.0008440239779399228 | 2.199289573232799 / 6.28067903125 | 1.9120117300597668 / 0.19681005859375 | Four-SIMD fused affine norm/QKV grouping with prefetch depth two. |
| 116 | [8449082c](https://mlx.fast/api/submissions/8449082c-4dc2-4526-b3bd-69712c3b8a8e) · [`5b46c79c`](https://github.com/Layr-Labs/mlxfast-challenge/commit/5b46c79cfd8d6496989ba5977950e969ba4107ac) · [PR 986](https://github.com/Layr-Labs/mlxfast-challenge/pull/986) | 113 | 2.1640759452478 | +0.040418573540589975 | 2.2736319629228885 / 6.0902330703125 | 1.8660767105710185 / 0.197249185546875 | Expanded checkpoint-NVFP4 attention coverage from layer 32 to layer 24. |
| 117 | [df2a7483](https://mlx.fast/api/submissions/df2a7483-9c5b-4f4c-8a2f-9fee780515d7) · [`500d92a0`](https://github.com/Layr-Labs/mlxfast-challenge/commit/500d92a0f486a0297f312d8f4d38d5ab3b58f900) · [PR 995](https://github.com/Layr-Labs/mlxfast-challenge/pull/995) | 116 | 2.23332009444833 | +0.06924414920053001 | 2.3707153235296095 / 5.85775065625 | 1.8670918086319037 / 0.196566080078125 | Moved the NVFP4 boundary from 24 to exact-tested layer 17. |
| 118 | [214fd89a](https://mlx.fast/api/submissions/214fd89a-69af-4858-af54-8a801672c78d) · [`fc306048`](https://github.com/Layr-Labs/mlxfast-challenge/commit/fc306048e61c2cb7e56a8ff406db40adafcc8e79) · [PR 999](https://github.com/Layr-Labs/mlxfast-challenge/pull/999) | 117 | 2.2414044139947 | +0.008084319546370011 | 2.384968779200647 / 5.8330843046875 | 1.8605133763413995 / 0.197362142578125 | Composed exact top-8, unpacked routed R1 QMV, and SG4/PF2. |
| 119 | [5139da0f](https://mlx.fast/api/submissions/5139da0f-ac51-4a81-b3d8-880a8a74f58f) · [`c5206993`](https://github.com/Layr-Labs/mlxfast-challenge/commit/c5206993d510ca0c50861b1f5d3d26030d76a22b) · [PR 1002](https://github.com/Layr-Labs/mlxfast-challenge/pull/1002) | 117 | 2.26148968661582 | +0.02008527262111981 | 2.3764347227699028 / 5.841873375 | 1.9489503612125283 / 0.197732177734375 | Hoisted corrected router-order ordinals into their existing producer. |
| 120 | [db173215](https://mlx.fast/api/submissions/db173215-a7d7-4863-a333-8132c33be279) · [`7b2c9407`](https://github.com/Layr-Labs/mlxfast-challenge/commit/7b2c9407032e41408fbfaba94625d9c53b1934ca) · [PR 1003](https://github.com/Layr-Labs/mlxfast-challenge/pull/1003) | 117 | 2.36996072007723 | +0.1084710334614103 | 2.5682349829553703 / 5.4161556015625 | 1.862345783592638 / 0.1969033203125 | Moved all 40 attention layers to checkpoint NVFP4 and unlocked format-aware fusion. |
| 121 | [9847ff8f](https://mlx.fast/api/submissions/9847ff8f-918e-4988-ba2f-a1137d23784b) · [`e6596576`](https://github.com/Layr-Labs/mlxfast-challenge/commit/e65965761f34afbabc696b3eccdd363863edd480) · [PR 1014](https://github.com/Layr-Labs/mlxfast-challenge/pull/1014) | 120 | 2.37074944628857 | +0.0007887262113399629 | 2.565469122263709 / 5.3976897734375 | 1.870864160764886 / 0.1969623203125 | Restored producer-computed router keys erased by the all-NVFP4 overlay. |
| 122 | [cc79cef2](https://mlx.fast/api/submissions/cc79cef2-8a0e-4bbd-aaba-bdaaae453249) · [`71b80b1f`](https://github.com/Layr-Labs/mlxfast-challenge/commit/71b80b1f33b01eb3edc871df85675cdbd6fe6320) · [PR 1017](https://github.com/Layr-Labs/mlxfast-challenge/pull/1017) | 121 | 2.38717668655054 | +0.016427240261970066 | 2.5506483303610423 / 5.424066078125 | 1.956980526474057 / 0.196989095703125 | Folded E4M3 sign handling and exact power-of-two scales in the fused NVFP4 kernel. |
| 123 | [70a3ad4b](https://mlx.fast/api/submissions/70a3ad4b-70da-4b17-ab4f-388945dfee29) · [`60f436a2`](https://github.com/Layr-Labs/mlxfast-challenge/commit/60f436a2361eef72b207c2a3cf0d5b6984b8b0d1) · [PR 1024](https://github.com/Layr-Labs/mlxfast-challenge/pull/1024) | 122 | 2.39434519974008 | +0.007168513189539816 | 2.5759627244533863 / 5.3932425078125 | 1.9227744102278264 / 0.196256265625 | Fused split-K prefill replay and removed dormant LM-head arms. |
| 124 | [a0da915f](https://mlx.fast/api/submissions/a0da915f-450a-4063-bf8e-ec1661f4a661) · [`70fe340b`](https://github.com/Layr-Labs/mlxfast-challenge/commit/70fe340becd16cf5efa40884963283e6a834c84b) · [PR 1027](https://github.com/Layr-Labs/mlxfast-challenge/pull/1027) | 123 | 2.45073250313311 | +0.05638730339303022 | 2.6492948985023403 / 5.2904329375 | 1.9399598118033108 / 0.19554093359375 | Disabled fused norm/QKV/gate because it duplicated RMSNorm work per output tile. |
| 125 | [4173c401](https://mlx.fast/api/submissions/4173c401-0f25-41fd-bec7-cdea22a1aac3) · [`13496639`](https://github.com/Layr-Labs/mlxfast-challenge/commit/1349663988dacafe7ee4b5b11832a4891d1aa5cc) · [PR 1051](https://github.com/Layr-Labs/mlxfast-challenge/pull/1051) | 124 | 2.45196981458518 | +0.0012373114520696227 | 2.6402444474889513 / 5.2711627578125 | 1.963939313525582 / 0.195565998046875 | Aligned uchar4 affine-code loads plus layer-0 projection-ready `asyncEval`. |
| 126 | [05e7894f](https://mlx.fast/api/submissions/05e7894f-0eaf-4f6d-8622-499d1e44185d) · [`7702fab8`](https://github.com/Layr-Labs/mlxfast-challenge/commit/7702fab8a41fe2f4ff2ae281beeb1548b31e3406) · [PR 1056](https://github.com/Layr-Labs/mlxfast-challenge/pull/1056) | 125 | 2.4549506212825 | +0.0029808066973200376 | 2.6466235994572105 / 5.249092125 | 1.9592709649968867 / 0.195664794921875 | Retiled fused routed/shared down plus residual to one output row per SIMD. |

## Mechanism waves

### Wave 1: exact metadata and dependency-graph experiments

Ranks 112–115 explored small decode wins while preserving accepted attention
numerics.

The metadata layout at ranks 112 and 113 replaces repeated raw BF16
`(scale, bias)` pairs with UInt16 indices into an insertion-ordered UInt32
table. Kernels reconstruct the exact two UInt16 payloads by bit cast at the
same use point, retaining every code byte, accumulation operation, reduction,
and BF16 store. Rank 113 is the cleaner evidence because it contains only this
runtime mechanism. All 32 affine output-projection banks and 28 of 32 fused
affine QKV banks fit the UInt16 table; four QKV banks decline safely to the raw
path.

Rank 114 demonstrates that removing a dependency window matters more than
removing a dispatch. The routed QMV computes its own exact top-8 winner from
the current router inputs, so it can execute alongside the standalone top-8
selector and shared QMV instead of waiting. The selector remains because later
consumers still need its indices and weights. The sparse layer moves from
seven serialized barrier windows to six.

Rank 115 changes ownership geometry rather than arithmetic. Four SIMD groups
share an exact RMSNorm replica over 16 projection rows instead of two groups
over eight. The initial SG4/PF4 configuration was slightly slower; reducing
register-prefetch depth to two made the long local control positive. Geometry
and prefetch/live-state pressure therefore have to be tuned together.

These are alternative branches, not three cumulative wins. Their durable
value is the method: preserve exact bit patterns and reduction order, expose a
same-binary control, and optimize the live dependency or resource graph.

### Wave 2: halve attention bytes with checkpoint NVFP4

Ranks 116, 117, and 120 are the largest coherent wave.

The inherited decode side layout represented attention Q/K/V and output
projection weights as group-32 affine INT8:

```text
1 byte code/value + 2-byte scale/32 + 2-byte bias/32
= 1.125 bytes/parameter
```

The checkpoint already stores those weights as group-16 NVFP4:

```text
4-bit code/value + one E4M3 scale byte/16
= 0.5625 bytes/parameter
```

Moving a layer to checkpoint NVFP4 therefore halves that layer's decode-side
attention weight traffic. It also moves numerics toward the checkpoint oracle
rather than introducing a third representation.

Coverage moved 32 → 24 at rank 116, 24 → 17 at rank 117, and 17 → 0 at rank
120. Rank 120 also relaxed an obsolete fixed `layer >= 32` fusion guard so the
existing NVFP4 norm/QKV/gate kernel could run wherever the selected wire
format made it valid.

Rank 117 provides the most important correctness warning in this wave. Its
local boundary sweep was:

| NVFP4 start layer | Local exact-token result |
|---:|---|
| 24 | pass |
| 20 | pass |
| 19 | fail at teacher-forced step 3 |
| 18 | fail at teacher-forced step 3 |
| 17 | pass |
| 16 | fail at teacher-forced step 3 |

Near-tie argmax behavior is not monotonic in the number of converted layers.
A sequential search that stops at the first failure would have missed a
faster exact boundary. Numerical boundaries must be tested individually.

### Wave 3: reconcile the frontier and remove mature-path overhead

Ranks 121–126 optimize the all-NVFP4 frontier rather than widening its
representation further.

Rank 121 restores exact corrected router ordinals in the existing fused
residual/RMSNorm/router producer. Computing 256 ordinals once avoids
reconstructing the nonlinear score and ordering key across the routed QMV's
1,024 threadgroups. The standalone top-8 path remains available for its other
consumers.

Rank 122 removes instructions from the fused NVFP4 scale path. It carries the
E4M3 sign directly into the half bit pattern and folds `256 * 16384` into one
exact `2^22` float scale. The submitter exhaustively checked all 256 scale-byte
patterns. This was a narrow, correctness-strong change, but its official
causal timing evidence is weak: candidate decode was slower than rank 121
while the paired prefill ratio moved sharply. Rank 124 later makes this fused
path opt-in, so the rank-122 mechanism is not active by default at rank 126.

Rank 123's fused split-K kernel is a better example of profitable fusion. One
dispatch replays each NVFP4 partition's original loader/MMA schedule,
emulates the BF16 intermediate-store rounding in registers, accumulates
partitions in the old FP32 reduction order, and emits the standard final tile
store. It removes an intermediate surface and reduction dispatches without
duplicating a producer. Deleted LM-head int6/preabs arms were dormant and
served only to satisfy the editable-source byte cap.

Rank 124 supplies the complementary lesson: **un-fusion can win**. Once all 40
attention layers became eligible for the fused norm/QKV/gate kernel, every
output-tile threadgroup independently repeated the same 2,048-element RMS
reduction and barriers. The separate path computes RMSNorm once, materializes
one 4 KiB BF16 row, and lets the NVFP4 QKV and affine gate kernels consume it.
Its +2.3550197941% leaderboard jump is one of the strongest late-stage results.

Rank 125 composes two small mechanisms with independent positive official
candidate-phase receipts: a single aligned `uchar4` load for four affine code
bytes while retaining four sequential multiply-add statements, and an
`asyncEval` immediately after layer 0's QKV/gate values are constructed.
Candidate decode improved by 0.3642457983% versus rank 124 even though its
paired decode speedup moved the other way.

Rank 126 moves the fused routed/shared down+residual kernel from four rows to
one row per SIMD group and grows the grid by exactly four. The same rows,
weights, scale bytes, qdots, reduction order, router weighting, BF16
boundaries, and residual stores remain. An isolated earlier M5 run showed
about a 0.392% candidate-decode improvement; rank 126 improved candidate
decode by 0.4187052046% versus rank 125. On the submitter's local Apple GPU,
the same ownership change was approximately 12% slower. That sign reversal is
direct evidence that occupancy and scheduling do not transfer reliably across
Apple GPU generations.

## Concise submission dossiers

### Rank 112 — indexed metadata plus shared carriers

- **Actual base:** rank 111.
- **Outcome:** score +1.1677905050%; raw candidate decode 1.3520235616% lower
  and prefill 0.0518543577% higher than rank 111.
- **Mechanism:** exact UInt16 metadata indirection plus reuse of immutable
  one- and three-element attention parameter arrays across lockstep layers.
- **Interpretation:** an officially successful two-mechanism bundle. The
  metadata idea had an earlier positive absolute M5 receipt; carrier sharing
  was not separately priced in this row.

### Rank 113 — metadata-only re-land

- **Actual base:** rank 111, not rank 112.
- **Outcome:** score +1.2647288588%; raw candidate decode 1.5997992965% lower
  and prefill 0.1338521435% higher than rank 111.
- **Mechanism:** the exact metadata layout alone, with fail-closed raw fallback
  for banks exceeding 65,536 distinct pairs.
- **Interpretation:** stronger isolation for the metadata idea. The shared
  carrier mechanism from rank 112 is absent.

### Rank 114 — top-8 inside routed QMV

- **Actual base:** rank 113.
- **Outcome:** score +0.1545636722%; raw candidate decode 0.0598901566% lower
  and prefill 0.1601430457% lower than rank 113.
- **Mechanism:** reproduce the strict total-order top-8 selection inside the
  routed QMV so that the QMV no longer waits on the standalone selector.
- **Interpretation:** structurally clear dependency-window removal, but a
  small single-run official timing movement.

### Rank 115 — SG4/PF2 fused affine QKV

- **Actual base:** rank 113, not rank 114.
- **Outcome:** score +0.1943848149%; raw candidate decode 0.7016058197% lower
  and prefill 0.1318555741% lower than rank 113.
- **Mechanism:** four SIMD groups per threadgroup with exact virtual RMS slot
  mapping and a jointly tuned prefetch depth of two.
- **Interpretation:** the tuned combination matters; SG4 with the inherited
  prefetch depth four was locally negative. This snapshot drops rank 114.

### Rank 116 — NVFP4 layers 24–39

- **Actual base:** rank 113, not rank 115.
- **Outcome:** score +2.1013374924%; raw candidate decode 3.7125824999% lower
  and prefill 0.0909724373% higher than rank 113.
- **Mechanism:** halve QKV/O bytes for eight more layers by using checkpoint
  NVFP4 instead of the affine INT8 side layout.
- **Interpretation:** strong representation/bandwidth evidence. This branch
  does not contain the rank-114 or rank-115 alternatives.

### Rank 117 — NVFP4 layers 17–39

- **Actual base:** rank 116.
- **Outcome:** score +3.1997097585%; raw candidate decode 3.8172991309% lower
  and prefill 0.3463159895% lower than rank 116.
- **Mechanism:** one default changes from layer 24 to layer 17.
- **Interpretation:** exceptionally clean source delta and a critical lesson
  about nonmonotonic near-tie correctness boundaries.

### Rank 118 — exact scheduling recomposition

- **Actual base:** rank 117.
- **Outcome:** score +0.3619866031%; raw candidate decode 0.4210891349% lower
  and prefill 0.4049846747% higher than rank 117.
- **Mechanism:** top-8 production, unpacked one-row routed QMV, and SG4/PF2.
- **Interpretation:** prior exact receipts support the pieces, but this is a
  three-mechanism composition, not an isolated marginal measurement.

### Rank 119 — producer-computed router keys

- **Actual base:** rank 117, not rank 118.
- **Outcome:** score +1.2613324994%; raw candidate decode 0.2710474068% lower
  and prefill 0.5932344257% higher than rank 117.
- **Mechanism:** compute exact corrected ordinals once beside the BF16 router
  logit store, then let each QMV SIMD perform only comparator rounds.
- **Interpretation:** repeated local A/Bs across attention layouts were
  positive, but the immediate leaderboard increase cannot be added to rank
  118 because this snapshot replaces it.

### Rank 120 — all-layer NVFP4

- **Actual base:** rank 117, not rank 119.
- **Outcome:** score +6.1182732367%; raw candidate decode 7.5386454733% lower
  and prefill 0.1715658339% higher than rank 117.
- **Mechanism:** set NVFP4 start layer to zero and let the format guard enable
  fused norm/QKV/gate across the whole coverage window.
- **Interpretation:** largest result in the window and the endpoint of the
  legal representation-byte ladder. It erases rank-119 router keys.

### Rank 121 — restore router keys

- **Actual base:** rank 120.
- **Outcome:** score +0.0332801386%; raw candidate decode 0.3409397640% lower
  and prefill 0.0299639437% higher than rank 120.
- **Mechanism:** reconstruct the rank-119 producer/consumer dependency change
  on the all-NVFP4 source; remove unreachable kernels for source budget.
- **Interpretation:** the official delta is tiny, but the source-history
  lesson is large: promotion state is replaceable, not automatically
  cumulative.

### Rank 122 — exact NVFP4 scale/sign fold

- **Actual base:** rank 121.
- **Outcome:** score +0.6929133860%; raw candidate decode 0.4886591448% higher
  and prefill 0.0135941690% higher than rank 121.
- **Mechanism:** exact sign carry and `2^22` scale fold in the fused tail
  kernel, with exhaustive scale-byte verification.
- **Interpretation:** correctness evidence is strong, timing attribution is
  weak because the candidate phases did not improve. The path becomes
  default-off at rank 124.

### Rank 123 — exact fused split-K prefill

- **Actual base:** rank 122.
- **Outcome:** score +0.3002925267%; raw candidate decode 0.5682742406% lower
  and prefill 0.3720155552% lower than rank 122.
- **Mechanism:** remove split-K intermediate/reduce dispatches while emulating
  their exact BF16 and FP32 boundaries; delete only dormant LM-head arms.
- **Interpretation:** a narrow active mechanism with favorable raw movement
  in both phases. The accompanying negative result on runtime-parametric
  kernel geometry is equally valuable.

### Rank 124 — un-fuse attention input projection

- **Actual base:** rank 123.
- **Outcome:** score +2.3550197941%; raw candidate decode 1.9062664096% lower
  and prefill 0.3644887611% lower than rank 123.
- **Mechanism:** make stock RMSNorm plus separate NVFP4 QKV and INT8 gate
  projections the default; keep the fused path as an explicit control.
- **Interpretation:** strong same-binary brackets and clear producer
  multiplicity make this one of the most credible late-stage causal wins.

### Rank 125 — compose two small official positives

- **Actual base:** rank 124.
- **Outcome:** score +0.0504874135%; raw candidate decode 0.3642457983% lower
  and prefill 0.0128180083% higher than rank 124.
- **Mechanism:** aligned four-byte affine-code loads and one layer-0
  projection-ready enqueue.
- **Interpretation:** the paired score understates the candidate decode move;
  both pieces had independent positive M5 candidate-phase receipts. A locally
  attractive dense-256 geometry arm was deliberately excluded after a
  negative official result.

### Rank 126 — one output row per SIMD in fused down

- **Actual base:** rank 125.
- **Outcome:** score +0.1215678382%; raw candidate decode 0.4187052046% lower
  and prefill 0.0505184316% higher than rank 125.
- **Mechanism:** reduce per-SIMD live accumulators and expose four times as
  many independent down-weight streams, with a bijective row remap.
- **Interpretation:** supported by an isolated positive official M5 receipt,
  but dramatically negative on another Apple GPU. Treat it as M5-specific
  until independently re-established elsewhere.

## What is active at rank 126

The latest source is a composition of selected endpoints, not all 15 wins.

| Status | Mechanism | Provenance | Rank-126 interpretation |
|---|---|---|---|
| Active | All 40 attention QKV/O banks use checkpoint NVFP4 | 116 → 117 → 120 | Dominant landed byte reduction; affine INT8 QKV/O is now a control/fallback, not the default. |
| Active | Producer-computed exact router ordinals | 119, restored 121 | Avoids high-fan-out nonlinear key reconstruction while preserving standalone router consumers. |
| Active | Exact fused split-K prefill | 123 | Removes an intermediate surface and reduce dispatches for eligible non-affine quantized matmuls. |
| Active | Separate RMSNorm, NVFP4 QKV, and affine gate | 124 | The all-layer fused norm/QKV/gate path is compiled but default-off. |
| Active | Aligned uchar4 affine-code loads | 125 | Changes memory load width without changing sequential accumulation. |
| Active | Layer-0 projection-ready `asyncEval` | 125 | Starts already-constructed GPU work while Swift builds the rest of layer 0. |
| Active | R1 fused routed/shared down plus residual | 126 | M5-positive ownership geometry; architecture-sensitive. |
| Superseded | Shared fused-attention parameter carriers | 112 | Removed by the rank-113 metadata-only alternative. |
| Effectively superseded | Indexed affine QKV/O metadata | 112–113 | Code remains, but all default QKV/O banks are now NVFP4, so the original qualifying affine banks no longer own the hot path. |
| Superseded | Early consumer-local top-8 variants | 114, 118 | Replaced by producer-computed ordinals and the current packed routed consumer. |
| Superseded | SG4 affine-QKV geometry | 115, 118 | Displaced by alternative overlays and then by all-layer NVFP4. |
| Subsumed | NVFP4 boundaries 24 and 17 | 116–117 | Valuable rollout evidence; final default is boundary zero. |
| Default-off | Fused-tail scale/sign fold | 122 | It affects the fused norm/QKV/gate kernel that rank 124 makes opt-in. |
| Default-off | All-layer fused norm/QKV/gate schedule | 120, reversed 124 | Format eligibility remains correct, but the separate schedule is faster at current multiplicity. |

This table should be kept current during our campaign. A mechanism can remain
in source while becoming irrelevant to the selected path, and a later overlay
can silently remove an orthogonal win.

## Causal and measurement cautions

### A promotion is a snapshot result

Public mechanism notes are detailed but remain author claims. The strongest
evidence combines a narrow diff, a same-binary selector or A/B bracket, and an
official candidate-phase receipt. Bundled snapshots and alternative branches
deserve more conservative attribution.

### Paired baselines make cross-row phase stories noisy

Across these official records, same-session baseline decode ranged from
13.81303190625 to 14.0159169921875 ms/token, a **1.4687947390%** span. Baseline
prefill ranged from 0.366702068359375 to 0.38550382421875 ms/token, a
**5.1272565610%** span.

The paired ratio is the ranking authority because it cancels session drift.
It can nevertheless make mechanism attribution counterintuitive across
different sessions:

- Rank 119 is a decode-only router change, yet its immediate score increase is
  dominated by a large paired-prefill movement.
- Rank 122 promoted while raw candidate decode and prefill were both slightly
  slower than rank 121.
- Rank 125 improved raw candidate decode while its paired decode speedup fell.

Raw candidate times are also cross-session observations, not controlled A/Bs.
Use them as corroboration. Source reachability, same-binary controls, repeated
brackets, and independent official receipts are the causal tools.

### Correctness boundaries are discrete and nonmonotonic

Exact-token gates convert tiny numerical changes into pass/fail outcomes at
near-tie argmaxes. More approximation does not imply a monotonic loss surface,
as the rank-117 boundary sweep shows. Test each candidate boundary and retain
the exact BF16 materialization and reduction contracts explicitly.

### Fusion is frontier-relative

Rank 123 fusion wins because it removes a real intermediate and faithfully
replays its rounding. Rank 124 un-fusion wins because the fused kernel
duplicates the same producer work in every consumer group. Count producer
multiplicity, barriers, live registers, threadgroup memory, input rereads, and
occupancy—not only launches.

### Dormant-looking code can change a pipeline

Rank 123's public postmortem records a runtime-parametric QMV geometry that
regressed the official M5 even when its knobs selected the stock geometry.
The likely cause was a runtime-bounded branch increasing register allocation
for the entire pipeline state. Prefer separate compile-time-specialized PSOs
to “harmless” runtime branches in a hot kernel.

### Apple GPU geometry does not transfer reliably

Rank 126 was roughly 12% slower locally and about 0.4% faster in isolated
official M5 candidate time. Kernel ownership, occupancy, and instruction
scheduling results must be labeled by GPU generation. Our M4 replication is
directional evidence, not a literal M5 reproduction.

### A large public jump does not prove the band changed

The acceptance band is evaluated against pinned calibration while the public
score is a same-session paired ratio. Rank 120's public jump therefore must
not be read as proof that the policy relaxed. Continue staging changes into
small, independently diagnosable submissions.

## Campaign implications

1. **Start from rank 126, not from historical patches.** The current stack
   already contains, supersedes, or deliberately disables most earlier ideas.
2. **Maintain an active-path manifest.** Record defaults, guards, qualifying
   shapes and formats, and restoration selectors after every promotion.
3. **Measure bytes before designing kernels.** The largest late win came from
   comparing INT8 to the already-legal NVFP4 checkpoint representation, not
   to the original BF16 path.
4. **Optimize value-graph fan-out.** Small computations become large when
   repeated across 1,024 consumer groups; hoist exact shared metadata only to
   producers those consumers already depend on.
5. **Use same-binary controls.** Every new default should have a direct
   selector that restores the current frontier without changing the binary or
   pipeline cache unintentionally.
6. **Preserve arithmetic contracts as first-class documentation.** Exact
   payload bit casts, strict total-order ties, BF16 rounding boundaries,
   partition-store emulation, signed-zero cases, and reduction order are what
   made aggressive structural changes gate-safe.
7. **Treat sub-1% official results as distributions.** Require repeated local
   brackets where transferable, inspect absolute candidate phases and the
   paired baseline, and prefer independent official receipts over one scalar.
8. **Keep search breadth.** Attention representation is now at its legal byte
   floor, so new work should investigate scheduling, duplicated computation,
   graph-construction overlap, attention/MoE epilogues, KV handling, and the
   untouched transform surface rather than re-running the old widening ladder.

The record provides strong priors, not a mandate to copy every historical
idea. The useful balance is to preserve the current proven stack, reuse the
proof and measurement techniques that worked, and reserve meaningful campaign
capacity for hypotheses the leaderboard has not already exhausted.
