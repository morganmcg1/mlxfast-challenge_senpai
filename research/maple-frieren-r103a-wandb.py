#!/usr/bin/env python3
"""Research-only (PR #571, R103-A): publish the rung-1/rung-2 record to W&B.

Reads the artefacts the drivers already wrote -- analysis.json for the two-arm
rung 1, analysis-multi.json for the three-arm rung 2, the provenance files and
the token-parity checksum lists -- and logs them as one run in
wandb-applied-ai-team/mlxfast-maple. Nothing is recomputed here; if a number is
in W&B it came from the preregistered analyzer, so the run can be audited
against the on-disk artefacts.

Usage:
  python3 research/maple-frieren-r103a-wandb.py RUNG1_DIR [RUNG2_DIR]

When RUNG2_DIR is given, the three-arm block is the primary result and rung 1
enters as an independent replication of the composed A->C contrast.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import wandb

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"

# The M5 quantity this experiment was originally pointed at, derived in doc 1.1
# from the two official receipts. Advisor feedback fb2 RETRACTED it as a target
# (two-receipt sigma 17.1-20.2 => z ~ 1.0-1.2), so it is logged as historical
# context, not as a bar.
M5_TARGET_US = 20.149
M5_TARGET_PCT = 0.4865
M5_HEADLINE_US = 19.405
M5_TARGET_RETRACTED = True

# fb3's acceptance model: candidate-score delta in percent per us/step of T,
# and the us/step at which effort starts paying.
CS_PCT_PER_US = 1.0 / 65.7
CS_EFFORT_THRESHOLD_US = 32.8

# Three legs are read from one block, so intervals quoted jointly are widened.
BONFERRONI_3 = 1.2214

LEG_MECHANISM = {
    "A->B": "#565 sliding-attention K/V software pipeline 2-way -> 4-way",
    "B->C": "#558 / R3 router weight-prefetch peel (pf0 -> pf1)",
    "A->C": "both, composed",
}


def sh(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return ""


def kv_file(path: Path) -> dict[str, str]:
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                if k.strip().isidentifier():
                    out[k.strip()] = v.strip()
    return out


def flat_paired(prefix: str, p: dict) -> dict:
    keep = ("k", "mean", "sd", "half_width", "lo", "hi", "pos", "neg")
    return {f"{prefix}/{k}": p[k] for k in keep if k in p}


def distinct_checksums(path: Path) -> int:
    if not path.exists():
        return -1
    return len({ln.split()[0] for ln in path.read_text().split("\n") if ln.strip()})


def log_rung2(run, m: dict, a: dict) -> dict:
    """Summarise the three-arm block: levels, both contrast estimators, the
    drift nulls, the preregistered triggers, and the fb3 acceptance sensitivity.
    """
    s: dict = {
        "rung2/precision_worst_half_width_us": m["precision"]["worst_half_width_m4"],
        "rung2/precision_target_us": m["precision"]["target"],
        "rung2/precision_pass": m["precision"]["pass"],
        "rung2/n2_fires": m["n2_fires"],
        "rung2/n5_fires": m["n5_fires"],
    }

    med = m["stats"]["median"]
    for arm, lvl in med["levels"].items():
        s[f"rung2/level/{arm}_us_per_step"] = lvl
    step_us = med["levels"]["A"]

    for leg, c in med["cycle_contrasts"].items():
        s.update(flat_paired(f"rung2/cycle/{leg}", c))
        s[f"rung2/cycle/{leg}/bonferroni_half_width"] = \
            c["half_width"] * BONFERRONI_3
        s[f"rung2/cycle/{leg}/bonferroni_excludes_zero"] = \
            abs(c["mean"]) > c["half_width"] * BONFERRONI_3
        s[f"rung2/cycle/{leg}/pct_of_step"] = 100.0 * c["mean"] / step_us
        s[f"rung2/cycle/{leg}/cs_pct_fixed_overhead"] = c["mean"] * CS_PCT_PER_US
        s[f"rung2/cycle/{leg}/clears_effort_threshold"] = \
            abs(c["mean"]) >= CS_EFFORT_THRESHOLD_US
    for leg, c in med["contrasts"].items():
        s.update(flat_paired(f"rung2/perrep/{leg}", c))

    for key, n in med["nulls"].items():
        s.update(flat_paired(f"rung2/null/{key}", n))
        s[f"rung2/null/{key}/excludes_zero"] = n["lo"] * n["hi"] > 0

    # Independent replication check: rung 1 measured the composed A->C contrast
    # with a different design, so its agreement is evidence the block is real.
    # Standard errors are rebuilt from sd and k rather than from the half-widths,
    # because the two rungs have different degrees of freedom.
    ac = med["cycle_contrasts"]["A->C"]
    r1c = a["median"]["real"]
    se = ((r1c["sd"] ** 2 / r1c["k"]) + (ac["sd"] ** 2 / ac["k"])) ** 0.5
    s["rung2/replication/rung1_ac_us"] = r1c["mean"]
    s["rung2/replication/rung1_ac_half_width"] = r1c["half_width"]
    s["rung2/replication/difference_us"] = ac["mean"] - r1c["mean"]
    s["rung2/replication/difference_se_us"] = se
    s["rung2/replication/difference_in_sd"] = \
        abs(ac["mean"] - r1c["mean"]) / se

    tbl = wandb.Table(columns=["leg", "mechanism", "estimator", "k", "mean_us",
                               "half_width", "lo", "hi", "pos", "neg",
                               "pct_of_step", "cs_pct_fixed_overhead"])
    for est, block in (("cycle-blocked", med["cycle_contrasts"]),
                       ("per-repetition", med["contrasts"])):
        for leg, c in block.items():
            tbl.add_data(leg, LEG_MECHANISM[leg], est, c["k"], c["mean"],
                         c["half_width"], c["lo"], c["hi"], c["pos"], c["neg"],
                         100.0 * c["mean"] / step_us, c["mean"] * CS_PCT_PER_US)
    run.log({"rung2/contrasts": tbl})

    nulls = wandb.Table(columns=["cell", "arm", "separation", "k", "mean_us",
                                 "half_width", "lo", "hi", "excludes_zero"])
    for key, n in med["nulls"].items():
        nulls.add_data(key, n["arm"], n["separation"], n["k"], n["mean"],
                       n["half_width"], n["lo"], n["hi"], n["lo"] * n["hi"] > 0)
    run.log({"rung2/drift_nulls": nulls})

    robust = wandb.Table(columns=["statistic", "leg", "mean_us", "lo", "hi"])
    for stat, block in m["stats"].items():
        for leg, c in block["cycle_contrasts"].items():
            robust.add_data(stat, leg, c["mean"], c["lo"], c["hi"])
    run.log({"rung2/robustness_across_statistics": robust})

    return s


def main() -> None:
    r1 = Path(sys.argv[1])
    r2 = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    a = json.loads((r1 / "analysis.json").read_text())
    m = json.loads((r2 / "analysis-multi.json").read_text()) \
        if r2 is not None and (r2 / "analysis-multi.json").exists() else None

    prov = kv_file(r1 / "provenance.txt")
    prov0 = kv_file(Path("/tmp/maple-r103a/rung0-provenance.txt"))

    cks = r1 / "tokens.cksum"
    n_distinct = distinct_checksums(cks)

    config = {
        "assignment_id": "maple-r103-a-missing-microseconds-localize",
        "revision_id": "r103-a-rev1",
        "pr": 571,
        "branch": "maple-frieren/r103-missing-microseconds-localize",
        "base_sha": "0f6862d099252d40a807df30abfbbd7c9cd596ae",
        "old_sha": "30f752df890de58d9d98382505c95f2008591101",
        "code_sha": sh(["git", "rev-parse", "HEAD"]),
        "host": sh(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "host_mem_bytes": sh(["sysctl", "-n", "hw.memsize"]),
        "design": "4-slot position-matched ABBA (oldA old new oldB), "
                  "order reversed on odd reps",
        "warmup_reps_discarded": a["warmup_reps"],
        "pairs_analysed": len(a["analysed_reps"]),
        "position_multiset": a["position_multiset"],
        "decision_statistic": "median of steps 1..N-1",
        "m5_target_us_per_step": M5_TARGET_US,
        "m5_target_pct": M5_TARGET_PCT,
        "m5_headline_us_per_step": M5_HEADLINE_US,
        "m5_target_retracted_by_advisor": M5_TARGET_RETRACTED,
        "cs_pct_per_us_step": CS_PCT_PER_US,
        "cs_effort_threshold_us_step": CS_EFFORT_THRESHOLD_US,
        "digest_head": prov0.get("digest_head"),
        "digest_at_old": prov0.get("digest_at_old"),
        "digest_after_restore": prov0.get("digest_after_restore"),
        "rung1_head": prov.get("head"),
        "rung1_digest_before": prov.get("digest_before"),
        "rung1_digest_after": prov.get("digest_after"),
        "token_checksums_distinct": n_distinct,
        "rung2_run": m is not None,
    }
    if m is not None:
        prov2 = kv_file(r2 / "provenance.txt")
        config.update({
            "rung2_arms": m["arms"],
            "rung2_arm_definitions": {
                "A": "30f752df pre-#565 snapshot binary (router _rpg8_keys_v1)",
                "B": "0f6862d0 binary, DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0 "
                     "(router _rpg8_keys_v1, same kernel as A)",
                "C": "0f6862d0 binary, DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1 "
                     "(shipped default, router _rpg8_keys_v1_pf1)",
            },
            "rung2_leg_mechanisms": {
                "A->B": "#565 sliding-attention K/V software pipeline 2-way -> 4-way",
                "B->C": "#558 / R3 router weight-prefetch peel",
                "A->C": "both, composed",
            },
            "rung2_design": "3-arm rotated block, 3 rotation phases x 6 slots, "
                            "24 reps of which 21 analysed, 7 complete cycles",
            "rung2_reps_analysed": m["reps"],
            "rung2_warmup_reps_discarded": m["warmup"],
            "rung2_primary_estimator": m["primary_estimator"],
            "rung2_slot_layout": m["layout"],
            "rung2_token_checksums_distinct":
                distinct_checksums(r2 / "tokens.cksum"),
            "rung2_digest_before": prov2.get("digest_before"),
            "rung2_digest_after": prov2.get("digest_after"),
        })

    primary = "three-arm rotated block (rung 2)" if m is not None \
        else "paired ABBA (rung 1)"
    run = wandb.init(entity=ENTITY, project=PROJECT, config=config,
                     job_type="timing-census",
                     name="r103a-three-arm-m4" if m is not None
                          else "r103a-abba-m4-rung1",
                     tags=["r103", "r103-a", "maple-frieren", "pr571",
                           "measurement-only", "m4-pro"],
                     notes="R103-A: decomposing the claimed OLD->NEW decode "
                           "regression on M4 Pro into the #565 K/V pipeline leg "
                           "and the #558 router weight-prefetch leg. Primary: "
                           + primary + ". Rung 1 is the two-arm predecessor "
                           "with a byte-identical-code null arm.")

    summary: dict = {
        "rung1/verdict_code": a["verdict_code"],
        "rung1/verdict_text": a["verdict_text"],
    }
    for stat in ("median", "trimmed", "mean", "mean_first128"):
        if stat not in a:
            continue
        b = a[stat]
        summary.update(flat_paired(f"rung1/{stat}/real", b["real"]))
        summary.update(flat_paired(f"rung1/{stat}/null", b["null"]))
        summary[f"rung1/{stat}/old_level_us"] = b["old_level_us"]
        summary[f"rung1/{stat}/real_relative_pct"] = b["real_relative_pct"]
    for key, p in a.get("diagnostics", {}).items():
        summary.update(flat_paired(f"rung1/diag/{key}", p))

    # Per-repetition paired differences, so the run carries the raw evidence
    # for the interval rather than only its endpoints.
    for row in a["median"]["real"]["pairs"]:
        rep = row["rep"]
        null_rows = {q["rep"]: q for q in a["median"]["null"]["pairs"]}
        wandb.log({
            "rep": rep,
            "rung1/pair/real_new_minus_old_us": row["diff_us"],
            "rung1/pair/new_us": row["new"],
            "rung1/pair/old_us": row["old"],
            "rung1/pair/null_oldB_minus_oldA_us":
                null_rows.get(rep, {}).get("diff_us"),
        }, step=rep)

    if m is not None:
        summary.update(log_rung2(run, m, a))

    run.summary.update(summary)

    art = wandb.Artifact("r103a-evidence", type="measurement")
    for p in [r1 / "analysis.json", r1 / "provenance.txt", r1 / "index.tsv",
              r1 / "tokens.cksum", Path("/tmp/maple-r103a/rung0-provenance.txt"),
              Path("/tmp/maple-r103a/layout/layout.json")]:
        if p.exists():
            art.add_file(str(p), name=p.name if p.parent != r1
                         else f"rung1-{p.name}")
    if r2 is not None:
        for p in [r2 / "analysis-multi.json", r2 / "provenance.txt",
                  r2 / "index.tsv", r2 / "tokens.cksum",
                  r2 / "position-matched.txt"]:
            if p.exists():
                art.add_file(str(p), name=f"rung2-{p.name}")
    run.log_artifact(art)

    print(f"W&B run: {run.url}  id={run.id}")
    run.finish()


if __name__ == "__main__":
    main()
