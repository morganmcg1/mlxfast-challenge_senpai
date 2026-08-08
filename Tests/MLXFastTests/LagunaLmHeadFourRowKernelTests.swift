import Foundation
import MLX
import MLXFast
@testable import MLXFastModel
import Testing

private let lmHeadVocab = 100_352
private let lmHeadHidden = 2_048
private let lmHeadOutputOffset = 5

private let lmHeadTwoRowSource = """
    constexpr float GAMMA = 0x1p-15f;

    uint row0 = threadgroup_position_in_grid.x * 16 +
        2 * simdgroup_index_in_threadgroup;
    uint row1 = row0 + 1;
    uint lane = thread_index_in_simdgroup;

    const device uint8_t* lorow0 = codes_lo + size_t(row0) * 1024;
    const device uint8_t* lorow1 = lorow0 + 1024;
    const device uint8_t* hirow0 = codes_hi + size_t(row0) * 256;
    const device uint8_t* hirow1 = hirow0 + 256;
    const device uint8_t* srow0 = scales + size_t(row0) * 64;
    const device uint8_t* srow1 = srow0 + 64;

    float c_acc0 = 0.0f;
    float d_acc0 = 0.0f;
    float c_acc1 = 0.0f;
    float d_acc1 = 0.0f;
    for (uint gg = 0; gg < 2; ++gg) {
        uint g = 2 * lane + gg;
        float sd0 = laguna_e8m0_decode(srow0[g]);
        float sd1 = laguna_e8m0_decode(srow1[g]);
        uint4 lo40 = ((const device uint4*)(lorow0 + g * 16))[0];
        uint4 lo41 = ((const device uint4*)(lorow1 + g * 16))[0];
        uint hb0 = ((const device uint*)(hirow0 + g * 4))[0];
        uint hb1 = ((const device uint*)(hirow1 + g * 4))[0];
        const device ushort4* xrow = (const device ushort4*)(x + g * 32);
        float cg0 = 0.0f;
        float cg1 = 0.0f;
        float ag = 0.0f;
        #pragma clang loop unroll(full)
        for (uint w = 0; w < 4; ++w) {
            uint lw0 = lo40[w];
            uint hw0 = hb0 >> (8u * w);
            uint4 ne0 = (uint4(lw0) >> uint4(0u, 8u, 16u, 24u)) & 15u;
            uint4 no0 = (uint4(lw0) >> uint4(4u, 12u, 20u, 28u)) & 15u;
            uint4 he0 = (uint4(hw0) >> uint4(0u, 2u, 4u, 6u)) & 1u;
            uint4 ho0 = (uint4(hw0) >> uint4(1u, 3u, 5u, 7u)) & 1u;
            float4 ve0 = float4(ne0 | (he0 << 4u)) - 16.0f;
            float4 vo0 = float4(no0 | (ho0 << 4u)) - 16.0f;

            float4 xa = as_type<float4>(uint4(xrow[2 * w]) << 16);
            float4 xb = as_type<float4>(uint4(xrow[2 * w + 1]) << 16);
            float4 xe = float4(xa.x, xa.z, xb.x, xb.z);
            float4 xo = float4(xa.y, xa.w, xb.y, xb.w);
            float4 axe = metal::abs(xe);
            float4 axo = metal::abs(xo);
            #pragma clang loop unroll(full)
            for (uint k = 0; k < 4; ++k) {
                cg0 += xe[k] * ve0[k];
                cg0 += xo[k] * vo0[k];
                ag += axe[k];
                ag += axo[k];
            }

            uint lw1 = lo41[w];
            uint hw1 = hb1 >> (8u * w);
            uint4 ne1 = (uint4(lw1) >> uint4(0u, 8u, 16u, 24u)) & 15u;
            uint4 no1 = (uint4(lw1) >> uint4(4u, 12u, 20u, 28u)) & 15u;
            uint4 he1 = (uint4(hw1) >> uint4(0u, 2u, 4u, 6u)) & 1u;
            uint4 ho1 = (uint4(hw1) >> uint4(1u, 3u, 5u, 7u)) & 1u;
            float4 ve1 = float4(ne1 | (he1 << 4u)) - 16.0f;
            float4 vo1 = float4(no1 | (ho1 << 4u)) - 16.0f;
            #pragma clang loop unroll(full)
            for (uint k = 0; k < 4; ++k) {
                cg1 += xe[k] * ve1[k];
                cg1 += xo[k] * vo1[k];
            }
        }
        c_acc0 += sd0 * cg0;
        d_acc0 += (0.5f * sd0) * ag;
        c_acc1 += sd1 * cg1;
        d_acc1 += (0.5f * sd1) * ag;
    }
    c_acc0 = simd_sum(c_acc0);
    d_acc0 = simd_sum(d_acc0);
    if (lane == 0) {
        coarse[row0] = c_acc0;
        float d_up0 = d_acc0 * (1.0f + 61.0f * GAMMA);
        uint dbits0 = as_type<uint>(d_up0);
        uint dtrunc0 = dbits0 & 0xFFFF0000u;
        if (dtrunc0 != dbits0) {
            dtrunc0 += 0x00010000u;
        }
        delta[row0] = as_type<bfloat>(ushort(dtrunc0 >> 16));
    }
    c_acc1 = simd_sum(c_acc1);
    d_acc1 = simd_sum(d_acc1);
    if (lane == 0) {
        coarse[row1] = c_acc1;
        float d_up1 = d_acc1 * (1.0f + 61.0f * GAMMA);
        uint dbits1 = as_type<uint>(d_up1);
        uint dtrunc1 = dbits1 & 0xFFFF0000u;
        if (dtrunc1 != dbits1) {
            dtrunc1 += 0x00010000u;
        }
        delta[row1] = as_type<bfloat>(ushort(dtrunc1 >> 16));
    }
    """

private let lmHeadTwoRowKernel = MLXFast.metalKernel(
    name: "laguna_lmhead_int5_two_row_test_oracle",
    inputNames: ["x", "codes_lo", "codes_hi", "scales"],
    outputNames: ["coarse", "delta"],
    source: lmHeadTwoRowSource,
    header: lagunaLmHeadPruneHeader,
    ensureRowContiguous: true
)

private struct LmHeadWeights {
    let codesLo: MLXArray
    let codesHi: MLXArray
    let scales: MLXArray
}

private struct LmHeadInputs {
    let x: MLXArray
    let codesLo: MLXArray
    let codesHi: MLXArray
    let scales: MLXArray

    var arrays: [MLXArray] { [x, codesLo, codesHi, scales] }
}

private func makeLmHeadWeights() -> LmHeadWeights {
    let codesLoBacking = MLXRandom.randInt(
        UInt8(0) ..< UInt8.max,
        [lmHeadVocab + 1, 1_024],
        key: MLXRandom.key(10)
    )
    let codesHiBacking = MLXRandom.randInt(
        UInt8(0) ..< UInt8.max,
        [lmHeadVocab + 1, 256],
        key: MLXRandom.key(11)
    )
    let scalesBacking = MLXRandom.randInt(
        UInt8(110) ..< UInt8(140),
        [lmHeadVocab + 1, 64],
        key: MLXRandom.key(12)
    )
    return LmHeadWeights(
        codesLo: codesLoBacking[1 ..< (lmHeadVocab + 1)],
        codesHi: codesHiBacking[1 ..< (lmHeadVocab + 1)],
        scales: scalesBacking[1 ..< (lmHeadVocab + 1)]
    )
}

private func hiddenFromBits(_ pattern: [UInt16]) -> MLXArray {
    let bits = (0 ..< (lmHeadHidden + 2)).map { pattern[$0 % pattern.count] }
    return MLXArray(bits, [bits.count]).view(dtype: .bfloat16)[1 ..< (lmHeadHidden + 1)]
}

private func makeInputs(x: MLXArray, weights: LmHeadWeights, scales: MLXArray? = nil)
    -> LmHeadInputs
{
    LmHeadInputs(
        x: x,
        codesLo: weights.codesLo,
        codesHi: weights.codesHi,
        scales: scales ?? weights.scales
    )
}

private func runTwoRow(_ inputs: LmHeadInputs) -> [MLXArray] {
    lmHeadTwoRowKernel(
        inputs.arrays,
        grid: (lmHeadVocab / 16 * 256, 1, 1),
        threadGroup: (256, 1, 1),
        outputShapes: [[lmHeadVocab], [lmHeadVocab]],
        outputDTypes: [.float32, .bfloat16]
    )
}

private func runFourRow(_ inputs: LmHeadInputs) -> [MLXArray] {
    lagunaLmHeadInt5CoarseRatioBoundDeltaBF16Kernel(
        inputs.arrays,
        grid: (lmHeadVocab / 16 * 128, 1, 1),
        threadGroup: (128, 1, 1),
        outputShapes: [[lmHeadVocab], [lmHeadVocab]],
        outputDTypes: [.float32, .bfloat16]
    )
}

private func uint32Bits(_ array: MLXArray) -> [UInt32] {
    array.view(dtype: .uint32).asArray(UInt32.self)
}

private func uint16Bits(_ array: MLXArray) -> [UInt16] {
    array.view(dtype: .uint16).asArray(UInt16.self)
}

private func mismatchCount<T: Equatable>(_ lhs: [T], _ rhs: [T]) -> Int {
    precondition(lhs.count == rhs.count)
    return zip(lhs, rhs).reduce(into: 0) { count, pair in
        if pair.0 != pair.1 { count += 1 }
    }
}

private func offsetSource(_ source: String, rows: Int) -> String {
    (0 ..< rows).reduce(source) { result, row in
        result
            .replacingOccurrences(
                of: "coarse[row\(row)]",
                with: "coarse[row\(row) + \(lmHeadOutputOffset)]"
            )
            .replacingOccurrences(
                of: "delta[row\(row)]",
                with: "delta[row\(row) + \(lmHeadOutputOffset)]"
            )
    }
}

private func checkSentinels(
    _ output: [MLXArray],
    expectedCoarse: [UInt32],
    expectedDelta: [UInt16]
) {
    let coarse = uint32Bits(output[0])
    let delta = uint16Bits(output[1])
    let body = lmHeadOutputOffset ..< (lmHeadOutputOffset + lmHeadVocab)
    let suffix = (lmHeadOutputOffset + lmHeadVocab) ..< coarse.count

    #expect(coarse[..<lmHeadOutputOffset].allSatisfy { $0 == Float(-123).bitPattern })
    #expect(coarse[suffix].allSatisfy { $0 == Float(-123).bitPattern })
    #expect(delta[..<lmHeadOutputOffset].allSatisfy { $0 == UInt16(0xC2F6) })
    #expect(delta[suffix].allSatisfy { $0 == UInt16(0xC2F6) })
    #expect(Array(coarse[body]) == expectedCoarse)
    #expect(Array(delta[body]) == expectedDelta)
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}

private func mad(_ values: [Double], around center: Double) -> Double {
    median(values.map { abs($0 - center) })
}

private func measureMicroseconds(_ operation: () -> [MLXArray]) -> Double {
    let start = DispatchTime.now().uptimeNanoseconds
    eval(operation())
    return Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000
}

private func jsonArray(_ values: [Double]) -> String {
    "[" + values.map { String(format: "%.3f", $0) }.joined(separator: ",") + "]"
}

@Suite(.serialized)
struct LagunaLmHeadFourRowKernelTests {
    @Test
    func exactnessWhenRequested() {
        guard ProcessInfo.processInfo.environment["MLXFAST_LMHEAD_FOUR_ROW_MODE"] == "exactness"
        else { return }

        Memory.peakMemory = 0
        let weights = makeLmHeadWeights()
        let randomX = MLXRandom.normal(
            [lmHeadHidden + 2],
            dtype: .bfloat16,
            key: MLXRandom.key(13)
        )[1 ..< (lmHeadHidden + 1)]
        let signedX = hiddenFromBits([
            0x0000, 0x8000, 0x0001, 0x8001, 0x3F80, 0xBF80, 0x7F7F, 0xFF7F,
        ])
        let nonFiniteX = hiddenFromBits([
            0x3F80, 0xBF80, 0x7F80, 0xFF80, 0x7FC1, 0xFFC1, 0x0000, 0x8000,
        ])
        let extremeScaleBacking = MLXArray.full(
            [lmHeadVocab + 1, 64],
            values: MLXArray(UInt8(254)),
            dtype: .uint8
        )
        let extremeScales = extremeScaleBacking[1 ..< (lmHeadVocab + 1)]
        eval(weights.codesLo, weights.codesHi, weights.scales, extremeScales)

        let cases: [(String, LmHeadInputs)] = [
            ("random", makeInputs(x: randomX, weights: weights)),
            ("signed-boundaries", makeInputs(x: signedX, weights: weights)),
            ("defined-nan-inf", makeInputs(x: nonFiniteX, weights: weights)),
            (
                "extreme-scales",
                makeInputs(x: signedX, weights: weights, scales: extremeScales)
            ),
        ]
        var checkedCoarse = 0
        var checkedDelta = 0
        var firstExpectedCoarse: [UInt32] = []
        var firstExpectedDelta: [UInt16] = []

        for (index, testCase) in cases.enumerated() {
            let old = runTwoRow(testCase.1)
            let new = runFourRow(testCase.1)
            eval(old + new)
            let oldCoarse = uint32Bits(old[0])
            let newCoarse = uint32Bits(new[0])
            let oldDelta = uint16Bits(old[1])
            let newDelta = uint16Bits(new[1])
            let coarseMismatches = mismatchCount(oldCoarse, newCoarse)
            let deltaMismatches = mismatchCount(oldDelta, newDelta)
            print(
                "LMHEAD_FOUR_ROW_CASE label=\(testCase.0) coarse_mismatches=\(coarseMismatches) delta_mismatches=\(deltaMismatches) rows=\(lmHeadVocab)"
            )
            #expect(coarseMismatches == 0)
            #expect(deltaMismatches == 0)
            checkedCoarse += oldCoarse.count
            checkedDelta += oldDelta.count
            if index == 0 {
                firstExpectedCoarse = oldCoarse
                firstExpectedDelta = oldDelta
            }
        }

        let offsetOldKernel = MLXFast.metalKernel(
            name: "laguna_lmhead_int5_two_row_offset_test",
            inputNames: ["x", "codes_lo", "codes_hi", "scales"],
            outputNames: ["coarse", "delta"],
            source: offsetSource(lmHeadTwoRowSource, rows: 2),
            header: lagunaLmHeadPruneHeader,
            ensureRowContiguous: true
        )
        let offsetNewKernel = MLXFast.metalKernel(
            name: "laguna_lmhead_int5_four_row_offset_test",
            inputNames: ["x", "codes_lo", "codes_hi", "scales"],
            outputNames: ["coarse", "delta"],
            source: offsetSource(lagunaLmHeadInt5CoarseRatioBoundDeltaBF16Source, rows: 4),
            header: lagunaLmHeadPruneHeader,
            ensureRowContiguous: true
        )
        let offsetShape = [lmHeadVocab + 2 * lmHeadOutputOffset]
        let offsetOld = offsetOldKernel(
            cases[0].1.arrays,
            grid: (lmHeadVocab / 16 * 256, 1, 1),
            threadGroup: (256, 1, 1),
            outputShapes: [offsetShape, offsetShape],
            outputDTypes: [.float32, .bfloat16],
            initValue: -123
        )
        let offsetNew = offsetNewKernel(
            cases[0].1.arrays,
            grid: (lmHeadVocab / 16 * 128, 1, 1),
            threadGroup: (128, 1, 1),
            outputShapes: [offsetShape, offsetShape],
            outputDTypes: [.float32, .bfloat16],
            initValue: -123
        )
        eval(offsetOld + offsetNew)
        checkSentinels(
            offsetOld,
            expectedCoarse: firstExpectedCoarse,
            expectedDelta: firstExpectedDelta
        )
        checkSentinels(
            offsetNew,
            expectedCoarse: firstExpectedCoarse,
            expectedDelta: firstExpectedDelta
        )

        let corruptedSource = lagunaLmHeadInt5CoarseRatioBoundDeltaBF16Source.replacingOccurrences(
            of: "coarse[row0] = c_acc0;",
            with: "coarse[row0] = c_acc0 + 1.0f;"
        )
        let corruptedKernel = MLXFast.metalKernel(
            name: "laguna_lmhead_int5_four_row_corruption_test",
            inputNames: ["x", "codes_lo", "codes_hi", "scales"],
            outputNames: ["coarse", "delta"],
            source: corruptedSource,
            header: lagunaLmHeadPruneHeader,
            ensureRowContiguous: true
        )
        let corrupted = corruptedKernel(
            cases[0].1.arrays,
            grid: (lmHeadVocab / 16 * 128, 1, 1),
            threadGroup: (128, 1, 1),
            outputShapes: [[lmHeadVocab], [lmHeadVocab]],
            outputDTypes: [.float32, .bfloat16]
        )
        eval(corrupted)
        let detectedCorruptions = mismatchCount(firstExpectedCoarse, uint32Bits(corrupted[0]))
        #expect(detectedCorruptions > 0)

        print(
            "LMHEAD_FOUR_ROW_EXACTNESS coarse_checked=\(checkedCoarse) delta_checked=\(checkedDelta) sentinel_outputs=4 input_backing_offset=1 output_offset=\(lmHeadOutputOffset) corruption_mismatches=\(detectedCorruptions) boundary_rows=0,\(lmHeadVocab - 1) peak_memory_bytes=\(Memory.peakMemory)"
        )
    }

    @Test
    func isolatedTimingWhenRequested() {
        guard ProcessInfo.processInfo.environment["MLXFAST_LMHEAD_FOUR_ROW_MODE"] == "timing"
        else { return }

        Memory.peakMemory = 0
        let weights = makeLmHeadWeights()
        let x = MLXRandom.normal(
            [lmHeadHidden + 2],
            dtype: .bfloat16,
            key: MLXRandom.key(14)
        )[1 ..< (lmHeadHidden + 1)]
        let inputs = makeInputs(x: x, weights: weights)
        eval(inputs.arrays)
        for _ in 0 ..< 8 {
            eval(runTwoRow(inputs))
            eval(runFourRow(inputs))
        }

        let thermalBefore = String(describing: ProcessInfo.processInfo.thermalState)
        var oldAB: [Double] = []
        var newAB: [Double] = []
        var oldBA: [Double] = []
        var newBA: [Double] = []
        for _ in 0 ..< 40 {
            oldAB.append(measureMicroseconds { runTwoRow(inputs) })
            newAB.append(measureMicroseconds { runFourRow(inputs) })
        }
        for _ in 0 ..< 40 {
            newBA.append(measureMicroseconds { runFourRow(inputs) })
            oldBA.append(measureMicroseconds { runTwoRow(inputs) })
        }
        let thermalAfter = String(describing: ProcessInfo.processInfo.thermalState)

        let oldABMedian = median(oldAB)
        let newABMedian = median(newAB)
        let oldBAMedian = median(oldBA)
        let newBAMedian = median(newBA)
        let speedupAB = oldABMedian / newABMedian
        let speedupBA = oldBAMedian / newBAMedian
        let deviations =
            oldAB.map { abs($0 - oldABMedian) }
            + newAB.map { abs($0 - newABMedian) }
            + oldBA.map { abs($0 - oldBAMedian) }
            + newBA.map { abs($0 - newBAMedian) }
        let pooledMAD = median(deviations)
        let minimumGap = min(oldABMedian - newABMedian, oldBAMedian - newBAMedian)
        let speedGate = speedupAB >= 1.005 && speedupBA >= 1.005
        let noiseGate = minimumGap > 2 * pooledMAD
        let passed = speedGate && noiseGate

        print(
            "LMHEAD_FOUR_ROW_TIMING old_ab_us=\(jsonArray(oldAB)) new_ab_us=\(jsonArray(newAB)) old_ba_us=\(jsonArray(oldBA)) new_ba_us=\(jsonArray(newBA)) old_ab_median_us=\(oldABMedian) new_ab_median_us=\(newABMedian) old_ba_median_us=\(oldBAMedian) new_ba_median_us=\(newBAMedian) speedup_ab=\(speedupAB) speedup_ba=\(speedupBA) old_ab_mad_us=\(mad(oldAB, around: oldABMedian)) new_ab_mad_us=\(mad(newAB, around: newABMedian)) old_ba_mad_us=\(mad(oldBA, around: oldBAMedian)) new_ba_mad_us=\(mad(newBA, around: newBAMedian)) pooled_mad_us=\(pooledMAD) minimum_gap_us=\(minimumGap) thermal_before=\(thermalBefore) thermal_after=\(thermalAfter) peak_memory_bytes=\(Memory.peakMemory) passed=\(passed)"
        )
        #expect(speedGate)
        #expect(noiseGate)
    }
}
