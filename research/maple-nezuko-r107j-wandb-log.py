#!/usr/bin/env python3
"""Publish the R107-J certification-instrument characterisation to W&B.

R107-J deliverable: characterise the paired `./benchmark.sh --local-submit`
decode instrument so another student can *certify* a 0.25-0.35 % summed effect
under rule 105.5 without reading my code.

What this run carries
  * the A/A null: arms A and A' are the SAME binary with the SAME (empty) gate
    set, blocked and interleaved.  The estimand is identically zero, so the
    measured spread IS the instrument's paired sd and the CI must cover zero.
  * the power curve derived from that measured sd: blocks -> dof -> t -> CI95
    half-width, in M4 us/step, in relative decode %, and in % of `cs`.
  * any additional paired table handed in on the command line (e.g. the
    positive control), logged with its own prefix.

Every number is local M4 Pro (host: Apple M4 Pro, 20 GPU cores, 48 GiB).
No official receipt is spent.  Rule 86: --local-iterate is never evidence and
never appears here; the certify harness refuses to emit it.

Usage:
  research/maple-nezuko-r107j-wandb-log.py <aa-null.tsv> [<other.tsv> ...]
Env:
  WANDB_NAME / WANDB_NOTES / WANDB_MODE optional overrides.
"""

import csv
import math
import os
import pathlib
import sys

import wandb

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"

# ---- campaign constants (R107 ledger) --------------------------------------
K_ALPHA = 0.4369          # M4->M5 transfer factor, bytes-priced
K_BETA = 0.5000           # M4->M5 transfer factor, latency-priced
PCS_PER_M5_US = 0.015228  # % of `cs` bought per M5 us/step
BAR_PCS = 0.40            # rule 105.6 slot bar, in % of `cs`
# 0.40 % of cs = 26.27 M5 us/step = 60.1 M4 us/step (alpha) = 52.5 (beta).
BAR_M4_ALPHA = BAR_PCS / (K_ALPHA * PCS_PER_M5_US)
BAR_M4_BETA = BAR_PCS / (K_BETA * PCS_PER_M5_US)
# rule 105.10: L3 de-biased is 0.1966 % of cs, so a second summand must cover
# the residual 0.2034 % = 30.6 M4 us/step at alpha.  That is the effect size
# the power curve has to resolve.
RESIDUAL_PCS = 0.2034
RESIDUAL_M4_ALPHA = RESIDUAL_PCS / (K_ALPHA * PCS_PER_M5_US)

T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
        7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
        13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101,
        19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064,
        25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}
T80 = {1: 1.376, 2: 1.061, 3: 0.978, 4: 0.941, 5: 0.920, 6: 0.906,
       7: 0.896, 8: 0.889, 9: 0.883, 10: 0.879, 11: 0.876, 12: 0.873,
       13: 0.870, 14: 0.868, 15: 0.866, 16: 0.865, 17: 0.863, 18: 0.862,
       19: 0.861, 20: 0.860, 21: 0.859, 22: 0.858, 23: 0.858, 24: 0.857,
       25: 0.856, 26: 0.856, 27: 0.855, 28: 0.855, 29: 0.854, 30: 0.854}


def tq(tbl, dof):
    if dof <= 0:
        return float("nan")
    if dof in tbl:
        return tbl[dof]
    hi = max(tbl)
    return tbl[hi] if dof > hi else tbl[min(tbl)]


def mean(xs):
    return sum(xs) / len(xs)


def sd(xs):
    if len(xs) < 2:
        return float("nan")
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def fnum(s):
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return None if v != v else v


def read_rows(path):
    with open(path, newline="") as fh:
        return [r for r in csv.DictReader(fh, delimiter="\t")]


def us(row, key):
    """The harness records SECONDS per token; every number here is us/step."""
    v = fnum(row.get(key))
    return None if v is None else v * 1e6


def paired(rows, s_key="decode_s_per_token"):
    """Reference arm = arm of the lowest idx.  Returns (ref, stats, diffs)."""
    order, byblock = [], {}
    for r in rows:
        arm = r["arm"]
        if arm not in order:
            order.append(arm)
        byblock.setdefault(r["block"], {})[arm] = r
    ref = order[0]
    out, diffs = {}, {}
    for arm in order[1:]:
        d = []
        for blk in sorted(byblock, key=lambda b: int(b)):
            cell = byblock[blk]
            if arm in cell and ref in cell:
                a, b = us(cell[ref], s_key), us(cell[arm], s_key)
                if a is not None and b is not None:
                    d.append((int(blk), b - a))
        if len(d) < 2:
            continue
        vals = [x for _, x in d]
        n, m, s = len(vals), mean([x for _, x in d]), sd(vals)
        dof = n - 1
        t = tq(T975, dof)
        hw = t * s / math.sqrt(n)
        out[arm] = {
            "n_pairs": n, "dof": dof, "t975": t,
            "delta_us_per_step": m, "paired_sd_us": s,
            "sem_us": s / math.sqrt(n), "ci95_hw_us": hw,
            "ci95_low_us": m - hw, "ci95_high_us": m + hw,
            "covers_zero": bool((m - hw) <= 0.0 <= (m + hw)),
            "delta_pct_cs_alpha": m * K_ALPHA * PCS_PER_M5_US,
            "delta_pct_cs_beta": m * K_BETA * PCS_PER_M5_US,
        }
        diffs[arm] = d
    return ref, out, diffs


def power_curve(sd_us, base_us):
    """blocks -> CI95 half-width, in us/step, relative decode %, % of cs."""
    rows = []
    for nb in list(range(3, 21)) + [24, 30]:
        dof = nb - 1
        t = tq(T975, dof)
        hw = t * sd_us / math.sqrt(nb)
        rows.append({
            "blocks": nb, "runs": 2 * nb, "dof": dof, "t975": t,
            "hw_us_per_step": hw,
            "hw_rel_decode_pct": 100.0 * hw / base_us,
            "hw_pct_cs_alpha": hw * K_ALPHA * PCS_PER_M5_US,
            "hw_pct_cs_beta": hw * K_BETA * PCS_PER_M5_US,
            "wall_hours": 2 * nb * 198.0 / 3600.0,
        })
    return rows


def blocks_needed(sd_us, target_pcs, k=K_ALPHA):
    """Blocks so that (a) hw < effect, and (b) 80 % power at alpha=0.05."""
    eff = target_pcs / (k * PCS_PER_M5_US)
    res = pwr = None
    for nb in range(3, 4001):
        dof = nb - 1
        se = sd_us / math.sqrt(nb)
        if res is None and tq(T975, dof) * se < eff:
            res = nb
        if pwr is None and (tq(T975, dof) + tq(T80, dof)) * se < eff:
            pwr = nb
        if res and pwr:
            break
    return eff, res, pwr


def log_table(rows, prefix):
    cols = ["session", "idx", "block", "pos", "arm", "gates",
            "decode_s_per_token", "prefill_s_per_token", "passed",
            "golden", "kernels", "wall_s"]
    tbl = wandb.Table(columns=cols + ["decode_us_per_token"])
    for r in rows:
        tbl.add_data(*([r.get(c, "") for c in cols] +
                       [us(r, "decode_s_per_token")]))
    return {"%s/runs" % prefix: tbl}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    aa_path = sys.argv[1]
    aa = read_rows(aa_path)
    ref, stats, diffs = paired(aa)
    if not stats:
        sys.exit("no usable pairs in %s" % aa_path)
    arm = sorted(stats)[0]
    st = stats[arm]
    base = mean([us(r, "decode_s_per_token") for r in aa
                 if r["arm"] == ref and us(r, "decode_s_per_token")])

    run = wandb.init(
        entity=ENTITY, project=PROJECT,
        name=os.environ.get("WANDB_NAME", "maple-nezuko-r107j-instrument"),
        notes=os.environ.get(
            "WANDB_NOTES",
            "R107-J: A/A null + power curve for the paired --local-submit "
            "decode instrument.  Local M4 Pro only, no receipt spent."),
        tags=["maple-nezuko", "r107-j", "instrument", "aa-null",
              "power-curve", "local-submit", "no-receipt"],
        config={
            "host": "Apple M4 Pro / 20 GPU cores / 48 GiB",
            "epoch": "R107",
            "measurement": "census (1023 decode steps, ./benchmark.sh "
                           "--local-submit)",
            "mode": "--local-submit",
            "arms": "A vs A' (identical binary, identical empty gate set)",
            "blocks": st["n_pairs"],
            "runs": len(aa),
            "reference_arm": ref,
            "k_alpha": K_ALPHA, "k_beta": K_BETA,
            "pct_cs_per_m5_us": PCS_PER_M5_US,
            "bar_pct_cs": BAR_PCS,
            "bar_m4_us_alpha": BAR_M4_ALPHA,
            "bar_m4_us_beta": BAR_M4_BETA,
            "residual_summand_pct_cs": RESIDUAL_PCS,
            "residual_summand_m4_us_alpha": RESIDUAL_M4_ALPHA,
            "head": aa[0].get("head", ""),
        })

    summary = {"aa/%s" % k: v for k, v in st.items()}
    summary["aa/reference_mean_us_per_step"] = base
    summary["aa/paired_cv_pct"] = 100.0 * st["paired_sd_us"] / base
    summary["aa/null_holds"] = st["covers_zero"]
    # prefill neutrality (rule 105.4): the paired design must not be charging
    # or crediting prefill to either arm.
    _, pst, _ = paired(aa, s_key="prefill_s_per_token")
    if arm in pst:
        summary["aa/prefill_delta_us_per_token"] = \
            pst[arm]["delta_us_per_step"]
        summary["aa/prefill_ci95_hw_us"] = pst[arm]["ci95_hw_us"]
        summary["aa/prefill_covers_zero"] = pst[arm]["covers_zero"]
    summary["aa/correctness_failures"] = sum(
        1 for r in aa if str(r.get("passed", "")).lower() not in ("true", ""))
    summary["aa/distinct_golden_hashes"] = len(
        {r.get("golden", "") for r in aa if r.get("golden", "")})
    summary["aa/distinct_kernel_sets"] = len(
        {r.get("kernels", "") for r in aa if r.get("kernels", "")})

    pc = power_curve(st["paired_sd_us"], base)
    pctbl = wandb.Table(columns=["blocks", "runs", "dof", "t975",
                                 "hw_us_per_step", "hw_rel_decode_pct",
                                 "hw_pct_cs_alpha", "hw_pct_cs_beta",
                                 "wall_hours"])
    for r in pc:
        pctbl.add_data(*[r[c] for c in pctbl.columns])
    for r in pc:
        if r["blocks"] in (6, 10, 12, 20):
            summary["power/hw_us_at_%d_blocks" % r["blocks"]] = \
                r["hw_us_per_step"]
            summary["power/hw_pct_cs_alpha_at_%d_blocks" % r["blocks"]] = \
                r["hw_pct_cs_alpha"]

    bntbl = wandb.Table(columns=["target_pct_cs", "effect_m4_us_alpha",
                                 "blocks_ci_excludes_zero",
                                 "blocks_80pct_power", "runs_80pct_power",
                                 "wall_hours_80pct_power"])
    for tgt in (0.40, 0.30, 0.25, 0.20):
        eff, res, pwr = blocks_needed(st["paired_sd_us"], tgt)
        bntbl.add_data(tgt, eff, res, pwr, 2 * pwr if pwr else None,
                       (2 * pwr * 198.0 / 3600.0) if pwr else None)
        summary["power/blocks_for_%.2fpct_cs" % tgt] = res
        summary["power/blocks_80pct_for_%.2fpct_cs" % tgt] = pwr
    eff, res, pwr = blocks_needed(st["paired_sd_us"], RESIDUAL_PCS)
    summary["power/blocks_for_residual_summand"] = res
    summary["power/blocks_80pct_for_residual_summand"] = pwr

    payload = {"power/curve": pctbl, "power/blocks_needed": bntbl}
    payload.update(log_table(aa, "aa"))

    dtbl = wandb.Table(columns=["block", "diff_us_per_step"])
    for blk, d in diffs[arm]:
        dtbl.add_data(blk, d)
    payload["aa/paired_diffs"] = dtbl

    # Optional extra paired tables (positive control, candidate arms, ...).
    for p in sys.argv[2:]:
        rows = read_rows(p)
        stem = pathlib.Path(p).stem.replace("r107j-", "")
        pref = "extra_" + stem.replace("-", "_")
        r2, s2, _ = paired(rows)
        for a2, v2 in s2.items():
            for k2, val in v2.items():
                summary["%s/%s_vs_%s/%s" % (pref, a2, r2, k2)] = val
        payload.update(log_table(rows, pref))

    run.summary.update(summary)
    run.log(payload)

    print("A/A null: arm=%s vs ref=%s  n=%d dof=%d" %
          (arm, ref, st["n_pairs"], st["dof"]))
    print("  reference mean      = %.3f us/step" % base)
    print("  MEASURED paired sd  = %.3f us/step (cv %.4f %% of decode)" %
          (st["paired_sd_us"], 100.0 * st["paired_sd_us"] / base))
    print("  delta               = %+.3f us/step" % st["delta_us_per_step"])
    print("  CI95                = [%+.3f, %+.3f]  covers_zero=%s" %
          (st["ci95_low_us"], st["ci95_high_us"], st["covers_zero"]))
    print("  blocks for 0.2034 %% of cs residual: %s (CI) / %s (80 %% power)"
          % (res, pwr))
    print("W&B run url:", run.url)
    run.finish()


if __name__ == "__main__":
    main()
