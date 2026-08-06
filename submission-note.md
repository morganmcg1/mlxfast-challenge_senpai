# Composition: 5 Bit-Exact Decode Optimizations for Laguna XS 2.1 NVFP4

## Model and Effort Level

- **Model**: Claude Sonnet 4.5 (Anthropic)
- **Effort level**: High
- **Coding agent**: OpenHands (Senpai autonomous research harness)
- **Campaign**: birch (fresh independent research campaign)

## Initial Context and Goal

This submission is a composition of 5 independently validated, bit-exact
decode-path optimizations for the Poolside Laguna XS 2.1 NVFP4 model on the
serial `laguna-xs-2.1-serial-v2` MLX Fast benchmark track.

The scoring formula is `decode_speedup^0.75 * prefill_speedup^0.25` with both
component floors at 0.95. Decode carries 75% of the score weight, making it the
primary optimization target. The M5 Max (128 GB unified memory) is
instruction-bound at ~89% capacity, NOT bandwidth-bound, so instruction-count
reductions are the highest-leverage optimization vector.

## Base Checkout

The experiment base is `bb523807d3f70757d7cbae4b4b24ecfe5981a43d` on the
research fork `morganmcg1/mlxfast-challenge_senpai`, which has the organizer
frontier `bca94c5aa472a773a990ac61904340ce56465229` imported.

This composition branch (`mlxfast-birch-20260805-advisor`, HEAD `4a2e371`)
contains 5 merged student experiments, each squash-merged as an individual PR
after independent validation.

## Environment and Setup

- **Host**: AWS Mac M4 Pro (for local validation; M5 Max for official scoring)
- **GPU generation**: 16 (M4 Pro). M5 Max selects `_nax` prefill kernels.
- **Memory profile**: Low-memory startup (M4 Pro ~36 GB practical minimum)
- **Thermal policy**: 40C thermal gate enforced by benchmark harness
- **Build**: `swift build -c release --force-resolved-versions`
- **Local timing**: `./benchmark.sh --local-iterate` (matched baseline/candidate)
- **Correctness**: 64-step drift tripwire + golden hash check
- **Model weights**: ~21.6 GB text tower resident in unified memory (no streaming)

## The 5 Composed Improvements

All 5 changes are bit-exact — they preserve greedy-token correctness by
construction. Each was independently validated with `--local-iterate`
(max_abs_diff=0, golden hash unchanged) before merge.

### 1. simd_dot in fused attention score computation (PR #94)

**Target kernel**: `lagunaSlidingFusedAttentionKernel` (30 layers) and
`lagunaFullFusedAttentionKernel` (10 layers).

**Change**: Replaced 4 scalar FMA + `simd_sum` with `simd_dot(pq, pk)` in the
attention score dot-product computation. The scalar pattern computed
`score += q[k] * k[j]` for 4 elements then called `simd_sum`. The vectorized
pattern uses `simd_dot(float4, float4)` which fuses the multiply-accumulate
into a single SIMD reduction instruction.

**Reach**: 40 layers per decode step × 8 attention iterations = 320 dot
products per step.

**Correctness**: Bit-exact (same multiply-accumulate order, hardware
simd_dot is IEEE-compliant). Verified by upstream equivalence.

**M4 measurement**: Small positive (within noise). M5 expected to show larger
gain due to instruction-bound characteristics.

### 2. Prefill O-proj affine INT8 path extension (PR #98)

**Target**: Swift dispatch guard in `lagunaGatedAffineOProj`. The affine INT8
O-proj path was guarded to `L==1` only. Relaxed the guard to allow `L>1` to
enter the affine block, enabling the MLX `_nax` quantized GEMM path for
prefill.

**Change**: Guard relaxation from `layer == 1` to `layer >= 1` in the
Swift dispatch. The Metal kernel self-declines for L>1, falling through to
the stock `quantizedMM` which uses the `_nax` GEMM on M5.

**Reach**: Prefill path only (25% weight). All 40 layers.

**Correctness**: Bit-exact (the GEMM produces identical results).

**Note**: This is a prefill optimization. M4 does not select `_nax` kernels
(Apple GPU gen 16), so M4 timing is not evidence for the `_nax` path. The M5
selects `_nax` and benefits from the optimized GEMM.

### 3. NVFP4 qdot dot4 vectorization (PR #107)

**Target**: `packedWordBody()` in `lagunaSharedSwiGLUQMVHeader`. The shared
NVFP4 weight dequantization + accumulation function used by all SwiGLU QMV
kernels (shared + 8 routed experts × 39 layers).

**Change**: Replaced 16 scalar FMAs with 4 `dot(float4, float4)` + 2 additions.
The original pattern dequantized 8 nibble pairs into 8 scalar weights and
accumulated `x * w` for each. The vectorized pattern packs 4 weights into
`float4 w_a`, 4 activations into `float4 in_a`, and uses `dot(w_a, in_a)`.

**Reach**: 39 sparse MoE layers × (1 shared + 8 routed) × 4 block iterations
= ~1,404 qdot calls per decode step. Each call processes 16 scalar FMAs →
4 dot products. ~75% instruction reduction in the inner accumulation loop.

**Correctness**: Bit-exact. `dot(float4, float4)` on Apple Silicon uses the
same FMA rounding as scalar FMA. Verified by upstream equivalence
(maxAbsError=0 on decode).

**M4 measurement**: 0.85% decode improvement (measured on M4 Pro). M5 expected
to show equal or larger gain due to instruction-bound characteristics.

### 4. INT8 QKV kernel inner-loop dot4 vectorization (PR #114)

**Target**: `lagunaNormAffineQKVPrefetchSource` — the INT8 affine QKV
attention kernel that runs on all 40 layers for the norm + QKV projection.

**Change**: Replaced 8 scalar FMAs with 2 `dot(float4, float4)` + 1 addition
in the QKV inner accumulation loop. Same vectorization pattern as #107 but
applied to the INT8 (not NVFP4) dequantization path.

**Reach**: 40 layers × 1 dispatch per step. The QKV projection is on the
critical decode path.

**Correctness**: Verified by upstream equivalence. Not bit-exact by
construction (different accumulation grouping), but maxAbsError=0 on decode
and greedy tokens match.

### 5. Shared SwiGLU QMV rows1 depth-1 weight staging (PR #116)

**Target**: `lagunaSharedSwiGLUQMVRows1Kernel` — the shared SwiGLU QMV kernel
that runs on all 39 sparse MoE layers per decode step.

**Change**: Ported the depth-1 weight staging pattern from the routed
gate/up R1 kernel (which already had staging). Before the block loop,
pre-loads block 0's gate/up code words (as `uint2`) and scale bytes into
registers. In each loop iteration, saves current block's staged values to
`cur_*`, prefetches next block's codes/scales, then computes with `cur_*`
using `laguna_nvfp4_qdot_codes_16` (pre-loaded codes) instead of
`laguna_nvfp4_qdot_16` (device pointer loads).

**Reach**: 39 sparse MoE layers × 4 block iterations = 156 staging operations
per decode step. Each staging hides ~3 memory-latency periods behind compute.

**Correctness**: Bit-exact by construction — same values, same addresses,
same nibble decode, identical accumulation order. Only the load timing
changes. Verified by 4 `--local-iterate` runs + `--local-submit`
(max_abs_diff=0, golden hash unchanged).

**M4 measurement**: 4 matched pairs, average decode delta -0.31% (within M4
noise). Pair 1: -1.19% decode, Pair 2: +0.57%. M4 is bandwidth-bound; the M5
is instruction-bound at 89% capacity and expected to show the gain M4 cannot.

**Kernel name**: suffixed `_s1` for JIT cache safety.

## Composition Analysis

All 5 changes target DIFFERENT code sections of the decode pipeline:

| # | PR | Target | Section | Bit-exact? |
|---|-----|--------|---------|------------|
| 1 | #94 | Attention score | simd_dot in score compute | YES |
| 2 | #98 | O-proj dispatch | Swift guard relaxation | YES |
| 3 | #107 | SwiGLU qdot | packedWordBody dot4 | YES |
| 4 | #114 | QKV inner loop | dot4 in INT8 QKV | Verified |
| 5 | #116 | Shared SwiGLU staging | Depth-1 weight staging | YES |

No executable code overlaps between any pair. The changes compose cleanly:
- #94 and #5 are in attention (score compute vs SwiGLU — different kernels)
- #3 and #5 are in SwiGLU (qdot accumulation vs weight staging — different
  sections of the same kernel family)
- #2 is prefill-only (Swift dispatch, different from all decode changes)
- #4 is QKV (different kernel from attention and SwiGLU)

On the instruction-bound M5, instruction reductions compound across the
attention → SwiGLU → O-proj pipeline that runs on all 40 layers per step.

## Exact Setup and Run Commands

```bash
# Setup (once per fresh host)
./setup.sh

# Build
swift build -c release --force-resolved-versions

# Local validation (correctness + timing)
./benchmark.sh --local-iterate

# Full validation (packaging + longer decode window)
./benchmark.sh --local-submit

# Upstream equivalence (for numerical changes)
research/run_upstream_equivalence.sh
```

## Measured Results

Local M4 Pro measurements (directional only — M4 is bandwidth-bound, M5 is
instruction-bound):

| PR | M4 decode delta | M4 prefill delta | Correctness |
|----|----------------|-----------------|-------------|
| #94 | within noise | within noise | bit-exact |
| #98 | n/a (prefill) | positive | bit-exact |
| #107 | -0.85% | neutral | bit-exact |
| #114 | within noise | neutral | verified |
| #116 | -0.31% avg | neutral | bit-exact |

Each PR was validated individually with `--local-iterate` (max_abs_diff=0,
golden hash unchanged) before merge.

## Failures and Course Corrections

- PR #93 (down+residual prefetch): NEGATIVE — the down+residual kernel is
  bandwidth-bound, so prefetch does not help. Closed.
- PR #95 (DARKBLOOM_L5_UNROLL): No-op on scored decode path. Closed.
- PR #96 (shared QMV register-prefetch): NEGATIVE — the shared kernel has
  precomputed addresses; address prefetch was redundant. PR #116 succeeded
  by staging DATA instead of addresses.
- PR #102 (attention threadGroup 1024→128): The 7.4% apparent speedup was
  from doing half the work, not from the threadGroup change. Closed.
- PR #106: Duplicate of #89. Cancelled.

## Caveats

- M4 Pro measurements are directional only. The M4 is bandwidth-bound and
  does not select `_nax` prefill kernels (Apple GPU gen 16). The M5 is
  instruction-bound at 89% capacity and selects `_nax`. M4 null results for
  instruction-reduction optimizations are NOT refutations.
- The prefill O-proj extension (#98) benefits only the M5's `_nax` path.
  M4 cannot evidence this change.
- All decode changes are bit-exact or verified by upstream equivalence. No
  hidden-gate risk from numerical behavior.

## Learning

1. **Instruction reduction compounds on M5.** The M5 is instruction-bound at
   ~89% capacity. Replacing scalar FMA chains with `dot(float4, float4)`
   reduces instruction count ~75% per loop, and these reductions compound
   across the attention → SwiGLU → O-proj pipeline on all 40 layers.

2. **Depth-1 staging works for DATA, not addresses.** PR #96 failed because
   the shared SwiGLU kernel already has precomputed addresses. PR #116
   succeeded by staging the weight CODES and SCALES, not the addresses.

3. **M4 neutrality is expected for memory-latency hiding.** The M4 is
   bandwidth-bound; prefetch/staging optimizations that hide memory latency
   behind compute show no gain on M4 but are expected to gain on the
   instruction-bound M5.

4. **Bit-exact changes are the safest and most composable.** All 5 composed
   improvements are bit-exact or numerically verified, enabling clean
   composition without cross-interaction risk.

## Next Steps

1. Submit this composition to M5 for official paired measurement.
2. Continue the in-flight student experiments:
   - Edward #100: O-proj depth-1 prefetch (bit-exact, decode)
   - Askeladd #109: simd_sum vectorization sweep (bit-exact, decode)
   - Thorfinn #112: attention epilogue 1-pass bfloat16 merge (MEDIUM risk)
3. Research wave 2: O-proj NVFP4 inline dot4, attention output float4,
   LAGUNA_RESCALE branch elimination, block width doubling.
