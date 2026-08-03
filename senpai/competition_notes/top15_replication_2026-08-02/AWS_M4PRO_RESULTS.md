# AWS M4 Pro replication of leaderboard ranks 112–126

Status: **complete, 15 of 15 candidates validated** as of 2026-08-03.

This report compares the frozen top-15 leaderboard snapshots with private,
same-host measurements on AWS EC2 `mac-m4pro.metal`. It answers a practical
question: which established M5 optimizations are useful priors for our own
campaign, and which must be retuned on the official M5?

No command in this campaign invoked `mlxfast submit`. All benchmark outputs
and raw result trees remain local and ignored by Git. Only this aggregate
report is tracked.

Companion documents:

- [Official M5 findings](official-findings.md)
- [Replication contract and runner](README.md)
- [Frozen submission ledger](candidates.json)
- [Full local quality report](REPORT.md)
- [Quality-proxy calibration](QUALITY_CALIBRATION.md)
- [AWS runbook](../../infra.md)

## Executive answer

The M4 Pro is a strong directional proxy for **representation, memory-traffic,
and dependency-graph changes**, but it is not a reliable proxy for exact GPU
occupancy geometry.

- The small early changes at ranks 112–115 reproduce closely. Their M4
  weighted gains versus rank 111 are 1.0095–1.0199×, close to the official
  rank-111-normalized range of 1.0101–1.0175×.
- The checkpoint-NVFP4 rollout at ranks 116, 117, and 120 transfers strongly.
  Rank 120 reaches 1.1971× on M4 versus 1.1369× in the official M5 raw-time
  comparison. The exact magnitude is different, but the main conclusion is
  the same: reading roughly half as many attention-weight bytes is a major
  decode win.
- Ranks 120–125 all land between 1.1971× and 1.2082× on their host-local M4
  indices, versus 1.1369×–1.1623× in the official normalized M5 comparison.
  This strongly transfers the all-layer NVFP4 and separate-RMSNorm foundation;
  the smaller 120→125 ordering remains below what these cross-host cohorts can
  attribute confidently.
- Rank 126 is the counterexample. The one-row-per-SIMD retile improves M5 by
  about 0.3% over rank 125 in the rank-111-normalized weighted comparison, but
  regresses the M4 weighted index by about 7.3% and decode by about 10.0%
  versus rank 125. SIMD ownership, register pressure, occupancy, and `_nax`
  scheduling therefore require M5 evidence.

The right operating model is: use M4 to reject bad architecture-neutral ideas
and validate large structural wins, then use the official M5 for final kernel
geometry and sub-1% ordering. M4 is useful; it is not a drop-in performance
oracle for M5.

## How to read the comparison

Every candidate below was compared with a fresh rank-111 run in the same
cohort on the same physical host. The host-local ratios are:

```text
prefill_x = rank111_prefill_seconds_per_token / candidate_prefill_seconds_per_token
decode_x  = rank111_decode_seconds_per_token  / candidate_decode_seconds_per_token
weighted_x = decode_x^0.75 * prefill_x^0.25
```

The “official normalized” columns apply that same calculation to the raw M5
candidate milliseconds in `candidates.json`. They are deliberately **not**
the published paired speedups or leaderboard score: each official submission
had its own same-session pinned baseline, so direct ratios of published
speedups would mix in baseline drift. Rank-111-normalized raw candidate times
give the cleanest available like-for-like cumulative comparison.

Ratios above one are faster. Table values are rounded to six decimals; the
ignored score JSON retains full precision.

### Cohort baselines

| Cohort | Candidates | Rank-111 prefill ms/token | Rank-111 decode ms/token | Status |
|---|---|---:|---:|---|
| `aws-top15-01r1` | 112–114 | 1.127997 | 12.429316 | valid |
| `aws-top15-03r3` | 115–117 | 1.118251 | 12.466386 | valid |
| `aws-top15-03r1` | 118 | 1.116307 | 12.452107 | valid |
| `aws-top15-03r2` | 119–120 | 1.127158 | 12.476877 | valid |
| `aws-top15-04r3` | 121 | 1.120949 | 12.434350 | valid recovery cohort |
| `aws-top15-01r2` | 122 | 1.141534 | 12.446776 | valid |
| `aws-top15-03r4` | 123 | 1.127783 | 12.488313 | valid |
| `aws-top15-05` | 124–126 | 1.127556 | 12.426714 | valid |

Splitting the work into retry cohorts was intentional after infrastructure
failures: each retry received a new workspace and a new rank-111 measurement.
No candidate is normalized against another host's baseline.

## Exact M4 results and official comparison

In the paired phase columns, values are `prefill / decode`. “M4 ÷ M5” is the
ratio between the two rank-111-normalized weighted indices; it is a transfer
comparison, not a score prediction.

| Rank | Submission / source | Cohort | M4 candidate ms/token | M4 phase x | M4 weighted x | Official phase x | Official weighted x | M4 ÷ M5 |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 112 | [aa6660cb](https://mlx.fast/api/submissions/aa6660cb-a3e4-410a-a365-bb117e3e98f1) · [`df0af746`](https://github.com/Layr-Labs/mlxfast-challenge/commit/df0af746de208e267ae16e7dc62f901aa5cff77a) | `01r1` | 1.127650 / 12.260721 | 1.000308 / 1.013751 | 1.010373 | 0.999482 / 1.013706 | 1.010131 | 1.000240 |
| 113 | [96bfd3b7](https://mlx.fast/api/submissions/96bfd3b7-49c2-4f0b-b0bd-288173ac284b) · [`274a909a`](https://github.com/Layr-Labs/mlxfast-challenge/commit/274a909ae2f8b65414ec7b1bbb5981c5cf091cde) | `01r1` | 1.126721 / 12.254865 | 1.001133 / 1.014235 | 1.010944 | 0.998663 / 1.016258 | 1.011831 | 0.999123 |
| 114 | [3223e19d](https://mlx.fast/api/submissions/3223e19d-8e7a-4001-a2c8-0176900a7005) · [`149892c3`](https://github.com/Layr-Labs/mlxfast-challenge/commit/149892c38865cdb78af6c1b1158fecc853446ed4) | `01r1` | 1.141649 / 12.224193 | 0.988042 / 1.016780 | 1.009518 | 1.000265 / 1.016867 | 1.012691 | 0.996867 |
| 115 | [dd341a52](https://mlx.fast/api/submissions/dd341a52-a695-4d0d-8bdf-75ef44a9c74a) · [`d4cb1ae8`](https://github.com/Layr-Labs/mlxfast-challenge/commit/d4cb1ae8d63cd3e59169bc7685d85ca7970241e6) | `03r3` | 1.141627 / 12.059326 | 0.979523 / 1.033755 | 1.019922 | 0.999982 / 1.023439 | 1.017523 | 1.002357 |
| 116 | [8449082c](https://mlx.fast/api/submissions/8449082c-4dc2-4526-b3bd-69712c3b8a8e) · [`5b46c79c`](https://github.com/Layr-Labs/mlxfast-challenge/commit/5b46c79cfd8d6496989ba5977950e969ba4107ac) | `03r3` | 1.127961 / 11.648120 | 0.991391 / 1.070249 | 1.049965 | 0.997756 / 1.055442 | 1.040715 | 1.008888 |
| 117 | [df2a7483](https://mlx.fast/api/submissions/df2a7483-9c5b-4f4c-8a2f-9fee780515d7) · [`500d92a0`](https://github.com/Layr-Labs/mlxfast-challenge/commit/500d92a0f486a0297f312d8f4d38d5ab3b58f900) | `03r3` | 1.116583 / 11.070016 | 1.001494 / 1.126140 | 1.093595 | 1.001223 / 1.097331 | 1.072472 | 1.019695 |
| 118 | [214fd89a](https://mlx.fast/api/submissions/214fd89a-69af-4858-af54-8a801672c78d) · [`fc306048`](https://github.com/Layr-Labs/mlxfast-challenge/commit/fc306048e61c2cb7e56a8ff406db40adafcc8e79) | `03r1` | 1.100469 / 10.924149 | 1.014392 / 1.139870 | 1.107115 | 0.997185 / 1.101971 | 1.074785 | 1.030081 |
| 119 | [5139da0f](https://mlx.fast/api/submissions/5139da0f-ac51-4a81-b3d8-880a8a74f58f) · [`c5206993`](https://github.com/Layr-Labs/mlxfast-challenge/commit/c5206993d510ca0c50861b1f5d3d26030d76a22b) | `03r2` | 1.141624 / 11.038090 | 0.987329 / 1.130347 | 1.092759 | 0.995318 / 1.100313 | 1.073069 | 1.018349 |
| 120 | [db173215](https://mlx.fast/api/submissions/db173215-a7d7-4863-a333-8132c33be279) · [`7b2c9407`](https://github.com/Layr-Labs/mlxfast-challenge/commit/7b2c9407032e41408fbfaba94625d9c53b1934ca) | `03r2` | 1.127453 / 9.815259 | 0.999738 / 1.271171 | 1.197084 | 0.999508 / 1.186799 | 1.136919 | 1.052919 |
| 121 | [9847ff8f](https://mlx.fast/api/submissions/9847ff8f-918e-4988-ba2f-a1137d23784b) · [`e6596576`](https://github.com/Layr-Labs/mlxfast-challenge/commit/e65965761f34afbabc696b3eccdd363863edd480) | `04r3` | 1.128710 / 9.758540 | 0.993125 / 1.274202 | 1.197236 | 0.999209 / 1.190859 | 1.139750 | 1.050437 |
| 122 | [cc79cef2](https://mlx.fast/api/submissions/cc79cef2-8a0e-4bbd-aaba-bdaaae453249) · [`71b80b1f`](https://github.com/Layr-Labs/mlxfast-challenge/commit/71b80b1f33b01eb3edc871df85675cdbd6fe6320) | `01r2` | 1.116011 / 9.745206 | 1.022870 / 1.277220 | 1.208243 | 0.999073 / 1.185068 | 1.135552 | 1.064015 |
| 123 | [70a3ad4b](https://mlx.fast/api/submissions/70a3ad4b-70da-4b17-ab4f-388945dfee29) · [`60f436a2`](https://github.com/Layr-Labs/mlxfast-challenge/commit/60f436a2361eef72b207c2a3cf0d5b6984b8b0d1) | `03r4` | 1.125231 / 9.745632 | 1.002268 / 1.281427 | 1.205081 | 1.002804 / 1.191841 | 1.141479 | 1.055719 |
| 124 | [a0da915f](https://mlx.fast/api/submissions/a0da915f-450a-4063-bf8e-ec1661f4a661) · [`70fe340b`](https://github.com/Layr-Labs/mlxfast-challenge/commit/70fe340becd16cf5efa40884963283e6a834c84b) | `05` | 1.126696 / 9.662284 | 1.000763 / 1.286105 | 1.207926 | 1.006472 / 1.215003 | 1.159133 | 1.042094 |
| 125 | [4173c401](https://mlx.fast/api/submissions/4173c401-0f25-41fd-bec7-cdea22a1aac3) · [`13496639`](https://github.com/Layr-Labs/mlxfast-challenge/commit/1349663988dacafe7ee4b5b11832a4891d1aa5cc) | `05` | 1.138920 / 9.661438 | 0.990022 / 1.286218 | 1.204750 | 1.006343 / 1.219444 | 1.162273 | 1.036547 |
| 126 | [05e7894f](https://mlx.fast/api/submissions/05e7894f-0eaf-4f6d-8622-499d1e44185d) · [`7702fab8`](https://github.com/Layr-Labs/mlxfast-challenge/commit/7702fab8a41fe2f4ff2ae281beeb1548b31e3406) | `05` | 1.123800 / 10.732805 | 1.003342 / 1.157825 | 1.117106 | 1.005835 / 1.224572 | 1.165789 | 0.958241 |

All 15 candidate attempts passed the local 1,025-step exact-token
correctness check with `max_abs_diff = 0`. They used the same nine-file,
21,568,891,382-byte transformed weight set. These are public/local checks,
not the organizer's hidden M5 correctness, GPQA, semantic, or acceptance-band
gates.

## What each snapshot did

The leaderboard is chronological, but the source lineage branches. Rank 113
replaces 112; ranks 114–116 are alternatives based on 113; ranks 118–120 are
alternatives based on 117. Only the 120→126 tail is conceptually linear.

```text
111
├── 112  metadata indexing + shared attention carriers
└── 113  metadata indexing only
    ├── 114  consumer-local exact top-8
    ├── 115  SG4/PF2 affine QKV
    └── 116  NVFP4 boundary 32 → 24
        └── 117  NVFP4 boundary 24 → 17
            ├── 118  top-8 + unpacked R1 QMV + SG4/PF2
            ├── 119  producer-computed router keys
            └── 120  NVFP4 boundary 17 → 0 + eligible fusion
                └── 121  restore producer-computed router keys
                    └── 122  exact fused-tail scale/sign fold
                        └── 123  exact fused split-K prefill
                            └── 124  separate norm/QKV/gate
                                └── 125  uchar4 loads + layer-0 async
                                    └── 126  one-row-per-SIMD down retile
```

| Rank | Actual base | Mechanism and outcome interpretation |
|---:|---:|---|
| 112 | 111 | Replaced raw BF16 affine `(scale, bias)` pairs with lossless UInt16 table indices and shared tiny immutable attention arrays. A successful bundle; carrier sharing was not independently priced. |
| 113 | 111 | Re-landed only the exact metadata lookup, with a raw fallback above 65,536 entries. This is the cleaner evidence for the indexing idea and replaces rank 112. |
| 114 | 113 | Recomputed strict-total-order top-8 inside routed QMV so it could run alongside the standalone selector, removing one serialized dependency window without changing later consumers. |
| 115 | 113 | Changed affine RMS/QKV ownership to four SIMD groups and jointly reduced prefetch depth to two. The combination was positive; the earlier SG4/PF4 geometry was not. |
| 116 | 113 | Changed attention layers 24–39 from group-32 affine INT8 to checkpoint group-16 NVFP4, roughly halving QKV/O weight bytes for eight additional layers. |
| 117 | 116 | Moved the NVFP4 start boundary from layer 24 to layer 17. Nearby boundaries did not pass monotonically, so this is also evidence to test exact-token boundaries individually. |
| 118 | 117 | Composed exact top-8, an unpacked one-row routed QMV, and SG4/PF2. This is a three-mechanism snapshot, not an isolated effect. |
| 119 | 117 | Computed corrected router ordinals once in their existing producer and reused them across high-fan-out routed-QMV consumers. It replaces rank 118 rather than adding to it. |
| 120 | 117 | Moved all 40 attention layers to checkpoint NVFP4 and made fusion eligibility depend on the selected wire format. This is the dominant result in the window, but it overwrote rank 119's router keys. |
| 121 | 120 | Restored the producer-computed router keys on the all-NVFP4 source. The tiny official delta understates the maintenance lesson: later overlays can silently erase orthogonal wins. |
| 122 | 121 | Carried the E4M3 sign directly into half bits and folded exact powers of two in the fused NVFP4 tail. Correctness support is strong, causal timing support is weak, and rank 124 later makes this path default-off. |
| 123 | 122 | Fused split-K prefill while exactly emulating intermediate BF16 rounding and FP32 reduction order, removing an intermediate surface and reductions. Dormant LM-head arms were removed only for source budget. |
| 124 | 123 | Disabled fused norm/QKV/gate by default. The fused kernel repeated the same 2,048-element RMS reduction per output tile; separate RMSNorm computes one 4 KiB row once for all consumers. This is a particularly credible un-fusion win. |
| 125 | 124 | Combined aligned `uchar4` affine-code loads with `asyncEval` after layer-0 QKV/gate construction. Both had independent positive M5 candidate-phase evidence, though this M4 sample does not isolate a gain. |
| 126 | 125 | Retiled fused routed/shared down plus residual from four output rows to one per SIMD and quadrupled the grid. The arithmetic is unchanged, but the M4/M5 sign reversal exposes architecture-sensitive occupancy. |

## Detailed transfer learnings

### 1. Rank 118 is better on M4 cumulatively, but that is not its marginal win

The AWS result quoted most often is:

```text
Prefill: 1.116307 → 1.100469 ms/token  (1.0144×)
Decode:  12.452107 → 10.924149 ms/token (1.1399×)
Weighted host-local index:               1.1071×
```

Against rank 111, the corresponding official raw M5 comparison is 0.9972×
prefill, 1.1020× decode, and 1.0748× weighted. The M4 cumulative result is
therefore about 3.0% stronger on the weighted ratio, driven primarily by a
13.99% M4 decode gain versus 10.20% on M5.

That **does not** mean the three rank-118 mechanisms produced a 10.7% isolated
gain. Rank 118 inherits the much larger NVFP4 rollout through rank 117. Its
official marginal weighted movement over conceptual base rank 117 is only
about 0.2% using normalized raw candidate times. Comparing the independent M4
117 and 118 cohorts suggests a larger roughly 1.2% movement, but that is a
cross-host comparison and is not a controlled A/B. Treat rank 118 as evidence
that the complete stack transfers, then re-isolate its three pieces before
adopting any one of them.

### 2. Byte reduction is the strongest portable signal

The inherited affine INT8 attention representation costs about 1.125 bytes
per parameter; checkpoint NVFP4 costs about 0.5625. Ranks 116, 117, and 120
progressively widen that representation without inventing new approximate
weights. Their M4 cumulative decode ratios climb from 1.0702× to 1.1261× to
1.2712×, in the same order as the official 1.0554×, 1.0973×, and 1.1868×.

This is exactly the kind of work for which M4 is useful: the performance
mechanism is fewer bytes and less conversion, not a fragile occupancy point.
Start our campaign from the all-layer-NVFP4 endpoint; do not rediscover the
32→24→17→0 ladder.

### 3. Optimize repeated work, not kernel count

Rank 123 demonstrates good fusion: it removes a materialized intermediate and
reduction dispatches while reproducing the original arithmetic boundaries.
Rank 124 demonstrates good un-fusion: the fused attention input kernel
duplicated RMSNorm across every output tile. The reusable lesson is to count
producer multiplicity, input rereads, barriers, live registers, and occupancy,
not just launches.

Rank 124's large cumulative M4 result agrees with the M5 direction. Ranks 123
and 124 ran in different fresh-baseline cohorts, so their roughly 0.2% index
difference is not a controlled marginal measurement. The official lineage and
the repeated-work analysis remain the stronger causal evidence for un-fusion.

### 4. Exactness techniques are reusable even when their hot path is not

Several successful changes preserve behavior by construction:

- bit-cast exact BF16 metadata payloads rather than recomputing values;
- retain strict total-order tie handling in router top-8;
- preserve BF16 materialization points and FP32 partition reduction order;
- exhaustively verify all 256 E4M3 scale bytes;
- provide a same-binary selector that restores the previous path.

These proof patterns are more durable than any one micro-optimization. At
rank 126, some early paths are superseded: affine QKV metadata and SG4 affine
QKV no longer own the default all-NVFP4 path, while rank 122's fused-tail
change is default-off after rank 124.

### 5. Prefill movements at this scale are noisy

Most of the 112–126 window is decode-led. M4 prefill ratios fluctuate by
roughly one or two percent across candidates even when the named mechanism is
decode-only, while the official raw prefill differences are generally below
one percent. Interpret a single prefill movement as supporting evidence, not
causal proof. The 75% decode weight in the score makes the large decode trends
more decision-relevant.

### 6. Kernel geometry is generation-specific

Rank 126 reduces per-SIMD live accumulators and exposes more independent work.
That is slightly favorable on the M5 Max and sharply unfavorable on this M4
Pro. The complete rank-126 snapshot still beats rank 111 on M4 because it
inherits the earlier stack, but the 125→126 change itself is a regression.

Use M4 for functional validation of geometry candidates and for large effects,
but require M5 measurements for:

- rows or outputs per SIMD group;
- threadgroup and split-K ownership;
- register-prefetch depth and live-state tradeoffs;
- `_nax` variants and M5-specific dispatch thresholds; and
- any claimed win below about one percent.

## Recommended foundation for our campaign

1. Start from the latest proven source, not by stacking all 15 patches. The
   active rank-126 foundation includes all-layer NVFP4, producer-computed
   router ordinals, exact split-K prefill, separate norm/QKV/gate, aligned
   affine-code loads, and the layer-0 enqueue. Keep the rank-126 down-kernel
   geometry behind a generation-specific selector until it is revalidated.
2. Preserve an active-path manifest after every experiment: defaults, guards,
   qualifying shapes, formats, and selectors. Rank 120 erasing the rank-119
   router optimization is the warning case.
3. Use M4 first for byte/layout changes, exact dependency-graph work, removal
   of duplicated computation, KV-cache work, and transform metadata.
4. Build same-binary controls for all scheduling changes. Small numbers need
   repeated cool brackets; a new executable or pipeline cache can otherwise
   be mistaken for a mechanism effect.
5. Keep arithmetic contracts explicit. Exact output tokens depend on payload
   bits, signed zero, BF16 boundaries, tie rules, and reduction order.
6. Keep search breadth. The all-layer checkpoint representation is already at
   the legal attention byte floor. Promising open territory includes KV-cache
   handling, attention and MoE epilogues, MLX scheduling, graph-construction
   overlap, duplicated routing work, and transform-produced runtime metadata.

The leaderboard work gives us strong priors and a tested proof vocabulary. It
should save us from repeating settled searches without narrowing the campaign
to other people's exact kernel choices.

## Infrastructure, evidence, and cost

AWS did not offer an EC2 M5 Mac type, and live M4 Max capacity was unavailable,
so the campaign used five `mac-m4pro.metal` Dedicated Hosts in `us-east-1`.
Each was a 48 GB Apple M4 Pro Mac mini (`Mac16,11`) running macOS 26.5.2,
Xcode 26.6, Swift 6.3.3, and the repository's automatic low-memory startup
profile. Each root disk was 200 GiB gp3 at 10,000 IOPS / 400 MB/s.

Bootstrap assets were hash-pinned in a private S3 bucket and reached through a
VPC endpoint and instance role; credentials were not embedded on the Macs.
One-shot system LaunchDaemons survived SSH and Codex disconnection without
restart loops. A stale single-IP security-group allowlist temporarily cut
controller SSH after the operator's public IP changed; the launchd jobs kept
running, and access was restored with a second narrow `/32` rule. The EC2
guests expose no supported SMC fan control, so the
recorded fan policy is honestly `none`; responsive `macmon` telemetry and the
40 °C thermal gates remained mandatory. Every completed row is attempt 1 in
the validated cohort view and has a retained score hash, transformed-weight
hash, run spec, preflight samples, host record, and benchmark log.

The final validator accepted eight fresh-baseline cohorts covering every rank
exactly once. Rank 121 was recovered from an intentionally interrupted cohort;
its incomplete rank-122 directory was retained in the raw archive but excluded
from the validated view. Rank 122 and the backup rank 123 completed on separate
hosts. The parallel slot05 rank-123 attempt timed out cleanly at the 40 °C
launch gate before loading the model and contributed no score.

EC2 Mac Dedicated Hosts carry a 24-hour minimum. At the observed
`mac-m4pro.metal` price of $1.97/hour, five hosts cost $236.40 before storage,
IPv4, tax, and egress. The campaign estimate including five provisioned root
volumes and public IPv4 is approximately **$247.19**. Dedicated Hosts may be
released no earlier than 2026-08-04 14:39:11 UTC; instance termination alone
does not stop host billing. Termination was requested for all five instances
after artifact validation on 2026-08-03; four were still completing AWS's Mac
shutdown/scrub transition at handoff. The Dedicated Hosts remain until that
release time.

Raw artifacts live only under the ignored local tree
`quality-results/aws-top15-20260803/collected/`, with the exact 15-row validator
output in the adjacent ignored `controller/summary.json` and `summary.tsv`.
They must not be uploaded to the competition service.
