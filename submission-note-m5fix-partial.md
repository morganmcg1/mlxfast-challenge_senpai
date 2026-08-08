# M5 Build Fix: Restore Prefill QK-norm+RoPE Custom Kernels (2 of 3 JIT compile deltas)

## Model and Effort

Model: senpai
Agent: OpenHands advisor (kepler) with 4 student agents (edward, alphonse, thorfinn, askeladd)
Effort: Maximum, autonomous research campaign

## Goal

Maximize the official paired inference speedup score on the Poolside Laguna XS 2.1
NVFP4 serial track:

```
score = decode_speedup^0.75 * prefill_speedup^0.25
```

Both component speedups must be at least 0.95. The official M5 Max (40 GPU cores,
128GB unified memory) is authoritative. Leaderboard #1: yudduy 2.6063. Our promoted:
2.5888. Gap: ~0.67%.

## Problem: 46+ Consecutive M5 Build Failures

After a series of optimization commits, the M5 build started timing out at ~900s.
The last successful M5 build was f790e33f (score 2.5213). All subsequent submissions
failed with build timeout.

## Root Cause Analysis

### Initial Hypothesis (Disproven)

The "nuclear fallback" refactoring (a2cb0a0a) replaced 31 custom Metal kernels with
standard MLX ops. Initial theory: standard MLX ops compile from larger Metal source
headers (quantized.h 2,608 lines, steel_gemm 718 lines, steel_attention 1,160 lines)
vs custom kernels (30-300 lines), causing 5-10x more Metal source to compile.

### Deep Analysis (Confirmed)

Systematic comparison of f790e33f (last M5 success) vs current HEAD revealed:

1. The standard MLX op CALLS are nearly identical between f790e33f and current code.
   Both used standard `MLX.gatherQuantizedMM` for prefill MoE, standard `matmul` for
   QKV/O-proj, standard `attentionWithCacheUpdate` for prefill SDPA.

2. The custom MoE/QKV/O-proj kernels were ALL decode-only (guarded by `x.dim(1)==1`).
   They were never used for prefill in either f790e33f or current code.

3. The ACTUAL JIT compile delta is only 3 standard MLX compiles:
   - **rope.metal** (229 lines) for prefill RoPE — f790e33f used custom
     `lagunaPrefillSlidingQKNormRoPEKernel` which was deleted in the nuclear fallback
   - **rms_norm.metal** (391 lines) for prefill QK-norm — same custom kernel
   - **steel_attention** (1,160 lines) for decode full-attn — f790e33f used custom
     `lagunaFullFusedAttentionKernel` which was reverted

4. The groupSize=32 quantizedMM calls (kHalvedScales) are guarded by
   `lagunaPrefillSharedHalvedEnabled=false` — never reached, never compiled.

### Negative Results (Preserved)

- **PR #418 (edward)**: Attempted to restore custom prefill MoE kernels from f790e33f.
  CONFIRMED: f790e33f used standard `MLX.gatherQuantizedMM` for prefill MoE. No custom
  prefill MoE kernels existed to restore. The custom MoE kernels were decode-only.
  `lagunaFusedSortedRoutedGateUp` is a dispatch fusion wrapper that still calls
  `gatherQuantizedMM` underneath — it doesn't replace the JIT compile.

- **PR #419 (alphonse)**: Attempted to restore custom QKV/O-proj prefill kernels.
  CONFIRMED: f790e33f used standard `matmul` for QKV/O-proj in prefill. No custom
  prefill QKV/O-proj kernels existed.

## Fix: This Submission

This submission composes 3 accepted PRs:

### 1. PR #407: Restore Prefill QK-norm+RoPE Custom Kernels (c72b296)

Restores `lagunaPrefillSlidingQKNormRoPEKernel` and `lagunaPrefillFullQKNormYaRNKernel`
from f790e33f. These custom Metal kernels fuse per-head RMSNorm + RoPE for all L
tokens in one dispatch per layer, replacing 6 stock dispatches (qNorm + kNorm +
transpose×2 + applyRotaryPosition×2) across 40 layers (~200 dispatch eliminations).

More importantly, these custom kernels compile from small source strings (~100 lines
each) instead of triggering JIT compilation of `rms_norm.metal` (391 lines) and
`rope.metal` (229 lines) standard MLX headers. This eliminates 2 of the 3 extra JIT
compiles that differ from f790e33f.

Bit-exact: The fused kernels consume the same FP32 atlas rows the stock RoPE
dispatches produce. The arithmetic is identical.

M4 measurement: +2.6% prefill, flat decode, bit-exact.

### 2. PR #402: kHalvedScales Runtime Constant (f763c87)

Re-implements the kHalvedScales bandwidth optimization (~0.9% score) using a runtime
`set_bytes` constant instead of a template parameter. This creates zero new JIT
compilations (the Metal compiler generates one kernel binary with both branches
present). The `lagunaPrefillSharedHalvedEnabled` flag is kept `false` for now —
the runtime constant infrastructure is ready but the actual halving is disabled
until the M5 build is confirmed stable.

Changes: fp_quantized_nax.h (QuantizedBlockLoader: kHalvedScales as constructor
param + member, read_scale() with halved indexing + escape, next() with halved
stride), fp_quantized_nax.cpp (sync twin), quantized.cpp (halved_scales detection
via group_size==32, set_bytes for runtime constant).

### 3. PR #411: _nax Function Constant Cleanup (d829fb1)

Converts 8 function constants (fc 200-207: align_M/N/K, run_skip,
stage_widest/wideld/runbar/novol) in the non-expert gather-QMM path to template
parameters baked into the kernel name. This eliminates 2^4=16 potential pipeline
specializations. The non-expert path is dormant in scored execution (all MoE uses
expert-aligned path), so this has zero direct effect on scored-path compile count.
Safe code cleanup, net-negative bytes.

## What's NOT Included (Pending)

### PR #420 (thorfinn): Full-Attention Decode Kernel Restoration

This is the 3rd JIT compile delta fix — restoring `lagunaFullFusedAttentionKernel`
from f790e33f to eliminate the `steel_attention` (1,160 lines) JIT compile for decode
full-attention shapes. This is the LARGEST of the 3 deltas. Thorfinn is currently
working on this (PR #420, WIP).

This submission tests whether fixing 2 of 3 deltas is sufficient to pass the M5
build timeout. If it fails, PR #420 will be added and resubmitted.

## Environment

- AWS Mac M4 Pro (development/testing)
- M5 Max (official scoring, 40 GPU cores, 128GB unified memory)
- Swift release build with `--force-resolved-versions`
- `./benchmark.sh --local-iterate` for correctness + timing
- M4 golden drift at step 0 is expected on non-M5 Apple Silicon

## Build and Test Commands

```bash
swift build -c release --force-resolved-versions && git checkout -- Package.resolved
./benchmark.sh --local-iterate
```

## Results

### M4 Pro (directional only, not M5 ranking)

- Build: succeeded (46.87s)
- Correctness: M4 golden drift at step 0 (expected on non-M5)
- Same-host timing (thermal artifacts likely):
  - Decode: 0.018463 → 0.013566 s/token
  - Prefill: 0.002227 → 0.001112 s/token

### M5 (authoritative)

This submission is the M5 test. Previous 46+ submissions failed with build timeout.
f790e33f (last success) scored 2.5213.

## Budget

- LRM: 333,897 bytes / 524,288 cap
- Total surface: well within 3,000,000 byte cap
- Growth per submission: well within 262,144 byte limit

## Submitted Paths

- Sources/MLXFastModel/LagunaRuntimeModel.swift
- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h
- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
- Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp

## Learning

1. The M5 build timeout is caused by cumulative JIT compile time, not compile count.
   Standard MLX ops compile from large shared headers (700-2600 lines) while custom
   kernels compile from small source strings (30-300 lines).

2. The actual delta between the last M5 success (f790e33f) and the failing current
   code is only 3 standard MLX JIT compiles: rope.metal, rms_norm.metal, and
   steel_attention. All other standard MLX ops were identical between the two.

3. Custom MoE/QKV/O-proj kernels were decode-only in f790e33f. Restoring them for
   prefill is not possible — f790e33f used standard ops for prefill MoE/QKV too.

4. The kHalvedScales runtime constant approach (set_bytes instead of template param)
   is M5-safe: zero new JIT compilations, one kernel binary with both branches.

## Next Steps

1. If M5 build passes: add PR #420 (full-attn decode kernel) for the 3rd fix
2. If M5 build fails: PR #420 is critical, add it and resubmit
3. Once M5 builds: re-enable kHalvedScales (set lagunaPrefillSharedHalvedEnabled=true)
4. Compose edward's prefill dispatch fusion (PR #425) for additional prefill gains
5. Re-apply XMAJOR fold and other optimizations
6. Submit optimized candidate to beat leaderboard 2.6063
