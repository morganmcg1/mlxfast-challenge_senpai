import Foundation
import MLX
@testable import MLXFastModel
import Testing

private let probeVocab = 100_352
private let probeHidden = 2_048

private enum LmHeadProbeError: Error {
    case missingInt5Planes
}

private struct LmHeadProbeContext {
    let lmHead: MLXArray
    let hidden: MLXArray
    let codesLo: MLXArray
    let codesHi: MLXArray
    let scales: MLXArray
}

private struct LmHeadProbeOutput {
    let coarse: MLXArray
    let delta: MLXArray
    let partialMax: MLXArray
    let partialIndex: MLXArray
    let threshold: MLXArray
    let assembled: MLXArray
}

private struct LmHeadProbeWinner: Equatable {
    let value: Float
    let index: UInt32
}

private func makeLmHeadProbeContext() throws -> LmHeadProbeContext {
    let weightsPath = ProcessInfo.processInfo.environment["MLXFAST_WEIGHTS_PATH"]
        ?? "weights"
    let store = try DenseTensorStore(weightsPath: weightsPath)
    let tensor = try store.materializedTensor(named: LagunaWeightNames.lmHead)
    let lmHead = try MLXArrayTensorBridge().makeArray(from: tensor)
    guard let pruner = LagunaLmHeadPruner(lmHeadWeight: lmHead),
        let codesLo = pruner.int5CodesLo,
        let codesHi = pruner.int5CodesHi,
        let scales = pruner.int5Scales
    else {
        throw LmHeadProbeError.missingInt5Planes
    }
    let axis = MLXArray(0..<probeHidden).asType(.float32)
    let hidden = (
        sin(axis * Float(0.013)) * Float(0.75)
            + cos(axis * Float(0.007)) * Float(0.25)
    ).asType(.bfloat16)
    eval([lmHead, hidden] + pruner.residentArrays)
    return LmHeadProbeContext(
        lmHead: lmHead,
        hidden: hidden,
        codesLo: codesLo,
        codesHi: codesHi,
        scales: scales
    )
}

private func runLmHeadProbeChain(
    fused: Bool,
    context: LmHeadProbeContext
) -> LmHeadProbeOutput {
    let producer = fused
        ? LagunaLmHeadArgmaxFusionProbeKernels.candidateProducer
        : LagunaLmHeadArgmaxFusionProbeKernels.controlProducer
    let producerOutput = producer(
        [context.hidden, context.codesLo, context.codesHi, context.scales],
        grid: (probeVocab / 16 * 256, 1, 1),
        threadGroup: (256, 1, 1),
        outputShapes: fused
            ? [[probeVocab], [probeVocab], [probeVocab / 16], [probeVocab / 16]]
            : [[probeVocab], [probeVocab]],
        outputDTypes: fused
            ? [.float32, .bfloat16, .float32, .uint32]
            : [.float32, .bfloat16]
    )
    let partials: [MLXArray]
    if fused {
        partials = [producerOutput[2], producerOutput[3]]
    } else {
        partials = LagunaLmHeadArgmaxFusionProbeKernels.controlStage1(
            [producerOutput[0]],
            grid: (224, 128, 1),
            threadGroup: (224, 1, 1),
            outputShapes: [[128], [128]],
            outputDTypes: [.float32, .uint32]
        )
    }
    let thresholdThreads = fused ? 256 : 32
    let thresholdKernel = fused
        ? LagunaLmHeadArgmaxFusionProbeKernels.candidateThreshold
        : LagunaLmHeadArgmaxFusionProbeKernels.controlThreshold
    let threshold = thresholdKernel(
        [partials[0], partials[1], context.lmHead, context.hidden],
        grid: (thresholdThreads, 1, 1),
        threadGroup: (thresholdThreads, 1, 1),
        outputShapes: [[1]],
        outputDTypes: [.float32]
    )[0]
    let assembled = LagunaLmHeadArgmaxFusionProbeKernels.assembly(
        [producerOutput[0], producerOutput[1], threshold, context.lmHead, context.hidden],
        grid: (probeVocab / 32 * 256, 1, 1),
        threadGroup: (256, 1, 1),
        outputShapes: [[probeVocab]],
        outputDTypes: [.bfloat16]
    )[0]
    return LmHeadProbeOutput(
        coarse: producerOutput[0],
        delta: producerOutput[1],
        partialMax: partials[0],
        partialIndex: partials[1],
        threshold: threshold,
        assembled: assembled
    )
}

private func probeWinner(
    values: [Float],
    indices: [UInt32]
) -> LmHeadProbeWinner {
    var best = -Float.infinity
    var bestIndex = UInt32.max
    for offset in values.indices {
        let value = values[offset]
        let index = indices[offset]
        if value > best || (value == best && index < bestIndex) {
            best = value
            bestIndex = index
        }
    }
    return LmHeadProbeWinner(value: best, index: bestIndex)
}

private func probeWinner(
    coarse: [Float],
    range: Range<Int>
) -> LmHeadProbeWinner {
    var best = -Float.infinity
    var bestIndex = UInt32.max
    for offset in range {
        let value = coarse[offset]
        let index = UInt32(offset)
        if value > best || (value == best && index < bestIndex) {
            best = value
            bestIndex = index
        }
    }
    return LmHeadProbeWinner(value: best, index: bestIndex)
}

private func corrupted(_ data: Data) -> Data {
    var result = data
    result[result.startIndex] ^= 1
    return result
}

@Test
func lmHeadCoarseArgmaxFusionBitwiseOracle() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_LMHEAD_PROBE_MODE"] == "oracle"
    else {
        return
    }
    let context = try makeLmHeadProbeContext()
    let control = runLmHeadProbeChain(fused: false, context: context)
    let candidate = runLmHeadProbeChain(fused: true, context: context)
    eval([
        control.coarse, control.delta, control.partialMax, control.partialIndex,
        control.threshold, control.assembled, candidate.coarse, candidate.delta,
        candidate.partialMax, candidate.partialIndex, candidate.threshold,
        candidate.assembled,
    ])

    let controlCoarseData = control.coarse.asData(access: .copy).data
    let candidateCoarseData = candidate.coarse.asData(access: .copy).data
    let controlDeltaData = control.delta.asData(access: .copy).data
    let candidateDeltaData = candidate.delta.asData(access: .copy).data
    let controlThresholdData = control.threshold.asData(access: .copy).data
    let candidateThresholdData = candidate.threshold.asData(access: .copy).data
    let controlAssembledData = control.assembled.asData(access: .copy).data
    let candidateAssembledData = candidate.assembled.asData(access: .copy).data
    #expect(controlCoarseData == candidateCoarseData)
    #expect(controlDeltaData == candidateDeltaData)
    #expect(controlThresholdData == candidateThresholdData)
    #expect(controlAssembledData == candidateAssembledData)

    let coarse = control.coarse.asArray(Float.self)
    let fullWinner = probeWinner(coarse: coarse, range: 0..<probeVocab)
    let controlValues = control.partialMax.asArray(Float.self)
    let controlIndices = control.partialIndex.asArray(UInt32.self)
    let candidateValues = candidate.partialMax.asArray(Float.self)
    let candidateIndices = candidate.partialIndex.asArray(UInt32.self)
    let controlWinner = probeWinner(values: controlValues, indices: controlIndices)
    let candidateWinner = probeWinner(values: candidateValues, indices: candidateIndices)
    #expect(controlWinner == fullWinner)
    #expect(candidateWinner == fullWinner)

    for partition in controlValues.indices {
        let expected = probeWinner(
            coarse: coarse,
            range: partition * 784..<(partition + 1) * 784
        )
        #expect(controlValues[partition].bitPattern == expected.value.bitPattern)
        #expect(controlIndices[partition] == expected.index)
    }
    for partition in candidateValues.indices {
        let expected = probeWinner(
            coarse: coarse,
            range: partition * 16..<(partition + 1) * 16
        )
        #expect(candidateValues[partition].bitPattern == expected.value.bitPattern)
        #expect(candidateIndices[partition] == expected.index)
    }

    var corruptedValues = candidateValues
    var corruptedIndices = candidateIndices
    let otherPartition = try #require(
        candidateIndices.firstIndex(where: { $0 != fullWinner.index })
    )
    corruptedValues[otherPartition] = Float.greatestFiniteMagnitude
    corruptedIndices[otherPartition] = fullWinner.index == 0 ? 1 : 0
    #expect(
        probeWinner(values: corruptedValues, indices: corruptedIndices)
            != fullWinner
    )

    corruptedValues = candidateValues
    corruptedIndices = candidateIndices
    let winnerPartition = try #require(
        candidateIndices.firstIndex(where: { $0 == fullWinner.index })
    )
    corruptedIndices[winnerPartition] = fullWinner.index == 0 ? 1 : 0
    #expect(
        probeWinner(values: corruptedValues, indices: corruptedIndices)
            != fullWinner
    )
    #expect(corrupted(candidateThresholdData) != controlThresholdData)
    #expect(corrupted(candidateAssembledData) != controlAssembledData)

    print(
        "lmhead_argmax_gate1 coarse_bitwise=true delta_bitwise=true "
            + "winner_index=\(fullWinner.index) threshold_bitwise=true "
            + "assembled_bitwise=true corruption_controls=true "
            + "control_dispatches=4 candidate_dispatches=3"
    )
}

private func executeLmHeadProbeChain(
    fused: Bool,
    context: LmHeadProbeContext
) {
    autoreleasepool {
        let output = runLmHeadProbeChain(fused: fused, context: context)
        eval(output.assembled)
    }
}

private func measureLmHeadProbeChain(
    fused: Bool,
    context: LmHeadProbeContext,
    iterations: Int
) -> Double {
    Stream.gpu.synchronize()
    let start = DispatchTime.now().uptimeNanoseconds
    for _ in 0..<iterations {
        executeLmHeadProbeChain(fused: fused, context: context)
    }
    Stream.gpu.synchronize()
    return Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000_000_000
}

@Test
func lmHeadCoarseArgmaxFusionSameBinaryTiming() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_LMHEAD_PROBE_MODE"] == "timing"
    else {
        return
    }
    let context = try makeLmHeadProbeContext()
    for _ in 0..<8 {
        executeLmHeadProbeChain(fused: false, context: context)
        executeLmHeadProbeChain(fused: true, context: context)
    }

    let iterations = 128
    let controlAB = measureLmHeadProbeChain(
        fused: false, context: context, iterations: iterations)
    let candidateAB = measureLmHeadProbeChain(
        fused: true, context: context, iterations: iterations)
    let candidateBA = measureLmHeadProbeChain(
        fused: true, context: context, iterations: iterations)
    let controlBA = measureLmHeadProbeChain(
        fused: false, context: context, iterations: iterations)
    let speedupAB = controlAB / candidateAB
    let speedupBA = controlBA / candidateBA
    print(
        "lmhead_argmax_gate3 iterations=\(iterations) "
            + "control_ab_seconds=\(controlAB) candidate_ab_seconds=\(candidateAB) "
            + "speedup_ab=\(speedupAB) candidate_ba_seconds=\(candidateBA) "
            + "control_ba_seconds=\(controlBA) speedup_ba=\(speedupBA)"
    )
    #expect(speedupAB >= 1.005)
    #expect(speedupBA >= 1.005)
}
