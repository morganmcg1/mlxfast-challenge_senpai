#!/usr/bin/env python3
"""Log the R90-A native-AGX instruction census to W&B.

Reads research/maple-frieren-pr481-census.tsv (the measured __compute sizes) and
publishes every raw arm plus the derived slopes and gate verdicts. This arm
produces no timing metrics; the counts are the result.

    python3 research/maple-frieren-pr481-log-wandb.py
"""
import csv
import os
import pathlib

import wandb

ROOT = pathlib.Path(__file__).resolve().parents[1]
TSV = ROOT / "research" / "maple-frieren-pr481-census.tsv"

ARCHS = ("applegpu_g16s", "applegpu_g17s")
REAL_ROUTER = (
    "custom_kernel_laguna_prefill_router_tournament_ordinal"
    "_active64_v2_bfloat16_t_float_uint32_t_float"
)
S4A_GATE = 0.40


def load():
    by_arch = {a: {} for a in ARCHS}
    with TSV.open() as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            by_arch[row["arch"]][row["fn"]] = int(row["compute_bytes"])
    return by_arch


def slope(v, lo_fn, hi_fn, lo_n, hi_n):
    return (v[hi_fn] - v[lo_fn]) / (hi_n - lo_n)


def main():
    by_arch = load()
    run = wandb.init(
        project="mlxfast-maple",
        entity="wandb-applied-ai-team",
        job_type="offline-census",
        name="maple-frieren-r90a-agx-instruction-census",
        tags=["r90-a", "agx-native-census", "no-gpu", "zero-editable-bytes"],
        config={
            "assignment_id": "maple-r90-a-agx-instruction-census",
            "revision_id": "r90-a-rev1",
            "pr": 481,
            "student": "maple-frieren",
            "metal_std": "-std=metal4.0",
            "fast_math": "-fno-fast-math",
            "platform_version": "macos 26.0 26.5",
            "toolchain": "Metal 32023.883 / v17.6.109.0, macOS 26.5.2 (25F84), SDK 26.5",
            "archs": list(ARCHS),
            "s4a_gate_fraction": S4A_GATE,
            "censused_kernel": REAL_ROUTER,
            "gpu_used": False,
            "editable_bytes_changed": 0,
        },
    )

    summary = {}
    for arch in ARCHS:
        v = by_arch[arch]
        for fn, b in v.items():
            summary[f"bytes/{arch}/{fn}"] = b

        # Instruction-encoding length per source-level op, by opcode class.
        for cls, stem in (
            ("fadd", "e_fadd"),
            ("ffma", "e_ffma"),
            ("ffma_imm", "e_fimm"),
            ("imad", "e_imad"),
        ):
            summary[f"bytes_per_op/{arch}/{cls}"] = slope(
                v, f"{stem}_064", f"{stem}_128", 64, 128
            )

        # S4-a comparator pricing. The rolled slope is per extra bitonic
        # `sequence` value; the unrolled slope is per comparator stage.
        summary[f"s4a/{arch}/rolled_bytes_per_sequence"] = slope(
            v, "r_cmp10", "r_cmp15", 4, 5
        )
        summary[f"s4a/{arch}/unrolled_bytes_per_stage_bitonic"] = slope(
            v, "r_u01", "r_u15", 1, 15
        )
        summary[f"s4a/{arch}/unrolled_bytes_per_stage_monotone"] = slope(
            v, "r_m01", "r_m05", 1, 5
        )
        summary[f"s4a/{arch}/pragma_unroll_honoured"] = v["r_p15"] != v["r_cmp15"]
        summary[f"s4a/{arch}/rolled_vs_unrolled_15stage_bytes"] = (
            v["r_u15"] - v["r_cmp15"]
        )

        real, mock, null = v[REAL_ROUTER], v["r_cd_mock"], v["r_cmp00"]
        whole = (real - mock) / real
        region = ((real - null) - (mock - null)) / (real - null)
        summary[f"s4a/{arch}/real_bytes"] = real
        summary[f"s4a/{arch}/cd_mock_bytes"] = mock
        summary[f"s4a/{arch}/matched_null_bytes"] = null
        summary[f"s4a/{arch}/drop_whole_kernel"] = whole
        summary[f"s4a/{arch}/drop_censused_region"] = region
        summary[f"s4a/{arch}/gate_pass_whole_kernel"] = whole >= S4A_GATE
        summary[f"s4a/{arch}/gate_pass_censused_region"] = region >= S4A_GATE

        # S4-b marginal cost per NVFP4 code, folding-immune (8-group minus
        # 4-group arm, i.e. the extra 64 codes).
        base = v["n_bp0_8"] - v["n_bp0_4"]
        for variant in ("bp0", "bp1", "bp2", "lut", "sm"):
            marg = v[f"n_{variant}_8"] - v[f"n_{variant}_4"]
            summary[f"s4b/{arch}/{variant}_bytes_per_64_codes"] = marg
            summary[f"s4b/{arch}/{variant}_bytes_per_code"] = marg / 64.0
            summary[f"s4b/{arch}/{variant}_vs_bp0_frac"] = (marg - base) / base

    run.summary.update(summary)
    print(f"run_id={run.id}")
    print(f"url={run.url}")
    run.finish()


if __name__ == "__main__":
    if "WANDB_API_KEY" not in os.environ:
        raise SystemExit("WANDB_API_KEY is not set")
    main()
