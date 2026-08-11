#!/usr/bin/env python3
"""Publish the R119-B grid-append shared+routed gate/up QMV campaign to W&B.

Estimators are imported from research/edward_r119b_stats.py so the run's numbers
cannot drift from the memo's numbers. Every per-step wall sample from every
worker process is logged, so the ABBA/BAAB sequence and any thermal drift are
inspectable in the UI.

Usage:
  python3 research/edward_r119b_wandb.py --out /tmp/r119b --prof /tmp/edward-r119b-prof
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess

import numpy as np
import wandb

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "r119b_stats", os.path.join(REPO, "research/edward_r119b_stats.py")
)
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

_bspec = importlib.util.spec_from_file_location(
    "r119b_busy_ci", os.path.join(REPO, "research/edward_r119b_busy_ci.py")
)
B = importlib.util.module_from_spec(_bspec)
_bspec.loader.exec_module(B)

# Assignment pricing fork (PR #712 section 4): measured M5 dispatch price
# 1.2382 us x 39 removed dispatches per step.
DISPATCH_PRICE_US = 1.2382
DISPATCHES_REMOVED = 39
FLOOR_US_PER_STEP = DISPATCH_PRICE_US * DISPATCHES_REMOVED  # 48.3
CEILING_US_PER_STEP = 105.0
# 0.75 decode weight applied to the relative decode gain.
SCORE_WEIGHT_DECODE = 0.75


def sh(cmd: list[str]) -> str:
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True).stdout.strip()


def per_run_medians(paths, pool=False):
    rows = S.load(paths)
    src_index = {t: i for i, t in enumerate(sorted({r[0] for r in rows}))}
    samples: dict = {}
    meta: dict = {}
    for tag, block, run, arm, step, ms in rows:
        if pool:
            i = src_index[tag]
            key = (i * 10000 + run)
            m = (i * 1000 + block, arm, tag)
        else:
            key = run
            m = (block, arm, tag)
        samples.setdefault(key, []).append(ms)
        meta[key] = m
    return samples, meta


def estimators(paths, base="C", cand="F", pool=False):
    samples, meta = per_run_medians(paths, pool=pool)
    runs = sorted(samples)
    med = {r: float(np.median(samples[r])) for r in runs}
    out: dict = {}

    b = np.array([med[r] for r in runs if meta[r][1] == base])
    c = np.array([med[r] for r in runs if meta[r][1] == cand])
    if b.size == 0 or c.size == 0:
        return out, samples, meta, med
    ref = float(b.mean())
    out["ref_ms"] = ref
    out["n_base"] = int(b.size)
    out["n_cand"] = int(c.size)

    blocks: dict = {}
    for r in runs:
        blocks.setdefault(meta[r][0], {}).setdefault(meta[r][1], []).append(med[r])
    d = np.array(
        [
            float(np.mean(v[base]) - np.mean(v[cand]))
            for _, v in sorted(blocks.items())
            if base in v and cand in v
        ]
    )
    if d.size >= 2:
        m, lo, hi, p, n = S.one_sample_ci(d)
        out["block"] = dict(delta_us=1000 * m, lo_us=1000 * lo, hi_us=1000 * hi, p=p, n=n)

    pairs = []
    for i in range(len(runs) - 1):
        r1, r2 = runs[i], runs[i + 1]
        if meta[r1][2] != meta[r2][2]:
            continue
        a1, a2 = meta[r1][1], meta[r2][1]
        if a1 == base and a2 == cand:
            pairs.append(med[r1] - med[r2])
        elif a1 == cand and a2 == base:
            pairs.append(med[r2] - med[r1])
    if len(pairs) >= 2:
        m, lo, hi, p, n = S.one_sample_ci(np.asarray(pairs))
        out["pair"] = dict(delta_us=1000 * m, lo_us=1000 * lo, hi_us=1000 * hi, p=p, n=n)

    if b.size >= 2 and c.size >= 2:
        diff, lo, hi, p, df = S.welch(b, c)
        out["welch"] = dict(
            delta_us=1000 * diff, lo_us=1000 * lo, hi_us=1000 * hi, p=p, n=df
        )

    for arm, arr in ((base, b), (cand, c)):
        pooled = np.concatenate([np.asarray(samples[r]) for r in runs if meta[r][1] == arm])
        lo98, hi98 = np.percentile(pooled, [1.0, 99.0])
        out[f"raw_{arm}"] = dict(
            samples=int(pooled.size),
            median_ms=float(np.median(pooled)),
            bimodality=S.sarle(pooled),
            bimodality_core98=S.sarle(pooled[(pooled >= lo98) & (pooled <= hi98)]),
            modes=S.mode_count(pooled),
        )
    return out, samples, meta, med


def grep1(path, pattern, cast=float):
    if not os.path.exists(path):
        return None
    m = re.search(pattern, open(path).read())
    return cast(m.group(1)) if m else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/r119b")
    ap.add_argument("--prof", default="/tmp/edward-r119b-prof")
    ap.add_argument("--correct", default="/tmp/r119b-correct")
    ap.add_argument("--name", default="r119b-gridappend-shared-routed-qmv")
    args = ap.parse_args()

    abba = os.path.join(args.out, "abba_raw.csv")
    baab = os.path.join(args.out, "baab_raw.csv")
    nc = os.path.join(args.out, "nc_raw.csv")

    run = wandb.init(
        entity="wandb-applied-ai-team",
        project="mlxfast-maple",
        name=args.name,
        job_type="decode-kernel-fusion",
        tags=["r119-b", "grid-append", "shared-expert", "routed-moe", "qmv", "maple-edward"],
        config={
            "assignment_id": "maple-r119-b-shared-routed-qmv-gridappend",
            "revision_id": "r119-b-rev1",
            "pr": 712,
            "branch": "maple-edward/r119-b-shared-routed-qmv-gridappend",
            "base_sha": "f8cb5c5be3a0480799088a8f7efd5808553dc20a",
            "commit": sh(["git", "rev-parse", "HEAD"]),
            "host": "Apple M4 Pro, 20 GPU cores, 48 GiB (low-memory profile)",
            "gpu_generation": 16,
            "nax_kernels_reachable": False,
            "env_switch": "DARKBLOOM_SHARED_ROUTED_QMV_FUSED",
            "kernel": "laguna_shared_routed_nvfp4_swiglu_qmv_top8keys_r1_bf16_v1",
            "guest_tiles": 256,
            "host_tiles": 2048,
            "threads_per_threadgroup": 64,
            "grid_threads": (256 + 8 * 256) * 64,
            "layers_fused": 39,
            "floor_us_per_step": FLOOR_US_PER_STEP,
            "ceiling_us_per_step": CEILING_US_PER_STEP,
            "m5_dispatch_price_us": DISPATCH_PRICE_US,
            "rank_axis": "end-to-end SPLIT=0 per-step decode wall",
        },
    )
    summary = {}

    # --- dispatch / occupancy / attribution from the GPU-profile probe -------
    for tag in ("s0_off", "s0_on", "s1_off", "s1_on"):
        log = os.path.join(args.prof, f"{tag}.log")
        for key, pat in (
            ("wall_ms", r"per steady step: wall=([0-9.]+) ms"),
            ("busy_sum_ms", r"gpu_busy_sum=([0-9.]+) ms"),
            ("busy_union_ms", r"gpu_busy_union=([0-9.]+) ms"),
            ("gap_ms", r"gap=([0-9.]+) ms"),
            ("cbs", r"cbs=([0-9.]+)"),
            ("dispatches", r"dispatches=([0-9.]+)"),
        ):
            v = grep1(log, pat)
            if v is not None:
                summary[f"probe/{tag}/{key}"] = v

    d_off = summary.get("probe/s0_off/dispatches")
    d_on = summary.get("probe/s0_on/dispatches")
    if d_off and d_on:
        summary["probe/dispatch_delta_per_step"] = d_on - d_off
    b_off = summary.get("probe/s0_off/busy_sum_ms")
    b_on = summary.get("probe/s0_on/busy_sum_ms")
    if b_off and b_on:
        summary["probe/split0_busy_delta_us_per_step"] = 1000 * (b_off - b_on)
        if d_off and d_on:
            summary["probe/split0_marginal_dispatch_price_us"] = 1000 * (b_off - b_on) / (
                d_off - d_on
            )
    g_off = summary.get("probe/s0_off/gap_ms")
    g_on = summary.get("probe/s0_on/gap_ms")
    if g_off and g_on:
        summary["probe/split0_gap_delta_us_per_step"] = 1000 * (g_on - g_off)
    w_off = summary.get("probe/s0_off/wall_ms")
    w_on = summary.get("probe/s0_on/wall_ms")
    if w_off and w_on:
        summary["probe/split0_wall_delta_us_per_step"] = 1000 * (w_on - w_off)

    # SPLIT=1 per-kernel attribution: the separately measured host-only leg.
    def kern(tag, needle):
        log = os.path.join(args.prof, f"{tag}.log")
        if not os.path.exists(log):
            return None, None
        for line in open(log):
            if needle in line:
                f = line.split()
                return float(f[0]), float(f[3])  # us/step, us/call
        return None, None

    host_step, host_call = kern("s1_off", "routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2")
    guest_step, guest_call = kern("s1_off", "shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1")
    fused_step, fused_call = kern("s1_on", "shared_routed_nvfp4_swiglu_qmv_top8keys_r1_bf16_v1")
    if host_call and guest_call and fused_call:
        summary["split1/host_only_us_per_call"] = host_call
        summary["split1/guest_only_us_per_call"] = guest_call
        summary["split1/fused_us_per_call"] = fused_call
        summary["split1/host_leg_growth_us_per_call"] = fused_call - host_call
        summary["split1/isolated_saving_us_per_call"] = guest_call - (fused_call - host_call)
        summary["split1/delta_us_per_step"] = host_step + guest_step - fused_step

    # Welch intervals on per-step GPU busy time, both split regimes.
    for label, off, on in (
        ("split0", "s0_off", "s0_on"),
        ("split1", "s1_off", "s1_on"),
    ):
        pa = os.path.join(args.prof, f"{off}.err")
        pb = os.path.join(args.prof, f"{on}.err")
        if not (os.path.exists(pa) and os.path.exists(pb)):
            continue
        a, amode = B.steady_modal(pa, drop_lo=1)
        b, bmode = B.steady_modal(pb, drop_lo=1)
        if len(a) < 8 or len(b) < 8:
            continue
        w = B.welch(a, b, 0.95)
        summary[f"busy_ci/{label}/n_per_arm"] = min(len(a), len(b))
        summary[f"busy_ci/{label}/baseline_us"] = w["baseline_mean"]
        summary[f"busy_ci/{label}/candidate_us"] = w["candidate_mean"]
        summary[f"busy_ci/{label}/delta_us"] = w["delta"]
        summary[f"busy_ci/{label}/lo_us"] = w["lo"]
        summary[f"busy_ci/{label}/hi_us"] = w["hi"]
        # busy_ci deltas are candidate-minus-baseline; campaign deltas are
        # baseline-minus-candidate. saving_us is positive-is-faster everywhere.
        summary[f"busy_ci/{label}/saving_us"] = -w["delta"]
        summary[f"busy_ci/{label}/saving_lo_us"] = -w["hi"]
        summary[f"busy_ci/{label}/saving_hi_us"] = -w["lo"]
        summary[f"busy_ci/{label}/p"] = w["p"]
        summary[f"busy_ci/{label}/excludes_zero"] = bool(w["lo"] * w["hi"] > 0)
        summary[f"busy_ci/{label}/dispatches_baseline"] = amode
        summary[f"busy_ci/{label}/dispatches_candidate"] = bmode
        if amode != bmode:
            n_removed = amode - bmode
            summary[f"busy_ci/{label}/price_per_dispatch_us"] = -w["delta"] / n_removed
            summary[f"busy_ci/{label}/price_lo_us"] = -w["hi"] / n_removed
            summary[f"busy_ci/{label}/price_hi_us"] = -w["lo"] / n_removed

    # --- ranked end-to-end campaign ----------------------------------------
    tbl = wandb.Table(columns=["order", "block", "run", "arm", "n", "median_ms", "mean_ms"])
    for label, path in (("abba", abba), ("baab", baab), ("nc", nc)):
        if not os.path.exists(path):
            continue
        samples, meta = per_run_medians([path])
        for r in sorted(samples):
            x = np.asarray(samples[r])
            tbl.add_data(label, meta[r][0], r, meta[r][1], int(x.size), float(np.median(x)),
                         float(x.mean()))
            for i, v in enumerate(x):
                run.log({f"step_ms/{label}": float(v), f"arm_code/{label}":
                         {"C": 0, "F": 1, "N": 2}[meta[r][1]], "sample_index": i,
                         "run_index": r})
    run.log({"per_run_medians": tbl})

    campaigns = {
        "abba": ([abba], "C", "F", False),
        "baab": ([baab], "C", "F", False),
        "pooled": ([abba, baab], "C", "F", True),
        "negative_control": ([nc], "C", "N", False),
    }
    verdicts = {}
    for name, (paths, base, cand, pool) in campaigns.items():
        if not all(os.path.exists(p) for p in paths):
            continue
        est, _, _, _ = estimators(paths, base, cand, pool)
        ref_us = 1000 * est.get("ref_ms", float("nan"))
        for key in ("block", "pair", "welch"):
            if key not in est:
                continue
            e = est[key]
            summary[f"{name}/{key}/delta_us"] = e["delta_us"]
            summary[f"{name}/{key}/ci_lo_us"] = e["lo_us"]
            summary[f"{name}/{key}/ci_hi_us"] = e["hi_us"]
            summary[f"{name}/{key}/p"] = e["p"]
            summary[f"{name}/{key}/n"] = e["n"]
            summary[f"{name}/{key}/excludes_zero"] = bool(e["lo_us"] * e["hi_us"] > 0)
            summary[f"{name}/{key}/rel_pct"] = 100 * e["delta_us"] / ref_us
            summary[f"{name}/{key}/score_pct"] = (
                SCORE_WEIGHT_DECODE * 100 * e["delta_us"] / ref_us
            )
        for arm in (base, cand):
            k = f"raw_{arm}"
            if k in est:
                summary[f"{name}/raw_{arm}/samples"] = est[k]["samples"]
                summary[f"{name}/raw_{arm}/median_ms"] = est[k]["median_ms"]
                summary[f"{name}/raw_{arm}/bimodality"] = est[k]["bimodality"]
                summary[f"{name}/raw_{arm}/bimodality_core98"] = est[k]["bimodality_core98"]
                summary[f"{name}/raw_{arm}/modes"] = est[k]["modes"]
                summary[f"{name}/raw_{arm}/suspect_bimodal"] = bool(
                    est[k]["bimodality"] > 0.555 and est[k]["modes"] >= 2
                )
        summary[f"{name}/ref_us"] = ref_us
        summary[f"{name}/n_base"] = est.get("n_base")
        summary[f"{name}/n_cand"] = est.get("n_cand")
        verdicts[name] = all(
            summary.get(f"{name}/{k}/excludes_zero") for k in ("block", "pair", "welch")
        )

    for name, v in verdicts.items():
        summary[f"{name}/all_three_exclude_zero"] = v

    # Pricing fork verdict against the assignment's floor and ceiling.
    pooled_delta = summary.get("pooled/block/delta_us")
    if pooled_delta is not None:
        summary["fork/pooled_block_delta_us"] = pooled_delta
        summary["fork/vs_floor_us"] = pooled_delta - FLOOR_US_PER_STEP
        summary["fork/vs_ceiling_us"] = pooled_delta - CEILING_US_PER_STEP
        if pooled_delta >= CEILING_US_PER_STEP:
            verdict = "confirms_new_lever"
        elif pooled_delta >= FLOOR_US_PER_STEP:
            verdict = "between_dispatch_floor_and_ceiling"
        else:
            verdict = "below_dispatch_floor_negative"
        summary["fork/verdict"] = verdict

    for gate in (0, 1):
        sc = os.path.join(args.correct, f"score_{gate}.json")
        if not os.path.exists(sc):
            continue
        m = json.load(open(sc)).get("metrics", {})
        for k in ("decode_seconds_per_token", "prefill_seconds_per_token",
                  "decode_speedup", "prefill_speedup", "passed_correctness",
                  "max_abs_diff", "golden_hash", "checked_steps", "num_layers"):
            summary[f"local_iterate/gate{gate}/{k}"] = m.get(k)
    off = summary.get("local_iterate/gate0/prefill_seconds_per_token")
    on = summary.get("local_iterate/gate1/prefill_seconds_per_token")
    if isinstance(off, float) and isinstance(on, float) and off > 0:
        summary["local_iterate/prefill_regression_pct"] = 100.0 * (on - off) / off
    off = summary.get("local_iterate/gate0/decode_seconds_per_token")
    on = summary.get("local_iterate/gate1/decode_seconds_per_token")
    if isinstance(off, float) and isinstance(on, float) and off > 0:
        summary["local_iterate/decode_delta_pct"] = 100.0 * (on - off) / off

    for gate, fname in ((1, "equiv_on.log"), (0, "equiv_off.log")):
        path = os.path.join(args.correct, fname)
        if not os.path.exists(path):
            continue
        text = open(path, errors="replace").read()
        for key, pat in (("exact_steps", r"EQUIVALENCE_EXACT_STEPS=(\d+)"),
                         ("exit", r"EQUIVALENCE_EXIT=(\d+)")):
            mm = re.search(pat, text)
            if mm:
                summary[f"equivalence/gate{gate}/{key}"] = int(mm.group(1))
        summary[f"equivalence/gate{gate}/tests_executed"] = len(
            re.findall(r"Test lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled\(\) started", text))
        steps = re.findall(
            r'"label" : "([^"]+)",\s*\n\s*"maximumAbsoluteLogitError" : ([0-9.e-]+),'
            r'\s*\n\s*"meanAbsoluteLogitError" : ([0-9.e-]+),'
            r'\s*\n\s*"runtimeToken" : (\d+),\s*\n\s*"upstreamToken" : (\d+)', text)
        exact_decode = sum(1 for s in steps if s[0].startswith("decode") and float(s[1]) == 0.0)
        summary[f"equivalence/gate{gate}/decode_steps_exact"] = exact_decode
        summary[f"equivalence/gate{gate}/token_divergences"] = sum(
            1 for s in steps if s[3] != s[4])
        for s in steps:
            if s[0] == "prefill":
                summary[f"equivalence/gate{gate}/prefill_max_abs_logit_error"] = float(s[1])
                summary[f"equivalence/gate{gate}/prefill_mean_abs_logit_error"] = float(s[2])
    if ("equivalence/gate0/prefill_max_abs_logit_error" in summary
            and "equivalence/gate1/prefill_max_abs_logit_error" in summary):
        summary["equivalence/prefill_error_reproduces_on_base"] = (
            summary["equivalence/gate0/prefill_max_abs_logit_error"]
            == summary["equivalence/gate1/prefill_max_abs_logit_error"])

    run.summary.update(summary)
    for k in sorted(summary):
        print(f"{k}\t{summary[k]}")
    print(f"\nW&B run: {run.url}\nrun id: {run.id}")
    run.finish()


if __name__ == "__main__":
    main()
