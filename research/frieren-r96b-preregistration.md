# R96-B preregistration — certified lossless top-8 screen for the BF16 MoE router

**Committed before any Stage 1 data was generated or inspected.**
Assignment: PR #512, `maple-r96-b-router-certified-screen`, rev `r96-b-rev1`.
BASE_SHA `43036cd39dd3c795b117b099f0fe52767fbedbca`. Host: M4 Pro, 48 GiB, macOS 26.5.2.

## 1. What is being decided

Stage 1 decides, from real decode-time data, whether a **certified lossless**
low-precision screen of the router matrix can remove enough bytes per decode step
to be worth building. No kernel is written in Stage 1.

## 2. Verified target (code facts, established before the bar was fixed)

The decode router GEMV is **not** a standalone dispatch. It is fused into
`laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:930-1149`, wrapper `:1193-1235`),
called from the scored decode path at
`Sources/MLXFastModel/LagunaRuntimeLayers.swift:2345-2362`. That kernel reads the
full row-major BF16 `[256, 2048]` router weight (`:1208`, indexing `:1010-1014`)
once per sparse layer per token.

Reference arithmetic that any screen must reproduce, read from the kernel source:

* per lane `l`: `acc_l = Σ_{block=0..15} Σ_{i=0..3} f32(w[row, l*4 + block*128 + i]) * f32(x[l*4 + block*128 + i])`
  accumulated in FP32 in ascending block order (`:1007-1024`);
* `router_result[r] = simd_sum(acc_l)` over 32 lanes;
* `L_i = bfloat(router_result[i])` — **the reference logit is BF16**
  (`:961-969`);
* `score_i = sigmoid(f32(L_i))`, `key_i = ordinal(-(score_i + bias_i))` (`:963-967`);
* `x` is exactly the BF16 `normalized` output of the same kernel, so the screen
  and the reference consume an identical input vector.

Gate contract (`LagunaRuntimeLayers.swift:1386-1500`): top-8 **choice** uses
`sigmoid(L) + e_score_correction_bias`; mixture **weights** are the *pre-bias*
`sigmoid(L)` of the 8 winners, then `normTopkProb` renormalized.
`routerLogitSoftcapping == 0` for this config. Therefore a screen must certify
the choice AND recover the exact pre-bias `sigmoid(L)` for the 8 winners, which
requires an exact re-read of at least those 8 rows.

Per sparse layer (39 of 40): weight `1,048,576 B`, bias `1,024 B`.
Family total **40,934,400 B/step**.

## 3. Pre-specified screen grid

Only these configurations will be evaluated. No post-hoc additions.

* **Scheme A — symmetric power-of-two group scale** (the shipped LM-head form,
  `LagunaLmHeadPrune.swift:864-918`): `sd = 2^e` per group, `q = round(w/sd)`,
  `|w - sd*q| <= sd/2` exactly (flat half cell, because `sd` is a power of two).
  Group scale stored as 1 B e8m0.
* **Scheme B — affine min/max group scale**: `s = (max-min)/(2^b - 1)`,
  `|w - (s*q + min)| <= s/2`. Group scale + group min stored as 2 B FP16 each.

Bit widths `b ∈ {8, 6, 5, 4, 3}`. Group sizes `G ∈ {32, 64, 128, 2048}`
(`2048` = one group per row). Scheme A additionally requires
`max|q| <= 2^(b-1) - 1` on the real tensor; a row that does not fit is recorded
as an escaped row that reads BF16 in full (`0xFF` sentinel precedent,
`LagunaRuntimeWeights.swift:918`).

## 4. Pre-specified error bound (rigorous, two-sided)

For expert `i`, with screen logit `l̂_i = Σ_j x_j ŵ_ij` (FP32):

1. **L1 bound** `E1_i = Σ_g (halfcell_{i,g}) * Σ_{j∈g} |x_j|`, where
   `halfcell = sd/2` (A) or `s/2` (B).
2. **L2 / Cauchy–Schwarz bound** `E2_i = ||x||_2 * ||W_i - Ŵ_i||_2`, with the
   exact residual norm stored per row (2 B/row FP16, rounded up; 512 B/layer).
3. **Screen accumulation slack** `η_i = 2^-18 * Σ_j |x_j ŵ_ij|`. (A chunked FP32
   sum of 2048 terms with 16 sequential chunks and a 5-level tree has error
   `<= 21 * 2^-24 * Σ|terms| < 2^-19.7 * Σ|terms|`; `2^-18` over-bounds it.)
4. **Reference BF16 rounding** `ρ_i = ulp_bf16(|l̂_i| + E_i + η_i) / 2`, because
   the reference logit `L_i` is the BF16 rounding of the exact FP32 accumulator.

`ε_i = min(E1_i, E2_i) + η_i + ρ_i`, and the certified interval on the
**bias-corrected** score is
`c^-_i = sigmoid(l̂_i - ε_i) + b_i`, `c^+_i = sigmoid(l̂_i + ε_i) + b_i`
(exact sigmoid of the endpoints, tighter than a Lipschitz bound, and rigorous
because sigmoid is monotone).

## 5. Pre-specified certification and byte accounting

`τ = ` 8th largest of `{c^-}`. Candidate set `C = { i : c^+_i >= τ }`
(non-strict, so an exact tie is conservatively a candidate). `|C| >= 8` always.
Every row in `C` is re-read at full BF16 precision and its logit recomputed with
the reference lane mapping, so the recovered `(indices, weights)` are
bit-identical. Define the **excess** `A = |C| - 8`.

```
net_bytes(layer-step) = plane_bytes + scale_bytes + 512 + 4096 * |C|
plane_bytes  = 256 * 2048 * b / 8
scale_bytes  = 256 * (2048/G) * (1 for scheme A, 4 for scheme B)
baseline     = 1,048,576 B
```

Score credit uses the programme's realised byte price
**0.015224 % score per MB/step** (PR #110 ledger), reported alongside the
DRAM-model upper bound `t = 3.97 µs + bytes / 266.3 GB/s` (rule 55).

## 6. GO / NO-GO bar (fixed now)

**GO to Stage 2** iff at least one configuration in the Section 3 grid satisfies
all three:

* **(i)** mean `net_bytes` over all dumped decode layer-steps
  `<= 0.60 * 1,048,576 = 629,146 B` — i.e. **>= 40 % net byte reduction**,
  **>= 16.35 MB/step**, **>= 0.249 % score**;
* **(ii)** `p99(A) <= 16` over all dumped decode layer-steps;
* **(iii)** `max(A) <= 64` (escape-path feasibility ceiling for the kernel).

Otherwise **NO-GO**: terminal negative result, published with the full margin and
ambiguity distributions.

Tie-break among passing configurations: maximise mean byte saving subject to
(ii) and (iii); break a remaining tie toward the smaller `b` and larger `G`.

## 7. Pre-declared failure modes

* If `ρ` (the reference BF16 rounding term) dominates `ε` at the best `b`, then
  **no weight precision helps** and the certified-screen formulation is closed
  for this tensor regardless of the grid. This will be reported explicitly with
  the term decomposition `min(E1,E2) : η : ρ`.
* If margins `c[8] - c[9]` are routinely below `2ε`, `|C|` inflates and the byte
  saving evaporates. That is the NO-GO branch and is a real result.
* Scheme A escape rows (`max|q|` overflow) count as full `1,048,576/256` B rows
  in the byte accounting; they are not silently dropped.

## 8. Measurement protocol

* Data source: a **research-only, not-shipped** dump patch on
  `LagunaRuntimeLayers.swift:2353-2362` writing, per decode call,
  the BF16 `normalized` router input (2048) and the BF16 `router_logits` (256),
  plus a one-time dump of each layer's runtime `routerWeight` and
  `e_score_correction_bias` so the analysis uses the exact runtime tensors and
  not a re-derived checkpoint copy.
* The patch is reverted before any timing.
* Analysis is offline NumPy (`research/frieren_r96b_screen.py`).
* Validation of the pipeline: recomputing `bfloat(Σ x_j w_ij)` in FP64 must
  reproduce the dumped BF16 `router_logits` for >= 99.9 % of entries, and every
  mismatch must be within 1 BF16 ulp. If that check fails, Stage 1 is void and
  the dump is fixed before the bar is applied.

## 9. Stop rule

Stage 1 misses the bar -> submit the terminal negative immediately.
Stage 1 clears the bar -> Stage 2 build under rule 24 (one mechanism), with a
bit-identity proof on `(indices, weights)` for all 39 layers x all decode steps.
Wall clock cap ~6 h or 12 timed sessions.
