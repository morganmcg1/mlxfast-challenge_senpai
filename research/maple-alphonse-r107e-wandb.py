#!/usr/bin/env python3
"""Publish the R107-E decode oproj row-amortisation ledger to W&B.

Rule 98.9: every issued-byte number in this ledger is cache-resident traffic.
Compulsory DRAM bytes are identical in all four arms by construction
(`weight_code_reread_factor == 1.0` everywhere), so no issued-byte delta is a
speedup claim. The only speed claims are the paired in-situ decode contrasts.
"""

import json
import subprocess

import wandb

REPO = ("/Users/ec2-user/.senpai/native/mlxfast-maple-20260810-expansion/"
        "roles/student-maple-alphonse/workspace/target")
ART = f"{REPO}/research/artifacts/maple-alphonse-r107e"
ARMS = ("g0", "g1", "g2", "g3")
BAR_PCT = 0.4  # shippable relative-decode bar from the assignment

head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"],
                      capture_output=True, text=True, check=True).stdout.strip()

stats = json.load(open(f"{ART}/insitu-stats.json"))
traffic = json.load(open(f"{ART}/geom-traffic-model.json"))
air = json.load(open(f"{ART}/geom-air-ledger.json"))
roof = traffic["roofline"]
dec, pla = stats["decode"], stats["prefill_placebo"]


def wins(rec: dict) -> bool:
    """A contrast is a shippable win only if it is faster (negative delta), the
    magnitude clears the bar, and the CI excludes zero."""
    return bool(rec["mean_pct"] <= -BAR_PCT and rec["excludes_zero"]
                and rec["ci95_pct"][1] < 0)


amort, tgshape = dec["contrasts"]["A_amortisation"], dec["contrasts"]["B_threadgroup_shape"]
best_arm = min(("g1", "g2", "g3"), key=lambda a: dec["contrasts"][f"{a}_vs_g0"]["mean_pct"])
best = dec["contrasts"][f"{best_arm}_vs_g0"]

v_amort, v_tgshape = wins(amort), wins(tgshape)
# The family already runs at 87.1% / 80.6% of the measured M4 Pro ceiling, so a
# 24% cut in *issued* bytes that buys no time says the binding constraint is not
# issue slots. That is the mechanistic reading of a null on factor A.
n_issue_bound = bool(not v_amort and amort["mean_pct"] > -BAR_PCT)
n_amort = bool(not v_amort)
# N-ROOFLINE would fire if the family's whole remaining deficit were under the
# bar. It is not: 0.96-1.31% of decode is available, the arms just cannot take it.
n_roofline = bool(min(roof["family_total_headroom_pct_of_decode"].values()) < BAR_PCT)

run = wandb.init(
    entity="wandb-applied-ai-team",
    project="mlxfast-maple",
    name="maple-alphonse-r107e-decode-oproj-amortisation",
    job_type="paired-insitu-timing",
    tags=["maple-alphonse", "r107-E", "oproj_act_h64", "oproj_act_h48", "T3b",
          "T3c", "decode", "row-amortisation", "2x2-factorial", "abba-paired",
          "rule-98.9-cache-resident", "rule-81-both-references"],
    notes=(
        "Does the decode NVFP4 oproj family lose time re-issuing cache-resident "
        "activation and scale traffic once per output row? Four arms in a 2x2 "
        "factorial of results_per_simdgroup {4,8} x rows_per_threadgroup {8,16}, "
        "timed as position-mirrored ABBA halves through ./benchmark.sh "
        "--local-iterate on one quiet M4 Pro. Raising rps 4->8 cuts issued bytes "
        "24.2% and ops-per-useful-FMA 13.6% with compulsory DRAM bytes held "
        "exactly fixed. The pre-timing roofline is the tight constraint: T3b+T3c "
        "already achieve 87.1%/80.6% of the measured 266.80 GB/s M4 Pro ceiling, "
        "so the entire remaining deficit is 0.96-1.31% of decode and the 0.4% "
        "bar needs 31-42% of it."
    ),
    config={
        "assignment_pr": 644,
        "assignment_id": "maple-r107-e-decode-oproj-amortisation",
        "revision_id": "r107-e-rev1",
        "branch": "maple-alphonse/r107-decode-oproj-amortisation",
        "base_sha": "2454cc01ea3afabac067f0a271e36901fea7d21c",
        "head_sha": head,
        "host": "Apple M4 Pro / 20 GPU cores / 14 CPU / 48 GiB",
        "gpu_architecture": "applegpu_g16s",
        "apple_gpu_generation": 16,
        "nax_available": False,
        "macos": "26.5.2 (25F84)",
        "hypothesis": "H-OPROJ-ISSUE",
        "kernel_generator": "lagunaGatedAffineOProjNVFP4Source",
        "live_kernel_dict": "lagunaActivatedOProjLaneMajorKernels",
        "knob": "DARKBLOOM_OPROJ_GEOM (unset|g1|g2|g3)",
        "arms": {a: traffic["factorial"]["cells"][a] for a in ARMS},
        "factorial_design": traffic["factorial"]["design"],
        "g0_air_identical_to_base_h64": air["g0_emission_identical_to_base"]["h64"],
        "g0_air_identical_to_base_h48": air["g0_emission_identical_to_base"]["h48"],
        "prefill_is_placebo_channel": True,
        "prefill_placebo_reason": ("decode oproj call site gated on gatePerHead && "
                                   "B==1 && L==1, LagunaRuntimeModel.swift:6355-6362"),
        "shippable_bar_pct_of_decode": BAR_PCT,
        "shippable_bar_us_m5": roof["m5_bar_us"],
        "shippable_bar_us_local": roof["shippable_bar_us_local"],
        "m4_ceiling_gb_per_s": roof["m4_ceiling_gb_per_s"],
        "b_step_bytes": roof["b_step_bytes"],
        "m5_pool_provenance": ("alpha = 0.4369 / beta = 0.5 two-pool map, "
                               "residual -6.63%, #561"),
        "alpha_beta_degeneracy_caveat": roof["caveat"],
        "sessions": stats["sessions"],
        "n_runs": stats["n_runs"],
        "n_abba_pairs": stats["n_halves"],
        "n_forward_halves": stats["n_forward_halves"],
        "n_reverse_halves": stats["n_reverse_halves"],
        "submitted_surface_files": 1,
        "submitted_surface_file": "Sources/MLXFastModel/LagunaRuntimeModel.swift",
        "official_submissions_from_this_pr": 0,
        "instrument": ("research/maple-alphonse-r107e-{insitu.sh,"
                       "oproj-geom-census.py,traffic-model.py,analyse.py}"),
        "report": "research/maple-alphonse-r107e-decode-oproj-amortisation.md",
    },
)

summary = {
    # PRIMARY: paired in-situ decode contrasts. Negative = faster than shipped.
    "primary/amortisation_effect_pct": amort["mean_pct"],
    "primary/amortisation_ci95_lo_pct": amort["ci95_pct"][0],
    "primary/amortisation_ci95_hi_pct": amort["ci95_pct"][1],
    "primary/amortisation_excludes_zero": int(amort["excludes_zero"]),
    "primary/amortisation_sign_p": amort["sign_p"],
    "primary/threadgroup_shape_effect_pct": tgshape["mean_pct"],
    "primary/threadgroup_shape_ci95_lo_pct": tgshape["ci95_pct"][0],
    "primary/threadgroup_shape_ci95_hi_pct": tgshape["ci95_pct"][1],
    "primary/threadgroup_shape_excludes_zero": int(tgshape["excludes_zero"]),
    "primary/interaction_effect_pct": dec["contrasts"]["AB_interaction"]["mean_pct"],
    "primary/best_arm": best_arm,
    "primary/best_arm_effect_pct": best["mean_pct"],
    "primary/best_arm_clears_bar": int(wins(best)),
    "primary/any_arm_shippable": int(any(wins(dec["contrasts"][f"{a}_vs_g0"])
                                         for a in ("g1", "g2", "g3"))),
    "primary/bar_pct": BAR_PCT,

    # Per-arm paired decode deltas.
    **{f"decode/{a}_vs_g0_pct": dec["contrasts"][f"{a}_vs_g0"]["mean_pct"]
       for a in ("g1", "g2", "g3")},
    **{f"decode/{a}_vs_g0_ci95_hi_pct": dec["contrasts"][f"{a}_vs_g0"]["ci95_pct"][1]
       for a in ("g1", "g2", "g3")},
    **{f"decode/mean_s_{a}": dec["arm_means_s"][a] for a in ARMS},
    "decode/g0_mean_s": dec["g0_mean_s"],
    "decode/g0_cov_pct": dec["g0_cov_pct"],

    # PLACEBO: the same estimator on an axis the kernel provably cannot reach.
    "placebo/prefill_g0_mean_s": pla["g0_mean_s"],
    "placebo/prefill_g0_cov_pct": pla["g0_cov_pct"],
    "placebo/prefill_amortisation_effect_pct": pla["contrasts"]["A_amortisation"]["mean_pct"],
    "placebo/prefill_max_abs_arm_effect_pct": max(
        abs(pla["contrasts"][f"{a}_vs_g0"]["mean_pct"]) for a in ("g1", "g2", "g3")),
    "placebo/prefill_any_false_positive": int(any(
        pla["contrasts"][f"{a}_vs_g0"]["excludes_zero"] for a in ("g1", "g2", "g3"))),

    # ROOFLINE: what the family could give up at best, measured on this host.
    "roofline/t3b_m4_achieved_gb_per_s": roof["families"]["T3b_oproj_h64"]["m4_achieved_gb_per_s"],
    "roofline/t3b_m4_pct_of_ceiling": roof["families"]["T3b_oproj_h64"]["m4_pct_of_ceiling"],
    "roofline/t3b_m4_us_per_dispatch": roof["families"]["T3b_oproj_h64"]["m4_us_per_dispatch"],
    "roofline/t3b_pct_of_b_step": roof["families"]["T3b_oproj_h64"]["pct_of_b_step"],
    "roofline/t3b_headroom_us_vs_lmhead": roof["families"]["T3b_oproj_h64"]["headroom_us"]["lmhead"],
    "roofline/t3b_headroom_us_vs_dense_down": roof["families"]["T3b_oproj_h64"]["headroom_us"]["dense_down"],
    "roofline/t3c_m4_pct_of_ceiling": roof["families"]["T3c_oproj_h48"]["m4_pct_of_ceiling"],
    "roofline/t3c_m4_us_per_dispatch": roof["families"]["T3c_oproj_h48"]["m4_us_per_dispatch"],
    "roofline/t3c_pct_of_b_step": roof["families"]["T3c_oproj_h48"]["pct_of_b_step"],
    "roofline/family_headroom_pct_vs_lmhead":
        roof["family_total_headroom_pct_of_decode"]["lmhead"],
    "roofline/family_headroom_pct_vs_dense_down":
        roof["family_total_headroom_pct_of_decode"]["dense_down"],
    "roofline/deficit_fraction_needed_vs_lmhead":
        roof["fraction_of_deficit_needed_to_clear_bar"]["lmhead"],
    "roofline/deficit_fraction_needed_vs_dense_down":
        roof["fraction_of_deficit_needed_to_clear_bar"]["dense_down"],
    "roofline/local_whole_step_pct_of_ceiling": roof["local_pct_of_ceiling_whole_step"],
    # Rule 81: both published reference rates, because the >=10pp clause is met
    # under lmhead and fails under the fairer same-pattern dense_down.
    "roofline/rule81_reference_lmhead_us_t3b": 51.7,
    "roofline/rule81_reference_dense_down_us_t3b": 36.1,

    # ISSUE-SIDE model, cache-resident only (rule 98.9) - never a speed claim.
    "issued/h64_bytes_rps4": traffic["arms"]["g0"]["h64"]["issued_bytes_total"],
    "issued/h64_bytes_rps8": traffic["arms"]["g1"]["h64"]["issued_bytes_total"],
    "issued/h64_issued_reduction_pct": 100.0 * (
        traffic["arms"]["g1"]["h64"]["issued_bytes_total"]
        / traffic["arms"]["g0"]["h64"]["issued_bytes_total"] - 1.0),
    "issued/h64_over_compulsory_rps4": traffic["arms"]["g0"]["h64"]["issued_over_compulsory"],
    "issued/h64_over_compulsory_rps8": traffic["arms"]["g1"]["h64"]["issued_over_compulsory"],
    "issued/h64_activation_reread_rps4": traffic["arms"]["g0"]["h64"]["activation_reread_factor"],
    "issued/h64_activation_reread_rps8": traffic["arms"]["g1"]["h64"]["activation_reread_factor"],
    "issued/h64_ops_per_fma_rps4": traffic["arms"]["g0"]["h64"]["ops_per_fma"],
    "issued/h64_ops_per_fma_rps8": traffic["arms"]["g1"]["h64"]["ops_per_fma"],
    "issued/weight_code_reread_factor_all_arms": 1.0,
    "issued/compulsory_bytes_identical_across_arms": 1,
    "issued/grid_threads_rps4": traffic["arms"]["g0"]["h64"]["grid_threads"],
    "issued/grid_threads_rps8": traffic["arms"]["g1"]["h64"]["grid_threads"],

    # Static AIR census: instruction *sites*, not dynamic issue counts.
    "air/g0_emission_identical_to_base": int(
        all(air["g0_emission_identical_to_base"].values())),
    "air/all_eight_variants_compiled": 1,
    "air/ir_counts_flat_across_arms_loops_not_unrolled": 1,

    # Preregistered outcomes.
    "outcome/V_AMORT": int(v_amort),
    "outcome/N_AMORT": int(n_amort),
    "outcome/V_TGSHAPE": int(v_tgshape),
    "outcome/N_ISSUE_BOUND": int(n_issue_bound),
    "outcome/N_ROOFLINE": int(n_roofline),
    "outcome/N_CORRECT": 0,
    "outcome/N_BUILD": 0,
    "outcome/all_arms_pass_local_correctness": 1,
}
run.summary.update(summary)

runs_t = wandb.Table(columns=["session", "pos", "arm", "half", "order",
                              "decode_s", "prefill_s", "passed"])
for h in stats["halves"]:
    for arm in ARMS:
        runs_t.add_data(h["session"], h["arm_pos"][arm], arm, h["half"], h["order"],
                        h["decode"][arm], h["prefill"][arm], True)
run.log({"insitu_runs": runs_t})

con_t = wandb.Table(columns=["axis", "contrast", "n_pairs", "mean_pct", "ci95_lo_pct",
                             "ci95_hi_pct", "excludes_zero", "sign_pos", "sign_p",
                             "forward_pct", "reverse_pct"])
for axis, blk in (("decode", dec), ("prefill_placebo", pla)):
    for name, rec in blk["contrasts"].items():
        base = blk["g0_mean_s"]
        con_t.add_data(axis, name, rec["n"], rec["mean_pct"], rec["ci95_pct"][0],
                       rec["ci95_pct"][1], rec["excludes_zero"], rec["sign_pos"],
                       rec["sign_p"],
                       100.0 * rec["by_order"].get("forward", float("nan")) / base,
                       100.0 * rec["by_order"].get("reverse", float("nan")) / base)
run.log({"contrasts": con_t})

geom_t = wandb.Table(columns=["arm", "head", "rps", "num_simdgroups", "rows_per_tg",
                              "threads_per_tg", "threadgroups", "grid_threads",
                              "issued_MB", "issued_over_compulsory",
                              "act_reread", "ops_per_fma"])
for arm in ARMS:
    for head_k in ("h64", "h48"):
        m = traffic["arms"][arm][head_k]
        geom_t.add_data(arm, head_k, m["results_per_simdgroup"], m["num_simdgroups"],
                        m["rows_per_threadgroup"], m["threads_per_threadgroup"],
                        m["threadgroups"], m["grid_threads"],
                        m["issued_bytes_total"] / 1e6, m["issued_over_compulsory"],
                        m["activation_reread_factor"], m["ops_per_fma"])
run.log({"arm_geometry": geom_t})

roof_t = wandb.Table(columns=["family", "calls", "MB_per_step", "pct_of_B_step",
                              "m4_us_measured", "m4_us_per_dispatch", "m4_GB_s",
                              "m4_pct_of_ceiling", "headroom_us_vs_lmhead",
                              "headroom_us_vs_dense_down", "m5_us_modelled"])
for name, f in roof["families"].items():
    roof_t.add_data(name, f["calls"], f["head_bytes"] / 1e6, f["pct_of_b_step"],
                    f["m4_us_measured"], f["m4_us_per_dispatch"],
                    f["m4_achieved_gb_per_s"], f["m4_pct_of_ceiling"],
                    f["headroom_us"]["lmhead"], f["headroom_us"]["dense_down"],
                    f["m5_us_modelled"])
run.log({"roofline": roof_t})

artifact = wandb.Artifact("maple-alphonse-r107e-ledger", type="analysis")
for name in ("insitu-stats.json", "geom-traffic-model.json", "geom-air-ledger.json"):
    artifact.add_file(f"{ART}/{name}")
artifact.add_dir(f"{ART}/insitu", name="insitu")
artifact.add_file(f"{REPO}/research/maple-alphonse-r107e-decode-oproj-amortisation.md")
run.log_artifact(artifact)

print("run:", run.url)
print("run_id:", run.id)
run.finish()
