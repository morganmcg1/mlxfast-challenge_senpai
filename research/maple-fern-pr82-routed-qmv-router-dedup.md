# PR #82 — routed QMV router dedup (`maple-2026-08-06f-routed-qmv-router-dedup`, r1)

Student: maple-fern. Base `BASE_SHA = f2fedd584e6514569758d79e581402210306e77b`
(base branch `codex/mlxfast-maple-20260804-advisor`). Branch
`maple-fern/routed-qmv-router-dedup`.

**No W&B run exists for this experiment.** This campaign's round-6…13 PRs have no
W&B runs; evidence is ranked `mlxfast` receipt IDs plus `research/*.md` paths and
the local certificates reproduced below.

> **Rebased.** Sections 1-9 were produced against the old base
> `ab1f9a13`. Following the advisor's `REBASE RELEASED` instruction
> (comment 5200113236) this branch took its single permitted rebase onto
> `BASE_SHA = f2fedd584e6514569758d79e581402210306e77b` (post-#72 nezuko,
> post-#81 tanjiro). Section 10 reports what changed, answers the
> register-pressure question that came with the rebase, and re-certifies
> the result at the new base. The old-base evidence is retained verbatim
> because it is the larger campaign (13 runs) and its conclusion survives.
> **All `file:line` anchors in §§1-9 are old-base (`ab1f9a13`) anchors and
> have shifted.** The new-base equivalents are given in §10.1.

Two `baseline_advanced` events were cleared as docs-only and neither triggered a
rebase: `53672755` against the old base, and `f2fedd58` → `6a19fd74bf64e6bde9d2a3c5d7f7970588803cab`
against the new one (advisor comment 5200286285, `research/CURRENT_RESEARCH_STATE.md`
only, intersection with `editablePaths` empty). This result is therefore measured
against `f2fedd58`, and `accepted_base_sha` is `f2fedd58`.

## Verdict: bit-exact; the predicted gain is below this host's resolution — `inconclusive`, and I am *not* requesting a ranked slot

The change is bit-exact (§5 oracle, 5320 pairs, 0 differing; upstream-equivalence
report byte-identical to the unchanged base, on both the old and the rebased
base). Two independent local screens — 13 runs on the old base `ab1f9a13`
(§7) and 8 runs on the rebased base `f2fedd58` (§10.4) — put the pooled
point estimate slightly negative, and in **both** cases the measured
same-session same-arm A/A spread is larger than the contrast.

Primary metric — pooled 4v4 position-balanced mirror at the submitted base
`f2fedd58` (§10.4), which is what the Senpai result reports:

```text
paired_estimate 0.992096884   (delta -0.007903116)
decode_gain     0.991039124   prefill_gain 0.995276942
measured A/A decode spread    arm B +1.447 %   arm C +1.764 %
```

Corroborating, pooled 4v4 position-balanced mirror at the old base
`ab1f9a13` (§7.3):

```text
paired_estimate 0.995775911   (delta -0.004224089)
decode_gain     0.993272449   prefill_gain 1.003324221
all-run decode spread +3.108 %
```

The two bases agree on `decode_gain` to 0.02 pp. In both, the contrast is
smaller than the spread the *same arm* shows against itself, which is the
whole content of the resolution statement below.

**Two retractions are recorded in this report, and they are the most useful
part of it.**

1. **The −1.35 % regression claim is withdrawn** (§7.2 → §7.3). Sequence 1
   alone happened to contain both extremes of the 10-run decode
   distribution; the mirrored sequence did not replicate it.
2. **"Performance-neutral" / "REFUTED" is withdrawn** (§11). Under §0.9.32
   the correct statement is that any effect is **below this host's
   resolution of the measured A/A spread**, not that there is none. Under
   §0.9.33 this mechanism lives in the issue/redundancy channel, which is
   machine-determined: the instruction-to-DRAM ratio is ~0.74 on M4 Pro
   against ~0.89 on M5 Max, so an M4 null **cannot** refute it.

Disposition: **`inconclusive`**. I nonetheless recommend **against** spending
an official M5 slot on Variant A, for reasons that do not depend on the
local timing at all — the redundancy is a documented, deliberate
de-synchronisation, and the only M5 measurement in the repository for a
comparable perturbation of this encoder ordering is a `+0.10 ms/step`
**regression** (§10.5.1, §11.3). §10.6 and §11.4 name what to spend the
next rung on instead.

## 1. Hypothesis

The R1 routed gate/up QMV kernel re-runs the entire 8-round top-8 router
extraction inside every one of its 2048 threadgroups purely to recover a single,
threadgroup-uniform expert id. That id is already published by the selector as
`indices[slot]`. Reading it directly should be bit-exact and should delete
~17 % of the kernel's dynamic instructions.

Pre-registered bracket **[0 %, +1.64 %]** on `ns`, point estimate
**+0.4 % to +0.8 %**. Receipt MDE on `ns` is 0.278 %; receipt-resolvability floor
is ≥ 18.7 µs/step; score sensitivity 14.862 %/ms.

## 2. §3.0 census — who re-runs the top-8 extraction

| Site | File:line (at BASE_SHA) | Re-runs extraction? | Notes |
| --- | --- | --- | --- |
| Routed gate/up QMV, R1 arm `…_top8keys_r1_bf16_v2` | `LagunaRuntimeModel.swift:7631-7748` | **yes** | `expert_slot = group % 8` is threadgroup-uniform; 2048 TGs × 2 simdgroups |
| Routed gate/up QMV, non-R1 arm `…_top8keys_bf16_v1` | `:7608-7618` | **yes** | fallback when `DARKBLOOM_ROUTED_GATEUP_R1=0`; 2 rows/simdgroup, grid 8·128·64 |
| Routed gate/up QMV, indices arm `…_packed_bf16_v1` | `:7337-7434` | no | already `uint expert = uint(indices[expert_slot]);` at `:7358` |
| Routed down + residual `…_r1_v5` | `:7945+` | no | already reads `indices[slot]` |
| Router producer `…_rpg8_keys_v1` | gen `:853-985`, wrapper `:1056+` | no | only *writes* keys; tiled to 32 TGs so it cannot compute top-8 itself |
| Decode ordinal selector | `:8773+`, `:8900-8934` | n/a | 1 TG × 256 threads, full 256-element Batcher bitonic sort; *is* the publisher |
| Shared-expert QMV | — | no | does not route |

So exactly two sites re-run the extraction, and both are the same gate/up kernel
under two geometries. Everything downstream already trusts `indices`.

## 3. Bit-exactness argument (structural, not statistical)

The promoted down+residual kernel pairs this kernel's `activated[slot]` row block
with `indices[slot]` **and** `router_weights[slot]`. Therefore
`top8_winner(slot) == indices[slot]` is **already a correctness invariant of the
promoted, gate-passing frontier**, not a new assumption introduced here. If it
did not hold, the current frontier would be silently mis-routing.

The change strictly *reduces* the number of independent computations of that
value: before, gate/up derived the expert from producer ordinals while down
derived it from the selector; after, both read the same buffer.

## 4. Change (Variant A)

Single submitted path: `Sources/MLXFastModel/LagunaRuntimeModel.swift`.

- Kernel renamed `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`
  → `laguna_routed_nvfp4_swiglu_qmv_packed_top8idx_r1_bf16_v1`. The rename is
  mandatory: MLX JIT caches compiled kernels by name.
- `inputNames`: `["input","fused_weight","packed_scales","router_keys"]`
  → `["input","fused_weight","packed_scales","indices"]`.
- MSL body: `\(lagunaRouterTop8PrecomputedPrelude)` + `uint expert = top8_winner;`
  → `uint expert = uint(indices[expert_slot]);`
- `header:` reduced from
  `lagunaSharedSwiGLUQMVHeader + lagunaDecodeRouterOrdinalHeader + lagunaRouterTop8PrologueHeader`
  to `lagunaSharedSwiGLUQMVHeader` only.
- Wrapper `lagunaRoutedSwiGLUQMVPackedTop8` gains an `indices:` parameter with
  dtype/shape preconditions. **The non-R1 keys branch is untouched**, so
  `DARKBLOOM_ROUTED_GATEUP_R1=0` still restores the promoted 2-row keys kernel
  exactly.
- Call site passes `indices: inds`.

No other operation in the kernel changes: same bank addressing, same qdot and
`simd_sum` order, same suffix/SwiGLU/BF16 boundaries, one writer per row.

## 5. §4.1 bit-exactness oracle

Research-only instrument (`research/maple-fern-pr82-oracle.patch`, driver
`research/maple_fern_pr82_oracle.sh`). It dispatches, per MoE layer per decode
step, the **unmodified** in-kernel selection logic
(`laguna_router_top8_extract_round` over `router_keys`, identical lane mapping)
for all eight ranks and compares against the selector-published `indices[0..7]`
that the candidate kernel now reads.

```
=== arm base (steps=16) ===
arm=base emitted_lines=665 lines_with_diffs=0: 665
arm=base pairs_compared=5320
arm=base total_differing_pairs=0
FERNORACLE pairs=8 diffs=0 extract=[89, 223, 61, 145, 99, 163, 141, 69] indices=[89, 223, 61, 145, 99, 163, 141, 69]
FERNORACLE pairs=8 diffs=0 extract=[0, 131, 18, 236, 186, 168, 193, 199] indices=[0, 131, 18, 236, 186, 168, 193, 199]
FERNORACLE pairs=8 diffs=0 extract=[0, 154, 79, 238, 223, 211, 185, 204] indices=[0, 154, 79, 238, 223, 211, 185, 204]

=== arm control (steps=16) ===
arm=control emitted_lines=665 lines_with_diffs=0: 0
arm=control pairs_compared=5320
arm=control total_differing_pairs=665
FERNORACLE pairs=8 diffs=1 extract=[89, 223, 61, 146, 99, 163, 141, 69] indices=[89, 223, 61, 145, 99, 163, 141, 69]
```

- **base**: 5,320 pairs compared over 665 emitted lines, **0 differing pairs**;
  every line reports `diffs=0`.
- **control** (`DARKBLOOM_FERN_ORACLE_FAULT=1`, `+1` injected on rank 3 only):
  665 differing pairs, **0 lines with `diffs=0`** — the oracle is live and would
  have caught a mismatch on every line.

The control arm is what makes the base arm informative: a silent oracle would
have reported the same `0` for a probe that was wired to nothing.

## 6. §4.2 certificates

### Scope and budget

```text
senpai/validate-assignment-scope.sh ab1f9a13… Sources/MLXFastModel/LagunaRuntimeModel.swift
  -> assignment scope OK: 1 submitted path(s) against BASE_SHA=ab1f9a13…

senpai/check-editable-budget.sh ab1f9a13…
  -> editable budget OK: current=2967485/3000000 bytes headroom=32515
     growth=654/262144 files=142 (base=142)
```

One submitted path only. File count unchanged at 142, so nothing was added to or
removed from the editable surface.

### Bytes

| | bytes |
| --- | --- |
| `LagunaRuntimeModel.swift` at `BASE_SHA` | 521,768 |
| `LagunaRuntimeModel.swift` candidate | 522,422 |
| growth | **+654** |
| per-file cap | 524,288 (1,866 B of headroom left) |

The +654 B is almost entirely the 8-line invariant doc comment; the code change
itself is net-negative in source size. Worth flagging to the advisor: this file
now sits **1,866 B under the 524,288 per-file cap**, which is a tight constraint
for any future work in it regardless of this experiment's outcome.

### Baseline advance

The `baseline_advanced` event during this assignment reported
`current_base_sha = 53672755…`. The advisor cleared it as docs-only
(`research/CURRENT_RESEARCH_STATE.md`, outside `editablePaths`) with an explicit
**do not rebase**, so every measurement here is against the assigned
`BASE_SHA = ab1f9a1323421703f944ac1895841e39b8302542`.

### Injection guard unchanged

The debug injection defaults are untouched; only the line numbers move by the
+10 lines of doc comment.

| | line | text |
| --- | --- | --- |
| base | 11342 | `"DARKBLOOM_INJECT_DECODE_EMPTY", 0)` |
| base | 11354 | `"DARKBLOOM_INJECT_EMPTY_TG", 160)` |
| candidate | 11352 | `"DARKBLOOM_INJECT_DECODE_EMPTY", 0)` |
| candidate | 11364 | `"DARKBLOOM_INJECT_EMPTY_TG", 160)` |

### Harness correctness and goldens

All four `--local-iterate` runs in §7 report `passed_correctness = true`,
`error = ""`, `max_abs_diff = 0`, and there is exactly **one distinct
`golden_hash` across all four runs**, baseline and candidate alike:

```text
golden_hash  = b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63
weights_hash = aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d
harness_hash = 56ba8b02…  (baseline)   712c4035…  (candidate)
```

`harness_hash` differs by construction because it hashes the editable surface,
which is what the experiment changes; `golden_hash` and `weights_hash` are the
behavioural hashes and they are identical.

### Upstream equivalence

Run through `research/run_upstream_equivalence.sh` on **both** arms. The wrapper
executed 1 test in each invocation (not a zero-test pass) and reported
`EQUIVALENCE_EXACT_STEPS=8` in both.

| | prefill max abs logit err | prefill mean abs logit err | decode-0 … decode-7 max abs err | all predicted tokens |
| --- | --- | --- | --- | --- |
| base (`ede561b6`) | 0.125 | 0.011933609 | 0, 0, 0, 0, 0, 0, 0, 0 | identical |
| candidate | 0.125 | 0.011933609 | 0, 0, 0, 0, 0, 0, 0, 0 | identical |

Both arms **fail** the test, with `EQUIVALENCE_EXIT=1`, because the assertion
tolerance is exactly `0.0` and the prefill step reports 0.125.

I ran the base control precisely because of the `AGENTS.md` rule "if a non-M5
host disagrees with a public golden, test the unchanged base". The two reports
are **byte-identical**, down to `meanAbsoluteLogitError = 0.011933609` and every
predicted token id. So:

- the failure is a **pre-existing M4 Pro property of the unchanged base**, not
  something this change introduces. The test is named
  `lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled` and `AGENTS.md` notes
  that M4 Pro reports GPU generation 16 and does not select the `_nax` prefill
  kernels the ranked M5 uses — which is exactly where the 0.125 appears;
- the *differential* certificate this experiment actually needs is met
  perfectly: **candidate ≡ base on every step of the equivalence oracle**, and
  all eight decode steps — the only steps this decode-only change can reach —
  are bit-exact against the vendored upstream model on both arms.

I did **not** set `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1`; it was unnecessary since
`benchmark.sh --local-iterate` passed correctness outright on both arms.

Stated caveat, unchanged from the brief: `LagunaUpstreamEquivalence.swift` never
exercises the layouts derived in `prepareFusedRuntimeWeights()`, so it is not a
complete oracle for representation changes. That is why §5's dedicated in-kernel
oracle exists and is the primary bit-exactness evidence here.

## 7. §6.1 M4 matched no-harm screen — the predicted gain does not appear

### 7.1 Sequence 1 — position-balanced B C C B

Host: Apple M4 Pro, 48.0 GiB. Every run is a full `./benchmark.sh
--local-iterate`, one model-holding process at a time, behind the standard 40 C
cool-down gate. Baseline runs execute at detached `ede561b6` (content-identical
to `BASE_SHA` for `Sources/`); candidate runs at the branch head.

Four runs were taken in the position-balanced order **B C C B**. This is a true
ABBA: the baseline occupies positions 1 and 4 (sum 5) and the candidate
positions 2 and 3 (sum 5), so any *linear* drift over the sequence cancels
exactly in the arm means.

| pos | arm | decode s/tok | prefill s/tok | correctness | `max_abs_diff` | `golden_hash` |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | baseline | 0.012945894211 | 0.001125843668 | pass | 0 | `b9509697…` |
| 2 | candidate | 0.013105335289 | 0.001112878500 | pass | 0 | `b9509697…` |
| 3 | candidate | 0.013348218422 | 0.001124709635 | pass | 0 | `b9509697…` |
| 4 | baseline | 0.013149964516 | 0.001123731445 | pass | 0 | `b9509697…` |

Position-balanced merge (`research/maple_fern_pr82_pair.py`):

```text
mean baseline decode   = 0.013047929363     mean candidate decode  = 0.013226776855
mean baseline prefill  = 0.001124787557     mean candidate prefill = 0.001118794067
decode_gain     = 0.986478377   (-1.352 %)
prefill_gain    = 1.005357098   (+0.536 %)
paired_estimate = 0.991164559
```

### 7.2 Why sequence 1 looked like a refutation — the contemporaneous reading

The assignment's A/A floor for this host is prefill −1.30 % and decode
**+0.48 %**. The measured decode change is **−1.352 %, i.e. 2.8× the A/A decode
floor**, and the brief is explicit that a regression outside the floor *is* a
refutation.

Three independent checks say the signal is real rather than a drift artefact:

1. **Both adjacent pairs agree.** B1/C1 gives decode_gain 0.987834 and B2/C2
   gives 0.985148 — the same sign and a spread of only 0.27 %, even though the
   two pairs sit at opposite ends of the thermal sequence.
2. **The drift is monotone and common-mode.** The repeat spread within each arm
   is +1.576 % (baseline) and +1.853 % (candidate) — both positive and of
   similar size, which is the signature of thermal drift rising across the
   sequence, not of an arm difference. This drift is larger than the quoted A/A
   floor, which is exactly why the unbalanced single pair could not have settled
   the question and the balanced design was necessary.
3. **The regression survives the balancing.** Drift inflates positions 3 and 4
   most; the candidate holds positions 2 and 3 and the baseline 1 and 4, so the
   *un*balanced reading would if anything flatter the baseline. Balancing
   removes that and the candidate is still 1.35 % slower.

Prefill improved +0.536 %, well inside its −1.30 % A/A floor and of no
consequence: the change touches a decode-only kernel (`lagunaRoutedGateUpR1`
dispatches from the single-token decode path), so a prefill move here is noise
by construction and I do not claim it.

The pre-registered bracket in §1 was **[0 %, +1.64 %]** on score with a point
estimate of +0.4 % to +0.8 %. The measured `paired_estimate` of 0.9912 is
**below the bottom of the bracket**, so the bracket is falsified in the
direction §8 predicted, not merely unmet.

### 7.3 Sequence 1 does not replicate — the mirror, and the retraction

The §7.2 reasoning was wrong, and I am reporting that against my own earlier
reading rather than letting it stand.

Pooling sequence 1 with the five runs of the §8.2 attribution sequence made one
thing visible that sequence 1 alone could not show: **sequence 1's position-1
baseline run is the fastest decode measurement in the entire study by a wide
margin.** Sorted across every run taken here, it sits 1.232 % below the next
fastest, while runs 2–10 together span only 1.853 %. A single run that far
outside the body of the distribution, sitting on a *baseline* slot, biases the
baseline mean fast and therefore inflates an apparent candidate regression.

A B C C B design cancels *monotone* drift over the sequence exactly. It does
nothing about a one-off outlier. So I ran the exact position mirror, **C B B C**,
under identical conditions:

| pos | arm | decode s/tok | prefill s/tok | correctness | `max_abs_diff` | `harness_hash` |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | candidate | 0.013226644211 | 0.001123961590 | pass | 0 | `712c4035…` |
| 2 | baseline | 0.013238099937 | 0.001123838459 | pass | 0 | `56ba8b02…` |
| 3 | baseline | 0.013241236648 | 0.001125893961 | pass | 0 | `56ba8b02…` |
| 4 | candidate | 0.013251095375 | 0.001122850668 | pass | 0 | `712c4035…` |

```text
seq3 (C B B C) alone:  decode_gain 1.000060315 (+0.006 %)   paired 1.000370015
```

**The mirror shows no difference at all** — +0.006 % on decode, which is 80×
smaller than this host's A/A decode floor of 0.48 %.

Pooling sequence 1 and sequence 3 gives a fully position-balanced 4-vs-4 design
in which each arm occupies each of the four positions exactly once
(`research/maple_fern_pr82_mirror.py` asserts this balance, and asserts every
arm label against `harness_hash` before the value enters a mean):

```text
POOLED 4v4 mirror:     decode_gain 0.993272449 (-0.673 %)   prefill_gain 1.003324221
                       paired_estimate 0.995775911
```

This pooled figure is the primary estimate of the report, because it is the
balanced design and it includes every run rather than the subset that suits the
conclusion. But it is fragile, and the sensitivity analysis over all ten
base-tree and candidate-tree runs in the study says so plainly. The K arm of
§8.2 is the *same tree* as the baseline (`harness_hash 56ba8b02…`), so it
contributes base-tree observations too:

```text
base-tree decode (n=6): 0.012945894 0.013149965 0.013238100 0.013238144
                        0.013241237 0.013260550
cand-tree decode (n=4): 0.013105335 0.013226644 0.013251095 0.013348218

mean of all runs            gain 0.995931196   (-0.407 %)
median of all runs          gain 0.999943521   (-0.006 %)
mean, single outlier dropped gain 0.999454062  (-0.055 %)
```

Every estimator that is robust to one extreme observation lands within 0.06 % of
**exactly no change**. The whole of the apparent regression traces to sequence 1,
and specifically to the fact that sequence 1 happened to contain *both* extremes
of the ten-run distribution — the fastest run on its baseline arm and the
slowest run on its candidate arm. That is also why §7.2's "both adjacent pairs
agree" check did not save me: B2/C2 rests on the slowest run in the study, so
the two pairs agreed because they shared the same accident, not because the
effect was real.

**Retraction.** I withdraw the §7.2 claim of a real −1.35 % regression. The
correct reading of this host is that the change is **performance-neutral**: no
estimator supports the pre-registered gain, and no estimator robust to a single
outlier supports a loss either.

### 7.4 What the null result means

> **Cross-reference (added after §10).** This section's bandwidth-bound
> reading was challenged during review by a roofline argument, and I
> initially accepted the challenge. That acceptance is **retracted** in
> §10.5.2 on a unit error; corrected, both available M4 estimates bracket
> this kernel at 94–108 % of the effective M4 ceiling. **§7.4 stands.**
> Its wording is also restated under §0.9.32 in §11.2: read "null result"
> throughout this section as "below this host's resolution".

The change is bit-exact (§5, and `max_abs_diff = 0` with a single distinct
`golden_hash` across all thirteen runs in this report), so the arithmetic
performed on the GPU is strictly *less* in the candidate: eight loads and the
extraction's rounding chain are deleted per routed slot, and nothing is added
except one input binding.

That gives the null result its content. The hypothesis was not "this might be a
wash"; it was a priced prediction that the deleted work was worth +0.4 % to
+0.8 % of score, bracketed at +1.64 % (§1). A strict, bit-exact deletion of real
instructions that moves decode time by **+0.006 %** on the balanced mirror, and
by −0.006 % on the median of all ten runs, is a measurement that the deleted
instructions were not on the critical path at all.

The natural conclusion is that the routed gate/up QMV kernel is **bound by the
weight stream, not by its ALU work**. Each threadgroup reads a distinct ~1 MB
`fused_weight` slab; the eight independent `router_keys[lane + 32u*j]` loads and
the small rounding chain that follows them fit under that stream and cost
nothing observable. §8.2 supplies the complementary half of the same picture
from the other direction: *adding* a dependency edge and an encode reorder to
the same kernel, with GPU arithmetic held constant, also moved decode time by
less than the noise floor (and in the fast direction). Two probes that push the
kernel in opposite directions both land at zero, which is what a
bandwidth-bound kernel looks like from the outside.

§8 develops this: §8.1 states the scheduling explanation I pre-registered for
the apparent regression, §8.2 tests it directly and refutes it, and §8.3 records
what the pair of null results implies for anyone tempted to shave instructions
out of this kernel next.

## 8. Counter-hypothesis: barrier / dispatch overlap — pre-registered, then refuted

> **Cross-reference (added after §10).** Two amendments, both softening
> claims made here. (i) §8.1 leans on PR27's 16× under-read as evidence that
> "real overlap exists" in decode; **#73 measures `gpu_busy_sum ==
> gpu_busy_union` in decode**, i.e. *zero* dispatch concurrency, so
> per-dispatch decode time is fully additive. That does not change §8.2's
> empirical refutation — it independently predicts it — but it does mean the
> §8.1 mechanism was never structurally available in decode in the first
> place. The specific sentence in §10.5 where I asserted a kernel "provably
> overlaps the shared QMV" is retracted there. (ii) The word "refuted" in
> this heading and in §8.2 is about a *mechanism* being ruled out by a
> direct probe, not about an effect size; where §8.2 reports its own
> contrast as null, read it under §0.9.32 as **below this host's
> resolution** (§11.2).

### 8.1 The pre-registered mechanism

This was pre-registered before any timing was taken, because the tree states the
risk explicitly in two places:

- `LagunaRuntimeModel.swift:170` — on `DARKBLOOM_ROUTER_PRECOMPUTED_KEYS`:
  *"The OFF arm restores the promoted selector dependency exactly."*
- `LagunaRuntimeModel.swift:7563-7564` — on the extraction header: *"Each routed
  slot performs only the rounds it needs and **never waits on a cross-threadgroup
  selector**."*

In other words the extraction this experiment deletes was promoted **precisely
to break the gate/up → selector dependency**. Reading `indices` re-creates it.

Mechanism, verified in `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp`:
the encoder is created `MTL::DispatchTypeConcurrent` (`:547-548`);
`set_input_array` (`:324-325`) sets `needs_barrier_` on RAW when the input is in
`prev_outputs_`; `register_output_array` (`:343-348`) on WAR; `maybeInsertBarrier()`
(`:363-375`) emits `memoryBarrier(BarrierScopeBuffers)` and **replaces**
`prev_inputs_`/`prev_outputs_` on barrier, otherwise accumulates. A dispatch is
therefore serialized only against producers *since the last barrier*.

Because MLX's tape is built by reverse-BFS (`transforms.cpp:180-224`, executed in
reverse at `:228`), adding `indices` as a gate/up input also **reorders the
encode**. Writing P = router producer, S = selector, Sh = shared QMV,
G = routed gate/up, D = down+residual:

| Arm | Encode order | Barriers/layer | Concurrent region |
| --- | --- | --- | --- |
| keys (baseline) | `P → Sh → S → G → D` | 3 | `{Sh ∥ S ∥ G}` |
| indices (candidate) | `P → S → Sh → G → D` | 4 | `{S ∥ Sh}`, G serialized after both |

The naive "the whole selector becomes exposed" model is *wrong in both
directions*: the selector still hides under `Sh` in the candidate arm, so the
cost is not the selector's ~139.6 µs true M4 / ~105.6 µs M5-equivalent. The real
costs are (i) `G` no longer overlapping `Sh`, (ii) one extra `memoryBarrier`
drain × sparse layers, and (iii) **zero** delta in layers where a command-buffer
split already sits between S and G. The runtime pins
`MLX_MAX_MB_PER_BUFFER=200` / `MLX_MAX_OPS_PER_BUFFER=200`
(`LagunaRuntimeWeights.swift:386-387`) and `device.cpp:484-486` counts each
layer's ~350 MB of touched banks, giving ~50 command buffers/step — roughly 0.8
splits per sparse layer — so a material fraction of layers already lose that
overlap today.

Prior evidence on overlap is genuinely ambiguous and I do not claim it resolves
this: PR73's `gpu_busy_sum == gpu_busy_union` was measured under `SPLIT=1`
per-dispatch forced serialization and therefore *cannot* detect overlap; PR27
measured 40 unchained empty dispatches at 0.154 µs each against 2.53 µs isolated,
a 16× under-read that does demonstrate real overlap exists.

`device.cpp`/`device.h` are **not** in `editablePaths`, so no part of this
mechanism may depend on editing them.

### 8.2 Direct test of the counter-hypothesis — it is refuted

The §8.1 mechanism is a *prediction*, so I tested it directly rather than
resting the report on it. The test isolates the one thing §8.1 blames — the
added dependency edge — from the one thing the experiment actually changes — the
deleted extraction rounds.

Three trees were built, each identified in the emitted metrics by its
`harness_hash` so no arm can be mislabelled:

| tree | GPU work in gate/up | `indices` is a kernel input | `harness_hash` |
| --- | --- | --- | --- |
| **K** (base) | extraction rounds present | no | `56ba8b02…` |
| **KI** (probe) | extraction rounds present | **yes** | `0dd99ac5…` |
| **I** (candidate) | extraction deleted | yes | `712c4035…` |

KI is the baseline kernel with the candidate's input edge bolted on: it takes
*both* `router_keys` and `indices`, and still computes the winner from
`router_keys`. Its GPU arithmetic is byte-for-byte the baseline's; the only
difference from K is the dependency edge and the encode reorder that §8.1 says
follows from it. **K → KI therefore prices the counter-hypothesis on its own.**

Five runs. The position-4 run was **mis-armed** — it did not execute the arm it
was queued for (see the note after the table) — and is excluded from every
estimate below; it is listed only for completeness.

| pos | arm | decode s/tok | prefill s/tok | correctness |
| --- | --- | --- | --- | --- |
| 1 | K | 0.013238144203 | 0.001112089520 | pass |
| 2 | KI | 0.013188098633 | 0.001111878092 | pass |
| 3 | KI | 0.013211592773 | 0.001110943279 | pass |
| 4 | *(mis-armed, excluded)* | 0.013200338539 | 0.001112690592 | pass |
| 5 | K | 0.013260549805 | 0.001125702393 | pass |

Positions 1/2/3/5 are a clean K KI KI K balance:

```text
decode_gain(KI vs K)  = 1.003750142   (KI 0.375 % FASTER)
prefill_gain(KI vs K) = 1.006734928
paired_estimate       = 1.004495508
```

The two independent adjacent contrasts are K1/KI1 = 1.003794753 and
K2/KI2 = 1.003705612 — they agree to **0.009 pp**, which makes this the tightest
comparison in the entire study, tighter than either arm's own repeat spread
(K +0.169 %, KI +0.178 %).

**§8.1 is refuted.** It predicted the added edge would cost roughly the 1.35 %
decode regression that §7.2 read off sequence 1; the measurement puts it at
0.375 % on the *fast* side — wrong sign, and about 3.6× too small in magnitude
even ignoring sign. Adding the `indices` input edge to the routed gate/up
kernel, with GPU work held constant, costs nothing measurable on this host.

I am reporting this against my own pre-registered explanation. The mechanism
described in §8.1 is real in the MLX source; what §8.2 shows is that its *cost*
here is below the noise floor.

These five runs were taken before the §7.3 mirror, when there was still an
apparent regression to explain. The mirror subsequently removed that regression,
so §8.2 no longer has a slowdown to account for — but it remains the study's
tightest measurement (two independent contrasts agreeing to 0.009 pp) and it is
the second of the two probes in §7.4: a probe that *adds* scheduling work to
this kernel and changes nothing.

**The mis-armed run, and the rule it produced.** The position-4 run did not
execute the arm it was queued for. `run_training` returns as soon as the
supervised process starts, and `benchmark.sh` performs the Swift build *inside*
that process, so a `git checkout` issued after launch raced the build and the
worker was compiled from the wrong tree: it emitted
`harness_hash 712c4035…`, the candidate tree, rather than the base tree it was
queued as. It was caught because every `--local-iterate` result carries a
`harness_hash` identifying the built tree, and the emitted hash disagreed with
the intended label. Two rules came out of it and I followed both
for the rest of the study: do not touch the worktree — including `git checkout`
— until the launched training id reports a terminal state; and label every arm
from the emitted `harness_hash`, never from launch order or intent. The merge
scripts used in this report assert the hash before a value enters an estimate,
so a repeat of this mistake fails loudly instead of quietly biasing a mean.


### 8.3 What the two null results say about this kernel

§7.3 removed the regression and §8.2 removed the scheduling explanation for it,
so nothing here needs explaining away any more. What is left is a positive
finding, and it is the useful output of this experiment.

**Leading reading: the routed gate/up QMV kernel is weight-bandwidth-bound, and
its ALU work is already free.** Two probes moved the kernel in opposite
directions and neither moved decode time:

- **remove work** (this experiment): delete eight `router_keys` loads and the
  extraction's rounding chain per routed slot → +0.006 % on the balanced mirror,
  −0.006 % on the median of ten runs;
- **add work** (§8.2): add an input binding, a dependency edge, and the encode
  reorder that follows from it, with GPU arithmetic held constant → +0.375 %,
  i.e. also nothing, and on the fast side.

Each threadgroup of this kernel streams a distinct ~1 MB `fused_weight` slab
(dispatch at `LagunaRuntimeModel.swift:7764-7773`, 2048 threadgroups of 64). A
handful of independent scalar loads and a short rounding chain hide completely
under that stream. On this host the kernel's cost is bytes, not instructions.

That is a falsifiable claim and it makes a prediction: **any future change to
this kernel that only reduces instruction count should also measure zero.** The
way to make the routed projections cheaper is to move fewer weight bytes — or to
remove the dispatch entirely — not to shave arithmetic out of the inner loop.
§9.2 turns this into the concrete next step.

**Secondary possibility I cannot exclude: register pressure and occupancy.** The
deleted prelude holds `thread uint top8_keys[8]` live across the extraction, so
deleting it frees eight registers. In principle a register-allocation change can
perturb the explicit depth-1 weight-staging software pipeline in this kernel
(comment at `LagunaRuntimeModel.swift:7672-7679`), and higher occupancy is not
obviously good when each extra resident threadgroup streams another distinct
~1 MB slab. I raised this as the leading candidate while there was a slowdown to
explain; with the slowdown retracted it is demoted to a possible reason the
saving is *exactly* zero rather than slightly positive. It is not needed by the
data and I do not claim it.

One explanation I considered and reject outright: "the candidate puts a
dependent scalar load on the critical path." It does not. The baseline issues
eight *independent* `router_keys[lane + 32u*j]` loads and then does ALU work on
them; the candidate issues a single `indices[expert_slot]` load. The candidate's
load is strictly lower-latency, so it could not have produced a slowdown even if
one had survived the mirror.

## 9. Suggested follow-ups

I did not implement any of these.

> **Superseded (added after §10).** §10.6 replaces this ranking after the
> rebase, #71's closure of the byte-currency framing, and #73's
> zero-concurrency result. Read §10.6 first; §9.1-§9.5 are kept as the
> contemporaneous record.

### 9.1 Fuse the selector into the gate/up kernel (highest value)

> **WITHDRAWN (added after §10).** This follow-up is **withdrawn**; see
> §10.6 for the replacement ranking. It is superseded by F2 (fold the
> shared expert's gate/up into the routed gate/up dispatch as a 9th slot),
> which removes 39 dispatches per step against this one's 1, has a direct
> in-tree precedent, and is unblocked by #73's zero-concurrency result.
> The text below is retained unedited as the contemporaneous record.

This is the version of the idea that survives the whole study, and §8.2 makes it
*more* attractive than it looked at pre-registration, not less.

Have the routed gate/up QMV kernel publish the routing outputs itself and delete
the standalone `laguna_decode_router_top8_v3` dispatch. Concretely, from a
read of the current tree:

- the selector is `lagunaDecodeRouterTop8Kernel` (`LagunaRuntimeModel.swift:8744`,
  ordinal variants at `:8900/:8909/:8918/:8927`), outputs
  `["router_indices", "router_scores"]` (`:8747`) shaped `[[1,1,8],[1,1,8]]` as
  `[.uint32, .float32]`, dispatched `grid (256,1,1)`;
- the gate/up R1 kernel (`:7631`) already launches 2048 threadgroups with
  `expert_slot = group % 8` (`:7649-7654`) and **already derives the rank-slot
  winner in-kernel from `router_keys`** (`:7595-7607`). The index half of the
  selector's output is therefore redundant work the gate/up kernel could publish
  for free: the `tile == 0` threadgroups write their own slot;
- `MLXFast.metalKernel` supports heterogeneous multi-output — there is a
  four-output example in the same file, `lagunaResidualRMSNormRouterKernels`
  (`:1004`, dispatched `:1088-1095`);
- there is **no ordering obstacle**. Every use of `inds` before the gate/up call
  is metadata-only on a lazy array (`inds.size` at `:10207`, `inds.dtype`/`dims`
  at `:10233-10234`), and the shared-expert path takes only `x` and the shared
  activation (`:10302`), so it stays overlap-eligible. The genuine consumers
  (`lagunaRoutedSharedDownResidual` `:10323`, `lagunaRoutedDownReduce` `:10351`)
  already run after gate/up.

The real cost is the *weights*, not the indices: `router_keys` carries only the
ordinal of `-(score + correction_bias)` (`:866-869`) and the gate/up prelude
never computes scores. To publish `router_scores` bit-exactly the fused kernel
must also take `router_logits`, recompute the same sigmoid, and reproduce the
norm-sink's rank-order left fold `total = simd_shuffle(my_score, i) + total`
(`:8626-8632`) in one designated threadgroup running all eight rounds.

Prize: one dispatch removed per sparse layer, worth roughly 1.57 % of score by
the §7 pricing. Crucially this is a *dispatch* removal, not an instruction-count
reduction, so it is the one class of change to this path that §8.3 does not
predict will measure zero. §8.2 also lowers the risk estimate: I pre-registered
a worry that adding a dependency edge to the gate/up kernel would cost more than
it saved, and the K/KI contrast measured that edge in isolation at 0.375 % on
the *fast* side, with two independent contrasts agreeing to 0.009 pp. A fused
design does not even add an edge. Verdict from the code read: plausible, needs
bounded restructuring. Smallest open question before starting: whether MLX
safely allocates an extra output that only a subset of threadgroups writes —
resolve by reading custom-kernel output allocation in `Vendor/mlx-swift`.

### 9.2 Target bytes, not instructions, in the routed gate/up path

> **Mostly withdrawn (added after §10).** #71 closed the routed-QMV
> byte-currency framing: that instrument self-invalidated at 108.1 % of the
> M4 ceiling, so "spend the saved bytes" is no longer a live proposal for
> this kernel. What survives is only the algorithm-determined half — the
> in-flight byte count itself, which transfers across generations under
> §0.9.33 — and it survives *only* under the bit-exactness constraint
> spelled out in §10.6 (**loads only**; any change to what is computed
> breaks the greedy-token gate). See §10.6 F1.

The transferable finding of this experiment is §8.3: on this host the routed
gate/up QMV kernel is **bound by its weight stream, not by its ALU work**. Two
probes said so from opposite directions — deleting eight loads and a rounding
chain moved decode by +0.006 % (mirror) / −0.006 % (median of ten runs), and
adding an input binding, a dependency edge and an encode reorder moved it by
+0.375 %.

That is a falsifiable prediction, and it should be used as a filter before
spending runs: **any proposed change to this kernel whose entire mechanism is
"fewer instructions in the inner loop" should be expected to measure zero.**
Ideas worth run budget on this path are the ones that reduce bytes moved or
dispatches issued — 9.1 above, anything that shrinks or shares the per-slot
~1 MB `fused_weight` slab, or anything that improves reuse across the 2048
threadgroups of the `:7764-7773` dispatch.

Two ways to strengthen or break the finding, both cheap:

- **Per-variant Metal compiler statistics** (used registers, occupancy,
  threadgroup memory) for the two MSL sources. This is a static artefact of the
  shader, so it needs neither the ranked host nor the noise floor that dominated
  §7. It would confirm directly that the deleted prelude changed nothing that
  matters, and would also settle the demoted register-pressure possibility in
  §8.3. Note these kernels JIT at runtime, so a successful `swift build` proves
  nothing about the MSL — the statistics must come from compiling the emitted
  source.
- **One deliberately larger ALU deletion** in the same kernel, if a bit-exact
  one exists. Bandwidth-bound predicts it also measures zero; ALU-bound predicts
  it scales. A single discriminating run beats re-litigating this one.

### 9.3 Retire the "shave arithmetic out of the routed prelude" family

The extraction this experiment removed is genuinely redundant work — §5 proves
`top8_winner(slot) == indices[slot]` exactly, over 5,320 pairs, with a live
fault control — and on paper it was worth roughly 17 % of a kernel that is
15.2 % of decode. The measured value is zero. The paper pricing was not wrong
about the instruction count; it was wrong to assume instructions are what this
kernel pays for.

So the whole family should be closed, not just this instance. Deleting the
extraction, cheapening the rounding chain, or trimming the prelude's register
footprint are all the same bet on the same mechanism, and §9.2 predicts each of
them measures zero. Revisit only behind 9.1, or if the compiler statistics in
9.2 contradict the bandwidth reading, or on a machine whose balance differs
enough to change the answer — which is an M5 question this M4 Pro host cannot
settle.

On this experiment's own diff: it is bit-exact, +654 bytes, and
performance-neutral within the resolution of this host. It buys nothing, and it
spends scarce per-file byte headroom (9.4), so I do not recommend merging it.

### 9.4 Per-file byte pressure in `LagunaRuntimeModel.swift`

Unrelated to the hypothesis but worth the advisor's attention: the submitted
file is now within **1,866 bytes** of the 524,288 per-file cap
(521,768 at base). Several plausible future experiments in this file will not
fit. A byte-neutral or byte-reducing cleanup pass, or a split into a second
editable file if the contract allows it, may need to be scheduled before the
next sizeable change to this file.

### 9.5 Two methodology items for the next M4 screen

Both came out of this study's own measurement failures and cost me runs.

- **Mirror the position design, and check for a single outlier before
  believing a small effect.** Sequence 1's B C C B design was position-balanced
  and both of its adjacent pairs agreed, and it was still wrong: it happened to
  contain *both* extremes of the ten-run distribution, the fastest run on its
  baseline arm and the slowest on its candidate arm. The fastest run sits
  1.232 % below the next fastest while runs 2–10 span 1.853 %. This was **not**
  a first-run-of-session effect — sequence 3's position-1 run was +0.033 %
  relative to its own sequence, so "discard the first run" would not have caught
  it. What caught it was running the exact position mirror (C B B C) and then
  looking at the pooled distribution. For any effect near this host's A/A floor,
  the standing rule should be: run the mirror, pool to a fully balanced design,
  and report a leave-one-out or median estimate alongside the mean.
- **Label arms by `harness_hash`, never by intent.** `run_training` returns as
  soon as the process starts and `benchmark.sh` builds *inside* it, so a
  `git checkout` issued after launch can race the build and silently produce a
  run of the wrong arm. That happened once here (§8.2) and was caught only
  because `harness_hash` disagreed with the label. The operational rule is: do
  not touch the worktree until the training id is terminal, and verify every
  arm from the emitted hash before it enters an estimate.

## 10. Rebase onto `f2fedd58`, and the register-pressure question

The advisor released the single permitted rebase with a specific question
attached:

> register pressure is exactly the channel your hoist competes in. If the
> hoist now costs a threadgroup-memory round trip that #72's extra
> patch-select registers made necessary, that is a real finding, not a
> nuisance; report it.

This section answers it. Sections 1-9 were produced against the old base
`ab1f9a13`; everything below is at `f2fedd58` (post-#72, post-#81).

### 10.1 What the two intervening merges actually did

Anchors at `f2fedd58`, for the four sites §§1-9 refer to by their old-base
line numbers (all in `Sources/MLXFastModel/LagunaRuntimeModel.swift`):

| site | `f2fedd58` |
| --- | --- |
| R1 routed gate/up QMV `…top8keys_r1_bf16_v2` | `:7515` |
| `expert_slot = group % routed_experts` | `:7534` |
| router top-8 keys kernel | `:997` |
| `prepareFusedRoutedGateUp()` | `:9855` |

**#72 (nezuko, substantive).** Halved the routed group-32 scale plane. All
four routed QMV kernels were edited identically: `scale_row_bytes` 32 -> 16,
a new `scale_patch_bytes` term offsets the plane, the scale index gains a
`lane >> 1`, and a 128-byte patch header is selected against by a predicated
read. In the R1 gate/up kernel this is:

```metal
const device uint8_t* first_scales =
    row_scales + sub * 2 * scale_row_bytes + (lane >> 1);
bool patch_lane = expert == 0 && logical_row == 0 && lane == 1;
gate_sb = patch_lane ? packed_scales[0] : first_scales[0];
up_sb   = patch_lane ? packed_scales[1] : first_scales[scale_row_bytes];
```

**#81 (tanjiro, cosmetic).** A file-wide dedent of Metal string-literal
bodies plus removal of `//` comments inside those literals. Certified
behaviour-neutral; `LagunaRuntimeModel.swift` shrank 521,506 -> 478,533 B.

Neither merge touched the extraction site this experiment deletes, nor the
wrapper signature it extends. The Variant A patch produced on the old base
applies to post-#72 with offsets only; against post-#81 two of its six hunks
fail *purely* on the dedent whitespace of MSL context lines, with the code
text otherwise character-identical. The rebase conflict was therefore
whitespace, not semantics, and was resolved by keeping #81's dedented body
and re-applying the two substantive edits.

The rebased diff against `f2fedd58` is **19 insertions / 9 deletions**, the
same shape as against `ab1f9a13`.

### 10.2 Analytical register accounting

The question is whether deleting the prelude now changes the *binding*
constraint. It does not, and the reason is that the prelude's live set was
never the kernel's peak.

Removed by Variant A, live only inside the prelude:

| value | registers |
| --- | --- |
| `thread uint top8_keys[8]` (statically indexed, unrolled) | 8 |
| `top8_mask`, `top8_winner` | 2 |
| `laguna_router_top8_extract_round` locals (`best_ordinal`, `best_index`, `e`, `o`, `other_ordinal`, `other_index`) | ~4-6 |

Peak during the prelude is therefore roughly **14-16** live 32-bit values,
and `top8_keys` dies at the closing brace.

Retained, live inside the main accumulation loop:

| value | registers |
| --- | --- |
| `thread float input_values[16]` | 16 |
| `gate_codes`, `up_codes` (`uint2` each) | 4 |
| `cur_gate_codes`, `cur_up_codes` | 4 |
| `gate_result`, `up_result` | 2 |
| `gate_sb`, `up_sb`, `cur_gate_sb`, `cur_up_sb` | 4 (packed) |
| pointers, `block`, `next_block`, `i`, addressing temporaries | ~8 |

Main-loop peak is on the order of **38-40** live values, comfortably above
the prelude's peak, and the two regions do not overlap in the schedule: the
prelude completes before `expert` is consumed to form `expert_weight`.

#72's additions - one `bool patch_lane` (a predicate, not a general
register) and two extra byte loads - sit inside the prefetch block, whose
own live set is also below the main-loop peak.

**Conclusion:** the occupancy-determining peak of this kernel is the
accumulation loop, both before and after #72. Deleting the prelude removes
~15 registers from a region that was not the peak, so it cannot raise
occupancy; #72 adds ~1 predicate to a region that is not the peak, so it
cannot have created a spill boundary for the prelude to fall off. There is
no threadgroup-memory round trip in either version - the resolved kernel
declares no `threadgroup` storage at all.

### 10.3 Empirical answer

The analytical argument predicts that the new-base contrast should look like
the old-base contrast: a null. Section 10.4 reports the measured
counterbalanced result at `f2fedd58`.
### 10.4 The new-base screen, measured

Eight timed runs on the rebased branch, plus one excluded warm-up. The
design and decision rule were written down in full *before* any new-base
timing number was read (committed verbatim at `research/maple-fern-pr82-prereg-newbase.md`) and are unchanged.

Every run below carries `passed_correctness=true`, `max_abs_diff=0`,
`golden_hash=b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`
and `weights_hash=aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d`.
Arms are labelled **post hoc by `harness_hash`**, never by intent:

| arm | `harness_hash` |
| --- | --- |
| **B** unchanged base `f2fedd58` | `d60b8e89968c7f1e...` |
| **C** candidate `352e5f26` | `25be2db23202d0ff...` |

Raw artefacts: `research/pr82-scores-newbase/*.json`.
Analysis: `research/maple_fern_pr82_newbase.py` (asserts the four
certificates above, asserts each arm has a single `harness_hash` and that
the two are distinct, then pools position-balanced).
Two mirrored sequences were run back to back in the same session, on the
same host, under the same 40 C thermal gate:

| # | file | arm | decode s/tok | prefill s/tok |
| --- | --- | --- | --- | --- |
| — | `score.warmup.C0.json` | C (**excluded**, warm-up) | 0.0131970530546875 | 0.00113865421484375 |
| 1 | `score.nb1.B1.json` | B | 0.012975816078125 | 0.0011121748046875 |
| 2 | `score.nb1.C1.json` | C | 0.0132736240234375 | 0.001124676025390625 |
| 3 | `score.nb1.C2.json` | C | 0.013044018875 | 0.001125221923828125 |
| 4 | `score.nb1.B2.json` | B | 0.0131636077421875 | 0.001113708416015625 |
| 5 | `score.nb2.C1.json` | C | 0.01327408365625 | 0.0011258353671875 |
| 6 | `score.nb2.B1.json` | B | 0.0130079388046875 | 0.001125141357421875 |
| 7 | `score.nb2.B2.json` | B | 0.0131462942734375 | 0.001120531900390625 |
| 8 | `score.nb2.C2.json` | C | 0.0131707169765625 | 0.001117042805 |

Sequence 1 is `B C C B`; sequence 2 is its mirror `C B B C`. Each arm
therefore occupies positions 1 and 4 once and positions 2 and 3 once, so a
monotone session drift of any shape cancels to first order in the pool.

Pooled 4v4 position-balanced (`python3 research/maple_fern_pr82_newbase.py`):

```text
base   decode mean 0.013073414225      cand decode mean 0.013191622719
decode_gain       0.991039124   (-0.896 %)
prefill_gain      0.995276942   (-0.472 %)
paired_estimate   0.992096884
```

Per sequence:

```text
seq1 (B C C B)  decode_gain 0.993228152  prefill_gain 0.989326303  paired 0.992251249
seq2 (C B B C)  decode_gain 0.988860955  prefill_gain 1.001246205  paired 0.991942830
```

And the number that decides how to read all of the above — the measured
same-session, same-arm A/A spread:

```text
arm B  decode  min 0.012975816078  max 0.013163607742   spread +1.447 %
arm C  decode  min 0.013044018875  max 0.013274083656   spread +1.764 %
all 8  decode  min 0.012975816078  max 0.013274083656   spread +2.299 %
arm B  prefill spread +1.166 %
arm C  prefill spread +0.787 %
```

The B-vs-C decode contrast is **−0.896 %**. Arm B disagrees with *itself* by
+1.447 % and arm C by +1.764 % across runs that differ in nothing but
launch order. The contrast is smaller than either arm's own noise floor.
Per §0.9.32 the correct statement is that **the predicted effect is below
this host's resolution of ±1.4…1.8 % (decode, same-arm A/A)**; this
instrument cannot distinguish the predicted +0.4…+0.8 % from zero, and it
equally cannot distinguish it from the −0.896 % it happened to print. The
new-base screen reproduces the old-base screen (§7.3, pooled
`decode_gain 0.993272449`) to within 0.02 pp, which is reassuring about the
*method* and says nothing about the *mechanism*.

#### 10.4.1 A methodological near-miss worth recording

Partway through, with five of the eight runs in hand, the prefill column
looked like it had separated by arm: every candidate prefill sat near
0.0011250 and every base prefill near 0.0011125. That is a clean-looking
1.1 % arm separation on a metric with a hard 0.95 floor, and it is exactly
the shape of result that invites a mechanism story. I had one available
(kernel rename → fresh MLX JIT library-cache entry).

It was wrong. Run 6, `score.nb2.B1.json`, is a **base** run with prefill
0.001125141357 — inside the candidate range — and run 7 fell back to
0.001120531900. The apparent separation was session drift that happened to
be aligned with arm order in the first sequence, and the pre-registered
mirror is precisely what cancelled it: seq1 prefill_gain 0.989 and seq2
prefill_gain 1.001 straddle unity.

Two things saved this from becoming a false finding, and both were fixed
before any number was read: arms were labelled **post hoc by
`harness_hash`** rather than by intent, and the second sequence was the
**mirror** of the first rather than a repeat. A confirmatory sixth run in
the same order as the first would have strengthened the artefact instead of
exposing it. Recorded here because the failure mode is generic to this
campaign, not specific to this PR.

Independently, an explore pass over the call site established that a
prefill effect is **not causally possible** for this change: the modified
call site (`Sources/MLXFastModel/LagunaRuntimeModel.swift:10037`) is behind
a `x.dim(1) == 1 && inds.size < 64` guard (`:9990-9993`) that prefill never
satisfies; `inds` is produced at `:9986` and already consumed by kernels at
`:10064`, `:10074` and `:10109` on the unmodified path, so no new
materialisation is introduced; the prologue helpers remain live for the
decode-only fallback (`:7496`, `:7498-7499`); and the JIT concern is void
because warm-up runs prefill *then* decode
(`Sources/MLXFastModel/LagunaRuntimeWeights.swift:470-479`), placing any
library-cache miss outside both timed windows. Residual caveat: I did not
inspect the harness's own prefill-window boundary definition, so this is an
argument about the model code, not about the timer.
#### 10.4.2 Scope and budget certificates at the new base

Both re-run at `f2fedd58` after the rebase:

```text
$ senpai/validate-assignment-scope.sh f2fedd584e6514569758d79e581402210306e77b \
      Sources/MLXFastModel/LagunaRuntimeModel.swift
OK   1 submitted path

$ senpai/check-editable-budget.sh f2fedd584e6514569758d79e581402210306e77b
current=2930746 headroom=69254 growth=662/262144 files=142
```

The submitted surface is still exactly one file. Growth is 662 B against the
15 kB the advisor allocated to this PR and against the 262,144 B per-review
cap. `LagunaRuntimeModel.swift` is 479,195 B against the 524,288 B per-file
cap, leaving 45,093 B — comfortably inside the standing ≥ 20 kB margin law
for this file.
### 10.5 Corrections I owe the record

A fresh, context-free frontier review of this result (asked to attack the
conclusion, not defend it) raised two objections. **One survives and is
important. One I am retracting, because checking it against the programme's
own priced census showed the reviewer made a unit error that I then
propagated.** Both are recorded because the retraction is as informative as
the finding.

#### 10.5.1 The design intent I violated is documented in the file (STANDS)

`lagunaRouterTop8PrologueHeader` carries this doc comment:

> Simd-shuffle-only comparator-minimum extraction; lane `l` owns experts
> `l + 32j`, `mask` bit `j` marks extracted. Each routed slot performs only
> the rounds it needs and **never waits on a cross-threadgroup selector**.

The re-extraction is not an oversight to be deleted; it is a deliberate
*de-synchronisation*. The 2048 threadgroups of the routed QMV each derive
their own expert id so the dispatch does not have to be ordered behind the
single-threadgroup selector. Variant A converts that into a real MLX input
dependency, which is exactly what the design avoids.

The file also already contains an M5-measured price for that class of
change. The note above `lagunaSharedFirstDownOrderEnabled` records:

> MEASURED (2026-08-01, M5 Max 128 GB, driver rig, 150-step cool-floor
> windows): shared-first REGRESSES ~+0.10 ms/step. Cause: [...] moving it
> before the top-8 barrier makes the barrier ahead of the routed QMV wait
> on the shared QMV too, LENGTHENING the critical path (barriers are
> encoder-wide, not per-resource).

`+0.10 ms/step` against a ~13.0 ms/step M4 decode is ~0.77 %, and against
the ~4.28 ms M5-equivalent decode it is ~2.3 %. Same sign as this
experiment's persistent negative point estimate, and the same order on M4.

My §8 attribution arm (`KI`: the `indices` argument added but *not* read, so
the MLX dependency edge exists without the ALU saving) came out `+0.375 %`,
i.e. the wrong sign for the barrier hypothesis, which is why §8 called it
refuted. **That refutation was too strong.** `+0.375 %` sits well inside the
same-session A/A spread this campaign actually measured, so the arm
constrains the barrier channel only very loosely. The honest statement is:

> The barrier channel is **not excluded**. The only M5 measurement in the
> repository for a comparable perturbation of this encoder ordering is a
> `+0.10 ms/step` regression. That is an additional, independent reason not
> to spend an official M5 slot on Variant A.

#### 10.5.2 RETRACTED: the "not bandwidth-saturated" roofline correction

The review argued that §7.4's "weight-bandwidth-bound" was overstated, on
the grounds that the routed gate/up QMV moves ~348 MB/step in ~2.0 ms, i.e.
~171 GB/s, only ~63 % of the M4 Pro's ~273 GB/s theoretical peak, and that
the real constraint was memory-level parallelism.

**The ~2.0 ms is wrong, and I should have caught it before writing it down.**
It was obtained as `15.2 % x 13.3 ms`. But `15.2 %` is this campaign's
**M5-equivalent** share of decode `T` (`650.3 us / 4281 us`), not an M4
share. The M4 wall time for the same kernel is the priced `1503.9 us`
against the ~13.05 ms M4 step measured in §10.4, i.e. **~11.5 %**. Applying
an M5-equivalent fraction to an M4 wall clock inflated the denominator by
~33 %.

It also used the wrong ceiling. The programme's own effective M4 DRAM
ceiling is the constant implied by #71's floor: `368.1 MB / 1.4145 ms =`
**`260.2 GB/s`**. The 273 GB/s figure is a datasheet peak, not an
achievable rate.

Redone with the campaign's own priced numbers and post-#72 byte census:

> `368.1 MB / 1503.9 us = 244.8 GB/s = ~94 % of the 260.2 GB/s effective
> M4 ceiling.`

That is saturation, not slack. It is also consistent with the programme's
prior result rather than in tension with it: **#71 already closed the
routed-QMV byte-currency framing**, reporting the exclusive-share instrument
measuring 92.5 % of that 1.4145 ms floor, i.e. `281.3 GB/s = 108.1 %` of
ceiling - a physically impossible figure whose only correct reading is that
the instrument self-invalidates at this level of attribution.

So: **§7.4 stands as written.** The routed gate/up QMV is weight-bandwidth-
bound on M4. The two independent M4 estimates bracket it at **94 %-108 %**
of the effective ceiling; the disagreement between them is exactly #71's
point, and neither leaves room for the "only 63 %" reading.

Two consequences I am obliged to carry forward under **§0.9.33**:

- Achieved GB/s and "% of ceiling" are **machine-determined** and therefore
  **do not transfer** to M5. Everything above is an M4 statement. What does
  transfer is the byte census itself (368.1 MB/step for this kernel,
  algorithm-determined) and the ~5-6 `qdot` ops per weight byte.
- This experiment's mechanism was never a byte mechanism. It is an
  issue/redundancy mechanism (~512x redundant top-8 extraction), and the
  instruction-to-DRAM ratio is ~0.74 on M4 Pro against ~0.89 on M5 Max.
  A local instruction-channel win therefore **understates** the M5 effect,
  and a local null **does not refute** it. §11 states the disposition in
  those terms.

I am also correcting a second claim of my own that #73 falsifies. §10.5.2's
first draft said this kernel "provably overlaps the shared QMV". **#73
measured zero dispatch concurrency in decode** (`gpu_busy_sum ==
gpu_busy_union`). Decode dispatches are serial on this stack, so exclusive
attribution is legitimate and per-dispatch time is fully additive.

### 10.6 Revised follow-ups

**§9.1 (fuse the router top-8 selector into the gate/up kernel) is
withdrawn.** The review's objection is decisive and is already in the file:
2048 threadgroups cannot consume one threadgroup's result without an encoder
barrier between dispatches, so "fusion" would have to be the *distributed
re-derivation that is already shipped* - the very code this experiment
deleted. The selector is one small threadgroup already behind an 8.9 MB
kernel in the same encoder, and the only measured datum about perturbing
this ordering is a `+0.10 ms/step` regression.

**F1 (deepen prefetch in the routed gate/up QMV) is withdrawn for that
kernel, and its premise is retained only where it can still apply.**
The first draft of this section proposed going two blocks ahead on the
grounds that the kernel was latency-starved. §10.5.2 retracts that premise:
at ~90 % of the M4 ceiling there is at most ~11 % of the kernel available
even in the limit, and #71 has already closed byte-currency work here.

What survives is the *transferable* half of the router-GEMV precedent. That
note observes:

> `tiles * rows_per_group == 256` at every tiling, so retiling alone cannot
> add a single outstanding load and leaves in-flight bytes pinned at 64 KB
> [...] Hoisting four blocks' weight loads takes that to 256 KB.

`tiles * rows_per_group` and in-flight bytes are **algorithm-determined**,
so under §0.9.33 they transfer across generations; achieved GB/s does not.
The correct target for that idea is therefore whichever decode kernel is
demonstrably *far* from ceiling - which the routed gate/up is not. Selecting
that kernel requires a per-dispatch byte-and-time census that this
experiment did not run, so I am not proposing a specific rung.

*If it is ever run:* **loads only.** The same router-GEMV note warns that
giving each unrolled step its own partial accumulator regroups sequential
FP32 adds into a tree, loses bit-exactness, and passes every local check
while failing the hidden exact-token gate.

**F2 (promoted to first). Merge the shared-expert gate/up as a 9th slot of
the routed gate/up dispatch.** The shared SwiGLU QMV R1 variant is
shape-identical to one expert slot of the routed kernel (512 rows,
`row = tile*2 + simd_group`, 1024-byte packed rows, same `qdot` header, same
fused gate/up row layout). Extending the grid from `8*256*64` to `9*256*64`
with slot 8 reading the shared fused weight unconditionally removes 39
dispatches per step. There is a shipped, promoted precedent for exactly this
shape: the down+residual kernel is already a 9-slot routed+shared fusion
(`laguna_routed_shared_nvfp4_down_residual_bf16_r1_v5`).

The first draft capped this at "encode-side only, ~+0.3-0.8 %, because the
two kernels already overlap". **#73's zero-concurrency result removes that
cap.** With no dispatch overlap, the shared QMV's wall time is fully
additive, so merging recovers per-dispatch ramp-up and drain as well as
encode cost. It also does not move a single byte, so it is untouched by
#71's closure of the byte-currency framing, and dispatch count is an
algorithm-determined census quantity that transfers to M5 under §0.9.33.
This is now the strongest remaining rung I can see in this area.

**F3. Verify, then attack, per-step encode overhead.** §8.1 assumed ~50
command buffers per decode step from `MLX_MAX_OPS_PER_BUFFER=200`. Decode
encodes on the order of 400 custom dispatches per step, which predicts 2-3
buffers from op count alone; 50 would mean ~8 ops per buffer, i.e. something
else is fragmenting them. Command-buffer count is algorithm-determined and
transfers; it matters relatively more on M5, where GPU time roughly halves
but encode does not. One signpost capture of a single decode step settles
it, and F2 is one of the fixes if fragmentation is real.

*Checked and cleared:* the review also flagged a possible envelope violation
in that all 40 attention layers run group-16 NVFP4 rather than group-32
affine INT8. It is not a violation - the doc comment on
`lagunaNativeAffineNVFP4From` states this is the shipped representation the
goldens came from, "envelope option (1), which never requires the INT8
re-quant". Not re-quantizing is trivially inside an envelope that constrains
re-quantization. The useful corollary for planning is that attention
precision headroom is already spent.

## 11. Disposition (final, stated under §0.9.32 and §0.9.33)

**Senpai result status: `inconclusive`.**

Earlier drafts of this report called the hypothesis `REFUTED` and set the
Senpai status to `failed`. **Both are withdrawn.** The advisor's standing
ruling is that an M4 null is not a refutation and an M4 regression is, and
§0.9.32 requires the null to be written as a resolution statement rather
than as an absence of effect. This section is the corrected disposition.

### 11.1 What was established beyond doubt

- **Bit-exactness.** Every timed arm on both bases carries
  `passed_correctness=true`, `max_abs_diff=0`,
  `golden_hash=b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`,
  `weights_hash=aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d`.
  The §4.1 differential oracle passed 5,320 slot/expert pairs across 665
  decode steps with 0 differing, and its deliberate-fault control fired on
  all 665. Upstream equivalence was run on the candidate **and** on an
  unchanged-base control, byte-identical reports.
  `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` was never set.
  Variant A does what it claims: the hoisted per-slot winner is the same
  expert id the kernel used to re-derive.

- **The mechanism is real and correctly priced as a census.** The routed
  QMV re-derives the per-slot top-8 winner in every one of 2048
  threadgroups, ~512x redundantly, at 39 dispatches/step. Dispatch counts
  and redundancy factors are algorithm-determined and transfer under
  §0.9.33.

### 11.2 What the local instrument can and cannot say

The paired local screens are **below this host's resolution**. Precisely:

- the pooled point estimate for `decode_gain` is negative and small
  (−0.896 % on the new base, 8 runs; −0.673 % on the old base, 8 of 13);
- the **measured same-session, same-arm A/A spread** on this M4 Pro is
  larger than that point estimate, on both bases and in both arms
  (new base: B +1.447 %, C +1.764 %; old base: all-run +3.108 %);
- so the correct statement is *"any decode effect is below this host's
  resolution of the measured A/A spread"*, **not** *"there is no effect"*.

Two further reasons the local instrument is the wrong instrument for *this*
mechanism specifically:

1. **§0.9.33.** This is an issue/redundancy mechanism, not a byte mechanism.
   The instruction-to-DRAM ratio is ~0.74 on M4 Pro against ~0.89 on M5 Max,
   so a local instruction-channel win **understates** the M5 effect and a
   local null **cannot refute** it.
2. **The prefill axis is a known host artefact** (`prefill_speedup ~0.32`,
   `floor=false` on both arms), so no local prefill number - in either
   direction - is evidence about ranked prefill. §10.4 records one
   instructive near-miss on this axis.

### 11.3 Why I nevertheless recommend *against* an M5 slot for Variant A

This is the part that does not depend on the local timing at all, and it is
the reason the disposition is `inconclusive` rather than "needs a ranked
run":

- **The redundancy is deliberate.** `lagunaRouterTop8PrologueHeader` states
  that each routed slot "never waits on a cross-threadgroup selector".
  Variant A replaces a de-synchronised re-derivation with a real MLX input
  dependency - the precise thing the shipped design avoids (§10.5.1).
- **The only M5 measurement in the repository for a comparable perturbation
  of this encoder ordering is a regression**: `+0.10 ms/step` for
  shared-first ordering, because "barriers are encoder-wide, not
  per-resource". That is ~2.3 % of the M5-equivalent decode step.
- **The byte-currency framing here is already closed by #71**, and §10.5.2
  retracts my own attempt to reopen it: at ~245 GB/s the routed gate/up QMV
  is at ~94 % of the effective M4 ceiling.

Expected value of a ranked slot for Variant A is therefore a small,
symmetric, and probably negative bet against a demonstrated M5 regression
for the same class of change. **I am not requesting the channel for it.**

### 11.4 What I would spend the next rung on instead

§10.6, in order: **F2** (merge the shared-expert gate/up as a 9th slot of
the routed gate/up dispatch; removes 39 dispatches/step, moves no bytes,
has a shipped 9-slot precedent, and is unaffected by both #71's byte
closure and #73's zero-concurrency result), then **F3** (verify the
per-step command-buffer count before anyone else builds an argument on the
assumed ~50). **§9.1 and F1-as-drafted are withdrawn**, with reasons.
