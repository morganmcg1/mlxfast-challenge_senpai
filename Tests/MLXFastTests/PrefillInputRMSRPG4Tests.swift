import Foundation
import MLX
@testable import MLXFastModel
import Testing

private let prefillInputRMSRPG4Epsilon: Float = 1e-6
private let prefillInputRMSRPG4Width = 2048

private func bf16Array(bits: [UInt16], shape: [Int]) -> MLXArray {
    MLXArray(bits, shape).view(dtype: .bfloat16)
}

private func repeatedBF16Pattern(_ pattern: [UInt16], rows: Int) -> MLXArray {
    let count = rows * prefillInputRMSRPG4Width
    let bits = (0..<count).map { pattern[$0 % pattern.count] }
    return bf16Array(bits: bits, shape: [1, rows, prefillInputRMSRPG4Width])
}

private func stockInputRMS(_ input: MLXArray, weight: MLXArray) -> MLXArray {
    MLXFast.rmsNorm(input, weight: weight, eps: prefillInputRMSRPG4Epsilon)
}

private func exactBytes(_ array: MLXArray) -> Data {
    array.asData(access: .copy).data
}

private func requireExactInputRMSMatch(
    input: MLXArray, weight: MLXArray, label: String
) throws -> Data {
    let candidate = try #require(
        lagunaPrefillInputRMSRPG4(
            input, weight: weight, epsilon: prefillInputRMSRPG4Epsilon
        ),
        "candidate declined supported case \(label)"
    )
    let stock = stockInputRMS(input, weight: weight)
    eval(candidate, stock)

    #expect(candidate.dtype == .bfloat16)
    #expect(candidate.shape == stock.shape)
    let candidateBytes = exactBytes(candidate)
    let stockBytes = exactBytes(stock)
    #expect(candidateBytes == stockBytes, "byte mismatch for \(label)")
    print("prefill_input_rms_rpg4_exact label=\(label) bytes=\(candidateBytes.count)")
    return stockBytes
}

@Test
func prefillInputRMSRPG4MatchesStockBytesWhenRuntimeTestsAreEnabled() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
    else { return }
    #expect(
        ProcessInfo.processInfo.environment["DARKBLOOM_PREFILL_INPUT_RMS_RPG4"] == "1"
    )

    let store = try DenseTensorStore(weightsPath: "weights")
    let tensor = try store.materializedTensor(
        named: "model.layers.0.input_layernorm.weight"
    )
    let realWeight = try MLXArrayTensorBridge().makeArray(from: tensor)
    #expect(realWeight.dtype == .bfloat16)
    #expect(realWeight.shape == [prefillInputRMSRPG4Width])

    let finitePattern: [UInt16] = [
        0x0000, 0x8000, 0x0001, 0x8001, 0x007f, 0x807f, 0x0080, 0x8080,
        0x3f80, 0xbf80, 0x3f00, 0xbf00, 0x4000, 0xc000, 0x7f7f, 0xff7f,
    ]
    let nonfinitePattern: [UInt16] = [
        0x0000, 0x8000, 0x3f80, 0xbf80, 0x7f80, 0xff80, 0x7fc1, 0xffc1,
        0x0001, 0x8001, 0x7f7f, 0xff7f, 0x3f00, 0xbf00, 0x4000, 0xc000,
    ]

    var finiteRows4Stock = Data()
    for rows in [4, 8, 512] {
        let finiteInput = repeatedBF16Pattern(finitePattern, rows: rows)
        let stockBytes = try requireExactInputRMSMatch(
            input: finiteInput, weight: realWeight, label: "real_weight_finite_rows_\(rows)"
        )
        if rows == 4 {
            finiteRows4Stock = stockBytes
        }
        _ = try requireExactInputRMSMatch(
            input: repeatedBF16Pattern(nonfinitePattern, rows: rows),
            weight: realWeight,
            label: "real_weight_nonfinite_rows_\(rows)"
        )
    }

    let adversarialWeight = bf16Array(
        bits: (0..<prefillInputRMSRPG4Width).map {
            nonfinitePattern[$0 % nonfinitePattern.count]
        },
        shape: [prefillInputRMSRPG4Width]
    )
    _ = try requireExactInputRMSMatch(
        input: repeatedBF16Pattern(finitePattern, rows: 4),
        weight: adversarialWeight,
        label: "adversarial_weight_rows_4"
    )

    var corrupted = finiteRows4Stock
    corrupted[corrupted.startIndex] ^= 1
    #expect(corrupted != finiteRows4Stock, "positive corruption control was not detected")
    print("prefill_input_rms_rpg4_positive_corruption_detected=true")
}

@Test
func prefillInputRMSRPG4DeclinesUnsupportedCasesWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
    else { return }

    let weight = repeatedBF16Pattern([0x3f80], rows: 1).reshaped([
        prefillInputRMSRPG4Width
    ])
    for rows in [1, 2, 3, 5, 511, 513] {
        let input = repeatedBF16Pattern([0x3f80], rows: rows)
        #expect(
            lagunaPrefillInputRMSRPG4(
                input, weight: weight, epsilon: prefillInputRMSRPG4Epsilon
            ) == nil,
            "candidate accepted unsupported row count \(rows)"
        )
    }

    let supportedInput = repeatedBF16Pattern([0x3f80], rows: 4)
    #expect(
        lagunaPrefillInputRMSRPG4(
            supportedInput.asType(.float32),
            weight: weight,
            epsilon: prefillInputRMSRPG4Epsilon
        ) == nil
    )
    #expect(
        lagunaPrefillInputRMSRPG4(
            supportedInput,
            weight: weight.asType(.float32),
            epsilon: prefillInputRMSRPG4Epsilon
        ) == nil
    )
    #expect(
        lagunaPrefillInputRMSRPG4(
            supportedInput,
            weight: weight,
            epsilon: prefillInputRMSRPG4Epsilon.nextUp
        ) == nil
    )
    print("prefill_input_rms_rpg4_fallback_rows=1,2,3,5,511,513")
}
