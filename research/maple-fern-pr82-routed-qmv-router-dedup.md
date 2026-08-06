# PR #82 — routed QMV router dedup (`maple-2026-08-06f-routed-qmv-router-dedup`, r1)

Student: maple-fern. Base `BASE_SHA = ab1f9a1323421703f944ac1895841e39b8302542`
(base branch `codex/mlxfast-maple-20260804-advisor`). Branch
`maple-fern/routed-qmv-router-dedup`.

**No W&B run exists for this experiment.** This campaign's round-6…13 PRs have no
W&B runs; evidence is ranked `mlxfast` receipt IDs plus `research/*.md` paths and
the local certificates reproduced below.

`baseline_advanced` to `53672755` was cleared by the advisor as docs-only
(`research/CURRENT_RESEARCH_STATE.md`, outside `editablePaths`); this result is
measured against `ab1f9a13` and was not rebased.

## Verdict: REFUTED on M4 — bit-exact, and performance-neutral

The change is bit-exact (§5 oracle, 5320 pairs, 0 differing; upstream-equivalence
report byte-identical to the unchanged base). It is **not** a win: the
pre-registered `[0 %, +1.64 %]` bracket is excluded on the fast side.

Primary metric, pooled 4v4 position-balanced mirror (§7.3):

```text
paired_estimate 0.995775911   (delta -0.004224089)
decode_gain     0.993272449   prefill_gain 1.003324221
```

**Retraction.** §7.2 records the contemporaneous reading of sequence 1 alone,
which showed a −1.35 % decode regression. The mirrored sequence 3 (§7.3) did not
replicate it: sequence 1 happened to contain both extremes of the 10-run decode
distribution. The regression claim is withdrawn. The honest conclusion is
**no measurable effect in either direction** on this host — median 10-run gain
0.999943521 (−0.006 %). Do not merge the diff and do not spend a ranked receipt
on it; see §9.3.

Disposition: `failed` (hypothesis refuted). §8 shows the pre-registered
counter-hypothesis is refuted too, and §8.3 turns the two nulls into the
positive finding: this kernel is weight-bandwidth-bound.

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

### 9.1 Fuse the selector into the gate/up kernel (highest value)

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
