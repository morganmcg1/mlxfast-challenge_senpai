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

Two controls close the interpretation. Raising `MLX_MAX_OPS_PER_BUFFER` 100×
does not move the slope (§4), so the tax is per-dispatch/per-barrier and not
per-command-buffer — which also refutes the standing "command-buffer size
clause is worth 200–600 µs" estimate on this host. And the cost is **additive**
across sites (§7): two boundaries armed together cost 0.96 ± 0.05 of the sum of
their solo costs (t = −0.76), so the recommendation to bundle 2–3 dispatch
removals into one ranked candidate is measured rather than assumed.

The actionable consequence: the selection criterion for decode work is no
longer elasticity or critical-path position, it is **dispatch count**. At
c ≈ 1.4 µs the full 400-dispatch decode step carries a ≈ 560 µs tax (6.8 % of
the M4 Pro step); one removed per-layer dispatch is ≈ 27.6 µs/step on M5
≈ 0.42 % of score.

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

**The instrument is not submitted.** It lives in
`research/maple-fern-boundary-gap-injection.patch` and is applied with
`git apply` to reproduce. `Sources/` at the submitted head is byte-identical to
the base `fe5d843`; `senpai/check-editable-budget.sh fe5d843` reports
`growth=0/262144`, `current=2949686`. This matters beyond bookkeeping: the
instrument's census counter writes a Swift dictionary entry on every one of the
158 dispatches per step even when disarmed, which is exactly the kind of hot-path
cost this experiment exists to measure. Shipping it would have poisoned any
later timing on this branch.

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

**Result** (`fern_gap_cbcontrol.sh`, schedule `0,1,2,4,8,8,4,2,1,0`, 2 blocks,
216 steps/segment, drop 24; 3 runs, 349 s wall):

| run | `MLX_MAX_OPS_PER_BUFFER` | `MLX_MAX_MB_PER_BUFFER` | µs/boundary (K≥1) | K=0 step (ms) |
|---|--:|--:|--:|--:|
| `T0b_qkv` | 40 (default) | 40 (default) | 1.295 ± 0.128 | 8.20 |
| `T0b_qkv` | 4000 | 40 | 1.421 ± 0.118 | 8.19 |
| `T0b_qkv` | 4000 | 100000 | 1.431 ± 0.056 | 8.21 |
| `T0a_router_top8` | 40 (default) | 40 (default) | 1.416 ± 0.109 | 8.20 |
| `T0a_router_top8` | 4000 | 100000 | 1.394 ± 0.121 | 8.20 |

Raising `max_ops_per_buffer` by 100× and `max_mb_per_buffer` by 2500× **did not
move the slope** (1.295 → 1.431 µs, i.e. if anything slightly *up*, and well
inside 1σ of the pooled value). A per-command-buffer cost would have fallen by
~100×. The confound is therefore ruled out: the tax is genuinely
**per-dispatch + per-barrier**, not per-command-buffer. Pooled estimate across
these five command-buffer-control runs = **1.3914 µs per injected boundary** on
this M4 Pro. The five multi-call sites of §2 pool to 1.4796 µs. The two pools
bracket the headline constant used from here on: **c ≈ 1.4 µs**, with a
site-to-site range of 1.29–1.73 µs. (The W&B run's `pooled/us_per_boundary` and
`prize/*` keys were logged from the §2 six-site pool, 1.4796 µs, so they read
~6 % higher than the numbers below; same measurement, different pooling basis.)

Two corollaries fall out of the same three runs:

1. **Raising `MLX_MAX_OPS_PER_BUFFER` is not a free win.** The K = 0 column is
   flat at 8.19–8.21 ms across every setting (σ(step) ≈ 0.01 ms here). Whatever
   command-buffer commit overhead exists on this host, the default 40/40 policy
   is not leaving measurable decode time on the table. This is a clean null and
   it should stop anyone else from spending a receipt on the env knob.
2. It also constrains a candidate raised in review — "lift the CB **size**
   clause, since `buffer_sizes_` counts ~540 MB of resident expert weights per
   layer against a 40 MB threshold, implying ~40 forced splits/step, worth
   200–600 µs". `MLX_MAX_MB_PER_BUFFER=100000` removes that clause entirely and
   bought **0.00 ± 0.02 ms**. Either the splits are not happening (the size
   accumulator only counts *unique* inputs per buffer, `device.cpp:320`, and a
   resident weight already tracked is not re-counted) or they are free. Either
   way the 200–600 µs estimate is refuted on this host and (c′) is dead.

All three runs: 0 token divergences, phase check OK, reachability census exactly
40/39/39/39/39/1 on every step. TSVs: `/tmp/fern241/ops4000_T0b_qkv.tsv`,
`/tmp/fern241/opsmb_T0b_qkv.tsv`, `/tmp/fern241/opsmb_T0a_router_top8.tsv`.

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

### 6.1 The selection rule changes

The assignment's Part B rule was "fuse the single largest **E-weighted**
boundary". §2.2 refutes the premise that rule rests on. The replacement rule is
simpler and strictly broader:

> **Every removable decode dispatch is worth ≈ 1.4 µs on this host, regardless
> of its consumer's elasticity, its position in the chain, or whether it sits on
> the critical path.**

So the target list is no longer "chain-link boundaries in front of
zero-absorbed-slack consumers". It is "dispatch count per decode step", full
stop. That is a much easier quantity to attack and a much easier one to verify:
you can count dispatches statically before you build anything.

Concretely, per decode step this model issues **10 dispatches per sparse layer**
(9 for dense-only), enumerated below with the source line of the issuing call in
the unmodified `LagunaRuntimeModel.swift`:

| # | dispatch | issued at |
|---|---|---|
| 1 | `inputNorm(input)` (plain MLX RMSNorm, AOT) | ~5741 |
| 2 | `lagunaDecodeNVFP4QKVR1` | ~5742-5746 |
| 3 | `lagunaGateSoftplus` | ~5786-5788 |
| 4 | `lagunaSlidingFusedAttention` / `lagunaFullFusedAttention` | ~5956 / ~5982 |
| 5 | `lagunaGatedAffineOProjNVFP4` | ~6165-6179 |
| 6 | `lagunaResidualRMSNormRouter` | ~10344-10349 |
| 7 | `lagunaDecodeRouterTop8` | ~9519-9523 |
| 8 | `lagunaRoutedSwiGLUQMVPackedTop8` | ~10038-10043 |
| 9 | `lagunaSharedSwiGLUQMV` (via `fusedSharedDownInputs`) | ~10088-10090 |
| 10 | `lagunaRoutedSharedDownResidual` | ~10105-10116 |

At c ≈ 1.4 µs each, the whole decode step's dispatch tax is
`(10 × 39 + 9 × 1 + 1) × 1.4 = 400 × 1.4 ≈ 560 µs` of the 8.20 ms M4 Pro step —
**6.8 %**. Removing *one* per-layer dispatch is 39 × 1.4 ≈ **54.6 µs/step here**.
Scaling by the step-time ratio (4.1436 / 8.20) that is ≈ **27.6 µs/step on the
ranked M5**, i.e. ≈ **0.42 % of score** at the measured prize slope of
0.015280 %/µs.

**How large is that against noise? Smaller than it first looks.** The
cross-session decode-difference σ measured on the promoted frontier is 15.34 µs,
so 27.6 µs is **1.80σ**, not the 14σ an earlier draft of this section claimed.
(The 14σ figure came from mis-applying the *whole spine total*, 235 µs/step M4
Pro ≈ 119 µs/step M5 ≈ 7.7σ — and from using the M4 Pro number where the M5 one
belongs. Both errors are corrected here; the underlying measurements are
unchanged.) The honest reading:

- One removed per-layer dispatch ≈ 0.42 % of score, ≈ 1.8σ against
  cross-session noise. That is *worth having* but it is a **marginal lone
  receipt** — a single such change has a real chance of landing inside the noise
  band on any one ranked session.
- The ranked protocol runs candidate and baseline **back to back in the same
  session**, which removes most of the cross-session drift that σ = 15.34 µs
  measures. The paired noise floor is smaller than 15.34 µs, so 1.8σ is a
  conservative lower bound on the detection margin, not the expected one.
- The safe way to spend a receipt is therefore to **bundle 2–3 dispatch
  removals** into one candidate: 3 × 27.6 ≈ 83 µs/step M5 ≈ 1.3 % of score
  ≈ 5.4σ cross-session, which is unambiguous under any pairing assumption.

That last bullet rests on an assumption — that two boundary costs **add** rather
than sharing a saturating resource. It is the one assumption in this report that
would silently invalidate the recommendation if false, so I measured it directly
rather than assuming it. **§7 confirms additivity** at ratio 0.96 ± 0.05
(t = −0.76 against perfect additivity), so the bundling arithmetic above stands.

The whole 400-dispatch tax, if it could be halved, would be ≈ 280 µs/step M4 Pro
≈ 142 µs/step M5 ≈ **2.2 % of score**. That is the size of the prize this census
prices; it is not claimed to be fully recoverable.

### 6.2 Why the two published nulls do not block this

The obvious objection is PR #204: it deleted 39 side-branch dispatches per step
and measured −0.9 ± 29.7 µs. Under the model above the expected effect was
+55 µs, so #204 had roughly 46 % power — it is a **1.9σ non-detection, not a
refutation**. There is also a mechanistic escape: MLX's `memoryBarrier` is
emitted when a *tracked* resource is re-read (`device.cpp:363-390`); a
side-branch output that nothing re-reads before the next barrier may never have
forced a barrier at all, so deleting it removed a dispatch's encode cost but not
its barrier cost. Both explanations point the same way — **remove dispatches
whose outputs are actually consumed**, which is exactly what a fusion does and
exactly what a dead-side-branch deletion does not.

PR #158's observational null (−0.12 ± 0.22 µs/dispatch) is a different kind of
estimate: it regressed step time on naturally-varying dispatch counts, where
dispatch count is confounded with which kernels ran and how much data they
touched. The present design holds the kernel mix fixed and varies only the
boundary count, and its standard errors (0.05–0.20 µs) are small against the
1.4 µs effect.

### 6.3 Ranked targets, in the order I would spend receipts on them

**(1) Remove dispatch #9 — fold the shared-expert gate/up QMV into the routed
packed top-8 QMV.** The code already anticipates this: there is a declared
`var mergedSharedActivated: MLXArray?` with a doc comment describing exactly this
batching, and the variable is **never assigned**, so dispatch #9 fires on every
one of the 39 sparse layers. Worth 39 × 1.4 ≈ 54.6 µs/step (M4 Pro), ≈ 27.6 µs/step
(M5), ≈ 0.42 % of score. Both the routed and the shared expert use the same
NVFP4 weight format, so the shared expert is representable as one more row of
the packed batch. Bit-exactness is the risk: the two kernels must accumulate in
the same order and precision. This is the highest value-per-byte item on the
list and it is inside the maple-fern region fence.

**(2) Remove dispatch #7 — fold the top-8 selection into
`lagunaResidualRMSNormRouter`.** That kernel already materialises the packed
router keys that `lagunaDecodeRouterTop8` then re-derives. Same 54.6 µs/step (M4 Pro) / 27.6 µs/step (M5). Note
that `T0a_router_top8` has E = −0.045 — it is *fully shadowed*, so under the old
E-weighted rule this target scored zero. Under the corrected rule it is worth
exactly as much as any other. **This is the single sharpest test of §2.2's
claim**: if removing a fully-shadowed dispatch buys 55 µs, the elasticity model
is dead and the dispatch-count model is right. I would run this as the
discriminator even before the bigger fusions.

**(3) Remove dispatch #1 — fuse the input RMSNorm into the QKV GEMV prologue.**
The fused path already exists (`lagunaNormAffineQKV`) but declines on this
checkpoint because it requires affine 8-bit group-32 weights and all 40 layers
are NVFP4. Extending it to NVFP4 is the original H13 proposal. Worth 40 × 1.4 ≈
57 µs/step. Highest bitwise risk of the three (RMSNorm reduction order inside a
GEMV prologue), and the QKV wrapper is outside the maple-fern fence.

**(4) Audit-and-delete genuinely redundant ops.** Found while enumerating: a
never-assigned `mergedSharedActivated` (above); `let fusedTailGateLogits:
MLXArray? = nil` with an unreachable consumer; a `deferGateActivation` branch
that is never load-bearing; a decode-unreachable `softplus`; four dead fallback
blocks; and four `eScoreCorrectionBias.asType(.float32)` calls on an array that
is already F32 (`MLXArray.asType` returns `self` on a dtype match, so these are
0 dispatches — dead code, not dead work). These are worth **0 µs** individually
— they are listed so nobody re-discovers them and mistakes them for a win.

### 6.4 Things this experiment took off the table

- **`MLX_MAX_OPS_PER_BUFFER` / `MLX_MAX_MB_PER_BUFFER` tuning.** Clean null,
  §4. Do not spend a receipt here.
- **The command-buffer *size*-clause hypothesis** (~40 forced splits/step from
  resident expert weights, estimated 200–600 µs). Refuted on this host, §4
  corollary 2.
- **Elasticity as a fusion-selection criterion.** §2.2. E still correctly
  predicts whether extra *arithmetic* in a kernel is free; it does not predict
  the value of removing a *dispatch*.
- **Per-dispatch GPU timestamps via `MTLCounterSampleBuffer`.** Unsupported on
  this device (§1.1); do not plan an experiment that needs them.

### 6.5 What would falsify the model in §2.2

If target (2) — removing the fully-shadowed router top-8 dispatch — buys
substantially less than 39 × 1.4 µs, then the injected-boundary cost is not
symmetric with removal, and the 1.4 µs figure is an upper bound on the prize
rather than an estimate of it. The asymmetries to look for, in order of prior
likelihood: (a) the removed dispatch's barrier is immediately re-triggered by
another consumer of the same resource, so no barrier is actually saved;
(b) MLX's resource-tracking set is reshuffled by the removal, moving the
serialization point rather than deleting it (`device.cpp:363-372`); (c) the
fused kernel pays back the saved time as recompute. (c) is measurable
statically; (a) and (b) are not, and need the experiment.

## 7. Part B: is the boundary cost additive?

### 7.1 Why this, and not "fuse where the trace shows a gap"

The assignment's Part B was *"fuse only where the trace shows a gap"*. §2.2
dissolved that instruction rather than answering it: the gap is **flat
everywhere**, so "where the trace shows a gap" selects all 400 dispatches and
carries no information. Executing Part B literally would have meant picking a
fusion target on a criterion the experiment had just refuted.

The two nearest genuine fusion targets are also outside my region fence — the
routed and shared QMV kernel wrappers live at ~7639 and ~8320, which are not in
`:600-1100`, `:8525-8910`, `:9461-9575`, or the decode branch of
`:10003-10130`. Building a fusion there would have collided with another
student's surface.

So I spent Part B on the one **load-bearing and untested** assumption left in
§6.1. The whole recommendation "bundle 2–3 removals to clear the noise floor"
silently assumes per-boundary costs **add**. If instead they share a saturating
resource — a single command-buffer submission overhead, a fixed per-step
encoder cost, a driver-side queue that is already the bottleneck — then a
bundle would be worth much less than the sum of its parts, and the correct
advice would flip to *"build one large fusion, not several small ones"*. That
is a different research programme, so it is worth one campaign to find out.

### 7.2 Design

Three arms, **back to back in one session**, same schedule as §2
(`0,1,2,4,8,8,4,2,1,0` × 3 blocks, 216 steps/segment, first 24 dropped → 192
timed steps/segment):

| arm | armed site(s) | E | injected boundaries per unit K |
|---|---|--:|--:|
| `add_solo_T0b` | `T0b_qkv` | +0.741 | 40 |
| `add_solo_T0a` | `T0a_router_top8` | −0.045 | 39 |
| `add_both` | both | — | 79 |

The two solo sites were chosen at **opposite ends of the elasticity range** so
that if any interaction exists, this pair is where it should be largest. The
instrument's `DARKBLOOM_DECODE_GAP_SITE` was extended from a single name to a
comma-separated set (`private static let sites: Set<String>`, guard becomes
`sites.contains(name)`) so both sites arm from one process.

Same-session is essential: the two solo slopes and the joint slope must come
from one thermal and allocator state, or the contrast measures drift rather
than interaction. This is the MATCHED-CONTROL DOCTRINE applied to a
measurement rather than to a candidate.

`training_id 9feea392-bb79-4485-b311-37b9d7e25b08`, exit 0. All three runs:
0 token divergences, phase check OK for all 30 segments, and the reachability
census exactly `T0b_qkv 40 / T0a_router_top8 39 / T1c_lmhead 1 /
T2a_shared_qmv 39 / T2c_routed_qmv 39 / T2d_down_residual 39` on every one of
6490 instrumented decode steps per run. In `add_both` the driver marks **both**
sites `<== TARGET`, confirming the multi-site arming actually engaged rather
than silently falling through to one site.

### 7.3 Result: additivity holds

Slopes are OLS over K ≥ 1, block-centred, in µs/step per unit K
(`--calls 1`, so the number is the whole step's injected cost, not per-boundary):

| quantity | µs/step per unit K | se |
|---|--:|--:|
| `add_solo_T0b` | 58.674 | 3.94 |
| `add_solo_T0a` | 53.145 | 3.10 |
| **predicted additive** (sum) | **111.819** | 5.01 |
| **observed joint** `add_both` | **107.434** | 2.83 |
| difference (observed − predicted) | **−4.385** | 5.76 |

- **t = −0.762** against the null "perfectly additive". Not significant.
- **ratio observed/predicted = 0.9608 ± 0.0500**, 95 % CI **0.857 … 1.064**.
- 95 % CI on the difference: **[−16.3, +7.6] µs/step**, i.e. the data exclude
  any sublinearity worse than about 15 %.

Secondary fit including K = 0 (which folds in the first-touch offset, §3) gives
the same verdict slightly more sharply: predicted 119.27 ± 3.64, observed
112.85 ± 2.44, difference −6.42 ± 4.38, **t = −1.47**, ratio 0.946 ± 0.035.
Both fits agree; neither reaches significance.

*Note on the two error conventions.* The W&B run logs
`additivity/summary/difference_t = −1.01` where the table above says −0.76. The
point estimates are identical (ratio 0.9608 in both); only the standard errors
differ, for the reason already recorded in §4: `fern_gap_stats.py` centres each
block on its **K = 1** arm and reports a wider se (3.94 / 3.10 / 2.83), while
`fern_gap_wandb.py` centres on the **block mean** and reports a narrower one
(2.92 / 2.55 / 1.94). The table above quotes the more conservative pair. Both
are far short of the |t| = 2.07 that would reject additivity, so the verdict is
insensitive to the choice.

**Verdict: ADDITIVE.** Two independent decode boundaries cost what they cost
separately. The point estimate sits 4 % below perfect additivity and is
statistically indistinguishable from it; if there is any shared saturating
component it is smaller than ~15 % of a boundary and does not change any
decision in §6.

Per-boundary this session: T0b 58.674/40 = **1.467 µs**, T0a 53.145/39 =
**1.363 µs**, joint 107.434/79 = **1.360 µs** — all inside the 1.29–1.73 µs
range of §2 and consistent with the c ≈ 1.4 µs headline. The §2 campaign
measured 51.8 and 55.2 µs/step for these same two sites in a different session;
the ±10 % session-to-session wobble is why the additivity contrast had to be
run within one session.

### 7.4 A corroborating detail: the first-touch offset is *not* additive

The K = 0 → K = 1 excess over the fitted slope (§3) behaves completely
differently from the slope itself:

| arm | first-touch offset (µs/step) |
|---|--:|
| `add_solo_T0b` | 22.8 |
| `add_solo_T0a` | 72.0 |
| sum, if additive | 94.8 |
| **`add_both` observed** | **72.4** |

The joint arm's offset equals the **larger** of the two solo offsets, not their
sum. That is exactly what a one-time serialization-point move plus
resource-tracking-set reshuffle should look like: arming *any* site pays it
once, arming a second site does not pay it again. It is not a per-boundary cost
and it is not a property of the site.

This is a useful independent check on the reduction method. §3 excluded the
first-touch offset on the argument that it is an instrument artefact rather
than a boundary cost; the offset's non-additivity is direct evidence for that
argument, obtained without assuming it. It also rules out the alternative
reading that the offset is just "the first boundary is expensive" — if it were,
the joint arm would have paid it twice.

### 7.5 What this changes

Nothing in §6 flips. The bundling recommendation in §6.1 is confirmed rather
than merely assumed:

- **Bundling 2–3 dispatch removals into one ranked candidate is the right way
  to spend a receipt.** 3 × 27.6 ≈ 83 µs/step on M5 ≈ 1.3 % of score, and that
  arithmetic is now measured, not extrapolated.
- **A lone removal remains marginal** (1.8σ cross-session). Additivity does not
  rescue it; it just means the fix is to add more removals, not to hunt for a
  single magic one.
- **The 400-dispatch tax in §6.1 is a real sum, not an over-count.** Because the
  boundaries add, `400 × 1.4 ≈ 560 µs` is a legitimate total rather than a
  quantity that would collapse under a shared bottleneck.

The one caveat that survives: additivity was tested for **injected** boundaries
at two sites. It is evidence that the *cost model* is linear, and it is not by
itself evidence that two *removals* will both be realised — that still depends
on the removal-side asymmetries listed in §6.5, chiefly whether a removed
dispatch's barrier is immediately re-triggered by another consumer. Additivity
makes the bundle arithmetic sound; §6.5's falsification test is still the thing
that has to pass.

