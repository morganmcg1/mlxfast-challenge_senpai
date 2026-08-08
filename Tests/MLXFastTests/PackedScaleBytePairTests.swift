import Foundation
import MLX
import MLXFastCore
@testable import MLXFastModel
import Testing

@Test
func packedScaleBytePairLayoutExhaustivelyPreservesEverySourceByte() {
    let experts = 256
    let tiles = 128
    let kBlocks = 4
    let subPairs = 4
    let lanes = 32
    var checked = 0
    var firstMismatch: String?

    for expert in 0..<experts {
        for tile in 0..<tiles {
            for kBlock in 0..<kBlocks {
                for subPair in 0..<subPairs {
                    for lane in 0..<lanes {
                        for projection in 0..<2 {
                            let pairOffset = (((((expert * tiles + tile) * kBlocks + kBlock)
                                * subPairs + subPair) * lanes + lane) * 2 + projection)
                            var remaining = pairOffset
                            let decodedProjection = remaining % 2
                            remaining /= 2
                            let decodedLane = remaining % lanes
                            remaining /= lanes
                            let decodedSubPair = remaining % subPairs
                            remaining /= subPairs
                            let decodedKBlock = remaining % kBlocks
                            remaining /= kBlocks
                            let decodedTile = remaining % tiles
                            let decodedExpert = remaining / tiles

                            let expectedSub = subPair * 2 + projection
                            let expectedSource = packedScaleSourceOffset(
                                expert: expert,
                                tile: tile,
                                kBlock: kBlock,
                                sub: expectedSub,
                                lane: lane)
                            let decodedSource = packedScaleSourceOffset(
                                expert: decodedExpert,
                                tile: decodedTile,
                                kBlock: decodedKBlock,
                                sub: decodedSubPair * 2 + decodedProjection,
                                lane: decodedLane)
                            if firstMismatch == nil, expectedSource != decodedSource {
                                firstMismatch = "pairOffset=\(pairOffset) expected=\(expectedSource) actual=\(decodedSource)"
                            }
                            checked += 1
                        }
                    }
                }
            }
        }
    }

    #expect(firstMismatch == nil, Comment(rawValue: firstMismatch ?? ""))
    #expect(checked == 33_554_432)
    print("PACKED_SCALE_PAIR_MAPPING checked=\(checked) mismatches=\(firstMismatch == nil ? 0 : 1)")
}

@Test
func packedScaleBytePairMetalExactnessAndIsolationWhenEnabled() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_PACKED_SCALE_PAIR_EXPERIMENT"] == "1" else {
        return
    }

    let weightsPath = ProcessInfo.processInfo.environment["MLXFAST_WEIGHTS_PATH"] ?? "weights"
    let store = try DenseTensorStore(weightsPath: weightsPath)
    let bridge = MLXArrayTensorBridge()
    let prefix = "model.layers.1.mlp.switch_mlp"
    let gateWeight = try bridge.makeArray(
        from: store.materializedTensor(named: "\(prefix).gate_proj.weight"))
    let upWeight = try bridge.makeArray(
        from: store.materializedTensor(named: "\(prefix).up_proj.weight"))
    let gateScales = try bridge.makeArray(
        from: store.materializedTensor(named: "\(prefix).gate_proj.scales"))
    let upScales = try bridge.makeArray(
        from: store.materializedTensor(named: "\(prefix).up_proj.scales"))

    #expect(gateWeight.shape == [256, 512, 256])
    #expect(upWeight.shape == gateWeight.shape)
    #expect(gateScales.shape == [256, 512, 128])
    #expect(upScales.shape == gateScales.shape)

    let fusedWeight = fuseGateUp(gate: gateWeight, up: upWeight)
    let checkpointScales = fuseGateUp(gate: gateScales, up: upScales)
    let checkpointBanks = makePackedScaleBanks(checkpointScales)
    eval(fusedWeight, checkpointBanks.scalar, checkpointBanks.paired)

    let inputs = [
        ("random", randomInput(seed: 0xceda_379)),
        ("adversarial", adversarialInput()),
        ("low-magnitude", lowMagnitudeInput()),
    ]
    let expertSelections: [(String, [UInt32])] = [
        ("boundaries", [0, 1, 31, 32, 127, 128, 254, 255]),
        ("reversed-slots", [255, 128, 32, 31, 1, 0, 254, 127]),
        ("repeated", [0, 255, 0, 255, 31, 32, 31, 32]),
    ]
    var exactComparisons = 0
    var verbose = true

    for (inputName, input) in inputs {
        for (selectionName, selection) in expertSelections {
            let indices = MLXArray(selection, [1, 1, 8])
            for repetition in 0..<3 {
                try expectBitwiseEqual(
                    input: input,
                    fusedWeight: fusedWeight,
                    banks: checkpointBanks,
                    indices: indices,
                    label: "checkpoint/\(inputName)/\(selectionName)/repeat-\(repetition)",
                    verbose: verbose)
                verbose = false
                exactComparisons += 1
            }
        }
    }

    let randomBanks = makePackedScaleBanks(
        syntheticFusedScales(seed: 0x379c_ed4, adversarial: false))
    let adversarialBanks = makePackedScaleBanks(
        syntheticFusedScales(seed: 0, adversarial: true))
    eval(randomBanks.scalar, randomBanks.paired, adversarialBanks.scalar, adversarialBanks.paired)

    let stressInput = adversarialInput()
    let stressIndices = MLXArray(
        [UInt32(255), 0, 128, 127, 32, 31, 254, 1], [1, 1, 8])
    for (name, banks) in [("random-scales", randomBanks), ("adversarial-scales", adversarialBanks)] {
        for repetition in 0..<3 {
            try expectBitwiseEqual(
                input: stressInput,
                fusedWeight: fusedWeight,
                banks: banks,
                indices: stressIndices,
                label: "\(name)/repeat-\(repetition)",
                verbose: false)
            exactComparisons += 1
        }
    }
    print("PACKED_SCALE_PAIR_EXACT comparisons=\(exactComparisons) mismatches=0")

    let timingInput = randomInput(seed: 0x51a7_e379)
    let timingIndices = MLXArray(
        [UInt32(0), 255, 31, 32, 127, 128, 1, 254], [1, 1, 8])
    for _ in 0..<10 {
        _ = measureKernel(
            input: timingInput,
            fusedWeight: fusedWeight,
            packedScales: checkpointBanks.scalar,
            indices: timingIndices,
            pairScaleBytes: false)
        _ = measureKernel(
            input: timingInput,
            fusedWeight: fusedWeight,
            packedScales: checkpointBanks.paired,
            indices: timingIndices,
            pairScaleBytes: true)
    }

    let repetitions = 40
    let ab = measureOrder(
        repetitions: repetitions,
        firstPair: false,
        input: timingInput,
        fusedWeight: fusedWeight,
        banks: checkpointBanks,
        indices: timingIndices)
    let ba = measureOrder(
        repetitions: repetitions,
        firstPair: true,
        input: timingInput,
        fusedWeight: fusedWeight,
        banks: checkpointBanks,
        indices: timingIndices)
    printTiming(label: "AB", summary: ab, repetitions: repetitions)
    printTiming(label: "BA", summary: ba, repetitions: repetitions)
}

private struct PackedScaleBanks {
    let scalar: MLXArray
    let paired: MLXArray
}

private struct TimingSummary {
    let scalarMedian: Double
    let pairedMedian: Double
    let speedup: Double
    let normalizedMAD: Double
    let noiseMultiple: Double
}

private func packedScaleSourceOffset(
    expert: Int,
    tile: Int,
    kBlock: Int,
    sub: Int,
    lane: Int
) -> Int {
    let logicalRow = tile * 4 + sub / 2
    let gateRow = (logicalRow / 32) * 64 + logicalRow % 32
    let fusedRow = sub % 2 == 0 ? gateRow : gateRow + 32
    return ((expert * 4096 + fusedRow * 4 + kBlock) * 32) + lane
}

private func fuseGateUp(gate: MLXArray, up: MLXArray) -> MLXArray {
    let experts = gate.dim(0)
    let rows = gate.dim(1)
    let depth = gate.dim(2)
    let pairRows = 32
    return concatenated(
        [
            gate.reshaped([experts, rows / pairRows, pairRows, depth]),
            up.reshaped([experts, rows / pairRows, pairRows, depth]),
        ],
        axis: 2
    ).reshaped([experts, 2 * rows, depth])
}

private func makePackedScaleBanks(_ fusedScales: MLXArray) -> PackedScaleBanks {
    let experts = 256
    let rows = 1024
    let rowBlocks = fusedScales.reshaped([experts, rows * 4, 32])
    var order = [Int32]()
    order.reserveCapacity(rows * 4)
    for tile in 0..<(rows / 8) {
        for kBlock in 0..<4 {
            for sub in 0..<8 {
                let logicalRow = tile * 4 + sub / 2
                let gateRow = (logicalRow / 32) * 64 + logicalRow % 32
                let fusedRow = sub % 2 == 0 ? gateRow : gateRow + 32
                order.append(Int32(fusedRow * 4 + kBlock))
            }
        }
    }
    let gathered = take(rowBlocks, MLXArray(order), axis: 1)
    let scalar = contiguous(gathered)
    let paired = contiguous(
        gathered.reshaped([experts, rows / 8, 4, 4, 2, 32])
            .transposed(0, 1, 2, 3, 5, 4))
    return PackedScaleBanks(scalar: scalar, paired: paired)
}

private func syntheticFusedScales(seed: UInt64, adversarial: Bool) -> MLXArray {
    let values: [UInt8]
    if adversarial {
        values = (0..<128).map { $0.isMultiple(of: 2) ? UInt8(0x08) : UInt8(0x70) }
    } else {
        let valid: [UInt8] = [0x20, 0x28, 0x30, 0x38, 0x40, 0x48, 0x50, 0x58]
        var state = seed
        values = (0..<128).map { _ in
            state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
            return valid[Int((state >> 32) % UInt64(valid.count))]
        }
    }
    let seedArray = MLXArray(values, [1, 1, 128])
    return broadcast(seedArray, to: [256, 1024, 128])
}

private func randomInput(seed: UInt64) -> MLXArray {
    var state = seed
    let values = (0..<2048).map { _ -> Float in
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        let unit = Float(state >> 40) / Float(1 << 24)
        return (unit * 2 - 1) * 3
    }
    return MLXArray(values, [1, 1, 2048]).asType(.bfloat16)
}

private func adversarialInput() -> MLXArray {
    let pattern: [Float] = [
        0, -0, 0.000_976_562_5, -0.000_976_562_5,
        0.5, -0.5, 15.5, -15.5,
        127, -127, 255, -255, 1, -1, 3.25, -3.25,
    ]
    let values = (0..<2048).map { pattern[$0 % pattern.count] }
    return MLXArray(values, [1, 1, 2048]).asType(.bfloat16)
}

private func lowMagnitudeInput() -> MLXArray {
    let values = (0..<2048).map { index -> Float in
        let magnitude = Float((index % 31) + 1) / 4096
        return index.isMultiple(of: 2) ? magnitude : -magnitude
    }
    return MLXArray(values, [1, 1, 2048]).asType(.bfloat16)
}

private func expectBitwiseEqual(
    input: MLXArray,
    fusedWeight: MLXArray,
    banks: PackedScaleBanks,
    indices: MLXArray,
    label: String,
    verbose: Bool
) throws {
    let scalar = lagunaRoutedSwiGLUQMVPackedTop8(
        input,
        fusedWeight: fusedWeight,
        packedScales: banks.scalar,
        indices: indices,
        pairScaleBytes: false,
        verbose: verbose)
    let paired = lagunaRoutedSwiGLUQMVPackedTop8(
        input,
        fusedWeight: fusedWeight,
        packedScales: banks.paired,
        indices: indices,
        pairScaleBytes: true,
        verbose: verbose)
    eval(scalar, paired)
    let scalarBits = scalar.view(dtype: .uint16).asArray(UInt16.self)
    let pairedBits = paired.view(dtype: .uint16).asArray(UInt16.self)
    guard scalarBits == pairedBits else {
        let mismatch = (0..<min(scalarBits.count, pairedBits.count))
            .first { scalarBits[$0] != pairedBits[$0] } ?? -1
        Issue.record("\(label) BF16 mismatch at flat index \(mismatch)")
        throw PackedScalePairTestError.bitwiseMismatch(label)
    }
}

private enum PackedScalePairTestError: Error {
    case bitwiseMismatch(String)
}

private func measureKernel(
    input: MLXArray,
    fusedWeight: MLXArray,
    packedScales: MLXArray,
    indices: MLXArray,
    pairScaleBytes: Bool
) -> Double {
    let output = lagunaRoutedSwiGLUQMVPackedTop8(
        input,
        fusedWeight: fusedWeight,
        packedScales: packedScales,
        indices: indices,
        pairScaleBytes: pairScaleBytes)
    let start = DispatchTime.now().uptimeNanoseconds
    eval(output)
    return Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000_000_000
}

private func measureOrder(
    repetitions: Int,
    firstPair: Bool,
    input: MLXArray,
    fusedWeight: MLXArray,
    banks: PackedScaleBanks,
    indices: MLXArray
) -> TimingSummary {
    var scalar = [Double]()
    var paired = [Double]()
    scalar.reserveCapacity(repetitions)
    paired.reserveCapacity(repetitions)
    for _ in 0..<repetitions {
        if firstPair {
            paired.append(measureKernel(
                input: input,
                fusedWeight: fusedWeight,
                packedScales: banks.paired,
                indices: indices,
                pairScaleBytes: true))
            scalar.append(measureKernel(
                input: input,
                fusedWeight: fusedWeight,
                packedScales: banks.scalar,
                indices: indices,
                pairScaleBytes: false))
        } else {
            scalar.append(measureKernel(
                input: input,
                fusedWeight: fusedWeight,
                packedScales: banks.scalar,
                indices: indices,
                pairScaleBytes: false))
            paired.append(measureKernel(
                input: input,
                fusedWeight: fusedWeight,
                packedScales: banks.paired,
                indices: indices,
                pairScaleBytes: true))
        }
    }
    let scalarMedian = median(scalar)
    let pairedMedian = median(paired)
    let speedup = scalarMedian / pairedMedian
    let normalizedMAD = max(
        medianAbsoluteDeviation(scalar, around: scalarMedian) / scalarMedian,
        medianAbsoluteDeviation(paired, around: pairedMedian) / pairedMedian)
    let signal = speedup - 1
    let noiseMultiple = normalizedMAD > 0 ? signal / normalizedMAD : .infinity
    return TimingSummary(
        scalarMedian: scalarMedian,
        pairedMedian: pairedMedian,
        speedup: speedup,
        normalizedMAD: normalizedMAD,
        noiseMultiple: noiseMultiple)
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}

private func medianAbsoluteDeviation(_ values: [Double], around center: Double) -> Double {
    median(values.map { abs($0 - center) })
}

private func printTiming(label: String, summary: TimingSummary, repetitions: Int) {
    print(
        "PACKED_SCALE_PAIR_TIMING order=\(label) reps=\(repetitions) "
            + "scalar_median_s=\(summary.scalarMedian) paired_median_s=\(summary.pairedMedian) "
            + "speedup=\(summary.speedup) normalized_mad=\(summary.normalizedMAD) "
            + "noise_multiple=\(summary.noiseMultiple) gate_1pct=\(summary.speedup >= 1.01) "
            + "gate_2mad=\(summary.noiseMultiple > 2)")
}
