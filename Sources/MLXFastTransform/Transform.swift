import Foundation
import MLXFastCore
#if canImport(Darwin)
import Darwin
#endif

public struct TransformOptions: Equatable {
    public let referencePath: String
    public let outputPath: String

    public init(referencePath: String, outputPath: String) {
        self.referencePath = referencePath
        self.outputPath = outputPath
    }
}

public struct TransformReport: Equatable {
    public let referencePath: String
    public let outputPath: String
    public let denseTensorCount: Int
    public let denseShardCount: Int
    public let configPath: String
    public let indexPath: String

    public init(
        referencePath: String,
        outputPath: String,
        denseTensorCount: Int,
        denseShardCount: Int,
        configPath: String,
        indexPath: String
    ) {
        self.referencePath = referencePath
        self.outputPath = outputPath
        self.denseTensorCount = denseTensorCount
        self.denseShardCount = denseShardCount
        self.configPath = configPath
        self.indexPath = indexPath
    }
}

enum TransformModelFamily: Equatable {
    case gemma4
    case laguna
}

public enum SwiftTransform {
    static let textTowerPrefix = "language_model."

    public static func run(_ options: TransformOptions) throws -> TransformReport {
        try run(
            options,
            beforeSidecarGeneration: nil,
            beforeSourceRevalidation: nil
        )
    }

    static func run(
        _ options: TransformOptions,
        beforeSidecarGeneration: (() throws -> Void)? = nil,
        beforeSourceRevalidation: (() throws -> Void)?
    ) throws -> TransformReport {
        let referenceDirectory = canonicalURL(
            try findReferenceDirectory(URL(fileURLWithPath: options.referencePath))
        )
        let outputDirectory = canonicalURL(URL(fileURLWithPath: options.outputPath))
        try validateDistinctDirectories(
            referenceDirectory: referenceDirectory,
            outputDirectory: outputDirectory
        )
        var outputIsDirectory = ObjCBool(false)
        if FileManager.default.fileExists(
            atPath: outputDirectory.path,
            isDirectory: &outputIsDirectory
        ), !outputIsDirectory.boolValue {
            throw MLXFastError.invalidInput(
                "transform output exists and is not a directory: \(outputDirectory.path)"
            )
        }

        let referenceConfigPath = referenceDirectory.appendingPathComponent("config.json")
        try requireFile(
            referenceConfigPath.path,
            description: "reference checkpoint config"
        )
        let sourceConfigRoot = try loadReferenceConfigRoot(referenceConfigPath)
        let modelFamily = try detectModelFamily(sourceConfigRoot: sourceConfigRoot)
        let runtimeConfigData = try makeRuntimeConfigData(
            sourceConfigRoot: sourceConfigRoot,
            family: modelFamily
        )
        let metadataSnapshot = try captureMetadataFiles(from: referenceDirectory)

        let index = try loadIndex(referenceDirectory)
        let indexSnapshot = try index.canonicalData()
        let validatedHeaders = try validateCheckpointIndex(
            index,
            referenceDirectory: referenceDirectory
        )
        let textKeys = Set(
            index.weightMap.keys.filter { isSelectedTextTowerKey($0, family: modelFamily) }
        )
        guard !textKeys.isEmpty else {
            throw MLXFastError.invalidInput("checkpoint index contains no text-tower tensors")
        }

        let routerKeys = modelFamily == .laguna
            ? Set(textKeys.filter { $0.hasSuffix(".mlp.gate.weight") })
            : Set<String>()
        let copiedTextKeys = textKeys.subtracting(routerKeys)
        let textKeysByShard = Dictionary(grouping: copiedTextKeys) { key in
            index.weightMap[key] ?? ""
        }
        var totalTensorByteCount = 0
        for key in copiedTextKeys.sorted() {
            guard let shardName = index.weightMap[key],
                  let info = validatedHeaders[shardName]?.tensors[key]
            else {
                throw MLXFastError.invalidInput(
                    "missing validated tensor metadata for \(key)"
                )
            }
            let (nextTotal, overflow) = totalTensorByteCount.addingReportingOverflow(
                info.byteCount
            )
            guard !overflow else {
                throw MLXFastError.invalidInput(
                    "transformed tensor byte count overflows Int"
                )
            }
            totalTensorByteCount = nextTotal
        }

        if modelFamily == .laguna {
            // Fail before the multi-GB copy if the selected tensor set is
            // structurally inconsistent with the quantization spec the
            // emitted config.json declares (the runtime re-validates the
            // full geometry against LagunaConfig at load).
            try LagunaCheckpointValidation.validateSelectedTensors(
                selectedKeys: textKeys,
                index: index,
                headers: validatedHeaders,
                quantization: LagunaCheckpointValidation.quantizationSpec(
                    fromConfigRoot: sourceConfigRoot
                )
            )
        }

        let fileManager = FileManager.default
        let stagingDirectory = outputDirectory.deletingLastPathComponent().appendingPathComponent(
            ".\(outputDirectory.lastPathComponent).mlxfast-transform-\(UUID().uuidString)",
            isDirectory: true
        )
        try fileManager.createDirectory(
            at: stagingDirectory.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try fileManager.createDirectory(at: stagingDirectory, withIntermediateDirectories: false)
        var installed = false
        defer {
            if !installed {
                try? fileManager.removeItem(at: stagingDirectory)
            }
        }

        var copiedTensors = 0
        var stagedHeaders: [String: SafetensorsHeader] = [:]
        for shardName in textKeysByShard.keys.sorted() {
            let source = referenceDirectory.appendingPathComponent(shardName)
            let destination = stagingDirectory.appendingPathComponent(shardName)
            guard let header = validatedHeaders[shardName] else {
                throw MLXFastError.invalidInput("missing validated header for checkpoint shard \(shardName)")
            }
            let selectedNames = textKeysByShard[shardName, default: []].sorted()
            if Set(selectedNames) == Set(header.tensors.keys) {
                // Poolside's reference is already text-only. Preserve the
                // byte-identical shard and use an APFS copy-on-write clone
                // when source/output share a volume; fall back to a normal
                // independent file copy elsewhere. Never publish a symlink.
                try cloneOrCopyShard(from: source, to: destination)
                copiedTensors += selectedNames.count
            } else {
                copiedTensors += try Safetensors.copySubset(
                    from: source,
                    to: destination,
                    tensorNames: selectedNames,
                    validatedHeader: header
                )
            }
            stagedHeaders[shardName] = try Safetensors.readHeader(destination)
        }

        try beforeSidecarGeneration?()
        let emptyMetadata = GeneratedAffineMetadataReport(weightMap: [:], tensorByteCount: 0)
        let generatedProjectionMetadata: GeneratedAffineMetadataReport
        let generatedTiedHeadMetadata: GeneratedAffineMetadataReport
        let generatedRouterMetadata: GeneratedAffineMetadataReport
        switch modelFamily {
        case .gemma4:
            generatedProjectionMetadata = try AffineMetadataCoding.writeProjectionSidecar(
                sourceDirectory: stagingDirectory,
                index: index,
                sourceHeaders: stagedHeaders,
                selectedKeys: textKeys,
                destinationDirectory: stagingDirectory
            )
            generatedTiedHeadMetadata = try TiedHeadMetadataCoding.writeSidecar(
                sourceDirectory: stagingDirectory,
                index: index,
                sourceHeaders: stagedHeaders,
                selectedKeys: textKeys,
                destinationDirectory: stagingDirectory
            )
            generatedRouterMetadata = emptyMetadata
        case .laguna:
            generatedProjectionMetadata = emptyMetadata
            generatedTiedHeadMetadata = emptyMetadata
            generatedRouterMetadata = try writeRouterSidecar(
                sourceDirectory: referenceDirectory,
                index: index,
                sourceHeaders: validatedHeaders,
                routerKeys: routerKeys,
                destinationDirectory: stagingDirectory
            )
        }
        let (projectionOutputByteCount, projectionSizeOverflow) =
            totalTensorByteCount.addingReportingOverflow(
                generatedProjectionMetadata.tensorByteCount
            )
        let (tiedOutputByteCount, tiedHeadSizeOverflow) =
            projectionOutputByteCount.addingReportingOverflow(
                generatedTiedHeadMetadata.tensorByteCount
            )
        let (outputTensorByteCount, routerSizeOverflow) =
            tiedOutputByteCount.addingReportingOverflow(generatedRouterMetadata.tensorByteCount)
        guard !projectionSizeOverflow, !tiedHeadSizeOverflow, !routerSizeOverflow else {
            throw MLXFastError.invalidInput("transformed tensor byte count overflows Int")
        }
        let generatedWeightMap = generatedProjectionMetadata.weightMap
            .merging(generatedTiedHeadMetadata.weightMap) { _, _ in
                preconditionFailure("generated metadata tensor names collide")
            }
            .merging(generatedRouterMetadata.weightMap) { _, _ in
                preconditionFailure("generated metadata tensor names collide")
            }

        try writeMetadataFiles(metadataSnapshot, to: stagingDirectory)
        try index.writeStripped(
            to: stagingDirectory.appendingPathComponent("model.safetensors.index.json"),
            keeping: copiedTextKeys,
            totalTensorByteCount: outputTensorByteCount,
            additionalWeightMap: generatedWeightMap
        )

        try runtimeConfigData.write(
            to: stagingDirectory.appendingPathComponent("config.json")
        )
        try beforeSourceRevalidation?()
        try validateConfigAndIndexSnapshot(
            referenceDirectory: referenceDirectory,
            referenceConfigPath: referenceConfigPath,
            runtimeConfigData: runtimeConfigData,
            indexSnapshot: indexSnapshot,
            metadataSnapshot: metadataSnapshot
        )
        for shardName in validatedHeaders.keys.sorted() {
            guard let header = validatedHeaders[shardName] else {
                throw MLXFastError.invalidInput(
                    "missing validated header for checkpoint shard \(shardName)"
                )
            }
            try Safetensors.validateSourceIdentity(
                referenceDirectory.appendingPathComponent(shardName),
                against: header
            )
        }
        try validateConfigAndIndexSnapshot(
            referenceDirectory: referenceDirectory,
            referenceConfigPath: referenceConfigPath,
            runtimeConfigData: runtimeConfigData,
            indexSnapshot: indexSnapshot,
            metadataSnapshot: metadataSnapshot
        )
        try installTransformedDirectory(
            stagingDirectory,
            at: outputDirectory,
            fileManager: fileManager
        )
        installed = true

        let indexPath = outputDirectory.appendingPathComponent("model.safetensors.index.json")
        let configPath = outputDirectory.appendingPathComponent("config.json")

        return TransformReport(
            referencePath: referenceDirectory.path,
            outputPath: outputDirectory.path,
            denseTensorCount: copiedTensors
                + generatedProjectionMetadata.tensorCount
                + generatedTiedHeadMetadata.tensorCount
                + generatedRouterMetadata.tensorCount,
            denseShardCount: textKeysByShard.count
                + generatedProjectionMetadata.shardCount
                + generatedTiedHeadMetadata.shardCount
                + generatedRouterMetadata.shardCount,
            configPath: configPath.path,
            indexPath: indexPath.path
        )
    }

    private struct RouterTensor {
        let name: String
        let dtype: String
        let shape: [Int]
        let data: Data
    }

    private static func writeRouterSidecar(
        sourceDirectory: URL,
        index: CheckpointIndex,
        sourceHeaders: [String: SafetensorsHeader],
        routerKeys: Set<String>,
        destinationDirectory: URL
    ) throws -> GeneratedAffineMetadataReport {
        let shardName = "mlxfast-router-highbyte.safetensors"
        var tensors: [RouterTensor] = []
        for name in routerKeys.sorted() {
            guard let shard = index.weightMap[name],
                  let header = sourceHeaders[shard],
                  let info = header.tensors[name],
                  info.dtype == "BF16", info.shape == [256, 2_048]
            else {
                throw MLXFastError.invalidInput("invalid Laguna router tensor \(name)")
            }
            let bytes = try tensorBytes(
                named: name,
                sourceDirectory: sourceDirectory,
                index: index,
                sourceHeaders: sourceHeaders
            )
            var payload = Data()
            var offsets = Data(capacity: 1_024)
            payload.reserveCapacity(256 * 3_088)
            for row in 0..<256 {
                let base = row * 4_096
                var seen = [Bool](repeating: false, count: 256)
                for column in 0..<2_048 {
                    seen[Int(bytes[base + 2 * column + 1])] = true
                }
                let palette = seen.indices.filter { seen[$0] }
                guard payload.count < 0x8000_0000 else {
                    throw MLXFastError.invalidInput("router payload exceeds UInt31 capacity")
                }
                let fallback = palette.count > 16
                var tagged = (UInt32(payload.count) | (fallback ? 0x8000_0000 : 0)).littleEndian
                withUnsafeBytes(of: &tagged) { offsets.append(contentsOf: $0) }
                if fallback {
                    payload.append(bytes.subdata(in: base..<(base + 4_096)))
                    continue
                }
                var paletteIndex = [UInt8](repeating: 0, count: 256)
                for (position, value) in palette.enumerated() {
                    paletteIndex[value] = UInt8(position)
                }
                for column in 0..<2_048 {
                    payload.append(bytes[base + 2 * column])
                }
                for column in stride(from: 0, to: 2_048, by: 2) {
                    let low = paletteIndex[Int(bytes[base + 2 * column + 1])]
                    let high = paletteIndex[Int(bytes[base + 2 * column + 3])]
                    payload.append(low | (high << 4))
                }
                payload.append(contentsOf: palette.map { UInt8($0) })
                if palette.count < 16 {
                    payload.append(contentsOf: repeatElement(UInt8(0), count: 16 - palette.count))
                }
            }
            tensors.append(RouterTensor(name: name, dtype: "U8", shape: [payload.count], data: payload))
            tensors.append(RouterTensor(
                name: name + "_row_offsets",
                dtype: "U32",
                shape: [256],
                data: offsets
            ))
        }

        var headerObject: [String: Any] = [
            "__metadata__": ["format": "mlxfast-router-highbyte-v1"]
        ]
        var cursor = 0
        for tensor in tensors {
            headerObject[tensor.name] = [
                "dtype": tensor.dtype,
                "shape": tensor.shape,
                "data_offsets": [cursor, cursor + tensor.data.count],
            ]
            cursor += tensor.data.count
        }
        var header = try JSONSerialization.data(withJSONObject: headerObject, options: [.sortedKeys])
        while !header.count.isMultiple(of: 8) { header.append(0x20) }
        let destination = destinationDirectory.appendingPathComponent(shardName)
        try Data().write(to: destination, options: [.withoutOverwriting])
        let output = try FileHandle(forWritingTo: destination)
        defer { try? output.close() }
        var headerLength = UInt64(header.count).littleEndian
        try output.write(contentsOf: Data(bytes: &headerLength, count: 8))
        try output.write(contentsOf: header)
        for tensor in tensors { try output.write(contentsOf: tensor.data) }
        try output.synchronize()
        return GeneratedAffineMetadataReport(
            weightMap: Dictionary(uniqueKeysWithValues: tensors.map { ($0.name, shardName) }),
            tensorByteCount: cursor
        )
    }

    private static func tensorBytes(
        named name: String,
        sourceDirectory: URL,
        index: CheckpointIndex,
        sourceHeaders: [String: SafetensorsHeader]
    ) throws -> Data {
        guard let shard = index.weightMap[name],
              let header = sourceHeaders[shard],
              let info = header.tensors[name]
        else {
            throw MLXFastError.invalidInput("missing validated tensor metadata for \(name)")
        }
        let handle = try FileHandle(forReadingFrom: sourceDirectory.appendingPathComponent(shard))
        defer { try? handle.close() }
        try handle.seek(toOffset: header.dataBaseOffset + UInt64(info.dataStart))
        let bytes = handle.readData(ofLength: info.byteCount)
        guard bytes.count == info.byteCount else {
            throw MLXFastError.invalidInput("short read while encoding router \(name)")
        }
        return bytes
    }

    private static func loadIndex(_ referenceDirectory: URL) throws -> CheckpointIndex {
        let indexPath = referenceDirectory.appendingPathComponent("model.safetensors.index.json")
        if FileManager.default.fileExists(atPath: indexPath.path) {
            return try CheckpointIndex.load(from: indexPath)
        }
        return try CheckpointIndex.buildFromSafetensors(in: referenceDirectory)
    }

    private static func validateCheckpointIndex(
        _ index: CheckpointIndex,
        referenceDirectory: URL
    ) throws -> [String: SafetensorsHeader] {
        guard !index.weightMap.isEmpty else {
            throw MLXFastError.invalidInput("checkpoint index contains no tensors")
        }

        let keysByShard = Dictionary(grouping: index.weightMap.keys.sorted()) { key in
            index.weightMap[key] ?? ""
        }
        var headersByShard: [String: SafetensorsHeader] = [:]
        for shardName in keysByShard.keys.sorted() {
            try validateSafetensorsShardName(shardName, context: "checkpoint index")

            let shardURL = referenceDirectory.appendingPathComponent(shardName)
            try requireFile(shardURL.path, description: "checkpoint shard \(shardName)")
            let header = try Safetensors.readHeader(shardURL)
            headersByShard[shardName] = header

            for key in keysByShard[shardName, default: []].sorted() {
                guard let info = header.tensors[key] else {
                    throw MLXFastError.invalidInput(
                        "checkpoint index lists tensor \(key) in \(shardName), but the shard header does not contain it"
                    )
                }
                let dtype = try TensorDType.parse(info.dtype)
                let expectedByteLength = try expectedTensorByteCount(
                    name: key,
                    dtype: dtype,
                    shape: info.shape
                )
                guard info.byteCount == expectedByteLength else {
                    throw MLXFastError.invalidInput(
                        "checkpoint tensor \(key) byte length \(info.byteCount) does not match dtype \(info.dtype) and shape \(info.shape) expected \(expectedByteLength)"
                    )
                }
                // readHeader validated every data range against the opened
                // target descriptor. Do not recheck via the shard pathname:
                // FileManager reports a symlink's own size, not its target's.
                guard info.dataStart >= 0, info.byteCount > 0 else {
                    throw MLXFastError.invalidInput(
                        "checkpoint tensor \(key) has an empty or invalid byte range"
                    )
                }
            }
        }
        return headersByShard
    }

    private static func canonicalURL(_ url: URL) -> URL {
        url.standardizedFileURL.resolvingSymlinksInPath()
    }

    static func validateDistinctDirectories(
        referenceDirectory: URL,
        outputDirectory: URL,
        workingDirectory: URL = URL(
            fileURLWithPath: FileManager.default.currentDirectoryPath,
            isDirectory: true
        )
    ) throws {
        guard referenceDirectory.path != outputDirectory.path else {
            throw MLXFastError.invalidInput(
                "transform reference and output directories must be different: \(referenceDirectory.path)"
            )
        }
        let outputPrefix = outputDirectory.path == "/" ? "/" : outputDirectory.path + "/"
        guard !referenceDirectory.path.hasPrefix(outputPrefix) else {
            throw MLXFastError.invalidInput(
                "transform output directory cannot contain the reference directory: \(outputDirectory.path)"
            )
        }
        let referencePrefix = referenceDirectory.path == "/"
            ? "/"
            : referenceDirectory.path + "/"
        guard !outputDirectory.path.hasPrefix(referencePrefix) else {
            throw MLXFastError.invalidInput(
                "transform output directory cannot be inside the reference directory: \(outputDirectory.path)"
            )
        }

        let canonicalWorkingDirectory = canonicalURL(workingDirectory)
        guard canonicalWorkingDirectory.path != outputDirectory.path,
              !canonicalWorkingDirectory.path.hasPrefix(outputPrefix)
        else {
            throw MLXFastError.invalidInput(
                "transform output directory cannot contain the current working directory: \(outputDirectory.path)"
            )
        }
    }

    private static func installTransformedDirectory(
        _ stagedDirectory: URL,
        at outputDirectory: URL,
        fileManager: FileManager
    ) throws {
        if fileManager.fileExists(atPath: outputDirectory.path) {
            _ = try fileManager.replaceItemAt(outputDirectory, withItemAt: stagedDirectory)
        } else {
            try fileManager.moveItem(at: stagedDirectory, to: outputDirectory)
        }
    }

    private static func findReferenceDirectory(_ base: URL) throws -> URL {
        if FileManager.default.fileExists(
            atPath: base.appendingPathComponent("config.json").path
        ) {
            return base
        }

        guard let enumerator = FileManager.default.enumerator(
            at: base,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) else {
            throw MLXFastError.missingFile("reference path not found at \(base.path)")
        }

        for case let url as URL in enumerator {
            if url.lastPathComponent == "config.json" {
                return url.deletingLastPathComponent()
            }
        }

        throw MLXFastError.missingFile(
            "no config.json found under \(base.path); place the pinned reference checkpoint there"
        )
    }

    static func isTextTowerKey(_ key: String) -> Bool {
        key.hasPrefix(textTowerPrefix)
    }

    /// Poolside Laguna is already text-only and uses runtime-native
    /// `model.*` / `lm_head.*` names. Legacy Gemma retains the
    /// `language_model.*` selection. Precomputed rotary tables are omitted.
    static func isSelectedTextTowerKey(_ key: String, family: TransformModelFamily) -> Bool {
        switch family {
        case .gemma4:
            return isTextTowerKey(key)
        case .laguna:
            guard key.hasPrefix("model.") || key.hasPrefix("lm_head.") else {
                return false
            }
            return !key.contains("rotary_emb.inv_freq")
        }
    }

    private static func captureMetadataFiles(from source: URL) throws -> [String: Data] {
        let files = try FileManager.default.contentsOfDirectory(
            at: source,
            includingPropertiesForKeys: [.isRegularFileKey, .isSymbolicLinkKey]
        )
        var snapshot: [String: Data] = [:]
        for file in files.sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) {
            if file.lastPathComponent == "model.safetensors.index.json" || file.lastPathComponent == "config.json" {
                continue
            }
            if shouldCopyMetadataFile(file) {
                let values = try file.resourceValues(
                    forKeys: [.isRegularFileKey, .isSymbolicLinkKey]
                )
                guard values.isRegularFile == true, values.isSymbolicLink != true else {
                    throw MLXFastError.invalidInput(
                        "reference metadata is not a regular file: \(file.path)"
                    )
                }
                snapshot[file.lastPathComponent] = try Data(contentsOf: file)
            }
        }
        return snapshot
    }

    private static func writeMetadataFiles(
        _ snapshot: [String: Data],
        to destination: URL
    ) throws {
        for name in snapshot.keys.sorted() {
            try snapshot[name]?.write(to: destination.appendingPathComponent(name))
        }
    }

    private static func shouldCopyMetadataFile(_ url: URL) -> Bool {
        let name = url.lastPathComponent
        if name.hasSuffix(".safetensors") {
            return false
        }
        switch url.pathExtension {
        case "json", "model", "tiktoken", "txt":
            return true
        default:
            return name == "tokenizer" || name == "vocab"
        }
    }

    private static func cloneOrCopyShard(from source: URL, to destination: URL) throws {
        #if canImport(Darwin)
        let cloned = source.path.withCString { sourcePath in
            destination.path.withCString { destinationPath in
                clonefile(sourcePath, destinationPath, 0) == 0
            }
        }
        if !cloned {
            if FileManager.default.fileExists(atPath: destination.path) {
                try FileManager.default.removeItem(at: destination)
            }
            try FileManager.default.copyItem(at: source, to: destination)
        }
        #else
        if FileManager.default.fileExists(atPath: destination.path) {
            try FileManager.default.removeItem(at: destination)
        }
        try FileManager.default.copyItem(at: source, to: destination)
        #endif
        let values = try destination.resourceValues(
            forKeys: [.isRegularFileKey, .isSymbolicLinkKey]
        )
        guard values.isRegularFile == true, values.isSymbolicLink != true else {
            throw MLXFastError.invalidInput(
                "transformed shard copy is not an independent regular file: \(destination.path)"
            )
        }
    }

    private static func loadReferenceConfigRoot(_ sourceConfigPath: URL) throws -> [String: Any] {
        let data = try Data(contentsOf: sourceConfigPath)
        let object = try JSONSerialization.jsonObject(with: data)
        guard let root = object as? [String: Any] else {
            throw MLXFastError.invalidInput("reference config.json must be a JSON object")
        }
        return root
    }

    static func detectModelFamily(
        sourceConfigRoot root: [String: Any]
    ) throws -> TransformModelFamily {
        if root["text_config"] is [String: Any] {
            return .gemma4
        }
        if let modelType = root["model_type"] as? String, modelType == "laguna" {
            return .laguna
        }
        throw MLXFastError.invalidInput(
            "reference config.json is missing text_config and does not declare model_type laguna"
        )
    }

    static func makeRuntimeConfigData(sourceConfigPath: URL) throws -> Data {
        let root = try loadReferenceConfigRoot(sourceConfigPath)
        return try makeRuntimeConfigData(
            sourceConfigRoot: root,
            family: detectModelFamily(sourceConfigRoot: root)
        )
    }

    /// Writes the runtime's `config.json`.
    ///
    /// Gemma 4 (legacy): the source checkpoint's `text_config` fields
    /// flattened to the top level (the schema the archived Gemma 4 runtime
    /// read), plus the
    /// checkpoint-wide `quantization` block -- no vision or audio config, no
    /// architecture/tokenizer metadata duplicated from
    /// `tokenizer_config.json`.
    ///
    /// Laguna: the source config is already the flat schema
    /// `LagunaConfig.load` parses (per docs/laguna-weight-contract.md the
    /// transform may copy the source fields directly), so it is passed
    /// through minus the empty multimodal `vision_config` stub. Its matching
    /// NVFP4 4-bit group-16 `quantization` and `quantization_config` blocks are
    /// both required and preserved.
    static func makeRuntimeConfigData(
        sourceConfigRoot root: [String: Any],
        family: TransformModelFamily
    ) throws -> Data {
        var runtimeConfig: [String: Any]
        switch family {
        case .gemma4:
            guard let textConfig = root["text_config"] as? [String: Any] else {
                throw MLXFastError.invalidInput("reference config.json is missing text_config")
            }
            runtimeConfig = textConfig
            if let quantization = root["quantization"] {
                runtimeConfig["quantization"] = quantization
            } else if let quantizationConfig = root["quantization_config"] {
                runtimeConfig["quantization"] = quantizationConfig
            }
        case .laguna:
            _ = try LagunaCheckpointValidation.quantizationSpec(fromConfigRoot: root)
            runtimeConfig = root
            runtimeConfig["vision_config"] = nil
        }

        return try JSONSerialization.data(
            withJSONObject: runtimeConfig,
            options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        )
    }

    private static func validateConfigAndIndexSnapshot(
        referenceDirectory: URL,
        referenceConfigPath: URL,
        runtimeConfigData: Data,
        indexSnapshot: Data,
        metadataSnapshot: [String: Data]
    ) throws {
        guard try makeRuntimeConfigData(sourceConfigPath: referenceConfigPath)
            == runtimeConfigData
        else {
            throw MLXFastError.invalidInput(
                "reference config changed while transform was running"
            )
        }
        guard try loadIndex(referenceDirectory).canonicalData() == indexSnapshot else {
            throw MLXFastError.invalidInput(
                "checkpoint index changed while transform was running"
            )
        }
        guard try captureMetadataFiles(from: referenceDirectory) == metadataSnapshot else {
            throw MLXFastError.invalidInput(
                "reference tokenizer metadata changed while transform was running"
            )
        }
    }
}
