import Dispatch
import Foundation
import MLX
import Testing
@testable import MLXFastModel

@Suite(.serialized)
struct PrefillResidualRMSRPG4Tests {
    private let width = 2_048

    private func inputs(rows: Int) -> (MLXArray, MLXArray, MLXArray) {
        let count = rows * width
        let residual = MLXArray(
            (0..<count).map { Float(($0 % 257) - 128) / 256 },
            [1, rows, width]
        ).asType(.bfloat16)
        let branch = MLXArray(
            (0..<count).map { Float(($0 % 131) - 65) / 192 },
            [1, rows, width]
        ).asType(.bfloat16)
        let weight = MLXArray(
            (0..<width).map { 0.75 + Float($0 % 37) / 128 },
            [width]
        ).asType(.bfloat16)
        return (residual, branch, weight)
    }

    private func bfloat16Array(bits: [UInt16], shape: [Int]) -> MLXArray {
        let data = bits.withUnsafeBytes { Data($0) }
        return MLXArray(data, shape, dtype: .bfloat16)
    }

    private func exactBytes(_ array: MLXArray) -> Data {
        array.asData(access: .copy).data
    }

    private func expectExactMatch(rows: Int) {
        let (residual, branch, weight) = inputs(rows: rows)
        let reference = lagunaResidualRMSNorm(
            residual: residual,
            branch: branch,
            weight: weight
        )
        let candidate = lagunaPrefillResidualRMSNorm(
            residual: residual,
            branch: branch,
            weight: weight
        )
        eval(reference.0, reference.1, candidate.0, candidate.1)
        #expect(exactBytes(reference.0) == exactBytes(candidate.0))
        #expect(exactBytes(reference.1) == exactBytes(candidate.1))
    }

    @Test
    func correctnessRoutingAndSpecialValues() {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
            return
        }

        let ablationDisabled = ProcessInfo.processInfo.environment[
            "DARKBLOOM_PREFILL_RESIDUAL_RMS_RPG4"
        ] == "0"
        let selectedRows = [4, 8, 512]
        let fallbackRows = [1, 2, 3, 5, 511, 513]

        for rows in selectedRows {
            #expect(lagunaPrefillResidualRMSNormUsesRPG4(rows: rows) == !ablationDisabled)
            expectExactMatch(rows: rows)
        }
        for rows in fallbackRows {
            #expect(!lagunaPrefillResidualRMSNormUsesRPG4(rows: rows))
            expectExactMatch(rows: rows)
        }

        let prefillCalls = (0..<39).filter {
            lagunaPrefillResidualRMSNormUsesRPG4(rows: 512)
        }.count
        let decodeCalls = (0..<39).filter {
            lagunaPrefillResidualRMSNormUsesRPG4(rows: 1)
        }.count
        #expect(prefillCalls == (ablationDisabled ? 0 : 39))
        #expect(decodeCalls == 0)
        if !ablationDisabled {
            #expect(prefillCalls * (512 / 4) == 4_992)
            #expect(prefillCalls * 512 == 19_968)
        }

        let patterns: [UInt16] = [
            0x0000, 0x8000, 0x0001, 0x8001,
            0x007f, 0x0080, 0x3f80, 0xbf80,
            0x7f7f, 0xff7f, 0x7f80, 0xff80,
            0x7fc1, 0xffc1,
        ]
        let count = 4 * width
        let residualBits = (0..<count).map { patterns[$0 % patterns.count] }
        let branchBits = (0..<count).map { patterns[($0 * 5 + 3) % patterns.count] }
        let weightBits = (0..<width).map { patterns[($0 * 3 + 6) % patterns.count] }
        let residual = bfloat16Array(bits: residualBits, shape: [1, 4, width])
        let branch = bfloat16Array(bits: branchBits, shape: [1, 4, width])
        let weight = bfloat16Array(bits: weightBits, shape: [width])
        let reference = lagunaResidualRMSNorm(
            residual: residual,
            branch: branch,
            weight: weight
        )
        let candidate = lagunaPrefillResidualRMSNorm(
            residual: residual,
            branch: branch,
            weight: weight
        )
        eval(reference.0, reference.1, candidate.0, candidate.1)
        let referenceResidual = exactBytes(reference.0)
        let referenceNormalized = exactBytes(reference.1)
        #expect(referenceResidual == exactBytes(candidate.0))
        #expect(referenceNormalized == exactBytes(candidate.1))

        var corrupted = referenceNormalized
        corrupted[corrupted.startIndex] ^= 1
        #expect(corrupted != referenceNormalized)
    }

    private enum Variant {
        case reference
        case rpg4
    }

    private func measure(
        _ variant: Variant,
        residual: MLXArray,
        branch: MLXArray,
        weight: MLXArray
    ) -> UInt64 {
        let start = DispatchTime.now().uptimeNanoseconds
        let outputs: (MLXArray, MLXArray)
        switch variant {
        case .reference:
            outputs = lagunaResidualRMSNorm(
                residual: residual,
                branch: branch,
                weight: weight
            )
        case .rpg4:
            outputs = lagunaPrefillResidualRMSNorm(
                residual: residual,
                branch: branch,
                weight: weight
            )
        }
        eval(outputs.0, outputs.1)
        return DispatchTime.now().uptimeNanoseconds - start
    }

    private func runOrdering(
        _ ordering: [Variant],
        repetitions: Int,
        residual: MLXArray,
        branch: MLXArray,
        weight: MLXArray
    ) -> (referenceNanoseconds: UInt64, rpg4Nanoseconds: UInt64, calls: Int) {
        var referenceNanoseconds: UInt64 = 0
        var rpg4Nanoseconds: UInt64 = 0
        var referenceCalls = 0
        var rpg4Calls = 0
        for _ in 0..<repetitions {
            for variant in ordering {
                let elapsed = measure(
                    variant,
                    residual: residual,
                    branch: branch,
                    weight: weight
                )
                switch variant {
                case .reference:
                    referenceNanoseconds += elapsed
                    referenceCalls += 1
                case .rpg4:
                    rpg4Nanoseconds += elapsed
                    rpg4Calls += 1
                }
            }
        }
        #expect(referenceCalls == rpg4Calls)
        return (referenceNanoseconds, rpg4Nanoseconds, referenceCalls)
    }

    @Test
    func isolatedTimingGate() {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_RPG4_TIMING"] == "1" else {
            return
        }
        #expect(lagunaPrefillResidualRMSNormUsesRPG4(rows: 512))

        let (residual, branch, weight) = inputs(rows: 512)
        for _ in 0..<16 {
            _ = measure(.reference, residual: residual, branch: branch, weight: weight)
            _ = measure(.rpg4, residual: residual, branch: branch, weight: weight)
        }

        let repetitions = 256
        let abba = runOrdering(
            [.reference, .rpg4, .rpg4, .reference],
            repetitions: repetitions,
            residual: residual,
            branch: branch,
            weight: weight
        )
        let baab = runOrdering(
            [.rpg4, .reference, .reference, .rpg4],
            repetitions: repetitions,
            residual: residual,
            branch: branch,
            weight: weight
        )
        let abbaSpeedup = Double(abba.referenceNanoseconds) / Double(abba.rpg4Nanoseconds)
        let baabSpeedup = Double(baab.referenceNanoseconds) / Double(baab.rpg4Nanoseconds)
        let referenceMean = (
            Double(abba.referenceNanoseconds) / Double(abba.calls)
                + Double(baab.referenceNanoseconds) / Double(baab.calls)
        ) / 2
        let rpg4Mean = (
            Double(abba.rpg4Nanoseconds) / Double(abba.calls)
                + Double(baab.rpg4Nanoseconds) / Double(baab.calls)
        ) / 2
        let savedNanosecondsPerCall = referenceMean - rpg4Mean
        let baselinePrefillNanoseconds = 0.001124221923828125 * 512 * 1_000_000_000
        let projectedPrefillNanoseconds = baselinePrefillNanoseconds
            - 39 * savedNanosecondsPerCall
        let projectedPrefillSpeedup = baselinePrefillNanoseconds / projectedPrefillNanoseconds

        print(String(
            format: "RPG4_TIMING abba=%.9f baab=%.9f reference_ns=%.3f rpg4_ns=%.3f saved_ns=%.3f projected_prefill=%.9f repetitions=%d calls_per_variant_per_order=%d",
            abbaSpeedup,
            baabSpeedup,
            referenceMean,
            rpg4Mean,
            savedNanosecondsPerCall,
            projectedPrefillSpeedup,
            repetitions,
            abba.calls
        ))
        #expect(abbaSpeedup >= 1.005)
        #expect(baabSpeedup >= 1.005)
        #expect(projectedPrefillSpeedup >= 1.0005)
    }
}
