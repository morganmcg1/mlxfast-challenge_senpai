import Foundation
import MLX
@testable import MLXFastModel
import Testing

@Suite(.serialized)
struct LagunaOProjFinalResidualProbeTests {
    @Test
    func affinePlainAndIndexedH48H64AreBitExact() throws {
        guard runtimeProbeEnabled else { return }
        #expect(ProcessInfo.processInfo.environment["DARKBLOOM_OPROJ_FINAL_RESIDUAL"] == "1")

        let router = makeRouterInputs()
        for heads in [48, 64] {
            let input = makeProjectionInputs(heads: heads)
            let inVec = heads * 128
            let codes = MLXArray.full(
                [2_048, inVec / 4], values: MLXArray(UInt32(0x7f00_80ff)),
                dtype: .uint32)
            let scales = MLXArray.full(
                [2_048, inVec / 32], values: MLXArray(Float(0.001953125)),
                dtype: .bfloat16)
            let biases = MLXArray.full(
                [2_048, inVec / 32], values: MLXArray(Float(-0.015625)),
                dtype: .bfloat16)
            let indexed = indexedMetadata(scales: scales, biases: biases)

            let plainProjection = try #require(lagunaGatedAffineOProj(
                attentionOutput: input.attention, gateLogits: input.rawGate,
                codes: codes, scales: scales, biases: biases, heads: heads))
            let indexedProjection = try #require(lagunaGatedAffineOProj(
                attentionOutput: input.attention, gateLogits: input.rawGate,
                codes: codes, scales: scales, biases: biases,
                indexedMetadata: indexed, heads: heads))
            expectBitsEqual(plainProjection, indexedProjection, label: "affine-projection-H\(heads)")

            for (storage, metadata) in [("plain", nil), ("indexed", indexed)] {
                let projection = try #require(lagunaGatedAffineOProj(
                    attentionOutput: input.attention, gateLogits: input.rawGate,
                    codes: codes, scales: scales, biases: biases,
                    indexedMetadata: metadata, heads: heads))
                let fused = try #require(lagunaGatedAffineOProj(
                    attentionOutput: input.attention, gateLogits: input.rawGate,
                    codes: codes, scales: scales, biases: biases,
                    indexedMetadata: metadata, heads: heads, residual: input.residual))
                verifyFullChain(
                    label: "affine-\(storage)-H\(heads)", residual: input.residual,
                    projection: projection, fused: fused, router: router,
                    testCorruption: heads == 48 && storage == "plain")
            }
        }
    }

    @Test
    func nvfp4RawAndActivatedH48H64AreBitExact() throws {
        guard runtimeProbeEnabled else { return }
        #expect(ProcessInfo.processInfo.environment["DARKBLOOM_OPROJ_FINAL_RESIDUAL"] == "1")

        let router = makeRouterInputs()
        for heads in [48, 64] {
            let input = makeProjectionInputs(heads: heads)
            let inVec = heads * 128
            let codes = MLXArray.full(
                [2_048, inVec / 8], values: MLXArray(UInt32(0x7654_3210)),
                dtype: .uint32)
            let scales = MLXArray.full(
                [2_048, inVec / 16], values: MLXArray(UInt8(0x30)),
                dtype: .uint8)

            for (gateForm, gate, activated) in [
                ("raw", input.rawGate, false),
                ("activated", input.activatedGate, true),
            ] {
                let projection = try #require(lagunaGatedAffineOProjNVFP4(
                    attentionOutput: input.attention, gateLogits: gate,
                    codes: codes, scales: scales, heads: heads,
                    gateIsActivated: activated))
                let fused = try #require(lagunaGatedAffineOProjNVFP4(
                    attentionOutput: input.attention, gateLogits: gate,
                    codes: codes, scales: scales, heads: heads,
                    gateIsActivated: activated, residual: input.residual))
                verifyFullChain(
                    label: "nvfp4-\(gateForm)-H\(heads)", residual: input.residual,
                    projection: projection, fused: fused, router: router,
                    testCorruption: false)
            }
        }
    }

    @Test
    func affineEpilogueHandlesBF16BoundariesAndNonFiniteValuesBitExactly() throws {
        guard runtimeProbeEnabled else { return }

        let heads = 48
        let input = makeProjectionInputs(heads: heads, edgeResidual: true)
        let inVec = heads * 128
        let codes = MLXArray.full(
            [2_048, inVec / 4], values: MLXArray(UInt32(0)), dtype: .uint32)
        let scales = MLXArray.full(
            [2_048, inVec / 32], values: MLXArray(Float(1)), dtype: .bfloat16)
        let biases = MLXArray.full(
            [2_048, inVec / 32], values: MLXArray(Float(0)), dtype: .bfloat16)
        let projection = try #require(lagunaGatedAffineOProj(
            attentionOutput: input.attention, gateLogits: input.rawGate,
            codes: codes, scales: scales, biases: biases, heads: heads))
        let fused = try #require(lagunaGatedAffineOProj(
            attentionOutput: input.attention, gateLogits: input.rawGate,
            codes: codes, scales: scales, biases: biases,
            heads: heads, residual: input.residual))
        let reference = (input.residual + projection).asType(.bfloat16)
        expectBitsEqual(fused, reference, label: "affine-edge-epilogue-H48")
        print("oproj_final_residual_probe affine-edge-epilogue-H48 PASS elements=2048")
    }
}

private let runtimeProbeEnabled =
    ProcessInfo.processInfo.environment["MLXFAST_RUN_OPROJ_FINAL_RESIDUAL_PROBE"] == "1"

private struct ProjectionInputs {
    let attention: MLXArray
    let rawGate: MLXArray
    let activatedGate: MLXArray
    let residual: MLXArray
}

private struct RouterInputs {
    let weight: MLXArray
    let routerWeight: MLXArray
}

private func makeProjectionInputs(heads: Int, edgeResidual: Bool = false) -> ProjectionInputs {
    let inVec = heads * 128
    var attentionValues = (0..<inVec).map { index in
        Float(sin(Double(index) * 0.019 + Double(heads) * 0.003) * 0.1875)
    }
    attentionValues[0] = 0
    attentionValues[1] = -0.0
    attentionValues[2] = 0.0078125
    attentionValues[3] = -0.0078125

    let rawGateValues = (0..<heads).map { index in
        Float(sin(Double(index) * 0.23) * 3.0 - 0.75)
    }
    let activatedGateValues = rawGateValues.map { value in
        Float(log1p(exp(Double(value))))
    }
    var residualValues = (0..<2_048).map { index in
        Float(cos(Double(index) * 0.031 + Double(heads) * 0.007) * 0.75)
    }
    residualValues[0] = 0
    residualValues[1] = -0.0
    residualValues[2] = 1.0
    residualValues[3] = -1.0
    residualValues[4] = 0.0078125
    residualValues[5] = -0.0078125
    if edgeResidual {
        residualValues[6] = Float.infinity
        residualValues[7] = -Float.infinity
        residualValues[8] = Float.nan
        residualValues[9] = Float.leastNonzeroMagnitude
        residualValues[10] = -Float.leastNonzeroMagnitude
        residualValues[11] = Float.greatestFiniteMagnitude
        residualValues[12] = -Float.greatestFiniteMagnitude
    }

    return ProjectionInputs(
        attention: MLXArray(attentionValues, [1, 1, inVec]).asType(.bfloat16),
        rawGate: MLXArray(rawGateValues, [1, 1, heads]).asType(.bfloat16),
        activatedGate: MLXArray(activatedGateValues, [1, 1, heads]).asType(.bfloat16),
        residual: MLXArray(residualValues, [1, 1, 2_048]).asType(.bfloat16))
}

private func makeRouterInputs() -> RouterInputs {
    let columns = MLXArray(0..<2_048).asType(.float32)
    let rows = MLXArray(0..<256).asType(.float32).reshaped([256, 1])
    let weight = (cos(columns * 0.009) * 0.5 + 0.75).asType(.bfloat16)
    let routerWeight = (
        sin(rows * 0.037 + columns.reshaped([1, 2_048]) * 0.013) * 0.03125
    ).asType(.bfloat16)
    return RouterInputs(weight: weight, routerWeight: routerWeight)
}

private func indexedMetadata(
    scales: MLXArray, biases: MLXArray
) -> LagunaIndexedAffineMetadata {
    let scaleBit = scales[0, 0].view(dtype: .uint16).item(UInt16.self)
    let biasBit = biases[0, 0].view(dtype: .uint16).item(UInt16.self)
    let pair = UInt32(scaleBit) | (UInt32(biasBit) << 16)
    return LagunaIndexedAffineMetadata(
        indices: MLXArray.full(
            scales.shape, values: MLXArray(UInt16(0)), dtype: .uint16),
        lut: MLXArray([pair]))
}

private func verifyFullChain(
    label: String, residual: MLXArray, projection: MLXArray, fused: MLXArray,
    router: RouterInputs, testCorruption: Bool
) {
    let referenceH = (residual + projection).asType(.bfloat16)
    let legacy = lagunaResidualRMSNormRouter(
        residual: residual, branch: projection,
        weight: router.weight, routerWeight: router.routerWeight)
    let candidate = lagunaSummedRMSNormRouter(
        summed: fused, weight: router.weight, routerWeight: router.routerWeight)

    expectBitsEqual(fused, referenceH, label: "\(label)-h")
    expectBitsEqual(fused, legacy.summed, label: "\(label)-summed")
    expectBitsEqual(candidate.normalized, legacy.normalized, label: "\(label)-normalized")
    expectBitsEqual(candidate.routerLogits, legacy.routerLogits, label: "\(label)-router-256")

    if testCorruption {
        var deltaValues = Array(repeating: Float(0), count: 2_048)
        deltaValues[17] = 0.5
        let corrupted = (
            fused + MLXArray(deltaValues, [1, 1, 2_048]).asType(.bfloat16)
        ).asType(.bfloat16)
        let corruptedRouter = lagunaSummedRMSNormRouter(
            summed: corrupted, weight: router.weight,
            routerWeight: router.routerWeight)
        #expect(bits(corrupted) != bits(referenceH), "\(label) corruption did not change h")
        #expect(
            bits(corruptedRouter.routerLogits) != bits(legacy.routerLogits),
            "\(label) corruption did not reach router logits")
        print("oproj_final_residual_probe \(label)-corruption PASS")
    }

    print(
        "oproj_final_residual_probe \(label) PASS "
            + "h=2048 normalized=2048 router_logits=256")
}

private func expectBitsEqual(_ lhs: MLXArray, _ rhs: MLXArray, label: String) {
    let lhsBits = bits(lhs)
    let rhsBits = bits(rhs)
    #expect(lhsBits == rhsBits, "\(label) BF16 bit mismatch")
}

private func bits(_ array: MLXArray) -> [UInt16] {
    eval(array)
    return array.view(dtype: .uint16).asArray(UInt16.self)
}
