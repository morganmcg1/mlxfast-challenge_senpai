#!/usr/bin/env python3

import copy
import json
import math
import string
from decimal import Decimal
from pathlib import Path


DATA_PATH = Path(__file__).with_name("local_amdahl_realization_cohort.json")
EXPECTED_ORDERS = (["A", "B", "B", "A"], ["B", "A", "A", "B"])
TOLERANCE = 5e-15


class AuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


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
            require(isinstance(row["candidate_sha"], str) and len(row["candidate_sha"]) == 40, f"{row['mechanism_id']}: invalid candidate SHA")
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


def validate_artifacts(artifacts):
    require(len(artifacts) == len({artifact["locator"] for artifact in artifacts}), "duplicate artifact locator")
    hexadecimal = set(string.hexdigits.lower())
    for artifact in artifacts:
        digest = artifact["sha256"]
        require(len(digest) == 64 and set(digest) <= hexadecimal, f"invalid SHA-256 for {artifact['locator']}")


def expect_failure(name, action):
    try:
        action()
    except AuditError:
        print(f"PASS negative-control {name}")
        return
    raise AuditError(f"negative control unexpectedly passed: {name}")


def run_negative_controls(data):
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


def main():
    with DATA_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)

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
    validate_artifacts(data["imported_artifacts"])
    print(f"PASS artifact-hashes count={len(data['imported_artifacts'])}")
    run_negative_controls(data)

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
