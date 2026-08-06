# Fresh Optimization Directions for Instruction-Bound M5 MoE Decode

**Date:** 2026-08-06
**Target:** Poolside Laguna XS 2.1 NVFP4, M5 Max 128GB (Apple GPU gen 17, instruction-bound ~89% GPU capacity)
**Score:** decode_speedup^0.75 * prefill_speedup^0.25, decode = 75% weight
**Status:** Research task only — no code implemented

---

## Context: What the Analysis Found

### Decode Kernel Instruction Breakdown (per thread, per decode step)

The M5 is **instruction-bound (ALU-bound)**, not bandwidth-bound. The MoE gate/up
kernel dominates decode at ~60% of MoE ALU work, the down kernel contributes ~40%.

**R1 Routed SwiGLU QMV (gate/up)** — 2048 threadgroups × 64 threads (2 simdgroups):
- 1 output row per simdgroup, 4 blocks × 2 qdots (gate+up) = **8 qdot_16 calls per thread**
- Per qdot_16 (current, with nibble extraction):
  - Nibble extraction: ~20 int ops per code word, 40 per qdot (**38% of qdot cost**)
  - half2->float2 conversion: ~4 ops
  - float4 construction (interleaved gather): ~8-16 shuffle ops
  - dot(float4,float4): 8 FMA
  - Scale computation: ~4 ops
  - **Total: ~70 ops/qdot, ~560 ops/thread (gate/up)**

**9-slot fused down+residual** — 512 threadgroups × 288 threads (9 simdgroups):
- 4 output rows per simdgroup, 1 qdot per row, no block loop (512 = 32x16)
- **4 qdot_16 calls per thread, ~280 ops/thread (down)**
- Plus threadgroup barrier + weighted reduction across 8 routed + 1 shared expert

**Total per MoE layer:** ~130M ALU ops (gate/up ~77M + down ~53M)
**39 MoE layers x 128 decode steps:** ~65B ALU ops

### What's Already Optimized (DO NOT repeat)
- Nibble split optimization (nibbleSplit=2, fewer int ops): **MERGED**
- Scale fold (2^22 into weight, deferred scale): **MERGED**
- Seed elision (first accum = instead of += 0): **MERGED**
- Scalar FMA -> dot(float4) vectorization: **MERGED**
- INT8 dot4 in QKV/O-proj: **MERGED**
- SwiGLU depth-1 weight prefetch: **MERGED**
- Attention joint max/rescale fusion: **CLOSED** (memory-bound)
- threadGroup 1024->128: **CLOSED** (false win)

### What's In-Flight (acknowledge, build on top of)
- **NVFP4 code pre-expansion** (pre-expand 4-bit codes to half2 at transform time): M5 validating
- **Gate-scale fold in O-proj**: implementing
- **Scale decode LUT** (256-entry constant LUT): implementing
- **Fused down+residual weight staging**: just assigned

---

## Ranked Hypotheses (FRESH, post-pre-expansion focused)

### H1: max_total_threads_per_threadgroup Attribute + Register Pressure Audit
**Estimated impact:** 5-15% decode speedup
**Risk:** LOW
**Effort:** LOW (1 flag + benchmark sweep)

**Hypothesis:** The Metal compiler's register allocator is suboptimal for the
current kernels because max_total_threads_per_threadgroup is not set. Apple's
own guidance (Tech Talks 10580, WWDC20) states this attribute lets the compiler
spill registers more efficiently and optimize register allocation at pipeline
creation time. Without it, LLVM IR passes "largely ignore register pressure"
(Apple LLVM GPU Compiler, LLVM Dev Meeting 2017), potentially reducing
occupancy below what the kernel's register count could support.

The MLX community (discussion #3801) measured that M=1 decode is
**"row-starved, not bandwidth-bound"** -- a 2048-row contiguous qmv takes 0.24ms
vs ~8us at peak bandwidth, a ~30x latency/occupancy floor. Getting more useful
rows in flight per dispatch is the primary lever, and occupancy is directly
controlled by register pressure.

**Implementation sketch:**
1. Add `[[max_total_threads_per_threadgroup(64)]]` to the R1 gate/up kernel
   (currently 64 threads). Add `[[max_total_threads_per_threadgroup(288)]]` to
   the 9-slot down kernel.
2. Audit register pressure: the R1 kernel has ~30 live registers (16 input +
   2 accum + 4 codes + 4 scales + misc). With 128 regs/thread on Apple GPU, this
   allows 4 threadgroups per SIMD. Verify the compiler isn't over-allocating.
3. If register pressure is high, restructure the loop to reduce live values
   (e.g., process gate and up sequentially instead of maintaining both
   accumulators simultaneously -- halves accumulator registers at the cost of
   reloading input, but input is thread-local and already in registers).
4. Benchmark with `./benchmark.sh --local-iterate` on M5.

**Falsifiability:** If setting the attribute and auditing registers produces no
measurable decode improvement (<1%), the kernel is already at optimal occupancy
and register pressure is not the bottleneck.

**Key references:**
- Apple Tech Talks 10580: max_total_threads_per_threadgroup for efficient spilling
- Apple LLVM GPU Compiler (LLVM Dev 2017): "LLVM IR passes largely ignore register pressure"
- MLX discussion #3801: "row-starved, not bandwidth-bound" at M=1

---

### H2: Pre-Interleaved Weight Layout (Transform-Time Transpose to half4 Groups)
**Estimated impact:** 6-10% post-expansion gate/up kernel reduction; 3-5% total decode
**Risk:** LOW (transform-only change, runtime kernel simplification)
**Effort:** MEDIUM (transform code + kernel weight-load pattern change)

**Hypothesis:** After pre-expansion (in-flight), the qdot loads half2 values and
constructs float4 by gathering .x from 4 separate float2s:

```metal
// Current post-expansion pattern (per code word):
float2 v0 = float2(expanded[0]) * scale;  // load + cvt + mul
float2 v1 = float2(expanded[1]) * scale;  // load + cvt + mul
float2 v2 = float2(expanded[2]) * scale;  // load + cvt + mul
float2 v3 = float2(expanded[3]) * scale;  // load + cvt + mul
float4 w_a = float4(v0.x, v1.x, v2.x, v3.x);  // <- interleaved gather (shuffle)
float4 w_b = float4(v0.y, v1.y, v2.y, v3.y);  // <- interleaved gather (shuffle)
```

The interleaved gather (extracting .x from 4 float2s into one float4, .y into
another) is a register transpose that may cost 8-16 shuffle instructions per
code word. If instead the transform pre-interleaves the expanded weights into
two half4 groups:

```metal
// Pre-interleaved layout:
half4 w_a_half = expanded_a[code_word];  // already {v0.x, v1.x, v2.x, v3.x}
half4 w_b_half = expanded_b[code_word];  // already {v0.y, v1.y, v2.y, v3.y}
float4 w_a = float4(w_a_half) * scale;    // 1 load + 2 cvt + 4 mul
float4 w_b = float4(w_b_half) * scale;    // 1 load + 2 cvt + 4 mul
```

This eliminates the interleaved float4 construction entirely. The FMA chain
`dot(w_a, in_a) + dot(w_b, in_b)` is **unchanged** -- same operands, same order,
same rounding. Only the weight layout differs.

**Per-qdot savings:** 4 loads (half4) vs 8 loads (half2) = -4 ops; 0 shuffle vs
8-16 shuffle = -8 to -16 ops. Total: **12-20 ops/qdot saved** (post-expansion).
At 8 qdots/thread: **96-160 ops/thread saved**.

**Implementation sketch:**
1. In Sources/MLXFastTransform/, add a transform pass that, for each group of
   16 NVFP4 values (8 half2 pairs), transposes into 2 half4 vectors: all .x
   components contiguous, then all .y components contiguous.
2. Store the transposed layout alongside (or replacing) the expanded half2
   layout. Memory cost is identical (32 bytes per 16 values either way).
3. Modify the R1 gate/up and down kernel weight-load patterns to load half4
   directly from the transposed layout.
4. The qdot_16 function signature changes from taking uint2 codes to taking
   two half4 (or the expanded equivalent).
5. Verify exactness via `research/run_upstream_equivalence.sh`.

**Falsifiability:** If the Metal compiler already optimizes away the float4
construction from interleaved float2 components (register coalescing), the
savings drop to ~4 ops/qdot (load count only) and the impact is <2%.

**Key references:**
- QServe (arXiv:2405.04532): "compute-aware weight reordering" for sequential register access
- Marlin (IST-DASLab): "weights reshuffled offline into ideal access patterns"
- WWDC16: vectorization of neighboring loads; compiler tries to coalesce

---

### H3: Fused Gate/Up + Down Single-Dispatch Kernel
**Estimated impact:** 2-5% decode (dispatch elimination + input sharing)
**Risk:** MEDIUM (kernel complexity, occupancy concerns)
**Effort:** HIGH (new fused kernel)

**Hypothesis:** Each MoE layer currently dispatches 3-4 kernels for the MoE
block: (1) routed SwiGLU QMV, (2) shared SwiGLU QMV, (3) 9-slot fused
down+residual. The routed and shared gate/up dispatches share the same input
activation vector (the post-attention RMSNorm output), but each loads it
independently. Fusing the routed and shared gate/up into a single dispatch
would:

- Eliminate 1 kernel dispatch per layer (39 layers x 128 steps = 4992 fewer
  dispatches). At ~10-20us dispatch overhead on Apple GPU: 50-100ms over the
  full decode.
- Share the input activation load across routed and shared experts (currently
  loaded twice -- once per dispatch).
- Potentially overlap routed and shared computation within the same
  threadgroup wave.

The MLX community (omlx issue #2238) demonstrated that fusing gate+up
gather_qmm is **bit-exact** and yields **+6.6-7.6% decode for free**. The
ONNX Runtime WebGPU QMoE fusion reduced 17 dispatches to 5, achieving ~21%
throughput improvement.

**Implementation sketch:**
1. Create a combined kernel that takes routed expert indices, routed weights,
   shared expert weights, and the input activation.
2. Threadgroup grid: 8 routed expert slots + 1 shared slot = 9 slots, each
   computing 512/2 = 256 rows (gate/up), producing the activated output.
3. The shared expert's gate/up uses the same input but different weights -- load
   input once into threadgroup memory, broadcast to all 9 slots.
4. The activated output (routed + shared) is written to an intermediate buffer
   for the down kernel (can't fully fuse gate/up+down because the down kernel
   needs all 9 activated outputs before reducing).
5. Alternatively: fuse ALL into one mega-kernel with threadgroup memory
   staging the activated output. This eliminates the intermediate buffer
   write/read but increases threadgroup memory pressure (9 x 512 x 2 bytes =
   9KB threadgroup memory).

**Falsifiability:** If the fused kernel's increased register pressure or
threadgroup memory usage reduces occupancy below the dispatch savings, net
decode time will not improve. Test with --local-iterate.

**Key references:**
- omlx issue #2238: fused gate+up gather_qmm, +6.6-7.6% decode, bit-exact
- ONNX Runtime PR #27998: QMoE fusion 17->5 dispatches, ~21% throughput
- FlashFormer (arXiv:2505.22758): whole-model kernel for batch-1 inference
- TritonMoE (arXiv:2605.23911): fused gate+up, 35% memory traffic reduction

---

### H4: Thread-Local Array -> Register-Resident Values
**Estimated impact:** 0-10% (depends on whether compiler already optimizes)
**Risk:** LOW
**Effort:** LOW-MEDIUM (restructure qdot to avoid thread float[16])

**Hypothesis:** The current qdot path uses a `thread float input_values[16]`
array that is filled from vec<bfloat,4> loads and then passed by pointer to
laguna_nvfp4_qdot_codes_16. Apple's WWDC16 guidance explicitly warns that
**"dynamically indexed non-constant stack arrays force stack spills"** -- even
though the indices are compile-time constant in the unrolled loop, the Metal
compiler may not recognize this and may spill the 16-float array to the stack
(thread-local memory), converting every access from a register read to a
memory load.

With 8 qdot calls per thread, each reading 16 values, that's 128 potential
stack reads. If the compiler spills, eliminating the stack array saves 128
memory operations per thread.

**Implementation sketch:**
1. Replace the `thread float input_values[16]` with 4 explicit float4
   variables:
   ```metal
   float4 in0 = float4(input_vectors[0]);  // unpack vec<bfloat,4>
   float4 in1 = float4(input_vectors[1]);
   float4 in2 = float4(input_vectors[2]);
   float4 in3 = float4(input_vectors[3]);
   ```
2. Restructure laguna_nvfp4_qdot_codes_16 to take float4 in0, float4 in1,
   float4 in2, float4 in3 by value instead of const thread float*.
3. The qdot body accesses in0.x, in0.y, etc. -- guaranteed register-resident.
4. This also enables the compiler to see the float4 input structure and
   potentially fuse the input construction with the dot product.
5. Verify the generated AIR/IR to confirm the array is no longer on stack.

**Falsifiability:** Inspect the compiled Metal IR (via xcrun -sdk macosx metal
-emit-ir or air-disassemble) for stack spills. If no spills exist, this change
has zero impact. If spills exist and are eliminated, measure the delta.

**Key references:**
- WWDC16 "What's New in Metal": "Avoid dynamically indexed non-constant stack
  arrays -- forces stack spills"
- WWDC20: register pressure management via 16-bit types
- Software-Directed Register File Utilization (DOI:10.1145/3243905): 12%
  speedup from early register deallocation

---

### H5: Threadgroup Input Sharing Across Simdgroups (Eliminate 2x Input Unpack)
**Estimated impact:** 3-5% gate/up kernel
**Risk:** LOW-MEDIUM (adds barrier + threadgroup memory)
**Effort:** MEDIUM

**Hypothesis:** In the R1 gate/up kernel, the threadgroup has 2 simdgroups (64
threads). Both simdgroups compute different output rows but load the **same**
input activation vector. Each thread loads 16 bfloat values and unpacks them
to float -- 16 conversion ops per thread per block. With 2 simdgroups, every
input value is unpacked twice (once per simdgroup).

Total redundant unpack ops: 32 threads x 16 values x 4 blocks = 2048 unpack
ops per threadgroup, of which 1024 are redundant. With 2048 threadgroups:
**2.1M redundant unpack operations**.

Loading the input into threadgroup memory once (by simdgroup 0) and having
both simdgroups read from threadgroup memory eliminates the redundant unpack.
The device memory load is already cached (both simdgroups read the same cache
line), so the savings are in ALU (bfloat->float conversion), not memory.

**Implementation sketch:**
1. Before the block loop, simdgroup 0 loads the full 2048-value input into
   threadgroup memory as float (2048 x 4 = 8KB -- within Apple GPU's 32KB
   threadgroup memory limit, but check against current usage).
2. threadgroup_barrier(mem_flags::mem_threadgroup).
3. Both simdgroups read input from threadgroup memory (no conversion needed --
   already float).
4. The bfloat->float conversion happens once (in simdgroup 0's load), not twice.
5. Alternative: load as bfloat into threadgroup memory (2KB) and convert on
   read -- smaller threadgroup memory but doesn't save the conversion ops.

**Falsifiability:** If the bfloat->float conversion is already free (the Apple
GPU handles bfloat as a native type with zero-cost conversion), the savings are
zero. If conversion costs 1 ALU op per value, savings = ~2.1M ops = ~2.7% of
gate/up ALU. The threadgroup barrier adds latency (~100-200 cycles); with 2048
threadgroups, the barrier cost must be < the unpack savings.

**Key references:**
- FairyFuse (arXiv:2604.20913): "input vector reuse -- load activation once,
  share across all sub-GEMVs"
- TritonMoE: "shares input activation across both SwiGLU projections"

---

### H6: Instruction Diversity -- Interleave Dequant with FMA After Pre-Expansion
**Estimated impact:** 0-5% (speculative, pipeline utilization)
**Risk:** LOW
**Effort:** LOW-MEDIUM (loop restructuring)

**Hypothesis:** After pre-expansion eliminates the nibble extraction (integer
ops), the qdot inner loop becomes dominated by a single instruction type: float
FMA. Research by Minglun Gong shows that **low instruction diversity causes
pipeline stalls** -- a "Rebalanced Kernel" approach improved throughput by 24%
from diversity alone. On Apple GPU's shader cores, the ALU pipeline may stall
when fed a monotonous stream of same-type instructions.

The current code already interleaves int ops (nibble extraction) with float
ops (FMA), providing natural diversity. After pre-expansion, this diversity
vanishes. Restoring it by interleaving the scale multiplication (currently
deferred to epilogue) with the FMA chain, or by interleaving weight loads
with FMA, could improve pipeline utilization.

**Implementation sketch:**
1. After pre-expansion, instead of loading all 4 half4 weights, converting all
   to float4, then doing all 4 dot products, interleave:
   ```
   load w_a0; convert; fma(accum, w_a0, in_a0)  // load+cvt+fma interleaved
   load w_b0; convert; fma(accum, w_b0, in_b0)
   load w_a1; convert; fma(accum, w_a1, in_a1)
   load w_b1; convert; fma(accum, w_b1, in_b1)
   ```
   vs current:
   ```
   load all 4; convert all 4; dot all 4
   ```
2. The interleaving gives the load and convert units time to work while the
   FMA unit is busy, improving pipeline overlap.
3. This is the same principle as the depth-1 weight prefetch already merged
   for SwiGLU, but applied to the load-convert-FMA pipeline within the qdot.

**Falsifiability:** If the Apple GPU's scheduler already interleaves
instructions optimally (out-of-order issue within a thread), manual interleaving
has no effect. Benchmark with and without interleaving on M5.

**Key references:**
- Minglun Gong: "Low instruction diversity causes pipeline stalls; 24%
  improvement from diversity alone"
- Apple GPU docs: 4 schedulers each dispatch one instruction from one SIMD per
  cycle -- instruction mix affects throughput

---

### H7: Scale-Deferred Accumulation in Half2 Space (Post-Expansion)
**Estimated impact:** 5-8% post-expansion (halves FMA count if half2 FMA is 1 instruction)
**Risk:** HIGH (precision change, may break exactness)
**Effort:** MEDIUM

**Hypothesis:** After pre-expansion, the qdot converts half2->float2, multiplies
by scale, constructs float4, and does float4 dot (4 FMA per dot). On Apple GPU,
**FP16 FMA operates on half2 (2 values per instruction)**, giving 2x throughput
vs FP32 FMA (per Apple GPU ISA docs: F16 FMA has 0.56cy dependency vs 0.84cy
for F32; minimum occupancy FMA 3.9cy F16 vs 6.6cy F32).

If the dot product is done in half2 space instead of float:
```metal
half2 w = expanded[i];  // already scaled (pre-expansion + scale fold)
half2 in = half2(input_pair);  // BF16 -> half (exact for representable values)
half2 prod = fma(w, in, half2_accum);  // 1 instruction, 2 FMA
```

This halves the FMA instruction count: 4 half2 FMA per code word instead of 8
float FMA. However, half2 FMA has less precision than float FMA (10-bit mantissa
vs 23-bit). The accumulation of 16 values in half2 might lose precision and
change the greedy token.

**The exactness concern:** The current code accumulates in float (23-bit
mantissa) for good reason. Half2 accumulation of 16 values, each with 4-bit
weight precision, might be acceptable IF the input is BF16 (also limited
precision). But the competition requires exact greedy token match -- any
precision change that flips a near-tie argmax fails.

**Implementation sketch:**
1. Pre-expand weights to half2 with scale already folded (so weights are
   final FP16 values, no runtime scale needed).
2. Convert input BF16 to half (exact for values within half range).
3. Accumulate using half2 FMA in the inner loop.
4. Convert the half2 accumulator to float at the epilogue for the simd_sum
   reduction (which must stay in float for cross-lane reduction).
5. Run the 64-step drift tripwire and 512-token teacher-forced cases to
   verify exactness.

**Falsifiability:** If any checked greedy token differs from the baseline,
this approach fails the exactness gate. The probability of success depends on
whether the BF16 input precision dominates the half2 accumulation error.
Given that NVFP4 weights are only 4-bit (very coarse), the half2 accumulation
error might be smaller than the weight quantization error -- but this is not
guaranteed for adversarial inputs.

**Key references:**
- Apple GPU ISA (dougallj.github.io/applegpu): F16 FMA 2x throughput vs F32
- WWDC20: "Use half everywhere possible -- halves register usage, faster ALU"
- MixPE (arXiv:2411.16158): mixed-precision GEMM then per-group dequant after

---

### H8: Eliminate is_shared Branch in 9-Slot Kernel
**Estimated impact:** 1-2% (eliminate divergent branch in hot kernel)
**Risk:** LOW
**Effort:** LOW

**Hypothesis:** The 9-slot down+residual kernel has a compile-time constant
branch (`lagunaSharedFirstDownOrderEnabled`) that selects between two input
orderings. This branch generates two kernel variants (different names), but
if both are compiled and the selection happens at kernel creation time, there
may be a residual `is_shared` branch inside the kernel body:

```metal
bool is_shared = slot == shared_slot;
uint expert = is_shared ? 0 : uint(indices[slot]);
const device bfloat* expert_input = is_shared
    ? shared_activated
    : routed_activated + slot * input_width;
```

This `is_shared` branch is uniform within a simdgroup (all 32 threads in a
simdgroup have the same slot), so it shouldn't cause warp divergence. But the
ternary expressions may generate extra move instructions or prevent the
compiler from optimizing the address computation.

If the shared expert is always in slot 8 (the last simdgroup), the compiler
can statically resolve `is_shared = (slot == 8)` and eliminate the branch.
But if the Metal compiler doesn't do this, the ternary generates a select
instruction per access.

**Implementation sketch:**
1. Split the 9-slot kernel into two separate kernels: one for the 8 routed
   experts (no is_shared branch) and one for the shared expert. The shared
   kernel is trivial (1 simdgroup, 4 rows). The routed kernel has 8 simdgroups.
2. Dispatch both in sequence (2 dispatches instead of 1), but the routed
   kernel's 8 simdgroups run without any branch.
3. The reduction still needs both results -- use a small threadgroup-memory
   kernel or atomics, or keep the current fused approach but with the shared
   expert handled by a separate code path (no branch).
4. Alternatively: template the kernel on is_shared and instantiate both,
   letting the compiler eliminate the dead branch.

**Falsifiability:** If the is_shared branch is already optimized away by the
compiler (uniform branch elimination), this has zero impact. Inspect the
compiled IR for select instructions.

---

## Summary Ranking

| # | Hypothesis | Impact | Risk | Effort | Post-Expansion? |
|---|-----------|--------|------|--------|-----------------|
| H1 | max_total_threads + register audit | 5-15% | LOW | LOW | Independent |
| H2 | Pre-interleaved weight layout | 6-10% gate/up | LOW | MEDIUM | Yes (builds on) |
| H3 | Fused gate/up+down dispatch | 2-5% | MEDIUM | HIGH | Independent |
| H4 | Thread-local array -> registers | 0-10% | LOW | LOW-MED | Yes (simpler) |
| H5 | Threadgroup input sharing | 3-5% | LOW-MED | MEDIUM | Independent |
| H6 | Instruction diversity | 0-5% | LOW | LOW-MED | Yes (after) |
| H7 | Half2 FMA accumulation | 5-8% | HIGH | MEDIUM | Yes (enables) |
| H8 | Eliminate is_shared branch | 1-2% | LOW | LOW | Independent |

**Recommended first experiments:** H1 (quick test, high impact), H2 (builds on
in-flight pre-expansion), H4 (quick test, may be free win).

**Key insight from literature:** The MLX community's finding that M=1 decode
is "row-starved, not bandwidth-bound" means **occupancy (H1) and dispatch
reduction (H3) may matter more than per-thread instruction count** -- even on
an instruction-bound GPU, if there aren't enough rows in flight to keep the ALU
pipeline fed, reducing instructions per row doesn't help. H1 should be tested
first because it's the cheapest to implement and directly addresses the
occupancy bottleneck.

**Caution on H7:** The half2 FMA approach (H7) is the highest-risk hypothesis
because it changes numerical precision. It should only be attempted after all
exactness-preserving optimizations are exhausted, and with the understanding
that it will likely fail the exactness gate unless the model's argmax margins
are wide enough to absorb the precision change.

---

## Literature Evidence Base

The following sources informed this analysis (searched via Exa general-web and
research-publications modes):

**Apple Silicon / Metal:**
- Apple Tech Talks 10580, WWDC20/WWDC16: max_total_threads_per_threadgroup,
  register pressure, constant address space, stack array spills
- Apple LLVM GPU Compiler (LLVM Dev 2017): "LLVM IR passes largely ignore
  register pressure"
- dougallj.github.io/applegpu: Apple GPU ISA (128 regs/thread, 32-wide SIMD,
  F16/F32 throughput)
- Rigel (arXiv:2606.12765): M4 Metal 4.1 fp4/fp8 matmul2d is emulated, not
  hardware-accelerated

**MoE / Kernel Fusion:**
- MLX discussion #3801: "row-starved, not bandwidth-bound" at M=1; 30x
  latency/occupancy floor
- omlx issue #2238: fused gate+up gather_qmm, +6.6-7.6% decode, bit-exact
- ONNX Runtime PR #27998: QMoE fusion 17->5 dispatches, ~21% throughput
- FlashFormer (arXiv:2505.22758): whole-model kernel for batch-1 inference
- TritonMoE (arXiv:2605.23911): fused gate+up, 35% memory traffic reduction
- FairyFuse (arXiv:2604.20913): input vector reuse across sub-GEMVs

**Quantization / Dequant:**
- Fast NF4 (arXiv:2604.02556): bit manipulation dequant, 71% instruction
  reduction, 2.0-2.2x kernel speedup
- T-MAN (arXiv:2511.11248): LUT-based GEMV with baked scales
- LiquidGEMM (arXiv:2509.01229): epilogue scale deferral
- QServe (arXiv:2405.04532): compute-aware weight reordering
- MixPE (arXiv:2411.16158): shift&add for FP4 multiplication
- Marlin (IST-DASLab): offline weight/scale reshuffling

**Register / Occupancy:**
- Shobaki et al. (DOI:10.1145/3368826.3377918): occupancy primary objective
- Software-Directed Register File (DOI:10.1145/3243905): 12% speedup from
  register deallocation
- Minglun Gong: 24% improvement from instruction diversity alone
