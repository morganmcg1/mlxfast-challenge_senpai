import Dispatch
import Foundation
import MLX
import MLXRandom

private let baselineSHA = "55e89bd1761da9982a44871486c7c71dd6483b0d"
private let candidateRuntimeSHA = "257b514b4185b651a34eb60fb13b4bb8aaecdc5d"
private let headDim = 128
private let kvHeads = 8
private let slidingHeads = 64
private let fullHeads = 48
private let slidingWindow = 512
private let fullCapacity = 640

private enum BenchmarkError: Error, CustomStringConvertible {
    case commandFailed(String)
    case invalidSource(String)
    case invariant(String)

    var description: String {
        switch self {
        case .commandFailed(let message), .invalidSource(let message), .invariant(let message):
            return message
        }
    }
}

private enum ABI: String {
    case old
    case packed
}

private enum Family: String {
    case sliding
    case full
}

private struct Options {
    let quick: Bool
    let repeats: Int

    static func parse() throws -> Options {
        let arguments = Array(CommandLine.arguments.dropFirst())
        var quick = false
        var repeats = 2
        var index = 0
        while index < arguments.count {
            switch arguments[index] {
            case "--quick":
                quick = true
                index += 1
            case "--repeats":
                guard index + 1 < arguments.count,
                      let value = Int(arguments[index + 1]), value > 0
                else {
                    throw BenchmarkError.invariant("--repeats requires a positive integer")
                }
                repeats = value
                index += 2
            default:
                throw BenchmarkError.invariant("unknown argument: \(arguments[index])")
            }
        }
        return Options(quick: quick, repeats: repeats)
    }
}

private struct KernelSources {
    let slidingDecode: String
    let fullDecode: String
    let slidingPrefill: String
    let fullPrefill: String
}

private struct Kernels {
    let slidingDecode: MLXFast.MLXFastKernel
    let fullDecode: MLXFast.MLXFastKernel
    let slidingPrefill: MLXFast.MLXFastKernel
    let fullPrefill: MLXFast.MLXFastKernel

    init(sources: KernelSources, abi: ABI) {
        let decodeInputs: [String]
        let prefillInputs: [String]
        switch abi {
        case .old:
            decodeInputs = [
                "raw_queries", "raw_keys", "raw_values",
                "query_weight", "key_weight", "angles",
                "k_cache", "v_cache", "params", "scale_arr",
            ]
            prefillInputs = [
                "raw_queries", "raw_keys", "query_weight", "key_weight", "angles", "offsets",
            ]
        case .packed:
            decodeInputs = [
                "raw_queries", "raw_keys", "raw_values",
                "norm_weight_bank", "angles",
                "k_cache", "v_cache", "params", "scale_arr",
            ]
            prefillInputs = [
                "raw_queries", "raw_keys", "norm_weight_bank", "angles", "offsets",
            ]
        }
        slidingDecode = MLXFast.metalKernel(
            name: "qk_abi_\(abi.rawValue)_sliding_decode",
            inputNames: decodeInputs,
            outputNames: ["attended"],
            source: sources.slidingDecode,
            ensureRowContiguous: true
        )
        fullDecode = MLXFast.metalKernel(
            name: "qk_abi_\(abi.rawValue)_full_decode",
            inputNames: decodeInputs,
            outputNames: ["attended"],
            source: sources.fullDecode,
            ensureRowContiguous: true
        )
        slidingPrefill = MLXFast.metalKernel(
            name: "qk_abi_\(abi.rawValue)_sliding_prefill",
            inputNames: prefillInputs,
            outputNames: ["queries", "keys"],
            source: sources.slidingPrefill,
            ensureRowContiguous: true
        )
        fullPrefill = MLXFast.metalKernel(
            name: "qk_abi_\(abi.rawValue)_full_prefill",
            inputNames: prefillInputs,
            outputNames: ["queries", "keys"],
            source: sources.fullPrefill,
            ensureRowContiguous: true
        )
    }
}

private struct NormWeights {
    let query: MLXArray
    let key: MLXArray
    let bank: MLXArray
}

private struct DecodeLayer {
    let family: Family
    let rawQueries: MLXArray
    let rawKeys: MLXArray
    let rawValues: MLXArray
    let weights: NormWeights
    let oldKeys: MLXArray
    let oldValues: MLXArray
    let packedKeys: MLXArray
    let packedValues: MLXArray
}

private struct PrefillLayer {
    let family: Family
    let rawQueries: MLXArray
    let rawKeys: MLXArray
    let weights: NormWeights
}

private struct Fixtures {
    let decodeLayers: [DecodeLayer]
    let prefillLayers: [PrefillLayer]
    let slidingDecodeAngles: MLXArray
    let fullDecodeAngles: MLXArray
    let slidingPrefillAngles: MLXArray
    let fullPrefillAngles: MLXArray
    let offsets: MLXArray
    let scale: MLXArray
    let slidingParams: [MLXArray]
    let fullParams: [MLXArray]
    let steps: Int
    let prefillLength: Int
}

private struct Correctness {
    var bankQueryMaxAbs = Float.zero
    var bankKeyMaxAbs = Float.zero
    var decodeOutputMaxAbs = Float.zero
    var decodeKeyCacheMaxAbs = Float.zero
    var decodeValueCacheMaxAbs = Float.zero
    var prefillQueryMaxAbs = Float.zero
    var prefillKeyMaxAbs = Float.zero
}

private struct TimingSample {
    let workload: String
    let block: Int
    let half: String
    let position: Int
    let abi: ABI
    let seconds: Double
    let thermalBefore: String
    let thermalAfter: String

    var json: [String: Any] {
        [
            "workload": workload,
            "block": block,
            "half": half,
            "position": position,
            "abi": abi.rawValue,
            "seconds": seconds,
            "thermalBefore": thermalBefore,
            "thermalAfter": thermalAfter,
        ]
    }
}

private let repoRoot = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    .deletingLastPathComponent()
    .deletingLastPathComponent()

private func runCommand(_ executable: String, _ arguments: [String], at directory: URL) throws -> String {
    let process = Process()
    let output = Pipe()
    let errors = Pipe()
    process.executableURL = URL(fileURLWithPath: executable)
    process.arguments = arguments
    process.currentDirectoryURL = directory
    process.standardOutput = output
    process.standardError = errors
    try process.run()
    process.waitUntilExit()
    let stdout = String(decoding: output.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
    let stderr = String(decoding: errors.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
    guard process.terminationStatus == 0 else {
        throw BenchmarkError.commandFailed(
            "command failed (\(process.terminationStatus)): \(executable) \(arguments.joined(separator: " "))\n\(stderr)"
        )
    }
    return stdout.trimmingCharacters(in: .whitespacesAndNewlines)
}

private func extractSource(_ text: String, variable: String) throws -> String {
    let declaration = "private let \(variable) = MLXFast.metalKernel("
    guard let declarationRange = text.range(of: declaration) else {
        throw BenchmarkError.invalidSource("missing kernel declaration \(variable)")
    }
    let tail = text[declarationRange.upperBound...]
    guard let sourceMarker = tail.range(of: "source: \"\"\"") else {
        throw BenchmarkError.invalidSource("missing source marker for \(variable)")
    }
    let sourceStart = sourceMarker.upperBound
    guard let sourceEnd = text[sourceStart...].range(of: "\"\"\"") else {
        throw BenchmarkError.invalidSource("missing source terminator for \(variable)")
    }
    return String(text[sourceStart..<sourceEnd.lowerBound])
}

private func loadSources(_ text: String) throws -> KernelSources {
    try KernelSources(
        slidingDecode: extractSource(text, variable: "lagunaSlidingFusedAttentionKernel"),
        fullDecode: extractSource(text, variable: "lagunaFullFusedAttentionKernel"),
        slidingPrefill: extractSource(text, variable: "lagunaPrefillSlidingQKNormRoPEH1Kernel"),
        fullPrefill: extractSource(text, variable: "lagunaPrefillFullQKNormYaRNH1Kernel")
    )
}

private func randomBF16(_ shape: [Int]) -> MLXArray {
    MLXRandom.uniform(low: -0.75, high: 0.75, shape).asType(.bfloat16)
}

private func randomFloat32(_ shape: [Int]) -> MLXArray {
    MLXRandom.uniform(low: -0.5, high: 0.5, shape)
}

private func makeWeights() -> NormWeights {
    let query = randomBF16([headDim])
    let key = randomBF16([headDim])
    let bank = concatenated([query, key], axis: 0)
    return NormWeights(query: query, key: key, bank: bank)
}

private func makeFixtures(quick: Bool) -> Fixtures {
    let steps = quick ? 1 : 128
    let prefillLength = quick ? 8 : 512
    let slidingLayerCount = quick ? 1 : 30
    let fullLayerCount = quick ? 1 : 10
    var decodeLayers = [DecodeLayer]()
    var prefillLayers = [PrefillLayer]()
    var materialized = [MLXArray]()

    func appendLayer(family: Family) {
        let heads = family == .sliding ? slidingHeads : fullHeads
        let capacity = family == .sliding ? slidingWindow : fullCapacity
        let decodeWeights = makeWeights()
        let prefillWeights = makeWeights()
        let decodeLayer = DecodeLayer(
            family: family,
            rawQueries: randomBF16([1, 1, heads * headDim]),
            rawKeys: randomBF16([1, 1, kvHeads * headDim]),
            rawValues: randomBF16([1, 1, kvHeads * headDim]),
            weights: decodeWeights,
            oldKeys: MLXArray.zeros([1, kvHeads, capacity, headDim], dtype: .bfloat16),
            oldValues: MLXArray.zeros([1, kvHeads, capacity, headDim], dtype: .bfloat16),
            packedKeys: MLXArray.zeros([1, kvHeads, capacity, headDim], dtype: .bfloat16),
            packedValues: MLXArray.zeros([1, kvHeads, capacity, headDim], dtype: .bfloat16)
        )
        let prefillLayer = PrefillLayer(
            family: family,
            rawQueries: randomBF16([1, prefillLength, heads * headDim]),
            rawKeys: randomBF16([1, prefillLength, kvHeads * headDim]),
            weights: prefillWeights
        )
        decodeLayers.append(decodeLayer)
        prefillLayers.append(prefillLayer)
        materialized.append(contentsOf: [
            decodeLayer.rawQueries, decodeLayer.rawKeys, decodeLayer.rawValues,
            decodeWeights.query, decodeWeights.key, decodeWeights.bank,
            decodeLayer.oldKeys, decodeLayer.oldValues,
            decodeLayer.packedKeys, decodeLayer.packedValues,
            prefillLayer.rawQueries, prefillLayer.rawKeys,
            prefillWeights.query, prefillWeights.key, prefillWeights.bank,
        ])
    }

    for _ in 0..<slidingLayerCount {
        appendLayer(family: .sliding)
    }
    for _ in 0..<fullLayerCount {
        appendLayer(family: .full)
    }

    let slidingDecodeAngles = randomFloat32([1, 1, 1, headDim])
    let fullDecodeAngles = randomFloat32([1, 1, 1, headDim / 2])
    let slidingPrefillAngles = randomFloat32([1, 1, prefillLength, headDim])
    let fullPrefillAngles = randomFloat32([1, 1, prefillLength, headDim / 2])
    let offsets = MLXArray([Int32(0)])
    let scale = MLXArray([Float(1.0 / sqrt(Float(headDim)))])
    let slidingParams = (0..<steps).map { MLXArray([UInt32($0 % slidingWindow)]) }
    let fullParams = (0..<steps).map {
        MLXArray([UInt32(512 + $0), UInt32(513 + $0), UInt32(fullCapacity)])
    }
    materialized.append(contentsOf: [
        slidingDecodeAngles, fullDecodeAngles,
        slidingPrefillAngles, fullPrefillAngles, offsets, scale,
    ])
    materialized.append(contentsOf: slidingParams)
    materialized.append(contentsOf: fullParams)
    eval(materialized)

    return Fixtures(
        decodeLayers: decodeLayers,
        prefillLayers: prefillLayers,
        slidingDecodeAngles: slidingDecodeAngles,
        fullDecodeAngles: fullDecodeAngles,
        slidingPrefillAngles: slidingPrefillAngles,
        fullPrefillAngles: fullPrefillAngles,
        offsets: offsets,
        scale: scale,
        slidingParams: slidingParams,
        fullParams: fullParams,
        steps: steps,
        prefillLength: prefillLength
    )
}

private func decode(
    kernels: Kernels,
    abi: ABI,
    fixtures: Fixtures,
    stream: MLX.Stream
) -> [MLXArray] {
    var finalOutputs = [MLXArray]()
    for step in 0..<fixtures.steps {
        var outputs = [MLXArray]()
        outputs.reserveCapacity(fixtures.decodeLayers.count)
        for layer in fixtures.decodeLayers {
            let cacheKeys = abi == .old ? layer.oldKeys : layer.packedKeys
            let cacheValues = abi == .old ? layer.oldValues : layer.packedValues
            let angles: MLXArray
            let params: MLXArray
            let kernel: MLXFast.MLXFastKernel
            let heads: Int
            switch layer.family {
            case .sliding:
                angles = fixtures.slidingDecodeAngles
                params = fixtures.slidingParams[step]
                kernel = kernels.slidingDecode
                heads = slidingHeads
            case .full:
                angles = fixtures.fullDecodeAngles
                params = fixtures.fullParams[step]
                kernel = kernels.fullDecode
                heads = fullHeads
            }
            let inputs: [any ScalarOrArray]
            switch abi {
            case .old:
                inputs = [
                    layer.rawQueries, layer.rawKeys, layer.rawValues,
                    layer.weights.query, layer.weights.key, angles,
                    cacheKeys, cacheValues, params, fixtures.scale,
                ]
            case .packed:
                inputs = [
                    layer.rawQueries, layer.rawKeys, layer.rawValues,
                    layer.weights.bank, angles,
                    cacheKeys, cacheValues, params, fixtures.scale,
                ]
            }
            let output = kernel(
                inputs,
                grid: ((heads / 2) * 1024, 1, 1),
                threadGroup: (1024, 1, 1),
                outputShapes: [[1, heads, 1, headDim]],
                outputDTypes: [.bfloat16],
                stream: stream
            )[0]
            outputs.append(output)
        }
        eval(outputs)
        stream.synchronize()
        if step == fixtures.steps - 1 {
            finalOutputs = outputs
        }
    }
    return finalOutputs
}

private func prefill(
    kernels: Kernels,
    abi: ABI,
    fixtures: Fixtures,
    stream: MLX.Stream
) -> [MLXArray] {
    var outputs = [MLXArray]()
    outputs.reserveCapacity(fixtures.prefillLayers.count * 2)
    for layer in fixtures.prefillLayers {
        let angles: MLXArray
        let kernel: MLXFast.MLXFastKernel
        let heads: Int
        switch layer.family {
        case .sliding:
            angles = fixtures.slidingPrefillAngles
            kernel = kernels.slidingPrefill
            heads = slidingHeads
        case .full:
            angles = fixtures.fullPrefillAngles
            kernel = kernels.fullPrefill
            heads = fullHeads
        }
        let inputs: [any ScalarOrArray]
        switch abi {
        case .old:
            inputs = [
                layer.rawQueries, layer.rawKeys,
                layer.weights.query, layer.weights.key, angles, fixtures.offsets,
            ]
        case .packed:
            inputs = [
                layer.rawQueries, layer.rawKeys,
                layer.weights.bank, angles, fixtures.offsets,
            ]
        }
        outputs.append(contentsOf: kernel(
            inputs,
            grid: ((heads + kvHeads) * 32, fixtures.prefillLength, 1),
            threadGroup: (32, 1, 1),
            outputShapes: [
                [1, heads, fixtures.prefillLength, headDim],
                [1, kvHeads, fixtures.prefillLength, headDim],
            ],
            outputDTypes: [.bfloat16, .bfloat16],
            stream: stream
        ))
    }
    eval(outputs)
    stream.synchronize()
    return outputs
}

private func maxAbsDiff(_ lhs: MLXArray, _ rhs: MLXArray) -> Float {
    abs(lhs.asType(.float32) - rhs.asType(.float32)).max().item(Float.self)
}

private func verifyCorrectness(
    old: Kernels,
    packed: Kernels,
    fixtures: Fixtures,
    stream: MLX.Stream
) throws -> Correctness {
    var result = Correctness()
    for layer in fixtures.decodeLayers {
        result.bankQueryMaxAbs = max(
            result.bankQueryMaxAbs,
            maxAbsDiff(layer.weights.bank[0..<headDim], layer.weights.query)
        )
        result.bankKeyMaxAbs = max(
            result.bankKeyMaxAbs,
            maxAbsDiff(layer.weights.bank[headDim..<(2 * headDim)], layer.weights.key)
        )
    }
    for layer in fixtures.prefillLayers {
        result.bankQueryMaxAbs = max(
            result.bankQueryMaxAbs,
            maxAbsDiff(layer.weights.bank[0..<headDim], layer.weights.query)
        )
        result.bankKeyMaxAbs = max(
            result.bankKeyMaxAbs,
            maxAbsDiff(layer.weights.bank[headDim..<(2 * headDim)], layer.weights.key)
        )
    }

    let oldDecode = decode(kernels: old, abi: .old, fixtures: fixtures, stream: stream)
    let packedDecode = decode(kernels: packed, abi: .packed, fixtures: fixtures, stream: stream)
    for (oldOutput, packedOutput) in zip(oldDecode, packedDecode) {
        result.decodeOutputMaxAbs = max(
            result.decodeOutputMaxAbs, maxAbsDiff(oldOutput, packedOutput))
    }
    for layer in fixtures.decodeLayers {
        result.decodeKeyCacheMaxAbs = max(
            result.decodeKeyCacheMaxAbs, maxAbsDiff(layer.oldKeys, layer.packedKeys))
        result.decodeValueCacheMaxAbs = max(
            result.decodeValueCacheMaxAbs, maxAbsDiff(layer.oldValues, layer.packedValues))
    }

    let oldPrefill = prefill(kernels: old, abi: .old, fixtures: fixtures, stream: stream)
    let packedPrefill = prefill(kernels: packed, abi: .packed, fixtures: fixtures, stream: stream)
    for index in stride(from: 0, to: oldPrefill.count, by: 2) {
        result.prefillQueryMaxAbs = max(
            result.prefillQueryMaxAbs,
            maxAbsDiff(oldPrefill[index], packedPrefill[index])
        )
        result.prefillKeyMaxAbs = max(
            result.prefillKeyMaxAbs,
            maxAbsDiff(oldPrefill[index + 1], packedPrefill[index + 1])
        )
    }

    let all = [
        result.bankQueryMaxAbs, result.bankKeyMaxAbs,
        result.decodeOutputMaxAbs, result.decodeKeyCacheMaxAbs,
        result.decodeValueCacheMaxAbs, result.prefillQueryMaxAbs,
        result.prefillKeyMaxAbs,
    ]
    guard all.allSatisfy({ $0 == 0 }) else {
        throw BenchmarkError.invariant("old and packed ABIs are not bit exact: \(result)")
    }
    return result
}

private func thermalState() -> String {
    switch ProcessInfo.processInfo.thermalState {
    case .nominal: return "nominal"
    case .fair: return "fair"
    case .serious: return "serious"
    case .critical: return "critical"
    @unknown default: return "unknown"
    }
}

private func timeWorkload(
    name: String,
    repeats: Int,
    old: Kernels,
    packed: Kernels,
    fixtures: Fixtures,
    stream: MLX.Stream,
    operation: (Kernels, ABI, Fixtures, MLX.Stream) -> [MLXArray]
) -> [TimingSample] {
    let order: [(ABI, String, Int)] = [
        (.packed, "BAAB", 0), (.old, "BAAB", 1),
        (.old, "BAAB", 2), (.packed, "BAAB", 3),
        (.old, "ABBA", 0), (.packed, "ABBA", 1),
        (.packed, "ABBA", 2), (.old, "ABBA", 3),
    ]
    var samples = [TimingSample]()
    for block in 0..<repeats {
        for (abi, half, position) in order {
            stream.synchronize()
            let beforeThermal = thermalState()
            let start = DispatchTime.now().uptimeNanoseconds
            _ = operation(abi == .old ? old : packed, abi, fixtures, stream)
            stream.synchronize()
            let end = DispatchTime.now().uptimeNanoseconds
            let afterThermal = thermalState()
            let seconds = Double(end - start) / 1_000_000_000
            let sample = TimingSample(
                workload: name,
                block: block,
                half: half,
                position: position,
                abi: abi,
                seconds: seconds,
                thermalBefore: beforeThermal,
                thermalAfter: afterThermal
            )
            samples.append(sample)
            print(
                String(
                    format: "TIMING workload=%@ block=%d half=%@ position=%d abi=%@ seconds=%.9f thermal=%@->%@",
                    name, block, half, position, abi.rawValue, seconds, beforeThermal, afterThermal
                )
            )
        }
    }
    return samples
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let midpoint = sorted.count / 2
    if sorted.count % 2 == 0 {
        return (sorted[midpoint - 1] + sorted[midpoint]) / 2
    }
    return sorted[midpoint]
}

private func summary(_ samples: [TimingSample]) -> [String: Any] {
    let old = samples.filter { $0.abi == .old }.map(\.seconds)
    let packed = samples.filter { $0.abi == .packed }.map(\.seconds)
    let oldMedian = median(old)
    let packedMedian = median(packed)
    var orders = [[String: Any]]()
    for block in Set(samples.map(\.block)).sorted() {
        for half in ["BAAB", "ABBA"] {
            let subset = samples.filter { $0.block == block && $0.half == half }
            let oldSeconds = subset.filter { $0.abi == .old }.map(\.seconds)
            let packedSeconds = subset.filter { $0.abi == .packed }.map(\.seconds)
            let oldHalfMedian = median(oldSeconds)
            let packedHalfMedian = median(packedSeconds)
            orders.append([
                "block": block,
                "order": half,
                "oldMedianSeconds": oldHalfMedian,
                "packedMedianSeconds": packedHalfMedian,
                "speedup": oldHalfMedian / packedHalfMedian,
            ])
        }
    }
    return [
        "oldMedianSeconds": oldMedian,
        "packedMedianSeconds": packedMedian,
        "speedup": oldMedian / packedMedian,
        "orderSummaries": orders,
    ]
}

private func rowMajorStrides(_ shape: [Int]) -> [Int] {
    var result = Array(repeating: 1, count: shape.count)
    guard shape.count > 1 else { return result }
    for index in stride(from: shape.count - 2, through: 0, by: -1) {
        result[index] = result[index + 1] * shape[index + 1]
    }
    return result
}

private func layout(_ array: MLXArray) -> [String: Any] {
    let data = array.asData(access: .noCopy)
    return [
        "shape": data.shape,
        "strides": data.strides,
        "contiguous": data.strides == rowMajorStrides(data.shape),
        "dtype": String(describing: data.dType),
    ]
}

private func emitJSON(_ object: [String: Any]) throws {
    let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    print("RESULT_JSON \(String(decoding: data, as: UTF8.self))")
}

private func run() throws {
    let options = try Options.parse()
    guard FileManager.default.fileExists(
        atPath: repoRoot.appendingPathComponent("Sources/MLXFastModel/LagunaRuntimeModel.swift").path
    ) else {
        throw BenchmarkError.invariant("run from research/qk-abi-bench")
    }
    let runtimePath = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
    let headSHA = try runCommand("/usr/bin/git", ["rev-parse", "HEAD"], at: repoRoot)
    let currentRuntimeBlob = try runCommand("/usr/bin/git", ["hash-object", runtimePath], at: repoRoot)
    let candidateRuntimeBlob = try runCommand(
        "/usr/bin/git", ["rev-parse", "\(candidateRuntimeSHA):\(runtimePath)"], at: repoRoot
    )
    guard currentRuntimeBlob == candidateRuntimeBlob else {
        throw BenchmarkError.invariant(
            "runtime blob \(currentRuntimeBlob) differs from candidate \(candidateRuntimeBlob)"
        )
    }
    let currentText = try String(
        contentsOf: repoRoot.appendingPathComponent(runtimePath),
        encoding: .utf8
    )
    let baselineText = try runCommand(
        "/usr/bin/git",
        ["show", "\(baselineSHA):\(runtimePath)"],
        at: repoRoot
    )
    let oldSources = try loadSources(baselineText)
    let packedSources = try loadSources(currentText)
    let old = Kernels(sources: oldSources, abi: .old)
    let packed = Kernels(sources: packedSources, abi: .packed)

    MLXRandom.seed(613)
    let stream = MLX.Stream()
    let fixtures = makeFixtures(quick: options.quick)
    let firstBank = fixtures.decodeLayers[0].weights.bank
    let firstQuery = fixtures.decodeLayers[0].weights.query
    let firstKey = fixtures.decodeLayers[0].weights.key
    let correctness = try verifyCorrectness(
        old: old, packed: packed, fixtures: fixtures, stream: stream
    )
    print("CORRECTNESS \(correctness)")

    _ = decode(kernels: old, abi: .old, fixtures: fixtures, stream: stream)
    _ = decode(kernels: packed, abi: .packed, fixtures: fixtures, stream: stream)
    _ = prefill(kernels: old, abi: .old, fixtures: fixtures, stream: stream)
    _ = prefill(kernels: packed, abi: .packed, fixtures: fixtures, stream: stream)
    stream.synchronize()

    var decodeSamples = [TimingSample]()
    var prefillSamples = [TimingSample]()
    if !options.quick {
        decodeSamples = timeWorkload(
            name: "decode",
            repeats: options.repeats,
            old: old,
            packed: packed,
            fixtures: fixtures,
            stream: stream,
            operation: { kernels, abi, fixtures, stream in
                decode(kernels: kernels, abi: abi, fixtures: fixtures, stream: stream)
            }
        )
        prefillSamples = timeWorkload(
            name: "prefill",
            repeats: options.repeats,
            old: old,
            packed: packed,
            fixtures: fixtures,
            stream: stream,
            operation: { kernels, abi, fixtures, stream in
                prefill(kernels: kernels, abi: abi, fixtures: fixtures, stream: stream)
            }
        )
    }

    var result: [String: Any] = [
        "schemaVersion": 1,
        "baselineSHA": baselineSHA,
        "candidateRuntimeSHA": candidateRuntimeSHA,
        "candidateRuntimeBlob": candidateRuntimeBlob,
        "headSHA": headSHA,
        "quick": options.quick,
        "repetitions": options.quick ? 0 : options.repeats,
        "timingOrderPerBlock": "BAAB_ABBA",
        "thermalStart": thermalState(),
        "architecture": try runCommand("/usr/sbin/sysctl", ["-n", "machdep.cpu.brand_string"], at: repoRoot),
        "familyReach": [
            "decodeSlidingFused": true,
            "decodeFullFused": true,
            "prefillSlidingH1": true,
            "prefillFullH1": true,
            "standaloneDecodeQKFallback": false,
        ],
        "dispatchCountsPerObservation": [
            "decodeSteps": fixtures.steps,
            "decodeSliding": fixtures.steps * fixtures.decodeLayers.filter { $0.family == .sliding }.count,
            "decodeFull": fixtures.steps * fixtures.decodeLayers.filter { $0.family == .full }.count,
            "prefillLength": fixtures.prefillLength,
            "prefillSliding": fixtures.prefillLayers.filter { $0.family == .sliding }.count,
            "prefillFull": fixtures.prefillLayers.filter { $0.family == .full }.count,
        ],
        "bindingCounts": [
            "decodeOld": 10,
            "decodePacked": 9,
            "prefillOld": 6,
            "prefillPacked": 5,
        ],
        "bank": [
            "kOffsetElements": headDim,
            "kOffsetBytes": headDim * 2,
            "materializedBeforeTiming": true,
            "hotPathMaterialization": false,
            "queryLayout": layout(firstQuery),
            "keyLayout": layout(firstKey),
            "bankLayout": layout(firstBank),
        ],
        "correctness": [
            "bankQueryMaxAbs": correctness.bankQueryMaxAbs,
            "bankKeyMaxAbs": correctness.bankKeyMaxAbs,
            "decodeOutputMaxAbs": correctness.decodeOutputMaxAbs,
            "decodeKeyCacheMaxAbs": correctness.decodeKeyCacheMaxAbs,
            "decodeValueCacheMaxAbs": correctness.decodeValueCacheMaxAbs,
            "prefillQueryMaxAbs": correctness.prefillQueryMaxAbs,
            "prefillKeyMaxAbs": correctness.prefillKeyMaxAbs,
        ],
        "rawTimings": (decodeSamples + prefillSamples).map(\.json),
        "thermalEnd": thermalState(),
    ]
    if !options.quick {
        let decodeSummary = summary(decodeSamples)
        let prefillSummary = summary(prefillSamples)
        let decodeSpeedup = decodeSummary["speedup"] as! Double
        let prefillSpeedup = prefillSummary["speedup"] as! Double
        result["decode"] = decodeSummary
        result["prefill"] = prefillSummary
        result["weightedSpeedup"] = pow(decodeSpeedup, 0.75) * pow(prefillSpeedup, 0.25)
    }
    try emitJSON(result)
}

do {
    try run()
} catch {
    fputs("QK ABI benchmark failed: \(error)\n", stderr)
    exit(1)
}
