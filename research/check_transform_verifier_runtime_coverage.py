#!/usr/bin/env python3
import copy
import hashlib
import json
from pathlib import Path

MANIFEST_PATH = Path(__file__).with_name("transform_verifier_runtime_coverage_manifest.json")
SOURCE_REVISION = "dd35f692f26a17c93f69065ea8208e349f23743a"
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
}
EXPECTED_IGNORES = [".benchmark-source.sha256", ".gitkeep"]
KNOWN_DEFECT = "edge.runtime_directory_inventory.nonregular_safetensors_suffix"


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def validate(manifest):
    errors = []
    if manifest.get("schema_version") != 1:
        errors.append("schema_version")
    if manifest.get("source_revision") != SOURCE_REVISION:
        errors.append("source_revision")
    if manifest.get("terminal_verdict") != "COVERAGE_DEFECT":
        errors.append("terminal_verdict")

    rows = manifest.get("rows", [])
    ids = [row.get("id") for row in rows]
    if len(ids) != len(set(ids)):
        errors.append("duplicate_row_id")
    missing_ids = sorted(REQUIRED_IDS - set(ids))
    if missing_ids:
        errors.append("missing_rows:" + ",".join(missing_ids))
    kinds = {row.get("kind") for row in rows}
    missing_kinds = sorted(REQUIRED_KINDS - kinds)
    if missing_kinds:
        errors.append("missing_kinds:" + ",".join(missing_kinds))

    for row in rows:
        row_id = row.get("id", "<missing>")
        missing = sorted(REQUIRED_FIELDS - set(row))
        if missing:
            errors.append(f"row_fields:{row_id}:{','.join(missing)}")
        if row.get("source_revision") != SOURCE_REVISION:
            errors.append(f"row_revision:{row_id}")
        citations = row.get("citations")
        if not isinstance(citations, dict) or set(citations) != {"producer", "consumer", "verifier"}:
            errors.append(f"row_citations:{row_id}")
        elif any(not isinstance(value, str) or not value.strip() for value in citations.values()):
            errors.append(f"row_empty_citation:{row_id}")

    fixture = manifest.get("control_fixture", {})
    row_ids = set(ids)
    for producer_id in fixture.get("required_producer_ids", []):
        if producer_id not in row_ids:
            errors.append(f"producer_inventory:{producer_id}")
    for runtime_id in fixture.get("required_runtime_ids", []):
        if runtime_id not in row_ids:
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
    if fixture.get("runtime_paths_statically_bounded") is not True:
        errors.append("dynamic_runtime_path")
    if fixture.get("path_normalization_required") is not True:
        errors.append("path_normalization")
    if fixture.get("root_escape_allowed") is not False:
        errors.append("root_escape")
    if fixture.get("expected_regular_files") != fixture.get("actual_regular_files"):
        errors.append("exact_file_set")
    if fixture.get("coverage_join") != EXPECTED_JOINS:
        errors.append("coverage_join")

    failure = manifest.get("first_failure", {})
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
    candidate["control_fixture"]["runtime_paths_statically_bounded"] = False
    cases.append(("insert_dynamic_runtime_path", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    candidate["control_fixture"]["actual_regular_files"].append("unexpected.bin")
    cases.append(("add_extra_output_file", validate(candidate)))

    candidate = copy.deepcopy(manifest)
    candidate["control_fixture"]["path_normalization_required"] = False
    candidate["control_fixture"]["root_escape_allowed"] = True
    cases.append(("allow_root_escape", validate(candidate)))

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
