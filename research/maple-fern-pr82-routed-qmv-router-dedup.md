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

<!-- FILL: local-iterate correctness, goldens, upstream equivalence, injection guard, budget, bytes -->

## 7. §6.1 M4 matched no-harm screen — the mechanism is refuted

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

### Why this is a refutation and not noise

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

### Attribution

Because the change is bit-exact (§5, and `max_abs_diff = 0` with a single
distinct `golden_hash` across all four runs), the arithmetic performed on the
GPU is strictly *less* in the candidate: the extraction rounds are deleted and
nothing is added. A bit-exact strict-work-reduction that runs **slower** can
only be a scheduling effect, which is precisely the §8 counter-hypothesis, and
that counter-hypothesis was registered before any timing was taken.

## 8. Pre-registered counter-hypothesis: barrier / dispatch overlap

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

The matched M4 screen in §7 is the discriminator between "extraction removal won"
and "the new barrier ate the win".

`device.cpp`/`device.h` are **not** in `editablePaths`, so no part of this
mechanism may depend on editing them.

## 9. Suggested follow-ups

<!-- FILL -->
