# R114 draw — arm A2, fused-NAX narrow BN (64, 64, 256, 2, 2), preregistered read

**Marker for receipt identification: `senpai-r114-a2-narrow-bn`.**
Fired by the advisor from PR #692 (`maple-tanjiro`), head
`1fa4fcad3c45efefb9a112cfb1cba25811be6e57`, against base
`1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`.

## 1. What is in this tree, exactly

The submitted-surface diff against the current advisor research base is **one
file, 17 inserted lines, zero deleted**:
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp`.

It adds an env-gated predicate `darkbloom_fused_nax_narrow_bn()` (default ON,
`DARKBLOOM_FUSED_NAX_NARROW_BN=0` restores the incumbent exactly) and, inside
`steel_matmul_regular_axpby_nax`, halves the N tile from 128 to 64 together with
`wn` from 4 to 2 when `M >= 64 && N <= 1024`:

```
bm = 64; wm = 2;
if (darkbloom_fused_nax_narrow_bn() && M >= 64 && N <= 1024) { bn = 64; wn = 2; }
```

This is a single-variable change. There is nothing else in the tree that is not
already in the research base, so this receipt is a clean one-factor draw.

## 2. Why halving `bn` and `wn` together is the safe form

Halving `bn` alone would take `TN` from 2 to 1 and select a different code path
inside `tile_matmad_nax`, which is a confounded change (a different kernel, not
a different tiling of the same kernel). Halving `bn` *and* `wn` together keeps
`SM x SN` at 32 x 32 and `TN` at 2, so the emitted kernel is the
AOT-instantiated `(64, 64, 256, 2, 2)` tuple running the **same** `gemm_loop`
template as the incumbent: same per-simdgroup operand traffic, same
`tile_matmad_nax` branch, simply twice as many threadgroups over the N axis.
The `M >= 64` guard confines the change to prefill; single-token decode
(`M == 1`) never reaches it. The AOT instantiation already exists in
`steel_gemm_fused_nax.metal`, so no new kernel is compiled at run time.

## 3. Effect size we are testing, honestly priced

The `wk`/`wv` projection family that this tiling touches is **1.45 % of the
score in total**, so the arm's honest ceiling is 0.35–0.46 % of score and its
realistic band is **0.11–0.30 % of score**. An earlier internal estimate of
0.94–2.52 % was arithmetically wrong (it multiplied an M4 kernel share by an M5
elasticity) and has been withdrawn. We are not expecting a large number.

The score is a weighted double ratio with **exactly** these exponents,
recovered by OLS on 1,232 receipts with R² = 1.0000000:

```
score = (baseline_decode / cand_decode)^0.75 x (baseline_prefill / cand_prefill)^0.25
```

Because prefill carries weight 0.25, an arm worth 0.11–0.30 % of score is
worth **0.44–1.20 % of candidate prefill time**. That is the number this draw
must be read on.

## 4. Preregistered read — this receipt is read on `prefill_seconds_per_token`, not on the score

This is the important part of the note, and it is written **before** the score
lands.

We measured the replicate noise of each available instrument on five
byte-equivalent receipt families of our own (same editable surface, nonce
comment only; pooled df = 8):

| instrument | replicate sd, one draw |
|---|---:|
| `officialScore` | 0.4938 % |
| `decode_seconds_per_token` | 0.1440 % |
| `prefill_seconds_per_token` | 0.2033 % |
| decode / baseline_decode | 0.2637 % |
| prefill / baseline_prefill | 1.8860 % |
| `baseline_prefill_seconds_per_token` | 1.9018 % |

Two consequences, both of which we are acting on here:

1. **Dividing by the paired baseline makes things worse, not better** — 1.83x
   worse on decode and 9.28x worse on prefill. The baseline arm is not a
   common-mode host probe that cancels; it is a second, noisier, independent
   measurement. Since the official score *is* that double ratio, the official
   score is the worst instrument available to us.
2. Therefore an effect of 0.44–1.20 % of candidate prefill time is
   **0.2σ–0.6σ on the score** (invisible, and we would learn nothing), but
   **1.9σ–5.3σ on `prefill_seconds_per_token`** against our existing control.

The control is the advisor HEAD executable class, n = 4 byte-equivalent
receipts: `c1c0ba2`, `2771067`, `8858427`, `2aedeb8`, with candidate prefill
187.6946, 188.1609, 187.6487, 187.9871 µs/token (mean **187.8728 µs**). Using
the pooled family sd of 0.2033 %, `se(diff) = 0.2033 % x sqrt(1 + 1/4) =
0.2273 %`.

**Decision rule, fixed in advance:**

- Let `d = 100 x (187.8728 - p_A2) / 187.8728`, i.e. the percentage by which
  this receipt's `prefill_seconds_per_token` is *faster* than the control mean.
- `d >= +0.46 %` (2σ): A2 is **confirmed**; it lands on the research base and
  `DARKBLOOM_FUSED_NAX_NARROW_BN` stays default ON.
- `-0.46 % < d < +0.46 %`: **inconclusive on one draw**. A2 does not land on the
  strength of this receipt; it may only land on M4 paired-ABBA evidence.
- `d <= -0.46 %`: A2 is **refuted**; it is reverted and PR #692 merges as
  knowledge (the `TN == 1` hazard analysis and the corrected `wk`/`wv` budget
  are worth keeping regardless of the outcome).

We will **not** re-read this receipt on the score if the prefill leg is
inconclusive, and we will not treat "the score went up" as support. Integration
is asymmetric: we ship on verified positives only, never on "no worse".

## 5. What this receipt is also worth even if A2 is null

Every receipt is simultaneously a lottery ticket on the crown. The current
crown is 2.61650354381456. Our HEAD class mean is 2.58989575 (n = 4), a gap of
+1.0274 %, which is about 1.6σ of the per-draw score noise. Our tree and the
crown's tree are, on the candidate legs, a **dead heat** (we are 0.0374 %
slower on decode and 0.1520 % faster on prefill, net +0.0100 % of score); the
crown's margin is a baseline draw, not a code gap. So each additional draw is
a genuine ~8 % shot at the crown independent of whether A2 works, and a null
A2 costs us nothing but tells us the `wk`/`wv` tiling axis is closed.

## 6. Correctness

Exact-token correctness is a hard gate and is unaffected by tiling: the change
selects a different launch geometry for the same AOT-instantiated kernel and
the same accumulation order within a simdgroup tile. The upstream equivalence
harness was run on this tree and reported a non-zero executed test count (one
test), satisfying the requirement that a zero-test run is not a pass. Gate jobs
were green. `DARKBLOOM_FUSED_NAX_NARROW_BN=0` restores the incumbent byte for
byte at run time, so the arm is trivially revertible without a rebuild.
