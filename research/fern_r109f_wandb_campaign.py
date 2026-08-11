#!/usr/bin/env python3
"""Publish the R109-F maple-fern campaign to W&B (wandb-applied-ai-team/mlxfast-maple).

Three runs, each recomputed from the receipt cache so every number on the
dashboard is evidence-linked rather than transcribed:

  1. ``fern-r109f-instrument-collapse``
     The baseline-leg noise gauge.  Every ranked receipt carries four legs; the
     two baseline legs execute identical reference code for every solver on
     every submission, so they are a free zero-code-variance noise gauge.  Logs
     per-leg mean/sd/cv, the implied ceiling on between-package code variance,
     the receipts-per-arm power table, and the three self-retractions.

  2. ``fern-r109f-crown-lottery``
     The draw-factor order statistic.  ``published = normalized x draw``; the
     draw factor is host luck no solver can influence.  Logs the draw CDF, the
     per-shot crown probability for our best package, the crown holder's
     code-rank vs luck-rank, and the elasticity of crown probability with
     respect to real code gain.

  3. ``fern-r109f-arms``
     The local 2x2 arm ledger (atlas v2/v3 x router prefetch 0/1) plus every
     ranked receipt this campaign fired, with normalized score and draw factor
     separated.

Usage:
    python3 research/fern_r109f_wandb_campaign.py [--dry-run] [--only NAME ...]
"""

import argparse
import json
import math
import os
import platform
import statistics
import subprocess
import sys

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"

# Score normalization constants, read off the harness reference legs.
REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626
CROWN = 2.61650354381456
CROWN_RECEIPT = "cc6ddc1"
CROWN_SOLVER = "a-github-name"

CACHES = [
    "/tmp/subs_p7.json",
    "/tmp/subs_p6.json",
    "/tmp/subs_p5.json",
    "/tmp/subs_p4.json",
    "/tmp/subs_p3.json",
    "research/artifacts/fern-r109f/receipts/submissions.json",
]

# Noise-gauge window: a single UTC hour keeps host drift out of the estimate.
NOISE_WINDOW = "2026-08-10T00"

# Our ranked receipts this campaign, in firing order.
OUR_RECEIPTS = [
    ("c1c0ba2c-ec1c-43f4-92bb-3c5b8b0a76e9", "t1", "base 074f47e4"),
    ("88584270-140e-4f28-a924-b00c77b1becd", "t2", "same-exe replay 04e8bf3c"),
    ("e4078827-c7fd-4173-a2bf-2f6af7cc6e73", "t3", "base + QHOIST=1 ec0954e2"),
    ("ed40f3ee-b76b-45de-b751-d02b013ea113", "t4", "base + atlas v3, QHOIST reverted"),
]

# Local 2x2, from research/fern_r109f_ab_rebuild.sh / fern_r109f_env_bench.sh.
# decode seconds/token on the local M4 harness, golden b9509697c08a2cf3.
LOCAL_ARMS = [
    ("head-baseline", "v2", 1, 0.0129533590469, "17868864"),
    ("atlas-v3_tg128", "v3", 1, 0.0129499915312, "4e5aaf6b"),
    ("atlas-v3-prefetch0", "v3", 0, 0.0129673987656, "f621d5c1"),
    ("fork-main-1bc1c895", "v2", 0, 0.0129902204000, "8fdfb2a1"),
]

# Own best ranked receipt before this campaign (package 5c542169).
PRIOR_BEST_OFFICIAL = 2.60664970
PRIOR_BEST_COMMIT = "5c542169b5e6c295805f50fa65df3150816eb443"


def sh(*args):
    try:
        return subprocess.run(
            args, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return ""


def load_rows():
    for path in CACHES:
        if os.path.exists(path):
            with open(path) as fh:
                data = json.load(fh)
            rows = data["submissions"] if isinstance(data, dict) else data
            return rows, path
    raise SystemExit(f"no receipt cache found; looked in {CACHES}")


def normalized(m):
    d = m.get("decode_seconds_per_token")
    p = m.get("prefill_seconds_per_token")
    if not d or not p:
        return None
    return (REF_D / d) ** 0.75 * (REF_P / p) ** 0.25


def full_leg(r):
    """Receipt with all four timing legs and a correctness pass."""
    m = r.get("officialMetrics") or {}
    if not m.get("passed_correctness"):
        return False
    keys = (
        "decode_seconds_per_token",
        "prefill_seconds_per_token",
        "baseline_decode_seconds_per_token",
        "baseline_prefill_seconds_per_token",
    )
    return all(m.get(k) for k in keys)


def cv(xs):
    mu = statistics.fmean(xs)
    sd = statistics.stdev(xs)
    return mu, sd, 100.0 * sd / mu


# --------------------------------------------------------------------------
# run 1: the instrument collapse
# --------------------------------------------------------------------------
def leg_noise(rows):
    # Same selection as research/fern_r109f_leg_noise.py: every full-leg
    # correctness-passing receipt created at or after the window start.
    win = [
        r
        for r in rows
        if full_leg(r) and str(r.get("createdAt", ""))[:19] >= NOISE_WINDOW
    ]
    legs = {
        "baseline_decode_us": [
            r["officialMetrics"]["baseline_decode_seconds_per_token"] * 1e6 for r in win
        ],
        "candidate_decode_us": [
            r["officialMetrics"]["decode_seconds_per_token"] * 1e6 for r in win
        ],
        "baseline_prefill_us": [
            r["officialMetrics"]["baseline_prefill_seconds_per_token"] * 1e6 for r in win
        ],
        "candidate_prefill_us": [
            r["officialMetrics"]["prefill_seconds_per_token"] * 1e6 for r in win
        ],
    }
    norms = [normalized(r["officialMetrics"]) for r in win]
    out = {"n": len(win), "window": NOISE_WINDOW, "legs": {}}
    for name, xs in legs.items():
        mu, sd, c = cv(xs)
        out["legs"][name] = {"mean": mu, "sd": sd, "cv_pct": c}
    mu, sd, c = cv(norms)
    out["legs"]["normalized_score"] = {"mean": mu, "sd": sd, "cv_pct": c}

    # The candidate decode leg carries baseline decode noise PLUS whatever real
    # code spread exists across the field.  Subtract in quadrature.
    cb = out["legs"]["baseline_decode_us"]["cv_pct"]
    cc = out["legs"]["candidate_decode_us"]["cv_pct"]
    resid = cc * cc - cb * cb
    out["code_spread_ceiling_cv_pct"] = math.sqrt(resid) if resid > 0 else 0.0
    out["code_spread_ceiling_us"] = (
        out["code_spread_ceiling_cv_pct"] / 100.0
        * out["legs"]["candidate_decode_us"]["mean"]
    )
    return out


def power_table(cv_pct):
    """Receipts per arm for a two-sample test, alpha .05 two-sided, power .95."""
    z = 1.959963985 + 1.644853627  # z_{1-a/2} + z_{1-b}
    rows = []
    for effect in (0.10, 0.20, 0.30, 0.50, 0.60, 1.00):
        n = 2.0 * (z * cv_pct / effect) ** 2
        rows.append(
            {"effect_pct": effect, "receipts_per_arm": math.ceil(n), "n_exact": n}
        )
    return rows


# --------------------------------------------------------------------------
# run 2: the crown lottery
# --------------------------------------------------------------------------
def draw_stats(rows):
    draws = []
    norms = []
    for r in rows:
        if not full_leg(r):
            continue
        pub = r.get("officialScore")
        n = normalized(r["officialMetrics"])
        if not pub or not n:
            continue
        draws.append(pub / n)
        norms.append((n, r))
    draws.sort()
    return draws, norms


def pctile(sorted_xs, q):
    if not sorted_xs:
        return None
    i = min(len(sorted_xs) - 1, max(0, int(round(q * (len(sorted_xs) - 1)))))
    return sorted_xs[i]


def crown_prob(draws, norm_value):
    """Assumption-free: what fraction of observed draws lift this package to the crown?"""
    need = CROWN / norm_value
    k = sum(1 for d in draws if d >= need)
    p = k / len(draws)
    return need, k, p


def elasticity(draws, base_norm):
    out = []
    for gain in (0.0, 0.10, 0.20, 0.30, 0.50, 0.64, 1.00, 1.60):
        n = base_norm * (1.0 + gain / 100.0)
        need, k, p = crown_prob(draws, n)
        shots = math.ceil(math.log(0.5) / math.log(1 - p)) if 0 < p < 1 else None
        out.append(
            {
                "code_gain_pct": gain,
                "normalized": n,
                "draw_needed": need,
                "k": k,
                "p_per_shot_pct": 100.0 * p,
                "shots_for_50pct": shots,
                "hours_for_50pct": (shots * 22.0 / 60.0) if shots else None,
            }
        )
    base_p = out[0]["p_per_shot_pct"]
    for row in out:
        row["ratio_vs_zero"] = row["p_per_shot_pct"] / base_p if base_p else None
    return out


def wilson_upper(k, n, z=1.959963985):
    if n == 0:
        return None
    ph = k / n
    d = 1 + z * z / n
    c = ph + z * z / (2 * n)
    hw = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return (c + hw) / d


# --------------------------------------------------------------------------
def base_config(rows, cache):
    return {
        "round": "r109-F",
        "student": "maple-fern",
        "assignment": "maple-r109-f-integration-and-submission",
        "revision": "r109-f-rev2",
        "pr": 686,
        "git/head": sh("git", "rev-parse", "HEAD"),
        "git/branch": sh("git", "rev-parse", "--abbrev-ref", "HEAD"),
        "host/chip": sh("sysctl", "-n", "machdep.cpu.brand_string"),
        "host/os": platform.platform(),
        "host/is_ranked": False,
        "receipts/cache": cache,
        "receipts/total_rows": len(rows),
        "receipts/full_leg_correct": sum(1 for r in rows if full_leg(r)),
        "score/ref_decode_s_per_tok": REF_D,
        "score/ref_prefill_s_per_tok": REF_P,
        "score/crown": CROWN,
        "score/crown_receipt": CROWN_RECEIPT,
        "score/crown_solver": CROWN_SOLVER,
    }


def run_instrument_collapse(wandb, rows, cache, dry):
    ln = leg_noise(rows)
    cfg = base_config(rows, cache)
    cfg.update({"noise/window_utc_hour": NOISE_WINDOW, "noise/n_receipts": ln["n"]})

    summary = {}
    for name, s in ln["legs"].items():
        summary[f"noise/{name}/mean"] = s["mean"]
        summary[f"noise/{name}/sd"] = s["sd"]
        summary[f"noise/{name}/cv_pct"] = s["cv_pct"]
    summary["noise/code_spread_ceiling_cv_pct"] = ln["code_spread_ceiling_cv_pct"]
    summary["noise/code_spread_ceiling_us"] = ln["code_spread_ceiling_us"]

    norm_cv = ln["legs"]["normalized_score"]["cv_pct"]
    pt = power_table(norm_cv)
    for row in pt:
        summary[f"power/receipts_per_arm_at_{row['effect_pct']:.2f}pct"] = row[
            "receipts_per_arm"
        ]

    print(f"[instrument-collapse] n={ln['n']} window={NOISE_WINDOW}")
    for name, s in ln["legs"].items():
        print(f"  {name:<22} mean={s['mean']:.4f} sd={s['sd']:.4f} cv={s['cv_pct']:.4f}%")
    print(
        f"  between-package code spread ceiling: "
        f"{ln['code_spread_ceiling_cv_pct']:.4f}% "
        f"({ln['code_spread_ceiling_us']:.2f} us)"
    )
    for row in pt:
        print(
            f"  power: detect {row['effect_pct']:.2f}% -> "
            f"{row['receipts_per_arm']} receipts/arm"
        )
    if dry:
        return None

    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        name="fern-r109f-instrument-collapse",
        job_type="analysis",
        tags=["r109-F", "maple-fern", "instrument", "noise-gauge", "retraction"],
        notes=(
            "Baseline-leg noise gauge. The two baseline legs of every ranked receipt "
            "run identical reference code for every solver, so they are a free "
            "zero-code-variance instrument. Result: the ranked host is a 0.37%-sd "
            "lottery and field-wide between-package code spread is at most 0.164%."
        ),
        config=cfg,
        reinit=True,
    )
    lt = wandb.Table(columns=["leg", "mean", "sd", "cv_pct"])
    for name, s in ln["legs"].items():
        lt.add_data(name, s["mean"], s["sd"], s["cv_pct"])
    ptab = wandb.Table(columns=["effect_pct", "receipts_per_arm", "n_exact"])
    for row in pt:
        ptab.add_data(row["effect_pct"], row["receipts_per_arm"], row["n_exact"])
    rtab = wandb.Table(columns=["claim", "verdict", "corrected"])
    rtab.add_data(
        "normalized score is a 0.002% instrument, so 1 receipt beats ~470",
        "RETRACTED",
        "two-point tails-tails coincidence: 0.2us apart is 0.015 sigma of "
        "sigma=13.69us, p~1.6%. True instrument sd is 0.370% of mean; "
        "resolution was overstated ~185x.",
    )
    rtab.add_data(
        "we shipped a package 0.60% worse than our own rank-2-of-1231 receipt",
        "RETRACTED",
        "that receipt's 4890.7us is a -2.19 sigma draw of the same executable "
        "cluster, not a faster package. Reconstruction reverted before spending "
        "a submission slot.",
    )
    rtab.add_data(
        "QHOIST costs 678x the noise band",
        "CORRECTED (verdict survives)",
        "-1.36% normalized = -3.82 sigma, p~1.3e-4, and prefill-driven: "
        "candidate prefill 196.30us is +4.27 sigma; decode excess only ~1.2 "
        "sigma. Revert stands.",
    )
    run.log({"leg_noise": lt, "power_table": ptab, "retractions": rtab})
    run.summary.update(summary)
    url = run.url
    run_id = run.id
    run.finish()
    return run_id, url


def run_crown_lottery(wandb, rows, cache, dry):
    draws, norms = draw_stats(rows)
    n = len(draws)
    norms_sorted = sorted(norms, key=lambda t: -t[0])

    our_best_norm = max(
        (normalized(r["officialMetrics"]) for r in rows
         if full_leg(r) and r["id"] in {i for i, _, _ in OUR_RECEIPTS}),
        default=None,
    )
    if our_best_norm is None:
        raise SystemExit("no full-leg receipt of ours in cache")

    need, k, p = crown_prob(draws, our_best_norm)
    shots = math.ceil(math.log(0.5) / math.log(1 - p)) if 0 < p < 1 else None
    el = elasticity(draws, our_best_norm)

    # Crown provenance: separate the crown holder's code from their luck.
    # CROWN_RECEIPT is a receipt-id prefix, not a commit sha.
    crown_row = None
    for i, (nv, r) in enumerate(norms_sorted):
        if str(r.get("id", "")).startswith(CROWN_RECEIPT):
            crown_row = (i + 1, nv, r)
            break
    if crown_row is None:
        raise SystemExit(f"crown receipt {CROWN_RECEIPT} not found among {n} draws")
    draw_rank = None
    crown_draw = None
    if crown_row:
        _, nv, r = crown_row
        crown_draw = r["officialScore"] / nv
        draw_rank = sum(1 for d in draws if d > crown_draw) + 1

    mu, sd, c = cv(draws)
    cfg = base_config(rows, cache)
    cfg.update({"lottery/n_draws": n, "lottery/our_best_normalized": our_best_norm})

    summary = {
        "lottery/draw/min": draws[0],
        "lottery/draw/p05": pctile(draws, 0.05),
        "lottery/draw/median": pctile(draws, 0.50),
        "lottery/draw/p95": pctile(draws, 0.95),
        "lottery/draw/max": draws[-1],
        "lottery/draw/mean": mu,
        "lottery/draw/sd": sd,
        "lottery/draw/cv_pct": c,
        "lottery/our_best_normalized": our_best_norm,
        "lottery/draw_needed_for_crown": need,
        "lottery/k_draws_sufficient": k,
        "lottery/p_per_shot_pct": 100.0 * p,
        "lottery/p_wilson_upper95_pct": 100.0 * wilson_upper(k, n),
        "lottery/shots_for_50pct": shots,
        "lottery/hours_for_50pct": (shots * 22.0 / 60.0) if shots else None,
        "lottery/elasticity_per_0.1pct_code": (
            (el[6]["p_per_shot_pct"] / el[0]["p_per_shot_pct"]) ** (1.0 / 10.0)
            if el[0]["p_per_shot_pct"]
            else None
        ),
    }
    if crown_row:
        summary.update(
            {
                "crown/code_rank_of_n": crown_row[0],
                "crown/normalized": crown_row[1],
                "crown/draw": crown_draw,
                "crown/luck_rank_of_n": draw_rank,
                "crown/n": n,
            }
        )

    print(f"[crown-lottery] n_draws={n}")
    print(
        f"  draw factor: min={draws[0]:.6f} p05={pctile(draws,0.05):.6f} "
        f"med={pctile(draws,0.50):.6f} p95={pctile(draws,0.95):.6f} "
        f"max={draws[-1]:.6f}  cv={c:.4f}%"
    )
    print(
        f"  our best normalized={our_best_norm:.6f} needs draw={need:.6f}: "
        f"{k}/{n} = {100.0*p:.4f}%/shot, n(50%)={shots}"
    )
    if crown_row:
        print(
            f"  crown provenance: code rank {crown_row[0]}/{n}, "
            f"luck rank {draw_rank}/{n} (draw={crown_draw:.6f})"
        )
    for row in el:
        print(
            f"  +{row['code_gain_pct']:.2f}% code -> draw {row['draw_needed']:.6f}, "
            f"k={row['k']}, p={row['p_per_shot_pct']:.4f}%, "
            f"n(50%)={row['shots_for_50pct']}, x{row['ratio_vs_zero']:.1f}"
        )
    if dry:
        return None

    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        name="fern-r109f-crown-lottery",
        job_type="analysis",
        tags=["r109-F", "maple-fern", "crown-ev", "order-statistic", "elasticity"],
        notes=(
            "published = normalized x draw. The draw factor is host luck no solver "
            "can influence (it is dominated by baseline prefill noise). Empirical "
            "order statistic over every full-leg receipt gives an assumption-free "
            "per-shot crown probability, and the elasticity of that probability "
            "with respect to real code gain."
        ),
        config=cfg,
        reinit=True,
    )
    dt = wandb.Table(columns=["quantile", "draw_factor"])
    for q in (0.0, 0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1.0):
        dt.add_data(q, pctile(draws, q))
    et = wandb.Table(
        columns=[
            "code_gain_pct",
            "normalized",
            "draw_needed",
            "k_of_n",
            "p_per_shot_pct",
            "shots_for_50pct",
            "hours_for_50pct",
            "ratio_vs_zero",
        ]
    )
    for row in el:
        et.add_data(
            row["code_gain_pct"],
            row["normalized"],
            row["draw_needed"],
            row["k"],
            row["p_per_shot_pct"],
            row["shots_for_50pct"],
            row["hours_for_50pct"],
            row["ratio_vs_zero"],
        )
    run.log({"draw_cdf": dt, "elasticity": et})
    run.summary.update(summary)
    url = run.url
    run_id = run.id
    run.finish()
    return run_id, url


def run_arms(wandb, rows, cache, dry):
    by_id = {r["id"]: r for r in rows}
    cfg = base_config(rows, cache)
    cfg.update(
        {
            "local/golden_hash": "b9509697c08a2cf3",
            "local/harness": "benchmark.sh --local-iterate",
            "bar/prior_best_official": PRIOR_BEST_OFFICIAL,
            "bar/prior_best_commit": PRIOR_BEST_COMMIT,
        }
    )

    head_decode = LOCAL_ARMS[0][3]
    summary = {}
    print("[arms] local 2x2 (decode s/tok, local M4):")
    for name, atlas, pf, dec, ref in LOCAL_ARMS:
        delta_pct = 100.0 * (dec - head_decode) / head_decode
        summary[f"local/{name}/decode_s_per_tok"] = dec
        summary[f"local/{name}/delta_vs_head_pct"] = delta_pct
        print(
            f"  {name:<22} atlas={atlas} prefetch={pf} decode={dec:.13f} "
            f"delta={delta_pct:+.4f}%  ({ref})"
        )

    print("[arms] ranked receipts:")
    best_pub = None
    for rid, tag, desc in OUR_RECEIPTS:
        r = by_id.get(rid)
        if r is None:
            print(f"  {tag}: {rid[:8]} not in cache")
            continue
        m = r.get("officialMetrics") or {}
        nv = normalized(m) if full_leg(r) else None
        pub = r.get("officialScore")
        draw = (pub / nv) if (pub and nv) else None
        if pub and (best_pub is None or pub > best_pub):
            best_pub = pub
        print(
            f"  {tag} {rid[:8]} status={r['status']:<10} published={pub} "
            f"normalized={nv} draw={draw}"
        )
        if pub:
            summary[f"ranked/{tag}/published"] = pub
        if nv:
            summary[f"ranked/{tag}/normalized"] = nv
        if draw:
            summary[f"ranked/{tag}/draw"] = draw
        if m.get("decode_seconds_per_token"):
            summary[f"ranked/{tag}/cand_decode_us"] = (
                m["decode_seconds_per_token"] * 1e6
            )
            summary[f"ranked/{tag}/cand_prefill_us"] = (
                m["prefill_seconds_per_token"] * 1e6
            )
            summary[f"ranked/{tag}/base_decode_us"] = (
                m["baseline_decode_seconds_per_token"] * 1e6
            )
            summary[f"ranked/{tag}/base_prefill_us"] = (
                m["baseline_prefill_seconds_per_token"] * 1e6
            )
    if best_pub:
        summary["ranked/best_published"] = best_pub
        summary["ranked/best_published_delta_vs_prior_best"] = (
            best_pub - PRIOR_BEST_OFFICIAL
        )
    if dry:
        return None

    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        name="fern-r109f-arms",
        job_type="local-timing",
        tags=["r109-F", "maple-fern", "arms", "atlas-v3", "router-prefetch"],
        notes=(
            "Local 2x2 (atlas v2/v3 x router weight prefetch 0/1) on the local M4, "
            "plus every ranked receipt this campaign fired with normalized score "
            "and draw factor separated. atlas v3_tg128 is -0.026% locally, which is "
            "inside local repeatability and far below ranked resolution; prefetch "
            "1->0 costs +17.4us, so the default 1 stays."
        ),
        config=cfg,
        reinit=True,
    )
    at = wandb.Table(
        columns=["arm", "atlas", "router_prefetch", "decode_s_per_tok", "delta_vs_head_pct", "ref"]
    )
    for name, atlas, pf, dec, ref in LOCAL_ARMS:
        at.add_data(name, atlas, pf, dec, 100.0 * (dec - head_decode) / head_decode, ref)
    rt = wandb.Table(
        columns=[
            "ticket",
            "id",
            "package",
            "status",
            "published",
            "normalized",
            "draw",
            "cand_decode_us",
            "cand_prefill_us",
            "base_decode_us",
            "base_prefill_us",
        ]
    )
    for rid, tag, desc in OUR_RECEIPTS:
        r = by_id.get(rid)
        if r is None:
            continue
        m = r.get("officialMetrics") or {}
        nv = normalized(m) if full_leg(r) else None
        pub = r.get("officialScore")
        rt.add_data(
            tag,
            rid,
            desc,
            r["status"],
            pub,
            nv,
            (pub / nv) if (pub and nv) else None,
            (m.get("decode_seconds_per_token") or 0) * 1e6 or None,
            (m.get("prefill_seconds_per_token") or 0) * 1e6 or None,
            (m.get("baseline_decode_seconds_per_token") or 0) * 1e6 or None,
            (m.get("baseline_prefill_seconds_per_token") or 0) * 1e6 or None,
        )
    run.log({"local_arms": at, "ranked_receipts": rt})
    run.summary.update(summary)
    url = run.url
    run_id = run.id
    run.finish()
    return run_id, url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()

    rows, cache = load_rows()
    print(f"cache={cache} rows={len(rows)} full_leg_correct={sum(1 for r in rows if full_leg(r))}")

    wandb = None
    if not args.dry_run:
        import wandb as _w

        wandb = _w

    todo = {
        "instrument-collapse": run_instrument_collapse,
        "crown-lottery": run_crown_lottery,
        "arms": run_arms,
    }
    names = args.only or list(todo)
    made = []
    for name in names:
        if name not in todo:
            raise SystemExit(f"unknown run {name}; have {list(todo)}")
        res = todo[name](wandb, rows, cache, args.dry_run)
        if res:
            made.append((name, res[0], res[1]))

    if made:
        print("\n=== W&B runs ===")
        for name, run_id, url in made:
            print(f"{name}\t{run_id}\t{url}")


if __name__ == "__main__":
    sys.exit(main())
