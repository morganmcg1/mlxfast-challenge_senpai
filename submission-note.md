# Gate-softplus dot4 vectorization + packed simd_sum

## Model and Effort Level

- **Model**: senpai
- **Coding agent**: OpenHands (Senpai autonomous research harness)
- **Campaign**: birch (fresh independent research campaign)
- **Experiment**: alphonse-gate-softplus-dot4-v1 (PR #130)

## Hypothesis

The gate-softplus kernel (`lagunaGateSoftplusSource`) computes the per-head
softplus gate for attention output projection on all 39 attention layers per
decode step. Its inner loop uses V=8 scalar FMAs per row per block. Can this
be vectorized to `dot(float4, float4)` for the same 75% instruction reduction
proven in PRs #107, #114, and #119?

## Change

Replaced 8 scalar FMAs with 2 `dot(float4, float4)` + 1 addition in the
gate-softplus inner accumulation loop. Additionally replaced 4 scalar
`simd_sum` calls with 1 packed `simd_sum(vec<float,4>)` for the cross-lane
reduction.

Both changes are bit-exact by construction: `dot(float4, float4)` on Apple
Silicon uses the same sequential FMA rounding as scalar multiply-accumulate,
and `simd_sum(vec<float,4>)` performs the same cross-lane reduction as 4
scalar calls.

## Environment

- **Host**: AWS Mac M4 Pro (local validation; M5 Max for official scoring)
- **GPU generation**: 16 (M4 Pro). M5 Max selects `_nax` prefill kernels.
- **Thermal policy**: 40C thermal gate enforced by benchmark harness
- **Base**: bb523807d3f70757d7cbae4b4b24ecfe5981a43d (ORGANIZER_FRONTIER=bca94c5)

## Submitted candidate files

- Sources/MLXFastModel/LagunaRuntimeModel.swift

## Validation

- **--local-iterate**: max_abs_diff=0, passed_correctness=true, golden hash
  unchanged (b9509697...). 130 checked steps, 40 layers.
- **--local-submit**: passed=true, score=1.0127, max_abs_diff=0. Decode
  speedup 1.483x (calibration), 1025 checked steps.
- **Upstream equivalence**: All 8 decode steps bit-exact (0.0 error).
  Prefill logit error 0.125 is pre-existing (identical on baseline commit
  318fb5a), not caused by this change.

## Measured Results (M4 Pro, directional)

| Metric | Baseline (f26a8cd) | Candidate (cbb5f62) | Paired ratio |
| --- | ---: | ---: | ---: |
| decode seconds/token | 0.013355 | 0.013166 | 1.014x |
| prefill seconds/token | 0.001140 | 0.001127 | 1.011x |
| same-host paired estimate | — | — | 1.0136 |

Both paired speedups exceed the 0.95 floor. The calibration-based
prefill_speedup field (0.326) is a known M4 artifact — M4 prefill is 3x
slower than the pinned M5 calibration. The paired same-host comparison shows
prefill is actually slightly faster (1.011x), as expected since the
gate-softplus kernel runs only during decode.

## Caveats

- M4 Pro is bandwidth-bound; M5 is instruction-bound at ~89%. M4 results are
  directional. The instruction-count reduction (8 FMAs -> 2 dot4s, 4 simd_sum
  -> 1 packed) is expected to show a larger effect on the M5.
- The paired M4 gain is small (+1.4% decode) but positive. M5 is needed for
  the definitive verdict.
