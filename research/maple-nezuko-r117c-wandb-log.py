#!/usr/bin/env python3
"""Log the R117-C Stage-1 o_proj geometry ladder to W&B.

Publishes ONE run in wandb-applied-ai-team/mlxfast-maple carrying the complete
raw evidence for the amendment-14 design:

    arms      G4 = DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP=4  (shipped default value
                   supplied through the env route -> BYTE-IDENTICAL to C, and
                   therefore the negative control the advisor required)
              R2 = DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP=2  (candidate)
              C  = no env var at all                     (ungated baseline)

    primary   R2 - G4, paired on the block, both arms gated, so any cost of the
              env-invocation route itself cancels exactly.
    control   C  - G4, which must contain zero if the instrument is honest.

Every number is from the local M4 Pro host via ./benchmark.sh --local-submit
(1023 scored decode steps, end-to-end wall). No official receipt is spent.

Usage:  research/maple-nezuko-r117c-wandb-log.py ROWS.tsv [ROWS2.tsv ...]
Env:    WANDB_NAME / WANDB_NOTES optional overrides
        B=20000 bootstrap resamples, SEED=117
"""
import os
import random
import sys

import wandb

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
PCT_CS_PER_US = 0.015228   # % of cs bought by 1 M5 us/step
K_ALPHA = 0.4369           # M4 -> M5 transfer, bytes-priced (the pessimistic one)


def median(xs):
    s = sorted(xs)
    n = len(s)
    if not n:
        return float("nan")
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def boot_ci(D, B, seed):
    rng = random.Random(seed)
    n = len(D)
    out = []
    for _ in range(B):
        out.append(median([D[rng.randrange(n)] for _ in range(n)]))
    out.sort()
    return out[int(0.025 * (B - 1))], out[int(0.975 * (B - 1))]


def main():
    paths = sys.argv[1:]
    if not paths:
        print("usage: maple-nezuko-r117c-wandb-log.py ROWS.tsv [...]")
        return 2
    B = int(os.environ.get("B", "20000"))
    seed = int(os.environ.get("SEED", "117"))

    rows = []
    for p in paths:
        with open(p) as fh:
            head = fh.readline().rstrip("\n").split("\t")
            for line in fh:
                if line.strip():
                    rows.append(dict(zip(head, line.rstrip("\n").split("\t"))))

    arms, tab, pos = [], {}, {}
    for r in rows:
        if r["arm"] not in arms:
            arms.append(r["arm"])
        # Block identity must carry the session: two ladders both number their
        # blocks from 1, and pairing across sessions would be a silent lie.
        b = (r.get("session", ""), int(r["block"]))
        tab.setdefault(b, {})[r["arm"]] = float(r["decode_s_per_token"]) * 1e6
        pos.setdefault(b, {})[r["arm"]] = int(r["pos"])
    ref = os.environ.get("REF_ARM") or arms[0]
    if ref not in arms:
        raise SystemExit(f"REF_ARM={ref!r} not among arms {arms}")

    n_fail = sum(1 for r in rows if r.get("passed") != "true")
    goldens = sorted({r["golden"] for r in rows if r.get("golden")})
    head_sha = rows[0].get("head", "")
    session = rows[0].get("session", "")

    run = wandb.init(
        entity=ENTITY, project=PROJECT,
        name=os.environ.get("WANDB_NAME", f"nezuko-r117c-oproj-ladder-{session}"),
        notes=os.environ.get(
            "WANDB_NOTES",
            "R117-C stage 1: o_proj rowsPerSimdgroup ladder, amendment 14. "
            "Primary contrast R2-G4 (both env-gated); byte-identical negative "
            "control C-G4. benchmark.sh --local-submit, blocked and interleaved."),
        tags=["r117", "nezuko", "oproj-geometry", "local-submit", "paired"],
        config={
            "instrument": "research/maple-nezuko-r107j-certify.sh",
            "mode": "--local-submit",
            "decode_steps": 1023,
            "host": "M4-Pro-20core",
            "arms": arms,
            "reference_arm": ref,
            "n_blocks": len(tab),
            "n_runs": len(rows),
            "head_sha": head_sha,
            "session": session,
            "bootstrap_B": B,
            "bootstrap_seed": seed,
        },
    )

    tbl = wandb.Table(columns=["idx", "block", "pos", "arm", "gates",
                               "decode_us_per_token", "prefill_us_per_token",
                               "passed", "golden"])
    for r in rows:
        tbl.add_data(int(r["idx"]), int(r["block"]), int(r["pos"]), r["arm"],
                     r["gates"], float(r["decode_s_per_token"]) * 1e6,
                     float(r["prefill_s_per_token"]) * 1e6,
                     r["passed"], r["golden"][:16])
    run.log({"runs": tbl})

    summary = {
        "correctness/failed_runs": n_fail,
        "correctness/distinct_golden_hashes": len(goldens),
        "correctness/golden": goldens[0][:32] if goldens else "",
    }
    for a in arms:
        vals = [tab[b][a] for b in sorted(tab) if a in tab[b]]
        if vals:
            summary[f"level/{a}_us_per_token_mean"] = sum(vals) / len(vals)
            summary[f"level/{a}_us_per_token_median"] = median(vals)
            summary[f"level/{a}_n"] = len(vals)

    for a in arms:
        if a == ref:
            continue
        blocks = sorted(b for b in tab if a in tab[b] and ref in tab[b])
        D = [tab[b][a] - tab[b][ref] for b in blocks]
        if not D:
            continue
        med = median(D)
        lo, hi = boot_ci(D, B, seed)
        key = f"{a}_minus_{ref}"
        refmean = sum(tab[b][ref] for b in blocks) / len(blocks)
        summary.update({
            f"contrast/{key}/median_us": med,
            f"contrast/{key}/mean_us": sum(D) / len(D),
            f"contrast/{key}/ci95_lo_us": lo,
            f"contrast/{key}/ci95_hi_us": hi,
            f"contrast/{key}/covers_zero": bool(lo <= 0 <= hi),
            f"contrast/{key}/n_blocks": len(D),
            f"contrast/{key}/pct_decode_wall": 100.0 * med / refmean,
            f"contrast/{key}/pct_cs_alpha": med * K_ALPHA * PCT_CS_PER_US,
        })

    run.summary.update(summary)
    for k in sorted(summary):
        print(f"{k} = {summary[k]}")
    run.finish()
    print(f"RUN_ID {run.id}")
    print(f"RUN_URL {run.url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
