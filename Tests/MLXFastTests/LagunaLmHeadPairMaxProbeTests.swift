import Foundation
import MLX
@testable import MLXFastModel
import Testing

private let pairProbeVocab = 100_352
private let pairProbeHidden = 2_048

private enum PairProbeError: Error {
    case invalidConfiguration(String)
    case missingInt5Planes
    case coolingFailed(Int32)
    case outputMismatch(String)
}

private enum PairProbeArm: Equatable {
    case control
    case candidate
}

private enum PairProbeOrder: String, Hashable {
    case ab = "AB"
    case ba = "BA"
}

private struct PairProbeContext {
    let lmHead: MLXArray
    let hidden: MLXArray
    let codesLo: MLXArray
    let codesHi: MLXArray
    let scales: MLXArray
}

private struct PairProbeOutput {
    let coarse: MLXArray
    let delta: MLXArray
    let pairMax: MLXArray?
    let threshold: MLXArray
    let assembled: MLXArray
}

private struct PairProbeSample {
    let order: PairProbeOrder
    let pair: Int
    let controlSeconds: Double
    let candidateSeconds: Double

    var speedup: Double { controlSeconds / candidateSeconds }
}

private struct PairProbeStats {
    let median: Double
    let mad: Double
}

private struct PairProbeFiltered {
    let values: [Double]
    let removedIndex: Int?
}

private func makePairProbeContext() throws -> PairProbeContext {
    let weightsPath = ProcessInfo.processInfo.environment["MLXFAST_WEIGHTS_PATH"] ?? "weights"
    let store = try DenseTensorStore(weightsPath: weightsPath)
    let tensor = try store.materializedTensor(named: LagunaWeightNames.lmHead)
    let lmHead = try MLXArrayTensorBridge().makeArray(from: tensor)
    guard let pruner = LagunaLmHeadPruner(lmHeadWeight: lmHead),
        let codesLo = pruner.int5CodesLo,
        let codesHi = pruner.int5CodesHi,
        let scales = pruner.int5Scales
    else {
        throw PairProbeError.missingInt5Planes
    }
    let hidden = MLXArray(
        (0..<pairProbeHidden).map { Float(Int($0 % 31) - 15) / 32 }
    ).asType(.bfloat16)
    eval([lmHead, hidden] + pruner.residentArrays)
    return PairProbeContext(
        lmHead: lmHead,
        hidden: hidden,
        codesLo: codesLo,
        codesHi: codesHi,
        scales: scales
    )
}

private func runPairProbeChain(
    _ arm: PairProbeArm,
    context: PairProbeContext
) -> PairProbeOutput {
    let candidate = arm == .candidate
    let producer = candidate
        ? LagunaLmHeadPairMaxProbeKernels.candidateProducer
        : LagunaLmHeadPairMaxProbeKernels.controlProducer
    let produced = producer(
        [context.hidden, context.codesLo, context.codesHi, context.scales],
        grid: (pairProbeVocab / 16 * 256, 1, 1),
        threadGroup: (256, 1, 1),
        outputShapes: candidate
            ? [[pairProbeVocab], [pairProbeVocab], [pairProbeVocab / 2]]
            : [[pairProbeVocab], [pairProbeVocab]],
        outputDTypes: candidate
            ? [.float32, .bfloat16, .float32]
            : [.float32, .bfloat16]
    )
    let threshold: MLXArray
    if candidate {
        threshold = LagunaLmHeadPairMaxProbeKernels.candidateThreshold(
            [produced[2], produced[0], context.lmHead, context.hidden],
            grid: (224, 1, 1),
            threadGroup: (224, 1, 1),
            outputShapes: [[1]],
            outputDTypes: [.float32]
        )[0]
    } else {
        let partials = LagunaLmHeadPairMaxProbeKernels.controlStage1(
            [produced[0]],
            grid: (224, 128, 1),
            threadGroup: (224, 1, 1),
            outputShapes: [[128], [128]],
            outputDTypes: [.float32, .uint32]
        )
        threshold = LagunaLmHeadPairMaxProbeKernels.controlThreshold(
            [partials[0], partials[1], context.lmHead, context.hidden],
            grid: (32, 1, 1),
            threadGroup: (32, 1, 1),
            outputShapes: [[1]],
            outputDTypes: [.float32]
        )[0]
    }
    let assembled = LagunaLmHeadPairMaxProbeKernels.assembly(
        [produced[0], produced[1], threshold, context.lmHead, context.hidden],
        grid: (pairProbeVocab / 32 * 256, 1, 1),
        threadGroup: (256, 1, 1),
        outputShapes: [[pairProbeVocab]],
        outputDTypes: [.bfloat16]
    )[0]
    return PairProbeOutput(
        coarse: produced[0],
        delta: produced[1],
        pairMax: candidate ? produced[2] : nil,
        threshold: threshold,
        assembled: assembled
    )
}

private func mismatchCount<T: Equatable>(_ lhs: [T], _ rhs: [T]) -> Int {
    guard lhs.count == rhs.count else { return max(lhs.count, rhs.count) }
    return zip(lhs, rhs).reduce(into: 0) { count, values in
        if values.0 != values.1 {
            count += 1
        }
    }
}

private func bf16Argmax(_ bits: [UInt16]) -> Int {
    var best = -Float.infinity
    var bestIndex = 0
    for (index, bitPattern) in bits.enumerated() {
        let value = Float(bitPattern: UInt32(bitPattern) << 16)
        if value > best {
            best = value
            bestIndex = index
        }
    }
    return bestIndex
}

private func verifyPairProbeOracle(
    context: PairProbeContext
) throws -> Data {
    let control = runPairProbeChain(.control, context: context)
    let candidate = runPairProbeChain(.candidate, context: context)
    guard let pairMax = candidate.pairMax else {
        throw PairProbeError.outputMismatch("missing pair maxima")
    }
    eval([
        control.coarse, control.delta, control.threshold, control.assembled,
        candidate.coarse, candidate.delta, pairMax, candidate.threshold,
        candidate.assembled,
    ])

    let controlCoarse = control.coarse.view(dtype: .uint32).asArray(UInt32.self)
    let candidateCoarse = candidate.coarse.view(dtype: .uint32).asArray(UInt32.self)
    let controlDelta = control.delta.view(dtype: .uint16).asArray(UInt16.self)
    let candidateDelta = candidate.delta.view(dtype: .uint16).asArray(UInt16.self)
    let candidatePairs = pairMax.view(dtype: .uint32).asArray(UInt32.self)
    let controlThreshold = control.threshold.view(dtype: .uint32).asArray(UInt32.self)
    let candidateThreshold = candidate.threshold.view(dtype: .uint32).asArray(UInt32.self)
    let controlLogits = control.assembled.view(dtype: .uint16).asArray(UInt16.self)
    let candidateLogits = candidate.assembled.view(dtype: .uint16).asArray(UInt16.self)

    var expectedPairs = [UInt32]()
    expectedPairs.reserveCapacity(pairProbeVocab / 2)
    for row0 in stride(from: 0, to: pairProbeVocab, by: 2) {
        let first = Float(bitPattern: controlCoarse[row0])
        let second = Float(bitPattern: controlCoarse[row0 + 1])
        expectedPairs.append(second > first ? controlCoarse[row0 + 1] : controlCoarse[row0])
    }

    let coarseMismatch = mismatchCount(controlCoarse, candidateCoarse)
    let deltaMismatch = mismatchCount(controlDelta, candidateDelta)
    let pairMismatch = mismatchCount(expectedPairs, candidatePairs)
    let thresholdMismatch = mismatchCount(controlThreshold, candidateThreshold)
    let logitsMismatch = mismatchCount(controlLogits, candidateLogits)
    let tokenMismatch = bf16Argmax(controlLogits) == bf16Argmax(candidateLogits) ? 0 : 1
    var corruptedPairs = candidatePairs
    corruptedPairs[0] ^= 1
    let corruptionDetected = mismatchCount(expectedPairs, corruptedPairs) > 0
    print(
        "lmhead_pair_probe_oracle coarse=\(coarseMismatch) delta=\(deltaMismatch) "
            + "pair=\(pairMismatch) selected_row=0_from_prior_real_sequence_oracle "
            + "threshold=\(thresholdMismatch) logits=\(logitsMismatch) "
            + "token=\(tokenMismatch) corruption_detected=\(corruptionDetected)"
    )
    guard coarseMismatch == 0, deltaMismatch == 0, pairMismatch == 0,
        thresholdMismatch == 0, logitsMismatch == 0, tokenMismatch == 0,
        corruptionDetected
    else {
        throw PairProbeError.outputMismatch("oracle mismatch")
    }
    return control.assembled.asData(access: .copy).data
}

private func runPairProbeCoolGate(_ phase: String) throws {
    let environment = ProcessInfo.processInfo.environment
    guard environment["MLXFAST_LOCAL_COOL_GATE_STRICT_TELEMETRY"] == "1",
        let helper = environment["MLXFAST_LOCAL_COOL_GATE_HELPER"],
        !helper.isEmpty,
        FileManager.default.isExecutableFile(atPath: helper)
    else {
        throw PairProbeError.invalidConfiguration("strict cooling helper required")
    }
    let process = Process()
    process.executableURL = URL(fileURLWithPath: helper)
    process.arguments = ["--local-cool-gate-only"]
    var childEnvironment = environment
    childEnvironment["MLXFAST_LOCAL_COOL_GATE_PHASE"] = phase
    process.environment = childEnvironment
    try process.run()
    process.waitUntilExit()
    guard process.terminationReason == .exit, process.terminationStatus == 0 else {
        throw PairProbeError.coolingFailed(process.terminationStatus)
    }
}

private func measurePairProbeArm(
    _ arm: PairProbeArm,
    context: PairProbeContext,
    iterations: Int,
    expectedLogits: Data
) throws -> Double {
    try autoreleasepool {
        var outputs = [MLXArray]()
        outputs.reserveCapacity(iterations)
        for _ in 0..<iterations {
            outputs.append(runPairProbeChain(arm, context: context).assembled)
        }
        Stream.gpu.synchronize()
        let start = DispatchTime.now().uptimeNanoseconds
        eval(outputs)
        Stream.gpu.synchronize()
        let elapsed = DispatchTime.now().uptimeNanoseconds - start
        guard outputs.last?.asData(access: .copy).data == expectedLogits else {
            throw PairProbeError.outputMismatch("post-timing arm mismatch")
        }
        return Double(elapsed) / 1_000_000_000
    }
}

private func median(_ sorted: [Double]) -> Double {
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}

private func pairProbeStats(_ values: [Double]) -> PairProbeStats {
    let center = median(values.sorted())
    let deviations = values.map { abs($0 - center) }.sorted()
    return PairProbeStats(median: center, mad: median(deviations))
}

private func geometricMean(_ values: [Double]) -> Double {
    Foundation.exp(values.map { Foundation.log($0) }.reduce(0, +) / Double(values.count))
}

private func madFiltered(_ values: [Double]) -> PairProbeFiltered {
    let stats = pairProbeStats(values)
    guard stats.mad > 0 else {
        return PairProbeFiltered(values: values, removedIndex: nil)
    }
    let deviations = values.map { abs($0 - stats.median) }
    guard let index = deviations.indices.max(by: { deviations[$0] < deviations[$1] }),
        deviations[index] > 3 * stats.mad
    else {
        return PairProbeFiltered(values: values, removedIndex: nil)
    }
    var filtered = values
    filtered.remove(at: index)
    return PairProbeFiltered(values: filtered, removedIndex: index)
}

@Test
func lagunaLmHeadPairMaxIsolatedTimingProbe() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_LMHEAD_PAIR_MAX_PROBE"] == "1" else {
        return
    }
    guard ProcessInfo.processInfo.environment["DARKBLOOM_LMHEAD_PAIR_MAX"] != "0" else {
        throw PairProbeError.invalidConfiguration("candidate must be the default producer")
    }

    let context = try makePairProbeContext()
    let expectedLogits = try verifyPairProbeOracle(context: context)
    let iterations = 128
    print(
        "lmhead_pair_probe_contract iterations_per_sample=\(iterations) cooled_pairs=14 "
            + "orders=7_AB_7_BA outlier_rule=max_one_per_arm_if_abs_deviation_gt_3_MAD"
    )

    for _ in 0..<2 {
        _ = try measurePairProbeArm(
            .control, context: context, iterations: 16, expectedLogits: expectedLogits)
        _ = try measurePairProbeArm(
            .candidate, context: context, iterations: 16, expectedLogits: expectedLogits)
    }

    var samples = [PairProbeSample]()
    samples.reserveCapacity(14)
    var orderCounts: [PairProbeOrder: Int] = [.ab: 0, .ba: 0]
    for pairIndex in 0..<14 {
        let order: PairProbeOrder = pairIndex.isMultiple(of: 2) ? .ab : .ba
        let orderPair = orderCounts[order, default: 0]
        try runPairProbeCoolGate("lmhead-pair-max-\(order.rawValue)-\(orderPair)")
        let firstArm: PairProbeArm = order == .ab ? .control : .candidate
        let secondArm: PairProbeArm = order == .ab ? .candidate : .control
        let first = try measurePairProbeArm(
            firstArm, context: context, iterations: iterations, expectedLogits: expectedLogits)
        let second = try measurePairProbeArm(
            secondArm, context: context, iterations: iterations, expectedLogits: expectedLogits)
        let control = order == .ab ? first : second
        let candidate = order == .ab ? second : first
        let sample = PairProbeSample(
            order: order,
            pair: orderPair,
            controlSeconds: control,
            candidateSeconds: candidate
        )
        samples.append(sample)
        orderCounts[order, default: 0] += 1
        print(
            "lmhead_pair_probe_sample order=\(order.rawValue) pair=\(orderPair) "
                + "control_seconds=\(control) candidate_seconds=\(candidate) "
                + "speedup=\(sample.speedup) exact_control=true exact_candidate=true"
        )
    }

    func reportOrder(_ order: PairProbeOrder) -> Double {
        let ordered = samples.filter { $0.order == order }
        let control = ordered.map(\.controlSeconds)
        let candidate = ordered.map(\.candidateSeconds)
        let controlStats = pairProbeStats(control)
        let candidateStats = pairProbeStats(candidate)
        let speedup = controlStats.median / candidateStats.median
        print(
            "lmhead_pair_probe_order order=\(order.rawValue) "
                + "control_median=\(controlStats.median) control_mad=\(controlStats.mad) "
                + "candidate_median=\(candidateStats.median) candidate_mad=\(candidateStats.mad) "
                + "median_speedup=\(speedup)"
        )
        return speedup
    }

    let abSpeedup = reportOrder(.ab)
    let baSpeedup = reportOrder(.ba)
    let pooledGeometric = geometricMean(samples.map(\.speedup))
    let controlFiltered = madFiltered(samples.map(\.controlSeconds))
    let candidateFiltered = madFiltered(samples.map(\.candidateSeconds))
    let robustSpeedup =
        geometricMean(controlFiltered.values) / geometricMean(candidateFiltered.values)
    let passed = abSpeedup >= 1.005 && baSpeedup >= 1.005
        && robustSpeedup >= 1.005 && abSpeedup > 1 && baSpeedup > 1
    print(
        "lmhead_pair_probe_result ab_median_speedup=\(abSpeedup) "
            + "ba_median_speedup=\(baSpeedup) pooled_geometric_speedup=\(pooledGeometric) "
            + "robust_speedup=\(robustSpeedup) "
            + "control_removed=\(String(describing: controlFiltered.removedIndex)) "
            + "candidate_removed=\(String(describing: candidateFiltered.removedIndex)) "
            + "gate_passed=\(passed)"
    )
    #expect(passed)
}
