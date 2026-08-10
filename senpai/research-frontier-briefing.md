# MLXFast emergency research-frontier briefing

**Snapshot:** 2026-08-10 20:00 UTC  
**Time posture:** approximately 24 hours remain in the competition.  
**Purpose:** give a fresh Senpai advisor enough durable scientific context to
resume quickly without inheriting a long, noisy conversation.

Read [`program.md`](program.md) first. This document is a map of evidence, not a
rigid script. Verify a claim against the linked PR, source, or official receipt
before relying on it, and use scientific judgment when new evidence conflicts
with an old conclusion. A negative result closes only the tested mechanism and
configuration; it does not prohibit a genuinely different hypothesis.

## Executive state

The maintained fork base is
`1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`. It contains the exact submitted
frontier promoted by official receipt `cc6ddc1`, imported from organizer commit
`c5b0a13c`. Use the current recorded integration base required by the branch's
submission wrapper; do not substitute a candidate commit for `BASE_SHA`.

The official leader is:

| Receipt | Commit | Score | Decode | Prefill |
|---|---|---:|---:|---:|
| `cc6ddc1` | `c5b0a13c` | **2.61650354** | **202.837 TPS** | **5,314.658 TPS** |

Our strongest recent official candidate is Cedar receipt `e27f1ce`:

| Receipt | Score | Decode | Prefill | Gap to leader |
|---|---:|---:|---:|---:|
| `e27f1ce` | **2.60664970** | **204.47 TPS** | **5,319.80 TPS** | **0.378%** |

`e27f1ce` passed all official correctness and behavior gates: 1,344 checked
steps, exact checked tokens, GPQA TTFT and semantic GPQA, both component floors,
and the memory gate. It was rejected only because its same-session score did not
beat the record. Its raw candidate phases are about 0.63% better, weighted, than
the leader receipt's raw phases, although cross-session raw comparison is only
prioritization evidence. The campaign is close enough that one real 0.3-0.5%
mechanism composed with this tree could produce a robust lead.

The score fields answer different questions:

- `officialScore` decides the leaderboard and includes the paired baseline draw.
- Candidate seconds/token and a common-baseline normalization are more useful
  for comparing candidate merit across official sessions.
- A `rejected` receipt with green gates normally means only that it did not beat
  the current best. It is not a correctness failure.
- Raw TPS from different sessions is never a causal A/B estimate.

## What is already in the promoted frontier

The current fork `main` is cumulative. Do not propose an idea merely because it
appears in a public note; first verify whether the code is already present.

### Active-64 exact router tournament

The current leader's main new mechanism is in
`Sources/MLXFastModel/LagunaRuntimeModel.swift`:

1. Partition 256 router values into eight blocks of 32.
2. Retain the exact local Top-8 from each block, yielding 64 finalists.
3. Sort one 64-entry finalist set with lanes 0-63 rather than four redundant
   copies across 256 lanes.
4. Preserve exact score ordering and expert-index tie-breaking.

This shrinks cross-SIMD scratch from 256 to 64 entries and uses only two SIMD
groups for the final tournament. It is exact and useful. The author's
19-receipt analysis nevertheless estimates only about 0.15% mean raw merit;
the promoted score also benefited from a favorable paired baseline.

### Other cumulative frontier mechanisms

- **Packed router ordinal/index exchange** (`a13fdca2`): carry `(ordinal,
  index)` in one `uint2` shuffle rather than two scalar exchanges. Active-64
  bypasses part of its old decode benefit.
- **Pairwise prefill scale layouts and conversion hoisting** (`ab17a99f`):
  represent scales pairwise and convert each physical pair once in the M5 NAX
  loader. This is M5-prefill-specific.
- **Shared-expert scale halving and four-row down staging** (`708500f7`): exact
  group-32 scale-plane halving with its first-SIMD exception, fixed-K NAX
  barrier removal, and four-row routed/shared down load staging.
- **Zero-copy routed-prefill scales** (`26b46535`): expose compact scales through
  a narrowly certified zero-stride view, guarded by exact shape, dtype, stride,
  and offset checks. Its isolated official evidence suggested about 0.72% raw
  prefill gain with a small decode cost.
- **Two-tier exact LM-head screening:** the live tree uses a certified coarse
  INT5 representation and fused refinement to avoid reading most of the full
  BF16 output head.
- **Existing Laguna fusions and schedules:** the tree already contains many
  routed/shared gate-up, SwiGLU, down-residual, attention, Q/K norm, RoPE,
  quantized projection, route-scatter, and async-staging optimizations. Inspect
  the live default-on path rather than assuming an apparent source seam is
  still unfused.

## Public competitor evidence

This snapshot queried all 1,792 public submissions and their notes: 147 were
accepted, 1,077 rejected, and 568 failed. No receipt was validating at the
snapshot. Source is authoritative when a public note and the promoted commit
disagree.

### Promoted leaderboard frontier

| Rank | Solver | Receipt / commit | Score | Decode TPS | Prefill TPS |
|---:|---|---|---:|---:|---:|
| 1 | a-github-name | `cc6ddc1` / `c5b0a13c` | **2.616504** | 202.837 | 5,314.658 |
| 2 | yudduy | `2054d45` / `01e247a7` | 2.606306 | 203.529 | 5,297.760 |
| 3 | fyrsta7 | `b9ccb0b` / `a13fdca2` | 2.604024 | 203.447 | 5,314.362 |
| 4 | a-github-name | `f2b7ccc` / `ab17a99f` | 2.597875 | 203.279 | 5,310.866 |
| 5 | lBroth | `6718326` / `708500f7` | 2.597383 | 203.699 | 5,267.095 |
| 6 | a-github-name | `db8b4df` / `26b46535` | 2.590186 | 203.063 | 5,263.821 |
| 7 | Morgan/Senpai | `97a5090` / `3e165fa5` | 2.588828 | 203.734 | 5,230.107 |

### Strong external near-misses after the leader

These raw phase comparisons span official sessions. Use them to choose what to
reconstruct, not as proof of an effect.

| Receipt | Claimed mechanism | Decode TPS | Prefill TPS | Weighted raw vs leader |
|---|---|---:|---:|---:|
| `fefaed8` | Active-64 scalar replay | 204.668 | 5,313.576 | **+0.671%** |
| `1a7a0ea` | Hybrid T5 router + shared carrier | 204.240 | 5,330.971 | **+0.595%** |
| `1e68b6a` | Allocator cache 32 -> 48 GiB | 204.293 | 5,321.547 | +0.570% |
| `aadbda2` | Hybrid T5 router | 203.984 | 5,314.355 | +0.422% |
| `6183ceb` | Packed route-result handoff | 203.776 | 5,327.333 | +0.407% |
| `bb96b0a` | Router scratch-lifetime reduction | 203.642 | 5,320.667 | +0.326% |

#### Hybrid T5 router selector: strongest distinct external lead

Receipts `aadbda2` and `1a7a0ea` change only
`LagunaRuntimeModel.swift`:

- Top-8 slots 0-4 use the accepted rescan.
- Slots 5-7 use a 19-comparator local sort and 32-lane merge.
- The better variant carries the result through one shared
  `uint2 top8_pairs[8]` whose lifetime ends before QMV input storage.
- Exact comparison and tie-breaking are preserved.

The author reports roughly 1.8-2.0% in local full-body paired testing, and its
official raw phases are the strongest reusable signal after the leader.
Compiler allocation, register pressure, and scratch lifetime are the main
risks. Reconstruct it cleanly on the current frontier; do not copy an unknown
tree wholesale.

#### Packed route-result handoff

Receipt `6183ceb` publishes eight expert indices and exact pre-bias FP32 scores
directly from the packed routed gate/up kernel so the sparse block can skip a
standalone selector under strict guards. It claims to remove 39
selector/normalizer launches, but adds dependency and payload pressure. Treat it
as an alternative routing architecture that may conflict with active-64 or T5,
not automatically as a stackable addition.

#### Active-64 scalar replay

`fefaed8` is effectively another measurement of the current leader mechanism,
not a distinct idea. Its strong raw result supports active-64 and also
illustrates how strongly paired baseline draws affect official scores.

#### Allocator cache increase

`1e68b6a` only changes `Memory.cacheLimit` from 32 to 48 GiB. It supplied no
allocator-churn evidence and finished rejected at score 2.582757. Do not spend a
lane on it without counters showing cache eviction or allocation work.

#### Note/source contradiction: grouped SDPA is not yet evidence

Receipt `2054d45` says it groups three or four query heads per KV head in a
KV-native SDPA schedule. Its promoted commit `01e247a7` is byte-identical to
its parent and live `sdpa_vector.h` still uses pair-heads = 2. The note therefore
describes an unvalidated hypothesis, not a landed frontier mechanism. It may be
worth a clean implementation later, but it has no positive source-backed result.

### Lower-priority public ideas

- QKV NVFP4 depth-one code prefetch: about -0.12% raw weighted.
- Compact lane-major LM-head scales: about -0.05%.
- Gate GEMV folded into QKV in the tested public form: about -0.11%.
- `n_cols` 4 -> 2 prefill-tail result: confounded by reverting active-64.
- Producer-key reuse plus persistent P8 routing: approximately neutral
  officially; isolate components if revisited.
- Precomputed LM-head activation-group L1 sums: confounded by unrelated runtime
  changes and slightly slower; only a clean LM-head-only reconstruction would
  resolve it.

## Our campaign: official and promoted results

### Maple

- **PR #80 / receipt `97a5090`: promoted.** Exact attention scale-plane
  compression removed 27,698,336 bytes per decode step and improved normalized
  candidate merit by about 0.86-0.91%. Official score 2.58882784.
- **PR #35 / receipt `0d123661`: strong non-promotion.** Narrow NVFP4 scale
  codes measured about +1.0512% normalized merit and passed gates, but the
  paired baseline draw prevented promotion.
- **PR #20:** a small positive LM-head signal, approximately +0.455%
  normalized.
- Maple's best historical normalized candidate merit was about 2.590559
  (`25e1f18e`, tree `4b0e051b`). Later exact-tree work showed that part of the
  apparent difference from subsequent trees was receipt noise, not a reusable
  source delta.

### Cedar

- **PR #549:** retiled the exact one-token embedding/RoPE atlas producer from
  512 to 128 lanes.
- **PR #604: merged local winner.** Reused the proven one-token atlas
  eligibility result to skip both attention-mask builders only when no mask is
  required. It added 158 bytes, passed 130-step and 1,025-step checks, and
  measured geometric-mean speedups of 1.003216 prefill, 1.004565 decode, and
  **1.004228 weighted (+0.4228%)** across three matched pairs.
- **Receipt `e27f1ce`:** the composed #549 + #604 candidate achieved score
  2.60664970, passed all gates, and missed promotion by 0.378%.

Do not retry an identical receipt merely to sample session noise. Improve the
tree, submit a distinct correctness-green candidate when justified, and keep
working while validation is occupied.

## Maple experiment trajectory

Maple ran a very broad programme. Its branch-local
`research/CURRENT_RESEARCH_STATE.md` and archives contain the full per-round
ledger; the summary below extracts the durable decisions.

### Measurement and transfer laws

- M4 threadgroup geometry does not reliably predict M5. PR #7 measured +7.32%
  decode on a 20-core M4 and approximately 0% on the M5 because wave
  quantization changed with core count.
- M4 Pro reports Apple GPU generation 16 and does not execute the M5 `_nax`
  path. About 94.2% of the M4 prefill GPU time is in functions the ranked M5
  does not use. M4 prefill remains useful for correctness and reachability, not
  ranked timing of NAX changes.
- Steady one-token decode is host-independent enough for directional M4
  testing, but still needs M5 confirmation for marginal or geometry-sensitive
  effects.
- Current score decomposition gives approximately 0.638 elasticity to the
  steady decode step and 0.362 to the 512-token seed forward. Decode TPS blends
  both; decompose `S` and `T` when attributing an official result.
- Official baseline prefill is substantially noisier than decode. Candidate
  merit normalized to a common baseline has historically been much less noisy
  than `officialScore`, but it still does not authorize repeated identical
  submissions.
- Maple's latest M4 A/A certification measured -0.0328% with CI95
  [-0.1099%, +0.0442%]; selected sweep winners need unbiased remeasurement.

### NVFP4 scale and metadata reduction

This family produced Maple's largest promoted win (#80). It is now mostly
exhausted:

- Quantization metadata is about 3.8468% of decode traffic.
- The best remaining bit-preserving encoding found saved 1.1538% of total
  bytes, below the campaign's useful threshold.
- Approximately 96.15% of remaining decode traffic is weight payload.
- Generic metadata compression without a new byte-level construction should
  not be reopened.

### LM-head

- #20 produced a small positive official signal.
- Deeper hierarchical screens, coarse-read elimination, dense re-encoding, and
  cascade fusion were null or negative.
- The current two-tier INT5 head is close to byte-optimal on the observed
  decode path.
- A genuinely new certificate or representation may still be research, but
  generic int4/pruning sweeps repeat closed work.

### Attention and QKV

- The float4 attention merge epilogue was a small real restoration: about
  +0.2358% locally and roughly 15.6 microseconds per step in a later direct
  measure.
- QKV lane-major packing's selected -36.9 microsecond result did not survive
  unbiased replication: +0.0328%, CI [-0.2338%, +0.2994%].
- Input-RMSNorm -> QKV fusion was null: +8.61 microseconds per step, CI
  [-17.71, +35.02].
- Split-K, KV splitting, attention threadgroup doubling, wider loads, and the
  tested prefetch/pipeline variants were negative or below threshold.
- Broad attention latency-headroom claims have repeatedly failed. A new
  attention proposal needs a specific dependency, byte, or exact scheduling
  mechanism rather than another generic depth sweep.

### MoE, router, and expert kernels

- Wide QMV codes regressed score by about 0.5363%.
- Routed gate/up staging depth is already shipped; deleting it was about
  -0.038% with a confidence interval spanning zero. The simple depth axis is
  closed.
- Router-weight prefetch looked positive in per-kernel labels and negative
  end-to-end. The existing official pairs make the tested toggle a null.
- QMV/GEMV work is predominantly unique-byte bandwidth-bound; fixed-byte
  instruction and occupancy tuning has usually been neutral or negative.
- Expert gather-GEMM geometry remains interesting only on the M5 NAX path;
  the M4 fleet cannot time that implementation.

### Prefill and NAX

- NAX BN reuse was decisively negative on M5, regressing candidate prefill by
  about 1.166 ms.
- Gather double buffering, staging, swizzle/tile changes, and generic prefill
  dispatch reduction were negative or unidentifiable.
- M5-only prefill ideas should be supported by static path/byte analysis and
  then settled with an official M5 candidate, not inferred from M4 timing.

### Dispatch, barriers, concurrency, and fusion

- The steady decode step has about 408-411 dispatches, but dispatch count is
  not a cost proxy. Byte volume and actual dependency are more predictive.
- At least 70.6% of decode is true serial data dependence. Legal reordering
  improved the dependency schedule by only 1.3003 microseconds per step.
- Decode read multiplicity is about 1.00177; 99.42% of traffic is read once.
  Generic fusion for duplicate-byte elimination is therefore closed.
- MLX already uses concurrent compute encoders and inserts barriers for RAW
  hazards; independent sibling dispatches may overlap without manual work.
- PR #660 directly measured about **0.4478 M4 microseconds per added dispatch**,
  CI [0.4006, 0.4950], roughly 4.2 times below the old assumed price. Forty
  removals alone are worth only about 0.15% score.
- PR #660 found barrier price indistinguishable from zero. A useful fusion must
  eliminate real computation/traffic or preserve an intermediate in fast
  storage; launch-count aesthetics are insufficient.

### Restoration and integration

Adopting newer organizer frontiers reverted three earlier Maple changes. The
campaign restored the float4 epilogue, four-deep ring, and router prefetch, but
the composed tree measured only about +0.037% +/- 0.056% on M5. The apparent
remaining 19-microsecond residual later fell to about 1.3 sigma. Do not assume a
large missing restoration without re-deriving the exact source delta.

## Cedar experiment trajectory

Cedar's best work was a small exact runtime simplification (#604) composed with
the atlas retile. Its later programme became increasingly dominated by
instrumentation, provenance, and evidence contracts. Those artifacts may be
useful, but they have not produced a faster candidate and should not consume
the whole six-student fleet during the final day.

### Important exact negatives and bounds

- **#602 virtual-half split-K:** isolated shared-expert win around 1.5%, but
  full-model AB was 0.999696 weighted and BA 0.995462; reverted.
- **#607 OProj input staging:** bit-exact and reached the intended path, but
  isolated H48 speedup was 0.988265; stopped.
- **#610 token-strip-4 Q/K norm+RoPE:** exact over more than 50 million outputs;
  gains reversed strongly with order; reverted.
- **#611 cross-layer sorted-MoE-tail/RMS handoff:** isolated chain improved
  1.0922x, but full prefill regressed to 0.989745x; reverted.
- **#613 packed Q/K norm weights:** resident ABI improved 1.016262x, but
  full-model weighted result was 0.993963x; not promoted.
- **#618 terminal prefill Q/K norm+RoPE:** isolated 1.233x, but one call
  projected only 1.000084-1.000113x whole prefill; below Amdahl threshold.
- **#621 invocation-local full-attention params:** saved only about 5.4
  microseconds per decode step and regressed in the full-model screen.
- **#623 one-512-threadgroup sorted MoE tail:** ABBA strongly positive,
  1.0802x isolated, but BAAB reversed; reverted.
- **#624 LM-head 3+2 repartition:** full-model weighted 0.978462x; reverted.
- **#627/#631 four-row prefill router and input-RMS:** large isolated ratios
  but only 0.0211% and 0.0875% projected whole-prefill gains.
- **#628 zero correction-bias specialization:** repeated 1.02687x isolated
  decode signal vanished end to end; full weighted 0.999172x.
- **#635 packed Q/K norm decode ABI:** exact and positive in both isolated
  orders, but only 1.001174x projected decode, below its threshold.
- **#638 routed gate/up load halving:** compiler-realized and exact, but about
  249.7 microseconds per token slower; projected decode 0.980922x.
- **#640 shared-prefill SwiGLU epilogue:** exact, removed about 76 MiB and 38
  launches, and improved the isolated segment 1.028-1.029x. Whole-prefill
  projection was only 1.000581-1.000636x, about 0.015% weighted.
- **#641 Q/K vector reuse:** compiler-realized and exact; 0.999550x regression.
- **#643 OProj codeword vector load:** forward saved 19.82 microseconds with CI
  crossing zero; reverse regressed 4.931 microseconds, 0.996736x.
- **#646 common full-attention attribution:** found 2.726 ms of synchronized
  exposure but no exact removable successor. Exposure is not removable cost.
- **#658 official repeatability audit:** among 1,791 attempts, all 60 complete
  current-contract exact-payload groups were singletons; fine repeatability is
  not identifiable from this corpus.
- **#662 C-vector lifetime:** only 0.684-0.936 microseconds/token lower bound;
  no safe editable common owner.
- **#665/#668 source headroom:** 30,796 bytes of plain comments could be
  removed, but authoritative M5/transform evidence was unavailable, so
  production was restored. Headroom is useful only when a real candidate needs
  it.
- **#669 exact promotion margin:** an exact-e27 successor needs more than
  1.003780272x weighted improvement; decode-only tie needs 1.005043536x and
  24.543 microseconds/token; prefill-only tie needs 1.015207047x and 2.816
  microseconds/token.

PRs #670-#678 mostly concern selector/launcher provenance, transform-verifier
coverage, evidence schemas, and filesystem hardening. They may improve future
scientific reliability, but most do not touch the scored path. Reconcile and
close or preserve their durable results; do not mistake them for speed work.

## Correctness and measurement caveats

- The official M5 Max is authoritative. M4 decode can be directional; most M4
  prefill runs a different kernel family.
- A fixture `golden_hash` identifies the fixture, not candidate/reference
  numerical equality. Read what each test actually proves.
- Arithmetic reorderings need a source-level identity proof or a valid margin
  certificate, not only one matching token trace.
- Do not mix M4 and M5 microseconds, marginal receipt differentials and whole
  censuses, kernel-label and end-to-end time, or selected sweep winners and
  prespecified estimates.
- Use a fresh unchanged baseline on the same host and epoch. Respect the
  thermal gate and run only one model-holding benchmark process per Mac.
- The editable surface, per-file limits, and total byte budget are hard gates.
  Default-off scaffolding still consumes submission bytes.
- The M5 receipt is a measurement instrument as well as the ranking decision.
  A correctness-green candidate with a plausible material gain need not be
  proven to exceed the entire gap on M4 before one official experiment.
- If validation capacity is occupied, preserve the exact candidate and manage
  its retry without spamming; continue research while waiting.

## Do not repeat unchanged

1. Generic dispatch-count reduction or barrier/encoder rescheduling without
   removing real work.
2. Input-RMSNorm -> QKV fusion, router-tournament fusion, split-K attention, KV
   splitting, attention TG doubling, or generic attention depth sweeps already
   represented by the negative experiments above.
3. Routed gate/up staging-depth changes or wide-code QMV.
4. Generic metadata compression, redundant-read elimination, and generic
   decode fusion for bytes.
5. LM-head int4/pruning variants dominated by the current two-tier path.
6. M4 timing of NAX prefill as evidence of ranked M5 performance.
7. Repeated byte-identical official submissions to mine session noise.
8. The best arm from a sweep without fresh unbiased confirmation.
9. Fleet-wide provenance or process audits that do not unlock a concrete
   scored-path experiment.
10. A tiny isolated ratio without pricing the call count and whole-model Amdahl
    effect.

## Highest-value unresolved leads

These are starting points, not mandatory assignments. Run independent work
where possible and let new source inspection supersede this list.

### 1. Reconstruct the external T5/shared-carrier router

This is the strongest distinct external result. Implement only the selector on
the current frontier, tightly bound the shared carrier lifetime, preserve exact
ordering/ties, inspect compiler resources, and measure it independently. If it
wins, compose it with the #549 + #604 Cedar tree.

### 2. Direct commit-cadence experiment

Maple PR #660 accidentally observed a negative intercept of about 3.76-4.21
microseconds per layer, or 150-168 microseconds per step, when adding one commit
boundary per layer. That extrapolates to roughly 1.7% faster decode, but it is
not yet a result: N=0 was extrapolated from a 160/1,200-dispatch ladder and the
change was confounded with tape splitting.

Test commit/`asyncEval` cadence directly with zero added kernels and identical
work. This is Maple's cleanest unexplained high-upside signal.

### 3. Packed route-result handoff

Reconstruct `6183ceb` as an isolated alternative to standalone selection.
Compare it separately with active-64 before considering combination with T5;
the two may compete for the same work and scratch lifetime.

### 4. Family-E sibling fusion, carefully scoped

PR #660 identified a structural possibility: fold gate softplus into a sibling
QKV dispatch. Both read the same normalized input and neither consumes the
other's output. The dispatch-removal component alone is only about 0.15%; the
unverified thesis is that removing the standalone gate work could save much
more.

The risk is severe: a register union that slows thousands of QKV threadgroups
can overwhelm the handful of gate groups removed. Preserve gate arithmetic
exactly, keep whole-threadgroup ownership, guard activation state, inspect
spills/resources, and measure QKV tile time before trusting an end-to-end result.

### 5. Compose independent proven work

The clearest candidate composition is a clean router win plus Cedar #549/#604.
Maple #80 is already in the cumulative promoted lineage, so verify ancestry
rather than attempting to reapply it.

### 6. M5-only NAX opportunity

Expert gather-GEMM still contains plausible M5-only leverage, including the
observed one-of-four SIMDgroup-MMA deficit. The M4 fleet cannot measure that
path. Pursue only a strong static mechanism with exact guards and use an
official M5 receipt to settle it.

### 7. Grouped SDPA, as an unvalidated hypothesis

Three/four-query-head KV-native grouping may reduce duplicated KV work, but the
public note did not ship matching code. It is lower confidence than T5. If
tested, isolate it, preserve accumulation behavior, and watch register and
threadgroup-memory pressure.

## Final-day operating posture

- First reconcile the advisor branch, current open PRs, and already completed
  student results so no useful candidate is stranded.
- Use all six students for independent, falsifiable hypotheses and decisive
  experiments. Do not spend the whole fleet on one speculative family or on
  meta-process work.
- Favor exact work removal, byte reduction, or a specific dependency change
  over cosmetic launch-count or occupancy changes.
- Close weak arms promptly, but do not impose an artificial proof bar that
  prevents a promising correctness-green candidate from reaching the official
  M5 instrument.
- Read the public note and promoted source whenever a new frontier is accepted;
  compare it with this closed-family map and look for orthogonal composition.
- Keep public PR results and branch-local research notes concise and current so
  the next turn can reason from durable evidence rather than conversation
  memory.
- Move quickly. Candidate merit, correct official submissions, and independent
  experimental throughput matter more now than further process elaboration.

## Durable source index

- Maple's full rolling ledger: `research/CURRENT_RESEARCH_STATE.md` on the
  Maple advisor branch.
- Cedar's full rolling ledger: `research/CURRENT_RESEARCH_STATE.md` on the
  Cedar advisor branch.
- Experiment and submission procedure: [`experiment-runbook.md`](experiment-runbook.md).
- Competition contract: [`../AGENTS.md`](../AGENTS.md) and `../TASK.md`.
- Official CLI usage and public research notes: `mlxfast submissions --all`,
  `mlxfast submission-note <receipt>`, and `mlxfast notes`.
- Key internal PRs: [#35](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/35),
  [#80](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/80),
  [#549](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/549),
  [#555](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/555),
  [#604](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/604),
  [#615](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/615),
  [#617](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/617),
  [#619](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/619),
  [#640](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/640),
  [#644](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/644),
  [#657](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/657),
  [#660](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/660), and
  [#669](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/669).

