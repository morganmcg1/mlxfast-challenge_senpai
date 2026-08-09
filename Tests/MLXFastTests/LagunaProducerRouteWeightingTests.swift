import Foundation
import MLX
@testable import MLXFastModel
import Testing

@Suite(.serialized)
struct LagunaProducerRouteWeightingTests {
    @Test
    func actualKernelIsBitExactAndDetectsSlotCorruption() {
        guard ProcessInfo.processInfo.environment[
            "MLXFAST_RUN_PRODUCER_ROUTE_WEIGHTING_TESTS"
        ] == "1" else {
            return
        }

        let weights = makeProducerRouteWeights()
        for caseIndex in 0..<4 {
            let fixture = makeProducerRouteFixture(caseIndex: caseIndex, weights: weights)
            let control = producerRouteOutput(fixture, producerRouteWeighting: false)
            let candidate = producerRouteOutput(fixture, producerRouteWeighting: true)
            eval(control, candidate)

            let controlBits = control.view(dtype: .uint16).asArray(UInt16.self)
            let candidateBits = candidate.view(dtype: .uint16).asArray(UInt16.self)
            let allMismatches = producerRouteMismatchCount(controlBits, candidateBits)
            let firstMismatches = producerRouteMismatchCount(
                controlBits,
                candidateBits,
                rows: [0, 1, 2]
            )
            let interiorMismatches = producerRouteMismatchCount(
                controlBits,
                candidateBits,
                rows: [1023, 1024, 1025]
            )
            let finalMismatches = producerRouteMismatchCount(
                controlBits,
                candidateBits,
                rows: [2046, 2047]
            )
            print(
                "producer-route case=\(caseIndex) mismatches=\(allMismatches) "
                    + "first=\(firstMismatches) interior=\(interiorMismatches) "
                    + "final=\(finalMismatches)"
            )
            #expect(
                allMismatches == 0,
                Comment(rawValue: "case \(caseIndex) changed BF16 output bits")
            )
        }

        let fixture = makeProducerRouteFixture(caseIndex: 2, weights: weights)
        var corruptedValues = fixture.routerWeightValues
        corruptedValues.swapAt(0, 1)
        let corruptedWeights = MLXArray(corruptedValues, [1, 1, 8])
        let control = producerRouteOutput(fixture, producerRouteWeighting: false)
        let corrupted = producerRouteOutput(
            fixture,
            routerWeights: corruptedWeights,
            producerRouteWeighting: true
        )
        eval(control, corrupted)
        let corruptionMismatches = producerRouteMismatchCount(
            control.view(dtype: .uint16).asArray(UInt16.self),
            corrupted.view(dtype: .uint16).asArray(UInt16.self)
        )
        print("producer-route corruption mismatches=\(corruptionMismatches)")
        #expect(
            corruptionMismatches > 0,
            "slot-order corruption control did not perturb output bits"
        )
    }

    @Test
    func actualKernelWritesIndependentABBAAndBAABTimingSamples() throws {
        guard ProcessInfo.processInfo.environment[
            "MLXFAST_RUN_PRODUCER_ROUTE_WEIGHTING_TIMING"
        ] == "1" else {
            return
        }

        let fixture = makeProducerRouteFixture(
            caseIndex: 0,
            weights: makeProducerRouteWeights()
        )
        let launchesPerSample = 4
        for _ in 0..<16 {
            _ = measureProducerRouteKernel(
                fixture,
                producerRouteWeighting: false,
                launches: launchesPerSample
            )
            _ = measureProducerRouteKernel(
                fixture,
                producerRouteWeighting: true,
                launches: launchesPerSample
            )
        }

        var samples = [[String: Any]]()
        samples.reserveCapacity(514)
        for block in 0..<257 {
            samples.append(
                producerRouteSuperblock(
                    fixture,
                    order: [false, true, true, false],
                    orderName: "ABBA",
                    block: block,
                    launches: launchesPerSample
                )
            )
        }
        for block in 0..<257 {
            samples.append(
                producerRouteSuperblock(
                    fixture,
                    order: [true, false, false, true],
                    orderName: "BAAB",
                    block: block,
                    launches: launchesPerSample
                )
            )
        }

        let artifact: [String: Any] = [
            "schema_version": 1,
            "control_kernel": "laguna_routed_shared_nvfp4_down_residual_bf16_r3ceil_v1_bf4",
            "candidate_kernel": "laguna_routed_shared_nvfp4_down_residual_bf16_r3ceil_v1_bf4_producer_route_v1",
            "generic_kernel_family": "laguna_routed_shared_nvfp4_down_residual_bf16_r3ceil_v1_bf4",
            "threadgroup_storage_bytes": 54,
            "grid": [196_704, 1, 1],
            "threadgroup": [288, 1, 1],
            "warmup_samples_per_arm": 16,
            "launches_per_sample": launchesPerSample,
            "superblocks_per_order": 257,
            "cooling_policy": "single quiet interleaved process; no arm-specific cooling",
            "samples": samples,
        ]
        let artifactDirectory = ".agent_tmp"
        try FileManager.default.createDirectory(
            atPath: artifactDirectory,
            withIntermediateDirectories: true
        )
        let artifactPath = "\(artifactDirectory)/pr487-producer-weighting-timing.json"
        let data = try JSONSerialization.data(
            withJSONObject: artifact,
            options: [.prettyPrinted, .sortedKeys]
        )
        try data.write(to: URL(fileURLWithPath: artifactPath))
        print("producer-route timing artifact=\(artifactPath) samples=\(samples.count)")
        #expect(samples.count == 514)
    }
}

private struct ProducerRouteWeights {
    let routedDownWeight: MLXArray
    let routedDownScales: MLXArray
    let sharedDownWeight: MLXArray
    let sharedDownScales: MLXArray
}

private struct ProducerRouteFixture {
    let routedActivated: MLXArray
    let routedDownWeight: MLXArray
    let routedDownScales: MLXArray
    let indices: MLXArray
    let routerWeights: MLXArray
    let routerWeightValues: [Float]
    let sharedActivated: MLXArray
    let sharedDownWeight: MLXArray
    let sharedDownScales: MLXArray
    let residual: MLXArray
}

private struct ProducerRouteLCG {
    var state: UInt64

    mutating func next(scale: Float) -> Float {
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        let unit = Float((state >> 40) & 0x00ff_ffff) / Float(0x0100_0000)
        return (unit * 2 - 1) * scale
    }
}

private func makeProducerRouteWeights() -> ProducerRouteWeights {
    let packedCodes = (0..<256).map { expert -> UInt32 in
        UInt32((expert * 5) % 15 + 1) &* UInt32(0x1111_1111)
    }
    let routedDownWeight = contiguous(
        broadcast(
            MLXArray(packedCodes, [256, 1, 1]),
            to: [256, 2048, 64]
        )
    )
    let routedDownScales = MLXArray.full(
        [256, 2048, 32],
        values: MLXArray(UInt8(0x38)),
        dtype: .uint8
    )
    let sharedDownWeight = contiguous(
        broadcast(
            MLXArray([UInt32(0x7654_3210)], [1, 1]),
            to: [2048, 64]
        )
    )
    let sharedDownScales = MLXArray.full(
        [2048, 32],
        values: MLXArray(UInt8(0x38)),
        dtype: .uint8
    )
    return ProducerRouteWeights(
        routedDownWeight: routedDownWeight,
        routedDownScales: routedDownScales,
        sharedDownWeight: sharedDownWeight,
        sharedDownScales: sharedDownScales
    )
}

private func makeProducerRouteFixture(
    caseIndex: Int,
    weights: ProducerRouteWeights
) -> ProducerRouteFixture {
    var rng = ProducerRouteLCG(state: UInt64(0xc0ffee + caseIndex * 977))
    let adversarial: [Float] = [
        0, 0.00390625, -0.00390625, 0.5, -0.5, 1, -1, 6,
        -6, 1.00390625, -1.00390625, 0.33325195, -0.33325195,
    ]
    let routedValues = (0..<(8 * 512)).map { index -> Float in
        switch caseIndex {
        case 1:
            return adversarial[index % adversarial.count]
        case 2:
            return adversarial[(index * 7 + 3) % adversarial.count] * 0.25
        case 3:
            return index % 11 == 0 ? 0 : rng.next(scale: 1.5)
        default:
            return rng.next(scale: 0.75)
        }
    }
    let sharedValues = (0..<512).map { _ in rng.next(scale: 0.5) }
    let residualValues = (0..<2048).map { _ in rng.next(scale: 0.25) }
    let indicesByCase: [[UInt32]] = [
        [0, 7, 42, 255, 3, 128, 17, 99],
        [255, 254, 129, 128, 64, 31, 7, 1],
        [13, 211, 5, 144, 89, 233, 34, 177],
        [201, 2, 87, 250, 19, 111, 63, 149],
    ]
    let routerWeightsByCase: [[Float]] = [
        [0.31, 0.19, 0.14, 0.11, 0.09, 0.07, 0.05, 0.04],
        [1.0e-38, -1.0e-38, 16, -12, 8, -4, 0.00006103515625, -0.00006103515625],
        [1.00390625, 1.01171875, 0.501953125, -0.501953125, 0.33325195, -0.33325195, 2.0078125, -2.0078125],
        [0.27, -0.23, 0.17, -0.13, 0.09, -0.07, 0.05, -0.03],
    ]
    let routerWeightValues = routerWeightsByCase[caseIndex]
    return ProducerRouteFixture(
        routedActivated: MLXArray(routedValues, [1, 1, 8, 1, 512])
            .asType(.bfloat16),
        routedDownWeight: weights.routedDownWeight,
        routedDownScales: weights.routedDownScales,
        indices: MLXArray(indicesByCase[caseIndex], [1, 1, 8]),
        routerWeights: MLXArray(routerWeightValues, [1, 1, 8]),
        routerWeightValues: routerWeightValues,
        sharedActivated: MLXArray(sharedValues, [1, 1, 512])
            .asType(.bfloat16),
        sharedDownWeight: weights.sharedDownWeight,
        sharedDownScales: weights.sharedDownScales,
        residual: MLXArray(residualValues, [1, 1, 2048]).asType(.bfloat16)
    )
}

private func producerRouteOutput(
    _ fixture: ProducerRouteFixture,
    routerWeights: MLXArray? = nil,
    producerRouteWeighting: Bool
) -> MLXArray {
    lagunaRoutedSharedDownResidual(
        routedActivated: fixture.routedActivated,
        routedDownWeight: fixture.routedDownWeight,
        routedDownScales: fixture.routedDownScales,
        indices: fixture.indices,
        routerWeights: routerWeights ?? fixture.routerWeights,
        sharedActivated: fixture.sharedActivated,
        sharedDownWeight: fixture.sharedDownWeight,
        sharedDownScales: fixture.sharedDownScales,
        residual: fixture.residual,
        producerRouteWeighting: producerRouteWeighting
    )
}

private func producerRouteMismatchCount(
    _ lhs: [UInt16],
    _ rhs: [UInt16],
    rows: [Int]? = nil
) -> Int {
    if let rows {
        return rows.reduce(into: 0) { count, row in
            if lhs[row] != rhs[row] {
                count += 1
            }
        }
    }
    return zip(lhs, rhs).reduce(into: 0) { count, values in
        if values.0 != values.1 {
            count += 1
        }
    }
}

private func measureProducerRouteKernel(
    _ fixture: ProducerRouteFixture,
    producerRouteWeighting: Bool,
    launches: Int
) -> UInt64 {
    let outputs = (0..<launches).map { _ in
        producerRouteOutput(
            fixture,
            producerRouteWeighting: producerRouteWeighting
        )
    }
    let start = DispatchTime.now().uptimeNanoseconds
    eval(outputs)
    return DispatchTime.now().uptimeNanoseconds - start
}

private func producerRouteSuperblock(
    _ fixture: ProducerRouteFixture,
    order: [Bool],
    orderName: String,
    block: Int,
    launches: Int
) -> [String: Any] {
    var control = [Int]()
    var candidate = [Int]()
    for producerRouteWeighting in order {
        let duration = Int(
            measureProducerRouteKernel(
                fixture,
                producerRouteWeighting: producerRouteWeighting,
                launches: launches
            )
        )
        if producerRouteWeighting {
            candidate.append(duration)
        } else {
            control.append(duration)
        }
    }
    return [
        "order": orderName,
        "block": block,
        "control_ns": control,
        "candidate_ns": candidate,
    ]
}
