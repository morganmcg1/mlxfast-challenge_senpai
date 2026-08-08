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

    @Test
    func mirroredFullChainTiming() throws {
        guard timingProbeEnabled else { return }
        #expect(ProcessInfo.processInfo.environment["DARKBLOOM_OPROJ_FINAL_RESIDUAL"] == "1")

        let storage = ProcessInfo.processInfo.environment["MLXFAST_OPROJ_TIMING_STORAGE"]
            ?? "affine-indexed"
        let architecture = ProcessInfo.processInfo.environment["MLXFAST_TIMING_ARCH"]
            ?? "unknown"
        let router = makeRouterInputs()
        eval(router.weight, router.routerWeight)

        var headResults: [HeadTimingResult] = []
        for heads in [48, 64] {
            let chain = try makeTimingChain(storage: storage, heads: heads, router: router)
            for _ in 0..<16 {
                eval(try chain.control())
                eval(try chain.candidate())
                eval(try chain.candidate())
                eval(try chain.control())
            }
            let ab = try measureOrder(chain: chain, controlFirst: true, iterations: 128)
            let ba = try measureOrder(chain: chain, controlFirst: false, iterations: 128)
            let result = HeadTimingResult(heads: heads, ab: ab, ba: ba)
            headResults.append(result)
            printTimingBlock(storage: storage, heads: heads, order: "AB", block: ab)
            printTimingBlock(storage: storage, heads: heads, order: "BA", block: ba)
        }

        let combinedAB = combineTimingBlocks(headResults.map(\.ab))
        let combinedBA = combineTimingBlocks(headResults.map(\.ba))
        printTimingBlock(storage: storage, heads: 0, order: "AB-combined", block: combinedAB)
        printTimingBlock(storage: storage, heads: 0, order: "BA-combined", block: combinedBA)

        let repeatableSignReversal = headResults.contains {
            $0.ab.speedup < 1.0 && $0.ba.speedup < 1.0
        }
        let gatePassed = timingOrderPasses(combinedAB) && timingOrderPasses(combinedBA)
            && !repeatableSignReversal
        print(
            "oproj_final_residual_timing gate=\(gatePassed ? "PASS" : "FAIL") "
                + "storage=\(storage) architecture=\(architecture) selector=1 "
                + "iterations_per_arm_per_order=128 repeatable_sign_reversal=\(repeatableSignReversal)")
    }
}

private let runtimeProbeEnabled =
    ProcessInfo.processInfo.environment["MLXFAST_RUN_OPROJ_FINAL_RESIDUAL_PROBE"] == "1"
private let timingProbeEnabled =
    ProcessInfo.processInfo.environment["MLXFAST_RUN_OPROJ_FINAL_RESIDUAL_TIMING"] == "1"

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

private struct TimingChain {
    let control: () throws -> MLXArray
    let candidate: () throws -> MLXArray
}

private struct TimingBlock {
    let control: [UInt64]
    let candidate: [UInt64]

    var controlMedian: Double { median(control.map(Double.init)) }
    var candidateMedian: Double { median(candidate.map(Double.init)) }
    var speedup: Double { controlMedian / candidateMedian }
    var pairedSavings: [Double] {
        zip(control, candidate).map { Double($0.0) - Double($0.1) }
    }
    var pairedSavingsMedian: Double { median(pairedSavings) }
    var pairedSavingsMAD: Double { mad(pairedSavings) }
}

private struct HeadTimingResult {
    let heads: Int
    let ab: TimingBlock
    let ba: TimingBlock
}

private enum TimingProbeError: Error {
    case unsupportedStorage(String)
    case guardDeclined(String)
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

private func makeTimingChain(
    storage: String, heads: Int, router: RouterInputs
) throws -> TimingChain {
    let input = makeProjectionInputs(heads: heads)
    let inVec = heads * 128

    switch storage {
    case "affine-plain", "affine-indexed":
        let codes = MLXArray.full(
            [2_048, inVec / 4], values: MLXArray(UInt32(0x7f00_80ff)),
            dtype: .uint32)
        let scales = MLXArray.full(
            [2_048, inVec / 32], values: MLXArray(Float(0.001953125)),
            dtype: .bfloat16)
        let biases = MLXArray.full(
            [2_048, inVec / 32], values: MLXArray(Float(-0.015625)),
            dtype: .bfloat16)
        let metadata = storage == "affine-indexed"
            ? indexedMetadata(scales: scales, biases: biases) : nil
        if let metadata {
            eval(
                input.attention, input.rawGate, input.residual,
                codes, scales, biases, metadata.indices, metadata.lut)
        } else {
            eval(input.attention, input.rawGate, input.residual, codes, scales, biases)
        }

        return TimingChain(
            control: {
                guard let projection = lagunaGatedAffineOProj(
                    attentionOutput: input.attention, gateLogits: input.rawGate,
                    codes: codes, scales: scales, biases: biases,
                    indexedMetadata: metadata, heads: heads)
                else { throw TimingProbeError.guardDeclined("affine-control-H\(heads)") }
                return lagunaResidualRMSNormRouter(
                    residual: input.residual, branch: projection,
                    weight: router.weight, routerWeight: router.routerWeight
                ).routerLogits
            },
            candidate: {
                guard let fused = lagunaGatedAffineOProj(
                    attentionOutput: input.attention, gateLogits: input.rawGate,
                    codes: codes, scales: scales, biases: biases,
                    indexedMetadata: metadata, heads: heads, residual: input.residual)
                else { throw TimingProbeError.guardDeclined("affine-candidate-H\(heads)") }
                return lagunaSummedRMSNormRouter(
                    summed: fused, weight: router.weight,
                    routerWeight: router.routerWeight
                ).routerLogits
            })

    case "nvfp4-raw", "nvfp4-activated":
        let codes = MLXArray.full(
            [2_048, inVec / 8], values: MLXArray(UInt32(0x7654_3210)),
            dtype: .uint32)
        let scales = MLXArray.full(
            [2_048, inVec / 16], values: MLXArray(UInt8(0x30)), dtype: .uint8)
        let activated = storage == "nvfp4-activated"
        let gate = activated ? input.activatedGate : input.rawGate
        eval(input.attention, gate, input.residual, codes, scales)

        return TimingChain(
            control: {
                guard let projection = lagunaGatedAffineOProjNVFP4(
                    attentionOutput: input.attention, gateLogits: gate,
                    codes: codes, scales: scales, heads: heads,
                    gateIsActivated: activated)
                else { throw TimingProbeError.guardDeclined("nvfp4-control-H\(heads)") }
                return lagunaResidualRMSNormRouter(
                    residual: input.residual, branch: projection,
                    weight: router.weight, routerWeight: router.routerWeight
                ).routerLogits
            },
            candidate: {
                guard let fused = lagunaGatedAffineOProjNVFP4(
                    attentionOutput: input.attention, gateLogits: gate,
                    codes: codes, scales: scales, heads: heads,
                    gateIsActivated: activated, residual: input.residual)
                else { throw TimingProbeError.guardDeclined("nvfp4-candidate-H\(heads)") }
                return lagunaSummedRMSNormRouter(
                    summed: fused, weight: router.weight,
                    routerWeight: router.routerWeight
                ).routerLogits
            })

    default:
        throw TimingProbeError.unsupportedStorage(storage)
    }
}

private func measureOrder(
    chain: TimingChain, controlFirst: Bool, iterations: Int
) throws -> TimingBlock {
    var control: [UInt64] = []
    var candidate: [UInt64] = []
    control.reserveCapacity(iterations)
    candidate.reserveCapacity(iterations)

    for _ in 0..<iterations {
        if controlFirst {
            control.append(try measure(chain.control))
            candidate.append(try measure(chain.candidate))
        } else {
            candidate.append(try measure(chain.candidate))
            control.append(try measure(chain.control))
        }
    }
    return TimingBlock(control: control, candidate: candidate)
}

private func measure(_ builder: () throws -> MLXArray) rethrows -> UInt64 {
    let start = DispatchTime.now().uptimeNanoseconds
    let output = try builder()
    eval(output)
    return DispatchTime.now().uptimeNanoseconds - start
}

private func combineTimingBlocks(_ blocks: [TimingBlock]) -> TimingBlock {
    TimingBlock(
        control: blocks.flatMap(\.control),
        candidate: blocks.flatMap(\.candidate))
}

private func median(_ values: [Double]) -> Double {
    precondition(!values.isEmpty)
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}

private func mad(_ values: [Double]) -> Double {
    let center = median(values)
    return median(values.map { abs($0 - center) })
}

private func timingOrderPasses(_ block: TimingBlock) -> Bool {
    block.speedup >= 1.005
        && block.pairedSavingsMedian > 2 * block.pairedSavingsMAD
}

private func printTimingBlock(
    storage: String, heads: Int, order: String, block: TimingBlock
) {
    let headLabel = heads == 0 ? "combined" : "H\(heads)"
    print(
        "oproj_final_residual_timing_raw storage=\(storage) heads=\(headLabel) "
            + "order=\(order) control_ns=\(block.control) candidate_ns=\(block.candidate)")
    print(
        "oproj_final_residual_timing_summary storage=\(storage) heads=\(headLabel) "
            + "order=\(order) control_median_ns=\(block.controlMedian) "
            + "candidate_median_ns=\(block.candidateMedian) speedup=\(block.speedup) "
            + "paired_savings_median_ns=\(block.pairedSavingsMedian) "
            + "paired_savings_mad_ns=\(block.pairedSavingsMAD) "
            + "noise_gate=\(timingOrderPasses(block) ? "PASS" : "FAIL")")
}
