#!/usr/bin/env python3
"""Audit the top-15 study artifacts and build deterministic report inputs.

The default ``--check`` mode never writes. ``--write`` atomically emits
``report-data.json`` and ``checksums.sha256`` beside this script. The builder
audits the primary cohort, the separate negative controls, and the isolated
extended-AIME diagnostics. It does not invoke the benchmark, quality
evaluator, network, or model binaries.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parents[2]
MANIFEST_PATH = SCRIPT_DIR / "candidates.json"
CONTROL_DEFINITION_PATH = SCRIPT_DIR / "negative-controls.json"
CONTROL_RUN_PATH = SCRIPT_DIR / "control-run.json"
EXTENDED_AIME_RUNNER_PATH = SCRIPT_DIR / "run-extended-aime.py"
EXTENDED_AIME_IDS_PATH = SCRIPT_DIR / "extended-aime-ids.json"
RUNNER_PATH = SCRIPT_DIR / "run-study.sh"
WRAPPER_PATH = SCRIPT_DIR / "quality-bridge-wrapper.sh"
README_PATH = SCRIPT_DIR / "README.md"
BUILDER_PATH = Path(__file__).resolve()
FINAL_REPORT_PATH = SCRIPT_DIR / "REPORT.md"
OFFICIAL_FINDINGS_PATH = SCRIPT_DIR / "official-findings.md"
LOCAL_BENCHMARK_PATH = REPO / "benchmark.sh"
FAN_CONTROL_PATH = REPO / "tools" / "fan-control.sh"
PUBLIC_FIXTURE_PATH = (
    REPO / "correctness_prompts" / "public_longcopy_gate_english_512_256.json"
)
DEFAULT_RESULTS = REPO / "quality-results" / "leaderboard-top15-20260802"
DEFAULT_CONTROL_RESULTS = (
    REPO / "quality-results" / "leaderboard-top15-controls-20260802"
)
DEFAULT_EXTENDED_AIME_RESULTS = (
    REPO / "quality-results" / "leaderboard-top15-20260802-aime-extended-6144"
)
REPORT_PATH = SCRIPT_DIR / "report-data.json"
CHECKSUMS_PATH = SCRIPT_DIR / "checksums.sha256"

REQUIRED_PUBLICATION_PATHS = (FINAL_REPORT_PATH, OFFICIAL_FINDINGS_PATH)

ATTEMPT_RE = re.compile(r"^attempt-([1-9][0-9]*)$")
BOXED_ANSWER_RE = re.compile(r"\\boxed\s*\{")
AIME_INTEGER_RE = re.compile(r"-?\d[\d,]*")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
LOCAL_GATE_PASS_RE = re.compile(
    r"^benchmark\.sh: GPU cool-down gate passed "
    r"\(current (?P<temperature>[0-9]+(?:\.[0-9]+)?)C, target <=40C, waited [0-9]+s\)$"
)
LOCAL_GATE_PHASE_RE = re.compile(
    r"^mlxfast: benchmark elapsed=[0-9]+(?:\.[0-9]+)?s local thermal gate "
    r"(?P<event>start|complete) phase=(?P<phase>prefill|decode)$"
)
LOCAL_THERMAL_REJECTION_MARKERS = (
    "local GPU cool-down gate disabled",
    "skipping the GPU cool-down gate",
    "temperature reading looks implausible",
    "plausibility floor",
    "retrying the temperature reader",
    "strict local thermal telemetry",
    "refusing to claim a thermally gated local timing",
    "temperature reader returned no usable sample",
    "local thermal gate failed",
)
PINNED_LOCAL_BENCHMARK_SHA256 = (
    "8827d1829db796836a87473dd730ff2c80a381df00626aabb526b8f20b3a8f57"
)
PINNED_FAN_CONTROL_SHA256 = (
    "d0281dd62612d5c3371904e317045ed9ae2e7d14021aee65e5b889ee1e46f84a"
)
PINNED_MACMON_SHA256 = (
    "495da8787023c9ebcd62d19e348cd6f1dec5dba3ef2d4f1ff55d9e2079860e19"
)
PINNED_MACMON_VERSION = "macmon 0.7.2"
LOCAL_BENCHMARK_CUTOVER = "2026-08-02T22:27:54Z"
PERFORMANCE_ENVIRONMENT_POLICY = "env-i-v1"
LEGACY_RANK111_LOG_SHA256 = (
    "f324d48d983efb427326c13caf0bc3dd0cc5b5e71a786f4f06c4c492270c4130"
)

QUALITY_SUITES = {"ppl", "mmlu_pro", "gpqa_diamond", "aime", "gsm8k"}
QUALITY_COMMAND_NAMES = {
    "ppl",
    "mmlu_pro_greedy",
    "gpqa_diamond_greedy",
    "gpqa_diamond_sampled_s0",
    "aime_greedy",
    "gsm8k_greedy",
    "gpqa_diamond_ranked_greedy",
}
COMPONENT_TOTALS = {
    "mmlu": 20,
    "gpqa_greedy": 9,
    "gpqa_sampled": 9,
    "aime": 9,
    "gsm8k": 6,
}
RETENTION_NUMERATOR = 97
RETENTION_DENOMINATOR = 100
RETENTION = RETENTION_NUMERATOR / RETENTION_DENOMINATOR
BEHAVIOR_NUMERATOR = 7
BEHAVIOR_DENOMINATOR = 9

CONTROL_RANKS = (201, 202, 203)
EXTENDED_AIME_RANKS = (116, 117, 118, 119)
EXTENDED_AIME_ID = "2024-2024-II-2"
EXTENDED_AIME_SCHEMA = "mlxfast-top15-extended-aime-v1"
EXTENDED_AIME_MAX_TOKENS = 6_144
PRIMARY_AIME_MAX_TOKENS = 2_048

KNOWN_AUXILIARY_RESULT_DIRECTORIES = {
    "root": {"setup"},
    "performance": {"000-official-pinned-baseline"},
    "quality": set(),
}

TERMINAL_ARTIFACT_PATHS = {
    "log": "{attempt}.log",
    "meta": "{attempt}.meta.json",
    "responses": "{attempt}/responses.jsonl",
    "run": "{attempt}/run.json",
    "run_spec": "run-spec.json",
    "real_bridge": "candidate-bridge",
    "raw.aime": "{attempt}/pass_1/aime_greedy.json",
    "raw.gpqa_greedy": "{attempt}/pass_1/gpqa_diamond_greedy.json",
    "raw.gpqa_sampled": "{attempt}/pass_1/gpqa_diamond_sampled_s0.json",
    "raw.gsm8k": "{attempt}/pass_1/candidate_gsm8k_greedy.json",
    "raw.mmlu_pro": "{attempt}/pass_1/mmlu_pro_greedy.json",
    "raw.ppl_results": "{attempt}/pass_1/ppl_results.jsonl",
    "raw.ppl_summary": "{attempt}/pass_1/ppl_summary.json",
    "raw.ranked_gpqa": "{attempt}/pass_1/gpqa_diamond_ranked_greedy.json",
}


class AuditFailure(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditFailure(message)


def is_number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def close(left: Any, right: Any, tolerance: float = 1e-12) -> bool:
    return is_number(left) and is_number(right) and math.isclose(
        float(left), float(right), rel_tol=tolerance, abs_tol=tolerance
    )


def validated_local_gate_temperatures(log_text: str, label: str) -> list[float]:
    """Return the two credible prefill/decode gate temperatures in a local run."""

    require(
        not any(marker in log_text for marker in LOCAL_THERMAL_REJECTION_MARKERS),
        f"{label} used implausible GPU telemetry",
    )
    events: list[tuple[str, str | float]] = []
    temperatures: list[float] = []
    for line in log_text.splitlines():
        phase_match = LOCAL_GATE_PHASE_RE.fullmatch(line)
        if phase_match:
            events.append((phase_match.group("event"), phase_match.group("phase")))
            continue
        pass_match = LOCAL_GATE_PASS_RE.fullmatch(line)
        if pass_match:
            temperature = float(pass_match.group("temperature"))
            temperatures.append(temperature)
            events.append(("pass", temperature))
            continue
        require(
            "GPU cool-down gate passed" not in line
            and "local thermal gate start phase=" not in line
            and "local thermal gate complete phase=" not in line,
            f"{label} contains an untrusted or malformed thermal event",
        )
    require(
        [event[0:2] if event[0] != "pass" else ("pass", None) for event in events]
        == [
            ("start", "prefill"),
            ("pass", None),
            ("complete", "prefill"),
            ("start", "decode"),
            ("pass", None),
            ("complete", "decode"),
        ],
        f"{label} does not contain ordered prefill/decode thermal gates",
    )
    require(
        len(temperatures) == 2,
        f"{label} does not contain exactly two completed local thermal gates",
    )
    require(
        all(5 < temperature <= 40 for temperature in temperatures),
        f"{label} thermal-gate temperature is outside the credible (5, 40]C range",
    )
    return temperatures


def aime_integer(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    match = re.search(r"-?\d+", str(value).strip().replace(",", ""))
    return int(match.group(0)) if match else None


def boxed_answer_spans(text: str) -> list[str]:
    spans: list[str] = []
    for match in BOXED_ANSWER_RE.finditer(text):
        index = match.end()
        depth = 1
        characters: list[str] = []
        while index < len(text) and depth > 0:
            character = text[index]
            if character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    break
            characters.append(character)
            index += 1
        spans.append("".join(characters))
    return spans


def extract_aime_answer(text: str) -> int | None:
    """Mirror the frozen evaluator's last-boxed-integer AIME extraction."""

    if not text:
        return None
    for span in reversed(boxed_answer_spans(text)):
        answer = aime_integer(span)
        if answer is not None:
            return answer
    answer: int | None = None
    for match in AIME_INTEGER_RE.finditer(text):
        candidate = aime_integer(match.group(0))
        if candidate is not None and 0 <= candidate <= 999:
            answer = candidate
    return answer


def canonical_json(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode()


class Files:
    """Read each file once so an audit is a coherent point-in-time snapshot."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo.resolve()
        self.cache: dict[Path, bytes] = {}
        self.checksums: dict[str, str] = {}
        self.directory_snapshots: dict[Path, tuple[tuple[str, str], ...] | None] = {}

    def bytes(self, path: Path) -> bytes:
        resolved = path.resolve()
        if resolved not in self.cache:
            self.cache[resolved] = resolved.read_bytes()
        return self.cache[resolved]

    def text(self, path: Path) -> str:
        return self.bytes(path).decode()

    def json_value(self, path: Path) -> Any:
        try:
            payload = json.loads(
                self.text(path),
                parse_constant=reject_nonfinite_json,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise AuditFailure(f"invalid JSON: {relative(path)}: {error}") from error
        return payload

    def json(self, path: Path) -> dict[str, Any]:
        payload = self.json_value(path)
        require(isinstance(payload, dict), f"JSON is not an object: {relative(path)}")
        return payload

    def digest(self, path: Path) -> str:
        return hashlib.sha256(self.bytes(path)).hexdigest()

    def ref(self, path: Path, **extra: Any) -> dict[str, Any]:
        resolved = path.resolve()
        digest = self.digest(resolved)
        path_text = relative(resolved)
        if resolved.is_relative_to(self.repo):
            self.checksums[path_text] = digest
        return {
            "path": path_text,
            "sha256": digest,
            "bytes": len(self.bytes(resolved)),
            **extra,
        }

    def observe_directory(self, path: Path) -> None:
        resolved = path.resolve()
        self.directory_snapshots.setdefault(resolved, self._directory_state(resolved))

    @staticmethod
    def _directory_state(path: Path) -> tuple[tuple[str, str], ...] | None:
        if not path.is_dir():
            return None
        return tuple(
            sorted(
                (
                    child.name,
                    "directory"
                    if child.is_dir()
                    else "file"
                    if child.is_file()
                    else "other",
                )
                for child in path.iterdir()
            )
        )

    def verify_unchanged(self) -> None:
        changed = [
            relative(path)
            for path, expected in self.cache.items()
            if not path.exists() or path.read_bytes() != expected
        ]
        changed.extend(
            relative(path)
            for path, expected in self.directory_snapshots.items()
            if self._directory_state(path) != expected
        )
        require(not changed, f"input files changed during audit: {', '.join(changed)}")


def relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO).as_posix()
    except ValueError:
        return str(resolved)


def has_unresolved_marker(text: str, marker: str) -> bool:
    """Return whether ``marker`` is asserted rather than explicitly negated."""

    for match in re.finditer(rf"\b{re.escape(marker)}s?\b", text):
        prefix = text[max(0, match.start() - 48) : match.start()]
        if re.search(r"\b(?:0|no|not|zero)\s+(?:[a-z0-9/-]+\s+){0,4}$", prefix):
            continue
        return True
    return False


def performance_completion_markers(report_text: str) -> list[dict[str, Any]]:
    """Locate explicit signs that REPORT.md still lacks final performance data.

    Final prose may say that there are ``0 pending`` arms or ``no performance
    placeholders``. Positive placeholder/pending language, explicit unrun or
    absent-performance language, and performance TODO/TBD markers are rejected.
    The result is deterministic and suitable for embedding in report-data.json.
    """

    source_lines = report_text.splitlines()
    plain_lines = [
        re.sub(r"[`*_]", "", source_line).strip().lower()
        for source_line in source_lines
    ]
    markers: list[dict[str, Any]] = []
    section_heading = ""
    for index, (source_line, text) in enumerate(
        zip(source_lines, plain_lines, strict=True)
    ):
        if not text:
            continue
        if text.startswith("#"):
            section_heading = text.lstrip("# ")
        adjacent = [
            plain_lines[neighbor]
            for neighbor in (index - 1, index + 1)
            if 0 <= neighbor < len(plain_lines)
            and plain_lines[neighbor]
            and not plain_lines[neighbor].startswith("#")
        ]
        context = " ".join([section_heading, text, *adjacent])
        kinds: list[str] = []
        if has_unresolved_marker(text, "placeholder"):
            kinds.append("placeholder")
        performance_context = "performance" in context
        publication_context = "report-data/checksum publication" in context
        if (performance_context or publication_context) and has_unresolved_marker(
            text, "pending"
        ):
            kinds.append("performance_pending")
        if performance_context and re.search(r"\b(?:todo|tbd|fixme)\b", text):
            kinds.append("performance_todo")
        if re.search(
            r"\b(?:unrun performance|no local performance result|"
            r"performance (?:artifacts?|arms?|results?) (?:are |is )?"
            r"(?:still )?(?:absent|missing|unrun))\b",
            text,
        ):
            kinds.append("performance_absent")
        if performance_context and re.search(
            r"\b0\s*(?:/|of)\s*16\b|\b0 valid selected attempts\b",
            text,
        ):
            kinds.append("performance_zero_complete_arms")
        if kinds:
            markers.append(
                {
                    "line": index + 1,
                    "kinds": sorted(set(kinds)),
                    "text": source_line.strip(),
                }
            )
    return markers


def checksum_manifest_bytes(
    input_checksums: dict[str, str], report_data_bytes: bytes
) -> bytes:
    """Build a final checksum manifest while deliberately excluding itself."""

    checksums = dict(input_checksums)
    required = [relative(path) for path in REQUIRED_PUBLICATION_PATHS]
    missing = [path for path in required if path not in checksums]
    require(
        not missing,
        "final checksum publication is missing required Markdown: "
        + ", ".join(missing),
    )
    checksum_path = relative(CHECKSUMS_PATH)
    report_data_path = relative(REPORT_PATH)
    require(
        checksum_path not in checksums,
        "checksum manifest cannot checksum itself",
    )
    require(
        report_data_path not in checksums,
        "report-data checksum must be derived from the publication payload",
    )
    checksums[report_data_path] = hash_text(report_data_bytes)
    for path, digest in checksums.items():
        require("\n" not in path and "\r" not in path, "checksum path contains a newline")
        require(
            SHA256_RE.fullmatch(digest) is not None,
            f"invalid checksum digest for {path}",
        )
    return "".join(
        f"{digest}  {path}\n" for path, digest in sorted(checksums.items())
    ).encode()


def file_under(root: Path, value: str) -> Path:
    require(bool(value), "artifact path is empty")
    candidate = (root / value).resolve()
    require(candidate.is_relative_to(root.resolve()), f"artifact escapes arm: {value}")
    return candidate


def hash_text(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_stream(files: Files, path: Path) -> list[Any]:
    """Parse whitespace-separated JSON values without assuming line boundaries.

    Response strings can legally contain Unicode line-separator characters,
    which ``str.splitlines`` would incorrectly treat as record separators.
    """

    text = files.text(path)
    decoder = json.JSONDecoder(parse_constant=reject_nonfinite_json)
    rows: list[Any] = []
    offset = 0
    while offset < len(text):
        while offset < len(text) and text[offset].isspace():
            offset += 1
        if offset == len(text):
            break
        try:
            row, offset = decoder.raw_decode(text, offset)
        except (json.JSONDecodeError, ValueError) as error:
            position = getattr(error, "pos", offset)
            message = getattr(error, "msg", str(error))
            raise AuditFailure(
                f"invalid JSON stream at {relative(path)} offset {position}: {message}"
            ) from error
        rows.append(row)
    return rows


def load_manifest(files: Files) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = files.json(MANIFEST_PATH)
    candidates = manifest.get("candidates")
    require(isinstance(candidates, list), "manifest candidates is not a list")
    require(len(candidates) == 15, "manifest must contain exactly 15 candidates")
    ranks = [candidate.get("rank") for candidate in candidates]
    require(ranks == list(range(112, 127)), "candidate ranks must be exactly 112..126")

    baseline = manifest.get("baseline")
    require(isinstance(baseline, dict), "manifest baseline is missing")
    require(baseline.get("rank") == 111, "local comparator must be rank 111")

    identities = [baseline, *candidates]
    require(
        len({item.get("submission_id") for item in identities}) == 16,
        "submission IDs are not unique",
    )
    require(
        len({item.get("source_ref") for item in identities}) == 16,
        "source refs are not unique",
    )
    for item in identities:
        rank = item.get("rank")
        require(isinstance(rank, int), "rank is not an integer")
        require(
            isinstance(item.get("submission_id"), str)
            and UUID_RE.fullmatch(item["submission_id"]) is not None,
            f"rank {rank} has an invalid submission ID",
        )
        require(
            isinstance(item.get("source_ref"), str)
            and COMMIT_RE.fullmatch(item["source_ref"]) is not None,
            f"rank {rank} has an invalid source ref",
        )
        for field in (
            "score",
            "decode_speedup",
            "decode_ms_per_token",
            "prefill_speedup",
            "prefill_ms_per_token",
        ):
            require(
                is_number(item.get(field)) and item[field] > 0,
                f"rank {rank} has invalid {field}",
            )
        recomputed = item["decode_speedup"] ** 0.75 * item["prefill_speedup"] ** 0.25
        require(
            close(recomputed, item["score"], 1e-10),
            f"rank {rank} official score does not match phase speedups",
        )

    for candidate in candidates:
        require(
            isinstance(candidate.get("pr"), int)
            and not isinstance(candidate.get("pr"), bool)
            and candidate["pr"] > 0,
            f"rank {candidate['rank']} has an invalid PR number",
        )
        require(
            isinstance(candidate.get("mechanism"), str) and candidate["mechanism"],
            f"rank {candidate['rank']} has no mechanism summary",
        )

    require(
        isinstance(manifest.get("study"), str) and manifest["study"],
        "manifest study ID is missing",
    )
    require(
        isinstance(manifest.get("harness_commit"), str)
        and COMMIT_RE.fullmatch(manifest["harness_commit"]) is not None,
        "manifest harness commit is invalid",
    )
    require(
        manifest["harness_commit"] == candidates[-1]["source_ref"],
        "harness commit is not the rank-126 source ref",
    )
    require(
        isinstance(manifest.get("evaluator_sha256"), str)
        and SHA256_RE.fullmatch(manifest["evaluator_sha256"]) is not None,
        "manifest evaluator hash is invalid",
    )
    require(
        manifest.get("required_environment")
        == {"DARKBLOOM_EXPERT_ALIGNED_GATHER": "0"},
        "required M4 environment differs",
    )
    return manifest, candidates


def git_commit_identity(ref: str) -> dict[str, str]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(REPO),
            "show",
            "-s",
            "--format=%H%x00%T%x00%P%x00%s",
            ref,
        ],
        check=False,
        capture_output=True,
    )
    require(result.returncode == 0, f"git cannot resolve source ref {ref}")
    parts = result.stdout.rstrip(b"\n").decode().split("\0")
    require(len(parts) == 4, f"git emitted an invalid identity for {ref}")
    commit, tree, parents, subject = parts
    parent_rows = parents.split()
    require(len(parent_rows) == 1, f"source ref {ref} does not have exactly one parent")
    return {
        "object_type": "commit",
        "resolved_commit": commit,
        "tree": tree,
        "parent": parent_rows[0],
        "subject": subject,
    }


def load_control_manifests(
    files: Files,
    primary_manifest: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    definition = files.json(CONTROL_DEFINITION_PATH)
    run = files.json(CONTROL_RUN_PATH)
    require(definition.get("schema_version") == 1, "negative-control definition schema differs")
    require(
        run.get("manifest_schema") == "mlxfast-quality-control-run-v1",
        "negative-control run schema differs",
    )
    require(
        definition.get("study") == run.get("study")
        and run.get("cohort") == "negative-controls",
        "negative-control study identity differs",
    )
    require(
        (run.get("performance") or {}).get("enabled") is False,
        "negative controls unexpectedly enable performance",
    )
    definition_ref = run.get("control_definition") or {}
    require(
        definition_ref.get("path") == CONTROL_DEFINITION_PATH.name,
        "control definition path differs",
    )
    require(
        definition_ref.get("sha256") == files.digest(CONTROL_DEFINITION_PATH),
        "control definition hash differs",
    )

    provenance = definition.get("provenance") or {}
    benchmark_id = provenance.get("benchmark_id")
    require(
        isinstance(benchmark_id, str)
        and UUID_RE.fullmatch(benchmark_id) is not None
        and benchmark_id in str(provenance.get("public_submission_index", "")),
        "control leaderboard provenance differs",
    )
    require(
        provenance.get("source_repository")
        == "https://github.com/Layr-Labs/mlxfast-challenge",
        "control source repository differs",
    )
    for field, primary_field in (
        ("harness_commit", "harness_commit"),
        ("evaluator_commit", "evaluator_commit"),
        ("evaluator_sha256", "evaluator_sha256"),
        ("quality_baseline", "quality_baseline"),
        ("host", "host"),
        ("required_environment", "required_environment"),
    ):
        require(run.get(field) == primary_manifest.get(primary_field), f"control {field} differs from primary study")
    require(
        provenance.get("common_harness_ref") == run["harness_commit"]
        and provenance.get("evaluator_commit") == run["evaluator_commit"]
        and provenance.get("evaluator_sha256") == run["evaluator_sha256"]
        and provenance.get("quality_baseline") == run["quality_baseline"]
        and provenance.get("host") == run["host"]
        and provenance.get("required_environment") == run["required_environment"],
        "control definition provenance differs from the frozen run manifest",
    )

    controls = definition.get("controls")
    run_rows = run.get("candidates")
    require(isinstance(controls, list) and len(controls) == 3, "control definition must contain three controls")
    require(isinstance(run_rows, list) and len(run_rows) == 3, "control run must contain three arms")
    require([row.get("order") for row in controls] == [1, 2, 3], "control order differs")
    require([row.get("rank") for row in run_rows] == list(CONTROL_RANKS), "control ranks differ")
    require(
        (definition.get("selection") or {}).get("control_count") == 3,
        "control selection count differs",
    )

    object_check = provenance.get("local_source_object_check") or {}
    require(
        object_check.get("result") == "all_present_verified",
        "control source-object check is not frozen as verified",
    )
    verified = object_check.get("verified_commits")
    require(isinstance(verified, list) and len(verified) == 3, "control verified-commit set differs")
    verified_by_submission = {row.get("submission_id"): row for row in verified}
    require(len(verified_by_submission) == 3, "control verified-commit IDs are not unique")

    merged: list[dict[str, Any]] = []
    for definition_row, run_row in zip(controls, run_rows, strict=True):
        rank = run_row.get("rank")
        submission_id = definition_row.get("submission_id")
        source_ref = definition_row.get("source_ref")
        require(
            isinstance(submission_id, str) and UUID_RE.fullmatch(submission_id) is not None,
            f"control rank {rank} submission ID is invalid",
        )
        require(
            isinstance(source_ref, str) and COMMIT_RE.fullmatch(source_ref) is not None,
            f"control rank {rank} source ref is invalid",
        )
        for field in ("submission_id", "source_ref", "source_ref_kind"):
            require(
                run_row.get(field) == definition_row.get(field),
                f"control rank {rank} {field} differs between manifests",
            )
        require(
            definition_row.get("source_ref_kind") == "submissionCommitSha",
            f"control rank {rank} source-ref kind differs",
        )
        for field in ("label", "mechanism", "control_role", "independence_caveat"):
            require(
                isinstance(definition_row.get(field), str)
                and definition_row[field],
                f"control rank {rank} {field} is missing",
            )
        require(
            run_row.get("control_order") == definition_row.get("order"),
            f"control rank {rank} order differs",
        )
        official = definition_row.get("official") or {}
        require(
            official.get("status") == "failed"
            and official.get("failure_category")
            == run_row.get("official_failure_category"),
            f"control rank {rank} official outcome differs",
        )
        require(
            isinstance(official.get("submission_url"), str)
            and submission_id in official["submission_url"],
            f"control rank {rank} official submission link differs",
        )
        workflow_id = official.get("workflow_run_id")
        artifact_id = official.get("redacted_artifact_id")
        require(
            isinstance(workflow_id, str)
            and workflow_id.isdigit()
            and workflow_id in str(official.get("workflow_url", ""))
            and isinstance(artifact_id, str)
            and artifact_id.isdigit()
            and workflow_id in str(official.get("redacted_artifact_url", ""))
            and artifact_id in str(official.get("redacted_artifact_url", "")),
            f"control rank {rank} official workflow provenance differs",
        )
        require(
            isinstance(official.get("redacted_evidence"), dict)
            and official["redacted_evidence"].get("mode") == "single-machine",
            f"control rank {rank} official redacted evidence differs",
        )
        frozen = verified_by_submission.get(submission_id)
        require(isinstance(frozen, dict), f"control rank {rank} lacks frozen source provenance")
        require(frozen.get("source_ref") == source_ref, f"control rank {rank} frozen source ref differs")
        observed = git_commit_identity(source_ref)
        for field, value in observed.items():
            require(frozen.get(field) == value, f"control rank {rank} frozen Git {field} differs")
        require(
            frozen.get("subject") == f"Validate submission {submission_id}",
            f"control rank {rank} validation subject differs",
        )
        merged.append({**run_row, "definition": definition_row})
    require(
        len({row["submission_id"] for row in merged}) == 3
        and len({row["source_ref"] for row in merged}) == 3,
        "control source identities are not unique",
    )
    return definition, run, merged


def git_parent(ref: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO), "show", "-s", "--format=%P", ref],
        check=False,
        capture_output=True,
        text=True,
    )
    require(result.returncode == 0, f"git cannot resolve source ref {ref}")
    parents = result.stdout.strip().split()
    require(len(parents) == 1, f"source ref {ref} does not have exactly one parent")
    return parents[0]


def source_chain(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [manifest["baseline"], *manifest["candidates"]]
    chain: list[dict[str, Any]] = []
    predecessor: dict[str, Any] | None = None
    for row in rows:
        parent = git_parent(row["source_ref"])
        expected = predecessor["source_ref"] if predecessor else parent
        if predecessor is not None:
            require(
                parent == expected,
                f"rank {row['rank']} is not a direct child of rank {predecessor['rank']}",
            )
        chain.append(
            {
                "rank": row["rank"],
                "source_ref": row["source_ref"],
                "actual_parent": parent,
                "expected_predecessor_ref": expected,
                "direct_parent_verified": None if predecessor is None else parent == expected,
            }
        )
        predecessor = row
    return chain


def harness_editable_paths(harness_ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{harness_ref}:benchmark.json"],
        check=False,
        capture_output=True,
    )
    require(result.returncode == 0, "cannot read benchmark.json from harness commit")
    try:
        benchmark = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AuditFailure(f"harness benchmark.json is invalid: {error}") from error
    editable = benchmark.get("editablePaths") if isinstance(benchmark, dict) else None
    require(
        isinstance(editable, list)
        and editable
        and all(isinstance(path, str) and path for path in editable),
        "harness editablePaths is invalid",
    )
    return editable


def expected_editable_identity(ref: str, editable: list[str]) -> dict[str, Any]:
    """Reproduce quality-eval's editable source digest directly from a git tree."""

    result = subprocess.run(
        ["git", "-C", str(REPO), "archive", "--format=tar", ref, "--", *editable],
        check=False,
        capture_output=True,
    )
    require(result.returncode == 0, f"cannot archive editable paths from {ref}")
    source_files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        for member in archive.getmembers():
            if member.isfile():
                extracted = archive.extractfile(member)
                require(extracted is not None, f"cannot read archived file {member.name}")
                source_files[member.name] = extracted.read()
            elif member.issym() or member.islnk():
                raise AuditFailure(f"editable source contains a link: {member.name}")
    missing = [
        path
        for path in editable
        if path not in source_files
        and not any(candidate.startswith(f"{path.rstrip('/')}/") for candidate in source_files)
    ]
    digest = hashlib.sha256()
    # Match quality-eval's ``sorted(set[Path])`` ordering, which compares path
    # components rather than the flattened POSIX strings.
    for path in sorted(source_files, key=Path):
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(source_files[path]).hexdigest().encode())
        digest.update(b"\n")
    for path in sorted(missing):
        digest.update(path.encode())
        digest.update(b"\0MISSING\n")
    return {
        "editable_source_sha256": digest.hexdigest(),
        "editable_file_count": len(source_files),
        "missing_editable_paths": sorted(missing),
    }


def leaf_correct_count(
    payload: dict[str, Any],
    rows_field: str,
    correct_field: str,
    aggregate_field: str,
    expected_rows: int,
    label: str,
) -> int:
    rows = payload.get(rows_field)
    require(
        isinstance(rows, list) and len(rows) == expected_rows,
        f"{label} leaf row count differs",
    )
    identifiers: list[tuple[type[Any], Any]] = []
    correct = 0
    for row in rows:
        require(isinstance(row, dict), f"{label} leaf row is not an object")
        identifier = row.get("id")
        require(
            (isinstance(identifier, (str, int)) and not isinstance(identifier, bool)),
            f"{label} leaf ID is invalid",
        )
        identifiers.append((type(identifier), identifier))
        value = row.get(correct_field)
        require(isinstance(value, bool), f"{label} leaf correctness is not boolean")
        correct += int(value)
    require(
        len(set(identifiers)) == expected_rows,
        f"{label} leaf IDs are not unique",
    )
    require(
        payload.get(aggregate_field) == correct,
        f"{label} aggregate correctness differs from leaves",
    )
    return correct


def require_quality_commands(commands: Any, label: str) -> list[dict[str, Any]]:
    require(
        isinstance(commands, list)
        and len(commands) == len(QUALITY_COMMAND_NAMES)
        and all(isinstance(command, dict) for command in commands),
        f"{label} command list differs",
    )
    require(
        {command.get("name") for command in commands} == QUALITY_COMMAND_NAMES,
        f"{label} command names differ",
    )
    require(
        all(
            command.get("exit_code") == 0 and command.get("status") == "passed"
            for command in commands
        ),
        f"{label} command result differs",
    )
    return commands


def recompute_ppl_artifacts(
    files: Files,
    results_path: Path,
    summary_path: Path,
    label: str,
) -> dict[str, Any]:
    summary = files.json(summary_path)
    rows = json_stream(files, results_path)
    require(len(rows) == 8, f"{label} PPL record count differs")
    identifiers: list[tuple[type[Any], Any]] = []
    for row in rows:
        require(isinstance(row, dict), f"{label} PPL row is not an object")
        require(row.get("error") is None, f"{label} PPL row records an error")
        identifier = row.get("id")
        require(
            isinstance(identifier, (str, int)) and not isinstance(identifier, bool),
            f"{label} PPL row ID is invalid",
        )
        identifiers.append((type(identifier), identifier))
        token_count = row.get("num_tokens")
        negative_log_likelihood = row.get("neg_log_likelihood")
        require(
            isinstance(token_count, int)
            and not isinstance(token_count, bool)
            and token_count > 0
            and is_number(negative_log_likelihood)
            and negative_log_likelihood >= 0,
            f"{label} PPL row is invalid",
        )
        try:
            row_ppl = math.exp(float(negative_log_likelihood) / token_count)
        except OverflowError as error:
            raise AuditFailure(f"{label} PPL row overflows") from error
        require(close(row.get("ppl"), row_ppl), f"{label} PPL row value differs")
    require(len(set(identifiers)) == 8, f"{label} PPL row IDs are not unique")
    token_count = sum(row["num_tokens"] for row in rows)
    negative_log_likelihood = sum(float(row["neg_log_likelihood"]) for row in rows)
    try:
        ppl = math.exp(negative_log_likelihood / token_count)
    except OverflowError as error:
        raise AuditFailure(f"{label} aggregate PPL overflows") from error
    require(token_count == 256, f"{label} PPL token count differs")
    require(summary.get("num_records") == 8, f"{label} PPL summary record count differs")
    require(summary.get("num_tokens") == token_count, f"{label} PPL summary token count differs")
    require(summary.get("prompt_logprobs") == 1, f"{label} PPL prompt-logprobs contract differs")
    require(
        close(summary.get("neg_log_likelihood"), negative_log_likelihood),
        f"{label} PPL summary NLL differs",
    )
    require(close(summary.get("ppl"), ppl), f"{label} PPL summary value differs")
    return {
        "value": ppl,
        "neg_log_likelihood": negative_log_likelihood,
        "tokens": token_count,
        "records": len(rows),
    }


def public_probe_contract(files: Files, run: dict[str, Any], label: str) -> dict[str, Any]:
    probe = run.get("local_public_correctness_probe")
    require(isinstance(probe, dict), f"{label} public probe is missing")
    fixture = files.json(PUBLIC_FIXTURE_PATH)
    fixture_ref = files.ref(PUBLIC_FIXTURE_PATH)
    cases = fixture.get("cases")
    require(isinstance(cases, list), "public fixture cases are missing")
    matches = [case for case in cases if isinstance(case, dict) and case.get("name") == probe.get("case")]
    require(len(matches) == 1, f"{label} public probe case is not in the fixture")
    case = matches[0]
    prompt_tokens = case.get("prompt_tokens")
    expected_tokens = case.get("expected_tokens")
    require(
        isinstance(prompt_tokens, list)
        and prompt_tokens
        and all(isinstance(token, int) and not isinstance(token, bool) for token in prompt_tokens),
        "public fixture prompt tokens are invalid",
    )
    require(
        isinstance(expected_tokens, list)
        and expected_tokens
        and all(isinstance(token, int) and not isinstance(token, bool) for token in expected_tokens),
        "public fixture expected tokens are invalid",
    )
    expected_token = expected_tokens[0]
    actual_token = probe.get("actual_token")
    require(probe.get("available") is True, f"{label} public probe is unavailable")
    require(
        isinstance(actual_token, int) and not isinstance(actual_token, bool),
        f"{label} public probe actual token is invalid",
    )
    require(probe.get("expected_token") == expected_token, f"{label} public probe expected token differs")
    require(
        probe.get("prompt_token_count") == len(prompt_tokens),
        f"{label} public probe prompt length differs",
    )
    require(
        probe.get("fixture_sha256") == fixture_ref["sha256"],
        f"{label} public probe fixture hash differs",
    )
    require(
        Path(str(probe.get("fixture", ""))).name == PUBLIC_FIXTURE_PATH.name,
        f"{label} public probe fixture path differs",
    )
    matched = actual_token == expected_token
    require(
        probe.get("matches_m5_fixture") is matched,
        f"{label} public probe recorded match differs from tokens",
    )
    require(
        isinstance(probe.get("interpretation"), str) and probe["interpretation"],
        f"{label} public probe interpretation is missing",
    )
    return {
        "case": case["name"],
        "fixture_sha256": fixture_ref["sha256"],
        "prompt_token_count": len(prompt_tokens),
        "expected_token": expected_token,
        "actual_token": actual_token,
        "matched": matched,
    }


def complete_raw_quality(files: Files, root: Path) -> dict[str, Any]:
    """Derive a valid quick-profile score from raw task artifacts."""

    pass_dir = root / "pass_1"
    files.observe_directory(root)
    files.observe_directory(pass_dir)
    paths = {
        "ppl_results": pass_dir / "ppl_results.jsonl",
        "ppl_summary": pass_dir / "ppl_summary.json",
        "mmlu": pass_dir / "mmlu_pro_greedy.json",
        "gpqa_greedy": pass_dir / "gpqa_diamond_greedy.json",
        "gpqa_sampled": pass_dir / "gpqa_diamond_sampled_s0.json",
        "aime": pass_dir / "aime_greedy.json",
        "gsm8k": pass_dir / "candidate_gsm8k_greedy.json",
        "ranked_gpqa": pass_dir / "gpqa_diamond_ranked_greedy.json",
    }
    for path in paths.values():
        require(path.is_file(), f"raw quality artifact is missing: {relative(path)}")
        files.ref(path)
    ppl = recompute_ppl_artifacts(
        files,
        paths["ppl_results"],
        paths["ppl_summary"],
        "raw quality",
    )

    tasks = {
        name: files.json(paths[name])
        for name in ("mmlu", "gpqa_greedy", "gpqa_sampled", "aime", "gsm8k", "ranked_gpqa")
    }
    for name, total in (("mmlu", 20), ("gpqa_greedy", 9), ("gpqa_sampled", 9)):
        task = tasks[name]
        require(
            task.get("n_samples") == total
            and task.get("n_expected") == total
            and task.get("n_scored") == total
            and task.get("n_error") == 0
            and task.get("n_length_truncated") == 0
            and task.get("incomplete") is False
            and isinstance(task.get("per_sample"), list)
            and len(task["per_sample"]) == total
            and all(
                isinstance(sample, dict)
                and sample.get("error") is None
                and sample.get("length_truncated") is False
                and sample.get("stop_reason") == "stop"
                for sample in task["per_sample"]
            ),
            f"raw {name} contract differs",
        )
    aime = tasks["aime"]
    require(
        aime.get("n_problems") == 9
        and aime.get("total_samples") == 9
        and isinstance(aime.get("per_problem"), list)
        and len(aime["per_problem"]) == 9
        and all(
            isinstance(problem, dict)
            and problem.get("finish_reasons") == ["stop"]
            and len(problem.get("texts") or []) == 1
            and len(problem.get("answers") or []) == 1
            for problem in aime["per_problem"]
        ),
        "raw AIME contract differs",
    )
    gsm8k = tasks["gsm8k"]
    require(
        gsm8k.get("n_problems") == 6
        and gsm8k.get("n_requested") == 6
        and gsm8k.get("n_error") == 0
        and gsm8k.get("truncation_rate") == 0
        and isinstance(gsm8k.get("per_problem"), list)
        and len(gsm8k["per_problem"]) == 6
        and all(
            isinstance(problem, dict) and problem.get("finish_reason") == "stop"
            for problem in gsm8k["per_problem"]
        ),
        "raw GSM8K contract differs",
    )
    ranked = tasks["ranked_gpqa"]
    require(
        ranked.get("n_samples") == 9
        and ranked.get("n_expected") == 9
        and ranked.get("n_scored") == 9
        and ranked.get("n_error") == 0
        and ranked.get("incomplete") is False
        and isinstance(ranked.get("per_sample"), list)
        and len(ranked["per_sample"]) == 9
        and all(
            isinstance(sample, dict)
            and sample.get("error") is None
            and sample.get("stop_reason") in {"stop", "max_tokens"}
            for sample in ranked["per_sample"]
        ),
        "raw ranked-GPQA contract differs",
    )
    derived_correct = {
        "mmlu": leaf_correct_count(tasks["mmlu"], "per_sample", "correct", "n_correct", 20, "raw MMLU"),
        "gpqa_greedy": leaf_correct_count(
            tasks["gpqa_greedy"], "per_sample", "correct", "n_correct", 9, "raw greedy GPQA"
        ),
        "gpqa_sampled": leaf_correct_count(
            tasks["gpqa_sampled"], "per_sample", "correct", "n_correct", 9, "raw sampled GPQA"
        ),
        "aime": leaf_correct_count(aime, "per_problem", "maj_correct", "n_correct_maj", 9, "raw AIME"),
        "gsm8k": leaf_correct_count(gsm8k, "per_problem", "correct", "n_correct", 6, "raw GSM8K"),
    }
    leaf_correct_count(
        ranked,
        "per_sample",
        "correct",
        "n_correct",
        9,
        "raw ranked GPQA",
    )
    components = {
        name: {"correct": derived_correct[name], "total": total}
        for name, total in COMPONENT_TOTALS.items()
    }
    correct = sum(component["correct"] for component in components.values())
    for component in components.values():
        component["score"] = component["correct"] / component["total"]
    return {
        "overall": {"correct": correct, "total": 53, "score": correct / 53},
        "components": components,
        "ppl": ppl["value"],
        "ppl_neg_log_likelihood": ppl["neg_log_likelihood"],
        "ppl_tokens": ppl["tokens"],
        "ppl_records": ppl["records"],
    }


def require_quality_metrics_match(
    summarized: dict[str, Any], raw: dict[str, Any], label: str
) -> None:
    require(summarized["overall"] == raw["overall"], f"{label} summary overall differs from raw")
    require(summarized["components"] == raw["components"], f"{label} summary components differ from raw")
    require(close(summarized["ppl"], raw["ppl"]), f"{label} summary PPL differs from raw")


def frozen_weight_identity(run: dict[str, Any]) -> dict[str, Any]:
    """Build the trusted harness directory digest from baseline file receipts."""

    artifact_files = (run.get("artifact_identity") or {}).get("files") or {}
    names = [
        "config.json",
        *(f"model-{index:05d}-of-00005.safetensors" for index in range(1, 6)),
        "model.safetensors.index.json",
        "tokenizer.json",
        "tokenizer_config.json",
    ]
    entries: dict[str, dict[str, Any]] = {}
    for name in names:
        keys = (f"weights/{name}", f"tokenizer/{name}")
        entry = next(
            (artifact_files[key] for key in keys if isinstance(artifact_files.get(key), dict)),
            None,
        )
        require(entry is not None, f"baseline identity lacks {name}")
        digest = entry.get("sha256")
        byte_count = entry.get("bytes")
        require(
            isinstance(digest, str)
            and SHA256_RE.fullmatch(digest) is not None
            and isinstance(byte_count, int)
            and not isinstance(byte_count, bool)
            and byte_count >= 0,
            f"baseline identity for {name} is invalid",
        )
        entries[name] = {"sha256": digest, "bytes": byte_count}
    tree = hashlib.sha256()
    for name, entry in sorted(entries.items()):
        tree.update(name.encode())
        tree.update(b"\0")
        tree.update(bytes.fromhex(entry["sha256"]))
        tree.update(b"\0")
    return {
        "sha256": tree.hexdigest(),
        "file_count": len(entries),
        "byte_count": sum(entry["bytes"] for entry in entries.values()),
        "files": entries,
        "source": "recomputed from the frozen baseline run's full shard/tokenizer receipts",
    }


def frozen_run_spec_artifacts(
    run: dict[str, Any], weights_identity: dict[str, Any]
) -> dict[str, str]:
    artifact_identity = run.get("artifact_identity") or {}
    artifact_files = artifact_identity.get("files") or {}
    reference_config = artifact_files.get("tokenizer/config.json")
    require(
        isinstance(reference_config, dict)
        and isinstance(reference_config.get("sha256"), str)
        and SHA256_RE.fullmatch(reference_config["sha256"]) is not None,
        "baseline reference-config receipt is invalid",
    )
    transform_source = artifact_identity.get("transform_source_sha256")
    require(
        isinstance(transform_source, str)
        and SHA256_RE.fullmatch(transform_source) is not None,
        "baseline transform-source receipt is invalid",
    )
    marker_sha256 = hash_text(f"{transform_source}\n".encode())
    return {
        "weights_config_sha256": weights_identity["files"]["config.json"]["sha256"],
        "weights_index_sha256": weights_identity["files"]["model.safetensors.index.json"]["sha256"],
        "transform_marker_sha256": marker_sha256,
        "transform_source_sha256": transform_source,
        "reference_config_sha256": reference_config["sha256"],
    }


def require_run_weights_match(
    run: dict[str, Any], expected: dict[str, Any], label: str
) -> None:
    artifact_files = (run.get("artifact_identity") or {}).get("files") or {}
    for name, receipt in expected["files"].items():
        keys = (f"weights/{name}", f"tokenizer/{name}")
        actual = next(
            (artifact_files[key] for key in keys if isinstance(artifact_files.get(key), dict)),
            None,
        )
        require(actual is not None, f"{label} identity lacks {name}")
        require(actual.get("sha256") == receipt["sha256"], f"{label} hash differs for {name}")
        require(actual.get("bytes") == receipt["bytes"], f"{label} byte count differs for {name}")


def baseline_quality(files: Files, manifest: dict[str, Any]) -> dict[str, Any]:
    root = (REPO / manifest["quality_baseline"]).resolve()
    run_path = root / "run.json"
    summary_path = root / "summary.json"
    require(run_path.is_file() and summary_path.is_file(), "quality baseline is incomplete")
    run = files.json(run_path)
    summary = files.json(summary_path)
    require(run.get("status") == "completed", "quality baseline is not completed")
    require(run.get("evaluation_valid") is True, "quality baseline is invalid")
    require(not run.get("failures"), "quality baseline records failures")
    require(run.get("profile") == "quick", "quality baseline is not quick")
    require(run.get("passes") == 1, "quality baseline does not have one pass")
    require(set(run.get("suites") or []) == QUALITY_SUITES, "quality baseline suites differ")
    require(
        (run.get("evaluator_provenance") or {}).get("sha256")
        == manifest["evaluator_sha256"],
        "quality baseline evaluator hash differs",
    )
    host = run.get("host_identity") or {}
    require(host.get("hardware_model") == manifest["host"]["model"], "baseline host model differs")
    require(host.get("cpu_brand") == manifest["host"]["chip"], "baseline chip differs")
    metrics = summary_metrics(summary)
    raw_metrics = complete_raw_quality(files, root)
    require_quality_metrics_match(metrics, raw_metrics, "quality baseline")
    weights_identity = frozen_weight_identity(run)
    run_spec_artifacts = frozen_run_spec_artifacts(run, weights_identity)
    public_probe = public_probe_contract(files, run, "baseline")
    require(public_probe["matched"], "baseline public probe does not match the fixture")
    require(metrics["overall"]["correct"] == 26, "baseline correct count is not 26")
    require(metrics["overall"]["total"] == 53, "baseline total is not 53")
    require((run.get("ppl_manifest") or {}).get("num_records") == 8, "baseline PPL records differ")
    require(
        (run.get("ppl_manifest") or {}).get("num_target_tokens") == 256,
        "baseline PPL token count differs",
    )
    return {
        "path": relative(root),
        "artifacts": {
            "run": files.ref(run_path),
            "summary": files.ref(summary_path),
        },
        "metrics": {**metrics, "raw_recomputed": raw_metrics},
        "weights_identity": weights_identity,
        "run_spec_artifacts": run_spec_artifacts,
        "public_probe": public_probe,
        "gate": {
            "minimum_retention": RETENTION,
            "minimum_correct": math.ceil(metrics["overall"]["correct"] * RETENTION),
            "maximum_ppl": metrics["ppl"] / RETENTION,
            "minimum_ranked_gpqa_matches": 7,
            "public_probe_must_match": True,
        },
        "run": run,
        "root": root,
    }


def summary_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    arms = summary.get("arms")
    require(isinstance(arms, list) and len(arms) == 1, "summary must contain one arm")
    arm = arms[0]
    require(isinstance(arm, dict), "summary arm is invalid")
    overall = arm.get("overall_score")
    require(isinstance(overall, dict), "summary overall score is missing")
    components = overall.get("components")
    require(isinstance(components, dict), "summary components are missing")
    normalized: dict[str, dict[str, Any]] = {}
    correct_sum = 0
    for name, total in COMPONENT_TOTALS.items():
        component = components.get(name)
        require(isinstance(component, dict), f"summary component {name} is missing")
        correct = component.get("correct")
        require(
            isinstance(correct, int) and not isinstance(correct, bool) and 0 <= correct <= total,
            f"summary component {name} correct count is invalid",
        )
        require(component.get("total") == total, f"summary component {name} total differs")
        require(close(component.get("score"), correct / total), f"summary component {name} score differs")
        normalized[name] = {"correct": correct, "total": total, "score": correct / total}
        correct_sum += correct
    require(overall.get("correct") == correct_sum, "summary aggregate correct count differs")
    require(overall.get("total") == 53, "summary aggregate total differs")
    require(close(overall.get("score"), correct_sum / 53), "summary aggregate score differs")
    ppl = (((arm.get("metrics") or {}).get("ppl") or {}).get("mean"))
    require(is_number(ppl) and ppl > 0, "summary PPL is invalid")
    return {
        "overall": {"correct": correct_sum, "total": 53, "score": correct_sum / 53},
        "components": normalized,
        "ppl": float(ppl),
    }


def validate_run_spec(
    files: Files,
    path: Path,
    phase: str,
    identity: dict[str, Any],
    manifest: dict[str, Any],
    manifest_sha256: str,
    baseline: dict[str, Any],
) -> dict[str, Any]:
    require(path.is_file(), f"missing run spec: {relative(path)}")
    spec = files.json(path)
    arm = spec.get("arm") or {}
    require(spec.get("study") == manifest["study"], "run spec study differs")
    require(spec.get("phase") == phase, "run spec phase differs")
    require(str(arm.get("rank")) == str(identity["rank"]), "run spec rank differs")
    require(arm.get("submission_id") == identity["submission_id"], "run spec submission differs")
    require(arm.get("source_ref") == identity["source_ref"], "run spec source differs")
    require(spec.get("harness_ref") == manifest["harness_commit"], "run spec harness differs")
    require(spec.get("manifest_sha256") == manifest_sha256, "run spec manifest hash differs")
    require(
        (spec.get("environment") or {}).get("DARKBLOOM_EXPERT_ALIGNED_GATHER") == "0",
        "run spec M4 environment differs",
    )
    performance = spec.get("performance") or {}
    if (manifest.get("performance") or {}).get("enabled") is False:
        require(performance == {"enabled": False}, "disabled control performance contract differs")
    else:
        require(performance.get("mode") == "--local-submit", "performance mode is not full local-submit")
        require(performance.get("runtime") == "swift-local-submit", "performance runtime differs")
        require(
            performance.get("allow_golden_drift") in {"0", "1"},
            "performance golden-drift setting is invalid",
        )
    quality = spec.get("quality") or {}
    require(quality.get("evaluator_sha256") == manifest["evaluator_sha256"], "run spec evaluator differs")
    require(
        quality.get("baseline_run_sha256") == baseline["artifacts"]["run"]["sha256"],
        "run spec baseline run hash differs",
    )
    require(
        quality.get("baseline_summary_sha256") == baseline["artifacts"]["summary"]["sha256"],
        "run spec baseline summary hash differs",
    )
    require(
        quality.get("launcher_wrapper_sha256") == files.digest(WRAPPER_PATH),
        "run spec wrapper hash differs",
    )
    artifacts = spec.get("artifacts") or {}
    weights = artifacts.get("weights") or {}
    expected_artifacts = baseline["run_spec_artifacts"]
    for field, expected_field in (
        ("config_sha256", "weights_config_sha256"),
        ("index_sha256", "weights_index_sha256"),
        ("transform_marker_sha256", "transform_marker_sha256"),
    ):
        require(
            weights.get(field) == expected_artifacts[expected_field],
            f"run spec weight {field} differs from the frozen receipt",
        )
    reference = artifacts.get("reference") or {}
    require(
        reference.get("config_sha256") == expected_artifacts["reference_config_sha256"],
        "run spec reference config hash differs from the frozen receipt",
    )
    optional_live_artifacts = {
        "weights_config": Path(str(weights.get("path", ""))).resolve() / "config.json",
        "weights_index": Path(str(weights.get("path", ""))).resolve()
        / "model.safetensors.index.json",
        "transform_marker": Path(str(weights.get("path", ""))).resolve()
        / ".benchmark-source.sha256",
        "reference_config": Path(str(reference.get("path", ""))).resolve() / "config.json",
    }
    expected_hashes = {
        "weights_config": expected_artifacts["weights_config_sha256"],
        "weights_index": expected_artifacts["weights_index_sha256"],
        "transform_marker": expected_artifacts["transform_marker_sha256"],
        "reference_config": expected_artifacts["reference_config_sha256"],
    }
    live_verified: list[str] = []
    for name, target in optional_live_artifacts.items():
        if target.is_file():
            require(
                files.digest(target) == expected_hashes[name],
                f"live run spec artifact differs: {target}",
            )
            live_verified.append(name)
    return {
        "payload": spec,
        "artifact": files.ref(path, live_artifacts_verified=live_verified),
        "live_artifacts_verified": live_verified,
    }


def attempt_names(arm_dir: Path) -> list[str]:
    names: set[str] = set()
    if not arm_dir.is_dir():
        return []
    for child in arm_dir.iterdir():
        match = re.match(r"^(attempt-[1-9][0-9]*)(?:\.|$)", child.name)
        if match:
            names.add(match.group(1))
    return sorted(names, key=lambda name: int(name.split("-")[1]))


def retained_tree(files: Files, root: Path) -> list[dict[str, Any]]:
    """Checksum every retained regular file under an attempt or build attempt.

    Failed and interrupted attempts are evidence, but never selected results.  A
    complete recursive inventory keeps that distinction independently auditable.
    """

    if not root.is_dir():
        return []
    artifacts: list[dict[str, Any]] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        files.observe_directory(directory)
        for child in sorted(directory.iterdir(), key=lambda path: path.name):
            require(not child.is_symlink(), f"retained attempt contains a symlink: {relative(child)}")
            if child.is_dir():
                pending.append(child)
            elif child.is_file():
                artifacts.append(files.ref(child))
            else:
                raise AuditFailure(f"retained attempt contains a special file: {relative(child)}")
    return sorted(artifacts, key=lambda artifact: artifact["path"])


def retained_attempt_sidecars(
    files: Files, arm_dir: Path, attempt: str
) -> list[dict[str, Any]]:
    """Checksum attempt-prefixed evidence stored beside the attempt directory."""

    if not arm_dir.is_dir():
        return []
    prefix = f"{attempt}."
    artifacts: list[dict[str, Any]] = []
    for child in sorted(arm_dir.iterdir(), key=lambda path: path.name):
        if not child.name.startswith(prefix):
            continue
        require(
            not child.is_symlink(),
            f"retained attempt sidecar is a symlink: {relative(child)}",
        )
        if child.is_file():
            artifacts.append(files.ref(child))
        elif child.is_dir():
            artifacts.extend(retained_tree(files, child))
        else:
            raise AuditFailure(
                f"retained attempt sidecar is a special file: {relative(child)}"
            )
    return sorted(artifacts, key=lambda artifact: artifact["path"])


def attempt_inventory(files: Files, arm_dir: Path) -> list[dict[str, Any]]:
    files.observe_directory(arm_dir)
    inventory: list[dict[str, Any]] = []
    for name in attempt_names(arm_dir):
        meta_path = arm_dir / f"{name}.meta.json"
        attempt_dir = arm_dir / name
        run_path = attempt_dir / "run.json"
        score_path = arm_dir / f"{name}.score.json"
        row: dict[str, Any] = {"attempt": name, "selected": False}
        files.observe_directory(attempt_dir)
        retained = retained_tree(files, attempt_dir)
        if retained:
            row["retained_artifacts"] = retained
        sidecars = retained_attempt_sidecars(files, arm_dir, name)
        if sidecars:
            row["retained_sidecars"] = sidecars
        if meta_path.is_file():
            row["meta"] = files.ref(meta_path)
            try:
                meta = files.json(meta_path)
                row.update(
                    {
                        "state": "finished",
                        "exit_code": meta.get("exit_code"),
                        "finished_at": meta.get("finished_at"),
                    }
                )
            except AuditFailure as error:
                row["state"] = "metadata_in_progress"
                row.setdefault("observations", []).append(str(error))
            log_path = arm_dir / f"{name}.log"
            if log_path.is_file():
                row["log"] = files.ref(log_path)
            if score_path.is_file():
                row["score"] = files.ref(score_path)
                try:
                    score = files.json(score_path)
                    row["error"] = (score.get("metrics") or {}).get("error")
                except AuditFailure as error:
                    row["state"] = "metadata_in_progress"
                    row.setdefault("observations", []).append(str(error))
            if run_path.is_file():
                row["run"] = files.ref(run_path)
                try:
                    run = files.json(run_path)
                    row["run_status"] = run.get("status")
                    row["error"] = run.get("error")
                except AuditFailure as error:
                    row["state"] = "metadata_in_progress"
                    row.setdefault("observations", []).append(str(error))
        else:
            row["state"] = "in_progress_or_interrupted"
        inventory.append(row)
    return inventory


def select_inventory_attempt(
    attempts: list[dict[str, Any]], selected: str
) -> None:
    matching = [attempt for attempt in attempts if attempt["attempt"] == selected]
    require(len(matching) == 1, f"selected attempt is absent from inventory: {selected}")
    matching[0]["selected"] = True


def has_in_progress_attempt(attempts: list[dict[str, Any]]) -> bool:
    return any(
        attempt.get("state") in {"in_progress_or_interrupted", "metadata_in_progress"}
        for attempt in attempts
    )


def validate_performance_selected(
    files: Files,
    arm_dir: Path,
    identity: dict[str, Any],
    manifest: dict[str, Any],
    manifest_sha256: str,
    baseline: dict[str, Any],
    expected_source: dict[str, Any],
) -> dict[str, Any]:
    selected_path = arm_dir / "selected-attempt.txt"
    selected = files.text(selected_path).strip()
    require(ATTEMPT_RE.fullmatch(selected) is not None, "selected performance attempt name is invalid")
    require(not (arm_dir / "terminal-noncompletion.json").exists(), "performance arm also has terminal marker")
    spec = validate_run_spec(
        files, arm_dir / "run-spec.json", "performance", identity, manifest, manifest_sha256, baseline
    )
    score_path = arm_dir / f"{selected}.score.json"
    canonical_score_path = arm_dir / "score.json"
    meta_path = arm_dir / f"{selected}.meta.json"
    integrity_path = arm_dir / f"{selected}.integrity.json"
    log_path = arm_dir / f"{selected}.log"
    for path in (score_path, canonical_score_path, meta_path, integrity_path, log_path):
        require(path.is_file(), f"selected performance artifact is missing: {relative(path)}")
    gate_temperatures = validated_local_gate_temperatures(
        files.text(log_path), "selected performance"
    )
    require(files.bytes(score_path) == files.bytes(canonical_score_path), "canonical score copy differs")
    score = files.json(score_path)
    meta = files.json(meta_path)
    integrity = files.json(integrity_path)
    metrics = score.get("metrics") or {}
    require(is_number(score.get("score")) and score["score"] > 0, "selected score is invalid")
    require(is_number(metrics.get("decode_seconds_per_token")) and metrics["decode_seconds_per_token"] > 0, "decode time is invalid")
    require(is_number(metrics.get("prefill_seconds_per_token")) and metrics["prefill_seconds_per_token"] > 0, "prefill time is invalid")
    require(
        is_number(metrics.get("baseline_decode_seconds_per_token"))
        and metrics["baseline_decode_seconds_per_token"] > 0,
        "decode baseline time is invalid",
    )
    require(
        is_number(metrics.get("baseline_prefill_seconds_per_token"))
        and metrics["baseline_prefill_seconds_per_token"] > 0,
        "prefill baseline time is invalid",
    )
    recomputed_decode_speedup = (
        metrics["baseline_decode_seconds_per_token"]
        / metrics["decode_seconds_per_token"]
    )
    recomputed_prefill_speedup = (
        metrics["baseline_prefill_seconds_per_token"]
        / metrics["prefill_seconds_per_token"]
    )
    recomputed_score = (
        recomputed_decode_speedup**0.75 * recomputed_prefill_speedup**0.25
    )
    require(
        close(metrics.get("decode_speedup"), recomputed_decode_speedup, 1e-10),
        "recorded decode speedup differs from phase times",
    )
    require(
        close(metrics.get("prefill_speedup"), recomputed_prefill_speedup, 1e-10),
        "recorded prefill speedup differs from phase times",
    )
    require(close(score.get("score"), recomputed_score, 1e-10), "recorded score differs from phase times")
    decode_floor = metrics.get("decode_speedup_floor")
    prefill_floor = metrics.get("prefill_speedup_floor")
    require(is_number(decode_floor) and decode_floor == 0.95, "decode floor differs")
    require(is_number(prefill_floor) and prefill_floor == 0.95, "prefill floor differs")
    decode_floor_passed = recomputed_decode_speedup >= decode_floor
    prefill_floor_passed = recomputed_prefill_speedup >= prefill_floor
    require(
        metrics.get("passed_decode_speedup_floor") == decode_floor_passed,
        "recorded decode floor decision differs",
    )
    require(
        metrics.get("passed_prefill_speedup_floor") == prefill_floor_passed,
        "recorded prefill floor decision differs",
    )
    # These floor flags compare an M4 local timing with the organizer's pinned
    # M5 calibration constants. They are useful receipts, but they are not a
    # validity gate for this same-M4 rank-111-normalized transfer study.
    require(metrics.get("checked_steps") == 1025, "local-submit checked-step count differs")
    require(metrics.get("case_count") == 1, "local-submit case count differs")
    require(
        isinstance(metrics.get("golden_hash"), str)
        and SHA256_RE.fullmatch(metrics["golden_hash"]) is not None,
        "selected performance golden hash is invalid",
    )
    allow_golden_drift = spec["payload"]["performance"]["allow_golden_drift"]
    if allow_golden_drift == "0":
        require(score.get("passed") is True, "selected performance did not pass")
        require(metrics.get("passed_correctness") is True, "selected performance correctness failed")
    else:
        require(
            (score.get("passed") is True and metrics.get("passed_correctness") is True)
            or (score.get("passed") is False and metrics.get("passed_correctness") is False),
            "selected performance has an invalid controlled-drift state",
        )
    require(metrics.get("partial_result") is False, "selected performance is partial")
    require(metrics.get("runtime") == "swift-local-submit", "selected performance runtime differs")
    score_commit = metrics.get("commit")
    require(
        isinstance(score_commit, str)
        and 7 <= len(score_commit) <= 40
        and manifest["harness_commit"].startswith(score_commit),
        "selected performance score harness commit differs",
    )
    require(
        isinstance(metrics.get("harness_hash"), str)
        and SHA256_RE.fullmatch(metrics["harness_hash"]) is not None,
        "selected performance harness hash is invalid",
    )
    require(meta.get("exit_code") == 0, "selected performance exit code is not zero")
    require(meta.get("source_ref") == identity["source_ref"], "performance meta source differs")
    require(meta.get("harness_ref") == manifest["harness_commit"], "performance meta harness differs")
    require(meta.get("manifest_sha256") == manifest_sha256, "performance meta manifest differs")
    require(meta.get("mode") == "--local-submit", "performance meta mode differs")
    require(meta.get("runtime") == "swift-local-submit", "performance meta runtime differs")
    environment = meta.get("environment") or {}
    require(environment.get("DARKBLOOM_EXPERT_ALIGNED_GATHER") == "0", "performance M4 override differs")
    require(
        environment.get("MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT") == allow_golden_drift,
        "performance golden drift differs",
    )
    finished_at = meta.get("finished_at")
    legacy_thermal_provenance = (
        all(
            key not in meta
            for key in (
                "local_benchmark_sha256",
                "runner_sha256",
                "fan_control_sha256",
                "macmon_sha256",
                "macmon_version",
                "log_sha256",
                "environment_policy",
            )
        )
        and isinstance(finished_at, str)
        and finished_at <= LOCAL_BENCHMARK_CUTOVER
        and identity["rank"] == 111
        and files.digest(log_path) == LEGACY_RANK111_LOG_SHA256
    )
    current_thermal_provenance = (
        meta.get("local_benchmark_sha256") == PINNED_LOCAL_BENCHMARK_SHA256
        and meta.get("runner_sha256") == files.digest(RUNNER_PATH)
        and meta.get("fan_control_sha256") == PINNED_FAN_CONTROL_SHA256
        and meta.get("macmon_sha256") == PINNED_MACMON_SHA256
        and meta.get("macmon_version") == PINNED_MACMON_VERSION
        and meta.get("log_sha256") == files.digest(log_path)
        and meta.get("environment_policy") == PERFORMANCE_ENVIRONMENT_POLICY
        and environment.get("MLXFAST_LOCAL_COOL_GATE_STRICT_TELEMETRY") == "1"
    )
    require(
        legacy_thermal_provenance or current_thermal_provenance,
        "performance thermal-tool or log provenance differs",
    )
    score_sha = files.digest(score_path)
    integrity_sha = files.digest(integrity_path)
    require(meta.get("score_sha256") == score_sha, "performance score hash differs")
    require(meta.get("integrity_sha256") == integrity_sha, "performance integrity hash differs")
    require(integrity.get("score_sha256") == score_sha, "integrity score hash differs")
    require(integrity.get("weights_sha256") == metrics.get("weights_hash"), "integrity weights hash differs")
    require(integrity.get("weights_file_count") == metrics.get("weights_file_count"), "integrity weight count differs")
    require(integrity.get("weights_byte_count") == metrics.get("weights_byte_count"), "integrity weight bytes differ")
    expected_weights = baseline["weights_identity"]
    require(integrity.get("weights_sha256") == expected_weights["sha256"], "performance weights differ from baseline receipts")
    require(integrity.get("weights_file_count") == expected_weights["file_count"], "performance weight count differs from baseline receipts")
    require(integrity.get("weights_byte_count") == expected_weights["byte_count"], "performance weight bytes differ from baseline receipts")
    expected_transform_source = baseline["run_spec_artifacts"]["transform_source_sha256"]
    require(
        integrity.get("transform_source_sha256") == expected_transform_source,
        "integrity transform source differs from the frozen receipt",
    )
    marker_path = (
        Path(spec["payload"]["artifacts"]["weights"]["path"])
        / ".benchmark-source.sha256"
    )
    if marker_path.is_file():
        require(
            files.text(marker_path).strip() == expected_transform_source,
            "live transform source differs",
        )
    if metrics.get("golden_hash"):
        require(integrity.get("golden_sha256") == metrics["golden_hash"], "integrity golden hash differs")
    artifacts = {
        "run_spec": spec["artifact"],
        "selected_attempt": files.ref(selected_path),
        "score": files.ref(score_path),
        "canonical_score": files.ref(canonical_score_path),
        "meta": files.ref(meta_path),
        "integrity": files.ref(integrity_path),
        "log": files.ref(log_path),
    }
    sidecar = Path(f"{score_path}.sha256")
    if sidecar.is_file():
        artifacts["score_sidecar"] = files.ref(sidecar)
        require(score_sha in files.text(sidecar).split(), "score sidecar hash differs")
    return {
        "status": "valid_selected_attempt",
        "selected_attempt": selected,
        "metrics": {
            "native_local_score": float(score["score"]),
            "recomputed_native_local_score": recomputed_score,
            "recomputed_decode_speedup": recomputed_decode_speedup,
            "recomputed_prefill_speedup": recomputed_prefill_speedup,
            "decode_seconds_per_token": float(metrics["decode_seconds_per_token"]),
            "decode_ms_per_token": float(metrics["decode_seconds_per_token"]) * 1000,
            "prefill_seconds_per_token": float(metrics["prefill_seconds_per_token"]),
            "prefill_ms_per_token": float(metrics["prefill_seconds_per_token"]) * 1000,
            "thermal_gate_temperatures_c": gate_temperatures,
            "thermal_provenance": {
                "policy": (
                    "legacy_pre_cutover_hashless_log"
                    if legacy_thermal_provenance
                    else "strict_hash_bound"
                ),
                "local_benchmark_sha256": meta.get("local_benchmark_sha256"),
                "runner_sha256": meta.get("runner_sha256"),
                "fan_control_sha256": meta.get("fan_control_sha256"),
                "macmon_sha256": meta.get("macmon_sha256"),
                "macmon_version": meta.get("macmon_version"),
                "log_sha256": meta.get("log_sha256"),
                "environment_policy": meta.get("environment_policy"),
            },
            "official_calibration_floor_receipt": {
                "decode_floor": float(decode_floor),
                "prefill_floor": float(prefill_floor),
                "decode_passed": decode_floor_passed,
                "prefill_passed": prefill_floor_passed,
                "interpretation": (
                    "Diagnostic comparison with pinned organizer M5 calibration; "
                    "not a local M4 artifact-validity condition"
                ),
            },
            "passed_correctness": metrics.get("passed_correctness"),
            "allow_golden_drift": allow_golden_drift == "1",
            "controlled_drift_signature": {
                "golden_hash": metrics.get("golden_hash"),
                "first_failing_case": metrics.get("first_failing_case"),
                "first_failing_step": metrics.get("first_failing_step"),
                "expected_token": metrics.get("expected_token"),
                "actual_token": metrics.get("actual_token"),
            }
            if metrics.get("passed_correctness") is False
            else None,
            "checked_steps": metrics.get("checked_steps"),
            "case_count": metrics.get("case_count"),
            "golden_hash": metrics.get("golden_hash"),
        },
        "source_identity": {
            "declared_source_ref": identity["source_ref"],
            "expected_editable_source": expected_source,
            "observed_harness_hash": metrics["harness_hash"],
            "binding": "trusted runner checkout contract; performance artifacts do not emit the applied editable-tree digest",
        },
        "artifacts": artifacts,
    }


def audit_performance_arm(
    files: Files,
    results: Path,
    identity: dict[str, Any],
    manifest: dict[str, Any],
    manifest_sha256: str,
    baseline: dict[str, Any],
    expected_source: dict[str, Any],
) -> dict[str, Any]:
    arm_dir = results / "performance" / f"{identity['rank']}-{identity['submission_id']}"
    files.observe_directory(arm_dir)
    attempts = attempt_inventory(files, arm_dir)
    row: dict[str, Any] = {
        "path": relative(arm_dir),
        "attempts": attempts,
    }
    if not arm_dir.is_dir():
        return {**row, "status": "pending", "reason": "arm_directory_absent"}
    selected = arm_dir / "selected-attempt.txt"
    terminal = arm_dir / "terminal-noncompletion.json"
    if terminal.exists():
        return {**row, "status": "invalid", "errors": ["performance arm has a terminal marker"]}
    if selected.is_file():
        try:
            marker_value = files.text(selected).strip()
        except UnicodeDecodeError as error:
            return {
                **row,
                "status": "invalid",
                "errors": [f"selected marker is not UTF-8: {error}"],
            }
        if ATTEMPT_RE.fullmatch(marker_value) is None:
            if marker_value in {"", "attempt-"}:
                return {
                    **row,
                    "status": "pending",
                    "reason": "selected_marker_in_progress",
                    "observations": [f"incomplete selected marker: {marker_value!r}"],
                }
            return {
                **row,
                "status": "invalid",
                "errors": [f"malformed selected marker: {marker_value!r}"],
            }
    if not selected.is_file():
        if (arm_dir / "run-spec.json").is_file():
            try:
                spec = validate_run_spec(
                    files,
                    arm_dir / "run-spec.json",
                    "performance",
                    identity,
                    manifest,
                    manifest_sha256,
                    baseline,
                )
                row["run_spec"] = spec["artifact"]
            except AuditFailure as error:
                if has_in_progress_attempt(attempts):
                    return {
                        **row,
                        "status": "pending",
                        "reason": "run_spec_or_attempt_metadata_in_progress",
                        "observations": [str(error)],
                    }
                return {**row, "status": "invalid", "errors": [str(error)]}
        return {**row, "status": "pending", "reason": "no_valid_selected_attempt"}
    try:
        result = validate_performance_selected(
            files,
            arm_dir,
            identity,
            manifest,
            manifest_sha256,
            baseline,
            expected_source,
        )
        select_inventory_attempt(attempts, result["selected_attempt"])
        return {
            **row,
            **result,
        }
    except (AuditFailure, OSError) as error:
        return {**row, "status": "invalid", "errors": [str(error)]}


def response_rows(files: Files, run_dir: Path) -> dict[tuple[str, str], str]:
    files.observe_directory(run_dir)
    if run_dir.is_dir():
        for child in run_dir.iterdir():
            if child.is_dir() and child.name.startswith("pass_"):
                files.observe_directory(child)
    rows: dict[tuple[str, str], str] = {}
    for path in sorted(run_dir.glob("pass_*/*.json")):
        if path.name.endswith("summary.json"):
            continue
        files.ref(path)
        try:
            data = files.json(path)
        except AuditFailure:
            continue
        relative_result = path.relative_to(run_dir).as_posix()
        samples = data.get("per_sample")
        if isinstance(samples, list):
            for sample in samples:
                if isinstance(sample, dict) and isinstance(sample.get("completion"), str):
                    rows[(relative_result, str(sample.get("id")))] = sample["completion"]
        problems = data.get("per_problem")
        if isinstance(problems, list):
            for problem in problems:
                if not isinstance(problem, dict):
                    continue
                if isinstance(problem.get("text"), str):
                    rows[(relative_result, str(problem.get("id")))] = problem["text"]
                elif isinstance(problem.get("texts"), list):
                    rows[(relative_result, str(problem.get("id")))] = json.dumps(
                        problem["texts"], ensure_ascii=False
                    )
    return rows


def recompute_response_identity(
    baseline_rows: dict[tuple[str, str], str],
    candidate_rows: dict[tuple[str, str], str],
) -> dict[str, Any]:
    baseline_keys = set(baseline_rows)
    candidate_keys = set(candidate_rows)
    common = baseline_keys & candidate_keys
    matched = sum(baseline_rows[key] == candidate_rows[key] for key in common)
    ranked_base = {
        key for key in baseline_keys if key[0].endswith("gpqa_diamond_ranked_greedy.json")
    }
    ranked_candidate = {
        key for key in candidate_keys if key[0].endswith("gpqa_diamond_ranked_greedy.json")
    }
    ranked_common = ranked_base & ranked_candidate
    ranked_matched = sum(
        baseline_rows[key] == candidate_rows[key] for key in ranked_common
    )
    ranked_required = math.ceil(len(ranked_base) * BEHAVIOR_NUMERATOR / BEHAVIOR_DENOMINATOR)
    return {
        "matched": matched,
        "total_compared": len(common),
        "baseline_only": len(baseline_keys - candidate_keys),
        "candidate_only": len(candidate_keys - baseline_keys),
        "row_sets_match": baseline_keys == candidate_keys,
        "ranked_gpqa": {
            "matched": ranked_matched,
            "total": len(ranked_base),
            "compared": len(ranked_common),
            "required_matches": ranked_required,
            "baseline_only": len(ranked_base - ranked_candidate),
            "candidate_only": len(ranked_candidate - ranked_base),
            "passed": (
                len(ranked_base) > 0
                and ranked_base == ranked_candidate
                and ranked_matched >= ranked_required
            ),
        },
    }


def quality_artifacts(files: Files, arm_dir: Path, attempt: str) -> dict[str, Any]:
    attempt_dir = arm_dir / attempt
    pass_dir = attempt_dir / "pass_1"
    files.observe_directory(attempt_dir)
    files.observe_directory(pass_dir)
    paths = {
        "run_spec": arm_dir / "run-spec.json",
        "selected_attempt": arm_dir / "selected-attempt.txt",
        "meta": arm_dir / f"{attempt}.meta.json",
        "log": arm_dir / f"{attempt}.log",
        "run": attempt_dir / "run.json",
        "summary": attempt_dir / "summary.json",
        "comparison": attempt_dir / "comparison.json",
        "responses": attempt_dir / "responses.jsonl",
        "ppl_manifest": attempt_dir / "ppl_manifest.jsonl",
        "ppl_results": pass_dir / "ppl_results.jsonl",
        "ppl_summary": pass_dir / "ppl_summary.json",
        "mmlu_pro": pass_dir / "mmlu_pro_greedy.json",
        "gpqa_greedy": pass_dir / "gpqa_diamond_greedy.json",
        "gpqa_sampled": pass_dir / "gpqa_diamond_sampled_s0.json",
        "aime": pass_dir / "aime_greedy.json",
        "gsm8k": pass_dir / "candidate_gsm8k_greedy.json",
        "ranked_gpqa": pass_dir / "gpqa_diamond_ranked_greedy.json",
        "real_bridge": arm_dir / "candidate-bridge",
        "real_bridge_source": arm_dir / "candidate-bridge.source.sha256",
    }
    for path in paths.values():
        require(path.is_file(), f"selected quality artifact is missing: {relative(path)}")
    return {name: files.ref(path) for name, path in paths.items()}


def validate_quality_selected(
    files: Files,
    arm_dir: Path,
    identity: dict[str, Any],
    manifest: dict[str, Any],
    manifest_sha256: str,
    baseline: dict[str, Any],
    baseline_rows: dict[tuple[str, str], str],
    expected_source: dict[str, Any],
) -> dict[str, Any]:
    selected_path = arm_dir / "selected-attempt.txt"
    selected = files.text(selected_path).strip()
    require(ATTEMPT_RE.fullmatch(selected) is not None, "selected quality attempt name is invalid")
    require(not (arm_dir / "terminal-noncompletion.json").exists(), "quality arm has both terminal and selected markers")
    spec = validate_run_spec(
        files, arm_dir / "run-spec.json", "quality", identity, manifest, manifest_sha256, baseline
    )
    artifacts = quality_artifacts(files, arm_dir, selected)
    attempt_dir = arm_dir / selected
    run = files.json(attempt_dir / "run.json")
    summary = files.json(attempt_dir / "summary.json")
    comparison = files.json(attempt_dir / "comparison.json")
    meta = files.json(arm_dir / f"{selected}.meta.json")
    metrics = summary_metrics(summary)
    raw_metrics = complete_raw_quality(files, attempt_dir)
    require_quality_metrics_match(metrics, raw_metrics, "candidate quality")

    require(run.get("status") == "completed", "quality run is not completed")
    require(run.get("evaluation_valid") is True, "quality run is not valid")
    require(not run.get("failures"), "quality run records failures")
    require_run_weights_match(run, baseline["weights_identity"], "candidate quality")
    require(run.get("profile") == "quick", "quality profile differs")
    require(run.get("passes") == 1, "quality pass count differs")
    require(set(run.get("suites") or []) == QUALITY_SUITES, "quality suites differ")
    require_quality_commands(run.get("commands"), "quality")
    require((run.get("ppl_manifest") or {}).get("num_records") == 8, "quality PPL record count differs")
    require((run.get("ppl_manifest") or {}).get("num_target_tokens") == 256, "quality PPL token count differs")
    require((run.get("evaluator_provenance") or {}).get("sha256") == manifest["evaluator_sha256"], "quality evaluator differs")
    host = run.get("host_identity") or {}
    require(host.get("hardware_model") == manifest["host"]["model"], "quality host model differs")
    require(host.get("cpu_brand") == manifest["host"]["chip"], "quality chip differs")
    checkout = (run.get("artifact_identity") or {}).get("checkout") or {}
    require(checkout.get("git_head") == manifest["harness_commit"], "quality harness differs")
    require(
        checkout.get("editable_source_sha256")
        == expected_source["editable_source_sha256"],
        "quality editable-source digest differs from the promoted commit",
    )
    require(
        checkout.get("editable_file_count") == expected_source["editable_file_count"],
        "quality editable-source file count differs",
    )
    require(
        sorted(checkout.get("missing_editable_paths") or [])
        == expected_source["missing_editable_paths"],
        "quality missing editable paths differ",
    )
    bridge_identity = (((run.get("artifact_identity") or {}).get("files") or {}).get("bridge") or {})
    require(bridge_identity.get("sha256") == files.digest(WRAPPER_PATH), "quality wrapper differs")
    attributes = (run.get("weave") or {}).get("attributes") or {}
    require(attributes.get("submission_id") == identity["submission_id"], "quality submission attribute differs")
    require(attributes.get("promoted_commit") == identity["source_ref"], "quality source attribute differs")
    require(attributes.get("host_compatibility") == "DARKBLOOM_EXPERT_ALIGNED_GATHER=0", "quality host override differs")
    real_bridge_sha = files.digest(arm_dir / "candidate-bridge")
    require(attributes.get("real_quality_bridge_sha256") == real_bridge_sha, "quality real bridge attribute differs")
    require(meta.get("source_ref") == identity["source_ref"], "quality meta source differs")
    require(meta.get("harness_ref") == manifest["harness_commit"], "quality meta harness differs")
    require(meta.get("manifest_sha256") == manifest_sha256, "quality meta manifest differs")
    require(meta.get("evaluator_sha256") == manifest["evaluator_sha256"], "quality meta evaluator differs")
    require(meta.get("wrapper_sha256") == files.digest(WRAPPER_PATH), "quality meta wrapper differs")
    require(meta.get("real_bridge_sha256") == real_bridge_sha, "quality meta bridge differs")
    source_fingerprint = files.text(arm_dir / "candidate-bridge.source.sha256").strip()
    require(meta.get("real_bridge_source_sha256") == source_fingerprint, "quality bridge source fingerprint differs")
    require((meta.get("environment") or {}).get("DARKBLOOM_EXPERT_ALIGNED_GATHER") == "0", "quality meta M4 override differs")

    require((comparison.get("compatibility") or {}).get("validated") is True, "comparison compatibility is invalid")
    require(Path(str(comparison.get("baseline"))).resolve() == baseline["root"], "comparison baseline path differs")
    require(Path(str(comparison.get("candidate"))).resolve() == attempt_dir.resolve(), "comparison candidate path differs")
    candidate_rows = response_rows(files, attempt_dir)
    require(
        len(json_stream(files, attempt_dir / "responses.jsonl")) == 70,
        "quality response count differs",
    )
    require(
        len(json_stream(files, attempt_dir / "pass_1" / "ppl_results.jsonl")) == 8,
        "quality PPL row count differs",
    )
    responses = recompute_response_identity(baseline_rows, candidate_rows)
    ranked = responses["ranked_gpqa"]
    require(ranked["total"] == 9 and ranked["required_matches"] == 7, "ranked GPQA contract differs")
    recorded_ranked = (comparison.get("response_identity") or {}).get("ranked_gpqa") or {}
    for field in ("matched", "total", "compared", "required_matches", "baseline_only", "candidate_only", "passed"):
        require(recorded_ranked.get(field) == ranked[field], f"recorded ranked GPQA {field} differs")
    recorded_identity = comparison.get("response_identity") or {}
    require(recorded_identity.get("matched") == responses["matched"], "response match count differs")
    require(recorded_identity.get("total") == responses["total_compared"], "response compared count differs")
    require(recorded_identity.get("baseline_only") == responses["baseline_only"], "response baseline-only count differs")
    require(recorded_identity.get("candidate_only") == responses["candidate_only"], "response candidate-only count differs")

    probe = public_probe_contract(files, run, "quality candidate")
    baseline_probe = baseline["public_probe"]
    for field in ("case", "fixture_sha256", "prompt_token_count", "expected_token"):
        require(
            probe[field] == baseline_probe[field],
            f"quality public probe {field} differs from baseline",
        )
    probe_passed = probe["matched"]
    recorded_probe = recorded_identity.get("public_probe") or {}
    require(recorded_probe.get("available") is True, "recorded public probe availability differs")
    require(
        recorded_probe.get("baseline_token") == baseline_probe["actual_token"],
        "recorded public probe baseline token differs",
    )
    require(
        recorded_probe.get("candidate_token") == probe["actual_token"],
        "recorded public probe candidate token differs",
    )
    require(recorded_probe.get("matched") == probe_passed, "recorded public probe decision differs")

    minimum_correct = baseline["gate"]["minimum_correct"]
    maximum_ppl = baseline["gate"]["maximum_ppl"]
    correct_passed = metrics["overall"]["correct"] >= minimum_correct
    ppl_passed = metrics["ppl"] <= maximum_ppl + 1e-12
    local_gate = (
        correct_passed
        and ppl_passed
        and ranked["passed"]
        and responses["row_sets_match"]
        and probe_passed
    )
    reasons = []
    if not correct_passed:
        reasons.append("overall_correct")
    if not ppl_passed:
        reasons.append("ppl")
    if not ranked["passed"]:
        reasons.append("ranked_gpqa_prefix")
    if not responses["row_sets_match"]:
        reasons.append("response_row_set")
    if not probe_passed:
        reasons.append("public_probe")
    decision = comparison.get("decision") or {}
    require(decision.get("local_retention_gate_passed") == local_gate, "recorded local gate differs")
    require(decision.get("row_sets_match") == responses["row_sets_match"], "recorded row-set decision differs")
    require(meta.get("exit_code") == (0 if local_gate else 3), "quality exit code and gate differ")
    overall_comparison = (comparison.get("metrics") or {}).get("overall_score") or {}
    ppl_comparison = (comparison.get("metrics") or {}).get("ppl") or {}
    require(overall_comparison.get("candidate_correct") == metrics["overall"]["correct"], "comparison correct count differs")
    require(overall_comparison.get("required_correct") == minimum_correct, "comparison correct threshold differs")
    require(overall_comparison.get("gate_passed") == correct_passed, "comparison correct gate differs")
    require(close(ppl_comparison.get("candidate"), metrics["ppl"]), "comparison PPL differs")
    require(close(ppl_comparison.get("threshold"), maximum_ppl), "comparison PPL threshold differs")
    require(ppl_comparison.get("gate_passed") == ppl_passed, "comparison PPL gate differs")

    return {
        "status": "valid_selected_attempt",
        "selected_attempt": selected,
        "formal_comparison": True,
        "metrics": {
            **metrics,
            "raw_recomputed": raw_metrics,
            "ranked_gpqa": ranked,
            "public_probe": {
                "actual_token": probe["actual_token"],
                "baseline_token": baseline_probe["actual_token"],
                "expected_token": probe["expected_token"],
                "matched": probe_passed,
                "prompt_token_count": probe["prompt_token_count"],
                "fixture_sha256": probe["fixture_sha256"],
            },
            "response_identity": responses,
        },
        "gate": {
            "minimum_retention": RETENTION,
            "minimum_correct": minimum_correct,
            "maximum_ppl": maximum_ppl,
            "correct_passed": correct_passed,
            "ppl_passed": ppl_passed,
            "ranked_gpqa_passed": ranked["passed"],
            "row_sets_match": responses["row_sets_match"],
            "public_probe_passed": probe_passed,
            "local_retention_gate_passed": local_gate,
            "failure_reasons": reasons,
            "recorded_decision_matches": True,
        },
        "source_identity": {
            "editable_source_sha256": checkout.get("editable_source_sha256"),
            "metallib_sha256": ((((run.get("artifact_identity") or {}).get("files") or {}).get("metallib") or {}).get("sha256")),
            "real_bridge_source_sha256": source_fingerprint,
        },
        "artifacts": {**artifacts, "run_spec": spec["artifact"]},
    }


def walk_marker_artifacts(
    files: Files, arm_dir: Path, value: Any, prefix: str = ""
) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
        path = file_under(arm_dir, value["path"])
        require(path.is_file(), f"terminal marker artifact is missing: {value['path']}")
        actual = files.digest(path)
        require(actual == value["sha256"], f"terminal marker hash differs: {value['path']}")
        return {prefix or "artifact": files.ref(path)}
    flattened: dict[str, Any] = {}
    for key, child in sorted(value.items()):
        name = f"{prefix}.{key}" if prefix else key
        flattened.update(walk_marker_artifacts(files, arm_dir, child, name))
    return flattened


def terminal_artifact_contract(marker: dict[str, Any], attempt: str) -> None:
    artifacts = marker.get("artifacts")
    require(isinstance(artifacts, dict), "terminal artifacts are not an object")
    for dotted, template in TERMINAL_ARTIFACT_PATHS.items():
        value: Any = artifacts
        for component in dotted.split("."):
            require(isinstance(value, dict), f"terminal artifact {dotted} is missing")
            value = value.get(component)
        require(isinstance(value, dict), f"terminal artifact {dotted} is missing")
        expected_path = template.format(attempt=attempt)
        require(
            value.get("path") == expected_path,
            f"terminal artifact {dotted} path differs",
        )
        require(
            isinstance(value.get("sha256"), str)
            and SHA256_RE.fullmatch(value["sha256"]) is not None,
            f"terminal artifact {dotted} hash is invalid",
        )
    require(
        ((artifacts.get("responses") or {}).get("records")) == 70,
        "terminal responses record count differs",
    )
    require(
        ((((artifacts.get("raw") or {}).get("ppl_results") or {}).get("records"))) == 8,
        "terminal PPL artifact record count differs",
    )


def validate_terminal_noncompletion(
    files: Files,
    arm_dir: Path,
    identity: dict[str, Any],
    manifest: dict[str, Any],
    manifest_sha256: str,
    baseline: dict[str, Any],
    expected_source: dict[str, Any],
) -> dict[str, Any]:
    marker_path = arm_dir / "terminal-noncompletion.json"
    marker = files.json(marker_path)
    require(not (arm_dir / "selected-attempt.txt").exists(), "terminal arm also has selected attempt")
    require(marker.get("schema") == "mlxfast-top15-quality-terminal-v1", "terminal schema differs")
    require(marker.get("status") == "bounded_noncompletion", "terminal status differs")
    require(marker.get("reason") == "aime_length", "terminal reason differs")
    marker_arm = marker.get("arm") or {}
    require(marker_arm.get("rank") == identity["rank"], "terminal rank differs")
    require(marker_arm.get("submission_id") == identity["submission_id"], "terminal submission differs")
    require(marker_arm.get("source_ref") == identity["source_ref"], "terminal source differs")
    require(marker.get("study") == manifest["study"], "terminal study differs")
    require(marker.get("harness_ref") == manifest["harness_commit"], "terminal harness differs")
    require(marker.get("manifest_sha256") == manifest_sha256, "terminal manifest differs")
    require(marker.get("evaluator_sha256") == manifest["evaluator_sha256"], "terminal evaluator differs")
    require(marker.get("wrapper_sha256") == files.digest(WRAPPER_PATH), "terminal wrapper differs")
    attempt = marker.get("attempt")
    require(isinstance(attempt, str) and ATTEMPT_RE.fullmatch(attempt), "terminal attempt differs")
    terminal_artifact_contract(marker, attempt)
    spec = validate_run_spec(
        files, arm_dir / "run-spec.json", "quality", identity, manifest, manifest_sha256, baseline
    )
    verified_artifacts = walk_marker_artifacts(files, arm_dir, marker.get("artifacts") or {})

    attempt_dir = arm_dir / attempt
    pass_dir = attempt_dir / "pass_1"
    files.observe_directory(attempt_dir)
    files.observe_directory(pass_dir)
    run = files.json(attempt_dir / "run.json")
    meta = files.json(arm_dir / f"{attempt}.meta.json")
    require(run.get("status") == "failed", "terminal run status differs")
    require(run.get("evaluation_valid") is False, "terminal run unexpectedly valid")
    require_run_weights_match(run, baseline["weights_identity"], "terminal quality")
    require(run.get("profile") == "quick" and run.get("passes") == 1, "terminal profile differs")
    require(set(run.get("suites") or []) == QUALITY_SUITES, "terminal suites differ")
    require(isinstance(run.get("error"), str) and run["error"].endswith("quality answer was truncated before completion"), "terminal error is not AIME truncation")
    require((run.get("evaluator_provenance") or {}).get("sha256") == manifest["evaluator_sha256"], "terminal run evaluator differs")
    host = run.get("host_identity") or {}
    require(host.get("hardware_model") == manifest["host"]["model"], "terminal host model differs")
    require(host.get("cpu_brand") == manifest["host"]["chip"], "terminal chip differs")
    checkout = (run.get("artifact_identity") or {}).get("checkout") or {}
    require(checkout.get("git_head") == manifest["harness_commit"], "terminal run harness differs")
    require(
        checkout.get("editable_source_sha256")
        == expected_source["editable_source_sha256"],
        "terminal editable-source digest differs from the promoted commit",
    )
    require(
        checkout.get("editable_file_count") == expected_source["editable_file_count"],
        "terminal editable-source file count differs",
    )
    require(
        sorted(checkout.get("missing_editable_paths") or [])
        == expected_source["missing_editable_paths"],
        "terminal missing editable paths differ",
    )
    bridge_identity = (((run.get("artifact_identity") or {}).get("files") or {}).get("bridge") or {})
    require(bridge_identity.get("sha256") == files.digest(WRAPPER_PATH), "terminal run wrapper differs")
    attributes = (run.get("weave") or {}).get("attributes") or {}
    require(attributes.get("submission_id") == identity["submission_id"], "terminal run submission differs")
    require(attributes.get("promoted_commit") == identity["source_ref"], "terminal run source differs")
    require(attributes.get("host_compatibility") == "DARKBLOOM_EXPERT_ALIGNED_GATHER=0", "terminal run host override differs")
    commands = require_quality_commands(run.get("commands"), "terminal quality")
    command_contract = [
        {
            "name": command.get("name"),
            "exit_code": command.get("exit_code"),
            "status": command.get("status"),
            "head_mode": command.get("head_mode"),
        }
        for command in commands
    ]
    require(marker.get("command_contract") == command_contract, "terminal command contract differs")
    require(meta.get("exit_code") == 2, "terminal evaluator exit code differs")
    require(meta.get("source_ref") == identity["source_ref"], "terminal meta source differs")
    require(meta.get("harness_ref") == manifest["harness_commit"], "terminal meta harness differs")
    require(meta.get("manifest_sha256") == manifest_sha256, "terminal meta manifest differs")
    require(meta.get("evaluator_sha256") == manifest["evaluator_sha256"], "terminal meta evaluator differs")
    require(meta.get("wrapper_sha256") == files.digest(WRAPPER_PATH), "terminal meta wrapper differs")
    require(marker.get("finished_at") == meta.get("finished_at"), "terminal finish time differs")
    real_bridge = arm_dir / "candidate-bridge"
    real_bridge_sidecar = arm_dir / "candidate-bridge.source.sha256"
    real_bridge_sha = files.digest(real_bridge)
    real_bridge_source_sha = files.text(real_bridge_sidecar).strip()
    real_bridge_marker = ((marker.get("artifacts") or {}).get("real_bridge") or {})
    require(attributes.get("real_quality_bridge_sha256") == real_bridge_sha, "terminal run real bridge differs")
    require(meta.get("real_bridge_sha256") == real_bridge_sha, "terminal meta real bridge differs")
    require(meta.get("real_bridge_source_sha256") == real_bridge_source_sha, "terminal meta bridge source differs")
    require(real_bridge_marker.get("source_sidecar_sha256") == files.digest(real_bridge_sidecar), "terminal bridge sidecar hash differs")
    require(real_bridge_marker.get("source_sha256") == real_bridge_source_sha, "terminal bridge source value differs")

    ppl = recompute_ppl_artifacts(
        files,
        pass_dir / "ppl_results.jsonl",
        pass_dir / "ppl_summary.json",
        "terminal quality",
    )
    mmlu = files.json(pass_dir / "mmlu_pro_greedy.json")
    gpqa_greedy = files.json(pass_dir / "gpqa_diamond_greedy.json")
    gpqa_sampled = files.json(pass_dir / "gpqa_diamond_sampled_s0.json")
    aime = files.json(pass_dir / "aime_greedy.json")
    gsm8k = files.json(pass_dir / "candidate_gsm8k_greedy.json")
    ranked = files.json(pass_dir / "gpqa_diamond_ranked_greedy.json")
    for name, payload, total in (
        ("mmlu", mmlu, 20),
        ("gpqa_greedy", gpqa_greedy, 9),
        ("gpqa_sampled", gpqa_sampled, 9),
    ):
        require(
            payload.get("n_samples") == total
            and payload.get("n_expected") == total
            and payload.get("n_scored") == total
            and payload.get("n_error") == 0
            and payload.get("n_length_truncated") == 0
            and payload.get("incomplete") is False
            and isinstance(payload.get("per_sample"), list)
            and len(payload["per_sample"]) == total
            and all(
                isinstance(sample, dict)
                and sample.get("error") is None
                and sample.get("length_truncated") is False
                and sample.get("stop_reason") == "stop"
                for sample in payload["per_sample"]
            ),
            f"terminal {name} contract differs",
        )
    require(
        aime.get("n_problems") == 9
        and aime.get("total_samples") == 9
        and isinstance(aime.get("per_problem"), list)
        and len(aime["per_problem"]) == 9
        and all(
            isinstance(problem, dict)
            and isinstance(problem.get("finish_reasons"), list)
            and len(problem["finish_reasons"]) == 1
            and problem["finish_reasons"][0] in {"stop", "length"}
            and isinstance(problem.get("sample_chars"), list)
            and len(problem["sample_chars"]) == 1
            and isinstance(problem.get("texts"), list)
            and len(problem["texts"]) == 1
            and isinstance(problem.get("answers"), list)
            and len(problem["answers"]) == 1
            for problem in aime["per_problem"]
        )
        and any(
            "length" in (problem.get("finish_reasons") or [])
            for problem in aime.get("per_problem", [])
        ),
        "terminal AIME truncation contract differs",
    )
    require(
        gsm8k.get("n_problems") == 6
        and gsm8k.get("n_requested") == 6
        and gsm8k.get("n_error") == 0
        and gsm8k.get("truncation_rate") == 0
        and isinstance(gsm8k.get("per_problem"), list)
        and len(gsm8k["per_problem"]) == 6
        and all(
            isinstance(problem, dict) and problem.get("finish_reason") == "stop"
            for problem in gsm8k["per_problem"]
        ),
        "terminal GSM8K contract differs",
    )
    require(
        ranked.get("n_samples") == 9
        and ranked.get("n_expected") == 9
        and ranked.get("n_scored") == 9
        and ranked.get("n_error") == 0
        and ranked.get("incomplete") is False
        and isinstance(ranked.get("per_sample"), list)
        and len(ranked["per_sample"]) == 9
        and all(
            isinstance(sample, dict)
            and sample.get("error") is None
            and sample.get("stop_reason") in {"stop", "max_tokens"}
            for sample in ranked["per_sample"]
        ),
        "terminal ranked-GPQA contract differs",
    )
    derived_correct = {
        "mmlu": leaf_correct_count(mmlu, "per_sample", "correct", "n_correct", 20, "terminal MMLU"),
        "gpqa_greedy": leaf_correct_count(
            gpqa_greedy, "per_sample", "correct", "n_correct", 9, "terminal greedy GPQA"
        ),
        "gpqa_sampled": leaf_correct_count(
            gpqa_sampled, "per_sample", "correct", "n_correct", 9, "terminal sampled GPQA"
        ),
        "aime": leaf_correct_count(
            aime, "per_problem", "maj_correct", "n_correct_maj", 9, "terminal AIME"
        ),
        "gsm8k": leaf_correct_count(
            gsm8k, "per_problem", "correct", "n_correct", 6, "terminal GSM8K"
        ),
    }
    ranked_correct = leaf_correct_count(
        ranked,
        "per_sample",
        "correct",
        "n_correct",
        9,
        "terminal ranked GPQA",
    )
    raw = {
        "validation_status": "unvalidated_due_aime_length",
        "overall": {
            "correct": sum(derived_correct.values()),
            "total": 53,
        },
        "mmlu_pro": {"correct": derived_correct["mmlu"], "total": mmlu["n_samples"]},
        "gpqa_greedy": {"correct": derived_correct["gpqa_greedy"], "total": gpqa_greedy["n_samples"]},
        "gpqa_sampled": {"correct": derived_correct["gpqa_sampled"], "total": gpqa_sampled["n_samples"]},
        "aime": {"correct": derived_correct["aime"], "total": aime["n_problems"]},
        "gsm8k": {"correct": derived_correct["gsm8k"], "total": gsm8k["n_problems"]},
        "ppl": {"value": ppl["value"], "records": ppl["records"], "tokens": ppl["tokens"]},
        "ranked_gpqa": {
            "raw_task_correct": ranked_correct,
            "total": ranked["n_samples"],
            "formal_prefix_comparison": False,
        },
    }
    require(marker.get("raw_quality") == raw, "terminal raw quality does not recompute")
    response_records = json_stream(files, attempt_dir / "responses.jsonl")
    require(
        len(response_records) == 70
        and all(
            isinstance(record, dict) and record.get("error") is None
            for record in response_records
        ),
        "terminal response contract differs",
    )
    require(len(json_stream(files, pass_dir / "ppl_results.jsonl")) == 8, "terminal PPL row count differs")
    truncated = [
        {
            "id": problem.get("id"),
            "finish_reasons": problem.get("finish_reasons"),
            "sample_chars": problem.get("sample_chars"),
            "answers": problem.get("answers"),
        }
        for problem in aime.get("per_problem", [])
        if "length" in (problem.get("finish_reasons") or [])
    ]
    require(marker.get("truncated_items") == truncated and truncated, "terminal truncation list differs")
    recorded_probe = run.get("local_public_correctness_probe") or {}
    require(marker.get("public_probe") == recorded_probe, "terminal public probe differs")
    probe = public_probe_contract(files, run, "terminal quality")
    baseline_probe = baseline["public_probe"]
    for field in ("case", "fixture_sha256", "prompt_token_count", "expected_token"):
        require(
            probe[field] == baseline_probe[field],
            f"terminal public probe {field} differs from baseline",
        )
    require(probe["matched"], "terminal public probe failed")
    interpretation = marker.get("interpretation") or {}
    require(interpretation.get("formally_comparable") is False, "terminal comparison flag differs")
    require(interpretation.get("local_retention_gate_evaluated") is False, "terminal gate flag differs")
    return {
        "status": "terminal_noncompletion",
        "terminal_reason": "aime_length",
        "attempt": attempt,
        "formal_comparison": False,
        "local_retention_gate_passed": None,
        "raw_quality": raw,
        "public_probe": probe,
        "truncated_items": truncated,
        "artifacts": {
            "terminal_marker": files.ref(marker_path),
            "run_spec": spec["artifact"],
            **verified_artifacts,
        },
    }


def audit_quality_arm(
    files: Files,
    results: Path,
    identity: dict[str, Any],
    manifest: dict[str, Any],
    manifest_sha256: str,
    baseline: dict[str, Any],
    baseline_rows: dict[tuple[str, str], str],
    expected_source: dict[str, Any],
) -> dict[str, Any]:
    arm_dir = results / "quality" / f"{identity['rank']}-{identity['submission_id']}"
    files.observe_directory(arm_dir)
    attempts = attempt_inventory(files, arm_dir)
    row: dict[str, Any] = {
        "path": relative(arm_dir),
        "attempts": attempts,
    }
    if not arm_dir.is_dir():
        return {**row, "status": "pending", "reason": "arm_directory_absent"}
    selected = arm_dir / "selected-attempt.txt"
    terminal = arm_dir / "terminal-noncompletion.json"
    if selected.exists() and terminal.exists():
        return {**row, "status": "invalid", "errors": ["arm has both selected and terminal markers"]}
    if selected.is_file():
        try:
            marker_value = files.text(selected).strip()
        except UnicodeDecodeError as error:
            return {
                **row,
                "status": "invalid",
                "errors": [f"selected marker is not UTF-8: {error}"],
            }
        if ATTEMPT_RE.fullmatch(marker_value) is None:
            if marker_value in {"", "attempt-"}:
                return {
                    **row,
                    "status": "pending",
                    "reason": "selected_marker_in_progress",
                    "observations": [f"incomplete selected marker: {marker_value!r}"],
                }
            return {
                **row,
                "status": "invalid",
                "errors": [f"malformed selected marker: {marker_value!r}"],
            }
    try:
        if selected.is_file():
            result = validate_quality_selected(
                files,
                arm_dir,
                identity,
                manifest,
                manifest_sha256,
                baseline,
                baseline_rows,
                expected_source,
            )
            select_inventory_attempt(attempts, result["selected_attempt"])
            return {
                **row,
                **result,
            }
        if terminal.is_file():
            return {
                **row,
                **validate_terminal_noncompletion(
                    files,
                    arm_dir,
                    identity,
                    manifest,
                    manifest_sha256,
                    baseline,
                    expected_source,
                ),
            }
        if (arm_dir / "run-spec.json").is_file():
            try:
                spec = validate_run_spec(
                    files,
                    arm_dir / "run-spec.json",
                    "quality",
                    identity,
                    manifest,
                    manifest_sha256,
                    baseline,
                )
                row["run_spec"] = spec["artifact"]
            except AuditFailure as error:
                if has_in_progress_attempt(attempts):
                    return {
                        **row,
                        "status": "pending",
                        "reason": "run_spec_or_attempt_metadata_in_progress",
                        "observations": [str(error)],
                    }
                raise
        return {**row, "status": "pending", "reason": "no_terminal_result"}
    except (AuditFailure, KeyError, OSError, TypeError) as error:
        return {**row, "status": "invalid", "errors": [str(error)]}


def require_sha256_value(value: Any, label: str) -> str:
    require(
        isinstance(value, str) and SHA256_RE.fullmatch(value) is not None,
        f"{label} is not a SHA-256",
    )
    return value


def audit_extended_evaluator(
    files: Files,
    results: Path,
    manifest: dict[str, Any],
) -> dict[str, Any] | None:
    identity_path = results / "_pinned-evaluator.json"
    evaluator_root = results / "_pinned-evaluator" / "senpai" / "quality_eval"
    files.observe_directory(results)
    if not identity_path.exists() and not evaluator_root.exists():
        return None
    require(identity_path.is_file(), "extended-AIME pinned evaluator identity is missing")
    require(evaluator_root.is_dir(), "extended-AIME pinned evaluator tree is missing")
    identity = files.json(identity_path)
    require(
        identity.get("schema") == f"{EXTENDED_AIME_SCHEMA}-evaluator",
        "extended-AIME evaluator schema differs",
    )
    require(
        identity.get("commit") == manifest.get("evaluator_commit"),
        "extended-AIME evaluator commit differs",
    )
    provenance = identity.get("provenance") or {}
    require(
        provenance.get("sha256") == manifest["evaluator_sha256"],
        "extended-AIME evaluator provenance hash differs",
    )
    provenance_files = provenance.get("files")
    require(
        isinstance(provenance_files, dict) and provenance_files,
        "extended-AIME evaluator provenance files are missing",
    )
    verified: dict[str, Any] = {}
    for name, expected in sorted(provenance_files.items()):
        require_sha256_value(expected, f"extended-AIME evaluator file {name}")
        path = file_under(evaluator_root, name)
        require(path.is_file(), f"extended-AIME evaluator file is missing: {name}")
        require(files.digest(path) == expected, f"extended-AIME evaluator file hash differs: {name}")
        verified[name] = files.ref(path)
    return {
        "identity": files.ref(identity_path),
        "commit": identity["commit"],
        "provenance_sha256": provenance["sha256"],
        "files": verified,
    }


def extended_primary_evidence(
    files: Files,
    primary_results: Path,
    identity: dict[str, Any],
) -> dict[str, Any]:
    arm_dir = primary_results / "quality" / f"{identity['rank']}-{identity['submission_id']}"
    marker_path = arm_dir / "terminal-noncompletion.json"
    marker = files.json(marker_path)
    require(
        marker.get("schema") == "mlxfast-top15-quality-terminal-v1"
        and marker.get("status") == "bounded_noncompletion"
        and marker.get("reason") == "aime_length",
        f"rank {identity['rank']} primary AIME evidence is not a bounded non-completion",
    )
    require(
        marker.get("arm")
        == {
            "rank": identity["rank"],
            "submission_id": identity["submission_id"],
            "source_ref": identity["source_ref"],
        },
        f"rank {identity['rank']} primary AIME marker identity differs",
    )
    truncated = marker.get("truncated_items")
    require(
        isinstance(truncated, list)
        and len(truncated) == 1
        and truncated[0].get("id") == EXTENDED_AIME_ID
        and truncated[0].get("finish_reasons") == ["length"],
        f"rank {identity['rank']} primary marker is not bounded on {EXTENDED_AIME_ID}",
    )
    artifacts = marker.get("artifacts") or {}

    def marked(name: str, descriptor: Any) -> tuple[Path, dict[str, Any]]:
        require(isinstance(descriptor, dict), f"rank {identity['rank']} primary {name} descriptor is missing")
        path = file_under(arm_dir, str(descriptor.get("path", "")))
        expected = require_sha256_value(descriptor.get("sha256"), f"rank {identity['rank']} primary {name}")
        require(path.is_file(), f"rank {identity['rank']} primary {name} is missing")
        require(files.digest(path) == expected, f"rank {identity['rank']} primary {name} hash differs")
        return path, files.ref(path)

    run_spec_path, run_spec_ref = marked("run spec", artifacts.get("run_spec"))
    run_path, run_ref = marked("run", artifacts.get("run"))
    aime_path, aime_ref = marked("AIME result", (artifacts.get("raw") or {}).get("aime"))
    bridge_descriptor = artifacts.get("real_bridge")
    bridge_path, bridge_ref = marked("real bridge", bridge_descriptor)
    sidecar_path = bridge_path.with_name(f"{bridge_path.name}.source.sha256")
    require(sidecar_path.is_file(), f"rank {identity['rank']} primary bridge source sidecar is missing")
    sidecar_ref = files.ref(sidecar_path)
    bridge_source = files.text(sidecar_path).strip()
    require_sha256_value(bridge_source, f"rank {identity['rank']} primary bridge source")
    require(
        bridge_source == (bridge_descriptor or {}).get("source_sha256")
        and sidecar_ref["sha256"] == (bridge_descriptor or {}).get("source_sidecar_sha256"),
        f"rank {identity['rank']} primary bridge source provenance differs",
    )

    run = files.json(run_path)
    checkout = (run.get("artifact_identity") or {}).get("checkout") or {}
    run_files = (run.get("artifact_identity") or {}).get("files") or {}
    editable_source = require_sha256_value(
        checkout.get("editable_source_sha256"),
        f"rank {identity['rank']} primary editable source",
    )
    metallib = require_sha256_value(
        ((run_files.get("metallib") or {}).get("sha256")),
        f"rank {identity['rank']} primary metallib",
    )
    aime = files.json(aime_path)
    rows = [
        row
        for row in (aime.get("per_problem") or [])
        if isinstance(row, dict) and row.get("id") == EXTENDED_AIME_ID
    ]
    require(len(rows) == 1, f"rank {identity['rank']} primary frozen AIME item differs")
    row = rows[0]
    require(
        row.get("finish_reasons") == ["length"]
        and len(row.get("answers") or []) == 1
        and len(row.get("sample_chars") or []) == 1
        and isinstance(row.get("gold"), int),
        f"rank {identity['rank']} primary frozen AIME shape differs",
    )
    prompt_sha = require_sha256_value(
        row.get("prompt_sha"), f"rank {identity['rank']} primary AIME prompt"
    )
    return {
        "arm_dir": arm_dir,
        "marker": marker,
        "marker_path": marker_path,
        "marker_ref": files.ref(marker_path),
        "run_spec_path": run_spec_path,
        "run_spec_ref": run_spec_ref,
        "run_path": run_path,
        "run_ref": run_ref,
        "aime_path": aime_path,
        "aime_ref": aime_ref,
        "bridge_ref": bridge_ref,
        "bridge_source_ref": sidecar_ref,
        "bridge_source_sha256": bridge_source,
        "editable_source_sha256": editable_source,
        "metallib_sha256": metallib,
        "frozen_item": {
            "id": EXTENDED_AIME_ID,
            "prompt_sha256": prompt_sha,
            "gold": row["gold"],
            "finish_reason": "length",
            "max_tokens": PRIMARY_AIME_MAX_TOKENS,
            "answer": row["answers"][0],
            "sample_chars": row["sample_chars"][0],
        },
    }


def expected_extended_contract(files: Files) -> dict[str, Any]:
    ids_sha = files.digest(EXTENDED_AIME_IDS_PATH)
    return {
        "client_concurrency": 1,
        "diagnostic_only": True,
        "enable_thinking": False,
        "expect_count": 1,
        "formally_comparable": False,
        "head_mode": "full",
        "ids": [EXTENDED_AIME_ID],
        "ids_sha256": ids_sha,
        "k": 1,
        "max_tokens": EXTENDED_AIME_MAX_TOKENS,
        "min_tokens": 0,
        "model": "laguna-xs-2.1",
        "modifies_primary_quality_result": False,
        "request_timeout_s": 900,
        "retroactively_validates_primary_quick_result": False,
        "save_text": True,
        "seed": 1234,
        "suite": "aime",
        "temperature": 0.0,
        "top_k": -1,
        "top_p": 1.0,
        "years": ["2024", "2025-I", "2025-II"],
    }


def validate_extended_shared_artifacts(
    files: Files,
    shared: Any,
    baseline: dict[str, Any],
) -> dict[str, Any]:
    require(isinstance(shared, dict), "extended-AIME shared artifact identity is missing")
    verified: dict[str, Any] = {}
    for group in ("weights", "tokenizer"):
        descriptor = shared.get(group) or {}
        root_text = descriptor.get("path")
        expected_files = descriptor.get("files")
        require(
            isinstance(root_text, str)
            and root_text
            and isinstance(expected_files, dict)
            and expected_files,
            f"extended-AIME shared {group} identity differs",
        )
        root = Path(root_text).expanduser().resolve()
        group_refs: dict[str, Any] = {}
        for name, expected in sorted(expected_files.items()):
            require_sha256_value(expected, f"extended-AIME shared {group}/{name}")
            path = file_under(root, name)
            require(path.is_file(), f"extended-AIME shared artifact is missing: {path}")
            require(files.digest(path) == expected, f"extended-AIME shared artifact hash differs: {path}")
            group_refs[name] = files.ref(path)
        verified[group] = {"path": str(root), "files": group_refs}
    frozen = baseline["run_spec_artifacts"]
    weights = (shared.get("weights") or {}).get("files") or {}
    tokenizer = (shared.get("tokenizer") or {}).get("files") or {}
    require(
        weights.get("config.json") == frozen["weights_config_sha256"]
        and weights.get("model.safetensors.index.json")
        == frozen["weights_index_sha256"]
        and weights.get(".benchmark-source.sha256")
        == frozen["transform_marker_sha256"],
        "extended-AIME shared weights differ from the frozen baseline",
    )
    require(
        tokenizer.get("config.json") == frozen["reference_config_sha256"],
        "extended-AIME shared tokenizer config differs from the frozen baseline",
    )
    return verified


def validate_extended_bundle(
    files: Files,
    arm_dir: Path,
    identity: dict[str, Any],
    manifest: dict[str, Any],
    manifest_sha256: str,
    baseline: dict[str, Any],
    primary: dict[str, Any],
    evaluator: dict[str, Any],
) -> dict[str, Any]:
    artifact_dir = arm_dir / "artifacts"
    spec_path = arm_dir / "run-spec.json"
    identity_path = artifact_dir / "identity.json"
    require(artifact_dir.is_dir(), f"rank {identity['rank']} extended-AIME artifact bundle is missing")
    require(spec_path.is_file(), f"rank {identity['rank']} extended-AIME run spec is missing")
    require(identity_path.is_file(), f"rank {identity['rank']} extended-AIME artifact identity is missing")
    files.observe_directory(artifact_dir)

    artifact_identity = files.json(identity_path)
    expected_names = {
        "builder.json",
        "candidate-bridge",
        "candidate-bridge.source.sha256",
        "mlx.metallib",
        "mlx.metallib.fingerprint",
        "quality-bridge-wrapper.sh",
        "ids.json",
        "quality-artifact.json",
    }
    recorded_files = artifact_identity.get("files")
    require(
        artifact_identity.get("schema") == f"{EXTENDED_AIME_SCHEMA}-artifact"
        and isinstance(recorded_files, dict)
        and set(recorded_files) == expected_names,
        f"rank {identity['rank']} extended-AIME artifact identity differs",
    )
    artifact_refs: dict[str, Any] = {}
    recomputed_files: dict[str, Any] = {}
    for name in sorted(expected_names):
        path = artifact_dir / name
        require(path.is_file() and not path.is_symlink(), f"rank {identity['rank']} artifact is missing: {name}")
        ref = files.ref(path)
        artifact_refs[name] = ref
        recomputed_files[name] = {"bytes": ref["bytes"], "sha256": ref["sha256"]}
    require(recorded_files == recomputed_files, f"rank {identity['rank']} preserved artifact hashes differ")

    builder = files.json(artifact_dir / "builder.json")
    require(
        builder == artifact_identity.get("builder")
        and builder.get("schema") == f"{EXTENDED_AIME_SCHEMA}-artifact-builder",
        f"rank {identity['rank']} artifact builder provenance differs",
    )
    runner = builder.get("runner") or {}
    require(
        Path(str(runner.get("path", ""))).resolve() == EXTENDED_AIME_RUNNER_PATH.resolve()
        and SHA256_RE.fullmatch(str(runner.get("sha256", ""))) is not None,
        f"rank {identity['rank']} artifact runner provenance differs",
    )
    require(
        files.json_value(artifact_dir / "ids.json") == [EXTENDED_AIME_ID]
        and artifact_refs["ids.json"]["sha256"] == files.digest(EXTENDED_AIME_IDS_PATH),
        f"rank {identity['rank']} frozen extended-AIME IDs differ",
    )
    require(
        artifact_refs["quality-bridge-wrapper.sh"]["sha256"] == files.digest(WRAPPER_PATH),
        f"rank {identity['rank']} preserved wrapper differs",
    )
    require(
        artifact_refs["mlx.metallib"]["sha256"] == primary["metallib_sha256"],
        f"rank {identity['rank']} preserved metallib differs from primary evidence",
    )
    require(
        files.text(artifact_dir / "candidate-bridge.source.sha256").strip()
        == primary["bridge_source_sha256"],
        f"rank {identity['rank']} preserved bridge source differs from primary evidence",
    )

    spec = files.json(spec_path)
    arm = {
        "rank": identity["rank"],
        "submission_id": identity["submission_id"],
        "source_ref": identity["source_ref"],
    }
    require(spec.get("schema") == f"{EXTENDED_AIME_SCHEMA}-run-spec", f"rank {identity['rank']} diagnostic schema differs")
    require(spec.get("study") == manifest["study"] and spec.get("phase") == "diagnostic_extended_aime", f"rank {identity['rank']} diagnostic identity differs")
    require(spec.get("arm") == arm, f"rank {identity['rank']} diagnostic arm differs")
    require(spec.get("harness_ref") == manifest["harness_commit"], f"rank {identity['rank']} diagnostic harness differs")
    require(spec.get("manifest_sha256") == manifest_sha256, f"rank {identity['rank']} diagnostic manifest differs")
    require(spec.get("environment") == manifest["required_environment"], f"rank {identity['rank']} diagnostic environment differs")
    require(spec.get("host_contract") == manifest["host"], f"rank {identity['rank']} diagnostic host contract differs")
    require(spec.get("runner") == runner, f"rank {identity['rank']} diagnostic runner differs")
    evaluator_spec = spec.get("evaluator") or {}
    require(
        evaluator_spec.get("commit") == manifest.get("evaluator_commit")
        and evaluator_spec.get("sha256") == manifest["evaluator_sha256"]
        and evaluator_spec.get("aime_eval_sha256")
        == evaluator["files"]["upstream/aime_eval.py"]["sha256"],
        f"rank {identity['rank']} diagnostic evaluator provenance differs",
    )
    require(
        spec.get("diagnostic_contract") == expected_extended_contract(files),
        f"rank {identity['rank']} diagnostic command contract differs",
    )
    require(spec.get("artifacts") == artifact_identity, f"rank {identity['rank']} diagnostic artifact binding differs")

    primary_spec = spec.get("primary_evidence") or {}
    expected_primary_refs = {
        "terminal_marker": (primary["marker_path"], primary["marker_ref"]["sha256"]),
        "run_spec": (primary["run_spec_path"], primary["run_spec_ref"]["sha256"]),
        "run": (primary["run_path"], primary["run_ref"]["sha256"]),
        "aime": (primary["aime_path"], primary["aime_ref"]["sha256"]),
    }
    for name, (path, digest) in expected_primary_refs.items():
        descriptor = primary_spec.get(name) or {}
        require(
            Path(str(descriptor.get("path", ""))).resolve() == path.resolve()
            and descriptor.get("sha256") == digest,
            f"rank {identity['rank']} diagnostic primary {name} binding differs",
        )
    require(primary_spec.get("frozen_item") == primary["frozen_item"], f"rank {identity['rank']} diagnostic frozen item differs")
    require(
        (primary_spec.get("real_bridge") or {}).get("sha256") == primary["bridge_ref"]["sha256"]
        and (primary_spec.get("real_bridge") or {}).get("source_sha256")
        == primary["bridge_source_sha256"],
        f"rank {identity['rank']} diagnostic bridge binding differs",
    )
    require(primary_spec.get("metallib_sha256") == primary["metallib_sha256"], f"rank {identity['rank']} diagnostic metallib binding differs")
    require(primary_spec.get("editable_source_sha256") == primary["editable_source_sha256"], f"rank {identity['rank']} diagnostic source binding differs")

    shared_refs = validate_extended_shared_artifacts(files, spec.get("shared_artifacts"), baseline)
    artifact_manifest = files.json(artifact_dir / "quality-artifact.json")
    require(
        artifact_manifest
        == {
            "weights": (spec["shared_artifacts"]["weights"])["path"],
            "tokenizer": (spec["shared_artifacts"]["tokenizer"])["path"],
            "bridge": "quality-bridge-wrapper.sh",
            "metallib": "mlx.metallib",
        },
        f"rank {identity['rank']} quality artifact manifest differs",
    )
    return {
        "spec": spec,
        "spec_ref": files.ref(spec_path),
        "artifact_identity": artifact_identity,
        "artifact_identity_ref": files.ref(identity_path),
        "artifacts": artifact_refs,
        "shared_artifacts": shared_refs,
        "recorded_runner_sha256": runner["sha256"],
        "current_runner_sha256": files.digest(EXTENDED_AIME_RUNNER_PATH),
        "current_runner_matches_recorded": runner["sha256"]
        == files.digest(EXTENDED_AIME_RUNNER_PATH),
    }


def extended_attempt_inventory(
    files: Files,
    arm_dir: Path,
    identity: dict[str, Any],
    bundle: dict[str, Any] | None,
    primary: dict[str, Any],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    if not arm_dir.is_dir():
        return []
    names = sorted(
        (
            path.name
            for path in arm_dir.iterdir()
            if path.is_dir()
            and (re.fullmatch(r"build-attempt-[1-9][0-9]*", path.name) or ATTEMPT_RE.fullmatch(path.name))
        ),
        key=lambda name: (0 if name.startswith("build-") else 1, int(name.split("-")[-1])),
    )
    arm = {
        "rank": identity["rank"],
        "submission_id": identity["submission_id"],
        "source_ref": identity["source_ref"],
    }
    inventory: list[dict[str, Any]] = []
    for name in names:
        attempt_dir = arm_dir / name
        row: dict[str, Any] = {
            "attempt": name,
            "selected": False,
            "retained_artifacts": retained_tree(files, attempt_dir),
        }
        started_path = attempt_dir / "started.json"
        finished_path = attempt_dir / "finished.json"
        if not started_path.is_file():
            row.update(status="in_progress_or_interrupted", reason="missing_started_record")
            inventory.append(row)
            continue
        started = files.json(started_path)
        if name.startswith("build-"):
            require(started.get("schema") == f"{EXTENDED_AIME_SCHEMA}-build-started", f"rank {identity['rank']} build-attempt start schema differs")
            require(started.get("arm") == arm and started.get("source_ref") == identity["source_ref"], f"rank {identity['rank']} build-attempt identity differs")
            require(started.get("harness_ref") == manifest["harness_commit"], f"rank {identity['rank']} build-attempt harness differs")
            runner = started.get("runner") or {}
            require(
                Path(str(runner.get("path", ""))).resolve() == EXTENDED_AIME_RUNNER_PATH.resolve()
                and SHA256_RE.fullmatch(str(runner.get("sha256", ""))) is not None,
                f"rank {identity['rank']} build-attempt runner differs",
            )
            frozen_runner = (
                (bundle["artifact_identity"].get("builder") or {}).get("runner")
                if bundle is not None
                else None
            )
            row.update(
                runner_sha256=runner["sha256"],
                matches_frozen_bundle_runner=(
                    frozen_runner is None or runner == frozen_runner
                ),
            )
            if not finished_path.is_file():
                row.update(status="in_progress_or_interrupted", reason="missing_finished_record")
            else:
                finished = files.json(finished_path)
                require(finished.get("schema") == f"{EXTENDED_AIME_SCHEMA}-build-finished", f"rank {identity['rank']} build-attempt finish schema differs")
                log_path = attempt_dir / "build.log"
                require(log_path.is_file(), f"rank {identity['rank']} build-attempt log is missing")
                require(finished.get("log_sha256") == files.digest(log_path), f"rank {identity['rank']} build-attempt log hash differs")
                exit_code = finished.get("exit_code")
                require(isinstance(exit_code, int) and not isinstance(exit_code, bool), f"rank {identity['rank']} build-attempt exit code differs")
                row.update(
                    status="successful_build" if exit_code == 0 else "infrastructure_failure",
                    exit_code=exit_code,
                    error=finished.get("error"),
                    finished=files.ref(finished_path),
                )
            inventory.append(row)
            continue

        require(started.get("schema") == f"{EXTENDED_AIME_SCHEMA}-attempt-started", f"rank {identity['rank']} diagnostic-attempt start schema differs")
        require(started.get("arm") == arm, f"rank {identity['rank']} diagnostic-attempt identity differs")
        require(started.get("primary_terminal_marker_sha256") == primary["marker_ref"]["sha256"], f"rank {identity['rank']} diagnostic-attempt primary binding differs")
        if bundle is not None:
            require(started.get("run_spec_sha256") == bundle["spec_ref"]["sha256"], f"rank {identity['rank']} diagnostic-attempt run-spec binding differs")
            require(started.get("artifact_identity_sha256") == bundle["artifact_identity_ref"]["sha256"], f"rank {identity['rank']} diagnostic-attempt artifact binding differs")
        if not finished_path.is_file():
            row.update(status="in_progress_or_interrupted", reason="missing_finished_record")
            inventory.append(row)
            continue
        finished = files.json(finished_path)
        require(finished.get("schema") == f"{EXTENDED_AIME_SCHEMA}-attempt-finished", f"rank {identity['rank']} diagnostic-attempt finish schema differs")
        require(finished.get("arm") == arm, f"rank {identity['rank']} diagnostic-attempt finished identity differs")
        require(bundle is not None, f"rank {identity['rank']} finished diagnostic lacks a frozen bundle")
        require(finished.get("run_spec_sha256") == bundle["spec_ref"]["sha256"], f"rank {identity['rank']} diagnostic-attempt finished run-spec differs")
        require(finished.get("shared_artifacts_after") == bundle["spec"].get("shared_artifacts"), f"rank {identity['rank']} diagnostic shared artifacts changed")
        recorded_hashes = finished.get("hashes")
        require(isinstance(recorded_hashes, dict), f"rank {identity['rank']} diagnostic-attempt hashes are missing")
        for artifact_name, expected in recorded_hashes.items():
            path = file_under(attempt_dir, artifact_name)
            require(path.is_file(), f"rank {identity['rank']} diagnostic-attempt artifact is missing: {artifact_name}")
            require(files.digest(path) == expected, f"rank {identity['rank']} diagnostic-attempt artifact hash differs: {artifact_name}")
        exit_code = finished.get("exit_code")
        server_exit = finished.get("server_exit_code")
        require(isinstance(exit_code, int) and not isinstance(exit_code, bool), f"rank {identity['rank']} diagnostic-attempt exit code differs")
        valid_server_exit = (
            isinstance(server_exit, int)
            and not isinstance(server_exit, bool)
            and server_exit in (0, 130)
        )
        clean_completion = (
            exit_code == 0
            and finished.get("server_shutdown_clean") is True
            and valid_server_exit
            and finished.get("error") is None
        )
        row.update(
            status="completed_unselected" if clean_completion else "infrastructure_failure",
            exit_code=exit_code,
            server_exit_code=server_exit,
            server_shutdown_clean=finished.get("server_shutdown_clean"),
            error=finished.get("error"),
            finished=files.ref(finished_path),
        )
        inventory.append(row)
    return inventory


def validate_extended_completion(
    files: Files,
    arm_dir: Path,
    identity: dict[str, Any],
    bundle: dict[str, Any],
    primary: dict[str, Any],
    manifest: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    marker_path = arm_dir / "completed.json"
    marker = files.json(marker_path)
    arm = {
        "rank": identity["rank"],
        "submission_id": identity["submission_id"],
        "source_ref": identity["source_ref"],
    }
    require(marker.get("schema") == f"{EXTENDED_AIME_SCHEMA}-completed", f"rank {identity['rank']} completion schema differs")
    require(marker.get("status") == "completed_diagnostic", f"rank {identity['rank']} completion status differs")
    require(marker.get("study") == manifest["study"] and marker.get("arm") == arm, f"rank {identity['rank']} completion identity differs")
    interpretation = marker.get("interpretation") or {}
    require(
        interpretation.get("diagnostic_only") is True
        and interpretation.get("formally_comparable") is False
        and interpretation.get("local_retention_gate_evaluated") is False
        and interpretation.get("primary_quick_result_changed") is False,
        f"rank {identity['rank']} diagnostic-only interpretation differs",
    )
    require(marker.get("primary_terminal_marker_sha256") == primary["marker_ref"]["sha256"], f"rank {identity['rank']} completion primary binding differs")
    attempt_name = marker.get("attempt")
    require(isinstance(attempt_name, str) and ATTEMPT_RE.fullmatch(attempt_name), f"rank {identity['rank']} completion attempt differs")
    matching_attempts = [row for row in attempts if row["attempt"] == attempt_name]
    require(len(matching_attempts) == 1, f"rank {identity['rank']} selected diagnostic attempt is missing")
    selected = matching_attempts[0]
    require(selected.get("status") == "completed_unselected", f"rank {identity['rank']} selected diagnostic attempt did not complete cleanly")
    selected["selected"] = True
    selected["status"] = "selected_completed_attempt"

    artifacts = marker.get("artifacts") or {}
    expected_paths = {
        "run_spec": arm_dir / "run-spec.json",
        "finished": arm_dir / attempt_name / "finished.json",
        "result": arm_dir / attempt_name / "aime-extended.json",
        "request_journal": arm_dir / attempt_name / "responses.jsonl",
    }
    artifact_refs: dict[str, Any] = {}
    for name, expected_path in expected_paths.items():
        descriptor = artifacts.get(name) or {}
        path = file_under(arm_dir, str(descriptor.get("path", "")))
        require(path == expected_path.resolve(), f"rank {identity['rank']} completion {name} path differs")
        require(path.is_file(), f"rank {identity['rank']} completion {name} is missing")
        require(descriptor.get("sha256") == files.digest(path), f"rank {identity['rank']} completion {name} hash differs")
        artifact_refs[name] = files.ref(path)
    require(artifact_refs["run_spec"]["sha256"] == bundle["spec_ref"]["sha256"], f"rank {identity['rank']} completion run-spec binding differs")
    require((artifacts.get("request_journal") or {}).get("records") == 1, f"rank {identity['rank']} completion request count differs")

    result = files.json(expected_paths["result"])
    require(result.get("label") == f"top15-extended-aime-{identity['rank']}-{identity['submission_id']}", f"rank {identity['rank']} diagnostic label differs")
    require(result.get("model") == "laguna-xs-2.1", f"rank {identity['rank']} diagnostic model differs")
    require(result.get("years") == ["2024", "2025-I", "2025-II"], f"rank {identity['rank']} diagnostic years differ")
    require(result.get("k") == 1 and result.get("maj_k") == 1 and result.get("client_concurrency") == 1, f"rank {identity['rank']} diagnostic sampling shape differs")
    require(result.get("n_problems") == 1 and result.get("total_samples") == 1, f"rank {identity['rank']} diagnostic result shape differs")
    require(
        result.get("sampling")
        == {
            "temperature": 0.0,
            "top_p": 1.0,
            "top_k": -1,
            "max_tokens": EXTENDED_AIME_MAX_TOKENS,
            "min_tokens": 0,
            "seed": 1234,
            "enable_thinking": False,
        },
        f"rank {identity['rank']} diagnostic sampling contract differs",
    )
    rows = result.get("per_problem")
    require(isinstance(rows, list) and len(rows) == 1, f"rank {identity['rank']} diagnostic row count differs")
    row = rows[0]
    require(
        isinstance(row, dict)
        and row.get("id") == EXTENDED_AIME_ID
        and row.get("year") == "2024"
        and row.get("prompt_sha") == primary["frozen_item"]["prompt_sha256"]
        and row.get("gold") == primary["frozen_item"]["gold"]
        and row.get("k") == 1
        and len(row.get("answers") or []) == 1
        and len(row.get("sample_chars") or []) == 1
        and len(row.get("texts") or []) == 1
        and row.get("finish_reasons") in (["stop"], ["length"]),
        f"rank {identity['rank']} diagnostic frozen row differs",
    )
    journal = json_stream(files, expected_paths["request_journal"])
    require(len(journal) == 1 and isinstance(journal[0], dict), f"rank {identity['rank']} diagnostic journal shape differs")
    record = journal[0]
    request = record.get("request") or {}
    require(record.get("endpoint") == "/v1/chat/completions" and record.get("status") == 200, f"rank {identity['rank']} diagnostic request failed")
    require(
        request.get("model") == "laguna-xs-2.1"
        and request.get("n") == 1
        and request.get("temperature") == 0.0
        and request.get("top_p") == 1.0
        and request.get("top_k") == -1
        and request.get("seed") == 1234
        and request.get("max_tokens") == EXTENDED_AIME_MAX_TOKENS
        and request.get("min_tokens") == 0,
        f"rank {identity['rank']} diagnostic request contract differs",
    )
    prompt_payload = json.dumps(
        {"messages": request.get("messages"), "gold": row["gold"]},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    require(hash_text(prompt_payload.encode()) == row["prompt_sha"], f"rank {identity['rank']} diagnostic request prompt differs")
    choices = (record.get("response") or {}).get("choices") or []
    require(
        isinstance(choices, list)
        and len(choices) == 1
        and isinstance(choices[0], dict),
        f"rank {identity['rank']} diagnostic response shape differs",
    )
    journal_finish = [
        choice.get("finish_reason")
        for choice in choices
        if isinstance(choice, dict)
    ]
    require(journal_finish == row["finish_reasons"], f"rank {identity['rank']} diagnostic journal finish reason differs")
    message = choices[0].get("message") or {}
    completion_text = message.get("content")
    require(
        message.get("role") == "assistant" and isinstance(completion_text, str),
        f"rank {identity['rank']} diagnostic response content differs",
    )
    extracted_answer = extract_aime_answer(completion_text)
    answer_counts = {} if extracted_answer is None else {str(extracted_answer): 1}
    correct = extracted_answer == row["gold"]
    require(
        row["texts"] == [completion_text]
        and row["sample_chars"] == [len(completion_text)]
        and row["answers"] == [extracted_answer]
        and row.get("answer_counts") == answer_counts
        and row.get("maj_answer") == extracted_answer
        and row.get("maj_correct") is correct
        and row.get("correct_samples") == int(correct)
        and close(row.get("pass_rate"), float(correct)),
        f"rank {identity['rank']} diagnostic result differs from request journal",
    )
    require(
        result.get("n_correct_maj") == int(correct)
        and close(result.get("maj_k_accuracy"), float(correct))
        and close(result.get("mean_pass_rate"), float(correct))
        and close(
            result.get("extract_fail_rate"),
            1.0 if extracted_answer is None else 0.0,
        ),
        f"rank {identity['rank']} diagnostic aggregate metrics differ",
    )

    finish_reason = row["finish_reasons"][0]
    outcome = "completed_before_extended_ceiling" if finish_reason == "stop" else "still_length_bounded_at_6144"
    require(marker.get("outcome") == outcome, f"rank {identity['rank']} diagnostic outcome differs")
    frozen_item = marker.get("frozen_item") or {}
    require(
        frozen_item
        == {
            "id": EXTENDED_AIME_ID,
            "prompt_sha256": row["prompt_sha"],
            "gold": row["gold"],
            "answer": row["answers"][0],
            "maj_correct": row.get("maj_correct"),
            "finish_reason": finish_reason,
            "sample_chars": row["sample_chars"][0],
            "max_tokens": EXTENDED_AIME_MAX_TOKENS,
        },
        f"rank {identity['rank']} completion frozen-item summary differs",
    )
    host = marker.get("host_identity") or {}
    require(
        host.get("model") == manifest["host"]["model"]
        and host.get("chip") == manifest["host"]["chip"]
        and host.get("memory") == f"{manifest['host']['memory_gb']} GB",
        f"rank {identity['rank']} completion host differs",
    )
    return {
        "status": "valid_completed_diagnostic",
        "formal_comparison": False,
        "selected_attempt": attempt_name,
        "outcome": outcome,
        "frozen_item": frozen_item,
        "artifacts": {
            "completion_marker": files.ref(marker_path),
            **artifact_refs,
        },
    }


def audit_extended_arm(
    files: Files,
    primary_results: Path,
    results: Path,
    identity: dict[str, Any],
    manifest: dict[str, Any],
    manifest_sha256: str,
    baseline: dict[str, Any],
    evaluator: dict[str, Any] | None,
) -> dict[str, Any]:
    arm_dir = results / f"{identity['rank']}-{identity['submission_id']}"
    files.observe_directory(arm_dir)
    row: dict[str, Any] = {"path": relative(arm_dir)}
    try:
        primary = extended_primary_evidence(files, primary_results, identity)
        row["primary_evidence"] = {
            "terminal_marker": primary["marker_ref"],
            "run_spec": primary["run_spec_ref"],
            "run": primary["run_ref"],
            "aime": primary["aime_ref"],
            "frozen_item": primary["frozen_item"],
            "editable_source_sha256": primary["editable_source_sha256"],
            "metallib_sha256": primary["metallib_sha256"],
            "bridge_source_sha256": primary["bridge_source_sha256"],
        }
        if not arm_dir.is_dir():
            return {**row, "status": "pending", "reason": "arm_directory_absent", "attempts": []}
        bundle: dict[str, Any] | None = None
        has_bundle_input = (arm_dir / "artifacts").exists() or (arm_dir / "run-spec.json").exists()
        if has_bundle_input:
            require(evaluator is not None, f"rank {identity['rank']} diagnostic evaluator is not pinned")
            bundle = validate_extended_bundle(
                files,
                arm_dir,
                identity,
                manifest,
                manifest_sha256,
                baseline,
                primary,
                evaluator,
            )
            row["bundle"] = {
                key: value
                for key, value in bundle.items()
                if key not in {"spec", "artifact_identity"}
            }
        attempts = extended_attempt_inventory(
            files, arm_dir, identity, bundle, primary, manifest
        )
        row["attempts"] = attempts
        if bundle is not None:
            producer = (
                (bundle["artifact_identity"].get("builder") or {}).get(
                    "build_attempt"
                )
            )
            matching_producers = [
                attempt
                for attempt in attempts
                if attempt["attempt"] == producer
                and attempt.get("status") == "successful_build"
                and attempt.get("matches_frozen_bundle_runner") is True
            ]
            require(
                len(matching_producers) == 1,
                f"rank {identity['rank']} frozen bundle lacks its matching successful build attempt",
            )
        completed = arm_dir / "completed.json"
        if completed.is_file():
            require(bundle is not None, f"rank {identity['rank']} completion lacks a frozen bundle")
            return {
                **row,
                **validate_extended_completion(
                    files,
                    arm_dir,
                    identity,
                    bundle,
                    primary,
                    manifest,
                    attempts,
                ),
            }
        retained_failures = sum(
            attempt.get("status") == "infrastructure_failure" for attempt in attempts
        )
        return {
            **row,
            "status": "pending",
            "reason": "no_valid_completion_marker",
            "retained_infrastructure_failures": retained_failures,
        }
    except (AuditFailure, KeyError, OSError, TypeError) as error:
        return {**row, "status": "invalid", "errors": [str(error)]}


def official_row(identity: dict[str, Any], predecessor: dict[str, Any] | None) -> dict[str, Any]:
    score_recomputed = identity["decode_speedup"] ** 0.75 * identity["prefill_speedup"] ** 0.25
    incremental = None
    if predecessor:
        decode_ratio = predecessor["decode_ms_per_token"] / identity["decode_ms_per_token"]
        prefill_ratio = predecessor["prefill_ms_per_token"] / identity["prefill_ms_per_token"]
        incremental = {
            "score_delta": identity["score"] - predecessor["score"],
            "decode_absolute_ratio_vs_prior_snapshot": decode_ratio,
            "prefill_absolute_ratio_vs_prior_snapshot": prefill_ratio,
            "weighted_absolute_ratio_vs_prior_snapshot": decode_ratio**0.75 * prefill_ratio**0.25,
            "warning": "Absolute phase values come from different paired official sessions; this is descriptive, not an isolated causal estimate.",
        }
    return {
        "score": identity["score"],
        "decode_speedup": identity["decode_speedup"],
        "decode_ms_per_token": identity["decode_ms_per_token"],
        "prefill_speedup": identity["prefill_speedup"],
        "prefill_ms_per_token": identity["prefill_ms_per_token"],
        "score_recomputed": score_recomputed,
        "score_recomputation_error": score_recomputed - identity["score"],
        "incremental_vs_preceding_rank": incremental,
    }


def add_local_comparisons(rows: list[dict[str, Any]], comparator: dict[str, Any]) -> None:
    comparator_result = comparator["performance"]
    comparator_metrics = comparator_result.get("metrics") if comparator_result.get("status") == "valid_selected_attempt" else None
    previous_metrics = comparator_metrics
    for row in rows:
        performance = row["performance"]
        metrics = performance.get("metrics") if performance.get("status") == "valid_selected_attempt" else None
        if metrics and comparator_metrics:
            decode = comparator_metrics["decode_seconds_per_token"] / metrics["decode_seconds_per_token"]
            prefill = comparator_metrics["prefill_seconds_per_token"] / metrics["prefill_seconds_per_token"]
            performance["comparison_to_rank111"] = {
                "decode_speedup": decode,
                "prefill_speedup": prefill,
                "weighted_index": decode**0.75 * prefill**0.25,
            }
        else:
            performance["comparison_to_rank111"] = None
        if metrics and previous_metrics:
            decode = previous_metrics["decode_seconds_per_token"] / metrics["decode_seconds_per_token"]
            prefill = previous_metrics["prefill_seconds_per_token"] / metrics["prefill_seconds_per_token"]
            performance["comparison_to_preceding_rank"] = {
                "decode_speedup": decode,
                "prefill_speedup": prefill,
                "weighted_index": decode**0.75 * prefill**0.25,
            }
        else:
            performance["comparison_to_preceding_rank"] = None
        previous_metrics = metrics


def enforce_controlled_golden_drift(
    comparator: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    """Mirror the runner's M4-only drift-signature acceptance rule."""

    selected = [
        comparator["performance"],
        *(row["performance"] for row in rows),
    ]
    selected = [result for result in selected if result.get("status") == "valid_selected_attempt"]
    settings = {
        result["metrics"].get("allow_golden_drift")
        for result in selected
    }
    if len(settings) > 1:
        for result in selected:
            result["status"] = "invalid"
            result["errors"] = ["selected performance arms use mixed golden-drift settings"]
        return

    comparator_result = comparator["performance"]
    if comparator_result.get("status") != "valid_selected_attempt":
        return
    comparator_metrics = comparator_result["metrics"]
    comparator_signature = comparator_metrics.get("controlled_drift_signature")
    for row in rows:
        result = row["performance"]
        if result.get("status") != "valid_selected_attempt":
            continue
        metrics = result["metrics"]
        signature = metrics.get("controlled_drift_signature")
        if metrics.get("passed_correctness") is False and (
            comparator_metrics.get("passed_correctness") is not False
            or signature != comparator_signature
        ):
            result["status"] = "invalid"
            result["errors"] = [
                "candidate golden-drift signature does not match the rank-111 comparator"
            ]


def classify_result_directories(
    results: Path, expected: dict[str, set[str]]
) -> dict[str, dict[str, list[str]]]:
    known: dict[str, list[str]] = {}
    unknown: dict[str, list[str]] = {}
    for scope in ("root", "performance", "quality"):
        root = results if scope == "root" else results / scope
        actual = (
            {path.name for path in root.iterdir() if path.is_dir()}
            if root.is_dir()
            else set()
        )
        allowlisted = KNOWN_AUXILIARY_RESULT_DIRECTORIES[scope]
        known[scope] = sorted((actual - expected[scope]) & allowlisted)
        unknown[scope] = sorted(actual - expected[scope] - allowlisted)
    return {"known_auxiliary": known, "unknown": unknown}


def build_payload(
    results: Path,
    control_results: Path = DEFAULT_CONTROL_RESULTS,
    extended_aime_results: Path = DEFAULT_EXTENDED_AIME_RESULTS,
) -> tuple[dict[str, Any], Files]:
    results = results.resolve()
    control_results = control_results.resolve()
    extended_aime_results = extended_aime_results.resolve()
    require(results.is_relative_to(REPO), "results directory must be inside the repository")
    require(control_results.is_relative_to(REPO), "control results directory must be inside the repository")
    require(extended_aime_results.is_relative_to(REPO), "extended-AIME results directory must be inside the repository")
    require(
        len({results, control_results, extended_aime_results}) == 3,
        "primary, control, and extended-AIME result roots must be distinct",
    )
    files = Files(REPO)
    files.observe_directory(results)
    files.observe_directory(results / "performance")
    files.observe_directory(results / "quality")
    files.observe_directory(control_results)
    files.observe_directory(control_results / "quality")
    files.observe_directory(extended_aime_results)
    manifest, candidates = load_manifest(files)
    manifest_ref = files.ref(MANIFEST_PATH)
    manifest_sha256 = manifest_ref["sha256"]
    final_report_ref = files.ref(FINAL_REPORT_PATH)
    official_findings_ref = files.ref(OFFICIAL_FINDINGS_PATH)
    local_benchmark_ref = files.ref(LOCAL_BENCHMARK_PATH)
    fan_control_ref = files.ref(FAN_CONTROL_PATH)
    require(final_report_ref["bytes"] > 0, "REPORT.md is empty")
    require(official_findings_ref["bytes"] > 0, "official-findings.md is empty")
    require(
        local_benchmark_ref["sha256"] == PINNED_LOCAL_BENCHMARK_SHA256,
        "local fail-closed benchmark SHA differs",
    )
    require(
        fan_control_ref["sha256"] == PINNED_FAN_CONTROL_SHA256,
        "local fan-control SHA differs",
    )
    final_report_markers = performance_completion_markers(
        files.text(FINAL_REPORT_PATH)
    )
    final_markdown_complete = not final_report_markers
    control_definition, control_run, controls = load_control_manifests(files, manifest)
    control_definition_ref = files.ref(CONTROL_DEFINITION_PATH)
    control_run_ref = files.ref(CONTROL_RUN_PATH)
    extended_ids = files.json_value(EXTENDED_AIME_IDS_PATH)
    require(
        extended_ids == [EXTENDED_AIME_ID],
        f"extended-AIME IDs must contain only {EXTENDED_AIME_ID}",
    )
    extended_ids_ref = files.ref(EXTENDED_AIME_IDS_PATH)
    extended_runner_ref = files.ref(EXTENDED_AIME_RUNNER_PATH)
    baseline = baseline_quality(files, manifest)
    baseline_rows = response_rows(files, baseline["root"])
    chain = source_chain(manifest)
    editable = harness_editable_paths(manifest["harness_commit"])
    expected_sources = {
        identity["source_ref"]: expected_editable_identity(identity["source_ref"], editable)
        for identity in [manifest["baseline"], *candidates, *controls]
    }

    control_contract = control_definition.get("local_evaluation_contract") or {}
    require(control_contract.get("profile") == "quick", "control quality profile differs")
    require(control_contract.get("downstream_attempts") == 53, "control downstream count differs")
    require(
        control_contract.get("minimum_downstream_correct")
        == baseline["gate"]["minimum_correct"],
        "control correct-count threshold differs from baseline",
    )
    require(
        control_contract.get("perplexity_target_tokens") == 256
        and close(
            control_contract.get("maximum_perplexity"),
            baseline["gate"]["maximum_ppl"],
            1e-6,
        ),
        "control perplexity contract differs from baseline",
    )
    require(
        control_contract.get("ranked_gpqa_cases") == 9
        and control_contract.get("minimum_ranked_gpqa_prefix_matches") == 7,
        "control ranked-GPQA contract differs from baseline",
    )

    comparator_identity = manifest["baseline"]
    comparator_performance = audit_performance_arm(
        files,
        results,
        comparator_identity,
        manifest,
        manifest_sha256,
        baseline,
        expected_sources[comparator_identity["source_ref"]],
    )
    comparator = {
        "rank": comparator_identity["rank"],
        "submission_id": comparator_identity["submission_id"],
        "source_ref": comparator_identity["source_ref"],
        "role": comparator_identity.get("role"),
        "expected_source_identity": expected_sources[comparator_identity["source_ref"]],
        "links": links(comparator_identity, None),
        "official": official_row(comparator_identity, None),
        "performance": comparator_performance,
    }

    rows: list[dict[str, Any]] = []
    predecessor = comparator_identity
    for candidate in candidates:
        performance = audit_performance_arm(
            files,
            results,
            candidate,
            manifest,
            manifest_sha256,
            baseline,
            expected_sources[candidate["source_ref"]],
        )
        quality = audit_quality_arm(
            files,
            results,
            candidate,
            manifest,
            manifest_sha256,
            baseline,
            baseline_rows,
            expected_sources[candidate["source_ref"]],
        )
        rows.append(
            {
                "rank": candidate["rank"],
                "submission_id": candidate["submission_id"],
                "source_ref": candidate["source_ref"],
                "pr": candidate.get("pr"),
                "mechanism": candidate.get("mechanism"),
                "expected_source_identity": expected_sources[candidate["source_ref"]],
                "predecessor": {
                    "rank": predecessor["rank"],
                    "source_ref": predecessor["source_ref"],
                },
                "links": links(candidate, predecessor),
                "official": official_row(candidate, predecessor),
                "performance": performance,
                "quality": quality,
            }
        )
        predecessor = candidate
    enforce_controlled_golden_drift(comparator, rows)
    add_local_comparisons(rows, comparator)

    control_rows: list[dict[str, Any]] = []
    for control in controls:
        quality = audit_quality_arm(
            files,
            control_results,
            control,
            control_run,
            control_run_ref["sha256"],
            baseline,
            baseline_rows,
            expected_sources[control["source_ref"]],
        )
        if quality.get("status") == "valid_selected_attempt":
            local_outcome = (
                "local_pass"
                if quality["gate"]["local_retention_gate_passed"]
                else "local_regression"
            )
        elif quality.get("status") == "terminal_noncompletion":
            local_outcome = "not_evaluable_bounded_noncompletion"
        else:
            local_outcome = None
        definition_row = control["definition"]
        control_rows.append(
            {
                "rank": control["rank"],
                "control_order": control["control_order"],
                "label": definition_row.get("label"),
                "submission_id": control["submission_id"],
                "source_ref": control["source_ref"],
                "mechanism": definition_row.get("mechanism"),
                "control_role": definition_row.get("control_role"),
                "independence_caveat": definition_row.get("independence_caveat"),
                "official": definition_row.get("official"),
                "expected_interpretation": definition_row.get(
                    "expected_interpretation"
                ),
                "expected_source_identity": expected_sources[control["source_ref"]],
                "links": links(control, None),
                "quality": quality,
                "local_outcome": local_outcome,
            }
        )
    control_statuses = Counter(row["quality"]["status"] for row in control_rows)
    control_outcomes = Counter(row["local_outcome"] for row in control_rows)

    snapshot_path = control_results / "current-snapshot.json"
    control_snapshot: dict[str, Any] | None = None
    if snapshot_path.is_file():
        snapshot = files.json(snapshot_path)
        matching = [
            control
            for control in controls
            if snapshot.get("source_ref") == control["source_ref"]
            and snapshot.get("label")
            == f"{control['rank']}-{control['submission_id']}"
        ]
        require(len(matching) == 1, "control current snapshot is not a frozen arm")
        require(
            snapshot.get("harness_ref") == control_run["harness_commit"],
            "control current snapshot harness differs",
        )
        control_snapshot = {"payload": snapshot, "artifact": files.ref(snapshot_path)}
    control_setup = retained_tree(files, control_results / "setup")
    primary_setup = retained_tree(files, results / "setup")
    retained_official_baseline_attempt = retained_tree(
        files, results / "performance" / "000-official-pinned-baseline"
    )

    extended_evaluator = audit_extended_evaluator(
        files, extended_aime_results, manifest
    )
    candidates_by_rank = {candidate["rank"]: candidate for candidate in candidates}
    extended_rows: list[dict[str, Any]] = []
    for rank in EXTENDED_AIME_RANKS:
        candidate = candidates_by_rank[rank]
        extended_rows.append(
            {
                "rank": rank,
                "submission_id": candidate["submission_id"],
                "source_ref": candidate["source_ref"],
                "diagnostic": audit_extended_arm(
                    files,
                    results,
                    extended_aime_results,
                    candidate,
                    manifest,
                    manifest_sha256,
                    baseline,
                    extended_evaluator,
                ),
            }
        )
    extended_statuses = Counter(
        row["diagnostic"]["status"] for row in extended_rows
    )
    retained_extended_failures = sum(
        attempt.get("status") == "infrastructure_failure"
        for row in extended_rows
        for attempt in row["diagnostic"].get("attempts", [])
    )

    performance_statuses = Counter(
        [comparator_performance["status"], *(row["performance"]["status"] for row in rows)]
    )
    quality_statuses = Counter(row["quality"]["status"] for row in rows)
    expected_dirs = {
        "root": {"performance", "quality"},
        "performance": {
            f"{comparator_identity['rank']}-{comparator_identity['submission_id']}",
            *(f"{candidate['rank']}-{candidate['submission_id']}" for candidate in candidates),
        },
        "quality": {
            f"{candidate['rank']}-{candidate['submission_id']}" for candidate in candidates
        },
    }
    result_directories = classify_result_directories(results, expected_dirs)
    control_expected_dirs = {
        "root": {"quality"},
        "performance": set(),
        "quality": {
            f"{control['rank']}-{control['submission_id']}" for control in controls
        },
    }
    control_result_directories = classify_result_directories(
        control_results, control_expected_dirs
    )
    extended_expected = {
        "_pinned-evaluator",
        *(
            f"{candidates_by_rank[rank]['rank']}-{candidates_by_rank[rank]['submission_id']}"
            for rank in EXTENDED_AIME_RANKS
        ),
    }
    extended_actual = (
        {
            path.name
            for path in extended_aime_results.iterdir()
            if path.is_dir()
        }
        if extended_aime_results.is_dir()
        else set()
    )
    unknown_extended_directories = sorted(extended_actual - extended_expected)
    unknown_result_directories = sum(
        len(names) for names in result_directories["unknown"].values()
    ) + sum(
        len(names) for names in control_result_directories["unknown"].values()
    ) + len(unknown_extended_directories)
    invalid = (
        performance_statuses["invalid"]
        + quality_statuses["invalid"]
        + control_statuses["invalid"]
        + extended_statuses["invalid"]
    )
    processed_quality = (
        quality_statuses["valid_selected_attempt"] + quality_statuses["terminal_noncompletion"]
    )
    processed_controls = (
        control_statuses["valid_selected_attempt"]
        + control_statuses["terminal_noncompletion"]
    )
    artifact_data_complete = (
        performance_statuses["valid_selected_attempt"] == 16
        and processed_quality == 15
        and processed_controls == 3
        and extended_statuses["valid_completed_diagnostic"] == 4
        and invalid == 0
        and unknown_result_directories == 0
    )
    ready_for_final_publication = artifact_data_complete and final_markdown_complete
    inputs = {
        "manifest": manifest_ref,
        "final_report": final_report_ref,
        "official_findings": official_findings_ref,
        "local_fail_closed_benchmark": local_benchmark_ref,
        "local_fan_control": fan_control_ref,
        "runner": files.ref(RUNNER_PATH),
        "negative_control_definition": control_definition_ref,
        "negative_control_run": control_run_ref,
        "control_current_snapshot": control_snapshot,
        "control_setup_artifacts": control_setup,
        "primary_setup_artifacts": primary_setup,
        "retained_official_baseline_attempt": {
            "selected": False,
            "reason": "auxiliary_failed_attempt_outside_frozen_16-arm cohort",
            "artifacts": retained_official_baseline_attempt,
        },
        "extended_aime_runner": extended_runner_ref,
        "extended_aime_ids": extended_ids_ref,
        "extended_aime_evaluator": extended_evaluator,
        "quality_bridge_wrapper": files.ref(WRAPPER_PATH),
        "public_correctness_fixture": files.ref(PUBLIC_FIXTURE_PATH),
        "readme": files.ref(README_PATH),
        "report_data_builder": files.ref(BUILDER_PATH),
        "quality_baseline": {
            key: value for key, value in baseline.items() if key not in {"run", "root"}
        },
    }
    payload = {
        "schema": "mlxfast-top15-report-data-v2",
        "study": manifest["study"],
        "leaderboard_snapshot_utc": manifest.get("leaderboard_snapshot_utc"),
        "host": manifest["host"],
        "contract": {
            "harness_commit": manifest["harness_commit"],
            "evaluator_commit": manifest.get("evaluator_commit"),
            "evaluator_sha256": manifest["evaluator_sha256"],
            "environment": manifest["required_environment"],
            "performance_mode": "--local-submit",
            "performance_runtime": "swift-local-submit",
            "golden_drift_policy": "Disabled unless every selected arm uses the runner's comparator-matched M4-only signature rule.",
            "score_formula": "decode_speedup^0.75 * prefill_speedup^0.25",
            "quality_gate": baseline["gate"],
            "terminal_noncompletion_policy": {
                "formal_comparison": False,
                "local_retention_gate_evaluated": False,
                "accepted_reason": "aime_length",
            },
            "negative_control_policy": {
                "separate_cohort": True,
                "performance_enabled": False,
                "processed_statuses": [
                    "valid_selected_attempt",
                    "terminal_noncompletion",
                ],
                "formal_comparisons_and_bounded_noncompletions_reported_separately": True,
            },
            "extended_aime_policy": {
                "diagnostic_only": True,
                "formally_comparable": False,
                "primary_quality_result_changed": False,
                "selected_only_by": "validated completed.json marker",
                "failed_and_infrastructure_attempts": "checksummed evidence; never selected",
                "frozen_id": EXTENDED_AIME_ID,
                "primary_max_tokens": PRIMARY_AIME_MAX_TOKENS,
                "diagnostic_max_tokens": EXTENDED_AIME_MAX_TOKENS,
            },
            "performance_source_provenance": {
                "expected_editable_digest_recomputed_from_git": True,
                "applied_editable_digest_emitted_by_performance_artifact": False,
                "binding": "trusted runner checkout contract plus declared source ref",
            },
        },
        "inputs": inputs,
        "source_chain": chain,
        "official_pinned_baseline": manifest.get("official_pinned_baseline"),
        "local_comparator": comparator,
        "candidates": rows,
        "negative_controls": {
            "study": control_run["study"],
            "definition": {
                "purpose": control_definition.get("purpose"),
                "selection": control_definition.get("selection"),
                "interpretation": control_definition.get("interpretation"),
                "provenance": control_definition.get("provenance"),
            },
            "controls": control_rows,
        },
        "extended_aime": {
            "results_path": relative(extended_aime_results),
            "frozen_ranks": list(EXTENDED_AIME_RANKS),
            "frozen_ids": extended_ids,
            "evaluator": extended_evaluator,
            "arms": extended_rows,
        },
        "final_markdown": {
            "complete": final_markdown_complete,
            "report_path": relative(FINAL_REPORT_PATH),
            "official_findings_path": relative(OFFICIAL_FINDINGS_PATH),
            "performance_completion_markers": final_report_markers,
            "completion_rule": (
                "REPORT.md must contain no positive placeholder marker, no "
                "performance pending/TODO/TBD marker, and no explicit absent "
                "or zero-of-16 performance-result marker"
            ),
        },
        "summary": {
            "performance": {
                "expected": 16,
                "valid_selected_attempts": performance_statuses["valid_selected_attempt"],
                "pending": performance_statuses["pending"],
                "invalid": performance_statuses["invalid"],
            },
            "quality": {
                "expected": 15,
                "valid_comparisons": quality_statuses["valid_selected_attempt"],
                "terminal_noncompletions": quality_statuses["terminal_noncompletion"],
                "processed": processed_quality,
                "pending": quality_statuses["pending"],
                "invalid": quality_statuses["invalid"],
            },
            "negative_controls": {
                "expected": 3,
                "valid_comparisons": control_statuses[
                    "valid_selected_attempt"
                ],
                "terminal_noncompletions": control_statuses[
                    "terminal_noncompletion"
                ],
                "processed": processed_controls,
                "concordant_local_regressions": control_outcomes[
                    "local_regression"
                ],
                "discordant_local_passes": control_outcomes["local_pass"],
                "not_evaluable": control_outcomes[
                    "not_evaluable_bounded_noncompletion"
                ],
                "pending": control_statuses["pending"],
                "invalid": control_statuses["invalid"],
            },
            "extended_aime": {
                "expected": 4,
                "valid_completed_diagnostics": extended_statuses[
                    "valid_completed_diagnostic"
                ],
                "pending": extended_statuses["pending"],
                "invalid": extended_statuses["invalid"],
                "retained_infrastructure_failures": retained_extended_failures,
            },
            "artifact_data_complete": artifact_data_complete,
            "final_markdown_complete": final_markdown_complete,
            "ready_for_final_report": ready_for_final_publication,
            "ready_for_final_publication": ready_for_final_publication,
            "audit_valid": invalid == 0 and unknown_result_directories == 0,
            "integrity": {
                "invalid_arms": invalid,
                "unknown_result_directories": unknown_result_directories,
            },
        },
        "known_auxiliary_result_directories": {
            "primary": result_directories["known_auxiliary"],
            "negative_controls": control_result_directories["known_auxiliary"],
            "extended_aime": ["_pinned-evaluator"]
            if "_pinned-evaluator" in extended_actual
            else [],
        },
        "untracked_result_directories": {
            "primary": result_directories["unknown"],
            "negative_controls": control_result_directories["unknown"],
            "extended_aime": {"root": unknown_extended_directories},
        },
        "checksum_manifest": {
            "path": relative(CHECKSUMS_PATH),
            "format": "SHA256SUMS",
            "excludes_itself": True,
            "includes_report_data_when_written": True,
            "includes_required_final_markdown_when_written": True,
            "required_final_markdown": [
                relative(path) for path in REQUIRED_PUBLICATION_PATHS
            ],
        },
        "limitations": [
            "Local measurements use Apple M4 Max with DARKBLOOM_EXPERT_ALIGNED_GATHER=0; official results use Apple M5 Max.",
            "A valid terminal_noncompletion preserves raw diagnostics but has no formal local retention-gate decision.",
            "Performance arms are single full local-submit observations and do not estimate variance.",
            "The three negative controls calibrate surrogate discrimination but are a deliberately selected diagnostic cohort, not an estimate of population false-positive rates.",
            "Extended-AIME runs are isolated diagnostics and never retroactively convert a primary bounded non-completion into a formal quality comparison.",
            "Extended-AIME bundles record the runner that built them; a later completion marker does not carry a separate completing-runner hash, so completion provenance is validated through the frozen run spec, attempt hashes, evaluator provenance, and diagnostic contract.",
            "Performance artifacts do not emit the applied editable-tree digest; source attribution relies on the checksummed runner's checkout contract and declared source ref.",
            "The builder snapshots and rechecks inputs before publication, but the study runner does not share its writer lock; a publication in the final syscall window is detectable only on the next audit.",
        ],
    }
    payload["checksum_manifest"]["entries_when_written"] = len(files.checksums) + 1
    return payload, files


def links(identity: dict[str, Any], predecessor: dict[str, Any] | None) -> dict[str, Any]:
    source = identity["source_ref"]
    links_payload: dict[str, Any] = {
        "submission": f"https://mlx.fast/api/submissions/{identity['submission_id']}",
        "commit": f"https://github.com/Layr-Labs/mlxfast-challenge/commit/{source}",
    }
    if identity.get("pr"):
        links_payload["pull_request"] = (
            f"https://github.com/Layr-Labs/mlxfast-challenge/pull/{identity['pr']}"
        )
    if predecessor:
        links_payload["compare_to_predecessor"] = (
            "https://github.com/Layr-Labs/mlxfast-challenge/compare/"
            f"{predecessor['source_ref']}...{source}"
        )
    return links_payload


def write_outputs(payload: dict[str, Any], files: Files) -> None:
    def stage(path: Path, prefix: str, data: bytes) -> Path:
        descriptor, name = tempfile.mkstemp(
            dir=path.parent,
            prefix=prefix,
            suffix=".tmp",
        )
        staged = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            staged.chmod(0o644)
        except BaseException:
            staged.unlink(missing_ok=True)
            raise
        return staged

    report_tmp: Path | None = None
    checksums_tmp: Path | None = None
    # The executable itself is a stable, repository-owned lock inode. This
    # avoids introducing a persistent lock artifact into the study directory.
    with BUILDER_PATH.open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        files.verify_unchanged()
        try:
            report_bytes = canonical_json(payload)
        except ValueError as error:
            raise AuditFailure(f"report payload is not canonical JSON: {error}") from error
        checksum_bytes = checksum_manifest_bytes(files.checksums, report_bytes)
        try:
            report_tmp = stage(REPORT_PATH, ".report-data.", report_bytes)
            checksums_tmp = stage(CHECKSUMS_PATH, ".checksums.", checksum_bytes)
            files.verify_unchanged()
            os.replace(report_tmp, REPORT_PATH)
            report_tmp = None
            # Publish the checksum manifest last so its appearance certifies
            # that the corresponding report-data payload is already in place.
            os.replace(checksums_tmp, CHECKSUMS_PATH)
            checksums_tmp = None
        finally:
            if report_tmp is not None:
                report_tmp.unlink(missing_ok=True)
            if checksums_tmp is not None:
                checksums_tmp.unlink(missing_ok=True)


def print_summary(payload: dict[str, Any], wrote: bool) -> None:
    summary = payload["summary"]
    performance = summary["performance"]
    quality = summary["quality"]
    controls = summary["negative_controls"]
    extended = summary["extended_aime"]
    print(
        "report-data audit: performance "
        f"{performance['valid_selected_attempts']}/{performance['expected']} valid, "
        f"{performance['pending']} pending, {performance['invalid']} invalid"
    )
    print(
        "report-data audit: quality "
        f"{quality['valid_comparisons']} valid comparisons, "
        f"{quality['terminal_noncompletions']} terminal non-completions, "
        f"{quality['pending']} pending, {quality['invalid']} invalid"
    )
    print(
        "report-data audit: negative controls "
        f"{controls['valid_comparisons']} valid comparisons, "
        f"{controls['terminal_noncompletions']} terminal non-completions, "
        f"{controls['processed']}/{controls['expected']} processed, "
        f"{controls['pending']} pending, {controls['invalid']} invalid"
    )
    print(
        "report-data audit: extended AIME "
        f"{extended['valid_completed_diagnostics']}/{extended['expected']} valid, "
        f"{extended['pending']} pending, {extended['invalid']} invalid, "
        f"{extended['retained_infrastructure_failures']} retained infrastructure failures"
    )
    print(
        "report-data audit: artifact_data_complete="
        f"{str(summary['artifact_data_complete']).lower()}"
    )
    print(
        "report-data audit: final_markdown_complete="
        f"{str(summary['final_markdown_complete']).lower()} "
        f"({len(payload['final_markdown']['performance_completion_markers'])} "
        "performance completion markers)"
    )
    print(f"report-data audit: ready_for_final_report={str(summary['ready_for_final_report']).lower()}")
    for cohort, scopes in payload["untracked_result_directories"].items():
        for scope, names in scopes.items():
            if names:
                print(
                    f"report-data audit: untracked {cohort}/{scope} result directories: "
                    + ", ".join(names),
                    file=sys.stderr,
                )
    comparator = payload["local_comparator"]["performance"]
    if comparator.get("status") == "invalid":
        for error in comparator.get("errors", []):
            print(f"report-data audit: rank 111 performance invalid: {error}", file=sys.stderr)
    for row in payload["candidates"]:
        for phase in ("performance", "quality"):
            result = row[phase]
            if result.get("status") == "invalid":
                for error in result.get("errors", []):
                    print(
                        f"report-data audit: rank {row['rank']} {phase} invalid: {error}",
                        file=sys.stderr,
                    )
    for row in payload["negative_controls"]["controls"]:
        result = row["quality"]
        if result.get("status") == "invalid":
            for error in result.get("errors", []):
                print(
                    f"report-data audit: control rank {row['rank']} invalid: {error}",
                    file=sys.stderr,
                )
    for row in payload["extended_aime"]["arms"]:
        result = row["diagnostic"]
        if result.get("status") == "invalid":
            for error in result.get("errors", []):
                print(
                    f"report-data audit: extended-AIME rank {row['rank']} invalid: {error}",
                    file=sys.stderr,
                )
    if wrote:
        print(f"wrote {relative(REPORT_PATH)}")
        print(f"wrote {relative(CHECKSUMS_PATH)}")


def print_completion_blockers(payload: dict[str, Any]) -> None:
    for marker in payload["final_markdown"]["performance_completion_markers"]:
        kinds = ",".join(marker["kinds"])
        print(
            f"report-data audit: {relative(FINAL_REPORT_PATH)}:{marker['line']}: "
            f"{kinds}: {marker['text']}",
            file=sys.stderr,
        )


def run_self_test() -> int:
    try:
        complete = """# Final report

Local performance is complete: 16/16 valid selected attempts and 0 pending arms.
No performance placeholders remain.
"""
        require(
            performance_completion_markers(complete) == [],
            "negated completion language was treated as unresolved",
        )

        incomplete = """# Draft
| Local performance | **PENDING** |
**PLACEHOLDER STATUS:** no local performance result is reported.
Performance TODO: add the measurements.
Performance arms are still absent.
Performance: 0/16 valid selected attempts.
## Performance appendix
**PENDING**
"""
        markers = performance_completion_markers(incomplete)
        require(len(markers) == 6, "not every synthetic completion marker was found")
        found_kinds = {kind for marker in markers for kind in marker["kinds"]}
        require(
            {
                "placeholder",
                "performance_pending",
                "performance_todo",
                "performance_absent",
                "performance_zero_complete_arms",
            }
            <= found_kinds,
            "synthetic completion marker kinds differ",
        )

        final_report_path = relative(FINAL_REPORT_PATH)
        official_findings_path = relative(OFFICIAL_FINDINGS_PATH)
        report_data_path = relative(REPORT_PATH)
        checksum_path = relative(CHECKSUMS_PATH)
        report_data_bytes = b'{"synthetic":true}\n'
        checksum_bytes = checksum_manifest_bytes(
            {
                final_report_path: "a" * 64,
                official_findings_path: "b" * 64,
            },
            report_data_bytes,
        )
        checksum_text = checksum_bytes.decode()
        require(
            f"{'a' * 64}  {final_report_path}\n" in checksum_text
            and f"{'b' * 64}  {official_findings_path}\n" in checksum_text,
            "required Markdown is absent from the synthetic checksum manifest",
        )
        require(
            f"{hash_text(report_data_bytes)}  {report_data_path}\n" in checksum_text,
            "report-data digest is absent from the synthetic checksum manifest",
        )
        require(
            checksum_path not in checksum_text,
            "synthetic checksum manifest contains a self-reference",
        )

        try:
            checksum_manifest_bytes(
                {final_report_path: "a" * 64}, report_data_bytes
            )
        except AuditFailure as error:
            require(
                official_findings_path in str(error),
                "missing-Markdown failure does not identify the missing path",
            )
        else:
            raise AuditFailure("missing required Markdown did not fail publication")

        valid_gate_log = """
mlxfast: benchmark elapsed=77.0s local thermal gate start phase=prefill
benchmark.sh: GPU cool-down gate passed (current 40.0C, target <=40C, waited 240s)
mlxfast: benchmark elapsed=529.3s local thermal gate complete phase=prefill
mlxfast: benchmark elapsed=573.5s local thermal gate start phase=decode
benchmark.sh: GPU cool-down gate passed (current 39.9C, target <=40C, waited 150s)
mlxfast: benchmark elapsed=855.2s local thermal gate complete phase=decode
"""
        require(
            validated_local_gate_temperatures(valid_gate_log, "synthetic")
            == [40.0, 39.9],
            "valid synthetic thermal gates were not parsed",
        )
        try:
            validated_local_gate_temperatures(
                "mlxfast: benchmark elapsed=1.0s local thermal gate start "
                "phase=prefill\n"
                "benchmark.sh: warning: the GPU temperature reads 1.5C, at "
                "or below the 5C plausibility floor; retrying the temperature "
                "reader (2 attempts remain)\n",
                "synthetic",
            )
        except AuditFailure as error:
            require(
                "implausible GPU telemetry" in str(error),
                "implausible synthetic telemetry failed for the wrong reason",
            )
        else:
            raise AuditFailure("implausible synthetic telemetry was accepted")

        try:
            validated_local_gate_temperatures(
                "\n".join(valid_gate_log.splitlines()[1:4]), "synthetic"
            )
        except AuditFailure as error:
            require(
                "ordered prefill/decode" in str(error),
                "incomplete synthetic gate log failed for the wrong reason",
            )
        else:
            raise AuditFailure("an incomplete synthetic thermal-gate log was accepted")

        try:
            validated_local_gate_temperatures(
                valid_gate_log.replace(
                    "benchmark.sh: GPU cool-down gate passed",
                    "mlxfast-worker: benchmark.sh: GPU cool-down gate passed",
                    1,
                ),
                "synthetic",
            )
        except AuditFailure as error:
            require(
                "untrusted or malformed" in str(error),
                "worker-prefixed synthetic gate failed for the wrong reason",
            )
        else:
            raise AuditFailure("a worker-prefixed thermal event was accepted")
    except AuditFailure as error:
        print(f"report-data self-test failed: {error}", file=sys.stderr)
        return 1
    print("report-data self-test: 11 deterministic checks passed")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="audit without writing (default)")
    action.add_argument("--write", action="store_true", help="write report-data.json and checksums.sha256")
    action.add_argument(
        "--self-test",
        action="store_true",
        help="run deterministic Markdown/checksum tests without reading study results",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help=(
            "fail unless performance is 16/16 valid, primary quality is 15/15 "
            "processed, controls are 3/3 processed, extended AIME is 4/4 valid, "
            "and REPORT.md has no performance completion markers"
        ),
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=DEFAULT_RESULTS,
        help="study results directory (default: quality-results/leaderboard-top15-20260802)",
    )
    parser.add_argument(
        "--control-results",
        type=Path,
        default=DEFAULT_CONTROL_RESULTS,
        help="negative-control results directory",
    )
    parser.add_argument(
        "--extended-aime-results",
        type=Path,
        default=DEFAULT_EXTENDED_AIME_RESULTS,
        help="isolated 6,144-token AIME diagnostic results directory",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return run_self_test()
    try:
        payload, files = build_payload(
            args.results.expanduser().resolve(),
            args.control_results.expanduser().resolve(),
            args.extended_aime_results.expanduser().resolve(),
        )
        files.verify_unchanged()
        if not payload["summary"]["audit_valid"]:
            print_summary(payload, False)
            return 1
        if args.require_complete and not payload["summary"]["ready_for_final_report"]:
            print_summary(payload, False)
            print_completion_blockers(payload)
            return 2
        if args.write:
            write_outputs(payload, files)
        print_summary(payload, args.write)
        return 0
    except (AuditFailure, OSError, KeyError, TypeError) as error:
        print(f"report-data audit failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
