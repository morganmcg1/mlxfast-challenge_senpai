import Foundation
import MLX
import Testing
@testable import MLXFastModel

private let slidingAttentionWriteIndices = [0, 15, 16, 31, 32, 255, 511]

private struct SlidingAttentionFixture {
    let rawQueries: MLXArray
    let rawKeys: MLXArray
    let rawValues: MLXArray
    let queryWeight: MLXArray
    let keyWeight: MLXArray
    let angles: MLXArray
    let cacheKeys: MLXArray
    let cacheValues: MLXArray
    let scale: MLXArray
}

@Test
func lagunaSlidingFusedAttention16SGIsBitwiseEquivalentWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
    else {
        return
    }

    let fixture = makeSlidingAttentionFixture()
    for writeIdx in slidingAttentionWriteIndices {
        let controlKeys = deepCopy(fixture.cacheKeys)
        let controlValues = deepCopy(fixture.cacheValues)
        let candidateKeys = deepCopy(fixture.cacheKeys)
        let candidateValues = deepCopy(fixture.cacheValues)

        let control = runSlidingAttention(
            fixture,
            cacheKeys: controlKeys,
            cacheValues: controlValues,
            writeIdx: writeIdx,
            use16PhysicalSimdgroups: false
        )
        eval(control)
        let candidate = runSlidingAttention(
            fixture,
            cacheKeys: candidateKeys,
            cacheValues: candidateValues,
            writeIdx: writeIdx,
            use16PhysicalSimdgroups: true
        )
        eval(candidate)

        let controlOutputBits = bf16Bits(control)
        let candidateOutputBits = bf16Bits(candidate)
        let controlKeyBits = bf16Bits(controlKeys)
        let candidateKeyBits = bf16Bits(candidateKeys)
        let controlValueBits = bf16Bits(controlValues)
        let candidateValueBits = bf16Bits(candidateValues)
        let label = "writeIdx=\(writeIdx)"

        #expect(
            controlOutputBits == candidateOutputBits,
            Comment(rawValue: "output mismatch for \(label)")
        )
        #expect(
            controlKeyBits == candidateKeyBits,
            Comment(rawValue: "key-cache mismatch for \(label)")
        )
        #expect(
            controlValueBits == candidateValueBits,
            Comment(rawValue: "value-cache mismatch for \(label)")
        )

        if writeIdx == slidingAttentionWriteIndices[0] {
            var corrupted = candidateOutputBits
            corrupted[corrupted.count / 2] ^= UInt16(1)
            #expect(
                controlOutputBits != corrupted,
                "corruption control failed to detect a flipped BF16 bit"
            )
        }

        print(
            "sliding_attention_oracle \(label) heads=64 head_dim=128 "
                + "output_words=\(controlOutputBits.count) "
                + "cache_words=\(controlKeyBits.count + controlValueBits.count) bitwise=true"
        )
    }
}

@Test
func lagunaSlidingFusedAttention16SGPairedTimingWhenRuntimeBenchmarksAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_BENCHMARKS"] == "1"
    else {
        return
    }

    let fixture = makeSlidingAttentionFixture()
    let controlKeys = deepCopy(fixture.cacheKeys)
    let controlValues = deepCopy(fixture.cacheValues)
    let candidateKeys = deepCopy(fixture.cacheKeys)
    let candidateValues = deepCopy(fixture.cacheValues)
    let writeIdx = 255

    eval(
        runSlidingAttention(
            fixture,
            cacheKeys: controlKeys,
            cacheValues: controlValues,
            writeIdx: writeIdx,
            use16PhysicalSimdgroups: false
        ),
        runSlidingAttention(
            fixture,
            cacheKeys: candidateKeys,
            cacheValues: candidateValues,
            writeIdx: writeIdx,
            use16PhysicalSimdgroups: true
        )
    )
    Stream().synchronize()

    let pairCount = 9
    let repetitions = 64
    var controlAB = [Double]()
    var candidateAB = [Double]()
    var controlBA = [Double]()
    var candidateBA = [Double]()

    for _ in 0..<pairCount {
        controlAB.append(
            measureSlidingAttentionBlock(
                fixture,
                cacheKeys: controlKeys,
                cacheValues: controlValues,
                writeIdx: writeIdx,
                use16PhysicalSimdgroups: false,
                repetitions: repetitions
            ))
        candidateAB.append(
            measureSlidingAttentionBlock(
                fixture,
                cacheKeys: candidateKeys,
                cacheValues: candidateValues,
                writeIdx: writeIdx,
                use16PhysicalSimdgroups: true,
                repetitions: repetitions
            ))
    }
    for _ in 0..<pairCount {
        candidateBA.append(
            measureSlidingAttentionBlock(
                fixture,
                cacheKeys: candidateKeys,
                cacheValues: candidateValues,
                writeIdx: writeIdx,
                use16PhysicalSimdgroups: true,
                repetitions: repetitions
            ))
        controlBA.append(
            measureSlidingAttentionBlock(
                fixture,
                cacheKeys: controlKeys,
                cacheValues: controlValues,
                writeIdx: writeIdx,
                use16PhysicalSimdgroups: false,
                repetitions: repetitions
            ))
    }

    let controlABMedian = median(controlAB)
    let candidateABMedian = median(candidateAB)
    let controlBAMedian = median(controlBA)
    let candidateBAMedian = median(candidateBA)
    let speedupAB = controlABMedian / candidateABMedian
    let speedupBA = controlBAMedian / candidateBAMedian

    print(
        "sliding_attention_timing order=AB repetitions=\(repetitions) pairs=\(pairCount) "
            + "control_seconds=\(controlABMedian) candidate_seconds=\(candidateABMedian) "
            + "speedup=\(speedupAB)"
    )
    print(
        "sliding_attention_timing order=BA repetitions=\(repetitions) pairs=\(pairCount) "
            + "control_seconds=\(controlBAMedian) candidate_seconds=\(candidateBAMedian) "
            + "speedup=\(speedupBA)"
    )

    #expect(speedupAB >= 1.01, Comment(rawValue: "AB speedup \(speedupAB) < 1.01"))
    #expect(speedupBA >= 1.01, Comment(rawValue: "BA speedup \(speedupBA) < 1.01"))
}

private func makeSlidingAttentionFixture() -> SlidingAttentionFixture {
    let headDim = 128
    let queryElements = 64 * headDim
    let keyValueElements = 8 * headDim
    let cacheElements = 8 * 512 * headDim

    let queryAxis = MLXArray(0..<queryElements).asType(.float32)
    let keyValueAxis = MLXArray(0..<keyValueElements).asType(.float32)
    let dimensionAxis = MLXArray(0..<headDim).asType(.float32)
    let cacheAxis = MLXArray(0..<cacheElements).asType(.float32)

    let rawQueries = (
        sin(queryAxis * 0.013) * 0.375 + cos(queryAxis * 0.007) * 0.125
    ).asType(.bfloat16).reshaped([1, 1, queryElements])
    let rawKeys = (
        sin(keyValueAxis * 0.019 + 0.3) * 0.25
            + cos(keyValueAxis * 0.011) * 0.0625
    ).asType(.bfloat16).reshaped([1, 1, keyValueElements])
    let rawValues = (
        cos(keyValueAxis * 0.017 + 0.2) * 0.3125
            - sin(keyValueAxis * 0.005) * 0.09375
    ).asType(.bfloat16).reshaped([1, 1, keyValueElements])
    let queryWeight = (
        sin(dimensionAxis * 0.031) * 0.125 + 0.75
    ).asType(.bfloat16)
    let keyWeight = (
        cos(dimensionAxis * 0.023) * 0.1875 + 0.625
    ).asType(.bfloat16)

    var angleValues = [Float]()
    angleValues.reserveCapacity(headDim)
    for index in 0..<(headDim / 2) {
        angleValues.append(cos(Float(index) * 0.017))
    }
    for index in 0..<(headDim / 2) {
        angleValues.append(sin(Float(index) * 0.017))
    }
    let angles = MLXArray(angleValues, [1, 1, 1, headDim])

    let cacheKeys = (
        sin(cacheAxis * 0.00037 + 0.41) * 0.21875
            + cos(cacheAxis * 0.00011) * 0.03125
    ).asType(.bfloat16).reshaped([1, 8, 512, headDim])
    let cacheValues = (
        cos(cacheAxis * 0.00029 + 0.17) * 0.28125
            - sin(cacheAxis * 0.00007) * 0.046875
    ).asType(.bfloat16).reshaped([1, 8, 512, headDim])

    return SlidingAttentionFixture(
        rawQueries: rawQueries,
        rawKeys: rawKeys,
        rawValues: rawValues,
        queryWeight: queryWeight,
        keyWeight: keyWeight,
        angles: angles,
        cacheKeys: cacheKeys,
        cacheValues: cacheValues,
        scale: MLXArray([Float(1.0 / sqrt(128.0))])
    )
}

private func runSlidingAttention(
    _ fixture: SlidingAttentionFixture,
    cacheKeys: MLXArray,
    cacheValues: MLXArray,
    writeIdx: Int,
    use16PhysicalSimdgroups: Bool
) -> MLXArray {
    lagunaSlidingFusedAttention(
        rawQueries: fixture.rawQueries,
        rawKeys: fixture.rawKeys,
        rawValues: fixture.rawValues,
        queryWeight: fixture.queryWeight,
        keyWeight: fixture.keyWeight,
        angles: fixture.angles,
        cacheKeys: cacheKeys,
        cacheValues: cacheValues,
        writeIdx: writeIdx,
        scale: fixture.scale,
        use16PhysicalSimdgroups: use16PhysicalSimdgroups
    )
}

private func measureSlidingAttentionBlock(
    _ fixture: SlidingAttentionFixture,
    cacheKeys: MLXArray,
    cacheValues: MLXArray,
    writeIdx: Int,
    use16PhysicalSimdgroups: Bool,
    repetitions: Int
) -> Double {
    Stream().synchronize()
    let start = DispatchTime.now().uptimeNanoseconds
    var outputs = [MLXArray]()
    outputs.reserveCapacity(repetitions)
    for _ in 0..<repetitions {
        outputs.append(
            runSlidingAttention(
                fixture,
                cacheKeys: cacheKeys,
                cacheValues: cacheValues,
                writeIdx: writeIdx,
                use16PhysicalSimdgroups: use16PhysicalSimdgroups
            ))
    }
    eval(outputs)
    Stream().synchronize()
    return Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000_000_000.0
}

private func deepCopy(_ array: MLXArray) -> MLXArray {
    MLXArray(data: array.asData(access: .copy))
}

private func bf16Bits(_ array: MLXArray) -> [UInt16] {
    array.view(dtype: .uint16).asArray(UInt16.self)
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    return sorted[sorted.count / 2]
}
