// Research-only (not part of the submission).
//
// M2 pricing probe: is it worth deleting the routed-prefill sorted row gather
// and instead teaching the sorted-rhs gather-GEMM to read x through a row
// index array (lhs_indices)?
//
// The mechanism has two halves and they pull in opposite directions:
//
//   half (a)  the gather kernel itself disappears.
//             2 MiB read + 16 MiB write per routed layer, deleted outright.
//
//   half (b)  the GEMM's x read changes from a sequential walk over a
//             contiguous 16 MiB sorted copy into a permuted walk over the
//             512-row 2 MiB source with 8x reuse (topK = 8).
//             This can be cheaper (8x fewer useful bytes) or dearer
//             (scattered rows, extra index load).
//
// Shapes are the ones actually observed on this tree by the Step 0 census:
//   sortedX [4096, 1, 2048] bfloat16, source x [512, 2048] bfloat16
//   -> row = 2048 * 2 B = 4 kB, source 2 MiB, sorted copy 16 MiB.
//
// Two cache regimes are measured because in situ the 16 MiB sorted copy is
// written and then immediately re-read, while a 453 MB expert-weight stream
// runs through the same cache hierarchy:
//   L = 1  small working set, both arms cache-warm
//   L = 8  144 MiB working set, DRAM traffic forced
// Both are reported; the decision uses whichever is MORE favourable to the
// mechanism, so a STOP verdict is robust.
//
// Every measured quantity here is an UPPER BOUND on the real saving:
//   * t_gather is a lower bound on MLX's general Gather kernel (this is a
//     pure row copy with no stride/offset/bounds machinery), so deleting it
//     saves at least this much.
//   * t_perm reads each 4 kB row fully contiguously, which is the most
//     favourable possible permuted access pattern. The real sorted-rhs kernel
//     reads bm x bk = 16 rows x 64 B tiles, i.e. 16 scattered 64 B loads, so
//     the real t_perm is worse and the real half (b) is smaller.
//
// Build/run:
//   xcrun swiftc -O research/maple_fern_m2_gather_probe.swift \
//     -framework Metal -framework Foundation -o /tmp/m2probe
//   /tmp/m2probe 1 7
//   /tmp/m2probe 8 7

import Foundation
import Metal

let source = """
#include <metal_stdlib>
using namespace metal;

// One threadgroup per sorted row. 256 threads x uint4 = 4096 B = one row.
constant constexpr uint VEC_PER_ROW = 256;

// half (a): materialise the sorted copy. 2 MiB read + 16 MiB write per layer.
kernel void t_gather(
    device const uint4* src [[buffer(0)]],
    device uint4* dst [[buffer(1)]],
    device const uint* row_order [[buffer(2)]],
    uint tgid [[threadgroup_position_in_grid]],
    uint tid [[thread_position_in_threadgroup]])
{
    uint sr = row_order[tgid];
    dst[tgid * VEC_PER_ROW + tid] = src[sr * VEC_PER_ROW + tid];
}

// half (b) arm 1: the GEMM reads the contiguous 16 MiB sorted copy.
kernel void t_seq(
    device const uint4* dst [[buffer(0)]],
    device const uint* row_order [[buffer(1)]],
    device uint* out [[buffer(2)]],
    uint tgid [[threadgroup_position_in_grid]],
    uint tid [[thread_position_in_threadgroup]])
{
    uint4 v = dst[tgid * VEC_PER_ROW + tid];
    uint acc = v.x ^ v.y ^ v.z ^ v.w;
    if (acc == 0xFFFFFFFFu) { out[tgid] = acc; }
}

// half (b) arm 2: the GEMM reads the same logical elements from the 2 MiB
// source through row_order. Identical arithmetic, different addressing, plus
// the index load the indirection would really cost.
kernel void t_perm(
    device const uint4* src [[buffer(0)]],
    device const uint* row_order [[buffer(1)]],
    device uint* out [[buffer(2)]],
    uint tgid [[threadgroup_position_in_grid]],
    uint tid [[thread_position_in_threadgroup]])
{
    uint sr = row_order[tgid];
    uint4 v = src[sr * VEC_PER_ROW + tid];
    uint acc = v.x ^ v.y ^ v.z ^ v.w;
    if (acc == 0xFFFFFFFFu) { out[tgid] = acc; }
}
"""

let args = CommandLine.arguments
let layers = args.count > 1 ? (Int(args[1]) ?? 1) : 1
let reps = args.count > 2 ? (Int(args[2]) ?? 7) : 7
let discard = 2

let tokens = 512
let sortedRows = 4096
let hidden = 2048
let topK = sortedRows / tokens

let vecPerRow = hidden / 8              // uint4 = 8 ushorts
let srcVecs = layers * tokens * vecPerRow
let dstVecs = layers * sortedRows * vecPerRow
let srcBytes = srcVecs * 16
let dstBytes = dstVecs * 16

guard let device = MTLCreateSystemDefaultDevice() else {
    fatalError("no Metal device")
}
let queue = device.makeCommandQueue()!
let library = try device.makeLibrary(source: source, options: nil)

func pipeline(_ name: String) throws -> MTLComputePipelineState {
    try device.makeComputePipelineState(function: library.makeFunction(name: name)!)
}
let pGather = try pipeline("t_gather")
let pSeq = try pipeline("t_seq")
let pPerm = try pipeline("t_perm")

// row_order model: after the expert-major counting sort, row_order[i] = the
// source token that sorted row i came from. Each of the 512 tokens appears
// exactly topK = 8 times, at positions that are pseudo-random with respect to
// token identity. Seeded so the permutation is reproducible.
var rngState: UInt64 = 0x9E3779B97F4A7C15
func nextRandom(_ bound: UInt32) -> UInt32 {
    rngState ^= rngState << 13
    rngState ^= rngState >> 7
    rngState ^= rngState << 17
    return UInt32(rngState % UInt64(bound))
}

var rowOrder = [UInt32](repeating: 0, count: layers * sortedRows)
for l in 0..<layers {
    var perm = [UInt32]()
    perm.reserveCapacity(sortedRows)
    for t in 0..<tokens {
        for _ in 0..<topK { perm.append(UInt32(l * tokens + t)) }
    }
    var i = sortedRows - 1
    while i > 0 {
        let j = Int(nextRandom(UInt32(i + 1)))
        perm.swapAt(i, j)
        i -= 1
    }
    for i in 0..<sortedRows { rowOrder[l * sortedRows + i] = perm[i] }
}

let srcBuf = device.makeBuffer(length: srcBytes, options: .storageModeShared)!
let dstBuf = device.makeBuffer(length: dstBytes, options: .storageModeShared)!
let outBuf = device.makeBuffer(length: layers * sortedRows * 4, options: .storageModeShared)!
let orderBuf = device.makeBuffer(bytes: rowOrder,
                                 length: rowOrder.count * 4,
                                 options: .storageModeShared)!

// Non-zero, non-uniform payload so nothing can be constant-folded and so the
// XOR guard never accidentally trips.
let srcPtr = srcBuf.contents().bindMemory(to: UInt32.self, capacity: srcBytes / 4)
var seed: UInt32 = 0x12345678
for i in 0..<(srcBytes / 4) {
    seed = seed &* 1664525 &+ 1013904223
    srcPtr[i] = seed | 1
}

func time(_ pipe: MTLComputePipelineState, _ buffers: [MTLBuffer]) -> Double {
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipe)
    for (i, b) in buffers.enumerated() { enc.setBuffer(b, offset: 0, index: i) }
    enc.dispatchThreadgroups(MTLSize(width: layers * sortedRows, height: 1, depth: 1),
                             threadsPerThreadgroup: MTLSize(width: vecPerRow, height: 1, depth: 1))
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    return (cb.gpuEndTime - cb.gpuStartTime) * 1_000_000.0  // microseconds
}

var tGather = [Double]()
var tSeq = [Double]()
var tPerm = [Double]()

// Three kernels interleaved inside each repetition, so thermal or clock drift
// cannot land preferentially on one arm.
for _ in 0..<reps {
    tGather.append(time(pGather, [srcBuf, dstBuf, orderBuf]))
    tSeq.append(time(pSeq, [dstBuf, orderBuf, outBuf]))
    tPerm.append(time(pPerm, [srcBuf, orderBuf, outBuf]))
}

func stats(_ raw: [Double]) -> (median: Double, min: Double, max: Double, kept: [Double]) {
    let kept = Array(raw.dropFirst(discard))
    let s = kept.sorted()
    return (s[s.count / 2], s.first!, s.last!, kept)
}

let g = stats(tGather)
let s = stats(tSeq)
let p = stats(tPerm)

func fmt(_ v: [Double]) -> String {
    v.map { String(format: "%.2f", $0) }.joined(separator: " ")
}

print("=== M2 gather-elision probe ===")
print("device: \(device.name)  layers=\(layers) reps=\(reps) discard_first=\(discard)")
print(String(format: "src buffer: %.1f MiB   dst buffer: %.1f MiB   total %.1f MiB",
             Double(srcBytes) / 1048576.0, Double(dstBytes) / 1048576.0,
             Double(srcBytes + dstBytes) / 1048576.0))
print("tokens=\(tokens) sortedRows=\(sortedRows) hidden=\(hidden) topK=\(topK) rowBytes=\(hidden * 2)")
print("")
print("raw GPU us (all reps, first \(discard) discarded):")
print("  t_gather: \(fmt(tGather))")
print("  t_seq   : \(fmt(tSeq))")
print("  t_perm  : \(fmt(tPerm))")
print("")

func line(_ name: String, _ st: (median: Double, min: Double, max: Double, kept: [Double]),
          _ bytes: Double) {
    let spread = st.max / st.min
    let gbs = bytes / (st.median * 1e-6) / 1e9
    let pad = name.padding(toLength: 9, withPad: " ", startingAt: 0)
    print(pad + String(format: " median %8.2f us   min %8.2f  max %8.2f  spread %.3f   %7.1f GB/s (logical %.1f MiB)",
                       st.median / Double(layers), st.min / Double(layers),
                       st.max / Double(layers), spread, gbs, bytes / 1048576.0))
}

let gatherBytes = Double(layers) * Double(tokens + sortedRows) * Double(hidden * 2)
let seqBytes = Double(layers) * Double(sortedRows) * Double(hidden * 2)
let permBytes = Double(layers) * Double(sortedRows) * Double(hidden * 2)

print("per-layer GPU time (total divided by layers=\(layers)):")
line("t_gather", g, gatherBytes)
line("t_seq", s, seqBytes)
line("t_perm", p, permBytes)
print("")

let halfA = g.median / Double(layers)
let halfB = (s.median - p.median) / Double(layers)
let routedLayers = 39.0
let combinedM4ms = routedLayers * (halfA + halfB) / 1000.0
let byteArmFactor = 0.399
let convertedM5ms = byteArmFactor * combinedM4ms
let scoreDeltaPct = 0.371 * convertedM5ms

print(String(format: "half_a (gather deleted)      = %8.2f us/layer", halfA))
print(String(format: "half_b (t_seq - t_perm)      = %8.2f us/layer", halfB))
print(String(format: "combined M4                  = %8.3f ms  (x %.0f routed layers)",
             combinedM4ms, routedLayers))
print(String(format: "converted M5 prefill         = %8.3f ms  (x %.3f byte-arm factor)",
             convertedM5ms, byteArmFactor))
print(String(format: "score delta                  = %+8.3f %%  (1 ms prefill = 0.371 %%)",
             scoreDeltaPct))
print("")

let maxSpread = max(g.max / g.min, max(s.max / s.min, p.max / p.min))
print("--- decision table ---")
print(String(format: "D1 noise gate     : max spread %.3f  %@ (STOP if > 1.20)",
             maxSpread, maxSpread > 1.20 ? "FIRES -> STOP" : "clear"))
print(String(format: "D2 sign gate      : half_b %+.2f us, half_a+half_b %+.2f us  %@",
             halfB, halfA + halfB,
             (halfB < 0 && (halfA + halfB) <= 0) ? "FIRES -> STOP" : "clear"))
print(String(format: "D3 magnitude gate : converted %.3f ms  %@ (STOP if < 1.0)",
             convertedM5ms, convertedM5ms < 1.0 ? "FIRES -> STOP" : "clear"))
print(String(format: "D4 proceed        : %@", convertedM5ms >= 1.0 ? "YES" : "no"))
