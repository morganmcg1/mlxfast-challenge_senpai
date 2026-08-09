import Foundation
import MLX
@testable import MLXFastModel
import Testing

private struct FullAttentionInputs {
    let rawQueries: MLXArray
    let rawKeys: MLXArray
    let rawValues: MLXArray
    let queryWeight: MLXArray
    let keyWeight: MLXArray
    let angles: MLXArray
    let scale: MLXArray
}

private enum FullAttentionVariant {
    case control
    case candidate
}

private func deterministicTensor(
    count: Int,
    shape: [Int],
    phase: Float,
    frequency: Float,
    amplitude: Float
) -> MLXArray {
    let axis = MLXArray(0..<count).asType(.float32)
    return (sin(axis * frequency + phase) * amplitude)
        .asType(.bfloat16)
        .reshaped(shape)
}

private func makeFullAttentionInputs() -> FullAttentionInputs {
    let headDim = LagunaConstants.headDim
    let heads = LagunaConstants.fullAttentionHeads
    let kvHeads = LagunaConstants.numKeyValueHeads
    return FullAttentionInputs(
        rawQueries: deterministicTensor(
            count: heads * headDim,
            shape: [1, 1, heads * headDim],
            phase: 0.11,
            frequency: 0.013,
            amplitude: 0.125
        ),
        rawKeys: deterministicTensor(
            count: kvHeads * headDim,
            shape: [1, 1, kvHeads * headDim],
            phase: 0.23,
            frequency: 0.017,
            amplitude: 0.09375
        ),
        rawValues: deterministicTensor(
            count: kvHeads * headDim,
            shape: [1, 1, kvHeads * headDim],
            phase: 0.37,
            frequency: 0.019,
            amplitude: 0.109375
        ),
        queryWeight: deterministicTensor(
            count: headDim,
            shape: [headDim],
            phase: 0.41,
            frequency: 0.021,
            amplitude: 0.0625
        ),
        keyWeight: deterministicTensor(
            count: headDim,
            shape: [headDim],
            phase: 0.53,
            frequency: 0.023,
            amplitude: 0.078125
        ),
        angles: (MLXArray(0..<(headDim / 2)).asType(.float32) * 0.001 + 0.02)
            .reshaped([1, 1, 1, headDim / 2]),
        scale: MLXArray(Float(1.0 / Foundation.sqrt(Double(headDim))))
    )
}

private func makeFullAttentionCache(capacity: Int, phase: Float) -> MLXArray {
    let count = LagunaConstants.numKeyValueHeads * capacity * LagunaConstants.headDim
    return deterministicTensor(
        count: count,
        shape: [1, LagunaConstants.numKeyValueHeads, capacity, LagunaConstants.headDim],
        phase: phase,
        frequency: 0.00013,
        amplitude: 0.03125
    )
}

private func invokeFullAttention(
    _ variant: FullAttentionVariant,
    inputs: FullAttentionInputs,
    cacheKeys: MLXArray,
    cacheValues: MLXArray,
    writeIdx: Int
) -> MLXArray {
    switch variant {
    case .control:
        lagunaFullFusedAttentionControl(
            rawQueries: inputs.rawQueries,
            rawKeys: inputs.rawKeys,
            rawValues: inputs.rawValues,
            queryWeight: inputs.queryWeight,
            keyWeight: inputs.keyWeight,
            angles: inputs.angles,
            cacheKeys: cacheKeys,
            cacheValues: cacheValues,
            writeIdx: writeIdx,
            scale: inputs.scale
        )
    case .candidate:
        lagunaFullFusedAttention(
            rawQueries: inputs.rawQueries,
            rawKeys: inputs.rawKeys,
            rawValues: inputs.rawValues,
            queryWeight: inputs.queryWeight,
            keyWeight: inputs.keyWeight,
            angles: inputs.angles,
            cacheKeys: cacheKeys,
            cacheValues: cacheValues,
            writeIdx: writeIdx,
            scale: inputs.scale
        )
    }
}

private func firstExactMismatch(_ lhs: MLXArray, _ rhs: MLXArray) -> Int? {
    let left = lhs.asArray(Float.self)
    let right = rhs.asArray(Float.self)
    guard left.count == right.count else { return min(left.count, right.count) }
    return left.indices.first { left[$0].bitPattern != right[$0].bitPattern }
}

private func blockingNanoseconds(_ body: () -> MLXArray) -> UInt64 {
    Stream.gpu.synchronize()
    let start = DispatchTime.now().uptimeNanoseconds
    let output = body()
    eval(output)
    Stream.gpu.synchronize()
    return DispatchTime.now().uptimeNanoseconds - start
}

private func proveWriteSlotOwnership() {
    let layers = 10
    var ownerObservations = 0
    var nonownerObservations = 0
    var invalidResidueMappings = 0
    var invalidOwners = 0

    for _ in 0..<layers {
        for length in 1...640 {
            let writeIdx = length - 1
            let owner = writeIdx & 31
            for simdgroup in 0..<32 {
                let rows = stride(from: simdgroup, to: length, by: 32)
                if rows.contains(where: { ($0 & 31) != simdgroup }) {
                    invalidResidueMappings += 1
                }
                let reachesWriteIdx = rows.contains(writeIdx)
                if reachesWriteIdx != (simdgroup == owner) {
                    invalidOwners += 1
                }
                if simdgroup == owner {
                    ownerObservations += 1
                } else {
                    nonownerObservations += 1
                }
            }
        }
    }

    #expect(invalidResidueMappings == 0)
    #expect(invalidOwners == 0)
    #expect(ownerObservations == 6_400)
    #expect(nonownerObservations == 198_400)
    print(
        "FULL_OWNER_REACHABILITY {\"lengths\":640,\"layers\":10,\"owner_observations\":\(ownerObservations),\"nonowner_observations\":\(nonownerObservations),\"invalid_residue_mappings\":\(invalidResidueMappings),\"invalid_owners\":\(invalidOwners)}"
    )
}

private func verifyParity(inputs: FullAttentionInputs) {
    let capacity = 640
    let positions = [0, 1, 31, 32, 63, 511, 512, 544, 576, 608, 639]

    for writeIdx in positions {
        let controlKeys = makeFullAttentionCache(capacity: capacity, phase: 0.61)
        let controlValues = makeFullAttentionCache(capacity: capacity, phase: 0.73)
        let candidateKeys = makeFullAttentionCache(capacity: capacity, phase: 0.61)
        let candidateValues = makeFullAttentionCache(capacity: capacity, phase: 0.73)
        eval(controlKeys, controlValues, candidateKeys, candidateValues)
        Stream.gpu.synchronize()
        let control = invokeFullAttention(
            .control,
            inputs: inputs,
            cacheKeys: controlKeys,
            cacheValues: controlValues,
            writeIdx: writeIdx
        )
        let candidate = invokeFullAttention(
            .candidate,
            inputs: inputs,
            cacheKeys: candidateKeys,
            cacheValues: candidateValues,
            writeIdx: writeIdx
        )
        eval(control, candidate)
        Stream.gpu.synchronize()

        let outputMismatch = firstExactMismatch(control, candidate)
        let keyMismatch = firstExactMismatch(controlKeys, candidateKeys)
        let valueMismatch = firstExactMismatch(controlValues, candidateValues)
        let outputMismatchText = outputMismatch.map(String.init) ?? "null"
        let keyMismatchText = keyMismatch.map(String.init) ?? "null"
        let valueMismatchText = valueMismatch.map(String.init) ?? "null"
        #expect(outputMismatch == nil)
        #expect(keyMismatch == nil)
        #expect(valueMismatch == nil)
        print(
            "FULL_OWNER_PARITY {\"write_idx\":\(writeIdx),\"output_mismatch\":\(outputMismatchText),\"key_cache_mismatch\":\(keyMismatchText),\"value_cache_mismatch\":\(valueMismatchText)}"
        )
    }
}

private func measureFullAttention(length: Int, inputs: FullAttentionInputs) {
    let writeIdx = length - 1
    let controlKeys = makeFullAttentionCache(capacity: length, phase: 0.61)
    let controlValues = makeFullAttentionCache(capacity: length, phase: 0.73)
    let candidateKeys = makeFullAttentionCache(capacity: length, phase: 0.61)
    let candidateValues = makeFullAttentionCache(capacity: length, phase: 0.73)
    eval(controlKeys, controlValues, candidateKeys, candidateValues)
    Stream.gpu.synchronize()

    for _ in 0..<10 {
        _ = blockingNanoseconds {
            invokeFullAttention(
                .control,
                inputs: inputs,
                cacheKeys: controlKeys,
                cacheValues: controlValues,
                writeIdx: writeIdx
            )
        }
        _ = blockingNanoseconds {
            invokeFullAttention(
                .candidate,
                inputs: inputs,
                cacheKeys: candidateKeys,
                cacheValues: candidateValues,
                writeIdx: writeIdx
            )
        }
    }

    for controlFirst in [true, false] {
        var controlSamples: [UInt64] = []
        var candidateSamples: [UInt64] = []
        controlSamples.reserveCapacity(101)
        candidateSamples.reserveCapacity(101)

        for _ in 0..<101 {
            if controlFirst {
                controlSamples.append(blockingNanoseconds {
                    invokeFullAttention(
                        .control,
                        inputs: inputs,
                        cacheKeys: controlKeys,
                        cacheValues: controlValues,
                        writeIdx: writeIdx
                    )
                })
                candidateSamples.append(blockingNanoseconds {
                    invokeFullAttention(
                        .candidate,
                        inputs: inputs,
                        cacheKeys: candidateKeys,
                        cacheValues: candidateValues,
                        writeIdx: writeIdx
                    )
                })
            } else {
                candidateSamples.append(blockingNanoseconds {
                    invokeFullAttention(
                        .candidate,
                        inputs: inputs,
                        cacheKeys: candidateKeys,
                        cacheValues: candidateValues,
                        writeIdx: writeIdx
                    )
                })
                controlSamples.append(blockingNanoseconds {
                    invokeFullAttention(
                        .control,
                        inputs: inputs,
                        cacheKeys: controlKeys,
                        cacheValues: controlValues,
                        writeIdx: writeIdx
                    )
                })
            }
        }

        let order = controlFirst ? "control-candidate" : "candidate-control"
        let controls = controlSamples.map(String.init).joined(separator: ",")
        let candidates = candidateSamples.map(String.init).joined(separator: ",")
        print(
            "FULL_OWNER_SAMPLES {\"length\":\(length),\"order\":\"\(order)\",\"control_ns\":[\(controls)],\"candidate_ns\":[\(candidates)]}"
        )
    }
}

@Test
func fullAttentionOwnerLoadsMatchControlAndMeasureWhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_FULL_OWNER_TESTS"] == "1"
    else {
        return
    }

    let device = GPU.deviceInfo()
    print(
        "FULL_OWNER_DEVICE {\"architecture\":\"\(device.architecture)\",\"memory_bytes\":\(device.memorySize),\"recommended_working_set_bytes\":\(device.maxRecommendedWorkingSetSize),\"kernel\":\"laguna_full_fused_attn_grow_v1\",\"threadgroup_threads\":1024,\"simdgroups\":32}"
    )
    proveWriteSlotOwnership()
    let inputs = makeFullAttentionInputs()
    verifyParity(inputs: inputs)
    measureFullAttention(length: 512, inputs: inputs)
    measureFullAttention(length: 640, inputs: inputs)
}
