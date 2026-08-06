# SENPAI Research State
- 2026-08-06T12:27Z (updated)
- Campaign mlxfast-birch-20260805. Advisor HEAD at 495e4db (deep research ideas added).
  Previous frontier: a996a21 (5 merged improvements, M5 submission 00de2d3f).
- **WAVE 3 ASSIGNED**: 4 new instruction-reduction experiments from DEEP_RESEARCH_IDEAS.md.
  All 4 students assigned to independent, novel optimization arms targeting different kernel families.
  PRs: #121 (Edward), #122 (Alphonse), #123 (Thorfinn), #124 (Askeladd).
- **LEADERBOARD**: Our team (morganmcg1) holds #1 at 2.5888 (maple campaign).
  Birch campaign best: 2.5459 (commit d4235c9, M5).
  Target: 2.5523 (gap ~0.0064, ~0.25%).
- **FRONTIER**: 495e4db (advisor HEAD, deep research ideas committed).
  Previous: a996a21 (5 merged improvements: #94, #98, #107, #114, #116, M5 submitted).
- **BROKEN PRs**: #69, #83, #86, #92, #99, #108, #111, #113, #115 (orphan drafts with
  invalid/missing markers from prior sessions). Cannot close via close_experiment. Ignore.
- **CLOSED**: PRs #117 (Edward), #118 (Thorfinn), #120 (Askeladd) closed via close_experiment.
  PR #119 (Alphonse NVFP4 O-proj dot4) merged → 639646a. PR #98 reverted → cc63c1c.

## COMPOSITION STRATEGY (see research/COMPOSITION_STRATEGY.md for full analysis)

**Merge order**: #109 (bit-exact, ZERO risk) → #100 (bit-exact, LOW risk)
→ #114 (MED, needs equivalence) → #112 (MED, needs equivalence)

**Submission strategy**: Submit INDIVIDUALLY first for clean M5 attribution.
If gap not closed by single experiment, compose #109 + #100 (both bit-exact,
0.5–2.5% compound decode gain). Never compose unproven non-bit-exact changes.

**Conflict analysis**: No executable code overlaps. #100 + #109 touch same
function (O-proj L4090–4244) but different sections (body vs epilogue) —
textual rebase conflict possible, manually resolvable. All other pairs fully
independent. Merged #107 (qdot header) affects #109's SwiGLU/Down kernels but
NOT #100 (O-proj has own inline qdot), #114 (INT8, not NVFP4), or #112 (BF16).

**Composition risk**: LOW. Different dispatches, no global flip to bandwidth-
bound. Register pressure does not accumulate across kernels. Instruction
reductions decrease heat. All changes are instruction reductions → negative
byte delta, no budget risk.

## MERGED: PR #94 (Alphonse) — simd_dot in fused attention score computation
- **Status**: MERGED (squash) → e925569. Bit-exact, upstream-equivalence verified.
- **Change**: Replaced 4 scalar FMA + simd_sum (5 ops) with dot(float4,float4) + simd_sum (2 ops)
  in both sliding (v1→v2) and full (v1→v2) fused attention kernels. -39 lines, -1,640 bytes.
- **M4 timing**: INCONCLUSIVE (+0.25% decode, within noise). Expected — M4 is bandwidth-bound.
- **M5 hypothesis**: Instruction reduction on instruction-bound M5. Unverified on M5.
- **Composition**: Safe to compose with #102 (threadGroup) and #100 (O-proj prefetch).
- **W&B**: Baseline y81omqko/6ga1mg8e/7qta01sy, Candidate njlm1fh1/rieo4n2q/tk4ca0ad
- **Note**: Student used dot()+simd_sum (2 ops) not simd_dot() (1 op). Still 60% instruction reduction.

## MERGED: PR #107 (Alphonse) — NVFP4 qdot dot4 vectorization
- **Status**: MERGED (squash) → 16f1dc5. Bit-exact, upstream-equivalence verified.
- **Change**: Replaced 16 scalar fma() with 4 dot(float4,float4) + 2 add in
  `packedWordBody()` (the shared NVFP4 qdot header). 7 insertions, 12 deletions.
  62.5% instruction reduction in the qdot body.
- **M4 same-host timing**: decode 0.013387→0.013273 s/tok (-0.85%), prefill
  neutral (+0.1%). Correctness: max_abs_diff=0 (bit-exact).
- **Upstream equivalence**: All 8 decode steps EXACT (maxAbsError=0). Prefill
  maxAbsError=0.125 is pre-existing M4 fixture drift (identical to baseline).
- **Full tests**: 456/456 passed.
- **Key finding**: dot(float4,float4) is numerically safe for NVFP4 qdot —
  identical greedy tokens and exact decode-step logits vs upstream oracle.
  M4 (bandwidth-bound) shows 0.85%; M5 (ALU-bound) should show larger gain.
- **Composition**: qdot is called by ALL NVFP4 kernels. Composes with all
  other experiments (different code paths).

## MERGED: PR #98 (Askeladd) — Prefill O-proj affine INT8 path extension
- **Status**: MERGED (squash) → b6a0889. Bit-exact, upstream-equivalence verified.
- **Change**: Extended affine INT8 O-proj `quantizedMM` path from L==1 (decode-only)
  to L>1 (prefill). Guard relaxation: removed `B==1, L==1` constraint, replaced
  `dims(1,1,...)` with `ndim==3, dim(-1)==...`. Fused GEMV kept decode-only (self-
  declines for L>1). Gate product softplus guarded to L==1. 6 insertions, 6 deletions.
- **M4 same-host timing**: Prefill 3.3% faster (0.001156→0.001119 s/tok), decode
  within noise (0.992x). Correctness: max_abs_diff=0, all gates passed.
- **W&B**: Baseline 7bidudzi, Candidate j4unnmfw (local-iterate same-host pair).
- **_nax VERIFIED (2026-08-06)**: Source investigation confirms `quantizedMM` with
  affine INT8 DOES select `_nax` on M5. Dispatch path: `quantizedMM` → `qmm`
  (quantized.cpp:718) → `qmm_nax` (quantized.cpp:735) when `is_nax_available() &&
  transpose && K%64==0 && non-float32`. M5 satisfies `is_nax_available()` (macOS
  26.2+, GPU gen≥17). Both old BF16 `wo(output)` and new affine INT8 `quantizedMM`
  use `_nax` on M5. The bandwidth reduction (INT8 0.5625 B/param vs BF16 2.0 B/param)
  is architecture-independent. _nax reachability risk is RESOLVED — LOW risk.
- **Remaining caveat**: M4 (gen 16) ran non-`_nax` quantized kernels; M5 runs
  `_nax` quantized kernels. Net prefill delta on M5 is still empirical (INT8
  dequant overhead vs BF16 bandwidth savings), but the mechanism is sound.
  Official M5 measurement needed to confirm gain, not to prevent regression.

## In-Flight Experiments (Wave 3: novel instruction-reduction arms from DEEP_RESEARCH_IDEAS.md)

All 4 students assigned to independent, novel optimization arms targeting different kernel families.
These go beyond the scalar-FMA-to-dot4 pattern that dominated prior work.

| Student | PR | Experiment | Mechanism | Risk | Est. Impact | Bit-exact? | Status |
|---------|-----|-----------|-----------|------|-------------|------------|--------|
| Edward | #121 | NVFP4 Code Pre-Expansion Side Bank | Pre-expand 4-bit nibble codes to half2 bit patterns at transform time. Replace 13-op extract macro with 1 uint4 load. O-proj + SwiGLU. ~135K ALU ops/step eliminated. | LOW | 0.5-2.0% decode | YES | ASSIGNED |
| Alphonse | #122 | Fused pair_a+pair_b Online Softmax | Compute both KV scores first, apply single joint rescale instead of 2 sequential. Attention main loop, ~22K ops/step saved. | MED | 0.5-1.5% decode | NO | ASSIGNED |
| Thorfinn | #123 | SwiGLU Input Scatter-to-float4 | Eliminate scatter-to-thread-float[16] array, pass float4 by value to qdot. ~45K instructions/step eliminated. | LOW | 0.3-0.8% decode | YES | ASSIGNED |
| Askeladd | #124 | Gate-Scale Fold in O-proj | Fold gate g into per-group scale, eliminate 16 per-element multiplies + 16 BF16 rounds per k-block. ~38K ops/step. | MED | 0.3-1.0% decode | NO | ASSIGNED |

**All 4 experiments are independent** — they touch different kernels/sections:
- Edward: O-proj extract macro (L4127-4136) + SwiGLU header extract (L6340-6375) + Transform.swift
- Alphonse: Attention main loop (L1550-1601 sliding, L2013-2064 full) — different kernel entirely
- Thorfinn: SwiGLU qdot function signature (L6452-6459) + kernel bodies (L6483-6518, L6575-6618)
- Askeladd: O-proj loadInput (L4152-4162) + scale application (L4220) — different section from Edward

All target the instruction-bound M5 decode path. Two bit-exact (LOW risk), two not bit-exact (MED risk).
Maximum compound decode gain if all win: 1.6-5.3%.

### Remaining ideas from DEEP_RESEARCH_IDEAS.md (unassigned, ready for next wave):
- Idea #4: Scale Decode LUT — 256-entry float LUT replaces 5-op E4M3 decode. Bit-exact, 0.2-0.5%.
- Idea #5: O-proj block_size 512→1024 — halve loop iterations. Bit-exact, 0.1-0.5%.
- Idea #6: fma() in attention output — 1 instr savings per element. Not bit-exact, 0.1-0.3%.

### Key Design Notes

- **Edward #117 (INT8 O-proj dot4)**: Same pattern as merged PR #114 (INT8 QKV
  dot4). The INT8 affine O-proj inner loop has 8 scalar FMAs (values_per_thread=8).
  Replacing with 2 dot(float4)+1 add reduces 8 instructions to 3. PR #114 proved
  bit-exact for the same transformation on the QKV kernel. 40 layers, decode.

- **Thorfinn #118 (attn pair_o float4 FMA)**: The pair attention output accumulation
  does 8 scalar FMAs per iteration (pair_o0[0..3] and pair_o1[0..3] each updated
  with factor*old + exp*value). float4 FMA is element-wise — no cross-element
  interaction, no reduction order change. Should be bit-exact. 3 blocks in the
  kernel: main loop sub_a, sub_b, and tail. N iterations per layer (up to 512).

- **Alphonse #119 (NVFP4 O-proj dot4)**: The NVFP4 O-proj kernel has its own
  inline dequant + accumulation (NOT using laguna_nvfp4_qdot_16 which was already
  optimized by PR #107). Each group of 4 scalar multiply-adds can be replaced
  with 1 dot(float4,float4). PR #107 proved dot() bit-exact for the same pattern.
  seedElide branch needs careful handling (assign vs add for j==0).

- **Askeladd #120 (router GEMV dot4)**: The fused RMSNorm+router kernel has an
  EXPLICIT WARNING (L846-848) about accumulation order: regrouping 64 sequential
  adds into a tree broke the hidden gate. Using dot() WITHIN each 4-element group
  preserves across-block sequential order. PRs #107/#114 prove dot() is sequential
  FMA on Apple Silicon. But the router is the strictest accumulation gate —
  upstream-equivalence verification is mandatory. 39 layers, decode.

### Merged improvements on advisor branch a996a21 (5 improvements, all compose):
- PR #94 (simd_dot attention, bit-exact): merged
- PR #98 (prefill O-proj affine INT8): merged, +3.3% prefill on M4
- PR #107 (qdot dot4 vectorization, bit-exact): merged, -0.85% decode on M4
- PR #114 (INT8 QKV dot4, numerically verified): merged
- PR #116 (shared SwiGLU staging, bit-exact): merged, M4 neutral (expected)

**M5 SUBMISSION DISPATCHED**: 5-PR composition (a996a21) submitted as submission 00de2d3f.
Awaiting M5 result. This is the first birch-campaign M5 submission of the composed advisor branch.

## MoE Kernel Analysis Findings (from frontier subagent, 2026-08-06)

### Finding A (HIGH, BIT-EXACT) — Shared SwiGLU QMV rows1 depth-1 weight staging
- `lagunaSharedSwiGLUQMVRows1Kernel` (L6558-6640) lacks depth-1 weight staging
- Routed R1 kernel (L7246-7396) already stages block b+1's codes/scales before block b's qdots
- Shared kernel uses non-staging `laguna_nvfp4_qdot_16` instead of `laguna_nvfp4_qdot_codes_16`
- **Port the exact staging pattern** — same qdot, same K-block count, same TG geometry
- Proven in sibling kernel, mechanical change
- Expected: 0.3-0.6% decode

### Finding B (MEDIUM, BIT-EXACT) — Fused down+residual simd_sum vectorization
- L7628-7633 uses 4 separate scalar `simd_sum` calls
- Standalone `lagunaRoutedDownReduceKernel` (L7469-7474) uses single `vec<float,4>` packed `simd_sum`
- Replace 4 scalar with 1 packed — 442K fewer cross-lane reductions per token
- **ALREADY ASSIGNED to Askeladd as part of PR #109**

### Finding C (MEDIUM, BIT-EXACT) — Fused down+residual weight staging
- L7618-7633 loads weight/scale per-row inside the loop
- Standalone kernel (L7453-7467) stages all 4 rows' codes/scale bytes before computing any qdot
- Port the staging pattern

### Finding E (LOW-MED, NOT bit-exact) — Prefill gather-GEMM tiling
- BM=BN=BK=64, WM=WN=2. Could try BK=128 or asymmetric WM/WN
- Changes reduction order → requires upstream equivalence test
- M4 doesn't select `_nax`, so M5-only evidence needed. Defer.

## Next-Wave Experiments (READY TO ASSIGN when students free up)

### Wave 2a: Shared SwiGLU QMV rows1 depth-1 weight staging (Finding A)
- **HIGHEST PRIORITY unassigned bit-exact idea**
- Port depth-1 staging from routed R1 kernel to shared kernel
- Same qdot, same K-block count, same threadgroup geometry
- Proven in sibling kernel, mechanical change
- Expected: 0.3-0.6% decode
- Assign when Edward or Thorfinn frees up

### Wave 2b: MoE gate/up block_width 512→1024
- Halve loop iterations in gate/up QMV kernels
- Bit-exact (same computation, fewer loop overhead)
- Expected: 0.3-0.8% decode

### Wave 2c: LAGUNA_RESCALE branch elimination
- Remove dead branch, always call exp(0)=1
- Bit-exact, zero risk
- Expected: 0.2-0.4% decode

### Wave 2d: Merge shared QMV into routed QMV dispatch
- Activate `mergedSharedActivated` scaffold (line 9931, always nil)
- Saves 39 dispatches/step (13.7% dispatch reduction)
- **WARNING**: PR #97 proved dispatch elimination is NOT a prefill win.
  This may also not help if dispatch overhead is truly negligible.

### Wave 2e: callLastPrefillRow fused O-proj
- Terminal prefill layer (layer 39) uses stock BF16 `wo(output)`
- INT8 affine O-proj kernel is shape-compatible (`[1,1,H*D]`)
- 1 layer, LOW complexity, LOW risk — quick win if affine GEMV beats BF16 GEMM

### Wave 2f: LM head int4 coarse screen (HIGHEST POTENTIAL, HIGHEST RISK)
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
| #107 | Alphonse | NVFP4 qdot dot4 vectorization | MERGED → 16f1dc5. Bit-exact, 62.5% instruction reduction. M4 decode -0.85%, M5 should show more. |
| #94 | Alphonse | simd_dot (dot+simd_sum) in attention | MERGED → e925569. Bit-exact, -39 lines. M4 inconclusive, M5 unverified. |
| #98 | Askeladd | Prefill O-proj affine INT8 path extension | MERGED → b6a0889. Bit-exact, M4 prefill +3.3%. _nax confirmed reachable on M5. |
| #102 | Thorfinn | Attention threadGroup 1024→128 | CLOSED — 7.4% speedup was from doing half the work, not threadGroup change. |
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
