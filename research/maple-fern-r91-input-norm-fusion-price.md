# R91-A — pricing the input-RMSNorm -> QKV fusion before implementing it

PR #483 · assignment `maple-r91-a-input-norm-fusion-price` · revision
`r91-a-rev1` · branch `maple-fern/r91-input-norm-fusion-price` ·
base `3f430f6f17ac4bfbac5f47767ca78cb89d84a760`.

The advisor branch moved to `30f752df` (merge of #481) while stage 1 was on the
GPU. Per the advisor's instruction not to rebase mid-measurement, **every number
in this file was measured on `3f430f6f` plus this branch's probe commits**.
`30f752df` ships zero editable-path bytes — all 11 of its files land under
`research/` and `senpai/tools/agx-census-probe/` — so it cannot move a timing
result here.

Status: **terminal — the family is dead.** Stage 1 priced the fusion at
**≤ 35.02 µs/step (95 % upper bound) ≈ 0.535 % score**, against the
assignment's ~80 µs/step stopping bar and its ~193 µs/step model. Stages 2 and
3 were therefore not run. `Sources/` is unmodified on the submitted branch; the
instrument is preserved as `research/maple-fern-r91-stage1-probe.patch`.

Three results here outlive this assignment:

1. **The prize does not exist.** Adding a whole redundant input-RMSNorm plus a
   glue op to every layer — 80 extra dispatches/step, +19.7 % dispatch count —
   costs **+8.61 µs/step busy, CI [−17.71, +35.02]**, i.e. nothing. (Finding 4)
2. **Deletion probes are unsound on this MoE model.** Stage 1a's arms decode a
   *different token stream*, so they re-route to different experts. Its
   −137 µs/step "ceiling" was routing contamination, not dispatch cost.
   (Findings 3, 4)
3. **The assignment used rule 41's WIDE constant where TINY applies.** A
   decode input-RMSNorm is a 4 KB dispatch, so the boundary term is
   40 × 0.7258 = 29.0 µs/step, not 40 × 1.4064 = 56.3. That independently lands
   under the bar too. Separately, `gap` never moves in any contrast, so the
   76.3 % serialization share of a boundary is hidden on this GPU-bound stream
   and is not recoverable here. (Finding 6)

W&B: [`ubjfsywa`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/ubjfsywa)
(group `r91-a-input-norm-fusion-price`).

Mechanism class (`research/DATASET_ANALYSIS.md` §5): this lever is "remove a
dispatch boundary" plus "issue fewer instructions", both of which are expected
to transfer *positively* from M4 Pro to the ranked M5. The problem is not
transfer risk — it is that the prize is too small on either machine.

## Why this is a pricing experiment and not an implementation

The advisor's arithmetic for the prize:

| term | value |
| --- | --- |
| `rmsbfloat16` share of steady decode busy | 1.66 % of ~8,500 µs/step ≈ 141 µs/step over 41 dispatches |
| the 40 per-layer input norms | ≈ 137 µs/step |
| dispatch boundaries removed, 40 × 1.4064 µs (rule 41) | ≈ 56 µs/step |
| **ceiling** | **≈ 193 µs/step ≈ 2.95 % score** |

Rule 38's 40 % haircut is withdrawn for this family, so no discount is applied
to that estimate. The ceiling is a *model*; stage 1 measures it.

Two of the four candidate fusion shapes are already dead on paper:

* **(1) naive full fusion** — every QKV output row re-derives the whole
  normalized row, `R = 5,120` redundant recomputes, net ≈ −115 µs/step.
* **(3) folding `w_norm[i]` into the NVFP4 weights offline** — not bit-exact,
  so it is outside the correctness gate regardless of speed.

The two open shapes are **(2)** a thin-boundary invRMS scalar handed to the
QKV kernel and **(4)** deterministic partial sums-of-squares written by the
preceding kernel. Both are only worth writing if the whole prize is large
enough to survive their producer cost, which is what stages 1 and 2 price.

## Rule 39 — reachability audit

All line numbers are on this branch's `Sources/MLXFastModel/LagunaRuntimeModel.swift`
at commit `6b9fab4` (the probe commit); the shipped call site is unchanged from
the base except for the probe branch.

| # | fact | evidence |
| --- | --- | --- |
| 1 | The scored decode attention entry point is `LagunaRuntimeAttention.callAsFunction`. | `:5699` |
| 2 | Its fused-decode block is guarded to `B == 1, L == 1`, bf16 activations, bf16 norm weight of `hiddenSize`, per-head gating. A 1-token decode step takes it; the 512-token prefill does not. | `:5717-5735` |
| 3 | Inside that block the native-affine branch is taken when `lagunaUseNativeAffineQKV(layer:)` holds and `_nativeAffineQKV` is present. | `:5737-5739` |
| 4 | The one-dispatch fused norm+QKV (`lagunaNormAffineQKV`) is gated on `mode == .affine, bits == 8, groupSize == 32`. On the shipped default configuration (`DARKBLOOM_NATIVE_AFFINE_NVFP4` on, `_FROM` = "0") **every** layer is NVFP4, so this guard declines on all 40 layers and `fusedQKV == nil`. | `:5747-5753`, flags at `:2869-2875` |
| 5 | Therefore `inputNorm(input)` at the probe site executes once per layer per decode step — 40 dispatches/step. | `:5789-5799` |
| 6 | Its consumer is `lagunaDecodeNVFP4QKVR1(normalized:bank:heads:)`. | `:5800-5803`, definition `:4823` |
| 6b | That helper has **three** dispatch branches selecting a scale-plane encoding, and the one taken on the default configuration is the **lane-major** branch, whose body comes from `lagunaDecodeNVFP4QKVLaneMajorSource(pairwise:)` — *not* from `lagunaDecodeNVFP4QKVR1Source`. `DARKBLOOM_ATTN_SCALE_NARROW_QKV`, `_LANEMAJOR` and `_PAIRWISE_QKV` all default on (`!= "0"`), and the lane-major bank is populated at `:5596-5604`. Any stage-2 instrument placed in the stock or narrow generator would never execute. | branch `:4842-4858`, source `:4743-4800`, names `:4806-4809`, flags `LagunaRuntimeWeights.swift:677-678,693-694,718-719` |
| 7 | The same `normalized` row is also read by the gate path (`lagunaGateSoftplus`, `quantizedMM`, `gateProjection`), so the probe perturbs the gate input as well as QKV. It still removes exactly one dispatch per layer and adds none. | `:5816`, `:5823`, `:5832` |
| 8 | The second `inputNorm(input)` site is `let normalizedInput: MLXArray? = fusedNormQKV == nil ? inputNorm(input) : nil`. At decode `fusedNormQKV` is always non-nil, so it is `nil` and no norm runs there; the retained BF16 QKV bank below it is `L > 1` only. | `:5878-5879`, `:5888` |
| 9 | `inputNorm` is `MLXNN.RMSNorm` (`LagunaRuntimeLayers.swift:2303`, passed `:2335`) → `MLXFast.rmsNorm` → the AOT metallib kernel `rms_single_row` in `Vendor/mlx-swift/.../kernels/rms_norm.metal`. There is no custom standalone-norm kernel in the runtime. | as cited |
| 10 | Empirical confirmation that the control reaches the scored path: the pre-check measures `base` = **406.0 dispatches/step**, `skipr` = **366.0**, `skipc` = **366.0**. The delta is exactly **40**, one per decoder layer, matching fact 5. | `/tmp/maple-r91a/precheck/` |

## Stage 1 — the ceiling probe

### Arms

One binary; the arm is selected by `DARKBLOOM_R91_INPUT_NORM_PROBE`
(`:5306-5322`, applied `:5789-5799`). No kernel *source* differs between arms —
only how many times the unchanged AOT `rms_single_row` is dispatched — so
rule 33's JIT-cache-key hazard does not apply.

| arm | mode | what the QKV/gate consume |
| --- | --- | --- |
| `base` | 0 | `inputNorm(input)` — shipped |
| `skipr` | −1 | the raw residual `input`. Deletes exactly one dispatch per layer and preserves every producer/consumer edge, so the dispatch stream stays serialised exactly as shipped. **Primary.** |
| `skipc` | −2 | `inputNorm.weight` reshaped to the row shape (contiguous reshape ⇒ no dispatch). Bounded values, but the projection subchain no longer depends on the previous layer's residual, so it may overlap. **Diagnostic upper bracket only.** |

Both deletion arms are **numerically wrong by construction**. They are exempt
from the correctness gate because they never ship: the probe is delivered as a
research patch and the submitted `Sources/` tree is byte-identical to the base.
That exemption is stated here explicitly, as the assignment requires.

A bit-exact "inject a redundant extra rmsNorm" arm was considered up front and
initially rejected, because MLX is lazy — a discarded duplicate node is never
evaluated — and forcing it into the graph costs an extra glue dispatch. Stage
1a's `skipc` result overturned that judgement: the glue dispatch can be
*matched* across both arms and cancelled, whereas the value perturbation the
deletion arms carry cannot be. See stage 1b below.

### Design

`research/maple_r91a_input_norm_ab.sh`. Counterbalanced 8-slot palindromic
`ORDER="base skipr skipc base base skipc skipr base"`, giving per rep two
`base/skipr` duplexes, two `base/skipc` duplexes, two `skipr/skipc` duplexes
and one `base/base` null duplex. `REPS=4` ⇒ **n = 8 duplexes** on each of the
two primary contrasts. `STEPS=200`, first step dropped (KV growth).

Regimes:

* `nat` — `DARKBLOOM_GPU_PROFILE=1`, shipped dispatch concurrency (~45 CBs/step).
  **The only regime a conclusion is drawn from.**
* `s1` — additionally `DARKBLOOM_GPU_PROFILE_SPLIT=1`, 406 CBs/step, one
  dispatch per command buffer. **Attribution only** (rule 43): no `s1` total,
  ratio or cross-kernel sum enters any conclusion below.

### σ used (rule 40)

Paired-ABBA `nat` **absolute busy**, σ = 14.74 µs/step (±12.3 at n = 8) and
`nat` **wall**, σ = 29.96 µs/step (±25.0 at n = 8), from the σ table at
`research/CURRENT_RESEARCH_STATE.md:135-150`. The ratio-adjusted busy estimator
(σ = 10.65) is **not** used: the whole point of the arm is that it perturbs
kernels it does not touch, which invalidates a control denominator. The
in-session null (`--offset 1`, `base/base`) is reported next to each contrast
as the estimator's own zero check.

### Stage 1a results — deletion arms

Run on `3f430f6f17ac4bfbac5f47767ca78cb89d84a760` (the assignment's `BASE_SHA`;
the advisor bumped the base twice mid-measurement and instructed no rebase).
`env OUT=/tmp/maple-r91a REPS=4 STEPS=200 REGIMES=nat`, 32 timed slots, 200
steps each, first step dropped ⇒ 199 steady steps per slot.

Per-arm means (µs/step): `base` wall 8222.3 / busy 7966.4; `skipr` wall 8075.7 /
busy 7823.5; `skipc` wall 9054.2 / busy 8757.9.

| contrast | offset | n | metric | Δ µs/step | 95 % CI | SD | score % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `skipr − base` | 0 | 8 | wall | **−135.93** | [−154.67, −117.14] | 22.82 | −2.0770 |
| | | | busy_sum | **−137.13** | [−143.57, −130.68] | 7.84 | **−2.0953** |
| | | | busy_union | −137.13 | [−143.57, −130.68] | 7.84 | −2.0953 |
| | | | gap | +1.49 | [−21.39, +26.64] | 28.51 | — |
| `skipc − base` | 0 | 8 | wall | +821.27 | [+757.13, +885.86] | 70.00 | +12.5490 |
| | | | busy_sum | +785.62 | [+738.32, +833.18] | 51.64 | +12.0043 |
| | | | gap | +46.70 | [+6.25, +93.29] | 43.99 | — |
| `skipc − skipr` | 1 | 8 | wall | +978.37 | [+930.66, +1026.34] | 51.03 | +14.9496 |
| | | | busy_sum | +934.30 | [+900.46, +968.28] | 36.23 | +14.2762 |
| `base − base` (null) | 1 | 7 | wall | +1.92 | [−44.01, +48.11] | 49.79 | +0.0293 |
| | | | busy_sum | +16.08 | [−19.15, +51.47] | 38.10 | +0.2457 |

Three findings.

**1. The naive ceiling is 137 µs/step, not the assignment's modelled 193.**
`skipr` removes 40 dispatches and saves 137.13 µs/step of busy time
(≈ 2.10 % of score at 0.015280 %/µs/step). The in-session null is +16.08
[−19.15, +51.47], so the contrast is ~7σ clear of the estimator's own zero.

**2. The 56 µs/step dispatch-boundary term does not materialise.**
Rule 41 prices a decode dispatch boundary at 1.4064 µs, so deleting 40
boundaries should have shown ≈ 56 µs/step of *wall* saving on top of the kernel
work, i.e. `gap` should have fallen. It did not: `gap` moved **+1.49 µs/step
[−21.39, +26.64]** — statistically zero — and the wall saving (135.93) equals
the busy saving (137.13) inside noise. Removing 9.9 % of the dispatch stream
(406.0 → 366.0 per step) bought no boundary time at all. The whole prize is the
kernel's own busy time, 137.13 / 40 ≈ **3.43 µs per input-norm dispatch**.
Rule 41's per-boundary price evidently applies to *added* boundaries that break
an existing pipeline, not to these already-pipelined ones.

**3. A value-content confound of ~7× the prize exists, so the deletion arms
cannot be read as a clean price.** `skipr` and `skipc` run at *identical*
366.0 dispatches/step and 45.0 CBs/step, yet `skipc` is **+934.30 µs/step**
busier. Nothing structural distinguishes them — only the values flowing
through. The most plausible mechanism is the MoE router: garbage hidden states
change top-k expert selection, and therefore the expert-gather DRAM access
pattern (denormal handling is an alternative). Either way, on this model an
E0-style "delete the dispatch" probe is **not sound in isolation**: any deletion
arm silently carries a value perturbation whose contribution is unbounded by
the design. `skipc` is *not* a usable upper bracket — it is a slower arm, not a
bounding one.

Finding 3 is why stage 1 is not finished at 137 µs/step.

### Stage 1b — the bit-exact confound-free arm

Two additional arms on the same binary, both **numerically identical to
shipped** (`maximum(x, x) == x` bit-for-bit, so every route, every gather and
every downstream value is unchanged):

| arm | mode | graph |
| --- | --- | --- |
| `max1` | 3 | `y = inputNorm(input)`; `normalized = maximum(y, y)`. One norm + one glue dispatch per layer. |
| `dupn` | 2 | `normalized = maximum(inputNorm(input), inputNorm(input))`. **Two** norms + the same one glue dispatch per layer. |

`dupn − max1` therefore differs by exactly one input-RMSNorm dispatch per layer
and by nothing else — same values, same dispatch classes, same command-buffer
structure. By symmetry it is the confound-free price of the norm edge, and it
brackets the deletion estimate from the other side. `max1 − base` is a free
by-product: the price of inserting 40 near-zero-work dispatches into the decode
chain, an independent test of finding 2.

`ORDER="base max1 max1 base dupn max1 max1 dupn"`, `REPS=4`, `STEPS=200`
⇒ n = 8 for `base|max1` at offset 0, n = 8 for `max1|dupn` at offset 0, n = 8
sign-balanced for `base|dupn` at offset 1, and n = 8 `max1|max1` nulls at
offset 1.

#### Instrument receipts

Rule 39 reachability, measured over all 32 timed slots (not just the
pre-check), plus the bit-exactness receipt:

| arm | dispatches/step | cbs/step | token-stream sha256 (16) |
| --- | --- | --- | --- |
| `base` | 406.0 | 45.0 | `a1ab08a6ea7ac45e` |
| `max1` | 446.0 (+40 glue) | 45.0 | `a1ab08a6ea7ac45e` |
| `dupn` | 486.0 (+40 glue +40 norm) | 45.0 | `a1ab08a6ea7ac45e` |

All three arms emit **one** distinct token stream across all 32 slots, and it
is the same stream `base` emits in stage 1a. The +40/+80 dispatch steps land
exactly as designed, so MLX performed no CSE on the duplicated norm. `cbs/step`
is 45.0 everywhere, which removes command-buffer repacking as a confound.

Per-arm means (µs/step): `base` wall 8217.3 / busy 7970.0; `max1` wall 8258.7 /
busy 8001.5; `dupn` wall 8232.2 / busy 7977.1. `busy_sum / busy_union = 1.0000`
for every arm — these dispatches are serial, with no overlap to hide behind.

#### Results

| contrast | offset | n | metric | Δ µs/step | 95 % CI | SD | score % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `max1 − base` | 0 | 8 | wall | +50.88 | [−21.10, +123.48] | 85.92 | +0.7774 |
| | | | busy_sum | **+30.03** | [+7.04, +53.09] | 27.43 | +0.4589 |
| | | | busy_union | +30.03 | [+7.04, +53.09] | 27.43 | +0.4589 |
| | | | gap | +14.37 | [−30.81, +68.97] | 56.05 | — |
| `dupn − max1` | 0 | 8 | wall | −16.76 | [−35.02, +1.54] | 21.91 | −0.2561 |
| | | | busy_sum | **−25.87** | [−40.02, −11.68] | 17.00 | −0.3952 |
| | | | busy_union | −25.87 | [−40.02, −11.68] | 17.00 | −0.3952 |
| | | | gap | +9.66 | [−9.96, +30.91] | 23.49 | — |
| `dupn − base` | 1 | 7 | wall | +16.09 | [−16.01, +48.31] | 34.71 | +0.2458 |
| | | | busy_sum | **+8.61** | [−17.71, +35.02] | 28.47 | +0.1315 |
| | | | busy_union | +8.61 | [−17.71, +35.02] | 28.47 | +0.1315 |
| | | | gap | +7.14 | [−10.31, +25.86] | 18.99 | — |
| `max1 − max1` NULL | 1 | 8 | wall | +25.04 | [−43.23, +93.87] | 81.73 | +0.3826 |
| | | | busy_sum | +2.01 | [−9.20, +13.23] | 13.41 | +0.0307 |
| | | | gap | +16.45 | [−33.68, +78.97] | 62.46 | — |

The null is healthy on the busy axis: +2.01 µs/step with SD 13.41, consistent
with the tabulated `nat` absolute-busy σ = 14.74. The wall axis is noisier here
than the tabulated σ = 29.96 (SD 81.73), so **every conclusion below is taken
on the busy axis**; wall is quoted only for direction.

#### Finding 4 — the fusion prize is ≤ 35 µs/step, and stage 1a's 137 was contamination

`dupn − base` adds one full redundant input-RMSNorm **and** one glue dispatch
per layer — 80 extra dispatches/step, a +19.7 % increase in dispatch count —
for **+8.61 µs/step busy, 95 % CI [−17.71, +35.02]**. That is statistically
indistinguishable from zero.

Both components of that sum are physically non-negative, so the sum bounds each
part. The gross prize of removing the input-norm edge is therefore

> **≤ 35.02 µs/step (95 % upper bound) ≈ 0.535 % score**, point estimate ≈ 8.6 µs/step ≈ 0.13 %.

This is **5.5× smaller** than stage 1a's `skipr` estimate of −137.13 µs/step and
**22× smaller** than the assignment's modelled 193 µs/step. The difference is
now directly attributable, because stage 1a's arms were not bit-exact:

| stage | arm | token-stream sha256 (16) | same as base? |
| --- | --- | --- | --- |
| 1a | `base` | `a1ab08a6ea7ac45e` | — |
| 1a | `skipr` | `b2a3ca01c7e12a12` | **no** |
| 1a | `skipc` | `d9bdecea7bfdc7bc` | **no** |
| 1b | `max1`, `dupn` | `a1ab08a6ea7ac45e` | **yes** |

`skipr` decodes a different token sequence, so it routes to a different set of
experts and does a different amount of gather-GEMM work. Stage 1a finding 3
already showed that two arms with *identical* dispatch and cbs counts can
differ by 934 µs/step purely through routing. `skipr − base` = −137 µs/step is
the same contamination at smaller magnitude, not the price of 40 norm
dispatches. **The deletion-probe methodology is unsound on this MoE model and
its stage 1a numbers should not be quoted as a ceiling.**

#### Finding 5 — the decomposition is unreliable, but the bound is not

Taken separately the two halves disagree with physics: `dupn − max1` adds 40
real RMSNorm dispatches and *lowers* busy time by 25.87 µs/step, with a CI that
excludes zero. Adding work cannot reduce GPU busy time directly, so this is a
second-order artefact. The most plausible mechanism is MLX buffer donation:
`max1` computes `maximum(y, y)`, whose single input is referenced twice, which
blocks donating that buffer to the output; `dupn` computes `maximum(a, b)` from
two singly-referenced buffers and can donate one. `max1`'s glue dispatch is
then more expensive than `dupn`'s, which inflates `max1 − base` (+30.03) and
depresses `dupn − max1` (−25.87) by roughly the same amount.

Additivity confirms the two halves are self-consistent even so:
`(max1 − base) + (dupn − max1) = +4.16` µs/step versus the directly measured
`dupn − base = +8.61` µs/step — well inside the CI.

The decision does not depend on resolving this. `max1` is only an intermediate;
the quantity that bounds the fusion prize is the end-to-end `dupn − base`
contrast, which involves no `maximum(x, x)` on either side of the comparison in
a way that could inflate it — and any donation penalty in `dupn`'s glue
dispatch makes the +8.61 an **over**-estimate of the norm cost, so the bound
holds a fortiori.

#### Finding 6 — the assignment used rule 41's WIDE constant where TINY applies

Rule 41 is calibrated in two regimes: **WIDE 1.4064 µs** and **TINY 0.7258 µs**
per dispatch, a 1.94× ratio (`research/DATASET_ANALYSIS.md` §6). The assignment
priced the boundary term at ~56 µs/step, which is 40 × WIDE. An input-RMSNorm
in decode is one row of 2,048 elements — 4 KB in, 4 KB out. That is a TINY
dispatch, so the applicable term is 40 × 0.7258 = **29.0 µs/step**, not 56.3.

Stage 1b corroborates the TINY constant directly. `max1 − base` inserts 40
near-zero-work elementwise dispatches for **+30.03 µs/step busy = 0.751
µs/dispatch**, within noise of 0.7258.

So two independent routes now converge on the same answer:

| route | prize for removing the 40 norm dispatches |
| --- | --- |
| rule 41 TINY × 40 | 29.0 µs/step ≈ 0.44 % score |
| this experiment, `dupn − base` 95 % UB | ≤ 35.02 µs/step ≈ 0.535 % score |

Both are well under the ~80 µs/step bar. The stop decision does not depend on
which one is preferred, which is the strongest form this conclusion could take.

Two caveats are recorded honestly rather than smoothed over:

1. The two stage-1b arms disagree with each other. 80 added dispatches
   (`dupn − base`, +8.61) cost *less* than 40 added dispatches (`max1 − base`,
   +30.03). Under the donation reading of finding 5, `max1 − base` is inflated
   by allocator churn and its agreement with TINY is partly coincidental. The
   end-to-end bound is unaffected either way.
2. Rule 41 attributes 76.3 % of a boundary (1.073 µs) to serialization and
   ordering, which must land in `gap`. **`gap` is statistically zero in all
   four contrasts** (+14.37, +9.66, +7.14, +16.45 µs/step, every CI spanning
   zero). On this GPU-bound decode stream that component is hidden behind GPU
   execution, so the fraction of a boundary that is actually *recoverable* here
   is nearer the 22.4 % fixed cost than the full constant.

Point 2 is flagged for the advisor: it affects any NET estimate whose prize is
"removed boundaries", and it argues that the recoverable-per-dispatch figure
should be re-derived on the `nat` decode stream rather than inherited.

### Stopping rule

The assignment's stopping rule is: if the measured ceiling is below
~80 µs/step, stop and write it up as a null — the family is dead and stage 2
is not run.

**The rule fires. Stage 1 is terminal and stages 2 and 3 are not run.**

The ceiling is ≤ 35.02 µs/step at the 95 % upper bound, against a bar of
~80 µs/step. The bound is on the *gross* prize: it assumes fusion removes the
whole norm edge and adds nothing back. Every real shape adds work back —

- shape (a) (pass a precomputed 1/RMS scalar, keep a separate reduce kernel)
  keeps the reduce dispatch and so recovers only part of an already-tiny edge;
- shape (b)+(a) (previous kernel emits partial sums-of-squares, QKV finishes
  them in a prologue) adds a prologue to **R = 5,120** threadgroups per QKV
  dispatch, which is the term that killed naive full fusion at −115 µs/step.

so their NET is bounded above by a number that is already inside the noise
floor of the instrument, before subtracting any give-back. There is no shape in
this family whose NET can be shown positive with the available measurement
precision, so spending the stage 2 ALU-injection ladder and the offline AGX
census on it would be measuring give-back against a prize that does not exist.

## Stage 2 — ALU-injection ladder

**Not run.** Stage 1's ceiling (≤ 35 µs/step, 95 % UB) is below the ~80 µs/step
stopping bar. See "Stopping rule" above.

## Stage 3 — implementation

**Not run.** No shape in this family can have a positive NET at the measured
ceiling.

Accordingly no change ships in `Sources/`. The probe knob used to obtain these
numbers is preserved as a re-appliable patch rather than as live scored code —
see "Probe patch" below.

## Reproduction

Both stages ran on the M4 Pro research host against
`BASE_SHA=3f430f6f17ac4bfbac5f47767ca78cb89d84a760`. Re-apply the probe patch
first (see below), then:

```bash
# stage 1a — deletion arms (32 runs, ~25 min). Superseded; kept for provenance.
env OUT=/tmp/maple-r91a REPS=4 STEPS=200 REGIMES=nat \
  bash research/maple_r91a_input_norm_ab.sh

# stage 1b — bit-exact arms (32 runs, ~25 min). This is the result of record.
env OUT=/tmp/maple-r91b REPS=4 STEPS=200 REGIMES=nat \
  ORDER="base max1 max1 base dupn max1 max1 dupn" \
  bash research/maple_r91a_input_norm_ab.sh

# stage 1b contrasts
for spec in "base max1 0 base_max1_o0" "max1 dupn 0 max1_dupn_o0" \
            "base dupn 1 base_dupn_o1" "max1 max1 1 max1_max1_o1"; do
  set -- $spec
  python3 research/maple_r88a_additivity.py --steps 200 --drop-first 1 \
    --arms $1 $2 --offset $3 \
    --json-out /tmp/maple-r91b/stats/$4.json /tmp/maple-r91b/nat/*.log
done

# bit-exactness receipt (must print 1)
for f in /tmp/maple-r91b/nat/*.tokens; do shasum -a256 < "$f"; done \
  | cut -d' ' -f1 | sort -u | wc -l
```

## Probe patch

Stage 1 is a pricing experiment with a null outcome, so nothing ships in
`Sources/`. The probe knob that produced every number above is preserved as
`research/maple-fern-r91-stage1-probe.patch`, whose header records the base SHA
and the re-apply command. It adds `DARKBLOOM_R91_INPUT_NORM_PROBE` to
`LagunaRuntimeModel.swift` with modes `0` base, `-1` skipr, `-2` skipc,
`2` dupn, `3` max1.

The `skipr`/`skipc` modes are **not** bit-exact and are research-only; they
change the decoded token stream by construction, which is exactly what finding
4 shows makes them unusable as a ceiling. The `dupn`/`max1` modes are bit-exact
and are the ones that carry the result. Neither is proposed for the scored
path, so no correctness gate was run against a shipping candidate — there is no
shipping candidate.
