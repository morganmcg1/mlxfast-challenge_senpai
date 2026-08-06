# SENPAI Research State
- 2026-08-06T08:55Z (updated)
- Campaign mlxfast-birch-20260805. All 4 students active. Advisor HEAD at f4bad35.
- **SCORE GAP**: Current best 2.5459 (commit 4058d0b on M5) vs target 2.5523
  (lBroth) = ~0.25% gap. Any single experiment success likely closes this.
- **FRONTIER**: f4bad35 (advisor record on top of e925569 = PR #94 merged:
  simd_dot attention, bit-exact, -39 lines).
  Previous frontier: 12a712d (PR #84: top-8 elimination), then 61aef87 (research notes).

## MERGED: PR #94 (Alphonse) — simd_dot in fused attention score computation
- **Status**: MERGED (squash) → e925569. Bit-exact, upstream-equivalence verified.
- **Change**: Replaced 4 scalar FMA + simd_sum (5 ops) with dot(float4,float4) + simd_sum (2 ops)
  in both sliding (v1→v2) and full (v1→v2) fused attention kernels. -39 lines, -1,640 bytes.
- **M4 timing**: INCONCLUSIVE (+0.25% decode, within noise). Expected — M4 is bandwidth-bound.
- **M5 hypothesis**: Instruction reduction on instruction-bound M5. Unverified on M5.
- **Composition**: Safe to compose with #102 (threadGroup) and #100 (O-proj prefetch).
- **W&B**: Baseline y81omqko/6ga1mg8e/7qta01sy, Candidate njlm1fh1/rieo4n2q/tk4ca0ad
- **Note**: Student used dot()+simd_sum (2 ops) not simd_dot() (1 op). Still 60% instruction reduction.

## In-Flight Experiments (3 decode + 1 prefill, all independent)

| Student | PR | Experiment | Mechanism | Risk | Est. Impact |
|---------|-----|-----------|-----------|------|-------------|
| Alphonse | #107 | NVFP4 qdot dot4 vectorization | Replace 16 scalar FMA with 4 dot(float4,float4)+adds in shared qdot header (all NVFP4 kernels) | MED | 0.5-2.0% decode |
| Thorfinn | #102 | Attention threadGroup 1024→128 | Reduce 8× over-provisioning: only 128/1024 threads active. Bit-exact, improves occupancy + barrier latency | ZERO | 0.3-1.0% decode |
| Edward | #100 | Depth-1 prefetch on gated affine INT8 O-proj kernel | Prefetch weight blocks behind compute in O-proj decode kernel | LOW | 0.3-1.5% decode |
| Askeladd | #98 | Prefill O-proj affine path extension | Relax L==1 guard → quantizedMM with affine INT8 weights for prefill | MED | 0.3-1.0% prefill |

3 decode arms (75% score weight) + 1 prefill arm (25% weight). All independent code sections.

### Key Design Notes

- **Alphonse #107**: Highest-impact experiment. qdot (laguna_nvfp4_qdot_codes_16)
  is called by ALL NVFP4 kernels (shared SwiGLU QMV, routed SwiGLU R1, down+residual,
  O-proj). 16 scalar FMA → 4 dot+2 add = 6 instructions (62.5% reduction in qdot body).
  NOT bit-exact by construction (different summation order). Upstream equivalence
  REQUIRED. Fallback arms: B (dot only for word 0), C (dot for first group per word),
  D (close as negative). PR #94 proved dot() is bit-exact for attention on M5.
  Previous PR #106 (down+residual 4→8) was cancelled — duplicate of PR #89 (NEGATIVE).

- **Thorfinn #102**: Both fused attention kernels (sliding + full) dispatch
  threadGroup=1024 but only 4 simdgroups (128 threads) do work. The kernel
  comment at line 2366 confirms "one threadgroup of 128 threads (four simdgroups)".
  Reducing to threadGroup=128 is bit-exact (same sg 0-3 mapping) and reduces
  register waste + barrier latency. Runs on all 40 layers per decode step.
  Independent from #94 (dispatch params vs kernel source — different code sections).
  NOTE: #94 is now merged, so #102 must rebase to f4bad35 before testing.

- **Edward #100**: Depth-1 prefetch on gated affine INT8 O-proj kernel.
  Prior #93 (down+residual prefetch) was NEGATIVE (bandwidth-bound), but O-proj
  kernel may have different characteristics. M4 null is NOT a refutation for
  prefetch — M5 memory hierarchy differs. PR #99 is a duplicate — use #100.

- **Askeladd #98**: Extends INT8 affine O-proj from decode-only to prefill.
  Changes memory bandwidth (BF16→INT8), not dispatch count. Key distinction
  from #97 (which proved dispatch elimination is NOT a win for prefill).
  M4 prefill timing NOT evidence for _nax kernels (M4 doesn't select them).

## Next-Wave Experiments (READY TO ASSIGN when students free up)

### Wave 2a: Merge shared QMV into routed QMV dispatch
- Activate `mergedSharedActivated` scaffold (line 9931, always nil)
- Saves 39 dispatches/step (13.7% dispatch reduction)
- **WARNING**: PR #97 proved dispatch elimination is NOT a prefill win.
  This may also not help if dispatch overhead is truly negligible.
- **Conflicts with Thorfinn #102** — assign after #102 resolves

### Wave 2b: callLastPrefillRow fused O-proj
- Terminal prefill layer (layer 39) uses stock BF16 `wo(output)`
- INT8 affine O-proj kernel is shape-compatible (`[1,1,H*D]`)
- 1 layer, LOW complexity, LOW risk — quick win if affine GEMV beats BF16 GEMM

### Wave 2c: LM head int4 coarse screen (HIGHEST POTENTIAL, HIGHEST RISK)
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
- Attention kernels use threadGroup=1024 but only 128 threads active (4 simdgroups).
  Grid: (heads/2)*1024. Reducing to threadGroup=128 is bit-exact (NEW: #102).

## Prior Results (DO NOT REPEAT)

| PR | Student | Idea | Result |
|----|---------|------|--------|
| #94 | Alphonse | simd_dot (dot+simd_sum) in attention | MERGED — bit-exact, -39 lines. M4 inconclusive, M5 unverified. |
| #97 | Edward | Prefill shared expert fused bank guard | NEGATIVE — dispatch elimination is NOT a win. Dispatch overhead negligible. |
| #96 | Thorfinn | Register-prefetch on shared SwiGLU QMV | NEGATIVE — register pressure regression. Shared kernel has precomputed addresses. |
| #93 | Edward | Register-prefetch on down+residual kernel | NEGATIVE — bandwidth-bound kernel, prefetch adds overhead. W&B run 3jhy0yb3 |
| #95 | Askeladd | O-proj unroll sweep (DARKBLOOM_L5_UNROLL 2→4) | DEAD — env var controls BF16 kernel UNREACHABLE on scored decode path. W&B run k0c3pi23 |
| #75 | Edward | TG input staging (routed R1) | NEGATIVE on M4 — L1 handles 2x redundancy |
| #74 | Edward | Prefetch depth 2→4 | NEGATIVE — bandwidth-bound, depth hurts |
| #89 | — | Down+residual 4→8 SIMD groups | NEGATIVE — register pressure regression |
| #51 | Alphonse | LM-head coarse pass | CLOSED — LM-head already maximally optimized |
| #78 | Alphonse | Norm+NVFP4 QKV v1 | CLOSED — stalled, reassigned |
| #50 | Thorfinn | Merge QMV v1 | CLOSED — unresponsive |

Note: PR #74 (prefetch depth 2→4) was on the routed R1 kernel. Current
prefetch experiments (#93, #96, #100) add depth-1 prefetch to kernels that have
ZERO prefetch — different from deepening existing prefetch. PR #93 negative
on down+residual does NOT refute #100 (O-proj) — different kernel geometry.
M4 instruction-removal nulls are NOT refutations (M5 is instruction-bound).
Threadgroup geometry can flip sign across GPU core counts (M4 vs M5).
