import Foundation
import MLX
import MLXLMCommon
import MLXNN
@testable import MLXFastModel
import Testing

@Suite(.serialized)
struct SharedGateUpFusionDiagnostics {
    private struct LoadedExperts {
        let runtime: LagunaRuntimeModel
        let experts: [LagunaRuntimeMLP]
    }

    private struct PairedStats {
        let geometricMean: Double
        let lower95: Double
        let separateMean: Double
        let fusedMean: Double
    }

    @Test
    func sharedGateUpVirtualHalfSplitKTrace() throws {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_SHARED_GATE_UP_DIAGNOSTICS"] == "1" else {
            return
        }
        let candidate = ProcessInfo.processInfo.environment["DARKBLOOM_FUSED_SHARED_GATE_UP"] != "0"
        let loaded = try loadExperts(prepareFused: candidate)
        let prefill = deterministicInput(rows: 512, salt: 19)

        stderr("GATE0_PREFILL_BEGIN")
        if candidate {
            eval(loaded.experts.map { $0(prefill) })
        } else {
            var outputs: [MLXArray] = []
            outputs.reserveCapacity(2 * loaded.experts.count)
            for expert in loaded.experts {
                outputs.append(expert.gateProj(prefill))
                outputs.append(expert.upProj(prefill))
            }
            eval(outputs)
        }
        stderr("GATE0_PREFILL_END")

        let decode = deterministicInput(rows: 1, salt: 23)
        stderr("GATE0_DECODE_BEGIN")
        eval(loaded.experts.map { $0(decode) })
        stderr("GATE0_DECODE_END")
        print("GATE0_REPORT candidate=\(candidate ? 1 : 0) experts=\(loaded.experts.count)")
        _ = loaded.runtime
    }

    @Test
    func sharedGateUpVirtualHalfExactnessAndTiming() throws {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_SHARED_GATE_UP_DIAGNOSTICS"] == "1" else {
            return
        }
        let loaded = try loadExperts(prepareFused: true)
        let rowCounts = [2, 31, 32, 33, 127, 128, 511, 512]
        var corruptionChecked = false

        for rows in rowCounts {
            let x = deterministicInput(rows: rows, salt: rows + 29)
            for (layer, expert) in loaded.experts.enumerated() {
                let separateGate = expert.gateProj(x)
                let separateUp = expert.upProj(x)
                let fused = try fusedGateUp(expert, x: x)
                let fusedGate = fused[.ellipsis, 0 ..< LagunaConstants.sharedExpertIntermediateSize]
                let fusedUp = fused[.ellipsis, LagunaConstants.sharedExpertIntermediateSize...]
                let separateActivation = compiledSiluProduct(separateGate, separateUp)
                let fusedActivation = compiledSiluProduct(fusedGate, fusedUp)
                let separateDown = expert.downProj(separateActivation)
                let fusedDown = expert.downProj(fusedActivation)
                let candidateDown = expert(x)
                eval([
                    separateGate, separateUp, fusedGate, fusedUp,
                    separateActivation, fusedActivation,
                    separateDown, fusedDown, candidateDown,
                ])

                #expect(
                    sameBits(separateGate, fusedGate),
                    Comment(rawValue: "gate layer=\(layer + 1) rows=\(rows)")
                )
                #expect(
                    sameBits(separateUp, fusedUp),
                    Comment(rawValue: "up layer=\(layer + 1) rows=\(rows)")
                )
                #expect(
                    sameBits(separateActivation, fusedActivation),
                    Comment(rawValue: "activation layer=\(layer + 1) rows=\(rows)")
                )
                #expect(
                    sameBits(separateDown, fusedDown),
                    Comment(rawValue: "down layer=\(layer + 1) rows=\(rows)")
                )
                #expect(
                    sameBits(fusedDown, candidateDown),
                    Comment(rawValue: "candidate layer=\(layer + 1) rows=\(rows)")
                )

                if !corruptionChecked {
                    var corrupted = separateGate.view(dtype: .uint16).asArray(UInt16.self)
                    corrupted[0] ^= 1
                    let corruptedGate = MLXArray(corrupted, separateGate.shape).view(dtype: .bfloat16)
                    #expect(!sameBits(separateGate, corruptedGate))
                    corruptionChecked = true
                }
            }
            print("GATE1_ROWS_EXACT rows=\(rows) experts=\(loaded.experts.count)")
            Memory.clearCache()
        }

        let fusedBytes = loaded.experts.reduce(0) { partial, expert in
            partial + (expert._fusedGateUpWeight?.nbytes ?? 0)
                + (expert._fusedGateUpScales?.nbytes ?? 0)
        }
        #expect(corruptionChecked)
        #expect(fusedBytes <= 64 * 1024 * 1024)
        print(
            "GATE1_REPORT experts=\(loaded.experts.count) rows=\(rowCounts.count) "
                + "corruption=detected fused_bytes=\(fusedBytes) active_bytes=\(Memory.activeMemory)"
        )

        let timingInput = deterministicInput(rows: 512, salt: 41)
        for _ in 0..<3 {
            _ = measureSeparate(loaded.experts, x: timingInput)
            _ = try measureFused(loaded.experts, x: timingInput)
            _ = try measureFused(loaded.experts, x: timingInput)
            _ = measureSeparate(loaded.experts, x: timingInput)
        }

        var abLogs: [Double] = []
        var abSeparate: [Double] = []
        var abFused: [Double] = []
        var baLogs: [Double] = []
        var baSeparate: [Double] = []
        var baFused: [Double] = []
        for _ in 0..<30 {
            let separate = measureSeparate(loaded.experts, x: timingInput)
            let fused = try measureFused(loaded.experts, x: timingInput)
            abSeparate.append(separate)
            abFused.append(fused)
            abLogs.append(log(separate / fused))
        }
        for _ in 0..<30 {
            let fused = try measureFused(loaded.experts, x: timingInput)
            let separate = measureSeparate(loaded.experts, x: timingInput)
            baSeparate.append(separate)
            baFused.append(fused)
            baLogs.append(log(separate / fused))
        }

        let ab = summarize(logRatios: abLogs, separate: abSeparate, fused: abFused)
        let ba = summarize(logRatios: baLogs, separate: baSeparate, fused: baFused)
        print(
            String(
                format:
                    "GATE2_REPORT pairs_ab=30 pairs_ba=30 ab_geomean=%.6f ab_lower95=%.6f "
                    + "ab_separate_s=%.9f ab_fused_s=%.9f ba_geomean=%.6f ba_lower95=%.6f "
                    + "ba_separate_s=%.9f ba_fused_s=%.9f",
                ab.geometricMean, ab.lower95, ab.separateMean, ab.fusedMean,
                ba.geometricMean, ba.lower95, ba.separateMean, ba.fusedMean
            )
        )
        #expect(ab.geometricMean >= 1.010)
        #expect(ba.geometricMean >= 1.010)
        #expect(ab.lower95 > 1.0)
        #expect(ba.lower95 > 1.0)
        _ = loaded.runtime
    }

    private func loadExperts(prepareFused: Bool) throws -> LoadedExperts {
        let environment = ProcessInfo.processInfo.environment
        let weightsPath = try #require(environment["MLXFAST_LAGUNA_EQUIVALENCE_WEIGHTS_PATH"])
        let config = try LagunaConfig.load(from: weightsPath)
        let loader = try LagunaWeightLoader(weightsPath: weightsPath)
        try loader.denseStore.validateReadableByteRanges()
        try loader.validateRequiredMetadata(config: config)
        let weights = try loadRuntimeWeightArrays(denseStore: loader.denseStore)
        let runtime = LagunaRuntimeModel(config)
        try runtime.update(
            parameters: ModuleParameters.unflattened(runtime.sanitize(weights: weights)),
            verify: [.all]
        )
        eval(runtime)

        let experts = runtime.model.layers.compactMap { layer in
            (layer.mlp as? LagunaRuntimeSparseMoEBlock)?.sharedExpert
        }
        #expect(experts.count == 39)
        if prepareFused {
            var arrays: [MLXArray] = []
            for expert in experts {
                arrays.append(contentsOf: expert.prepareFusedSharedGateUp())
            }
            eval(arrays)
            #expect(experts.allSatisfy { $0._fusedGateUpSplit == 512 })
        }
        return LoadedExperts(runtime: runtime, experts: experts)
    }

    private func deterministicInput(rows: Int, salt: Int) -> MLXArray {
        let count = rows * LagunaConstants.hiddenSize
        let values = (0..<count).map { index in
            Float((index * 17 + salt) % 257 - 128) / 128
        }
        return MLXArray(values, [1, rows, LagunaConstants.hiddenSize]).asType(.bfloat16)
    }

    private func fusedGateUp(_ expert: LagunaRuntimeMLP, x: MLXArray) throws -> MLXArray {
        let weight = try #require(expert._fusedGateUpWeight)
        let scales = try #require(expert._fusedGateUpScales)
        return MLX.quantizedMM(
            x,
            weight,
            scales: scales,
            biases: nil,
            transpose: true,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4
        )
    }

    private func sameBits(_ lhs: MLXArray, _ rhs: MLXArray) -> Bool {
        lhs.shape == rhs.shape
            && lhs.view(dtype: .uint16).asArray(UInt16.self)
                == rhs.view(dtype: .uint16).asArray(UInt16.self)
    }

    private func measureSeparate(_ experts: [LagunaRuntimeMLP], x: MLXArray) -> Double {
        let start = DispatchTime.now().uptimeNanoseconds
        var outputs: [MLXArray] = []
        outputs.reserveCapacity(2 * experts.count)
        for expert in experts {
            outputs.append(expert.gateProj(x))
            outputs.append(expert.upProj(x))
        }
        eval(outputs)
        return Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000_000_000
    }

    private func measureFused(_ experts: [LagunaRuntimeMLP], x: MLXArray) throws -> Double {
        let start = DispatchTime.now().uptimeNanoseconds
        var outputs: [MLXArray] = []
        outputs.reserveCapacity(experts.count)
        for expert in experts {
            outputs.append(try fusedGateUp(expert, x: x))
        }
        eval(outputs)
        return Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000_000_000
    }

    private func summarize(
        logRatios: [Double], separate: [Double], fused: [Double]
    ) -> PairedStats {
        let count = Double(logRatios.count)
        let meanLog = logRatios.reduce(0, +) / count
        let variance = logRatios.reduce(0) { $0 + pow($1 - meanLog, 2) } / (count - 1)
        let standardError = sqrt(variance / count)
        return PairedStats(
            geometricMean: exp(meanLog),
            lower95: exp(meanLog - 1.699 * standardError),
            separateMean: separate.reduce(0, +) / count,
            fusedMean: fused.reduce(0, +) / count
        )
    }

    private func stderr(_ line: String) {
        FileHandle.standardError.write(Data("\(line)\n".utf8))
    }
}
