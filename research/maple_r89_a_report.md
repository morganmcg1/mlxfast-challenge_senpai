# R89-A — router weight prefetch above the RMS-norm barriers

**Result: attribution-positive, end-to-end below floor.** The hoist is real and
causal at the kernel label (A1−A4 = −6.85 µs/step, 95 % CI [−9.76, −3.94], 8/8
reps negative, p = 0.0039), bit-exact on every arm, and passes the occupancy
gate. It is **not** demonstrable as a rule-43 end-to-end number on this host:
my `nat`-regime census floor is ±13.3 µs/step on absolute busy, 1.9× the
effect, and the one nominally significant `nat` number contradicts its own
control arms. I am asking for a policy ruling rather than claiming a merge.

- Base: `3f430f6f17ac4bfbac5f47767ca78cb89d84a760`
- Host: Apple M4 Pro, `applegpu_g16s`, 48 GiB, Darwin 25.5.0 (**not** the ranked M5 Max)
- Submitted path: `Sources/MLXFastModel/LagunaRuntimeModel.swift` (only)
- Shipped default: `DARKBLOOM_ROUTER_WEIGHT_PREFETCH = 1` (depth 1)

---

## 1. Hypothesis, restated as latency-overlap-only

The original brief allowed two mechanisms. Advisor comment 5228932028 killed one
of them with measured evidence, so the hypothesis is now single-mechanism.

**Mechanism A — barrier cost — is dead and I am not claiming it.** Tanjiro's
R87-A (#469) measured injected `threadgroup_barrier` at **0.0293 µs per barrier
per dispatch** (8 extra barriers → +9.13 µs/step, 16 → +8.52, saturating). The
router kernel crosses four barriers. Four barriers ≈ 0.12 µs/dispatch ≈ 4.6
µs/step *in total*, and a hoist does not remove a single one of them — it moves
a load across them. There is no barrier-cost budget to recover. I am
**not** citing rule 41's 1.4064 µs dispatch-boundary price either: the advisor
scope-limited rule 41 to dispatch boundaries, and an in-kernel barrier is not a
dispatch boundary. Treating it as one was a category error in my original brief.

**Mechanism B — latency overlap — is the only mechanism that can pay, and it is
what I tested.** The router GEMV's first four `vec<bfloat,4>` loads from
`router_weight` are issued *after* the cross-simdgroup reduction completes. If
AGX keeps a `device` load in flight across
`threadgroup_barrier(mem_flags::mem_threadgroup)`, issuing them *before* the
reduction lets their memory latency be absorbed by the reduction's own
execution, so the GEMV starts with its first tile already in registers.

**Ceiling.** The win cannot exceed the duration of the phase the load overlaps
into — the residual-add + sum-of-squares + cross-simdgroup reduction + normalize
window. It is emphatically *not* the ~154 µs/step "excess" figure from the old
round-36 analysis. Section 6 measures that window directly.

**Falsifiable prediction and its control.** If mechanism B is real, A1 (peel
hoisted **above** the barriers) must beat A4 (character-identical peel left
**below** the barriers). If the compiler already hoists the loads, or if AGX
drops loads at a barrier, A1 == A4 and the whole lever is dead. A4 is therefore
the arm that decides, and A1 == A4 would have been a fully publishable negative.

---

## 2. Floor arithmetic — stated before any result (rule 40)

Rule 40 requires naming the estimator before quoting a number. Every floor below
is **measured on this rig by my own `0b` null control** (an independently
dispatched but character-identical copy of A0 occupying its own slot in the same
reps), not inherited from the published table.

| estimator | σ (µs/step) | ±95 % at n = 8 | observed `0b` null |
|---|---|---|---|
| **per-kernel router label** (SPLIT=1) | **3.34** | **±2.79** | −0.58 |
| census absolute busy (SPLIT=1) | 60.27 | ±50.39 | +0.50 |
| census union busy (SPLIT=1) | 58.80 | ±49.17 | +0.50 |
| census wall (SPLIT=1) | 177.36 | ±148.30 | −17.00 |
| end-to-end median (SPLIT=1) | 192.99 | ±161.37 | −13.25 |
| census absolute busy (`nat`) | 15.86 | ±13.26 | −0.25 |
| census union busy (`nat`) | 15.86 | ±13.26 | −0.25 |
| census wall (`nat`) | 12.19 | ±10.19 | −6.00 |
| end-to-end median (`nat`) | 6.25 | ±5.23 | **+4.38 ← null not clean** |

My per-kernel σ of 3.34 µs/step sits inside the advisor's published per-kernel
band of 0.4–4.9. My SPLIT=1 census σ's are ~4× the published within-process
`nat` values because **my census is one process per arm** — it is a
cross-process estimator and pays exactly rule 40's cross-process penalty. I
cannot fix this: `DARKBLOOM_ROUTER_WEIGHT_PREFETCH` is read once at static
initialisation, so in-process arm switching is impossible without changing the
shipped selection mechanism. The `nat` census is ~4× tighter than the SPLIT=1
census (fewer, larger command buffers ⇒ less per-CB jitter), but still not
tight enough.

**Consequence, stated up front:**

| estimator | ±95 % at n = 8 | vs. a ~7 µs/step effect |
|---|---|---|
| per-kernel router label | ±2.79 | resolvable (2.5× headroom) |
| `nat` end-to-end median | ±5.23 | marginal, **and its own null reads +4.38** |
| `nat` census wall | ±10.19 | 1.5× too coarse |
| `nat` census absolute busy | ±13.26 | 1.9× too coarse |
| SPLIT=1 census / median | ±49 to ±161 | 7–23× too coarse |

An effect of ~7 µs/step is resolvable at the kernel label and *provably
unresolvable* at every census estimator I can build on this host. A null census
here is therefore uninformative about a 7 µs/step effect, and I do not present
it as evidence of absence.

**Positive control #1 — the per-kernel estimator.** In the same reps, A1 and A2
move it by −6.80 and −6.36 µs/step with CIs excluding zero and 8/8 per-rep sign
agreement, while `0b` reads −0.63 [−3.44, +2.19]. So the estimator demonstrably
resolves ~6 µs/step and demonstrably reads zero when nothing changed. That is
what licenses reading A4's null as "A4 < ~3.2 µs/step", i.e. less than half
of A1.

**Positive control #2 — the census estimator.** The advisor asked for a control
guaranteed to move the number by a predicted size before any null is trusted. I
have one for free, because I ran the *same* 8 reps × 5 slots under both
`DARKBLOOM_GPU_PROFILE_SPLIT=1` and `SPLIT=0`. That regime switch is a known,
independently measured perturbation (PR #473: +1642 µs/step). Pairing the 40
matched `(rep, slot)` records:

| census estimator | SPLIT=1 − `nat` | 95 % CI |
|---|---|---|
| wall | **+1611.80 µs/step** | [+1576.33, +1647.27] |
| end-to-end median | +1597.12 µs/step | [+1560.11, +1634.14] |
| absolute busy | +603.72 µs/step | [+589.05, +618.40] |
| union busy | +601.15 µs/step | [+586.65, +615.65] |

The census wall recovers PR #473's +1642 µs/step to within 2 %, at n = 40 with
a ±36 µs/step CI. **The census instrument works.** It is simply, and
demonstrably, ~2× short of the resolution a 7 µs/step effect needs at n = 8.
(Side result: only 604 of those 1612 µs are GPU-*busy* time; the other ~1008
µs/step is inter-command-buffer gap across 361 extra CB boundaries ≈ 2.8 µs per
CB boundary, about twice rule 41's 1.4064 µs dispatch-boundary price. That is a
consistency check on rule 41, not a new claim.)

**Positive control #3 — the standalone probe.** Section 6's phase-split arms
delete an entire phase of the kernel and are guaranteed to move the number by a
large, predicted amount. They do: −155.81 µs/step [−156.17, −155.44] for the
GEMV phase and −12.80 µs/step [−13.22, −12.39] for the reduction tail, against
paired nulls of −0.34 and −0.05. So the probe resolves both a huge effect and a
~13 µs/step effect, and reads zero on a null.

---

## 3. Reachability audit

All line numbers re-grepped on the current base `3f430f6f` (post-#456 surface
reconstruction) with my patch applied.

| item | file | line |
|---|---|---|
| `let lagunaRouterWeightPrefetch: Int = {` (doc block 686–696) | `LagunaRuntimeModel.swift` | 697 |
| `private func lagunaNormReductionTail(` | `LagunaRuntimeModel.swift` | 831 |
| `private func lagunaRouterPrefetchGroups(rowsPerThread:prefetch:)` | `LagunaRuntimeModel.swift` | 877 |
| `private func lagunaResidualRMSNormRouterSource(rowsPerGroup:prefetch:)` | `LagunaRuntimeModel.swift` | 930 |
| `private let lagunaResidualRMSNormRouterKernels:` | `LagunaRuntimeModel.swift` | 1121 |
| `func lagunaResidualRMSNormRouter(` (dispatch wrapper) | `LagunaRuntimeModel.swift` | 1193 |
| kernel lookup `rowsPerGroup * 8 + lagunaRouterWeightPrefetch]!` | `LagunaRuntimeModel.swift` | 1225 |
| `lagunaRouterPrecomputedKeysEnabled` | `LagunaRuntimeModel.swift` | 171 |
| **call site — decode, per layer** | `LagunaRuntimeLayers.swift` | 2353 |
| **call site — `callLastPrefillRow`, prefill only** | `LagunaRuntimeLayers.swift` | 2450 |

Both call sites are gated on `let sparse = mlp as? LagunaRuntimeSparseMoEBlock`.

Configuration facts establishing that the control reaches the scored path:

- `lagunaRouterRowsPerGroup` defaults to **8**. At rpg8: `simdGroups = 16`,
  `rowsPerThread = 1`, `activeSimdGroups = 8` ⇒ the
  `if (simd_group < active_simd_groups)` guard is live and the unrolled-by-4
  branch is the one emitted.
- `lagunaRouterPrecomputedKeysEnabled` is on ⇒ dispatched kernel is
  `laguna_residual_rms_router_bf16_2048_rpg8_keys_v1` (+ arm suffix).
- `num_hidden_layers = 40`, `mlp_only_layers = [0]` ⇒ **39 sparse layers ⇒ 39
  decode dispatches/step**. GPUPROF independently confirms `n/step = 39.00`.
- Measured baseline: **8.2188 µs/call × 39 = 320.6 µs/step**, 3.9 % of the
  9.865 ms SPLIT=1 step.

---

## 4. Implementation

Eight hunks, all inside the router source generator, its kernel dictionary and
the dispatch wrapper. No other function is touched. The two behavioural
one-liners are:

```diff
-\(lagunaNormReductionTail2048)
+\(prefetchEarly)\(lagunaNormReductionTail2048)
...
-\(guardOpen)\
+\(prefetchLate)\(guardOpen)\
```

`prefetchEarly` / `prefetchLate` interpolate to `""` at depth 0, so **the
emitted Metal for arm 0 is byte-identical to the base emission** (3,490 B,
verified twice by byte-comparing the generated source). The peel declares
`thread vec<bfloat,4> laguna_pf[4*groups]` outside its own
`if (simd_group < active_simd_groups)` guard and indexes
`laguna_pf_row = tile * rows_per_group + simd_group * rows_per_thread`, which is
the same expression as `router_row`. The accumulate branch consumes
`laguna_pf[g*4+u][i]` in the **identical `(block, i)` order** into the same
single FP32 `router_result[0]`, then runs the original loop from
`block = prefetchGroups * 4`.

Exactness envelope respected: loads only, no per-iteration partials, `n_reads`,
`block_width`, `router_blocks`, the `simd_shuffle_down` ladder and the single
BF16 round are unchanged, and the norm half is untouched.

Depth is encoded in the kernel name (`_pf1`, `_pf2`, `_pf3`, `_pf4`, `_pf1c`)
because MLX's JIT caches by name. The dictionary is keyed
`rowsPerGroup * 8 + prefetch` over `[1,2,4,8,16,32,64] × [0…5]` = 42 entries,
all built eagerly, so **every arm compiles the identical pipeline set and only
the dispatched kernel differs**. That property matters in §7.

Arm ↔ env mapping (deliberately non-obvious, so stated explicitly):

| `DARKBLOOM_ROUTER_WEIGHT_PREFETCH` | arm | meaning |
|---|---|---|
| 0 | A0 | depth 0, shipped baseline |
| 1 | A1 | depth 1, hoisted above barriers |
| 2 | A2 | depth 2, hoisted |
| 3 | A5 | depth 3, hoisted |
| 4 | A3 | depth 4 (full block), hoisted |
| 5 | A4 | depth 1 **control**, identical peel left below the barriers |

Byte accounting on base `3f430f6f`: `Sources/MLXFastModel/LagunaRuntimeModel.swift`
grows **+4,135 B**. `senpai/validate-assignment-scope.sh` → *assignment scope
OK: 1 submitted path(s)*. `senpai/check-editable-budget.sh` → *editable budget OK:
current=2895390/3000000 headroom=104610 growth=4226/262144 files=141
(base=141)*. Per the advisor's latest note the per-file cap is no longer the
binding constraint (125,627 B of per-file headroom), so the patch is written for
clarity, not for bytes.

---

## 5. Occupancy gate

`maxTotalThreadsPerThreadgroup = 1024`, `threadExecutionWidth = 32`,
`staticThreadgroupMemoryLength = 4240` — **identical on all six arms**, all
PASS against the ≥ 512 hard gate at the 512-thread dispatch.

Caveat I want on the record rather than presented as reassurance: on Apple GPU
family 9+ `maxTotalThreadsPerThreadgroup` is a **weak** occupancy signal.
Dynamic Caching virtualises the register file, so the value pins at 1024 and
spills go to device scratch instead of reducing the reported limit. The
`staticThreadgroupMemoryLength` is also insensitive for the same reason. The
real register-pressure evidence is behavioural: see the depth-4 cliff in §6.

---

## 6. Standalone kernel probe, and the overlap ceiling

`research/maple_r89_router_probe.swift` compiles the Metal emitted by the
**scored generator itself** (`research/maple_r89_emit_router_sources.py` lifts
the generator verbatim, so probe and runtime cannot drift) and runs
ABBA/BAAB-interleaved paired differences.

Emitted sizes: arm0 3,490 B (byte-identical to base); arm1/2/5 4,391; arm3/4
4,394. `diff arm3 arm4` is only `laguna_pf[12]→[16]`, `k<12→k<16`, `g<3→g<4`,
`block=12→16`. `diff arm1 arm5` is **placement only** — a character-identical
12-line peel.

The probe was run four times across the assignment. Run 4 (this session, with
the phase arms added) reproduces run 3 arm for arm: A1−A0 −0.1114 vs −0.1062,
A2−A0 −0.3521 vs −0.3556, A3−A0 +0.3655 vs +0.3443, A4−A0 +0.0082 vs −0.0020.
The table below is run 3; run 4 is in the W&B artefact.

**COLD** (rotating 64 × 1 MiB weights, A0 = 6.51 µs/call):

| comparison | diff µs/call | 95 % CI | ×39 µs/step |
|---|---|---|---|
| null (pre) | −0.0024 | [−0.0232, +0.0184] | −0.09 |
| A1 − A0 (d1) | −0.1062 | [−0.1190, −0.0934] | −4.14 |
| A2 − A0 (d2) | −0.3556 | [−0.3658, −0.3453] | −13.87 |
| A5 − A0 (d3) | −0.3524 | [−0.3653, −0.3395] | −13.74 |
| A3 − A0 (d4) | **+0.3443** | [+0.3325, +0.3560] | **+13.43** ❌ cliff |
| A4 − A0 (control) | −0.0020 | [−0.0148, +0.0107] | null |
| A1 − A4 | −0.1141 | [−0.1269, −0.1012] | −4.45 |
| A2 − A4 | −0.3383 | [−0.3444, −0.3321] | −13.19 |
| null (post) | +0.0055 | [−0.0129, +0.0240] | +0.22 |

**HOT** (single resident 1 MiB weight, A0 = 3.49 µs/call): *every* arm costs —
A1 +0.0474, A2 +0.0824, A5 +0.2069, A3 +0.2678, A4 +0.0104, nulls +0.0029 /
−0.0011. This is the expected signature of a latency-hiding lever: with the
weight already resident there is no latency to hide, so only the fixed price of
the peel remains. A4 reading ≈ 0 in COLD while A1 reads −0.11 says that price
comes from **placement**, not from the peel's arithmetic.

The depth-4 cliff appears only COLD and degrades monotonically HOT, which points
at outstanding-load / MSHR saturation rather than an occupancy loss (consistent
with §5: the occupancy counters cannot see it).

### The overlap ceiling, measured

The advisor asked for the ceiling to be estimated explicitly and the prediction
stated as a fraction of it. I measured it rather than assuming it, with two
extra probe arms emitted by the same generator:

- **arm6 "P-norm"** — the router GEMV block is replaced by a single
  `router_result[0] = float(normalized_row[simd_lane * n_reads]);`. What
  remains is the residual add, sum-of-squares, cross-SIMD reduction, normalize
  and store. 2,738 B.
- **arm7 "P-gemv"** — the reduction tail is replaced by
  `float laguna_inv_mean = 1.0f;`, deleting the `simd_shuffle_down` ladder and
  its barriers while leaving the GEMV intact. 2,896 B.

Neither is a candidate; both are pure instrumentation and are not reachable
from the runtime (the generator only emits them under the research script).

| phase contrast | COLD µs/call | ×39 µs/step | 95 % CI (µs/step) | HOT µs/call |
|---|---|---|---|---|
| whole kernel A0 | 6.511 | 253.9 | — | 3.487 |
| P-norm − A0 ⇒ **router GEMV phase** | −3.9951 | **−155.81** | [−156.17, −155.44] | −0.9796 |
| P-gemv − A0 ⇒ **cross-SIMD reduction tail** | −0.3282 | **−12.80** | [−13.22, −12.39] | −0.3189 |
| ⇒ residual-add + sumsq + normalize (remainder) | ≈2.19 | ≈85.3 | — | ≈2.19 |

Two things follow.

1. **The reduction tail is ≈0.328 µs/call ≈ 12.8 µs/step, and it is
   COLD/HOT-invariant** (0.3282 vs 0.3189, a 3 % difference against a 1.9×
   change in the rest of the kernel). A phase whose duration does not care
   whether the weights are resident is a synchronisation/latency phase, not a
   bandwidth phase. That is exactly the window a prefetch can convert into
   useful load time.
2. **The ceiling for this lever is therefore ~12.8 µs/step, not 154 µs/step.**
   The prefetch is issued immediately before the tail, so at most it can hide
   the whole tail.

**Prediction as a fraction of the ceiling, and the outcome:**

| arm | measured, in situ | fraction of the 12.8 µs/step ceiling |
|---|---|---|
| A1 (depth 1) | −6.85 µs/step vs A4 | **54 %** |
| A2 (depth 2) | −6.41 µs/step vs A4 | 50 % |

A depth-1 hoist issues 4 of the 16 loads early, so recovering roughly half of
the tail is the right order of magnitude; and A1 ≈ A2 in situ says the window
saturates by depth 1 there, which is why depth 2 buys nothing extra even though
COLD-standalone it buys 3×. **The effect is bounded by a phase I measured, and
it lands at ~half of that bound.** Nothing here requires the 154 µs/step figure
the round-36 closure was arguing about.

For an independent in-situ anchor: `research/CURRENT_RESEARCH_STATE.md` §4.26
(lines 4400–4407) and `research/nezuko-pr158-decode-dead-time.md` (lines 551,
713, 750) put the residual-add + sumsq + reduction "norm prologue" of this same
kernel at **≈44 µs/step** in situ, and already showed that splitting it into its
own dispatch is net-negative (the extra dispatch costs ≈140 µs/step). My probe's
remainder figure (≈85 µs/step for residual-add + sumsq + normalize) is larger
because the standalone probe is cold and unshadowed; the prior art's in-situ
figure is the conservative one. Against the prior art's number the win is 6.85 /
44 ≈ **16 %** of the norm prologue. Either way the claim is a fraction of a
measured phase, not a fraction of a modelled "excess".

---

## 7. In-situ decode, SPLIT=1 per-kernel labels (n = 8 reps × 300 steps)

`research/maple_r89_insitu.py`, one process per slot, slot order forward on even
reps and reversed on odd (ABBA, rule 36), paired **within** rep.

**Router µs/step vs slot 0 (A0):**

| slot | arm | level µs/step | paired d | 95 % CI |
|---|---|---|---|---|
| 0 | A0 | 320.57 | — | — |
| 0b | null control | 319.95 | −0.625 | [−3.437, +2.187] |
| **1** | **A1 d1** | **313.77** | **−6.800** | **[−9.381, −4.219]** ✅ |
| **2** | **A2 d2** | **314.21** | **−6.362** | **[−7.737, −4.988]** ✅ |
| 3 | A5 d3 | 320.49 | −0.087 | [−1.876, +1.701] |
| 4 | A3 d4 | 318.90 | −1.675 | [−3.974, +0.624] |
| 5 | A4 control | 320.62 | +0.050 | [−3.111, +3.211] |

**Router µs/step vs slot 5 (A4) — the decisive contrast:**

| slot | arm | paired d | 95 % CI |
|---|---|---|---|
| 0 | A0 | −0.050 | [−3.211, +3.111] |
| 0b | null | −0.675 | [−3.830, +2.480] |
| **1** | **A1** | **−6.850** | **[−9.760, −3.940]** ✅ |
| **2** | **A2** | **−6.412** | **[−8.717, −4.108]** ✅ |
| 3 | A5 d3 | −0.138 | [−2.805, +2.530] |
| 4 | A3 d4 | −1.725 | [−3.080, −0.370] |

**Per-rep sign counts** (exact binomial, two-sided), vs A0: A1 8/8 negative
p = 0.0039; A2 8/8 p = 0.0039; A5 d3 4/8 p = 0.64; A3 d4 6/8 p = 0.14; A4 3/8
p = 0.86; `0b` 6/8 p = 0.14. Vs A4: A1 8/8, A2 8/8, A3 d4 8/8, all p = 0.0039.

**Reading.** A1 ≠ A4 with a CI excluding zero on both the A0- and A4-referenced
contrasts, with 8/8 sign agreement, while the two null arms (`0b`, A4) sit on
zero. So **the compiler does not already hoist these loads, AGX does keep the
`device` load in flight across a threadgroup barrier, and mechanism B is
confirmed at the kernel label.** Both of the assignment's merge CIs are met *on
this estimator*.

Reported **undiscounted**, per advisor comment 5228932028 item 5. I am not
applying the E = 0.349 in-situ shadowing haircut that a frontier reviewer
proposed, and I am not quoting any SPLIT=1 total, ratio or cross-kernel sum as
an end-to-end number.

### Kernels touched and not touched (PR #473 attribution hazard)

My patch changes exactly one kernel family:
`laguna_residual_rms_router_bf16_2048_rpg8_keys_v1[_pfN]`, generated at
`LagunaRuntimeModel.swift:929` and dispatched at `LagunaRuntimeLayers.swift:2353`
(decode) and `:2450` (prefill last row). It does **not** touch
`gate_sp_h64_v1`, `shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1`,
`sliding_fused_attn_ring_v1`, `laguna_moe_*`, the RoPE/embedding atlas, the
decode ordinal header, or any `arg_reduce`/SDPA/RMSNorm AOT kernel. PR #473 and
the queued router-tournament instruction diet share the decode-glue/router pool
with me, so the per-kernel label — not any pool total — is the grain at which my
claim is stated.

---

## 8. Negative-control matrix — and an independent confirmation of rule 43

Free re-analysis (`research/maple_r89_kernel_controls.py`, zero extra GPU time)
of the same GPUPROF tables, applying the identical paired estimator to all **28
untreated kernel labels**. `#sig` counts labels whose 95 % CI excludes zero.

| slot | 0 | 1 (A1) | 2 (A2) | 3 (A5 d3) | 4 (A3 d4) | 5 (A4) | **0b** |
|---|---|---|---|---|---|---|---|
| **#sig / 28** | 0 | 4 | 7 | 6 | 7 | 7 | **0** |

Two facts, and they point in opposite directions:

1. **The `0b` null control is clean on all 28 untreated labels** (max |d| = 1.17
   µs/step). The estimator is unbiased and run-order / position curvature is not
   manufacturing false positives.
2. **Every arm that dispatches a differently-*named* router kernel — including
   the A4 control, which is behaviourally a no-op — perturbs 4–7 untreated
   labels**, some substantially: `gate_sp_h64_v1` (251 µs/step) moves
   −3.88 / −14.16 / −13.20 / −14.15 / −2.01 for slots 1/2/3/4/5;
   `shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` (287 µs/step) moves
   +1.70 / −9.36 / −9.79 / −8.67 / **+11.08**; `sliding_fused_attn_ring_v1`
   (629 µs/step) moves **+9.54\*** / +7.42\* / +0.11 / +2.30\* / +0.60.

All 42 pipelines are built eagerly in every arm, so the *compiled set* is
identical and only the *dispatched* name differs. The best available explanation
is GPU code residency / instruction-cache layout shifting under SPLIT=1's
406-CB-per-step regime.

Consequences:

- **Cross-kernel sums under SPLIT=1 are not usable.** Consistency sum over all
  labels vs A0: A1 +9.74 [−42.2, +61.7]; A2 −33.26 [−62.6, −3.9]; `0b` +0.25
  [−50.2, +50.7]. Remainder excluding the router: A1 +16.54 [−32.9, +66.0];
  A2 −26.90 [−55.0, +1.2]; `0b` +0.88. I report these **only** as an
  internal-validity check and explicitly not as an end-to-end number — which is
  an independent, mechanism-level confirmation of rule 43 arrived at from a
  different direction than PR #473's CB-count argument.
- **The router contrast survives**, because `0b` and A4 both read null *on the
  router label* (−0.63, +0.05), and because the name/layout artefact is shared
  by A1 and A4 and therefore cancels in the A1 − A4 contrast. Five distinct
  kernel names (`""`, `_pf1c`, `_pf3`, `_pf4`) read null on the router label
  while two read ≈ −0.17 µs/call, which independently bounds any pure
  name artefact well below the effect.

**This may resolve a standing open question.**
`research/CURRENT_RESEARCH_STATE.md:4707` (open question Q6) records the
"#301 §7.3 decode-neighbour effect" as *"unexplained and large… if it is a
session artefact, it invalidates a class of our single-session Stage-3
numbers"*. I searched for prior art on JIT-kernel-name-induced perturbation of
untreated neighbours and found none. What I measured is exactly that shape: a
behaviourally null arm that only changes the *dispatched kernel name* moves
untreated neighbours by up to 14 µs/step, while a null arm that changes
*nothing at all* moves none of them. If that generalises, Q6's neighbour effect
is a code-residency artefact of changing a kernel name, and the mitigation is
the one I used here — always carry a same-name-changing control arm (my A4),
never a name-identical one alone. I have not tested this beyond my own kernel
family and offer it as a lead, not a finding.

---

## 9. `nat`-regime paired census (rule 43)

Rule 43 requires the end-to-end magnitude to come from a `nat`-regime (SPLIT=0)
paired ABBA census with n ≥ 8 duplexes, reporting wall **and** absolute busy.
I ran exactly that: `R89_SLOTS=0,0b,1,2,5`, 8 reps × 300 steps, SPLIT=0,
one process per slot per rep, ABBA slot-order alternation, paired within rep.
1789 s of GPU time. **Zero token divergences on every slot.**

Router per-kernel tables are empty here by construction: under SPLIT=0 a
command buffer holds many dispatches, so the driver correctly skips those rows.
That is why §7 exists at all.

**Census absolute busy, ms/step (ref = slot 0).** `gpu_busy_sum` and
`gpu_busy_union` are numerically identical (ratio 1.0000, sd 0.0000, n = 40) —
as the advisor said, that distinction is vacuous on M4 Pro.

| slot | level | paired Δ (ms) | 95 % CI | µs/step |
|---|---|---|---|---|
| 0 — A0 | 7.9874 | — | — | 0 |
| 0b — null | 7.9871 | −0.0002 | [−0.0135, +0.0130] | −0.25 [−13.51, +13.01] |
| 1 — A1 | 7.9982 | +0.0109 | [−0.0011, +0.0229] | +10.87 [−1.13, +22.88] |
| 2 — A2 | 7.9829 | −0.0045 | [−0.0184, +0.0094] | −4.50 [−18.36, +9.36] |
| 5 — A4 | 7.9642 | −0.0231 | [−0.0790, +0.0327] | −23.12 [−78.98, +32.73] |

**Census wall, µs/step (ref = slot 0):** `0b` −6.00 [−16.19, +4.19];
A1 +8.38 [−9.02, +25.77]; A2 −11.12 [−29.51, +7.26];
A4 −24.12 [−118.08, +69.83]. A0 level 8.2414 ms.

**End-to-end median, µs/step (ref = slot 0):** A0 level 8.2216 ms;
`0b` **+4.38 [−0.86, +9.61]**; **A1 +18.50 [+10.44, +26.56]**;
A2 +0.00 [−11.62, +11.62]; A4 −31.75 [−96.16, +32.66].

### Reading this honestly

Nothing here reaches significance on busy or wall — every CI contains zero, and
the floors (§2) are 1.5–1.9× the size of the effect, so that was the expected
outcome before I ran it.

The one nominally significant number is **A1 = +18.50 µs/step on the end-to-end
median, in the wrong direction**, and I am reporting it rather than burying it.
I do not believe it is a mechanism, for three reasons, and I would rather state
them explicitly than have them found in review:

1. **Its own null control is not clean.** `0b` — an identical copy of A0 in a
   different slot position — reads +4.38 [−0.86, +9.61] on the same estimator.
   A systematic per-slot-position bias of ~4 µs/step exists on the median.
2. **The behaviourally null A4 reads −31.75 µs/step** on the same estimator,
   with a ±64 µs/step CI. A no-op arm swinging −32 µs/step is a direct
   demonstration that between-process offsets dominate this estimator.
3. **A2 contradicts it.** A2 is a strictly *larger* version of the same
   perturbation (8 hoisted loads instead of 4, same placement, same mechanism).
   If A1 genuinely cost +18.5 µs/step end to end, A2 should cost at least as
   much. A2 reads exactly **+0.00 [−11.62, +11.62]**. A dose-response that is
   large at dose 1 and exactly zero at dose 2 is not a dose-response.

So: **the `nat` census is uninformative here, in the direction of "cannot
tell", and I am not claiming an end-to-end win from it.** The instrument itself
is sound — positive control #2 in §2 shows it recovers a +1612 µs/step known
perturbation to within 2 % — it is simply ~2× short of the resolution this
effect needs at n = 8. Getting it there would need ~n = 30 duplexes
(≈2 h of GPU per estimator) *and* an in-process arm switch to escape the
cross-process penalty, which the static-initialiser selection mechanism
forbids.

---

## 10. Correctness

### 10.1 In-situ token divergence — zero on every arm, both regimes

The in-situ harness re-checks greedy tokens against the run's own reference on
every rep. Divergence counts:

| regime | reps × steps | slots checked | divergences |
|---|---|---|---|
| SPLIT=1 | 8 × 300 | A0, 0b, A1, A2, A5, A3, A4 | **0 on every slot** |
| `nat` (SPLIT=0) | 8 × 300 | A0, 0b, A1, A2, A4 | **0 on every slot** |

That is 0/8 reps × 0 divergent tokens across all 7 depths including the full
peel A3 and the below-barrier control A4. This is the expected result: the edit
is LOADS ONLY. `n_reads`, `block_width`, `router_blocks`, the `simd_shuffle_down`
ladder, the single BF16 round, and the `(block, i)` accumulation order into the
one FP32 `router_result[0]` are all untouched, and the norm half of the kernel
is not modified at all.

### 10.2 Upstream equivalence — bit-identical to base, and the one failure is pre-existing

`research/run_upstream_equivalence.sh` (bare filter
`lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled`, debug metallib repaired
from the release worker build, zero-selected-tests self-check active). Three
invocations on this host, all with `EQUIVALENCE_EXACT_STEPS=8`:

| build | prefill max‖Δlogit‖ | prefill mean‖Δlogit‖ | decode-0…7 max‖Δlogit‖ | every token |
|---|---|---|---|---|
| **unchanged base file @ `3f430f6f`** | 0.125 | 0.011933609 | 0.0 (all 8) | matches upstream |
| candidate, `DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0` | 0.125 | 0.011933609 | 0.0 (all 8) | matches upstream |
| candidate, `DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1` (**shipped**) | 0.125 | 0.011933609 | 0.0 (all 8) | matches upstream |

The three reports are **identical to every printed digit**, including the
mantissa-level `meanAbsoluteLogitError` — 0.011933609 in all three. Tokens
(5991, 509, 902, 5991, 509, 902, 5991, 509, 902) are identical across all three
and equal to upstream in all three.

All three also **fail** the test, because `LagunaCorrectnessTests.swift:249`
asserts `maximumAbsoluteLogitError` against a tolerance of exactly **0.0** and
prefill reads 0.125. Following the AGENTS.md instruction for a non-M5 host
disagreeing with a fixture, I ran the *unchanged base* file in the same
incremental build (temporary commit, reverted; branch tip restored to `9453d7b`
and re-verified by SHA-256 of the submitted file) and it fails identically.
So this is a **pre-existing M4 Pro artifact of the base, not a regression from
this change**. Corroborating detail: 0.125 is exactly 1 ULP of BF16 at magnitude
16–32, i.e. a single-rounding difference in the prefill logits, and it appears
*only* on prefill — the phase where M4 Pro (Apple GPU generation 16) does not
select the `_nax` kernels the M5 uses. The scored decode path is exact to 0.0.

I did **not** set `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` at any point in this
experiment.

**The correctness claim I am actually making is the strong one and it does not
depend on the M5-fixture question at all:** the candidate at the shipped depth 1
is *byte-for-byte identical in output* to the unchanged base on this host. Any
verdict the base earns on the ranked M5, the candidate earns too.

### 10.3 Public 64-step tripwire and goldens

`./benchmark.sh --local-iterate` was run twice back to back in one session on
the quiet host, both behind the 40 °C thermal gate, from the identical tree
(`commit 9453d7b`, worktree clean): once on the **shipped default (depth 1,
no environment overrides)** and once with
`DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0`, which makes the emitted Metal
byte-identical to the base kernel (3,490 B, §4). Both exited 0.

| field | depth 1 (shipped default) | depth 0 (`=0`, base-identical Metal) |
|---|---|---|
| `passed` | **true** | **true** |
| `passed_correctness` | **true** | **true** |
| `max_abs_diff` | **0** | **0** |
| `checked_steps` | 130 | 130 |
| `case_count` | 1 | 1 |
| `first_failing_case` / `_layer` / `_step` | null / null / null | null / null / null |
| `error` | `""` (empty) | `""` (empty) |
| `golden_hash` | `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63` | same |
| `harness_hash` | `a49b5612a6b56882af1d20b17b0dffe4780fa7b862b9c901b6b54d19526b93a9` | same |
| `commit` | `9453d7b` | `9453d7b` |
| `peak_ram_gb` | 21 | 21 |
| `timestamp` | `2026-08-09T00:49:12Z` | `2026-08-09T00:53:11Z` |

**Every one of the 130 checked greedy steps matched, `max_abs_diff` is exactly
0, and no golden-drift note was emitted in either run.** I did not set
`MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` (it appears nowhere in either log or in any
command I issued).

The timing numbers the same two runs produced, reported for completeness and
explicitly **not** offered as evidence for the hypothesis:

| field | depth 1 | depth 0 | Δ (d1 − d0) |
|---|---|---|---|
| `decode_seconds_per_token` | 0.01307511 | 0.01306479 | **+10.3 µs/step** |
| `decode_speedup` (floor 0.95) | 1.0597 ✅ | 1.0606 ✅ | −0.0009 |
| `prefill_seconds_per_token` | 0.00111159 | 0.00113759 | −26.0 µs/token |
| `prefill_speedup` (floor 0.95) | 0.3306 ❌ | 0.3231 ❌ | +0.0075 |
| `score` (est) | 0.79202 | 0.78792 | +0.0041 |

Three things must be said plainly about that table:

1. **It is n = 1 per arm, so it has no resolution at all.** There is no variance
   estimate, hence no CI, hence nothing to compare against the 6.85 µs/step
   effect. The observed decode delta is +10.3 µs/step — nominally the *wrong*
   sign — and the observed prefill delta is −26.0 µs/token in a phase this
   lever barely touches (one router call per prefill vs 39 per decode step),
   which is itself the clearest available demonstration that both numbers are
   sampling noise. The harness's timed window is 2.2 s over 130 steps; my
   in-situ census (§7) is 8 duplexes × 300 steps and still needed ±1.3
   µs/step of paired structure to see the effect. `--local-iterate` is ~40×
   shorter and unpaired. This is the same floor arithmetic as §2: an
   underpowered instrument reporting a wrong-signed point estimate is not
   contrary evidence, it is *no* evidence.
2. **The speedups are not same-session paired speedups.** The harness divides by
   pinned constants — `baseline_decode_seconds_per_token = 0.01385621`,
   `baseline_prefill_seconds_per_token = 0.00036752` — which come from the
   ranked M5, not from a baseline measured next to these candidates. The
   `score.local-iterate.baseline.json` that also sits in the tree is a stale
   2026-08-07 artifact from an unrelated commit (`61b064b`) built against a
   *different harness* (`harness_hash 9e7e0bad…` ≠ `a49b5612…`); the "vs
   baseline" lines `benchmark.sh` prints against it are cross-commit,
   cross-harness, and I do not rely on them anywhere in this report.
3. **The prefill floor failure is a host artifact, not a candidate
   regression.** It fails identically in the base-identical depth-0 arm
   (0.3231) and in that stale unrelated `61b064b` run (0.3266). M4 Pro reports
   Apple GPU generation 16 and does not select the `_nax` prefill kernels the
   ranked M5 uses, so this machine's prefill seconds/token are ~3× the M5
   constant it is being divided by. Nothing in this change touches prefill
   dispatch. The decode floor passes in both arms.

---

## 11. Prior art this contradicts, and why I ran it anyway

`research/CURRENT_RESEARCH_STATE.md` §4.26 (line 4757) says
"⛔⛔ Round-36 recon A — the `residual_rms_router` family is **CLOSED**", and
line 1554 says the "~154 µs excess is a unique-vs-issued-byte artifact … on
*issued* bytes the kernel already runs at ≈ 81 % of the M4 ceiling. In situ it
is two-thirds shadowed (E = 0.349, 2.73 µs/call marginal vs 7.72 census). Every
lever is dead … **Do not re-propose.**" (See also lines 1012, 2269, 3471, 6723.)

I am surfacing this rather than hiding it. My rebuttal is narrow: **that closure
ruled out byte reduction.** This lever moves **zero bytes** — the same 2048
BF16 columns are read, in the same order, by the same instructions — and is
pure latency scheduling. The 81 %-of-ceiling result is a bandwidth statement and
says nothing about whether issue timing is optimal. The measurement supports the
rebuttal: A1 and A4 read the *identical* number of bytes and differ by 6.85
µs/step.

I am *not* claiming the closure was wrong about bytes, and I am *not* using
rule 41 to promote this lever. The E = 0.349 shadowing figure is the strongest
reason to expect the kernel-local win to shrink in situ; the advisor has
instructed me to report undiscounted, so the raw number above is the raw number,
and §9 is where the shadowing question actually gets adjudicated.

For scale: the closest prior comparable, PR #60's in-loop unroll hoist, moved
the step 13 µs = 0.15 %.

---

## 12. Honest three-tier claim

| tier | claim | verdict |
|---|---|---|
| **Attribution** (per-kernel label, SPLIT=1, σ = 3.34) | hoisting the peel above the barriers reduces router kernel time by 6.80 µs/step vs A0 and 6.85 vs A4 | **positive**, CI excludes zero, 8/8 sign, negative controls clean |
| **Projection** | 6.85 µs/step ÷ 8.213 ms nat step ≈ **0.083 %** of decode; ranked weight 0.75 ⇒ ≈ **+0.06 %** score if it transfers 1:1 | not measured, stated as arithmetic only |
| **End-to-end** (`nat` census, rule 43, ±13.26 busy / ±10.19 wall / ±5.23 median) | no improvement detected; A1 reads **+10.87 busy [−1.13,+22.88]**, **+8.38 wall**, **+18.50 median [+10.44,+26.56]** vs A0 — i.e. nominally *slower*, not faster | **not adjudicated — the census cannot separate a 6.85 µs/step effect from its own artifacts on this host** (see §9) |

Why I do not report the `nat` median as a regression: its own null slot 0b reads
**+4.38 µs/step** (the median estimator is the one estimator whose null is *not*
clean), the behaviourally-null control A4 reads **−31.75**, and A2 — a strictly
larger dose of the same edit — reads **exactly +0.00**. A mechanism that is
monotone in dose cannot produce d1 = +18.5, d2 = 0.0. The honest statement is
that the `nat` census on this rig has no resolving power here, in either
direction.

The single strongest objection to promoting this, which my data cannot defeat:
under SPLIT=1 the router kernel gets its own command buffer, so the post-barrier
stall is fully exposed; in the shipped 45-CB regime it may already be hidden
behind neighbouring work. My `nat` floors are **±13.26 µs/step busy, ±10.19
wall, ±5.23 median** — 1.5–1.9× the 6.85 µs/step effect on the two estimators
with clean nulls — so this rig is roughly **2× short** of the resolution
required, not 10× short. The cross-regime positive control in §2 confirms the
instrument itself is sound (it recovers PR #473's +1,642 µs/step to within 2 %);
it is simply not sensitive enough. Closing that 2× would take ~30–40 paired
duplexes at n = 8 each, or in-process arm switching, which the
read-once-at-static-init env knob makes impossible without changing the shipped
selection mechanism.

Other honest caveats:

- The standalone microbenchmark **understated** the effect at depth 1 (−4.14
  µs/step COLD vs −6.80 in situ) and **disagreed on depth shape**: COLD ranked
  d2 ≈ d3 ≫ d1 while in situ d1 ≈ d2 ≫ d3 ≈ 0. Trust the in-situ ordering; the
  microbench working set is not the real one.
- `gpu_busy_sum / gpu_busy_union = 1.0000`, sd 0.0000, n = 40 under `nat`
  (1.0003, sd 0.0001, n = 56 under SPLIT=1) — the sum/union distinction is
  **vacuous on M4 Pro**, exactly as the advisor stated. Noted once, not used
  again.
- Independent replication of #473's instrument cost: my `nat` median is 8.213
  ms/step vs 9.865 ms/step under SPLIT=1 ⇒ **1,652 µs/step**, against #473's
  independently measured 1,642 µs/step.
- M4 Pro reports Apple GPU generation 16 and does not select the `_nax` prefill
  kernels. This lever is not an `_nax` change, but the ranked M5's cache
  hierarchy and MSHR budget differ, so the depth-4 cliff location is not
  guaranteed to transfer.

## 13. Why depth 1 ships

d1 and d2 are statistically tied in situ (−6.80 vs −6.36, overlapping CIs). I
ship **d1**:

- nominally best in situ;
- half the live-register span (8 vs 16 32-bit registers per lane), i.e. one step
  further from the depth-4 cliff, which is the only catastrophic failure mode
  observed (+13.4 µs/step COLD);
- the cliff is a memory-parallelism limit, and the M5's limit is unknown; the
  cheaper arm is the safer arm on unseen hardware.

Counterargument I want on the record: if M5 decode behaves like my COLD
microbench rather than my in-situ rig, d2 would have delivered ~2–3× the
per-call gain and d1 leaves that on the table. I judge P(cliff moves down to d2
on M5) ≈ 10 %.

---

## 14. Reproduction

```bash
# scored build
./benchmark.sh --local-iterate

# emitted Metal per arm + phase-split diagnostics
python3 research/maple_r89_emit_router_sources.py /tmp/r89src 8

# occupancy gate + ABBA/BAAB paired kernel timing + phase durations
xcrun swiftc -O research/maple_r89_router_probe.swift -o /tmp/r89probe
/tmp/r89probe /tmp/r89src

# in-situ per-kernel labels (attribution grain, SPLIT=1)
python3 research/maple_r89_insitu.py /tmp/r89insitu 8 300 1

# in-situ nat-regime census (rule 43 grain, SPLIT=0)
R89_SLOTS=0,0b,1,2,5 python3 research/maple_r89_insitu.py /tmp/r89nat 8 300 0

# free re-analysis: negative-control matrix over untreated kernel labels
python3 research/maple_r89_kernel_controls.py /tmp/r89insitu 0

# correctness
DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0 research/run_upstream_equivalence.sh
DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1 research/run_upstream_equivalence.sh
```

W&B — entity `wandb-applied-ai-team`, project `mlxfast-maple`, group
`r89-a-router-weight-prefetch`. Every run carries the occupancy gate, the COLD
and HOT microbench contrasts, and the SPLIT=1 and `nat` in-situ contrasts
(`insitu/*` and `insitu/nat_*`), plus `vsA4_*` for the control contrast, and
`correctness/divergences_max`.

| run | arm | W&B run id | URL |
|---|---|---|---|
| `r89a-arm0` | A0 depth 0 (baseline, = shipped base) | `vu8o8iet` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/vu8o8iet |
| `r89a-arm0b` | A0′ depth 0 (null control, second slot) | `tdaj7nqj` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/tdaj7nqj |
| `r89a-arm1` | **A1 depth 1 hoisted (shipped default)** | `dio6djt1` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/dio6djt1 |
| `r89a-arm2` | A2 depth 2 hoisted | `udeoztus` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/udeoztus |
| `r89a-arm3` | A5 depth 3 hoisted | `hojidlc7` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/hojidlc7 |
| `r89a-arm4` | A3 depth 4 hoisted (full peel) | `1n24985y` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/1n24985y |
| `r89a-arm5` | **A4 depth 1 control (loads *below* the barriers)** | `qmkav530` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/qmkav530 |
| `r89a-summary` | all tables (occupancy, COLD/HOT, SPLIT=1, `nat`) | `lh0lp2nf` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/lh0lp2nf |

(`arm3`/`arm4`/`arm5` run names follow the env slot, not the arm letter; the
`arm_label` config field on each run gives the unambiguous mapping.)

---

## 15. Policy ruling requested

Rule 43 says an end-to-end magnitude must come from a `nat`-regime paired ABBA
census. The assignment's merge criteria are written on the per-kernel estimator
(A1 beats A0 and A1 beats A4, both CIs excluding zero). On this host those two
requirements are **mutually unsatisfiable for an effect of this size**: 6.85
µs/step is 2.5× my per-kernel resolution and 0.14× my census resolution.

I have met the assignment's stated criteria and cannot meet rule 43's, so I am
submitting this as **attribution-positive / end-to-end-below-floor** and asking
for a ruling rather than asserting a merge. Three options as I see them:

1. **Merge on attribution.** The change is bit-exact, byte-neutral, occupancy-safe,
   and its causal mechanism is isolated by a character-identical placement
   control. Downside: rule 43 is bypassed for the magnitude.
2. **Hold for an M5 measurement.** The ranked M5 would settle both the transfer
   question and the depth choice. This is my preference if M5 time exists.
3. **Reject as unresolvable on M4.** Defensible, and I would not argue with it —
   but note that under this standard *no* ≤ 10 µs/step lever can ever be
   promoted from an M4 host, which is a fairly consequential precedent.

## 16. Suggested follow-ups (not implemented)

- The same hoist at the **QKV** norm site and at the second
  `lagunaNormReductionTail2048` site. Rule 24 forbade me from extending there;
  the mechanism is identical and should replicate.
- An in-process arm-switching harness (make the depth a dispatch-time argument
  rather than a static-init env read) so a `nat` census with n ≈ 150–400 paired
  duplexes becomes possible. This is the single change that would let *any*
  sub-10 µs/step lever clear rule 43 on non-ranked hardware.
- A stationarity check (first-vs-late steps within a rep) which I did not run.
- Fold the JIT-name/instruction-residency artefact from §8 into standing
  doctrine: any arm that changes a kernel *name* perturbs unrelated labels under
  SPLIT=1, so name-matched controls (my A4) should be mandatory, not optional.
