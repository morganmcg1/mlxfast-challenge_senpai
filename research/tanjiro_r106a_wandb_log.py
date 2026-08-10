"""Publishes the R106-A decode byte-composition ledger to W&B.

Reads the artifact produced by `tanjiro_r106a_byte_ledger.py` and logs the
Stage-1 reconciliation, the Stage-2 metadata classification, and the Stage-3
gate verdict as one summary-only run (no training, no timing).
"""

import json
import os
import sys

import wandb

ART = "research/artifacts/maple-tanjiro-r106a/decode-metadata-ledger.json"
B = 1_671_402_432
US_PER_PCT_SCORE = 65.67
US_PER_PCT_B = 27.731


def main():
    with open(ART) as fh:
        d = json.load(fh)
    led, ceil, sc = d["ledger"], d["ceiling"], d["scales"]
    tot = ceil["_total"]

    cfg = {
        "assignment_id": "maple-r106-a-decode-byte-composition",
        "revision_id": "r106-a-rev1",
        "pr": 615,
        "student": "maple-tanjiro",
        "base_sha": "0954002c16014a03091e1856cdf356fb0e6a3e38",
        "accepted_step_bytes_B": B,
        "stage3_gate_pct_of_B": 1.2,
        "us_per_pct_of_B": US_PER_PCT_B,
        "us_per_pct_of_score": US_PER_PCT_SCORE,
        "official_receipts_used": 0,
        "code_changed": False,
    }

    run = wandb.init(
        project="mlxfast-maple",
        entity="wandb-applied-ai-team",
        name="r106a-decode-byte-composition",
        job_type="analysis",
        tags=["r106-a", "maple-tanjiro", "pr615", "ledger", "no-timing"],
        config=cfg,
        notes=(
            "Stage-1 exact byte ledger for one decode step + Stage-2 bit-exact "
            "classification of quantisation metadata. Stage-3 build gate did "
            "not open."
        ),
    )

    m = {
        "stage1/derived_step_bytes": led["derived_step_bytes"],
        "stage1/accepted_step_bytes": led["accepted_step_bytes"],
        "stage1/residual_bytes": led["reconciliation_residual_bytes"],
        "stage1/residual_pct_of_B": led["reconciliation_residual_pct_of_B"],
        "stage1/families_total": len(led["families"]),
        "stage1/families_exact": sum(
            1 for f in led["families"] if f["delta_bytes"] == 0),
        "stage1/omitted_activation_operand_bytes":
            led["omitted_activation_operand_bytes"],
        "stage1/omitted_activation_operand_pct_of_B":
            led["omitted_activation_operand_pct_of_B"],
        "stage2/metadata_total_bytes": led["metadata_total_bytes"],
        "stage2/metadata_pct_of_B": led["metadata_pct_of_B"],
        "stage2/metadata_pct_of_score_if_fully_free":
            led["metadata_pct_of_score_if_fully_free"],
        "stage3/addressable_saving_bytes": tot["nibble_delta_saving"],
        "stage3/addressable_pct_of_B": tot["nibble_delta_pct_of_B"],
        "stage3/addressable_pct_of_score": tot["nibble_delta_pct_of_score"],
        "stage3/entropy_floor_saving_bytes": tot["entropy_saving"],
        "stage3/entropy_floor_pct_of_B": tot["entropy_pct_of_B"],
        "stage3/largest_single_component_pct_of_B":
            tot["largest_single_component_pct_of_B"],
        "stage3/gate_opened": False,
    }
    for name, bucket in led["buckets"].items():
        m[f"bucket/{name}/payload_bytes"] = bucket["payload"]
        m[f"bucket/{name}/metadata_bytes"] = bucket["metadata"]
    for site, row in ceil.items():
        if site == "_total":
            continue
        m[f"site/{site}/metadata_bytes_now"] = row["metadata_bytes_now"]
        m[f"site/{site}/nibble_delta_saving"] = row["nibble_delta_saving"]
        m[f"site/{site}/nibble_delta_pct_of_B"] = row["nibble_delta_pct_of_B"]
        if row["measured_g32_entropy_bits"]:
            m[f"site/{site}/g32_entropy_bits"] = row["measured_g32_entropy_bits"]
    for cls, st in sc.items():
        for k in ("run2_equal_frac", "run4_equal_frac", "run8_equal_frac",
                  "g32_row_span_le15_frac", "g32_row_distinct_mean",
                  "g32_row_distinct_max", "g32_entropy_bits"):
            m[f"census/{cls}/{k}"] = st[k]
        m[f"census/{cls}/run2_exceptions"] = st["run2_exceptions"]
    run.log(m)
    run.summary.update(m)

    cols = ["bucket", "payload_bytes", "metadata_bytes", "metadata_pct_of_B"]
    tbl = wandb.Table(columns=cols)
    for name, bucket in led["buckets"].items():
        tbl.add_data(name, bucket["payload"], bucket["metadata"],
                     100.0 * bucket["metadata"] / B)
    run.log({"stage1/bucket_ledger": tbl})

    fam = wandb.Table(columns=["family", "bucket", "calls", "payload_bytes",
                               "metadata_bytes", "derived_bytes",
                               "accepted_bytes", "delta_bytes"])
    for f in led["families"]:
        fam.add_data(f["family"], f["bucket"], f["calls"], f["payload_bytes"],
                     f["metadata_bytes"], f["derived_bytes"],
                     f["accepted_bytes"], f["delta_bytes"])
    run.log({"stage1/family_ledger": fam})

    art = wandb.Artifact("r106a-decode-metadata-ledger", type="analysis")
    art.add_file(ART)
    run.log_artifact(art)
    print(run.url)
    print(run.id)
    run.finish()
    return 0


if __name__ == "__main__":
    if not os.path.exists(ART):
        sys.exit(f"missing artifact {ART}; run tanjiro_r106a_byte_ledger.py first")
    sys.exit(main())
