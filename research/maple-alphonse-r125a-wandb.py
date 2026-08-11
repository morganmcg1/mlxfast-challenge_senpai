#!/usr/bin/env python3
"""Publish the R125-A shared-QMV threadgroup-width replication to W&B.

Usage: python3 research/maple-alphonse-r125a-wandb.py OUTDIR [OUTDIR ...]

Parsing and estimators are imported from `maple_r125a_analyze.py` so the run's
numbers cannot drift from the memo's numbers. Every slot is logged as a step in
the order it ran, so the mirrored 64/256/256/64 sequence and any thermal drift
are inspectable in the UI.
"""

import importlib.util
import os
import statistics
import subprocess
import sys

import wandb

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "r125a_analyze", os.path.join(REPO, "research/maple_r125a_analyze.py"))
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)
WSPEC = importlib.util.spec_from_file_location(
    "r125a_wall", os.path.join(REPO, "research/maple_r125a_wall_analyze.py"))
W = importlib.util.module_from_spec(WSPEC)
WSPEC.loader.exec_module(W)

# Ranked-host quantisation: worst-core rows = ceil(TGs/C) * rows_per_TG.
RANKED_CORES, LOCAL_CORES = 40, 20


def worst_core_rows(tg_width: int, cores: int, rows: int = 512) -> int:
    simdgroups = tg_width // 32
    tgs = rows // simdgroups
    return -(-tgs // cores) * simdgroups


def main(outdirs):
    slots = {}
    for outdir in outdirs:
        for name in sorted(os.listdir(outdir)):
            if not name.endswith(".log"):
                continue
            m = A.SLOT.match(name[:-4])
            if not m:
                continue
            parsed = A.parse_log(os.path.join(outdir, name))
            if parsed is None:
                continue
            slots[(int(m.group(1)), int(m.group(2)))] = (int(m.group(3)), *parsed)
    if not slots:
        raise SystemExit("no parseable slots")

    arms = sorted({v[0] for v in slots.values()})
    blocks = sorted({b for b, _ in slots})
    base_arm = arms[0]
    per_arm = {a: [] for a in arms}
    for (_b, _s), (tg, kernels, _h) in sorted(slots.items()):
        per_arm[tg].append(A.family_total(kernels, A.SHARED_QMV)[0])

    deltas = {}
    for a in arms[1:]:
        d = []
        for b in blocks:
            ref = [v[1] for (bb, _), v in slots.items()
                   if bb == b and v[0] == base_arm]
            cand = [v[1] for (bb, _), v in slots.items()
                    if bb == b and v[0] == a]
            if ref and cand:
                d.append(
                    statistics.mean(A.family_total(k, A.SHARED_QMV)[0] for k in cand)
                    - statistics.mean(A.family_total(k, A.SHARED_QMV)[0] for k in ref))
        deltas[a] = d

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                          capture_output=True, text=True).stdout.strip()

    run = wandb.init(
        entity="wandb-applied-ai-team",
        project="mlxfast-maple",
        name="r125a-shared-qmv-tg256-replication",
        group="r125a-shared-qmv-tg256",
        job_type="kernel-geometry-replication",
        tags=["maple-alphonse", "r125-A", "shared_expert", "swiglu_qmv",
              "threadgroup-geometry", "gpu-busy-atlas", "split1", "mirrored-abba",
              "m4-directional", "replication"],
        notes=(
            "Replication of frieren's R119-C shared-expert SwiGLU QMV "
            "threadgroup-width arms on the maple advisor base. The 512 output "
            "rows, one row per simdgroup, are partitioned either as 2 "
            "simdgroups x 256 threadgroups (TG=64, the shipped default) or as 8 "
            "x 64 (TG=256, the geometry PR #729 proposed to land). Bytes read, "
            "arithmetic and output are byte-identical; only the partition "
            "changes. Instrument is decode_probe.py --profile with "
            "DARKBLOOM_GPU_PROFILE_SPLIT=1, 200 steps, 40C gate per slot, "
            "mirrored 64/256/256/64 blocks. The reported metric is a per-step "
            "GPU-busy COST of the kernel: lower is better. Directional M4 Pro "
            "evidence only (Apple GPU generation 16, never selects _nax)."),
        config={
            "assignment_id": "maple-r125-a-shared-qmv-tg256-landing",
            "revision_id": "r125-a-rev1",
            "pr": 729,
            "branch": "maple-alphonse/r125-a-shared-qmv-tg256-landing",
            "base_sha": "a9de9e8f21188715f6d80ada4b581bcd50d4ec81",
            "head_sha": head,
            "env_switch": "DARKBLOOM_SHARED_QMV_TG",
            "arms": arms,
            "blocks": len(blocks),
            "slots_per_arm": {str(a): len(per_arm[a]) for a in arms},
            "steps_per_slot": 200,
            "gpu_profile_split": 1,
            "split1_inflation_us_per_call": 1.554,
            "atlas_resolution_us_step": A.RESOLUTION_US,
            "host": "M4 Pro, 20 GPU cores, 48 GiB, Apple GPU gen 16",
            "startup_memory_profile": "low-memory (host < 64 GiB)",
            "ranked_cores": RANKED_CORES,
            "local_cores": LOCAL_CORES,
        },
    )

    for i, ((b, s), (tg, kernels, header)) in enumerate(sorted(slots.items())):
        us, n = A.family_total(kernels, A.SHARED_QMV)
        wandb.log({
            "slot/index": i,
            "slot/block": b,
            "slot/position": s,
            "slot/tg_width": tg,
            "slot/shared_qmv_us_per_step": us,
            "slot/shared_qmv_calls_per_step": n,
            "slot/shared_qmv_us_per_call": us / n if n else float("nan"),
            "slot/gpu_busy_sum_ms": header.get("gpu_busy_sum"),
            "slot/gpu_busy_union_ms": header.get("gpu_busy_union"),
            "slot/wall_ms": header.get("wall"),
            "slot/gap_ms": header.get("gap"),
        }, step=i)

    summary = {}
    for a in arms:
        m, sem = A.mean_sem(per_arm[a])
        summary[f"arm/tg{a}/shared_qmv_us_per_step_mean"] = m
        summary[f"arm/tg{a}/shared_qmv_us_per_step_sem"] = sem
        summary[f"arm/tg{a}/n"] = len(per_arm[a])
        summary[f"arm/tg{a}/worst_core_rows_c40"] = worst_core_rows(a, RANKED_CORES)
        summary[f"arm/tg{a}/worst_core_rows_c20"] = worst_core_rows(a, LOCAL_CORES)
    base_mean = statistics.mean(per_arm[base_arm])
    for a, d in deltas.items():
        m, sem = A.mean_sem(d)
        lo, hi = A.ci95(d)
        # C=20 exaggerates arm imbalance relative to the ranked C=40 host; deflate
        # the local delta by the ratio of the two worst-core penalties.
        pen20 = worst_core_rows(a, LOCAL_CORES) / worst_core_rows(base_arm, LOCAL_CORES) - 1
        pen40 = worst_core_rows(a, RANKED_CORES) / worst_core_rows(base_arm, RANKED_CORES) - 1
        summary.update({
            f"delta/tg{a}_vs_tg{base_arm}/us_per_step": m,
            f"delta/tg{a}_vs_tg{base_arm}/sem": sem,
            f"delta/tg{a}_vs_tg{base_arm}/ci95_lo": lo,
            f"delta/tg{a}_vs_tg{base_arm}/ci95_hi": hi,
            f"delta/tg{a}_vs_tg{base_arm}/pct_of_kernel": m / base_mean * 100,
            f"delta/tg{a}_vs_tg{base_arm}/blocks_positive": sum(1 for x in d if x > 0),
            f"delta/tg{a}_vs_tg{base_arm}/blocks": len(d),
            f"delta/tg{a}_vs_tg{base_arm}/ranked_equivalent_us_per_step":
                m * (pen40 / pen20) if pen20 else float("nan"),
        })
    wall_out = os.environ.get("R125A_WALL_OUT")
    if wall_out and os.path.isdir(wall_out):
        summary.update(W.wandb_summary(wall_out))
    summary["verdict"] = "do-not-land: TG=256 is a cost, not a gain"
    run.summary.update(summary)
    print(f"wandb run: {run.url}  id={run.id}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["/tmp/maple-r125a-atlas"]))
