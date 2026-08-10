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

    private func makeFusedInputs() -> (
        MLXArray, MLXArray, MLXArray, MLXArray, MLXArray
    ) {
        let residualValues: [Float] = (0..<hidden).map { index in
            Float((index * 13) % 97 - 48) / 16
        }
        let branchValues: [Float] = (0..<hidden).map { index in
            Float((index * 19 + 3) % 89 - 44) / 32
        }
        let weightValues: [Float] = (0..<hidden).map { index in
            Float(96 + (index * 7) % 33) / 112
        }
        let routerWeightValues: [Float] = (0..<(experts * hidden)).map { index in
            Float((index * 23 + index / hidden * 11) % 61 - 30) / 128
        }
        let residual = MLXArray(residualValues, [1, 1, hidden]).asType(.bfloat16)
        let branch = MLXArray(branchValues, [1, 1, hidden]).asType(.bfloat16)
        let weight = MLXArray(weightValues).asType(.bfloat16)
        let routerWeight = MLXArray(routerWeightValues, [experts, hidden]).asType(.bfloat16)
        let bias = MLXArray([Float](repeating: 0, count: experts))
        return (residual, branch, weight, routerWeight, bias)
    }

    private func requireSameFusedOutput(
        _ lhs: (summed: MLXArray, normalized: MLXArray, routerLogits: MLXArray,
            routerKeys: MLXArray?),
        _ rhs: (summed: MLXArray, normalized: MLXArray, routerLogits: MLXArray,
            routerKeys: MLXArray?)
    ) throws {
        let lhsKeys = try #require(lhs.routerKeys)
        let rhsKeys = try #require(rhs.routerKeys)
        eval(
            lhs.summed, lhs.normalized, lhs.routerLogits, lhsKeys,
            rhs.summed, rhs.normalized, rhs.routerLogits, rhsKeys
        )
        try #require(bfloatWords(lhs.summed) == bfloatWords(rhs.summed))
        try #require(bfloatWords(lhs.normalized) == bfloatWords(rhs.normalized))
        try #require(bfloatWords(lhs.routerLogits) == bfloatWords(rhs.routerLogits))
        try #require(floatWords(lhsKeys) == floatWords(rhsKeys))
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
        try requireSameFusedOutput(generic, specialized)
    }

    private func verifyFallbacks(
        _ config: LagunaConfig,
        inputs: (MLXArray, MLXArray, MLXArray, MLXArray, MLXArray)
    ) throws -> Int {
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
            let actual = lagunaResidualRMSNormRouter(
                residual: inputs.0,
                branch: inputs.1,
                weight: inputs.2,
                routerWeight: inputs.3,
                correctionBias: bias,
                zeroCorrectionBias: gate.correctionBiasIsPositiveZero
            )
            let expected = lagunaResidualRMSNormRouter(
                residual: inputs.0,
                branch: inputs.1,
                weight: inputs.2,
                routerWeight: inputs.3,
                correctionBias: bias
            )
            try requireSameFusedOutput(actual, expected)
            comparisons += 1
        }

        let generic = lagunaResidualRMSNormRouter(
            residual: inputs.0,
            branch: inputs.1,
            weight: inputs.2,
            routerWeight: inputs.3,
            correctionBias: biases[1]
        )
        let forcedZero = lagunaResidualRMSNormRouter(
            residual: inputs.0,
            branch: inputs.1,
            weight: inputs.2,
            routerWeight: inputs.3,
            correctionBias: biases[1],
            zeroCorrectionBias: true
        )
        let genericKeys = try #require(generic.routerKeys)
        let forcedZeroKeys = try #require(forcedZero.routerKeys)
        eval(genericKeys, forcedZeroKeys)
        try #require(floatWords(genericKeys) != floatWords(forcedZeroKeys))
        return comparisons
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
                normalizing: true
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

    private func orderedSamples(
        order: [Bool],
        measure: (Bool) -> Double
    ) -> (generic: [Double], zeroBias: [Double]) {
        for _ in 0..<4 {
            _ = measure(false)
            _ = measure(true)
        }
        var generic = [Double]()
        var zeroBias = [Double]()
        for _ in 0..<8 {
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
    func zeroCorrectionBiasDecodeOnlyLifecycleParityAndTiming() throws {
        guard requireResearchRun() else { return }

        let config = try loadLagunaConfig(pinnedLagunaConfigObject())
        try verifyCertificateLifecycle(config)
        let fusedInputs = makeFusedInputs()
        try verifyFusedParity(inputs: fusedInputs)
        let fallbackComparisons = try verifyFallbacks(config, inputs: fusedInputs)

        let abba = orderedSamples(order: [false, true, true, false]) {
            timeDecodeChain(inputs: fusedInputs, zeroBias: $0)
        }
        let baab = orderedSamples(order: [true, false, false, true]) {
            timeDecodeChain(inputs: fusedInputs, zeroBias: $0)
        }
        let pooledGeneric = abba.generic + baab.generic
        let pooledZeroBias = abba.zeroBias + baab.zeroBias
        let pooledGenericMedian = median(pooledGeneric)
        let pooledZeroBiasMedian = median(pooledZeroBias)
        let baselineDecodeSecondsPerToken = 0.0130094560546875
        let decodeDeltaSeconds = (pooledGenericMedian - pooledZeroBiasMedian) / 1_000_000
        let projectedDecodeSpeedup = baselineDecodeSecondsPerToken
            / (baselineDecodeSecondsPerToken - decodeDeltaSeconds)
        let projectedPrefillSpeedup = 1.0
        let projectedScoreSpeedup = pow(projectedDecodeSpeedup, 0.75)

        let result: [String: Any] = [
            "schema_version": 2,
            "host": "M4 Pro 48GB",
            "orders": ["ABBA", "BAAB"],
            "samples_per_arm_per_order": abba.generic.count,
            "expected_scored_dispatches": [
                "decode": 39 * 128,
                "prefill": 0,
            ],
            "correctness": [
                "certificate_cases": 7,
                "fused_bitwise_comparisons": 4,
                "fallback_bitwise_comparisons": fallbackComparisons,
                "corruption_control": true,
            ],
            "decode_39_stage_fused_plus_stock_selector": [
                "ABBA": [
                    "generic_us": abba.generic,
                    "zero_bias_us": abba.zeroBias,
                    "generic_median_us": median(abba.generic),
                    "zero_bias_median_us": median(abba.zeroBias),
                    "speedup": median(abba.generic) / median(abba.zeroBias),
                    "speedup_bootstrap_95ci": bootstrapSpeedupCI(
                        generic: abba.generic, zeroBias: abba.zeroBias),
                ],
                "BAAB": [
                    "generic_us": baab.generic,
                    "zero_bias_us": baab.zeroBias,
                    "generic_median_us": median(baab.generic),
                    "zero_bias_median_us": median(baab.zeroBias),
                    "speedup": median(baab.generic) / median(baab.zeroBias),
                    "speedup_bootstrap_95ci": bootstrapSpeedupCI(
                        generic: baab.generic, zeroBias: baab.zeroBias),
                ],
                "pooled": [
                    "generic_us": pooledGeneric,
                    "zero_bias_us": pooledZeroBias,
                    "generic_median_us": pooledGenericMedian,
                    "zero_bias_median_us": pooledZeroBiasMedian,
                    "speedup": pooledGenericMedian / pooledZeroBiasMedian,
                    "speedup_bootstrap_95ci": bootstrapSpeedupCI(
                        generic: pooledGeneric, zeroBias: pooledZeroBias),
                ],
            ],
            "projection_from_local_baseline": [
                "baseline_decode_seconds_per_token": baselineDecodeSecondsPerToken,
                "decode_speedup": projectedDecodeSpeedup,
                "prefill_speedup": projectedPrefillSpeedup,
                "score_speedup": projectedScoreSpeedup,
            ],
        ]
        let data = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
        print("ZERO_BIAS_RESEARCH_RESULT \(String(decoding: data, as: UTF8.self))")
    }
}
