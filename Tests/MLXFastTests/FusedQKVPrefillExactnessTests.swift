import Foundation
import MLX
@testable import MLXFastModel
import Testing

private let qkvLength = 512
private let qkvHidden = 2_048
private let qkvQueryDim = 6_144
private let qkvKVDim = 1_024
private let qkvOutputDim = 8_192
private let qkvAtlasLength = 4_096
private let qkvHeadDim = 128

@Test
func fusedQKVPrefillEpilogueMatchesStandalonePipelineExactlyWhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
    else { return }

    let kAxis = MLXArray(0..<qkvHidden).asType(.float32).reshaped(1, qkvHidden)
    let rowAxis = MLXArray(0..<qkvLength).asType(.float32).reshaped(qkvLength, 1)
    let outputAxis = MLXArray(0..<qkvOutputDim).asType(.float32)
        .reshaped(qkvOutputDim, 1)
    let input = (sin(kAxis * 0.017 + rowAxis * 0.031) * 0.125)
        .asType(.bfloat16).reshaped(1, qkvLength, qkvHidden)
    let weight = (cos(kAxis * 0.013 + outputAxis * 0.007) * 0.0625)
        .asType(.bfloat16)

    let headAxis = MLXArray(0..<qkvHeadDim).asType(.float32)
    let queryWeight = (sin(headAxis * 0.021) * 0.25 + 1).asType(.bfloat16)
    let keyWeight = (cos(headAxis * 0.019) * 0.25 + 1).asType(.bfloat16)
    let positionAxis = MLXArray(0..<qkvAtlasLength).asType(.float32)
        .reshaped(qkvAtlasLength, 1)
    let rotaryAxis = MLXArray(0..<(qkvHeadDim / 2)).asType(.float32)
        .reshaped(1, qkvHeadDim / 2)
    let angleRows = positionAxis * 0.00031 + rotaryAxis * 0.0017
    let angles = angleRows.reshaped(1, 1, qkvAtlasLength, qkvHeadDim / 2)
    let offset = 3
    let offsets = MLXArray([Int32(offset)])

    let qMetadata = broadcast(
        queryWeight.reshaped(1, qkvHeadDim),
        to: [qkvAtlasLength, qkvHeadDim])
    let kMetadata = broadcast(
        keyWeight.reshaped(1, qkvHeadDim),
        to: [qkvAtlasLength, qkvHeadDim])
    let metadata = concatenated(
        [qMetadata, kMetadata, angleRows.view(dtype: .bfloat16)], axis: 1)
    let c = asStrided(
        metadata, [1, qkvLength, qkvOutputDim],
        strides: [0, 384, 0], offset: offset * 384)

    let fused = addMM(c, input, weight.T, beta: 0).reshaped(-1)
    let raw = matmul(input, weight.T)
    let (referenceQueries, referenceKeys) = lagunaPrefillFullQKNormYaRN(
        rawQueries: raw[.ellipsis, 0..<qkvQueryDim],
        rawKeys: raw[.ellipsis, qkvQueryDim..<(qkvQueryDim + qkvKVDim)],
        queryWeight: queryWeight,
        keyWeight: keyWeight,
        angles: angles,
        offsets: offsets,
        length: qkvLength)
    let qEnd = qkvLength * qkvQueryDim
    let kEnd = qEnd + qkvLength * qkvKVDim
    let fusedQueries = fused[0..<qEnd].reshaped(1, 48, qkvLength, qkvHeadDim)
    let fusedKeys = fused[qEnd..<kEnd].reshaped(1, 8, qkvLength, qkvHeadDim)
    let fusedVFlat = fused[kEnd..<(kEnd + qkvLength * qkvKVDim)]
    let fusedValues = fusedVFlat.reshaped(1, qkvLength, qkvKVDim)
    let fusedValuesAsHeadMajor = fusedVFlat
        .reshaped(1, 8, qkvLength, qkvHeadDim)
        .transposed(0, 2, 1, 3)
        .reshaped(1, qkvLength, qkvKVDim)
    let referenceValues = raw[
        .ellipsis,
        (qkvQueryDim + qkvKVDim)..<(qkvQueryDim + 2 * qkvKVDim)]

    eval(
        fusedQueries, fusedKeys, fusedValues, fusedValuesAsHeadMajor,
        referenceQueries, referenceKeys, referenceValues)
    let qMismatches = mismatchCount(fusedQueries, referenceQueries)
    let kMismatches = mismatchCount(fusedKeys, referenceKeys)
    let vMismatches = mismatchCount(fusedValues, referenceValues)
    let vHeadMajorMismatches = mismatchCount(
        fusedValuesAsHeadMajor, referenceValues)
    let fusedVBits = fusedValues.view(dtype: .uint16).asArray(UInt16.self)
    let referenceVBits = referenceValues.view(dtype: .uint16).asArray(UInt16.self)
    print(
        "fused_qkv_exactness offset=\(offset) q_mismatches=\(qMismatches) "
            + "k_mismatches=\(kMismatches) v_mismatches=\(vMismatches) "
            + "v_head_major_mismatches=\(vHeadMajorMismatches)"
    )
    print(
        "fused_qkv_v_samples fused=\(Array(fusedVBits.prefix(16))) "
            + "reference=\(Array(referenceVBits.prefix(16)))"
    )
    #expect(qMismatches == 0)
    #expect(kMismatches == 0)
    #expect(vMismatches == 0)

    let neighborLength = qkvLength - 1
    let neighborInput = input[0..., 0..<neighborLength, 0...]
    let neighborC = asStrided(
        metadata, [1, neighborLength, qkvOutputDim],
        strides: [0, 384, 0], offset: offset * 384)
    let neighborActual = addMM(neighborC, neighborInput, weight.T, beta: 0)
    let neighborReference = matmul(neighborInput, weight.T)
    eval(neighborActual, neighborReference)
    let neighborMismatches = mismatchCount(neighborActual, neighborReference)
    print(
        "fused_qkv_neighbor_fallback M=\(neighborLength) "
            + "mismatches=\(neighborMismatches)"
    )
    #expect(neighborMismatches == 0)
}

private func mismatchCount(_ lhs: MLXArray, _ rhs: MLXArray) -> Int {
    let lhsBits = lhs.view(dtype: .uint16).asArray(UInt16.self)
    let rhsBits = rhs.view(dtype: .uint16).asArray(UInt16.self)
    return zip(lhsBits, rhsBits).reduce(into: 0) { count, pair in
        if pair.0 != pair.1 { count += 1 }
    }
}
