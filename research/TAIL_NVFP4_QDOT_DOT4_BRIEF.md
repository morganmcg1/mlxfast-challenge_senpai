# tail_nvfp4_qdot scalar→dot4 Assignment Brief

## Ready-to-Assign Experiment

This is the assignment body for the tail_nvfp4_qdot dot4 vectorization experiment.
When a student becomes available, use this brief with the assign-experiment skill.

## Assignment Body

## Experiment: tail_nvfp4_qdot scalar FMA → dot(float4) vectorization (LAST remaining scalar NVFP4 qdot)

### Causal Question
The `laguna_tail_nvfp4_qdot` function (L4536-4572) is the ONLY remaining NVFP4 quantized kernel that uses scalar multiply-add accumulation. Every other NVFP4 kernel (MoE qdot at L6508, O-proj at L4224) already uses `dot(float4, float4)`. This kernel runs on ALL 40 attention layers per decode step. Can converting it to dot4 reduce instruction count and improve decode throughput on the instruction-bound M5?

### Target Evidence
The `laguna_tail_nvfp4_qdot` function at L4536-4572 uses scalar multiply-add for both the first group (L4493-4513, `lagunaTailNVFP4QDotFirstGroupSource`) and the second group (L4565-4569):

```metal
// First group (L4497-4500 or L4503-4506):
accum += (x_thread[8 * j] * v04.x +
          x_thread[8 * j + 1] * v15.x +
          x_thread[8 * j + 2] * v26.x +
          x_thread[8 * j + 3] * v37.x);

// Second group (L4565-4569):
accum += (x_thread[8 * j + 4] * v04.y +
          x_thread[8 * j + 5] * v15.y +
          x_thread[8 * j + 6] * v26.y +
          x_thread[8 * j + 7] * v37.y);
```

The O-proj kernel already uses the dot4 form (L4224-4227):
```metal
accum += dot(float4(x_thread[8 * j], x_thread[8 * j + 1], x_thread[8 * j + 2], x_thread[8 * j + 3]),
             float4(v04.x, v15.x, v26.x, v37.x));
accum += dot(float4(x_thread[8 * j + 4], x_thread[8 * j + 5], x_thread[8 * j + 6], x_thread[8 * j + 7]),
             float4(v04.y, v15.y, v26.y, v37.y));
```

Per decode step: 40 layers × 4 qdot calls × 2 groups × (4 mul + 3 add) = 4480 scalar FMA ops → 4480/4 = 1120 dot4 ops. Savings: ~3360 instructions per thread per step.

### Expected Signal
0.3-0.8% decode improvement on M5. The M5 is instruction-bound at ~89% ALU utilization. This kernel runs 40× per decode step on ALL attention layers (QKV projection). The dot4 conversion reduces the inner loop from 7 instructions (4 mul + 3 add) to 2 instructions (2 dot4 + 1 add), a 71% instruction reduction.

### Numerical Risk
**Bit-exact.** `dot(float4, float4)` on Apple Silicon implements sequential FMA in the same order as scalar multiply-accumulate. This was proven bit-exact by:
- PR #107 (NVFP4 qdot dot4): merged, bit-exact
- PR #114 (INT8 QKV dot4): merged, bit-exact
- PR #119 (NVFP4 O-proj dot4): merged, bit-exact
- PR #130 (Gate-softplus dot4): merged, bit-exact

The `laguna_tail_nvfp4_qdot` uses the same nibble extraction (L4552-4559) as the MoE `laguna_nvfp4_qdot_codes_16` (L6385-6394). The accumulation order is preserved: 8 FMAs split into two groups of 4, each computed as a sequential dot product, accumulated in the same order.

### Cheapest Decisive Test
1. Measure fresh local baseline: `./benchmark.sh --local-iterate`
2. Convert the scalar multiply-add in `lagunaTailNVFP4QDotFirstGroupSource` (L4493-4513) and the second group (L4565-4569) to `dot(float4, float4)`, matching the O-proj pattern at L4224-4227.
3. Run candidate: `./benchmark.sh --local-iterate`
4. Compare seconds/token directly
5. If correctness passes, run upstream equivalence (expect bit-exact): `research/run_upstream_equivalence.sh`

### Stop Rule
- **Green:** bit-exact, same-host seconds/token gain → proceed to `--local-submit`
- **Dead:** no gain on M4 (expected — M4 is bandwidth-bound; M4 null is NOT conclusive for instruction-reduction changes — M5 needed)
- **Invalid:** correctness failure or upstream equivalence mismatch

### Implementation Details

**Submitted paths:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`

**Target 1: `lagunaTailNVFP4QDotFirstGroupSource` (L4493-4513)**

Convert the scalar multiply-add in both the seedElide=true and seedElide=false branches:

seedElide=true branch (L4495-4507):
```metal
// BEFORE:
accum = (x_thread[8 * j] * v04.x + x_thread[8 * j + 1] * v15.x +
         x_thread[8 * j + 2] * v26.x + x_thread[8 * j + 3] * v37.x);
// ...
accum += (x_thread[8 * j] * v04.x + x_thread[8 * j + 1] * v15.x +
          x_thread[8 * j + 2] * v26.x + x_thread[8 * j + 3] * v37.x);

// AFTER:
accum = dot(float4(x_thread[8 * j], x_thread[8 * j + 1], x_thread[8 * j + 2], x_thread[8 * j + 3]),
            float4(v04.x, v15.x, v26.x, v37.x));
// ...
accum += dot(float4(x_thread[8 * j], x_thread[8 * j + 1], x_thread[8 * j + 2], x_thread[8 * j + 3]),
             float4(v04.x, v15.x, v26.x, v37.x));
```

seedElide=false branch (L4508-4512):
```metal
// BEFORE:
accum += (x_thread[8 * j] * v04.x + x_thread[8 * j + 1] * v15.x +
          x_thread[8 * j + 2] * v26.x + x_thread[8 * j + 3] * v37.x);

// AFTER:
accum += dot(float4(x_thread[8 * j], x_thread[8 * j + 1], x_thread[8 * j + 2], x_thread[8 * j + 3]),
             float4(v04.x, v15.x, v26.x, v37.x));
```

**Target 2: Second group in `laguna_tail_nvfp4_qdot` (L4565-4569)**

```metal
// BEFORE:
accum += (x_thread[8 * j + 4] * v04.y +
          x_thread[8 * j + 5] * v15.y +
          x_thread[8 * j + 6] * v26.y +
          x_thread[8 * j + 7] * v37.y);

// AFTER:
accum += dot(float4(x_thread[8 * j + 4], x_thread[8 * j + 5], x_thread[8 * j + 6], x_thread[8 * j + 7]),
             float4(v04.y, v15.y, v26.y, v37.y));
```

### Budget
File: LagunaRuntimeModel.swift at ~510K / 524,288 bytes. The change is small (<200 bytes — replacing scalar ops with dot4 is shorter). Total surface: ~2,967K / 3,000,000 bytes. Headroom: ~33K bytes.
