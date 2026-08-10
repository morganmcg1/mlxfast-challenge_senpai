import Foundation
import MLX
import MLXFast
import Testing
@testable import MLXFastModel

private enum OProjExperimentForm: CaseIterable {
    case activeStock
    case activeLaneMajor
    case preactivatedStock
    case preactivatedLaneMajor

    var preactivated: Bool {
        switch self {
        case .preactivatedStock, .preactivatedLaneMajor: true
        default: false
        }
    }

    var laneMajor: Bool {
        switch self {
        case .activeLaneMajor, .preactivatedLaneMajor: true
        default: false
        }
    }

    var label: String {
        switch self {
        case .activeStock: "active-stock"
        case .activeLaneMajor: "active-lane-major"
        case .preactivatedStock: "preactivated-stock"
        case .preactivatedLaneMajor: "preactivated-lane-major"
        }
    }
}

private struct OProjExperimentFixture {
    let bank: Int
    let heads: Int
    let form: OProjExperimentForm
    let attention: MLXArray
    let gate: MLXArray
    let codes: MLXArray
    let scales: MLXArray
    let scaleNibbles: MLXArray
    let scaleBases: MLXArray

    var inputs: [MLXArray] {
        if form.laneMajor {
            [attention, gate, codes, scaleNibbles, scaleBases, scales]
        } else {
            [attention, gate, codes, scales]
        }
    }
}

private struct OProjExperimentKernelPair {
    let scalar: MLXFast.MLXFastKernel
    let vector: MLXFast.MLXFastKernel
}

private let vectorLoadDeclaration = """
const bool code_load_aligned =
    (reinterpret_cast<ulong>(weight_codes) & 7ul) == 0ul;
"""

private let vectorLoadBlock = """
        uint2 code_pair;
        if (code_load_aligned) {
            code_pair = *reinterpret_cast<const device uint2*>(wl);
        } else {
            code_pair = uint2(wl[0], wl[1]);
        }
        #pragma unroll
        for (uint j = 0; j < codes_per_thread; ++j) {
            const uint c = j == 0 ? code_pair.x : code_pair.y;
"""

private let scalarLoadBlock = """
        #pragma unroll
        for (uint j = 0; j < codes_per_thread; ++j) {
            const uint c = wl[j];
"""

private func scalarOProjSource(_ candidate: String) -> String {
    precondition(candidate.components(separatedBy: vectorLoadDeclaration).count == 2)
    precondition(candidate.components(separatedBy: vectorLoadBlock).count == 2)
    return candidate
        .replacingOccurrences(of: vectorLoadDeclaration, with: "")
        .replacingOccurrences(of: vectorLoadBlock, with: scalarLoadBlock)
}

private func alignmentProbeOProjSource(_ candidate: String) -> String {
    precondition(candidate.components(separatedBy: vectorLoadDeclaration).count == 2)
    return candidate.replacingOccurrences(
        of: vectorLoadDeclaration,
        with: vectorLoadDeclaration
            + "if (tile == 0 && lid == 0) alignment[0] = code_load_aligned ? 1u : 0u;\n"
    )
}

private func experimentInputNames(_ form: OProjExperimentForm) -> [String] {
    var names = [
        "attention_output",
        form.preactivated ? "gate_values" : "gate_logits",
        "weight_codes",
    ]
    if form.laneMajor {
        names += ["scale_nibbles", "scale_bases"]
    }
    names.append("weight_scales")
    return names
}

private func experimentKernel(
    heads: Int,
    form: OProjExperimentForm,
    scalar: Bool,
    alignmentProbe: Bool = false
) -> MLXFast.MLXFastKernel {
    let candidate = lagunaGatedAffineOProjNVFP4Source(
        heads: heads,
        preActivatedGate: form.preactivated,
        laneMajor: form.laneMajor,
        pairwise: form.laneMajor
    )
    let source = alignmentProbe
        ? alignmentProbeOProjSource(candidate)
        : (scalar ? scalarOProjSource(candidate) : candidate)
    let variant = alignmentProbe ? "alignment" : (scalar ? "scalar" : "vector")
    return MLXFast.metalKernel(
        name: "oproj_codeword_\(variant)_h\(heads)_\(form.label.replacingOccurrences(of: "-", with: "_"))",
        inputNames: experimentInputNames(form),
        outputNames: alignmentProbe ? ["projected", "alignment"] : ["projected"],
        source: source,
        ensureRowContiguous: true
    )
}

private func experimentKernelPairs(
    forms: [OProjExperimentForm]
) -> [String: OProjExperimentKernelPair] {
    var pairs: [String: OProjExperimentKernelPair] = [:]
    for heads in [48, 64] {
        for form in forms {
            pairs["\(heads)-\(form.label)"] = OProjExperimentKernelPair(
                scalar: experimentKernel(heads: heads, form: form, scalar: true),
                vector: experimentKernel(heads: heads, form: form, scalar: false)
            )
        }
    }
    return pairs
}

private func experimentDispatch(
    _ kernel: MLXFast.MLXFastKernel,
    fixture: OProjExperimentFixture,
    verbose: Bool = false,
    alignmentProbe: Bool = false
) -> [MLXArray] {
    kernel(
        fixture.inputs,
        grid: ((2_048 / 8) * 64, 1, 1),
        threadGroup: (64, 1, 1),
        outputShapes: alignmentProbe ? [[1, 1, 2_048], [1]] : [[1, 1, 2_048]],
        outputDTypes: alignmentProbe ? [.bfloat16, .uint32] : [.bfloat16],
        verbose: verbose
    )
}

private func experimentCodes(heads: Int, bank: Int, misaligned: Bool = false) -> MLXArray {
    let rowWords = heads * 16
    let count = 2_048 * rowWords
    let offset = misaligned ? 1 : 0
    var words = [UInt32](repeating: 0, count: count + offset)
    let patterns: [UInt32] = [
        0x0000_0000, 0xffff_ffff, 0x0123_4567, 0x89ab_cdef,
        0x7654_3210, 0xfedc_ba98, 0x1111_1111, 0x8888_8888,
    ]
    let seed = UInt32(truncatingIfNeeded: bank &* 0x45d9f3b) ^ UInt32(heads)
    for index in 0..<count {
        let x = UInt32(truncatingIfNeeded: index) &* 0x9e37_79b9 &+ seed
        words[index + offset] = x ^ (x >> 16) ^ patterns[(index + bank) & 7]
    }
    let base = MLXArray(words, [count + offset])
    if misaligned {
        return base[1...].reshaped([2_048, rowWords])
    }
    return base.reshaped([2_048, rowWords])
}

private func experimentFixture(
    bank: Int,
    heads: Int,
    form: OProjExperimentForm,
    misaligned: Bool = false
) -> OProjExperimentFixture {
    let inVec = heads * 128
    let groups = inVec / 16
    let attentionValues: [Float] = (0..<inVec).map { index in
        let base: [Float] = [-3.5, -1.0, -0.0, 0.03125, 0.5, 1.0, 2.75, 6.0]
        return base[(index + bank) & 7] * Float((index % 5) + 1) / 5
    }
    let gateValues: [Float] = (0..<heads).map { index in
        if form.preactivated {
            let base: [Float] = [0, 0.000_976_562_5, 0.125, 0.5, 1, 4, 16, 64]
            return base[(index + bank) & 7]
        }
        let base: [Float] = [-16, -6, -2, -0.0, 0.25, 2, 6, 16]
        return base[(index + bank) & 7]
    }
    return OProjExperimentFixture(
        bank: bank,
        heads: heads,
        form: form,
        attention: MLXArray(attentionValues, [1, 1, inVec]).asType(.bfloat16),
        gate: MLXArray(gateValues, [1, 1, heads]).asType(.bfloat16),
        codes: experimentCodes(heads: heads, bank: bank, misaligned: misaligned),
        scales: MLXArray.full(
            [2_048, groups],
            values: MLXArray(UInt8(0x38)),
            dtype: .uint8
        ),
        scaleNibbles: MLXArray.full(
            [2_048, groups / 4],
            values: MLXArray(UInt8(0)),
            dtype: .uint8
        ),
        scaleBases: MLXArray.full(
            [2_048],
            values: MLXArray(UInt8(0x38)),
            dtype: .uint8
        )
    )
}

private func experimentBankDescriptors(
    form: OProjExperimentForm? = nil
) -> [(bank: Int, heads: Int, form: OProjExperimentForm)] {
    let forms = OProjExperimentForm.allCases
    let h64 = (0..<30).map { bank in
        (bank, 64, form ?? forms[bank % forms.count])
    }
    let h48 = (0..<10).map { offset in
        let bank = 30 + offset
        return (bank, 48, form ?? forms[bank % forms.count])
    }
    return h64 + h48
}

@Test
func oprojVectorLoadMatchesScalarAcrossAllBanksWhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_OPROJ_VECTOR_CORRECTNESS"] == "1" else {
        return
    }

    let pairs = experimentKernelPairs(forms: OProjExperimentForm.allCases)
    var compared = 0
    for descriptor in experimentBankDescriptors() {
        let fixture = experimentFixture(
            bank: descriptor.bank,
            heads: descriptor.heads,
            form: descriptor.form
        )
        eval(fixture.inputs)
        let pair = pairs["\(descriptor.heads)-\(descriptor.form.label)"]!
        let scalar = experimentDispatch(pair.scalar, fixture: fixture)[0]
        let vector = experimentDispatch(
            pair.vector,
            fixture: fixture,
            verbose: descriptor.bank == 0 || descriptor.bank == 30
        )[0]
        eval(scalar, vector)
        let scalarBits = scalar.view(dtype: .uint16).asArray(UInt16.self)
        let vectorBits = vector.view(dtype: .uint16).asArray(UInt16.self)
        if scalarBits != vectorBits {
            print(
                "OPROJ_CORRECTNESS_MISMATCH bank=\(descriptor.bank) "
                    + "heads=\(descriptor.heads) form=\(descriptor.form.label)"
            )
        }
        #expect(scalarBits == vectorBits)
        compared += 1
    }
    #expect(compared == 40)

    let form = OProjExperimentForm.activeStock
    let misaligned = experimentFixture(bank: 97, heads: 48, form: form, misaligned: true)
    let pair = pairs["48-\(form.label)"]!
    let scalar = experimentDispatch(pair.scalar, fixture: misaligned)[0]
    let vector = experimentDispatch(pair.vector, fixture: misaligned)[0]
    let probe = experimentKernel(heads: 48, form: form, scalar: false, alignmentProbe: true)
    let probeOutputs = experimentDispatch(
        probe,
        fixture: misaligned,
        alignmentProbe: true
    )
    eval(scalar, vector, probeOutputs[0], probeOutputs[1])
    let scalarBits = scalar.view(dtype: .uint16).asArray(UInt16.self)
    let vectorBits = vector.view(dtype: .uint16).asArray(UInt16.self)
    #expect(scalarBits == vectorBits)
    #expect(probeOutputs[1].asArray(UInt32.self) == [0])

    var corrupted = scalarBits
    corrupted[0] ^= 1
    #expect(corrupted != vectorBits)
    print(
        "OPROJ_CORRECTNESS_PASS banks=40 h64=30 h48=10 "
            + "misaligned_fallback=1 corruption_control=1"
    )
}

private func experimentMeasure(
    fixtures: [OProjExperimentFixture],
    pairs: [String: OProjExperimentKernelPair],
    vector: Bool
) -> Double {
    let start = ContinuousClock.now
    var outputs: [MLXArray] = []
    outputs.reserveCapacity(fixtures.count)
    for fixture in fixtures {
        let pair = pairs["\(fixture.heads)-\(fixture.form.label)"]!
        let kernel = vector ? pair.vector : pair.scalar
        outputs.append(experimentDispatch(kernel, fixture: fixture)[0])
    }
    eval(outputs)
    let elapsed = start.duration(to: .now).components
    return Double(elapsed.seconds) * 1_000_000 + Double(elapsed.attoseconds) / 1_000_000_000_000
}

private func experimentSamples(
    order: String,
    fixtures: [OProjExperimentFixture],
    pairs: [String: OProjExperimentKernelPair]
) -> (scalar: [Double], vector: [Double]) {
    var scalar: [Double] = []
    var vector: [Double] = []
    scalar.reserveCapacity(64)
    vector.reserveCapacity(64)
    for _ in 0..<64 {
        if order == "ABBA" {
            let scalarFirst = experimentMeasure(fixtures: fixtures, pairs: pairs, vector: false)
            let vectorFirst = experimentMeasure(fixtures: fixtures, pairs: pairs, vector: true)
            let vectorSecond = experimentMeasure(fixtures: fixtures, pairs: pairs, vector: true)
            let scalarSecond = experimentMeasure(fixtures: fixtures, pairs: pairs, vector: false)
            scalar.append((scalarFirst + scalarSecond) / 2)
            vector.append((vectorFirst + vectorSecond) / 2)
        } else {
            let vectorFirst = experimentMeasure(fixtures: fixtures, pairs: pairs, vector: true)
            let scalarFirst = experimentMeasure(fixtures: fixtures, pairs: pairs, vector: false)
            let scalarSecond = experimentMeasure(fixtures: fixtures, pairs: pairs, vector: false)
            let vectorSecond = experimentMeasure(fixtures: fixtures, pairs: pairs, vector: true)
            scalar.append((scalarFirst + scalarSecond) / 2)
            vector.append((vectorFirst + vectorSecond) / 2)
        }
    }
    return (scalar, vector)
}

private func experimentPrintSamples(
    label: String,
    order: String,
    samples: (scalar: [Double], vector: [Double])
) {
    let scalar = samples.scalar.map { String(format: "%.3f", $0) }.joined(separator: ",")
    let vector = samples.vector.map { String(format: "%.3f", $0) }.joined(separator: ",")
    print("OPROJ_TIMING label=\(label) order=\(order) scalar_us=[\(scalar)]")
    print("OPROJ_TIMING label=\(label) order=\(order) vector_us=[\(vector)]")
}

@Test
func oprojVectorLoadIsolatedTimingWhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_OPROJ_VECTOR_TIMING"] == "1" else {
        return
    }

    let form = OProjExperimentForm.preactivatedLaneMajor
    let pairs = experimentKernelPairs(forms: [form])
    let fixtures = experimentBankDescriptors(form: form).map { descriptor in
        experimentFixture(bank: descriptor.bank, heads: descriptor.heads, form: descriptor.form)
    }
    eval(fixtures.flatMap(\.inputs))

    for _ in 0..<4 {
        _ = experimentMeasure(fixtures: fixtures, pairs: pairs, vector: false)
        _ = experimentMeasure(fixtures: fixtures, pairs: pairs, vector: true)
    }

    let h64 = fixtures.filter { $0.heads == 64 }
    let h48 = fixtures.filter { $0.heads == 48 }
    for (label, subset) in [("all", fixtures), ("h64", h64), ("h48", h48)] {
        experimentPrintSamples(
            label: label,
            order: "ABBA",
            samples: experimentSamples(order: "ABBA", fixtures: subset, pairs: pairs)
        )
        experimentPrintSamples(
            label: label,
            order: "BAAB",
            samples: experimentSamples(order: "BAAB", fixtures: subset, pairs: pairs)
        )
    }
}
