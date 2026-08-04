import Foundation
import Metal

// Standalone probe for the fused *full* (growing-KV) decode-attention kernel.
// Laguna's exact decode geometry for that family: 48 query heads, 8 KV heads,
// head_dim 128, 10 full-attention layers per decode step, contiguous cache of
// `capacity` slots with the live prefix N = writeIdx + 1.
//
// Two modes:
//   variant mode      label:file.metal:headsPerThreadgroup
//                     bitwise-diffs every variant against the first and reports
//                     isolated per-layer time.
//   occupancy mode    --occupancy label:file.metal:headsPerThreadgroup
//                     times the same kernel at 1..48 dispatched threadgroups.
//                     Outputs are meaningless below full width; the point is the
//                     shape of time vs threadgroup count, which reveals how many
//                     1024-thread threadgroups the GPU runs concurrently.

let heads = 48
let kvHeads = 8
let headDim = 128
let layers = 10
let capacity = 640
let liveN = 576

func bf16(_ value: Float) -> UInt16 {
    UInt16(truncatingIfNeeded: value.bitPattern >> 16)
}

var seed: UInt64 = 0x2545_F491_4F6C_DD1D
func nextUniform() -> Float {
    seed ^= seed << 13
    seed ^= seed >> 7
    seed ^= seed << 17
    return Float(Double(seed >> 11) / Double(1 << 53)) * 2.0 - 1.0
}

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!

func makeBF16Buffer(_ count: Int, scale: Float = 1.0) -> MTLBuffer {
    var values = [UInt16](repeating: 0, count: count)
    for i in 0..<count { values[i] = bf16(nextUniform() * scale) }
    return device.makeBuffer(
        bytes: &values, length: count * 2, options: .storageModeShared)!
}

func makeFloatBuffer(_ values: [Float]) -> MTLBuffer {
    var copy = values
    return device.makeBuffer(
        bytes: &copy, length: values.count * 4, options: .storageModeShared)!
}

let rawQueries = makeBF16Buffer(heads * headDim)
let rawKeys = makeBF16Buffer(kvHeads * headDim)
let rawValues = makeBF16Buffer(kvHeads * headDim)
let queryWeight = makeBF16Buffer(headDim)
let keyWeight = makeBF16Buffer(headDim)

// The full-attention kernel is partial-rotary: rotary_pairs = 32, so it reads
// cos at angles[0..31] and sin at angles[32..63].
var angleValues = [Float](repeating: 0, count: headDim)
for i in 0..<32 {
    let theta = Float(i) * 0.017
    angleValues[i] = cos(theta)
    angleValues[i + 32] = sin(theta)
}
let angles = makeFloatBuffer(angleValues)
let scaleArr = makeFloatBuffer([1.0 / sqrt(Float(headDim))])

// One contiguous K/V cache per layer so the per-step working set matches decode.
let cacheElements = kvHeads * capacity * headDim
var kCaches: [MTLBuffer] = []
var vCaches: [MTLBuffer] = []
for _ in 0..<layers {
    kCaches.append(makeBF16Buffer(cacheElements, scale: 0.5))
    vCaches.append(makeBF16Buffer(cacheElements, scale: 0.5))
}
let pristineK = kCaches.map { buffer -> [UInt16] in
    let pointer = buffer.contents().bindMemory(
        to: UInt16.self, capacity: cacheElements)
    return Array(UnsafeBufferPointer(start: pointer, count: cacheElements))
}
let pristineV = vCaches.map { buffer -> [UInt16] in
    let pointer = buffer.contents().bindMemory(
        to: UInt16.self, capacity: cacheElements)
    return Array(UnsafeBufferPointer(start: pointer, count: cacheElements))
}

func restoreCaches() {
    for layer in 0..<layers {
        pristineK[layer].withUnsafeBytes {
            kCaches[layer].contents().copyMemory(
                from: $0.baseAddress!, byteCount: $0.count)
        }
        pristineV[layer].withUnsafeBytes {
            vCaches[layer].contents().copyMemory(
                from: $0.baseAddress!, byteCount: $0.count)
        }
    }
}

// params = [writeIdx, N, capacity], matching lagunaFullFusedAttention.
var params: [UInt32] = [UInt32(liveN - 1), UInt32(liveN), UInt32(capacity)]
let paramsBuffer = device.makeBuffer(
    bytes: &params, length: 12, options: .storageModeShared)!

let attended = device.makeBuffer(
    length: heads * headDim * 2, options: .storageModeShared)!

struct Variant {
    let label: String
    let groupHeads: Int
    let pipeline: MTLComputePipelineState
}

func loadVariant(label: String, path: String, groupHeads: Int) -> Variant {
    let source = try! String(contentsOfFile: path, encoding: .utf8)
    let options = MTLCompileOptions()
    // Match mlx's JIT: Device::build_library_ sets fast math off.
    options.fastMathEnabled = false
    let library = try! device.makeLibrary(source: source, options: options)
    let function = library.makeFunction(name: "probe")!
    let pipeline = try! device.makeComputePipelineState(function: function)
    return Variant(label: label, groupHeads: groupHeads, pipeline: pipeline)
}

var args = Array(CommandLine.arguments.dropFirst())
let occupancyMode = args.first == "--occupancy"
if occupancyMode { args.removeFirst() }
guard !args.isEmpty else {
    FileHandle.standardError.write(Data(
        "usage: probe [--occupancy] label:file.metal:headsPerThreadgroup ...\n".utf8))
    exit(2)
}
let variants = args.map { spec -> Variant in
    let f = spec.split(separator: ":").map(String.init)
    precondition(f.count == 3, "bad variant spec \(spec)")
    return loadVariant(label: f[0], path: f[1], groupHeads: Int(f[2])!)
}

func encode(
    _ variant: Variant, layer: Int, groups: Int,
    into encoder: MTLComputeCommandEncoder
) {
    encoder.setComputePipelineState(variant.pipeline)
    encoder.setBuffer(rawQueries, offset: 0, index: 0)
    encoder.setBuffer(rawKeys, offset: 0, index: 1)
    encoder.setBuffer(rawValues, offset: 0, index: 2)
    encoder.setBuffer(queryWeight, offset: 0, index: 3)
    encoder.setBuffer(keyWeight, offset: 0, index: 4)
    encoder.setBuffer(angles, offset: 0, index: 5)
    encoder.setBuffer(kCaches[layer], offset: 0, index: 6)
    encoder.setBuffer(vCaches[layer], offset: 0, index: 7)
    encoder.setBuffer(paramsBuffer, offset: 0, index: 8)
    encoder.setBuffer(scaleArr, offset: 0, index: 9)
    encoder.setBuffer(attended, offset: 0, index: 10)
    encoder.dispatchThreadgroups(
        MTLSize(width: groups, height: 1, depth: 1),
        threadsPerThreadgroup: MTLSize(width: 1024, height: 1, depth: 1))
}

func fullGroups(_ variant: Variant) -> Int { heads / variant.groupHeads }

func runOnce(_ variant: Variant) -> [UInt16] {
    restoreCaches()
    let buffer = queue.makeCommandBuffer()!
    let encoder = buffer.makeComputeCommandEncoder()!
    encode(variant, layer: 0, groups: fullGroups(variant), into: encoder)
    encoder.endEncoding()
    buffer.commit()
    buffer.waitUntilCompleted()
    let pointer = attended.contents().bindMemory(
        to: UInt16.self, capacity: heads * headDim)
    return Array(UnsafeBufferPointer(start: pointer, count: heads * headDim))
}

// One command buffer per "decode step" of `layers` dispatches, matching the real
// pattern. Variants are measured round-robin so drifting host load cannot be
// mistaken for a shape effect, and each keeps its minimum block.
func timeBlock(_ variant: Variant, groups: Int, steps: Int) -> Double {
    let start = DispatchTime.now().uptimeNanoseconds
    for _ in 0..<steps {
        let buffer = queue.makeCommandBuffer()!
        let encoder = buffer.makeComputeCommandEncoder()!
        for layer in 0..<layers {
            encode(variant, layer: layer, groups: groups, into: encoder)
        }
        encoder.endEncoding()
        buffer.commit()
        buffer.waitUntilCompleted()
    }
    let elapsed = Double(DispatchTime.now().uptimeNanoseconds - start) / 1e9
    return elapsed / Double(steps)
}

print("device: \(device.name)")
print(
    "threadgroup memory limit \(device.maxThreadgroupMemoryLength) B, "
        + "max threads/tg \(device.maxThreadsPerThreadgroup.width)")
for variant in variants {
    print(
        "\(variant.label): threadExecutionWidth "
            + "\(variant.pipeline.threadExecutionWidth), "
            + "maxTotalThreadsPerThreadgroup "
            + "\(variant.pipeline.maxTotalThreadsPerThreadgroup), "
            + "staticThreadgroupMemoryLength "
            + "\(variant.pipeline.staticThreadgroupMemoryLength)")
}

let steps = 20
let rounds = 9

if occupancyMode {
    // Time g = 1..heads threadgroups. A step function with risers at
    // g = cores + 1, 2*cores + 1, ... pins the concurrent-threadgroup count.
    let variant = variants[0]
    print("")
    print(
        "occupancy scan: \(variant.label), \(layers) dispatches per step, "
            + "min of \(rounds) blocks of \(steps) steps")
    var results = [Int: Double]()
    for _ in 0..<3 { _ = timeBlock(variant, groups: heads, steps: 2) }
    for round in 0..<rounds {
        // Alternate scan direction so monotone host drift cannot fake a step.
        let order = round % 2 == 0
            ? Array(1...heads) : Array((1...heads).reversed())
        for g in order {
            let seconds = timeBlock(variant, groups: g, steps: steps)
            results[g] = min(results[g] ?? .greatestFiniteMagnitude, seconds)
        }
    }
    let unit = results[1]!
    for g in 1...heads {
        let seconds = results[g]!
        print(String(
            format: "groups %2d  %8.2f us/step  %7.2f us/dispatch  x%5.2f vs 1 TG",
            g, seconds * 1e6, seconds * 1e6 / Double(layers),
            seconds / unit))
    }
} else {
    let reference = runOnce(variants[0])
    print("")
    for variant in variants {
        let candidate = runOnce(variant)
        let mismatches = zip(reference, candidate).filter { $0 != $1 }.count
        print(
            "\(variant.label): bitwise mismatches vs \(variants[0].label) "
                + "= \(mismatches)")
    }

    var best = [String: Double]()
    var median = [String: [Double]]()
    for variant in variants {
        _ = timeBlock(variant, groups: fullGroups(variant), steps: 3)
    }
    for round in 0..<rounds {
        for offset in 0..<variants.count {
            let variant = variants[(round + offset) % variants.count]
            let seconds = timeBlock(
                variant, groups: fullGroups(variant), steps: steps)
            best[variant.label] = min(
                best[variant.label] ?? .greatestFiniteMagnitude, seconds)
            median[variant.label, default: []].append(seconds)
        }
    }

    print("")
    print(
        "isolated timing: \(layers) full-attention dispatches per step, "
            + "\(rounds) round-robin blocks of \(steps) steps, N=\(liveN)")
    // Unique live K+V bytes touched per step, the denominator nezuko's
    // per-dispatch table uses.
    let uniqueBytes = Double(layers * 2 * kvHeads * liveN * headDim * 2)
    for variant in variants {
        let seconds = best[variant.label]!
        var samples = median[variant.label]!
        samples.sort()
        let mid = samples[samples.count / 2]
        // What the kernel actually requests: every threadgroup streams its own
        // KV head's full live prefix, so sharing factor is gqa / groupHeads.
        let requested = uniqueBytes
            * Double((heads / kvHeads) / variant.groupHeads)
        print(String(
            format: "%@ min %7.1f us/step  median %7.1f  %6.2f us/layer  "
                + "tg %2d  unique %5.1f MB %5.0f GB/s  requested %6.1f MB %5.0f GB/s",
            variant.label.padding(toLength: 12, withPad: " ", startingAt: 0),
            seconds * 1e6, mid * 1e6, seconds * 1e6 / Double(layers),
            fullGroups(variant),
            uniqueBytes / 1e6, uniqueBytes / seconds / 1e9,
            requested / 1e6, requested / seconds / 1e9))
    }
    print(String(
        format: "unique live KV per step: %.1f MB (capacity %d, N %d)",
        uniqueBytes / 1e6, capacity, liveN))
}
