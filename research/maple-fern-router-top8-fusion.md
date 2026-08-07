# PR #204 — Router top-8 fusion: publishing the decode router from the QMV producer

- assignment: `maple-2026-08-07b-router-top8-fusion`, revision `r1`
- branch: `maple-fern/router-top8-fusion`, base `1fe609eb920dd96a409f2949a0e901d3bb525af6`
- submitted surface: `Sources/MLXFastModel/LagunaRuntimeModel.swift` only
- measurement host: Apple **M4 Pro**, 48 GiB (low-memory startup profile), 20 GPU cores

## 1. What was changed

Arm 3 of the pre-registered set: **delete the standalone dispatch, let an
existing producer emit the result.**

At decode, every one of the 39 MoE layers issued
`laguna_decode_router_top8_ordinal_table_norm_v1` as its own Metal dispatch —
one threadgroup of 256 threads that sorts 256 ordinal keys, extracts the top 8,
reads 8 scores back out of a threadgroup table, sums them across a simd and
writes 8 `uint32` indices plus 8 `float32` normalized scores.

The change makes the routed gate/up NVFP4 QMV+SwiGLU kernel publish those two
arrays itself, from **one** of its 2048 threadgroups, and skips the standalone
dispatch entirely. Net dispatch delta: **−39 per decode step, +0 added.**

### 1.1 Why this is nearly free — the load-bearing observation

The QMV kernel is `..._packed_top8keys_r1_...`: it already receives
`router_keys` and each threadgroup **already runs the selection tournament for
itself**, in the shared prelude (`LagunaRuntimeModel.swift:7504`):

```metal
thread uint top8_keys[8];
for (uint j = 0; j < 8; ++j) { top8_keys[j] = router_keys[lane + 32u * j]; }
uint top8_mask = 0u, top8_winner = 0u;
for (uint r = 0; r <= expert_slot; ++r) {
    top8_winner = laguna_router_top8_extract_round(top8_keys, top8_mask, lane);
}
uint expert = top8_winner;
```

So the top-8 selection was **already being computed 2048 times per layer**
inside the consumer. The standalone dispatch was a 39×/step *redundant
re-selection*; its only unique product was the normalized score vector and a
materialized index array for the down kernel.

Threadgroup `group == 7` has `expert_slot == 7`, so it already executes all
eight extraction rounds. The emit block re-runs those eight rounds on
`simd_group == 0` from a **fresh reload of the keys** rather than threading a
per-rank winner through the prelude. That is deliberate: it keeps the fallback
kernel's Metal source byte-for-byte identical, so the non-emit path cannot
regress. The marginal added ALU is one extra 8-round tournament on 32 lanes of
1 of 2048 threadgroups, against a per-threadgroup 2048-wide NVFP4 dot product
that dominates it by orders of magnitude.

### 1.2 Shape of the edit

Two edits in one file, +188/−6:

1. `lagunaRoutedSwiGLUQMVPackedTop8R1Source(emitRouter:)` — the existing source
   builder gains a flag. `emitRouter: false` reproduces the previous source
   byte for byte; `true` appends the emit block. A separate kernel object,
   `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_emit_bf16_v1`, carries the
   extra outputs (renaming is mandatory — the JIT cache is keyed by name).
2. A guarded fast path in `LagunaRuntimeSparseMoEBlock.forward`, placed
   immediately before `gate(x, logits:)`, that calls the emit kernel and returns
   through the existing down+residual fusion. The guard set is a restatement of
   the guards the existing fused chain already required, plus the emit flag.
   `fusedSharedDownInputs` is evaluated **last** so a fall-through never wastes a
   dispatch. The prefill branch and every fallback are untouched.

`DARKBLOOM_DECODE_ROUTER_EMIT_SINK=0` restores the previous behaviour on the
same binary. That is what makes the A/B below a true single-binary contrast.

## 2. Bit-exactness

### 2.1 The two traps, and why they are avoided

The assignment pre-registered two ways this change silently breaks exactness.

**Trap 1 — summation order.** The deployed kernel accumulates
`total = simd_shuffle(my_score, i) + total` for `i = 0..7`, i.e. strictly in
rank order with the running total on the right. Floating-point addition is not
associative, so any reassociation changes the result. The emit block reproduces
that loop verbatim, including operand order.

**Trap 2 — score provenance.** The scores must come from the same sigmoid
expression, never reconstructed from the lossy ordinal key. The emit block uses
`x = float(router_logits[my_index]); y = 1/(1+exp(|x|)); score = x<0 ? y : 1-y`,
reading the same `bfloat16` logits array the gate's decode cast-sink already
passes to the standalone kernel unconverted.

### 2.2 The deployed variant is the *table* variant

A correction to the assignment's framing: the default deployed kernel is
`..._ordinal_table_norm_v1`, not the recompute variant
(`DARKBLOOM_ROUTER_ORDINAL_SCORE_TABLE` defaults on, `:8809`). The table variant
stashes `original_scores[lane] = score` in threadgroup memory before the sort
and reloads `my_score = original_scores[my_index]` after it. An `fp32` store
followed by an `fp32` load is the identity, and the sort's `stride >= 32` rounds
carry barriers that separate the write from the read, so the table and recompute
variants are bit-identical. The emit block matches both.

### 2.3 Three-axis structural argument

- **Selection** — `laguna_router_key_ordinal` is the standard monotone
  `float → uint` total order (NaN above every finite key; both zeros map to the
  same code), and `laguna_router_ordinal_before` breaks ties by index. This is
  structurally the same comparator and the same total order the standalone sort
  uses, so the *set* of eight winners agrees.
- **Rank** — the tournament extracts winners one at a time, masking each as it
  goes, so rank `r` is the `r`-th largest under that total order, matching the
  sorted array's position `r`.
- **Scores** — identical expression on identical inputs (§2.1).

### 2.4 Empirical certificate

Full-vocabulary bitwise logit digests (`top_k = 100352`, SHA-256 per step),
64 teacher-forced steps, both arms on the **same binary**:

| arm | `DARKBLOOM_DECODE_ROUTER_EMIT_SINK` | run digest |
|---|---|---|
| `emit` | 1 | `3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928` |
| `base` | 0 | `3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928` |

**0 of 65 step digests differ.**

### 2.5 Sensitivity control — the certificate is not vacuous

A digest match only means something if the instrument can see a difference.
Downstream, the score is consumed as `bfloat(router_weights[routed_slot])`
(`:8068`) — it is rounded to `bfloat16`. So a 1-ULP **fp32** perturbation would
be absorbed by that cast and would prove nothing. The injected fault is
therefore exactly **one `bfloat16` ULP** on the stored score:

```metal
float fault_out = my_score / total;
fault_out = as_type<float>(as_type<uint>(fault_out) + (1u << 16));
```

| arm | run digest | vs clean reference |
|---|---|---|
| `faultemit` (sink=1) | `13a22cdee14a0798960f46a1b4bf0156e4fdd02bf07ace120f8d65fe6c625341` | **differs** |
| `faultbase` (sink=0) | `3447204b…4928` | identical |

**65 of 65 step digests differ, first difference at step 0.** The fault-carrying
binary still reproduces the clean reference exactly on the base arm, which also
confirms the fault is confined to the emit path. The instrument has full
sensitivity to the smallest perturbation that can survive to the consumer; the
0/65 match in §2.4 is a real certificate.

### 2.6 Reachability witness

`DARKBLOOM_TRACE_FUSION=1` with the sink on prints:

```
mlxfast: fusion active: routed gate/up QMV + SwiGLU (packed, producer keys, router sink)
```

The guard chain is entered on the scored decode path, so the digest match is
not the trivial consequence of a fall-through.

## 3. Pre-registered timing predictions

Recorded **before** any timing data was inspected, from an independent analysis
of the dispatch cost model `T = a + W·φ` with `a = 1.661 µs`,
`φ = 1.469 µs/wave` (single-threadgroup floor `a + φ = 3.13 µs`):

| model | predicted Δ decode µs/step |
|---|---|
| strictly serial dispatches | −181 (range −122 … −205) |
| fully overlapped dispatches | −68 (range −40 … −110) |
| **best point prediction** | **−110**, 90% CI [−55, −175] |

The competing published figures for this kernel family are mutually
inconsistent and cannot all be the *marginal* cost: 4.70 µs/call profiled
(185.7 µs/step), 205.3 µs/step profiled by census, 139.6 µs/step census
"deconvolved", 105.6 µs/step in a prior critique. The A/B measures the marginal
cost directly and adjudicates between them.

<!-- RESULTS SECTION PENDING -->
