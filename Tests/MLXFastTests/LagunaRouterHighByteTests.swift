import Foundation
import MLX
import MLXFastCore
@testable import MLXFastModel
import MLXNN
import Testing

private let routerExperts = 256
private let routerHidden = 2_048

private struct RouterHighByteFixture {
    let payload: MLXArray
    let offsets: MLXArray
    let dense: MLXArray
    let norm: MLXArray
    let bias: MLXArray
}

private enum RouterHighByteArm {
    case compact
    case dense
}

@Test
func lagunaRouterHighByteProofWhenEnabled() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_ROUTER_HIGHBYTE_PROOF"] == "1" else {
        return
    }

    let weightsPath = ProcessInfo.processInfo.environment[
        "MLXFAST_LAGUNA_EQUIVALENCE_WEIGHTS_PATH"
    ] ?? URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        .appendingPathComponent("weights").path
    let config = try LagunaConfig.load(from: weightsPath)
    let loader = try LagunaWeightLoader(weightsPath: weightsPath)
    let bridge = MLXArrayTensorBridge()
    let layers = (0..<config.numHiddenLayers).filter { config.isSparse(layer: $0) }
    var fixtures: [RouterHighByteFixture] = []
    var reconstructedWords = 0
    var compactRows = 0

    let residual = deterministicRouterInput(rows: 1, multiplier: 7, modulus: 37)
    let branch = deterministicRouterInput(rows: 1, multiplier: 11, modulus: 41)
    let prefill = deterministicRouterInput(rows: 4, multiplier: 13, modulus: 43)

    for layer in layers {
        let weightName = LagunaWeightNames.mlp(layer, "gate.weight")
        let payloadTensor = try loader.denseStore.materializedTensor(named: weightName)
        let offsetsTensor = try loader.denseStore.materializedTensor(
            named: weightName + "_row_offsets"
        )
        let denseTensor = try independentlyExpandRouter(
            payload: payloadTensor,
            offsets: offsetsTensor
        )
        let payload = try bridge.makeArray(from: payloadTensor)
        let offsets = try bridge.makeArray(from: offsetsTensor)
        let dense = try bridge.makeArray(from: denseTensor)
        let norm = try bridge.makeArray(
            from: loader.denseStore.materializedTensor(
                named: LagunaWeightNames.layer(layer, "post_attention_layernorm.weight")
            )
        )
        let bias = try bridge.makeArray(
            from: loader.denseStore.materializedTensor(
                named: LagunaWeightNames.mlp(layer, "gate.e_score_correction_bias")
            )
        )
        let layerCompactRows = try offsetsTensor.uint32Values().filter {
            ($0 & 0x8000_0000) == 0
        }.count
        let fixture = RouterHighByteFixture(
            payload: payload,
            offsets: offsets,
            dense: dense,
            norm: norm,
            bias: bias
        )
        fixtures.append(fixture)
        compactRows += layerCompactRows

        let expanded = lagunaExpandRouter(payload, offsets: offsets)
        eval(expanded, dense)
        let expandedValues = expanded.asArray(Float.self)
        #expect(expandedValues == dense.asArray(Float.self), "expanded router layer \(layer)")
        reconstructedWords += expandedValues.count

        let candidate = lagunaResidualRMSNormRouter(
            residual: residual,
            branch: branch,
            weight: norm,
            routerWeight: payload,
            routerOffsets: offsets,
            correctionBias: bias
        )
        let referenceNorm = lagunaResidualRMSNorm(
            residual: residual,
            branch: branch,
            weight: norm
        )
        let referenceLogits = referenceNorm.1.matmul(dense.T)
        eval([
            candidate.summed,
            candidate.normalized,
            candidate.routerLogits,
            referenceNorm.0,
            referenceNorm.1,
            referenceLogits,
        ])
        #expect(
            candidate.summed.asArray(Float.self) == referenceNorm.0.asArray(Float.self),
            "summed residual layer \(layer)"
        )
        #expect(
            candidate.normalized.asArray(Float.self) == referenceNorm.1.asArray(Float.self),
            "normalized residual layer \(layer)"
        )
        #expect(
            candidate.routerLogits.asArray(Float.self) == referenceLogits.asArray(Float.self),
            "decode router logits layer \(layer)"
        )

        let candidateGate = LagunaRuntimeMoEGate(config)
        candidateGate.update(parameters: ModuleParameters.unflattened([
            "weight": payload,
            "weight_row_offsets": offsets,
            "e_score_correction_bias": bias,
        ]))
        let referenceGate = LagunaRuntimeMoEGate(config)
        referenceGate.update(parameters: ModuleParameters.unflattened([
            "e_score_correction_bias": bias,
        ]))

        let candidateDecode = candidateGate(
            candidate.normalized,
            logits: candidate.routerLogits
        )
        let referenceDecode = referenceGate(referenceNorm.1, logits: referenceLogits)
        let expandedPrefillLogits = prefill.matmul(expanded.T)
        let densePrefillLogits = prefill.matmul(dense.T)
        let candidatePrefill = candidateGate(prefill)
        let referencePrefill = referenceGate(prefill, logits: densePrefillLogits)
        eval([
            candidateDecode.0,
            candidateDecode.1,
            referenceDecode.0,
            referenceDecode.1,
            expandedPrefillLogits,
            densePrefillLogits,
            candidatePrefill.0,
            candidatePrefill.1,
            referencePrefill.0,
            referencePrefill.1,
        ])
        #expect(
            candidateDecode.0.asArray(UInt32.self) == referenceDecode.0.asArray(UInt32.self),
            "decode selected experts layer \(layer)"
        )
        #expect(
            candidateDecode.1.asArray(Float.self) == referenceDecode.1.asArray(Float.self),
            "decode selected weights layer \(layer)"
        )
        #expect(
            expandedPrefillLogits.asArray(Float.self) == densePrefillLogits.asArray(Float.self),
            "prefill router logits layer \(layer)"
        )
        #expect(
            candidatePrefill.0.asArray(UInt32.self) == referencePrefill.0.asArray(UInt32.self),
            "prefill selected experts layer \(layer)"
        )
        #expect(
            candidatePrefill.1.asArray(Float.self) == referencePrefill.1.asArray(Float.self),
            "prefill selected weights layer \(layer)"
        )
    }

    #expect(fixtures.count == 39)
    #expect(reconstructedWords == 39 * routerExperts * routerHidden)
    print(
        "ROUTER_HIGHBYTE_CORRECTNESS layers=\(fixtures.count) words=\(reconstructedWords) "
            + "compact_rows=\(compactRows) raw_rows=\(fixtures.count * routerExperts - compactRows)"
    )

    _ = measureRouterArm(.compact, fixtures: fixtures, residual: residual, branch: branch)
    _ = measureRouterArm(.dense, fixtures: fixtures, residual: residual, branch: branch)
    var abbaCompact: [Double] = []
    var abbaDense: [Double] = []
    var baabCompact: [Double] = []
    var baabDense: [Double] = []
    for _ in 0..<16 {
        abbaCompact.append(
            measureRouterArm(.compact, fixtures: fixtures, residual: residual, branch: branch)
        )
        abbaDense.append(
            measureRouterArm(.dense, fixtures: fixtures, residual: residual, branch: branch)
        )
        abbaDense.append(
            measureRouterArm(.dense, fixtures: fixtures, residual: residual, branch: branch)
        )
        abbaCompact.append(
            measureRouterArm(.compact, fixtures: fixtures, residual: residual, branch: branch)
        )
    }
    for _ in 0..<16 {
        baabDense.append(
            measureRouterArm(.dense, fixtures: fixtures, residual: residual, branch: branch)
        )
        baabCompact.append(
            measureRouterArm(.compact, fixtures: fixtures, residual: residual, branch: branch)
        )
        baabCompact.append(
            measureRouterArm(.compact, fixtures: fixtures, residual: residual, branch: branch)
        )
        baabDense.append(
            measureRouterArm(.dense, fixtures: fixtures, residual: residual, branch: branch)
        )
    }
    let timing: [String: Any] = [
        "layers": fixtures.count,
        "compact_rows": compactRows,
        "raw_rows": fixtures.count * routerExperts - compactRows,
        "ABBA": ["candidate_us": abbaCompact, "baseline_us": abbaDense],
        "BAAB": ["candidate_us": baabCompact, "baseline_us": baabDense],
    ]
    let timingData = try JSONSerialization.data(withJSONObject: timing, options: [.sortedKeys])
    let timingJSON = try #require(String(data: timingData, encoding: .utf8))
    print("ROUTER_HIGHBYTE_TIMING \(timingJSON)")
}

private func independentlyExpandRouter(
    payload: MaterializedTensor,
    offsets: MaterializedTensor
) throws -> MaterializedTensor {
    guard payload.dtype == .u8, offsets.dtype == .u32, offsets.shape == [routerExperts] else {
        throw MLXFastError.invalidInput("compact router tensors have unexpected metadata")
    }
    let bytes = try payload.uint8Values()
    let rowOffsets = try offsets.uint32Values()
    var dense = Data()
    dense.reserveCapacity(routerExperts * routerHidden * 2)
    for tagged in rowOffsets {
        let base = Int(tagged & 0x7fff_ffff)
        if (tagged & 0x8000_0000) != 0 {
            guard base + routerHidden * 2 <= bytes.count else {
                throw MLXFastError.invalidInput("raw compact-router row exceeds payload")
            }
            dense.append(contentsOf: bytes[base..<(base + routerHidden * 2)])
        } else {
            guard base + routerHidden + routerHidden / 2 + 16 <= bytes.count else {
                throw MLXFastError.invalidInput("palette compact-router row exceeds payload")
            }
            for column in 0..<routerHidden {
                let packed = bytes[base + routerHidden + column / 2]
                let paletteIndex = column.isMultiple(of: 2) ? packed & 0x0f : packed >> 4
                dense.append(bytes[base + column])
                dense.append(bytes[base + routerHidden + routerHidden / 2 + Int(paletteIndex)])
            }
        }
    }
    return try MaterializedTensor(
        name: payload.name + ".independent_dense",
        dtype: .bf16,
        shape: [routerExperts, routerHidden],
        bytes: dense
    )
}

private func deterministicRouterInput(rows: Int, multiplier: Int, modulus: Int) -> MLXArray {
    let values = (0..<(rows * routerHidden)).map { index in
        Float((index * multiplier) % modulus - modulus / 2) / 32
    }
    return MLXArray(values, [1, rows, routerHidden]).asType(.bfloat16)
}

@inline(never)
private func measureRouterArm(
    _ arm: RouterHighByteArm,
    fixtures: [RouterHighByteFixture],
    residual: MLXArray,
    branch: MLXArray
) -> Double {
    let start = DispatchTime.now().uptimeNanoseconds
    let outputs: [MLXArray] = fixtures.map { fixture in
        switch arm {
        case .compact:
            return lagunaResidualRMSNormRouter(
                residual: residual,
                branch: branch,
                weight: fixture.norm,
                routerWeight: fixture.payload,
                routerOffsets: fixture.offsets,
                correctionBias: fixture.bias
            ).routerLogits
        case .dense:
            let normalized = lagunaResidualRMSNorm(
                residual: residual,
                branch: branch,
                weight: fixture.norm
            ).1
            return normalized.matmul(fixture.dense.T)
        }
    }
    eval(outputs)
    return Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000
}
