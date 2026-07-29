import Foundation

public enum BridgeRequestKind: String, Codable, Sendable {
    case generate
    case logprobs
}

public struct BridgeRequest: Decodable, Equatable, Sendable {
    public let id: String
    public let kind: BridgeRequestKind
    public let promptTokenIDs: [Int]
    public let maxTokens: Int?
    public let temperature: Float
    public let topP: Float
    public let topK: Int
    public let seed: UInt64
    public let minTokens: Int
    public let stopTokenIDs: [Int]
    public let scoreStart: Int
    public let scoreEnd: Int?

    public init(
        id: String,
        kind: BridgeRequestKind,
        promptTokenIDs: [Int],
        maxTokens: Int? = nil,
        temperature: Float = 0,
        topP: Float = 1,
        topK: Int = 0,
        seed: UInt64 = 0,
        minTokens: Int = 0,
        stopTokenIDs: [Int] = [],
        scoreStart: Int = 1,
        scoreEnd: Int? = nil
    ) {
        self.id = id
        self.kind = kind
        self.promptTokenIDs = promptTokenIDs
        self.maxTokens = maxTokens
        self.temperature = temperature
        self.topP = topP
        self.topK = topK
        self.seed = seed
        self.minTokens = minTokens
        self.stopTokenIDs = stopTokenIDs
        self.scoreStart = scoreStart
        self.scoreEnd = scoreEnd
    }

    private enum CodingKeys: String, CodingKey {
        case id
        case kind
        case promptTokenIDs = "prompt_token_ids"
        case maxTokens = "max_tokens"
        case temperature
        case topP = "top_p"
        case topK = "top_k"
        case seed
        case minTokens = "min_tokens"
        case stopTokenIDs = "stop_token_ids"
        case scoreStart = "score_start"
        case scoreEnd = "score_end"
    }

    public init(from decoder: any Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decode(String.self, forKey: .id)
        kind = try values.decode(BridgeRequestKind.self, forKey: .kind)
        promptTokenIDs = try values.decode([Int].self, forKey: .promptTokenIDs)
        maxTokens = try values.decodeIfPresent(Int.self, forKey: .maxTokens)
        temperature = try values.decodeIfPresent(Float.self, forKey: .temperature) ?? 0
        topP = try values.decodeIfPresent(Float.self, forKey: .topP) ?? 1
        topK = try values.decodeIfPresent(Int.self, forKey: .topK) ?? 0
        seed = try values.decodeIfPresent(UInt64.self, forKey: .seed) ?? 0
        minTokens = try values.decodeIfPresent(Int.self, forKey: .minTokens) ?? 0
        stopTokenIDs = try values.decodeIfPresent([Int].self, forKey: .stopTokenIDs) ?? []
        scoreStart = try values.decodeIfPresent(Int.self, forKey: .scoreStart) ?? 1
        scoreEnd = try values.decodeIfPresent(Int.self, forKey: .scoreEnd)
    }

    public func validated(
        vocabSize: Int,
        maxPositionEmbeddings: Int
    ) throws -> ValidatedBridgeRequest {
        guard !id.isEmpty else {
            throw BridgeProtocolError("id must not be empty")
        }
        guard vocabSize > 0 else {
            throw BridgeProtocolError("vocab size must be positive")
        }
        guard maxPositionEmbeddings > 0 else {
            throw BridgeProtocolError("maximum position count must be positive")
        }
        guard !promptTokenIDs.isEmpty else {
            throw BridgeProtocolError("prompt_token_ids must not be empty")
        }
        try validateTokens(
            promptTokenIDs,
            field: "prompt_token_ids",
            vocabSize: vocabSize
        )
        try validateTokens(
            stopTokenIDs,
            field: "stop_token_ids",
            vocabSize: vocabSize
        )
        guard promptTokenIDs.count <= maxPositionEmbeddings else {
            throw BridgeProtocolError(
                "prompt has \(promptTokenIDs.count) tokens; model maximum is \(maxPositionEmbeddings)"
            )
        }

        switch kind {
        case .generate:
            guard let maxTokens else {
                throw BridgeProtocolError(
                    "generate request requires max_tokens"
                )
            }
            guard maxTokens >= 0 else {
                throw BridgeProtocolError("max_tokens must be non-negative")
            }
            guard minTokens >= 0 else {
                throw BridgeProtocolError("min_tokens must be non-negative")
            }
            guard temperature.isFinite, temperature >= 0 else {
                throw BridgeProtocolError(
                    "temperature must be finite and non-negative"
                )
            }
            guard topP.isFinite, topP > 0, topP <= 1 else {
                throw BridgeProtocolError(
                    "top_p must be finite and in (0, 1]"
                )
            }
            guard topK >= -1, topK <= vocabSize else {
                throw BridgeProtocolError(
                    "top_k must be -1 or in 0...\(vocabSize)"
                )
            }
            guard maxTokens <= maxPositionEmbeddings - promptTokenIDs.count
            else {
                throw BridgeProtocolError(
                    "prompt plus max_tokens exceeds model maximum \(maxPositionEmbeddings)"
                )
            }
            return .generate(
                ValidatedGenerateRequest(
                    id: id,
                    promptTokenIDs: promptTokenIDs,
                    maxTokens: maxTokens,
                    temperature: temperature,
                    topP: topP,
                    topK: max(topK, 0),
                    seed: seed,
                    minTokens: minTokens,
                    stopTokenIDs: Array(Set(stopTokenIDs)).sorted()
                )
            )

        case .logprobs:
            let end = scoreEnd ?? promptTokenIDs.count
            guard scoreStart >= 1, scoreStart <= promptTokenIDs.count else {
                throw BridgeProtocolError(
                    "score_start must be in 1...\(promptTokenIDs.count)"
                )
            }
            guard end >= scoreStart, end <= promptTokenIDs.count else {
                throw BridgeProtocolError(
                    "score_end must be in score_start...\(promptTokenIDs.count)"
                )
            }
            return .logprobs(
                ValidatedLogprobsRequest(
                    id: id,
                    promptTokenIDs: promptTokenIDs,
                    scoreStart: scoreStart,
                    scoreEnd: end
                )
            )
        }
    }

    private func validateTokens(
        _ tokens: [Int],
        field: String,
        vocabSize: Int
    ) throws {
        if let invalid = tokens.enumerated().first(where: {
            $0.element < 0 || $0.element >= vocabSize
        }) {
            throw BridgeProtocolError(
                "\(field)[\(invalid.offset)]=\(invalid.element) is outside 0..<\(vocabSize)"
            )
        }
    }
}

public enum ValidatedBridgeRequest: Equatable, Sendable {
    case generate(ValidatedGenerateRequest)
    case logprobs(ValidatedLogprobsRequest)
}

public struct ValidatedGenerateRequest: Equatable, Sendable {
    public let id: String
    public let promptTokenIDs: [Int]
    public let maxTokens: Int
    public let temperature: Float
    public let topP: Float
    public let topK: Int
    public let seed: UInt64
    public let minTokens: Int
    public let stopTokenIDs: [Int]

    public init(
        id: String,
        promptTokenIDs: [Int],
        maxTokens: Int,
        temperature: Float,
        topP: Float,
        topK: Int,
        seed: UInt64,
        minTokens: Int,
        stopTokenIDs: [Int]
    ) {
        self.id = id
        self.promptTokenIDs = promptTokenIDs
        self.maxTokens = maxTokens
        self.temperature = temperature
        self.topP = topP
        self.topK = topK
        self.seed = seed
        self.minTokens = minTokens
        self.stopTokenIDs = stopTokenIDs
    }
}

public struct ValidatedLogprobsRequest: Equatable, Sendable {
    public let id: String
    public let promptTokenIDs: [Int]
    public let scoreStart: Int
    public let scoreEnd: Int

    public init(
        id: String,
        promptTokenIDs: [Int],
        scoreStart: Int,
        scoreEnd: Int
    ) {
        self.id = id
        self.promptTokenIDs = promptTokenIDs
        self.scoreStart = scoreStart
        self.scoreEnd = scoreEnd
    }
}

public struct BridgeResponse: Encodable, Equatable, Sendable {
    public let id: String?
    public let kind: String?
    public let ok: Bool
    public let model: String?
    public let vocabSize: Int?
    public let maxPositionEmbeddings: Int?
    public let tokenIDs: [Int]?
    public let finishReason: String?
    public let tokenLogprobs: [Double]?
    public let error: String?

    private enum CodingKeys: String, CodingKey {
        case id
        case kind
        case ok
        case model
        case vocabSize = "vocab_size"
        case maxPositionEmbeddings = "max_position_embeddings"
        case tokenIDs = "token_ids"
        case finishReason = "finish_reason"
        case tokenLogprobs = "token_logprobs"
        case error
    }

    public static func ready(
        model: String,
        vocabSize: Int,
        maxPositionEmbeddings: Int
    ) -> BridgeResponse {
        BridgeResponse(
            id: nil,
            kind: "ready",
            ok: true,
            model: model,
            vocabSize: vocabSize,
            maxPositionEmbeddings: maxPositionEmbeddings,
            tokenIDs: nil,
            finishReason: nil,
            tokenLogprobs: nil,
            error: nil
        )
    }

    public static func generated(
        id: String,
        tokenIDs: [Int],
        finishReason: String
    ) -> BridgeResponse {
        BridgeResponse(
            id: id,
            kind: nil,
            ok: true,
            model: nil,
            vocabSize: nil,
            maxPositionEmbeddings: nil,
            tokenIDs: tokenIDs,
            finishReason: finishReason,
            tokenLogprobs: nil,
            error: nil
        )
    }

    public static func logprobs(
        id: String,
        tokenLogprobs: [Double]
    ) -> BridgeResponse {
        BridgeResponse(
            id: id,
            kind: nil,
            ok: true,
            model: nil,
            vocabSize: nil,
            maxPositionEmbeddings: nil,
            tokenIDs: nil,
            finishReason: nil,
            tokenLogprobs: tokenLogprobs,
            error: nil
        )
    }

    public static func failure(id: String?, error: String) -> BridgeResponse {
        BridgeResponse(
            id: id,
            kind: nil,
            ok: false,
            model: nil,
            vocabSize: nil,
            maxPositionEmbeddings: nil,
            tokenIDs: nil,
            finishReason: nil,
            tokenLogprobs: nil,
            error: error
        )
    }
}

public struct BridgeProtocolError: Error, LocalizedError, Equatable, Sendable {
    public let message: String

    public init(_ message: String) {
        self.message = message
    }

    public var errorDescription: String? { message }
}

public func bridgeRequestID(from data: Data) -> String? {
    guard
        let object = try? JSONSerialization.jsonObject(with: data),
        let dictionary = object as? [String: Any]
    else {
        return nil
    }
    return dictionary["id"] as? String
}
