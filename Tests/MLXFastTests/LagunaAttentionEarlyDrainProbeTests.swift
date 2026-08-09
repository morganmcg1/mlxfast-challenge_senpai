import Foundation
import MLX
@testable import MLXFastModel
import Testing

@Suite(.serialized)
struct LagunaAttentionEarlyDrainProbeTests {
    private struct Inputs {
        let rawQueries: MLXArray
        let rawKeys: MLXArray
        let rawValues: MLXArray
        let queryWeight: MLXArray
        let keyWeight: MLXArray
        let angles: MLXArray
        let cacheKeys: MLXArray
        let cacheValues: MLXArray
        let scale: MLXArray
    }

    private func deterministic(
        _ shape: [Int], salt: Float, dtype: DType
    ) -> MLXArray {
        let count = shape.reduce(1, *)
        let axis = MLXArray(0..<count).asType(.float32)
        return (sin(axis * 0.013 + salt) * 0.125)
            .asType(dtype)
            .reshaped(shape)
    }

    private func makeInputs(
        heads: Int,
        angleWidth: Int,
        cacheCapacity: Int,
        salt: Float
    ) -> Inputs {
        let headDim = 128
        let kvHeads = 8
        let inputs = Inputs(
            rawQueries: deterministic(
                [1, 1, heads * headDim], salt: salt + 0.1, dtype: .bfloat16),
            rawKeys: deterministic(
                [1, 1, kvHeads * headDim], salt: salt + 0.2, dtype: .bfloat16),
            rawValues: deterministic(
                [1, 1, kvHeads * headDim], salt: salt + 0.3, dtype: .bfloat16),
            queryWeight: deterministic(
                [headDim], salt: salt + 0.4, dtype: .bfloat16),
            keyWeight: deterministic(
                [headDim], salt: salt + 0.5, dtype: .bfloat16),
            angles: deterministic(
                [1, 1, 1, angleWidth], salt: salt + 0.6, dtype: .float32),
            cacheKeys: deterministic(
                [1, kvHeads, cacheCapacity, headDim],
                salt: salt + 0.7,
                dtype: .bfloat16),
            cacheValues: deterministic(
                [1, kvHeads, cacheCapacity, headDim],
                salt: salt + 0.8,
                dtype: .bfloat16),
            scale: MLXArray([pow(Float(headDim), -0.5)])
        )
        eval([
            inputs.rawQueries, inputs.rawKeys, inputs.rawValues,
            inputs.queryWeight, inputs.keyWeight, inputs.angles,
            inputs.cacheKeys, inputs.cacheValues, inputs.scale,
        ])
        Stream.gpu.synchronize()
        return inputs
    }

    private func append(
        _ array: MLXArray,
        label: String,
        to artifact: inout Data
    ) {
        let native = array.asData(access: .copy)
        artifact.append(
            Data(
                "\(label) shape=\(native.shape) dtype=\(native.dType) bytes=\(native.data.count)\n"
                    .utf8))
        artifact.append(native.data)
        artifact.append(0x0a)
    }

    @Test
    func oracleArtifacts() throws {
        guard let artifactPath = ProcessInfo.processInfo.environment[
            "MLXFAST_ATTENTION_ORACLE_PATH"
        ] else {
            return
        }

        var artifact = Data("laguna-attention-early-drain-oracle-v1\n".utf8)
        for logicalPosition in [511, 512, 513, 639] {
            let salt = Float(logicalPosition) * 0.001
            let sliding = makeInputs(
                heads: 64,
                angleWidth: 128,
                cacheCapacity: 512,
                salt: salt)
            let slidingOutput = lagunaSlidingFusedAttention(
                rawQueries: sliding.rawQueries,
                rawKeys: sliding.rawKeys,
                rawValues: sliding.rawValues,
                queryWeight: sliding.queryWeight,
                keyWeight: sliding.keyWeight,
                angles: sliding.angles,
                cacheKeys: sliding.cacheKeys,
                cacheValues: sliding.cacheValues,
                writeIdx: logicalPosition % 512,
                scale: sliding.scale)
            eval(slidingOutput)
            Stream.gpu.synchronize()
            append(
                slidingOutput,
                label: "sliding.position.\(logicalPosition).attended",
                to: &artifact)
            append(
                sliding.cacheKeys,
                label: "sliding.position.\(logicalPosition).cache_keys",
                to: &artifact)
            append(
                sliding.cacheValues,
                label: "sliding.position.\(logicalPosition).cache_values",
                to: &artifact)

            let full = makeInputs(
                heads: 48,
                angleWidth: 64,
                cacheCapacity: 768,
                salt: salt + 1.0)
            let fullOutput = lagunaFullFusedAttention(
                rawQueries: full.rawQueries,
                rawKeys: full.rawKeys,
                rawValues: full.rawValues,
                queryWeight: full.queryWeight,
                keyWeight: full.keyWeight,
                angles: full.angles,
                cacheKeys: full.cacheKeys,
                cacheValues: full.cacheValues,
                writeIdx: logicalPosition,
                scale: full.scale)
            eval(fullOutput)
            Stream.gpu.synchronize()
            append(
                fullOutput,
                label: "full.position.\(logicalPosition).attended",
                to: &artifact)
            append(
                full.cacheKeys,
                label: "full.position.\(logicalPosition).cache_keys",
                to: &artifact)
            append(
                full.cacheValues,
                label: "full.position.\(logicalPosition).cache_values",
                to: &artifact)
        }

        try artifact.write(to: URL(fileURLWithPath: artifactPath))
        print("ORACLE,path=\(artifactPath),bytes=\(artifact.count)")
    }

    private func timedBatch(
        family: String,
        makeOutput: () -> MLXArray
    ) {
        let batchSize = 128
        for _ in 0..<2 {
            let outputs = (0..<batchSize).map { _ in makeOutput() }
            eval(outputs)
            Stream.gpu.synchronize()
        }

        let outputs = (0..<batchSize).map { _ in makeOutput() }
        let start = DispatchTime.now().uptimeNanoseconds
        eval(outputs)
        Stream.gpu.synchronize()
        let elapsed = DispatchTime.now().uptimeNanoseconds - start
        print(
            "TIMING,family=\(family),kernels=\(batchSize),ns=\(elapsed),ns_per_kernel=\(Double(elapsed) / Double(batchSize))"
        )
    }

    @Test
    func isolatedTiming() {
        guard ProcessInfo.processInfo.environment[
            "MLXFAST_RUN_ATTENTION_EARLY_DRAIN_TIMING"
        ] == "1" else {
            return
        }

        let sliding = makeInputs(
            heads: 64,
            angleWidth: 128,
            cacheCapacity: 512,
            salt: 2.0)
        timedBatch(family: "sliding") {
            lagunaSlidingFusedAttention(
                rawQueries: sliding.rawQueries,
                rawKeys: sliding.rawKeys,
                rawValues: sliding.rawValues,
                queryWeight: sliding.queryWeight,
                keyWeight: sliding.keyWeight,
                angles: sliding.angles,
                cacheKeys: sliding.cacheKeys,
                cacheValues: sliding.cacheValues,
                writeIdx: 0,
                scale: sliding.scale)
        }

        let full = makeInputs(
            heads: 48,
            angleWidth: 64,
            cacheCapacity: 768,
            salt: 3.0)
        timedBatch(family: "full") {
            lagunaFullFusedAttention(
                rawQueries: full.rawQueries,
                rawKeys: full.rawKeys,
                rawValues: full.rawValues,
                queryWeight: full.queryWeight,
                keyWeight: full.keyWeight,
                angles: full.angles,
                cacheKeys: full.cacheKeys,
                cacheValues: full.cacheValues,
                writeIdx: 512,
                scale: full.scale)
        }
    }
}
