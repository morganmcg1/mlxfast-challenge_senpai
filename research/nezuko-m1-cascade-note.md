# LM-head three-level decode screen (M1 cascade) — submission note

Student `maple-nezuko`, campaign `mlxfast-maple-20260804`, PR #20,
assignment `maple-2026-08-04d-lmhead-cascade`.

This archive contains exactly two independent changes on top of the promoted
frontier: a **deletion** of two previously-harvested mechanisms that measured
individually inert, and a **port of one mechanism (M1) from public submission
`ae9ac90b`** (solver `ivanfioravanti`, model `Kimi K3`). Mechanisms M2–M5 of
that submission are deliberately **not** included; this archive isolates M1 so
that its effect can be priced on its own.

---

## 1. What the decode LM-head did before this change

The scored decode path does not run a dense BF16 GEMV over the 100352-row
output embedding. It runs a *certified screen*: a cheap approximate pass
computes a coarse dot product together with a rigorous error bound, and only
the rows whose coarse upper bound can still reach the running maximum are
recomputed with a bit-exact BF16 GEMV. Non-candidate slots keep their coarse
BF16 value, which the certificate proves is strictly below the winner, so the
argmax the harness takes is the stock argmax.

The approximate pass reads an INT5 copy of the weight matrix, stored as two
planes plus per-group BF16 scales:

| plane | bytes/row | contents |
|---|---|---|
| nibble plane | 1024 | 4 bits per weight |
| bit plane | 256 | 1 bit per weight |
| scales | 64 | per-group BF16 |
| **total** | **1344** | |

Over 100352 rows that is **134.88 MB per decode step**, and it was measured on
this campaign's M4 Pro host at **510.9 µs/call, 264.0 GB/s** — i.e. 101% of the
260.2 GB/s measured read ceiling. It is the single largest byte stream in the
decode step and it is already bandwidth-saturated, so the only way to make it
faster is to **make it read fewer bytes**.

## 2. What M1 changes

M1 splits the single approximate pass into two levels, so that the common case
never touches the bit plane at all.

The INT5 code `q ∈ [0,31]` (offset binary `u = q + 16`) is re-split so that the
nibble plane alone is a **self-contained 2×-coarse code**:

```
nibble plane  H = floor(u / 2) = floor(q/2) + 8      (was: high 4 bits)
bit plane     b = u - 2*floor(u/2) = u & 1           (was: bit 4)
```

* **Level 1** reads the nibble plane and scales only — **1088 B/row**. It
  decodes the cell midpoint `q0 = 2H - 15.5`, for which `|q - q0| = 0.5`
  exactly. Its per-element uncertainty is therefore the INT5 quantisation
  residual (`0.5·sd`) **plus** the cell uncertainty (`0.5·sd`), i.e. a
  coefficient of `1.0·sd`, which is what the kernel accumulates
  (`d_acc += sd * ag`).
* **Level 2** screens on that wider interval and, **for surviving rows only**,
  reads the 256 B bit plane and applies the correction `sd·(b - 0.5)` per
  element. That recovers `q` exactly, so the remaining uncertainty falls back
  to the quantisation residual alone — half the level-1 bound.
* **Level 3** is the unchanged bit-exact BF16 GEMV over the refined survivors.

Level 1's read drops from 1344 B/row to 1088 B/row:

```
100352 rows x 256 B = 25.69 MB removed per decode step
134.88 MB  ->  109.18 MB
```

Prefill is unchanged: it keeps the original single-pass kernel, because there
the screen is amortised over many rows and the extra level buys nothing.
Refinement is applied only when the input is a single decode token.

## 3. The refinement certificate

The level-2 certificate constant was **re-derived here rather than copied**.
With the codebase's `GAMMA = 0x1p-15f`:

* Level 1 stores `delta = d_acc·(1 + 32·GAMMA)`, where the post-refinement
  exact-arithmetic residual is `d = d_acc/2`.
* After refinement the accumulated magnitude obeys `m ≤ 32·d`, so the
  certificate must dominate `d·(1 + GAMMA) + 2·GAMMA·m = d·(1 + 65·GAMMA)`.
* Hence the required multiplier is
  `k ≥ (1 + 65·GAMMA) / (2·(1 + 32·GAMMA)) ≈ 0.5·(1 + 33·GAMMA)`.

The source submission uses `0x1.004p-1f = 0.5·(1 + 32·GAMMA)`, which is short
of that requirement by about one `GAMMA`. This archive uses
**`0x1.005p-1f = 0.5·(1 + 40·GAMMA)`**, which carries 7·GAMMA of margin and is
therefore **strictly more conservative than the source**: a larger multiplier
widens the interval and can only admit *more* rows into the exact pass, never
fewer. The multiply is exact in FP32 (an 8-bit BF16 significand times a 13-bit
constant needs 21 bits), and the result is rounded **up** to BF16 regardless.

Both new kernels are named `_v1` and the reworked single-pass kernel is renamed
`_v5` → `_v6`, because MLX caches JIT kernels by name and the plane semantics
changed. Shipping the new packing under an old kernel name would silently reuse
a stale binary.

## 4. Correctness evidence

* **Harness gate, 8 independent `--local-iterate` runs** (4 with the cascade
  active, 4 with it disabled in the same binary): `max_abs_diff = 0`,
  `passed_correctness = true`, `checked_steps = 130`, identical `golden_hash`
  and `weights_hash` in every run.
* **Plane round-trip**: the packing convention was verified line-by-line
  between the producer (`buildInt5Planes`) and all three consumer kernels.
  Producer stores element `2b` in the low nibble and `2b+1` in the high nibble;
  bit plane stores element `j` of each 32-element group in bit `j` of the
  group's little-endian word. All three kernels decode with exactly that
  convention.
* **Decode algebra**, checked symbolically:
  * level 1 `float4(ne << 1u) - 15.5f` → `2H - 15.5`, exact midpoint;
  * level 2 `(2H - 15.5) + (b - 0.5)` → `2H + b - 16 = q`, exact;
  * single-pass `float4((ne << 1u) | he) - 16.0f` → `u - 16 = q`, exact
    (the `<<1` leaves bit 0 free, so the OR is an add).
  All three are exact in FP32: `u ≤ 31` and the offsets need ≤ 6 significand
  bits.
* **Self-validating property**: a transposition bug in the re-split would
  inflate `delta`, which would push *more* rows into the exact GEMV. That
  shows up as lost speed, not as a wrong token — so the measured speedup is
  itself evidence that the repacking is correct.

## 5. Byte-budget arithmetic

This arm is a pure byte-removal change, which is the one class of local
measurement that transfers between hosts: the decode step is a fixed byte
budget, so removing `dB` bytes costs the same *fraction* of the pure decode
step `T` on either generation.

One refinement to that identity matters here. Bytes must be priced at the
**bandwidth of the kernel they are removed from**, not at the step average.
The level-1 pass runs at 264.0 GB/s, well above the ~205 GB/s step average, so:

```
25.69 MB / 264.0 GB/s = 97.3 us   ->  -1.11% of T   (kernel rate)
25.69 MB / 204.6 GB/s = 125.6 us  ->  -1.43% of T   (step-average rate)
```

The local A/B discriminates between these two predictions. Report `T`
separately from the composite, since the 512-token seed prefill folds into
`decode_seconds_per_token` at a much larger share on M4 than on the ranked box:

```
S = 512000 * prefill_seconds_per_token       (ms)
T = 1000 * decode_seconds_per_token - S/128  (ms)
```

## 6. Also in this archive: two deletions

Two mechanisms harvested earlier in this campaign measured individually inert
and are **reverted** here, as plain deletions with no flag left behind:

* `9c1ad1c` — `MLX_MAX_OPS_PER_BUFFER` 200 → 400.
* `6ca0c71` — NAX `fp_qmm_t` barrier elision (`fixed_K == 0` guards).

Their isolated public receipts put them at roughly +0.03% and +0.07% of score,
both far inside the noise floor of a three-receipt family, so reverting them
costs nothing measurable and removes two mechanisms that would otherwise have
to be carried and re-justified forever.

## 7. Scope

No harness, scoring, workflow, test, or fixture file is modified. No prompt,
token, or answer is hardcoded; nothing is keyed on input tokens. The change is
input-independent weight repacking plus a kernel screen, which the serial
non-speculative track rules allow: each invocation still computes logits and KV
rows only for the tokens supplied in that invocation and advances position by
exactly the supplied input length.
