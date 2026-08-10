import Dispatch
import Foundation
import MLX
import MLXLMCommon
import MLXNN
import Testing

@testable import MLXFastModel

@Test
func nvfp4Group16SplitKMatmulMatchesDequantizedReferenceWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    // M=32, N=128, K=64 enters qmm_splitk. With group size 16 the old
    // dispatch selected four K=16 partitions even though the Metal kernel
    // consumes K in 32-wide tiles, over-reading every partition.
    let input = MLXArray(Array(repeating: Float(1), count: 32 * 64), [32, 64])
    let weight = MLXArray(Array(repeating: Float(1), count: 128 * 64), [128, 64])
    let (packedWeight, scales, biases) = quantized(
        weight,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4
    )

    let actual = quantizedMM(
        input,
        packedWeight,
        scales: scales,
        biases: biases,
        transpose: true,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4
    )
    let referenceWeight = dequantized(
        packedWeight,
        scales: scales,
        biases: biases,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4,
        dtype: .float32
    )
    let reference = matmul(input, referenceWeight.T)
    eval(actual, reference)

    let actualValues = actual.asArray(Float.self)
    let referenceValues = reference.asArray(Float.self)
    #expect(actualValues.allSatisfy { $0.isFinite })
    #expect(referenceValues.allSatisfy { $0.isFinite })
    let maximumError = zip(actualValues, referenceValues)
        .map { abs($0 - $1) }
        .max() ?? .infinity
    #expect(maximumError <= 1e-4)
}

@Test
func nvfp4NibbleOrderAndE4M3ScaleBytesMatchMLXContractWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    // U32 packs eight FP4 values least-significant nibble first. E2M1 codes
    // 0...7 decode as 0, .5, 1, 1.5, 2, 3, 4, 6 and bit 3 is the sign.
    // E4M3 scale bytes 0x38 and 0x40 decode as 1 and 2 respectively.
    let packed = MLXArray(
        [
            UInt32(0x7654_3210), UInt32(0xfedc_ba98),
            UInt32(0x7654_3210), UInt32(0xfedc_ba98),
        ],
        [2, 2]
    )
    let scales = MLXArray([UInt8(0x38), UInt8(0x40)], [2, 1])
    let unpacked = dequantized(
        packed,
        scales: scales,
        biases: nil,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4,
        dtype: .float32
    )
    eval(unpacked)

    let base: [Float] = [
        0, 0.5, 1, 1.5, 2, 3, 4, 6,
        -0, -0.5, -1, -1.5, -2, -3, -4, -6,
    ]
    #expect(unpacked.shape == [2, 16])
    #expect(unpacked.asArray(Float.self) == base + base.map { $0 * 2 })
}

@Test
func nvfp4ActualSharedExpertQMMShapesCoverDecodeAndSplitKPrefillWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    // gate/up: [512, 2048] logical, down: [2048, 512] logical.
    for (label, outputFeatures, inputFeatures) in [
        ("shared-gate-up", 512, 2_048),
        ("shared-down", 2_048, 512),
    ] {
        let weight = MLXArray.full(
            [outputFeatures, inputFeatures],
            values: MLXArray(Float(0.5)),
            dtype: .float32
        )
        let (packedWeight, scales, biases) = quantized(
            weight,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4
        )
        let referenceWeight = dequantized(
            packedWeight,
            scales: scales,
            biases: biases,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4,
            dtype: .float32
        )

        for tokenRows in [1, 32] {
            let input = MLXArray.full(
                [tokenRows, inputFeatures],
                values: MLXArray(Float(1)),
                dtype: .float32
            )
            let actual = quantizedMM(
                input,
                packedWeight,
                scales: scales,
                biases: biases,
                transpose: true,
                groupSize: 16,
                bits: 4,
                mode: .nvfp4
            )
            let reference = matmul(input, referenceWeight.T)
            expectFiniteClose(
                actual,
                reference,
                tolerance: 1e-4,
                label: "\(label)-M\(tokenRows)"
            )
        }
    }
}

@Test
func nvfp4ActualRoutedGatherShapesCoverMultipleExpertsAndPrefillWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    // gate/up logical [256, 512, 2048], down logical [256, 2048, 512].
    for (label, outputFeatures, inputFeatures) in [
        ("routed-gate-up", 512, 2_048),
        ("routed-down", 2_048, 512),
    ] {
        verifyActualRoutedGather(
            label: label,
            outputFeatures: outputFeatures,
            inputFeatures: inputFeatures,
            tokenCounts: [1, 8]
        )
    }
}

@Test
func quantizedSwitchLinearForwardsNVFP4GatherSemanticsWhenRuntimeTestsAreEnabled() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let dense = SwitchLinear(
        inputDims: 64,
        outputDims: 32,
        numExperts: 4,
        bias: false
    )
    let layer = QuantizedSwitchLinear(
        dense,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4
    )
    let input = MLXArray.full(
        [1, 2, 64],
        values: MLXArray(Float(0.25)),
        dtype: .float32
    )
    let expandedInput = expandedDimensions(input, axes: [-2, -3])
    let indices = MLXArray([Int32(0), 3, 2, 1], [1, 2, 2])
    let actual = layer(expandedInput, indices)

    let parameters = Dictionary(uniqueKeysWithValues: layer.parameters().flattened())
    let packedWeight = try #require(parameters["weight"])
    let scales = try #require(parameters["scales"])
    let referenceWeight = dequantized(
        packedWeight,
        scales: scales,
        biases: parameters["biases"],
        groupSize: 16,
        bits: 4,
        mode: .nvfp4,
        dtype: .float32
    )
    let reference = gatherMM(
        expandedInput,
        referenceWeight.swappedAxes(-1, -2),
        rhsIndices: indices
    )
    expectFiniteClose(
        actual,
        reference,
        tolerance: 1e-4,
        label: "QuantizedSwitchLinear"
    )
}

private func verifyActualRoutedGather(
    label: String,
    outputFeatures: Int,
    inputFeatures: Int,
    tokenCounts: [Int]
) {
    let expertCount = 256
    let topK = 8
    let packedWidth = inputFeatures * 4 / 32
    let scaleWidth = inputFeatures / 16

    // Give every expert a distinct constant E2M1 code. Broadcasting then
    // materializing this compact seed avoids a giant Swift-side payload while
    // still proving rhs expert indexing, including expert 255.
    let expertPackedCodes = (0..<expertCount).map { expert -> UInt32 in
        UInt32((expert % 7) + 1) &* UInt32(0x1111_1111)
    }
    let packedSeed = MLXArray(expertPackedCodes, [expertCount, 1, 1])
    let packedWeight = contiguous(
        broadcast(
            packedSeed,
            to: [expertCount, outputFeatures, packedWidth]
        )
    )
    let scales = MLXArray.full(
        [expertCount, outputFeatures, scaleWidth],
        values: MLXArray(UInt8(0x38)),
        dtype: .uint8
    )
    let selectedExpertIDs: [Int32] = [0, 7, 42, 255, 3, 128, 17, 99]
    let uniqueIDs = MLXArray(selectedExpertIDs)
    let selectedPacked = take(packedWeight, uniqueIDs, axis: 0)
    let selectedScales = take(scales, uniqueIDs, axis: 0)
    let selectedReferenceWeight = dequantized(
        selectedPacked,
        scales: selectedScales,
        biases: nil,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4,
        dtype: .float32
    )

    for tokenCount in tokenCounts {
        let input = MLXArray.full(
            [1, tokenCount, inputFeatures],
            values: MLXArray(Float(0.25)),
            dtype: .float32
        )
        let expandedInput = expandedDimensions(input, axes: [-2, -3])
        let flattenedIDs = (0..<tokenCount).flatMap { _ in selectedExpertIDs }
        let rhsIndices = MLXArray(flattenedIDs, [1, tokenCount, topK])
        let actual = gatherQuantizedMM(
            expandedInput,
            packedWeight,
            scales: scales,
            biases: nil,
            rhsIndices: rhsIndices,
            transpose: true,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4
        )
        let localIDs = MLXArray(
            (0..<tokenCount).flatMap { _ in (0..<topK).map(Int32.init) },
            [1, tokenCount, topK]
        )
        let reference = gatherMM(
            expandedInput,
            selectedReferenceWeight.swappedAxes(-1, -2),
            rhsIndices: localIDs
        )
        expectFiniteClose(
            actual,
            reference,
            tolerance: 1e-4,
            label: "\(label)-tokens\(tokenCount)"
        )
    }
}

private func expectFiniteClose(
    _ actual: MLXArray,
    _ reference: MLXArray,
    tolerance: Float,
    label: String
) {
    eval(actual, reference)
    let actualValues = actual.asArray(Float.self)
    let referenceValues = reference.asArray(Float.self)
    #expect(actual.shape == reference.shape, Comment(rawValue: label))
    #expect(
        actualValues.allSatisfy { $0.isFinite },
        Comment(rawValue: "\(label) produced non-finite NVFP4 output")
    )
    #expect(
        referenceValues.allSatisfy { $0.isFinite },
        Comment(rawValue: "\(label) produced non-finite reference output")
    )
    let maximumError = zip(actualValues, referenceValues)
        .map { abs($0 - $1) }
        .max() ?? .infinity
    #expect(
        maximumError <= tolerance,
        Comment(rawValue: "\(label) max error \(maximumError) > \(tolerance)")
    )
}


@Test
func fullAttentionInvocationParameterCarrierProbeWhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_FULL_PARAMS_CARRIER_PROBE"] == "1"
    else { return }

    let inputs = FullAttentionProbeInputs()
    for offset in [512, 513, 767] {
        verifyFullAttentionPair(inputs: inputs, offset: offset, capacity: 768)
    }
    verifyFullAttentionGrowthBoundary()
    verifyFullAttentionCarrierFallback()
    verifyFullAttentionCarrierCounts()
    runFullAttentionCarrierTiming(inputs: inputs)
}

private struct FullAttentionProbeInputs {
    let rawQueries = MLXArray.full(
        [1, 1, 48 * 128], values: MLXArray(Float(0.125)), dtype: .bfloat16)
    let rawKeys = MLXArray.full(
        [1, 1, 8 * 128], values: MLXArray(Float(0.0625)), dtype: .bfloat16)
    let rawValues = MLXArray.full(
        [1, 1, 8 * 128], values: MLXArray(Float(0.25)), dtype: .bfloat16)
    let queryWeight = MLXArray.ones([128], dtype: .bfloat16)
    let keyWeight = MLXArray.ones([128], dtype: .bfloat16)
    let angles = MLXArray.zeros([1, 1, 1, 64], dtype: .float32)
    let scale = MLXArray([pow(Float(128), -0.5)])

    var residentArrays: [MLXArray] {
        [rawQueries, rawKeys, rawValues, queryWeight, keyWeight, angles, scale]
    }

    func call(
        cacheKeys: MLXArray,
        cacheValues: MLXArray,
        writeIdx: Int,
        params: MLXArray
    ) -> MLXArray {
        lagunaFullFusedAttention(
            rawQueries: rawQueries,
            rawKeys: rawKeys,
            rawValues: rawValues,
            queryWeight: queryWeight,
            keyWeight: keyWeight,
            angles: angles,
            cacheKeys: cacheKeys,
            cacheValues: cacheValues,
            writeIdx: writeIdx,
            params: params,
            scale: scale
        )
    }
}

private struct FullAttentionResidentLayer {
    let keys: MLXArray
    let values: MLXArray
}

private enum FullAttentionProbeArm: Equatable {
    case baseline
    case candidate
}

private func makeFullAttentionCache(capacity: Int, offset: Int) -> KVCacheSimple {
    let cache = KVCacheSimple()
    cache.state = [
        MLXArray.full(
            [1, 8, capacity, 128],
            values: MLXArray(Float(0.03125)),
            dtype: .bfloat16),
        MLXArray.full(
            [1, 8, capacity, 128],
            values: MLXArray(Float(0.015625)),
            dtype: .bfloat16),
    ]
    #expect(cache.trim(capacity - offset) == capacity - offset)
    #expect(cache.offset == offset)
    return cache
}

private func rawBF16(_ value: MLXArray) -> [UInt16] {
    value.view(dtype: .uint16).asArray(UInt16.self)
}

private func verifyFullAttentionPair(
    inputs: FullAttentionProbeInputs,
    offset: Int,
    capacity: Int
) {
    let baselineCache = makeFullAttentionCache(capacity: capacity, offset: offset)
    let candidateCache = makeFullAttentionCache(capacity: capacity, offset: offset)
    let baselinePrepared = baselineCache.fusedAppendPrepare()
    let candidatePrepared = candidateCache.fusedAppendPrepare()
    #expect(baselinePrepared.map { _ in true } ?? false)
    #expect(candidatePrepared.map { _ in true } ?? false)

    let baselineAppend = baselinePrepared!
    let candidateAppend = candidatePrepared!
    let baselineParams = MLXArray([
        UInt32(offset), UInt32(offset + 1), UInt32(capacity),
    ])
    var carrier: LagunaFullAttentionParamsCarrier?
    _ = lagunaFullAttentionParams(
        writeIdx: offset, capacity: capacity, carrier: &carrier)
    let candidateParams = lagunaFullAttentionParams(
        writeIdx: offset, capacity: capacity, carrier: &carrier)
    #expect(baselineParams.dtype == .uint32)
    #expect(candidateParams.dtype == .uint32)
    #expect(baselineParams.asArray(UInt32.self) == [offset, offset + 1, capacity].map(UInt32.init))
    #expect(candidateParams.asArray(UInt32.self) == [offset, offset + 1, capacity].map(UInt32.init))
    #expect(carrier?.writeIdx == offset)
    #expect(carrier?.capacity == capacity)

    let baselineOutput = inputs.call(
        cacheKeys: baselineAppend.keys,
        cacheValues: baselineAppend.values,
        writeIdx: baselineAppend.writeIdx,
        params: baselineParams)
    let candidateOutput = inputs.call(
        cacheKeys: candidateAppend.keys,
        cacheValues: candidateAppend.values,
        writeIdx: candidateAppend.writeIdx,
        params: candidateParams)
    eval(
        [baselineOutput, candidateOutput]
            + baselineCache.innerState()
            + candidateCache.innerState())
    Stream.gpu.synchronize()

    #expect(rawBF16(baselineOutput) == rawBF16(candidateOutput))
    let baselineState = baselineCache.innerState()
    let candidateState = candidateCache.innerState()
    #expect(baselineState.count == 2)
    #expect(candidateState.count == 2)
    #expect(rawBF16(baselineState[0]) == rawBF16(candidateState[0]))
    #expect(rawBF16(baselineState[1]) == rawBF16(candidateState[1]))

    baselineCache.fusedAppendAdvance()
    candidateCache.fusedAppendAdvance()
    #expect(baselineCache.offset == offset + 1)
    #expect(candidateCache.offset == offset + 1)
    print("FULL_PARAMS_EXACT offset=\(offset) capacity=\(capacity) words=\(candidateParams.asArray(UInt32.self)) output_bits=match cache_bits=match advanced=\(candidateCache.offset)")
}

private func verifyFullAttentionGrowthBoundary() {
    let baseline = makeFullAttentionCache(capacity: 768, offset: 768)
    let candidate = makeFullAttentionCache(capacity: 768, offset: 768)
    #expect(baseline.fusedAppendPrepare().map { _ in false } ?? true)
    #expect(candidate.fusedAppendPrepare().map { _ in false } ?? true)

    let keys = MLXArray.full(
        [1, 8, 1, 128], values: MLXArray(Float(0.0625)), dtype: .bfloat16)
    let values = MLXArray.full(
        [1, 8, 1, 128], values: MLXArray(Float(0.125)), dtype: .bfloat16)
    let baselineUpdated = baseline.update(keys: keys, values: values)
    let candidateUpdated = candidate.update(keys: keys, values: values)
    eval([
        baselineUpdated.0, baselineUpdated.1,
        candidateUpdated.0, candidateUpdated.1,
    ])
    Stream.gpu.synchronize()

    #expect(baseline.offset == 769)
    #expect(candidate.offset == 769)
    #expect(rawBF16(baselineUpdated.0) == rawBF16(candidateUpdated.0))
    #expect(rawBF16(baselineUpdated.1) == rawBF16(candidateUpdated.1))
    print("FULL_PARAMS_GROWTH offset=768 prepared=nil stock_offset=769 cache_bits=match")
}

private func verifyFullAttentionCarrierFallback() {
    var carrier: LagunaFullAttentionParamsCarrier?
    _ = lagunaFullAttentionParams(
        writeIdx: 513, capacity: 768, carrier: &carrier)
    let mismatch = lagunaFullAttentionParams(
        writeIdx: 514, capacity: 768, carrier: &carrier)
    #expect(mismatch.dtype == .uint32)
    #expect(mismatch.asArray(UInt32.self) == [UInt32(514), 515, 768])
    #expect(carrier?.writeIdx == 513)
    #expect(carrier?.capacity == 768)
    print("FULL_PARAMS_FALLBACK requested=514 carrier=513 words=[514,515,768] carrier_unchanged=true")
}

private func verifyFullAttentionCarrierCounts() {
    var constructions = 0
    var reuses = 0
    var mismatches = 0
    for offset in 513..<640 {
        var carrier: LagunaFullAttentionParamsCarrier?
        for _ in 0..<10 {
            let previous = carrier
            let params = lagunaFullAttentionParams(
                writeIdx: offset, capacity: 768, carrier: &carrier)
            if previous == nil {
                constructions += 1
            } else if previous?.writeIdx == offset && previous?.capacity == 768 {
                reuses += 1
            } else {
                mismatches += 1
            }
            #expect(params.asArray(UInt32.self) == [UInt32(offset), UInt32(offset + 1), 768])
        }
    }
    #expect(constructions == 127)
    #expect(reuses == 1_143)
    #expect(mismatches == 0)
    print("FULL_PARAMS_COUNTS positions=127 dispatches=1270 baseline_constructions=1270 candidate_constructions=\(constructions) candidate_reuses=\(reuses) mismatches=\(mismatches) prefill=0 sliding=0 growth=0")
}

private func makeFullAttentionResidentLayers() -> [FullAttentionResidentLayer] {
    (0..<10).map { index in
        FullAttentionResidentLayer(
            keys: MLXArray.full(
                [1, 8, 768, 128],
                values: MLXArray(Float(index + 1) / 256),
                dtype: .bfloat16),
            values: MLXArray.full(
                [1, 8, 768, 128],
                values: MLXArray(Float(index + 1) / 512),
                dtype: .bfloat16)
        )
    }
}

private func runFullAttentionSequence(
    inputs: FullAttentionProbeInputs,
    layers: [FullAttentionResidentLayer],
    arm: FullAttentionProbeArm
) {
    var carrier: LagunaFullAttentionParamsCarrier?
    var outputs = [MLXArray]()
    outputs.reserveCapacity(layers.count)
    for layer in layers {
        let params: MLXArray
        switch arm {
        case .baseline:
            params = MLXArray([UInt32(513), 514, 768])
        case .candidate:
            params = lagunaFullAttentionParams(
                writeIdx: 513, capacity: 768, carrier: &carrier)
        }
        outputs.append(inputs.call(
            cacheKeys: layer.keys,
            cacheValues: layer.values,
            writeIdx: 513,
            params: params))
    }
    eval(outputs)
}

private func measureFullAttentionBlock(
    inputs: FullAttentionProbeInputs,
    layers: [FullAttentionResidentLayer],
    arm: FullAttentionProbeArm,
    repetitions: Int
) -> UInt64 {
    Stream.gpu.synchronize()
    let start = DispatchTime.now().uptimeNanoseconds
    for _ in 0..<repetitions {
        runFullAttentionSequence(inputs: inputs, layers: layers, arm: arm)
    }
    Stream.gpu.synchronize()
    return (DispatchTime.now().uptimeNanoseconds - start) / UInt64(repetitions)
}

private func runFullAttentionCarrierTiming(inputs: FullAttentionProbeInputs) {
    let baselineLayers = makeFullAttentionResidentLayers()
    let candidateLayers = makeFullAttentionResidentLayers()
    eval(
        inputs.residentArrays
            + baselineLayers.flatMap { [$0.keys, $0.values] }
            + candidateLayers.flatMap { [$0.keys, $0.values] })
    Stream.gpu.synchronize()
    runFullAttentionSequence(
        inputs: inputs, layers: baselineLayers, arm: .baseline)
    runFullAttentionSequence(
        inputs: inputs, layers: candidateLayers, arm: .candidate)
    Stream.gpu.synchronize()

    let repetitions = 16
    let rounds = 8
    let orders: [(String, [FullAttentionProbeArm])] = [
        ("ABBA", [.baseline, .candidate, .candidate, .baseline]),
        ("BAAB", [.candidate, .baseline, .baseline, .candidate]),
    ]
    for (order, pattern) in orders {
        for round in 0..<rounds {
            for (block, arm) in pattern.enumerated() {
                let layers = arm == .baseline ? baselineLayers : candidateLayers
                let elapsed = measureFullAttentionBlock(
                    inputs: inputs,
                    layers: layers,
                    arm: arm,
                    repetitions: repetitions)
                let label = arm == .baseline ? "A" : "B"
                print("FULL_PARAMS_TIMING order=\(order) round=\(round) block=\(block) arm=\(label) ns_per_sequence=\(elapsed) n=\(repetitions)")
            }
        }
    }
}
