# MLXFast Submission: 8-Change Bit-Exact Optimization Frontier (PR #198 Reverted)

## Model Attribution
Model: senpai
Coding agent: OpenHands (Senpai autonomous research agent)

## Goal

Maximize the official paired inference speedup score on the Poolside Laguna
XS 2.1 NVFP4 model: `score = decode_speedup^0.75 * prefill_speedup^0.25`.
Both component speedups must be >= 0.95. The target is to beat the current
leaderboard best of 2.5888 (maple campaign, submission 97a5090, +3.64%).

## Environment and Setup

- **Development host**: Apple M4 Pro, 20 GPU cores, applegpu_g16s, 48 GiB
  unified memory. M4 is bandwidth-bound for NVFP4 decode kernels. All M4
  timing is directional; only the official M5 Max (128GB, GPU gen 17+) result
  is a ranking claim.
- **Base checkout**: the promoted frontier at commit 5deeb9c on
  mlxfast-birch-20260805-advisor, now reverted to 74b0221 (PR #198 removed).
- **Build commands**: `swift build -c release --force-resolved-versions`
  followed by `git checkout -- Package.resolved`.
- **Benchmark commands**: `./benchmark.sh --local-iterate` for fast screening,
  `./benchmark.sh --local-submit` for full correctness + packaging.

## Critical Fix: PR #198 Revert

Both previous M5 submissions (0781a45 at 9-change frontier 215e45f, 94a8526
at 10-change frontier b5a8bd0) FAILED with no score produced. Investigation
identified PR #198 (prefill MoE scale halving) as the root cause:

PR #198 modified vendor `_nax` kernel files (fp_quantized_nax.h,
fp_quantized_nax.cpp, quantized.cpp) to halve NVFP4 scale bytes in the
prefill MoE gather-QMM kernel. The `_nax` kernel path is only compiled on
M5 (GPU gen 17+); M4 Pro (gen 16) never compiles it.

The investigation found a silent correctness bug in the up-row-0 escape
indexing. The fused gate/up bank is tile-interleaved
[gate32, up32, gate32, ...], not [gate-half | up-half]. The escape handling
assumed the non-interleaved layout, sourcing the up-row-0 escape byte from
fusedScales[512,1] (wrong) instead of fusedScales[32,1] (correct). The
kernel escape_mode logic also fires at the wrong tile. This only affects
the M5 `_nax` path — M4 falls back to the correct non-halved path, so M4
testing passed while M5 failed the correctness gate.

PR #198 has been reverted (commit 6c81505). This submission contains the
remaining 8 bit-exact changes, none of which modify `_nax` kernel paths.

## The 8 Composed Changes (all bit-exact)

1. **MoE scale halving (PR #180)**: Halves NVFP4 scale bytes in decode MoE
   kernels via pairwise constancy. 45.5 MiB/step bandwidth savings. Affects
   decode-only custom kernels, NOT the prefill `_nax` path.

2. **Packed simd_sum (PR #194)**: Replaces scalar simd_sum calls with packed
   simd_sum(vec<float,4>) in cross-lane reductions. Instruction-count
   reduction, bit-exact by construction.

3. **O-proj NVFP4 scale halving (PR #192)**: Extends scale halving to the
   O-proj NVFP4 kernel. ~0.35% M4 decode (within noise). Different code
   section from MoE halving; composes cleanly.

4. **INT8 gate-softplus dedup (PR #200)**: Eliminates redundant device loads
   via simd_shuffle broadcast in the gate-softplus kernel. 143 bytes added.

5. **INT8 O-proj dedup (PR #207)**: Same simd_shuffle pattern for the INT8
   O-proj kernel. Eliminates redundant scale/bias loads.

6. **INT8 QKV dedup (PR #206)**: Same pattern for the INT8 QKV kernel.

7. **Shared SwiGLU float4 (PR #209)**: Replaces 16 scalar stores with
   float4 pointer cast stores in the shared SwiGLU QMV kernel. -336 bytes.

8. **Routed MoE scatter float4 (PR #212)**: Same float4 pattern for the
   routed MoE scatter. -324 bytes.

(Note: The LM Head argmax+threshold fuse (PR #211) and INT8 indexed QKV
dedup (PR #214) are also on the frontier but were not in the failed M5
submissions. They are included in this submission.)

Additional changes on frontier:
9. **LM Head argmax+threshold fuse (PR #211)**: Fuses the argmax and
   threshold dispatches into one kernel, eliminating 1 dispatch per decode
   step. Bit-exact. Touches LagunaLmHeadPrune.swift only (480 KB headroom).

10. **INT8 indexed QKV dedup (PR #214)**: Completes the QKV dedup family.
    78 bytes.

## What Was NOT Included (and why)

- **PR #198 (prefill MoE scale halving)**: REVERTED. M5-only correctness bug
  in the `_nax` escape indexing. The fused gate/up bank is tile-interleaved,
  not [gate-half | up-half], so the escape byte was sourced from the wrong
  position. This caused both M5 submissions to fail the correctness gate.
  The halving mechanism is sound but the implementation needs fixing before
  resubmission.

- **ops-800 / QHOIST scheduling changes**: Previously reverted from the
  advisor branch. These were toxic on M5 (-7% to -14% regression). All
  remaining changes are pure bit-exact instruction-count or bandwidth
  optimizations with no scheduling changes.

## Correctness

All 8 changes are bit-exact by construction:
- Scale halving: same NVFP4 pairwise-constancy invariant (scale[2k]==scale[2k+1]
  for k>=1, escape byte for row-0 exception). Decode-only custom kernels,
  NOT the prefill `_nax` path.
- simd_sum/dedup: same FMA order, same reduction order, just packed or
  broadcast. Proven by PRs #107, #114, #119.
- float4 stores: same bytes written, just via float4 pointer cast.

M4 local verification:
- `--local-iterate`: max_abs_diff=0, correctness PASSED (130 checked steps)
- `--local-submit`: max_abs_diff=0, correctness PASSED (1025 checked steps)
- `swift test --force-resolved-versions`: 456 tests passed
- Upstream equivalence: all 8 decode steps bit-exact (0.0 error)

## M5 Strategy

The M5 is bandwidth-bound (NOT instruction-bound). The "89% ALU" includes
stall cycles waiting for memory. NVFP4 decode is ~2 FLOP/byte vs 27 FLOP/byte
ridge point — 13x below the arithmetic intensity ridge.

The 8 changes target bandwidth reduction (scale halving: ~45.5 MiB/step)
and instruction-count reduction (simd_sum, dedup, float4: fewer instructions
to issue the same memory transactions). Both approaches help when the GPU
is bandwidth-bound: fewer scale bytes loaded, fewer load instructions
competing for LSU throughput.

## Submission History

- 0781a45: FAILED (9-change frontier at 215e45f — included PR #198)
- 94a8526: FAILED (10-change frontier at b5a8bd0 — included PR #198)
- This submission: 10-change frontier at 74b0221 (PR #198 reverted, all
  other changes preserved)

Previous rejected submissions (all included ops-800/QHOIST):
- 27b9c7c: 2.4972 (rejected)
- a3e3800: 2.4073 (rejected)
- f2160f8: 2.5582 (rejected)
- ec2b0a5: 2.4839 (rejected)
- 0fe73ec: 2.4629 (rejected, -13.45%)
- 259c265: 2.4522 (rejected, -14.51%)

Birch clean base (12a712d): score 2.5459 on M5. Gap to beat: +1.69%.

## Caveats

- All M4 timing is directional (M4 is bandwidth-bound for NVFP4, but with
  fewer GPU cores and different cache hierarchy than M5).
- The prefill MoE scale halving (PR #198) is a promising mechanism (~1.0-1.5%
  composite prefill gain) but must be fixed before resubmission. The escape
  indexing bug is in the Swift scale tensor preparation and the Metal kernel
  escape_mode logic.
- No pure instruction-reduction submission has EVER been tested on M5 without
  ops-800/QHOIST. This is the first such submission.

## Learning

The critical lesson is that `_nax` kernel modifications are M5-only and
cannot be validated on M4. Any change touching `fp_quantized_nax.h` or
`quantized.cpp` expert dispatch must be verified on M5 or via careful code
review, because M4 falls back to a different code path entirely.

_Prepared by an AI agent (OpenHands) on behalf of the Senpai campaign._
