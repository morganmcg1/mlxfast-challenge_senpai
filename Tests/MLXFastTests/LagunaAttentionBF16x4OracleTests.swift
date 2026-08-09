import Foundation
import MLX
@testable import MLXFastModel
import XCTest

final class LagunaAttentionBF16x4OracleTests: XCTestCase {
    private let headDim = 128
    private let kvHeads = 8

    func testRawByteOracle() throws {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
        else {
            throw XCTSkip("set MLXFAST_RUN_MLX_RUNTIME_TESTS=1")
        }
        guard let outputPath = ProcessInfo.processInfo.environment[
            "MLXFAST_ATTENTION_ORACLE_OUTPUT"]
        else {
            XCTFail("MLXFAST_ATTENTION_ORACLE_OUTPUT is required")
            return
        }

        var artifact = Data("mlxfast-bf16x4-oracle-v1\n".utf8)
        try appendSpecialConversionOracle(to: &artifact)
        for position in [511, 512, 513, 639] {
            appendSliding(position: position, to: &artifact)
            appendFull(position: position, to: &artifact)
        }
        try artifact.write(to: URL(fileURLWithPath: outputPath), options: .atomic)
        print("bf16x4_oracle_path=\(outputPath) bytes=\(artifact.count)")
    }

    private func appendSpecialConversionOracle(to artifact: inout Data) throws {
        let inputBits: [UInt32] = [
            0x0000_0000, 0x8000_0000,
            0x0000_0001, 0x8000_0001,
            0x0000_8000, 0x8000_8000,
            0x0001_0000, 0x8001_0000,
            0x0001_8000, 0x8001_8000,
            0x3f80_8000, 0xbf80_8000,
            0x3f81_8000, 0xbf81_8000,
            0x7f7f_ffff, 0xff7f_ffff,
            0x7f80_0000, 0xff80_0000,
            0x7fc0_0000, 0xffc0_0000,
            0x7fa0_0001, 0xffa0_0001,
            0x0080_0000, 0x8080_0000,
        ]
        let input = MLXArray(inputBits).view(dtype: .float32)
        let kernel = MLXFast.metalKernel(
            name: "laguna_bf16x4_store_oracle",
            inputNames: ["input"],
            outputNames: ["scalar_out", "vector_out"],
            source: """
                uint base = thread_position_in_grid.x * 4;
                scalar_out[base + 0] = static_cast<bfloat>(input[base + 0]);
                scalar_out[base + 1] = static_cast<bfloat>(input[base + 1]);
                scalar_out[base + 2] = static_cast<bfloat>(input[base + 2]);
                scalar_out[base + 3] = static_cast<bfloat>(input[base + 3]);
                *reinterpret_cast<device vec<bfloat, 4>*>(vector_out + base) =
                    vec<bfloat, 4>(
                        static_cast<bfloat>(input[base + 0]),
                        static_cast<bfloat>(input[base + 1]),
                        static_cast<bfloat>(input[base + 2]),
                        static_cast<bfloat>(input[base + 3]));
                """)
        let outputs = kernel(
            [input],
            grid: (inputBits.count / 4, 1, 1),
            threadGroup: (inputBits.count / 4, 1, 1),
            outputShapes: [[inputBits.count], [inputBits.count]],
            outputDTypes: [.bfloat16, .bfloat16]
        )
        eval(outputs)
        let scalarBits = outputs[0].view(dtype: .uint16).asArray(UInt16.self)
        let vectorBits = outputs[1].view(dtype: .uint16).asArray(UInt16.self)
        XCTAssertEqual(scalarBits, vectorBits)
        append(label: "special/input-f32-bits", bytes: input.asData(access: .copy).data,
               to: &artifact)
        append(array: outputs[0], label: "special/scalar-bf16", to: &artifact)
        append(array: outputs[1], label: "special/vector-bf16", to: &artifact)
        print("bf16x4_special_cases=\(inputBits.count) scalar_vector_mismatches=0")
    }

    private func appendSliding(position: Int, to artifact: inout Data) {
        let heads = 64
        let window = 512
        let writeIndex = position % window
        let query = deterministicBF16(
            shape: [1, 1, heads * headDim], phase: Float(position) * 0.001 + 0.1)
        let key = deterministicBF16(
            shape: [1, 1, kvHeads * headDim], phase: Float(position) * 0.001 + 0.2)
        let value = deterministicBF16(
            shape: [1, 1, kvHeads * headDim], phase: Float(position) * 0.001 + 0.3)
        let queryWeight = deterministicWeight(phase: 0.4)
        let keyWeight = deterministicWeight(phase: 0.5)
        let angles = identityAngles(rotaryDimensions: headDim)
        let cacheShape = [1, kvHeads, window, headDim]
        let cacheKeys = deterministicBF16(shape: cacheShape, phase: 0.6)
        let cacheValues = deterministicBF16(shape: cacheShape, phase: 0.7)
        let output = lagunaSlidingFusedAttention(
            rawQueries: query,
            rawKeys: key,
            rawValues: value,
            queryWeight: queryWeight,
            keyWeight: keyWeight,
            angles: angles,
            cacheKeys: cacheKeys,
            cacheValues: cacheValues,
            writeIdx: writeIndex,
            scale: MLXArray([Float(1.0 / sqrt(Float(headDim)))])
        )
        eval(output)
        append(array: output, label: "sliding/\(position)/output", to: &artifact)
        append(array: cacheKeys, label: "sliding/\(position)/cache-keys", to: &artifact)
        append(array: cacheValues, label: "sliding/\(position)/cache-values", to: &artifact)
        print("bf16x4_sliding_position=\(position) write_index=\(writeIndex)")
    }

    private func appendFull(position: Int, to artifact: inout Data) {
        let heads = 48
        let capacity = 768
        let query = deterministicBF16(
            shape: [1, 1, heads * headDim], phase: Float(position) * 0.001 + 0.8)
        let key = deterministicBF16(
            shape: [1, 1, kvHeads * headDim], phase: Float(position) * 0.001 + 0.9)
        let value = deterministicBF16(
            shape: [1, 1, kvHeads * headDim], phase: Float(position) * 0.001 + 1.0)
        let queryWeight = deterministicWeight(phase: 1.1)
        let keyWeight = deterministicWeight(phase: 1.2)
        let angles = identityAngles(rotaryDimensions: headDim / 2)
        let cacheShape = [1, kvHeads, capacity, headDim]
        let cacheKeys = deterministicBF16(shape: cacheShape, phase: 1.3)
        let cacheValues = deterministicBF16(shape: cacheShape, phase: 1.4)
        let output = lagunaFullFusedAttention(
            rawQueries: query,
            rawKeys: key,
            rawValues: value,
            queryWeight: queryWeight,
            keyWeight: keyWeight,
            angles: angles,
            cacheKeys: cacheKeys,
            cacheValues: cacheValues,
            writeIdx: position,
            scale: MLXArray([Float(1.0 / sqrt(Float(headDim)))])
        )
        eval(output)
        append(array: output, label: "full/\(position)/output", to: &artifact)
        append(array: cacheKeys, label: "full/\(position)/cache-keys", to: &artifact)
        append(array: cacheValues, label: "full/\(position)/cache-values", to: &artifact)
        print("bf16x4_full_position=\(position) capacity=\(capacity)")
    }

    private func deterministicBF16(shape: [Int], phase: Float) -> MLXArray {
        let count = shape.reduce(1, *)
        let axis = MLXArray(0..<count).asType(.float32)
        return (sin(axis * 0.0013 + phase) * 0.125)
            .asType(.bfloat16)
            .reshaped(shape)
    }

    private func deterministicWeight(phase: Float) -> MLXArray {
        let axis = MLXArray(0..<headDim).asType(.float32)
        return (cos(axis * 0.017 + phase) * 0.25 + 1.0).asType(.bfloat16)
    }

    private func identityAngles(rotaryDimensions: Int) -> MLXArray {
        let half = rotaryDimensions / 2
        return MLXArray(
            Array(repeating: Float(1), count: half)
                + Array(repeating: Float(0), count: half)
        ).reshaped([1, 1, 1, rotaryDimensions])
    }

    private func append(array: MLXArray, label: String, to artifact: inout Data) {
        eval(array)
        append(label: label, bytes: array.asData(access: .copy).data, to: &artifact)
    }

    private func append(label: String, bytes: Data, to artifact: inout Data) {
        let labelBytes = Data(label.utf8)
        append(UInt32(labelBytes.count), to: &artifact)
        artifact.append(labelBytes)
        append(UInt64(bytes.count), to: &artifact)
        artifact.append(bytes)
    }

    private func append<T: FixedWidthInteger>(_ value: T, to data: inout Data) {
        var littleEndian = value.littleEndian
        Swift.withUnsafeBytes(of: &littleEndian) { data.append(contentsOf: $0) }
    }
}
