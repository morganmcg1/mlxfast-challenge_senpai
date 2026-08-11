#!/usr/bin/env python3
"""r109-A cadence screen analysis: paired within-block contrasts, argmax debiasing,
and W&B logging of every arm.

Usage:
  python3 research/frieren_r109_analyze.py [results.jsonl ...] [--tag NAME] [--no-wandb]
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np

DECODE_REF = 0.013890
PREFILL_REF = 0.0003845
CONTROL_DEFAULT = {"ctl", "pctl"}


def ns(decode_spt: float, prefill_spt: float) -> float:
    return (DECODE_REF / decode_spt) ** 0.75 * (PREFILL_REF / prefill_spt) ** 0.25


def expected_max(m: int, draws: int = 200000, seed: int = 0) -> float:
    if m <= 1:
        return 0.0
    rng = np.random.default_rng(seed)
    return float(rng.standard_normal((draws, m)).max(axis=1).mean())


def load(paths: list[str]) -> list[dict]:
    rows = []
    for p in paths:
        with open(p) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                if r.get("decode_spt") and r.get("prefill_spt"):
                    r["ns"] = ns(r["decode_spt"], r["prefill_spt"])
                    rows.append(r)
                else:
                    print(f"  skipped (no metrics): {r}", file=sys.stderr)
    return rows


def main() -> int:
    args = [a for a in sys.argv[1:]]
    use_wandb = "--no-wandb" not in args
    args = [a for a in args if a != "--no-wandb"]
    tag = "r109a-cadence"
    if "--tag" in args:
        i = args.index("--tag")
        tag = args[i + 1]
        del args[i : i + 2]
    control_arg = None
    if "--control" in args:
        i = args.index("--control")
        control_arg = args[i + 1]
        del args[i : i + 2]
    paths = args or ["research/r109-cadence/results.jsonl"]

    rows = load(paths)
    if not rows:
        print("no rows", file=sys.stderr)
        return 1

    names = (control_arg,) if control_arg else ("ctl", "pctl")
    control = next(a for a in names if any(r["arm"] == a for r in rows))
    by_block: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        by_block[r["block"]][r["arm"]] = r

    arms = sorted({r["arm"] for r in rows})
    deltas: dict[str, list[float]] = defaultdict(list)
    d_dec: dict[str, list[float]] = defaultdict(list)
    d_pre: dict[str, list[float]] = defaultdict(list)
    d_dec_us: dict[str, list[float]] = defaultdict(list)
    blocks_used = []
    for b in sorted(by_block):
        blk = by_block[b]
        if control not in blk:
            continue
        blocks_used.append(b)
        c = blk[control]
        for arm, r in blk.items():
            deltas[arm].append(r["ns"] / c["ns"] - 1.0)
            d_dec[arm].append(c["decode_spt"] / r["decode_spt"] - 1.0)
            d_pre[arm].append(c["prefill_spt"] / r["prefill_spt"] - 1.0)
            d_dec_us[arm].append((c["decode_spt"] - r["decode_spt"]) * 1e6)

    table = []
    for arm in arms:
        v = np.array(deltas[arm])
        u = np.array(d_dec_us[arm])
        w = np.array(d_dec[arm])
        sem_v = v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else float("nan")
        sem_w = w.std(ddof=1) / np.sqrt(len(w)) if len(w) > 1 else float("nan")
        hashes = sorted(
            {r.get("golden_hash") for r in rows if r["arm"] == arm and r.get("golden_hash")}
        )
        table.append(
            dict(
                arm=arm,
                value=next(r["value"] for r in rows if r["arm"] == arm),
                n=len(v),
                mean_ns_pct=100 * v.mean(),
                sd_ns_pct=100 * v.std(ddof=1) if len(v) > 1 else float("nan"),
                t_ns=float(v.mean() / sem_v) if len(v) > 1 and sem_v else float("nan"),
                decode_saving_us=float(u.mean()),
                decode_saving_us_sem=float(u.std(ddof=1) / np.sqrt(len(u)))
                if len(u) > 1
                else float("nan"),
                golden_hashes=hashes,
                mean_decode_pct=100 * np.mean(d_dec[arm]),
                sd_decode_pct=100 * w.std(ddof=1) if len(w) > 1 else float("nan"),
                t_decode=float(w.mean() / sem_w) if len(w) > 1 and sem_w else float("nan"),
                mean_prefill_pct=100 * np.mean(d_pre[arm]),
                mean_decode_spt=float(
                    np.mean([r["decode_spt"] for r in rows if r["arm"] == arm])
                ),
                mean_prefill_spt=float(
                    np.mean([r["prefill_spt"] for r in rows if r["arm"] == arm])
                ),
                mean_ns=float(np.mean([r["ns"] for r in rows if r["arm"] == arm])),
                all_correct=all(
                    bool(r.get("passed_correctness")) for r in rows if r["arm"] == arm
                ),
            )
        )

    cand = [t for t in table if t["arm"] != control]
    nb = len(blocks_used)
    pooled = [
        np.array(deltas[t["arm"]]) - np.mean(deltas[t["arm"]])
        for t in cand
        if len(deltas[t["arm"]]) > 1
    ]
    if pooled:
        resid = np.concatenate(pooled)
        dof = sum(len(deltas[t["arm"]]) - 1 for t in cand if len(deltas[t["arm"]]) > 1)
        sigma = float(np.sqrt((resid**2).sum() / max(dof, 1)))
    else:
        sigma = float("nan")
    sem = sigma / np.sqrt(max(nb, 1))

    mat = [deltas[t["arm"]] for t in cand if len(deltas[t["arm"]]) == nb]
    rho = 0.5
    if nb >= 3 and len(mat) >= 2:
        cm = np.corrcoef(np.array(mat))
        off = cm[np.triu_indices_from(cm, k=1)]
        off = off[np.isfinite(off)]
        if off.size:
            rho = float(np.clip(off.mean(), 0.0, 0.95))

    m = len(cand)
    emax = expected_max(m)
    bias = sem * np.sqrt(max(1 - rho, 0.0)) * emax

    cand_sorted = sorted(cand, key=lambda t: -t["mean_ns_pct"])
    best = cand_sorted[0]

    print(f"control={control}  blocks={blocks_used}  arms={m}")
    print(
        f"pooled sigma_contrast={100*sigma:.4f}%  sem={100*sem:.4f}%  rho={rho:.3f}  "
        f"E[max_{m}]={emax:.3f}  argmax_bias={100*bias:.4f}%"
    )
    print(f"pricing: 0.0070 %score per M4 wall us/step; bar to beat crown = 54 us/step")
    print(
        f"{'arm':8s} {'value':32s} {'n':>2s} {'ns d%':>8s} {'sd%':>7s} {'t':>6s} "
        f"{'DEC d%':>8s} {'sd%':>7s} {'t_dec':>6s} "
        f"{'dec us/step':>12s} {'+-sem':>7s} {'pre d%':>8s} ok"
    )
    for t in sorted(table, key=lambda t: -t["mean_decode_pct"]):
        print(
            f"{t['arm']:8s} {t['value']:32s} {t['n']:2d} {t['mean_ns_pct']:8.3f} "
            f"{t['sd_ns_pct']:7.3f} {t['t_ns']:6.2f} "
            f"{t['mean_decode_pct']:8.3f} {t['sd_decode_pct']:7.3f} {t['t_decode']:6.2f} "
            f"{t['decode_saving_us']:12.1f} "
            f"{t['decode_saving_us_sem']:7.1f} {t['mean_prefill_pct']:8.3f} "
            f"{'Y' if t['all_correct'] else 'N'}"
        )

    all_hashes = sorted({h for t in table for h in t["golden_hashes"]})
    print(
        f"\ngolden_hash: {len(all_hashes)} distinct across all arms "
        f"({'BIT-EXACT across arms' if len(all_hashes) == 1 else 'DIVERGENCE - inspect'})"
    )
    for h in all_hashes:
        print(f"  {h}  arms={[t['arm'] for t in table if h in t['golden_hashes']]}")
    print(
        f"\nraw argmax: {best['arm']} {best['mean_ns_pct']:+.3f}%  ->  "
        f"debiased {best['mean_ns_pct'] - 100*bias:+.3f}%"
    )

    summary = dict(
        control=control,
        n_blocks=nb,
        n_arms=m,
        sigma_contrast_pct=100 * sigma,
        sem_pct=100 * sem,
        rho=rho,
        expected_max=emax,
        argmax_bias_pct=100 * bias,
        raw_argmax_arm=best["arm"],
        raw_argmax_ns_pct=best["mean_ns_pct"],
        debiased_argmax_ns_pct=best["mean_ns_pct"] - 100 * bias,
        raw_argmax_decode_us=best["decode_saving_us"],
        all_arms_correct=all(t["all_correct"] for t in table),
        distinct_golden_hashes=len(all_hashes),
    )
    out = dict(summary=summary, arms=table, blocks=blocks_used)
    os.makedirs("research/r109-cadence", exist_ok=True)
    with open(f"research/r109-cadence/analysis-{tag}.json", "w") as fh:
        json.dump(out, fh, indent=2)

    if use_wandb:
        import wandb

        run = wandb.init(
            entity="wandb-applied-ai-team",
            project="mlxfast-maple",
            name=tag,
            job_type="cadence-screen",
            config=dict(
                assignment="maple-r109-a-decode-commit-cadence",
                pr=681,
                host="M4 Pro 48GB",
                harness="benchmark.sh --local-iterate",
                knob=os.environ.get("R109_KNOB", "DARKBLOOM_DECODE_ASYNC_STAGE"),
                control=control,
                decode_ref=DECODE_REF,
                prefill_ref=PREFILL_REF,
                blocks=nb,
            ),
        )
        cols = list(table[0].keys())
        wandb.log(
            {
                "arms": wandb.Table(
                    columns=cols, data=[[t[c] for c in cols] for t in table]
                )
            }
        )
        runs_cols = [
            "arm",
            "value",
            "block",
            "slot",
            "decode_spt",
            "prefill_spt",
            "ns",
            "passed_correctness",
            "wall_secs",
        ]
        wandb.log(
            {
                "runs": wandb.Table(
                    columns=runs_cols,
                    data=[[r.get(c) for c in runs_cols] for r in rows],
                )
            }
        )
        for t in table:
            for k in ("mean_ns_pct", "mean_decode_pct", "mean_prefill_pct", "mean_ns"):
                wandb.summary[f"arm/{t['arm']}/{k}"] = t[k]
        for k, v in summary.items():
            wandb.summary[k] = v
        print(f"\nW&B: {run.url}  id={run.id}")
        run.finish()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
