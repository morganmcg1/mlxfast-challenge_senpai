import Foundation
import Metal

// Standalone probe for the routed-QMV router Top-8 butterfly (PR #442).
// Runs `laguna_router_top8_extract_round` in isolation over a randomized
// 256-wide router-key corpus, bit-diffs every variant against the first, and
// times them round-robin so the scalar and uint2 butterflies can be compared
// without the memory-bound QMV body masking the ALU difference.
//
// usage: ./probe label:file.metal [label:file.metal ...] [--repeats N]

let simdWidth = 32
let expertsPerLane = 8
let keysPerCase = simdWidth * expertsPerLane  // 256 routed experts
let roundsPerCase = 8
let cases = 2048
let simdsPerGroup = 2
let threadsPerGroup = simdWidth * simdsPerGroup

var repeats = 32
var specs: [(String, String)] = []
var argv = Array(CommandLine.arguments.dropFirst())
var i = 0
while i < argv.count {
    if argv[i] == "--repeats", i + 1 < argv.count {
        repeats = Int(argv[i + 1])!
        i += 2
        continue
    }
    let parts = argv[i].split(separator: ":", maxSplits: 1).map(String.init)
    specs.append((parts[0], parts[1]))
    i += 1
}
guard !specs.isEmpty else {
    FileHandle.standardError.write(Data("usage: probe label:file.metal ...\n".utf8))
    exit(2)
}

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!

var seed: UInt64 = 0x2545_F491_4F6C_DD1D
func nextBits() -> UInt64 {
    seed ^= seed << 13
    seed ^= seed >> 7
    seed ^= seed << 17
    return seed
}
func nextUniform() -> Float {
    Float(Double(nextBits() >> 11) / Double(1 << 53)) * 2.0 - 1.0
}

// Corpus: mostly plain router logits, plus adversarial cases that exercise the
// comparator's tie, signed-zero, infinity and NaN branches. Ties matter most:
// equal ordinals force the index tiebreak, which is exactly what the packed
// shuffle must preserve.
let specials: [Float] = [
    0.0, -0.0, .infinity, -.infinity, .nan, -Float.nan,
    Float.leastNonzeroMagnitude, -Float.leastNonzeroMagnitude,
    Float.greatestFiniteMagnitude, -Float.greatestFiniteMagnitude,
]
var keyValues = [Float](repeating: 0, count: cases * keysPerCase)
for c in 0..<cases {
    let base = c * keysPerCase
    let flavor = c % 4
    for k in 0..<keysPerCase {
        keyValues[base + k] = nextUniform()
    }
    switch flavor {
    case 1:
        // Heavy ties: collapse the corpus onto a handful of distinct values so
        // most comparisons fall through to the index tiebreak.
        let levels = 3 + Int(nextBits() % 5)
        var pool = [Float]()
        for _ in 0..<levels { pool.append(nextUniform()) }
        for k in 0..<keysPerCase {
            keyValues[base + k] = pool[Int(nextBits() % UInt64(levels))]
        }
    case 2:
        // Sprinkle specials, including duplicates of the same special.
        for _ in 0..<24 {
            let k = Int(nextBits() % UInt64(keysPerCase))
            keyValues[base + k] = specials[Int(nextBits() % UInt64(specials.count))]
        }
    case 3:
        // Degenerate: every key identical, so all 256 experts tie.
        let v = specials[Int(nextBits() % UInt64(specials.count))]
        for k in 0..<keysPerCase { keyValues[base + k] = v }
    default:
        break
    }
}
let keyBuffer = device.makeBuffer(
    bytes: &keyValues, length: keyValues.count * 4, options: .storageModeShared)!

func makeParams(_ repeats: Int) -> MTLBuffer {
    var values: [UInt32] = [UInt32(repeats), 0]
    return device.makeBuffer(
        bytes: &values, length: 8, options: .storageModeShared)!
}
let paramsOnce = makeParams(1)
let paramsTimed = makeParams(repeats)

struct Variant {
    let label: String
    let pipeline: MTLComputePipelineState
    let out: MTLBuffer
}

let options = MTLCompileOptions()
options.fastMathEnabled = false  // matches MLX Device::build_library_
var variants: [Variant] = []
for (label, path) in specs {
    let source = try! String(contentsOfFile: path, encoding: .utf8)
    let library = try! device.makeLibrary(source: source, options: options)
    let function = library.makeFunction(name: "probe")!
    let pipeline = try! device.makeComputePipelineState(function: function)
    let out = device.makeBuffer(
        length: cases * roundsPerCase * 4, options: .storageModeShared)!
    variants.append(Variant(label: label, pipeline: pipeline, out: out))
}

func encode(_ v: Variant, params: MTLBuffer, into encoder: MTLComputeCommandEncoder) {
    encoder.setComputePipelineState(v.pipeline)
    encoder.setBuffer(keyBuffer, offset: 0, index: 0)
    encoder.setBuffer(v.out, offset: 0, index: 1)
    encoder.setBuffer(params, offset: 0, index: 2)
    encoder.dispatchThreadgroups(
        MTLSize(width: cases / simdsPerGroup, height: 1, depth: 1),
        threadsPerThreadgroup: MTLSize(width: threadsPerGroup, height: 1, depth: 1))
}

func runOnce(_ v: Variant) -> [UInt32] {
    memset(v.out.contents(), 0, v.out.length)
    let buffer = queue.makeCommandBuffer()!
    let encoder = buffer.makeComputeCommandEncoder()!
    encode(v, params: paramsOnce, into: encoder)
    encoder.endEncoding()
    buffer.commit()
    buffer.waitUntilCompleted()
    let ptr = v.out.contents().bindMemory(
        to: UInt32.self, capacity: cases * roundsPerCase)
    return Array(UnsafeBufferPointer(start: ptr, count: cases * roundsPerCase))
}

print("corpus: \(cases) cases x \(keysPerCase) keys, \(roundsPerCase) rounds each")
let reference = runOnce(variants[0])
let distinct = Set(reference).count
print("reference \(variants[0].label): \(distinct) distinct winner values")
var anyMismatch = false
for v in variants {
    let candidate = runOnce(v)
    let bad = zip(reference, candidate).enumerated().filter { $0.element.0 != $0.element.1 }
    if !bad.isEmpty { anyMismatch = true }
    let firstBad = bad.first.map {
        " first at case \($0.offset / roundsPerCase) round \($0.offset % roundsPerCase)"
            + " ref \($0.element.0) got \($0.element.1)"
    } ?? ""
    print("\(v.label): mismatch = \(bad.count)\(firstBad)")
}

let dispatchesPerStep = 8
func timeBlock(_ v: Variant, steps: Int) -> Double {
    let start = DispatchTime.now().uptimeNanoseconds
    for _ in 0..<steps {
        let buffer = queue.makeCommandBuffer()!
        let encoder = buffer.makeComputeCommandEncoder()!
        for _ in 0..<dispatchesPerStep {
            encode(v, params: paramsTimed, into: encoder)
        }
        encoder.endEncoding()
        buffer.commit()
        buffer.waitUntilCompleted()
    }
    return Double(DispatchTime.now().uptimeNanoseconds - start) / 1e9 / Double(steps)
}

let steps = 20
let blocks = 9
for v in variants { _ = timeBlock(v, steps: 3) }
var best = [String: Double]()
var samples = [String: [Double]]()
for block in 0..<blocks {
    for offset in 0..<variants.count {
        let v = variants[(block + offset) % variants.count]
        let seconds = timeBlock(v, steps: steps)
        best[v.label] = min(best[v.label] ?? .greatestFiniteMagnitude, seconds)
        samples[v.label, default: []].append(seconds)
    }
}

// One dispatch executes cases * roundsPerCase * repeats extract-rounds.
let roundsPerDispatch = Double(cases * roundsPerCase * repeats)
let roundsPerStep = roundsPerDispatch * Double(dispatchesPerStep)
print("")
print("timing: repeats=\(repeats), \(dispatchesPerStep) dispatches/step, "
    + "\(blocks) round-robin blocks of \(steps) steps, "
    + String(format: "%.3fM rounds/step", roundsPerStep / 1e6))
let baseline = best[variants[0].label]!
for v in variants {
    var s = samples[v.label]!
    s.sort()
    let mid = s[s.count / 2]
    let minimum = best[v.label]!
    print(String(
        format: "%@ min %9.1f us/step  median %9.1f  %7.3f ns/round  %+7.3f%% vs %@",
        v.label.padding(toLength: 16, withPad: " ", startingAt: 0),
        minimum * 1e6, mid * 1e6, minimum * 1e9 / roundsPerStep,
        (minimum / baseline - 1.0) * 100.0, variants[0].label))
}
if anyMismatch { print("NOTE: at least one variant diverged (expected for fault arms)") }
