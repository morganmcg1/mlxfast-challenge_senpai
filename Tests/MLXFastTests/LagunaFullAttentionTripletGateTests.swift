import Foundation
import MLX
@testable import MLXFastModel
import Testing

@Suite(.serialized)
struct LagunaFullAttentionTripletGateTests {
    private enum FixtureMode: String, CaseIterable {
        case smooth
        case random
        case adversarial
    }

    private struct Fixture {
        let rawQueries: MLXArray
        let rawKeys: MLXArray
        let rawValues: MLXArray
        let queryWeight: MLXArray
        let keyWeight: MLXArray
        let angles: MLXArray
        let cacheKeys: MLXArray
        let cacheValues: MLXArray
        let writeIdx: Int
        let scale: MLXArray
    }

    private let heads = LagunaConstants.fullAttentionHeads
    private let kvHeads = LagunaConstants.numKeyValueHeads
    private let headDim = LagunaConstants.headDim
    private let capacity = 640

    @Test
    func lagunaFullAttentionTripletGateExactOutputsAndCaches() {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
        else { return }

        let contexts = [513, 544, 545, 576, 577, 608, 609, 640]
        for mode in FixtureMode.allCases {
            for context in contexts {
                let baseline = makeFixture(context: context, mode: mode)
                let candidate = makeFixture(context: context, mode: mode)
                materialize(baseline)
                materialize(candidate)

                let baselineOutput = baselineAttention(baseline)
                let candidateOutput = candidateAttention(candidate)
                eval(
                    baselineOutput, candidateOutput,
                    baseline.cacheKeys, baseline.cacheValues,
                    candidate.cacheKeys, candidate.cacheValues
                )

                let label = "mode=\(mode.rawValue) context=\(context)"
                #expect(
                    firstMismatch(bits(baselineOutput), bits(candidateOutput)) == nil,
                    "output mismatch \(label)"
                )
                #expect(
                    firstMismatch(bits(baseline.cacheKeys), bits(candidate.cacheKeys)) == nil,
                    "key-cache mismatch \(label)"
                )
                #expect(
                    firstMismatch(bits(baseline.cacheValues), bits(candidate.cacheValues)) == nil,
                    "value-cache mismatch \(label)"
                )
                print("GATE0 exact-match \(label)")
            }
        }
    }

    @Test
    func lagunaFullAttentionTripletGateThirdHeadSensitivity() {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
        else { return }

        let context = 640
        let original = makeFixture(context: context, mode: .random)
        let mutated = makeFixture(context: context, mode: .random, mutateThirdHead: true)
        let baselineMutated = makeFixture(
            context: context,
            mode: .random,
            mutateThirdHead: true
        )
        materialize(original)
        materialize(mutated)
        materialize(baselineMutated)

        let originalOutput = candidateAttention(original)
        let mutatedOutput = candidateAttention(mutated)
        let baselineOutput = baselineAttention(baselineMutated)
        eval(originalOutput, mutatedOutput, baselineOutput)

        let originalBits = bits(originalOutput)
        let mutatedBits = bits(mutatedOutput)
        let baselineBits = bits(baselineOutput)
        let firstTwoHeads = 0 ..< (2 * headDim)
        let thirdHead = (2 * headDim) ..< (3 * headDim)

        #expect(
            firstMismatch(baselineBits, mutatedBits) == nil,
            "mutated third-head output differs from pair baseline"
        )
        #expect(
            Array(originalBits[firstTwoHeads]) == Array(mutatedBits[firstTwoHeads]),
            "third-head mutation contaminated first two heads"
        )
        #expect(
            Array(originalBits[thirdHead]) != Array(mutatedBits[thirdHead]),
            "third-head mutation did not affect third-head output"
        )
        print("GATE0 third-head-sensitivity exact=true isolated=true responsive=true")
    }

    @Test
    func lagunaFullAttentionTripletGateResourcesAndPairedTiming() {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
        else { return }

        let staticThreadgroupBytes =
            5 * headDim * MemoryLayout<UInt16>.stride
            + 6 * 32 * 32 * MemoryLayout<Float>.stride
            + 2 * 3 * 32 * MemoryLayout<Float>.stride
        let threadsPerThreadgroup = 1024
        #expect(staticThreadgroupBytes == 26_624)
        #expect(staticThreadgroupBytes <= 28 * 1024)
        #expect(threadsPerThreadgroup <= 1024)
        print(
            "GATE0 resources static_threadgroup_bytes=\(staticThreadgroupBytes) "
                + "threads=\(threadsPerThreadgroup)"
        )

        let baseline = makeFixture(context: 640, mode: .random)
        let candidate = makeFixture(context: 640, mode: .random)
        materialize(baseline)
        materialize(candidate)
        for _ in 0 ..< 5 {
            eval(baselineAttention(baseline))
            eval(candidateAttention(candidate))
        }

        let iterations = 100
        let rounds = 5
        let baselineFirst = pairedTiming(
            baseline: baseline,
            candidate: candidate,
            baselineFirst: true,
            iterations: iterations,
            rounds: rounds
        )
        let candidateFirst = pairedTiming(
            baseline: baseline,
            candidate: candidate,
            baselineFirst: false,
            iterations: iterations,
            rounds: rounds
        )

        printTiming("baseline-candidate", baselineFirst, iterations: iterations, rounds: rounds)
        printTiming("candidate-baseline", candidateFirst, iterations: iterations, rounds: rounds)
        #expect(
            baselineFirst.speedup >= 1.01,
            "baseline-candidate speedup \(baselineFirst.speedup) is below 1.01"
        )
        #expect(
            candidateFirst.speedup >= 1.01,
            "candidate-baseline speedup \(candidateFirst.speedup) is below 1.01"
        )
    }

    private func makeFixture(
        context: Int,
        mode: FixtureMode,
        mutateThirdHead: Bool = false
    ) -> Fixture {
        var queries = values(
            count: heads * headDim,
            mode: mode,
            salt: UInt32(context) &+ 11
        )
        if mutateThirdHead {
            for index in (2 * headDim) ..< (3 * headDim) {
                queries[index] = -queries[index] + Float((index % 7) - 3) * 0.125
            }
        }
        let keys = values(
            count: kvHeads * headDim,
            mode: mode,
            salt: UInt32(context) &+ 23
        )
        let newValues = values(
            count: kvHeads * headDim,
            mode: mode,
            salt: UInt32(context) &+ 37
        )
        let cacheKeys = values(
            count: kvHeads * capacity * headDim,
            mode: mode,
            salt: UInt32(context) &+ 41
        )
        let cacheValues = values(
            count: kvHeads * capacity * headDim,
            mode: mode,
            salt: UInt32(context) &+ 53
        )
        let queryWeight = (0 ..< headDim).map {
            Float(0.75) + Float(($0 * 7 + context) % 19) / 32
        }
        let keyWeight = (0 ..< headDim).map {
            Float(0.6875) + Float(($0 * 11 + context) % 23) / 32
        }
        var angles = [Float](repeating: 0, count: headDim / 2)
        let rotaryPairs = headDim / 4
        for index in 0 ..< rotaryPairs {
            let theta = Float((index + 1) * ((context % 31) + 1)) / 4096
            angles[index] = cos(theta)
            angles[index + rotaryPairs] = sin(theta)
        }

        return Fixture(
            rawQueries: bfloatArray(queries, shape: [1, 1, heads * headDim]),
            rawKeys: bfloatArray(keys, shape: [1, 1, kvHeads * headDim]),
            rawValues: bfloatArray(newValues, shape: [1, 1, kvHeads * headDim]),
            queryWeight: bfloatArray(queryWeight, shape: [headDim]),
            keyWeight: bfloatArray(keyWeight, shape: [headDim]),
            angles: MLXArray(angles, [1, 1, 1, headDim / 2]),
            cacheKeys: bfloatArray(
                cacheKeys,
                shape: [1, kvHeads, capacity, headDim]
            ),
            cacheValues: bfloatArray(
                cacheValues,
                shape: [1, kvHeads, capacity, headDim]
            ),
            writeIdx: context - 1,
            scale: MLXArray(Float(1 / sqrt(Float(headDim))))
        )
    }

    private func values(count: Int, mode: FixtureMode, salt: UInt32) -> [Float] {
        switch mode {
        case .smooth:
            return (0 ..< count).map { index in
                let coarse = Float((index + Int(salt)) % 29 - 14) / 16
                let fine = Float((index * 7 + Int(salt)) % 13 - 6) / 256
                return coarse + fine
            }
        case .random:
            return (0 ..< count).map { index in
                var word = UInt32(truncatingIfNeeded: index) &* 747_796_405 &+ salt
                word ^= word >> 16
                word &*= 2_246_822_519
                word ^= word >> 13
                return Float(Int(word & 0xffff) - 32_768) / 16_384
            }
        case .adversarial:
            let pattern: [Float] = [
                0.000_976_562_5, -0.000_976_562_5,
                8, -8, 0.125, -0.125, 2, -2,
            ]
            return (0 ..< count).map { pattern[($0 + Int(salt)) % pattern.count] }
        }
    }

    private func bfloatArray(_ values: [Float], shape: [Int]) -> MLXArray {
        MLXArray(values, shape).asType(.bfloat16)
    }

    private func materialize(_ fixture: Fixture) {
        eval(
            fixture.rawQueries, fixture.rawKeys, fixture.rawValues,
            fixture.queryWeight, fixture.keyWeight, fixture.angles,
            fixture.cacheKeys, fixture.cacheValues, fixture.scale
        )
    }

    private func baselineAttention(_ fixture: Fixture) -> MLXArray {
        lagunaFullPairGateAttention(
            rawQueries: fixture.rawQueries,
            rawKeys: fixture.rawKeys,
            rawValues: fixture.rawValues,
            queryWeight: fixture.queryWeight,
            keyWeight: fixture.keyWeight,
            angles: fixture.angles,
            cacheKeys: fixture.cacheKeys,
            cacheValues: fixture.cacheValues,
            writeIdx: fixture.writeIdx,
            scale: fixture.scale
        )
    }

    private func candidateAttention(_ fixture: Fixture) -> MLXArray {
        lagunaFullFusedAttention(
            rawQueries: fixture.rawQueries,
            rawKeys: fixture.rawKeys,
            rawValues: fixture.rawValues,
            queryWeight: fixture.queryWeight,
            keyWeight: fixture.keyWeight,
            angles: fixture.angles,
            cacheKeys: fixture.cacheKeys,
            cacheValues: fixture.cacheValues,
            writeIdx: fixture.writeIdx,
            scale: fixture.scale
        )
    }

    private func bits(_ array: MLXArray) -> [UInt16] {
        array.view(dtype: .uint16).asArray(UInt16.self)
    }

    private func firstMismatch(_ lhs: [UInt16], _ rhs: [UInt16]) -> Int? {
        guard lhs.count == rhs.count else { return min(lhs.count, rhs.count) }
        for index in lhs.indices where lhs[index] != rhs[index] {
            return index
        }
        return nil
    }

    private struct TimingResult {
        let baselineSeconds: Double
        let candidateSeconds: Double
        let speedup: Double
    }

    private func pairedTiming(
        baseline: Fixture,
        candidate: Fixture,
        baselineFirst: Bool,
        iterations: Int,
        rounds: Int
    ) -> TimingResult {
        var baselineDurations: [Double] = []
        var candidateDurations: [Double] = []
        for _ in 0 ..< rounds {
            if baselineFirst {
                baselineDurations.append(
                    duration(iterations: iterations) { baselineAttention(baseline) }
                )
                candidateDurations.append(
                    duration(iterations: iterations) { candidateAttention(candidate) }
                )
            } else {
                candidateDurations.append(
                    duration(iterations: iterations) { candidateAttention(candidate) }
                )
                baselineDurations.append(
                    duration(iterations: iterations) { baselineAttention(baseline) }
                )
            }
        }
        let baselineMedian = median(baselineDurations)
        let candidateMedian = median(candidateDurations)
        return TimingResult(
            baselineSeconds: baselineMedian,
            candidateSeconds: candidateMedian,
            speedup: baselineMedian / candidateMedian
        )
    }

    private func duration(iterations: Int, operation: () -> MLXArray) -> Double {
        let start = Date.timeIntervalSinceReferenceDate
        for _ in 0 ..< iterations {
            eval(operation())
        }
        return Date.timeIntervalSinceReferenceDate - start
    }

    private func median(_ values: [Double]) -> Double {
        values.sorted()[values.count / 2]
    }

    private func printTiming(
        _ order: String,
        _ result: TimingResult,
        iterations: Int,
        rounds: Int
    ) {
        print(
            "GATE0 order=\(order) baseline_seconds=\(result.baselineSeconds) "
                + "candidate_seconds=\(result.candidateSeconds) "
                + "speedup=\(result.speedup) iterations=\(iterations) rounds=\(rounds)"
        )
    }
}
