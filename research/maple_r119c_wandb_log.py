#!/usr/bin/env python3
"""Publish the R119-C load-balance-granularity measurement to W&B.

    python3 research/maple_r119c_wandb_log.py research/r119c-runs/atlas

One run per threadgroup arm carries that arm's per-replicate SPLIT=1 kernel
us/step series; one summary run carries the arm table, phi with its CI, the
untouched-neighbour negative control, and the decision branch.

Reads only artifacts produced by research/maple_r119c_atlas.sh; never re-times.
"""
import importlib.util
import os
import statistics
import sys

import wandb

_spec = importlib.util.spec_from_file_location(
    "r119c", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "maple_r119c_analyze.py"))
r119c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r119c)

PROJECT = os.environ.get("WANDB_PROJECT", "mlxfast-maple")
ENTITY = os.environ.get("WANDB_ENTITY", "wandb-applied-ai-team")
BASE_TAGS = ["maple", "student:maple-frieren", "pr714", "r119-c",
             "load-balance-granularity", "shared-expert", "decode"]
RESOLUTION_US = 0.655
# Worst-core rows under the static threadgroup -> core assignment, 512 rows on
# a 20-core host: ceil(512 / rows_per_tg / 20) * rows_per_tg.
WORST_CORE_ROWS = {64: 26, 128: 28, 256: 32}
IDEAL_ROWS = 512 / 20


def collect(outdir):
    per_arm = {}
    for path in sorted(__import__("glob").glob(
            os.path.join(outdir, "p*-tg*.log"))):
        tg = int(__import__("re").search(r"-tg(\d+)\.log$", path).group(1))
        rows, wall, busy, calls = r119c.parse_log(path)
        if wall is None:
            continue
        qmv = sum(v for k, v in rows.items() if r119c.ARM_ROW in k)
        ncall = sum(v for k, v in calls.items() if r119c.ARM_ROW in k)
        per_arm.setdefault(tg, []).append(
            dict(log=os.path.basename(path), qmv_us_per_step=qmv,
                 qmv_calls_per_step=ncall, wall_ms=wall, busy_ms=busy,
                 rows=rows))
    return per_arm


def main() -> int:
    outdir = sys.argv[1] if len(sys.argv) > 1 else "research/r119c-runs/atlas"
    per_arm = collect(outdir)
    if not per_arm:
        print("no atlas logs found")
        return 1
    arms = sorted(per_arm)

    # Common-mode normalization: every kernel other than the arm kernel is
    # untouched, so their in-run sum is a reference for slot speed.
    grand = statistics.mean(
        [sum(v for k, v in rec["rows"].items() if r119c.ARM_ROW not in k)
         for tg in arms for rec in per_arm[tg]])
    for tg in arms:
        for rec in per_arm[tg]:
            rec["ref_us_per_step"] = sum(
                v for k, v in rec["rows"].items() if r119c.ARM_ROW not in k)
            rec["qmv_us_per_step_norm"] = (
                rec["qmv_us_per_step"] * grand / rec["ref_us_per_step"])

    stats, nstats = {}, {}
    for tg in arms:
        stats[tg] = r119c.summarize(
            [r["qmv_us_per_step"] for r in per_arm[tg]])
        nstats[tg] = r119c.summarize(
            [r["qmv_us_per_step_norm"] for r in per_arm[tg]])
    base, nbase = stats[64][0], nstats[64][0]

    for tg in arms:
        mean, sd, sem, n = stats[tg]
        run = wandb.init(
            entity=ENTITY, project=PROJECT,
            name=f"r119c-tg{tg}", group="r119c-shared-qmv-tg-granularity",
            job_type="atlas-arm", tags=BASE_TAGS + [f"tg{tg}"],
            config=dict(
                threadgroup_threads=tg, simdgroups_per_threadgroup=tg // 32,
                rows_per_threadgroup=tg // 32,
                threadgroups=512 // (tg // 32), total_threads=16384,
                worst_core_rows=WORST_CORE_ROWS[tg], ideal_rows=IDEAL_ROWS,
                predicted_imbalance_vs_tg64=r119c.PREDICTED[tg],
                steps=200, split=1, host="m4-pro-20core",
                kernel_family="shared_nvfp4_swiglu_qmv_rows1_halved",
                dispatched_pipeline=sorted({
                    k for rec in per_arm[tg] for k in rec["rows"]
                    if r119c.ARM_ROW in k})),
            reinit=True)
        for i, rec in enumerate(per_arm[tg]):
            wandb.log(dict(replicate=i,
                           qmv_us_per_step=rec["qmv_us_per_step"],
                           qmv_us_per_step_norm=rec["qmv_us_per_step_norm"],
                           reference_us_per_step=rec["ref_us_per_step"],
                           qmv_calls_per_step=rec["qmv_calls_per_step"],
                           wall_ms_per_step=rec["wall_ms"],
                           gpu_busy_ms_per_step=rec["busy_ms"]), step=i)
        run.summary.update(dict(
            qmv_us_per_step_mean=mean, qmv_us_per_step_sd=sd,
            qmv_us_per_step_sem=sem, n_replicates=n,
            qmv_us_per_step_norm_mean=nstats[tg][0],
            qmv_us_per_step_norm_sd=nstats[tg][1],
            qmv_us_per_step_norm_sem=nstats[tg][2],
            delta_norm_vs_tg64_us=nstats[tg][0] - nbase,
            wall_ms_mean=statistics.mean(
                [r["wall_ms"] for r in per_arm[tg]]),
            busy_ms_mean=statistics.mean(
                [r["busy_ms"] for r in per_arm[tg]]),
            delta_vs_tg64_us=mean - base,
            delta_vs_tg64_pct=(mean - base) / base * 100.0))
        run.finish()

    # Summary run: phi and the negative control.
    def through_origin(key, ref):
        xs, ys = [], []
        for tg in arms:
            for rec in per_arm[tg]:
                xs.append(r119c.PREDICTED[tg] * ref)
                ys.append(rec[key] - ref)
        s = sum(x * y for x, y in zip(xs, ys)) / sum(x * x for x in xs)
        resid = [y - s * x for x, y in zip(xs, ys)]
        return s, (sum(r * r for r in resid) / (len(xs) - 1)
                   / sum(x * x for x in xs)) ** 0.5, len(xs)

    slope, se, n_runs = through_origin("qmv_us_per_step", base)
    nslope, nse, _ = through_origin("qmv_us_per_step_norm", nbase)

    common = None
    for tg in arms:
        names = set()
        for rec in per_arm[tg]:
            names |= {k for k in rec["rows"] if r119c.ARM_ROW not in k}
        common = names if common is None else (common & names)
    drifts = []
    for name in sorted(common):
        vals, ok = {}, True
        for tg in arms:
            v = [rec["rows"].get(name) for rec in per_arm[tg]]
            if any(x is None for x in v):
                ok = False
                break
            vals[tg] = statistics.mean(v)
        if ok:
            d = max(abs(vals[tg] - vals[64]) for tg in arms)
            drifts.append((d, name, vals, d / vals[64] * 100.0,
                           vals[128] > vals[64] < vals[256]
                           and vals[256] > vals[128]))
    drifts.sort(reverse=True)
    n_drift = sum(1 for d, *_ in drifts if d > RESOLUTION_US)
    n_monotone = sum(1 for *_, mono in drifts if mono)

    lo, hi = slope - 1.96 * se, slope + 1.96 * se
    nlo, nhi = nslope - 1.96 * nse, nslope + 1.96 * nse
    if nhi < 0.15:
        branch = "refuted: phi below the 0.15 prior ceiling"
    elif nlo > 0.85:
        branch = "confirmed: phi indistinguishable from 1"
    else:
        branch = "intermediate: advisor prices phi directly"

    run = wandb.init(
        entity=ENTITY, project=PROJECT, name="r119c-summary",
        group="r119c-shared-qmv-tg-granularity", job_type="summary",
        tags=BASE_TAGS + ["summary"],
        config=dict(steps=200, split=1, host="m4-pro-20core",
                    atlas_resolution_us=RESOLUTION_US,
                    law="L-LOAD-BALANCE-GRANULARITY"),
        reinit=True)
    table = wandb.Table(columns=[
        "arm_tg", "n", "qmv_us_per_step_mean", "sd", "sem",
        "delta_vs_tg64_us", "delta_pct", "predicted_if_phi1_us", "phi",
        "qmv_norm_mean", "delta_norm_us", "phi_norm"])
    for tg in arms:
        mean, sd, sem, n = stats[tg]
        pred = r119c.PREDICTED[tg] * base
        npred = r119c.PREDICTED[tg] * nbase
        table.add_data(tg, n, mean, sd, sem, mean - base,
                       (mean - base) / base * 100.0, pred,
                       (mean - base) / pred if pred else 0.0,
                       nstats[tg][0], nstats[tg][0] - nbase,
                       (nstats[tg][0] - nbase) / npred if npred else 0.0)
    ctl = wandb.Table(columns=["kernel", "max_abs_delta_us", "max_delta_pct",
                               "beyond_resolution", "monotone_in_arm"]
                      + [f"tg{tg}_us_per_step" for tg in arms])
    for d, name, vals, pct, mono in drifts:
        ctl.add_data(name, d, pct, bool(d > RESOLUTION_US), bool(mono),
                     *[vals[t] for t in arms])
    run.log(dict(arm_table=table, negative_control=ctl))
    summary = dict(
        phi=slope, phi_se=se, phi_ci_lo=lo, phi_ci_hi=hi,
        phi_norm=nslope, phi_norm_se=nse, phi_norm_ci_lo=nlo,
        phi_norm_ci_hi=nhi,
        decision_branch=branch, base_qmv_us_per_step=base,
        n_runs=n_runs, n_common_kernels=len(drifts),
        n_control_kernels_beyond_resolution=n_drift,
        n_control_kernels_monotone_in_arm=n_monotone,
        control_max_drift_us=drifts[0][0] if drifts else 0.0,
        control_max_drift_pct=max((p for *_, p, _ in drifts), default=0.0))
    for tg in arms:
        mean, sd, sem, n = stats[tg]
        pred = r119c.PREDICTED[tg] * base
        npred = r119c.PREDICTED[tg] * nbase
        summary[f"tg{tg}_qmv_us_per_step"] = mean
        summary[f"tg{tg}_delta_us"] = mean - base
        summary[f"tg{tg}_phi"] = (mean - base) / pred if pred else 0.0
        summary[f"tg{tg}_qmv_us_per_step_norm"] = nstats[tg][0]
        summary[f"tg{tg}_phi_norm"] = (
            (nstats[tg][0] - nbase) / npred if npred else 0.0)
    run.summary.update(summary)
    run.finish()
    print(f"phi={slope:+.3f} [{lo:+.3f}, {hi:+.3f}]  "
          f"phi_norm={nslope:+.3f} [{nlo:+.3f}, {nhi:+.3f}]  {branch}")
    print(f"control: {n_drift}/{len(drifts)} kernels beyond "
          f"+-{RESOLUTION_US} us/step, {n_monotone} monotone in arm")
    print(f"summary run: {run.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
