import MLX
import MLXLMCommon
import Testing

@Suite(.serialized)
struct RouteSorterPropertyTemporaryTests {
    private let routeCount = 4096
    private let topK = 8
    private let width = 4

    @Test func persistentSidecarSorterPropertyMatrix() {
        let cases: [(String, [UInt32])] = [
            ("router-like", routerLike()),
            ("balanced", (0 ..< routeCount).map { UInt32($0 % 256) }),
            ("duplicate-heavy", (0 ..< routeCount).map { $0 % 10 == 0 ? UInt32($0 % 256) : 17 }),
            ("all-equal", Array(repeating: 91, count: routeCount)),
            ("zero-and-255", (0 ..< routeCount).map { $0.isMultiple(of: 3) ? 0 : 255 }),
            ("boundary-keys", boundaryKeys()),
            ("random", randomKeys(seed: 0x738C_EDA4)),
            ("reverse-blocks", (0 ..< routeCount).map { UInt32(255 - (($0 / 16) % 256)) }),
        ]

        for repetition in 0 ..< 20 {
            for (name, keys) in cases {
                check(keys: keys, name: name, repetition: repetition)
            }
        }
    }

    private func check(keys: [UInt32], name: String, repetition: Int) {
        let rows = routeCount / topK
        let values = (0 ..< rows * width).map { Float(($0 * 17 + 3) % 1024) / 16 }
        let x = MLXArray(values).reshaped(1, rows, width).asType(.bfloat16)
        let indices = MLXArray(keys).reshaped(1, rows, topK)
        let (sortedX, sidecar, inverse) = gatherSort(
            x: x, indices: indices, expertBoundsSidecar: true)
        let physicalPrefixes = asStrided(sidecar, [257], strides: [1])
        let restored = sortedX[inverse]
        eval(sortedX, physicalPrefixes, inverse, restored)

        var counts = Array(repeating: 0, count: 256)
        for key in keys {
            counts[Int(key)] += 1
        }
        var expectedPrefixes = Array(repeating: 0, count: 257)
        for expert in 0 ..< 256 {
            expectedPrefixes[expert + 1] = expectedPrefixes[expert] + counts[expert]
        }
        let prefixValues = physicalPrefixes.asArray(UInt32.self).map(Int.init)
        #expect(
            prefixValues == expectedPrefixes,
            "\(name) repetition \(repetition): physical prefix mismatch")

        let inverseValues = inverse.asArray(UInt32.self).map(Int.init)
        #expect(
            inverseValues.sorted() == Array(0 ..< routeCount),
            "\(name) repetition \(repetition): inverse is not a permutation")

        var sortedKeys = Array(repeating: -1, count: routeCount)
        for (inputOffset, outputOffset) in inverseValues.enumerated() {
            sortedKeys[outputOffset] = Int(keys[inputOffset])
        }
        for expert in 0 ..< 256 {
            #expect(
                sortedKeys[expectedPrefixes[expert] ..< expectedPrefixes[expert + 1]]
                    .allSatisfy { $0 == expert },
                "\(name) repetition \(repetition): expert segment mismatch")
        }

        let sourceBits = x.view(dtype: .uint16).asArray(UInt16.self)
        let sortedBits = sortedX.view(dtype: .uint16).asArray(UInt16.self)
        for (inputOffset, outputOffset) in inverseValues.enumerated() {
            let sourceRow = inputOffset / topK
            for column in 0 ..< width {
                let expected = sourceBits[sourceRow * width + column]
                #expect(
                    sortedBits[outputOffset * width + column] == expected,
                    "\(name) repetition \(repetition): gathered BF16 mismatch")
            }
        }

        let restoredBits = restored.view(dtype: .uint16).asArray(UInt16.self)
        for inputOffset in 0 ..< routeCount {
            let sourceRow = inputOffset / topK
            for column in 0 ..< width {
                let expected = sourceBits[sourceRow * width + column]
                #expect(
                    restoredBits[inputOffset * width + column] == expected,
                    "\(name) repetition \(repetition): restored BF16 mismatch")
            }
        }
    }

    private func routerLike() -> [UInt32] {
        (0 ..< routeCount).map { offset in
            let row = offset / topK
            let lane = offset % topK
            let hot = [3, 17, 29, 47, 71, 109, 173, 241]
            if (row + lane * 3).isMultiple(of: 5) {
                return UInt32(hot[(row + lane) % hot.count])
            }
            return UInt32((row * 73 + lane * 29 + row / 7) % 256)
        }
    }

    private func boundaryKeys() -> [UInt32] {
        let boundaries: [UInt32] = [0, 1, 31, 32, 63, 64, 127, 128, 254, 255]
        return (0 ..< routeCount).map { boundaries[($0 * 7 + $0 / 13) % boundaries.count] }
    }

    private func randomKeys(seed: UInt32) -> [UInt32] {
        var state = seed
        return (0 ..< routeCount).map { _ in
            state = state &* 1_664_525 &+ 1_013_904_223
            return state >> 24
        }
    }
}
