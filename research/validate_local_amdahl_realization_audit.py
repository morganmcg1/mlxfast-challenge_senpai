#!/usr/bin/env python3

import argparse
import copy
import hashlib
import json
import math
import os
import re
import statistics
from decimal import Decimal
from pathlib import Path


ROOT_PATH = Path(__file__).resolve().parents[1]
DATA_PATH = Path(__file__).with_name("local_amdahl_realization_cohort.json")
INDEX_PATH = Path(__file__).with_name("local_amdahl_realization_archive_index.json")
ARCHIVE_FILENAME = "pull-requests-844db61edd851eedb7a0.md"
ACTIVE_EXCLUSIONS = {658, 659, 661, 662, 665}
EXPECTED_ORDERS = (["A", "B", "B", "A"], ["B", "A", "A", "B"])
TOLERANCE = 5e-15


class AuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


def load_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def require_digest(value, expected, label):
    require(sha256_bytes(value) == expected, f"{label}: SHA-256 mismatch")


def validate_cohort(data, mechanisms=None):
    rows = data["mechanisms"] if mechanisms is None else mechanisms
    fields = data["eligibility_fields"]
    canonical_unit = data["canonical_time_unit"]
    require(len(rows) == len({row["mechanism_id"] for row in rows}), "duplicate mechanism_id")
    require(len(rows) == len({row["pr_number"] for row in rows}), "duplicate PR")

    eligible = []
    for row in rows:
        require(row["isolated_units"] == canonical_unit, f"{row['mechanism_id']}: isolated unit mismatch")
        require(row["whole_units"] == canonical_unit, f"{row['mechanism_id']}: whole unit mismatch")
        require(set(row["flags"]) == set(fields), f"{row['mechanism_id']}: eligibility field mismatch")
        require(all(isinstance(value, bool) for value in row["flags"].values()), f"{row['mechanism_id']}: non-boolean flag")

        if row["flags"]["candidate_identity_linked"]:
            require(re.fullmatch(r"[0-9a-f]{40}", row["candidate_sha"]) is not None, f"{row['mechanism_id']}: invalid candidate SHA")
            require(row["candidate_sha"] == row["isolated_candidate_sha"], f"{row['mechanism_id']}: isolated candidate SHA mismatch")
        if row["flags"]["same_candidate_sha"]:
            require(row["candidate_sha"] == row["full_candidate_sha"], f"{row['mechanism_id']}: full candidate SHA mismatch")

        orders = row.get("full_order_evidence", {})
        if row["flags"]["full_abba"]:
            require(orders.get("abba") == EXPECTED_ORDERS[0], f"{row['mechanism_id']}: invalid or missing ABBA order")
        if row["flags"]["full_baab"]:
            require(orders.get("baab") == EXPECTED_ORDERS[1], f"{row['mechanism_id']}: invalid or missing BAAB order")

        computed = all(row["flags"][field] for field in fields)
        require(row["eligible"] is computed, f"{row['mechanism_id']}: stale declared eligibility")
        if computed:
            eligible.append(row)

    return eligible


def geometric_mean(values):
    require(len(values) == 2 and all(value > 0 for value in values), "each arm requires two positive observations")
    return math.sqrt(values[0] * values[1])


def recompute_block(check):
    require("order" in check, f"{check.get('check_id', 'unknown')}: missing order")
    require(check["order"] in EXPECTED_ORDERS, f"{check['check_id']}: unsupported order")
    require(len(check.get("rows", [])) == 4, f"{check['check_id']}: expected four rows")
    require([row["label"] for row in check["rows"]] == check["order"], f"{check['check_id']}: row order mismatch")

    base = [row for row in check["rows"] if row["label"] == "A"]
    candidate = [row for row in check["rows"] if row["label"] == "B"]
    result = {
        "base_prefill": geometric_mean([row["prefill"] for row in base]),
        "base_decode": geometric_mean([row["decode"] for row in base]),
        "candidate_prefill": geometric_mean([row["prefill"] for row in candidate]),
        "candidate_decode": geometric_mean([row["decode"] for row in candidate]),
    }
    result["prefill_speedup"] = result["base_prefill"] / result["candidate_prefill"]
    result["decode_speedup"] = result["base_decode"] / result["candidate_decode"]
    result["weighted_speedup"] = result["decode_speedup"] ** 0.75 * result["prefill_speedup"] ** 0.25

    for key, expected in check["expected"].items():
        require(math.isclose(result[key], expected, rel_tol=0, abs_tol=TOLERANCE), f"{check['check_id']}: {key} arithmetic mismatch")
    return result


def validate_positive_control(control, canonical_unit):
    require(control["units"] == canonical_unit, "synthetic control unit mismatch")
    require(bool(control["family"]), "synthetic control missing family")
    decimal = lambda key: Decimal(str(control[key]))
    projected = decimal("isolated_per_call_saving") * control["scored_call_count"]
    observed = decimal("whole_base_time") - decimal("whole_candidate_time")
    realization = observed / projected
    require(projected == decimal("projected_saving"), "synthetic projected saving mismatch")
    require(observed == decimal("observed_saving"), "synthetic observed saving mismatch")
    require(realization == decimal("expected_realization"), "synthetic realization mismatch")
    require(projected > 0 and observed > 0 and realization > 0, "synthetic sign check failed")
    return float(realization)


def result_signals(results):
    text = "\n".join(f"{result.get('hypothesis', '')}\n{result.get('summary', '')}" for result in results).lower()
    return {
        "isolated_timing_terms": bool(re.search(r"isolated|microbenchmark|target[- ]label|kernel[- ]only|family timing", text)),
        "whole_model_timing_terms": bool(re.search(r"local-iterate|whole[- ]model|full[- ]model|end[- ]to[- ]end", text)),
    }


def build_archive_index(raw, data):
    selected = {row["pr_number"]: row for row in data["mechanisms"]}
    matches = list(re.finditer(rb"(?m)^## PR #(\d+) \xe2\x80\x94 (.*)\n", raw))
    rows = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        section = raw[match.start():end]
        pr_number = int(match.group(1))
        title = match.group(2).decode("utf-8")
        payloads = re.findall(rb"<!-- senpai-result:v1 (.*?) -->", section, re.DOTALL)
        results = [json.loads(payload.decode("utf-8")) for payload in payloads]
        metadata = [
            {
                "revision_id": result["assignment"]["revision_id"],
                "status": result["status"],
                "commit_sha": result["commit_sha"],
            }
            for result in results
        ]

        if pr_number in selected:
            disposition = "screened_mechanism"
            exclusion_code = None
            exclusion_reason = None
        elif pr_number in ACTIVE_EXCLUSIONS:
            disposition = "predeclared_active_exclusion"
            exclusion_code = "active_pr_excluded_before_screening"
            exclusion_reason = "The frozen protocol predeclared this active PR as nonterminal at archive freeze; no observed outcome was used."
        elif not results:
            disposition = "omitted"
            exclusion_code = "no_structured_terminal_result"
            exclusion_reason = "No senpai-result:v1 envelope exists in the frozen PR section, so a same-candidate isolated/full evidence join cannot be established."
        else:
            disposition = "omitted"
            exclusion_code = "no_complete_joined_isolated_full_chain"
            exclusion_reason = "Frozen full-text review found no terminal evidence preserving both a predeclared exact same-M4 complete changed-chain isolated timing block and matched same-candidate whole-model component timing; rules 1-4 therefore cannot all pass regardless of result sign or status."

        selected_row = selected.get(pr_number)
        if selected_row:
            disposition_reason = (
                f"Included in the frozen 14-PR diagnostic set as mechanism {selected_row['mechanism_id']} "
                f"and cluster {selected_row['cluster_id']}; the cohort ledger records its detailed "
                "evidence-stage eligibility disposition."
            )
        else:
            disposition_reason = exclusion_reason
        rows.append(
            {
                "pr_number": pr_number,
                "url": f"https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/{pr_number}",
                "title": title,
                "section_sha256": sha256_bytes(section),
                "structured_result_count": len(results),
                "structured_results": metadata,
                "diagnostic_signals": result_signals(results),
                "disposition": disposition,
                "disposition_reason": disposition_reason,
                "mechanism_id": selected_row["mechanism_id"] if selected_row else None,
                "cluster_id": selected_row["cluster_id"] if selected_row else None,
                "family": selected_row["family"] if selected_row else None,
                "exclusion_code": exclusion_code,
                "exclusion_reason": exclusion_reason,
            }
        )

    disposition_counts = {
        name: sum(row["disposition"] == name for row in rows)
        for name in ("screened_mechanism", "predeclared_active_exclusion", "omitted")
    }
    return {
        "schema_version": 1,
        "source_archive": {
            "locator": f"typed-get-prs controller artifact {ARCHIVE_FILENAME}",
            "sha256": sha256_bytes(raw),
            "byte_count": len(raw),
            "line_count": raw.count(b"\n"),
            "pr_section_count": len(rows),
            "structured_result_count": sum(row["structured_result_count"] for row in rows),
            "r1_claimed_structured_result_count": 279,
            "correction": "The frozen bytes contain 274 senpai-result:v1 envelopes. The r1 value 279 is not reproducible and is withdrawn.",
        },
        "selection_policy": {
            "screened_prs": sorted(selected),
            "predeclared_active_exclusions": sorted(ACTIVE_EXCLUSIONS),
            "outcome_fields_used_for_inclusion": [],
            "inclusion_rule": "The prior audit froze 14 candidate diagnostic mechanisms before r2 eligibility evaluation; outcome sign and status were not selection fields.",
            "omission_rule": "A PR is omitted unless its frozen terminal evidence was reviewed as preserving both required evidence stages under the same candidate. Keyword flags are diagnostic only and never select a PR.",
        },
        "summary": {
            "pr_sections": len(rows),
            "structured_results": sum(row["structured_result_count"] for row in rows),
            "dispositions": disposition_counts,
        },
        "pull_requests": rows,
    }


def validate_archive_index(index, data):
    rows = index["pull_requests"]
    source = index["source_archive"]
    require(index["schema_version"] == 1, "archive index schema mismatch")
    require(len(rows) == len({row["pr_number"] for row in rows}), "archive index duplicate PR")
    require([row["pr_number"] for row in rows] == sorted(row["pr_number"] for row in rows), "archive index PRs not sorted")
    require(len(rows) == source["pr_section_count"] == index["summary"]["pr_sections"] == 262, "archive PR coverage mismatch")
    result_count = sum(row["structured_result_count"] for row in rows)
    require(result_count == source["structured_result_count"] == index["summary"]["structured_results"] == 274, "archive structured-result coverage mismatch")
    require(source["r1_claimed_structured_result_count"] == 279, "r1 claim record mismatch")
    require(source["correction"], "missing structured-result count correction")
    require(re.fullmatch(r"[0-9a-f]{64}", source["sha256"]) is not None, "invalid source archive digest")

    selected = {row["pr_number"] for row in data["mechanisms"]}
    indexed_selected = {row["pr_number"] for row in rows if row["disposition"] == "screened_mechanism"}
    indexed_active = {row["pr_number"] for row in rows if row["disposition"] == "predeclared_active_exclusion"}
    require(indexed_selected == selected, "archive screened set mismatch")
    require(indexed_active == ACTIVE_EXCLUSIONS, "archive active exclusion set mismatch")
    require(index["selection_policy"]["outcome_fields_used_for_inclusion"] == [], "outcome-dependent inclusion declared")
    require(index["selection_policy"]["inclusion_rule"], "missing archive inclusion rule")
    require(index["selection_policy"]["omission_rule"], "missing archive omission rule")

    for row in rows:
        require(re.fullmatch(r"[0-9a-f]{64}", row["section_sha256"]) is not None, f"PR {row['pr_number']}: invalid section digest")
        require(row["structured_result_count"] == len(row["structured_results"]), f"PR {row['pr_number']}: result metadata count mismatch")
        require(row["disposition_reason"], f"PR {row['pr_number']}: missing disposition reason")
        if row["disposition"] == "screened_mechanism":
            require(row["mechanism_id"] and row["cluster_id"] and row["family"], f"PR {row['pr_number']}: missing mechanism annotation")
            require(row["exclusion_code"] is None and row["exclusion_reason"] is None, f"PR {row['pr_number']}: screened row has exclusion")
            require(row["disposition_reason"].startswith("Included in the frozen 14-PR diagnostic set"), f"PR {row['pr_number']}: invalid inclusion reason")
        else:
            require(row["exclusion_code"] and row["exclusion_reason"], f"PR {row['pr_number']}: omitted row missing explicit reason")
            require(row["disposition_reason"] == row["exclusion_reason"], f"PR {row['pr_number']}: exclusion reason mismatch")

    counts = {
        name: sum(row["disposition"] == name for row in rows)
        for name in ("screened_mechanism", "predeclared_active_exclusion", "omitted")
    }
    require(counts == index["summary"]["dispositions"], "archive disposition count mismatch")
    require(counts == {"screened_mechanism": 14, "predeclared_active_exclusion": 5, "omitted": 243}, "archive reduction mismatch")


def validate_pr517_evidence(data):
    evidence = data["pr517_isolated_gain_evidence"]
    row = next(row for row in data["mechanisms"] if row["pr_number"] == 517)
    require(evidence["reported_unit_label"] == "microseconds_per_decode_token", "PR517 reported unit changed")
    require(evidence["scored_calls_per_decode_token"] == 39, "PR517 scored call census changed")
    require(evidence["absolute_base_times_available"] is False, "PR517 base times unexpectedly available")
    require(evidence["absolute_candidate_times_available"] is False, "PR517 candidate times unexpectedly available")
    require(evidence["isolated_loop_normalizer_available"] is False, "PR517 isolated normalizer unexpectedly available")
    require(evidence["admissible_per_call_saving_identified"] is False, "PR517 per-call saving incorrectly identified")
    require(evidence["admissible_projected_saving_identified"] is False, "PR517 projected saving incorrectly identified")
    require(row["flags"]["isolated_absolute_pair"] is False and row["eligible"] is False, "PR517 eligibility changed")

    for block in evidence["gain_vectors"]:
        values = block["values"]
        require(len(values) == 7 and all(value > 0 for value in values), f"PR517 {block['block_id']}: invalid gain vector")
        require(math.isclose(statistics.median(values), block["reported_median"], rel_tol=0, abs_tol=1e-12), f"PR517 {block['block_id']}: median mismatch")


def verify_artifacts(data, archive_bytes):
    artifacts = data["artifacts"]
    require(len(artifacts) == len({artifact["artifact_id"] for artifact in artifacts}), "duplicate artifact id")
    verified = 0
    unverified = 0
    for artifact in artifacts:
        expected = artifact["sha256"]
        require(re.fullmatch(r"[0-9a-f]{64}", expected) is not None, f"{artifact['artifact_id']}: invalid recorded digest")
        availability = artifact["availability"]
        if availability == "committed":
            path = ROOT_PATH / artifact["path"]
            require(path.is_file(), f"{artifact['artifact_id']}: committed artifact missing")
            require_digest(path.read_bytes(), expected, artifact["artifact_id"])
            verified += 1
        elif availability == "external_controller_state":
            if archive_bytes is None:
                require(artifact["verification_status_without_bytes"] == "unverified", f"{artifact['artifact_id']}: missing unverified status")
                unverified += 1
            else:
                require_digest(archive_bytes, expected, artifact["artifact_id"])
                verified += 1
        elif availability == "unavailable_external":
            require(artifact["verification_status"] == "unverified", f"{artifact['artifact_id']}: unavailable artifact claimed verified")
            unverified += 1
        else:
            raise AuditError(f"{artifact['artifact_id']}: unsupported availability")
    return verified, unverified


def expect_failure(name, action):
    try:
        action()
    except AuditError:
        print(f"PASS negative-control {name}")
        return
    raise AuditError(f"negative control unexpectedly passed: {name}")


def run_negative_controls(data, index, archive_bytes):
    expected_controls = {
        "duplicate_mechanism_row",
        "swap_time_units",
        "omit_order",
        "alter_candidate_sha",
        "archive_extraction_missing_pr",
        "archive_result_coverage_mismatch",
        "real_digest_mismatch",
        "archive_byte_mismatch",
    }
    require(set(data["negative_controls"]) == expected_controls, "negative control declaration mismatch")

    duplicate = copy.deepcopy(data["mechanisms"])
    duplicate.append(copy.deepcopy(duplicate[0]))
    expect_failure("duplicate_mechanism_row", lambda: validate_cohort(data, duplicate))

    swapped = copy.deepcopy(data["mechanisms"])
    swapped[0]["isolated_units"] = "milliseconds"
    expect_failure("swap_time_units", lambda: validate_cohort(data, swapped))

    missing_order = copy.deepcopy(data["arithmetic_checks"][0])
    del missing_order["order"]
    expect_failure("omit_order", lambda: recompute_block(missing_order))

    altered_sha = copy.deepcopy(data["mechanisms"])
    target = next(row for row in altered_sha if row["pr_number"] == 517)
    target["full_candidate_sha"] = "0" * 40
    expect_failure("alter_candidate_sha", lambda: validate_cohort(data, altered_sha))

    missing_pr = copy.deepcopy(index)
    missing_pr["pull_requests"].pop()
    expect_failure("archive_extraction_missing_pr", lambda: validate_archive_index(missing_pr, data))

    wrong_total = copy.deepcopy(index)
    wrong_total["source_archive"]["structured_result_count"] += 1
    expect_failure("archive_result_coverage_mismatch", lambda: validate_archive_index(wrong_total, data))

    index_artifact = next(artifact for artifact in data["artifacts"] if artifact["artifact_id"] == "committed_archive_index")
    expect_failure("real_digest_mismatch", lambda: require_digest(INDEX_PATH.read_bytes() + b"\n", index_artifact["sha256"], "tampered archive index"))

    tampered_archive = (archive_bytes or b"") + b"\n"
    expect_failure("archive_byte_mismatch", lambda: require_digest(tampered_archive, index["source_archive"]["sha256"], "tampered source archive"))


def default_archive_path():
    state_dir = os.environ.get("SENPAI_OPENHANDS_STATE_DIR")
    if not state_dir:
        return None
    candidate = Path(state_dir) / "github" / ARCHIVE_FILENAME
    return candidate if candidate.is_file() else None


def main():
    parser = argparse.ArgumentParser(description="Validate the frozen local Amdahl-realization audit")
    parser.add_argument("--archive", type=Path, help="path to the frozen typed-get-prs Markdown archive")
    parser.add_argument("--write-index", action="store_true", help="regenerate the committed archive index from --archive")
    args = parser.parse_args()

    data = load_json(DATA_PATH)
    archive_path = args.archive or default_archive_path()
    archive_bytes = archive_path.read_bytes() if archive_path else None

    if args.write_index:
        require(archive_bytes is not None, "--write-index requires an available archive")
        INDEX_PATH.write_text(json.dumps(build_archive_index(archive_bytes, data), indent=2) + "\n", encoding="utf-8")
        print(f"WROTE archive-index path={INDEX_PATH}")
        return

    index = load_json(INDEX_PATH)
    validate_archive_index(index, data)
    print("PASS archive-index pr_sections=262 structured_results=274 screened=14 active_excluded=5 omitted=243")
    if archive_bytes is not None:
        require(build_archive_index(archive_bytes, data) == index, "source archive extraction differs from committed index")
        print(f"PASS source-archive bytes={len(archive_bytes)} sha256={sha256_bytes(archive_bytes)}")
    else:
        print("UNVERIFIED source-archive bytes unavailable; committed index coverage only")

    eligible = validate_cohort(data)
    require(len(data["mechanisms"]) == data["decision"]["screened_mechanisms"], "screened mechanism count mismatch")
    require(len({row["family"] for row in data["mechanisms"]}) == data["decision"]["screened_families"], "screened family count mismatch")
    eligible_clusters = {row["cluster_id"] for row in eligible}
    eligible_families = {row["family"] for row in eligible}
    require(len(eligible_clusters) == data["decision"]["eligible_mechanism_clusters"], "eligible cluster count mismatch")
    require(len(eligible_families) == data["decision"]["eligible_families"], "eligible family count mismatch")

    for check in data["arithmetic_checks"]:
        result = recompute_block(check)
        print(f"PASS arithmetic {check['check_id']} weighted_speedup={result['weighted_speedup']:.12f}")

    realization = validate_positive_control(data["synthetic_positive_control"], data["canonical_time_unit"])
    print(f"PASS synthetic-positive family=synthetic_control realization={realization:.6f}")
    validate_pr517_evidence(data)
    print("PASS pr517-semantics admissible_per_call_saving=false admissible_projected_saving=false")
    verified, unverified = verify_artifacts(data, archive_bytes)
    print(f"PASS artifact-byte-verification verified={verified} unverified={unverified}")
    run_negative_controls(data, index, archive_bytes)

    threshold = data["assignment"]["decision_threshold"]
    require(len(eligible_clusters) < threshold["minimum_mechanism_clusters"] or len(eligible_families) < threshold["minimum_families"], "NO-GO declaration conflicts with eligible cohort")
    require(data["decision"]["verdict"] == "NO-GO", "unexpected decision verdict")
    print(
        "NO-GO "
        f"eligible_clusters={len(eligible_clusters)}/{threshold['minimum_mechanism_clusters']} "
        f"eligible_families={len(eligible_families)}/{threshold['minimum_families']}"
    )


if __name__ == "__main__":
    main()
