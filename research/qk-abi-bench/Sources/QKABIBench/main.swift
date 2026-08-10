import Dispatch
import Foundation
import MLX
import MLXRandom

private let baselineSHA = "52a1425929dc545596e841ef1bc9d0dc761def74"
private let candidateRuntimeSHA = "098f29e4d5e8257740c98c2450b3e5337a3b2dbc"
private let headDim = 128
private let kvHeads = 8
private let slidingHeads = 64
private let fullHeads = 48
private let slidingWindow = 512
private let fullCapacity = 768
private let decodeSteps = 128
private let baseDecodeSequenceSeconds = 0.0127166572265625 * 128.0

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
    let blocks: Int

    static func parse() throws -> Options {
        let arguments = Array(CommandLine.arguments.dropFirst())
        var quick = false
        var blocks = 32
        var index = 0
        while index < arguments.count {
            switch arguments[index] {
            case "--quick":
                quick = true
                index += 1
            case "--blocks", "--repeats":
                guard index + 1 < arguments.count,
                      let value = Int(arguments[index + 1]), value > 0
                else {
                    throw BenchmarkError.invariant("--blocks requires a positive integer")
                }
                blocks = value
                index += 2
            default:
                throw BenchmarkError.invariant("unknown argument: \(arguments[index])")
            }
        }
        if !quick && blocks < 32 {
            throw BenchmarkError.invariant("Gate 2 requires at least 32 timing blocks")
        }
        return Options(quick: quick, blocks: blocks)
    }
}

private struct KernelSource {
    let source: String
    let header: String
}

private struct KernelSources {
    let sliding: KernelSource
    let full: KernelSource
}

private struct Kernels {
    let sliding: MLXFast.MLXFastKernel
    let full: MLXFast.MLXFastKernel

    init(sources: KernelSources, abi: ABI) {
        let inputs: [String]
        switch abi {
        case .old:
            inputs = [
                "raw_queries", "raw_keys", "raw_values",
                "query_weight", "key_weight", "angles",
                "k_cache", "v_cache", "params", "scale_arr",
            ]
        case .packed:
            inputs = [
                "raw_queries", "raw_keys", "raw_values",
                "qk_norm_weight", "angles",
                "k_cache", "v_cache", "params", "scale_arr",
            ]
        }
        sliding = MLXFast.metalKernel(
            name: "decode_qk_bank_\(abi.rawValue)_sliding",
            inputNames: inputs,
            outputNames: ["attended"],
            source: sources.sliding.source,
            header: sources.sliding.header,
            ensureRowContiguous: true
        )
        full = MLXFast.metalKernel(
            name: "decode_qk_bank_\(abi.rawValue)_full",
            inputNames: inputs,
            outputNames: ["attended"],
            source: sources.full.source,
            header: sources.full.header,
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
    let id: Int
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

private struct Fixtures {
    let layers: [DecodeLayer]
    let slidingAngles: MLXArray
    let fullAngles: MLXArray
    let scale: MLXArray
    let slidingParams: [MLXArray]
    let fullParams: [MLXArray]
}

private struct Correctness {
    var bankQueryRawExact = true
    var bankKeyRawExact = true
    var attendedRawExact = true
    var keyCacheRawExact = true
    var valueCacheRawExact = true
    var cacheClocksExact = true
    var exactCases = 0
    var packedCases = 0
    var fallbackCases = 0
    var corruptionDetected = false

    var json: [String: Any] {
        [
            "bankQueryRawExact": bankQueryRawExact,
            "bankKeyRawExact": bankKeyRawExact,
            "attendedRawExact": attendedRawExact,
            "entireKeyCacheRawExact": keyCacheRawExact,
            "entireValueCacheRawExact": valueCacheRawExact,
            "cacheClocksAndPositionsExact": cacheClocksExact,
            "exactCases": exactCases,
            "packedEligibleCases": packedCases,
            "stockFallbackCases": fallbackCases,
            "corruptionControlDetected": corruptionDetected,
        ]
    }
}

private struct TimingSample {
    let block: Int
    let order: String
    let position: Int
    let abi: ABI
    let seconds: Double
    let thermalBefore: String
    let thermalAfter: String

    var json: [String: Any] {
        [
            "block": block,
            "order": order,
            "position": position,
            "abi": abi.rawValue,
            "seconds": seconds,
            "thermalBefore": thermalBefore,
            "thermalAfter": thermalAfter,
        ]
    }
}

private struct LCG {
    var state: UInt64

    mutating func index(upperBound: Int) -> Int {
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        return Int((state >> 32) % UInt64(upperBound))
    }
}

private let repoRoot = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    .deletingLastPathComponent()
    .deletingLastPathComponent()

private func progress(_ message: String) {
    FileHandle.standardError.write(Data("PROGRESS \(message)\n".utf8))
}

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
    let stdout = String(decoding: output.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
    process.waitUntilExit()
    let stderr = String(decoding: errors.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
    guard process.terminationStatus == 0 else {
        throw BenchmarkError.commandFailed(
            "command failed (\(process.terminationStatus)): \(executable) \(arguments.joined(separator: " "))\n\(stderr)"
        )
    }
    return stdout.trimmingCharacters(in: .whitespacesAndNewlines)
}

private func declarationRange(_ text: String, variable: String) throws -> Range<String.Index> {
    let declaration = "private let \(variable) = MLXFast.metalKernel("
    guard let declarationStart = text.range(of: declaration) else {
        throw BenchmarkError.invalidSource("missing kernel declaration \(variable)")
    }
    let tail = text[declarationStart.upperBound...]
    guard let sourceMarker = tail.range(of: "source: \"\"\"") else {
        throw BenchmarkError.invalidSource("missing source marker for \(variable)")
    }
    guard let sourceEnd = text[sourceMarker.upperBound...].range(of: "\"\"\"") else {
        throw BenchmarkError.invalidSource("missing source terminator for \(variable)")
    }
    guard let declarationEnd = text[sourceEnd.upperBound...].range(of: "\n)\n") else {
        throw BenchmarkError.invalidSource("missing declaration terminator for \(variable)")
    }
    return declarationStart.lowerBound..<declarationEnd.upperBound
}

private func extractSource(_ text: String, variable: String) throws -> KernelSource {
    let range = try declarationRange(text, variable: variable)
    let declaration = text[range]
    guard let sourceMarker = declaration.range(of: "source: \"\"\"") else {
        throw BenchmarkError.invalidSource("missing source marker for \(variable)")
    }
    guard let sourceEnd = declaration[sourceMarker.upperBound...].range(of: "\"\"\"") else {
        throw BenchmarkError.invalidSource("missing source terminator for \(variable)")
    }
    let arguments = declaration[sourceEnd.upperBound...]
    let header: String
    if let headerMarker = arguments.range(of: "header: \"\"\"") {
        guard let headerEnd = arguments[headerMarker.upperBound...].range(of: "\"\"\"") else {
            throw BenchmarkError.invalidSource("missing header terminator for \(variable)")
        }
        header = String(arguments[headerMarker.upperBound..<headerEnd.lowerBound])
            .replacingOccurrences(of: "\\\\", with: "\\")
    } else {
        header = ""
    }
    return KernelSource(
        source: String(declaration[sourceMarker.upperBound..<sourceEnd.lowerBound]),
        header: header
    )
}

private func extractDeclaration(_ text: String, variable: String) throws -> String {
    String(text[try declarationRange(text, variable: variable)])
}

private func loadSources(_ text: String) throws -> KernelSources {
    try KernelSources(
        sliding: extractSource(text, variable: "lagunaSlidingFusedAttentionKernel"),
        full: extractSource(text, variable: "lagunaFullFusedAttentionKernel")
    )
}

private func occurrences(of needle: String, in text: String) -> Int {
    var count = 0
    var remainder = text[...]
    while let range = remainder.range(of: needle) {
        count += 1
        remainder = remainder[range.upperBound...]
    }
    return count
}

private func staticAudit(baseline: String, candidate: String) throws -> [String: Any] {
    let prefillVariables = [
        "lagunaPrefillSlidingQKNormRoPEKernel",
        "lagunaPrefillSlidingQKNormRoPEH1Kernel",
        "lagunaPrefillFullQKNormYaRNKernel",
        "lagunaPrefillFullQKNormYaRNH1Kernel",
    ]
    var prefill = [[String: Any]]()
    for variable in prefillVariables {
        let old = try extractDeclaration(baseline, variable: variable)
        let new = try extractDeclaration(candidate, variable: variable)
        prefill.append([
            "symbol": variable,
            "declarationExact": old == new,
            "inputABIExact": old == new,
            "packedBindingPresent": new.contains("qk_norm_weight"),
        ])
        guard old == new, !new.contains("qk_norm_weight") else {
            throw BenchmarkError.invariant("prefill ABI changed for \(variable)")
        }
    }

    let sliding = try extractDeclaration(candidate, variable: "lagunaSlidingFusedAttentionKernel")
    let full = try extractDeclaration(candidate, variable: "lagunaFullFusedAttentionKernel")
    guard sliding.contains("\"qk_norm_weight\""), full.contains("\"qk_norm_weight\"") else {
        throw BenchmarkError.invariant("decode fused kernels do not bind qk_norm_weight")
    }
    guard sliding.contains("qk_norm_weight + (sg == 2 ? head_dim : 0)"),
          full.contains("qk_norm_weight + (sg == 2 ? head_dim : 0)")
    else {
        throw BenchmarkError.invariant("decode K offset is not head_dim")
    }

    let fullLayerIDs = Array(stride(from: 0, to: 40, by: 4))
    let slidingLayerIDs = (0..<40).filter { $0 % 4 != 0 }
    let fallbackSelectors = [
        "} else if useFusedFullQKNormYaRN",
        "} else if useFusedSlidingQKNormRoPE",
    ]
    let fallbackPreserved = fallbackSelectors.allSatisfy {
        let baselineCount = occurrences(of: $0, in: baseline)
        return baselineCount > 0 && occurrences(of: $0, in: candidate) == baselineCount
    }
    return [
        "prefillDeclarations": prefill,
        "prefillPackedSelectionsAt512": 0,
        "decodePackedKernelDeclarations": 2,
        "qkNormWeightOccurrencesInRuntime": occurrences(of: "qk_norm_weight", in: candidate),
        "slidingLayerIDs": slidingLayerIDs,
        "fullLayerIDs": fullLayerIDs,
        "productionLayerOrder": (0..<40).map { $0 % 4 == 0 ? "full" : "sliding" },
        "fullFirstDecodeUsesStockFallback": true,
        "fallbackPreserved": fallbackPreserved,
        "bankPreparedBeforeScoredForward": candidate.contains("prepareFusedRuntimeWeights")
            && candidate.contains("prepareFusedQKNormWeight"),
    ]
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
    return NormWeights(query: query, key: key, bank: concatenated([query, key], axis: 0))
}

private func makeFixtures() -> Fixtures {
    var layers = [DecodeLayer]()
    var materialized = [MLXArray]()
    for id in 0..<40 {
        let family: Family = id % 4 == 0 ? .full : .sliding
        let heads = family == .sliding ? slidingHeads : fullHeads
        let capacity = family == .sliding ? slidingWindow : fullCapacity
        let weights = makeWeights()
        let layer = DecodeLayer(
            id: id,
            family: family,
            rawQueries: randomBF16([1, 1, heads * headDim]),
            rawKeys: randomBF16([1, 1, kvHeads * headDim]),
            rawValues: randomBF16([1, 1, kvHeads * headDim]),
            weights: weights,
            oldKeys: MLXArray.zeros([1, kvHeads, capacity, headDim], dtype: .bfloat16),
            oldValues: MLXArray.zeros([1, kvHeads, capacity, headDim], dtype: .bfloat16),
            packedKeys: MLXArray.zeros([1, kvHeads, capacity, headDim], dtype: .bfloat16),
            packedValues: MLXArray.zeros([1, kvHeads, capacity, headDim], dtype: .bfloat16)
        )
        layers.append(layer)
        materialized.append(contentsOf: [
            layer.rawQueries, layer.rawKeys, layer.rawValues,
            weights.query, weights.key, weights.bank,
            layer.oldKeys, layer.oldValues, layer.packedKeys, layer.packedValues,
        ])
    }

    let slidingAngles = randomFloat32([1, 1, 1, headDim])
    let fullAngles = randomFloat32([1, 1, 1, headDim / 2])
    let scale = MLXArray([Float(1.0 / sqrt(Float(headDim)))])
    let slidingParams = (0..<decodeSteps).map { MLXArray([UInt32($0)]) }
    let fullParams = (0..<(decodeSteps - 1)).map {
        MLXArray([UInt32(513 + $0), UInt32(514 + $0), UInt32(fullCapacity)])
    }
    materialized.append(contentsOf: [slidingAngles, fullAngles, scale])
    materialized.append(contentsOf: slidingParams)
    materialized.append(contentsOf: fullParams)
    eval(materialized)
    MLX.Stream.gpu.synchronize()
    return Fixtures(
        layers: layers,
        slidingAngles: slidingAngles,
        fullAngles: fullAngles,
        scale: scale,
        slidingParams: slidingParams,
        fullParams: fullParams
    )
}

private func dispatch(
    kernels: Kernels,
    abi: ABI,
    layer: DecodeLayer,
    keys: MLXArray,
    values: MLXArray,
    params: MLXArray,
    fixtures: Fixtures,
    bankOverride: MLXArray? = nil,
    stream: MLX.Stream
) -> MLXArray {
    let kernel = layer.family == .sliding ? kernels.sliding : kernels.full
    let angles = layer.family == .sliding ? fixtures.slidingAngles : fixtures.fullAngles
    let heads = layer.family == .sliding ? slidingHeads : fullHeads
    let inputs: [any ScalarOrArray]
    switch abi {
    case .old:
        inputs = [
            layer.rawQueries, layer.rawKeys, layer.rawValues,
            layer.weights.query, layer.weights.key, angles,
            keys, values, params, fixtures.scale,
        ]
    case .packed:
        inputs = [
            layer.rawQueries, layer.rawKeys, layer.rawValues,
            bankOverride ?? layer.weights.bank, angles,
            keys, values, params, fixtures.scale,
        ]
    }
    return kernel(
        inputs,
        grid: ((heads / 2) * 1024, 1, 1),
        threadGroup: (1024, 1, 1),
        outputShapes: [[1, heads, 1, headDim]],
        outputDTypes: [.bfloat16],
        stream: .stream(stream)
    )[0]
}

private func rawEqual(_ lhs: MLXArray, _ rhs: MLXArray) -> Bool {
    let left = lhs.asData(access: .copy)
    let right = rhs.asData(access: .copy)
    return left.shape == right.shape
        && left.strides == right.strides
        && left.dType == right.dType
        && left.data == right.data
}

private func params(family: Family, writeIndex: Int) -> MLXArray {
    switch family {
    case .sliding:
        return MLXArray([UInt32(writeIndex)])
    case .full:
        return MLXArray([UInt32(writeIndex), UInt32(writeIndex + 1), UInt32(fullCapacity)])
    }
}

private func verifyCorrectness(
    old: Kernels,
    packed: Kernels,
    fixtures: Fixtures,
    stream: MLX.Stream
) throws -> Correctness {
    var result = Correctness()
    progress("Gate 1 bank layout and 40-layer target indices")
    for layer in fixtures.layers {
        result.bankQueryRawExact = result.bankQueryRawExact
            && rawEqual(layer.weights.bank[0..<headDim], layer.weights.query)
        result.bankKeyRawExact = result.bankKeyRawExact
            && rawEqual(layer.weights.bank[headDim..<(2 * headDim)], layer.weights.key)

        let targetIndices = layer.family == .sliding ? [0, 1, 511] : [512, 513, 639, 767]
        for writeIndex in targetIndices {
            let capacity = layer.family == .sliding ? slidingWindow : fullCapacity
            let oldKeys = MLXArray.zeros([1, kvHeads, capacity, headDim], dtype: .bfloat16)
            let oldValues = MLXArray.zeros([1, kvHeads, capacity, headDim], dtype: .bfloat16)
            let otherKeys = MLXArray.zeros([1, kvHeads, capacity, headDim], dtype: .bfloat16)
            let otherValues = MLXArray.zeros([1, kvHeads, capacity, headDim], dtype: .bfloat16)
            let callParams = params(family: layer.family, writeIndex: writeIndex)
            let oldOutput = dispatch(
                kernels: old, abi: .old, layer: layer,
                keys: oldKeys, values: oldValues, params: callParams,
                fixtures: fixtures, stream: stream
            )
            let usesFallback = layer.family == .full && writeIndex == 512
            let otherOutput = dispatch(
                kernels: usesFallback ? old : packed,
                abi: usesFallback ? .old : .packed,
                layer: layer,
                keys: otherKeys, values: otherValues, params: callParams,
                fixtures: fixtures, stream: stream
            )
            eval([oldOutput, otherOutput, oldKeys, oldValues, otherKeys, otherValues])
            stream.synchronize()
            result.attendedRawExact = result.attendedRawExact && rawEqual(oldOutput, otherOutput)
            result.keyCacheRawExact = result.keyCacheRawExact && rawEqual(oldKeys, otherKeys)
            result.valueCacheRawExact = result.valueCacheRawExact && rawEqual(oldValues, otherValues)
            result.cacheClocksExact = result.cacheClocksExact
                && writeIndex + 1 <= capacity
            result.exactCases += 1
            if usesFallback {
                result.fallbackCases += 1
            } else {
                result.packedCases += 1
            }
        }
    }

    guard let slidingLayer = fixtures.layers.first(where: { $0.family == .sliding }) else {
        throw BenchmarkError.invariant("missing sliding layer")
    }
    let capacity = slidingWindow
    let goodKeys = MLXArray.zeros([1, kvHeads, capacity, headDim], dtype: .bfloat16)
    let goodValues = MLXArray.zeros([1, kvHeads, capacity, headDim], dtype: .bfloat16)
    let badKeys = MLXArray.zeros([1, kvHeads, capacity, headDim], dtype: .bfloat16)
    let badValues = MLXArray.zeros([1, kvHeads, capacity, headDim], dtype: .bfloat16)
    let corruptedBank = concatenated([
        slidingLayer.weights.query,
        MLXArray.zeros([headDim], dtype: .bfloat16),
    ], axis: 0)
    eval(corruptedBank)
    let goodOutput = dispatch(
        kernels: packed, abi: .packed, layer: slidingLayer,
        keys: goodKeys, values: goodValues, params: params(family: .sliding, writeIndex: 0),
        fixtures: fixtures, stream: stream
    )
    let badOutput = dispatch(
        kernels: packed, abi: .packed, layer: slidingLayer,
        keys: badKeys, values: badValues, params: params(family: .sliding, writeIndex: 0),
        fixtures: fixtures, bankOverride: corruptedBank, stream: stream
    )
    eval([goodOutput, badOutput, goodKeys, badKeys])
    stream.synchronize()
    result.corruptionDetected = !rawEqual(goodOutput, badOutput) || !rawEqual(goodKeys, badKeys)

    guard result.bankQueryRawExact, result.bankKeyRawExact,
          result.attendedRawExact, result.keyCacheRawExact,
          result.valueCacheRawExact, result.cacheClocksExact,
          result.corruptionDetected,
          result.exactCases == 130,
          result.packedCases == 120,
          result.fallbackCases == 10
    else {
        throw BenchmarkError.invariant("Gate 1 exactness failed: \(result.json)")
    }
    return result
}

@discardableResult
private func runProductionSequence(
    kernels: Kernels,
    abi: ABI,
    fixtures: Fixtures,
    stream: MLX.Stream
) -> Int {
    var dispatches = 0
    for step in 0..<decodeSteps {
        var outputs = [MLXArray]()
        outputs.reserveCapacity(40)
        for layer in fixtures.layers {
            if layer.family == .full && step == decodeSteps - 1 {
                continue
            }
            let keys = abi == .old ? layer.oldKeys : layer.packedKeys
            let values = abi == .old ? layer.oldValues : layer.packedValues
            let callParams = layer.family == .sliding
                ? fixtures.slidingParams[step]
                : fixtures.fullParams[step]
            outputs.append(dispatch(
                kernels: kernels,
                abi: abi,
                layer: layer,
                keys: keys,
                values: values,
                params: callParams,
                fixtures: fixtures,
                stream: stream
            ))
            dispatches += 1
        }
        eval(outputs)
    }
    return dispatches
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

private func timeSequences(
    blocks: Int,
    old: Kernels,
    packed: Kernels,
    fixtures: Fixtures,
    stream: MLX.Stream
) throws -> [TimingSample] {
    let order: [(ABI, String, Int)] = [
        (.packed, "BAAB", 0), (.old, "BAAB", 1),
        (.old, "BAAB", 2), (.packed, "BAAB", 3),
        (.old, "ABBA", 0), (.packed, "ABBA", 1),
        (.packed, "ABBA", 2), (.old, "ABBA", 3),
    ]
    var samples = [TimingSample]()
    for block in 0..<blocks {
        for (abi, half, position) in order {
            stream.synchronize()
            let before = thermalState()
            let start = DispatchTime.now().uptimeNanoseconds
            let dispatches = runProductionSequence(
                kernels: abi == .old ? old : packed,
                abi: abi,
                fixtures: fixtures,
                stream: stream
            )
            stream.synchronize()
            let end = DispatchTime.now().uptimeNanoseconds
            guard dispatches == 5_110 else {
                throw BenchmarkError.invariant("sequence dispatched \(dispatches), expected 5110")
            }
            let after = thermalState()
            let seconds = Double(end - start) / 1_000_000_000
            let sample = TimingSample(
                block: block,
                order: half,
                position: position,
                abi: abi,
                seconds: seconds,
                thermalBefore: before,
                thermalAfter: after
            )
            samples.append(sample)
            print(String(
                format: "TIMING block=%d order=%@ position=%d abi=%@ seconds=%.9f thermal=%@->%@",
                block, half, position, abi.rawValue, seconds, before, after
            ))
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

private func mad(_ values: [Double]) -> Double {
    let center = median(values)
    return median(values.map { abs($0 - center) })
}

private func percentile(_ sorted: [Double], _ probability: Double) -> Double {
    let position = probability * Double(sorted.count - 1)
    let lower = Int(floor(position))
    let upper = Int(ceil(position))
    if lower == upper { return sorted[lower] }
    let weight = position - Double(lower)
    return sorted[lower] * (1 - weight) + sorted[upper] * weight
}

private func bootstrapCI(_ values: [Double], seed: UInt64) -> [Double] {
    var generator = LCG(state: seed)
    var estimates = [Double]()
    estimates.reserveCapacity(10_000)
    for _ in 0..<10_000 {
        var sample = [Double]()
        sample.reserveCapacity(values.count)
        for _ in values.indices {
            sample.append(values[generator.index(upperBound: values.count)])
        }
        estimates.append(median(sample))
    }
    estimates.sort()
    return [percentile(estimates, 0.025), percentile(estimates, 0.975)]
}

private func orderSummary(_ samples: [TimingSample], order: String, seed: UInt64) -> [String: Any] {
    let subset = samples.filter { $0.order == order }
    let blocks = Set(subset.map(\.block)).sorted()
    let paired = blocks.map { block -> Double in
        let current = subset.filter { $0.block == block }
        let old = current.filter { $0.abi == .old }.map(\.seconds)
        let packed = current.filter { $0.abi == .packed }.map(\.seconds)
        return median(old) / median(packed)
    }
    let old = subset.filter { $0.abi == .old }.map(\.seconds)
    let packed = subset.filter { $0.abi == .packed }.map(\.seconds)
    let interval = bootstrapCI(paired, seed: seed)
    return [
        "blocks": blocks.count,
        "oldMedianSeconds": median(old),
        "oldMADSeconds": mad(old),
        "packedMedianSeconds": median(packed),
        "packedMADSeconds": mad(packed),
        "pairedSpeedups": paired,
        "medianPairedSpeedup": median(paired),
        "pairedSpeedupMAD": mad(paired),
        "bootstrap95CI": interval,
        "bootstrapReplicates": 10_000,
    ]
}

private func layout(_ array: MLXArray) -> [String: Any] {
    let data = array.asData(access: .noCopy)
    return [
        "shape": data.shape,
        "strides": data.strides,
        "dtype": String(describing: data.dType),
    ]
}

private func emitJSON(_ object: [String: Any]) throws {
    let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    print("RESULT_JSON \(String(decoding: data, as: UTF8.self))")
}

private func run() throws {
    let options = try Options.parse()
    let runtimePath = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
    guard FileManager.default.fileExists(atPath: repoRoot.appendingPathComponent(runtimePath).path) else {
        throw BenchmarkError.invariant("run from research/qk-abi-bench")
    }
    let headSHA = try runCommand("/usr/bin/git", ["rev-parse", "HEAD"], at: repoRoot)
    let currentRuntimeBlob = try runCommand("/usr/bin/git", ["hash-object", runtimePath], at: repoRoot)
    let candidateRuntimeBlob = try runCommand(
        "/usr/bin/git", ["rev-parse", "\(candidateRuntimeSHA):\(runtimePath)"], at: repoRoot
    )
    guard currentRuntimeBlob == candidateRuntimeBlob else {
        throw BenchmarkError.invariant("current runtime differs from candidate commit")
    }
    let currentText = try String(contentsOf: repoRoot.appendingPathComponent(runtimePath), encoding: .utf8)
    let baselineText = try runCommand(
        "/usr/bin/git", ["show", "\(baselineSHA):\(runtimePath)"], at: repoRoot
    )
    let sourceAudit = try staticAudit(baseline: baselineText, candidate: currentText)
    let old = Kernels(sources: try loadSources(baselineText), abi: .old)
    let packed = Kernels(sources: try loadSources(currentText), abi: .packed)

    MLXRandom.seed(635)
    let stream = MLX.Stream.gpu
    progress("materialize resident 40-layer fixtures")
    let fixtures = makeFixtures()
    let first = fixtures.layers[0].weights
    progress("run Gate 1 exactness and corruption control")
    let correctness = try verifyCorrectness(old: old, packed: packed, fixtures: fixtures, stream: stream)

    progress("warm complete old and packed production sequences")
    guard runProductionSequence(kernels: old, abi: .old, fixtures: fixtures, stream: stream) == 5_110,
          runProductionSequence(kernels: packed, abi: .packed, fixtures: fixtures, stream: stream) == 5_110
    else {
        throw BenchmarkError.invariant("warm sequence census mismatch")
    }
    stream.synchronize()

    var samples = [TimingSample]()
    if !options.quick {
        progress("run Gate 2 balanced 32-block timing")
        samples = try timeSequences(
            blocks: options.blocks,
            old: old,
            packed: packed,
            fixtures: fixtures,
            stream: stream
        )
    }

    var result: [String: Any] = [
        "schemaVersion": 2,
        "baselineSHA": baselineSHA,
        "candidateRuntimeSHA": candidateRuntimeSHA,
        "candidateRuntimeBlob": candidateRuntimeBlob,
        "headSHA": headSHA,
        "quick": options.quick,
        "architecture": try runCommand("/usr/sbin/sysctl", ["-n", "machdep.cpu.brand_string"], at: repoRoot),
        "thermalEnd": thermalState(),
        "sourceAudit": sourceAudit,
        "bindings": [
            "oldInputCount": 10,
            "packedInputCount": 9,
            "removedBinding": "key_weight",
            "bankBinding": "qk_norm_weight",
            "kOffsetElements": headDim,
            "kOffsetBytes": headDim * 2,
        ],
        "bank": [
            "shape": [2 * headDim],
            "dtype": "bfloat16",
            "materializedBeforeTiming": true,
            "queryLayout": layout(first.query),
            "keyLayout": layout(first.key),
            "bankLayout": layout(first.bank),
        ],
        "productionCensusPerObservation": [
            "slidingLayers": 30,
            "fullLayers": 10,
            "slidingCalls": 30 * 128,
            "fullCalls": 10 * 127,
            "totalPackedSelections": 5_110,
            "prefillPackedSelections": 0,
            "slidingWriteIndices": [0, 127],
            "fullWriteIndices": [513, 639],
        ],
        "correctness": correctness.json,
        "rawTimings": samples.map(\.json),
        "wandb": "N/A: local Swift/Metal inference benchmark",
    ]

    if !options.quick {
        let baab = orderSummary(samples, order: "BAAB", seed: 635_001)
        let abba = orderSummary(samples, order: "ABBA", seed: 635_002)
        let oldMedian = median(samples.filter { $0.abi == .old }.map(\.seconds))
        let packedMedian = median(samples.filter { $0.abi == .packed }.map(\.seconds))
        let projectedCandidate = baseDecodeSequenceSeconds - (oldMedian - packedMedian)
        let amdahlSpeedup = baseDecodeSequenceSeconds / projectedCandidate
        let baabSpeedup = baab["medianPairedSpeedup"] as! Double
        let abbaSpeedup = abba["medianPairedSpeedup"] as! Double
        let baabLower = (baab["bootstrap95CI"] as! [Double])[0]
        let abbaLower = (abba["bootstrap95CI"] as! [Double])[0]
        let gatePass = baabSpeedup >= 1.010 && abbaSpeedup >= 1.010
            && baabLower > 1.0 && abbaLower > 1.0
            && amdahlSpeedup >= 1.0015
        result["timing"] = [
            "blocks": options.blocks,
            "observations": samples.count,
            "orderPerBlock": "BAAB then ABBA",
            "BAAB": baab,
            "ABBA": abba,
            "overallOldMedianSeconds": oldMedian,
            "overallPackedMedianSeconds": packedMedian,
            "overallMicroSpeedup": oldMedian / packedMedian,
            "baseFullDecodeSequenceSeconds": baseDecodeSequenceSeconds,
            "projectedCandidateDecodeSequenceSeconds": projectedCandidate,
            "amdahlProjectedDecodeSpeedup": amdahlSpeedup,
            "gate2Pass": gatePass,
        ]
    }
    try emitJSON(result)
}

do {
    try run()
} catch {
    fputs("QK ABI benchmark failed: \(error)\n", stderr)
    exit(1)
}
