#!/usr/bin/env python3

import copy
import hashlib
import json
import subprocess
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path

BASE_SHA = "ac0e7cf6f283c8ac655af955d7ccf57c5141185e"
CC6_SCORE = Decimal("2.61650354381456")
CC6_PREFILL_SPEEDUP = Decimal("2.0441331295729355")
CC6_DECODE_SPEEDUP = Decimal("2.8409180802229947")
E27_SCORE = Decimal("2.60664969895906")
E27_PREFILL_SPEEDUP = Decimal("2.0102798437644536")
E27_DECODE_SPEEDUP = Decimal("2.8424405431090602")
E27_PREFILL_SECONDS = Decimal("0.000187976888671875")
E27_DECODE_SECONDS = Decimal("0.0048906780546875")
DECODE_WEIGHT = Decimal("0.75")
PREFILL_WEIGHT = Decimal("0.25")
COMPONENT_FLOOR = Decimal("0.95")
EXPECTED_CONTRACT_SHA256 = "e01d3ea1c9281cfe81e1693d987627005fed6963440fbef6a761e4f28dd67fb6"
EXPECTED_E27_MANIFEST_SHA256 = "2622b4de40b12f19fb696755425819b3c5faf7dfc300ac9d2ca7f9e2f9575230"
RANKED_AUDIT = Path("research/ranked-best-payload-gap-audit.json")
RECLAMATION_MANIFEST = Path("research/submitted_surface_reclamation_manifest.json")


def decimal_string(value):
    return format(value, "f")


def weighted_score(decode, prefill, decode_weight=DECODE_WEIGHT, prefill_weight=PREFILL_WEIGHT):
    return decode**decode_weight * prefill**prefill_weight


def rounded_significant(value, digits=12):
    quantum = Decimal(1).scaleb(value.adjusted() - digits + 1)
    return value.quantize(quantum, rounding=ROUND_HALF_EVEN)


def output_string(value, digits=20):
    return decimal_string(rounded_significant(value, digits))


def score_check(decode, prefill, published, decode_weight=DECODE_WEIGHT, prefill_weight=PREFILL_WEIGHT):
    computed = weighted_score(decode, prefill, decode_weight, prefill_weight)
    return {
        "computed": output_string(computed),
        "published": decimal_string(published),
        "absolute_difference": output_string(abs(computed - published)),
        "rounded_12_significant": {
            "computed": decimal_string(rounded_significant(computed)),
            "published": decimal_string(rounded_significant(published)),
        },
        "passes_12_significant_digits": rounded_significant(computed) == rounded_significant(published),
    }


def normalized_records(records):
    return sorted(
        (
            {
                "path": item["path"],
                "size": item["size"] if "size" in item else item["bytes"],
                "sha256": item["sha256"],
            }
            for item in records
        ),
        key=lambda item: item["path"],
    )


def canonical_manifest(records):
    return (json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def manifest_sha256(records):
    return hashlib.sha256(canonical_manifest(records)).hexdigest()


def first_difference(actual, expected):
    for index, (left, right) in enumerate(zip(actual, expected)):
        if left != right:
            return {"index": index, "path": min(left["path"], right["path"]), "actual": left, "expected": right}
    if len(actual) != len(expected):
        item = actual[len(expected)] if len(actual) > len(expected) else expected[len(actual)]
        return {
            "index": min(len(actual), len(expected)),
            "path": item["path"],
            "actual": item if len(actual) > len(expected) else None,
            "expected": item if len(expected) > len(actual) else None,
        }
    return None


def git_bytes(*args):
    return subprocess.check_output(["git", *args])


def reconstruct_base_surface():
    contract = git_bytes("show", f"{BASE_SHA}:benchmark.json")
    contract_data = json.loads(contract)
    editable_paths = contract_data["editablePaths"]
    tree = git_bytes("ls-tree", "-r", "-z", BASE_SHA, "--", *editable_paths)
    blobs = {}
    for raw in tree.split(b"\0"):
        if not raw:
            continue
        metadata, raw_path = raw.split(b"\t", 1)
        mode, object_type, object_id = metadata.decode().split()
        path = raw_path.decode()
        if object_type == "blob" and mode.startswith("100"):
            blobs[path] = object_id
    records = []
    for path, object_id in sorted(blobs.items()):
        content = git_bytes("cat-file", "blob", object_id)
        records.append({"path": path, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    return {
        "contract_sha256": hashlib.sha256(contract).hexdigest(),
        "editable_path_entries": len(editable_paths),
        "records": records,
    }


def latency_fields(factor, seconds, include_pass=False):
    saved_seconds = seconds - seconds / factor
    result = {"savings_microseconds_per_token": output_string(saved_seconds * Decimal(1_000_000))}
    if include_pass:
        result["savings_milliseconds_per_512_token_pass"] = output_string(
            saved_seconds * Decimal(512_000)
        )
    return result


def main():
    with localcontext() as context:
        context.prec = 80
        context.rounding = ROUND_HALF_EVEN

        ranked = json.loads(RANKED_AUDIT.read_text())
        reclamation = json.loads(RECLAMATION_MANIFEST.read_text())
        surface = reclamation["surface"]
        e27_receipt = "e27f1ce4-23bb-4b5f-8e8e-90082be9ea3a"
        e27_from_gap = normalized_records(
            ranked["payload_reconstruction"]["common_files"]
            + ranked["payload_reconstruction"]["receipt_specific_files"][e27_receipt]
        )
        e27_from_reclamation = normalized_records(surface["files"])
        base = reconstruct_base_surface()
        base_records = base["records"]

        evidence_difference = first_difference(e27_from_reclamation, e27_from_gap)
        base_difference = first_difference(base_records, e27_from_reclamation)
        identity_checks = {
            "required_base_sha": BASE_SHA,
            "contract_sha256": base["contract_sha256"],
            "editable_path_entries": base["editable_path_entries"],
            "file_count": len(base_records),
            "total_bytes": sum(item["size"] for item in base_records),
            "manifest_sha256": manifest_sha256(base_records),
            "gap_manifest_sha256": manifest_sha256(e27_from_gap),
            "reclamation_manifest_sha256": manifest_sha256(e27_from_reclamation),
            "first_difference": base_difference or evidence_difference,
        }
        identity_checks["exact"] = all(
            (
                base["contract_sha256"] == EXPECTED_CONTRACT_SHA256,
                base["editable_path_entries"] == 97,
                len(base_records) == len(e27_from_gap) == 142,
                sum(item["size"] for item in base_records) == 2_984_121,
                manifest_sha256(base_records) == EXPECTED_E27_MANIFEST_SHA256,
                manifest_sha256(e27_from_gap) == EXPECTED_E27_MANIFEST_SHA256,
                manifest_sha256(e27_from_reclamation) == EXPECTED_E27_MANIFEST_SHA256,
                evidence_difference is None,
                base_difference is None,
            )
        )
        if not identity_checks["exact"]:
            result = {
                "schema_version": 1,
                "status": "INDETERMINATE",
                "payload_identity_gate": identity_checks,
                "first_missing_or_mismatched_input": base_difference or evidence_difference,
            }
            print(json.dumps(result, indent=2, sort_keys=True))
            raise SystemExit(2)

        cc6_check = score_check(CC6_DECODE_SPEEDUP, CC6_PREFILL_SPEEDUP, CC6_SCORE)
        e27_check = score_check(E27_DECODE_SPEEDUP, E27_PREFILL_SPEEDUP, E27_SCORE)
        tie_ratio = CC6_SCORE / E27_SCORE
        decode_only = tie_ratio ** (Decimal(1) / DECODE_WEIGHT)
        prefill_only = tie_ratio ** (Decimal(1) / PREFILL_WEIGHT)

        frontier = []
        frontier_multipliers = []
        for decode_share in map(Decimal, ("0", "0.25", "0.50", "0.75", "1")):
            prefill_share = Decimal(1) - decode_share
            decode_factor = tie_ratio ** (decode_share / DECODE_WEIGHT)
            prefill_factor = tie_ratio ** (prefill_share / PREFILL_WEIGHT)
            multiplier = weighted_score(decode_factor, prefill_factor)
            frontier_multipliers.append(multiplier)
            projected_decode_speedup = E27_DECODE_SPEEDUP * decode_factor
            projected_prefill_speedup = E27_PREFILL_SPEEDUP * prefill_factor
            decode_latency = latency_fields(decode_factor, E27_DECODE_SECONDS)
            prefill_latency = latency_fields(prefill_factor, E27_PREFILL_SECONDS, include_pass=True)
            frontier.append(
                {
                    "decode_share_percent": decimal_string(decode_share * 100),
                    "prefill_share_percent": decimal_string(prefill_share * 100),
                    "decode_factor": output_string(decode_factor),
                    "prefill_factor": output_string(prefill_factor),
                    "decode_speedup": output_string(projected_decode_speedup),
                    "prefill_speedup": output_string(projected_prefill_speedup),
                    "decode_savings_us_per_token": decode_latency["savings_microseconds_per_token"],
                    "prefill_savings_us_per_token": prefill_latency["savings_microseconds_per_token"],
                    "prefill_savings_ms_per_512": prefill_latency["savings_milliseconds_per_512_token_pass"],
                    "weighted_score": output_string(E27_SCORE * multiplier),
                    "floors": "PASS"
                    if projected_decode_speedup >= COMPONENT_FLOOR
                    and projected_prefill_speedup >= COMPONENT_FLOOR
                    else "FAIL",
                }
            )

        swapped = score_check(
            E27_DECODE_SPEEDUP,
            E27_PREFILL_SPEEDUP,
            E27_SCORE,
            decode_weight=PREFILL_WEIGHT,
            prefill_weight=DECODE_WEIGHT,
        )
        mutated_decode = Decimal("2.8424406431090602")
        mutated_component = score_check(mutated_decode, E27_PREFILL_SPEEDUP, E27_SCORE)
        corrupted_records = copy.deepcopy(e27_from_reclamation)
        original_sha = corrupted_records[0]["sha256"]
        corrupted_records[0]["sha256"] = ("0" if original_sha[0] != "0" else "1") + original_sha[1:]
        corruption_difference = first_difference(base_records, corrupted_records)

        controls = {
            "swapped_exponents": {
                "decode_weight": decimal_string(PREFILL_WEIGHT),
                "prefill_weight": decimal_string(DECODE_WEIGHT),
                "score_reproduction": swapped,
                "status": "PASS" if not swapped["passes_12_significant_digits"] else "FAIL",
            },
            "mutated_official_component_digit": {
                "original_e27_decode_speedup": decimal_string(E27_DECODE_SPEEDUP),
                "mutated_e27_decode_speedup": decimal_string(mutated_decode),
                "score_reproduction": mutated_component,
                "status": "PASS" if not mutated_component["passes_12_significant_digits"] else "FAIL",
            },
            "mutated_manifest_record_sha_digit": {
                "first_difference_index": corruption_difference["index"],
                "first_difference_path": corruption_difference["path"],
                "original_manifest_sha256": EXPECTED_E27_MANIFEST_SHA256,
                "mutated_manifest_sha256": manifest_sha256(corrupted_records),
                "status": "PASS" if corruption_difference is not None else "FAIL",
            },
        }

        proven = (
            cc6_check["passes_12_significant_digits"]
            and e27_check["passes_12_significant_digits"]
            and all(item["floors"] == "PASS" for item in frontier)
            and all(item["status"] == "PASS" for item in controls.values())
            and all(abs(multiplier - tie_ratio) < Decimal("1e-70") for multiplier in frontier_multipliers)
        )
        local_gate = Decimal("1.001")
        result = {
            "schema_version": 1,
            "status": "PROMOTION_MARGIN_PROVEN" if proven else "INDETERMINATE",
            "scope": "deterministic static audit; no production edit, build, inference, timing, W&B, receipt query, or submission",
            "rounding_policy": "Python Decimal precision 80 with ROUND_HALF_EVEN; score checks compare values rounded to 12 significant digits; derived JSON decimals are rounded to 20 significant digits",
            "payload_identity_gate": identity_checks,
            "score_reproduction": {
                "cc6": {
                    "decode_speedup": decimal_string(CC6_DECODE_SPEEDUP),
                    "prefill_speedup": decimal_string(CC6_PREFILL_SPEEDUP),
                    **cc6_check,
                },
                "e27": {
                    "decode_speedup": decimal_string(E27_DECODE_SPEEDUP),
                    "prefill_speedup": decimal_string(E27_PREFILL_SPEEDUP),
                    **e27_check,
                },
            },
            "promotion_margin": {
                "tie_ratio_cc6_over_e27": output_string(tie_ratio),
                "tie_weighted_improvement_percent": output_string((tie_ratio - 1) * 100),
                "strict_promotion_condition": "candidate weighted incremental multiplier > tie_ratio_cc6_over_e27",
                "decode_only_incremental_speedup": output_string(decode_only),
                "decode_only_latency": latency_fields(decode_only, E27_DECODE_SECONDS),
                "prefill_only_incremental_speedup": output_string(prefill_only),
                "prefill_only_latency": latency_fields(prefill_only, E27_PREFILL_SECONDS, include_pass=True),
                "general_frontier_equation": "0.75*ln(decode_incremental_speedup) + 0.25*ln(prefill_incremental_speedup) = ln(tie_ratio_cc6_over_e27)",
            },
            "mixed_log_margin_frontier": frontier,
            "screening_distinction": {
                "generic_local_weighted_gate": decimal_string(local_gate),
                "score_at_exactly_generic_gate_from_e27": output_string(E27_SCORE * local_gate),
                "remaining_multiplier_after_generic_gate_to_tie": output_string(tie_ratio / local_gate),
                "remaining_percent_after_generic_gate_to_tie": output_string((tie_ratio / local_gate - 1) * 100),
                "rule": "Use the deterministic official margin in addition to candidate-specific local, full-model, and ranked-M5 evidence; it supplies no M4-to-M5 transfer factor.",
            },
            "positive_controls": controls,
            "interpretation": "Every future candidate based on the exact e27 surface must exceed the strict cc6/e27 weighted ratio on ranked M5 while retaining both official component floors and all correctness gates. Tie rows are algebraic boundaries, not predictions.",
            "terminal_receipt_rule": "cc6 and terminal e27 must never be retried, rerun, resubmitted, or mutated.",
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        if result["status"] != "PROMOTION_MARGIN_PROVEN":
            raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as error:
        missing_input = {
            "error_type": type(error).__name__,
            "detail": str(error),
        }
        if isinstance(error, FileNotFoundError):
            missing_input["path"] = error.filename
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "INDETERMINATE",
                    "first_missing_or_mismatched_input": missing_input,
                },
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(2)
