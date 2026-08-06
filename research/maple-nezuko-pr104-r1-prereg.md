# PR #104 r1 pre-registration — shared-expert scale-plane halving

Assignment `maple-2026-08-06j-shared-scale-plane-halving`, revision `r1`,
student `maple-nezuko`, base `dec0a83c075d151ef5dec94f4005bd39ff2c2d69`.

Written before any timing was taken. Protocol item 5 of the assignment
requires a pre-registration; this file is it.

## Preflight, quoted

```text
editable budget OK: current=2934331/3000000 bytes headroom=65669 growth=0/262144 files=142 (base=142)
assignment scope OK: 3 submitted path(s) against BASE_SHA=dec0a83c075d151ef5dec94f4005bd39ff2c2d69
```

Submitted surface, as scoped:

- `Sources/MLXFastModel/LagunaRuntimeWeights.swift`
- `Sources/MLXFastModel/LagunaRuntimeModel.swift`
- `Sources/MLXFastTransform/LagunaTransform.swift`

## Region fence

Four students share `LagunaRuntimeModel.swift` on this base. I own
`_routedDownScales` (~:9855), the routed-down halving call site (~:9956), and
in `LagunaRuntimeWeights.swift` the `lagunaHalvedGroup32ScalePlane` helper
(~:1014) with its header/size constants (~:975) and the routed gate/up call
site (~:1052). PR #101 owns `gate_sp` (~:4275) and the o_proj lane-major scale
reads (~:4135). PR #103 owns the two fused-attention kernel strings (~:1370,
~:1819) and their dispatch sites (~:1761, ~:2263). I touch none of theirs.

## Deliverable 1 — Arm A, shared-expert scale-plane halving

**Pre-registered stop rule, taken verbatim from the assignment**: *"If the true
figure is materially below 7.67 MB/step, say so and stop — a 3 MB/step arm is
not worth the headroom."*

Predicted effect, to be committed to before measuring: the removal is half the
plane, so the arm is worth `removed_bytes / achieved_rate × 14.862 %/ms`, with
the achieved rate taken from the kernel family that actually reads the bytes.
Threshold for a GO: the predicted score delta must clear the advisor's 0.61 %
acceptance bar with the 1.0–1.2× realisation band applied, and must clear the
programme's standing §0.5.8 admissibility floor of ≥23.3 MB/step removed at
546.2 GB/s.

Predicted decision if the removal is 3.83 MB/step: NO-GO, no GPU time, because
that is 6.1× below §0.5.8 and 5.9× below the acceptance bar. Recorded here
before the byte census was priced so the decision cannot be back-fitted.

Measurement plan had the arm been a GO: `./benchmark.sh --local-iterate`, three
matched baseline/candidate pairs on the same quiet host behind the 40C gate,
`research/run_upstream_equivalence.sh` with a nonzero selected-test count, and
`golden_hash` equality rather than `max_abs_diff` as the correctness evidence.

## Deliverable 0 — `ae9ac90b` re-audit

Question as assigned: is the `ae9ac90b` observed/predicted ratio of 1.47×
explained by (a) a bundled instruction/occupancy change, (b) a byte census that
under-counted, or (c) a real byte channel that can deliver both 0.59× and
1.47× — which would falsify the single-band model in §0.9.36.

Pre-registered discriminators, fixed before the arithmetic was run:

1. (b) is refuted if an independent first-principles byte census reproduces the
   claimed removal to within the precision of the original claim, or shows the
   original **over**-counted.
2. (a) is refuted if every identified instruction-channel hunk is a cost rather
   than a benefit, since a net-cost bundle cannot inflate an observed win.
3. (c) is *supported* only if, after (a) and (b) are refuted, the ratio remains
   outside the 1.0–1.2× band **under a denominator that is the achieved rate of
   the kernel that reads those bytes on the host where the measurement was
   taken**. If the ratio re-enters the band under any corpus-sanctioned
   denominator, the finding is inconclusive and the single-band model survives.

No GPU is required for this deliverable; it is settled by counting against the
`ae9ac90b` receipt note in `research/nezuko-corpus-1253.json` and the live
kernel sources.
