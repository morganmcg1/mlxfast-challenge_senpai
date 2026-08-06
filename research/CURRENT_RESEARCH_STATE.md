# SENPAI Research State
- 2026-08-06T05:39Z (updated)
- Campaign mlxfast-birch-20260805. Four students assigned round-2 decode
  optimization experiments (PRs #93-96), all IDLE awaiting student commits.
- **SCORE GAP**: Current best 2.5459 (commit 4058d0b on M5) vs target 2.5523
  (lBroth) = ~0.25% gap. Any single experiment success likely closes this.
- **FRONTIER**: aa3d227 (advisor HEAD, decode audit notes). Previous frontier
  12a712d (PR #84: top-8 elimination, bit-exact, -49 lines, merged).

## In-Flight Experiments (4 decode arms, all independent code sections)

| Student | PR | Experiment | Mechanism | Risk | Est. Impact |
|---------|-----|-----------|-----------|------|-------------|
| Edward | #93 | Register-prefetch on down+residual kernel | Depth-1 prefetch (4 rows), overlap weight loads with compute | LOW | 0.3-1.5% decode |
| Alphonse | #94 | simd_dot in attention score computation | Replace 4 scalar FMA + simd_sum with simd_dot (5→1 ops) | MED | 0.2-1.0% decode |
| Askeladd | #95 | O-proj unroll sweep (DARKBLOOM_L5_UNROLL 2→4) | Double outstanding loads per thread | LOW | 0.2-1.0% decode |
| Thorfinn | #96 | Register-prefetch on shared SwiGLU QMV (Rows1) | Depth-1 prefetch (4 blocks), overlap weight loads with compute | LOW | 0.3-1.5% decode |

All 4 arms target decode path (75% score weight). All independent code sections.
Edward + Thorfinn use same prefetch pattern (proven in routed R1 kernel lines
7325-7370) but on different kernels. Alphonse tests instruction reduction on
instruction-bound M5. Askeladd sweeps load unroll depth on o_proj.

## Next-Wave Experiments (READY TO ASSIGN when students free up)

### Wave 2a: Merge shared QMV into routed QMV dispatch (HIGHEST PRIORITY)
- Activate `mergedSharedActivated` scaffold (line 9931, always nil)
- Saves 39 dispatches/step (13.7% dispatch reduction)
- Scaffold + `fusedSharedDownInputs` API already exist for exactly this
- Both kernels read identical 2048-wide BF16 input `x`
- Correctness risk: LOW (independent per-row arithmetic)
- Complexity: MEDIUM (one new Metal kernel + Swift wiring)

### Wave 2b: Prefill O-proj gate product fusion
- Extend `lagunaGateProductSoftplus` to handle L>1
- Saves 40 dispatches during prefill (25% weight)
- Risk: LOW (bit-exact, extends proven decode kernel to 2D indexing)
- Independence: Prefill path, zero overlap with decode arms

## Key Research Context

- M4 Pro is bandwidth-bound (GPU gen 16); M5 Max is instruction-bound at ~89%
  capacity. Dispatch elimination and instruction reduction transfer better
  than bandwidth optimization from M4 to M5.
- M4 does NOT select `_nax` prefill kernels — M4 prefill timing is NOT evidence
  for `_nax` changes. Only decode and attention-path experiments are M4-testable.
- All decode fused O-proj kernels are hard-gated to L==1. Prefill (L>1) uses
  3-dispatch stock path.
- LagunaRuntimeModel.swift: 508,548 / 524,288 bytes (15,740 per-file headroom).
- Total editable surface: 2,965,156 / 3,000,000 bytes (34,844 headroom).

## Prior Negative Results (DO NOT REPEAT)

| PR | Student | Idea | Result |
|----|---------|------|--------|
| #75 | Edward | TG input staging (routed R1) | NEGATIVE on M4 — L1 handles 2x redundancy |
| #74 | Edward | Prefetch depth 2→4 | NEGATIVE — bandwidth-bound, depth hurts |
| #89 | — | Down+residual 4→8 SIMD groups | NEGATIVE — register pressure regression |
| #51 | Alphonse | LM-head coarse pass | CLOSED — LM-head already maximally optimized |
| #78 | Alphonse | Norm+NVFP4 QKV v1 | CLOSED — stalled, reassigned |
| #50 | Thorfinn | Merge QMV v1 | CLOSED — unresponsive |

Note: PR #74 (prefetch depth 2→4) was on the routed R1 kernel. Current
prefetch experiments (#93, #96) add depth-1 prefetch to kernels that have
ZERO prefetch — different from deepening existing prefetch. M4 instruction-
removal nulls are NOT refutations (M5 is instruction-bound). Threadgroup
geometry can flip sign across GPU core counts (M4 vs M5).

