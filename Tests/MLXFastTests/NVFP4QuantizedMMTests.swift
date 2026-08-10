import Foundation
import MLX
import MLXFastCore
@testable import MLXFastModel
import MLXNN
import Testing

@Suite(.serialized)
struct NVFP4QuantizedMMTests {
    @Test
    func nvfp4DatatypeHelpersStayInAOTAndJITSources() throws {
        let kernelRoot =
            "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels"
        let generatedRoot =
            "Vendor/mlx-swift/Source/Cmlx/mlx-generated"
        let fp4 = try String(contentsOfFile: "\(kernelRoot)/fp4.h", encoding: .utf8)
        let fp8 = try String(contentsOfFile: "\(kernelRoot)/fp8.h", encoding: .utf8)
        let fp4Body = fp4.components(separatedBy: "\n").dropFirst(2)
            .joined(separator: "\n")
        let fp8Body = fp8.components(separatedBy: "\n").dropFirst(2)
            .joined(separator: "\n")

        #expect(fp4Body.contains("struct fp4_e2m1"))
        #expect(fp8Body.contains("struct fp8_e4m3"))
        #expect(fp8Body.contains("struct fp8_e8m0"))

        for path in [
            "\(kernelRoot)/fp_quantized.h",
            "\(kernelRoot)/fp_quantized_nax.h",
        ] {
            let aot = try String(contentsOfFile: path, encoding: .utf8)
            #expect(aot.contains(#"#include "mlx/backend/metal/kernels/fp4.h""#))
            #expect(aot.contains(#"#include "mlx/backend/metal/kernels/fp8.h""#))
        }

        for path in [
            "\(generatedRoot)/fp_quantized.cpp",
            "\(generatedRoot)/fp_quantized_nax.cpp",
        ] {
            let jit = try String(contentsOfFile: path, encoding: .utf8)
            #expect(jit.contains(#"Contents from "mlx/backend/metal/kernels/fp4.h""#))
            #expect(jit.contains(#"Contents from "mlx/backend/metal/kernels/fp8.h""#))
            #expect(jit.contains(fp4Body))
            #expect(jit.contains(fp8Body))
        }

        let unaryAOT = try String(
            contentsOfFile: "\(kernelRoot)/unary_ops.h",
            encoding: .utf8
        )
        let unaryJIT = try String(
            contentsOfFile: "\(generatedRoot)/unary_ops.cpp",
            encoding: .utf8
        )
        #expect(unaryAOT.contains(#"#include "mlx/backend/metal/kernels/fp8.h""#))
        #expect(unaryJIT.contains(#"Contents from "mlx/backend/metal/kernels/fp8.h""#))
        #expect(unaryJIT.contains(fp8Body))
    }

    @Test
    func nvfp4Group16SplitKUsesKernelTileAlignment() throws {
        let source = try String(
            contentsOfFile:
                "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp",
            encoding: .utf8
        )
        #expect(source.contains("int k_align = std::max(group_size, 32);"))
        #expect(!source.contains("int k_align = group_size;"))
    }

    @Test
    func nvfp4NAXGatherFactoryUsesDeclaredTemplateNames() throws {
        let kernelRoot =
            "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels"
        let generatedRoot =
            "Vendor/mlx-swift/Source/Cmlx/mlx-generated"
        let declaredFunctions = [
            "fp_gather_qmm_t_nax",
            "fp_gather_qmm_n_nax",
        ]
        for path in [
            "\(kernelRoot)/fp_quantized_nax.h",
            "\(generatedRoot)/fp_quantized_nax.cpp",
        ] {
            let source = try String(contentsOfFile: path, encoding: .utf8)
            for function in declaredFunctions {
                #expect(source.contains("void \(function)("))
            }
        }

        let factory = try String(
            contentsOfFile:
                "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp",
            encoding: .utf8
        )
        #expect(factory.contains(#""gather_qmm_t_nax","#))
        #expect(factory.contains(#""gather_qmm_n_nax","#))
        #expect(!factory.contains(#""gather_qmm_t_nax_","#))
        #expect(!factory.contains(#""gather_qmm_n_nax_","#))
    }

    @Test
    func nvfp4PackedNibblesDecodeLowNibbleFirstWhenRuntimeTestsAreEnabled() {
        guard nvfp4RuntimeTestsEnabled else { return }

        let packed = MLXArray(
            packNVFP4Nibbles(Array(0...15).map(UInt8.init)),
            [1, 2]
        )
        let scales = MLXArray([UInt8(0x38)], [1, 1]) // E4M3 1.0
        let decoded = dequantized(
            packed,
            scales: scales,
            biases: nil,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4,
            dtype: .float32
        )

        #expect(
            decoded.asArray(Float.self) == [
                0, 0.5, 1, 1.5, 2, 3, 4, 6,
                0, -0.5, -1, -1.5, -2, -3, -4, -6,
            ]
        )
    }

    @Test
    func nvfp4U8E4M3ScalesDecodePerGroupWhenRuntimeTestsAreEnabled() {
        guard nvfp4RuntimeTestsEnabled else { return }

        // FP4 code 0x2 is exactly 1.0. E4M3 scale bytes 0x30 and 0x40
        // are 0.5 and 2.0, respectively.
        let packed = MLXArray(
            Array(repeating: UInt32(0x2222_2222), count: 4),
            [1, 4]
        )
        let scales = MLXArray([UInt8(0x30), UInt8(0x40)], [1, 2])
        let decoded = dequantized(
            packed,
            scales: scales,
            biases: nil,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4,
            dtype: .float32
        )

        #expect(
            decoded.asArray(Float.self)
                == Array(repeating: Float(0.5), count: 16)
                + Array(repeating: Float(2), count: 16)
        )
    }

    @Test
    func nvfp4Group16SplitKMatchesNonSplitReferenceWhenRuntimeTestsAreEnabled() {
        guard nvfp4RuntimeTestsEnabled else { return }

        let m = 32
        let n = 128
        let k = 64
        let weight = deterministicNVFP4Source(shape: [n, k], salt: 3)
        let x = deterministicNVFP4Source(shape: [m, k], salt: 11)
        let (packedWeight, scales, biases) = quantized(
            weight,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4
        )
        #expect(packedWeight.shape == [n, k / 8])
        #expect(scales.shape == [n, k / 16])
        #expect(biases == nil)

        let splitK = quantizedMM(
            x,
            packedWeight,
            scales: scales,
            biases: biases,
            transpose: true,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4
        )
        let nonSplit = nvfp4NonSplitReference(
            x: x,
            packedWeight: packedWeight,
            scales: scales
        )

        expectNVFP4Close(
            splitK,
            nonSplit,
            rtol: 1e-3,
            atol: 1e-3,
            context:
                "NVFP4 M=32 N=128 K=64 group-16 split-K versus batched non-split qmm"
        )
    }

    @Test
    func affineGroup32SplitKRemainsUnchangedWhenRuntimeTestsAreEnabled() throws {
        guard nvfp4RuntimeTestsEnabled else { return }

        let m = 32
        let n = 128
        let k = 64
        let weight = deterministicNVFP4Source(shape: [n, k], salt: 7)
        let x = deterministicNVFP4Source(shape: [m, k], salt: 19)
        let (packedWeight, scales, biases) = quantized(
            weight,
            groupSize: 32,
            bits: 4,
            mode: .affine
        )
        let affineBiases = try #require(biases)

        let splitK = quantizedMM(
            x,
            packedWeight,
            scales: scales,
            biases: affineBiases,
            transpose: true,
            groupSize: 32,
            bits: 4,
            mode: .affine
        )
        let nonSplit = quantizedMM(
            stacked([x, x]),
            stacked([packedWeight, packedWeight]),
            scales: stacked([scales, scales]),
            biases: stacked([affineBiases, affineBiases]),
            transpose: true,
            groupSize: 32,
            bits: 4,
            mode: .affine
        )[0]

        expectNVFP4Close(
            splitK,
            nonSplit,
            rtol: 1e-3,
            atol: 1e-3,
            context: "affine M=32 N=128 K=64 group-32 split-K"
        )
    }

    @Test
    func nvfp4ActualSharedProjectionShapesMatchNonSplitReferenceWhenRuntimeTestsAreEnabled() {
        guard nvfp4RuntimeTestsEnabled else { return }
        defer { Memory.clearCache() }

        let projectionShapes = [
            (
                label: "shared gate/up",
                outputFeatures: LagunaConstants.sharedExpertIntermediateSize,
                inputFeatures: LagunaConstants.hiddenSize
            ),
            (
                label: "shared down",
                outputFeatures: LagunaConstants.hiddenSize,
                inputFeatures: LagunaConstants.sharedExpertIntermediateSize
            ),
        ]

        for (index, projection) in projectionShapes.enumerated() {
            let x = deterministicNVFP4Source(
                shape: [32, projection.inputFeatures],
                salt: 23 + index
            )
            let weight = deterministicNVFP4Source(
                shape: [projection.outputFeatures, projection.inputFeatures],
                salt: 41 + index
            )
            let (packedWeight, scales, biases) = quantized(
                weight,
                groupSize: LagunaConstants.quantizationGroupSize,
                bits: LagunaConstants.quantizationBits,
                mode: .nvfp4
            )
            #expect(biases == nil)

            let splitK = quantizedMM(
                x,
                packedWeight,
                scales: scales,
                biases: nil,
                transpose: true,
                groupSize: LagunaConstants.quantizationGroupSize,
                bits: LagunaConstants.quantizationBits,
                mode: .nvfp4
            )
            let nonSplit = nvfp4NonSplitReference(
                x: x,
                packedWeight: packedWeight,
                scales: scales
            )

            expectNVFP4Close(
                splitK,
                nonSplit,
                rtol: 2e-3,
                atol: 2e-3,
                context:
                    "\(projection.label) M=32 N=\(projection.outputFeatures) K=\(projection.inputFeatures)"
            )
        }
    }

    @Test
    func nvfp4GatherRoutedDecodeAndPrefillShapesMatchNonGatherReferenceWhenRuntimeTestsAreEnabled() {
        guard nvfp4RuntimeTestsEnabled else { return }
        defer { Memory.clearCache() }

        expectNVFP4GatherMatchesReference(
            label: "routed gate/up decode",
            expertCount: 4,
            outputFeatures: LagunaConstants.moeIntermediateSize,
            inputFeatures: LagunaConstants.hiddenSize,
            rowsPerRoute: 1,
            expertIndices: [3, 0, 2, 1, 3, 1, 0, 2],
            sortedIndices: false,
            salt: 59
        )

        expectNVFP4GatherMatchesReference(
            label: "routed gate/up multi-row prefill",
            expertCount: 4,
            outputFeatures: LagunaConstants.moeIntermediateSize,
            inputFeatures: LagunaConstants.hiddenSize,
            rowsPerRoute: 32,
            expertIndices: [0, 3, 1, 2],
            sortedIndices: false,
            salt: 67
        )

        // A representative sorted prefill subset. Sixteen one-row routes over
        // four experts satisfies the same B/E >= 4 dispatch condition as the
        // full 512-token, top-8 Laguna prefill without allocating all 256
        // experts in this regression test.
        expectNVFP4GatherMatchesReference(
            label: "routed down sorted prefill",
            expertCount: 4,
            outputFeatures: LagunaConstants.hiddenSize,
            inputFeatures: LagunaConstants.moeIntermediateSize,
            rowsPerRoute: 1,
            expertIndices: [
                0, 0, 0, 0,
                1, 1, 1, 1,
                2, 2, 2, 2,
                3, 3, 3, 3,
            ],
            sortedIndices: true,
            salt: 71
        )
    }

    @Test
    func sharedPrefillSwiGLUEpilogueMatchesStockBF16BitsWhenRuntimeTestsAreEnabled() {
        guard nvfp4RuntimeTestsEnabled else { return }
        defer { Memory.clearCache() }

        let rows = LagunaConstants.sharedExpertIntermediateSize
        let hidden = LagunaConstants.hiddenSize
        let x = deterministicNVFP4Source(shape: [1, 512, hidden], salt: 83)
            .asType(.bfloat16)
        let (gateWeight, gateScales, gateBiases) = quantized(
            deterministicNVFP4Source(shape: [rows, hidden], salt: 89),
            groupSize: 16,
            bits: 4,
            mode: .nvfp4
        )
        let (upWeight, upScales, upBiases) = quantized(
            deterministicNVFP4Source(shape: [rows, hidden], salt: 97),
            groupSize: 16,
            bits: 4,
            mode: .nvfp4
        )
        #expect(gateBiases == nil)
        #expect(upBiases == nil)

        let stockGateUp = quantizedMM(
            x,
            concatenated([gateWeight, upWeight], axis: 0),
            scales: concatenated([gateScales, upScales], axis: 0),
            biases: nil,
            transpose: true,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4)
        let stockGate = stockGateUp[.ellipsis, 0 ..< rows]
        let stockUp = stockGateUp[.ellipsis, rows...]
        let stockActivation = (MLXNN.silu(stockGate) * stockUp).asType(.bfloat16)

        let interleavedWeight = concatenated([
            gateWeight.reshaped([rows / 16, 16, hidden / 8]),
            upWeight.reshaped([rows / 16, 16, hidden / 8]),
        ], axis: 1).reshaped([2 * rows, hidden / 8])
        let interleavedScaleStorage = concatenated([
            gateScales.reshaped([rows / 16, 16, hidden / 16]),
            upScales.reshaped([rows / 16, 16, hidden / 16]),
        ], axis: 1).reshaped([2 * rows, hidden / 16])

        let rawInterleaved = quantizedMM(
            x, interleavedWeight, scales: interleavedScaleStorage, biases: nil,
            transpose: true, groupSize: 16, bits: 4, mode: .nvfp4
        ).reshaped([1, 512, rows / 16, 32])
        let rawGate = rawInterleaved[.ellipsis, 0 ..< 16]
            .reshaped([1, 512, rows])
        let rawUp = rawInterleaved[.ellipsis, 16...]
            .reshaped([1, 512, rows])

        let markedScales = asStrided(
            interleavedScaleStorage,
            interleavedScaleStorage.shape,
            strides: [hidden / 16, 0],
            offset: 0)
        let fusedLogical = quantizedMM(
            x, interleavedWeight, scales: markedScales, biases: nil,
            transpose: true, groupSize: 16, bits: 4, mode: .nvfp4)
        let fusedActivation = fusedLogical.reshaped([-1])[0 ..< fusedLogical.size / 2]
            .reshaped([1, 512, rows])

        eval(stockGate, stockUp, stockActivation, rawGate, rawUp, fusedActivation)
        expectBF16BitsEqual(rawGate, stockGate, context: "interleaved gate")
        expectBF16BitsEqual(rawUp, stockUp, context: "interleaved up")
        expectBF16BitsEqual(fusedActivation, stockActivation, context: "fused SwiGLU")

        let expectedBits = stockActivation.view(dtype: .uint16).asArray(UInt16.self)
        var corruptedBits = expectedBits
        corruptedBits[expectedBits.count / 2] ^= 1
        #expect(corruptedBits != expectedBits)
    }

    @Test
    func realSharedPrefillSwiGLUEpilogueMatchesEveryCheckpointBankWhenRuntimeTestsAreEnabled() throws {
        guard nvfp4RuntimeTestsEnabled else { return }
        defer { Memory.clearCache() }

        let environment = ProcessInfo.processInfo.environment
        let weightsPath = environment["MLXFAST_REFERENCE_DIR"]
            ?? (FileManager.default.fileExists(atPath: MLXFastConstants.defaultWeightsPath)
                ? MLXFastConstants.defaultWeightsPath
                : MLXFastConstants.defaultReferencePath)
        let store = try DenseTensorStore(weightsPath: weightsPath)
        let bridge = MLXArrayTensorBridge()
        let testedRows = [2, 31, 32, 33, 511, 512, 513]
        var bankCount = 0
        var caseCount = 0
        var scoredActivationValues = 0
        var corruptionControlPassed = false

        for layer in 1...39 {
            let result = try verifyRealSharedExpertBank(
                layer: layer,
                store: store,
                bridge: bridge,
                testedRows: testedRows,
                isProductionSelection: layer <= 38
            )
            bankCount += 1
            caseCount += result.caseCount
            scoredActivationValues += result.scoredActivationValues
            corruptionControlPassed = corruptionControlPassed || result.corruptionControlPassed
            Memory.clearCache()
        }

        #expect(bankCount == 39)
        #expect(caseCount == 39 * testedRows.count)
        #expect(scoredActivationValues == 9_961_472)
        #expect(corruptionControlPassed)
    }
}

private let nvfp4RuntimeTestsEnabled =
    ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"

private func packNVFP4Nibbles(_ nibbles: [UInt8]) -> [UInt32] {
    precondition(nibbles.count.isMultiple(of: 8))
    return stride(from: 0, to: nibbles.count, by: 8).map { start in
        var word = UInt32(0)
        for offset in 0..<8 {
            word |= UInt32(nibbles[start + offset] & 0x0f) << (offset * 4)
        }
        return word
    }
}

private func deterministicNVFP4Source(shape: [Int], salt: Int) -> MLXArray {
    let count = shape.reduce(1, *)
    let values = (0..<count).map { index -> Float in
        let centered = ((index * 17 + salt) % 31) - 15
        return Float(centered) / 16
    }
    return MLXArray(values, shape)
}

private func expectBF16BitsEqual(
    _ actual: MLXArray,
    _ expected: MLXArray,
    context: String
) {
    #expect(actual.dtype == .bfloat16, Comment(rawValue: context))
    #expect(expected.dtype == .bfloat16, Comment(rawValue: context))
    #expect(actual.shape == expected.shape, Comment(rawValue: context))
    let actualBits = actual.view(dtype: .uint16).asArray(UInt16.self)
    let expectedBits = expected.view(dtype: .uint16).asArray(UInt16.self)
    #expect(actualBits == expectedBits, Comment(rawValue: context))
}

private struct RealSharedExpertBankResult {
    let caseCount: Int
    let scoredActivationValues: Int
    let corruptionControlPassed: Bool
}

private func verifyRealSharedExpertBank(
    layer: Int,
    store: DenseTensorStore,
    bridge: MLXArrayTensorBridge,
    testedRows: [Int],
    isProductionSelection: Bool
) throws -> RealSharedExpertBankResult {
    let gateWeight = try loadRealSharedExpertArray(
        layer: layer,
        suffix: "shared_expert.gate_proj.weight",
        expectedDType: "U32",
        expectedShape: [512, 256],
        store: store,
        bridge: bridge)
    let gateScales = try loadRealSharedExpertArray(
        layer: layer,
        suffix: "shared_expert.gate_proj.scales",
        expectedDType: "U8",
        expectedShape: [512, 128],
        store: store,
        bridge: bridge)
    let upWeight = try loadRealSharedExpertArray(
        layer: layer,
        suffix: "shared_expert.up_proj.weight",
        expectedDType: "U32",
        expectedShape: [512, 256],
        store: store,
        bridge: bridge)
    let upScales = try loadRealSharedExpertArray(
        layer: layer,
        suffix: "shared_expert.up_proj.scales",
        expectedDType: "U8",
        expectedShape: [512, 128],
        store: store,
        bridge: bridge)
    let downWeight = try loadRealSharedExpertArray(
        layer: layer,
        suffix: "shared_expert.down_proj.weight",
        expectedDType: "U32",
        expectedShape: [2048, 64],
        store: store,
        bridge: bridge)
    let downScales = try loadRealSharedExpertArray(
        layer: layer,
        suffix: "shared_expert.down_proj.scales",
        expectedDType: "U8",
        expectedShape: [2048, 32],
        store: store,
        bridge: bridge)

    let candidate = makeRealSharedExpertMLP(
        gateWeight: gateWeight,
        gateScales: gateScales,
        upWeight: upWeight,
        upScales: upScales,
        downWeight: downWeight,
        downScales: downScales)
    let control = makeRealSharedExpertMLP(
        gateWeight: gateWeight,
        gateScales: gateScales,
        upWeight: upWeight,
        upScales: upScales,
        downWeight: downWeight,
        downScales: downScales)
    let candidatePrepared = candidate.prepareFusedSharedGateUp()
    let controlPrepared = control.prepareFusedSharedGateUp()
    eval(candidatePrepared)
    eval(controlPrepared)
    control._fusedPrefillGateUpWeight = nil
    control._fusedPrefillGateUpScales = nil

    let fusedWeight = try requireSharedArray(
        candidate._fusedGateUpWeight,
        context: "layer \(layer) fused gate/up weight")
    let fusedScales = try requireSharedArray(
        candidate._fusedGateUpScales,
        context: "layer \(layer) fused gate/up scales")
    let interleavedWeight = try requireSharedArray(
        candidate._fusedPrefillGateUpWeight,
        context: "layer \(layer) interleaved gate/up weight")
    let markedScales = try requireSharedArray(
        candidate._fusedPrefillGateUpScales,
        context: "layer \(layer) marked gate/up scales")
    #expect(candidate._fusedGateUpSplit == 512)
    #expect(fusedWeight.dtype == .uint32)
    #expect(fusedWeight.shape == [1024, 256])
    #expect(fusedScales.dtype == .uint8)
    #expect(fusedScales.shape == [1024, 128])
    #expect(interleavedWeight.dtype == .uint32)
    #expect(interleavedWeight.shape == [1024, 256])
    #expect(markedScales.dtype == .uint8)
    #expect(markedScales.shape == [1024, 128])
    #expect(markedScales.asData(access: .noCopy).strides == [128, 0])

    let interleavedScaleStorage = concatenated([
        gateScales.reshaped([32, 16, 128]),
        upScales.reshaped([32, 16, 128]),
    ], axis: 1).reshaped([1024, 128])
    let down = candidate.downProj
    var scoredActivationValues = 0
    var corruptionControlPassed = false

    for rows in testedRows {
        let context = "layer \(layer), rows \(rows)"
        let x = adversarialSharedExpertInput(
            batch: 1,
            rows: rows,
            salt: layer * 1009 + rows,
            includeNonfinite: layer == 1)
        let stockGateUp = quantizedMM(
            x,
            fusedWeight,
            scales: fusedScales,
            biases: nil,
            transpose: true,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4)
        let stockGate = stockGateUp[.ellipsis, 0 ..< 512]
        let stockUp = stockGateUp[.ellipsis, 512...]
        let rawInterleaved = quantizedMM(
            x,
            interleavedWeight,
            scales: interleavedScaleStorage,
            biases: nil,
            transpose: true,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4
        ).reshaped([1, rows, 32, 32])
        let rawGate = rawInterleaved[.ellipsis, 0 ..< 16]
            .reshaped([1, rows, 512])
        let rawUp = rawInterleaved[.ellipsis, 16...]
            .reshaped([1, rows, 512])
        eval(stockGate, stockUp, rawGate, rawUp)
        expectBF16BitsEqual(rawGate, stockGate, context: "\(context) raw gate")
        expectBF16BitsEqual(rawUp, stockUp, context: "\(context) raw up")

        if rows == 512 {
            let expectedActivation = (MLXNN.silu(stockGate) * stockUp).asType(.bfloat16)
            let fusedLogical = quantizedMM(
                x,
                interleavedWeight,
                scales: markedScales,
                biases: nil,
                transpose: true,
                groupSize: 16,
                bits: 4,
                mode: .nvfp4)
            let actualActivation = fusedLogical.reshaped([-1])[0 ..< fusedLogical.size / 2]
                .reshaped([1, 512, 512])
            let expectedDown = down(expectedActivation)
            let actualDown = candidate(x)
            eval(expectedActivation, actualActivation, expectedDown, actualDown)
            expectBF16BitsEqual(
                actualActivation,
                expectedActivation,
                context: "\(context) fused activation")
            expectBF16BitsEqual(
                actualDown,
                expectedDown,
                context: "\(context) shared down")
            if isProductionSelection {
                scoredActivationValues += actualActivation.size
            }
            if layer == 1 {
                let actualBits = actualActivation.view(dtype: .uint16).asArray(UInt16.self)
                var corruptedBits = expectedActivation.view(dtype: .uint16).asArray(UInt16.self)
                corruptedBits[corruptedBits.count / 2] ^= 1
                #expect(corruptedBits != actualBits)
                corruptionControlPassed = true
            }
        } else {
            let expectedDown = control(x)
            let actualDown = candidate(x)
            eval(expectedDown, actualDown)
            expectBF16BitsEqual(
                actualDown,
                expectedDown,
                context: "\(context) unselected-row fallback")
        }
    }

    if layer == 1 {
        let decode = adversarialSharedExpertInput(
            batch: 1, rows: 1, salt: 2029, includeNonfinite: false)
        let decodeExpected = control(decode)
        let decodeActual = candidate(decode)
        eval(decodeExpected, decodeActual)
        expectBF16BitsEqual(
            decodeActual,
            decodeExpected,
            context: "one-token decode remains unchanged")

        let floatPrefill = adversarialSharedExpertInput(
            batch: 1, rows: 512, salt: 2039, includeNonfinite: false
        ).asType(.float32)
        let floatExpected = control(floatPrefill)
        let floatActual = candidate(floatPrefill)
        eval(floatExpected, floatActual)
        expectFloat32BitsEqual(
            floatActual,
            floatExpected,
            context: "float32 prefill fallback")

        let batched = adversarialSharedExpertInput(
            batch: 2, rows: 32, salt: 2053, includeNonfinite: false)
        let batchedExpected = control(batched)
        let batchedActual = candidate(batched)
        eval(batchedExpected, batchedActual)
        expectBF16BitsEqual(
            batchedActual,
            batchedExpected,
            context: "unsupported batch-shape fallback")
    }

    return RealSharedExpertBankResult(
        caseCount: testedRows.count,
        scoredActivationValues: scoredActivationValues,
        corruptionControlPassed: corruptionControlPassed)
}

private func loadRealSharedExpertArray(
    layer: Int,
    suffix: String,
    expectedDType: String,
    expectedShape: [Int],
    store: DenseTensorStore,
    bridge: MLXArrayTensorBridge
) throws -> MLXArray {
    let name = LagunaWeightNames.mlp(layer, suffix)
    guard let record = store.record(named: name) else {
        throw MLXFastError.invalidInput("missing real shared-expert tensor \(name)")
    }
    #expect(record.dtype == expectedDType, Comment(rawValue: name))
    #expect(record.shape == expectedShape, Comment(rawValue: name))
    let array = try bridge.makeArray(from: store.materializedTensor(named: name))
    #expect(array.shape == expectedShape, Comment(rawValue: name))
    if expectedDType == "U32" {
        #expect(array.dtype == .uint32, Comment(rawValue: name))
    } else {
        #expect(array.dtype == .uint8, Comment(rawValue: name))
    }
    return array
}

private func makeRealSharedExpertMLP(
    gateWeight: MLXArray,
    gateScales: MLXArray,
    upWeight: MLXArray,
    upScales: MLXArray,
    downWeight: MLXArray,
    downScales: MLXArray
) -> LagunaRuntimeMLP {
    let mlp = LagunaRuntimeMLP(dimensions: 2048, hiddenDimensions: 512)
    mlp.gateProj = QuantizedLinear(
        weight: gateWeight,
        scales: gateScales,
        biases: nil,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4)
    mlp.upProj = QuantizedLinear(
        weight: upWeight,
        scales: upScales,
        biases: nil,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4)
    mlp.downProj = QuantizedLinear(
        weight: downWeight,
        scales: downScales,
        biases: nil,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4)
    return mlp
}

private func requireSharedArray(
    _ array: MLXArray?,
    context: String
) throws -> MLXArray {
    guard let array else {
        throw MLXFastError.invalidInput("missing \(context)")
    }
    return array
}

private func adversarialSharedExpertInput(
    batch: Int,
    rows: Int,
    salt: Int,
    includeNonfinite: Bool
) -> MLXArray {
    let hidden = 2048
    var palette: [UInt16] = [
        0x0000, 0x8000,
        0x0001, 0x8001,
        0x007f, 0x807f,
        0x0080, 0x8080,
        0x3f00, 0xbf00,
        0x3f80, 0xbf80,
        0x4000, 0xc000,
        0x7f7f, 0xff7f,
    ]
    if includeNonfinite {
        palette.append(contentsOf: [0x7f80, 0xff80, 0x7fc1, 0xffc1])
    }
    var bits = [UInt16](repeating: 0, count: batch * rows * hidden)
    for index in bits.indices {
        bits[index] = palette[(index * 17 + salt) % palette.count]
    }
    let boundaryColumns = [0, 1, 15, 16, 31, 32, 127, 128, 255, 256, 511, 512, 1023, 1024, 2047]
    for batchIndex in 0..<batch {
        let rowStart = (batchIndex * rows + rows - 1) * hidden
        for (index, column) in boundaryColumns.enumerated() {
            bits[rowStart + column] = palette[(salt + index * 3) % palette.count]
        }
    }
    return MLXArray(bits, [batch, rows, hidden]).view(dtype: .bfloat16)
}

private func expectFloat32BitsEqual(
    _ actual: MLXArray,
    _ expected: MLXArray,
    context: String
) {
    #expect(actual.dtype == .float32, Comment(rawValue: context))
    #expect(expected.dtype == .float32, Comment(rawValue: context))
    #expect(actual.shape == expected.shape, Comment(rawValue: context))
    let actualBits = actual.view(dtype: .uint32).asArray(UInt32.self)
    let expectedBits = expected.view(dtype: .uint32).asArray(UInt32.self)
    #expect(actualBits == expectedBits, Comment(rawValue: context))
}

private func nvfp4NonSplitReference(
    x: MLXArray,
    packedWeight: MLXArray,
    scales: MLXArray
) -> MLXArray {
    quantizedMM(
        stacked([x, x]),
        stacked([packedWeight, packedWeight]),
        scales: stacked([scales, scales]),
        biases: nil,
        transpose: true,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4
    )[0]
}

private func expectNVFP4GatherMatchesReference(
    label: String,
    expertCount: Int,
    outputFeatures: Int,
    inputFeatures: Int,
    rowsPerRoute: Int,
    expertIndices: [Int],
    sortedIndices: Bool,
    salt: Int
) {
    let weight = deterministicNVFP4Source(
        shape: [expertCount, outputFeatures, inputFeatures],
        salt: salt
    )
    let (packedWeight, scales, biases) = quantized(
        weight,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4
    )
    precondition(biases == nil)

    let x = deterministicNVFP4Source(
        shape: [expertIndices.count, rowsPerRoute, inputFeatures],
        salt: salt + 13
    )
    let indices = MLXArray(expertIndices.map(UInt32.init), [expertIndices.count])
    let gathered = gatherQuantizedMM(
        x,
        packedWeight,
        scales: scales,
        biases: nil,
        rhsIndices: indices,
        transpose: true,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4,
        sortedIndices: sortedIndices
    )

    let selectedWeights = stacked(expertIndices.map { packedWeight[$0] })
    let selectedScales = stacked(expertIndices.map { scales[$0] })
    let nonGather = quantizedMM(
        x,
        selectedWeights,
        scales: selectedScales,
        biases: nil,
        transpose: true,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4
    )

    expectNVFP4Close(
        gathered,
        nonGather,
        rtol: 2e-3,
        atol: 2e-3,
        context:
            "\(label) B=\(expertIndices.count) M=\(rowsPerRoute) N=\(outputFeatures) K=\(inputFeatures)"
    )
}

private func expectNVFP4Close(
    _ actual: MLXArray,
    _ expected: MLXArray,
    rtol: Double,
    atol: Double,
    context: String
) {
    #expect(actual.shape == expected.shape, Comment(rawValue: context))
    let finite = isFinite(actual).all()
    let close = actual.allClose(expected, rtol: rtol, atol: atol)
    let maxError = abs(actual.asType(.float32) - expected.asType(.float32)).max()
    eval(finite, close, maxError)

    let maxErrorValue = maxError.item(Float.self)
    #expect(
        finite.item(Bool.self),
        Comment(rawValue: "\(context): output contains non-finite values")
    )
    #expect(
        close.item(Bool.self),
        Comment(rawValue: "\(context): max absolute error \(maxErrorValue)")
    )
}
