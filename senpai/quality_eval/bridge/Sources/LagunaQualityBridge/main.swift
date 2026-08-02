import Foundation
import Darwin
import LagunaQualityBridgeProtocol
import LagunaQualityMetalShim
import MLX
import MLXFastModel
import MLXLMCommon

@main
enum LagunaQualityBridgeCLI {
    static func main() {
        do {
            let options = try BridgeOptions(arguments: Array(CommandLine.arguments.dropFirst()))
            if options.showHelp {
                print(BridgeOptions.usage)
                return
            }
            if options.fullLogits {
                // Sampling and PPL need probability-correct full-vocabulary
                // logits. Greedy quality phases omit this flag and exercise
                // the candidate's submitted/default ranked decode head.
                setenv("DARKBLOOM_LM_HEAD_PRUNE", "0", 1)
            }
            try run(options: options)
        } catch {
            fputs("laguna-quality-bridge: \(errorDescription(error))\n", stderr)
            exit(2)
        }
    }

    private static func run(options: BridgeOptions) throws {
        guard let weightsPath = options.weightsPath else {
            throw CLIError("missing required --weights PATH")
        }
        try configureMetallib(options.metallibPath)

        fputs("laguna-quality-bridge: loading \(weightsPath)\n", stderr)
        let config = try LagunaConfig.load(from: weightsPath)
        let loader = try LagunaWeightLoader(weightsPath: weightsPath)
        let weightCache = LagunaRuntimeWeightCache(loader: loader, config: config)
        let model = try weightCache.requireLibraryModel()
        let engine = LagunaQualityEngine(
            model: model,
            config: config,
            fullLogits: options.fullLogits
        )
        let output = JSONLineOutput()

        try output.write(
            .ready(
                model: config.modelType,
                vocabSize: config.vocabSize,
                maxPositionEmbeddings: config.maxPositionEmbeddings
            )
        )
        fputs("laguna-quality-bridge: ready\n", stderr)

        while let line = readLine(strippingNewline: true) {
            guard !line.trimmingCharacters(in: .whitespaces).isEmpty else {
                continue
            }
            let data = Data(line.utf8)
            let id = bridgeRequestID(from: data)
            do {
                let request = try JSONDecoder().decode(BridgeRequest.self, from: data)
                let validated = try request.validated(
                    vocabSize: config.vocabSize,
                    maxPositionEmbeddings: config.maxPositionEmbeddings
                )
                try output.write(try engine.handle(validated))
            } catch {
                try output.write(
                    .failure(id: id, error: errorDescription(error))
                )
            }
        }
    }

    private static func requireFile(
        _ path: String,
        description: String
    ) throws {
        var isDirectory = ObjCBool(false)
        guard
            FileManager.default.fileExists(
                atPath: path,
                isDirectory: &isDirectory
            ),
            !isDirectory.boolValue
        else {
            throw CLIError("\(description) missing at \(path)")
        }
    }

    private static func configureMetallib(_ requestedPath: String?) throws {
        if let requestedPath {
            try requireFile(requestedPath, description: "MLX metallib")
            requestedPath.withCString(laguna_quality_set_metallib_path)
            return
        }

        let executable = URL(
            fileURLWithPath: CommandLine.arguments[0],
            relativeTo: URL(
                fileURLWithPath: FileManager.default.currentDirectoryPath,
                isDirectory: true
            )
        ).standardizedFileURL
        let colocated = executable
            .deletingLastPathComponent()
            .appendingPathComponent("mlx.metallib")
        guard FileManager.default.fileExists(atPath: colocated.path) else {
            throw CLIError(
                "MLX metallib is not next to the bridge binary; pass --metallib PATH"
            )
        }
    }
}

private final class LagunaQualityEngine {
    private let model: LagunaRuntimeModel
    private let config: LagunaConfig
    private let fullLogits: Bool

    init(model: LagunaRuntimeModel, config: LagunaConfig, fullLogits: Bool) {
        self.model = model
        self.config = config
        self.fullLogits = fullLogits
    }

    func handle(_ request: ValidatedBridgeRequest) throws -> BridgeResponse {
        switch request {
        case .generate(let request):
            if !fullLogits && (request.temperature != 0 || request.minTokens != 0) {
                throw BridgeProtocolError(
                    "ranked head supports only unmasked greedy generation; use --full-logits"
                )
            }
            let result = try generate(request)
            return .generated(
                id: request.id,
                tokenIDs: result.tokens,
                finishReason: result.finishReason
            )
        case .logprobs(let request):
            guard fullLogits else {
                throw BridgeProtocolError(
                    "prompt logprobs require --full-logits"
                )
            }
            return .logprobs(
                id: request.id,
                tokenLogprobs: try tokenLogprobs(request)
            )
        }
    }

    private func generate(
        _ request: ValidatedGenerateRequest
    ) throws -> (tokens: [Int], finishReason: String) {
        guard request.maxTokens > 0 else {
            return ([], "length")
        }

        let cache = model.newCache(parameters: nil)
        var logits = model(
            inputIDs(request.promptTokenIDs),
            cache: cache
        )
        let sampler = makeRowSampler(
            temperature: request.temperature,
            topP: request.topP,
            topK: request.topK,
            seed: request.seed
        )
        let stopTokens = Set(request.stopTokenIDs)
        let stopMask = makeStopMask(
            tokenIDs: request.stopTokenIDs,
            vocabSize: config.vocabSize
        )
        var generated: [Int] = []
        generated.reserveCapacity(request.maxTokens)

        for step in 0..<request.maxTokens {
            let effectiveLogits: MLXArray
            if step < request.minTokens, let stopMask {
                effectiveLogits = logits + stopMask
            } else {
                effectiveLogits = logits
            }
            let token = Int(
                sampler(effectiveLogits).item(Int32.self)
            )
            if stopTokens.contains(token), step >= request.minTokens {
                return (generated, "stop")
            }
            generated.append(token)
            if step + 1 < request.maxTokens {
                logits = model(inputIDs([token]), cache: cache)
            }
        }
        return (generated, "length")
    }

    private func tokenLogprobs(
        _ request: ValidatedLogprobsRequest
    ) throws -> [Double] {
        guard request.scoreStart < request.scoreEnd else {
            return []
        }

        let cache = model.newCache(parameters: nil)
        var logits = model(
            inputIDs(Array(request.promptTokenIDs[..<request.scoreStart])),
            cache: cache
        )
        var result: [Double] = []
        result.reserveCapacity(request.scoreEnd - request.scoreStart)

        for index in request.scoreStart..<request.scoreEnd {
            let target = request.promptTokenIDs[index]
            let floatLogits = logits.asType(.float32)
            let normalized = (
                floatLogits
                    - logSumExp(
                        floatLogits,
                        axis: -1,
                        keepDims: true
                    )
            )
            guard normalized.shape == [1, 1, config.vocabSize] else {
                throw BridgeProtocolError(
                    "full-logit scoring produced shape \(normalized.shape); expected [1, 1, \(config.vocabSize)]"
                )
            }
            let row = normalized.reshaped([config.vocabSize])
            result.append(Double(row[target].item(Float.self)))
            if index + 1 < request.scoreEnd {
                logits = model(inputIDs([target]), cache: cache)
            }
        }
        return result
    }

    /// Preserve the candidate's real batch-one generation path.
    private func inputIDs(_ tokens: [Int]) -> MLXArray {
        MLXArray(tokens.map(Int32.init), [1, tokens.count])
    }

    private func makeStopMask(
        tokenIDs: [Int],
        vocabSize: Int
    ) -> MLXArray? {
        guard !tokenIDs.isEmpty else {
            return nil
        }
        var values = [Float](repeating: 0, count: vocabSize)
        for token in tokenIDs {
            values[token] = -.infinity
        }
        return MLXArray(values)
    }
}

private struct BridgeOptions {
    let weightsPath: String?
    let metallibPath: String?
    let fullLogits: Bool
    let showHelp: Bool

    static let usage = """
        Usage:
          laguna-quality-bridge --weights PATH [--metallib PATH] [--full-logits]

        Loads one transformed Laguna model and serves JSONL requests on stdin.
        --full-logits disables the ranked argmax-only LM-head pruner for
        sampling and PPL; omit it to test submitted/default greedy behavior.
        stdout is reserved for JSONL responses; diagnostics go to stderr.
        """

    init(arguments: [String]) throws {
        if arguments == ["--help"] || arguments == ["-h"] {
            weightsPath = nil
            metallibPath = nil
            fullLogits = false
            showHelp = true
            return
        }

        var values: [String: String] = [:]
        var requestedFullLogits = false
        var index = 0
        while index < arguments.count {
            let name = arguments[index]
            if name == "--full-logits" {
                guard !requestedFullLogits else {
                    throw CLIError("duplicate option \(name)")
                }
                requestedFullLogits = true
                index += 1
                continue
            }
            guard ["--weights", "--metallib"].contains(name) else {
                throw CLIError("unexpected argument '\(name)'")
            }
            guard values[name] == nil else {
                throw CLIError("duplicate option \(name)")
            }
            guard index + 1 < arguments.count else {
                throw CLIError("\(name) requires a path")
            }
            values[name] = arguments[index + 1]
            index += 2
        }

        weightsPath = values["--weights"]
        metallibPath = values["--metallib"]
        fullLogits = requestedFullLogits
        showHelp = false
    }
}

private final class JSONLineOutput {
    private let encoder: JSONEncoder

    init() {
        encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    }

    func write(_ response: BridgeResponse) throws {
        var data = try encoder.encode(response)
        data.append(0x0A)
        try FileHandle.standardOutput.write(contentsOf: data)
    }
}

private struct CLIError: Error, LocalizedError {
    let message: String

    init(_ message: String) {
        self.message = message
    }

    var errorDescription: String? { message }
}

private func errorDescription(_ error: any Error) -> String {
    if let localized = error as? any LocalizedError,
        let description = localized.errorDescription
    {
        return description
    }
    return String(describing: error)
}
