// r97-c GATE 0: is Metal's `simd_sum` bit-exactly reproducible by an explicit
// shuffle ladder, and is a two-level (grouped) decomposition also bit-exact?
//
// Both decode attention kernels reduce with `simd_sum` over 32 lanes. Any
// two-stage split of those kernels needs to know (a) the exact summation order
// the compiler picks, and (b) whether a hierarchical combine — reduce inside a
// group, then across groups — lands on the same float.
//
// Build/run:
//   swiftc -O research/nezuko_r97_simdsum_order_probe.swift \
//     -o /tmp/nezuko_simdsum_probe -framework Metal -framework Foundation
//   /tmp/nezuko_simdsum_probe

import Foundation
import Metal

let kVectors = 200_000
let kLanes = 32
let kThreads = kVectors * kLanes

let source = """
#include <metal_stdlib>
using namespace metal;

// The shipped kernels' reduction.
kernel void ref_simd_sum(device const float *in [[buffer(0)]],
                         device float *out [[buffer(1)]],
                         uint gid [[thread_position_in_grid]]) {
    float v = in[gid];
    out[gid] = simd_sum(v);
}

// Ascending XOR butterfly: the canonical Metal lowering.
kernel void xor_ascending(device const float *in [[buffer(0)]],
                          device float *out [[buffer(1)]],
                          uint gid [[thread_position_in_grid]]) {
    float v = in[gid];
    v += simd_shuffle_xor(v, 1u);
    v += simd_shuffle_xor(v, 2u);
    v += simd_shuffle_xor(v, 4u);
    v += simd_shuffle_xor(v, 8u);
    v += simd_shuffle_xor(v, 16u);
    out[gid] = v;
}

// Descending XOR butterfly: same set of adds, different association.
kernel void xor_descending(device const float *in [[buffer(0)]],
                           device float *out [[buffer(1)]],
                           uint gid [[thread_position_in_grid]]) {
    float v = in[gid];
    v += simd_shuffle_xor(v, 16u);
    v += simd_shuffle_xor(v, 8u);
    v += simd_shuffle_xor(v, 4u);
    v += simd_shuffle_xor(v, 2u);
    v += simd_shuffle_xor(v, 1u);
    out[gid] = v;
}

// Shift-down tree (broadcast back), the other common lowering.
kernel void shuffle_down_tree(device const float *in [[buffer(0)]],
                              device float *out [[buffer(1)]],
                              uint gid [[thread_position_in_grid]]) {
    float v = in[gid];
    v += simd_shuffle_down(v, 16u);
    v += simd_shuffle_down(v, 8u);
    v += simd_shuffle_down(v, 4u);
    v += simd_shuffle_down(v, 2u);
    v += simd_shuffle_down(v, 1u);
    out[gid] = simd_broadcast_first(v);
}

// Strict left-to-right lane order, the "obvious" serial answer.
kernel void prefix_sequential(device const float *in [[buffer(0)]],
                              device float *out [[buffer(1)]],
                              uint gid [[thread_position_in_grid]]) {
    float v = in[gid];
    float acc = 0.0f;
    for (uint l = 0; l < 32; ++l) {
        acc += simd_shuffle(v, l);
    }
    out[gid] = acc;
}

// The load-bearing question for a two-stage split: reduce within 4-lane groups
// (xor 1,2), then across the 8 groups (xor 4,8,16). If this equals simd_sum,
// a hierarchical/grouped combine is exactly reproducible.
kernel void two_level(device const float *in [[buffer(0)]],
                      device float *out [[buffer(1)]],
                      uint gid [[thread_position_in_grid]]) {
    float v = in[gid];
    v += simd_shuffle_xor(v, 1u);
    v += simd_shuffle_xor(v, 2u);
    float g = v;
    g += simd_shuffle_xor(g, 4u);
    g += simd_shuffle_xor(g, 8u);
    g += simd_shuffle_xor(g, 16u);
    out[gid] = g;
}
"""

guard let device = MTLCreateSystemDefaultDevice(),
      let queue = device.makeCommandQueue() else {
    fatalError("no Metal device")
}
print("device: \(device.name)")
if #available(macOS 14.0, *) {
    print("architecture: \(device.architecture.name)")
}
print("vectors: \(kVectors)  lanes: \(kLanes)  threads: \(kThreads)")

let library = try device.makeLibrary(source: source, options: nil)

// Adversarial input: random mantissa scaled by 2^e, e uniform in [-12, 12].
// Wide dynamic range inside a simdgroup is what makes association order visible.
var input = [Float](repeating: 0, count: kThreads)
var state: UInt64 = 0x9E3779B97F4A7C15
func next() -> UInt64 {
    state ^= state << 13
    state ^= state >> 7
    state ^= state << 17
    return state
}
for i in 0..<kThreads {
    let mant = Float(next() >> 40) / Float(1 << 24) * 2.0 - 1.0
    let e = Int(next() % 25) - 12
    input[i] = mant * powf(2.0, Float(e))
}

let inBuf = device.makeBuffer(bytes: &input,
                              length: kThreads * MemoryLayout<Float>.stride,
                              options: .storageModeShared)!

func run(_ name: String) -> [Float] {
    let fn = library.makeFunction(name: name)!
    let pso = try! device.makeComputePipelineState(function: fn)
    let outBuf = device.makeBuffer(length: kThreads * MemoryLayout<Float>.stride,
                                   options: .storageModeShared)!
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pso)
    enc.setBuffer(inBuf, offset: 0, index: 0)
    enc.setBuffer(outBuf, offset: 0, index: 1)
    enc.dispatchThreads(MTLSize(width: kThreads, height: 1, depth: 1),
                        threadsPerThreadgroup: MTLSize(width: 256, height: 1, depth: 1))
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    let p = outBuf.contents().bindMemory(to: Float.self, capacity: kThreads)
    return Array(UnsafeBufferPointer(start: p, count: kThreads))
}

func ulpDiff(_ a: Float, _ b: Float) -> UInt32 {
    if a == b { return 0 }
    func key(_ x: Float) -> Int64 {
        let bits = Int64(Int32(bitPattern: x.bitPattern))
        return bits < 0 ? (Int64(Int32.min) - bits) : bits
    }
    let d = key(a) - key(b)
    return UInt32(clamping: d < 0 ? -d : d)
}

let reference = run("ref_simd_sum")

for variant in ["xor_ascending", "xor_descending", "shuffle_down_tree",
                "prefix_sequential", "two_level"] {
    let got = run(variant)
    var exact = 0
    var maxUlp: UInt32 = 0
    for i in 0..<kThreads {
        if got[i].bitPattern == reference[i].bitPattern {
            exact += 1
        } else {
            maxUlp = max(maxUlp, ulpDiff(got[i], reference[i]))
        }
    }
    let pct = 100.0 * Double(exact) / Double(kThreads)
    print(String(format: "%-14@ vs simd_sum: bitexact %d/%d (%.3f%%)  max_ulp %u",
                 variant as NSString, exact, kThreads, pct, maxUlp))
}
