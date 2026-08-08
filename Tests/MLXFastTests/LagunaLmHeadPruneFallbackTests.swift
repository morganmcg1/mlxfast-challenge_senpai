import MLX
@testable import MLXFastModel
import Testing

@Test
func lmHeadPrunerRejectsUnsupportedShapeAndDType() {
    let unsupportedShape = MLXArray.zeros([1, 2_048], dtype: .bfloat16)
    #expect(LagunaLmHeadPruner(lmHeadWeight: unsupportedShape) == nil)

    let unsupportedDType = MLXArray.zeros([100_352, 2_048], dtype: .float32)
    #expect(LagunaLmHeadPruner(lmHeadWeight: unsupportedDType) == nil)
}

@Test
func lmHeadPrunerUsesMXFP8WhenInt5CertificationFails() throws {
    let uncertifiableWeight = MLXArray.full(
        [100_352, 2_048],
        values: MLXArray(Float.infinity),
        dtype: .bfloat16
    )
    let pruner = try #require(LagunaLmHeadPruner(lmHeadWeight: uncertifiableWeight))

    #expect(pruner.int5CodesLo == nil)
    #expect(pruner.int5CodesHi == nil)
    #expect(pruner.int5Scales == nil)
    #expect(pruner.codes != nil)
    #expect(pruner.scales != nil)
    #expect(pruner.residentArrays.count == 2)
}
