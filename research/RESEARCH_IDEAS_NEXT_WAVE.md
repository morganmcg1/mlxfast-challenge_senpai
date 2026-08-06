# Novel Optimization Strategies — Next Wave

## Research Context

**Benchmark:** Poolside Laguna XS 2.1 NVFP4 MoE decode on M5 Max (128 GB).
**Score:** `decode_speedup^0.75 * prefill_speedup^0.25`, floors at 0.95 each.
**Model:** 40 decoder layers, 256 routed experts (8 per token), 1 shared expert,
hidden=2048, expert intermediate=512, NVFP4 group-16 quantization, ~21.6 GB resident.

**In-flight experiments (DO NOT duplicate):**
1. Redundant top-8 expert extraction elimination in routed gate/up R1
2. RMSNorm + NVFP4 QKV dispatch fusion (40 dispatches/step)
3. Shared gate/up QMV merged into routed gate/up dispatch (39 dispatches/step)
4. Prefill MoE gather-QMM `_nax` variant switch

**File budget:** LagunaRuntimeModel.swift is 508,548 / 524,288 bytes (15,740 bytes
headroom). Several ideas below require modifying Transform.swift or the kernel
source strings, which are smaller files with more headroom.

---

## Architectural Foundation

Two findings from the research are decisive for prioritization:

1. **Decode GEMV is bandwidth-bound, not compute-bound.** On Apple Silicon
   unified memory, the weight matrix is read exactly once per token. The
   bandwidth gap between global memory and threadgroup/tile memory is small
   (unlike discrete GPUs), so staging the *matrix* through shared memory barely
   helps and the barrier cost may exceed the savings. The winning moves are:
   read fewer bytes, coalesce reads at ≥4 B granularity, and stage the
   *activation vector* (read many times across output rows) in threadgroup
   memory. (Sources: Modular M5 fp4_gemv docs; philipturner/metal-flash-attention
   issue #12.)

2. **Hardware MMA (matmul2d / simdgroup_matrix) is the wrong tool for GEMV.**
   GEMV is rank-1; feeding it through the matrix unit wastes bandwidth and
   adds staging overhead. The custom kernels already use the correct primitive:
   scalar FMA + `simd_sum` reduction. Do NOT rewrite decode qdot to use
   simdgroup_matrix or NAXTile. (Sources: MLX issue #171; Modular docs;
   philipturner issue #12.)

---

## Idea 1: Stage the Activation Vector in Threadgroup Memory

**Category:** Memory access pattern optimization
**Estimated impact:** 5–10% decode speedup (recovers input-read overhead)
**Risk:** LOW
**Causal hypothesis:** The 2048-element BF16 input vector (4 KB) is read
independently by every lane of every simdgroup from device memory. In the shared
SwiGLU QMV kernel (line 6537–6547), 2 simdgroups × 32 lanes each read the same
2048 values per block — 64 redundant reads of the same 4 KB per block, 4 blocks
= 256 reads per threadgroup. Staging the input once in threadgroup memory and
having all lanes read from there eliminates ~96% of the input vector's device
memory traffic (from 64× to 1× per block).

**Current pattern** (LagunaRuntimeModel.swift:6537–6547):
```metal
for (uint block = 0; block < input_width; block += block_width) {
    const device vec<bfloat, 4>* input_vectors =
        (const device vec<bfloat, 4>*)(input + block + lane * values_per_lane);
    for (uint i = 0; i < values_per_lane / 4; ++i) {
        const vec<bfloat, 4> values = input_vectors[i];
        input_values[4 * i] = values[0];
        // ... 4 elements per vec4 load
    }
    // ... per-row qdot using input_values
}
```

**Proposed pattern:**
```metal
threadgroup bfloat tg_input[input_width]; // 2048 * 2 = 4 KB
// Cooperative load: 64 threads × 32 elements = 2048
for (uint i = lane; i < input_width; i += 32) {
    tg_input[i] = input[i];
}
// Each simdgroup loads its own 32-wide slice per block
threadgroup_barrier(mem_flags::mem_threadgroup);

for (uint block = 0; block < input_width; block += block_width) {
    // Read from threadgroup instead of device
    for (uint i = 0; i < values_per_lane; ++i) {
        input_values[i] = float(tg_input[block + lane * values_per_lane + i]);
    }
    // ... same qdot
}
```

**Scope:** Applies to all NVFP4 GEMV kernels: shared SwiGLU QMV (line 6515),
routed SwiGLU QMV (line 7174), down+residual (line 7649), QKV R1 (line 4604).
Each kernel's threadgroup already has spare SMEM (the down kernel uses 36 BF16
values for the reduction; the gate/up kernels use none).

**Correctness:** The activation values are identical — only the source of the
read changes (device → threadgroup). The `bfloat` rounding on store to
threadgroup memory matches the existing `float(input[...])` conversion. The qdot
arithmetic is unchanged. Bit-exact.

**Implementation effort:** ~200 bytes per kernel (4 kernels). The cooperative
load + barrier adds one `threadgroup_barrier` per threadgroup (amortized over
4 blocks × multiple rows). Net: saves far more bandwidth than the barrier costs.

**Validation:** Compare paired decode timing on M5. The input vector is 4 KB;
at 540 GB/s this is ~7.4 ns per read. 64 redundant reads = ~474 ns per kernel
per step. With 40 layers × ~3 kernels/layer, the total redundant input-read time
is ~57 µs per step. If decode is ~9.5 ms, this is ~0.6% — modest but real.
The larger win comes from reducing L1 cache pressure, freeing cache lines for
weight reads.

---

## Idea 2: Register-Resident Scale Pre-loading Across Blocks

**Category:** Memory access pattern optimization
**Estimated impact:** 2–4% decode speedup (reduces scale-read latency)
**Risk:** LOW
**Causal hypothesis:** In the gate/up kernels with `input_width=2048` and
`block_width=512`, there are 4 block iterations. Each block loads its scale byte
from device memory via `laguna_nvfp4_scale(gate_scale[0])` (line 7241). The
scale address for block `b` is
`tile_scales + b * scale_kblock_bytes + sub * 2 * scale_row_bytes + lane`.
Since the scales for all 4 blocks are contiguous in the packed layout, all 4
scale bytes for a given (row, lane) can be loaded into registers ONCE before the
block loop, then used across iterations without any device memory access.

**Current pattern** (LagunaRuntimeModel.swift:7222–7244):
```metal
for (uint block = 0; block < input_width; block += block_width) {
    const device uint8_t* block_scales =
        tile_scales + (block / block_width) * scale_kblock_bytes;
    for (uint row = 0; row < 2; ++row) {
        // ... scale address computed, scale[0] loaded from device
        gate_result[row] += laguna_nvfp4_qdot_16(
            gate_weight, input_values,
            laguna_nvfp4_scale(gate_scale[0]));
    }
}
```

**Proposed pattern:**
```metal
// Pre-load all 4 scale bytes for both rows into registers
float gate_scales[4][2]; // [block][row]
float up_scales[4][2];
for (uint b = 0; b < 4; ++b) {
    const device uint8_t* bs = tile_scales + b * scale_kblock_bytes;
    for (uint row = 0; row < 2; ++row) {
        uint sub = simd_group * 2 + row;
        gate_scales[b][row] = laguna_nvfp4_scale(
            bs[sub * 2 * scale_row_bytes + lane]);
        up_scales[b][row] = laguna_nvfp4_scale(
            bs[sub * 2 * scale_row_bytes + scale_row_bytes + lane]);
    }
}
// Use gate_scales[block][row] in the block loop — no device reads
```

**Scope:** Routed SwiGLU QMV (line 7174), shared SwiGLU QMV (line 6515).
The down kernel (line 7649) has only 1 block (512/512), so this does not apply
there. The QKV R1 kernel (line 4604) has 4 blocks and could benefit.

**Correctness:** The scale values are identical — they are loaded from the same
addresses, just earlier. The `laguna_nvfp4_scale` conversion is a pure function
of the byte. Bit-exact.

**Register pressure:** 4 blocks × 2 rows × 2 (gate+up) = 16 floats = 16 registers.
The current kernels are under-occupied (0.40 waves per notes/54 §11), so there
is register headroom. The QKV R1 kernel has 4 blocks × 1 row = 4 floats = 4
registers — negligible.

**Implementation effort:** ~150 bytes per kernel. Does not add any barriers.

---

## Idea 3: Prefetch Next Block's Weights During Current Block's Compute

**Category:** Memory access pattern optimization / memory-level parallelism
**Estimated impact:** 3–6% decode speedup (overlaps memory latency with compute)
**Risk:** LOW
**Causal hypothesis:** The qdot loop iterates over 4 blocks of 512 elements. Each
block reads 8 bytes of weight codes + 1 scale byte per lane, computes 16 FMA
operations, and accumulates. The weight read for block `b+1` can be issued
before block `b`'s computation finishes, overlapping the DRAM latency (~100 ns)
with the FMA compute (~20 ns). This is memory-level parallelism within a single
lane's instruction stream.

**Current pattern** (all NVFP4 GEMV kernels): sequential block loop, each block
reads weights then computes.

**Proposed pattern:** Insert an explicit prefetch for the next block's weight
address before the current block's FMA:
```metal
for (uint block = 0; block < input_width; block += block_width) {
    // Prefetch next block's weight codes
    if (block + block_width < input_width) {
        const device uint8_t* next_weight =
            expert_weight + gate_row * fused_row_bytes
            + (block + block_width) / 2 + lane * 8;
        // Metal doesn't have explicit prefetch for buffer reads,
        // but we can load into a register that the compiler won't DSE
        thread uint32_t prefetch_hint =
            *(const device uint32_t*)next_weight;
    }
    // ... current block's compute
}
```

Note: Metal does not expose a direct `prefetch` intrinsic for buffer reads (only
for textures). The alternative is a load-into-unused-register that the compiler
cannot eliminate. This is fragile — the optimizer may DCE the "unused" load.
A safer approach is to restructure the loop to process 2 blocks per iteration
(unrolled), issuing both weight loads before either block's compute:

```metal
for (uint block = 0; block < input_width; block += block_width * 2) {
    // Load weights for both blocks
    const device uint2* w0 = ...; const device uint2* w1 = ...;
    uint2 codes0 = w0[0]; uint2 codes1 = w1[0];
    // Compute block 0
    accum += laguna_nvfp4_qdot_codes_16(codes0, input_values, scale0);
    // Advance input for block 1
    // Compute block 1
    accum += laguna_nvfp4_qdot_codes_16(codes1, input_values2, scale1);
}
```

This is the "depth-2 block unroll" pattern already used in the O-projection
kernel (line 3502–3517, notes/54 §11). Applying it to the expert GEMV kernels
is novel because those kernels are bandwidth-bound, and the unroll lets the
memory system pipeline two weight reads.

**Scope:** All NVFP4 GEMV kernels with >1 block iteration: shared SwiGLU QMV
(line 6515, 4 blocks), routed SwiGLU QMV (line 7174, 4 blocks), QKV R1 (line
4604, 4 blocks).

**Correctness:** The FMA accumulation order is preserved if each block's
contribution is added to the same accumulator in the same order
(block 0, then block 1, etc.). The "LOADS ONLY" constraint from notes/54 §11
applies: do not combine per-block partials into a tree — accumulate sequentially
into one register.

**Register pressure:** 2× the in-flight weight codes (2 × uint2 = 16 bytes) plus
2× the input values (2 × 16 floats = 128 bytes = 32 registers). At 0.40 waves,
there is headroom for the expert kernels. The QKV R1 kernel at 64 threads may be
tighter — test carefully.

**Implementation effort:** ~300 bytes per kernel (loop restructuring + dual load).

---

## Idea 4: Texture-Backed Weight Storage for Expert NVFP4 Codes

**Category:** Metal-specific optimization / cache hierarchy
**Estimated impact:** 5–15% decode speedup (enlarges effective L1 cache)
**Risk:** MEDIUM (requires weight transform + Metal texture API changes)
**Causal hypothesis:** Apple GPUs have separate L1 caches for texture reads and
buffer reads (Apple Tech Talk 10580). The NVFP4 weight codes are currently stored
as `MTLBuffer` (uint8/uint32). Moving them to a 2D `MTLTexture` with lossless
compression would (a) use the separate texture L1 cache, effectively doubling
available cache capacity for weight reads, and (b) potentially benefit from the
GPU's texture compression hardware, reducing DRAM bandwidth. For a bandwidth-
bound GEMV, this directly attacks the bottleneck.

**Layout:** The packed codes are `[expert][row][col/8]` uint32. As a texture,
this maps to a 2D layout: width = `hidden/8` (256 for gate/up, 64 for down),
height = `expert_count * output_rows`. Metal textures support `MTLPixelFormatR32Uint`
which is 4 bytes per texel. The kernel would read via `texture2d<uint32_t>` instead
of `device uint32_t*`.

**Scope:** This requires changes to both Transform.swift (to produce texture-
compatible weight layouts) and the kernel sources (to accept texture arguments
instead of buffer pointers). The MLXFast metalKernel API would need to support
texture inputs — this may require checking whether `MLXFast.MLXFastKernel`
supports texture-typed inputs.

**Correctness:** The weight bytes are identical — only the storage format changes.
The kernel reads the same uint32 values. Bit-exact if the texture format is
`R32Uint` (no filtering, no compression artifacts).

**Risk factors:**
- MLX's metalKernel API may not support texture inputs directly. Check
  `MLXFast.metalKernel` for texture input support. If not, this requires a
  custom MTLCommandBuffer dispatch, which is outside the editable surface.
- Lossless texture compression on Apple GPUs is automatic for render passes
  but may not apply to compute kernel texture reads. Need to verify.
- The texture dimensions must fit Metal's limits (max 16384 for 2D textures on
  recent Apple Silicon). For 256 experts × 512 rows × 256 width, the height
  is 131072 — exceeds the 16384 limit. Would need a texture array or 3D texture.

**Implementation effort:** HIGH. Requires weight transform, API investigation,
and kernel changes. Estimated 500+ bytes across Transform.swift and kernel
sources. Given the 15,740-byte file headroom, this may not fit if all changes
land in LagunaRuntimeModel.swift.

**Recommendation:** Investigate feasibility (MLXFast texture support) before
committing. If feasible, this is the highest-upside idea because it attacks the
fundamental bandwidth bottleneck with a hardware-level cache expansion.

---

## Idea 5: Threadgroup Geometry Sweep for Down+Residual Kernel

**Category:** Threadgroup geometry optimization
**Estimated impact:** 1–3% decode speedup (occupancy / register pressure)
**Risk:** LOW
**Causal hypothesis:** The down+residual kernel (line 7649) uses 288 threads
(9 simdgroups): 8 routed expert slots + 1 shared slot, each computing 4 output
rows. The 288-thread group is unusual — Apple GPU occupancy is quantized in
64-thread steps (1024→896→832→704→384 at increasing register usage). A 288-thread
group may interact poorly with the core's threadgroup scheduler. Testing 256
threads (8 simdgroups, with the shared expert dispatched separately) or 320
threads (10 simdgroups, with 1 padding) could improve occupancy or reduce
scheduling overhead.

**Current geometry:** grid = `(2048 / 4, 1, 1)` = 512 threadgroups, each 288
threads = 147,456 total threads. At 0.40 waves, ~3.2 threadgroups per core.

**Proposed sweep:**
1. **256 threads (8 simdgroups):** Drop the shared expert from the fused kernel.
   The shared down projection runs as a separate small dispatch, then the
   residual add is done by the routed kernel's slot 0 after reading shared from
   device memory. This eliminates the barrier (slot 0 no longer waits for
   slot 8) but adds one dispatch. Net effect is a trade — fewer threads per
   group vs one more dispatch. Test both.
2. **320 threads (10 simdgroups):** Add a padding simdgroup that does nothing.
   This aligns the threadgroup to a 64-thread boundary (320 = 5 × 64). The
   padding group's qdot result is discarded. Costs 11% more threads but may
   improve scheduler alignment.
3. **512 threads (16 simdgroups):** Double the work per threadgroup — compute
   8 output rows instead of 4. This halves the number of threadgroups (256
   instead of 512) and doubles the threadgroup memory for the reduction
   (from 36 to 72 BF16 values). May improve occupancy if the current 512
   threadgroups are oversubscribing the core.

**Correctness:** All variants produce the same output values — only the
thread/group partitioning changes. The reduction order (8 routed experts summed
sequentially, then shared added, then residual) must be preserved. Bit-exact.

**Implementation effort:** ~100 bytes (threadgroup size constant + grid
adjustment). The sweep is parameterizable via an env flag.

**Note:** The AGENTS.md warns that threadgroup geometry can change sign across
core counts (M4 vs M5). Any conclusion must be validated on the M5, not M4.

---

## Idea 6: Eliminate the Down+Residual Barrier via Sequential Slot Ordering

**Category:** GPU synchronization reduction
**Estimated impact:** 1–2% decode speedup (eliminates one barrier per layer)
**Risk:** MEDIUM (changes reduction structure — must preserve BF16 rounding)
**Causal hypothesis:** The down+residual kernel (line 7732) has a
`threadgroup_barrier` between the per-slot down projection and the slot-0
reduction. All 9 simdgroups write their results to threadgroup memory, barrier,
then slot 0 reads all 9 results and computes the weighted sum + residual. The
barrier costs ~50–100 ns per threadgroup (at 512 threadgroups, this is serial
only within one group — the groups run in parallel, so the total cost is
~50–100 ns per decode step, not 512×). The barrier exists because slot 0 needs
all 8 routed results.

**Proposed alternative — device-memory atomic add:** Instead of threadgroup
memory + barrier, have each slot atomically add its weighted contribution
directly to the output buffer in device memory. Slot 0 initializes the output
with the residual, then each routed slot adds `route_weight * down_result *
2.5`. The shared slot adds its result.

**Problem:** BF16 atomic add is not associative. The current code does:
```metal
routed_total = bfloat(0);
for (routed_slot = 0..7) {
    routed_total = bfloat(product + routed_total); // sequential BF16 add
}
routed = bfloat(routed_total * bfloat(2.5f));
r2 = bfloat(routed + shared);
output = bfloat(residual + r2);
```
Atomic adds in arbitrary order would change the BF16 rounding. This is NOT
bit-exact.

**Proposed alternative — split-k reduction without barrier:** Each slot writes
its BF16 result to a per-slot region of the OUTPUT buffer (not threadgroup
memory). Slot 0 then reads all 8 routed results from device memory (which is
coherent within the same threadgroup's execution since the slots run
concurrently and the reads happen after all writes are in flight). This requires
a `threadgroup_barrier` on device memory (`mem_flags::mem_device`) instead of
threadgroup memory — which is not cheaper.

**Proposed alternative — eliminate the shared slot from the fused kernel:**
If the shared expert's down projection is dispatched separately (as in Idea 5
variant 1), the routed-only kernel has 8 slots = 256 threads, and slot 0 can
use `simd_sum` across the 8 simdgroups... but Metal does not support cross-
simdgroup shuffle. The reduction still needs threadgroup memory + barrier.

**Assessment:** The barrier is structurally necessary for the current fused
design. The only way to eliminate it is to split the kernel (which adds dispatch
overhead, negating the original fusion win) or to accept non-associative
reduction (which breaks correctness). **Recommendation: deprioritize.** The
barrier cost (~50–100 ns/step) is small relative to the ~9.5 ms decode step.
The fusion that created it (DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL) already
saved 39 dispatches/step, which is worth far more than the barrier costs.

---

## Idea 7: Precompute RMSNorm Inverse-RMS as a Scalar Before the Kernel

**Category:** Weight precomputation / compute reduction
**Estimated impact:** <1% decode speedup (tiny compute saving)
**Risk:** LOW
**Causal hypothesis:** The RMSNorm computation in the fused sliding attention
kernel (line 1442–1443) computes `simd_sum(x^2)` then
`precise::rsqrt(sum/128 + 1e-6)` per threadgroup. This is 32 FMA + 1 rsqrt per
head per layer — negligible compute. However, the `precise::rsqrt` is a full-
precision intrinsic that may take more cycles than a fast `rsqrt`. The fast
`metal::rsqrt` (without `precise::`) is ~2× faster but may differ by 1 ULP.

**Assessment:** Not worth pursuing. The RMSNorm compute is <0.1% of decode time.
The `precise::rsqrt` is needed for bit-exactness with the stock path. Any change
here risks the correctness gate for negligible gain.

---

## Idea 8: Fuse the Router GEMV with the Top-8 Extraction in a Single Kernel

**Category:** Compute reduction (not dispatch elimination — this is a kernel-
internal compute fusion)
**Estimated impact:** 2–4% decode speedup (eliminates intermediate 256-element
buffer materialization)
**Risk:** MEDIUM (changes router dispatch structure)
**Causal hypothesis:** The router path is: BF16 GEMV over `[256, 2048]` weight
→ 256 FP32 logits → softmax → top-8 extraction. Currently this is 2+ dispatches
(GEMV + softmax + top-8). The top-8 extraction uses a simd-shuffle comparator
(line 7269–7296) that runs over the 256 logits. If the GEMV and top-8 extraction
were fused into a single kernel, the 256-element intermediate buffer would never
be materialized to device memory, and the top-8 extraction could start as soon
as the GEMV's partial sums are available in threadgroup memory.

**Current flow:**
1. Router GEMV: 256 output rows × 2048 input → 256 FP32 logits (1 dispatch)
2. Softmax: 256 → 256 normalized (1 dispatch)
3. Top-8 extraction: 256 → 8 indices + 8 weights (1 dispatch, or fused with #2)

**Proposed fused kernel:** One threadgroup of 256 threads (8 simdgroups), each
lane computes 1 logit (256/32 = 8 elements per lane over the 2048 input). After
`simd_sum`, lane 0 of each simdgroup has 1 logit. 8 simdgroups × 32 lanes = 256
logits in threadgroup memory. Then the same threadgroup runs the top-8 extraction
using the existing simd-shuffle comparator, reading from threadgroup memory
instead of device memory.

**Scope:** The router GEMV is a BF16 dense matmul (not NVFP4). The custom kernel
would need to reproduce MLX's `gemv` for the `[256, 2048]` shape exactly. The
top-8 extraction is already a custom kernel (line 7269). Fusing them eliminates
2 dispatches and 1 device-memory round-trip for the 256-element buffer (1 KB
FP32 — small, but the dispatch overhead is the real saving).

**Correctness:** The GEMV must reproduce the stock `gemv` bit-exactly (same FP32
accumulation order, same BF16 cast). The softmax and top-8 extraction must
produce the same indices and weights. This is the same exactness requirement as
the existing custom kernels.

**Note:** This is adjacent to Experiment #1 (eliminating redundant top-8
extraction) but different: #1 reduces compute within the existing top-8 kernel,
while this fuses the router GEMV + softmax + top-8 into one kernel, eliminating
dispatch overhead and intermediate materialization.

**Implementation effort:** ~400 bytes for the fused kernel source.

---

## Idea 9: O-Projection Weight Row Reorder for Coalesced GEMV Access

**Category:** Memory access pattern optimization
**Estimated impact:** 2–5% decode speedup (improves coalescing on the largest
BF16 weight read)
**Risk:** MEDIUM (requires weight transform, may affect prefill)
**Causal hypothesis:** The O-projection is the single largest BF16 decode weight
read: 30 sliding layers at `[2048, 8192]` + 10 full-attention layers at
`[2048, 6144]` ≈ 1.2 GB (line 359–362). The GEMV accesses the weight matrix in
a lane-strided pattern: lane `l` reads columns `4l + 128i` (line 3496–3497). If
the weight matrix rows were physically reordered to match this access pattern
(contiguous 128-byte blocks matching the lane stride), every vec4 load would be
perfectly coalesced across all 32 lanes.

**Current access pattern:** The weight is row-major `[out_dim, in_dim]`. Lane `l`
reads `weight[(out_row + row) * in_dim + 4l + 128i]`. For 32 lanes, the reads
span 128 elements (256 bytes for BF16) per `i` step — this is already a single
256-byte cache line, so coalescing is already good. The issue is that consecutive
`i` steps jump by 128 elements (256 bytes), which is the next cache line. So the
pattern is: 32 lanes read 1 cache line, advance by 1 cache line, repeat. This is
optimal for sequential access.

**Assessment:** The O-projection GEMV access is already coalesced. Row reordering
would not improve it. The bottleneck is raw DRAM bandwidth, not coalescing. The
DARKBLOOM_NATIVE_AFFINE_OPROJ quantization (group-32 INT8) already reduces the
O-proj read from 1.2 GB BF16 to ~300 MB INT8 — a 4× bandwidth reduction.
**Deprioritize** unless the INT8 quantization has not been applied to all 40
layers (check `lagunaNativeAffineOProjLayerCount`).

---

## Idea 10: Batch Multiple Layers' Router + MoE Work into a Single Compute Encoder

**Category:** Command buffer optimization
**Estimated impact:** 1–3% decode speedup (reduces per-encode overhead)
**Risk:** LOW (no correctness impact — asyncEval is bit-exact)
**Causal hypothesis:** MLX dispatches each kernel as a separate compute encoder
within a command buffer. The asyncEval schedule (7 fires at layers 0,1,7,15,23,
31,39) creates command-buffer boundaries that let the CPU prepare future work
while the GPU executes current work. But within each asyncEval segment, each
kernel still gets its own compute encoder with per-encode overhead (~1–2 µs per
encode on Apple Silicon). For a 7-layer segment (layers 1–7), there are ~7 × 5
kernels = 35 encoders. If these could share fewer encoders, the per-encode tax
would drop.

**MLX constraint:** MLX's `metalKernel` API dispatches one kernel per call. There
is no public API to batch multiple kernel dispatches into one compute encoder.
However, MLX internally may already batch encoders within a single `asyncEval`
boundary. Check whether MLX's `Stream` / `StreamContext` reuses a single encoder
across multiple dispatches within the same async segment.

**Proposed investigation:** Profile the command buffer count per decode step
using Metal's `MTLCommandBuffer.label` or the GPU capture tool. If each kernel
gets its own encoder, the overhead is ~35 × 2 µs = 70 µs per 7-layer segment,
~400 µs per step — 4% of a 9.5 ms step. If encoders are already batched within
async segments, this is a non-issue.

**Alternative — custom MTLCommandBuffer:** If MLX does not batch encoders,
writing a custom command buffer that encodes multiple kernels per encoder would
require bypassing MLX's dispatch — likely outside the editable surface.

**Assessment:** Investigate first (is MLX already batching?). If not, this is
a framework-level optimization that may not be achievable within the editable
surface. **Low priority** unless profiling reveals per-encode overhead is
significant.

---

## Idea 11: Eliminate Per-Step Mask Creation Overhead

**Category:** Weight precomputation / dispatch elimination
**Estimated impact:** 0% (already optimized)
**Risk:** N/A
**Finding:** For single-token decode (`h.dim(1) == 1`), `createAttentionMask`
returns `.none` (line 309–311 in KVCache.swift). The sliding and full masks are
only created for prefill (`t > 1`). So during decode, NO mask dispatches occur.
This is already optimal. No action needed.

---

## Idea 12: Reduce NVFP4 Scale-Read Overhead via Threadgroup Broadcast

**Category:** Memory access pattern optimization
**Estimated impact:** 3–6% decode speedup (reduces scale-byte device reads)
**Risk:** LOW
**Causal hypothesis:** In the NVFP4 GEMV kernels, each lane reads its own scale
byte from device memory. For group-16 quantization with K=2048, each row has 128
scale bytes. With 32 lanes per simdgroup, the 32 lanes read 32 consecutive scale
bytes per block — this is a single 32-byte coalesced read. However, with 4 blocks
and 2 rows per iteration, the kernel issues 4 × 2 = 8 coalesced 32-byte reads
per simdgroup per K-loop. The scale bytes total 128 × 2 = 256 bytes per row per
simdgroup — 1 cache line. This is already efficient.

**But:** the `laguna_nvfp4_scale` function (line 6485–6491) performs a
`as_type<half>` conversion + sign application per scale byte. This is 3–4 ALU
ops per scale read. With 8 scale reads per row per simdgroup, that's 24–32 ALU
ops. For a bandwidth-bound kernel, this is in the noise.

**Assessment:** Scale reads are already coalesced and the conversion overhead
is negligible. The `DARKBLOOM_PACKED_SCALES` optimization (line 152–166) already
stores scales in walk-order for the routed kernels. **No further optimization
needed** unless profiling shows scale-read latency on the critical path.

---

## Priority Ranking

| # | Idea | Impact | Risk | Effort | Priority |
|---|------|--------|------|--------|----------|
| 1 | Stage activation vector in threadgroup memory | 5–10% | LOW | ~200 B/kernel | **P0** |
| 3 | Prefetch/depth-2 unroll next block's weights | 3–6% | LOW | ~300 B/kernel | **P0** |
| 2 | Register-resident scale pre-loading | 2–4% | LOW | ~150 B/kernel | **P1** |
| 4 | Texture-backed weight storage | 5–15% | MED | 500+ B, API check | **P1** (investigate) |
| 5 | Threadgroup geometry sweep (down kernel) | 1–3% | LOW | ~100 B | **P2** |
| 8 | Fuse router GEMV + top-8 extraction | 2–4% | MED | ~400 B | **P2** |
| 10 | Batch encoders within async segments | 1–3% | LOW | investigation | **P3** (investigate) |
| 6 | Eliminate down+residual barrier | 1–2% | MED | — | **Deprioritized** |
| 7 | Fast rsqrt in RMSNorm | <1% | LOW | — | **Deprioritized** |
| 9 | O-proj row reorder | 0% | — | — | **Not needed** |
| 11 | Mask creation overhead | 0% | — | — | **Already optimal** |
| 12 | Scale-read broadcast | 0% | — | — | **Already optimal** |

---

## Key Architectural Constraints

1. **Do NOT use simdgroup_matrix or matmul2d for decode GEMV.** These are
   compute-bound primitives; decode is bandwidth-bound. The current scalar FMA
   + `simd_sum` pattern is correct for this workload.

2. **Do NOT stage the weight matrix in threadgroup memory.** The matrix is read
   once; the barrier cost exceeds the bandwidth savings on unified memory. Only
   stage the activation vector (read many times across rows).

3. **Preserve FP32 accumulation order.** Every kernel must accumulate in the
   same block/row/lane order as the stock MLX `gemv` / `fp_qmv_fast` it replaces.
   Tree reduction or partial-sum reordering breaks bit-exactness. The "LOADS
   ONLY" constraint (notes/54 §11) applies to all depth-2 unroll variants.

4. **M5 selects `_nax` variants for prefill.** Any prefill optimization must
   target the NAXTile/matmul2d path, not the simdgroup_matrix path. Decode
   does not use `_nax` variants.

5. **M4 is not evidence for M5 threadgroup geometry.** Core count differences
   can flip the sign of occupancy changes. Validate all geometry conclusions on
   the ranked M5 host.

6. **The model is RAM-resident with no expert cache or streaming.** Do not
   optimize for cache miss patterns that assume cold weights — all 256 experts
   + shared expert are resident.

---

## Sources

- Modular M5 fp4_gemv documentation (M5-specific NVFP4 GEMV design, denormal
  flush-to-zero, 16-lane SIMD constraint, ~540 GB/s measured bandwidth)
- philipturner/metal-flash-attention issue #12 (unified memory bandwidth gap,
  simd_sum for GEMV, texture vs buffer L1)
- MLX issue #3251 (group-16 scale-read overhead, ~10–14% penalty)
- Apple WWDC 2020/10603 (TBDR memory hierarchy, tile memory, LLC)
- Apple Tech Talk 10580 (separate texture/buffer L1 caches)
- Alyssa Rosenzweig Asahi GPU reverse engineering (occupancy quantization,
  register file sizes, 64-thread step structure)
- Vendored MLX fp_quantized.cpp (QuantizedBlockLoader, threadgroup staging
  patterns — NOT applicable to decode GEMV but validates the bandwidth-bound
  framing)
- Vendored MLX fp_quantized_nax.cpp (NAXTile/matmul2d — compute-bound, NOT
  for decode GEMV)
- Vendored MLX steel_gemm_gather.cpp (run-length expert coalescing — relevant
  for prefill, not single-token decode)
