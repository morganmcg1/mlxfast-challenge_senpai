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
    "/tmp/subs_p10.json",
    "/tmp/subs_p9.json",
    "/tmp/subs_p8.json",
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
    ("0531544b-a426-4f26-821a-d7f642f6c101", "t5", "same-exe replay of t4 (atlas v3)"),
    ("cb4de9e0-b083-4061-8e2b-3fa3f055c1e9", "t6", "3rd shot of the atlas v3 executable"),
]

# Identical-executable replay groups.  Every member of a group is the SAME
# compiled executable -- verified with `git diff pkg-tN pkg-tM`, which touches
# only Sources/MLXFastModel/DenseTensorStore.swift and adds zero non-comment
# lines -- so all within-group variance is instrument, not code.  These 5
# receipts are the only replicated packages anywhere in the dataset: 0 of 1196
# full-leg receipts from other solvers share a submissionCommitSha.
REPLAY_GROUPS = [
    ("base_t1_t2", ["c1c0ba2c", "88584270"]),
    ("atlasv3_t4_t5_t6", ["ed40f3ee", "0531544b", "cb4de9e0"]),
]

# Package commit per ticket, tagged locally as pkg-t1 .. pkg-t6.
PKG_COMMITS = {
    "t1": "074f47e48fe5",
    "t2": "04e8bf3c861539369fac081b9433025d01208cd7",
    "t3": "ec0954e28ff59515389b659cb33343658acad84b",
    "t4": "d567a72a3b02d936ed37d909ece0b2cb1dca3163",
    "t5": "0a81e48b91c2617fdba30243ddf0f99e3a1fae0a",
    "t6": "fe610f60ecaa41dd93b0e6cf2994eba6ba1586f3",
}

# 8-run MLX_SDPA_BLOCKS sweep on the local host (all correct, golden
# b9509697c08a2cf3).  The arm is NULL; its value was the by-product -- a real
# measurement of local decode repeatability under sustained load, which killed
# the campaign's "local repeats to 0.05-0.10 %" claim (CORRECTION 5).
LOCAL_SWEEP = [
    ("default", None, 12934.7),
    ("default-replay", None, 12965.0),
    ("blocks16", 16, 13019.0),
    ("blocks32", 32, 12926.0),
    ("blocks128", 128, 12935.0),
    ("blocks256", 256, 12850.0),
    ("blocks256-replay", 256, 12934.0),
    ("blocks512", 512, 12889.0),
]

# Host-drift control (research/fern_r109f_host_drift.py).  The monotone
# t4->t5->t6 candidate-decode slide of -0.63 % over 47 min is NOT drift: the
# field control over the same window is flat and the baseline decode leg is
# white noise at lag 1.
DRIFT = {
    "field_cand_decode_spearman": 0.103,
    "field_cand_decode_late_minus_early_pct": 0.033,
    "field_base_decode_spearman": 0.273,
    "field_base_decode_late_minus_early_pct": 0.086,
    "base_decode_lag1_autocorr_n51": 0.008,
    "base_decode_lag1_band_n51": 0.280,
    "base_decode_lag1_autocorr_n213": 0.080,
    "base_decode_lag1_band_n213": 0.137,
    "our_slide_pct": -0.63,
    "our_slide_minutes": 47,
    "verdict": "no drift; blocked ranked A/B is valid without interleaving",
}

# Executable class per ticket: shots sharing a class ran the same binary up to a
# comment-only nonce, so any published spread inside a class is pure host luck.
OUR_CLASSES = {
    "t1": "r109F-base",
    "t2": "r109F-base",
    "t3": "r109F-qhoist",
    "t4": "r109F-atlasv3",
    "t5": "r109F-atlasv3",
    "t6": "r109F-atlasv3",
}

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


def robust_cv(xs):
    """Median / MAD-based cv, scaled to be a consistent sd estimator at normality.

    The plain cv of a candidate leg is NOT a noise estimate: the field posts
    genuinely broken packages, and a handful of 2-10x blow-ups dominate a
    second-moment statistic.  Concretely, widening this campaign's window from
    n=28 to n=54 receipts moved the plain candidate-decode cv from 0.2836 % to
    1.7266 % and the derived "field code spread ceiling" from 0.1788 % to
    1.7131 % -- a 10x swing driven by a few rows, in a number the campaign was
    about to publish. The robust version barely moves, because the median and the
    MAD ignore the tail. This is the fifth time in this campaign that a plain
    moment estimator has produced a headline that a robust one refuted, so it is
    now the default and the plain value is kept only for comparison.
    """
    med = statistics.median(xs)
    mad = statistics.median([abs(x - med) for x in xs])
    return med, 1.4826 * mad, 100.0 * 1.4826 * mad / med


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
    legs["normalized_score"] = norms
    out = {"n": len(win), "window": NOISE_WINDOW, "legs": {}}
    for name, xs in legs.items():
        mu, sd, c = cv(xs)
        med, rsd, rc = robust_cv(xs)
        # ROBUST IS THE DEFAULT.  `mean`/`sd`/`cv_pct` below are the robust
        # (median / 1.4826*MAD) figures; the plain moments are kept beside them
        # under plain_* purely so a reader can see how far the tail drags them.
        # See robust_cv()'s docstring for the n=28 -> n=54 blow-up that forced
        # this change *before* these numbers were published.
        out["legs"][name] = {
            "mean": med,
            "sd": rsd,
            "cv_pct": rc,
            "plain_mean": mu,
            "plain_sd": sd,
            "plain_cv_pct": c,
            "tail_inflation_x": (c / rc) if rc > 0 else None,
        }

    # The candidate decode leg carries baseline decode noise PLUS whatever real
    # code spread exists across the field.  Subtract in quadrature.  Both the
    # robust and the plain version are reported, because the plain one is the
    # number that swung 0.1788 % -> 1.7131 % when the window grew by 26 rows.
    def _ceiling(key):
        cb = out["legs"]["baseline_decode_us"][key]
        cc = out["legs"]["candidate_decode_us"][key]
        resid = cc * cc - cb * cb
        return math.sqrt(resid) if resid > 0 else 0.0

    out["code_spread_ceiling_cv_pct"] = _ceiling("cv_pct")
    out["code_spread_ceiling_us"] = (
        out["code_spread_ceiling_cv_pct"] / 100.0
        * out["legs"]["candidate_decode_us"]["mean"]
    )
    out["code_spread_ceiling_plain_cv_pct"] = _ceiling("plain_cv_pct")
    out["code_spread_ceiling_plain_us"] = (
        out["code_spread_ceiling_plain_cv_pct"] / 100.0
        * out["legs"]["candidate_decode_us"]["plain_mean"]
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


def receipts_for(cv_pct, effect_pct):
    """Single scalar from the same power model as power_table()."""
    z = 1.959963985 + 1.644853627
    return math.ceil(2.0 * (z * cv_pct / effect_pct) ** 2)


# Axes of a receipt, in the order they are reported.  `None` key means the axis
# is derived rather than read straight out of officialMetrics.
GAUGE_AXES = [
    ("candidate_prefill", "prefill_seconds_per_token"),
    ("normalized", None),
    ("candidate_decode", "decode_seconds_per_token"),
    ("published", None),
    ("reference_decode", "baseline_decode_seconds_per_token"),
    ("reference_prefill", "baseline_prefill_seconds_per_token"),
]


def leg_gauge(rows):
    """The campaign's central instrument measurement.

    Pools the within-group cv of every identical-executable replay group by
    degrees of freedom, giving a per-axis instrument sd with 3 df (k=2 base pair
    contributes 1, k=3 atlas-v3 group contributes 2).  Because the executables
    inside a group are git-verified identical, this sd is the *floor* on what a
    single ranked receipt can resolve on that axis -- and the axes differ by a
    factor of 28, which is the whole point: an arm must be judged on the leg it
    targets, not on the published score.
    """
    # Only full-leg, correctness-passing receipts carry all four legs; a queued
    # or failed row has officialMetrics == None and must not enter the gauge.
    by_id = {r["id"][:8]: r for r in rows if full_leg(r)}

    def axis_value(r, name, key):
        m = r["officialMetrics"]
        if key is not None:
            return m[key]
        return r["officialScore"] if name == "published" else normalized(m)

    out = {"axes": [], "groups": {}, "n_receipts": 0, "df": 0}
    seen = set()
    for gname, ids in REPLAY_GROUPS:
        got = [i for i in ids if i in by_id]
        out["groups"][gname] = {"k": len(got), "members": got}
        seen.update(got)
    out["n_receipts"] = len(seen)

    for name, key in GAUGE_AXES:
        ss, df, cells = 0.0, 0, {}
        for gname, ids in REPLAY_GROUPS:
            got = [by_id[i] for i in ids if i in by_id]
            if len(got) < 2:
                continue
            vals = [axis_value(r, name, key) for r in got]
            c = 100.0 * statistics.stdev(vals) / statistics.fmean(vals)
            cells[gname] = c
            ss += (len(vals) - 1) * c * c
            df += len(vals) - 1
        if df == 0:
            continue
        sd = (ss / df) ** 0.5
        out["df"] = df
        out["axes"].append(
            {
                "axis": name,
                "pooled_sd_pct": sd,
                "df": df,
                "receipts_at_0.20pct": receipts_for(sd, 0.20),
                "receipts_at_0.30pct": receipts_for(sd, 0.30),
                "receipts_at_0.50pct": receipts_for(sd, 0.50),
                **{f"cv_{g}_pct": v for g, v in cells.items()},
            }
        )
    return out


def local_sweep_stats():
    """Local decode repeatability, measured as a by-product of the null sweep."""
    vals = [v for _, _, v in LOCAL_SWEEP]
    mean = statistics.fmean(vals)
    sd = statistics.stdev(vals)
    return {
        "n": len(vals),
        "mean_us": mean,
        "sd_us": sd,
        "cv_pct": 100.0 * sd / mean,
        "range_pct": 100.0 * (max(vals) - min(vals)) / mean,
        # the two replicated arms: how far apart did the SAME config land?
        "replicate_gap_default_us": abs(12965.0 - 12934.7),
        "replicate_gap_blocks256_us": abs(12934.0 - 12850.0),
        "verdict": "MLX_SDPA_BLOCKS is null; local decode cv is ~0.35 %/run",
    }


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
        # robust (median / 1.4826*MAD) is the headline; plain moments beside it
        summary[f"noise/{name}/mean"] = s["mean"]
        summary[f"noise/{name}/sd"] = s["sd"]
        summary[f"noise/{name}/cv_pct"] = s["cv_pct"]
        summary[f"noise/{name}/plain_mean"] = s["plain_mean"]
        summary[f"noise/{name}/plain_sd"] = s["plain_sd"]
        summary[f"noise/{name}/plain_cv_pct"] = s["plain_cv_pct"]
        summary[f"noise/{name}/tail_inflation_x"] = s["tail_inflation_x"]
    summary["noise/code_spread_ceiling_cv_pct"] = ln["code_spread_ceiling_cv_pct"]
    summary["noise/code_spread_ceiling_us"] = ln["code_spread_ceiling_us"]
    summary["noise/code_spread_ceiling_plain_cv_pct"] = ln[
        "code_spread_ceiling_plain_cv_pct"
    ]
    summary["noise/code_spread_ceiling_plain_us"] = ln["code_spread_ceiling_plain_us"]
    summary["noise/estimator"] = "robust_median_mad"

    norm_cv = ln["legs"]["normalized_score"]["cv_pct"]
    pt = power_table(norm_cv)
    for row in pt:
        summary[f"power/receipts_per_arm_at_{row['effect_pct']:.2f}pct"] = row[
            "receipts_per_arm"
        ]
    # and the plain-cv power table, so the cost of the estimator choice is visible
    for row in power_table(ln["legs"]["normalized_score"]["plain_cv_pct"]):
        summary[
            f"power/plain_cv_receipts_per_arm_at_{row['effect_pct']:.2f}pct"
        ] = row["receipts_per_arm"]

    print(
        f"[instrument-collapse] n={ln['n']} window={NOISE_WINDOW} "
        f"estimator=robust(median/1.4826*MAD), plain shown for comparison"
    )
    for name, s in ln["legs"].items():
        print(
            f"  {name:<22} med={s['mean']:.4f} sd={s['sd']:.4f} "
            f"cv={s['cv_pct']:.4f}%   | plain cv={s['plain_cv_pct']:.4f}% "
            f"(tail inflation x{s['tail_inflation_x']:.2f})"
        )
    print(
        f"  between-package code spread ceiling (robust): "
        f"{ln['code_spread_ceiling_cv_pct']:.4f}% "
        f"({ln['code_spread_ceiling_us']:.2f} us)"
    )
    print(
        f"  between-package code spread ceiling (plain, NOT quoted): "
        f"{ln['code_spread_ceiling_plain_cv_pct']:.4f}% "
        f"({ln['code_spread_ceiling_plain_us']:.2f} us)"
    )
    for row in pt:
        print(
            f"  power: detect {row['effect_pct']:.2f}% -> "
            f"{row['receipts_per_arm']} receipts/arm"
        )

    # ---- the k=3 identical-executable gauge, and the per-leg reversal -------
    lg = leg_gauge(rows)
    for a in lg["axes"]:
        summary[f"gauge/{a['axis']}/pooled_sd_pct"] = a["pooled_sd_pct"]
        summary[f"gauge/{a['axis']}/receipts_at_0.30pct"] = a["receipts_at_0.30pct"]
    summary["gauge/df"] = lg["df"]
    summary["gauge/n_receipts"] = lg["n_receipts"]
    by_axis = {a["axis"]: a for a in lg["axes"]}
    if "published" in by_axis and "candidate_prefill" in by_axis:
        summary["gauge/prefill_leg_cheaper_than_score_x"] = (
            by_axis["published"]["receipts_at_0.30pct"]
            / by_axis["candidate_prefill"]["receipts_at_0.30pct"]
        )
    print(
        f"  gauge: {lg['n_receipts']} replayed receipts, {lg['df']} df "
        f"(groups: "
        + ", ".join(f"{g}=k{v['k']}" for g, v in lg["groups"].items())
        + ")"
    )
    for a in lg["axes"]:
        print(
            f"    {a['axis']:<18} sd={a['pooled_sd_pct']:.4f}%  "
            f"receipts@0.30%={a['receipts_at_0.30pct']}"
        )

    ls = local_sweep_stats()
    for k, v in ls.items():
        summary[f"local_sweep/{k}"] = v
    print(
        f"  local sweep: n={ls['n']} cv={ls['cv_pct']:.4f}% "
        f"(sd {ls['sd_us']:.1f} us) -- {ls['verdict']}"
    )
    for k, v in DRIFT.items():
        summary[f"drift/{k}"] = v
    print(f"  drift: {DRIFT['verdict']}")

    if dry:
        return None

    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        name="fern-r109f-instrument-collapse",
        job_type="analysis",
        tags=["r109-F", "maple-fern", "instrument", "noise-gauge", "retraction"],
        notes=(
            "Instrument gauge for the ranked host, from two directions. (1) The two "
            "baseline legs of every receipt run identical reference code for every "
            "solver, so they are a free zero-code-variance instrument: the host is a "
            "0.37%-sd lottery and field-wide between-package code spread is at most "
            "0.164%. (2) This campaign's 5 replayed receipts -- the ONLY replicated "
            "packages in the dataset, since 0 of 1196 full-leg receipts from other "
            "solvers share a submissionCommitSha -- give a per-axis pooled instrument "
            "sd with 3 df. The axes span 28x, which reverses the campaign's own "
            "advice: a 0.30% arm costs 77 receipts on officialScore but 2 on the "
            "candidate-prefill leg. Adjudicate arms per leg. Also logged: the null "
            "MLX_SDPA_BLOCKS sweep whose by-product killed the 'local repeats to "
            "0.05-0.10%' claim, and the drift control that cleared a monotone "
            "3-receipt slide as coincidence."
        ),
        config=cfg,
        reinit=True,
    )
    lt = wandb.Table(
        columns=[
            "leg",
            "robust_median",
            "robust_sd",
            "robust_cv_pct",
            "plain_mean",
            "plain_sd",
            "plain_cv_pct",
            "tail_inflation_x",
        ]
    )
    for name, s in ln["legs"].items():
        lt.add_data(
            name,
            s["mean"],
            s["sd"],
            s["cv_pct"],
            s["plain_mean"],
            s["plain_sd"],
            s["plain_cv_pct"],
            s["tail_inflation_x"],
        )
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
    rtab.add_data(
        "luck amplifies code by x33.4 (and x494.9 on the base pair)",
        "RETRACTED",
        "both ratios had a denominator with 1 df. With the k=3 gauge the honest "
        "figure is published sd 0.5169% over normalized sd 0.1917% = x2.7. New "
        "standing rule: no ratio may be quoted unless its denominator has >=3 df, "
        "and the df must be printed.",
    )
    rtab.add_data(
        "the local iterate repeats to 0.05-0.10%, a 4-7x better instrument",
        "RETRACTED",
        "an 8-run local sweep measures decode cv ~0.35%/run, WORSE than the "
        "ranked candidate-decode sd of 0.2646%. Local's advantage is throughput "
        "(~155s, unowned slot) ~ one order of magnitude, not resolution.",
    )
    rtab.add_data(
        "a ranked receipt cannot adjudicate any arm we actually have",
        "CORRECTED",
        "true of officialScore (sd 0.5169% -> 77 receipts for a 0.30% arm), false "
        "of the legs. Candidate prefill sd is 0.0750% -> 2 receipts, 38x cheaper. "
        "Adjudicate every arm on the officialMetrics leg it targets.",
    )
    rtab.add_data(
        "the field's decode code-spread ceiling is 0.1788% (28-receipt window)",
        "CAUGHT BEFORE PUBLICATION",
        "refreshing the receipt cache grew the same window to n=54 and the PLAIN "
        "cv figures exploded: candidate decode 0.2836%->1.7266%, normalized "
        "0.3478%->1.1851%, and the derived ceiling 0.1788%->1.7131% (84.47us) -- "
        "a ~10x swing from a handful of broken-package blow-ups, in a headline "
        "this run was about to log. Plain moments are not noise estimates when "
        "the field posts genuinely broken packages. leg_noise() now reports "
        "median/1.4826*MAD as the default and keeps the plain moments only for "
        "comparison. Across the SAME cache refresh the robust ceiling moved "
        "0.2240% (n=51) -> 0.2393% (n=54), i.e. +6.8%, while the plain one moved "
        "~10x; and the robust candidate-decode leg is inflated x5.2 by the tail "
        "while the baseline-decode leg is inflated x0.95 (no tail at all), which "
        "is exactly the signature of broken candidates rather than a noisy host.",
    )
    gtab = wandb.Table(
        columns=[
            "axis",
            "pooled_sd_pct",
            "df",
            "receipts_at_0.20pct",
            "receipts_at_0.30pct",
            "receipts_at_0.50pct",
        ]
    )
    for a in lg["axes"]:
        gtab.add_data(
            a["axis"],
            a["pooled_sd_pct"],
            a["df"],
            a["receipts_at_0.20pct"],
            a["receipts_at_0.30pct"],
            a["receipts_at_0.50pct"],
        )
    # `mlx_sdpa_blocks` is text, not a number: the first two rows leave the env
    # var unset, and a wandb.Table column whose first row is None types itself as
    # NoneType and then rejects every later integer.
    stab = wandb.Table(columns=["label", "mlx_sdpa_blocks", "decode_us", "delta_pct"])
    base_us = LOCAL_SWEEP[0][2]
    for label, blocks, us in LOCAL_SWEEP:
        stab.add_data(
            label,
            "unset" if blocks is None else str(blocks),
            us,
            100.0 * (us - base_us) / base_us,
        )
    # NOTE: a wandb.Table column is strongly typed by its first row, so a dict
    # that mixes numbers with a verdict string cannot share one `value` column.
    # Keep them apart rather than stringifying the numbers away.
    dtab = wandb.Table(columns=["quantity", "value_num", "value_text"])
    for k, v in DRIFT.items():
        if isinstance(v, (int, float)):
            dtab.add_data(k, float(v), "")
        else:
            dtab.add_data(k, None, str(v))
    run.log(
        {
            "leg_noise": lt,
            "power_table": ptab,
            "retractions": rtab,
            "leg_gauge_k3": gtab,
            "local_sdpa_blocks_sweep": stab,
            "host_drift_control": dtab,
        }
    )
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

    # ---- code axis vs luck axis, on our own receipts only -----------------
    # See instrument-collapse.md 5.3e.  Each of our draws is ranked inside the
    # empirical draw distribution of every full-leg correct receipt on the
    # benchmark, so "our luck was bad" becomes a percentile instead of a mood.
    field_draws = sorted(
        r["officialScore"] / normalized(r["officialMetrics"]) for r in rows if full_leg(r)
    )
    nfield = len(field_draws)

    def draw_pct(d):
        return 100.0 * sum(1 for x in field_draws if x <= d) / nfield

    own = []
    for rid, tag, _desc in OUR_RECEIPTS:
        r = by_id.get(rid)
        if r is None or not full_leg(r):
            continue
        nv = normalized(r["officialMetrics"])
        own.append((tag, r["officialScore"], nv, r["officialScore"] / nv))
    ok = [o for o in own if OUR_CLASSES.get(o[0]) != "r109F-qhoist"]
    print("[arms] code axis vs luck axis (own receipts, non-regressed classes):")
    for tag, pub, nv, dw in own:
        summary[f"ranked/{tag}/draw_percentile_of_field"] = draw_pct(dw)
        print(
            f"  {tag} class={OUR_CLASSES.get(tag,'?'):<14} published={pub:.6f} "
            f"normalized={nv:.6f} draw={dw:.6f} pct={draw_pct(dw):5.1f}%"
        )
    if len(ok) >= 2:
        nzs = [o[2] for o in ok]
        pubs = [o[1] for o in ok]
        cs = 100.0 * (max(nzs) - min(nzs)) / statistics.fmean(nzs)
        ps = 100.0 * (max(pubs) - min(pubs)) / statistics.fmean(pubs)
        summary["own/code_spread_pct"] = cs
        summary["own/published_spread_pct"] = ps
        summary["own/luck_over_code_amplification"] = (ps / cs) if cs else None
        summary["own/n_receipts"] = len(ok)
        summary["field/draw_n"] = nfield
        best_code = max(ok, key=lambda o: o[2])
        best_luck = max(ok, key=lambda o: o[1])
        summary["own/best_code_ticket"] = best_code[0]
        summary["own/best_code_normalized"] = best_code[2]
        summary["own/best_published_ticket"] = best_luck[0]
        summary["own/best_code_is_best_published"] = best_code[0] == best_luck[0]
        print(
            f"  code spread {cs:.4f}%  published spread {ps:.4f}%  "
            f"amplification x{ps/cs:.1f}  (best code {best_code[0]}, "
            f"best published {best_luck[0]})"
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
            "1->0 costs +17.4us, so the default 1 stays. The own/* summary keys are "
            "the campaign's own proof of its thesis (instrument-collapse.md 5.3e): "
            "across our non-regressed shots the code spread is ~0.044% and the "
            "published spread ~1.47%, and the ticket carrying the best code (t4, "
            "normalized 2.567970) published the worst score because its draw landed "
            "in the 3rd percentile of the field's draw distribution."
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
            "exe_class",
            "package",
            "status",
            "published",
            "normalized",
            "draw",
            "draw_percentile_of_field",
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
            OUR_CLASSES.get(tag, "?"),
            desc,
            r["status"],
            pub,
            nv,
            (pub / nv) if (pub and nv) else None,
            draw_pct(pub / nv) if (pub and nv) else None,
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
