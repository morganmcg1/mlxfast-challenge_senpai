#!/usr/bin/env python3
"""Log the r92-b g16s-vs-g17s decode-path encoding census to W&B.

One run per stage:

  stage1       dispatch decomposition of the equivalence-oracle vehicle
  stage2       matched static __compute census of the oracle-path decode kernels
  stage3       ablation bisection of the two kernels with a positive g17s excess
  stage1prime  the same census on the *scored* local-iterate decode path, which
               dispatches a different kernel set and flips the aggregate sign

This arm produces no timing metrics; per advisor rule 42 the static byte counts
are the result, and they are admissible only as matched-null differences within
one opcode class and one loop structure.

    python3 research/maple-frieren-r92-log-wandb.py \
        [stage1|stage2|stage3|stage1prime|all]
"""
import csv
import pathlib
import sys

import wandb

ROOT = pathlib.Path(__file__).resolve().parents[1]
ART = ROOT / "research" / "r92-artifacts"
CENSUS = ART / "r92-census.tsv"
BISECT = ART / "r92-bisect.tsv"
MANIFEST = ART / "r92-kernel-manifest.tsv"
CENSUS_SCORED = ART / "r92-census-scored.tsv"
MANIFEST_SCORED = ART / "r92-kernel-manifest-scored.tsv"
STAGE1PRIME = ART / "r92-census-stage1prime.txt"

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"
ARCHS = ("applegpu_g16s", "applegpu_g17s")

BASE_CONFIG = {
    "assignment_id": "maple-r92-b-m5-encoding-census",
    "revision_id": "r92-b-rev1",
    "pr": 490,
    "student": "maple-frieren",
    "base_sha": "8486638578a283de40369172f68c3a4d2d6a5365",
    "host_gpu": "apple_m4_pro",
    "host_arch": "applegpu_g16s",
    "metal_std": "-std=metal4.0",
    "fast_math": "-fno-fast-math",
    "toolchain": "Metal v17.6.109.0.92Vqge",
    "archs": list(ARCHS),
    "gpu_used_for_timing": False,
    "editable_bytes_changed": 0,
    "g17s_is_m5_max": "inference_not_documented",
}

# Instrumented custom-kernel dispatches in one steady teacher-forced decode step.
DISPATCHES = {
    "laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1": 39,
    "laguna_prefill_router_tournament_ordinal_norm_active64_v2": 39,
    "laguna_fused_norm_qkv_projection_bf16_h64_v3": 30,
    "laguna_sliding_fused_attn_ring_v1": 30,
    "laguna_gated_output_projection_bf16_h64_u2_v3": 30,
    "laguna_fused_norm_qkv_projection_bf16_h48_v3": 10,
    "laguna_full_fused_attn_grow_v1": 10,
    "laguna_gated_output_projection_bf16_h48_u2_v3": 10,
    "laguna_residual_rms_bf16_2048_v1": 1,
    "laguna_dense_down_residual_bf16_v1": 1,
    "laguna_full_qk_norm_yarn_bf16_128_v4": 0,
    "laguna_prefill_moe_tail_bf16_v1": 0,
}
NOISE_BAND_BYTES = 16


def load_census(path=CENSUS):
    by_study = {}
    with path.open() as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            by_study.setdefault(row["study"], {}).setdefault(row["arch"], {})[
                row["fn"]
            ] = int(row["compute_bytes"])
    return by_study


def kernel_of(fn):
    """Map an MLX mangled entry-point symbol back to its Laguna kernel name.

    `census.sh` records `kernel_name()`, i.e. `custom_kernel_<name>_<dtype>...`,
    so the dispatch table has to be keyed by containment rather than equality.
    """
    stem = fn[len("custom_kernel_"):] if fn.startswith("custom_kernel_") else fn
    hits = [k for k in DISPATCHES if stem.startswith(k)]
    if not hits:
        raise KeyError(f"no dispatch-table kernel matches {fn}")
    return max(hits, key=len)


def finish(run, summary):
    run.summary.update(summary)
    run.finish()


def stage1():
    run = wandb.init(
        project=PROJECT,
        entity=ENTITY,
        job_type="offline-census",
        name="maple-frieren-r92b-stage1-dispatch-decomposition",
        group="maple-frieren-r92b",
        tags=["r92-b", "stage1", "msl-dump", "no-timing", "zero-editable-bytes"],
        config={
            **BASE_CONFIG,
            "stage": 1,
            "vehicle": "upstream_equivalence_oracle_under_swift_test",
            "verbose_sites": 48,
            "dump_bytes": 12033105,
            "dump_emissions": 1717,
            "equivalence_exact_steps": 8,
        },
    )
    summary = {
        "dispatch/prefill": 115,
        "dispatch/decode_step0": 202,
        "dispatch/decode_steady": 200,
        "dispatch/total_emissions": 1717,
        "dump/distinct_kernels": 12,
        "dump/multi_variant_kernels": 0,
        "dump/nvfp4_occurrences": 0,
        "oracle/prefill_max_abs_logit_error": 0.125,
        "oracle/prefill_mean_abs_logit_error": 0.011933609,
        "oracle/decode_max_abs_logit_error": 0.0,
        "oracle/argmax_matches_upstream": 1,
    }
    for k, n in DISPATCHES.items():
        summary[f"dispatch/steady/{k}"] = n
    if MANIFEST.exists():
        with MANIFEST.open() as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                summary[f"manifest/emissions/{row['name']}"] = int(row["occurrences"])
                summary[f"manifest/gen_bytes/{row['name']}"] = int(row["gen_bytes"])
    finish(run, summary)


def stage2():
    by_study = load_census()
    run = wandb.init(
        project=PROJECT,
        entity=ENTITY,
        job_type="offline-census",
        name="maple-frieren-r92b-stage2-matched-census",
        group="maple-frieren-r92b",
        tags=["r92-b", "stage2", "agx-census", "no-timing", "zero-editable-bytes"],
        config={
            **BASE_CONFIG,
            "stage": 2,
            "noise_band_bytes": NOISE_BAND_BYTES,
            "floor_correction_bracket": "-16..0",
        },
    )

    summary = {}
    for study, by_arch in by_study.items():
        for arch, fns in by_arch.items():
            for fn, b in fns.items():
                summary[f"bytes/{study}/{arch}/{fn}"] = b

    # Control 1: marginal bytes per source-level op, by opcode class.
    enc = by_study.get("r92_encoding", {})
    for cls in ("fadd", "ffma", "fimm", "imad"):
        for arch in ARCHS:
            v = enc.get(arch, {})
            lo, hi = v.get(f"e_{cls}_064"), v.get(f"e_{cls}_128")
            if lo is not None and hi is not None:
                summary[f"bytes_per_op/{arch}/{cls}"] = (hi - lo) / 64.0
    g16 = summary.get("bytes_per_op/applegpu_g16s/imad")
    g17 = summary.get("bytes_per_op/applegpu_g17s/imad")
    if g16 and g17:
        summary["control1/imad_g17s_over_g16s"] = g17 / g16
        summary["control1/pass"] = int(abs(g16 - 12.0) < 0.51 and abs(g17 - 14.0) < 0.51)

    # Control 2: the arch floor delta is not a constant -16 B.
    fl = by_study.get("r92_floor", {})
    for fn in sorted(fl.get(ARCHS[0], {})):
        a, b = fl[ARCHS[0]][fn], fl[ARCHS[1]].get(fn)
        if b is not None:
            summary[f"control2/floor_delta/{fn}"] = b - a
    if "floor_buf4_bf16_simd" in fl.get(ARCHS[0], {}):
        summary["control2/simd_floor_delta"] = (
            fl[ARCHS[1]]["floor_buf4_bf16_simd"] - fl[ARCHS[0]]["floor_buf4_bf16_simd"]
        )

    # Stage 2 proper: per-kernel delta, and the dispatch-weighted excess.
    dec = by_study.get("r92_decode", {})
    weighted_pos = 0
    weighted_all = 0
    n_pos = n_neg = n_noise = 0
    for fn, a in sorted(dec.get(ARCHS[0], {}).items()):
        b = dec[ARCHS[1]].get(fn)
        if b is None:
            continue
        d = b - a
        kernel = kernel_of(fn)
        n = DISPATCHES[kernel]
        summary[f"delta/{kernel}"] = d
        summary[f"delta_pct/{kernel}"] = 100.0 * d / a
        summary[f"weighted_delta/{kernel}"] = n * d
        weighted_all += n * d
        if d > NOISE_BAND_BYTES:
            n_pos += 1
            weighted_pos += n * d
        elif d < -NOISE_BAND_BYTES:
            n_neg += 1
        else:
            n_noise += 1
    summary["stage2/weighted_positive_excess_bytes_per_step"] = weighted_pos
    summary["stage2/weighted_net_delta_bytes_per_step"] = weighted_all
    summary["stage2/kernels_g17s_larger"] = n_pos
    summary["stage2/kernels_g17s_smaller"] = n_neg
    summary["stage2/kernels_noise"] = n_noise
    finish(run, summary)


def stage3():
    rows = []
    with BISECT.open() as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    run = wandb.init(
        project=PROJECT,
        entity=ENTITY,
        job_type="offline-census",
        name="maple-frieren-r92b-stage3-ablation-bisection",
        group="maple-frieren-r92b",
        tags=["r92-b", "stage3", "ablation", "no-timing", "zero-editable-bytes"],
        config={
            **BASE_CONFIG,
            "stage": 3,
            "kernels": [
                "laguna_sliding_fused_attn_ring_v1",
                "laguna_full_fused_attn_grow_v1",
            ],
            "noise_band_bytes": NOISE_BAND_BYTES,
        },
    )
    base = {
        r["kernel"]: int(r["delta"]) for r in rows if r["ablation"] == "base"
    }
    summary = {}
    for r in rows:
        k, ab = r["kernel"], r["ablation"]
        short = "sliding" if "sliding" in k else "grow"
        summary[f"bisect/{short}/{ab}/g16s"] = int(r["g16s"])
        summary[f"bisect/{short}/{ab}/g17s"] = int(r["g17s"])
        summary[f"bisect/{short}/{ab}/delta"] = int(r["delta"])
        summary[f"bisect/{short}/{ab}/delta_vs_base"] = int(r["delta"]) - base[k]
    # The two headline falsifications.
    summary["stage3/epilogue_vec_simd_sum_is_canonicalised"] = 1
    summary["stage3/simd_sum_ladder_regression_bytes_g16s"] = 944
    summary["stage3/simd_sum_ladder_regression_bytes_g17s"] = 912
    summary["stage3/loop_is_rolled"] = 1
    summary["verdict"] = "H0"
    finish(run, summary)


def parse_stage1prime():
    """Read the weighted scored-step table emitted by weight_scored_step.py."""
    rows = []
    totals = {}
    steady = None
    for line in STAGE1PRIME.read_text().splitlines():
        if line.startswith("decode_steps_sampled="):
            steady = int(line.split("steady_dispatches=")[1])
        elif line.startswith("weighted_"):
            key, val = line.split("=", 1)
            lo, hi = (int(x) for x in val.split(".."))
            totals[key] = (lo, hi)
        elif line.startswith("laguna_"):
            f = line.split()
            rows.append(
                {
                    "kernel": f[0],
                    "n": int(f[1]),
                    "g16s": int(f[2]),
                    "g17s": int(f[3]),
                    "raw": int(f[4]),
                    "w_raw": int(f[5]),
                    "w_hi": int(f[6]),
                }
            )
    return steady, rows, totals


def stage1prime():
    steady, rows, totals = parse_stage1prime()
    by_study = load_census(CENSUS_SCORED)
    run = wandb.init(
        project=PROJECT,
        entity=ENTITY,
        job_type="offline-census",
        name="maple-frieren-r92b-stage1prime-scored-path-census",
        group="maple-frieren-r92b",
        tags=[
            "r92-b",
            "stage1prime",
            "agx-census",
            "scored-path",
            "no-timing",
            "zero-editable-bytes",
        ],
        config={
            **BASE_CONFIG,
            "stage": "1prime",
            "vehicle": "local_iterate_worker_stderr_budgeted_msl_dump",
            "dump_budget_per_worker": 2000,
            "dump_bytes": 21275521,
            "dump_emissions": 2690,
            "dump_distinct_kernels": 27,
            "noise_band_bytes": NOISE_BAND_BYTES,
            "floor_correction_bracket": "-16..0",
            "supersedes": "stage2_weighted_aggregates",
        },
    )

    summary = {}
    for study, by_arch in by_study.items():
        for arch, fns in by_arch.items():
            for fn, b in fns.items():
                summary[f"bytes/{study}/{arch}/{fn}"] = b

    # Control 1 reproduced in-session on the scored census invocation.
    enc = by_study.get("r92_encoding", {})
    for cls in ("fadd", "ffma", "fimm", "imad"):
        for arch in ARCHS:
            v = enc.get(arch, {})
            lo, hi = v.get(f"e_{cls}_064"), v.get(f"e_{cls}_128")
            if lo is not None and hi is not None:
                summary[f"bytes_per_op/{arch}/{cls}"] = (hi - lo) / 64.0
    g16 = summary.get("bytes_per_op/applegpu_g16s/imad")
    g17 = summary.get("bytes_per_op/applegpu_g17s/imad")
    if g16 and g17:
        summary["control1/imad_g17s_over_g16s"] = g17 / g16
        summary["control1/pass"] = int(abs(g16 - 12.0) < 0.51 and abs(g17 - 14.0) < 0.51)

    fl = by_study.get("r92_floor", {})
    for fn in sorted(fl.get(ARCHS[0], {})):
        b = fl[ARCHS[1]].get(fn)
        if b is not None:
            summary[f"control2/floor_delta/{fn}"] = b - fl[ARCHS[0]][fn]

    for r in rows:
        k = r["kernel"]
        summary[f"dispatch/steady_scored/{k}"] = r["n"]
        summary[f"delta/{k}"] = r["raw"]
        summary[f"delta_pct/{k}"] = 100.0 * r["raw"] / r["g16s"]
        summary[f"weighted_delta/{k}"] = r["w_raw"]
        summary[f"weighted_delta_hi/{k}"] = r["w_hi"]

    if MANIFEST_SCORED.exists():
        with MANIFEST_SCORED.open() as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                summary[f"manifest_scored/gen_bytes/{row['name']}"] = int(
                    row["gen_bytes"]
                )
                summary[f"manifest_scored/distinct_variants/{row['name']}"] = int(
                    row["distinct_variants"]
                )

    def cluster(*names):
        return sum(r["w_raw"] for r in rows if r["kernel"] in names)

    summary["stage1prime/steady_dispatches"] = steady
    summary["stage1prime/censused_steady_kernels"] = len(rows)
    for key, (lo, hi) in totals.items():
        summary[f"stage1prime/{key}"] = lo
        summary[f"stage1prime/{key}_hi"] = hi
    summary["stage1prime/oproj_cluster_weighted_bytes_per_step"] = cluster(
        "laguna_oproj_act_h64_v1_lm1_pw1_sc1_se1",
        "laguna_oproj_act_h48_v1_lm1_pw1_sc1_se1",
        "laguna_gate_sp_h64_v1",
        "laguna_gate_sp_h48_v1",
    )
    summary["stage1prime/nvfp4_trio_weighted_bytes_per_step"] = cluster(
        "laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6",
        "laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1",
        "laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2",
    )
    summary["stage1prime/attention_pair_weighted_bytes_per_step"] = cluster(
        "laguna_sliding_fused_attn_ring_v1",
        "laguna_full_fused_attn_grow_v1",
    )
    # Stage 2 censused four kernels the scored path never dispatches, so its
    # dispatch-weighted aggregate is retracted and the net sign flips.
    summary["stage1prime/stage2_weights_retracted"] = 1
    summary["stage1prime/stage2_weighted_net_delta_bytes_per_step"] = -24864
    for k in (
        "laguna_fused_norm_qkv_projection_bf16_h64_v3",
        "laguna_fused_norm_qkv_projection_bf16_h48_v3",
        "laguna_gated_output_projection_bf16_h64_u2_v3",
        "laguna_gated_output_projection_bf16_h48_u2_v3",
        "laguna_prefill_moe_tail_bf16_v1",
    ):
        summary[f"offpath/scored_dispatches/{k}"] = 0
    # Retroactive check of PR #481's mechanically reconstructed router TU.
    summary["pr481/router_recon_g16s"] = 4304
    summary["pr481/router_recon_g17s"] = 4272
    summary["pr481/router_real_g16s"] = 4720
    summary["pr481/router_real_g17s"] = 4688
    summary["pr481/router_abs_byte_gap"] = 416
    summary["pr481/router_delta_reproduces"] = 1
    # The instrumented vehicle's own cost, recorded so it is never mistaken for
    # a candidate regression.
    summary["vehicle/correctness_max_abs_diff"] = 0
    summary["vehicle/correctness_passed"] = 1
    summary["vehicle/instrumented_decode_s_per_token"] = 0.027414
    summary["vehicle/baseline_decode_s_per_token"] = 0.012988
    summary["vehicle/instrumented_est_score"] = 0.455
    summary["vehicle/baseline_est_score"] = 0.796
    summary["verdict"] = "H0"
    finish(run, summary)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in (
        ("stage1", stage1),
        ("stage2", stage2),
        ("stage3", stage3),
        ("stage1prime", stage1prime),
    ):
        if which in (name, "all"):
            fn()
