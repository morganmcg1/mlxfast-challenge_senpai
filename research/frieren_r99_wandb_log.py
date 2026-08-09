#!/usr/bin/env python3
"""Publish the r99-A ring-depth / epilogue restoration study to W&B.

  python3 research/frieren_r99_wandb_log.py \
      --probe-log research/r99-logs/frieren-r99a-probe-20sweeps.log.gz \
      --e2e-log   research/r99-logs/frieren-r99a-e2e-paired.log

One run per probe variant carries the whole threadgroup ladder as a step
series keyed on K, so the dose-response is plottable. One summary run carries
the headline K = 16 estimates, the end-to-end paired legs, and the go/no-go
verdict.
"""
import argparse
import gzip
import io
import json
import os
import re
import sys

import wandb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frieren_r99_agg import POOL_US_M4, POOL_US_M5, SCORE_PER_US, ROW, stats

PROJECT = os.environ.get("WANDB_PROJECT", "mlxfast-maple")
ENTITY = os.environ.get("WANDB_ENTITY", "wandb-applied-ai-team")
TAGS = ["maple", "student:maple-frieren", "pr539", "r99-a", "ring-depth"]
HEADLINE_K = 16

# Pools are per kernel, not per study: the full-attention twin has its own,
# smaller pool, so pricing its contrast through the sliding pool would inflate
# it by 2.8x. Its M5 column uses the M4->M5 ratio the sliding pool shows.
POOLS = {"sliding": (POOL_US_M4, POOL_US_M5), "full": (229.7, 104.8)}

# Provenance of each end-to-end block, keyed on its log basename so the
# replicate index published here is derived from the files actually passed and
# cannot drift from the write-up. Block A ran first; the re-run was to widen
# the driver's jq projection (76c0f48), which changed reporting only.
E2E_BLOCKS = {
    "frieren-r99a-e2e-paired-rep2.log": {
        "block": "A", "job": "e2c5423b-8919-4a99-8014-7a88d02b600d",
        "started_utc": "2026-08-09T14:44", "ended_utc": "2026-08-09T15:14",
        "wall_s": 1831, "driver_rev": "a8eda15"},
    "frieren-r99a-e2e-paired.log": {
        "block": "B", "job": "f55275e6-8a17-4347-82c3-d1249c1fcada",
        "started_utc": "2026-08-09T15:25", "ended_utc": "2026-08-09T15:58",
        "wall_s": 1998, "driver_rev": "76c0f48"},
}

# leg name -> (ring depth, float4 merge epilogue, submitted byte delta, kernel)
VARIANTS = {
    "null": (2, False, 0, "sliding"),
    "d4": (4, False, 4086, "sliding"),
    "epi": (2, True, -227, "sliding"),
    "d4epi": (4, True, 3859, "sliding"),
    "d8": (8, False, 12250, "sliding"),
    "full": (2, True, -227, "full"),
}


def open_maybe_gz(path):
    if path.endswith(".gz"):
        return io.TextIOWrapper(gzip.open(path, "rb"))
    return open(path)


def parse_probe(path):
    """-> {(leg, order, K): [pct per sweep]}"""
    out = {}
    leg = None
    with open_maybe_gz(path) as fh:
        for line in fh:
            if line.startswith("@@LEG"):
                _, leg, order = line.split()
            elif line.startswith("@@END"):
                leg = None
            elif leg:
                m = ROW.match(line)
                if m:
                    out.setdefault((leg, order, int(m.group(1))), []).append(
                        float(m.group(8)))
    return out


def contrasts(data):
    """-> {leg: {K: dict of paired statistics}}"""
    out = {}
    for (leg, order, k) in data:
        if order != "FWD":
            continue
        rev = data.get((leg, "REV", k))
        if not rev:
            continue
        p4, p5 = POOLS[VARIANTS.get(leg, (0, 0, 0, "sliding"))[3]]
        fm, fsd, fse, n = stats(data[(leg, "FWD", k)])
        rm, rsd, rse, _ = stats(rev)
        est = (fm - rm) / 2
        sem = (fse ** 2 + rse ** 2) ** 0.5 / 2
        out.setdefault(leg, {})[k] = {
            "est_pct": est, "sem_pct": sem, "t": est / sem if sem else float("nan"),
            "fwd_mean_pct": fm, "fwd_sd_pct": fsd, "rev_mean_pct": rm,
            "rev_sd_pct": rsd, "sweeps": n,
            "us_per_step_m4": -est / 100 * p4,
            "us_per_step_m5": -est / 100 * p5,
            "score_pct": -est / 100 * p5 * SCORE_PER_US,
        }
    return out


E2E_RUN = re.compile(r"^@@RUN sweep=(\d+) slot=(\d+) arm=(\w+) exit=(\d+)")


def parse_e2e(path, replicate=0):
    """-> [{replicate, sweep, order, slot, arm, ...score json fields}]"""
    rows, order, pending = [], None, None
    with open_maybe_gz(path) as fh:
        for line in fh:
            if line.startswith("@@ORDER"):
                order = line.split()[1]
            m = E2E_RUN.match(line)
            if m:
                pending = {"replicate": replicate,
                           "sweep": int(m.group(1)), "slot": int(m.group(2)),
                           "arm": m.group(3), "exit": int(m.group(4)),
                           "order": order}
                continue
            if pending and line.startswith("{"):
                try:
                    pending.update(json.loads(line))
                except json.JSONDecodeError:
                    pass
                rows.append(pending)
                pending = None
    return rows


def e2e_paired(rows, field="decode_spt"):
    """Order-corrected seconds/token, cand relative to base.

    Each leg here is already signed as cand-vs-base via the arm label, so a
    FWD sweep (base in slot 1) measures effect+slot_bias and a REV sweep
    (cand in slot 1) measures effect-slot_bias. The mean recovers the effect
    and the half-difference is the slot bias. This differs from the kernel
    probe, whose legs are raw slot2/slot1 ratios and therefore need
    (FWD-REV)/2 for the same quantity.

    Sweeps from independent replications are pooled per arm order rather than
    combined by inverse variance: with two sweeps per leg the per-run sem is
    itself a two-point estimate, and weighting by it lets one lucky leg
    dominate the answer.
    """
    by = {}
    for r in rows:
        if r.get(field):
            key = (r.get("replicate", 0), r["sweep"], r["order"])
            by.setdefault(key, {})[r["arm"]] = r[field]
    legs = {"FWD": [], "REV": []}
    for (_, _, order), arms in by.items():
        if "base" in arms and "cand" in arms:
            legs[order].append((arms["cand"] / arms["base"] - 1) * 100)
    if not legs["FWD"] or not legs["REV"]:
        return None
    fm, _, fse, fn = stats(legs["FWD"])
    rm, _, rse, rn = stats(legs["REV"])
    est = (fm + rm) / 2
    slot_bias = (fm - rm) / 2
    sem = (fse ** 2 + rse ** 2) ** 0.5 / 2
    return {"est_pct": est, "sem_pct": sem, "slot_bias_pct": slot_bias,
            "fwd_mean_pct": fm, "rev_mean_pct": rm, "fwd_n": fn, "rev_n": rn,
            "t": est / sem if sem else float("nan")}


def e2e_correctness(rows):
    """Golden-hash / exit census over every leg of every replication.

    ``passed_correctness`` is absent from the first block's legs: the driver
    only began emitting that field at 76c0f48, after that block had run. Those
    legs are censused as ``missing`` rather than silently counted as passing.
    """
    hashes = sorted({r["golden_hash"] for r in rows if r.get("golden_hash")})
    return {"runs": len(rows),
            "distinct_golden_hashes": len(hashes),
            "golden_hash": hashes[0] if len(hashes) == 1 else hashes,
            "nonzero_exits": sum(1 for r in rows if r.get("exit")),
            "failing_cases": sum(1 for r in rows
                                 if r.get("first_failing_case") is not None),
            "passed_correctness_true": sum(
                1 for r in rows if r.get("passed_correctness") is True),
            "passed_correctness_missing": sum(
                1 for r in rows if r.get("passed_correctness") is None)}


def init(name, job_type, config, notes=""):
    wandb_dir = os.environ.get("WANDB_DIR", "/tmp/r99/wandb")
    os.makedirs(wandb_dir, exist_ok=True)
    return wandb.init(dir=wandb_dir, entity=ENTITY, project=PROJECT, name=name,
                      notes=notes, job_type=job_type, tags=TAGS, config=config,
                      reinit=True)


def put(run, mapping):
    for k, v in mapping.items():
        run.summary[k] = v if isinstance(v, (int, float, bool)) else json.dumps(v)


COMMON = {
    "host": "m4pro-20core-48gb",
    "gpu_family": "applegpu_g16s",
    "ranked_host": "m5max-40core-128gb",
    "instrument": "nezuko_r98_ab_kernel_probe",
    "pool_us_per_step_m4": POOL_US_M4,
    "pool_us_per_step_m5": POOL_US_M5,
    "score_pct_per_us_m5": SCORE_PER_US,
    "base_sha": "c240616a4924285f44bbb2f7410802920351c7ff",
    "pr": 539,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe-log", required=True)
    ap.add_argument("--e2e-log", action="append", default=[],
                    help="repeat once per independent replication")
    ap.add_argument("--summary-only", action="store_true")
    args = ap.parse_args()

    ladder = contrasts(parse_probe(args.probe_log))
    e2e_rows = [r for i, p in enumerate(args.e2e_log)
                for r in parse_e2e(p, replicate=i)]
    blocks = {i: dict(E2E_BLOCKS.get(os.path.basename(p), {}), log=p,
                      replicate=i) for i, p in enumerate(args.e2e_log)}
    for i, blk in blocks.items():
        per = e2e_paired([r for r in e2e_rows if r["replicate"] == i])
        if per:
            blk.update({"est_pct": per["est_pct"], "sem_pct": per["sem_pct"],
                        "t": per["t"], "slot_bias_pct": per["slot_bias_pct"]})
    e2e = None
    if e2e_rows:
        e2e = dict(e2e_paired(e2e_rows),
                   replications=len(args.e2e_log),
                   blocks=list(blocks.values()),
                   **{"prefill_" + k: v
                      for k, v in e2e_paired(e2e_rows, "prefill_spt").items()},
                   **{"correctness_" + k: v
                      for k, v in e2e_correctness(e2e_rows).items()})
    ids = []

    if not args.summary_only:
        for leg, byk in ladder.items():
            depth, epi, dbytes, kern = VARIANTS.get(leg, (None, None, None, None))
            run = init("r99a-probe-%s" % leg, "kernel_probe",
                       dict(COMMON, variant=leg, ring_depth=depth,
                            float4_merge_epilogue=epi, submitted_bytes_delta=dbytes,
                            kernel=kern),
                       "r99-A probe ladder for variant %s" % leg)
            for k in sorted(byk):
                run.log(dict(byk[k], threadgroups=k,
                             tg_per_core=k / 20.0), step=k)
            head = byk.get(HEADLINE_K, {})
            put(run, {"headline_k": HEADLINE_K,
                      **{"k16_" + a: b for a, b in head.items()}})
            ids.append(run.id)
            run.finish()

    heads = {leg: byk.get(HEADLINE_K, {}) for leg, byk in ladder.items()}
    run = init("r99a-summary", "analysis",
               dict(COMMON, rungs_run="1,1b,1c,1e,full", rungs_declined="2,3",
                    receipts_spent=0, receipts_available=6,
                    shipped_variant="d4epi", shipped_bytes_delta=3859),
               "r99-A summary: 4-deep ring + float4 epilogue restoration")
    put(run, {
        "k16_est_pct_" + leg: h.get("est_pct") for leg, h in heads.items()})
    put(run, {
        "k16_score_pct_" + leg: h.get("score_pct") for leg, h in heads.items()})
    put(run, {
        "primary_metric": heads.get("d4epi", {}).get("est_pct"),
        "primary_metric_name": "kernel_paired_delta_pct_k16",
        "shipped_score_pct": heads.get("d4epi", {}).get("score_pct"),
        "go_bar_score_pct": 0.61,
        "go_bar_us_per_step": 40.0,
        "verdict": "receipts_declined_merge_on_merit",
        "sigma_score_pct": 0.6172,
        "sigma_cand_dec_pct": 0.2939,
        "null_control_k16_est_pct": heads.get("null", {}).get("est_pct"),
        "additive_prediction_pct": (heads.get("d4", {}).get("est_pct", 0)
                                    + heads.get("epi", {}).get("est_pct", 0)),
        "ladder": {leg: {str(k): v["est_pct"] for k, v in byk.items()}
                   for leg, byk in ladder.items()},
        # Score pricing divides by a *census* pool, so every score_pct above is
        # an E = 1 upper bound; E is unmeasured for the attention family.
        "marginal_efficiency_E": "unmeasured",
        "score_pct_is_upper_bound": True,
        "m5_band_low_pct": 0.08,
        "m5_band_high_pct": 0.21,
        "census_cross_check_pct": 0.248,
        "census_cross_check_source": "pr541-revert-census-additive",
        "deficit_to_record_pct": 1.0498,
        "bytes_growth": 3859,
        "bytes_headroom_after": 12292,
    })
    if e2e:
        put(run, {"e2e_" + k: v for k, v in e2e.items()})
    ids.append(run.id)
    run.finish()

    print(json.dumps({"run_ids": ids, "entity": ENTITY, "project": PROJECT},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
