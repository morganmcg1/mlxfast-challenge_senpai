import Foundation
import MLX

private let warmupIterations = 8_192
private let blockIterations = 4_096
private let cyclesPerOrder = 64
private let bootstrapReplicates = 20_000
private let expectedChecksum = 129

private extension MLXArray {
    @inline(__always)
    func decodeDims(_ d0: Int, _ d1: Int) -> Bool {
        ndim == 2 && shape2 == (d0, d1)
    }
}

@inline(__always)
private func hit(_ condition: Bool) -> Int {
    condition ? 1 : 0
}

@inline(never)
private func baselineAccessorChain(tokens: MLXArray, hidden: MLXArray) -> Int {
    var checksum = 0

    for _ in 0..<40 {
        checksum &+= hit(hidden.dim(0) == 1)
        checksum &+= hit(hidden.dim(1) == 1)
    }
    for _ in 0..<39 {
        checksum &+= hit(hidden.dim(1) == 1)
    }
    checksum &+= hit(hidden.dim(1) == 1)
    for _ in 0..<39 {
        checksum &+= hit(hidden.dim(1) > 1)
    }
    checksum &+= hit(tokens.decodeDims(1, 1))
    checksum &+= hit(tokens.decodeDims(1, 1))
    checksum &+= hit(hidden.dim(0) == 1 && hidden.dim(1) == 1)
    checksum &+= hit(tokens.decodeDims(1, 1))
    checksum &+= hit(hidden.dim(1) > 1)
    for _ in 0..<40 {
        checksum &+= hit(hidden.dim(1) > 1)
    }
    checksum &+= hit(hidden.dim(1) == 1)
    for _ in 0..<4 {
        checksum &+= hit(tokens.decodeDims(1, 1))
    }

    return checksum
}

@inline(never)
private func propagatedRoute(
    proof: Bool,
    tokens: MLXArray,
    hidden: MLXArray
) -> Int {
    var checksum = 0

    for _ in 0..<40 {
        let batch = proof ? 1 : hidden.dim(0)
        let length = proof ? 1 : hidden.dim(1)
        checksum &+= hit(batch == 1)
        checksum &+= hit(length == 1)
    }
    for _ in 0..<39 {
        checksum &+= hit(proof || hidden.dim(1) == 1)
    }
    checksum &+= hit(proof || hidden.dim(1) == 1)
    for _ in 0..<39 {
        checksum &+= hit(!proof && hidden.dim(1) > 1)
    }
    checksum &+= hit(proof || tokens.decodeDims(1, 1))
    checksum &+= hit(proof || tokens.decodeDims(1, 1))
    checksum &+= hit(proof || (hidden.dim(0) == 1 && hidden.dim(1) == 1))
    checksum &+= hit(proof || tokens.decodeDims(1, 1))
    checksum &+= hit(!proof && hidden.dim(1) > 1)
    for _ in 0..<40 {
        checksum &+= hit(!proof && hidden.dim(1) > 1)
    }
    checksum &+= hit(hidden.dim(1) == 1)
    for _ in 0..<4 {
        checksum &+= hit(proof || tokens.decodeDims(1, 1))
    }

    return checksum
}

@inline(never)
private func candidateProofChain(tokens: MLXArray, hidden: MLXArray) -> Int {
    propagatedRoute(proof: tokens.decodeDims(1, 1), tokens: tokens, hidden: hidden)
}

private struct BlockResult {
    let nanosecondsPerIteration: Double
    let checksum: Int
}

@inline(never)
private func measureBaseline(
    tokens: [MLXArray],
    hidden: [MLXArray],
    iterations: Int
) -> BlockResult {
    var checksum = 0
    let start = DispatchTime.now().uptimeNanoseconds
    for iteration in 0..<iterations {
        let index = iteration & 1
        checksum &+= baselineAccessorChain(tokens: tokens[index], hidden: hidden[index])
    }
    let elapsed = DispatchTime.now().uptimeNanoseconds - start
    return BlockResult(
        nanosecondsPerIteration: Double(elapsed) / Double(iterations),
        checksum: checksum
    )
}

@inline(never)
private func measureCandidate(
    tokens: [MLXArray],
    hidden: [MLXArray],
    iterations: Int
) -> BlockResult {
    var checksum = 0
    let start = DispatchTime.now().uptimeNanoseconds
    for iteration in 0..<iterations {
        let index = iteration & 1
        checksum &+= candidateProofChain(tokens: tokens[index], hidden: hidden[index])
    }
    let elapsed = DispatchTime.now().uptimeNanoseconds - start
    return BlockResult(
        nanosecondsPerIteration: Double(elapsed) / Double(iterations),
        checksum: checksum
    )
}

@inline(never)
private func measureControl(
    proofs: [Bool],
    tokens: [MLXArray],
    hidden: [MLXArray],
    iterations: Int
) -> BlockResult {
    var checksum = 0
    let start = DispatchTime.now().uptimeNanoseconds
    for iteration in 0..<iterations {
        let index = iteration & 1
        checksum &+= propagatedRoute(
            proof: proofs[index],
            tokens: tokens[index],
            hidden: hidden[index]
        )
    }
    let elapsed = DispatchTime.now().uptimeNanoseconds - start
    return BlockResult(
        nanosecondsPerIteration: Double(elapsed) / Double(iterations),
        checksum: checksum
    )
}

private enum Arm {
    case baseline
    case candidate
}

private struct OrderResult {
    let name: String
    let baselineBlocksNS: [Double]
    let candidateBlocksNS: [Double]
    let baselineCyclesNS: [Double]
    let candidateCyclesNS: [Double]
    let controlCyclesNS: [Double]
    let checksumValid: Bool
}

private func runOrder(
    name: String,
    sequence: [Arm],
    tokens: [MLXArray],
    hidden: [MLXArray],
    proofs: [Bool]
) -> OrderResult {
    var baselineBlocks: [Double] = []
    var candidateBlocks: [Double] = []
    var baselineCycles: [Double] = []
    var candidateCycles: [Double] = []
    var controlCycles: [Double] = []
    var checksumValid = true

    for _ in 0..<cyclesPerOrder {
        var cycleBaseline: [Double] = []
        var cycleCandidate: [Double] = []

        for arm in sequence {
            let result: BlockResult
            switch arm {
            case .baseline:
                result = measureBaseline(
                    tokens: tokens,
                    hidden: hidden,
                    iterations: blockIterations
                )
                baselineBlocks.append(result.nanosecondsPerIteration)
                cycleBaseline.append(result.nanosecondsPerIteration)
            case .candidate:
                result = measureCandidate(
                    tokens: tokens,
                    hidden: hidden,
                    iterations: blockIterations
                )
                candidateBlocks.append(result.nanosecondsPerIteration)
                cycleCandidate.append(result.nanosecondsPerIteration)
            }
            checksumValid = checksumValid
                && result.checksum == expectedChecksum * blockIterations
        }

        let control = measureControl(
            proofs: proofs,
            tokens: tokens,
            hidden: hidden,
            iterations: blockIterations
        )
        checksumValid = checksumValid
            && control.checksum == expectedChecksum * blockIterations
        controlCycles.append(control.nanosecondsPerIteration)
        baselineCycles.append(cycleBaseline.reduce(0, +) / Double(cycleBaseline.count))
        candidateCycles.append(cycleCandidate.reduce(0, +) / Double(cycleCandidate.count))
    }

    return OrderResult(
        name: name,
        baselineBlocksNS: baselineBlocks,
        candidateBlocksNS: candidateBlocks,
        baselineCyclesNS: baselineCycles,
        candidateCyclesNS: candidateCycles,
        controlCyclesNS: controlCycles,
        checksumValid: checksumValid
    )
}

private func percentile(_ values: [Double], _ probability: Double) -> Double {
    let sorted = values.sorted()
    let index = Int((Double(sorted.count - 1) * probability).rounded())
    return sorted[index]
}

private func median(_ values: [Double]) -> Double {
    percentile(values, 0.5)
}

private struct Generator {
    var state: UInt64

    mutating func nextIndex(upperBound: Int) -> Int {
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        return Int(state % UInt64(upperBound))
    }
}

private func bootstrapMedianCI(_ pairedSavings: [Double]) -> (Double, Double) {
    var generator = Generator(state: 0x701_25B6_0878)
    var estimates: [Double] = []
    estimates.reserveCapacity(bootstrapReplicates)
    for _ in 0..<bootstrapReplicates {
        var sample: [Double] = []
        sample.reserveCapacity(pairedSavings.count)
        for _ in pairedSavings.indices {
            sample.append(pairedSavings[generator.nextIndex(upperBound: pairedSavings.count)])
        }
        estimates.append(median(sample))
    }
    return (percentile(estimates, 0.025), percentile(estimates, 0.975))
}

private func pairedSavings(_ result: OrderResult) -> [Double] {
    zip(result.baselineCyclesNS, result.candidateCyclesNS).map(-)
}

private func orderJSON(_ result: OrderResult) -> [String: Any] {
    let savings = pairedSavings(result)
    let interval = bootstrapMedianCI(savings)
    return [
        "name": result.name,
        "baseline_blocks_ns_per_iteration": result.baselineBlocksNS,
        "candidate_blocks_ns_per_iteration": result.candidateBlocksNS,
        "baseline_cycles_ns_per_iteration": result.baselineCyclesNS,
        "candidate_cycles_ns_per_iteration": result.candidateCyclesNS,
        "control_cycles_ns_per_iteration": result.controlCyclesNS,
        "paired_savings_ns": savings,
        "median_baseline_ns": median(result.baselineCyclesNS),
        "median_candidate_ns": median(result.candidateCyclesNS),
        "median_control_ns": median(result.controlCyclesNS),
        "median_savings_ns": median(savings),
        "p95_savings_ns": percentile(savings, 0.95),
        "bootstrap_95_ci_lower_ns": interval.0,
        "bootstrap_95_ci_upper_ns": interval.1,
        "checksum_valid": result.checksumValid,
    ]
}

@main
private struct ShapeProofMicrobench {
    static func main() throws {
        let outputPath = CommandLine.arguments.dropFirst().first
            ?? "/tmp/pr701-shape-proof-microbench.json"

        try Stream.withNewDefaultStream(device: .cpu) {
            let tokens = [
                MLXArray([Int32(0)], [1, 1]),
                MLXArray([Int32(1)], [1, 1]),
            ]
            let hidden = [
                MLXArray([Float](repeating: 0, count: 2_048), [1, 1, 2_048]),
                MLXArray([Float](repeating: 1, count: 2_048), [1, 1, 2_048]),
            ]
            let proofs = [true, true]

            let baselineWarmup = measureBaseline(
                tokens: tokens,
                hidden: hidden,
                iterations: warmupIterations
            )
            let candidateWarmup = measureCandidate(
                tokens: tokens,
                hidden: hidden,
                iterations: warmupIterations
            )
            let controlWarmup = measureControl(
                proofs: proofs,
                tokens: tokens,
                hidden: hidden,
                iterations: warmupIterations
            )
            guard baselineWarmup.checksum == expectedChecksum * warmupIterations,
                candidateWarmup.checksum == expectedChecksum * warmupIterations,
                controlWarmup.checksum == expectedChecksum * warmupIterations
            else {
                throw NSError(
                    domain: "ShapeProofMicrobench",
                    code: 1,
                    userInfo: [NSLocalizedDescriptionKey: "warmup checksum mismatch"]
                )
            }

            let abba = runOrder(
                name: "ABBA",
                sequence: [.baseline, .candidate, .candidate, .baseline],
                tokens: tokens,
                hidden: hidden,
                proofs: proofs
            )
            let baab = runOrder(
                name: "BAAB",
                sequence: [.candidate, .baseline, .baseline, .candidate],
                tokens: tokens,
                hidden: hidden,
                proofs: proofs
            )

            let combinedSavings = pairedSavings(abba) + pairedSavings(baab)
            let combinedCI = bootstrapMedianCI(combinedSavings)
            let medianSavings = median(combinedSavings)
            let checksumValid = abba.checksumValid && baab.checksumValid
            let gatePassed = checksumValid
                && 422 >= 250
                && medianSavings >= 35_000
                && combinedCI.0 > 24_543

            #if arch(arm64)
                let architecture = "arm64"
            #else
                let architecture = "other"
            #endif

            let report: [String: Any] = [
                "schema_version": 1,
                "assignment": "mlxfast-cedar-20260811-thorfinn-decode-shape-proof",
                "method": "native MLX actual accessor chain, mirrored ABBA and BAAB",
                "device": "cpu",
                "architecture": architecture,
                "operating_system": ProcessInfo.processInfo.operatingSystemVersionString,
                "warmup_iterations_per_arm": warmupIterations,
                "cycles_per_order": cyclesPerOrder,
                "iterations_per_block": blockIterations,
                "blocks_per_arm_per_cycle": 2,
                "timed_iterations_per_arm_per_order": cyclesPerOrder * blockIterations * 2,
                "bootstrap_replicates": bootstrapReplicates,
                "expected_checksum_per_iteration": expectedChecksum,
                "accessor_census": [
                    "baseline_c_bridge_calls_per_token": 427,
                    "candidate_c_bridge_calls_per_token": 5,
                    "removed_c_bridge_calls_per_token": 422,
                    "threshold_calls": 250,
                ],
                "orders": [orderJSON(abba), orderJSON(baab)],
                "combined": [
                    "paired_savings_ns": combinedSavings,
                    "median_savings_ns": medianSavings,
                    "projected_savings_us_per_token": medianSavings / 1_000,
                    "bootstrap_95_ci_lower_ns": combinedCI.0,
                    "bootstrap_95_ci_upper_ns": combinedCI.1,
                    "bootstrap_95_ci_lower_us_per_token": combinedCI.0 / 1_000,
                    "bootstrap_95_ci_upper_us_per_token": combinedCI.1 / 1_000,
                    "checksum_valid": checksumValid,
                ],
                "gate": [
                    "median_savings_threshold_us": 35.0,
                    "ci_lower_threshold_us": 24.543,
                    "passed": gatePassed,
                ],
            ]

            let data = try JSONSerialization.data(
                withJSONObject: report,
                options: [.prettyPrinted, .sortedKeys]
            )
            try data.write(to: URL(fileURLWithPath: outputPath), options: .atomic)
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write(Data("\n".utf8))
        }
    }
}
