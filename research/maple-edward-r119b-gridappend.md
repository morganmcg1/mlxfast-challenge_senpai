# R119-B — shared+routed gate/up QMV grid-append

PR #712 · student `maple-edward` · assignment `maple-r119-b-shared-routed-qmv-gridappend`
rev `r119-b-rev1` · base `codex/mlxfast-maple-20260804-advisor` @
`f8cb5c5be3a0480799088a8f7efd5808553dc20a`
Host: Apple M4 Pro (20 GPU cores, 48 GiB, low-memory startup profile).
Apple GPU generation 16 — **no `_nax` prefill kernel family on this host**, so
every prefill number below is M4-family evidence only.

---

## 1. Checkpoint 1 — `dep_scope` verification, in my own words

The assignment requires me to prove, before writing Metal, that the shared-expert
gate/up QMV and the routed-expert gate/up QMV are independent within one decode
step. I re-derived this from the source rather than trusting the brief.

### 1.1 The two dispatches, as they exist today

Guest (shared expert), `Sources/MLXFastModel/LagunaRuntimeModel.swift`:

- source builder `lagunaSharedSwiGLUQMVRows1Source(halved:)` (:7121)
- kernel `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1`
- dispatch `lagunaSharedSwiGLUQMV` → `tiles = 256`, grid `(256*64,1,1)` = 16384,
  threadgroup `(64,1,1)`, one output `activated` of shape `[1,1,512]` bf16
- index algebra: `tile = threadgroup_position_in_grid.x`,
  `row = tile*2 + simdgroup_index_in_threadgroup`, so 256 TGs × 2 simdgroups
  cover all 512 shared-intermediate rows.
- inputs: `input` (the post-RMS normalized row), `fused_weight`, `fused_scales`.

Host (routed experts):

- kernel `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`
- dispatch `lagunaRoutedSwiGLUQMVPackedTop8` → grid `(8*256*64,1,1)` = 131072,
  threadgroup `(64,1,1)`, one output `activated` of shape `[1,1,8,1,512]` bf16
- index algebra: `group = threadgroup_position_in_grid.x`,
  `expert_slot = group % 8`, `tile = group / 8`,
  `logical_row = tile*2 + simdgroup_index_in_threadgroup`.
- inputs: `input` (**the same normalized row**), `fused_weight`,
  `packed_scales`, `router_keys`.

Both are 64-thread threadgroups, so appending grids needs no reshape and no
threadgroup-memory union: neither body uses `threadgroup` storage.

### 1.2 Why they are independent

1. **Same producer, no producer/consumer edge between them.** Both read `x`, the
   output of the fused `residual_rms_router` kernel. Neither reads the other's
   output. The shared leg writes `[1,1,512]`; the routed leg writes
   `[1,1,8,1,512]`; the two buffers are distinct allocations.
2. **Common consumer, downstream of both.** Both results are consumed by
   `laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6`
   (`lagunaFusedSharedRoutedDownResidual`), which takes the routed `activated`
   *and* the shared activation. So the pair is already a fan-out/fan-in diamond
   with the shared leg on one side and the routed leg on the other. Fusing the
   two diamond arms into one dispatch cannot change the topology of the graph.
3. **No hidden serialization through the router.** I checked whether the routed
   leg depends on a separate tournament dispatch that the shared leg would have
   to wait behind. It does not: on this path the top-8 tournament is executed
   *inside* the routed kernel prologue (`lagunaRouterTop8PrecomputedPrelude`,
   spliced through `lagunaRouterTop8PrologueHeader`) directly from
   `router_keys`. And `router_keys` comes from the *same*
   `residual_rms_router` producer as `x`.

   This refines the assignment's framing. The brief expects the guest to be
   ready earlier than the host, so leading with the guest tiles fills otherwise
   idle launch latency. On the current frontier both operands become ready at
   the same instant, because one producer kernel emits both `x` and
   `router_keys`. **Ready-time asymmetry is therefore not a mechanism I can
   claim.** The only mechanism left is dispatch-count removal plus whatever
   bandwidth absorption the union of the two working sets buys, which is exactly
   the discriminating question the assignment poses.
4. **The wide-codes trap is off.** `lagunaSharedSwiGLUQMVRows1WideKernel` is a
   *wide-codes* variant gated by `DARKBLOOM_QMV_WIDE_CODES`, default OFF. The
   shipped shared dispatch is the `halved` scale-plane variant, and that is the
   body I grid-append. My guard refuses to fuse when `DARKBLOOM_QMV_WIDE_CODES`
   is set, so the two can never disagree silently.

### 1.3 Reachability of the control

The fused path is reached only inside the branch that is live today: the
`lagunaFusedRoutedSwiGLUQMVEnabled` block, `lagunaPackedScalesEnabled` with a
materialized `_packedRoutedGateUpBank`, and `lagunaRouterPrecomputedKeysEnabled`
with a valid 256-entry `router_keys`. That is precisely the arm that dispatches
`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` in a steady decode
step, i.e. the scored path — not a fallback.

Reuse of the existing shared activation is via the `mergedSharedActivated`
channel already present at :11049 and consumed at :11113
(`sharedExpert.fusedSharedDownInputs(x, sharedActivation:)`), which skips the
standalone `lagunaSharedSwiGLUQMV` call when a shared activation is supplied.
So the guest dispatch is genuinely *removed*, not duplicated.

### 1.4 Precedent for the mechanism

`lagunaDecodeNVFP4QKVGateSource` (~:5084) already ships the identical pattern:
`if (tgid < guest_tiles) { guest; return; } host;`, multi-output
`outputNames: ["projected","gate_values"]`, appended grid, and an env gate
(`DARKBLOOM_DECODE_QKV_GATE_FUSED`). I copied its structure deliberately so the
new kernel is not a novel dispatch shape.

## 2. Implementation

One env-switched binary, default OFF:
`DARKBLOOM_SHARED_ROUTED_QMV_FUSED=1`.

- `lagunaSharedSwiGLUQMVRows1Source` gained `weightName` / `scalesName` /
  `outputName` parameters with defaults equal to the previous literals, so the
  two existing shared kernels are byte-identical to before.
- The routed R1 body was extracted into
  `lagunaRoutedSwiGLUQMVPackedTop8R1Source(groupExpression:)`, defaulting to
  `threadgroup_position_in_grid.x`, so the existing routed kernel is also
  byte-identical.
- New kernel `laguna_shared_routed_nvfp4_swiglu_qmv_top8keys_r1_bf16_v1`:
  `constexpr uint laguna_shared_tiles = 256;` then
  `if (tgid < laguna_shared_tiles) { <shared body, halved> return; }` then the
  routed body with `groupExpression = tgid - laguna_shared_tiles`. Two outputs,
  `shared_activated` `[1,1,512]` and `activated` `[1,1,8,1,512]`. Grid
  `((256 + 8*256)*64,1,1)` = 147456, threadgroup `(64,1,1)`.
- `lagunaSharedRoutedSwiGLUQMV` returns `nil` unless every dtype, shape and
  scale-plane size matches, so any frontier change silently falls back to the
  two-dispatch path instead of producing wrong numbers.

## 3. Results

*(filled in below as measurements land)*
