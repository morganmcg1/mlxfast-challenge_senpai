import Foundation
import MLX
import MLXLMCommon
import MLXNN
import Testing
@testable import MLXFastModel

@Test
func nvfp4Group16SplitKMatmulMatchesDequantizedReferenceWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    // M=32, N=128, K=64 enters qmm_splitk. With group size 16 the old
    // dispatch selected four K=16 partitions even though the Metal kernel
    // consumes K in 32-wide tiles, over-reading every partition.
    let input = MLXArray(Array(repeating: Float(1), count: 32 * 64), [32, 64])
    let weight = MLXArray(Array(repeating: Float(1), count: 128 * 64), [128, 64])
    let (packedWeight, scales, biases) = quantized(
        weight,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4
    )

    let actual = quantizedMM(
        input,
        packedWeight,
        scales: scales,
        biases: biases,
        transpose: true,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4
    )
    let referenceWeight = dequantized(
        packedWeight,
        scales: scales,
        biases: biases,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4,
        dtype: .float32
    )
    let reference = matmul(input, referenceWeight.T)
    eval(actual, reference)

    let actualValues = actual.asArray(Float.self)
    let referenceValues = reference.asArray(Float.self)
    #expect(actualValues.allSatisfy { $0.isFinite })
    #expect(referenceValues.allSatisfy { $0.isFinite })
    let maximumError = zip(actualValues, referenceValues)
        .map { abs($0 - $1) }
        .max() ?? .infinity
    #expect(maximumError <= 1e-4)
}

@Test
func nvfp4NibbleOrderAndE4M3ScaleBytesMatchMLXContractWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    // U32 packs eight FP4 values least-significant nibble first. E2M1 codes
    // 0...7 decode as 0, .5, 1, 1.5, 2, 3, 4, 6 and bit 3 is the sign.
    // E4M3 scale bytes 0x38 and 0x40 decode as 1 and 2 respectively.
    let packed = MLXArray(
        [
            UInt32(0x7654_3210), UInt32(0xfedc_ba98),
            UInt32(0x7654_3210), UInt32(0xfedc_ba98),
        ],
        [2, 2]
    )
    let scales = MLXArray([UInt8(0x38), UInt8(0x40)], [2, 1])
    let unpacked = dequantized(
        packed,
        scales: scales,
        biases: nil,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4,
        dtype: .float32
    )
    eval(unpacked)

    let base: [Float] = [
        0, 0.5, 1, 1.5, 2, 3, 4, 6,
        -0, -0.5, -1, -1.5, -2, -3, -4, -6,
    ]
    #expect(unpacked.shape == [2, 16])
    #expect(unpacked.asArray(Float.self) == base + base.map { $0 * 2 })
}

@Test
func nvfp4ActualSharedExpertQMMShapesCoverDecodeAndSplitKPrefillWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    // gate/up: [512, 2048] logical, down: [2048, 512] logical.
    for (label, outputFeatures, inputFeatures) in [
        ("shared-gate-up", 512, 2_048),
        ("shared-down", 2_048, 512),
    ] {
        let weight = MLXArray.full(
            [outputFeatures, inputFeatures],
            values: MLXArray(Float(0.5)),
            dtype: .float32
        )
        let (packedWeight, scales, biases) = quantized(
            weight,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4
        )
        let referenceWeight = dequantized(
            packedWeight,
            scales: scales,
            biases: biases,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4,
            dtype: .float32
        )

        for tokenRows in [1, 32] {
            let input = MLXArray.full(
                [tokenRows, inputFeatures],
                values: MLXArray(Float(1)),
                dtype: .float32
            )
            let actual = quantizedMM(
                input,
                packedWeight,
                scales: scales,
                biases: biases,
                transpose: true,
                groupSize: 16,
                bits: 4,
                mode: .nvfp4
            )
            let reference = matmul(input, referenceWeight.T)
            expectFiniteClose(
                actual,
                reference,
                tolerance: 1e-4,
                label: "\(label)-M\(tokenRows)"
            )
        }
    }
}

@Test
func nvfp4ActualRoutedGatherShapesCoverMultipleExpertsAndPrefillWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    // gate/up logical [256, 512, 2048], down logical [256, 2048, 512].
    for (label, outputFeatures, inputFeatures) in [
        ("routed-gate-up", 512, 2_048),
        ("routed-down", 2_048, 512),
    ] {
        verifyActualRoutedGather(
            label: label,
            outputFeatures: outputFeatures,
            inputFeatures: inputFeatures,
            tokenCounts: [1, 8]
        )
    }
}

@Test
func quantizedSwitchLinearForwardsNVFP4GatherSemanticsWhenRuntimeTestsAreEnabled() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let dense = SwitchLinear(
        inputDims: 64,
        outputDims: 32,
        numExperts: 4,
        bias: false
    )
    let layer = QuantizedSwitchLinear(
        dense,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4
    )
    let input = MLXArray.full(
        [1, 2, 64],
        values: MLXArray(Float(0.25)),
        dtype: .float32
    )
    let expandedInput = expandedDimensions(input, axes: [-2, -3])
    let indices = MLXArray([Int32(0), 3, 2, 1], [1, 2, 2])
    let actual = layer(expandedInput, indices)

    let parameters = Dictionary(uniqueKeysWithValues: layer.parameters().flattened())
    let packedWeight = try #require(parameters["weight"])
    let scales = try #require(parameters["scales"])
    let referenceWeight = dequantized(
        packedWeight,
        scales: scales,
        biases: parameters["biases"],
        groupSize: 16,
        bits: 4,
        mode: .nvfp4,
        dtype: .float32
    )
    let reference = gatherMM(
        expandedInput,
        referenceWeight.swappedAxes(-1, -2),
        rhsIndices: indices
    )
    expectFiniteClose(
        actual,
        reference,
        tolerance: 1e-4,
        label: "QuantizedSwitchLinear"
    )
}

private func verifyActualRoutedGather(
    label: String,
    outputFeatures: Int,
    inputFeatures: Int,
    tokenCounts: [Int]
) {
    let expertCount = 256
    let topK = 8
    let packedWidth = inputFeatures * 4 / 32
    let scaleWidth = inputFeatures / 16

    // Give every expert a distinct constant E2M1 code. Broadcasting then
    // materializing this compact seed avoids a giant Swift-side payload while
    // still proving rhs expert indexing, including expert 255.
    let expertPackedCodes = (0..<expertCount).map { expert -> UInt32 in
        UInt32((expert % 7) + 1) &* UInt32(0x1111_1111)
    }
    let packedSeed = MLXArray(expertPackedCodes, [expertCount, 1, 1])
    let packedWeight = contiguous(
        broadcast(
            packedSeed,
            to: [expertCount, outputFeatures, packedWidth]
        )
    )
    let scales = MLXArray.full(
        [expertCount, outputFeatures, scaleWidth],
        values: MLXArray(UInt8(0x38)),
        dtype: .uint8
    )
    let selectedExpertIDs: [Int32] = [0, 7, 42, 255, 3, 128, 17, 99]
    let uniqueIDs = MLXArray(selectedExpertIDs)
    let selectedPacked = take(packedWeight, uniqueIDs, axis: 0)
    let selectedScales = take(scales, uniqueIDs, axis: 0)
    let selectedReferenceWeight = dequantized(
        selectedPacked,
        scales: selectedScales,
        biases: nil,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4,
        dtype: .float32
    )

    for tokenCount in tokenCounts {
        let input = MLXArray.full(
            [1, tokenCount, inputFeatures],
            values: MLXArray(Float(0.25)),
            dtype: .float32
        )
        let expandedInput = expandedDimensions(input, axes: [-2, -3])
        let flattenedIDs = (0..<tokenCount).flatMap { _ in selectedExpertIDs }
        let rhsIndices = MLXArray(flattenedIDs, [1, tokenCount, topK])
        let actual = gatherQuantizedMM(
            expandedInput,
            packedWeight,
            scales: scales,
            biases: nil,
            rhsIndices: rhsIndices,
            transpose: true,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4
        )
        let localIDs = MLXArray(
            (0..<tokenCount).flatMap { _ in (0..<topK).map(Int32.init) },
            [1, tokenCount, topK]
        )
        let reference = gatherMM(
            expandedInput,
            selectedReferenceWeight.swappedAxes(-1, -2),
            rhsIndices: localIDs
        )
        expectFiniteClose(
            actual,
            reference,
            tolerance: 1e-4,
            label: "\(label)-tokens\(tokenCount)"
        )
    }
}

private func expectFiniteClose(
    _ actual: MLXArray,
    _ reference: MLXArray,
    tolerance: Float,
    label: String
) {
    eval(actual, reference)
    let actualValues = actual.asArray(Float.self)
    let referenceValues = reference.asArray(Float.self)
    #expect(actual.shape == reference.shape, Comment(rawValue: label))
    #expect(
        actualValues.allSatisfy { $0.isFinite },
        Comment(rawValue: "\(label) produced non-finite NVFP4 output")
    )
    #expect(
        referenceValues.allSatisfy { $0.isFinite },
        Comment(rawValue: "\(label) produced non-finite reference output")
    )
    let maximumError = zip(actualValues, referenceValues)
        .map { abs($0 - $1) }
        .max() ?? .infinity
    #expect(
        maximumError <= tolerance,
        Comment(rawValue: "\(label) max error \(maximumError) > \(tolerance)")
    )
}

@Test
func activatedOProjInputStagingMatchesControlAndReportsIsolatedTimingWhenExplicitlyEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_OPROJ_STAGING_PROBE"] == "1" else {
        return
    }

    let rawSource = lagunaGatedAffineOProjNVFP4Source(
        heads: 48,
        preActivatedGate: false,
        stagePreActivatedInput: true
    )
    let activatedControlSource = lagunaGatedAffineOProjNVFP4Source(
        heads: 48,
        preActivatedGate: true,
        stagePreActivatedInput: false
    )
    let activatedStagedSource = lagunaGatedAffineOProjNVFP4Source(
        heads: 48,
        preActivatedGate: true,
        stagePreActivatedInput: true
    )
    let tileDeclaration = "threadgroup bfloat input_tile[block_size];"
    #expect(!rawSource.contains(tileDeclaration))
    #expect(!activatedControlSource.contains(tileDeclaration))
    #expect(activatedStagedSource.occurrences(of: tileDeclaration) == 1)
    #expect(activatedStagedSource.occurrences(of: "threadgroup_barrier(mem_flags::mem_threadgroup);") == 2)
    print("OPROJ_RESOURCE staged_threadgroup_bytes=1024 control_threadgroup_bytes=0 delta_bytes=1024 occupancy_counters=unavailable")

    for heads in [48, 64] {
        guard runActivatedOProjInputStagingProbe(heads: heads) else {
            return
        }
    }
}

private func runActivatedOProjInputStagingProbe(heads: Int) -> Bool {
    let inputSize = heads * 128
    let outputSize = 8_192
    let controlName = "laguna_oproj_probe_h\(heads)_control"
    let stagedName = "laguna_oproj_probe_h\(heads)_staged_is1"
    let inputNames = [
        "attention_output", "gate_values", "weight_codes", "weight_scales",
    ]
    let controlKernel = MLXFast.metalKernel(
        name: controlName,
        inputNames: inputNames,
        outputNames: ["projected"],
        source: lagunaGatedAffineOProjNVFP4Source(
            heads: heads,
            preActivatedGate: true,
            stagePreActivatedInput: false
        ),
        ensureRowContiguous: true
    )
    let stagedKernel = MLXFast.metalKernel(
        name: stagedName,
        inputNames: inputNames,
        outputNames: ["projected"],
        source: lagunaGatedAffineOProjNVFP4Source(
            heads: heads,
            preActivatedGate: true,
            stagePreActivatedInput: true
        ),
        ensureRowContiguous: true
    )

    let rowCodes = (0..<outputSize).map { row in
        UInt32(0x7654_3210) ^ (UInt32(row & 7) &* UInt32(0x1111_1111))
    }
    let rowScales = (0..<outputSize).map { row in
        [UInt8(0x30), UInt8(0x38), UInt8(0x40), UInt8(0x48)][row & 3]
    }
    let codes = contiguous(
        broadcast(MLXArray(rowCodes, [outputSize, 1]), to: [outputSize, inputSize / 8])
    )
    let scales = contiguous(
        broadcast(MLXArray(rowScales, [outputSize, 1]), to: [outputSize, inputSize / 16])
    )

    let edgeValues: [Float] = [
        0, -0.0,
        Float(bitPattern: 0x0001_0000), Float(bitPattern: 0x8001_0000),
        0.000_976_562_5, -0.000_976_562_5,
        1, -1, 128, -128,
    ]
    let edgeAttention = MLXArray(
        (0..<inputSize).map { edgeValues[$0 % edgeValues.count] },
        [1, 1, inputSize]
    ).asType(.bfloat16)
    let edgeGates = MLXArray(
        (0..<heads).map { edgeValues[($0 * 3) % edgeValues.count] },
        [1, 1, heads]
    ).asType(.bfloat16)

    var random = OProjProbeRandom(state: UInt64(0xceda_0000 + heads))
    let randomAttention = MLXArray(
        (0..<inputSize).map { _ in random.nextFloat(scale: 4) },
        [1, 1, inputSize]
    ).asType(.bfloat16)
    let randomGates = MLXArray(
        (0..<heads).map { _ in random.nextFloat(scale: 2) },
        [1, 1, heads]
    ).asType(.bfloat16)
    eval(codes, scales, edgeAttention, edgeGates, randomAttention, randomGates)

    let edgeExact = activatedOProjOutputsMatchExactly(
        label: "H\(heads)-edge",
        controlKernel: controlKernel,
        stagedKernel: stagedKernel,
        attention: edgeAttention,
        gates: edgeGates,
        codes: codes,
        scales: scales
    )
    let randomExact = activatedOProjOutputsMatchExactly(
        label: "H\(heads)-seeded-random",
        controlKernel: controlKernel,
        stagedKernel: stagedKernel,
        attention: randomAttention,
        gates: randomGates,
        codes: codes,
        scales: scales
    )
    guard edgeExact && randomExact else {
        return false
    }

    for _ in 0..<4 {
        eval(activatedOProjProbeOutput(
            kernel: controlKernel,
            attention: randomAttention,
            gates: randomGates,
            codes: codes,
            scales: scales
        ))
        eval(activatedOProjProbeOutput(
            kernel: stagedKernel,
            attention: randomAttention,
            gates: randomGates,
            codes: codes,
            scales: scales
        ))
    }

    var controlAB: [Double] = []
    var stagedAB: [Double] = []
    var controlBA: [Double] = []
    var stagedBA: [Double] = []
    for _ in 0..<12 {
        controlAB.append(measureOProjProbe {
            activatedOProjProbeOutput(
                kernel: controlKernel,
                attention: randomAttention,
                gates: randomGates,
                codes: codes,
                scales: scales
            )
        })
        stagedAB.append(measureOProjProbe {
            activatedOProjProbeOutput(
                kernel: stagedKernel,
                attention: randomAttention,
                gates: randomGates,
                codes: codes,
                scales: scales
            )
        })
    }
    for _ in 0..<12 {
        stagedBA.append(measureOProjProbe {
            activatedOProjProbeOutput(
                kernel: stagedKernel,
                attention: randomAttention,
                gates: randomGates,
                codes: codes,
                scales: scales
            )
        })
        controlBA.append(measureOProjProbe {
            activatedOProjProbeOutput(
                kernel: controlKernel,
                attention: randomAttention,
                gates: randomGates,
                codes: codes,
                scales: scales
            )
        })
    }

    let ab = reportOProjTiming(
        heads: heads,
        order: "A-control/B-staged",
        controlName: controlName,
        stagedName: stagedName,
        control: controlAB,
        staged: stagedAB
    )
    let ba = reportOProjTiming(
        heads: heads,
        order: "B-staged/A-control",
        controlName: controlName,
        stagedName: stagedName,
        control: controlBA,
        staged: stagedBA
    )
    let threshold = max(0.015, 2 * max(ab.mde95, ba.mde95))
    let timingGate = ab.speedup > 1 + threshold && ba.speedup > 1 + threshold
    print(
        String(
            format: "OPROJ_GATE H%d pass=%@ threshold=%.6f speedup_ab=%.6f speedup_ba=%.6f",
            heads, timingGate.description, threshold, ab.speedup, ba.speedup
        )
    )
    return true
}

private func activatedOProjOutputsMatchExactly(
    label: String,
    controlKernel: MLXFast.MLXFastKernel,
    stagedKernel: MLXFast.MLXFastKernel,
    attention: MLXArray,
    gates: MLXArray,
    codes: MLXArray,
    scales: MLXArray
) -> Bool {
    let control = activatedOProjProbeOutput(
        kernel: controlKernel,
        attention: attention,
        gates: gates,
        codes: codes,
        scales: scales
    )
    let staged = activatedOProjProbeOutput(
        kernel: stagedKernel,
        attention: attention,
        gates: gates,
        codes: codes,
        scales: scales
    )
    eval(control, staged)
    let exact = control.view(dtype: .uint16).asArray(UInt16.self)
        == staged.view(dtype: .uint16).asArray(UInt16.self)
    #expect(exact, Comment(rawValue: "\(label) BF16 output bits differ"))
    print("OPROJ_ORACLE \(label) exact=\(exact) outputs=8192")
    return exact
}

private func activatedOProjProbeOutput(
    kernel: MLXFast.MLXFastKernel,
    attention: MLXArray,
    gates: MLXArray,
    codes: MLXArray,
    scales: MLXArray
) -> MLXArray {
    kernel(
        [attention, gates, codes, scales],
        grid: ((8_192 / 8) * 64, 1, 1),
        threadGroup: (64, 1, 1),
        outputShapes: [[1, 1, 8_192]],
        outputDTypes: [.bfloat16]
    )[0]
}

private func measureOProjProbe(_ operation: () -> MLXArray) -> Double {
    let start = DispatchTime.now().uptimeNanoseconds
    eval(operation())
    let end = DispatchTime.now().uptimeNanoseconds
    return Double(end - start) / 1_000_000_000
}

private func reportOProjTiming(
    heads: Int,
    order: String,
    controlName: String,
    stagedName: String,
    control: [Double],
    staged: [Double]
) -> (speedup: Double, mde95: Double) {
    let controlMedian = median(control)
    let stagedMedian = median(staged)
    let controlMAD = median(control.map { abs($0 - controlMedian) })
    let stagedMAD = median(staged.map { abs($0 - stagedMedian) })
    let pairedLogSpeedups = zip(control, staged).map { log($0 / $1) }
    let center = median(pairedLogSpeedups)
    let logMAD = median(pairedLogSpeedups.map { abs($0 - center) })
    let mde95 = exp(1.96 * 1.4826 * logMAD / sqrt(Double(control.count))) - 1
    let speedup = exp(center)
    print("OPROJ_TIMING H\(heads) order=\(order) control=\(controlName) staged=\(stagedName)")
    print("OPROJ_RAW H\(heads) order=\(order) control_seconds=\(formatOProjSamples(control))")
    print("OPROJ_RAW H\(heads) order=\(order) staged_seconds=\(formatOProjSamples(staged))")
    print(
        String(
            format: "OPROJ_STATS H%d order=%@ control_median=%.9f control_rel_mad=%.6f staged_median=%.9f staged_rel_mad=%.6f paired_speedup=%.6f robust_mde95=%.6f",
            heads, order, controlMedian, controlMAD / controlMedian,
            stagedMedian, stagedMAD / stagedMedian, speedup, mde95
        )
    )
    return (speedup, mde95)
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}

private func formatOProjSamples(_ values: [Double]) -> String {
    "[" + values.map { String(format: "%.9f", $0) }.joined(separator: ",") + "]"
}

private struct OProjProbeRandom {
    var state: UInt64

    mutating func nextFloat(scale: Float) -> Float {
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        let fraction = Float(UInt32(truncatingIfNeeded: state >> 24) & 0xffff) / 65_535
        return (2 * fraction - 1) * scale
    }
}

private extension String {
    func occurrences(of substring: String) -> Int {
        components(separatedBy: substring).count - 1
    }
}
