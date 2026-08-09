#!/usr/bin/env python3
"""Publish one R93-B stage to W&B (research only, not part of the submission).

  python3 research/fern_r93_wandb_log.py --name r93b-stage1 \
      --stage stage1 --summary /tmp/r93/stage1/variance.json \
      --records /tmp/r93/stage1/p*.json
"""
import argparse
import glob
import json
import os

import wandb

PROJECT = os.environ.get("WANDB_PROJECT", "mlxfast-maple")
ENTITY = os.environ.get("WANDB_ENTITY", "wandb-applied-ai-team")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--stage", required=True)
    ap.add_argument("--summary", default=None)
    ap.add_argument("--records", nargs="*", default=[])
    ap.add_argument("--notes", default="")
    ap.add_argument("--extra", default="{}", help="JSON dict merged into summary")
    args = ap.parse_args()

    files = []
    for pat in args.records:
        files.extend(sorted(glob.glob(pat)))

    # Keep wandb's scratch tree out of the checkout: run_job refuses to start
    # while the assignment worktree is dirty, and ./wandb would dirty it.
    wandb_dir = os.environ.get("WANDB_DIR", "/tmp/r93/wandb")
    os.makedirs(wandb_dir, exist_ok=True)

    run = wandb.init(
        dir=wandb_dir,
        entity=ENTITY, project=PROJECT, name=args.name, notes=args.notes,
        job_type="rig-calibration",
        tags=["maple", "student:maple-fern", "pr497", "r93-b", args.stage],
        config={"stage": args.stage, "host": "m4pro-48gb", "n_process_files": len(files)},
    )

    summary = {}
    if args.summary:
        with open(args.summary) as fh:
            summary = json.load(fh)
    summary.update(json.loads(args.extra))
    for k, v in summary.items():
        if isinstance(v, (int, float)):
            run.summary[k] = v
        else:
            run.summary[k] = json.dumps(v)

    if files:
        table = wandb.Table(columns=["process", "run", "step", "glue", "k", "us",
                                     "warmup_run", "gpu_c"])
        for path in files:
            with open(path) as fh:
                doc = json.load(fh)
            for rec in doc["records"]:
                table.add_data(rec["process"], rec["run"], rec["step"], rec["glue"],
                               rec["k"], rec["us"], bool(rec.get("warmup_run")),
                               rec.get("gpu_c"))
        run.log({"steps": table})
        art = wandb.Artifact(f"r93b-{args.stage}-raw", type="timing")
        for path in files:
            art.add_file(path)
        if args.summary:
            art.add_file(args.summary)
        run.log_artifact(art)

    print(f"WANDB_RUN_ID={run.id}")
    print(f"WANDB_RUN_URL={run.url}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
