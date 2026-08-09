#!/usr/bin/env python3
"""Publish the three R97-A Stage 2 rung states to W&B (research only).

One run per timed state (base / S2a / S2b), each carrying the two assignment
primary metrics `dense_mlp_bytes_per_step` and `dense_mlp_us_per_step`, plus the
ladder and per-run estimators and the raw process files as an artifact.

  python3 research/fern_r97_wandb_log.py \
      --ladder /tmp/r97/ladder/ladder.json \
      --perrun /tmp/r97/perrun/perrun01.json /tmp/r97/perrun/perrun02.json \
      --records '/tmp/r97/ladder/p*.json' --group r97a-stage2
"""
import argparse
import glob
import json
import os
import statistics

import wandb

PROJECT = os.environ.get("WANDB_PROJECT", "mlxfast-maple")
ENTITY = os.environ.get("WANDB_ENTITY", "wandb-applied-ai-team")

# Preregistered census, research/fern-r97-stage2-preregistration.md.
BYTES_PER_STEP = {0: 100_663_296, 1: 84_592_384, 2: 80_400_128}
PREDICTED_US_SAVED = {0: 0.0, 1: 60.3, 2: 76.1}
STATE = {0: "base", 1: "s2a-gate-up", 2: "s2b-gate-up-plus-down"}
DESCRIPTION = {
    0: "stock BF16 dense gate/up and down",
    1: "block-exponent gate/up B=128 d=4 with escapes, stock BF16 down",
    2: "block-exponent gate/up plus block-exponent down B=row(8192) d=6, no escapes",
}


# The shared R93 probe records the schedule depth as `k = 40 * depth`, one unit
# per decoder layer. Here a depth is a rung, so rung r appears as k = 40 * r in
# both the raw records and the analyser JSON keys.
K_PER_RUNG = 40


def load_records(patterns):
    files = []
    for pat in patterns:
        files.extend(sorted(glob.glob(pat)))
    per_rung = {}
    hashes = set()
    mismatches = 0
    for path in files:
        with open(path) as fh:
            doc = json.load(fh)
        hashes.update(doc.get("token_stream_hashes", []))
        mismatches += int(doc.get("teacher_forced_mismatches", 0))
        for rec in doc["records"]:
            if rec.get("warmup_run") or rec.get("placebo"):
                continue
            per_rung.setdefault(int(rec["k"]) // K_PER_RUNG, []).append(
                float(rec["us"]))
    return files, per_rung, sorted(hashes), mismatches


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ladder", required=True)
    ap.add_argument("--perrun", nargs="*", default=[])
    ap.add_argument("--records", nargs="*", default=[])
    ap.add_argument("--group", default="r97a-stage2")
    ap.add_argument("--notes", default="")
    ap.add_argument("--extra", default="{}", help="JSON dict merged into summary")
    args = ap.parse_args()

    with open(args.ladder) as fh:
        ladder = json.load(fh)
    perrun = []
    for path in args.perrun:
        with open(path) as fh:
            perrun.append(json.load(fh))

    files, per_rung, hashes, mismatches = load_records(args.records)
    extra = json.loads(args.extra)

    wandb_dir = os.environ.get("WANDB_DIR", "/tmp/r97/wandb")
    os.makedirs(wandb_dir, exist_ok=True)

    for k in (0, 1, 2):
        samples = per_rung.get(k, [])
        # `dense_mlp_us_per_step` is the whole single-token decode step for that
        # state; the ladder delta is the paired contrast between states.
        median_us = statistics.median(samples) if samples else float("nan")
        delta = ladder["delta"].get(str(k * K_PER_RUNG), {})
        delta_us = float(delta.get("delta", 0.0))
        ci = delta.get("ci", [0.0, 0.0])
        saved_us = -delta_us  # ladder deltas are candidate-minus-base
        bytes_removed = BYTES_PER_STEP[0] - BYTES_PER_STEP[k]
        predicted = PREDICTED_US_SAVED[k]
        efficiency = (saved_us / predicted) if predicted else float("nan")

        run = wandb.init(
            dir=wandb_dir, entity=ENTITY, project=PROJECT,
            name=f"r97a-stage2-{STATE[k]}", group=args.group,
            notes=args.notes or DESCRIPTION[k],
            job_type="dense-mlp-block-exponent",
            tags=["maple", "student:maple-fern", "pr525", "r97-a", "stage2",
                  STATE[k]],
            config={
                "rung": k, "state": STATE[k], "description": DESCRIPTION[k],
                "host": "m4pro-48gb", "assignment": "maple-r97-a-dense-mlp-stage2",
                "revision": "r97-a-rev1",
                "n_process_files": len(files),
                "n_kept_steps": len(samples),
                "predicted_us_saved": predicted,
                "predicted_bytes_removed_per_step": bytes_removed,
            },
        )
        run.summary["dense_mlp_bytes_per_step"] = BYTES_PER_STEP[k]
        run.summary["dense_mlp_us_per_step"] = median_us
        run.summary["dense_mlp_bytes_removed_per_step"] = bytes_removed
        run.summary["dense_mlp_mb_removed_per_step"] = bytes_removed / 1e6
        run.summary["ladder_delta_us"] = delta_us
        run.summary["ladder_delta_ci_lo"] = ci[0]
        run.summary["ladder_delta_ci_hi"] = ci[1]
        run.summary["ladder_saved_us"] = saved_us
        run.summary["ladder_resolved"] = bool(delta.get("resolved", False))
        run.summary["conversion_efficiency"] = efficiency
        run.summary["token_stream_hashes"] = json.dumps(hashes)
        run.summary["teacher_forced_mismatches"] = mismatches
        for doc in perrun:
            if int(doc["hi_k"]) != k * K_PER_RUNG:
                continue
            run.summary["perrun_delta_us"] = doc["delta_us_per_step"]
            run.summary["perrun_delta_ci_lo"] = doc["delta_ci"][0]
            run.summary["perrun_delta_ci_hi"] = doc["delta_ci"][1]
            run.summary["perrun_saved_us"] = -doc["delta_us_per_step"]
            run.summary["perrun_n_run_pairs"] = doc["n_run_pairs"]
        for key, value in extra.items():
            run.summary[key] = (value if isinstance(value, (int, float))
                                else json.dumps(value))

        if samples:
            table = wandb.Table(columns=["us"], data=[[x] for x in samples])
            run.log({"steps": table})
        if k == 2 and files:
            art = wandb.Artifact("r97a-stage2-raw", type="timing")
            for path in files + [args.ladder] + args.perrun:
                art.add_file(path)
            run.log_artifact(art)

        print(f"RUNG={k} WANDB_RUN_ID={run.id} WANDB_RUN_URL={run.url}")
        run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
