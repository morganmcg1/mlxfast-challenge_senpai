import Foundation
import MLX
@testable import MLXFastModel
import Testing

@Suite(.serialized)
struct LagunaSelectorScratchLifetimeTests {
    private struct Buffers {
        let inputs: [MLXArray]
        let fusedWeight: MLXArray
        let packedScales: MLXArray
    }

    private func buffers(inputCount: Int) -> Buffers {
        let hidden = LagunaConstants.hiddenSize
        let intermediate = LagunaConstants.moeIntermediateSize
        let experts = LagunaConstants.numExperts
        let inputs = (0..<inputCount).map { layer in
            let values = (0..<hidden).map { index in
                Float(((index * 29 + layer * 17) % 193) - 96) / 256
            }
            return MLXArray(values, [1, 1, hidden]).asType(.bfloat16)
        }
        return Buffers(
            inputs: inputs,
            fusedWeight: MLXArray.full(
                [experts, 2 * intermediate, hidden / 8],
                values: MLXArray(UInt32(0x2222_2222)), dtype: .uint32),
            packedScales: MLXArray.full(
                [lagunaPackedRoutedGateUpScaleBytes],
                values: MLXArray(UInt8(0x38)), dtype: .uint8)
        )
    }

    private func orderedKeys(_ indices: [UInt32]) -> MLXArray {
        var keys = Array(repeating: UInt32.max, count: LagunaConstants.numExperts)
        for (rank, index) in indices.enumerated() {
            keys[Int(index)] = UInt32(rank)
        }
        return MLXArray(keys, [1, 1, LagunaConstants.numExperts])
    }

    private func candidate(
        _ fixture: Buffers,
        input: MLXArray,
        keys: MLXArray
    ) -> MLXArray {
        lagunaRoutedSwiGLUQMVPackedTop8(
            input,
            fusedWeight: fixture.fusedWeight,
            packedScales: fixture.packedScales,
            routerKeys: keys
        )
    }

    private func control(
        _ fixture: Buffers,
        input: MLXArray,
        keys: MLXArray
    ) -> MLXArray {
        lagunaRoutedSwiGLUQMVPackedTop8R1ControlForTesting(
            input,
            fusedWeight: fixture.fusedWeight,
            packedScales: fixture.packedScales,
            routerKeys: keys
        )
    }

    private func bits(_ array: MLXArray) -> [UInt16] {
        array.view(dtype: .uint16).asArray(UInt16.self)
    }

    private func median(_ values: [Double]) -> Double {
        let sorted = values.sorted()
        let middle = sorted.count / 2
        if sorted.count.isMultiple(of: 2) {
            return (sorted[middle - 1] + sorted[middle]) / 2
        }
        return sorted[middle]
    }

    @Test
    func exactControlCandidateDifferential() {
        guard ProcessInfo.processInfo.environment[
            "MLXFAST_RUN_SELECTOR_SCRATCH_CORRECTNESS"
        ] == "1" else { return }
        #expect(lagunaRoutedGateUpR1Enabled)

        let fixture = buffers(inputCount: 1)
        let cases: [(String, [UInt32])] = [
            ("contiguous", [0, 1, 2, 3, 4, 5, 6, 7]),
            ("lane-boundaries", [31, 32, 63, 64, 95, 96, 127, 255]),
            ("reverse-spread", [255, 224, 193, 162, 131, 100, 69, 38]),
            ("cross-simd", [17, 249, 66, 190, 99, 157, 128, 33]),
        ]

        for (label, indices) in cases {
            let keys = orderedKeys(indices)
            let controlOutput = control(fixture, input: fixture.inputs[0], keys: keys)
            let candidateOutput = candidate(fixture, input: fixture.inputs[0], keys: keys)
            eval(controlOutput, candidateOutput)
            let controlBits = bits(controlOutput)
            let candidateBits = bits(candidateOutput)
            #expect(controlBits == candidateBits, Comment(rawValue: label))

            var corrupted = candidateBits
            corrupted[corrupted.count / 2] ^= 1
            let detected = zip(controlBits, corrupted).reduce(into: 0) { count, pair in
                if pair.0 != pair.1 { count += 1 }
            }
            #expect(detected == 1, Comment(rawValue: "corruption-\(label)"))
            print("SELECTOR_SCRATCH_EXACT_\(label)=true")
            print("SELECTOR_SCRATCH_CORRUPTION_DETECTED_\(label)=\(detected)")
        }
    }

    @Test
    func isolatedFullBodyTiming() {
        guard ProcessInfo.processInfo.environment[
            "MLXFAST_RUN_SELECTOR_SCRATCH_BENCH"
        ] == "1" else { return }
        #expect(lagunaRoutedGateUpR1Enabled)

        let fixture = buffers(inputCount: 39)
        let keys = orderedKeys([17, 249, 66, 190, 99, 157, 128, 33])

        func outputs(candidate selected: Bool) -> [MLXArray] {
            fixture.inputs.map { input in
                if selected {
                    return candidate(fixture, input: input, keys: keys)
                }
                return control(fixture, input: input, keys: keys)
            }
        }

        func measure(candidate selected: Bool) -> Double {
            let batch = outputs(candidate: selected)
            let start = DispatchTime.now().uptimeNanoseconds
            eval(batch)
            return Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000_000
        }

        for selected in [false, true, true, false, true, false, false, true] {
            _ = measure(candidate: selected)
        }

        func contrasts(order: [Bool], cycles: Int) -> [Double] {
            (0..<cycles).map { _ in
                let elapsed = order.map { measure(candidate: $0) }
                if order == [false, true, true, false] {
                    return ((elapsed[0] + elapsed[3]) - (elapsed[1] + elapsed[2]))
                        * 500
                }
                return ((elapsed[1] + elapsed[2]) - (elapsed[0] + elapsed[3]))
                    * 500
            }
        }

        func noiseContrasts(order: [Bool], cycles: Int) -> [Double] {
            (0..<cycles).map { _ in
                let elapsed = order.map { _ in measure(candidate: false) }
                if order == [false, true, true, false] {
                    return ((elapsed[0] + elapsed[3]) - (elapsed[1] + elapsed[2]))
                        * 500
                }
                return ((elapsed[1] + elapsed[2]) - (elapsed[0] + elapsed[3]))
                    * 500
            }
        }

        let abba = contrasts(order: [false, true, true, false], cycles: 12)
        let baab = contrasts(order: [true, false, false, true], cycles: 12)
        let noiseABBA = noiseContrasts(order: [false, true, true, false], cycles: 8)
        let noiseBAAB = noiseContrasts(order: [true, false, false, true], cycles: 8)
        let abbaMedian = median(abba)
        let baabMedian = median(baab)
        let noiseFloor = median((noiseABBA + noiseBAAB).map(abs))
        let passed = abbaMedian >= 25 && baabMedian >= 25
            && min(abbaMedian, baabMedian) > 2 * noiseFloor

        print("SELECTOR_SCRATCH_ABBA_US_PER_TOKEN=\(abba)")
        print("SELECTOR_SCRATCH_BAAB_US_PER_TOKEN=\(baab)")
        print("SELECTOR_SCRATCH_AA_ABBA_US_PER_TOKEN=\(noiseABBA)")
        print("SELECTOR_SCRATCH_AA_BAAB_US_PER_TOKEN=\(noiseBAAB)")
        print("SELECTOR_SCRATCH_ABBA_MEDIAN_US_PER_TOKEN=\(abbaMedian)")
        print("SELECTOR_SCRATCH_BAAB_MEDIAN_US_PER_TOKEN=\(baabMedian)")
        print("SELECTOR_SCRATCH_AA_NOISE_US_PER_TOKEN=\(noiseFloor)")
        print("SELECTOR_SCRATCH_GATE1_PASS=\(passed)")
    }
}
