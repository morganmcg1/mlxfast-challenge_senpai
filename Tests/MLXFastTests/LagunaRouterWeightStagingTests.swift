import Foundation
import MLX
import Testing
@testable import MLXFastModel

@Test
func lagunaRouterWeightStagingIsBitwiseExactWhenRuntimeTestsAreEnabled() {
    guard routerStagingRuntimeTestsEnabled else {
        return
    }

    let fixture = makeRouterStagingFixture()
    let cases = [
        makeRouterStagingCase(
            seed: 3,
            indices: [0, 7, 42, 255, 3, 128, 17, 99],
            routerWeights: [
                0.037109375, 0.061523438, 0.08984375, 0.1171875,
                0.14257813, 0.17578125, 0.2109375, 0.1640625,
            ]
        ),
        makeRouterStagingCase(
            seed: 11,
            indices: [255, 128, 99, 42, 17, 7, 3, 0],
            routerWeights: [
                0.1001, 0.12549, 0.1509, 0.2003,
                0.0752, 0.1102, 0.0901, 0.1487,
            ]
        ),
        makeRouterStagingCase(
            seed: 29,
            indices: [5, 67, 129, 191, 253, 31, 97, 223],
            routerWeights: [
                0.000_123, 0.015_747, 0.031_373, 0.062_747,
                0.124_747, 0.249_49, 0.125_51, 0.390_263,
            ]
        ),
    ]

    var allExact = true
    for testCase in cases {
        eval(testCase.arrays)
        let control = routerStagingOutput(
            fixture: fixture,
            testCase: testCase,
            useUnstagedControl: true
        )
        let staged = routerStagingOutput(
            fixture: fixture,
            testCase: testCase,
            useUnstagedControl: false
        )
        eval(control, staged)

        let controlBytes = control.asData(access: .copy).data
        let stagedBytes = staged.asData(access: .copy).data
        let tailRange = (2_046 * 2)..<(2_048 * 2)
        let exact = controlBytes == stagedBytes
            && controlBytes.subdata(in: tailRange) == stagedBytes.subdata(in: tailRange)
        allExact = allExact && exact
        #expect(exact, Comment(rawValue: "router staging changed BF16 output bytes"))
    }

    print(
        "ROUTER_STAGING_ORACLE cases=\(cases.count) bytes_per_case=4096 "
            + "tail_rows=2046,2047 bitwise=\(allExact)"
    )
}

@Test
func lagunaRouterWeightStagingCompleteKernelTimingWhenEnabled() {
    guard routerStagingRuntimeTestsEnabled,
        ProcessInfo.processInfo.environment["MLXFAST_RUN_ROUTER_STAGING_BENCHMARK"] == "1"
    else {
        return
    }

    let fixture = makeRouterStagingFixture()
    let testCase = makeRouterStagingCase(
        seed: 17,
        indices: [0, 7, 42, 255, 3, 128, 17, 99],
        routerWeights: [
            0.1001, 0.12549, 0.1509, 0.2003,
            0.0752, 0.1102, 0.0901, 0.1487,
        ]
    )
    eval(testCase.arrays)
    eval(routerStagingOutput(fixture: fixture, testCase: testCase, useUnstagedControl: true))
    eval(routerStagingOutput(fixture: fixture, testCase: testCase, useUnstagedControl: false))

    let batchSize = 128
    let rounds = 11
    var abControl = [Double]()
    var abStaged = [Double]()
    var baControl = [Double]()
    var baStaged = [Double]()

    for _ in 0..<rounds {
        abControl.append(
            measureRouterStagingBatch(
                fixture: fixture,
                testCase: testCase,
                useUnstagedControl: true,
                count: batchSize
            )
        )
        abStaged.append(
            measureRouterStagingBatch(
                fixture: fixture,
                testCase: testCase,
                useUnstagedControl: false,
                count: batchSize
            )
        )
        baStaged.append(
            measureRouterStagingBatch(
                fixture: fixture,
                testCase: testCase,
                useUnstagedControl: false,
                count: batchSize
            )
        )
        baControl.append(
            measureRouterStagingBatch(
                fixture: fixture,
                testCase: testCase,
                useUnstagedControl: true,
                count: batchSize
            )
        )
    }

    let abControlMedian = median(abControl)
    let abStagedMedian = median(abStaged)
    let baControlMedian = median(baControl)
    let baStagedMedian = median(baStaged)
    let abSpeedup = abControlMedian / abStagedMedian
    let baSpeedup = baControlMedian / baStagedMedian

    print(
        String(
            format: "ROUTER_STAGING_TIMING rounds=%d batch=%d ab_control_ms=%.6f "
                + "ab_staged_ms=%.6f ab_speedup=%.6f ab_control_mad_pct=%.3f "
                + "ab_staged_mad_pct=%.3f ba_control_ms=%.6f ba_staged_ms=%.6f "
                + "ba_speedup=%.6f ba_control_mad_pct=%.3f ba_staged_mad_pct=%.3f "
                + "threadgroup_bytes_control=54 threadgroup_bytes_staged=70",
            rounds,
            batchSize,
            abControlMedian * 1_000,
            abStagedMedian * 1_000,
            abSpeedup,
            relativeMADPercent(abControl),
            relativeMADPercent(abStaged),
            baControlMedian * 1_000,
            baStagedMedian * 1_000,
            baSpeedup,
            relativeMADPercent(baControl),
            relativeMADPercent(baStaged)
        )
    )
}

private let routerStagingRuntimeTestsEnabled =
    ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"

private struct RouterStagingFixture {
    let routedDownWeight: MLXArray
    let routedDownScales: MLXArray
    let sharedDownWeight: MLXArray
    let sharedDownScales: MLXArray
}

private struct RouterStagingCase {
    let routedActivated: MLXArray
    let indices: MLXArray
    let routerWeights: MLXArray
    let sharedActivated: MLXArray
    let residual: MLXArray

    var arrays: [MLXArray] {
        [routedActivated, indices, routerWeights, sharedActivated, residual]
    }
}

private func makeRouterStagingFixture() -> RouterStagingFixture {
    let routedPackedSeed = MLXArray(
        (0..<256).map { expert in
            UInt32((expert % 7) + 1) &* UInt32(0x1111_1111)
        },
        [256, 1, 1]
    )
    let routedDownWeight = contiguous(
        broadcast(routedPackedSeed, to: [256, 2_048, 64])
    )
    let routedScaleSeed = MLXArray(
        (0..<256).map { expert in UInt8(0x38 + (expert % 4)) },
        [256, 1, 1]
    )
    let routedDownScales = contiguous(
        broadcast(routedScaleSeed, to: [256, 2_048, 32])
    )

    let sharedPackedSeed = MLXArray(
        (0..<2_048).map { row in
            UInt32((row % 7) + 1) &* UInt32(0x1111_1111)
        },
        [2_048, 1]
    )
    let sharedDownWeight = contiguous(
        broadcast(sharedPackedSeed, to: [2_048, 64])
    )
    let sharedScaleSeed = MLXArray(
        (0..<2_048).map { row in UInt8(0x38 + (row % 4)) },
        [2_048, 1]
    )
    let sharedDownScales = contiguous(
        broadcast(sharedScaleSeed, to: [2_048, 32])
    )

    eval(routedDownWeight, routedDownScales, sharedDownWeight, sharedDownScales)
    return RouterStagingFixture(
        routedDownWeight: routedDownWeight,
        routedDownScales: routedDownScales,
        sharedDownWeight: sharedDownWeight,
        sharedDownScales: sharedDownScales
    )
}

private func makeRouterStagingCase(
    seed: Int,
    indices: [UInt32],
    routerWeights: [Float]
) -> RouterStagingCase {
    let routedValues = (0..<(8 * 512)).map { index in
        Float(((index * 37 + seed * 11) % 61) - 30) / 64
    }
    let sharedValues = (0..<512).map { index in
        Float(((index * 29 + seed * 7) % 47) - 23) / 64
    }
    let residualValues = (0..<2_048).map { index in
        Float(((index * 19 + seed * 13) % 53) - 26) / 32
    }

    return RouterStagingCase(
        routedActivated: MLXArray(routedValues, [1, 1, 8, 1, 512]).asType(.bfloat16),
        indices: MLXArray(indices, [1, 1, 8]),
        routerWeights: MLXArray(routerWeights, [1, 1, 8]),
        sharedActivated: MLXArray(sharedValues, [1, 1, 512]).asType(.bfloat16),
        residual: MLXArray(residualValues, [1, 1, 2_048]).asType(.bfloat16)
    )
}

private func routerStagingOutput(
    fixture: RouterStagingFixture,
    testCase: RouterStagingCase,
    useUnstagedControl: Bool
) -> MLXArray {
    lagunaRoutedSharedDownResidual(
        routedActivated: testCase.routedActivated,
        routedDownWeight: fixture.routedDownWeight,
        routedDownScales: fixture.routedDownScales,
        indices: testCase.indices,
        routerWeights: testCase.routerWeights,
        sharedActivated: testCase.sharedActivated,
        sharedDownWeight: fixture.sharedDownWeight,
        sharedDownScales: fixture.sharedDownScales,
        residual: testCase.residual,
        testingUseUnstagedRouterWeights: useUnstagedControl
    )
}

private func measureRouterStagingBatch(
    fixture: RouterStagingFixture,
    testCase: RouterStagingCase,
    useUnstagedControl: Bool,
    count: Int
) -> Double {
    var outputs = [MLXArray]()
    outputs.reserveCapacity(count)
    for _ in 0..<count {
        outputs.append(
            routerStagingOutput(
                fixture: fixture,
                testCase: testCase,
                useUnstagedControl: useUnstagedControl
            )
        )
    }

    let start = DispatchTime.now().uptimeNanoseconds
    eval(outputs)
    let end = DispatchTime.now().uptimeNanoseconds
    return Double(end - start) / 1_000_000_000
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    return sorted[sorted.count / 2]
}

private func relativeMADPercent(_ values: [Double]) -> Double {
    let center = median(values)
    let deviations = values.map { abs($0 - center) }
    return median(deviations) / center * 100
}
