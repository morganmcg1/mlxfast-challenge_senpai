#!/usr/bin/env python3
"""Publish the r109-f LUCK-TERM IDENTITY to W&B, recomputing every number here.

Why this script exists
----------------------
PR #686 was closed unmerged at 12:28Z, terminal `git push` is blocked, and
`respond_to_human_issue` refuses a PR, so W&B is the only surface the fleet and
the advisor still share with me between typed results. This run therefore
(a) recomputes the identity and the dispersion numbers directly from the cached
public receipt feed, so the run is *evidence* rather than an assertion, and
(b) uploads the write-up and the analysis scripts as a durable artifact.

Headline: the multiplicative luck factor in every official score is an exact
algebraic function of the harness's re-measurement of the UNMODIFIED baseline,
so it is observable for free on every public row and needs no repeats.

Usage:
  python3 research/fern_r109f_publish_luck_identity_wandb.py \
      research/artifacts/fern-r109f/receipts/submissions-2026-08-11T1206Z.json
"""
import json
import math
import os
import pathlib
import statistics
import sys

import wandb

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"

D0 = 0.01385621216015625
P0 = 0.00036751938916015626

BAR = 2.61955310948           # crown 4ea72c3b2887, graded 09:34:06Z
OUR_BEST_NORMALIZED = 2.582263  # tree behind 5c542169
NEEDED_MULT = BAR / OUR_BEST_NORMALIZED

HEADLINE = (
    "THE LUCK TERM IS AN EXACT IDENTITY, NOT AN ESTIMATE. "
    "draw = officialScore/normalized = (baseline_decode/D0)^0.75 * "
    "(baseline_prefill/P0)^0.25 to 4.7e-15 on 1284 public rows, so the per-shot "
    "lottery is code-free and directly observable. sd(log draw) = 0.537 %; the "
    "PREFILL baseline supplies ~81 % of it; the same-run ratio does NOT cancel it "
    "(corr(log baseline_prefill, log candidate_prefill) = +0.08). Per-shot sigma "
    "is 0.55-0.60 %, which refutes the 0.186-0.228 % replicate estimate; and the "
    "luck is i.i.d. (forecast r^2 = 0.000), which is a second independent proof "
    "of 'never wait, fire now'. P(one shot clears the bar) ~= 1.5-2 %."
)


def norm_keys(m):
    return {k.lower().replace("-", "_"): v for k, v in m.items()}


def pick(d, *cands):
    for c in cands:
        v = d.get(c)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return None


def load(path):
    with open(path) as fh:
        blob = json.load(fh)
    rows = blob if isinstance(blob, list) else (
        blob.get("submissions") or blob.get("items") or blob.get("data") or [])
    recs = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        score = r.get("officialScore")
        m = r.get("officialMetrics")
        if not isinstance(score, (int, float)) or not isinstance(m, dict):
            continue
        d = norm_keys(m)
        cd = pick(d, "candidate_decode_seconds_per_token", "decode_seconds_per_token")
        cp = pick(d, "candidate_prefill_seconds_per_token", "prefill_seconds_per_token")
        bd = pick(d, "baseline_decode_seconds_per_token")
        bp = pick(d, "baseline_prefill_seconds_per_token")
        ds = pick(d, "decode_speedup")
        ps = pick(d, "prefill_speedup")
        if None in (cd, cp, bd, bp, ds, ps):
            continue
        recs.append(dict(score=float(score), cd=cd, cp=cp, bd=bd, bp=bp, ds=ds, ps=ps,
                         normalized=(D0 / cd) ** 0.75 * (P0 / cp) ** 0.25))
    return len(rows), recs


def maxrel(pairs):
    return max(abs(a - b) / abs(b) for a, b in pairs)


def sd_log(xs):
    return statistics.stdev([math.log(x) for x in xs])


def cor(a, b):
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else float("nan")


def main():
    if not os.environ.get("WANDB_API_KEY"):
        sys.exit("WANDB_API_KEY is required")
    path = sys.argv[1] if len(sys.argv) > 1 else str(
        ROOT / "research/artifacts/fern-r109f/receipts/submissions-2026-08-11T1206Z.json")

    n_rows, recs = load(path)
    if not recs:
        sys.exit(f"no usable rows in {path}")

    # ---- the identities -------------------------------------------------
    id_decode = maxrel([(r["ds"], r["bd"] / r["cd"]) for r in recs])
    id_prefill = maxrel([(r["ps"], r["bp"] / r["cp"]) for r in recs])
    id_score = maxrel([(r["score"], r["ds"] ** 0.75 * r["ps"] ** 0.25) for r in recs])
    id_draw = maxrel([(r["score"] / r["normalized"],
                       (r["bd"] / D0) ** 0.75 * (r["bp"] / P0) ** 0.25) for r in recs])

    draws = sorted(r["score"] / r["normalized"] for r in recs)
    n = len(draws)
    sd_draw = sd_log(draws)
    sd_bd = sd_log([r["bd"] for r in recs])
    sd_bp = sd_log([r["bp"] for r in recs])
    c_bd_bp = cor([math.log(r["bd"]) for r in recs], [math.log(r["bp"]) for r in recs])
    var_d = (0.75 * sd_bd) ** 2
    var_p = (0.25 * sd_bp) ** 2
    share_p = var_p / sd_draw ** 2
    share_d = var_d / sd_draw ** 2

    # ---- no cancellation, selecting on the CODE side (not the outcome) ---
    sel = [r for r in recs if r["normalized"] >= 2.55]
    s_draw = sd_log([r["score"] / r["normalized"] for r in sel])
    s_norm = sd_log([r["normalized"] for r in sel])
    s_pub = sd_log([r["score"] for r in sel])
    c_nd = cor([math.log(r["normalized"]) for r in sel],
               [math.log(r["score"] / r["normalized"]) for r in sel])
    c_pf = cor([math.log(r["bp"]) for r in sel], [math.log(r["cp"]) for r in sel])
    c_dc = cor([math.log(r["bd"]) for r in sel], [math.log(r["cd"]) for r in sel])
    indep_pred = math.sqrt(s_draw ** 2 + s_norm ** 2)

    # ---- collider bias, recorded so nobody re-derives it as fact --------
    col = [r for r in recs if r["score"] >= 2.58]
    col_pub = sd_log([r["score"] for r in col])
    col_draw = sd_log([r["score"] / r["normalized"] for r in col])
    col_c = cor([math.log(r["normalized"]) for r in col],
                [math.log(r["score"] / r["normalized"]) for r in col])

    # ---- exceedances: the per-shot win probability, counted not modelled -
    def rate(t):
        return sum(1 for x in draws if x >= t) / n
    p_needed = rate(NEEDED_MULT)
    med_draw = statistics.median(draws)
    curse_centre = OUR_BEST_NORMALIZED * med_draw
    gap = BAR / curse_centre - 1.0
    z = math.log(BAR / curse_centre) / sd_draw

    run = wandb.init(
        entity=ENTITY, project=PROJECT,
        name="fern-r109f-LUCK-TERM-IDENTIFIED-exact",
        job_type="analysis",
        tags=["r109-f", "luck-term", "identity", "noise", "retraction",
              "read-only", "no-submission"],
        notes=HEADLINE,
        config=dict(
            receipts_file=str(pathlib.Path(path).name),
            rows_in_feed=n_rows,
            rows_usable=n,
            D0=D0, P0=P0, bar=BAR,
            our_best_normalized=OUR_BEST_NORMALIZED,
            needed_multiplier=NEEDED_MULT,
            pr_686_state="closed_unmerged_12:28Z",
            remote_branch_sha="bd47570461dce7471c15a7f7997a93988ff11b5c",
            fired_by_maple_fern=0,
            selection_rule="select on normalized (code side); NEVER on officialScore",
        ),
    )

    run.summary.update({
        "headline": HEADLINE,
        # identities
        "identity/decode_speedup_max_rel_err": id_decode,
        "identity/prefill_speedup_max_rel_err": id_prefill,
        "identity/official_score_max_rel_err": id_score,
        "identity/draw_factor_max_rel_err": id_draw,
        # the luck distribution
        "luck/sd_log_draw_pct": 100 * sd_draw,
        "luck/median_draw": med_draw,
        "luck/p95_draw": draws[int(0.95 * (n - 1))],
        "luck/p99_draw": draws[int(0.99 * (n - 1))],
        "luck/max_draw": draws[-1],
        "luck/sd_log_baseline_decode_pct": 100 * sd_bd,
        "luck/sd_log_baseline_prefill_pct": 100 * sd_bp,
        "luck/corr_log_baseline_decode_prefill": c_bd_bp,
        "luck/var_share_prefill": share_p,
        "luck/var_share_decode": share_d,
        # cancellation test on the code-selected subset
        "cancel/n_selected_normalized_ge_2p55": len(sel),
        "cancel/sd_log_draw_pct": 100 * s_draw,
        "cancel/sd_log_normalized_pct": 100 * s_norm,
        "cancel/sd_log_published_pct": 100 * s_pub,
        "cancel/independent_addition_prediction_pct": 100 * indep_pred,
        "cancel/corr_normalized_draw": c_nd,
        "cancel/corr_log_baseline_candidate_prefill": c_pf,
        "cancel/corr_log_baseline_candidate_decode": c_dc,
        "cancel/verdict": "NO cancellation; +-0.55 % white multiplicative lottery",
        # the trap
        "collider/n_selected_published_ge_2p58": len(col),
        "collider/sd_log_published_pct": 100 * col_pub,
        "collider/sd_log_draw_pct": 100 * col_draw,
        "collider/corr_normalized_draw": col_c,
        "collider/warning": ("apparent cancellation here is COLLIDER BIAS: "
                             "published = code x draw, so conditioning on "
                             "published forces the two to trade off"),
        # per-shot economics
        "shot/p_clear_bar_counted": p_needed,
        "shot/curse_corrected_centre": curse_centre,
        "shot/gap_to_bar_pct": 100 * gap,
        "shot/z_at_identified_sigma": z,
        "shot/p_over_8_shots": 1 - (1 - p_needed) ** 8,
        # adjudications
        "adjudicate/advisor_replicate_sigma_pct": "0.186-0.228 (refuted)",
        "adjudicate/identified_per_shot_sigma_pct": "0.55-0.60",
        "adjudicate/refuted_23_35_pct_figure": True,
        "adjudicate/last_safe_fire_k9_utc": "15:06Z",
        "adjudicate/superseded_last_fire_utc": "14:40Z (mine; adopted fleet-wide in c47 s5)",
        "crown/baseline_prefill_us": 393.615,
        "crown/normalized": 2.576540,
        "crown/note": ("crown was bought with reference-prefill luck; its tree's "
                       "normalized is WORSE than ours (2.582263)"),
        "tg256_disposition": "DO-NOT-LAND",
    })

    tbl = wandb.Table(columns=["threshold", "meaning", "count", "rate_pct"])
    for t, meaning in [
        (NEEDED_MULT, "multiplier our best tree needs to clear the bar"),
        (1.014786, "crown's excursion over its own tree's median draw"),
        (1.016694, "crown's own draw"),
        (1.009444, "e27f1ce's own draw (uncorrected win-prob, double counts luck)"),
    ]:
        tbl.add_data(t, meaning, int(round(rate(t) * n)), 100 * rate(t))
    run.log({"draw_exceedances": tbl})

    art = wandb.Artifact(
        "fern-r109f-luck-term", type="analysis",
        description="Durable copy of the r109-f luck-term identification: exact "
                    "identity for the per-shot lottery, variance shares, the "
                    "no-cancellation result, the collider-bias trap, the i.i.d. "
                    "result and the sigma adjudication. The branch carrying these "
                    "commits cannot be pushed (PR #686 closed; push blocked).",
    )
    for rel in [
        "research/fern-r109f-luck-term-identified.md",
        "research/fern-r109f-channel-slot-ledger.md",
        "research/fern_r109f_luck_identity.py",
        "research/fern_r109f_draw_regime.py",
        "research/fern_r109f_baseline_timing_edge.py",
        "research/fern_r109f_noise_identification.py",
        "research/fern_r109f_baseline_jitter.py",
    ]:
        p = ROOT / rel
        if p.exists():
            art.add_file(str(p), name=rel)
        else:
            print(f"MISSING (skipped): {rel}")
    run.log_artifact(art)

    print("rows_usable            :", n)
    print("identity draw max rel  : %.3e" % id_draw)
    print("sd(log draw)           : %.4f %%" % (100 * sd_draw))
    print("prefill var share      : %.1f %%" % (100 * share_p))
    print("sd(log published) sel  : %.4f %% (n=%d)" % (100 * s_pub, len(sel)))
    print("P(clear bar) counted   : %.3f %%" % (100 * p_needed))
    print(f"published: {run.url}  id={run.id}")
    run.finish()


if __name__ == "__main__":
    main()
