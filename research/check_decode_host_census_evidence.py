#!/usr/bin/env python3

import copy
import gzip
import hashlib
import json
import math
import statistics
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS_PATH = ROOT / "decode-host-census-results.json"
RESULTS_SHA256 = "daaaaba11288b47a8917bfc7ae94efd6eaa23faf0f20827ba3f515af1a4dbbb2"

RECEIPTS = {
    "sole_acquisition": {
        "path": "decode-host-census-acquisition-8d22dfb70ff95326f4171640d0b67ba7bc148d39464854ed7b44d49d8e5cc4c4.log.gz",
        "compressed_bytes": 13677,
        "compressed_sha256": "9e1482a5e5aed82a72da036fe7f38a01f94b6d6684f3cca2c663b914cf498db8",
        "raw_bytes": 172307,
        "raw_lines": 493,
        "raw_sha256": "8d22dfb70ff95326f4171640d0b67ba7bc148d39464854ed7b44d49d8e5cc4c4",
    },
    "preceding_idle_telemetry": {
        "path": "decode-host-census-idle-cdfde761adfa32b0e0d1a99ff17cfe03bbecde29059c1d53a43ec0afaa5098c6.jsonl.gz",
        "compressed_bytes": 145697,
        "compressed_sha256": "ca58e7afec7606d010da7b62b22eb43349aca49530b9c882ca224f38a2466694",
        "raw_bytes": 1327593,
        "raw_lines": 600,
        "raw_sha256": "cdfde761adfa32b0e0d1a99ff17cfe03bbecde29059c1d53a43ec0afaa5098c6",
    },
    "post_restoration_equivalence": {
        "path": "decode-host-census-equivalence-fce1364f59e1cd263d75144771434bfb8a2639ee38568b66fc42923b55f13e70.log.gz",
        "compressed_bytes": 1409,
        "compressed_sha256": "13ce46cf0931fc0d7bad21fc529c6019e336806ea3e83c12fbd866cd5322145a",
        "raw_bytes": 5876,
        "raw_lines": 113,
        "raw_sha256": "fce1364f59e1cd263d75144771434bfb8a2639ee38568b66fc42923b55f13e70",
    },
}

EXPECTED_DYNAMIC = {
    "model_dispatch": (1, 128),
    "layer_dispatch": (40, 5120),
    "attention_cache": (40, 5120),
    "kernel_config": (363, 46464),
    "moe_wrapper": (39, 4992),
    "graph_views": (1, 128),
    "async_submission": (8, 1024),
    "blocking_eval": (2, 256),
    "lm_head": (1, 128),
    "greedy_wait": (1, 128),
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_json(path):
    return json.loads(path.read_text())


def check_close(actual, expected, tolerance=1e-9):
    assert math.isclose(actual, expected, rel_tol=0, abs_tol=tolerance), (actual, expected)


def load_receipt(role):
    expected = RECEIPTS[role]
    path = ROOT / expected["path"]
    compressed = path.read_bytes()
    assert len(compressed) == expected["compressed_bytes"]
    assert sha256(compressed) == expected["compressed_sha256"]
    raw = gzip.decompress(compressed)
    assert len(raw) == expected["raw_bytes"]
    assert sha256(raw) == expected["raw_sha256"]
    assert len(raw.splitlines()) == expected["raw_lines"]
    return raw


def parse_window(line):
    payload = line.split("HOST_CENSUS window ", 1)[1]
    result = {}
    integer_fields = {
        "round", "position", "wall_nanos", "body_nanos", "parent_nanos",
        "count", "probe_nanos", "token_checksum",
    }
    for item in payload.split():
        key, value = item.split("=", 1)
        if key in integer_fields:
            result[key] = int(value)
        elif key in {"measured", "warm"}:
            assert value in {"0", "1"}
            result[key] = value == "1"
        elif key == "offsets":
            result[key] = [int(part) for part in value.split(",")]
        else:
            result[key] = value
    return result


def check_results():
    raw = RESULTS_PATH.read_bytes()
    assert len(raw) == 404486
    assert sha256(raw) == RESULTS_SHA256
    results = json.loads(raw)
    assert results["classification"] == "HOST_ATTRIBUTION_INCONCLUSIVE"
    assert results["validity"]["global_measurement_valid"] is False
    assert results["successor"]["nominated"] is False
    assert results["acquisition"]["attempt_count"] == 1
    assert results["acquisition"]["retry_count"] == 0
    assert results["acquisition"]["job_id"] == "583206df-e77d-4d1d-8925-31600618ba1e"
    assert results["acquisition"]["completion_marker"] == "HOST_CENSUS complete windows=400 passed=true"
    assert len(results["windows"]) == 400
    assert results["design"]["non_warm_windows_observed"] == 400
    assert results["design"]["non_warm_windows_expected"] == 400
    dynamic = {
        item["family"]: (item["calls_per_token"], item["calls_per_window"])
        for item in results["family_summaries"]
    }
    assert dynamic == EXPECTED_DYNAMIC
    return results


def check_acquisition(results):
    raw = load_receipt("sole_acquisition")
    text = raw.decode()
    required = [
        "mlxfast: benchmark elapsed=15.0s local thermal gate start phase=host-census",
        "benchmark.sh: strict persistent macmon confirmed phase=host-census samples=5 interval=1000ms final=39.3C",
        "benchmark.sh: GPU cool-down gate passed (current 39.3C, target <=40C, waited 20s)",
        "mlxfast: benchmark elapsed=45.6s local thermal gate complete phase=host-census",
        "HOST_CENSUS metadata families=model_dispatch,layer_dispatch,attention_cache,kernel_config,moe_wrapper,graph_views,async_submission,blocking_eval,lm_head,greedy_wait decode_steps=128 rounds=5 calibration_count=200000 calibration_nanos=2758821",
        "HOST_CENSUS corruption_control injected_count=1 observed_count=1 passed=true",
        "HOST_CENSUS complete windows=400 passed=true",
        "local-iterate failed error=host census complete",
    ]
    for marker in required:
        assert marker in text, marker
    assert text.count("HOST_CENSUS metadata ") == 1
    assert text.count("HOST_CENSUS corruption_control ") == 1
    assert text.count("HOST_CENSUS complete windows=400 passed=true") == 1
    lines = [line for line in text.splitlines() if "HOST_CENSUS window " in line]
    assert len(lines) == 401
    parsed = [parse_window(line) for line in lines]
    assert parsed[0] == results["warm_window"]
    assert parsed[1:] == results["windows"]
    source = results["acquisition"]["source_log"]
    assert source["sha256"] == RECEIPTS["sole_acquisition"]["raw_sha256"]
    assert source["bytes"] == len(raw)
    assert source["lines"] == len(raw.splitlines())


def check_idle(results):
    raw = load_receipt("preceding_idle_telemetry")
    rows = [json.loads(line) for line in raw.splitlines()]
    assert len(rows) == 600
    temperatures = [row["temp"]["gpu_temp_avg"] for row in rows]
    fans = [row["fans"][0]["rpm"] for row in rows]
    start = datetime.fromisoformat(rows[0]["timestamp"])
    end = datetime.fromisoformat(rows[-1]["timestamp"])
    summary = results["pre_acquisition"]
    check_close((end - start).total_seconds(), summary["span_seconds"], 1e-6)
    assert summary["valid_samples"] == len(rows)
    assert summary["idle_telemetry_log_sha256"] == RECEIPTS["preceding_idle_telemetry"]["raw_sha256"]
    expected_temperature = summary["gpu_temperature_c"]
    check_close(min(temperatures), expected_temperature["minimum"], 1e-6)
    check_close(statistics.fmean(temperatures), expected_temperature["mean"], 1e-6)
    check_close(max(temperatures), expected_temperature["maximum"], 1e-6)
    assert len(set(temperatures)) == expected_temperature["unique_values"]
    expected_fan = summary["fan_rpm"]
    assert min(fans) == expected_fan["minimum"]
    check_close(statistics.fmean(fans), expected_fan["mean"], 1e-3)
    assert max(fans) == expected_fan["maximum"]
    assert len(set(fans)) == expected_fan["unique_values"]


def check_equivalence(results):
    raw = load_receipt("post_restoration_equivalence")
    text = raw.decode()
    start = text.index('{\n  "decodeTokenCount"')
    report, _ = json.JSONDecoder().raw_decode(text[start:])
    assert report["promptTokenCount"] == 512
    assert report["decodeTokenCount"] == 8
    assert len(report["steps"]) == 9
    prefill = report["steps"][0]
    assert prefill == {
        "label": "prefill",
        "maximumAbsoluteLogitError": 0.125,
        "meanAbsoluteLogitError": 0.011933609,
        "runtimeToken": 5991,
        "upstreamToken": 5991,
    }
    expected_tokens = [509, 902, 5991, 509, 902, 5991, 509, 902]
    for index, (step, token) in enumerate(zip(report["steps"][1:], expected_tokens)):
        assert step["label"] == f"decode-{index}"
        assert step["maximumAbsoluteLogitError"] == 0
        assert step["meanAbsoluteLogitError"] == 0
        assert step["runtimeToken"] == token
        assert step["upstreamToken"] == token
    assert text.count("EQUIVALENCE_EXACT_STEPS=8") == 1
    restored = results["restoration"]["upstream_equivalence"]
    assert restored["log_sha256"] == RECEIPTS["post_restoration_equivalence"]["raw_sha256"]
    assert restored["accepted_baseline_equivalent"] is True
    assert restored["known_m4_prefill_signature_only"] is True


def validate_environment(environment, results):
    assert environment["schema_version"] == 1
    assert environment["immutable_results_sha256"] == RESULTS_SHA256
    pre = environment["pre_acquisition"]
    assert pre["source_event"]["sha256"] == "cd2d2065b818bc671fa5d74b834f1d33f14c24206b932317a9cfceaca1c9fa41"
    assert pre["stdout"] == ["auto", "competing_processes=false", "worktree_clean=true", "all_9_frozen_blobs_exact=true"]
    assert pre["observations"] == {
        "fan_mode": "auto",
        "competing_model_or_build_process": False,
        "worktree_clean": True,
        "all_frozen_blobs_exact": True,
    }
    assert all(path in pre["command"] for path in results["frozen_paths"])
    post = environment["post_acquisition"]
    assert post["source_event"]["sha256"] == "2a48d055be30ef7891278b54c5e13141ba62f6653c6b1e3cc7ba3709a543ed98"
    assert post["stdout"] == ["2026-08-10T18:03:54Z", "auto"]
    assert post["observations"] == {
        "checked_at": "2026-08-10T18:03:54Z",
        "fan_mode": "auto",
        "acquisition_pid_absent": True,
        "named_competing_processes_absent": True,
        "worktree_clean_before_restoration": True,
    }
    fan = environment["fan_mode_evidence"]
    assert fan["before"] == "auto" and fan["after"] == "auto"
    assert fan["continuous_during_acquisition"]["available"] is False
    assert fan["continuous_during_acquisition"]["status"] == "unverified"
    assert fan["legacy_results_field"]["value"] == results["environment"]["fan_mode_before_during_after"] == "auto"
    assert fan["legacy_results_field"]["verified_as_written"] is False
    assert fan["legacy_results_field"]["relied_upon"] is False
    gate_text = load_receipt("sole_acquisition").decode()
    for marker in environment["acquisition_gate"]["markers"]:
        assert marker in gate_text


def validate_scope(scope, results):
    assert scope["schema_version"] == 1
    assert scope["immutable_results_sha256"] == RESULTS_SHA256
    assert scope["decode_tokens_per_window"] == 128
    static = scope["frozen_internal_census"]
    custom = static["custom_kernel_dispatch"]
    components = custom["components_per_token"]
    assert components == {
        "attention_cache_boundaries": 120,
        "sparse_moe_kernel_boundaries": 195,
        "dense_shared_kernel_boundaries": 3,
        "lm_head_kernel_boundaries": 4,
        "embedding_kernel_boundaries": 1,
    }
    assert sum(components.values()) == custom["per_token"] == 323
    assert custom["per_window"] == custom["per_token"] * 128 == 41344
    assert static["async_eval"] == {"per_token": 8, "per_window": 1024}
    assert static["blocking_eval_api"] == {"per_token": 3, "per_window": 384}
    populated = static["populated_vector"]
    assert populated["per_token"] == 323 + 8 + 3 == 334
    assert populated["per_window"] == populated["per_token"] * 128 == 42752
    assert populated["formula"] == "323 custom-kernel + 8 async + 3 blocking = 334"
    observed = {
        key: (value["per_token"], value["per_window"])
        for key, value in scope["observed_dynamic_families"].items()
    }
    assert observed == EXPECTED_DYNAMIC
    result_dynamic = {
        item["family"]: (item["calls_per_token"], item["calls_per_window"])
        for item in results["family_summaries"]
    }
    assert observed == result_dynamic
    mappings = scope["mappings"]
    assert mappings["kernel_config"]["status"] == "validated_arithmetic"
    assert custom["per_token"] + 40 == observed["kernel_config"][0] == 363
    assert mappings["attention_cache"]["status"] == "validated"
    assert mappings["attention_cache"]["static_per_dynamic"] == 3
    assert observed["attention_cache"][0] * 3 == components["attention_cache_boundaries"]
    assert mappings["moe_wrapper"]["status"] == "validated"
    assert mappings["moe_wrapper"]["static_per_dynamic"] == 5
    assert observed["moe_wrapper"][0] * 5 == components["sparse_moe_kernel_boundaries"]
    assert mappings["lm_head"]["status"] == "validated"
    assert mappings["lm_head"]["static_per_dynamic"] == 4
    assert observed["lm_head"][0] * 4 == components["lm_head_kernel_boundaries"]
    assert mappings["async_submission"]["status"] == "validated"
    assert observed["async_submission"][0] == static["async_eval"]["per_token"]
    blocking = mappings["blocking_eval"]
    assert blocking["relation"] == "dynamic_subset_unresolved"
    assert blocking["static_per_token"] == 3
    assert blocking["dynamic_per_token"] == 2
    assert blocking["status"] == "unavailable"
    assert scope["coverage_control"] == {
        "status": "failed",
        "complete": False,
        "reason": "The blocking-eval static/dynamic mapping is unresolved; wrapper durations also overlap required graph work.",
    }


def expect_scope_rejection(scope, results, mutate):
    candidate = copy.deepcopy(scope)
    mutate(candidate)
    try:
        validate_scope(candidate, results)
    except AssertionError:
        return
    raise AssertionError("scope mutation was not rejected")


def check_scope_mutations(scope, results):
    expect_scope_rejection(
        scope, results,
        lambda value: value["frozen_internal_census"]["custom_kernel_dispatch"].update(per_token=322),
    )
    expect_scope_rejection(
        scope, results,
        lambda value: value["mappings"]["attention_cache"].update(static_per_dynamic=2),
    )
    expect_scope_rejection(
        scope, results,
        lambda value: value["mappings"]["blocking_eval"].update(status="validated"),
    )


def check_manifest():
    manifest = load_json(ROOT / "decode-host-census-evidence-manifest.json")
    assert manifest["schema_version"] == 1
    assert manifest["classification"] == "HOST_ATTRIBUTION_INCONCLUSIVE"
    assert manifest["successor_nominated"] is False
    assert manifest["immutable_results"] == {
        "path": "decode-host-census-results.json",
        "bytes": 404486,
        "sha256": RESULTS_SHA256,
        "non_warm_windows": 400,
    }
    listed = {item["role"]: item for item in manifest["raw_receipts"]}
    assert set(listed) == set(RECEIPTS)
    for role, expected in RECEIPTS.items():
        for key, value in expected.items():
            assert listed[role][key] == value
    assert manifest["environment_receipt"] == "decode-host-census-environment-receipt.json"
    assert manifest["scope_reconciliation"] == "decode-host-census-scope.json"
    assert manifest["checker"] == Path(__file__).name


def main():
    results = check_results()
    check_manifest()
    check_acquisition(results)
    check_idle(results)
    check_equivalence(results)
    environment = load_json(ROOT / "decode-host-census-environment-receipt.json")
    validate_environment(environment, results)
    scope = load_json(ROOT / "decode-host-census-scope.json")
    validate_scope(scope, results)
    check_scope_mutations(scope, results)
    print("HOST_CENSUS_EVIDENCE_OK windows=400 receipts=3 populated_vector=334 mutations=3 conclusion=HOST_ATTRIBUTION_INCONCLUSIVE")


if __name__ == "__main__":
    main()
