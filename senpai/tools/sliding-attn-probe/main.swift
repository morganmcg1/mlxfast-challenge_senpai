import Foundation
import Metal

// Standalone probe for the fused sliding decode-attention kernel shape.
// Compares bitwise output and isolated dispatch time across group widths at
// Laguna's exact decode geometry: 8 KV heads, 512-slot ring, head_dim 128,
// 64 query heads, 30 sliding layers per decode step.

let heads = 64
let kvHeads = 8
let headDim = 128
let window = 512
let layers = 30

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

var angleValues = [Float](repeating: 0, count: headDim)
for i in 0..<64 {
    let theta = Float(i) * 0.017
    angleValues[i] = cos(theta)
    angleValues[i + 64] = sin(theta)
}
let angles = makeFloatBuffer(angleValues)
let scaleArr = makeFloatBuffer([1.0 / sqrt(Float(headDim))])

// One K/V ring per layer so the per-step working set matches decode.
let ringElements = kvHeads * window * headDim
var kCaches: [MTLBuffer] = []
var vCaches: [MTLBuffer] = []
for _ in 0..<layers {
    kCaches.append(makeBF16Buffer(ringElements, scale: 0.5))
    vCaches.append(makeBF16Buffer(ringElements, scale: 0.5))
}
let pristineK = kCaches.map { buffer -> [UInt16] in
    let pointer = buffer.contents().bindMemory(to: UInt16.self, capacity: ringElements)
    return Array(UnsafeBufferPointer(start: pointer, count: ringElements))
}
let pristineV = vCaches.map { buffer -> [UInt16] in
    let pointer = buffer.contents().bindMemory(to: UInt16.self, capacity: ringElements)
    return Array(UnsafeBufferPointer(start: pointer, count: ringElements))
}

func restoreCaches() {
    for layer in 0..<layers {
        pristineK[layer].withUnsafeBytes {
            kCaches[layer].contents().copyMemory(from: $0.baseAddress!, byteCount: $0.count)
        }
        pristineV[layer].withUnsafeBytes {
            vCaches[layer].contents().copyMemory(from: $0.baseAddress!, byteCount: $0.count)
        }
    }
}

let writeIdx: UInt32 = 137
var params: [UInt32] = [writeIdx, 0, 0, 0]
let paramsBuffer = device.makeBuffer(
    bytes: &params, length: 16, options: .storageModeShared)!

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

// Variants come from the command line as `label:path:headsPerThreadgroup`
// triples. The first is the reference every other variant is diffed against,
// so pass the unmodified kernel first.
var args = Array(CommandLine.arguments.dropFirst())
// `--occupancy` times variants[0] at 1..heads dispatched threadgroups instead
// of comparing variants, so the concurrent-threadgroup count of the host can be
// read off the riser positions.
let occupancyMode = args.first == "--occupancy"
if occupancyMode { args.removeFirst() }
let specs = args
guard !specs.isEmpty else {
    FileHandle.standardError.write(Data(
        "usage: probe [--occupancy] label:file.metal:headsPerThreadgroup ...\n".utf8))
    exit(2)
}
let variants = specs.map { spec -> Variant in
    let f = spec.split(separator: ":").map(String.init)
    precondition(f.count == 3, "bad variant spec \(spec)")
    return loadVariant(label: f[0], path: f[1], groupHeads: Int(f[2])!)
}

func encode(
    _ variant: Variant, layer: Int, groups groupOverride: Int? = nil,
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
    let groups = groupOverride ?? (heads / variant.groupHeads)
    encoder.dispatchThreadgroups(
        MTLSize(width: groups, height: 1, depth: 1),
        threadsPerThreadgroup: MTLSize(width: 1024, height: 1, depth: 1))
}

func runOnce(_ variant: Variant) -> [UInt16] {
    restoreCaches()
    let buffer = queue.makeCommandBuffer()!
    let encoder = buffer.makeComputeCommandEncoder()!
    encode(variant, layer: 0, into: encoder)
    encoder.endEncoding()
    buffer.commit()
    buffer.waitUntilCompleted()
    let pointer = attended.contents().bindMemory(
        to: UInt16.self, capacity: heads * headDim)
    return Array(UnsafeBufferPointer(start: pointer, count: heads * headDim))
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

if !occupancyMode {
    let reference = runOnce(variants[0])
    print("")
    for variant in variants {
        let candidate = runOnce(variant)
        let mismatches = zip(reference, candidate).filter { $0 != $1 }.count
        print("\(variant.label): bitwise mismatches vs \(variants[0].label) = \(mismatches)")
    }
}

// Isolated timing: one command buffer per "decode step" of 30 sliding layers,
// matching the real dispatch pattern. Variants are measured round-robin so a
// drifting host load cannot be mistaken for a shape effect, and each variant
// keeps its minimum block.
func timeBlock(_ variant: Variant, groups: Int? = nil, steps: Int) -> Double {
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

let steps = 20
let rounds = 9

if occupancyMode {
    // Time variants[0] at g = 1..heads dispatched threadgroups. Risers at
    // g = cores + 1, 2*cores + 1, ... pin the concurrent-threadgroup count, and
    // the plateau value is the single-wave (per-threadgroup) latency a host with
    // at least g cores would pay.
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
            g, seconds * 1e6, seconds * 1e6 / Double(layers), seconds / unit))
    }
    exit(0)
}

for variant in variants { _ = timeBlock(variant, steps: 3) }
var best = [String: Double]()
var median = [String: [Double]]()
for round in 0..<rounds {
    for offset in 0..<variants.count {
        let variant = variants[(round + offset) % variants.count]
        let seconds = timeBlock(variant, steps: steps)
        best[variant.label] = min(best[variant.label] ?? .greatestFiniteMagnitude, seconds)
        median[variant.label, default: []].append(seconds)
    }
}

print("")
print(
    "isolated timing: \(layers) sliding-layer dispatches per step, "
        + "\(rounds) round-robin blocks of \(steps) steps")
let residentBytes = Double(layers * 2 * ringElements * 2)
for variant in variants {
    let seconds = best[variant.label]!
    var samples = median[variant.label]!
    samples.sort()
    let mid = samples[samples.count / 2]
    let requested = residentBytes * Double(8 / variant.groupHeads)
    let line = String(
        format:
            "%@ min %7.1f us/step  median %7.1f  %6.2f us/layer  tg %d  requested %6.1f MB  %5.0f GB/s",
        variant.label.padding(toLength: 14, withPad: " ", startingAt: 0),
        seconds * 1e6, mid * 1e6, seconds * 1e6 / Double(layers),
        heads / variant.groupHeads, requested / 1e6, requested / seconds / 1e9)
    print(line)
}
print(String(format: "resident KV per step: %.1f MB", residentBytes / 1e6))
