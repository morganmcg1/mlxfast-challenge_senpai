# Next Wave Assignment Candidates

**Date:** 2026-08-06 11:00 UTC
**Scored base:** 1a75d2b (advisor branch)
**Score:** 2.5459 → target 2.5523 (gap 0.25%)
**Hardware:** M5 Max = instruction-bound at ~89% capacity

## In-Flight (DO NOT duplicate)

| PR | Student | Experiment | Mechanism | Bit-exact | Est. |
|----|---------|-----------|-----------|-----------|------|
| #100 | Edward | O-proj depth-1 prefetch | Memory latency hiding | YES | 0.3-1.0% |
| #109 | Askeladd | simd_sum vec4 packing | Instruction reduction | YES | 0.2-1.0% |
| #112 | Thorfinn | Attention epilogue 1-pass (bfloat16) | Barrier elimination | NO | 0.3-0.6% |
| #116 | Alphonse | Shared SwiGLU depth-1 staging | Memory latency hiding | YES | 0.3-0.6% |

## Next Wave Candidates (untried, ready for assignment)

### A. LAGUNA_RESCALE Branch Removal

**Source:** `LAGUNA_RESCALE` macro in both attention kernel headers
**Lines:** 1683-1691 (sliding), 2178-2186 (full)
**Calls per step:** 4 per loop iteration × ~8 iterations × 40 layers = ~1280 calls/step
**Mechanism:** Remove `as_type<uint>` + branch + `exp(0)=1.0` shortcut.
Replace with unconditional `metal::fast::exp(delta)`.
**Bit-exact:** YES — `fast::exp(0.0f) == 1.0f` exactly on Apple Silicon
**Estimated impact:** 0.2-0.4% decode (eliminates ~4080 instructions/step)
**Complexity:** LOW — 1-line macro change in 2 kernel header strings
**Conflict:** None with in-flight PRs (attention loop body, not epilogue or score)
**Kernel name change:** Not needed (macro only, no kernel signature change)

### B. MoE Gate/Up Block Width 512→1024

**Source:** Routed SwiGLU QMV R1 kernel (line 7251) + Shared SwiGLU QMV R1 (line 6562)
**Mechanism:** Double `block_width` from 512 to 1024 and `values_per_lane` from 16 to 32.
Loop runs 2 iterations instead of 4. Each iteration does 2 qdot calls per row
(same 16-element qdot, just twice per block). Halves loop overhead (branch,
pointer compute, prefetch staging) per row.
**Bit-exact:** YES — each qdot processes the same 16 elements in the same order.
The `gate_result += qdot(...)` accumulation is sequential and unchanged.
Only the loop iteration count changes.
**Register pressure:** input_values[16]→[32] (+16 floats), staged codes +2 uint2,
staged scales +2 uint8_t. Total ~+20 registers. Kernel uses 64 threads (2
simdgroups) — plenty of per-thread register budget on M5.
**Estimated impact:** 0.3-0.8% decode (halves ~10 overhead instructions/iteration ×
512 rows × 9 experts × 39 layers)
**Complexity:** MEDIUM — modify block_width, values_per_lane, input load loop,
and prefetch staging in 2 kernels. Must also update scale addressing
(`block/block_width` divisor changes).
**Conflict:** Alphonse's #116 (shared SwiGLU staging) touches the same kernel.
Must merge #116 first, then apply block_width change on top. Or assign to a
different student after #116 resolves.
**Kernel name change:** Yes — append `_bw2` for JIT cache safety.

### C. Attention Phase 3 Restructure to 16 Simdgroups

**Source:** Fused attention kernels, Phase 3 (attention computation loop)
**Lines:** ~1526-1600 (sliding), ~1990-2060 (full)
**Background:** PR #102 tested threadGroup 1024→512 (32→16 simdgroups) and saw
7.4% decode speedup but broke correctness (skipped KV positions). The speedup
was real — from reducing dispatch overhead and barrier cost.
**Mechanism:** Keep threadGroup at 1024 but restructure Phase 3 to use only
16 simdgroups for KV iteration. Each of the 16 simdgroups processes 2× more
KV positions (stride 2*16=32 instead of 2*32=64). The other 16 simdgroups
remain idle during Phase 3 but participate in Phase 1/2/epilogue.
Alternatively: reduce threadGroup to 512 (16 sg) and have each sg process
16 positions instead of 8, maintaining coverage of all 512 KV positions.
**Bit-exact:** NO — changes the reduction order across simdgroups (different
KV positions are summed by different simdgroups). Online softmax rescaling
also changes order. Requires upstream equivalence.
**Estimated impact:** 3-7% decode (based on PR #102's 7.4% with 16 sg)
**Complexity:** HIGH — restructure KV loop stride, epilogue exchange buffer
sizes (BN 32→16), BDP changes, cross-sg reduction. Must also handle the
epilogue's `outputs[sg * BDP + lane]` addressing.
**Risk:** HIGH — may fail upstream equivalence. The online softmax is
numerically sensitive to reduction order changes.
**Conflict:** Thorfinn's #112 (attention epilogue 1-pass) touches the same
epilogue. Must resolve #112 first, then apply this on top.
**Kernel name change:** Yes — append `_bn16` for JIT cache safety.
**Fallback:** If full 16-sg restructure fails equivalence, try 24 sg
(threadGroup 768) as a partial reduction.

### D. Router GEMV + Top-8 Fusion

**Source:** Router GEMV + softmax + top-8 extraction (dispatches #4, #5)
**Lines:** ~1056-1087 (residual+RMSNorm+router), ~8237-8367 (top-8)
**Mechanism:** Fuse the router GEMV (256×2048 BF16 matmul), softmax, and
top-8 extraction into a single kernel. The 256-element intermediate logits
buffer never leaves threadgroup memory.
**Bit-exact:** Potentially — if the GEMV uses the same FP32 accumulation
order as MLX's stock gemv. The softmax and top-8 are already custom kernels.
**Estimated impact:** 2-4% decode (eliminates 1-2 dispatches + intermediate
buffer materialization per MoE layer × 39 layers)
**Complexity:** MEDIUM-HIGH — need to write a fused kernel that reproduces
the stock gemv for [256, 2048] exactly, then chains the top-8 extraction.
**Conflict:** None with in-flight PRs (dispatches #4/#5, not touched by any
in-flight experiment).
**Note:** PR #84 already eliminated redundant top-8 work. This is different:
it fuses the dispatches, not the internal computation.

### E. Texture-Backed Weight Storage (pending feasibility)

**Source:** All NVFP4 GEMV kernels
**Mechanism:** Move weight codes from MTLBuffer to MTLTexture for separate
L1 cache. May double effective cache for weight reads.
**Estimated impact:** 5-15% decode (theoretical — needs feasibility check)
**Status:** Feasibility investigation in progress (does MLXFast.metalKernel
support texture inputs?). If not feasible, this idea is dead.
**Complexity:** HIGH — requires weight transform + API changes
**Risk:** MEDIUM — texture dimension limits may require texture arrays

## Recommended Assignment Order

When students complete their current experiments:

1. **First available student → Idea A (RESCALE removal):** Quick win,
   trivial to implement, bit-exact, zero risk. Can be done in minutes.
   Assign to whoever finishes first (even if their main experiment is
   still in progress, this is a 5-minute change they can do in parallel).

2. **Second available student → Idea B (block_width doubling):** Bit-exact,
   moderate impact. Must wait for #116 (Alphonse) to resolve first since
   they touch the same kernel.

3. **Third available student → Idea C (attention restructure):** Highest
   potential but highest risk. Must wait for #112 (Thorfinn) to resolve.
   Assign to the student most comfortable with Metal kernel restructuring.

4. **Fourth available student → Idea D (router fusion):** Independent of
   all in-flight PRs. Can start immediately. Medium effort, medium impact.

5. **Idea E (texture):** Only if feasibility check passes. Assign as a
   research investigation first, not a full implementation.

## Composition Strategy

After the next wave completes:
- A + B compose (different kernels: attention vs MoE)
- A + D compose (different kernels: attention vs router)
- B + D compose (different kernels: MoE vs router)
- C is standalone (high-risk, needs individual validation before composing)
- All in-flight winners compose with A, B, D (different kernels)
- C + #112: Must compose carefully (both touch attention epilogue)
