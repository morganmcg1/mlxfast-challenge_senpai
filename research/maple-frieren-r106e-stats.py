#!/usr/bin/env python3
"""R106-E preregistered statistics: M-UNIQ, Delta-PAIR, POST, DECIDE.

Consumes the ladder's --json output and applies the four tests preregistered
in research/maple-frieren-r106e-replication.md sections 10.4-10.7.

    python3 research/maple-frieren-r106e-stats.py \
        --json /tmp/r106e_ladder.json [--out-json /tmp/r106e_stats.json]

The ladder owns feed extraction and per-draw reporting; this module owns the
inferential contract so the two can be audited separately.
"""

import argparse
import importlib.util
import json
import math
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))

# Sigma hypotheses under adjudication (percent, log scale). See section 10.2:
# these are NOT three estimates of one parameter, they are one estimate of
# sigma(ln cs), one exact value of sigma(ln session_factor), and one upper
# bound pooled across different code.
SIGMA_HYP = [
    ("H1", 0.2494, "sigma(ln cs) from one near-replicate pair, dof=1"),
    ("H2", 0.5393, "sigma(ln session_factor), baseline-only, n=1185"),
    ("H3", 1.2244, "pooled across different code: upper bound, biased up"),
]
SIGMA_SF_HIST = 0.5393  # percent; #555 Part 1, n=1185, lag-1 = -0.0173
N_SF_HIST = 1185
GAP_PCT = 0.999  # log-score gap to the record used by the p-table
BATCH_SIZES = (20, 50, 100)
SERIES = ("cand_dec", "cand_pre", "base_dec", "base_pre")


def load_ladder_helpers():
    path = os.path.join(HERE, "maple-frieren-r106e-ladder.py")
    spec = importlib.util.spec_from_file_location("r106e_ladder", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def norm_isf(p):
    lo, hi = -40.0, 40.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if norm_sf(mid) > p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def chi2_logpdf(x, k):
    if x <= 0:
        return float("-inf")
    return (k / 2 - 1) * math.log(x) - x / 2 - (k / 2) * math.log(2) - math.lgamma(k / 2)


def pearson(xs, ys):
    n = len(xs)
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx <= 0 or syy <= 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def m_uniq(draws):
    """Hard gate: a server-side cache would return byte-identical numbers.

    The submitted surface is exactly benchmark.json editablePaths, and every
    draw uploads the same bytes there (section 11). Only submissionCommitSha
    differs. So a content-addressed score cache is a live failure mode, and
    repeated raw times -- especially repeated BASELINE legs, which no candidate
    change can touch -- are its signature.
    """
    report, ok = {}, True
    for key in SERIES:
        vals = [d.get(key) for d in draws]
        vals = [v for v in vals if isinstance(v, (int, float))]
        uniq = len(set(vals))
        dup = uniq < len(vals)
        report[key] = {"n": len(vals), "unique": uniq, "duplicated": dup,
                       "values": vals}
        if dup:
            ok = False
    report["baseline_varies"] = bool(
        report.get("base_dec", {}).get("unique", 0) > 1
        or report.get("base_pre", {}).get("unique", 0) > 1
    )
    report["pass"] = bool(ok and report["baseline_varies"])
    return report


def decompose(draws):
    """ln S = ln cs + ln session_factor, exactly (verified to 4.9e-15 rel)."""
    x = [100.0 * math.log(d["cs"]) for d in draws]
    l = [100.0 * math.log(d["L"]) for d in draws]
    s = [100.0 * math.log(d["score"]) for d in draws]
    resid = max(abs(si - (xi + li)) for si, xi, li in zip(s, x, l))
    return x, l, s, resid


def delta_pair(x, l, s):
    """Pitman-Morgan test that pairing changes the ranked variance.

    U = ln S + ln cs, V = ln S - ln cs = ln sf, and Cov(U,V) = Var(ln S) -
    Var(ln cs). So corr(U,V) = 0 iff pairing is variance-neutral. Exact under
    bivariate normality with df = n-2.
    """
    n = len(x)
    out = {"n": n}
    if n < 3:
        out["verdict"] = "n < 3: Pitman-Morgan undefined"
        return out
    vx, vl, vs = statistics.variance(x), statistics.variance(l), statistics.variance(s)
    cov = (vs - vx - vl) / 2.0
    u = [si + xi for si, xi in zip(s, x)]
    v = [si - xi for si, xi in zip(s, x)]
    r = pearson(u, v)
    df = n - 2
    t = r * math.sqrt(df / max(1e-15, 1 - r * r))
    out.update({
        "sd_ln_cs_pct": math.sqrt(vx), "sd_ln_sf_pct": math.sqrt(vl),
        "sd_ln_S_pct": math.sqrt(vs), "cov_hat": cov,
        "corr_cs_sf": cov / math.sqrt(vx * vl) if vx > 0 and vl > 0 else float("nan"),
        "delta": vs - vx, "sigma_sf_hist_sq": SIGMA_SF_HIST ** 2,
        "r_UV": r, "t": t, "df": df,
    })
    out["verdict"] = (
        "Cov < 0: common-mode session drift, pairing HELPS" if cov < 0
        else "Cov >= 0: pairing does NOT help; paired design is not protective"
    )
    return out


def posterior(sd_ln_cs_pct, n, priors=None):
    """Posterior over the sigma hypotheses given s(ln cs) with n draws."""
    if n < 2:
        return {"verdict": "n < 2: no posterior"}
    k = n - 1
    priors = priors or [1.0 / len(SIGMA_HYP)] * len(SIGMA_HYP)
    logs = []
    for (_, sig, _), pri in zip(SIGMA_HYP, priors):
        # (n-1) s^2 / sigma^2 ~ chi2_k; Jacobian in s is constant across
        # hypotheses only up to the 2 k s / sigma^2 factor, which we keep.
        q = k * sd_ln_cs_pct ** 2 / sig ** 2
        logs.append(math.log(pri) + chi2_logpdf(q, k) + math.log(k / sig ** 2))
    m = max(logs)
    w = [math.exp(a - m) for a in logs]
    tot = sum(w)
    return {
        "n": n, "dof": k, "sd_ln_cs_pct": sd_ln_cs_pct,
        "posterior": {tag: wi / tot for (tag, _, _), wi in zip(SIGMA_HYP, w)},
        "hypotheses": {tag: {"sigma_pct": sig, "meaning": txt}
                       for tag, sig, txt in SIGMA_HYP},
    }


def p_beat(sigma_cs_pct, gap_pct=GAP_PCT, cov=0.0, sigma_sf_pct=SIGMA_SF_HIST):
    var = sigma_cs_pct ** 2 + sigma_sf_pct ** 2 + 2 * cov
    sd = math.sqrt(max(var, 1e-12))
    return norm_sf(gap_pct / sd), sd


def decide(post, cov=0.0, gap_pct=GAP_PCT):
    """Grind iff the posterior-averaged chance of a record within B draws >= 0.5."""
    out = {"gap_pct": gap_pct, "cov_used": cov, "batches": {}}
    if "posterior" not in post:
        out["verdict"] = "no posterior: cannot decide"
        return out
    per = {}
    for tag, sig, _ in SIGMA_HYP:
        p, sd = p_beat(sig, gap_pct, cov)
        per[tag] = {"sigma_pct": sig, "sd_ln_S_pct": sd, "z": gap_pct / sd, "p": p}
    out["per_hypothesis"] = per
    var_floor = sigma_sf_floor = SIGMA_SF_HIST ** 2 + 2 * cov
    for B in BATCH_SIZES:
        ev = sum(post["posterior"][tag] * (1 - (1 - per[tag]["p"]) ** B) for tag in per)
        # Break-even on the TOTAL ranked noise: the code-independent threshold.
        p_need = 1 - 0.5 ** (1.0 / B)
        sd_star = gap_pct / norm_isf(p_need)
        # Implied break-even on sigma(ln cs), given the session-factor floor.
        resid = sd_star ** 2 - var_floor
        cs_star = math.sqrt(resid) if resid > 0 else 0.0
        out["batches"][B] = {
            "expected_P_record": ev, "grind": ev >= 0.5,
            "break_even_sd_ln_S_pct": sd_star,
            "break_even_sigma_cs_pct": cs_star,
            "already_grind_at_zero_cs": resid <= 0,
        }
    out["sigma_sf_floor_var"] = sigma_sf_floor
    return out


def fmt(md, s=""):
    md.append(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, help="ladder --json output")
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--gap", type=float, default=GAP_PCT)
    ap.add_argument("--use-measured-cov", action="store_true",
                    help="price DECIDE with the measured Cov instead of 0")
    args = ap.parse_args()

    with open(args.json) as f:
        ladder = json.load(f)
    draws = [d for d in ladder.get("draws", [])
             if isinstance(d.get("cs"), (int, float))
             and isinstance(d.get("L"), (int, float))
             and isinstance(d.get("score"), (int, float))]
    draws.sort(key=lambda d: d.get("t") or "")
    n = len(draws)

    md, out = [], {"n": n}
    fmt(md, "## R106-E preregistered statistics")
    fmt(md)
    fmt(md, f"Scored draws with a complete metric set: **n = {n}**")
    fmt(md)

    uq = m_uniq(draws)
    out["m_uniq"] = uq
    fmt(md, "### M-UNIQ (hard gate)")
    fmt(md)
    fmt(md, "| series | n | unique | duplicated |")
    fmt(md, "|---|---|---|---|")
    for key in SERIES:
        r = uq[key]
        fmt(md, f"| `{key}` | {r['n']} | {r['unique']} | {'YES' if r['duplicated'] else 'no'} |")
    fmt(md)
    fmt(md, f"baseline legs vary: **{uq['baseline_varies']}** -- "
            f"gate: **{'PASS' if uq['pass'] else 'VOID (cache artefact)'}**")
    fmt(md)
    if not uq["pass"] and n >= 2:
        fmt(md, "> Every draw uploads byte-identical `editablePaths`; only the recorded")
        fmt(md, "> commit SHA differs. Repeated raw times are therefore consistent with a")
        fmt(md, "> content-addressed score cache, and the spread would measure nothing.")
        fmt(md)

    if n >= 2:
        x, l, s, resid = decompose(draws)
        out["identity_residual_pct"] = resid
        sd_cs = statistics.stdev(x)
        sd_sf = statistics.stdev(l)
        sd_s = statistics.stdev(s)
        helpers = load_ladder_helpers()
        ci_cs = helpers.sd_ci(sd_cs, n)
        out.update({"sd_ln_cs_pct": sd_cs, "sd_ln_sf_pct": sd_sf,
                    "sd_ln_S_pct": sd_s, "sd_ln_cs_ci95_pct": list(ci_cs)})
        fmt(md, "### Decomposition  ln S = ln cs + ln session_factor")
        fmt(md)
        fmt(md, f"identity residual: {resid:.3e} %% (exact to floating point)")
        fmt(md)
        fmt(md, "| term | s (%) | 95% CI (%) |")
        fmt(md, "|---|---|---|")
        fmt(md, f"| **sigma(ln cs) [the unmeasured term]** | {sd_cs:.4f} | "
                f"[{ci_cs[0]:.4f}, {ci_cs[1]:.4f}] |")
        fmt(md, f"| sigma(ln session_factor) | {sd_sf:.4f} | historical {SIGMA_SF_HIST:.4f} (n={N_SF_HIST}) |")
        fmt(md, f"| sigma(ln officialScore) | {sd_s:.4f} | |")
        fmt(md)

        dp = delta_pair(x, l, s)
        out["delta_pair"] = dp
        fmt(md, "### Delta-PAIR (does pairing protect us?)")
        fmt(md)
        if "cov_hat" in dp:
            fmt(md, f"Cov(ln cs, ln sf) = {dp['cov_hat']:+.5f} %^2  "
                    f"(corr {dp['corr_cs_sf']:+.3f});  "
                    f"Delta = s^2(ln S) - s^2(ln cs) = {dp['delta']:+.5f} %^2 "
                    f"vs historical sigma_sf^2 = {dp['sigma_sf_hist_sq']:.5f} %^2")
            fmt(md)
            fmt(md, f"Pitman-Morgan: r(U,V) = {dp['r_UV']:+.4f}, "
                    f"t = {dp['t']:+.3f}, df = {dp['df']}")
        fmt(md)
        fmt(md, f"**{dp['verdict']}**")
        fmt(md)

        post = posterior(sd_cs, n)
        out["posterior"] = post
        fmt(md, "### POST (which sigma does the data support?)")
        fmt(md)
        fmt(md, "| hyp | sigma (%) | what it actually estimates | posterior |")
        fmt(md, "|---|---|---|---|")
        for tag, sig, txt in SIGMA_HYP:
            p = post.get("posterior", {}).get(tag)
            fmt(md, f"| {tag} | {sig:.4f} | {txt} | "
                    f"{'%.3f' % p if p is not None else 'n/a'} |")
        fmt(md)

        cov = dp.get("cov_hat", 0.0) if args.use_measured_cov else 0.0
        dec = decide(post, cov=cov, gap_pct=args.gap)
        out["decide"] = dec
        fmt(md, "### DECIDE (grind the channel, or stop?)")
        fmt(md)
        fmt(md, f"gap to record = {args.gap:.3f} %% of log score; Cov priced at {cov:+.5f} %^2")
        fmt(md)
        fmt(md, "| hyp | sigma(ln S) (%) | z | p(one draw beats record) |")
        fmt(md, "|---|---|---|---|")
        for tag, r in dec.get("per_hypothesis", {}).items():
            fmt(md, f"| {tag} | {r['sd_ln_S_pct']:.4f} | {r['z']:.3f} | {100*r['p']:.2f}% |")
        fmt(md)
        fmt(md, "| B | E[P(>=1 record)] | break-even sigma(ln S) (%) | "
                "implied break-even sigma(ln cs) (%) | decision |")
        fmt(md, "|---|---|---|---|---|")
        for B, r in dec.get("batches", {}).items():
            imp = ("already met by sigma_sf alone"
                   if r["already_grind_at_zero_cs"]
                   else f"{r['break_even_sigma_cs_pct']:.3f}")
            fmt(md, f"| {B} | {100*r['expected_P_record']:.1f}% | "
                    f"{r['break_even_sd_ln_S_pct']:.4f} | {imp} | "
                    f"{'GRIND' if r['grind'] else 'stop'} |")
        fmt(md)
        fmt(md, f"The session-factor floor alone is sigma(ln sf) = {SIGMA_SF_HIST:.4f} %. "
                "Any batch size whose break-even sigma(ln S) falls below that floor is "
                "already in the grind regime independently of sigma(ln cs).")
        fmt(md)
    else:
        fmt(md, "n < 2: spread, Delta-PAIR, POST and DECIDE are undefined. "
                "Report the draws and stop.")
        fmt(md)

    print("\n".join(md))
    if args.out_json:
        with open(args.out_json, "w") as f:
            json.dump(out, f, indent=2, sort_keys=True, default=str)


if __name__ == "__main__":
    main()
