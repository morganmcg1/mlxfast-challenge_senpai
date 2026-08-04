import Foundation
import MLX
import MLXLMCommon
import MLXNN
import Testing
@testable import MLXFastCore
@testable import MLXFastModel

// Direct unit coverage for `LagunaConfig.load` (the runtime side of the
// transformed-weights contract in docs/laguna-weight-contract.md). The
// runtime worker's pinned-configuration gate is covered separately in
// BenchmarkSupportTests; these tests pin the LagunaConfig parse/validation
// behavior itself, including the exact Poolside NVFP4 contract.

/// Exact behavior-bearing fields from the immutable Poolside R2 config. The
/// checked-in fixture also records the source repository, revision, and
/// manifest-pinned config digest so tests cannot silently drift into a
/// synthetic schema.
func pinnedLagunaConfigObject() -> [String: Any] {
    let path =
        "Tests/Fixtures/PoolsideLagunaXS21NVFP4/config-contract.json"
    guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
          let root = try? JSONSerialization.jsonObject(with: data)
            as? [String: Any],
          let source = root["source"] as? [String: Any],
          source["repository"] as? String
            == MLXFastConstants.referenceModelRepository,
          source["revision"] as? String
            == MLXFastConstants.referenceModelRevision,
          source["config_sha256"] as? String
            == "ef1eaf6709b38ab58b47480fdf8b2732163b34427d4a0ec334f77af27e1ce3b9",
          let config = root["config"] as? [String: Any]
    else {
        preconditionFailure("invalid pinned Poolside config contract fixture")
    }
    return config
}

private func temporaryDirectory() throws -> URL {
    let url = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString,
        isDirectory: true
    )
    try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
}

func loadLagunaConfig(_ object: [String: Any]) throws -> LagunaConfig {
    let root = try temporaryDirectory()
    defer { try? FileManager.default.removeItem(at: root) }
    let data = try JSONSerialization.data(withJSONObject: object)
    try data.write(to: root.appendingPathComponent("config.json"))
    return try LagunaConfig.load(from: root.path)
}

private func deterministicKV(from start: Int, count: Int) -> MLXArray {
    let positions = MLXArray((start..<(start + count)).map { Float($0) })
        .reshaped([1, 1, count, 1])
    let dimensions = MLXArray((0..<4).map { Float($0) / 1_000 })
        .reshaped([1, 1, 1, 4])
    return broadcast(positions + dimensions, to: [1, 1, count, 4])
        .asType(.bfloat16)
}

private func expectExact(_ actual: MLXArray, _ expected: MLXArray) {
    #expect(actual.shape == expected.shape)
    #expect(arrayEqual(actual, expected).item(Bool.self))
}

@Test
func lagunaConfigLoadsPinnedPoolsideNVFP4Geometry() throws {
    let config = try loadLagunaConfig(pinnedLagunaConfigObject())

    #expect(config.modelType == LagunaConstants.modelType)
    #expect(config.vocabSize == LagunaConstants.vocabSize)
    #expect(config.hiddenSize == LagunaConstants.hiddenSize)
    #expect(config.numHiddenLayers == LagunaConstants.numHiddenLayers)
    #expect(config.numKeyValueHeads == LagunaConstants.numKeyValueHeads)
    #expect(config.headDim == LagunaConstants.headDim)
    #expect(config.slidingWindow == LagunaConstants.slidingWindow)
    #expect(config.maxPositionEmbeddings == LagunaConstants.maxPositionEmbeddings)
    #expect(config.rmsNormEps == LagunaConstants.rmsNormEpsilon)
    #expect(!config.tieWordEmbeddings)
    #expect(config.gating == .perHead)
    #expect(config.gatingTypes == [LagunaGatingMode](
        repeating: .perHead,
        count: LagunaConstants.numHiddenLayers
    ))
    #expect(config.mlpOnlyLayers == [0])
    #expect(config.decoderSparseStep == 1)
    #expect(config.moeRoutedScalingFactor == LagunaConstants.moeRoutedScalingFactor)
    #expect(config.normTopkProb)
    #expect(!config.moeApplyRouterWeightOnInput)

    // Per-layer schedule: full attention (48 heads, YaRN partial rotary) at
    // 0, 4, 8, ..., sliding (64 heads, default RoPE) elsewhere; dense MLP
    // only at layer 0.
    for layerIndex in 0..<config.numHiddenLayers {
        let isFull = layerIndex % 4 == 0
        #expect(config.layerType(forLayer: layerIndex) == (isFull ? .full : .sliding))
        #expect(
            config.heads(forLayer: layerIndex)
                == (isFull
                    ? LagunaConstants.fullAttentionHeads
                    : LagunaConstants.slidingAttentionHeads)
        )
        #expect(config.isSparse(layer: layerIndex) == (layerIndex != 0))
    }
    #expect(config.fullRope.type == "yarn")
    #expect(config.fullRope.partialRotaryFactor == 0.5)
    #expect(config.fullRope.attentionFactor == 1.0)
    #expect(config.slidingRope.type == "default")
    #expect(config.slidingRope.partialRotaryFactor == 1.0)
    #expect(config.slidingRope.attentionFactor == nil)

    // Quantization: exact Poolside NVFP4 4-bit group-16 with no overrides.
    #expect(config.quantization.groupSize == LagunaConstants.quantizationGroupSize)
    #expect(config.quantization.bits == LagunaConstants.quantizationBits)
    #expect(config.quantization.mode == LagunaConstants.quantizationMode)
    #expect(config.quantization.overrides.isEmpty)
}

@Test
func lagunaYaRNIgnoresSerializedAttentionFactorLikeUpstreamMLX() throws {
    let config = try loadLagunaConfig(pinnedLagunaConfigObject())
    let scaling = lagunaRopeScalingConfig(config.fullRope)

    #expect(config.fullRope.attentionFactor == 1.0)
    #expect(scaling["attention_factor"] == nil)
    #expect(scaling["mscale"] == nil)
    #expect(scaling["mscale_all_dim"] == nil)

    let upstreamDerivedMScale = 1.0 + 0.1 * log(config.fullRope.factor)
    #expect(abs(upstreamDerivedMScale - 1.3465735902799727) < 1e-12)
}

@Test
func kvCacheInitialAllocationSlackPreservesLogicalState() throws {
    let seedKeys = deterministicKV(from: 0, count: 512)
    let seedValues = deterministicKV(from: 1_000, count: 512)
    let nextKeys = deterministicKV(from: 512, count: 1)
    let nextValues = deterministicKV(from: 1_512, count: 1)
    let followingKeys = deterministicKV(from: 513, count: 1)
    let followingValues = deterministicKV(from: 1_513, count: 1)

    let standard = KVCacheSimple()
    let standardSeed = standard.update(keys: seedKeys, values: seedValues)
    #expect(standard.offset == 512)
    #expect(standard.innerState()[0].dim(2) == 512)
    #expect(standard.fusedAppendPrepare() == nil)
    expectExact(standardSeed.0, seedKeys)
    expectExact(standardSeed.1, seedValues)

    let standardNext = standard.update(keys: nextKeys, values: nextValues)
    #expect(standard.offset == 513)
    #expect(standard.innerState()[0].dim(2) == 768)
    expectExact(standardNext.0, concatenated([seedKeys, nextKeys], axis: 2))
    expectExact(standardNext.1, concatenated([seedValues, nextValues], axis: 2))

    let slack = KVCacheSimple(reserveInitialAllocationStep: true)
    let slackSeed = slack.update(keys: seedKeys, values: seedValues)
    #expect(slack.offset == 512)
    #expect(slack.innerState()[0].dim(2) == 768)
    #expect(slack.state[0].dim(2) == 512)
    expectExact(slackSeed.0, seedKeys)
    expectExact(slackSeed.1, seedValues)
    expectExact(slack.state[0], seedKeys)
    expectExact(slack.state[1], seedValues)

    let firstAppend = try #require(slack.fusedAppendPrepare())
    #expect(firstAppend.writeIdx == 512)
    #expect(firstAppend.keys.dim(2) == 768)

    let slackNext = slack.update(keys: nextKeys, values: nextValues)
    #expect(slack.offset == 513)
    expectExact(slackNext.0, concatenated([seedKeys, nextKeys], axis: 2))
    expectExact(slackNext.1, concatenated([seedValues, nextValues], axis: 2))

    let secondAppend = try #require(slack.fusedAppendPrepare())
    #expect(secondAppend.writeIdx == 513)

    let slackFollowing = slack.update(keys: followingKeys, values: followingValues)
    #expect(slack.offset == 514)
    expectExact(
        slackFollowing.0,
        concatenated([seedKeys, nextKeys, followingKeys], axis: 2)
    )
    expectExact(
        slackFollowing.1,
        concatenated([seedValues, nextValues, followingValues], axis: 2)
    )

    let copied = try #require(slack.copy() as? KVCacheSimple)
    #expect(copied.reserveInitialAllocationStep)
    #expect(copied.offset == slack.offset)
    expectExact(copied.state[0], slack.state[0])
    expectExact(copied.state[1], slack.state[1])
}

@Test
func lagunaRuntimeWiresOnlyExpertsToNVFP4WhenRuntimeTestsAreEnabled() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let model = LagunaRuntimeModel(try loadLagunaConfig(pinnedLagunaConfigObject()))
    let leaves = Dictionary(uniqueKeysWithValues: model.leafModules().flattened())

    let caches = model.newCache(parameters: nil)
    #expect(caches.count == LagunaConstants.numHiddenLayers)
    for layerIndex in caches.indices {
        if layerIndex.isMultiple(of: 4) {
            let cache = try #require(caches[layerIndex] as? KVCacheSimple)
            #expect(cache.reserveInitialAllocationStep)
        } else {
            #expect(caches[layerIndex] is RotatingKVCache)
        }
    }

    let denseGate = try #require(
        leaves["model.layers.0.mlp.gate_proj"] as? Linear
    )
    #expect(!(denseGate is QuantizedLinear))

    let router = try #require(leaves["model.layers.1.mlp.gate"])
    #expect(!(router is Quantized))

    let routedGate = try #require(
        leaves["model.layers.1.mlp.switch_mlp.gate_proj"] as? QuantizedSwitchLinear
    )
    #expect(routedGate.groupSize == LagunaConstants.quantizationGroupSize)
    #expect(routedGate.bits == LagunaConstants.quantizationBits)
    #expect(routedGate.mode == .nvfp4)

    let sharedGate = try #require(
        leaves["model.layers.1.mlp.shared_expert.gate_proj"] as? QuantizedLinear
    )
    #expect(sharedGate.groupSize == LagunaConstants.quantizationGroupSize)
    #expect(sharedGate.bits == LagunaConstants.quantizationBits)
    #expect(sharedGate.mode == .nvfp4)

    let attention = try #require(
        leaves["model.layers.1.self_attn.q_proj"] as? Linear
    )
    #expect(!(attention is QuantizedLinear))
}

@Test
func lagunaConfigRejectsChangedArchitecture() throws {
    var object = pinnedLagunaConfigObject()
    object["num_hidden_layers"] = 12
    #expect(throws: MLXFastError.self) {
        _ = try loadLagunaConfig(object)
    }

    object = pinnedLagunaConfigObject()
    object["tie_word_embeddings"] = true
    #expect(throws: MLXFastError.self) {
        _ = try loadLagunaConfig(object)
    }

    object = pinnedLagunaConfigObject()
    object["num_experts"] = 128
    #expect(throws: MLXFastError.self) {
        _ = try loadLagunaConfig(object)
    }
}

@Test
func lagunaConfigRejectsBehaviorChangingXSMutations() throws {
    func expectRejected(
        _ label: String,
        _ mutate: (inout [String: Any]) -> Void
    ) throws {
        var object = pinnedLagunaConfigObject()
        mutate(&object)
        #expect(throws: MLXFastError.self, Comment(rawValue: label)) {
            _ = try loadLagunaConfig(object)
        }
    }

    try expectRejected("48/64 head schedule") {
        var schedule = $0["num_attention_heads_per_layer"] as! [Int]
        schedule[1] = LagunaConstants.fullAttentionHeads
        $0["num_attention_heads_per_layer"] = schedule
    }
    try expectRejected("1-full:3-sliding attention schedule") {
        var schedule = $0["layer_types"] as! [String]
        schedule[1] = "full_attention"
        $0["layer_types"] = schedule
    }
    try expectRejected("dense layer zero only") {
        var schedule = $0["mlp_layer_types"] as! [String]
        schedule[1] = "dense"
        $0["mlp_layer_types"] = schedule
    }
    try expectRejected("mlp_only_layers") { $0["mlp_only_layers"] = [0, 2] }
    try expectRejected("decoder_sparse_step") { $0["decoder_sparse_step"] = 2 }
    try expectRejected("top-level attention heads") {
        $0["num_attention_heads"] = LagunaConstants.slidingAttentionHeads
    }
    try expectRejected("KV heads") { $0["num_key_value_heads"] = 4 }
    try expectRejected("head dimension") { $0["head_dim"] = 64 }
    try expectRejected("sliding window") { $0["sliding_window"] = 1_024 }
    try expectRejected("maximum position") { $0["max_position_embeddings"] = 131_072 }
    try expectRejected("RMS epsilon") { $0["rms_norm_eps"] = 1e-5 }
    try expectRejected("attention bias") { $0["attention_bias"] = true }
    try expectRejected("qkv_bias absent/null contract") { $0["qkv_bias"] = false }
    try expectRejected("attention dropout") { $0["attention_dropout"] = 0.1 }
    try expectRejected("global gating") { $0["gating"] = "per-element" }
    try expectRejected("tied embeddings") { $0["tie_word_embeddings"] = true }
    try expectRejected("expert count") { $0["num_experts"] = 128 }
    try expectRejected("experts per token") { $0["num_experts_per_tok"] = 4 }
    try expectRejected("routed expert width") { $0["moe_intermediate_size"] = 1_024 }
    try expectRejected("shared expert width") {
        $0["shared_expert_intermediate_size"] = 1_024
    }
    try expectRejected("routed scaling") { $0["moe_routed_scaling_factor"] = 1.0 }
    try expectRejected("top-k normalization") { $0["norm_topk_prob"] = false }
    try expectRejected("router weight placement") {
        $0["moe_apply_router_weight_on_input"] = true
    }
    try expectRejected("router softcap absent/null contract") {
        $0["moe_router_logit_softcapping"] = 0.0
    }
    try expectRejected("per-layer gating") {
        var schedule = $0["gating_types"] as! [String]
        schedule[7] = "per_element"
        $0["gating_types"] = schedule
    }
    try expectRejected("sliding RoPE theta") {
        mutateRope(&$0, kind: "sliding_attention", field: "rope_theta", value: 20_000.0)
    }
    try expectRejected("sliding partial rotary") {
        mutateRope(
            &$0,
            kind: "sliding_attention",
            field: "partial_rotary_factor",
            value: 0.5
        )
    }
    try expectRejected("full RoPE theta") {
        mutateRope(&$0, kind: "full_attention", field: "rope_theta", value: 1_000_000.0)
    }
    try expectRejected("full RoPE type") {
        mutateRope(&$0, kind: "full_attention", field: "rope_type", value: "default")
    }
    try expectRejected("YaRN factor") {
        mutateRope(&$0, kind: "full_attention", field: "factor", value: 16.0)
    }
    try expectRejected("YaRN original context") {
        mutateRope(
            &$0,
            kind: "full_attention",
            field: "original_max_position_embeddings",
            value: 4_096
        )
    }
    try expectRejected("YaRN beta fast") {
        mutateRope(&$0, kind: "full_attention", field: "beta_fast", value: 32.0)
    }
    try expectRejected("YaRN beta slow") {
        mutateRope(&$0, kind: "full_attention", field: "beta_slow", value: 2.0)
    }
    try expectRejected("full partial rotary") {
        mutateRope(
            &$0,
            kind: "full_attention",
            field: "partial_rotary_factor",
            value: 1.0
        )
    }
    try expectRejected("serialized YaRN attention factor") {
        mutateRope(&$0, kind: "full_attention", field: "attention_factor", value: 1.25)
    }
    try expectRejected("missing serialized YaRN attention factor") {
        var ropes = $0["rope_parameters"] as! [String: Any]
        var full = ropes["full_attention"] as! [String: Any]
        full.removeValue(forKey: "attention_factor")
        ropes["full_attention"] = full
        $0["rope_parameters"] = ropes
    }
    try expectRejected("unexpected YaRN mscale override") {
        mutateRope(&$0, kind: "full_attention", field: "mscale", value: 1.0)
    }
    try expectRejected("missing gating schedule") { $0.removeValue(forKey: "gating_types") }
}

@Test
func lagunaConfigAcceptsAbsentOrExplicitNullNullableArtifactFields() throws {
    var object = pinnedLagunaConfigObject()
    #expect(object["qkv_bias"] == nil)
    #expect(object["moe_router_logit_softcapping"] == nil)
    object["qkv_bias"] = NSNull()
    object["moe_router_logit_softcapping"] = NSNull()

    let config = try loadLagunaConfig(object)
    #expect(!config.qkvBias)
    #expect(config.moeRouterLogitSoftcapping == 0)
}

private func mutateRope(
    _ object: inout [String: Any],
    kind: String,
    field: String,
    value: Any
) {
    var ropes = object["rope_parameters"] as! [String: Any]
    var rope = ropes[kind] as! [String: Any]
    rope[field] = value
    ropes[kind] = rope
    object["rope_parameters"] = ropes
}

@Test
func lagunaConfigRejectsAnyQuantizationOverride() throws {
    var object = pinnedLagunaConfigObject()
    var quantization = try #require(object["quantization"] as? [String: Any])
    quantization["model.layers.1.mlp.switch_mlp.gate_proj"] = [
        "group_size": 16,
        "bits": 4,
    ]
    object["quantization"] = quantization
    #expect(throws: MLXFastError.self) {
        _ = try loadLagunaConfig(object)
    }
}

@Test
func lagunaConfigRequiresMatchingExplicitQuantizationBlocks() throws {
    var object = pinnedLagunaConfigObject()
    object.removeValue(forKey: "quantization_config")
    #expect(throws: MLXFastError.self) {
        _ = try loadLagunaConfig(object)
    }

    object = pinnedLagunaConfigObject()
    var quantizationConfig = try #require(
        object["quantization_config"] as? [String: Any]
    )
    quantizationConfig["group_size"] = 32
    object["quantization_config"] = quantizationConfig
    #expect(throws: MLXFastError.self) {
        _ = try loadLagunaConfig(object)
    }

    object = pinnedLagunaConfigObject()
    var quantization = try #require(object["quantization"] as? [String: Any])
    quantization.removeValue(forKey: "mode")
    object["quantization"] = quantization
    #expect(throws: MLXFastError.self) {
        _ = try loadLagunaConfig(object)
    }
}

@Test
func lagunaConfigRejectsUnsupportedRopeType() throws {
    var object = pinnedLagunaConfigObject()
    var ropeParameters = try #require(object["rope_parameters"] as? [String: Any])
    ropeParameters["full_attention"] = [
        "rope_theta": 500_000.0,
        "rope_type": "llama3",
        "partial_rotary_factor": 0.5,
    ]
    object["rope_parameters"] = ropeParameters
    #expect(throws: MLXFastError.self) {
        _ = try loadLagunaConfig(object)
    }
}
