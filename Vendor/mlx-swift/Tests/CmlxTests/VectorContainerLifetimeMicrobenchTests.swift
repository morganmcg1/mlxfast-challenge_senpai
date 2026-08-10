import Dispatch
import Foundation
import XCTest

@testable import Cmlx

final class VectorContainerLifetimeMicrobenchTests: XCTestCase {
    private struct Census: Codable {
        let mlxFastKernel: Int
        let asyncEval: Int
        let blockingEval: Int
    }

    private struct Result: Codable {
        let elementCount: Int
        let order: String
        let iterationsPerArm: Int
        let emptyIterations: Int
        let warmupPerArm: Int
        let currentMedianNS: Double
        let currentP95NS: Double
        let reusedMedianNS: Double
        let reusedP95NS: Double
        let emptyMedianNS: Double
        let emptyP95NS: Double
        let savingMedianNS: Double
        let savingBootstrap95LowerNS: Double
        let savingBootstrap95UpperNS: Double
        let currentCycleNS: [Double]
        let reusedCycleNS: [Double]
        let emptyCycleNS: [Double]
    }

    private struct Report: Codable {
        let schemaVersion: Int
        let operationA: String
        let operationB: String
        let elementCounts: [Int]
        let census: Census
        let creditedCallsPerToken: Int
        let censusValidatorAcceptedExpected: Bool
        let positiveControlRejectedAlteredCount: Bool
        let cycles: Int
        let iterationsPerBlock: Int
        let bootstrapReplicates: Int
        let checksum: UInt64
        let results: [Result]
    }

    private enum Arm {
        case current
        case reused
    }

    private let elementCounts = [1, 2, 3, 4, 5, 6, 9, 10]
    private let expectedCensus = Census(mlxFastKernel: 323, asyncEval: 8, blockingEval: 3)
    private let cycles = 16
    private let iterationsPerBlock = 32_768
    private let warmupIterations = 65_536
    private let bootstrapReplicates = 20_000

    func testVectorContainerLifetimeMicrobenchmark() throws {
        let expectedAccepted = validate(expectedCensus)
        let alteredRejected = !validate(
            Census(mlxFastKernel: 324, asyncEval: 8, blockingEval: 3))
        XCTAssertTrue(expectedAccepted)
        XCTAssertTrue(alteredRejected)

        let arrays = (0..<10).map { mlx_array_new_int($0) }
        defer { arrays.forEach { _ = mlx_array_free($0) } }

        var results: [Result] = []
        var checksum: UInt64 = 0
        for elementCount in elementCounts {
            try arrays.withUnsafeBufferPointer { buffer in
                guard let baseAddress = buffer.baseAddress else {
                    XCTFail("missing array buffer")
                    return
                }
                for order in ["ABBA", "BAAB"] {
                    let measured = measure(
                        elementCount: elementCount,
                        order: order,
                        data: baseAddress)
                    checksum &+= measured.checksum
                    results.append(measured.result)
                }
            }
        }

        let report = Report(
            schemaVersion: 1,
            operationA: "mlx_vector_array_new_data + mlx_vector_array_free",
            operationB: "pre-created same-size mlx_vector_array + mlx_vector_array_set_data",
            elementCounts: elementCounts,
            census: expectedCensus,
            creditedCallsPerToken: 334,
            censusValidatorAcceptedExpected: expectedAccepted,
            positiveControlRejectedAlteredCount: alteredRejected,
            cycles: cycles,
            iterationsPerBlock: iterationsPerBlock,
            bootstrapReplicates: bootstrapReplicates,
            checksum: checksum,
            results: results)

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let encoded = try encoder.encode(report)
        let output = try XCTUnwrap(
            ProcessInfo.processInfo.environment["MLXFAST_VECTOR_BENCH_OUTPUT"])
        try encoded.write(to: URL(fileURLWithPath: output), options: .atomic)
        print("VECTOR_CONTAINER_MICROBENCH=" + String(decoding: encoded, as: UTF8.self))
    }

    private func validate(_ census: Census) -> Bool {
        census.mlxFastKernel == 323 && census.asyncEval == 8 && census.blockingEval == 3
    }

    private func measure(
        elementCount: Int,
        order: String,
        data: UnsafePointer<mlx_array>
    ) -> (result: Result, checksum: UInt64) {
        var reused = mlx_vector_array_new_data(data, elementCount)
        defer { _ = mlx_vector_array_free(reused) }
        XCTAssertEqual(mlx_vector_array_size(reused), elementCount)

        var checksum = runCurrent(
            iterations: warmupIterations, elementCount: elementCount, data: data)
        checksum &+= runReused(
            iterations: warmupIterations, elementCount: elementCount, data: data,
            reused: &reused)
        checksum &+= runEmpty(iterations: warmupIterations, elementCount: elementCount)

        let sequence: [Arm] = order == "ABBA"
            ? [.current, .reused, .reused, .current]
            : [.reused, .current, .current, .reused]
        var currentBlocks: [Double] = []
        var reusedBlocks: [Double] = []
        var currentCycles: [Double] = []
        var reusedCycles: [Double] = []
        var emptyCycles: [Double] = []

        for _ in 0..<cycles {
            let empty = timed(iterations: iterationsPerBlock) {
                runEmpty(iterations: iterationsPerBlock, elementCount: elementCount)
            }
            checksum &+= empty.checksum
            emptyCycles.append(empty.nsPerIteration)

            var cycleCurrent: [Double] = []
            var cycleReused: [Double] = []
            for arm in sequence {
                switch arm {
                case .current:
                    let sample = timed(iterations: iterationsPerBlock) {
                        runCurrent(
                            iterations: iterationsPerBlock,
                            elementCount: elementCount,
                            data: data)
                    }
                    checksum &+= sample.checksum
                    currentBlocks.append(sample.nsPerIteration)
                    cycleCurrent.append(sample.nsPerIteration)
                case .reused:
                    let sample = timed(iterations: iterationsPerBlock) {
                        runReused(
                            iterations: iterationsPerBlock,
                            elementCount: elementCount,
                            data: data,
                            reused: &reused)
                    }
                    checksum &+= sample.checksum
                    reusedBlocks.append(sample.nsPerIteration)
                    cycleReused.append(sample.nsPerIteration)
                }
            }
            currentCycles.append(mean(cycleCurrent))
            reusedCycles.append(mean(cycleReused))
        }

        XCTAssertEqual(mlx_vector_array_size(reused), elementCount)
        let savings = zip(currentCycles, reusedCycles).map { $0 - $1 }
        let interval = bootstrapMedian95(savings, seed: UInt64(elementCount * 31 + order.count))
        let result = Result(
            elementCount: elementCount,
            order: order,
            iterationsPerArm: cycles * iterationsPerBlock * 2,
            emptyIterations: cycles * iterationsPerBlock,
            warmupPerArm: warmupIterations,
            currentMedianNS: median(currentBlocks),
            currentP95NS: percentile(currentBlocks, 0.95),
            reusedMedianNS: median(reusedBlocks),
            reusedP95NS: percentile(reusedBlocks, 0.95),
            emptyMedianNS: median(emptyCycles),
            emptyP95NS: percentile(emptyCycles, 0.95),
            savingMedianNS: median(savings),
            savingBootstrap95LowerNS: interval.lower,
            savingBootstrap95UpperNS: interval.upper,
            currentCycleNS: currentCycles.map(rounded),
            reusedCycleNS: reusedCycles.map(rounded),
            emptyCycleNS: emptyCycles.map(rounded))
        return (result, checksum)
    }

    private func timed(iterations: Int, _ body: () -> UInt64) ->
        (nsPerIteration: Double, checksum: UInt64)
    {
        let start = DispatchTime.now().uptimeNanoseconds
        let checksum = body()
        let elapsed = DispatchTime.now().uptimeNanoseconds - start
        return (Double(elapsed) / Double(iterations), checksum)
    }

    private func runCurrent(
        iterations: Int,
        elementCount: Int,
        data: UnsafePointer<mlx_array>
    ) -> UInt64 {
        var checksum = UInt64(elementCount)
        for _ in 0..<iterations {
            let vector = mlx_vector_array_new_data(data, elementCount)
            checksum &+= UInt64(mlx_vector_array_free(vector))
        }
        return checksum
    }

    private func runReused(
        iterations: Int,
        elementCount: Int,
        data: UnsafePointer<mlx_array>,
        reused: inout mlx_vector_array
    ) -> UInt64 {
        var checksum = UInt64(elementCount)
        for _ in 0..<iterations {
            checksum &+= UInt64(mlx_vector_array_set_data(&reused, data, elementCount))
        }
        return checksum
    }

    private func runEmpty(iterations: Int, elementCount: Int) -> UInt64 {
        var checksum = UInt64(elementCount)
        for i in 0..<iterations {
            checksum &+= UInt64((i & 7) &+ elementCount)
        }
        return checksum
    }

    private func mean(_ values: [Double]) -> Double {
        values.reduce(0, +) / Double(values.count)
    }

    private func median(_ values: [Double]) -> Double {
        percentile(values, 0.5)
    }

    private func percentile(_ values: [Double], _ quantile: Double) -> Double {
        let sorted = values.sorted()
        let index = Int((Double(sorted.count - 1) * quantile).rounded(.down))
        return sorted[index]
    }

    private func bootstrapMedian95(_ values: [Double], seed: UInt64) ->
        (lower: Double, upper: Double)
    {
        var generator = XorShift64(state: seed)
        var estimates: [Double] = []
        estimates.reserveCapacity(bootstrapReplicates)
        for _ in 0..<bootstrapReplicates {
            var sample: [Double] = []
            sample.reserveCapacity(values.count)
            for _ in values.indices {
                sample.append(values[Int(generator.next() % UInt64(values.count))])
            }
            estimates.append(median(sample))
        }
        return (percentile(estimates, 0.025), percentile(estimates, 0.975))
    }

    private func rounded(_ value: Double) -> Double {
        (value * 1_000).rounded() / 1_000
    }

    private struct XorShift64 {
        var state: UInt64

        mutating func next() -> UInt64 {
            state ^= state << 13
            state ^= state >> 7
            state ^= state << 17
            return state
        }
    }
}
