import Foundation
import Metal

// Standalone Metal microbenchmark for the shared-SwiGLU NVFP4 QMV kernel family.
// Goal: find out whether the shipped rows1-halved geometry is leaving achieved
// bandwidth on the table, or whether a 1.11 MB dispatch simply cannot go faster.

let args = CommandLine.arguments
guard args.count >= 2 else {
    FileHandle.standardError.write("usage: bench <header.metal> [iters]\n".data(using: .utf8)!)
    exit(2)
}
let headerPath = args[1]
let iters = args.count >= 3 ? Int(args[2])! : 60

var headerText = try String(contentsOfFile: headerPath, encoding: .utf8)
headerText = headerText
    .split(separator: "\n", omittingEmptySubsequences: false)
    .filter { !$0.hasPrefix("===QMVHEADER_") }
    .joined(separator: "\n")

let prelude = """
#include <metal_stdlib>
#include <metal_simdgroup>
using namespace metal;
typedef bfloat bf16;
"""

// ---------------------------------------------------------------------------
// Shipped body (rows1 halved), verbatim from lagunaSharedSwiGLUQMVRows1Source.
// Parameterised by rows-per-simdgroup (R) and simdgroups-per-threadgroup (G).
// ---------------------------------------------------------------------------
func rowsBody(rowsPerSimd R: Int, simdsPerTG G: Int) -> String {
    return """
constexpr uint input_width = 2048;
constexpr uint output_width = 512;
constexpr uint packed_row_bytes = 1024;
constexpr uint scale_row_bytes = 64;
constexpr uint scale_patch_bytes = 128;
constexpr uint block_width = 512;
constexpr uint values_per_lane = 16;
constexpr uint rows_per_simd = \(R);
constexpr uint simds_per_tg = \(G);

uint tile = threadgroup_position_in_grid.x;
uint simd_group = simdgroup_index_in_threadgroup;
uint lane = thread_index_in_simdgroup;
uint row_base = (tile * simds_per_tg + simd_group) * rows_per_simd;

thread float input_values[values_per_lane];
thread float gate_result[rows_per_simd];
thread float up_result[rows_per_simd];
for (uint r = 0; r < rows_per_simd; ++r) { gate_result[r] = 0.0f; up_result[r] = 0.0f; }

for (uint block = 0; block < input_width; block += block_width) {
    const device vec<bfloat, 4>* input_vectors =
        (const device vec<bfloat, 4>*) (input + block + lane * values_per_lane);
    for (uint i = 0; i < values_per_lane / 4; ++i) {
        const vec<bfloat, 4> values = input_vectors[i];
        input_values[4 * i] = values[0];
        input_values[4 * i + 1] = values[1];
        input_values[4 * i + 2] = values[2];
        input_values[4 * i + 3] = values[3];
    }
    for (uint r = 0; r < rows_per_simd; ++r) {
        uint row = row_base + r;
        const device uint8_t* gate_row_weight =
            (const device uint8_t*)fused_weight + row * packed_row_bytes + lane * 8;
        const device uint8_t* up_row_weight =
            (const device uint8_t*)fused_weight + (row + output_width) * packed_row_bytes + lane * 8;
        const device uint8_t* gate_row_scale =
            fused_scales + scale_patch_bytes + row * scale_row_bytes + (lane >> 1);
        const device uint8_t* up_row_scale =
            fused_scales + scale_patch_bytes + (row + output_width) * scale_row_bytes + (lane >> 1);
        gate_result[r] += laguna_nvfp4_qdot_16(
            gate_row_weight + block / 2, input_values,
            laguna_nvfp4_scale(gate_row_scale[block / 32]));
        up_result[r] += laguna_nvfp4_qdot_16(
            up_row_weight + block / 2, input_values,
            laguna_nvfp4_scale(up_row_scale[block / 32]));
    }
}

for (uint r = 0; r < rows_per_simd; ++r) {
    float g = simd_sum(gate_result[r]);
    float u = simd_sum(up_result[r]);
    if (lane == 0) {
        float gate = g * 4194304.0f;
        float up = u * 4194304.0f;
        float exp_abs = metal::exp(metal::abs(gate));
        float denominator = 1.0f + exp_abs;
        float y = 1.0f / denominator;
        float sigmoid = gate < 0.0f ? y : 1.0f - y;
        float silu = gate * sigmoid;
        activated[row_base + r] = bfloat(silu * up);
    }
}
"""
}

// K-split: S simdgroups cooperate on one output row, each covering 1/S of K.
func ksplitBody(split S: Int, rowsPerTG RT: Int) -> String {
    return """
constexpr uint input_width = 2048;
constexpr uint output_width = 512;
constexpr uint packed_row_bytes = 1024;
constexpr uint scale_row_bytes = 64;
constexpr uint scale_patch_bytes = 128;
constexpr uint block_width = 512;
constexpr uint values_per_lane = 16;
constexpr uint ksplit = \(S);
constexpr uint rows_per_tg = \(RT);

threadgroup float partial_gate[ksplit * rows_per_tg];
threadgroup float partial_up[ksplit * rows_per_tg];

uint tile = threadgroup_position_in_grid.x;
uint simd_group = simdgroup_index_in_threadgroup;
uint lane = thread_index_in_simdgroup;
uint local_row = simd_group / ksplit;
uint kpart = simd_group % ksplit;
uint row = tile * rows_per_tg + local_row;

thread float input_values[values_per_lane];
float gate_result = 0.0f;
float up_result = 0.0f;

const device uint8_t* gate_row_weight =
    (const device uint8_t*)fused_weight + row * packed_row_bytes + lane * 8;
const device uint8_t* up_row_weight =
    (const device uint8_t*)fused_weight + (row + output_width) * packed_row_bytes + lane * 8;
const device uint8_t* gate_row_scale =
    fused_scales + scale_patch_bytes + row * scale_row_bytes + (lane >> 1);
const device uint8_t* up_row_scale =
    fused_scales + scale_patch_bytes + (row + output_width) * scale_row_bytes + (lane >> 1);

for (uint b = kpart; b < input_width / block_width; b += ksplit) {
    uint block = b * block_width;
    const device vec<bfloat, 4>* input_vectors =
        (const device vec<bfloat, 4>*) (input + block + lane * values_per_lane);
    for (uint i = 0; i < values_per_lane / 4; ++i) {
        const vec<bfloat, 4> values = input_vectors[i];
        input_values[4 * i] = values[0];
        input_values[4 * i + 1] = values[1];
        input_values[4 * i + 2] = values[2];
        input_values[4 * i + 3] = values[3];
    }
    gate_result += laguna_nvfp4_qdot_16(
        gate_row_weight + block / 2, input_values,
        laguna_nvfp4_scale(gate_row_scale[block / 32]));
    up_result += laguna_nvfp4_qdot_16(
        up_row_weight + block / 2, input_values,
        laguna_nvfp4_scale(up_row_scale[block / 32]));
}

gate_result = simd_sum(gate_result);
up_result = simd_sum(up_result);
if (lane == 0) {
    partial_gate[simd_group] = gate_result;
    partial_up[simd_group] = up_result;
}
threadgroup_barrier(mem_flags::mem_threadgroup);
if (simd_group % ksplit == 0 && lane == 0) {
    float g = 0.0f, u = 0.0f;
    for (uint s = 0; s < ksplit; ++s) {
        g += partial_gate[local_row * ksplit + s];
        u += partial_up[local_row * ksplit + s];
    }
    float gate = g * 4194304.0f;
    float up = u * 4194304.0f;
    float exp_abs = metal::exp(metal::abs(gate));
    float denominator = 1.0f + exp_abs;
    float y = 1.0f / denominator;
    float sigmoid = gate < 0.0f ? y : 1.0f - y;
    float silu = gate * sigmoid;
    activated[row] = bfloat(silu * up);
}
"""
}

func wrap(_ name: String, _ body: String) -> String {
    return """
kernel void \(name)(
    const device bfloat* input [[buffer(0)]],
    const device uint8_t* fused_weight [[buffer(1)]],
    const device uint8_t* fused_scales [[buffer(2)]],
    device bfloat* activated [[buffer(3)]],
    uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
    uint3 thread_position_in_grid [[thread_position_in_grid]],
    uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
    uint thread_index_in_simdgroup [[thread_index_in_simdgroup]]) {
\(body)
}
"""
}

// Pure streaming-read control: read the same 1,114,240 B of weights+scales with
// `bytesPerThread` bytes per thread and `loadBytes`-wide loads, reduce, store.
func streamKernel(_ name: String, threads: Int, loadBytes: Int) -> String {
    let totalBytes = 1_048_576 + 65_536
    let perThread = totalBytes / threads
    let loadsPerThread = perThread / loadBytes
    let vecType = loadBytes == 16 ? "uint4" : (loadBytes == 8 ? "uint2" : "uint")
    let comps = loadBytes == 16 ? "v.x ^ v.y ^ v.z ^ v.w" : (loadBytes == 8 ? "v.x ^ v.y" : "v")
    return """
kernel void \(name)(
    const device bfloat* input [[buffer(0)]],
    const device uint8_t* fused_weight [[buffer(1)]],
    const device uint8_t* fused_scales [[buffer(2)]],
    device bfloat* activated [[buffer(3)]],
    uint3 thread_position_in_grid [[thread_position_in_grid]],
    uint thread_index_in_simdgroup [[thread_index_in_simdgroup]]) {
    const device \(vecType)* base = (const device \(vecType)*)fused_weight;
    uint tid = thread_position_in_grid.x;
    uint acc = 0;
    // contiguous per-warp stripe, stride = total threads (fully coalesced)
    for (uint i = 0; i < \(loadsPerThread); ++i) {
        \(vecType) v = base[tid + i * \(threads)];
        acc ^= (\(comps));
    }
    if (acc == 0xFFFFFFFFu) { activated[tid % 512] = bfloat(float(acc)); }
}
"""
}

var kernels: [(name: String, grid: Int, tg: Int, source: String)] = []

// V0: shipped geometry, R=1, G=2, 256 threadgroups of 64 threads.
kernels.append(("v0_shipped", 256 * 64, 64, wrap("v0_shipped", rowsBody(rowsPerSimd: 1, simdsPerTG: 2))))
// Threadgroup shape sweep at R=1 (same total threads, different TG packing).
kernels.append(("v1_r1_tg256", 64 * 256, 256, wrap("v1_r1_tg256", rowsBody(rowsPerSimd: 1, simdsPerTG: 8))))
kernels.append(("v2_r1_tg1024", 16 * 1024, 1024, wrap("v2_r1_tg1024", rowsBody(rowsPerSimd: 1, simdsPerTG: 32))))
// Rows per simdgroup sweep (fewer threads, more loads in flight per thread).
kernels.append(("v3_r2_tg64", 128 * 64, 64, wrap("v3_r2_tg64", rowsBody(rowsPerSimd: 2, simdsPerTG: 2))))
kernels.append(("v4_r4_tg64", 64 * 64, 64, wrap("v4_r4_tg64", rowsBody(rowsPerSimd: 4, simdsPerTG: 2))))
// K-split (more threads, more memory-level parallelism).
kernels.append(("v5_ks2_tg128", 256 * 128, 128, wrap("v5_ks2_tg128", ksplitBody(split: 2, rowsPerTG: 2))))
kernels.append(("v6_ks4_tg256", 256 * 256, 256, wrap("v6_ks4_tg256", ksplitBody(split: 4, rowsPerTG: 2))))
kernels.append(("v7_ks8_tg256", 512 * 256, 256, wrap("v7_ks8_tg256", ksplitBody(split: 8, rowsPerTG: 1))))
// Calibration arm: the shipped DARKBLOOM_QMV_WIDE_CODES kernel, verbatim.
// This arm was measured in situ at +12.2% kernel time vs the shipped default
// (research/maple-frieren-r106j-bitexactness-shelf.md). If the rig reproduces
// that regression, the rig's ranking can be trusted; it is a calibration
// standard here, never a candidate (it is not bit-exact and is closed).
let wideBody = """
constexpr uint input_width = 2048;
constexpr uint output_width = 512;
constexpr uint packed_row_bytes = 1024;
constexpr uint scale_row_bytes = 64;
constexpr uint scale_patch_bytes = 128;
constexpr uint slab_width = 1024;
constexpr uint values_per_lane = 32;

uint tile = threadgroup_position_in_grid.x;
uint simd_group = simdgroup_index_in_threadgroup;
uint lane = thread_index_in_simdgroup;
uint row = tile * 2 + simd_group;

const device uint8_t* gate_row_weight =
    (const device uint8_t*)fused_weight + row * packed_row_bytes + lane * 16;
const device uint8_t* up_row_weight =
    (const device uint8_t*)fused_weight + (row + output_width) * packed_row_bytes + lane * 16;
const device uint8_t* gate_row_scale =
    fused_scales + scale_patch_bytes + row * scale_row_bytes + lane;
const device uint8_t* up_row_scale =
    fused_scales + scale_patch_bytes + (row + output_width) * scale_row_bytes + lane;

thread float gate_result = 0.0f;
thread float up_result = 0.0f;
thread float input_values[values_per_lane];

for (uint slab = 0; slab < input_width; slab += slab_width) {
    const device vec<bfloat, 4>* input_vectors =
        (const device vec<bfloat, 4>*) (input + slab + lane * values_per_lane);
    for (uint i = 0; i < values_per_lane / 4; ++i) {
        const vec<bfloat, 4> values = input_vectors[i];
        input_values[4 * i] = values[0];
        input_values[4 * i + 1] = values[1];
        input_values[4 * i + 2] = values[2];
        input_values[4 * i + 3] = values[3];
    }
    uint8_t gate_sb = gate_row_scale[slab / 32];
    uint8_t up_sb = up_row_scale[slab / 32];
    const uint4 gate_codes = *(const device uint4*)(gate_row_weight + slab / 2);
    const uint4 up_codes = *(const device uint4*)(up_row_weight + slab / 2);
    gate_result += laguna_nvfp4_qdot_codes_16(
        gate_codes.xy, input_values, laguna_nvfp4_scale(gate_sb));
    gate_result += laguna_nvfp4_qdot_codes_16(
        gate_codes.zw, input_values + 16, laguna_nvfp4_scale(gate_sb));
    up_result += laguna_nvfp4_qdot_codes_16(
        up_codes.xy, input_values, laguna_nvfp4_scale(up_sb));
    up_result += laguna_nvfp4_qdot_codes_16(
        up_codes.zw, input_values + 16, laguna_nvfp4_scale(up_sb));
}

gate_result = simd_sum(gate_result);
up_result = simd_sum(up_result);
if (lane == 0) {
    float gate = gate_result * 4194304.0f;
    float up = up_result * 4194304.0f;
    float exp_abs = metal::exp(metal::abs(gate));
    float denominator = 1.0f + exp_abs;
    float y = 1.0f / denominator;
    float sigmoid = gate < 0.0f ? y : 1.0f - y;
    float silu = gate * sigmoid;
    activated[row] = bfloat(silu * up);
}
"""
kernels.append(("c0_wide_known_bad", 256 * 64, 64, wrap("c0_wide_known_bad", wideBody)))
// Streaming-read controls at the same byte volume.
kernels.append(("s0_stream_16k_8B", 16384, 64, streamKernel("s0_stream_16k_8B", threads: 16384, loadBytes: 8)))
kernels.append(("s1_stream_16k_16B", 16384, 64, streamKernel("s1_stream_16k_16B", threads: 16384, loadBytes: 16)))
kernels.append(("s2_stream_64k_16B", 65536, 256, streamKernel("s2_stream_64k_16B", threads: 65536, loadBytes: 16)))
kernels.append(("s3_stream_8k_16B", 8192, 256, streamKernel("s3_stream_8k_16B", threads: 8192, loadBytes: 16)))

let source = prelude + "\n" + headerText + "\n" + kernels.map { $0.source }.joined(separator: "\n\n")
try? source.write(toFile: "/tmp/qmvbench/generated.metal", atomically: true, encoding: .utf8)

guard let device = MTLCreateSystemDefaultDevice() else { fatalError("no device") }
let queue = device.makeCommandQueue()!
let opts = MTLCompileOptions()
opts.mathMode = .fast
opts.languageVersion = .version3_1
let library: MTLLibrary
do { library = try device.makeLibrary(source: source, options: opts) }
catch { FileHandle.standardError.write("compile failed: \(error)\n".data(using: .utf8)!); exit(1) }

let layers = 39
let weightBytesPerLayer = 1_048_576
let scaleBytesPerLayer = 128 + 65_536
let bytesPerCall = weightBytesPerLayer + 65_536

// Pool of distinct layer slots. `layers` slots (43 MB) fits comfortably in SLC
// and is re-read every iteration; a large pool (hundreds of MB) forces every
// call to come from cold DRAM, which is what the in-situ decode loop sees when
// 21.6 GB of other weights evict this kernel's slice between steps.
let poolMB = args.count >= 4 ? Int(args[3])! : 43
let poolSlots = max(layers, poolMB * 1_048_576 / bytesPerCall)
FileHandle.standardError.write("pool slots: \(poolSlots) (\(poolSlots * bytesPerCall / 1_048_576) MiB)\n".data(using: .utf8)!)

let weightBuf = device.makeBuffer(length: poolSlots * weightBytesPerLayer, options: .storageModeShared)!
let scaleBuf = device.makeBuffer(length: poolSlots * scaleBytesPerLayer, options: .storageModeShared)!
let inputBuf = device.makeBuffer(length: 4096, options: .storageModeShared)!
let outBuf = device.makeBuffer(length: layers * 1024, options: .storageModeShared)!

// deterministic fill
do {
    let w = weightBuf.contents().bindMemory(to: UInt8.self, capacity: poolSlots * weightBytesPerLayer)
    var s: UInt32 = 12345
    for i in 0..<(poolSlots * weightBytesPerLayer) { s = s &* 1664525 &+ 1013904223; w[i] = UInt8((s >> 16) & 0xFF) }
    let sc = scaleBuf.contents().bindMemory(to: UInt8.self, capacity: poolSlots * scaleBytesPerLayer)
    for i in 0..<(poolSlots * scaleBytesPerLayer) { s = s &* 1664525 &+ 1013904223; sc[i] = UInt8(((s >> 16) & 0x0F) | 0x30) }
    let inp = inputBuf.contents().bindMemory(to: UInt16.self, capacity: 2048)
    for i in 0..<2048 { inp[i] = UInt16(0x3F00 &+ UInt16(i % 32)) }
}


struct Variant {
    let name: String
    let grid: Int
    let tg: Int
    let pipe: MTLComputePipelineState
    var samples: [Double] = []
}

var variants: [Variant] = []
for k in kernels {
    guard let fn = library.makeFunction(name: k.name) else { print("missing \(k.name)"); continue }
    let pipe: MTLComputePipelineState
    do { pipe = try device.makeComputePipelineState(function: fn) }
    catch { print("pipeline failed \(k.name): \(error)"); continue }
    if k.tg > pipe.maxTotalThreadsPerThreadgroup {
        print("skip \(k.name): tg \(k.tg) > max \(pipe.maxTotalThreadsPerThreadgroup)")
        continue
    }
    variants.append(Variant(name: k.name, grid: k.grid, tg: k.tg, pipe: pipe))
}

var poolCursor = 0
func runOnce(_ v: Variant, slotOverride: Int? = nil) -> Double {
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(v.pipe)
    for l in 0..<layers {
        let slot = slotOverride ?? ((poolCursor + l) % poolSlots)
        enc.setBuffer(inputBuf, offset: 0, index: 0)
        enc.setBuffer(weightBuf, offset: slot * weightBytesPerLayer, index: 1)
        enc.setBuffer(scaleBuf, offset: slot * scaleBytesPerLayer, index: 2)
        enc.setBuffer(outBuf, offset: l * 1024, index: 3)
        enc.dispatchThreads(MTLSize(width: v.grid, height: 1, depth: 1),
                            threadsPerThreadgroup: MTLSize(width: v.tg, height: 1, depth: 1))
    }
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    poolCursor = (poolCursor + layers) % poolSlots
    return (cb.gpuEndTime - cb.gpuStartTime) * 1e6
}

// ---- coverage / correctness self-check -------------------------------------
// A geometry arm that under-covers the 512 output rows would look fast for free.
// Every arm must write all 512 rows and agree with the shipped arm.
func bf16ToFloat(_ bits: UInt16) -> Float {
    return Float(bitPattern: UInt32(bits) << 16)
}
func readOut() -> [Float] {
    let p = outBuf.contents().bindMemory(to: UInt16.self, capacity: layers * 512)
    return (0..<512).map { bf16ToFloat(p[$0]) }
}
var reference: [Float] = []
var verdicts: [String: String] = [:]
for v in variants {
    memset(outBuf.contents(), 0, layers * 1024)
    _ = runOnce(v, slotOverride: 0)
    let out = readOut()
    if v.name.hasPrefix("s") { verdicts[v.name] = "stream-control"; continue }
    let zeros = out.filter { $0 == 0.0 }.count
    if reference.isEmpty { reference = out; verdicts[v.name] = "reference(zeros=\(zeros))"; continue }
    var maxRel: Float = 0
    for i in 0..<512 {
        let d = abs(out[i] - reference[i])
        let s = max(abs(reference[i]), 1e-6)
        maxRel = max(maxRel, d / s)
    }
    verdicts[v.name] = String(format: "zeros=%d maxrel=%.2e", zeros, maxRel)
}
print("# coverage check (all arms must write 512 rows and match the shipped arm):")
for v in variants where !v.name.hasPrefix("s") {
    print("#   \(v.name): \(verdicts[v.name] ?? "?")")
}

// Global DVFS warmup: the Apple GPU needs O(100 ms) of sustained work before it
// reaches the steady clock the in-situ decode loop runs at. Measured without
// this, whichever variant runs first is penalised ~3x.
let warmStart = Date()
var warmRounds = 0
while Date().timeIntervalSince(warmStart) < 4.0 {
    for v in variants { _ = runOnce(v) }
    warmRounds += 1
}
print("# dvfs warmup rounds: \(warmRounds)")

// Round-robin interleaved sampling so residual drift hits every arm equally.
for _ in 0..<iters {
    for i in 0..<variants.count { variants[i].samples.append(runOnce(variants[i])) }
}

print("variant             us/call   us/step     GB/s  us/call_min  spread%    thr")
for v in variants {
    let s = v.samples.sorted()
    let med = s[s.count / 2]
    let best = s[0]
    let perCall = med / Double(layers)
    let gbs = Double(bytesPerCall) / (perCall * 1e-6) / 1e9
    let spread = (s[s.count - 1] - best) / best * 100.0
    print(String(format: "%-18@ %9.3f %9.2f %8.1f %9.3f %9.2f %7d",
                 v.name as NSString, perCall, med, gbs,
                 best / Double(layers), spread, v.grid))
}
