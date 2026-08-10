import Foundation
import MLX
import MLXFast
import MLXLMCommon
import Testing
@testable import MLXFastModel

private enum PrefillQKShape: String, CaseIterable {
    case sliding
    case full

    var queryHeads: Int {
        switch self {
        case .sliding: 64
        case .full: 48
        }
    }

    var angleWidth: Int {
        switch self {
        case .sliding: 128
        case .full: 64
        }
    }
}

private enum PrefillQKArm: String {
    case h1
    case h4
    case tokenStrip4
}

private struct PrefillQKFixture {
    let shape: PrefillQKShape
    let length: Int
    let rawQueries: MLXArray
    let rawKeys: MLXArray
    let queryWeight: MLXArray
    let keyWeight: MLXArray
    let angles: MLXArray
    let offsets: MLXArray

    init(shape: PrefillQKShape, length: Int, offset: Int) {
        self.shape = shape
        self.length = length
        rawQueries = makeBF16Array(
            count: length * shape.queryHeads * 128,
            shape: [1, length, shape.queryHeads * 128],
            seed: UInt32(0x51A7_0000 + shape.queryHeads + length)
        )
        rawKeys = makeBF16Array(
            count: length * 8 * 128,
            shape: [1, length, 8 * 128],
            seed: UInt32(0xB4D0_0000 + shape.queryHeads + length)
        )
        queryWeight = makeBF16Array(
            count: 128,
            shape: [128],
            seed: UInt32(0x1357_0000 + shape.queryHeads)
        )
        keyWeight = makeBF16Array(
            count: 128,
            shape: [128],
            seed: UInt32(0x2468_0000 + shape.queryHeads)
        )
        angles = makeAngles(rows: offset + length, width: shape.angleWidth)
        offsets = MLXArray([Int32(offset)])
    }
}

@Test
func prefillQKTokenStripDirectExactnessWhenResearchTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_PREFILL_QK_RESEARCH"] == "1" else {
        return
    }

    let lengths = [1, 2, 3, 4, 5, 511, 512, 513]
    var comparedElements = 0
    for shape in PrefillQKShape.allCases {
        for length in lengths {
            let offset = length.isMultiple(of: 2) ? 0 : 17
            let fixture = PrefillQKFixture(shape: shape, length: length, offset: offset)
            let h1 = launchPrefillQK(fixture, arm: .h1)
            let h4 = launchPrefillQK(fixture, arm: .h4)
            let tokenStrip4 = launchPrefillQK(fixture, arm: .tokenStrip4)
            eval(h1[0], h1[1], h4[0], h4[1], tokenStrip4[0], tokenStrip4[1])

            let h4Mismatches = bitMismatchCount(h4[0], h1[0])
                + bitMismatchCount(h4[1], h1[1])
            let tokenStrip4Mismatches = bitMismatchCount(tokenStrip4[0], h1[0])
                + bitMismatchCount(tokenStrip4[1], h1[1])
            let h4MaxAbsDiff = max(
                maxAbsoluteDifference(h4[0], h1[0]),
                maxAbsoluteDifference(h4[1], h1[1])
            )
            let tokenStrip4MaxAbsDiff = max(
                maxAbsoluteDifference(tokenStrip4[0], h1[0]),
                maxAbsoluteDifference(tokenStrip4[1], h1[1])
            )
            let elements = (shape.queryHeads + 8) * length * 128
            comparedElements += 2 * elements
            print(
                "prefill_qk_exact shape=\(shape.rawValue) length=\(length) "
                    + "offset=\(offset) elements_per_arm=\(elements) "
                    + "h4_mismatches=\(h4Mismatches) h4_max_abs_diff=\(h4MaxAbsDiff) "
                    + "token_strip4_mismatches=\(tokenStrip4Mismatches) "
                    + "token_strip4_max_abs_diff=\(tokenStrip4MaxAbsDiff)"
            )
            #expect(h4Mismatches == 0, "H4 differed bitwise from H1 for \(shape) L=\(length)")
            #expect(h4MaxAbsDiff == 0, "H4 differed numerically from H1 for \(shape) L=\(length)")
            #expect(
                tokenStrip4Mismatches == 0,
                "token-strip-4 differed bitwise from H1 for \(shape) L=\(length)"
            )
            #expect(
                tokenStrip4MaxAbsDiff == 0,
                "token-strip-4 differed numerically from H1 for \(shape) L=\(length)"
            )
        }
    }
    print("prefill_qk_exact_total compared_elements=\(comparedElements) mismatches=0")
}

@Test
func prefillQKTokenStripIsolatedTimingWhenResearchTestsAreEnabled() {
    let environment = ProcessInfo.processInfo.environment
    guard let shapeName = environment["MLXFAST_PREFILL_QK_TIMING_SHAPE"],
        let armName = environment["MLXFAST_PREFILL_QK_TIMING_ARM"]
    else {
        return
    }
    guard let shape = PrefillQKShape(rawValue: shapeName),
        let arm = PrefillQKArm(rawValue: armName)
    else {
        #expect(Bool(false), "invalid isolated timing shape or arm")
        return
    }

    let fixture = PrefillQKFixture(shape: shape, length: 512, offset: 17)
    let warmupCount = 25
    let sampleCount = 121
    for _ in 0..<warmupCount {
        let outputs = launchPrefillQK(fixture, arm: arm)
        eval(outputs[0], outputs[1])
    }

    var samples = [UInt64]()
    samples.reserveCapacity(sampleCount)
    for _ in 0..<sampleCount {
        let outputs = launchPrefillQK(fixture, arm: arm)
        let start = DispatchTime.now().uptimeNanoseconds
        eval(outputs[0], outputs[1])
        samples.append(DispatchTime.now().uptimeNanoseconds - start)
    }
    let rawSamples = samples.map(String.init).joined(separator: ",")
    print(
        "PREFILL_QK_TIMING shape=\(shape.rawValue) arm=\(arm.rawValue) "
            + "warmups=\(warmupCount) samples_ns=[\(rawSamples)]"
    )
}

private func launchPrefillQK(
    _ fixture: PrefillQKFixture,
    arm: PrefillQKArm
) -> [MLXArray] {
    let kernel: MLXFast.MLXFastKernel
    switch (fixture.shape, arm) {
    case (.sliding, .h1):
        kernel = lagunaPrefillSlidingQKNormRoPEH1Kernel
    case (.sliding, .h4):
        kernel = lagunaPrefillSlidingQKNormRoPEKernel
    case (.sliding, .tokenStrip4):
        kernel = lagunaPrefillSlidingQKNormRoPETokenStrip4Kernel
    case (.full, .h1):
        kernel = lagunaPrefillFullQKNormYaRNH1Kernel
    case (.full, .h4):
        kernel = lagunaPrefillFullQKNormYaRNKernel
    case (.full, .tokenStrip4):
        kernel = lagunaPrefillFullQKNormYaRNTokenStrip4Kernel
    }

    let totalHeads = fixture.shape.queryHeads + 8
    let gridWidth: Int
    let threadGroup: (Int, Int, Int)
    switch arm {
    case .h1:
        gridWidth = totalHeads * 32
        threadGroup = (32, 1, 1)
    case .h4:
        gridWidth = totalHeads / 4 * 128
        threadGroup = (128, 1, 1)
    case .tokenStrip4:
        gridWidth = totalHeads * 32
        threadGroup = (32, 4, 1)
    }

    return kernel(
        [
            fixture.rawQueries, fixture.rawKeys,
            fixture.queryWeight, fixture.keyWeight,
            fixture.angles, fixture.offsets,
        ],
        grid: (gridWidth, fixture.length, 1),
        threadGroup: threadGroup,
        outputShapes: [
            [1, fixture.shape.queryHeads, fixture.length, 128],
            [1, 8, fixture.length, 128],
        ],
        outputDTypes: [.bfloat16, .bfloat16]
    )
}

private func makeBF16Array(count: Int, shape: [Int], seed: UInt32) -> MLXArray {
    let special: [UInt16] = [
        0x0000, 0x8000,
        0x0001, 0x8001,
        0x007f, 0x807f,
        0x0080, 0x8080,
        0x3c00, 0xbc00,
        0x3f80, 0xbf80,
        0x4000, 0xc000,
        0x4f00, 0xcf00,
    ]
    var state = seed
    var bits = [UInt16]()
    bits.reserveCapacity(count)
    for index in 0..<count {
        if index % 37 < special.count {
            bits.append(special[index % 37])
            continue
        }
        state ^= state << 13
        state ^= state >> 17
        state ^= state << 5
        let sign = UInt16(truncatingIfNeeded: state >> 16) & 0x8000
        let exponent = UInt16(108 + Int(state % 36)) << 7
        let mantissa = UInt16(truncatingIfNeeded: state) & 0x007f
        bits.append(sign | exponent | mantissa)
    }
    return MLXArray(bits, shape).view(dtype: .bfloat16)
}

private func makeAngles(rows: Int, width: Int) -> MLXArray {
    let pairs = width / 2
    var values = [Float]()
    values.reserveCapacity(rows * width)
    for row in 0..<rows {
        for index in 0..<width {
            let pair = index % pairs
            let phase = Float(row + 1) * 0.013 + Float(pair + 1) * 0.007
            values.append(index < pairs ? cos(phase) : sin(phase))
        }
    }
    return MLXArray(values, [1, 1, rows, width])
}

private func bitMismatchCount(_ lhs: MLXArray, _ rhs: MLXArray) -> Int {
    let lhsBits = lhs.view(dtype: .uint16).asArray(UInt16.self)
    let rhsBits = rhs.view(dtype: .uint16).asArray(UInt16.self)
    return zip(lhsBits, rhsBits).reduce(into: 0) { mismatches, pair in
        if pair.0 != pair.1 {
            mismatches += 1
        }
    }
}

private func maxAbsoluteDifference(_ lhs: MLXArray, _ rhs: MLXArray) -> Float {
    let lhsValues = lhs.asType(.float32).asArray(Float.self)
    let rhsValues = rhs.asType(.float32).asArray(Float.self)
    return zip(lhsValues, rhsValues).reduce(0) { maximum, pair in
        max(maximum, abs(pair.0 - pair.1))
    }
}

@Test
func prefillQKTokenStripScoredReachabilityWhenResearchTestsAreEnabled() throws {
    let environment = ProcessInfo.processInfo.environment
    guard environment["MLXFAST_RUN_PREFILL_QK_REACHABILITY"] == "1" else {
        return
    }

    unsetenv("DARKBLOOM_TRACE_PREFILL_QK_CENSUS")
    let weightsPath = environment["MLXFAST_PREFILL_QK_WEIGHTS_PATH"] ?? "weights"
    let config = try LagunaConfig.load(from: weightsPath)
    let loader = try LagunaWeightLoader(weightsPath: weightsPath)
    let weightCache = LagunaRuntimeWeightCache(loader: loader, config: config)
    let model = try weightCache.requireLibraryModel()
    let cache = model.newCache(parameters: nil)
    let promptTokens = (0..<512).map { Int32((31 * $0 + 7) % config.vocabSize) }

    setenv("DARKBLOOM_TRACE_PREFILL_QK_CENSUS", "1", 1)
    defer { unsetenv("DARKBLOOM_TRACE_PREFILL_QK_CENSUS") }

    prefillQKReachabilityMarker("phase=prefill event=begin input_shape=(1,512)")
    let prefillLogits = model(MLXArray(promptTokens, [1, 512]), cache: cache)
    eval(prefillLogits)
    prefillQKReachabilityMarker(
        "phase=prefill event=end cache_offset=\(cache.first?.offset ?? -1)"
    )
    #expect(cache.allSatisfy { $0.offset == 512 })

    prefillQKReachabilityMarker("phase=decode event=begin input_shape=(1,1)")
    let decodeLogits = model(MLXArray([Int32(1)], [1, 1]), cache: cache)
    eval(decodeLogits)
    prefillQKReachabilityMarker(
        "phase=decode event=end cache_offset=\(cache.first?.offset ?? -1)"
    )
    #expect(cache.allSatisfy { $0.offset == 513 })
}

private func prefillQKReachabilityMarker(_ line: String) {
    FileHandle.standardError.write(Data("PREFILL_QK_REACHABILITY \(line)\n".utf8))
}

