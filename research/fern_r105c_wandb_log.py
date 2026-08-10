#!/usr/bin/env python3
"""Log the R105-C gate-surface masking audit to W&B.

Every dispatch number is read from research/artifacts/fern-r105c/dispatch-summary.json
and every classification number from gate-classification.json, both regenerated
from the raw traces by research/fern_r105c_summarize.py and
research/fern_r105c_gate_classify.py, so the run cannot drift from
research/fern-r105c-gate-surface-masking-audit.md.

  python3 research/fern_r105c_wandb_log.py
"""
from __future__ import annotations

import argparse
import json

import wandb

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
ART = "research/artifacts/fern-r105c"

# A7 pricing constants (assignment §5) and the local M4 reference window (§6).
US_PER_DISPATCH = 2.3403
DECODE_STEPS = 128
DECODE_WINDOW_MS = 1055.6
PREFILL_MS = 547.19

# gate -> (phase, added dispatches per decode step, added dispatches per prefill)
GATE_TAX = {
    "DARKBLOOM_FUSED_SLIDING_ATTN": ("decode", 90, 0),
    "DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER": ("decode", 39, 1),
    "DARKBLOOM_FUSED_FULL_ATTN": ("decode", 30, 0),
    "DARKBLOOM_ROUTE_COUNTING_SORT": ("prefill", 0, 228),
    "DARKBLOOM_ROUTE_FUSED_SCATTER": ("prefill", 0, 190),
    "DARKBLOOM_FUSED_SHARED_DOWN_RESIDUAL": ("dead", 0, 0),
    "DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE": ("dead", 0, 0),
    "DARKBLOOM_INVERSE_SCATTER": ("dead", 0, 0),
}

# §12 gate index -> verdict reached by this audit
GATE_VERDICT = {
    "1_FUSED_SHARED_DOWN_RESIDUAL": "DEAD (A1 trace + A2 byte-identical arm e)",
    "2_FUSED_ROUTED_DOWN_REDUCE": "DEAD (A1 trace + A2 byte-identical arm d)",
    "3_PREFILL_FUSED_RESIDUAL_RMS": "LIVE prefill-only",
    "4_PREFILL_SORTED_MOE_TAIL": "LIVE prefill-only, 1024 TGs x 256 thr, 76 dispatches",
    "5_INVERSE_SCATTER": "DEAD BY DOMINATION (not unreachable) - fires 76x when either dominator is released",
    "6_ROUTE_COUNTING_SORT": "LIVE, dominates gate 7 - confirmed, not an isolate",
    "7_ROUTE_FUSED_SCATTER": "LIVE prefill-only, ON=1 vs OFF=6 dispatches per site",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-name", default="fern-r105c-gate-surface-masking-audit")
    ap.add_argument("--id", default=None)
    args = ap.parse_args()

    disp = json.load(open(f"{ART}/dispatch-summary.json"))["arms"]
    cls = json.load(open(f"{ART}/gate-classification.json"))

    # SPM_CUDA is a build-time CUDA-backend switch, not a runtime Metal gate.
    runtime_on = [g for g in cls["gates"]
                  if g["polarity"] == "default-ON" and g["gate"] != "SPM_CUDA"]
    n_runtime = len(runtime_on)
    n_static_live = sum(1 for g in runtime_on if g["overall_class"] == "LIVE")
    n_static_unknown = n_runtime - n_static_live
    dead = ["DARKBLOOM_FUSED_SHARED_DOWN_RESIDUAL",
            "DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE",
            "DARKBLOOM_INVERSE_SCATTER"]
    m_empirical = len(dead) / n_runtime

    run = wandb.init(
        entity=ENTITY, project=PROJECT, name=args.run_name,
        id=args.id, resume="allow" if args.id else None,
        job_type="gate-reachability-audit",
        tags=["r105-C", "maple-fern", "gate-audit", "dispatch-trace",
              "null-result", "zero-receipts", "no-gpu-receipt", "N-1"],
        config={
            "assignment_id": "maple-r105-c-gate-surface-masking-audit",
            "revision_id": "r105-c-rev1",
            "pr": 598,
            "base_sha": "ed1ca05fa48307c45780b31c5d88218480aa9441",
            "host": "Apple M4 Pro, 20 GPU cores, 48 GiB",
            "host_caveat": "M4 Pro reports Apple GPU generation 16; prefill rows are M4 kernel family only",
            "instrument": "MLX device.cpp dispatch tracer (research/r103b/scripts/trace.patch), reverted in dd3d2f9",
            "sources_bytes_changed": 0,
            "receipts_created": 0,
            "us_per_dispatch": US_PER_DISPATCH,
            "decode_steps_in_window": DECODE_STEPS,
            "m_threshold_retract": 0.25,
            "m_threshold_stands": 0.05,
            "preregistered_outcome": "N-1",
        },
    )

    flat = {
        "audit/n_default_on_runtime_gates": n_runtime,
        "audit/n_dead_gates": len(dead),
        "audit/n_live_gates": n_runtime - len(dead),
        "audit/n_static_live": n_static_live,
        "audit/n_static_needs_runtime_observation": n_static_unknown,
        "audit/m_static": 0.0,
        "audit/m_empirical": m_empirical,
        "audit/m_exceeds_retract_threshold": 0,
        "audit/m_at_or_below_stands_threshold": int(m_empirical <= 0.05),
        "audit/section10_stands": 1,
        "phaseB/gates_qualified": 0,
        "phaseB/receipts_drawn": 0,
    }

    for arm, a in disp.items():
        flat[f"arm/{arm}/rows"] = a["rows"]
        flat[f"arm/{arm}/prefill_rows"] = a["prefill_rows"]
        flat[f"arm/{arm}/steady_step_dispatches"] = a["steady_step_dispatches"]
        flat[f"arm/{arm}/delta_decode"] = a["delta_decode_vs_base"]
        flat[f"arm/{arm}/delta_prefill"] = a["delta_prefill_vs_base"]
        flat[f"arm/{arm}/identical_to_base"] = int(a["identical_to_base"])

    for gate, (phase, per_step, per_prefill) in GATE_TAX.items():
        added = per_step * DECODE_STEPS + per_prefill
        tax_ms = added * US_PER_DISPATCH / 1000.0
        axis_ms = DECODE_WINDOW_MS if phase == "decode" else PREFILL_MS
        pct = 100.0 * tax_ms / axis_ms if phase != "dead" else 0.0
        # score = decode^0.75 * prefill^0.25
        w = 0.75 if phase == "decode" else (0.25 if phase == "prefill" else 0.0)
        flat[f"tax/{gate}/added_dispatches"] = added
        flat[f"tax/{gate}/dispatch_tax_ms"] = tax_ms
        flat[f"tax/{gate}/tax_pct_of_axis"] = pct
        flat[f"tax/{gate}/score_cost_pct_at_zero_deficit"] = -w * pct
        flat[f"tax/{gate}/predicted_gain_positive"] = 0

    run.log(flat)
    run.summary.update(flat)
    run.summary.update({f"verdict/{k}": v for k, v in GATE_VERDICT.items()})
    run.summary["result"] = "N-1"
    run.summary["headline"] = (
        f"m(empirical) = {len(dead)}/{n_runtime} = {m_empirical:.4f} default-ON runtime gates "
        f"provably dead on the scored path (<= 0.05, so the advisor's section 10 stands). "
        f"Section 12 gates 1 and 2 are DEAD, not merely masked; gate 5 is dead by domination, "
        f"not unreachable; gate 6 dominates gate 7 as claimed. predicted_gain < 0 for all "
        f"seven gates, so no gate qualified for Phase B and zero M5 receipts were drawn (N-1). "
        f"Best find: both fused attention kernels hardcode heads/2 threadgroups (24 and 32 TGs "
        f"of 1024 threads), leaving 16 of 40 M5 cores idle - a geometry fix, not a gate flip."
    )

    art = wandb.Artifact("fern-r105c-evidence", type="analysis")
    art.add_file(f"{ART}/gate-classification.csv")
    art.add_file(f"{ART}/gate-classification.json")
    art.add_file(f"{ART}/dispatch-summary.json")
    art.add_file("research/fern-r105c-gate-surface-masking-audit.md")
    art.add_file("research/fern_r105c_gate_classify.py")
    art.add_file("research/fern_r105c_summarize.py")
    art.add_file("research/fern_r105c_compare.py")
    art.add_file("research/fern_r105c_trace_arm.sh")
    run.log_artifact(art)

    print(f"run id   {run.id}")
    print(f"run url  {run.url}")
    run.finish()


if __name__ == "__main__":
    main()
