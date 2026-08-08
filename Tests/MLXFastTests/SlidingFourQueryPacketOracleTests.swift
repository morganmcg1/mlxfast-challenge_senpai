import Foundation
import MLX
@testable import MLXFastModel
import Testing

@Test
func slidingFourQueryPacketMatchesTwoHeadKernelAndReportsTiming() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
    else {
        return
    }

    let fixture = SlidingAttentionOracleFixture()
    for writeIdx in [0, 31, 511] {
        let (baselineKeys, baselineValues) = fixture.makeCache()
        let (candidateKeys, candidateValues) = fixture.makeCache()
        let baselineOutput = fixture.baseline(
            cacheKeys: baselineKeys,
            cacheValues: baselineValues,
            writeIdx: writeIdx
        )
        let candidateOutput = fixture.candidate(
            cacheKeys: candidateKeys,
            cacheValues: candidateValues,
            writeIdx: writeIdx
        )
        eval(baselineOutput, candidateOutput)

        let outputExact =
            baselineOutput.asArray(Float.self) == candidateOutput.asArray(Float.self)
        let keyCacheExact =
            baselineKeys.asArray(Float.self) == candidateKeys.asArray(Float.self)
        let valueCacheExact =
            baselineValues.asArray(Float.self) == candidateValues.asArray(Float.self)

        print(
            "SLIDING_ORACLE write_idx=\(writeIdx) "
                + "output_exact=\(outputExact) "
                + "key_cache_exact=\(keyCacheExact) "
                + "value_cache_exact=\(valueCacheExact)"
        )
        #expect(outputExact, "output mismatch at ring index \(writeIdx)")
        #expect(keyCacheExact, "key-cache mismatch at ring index \(writeIdx)")
        #expect(valueCacheExact, "value-cache mismatch at ring index \(writeIdx)")
    }

    let (baselineKeys, baselineValues) = fixture.makeCache()
    let (candidateKeys, candidateValues) = fixture.makeCache()
    for _ in 0..<3 {
        eval(fixture.baseline(
            cacheKeys: baselineKeys,
            cacheValues: baselineValues,
            writeIdx: 31
        ))
        eval(fixture.candidate(
            cacheKeys: candidateKeys,
            cacheValues: candidateValues,
            writeIdx: 31
        ))
    }

    var abBaseline = [Double]()
    var abCandidate = [Double]()
    var baBaseline = [Double]()
    var baCandidate = [Double]()
    for _ in 0..<9 {
        abBaseline.append(measureSlidingKernel {
            fixture.baseline(
                cacheKeys: baselineKeys,
                cacheValues: baselineValues,
                writeIdx: 31
            )
        })
        abCandidate.append(measureSlidingKernel {
            fixture.candidate(
                cacheKeys: candidateKeys,
                cacheValues: candidateValues,
                writeIdx: 31
            )
        })
    }
    for _ in 0..<9 {
        baCandidate.append(measureSlidingKernel {
            fixture.candidate(
                cacheKeys: candidateKeys,
                cacheValues: candidateValues,
                writeIdx: 31
            )
        })
        baBaseline.append(measureSlidingKernel {
            fixture.baseline(
                cacheKeys: baselineKeys,
                cacheValues: baselineValues,
                writeIdx: 31
            )
        })
    }

    let abBaselineMedian = median(abBaseline)
    let abCandidateMedian = median(abCandidate)
    let baBaselineMedian = median(baBaseline)
    let baCandidateMedian = median(baCandidate)
    let abSpeedup = abBaselineMedian / abCandidateMedian
    let baSpeedup = baBaselineMedian / baCandidateMedian
    let geometricSpeedup = (abSpeedup * baSpeedup).squareRoot()
    print(
        String(
            format:
                "SLIDING_TIMING ab_baseline=%.9f ab_candidate=%.9f "
                    + "ab_speedup=%.6f ba_baseline=%.9f ba_candidate=%.9f "
                    + "ba_speedup=%.6f geometric_speedup=%.6f",
            abBaselineMedian,
            abCandidateMedian,
            abSpeedup,
            baBaselineMedian,
            baCandidateMedian,
            baSpeedup,
            geometricSpeedup
        )
    )
    #expect(abBaselineMedian > 0)
    #expect(abCandidateMedian > 0)
    #expect(baBaselineMedian > 0)
    #expect(baCandidateMedian > 0)
}

private struct SlidingAttentionOracleFixture {
    private let rawQueries: MLXArray
    private let rawKeys: MLXArray
    private let rawValues: MLXArray
    private let queryWeight: MLXArray
    private let keyWeight: MLXArray
    private let angles: MLXArray
    private let scale: MLXArray
    private let cacheKeySeed: [Float]
    private let cacheValueSeed: [Float]

    init() {
        rawQueries = oracleBF16(
            shape: [1, 1, 64 * 128],
            salt: 3,
            modulus: 127,
            divisor: 128
        )
        rawKeys = oracleBF16(
            shape: [1, 1, 8 * 128],
            salt: 7,
            modulus: 113,
            divisor: 128
        )
        rawValues = oracleBF16(
            shape: [1, 1, 8 * 128],
            salt: 11,
            modulus: 109,
            divisor: 64
        )
        queryWeight = oracleBF16(
            shape: [128],
            salt: 13,
            modulus: 31,
            divisor: 64,
            offset: 1
        )
        keyWeight = oracleBF16(
            shape: [128],
            salt: 17,
            modulus: 29,
            divisor: 64,
            offset: 1
        )

        let cosine = (0..<64).map { index in
            Float(Foundation.cos(Double(index + 1) * 0.003))
        }
        let sine = (0..<64).map { index in
            Float(Foundation.sin(Double(index + 1) * 0.003))
        }
        angles = MLXArray(cosine + sine, [1, 1, 1, 128])
        scale = MLXArray(Float(1) / Float(128).squareRoot())

        let cacheCount = 8 * 512 * 128
        cacheKeySeed = oracleValues(
            count: cacheCount,
            salt: 19,
            modulus: 97,
            divisor: 128
        )
        cacheValueSeed = oracleValues(
            count: cacheCount,
            salt: 23,
            modulus: 89,
            divisor: 64
        )
        eval(rawQueries, rawKeys, rawValues, queryWeight, keyWeight, angles, scale)
    }

    func makeCache() -> (MLXArray, MLXArray) {
        let shape = [1, 8, 512, 128]
        let keys = MLXArray(cacheKeySeed, shape).asType(.bfloat16)
        let values = MLXArray(cacheValueSeed, shape).asType(.bfloat16)
        eval(keys, values)
        return (keys, values)
    }

    func baseline(
        cacheKeys: MLXArray,
        cacheValues: MLXArray,
        writeIdx: Int
    ) -> MLXArray {
        lagunaSlidingFusedAttentionBaseline(
            rawQueries: rawQueries,
            rawKeys: rawKeys,
            rawValues: rawValues,
            queryWeight: queryWeight,
            keyWeight: keyWeight,
            angles: angles,
            cacheKeys: cacheKeys,
            cacheValues: cacheValues,
            writeIdx: writeIdx,
            scale: scale
        )
    }

    func candidate(
        cacheKeys: MLXArray,
        cacheValues: MLXArray,
        writeIdx: Int
    ) -> MLXArray {
        lagunaSlidingFusedAttention(
            rawQueries: rawQueries,
            rawKeys: rawKeys,
            rawValues: rawValues,
            queryWeight: queryWeight,
            keyWeight: keyWeight,
            angles: angles,
            cacheKeys: cacheKeys,
            cacheValues: cacheValues,
            writeIdx: writeIdx,
            scale: scale
        )
    }
}

private func oracleBF16(
    shape: [Int],
    salt: Int,
    modulus: Int,
    divisor: Float,
    offset: Float = 0
) -> MLXArray {
    let values = oracleValues(
        count: shape.reduce(1, *),
        salt: salt,
        modulus: modulus,
        divisor: divisor,
        offset: offset
    )
    return MLXArray(values, shape).asType(.bfloat16)
}

private func oracleValues(
    count: Int,
    salt: Int,
    modulus: Int,
    divisor: Float,
    offset: Float = 0
) -> [Float] {
    (0..<count).map { index in
        let centered = ((index * 37 + salt) % modulus) - modulus / 2
        return offset + Float(centered) / divisor
    }
}

private func measureSlidingKernel(_ operation: () -> MLXArray) -> Double {
    let iterations = 20
    let start = ProcessInfo.processInfo.systemUptime
    for _ in 0..<iterations {
        eval(operation())
    }
    return (ProcessInfo.processInfo.systemUptime - start) / Double(iterations)
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    return sorted[sorted.count / 2]
}
