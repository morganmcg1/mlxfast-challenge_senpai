// PR #72 step 4a positive control.
//
// Runs MLX's own `fp_quantize<bfloat16_t, 16, 4>` -- assembled from the four
// generated preambles that jit_kernels.cpp:925-936 concatenates, with the
// template definition kernels.h:404-424 produces for the kname built at
// quantized.cpp:2433-2442 -- over the real BF16 attention q/k/v projections,
// using the exact 1-D dispatch of quantized.cpp:2455-2478
// (per_thread = max(16/32,1) = 1, nthreads = w.size(), grid = (nthreads,1,1)).
//
// It then reports, on the raw uint8 E4M3 scale bytes:
//   * the even-pair equality fraction  scale[2k] == scale[2k+1]
//   * the exact flat index of every exception
//   * the byte-shifted odd-pair control scale[2k+1] == scale[2k+2]
//   * the distinct-code count and subnormal fraction
//
// Build and run:
//   python3 research/nezuko_attn_dump.py
//   swiftc -O research/nezuko_attention_scale_control.swift \
//     -o /tmp/nezuko_g32/attn_control -framework Metal -framework Foundation
//   /tmp/nezuko_g32/attn_control

import Foundation
import Metal

let root = "/tmp/nezuko_g32"

func die(_ message: String) -> Never {
    FileHandle.standardError.write(Data("error: \(message)\n".utf8))
    exit(1)
}

guard let device = MTLCreateSystemDefaultDevice() else { die("no Metal device") }
guard let queue = device.makeCommandQueue() else { die("no command queue") }

let source: String
do {
    source = try String(contentsOfFile: "\(root)/fpq_source.metal", encoding: .utf8)
} catch {
    die("missing \(root)/fpq_source.metal -- run research/nezuko_attn_dump.py first")
}

let options = MTLCompileOptions()
options.mathMode = .safe
let library: MTLLibrary
do {
    library = try device.makeLibrary(source: source, options: options)
} catch {
    die("makeLibrary failed: \(error)")
}
guard let function = library.makeFunction(name: "nvfp4_quantize_bfloat16_t_gs_16_b_4") else {
    die("missing kernel nvfp4_quantize_bfloat16_t_gs_16_b_4")
}
let pipeline = try! device.makeComputePipelineState(function: function)

struct Dispatch {
    let layer: Int
    let proj: String
    let rows: Int
    let cols: Int
    let file: String
}

guard let manifestData = FileManager.default.contents(atPath: "\(root)/attn/manifest.json"),
    let raw = try? JSONSerialization.jsonObject(with: manifestData) as? [[String: Any]]
else { die("missing \(root)/attn/manifest.json") }

let dispatches: [Dispatch] = raw.map {
    let shape = $0["shape"] as! [Int]
    return Dispatch(
        layer: $0["layer"] as! Int, proj: $0["proj"] as! String,
        rows: shape[0], cols: shape[1], file: $0["file"] as! String)
}

/// Quantizes one weight tensor with the shipped kernel and returns the raw
/// E4M3 scale bytes.
func quantizeScales(_ d: Dispatch) -> [UInt8] {
    guard let weights = FileManager.default.contents(atPath: d.file) else {
        die("missing \(d.file)")
    }
    let count = d.rows * d.cols
    precondition(weights.count == count * 2, "size mismatch for \(d.file)")

    let wBuf = weights.withUnsafeBytes {
        device.makeBuffer(bytes: $0.baseAddress!, length: weights.count, options: .storageModeShared)!
    }
    let outBuf = device.makeBuffer(length: count / 2, options: .storageModeShared)!
    let scaleBuf = device.makeBuffer(length: count / 16, options: .storageModeShared)!

    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipeline)
    enc.setBuffer(wBuf, offset: 0, index: 0)
    enc.setBuffer(outBuf, offset: 0, index: 1)
    enc.setBuffer(scaleBuf, offset: 0, index: 2)
    let tg = min(pipeline.maxTotalThreadsPerThreadgroup, count)
    enc.dispatchThreads(
        MTLSize(width: count, height: 1, depth: 1),
        threadsPerThreadgroup: MTLSize(width: tg, height: 1, depth: 1))
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    if let error = cb.error { die("dispatch failed: \(error)") }

    let ptr = scaleBuf.contents().bindMemory(to: UInt8.self, capacity: count / 16)
    return Array(UnsafeBufferPointer(start: ptr, count: count / 16))
}

var totalPairs = 0
var evenEqual = 0
var oddPairs = 0
var oddEqual = 0
var codeHistogram = [Int](repeating: 0, count: 256)
var dispatchesWithException = 0
var exceptionsOffPairZero = 0
var perDispatch: [(String, Int, [Int])] = []

print("=== step 4a: attention plane positive control ===")
print("kernel  nvfp4_quantize_bfloat16_t_gs_16_b_4  (fp_quantize<bfloat16_t, 16, 4>)")
print("source  utils + gemm + quantized_utils + fp_quantized, math mode safe")
print("dispatches: \(dispatches.count)")

for d in dispatches {
    let scales = quantizeScales(d)
    let pairs = scales.count / 2
    var bad: [Int] = []
    for k in 0..<pairs where scales[2 * k] != scales[2 * k + 1] {
        bad.append(k)
    }
    totalPairs += pairs
    evenEqual += pairs - bad.count
    for k in 0..<(scales.count / 2 - 1) where scales[2 * k + 1] == scales[2 * k + 2] {
        oddEqual += 1
    }
    oddPairs += scales.count / 2 - 1
    for byte in scales { codeHistogram[Int(byte)] += 1 }
    if !bad.isEmpty {
        dispatchesWithException += 1
        exceptionsOffPairZero += bad.filter { $0 != 0 }.count
    }
    perDispatch.append(("L\(d.layer).\(d.proj)", pairs, bad))
}

print("")
print("=== per-dispatch exceptions (flat scale pair index) ===")
for (name, pairs, bad) in perDispatch {
    let where_ = bad.isEmpty ? "none" : bad.prefix(8).map(String.init).joined(separator: ",")
    print(String(format: "%-16@ pairs %9d  exceptions %2d  at %@",
                 name as NSString, pairs, bad.count, where_ as NSString))
}

let distinct = codeHistogram.filter { $0 > 0 }.count
let totalCodes = codeHistogram.reduce(0, +)
// E4M3: exponent field is bits 6..3; a zero exponent field means subnormal.
var subnormal = 0
for code in 0..<256 where (code & 0x78) == 0 { subnormal += codeHistogram[code] }

print("")
print("=== aggregate ===")
print(String(format: "pairs examined            %12d", totalPairs))
print(String(format: "even-pair equal           %12d  (%.6f%%)",
             evenEqual, 100.0 * Double(evenEqual) / Double(totalPairs)))
print(String(format: "odd-pair (shift) equal    %12d  (%.6f%%)",
             oddEqual, 100.0 * Double(oddEqual) / Double(oddPairs)))
print(String(format: "exceptions total          %12d", totalPairs - evenEqual))
print(String(format: "dispatches with exception %12d of %d", dispatchesWithException, dispatches.count))
print(String(format: "exceptions off pair 0     %12d", exceptionsOffPairZero))
print(String(format: "distinct E4M3 codes       %12d", distinct))
print(String(format: "subnormal code fraction   %11.4f%%",
             100.0 * Double(subnormal) / Double(totalCodes)))

print("")
print("=== verdict ===")
let structural = exceptionsOffPairZero == 0
let fraction = Double(evenEqual) / Double(totalPairs)
if structural && fraction >= 0.999 {
    print("PASS: every exception is at flat scale pair 0 of its own quantize dispatch,")
    print("      matching fp_quantized.cpp:2346-2352 (only the first simdgroup of a")
    print("      1-D dispatch sees tidx.x < 16 for any lane).")
} else {
    print("FAIL: exceptions are not confined to pair 0 -- the mechanism write-up is wrong.")
    exit(2)
}
