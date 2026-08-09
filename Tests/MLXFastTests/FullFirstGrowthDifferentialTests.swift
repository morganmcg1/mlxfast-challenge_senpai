import Foundation
import MLX
@testable import MLXFastModel
import Testing

@Test
func fullFirstGrowthCopiesAppendsAndPreservesPoisonGuardsWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let heads = 8
    let oldLength = 512
    let grownLength = 768
    let width = 128
    let guardedWidth = 132

    func backing(length: Int, salt: Int, poison: Float) -> [Float] {
        var values = Array(repeating: poison, count: heads * length * guardedWidth)
        for head in 0..<heads {
            for row in 0..<length {
                let start = (head * length + row) * guardedWidth
                for column in 0..<width {
                    values[start + column] = Float((head * 19 + row * 7 + column + salt) % 97 - 48)
                }
            }
        }
        return values
    }

    let oldKeyExpected = backing(length: oldLength, salt: 3, poison: 4096)
    let oldValueExpected = backing(length: oldLength, salt: 11, poison: -4096)
    let newKeyExpected = backing(length: 1, salt: 23, poison: 2048)
    let newValueExpected = backing(length: 1, salt: 41, poison: -2048)

    let oldKeyBacking = MLXArray(oldKeyExpected, [1, heads, oldLength, guardedWidth])
        .asType(.bfloat16)
    let oldValueBacking = MLXArray(oldValueExpected, [1, heads, oldLength, guardedWidth])
        .asType(.bfloat16)
    let newKeyBacking = MLXArray(newKeyExpected, [1, heads, 1, guardedWidth])
        .asType(.bfloat16)
    let newValueBacking = MLXArray(newValueExpected, [1, heads, 1, guardedWidth])
        .asType(.bfloat16)
    let oldKeys = oldKeyBacking[.ellipsis, 0..<width]
    let oldValues = oldValueBacking[.ellipsis, 0..<width]
    let newKeys = newKeyBacking[.ellipsis, 0..<width]
    let newValues = newValueBacking[.ellipsis, 0..<width]

    #expect(oldKeys.asData(access: .noCopy).strides[2] == guardedWidth)
    #expect(oldValues.asData(access: .noCopy).strides[2] == guardedWidth)
    #expect(newKeys.asData(access: .noCopy).strides[1] == guardedWidth)
    #expect(newValues.asData(access: .noCopy).strides[1] == guardedWidth)

    let grown = lagunaFullFirstGrowth(
        oldKeys: oldKeys,
        oldValues: oldValues,
        newKeys: newKeys,
        newValues: newValues
    )
    eval(grown.0, grown.1)

    func expectedGrowth(old: [Float], new: [Float]) -> [Float] {
        var expected = Array(repeating: Float.zero, count: heads * grownLength * width)
        for head in 0..<heads {
            for row in 0..<oldLength {
                let source = (head * oldLength + row) * width
                let destination = (head * grownLength + row) * width
                expected[destination..<(destination + width)] = old[source..<(source + width)]
            }
            let source = head * width
            let destination = (head * grownLength + oldLength) * width
            expected[destination..<(destination + width)] = new[source..<(source + width)]
        }
        return expected
    }

    let oldKeyLogical = oldKeys.asArray(Float.self)
    let oldValueLogical = oldValues.asArray(Float.self)
    let newKeyLogical = newKeys.asArray(Float.self)
    let newValueLogical = newValues.asArray(Float.self)
    #expect(grown.0.shape == [1, heads, grownLength, width])
    #expect(grown.1.shape == [1, heads, grownLength, width])
    #expect(grown.0.asArray(Float.self) == expectedGrowth(old: oldKeyLogical, new: newKeyLogical))
    #expect(grown.1.asArray(Float.self) == expectedGrowth(old: oldValueLogical, new: newValueLogical))

    #expect(oldKeyBacking.asArray(Float.self) == oldKeyExpected)
    #expect(oldValueBacking.asArray(Float.self) == oldValueExpected)
    #expect(newKeyBacking.asArray(Float.self) == newKeyExpected)
    #expect(newValueBacking.asArray(Float.self) == newValueExpected)
}
