#!/usr/bin/env python3
"""Log the r109-f paired TG=64 vs TG=256 A/B evidence to W&B.

The advisor requires a W&B run id for every timing claim. `benchmark.sh
--local-submit` is not W&B-instrumented, so the draws produce no run of their
own; this script publishes the parsed draw records and the paired statistics as
a single run so the claim has a citable id.

Usage:
  python research/fern_r109f_log_ab_wandb.py <ladder_dir> <arm_a> <arm_b> [--baseline <prefix>]

Reads <ladder_dir>/<arm>-<i>.json (the embedded score JSON recovered by
fern_r109f_parse_ladder.py) for i = 1..n on both arms, recomputes the paired
B-A statistics on the decode leg, and logs:
  * config: arms, env, commit, host facts, harness/golden/weights hashes
  * per-draw metrics as a step series (one step per pair index)
  * summary: paired mean delta, t, CI, verdict, and the #714 consistency check
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import subprocess
import sys

# score elasticity on the decode leg (ns = (REF_d/d)^0.75 * (REF_p/p)^0.25)
DECODE_ELASTICITY = 0.75
# frieren #714's banked claim, expressed on the decode leg
FRIEREN_CLAIM_SCORE = 0.0038
FRIEREN_CLAIM_DECODE = (1.0 + FRIEREN_CLAIM_SCORE) ** (-1.0 / DECODE_ELASTICITY) - 1.0

# two-sided 95% t quantiles, indexed by degrees of freedom
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
       7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
       15: 2.131, 20: 2.086, 30: 2.042}


def t95(df: int) -> float:
    if df <= 0:
        return float("nan")
    if df in T95:
        return T95[df]
    keys = sorted(T95)
    for k in keys:
        if k > df:
            return T95[k]
    return 1.96


def load_arm(ladder_dir: str, arm: str) -> list[dict]:
    """Return the per-draw score dicts for one arm, ordered by draw index."""
    out = []
    for path in sorted(glob.glob(os.path.join(ladder_dir, f"{arm}-*.json"))):
        stem = os.path.basename(path)[:-len(".json")]
        if stem.endswith("-parsed"):
            continue
        idx_txt = stem.rsplit("-", 1)[-1]
        if not idx_txt.isdigit():
            continue
        with open(path) as fh:
            raw = json.load(fh)
        # --local-submit writes score.json with everything under "metrics"
        rec = dict(raw.get("metrics", raw))
        for k, v in raw.items():
            if k != "metrics" and k not in rec:
                rec[k] = v
        rec["_draw_index"] = int(idx_txt)
        rec["_path"] = path
        out.append(rec)
    out.sort(key=lambda r: r["_draw_index"])
    return out


def leg(rec: dict, key: str) -> float:
    for k in (key, key.replace("_seconds_per_token", "_s_per_tok")):
        if k in rec:
            return float(rec[k])
    raise KeyError(f"{key} not in {sorted(rec)[:12]}")


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def sd(xs: list[float]) -> float:
    if len(xs) < 2:
        return float("nan")
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ladder_dir")
    ap.add_argument("arm_a")
    ap.add_argument("arm_b")
    ap.add_argument("--baseline", default=None,
                    help="optional pre-hunk baseline prefix, logged as context")
    ap.add_argument("--project", default="mlxfast-maple")
    ap.add_argument("--entity", default="wandb-applied-ai-team")
    args = ap.parse_args()

    a = load_arm(args.ladder_dir, args.arm_a)
    b = load_arm(args.ladder_dir, args.arm_b)
    n = min(len(a), len(b))
    if n < 2:
        print(f"need >=2 pairs, have a={len(a)} b={len(b)}", file=sys.stderr)
        return 2
    a, b = a[:n], b[:n]

    d_a = [leg(r, "decode_seconds_per_token") for r in a]
    d_b = [leg(r, "decode_seconds_per_token") for r in b]
    p_a = [leg(r, "prefill_seconds_per_token") for r in a]
    p_b = [leg(r, "prefill_seconds_per_token") for r in b]

    rel = [(y - x) / x * 100.0 for x, y in zip(d_a, d_b)]
    m_rel, s_rel = mean(rel), sd(rel)
    sem = s_rel / math.sqrt(n)
    tcrit = t95(n - 1)
    lo, hi = m_rel - tcrit * sem, m_rel + tcrit * sem
    tstat = m_rel / sem if sem else float("nan")
    significant = abs(tstat) > tcrit

    # decode-only score implication, prefill held fixed
    def to_score(r_pct: float) -> float:
        return ((1.0 + r_pct / 100.0) ** (-DECODE_ELASTICITY) - 1.0) * 100.0

    claim_pct = FRIEREN_CLAIM_DECODE * 100.0
    claim_excluded = not (lo <= claim_pct <= hi)

    correctness_ok = all(
        int(r.get("max_abs_diff", -1)) == 0 and bool(r.get("passed_correctness"))
        for r in a + b)
    harness_hashes = sorted({r.get("harness_hash") for r in a + b})
    golden_hashes = sorted({r.get("golden_hash") for r in a + b})

    try:
        import wandb
    except ImportError:
        print("wandb not importable", file=sys.stderr)
        return 3

    run = wandb.init(
        entity=args.entity,
        project=args.project,
        job_type="paired_ab",
        name=f"r109f-tg256-paired-ab-n{n}",
        tags=["r109-f", "maple-fern", "tg256", "shared-qmv", "paired-ab",
              "local-submit", "negative-result"],
        config={
            "assignment_id": "maple-r109-f-integration-and-submission",
            "revision_id": "r109-f-rev3",
            "student": "maple-fern",
            "base_sha": "18ac6015c6c2c52ae2fa8830b23d249b35b6f448",
            "commit": git_head(),
            "arm_a": args.arm_a,
            "arm_b": args.arm_b,
            "arm_a_env": "DARKBLOOM_SHARED_QMV_TG256=0",
            "arm_b_env": "DARKBLOOM_SHARED_QMV_TG256=1",
            "pairs": n,
            "blocking": "ABBA (odd pair index A,B; even pair index B,A)",
            "harness": "benchmark.sh --local-submit",
            "decode_steps_per_draw": 1023,
            "repeats_per_draw": 1,
            "host": "M4 Pro, 48 GiB, GPU gen 16 applegpu_g16s, 20 cores",
            "note_local_ns": ("local ns ~1.06 is not comparable to official ~2.6; "
                              "passed_prefill_speedup_floor is false locally under the "
                              "48 GiB low-memory startup profile. Adjudicate raw legs."),
            "harness_hashes": harness_hashes,
            "golden_hashes": golden_hashes,
        },
    )

    for i in range(n):
        run.log({
            "pair": i + 1,
            f"{args.arm_a}/decode_s_per_tok": d_a[i],
            f"{args.arm_b}/decode_s_per_tok": d_b[i],
            f"{args.arm_a}/prefill_s_per_tok": p_a[i],
            f"{args.arm_b}/prefill_s_per_tok": p_b[i],
            "paired/decode_rel_delta_pct": rel[i],
            "paired/decode_abs_delta_s": d_b[i] - d_a[i],
        }, step=i + 1)

    run.summary.update({
        "pairs": n,
        "decode_mean_a": mean(d_a),
        "decode_mean_b": mean(d_b),
        "decode_sd_a": sd(d_a),
        "decode_sd_b": sd(d_b),
        "paired_decode_rel_delta_pct_mean": m_rel,
        "paired_decode_rel_delta_pct_sd": s_rel,
        "paired_decode_rel_delta_pct_sem": sem,
        "paired_decode_rel_delta_pct_ci95_lo": lo,
        "paired_decode_rel_delta_pct_ci95_hi": hi,
        "paired_t_stat": tstat,
        "paired_t_crit_95": tcrit,
        "significant_at_95": significant,
        "implied_score_delta_pct": to_score(m_rel),
        "implied_score_delta_pct_ci95_lo": to_score(hi),
        "implied_score_delta_pct_ci95_hi": to_score(lo),
        "frieren_714_claim_score_pct": FRIEREN_CLAIM_SCORE * 100.0,
        "frieren_714_claim_decode_pct": claim_pct,
        "frieren_714_claim_excluded_at_95": claim_excluded,
        "all_draws_bit_exact": correctness_ok,
        "n_distinct_harness_hash": len(harness_hashes),
        "verdict": ("TG=256 effect distinguishable from zero"
                    if significant else
                    "TG=256 effect NOT distinguishable from zero (null)"),
    })
    url = run.get_url()
    rid = run.id
    run.finish()

    print(f"pairs={n} mean_rel={m_rel:+.4f}% ci95=[{lo:+.4f}%,{hi:+.4f}%] "
          f"t={tstat:+.3f} significant={significant}")
    print(f"frieren_714 decode claim {claim_pct:+.4f}% excluded={claim_excluded}")
    print(f"WANDB_RUN_ID={rid}")
    print(f"WANDB_RUN_URL={url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
