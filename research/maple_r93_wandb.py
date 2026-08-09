"""Log the R93-C stall-structure census to W&B.

This is a diagnostic round with no candidate and no training curve: the run
records the roofline arithmetic, every probe arm, and the fitted ladder slopes
as tables plus summary scalars.

  python3 research/maple_r93_wandb.py OUTDIR [OUTDIR ...]
"""

import json
import sys
from collections import defaultdict

import wandb

from maple_r93_analyze import (
    ALU_OPS_PER_S,
    BYTES_PER_STEP,
    GEOM,
    PATTERN_CEILING_GBPS,
    SEQ_PEAK_GBPS,
    SPLIT_TAX_US,
    load,
    ols,
)

BASE_SHA = "ca920bbe6938ae7efb9cab79739229a0321ba856"


def main() -> int:
    paths = sys.argv[1:]
    recs = load(paths)
    by_arm = defaultdict(list)
    for r in recs:
        by_arm[r["arm"]].append(r)

    arm_rows = []
    for arm, rs in sorted(by_arm.items()):
        for r in rs:
            rows = r["rows"]
            arm_rows.append([
                arm, r["index"], r["steps"], r["divergences"],
                round(r["busy_sum_ms"], 4), round(r["wall_ms"], 4),
                round(rows.get("qkv", {}).get("us_per_step", float("nan")), 1),
                round(rows.get("oproj", {}).get("us_per_step", float("nan")), 1),
                round(rows.get("routed", {}).get("us_per_step", float("nan")), 1),
            ])

    base = by_arm.get("off", [])
    roof_rows = []
    for tag in GEOM:
        vals = [r["rows"][tag]["us_per_step"] for r in base if tag in r["rows"]]
        if not vals:
            continue
        us = sum(vals) / len(vals)
        net = us - SPLIT_TAX_US * GEOM[tag]["dispatches"]
        gbps = BYTES_PER_STEP[tag] / (us * 1e-6) / 1e9
        ngbps = BYTES_PER_STEP[tag] / (net * 1e-6) / 1e9
        roof_rows.append([
            tag, round(us, 1), round(net, 1),
            round(BYTES_PER_STEP[tag] / 1e6, 1), round(gbps, 1), round(ngbps, 1),
            PATTERN_CEILING_GBPS[tag], round(ngbps / PATTERN_CEILING_GBPS[tag] * 100, 1),
            round(ngbps / SEQ_PEAK_GBPS * 100, 1),
        ])

    ladders = defaultdict(lambda: defaultdict(list))
    for arm, rs in by_arm.items():
        if ":" not in arm or "@" in arm:
            continue
        tgt, kind, n = arm.split(":")
        for r in rs:
            if tgt in r["rows"]:
                ladders[(tgt, kind)][int(n)].append(r["rows"][tgt]["us_per_step"])

    fit_rows = []
    for (tgt, kind) in sorted(ladders):
        lv = dict(ladders[(tgt, kind)])
        if 0 not in lv:
            pooled = [v for k, vv in ladders.items() if k[0] == tgt and 0 in vv
                      for v in vv[0]]
            if pooled:
                lv[0] = pooled
        xs = [n for n, vals in sorted(lv.items()) for _ in vals]
        ys = [v for _, vals in sorted(lv.items()) for v in vals]
        slope, _, half = ols(xs, ys)
        if kind in ("fma", "imad"):
            per_n = GEOM[tgt]["alu_ops_per_n"]
            nominal = per_n / ALU_OPS_PER_S * 1e6
            norm = slope / nominal * 100
            unit = "% of issue-limited cost"
        else:
            per_n = GEOM[tgt]["threads"] * (8 if kind == "ld8" else 16)
            nominal = float("nan")
            norm = per_n / (slope * 1e-6) / 1e9 if slope == slope and slope > 0 else float("nan")
            unit = "marginal GB/s"
        fit_rows.append([
            tgt, kind, len(xs), sorted(lv),
            round(slope, 2), round(half, 2), round(per_n / 1e6, 2),
            round(nominal, 2), round(norm, 2), unit,
        ])

    run = wandb.init(
        entity="wandb-applied-ai-team",
        project="mlxfast-maple",
        name="r93-c-stall-structure-census",
        job_type="diagnostic",
        tags=["r93-c", "stall-structure", "roofline", "diagnostic", "m4pro"],
        config={
            "assignment_id": "maple-r93-c-stall-structure-census",
            "revision_id": "r93-c-rev1",
            "pr": 498,
            "base_sha": BASE_SHA,
            "branch": "maple-nezuko/r93-stall-structure-census",
            "host": "M4 Pro applegpu_g16s 48 GiB (directional; ranked host is M5 Max)",
            "probe": "decode_probe.py --profile, DARKBLOOM_GPU_PROFILE_SPLIT=1",
            "probe_env": "NEZUKO_R93_PROBE=<target>:<kind>:<n>",
            "arms": len(arm_rows),
            "editable_bytes_changed": 0,
            "ships_a_fix": False,
        },
    )
    run.log({
        "census/arms": wandb.Table(
            columns=["arm", "rep", "steps", "divergences", "busy_sum_ms",
                     "wall_ms", "qkv_us", "oproj_us", "routed_us"],
            data=arm_rows),
        "roofline/table": wandb.Table(
            columns=["kernel", "raw_us_per_step", "net_us_per_step", "MB_per_step",
                     "raw_GB_s", "net_GB_s", "pattern_ceiling_GB_s",
                     "pct_pattern_ceiling", "pct_sequential_peak"],
            data=roof_rows),
        "ladders/fits": wandb.Table(
            columns=["kernel", "kind", "n_points", "levels", "slope_us_per_n",
                     "ci95_halfwidth", "work_per_n_M", "nominal_us_per_n",
                     "normalized", "normalized_unit"],
            data=fit_rows),
    })

    summary = {"probe/arms_total": len(arm_rows),
               "probe/non_bit_exact_arms":
                   sum(1 for r in recs if r.get("divergences"))}
    for row in roof_rows:
        summary[f"roofline/{row[0]}/net_GB_s"] = row[5]
        summary[f"roofline/{row[0]}/pct_pattern_ceiling"] = row[7]
        summary[f"roofline/{row[0]}/pct_sequential_peak"] = row[8]
    for row in fit_rows:
        summary[f"ladder/{row[0]}/{row[1]}/slope_us_per_n"] = row[4]
        summary[f"ladder/{row[0]}/{row[1]}/ci95"] = row[5]
        summary[f"ladder/{row[0]}/{row[1]}/normalized"] = row[8]
    for arm in ("off", "off@nosplit"):
        rs = by_arm.get(arm, [])
        if rs:
            key = arm.replace("@", "_")
            summary[f"split/{key}/busy_sum_ms"] = sum(
                r["busy_sum_ms"] for r in rs) / len(rs)
            summary[f"split/{key}/wall_ms"] = sum(
                r["wall_ms"] for r in rs) / len(rs)
    run.summary.update(summary)
    print(json.dumps({"run_id": run.id, "url": run.url}, indent=1))
    run.finish()
    return 0


if __name__ == "__main__":
    sys.exit(main())
