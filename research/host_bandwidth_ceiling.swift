// Research-only host DRAM streaming-ceiling probe (not part of the submission).
//
// Build and run:
//   xcrun swiftc -O research/host_bandwidth_ceiling.swift -o /tmp/bwceil
//   /tmp/bwceil [buffer_gib] [iterations]
//
// Reports achieved GB/s for a pure streaming read, a read+write copy, and a
// read-modify-write, using Metal GPU timestamps and wall time.

import Foundation
import Metal

let shaderSource = """
#include <metal_stdlib>
using namespace metal;

kernel void stream_read(device const float4 *in [[buffer(0)]],
                        device float *out [[buffer(1)]],
                        constant uint &n4 [[buffer(2)]],
                        uint gid [[thread_position_in_grid]],
                        uint gsize [[threads_per_grid]]) {
    float4 acc = float4(0.0f);
    for (uint i = gid; i < n4; i += gsize) {
        acc += in[i];
    }
    float s = acc.x + acc.y + acc.z + acc.w;
    if (s == 1.2345678e30f) {
        out[gid] = s;
    }
}

kernel void stream_copy(device const float4 *in [[buffer(0)]],
                        device float4 *out [[buffer(1)]],
                        constant uint &n4 [[buffer(2)]],
                        uint gid [[thread_position_in_grid]],
                        uint gsize [[threads_per_grid]]) {
    for (uint i = gid; i < n4; i += gsize) {
        out[i] = in[i];
    }
}

kernel void stream_scale(device float4 *data [[buffer(0)]],
                         constant uint &n4 [[buffer(1)]],
                         uint gid [[thread_position_in_grid]],
                         uint gsize [[threads_per_grid]]) {
    for (uint i = gid; i < n4; i += gsize) {
        data[i] = data[i] * 1.0000001f;
    }
}
"""

guard let device = MTLCreateSystemDefaultDevice(),
      let queue = device.makeCommandQueue()
else {
    fatalError("no Metal device")
}

let bufferGiB = CommandLine.arguments.count > 1 ? Double(CommandLine.arguments[1])! : 2.0
let iterations = CommandLine.arguments.count > 2 ? Int(CommandLine.arguments[2])! : 12

let bytes = Int(bufferGiB * 1024 * 1024 * 1024)
let n4 = UInt32(bytes / 16)

let library = try device.makeLibrary(source: shaderSource, options: nil)
func pipeline(_ name: String) throws -> MTLComputePipelineState {
    try device.makeComputePipelineState(function: library.makeFunction(name: name)!)
}
let readPipe = try pipeline("stream_read")
let copyPipe = try pipeline("stream_copy")
let scalePipe = try pipeline("stream_scale")

let src = device.makeBuffer(length: bytes, options: .storageModeShared)!
let dst = device.makeBuffer(length: bytes, options: .storageModeShared)!
let sink = device.makeBuffer(length: 1 << 22, options: .storageModeShared)!

// Touch both buffers so their pages are resident before timing.
let srcPtr = src.contents().bindMemory(to: Float.self, capacity: bytes / 4)
for i in stride(from: 0, to: bytes / 4, by: 1024) { srcPtr[i] = Float(i % 97) + 0.5 }
let dstPtr = dst.contents().bindMemory(to: Float.self, capacity: bytes / 4)
for i in stride(from: 0, to: bytes / 4, by: 1024) { dstPtr[i] = 1.0 }

print(String(format: "device=%@ buffer=%.2f GiB iterations=%d recommendedWorkingSet=%.1f GiB",
             device.name, bufferGiB, iterations,
             Double(device.recommendedMaxWorkingSetSize) / 1_073_741_824.0))

func run(_ name: String,
         _ pipe: MTLComputePipelineState,
         movedBytes: Int,
         threads: Int,
         encode: (MTLComputeCommandEncoder) -> Void) {
    var bestGPU = Double.greatestFiniteMagnitude
    var bestWall = Double.greatestFiniteMagnitude
    let tgSize = min(pipe.maxTotalThreadsPerThreadgroup, 256)
    for _ in 0..<iterations {
        let wallStart = Date()
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(pipe)
        encode(enc)
        enc.dispatchThreads(MTLSize(width: threads, height: 1, depth: 1),
                            threadsPerThreadgroup: MTLSize(width: tgSize, height: 1, depth: 1))
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        bestWall = min(bestWall, Date().timeIntervalSince(wallStart))
        bestGPU = min(bestGPU, cb.gpuEndTime - cb.gpuStartTime)
    }
    print(String(format: "%-12@ threads=%8d moved=%6.2f GB  gpu=%7.3f ms -> %6.1f GB/s   wall=%7.3f ms -> %6.1f GB/s",
                 name as NSString, threads, Double(movedBytes) / 1e9,
                 bestGPU * 1e3, Double(movedBytes) / bestGPU / 1e9,
                 bestWall * 1e3, Double(movedBytes) / bestWall / 1e9))
}

for threads in [1 << 16, 1 << 18, 1 << 20, 1 << 22] {
    run("read", readPipe, movedBytes: bytes, threads: threads) { enc in
        enc.setBuffer(src, offset: 0, index: 0)
        enc.setBuffer(sink, offset: 0, index: 1)
        var n = n4
        enc.setBytes(&n, length: 4, index: 2)
    }
}
for threads in [1 << 18, 1 << 20, 1 << 22] {
    run("copy(r+w)", copyPipe, movedBytes: 2 * bytes, threads: threads) { enc in
        enc.setBuffer(src, offset: 0, index: 0)
        enc.setBuffer(dst, offset: 0, index: 1)
        var n = n4
        enc.setBytes(&n, length: 4, index: 2)
    }
}
for threads in [1 << 20, 1 << 22] {
    run("rmw(r+w)", scalePipe, movedBytes: 2 * bytes, threads: threads) { enc in
        enc.setBuffer(dst, offset: 0, index: 0)
        var n = n4
        enc.setBytes(&n, length: 4, index: 1)
    }
}
