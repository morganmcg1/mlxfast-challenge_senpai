#!/usr/bin/env python3
"""Fixed-tree dispersion from the baseline leg, at zero channel cost.

Motivation (section 12). The ranked channel content-addresses submissions: an
upload whose `editablePaths` bytes already exist is deduplicated and the prior
submission is returned verbatim. So a fixed tree CANNOT be re-measured by
resubmitting it, and the assigned R106-E ladder cannot produce n independent
draws of one payload.

But the campaign has been re-measuring a fixed tree all along: the PINNED
BASELINE runs in every ranked session. Its two legs are measured in the same
session, which identifies a session/measurement split from second moments
alone:

    ln bd = mu_d +     s + e_d
    ln bp = mu_p + k * s + e_p

    Var(bd) = V_s + V_ed ,  Var(bp) = k^2 V_s + V_ep ,  Cov = k V_s

Three moments, four unknowns: k is not point-identified, but non-negativity of
V_ed and V_ep bounds it to [Cov/Var(bd), Var(bp)/Cov], which yields a genuine
identified INTERVAL for the fixed-tree leg noise. k = 1 (one common
multiplicative clock/thermal factor) is the natural point.

Then for a fixed candidate tree measured in the same session, the session term
cancels out of the score ratio exactly:

    ln cs = c + 0.75 (e_d - e'_d) + 0.25 (e_p - e'_p)
    Var(ln cs | fixed tree) = 0.5625 (V_ed + V_e'd) + 0.0625 (V_ep + V_e'p)

and taking the candidate leg to have the same noise as the baseline leg gives
Var = 1.125 V_ed + 0.125 V_ep.

    python3 research/maple-frieren-r106e-legnoise.py [--out-json PATH]
"""

import argparse
import json
import math
import os
import statistics
import urllib.request

FEED = ("https://api.mlx.fast/api/benchmarks/"
        "1854efdf-feba-4773-bae9-b80520881a74/submissions")
BD = "baseline_decode_seconds_per_token"
BP = "baseline_prefill_seconds_per_token"
CD = "decode_seconds_per_token"
CP = "prefill_seconds_per_token"


def fetch():
    tok = os.environ["MLXFAST_API_TOKEN"]
    req = urllib.request.Request(FEED, headers={"Authorization": f"Bearer {tok}"})
    return json.load(urllib.request.urlopen(req, timeout=90))["submissions"]


def moments(xs, ys):
    n = len(xs)
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    vx = sum((a - mx) ** 2 for a in xs) / (n - 1)
    vy = sum((b - my) ** 2 for b in ys) / (n - 1)
    cxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / (n - 1)
    return vx, vy, cxy


def lag1(xs):
    n = len(xs)
    m = statistics.fmean(xs)
    num = sum((xs[i] - m) * (xs[i + 1] - m) for i in range(n - 1))
    den = sum((a - m) ** 2 for a in xs)
    return num / den if den else float("nan")


def pct(v):
    """variance in log units -> sd in percent"""
    return 100.0 * math.sqrt(v) if v > 0 else 0.0


def mad(xs):
    med = statistics.median(xs)
    return statistics.median([abs(a - med) for a in xs])


def decompose(bd, bp, label, out):
    n = len(bd)
    x = [math.log(v) for v in bd]
    y = [math.log(v) for v in bp]
    vx, vy, c = moments(x, y)
    r = c / math.sqrt(vx * vy)

    rec = {"label": label, "n": n, "sd_ln_bd_pct": pct(vx), "sd_ln_bp_pct": pct(vy),
           "corr_legs": r, "lag1_ln_bd": lag1(x), "lag1_ln_bp": lag1(y)}

    print(f"\n### {label}   (n = {n})")
    print()
    print(f"sd(ln baseline decode)  = {pct(vx):.4f} %")
    print(f"sd(ln baseline prefill) = {pct(vy):.4f} %")
    print(f"corr(decode, prefill legs) = {r:+.4f}   "
          f"[lag-1: decode {rec['lag1_ln_bd']:+.4f}, prefill {rec['lag1_ln_bp']:+.4f}]")
    print()

    if c <= 0:
        print("Cov <= 0: the two legs share no positive common factor, so the")
        print("session/measurement split is not identified by this model.")
        rec["identified"] = False
        out.append(rec)
        return rec

    k_lo, k_hi = c / vx, vy / c
    rec.update({"identified": True, "k_lo": k_lo, "k_hi": k_hi})
    print(f"identified set for the prefill loading k: [{k_lo:.4f}, {k_hi:.4f}]")
    print()
    print("| k | sd(session) % | sd(e_decode) % | sd(e_prefill) % | "
          "=> sd(ln cs | fixed tree) % |")
    print("|---|---|---|---|---|")
    grid = sorted({k_lo, (k_lo + 1) / 2 if k_lo < 1 < k_hi else k_lo,
                   1.0 if k_lo <= 1 <= k_hi else (k_lo + k_hi) / 2,
                   (1 + k_hi) / 2 if k_lo < 1 < k_hi else k_hi, k_hi})
    rows = []
    for k in grid:
        vs = c / k
        ved = vx - c / k
        vep = vy - k * c
        ved, vep = max(ved, 0.0), max(vep, 0.0)
        v_cs = 1.125 * ved + 0.125 * vep
        rows.append({"k": k, "sd_session_pct": pct(vs), "sd_e_decode_pct": pct(ved),
                     "sd_e_prefill_pct": pct(vep), "sd_ln_cs_pct": pct(v_cs)})
        star = " **" if abs(k - 1.0) < 1e-12 else ""
        print(f"| {k:.4f}{star} | {pct(vs):.4f} | {pct(ved):.4f} | {pct(vep):.4f} | "
              f"**{pct(v_cs):.4f}**{star} |")
    rec["grid"] = rows
    lo = min(r["sd_ln_cs_pct"] for r in rows)
    hi = max(r["sd_ln_cs_pct"] for r in rows)
    rec["sd_ln_cs_interval_pct"] = [lo, hi]
    at1 = next((r for r in rows if abs(r["k"] - 1.0) < 1e-12), None)
    rec["sd_ln_cs_at_k1_pct"] = at1["sd_ln_cs_pct"] if at1 else None
    print()
    print(f"**identified interval for sigma(ln cs | fixed tree): "
          f"[{lo:.4f} %, {hi:.4f} %]**"
          + (f"; point at k=1: **{at1['sd_ln_cs_pct']:.4f} %**" if at1 else ""))
    out.append(rec)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args()

    rows = fetch()
    good = []
    for r in rows:
        m = r.get("officialMetrics")
        if not isinstance(m, dict):
            continue
        if not m.get("passed_correctness"):
            continue
        if not all(isinstance(m.get(k), (int, float)) and m[k] > 0
                   for k in (BD, BP, CD, CP)):
            continue
        good.append((r, m))
    good.sort(key=lambda rm: rm[0].get("createdAt") or "")

    print("## R106-E section 12: fixed-tree dispersion from the baseline leg")
    print()
    print(f"feed rows {len(rows)}; usable scored sessions **{len(good)}**")

    out = []
    decompose([m[BD] for _r, m in good], [m[BP] for _r, m in good],
              "All scored sessions", out)

    # Validation: reproduce the campaign's published session_factor sd (#555
    # Part 1, 0.5393 % at n = 1185) from these same second moments. ln sf =
    # 0.75 ln bd + 0.25 ln bp + const, so it is fully determined by them.
    xb = [math.log(m[BD]) for _r, m in good]
    yb = [math.log(m[BP]) for _r, m in good]
    vx, vy, c = moments(xb, yb)
    v_sf = 0.5625 * vx + 0.0625 * vy + 0.375 * c
    share_pre = 0.0625 * vy / v_sf
    print()
    print("### Validation against #555 Part 1")
    print()
    print(f"reconstructed sd(ln session_factor) = **{pct(v_sf):.4f} %** "
          f"vs published 0.5393 % (n = 1185; this feed now has {len(good)})")
    print()
    print(f"decomposition of that variance: decode leg "
          f"{100*0.5625*vx/v_sf:.1f} %, prefill leg **{100*share_pre:.1f} %**, "
          f"cross {100*0.375*c/v_sf:.1f} %")
    out.append({"label": "session_factor_reconstruction", "n": len(good),
                "sd_ln_sf_pct": pct(v_sf), "prefill_share": share_pre})

    print()
    print("### Robustness and stationarity")
    print()
    print("| window | n | sd(ln bd) % | sd(ln bp) % | "
          "robust sd(ln bd) % | robust sd(ln bp) % |")
    print("|---|---|---|---|---|---|")
    windows = [("all", good)] + [(f"last {k}", good[-k:])
                                 for k in (400, 200, 100, 50) if len(good) > k]
    for label, sub in windows:
        a = [math.log(m[BD]) for _r, m in sub]
        b = [math.log(m[BP]) for _r, m in sub]
        rec = {"label": f"window {label}", "n": len(sub),
               "sd_ln_bd_pct": 100 * statistics.stdev(a),
               "sd_ln_bp_pct": 100 * statistics.stdev(b),
               "robust_sd_ln_bd_pct": 100 * 1.4826 * mad(a),
               "robust_sd_ln_bp_pct": 100 * 1.4826 * mad(b)}
        out.append(rec)
        print(f"| {label} | {len(sub)} | {rec['sd_ln_bd_pct']:.4f} | "
              f"{rec['sd_ln_bp_pct']:.4f} | {rec['robust_sd_ln_bd_pct']:.4f} | "
              f"{rec['robust_sd_ln_bp_pct']:.4f} |")
    print()
    print("A robust sd far below the plain sd means the leg is heavy-tailed: a "
          "few pathological sessions, not a wide bulk.")

    # Headline. For a FIXED candidate tree measured in the same session:
    #   ln cs = 0.75 (ln bd - ln cd) + 0.25 (ln bp - ln cp)
    #   ln S  = 1.5 ln bd - 0.75 ln cd + 0.5 ln bp - 0.25 ln cp + const
    # Taking each candidate leg to carry the same relative noise as the
    # corresponding baseline leg. rho is the within-session correlation
    # between the baseline and candidate legs of the SAME metric: rho = 1 is
    # a pure common session factor that cancels from the ratio, rho = 0 is
    # leg-specific noise that does not.
    print()
    print("### Headline: sigma for a FIXED candidate tree")
    print()
    print("| rho (within-session baseline/candidate leg corr) | "
          "sigma(ln cs) % | sigma(ln officialScore) % |")
    print("|---|---|---|")
    head = []
    for rho in (0.0, 0.25, 0.5, 0.75, 0.9, 1.0):
        v_cs = (1.125 * vx + 0.125 * vy + 0.375 * c) * (1 - rho)
        v_s = (2.25 * vx + 0.5625 * vx - 2 * 1.5 * 0.75 * rho * vx
               + 0.25 * vy + 0.0625 * vy - 2 * 0.5 * 0.25 * rho * vy
               + 2 * 1.5 * 0.5 * c + 2 * 0.75 * 0.25 * c
               - 2 * (1.5 * 0.25 + 0.5 * 0.75) * rho * c)
        head.append({"rho": rho, "sd_ln_cs_pct": pct(v_cs), "sd_ln_S_pct": pct(v_s)})
        print(f"| {rho:.2f} | {pct(v_cs):.4f} | {pct(v_s):.4f} |")
    out.append({"label": "headline_fixed_tree", "rows": head,
                "sd_ln_bd_pct": pct(vx), "sd_ln_bp_pct": pct(vy),
                "corr_legs": c / math.sqrt(vx * vy)})
    print()
    print("Evidence on rho: the baseline's own two legs, measured back to back "
          f"in one session, correlate only {c / math.sqrt(vx*vy):+.4f}, and the "
          "session-to-session lag-1 autocorrelation of each leg is ~0. Both say "
          "the dominant noise is leg-specific and short-timescale, not a "
          "session-wide multiplicative factor, i.e. rho is small and little of "
          "it cancels from the ratio.")

    if args.out_json:
        with open(args.out_json, "w") as f:
            json.dump({"groups": out, "n_usable": len(good)}, f, indent=2, default=str)


if __name__ == "__main__":
    main()
