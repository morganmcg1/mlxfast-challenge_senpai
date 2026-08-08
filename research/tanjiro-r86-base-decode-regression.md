# R86-A: where the 1.44 % between our base and our best-ever submission actually lives

Assignment: `maple-r86-a-base-decode-regression`, revision `r86-a-rev1`, PR #460.
Base `f64456dd2dc503af080dca65bddfb922164c7bc5`. Host: Apple M4 Pro, 20 cores,
Apple GPU generation 16 (never selects `_nax`).

W&B: <https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/zvqcx1h8>
(run id `zvqcx1h8`, `job_type=diagnosis`). It carries the six per-arm timings,
the static classification of all 19 changed editable paths, and the
four-cluster carrier decomposition as tables.

## 0. The two numbers the assignment asks to keep separate

| what | submission | officialScore |
| --- | --- | --- |
| leaderboard bar (someone else's, re-verified top this campaign) | `cc6ddc1` by `a-github-name` | **2.6165035** |
| our own best-ever promoted submission | `97a5090c` | **2.58882784082067** |
| our current integration base's own control | `25b0b722` | **2.55158458026643** |

Runners-up behind the bar: 2.6063 / 2.6055 / 2.6040 / 2.6024 / 2.6012.
So the gap the assignment targets (base -> our best-ever) is 1.44 %, and even a
complete recovery still leaves 1.07 % to the bar. Both facts matter for how much
this is worth.

## 1. Reconstruction method and its fidelity calibration

I did **not** use fern's harness. I reconstructed both trees with
`mlxfast reset <submission> -f` onto the organizer base `c5b0a13`:

- `tanjiro/r86-frontier-content` @ `149212f78ef630da4e00f1123420fc6250e5e9a9`
  = the `97a5090c` editable surface.
- `tanjiro/r86-control-content` = the `25b0b722` editable surface, reconstructed
  **only as a fidelity calibration**.

The calibration is what licenses every static claim below. Reconstructing our
base's *own* control submission reproduced the base editable surface **exactly**,
with two exceptions: `Sources/MLXFastTransform/AffineMetadataCoding.swift` and
`Sources/MLXFastTransform/TiedHeadMetadataCoding.swift`, which our repo keeps as
0-line stubs and which `reset` refills with organizer-pristine content (+438 and
+401 lines). Those two files are therefore **tool artifacts, not real
differences**, and `mlxfast reset` is faithful for every non-empty file.

## 2. Correction 1: the delta is 17 files, not 11

Diffing the 97 `editablePaths` between base `f64456d` and frontier `149212f`
gives **19** differing files, i.e. **17 real** after removing the two artifacts.
The assignment's "11 files" (+`RoPEApplication.swift` = 12) is the delta to the
base's *best-overlap* submission (85/97 paths), not to `97a5090c`.

There is no organizer-side confound: organizer `3e165fa5` -> `c5b0a13` touched
5 editable paths and **0 non-editable paths**.

## 3. Correction 2: every file the assignment asked me to bisect is inert

Non-comment, non-blank changed-line counts, base -> frontier:

| file | non-comment changed lines | verdict |
| --- | --- | --- |
| `MLXLMCommon/.../BaseConfiguration.swift` | **0** | comment-only |
| `MLXLMCommon/.../BatchKVCache.swift` | **0** | comment-only |
| `MLXLMCommon/.../CompilableKVCache.swift` | **0** | comment-only |
| `MLXLMCommon/.../CompilableRotatingKVCache.swift` | **0** | comment-only |
| `MLXLMCommon/.../CompiledDecode.swift` | **0** | comment-only |
| `MLXLMCommon/.../Evaluate.swift` | **0** | comment-only |
| `MLXLMCommon/.../KVCache.swift` | **0** | comment-only |
| `MLXLMCommon/.../RoPEApplication.swift` | 1 comment line | comment-only |
| `Sources/MLXFastModel/LagunaConfig.swift` | 0 | comment-only |
| `Sources/MLXFastModel/LagunaRuntimeWeights.swift` | 0 | comment-only |
| `Sources/MLXFastModel/LagunaLmHeadPrune.swift` | 0 | array-literal reflow |
| `Sources/MLXFastTransform/Transform.swift` | +51 / -4 | **gemma4-only branch**; the Laguna branch emits empty metadata, so inert for this model |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | **+266 / -226** | **real** |
| 4 x `_nax` C++/Metal (below) | real text, see §4 | **default-path inert** |

The comment-only churn is the "Lever 1" byte-budget comment relocation
(commit `8237f43`). There are no `#line` / `#file` / `#function` macros in any of
those files, so the relocation cannot change codegen.

**Consequence: the assignment's Step-3 decode-first bisection over
`CompiledDecode` / `CompilableKVCache` / `CompilableRotatingKVCache` / `KVCache` /
`BatchKVCache` / `Evaluate` / `BaseConfiguration` is provably futile.** The
hypothesised ~38 us/step of decode cannot live in any of those seven files
because none of them contains a single differing line of code.

## 4. The four `_nax` files are also inert at the ranked default

Direction check (`git grep` over both trees) — note this is the *opposite* of the
direction stated in the assignment: the **slower base** carries scaffolding the
**faster best-ever submission** does not have.

| token | base `f64456d` (2.5516) | frontier `149212f` (2.5888) |
| --- | --- | --- |
| `darkbloom_nax_gather_probe` (from PR #170) | present | absent |
| `darkbloom_expert_bk128` (from PR #138) | present | absent |
| `darkbloom_steel_regular_skinny_tile` (H2/H2-r2) | present | absent |
| `Dshadow`, `loader_w2` shadow scaffolding | present | absent |
| `pair_planes` in `LagunaRuntimeModel.swift` | 0 | 26 |

Each of those four is inert on the ranked default path:

- `DARKBLOOM_NAX_GATHER_PROBE` default is `kNaxGatherProbeDefault = ""` -> probe
  `0`. Every use of `Dshadow` / `loader_w2` / the extra barriers is behind
  `if constexpr (kProbeM2 / kProbeStage / kProbeB2)`, so at probe 0 the shadow
  accumulator and the shadow loader are dead on declaration. The kernel name gets
  its `_pb_N` suffix only when probe != 0, so name and template argument list stay
  byte-identical to the frontier.
- `DARKBLOOM_EXPERT_BK128` default OFF -> BK stays 64.
- `DARKBLOOM_STEEL_REGULAR_SKINNY_TILE` default OFF (H2-r2 made it opt-in).
- `kWideLoadShapeOk` is **widened**, not narrowed:
  base `kWidenShapeOk && ((kSrcBytes == 16) || (kSrcBytes == 32))` vs frontier
  `kWidenShapeOk && (kSrcBytes == 16)`. The extra arm is the 32-byte (BK=128)
  geometry, unreachable while `DARKBLOOM_EXPERT_BK128` is off.

The env-knob inventories of `quantized.cpp` are otherwise identical between the
two trees.

The one residual `_nax` risk I cannot rule out statically is second-order: the
embedded `mlx-generated/fp_quantized_nax.cpp` is compiled **at runtime**, and the
base's copy is 132 lines longer. Identical post-DCE binaries are the expected
outcome, but larger pre-DCE function bodies can shift inlining and scheduling
heuristics. That is a weak mechanism and it cannot be tested on this host.

## 5. By elimination, `LagunaRuntimeModel.swift` is the sole carrier — and it
## decomposes into four clusters, only one of which can be the carrier

Of 17 real differences, 12 are comment/format-only, 1 is gemma4-only, and 4 are
default-path-inert `_nax` scaffolding. That leaves exactly one file with live
behavioural change on the ranked path:
**`Sources/MLXFastModel/LagunaRuntimeModel.swift`** (379 insertions / 283
deletions raw; +266 / -226 non-comment), the scored forward pass.

Its ~30 hunks fall into four clusters. This decomposition matters, because three
of the four are **not** candidate regressions:

| cluster | lines | which side has it | verdict |
| --- | --- | --- | --- |
| **A. fused-attention softmax reduction** (`lagunaFullFusedAttentionKernel`, ~1466-2260): frontier `threadgroup U outputs[4*BN*BDP]` with `pair_planes` / `pair_plane_size` / `pair_global_factor1`; base `threadgroup float4 outputs4[BN*BDP]` | net +14 `pair_*` lines in frontier | differs both ways | **the only viable carrier** |
| B. `LagunaFullParamsMemoStore` — single-entry memo for the full-attention uniform buffer, keyed on `(writeIdx, capacity)` cache geometry, `DARKBLOOM_FULL_PARAMS_MEMO=0` ablation | 40 | **base only** | added *after* `97a5090c`; a decode-side win, not a regression |
| C. `lagunaSharedSwiGLUQMVRows1Kernel` + pairwise-scale plane | 132 | **base only** | added after `97a5090c`; decode-side win |
| D. **PR #27 "M5 HARDWARE-CONSTANT INSTRUMENT"** — a research work-injection block whose own header says it *"deliberately SLOWS the tree"*; every knob defaults to 0 so it is inert | 258 | **frontier only** | the base correctly deleted it; must **not** be re-imported |

Cluster D is the single most important operational finding here: **a wholesale
revert of `LagunaRuntimeModel.swift` to `97a5090c` content would re-import 258
lines of a deliberately-slowing measurement instrument** (inert at defaults, but
dead weight against the byte budget and a trap for anyone who flips a knob). The
candidate must be surgical, not wholesale.

Clusters B and C are work the team added *after* `97a5090c` and are decode-side.
Since decode only lost 0.578 % and §6 shows that loss is fully accounted for by
the shared seed forward, B and C evidently netted ~0 on M5 rather than
regressing. That leaves **cluster A**, the fused-attention softmax reduction, as
the only difference that can carry the 3.98 % prefill loss. `lagunaFullFusedAttention`
serves the ten full-attention layers on both the 512-token prefill and the
512-token decode seed, which is exactly the shared term §6 requires.

## 6. Correction 3: the loss is prefill-dominant, not decode-dominant

From the two ranked receipts:

| axis | base `25b0b722` | frontier `97a5090c` | delta |
| --- | --- | --- | --- |
| prefill_speedup | 1.921890350333331 | 2.001471 | **-3.98 %** |
| decode_speedup | 2.804381476645093 | 2.820684 | **-0.578 %** |

Score is `decode^0.75 * prefill^0.25`, so the loss decomposes as
`0.75 x 0.578 + 0.25 x 3.98 = 0.434 + 0.995 = 1.43 pp`, matching the observed
1.44 % gap. **69 % of the loss is on the prefill axis.**

The decode term is 0.578 % of 4933.57 us/step = **28.5 us/step**, not 38.

And it is very likely not an independent decode regression at all. The
teacher-forced decode pass carries the 512-token seed forward: with
`S = 0.097782 s` and `decode_seconds_per_token = 0.0049335732421875 s`, the seed
forward is sigma = 15.48 % of decode time. A *pure* seed-forward slowdown of
3.98 % predicts a 0.616 % decode loss; 0.578 % was observed. The whole M5
regression is consistent with **one prefill-side slowdown and zero independent
decode-step regression**.

## 7. Go / no-go: matched-pair local M4 measurement

`research/tanjiro-r86-matched-pair.sh`, ABBA-ordered (rev, base / base, rev /
rev, base), 3 repeats per arm, flipping **only**
`Sources/MLXFastModel/LagunaRuntimeModel.swift` between base HEAD and `149212f`
content, `MLXFAST_LOCAL_FAN_PROMPT=0`, `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` unset,
40 C thermal gate honoured on every arm, one model process at a time.

| arm | decode us/step | prefill us/token |
| --- | --- | --- |
| base r1 | 12922 | 1112 |
| base r2 | 12866 | 1113 |
| base r3 | 12954 | 1125 |
| rev r1 | 12896 | 1138 |
| rev r2 | 12861 | 1113 |
| rev r3 | 12975 | 1138 |

- decode: base 12914.0 +/- 44.5, rev 12910.7 +/- 58.4.
  **delta (base - rev) = +3.3 us/step, 95 % CI [-114, +121]** (pooled SD 51.9,
  SE_diff 42.4, t(4) = 2.776). Relative CI +/- 0.91 %, consistent with the
  documented +/- 0.73 % single-run local MDE.
- prefill: base 1116.7, rev 1129.7, delta -13.0 us/token, 95 % CI [-39, +13].

**Verdict: no detection, and the design is structurally underpowered.** The M5
target is 28.5 us/step; this design resolves +/- 118 us/step, ~4x coarser. Even at
n = 26 per arm (~3.7 h of runs) M4 would only just resolve the proportional case.
More importantly, under §6 there is no independent decode regression for an M4
decode test to find, and M4 prefill runs a *different kernel family* (prefill
1117 us/token here vs 191 us/token on M5, a 5.8x gap, because Apple GPU
generation 16 never selects `_nax`), so the M4 prefill null is not evidence
either way.

Two further reasons this arm was the wrong shape, both only visible after §5's
decomposition: the flip moved **all four clusters at once**, so cluster A's
hypothesised regression is measured net of clusters B and C (decode wins the base
added after `97a5090c`) and of cluster D (an inert instrument). A surgical
cluster-A-only flip is the arm that should have been run — but it would still be
~4x below this host's resolution, so it was not worth the extra 26 minutes.

This is **Null A (no local reproduction)** — but from lack of instrument
resolution, not from absence of effect.

## 8. Correctness of the candidate

All six arms produced the identical golden hash
`b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63` with
`passed_correctness = true` over `checked_steps = 130` and
`MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` unset. Reverting
`LagunaRuntimeModel.swift` to `97a5090c` content on top of the current base
**builds and is token-identical** on this host. (`passed_prefill_speedup_floor`,
`gpqa_ttft_passed` and `semantic_gpqa_passed` are false in *both* arms; those are
M4 artifacts of a 3x-slower host, not candidate defects.)

## 9. What this means for the programme

Our integration base measured **1.44 % worse on M5 than our own best-ever
submission**, and every experiment merged onto it since has been judged against
the worse base, mostly on M4 evidence. Recovering that 1.44 % is worth more than
almost any micro-optimisation currently in flight, and it is a *single-file*
question.

## 10. Recommended next step (not taken here — needs advisor authorisation)

One ranked M5 A/B that restores **cluster A only** — the
`lagunaFullFusedAttentionKernel` softmax reduction (`~1466-2260` of
`Sources/MLXFastModel/LagunaRuntimeModel.swift`) to its `97a5090c` form — keeping
the base's clusters B and C and **not** re-importing cluster D.

Do **not** submit the wholesale file revert I timed here. It is the arm that was
cheap to measure locally, not the arm that should be ranked: it would give back
two decode optimisations and re-import PR #27's deliberately-slowing instrument.

M5 is the only instrument that can resolve this. The effect is prefill-dominant,
M5 prefill selects `_nax`, and this host (Apple GPU generation 16) cannot. The
wholesale-revert variant already builds and is token-identical locally, so the
surgical variant is very likely to build and stay token-identical too, but that
must be re-checked before dispatch. The change is a near-wash on bytes, so the
262,144-byte growth cap is not at risk; re-run
`senpai/check-editable-budget.sh "$BASE_SHA"` anyway.

Expected outcome if §5 is right: prefill_speedup recovers toward 2.0015 and the
score toward ~2.5888. That is still below the 2.6165 bar, so the receipt will
read `rejected` for ranking — the value is the **measurement**, and the promoted
base it would justify. Every experiment merged since has been judged against a
base worth 1.44 % less than one we already own.
