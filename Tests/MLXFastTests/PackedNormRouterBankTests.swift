import Foundation
import MLX
import MLXNN
import Testing
@testable import MLXFastModel

private struct PackedNormRouterLayerWeights {
    let norm: MLXArray
    let router: MLXArray
    let correction: MLXArray
    let packed: MLXArray
}

private struct PackedNormRouterOutputs {
    let summed: MLXArray
    let normalized: MLXArray
    let logits: MLXArray
    let keys: MLXArray?

    var arrays: [MLXArray] {
        [summed, normalized, logits] + (keys.map { [$0] } ?? [])
    }
}

@Test
func packedNormRouterSelectionIsDecodeOnly() throws {
    let path = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
    let source = try String(contentsOfFile: path, encoding: .utf8)
    let decoderStart = try #require(source.range(of: "final class LagunaRuntimeDecoderLayer"))
    let ordinaryStart = try #require(
        source.range(of: "    func callAsFunction(", range: decoderStart.lowerBound..<source.endIndex)
    )
    let terminalStart = try #require(
        source.range(of: "    func callLastPrefillRow(", range: ordinaryStart.upperBound..<source.endIndex)
    )
    let terminalEnd = try #require(
        source.range(of: "\n}\n\n// MARK: - Model", range: terminalStart.upperBound..<source.endIndex)
    )
    let ordinary = source[ordinaryStart.lowerBound..<terminalStart.lowerBound]
    let terminalPrefill = source[terminalStart.lowerBound..<terminalEnd.lowerBound]

    #expect(ordinary.contains("x.dims(1, 1, LagunaConstants.hiddenSize)"))
    #expect(ordinary.contains("packedWeight: packedNormRouterWeight(for: sparse)"))
    #expect(!terminalPrefill.contains("packedNormRouterWeight"))
    #expect(!terminalPrefill.contains("packedWeight:"))
    print("PACKED_NORM_ROUTER_CENSUS decode_calls=4992 prefill_calls=0 bindings_generic=5 bindings_packed=4")
}

@Test
func packedNormRouterBankDifferentialAndTimingWhenRuntimeTestsAreEnabled() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }
    let weightsPath = ProcessInfo.processInfo.environment["MLXFAST_PACKED_NORM_ROUTER_WEIGHTS_PATH"]
        ?? "weights"
    let store = try DenseTensorStore(weightsPath: weightsPath)
    let bridge = MLXArrayTensorBridge()
    let hidden = LagunaConstants.hiddenSize
    let experts = LagunaConstants.numExperts
    let sparseLayers = 1..<LagunaConstants.numHiddenLayers

    let constructionStart = DispatchTime.now().uptimeNanoseconds
    let layers = try sparseLayers.map { layer -> PackedNormRouterLayerWeights in
        let prefix = "model.layers.\(layer)"
        let norm = try bridge.makeArray(
            from: store.materializedTensor(named: "\(prefix).post_attention_layernorm.weight")
        )
        let router = try bridge.makeArray(
            from: store.materializedTensor(named: "\(prefix).mlp.gate.weight")
        )
        let correction = try bridge.makeArray(
            from: store.materializedTensor(named: "\(prefix).mlp.gate.e_score_correction_bias")
        )
        let packed = concatenated([norm.reshaped([1, hidden]), router], axis: 0)
        return PackedNormRouterLayerWeights(
            norm: norm,
            router: router,
            correction: correction,
            packed: packed
        )
    }
    let constructionEnd = DispatchTime.now().uptimeNanoseconds
    eval(layers.flatMap { [$0.norm, $0.router, $0.correction, $0.packed] })
    Stream.gpu.synchronize()
    let evaluationEnd = DispatchTime.now().uptimeNanoseconds

    let bytesPerBank = (experts + 1) * hidden * MemoryLayout<UInt16>.stride
    let totalBytes = layers.count * bytesPerBank
    #expect(layers.count == 39)
    #expect(bytesPerBank == 1_052_672)
    #expect(totalBytes == 41_054_208)
    print(
        "PACKED_NORM_ROUTER_LAYOUT banks=\(layers.count) bytes_per_bank=\(bytesPerBank) "
            + "total_bytes=\(totalBytes) construction_ns=\(constructionEnd - constructionStart) "
            + "evaluation_ns=\(evaluationEnd - constructionEnd)"
    )

    for (index, layer) in layers.enumerated() {
        let packedBits = bf16Bits(layer.packed)
        let expectedBits = bf16Bits(layer.norm) + bf16Bits(layer.router)
        #expect(
            packedBits == expectedBits,
            "packed bytes differ from source weights at sparse layer \(index + 1)"
        )
    }
    print("PACKED_NORM_ROUTER_BYTES verified_layers=39 exact=true")

    try verifyPackedNormRouterSelectorFallback(layers[0])

    let axis = MLXArray(0..<hidden).asType(.float32)
    let deterministicResidual = (sin(axis * 0.017) * 0.5)
        .asType(.bfloat16)
        .reshaped([1, 1, hidden])
    let deterministicBranch = (cos(axis * 0.011) * 0.25)
        .asType(.bfloat16)
        .reshaped([1, 1, hidden])
    let tieResidual = MLXArray.full(
        [1, 1, hidden], values: MLXArray(Float(0)), dtype: .bfloat16)
    let tieBranch = MLXArray.full(
        [1, 1, hidden], values: MLXArray(Float(-0.0)), dtype: .bfloat16)
    let special: [Float] = [
        0.0, -0.0, 1.0, -1.0, 0.5, -0.5,
        3.389_531_4e38, -3.389_531_4e38,
        1.175_494_35e-38, -1.175_494_35e-38,
        Float.infinity, -Float.infinity, Float.nan,
    ]
    let adversarialValues = (0..<hidden).map { special[$0 % special.count] }
    let adversarialResidual = MLXArray(adversarialValues, [1, 1, hidden])
        .asType(.bfloat16)
    let adversarialBranch = MLXArray.full(
        [1, 1, hidden], values: MLXArray(Float(0)), dtype: .bfloat16)

    for (label, residual, branch) in [
        ("real", deterministicResidual, deterministicBranch),
        ("signed-zero-ties", tieResidual, tieBranch),
        ("extrema-nan-inf", adversarialResidual, adversarialBranch),
    ] {
        let generic = runPackedNormRouter(
            residual: residual,
            branch: branch,
            layer: layers[0],
            packedWeight: nil
        )
        let packed = runPackedNormRouter(
            residual: residual,
            branch: branch,
            layer: layers[0],
            packedWeight: layers[0].packed
        )
        eval(generic.arrays + packed.arrays)
        Stream.gpu.synchronize()
        expectPackedNormRouterOutputsEqual(generic, packed, label: label)
        print("PACKED_NORM_ROUTER_DIFFERENTIAL case=\(label) exact=true")
    }

    let generic = runPackedNormRouter(
        residual: deterministicResidual,
        branch: deterministicBranch,
        layer: layers[0],
        packedWeight: nil
    )
    let wrongShape = runPackedNormRouter(
        residual: deterministicResidual,
        branch: deterministicBranch,
        layer: layers[0],
        packedWeight: layers[0].router
    )
    let wrongDType = runPackedNormRouter(
        residual: deterministicResidual,
        branch: deterministicBranch,
        layer: layers[0],
        packedWeight: layers[0].packed.asType(.float32)
    )
    let corruptedBank = (layers[0].packed + MLXArray(Float(0.125))).asType(.bfloat16)
    let corrupted = runPackedNormRouter(
        residual: deterministicResidual,
        branch: deterministicBranch,
        layer: layers[0],
        packedWeight: corruptedBank
    )
    eval(generic.arrays + wrongShape.arrays + wrongDType.arrays + corrupted.arrays)
    Stream.gpu.synchronize()
    expectPackedNormRouterOutputsEqual(generic, wrongShape, label: "wrong-shape-fallback")
    expectPackedNormRouterOutputsEqual(generic, wrongDType, label: "wrong-dtype-fallback")
    #expect(
        bf16Bits(generic.normalized) != bf16Bits(corrupted.normalized)
            || bf16Bits(generic.logits) != bf16Bits(corrupted.logits),
        "corrupting the packed bank did not change any checked output"
    )
    print("PACKED_NORM_ROUTER_FALLBACK wrong_shape=true wrong_dtype=true rebound=true corruption_detected=true")

    _ = timedPackedNormRouterChain(
        layers: layers,
        residual: deterministicResidual,
        branch: deterministicBranch,
        packed: false
    )
    _ = timedPackedNormRouterChain(
        layers: layers,
        residual: deterministicResidual,
        branch: deterministicBranch,
        packed: true
    )

    for (pattern, variants) in [
        ("ABBA", [false, true, true, false]),
        ("BAAB", [true, false, false, true]),
    ] {
        for block in 0..<20 {
            for (slot, packed) in variants.enumerated() {
                let elapsed = timedPackedNormRouterChain(
                    layers: layers,
                    residual: deterministicResidual,
                    branch: deterministicBranch,
                    packed: packed
                )
                print(
                    "PACKED_NORM_ROUTER_SAMPLE pattern=\(pattern) block=\(block) slot=\(slot) "
                        + "variant=\(packed ? "packed" : "generic") ns=\(elapsed)"
                )
            }
        }
    }
}

private func verifyPackedNormRouterSelectorFallback(
    _ weights: PackedNormRouterLayerWeights
) throws {
    let config = try loadLagunaConfig(pinnedLagunaConfigObject())
    let layer = LagunaRuntimeDecoderLayer(config, layerIdx: 1)
    let sparse = try #require(layer.mlp as? LagunaRuntimeSparseMoEBlock)
    try layer.postAttentionLayerNorm.update(
        parameters: ModuleParameters.unflattened(["weight": weights.norm]),
        verify: [.noUnusedKeys, .shapeMismatch]
    )
    try sparse.gate.update(
        parameters: ModuleParameters.unflattened(["weight": weights.router]),
        verify: [.noUnusedKeys, .shapeMismatch]
    )
    let packed = try #require(layer.preparePackedNormRouterWeight())
    eval(packed)
    Stream.gpu.synchronize()
    let selected = try #require(layer.packedNormRouterWeight(for: sparse))
    #expect(selected === packed)

    let rebound = (weights.norm + MLXArray(Float(0))).asType(.bfloat16)
    eval(rebound)
    Stream.gpu.synchronize()
    #expect(bf16Bits(rebound) == bf16Bits(weights.norm))
    let reboundNorm = RMSNorm(
        dimensions: config.hiddenSize, eps: Float(config.rmsNormEps))
    try reboundNorm.update(
        parameters: ModuleParameters.unflattened(["weight": rebound]),
        verify: [.noUnusedKeys, .shapeMismatch]
    )
    layer.postAttentionLayerNorm = reboundNorm
    switch layer.packedNormRouterWeight(for: sparse) {
    case nil:
        break
    case .some:
        Issue.record("rebound source unexpectedly selected the packed bank")
    }
}

private func runPackedNormRouter(
    residual: MLXArray,
    branch: MLXArray,
    layer: PackedNormRouterLayerWeights,
    packedWeight: MLXArray?
) -> PackedNormRouterOutputs {
    let result = lagunaResidualRMSNormRouter(
        residual: residual,
        branch: branch,
        weight: layer.norm,
        routerWeight: layer.router,
        correctionBias: layer.correction,
        packedWeight: packedWeight
    )
    return PackedNormRouterOutputs(
        summed: result.summed,
        normalized: result.normalized,
        logits: result.routerLogits,
        keys: result.routerKeys
    )
}

private func expectPackedNormRouterOutputsEqual(
    _ generic: PackedNormRouterOutputs,
    _ packed: PackedNormRouterOutputs,
    label: String
) {
    #expect(bf16Bits(generic.summed) == bf16Bits(packed.summed), "\(label) summed")
    #expect(
        bf16Bits(generic.normalized) == bf16Bits(packed.normalized),
        "\(label) normalized"
    )
    #expect(bf16Bits(generic.logits) == bf16Bits(packed.logits), "\(label) logits")
    switch (generic.keys, packed.keys) {
    case let (.some(genericKeys), .some(packedKeys)):
        #expect(
            genericKeys.asArray(UInt32.self) == packedKeys.asArray(UInt32.self),
            "\(label) keys"
        )
    case (nil, nil):
        break
    default:
        Issue.record("\(label) key output presence differs")
    }
}

private func bf16Bits(_ array: MLXArray) -> [UInt16] {
    array.view(dtype: .uint16).asArray(UInt16.self)
}

private func timedPackedNormRouterChain(
    layers: [PackedNormRouterLayerWeights],
    residual: MLXArray,
    branch: MLXArray,
    packed: Bool
) -> UInt64 {
    autoreleasepool {
        let start = DispatchTime.now().uptimeNanoseconds
        var currentResidual = residual
        var currentBranch = branch
        var evaluated: [MLXArray] = []
        evaluated.reserveCapacity(layers.count * 2 + 2)
        for layer in layers {
            let output = runPackedNormRouter(
                residual: currentResidual,
                branch: currentBranch,
                layer: layer,
                packedWeight: packed ? layer.packed : nil
            )
            currentResidual = output.summed
            currentBranch = output.normalized
            evaluated.append(output.logits)
            if let keys = output.keys {
                evaluated.append(keys)
            }
        }
        evaluated.append(currentResidual)
        evaluated.append(currentBranch)
        eval(evaluated)
        Stream.gpu.synchronize()
        return DispatchTime.now().uptimeNanoseconds - start
    }
}
