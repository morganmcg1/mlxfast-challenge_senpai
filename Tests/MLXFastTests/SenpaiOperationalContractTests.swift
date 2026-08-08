import Foundation
import Testing

private struct OperationalCommandResult {
    let status: Int32
    let output: String
}

private func runOperationalCommand(
    _ executable: String,
    _ arguments: [String],
    in directory: URL
) throws -> OperationalCommandResult {
    let pipe = Pipe()
    let process = Process()
    process.executableURL = URL(fileURLWithPath: executable)
    process.arguments = arguments
    process.currentDirectoryURL = directory
    process.standardOutput = pipe
    process.standardError = pipe
    try process.run()
    process.waitUntilExit()
    return OperationalCommandResult(
        status: process.terminationStatus,
        output: String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
    )
}

private func writeOperationalFile(_ contents: String, to url: URL) throws {
    try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(),
        withIntermediateDirectories: true
    )
    try contents.write(to: url, atomically: true, encoding: .utf8)
}

@Test
func senpaiAssignmentScopeUsesTheCommittedBaseContract() throws {
    let fileManager = FileManager.default
    let repository = fileManager.temporaryDirectory.appendingPathComponent(
        "mlxfast-assignment-scope-\(UUID().uuidString)",
        isDirectory: true
    )
    try fileManager.createDirectory(at: repository, withIntermediateDirectories: true)
    defer { try? fileManager.removeItem(at: repository) }

    try writeOperationalFile(
        #"{"editablePaths":["allowed","exact.swift"]}"#,
        to: repository.appendingPathComponent("benchmark.json")
    )
    try writeOperationalFile("seed\n", to: repository.appendingPathComponent("allowed/seed.swift"))
    try writeOperationalFile("exact\n", to: repository.appendingPathComponent("exact.swift"))

    #expect(try runOperationalCommand("/usr/bin/git", ["init", "-q"], in: repository).status == 0)
    #expect(try runOperationalCommand("/usr/bin/git", ["add", "."], in: repository).status == 0)
    #expect(try runOperationalCommand(
        "/usr/bin/git",
        ["-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "base"],
        in: repository
    ).status == 0)
    let revision = try runOperationalCommand(
        "/usr/bin/git", ["rev-parse", "HEAD"], in: repository
    ).output.trimmingCharacters(in: .whitespacesAndNewlines)

    let checkout = URL(fileURLWithPath: fileManager.currentDirectoryPath)
    let validator = checkout.appendingPathComponent("senpai/validate-assignment-scope.sh").path

    for allowedPath in ["allowed/new.swift", "exact.swift"] {
        let result = try runOperationalCommand(
            "/bin/bash", [validator, revision, allowedPath], in: repository
        )
        #expect(result.status == 0, "\(allowedPath): \(result.output)")
    }

    for rejectedPath in [
        "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/common/metal_kernel.cpp",
        "../outside.swift",
    ] {
        let result = try runOperationalCommand(
            "/bin/bash", [validator, revision, rejectedPath], in: repository
        )
        #expect(result.status != 0, Comment(rawValue: rejectedPath))
    }

    // A working-tree contract edit cannot grant the assignment more scope.
    try writeOperationalFile(
        #"{"editablePaths":["allowed","exact.swift","outside"]}"#,
        to: repository.appendingPathComponent("benchmark.json")
    )
    let poisoned = try runOperationalCommand(
        "/bin/bash", [validator, revision, "outside/new.swift"], in: repository
    )
    #expect(poisoned.status != 0)

    let abbreviated = try runOperationalCommand(
        "/bin/bash", [validator, "HEAD", "allowed/new.swift"], in: repository
    )
    #expect(abbreviated.status == 2)

    let budget = checkout.appendingPathComponent("senpai/check-editable-budget.sh").path
    let withinBudget = try runOperationalCommand(
        "/bin/bash", [budget, revision], in: repository
    )
    #expect(withinBudget.status == 0, Comment(rawValue: withinBudget.output))

    try Data(repeating: 0, count: 524_289).write(
        to: repository.appendingPathComponent("allowed/oversized.swift")
    )
    let oversized = try runOperationalCommand(
        "/bin/bash", [budget, revision], in: repository
    )
    #expect(oversized.status != 0)
    #expect(oversized.output.contains("per-file limit"))
}

@Test
func senpaiOperationalGuidanceMatchesTheDeployedRankedPath() throws {
    let files = [
        "Sources/MLXFastHarness/LagunaRuntimeLocalIterate.swift",
        "Sources/MLXFastTrustedHarness/LagunaRuntimeLocalIterate.swift",
    ]
    for path in files {
        let source = try String(contentsOfFile: path, encoding: .utf8)
        #expect(
            !source.contains("emitLocalAcceptanceBandNotice"),
            Comment(rawValue: path)
        )
        #expect(
            !source.contains("must be CHUNKED across submissions"),
            Comment(rawValue: path)
        )
    }

    let agentGuide = try String(contentsOfFile: "AGENTS.md", encoding: .utf8)
    let task = try String(contentsOfFile: "TASK.md", encoding: .utf8)
    let readme = try String(contentsOfFile: "README.md", encoding: .utf8)
    for guidance in [agentGuide, task, readme] {
        #expect(guidance.contains("deployed ranked wrapper"))
        #expect(guidance.contains("0.95"))
    }

    let runner = try String(
        contentsOfFile: "research/run_upstream_equivalence.sh",
        encoding: .utf8
    )
    #expect(runner.contains("--filter lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled"))
    #expect(runner.contains("zero selected tests is not a pass"))
    #expect(runner.contains("promptTokenCount"))

    let assignment = try String(contentsOfFile: "senpai/assignment-template.md", encoding: .utf8)
    #expect(assignment.contains("validate-assignment-scope.sh"))
    #expect(assignment.contains("check-editable-budget.sh"))
    #expect(assignment.contains("advisor, student, or human operator"))

    let submissionGuides = [
        ("AGENTS.md", agentGuide),
        ("README.md", readme),
        (
            "senpai/program.md",
            try String(contentsOfFile: "senpai/program.md", encoding: .utf8)
        ),
        (
            "senpai/experiment-runbook.md",
            try String(contentsOfFile: "senpai/experiment-runbook.md", encoding: .utf8)
        ),
        ("senpai/assignment-template.md", assignment),
    ]
    for (path, guidance) in submissionGuides {
        #expect(
            guidance.contains("--model \"senpai\""),
            Comment(rawValue: path)
        )
        #expect(guidance.contains("explicit"), Comment(rawValue: path))
        #expect(guidance.contains("timeout"), Comment(rawValue: path))
    }
}

@Test
func senpaiSubmissionWatcherIsReadOnlyAndTested() throws {
    let checkout = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    let result = try runOperationalCommand(
        "/usr/bin/python3",
        ["senpai/test_watch_submission.py"],
        in: checkout
    )
    #expect(result.status == 0, Comment(rawValue: result.output))

    let watcher = try String(
        contentsOfFile: "senpai/watch-submission.py",
        encoding: .utf8
    )
    #expect(watcher.contains("method=\"POST\"") == false)
    #expect(watcher.contains("mlxfast submit") == false)

    for path in ["senpai/infra.md", "senpai/program.md"] {
        let guidance = try String(contentsOfFile: path, encoding: .utf8)
        #expect(guidance.contains("senpai/watch-submission.py"), Comment(rawValue: path))
        #expect(guidance.contains("student"), Comment(rawValue: path))
        #expect(guidance.contains("advisor"), Comment(rawValue: path))
    }
}
