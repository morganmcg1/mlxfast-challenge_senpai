# Pre-registration — decode marginal-cost ledger (PR #218)

Assignment `maple-2026-08-07e-decode-marginal-cost-ledger`, revision `r1`,
student `maple-fern`. Base `0c86fc3b5b637a15eee8f95a82d30e67e3e481b3`.

**This file is committed before the first probe run.** Every verdict and every
predicted exposure factor `E` below is a prediction made from static dataflow
only, with no timing evidence from this session. Nothing in this file may be
edited after the first probe run; corrections go in the deliverable.

## 1. The predicate being tested

Advisor formulation (PR #218 §1.2):

> Dispatch `X` is a **side-branch** iff every consumer of `X` also transitively
> depends on a sibling `Y` whose duration is much greater than `X`, where `Y`
> is issued no later than `X`. Otherwise `X` is a **chain-link**.

Prediction: `E = measured_injection_slope / census_us_per_step` is near `0` for
side-branches and near `1` for chain-links.

All line numbers are `Sources/MLXFastModel/LagunaRuntimeModel.swift` at base
`0c86fc3b`, except the lm-head row which is `Sources/MLXFastModel/LagunaLmHeadPrune.swift`.

## 2. Decode graph skeleton (one layer, B=1, L=1)

```
x ──► [lagunaResidualRMSNormRouter :10359]  ──► summed h
                │                            ──► normalized
                │                            ──► routerLogits
                └────────────────────────────► routerKeys
normalized ──► [norm+affine QKV :5741 / decode_nvfp4_qkv :5761] ──► qkv
                     ├──► q,k,v ──► [sliding attn :5972 | full attn :5998] ──► attnOut
                     └──► gate rows ──► [gate_sp :5802] ──► gateLogits
attnOut, gateLogits ──► [oproj_act :6186] ──► r
routerKeys ──┬──► [router top8 :10003 → :8881] ──► inds, weights
             └──► [routed gate/up QMV :10054/:10057] ──► activated
x          ──► [shared QMV :10104] ──► sharedActivated
activated, weights, sharedActivated, residual
            ──► [routed+shared down+residual :10121, kernel :7846] ──► layer out
```

Terminal: `model.norm` then `[lmhead_int5_base_coarse_delta :10969 →
LagunaLmHeadPrune.swift:266]` → logits (the eval root).

Two diamonds are visible in that skeleton:

- **Diamond D1 (router).** `routerKeys` forks into the standalone top-8
  (`:10003`) and the routed gate/up QMV (`:10054`). Under
  `lagunaRouterPrecomputedKeysEnabled` the QMV consumes `routerKeys`
  **directly** (`lagunaRoutedSwiGLUQMVPackedTop8`, `:10057`) and does **not**
  consume `inds`. The arms rejoin at `lagunaRoutedSharedDownResidual`
  (`:10121`), which reads `routerWeights` from the short arm and
  `routedActivated` from the long arm. Short arm is free.
- **Diamond D2 (gate).** `qkv` forks into the attention chain
  (`:5972`/`:5998`) and the per-head gate softplus (`:5802`). They rejoin at
  the fused gated o-proj (`:6186`).

## 3. Pre-registered verdict table

`E_pred` is a point prediction; `E_range` is the interval I will treat as
"prediction confirmed".

| # | target | site(s) | calls/step | census µs/step | verdict | `E_pred` | `E_range` |
|---|---|---|---|---|---|---|---|
| T0a | `decode_router_top8_ordinal_table_norm` | call `:10003`, dispatch `:8881`, kernel `:8801` | 39 | 185.7 | **side-branch** | 0.00 | [-0.16, 0.16] |
| T0b | fused QKV `decode_nvfp4_qkv` / norm+affine QKV | `:5741`, `:5761`, kernels `:4692`/`:5226` | 40 | (from A2 census) | **chain-link** | 1.00 | [0.70, 1.30] |
| T1a | `residual_rms_router_rpg8_keys_v1` | `:10359`, kernel `:997` | 39 | 305.1 | **chain-link** | 1.00 | [0.70, 1.30] |
| T1b | `rmsbfloat16` (standalone input RMSNorm) | `:5758` `inputNorm(input)` | 41 | 124.6 | **chain-link** | 1.70 | [1.00, 2.20] |
| T1c | `lmhead_int5_base_coarse_delta` | `:10969`, kernel `LagunaLmHeadPrune.swift:266` | 1 | 427.0 | **chain-link** | 1.00 | [0.70, 1.30] |
| T2a | `shared_nvfp4_swiglu_qmv_rows1` | `:10104`, kernel `:6797` | 39 | 237.5 | **side-branch** | 0.10 | [-0.10, 0.35] |
| T2b | `gate_sp_h64` + `gate_sp_h48` | `:5802`, kernel `:4324` | 30 + 10 | 262.3 | **side-branch** | 0.10 | [-0.10, 0.35] |
| T2c | routed gate/up QMV | `:10054` / `:10057` / `:10068` / `:10078` | 39 | — | **chain-link** | 1.00 | [0.70, 1.30] |
| T2d | routed+shared down + residual | `:10121`, kernel `:7846` | 39 | — | **chain-link** | 1.00 | [0.70, 1.30] |
| T3a | `sliding_fused_attn_ring_v1` | `:5972`, wrapper `:1719`, kernel `:1369` | 30 | — | **chain-link** | 0.95 | [0.70, 1.30] |
| T3b | `full_fused_attn_grow_v1` | `:5998`, wrapper `:2220`, kernel `:1818` | 10 | — | **chain-link** | 0.95 | [0.70, 1.30] |
| T3c | `oproj_act_h64` | `:6186`, kernel `:4359` | 40 | — | **chain-link** | 0.95 | [0.70, 1.30] |

Counts of `calls/step` are the census values carried in from research state
§4.12.3. The instrument reports its own observed call count per name; where the
two disagree the observed count is authoritative and the disagreement is
reported.

## 4. Per-row reasoning

**T0a — router top-8, side-branch.** Consumers of the top-8 kernel are `inds`
and `weights`. Under the promoted `lagunaRouterPrecomputedKeysEnabled` branch
(`:10046-:10060`) the routed gate/up QMV takes `routerKeys` from the producer
directly, so `inds` has no consumer on that branch and `weights` has exactly
one: `lagunaRoutedSharedDownResidual` (`:10121`). That consumer also depends on
`routedActivated`, produced by the routed QMV — a sibling that forks from the
same `routerKeys` and is issued no later. The routed QMV moves the 8-expert
gate/up bank; the top-8 moves 256 fp32 scores. Predicate satisfied. This is the
A1 anchor and #204 already measured its deletion saving at `-0.9 ± 12.1 µs`.

**T0b — fused QKV, chain-link.** Everything else in the layer is downstream of
`qkv`: attention (`:5972`/`:5998`), the gate rows (`:5802`), and through those
the o-proj (`:6186`). At the moment it issues, its only unfinished sibling is
the previous layer's tail, which its consumers do not depend on. No covering
sibling exists. #174 measured `E = 0.999 [0.87, 1.14]`. A2 anchor.

**T1a — residual+RMSNorm+router, chain-link.** Sole producer of `summed`,
`normalized`, `routerLogits` and `routerKeys`; the entire remainder of the
layer plus the next layer's attention are downstream. Its own input is the
o-proj output, so it cannot overlap with the layer it terminates. Census floor
151.0 µs/step vs census 305.1 µs/step — if the slope lands near 305 the row is
the largest genuinely purchasable decode saving in the ledger.

**T1b — standalone `rmsbfloat16`, chain-link with census understatement.** This
is `inputNorm(input)` at `:5758`, taken only on layers where the fused
norm+affine QKV declines (NVFP4 tail layers and guard declines). Its consumer
is the projection immediately below it; nothing larger is in flight. Structural
verdict is chain-link, so `E ≈ 1` on the predicate. But the census row is
internally inconsistent: 124.6 µs/step over 41 calls is 3.04 µs/call against a
measured single-threadgroup floor of `a + phi = 3.130 µs` (#196), and #204
recorded the effective figure as 1.82 µs/call. If the census undercounts by the
ratio `3.130 / 1.82 = 1.72`, the injection slope should come back **above**
census. I therefore predict `E_pred = 1.70`, and I am pre-registering that an
`E` materially above 1 on this row is evidence the census row is wrong rather
than evidence the instrument is wrong — provided A1 and A2 both pass.

**T1c — lm-head coarse/delta, chain-link.** One call per step, at the very end
of the graph. Its only consumer is the logits eval root. No sibling covers it;
by construction the step cannot retire until it does. Largest single census row
in decode at 427.0 µs/step.

**T2a — shared expert QMV, side-branch (ambiguous, top measurement priority).**
Issued at `:10104` after the routed QMV at `:10054`, and its only consumer is
the join node `:10121`, which also depends on the routed QMV. Predicate is
satisfied *if* the routed QMV is "much greater". Routed moves 8 experts of the
`[gate; up]` bank; shared moves 1 expert. That is roughly 8x bytes — above the
3x flag threshold but not overwhelming, and the shared QMV is issued strictly
later, so it can only hide in the routed QMV's *residual* tail. #174 reported
`E = 0.10`. I predict `E = 0.10` but flag this row as the one most likely to
falsify the predicate in either direction, and as the row whose shadow ratio I
most expect to fall below 3x.

**T2b — per-head gate softplus, side-branch.** `gateLogits` has exactly one
consumer, the fused gated o-proj at `:6186`, which also consumes the attention
output. The attention chain forks from the same `qkv` and is issued no later
(`:5802` follows `:5761`). Attention is `E >= 0.90` sized; the gate is a
`nHeads x hidden` GEMV. Predicate satisfied. #174: `E = 0.10`.

**T2c — routed gate/up QMV, chain-link.** It is the long arm of diamond D1. The
only sibling any consumer of `activated` also depends on is the top-8 short arm
and the shared QMV, both smaller. Predicate not satisfied.

**T2d — routed+shared down+residual, chain-link.** The join node of D1 and the
layer's terminal dispatch. Nothing is in flight beside it except the next
layer's dependence on its own output.

**T3a/T3b — fused attention, chain-link.** The only sibling covering them is
`gate_sp`, which is much smaller (that is exactly why `gate_sp` is T2b's
side-branch). #174: `E >= 0.90`. Note these two kernels mutate the KV ring/
append buffers in place (`:5972` `rotating.fusedRingAdvance()`, `:5998`
`simple.fusedAppendAdvance()`), so duplicate copies must be given scratch KV
buffers and must not re-run `fusedRingPrepare()` / `fusedAppendPrepare()`.
That makes them the highest-implementation-risk rows and they are last.

**T3c — fused gated o-proj, chain-link.** Sole path from attention output to
the layer residual. #174: `E >= 0.94`.

## 5. Aggregate pre-registered predictions

1. **A1 passes**: `|slope(T0a)| < 30 µs` per copy-set per step.
2. **A2 passes**: `slope(T0b)/census(T0b) ∈ [0.7, 1.3]`.
3. Every row I called `chain-link` returns `E >= 0.7`; every row I called
   `side-branch` returns `E <= 0.35`. The predicate is falsified if any single
   row lands on the wrong side of `E = 0.5`.
4. The three largest genuinely purchasable decode savings will be, in order,
   `lmhead_int5_base_coarse_delta` (T1c), `residual_rms_router_rpg8_keys_v1`
   (T1a), and one of the routed QMV / down+residual pair (T2c/T2d).
5. Summed over the twelve rows, the chain-link slopes will account for **less
   than** the 4143.6 µs/step decode total, because weight-streaming time inside
   each chain-link kernel is counted once per row.
6. `K=1→2` and `K=2→5` slopes will agree within 25% on chain-link rows and may
   diverge on side-branch rows as the shadow saturates.

## 6. Instrument contract (fixed before measurement)

- Env: `DARKBLOOM_DECODE_DUP_TARGET=<name>`, `DARKBLOOM_DECODE_DUP_K=<K>`,
  `DARKBLOOM_DECODE_DUP_CHAIN=1`.
- `K = 1` is byte-identical behaviour to the unmodified runtime: no scratch
  arrays, no extra roots, no extra branch taken.
- Each duplicate writes its own freshly allocated output. No aliasing, no
  in-place reuse, no `* 0`, no epsilon.
- Duplicates are registered as extra eval roots and are listed **before** the
  real root in the same `asyncEval` call.
- The instrument counts its own invocations per target name per step and the
  run asserts `n_dispatch(K) - n_dispatch(1) == n_calls_per_step * (K - 1)`
  against the GPUPROF hook. A failed assertion voids the run.
- Protocol per reported row: `research/decode_probe.py`, 1200 timed steps,
  `CLOCK_UPTIME_RAW`, drop first 16 steps, run-median as the unit of
  replication, palindromic ABBA / ABCCBA ordering, minimum 3 paired blocks.

## 7. Kill rules (restated, binding)

1. A1 slope `>= 30 µs` or A2 ratio outside `[0.7, 1.3]` ⇒ publish no ledger
   rows; report the instrument as biased with the measured bias.
2. Dispatch-count assertion failure at any `K` ⇒ that run is void.
3. Any token divergence ⇒ stop that target and debug aliasing.

_Pre-registered by an AI agent (OpenHands) acting as research student
`maple-fern` for the Senpai maple campaign._
