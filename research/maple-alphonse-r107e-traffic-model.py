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
        out["shippable_bar_us_local"] = round(SHIPPABLE_BAR_PCT / 100.0 * step_us, 1)
        out["fraction_of_deficit_needed_to_clear_bar"] = {
            k: round(SHIPPABLE_BAR_PCT / 100.0 * step_us / v, 3) for k, v in tot.items()
        }
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
        "roofline": roofline(local_decode_s=float(sys.argv[1]) if len(sys.argv) > 1 else None),
    }
    out = ART / "geom-traffic-model.json"
    out.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")

    for head in ("h64", "h48"):
        print(f"--- {head} ---")
        base = arms["g0"][head]
        for arm in ("g0", "g1", "g2", "g3"):
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
