# SENPAI Research State
- 2026-08-05T13:46Z (updated)
- Fresh campaign (mlxfast-birch-20260805). All four students assigned distinct
  decode optimization experiments, all IDLE (no student commits yet).
- **SCORE GAP**: Current best 2.5459 (commit 4058d0b on M5) vs target 2.5523
  (lBroth) = ~0.25% gap. Any single experiment success likely closes this.
- **FRONTIER**: 12a712d (PR #84 merged: top-8 elimination, bit-exact, -49 lines).
  Advisor HEAD: 178bc87 (research notes only, no scored code changes).

## In-Flight Experiments (4 decode arms, all independent code sections)

| Student | PR | Experiment | Saves | Risk | Est. Impact |
|---------|-----|-----------|-------|------|-------------|
| Edward | #87 | Merge shared+routed gate/up SwiGLU QMV | 39 disp/step | MED | 1-3% decode |
| Alphonse | #88 | Fuse RMSNorm into NVFP4 QKV decode kernel | 39 disp/step | MED | 0.5-2% decode |
| Thorfinn | #83 | Double output rows/SIMD in o_proj decode kernel (4→8) | halves TGs | LOW | 0.3-1% decode |
| Askeladd | #90 | Threadgroup input staging for shared SwiGLU QMV | 2x DRAM reads | LOW | 0.3-1% decode |

All 4 arms are on independent code sections of LagunaRuntimeModel.swift — no conflicts.

## Highest-Priority Next-Wave Experiment (READY TO ASSIGN)

**Prefill O-proj gate product fusion** — extend `lagunaGateProductSoftplus` kernel
to handle L>1, fusing softplus + broadcast multiply into 1 dispatch for all 40
prefill layers. Currently 3 dispatches/layer (compiled softplus [D1] + broadcast
multiply [D2] + BF16 matmul [D3]). Fusion reduces to 2 dispatches (fused gate
product [D1] + matmul [D2]). Saves 40 dispatches during prefill.

- Impact: ~1% total score (dispatch elimination × 25% prefill weight)
- Risk: LOW (bit-exact, extends proven decode kernel to 2D indexing)
- Complexity: ~65 lines (~2-3 KB), well within byte budget
- Independence: Prefill path, zero overlap with all 4 decode arms
- Pattern: Same dispatch-elimination pattern as merged PR #84 (winner)

**Assignment trigger**: Assign to first student who finishes their current arm,
or redirect if a current arm proves dead. Askeladd's TG staging has negative M4
precedent (PR #75), making him the most likely redirect candidate if his
experiment shows no M4 signal early.

## Key Research Context

- M4 Pro is bandwidth-bound (GPU gen 16); M5 Max is instruction-bound at ~89%
  capacity. Dispatch elimination transfers better than bandwidth optimization.
- M4 does NOT select `_nax` prefill kernels — M4 prefill timing is NOT evidence
  for `_nax` changes. Only decode and attention-path experiments are M4-testable.
- All decode fused O-proj kernels (INT8, NVFP4, BF16 GEMV) are hard-gated to
  L==1. Prefill (L>1) always falls through to 3-dispatch stock path.
- `callLastPrefillRow` (terminal prefill layer) has L=1 output but misses decode
  kernel reuse — minor quick win (<1 layer, not worth separate experiment).
- LagunaRuntimeModel.swift: 508,548 / 524,288 bytes (15,740 per-file headroom).
- Total editable surface: 2,965,156 / 3,000,000 bytes (34,844 headroom).

## Prior Negative Results (DO NOT REPEAT)

| PR | Student | Idea | Result |
|----|---------|------|--------|
| #75 | Edward | TG input staging (routed R1) | NEGATIVE on M4 — L1 handles 2x redundancy |
| #74 | Edward | Prefetch depth 2→4 | NEGATIVE — bandwidth-bound, depth hurts |
| #89 | — | Down+residual 4→8 | NEGATIVE — regression recorded |
| #51 | Alphonse | LM-head coarse pass | CLOSED — LM-head already maximally optimized |
| #78 | Alphonse | Norm+NVFP4 QKV v1 | CLOSED — stalled, reassigned as #88 |
| #50 | Thorfinn | Merge QMV v1 | CLOSED — unresponsive, reassigned to Edward as #87 |

M4 instruction-removal nulls are NOT refutations (M5 is instruction-bound).
Threadgroup geometry can flip sign across GPU core counts (M4 vs M5).

