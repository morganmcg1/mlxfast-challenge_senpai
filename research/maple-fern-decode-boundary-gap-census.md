# Decode boundary-gap census (PR #241, maple-fern)

`assignment_id`: `maple-2026-08-07f-decode-boundary-gap-census`, revision `r1`.
Base `fe5d843f7374f8608e4638a05a17a92a09365ecc`. Host: Apple M4 Pro, 48 GiB,
20 GPU cores, Apple GPU generation 16, macOS 26.5.2. Steady one-token decode
step on this host: **8.20 ms** (ranked M5 step is 4.143569 ms).

**Everything in this document is research-only. Net submitted bytes: 0.**
The instrument lives in `research/maple-fern-boundary-gap-injection.patch`;
`Sources/` is byte-identical to the base at the submitted head.

---

## 0. One-paragraph verdict

The kill rule is **CLEARED**, but the hypothesis it was guarding is
**REFUTED**. A chained dispatch inserted into the real dependency chain
immediately in front of a spine consumer costs **1.30–1.73 µs**, and summed
over the 158 pre-registered spine boundaries that is **235 µs/step**, far above
the 100 µs floor. However the cost is **flat across consumer elasticity E**:
the pre-registered shadow control `T0a_router_top8`, whose measured elasticity
in PR #218 was **E = −0.045** (injected GPU *work* there is completely free),
pays **1.416 ± 0.109 µs** per injected dispatch — statistically identical to
the most exposed site. H13 said the money is *serial GPU idle in front of
zero-absorbed-slack consumers*. It is not. It is a **global per-dispatch /
per-barrier tax that no sibling can shadow**, because MLX's Metal backend
drives a single in-order command stream: GPU *work* is shadowable, a *barrier*
is not.

---

## 1. Instrument

### 1.1 Why not a real gap trace

`MTLCounterSampleBuffer` on this device reports:

```
atStageBoundary        : true
atDispatchBoundary     : false
atDrawBoundary         : false
atTileDispatchBoundary : false
atBlitBoundary         : false
counterSets            : timestamp ["GPUTimestamp"]
sampleTimestamps()     : cpu == gpu (shared mach epoch)
```

Per-dispatch GPU timestamps are therefore unobtainable. The only way to get a
per-dispatch boundary time is to split the work into more encoders or command
buffers, which *manufactures the very gap being measured*. This is a genuine
instrument negative and it is why the census below is causal rather than
observational.

`research/pr91-gpuprof-hook.patch` records per **command buffer**, not per
dispatch, so it cannot resolve a single boundary either.

### 1.2 The causal substitute: chained identity dispatches

`enum LagunaDecodeGap` (research patch) exposes
`pad(_ name: String, _ x: MLXArray) -> MLXArray`. When armed for site `name`
with parameter `K` it returns `x` chained through `K` bit-exact identity
multiplies:

```swift
var y = x
let one = cachedOne(x.dtype)          // MLXArray(Float(1)).asType(x.dtype)
for _ in 0..<k { y = y * one }
return y
```

Each link is a real `Multiply` node (MLX builds it unconditionally; eager
`eval_impl` has no CSE or simplification — those live only in `compile.cpp`,
and the pad sites are outside both of the runtime's `compile()` closures), and
each link's input is the previous link's output, so `set_input_array` sets
`needs_barrier_` and `maybeInsertBarrier()` emits a real
`memoryBarrier(BarrierScopeBuffers)`.

The injected tensor is ~16 KB, i.e. ≈0.082 µs of real bandwidth at 200 GB/s.
Anything above that in the marginal cost is dispatch + barrier + command-buffer
overhead — exactly what a producer/consumer fusion removes.

When `K == 0` the instrument is inert: `pad` returns `x` unchanged and adds no
node. `K == 0` is therefore a true unmodified reference arm.

### 1.3 Reachability census (REACHABILITY-BEFORE-NULL)

`pad` increments a per-site counter on **every** call regardless of arming, so
the census is free and always on. Across all six campaign runs, for all
6490 instrumented decode steps in each run, the per-step call counts were
**exactly constant** and exactly as pre-registered:

| site | consumer | calls/step observed | pre-registered |
|---|---|--:|--:|
| `T0b_qkv` | `lagunaDecodeNVFP4QKVR1` | 40 | 40 |
| `T0a_router_top8` | `lagunaDecodeRouterTop8` | 39 | 39 |
| `T2c_routed_qmv` | `lagunaRoutedSwiGLUQMVPackedTop8` | 39 | 39 |
| `T2a_shared_qmv` | `fusedSharedDownInputs`→`lagunaSharedSwiGLUQMV` | 39 | 39 |
| `T2d_down_residual` | `lagunaRoutedSharedDownResidual` | 39 | 39 |
| `T1c_lmhead` | `pruner.logits` | 1 | 1 |
| **spine total** | | **158** | **158** |

No site was silently unreached and no site fired a variable number of times.

### 1.4 Firing evidence

Three independent proofs that the injected dispatches actually execute:

1. The census above (call site reached, exact count).
2. A `GAPSEG` phase check: the worker echoes the K it believes it is running
   for every segment; all 30 segments matched the driver's intent in every run.
3. The K=64 anchor in the smoke run: +3.54 ms/step. An elided or folded
   multiply cannot cost 3.5 ms.

Teacher-forced greedy tokens matched the golden trace with **0 divergences**
in every segment of every run, confirming `x * 1` is bitwise identity for the
values actually present (finite normals; MSL §8.1 permits FTZ on subnormals
and does not pin NaN payloads, neither of which is reachable at these sites).

### 1.5 Design

Palindromic schedule `0,1,2,4,8,8,4,2,1,0` × 3 blocks = 30 segments,
216 decode steps per segment, first 24 dropped, 192 timed. Unit of replication
is the **segment median**, never the individual step. Every contrast is formed
inside a block so linear thermal/frequency drift cancels. Driver:
`research/fern_gap_probe.py`; campaign `research/fern_gap_campaign.sh`;
reducer `research/fern_gap_stats.py`. Raw TSVs kept in `/tmp/fern241/`.

---

## 2. Result: the gap census

Marginal cost of one extra chained dispatch on the named edge, block-centred
OLS over K ≥ 1 (the K = 0 → 1 step is reported separately in §3):

| site | E (PR #218) | µs per boundary | ± | t | calls/step | µs/step |
|---|--:|--:|--:|--:|--:|--:|
| `T0b_qkv` | 0.741 | **1.295** | 0.128 | 20.9 | 40 | 51.8 |
| `T2c_routed_qmv` | 0.754 | **1.512** | 0.200 | 15.6 | 39 | 59.0 |
| `T2d_down_residual` | 0.617 | **1.733** | 0.203 | 17.6 | 39 | 67.6 |
| `T2a_shared_qmv` | 0.311 | **1.442** | 0.053 | 56.0 | 39 | 56.2 |
| `T1c_lmhead` | 1.111 | 0.359 | 3.753 | 0.2 | 1 | 0.4 |
| **spine total** | | | | | **158** | **235.0** |
| `T0a_router_top8` *(control)* | **−0.045** | **1.416** | 0.109 | 26.7 | 39 | 55.2 |

Raw per-arm contrasts against the inert K = 0 arm are in §3.

### 2.1 Kill-rule verdict

The assignment's kill rule: *if the E-weighted summed gap at chain-link
boundaries is < 100 µs/step, stop.*

The injection prices the boundary **inside the live dependency chain**, so the
measured slope is already the elastic, causal quantity — it is a measured Δ in
wall-clock step time, not a raw idle interval that still needs an E discount.
Multiplying it by E again would double-count. Both readings clear the rule:

* raw (correct) reading: **235 µs/step** ≫ 100 µs;
* the literal Σ Eᵢ · callsᵢ · costᵢ reading: **142 µs/step** ≫ 100 µs.

**Verdict: the kill rule is CLEARED.** At the prize slope of 0.015280 % of
score per µs, 235 µs of M4-Pro step time is ≈ +3.6 % if it transferred one for
one; holding the *share* of the step constant (235/8200 = 2.87 %) and pricing
the equivalent M5 microseconds gives **≈ +1.8 % of score**. Directional only.

### 2.2 …but H13's mechanism is refuted

`T0a_router_top8` was pre-registered as the discriminator. Its consumer is
fully shadowed: in PR #218, injecting *real duplicated GPU work* there produced
a slope of −8.45 ± 4.83 µs per copy-set, E = −0.045, a confirmed null. If the
boundary cost were serial GPU idle in front of a zero-absorbed-slack consumer,
T0a must price at ≈ 0.

It prices at **1.416 ± 0.109 µs**, indistinguishable from `T0b_qkv`
(1.295 ± 0.128) and `T2a_shared_qmv` (1.442 ± 0.053). Across the five
39/40-call sites the cost is flat at 1.30–1.73 µs while E ranges over
−0.045 … 0.754. There is no usable correlation.

**Mechanism.** MLX's Metal backend encodes into a single in-order command
stream. `CommandEncoder::set_input_array` raises `needs_barrier_` when an input
aliases a previous output, and `maybeInsertBarrier()` emits
`memoryBarrier(BarrierScopeBuffers)` before the dispatch. That barrier drains
*everything* in flight in that encoder, not merely the producer. So sibling
GPU *work* can overlap and be shadowed — which is exactly what PR #218
measured — but a *barrier* cannot be shadowed by anyone. The tax is global.

This is a strictly better result than H13 predicted, because it means the
prize is not confined to five spine families: **every removable dispatch on
the decode path is worth ≈ 1.4 µs × its calls/step**, chain-link or not.

---

## 3. Per-arm contrasts and the first-touch offset

Δ versus the inert K = 0 arm, µs added per step (mean of 3 block-paired
contrasts, se over blocks):

| K | T0b_qkv | T2c_routed | T2d_down | T2a_shared | T0a_router | T1c_lmhead |
|--:|--:|--:|--:|--:|--:|--:|
| 1 | 109.1 ± 27.1 | 192.2 ± 9.8 | 125.1 ± 23.4 | 66.2 ± 6.1 | 98.1 ± 9.6 | 5.3 ± 0.3 |
| 2 | 132.3 ± 10.1 | 243.9 ± 28.6 | 253.2 ± 12.1 | 121.6 ± 3.7 | 190.3 ± 10.2 | 16.0 ± 21.1 |
| 4 | 239.4 ± 6.0 | 350.0 ± 43.9 | 410.0 ± 9.5 | 226.9 ± 5.1 | 277.9 ± 7.1 | 2.9 ± 7.1 |
| 8 | 461.3 ± 5.1 | 603.2 ± 38.3 | 618.3 ± 3.9 | 460.0 ± 4.2 | 499.1 ± 13.1 | 12.3 ± 3.4 |

The K = 0 → 1 step costs more than the K ≥ 1 slope predicts, by a site-varying
**first-touch offset** of 9.9 / 57.4 / 57.5 / 133.2 / 42.8 µs per step
(`T2a_shared`, `T0b_qkv`, `T2d_down`, `T2c_routed`, `T0a_router`). This is a
property of *interposing anything at all* on that edge — the most likely cause
is loss of MLX buffer donation / in-place output aliasing in the consumer, or
a consumer fast path keyed on input ownership. It is an instrument artefact,
not part of the fusion prize, and it is excluded from every headline number
above by fitting the slope over K ≥ 1 only. Its existence means the reported
1.3–1.7 µs is, if anything, a **lower** bound on what interposing a dispatch
costs — and correspondingly a conservative estimate of what removing one buys.

`T1c_lmhead` fires once per step so its slope has 40× less leverage; its
confidence interval (±3.75 µs) contains both zero and 1.4 µs. It is reported as
underpowered, not as a null.

---

## 4. Command-buffer aliasing control

**Confound.** On this M4 Pro (`arch` suffix `g`, "base, pro") MLX sets
`max_ops_per_buffer_ = 40` and `max_mb_per_buffer_ = 40`
(`device.cpp:579-582`), and `CommandEncoder::needs_commit()` splits the command
buffer when `buffer_ops_ > max_ops` or the accumulated unique input bytes
exceed `max_mb` (`device.cpp:484-487`). Every injected dispatch increments
`buffer_ops_` (`device.cpp:381`). One copy-set at a 39/40-call site therefore
adds ≈ 40 ops ≈ **exactly one extra command buffer per step**, so
"1.4 µs per dispatch" and "≈56 µs per extra command buffer" are perfectly
degenerate in §2's data. `T1c_lmhead` does not break the degeneracy either
(1 op = 1/40 CB, and 1.4 µs = 56/40 µs).

**Control.** Re-run `T0b_qkv` and `T0a_router_top8` with
`MLX_MAX_OPS_PER_BUFFER` and `MLX_MAX_MB_PER_BUFFER` raised
(`mlx/utils.h:178-188` reads both). A per-command-buffer cost must fall roughly
as 1/max_ops; a per-dispatch cost must not move. Script:
`research/fern_gap_cbcontrol.sh`.

*(results pending — filled in below)*

---

## 5. Reconciling with prior art

| study | claim | reconciliation |
|---|---|---|
| PR #158 | per-dispatch coefficient −0.12 ± 0.22 µs (null) | observational fit across natural variation in dispatch count; confounded with kernel identity and buffer sizes. The present design is interventional and its se is 0.05–0.20 µs on a 1.4 µs effect. |
| PR #158 | aggregate inter-CB gap ≈ 265 ± 20 µs/step, slope +0.059 ± 0.019 with busy time | same order as the 235 µs measured here; consistent with the boundary tax being the bulk of that gap. |
| PR #204 | deleting 39 side-branch dispatches → −0.9 ± 29.7 µs (p = 0.94) | expected effect under the present model is 39 × 1.4 = 55 µs; their se was 29.7 µs, so their null is a 1.9σ non-detection, i.e. **underpowered**, not a refutation. Additionally a side-branch output that is not re-read before the next barrier may never have forced a barrier, so deleting it removes a dispatch but no barrier. |
| PR #218 (mine) | E ranges −0.045 … 1.11 across these same six families | unchanged and not contradicted: that experiment injected *GPU work*, this one injects *barriers*. Work is shadowable; barriers are not. |

---

## 6. What this licenses next

*(to be completed after §4)*
