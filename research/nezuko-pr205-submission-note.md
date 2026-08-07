# Decode attention merge epilogue: stage the cross-simdgroup transpose as `float4`

Single mechanism, one file (`Sources/MLXFastModel/LagunaRuntimeModel.swift`),
**net −454 bytes**, and **bit-identical by construction**.

## What changed

Both decode attention kernels (sliding-window and full) process two heads per
threadgroup and finish with a cross-simdgroup merge: each simdgroup holds a
partial softmax result for its own KV block, and the epilogue transposes those
partials through threadgroup memory so a single `simd_sum` per output component
can combine them.

That epilogue used to declare `threadgroup U outputs[4 * BN * BDP]` and stage
**eight scalar planes** through it — 4 output components × 2 heads — with eight
threadgroup stores followed by eight threadgroup loads, all in one round.

It now declares `threadgroup float4 outputs4[BN * BDP]` and runs two rounds:
round 1 stores head 0's four components as a **single `float4`**, barriers,
reads one `float4` back, reduces and finalises head 0; round 2 reuses the same
buffer for head 1. **8 stores + 8 loads → 2 stores + 2 loads.**

Threadgroup footprint is unchanged (`float4[1056]` = `float[4224]` = 16 896 B,
total static threadgroup memory 18 432 B), grid and threadgroup size are
unchanged, and all barriers are retained — including the new round-1-read →
round-2-write WAR barrier that buffer reuse requires.

## Why it cannot change a bit

`U` is `typedef float`, so the `float4` staging is a pure repack of the same
32-bit values. The writer→reader transpose is the same bijection as before
(`lane*BDP+sg` written, `sg*BDP+lane` read), so **every `simd_sum` consumes the
same 32 scalar products from the same lanes in the same order**. Only the
grouping of independent reductions changed, which cannot perturb a result.

## Correctness evidence

- **Bitwise logit digest**, 64 decode steps, `top_k = 100352` (full vocabulary):
  base and candidate produce the **identical** whole-run digest
  `3447204b…4928`; **0 of 65 per-step digests differ**.
- **The control fires.** A 1-ULP bfloat XOR injected into the final store of
  both edited kernels — the smallest perturbation this change could have
  introduced — flips **64 of 65** per-step digests (the one it misses is the
  prefill step, correctly, since only the decode kernels were faulted). The
  greedy-token comparison stayed at 0 mismatches even under that fault, so the
  digest, not the token stream, is the instrument that is actually load-bearing
  here.
- **Upstream-equivalence oracle**: all 8 decode steps exactly
  `maximumAbsoluteLogitError = 0`, `EQUIVALENCE_EXACT_STEPS=8`, exactly one test
  selected. The prefill row (`0.125` / `0.011933609`, token `5991`) is the
  pre-existing M4 Pro artifact of the batched NVFP4 prefill path against the
  BF16 reference, reproduced byte-for-byte on the unmodified base in six prior
  sibling writeups; this change touches no prefill code.
- **`./benchmark.sh --local-submit`**: `passed_correctness true`,
  `max_abs_diff 0` over 1025 checked tokens / 1023 decode steps.
- An independent adversarial review of the diff returned **SAFE** on barrier
  sufficiency, FP equivalence, register liveness, indexing bounds, stale
  symbols, barrier divergence, and sliding-vs-full symmetry (the two new
  epilogues are byte-identical to each other).

## Timing evidence

Measured on Apple M4 Pro (20 GPU cores, `applegpu_g16s`), so it is directional
for the ranked M5 rather than decisive.

Kernel-level ABBA-interleaved paired differencing (400 reps × 11 rounds of
A,B,B,A; every section carries a null arm — a second independent build of the
*same* source — that must straddle zero):

| kernel | null arm | this change |
|---|---|---|
| sliding (32 TGs) | +0.011 µs [−0.074 +0.127] | **+0.400 µs (+2.51 %) [+0.258 +0.564]** |
| full (24 TGs) | −0.011 µs [−0.261 +0.404] | **+0.202 µs (+1.11 %) [+0.073 +0.443]** |

This was the only candidate rewrite of five with a **strictly positive spread on
both kernels**; the others (deferred divides, reciprocal hoist, and two
combinations) were at or below the null floor and were not shipped. Per decode
step the model runs 30 sliding and 10 full attention layers, projecting
**≈ 14 µs/step** on this host.

The mechanism is entirely intra-threadgroup — threadgroup-memory access width
and count, with essentially zero incremental DRAM traffic — and it is
unconditional rather than a heuristic that could select differently on another
architecture. A companion sweep showed the epilogue is strongly sensitive to
this exact access pattern (dropping the `BDP` pad from 33 to 32 costs
**+1.97 µs** sliding and **+1.82 µs** full), which is what carries the sign of
the result across to the M5.

_Prepared by an AI agent (OpenHands) on behalf of the Senpai campaign._
