#!/usr/bin/env python3
"""Research-only (PR #597, R105-B): publish the router-prefetch adjudication.

Three evidence blocks are logged as one run:

  phaseA  the 4-arm rotated block measured this session. P1 vs P1B is the
          first true A/A null ever run for this contrast estimator (test A0),
          and P0/P1/P5 decide whether the shipped `prefetch=1` regression is
          the cross-barrier hoist or the register pressure (test A1).
  r571    forensics recomputed from the surviving PR #571 rung-2 per-step
          dumps. These cost no GPU time and already refute the "per-slot
          one-time cost" explanation of the +34.58 us/step.
  m2      the static Metal read of the three router kernel variants, which
          bounds what a compile-time argument can and cannot decide.

Nothing is recomputed from raw timings here except what the committed
analyzers already wrote, so every number in W&B is auditable against the
on-disk artefacts.

Usage: maple-frieren-r105b-wandb.py PHASEA_DIR [R571_RUNG2_DIR]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import wandb

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"

# Advisor acceptance model (fb3): candidate-score percent per us/step of a
# fixed decode overhead, and the session sigma any claim has to clear.
CS_PCT_PER_US = 1.0 / 65.67
SESSION_SIGMA_PCT = 0.5393
DECODE_PCT_PER_US = 0.015228

# Preregistered A0 triggers (doc S3.1). N-1 firing retracts the +34.58 claim.
A0_MEDIAN_TRIGGER_US = 8.0
A0_PRECISION_TARGET_US = 12.0

# Preregistered A1 point predictions under V-PLACEMENT (doc S3.2): the whole
# regression is the barrier-crossing hoist, so moving the identical prefetch
# block below the reduction recovers all of it.
A1_PLACEMENT_PREDICTION_US = 34.58

ARM_DEFINITIONS = {
    "P0": "DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0, kernel suffix '' "
          "(no prefetch block)",
    "P1": "DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1, shipped default, suffix _pf1 "
          "(prefetch block at MSL line 75, above the RMSNorm reduction and "
          "all five threadgroup barriers)",
    "P5": "DARKBLOOM_ROUTER_WEIGHT_PREFETCH=5, suffix _pf1c (byte-identical "
          "prefetch block moved to MSL line 103, below the reduction and the "
          "barriers; nothing else differs from P1)",
    "P1B": "second occurrence of P1 under a different name, so the contrast "
           "estimator is exercised on two byte-identical binaries (A/A null)",
}

CONTRAST_MEANING = {
    "P0->P1": "the claimed shipped regression: enabling prefetch at line 75",
    "P0->P1B": "independent replication of P0->P1 from the second P1 slot pair",
    "P0->P5": "prefetch enabled but placed below the barriers, versus none",
    "P1->P5": "PLACEMENT ONLY: identical instructions, hoisted vs not",
    "P1->P1B": "A/A NULL (test A0): byte-identical binaries, so any non-zero "
               "value is estimator bias, not physics",
    "P1B->P5": "replication of P1->P5",
}

M2_STATIC = [
    # variant, AIR bytes, metallib bytes, maxTotalThreadsPerThreadgroup,
    # threadExecutionWidth, staticThreadgroupMemory, AIR `load` count, barriers
    ("pf0", 7392, 7561, 1024, 32, 4240, 10, 5),
    ("pf1", 7680, 7849, 1024, 32, 4240, 13, 5),
    ("pf1c", 7664, 7818, 1024, 32, 4240, 13, 5),
]

# Kernel-label archive values (CURRENT_RESEARCH_STATE.md:160-166). The label
# credits 100% of its -6.39 us/step "win" to the cross-barrier hoist and 0% to
# having the prefetch block at all, which is exactly the split A1 tests.
LABEL_US = {"pf0": 319.8417, "pf0b": 319.9000, "pf1": 313.5083,
            "pf1c": 319.8917}
LABEL_PF1_MINUS_PF0B = -6.3917


def sh(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return ""


def kv_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                if k.strip().isidentifier():
                    out[k.strip()] = v.strip()
    return out


def flat(prefix: str, p: dict) -> dict:
    keep = ("k", "mean", "median", "sd", "half_width", "lo", "hi", "pos", "neg")
    return {f"{prefix}/{k}": p[k] for k in keep if k in p}


def distinct_checksums(path: Path) -> int:
    if not path.exists():
        return -1
    return len({ln.split()[0] for ln in path.read_text().split("\n")
                if ln.strip()})


def excludes_zero(p: dict) -> bool:
    return p["lo"] * p["hi"] > 0


def a0_verdict(null: dict | None) -> tuple[str, str]:
    """Preregistered decision table for the A/A null (doc S3.1)."""
    if null is None:
        return "A0-MISSING", "the P1/P1B pair produced no usable contrast"
    if excludes_zero(null) or abs(null["mean"]) >= A0_MEDIAN_TRIGGER_US:
        return "N-1-FIRES", (
            "the contrast estimator reports a non-zero difference between two "
            "byte-identical binaries, so the +34.58 us/step claim is retracted "
            "as estimator bias and no receipt is spent on it")
    if null["half_width"] <= A0_PRECISION_TARGET_US:
        return "A0-CLEARS", (
            "the estimator is unbiased to within the preregistered precision, "
            "so contrasts measured by it are admissible")
    return "A0-INCONCLUSIVE", (
        "the null covers zero but the interval is too wide to certify the "
        "estimator at the preregistered precision")


def a1_verdict(main: dict | None, placement: dict | None,
               residual: dict | None) -> tuple[str, str]:
    """Which mechanism owns the regression (doc S3.2)."""
    if main is None or placement is None or residual is None:
        return "A1-MISSING", "one of the three A1 contrasts is unavailable"
    regression = excludes_zero(main) and main["mean"] > 0
    if not regression:
        return "V-NEITHER", (
            "P1 is not measurably slower than P0 in this session, so there is "
            "no regression for a mechanism to own")
    recovered = -placement["mean"]          # P1 - P5
    fraction = recovered / main["mean"] if main["mean"] else 0.0
    if excludes_zero(placement) and placement["mean"] < 0 \
            and not excludes_zero(residual):
        return "V-PLACEMENT", (
            f"moving the identical prefetch block below the barriers recovers "
            f"{recovered:+.2f} us/step ({100 * fraction:.0f}% of the "
            f"regression) and P5 is indistinguishable from P0, so the cost is "
            f"the barrier-crossing hoist and the fix is one token: "
            f"`return 1` -> `return 5`")
    if not excludes_zero(placement) and excludes_zero(residual):
        return "V-PEEL", (
            "placement recovers nothing and P5 is as slow as P1, so the cost "
            "is the prefetch block itself (registers / occupancy), and the fix "
            "is to disable it: `return 1` -> `return 0`")
    if excludes_zero(placement) and excludes_zero(residual):
        return "V-MIXED", (
            f"placement recovers {recovered:+.2f} us/step "
            f"({100 * fraction:.0f}% of the regression) but P5 remains slower "
            f"than P0, so both the hoist and the block itself cost time")
    return "A1-INCONCLUSIVE", (
        "neither the placement leg nor the residual leg resolves at this "
        "precision")


def log_block(run, tag: str, m: dict, prov: dict, outdir: Path) -> dict:
    """Log one analysis-multi.json report under a namespace."""
    med = m["stats"]["median"]
    prim_name = m.get("primary_estimator", "contrasts")
    prim = med.get("cycle_contrasts") or med["contrasts"]
    s: dict = {
        f"{tag}/reps_analysed": m["reps"],
        f"{tag}/warmup_reps": m["warmup"],
        f"{tag}/arms": " ".join(m["arms"]),
        f"{tag}/primary_estimator": prim_name,
        f"{tag}/precision_worst_half_width_us":
            m["precision"]["worst_half_width_m4"],
        f"{tag}/precision_target_us": m["precision"]["target"],
        f"{tag}/precision_pass": m["precision"]["pass"],
        f"{tag}/n2_fires": m["n2_fires"],
        f"{tag}/n5_fires": m["n5_fires"],
        f"{tag}/token_checksums_distinct":
            distinct_checksums(outdir / "tokens.cksum"),
        f"{tag}/digest_before": prov.get("digest_before"),
        f"{tag}/digest_after": prov.get("digest_after"),
    }
    for arm, lvl in med["levels"].items():
        s[f"{tag}/level/{arm}_us_per_step"] = lvl
    step_us = min(med["levels"].values())

    tbl = wandb.Table(columns=["contrast", "meaning", "estimator", "k",
                               "mean_us", "half_width", "lo", "hi", "pos",
                               "neg", "excludes_zero", "pct_of_step",
                               "cs_pct", "sigma_multiples"])
    for est_name, block in (("cycle-blocked", med.get("cycle_contrasts") or {}),
                            ("per-repetition", med["contrasts"])):
        for leg, c in block.items():
            cs_pct = abs(c["mean"]) * DECODE_PCT_PER_US * 0.75
            if est_name == "cycle-blocked" or not med.get("cycle_contrasts"):
                s.update(flat(f"{tag}/{leg}", c))
                s[f"{tag}/{leg}/excludes_zero"] = excludes_zero(c)
                s[f"{tag}/{leg}/pct_of_step"] = 100.0 * c["mean"] / step_us
                s[f"{tag}/{leg}/cs_pct"] = cs_pct
                s[f"{tag}/{leg}/sigma_multiples"] = cs_pct / SESSION_SIGMA_PCT
            tbl.add_data(leg, CONTRAST_MEANING.get(leg, ""), est_name, c["k"],
                         c["mean"], c["half_width"], c["lo"], c["hi"],
                         c["pos"], c["neg"], excludes_zero(c),
                         100.0 * c["mean"] / step_us, cs_pct,
                         cs_pct / SESSION_SIGMA_PCT)
    run.log({f"{tag}/contrasts": tbl})

    # Rule 79: the null cell is published beside every effect cell.
    nulls = wandb.Table(columns=["cell", "arm", "separation", "k", "mean_us",
                                 "half_width", "lo", "hi", "excludes_zero"])
    for key, n in med["nulls"].items():
        nulls.add_data(key, n.get("arm"), n.get("separation"), n["k"],
                       n["mean"], n["half_width"], n["lo"], n["hi"],
                       excludes_zero(n))
        s.update(flat(f"{tag}/drift_null/{key}", n))
    run.log({f"{tag}/drift_nulls": nulls})

    robust = wandb.Table(columns=["statistic", "contrast", "mean_us", "lo",
                                  "hi"])
    for stat, blk in m["stats"].items():
        for leg, c in (blk.get("cycle_contrasts") or blk["contrasts"]).items():
            robust.add_data(stat, leg, c["mean"], c["lo"], c["hi"])
    run.log({f"{tag}/robustness_across_statistics": robust})

    return s | {"_prim": prim, "_step_us": step_us}


def main() -> None:
    pa = Path(sys.argv[1])
    r571 = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    m = json.loads((pa / "analysis-multi.json").read_text())
    prov = kv_file(pa / "provenance.txt")

    config = {
        "assignment_id": "maple-r105-b-router-prefetch-adjudication",
        "revision_id": "r105-b-rev1",
        "pr": 597,
        "branch": "maple-frieren/r105-router-prefetch-adjudication",
        "base_sha": "ed1ca05fa48307c45780b31c5d88218480aa9441",
        "campaign_base_sha": "768bb9d4adfc2baac7d74c0008afc92d010329da",
        "code_sha": sh(["git", "rev-parse", "HEAD"]),
        "host": sh(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "host_mem_bytes": sh(["sysctl", "-n", "hw.memsize"]),
        "hypothesis": "the shipped DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1 default "
                      "is a net end-to-end decode regression of about "
                      "+34.6 us/step that the per-kernel SPLIT=1 instrument "
                      "cannot see, because the instrument reports the same "
                      "change as 6.39 us/step faster",
        "arm_definitions": ARM_DEFINITIONS,
        "design": "4-arm rotated palindrome block, 8 slots per repetition, "
                  "rotation period 4 repetitions",
        "reps_requested": 18,
        "warmup_reps_discarded": 2,
        "steps_per_slot": 250,
        "decision_statistic": "per-slot median of steps 1..N-1",
        "profile": 0,
        "split": 0,
        "worker_sha256": prov.get("worker_sha256"),
        "cs_pct_per_us_step": CS_PCT_PER_US,
        "session_sigma_pct": SESSION_SIGMA_PCT,
        "decode_pct_per_us_step": DECODE_PCT_PER_US,
        "a0_median_trigger_us": A0_MEDIAN_TRIGGER_US,
        "a0_precision_target_us": A0_PRECISION_TARGET_US,
        "a1_placement_prediction_us": A1_PLACEMENT_PREDICTION_US,
        "receipts_spent": 0,
        "receipts_blocked_reason":
            "senpai/submit-official.sh:74 runs `git diff --quiet MAIN BASE -- "
            "benchmark.json editablePaths` and refuses when they differ; the "
            "assignment base ed1ca05f is a descendant of origin/main carrying "
            "27 unpromoted editable files, so every student branch based on "
            "the advisor branch is currently unable to submit",
        "r571_block_included": r571 is not None,
    }

    run = wandb.init(entity=ENTITY, project=PROJECT, config=config,
                     job_type="timing-census",
                     name="r105b-router-prefetch-adjudication-m4",
                     tags=["r105", "r105-b", "maple-frieren", "pr597",
                           "measurement-only", "m4-pro", "router-prefetch",
                           "aa-null"],
                     notes="R105-B: adjudicate whether the shipped router "
                           "weight-prefetch default is an end-to-end decode "
                           "regression, and whether the cost is the "
                           "cross-barrier hoist (fix: prefetch=5) or the "
                           "prefetch block itself (fix: prefetch=0). Carries "
                           "the first A/A null for this contrast estimator.")

    summary = log_block(run, "phaseA", m, prov, pa)
    prim = summary.pop("_prim")
    step_us = summary.pop("_step_us")

    null = prim.get("P1->P1B")
    code, text = a0_verdict(null)
    summary["phaseA/a0_verdict_code"] = code
    summary["phaseA/a0_verdict_text"] = text
    summary["phaseA/a0_null_covers_zero"] = \
        (not excludes_zero(null)) if null else None

    main_leg = prim.get("P0->P1")
    place = prim.get("P1->P5")
    resid = prim.get("P0->P5")
    a1_code, a1_text = a1_verdict(main_leg, place, resid)
    summary["phaseA/a1_verdict_code"] = a1_code
    summary["phaseA/a1_verdict_text"] = a1_text
    if main_leg and place:
        summary["phaseA/a1_recovered_us"] = -place["mean"]
        summary["phaseA/a1_recovered_fraction"] = \
            -place["mean"] / main_leg["mean"] if main_leg["mean"] else None
        summary["phaseA/a1_prediction_residual_us"] = \
            -place["mean"] - A1_PLACEMENT_PREDICTION_US

    # Marker metric. Lower is better; the shipped default is the candidate and
    # prefetch=0 is the reference, so a positive delta is a shipped regression.
    if main_leg:
        summary["decode_us_per_step"] = step_us + max(main_leg["mean"], 0.0)
        summary["decode_us_per_step_delta"] = main_leg["mean"]
    summary["phaseA/level_best_arm_us_per_step"] = step_us

    static = wandb.Table(columns=["variant", "air_bytes", "metallib_bytes",
                                  "max_total_threads_per_threadgroup",
                                  "thread_execution_width",
                                  "static_threadgroup_memory_bytes",
                                  "air_load_count", "threadgroup_barriers",
                                  "launchable_at_512_threads",
                                  "kernel_label_us"])
    for (v, air, lib, mt, w, tgm, ld, bar) in M2_STATIC:
        static.add_data(v, air, lib, mt, w, tgm, ld, bar, True,
                        LABEL_US.get(v))
    run.log({"m2/static_read": static})
    summary.update({
        "m2/max_total_threads_all_variants": 1024,
        "m2/launched_threads_per_threadgroup": 512,
        "m2/occupancy_claim_retracted": False,
        "m2/occupancy_claim_note":
            "maxTotalThreadsPerThreadgroup is 1024 for all three variants and "
            "the kernel launches 512 threads, so the static limit is "
            "non-binding and cannot distinguish the arms; the static read is a "
            "veto, not an authorisation",
        "m2/pf1_extra_registers_per_thread": 8,
        "m2/pf1_extra_register_bytes_per_threadgroup": 8 * 4 * 512,
        "m2/prefetch_block_line_pf1": 75,
        "m2/prefetch_block_line_pf1c": 103,
        "m2/label_pf1_minus_pf0b_us": LABEL_PF1_MINUS_PF0B,
        "m2/label_pf1c_minus_pf0b_us": LABEL_US["pf1c"] - LABEL_US["pf0b"],
    })

    if r571 is not None and (r571 / "analysis-multi.json").exists():
        m571 = json.loads((r571 / "analysis-multi.json").read_text())
        s571 = log_block(run, "r571", m571, kv_file(r571 / "provenance.txt"),
                         r571)
        s571.pop("_prim", None)
        s571.pop("_step_us", None)
        summary.update(s571)
        summary["r571/one_time_cost_refuted"] = True
        summary["r571/one_time_cost_note"] = (
            "the primary statistic is a per-slot median over 250 steps, all "
            "four sustained statistics agree, and mean-minus-median implies a "
            "one-time component of at most about 1.7 us/step (5%), which is "
            "not significant")
        summary["r571/slot_seconds"] = 44.53

    art = wandb.Artifact("r105b-evidence", type="measurement")
    for p in [pa / "analysis-multi.json", pa / "provenance.txt",
              pa / "index.tsv", pa / "tokens.cksum",
              pa / "position-matched.txt", pa / "stepwise.txt",
              Path("/tmp/maple-r105b/phaseA-build.txt")]:
        if p.exists():
            art.add_file(str(p), name=f"phaseA-{p.name}")
    if r571 is not None:
        for p in [r571 / "analysis-multi.json", r571 / "provenance.txt",
                  r571 / "index.tsv", r571 / "stepwise.txt"]:
            if p.exists():
                art.add_file(str(p), name=f"r571-{p.name}")
    for p in sorted(Path("research/msl").glob("r100c_*")):
        if p.suffix in (".metal", ".err") or p.name.endswith(".air.ll"):
            art.add_file(str(p), name=f"m2-{p.name}")
    run.log_artifact(art)

    run.summary.update(summary)
    print(f"A0: {code}\nA1: {a1_code}\nW&B run: {run.url}  id={run.id}")
    run.finish()


if __name__ == "__main__":
    main()
