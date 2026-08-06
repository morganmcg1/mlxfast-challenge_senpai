# Prefill O-proj Analysis (2026-08-05)

## Summary

Prefill O-proj is 3 stock dispatches for ALL 40 layers:
1. softplus(projectedGate) — elementwise activation
2. broadcast multiply: output × gate → gated output [1,512,8192] BF16 (8.4 MB intermediate)
3. wo(gated) — stock matmul [512,8192] × [8192,2048] → [1,512,2048]

All decode fused O-proj kernels are hard-gated to L==1, so prefill gets zero fusion benefit.

## callLastPrefillRow (Terminal Layer 39 Only)

- Called only for the last layer during prefill (i == layers.count - 1, h.dim(1) > 1)
- Output is [1,1,H*D] — same shape as decode, satisfies fused O-proj guards
- INT8 affine kernel (lagunaGatedAffineOProj) folds softplus internally, takes raw logits
- _nativeAffineOProj is prepared for layer 39 (DARKBLOOM_NATIVE_AFFINE_OPROJ_LAYERS=40)
- Only 1 of 40 layers benefits — gain is bounded
- Risk: single-row BF16 GEMV may already be efficient; INT8 dequant overhead may not help
- Implementation: mirror callAsFunction:5941-6065 INT8 affine branches, hardcode gateIsActivated=false

## MLX GEMM Accumulation Order (M5 NAX Path)

- Shape [512,8192] × [8192,2048] BF16 → NAX split-K with 2 partitions of 4096
- bm=128, bn=128, bk=512, wm=4, wn=4, split_k_partition_size=4096
- Within partition: k-ascending FP32 MMA via NAXTile (hardware matrix multiply)
- Across partitions: single-thread sequential ascending sum, no atomics
- M5 (gen 17+) selects _nax; M4 (gen 16) does not — M4 prefill result not evidence for _nax change
- darkbloom_steel_prefill_tile override preserves k-ascending MMA chain for bit-exactness

## Bit-Exactness Risk

- 1-dispatch fused GEMM: must replicate exact NAX split-K structure — HIGH risk
- 2-dispatch (fused softplus+gate kernel → stock matmul): bit-exact, safe
  - Stock matmul is reference by definition
  - Elementwise activation is order-independent
  - Saves 1 dispatch per layer × 39 layers = 39 dispatches during prefill
  - BUT: still materializes [1,512,8192] intermediate (8.4 MB)
- No custom GEMM kernels for L>1 exist in the codebase — all are decode L=1 GEMV

## Impact Assessment

- Prefill is 25% of score, one-shot (not 128 steps like decode)
- 39 dispatch savings out of ~1000+ prefill dispatches = ~3-4% dispatch reduction
- Dispatch overhead ~1µs → ~39µs saved out of ~10-50ms prefill = ~0.1-0.4% timing gain
- The dominant prefill cost is the GEMMs themselves, not dispatch overhead
- Prefill optimizations have limited score impact vs decode (75% weight, 128 steps)

## Recommended Next-Wave Experiments (Priority Order)

1. callLastPrefillRow INT8 affine O-proj: 1 layer, LOW risk, <1KB change, quick test
2. Full prefill O-proj 2-dispatch fusion: 39 layers, MEDIUM risk, ~3KB kernel, saves 39 dispatches
3. Do NOT attempt 1-dispatch fused GEMM unless 2-dispatch overhead is proven to be the bottleneck

## Key Code Locations

- callLastPrefillRow: LagunaRuntimeModel.swift:6096-6175
- callAsFunction O-proj guard: LagunaRuntimeModel.swift:5941-6065
- lagunaGatedAffineOProj: LagunaRuntimeModel.swift:4071-4121
- lagunaGatedOutputProjection: LagunaRuntimeModel.swift:3750-3771
- lagunaUseNativeAffineOProj: LagunaRuntimeModel.swift:372-378
- _nativeAffineOProj preparation: LagunaRuntimeModel.swift:10873-10876
- callLastPrefillRow dispatch: LagunaRuntimeModel.swift:10716-10718
- NAX split-K dispatch: matmul.cpp:670+
- NAX GEMM header: kernels/steel/gemm/gemm_nax.h
