# Deep Research: Novel Optimization Ideas Beyond dot4

**Date**: 2026-08-05 (deep kernel source analysis)
**Score**: 2.5459 (current best, M5) → 2.5523 (target). Gap: ~0.25%.
**Architecture**: M5 Max = instruction-bound at ~89% GPU capacity. NOT bandwidth-bound.
**Score formula**: `decode_speedup^0.75 * prefill_speedup^0.25`. Decode = 75% weight.

## Methodology

Read the full kernel source in `Sources/MLXFastModel/LagunaRuntimeModel.swift`
(11,154 lines) including:
- Attention kernels (L1500–1700 sliding, L1990–2100 full)
- O-proj NVFP4 kernel (`lagunaGatedAffineOProjNVFP4Source` L4090–4244)
- SwiGLU QMV header (`lagunaSharedSwiGLUQMVHeader` L6334–6468)
- Shared SwiGLU QMV kernel (L6471–6549)
- Dense layer kernels (L7741+)
- Runtime feature flags (L100–200, L3998–4030, L6175–6332)

Cross-referenced every idea against ALL existing research files:
`RESEARCH_IDEAS_2026-08-05.md`, `RESEARCH_IDEAS_FRESH_20260805.md`,
`RESEARCH_IDEAS_NEXT_WAVE.md`, `RESEARCH_IDEAS_NEXT_WAVE_ASSIGNMENTS.md`,
`NOVEL_OPTIMIZATION_TARGETS.md`, `NOVEL_FUSION_IDEAS.md`,
`NEGATIVE_RESULTS_2026-08-05.md`, `DEEP_CODE_ANALYSIS_V2.md`.

**All 7 ideas below are NOVEL mechanisms not found in any prior research file.**
They go beyond the scalar-FMA-to-dot4 pattern that dominated prior work.

## In-Flight Experiments (DO NOT duplicate)

| PR | Student | Experiment | Section touched |
|----|---------|-----------|-----------------|
| #100 | Edward | O-proj depth-1 prefetch | O-proj body (weight loading) |
| #109 | Askeladd | simd_sum vec4 packing | O-proj epilogue |
| #112 | Thorfinn | Attention epilogue 1-pass merge | Attention epilogue barriers |
| #116 | Alphonse | Shared SwiGLU depth-1 staging | SwiGLU QMV body |

---

## Ranked Ideas

### 1. NVFP4 Code Pre-Expansion Side Bank (Transform + Runtime)

**Target**: `lagunaGatedAffineOProjNVFP4Source` L4133–4142 (extract macro),
L4217–4220 (dequant), and the shared header `lagunaSharedSwiGLUQMVHeader`
L6348–6383 (extract switch). Transform: `Sources/MLXFastTransform/Transform.swift`.

**Status**: FRESH — not in any prior research file.

**Problem**: Every NVFP4 qdot call performs a 13-instruction bitwise extract
(`xe | xe<<3`, `yo | yo>>3`, 4 shift+mask patterns) per 32-bit code word to
reconstruct the half2 bit patterns from the packed 4-bit nibbles. This extract
runs in the inner loop of every qdot call. The extract is pure ALU (bit
manipulation) with no data dependency on the input — it only depends on the
weight codes, which are fixed at checkpoint time. Per step: ~135K extract ALU
instructions (see Reach below for the breakdown).

**Mechanism**: During the weight transform (offline, not scored), pre-expand
each 32-bit packed code word into its 4 half2 bit patterns and store them as a
decode-only side bank. The `DARKBLOOM_PACKED_SCALES` precedent (L152–166) already
builds a side bank for scales in the kernel's walk order. Apply the same pattern
for expanded codes:

1. Transform: For each 32-bit code word `c`, precompute `p0..p3` (the 4
   `uint` half2 bit patterns) and store them as a 16-byte `uint4` side bank.
   Memory cost: 4× the code bytes (each 4-byte code word → 16 bytes of
   pre-expanded patterns). For O-proj: 2048 cols × 2048 rows / 8 × 4 =
   ~2 MB per layer × 40 = ~80 MB. Within the 128 GB budget.

2. Runtime: Replace the `extract` macro with a direct `uint4` load:
```metal
// Current (L4133-4142): 13 bitwise ops per code word
const uint xe = c & 0x0F0F0F0Fu; ... (13 ops)

// Proposed: 1 load per code word (pre-expanded side bank)
const device uint4* expanded = (const device uint4*)expanded_codes + ...;
const uint4 patterns = expanded[j];
const uint p0 = patterns.x; const uint p1 = patterns.y;
const uint p2 = patterns.z; const uint p3 = patterns.w;
```

The dequant (`float2(as_type<half2>(p0))`) is unchanged — only the extract
bitwise ops are eliminated.

**Reach**: ALL 40 layers (O-proj) + 39 layers × 9 experts (SwiGLU QMV).
O-proj `in_vec_size = heads * headDim` (L4170, NOT `hiddenSize`): sliding layers
(30) have in_vec_size=64×128=8192 → 16 k-iterations; full layers (10) have
in_vec_size=48×128=6144 → 12 k-iterations. Each k-iteration: 4 rows × 2 code
words × 13 ops = 104 extract ops. O-proj total: 30×16×104 + 10×12×104 = 62,400
ops/step. SwiGLU: in_vec_size=2048 → 4 k-iterations. Per k-iter: 2 rows × 2
words × 13 = 52 ops. SwiGLU total: (39×4×52) + (39×8×4×52) = 8,112 + 64,896 =
73,008 ops/step. Grand total: ~135,000 extract ALU instructions eliminated/step.

**Bit-exact**: YES — the pre-expanded patterns are computed with the exact same
bitwise operations as the runtime extract, just moved to the transform. The
`float2(as_type<half2>(p))` dequant is identical. Same values, same order.

**Expected impact**: 0.5–2.0% decode. On the instruction-bound M5, eliminating
~135K ALU instructions per step is significant. The extract is ~20% of each
qdot's instruction count (13 extract ops vs ~50 total including dequant +
accumulation). This is the largest single instruction-reduction opportunity
outside of dot4.

**Risk**: LOW. Bit-exact, proven side-bank precedent (`DARKBLOOM_PACKED_SCALES`).
Memory cost (~80 MB for O-proj, more for SwiGLU) is within budget.

**Conflict with in-flight**: POTENTIAL with #100 (O-proj prefetch). If #100
prefetches raw code words, the prefetch pattern changes to prefetch pre-expanded
`uint4` values (4× larger). Must rebase after #100 merges. The shared header
change is independent of #116 (SwiGLU staging touches the body, not the extract).

**Byte budget**: The runtime source SHRINKS (extract macro removed, replaced by
a load). The transform grows by the side-bank builder code, but Transform.swift
is a smaller file with more headroom.

---

### 2. Gate-Scale Fold in O-proj (Arithmetic Reassociation)

**Target**: `lagunaGatedAffineOProjNVFP4Source` L4158–4168 (`loadInput`),
L4228 (`result[row] += scale * accum`).

**Status**: FRESH — not in any prior research file.

**Problem**: The O-proj kernel applies the gate `g` to each input element
BEFORE the qdot, then applies the per-group scale AFTER:

```metal
// L4161-4162: per-element gate application (16 muls + 16 BF16 rounds)
for(uint i=0;i<values_per_thread;++i)
    x_thread[i]=float(bfloat(float(xp[i])*g));

// L4228: per-row scale application
result[row] += scale * accum;
```

The gate `g` is constant per head (same for all 16 values_per_thread and all
4 k-blocks). The scale `scale` varies per k-block. Mathematically:
`sum(x_i * g * w_i) * scale = sum(x_i * w_i) * (g * scale)`.

So `g` can be folded into `scale`, eliminating the 16 per-element multiplies and
16 BF16 rounds per k-block per row.

**Mechanism**: Replace `loadInput` with a raw load (no gate multiply), and
fold `g` into the scale at L4210:

```metal
// Current L4161-4162 (per-element gate):
x_thread[i] = float(bfloat(float(xp[i]) * g));

// Proposed: raw load (no gate multiply)
for(uint i=0;i<values_per_thread;++i)
    x_thread[i] = float(xp[i]);

// Current L4210-4211: scale decode
uint8_t sbits = sc[row * in_vec_size_g];
scaleDecode  // produces `float scale`

// Proposed: fold g into scale
float effective_scale = scale * g;
// ... qdot unchanged ...
result[row] += effective_scale * accum;
```

This eliminates 16 `float * float` multiplies + 16 `bfloat()` roundings per
k-block per row, replacing them with 1 `float * float` multiply per k-block
per row.

Per step: 30 sliding layers × 16 k-iter + 10 full × 12 k-iter = 600 k-iterations.
Each k-iteration: 16 muls + 16 BF16 rounds = 32 ops. Total: 600 × 32 = 19,200
muls + 19,200 BF16 rounds = 38,400 ops eliminated, replaced by 600 × 1 = 600
float multiplies (g folded into scale).

**Bit-exact**: NO — this changes the rounding point. Currently: `bfloat(x * g)`
rounds to BF16 before the qdot, then `scale * accum` rounds to BF16 at the
epilogue. With the fold: `x` stays BF16 (from the input), the qdot accumulates
in FP32, then `g * scale * accum` rounds at the epilogue. The intermediate BF16
rounding of `x * g` is lost. This changes results when `x * g` falls between
two BF16 representable values.

However, the input `xp` is already BF16 (from the attention output). The gate
`g` is a softplus output (BF16). The product `xp[i] * g` is currently rounded to
BF16, introducing a ~0.4% relative error per element. Folding `g` into the scale
preserves the full-precision product in the FP32 accumulation, which is
mathematically more accurate but different from the baseline.

**Expected impact**: 0.3–1.0% decode. Eliminating 38K ALU ops (19K muls + 19K
BF16 rounds) per step on the instruction-bound M5 is meaningful. The BF16
rounding instruction (`bfloat()`) is an ALU op, not free.

**Risk**: MEDIUM. Not bit-exact — requires `LagunaUpstreamEquivalence.swift`
verification. The change is mathematically sound (reassociation of a linear
scaling), but the lost BF16 rounding may change greedy tokens in edge cases.
The same risk profile as #114 (QKV INT8 affine dot4) which passed.

**Conflict with in-flight**: NONE with #100 (prefetch touches weight loading,
not input loading). NONE with #109 (simd_sum in epilogue). The gate-scale fold
changes `loadInput` (L4158–4168) and the scale application (L4228), both
different sections.

**Note**: When `preActivatedGate=true`, `g` comes from `gate_values` (precomputed
softplus). When `preActivatedGate=false`, `g` is computed in-kernel via softplus
(L4143–4157). The fold works in both cases. The `gateSetup` section (L4143–4157)
computes `g` into `gt[lid]` — this can still compute `g`, just not apply it per
element.

---

### 3. Fused pair_a + pair_b Online Softmax (Algorithmic Restructure)

**Target**: Sliding attention kernel L1532–1601 (main loop), full attention
kernel L2010–2080 (analogous). The two-pass (a/b) pipelined online softmax.

**Status**: FRESH — not in any prior research file.

**Problem**: The attention main loop processes 2 KV positions per iteration
(pair_a and pair_b), each with a FULL online softmax update: 2 rescales, 2 exp,
2 max updates, 2 sum updates, 8 output MACs. The two positions are processed
sequentially with independent running max/sum/output accumulators:

```metal
// L1553-1574: pair_a update (2 rescale + 2 exp + 2 max + 2 sum + 8 MAC)
U pair_new_max0 = metal::max(pair_max0, pair_score0);
LAGUNA_RESCALE(pair_factor0, pair_max0 - pair_new_max0);
pair_o0[0..3] = pair_o0[0..3] * pair_factor0 + pair_exp0 * pipe_va0..3;

// L1580-1601: pair_b update (identical structure, different K/V)
U pipeb_new_max0 = metal::max(pair_max0, pipeb_score0);
LAGUNA_RESCALE(pipeb_factor0, pair_max0 - pipeb_new_max0);
pair_o0[0..3] = pair_o0[0..3] * pipeb_factor0 + pipeb_exp0 * pipe_vb0..3;
```

The pair_b update rescales the output AGAIN (from pair_a's max to the joint
max of pair_a and pair_b). If we compute the joint max of both positions first,
we can apply a SINGLE rescale to the output:

**Mechanism**: Restructure to compute both scores first, then apply a single
joint online softmax update:

```metal
// Compute both scores
U pair_score0 = simd_sum(dot(pq0, pk_a));
U pipeb_score0 = simd_sum(dot(pq0, pk_b));

// Joint max (single update instead of two sequential)
U joint_new_max0 = metal::max(metal::max(pair_max0, pair_score0), pipeb_score0);
U factor_a, factor_b;
LAGUNA_RESCALE(factor_a, pair_max0 - joint_new_max0);
LAGUNA_RESCALE(factor_b, pair_max0 - joint_new_max0);  // same base = pair_max0

U exp_a0 = metal::fast::exp(pair_score0 - joint_new_max0);
U exp_b0 = metal::fast::exp(pipeb_score0 - joint_new_max0);

pair_max0 = joint_new_max0;
pair_sum0 = pair_sum0 * factor_a + exp_a0 + exp_b0;

// Single rescale for output, then add both V contributions
pair_o0[0] = pair_o0[0] * factor_a + exp_a0 * pipe_va0 + exp_b0 * pipe_vb0;
pair_o0[1] = pair_o0[1] * factor_a + exp_a0 * pipe_va1 + exp_b0 * pipe_vb1;
pair_o0[2] = pair_o0[2] * factor_a + exp_a0 * pipe_va2 + exp_b0 * pipe_vb2;
pair_o0[3] = pair_o0[3] * factor_a + exp_a0 * pipe_va3 + exp_b0 * pipe_vb3;
```

This eliminates: 1 rescale per pair per element (the pair_b rescale), 1 max
update, 1 sum update. The V values from both positions are added in a single
output update instead of two sequential rescales.

Per iteration: saves 4 rescale calls + 4 exp calls + 4 max updates + 4 sum
updates. Replaces 8 output MAC patterns (4 per pair × 2 pairs) with 4 fused MAC
patterns (each with 2 V contributions).

Per step: 30 sliding layers × ~8 iterations × 4 pairs (2 query heads × 2
elements) × (4 rescale + 4 exp + 4 max + 4 sum + 4 MAC) = ~15,360 ops saved.
Full attention: 10 layers × ~10 iterations × 4 × same = ~6,400 ops saved.

**Bit-exact**: NO — the rescale order changes. Currently: `o = o * fa + exp_a`
then `o = o * fb + exp_b`. Proposed: `o = o * fa + exp_a + exp_b` where `fa` and
`fb` use the same base max. When `pair_max0 == joint_new_max0` (pair_a's score
is the new max), `fa = 1.0` and the proposed form is `o = o + exp_a + exp_b`
while the current form is `o = o + exp_a` then `o = o * fb + exp_b` (different
when `fb ≠ 1`). The intermediate max value changes, so the exp arguments change,
producing different (though close) values. Requires upstream equivalence.

**Expected impact**: 0.5–1.5% decode. The attention main loop runs on all 40
layers and is ~40% of decode instructions. Reducing the per-iteration
instruction count by ~30% (eliminating half the rescale/exp/max/sum ops) on
the instruction-bound M5 is a significant opportunity.

**Risk**: MEDIUM. Not bit-exact (online softmax reordering). Same risk profile
as #112 (attention epilogue 1-pass merge, also not bit-exact). Requires
`LagunaUpstreamEquivalence.swift` + 64-step drift tripwire.

**Conflict with in-flight**: POTENTIAL with #112 (Thorfinn's epilogue 1-pass
merge). #112 changes the epilogue (after the main loop). This idea changes the
main loop itself. They touch different sections of the same kernel function but
the epilogue depends on the main loop's output state. Must rebase after #112
merges. NO conflict with #100 or #109 (O-proj kernel).

---

### 4. Scale Decode LUT (Lookup Table)

**Target**: `laguna_nvfp4_scale` function (L6441–6447 in shared header),
O-proj `scaleDecode` (L4101–4109). The E4M3 scale decode path.

**Status**: FRESH — not in any prior research file. Note: `NEGATIVE_RESULTS`
#1 "register-resident scale pre-loading" is about avoiding DRAM reads of
scales, NOT about the decode computation. This idea targets the ALU decode
instructions, not memory access.

**Problem**: The `laguna_nvfp4_scale(uint8_t bits)` function decodes an E4M3
byte to a float using 4–7 ALU instructions:

```metal
// L6441-6447 (default path, scale defer ON):
static inline float laguna_nvfp4_scale(uint8_t bits) {
    if (bits < 16u) {  // fast path: 2 ops
        ushort fast_raw = ushort(bits) << 7;
        return float(as_type<half>(fast_raw));
    }
    ushort raw = ushort(bits & 127) << 7;  // 2 ops
    half converted = as_type<half>(raw);    // 1 op
    half signed_value = (bits & 128) ? -converted : converted;  // 2 ops
    return float(signed_value);  // 1 op
}
```

The scale is a single byte with only 256 possible values. The function is
called once per qdot per row per k-block. Per step: 40 layers × 4 rows × 4
k-blocks (O-proj) + 39 layers × 9 experts × 2 rows × 4 k-blocks (SwiGLU) =
~3,500 calls/step × ~5 ops = ~17,500 ALU instructions.

**Mechanism**: Precompute a 256-entry float LUT at init time and pass it as a
constant buffer to the kernel. Replace the function call with a single array
index:

```metal
// Current:
float scale = laguna_nvfp4_scale(gate_scale[0]);

// Proposed:
float scale = scale_lut[gate_scale[0]];
```

The LUT is built once in Swift at init:
```swift
var lut = [Float](repeating: 0, count: 256)
for b in 0..<256 {
    let sbits = UInt8(b)
    // Replicate the exact decode logic
    if b < 16 {
        let raw = UInt16(b) << 7
        lut[b] = Float(raw.halfValue)  // as_type<half> equivalent
    } else {
        let raw = UInt16(b & 127) << 7
        let converted = raw.halfValue
        lut[b] = (b & 128 != 0) ? -Float(converted) : Float(converted)
    }
}
```

The LUT is 256 × 4 bytes = 1 KB — fits entirely in the GPU's constant memory
or L1 cache. It's shared across all threadgroups and never changes.

**Reach**: O-proj (40 layers) + SwiGLU (39 layers × 9 experts) + dense layer.
~3,500 scale decode calls per step × ~5 ALU ops each = ~17,500 instructions
eliminated, replaced by ~3,500 memory loads (L1 cache hits, ~1 cycle each).

**Bit-exact**: YES — the LUT is precomputed with the exact same arithmetic as
the runtime function. Each of the 256 entries matches the function's output for
that byte value. The `as_type<half>` conversion is replicated in Swift using the
same bit pattern. Must verify the Swift half type produces identical results to
Metal's `as_type<half>` (it should, since both are IEEE 754 half precision).

**Expected impact**: 0.2–0.5% decode. The scale decode is a small fraction of
total instructions (~2%), but eliminating 17K ALU ops per step on the
instruction-bound M5 is non-trivial. The LUT approach also reduces function call
overhead (inlining is eliminated).

**Risk**: LOW. Bit-exact if the LUT is precomputed correctly. Requires adding a
new kernel input (the LUT buffer). The `DARKBLOOM_PACKED_SCALES` precedent shows
that adding a side buffer to a kernel is straightforward. Must verify the Swift
`Float(Half)` conversion matches Metal's `float(as_type<half>(raw))`.

**Conflict with in-flight**: NONE. #100 (prefetch) and #109 (simd_sum) touch the
O-proj body and epilogue. The scale decode is a separate inline function.
#116 (SwiGLU staging) touches the SwiGLU body. The LUT changes the function
call, not the body. All in-flight PRs are orthogonal.

**Byte budget**: Net DECREASE in kernel source (inline function removed,
replaced by 1 load). Small increase in Swift for LUT construction (~20 lines).

---

### 5. O-proj Block Size 512→1024 (Loop Iteration Halving)

**Target**: `lagunaGatedAffineOProjNVFP4Source` L4177
(`constexpr uint block_size = values_per_thread * 32`).

**Status**: The block-width-doubling mechanism was proposed for SwiGLU QMV
kernels in `RESEARCH_IDEAS_FRESH_20260805.md` #5 and
`RESEARCH_IDEAS_NEXT_WAVE_ASSIGNMENTS.md` B. This idea applies the same
mechanism to the O-proj kernel, which is a DIFFERENT kernel with its own
`block_size` constant. Not previously proposed for O-proj specifically.

**Problem**: The O-proj k-loop (L4202) iterates `in_vec_size / block_size`
times. `in_vec_size = heads * headDim` (L4170): 8192 for sliding (64 heads),
6144 for full (48 heads). With block_size=512, that's 16 iterations (sliding)
and 12 (full). Each iteration: input load (16 BF16 reads + 16 float converts),
4 rows of qdot (each with 2 code words × dequant + accumulate), scale load,
scale decode, pointer updates (ws, sc, xp, column). Doubling block_size to 1024
halves the loop to 8 iterations (sliding) and 6 (full).

**Mechanism**: Change `block_size` from `values_per_thread * 32` to
`values_per_thread * 64` (= 1024). The k-loop runs 8 iterations (sliding) and 6
(full) instead of 16 and 12. Each iteration processes 2× more input columns
but the qdot call count per iteration stays the same (4 rows × 2 code words =
8 qdot calls per k-block). The pointer updates (`ws += block_size / 8`,
`sc += block_size / group_size`, `xp += block_size`) advance twice as far per
iteration.

Register pressure: `x_thread[16]` stays at 16 (values_per_thread doesn't
change). The input load loop (`for i in 0..values_per_thread`) doesn't change.
Only the outer k-loop count changes. Register pressure is unchanged.

Per step: 30 sliding × 8 saved iterations + 10 full × 6 saved = 300 saved
iterations × 4 rows × ~10 overhead instructions (pointer updates, loop counter,
branch, scale load) = ~12,000 instructions/step eliminated.

**Bit-exact**: YES — same total computation, just fewer loop iterations. The
qdot calls process the same elements in the same order. The accumulation order
(`result[row] += scale * accum`) is unchanged because the scale is per-k-block
and the k-blocks are processed in the same order.

**Expected impact**: 0.1–0.5% decode. Loop overhead reduction. Eliminating
~12K loop-control instructions per step on the instruction-bound M5 is
non-trivial. Smaller than the SwiGLU version because the O-proj has fewer rows
per iteration (4 vs 2), but the loop iteration count is larger (16/12 vs 4).

**Risk**: LOW. Bit-exact, no register pressure change (values_per_thread
unchanged). Must verify the pointer arithmetic (`ws += block_size / 8`,
`sc += block_size / group_size`, `xp += block_size`) is correct with the new
block_size.

**Conflict with in-flight**: POTENTIAL with #100 (Edward's O-proj prefetch).
If #100 prefetches the next k-block's weight codes, the prefetch distance and
pattern are tied to block_size. Doubling block_size changes the prefetch
stride. Must rebase after #100 merges. NO conflict with #109 (epilogue).

---

### 6. fma() Intrinsic in Attention Output Accumulation

**Target**: Sliding attention L1567–1574, L1594–1601. Full attention L2055–2062,
L2076–2083. The `pair_o0/pair_o1` output MAC.

**Status**: `RESEARCH_IDEAS_2026-08-05.md` #2 proposes float4 vectorization of
the same code using `po0 = po0 * factor + pv * exp` (2 muls + 1 add = 3 vector
ops). This idea proposes using `metal::fma()` instead, reducing to 1 fma + 1
mul = 2 vector ops. A refinement of the existing idea, not a duplicate.

**Problem**: The attention output accumulation does 4 scalar FMAs per element
pair per position:

```metal
// L1567: pair_o0[0] = pair_o0[0] * pair_factor0 + pair_exp0 * pipe_va0;
```

This is `a * b + c * d` — a 2-multiply + 1-add pattern. With float4
vectorization (existing idea #2), this becomes `float4_o * float4_factor +
float4_v * float4_exp` = 2 vector muls + 1 vector add. Using `metal::fma()`
reduces this to 1 vector mul + 1 vector fma:

```metal
// Existing idea #2 (3 ops):
float4 po0 = float4(pair_o0[0..3]);
float4 pv = float4(pipe_va0..3);
po0 = po0 * pair_factor0 + pv * pair_exp0;

// Proposed fma() refinement (2 ops):
float4 pv_scaled = pv * pair_exp0;       // 1 vector mul
po0 = metal::fma(po0, pair_factor0, pv_scaled);  // 1 vector fma
```

`metal::fma(a, b, c)` computes `a * b + c` with a single fused
multiply-add instruction on Apple Silicon, which is 1 instruction instead of
2 (mul + add). The result may differ from separate mul+add by at most 1 ULP
(fused vs. unfused rounding).

Per iteration per position: 8 scalar FMAs → (existing #2) 3 vector ops →
(this idea) 2 vector ops. Per step: 40 layers × ~8 iterations × 2 positions
× 2 pairs × 4 elements × 1 instruction saved = ~5,120 instructions saved
relative to existing #2, or ~20,480 relative to scalar baseline.

**Bit-exact**: NO — `fma(a, b, c)` uses fused multiply-add which rounds once,
while `a * b + c` rounds twice. This is the same risk as dot4 (which also
uses FMA-like instructions). PR #94 and #114 showed dot() passes upstream
equivalence despite FMA rounding differences. LOW risk.

**Expected impact**: 0.1–0.3% decode (incremental over existing #2). The fma()
saves 1 instruction per element per position, which compounds across all 40
layers. Small but free if #2 is already being implemented.

**Risk**: LOW. Not bit-exact (fused vs. unfused), but same risk profile as #94
and #114 which both passed. Should be implemented as a refinement of #2, not
independently.

**Conflict with in-flight**: NONE. #94 changed the score computation. #112
changes the epilogue. This changes the output MAC, which is between the score
and the pointer advance. All orthogonal.

**Recommendation**: Bundle with `RESEARCH_IDEAS_2026-08-05.md` #2 (attention
output float4). Implement the float4 vectorization using `fma()` from the
start rather than as a separate pass.

---

### 7. SwiGLU Input Scatter-to-float4 (Register-to-Register)

**Target**: Shared SwiGLU QMV kernel L6491–6503 (input scatter),
`laguna_nvfp4_qdot_16` function L6460–6467 (input parameter),
`packedWordBody` L6431–6432 (input reads). Routed SwiGLU QMV kernels have
analogous patterns.

**Status**: FRESH — not in any prior research file. Note:
`NEGATIVE_RESULTS` #2 "threadgroup input staging" is about staging input to
threadgroup memory to reduce DRAM reads. This idea eliminates the
scatter-to-array pattern entirely, keeping input in registers. Different
mechanism.

**Problem**: The SwiGLU QMV kernel loads the 16-element input vector as 4
`vec<bfloat, 4>` loads, then scatters each element to a `thread float[16]` array:

```metal
// L6491: array declaration
thread float input_values[values_per_lane];  // values_per_lane = 16

// L6494-6503: load + scatter
const device vec<bfloat, 4>* input_vectors = ...;
for (uint i = 0; i < values_per_lane / 4; ++i) {
    const vec<bfloat, 4> values = input_vectors[i];
    input_values[4 * i] = values[0];      // store
    input_values[4 * i + 1] = values[1];   // store
    input_values[4 * i + 2] = values[2];  // store
    input_values[4 * i + 3] = values[3];  // store
}
```

Then the qdot function reads from the array:
```metal
// L6431-6432 (packedWordBody):
const float4 in_a = float4(input[0], input[1], input[2], input[3]);
const float4 in_b = float4(input[4], input[5], input[6], input[7]);
```

The scatter writes 16 floats to an array (potentially in memory if the compiler
doesn't keep the array in registers), then the qdot reads them back and
reconstructs float4. This is 16 store + 8 float4-constructor-load instructions
per block per row. The array may also prevent the compiler from keeping values
in registers.

**Mechanism**: Change the qdot function to accept `float4` by value instead of
`const thread float*`:

```metal
// Current:
static inline float laguna_nvfp4_qdot_16(
    const device uint8_t* weight,
    const thread float* input,  // pointer to array
    float scale) { ... }

// Proposed:
static inline float laguna_nvfp4_qdot_16(
    const device uint8_t* weight,
    float4 in_a, float4 in_b,  // by value, in registers
    float scale) {
    // packedWordBody uses in_a, in_b directly:
    // const float4 in_a = input[0..3];  ← eliminated
    // accum += dot(w_a, in_a) + dot(w_b, in_b);
}
```

The kernel loads:
```metal
// Proposed: direct float4 load, no scatter
float4 in_a, in_b;
for (uint i = 0; i < values_per_lane / 8; ++i) {
    const vec<bfloat, 4> va = input_vectors[2*i];
    const vec<bfloat, 4> vb = input_vectors[2*i + 1];
    in_a = float4(va);  // implicit bfloat→float conversion
    in_b = float4(vb);
    // pass to qdot directly
    gate_result[row] += laguna_nvfp4_qdot_16(gate_weight, in_a, in_b, scale);
}
```

This eliminates:
- 16 store-to-array instructions per block per row
- 8 float4-constructor-from-array-load instructions per block per row
- The `thread float[16]` array declaration (potentially frees 16 registers)

Per step: 39 layers × 9 experts × 2 rows × 4 k-blocks × (16 stores + 8 loads) =
~45,000 instructions eliminated. Plus potential register pressure reduction
from eliminating the array.

**Bit-exact**: YES — the `float4(vec<bfloat,4>)` conversion is element-wise
and identical to the current `input_values[4*i] = values[0]` followed by
`float4(input[0], input[1], ...)`. Each element undergoes the same
bfloat→float conversion. No reordering, no precision change.

**Expected impact**: 0.3–0.8% decode. The SwiGLU QMV kernel is the most
frequently dispatched kernel (39 layers × 9 experts = 351 dispatches/step).
Eliminating ~45K instructions per step on the instruction-bound M5 is
significant. The register pressure reduction may also improve occupancy.

**Risk**: LOW. Bit-exact, mechanical refactor. The only risk is whether the
compiler already optimizes the scatter-to-array + float4-reconstruction pattern
into register-to-register moves. If it does, the gain is zero. If it doesn't
(likely, given the array is declared `thread float[]` which may force stack
allocation), the gain is real. Must check the compiled assembly or benchmark
to confirm.

**Conflict with in-flight**: NONE with #100/#109 (O-proj). POTENTIAL with #116
(Alphonse's shared SwiGLU staging) — both touch the SwiGLU QMV kernel. #116
adds depth-1 staging of weights; this idea changes the input loading pattern.
Different sections (weights vs input), but must rebase after #116 to avoid
merge conflicts in the same kernel source string.

---

## Summary Table

| # | Idea | Target | Reach | Bit-exact? | Est. decode impact | Risk | In-flight conflict |
|---|------|--------|-------|------------|-------------------|------|-------------------|
| 1 | NVFP4 code pre-expansion side bank | O-proj L4133 + SwiGLU header L6348 | 40+39 layers | YES | 0.5–2.0% | LOW | POTENTIAL #100 |
| 2 | Gate-scale fold in O-proj | O-proj L4158–4168, L4228 | 40 layers | NO | 0.3–1.0% | MED | NONE |
| 3 | Fused pair_a+pair_b online softmax | Attention L1532–1601 | 40 layers | NO | 0.5–1.5% | MED | POTENTIAL #112 |
| 4 | Scale decode LUT | `laguna_nvfp4_scale` L6441 + O-proj L4101 | 40+39 layers | YES | 0.2–0.5% | LOW | NONE |
| 5 | O-proj block_size 512→1024 | O-proj L4177 | 40 layers | YES | 0.1–0.5% | LOW | POTENTIAL #100 |
| 6 | fma() in attention output | Attention L1567–1574 | 40 layers | NO | 0.1–0.3% | LOW | NONE |
| 7 | SwiGLU input scatter-to-float4 | SwiGLU L6491–6503, L6460 | 39×9 experts | YES | 0.3–0.8% | LOW | POTENTIAL #116 |

## Recommended Assignment Order

**Phase 1 — Bit-exact, LOW risk (merge first, compound freely)**:
1. **Idea #1** (Code pre-expansion) — LARGEST expected gain of the bit-exact
   set. Eliminates ~135K ALU instructions/step. Transform-side work, runtime
   source shrinks. Must rebase after #100.
2. **Idea #4** (Scale decode LUT) — Clean, independent, no in-flight conflict.
   Can start immediately. 1 KB LUT, trivial kernel change.
3. **Idea #7** (SwiGLU scatter-to-float4) — Mechanical refactor, bit-exact.
   Must rebase after #116.

**Phase 2 — Not bit-exact, needs equivalence test (merge individually)**:
4. **Idea #2** (Gate-scale fold) — Eliminates 38K ALU ops/step (19K muls + 19K
   BF16 rounds). Same risk profile as #114 (passed). No in-flight conflict.
5. **Idea #3** (Fused pair_a+pair_b) — Largest potential non-bit-exact gain.
   Must rebase after #112. Requires careful upstream equivalence testing.

**Phase 3 — Refinements**:
6. **Idea #6** (fma() in attention output) — Bundle with existing idea #2
   (float4 vectorization). 1 instruction savings per element.
7. **Idea #5** (O-proj block_size) — Small gain, same mechanism as existing
   SwiGLU block_width idea. Must rebase after #100.

## Composition Analysis

All 7 ideas target DIFFERENT mechanisms:
- #1: Eliminates bitwise extract (ALU) via transform-side precomputation
- #2: Eliminates per-element multiply+round via arithmetic reassociation
- #3: Reduces online softmax iterations via algorithmic restructuring
- #4: Eliminates scale decode ALU via lookup table
- #5: Reduces loop overhead via wider blocks
- #6: Reduces instruction count via fused multiply-add
- #7: Eliminates scatter/reload via register-to-register passing

**No executable code overlaps between these ideas.** #1 and #4 both touch the
scale/code path but at different levels (extract vs decode). #2 and #5 both
touch the O-proj but at different sections (loadInput vs block_size constant).
#3 and #6 both touch attention but at different stages (main loop vs output MAC).

**Instruction reduction compounds**: #1 (extract elimination) + #4 (scale LUT)
+ #7 (scatter elimination) all reduce ALU instructions in the MoE/O-proj
pipeline. #3 + #6 reduce instructions in the attention pipeline. On the
instruction-bound M5, these stack multiplicatively in the instruction-count
dimension.

## What I Did NOT Propose (and why)

- **Threadgroup input staging**: DEAD per `NEGATIVE_RESULTS` #2 — L1/SLC
  already handles the 2× read redundancy.
- **Register-resident scale pre-loading**: DEAD per `NEGATIVE_RESULTS` #1 —
  scales are not read redundantly; prefetch already implemented.
- **Texture-backed weight storage**: DEAD per `NEGATIVE_RESULTS` #4 — no
  editable texture binding path in MLX.
- **Router GEMV + top-8 dispatch fusion**: Already implemented
  (`lagunaResidualRMSNormRouter` + `lagunaDecodeRouterTop8`).
- **Expert streaming/caching**: Not a scored cost (all experts RAM-resident).
  Prohibited.
- **Speculative decoding / token caching**: Violates serial non-speculative
  protocol. Prohibited.
- **KV cache quantization**: Outside the accepted attention quantization
  envelope. Prohibited.
- **Prefill custom kernels**: Prefill uses MLX `_nax` kernels which are not
  participant-editable Metal sources. The only prefill lever (affine INT8
  O-proj extension) is already merged as #98.
- **Attention threadgroup reduction (16 simdgroups)**: Already analyzed in
  `RESEARCH_IDEAS_NEXT_WAVE_ASSIGNMENTS.md` C — HIGH risk, needs #112 to
  resolve first. Not re-proposed here.
