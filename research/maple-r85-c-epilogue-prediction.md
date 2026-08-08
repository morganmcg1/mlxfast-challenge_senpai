# R85-C (rev2) — pre-registered prediction, float4 merge-epilogue port

Written and committed **before the first timing block**, as required by
`r85-c-fb2` / `r85-c-fb3`.

- Assignment: PR #457, revision `r85-c-rev2`.
- BASE_SHA (build and timing base): `7687c2e44e6975c181444ca8d3d151ee30480a72`.
- Host: AWS M4 Pro, Apple GPU generation 16 (`_nax` prefill kernels unreachable;
  both kernels touched here are decode fused-attention and are reachable).

## Mechanism

Re-lay the cross-simdgroup merge scratch in both decode fused-attention kernels
from plane-major scalars (`threadgroup U outputs[4 * BN * BDP]`, `pair_planes = 2`)
to component-major `float4` (`threadgroup float4 outputs4[BN * BDP]`).

Per lane, per kernel invocation:

| | threadgroup stores | threadgroup loads | barriers |
|---|---|---|---|
| base (plane-major SoA) | 8 (4 per round × 2 rounds) | 8 (4 per round × 2 rounds) | 3 |
| candidate (component-major AoS) | 2 (1 vector store per round) | 2 (1 vector load per round) | 3 |

Threadgroup footprint is unchanged: `BN * BDP * sizeof(float4)`
= `32 * 33 * 16` = **16,896 B**, exactly equal to
`4 * BN * BDP * sizeof(float)` = `4 * 32 * 33 * 4` = **16,896 B**.
No plane added, `pair_planes` removed rather than raised, so the 32,768 B
threadgroup wall recorded in `research/CURRENT_RESEARCH_STATE.md` §8 is not
approached.

## Prediction (pre-registered)

Both kernels ported, so the full #205 pair effect is predicted:

- **Point prediction: +18.6 µs/step decode** (faster), i.e. decode µs/step
  delta of **−18.6**.
- Interval carried from #205's in-situ measurement on the pre-frontier tree:
  **+18.58 ± 2.92 µs/step (1 s.e.), t = 6.37, 12/12 paired blocks positive**.
  Pre-registered 95 % interval: **+12.9 to +24.3 µs/step**.
- Score conversion at the standing 0.015280 %/µs-step: **≈ +0.284 % score**
  (95 % interval ≈ +0.197 % to +0.371 %).
- Prefill: no prediction of a gain. These are decode kernels; prefill should be
  unchanged within noise, and must not regress past the 0.95 floor.
- Bit-identity: `max_abs_diff` must be exactly **0**. Each `simd_sum` consumes
  the same 32 products in the same lane order, because the store index
  (`lane * BDP + sg`) and the transposed load index (`sg * BDP + lane`) are
  unchanged and the plane subscript `p` becomes the vector component.

## Pre-registered interpretation rules

- **At or near +18.6 µs/step** → clean replication of #205; the frontier's
  plane-major rewrite genuinely costs what we measured before.
- **Materially short of +18.6 but positive** → the frontier tree recovers part
  of the same benefit elsewhere (its surrounding kernel body differs from our
  pre-frontier tree even though the epilogue text does not); report as partial
  replication, not as a dead mechanism.
- **Null (inside the noise floor)** → real finding: on this hardware the
  plane-major SoA form is performance-equivalent to the AoS `float4` form, which
  retires a 0.284 % ghost. Report as such.
- **Negative** → report the regression and stop; do not iterate on variants.

## Noise floor this must clear

From `research/maple-r85-noise-floor.md` (this host, this harness):

- Single-run-vs-single-run wall-clock decode: **±133 µs/step** — far too coarse
  to see 18.6 µs/step, so single shots are not admissible evidence.
- Ratio-adjusted paired A/B/B/A blocks: **±5.1 µs/step at n = 8**. This is the
  instrument that can resolve the prediction; 18.6 µs/step is ≈ 3.6× that
  half-width.
- Per-kernel GPU-time attribution: **±0.3–2.0 µs/step** per kernel.

So the decision instrument is paired A/B/B/A blocks with ratio adjustment, plus
per-kernel attribution on the two touched kernels for mechanism confirmation.

## Structural finding recorded before measuring

The advisor's brief expected a **hand port** because "the frontier rewrote this
exact region". It did not. `git show 1aad492f -- Sources/MLXFastModel/LagunaRuntimeModel.swift`
applies to `7687c2e4` **cleanly**, with pure line offsets (+47) and zero
conflicts:

```
Hunk #1 succeeded at 1510 (offset 47 lines).
Hunk #2 succeeded at 1637 (offset 47 lines).
Hunk #3 succeeded at 1656 (offset 47 lines).
Hunk #4 succeeded at 1950 (offset 47 lines).
Hunk #5 succeeded at 2121 (offset 47 lines).
Hunk #6 succeeded at 2140 (offset 47 lines).
```

The frontier's epilogue is **textually identical to our pre-#205 code**, so the
organizer frontier did not author a competing SoA design — our #205 was simply
dropped when the frontier replaced the file. That strengthens the replication
prediction: there is no "frontier already recovers part of it" mechanism inside
the epilogue itself.

## Surface accounting

- Byte delta: **−454 B** (`511,418` → `510,964` on
  `Sources/MLXFastModel/LagunaRuntimeModel.swift`).
- `senpai/validate-assignment-scope.sh 7687c2e4… Sources/MLXFastModel/LagunaRuntimeModel.swift`
  → `assignment scope OK: 1 submitted path(s)`.
- `senpai/check-editable-budget.sh 7687c2e4…` →
  `current=2890889/3000000 headroom=109111 growth=-454/262144 files=140`.
