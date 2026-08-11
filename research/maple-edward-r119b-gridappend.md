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

All numbers below are from one host: Apple M4 Pro, 20 GPU cores, 48 GiB unified
memory, low-memory startup profile, Apple GPU generation 16. Generation 16 does
not select the `_nax` prefill kernels the ranked M5 uses, so nothing here is
prefill evidence for an `_nax` change. The mechanism under test is
dispatch-count removal on the decode path, which is the class that transfers
best across Apple Silicon generations; the absolute per-dispatch price does not.

### 3.1 Bit-exactness and gate selection

`research/edward_r119b_smoke.sh`, one binary, 512-token prefill plus 40
teacher-forced decode steps per arm:

| arm | trace line for the gate/up site | divergences |
| --- | --- | --- |
| `DARKBLOOM_SHARED_ROUTED_QMV_FUSED=0` | `routed gate/up QMV + SwiGLU (packed, producer keys)` | 0 |
| `DARKBLOOM_SHARED_ROUTED_QMV_FUSED=1` | `shared+routed gate/up QMV (grid-append, packed, producer keys)` | 0 |

`cmp` of the two full token dumps: `TOKENS_IDENTICAL`. The fused kernel is
therefore selected when the switch is on, the shipped two-dispatch kernel is
selected when it is off, and the two produce the same greedy tokens.

### 3.2 Checkpoint 1 — measured dispatch-count delta

`research/edward_r119b_profile.sh` with the PR-158 GPU-profile hook, steady-step
means over 120 teacher-forced steps (step 0 excluded; it pays the KV-growth
concat), `DARKBLOOM_GPU_PROFILE_SPLIT=0` so the shipped command-buffer batching
policy is intact:

| arm | dispatches/step | command buffers/step | gpu_busy_sum | gap | wall |
| --- | --- | --- | --- | --- | --- |
| gate 0 | **366.0** | 45.0 | 7.949 ms | 0.219 ms | 8.168 ms |
| gate 1 | **327.0** | 45.0 | 7.928 ms | 0.256 ms | 8.184 ms |

The dispatch delta is exactly **−39.0 per step**, i.e. one removed shared-expert
QMV encode for each of the 39 MoE layers, which is the count the assignment
predicted. Command-buffer count is unchanged, so the removal is purely
within-command-buffer and does not perturb the batching policy.

The paired GPU-busy delta is **−20.9 µs/step, 95 % CI [−31.2, −10.6]** over 118
steady steps per arm (§3.7), a marginal price of **0.54 µs per removed
dispatch** on this host. Note that the gap column *grew* by 37 µs while busy
fell 21 µs, which is why the single-pair wall delta is +16 µs — the wrong sign.
I treat that wall figure as unresolvable rather than as a regression: one pair
of processes cannot resolve 16 µs on an 8.2 ms step. §3.8 is the ranked answer.

### 3.3 Register/occupancy characteristics of the fused kernel

The GPU-profile hook prints Metal's own pipeline properties at creation
(`GPUPSO <name> maxThreads= execWidth= tgMem=`).
`maxTotalThreadsPerThreadgroup` is the register-pressure proxy: register
pressure is what lowers it.

| pipeline | maxThreads | execWidth | tgMem |
| --- | --- | --- | --- |
| `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` (guest alone) | 1024 | 32 | 0 |
| `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` (host alone) | 1024 | 32 | 0 |
| `laguna_shared_routed_nvfp4_swiglu_qmv_top8keys_r1_bf16_v1` (fused) | **1024** | 32 | 0 |

The union kernel keeps the same 1024-thread ceiling as both parents and still
declares no static threadgroup memory, and both bodies run at 64 threads per
threadgroup — 16× below the ceiling. `maxTotalThreadsPerThreadgroup` is a
compile-time register-pressure ceiling, not achieved occupancy, so the precise
claim is that **the register-pressure ceiling did not drop**. That is exactly
what the `N-GRIDAPPEND-REGISTER-UNION-COSTS-HOST` stop condition needs, and it
does not fire. §3.4 confirms it on timing as well as on the declared limit.

### 3.4 Separately measured host-only leg (SPLIT=1 attribution)

`DARKBLOOM_GPU_PROFILE_SPLIT=1` puts one dispatch per command buffer, which
isolates each kernel but inflates every per-dispatch cost by the per-command-
buffer overhead. It is attribution only, never a ranking axis.

| kernel | µs/step | calls/step | µs/call |
| --- | --- | --- | --- |
| host alone: routed gate/up QMV (`s1_off`) | 1498.9 | 39 | **38.43** |
| guest alone: shared gate/up QMV (`s1_off`) | 288.2 | 39 | **7.39** |
| fused host+guest (`s1_on`) | 1636.2 | 39 | **41.96** |

Derived per call:

- host-leg growth when the guest is appended: 41.96 − 38.43 = **+3.53 µs**;
- the two unfused command buffers together cost 38.43 + 7.39 = 45.82 µs/call
  against 41.96 µs/call fused, so the isolated saving is **3.86 µs/call**. In
  this regime each dispatch also pays one command-buffer commit/schedule, so a
  large part of that 3.86 µs is the *isolation regime's own* per-command-buffer
  overhead, which the shipped build never pays. I therefore do **not** claim
  "52 % of the guest's work was absorbed". The defensible statement is: fusion
  removed the guest's launch and command-buffer overhead, and the guest's
  streaming work reappeared almost in full as +3.53 µs of host-leg growth.
- The guest adds 256 tiles to the host's 2048, +12.5 %; scaling the host's
  *average* 38.43 µs/call gives 4.80 µs, so +3.53 µs looks "cheaper than
  proportional". I am flagging that comparison as weak rather than using it:
  the host's average per-tile cost includes its own launch ramp and drain, so
  its *marginal* per-tile cost is legitimately below its average and +3.53 µs
  may be exactly marginal-proportional. It is evidence that the host does not
  regress; it is not evidence of scheduler-level absorption.

Whole-step SPLIT=1 numbers agree: kernel-sum delta
1498.9 + 288.2 − 1636.2 = **150.9 µs/step**, GPU-busy delta
**−142.9 µs/step, 95 % CI [−151.1, −134.7]** (Welch on 118 steady steps per
arm, `research/edward_r119b_busy_ci.py`), wall delta 9.258 − 9.024 =
**234 µs/step**. SPLIT=1 wall runs at 9.0–9.3 ms against 8.2 ms shipped, so
µs/call is not directly comparable across SPLIT modes; the clock and pacing
differ.

### 3.5 Mechanism: which boundary class this fusion removes

Two facts from the vendored MLX source and from the command-buffer traces
explain the size of the end-to-end result, and they do not depend on this host.

1. MLX opens every compute encoder with `MTL::DispatchTypeConcurrent`
   (`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:548`), and
   inserts a barrier only when a new dispatch has a read/write hazard against an
   unfenced previous output (`device.cpp:311`–`374`). The guest and the host are
   a fan-out off one producer (§1.2), so no barrier separated them before the
   change.
2. The trace shows the guest and the host inside the **same** command buffer,
   next to their neighbours. The dominant per-step command-buffer signature in
   `s0_off.log` is
   `residual_rms_router… | shared_nvfp4_swiglu_qmv_rows1_halved… |
   prefill_router_tournament_ordinal_norm_active64_v2 |
   routed_nvfp4_swiglu_qmv_packed_top8keys_r1… |
   routed_shared_nvfp4_down_residual…`, and the command-buffer count is
   **45.0/step in both arms** (§3.2).

So this fusion removes neither a barrier nor a command-buffer boundary. It
removes one dispatch inside a region that was already encoded concurrently —
the cheapest boundary class that exists in this runtime. That is the physical
reason the realized saving is far below an additive dispatch price.

### 3.6 Bytes ledger: the routed leg has no bandwidth to donate

The ceiling half of the pricing fork assumes the host QMV has spare memory
bandwidth into which the guest's traffic can be absorbed. That is checkable from
the source without any GPU time. Per decode token, per sparse layer
(hidden 2048, intermediate 512, 256 experts, top-8 —
`Sources/MLXFastModel/LagunaConfig.swift:17,30-33`):

| buffer | guest (shared) | host (routed top-8) |
| --- | --- | --- |
| `fused_weight` uint32 NVFP4 codes | 1,048,576 B | 8 × 1,048,576 = 8,388,608 B |
| scales, uint8, one per 32 codes after halving | 65,538 B | 8 × 65,536 = 524,288 B |
| `router_keys` uint32[256] | — | 1,024 B |
| input row `x` bf16[2048] | 4,096 B | 4,096 B (same buffer) |
| **unique bytes read** | **1,118,210** | **8,918,016** |

Bytes per threadgroup are identical in both kernels, 4,352 B (4,096 code bytes +
256 scale bytes), which is the invariant that makes grid-append legitimate:
256 × 4,352 = 1.11 MB and 2,048 × 4,352 = 8.91 MB. `halved` in the guest kernel
name refers to the *scale plane* only — the checkpoint is group-16 and
`lagunaHalvedGroup32ScalePlane` drops the redundant odd byte of each group-16
pair, keeping 168 first-pair exceptions in a 128-byte header
(`Sources/MLXFastModel/LagunaRuntimeWeights.swift:1053-1094`) — so weight bytes
are unchanged.

Two conclusions:

- **Fusion saves no bytes.** The only buffer the two kernels share is the 4,096-B
  input row. Unfused 10,040,320 B versus fused 10,036,224 B, a 0.041 % byte
  reduction. Whatever this change wins, it cannot be bandwidth.
- **There is no headroom to absorb into.** The host reads 8,918,016 B in
  38.43 µs = **232 GB/s achieved, 85 % of the M4 Pro's 273 GB/s peak**. Spare
  bandwidth is ~41 GB/s, and streaming the guest's 1.12 MB through only that
  spare capacity would take 27 µs — far longer than the host's whole 38 µs call.
  The ceiling branch needed 105 µs/step = 2.69 µs/call of saving, i.e. the
  guest's traffic becoming nearly free. That is not physically available here.

For completeness: the observed +3.53 µs/call of host growth implies a marginal
1.12 MB at 317 GB/s, above the DRAM peak, so some of the guest's codes or scales
are being served from cache, or the SPLIT=1 per-call average overstates the
host's own steady-state rate. Either way the guest's traffic is paid, not
absorbed.

### 3.7 Two axes, with intervals, against the pre-registered fork

| axis | Δ GPU busy per step (95 % CI) | µs per removed dispatch | n/arm |
| --- | --- | --- | --- |
| SPLIT=1, one dispatch per command buffer | −142.9 [−151.1, −134.7] | 3.66 | 118 |
| **SPLIT=0, shipped batching** | **−20.9 [−31.2, −10.6]** | **0.536 [0.272, 0.800]** | 118 |

Both intervals exclude zero (p = 1e-4 for SPLIT=0), and the two intervals are
disjoint. Three consequences:

1. **The isolation regime overstates this fusion by 6.8×**, not by the
   assignment's 3.4×. Serializing dispatches into one command buffer each is not
   a neutral magnifier for a 7.4 µs, 256-threadgroup dispatch.
2. **The 1.2382 µs marginal dispatch price does not hold at this boundary
   class.** The measured shipped-regime price is 0.536 µs/dispatch with a 95 %
   upper bound of 0.800 µs, which excludes 1.2382 µs. The calibration is not
   wrong in general; it is *boundary-type dependent*, and this experiment
   removed 39 co-encoded, unbarriered, same-command-buffer boundaries.
3. **The realized GPU-time saving is below the assignment's refutation floor.**
   The floor is 48.3 µs/step. The entire 95 % CI of the measured saving,
   [10.6, 31.2] µs/step, lies below it. This is a resolved refutation, not an
   underpowered null.

The bandwidth-absorption half of the hypothesis fails separately: the guest's
streaming work reappears as +3.53 µs/call of host-leg growth (§3.4), so the
routed QMV had no bandwidth headroom to donate to the shared QMV.

### 3.8 Ranked end-to-end campaign

*(campaign in flight; filled in when it lands)*
