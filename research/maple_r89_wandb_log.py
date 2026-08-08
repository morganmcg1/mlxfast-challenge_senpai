#!/usr/bin/env python3
"""Publish the R89-A router weight prefetch evidence to W&B.

One run per arm carries that arm's occupancy gate, microbenchmark contrast and
in-situ contrast, plus a parent summary run holding the full tables. The probe
log is parsed rather than re-run so the numbers published are exactly the ones
in the committed artefacts.

Usage: maple_r89_wandb_log.py PROBE_LOG INSITU_RECORDS_JSON
"""
import json
import math
import os
import re
import statistics
import sys

import wandb

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
GROUP = "r89-a-router-weight-prefetch"

ARM_LABEL = {
    "0": "A0 depth0 (baseline, shipped)",
    "0b": "A0' depth0 (null control)",
    "1": "A1 depth1 hoisted",
    "2": "A2 depth2 hoisted",
    "3": "A5 depth3 hoisted",
    "4": "A3 depth4 hoisted (full)",
    "5": "A4 depth1 control (below barriers)",
}
ENV_OF_SLOT = {"0": 0, "0b": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5}
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
       14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
       20: 2.086}


def parse_probe(path):
    txt = open(path).read()
    occ, cold, hot = [], [], []
    section = None
    for line in txt.splitlines():
        if "occupancy (mandatory gate" in line:
            section = "occ"
            continue
        if "paired kernel time, COLD" in line:
            section = "cold"
            continue
        if "paired kernel time, HOT" in line:
            section = "hot"
            continue
        if section == "occ":
            m = re.match(r"(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(PASS|FAIL)\s+(.*)$",
                         line.strip())
            if m:
                occ.append({"arm_env": int(m.group(1)),
                            "max_total_threads": int(m.group(2)),
                            "exec_width": int(m.group(3)),
                            "static_tg_mem": int(m.group(4)),
                            "verdict": m.group(5), "label": m.group(6).strip()})
        elif section in ("cold", "hot"):
            m = re.match(r"(.+?)\s+([\d.]+)\s+([\d.]+)\s+(-?[\d.]+)\s+"
                         r"\[(-?[\d.+]+),(-?[\d.+]+)\]\s+(-?[\d.+]+)\s+"
                         r"(-?[\d.+]+)\s+(-?[\d.+]+)\s", line)
            if m:
                row = {"comparison": m.group(1).strip(),
                       "a_us_call": float(m.group(2)),
                       "b_us_call": float(m.group(3)),
                       "diff_us_call": float(m.group(4)),
                       "ci_lo": float(m.group(5)), "ci_hi": float(m.group(6)),
                       "abba_half": float(m.group(7)),
                       "baab_half": float(m.group(8)),
                       "diff_us_step": float(m.group(9))}
                (cold if section == "cold" else hot).append(row)
    return occ, cold, hot


def paired(recs, key):
    by_rep = {}
    for r in recs:
        if key in r:
            by_rep.setdefault(r["rep"], {})[r["slot"]] = r[key]
    out = {}
    for slot in ARM_LABEL:
        diffs = [b[slot] - b["0"] for b in by_rep.values()
                 if slot in b and "0" in b]
        levels = [b[slot] for b in by_rep.values() if slot in b]
        if not levels:
            continue
        e = {"level": statistics.mean(levels), "n": len(levels)}
        if len(diffs) > 1:
            d, sd = statistics.mean(diffs), statistics.stdev(diffs)
            hw = T95.get(len(diffs) - 1, 1.96) * sd / math.sqrt(len(diffs))
            e.update(diff=d, ci_lo=d - hw, ci_hi=d + hw, sd=sd)
        out[slot] = e
    return out


def main():
    probe_log, insitu_json = sys.argv[1], sys.argv[2]
    occ, cold, hot = parse_probe(probe_log)
    recs = json.load(open(insitu_json)) if os.path.exists(insitu_json) else []

    keys = ["router_us_call", "router_us_step", "busy_sum_ms",
            "busy_union_ms", "median_ms", "gap_ms", "wall_ms"]
    insitu = {k: paired(recs, k) for k in keys}
    n_call = max([r.get("router_n_step") or 0 for r in recs] or [39.0])

    common = {
        "assignment_id": "maple-r89-a-router-weight-prefetch",
        "revision_id": "r89-a-rev1",
        "pr": 475,
        "base_sha": "098cfe0b935b87912e537ae29e21fd6339bafca8",
        "scored_content_base": "3217f111142346e004f41fae611a8bede172a659",
        "host": "Apple M4 Pro applegpu_g16s 48GiB",
        "submitted_path": "Sources/MLXFastModel/LagunaRuntimeModel.swift",
        "router_calls_per_step": n_call,
        "knob": "DARKBLOOM_ROUTER_WEIGHT_PREFETCH",
    }

    cold_by = {r["comparison"]: r for r in cold}
    hot_by = {r["comparison"]: r for r in hot}
    slot_cmp = {"1": "A1 - A0", "2": "A2 - A0", "3": "A5 - A0  (depth3)",
                "4": "A3 - A0", "5": "A4 - A0"}

    for slot, label in ARM_LABEL.items():
        env = ENV_OF_SLOT[slot]
        run = wandb.init(entity=ENTITY, project=PROJECT, group=GROUP,
                         name=f"r89a-arm{slot}", job_type="arm",
                         config=dict(common, arm_slot=slot, arm_env=env,
                                     arm_label=label),
                         reinit=True)
        log = {}
        o = next((x for x in occ if x["arm_env"] == env), None)
        if o:
            log.update({f"occupancy/{k}": v for k, v in o.items()
                        if k != "label"})
            log["occupancy/gate_pass"] = 1.0 if o["verdict"] == "PASS" else 0.0
        c = cold_by.get(slot_cmp.get(slot, ""))
        if c:
            log.update({f"microbench_cold/{k}": v for k, v in c.items()
                        if k != "comparison"})
        h = hot_by.get(slot_cmp.get(slot, ""))
        if h:
            log.update({f"microbench_hot/{k}": v for k, v in h.items()
                        if k != "comparison"})
        for k, table in insitu.items():
            e = table.get(slot)
            if e:
                log.update({f"insitu/{k}_{f}": v for f, v in e.items()})
        divs = [r.get("divergences") for r in recs if r.get("slot") == slot]
        if divs:
            log["correctness/divergences_max"] = max(d or 0 for d in divs)
            log["correctness/n_runs"] = len(divs)
        run.log(log)
        run.summary.update(log)
        run.finish()

    run = wandb.init(entity=ENTITY, project=PROJECT, group=GROUP,
                     name="r89a-summary", job_type="summary",
                     config=common, reinit=True)
    if occ:
        run.log({"occupancy_table": wandb.Table(
            columns=list(occ[0].keys()),
            data=[list(r.values()) for r in occ])})
    for nm, rows in (("microbench_cold_table", cold),
                     ("microbench_hot_table", hot)):
        if rows:
            run.log({nm: wandb.Table(columns=list(rows[0].keys()),
                                     data=[list(r.values()) for r in rows])})
    for k, table in insitu.items():
        rows = [[s, e["n"], e["level"], e.get("diff"), e.get("ci_lo"),
                 e.get("ci_hi")] for s, e in table.items()]
        if rows:
            run.log({f"insitu_{k}_table": wandb.Table(
                columns=["slot", "n", "level", "paired_diff", "ci_lo", "ci_hi"],
                data=rows)})
    if recs:
        cols = sorted({k for r in recs for k in r})
        run.log({"insitu_raw": wandb.Table(
            columns=cols, data=[[r.get(c) for c in cols] for r in recs])})
    run.finish()
    print("logged to", f"{ENTITY}/{PROJECT} group={GROUP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
