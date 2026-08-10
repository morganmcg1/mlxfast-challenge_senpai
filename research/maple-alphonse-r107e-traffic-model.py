#!/usr/bin/env python3
"""R107-E: issued-traffic and op-count model for the decode oproj arms.

Reads the emitted per-arm Metal sources written by
research/maple-alphonse-r107e-oproj-geom-census.py, recovers each arm's
compile-time constants, and derives the per-dispatch *issued* load traffic and
per-thread op mix.

Every number here is an issue-side count. Compulsory DRAM bytes are unchanged
across arms by construction (each weight code is still read exactly once), so
the issued-byte deltas below are cache-resident traffic and must never be
headlined as a speedup (Rule 98.9). They exist only to say how large the
amortisation lever *could* be if issue slots or L1 bandwidth were the binding
constraint.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ART = pathlib.Path(__file__).resolve().parent / "artifacts" / "maple-alphonse-r107e"

CONSTS = (
    "in_vec_size",
    "out_vec_size",
    "gate_heads",
    "group_size",
    "values_per_thread",
    "block_size",
    "results_per_simdgroup",
    "num_simdgroups",
)


def read_constants(src: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for name in CONSTS:
        m = re.search(rf"constexpr uint {name} = ([^;]+);", src)
        if not m:
            raise SystemExit(f"missing constexpr {name}")
        expr = m.group(1).strip()
        out[name] = int(eval(expr, {}, dict(out)))  # noqa: S307 - literals only
    out["codes_per_thread"] = out["values_per_thread"] // 8
    return out


def check_structure(src: str, c: dict[str, int]) -> dict[str, bool]:
    """Confirm the load sites the model assumes, so the model cannot silently
    describe a kernel shape that is no longer emitted."""
    return {
        # scale_bases is based on out_row only and is never advanced in the k
        # loop, so bs[row] is loop-invariant and is not per-k-iteration traffic.
        "scale_base_loop_invariant": "const device uint8_t* bs = scale_bases + out_row;" in src
        and not re.search(r"\n\s*bs \+=", src),
        # one gate element per k iteration, before the row loop
        "gate_load_amortised": bool(
            re.search(r"float g=float\(gate_values\[column>>head_shift\]\);", src)
        ),
        # values_per_thread activation elements per k iteration, before the row loop
        "activation_load_amortised": bool(
            re.search(r"for\(uint i=0;i<values_per_thread;\+\+i\)\s*\n\s*x_thread\[i\]", src)
        ),
        # one scale nibble/byte per row per k iteration
        "scale_nibble_per_row": "const uint8_t raw = sp[0];" in src,
        # codes_per_thread weight words per row per k iteration
        "codes_per_row": "const uint c = wl[j];" in src,
        "result_array_sized_by_rps": f"thread float result[results_per_simdgroup]" in src,
    }


def model(c: dict[str, int]) -> dict[str, object]:
    rps = c["results_per_simdgroup"]
    ns = c["num_simdgroups"]
    k_blocks = c["in_vec_size"] // c["block_size"]
    simdgroups = c["out_vec_size"] // rps
    threads = simdgroups * 32
    threadgroups = simdgroups // ns

    # bytes issued per thread per k iteration
    act_bytes_per_k = 2 * c["values_per_thread"] + 2  # bfloat activations + one bfloat gate
    row_bytes_per_k = rps * (4 * c["codes_per_thread"] + 1)  # weight words + one scale byte
    per_thread = k_blocks * (act_bytes_per_k + row_bytes_per_k)

    issued_act = threads * k_blocks * act_bytes_per_k
    issued_code = threads * k_blocks * rps * 4 * c["codes_per_thread"]
    issued_nib = threads * k_blocks * rps
    issued_base = threads * rps  # loop-invariant, one load per row per thread
    issued_total = issued_act + issued_code + issued_nib + issued_base

    # compulsory distinct bytes actually resident behind this dispatch
    compulsory_codes = c["out_vec_size"] * c["in_vec_size"] // 2
    compulsory_nib = c["out_vec_size"] * (c["in_vec_size"] // c["group_size"]) // 4
    compulsory_base = c["out_vec_size"]
    compulsory_act = 2 * c["in_vec_size"]
    compulsory = compulsory_codes + compulsory_nib + compulsory_base + compulsory_act

    # per-thread op mix per k iteration
    fma_per_k = rps * c["codes_per_thread"] * 8
    # gate convert + values_per_thread multiplies + values_per_thread bfloat rounds
    act_ops_per_k = 1 + 2 * c["values_per_thread"]
    # per row: escape compare, select, nibble add, shift, half bitcast, scale fmul
    row_overhead_per_k = rps * 6

    return {
        "results_per_simdgroup": rps,
        "num_simdgroups": ns,
        "rows_per_threadgroup": ns * rps,
        "threads_per_threadgroup": ns * 32,
        "threadgroups": threadgroups,
        "grid_threads": threads,
        "k_blocks": k_blocks,
        "issued_bytes_per_thread": per_thread,
        "issued_activation_bytes": issued_act,
        "issued_weight_code_bytes": issued_code,
        "issued_scale_nibble_bytes": issued_nib,
        "issued_scale_base_bytes": issued_base,
        "issued_bytes_total": issued_total,
        "compulsory_bytes_total": compulsory,
        "issued_over_compulsory": round(issued_total / compulsory, 4),
        "activation_reread_factor": round(issued_act / compulsory_act, 2),
        "weight_code_reread_factor": round(issued_code / compulsory_codes, 4),
        "fma_per_thread_per_k": fma_per_k,
        "non_fma_ops_per_thread_per_k": act_ops_per_k + row_overhead_per_k,
        "ops_per_fma": round((fma_per_k + act_ops_per_k + row_overhead_per_k) / fma_per_k, 4),
        # load *instructions*, not bytes; reproduces the AIR dynamic census
        # (g0: 16 act + 1 gate + 8 codes + 4 nibbles + 4 bases = 33)
        "load_instructions_per_thread_per_k": (
            c["values_per_thread"] + 1 + rps * c["codes_per_thread"] + 2 * rps
        ),
    }


# Published bytes-regime rates for the two oproj families. m4_us and head_bytes
# are measured/HEAD-epoch columns of research/artifacts/fern-r101/m5-pool-table.csv;
# m5_us is the alpha=0.4369 / beta=0.5 two-pool projection of the same row.
POOL_ROWS = {
    "T3b_oproj_h64": {"calls": 30, "head_bytes": 259584000, "m4_us": 1117.7, "m5_us": 488.376},
    "T3c_oproj_h48": {"calls": 10, "head_bytes": 64901120, "m4_us": 301.8, "m5_us": 131.871},
}
# fern-r101 corollary 3: retire 273/266.3/260.6/237.4; measured M4 Pro ceiling.
M4_CEILING_GBS = 266.80
# Same-host reference efficiencies both published under rule 81, because the
# >=10 pp clause is met under one and fails under the other.
REFERENCE_PCT = {"lmhead": 97.4, "dense_down": 94.0}
# fern-r106g/family_breakdown.json B_step, and the local/M5 step budgets.
B_STEP_BYTES = 1671402432
M5_BASELINE_STEP_US = 6500.0
SHIPPABLE_BAR_PCT = 0.4
# Rule 105.10 (#644 comment 5241791262): once L3 is de-biased to 0.1966 % of cs,
# a second different-family bit-exact summand only has to supply the residual.
SUMMAND_BAR_PCT = 0.2034

# Measured M4 Pro per-dispatch times for the two oproj head counts (pool table
# §B.0.3, M4 column, divided by the call count). These are the only two dose
# points the family offers.
DOSE = {
    "T3b_oproj_h64": {"bytes": 8652800, "us": 1117.7 / 30, "k_blocks": 16, "calls": 30},
    "T3c_oproj_h48": {"bytes": 6490112, "us": 301.8 / 10, "k_blocks": 12, "calls": 10},
}
M4_CEILING_GB_S = 266.80

# Rule 100 (#642, maple-tanjiro, R107-D) measured an instruction-issue exchange
# rate on this host's decode fused-attention kernels: 0.008255 us per
# fma-per-thread at 32,768 resident threads, i.e. 3.969e12 issued fma/s, which
# is 97.7 % of the 2560 FP32 lanes x 1.578 GHz theoretical ceiling. That rate is
# the only *measured* instruction<->time conversion the campaign owns, so it is
# what H-OPROJ-ISSUE must be priced against.
RULE100_ISSUE_PER_S = 3.969e12
RULE100_THEORETICAL_PER_S = 2560 * 1.578e9
# alpha of the two-pool map: per-dispatch M5/M4 ratio for both oproj rows.
M5_OVER_M4 = 0.4369
DECODE_PRICE_PCT_PER_US = 0.015228
# Rule 105 (#644 comment 5241615076): the price was fitted on an official M5
# decode, so `SHIPPABLE_BAR_PCT` is a bar on M5 us/step. A delta measured on
# this M4 Pro converts as `pct_cs = us_m4 * k * DECODE_PRICE_PCT_PER_US` with
# k = alpha in the bytes regime. Comparing a raw M4 us figure, or a % of the M4
# decode step, against the 0.4 % bar is a unit error.
K_BYTES = {"alpha_0.4369": M5_OVER_M4, "alpha_0.389": 0.389}


def bar_us_m4(pct_of_cs: float) -> dict[str, float]:
    return {name: round(pct_of_cs / (k * DECODE_PRICE_PCT_PER_US), 1)
            for name, k in K_BYTES.items()}


def weighted_mean(values: list[float], weights: list[float]) -> float:
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)


def issue_ceiling(arms: dict[str, dict[str, dict]]) -> dict[str, object]:
    """Price the amortisation lever against rule 100's measured issue rate.

    Upper bound, deliberately generous to the hypothesis: every issue slot the
    arm removes -- load, integer, convert, fma -- is credited at the full FP32
    fma issue cost, and the halving of grid threads is assumed free. If the
    lever cannot clear the bar under those assumptions it cannot clear it at
    all.
    """
    fam = {"h64": "T3b_oproj_h64", "h48": "T3c_oproj_h48"}
    out: dict[str, object] = {}
    for head, key in fam.items():
        us_per_dispatch = DOSE[key]["us"]
        calls = DOSE[key]["calls"]
        slots: dict[str, int] = {}
        for arm, per_head in arms.items():
            m = per_head[head]
            per_thread_per_k = (
                m["fma_per_thread_per_k"]
                + m["non_fma_ops_per_thread_per_k"]
                + m["load_instructions_per_thread_per_k"]
            )
            slots[arm] = m["grid_threads"] * m["k_blocks"] * per_thread_per_k
        base = slots["g0"]
        achieved = base / (us_per_dispatch * 1e-6)
        rows = {}
        for arm in sorted(slots):
            removed = base - slots[arm]
            us_saved = removed / RULE100_ISSUE_PER_S * 1e6
            m5_us_step = us_saved * calls * M5_OVER_M4
            rows[arm] = {
                "issue_slots_per_dispatch": slots[arm],
                "slots_removed_vs_g0": removed,
                "slots_removed_pct": round(100.0 * removed / base, 3),
                "ceiling_us_per_dispatch": round(us_saved, 4),
                "ceiling_pct_of_dispatch": round(100.0 * us_saved / us_per_dispatch, 3),
                "ceiling_m4_us_per_step": round(us_saved * calls, 3),
                "ceiling_m5_us_per_step": round(m5_us_step, 3),
                "ceiling_pct_of_cs": round(m5_us_step * DECODE_PRICE_PCT_PER_US, 4),
            }
        out[key] = {
            "measured_us_per_dispatch": round(us_per_dispatch, 4),
            "issue_slots_per_dispatch_g0": base,
            "achieved_issue_per_s": achieved,
            "pct_of_measured_issue_peak": round(100.0 * achieved / RULE100_ISSUE_PER_S, 2),
            "pct_of_theoretical_issue_peak": round(
                100.0 * achieved / RULE100_THEORETICAL_PER_S, 2
            ),
            "arms": rows,
        }
    combined = {
        arm: round(
            sum(out[k]["arms"][arm]["ceiling_pct_of_cs"] for k in fam.values()), 4
        )
        for arm in sorted(arms)
    }
    best = max(combined, key=lambda a: combined[a])
    util = weighted_mean(
        [out[k]["pct_of_measured_issue_peak"] for k in fam.values()],
        [DOSE[k]["calls"] * DOSE[k]["us"] for k in fam.values()],
    )
    return {
        "note": "generous upper bound: every removed slot credited at the full "
                "fma issue cost, occupancy loss assumed free",
        "rule100_issue_per_s": RULE100_ISSUE_PER_S,
        "rule100_source": "#642 R107-D, 0.008255 us per fma-per-thread at 32768 threads",
        "families": out,
        "combined_ceiling_pct_of_cs": combined,
        "best_arm": best,
        "best_arm_combined_ceiling_pct_of_cs": combined[best],
        "bar_pct_of_cs": SHIPPABLE_BAR_PCT,
        "summand_bar_pct_of_cs": SUMMAND_BAR_PCT,
        "ceiling_clears_bar": combined[best] >= SHIPPABLE_BAR_PCT,
        "ceiling_clears_summand_bar": combined[best] >= SUMMAND_BAR_PCT,
        "time_weighted_issue_utilisation_pct": round(util, 2),
        # if only `util` of the dispatch is issue-limited, the ceiling scales down
        "utilisation_scaled_ceiling_pct_of_cs": round(combined[best] * util / 100.0, 4),
        "utilisation_scaled_clears_summand_bar":
            combined[best] * util / 100.0 >= SUMMAND_BAR_PCT,
        # rule 105: the same ceiling stated in the units this host measures in.
        "combined_ceiling_us_per_step_m4": bar_us_m4(combined[best]),
        "utilisation_scaled_ceiling_us_per_step_m4":
            bar_us_m4(combined[best] * util / 100.0),
        "solo_bar_us_per_step_m4": bar_us_m4(SHIPPABLE_BAR_PCT),
        "summand_bar_us_per_step_m4": bar_us_m4(SUMMAND_BAR_PCT),
        "slot_cost_multiplier_needed_at_measured_utilisation": round(
            SHIPPABLE_BAR_PCT / (combined[best] * util / 100.0), 3
        ),
        "slot_cost_multiplier_needed_for_summand_at_measured_utilisation": round(
            SUMMAND_BAR_PCT / (combined[best] * util / 100.0), 3
        ),
        "verdict": (
            "the lever's generous issue-slot ceiling is "
            f"{combined[best]:.3f} % of cs at 100 % issue-boundedness, but the family "
            f"issues at only {util:.1f} % of the measured issue peak while running at "
            "87.0/80.6 % of its bandwidth roofline, so the utilisation-scaled ceiling is "
            f"{combined[best] * util / 100.0:.3f} % of cs"
        ),
    }


def regime_fit() -> dict[str, object]:
    """Fit T = B/BW + L on the family's two dose points, and test whether the
    residual L behaves like a per-dispatch fixed cost or a per-k_block issue
    cost. The latter is what H-OPROJ-ISSUE requires."""
    a, b = DOSE["T3b_oproj_h64"], DOSE["T3c_oproj_h48"]
    d_bytes = a["bytes"] - b["bytes"]
    d_us = a["us"] - b["us"]

    # Two points, two parameters -> exact fit, zero residual degrees of freedom,
    # so no uncertainty is estimable from the fit itself.
    bw_free = d_bytes / (d_us * 1e-6) / 1e9
    l_free = a["us"] - a["bytes"] / (bw_free * 1e9) * 1e6

    # Collinearity diagnostic: are bytes and block count separable at all?
    bytes_per_block = {k: v["bytes"] / v["k_blocks"] for k, v in DOSE.items()}
    collinear_spread = (
        max(bytes_per_block.values()) / min(bytes_per_block.values()) - 1.0
    )

    # Physical alternative: pin BW at the measured ceiling and read off L.
    pinned = {}
    for k, v in DOSE.items():
        bw_us = v["bytes"] / (M4_CEILING_GB_S * 1e9) * 1e6
        resid = v["us"] - bw_us
        pinned[k] = {
            "bytes_time_us": round(bw_us, 3),
            "measured_us": round(v["us"], 3),
            "residual_L_us": round(resid, 3),
            "residual_per_k_block_us": round(resid / v["k_blocks"], 4),
        }
    l_vals = [pinned[k]["residual_L_us"] for k in DOSE]
    lb_vals = [pinned[k]["residual_per_k_block_us"] for k in DOSE]
    spread_fixed = max(l_vals) / min(l_vals) - 1.0
    spread_per_block = max(lb_vals) / min(lb_vals) - 1.0

    # H-OPROJ-ISSUE predicts L grows with k_blocks (more per-row re-issues).
    k_ratio = a["k_blocks"] / b["k_blocks"]
    l_ratio = pinned["T3b_oproj_h64"]["residual_L_us"] / pinned["T3c_oproj_h48"][
        "residual_L_us"
    ]

    total_L_us = sum(pinned[k]["residual_L_us"] * DOSE[k]["calls"] for k in DOSE)
    return {
        "free_two_point_fit": {
            "bw_gb_per_s": round(bw_free, 2),
            "L_us_per_dispatch": round(l_free, 3),
            "exceeds_measured_ceiling_by_pct": round(
                100 * (bw_free / M4_CEILING_GB_S - 1.0), 2
            ),
            "degrees_of_freedom": 0,
            "note": (
                "Exact fit: 2 points, 2 parameters. No uncertainty is estimable. "
                "The implied bandwidth exceeds the measured host ceiling, so a "
                "single fixed-L model cannot reproduce both points physically."
            ),
        },
        "collinearity": {
            "bytes_per_k_block": {k: round(v, 1) for k, v in bytes_per_block.items()},
            "spread": round(collinear_spread, 6),
            "verdict": (
                "DEGENERATE: bytes and k_blocks are collinear to "
                f"{100 * collinear_spread:.3f} % across the only two dose points, "
                "so this family cannot separate a bytes cost from a per-block "
                "issue cost by dose curve. The geometry arms are the only "
                "available instrument, because they hold compulsory bytes exactly "
                "fixed while changing per-row issue count."
            ),
        },
        "bw_pinned_at_measured_ceiling": pinned,
        "residual_scaling_test": {
            "k_blocks_ratio_h64_over_h48": round(k_ratio, 4),
            "residual_L_ratio_h64_over_h48": round(l_ratio, 4),
            "fixed_per_dispatch_spread": round(spread_fixed, 4),
            "per_k_block_spread": round(spread_per_block, 4),
            "better_described_as": (
                "fixed_per_dispatch" if spread_fixed < spread_per_block
                else "per_k_block"
            ),
            "h_oproj_issue_prediction": (
                "L should scale with k_blocks, i.e. ratio ~= "
                f"{k_ratio:.3f}"
            ),
            "observed_sign": (
                "OPPOSITE" if (l_ratio - 1.0) * (k_ratio - 1.0) < 0 else "consistent"
            ),
        },
        "family_total_residual_us_per_step": round(total_L_us, 1),
        "family_total_residual_pct_of_m5_step": round(
            100 * total_L_us / M5_BASELINE_STEP_US, 3
        ),
        "caveat": (
            "Borrows the M4 family microsecond labels from the §B.0.3 pool table "
            "and the 266.80 GB/s ceiling from fern-r101 corollary 3. Two dose "
            "points only."
        ),
    }


def t2d_comparison_column() -> dict[str, object]:
    """Comparison column, not an arm -- the T2d kernel is UNTOUCHED by R107-E.

    Verifies the advisor's arithmetic against the constants actually emitted by
    lagunaRoutedSharedDownResidualSource, so frieren (#597 R107-F) gets a second
    independent instrument reading on her own target.
    """
    input_width = 512
    output_width = 2048
    slots = 8 + 1  # routed_experts + shared_slot
    outputs_per_simd = 4
    values_per_lane = 16
    packed_row_bytes = 256
    routed_scale_row_bytes = 16
    calls = 39

    threadgroups = output_width // outputs_per_simd  # 1 simdgroup per TG
    weight_per_tg = slots * outputs_per_simd * packed_row_bytes
    scale_per_tg = slots * outputs_per_simd * routed_scale_row_bytes
    bytes_per_call = (weight_per_tg + scale_per_tg) * threadgroups

    unique_activation_bytes = slots * input_width * 2
    issued_activation_bytes = threadgroups * slots * input_width * 2

    lane_activation = values_per_lane * 2
    lane_weight = outputs_per_simd * (packed_row_bytes // (input_width // values_per_lane))
    lane_scale = 4
    lane_total = lane_activation + lane_weight + lane_scale

    return {
        "status": "comparison column, not an arm - kernel untouched by R107-E",
        "source_constants_verified": {
            "input_width": input_width,
            "output_width": output_width,
            "slots": slots,
            "outputs_per_simd": outputs_per_simd,
            "values_per_lane": values_per_lane,
            "packed_row_bytes": packed_row_bytes,
            "routed_scale_row_bytes": routed_scale_row_bytes,
        },
        "byte_identity": {
            "weight_bytes_per_tg": weight_per_tg,
            "scale_bytes_per_tg": scale_per_tg,
            "threadgroups": threadgroups,
            "bytes_per_call": bytes_per_call,
            "advisor_stated": 5013504,
            "agrees": bytes_per_call == 5013504,
            "bytes_per_step": bytes_per_call * calls,
            "pct_of_b_step": round(100 * bytes_per_call * calls / B_STEP_BYTES, 4),
        },
        "loads_per_unique_weight_byte": 1.0,
        "activation_reread_factor": threadgroups,
        "unique_activation_bytes_per_call": unique_activation_bytes,
        "issued_activation_bytes_per_call": issued_activation_bytes,
        "lane_load_traffic": {
            "activation_bytes": lane_activation,
            "weight_bytes": lane_weight,
            "scale_bytes": lane_scale,
            "total_bytes": lane_total,
            "activation_share_pct": round(100 * lane_activation / lane_total, 2),
            "advisor_stated_share_pct": 47.0,
        },
        "amortisation_factor": outputs_per_simd,
        "k_blocks": 1,
    }


def roofline(local_decode_s: float | None = None) -> dict[str, object]:
    """Price the ceiling on any mechanism that does not reduce compulsory bytes.

    Both oproj arms move identical compulsory bytes (weight_code_reread_factor
    == 1.0 everywhere), so the *entire* headroom available to the geometry lever
    is the family's distance from a same-pattern reference rate. If that
    distance is below the shippable bar the experiment is a roofline null before
    a single arm is timed.
    """
    out: dict[str, object] = {
        "m4_ceiling_gb_per_s": M4_CEILING_GBS,
        "b_step_bytes": B_STEP_BYTES,
        "reference_pct_of_peak": REFERENCE_PCT,
        "families": {},
    }
    tot = {k: 0.0 for k in REFERENCE_PCT}
    for name, row in POOL_ROWS.items():
        gbs = row["head_bytes"] / row["m4_us"] / 1e3
        pct = 100.0 * gbs / M4_CEILING_GBS
        fam: dict[str, object] = {
            "calls": row["calls"],
            "head_bytes": row["head_bytes"],
            "bytes_per_dispatch": row["head_bytes"] / row["calls"],
            "m4_us_measured": row["m4_us"],
            "m4_us_per_dispatch": round(row["m4_us"] / row["calls"], 3),
            "m4_achieved_gb_per_s": round(gbs, 2),
            "m4_pct_of_ceiling": round(pct, 2),
            "m5_us_modelled": row["m5_us"],
            "m5_us_per_dispatch": round(row["m5_us"] / row["calls"], 3),
            "pct_of_b_step": round(100.0 * row["head_bytes"] / B_STEP_BYTES, 3),
            "headroom_us": {},
        }
        for ref, ref_pct in REFERENCE_PCT.items():
            us = row["m4_us"] * (1.0 - pct / ref_pct)
            fam["headroom_us"][ref] = round(us, 1)  # type: ignore[index]
            tot[ref] += us
        out["families"][name] = fam  # type: ignore[index]

    step_us = (local_decode_s * 1e6) if local_decode_s else None
    out["family_total_headroom_us"] = {k: round(v, 1) for k, v in tot.items()}
    if step_us:
        out["local_decode_step_us"] = round(step_us, 1)
        out["local_achieved_gb_per_s"] = round(B_STEP_BYTES / step_us / 1e3, 2)
        out["local_pct_of_ceiling_whole_step"] = round(
            100.0 * B_STEP_BYTES / step_us / 1e3 / M4_CEILING_GBS, 2
        )
        out["family_total_headroom_pct_of_decode"] = {
            k: round(100.0 * v / step_us, 3) for k, v in tot.items()
        }
        # rule 105: the bar is a bar on M5 us/step, so the local deficit must be
        # compared against the *converted* bar, not against 0.4 % of this host's
        # decode step. The retired `0.4 % x local step` figure was 52.3 us, which
        # coincidentally equals the beta=0.5 latency conversion; the bytes regime
        # that this family sits in gives 60.1 us (alpha=0.4369) or 67.5 (0.389).
        out["family_total_headroom_pct_of_cs"] = {
            k: {n: round(v * kk * DECODE_PRICE_PCT_PER_US, 4)
                for n, kk in K_BYTES.items()}
            for k, v in tot.items()
        }
        out["fraction_of_deficit_needed_to_clear_bar"] = {
            k: {n: round(b / v, 3) for n, b in bar_us_m4(SHIPPABLE_BAR_PCT).items()}
            for k, v in tot.items()
        }
        out["fraction_of_deficit_needed_to_clear_summand_bar"] = {
            k: {n: round(b / v, 3) for n, b in bar_us_m4(SUMMAND_BAR_PCT).items()}
            for k, v in tot.items()
        }
    out["shippable_bar_us_per_step_m4"] = bar_us_m4(SHIPPABLE_BAR_PCT)
    out["summand_bar_us_per_step_m4"] = bar_us_m4(SUMMAND_BAR_PCT)
    out["m5_bar_us"] = round(SHIPPABLE_BAR_PCT / 100.0 * M5_BASELINE_STEP_US, 1)
    out["caveat"] = (
        "m5_us columns inherit the alpha/beta degeneracy (CURRENT_RESEARCH_STATE "
        "B.0.6): alpha~0.389 (ceiling 686) and alpha~0.437 (ceiling 610.6) fit "
        "equally well and differ by ~12 pct in every M5 headroom figure. The "
        "m4_* columns are measured on this host and carry no such degeneracy."
    )
    return out


def main() -> int:
    arms: dict[str, dict[str, object]] = {}
    for path in sorted(ART.glob("oproj_g*_h*.metal")):
        arm, head = re.match(r"oproj_(g\d)_(h\d+)\.metal", path.name).groups()
        src = path.read_text()
        c = read_constants(src)
        struct = check_structure(src, c)
        if not all(struct.values()):
            print(f"{path.name}: STRUCTURE MISMATCH {struct}", file=sys.stderr)
            return 2
        arms.setdefault(arm, {})[head] = model(c) | {"structure_checks": struct}

    ledger = {
        "note": "issue-side counts only; compulsory DRAM bytes are identical across arms",
        "arms": arms,
        "factorial": {
            "design": "2x2 over (results_per_simdgroup in {4,8}) x (rows_per_threadgroup in {8,16})",
            "cells": {
                "g0": "rps=4 rows/tg=8  (shipped)",
                "g1": "rps=8 rows/tg=16",
                "g2": "rps=8 rows/tg=8",
                "g3": "rps=4 rows/tg=16 (amortisation held fixed: negative control)",
            },
            "amortisation_main_effect": "mean(g1,g2) - mean(g0,g3)",
            "threadgroup_shape_main_effect": "mean(g1,g3) - mean(g0,g2)",
        },
        "occupancy_bracket": {
            "design": "single factor: results_per_simdgroup 4 -> 2 at fixed num_simdgroups=2",
            "cells": {
                "g0": "rps=4 rows/tg=8  grid=16384 (shipped)",
                "g4": "rps=2 rows/tg=4  grid=32768 (2x grid threads, de-amortised)",
            },
            "purpose": "brackets the shipped geometry from the opposite side of the "
                       "grid-thread axis; the slot model and the measured occupancy "
                       "axis predict opposite signs for g4",
        },
        "roofline": roofline(local_decode_s=float(sys.argv[1]) if len(sys.argv) > 1 else None),
        "issue_ceiling": issue_ceiling(arms),
        "regime_fit": regime_fit(),
        "t2d_comparison_column": t2d_comparison_column(),
    }
    out = ART / "geom-traffic-model.json"
    out.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")

    for head in ("h64", "h48"):
        print(f"--- {head} ---")
        base = arms["g0"][head]
        for arm in sorted(arms):
            m = arms[arm][head]
            print(
                f"  {arm}: rps={m['results_per_simdgroup']} ns={m['num_simdgroups']} "
                f"rows/tg={m['rows_per_threadgroup']} thr/tg={m['threads_per_threadgroup']} "
                f"tgs={m['threadgroups']} grid={m['grid_threads']}"
            )
            print(
                f"       issued act={m['issued_activation_bytes'] / 1e6:.3f}MB "
                f"total={m['issued_bytes_total'] / 1e6:.3f}MB "
                f"({100 * (m['issued_bytes_total'] / base['issued_bytes_total'] - 1):+.1f}% vs g0) "
                f"issued/compulsory={m['issued_over_compulsory']} "
                f"act_reread={m['activation_reread_factor']}x ops/fma={m['ops_per_fma']}"
            )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
