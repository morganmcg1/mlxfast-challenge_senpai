import Dispatch
import Foundation
import MLX
import MLXFast
@testable import MLXLMCommon
import Testing

private let physicalSidecarPrefixesKernel = MLXFast.metalKernel(
    name: "route_sorter_physical_sidecar_prefixes_test_v1",
    inputNames: ["sidecar"],
    outputNames: ["prefixes"],
    source: """
    uint offset = thread_position_in_grid.x;
    prefixes[offset] = sidecar[offset];
    """,
    ensureRowContiguous: false
)

@Suite(.serialized)
struct RouteSorterPropertyTemporaryTests {
    private let routeCount = 4096
    private let topK = 8
    private let width = 4

    @Test func persistentSidecarSorterPropertyMatrix() {
        let cases: [(String, [UInt32])] = [
            ("router-like", routerLike()),
            ("balanced", (0 ..< routeCount).map { UInt32($0 % 256) }),
            ("duplicate-heavy", (0 ..< routeCount).map { $0 % 10 == 0 ? UInt32($0 % 256) : 17 }),
            ("all-equal", Array(repeating: 91, count: routeCount)),
            ("zero-and-255", (0 ..< routeCount).map { $0.isMultiple(of: 3) ? 0 : 255 }),
            ("boundary-keys", boundaryKeys()),
            ("random", randomKeys(seed: 0x738C_EDA4)),
            ("reverse-blocks", (0 ..< routeCount).map { UInt32(255 - (($0 / 16) % 256)) }),
        ]

        for repetition in 0 ..< 20 {
            for (name, keys) in cases {
                check(keys: keys, name: name, repetition: repetition)
            }
        }
    }

    @Test func pairedSorterTiming() throws {
        let capturePath = "/tmp/f322-pr738-real-route-c3999cf6.csv"
        let capture = try String(contentsOfFile: capturePath, encoding: .utf8)
        let realKeys = capture.split { character in
            character == "," || character == "\n" || character == "\r"
                || character == " " || character == "\t"
        }.compactMap(UInt32.init)
        #expect(realKeys.count == routeCount)
        #expect(realKeys.allSatisfy { $0 < 256 })
        guard realKeys.count == routeCount, realKeys.allSatisfy({ $0 < 256 }) else {
            return
        }

        let distributions: [(name: String, indices: MLXArray)] = [
            ("real-route", MLXArray(realKeys)),
            ("balanced", MLXArray((0 ..< routeCount).map { UInt32($0 % 256) })),
            ("concentrated", MLXArray(Array(repeating: UInt32(17), count: routeCount))),
        ]
        let forward = F322RouteSorterTimingArm.allCases
        for distribution in distributions {
            for arm in forward {
                for _ in 0 ..< 20 {
                    evaluateSorter(distribution.indices, arm: arm)
                }
            }
        }

        let invocationsPerBlock = 128
        let cycles = 128
        var rawBlockNanoseconds: [String: [UInt64]] = [:]
        for cycle in 0 ..< cycles {
            let orderName = cycle.isMultiple(of: 2) ? "forward" : "reverse"
            let arms = cycle.isMultiple(of: 2) ? forward : Array(forward.reversed())
            for distribution in distributions {
                for arm in arms {
                    let elapsed = timeSorterBlock(
                        distribution.indices,
                        arm: arm,
                        invocations: invocationsPerBlock)
                    rawBlockNanoseconds[
                        timingKey(
                            distribution: distribution.name,
                            order: orderName,
                            arm: arm),
                        default: []
                    ].append(elapsed)
                }
            }
        }

        var summaries: [String: [String: Double]] = [:]
        for (key, samples) in rawBlockNanoseconds {
            let values = samples.map(Double.init)
            summaries[key] = [
                "median_ns": median(values),
                "mad_ns": medianAbsoluteDeviation(values),
                "min_ns": Double(samples.min() ?? 0),
                "max_ns": Double(samples.max() ?? 0),
            ]
        }

        var metrics: [String: [String: Double]] = [:]
        for distribution in distributions {
            let persistentSpeedup = pairedRatios(
                distribution: distribution.name,
                numerator: .stable32,
                denominator: .persistent1,
                raw: rawBlockNanoseconds)
            let unorderedSpeedup = pairedRatios(
                distribution: distribution.name,
                numerator: .stable32,
                denominator: .unordered32,
                raw: rawBlockNanoseconds)
            let persistentVersusUnordered = pairedRatios(
                distribution: distribution.name,
                numerator: .unordered32,
                denominator: .persistent1,
                raw: rawBlockNanoseconds)
            let persistentRegression = pairedRatios(
                distribution: distribution.name,
                numerator: .persistent1,
                denominator: .stable32,
                raw: rawBlockNanoseconds)
            metrics[distribution.name] = [
                "persistent_vs_stable_speedup_median": median(persistentSpeedup),
                "unordered_vs_stable_speedup_median": median(unorderedSpeedup),
                "persistent_vs_unordered_speedup_median": median(persistentVersusUnordered),
                "persistent_vs_stable_regression_median": median(persistentRegression) - 1,
            ]
        }

        let payload: [String: Any] = [
            "capture_path": capturePath,
            "capture_sha256": "04eb1bccf1016e61151ac3c58cf93fb24b0fb0c68444c56a850f14ad76357753",
            "route_count": routeCount,
            "warmups_per_arm_distribution": 20,
            "invocations_per_block": invocationsPerBlock,
            "cycles": cycles,
            "cycles_per_order": cycles / 2,
            "raw_block_ns": rawBlockNanoseconds,
            "summaries": summaries,
            "metrics": metrics,
        ]
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        print("F322_SORTER_TIMING_JSON=\(String(data: data, encoding: .utf8)!)")
    }

    private func evaluateSorter(_ indices: MLXArray, arm: F322RouteSorterTimingArm) {
        let result = f322RouteSorterTiming(indices, arm: arm)
        eval(result.rowOrder, result.sortedKeys, result.inverseOrder)
    }

    private func timeSorterBlock(
        _ indices: MLXArray,
        arm: F322RouteSorterTimingArm,
        invocations: Int
    ) -> UInt64 {
        let start = DispatchTime.now().uptimeNanoseconds
        for _ in 0 ..< invocations {
            evaluateSorter(indices, arm: arm)
        }
        return DispatchTime.now().uptimeNanoseconds - start
    }

    private func timingKey(
        distribution: String,
        order: String,
        arm: F322RouteSorterTimingArm
    ) -> String {
        "\(distribution)/\(order)/\(arm.rawValue)"
    }

    private func pairedRatios(
        distribution: String,
        numerator: F322RouteSorterTimingArm,
        denominator: F322RouteSorterTimingArm,
        raw: [String: [UInt64]]
    ) -> [Double] {
        ["forward", "reverse"].flatMap { order in
            let numeratorSamples = raw[
                timingKey(distribution: distribution, order: order, arm: numerator)] ?? []
            let denominatorSamples = raw[
                timingKey(distribution: distribution, order: order, arm: denominator)] ?? []
            return zip(numeratorSamples, denominatorSamples).map {
                Double($0.0) / Double($0.1)
            }
        }
    }

    private func median(_ values: [Double]) -> Double {
        guard !values.isEmpty else { return .nan }
        let sorted = values.sorted()
        let midpoint = sorted.count / 2
        if sorted.count.isMultiple(of: 2) {
            return (sorted[midpoint - 1] + sorted[midpoint]) / 2
        }
        return sorted[midpoint]
    }

    private func medianAbsoluteDeviation(_ values: [Double]) -> Double {
        let center = median(values)
        return median(values.map { abs($0 - center) })
    }

    private func check(keys: [UInt32], name: String, repetition: Int) {
        let rows = routeCount / topK
        let values = (0 ..< rows * width).map { Float(($0 * 17 + 3) % 1024) / 16 }
        let input = MLXArray(values).reshaped(1, rows, width).asType(.bfloat16)
        let x = MLX.expandedDimensions(input, axes: [-2, -3])
        let indices = MLXArray(keys).reshaped(1, rows, topK)
        let (sortedX, sidecar, inverse) = gatherSort(
            x: x, indices: indices, expertBoundsSidecar: true)
        let physicalPrefixes = physicalSidecarPrefixesKernel(
            [sidecar],
            grid: (257, 1, 1),
            threadGroup: (256, 1, 1),
            outputShapes: [[257]],
            outputDTypes: [.uint32]
        )[0]
        let restored = sortedX[inverse]
        eval(sortedX, physicalPrefixes, inverse, restored)

        var counts = Array(repeating: 0, count: 256)
        for key in keys {
            counts[Int(key)] += 1
        }
        var expectedPrefixes = Array(repeating: 0, count: 257)
        for expert in 0 ..< 256 {
            expectedPrefixes[expert + 1] = expectedPrefixes[expert] + counts[expert]
        }
        let prefixValues = physicalPrefixes.asArray(UInt32.self).map(Int.init)
        #expect(
            prefixValues == expectedPrefixes,
            "\(name) repetition \(repetition): physical prefix mismatch")

        let inverseValues = inverse.asArray(UInt32.self).map(Int.init)
        #expect(
            inverseValues.sorted() == Array(0 ..< routeCount),
            "\(name) repetition \(repetition): inverse is not a permutation")

        var sortedKeys = Array(repeating: -1, count: routeCount)
        for (inputOffset, outputOffset) in inverseValues.enumerated() {
            sortedKeys[outputOffset] = Int(keys[inputOffset])
        }
        for expert in 0 ..< 256 {
            #expect(
                sortedKeys[expectedPrefixes[expert] ..< expectedPrefixes[expert + 1]]
                    .allSatisfy { $0 == expert },
                "\(name) repetition \(repetition): expert segment mismatch")
        }

        let sourceBits = x.view(dtype: .uint16).asArray(UInt16.self)
        let sortedBits = sortedX.view(dtype: .uint16).asArray(UInt16.self)
        for (inputOffset, outputOffset) in inverseValues.enumerated() {
            let sourceRow = inputOffset / topK
            for column in 0 ..< width {
                let expected = sourceBits[sourceRow * width + column]
                #expect(
                    sortedBits[outputOffset * width + column] == expected,
                    "\(name) repetition \(repetition): gathered BF16 mismatch")
            }
        }

        let restoredBits = restored.view(dtype: .uint16).asArray(UInt16.self)
        for inputOffset in 0 ..< routeCount {
            let sourceRow = inputOffset / topK
            for column in 0 ..< width {
                let expected = sourceBits[sourceRow * width + column]
                #expect(
                    restoredBits[inputOffset * width + column] == expected,
                    "\(name) repetition \(repetition): restored BF16 mismatch")
            }
        }
    }

    private func routerLike() -> [UInt32] {
        (0 ..< routeCount).map { offset in
            let row = offset / topK
            let lane = offset % topK
            let hot = [3, 17, 29, 47, 71, 109, 173, 241]
            if (row + lane * 3).isMultiple(of: 5) {
                return UInt32(hot[(row + lane) % hot.count])
            }
            return UInt32((row * 73 + lane * 29 + row / 7) % 256)
        }
    }

    private func boundaryKeys() -> [UInt32] {
        let boundaries: [UInt32] = [0, 1, 31, 32, 63, 64, 127, 128, 254, 255]
        return (0 ..< routeCount).map { boundaries[($0 * 7 + $0 / 13) % boundaries.count] }
    }

    private func randomKeys(seed: UInt32) -> [UInt32] {
        var state = seed
        return (0 ..< routeCount).map { _ in
            state = state &* 1_664_525 &+ 1_013_904_223
            return state >> 24
        }
    }
}
