# R85-B (rev2) pre-registration — per-file cap relief by source split

Recorded **before** any timing was run. Base `7687c2e44e6975c181444ca8d3d151ee30480a72`.

## Hypothesis

Moving a contiguous region of `Sources/MLXFastModel/LagunaRuntimeModel.swift`
into a new in-surface file `Sources/MLXFastModel/LagunaRuntimeLayers.swift`
dissolves the 524,288 B per-file cap on the scored forward pass, is
byte-conserving on the total surface, and is bit-identical and
performance-neutral.

Null: the split changes emitted code, most plausibly because the
`private` -> `internal` widenings it forces defeat an optimization the
single-file layout was getting.

## Prediction (recorded before measurement)

- **Point prediction: 0 µs/step decode delta.** My prior is that the split is
  neutral, at ~85% confidence.
- **Interval: |Δ decode| < 25 µs/token on this M4 Pro host**, i.e. inside the
  paired run-to-run noise I have already measured on this host (paired
  candidate-minus-baseline decode differences of −5.5, +16.6, +30.5, +75 µs/token
  across four pairs of an unrelated arm, all null by construction).
- Prefill: 0, |Δ| < 0.3%.

Mechanism for the prior: SwiftPM `-c release` compiles the module with
whole-module optimization. Under WMO, `internal` declarations are visible to the
optimizer across every file of the module and are not externally linkable, so
the inliner and specializer see the same call graph as with file-scope
`private`. `private` is a *source-visibility* restriction, not an optimization
barrier, once WMO is on. The residual 15% covers cases where the compiler's
per-file work partitioning or a heuristic keyed on declaration context changes
an inlining decision.

## Honest limit of the timing test on this host

The advisor's failure threshold is "a split that costs 5 µs/step". On the M5
operating point 1 µs/step is 0.0153 % of score. On this M4 Pro host decode is
~12,870 µs/token, so 5 µs/token is 0.039 % — roughly an order of magnitude below
what paired `--local-iterate` timing can resolve. I therefore report:

1. the paired timing interval actually achieved, and
2. a **direct emitted-code comparison** of the two release builds, which
   answers the mechanistic question ("did the split change what the optimizer
   emitted?") at a resolution timing cannot reach.

If the emitted code for the scored module is unchanged apart from symbol
ordering, that is stronger evidence of neutrality than any M4 timing interval,
and the timing interval then serves only to exclude a gross regression.

## Carve

Lines 8693–11279 of `LagunaRuntimeModel.swift` at the base commit, verbatim:

| decl | line at base |
| --- | --- |
| `final class LagunaRuntimeMLP` | 8693 |
| decode router top-8 / ordinal kernels and sources | 9050–9497 |
| prefill router top-8 / tournament kernels and sources | 9514–10065 |
| `final class LagunaRuntimeMoEGate` | 10072 |
| prefill MoE tail, interleaved SwiGLU, fused sorted gate-up | 10206–10382 |
| `final class LagunaRuntimeSparseMoEBlock` | 10476 |
| `final class LagunaRuntimeDecoderLayer` | 10982 |
| decode embedding+RoPE atlas kernel and wrapper | 11195–11279 |

The advisor recommended 8693–11283. I stopped at 11279 because 11281–11283 is
the doc comment belonging to `LagunaRuntimeModelInner` at 11284; carving to
11283 would have orphaned it from its declaration. Line 11280 (the blank
separator) is dropped so exactly one blank line remains at the seam.

## Forced visibility widenings (`private` -> `internal`)

Derived with `research/fern_split_analysis.py`, which resolves every file-scope
`private` declaration against every use site and reports the ones that cross the
carve boundary.

Moved into the new file, used by the old file:

| decl | use sites in `LagunaRuntimeModel.swift` |
| --- | --- |
| `let lagunaDecodeRouterOrdinalHeader` | 3 kernel-source concatenations |
| `func lagunaDecodeEmbeddingRoPEAtlas` | `LagunaRuntimeModelInner` decode path |

Left in the old file, used by the new file:

| decl | use site in `LagunaRuntimeLayers.swift` |
| --- | --- |
| `let lagunaRouterPrecomputedKeysEnabled` | `LagunaRuntimeSparseMoEBlock` |
| `let lagunaTerminalPrefillFusionEnabled` | `LagunaRuntimeDecoderLayer` |
| `let lagunaRoPEAngleAtlasLength` | decode embedding+RoPE atlas wrapper |

Five widenings total. `lagunaRoutedSwiGLUQMVPackedKernel` appeared as a sixth
candidate but its only cross-boundary occurrence is inside a doc comment, so it
stays `private`.

## Stop rule

Report a neutrality verdict with an interval. A measured decode cost outside the
predicted interval, reproduced, ends the arm as a failure and the split is
reverted rather than argued down.
