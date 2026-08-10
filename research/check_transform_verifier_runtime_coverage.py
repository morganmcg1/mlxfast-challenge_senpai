#!/usr/bin/env python3
import copy
import hashlib
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path(__file__).with_name("transform_verifier_runtime_coverage_manifest.json")
SOURCE_REVISION = "dd35f692f26a17c93f69065ea8208e349f23743a"
REVISION_ID = "cedar-nezuko-transform-verifier-runtime-coverage-20260810-r3-tracked-dependency-citation-closure"
DEPENDENCY_REVISIONS = {
    "swift-transformers": "2fa33e1f5e7131a7fc64c28e6d161dcec0d24820",
}
DEPENDENCY_EVIDENCE = {
    "swift-transformers": {
        "package_identity": "swift-transformers",
        "repository_url": "https://github.com/huggingface/swift-transformers",
        "revision": DEPENDENCY_REVISIONS["swift-transformers"],
        "version": "1.3.3",
        "source_path": "Sources/Hub/Hub.swift",
        "source_range": {"start": 247, "end": 298},
        "content_addressed_url": (
            "https://github.com/huggingface/swift-transformers/blob/"
            "2fa33e1f5e7131a7fc64c28e6d161dcec0d24820/Sources/Hub/Hub.swift#L247-L298"
        ),
        "excerpt_sha256": "1cec8edb95382bee855ef929f63370e578548bd36ee61751782bcaa969f1cd65",
        "required_path_anchors": [
            "config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "chat_template.jinja",
            "chat_template.json",
        ],
    }
}
REQUIRED_FIELDS = {
    "id",
    "kind",
    "source_revision",
    "path_class",
    "citations",
    "verifier_treatment",
    "runtime_reach",
    "verdict",
}
REQUIRED_IDS = {
    "producer.config",
    "producer.index",
    "producer.shard",
    "producer.tokenizer_json",
    "producer.tokenizer_config",
    "producer.chat_template_json",
    "producer.chat_template_jinja_absent",
    "producer.metadata",
    "producer.laguna_sidecars_absent",
    "verifier.regeneration",
    "verifier.regular_file_inventory",
    "verifier.exact_set_size_bytes_digest",
    "verifier.newline_names_rejected",
    "verifier.directories_skipped",
    "runtime.config",
    "runtime.index",
    "runtime.root_safetensors_inventory",
    "runtime.shard_header",
    "runtime.shard_payload",
    "runtime.semantic_tokenizer_binding",
    "runtime.tokenizer_json",
    "runtime.tokenizer_config",
    "runtime.tokenizer_model_config",
    "runtime.tokenizer_chat_template_jinja",
    "runtime.tokenizer_chat_template_json",
    "ignored.gitkeep",
    "ignored.source_marker",
    "marker.source_hash_scope",
    "marker.transform_authored_rejected",
    "marker.benchmark_injection",
    "marker.reuse_comparison",
    "marker.integrity_binding",
    "history.prior_complete_proof",
}
REQUIRED_KINDS = {"producer", "verifier", "runtime_read", "ignored_path", "source_marker", "history"}
EXPECTED_JOINS = {
    "runtime.config": "producer.config",
    "runtime.index": "producer.index",
    "runtime.shard_header": "producer.shard",
    "runtime.shard_payload": "producer.shard",
    "runtime.tokenizer_json": "producer.tokenizer_json",
    "runtime.tokenizer_config": "producer.tokenizer_config",
    "runtime.tokenizer_model_config": "producer.config",
    "runtime.tokenizer_chat_template_jinja": "producer.chat_template_jinja_absent",
    "runtime.tokenizer_chat_template_json": "producer.chat_template_json",
}
EXPECTED_IGNORES = [".benchmark-source.sha256", ".gitkeep"]
RUNTIME_BOUNDS = {"fixed_root", "fixed_child", "index_bounded", "root_bounded"}
KNOWN_DEFECT = "edge.runtime_directory_inventory.nonregular_safetensors_suffix"
CITATION_RE = re.compile(r"^(?P<path>[^:;]+):(?P<ranges>\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)$")
DEPENDENCY_CITATION_RE = re.compile(
    r"^dependency:(?P<identity>[^:;]+):(?P<path>[^:;]+):"
    r"(?P<ranges>\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)$"
)
REQUIRED_SOURCE_ANCHORS = {
    ("Sources/MLXFastTransform/CheckpointIndex.swift", 28, 57): ("writeStripped", "data.write"),
    ("Sources/MLXFastTransform/Transform.swift", 506, 551): ("captureMetadataFiles", "shouldCopyMetadataFile"),
    (".github/workflows/benchmark.yml", 1503, 1515): ("MLXFAST_WEIGHTS_PATH", "MLXFAST_SEMANTIC_GPQA_OUTPUT_PATH"),
    ("Sources/MLXFastCLI/main.swift", 362, 370): ("semanticGPQATokenizerPath", "weightsPath"),
    ("Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift", 314, 332): ("tokenizer.json", "tokenizer_config.json"),
    ("Sources/MLXFastTrustedHarness/LagunaRuntimeCorrectness.swift", 467, 470): ("loadLocalTokenizer",),
    ("Sources/MLXFastTrustedHarness/LagunaRuntimeSupport.swift", 96, 100): ("AutoTokenizer.from",),
    ("Package.resolved", 266, 271): (DEPENDENCY_REVISIONS["swift-transformers"],),
}
REQUIRED_DEPENDENCY_ANCHORS = {
    (
        "swift-transformers",
        DEPENDENCY_EVIDENCE["swift-transformers"]["source_path"],
        247,
        298,
    ): tuple(DEPENDENCY_EVIDENCE["swift-transformers"]["required_path_anchors"]),
}


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def parse_ranges(ranges):
    for range_text in ranges.split(","):
        if "-" in range_text:
            start_text, end_text = range_text.split("-", 1)
        else:
            start_text = end_text = range_text
        yield range_text, int(start_text), int(end_text)


def parse_citation(value, context, errors):
    if not isinstance(value, str) or not value.strip():
        errors.append(f"citation_empty:{context}")
        return []
    if value.startswith("N/A:"):
        if not value[4:].strip():
            errors.append(f"citation_na_empty:{context}")
        return []

    parsed = []
    for part in value.split(";"):
        text = part.strip()
        dependency_match = DEPENDENCY_CITATION_RE.fullmatch(text)
        if dependency_match:
            identity = dependency_match.group("identity")
            expected = DEPENDENCY_EVIDENCE.get(identity)
            if expected is None:
                errors.append(f"dependency_citation_identity:{context}:{identity}")
                continue
            path = dependency_match.group("path")
            if path != expected["source_path"]:
                errors.append(f"dependency_citation_path:{context}:{identity}:{path}")
                continue
            expected_range = expected["source_range"]
            for range_text, start, end in parse_ranges(dependency_match.group("ranges")):
                if {"start": start, "end": end} != expected_range:
                    errors.append(f"dependency_citation_range:{context}:{identity}:{range_text}")
                    continue
                parsed.append(("dependency", identity, path, start, end))
            continue

        match = CITATION_RE.fullmatch(text)
        if not match:
            errors.append(f"citation_format:{context}")
            continue
        relative_path = Path(match.group("path"))
        if relative_path.is_absolute() or ".." in relative_path.parts:
            errors.append(f"citation_path_escape:{context}")
            continue
        source_path = (REPO_ROOT / relative_path).resolve()
        try:
            source_path.relative_to(REPO_ROOT)
        except ValueError:
            errors.append(f"citation_path_escape:{context}")
            continue
        if not source_path.is_file():
            errors.append(f"citation_missing_path:{context}:{relative_path.as_posix()}")
            continue
        lines = source_path.read_text(errors="replace").splitlines()
        for range_text, start, end in parse_ranges(match.group("ranges")):
            if start < 1 or end < start or end > len(lines):
                errors.append(f"citation_range:{context}:{relative_path.as_posix()}:{range_text}")
                continue
            parsed.append(("tracked", relative_path.as_posix(), start, end))
    return parsed


def validate_dependency_evidence(manifest, errors):
    evidence_map = manifest.get("dependency_evidence")
    if not isinstance(evidence_map, dict):
        errors.append("dependency_evidence")
        return
    if set(evidence_map) != set(DEPENDENCY_EVIDENCE):
        errors.append("dependency_evidence_identities")

    for identity, expected in DEPENDENCY_EVIDENCE.items():
        evidence = evidence_map.get(identity)
        if not isinstance(evidence, dict):
            errors.append(f"dependency_evidence_missing:{identity}")
            continue
        for field, expected_value in expected.items():
            if evidence.get(field) != expected_value:
                errors.append(f"dependency_evidence_field:{identity}:{field}")

        excerpt = evidence.get("excerpt")
        if not isinstance(excerpt, str):
            errors.append(f"dependency_excerpt_missing:{identity}")
            continue
        if not excerpt.endswith("\n"):
            errors.append(f"dependency_excerpt_final_newline:{identity}")
        source_range = expected["source_range"]
        expected_lines = source_range["end"] - source_range["start"] + 1
        if len(excerpt.splitlines()) != expected_lines:
            errors.append(f"dependency_excerpt_line_count:{identity}")
        digest = hashlib.sha256(excerpt.encode()).hexdigest()
        if digest != evidence.get("excerpt_sha256"):
            errors.append(f"dependency_excerpt_digest:{identity}")
        if digest != expected["excerpt_sha256"]:
            errors.append(f"dependency_excerpt_pinned_digest:{identity}")
        for anchor in expected["required_path_anchors"]:
            if anchor not in excerpt:
                errors.append(f"dependency_excerpt_anchor:{identity}:{anchor}")

    try:
        resolved = json.loads((REPO_ROOT / "Package.resolved").read_text())
    except (OSError, json.JSONDecodeError):
        errors.append("dependency_package_resolved_unreadable")
        return
    pins = resolved.get("pins", [])
    for identity, expected in DEPENDENCY_EVIDENCE.items():
        matches = [pin for pin in pins if pin.get("identity") == identity]
        if len(matches) != 1:
            errors.append(f"dependency_package_pin_count:{identity}")
            continue
        pin = matches[0]
        state = pin.get("state", {})
        if pin.get("location") != expected["repository_url"]:
            errors.append(f"dependency_package_location:{identity}")
        if state.get("revision") != expected["revision"]:
            errors.append(f"dependency_package_revision:{identity}")
        if state.get("version") != expected["version"]:
            errors.append(f"dependency_package_version:{identity}")


def validate_source_anchors(citations, manifest, errors):
    tracked_citations = {citation[1:] for citation in citations if citation[0] == "tracked"}
    dependency_citations = {citation[1:] for citation in citations if citation[0] == "dependency"}
    for anchor, required_text in REQUIRED_SOURCE_ANCHORS.items():
        path, start, end = anchor
        if anchor not in tracked_citations:
            errors.append(f"source_anchor_missing:{path}:{start}-{end}")
            continue
        lines = (REPO_ROOT / path).read_text(errors="replace").splitlines()
        excerpt = "\n".join(lines[start - 1 : end])
        for token in required_text:
            if token not in excerpt:
                errors.append(f"source_anchor_text:{path}:{start}-{end}:{token}")

    evidence_map = manifest.get("dependency_evidence", {})
    for anchor, required_text in REQUIRED_DEPENDENCY_ANCHORS.items():
        identity, path, start, end = anchor
        if anchor not in dependency_citations:
            errors.append(f"dependency_anchor_missing:{identity}:{path}:{start}-{end}")
            continue
        excerpt = evidence_map.get(identity, {}).get("excerpt", "")
        for token in required_text:
            if token not in excerpt:
                errors.append(f"dependency_anchor_text:{identity}:{path}:{start}-{end}:{token}")


def validate(manifest):
    errors = []
    if manifest.get("schema_version") != 1:
        errors.append("schema_version")
    if manifest.get("source_revision") != SOURCE_REVISION:
        errors.append("source_revision")
    if manifest.get("revision_id") != REVISION_ID:
        errors.append("revision_id")
    if manifest.get("dependency_source_revisions") != DEPENDENCY_REVISIONS:
        errors.append("dependency_source_revisions")
    validate_dependency_evidence(manifest, errors)
    if manifest.get("terminal_verdict") != "COVERAGE_DEFECT":
        errors.append("terminal_verdict")

    rows = manifest.get("rows", [])
    ids = [row.get("id") for row in rows]
    row_by_id = {row.get("id"): row for row in rows}
    if len(ids) != len(set(ids)):
        errors.append("duplicate_row_id")
    missing_ids = sorted(REQUIRED_IDS - set(ids))
    if missing_ids:
        errors.append("missing_rows:" + ",".join(missing_ids))
    kinds = {row.get("kind") for row in rows}
    missing_kinds = sorted(REQUIRED_KINDS - kinds)
    if missing_kinds:
        errors.append("missing_kinds:" + ",".join(missing_kinds))

    parsed_citations = []
    for row in rows:
        row_id = row.get("id", "<missing>")
        missing = sorted(REQUIRED_FIELDS - set(row))
        if missing:
            errors.append(f"row_fields:{row_id}:{','.join(missing)}")
        if row.get("source_revision") != SOURCE_REVISION:
            errors.append(f"row_revision:{row_id}")
        if row.get("kind") == "runtime_read" and row.get("path_bound") not in RUNTIME_BOUNDS:
            errors.append(f"runtime_path_unbounded:{row_id}")
        citations = row.get("citations")
        if not isinstance(citations, dict) or set(citations) != {"producer", "consumer", "verifier"}:
            errors.append(f"row_citations:{row_id}")
            continue
        for role, value in citations.items():
            parsed_citations.extend(parse_citation(value, f"{row_id}:{role}", errors))

    failure = manifest.get("first_failure", {})
    for index, citation in enumerate(failure.get("citations", [])):
        parsed_citations.extend(parse_citation(citation, f"first_failure:{index}", errors))
    validate_source_anchors(parsed_citations, manifest, errors)

    fixture = manifest.get("control_fixture", {})
    row_ids = set(ids)
    for producer_id in fixture.get("required_producer_ids", []):
        if producer_id not in row_ids or row_by_id.get(producer_id, {}).get("kind") != "producer":
            errors.append(f"producer_inventory:{producer_id}")
    for runtime_id in fixture.get("required_runtime_ids", []):
        if runtime_id not in row_ids or row_by_id.get(runtime_id, {}).get("kind") != "runtime_read":
            errors.append(f"runtime_inventory:{runtime_id}")

    if fixture.get("verifier_ignore_set") != EXPECTED_IGNORES:
        errors.append("verifier_ignore_set")
    ignored_runtime = sorted(
        set(fixture.get("verifier_ignore_set", []))
        & set(fixture.get("runtime_consumed_paths", []))
    )
    if ignored_runtime:
        errors.append("runtime_consumed_ignored:" + ",".join(ignored_runtime))
    if fixture.get("transform_marker_trusted") is not False:
        errors.append("transform_marker_trusted")
    if fixture.get("source_hash_bound") is not True:
        errors.append("source_hash_binding")
    if "runtime_paths_statically_bounded" in fixture:
        errors.append("runtime_path_summary_deprecated")
    if fixture.get("path_normalization_required") is not True:
        errors.append("path_normalization")
    if fixture.get("root_escape_allowed") is not False:
        errors.append("root_escape")
    if fixture.get("expected_regular_files") != fixture.get("actual_regular_files"):
        errors.append("exact_file_set")
    if fixture.get("coverage_join") != EXPECTED_JOINS:
        errors.append("coverage_join")
    else:
        for runtime_id, producer_id in EXPECTED_JOINS.items():
            if row_by_id.get(runtime_id, {}).get("kind") != "runtime_read":
                errors.append(f"coverage_runtime_kind:{runtime_id}")
            if row_by_id.get(producer_id, {}).get("kind") != "producer":
                errors.append(f"coverage_producer_kind:{producer_id}")

    if failure.get("id") != KNOWN_DEFECT or fixture.get("known_defect_id") != KNOWN_DEFECT:
        errors.append("known_defect_identity")
    if "directory" not in failure.get("path_expression", ""):
        errors.append("known_defect_path")
    if manifest.get("inventory_status", {}).get("coverage_join_closed") is not False:
        errors.append("defect_closure_state")
    return sorted(set(errors))


def omit_row(manifest, row_id):
    manifest["rows"] = [row for row in manifest["rows"] if row["id"] != row_id]


def controls(manifest):
    cases = []

    candidate = copy.deepcopy(manifest)
    omit_row(candidate, "producer.config")
    cases.append(("omit_config", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    omit_row(candidate, "producer.index")
    cases.append(("omit_index_metadata", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    candidate["control_fixture"]["coverage_join"]["runtime.shard_payload"] = "producer.config"
    cases.append(("reassign_shard", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    candidate["control_fixture"]["verifier_ignore_set"].append("config.json")
    cases.append(("ignore_runtime_path", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    candidate["control_fixture"]["transform_marker_trusted"] = True
    cases.append(("trust_transform_marker", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    candidate["control_fixture"]["source_hash_bound"] = False
    cases.append(("remove_source_hash_binding", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    candidate["rows"].append(
        {
            "id": "runtime.synthetic_dynamic",
            "kind": "runtime_read",
            "source_revision": SOURCE_REVISION,
            "path_class": "weightsRoot/<runtime-derived-unbounded-path>",
            "path_bound": "unbounded_dynamic",
            "citations": {
                "producer": "N/A: synthetic negative control",
                "consumer": "N/A: synthetic negative control",
                "verifier": "N/A: synthetic negative control",
            },
            "verifier_treatment": "Synthetic negative control.",
            "runtime_reach": "Synthetic negative control.",
            "verdict": "synthetic",
        }
    )
    cases.append(("insert_dynamic_runtime_path", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    candidate["control_fixture"]["actual_regular_files"].append("unexpected.bin")
    cases.append(("add_extra_output_file", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    candidate["control_fixture"]["path_normalization_required"] = False
    candidate["control_fixture"]["root_escape_allowed"] = True
    cases.append(("allow_root_escape", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    omit_row(candidate, "producer.tokenizer_json")
    cases.append(("omit_tokenizer_json_producer", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    omit_row(candidate, "runtime.tokenizer_config")
    cases.append(("omit_tokenizer_config_runtime", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    candidate["control_fixture"]["coverage_join"]["runtime.tokenizer_json"] = "producer.metadata"
    cases.append(("reassign_tokenizer_join", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    candidate["rows"][0]["citations"]["producer"] = "Sources/DoesNotExist.swift:1-2"
    cases.append(("invalid_source_path", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    candidate["rows"][0]["citations"]["producer"] = "Sources/MLXFastTransform/Transform.swift:999999-1000000"
    cases.append(("invalid_source_range", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    candidate["dependency_evidence"]["swift-transformers"]["revision"] = "0" * 40
    cases.append(("drift_dependency_revision", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    candidate["dependency_evidence"]["swift-transformers"]["excerpt"] = candidate[
        "dependency_evidence"
    ]["swift-transformers"]["excerpt"].replace("config.json", "config.drift", 1)
    cases.append(("drift_dependency_excerpt", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    candidate["dependency_evidence"]["swift-transformers"]["required_path_anchors"][0] = (
        "config.drift"
    )
    cases.append(("drift_dependency_anchor", validate(candidate)))

    return [{"id": control_id, "errors": errors} for control_id, errors in cases]


def main():
    manifest = json.loads(MANIFEST_PATH.read_text())
    manifest_errors = validate(manifest)
    control_results = controls(manifest)
    result = {
        "canonical_manifest_sha256": hashlib.sha256(canonical_bytes(manifest)).hexdigest(),
        "terminal_verdict": manifest.get("terminal_verdict"),
        "manifest_errors": manifest_errors,
        "known_defects": [manifest.get("first_failure", {}).get("id")],
        "controls": control_results,
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    controls_failed_as_expected = all(item["errors"] for item in control_results)
    raise SystemExit(0 if not manifest_errors and controls_failed_as_expected else 1)


if __name__ == "__main__":
    main()
