#!/usr/bin/env python3
"""Publish the R107-C expert gather-GEMM floor ledger to W&B.

No millisecond is claimed for this host: `fp_gather_qmm_rhs_expert_nax` is
unreachable at runtime on Apple GPU generation 16 (`is_nax_available()` needs
gen >= 17), so the published evidence is the rule-82 static geometry /
occupancy / byte ledger plus the archive closures.
"""

import json
import os
import statistics as st
import subprocess
from collections import defaultdict

import wandb

REPO = ("/Users/ec2-user/.senpai/native/mlxfast-maple-20260810-expansion/"
        "roles/student-maple-alphonse/workspace/target")
ART = f"{REPO}/research/artifacts/maple-alphonse-r107c"

PREFILL_PCT_PER_MS = 0.3781  # % of score per ms of prefill (assignment)
SIGMA_DELTA_MS = 0.4497
FAMILY_MS_M5 = 43.2619
FAMILY_ROOFLINE_MS = 35.6
RESIDUAL_MS = FAMILY_MS_M5 - FAMILY_ROOFLINE_MS
RELEVANCE_GATE_PCT = 0.4
DOWN_SHARE_OF_FAMILY_WEIGHTS = 0.5625 / 1.6875  # down / (gate_up + down)

head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"],
                      capture_output=True, text=True, check=True).stdout.strip()

ledger = json.load(open(f"{ART}/byte-ledger.json"))
air_raw = json.load(open(f"{ART}/air-census.json"))
air = {"64": dict(air_raw["down-bn64"]), "32": dict(air_raw["down-bn32"])}
for key, stem in (("64", "down-bn64"), ("32", "down-bn32")):
    air[key]["air_bytes"] = os.path.getsize(f"{ART}/{stem}.air")

lines = open(f"{ART}/occupancy-census.csv").read().splitlines()
hdr = next(i for i, l in enumerate(lines) if l.startswith("threads_per_tg"))
census = defaultdict(list)
for line in lines[hdr + 1:]:
    p = line.split(",")
    if len(p) == 5 and p[0].isdigit():
        census[int(p[1])].append(int(p[3]))

occ_mean = {b: st.mean(v) for b, v in census.items()}
occ_sd = {b: st.stdev(v) for b, v in census.items()}
occ_max = {b: max(v) for b, v in census.items()}
TG64, TG32 = 9232, 4624
occ_ratio_mean = occ_mean[TG32] / occ_mean[TG64]
occ_ratio_max = occ_max[TG32] / occ_max[TG64]

# Two bounds, both anchored on the family's above-roofline residual.
# Ceiling: any down-only change can at most delete the down share of that
# residual. Mechanism estimate: stall time scales inversely with the measured
# resident-concurrency gain.
residual_down_ms = RESIDUAL_MS * DOWN_SHARE_OF_FAMILY_WEIGHTS
harvest_ms_ceiling = residual_down_ms
harvest_pct_ceiling = harvest_ms_ceiling * PREFILL_PCT_PER_MS
harvest_ms_best = residual_down_ms * (1.0 - 1.0 / occ_ratio_mean)
harvest_pct_best = harvest_ms_best * PREFILL_PCT_PER_MS

run = wandb.init(
    entity="wandb-applied-ai-team",
    project="mlxfast-maple",
    name="maple-alphonse-r107c-expert-gather-gemm-floor",
    job_type="static-geometry-ledger",
    tags=["maple-alphonse", "r107-C", "routed_gather_gemm",
          "fp_gather_qmm_rhs_expert_nax", "prefill", "rule-82-ledger",
          "N-REACH", "N-FLOOR", "N-XMAJOR-CLOSED", "unmeasurable-on-host"],
    notes=(
        "How much prefill is left in routed_gather_gemm? Three of the four "
        "named axes were already closed in the archive (rule 83). The only "
        "live axis, bn 64->32, is admissible on the down projection only "
        "(K=512,N=2048) because the fused SwiGLU epilogue locks BN=64 for "
        "gate/up. The NAX family is unreachable at runtime on this gen-16 "
        "host, so the published evidence is a static AIR census, two measured "
        "staticThreadgroupMemoryLength values, and a measured "
        "resident-threadgroup occupancy census. Verdict: N-FLOOR with a "
        "closing ledger -- best-case harvest ~0.49% of score, above the 0.4% "
        "relevance gate but below the 1.35 ms 3-sigma bar."
    ),
    config={
        "assignment_pr": 636,
        "assignment_id": "maple-r107-c-expert-gather-gemm-floor",
        "revision_id": "r107-c-rev1",
        "branch": "maple-alphonse/r107-expert-gather-gemm-floor",
        "base_sha": "e1d206da6bedd2a3ce3957ae05437a78317e4620",
        "head_sha": head,
        "host": "Apple M4 Pro / 20 GPU cores / 14 CPU / 48 GiB",
        "gpu_architecture": "applegpu_g16s",
        "apple_gpu_generation": 16,
        "macos": "26.5.2 (25F84)",
        "metal_toolchain": "Apple metal version 32023.883",
        "nax_runtime_reachable": False,
        "nax_gate": "is_nax_available(): macOS>=26.2 && gen >= (arch ends 'p' ? 18 : 17)",
        "nax_kernel_compiles_on_host": True,
        "kernel": "fp_gather_qmm_rhs_expert_nax",
        "host_dispatch_file": ("Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/"
                               "metal/quantized.cpp"),
        "knob": "DARKBLOOM_EXPERT_DOWN_BN (default 64, accepts 32|64)",
        "one_axis": "down-projection N-tile bn: 64 (shipped) vs 32 (candidate)",
        "gate_up_bn_is_correctness_lock": True,
        "submitted_surface_files": 1,
        "submitted_surface_diff_bytes": 1740,
        "submitted_surface_growth_bytes": 998,
        "submitted_surface_cap_bytes": 8192,
        "default_path_is_byte_identical_to_base": True,
        "surface_digest_base": "cf6d3847d583730fc7366110d91f54c676405869634cd0ae4eebbd362363c612",
        "surface_digest_candidate": "e5dac8a08c2a04c565fb575d86e710721d548413e826fa113f9b99dc23f33258",
        "offline_compile_surface_digest": "803fe16405b346e41b80f5202c4d5135c137f95c94051e69b37c5679ae3c2eba",
        "prefill_pct_of_score_per_ms": PREFILL_PCT_PER_MS,
        "family_m5_ms": FAMILY_MS_M5,
        "family_roofline_ms": FAMILY_ROOFLINE_MS,
        "family_dispatches": 76,
        "sigma_delta_ms": SIGMA_DELTA_MS,
        "three_sigma_bar_ms": 3 * SIGMA_DELTA_MS,
        "relevance_gate_pct_of_score": RELEVANCE_GATE_PCT,
        "layers_moe": 39,
        "experts": 256,
        "top_k": 8,
        "prefill_tokens": 512,
        "mean_rows_per_expert": 16,
        "tile_BM_BK_WM_WN": "64/64/4/1",
        "instrument": ("research/maple-alphonse-r107c-{jit-air.sh,air-census.py,"
                       "pipeline-probe.swift,occupancy-census.swift,byte-ledger.py}"),
        "report": "research/maple-alphonse-r107c-expert-gather-gemm-floor.md",
    },
)

L64, L32 = ledger["64"], ledger["32"]
summary = {
    # PRIMARY: the rule-82 occupancy lever, measured on this host.
    "primary/resident_tgs_ratio_bn32_over_bn64_mean": occ_ratio_mean,
    "primary/resident_tgs_ratio_bn32_over_bn64_max": occ_ratio_max,
    "primary/tg_bytes_bn64": TG64,
    "primary/tg_bytes_bn32": TG32,
    "primary/tg_bytes_ratio": TG32 / TG64,
    "primary/harvest_ms_best_case": harvest_ms_best,
    "primary/harvest_pct_of_score_best_case": harvest_pct_best,
    "primary/harvest_ms_down_only_ceiling": harvest_ms_ceiling,
    "primary/harvest_pct_of_score_down_only_ceiling": harvest_pct_ceiling,
    "primary/clears_relevance_gate": int(harvest_pct_best >= RELEVANCE_GATE_PCT),
    "primary/clears_three_sigma_bar": int(harvest_ms_best >= 3 * SIGMA_DELTA_MS),
    "primary/ceiling_clears_three_sigma_bar": int(
        harvest_ms_ceiling >= 3 * SIGMA_DELTA_MS),
    "primary/family_fraction_of_roofline": FAMILY_ROOFLINE_MS / FAMILY_MS_M5,
    "primary/family_above_roofline_residual_ms": RESIDUAL_MS,

    # Occupancy census, the two points of interest.
    "occupancy/resident_tgs_bn64_mean": occ_mean[TG64],
    "occupancy/resident_tgs_bn64_sd": occ_sd[TG64],
    "occupancy/resident_tgs_bn64_max": occ_max[TG64],
    "occupancy/resident_tgs_bn32_mean": occ_mean[TG32],
    "occupancy/resident_tgs_bn32_sd": occ_sd[TG32],
    "occupancy/resident_tgs_bn32_max": occ_max[TG32],
    "occupancy/resident_simdgroups_per_core_bn64": L64["resident_simdgroups_per_core"],
    "occupancy/resident_simdgroups_per_core_bn32": L32["resident_simdgroups_per_core"],
    "occupancy/hard_tg_cap_per_core_observed": 227 / 20,
    "occupancy/naive_32kib_per_core_model_refuted": 1,
    "occupancy/register_api_uninformative_on_this_device": 1,

    # AIR census: what changes and, importantly, what does not.
    "air/bytes_bn64": air["64"]["air_bytes"],
    "air/bytes_bn32": air["32"]["air_bytes"],
    "air/bytes_ratio": air["32"]["air_bytes"] / air["64"]["air_bytes"],
    "air/barriers_invariant": int(air["64"]["barr"] == air["32"]["barr"]),
    "air/mma_run_sites_invariant": int(air["64"]["mma_run"] == air["32"]["mma_run"]),
    "air/phi_bn64": air["64"]["phi"], "air/phi_bn32": air["32"]["phi"],
    "air/br_bn64": air["64"]["br"], "air/br_bn32": air["32"]["br"],
    "air/phi_br_gate_passed": int(air["32"]["phi"] <= air["64"]["phi"]
                                  and air["32"]["br"] <= air["64"]["br"]),
    "air/build_ok_both_variants": 1,

    # Byte ledger: the invariants and the one real cost.
    "bytes/weight_bytes_per_layer_invariant": int(
        L64["weight_bytes_per_layer"] == L32["weight_bytes_per_layer"]),
    "bytes/weight_bytes_family_gb": L64["weight_bytes_family_gb"],
    "bytes/a_reread_multiplicity_bn64": L64["a_reread_multiplicity"],
    "bytes/a_reread_multiplicity_bn32": L32["a_reread_multiplicity"],
    "bytes/a_requests_family_gb_bn64": L64["a_bytes_family_gb"],
    "bytes/a_requests_family_gb_bn32": L32["a_bytes_family_gb"],
    "bytes/a_unique_bytes_per_layer": L64["a_unique_bytes_per_layer"],
    "bytes/weight_bytes_in_flight_per_core_bn64": L64["weight_bytes_in_flight_per_core"],
    "bytes/weight_bytes_in_flight_per_core_bn32": L32["weight_bytes_in_flight_per_core"],
    "bytes/tgs_per_layer_bn64": L64["tgs_per_layer"],
    "bytes/tgs_per_layer_bn32": L32["tgs_per_layer"],

    # The larger prize found on the way (not in scope, not implemented).
    "finding/mma_active_simdgroups_per_tg": L64["mma_active_simdgroups_per_tg"],
    "finding/simdgroups_per_tg": L64["simdgroups_per_tg"],
    "finding/mma_occupancy_deficit_factor": (
        L64["simdgroups_per_tg"] / L64["mma_active_simdgroups_per_tg"]),

    # Preregistered outcomes.
    "outcome/N_REACH": 1,
    "outcome/N_XMAJOR_CLOSED": 1,
    "outcome/N_FLOOR": 1,
    "outcome/N_BUILD": 0,
    "outcome/N_CORRECT": 0,
    "outcome/V_TILE": 0,
    "outcome/V_XMAJOR": 0,
    "outcome/V_EGROUPS": 0,
    "outcome/stage0_axes_closed_by_archive": 3,
}
run.summary.update(summary)

occ_table = wandb.Table(columns=["tg_bytes", "n", "mean", "sd", "min", "max",
                                 "corresponds_to_bn"])
for b in sorted(census):
    v = census[b]
    tag = {TG64: "64", TG32: "32"}.get(b, "")
    occ_table.add_data(b, len(v), st.mean(v), st.stdev(v), min(v), max(v), tag)
run.log({"occupancy_census": occ_table})


def contrast_table(d64, d32, skip=()):
    t = wandb.Table(columns=["quantity", "bn64", "bn32", "ratio"])
    for k in d64:
        if k in skip:
            continue
        a, b = d64[k], d32[k]
        numeric = isinstance(a, (int, float)) and isinstance(b, (int, float))
        t.add_data(k, str(a), str(b), (b / a) if numeric and a else None)
    return t


run.log({"air_census": contrast_table(air["64"], air["32"])})
run.log({"byte_ledger": contrast_table(L64, L32, skip=("bn",))})

stage0 = wandb.Table(columns=["axis", "status", "citation"])
stage0.add_data("darkbloom_stage_bm128_variant 4 vs 5", "CLOSED (official-M5 absolutes)",
                "artifacts/advisor-r103/receipt-corpus-frozen.json:6142,:6772; PREFILL_NAX_ANALYSIS.md:170")
stage0.add_data("darkbloom_gather_xmajor_ct", "CLOSED-NEGATIVE",
                "RESEARCH_ARCHIVE_through-round-91.md:1220-1226; nezuko-harvest-report.md:67,75-77")
stage0.add_data("DARKBLOOM_EXPERT_GATHER_GROUPS 64/128/256", "CLOSED-POSITIVE at 256 (shipped)",
                "rung1-comment-strip.patch:7381-7394; PREFILL_NAX_ANALYSIS.md:56-60")
stage0.add_data("bn 64->32", "NEVER MEASURED; admissible down-only",
                "RESEARCH_ARCHIVE_through-round-91.md:6560-6565,:6589; kernels/fp_quantized_nax.h:1781-1782")
run.log({"stage0_archive_closures": stage0})

artifact = wandb.Artifact("maple-alphonse-r107c-ledger", type="analysis")
for name in ["air-census.json", "byte-ledger.json", "occupancy-census.csv",
             "twin-diff.txt", "down-bn64.metal", "down-bn32.metal"]:
    artifact.add_file(f"{ART}/{name}")
artifact.add_file(f"{REPO}/research/maple-alphonse-r107c-expert-gather-gemm-floor.md")
run.log_artifact(artifact)

print("run:", run.url)
run.finish()
