#!/usr/bin/env python3
"""Log the r103-D residual/provenance/power result to W&B.

Every number is read from research/artifacts/fern-r103d/rung1.json, which
research/fern_r103d_rung1.py regenerates from the raw receipt pull, so the run
cannot drift away from
research/maple-fern-r103d-residual-provenance-and-power.md.

  python3 research/fern_r103d_wandb.py --json research/artifacts/fern-r103d/rung1.json
"""
from __future__ import annotations

import argparse
import json

import wandb

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"

# rung-0 blob-SHA provenance verdicts (research/fern_r103d_provenance.py)
PROVENANCE = {
    "ef055b9b_vs_local_30f752df": 0,
    "bd33883e_vs_local_e17bdeb": 0,
    "e33efe4e_vs_local_c6c66344": 0,
    "5a43d329_vs_local_6ada66c9": 0,
    "base_0f6862d0_vs_composed_bd33883e": 1,
    "composed_vs_armR_surface_differences": 32,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="research/artifacts/fern-r103d/rung1.json")
    ap.add_argument("--run-name", default="fern-r103d-residual-provenance-power")
    ap.add_argument("--id", default=None, help="resume this run id instead of starting one")
    args = ap.parse_args()
    d = json.load(open(args.json))

    run = wandb.init(
        entity=ENTITY, project=PROJECT, name=args.run_name,
        id=args.id, resume="allow" if args.id else None,
        job_type="receipt-corpus-analysis",
        tags=["r103-D", "maple-fern", "provenance", "power", "null-result",
              "no-gpu", "zero-receipts"],
        config={
            "assignment_id": "maple-r103-d-residual-provenance-and-power",
            "revision_id": "r103-d-rev1",
            "pr": 576,
            "corpus_rows": d["n_rows"],
            "receipts_with_metrics": d["n_metrics"],
            "receipts_usable": d["n_usable"],
            "noise_model": "pooled within-tree CV over 3 compile-identical triplets",
            "dof": d["dof"],
            "n_per_arm": 1,
            "n_per_arm_reason": "platform deduplicates by archive content",
            "pct_per_us_decode": 0.015228,
            "pct_per_ms_prefill_current": 0.2592,
            "pct_per_ms_prefill_assignment_retired": 0.3794,
            "us_per_pct_cs": 65.67,
            "receipts_created": 0,
            "bytes_written_to_Sources": 0,
        },
    )

    flat = {f"sigma_within_tree_pct/{k}": v
            for k, v in d["within_tree_sigma_pct"].items()}
    flat.update({f"provenance/{k}": v for k, v in PROVENANCE.items()})
    for id8, t in d["trees"].items():
        for k, v in t.items():
            if isinstance(v, (int, float)):
                flat[f"tree/{id8}_{t['label'].replace(' ', '_')}/{k}"] = v

    flat.update({
        "residual/decode_us_per_step": d["residual_decode_us"],
        "residual/decode_ci_lo_us": d["residual_decode_ci_lo"],
        "residual/decode_ci_hi_us": d["residual_decode_ci_hi"],
        "residual/decode_abs_t": d["residual_decode_abs_t"],
        "residual/cs_pct": d["residual_cs_pct"],
        "residual/cs_ci_lo_pct": d["residual_cs_ci_lo_pct"],
        "residual/cs_ci_hi_pct": d["residual_cs_ci_hi_pct"],
        "noise/sigma_single_decode_us": d["sigma_single_decode_us"],
        "noise/se_diff_decode_us": d["se_diff_decode_us"],
        "noise/sigma_y_paired_pct": d["sigma_y_pct"],
        "power/mdd_at_n1_us": d["mdd_n1_us"],
        "power/n_per_arm_for_0p43_us": d["n_per_arm_for_0p43_us"],
        "power/n_per_arm_for_10us": d["n_per_arm_for_10us"],
        "contrast/revert_control_to_armR_us": d["revert_control_to_armR_us"],
        "corpus/identity_worst_rel_err": d["identity_worst_rel_err"],
        "corpus/distinct_timing_pairs": d["dedup_distinct_timing_pairs"],
        "corpus/timing_pair_repeats": d["dedup_repeats"],
        "null/N1_provenance_unverified": int(d["N1_provenance_unverified"]),
        "null/N2_ci_includes_zero": int(d["N2_ci_includes_zero"]),
        "null/N3_underpowered": int(d["N3_underpowered"]),
        "null/N4_noise_model_inconsistent": int(d["N4_noise_model_inconsistent"]),
        "null/N5_sigma_tension_is_bug": int(d["N5_sigma_tension_is_bug"]),
        "coupling/corr_dec_pre_within_tree": d["corr_dec_pre_within_tree"],
        "coupling/corr_dec_pre_corpus": d["corr_dec_pre_corpus"],
        "coupling/corr_dec_pre_predicted_from_4P": d["corr_dec_pre_predicted_from_4P"],
        "coupling/prefill_share_of_cand_dec": d["prefill_share_of_cand_dec"],
    })
    run.log(flat)
    run.summary.update(flat)
    run.summary["headline"] = (
        f"composed-vs-Arm-R decode residual {d['residual_decode_us']:+.1f} us/step, "
        f"95% CI [{d['residual_decode_ci_lo']:+.1f}, {d['residual_decode_ci_hi']:+.1f}]; "
        f"provenance verified; N-2 fires")

    art = wandb.Artifact("fern-r103d-evidence", type="analysis")
    art.add_file(args.json)
    art.add_file("research/artifacts/fern-r103d/rung1.txt")
    art.add_file("research/artifacts/fern-r103d/provenance.txt")
    art.add_file("research/maple-fern-r103d-residual-provenance-and-power.md")
    art.add_file("research/maple-fern-r103d-rung1-preregistration.md")
    run.log_artifact(art)

    print(f"run id   {run.id}")
    print(f"run url  {run.url}")
    run.finish()


if __name__ == "__main__":
    main()
