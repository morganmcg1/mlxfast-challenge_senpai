// Research-only (not part of the submission surface).
//
// PR #300 Stage 1 -- the H1 falsifier.
//
// H1: a threadgroup of any width can serialise MLX's 512-lane `rmsbfloat16`
// reduction tree over a 2048-wide bf16 row and produce a bit-identical FP32
// `acc` and a bit-identical `precise::rsqrt(acc/2048 + 1e-6)`.
//
// Kernel A (control)   -- 512 threads / 16 simdgroups, verbatim transcription
//                         of `lagunaResidualRMSNormKernel`'s prologue
//                         (LagunaRuntimeModel.swift:1021-1044) plus
//                         `lagunaNormReductionTail2048` (:763-791).
// Kernel B (candidate) -- 64 threads / 2 simdgroups, `virtual_per_thread = 8`,
//                         verbatim transcription of `lagunaNormAffineQKVBody`
//                         (LagunaRuntimeModel.swift:4938-4966).
// Kernel Bf (control)  -- B with a deliberate `+1.0f` fault injected into one
//                         partial accumulator. REQUIRED: proves the comparator
//                         can fail (standing rule 16).
//
// Comparison is exact integer equality on the raw uint32 bit patterns. No
// tolerance, no allclose.
//
// MLX JIT-compiles `metalKernel` sources with fast math DISABLED
// (Vendor/mlx-swift/.../backend/metal/device.cpp:631), so this harness does the
// same. Running with fast math on would compare a different program than the
// one production ships.
//
// Build/run:
//   swiftc -O research/fern_redundant_rmsnorm_bitwise.swift \
//     -o /tmp/fern_rmsnorm_bitwise -framework Metal -framework Foundation
//   /tmp/fern_rmsnorm_bitwise [path/to/real_rows.bin]

import Foundation
import Metal

let axisSize = 2048

// MARK: - Metal source

let metalSource = """
#include <metal_stdlib>
using namespace metal;

// ---------------------------------------------------------------------------
// A: the shipped 512-thread reduction.
// Prologue transcribed from LagunaRuntimeModel.swift:1032-1043 (the squaring
// loop and `simd_sum`), tail transcribed from :770-790
// (`lagunaNormReductionTail2048`). `local_total` is the only addition: it
// exports the FP32 accumulator the shipped kernel consumes but never writes.
// ---------------------------------------------------------------------------
kernel void tree_a_512(
    device const ushort* x   [[buffer(0)]],
    device uint2* out        [[buffer(1)]],
    uint row                 [[threadgroup_position_in_grid]],
    uint lid                 [[thread_position_in_threadgroup]],
    uint simd_lane           [[thread_index_in_simdgroup]],
    uint simd_group          [[simdgroup_index_in_threadgroup]])
{
    constexpr uint axis_size = 2048;
    constexpr uint n_reads = 4;
    constexpr uint simd_size = 32;

    threadgroup float local_inv_mean[1];
    threadgroup float local_sums[simd_size];
    threadgroup float local_total[1];

    uint base = row * axis_size + lid * n_reads;

    float acc = 0.0f;
    for (uint i = 0; i < n_reads; ++i) {
        float fv = float(as_type<bfloat>(x[base + i]));
        acc += fv * fv;
    }

    acc = simd_sum(acc);

    if (simd_group == 0) {
        local_sums[simd_lane] = 0.0f;
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    if (simd_lane == 0) {
        local_sums[simd_group] = acc;
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    if (simd_group == 0) {
        acc = simd_sum(local_sums[simd_lane]);
        if (simd_lane == 0) {
            local_inv_mean[0] = metal::precise::rsqrt(acc / 2048.0f + 1.0e-6f);
            local_total[0] = acc;
        }
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    float laguna_inv_mean = local_inv_mean[0];

    if (lid == 0) {
        out[row] = uint2(as_type<uint>(local_total[0]),
                         as_type<uint>(laguna_inv_mean));
    }
}

// ---------------------------------------------------------------------------
// B: the 64-thread virtualised reduction.
// Transcribed from LagunaRuntimeModel.swift:4937-4966 -- the prologue the
// shipped fused norm+affine QKV kernel already runs. FAULT is compile-time 0
// for the clean arm and 1 for the injected-fault control arm.
// ---------------------------------------------------------------------------
kernel void tree_b_64(
    device const ushort* x   [[buffer(0)]],
    device uint2* out        [[buffer(1)]],
    constant uint& fault     [[buffer(2)]],
    uint row                 [[threadgroup_position_in_grid]],
    uint lid                 [[thread_position_in_threadgroup]],
    uint simd_lid            [[thread_index_in_simdgroup]],
    uint simd_gid            [[simdgroup_index_in_threadgroup]])
{
    constexpr uint axis_size = 2048;
    constexpr uint n_reads = 4;
    constexpr uint norm_threads = axis_size / n_reads;   // 512 logical lanes
    constexpr uint real_threads = 64;
    constexpr uint virtual_per_thread = norm_threads / real_threads;  // 8
    constexpr uint simd_size = 32;
    constexpr uint num_simdgroups = 2;
    constexpr float norm_eps = 1.0e-6f;

    threadgroup float local_inv_mean[1];
    threadgroup float local_sums[simd_size];
    threadgroup float local_total[1];

    uint row_base = row * axis_size;

    if (lid < simd_size) {
        local_sums[lid] = 0.0f;
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);

    for (uint j = 0; j < virtual_per_thread; ++j) {
        uint base = (lid + j * real_threads) * n_reads;
        float acc = 0.0f;
        for (uint i = 0; i < n_reads; ++i) {
            float xi = float(as_type<bfloat>(x[row_base + base + i]));
            acc += xi * xi;
        }
        // Injected fault: perturbs exactly one logical lane's partial.
        if (fault != 0u && j == 3u && lid == 5u) {
            acc += 1.0f;
        }
        acc = simd_sum(acc);
        if (simd_lid == 0) {
            local_sums[simd_gid + num_simdgroups * j] = acc;
        }
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);

    if (simd_gid == 0) {
        float total = simd_sum(local_sums[simd_lid]);
        if (simd_lid == 0) {
            local_inv_mean[0] =
                metal::precise::rsqrt(total / float(axis_size) + norm_eps);
            local_total[0] = total;
        }
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    float laguna_inv_mean = local_inv_mean[0];

    if (lid == 0) {
        out[row] = uint2(as_type<uint>(local_total[0]),
                         as_type<uint>(laguna_inv_mean));
    }
}
"""

// MARK: - bf16 helpers

@inline(__always) func f32ToBf16RN(_ f: Float) -> UInt16 {
    let bits = f.bitPattern
    if (bits & 0x7F80_0000) == 0x7F80_0000 && (bits & 0x007F_FFFF) != 0 {
        return UInt16(truncatingIfNeeded: (bits >> 16) | 0x0040)  // quiet NaN
    }
    let lsb = (bits >> 16) & 1
    let rounded = bits &+ 0x7FFF &+ lsb
    return UInt16(truncatingIfNeeded: rounded >> 16)
}

@inline(__always) func bf16ToF32(_ h: UInt16) -> Float {
    Float(bitPattern: UInt32(h) << 16)
}

// MARK: - deterministic RNG

struct SplitMix64 {
    var state: UInt64
    mutating func next() -> UInt64 {
        state = state &+ 0x9E37_79B9_7F4A_7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
        z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
        return z ^ (z >> 31)
    }
    mutating func uniform() -> Float { Float(next() >> 40) / Float(1 << 24) }
    mutating func normal() -> Float {
        let u1 = max(uniform(), 1e-7), u2 = uniform()
        return sqrt(-2 * log(u1)) * cos(2 * .pi * u2)
    }
}

// MARK: - adversarial input construction

/// Each class is a named generator over one 2048-wide bf16 row.
struct RowClass {
    let name: String
    let count: Int
    let make: (inout SplitMix64, Int) -> [UInt16]
}

let bf16Max: Float = 3.3895314e38

let rowClasses: [RowClass] = [
    RowClass(name: "gaussian-realistic", count: 192) { rng, _ in
        (0..<axisSize).map { _ in f32ToBf16RN(rng.normal() * 2.0) }
    },
    RowClass(name: "wide-dynamic-range", count: 192) { rng, _ in
        (0..<axisSize).map { _ in
            let e = Int(rng.uniform() * 60) - 30
            let sign: Float = rng.uniform() < 0.5 ? -1 : 1
            return f32ToBf16RN(sign * (1.0 + rng.uniform()) * powf(2, Float(e)))
        }
    },
    RowClass(name: "cancellation-signs", count: 128) { rng, _ in
        (0..<axisSize).map { i in
            let m = (1.0 + rng.uniform()) * powf(2, Float(Int(rng.uniform() * 20) - 10))
            return f32ToBf16RN(i % 2 == 0 ? m : -m)
        }
    },
    RowClass(name: "bf16-denormals", count: 96) { rng, _ in
        (0..<axisSize).map { _ in
            // bf16 subnormals: exponent field 0, non-zero mantissa.
            UInt16(truncatingIfNeeded: (rng.next() & 0x7F) | (rng.next() & 0x8000))
        }
    },
    RowClass(name: "signed-zeros", count: 64) { rng, _ in
        (0..<axisSize).map { _ in rng.uniform() < 0.5 ? UInt16(0x8000) : UInt16(0x0000) }
    },
    RowClass(name: "all-equal", count: 64) { rng, _ in
        let v = f32ToBf16RN((rng.uniform() - 0.5) * 8)
        return [UInt16](repeating: v, count: axisSize)
    },
    RowClass(name: "one-huge-among-tiny", count: 96) { rng, _ in
        var r = (0..<axisSize).map { _ in f32ToBf16RN(rng.normal() * 1e-20) }
        r[Int(rng.next() % UInt64(axisSize))] = f32ToBf16RN(1e18)
        return r
    },
    RowClass(name: "overflow-to-inf", count: 64) { rng, _ in
        (0..<axisSize).map { _ in f32ToBf16RN(bf16Max * (rng.uniform() < 0.5 ? -1 : 1)) }
    },
    RowClass(name: "mixed-magnitude-blocks", count: 128) { rng, _ in
        // Each 128-element simdgroup block gets its own exponent scale, so the
        // per-block partials that meet in `local_sums` differ by many orders.
        (0..<axisSize).map { i in
            let blk = i / 128
            return f32ToBf16RN(rng.normal() * powf(2, Float(blk * 4 - 32)))
        }
    },
    RowClass(name: "near-eps-rms", count: 64) { rng, _ in
        // acc/2048 comparable to the 1e-6 epsilon, so rsqrt sits on the knee.
        (0..<axisSize).map { _ in f32ToBf16RN(rng.normal() * 1e-3) }
    },
]

// MARK: - Metal setup

guard let device = MTLCreateSystemDefaultDevice(),
    let queue = device.makeCommandQueue()
else { fatalError("no Metal device") }

let options = MTLCompileOptions()
options.fastMathEnabled = false  // matches MLX device.cpp:631

let library: MTLLibrary
do {
    library = try device.makeLibrary(source: metalSource, options: options)
} catch {
    fatalError("compile failed: \(error)")
}

func pipeline(_ name: String) -> MTLComputePipelineState {
    guard let fn = library.makeFunction(name: name) else { fatalError("no \(name)") }
    return try! device.makeComputePipelineState(function: fn)
}

let pipeA = pipeline("tree_a_512")
let pipeB = pipeline("tree_b_64")

// MARK: - build the input set

var rng = SplitMix64(state: 0x5EED_1234_ABCD_0001)
var rows: [UInt16] = []
var labels: [String] = []

for cls in rowClasses {
    for i in 0..<cls.count {
        rows.append(contentsOf: cls.make(&rng, i))
        labels.append(cls.name)
    }
}
let syntheticRowCount = labels.count

// Optional real decoder hidden states dumped by research/fern_hidden_dump.patch.
if CommandLine.arguments.count > 1 {
    let path = CommandLine.arguments[1]
    guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)) else {
        fatalError("cannot read real-row file \(path)")
    }
    let n = data.count / (axisSize * 2)
    guard n > 0 else { fatalError("real-row file too small: \(data.count) bytes") }
    data.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
        let p = raw.bindMemory(to: UInt16.self)
        for r in 0..<n {
            rows.append(contentsOf: (0..<axisSize).map { p[r * axisSize + $0] })
            labels.append("real-decode-hidden-state")
        }
    }
    print("loaded \(n) real decoder rows from \(path)")
} else {
    print("NOTE: no real-row file supplied; synthetic classes only")
}

let rowCount = labels.count
print("rows: \(rowCount) (\(syntheticRowCount) synthetic, \(rowCount - syntheticRowCount) real)")

let inBuf = device.makeBuffer(bytes: rows, length: rows.count * 2, options: .storageModeShared)!
let outBytes = rowCount * MemoryLayout<SIMD2<UInt32>>.stride
let outA = device.makeBuffer(length: outBytes, options: .storageModeShared)!
let outB = device.makeBuffer(length: outBytes, options: .storageModeShared)!
let outBf = device.makeBuffer(length: outBytes, options: .storageModeShared)!

func dispatch(
    _ pipe: MTLComputePipelineState, _ out: MTLBuffer, threads: Int, fault: UInt32?
) {
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipe)
    enc.setBuffer(inBuf, offset: 0, index: 0)
    enc.setBuffer(out, offset: 0, index: 1)
    if var f = fault { enc.setBytes(&f, length: 4, index: 2) }
    enc.dispatchThreadgroups(
        MTLSize(width: rowCount, height: 1, depth: 1),
        threadsPerThreadgroup: MTLSize(width: threads, height: 1, depth: 1))
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    if let e = cb.error { fatalError("dispatch failed: \(e)") }
}

// Matched controls: same session, same input buffer, interleaved A/B/Bf.
dispatch(pipeA, outA, threads: 512, fault: nil)
dispatch(pipeB, outB, threads: 64, fault: 0)
dispatch(pipeA, outA, threads: 512, fault: nil)
dispatch(pipeB, outBf, threads: 64, fault: 1)

// MARK: - exact comparison

let a = outA.contents().bindMemory(to: SIMD2<UInt32>.self, capacity: rowCount)
let b = outB.contents().bindMemory(to: SIMD2<UInt32>.self, capacity: rowCount)
let bf = outBf.contents().bindMemory(to: SIMD2<UInt32>.self, capacity: rowCount)

@inline(__always) func ulpGap(_ x: UInt32, _ y: UInt32) -> UInt64 {
    // Monotone-ordered float compare; both operands are non-negative here.
    x > y ? UInt64(x - y) : UInt64(y - x)
}

struct Tally {
    var total = 0
    var accMismatch = 0
    var rsqrtMismatch = 0
    var worstAccUlp: UInt64 = 0
    var worstRsqrtUlp: UInt64 = 0
    var firstBad = -1
}

func compare(_ cand: UnsafeMutablePointer<SIMD2<UInt32>>) -> [String: Tally] {
    var byClass: [String: Tally] = [:]
    for r in 0..<rowCount {
        var t = byClass[labels[r]] ?? Tally()
        t.total += 1
        if a[r].x != cand[r].x {
            t.accMismatch += 1
            t.worstAccUlp = max(t.worstAccUlp, ulpGap(a[r].x, cand[r].x))
            if t.firstBad < 0 { t.firstBad = r }
        }
        if a[r].y != cand[r].y {
            t.rsqrtMismatch += 1
            t.worstRsqrtUlp = max(t.worstRsqrtUlp, ulpGap(a[r].y, cand[r].y))
            if t.firstBad < 0 { t.firstBad = r }
        }
        byClass[labels[r]] = t
    }
    return byClass
}

func report(_ title: String, _ tallies: [String: Tally]) -> (Int, Int) {
    print("\n=== \(title) ===")
    print(
        "class".padding(toLength: 26, withPad: " ", startingAt: 0)
            + "rows   acc!=  rsqrt!=  worstAccULP  worstRsqrtULP")
    var totalAcc = 0, totalRsqrt = 0
    for cls in rowClasses.map({ $0.name }) + ["real-decode-hidden-state"] {
        guard let t = tallies[cls] else { continue }
        totalAcc += t.accMismatch
        totalRsqrt += t.rsqrtMismatch
        print(
            cls.padding(toLength: 26, withPad: " ", startingAt: 0)
                + String(format: "%-6d %-6d %-8d %-12llu %-12llu",
                         t.total, t.accMismatch, t.rsqrtMismatch,
                         t.worstAccUlp, t.worstRsqrtUlp))
    }
    print("TOTAL rows=\(rowCount) accMismatch=\(totalAcc) rsqrtMismatch=\(totalRsqrt)")
    return (totalAcc, totalRsqrt)
}

let clean = compare(b)
let (cleanAcc, cleanRsqrt) = report("CLEAN ARM  A(512) vs B(64)", clean)

let faulted = compare(bf)
let (faultAcc, faultRsqrt) = report("FAULT-INJECTION CONTROL  A(512) vs B+1.0f", faulted)

print("\n--- verdict ---")
let comparatorLive = (faultAcc + faultRsqrt) > 0
print("comparator can fail (fault arm mismatched): \(comparatorLive)")
print("clean arm bit-identical: \(cleanAcc == 0 && cleanRsqrt == 0)")

if !comparatorLive {
    print("RESULT: INVALID -- the comparator could not detect an injected fault.")
    exit(2)
}
if cleanAcc == 0 && cleanRsqrt == 0 {
    print("RESULT: H1 SUPPORTED -- 64-thread tree is bit-identical on all \(rowCount) rows.")
    exit(0)
}
print("RESULT: H1 REFUTED -- \(cleanAcc) acc and \(cleanRsqrt) rsqrt mismatches.")
exit(1)
