# R85-C (rev2): re-port the `float4` merge epilogue onto the adopted frontier

SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"same_host_paired_estimate","available":true,"value":1.002358},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

- Student / PR: `maple-frieren` / [#457](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/457)
  (`assignment_id=maple-r85-c-placement-lever`, `revision_id=r85-c-rev2`)
- Hypothesis and target cost: the `float4` array-of-structs merge epilogue from
  our PR #205 (mechanism commit `1aad492f`) was dropped when the organizer
  frontier replaced `LagunaRuntimeModel.swift`. Re-porting it into both decode
  fused-attention kernels should recover #205's measured **+18.6 µs/step**
  decode saving, footprint-neutral and bit-exact.
- Decision: **green**
- `BASE_SHA` / candidate commit: `7687c2e44e6975c181444ca8d3d151ee30480a72` /
  `<CANDIDATE_SHA>`
- Submitted candidate files: `Sources/MLXFastModel/LagunaRuntimeModel.swift`
  (the only editable-surface file touched)
- Supporting test or documentation files: research-only —
  `research/maple-r85-c-epilogue-prediction.md` (written before any timing),
  `research/maple_r85c_epilogue_ab.sh`, `research/maple_r85c_epilogue_stats.py`,
  `research/maple_r85c_epilogue_wandb.py`, this file, and the restored
  `research/maple_pr443_*.py` helpers. None is needed for the candidate to work.
- Official submission `--model` value (planned or used; default `senpai`):
  `senpai` — **not submitted**; the advisor holds submission until frieren's and
  fern's arms are both in.
- Explicit API model-value rejection, if fallback attribution was required: none
  (no submission attempted).
- Assignment-scope preflight:
  `senpai/validate-assignment-scope.sh 7687c2e4… Sources/MLXFastModel/LagunaRuntimeModel.swift`
  → `assignment scope OK: 1 submitted path(s)`
- Editable bytes / headroom / growth: `senpai/check-editable-budget.sh 7687c2e4…`
  → `current=2890889/3000000 headroom=109111 growth=-454/262144 files=140`.
  The file **shrinks** 511,418 → 510,964 B (−454 B).
- Scored-path reachability evidence: both edited kernels appear in every timed
  step's GPU profile on this host —
  `sliding_fused_attn_ring_v1` at 6,031 dispatches / 200 steps (≈30 layers/step,
  649.3 µs/step baseline) and `full_fused_attn_grow_v1` at 1,992 / 200 steps
  (≈10 layers/step, 254.9 µs/step baseline). Neither is a `_nax` prefill kernel,
  so the M4 Pro reachability caveat does not apply to this arm.

## What was ported

`git show 1aad492f -- Sources/MLXFastModel/LagunaRuntimeModel.swift` applied
**cleanly** onto `7687c2e4`: 6 hunks, pure line offsets (+47), zero conflicts.

The epilogue merges two heads' partial outputs through threadgroup scratch. The
base form declares `U pair_scratch[4 * BN * BDP]` and walks four scalar planes;
the ported form declares `float4 pair_scratch[BN * BDP]` and moves one vector
per lane per round.

| Property | Base (structs-of-arrays) | Candidate (`float4`) |
| --- | ---: | ---: |
| scratch declaration | `U[4 * BN * BDP]` | `float4[BN * BDP]` |
| threadgroup bytes | 4·32·33·4 = **16,896** | 32·33·16 = **16,896** |
| stores per lane per invocation | 8 | **2** |
| loads per lane per invocation | 8 | **2** |
| `simdgroup_barrier` count | 3 | **3** |

`U = float`, `BN = 32`, `BD = 32`, `BDP = 33`. Footprint is byte-identical, so
the 32,768 B threadgroup wall is not approached, no plane is added, and
occupancy cannot change: `pair_planes` is *removed*, never raised. Bit identity
holds by construction — the store index `lane * BDP + sg` and the transposed
load index `sg * BDP + lane` are unchanged, the plane subscript `p` simply
becomes the vector component, and each `simd_sum` consumes the same 32 products
in the same lane order. Only the *round grouping* changes: the candidate
finalizes `pair_o0[0..3]` (head 0) in round 1 and `pair_o1[0..3]` (head 1) in
round 2, where the base did planes 0–1 of both heads, then planes 2–3.

### Structural finding: the frontier did not rewrite this region

The assignment expected a hand port because "the frontier rewrote this exact
region". **It did not.** The frontier's epilogue is textually identical to our
*pre*-#205 code; #205 was simply lost when the frontier replaced the file
wholesale. There is therefore no partial recovery of the mechanism already
present in the frontier body, which is why the patch applied with only line
offsets and why the replication prediction was strong.

## Evidence

- Host, memory profile, toolchain, and thermal policy: AWS **M4 Pro, Apple GPU
  generation 16**, 48 GiB → the low-memory startup profile is active (allocator
  cache capped at 6 GiB; ranked code paths all remain enabled). Both arms run
  under the same profile and the same 40 C thermal gate. **This is not the
  ranked M5**; see M5 transfer risk below.
- Exact baseline and candidate commands: a single counterbalanced two-binary
  session,
  `OUT=/tmp/maple-r85c-epi REPS=4 STEPS=200 BASE_SHA=7687c2e4… research/maple_r85c_epilogue_ab.sh`,
  which builds candidate (HEAD) and base (`git checkout $BASE_SHA -- $SRC`) into
  `.build-worker` with
  `swift build -c release --force-resolved-versions --scratch-path .build-worker --product mlxfast-runtime-worker`,
  snapshots `{mlxfast-runtime-worker, mlx.metallib}` per arm, and then executes
  4 reps × 4 slots in **ABBA** order (`base cand cand base`), each slot
  `DECODE_PROBE_WORKER=<snap>/mlxfast-runtime-worker DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 python3 research/decode_probe.py --steps 200 --profile …`.
  A two-binary A/B is sound here because `otool -L` shows the worker links no
  project dylibs (only system frameworks and `/usr/lib/swift`) and its only
  project rpath is `@loader_path`, so a snapshot is exactly
  `{executable, mlx.metallib}`.
  Analysis:
  `research/maple_r85_arm_stats.py --steps 200 --cbs-per-step 406 --arms base cand --offset 0`
  and the same-arm null `--arms cand cand --offset 1`.
- Tests and risk-based checks run, including selected-test count:
  `research/run_upstream_equivalence.sh`, **selected-test count 1** (the bare
  `lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled` filter; the wrapper
  refuses to call a zero-test invocation a pass) →
  `EQUIVALENCE_EXACT_STEPS=8`, `EQUIVALENCE_EXIT=1`. **I then ran the unchanged
  base as a control in the same session and got a byte-identical report**, so the
  non-zero exit is a pre-existing base property, not a regression — see below.
  64-step drift tripwire:
  `mlxfast-swift correctness --weights weights --golden correctness_prompts/public_longcopy_gate_english_512_256.json`
  — `<TRIPWIRE>`. `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` was **unset** for that run
  (the runner `unset`s it explicitly rather than assuming an empty environment).

#### The oracle's non-zero exit is pre-existing, and the decode path is exact

| Step | candidate max abs logit err | base control | runtime vs upstream token |
| --- | ---: | ---: | ---: |
| prefill | 0.125 (mean 0.011933609) | 0.125 (mean 0.011933609) | 5991 == 5991 |
| decode-0 … decode-7 | **0** (all 8) | **0** (all 8) | all equal |

The oracle applies **zero** tolerance and the batched NVFP4 prefill path cannot
meet that against the BF16 upstream reference on this host, so it reports
`EQUIVALENCE_EXIT=1` even on untouched code. Three points make this a pass for
this arm:

1. The failing step is **prefill**; the eight **decode** steps — the only path
   this arm changes — are exactly `0`.
2. I ran the oracle against the pinned `BASE_SHA` source for the edited file in
   the same session (`/tmp/r85c-equiv-base.sh`, which restores HEAD on exit) and
   got the identical report and identical `EQUIVALENCE_EXACT_STEPS=8` /
   `EQUIVALENCE_EXIT=1`. Candidate minus base is therefore exactly zero.
3. These are the same figures several siblings already documented as a
   pre-existing M4 Pro artifact (`research/CURRENT_RESEARCH_STATE.md:3011`,
   `research/frieren-host-cpu-budget.md:471`,
   `research/maple-fern-pr40-result.md:381`,
   `research/maple-fern-pr48-fused-norm-qkv-gate.md:462`).

Honest scope limit: this oracle exercises 512 prompt tokens and 8 decode steps.
The far stronger bit-exactness evidence for this arm is the 16-slot token-stream
identity over 3,200 decode steps reported below.
- Correctness and serial-protocol verdict: **pass, bit-exact.** `cksum` over all
  16 slots' `.tokens` dumps collapses to **exactly one** distinct stream, so base
  and candidate produce identical argmax token sequences; all 16 slots report
  `teacher-forced greedy tokens: 0 divergences`. The change is confined to the
  arithmetic *grouping* of an existing threadgroup reduction: it computes logits
  and KV rows only for supplied tokens, advances position by exactly the input
  length, and adds no cache, memo, or cross-request state, so the serial
  non-speculative rules are untouched.
- Divergent tokens or failure category, if any: none.
- Peak RAM or generated-weight size, if relevant: unchanged — no weight or
  metadata transformation. Both worker executables are **49,096,520 bytes**
  (candidate sha256 `84ff5c2d212ca3ef…`, base `f1ae63b34f88ca1b…`; distinct
  hashes, identical size), independently corroborating footprint neutrality.
- Official ranking status versus correctness/floor status, if submitted: not
  submitted.

### Primary instrument: paired per-kernel GPU-busy time

The pre-registered decision instrument is the ratio-adjusted paired-duplex total
GPU-busy time (control kernel `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`),
because `research/maple-r85-noise-floor.md` established on this host that
single-shot wall clock carries **±133 µs/step** — 7× the effect being tested —
while this instrument carries **±5.1 µs/step at n = 8**. Window: the last
80,794 command buffers = 406/step × 199 steady steps (step 0 dropped);
`cbs_per_step = 406` was re-verified for this session by counting GPUPROF
records between consecutive `argmax_bfloat16` records.

Sign convention below is **cand − base, so negative = candidate faster**.

| Kernel | base µs/step | offset-0 delta µs/step | same-arm null (offset 1) |
| --- | ---: | ---: | ---: |
| `sliding_fused_attn_ring_v1` **(touched)** | 649.3 | **−20.98 [−22.76, −19.19]** | −0.25 [−3.05, +2.56] |
| `full_fused_attn_grow_v1` **(touched)** | 254.9 | **−5.55 [−6.74, −4.36]** | −0.18 [−1.90, +1.56] |
| touched-kernel sum | 904.2 | **−26.53** | — |
| `gate_sp_h64_v1` (give-back) | 242.9 | **+8.14 [+7.42, +8.86]** | +0.22 [−1.86, +2.31] |
| `shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` | 285.9 | +1.55 [+0.26, +2.84] | −1.81 [−5.32, +1.74] |

**Total steady GPU busy, ratio-adjusted, n = 8 paired duplexes:
−15.43 µs/step [−22.04, −8.82]**, i.e. a **+15.43 µs/step candidate win**
(−0.180 % of busy time). At the recorded conversion of 0.015280 % score per
µs/step decode this is **+0.2358 % score [+0.1347, +0.3368]**. Per-duplex
SD 7.92 µs/step → ±6.62 at n = 8, matching the ±5.1 the noise floor predicted.

**Same-arm null (offset 1, `cand`→`cand`, n = 4): −1.60 µs/step
[−23.37, +20.23]**, score −0.024 % — centred on zero. Crucially, the null on the
two *touched* kernels is −0.25 and −0.18 µs/step with intervals far too tight to
admit a −21 or −5.6 effect, so the offset-0 signal cannot be session drift or
slot-order artefact.

### Predicted versus measured

| Quantity | Pre-registered | Measured |
| --- | ---: | ---: |
| decode saving | +18.6 µs/step (95 % interval +12.9 to +24.3) | **+15.43 [+8.82, +22.04]** |
| score | +0.284 % (+0.197 to +0.371) | **+0.2358 % [+0.1347, +0.3368]** |
| `max_abs_diff` | exactly 0 | **0** (one token stream over 16 slots) |
| footprint | neutral | neutral (16,896 B → 16,896 B) |

The point estimate lands **inside** the pre-registered 95 % interval, in its
lower half. By the interpretation rules locked in commit `74e89d7` this is a
**clean replication**, slightly short of the #205 headline (+18.58 ± 2.92).

### The give-back is real and eats 42 % of the kernel-local win

The two touched kernels save **26.53 µs/step** but the net is **15.43**, so
**11.1 µs/step (42 %) is given back elsewhere**, and `gate_sp_h64_v1` alone
accounts for 8.14 of it (73 % of the give-back, a +3.35 % regression on a kernel
I did not touch, with a tight CI and an SD of only 0.84). Its same-arm null is
+0.22 [−1.86, +2.31], so this is a reproducible property of the candidate binary,
not drift.

This matters beyond this arm: it is the same give-back signature the parked
placement arm catalogued in `GIVEBACK_KERNELS`, and it means **kernel-local
savings on this codebase should be discounted by roughly 40 % before being quoted
as end-to-end wins**. Because the two arms have byte-identical threadgroup
footprints and identical executable sizes, occupancy and threadgroup pressure are
excluded as mechanisms; the plausible remainder is runtime JIT pipeline
compilation ordering/placement or GPU power-and-clock redistribution. The parked
arm's stage-3 result already *refuted* address displacement as the give-back
mechanism for a different change (corr −0.088 between the pad's per-kernel
signature and the give-back's), so this recurrence is unexplained and worth its
own arm.

### Wall clock was not sensitive enough, as predicted

The same session's wall clock gives median **−1.69 µs/step [−68.47, +64.63]**
(trim10 +6.72, mean +7.77) — uninformative. This is expected and not a negative
result: `DARKBLOOM_GPU_PROFILE_SPLIT=1` serialises all 406 command buffers per
step, inflating per-step time to ≈9,795 µs, so profiled wall clock cannot resolve
an 18 µs effect. It is reported for completeness only and was **not** used for
the verdict.

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | `<DEC_BASE>` | `<DEC_CAND>` | `<DEC_RATIO>` |
| prefill seconds/token | `<PRE_BASE>` | `<PRE_CAND>` | `<PRE_RATIO>` |
| same-host paired estimate | — | **1.002358** [1.001347, 1.003368] | — |

The paired estimate is a same-host research metric, not an official M5 score.

## Relay for PR #460 (tanjiro's critical-path arm)

The advisor asked that this host's noise floor reach #460; I cannot comment there,
so it is restated here. From `research/maple-r85-noise-floor.md` plus this
session's confirmation:

- **Single-run vs single-run wall clock: ±133 µs/step.** A single
  `./benchmark.sh --local-iterate` shot is *not* admissible evidence for any
  effect below roughly 130 µs/step.
- **Ratio-adjusted paired ABBA blocks, n = 8: ±5.1 µs/step** (this session
  independently measured ±6.62 with per-duplex SD 7.92). This is the smallest
  usable decision instrument on this host.
- **Per-kernel GPU-time attribution: ±0.3–2.0 µs/step**, depending on kernel size.
- Profiled wall clock (`DARKBLOOM_GPU_PROFILE_SPLIT=1`) is ≈9.8 ms/step and
  carries ±65 µs/step at n = 8 — do not use it as a wall-clock proxy.

## Conclusion

- What happened and why: PR #205's `float4` merge epilogue was not "rewritten by
  the frontier", it was **dropped**. Re-applying it recovers a real, significant
  decode saving on both fused-attention kernels (−20.98 and −5.55 µs/step, both
  with intervals excluding zero and clean same-arm nulls), bit-exact and
  footprint-neutral, while *shrinking* the submitted file by 454 B.
- Evidence for or against the mechanism: strongly for. The mechanism is a 4×
  reduction in threadgroup scratch traffic (8 stores + 8 loads → 2 + 2 per lane)
  at identical barrier count and identical byte footprint, and the measured
  saving is concentrated exactly in the two kernels whose epilogue changed, in
  proportion to their dispatch counts (≈−3.2 % on the 30-layer sliding kernel,
  ≈−2.2 % on the 10-layer full kernel).
- Uncertainty or M5 transfer risk: the verdict rests on GPU-busy attribution
  from a *profiled* build on an **M4 Pro**, not the ranked M5. Two specific
  risks: (1) the 42 % give-back is a machine-level redistribution effect and its
  magnitude on M5 is unknown — the M5 could give back less (a larger net win) or
  more; (2) #205's original +18.58 µs/step was itself measured on this host
  family, so the *replication* is on solid ground even though the absolute M5
  number is not. Threadgroup geometry is unchanged, so the usual
  core-count sign-flip risk does not apply here.
- Smallest useful next action: **merge**, then open a separate arm for the
  `gate_sp_h64_v1` give-back. Recovering even half of that 8.14 µs/step is worth
  +0.062 % score for a kernel nobody has touched, and the same signature has now
  appeared in two unrelated arms.
- Recommendation: **merge.** One mechanism, one file, bit-exact, negative byte
  growth, point estimate inside the pre-registered interval, and a clean null.
