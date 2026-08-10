import Foundation
import MLX
import MLXNN
import Testing
@testable import MLXFastModel

@Suite(.serialized)
struct LagunaZeroCorrectionBiasResearchTests {
    private let experts = LagunaConstants.numExperts
    private let hidden = LagunaConstants.hiddenSize

    private func requireResearchRun() -> Bool {
        ProcessInfo.processInfo.environment["MLXFAST_RUN_ZERO_BIAS_RESEARCH"] == "1"
    }

    private func floatWords(_ array: MLXArray) -> [UInt32] {
        array.view(dtype: .uint32).asArray(UInt32.self)
    }

    private func bfloatWords(_ array: MLXArray) -> [UInt16] {
        array.view(dtype: .uint16).asArray(UInt16.self)
    }

    private func median(_ values: [Double]) -> Double {
        let sorted = values.sorted()
        let middle = sorted.count / 2
        return sorted.count.isMultiple(of: 2)
            ? (sorted[middle - 1] + sorted[middle]) / 2
            : sorted[middle]
    }

    private struct Generator {
        var state: UInt64

        mutating func index(upperBound: Int) -> Int {
            state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
            return Int((state >> 32) % UInt64(upperBound))
        }
    }

    private func bootstrapSpeedupCI(
        generic: [Double], zeroBias: [Double], iterations: Int = 10_000
    ) -> [Double] {
        var generator = Generator(state: 0x5a17_2026_0810_ceda)
        var ratios = [Double]()
        ratios.reserveCapacity(iterations)
        for _ in 0..<iterations {
            let genericSample = generic.indices.map { _ in
                generic[generator.index(upperBound: generic.count)]
            }
            let zeroBiasSample = zeroBias.indices.map { _ in
                zeroBias[generator.index(upperBound: zeroBias.count)]
            }
            ratios.append(median(genericSample) / median(zeroBiasSample))
        }
        ratios.sort()
        return [ratios[iterations / 40], ratios[iterations * 39 / 40]]
    }

    private func updateBias(_ bias: MLXArray, gate: LagunaRuntimeMoEGate) throws {
        try gate.update(
            parameters: ModuleParameters.unflattened([
                "e_score_correction_bias": bias
            ]),
            verify: .none
        )
    }

    private func requireSameRouterOutput(
        _ lhs: (MLXArray, MLXArray), _ rhs: (MLXArray, MLXArray)
    ) throws {
        eval(lhs.0, lhs.1, rhs.0, rhs.1)
        try #require(floatWords(lhs.0) == floatWords(rhs.0))
        try #require(floatWords(lhs.1) == floatWords(rhs.1))
    }

    private func verifyCertificateLifecycle(_ config: LagunaConfig) throws {
        let gate = LagunaRuntimeMoEGate(config)
        let positiveZero = MLXArray([Float](repeating: 0, count: experts))
        let negativeZero = MLXArray(
            [Float](repeating: Float(bitPattern: 0x8000_0000), count: experts))
        var nonzeroValues = [Float](repeating: 0, count: experts)
        nonzeroValues[17] = 0.25
        var nanValues = [Float](repeating: 0, count: experts)
        nanValues[19] = .nan

        try #require(!gate.correctionBiasIsPositiveZero)
        try updateBias(positiveZero, gate: gate)
        try #require(!gate.correctionBiasIsPositiveZero)
        gate.prepareCorrectionBiasSpecialization()
        try #require(gate.correctionBiasIsPositiveZero)

        try updateBias(positiveZero, gate: gate)
        try #require(!gate.correctionBiasIsPositiveZero)
        gate.prepareCorrectionBiasSpecialization()
        try #require(gate.correctionBiasIsPositiveZero)

        for rejected in [
            negativeZero,
            MLXArray(nonzeroValues),
            MLXArray(nanValues),
            positiveZero.asType(.bfloat16),
            MLXArray([Float](repeating: 0, count: experts)).reshaped(1, experts),
        ] {
            try updateBias(rejected, gate: gate)
            try #require(!gate.correctionBiasIsPositiveZero)
            gate.prepareCorrectionBiasSpecialization()
            try #require(!gate.correctionBiasIsPositiveZero)
        }
    }

    private func verifyTournamentParity() throws -> Int {
        let positiveZero = MLXArray([Float](repeating: 0, count: experts))
        let smooth = (0..<experts).map { Float(($0 * 37) % 113 - 56) / 9 }
        let tied = [Float](repeating: 0, count: experts)
        let signedZero = (0..<experts).map {
            $0.isMultiple(of: 2) ? Float.zero : Float(bitPattern: 0x8000_0000)
        }
        let extreme = (0..<experts).map {
            $0.isMultiple(of: 2) ? Float.greatestFiniteMagnitude : -Float.greatestFiniteMagnitude
        }
        let infinite = (0..<experts).map {
            $0.isMultiple(of: 2) ? Float.infinity : -Float.infinity
        }
        let nan = (0..<experts).map { index in
            index.isMultiple(of: 17) ? Float.nan : Float(index - 128) / 7
        }
        let cases = [smooth, tied, signedZero, extreme, infinite, nan]
        var comparisons = 0

        for values in cases {
            for dtype in [DType.float32, .bfloat16] {
                let logits = MLXArray(values, [1, 1, experts]).asType(dtype)
                for normalizing in [false, true] {
                    let generic = lagunaPrefillRouterTournamentOrdinalForTesting(
                        logits: logits,
                        correctionBias: positiveZero,
                        rows: 1,
                        normalizing: normalizing
                    )
                    let specialized = lagunaPrefillRouterTournamentOrdinalForTesting(
                        logits: logits,
                        correctionBias: positiveZero,
                        rows: 1,
                        normalizing: normalizing,
                        zeroCorrectionBias: true
                    )
                    try requireSameRouterOutput(generic, specialized)
                    comparisons += 1
                }
            }
        }

        let rows = 512
        let batchedValues = (0..<(rows * experts)).map {
            Float(($0 * 29 + $0 / experts * 7) % 127 - 63) / 11
        }
        for dtype in [DType.float32, .bfloat16] {
            let logits = MLXArray(batchedValues, [1, rows, experts]).asType(dtype)
            for normalizing in [false, true] {
                let generic = lagunaPrefillRouterTournamentOrdinalForTesting(
                    logits: logits,
                    correctionBias: positiveZero,
                    rows: rows,
                    normalizing: normalizing
                )
                let specialized = lagunaPrefillRouterTournamentOrdinalForTesting(
                    logits: logits,
                    correctionBias: positiveZero,
                    rows: rows,
                    normalizing: normalizing,
                    zeroCorrectionBias: true
                )
                try requireSameRouterOutput(generic, specialized)
                comparisons += 1
            }
        }
        return comparisons
    }

    private func makeFusedInputs() -> (
        MLXArray, MLXArray, MLXArray, MLXArray, MLXArray
    ) {
        let residual = MLXArray((0..<hidden).map {
            Float(($0 * 13) % 97 - 48) / 16
        }, [1, 1, hidden]).asType(.bfloat16)
        let branch = MLXArray((0..<hidden).map {
            Float(($0 * 19 + 3) % 89 - 44) / 32
        }, [1, 1, hidden]).asType(.bfloat16)
        let weight = MLXArray((0..<hidden).map {
            Float(96 + ($0 * 7) % 33) / 112
        }).asType(.bfloat16)
        let routerWeight = MLXArray((0..<(experts * hidden)).map {
            Float(($0 * 23 + $0 / hidden * 11) % 61 - 30) / 128
        }, [experts, hidden]).asType(.bfloat16)
        let bias = MLXArray([Float](repeating: 0, count: experts))
        return (residual, branch, weight, routerWeight, bias)
    }

    private func verifyFusedParity(
        inputs: (MLXArray, MLXArray, MLXArray, MLXArray, MLXArray)
    ) throws {
        let generic = lagunaResidualRMSNormRouter(
            residual: inputs.0,
            branch: inputs.1,
            weight: inputs.2,
            routerWeight: inputs.3,
            correctionBias: inputs.4
        )
        let specialized = lagunaResidualRMSNormRouter(
            residual: inputs.0,
            branch: inputs.1,
            weight: inputs.2,
            routerWeight: inputs.3,
            correctionBias: inputs.4,
            zeroCorrectionBias: true
        )
        let genericKeys = try #require(generic.routerKeys)
        let specializedKeys = try #require(specialized.routerKeys)
        eval(
            generic.summed, generic.normalized, generic.routerLogits, genericKeys,
            specialized.summed, specialized.normalized, specialized.routerLogits,
            specializedKeys
        )
        try #require(bfloatWords(generic.summed) == bfloatWords(specialized.summed))
        try #require(bfloatWords(generic.normalized) == bfloatWords(specialized.normalized))
        try #require(bfloatWords(generic.routerLogits) == bfloatWords(specialized.routerLogits))
        try #require(floatWords(genericKeys) == floatWords(specializedKeys))
    }

    private func verifyFallbacks(_ config: LagunaConfig) throws -> Int {
        let rows = 2
        let logits = MLXArray((0..<(rows * experts)).map {
            Float(($0 * 31) % 101 - 50) / 8
        }, [1, rows, experts]).asType(.bfloat16)
        let x = MLXArray([Float](repeating: 0, count: rows * hidden), [1, rows, hidden])
            .asType(.bfloat16)
        var nonzero = [Float](repeating: 0, count: experts)
        nonzero[255] = 100
        var nan = [Float](repeating: 0, count: experts)
        nan[31] = .nan
        let biases = [
            MLXArray([Float](repeating: Float(bitPattern: 0x8000_0000), count: experts)),
            MLXArray(nonzero),
            MLXArray(nan),
        ]
        var comparisons = 0

        for bias in biases {
            let gate = LagunaRuntimeMoEGate(config)
            try updateBias(bias, gate: gate)
            gate.prepareCorrectionBiasSpecialization()
            try #require(!gate.correctionBiasIsPositiveZero)
            let actual = gate(x, logits: logits)
            let expected = lagunaPrefillRouterTournamentOrdinalForTesting(
                logits: logits,
                correctionBias: bias,
                rows: rows,
                normalizing: config.normTopkProb
            )
            try requireSameRouterOutput(actual, expected)
            comparisons += 1
        }

        let zeroBias = MLXArray([Float](repeating: 0, count: experts))
        let zeroOutput = lagunaPrefillRouterTournamentOrdinalForTesting(
            logits: logits,
            correctionBias: zeroBias,
            rows: rows,
            normalizing: config.normTopkProb
        )
        let corruptedOutput = lagunaPrefillRouterTournamentOrdinalForTesting(
            logits: logits,
            correctionBias: biases[1],
            rows: rows,
            normalizing: config.normTopkProb
        )
        eval(zeroOutput.0, corruptedOutput.0)
        try #require(floatWords(zeroOutput.0) != floatWords(corruptedOutput.0))
        return comparisons
    }

    private func timeTournament(
        logits: MLXArray, bias: MLXArray, zeroBias: Bool
    ) -> Double {
        let start = DispatchTime.now().uptimeNanoseconds
        var outputs = [MLXArray]()
        outputs.reserveCapacity(38 * 2)
        for _ in 0..<38 {
            let output = lagunaPrefillRouterTournamentOrdinalForTesting(
                logits: logits,
                correctionBias: bias,
                rows: 512,
                normalizing: true,
                zeroCorrectionBias: zeroBias
            )
            outputs.append(output.0)
            outputs.append(output.1)
        }
        eval(outputs)
        let end = DispatchTime.now().uptimeNanoseconds
        return Double(end - start) / 1_000
    }

    private func timeDecodeChain(
        inputs: (MLXArray, MLXArray, MLXArray, MLXArray, MLXArray),
        zeroBias: Bool
    ) -> Double {
        let start = DispatchTime.now().uptimeNanoseconds
        var outputs = [MLXArray]()
        outputs.reserveCapacity(39 * 6)
        for _ in 0..<39 {
            let fused = lagunaResidualRMSNormRouter(
                residual: inputs.0,
                branch: inputs.1,
                weight: inputs.2,
                routerWeight: inputs.3,
                correctionBias: inputs.4,
                zeroCorrectionBias: zeroBias
            )
            let selected = lagunaPrefillRouterTournamentOrdinalForTesting(
                logits: fused.routerLogits,
                correctionBias: inputs.4,
                rows: 1,
                normalizing: true,
                zeroCorrectionBias: zeroBias
            )
            outputs.append(fused.summed)
            outputs.append(fused.normalized)
            outputs.append(fused.routerLogits)
            if let keys = fused.routerKeys {
                outputs.append(keys)
            }
            outputs.append(selected.0)
            outputs.append(selected.1)
        }
        eval(outputs)
        let end = DispatchTime.now().uptimeNanoseconds
        return Double(end - start) / 1_000
    }

    private func balancedSamples(_ measure: (Bool) -> Double) -> (
        generic: [Double], zeroBias: [Double]
    ) {
        for _ in 0..<4 {
            _ = measure(false)
            _ = measure(true)
        }
        var generic = [Double]()
        var zeroBias = [Double]()
        for block in 0..<8 {
            let order = block.isMultiple(of: 2)
                ? [false, true, true, false]
                : [true, false, false, true]
            for specialized in order {
                let sample = measure(specialized)
                if specialized {
                    zeroBias.append(sample)
                } else {
                    generic.append(sample)
                }
            }
        }
        return (generic, zeroBias)
    }

    @Test
    func zeroCorrectionBiasLifecycleParityAndTiming() throws {
        guard requireResearchRun() else { return }

        let config = try loadLagunaConfig(pinnedLagunaConfigObject())
        try verifyCertificateLifecycle(config)
        let tournamentComparisons = try verifyTournamentParity()
        let fusedInputs = makeFusedInputs()
        try verifyFusedParity(inputs: fusedInputs)
        let fallbackComparisons = try verifyFallbacks(config)

        let rows = 512
        let timingLogits = MLXArray((0..<(rows * experts)).map {
            Float(($0 * 43 + $0 / experts * 5) % 137 - 68) / 12
        }, [1, rows, experts]).asType(.bfloat16)
        let tournament = balancedSamples {
            timeTournament(logits: timingLogits, bias: fusedInputs.4, zeroBias: $0)
        }
        let decode = balancedSamples {
            timeDecodeChain(inputs: fusedInputs, zeroBias: $0)
        }

        let tournamentGenericMedian = median(tournament.generic)
        let tournamentZeroMedian = median(tournament.zeroBias)
        let decodeGenericMedian = median(decode.generic)
        let decodeZeroMedian = median(decode.zeroBias)
        let tournamentSpeedup = tournamentGenericMedian / tournamentZeroMedian
        let decodeSpeedup = decodeGenericMedian / decodeZeroMedian
        let baselineDecodeSecondsPerToken = 0.0130094560546875
        let baselinePrefillSecondsPerToken = 0.00111160807421875
        let decodeDeltaSeconds = (decodeGenericMedian - decodeZeroMedian) / 1_000_000
        let prefillDeltaSeconds = (tournamentGenericMedian - tournamentZeroMedian) / 1_000_000
        let projectedDecodeSpeedup = baselineDecodeSecondsPerToken
            / (baselineDecodeSecondsPerToken - decodeDeltaSeconds)
        let baselinePrefillTotal = baselinePrefillSecondsPerToken * Double(rows)
        let projectedPrefillSpeedup = baselinePrefillTotal
            / (baselinePrefillTotal - prefillDeltaSeconds)
        let projectedScoreSpeedup = pow(projectedDecodeSpeedup, 0.75)
            * pow(projectedPrefillSpeedup, 0.25)

        let result: [String: Any] = [
            "schema_version": 1,
            "host": "M4 Pro 48GB",
            "orders": ["ABBA", "BAAB"],
            "samples_per_arm": tournament.generic.count,
            "correctness": [
                "certificate_cases": 7,
                "tournament_bitwise_comparisons": tournamentComparisons,
                "fused_bitwise_comparisons": 4,
                "fallback_bitwise_comparisons": fallbackComparisons,
                "corruption_control": true,
            ],
            "tournament_38x512": [
                "generic_us": tournament.generic,
                "zero_bias_us": tournament.zeroBias,
                "generic_median_us": tournamentGenericMedian,
                "zero_bias_median_us": tournamentZeroMedian,
                "speedup": tournamentSpeedup,
                "speedup_bootstrap_95ci": bootstrapSpeedupCI(
                    generic: tournament.generic, zeroBias: tournament.zeroBias),
            ],
            "decode_39_stage_fused_plus_selector": [
                "generic_us": decode.generic,
                "zero_bias_us": decode.zeroBias,
                "generic_median_us": decodeGenericMedian,
                "zero_bias_median_us": decodeZeroMedian,
                "speedup": decodeSpeedup,
                "speedup_bootstrap_95ci": bootstrapSpeedupCI(
                    generic: decode.generic, zeroBias: decode.zeroBias),
            ],
            "projection_from_local_baseline": [
                "baseline_decode_seconds_per_token": baselineDecodeSecondsPerToken,
                "baseline_prefill_seconds_per_token": baselinePrefillSecondsPerToken,
                "decode_speedup": projectedDecodeSpeedup,
                "prefill_speedup": projectedPrefillSpeedup,
                "score_speedup": projectedScoreSpeedup,
            ],
        ]
        let data = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
        print("ZERO_BIAS_RESEARCH_RESULT \(String(decoding: data, as: UTF8.self))")
    }
}
