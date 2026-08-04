// Research-only host compute-ceiling probe (not part of the submission).
//
// The 512-token prefill forward reuses each weight 512 times, so unlike decode
// it is a FLOP-bound regime. research/host_bandwidth_ceiling.swift measures the
// DRAM ceiling; this measures the other axis: scalar FMA throughput and
// simdgroup-matrix (MMA) throughput, which is what MLX's steel GEMM and the
// NVFP4 gather-GEMM actually issue.
//
// Build and run:
//   xcrun swiftc -O research/host_flop_ceiling.swift -o /tmp/flopceil
//   /tmp/flopceil [iterations]
//
// Every kernel consumes its accumulators into a device buffer so the arithmetic
// cannot be eliminated; each kernel also reports the loop-trip count it actually
// executed, read back from the GPU, as a self-validation counter.

import Foundation
import Metal

let shaderSource = """
#include <metal_stdlib>
#include <metal_simdgroup_matrix>
using namespace metal;

// 8 independent FMA chains per thread: enough to cover ALU latency.
kernel void fma_f32(device float *out [[buffer(0)]],
                    device atomic_uint *trips [[buffer(1)]],
                    constant uint &iters [[buffer(2)]],
                    uint gid [[thread_position_in_grid]]) {
    float seed = float(gid & 1023) * 1e-6f + 1.0f;
    float b = 1.0000001f;
    float a0 = seed, a1 = seed + 1.0f, a2 = seed + 2.0f, a3 = seed + 3.0f;
    float a4 = seed + 4.0f, a5 = seed + 5.0f, a6 = seed + 6.0f, a7 = seed + 7.0f;
    uint n = 0;
    for (uint i = 0; i < iters; ++i) {
        a0 = fma(a0, b, seed); a1 = fma(a1, b, seed);
        a2 = fma(a2, b, seed); a3 = fma(a3, b, seed);
        a4 = fma(a4, b, seed); a5 = fma(a5, b, seed);
        a6 = fma(a6, b, seed); a7 = fma(a7, b, seed);
        n += 1;
    }
    out[gid] = a0 + a1 + a2 + a3 + a4 + a5 + a6 + a7;
    if (gid == 0) { atomic_store_explicit(trips, n, memory_order_relaxed); }
}

kernel void fma_f16(device float *out [[buffer(0)]],
                    device atomic_uint *trips [[buffer(1)]],
                    constant uint &iters [[buffer(2)]],
                    uint gid [[thread_position_in_grid]]) {
    half seed = half(float(gid & 255) * 1e-3f + 1.0f);
    half b = half(1.0009765625h);
    half a0 = seed, a1 = seed + 1.0h, a2 = seed + 2.0h, a3 = seed + 3.0h;
    half a4 = seed + 4.0h, a5 = seed + 5.0h, a6 = seed + 6.0h, a7 = seed + 7.0h;
    uint n = 0;
    for (uint i = 0; i < iters; ++i) {
        a0 = fma(a0, b, seed); a1 = fma(a1, b, seed);
        a2 = fma(a2, b, seed); a3 = fma(a3, b, seed);
        a4 = fma(a4, b, seed); a5 = fma(a5, b, seed);
        a6 = fma(a6, b, seed); a7 = fma(a7, b, seed);
        n += 1;
    }
    out[gid] = float(a0 + a1 + a2 + a3 + a4 + a5 + a6 + a7);
    if (gid == 0) { atomic_store_explicit(trips, n, memory_order_relaxed); }
}

// 4 independent 8x8x8 MMA chains per simdgroup.
kernel void mma_f16(device float *out [[buffer(0)]],
                    device atomic_uint *trips [[buffer(1)]],
                    constant uint &iters [[buffer(2)]],
                    uint gid [[thread_position_in_grid]],
                    uint sg [[simdgroup_index_in_threadgroup]],
                    uint tgid [[threadgroup_position_in_grid]],
                    uint sgs [[simdgroups_per_threadgroup]]) {
    simdgroup_matrix<half, 8, 8> A = make_filled_simdgroup_matrix<half, 8, 8>(0.001h);
    simdgroup_matrix<half, 8, 8> B = make_filled_simdgroup_matrix<half, 8, 8>(0.002h);
    simdgroup_matrix<float, 8, 8> c0 = make_filled_simdgroup_matrix<float, 8, 8>(0.0f);
    simdgroup_matrix<float, 8, 8> c1 = c0, c2 = c0, c3 = c0;
    uint n = 0;
    for (uint i = 0; i < iters; ++i) {
        simdgroup_multiply_accumulate(c0, A, B, c0);
        simdgroup_multiply_accumulate(c1, A, B, c1);
        simdgroup_multiply_accumulate(c2, A, B, c2);
        simdgroup_multiply_accumulate(c3, A, B, c3);
        n += 1;
    }
    simdgroup_multiply_accumulate(c0, A, B, c1);
    simdgroup_multiply_accumulate(c2, A, B, c3);
    simdgroup_multiply_accumulate(c0, A, B, c2);
    uint slot = (tgid * sgs + sg) * 64;
    simdgroup_store(c0, out + slot, 8);
    if (gid == 0) { atomic_store_explicit(trips, n, memory_order_relaxed); }
}

kernel void mma_bf16(device float *out [[buffer(0)]],
                     device atomic_uint *trips [[buffer(1)]],
                     constant uint &iters [[buffer(2)]],
                     uint gid [[thread_position_in_grid]],
                     uint sg [[simdgroup_index_in_threadgroup]],
                     uint tgid [[threadgroup_position_in_grid]],
                     uint sgs [[simdgroups_per_threadgroup]]) {
    simdgroup_matrix<bfloat, 8, 8> A = make_filled_simdgroup_matrix<bfloat, 8, 8>(bfloat(0.001f));
    simdgroup_matrix<bfloat, 8, 8> B = make_filled_simdgroup_matrix<bfloat, 8, 8>(bfloat(0.002f));
    simdgroup_matrix<float, 8, 8> c0 = make_filled_simdgroup_matrix<float, 8, 8>(0.0f);
    simdgroup_matrix<float, 8, 8> c1 = c0, c2 = c0, c3 = c0;
    uint n = 0;
    for (uint i = 0; i < iters; ++i) {
        simdgroup_multiply_accumulate(c0, A, B, c0);
        simdgroup_multiply_accumulate(c1, A, B, c1);
        simdgroup_multiply_accumulate(c2, A, B, c2);
        simdgroup_multiply_accumulate(c3, A, B, c3);
        n += 1;
    }
    simdgroup_multiply_accumulate(c0, A, B, c1);
    simdgroup_multiply_accumulate(c2, A, B, c3);
    simdgroup_multiply_accumulate(c0, A, B, c2);
    uint slot = (tgid * sgs + sg) * 64;
    simdgroup_store(c0, out + slot, 8);
    if (gid == 0) { atomic_store_explicit(trips, n, memory_order_relaxed); }
}
"""

guard let device = MTLCreateSystemDefaultDevice(),
      let queue = device.makeCommandQueue()
else {
    fatalError("no Metal device")
}

let iterations = CommandLine.arguments.count > 1 ? Int(CommandLine.arguments[1])! : 12
let library = try device.makeLibrary(source: shaderSource, options: nil)
func pipeline(_ name: String) throws -> MTLComputePipelineState {
    try device.makeComputePipelineState(function: library.makeFunction(name: name)!)
}

let threadgroup = 256
let outBuffer = device.makeBuffer(length: 1 << 26, options: .storageModeShared)!
let tripBuffer = device.makeBuffer(length: 4, options: .storageModeShared)!

print(String(format: "device=%@ iterations=%d", device.name, iterations))

func run(_ name: String, _ pipe: MTLComputePipelineState,
         threads: Int, loops: UInt32, flopsPerLoopPerThread: Double) {
    var best = Double.greatestFiniteMagnitude
    var trips: UInt32 = 0
    for _ in 0..<iterations {
        tripBuffer.contents().bindMemory(to: UInt32.self, capacity: 1)[0] = 0
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(pipe)
        enc.setBuffer(outBuffer, offset: 0, index: 0)
        enc.setBuffer(tripBuffer, offset: 0, index: 1)
        var n = loops
        enc.setBytes(&n, length: 4, index: 2)
        enc.dispatchThreads(MTLSize(width: threads, height: 1, depth: 1),
                            threadsPerThreadgroup: MTLSize(width: threadgroup, height: 1, depth: 1))
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        best = min(best, cb.gpuEndTime - cb.gpuStartTime)
        trips = tripBuffer.contents().bindMemory(to: UInt32.self, capacity: 1)[0]
    }
    let flops = Double(threads) * Double(loops) * flopsPerLoopPerThread
    let ok = trips == loops ? "ok" : "TRIP-MISMATCH"
    print(String(format: "%-10@ threads=%8d loops=%6d  gpu=%8.3f ms -> %7.2f TFLOP/s  (trips=%u %@)",
                 name as NSString, threads, Int(loops), best * 1e3,
                 flops / best / 1e12, trips, ok as NSString))
}

let fmaF32 = try pipeline("fma_f32")
let fmaF16 = try pipeline("fma_f16")
let mmaF16 = try pipeline("mma_f16")
let mmaBF16 = try pipeline("mma_bf16")

for threads in [1 << 16, 1 << 18, 1 << 20] {
    run("fma_f32", fmaF32, threads: threads, loops: 20000, flopsPerLoopPerThread: 16)
}
for threads in [1 << 18, 1 << 20] {
    run("fma_f16", fmaF16, threads: threads, loops: 20000, flopsPerLoopPerThread: 16)
}
// 4 MMAs of 8x8x8 per loop per simdgroup = 4 * 1024 FLOP / 32 threads.
for threads in [1 << 16, 1 << 18, 1 << 20] {
    run("mma_f16", mmaF16, threads: threads, loops: 8000, flopsPerLoopPerThread: 128)
}
for threads in [1 << 16, 1 << 18, 1 << 20] {
    run("mma_bf16", mmaBF16, threads: threads, loops: 8000, flopsPerLoopPerThread: 128)
}
