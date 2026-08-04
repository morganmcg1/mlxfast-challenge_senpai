// Research-only host probe (not part of the submission).
//
// Prints `MTLDevice.architecture.name`, which is the string MLX reads in
// `Device::Device()` (`device.cpp:574-595`) to pick its command-buffer commit
// thresholds, and re-derives those thresholds here so the mapping is measured
// rather than inferred. Also re-measures the isolated empty-dispatch cost at a
// few threadgroup counts, which is the upper bound the in-situ figure from the
// scored-path instrument is compared against.
//
// Build and run:
//   xcrun swiftc -O research/host_device_arch.swift -o /tmp/devarch && /tmp/devarch

import Foundation
import Metal

let src = """
#include <metal_stdlib>
using namespace metal;
kernel void empty_dispatch(device uint *sink [[buffer(0)]],
                           constant uint &control [[buffer(1)]],
                           uint gid [[thread_position_in_grid]]) {
    if (control == 0xFFFFFFFFu) { sink[gid & 255u] = gid; }
}
"""

let device = MTLCreateSystemDefaultDevice()!
let arch = device.architecture.name
print("device.name                 \(device.name)")
print("device.architecture.name    \(arch)")

var gen = 0
if arch.count >= 3 {
    let chars = Array(arch)
    let tens = Int(String(chars[chars.count - 3])) ?? 0
    let ones = Int(String(chars[chars.count - 2])) ?? 0
    gen = tens * 10 + ones
}
let last = arch.last!
let (maxOps, maxMB): (Int, Int)
switch last {
case "p": (maxOps, maxMB) = (20, 40)
case "g": (maxOps, maxMB) = (40, 40)
case "s": (maxOps, maxMB) = (50, 50)
case "d": (maxOps, maxMB) = (50, 50)
default: (maxOps, maxMB) = (40, 40)
}
print("MLX arch_gen                \(gen)")
print("MLX class char              '\(last)'")
print("MLX max_ops_per_buffer      \(maxOps)")
print("MLX max_mb_per_buffer       \(maxMB)   (Mi *items*, not bytes)")
print("  -> a 256 MiB uint32 pool is 67.1 Mi items = \(String(format: "%.2f", 67.108864 / Double(maxMB)))x the threshold")
print("  -> 512x8192 + 8192x2048 bf16 operands are 21.0 Mi items = \(String(format: "%.2f", 20.97152 / Double(maxMB)))x")

let lib = try! device.makeLibrary(source: src, options: nil)
let pipe = try! device.makeComputePipelineState(function: lib.makeFunction(name: "empty_dispatch")!)
let queue = device.makeCommandQueue()!
let sink = device.makeBuffer(length: 1024, options: .storageModeShared)!
var control: UInt32 = 7

print("\nisolated empty dispatch (one command buffer, N serialised dispatches)")
for tg in [1, 8, 40, 160, 512] {
    var best = Double.infinity
    for _ in 0..<5 {
        let n = 2000
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(pipe)
        enc.setBuffer(sink, offset: 0, index: 0)
        enc.setBytes(&control, length: 4, index: 1)
        for _ in 0..<n {
            enc.dispatchThreadgroups(
                MTLSize(width: tg, height: 1, depth: 1),
                threadsPerThreadgroup: MTLSize(width: 256, height: 1, depth: 1))
            enc.memoryBarrier(scope: .buffers)
        }
        enc.endEncoding()
        let t0 = Date()
        cb.commit()
        cb.waitUntilCompleted()
        let us = Date().timeIntervalSince(t0) * 1e6 / Double(n)
        best = min(best, us)
    }
    print(String(format: "  tg=%4d  %.3f us/dispatch", tg, best))
}
