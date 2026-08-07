import Dispatch
import Foundation
import MLX
import Testing

@Suite(.serialized)
struct RMSNormBarrierExperimentTests {
    @Test
    func rmsNormBarrierExperimentWhenEnabled() throws {
        guard let mode = ProcessInfo.processInfo.environment["MLXFAST_RMS_EXPERIMENT_MODE"] else {
            return
        }

        switch mode {
        case "oracle":
            try writeOracleOutputs()
        case "marker":
            verifyMarkerReachability()
        case "timing":
            runTimings()
        default:
            Issue.record("unsupported RMSNorm experiment mode: \(mode)")
        }
    }

    private func writeOracleOutputs() throws {
        let environment = ProcessInfo.processInfo.environment
        guard let outputDirectory = environment["MLXFAST_RMS_OUTPUT_DIR"] else {
            Issue.record("MLXFAST_RMS_OUTPUT_DIR is required")
            return
        }

        try FileManager.default.createDirectory(
            atPath: outputDirectory,
            withIntermediateDirectories: true
        )
        for (rows, axis) in [(1, 2048), (2, 2048), (511, 2048), (512, 2048), (513, 2048), (2, 1024)] {
            let output = rmsNorm(rows: rows, axis: axis)
            let data = output.asData(access: .copy).data
            let name = "rms_bf16_rows\(rows)_axis\(axis).bin"
            let url = URL(fileURLWithPath: outputDirectory).appendingPathComponent(name)
            try data.write(to: url, options: .atomic)
            print("RMS_ORACLE file=\(name) bytes=\(data.count)")
        }
    }

    private func verifyMarkerReachability() {
        for rows in [1, 512] {
            let output = rmsNorm(rows: rows, axis: 2048).asType(.float32).asArray(Float.self)
            let markedRows = (0..<rows).filter { output[$0 * 2048] == -123 }.count
            print("RMS_MARKER rows=\(rows) marked_rows=\(markedRows)")
            #expect(markedRows == rows)
        }
    }

    private func runTimings() {
        let label = ProcessInfo.processInfo.environment["MLXFAST_RMS_TIMING_LABEL"] ?? "unlabeled"
        benchmark(label: label, rows: 512, axis: 2048, batchSize: 128)
        benchmark(label: label, rows: 1, axis: 2048, batchSize: 2048)
    }

    private func benchmark(label: String, rows: Int, axis: Int, batchSize: Int) {
        let x = deterministicInput(rows: rows, axis: axis)
        let weight = deterministicWeight(axis: axis)
        eval(x, weight)
        Stream.gpu.synchronize()

        for _ in 0..<5 {
            evaluateBatch(x: x, weight: weight, batchSize: batchSize)
        }

        var samples = [Double]()
        samples.reserveCapacity(21)
        for _ in 0..<21 {
            let start = DispatchTime.now().uptimeNanoseconds
            evaluateBatch(x: x, weight: weight, batchSize: batchSize)
            let end = DispatchTime.now().uptimeNanoseconds
            samples.append(Double(end - start) / Double(batchSize))
        }

        let median = median(samples)
        let deviations = samples.map { abs($0 - median) }
        let mad = median(deviations)
        let formattedSamples = samples.map { String(format: "%.3f", $0) }.joined(separator: ",")
        print(
            "RMS_TIMING label=\(label) rows=\(rows) axis=\(axis) batch=\(batchSize) "
                + "median_ns=\(String(format: "%.3f", median)) "
                + "mad_ns=\(String(format: "%.3f", mad)) samples_ns=\(formattedSamples)"
        )
    }

    private func evaluateBatch(x: MLXArray, weight: MLXArray, batchSize: Int) {
        let outputs = (0..<batchSize).map { _ in
            MLXFast.rmsNorm(x, weight: weight, eps: 1e-6)
        }
        eval(outputs)
        Stream.gpu.synchronize()
    }

    private func rmsNorm(rows: Int, axis: Int) -> MLXArray {
        MLXFast.rmsNorm(
            deterministicInput(rows: rows, axis: axis),
            weight: deterministicWeight(axis: axis),
            eps: 1e-6
        )
    }

    private func deterministicInput(rows: Int, axis: Int) -> MLXArray {
        let values = (0..<(rows * axis)).map { index in
            Float((index * 37 + rows * 11 + axis) % 251 - 125) / 32
        }
        return MLXArray(values, [rows, axis]).asType(.bfloat16)
    }

    private func deterministicWeight(axis: Int) -> MLXArray {
        let values = (0..<axis).map { index in
            Float((index * 17 + axis) % 97 + 32) / 64
        }
        return MLXArray(values, [axis]).asType(.bfloat16)
    }

    private func median(_ values: [Double]) -> Double {
        let sorted = values.sorted()
        return sorted[sorted.count / 2]
    }
}
