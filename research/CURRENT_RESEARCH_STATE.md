# SENPAI Research State
- 2026-08-06T06:45Z (updated)
- Campaign mlxfast-birch-20260805. Three students on decode experiments (#94-96),
  Edward reassigned to prefill experiment (#97) after #93 negative result.
  Advisor HEAD at bc659cb (research-only commits, no scored code change).
- **SCORE GAP**: Current best 2.5459 (commit 4058d0b on M5) vs target 2.5523
  (lBroth) = ~0.25% gap. Any single experiment success likely closes this.
- **FRONTIER**: bc659cb (advisor HEAD, research state update). Previous frontier
  12a712d (PR #84: top-8 elimination, bit-exact, -49 lines, merged).

## In-Flight Experiments (3 decode + 1 prefill, all independent code sections)

| Student | PR | Experiment | Mechanism | Risk | Est. Impact |
|---------|-----|-----------|-----------|------|-------------|
| Alphonse | #94 | simd_dot in attention score computation | Replace 4 scalar FMA + simd_sum with simd_dot (5→1 ops) | MED | 0.2-1.0% decode |
| Askeladd | #95 | O-proj unroll sweep (DARKBLOOM_L5_UNROLL 2→4) | Double outstanding loads per thread | LOW | 0.2-1.0% decode |
| Thorfinn | #96 | Register-prefetch on shared SwiGLU QMV (Rows1) | Depth-1 prefetch (4 blocks), overlap weight loads with compute | LOW | 0.3-1.5% decode |
| Edward | #97 | Prefill shared expert fused bank guard | Remove x.dim(1)==1 guard → fused [gate;up] bank QMM for prefill | ZERO | 39 dispatches prefill |

3 decode arms (75% score weight) + 1 prefill arm (25% weight). All independent.
Edward pivoted from decode to prefill after #93 negative. Prefill is largely
unexplored — any measurable prefill gain is valuable at 25% score weight.

## Next-Wave Experiments (READY TO ASSIGN when students free up)

### Wave 2a: Merge shared QMV into routed QMV dispatch (HIGHEST PRIORITY)
- Activate `mergedSharedActivated` scaffold (line 9931, always nil)
- Saves 39 dispatches/step (13.7% dispatch reduction)
- Scaffold + `fusedSharedDownInputs` API already exist for exactly this
- Both kernels read identical 2048-wide BF16 input `x`
- Correctness risk: LOW (independent per-row arithmetic)
- Complexity: MEDIUM (one new Metal kernel + Swift wiring)
- **Conflicts with Thorfinn #96** — assign after #96 resolves

### Wave 2b: Prefill O-proj affine path extension
- Extend INT8 affine O-proj path from decode-only (L==1) to prefill (L>1)
- Add new guard block: `quantizedMM` with affine weights instead of `wo(output)`
- Saves 40 dispatches + BF16→INT8/INT4 weight bandwidth reduction
- Risk: MEDIUM (numerical behavior change, but within accepted envelope)
- Independence: Prefill path, zero overlap with decode arms
- **Detailed implementation plan available** (see MERGE_SHARED_QMV_BRIEF.md)

### Wave 2c: callLastPrefillRow fused O-proj
- Terminal prefill layer (layer 39) uses stock BF16 `wo(output)` 
- INT8 affine O-proj kernel is shape-compatible (`[1,1,H*D]`)
- 1 layer, LOW complexity, LOW risk — quick win if affine GEMV beats BF16 GEMM
- Agent analysis confirmed all instance state is shared, ready to port

### Wave 2d: LM head int4 coarse screen (HIGHEST POTENTIAL, HIGHEST RISK)
- Coarse pass reads 109 MB/step (int5 weights) — dominant LM head cost
- int4 would halve to 54.6 MB (2× fewer bytes, bandwidth-bound kernel)
- **BLOCKER**: breaks ratio-bound certificate (|q|≤15 needs 5 bits; int4 max |q|≤7)
- Requires re-derived error bound + new codebook + overflow guard fix
- This is the single highest-potential decode lever found by subagent analysis
- Defer until simpler experiments are exhausted

## Key Research Context

- M4 Pro is bandwidth-bound (GPU gen 16); M5 Max is instruction-bound at ~89%
  capacity. Dispatch elimination and instruction reduction transfer better
  than bandwidth optimization from M4 to M5.
- M4 does NOT select `_nax` prefill kernels — M4 prefill timing is NOT evidence
  for `_nax` changes. Only decode and attention-path experiments are M4-testable.
- All decode fused O-proj kernels are hard-gated to L==1. Prefill (L>1) uses
  3-dispatch stock path (softplus + broadcast multiply + BF16 wo matmul).
- Router GEMV + top-8 fusion is ALREADY BANKED — do not re-explore.
- LM head 4-dispatch chain is near-minimal (coarse→argmax→threshold→exact
  dependency). Only RMSNorm fusion is removable (LOW impact ~0.3%).
- LagunaRuntimeModel.swift: 508,548 / 524,288 bytes (15,740 per-file headroom).
- Total editable surface: 2,963,125 / 3,000,000 bytes (36,875 headroom).

## Prior Negative Results (DO NOT REPEAT)

| PR | Student | Idea | Result |
|----|---------|------|--------|
| #93 | Edward | Register-prefetch on down+residual kernel | NEGATIVE — W&B run 3jhy0yb3 verified, bandwidth-bound kernel, prefetch adds overhead |
| #75 | Edward | TG input staging (routed R1) | NEGATIVE on M4 — L1 handles 2x redundancy |
| #74 | Edward | Prefetch depth 2→4 | NEGATIVE — bandwidth-bound, depth hurts |
| #89 | — | Down+residual 4→8 SIMD groups | NEGATIVE — register pressure regression |
| #51 | Alphonse | LM-head coarse pass | CLOSED — LM-head already maximally optimized |
| #78 | Alphonse | Norm+NVFP4 QKV v1 | CLOSED — stalled, reassigned |
| #50 | Thorfinn | Merge QMV v1 | CLOSED — unresponsive |

Note: PR #74 (prefetch depth 2→4) was on the routed R1 kernel. Current
prefetch experiments (#93, #96) add depth-1 prefetch to kernels that have
ZERO prefetch — different from deepening existing prefetch. PR #93 negative
on down+residual does NOT refute #96 (shared QMV) — different kernel geometry.
M4 instruction-removal nulls are NOT refutations (M5 is instruction-bound).
Threadgroup geometry can flip sign across GPU core counts (M4 vs M5).

