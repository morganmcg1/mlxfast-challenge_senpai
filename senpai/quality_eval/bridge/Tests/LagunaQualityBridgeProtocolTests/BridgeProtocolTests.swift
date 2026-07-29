import Foundation
import LagunaQualityBridgeProtocol
import XCTest

final class BridgeProtocolTests: XCTestCase {
    func testGenerationDefaultsAndVLLMTopKSentinel() throws {
        let request = try decode(
            """
            {
              "id": "sample-1",
              "kind": "generate",
              "prompt_token_ids": [1, 2],
              "max_tokens": 4,
              "top_k": -1
            }
            """
        )

        guard case .generate(let validated) = try request.validated(
            vocabSize: 16,
            maxPositionEmbeddings: 32
        ) else {
            return XCTFail("expected generation request")
        }
        XCTAssertEqual(validated.temperature, 0)
        XCTAssertEqual(validated.topP, 1)
        XCTAssertEqual(validated.topK, 0)
        XCTAssertEqual(validated.seed, 0)
        XCTAssertEqual(validated.stopTokenIDs, [])
    }

    func testLogprobsDefaultsScoreEndToPromptLength() throws {
        let request = try decode(
            """
            {
              "id": "ppl-1",
              "kind": "logprobs",
              "prompt_token_ids": [3, 4, 5],
              "score_start": 2
            }
            """
        )

        guard case .logprobs(let validated) = try request.validated(
            vocabSize: 16,
            maxPositionEmbeddings: 32
        ) else {
            return XCTFail("expected logprobs request")
        }
        XCTAssertEqual(validated.scoreStart, 2)
        XCTAssertEqual(validated.scoreEnd, 3)
    }

    func testRejectsOutOfRangeToken() throws {
        let request = BridgeRequest(
            id: "bad-token",
            kind: .generate,
            promptTokenIDs: [16],
            maxTokens: 1
        )

        XCTAssertThrowsError(
            try request.validated(
                vocabSize: 16,
                maxPositionEmbeddings: 32
            )
        ) { error in
            XCTAssertEqual(
                (error as? BridgeProtocolError)?.message,
                "prompt_token_ids[0]=16 is outside 0..<16"
            )
        }
    }

    func testRejectsGenerationBeyondContextWindow() throws {
        let request = BridgeRequest(
            id: "too-long",
            kind: .generate,
            promptTokenIDs: [1, 2, 3],
            maxTokens: 2
        )

        XCTAssertThrowsError(
            try request.validated(
                vocabSize: 16,
                maxPositionEmbeddings: 4
            )
        )
    }

    func testErrorResponseOmitsUnrelatedFields() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(
            BridgeResponse.failure(id: "bad", error: "invalid")
        )
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )

        XCTAssertEqual(object["id"] as? String, "bad")
        XCTAssertEqual(object["ok"] as? Bool, false)
        XCTAssertEqual(object["error"] as? String, "invalid")
        XCTAssertNil(object["token_ids"])
    }

    func testRecoversStringIDFromMalformedRequest() throws {
        let data = Data(#"{"id":"request-7","kind":12}"#.utf8)
        XCTAssertEqual(bridgeRequestID(from: data), "request-7")
    }

    private func decode(_ json: String) throws -> BridgeRequest {
        try JSONDecoder().decode(BridgeRequest.self, from: Data(json.utf8))
    }
}
