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

Status: **stage 1 in progress** — numbers are filled in below as each stage
lands. Nothing in this file is a shipping change; the whole stage-1/stage-2
instrument is a research patch (`research/maple-fern-r91-stage1-probe.patch`)
and `Sources/` is unmodified on the submitted branch unless stage 3 wins.

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

A bit-exact "inject a redundant extra rmsNorm" ladder was considered and
rejected: MLX is lazy, so a discarded duplicate node is never evaluated, and
forcing it into the graph costs extra glue dispatches (`maximum`, `(y0+y1)*0.5`)
or extra unused kernel buffer inputs — i.e. it contaminates exactly the
quantity being measured.

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

### Results

_(to be filled in from `/tmp/maple-r91a/nat`)_

### Stopping rule

The assignment's stopping rule is: if the measured ceiling is below
~80 µs/step, stop and write it up as a null — the family is dead and stage 2
is not run.

## Stage 2 — ALU-injection ladder

_(only if stage 1 clears ~80 µs/step)_

## Stage 3 — implementation

_(only if a shape has positive NET)_

## Reproduction

```bash
# stage 1, nat regime (32 runs, ~35 min on the M4 Pro research host)
env OUT=/tmp/maple-r91a REPS=4 STEPS=200 REGIMES=nat \
  bash research/maple_r91a_input_norm_ab.sh

# stage 1, s1 regime for per-kernel attribution only
env OUT=/tmp/maple-r91a REPS=2 STEPS=200 REGIMES=s1 \
  bash research/maple_r91a_input_norm_ab.sh
```
