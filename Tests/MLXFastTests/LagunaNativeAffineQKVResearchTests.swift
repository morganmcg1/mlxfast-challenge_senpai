import Foundation
import MLX
import MLXFast
import Testing

@testable import MLXFastModel

private let qkvResearchHiddenSize = 2_048
private let qkvResearchGroups = qkvResearchHiddenSize / 32

private struct QKVResearchInputs {
    let residual: MLXArray
    let normWeight: MLXArray
    let codes: MLXArray
    let corruptCodes: MLXArray
    let scales: MLXArray
    let biases: MLXArray
    let indices: MLXArray
    let corruptIndices: MLXArray
    let metadataLUT: MLXArray

    var all: [MLXArray] {
        [
            residual, normWeight, codes, corruptCodes, scales, biases,
            indices, corruptIndices, metadataLUT,
        ]
    }

    func kernelInputs(indexed: Bool, corrupt: Bool = false) -> [MLXArray] {
        if indexed {
            return [
                residual, normWeight, codes,
                corrupt ? corruptIndices : indices, metadataLUT,
            ]
        }
        return [
            residual, normWeight, corrupt ? corruptCodes : codes, scales, biases,
        ]
    }
}

private struct QKVResearchKernels {
    let fourRows: MLXFast.MLXFastKernel
    let fiveRows: MLXFast.MLXFastKernel
}

private struct QKVTimingResult {
    let abFour: Double
    let abFive: Double
    let baFour: Double
    let baFive: Double
    let pairedMedian: Double
    let pairedMAD: Double

    var abSpeedup: Double { abFour / abFive }
    var baSpeedup: Double { baFour / baFive }
}

@Test
func nativeAffineQKVFiveRowsResearchGateWhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_QKV_RESEARCH_TEST"] == "1" else {
        return
    }

    print("QKV_RESEARCH_DEVICE architecture=\(GPU.deviceInfo().architecture)")
    for rows in [8_240, 10_304, 8_192] {
        runQKVResearchShape(rows: rows)
    }
}

private func runQKVResearchShape(rows: Int) {
    let inputs = makeQKVResearchInputs(rows: rows)
    eval(inputs.all)

    let ordinary = makeQKVResearchKernels(rows: rows, indexed: false)
    let indexed = makeQKVResearchKernels(rows: rows, indexed: true)

    let ordinaryFour = runQKVResearchKernel(
        ordinary.fourRows, inputs: inputs.kernelInputs(indexed: false), rows: rows,
        resultsPerSIMDGroup: 4)
    let ordinaryFive = runQKVResearchKernel(
        ordinary.fiveRows, inputs: inputs.kernelInputs(indexed: false), rows: rows,
        resultsPerSIMDGroup: 5)
    let indexedFour = runQKVResearchKernel(
        indexed.fourRows, inputs: inputs.kernelInputs(indexed: true), rows: rows,
        resultsPerSIMDGroup: 4)
    let indexedFive = runQKVResearchKernel(
        indexed.fiveRows, inputs: inputs.kernelInputs(indexed: true), rows: rows,
        resultsPerSIMDGroup: 5)
    eval([ordinaryFour, ordinaryFive, indexedFour, indexedFive])

    let ordinaryFourBits = outputBits(ordinaryFour)
    let ordinaryFiveBits = outputBits(ordinaryFive)
    let indexedFourBits = outputBits(indexedFour)
    let indexedFiveBits = outputBits(indexedFive)
    let ordinaryMismatch = mismatchCount(ordinaryFourBits, ordinaryFiveBits)
    let indexedMismatch = mismatchCount(indexedFourBits, indexedFiveBits)
    let crossMismatch = mismatchCount(ordinaryFiveBits, indexedFiveBits)
    #expect(ordinaryMismatch == 0)
    #expect(indexedMismatch == 0)
    #expect(crossMismatch == 0)

    let ordinaryCorrupt = runQKVResearchKernel(
        ordinary.fiveRows, inputs: inputs.kernelInputs(indexed: false, corrupt: true),
        rows: rows, resultsPerSIMDGroup: 5)
    let indexedCorrupt = runQKVResearchKernel(
        indexed.fiveRows, inputs: inputs.kernelInputs(indexed: true, corrupt: true),
        rows: rows, resultsPerSIMDGroup: 5)
    eval([ordinaryCorrupt, indexedCorrupt])
    let ordinaryControlChanged = outputBits(ordinaryCorrupt).last != ordinaryFiveBits.last
    let indexedControlChanged = outputBits(indexedCorrupt).last != indexedFiveBits.last
    #expect(ordinaryControlChanged)
    #expect(indexedControlChanged)

    print(
        "QKV_RESEARCH_CORRECTNESS rows=\(rows) ordinary_mismatch=\(ordinaryMismatch) "
            + "indexed_mismatch=\(indexedMismatch) cross_mismatch=\(crossMismatch) "
            + "ordinary_control_changed=\(ordinaryControlChanged) "
            + "indexed_control_changed=\(indexedControlChanged)"
    )

    let ordinaryTiming = timeQKVResearchKernels(
        ordinary, inputs: inputs.kernelInputs(indexed: false), rows: rows)
    let indexedTiming = timeQKVResearchKernels(
        indexed, inputs: inputs.kernelInputs(indexed: true), rows: rows)
    printQKVTiming(rows: rows, mode: "ordinary", result: ordinaryTiming)
    printQKVTiming(rows: rows, mode: "indexed", result: indexedTiming)
}

private func makeQKVResearchInputs(rows: Int) -> QKVResearchInputs {
    let residualValues = (0..<qkvResearchHiddenSize).map {
        Float(($0 % 29) - 14) / 32
    }
    let normValues = (0..<qkvResearchHiddenSize).map {
        Float(48 + ($0 % 17)) / 64
    }
    let residual = MLXArray(residualValues, [1, 1, qkvResearchHiddenSize])
        .asType(.bfloat16)
    let normWeight = MLXArray(normValues, [qkvResearchHiddenSize]).asType(.bfloat16)

    let wordsPerRow = qkvResearchHiddenSize / 4
    var codeValues = [UInt32](repeating: 0, count: rows * wordsPerRow)
    for row in 0..<rows {
        for word in 0..<wordsPerRow {
            codeValues[row * wordsPerRow + word] =
                0x0302_0100 ^ UInt32(truncatingIfNeeded: row &* 17 &+ word)
        }
    }
    var corruptCodeValues = codeValues
    for word in 0..<wordsPerRow {
        corruptCodeValues[(rows - 1) * wordsPerRow + word] = 0xfefd_fcfb
    }
    let codes = MLXArray(codeValues, [rows, wordsPerRow])
    let corruptCodes = MLXArray(corruptCodeValues, [rows, wordsPerRow])

    let palette = MLXArray(
        [Float(0.00390625), 0.005859375, 0.0078125, 0.009765625, 0.0625,
         Float(-0.015625), -0.0078125, 0, 0.0078125, 0.5])
        .asType(.bfloat16)
    eval(palette)
    let paletteBits = palette.view(dtype: .uint16).asArray(UInt16.self)

    var scaleBits = [UInt16](repeating: 0, count: rows * qkvResearchGroups)
    var biasBits = scaleBits
    var indexValues = [UInt16](repeating: 0, count: rows * qkvResearchGroups)
    for row in 0..<rows {
        for group in 0..<qkvResearchGroups {
            let offset = row * qkvResearchGroups + group
            let paletteIndex = (row + group) % 4
            scaleBits[offset] = paletteBits[paletteIndex]
            biasBits[offset] = paletteBits[5 + paletteIndex]
            indexValues[offset] = UInt16(paletteIndex)
        }
    }
    var corruptIndexValues = indexValues
    for group in 0..<qkvResearchGroups {
        corruptIndexValues[(rows - 1) * qkvResearchGroups + group] = 4
    }

    let scales = MLXArray(scaleBits, [rows, qkvResearchGroups]).view(dtype: .bfloat16)
    let biases = MLXArray(biasBits, [rows, qkvResearchGroups]).view(dtype: .bfloat16)
    let indices = MLXArray(indexValues, [rows, qkvResearchGroups])
    let corruptIndices = MLXArray(corruptIndexValues, [rows, qkvResearchGroups])
    let lutValues = (0..<5).map { index in
        UInt32(paletteBits[index]) | (UInt32(paletteBits[5 + index]) << 16)
    }
    let metadataLUT = MLXArray(lutValues, [lutValues.count])

    return QKVResearchInputs(
        residual: residual,
        normWeight: normWeight,
        codes: codes,
        corruptCodes: corruptCodes,
        scales: scales,
        biases: biases,
        indices: indices,
        corruptIndices: corruptIndices,
        metadataLUT: metadataLUT
    )
}

private func makeQKVResearchKernels(rows: Int, indexed: Bool) -> QKVResearchKernels {
    let inputNames = indexed
        ? ["residual", "norm_weight", "weight_codes", "metadata_indices", "metadata_lut"]
        : ["residual", "norm_weight", "weight_codes", "weight_scales", "weight_biases"]
    func make(_ results: Int) -> MLXFast.MLXFastKernel {
        MLXFast.metalKernel(
            name: "qkv_research_r\(rows)_\(indexed ? "idx" : "ordinary")_v\(results)",
            inputNames: inputNames,
            outputNames: ["projected"],
            source: lagunaNormAffineQKVResearchSource(
                rows: rows, depth: 4, indexed: indexed,
                resultsPerSIMDGroup: results),
            ensureRowContiguous: true
        )
    }
    return QKVResearchKernels(fourRows: make(4), fiveRows: make(5))
}

private func runQKVResearchKernel(
    _ kernel: MLXFast.MLXFastKernel,
    inputs: [MLXArray],
    rows: Int,
    resultsPerSIMDGroup: Int
) -> MLXArray {
    let rowsPerThreadgroup = 2 * resultsPerSIMDGroup
    return kernel(
        inputs,
        grid: (((rows + rowsPerThreadgroup - 1) / rowsPerThreadgroup) * 64, 1, 1),
        threadGroup: (64, 1, 1),
        outputShapes: [[1, 1, rows]],
        outputDTypes: [.bfloat16]
    )[0]
}

private func timeQKVResearchKernels(
    _ kernels: QKVResearchKernels,
    inputs: [MLXArray],
    rows: Int
) -> QKVTimingResult {
    for _ in 0..<3 {
        eval(runQKVResearchKernel(
            kernels.fourRows, inputs: inputs, rows: rows, resultsPerSIMDGroup: 4))
        eval(runQKVResearchKernel(
            kernels.fiveRows, inputs: inputs, rows: rows, resultsPerSIMDGroup: 5))
    }

    var abFour: [Double] = []
    var abFive: [Double] = []
    var baFour: [Double] = []
    var baFive: [Double] = []
    for _ in 0..<30 {
        abFour.append(timedQKVResearchKernel(
            kernels.fourRows, inputs: inputs, rows: rows, resultsPerSIMDGroup: 4))
        abFive.append(timedQKVResearchKernel(
            kernels.fiveRows, inputs: inputs, rows: rows, resultsPerSIMDGroup: 5))
    }
    for _ in 0..<30 {
        baFive.append(timedQKVResearchKernel(
            kernels.fiveRows, inputs: inputs, rows: rows, resultsPerSIMDGroup: 5))
        baFour.append(timedQKVResearchKernel(
            kernels.fourRows, inputs: inputs, rows: rows, resultsPerSIMDGroup: 4))
    }

    let pairedDifferences = zip(abFour, abFive).map { $0 - $1 }
        + zip(baFour, baFive).map { $0 - $1 }
    let pairedMedian = median(pairedDifferences)
    return QKVTimingResult(
        abFour: median(abFour),
        abFive: median(abFive),
        baFour: median(baFour),
        baFive: median(baFive),
        pairedMedian: pairedMedian,
        pairedMAD: median(pairedDifferences.map { abs($0 - pairedMedian) })
    )
}

private func timedQKVResearchKernel(
    _ kernel: MLXFast.MLXFastKernel,
    inputs: [MLXArray],
    rows: Int,
    resultsPerSIMDGroup: Int
) -> Double {
    let output = runQKVResearchKernel(
        kernel, inputs: inputs, rows: rows,
        resultsPerSIMDGroup: resultsPerSIMDGroup)
    let start = DispatchTime.now().uptimeNanoseconds
    eval(output)
    return Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000
}

private func outputBits(_ output: MLXArray) -> [UInt16] {
    output.view(dtype: .uint16).asArray(UInt16.self)
}

private func mismatchCount(_ lhs: [UInt16], _ rhs: [UInt16]) -> Int {
    zip(lhs, rhs).reduce(into: 0) { count, pair in
        if pair.0 != pair.1 { count += 1 }
    }
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}

private func printQKVTiming(rows: Int, mode: String, result: QKVTimingResult) {
    print(
        "QKV_RESEARCH_TIMING rows=\(rows) mode=\(mode) "
            + "ab_four_us=\(result.abFour) ab_five_us=\(result.abFive) "
            + "ab_speedup=\(result.abSpeedup) ba_four_us=\(result.baFour) "
            + "ba_five_us=\(result.baFive) ba_speedup=\(result.baSpeedup) "
            + "paired_median_us=\(result.pairedMedian) "
            + "paired_mad_us=\(result.pairedMAD) "
            + "over_2mad=\(result.pairedMedian > 2 * result.pairedMAD)"
    )
}
