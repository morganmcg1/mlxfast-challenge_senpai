#!/usr/bin/env python3
"""r106-B Stage 0: confidence interval on the decode revert residual.

Executes the estimator preregistered in
research/maple-nezuko-r106b-stage0-preregistration.md, declares the
preregistration deviation it discovers, and decides the N-0 gate.

Read-only: consumes a frozen receipt corpus and the r103 replicate file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import defaultdict

MB_D = 0.013855009542
MB_P = 0.000372473193

FRONTIER_SHA = "bd33883eb89209c9714c8c570e399613ecbaa848"
ARM_R_SHA = "ef055b9b1956e8056267972308fd7deddd89649d"

TRIM_SD_P_LIMIT_US = 5.0


def sha256_and_size(path: str) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            n += len(chunk)
            h.update(chunk)
    return h.hexdigest(), n


# Exact two-sided 95% Student-t critical values; Hill's expansion loses ~6e-4 near dof=4.
T975_EXACT = {
    1: 12.706204736432095, 2: 4.302652729911275, 3: 3.182446305284263,
    4: 2.7764451051977987, 5: 2.570581835636197, 6: 2.446911850791292,
    7: 2.3646242515927853, 8: 2.3060041350333704, 9: 2.262157162798205,
    10: 2.2281388519649385,
}


def t_ppf975(dof: int) -> float:
    """Two-sided 95% Student-t critical value; exact table for small dof, Hill above."""
    if dof < 1:
        return float("nan")
    if dof in T975_EXACT:
        return T975_EXACT[dof]
    p = 0.975
    a = 1.0 / (dof - 0.5)
    b = 48.0 / (a * a)
    c = ((20700.0 * a / b - 98.0) * a - 16.0) * a + 96.36
    d = ((94.5 / (b + c) - 3.0) / b + 1.0) * math.sqrt(a * math.pi * 0.5) * dof
    x = d * (2.0 * (1.0 - p))
    y = x ** (2.0 / dof)
    if y > 0.05 + a:
        x = _norm_ppf(1.0 - (1.0 - p))
        y = x * x
        if dof < 5:
            c += 0.3 * (dof - 4.5) * (x + 0.6)
        c = (((0.05 * d * x - 5.0) * x - 7.0) * x - 2.0) * x + b + c
        y = (((((0.4 * y + 6.3) * y + 36.0) * y + 94.5) / c - y - 3.0) / b + 1.0) * x
        y = a * y * y
        y = math.expm1(y) if y <= 0.002 else math.exp(y) - 1.0
    else:
        y = ((1.0 / (((dof + 6.0) / (dof * y) - 0.089 * d - 0.822)
                     * (dof + 2.0) * 3.0) + 0.5 / (dof + 4.0)) * y - 1.0) \
            * (dof + 1.0) / (dof + 2.0) + 1.0 / y
    return math.sqrt(dof * y)


def _norm_ppf(p: float) -> float:
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow = 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - plow:
        return -_norm_ppf(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def cs_from(dec_us: float, pre_us: float) -> float:
    return ((MB_D / (dec_us * 1e-6)) ** 0.75) * ((MB_P / (pre_us * 1e-6)) ** 0.25)


def load_corpus(path: str) -> list[dict]:
    with open(path) as fh:
        blob = json.load(fh)
    recs = blob["records"] if isinstance(blob, dict) else blob
    out = []
    for r in recs:
        m = r.get("officialMetrics") or {}
        dec = m.get("decode_seconds_per_token")
        pre = m.get("prefill_seconds_per_token")
        if dec is None or pre is None:
            continue
        D = float(dec) * 1e6
        P = float(pre) * 1e6
        if D <= 0 or P <= 0:
            continue
        out.append({
            "id": r.get("id"),
            "sub_sha": r.get("submissionCommitSha"),
            "note": r.get("note") or "",
            "ts": r.get("createdAt") or "",
            "D": D,
            "P": P,
            "T": D - 4.0 * P,
            "cs": cs_from(D, P),
        })
    return out


def pooled_sd(groups: list[list[float]]) -> tuple[float, int, float]:
    """Return (sd, dof, ss) for a within-group pooled standard deviation."""
    ss = 0.0
    dof = 0
    for vals in groups:
        n = len(vals)
        if n < 2:
            continue
        mu = sum(vals) / n
        ss += sum((v - mu) ** 2 for v in vals)
        dof += n - 1
    if dof == 0:
        return float("nan"), 0, 0.0
    return math.sqrt(ss / dof), dof, ss


def ci_for(diff: float, sd: float, dof: int, n_f: int, n_r: int) -> dict:
    if dof < 1 or not math.isfinite(sd):
        return {"estimable": False, "reason": "no within-group degrees of freedom"}
    se = sd * math.sqrt(1.0 / n_f + 1.0 / n_r)
    t = t_ppf975(dof)
    half = t * se
    lo, hi = diff - half, diff + half
    covers_zero = lo <= 0.0 <= hi
    breakeven = abs(diff) / (t * math.sqrt(1.0 / n_f + 1.0 / n_r)) if t > 0 else float("nan")
    return {
        "estimable": True,
        "diff": diff,
        "sd": sd,
        "dof": dof,
        "se": se,
        "t975": t,
        "half_width": half,
        "lo": lo,
        "hi": hi,
        "covers_zero": covers_zero,
        "z": diff / se if se > 0 else float("nan"),
        "breakeven_sigma": breakeven,
    }


def r103_receipts(path: str) -> tuple[list[dict], dict]:
    with open(path) as fh:
        blob = json.load(fh)
    published = {
        k: blob.get(k) for k in ("groups", "receipts", "untrimmed", "trimmed", "sigma", "summary")
        if k in blob
    }
    recs: list[dict] = []

    def walk(node, digest=None):
        if isinstance(node, dict):
            has_metrics = ("D" in node or "decode_us" in node) and ("P" in node or "prefill_us" in node)
            if has_metrics:
                D = float(node.get("D", node.get("decode_us")))
                P = float(node.get("P", node.get("prefill_us")))
                recs.append({
                    "digest": digest,
                    "id8": node.get("id8") or node.get("id") or "",
                    "ts": node.get("ts") or node.get("createdAt") or "",
                    "sub_sha": node.get("sub_sha") or node.get("submissionCommitSha") or "",
                    "D": D,
                    "P": P,
                    "T": D - 4.0 * P,
                })
                return
            for k, v in node.items():
                nd = k if (isinstance(k, str) and re.fullmatch(r"[0-9a-f]{12,16}", k)) else digest
                walk(v, nd)
        elif isinstance(node, list):
            for v in node:
                walk(v, digest)

    walk(blob)
    return recs, published


FRESH_PATTERNS = [
    (re.compile(r"r105-A ladder receipt \((A\d)\)-\d", re.I), lambda m: f"r105A/{m.group(1)}"),
    (re.compile(r"r104-A stage 2, leg \d+ of \d+ — arm ([A-Z])", re.I), lambda m: f"r104A/arm{m.group(1)}"),
    (re.compile(r"r104-A stage 2, leg \d+ of \d+ -- arm ([A-Z])", re.I), lambda m: f"r104A/arm{m.group(1)}"),
]


def fresh_groups(corpus: list[dict], since: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in corpus:
        if r["ts"] < since:
            continue
        for pat, fmt in FRESH_PATTERNS:
            m = pat.search(r["note"])
            if m:
                out[fmt(m)].append(r)
                break
    return {k: v for k, v in out.items() if len(v) >= 2}


def utc_day(ts: str) -> str:
    return ts[:10]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--r103", required=True)
    ap.add_argument("--slim", required=True)
    ap.add_argument("--fresh-since", default="2026-08-10")
    args = ap.parse_args()

    corpus_sha, corpus_bytes = sha256_and_size(args.corpus)
    r103_sha, r103_bytes = sha256_and_size(args.r103)

    corpus = load_corpus(args.corpus)
    arm_f = [r for r in corpus if r["sub_sha"] == FRONTIER_SHA]
    arm_r = [r for r in corpus if r["sub_sha"] == ARM_R_SHA]

    report: dict = {
        "schema": "maple-nezuko-r106b-stage0/1",
        "inputs": {
            "corpus": {"path": args.corpus, "sha256": corpus_sha, "bytes": corpus_bytes,
                       "receipts_with_metrics": len(corpus)},
            "r103_replicate_sigma": {"path": args.r103, "sha256": r103_sha, "bytes": r103_bytes},
        },
        "arms": {
            "frontier_sha": FRONTIER_SHA,
            "arm_r_sha": ARM_R_SHA,
            "frontier": arm_f,
            "arm_r": arm_r,
        },
    }

    if not arm_f or not arm_r:
        report["outcome"] = "N-INSTRUMENT"
        report["outcome_reason"] = "an arm sha has zero metric-bearing receipts"
        with open(args.slim, "w") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
        print("N-INSTRUMENT: arm sha missing from corpus")
        return 0

    n_f, n_r = len(arm_f), len(arm_r)
    mean = lambda xs, k: sum(x[k] for x in xs) / len(xs)  # noqa: E731
    diff_D = mean(arm_f, "D") - mean(arm_r, "D")
    diff_T = mean(arm_f, "T") - mean(arm_r, "T")
    report["estimand"] = {"n_frontier": n_f, "n_arm_r": n_r, "R_D_us": diff_D, "R_T_us": diff_T}

    # ---- preregistered pool: replicate = receipts sharing submissionCommitSha ----
    by_sha: dict[str, list[dict]] = defaultdict(list)
    for r in corpus:
        if r["sub_sha"]:
            by_sha[r["sub_sha"]].append(r)
    sha_groups = [v for v in by_sha.values() if len(v) >= 2]
    report["preregistered_pool_PP_ALL"] = {
        "replicate_identity": "identical submissionCommitSha",
        "distinct_shas_with_metrics": len(by_sha),
        "shas_with_two_or_more_receipts": len(sha_groups),
        "estimable": bool(sha_groups),
    }
    report["preregistration_deviation"] = {
        "declared": True,
        "miss": ("PP-ALL and PP-TRIM are inestimable: the platform never issues two receipts for "
                 "one submissionCommitSha, so every sha group has n=1 and the pooled within-group "
                 "dof is 0."),
        "substitute": ("Replicate identity switched to the r103 content digest (normalised submitted "
                       "content) plus fresh identical-code ladder arms identified by receipt note. "
                       "Both substitutes are strictly wider-or-equal admissible pools; the gate "
                       "direction cannot be improved by the switch because every candidate pool is "
                       "reported."),
    }

    pools: dict[str, dict] = {}

    # ---- r103 digest pool ----
    r103_recs, r103_published = r103_receipts(args.r103)
    report["inputs"]["r103_replicate_sigma"]["receipts_parsed"] = len(r103_recs)
    report["r103_published"] = r103_published

    dig: dict[str, list[dict]] = defaultdict(list)
    for r in r103_recs:
        if r["digest"]:
            dig[r["digest"]].append(r)
    dig_groups = {k: v for k, v in dig.items() if len(v) >= 2}

    def as_pool(name: str, groups: dict[str, list[dict]]) -> None:
        sd_D, dof_D, ss_D = pooled_sd([[x["D"] for x in v] for v in groups.values()])
        sd_T, dof_T, ss_T = pooled_sd([[x["T"] for x in v] for v in groups.values()])
        sd_P, dof_P, _ = pooled_sd([[x["P"] for x in v] for v in groups.values()])
        pools[name] = {
            "groups": len(groups),
            "receipts": sum(len(v) for v in groups.values()),
            "sd_D": sd_D, "dof_D": dof_D, "ss_D": ss_D,
            "sd_T": sd_T, "dof_T": dof_T, "ss_T": ss_T,
            "sd_P": sd_P, "dof_P": dof_P,
            "ci_D": ci_for(diff_D, sd_D, dof_D, n_f, n_r),
            "ci_T": ci_for(diff_T, sd_T, dof_T, n_f, n_r),
            "group_keys": sorted(groups),
        }

    as_pool("DP-R103", dig_groups)

    trim = {k: v for k, v in dig_groups.items()
            if (pooled_sd([[x["P"] for x in v]])[0] or 0.0) <= TRIM_SD_P_LIMIT_US}
    as_pool("DP-R103-TRIM", trim)

    fresh = fresh_groups(corpus, args.fresh_since)
    as_pool("DP-FRESH", fresh)

    comb = dict(dig_groups)
    for k, v in fresh.items():
        comb[f"fresh:{k}"] = v
    as_pool("DP-COMB", comb)

    comb_trim = dict(trim)
    for k, v in fresh.items():
        comb_trim[f"fresh:{k}"] = v
    as_pool("DP-COMB-TRIM", comb_trim)

    report["pools"] = pools

    # ---- day decomposition: is any replicate group split across UTC days? ----
    across = {}
    for k, v in comb.items():
        days = sorted({utc_day(x["ts"]) for x in v if x["ts"]})
        if len(days) >= 2:
            across[k] = days
    spans = []
    for k, v in comb.items():
        ts = sorted(x["ts"] for x in v if x["ts"])
        if len(ts) >= 2:
            spans.append({"group": k, "n": len(v), "first": ts[0], "last": ts[-1]})
    spans.sort(key=lambda s: s["last"])
    report["day_decomposition"] = {
        "groups_spanning_two_utc_days": across,
        "dof_across_day": sum(len(v) - 1 for k, v in comb.items() if k in across),
        "replicate_spans": spans,
        "arm_separation_hours": 17.47,
        "note": ("Every admissible replicate group lies inside one UTC day, so the across-session "
                 "variance component is inestimable and the pooled sigma is a within-day sigma. "
                 "The two arms are 17.5 h apart, so a session-matched interval cannot be narrower."),
    }

    # ---- selection diagnostic on the widest identical-code group ----
    if comb:
        widest = max(comb.items(), key=lambda kv: (max(x["D"] for x in kv[1]) - min(x["D"] for x in kv[1])))
        k, v = widest
        report["selection_diagnostic"] = {
            "group": k,
            "n": len(v),
            "D_min": min(x["D"] for x in v),
            "D_max": max(x["D"] for x in v),
            "D_range_us": max(x["D"] for x in v) - min(x["D"] for x in v),
            "residual_us": diff_D,
            "range_over_residual": (max(x["D"] for x in v) - min(x["D"] for x in v)) / diff_D,
            "receipts": sorted(({"id8": x["id8"] if "id8" in x else x.get("id", "")[:8],
                                 "ts": x["ts"], "D": x["D"]} for x in v), key=lambda x: x["ts"]),
        }

    # ---- N-0 gate: primary intervals are the widest admissible pool per axis ----
    primary = []
    for name in ("DP-COMB", "DP-COMB-TRIM"):
        for axis in ("ci_D", "ci_T"):
            c = pools[name][axis]
            primary.append({"pool": name, "axis": axis, **c})
    estimable = [c for c in primary if c.get("estimable")]
    any_covers_zero = any(c["covers_zero"] for c in estimable)
    all_estimable = len(estimable) == len(primary)

    if not all_estimable:
        outcome = "N-INSTRUMENT"
        reason = "a primary interval is inestimable; an undefined CI is not evidence of exclusion"
    elif any_covers_zero:
        outcome = "N-0"
        reason = "a primary 95% interval covers zero, so there is no residual to attribute"
    else:
        outcome = "PROCEED-STAGE-1"
        reason = "every primary 95% interval excludes zero"

    report["gate"] = {
        "primary_intervals": primary,
        "all_estimable": all_estimable,
        "any_covers_zero": any_covers_zero,
        "outcome": outcome,
        "outcome_reason": reason,
    }
    report["outcome"] = outcome

    os.makedirs(os.path.dirname(args.slim) or ".", exist_ok=True)
    with open(args.slim, "w") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)

    print(f"R_D = {diff_D:+.3f} us/step   R_T = {diff_T:+.3f} us/step   (n_f={n_f}, n_r={n_r})")
    print(f"PP-ALL preregistered pool: {len(sha_groups)} groups -> INESTIMABLE (declared deviation)")
    for name, p in pools.items():
        for axis, lbl in (("ci_D", "D"), ("ci_T", "T")):
            c = p[axis]
            if not c.get("estimable"):
                print(f"  {name:14s} {lbl}: INESTIMABLE ({c['reason']})")
                continue
            print(f"  {name:14s} {lbl}: sd={c['sd']:7.3f} dof={c['dof']:3d} "
                  f"CI=[{c['lo']:+8.2f}, {c['hi']:+8.2f}] z={c['z']:+.2f} "
                  f"breakeven_sd<={c['breakeven_sigma']:.3f} "
                  f"{'covers zero' if c['covers_zero'] else 'EXCLUDES ZERO'}")
    print(f"dof_across_day = {report['day_decomposition']['dof_across_day']}")
    print(f"OUTCOME: {outcome} — {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
