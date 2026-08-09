import Foundation
import MLX
@testable import MLXFastModel
import Testing

private let atlasReferenceKernel = MLXFast.metalKernel(
    name: "laguna_decode_embedding_rope_atlas_bf16_2048_oracle_tg512",
    inputNames: [
        "tokens", "embedding_weight", "full_atlas", "sliding_atlas",
        "atlas_position",
    ],
    outputNames: ["hidden", "full_angles", "sliding_angles"],
    source: """
constexpr uint hidden_size = 2048;
constexpr uint full_width = 64;
constexpr uint sliding_width = 128;

uint lane = thread_position_in_grid.x;
uint token = uint(tokens[0]);
uint position = uint(atlas_position);

const device vec<bfloat, 4>* embedding_vectors =
    (const device vec<bfloat, 4>*) (
        embedding_weight + token * hidden_size);
device vec<bfloat, 4>* hidden_vectors_out =
    (device vec<bfloat, 4>*)(hidden);
hidden_vectors_out[lane] = embedding_vectors[lane];

if (lane < full_width / 4) {
    const device vec<float, 4>* atlas_vectors =
        (const device vec<float, 4>*) (
            full_atlas + position * full_width);
    ((device vec<float, 4>*)(full_angles))[lane] =
        atlas_vectors[lane];
}
if (lane < sliding_width / 4) {
    const device vec<float, 4>* atlas_vectors =
        (const device vec<float, 4>*) (
            sliding_atlas + position * sliding_width);
    ((device vec<float, 4>*)(sliding_angles))[lane] =
        atlas_vectors[lane];
}
""",
    ensureRowContiguous: true
)

private let atlasCandidateKernel = MLXFast.metalKernel(
    name: "laguna_decode_embedding_rope_atlas_bf16_2048_oracle_tg128",
    inputNames: [
        "tokens", "embedding_weight", "full_atlas", "sliding_atlas",
        "atlas_position",
    ],
    outputNames: ["hidden", "full_angles", "sliding_angles"],
    source: """
constexpr uint hidden_size = 2048;
constexpr uint full_width = 64;
constexpr uint sliding_width = 128;

uint lane = thread_position_in_grid.x;
uint token = uint(tokens[0]);
uint position = uint(atlas_position);

const device vec<bfloat, 4>* embedding_vectors =
    (const device vec<bfloat, 4>*) (
        embedding_weight + token * hidden_size);
device vec<bfloat, 4>* hidden_vectors_out =
    (device vec<bfloat, 4>*)(hidden);
hidden_vectors_out[lane] = embedding_vectors[lane];
hidden_vectors_out[lane + 128] = embedding_vectors[lane + 128];
hidden_vectors_out[lane + 256] = embedding_vectors[lane + 256];
hidden_vectors_out[lane + 384] = embedding_vectors[lane + 384];

if (lane < full_width / 4) {
    const device vec<float, 4>* atlas_vectors =
        (const device vec<float, 4>*) (
            full_atlas + position * full_width);
    ((device vec<float, 4>*)(full_angles))[lane] =
        atlas_vectors[lane];
}
if (lane < sliding_width / 4) {
    const device vec<float, 4>* atlas_vectors =
        (const device vec<float, 4>*) (
            sliding_atlas + position * sliding_width);
    ((device vec<float, 4>*)(sliding_angles))[lane] =
        atlas_vectors[lane];
}
""",
    ensureRowContiguous: true
)

@Test
func lagunaDecodeEmbeddingRoPEAtlasTG128MatchesTG512RawBitsWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let tokens = [0, 1, 50_176, 100_350, 100_351]
    let positions = [0, 1, 511, 512, 4_095]
    let embedding = atlasEmbedding(tokens: tokens)
    let fullAtlas = atlasValues(width: 64, positions: positions)
    let slidingAtlas = atlasValues(width: 128, positions: positions)
    var corruptionControlRan = false

    for token in tokens {
        for position in positions {
            let inputs: [any ScalarOrArray] = [
                MLXArray([Int32(token)], [1, 1]),
                embedding,
                fullAtlas,
                slidingAtlas,
                Int32(position),
            ]
            let shapes = [[1, 1, 2_048], [1, 1, 1, 64], [1, 1, 1, 128]]
            let dtypes: [DType] = [.bfloat16, .float32, .float32]
            let reference = atlasReferenceKernel(
                inputs,
                grid: (512, 1, 1),
                threadGroup: (512, 1, 1),
                outputShapes: shapes,
                outputDTypes: dtypes
            )
            let candidate = atlasCandidateKernel(
                inputs,
                grid: (128, 1, 1),
                threadGroup: (128, 1, 1),
                outputShapes: shapes,
                outputDTypes: dtypes
            )
            eval(
                reference[0], reference[1], reference[2],
                candidate[0], candidate[1], candidate[2]
            )

            let context = "token=\(token), position=\(position)"
            let referenceHidden = rawWords(reference[0], as: UInt16.self)
            let candidateHidden = rawWords(candidate[0], as: UInt16.self)
            let referenceFull = rawWords(reference[1], as: UInt32.self)
            let candidateFull = rawWords(candidate[1], as: UInt32.self)
            let referenceSliding = rawWords(reference[2], as: UInt32.self)
            let candidateSliding = rawWords(candidate[2], as: UInt32.self)

            #expect(referenceHidden.count == 2_048, Comment(rawValue: context))
            #expect(candidateHidden.count == 2_048, Comment(rawValue: context))
            #expect(referenceFull.count == 64, Comment(rawValue: context))
            #expect(candidateFull.count == 64, Comment(rawValue: context))
            #expect(referenceSliding.count == 128, Comment(rawValue: context))
            #expect(candidateSliding.count == 128, Comment(rawValue: context))
            #expect(candidateHidden == referenceHidden, Comment(rawValue: context))
            #expect(candidateFull == referenceFull, Comment(rawValue: context))
            #expect(candidateSliding == referenceSliding, Comment(rawValue: context))

            if !corruptionControlRan {
                var corrupted = candidateHidden
                corrupted[1_024] ^= 1
                let mismatches = corrupted.indices.filter { corrupted[$0] != referenceHidden[$0] }
                #expect(mismatches == [1_024])
                corruptionControlRan = true
            }
        }
    }

    #expect(corruptionControlRan)
}

private func atlasEmbedding(tokens: [Int]) -> MLXArray {
    let vocabSize = 100_352
    let hiddenSize = 2_048
    var data = Data(count: vocabSize * hiddenSize * MemoryLayout<UInt16>.size)
    data.withUnsafeMutableBytes { bytes in
        for token in tokens {
            for column in 0..<hiddenSize {
                let value = UInt16(truncatingIfNeeded: token &* 251 &+ column &* 17 &+ 1)
                bytes.storeBytes(
                    of: value.littleEndian,
                    toByteOffset: (token * hiddenSize + column) * MemoryLayout<UInt16>.size,
                    as: UInt16.self
                )
            }
        }
    }
    return MLXArray(data, [vocabSize, hiddenSize], dtype: .bfloat16)
}

private func atlasValues(width: Int, positions: [Int]) -> MLXArray {
    let atlasLength = 4_096
    var data = Data(count: atlasLength * width * MemoryLayout<UInt32>.size)
    data.withUnsafeMutableBytes { bytes in
        for position in positions {
            for column in 0..<width {
                let value = Float(position * width + column + 1).bitPattern
                bytes.storeBytes(
                    of: value.littleEndian,
                    toByteOffset: (position * width + column) * MemoryLayout<UInt32>.size,
                    as: UInt32.self
                )
            }
        }
    }
    return MLXArray(data, [1, 1, atlasLength, width], dtype: .float32)
}

private func rawWords<T: FixedWidthInteger>(_ array: MLXArray, as: T.Type) -> [T] {
    let data = array.asData(access: .copy).data
    return data.withUnsafeBytes { bytes in
        stride(from: 0, to: bytes.count, by: MemoryLayout<T>.size).map {
            T(littleEndian: bytes.loadUnaligned(fromByteOffset: $0, as: T.self))
        }
    }
}
