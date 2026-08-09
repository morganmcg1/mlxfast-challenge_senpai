#!/usr/bin/env python3
"""Log the PR #483 R91-A stage-1 input-norm ceiling session to W&B.

One run per stage. Every number is read back out of the analyser JSON so the
W&B run and the research report cannot drift. `--contrast` takes
`name=path.json` pairs produced by `maple_r88a_additivity.py --json-out`;
`--kern` takes the same for `maple_r85_arm_stats.py --json-out`.

  python3 research/maple_r91a_wandb.py --name r91a-stage1-ceiling \\
      --logdir /tmp/maple-r91a/nat \\
      --contrast base_vs_skipr=/tmp/maple-r91a/nat-skipr.json \\
      --contrast base_vs_skipc=/tmp/maple-r91a/nat-skipc.json \\
      --contrast null_base=/tmp/maple-r91a/nat-null-base.json
"""
import argparse
import glob
import json
import os
import re

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
PCT_PER_US_STEP = 0.015280
DIVERGE_RE = re.compile(r"teacher-forced greedy tokens: (\d+) divergences")
CBS_RE = re.compile(r"cbs=([\d.]+) dispatches=([\d.]+)")


def load(path):
    with open(path) as fh:
        return json.load(fh)


def slot_facts(logdir):
    digests, divergences, cbs, disp = {}, [], {}, {}
    for path in sorted(glob.glob(os.path.join(logdir, "[0-9]*.tokens"))):
        with open(path) as fh:
            digests.setdefault(fh.read(), []).append(os.path.basename(path))
    for path in sorted(glob.glob(os.path.join(logdir, "[0-9]*.log"))):
        arm = os.path.basename(path).rsplit("-", 1)[1][: -len(".log")]
        with open(path, errors="replace") as fh:
            text = fh.read()
        m = DIVERGE_RE.search(text)
        divergences.append(int(m.group(1)) if m else -1)
        c = CBS_RE.search(text)
        if c:
            cbs.setdefault(arm, set()).add(float(c.group(1)))
            disp.setdefault(arm, set()).add(float(c.group(2)))
    return {
        "distinct_token_streams": len(digests),
        "token_groups": [len(g) for g in digests.values()],
        "max_divergences": max(divergences) if divergences else -1,
        "cbs_per_step": {k: sorted(v) for k, v in cbs.items()},
        "dispatches_per_step": {k: sorted(v) for k, v in disp.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--group", default="r91-a-input-norm-fusion-price")
    ap.add_argument("--logdir", action="append", default=[])
    ap.add_argument("--contrast", action="append", default=[])
    ap.add_argument("--kern", action="append", default=[])
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    import wandb

    summary = {"pct_score_per_us_step": PCT_PER_US_STEP}
    config = {"stage": args.name, "pr": 483,
              "assignment": "maple-r91-a-input-norm-fusion-price"}

    for spec in args.logdir:
        tag, _, path = spec.partition("=")
        if not path:
            tag, path = "nat", spec
        summary[f"slots/{tag}"] = slot_facts(path)

    for spec in args.contrast:
        tag, _, path = spec.partition("=")
        blob = load(path)
        summary[f"{tag}/kind"] = blob["kind"]
        summary[f"{tag}/n_duplex"] = blob["n_duplex"]
        for metric, row in blob["metrics"].items():
            summary[f"{tag}/{metric}_us_step"] = row["us_step"]
            summary[f"{tag}/{metric}_ci_lo"] = row["ci"][0]
            summary[f"{tag}/{metric}_ci_hi"] = row["ci"][1]
            summary[f"{tag}/{metric}_sd_us_step"] = row["sd_us_step"]
            summary[f"{tag}/{metric}_base_us_step"] = row["base_us_step"]
            summary[f"{tag}/{metric}_score_pct"] = (
                -row["us_step"] * PCT_PER_US_STEP)

    for spec in args.kern:
        tag, _, path = spec.partition("=")
        blob = load(path)
        rows = []
        for label, row in blob["labels"].items():
            rows.append([label, row["base_us_step"], row["abs_us_step"],
                         row["abs_ci"][0], row["abs_ci"][1]])
        summary[f"{tag}/n_duplex"] = blob["n_duplex"]
        summary[f"{tag}/base_busy_us_step"] = blob["base_busy_us_step"]
        summary[f"{tag}/busy_abs_us_step"] = blob["busy_abs"]["us_step"]
        summary[f"{tag}/busy_abs_ci"] = blob["busy_abs"]["ci"]
        summary[f"{tag}/labels"] = wandb.Table(
            columns=["label", "base_us_step", "abs_us_step",
                     "abs_ci_lo", "abs_ci_hi"],
            data=sorted(rows, key=lambda r: r[2]))

    run = wandb.init(entity=ENTITY, project=PROJECT, name=args.name,
                     group=args.group, job_type="probe", config=config,
                     notes=args.notes)
    for key, value in summary.items():
        run.summary[key] = value
    print(run.url)
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
