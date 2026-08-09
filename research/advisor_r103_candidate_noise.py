#!/usr/bin/env python3
"""Advisor round-103, part 2: the OTHER half of the record lottery.

Round-102 (#565) established score = cs * L, where
    cs = (MB_D/cand_dec)^0.75 * (MB_P/cand_pre)^0.25     (candidate merit)
    L  = (bl_dec/MB_D)^0.75  * (bl_pre/MB_P)^0.25        (baseline lottery)
and priced the record probability by holding cs FIXED and letting L draw.

That is only half the lottery.  cs is measured from the candidate's own
harness timings, which are noisy, so resubmitting the SAME TREE draws a fresh
cs as well as a fresh L:

    ln score = ln cs + ln L,   both random per receipt.

But the two are measured *in the same harness run on the same host*, so a slow
host inflates cand_dec and bl_dec together and the ratio partly cancels.
Whether the resubmission lottery is wider or narrower than the L-only model
depends entirely on that cancellation, which this script measures three ways:

  (1) Do same-(solver, commit) repeats exist in the corpus at all?
  (2) STOCK-CANDIDATE COHORT.  Receipts whose candidate is (near) the
      unmodified repo are many repeat measurements of a *fixed* tree.  Their
      observed sd(ln score) is the fixed-tree resubmission lottery, directly,
      and corr(ln cand_dec, ln bl_dec) is the common-mode cancellation.
  (3) FAST-CANDIDATE COHORT.  Same statistics restricted to cs > 2.5 receipts,
      where the candidate kernels no longer resemble the baseline's, to check
      whether cancellation survives at the frontier.

usage: advisor_r103_candidate_noise.py <out.json> [--reuse]
"""

import json
import math
import os
import pathlib
import statistics
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

BENCHMARK = "eigenlabs/mlxfast-challenge"
MB_D = 0.013855009542
MB_P = 0.000372473193
RECORD = 2.61650354381456

token = os.environ.get("MLXFAST_API_TOKEN")
base = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")
cfg_path = pathlib.Path.home() / ".config/mlxfast/config.json"
if not token and cfg_path.exists():
    cfg = json.loads(cfg_path.read_text())
    base = cfg.get("apiBaseUrl", base).rstrip("/")
    token = cfg["token"]


def get(path):
    req = urllib.request.Request(
        f"{base}{path}", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.load(resp)


def cs_of(dec, pre):
    return (MB_D / dec) ** 0.75 * (MB_P / pre) ** 0.25


def corr(a, b):
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else float("nan")


def cohort_report(name, sub):
    if len(sub) < 20:
        print(f"\n--- {name}: only n={len(sub)}, skipped")
        return None
    ld = [math.log(r["dec"]) for r in sub]
    lp = [math.log(r["pre"]) for r in sub]
    lbd = [math.log(r["bl_dec"]) for r in sub]
    lbp = [math.log(r["bl_pre"]) for r in sub]
    lcs = [math.log(r["cs"]) for r in sub]
    lL = [math.log(r["L"]) for r in sub]
    lsc = [math.log(r["score"]) for r in sub]
    print(f"\n--- {name}  n={len(sub)}")
    print(f"    sd(ln cand_dec) = {statistics.pstdev(ld)*100:7.4f}%   "
          f"sd(ln bl_dec) = {statistics.pstdev(lbd)*100:7.4f}%   "
          f"corr = {corr(ld, lbd):+.3f}")
    print(f"    sd(ln cand_pre) = {statistics.pstdev(lp)*100:7.4f}%   "
          f"sd(ln bl_pre) = {statistics.pstdev(lbp)*100:7.4f}%   "
          f"corr = {corr(lp, lbp):+.3f}")
    print(f"    sd(ln cs)       = {statistics.pstdev(lcs)*100:7.4f}%   "
          f"sd(ln L)      = {statistics.pstdev(lL)*100:7.4f}%   "
          f"corr = {corr(lcs, lL):+.3f}")
    print(f"    sd(ln SCORE)    = {statistics.pstdev(lsc)*100:7.4f}%   "
          f"<= fixed-tree resubmission lottery, if the tree really is fixed")
    quad = math.sqrt(statistics.pstdev(lcs) ** 2 + statistics.pstdev(lL) ** 2)
    print(f"    independence would predict {quad*100:7.4f}% ; "
          f"observed/predicted = {statistics.pstdev(lsc)/quad:.3f}")
    return statistics.pstdev(lsc)


def main():
    out = pathlib.Path(sys.argv[1])
    if out.exists() and "--reuse" in sys.argv:
        recs = json.loads(out.read_text())
        print(f"reusing {len(recs)} receipts from {out}")
    else:
        if not token:
            sys.exit("no MLXFAST_API_TOKEN")
        bid = get(f"/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}")[
            "benchmark"
        ]["id"]
        rows = get(f"/api/benchmarks/{bid}/submissions")["submissions"]
        recs = []
        for r in rows:
            m = r.get("officialMetrics") or {}
            if not isinstance(m, dict):
                continue
            d, p = m.get("decode_seconds_per_token"), m.get("prefill_seconds_per_token")
            bd = m.get("baseline_decode_seconds_per_token")
            bp = m.get("baseline_prefill_seconds_per_token")
            if not (d and p and bd and bp):
                continue
            recs.append(
                dict(
                    id=r["id"][:8], solver=r.get("solverUsername"),
                    ts=m.get("timestamp") or r.get("createdAt"),
                    commit=(m.get("commit") or r.get("commitSha") or "")[:12],
                    dec=d, pre=p, bl_dec=bd, bl_pre=bp,
                    cs=cs_of(d, p),
                    score=(bd / d) ** 0.75 * (bp / p) ** 0.25,
                    status=r.get("status"),
                )
            )
        recs.sort(key=lambda x: x["ts"] or "")
        out.write_text(json.dumps(recs, indent=1, sort_keys=True))
        print(f"pulled {len(rows)} rows -> {len(recs)} usable -> {out}")

    for r in recs:
        r["L"] = r["score"] / r["cs"]

    # ---- (1) do same-commit repeats exist? ----
    groups = defaultdict(list)
    for r in recs:
        if r["commit"]:
            groups[(r["solver"], r["commit"])].append(r)
    sizes = Counter(len(v) for v in groups.values())
    print(f"\n[1] (solver,commit) groups: {len(groups)}; "
          f"size histogram {dict(sorted(sizes.items()))}")
    nrep = 0
    for (s, c), v in groups.items():
        if len(v) >= 2:
            nrep += 1
            if nrep <= 15:
                cs = "  ".join(f"{x['cs']:.6f}" for x in v)
                sc = "  ".join(f"{x['score']:.6f}" for x in v)
                print(f"    REPEAT {str(s)[:18]:18s} {c} n={len(v)}"
                      f"\n           cs    = {cs}\n           score = {sc}")
    print(f"    total repeated commits: {nrep}")

    # ---- (2)/(3) cohorts ----
    stock = [r for r in recs if abs(r["cs"] - 1.0) < 0.01]
    fast = [r for r in recs if r["cs"] > 2.5]
    sd_stock = cohort_report("STOCK-CANDIDATE COHORT (|cs-1| < 1%)", stock)
    sd_fast = cohort_report("FAST-CANDIDATE COHORT (cs > 2.5)", fast)
    cohort_report("WHOLE CORPUS (candidate varies; upper bound only)", recs)

    # ---- (4) rebuilt record probability under each measured sigma ----
    lL = [math.log(r["L"]) for r in recs]
    sdL = statistics.pstdev(lL)
    print("\n===== P(record) per RESUBMISSION of a FIXED tree of merit cs")
    print("  A : L-only lottery, sigma = sd(ln L)              [the #565 model]")
    print("  B : fixed-tree lottery measured on the STOCK cohort")
    print("  C : fixed-tree lottery measured on the FAST  cohort")
    sigmas = [("A", sdL)]
    if sd_stock:
        sigmas.append(("B", sd_stock))
    if sd_fast:
        sigmas.append(("C", sd_fast))
    for tag, s in sigmas:
        print(f"    sigma_{tag} = {s*100:.4f}%")

    def pnorm_ge(z):
        return 0.5 * math.erfc(z / math.sqrt(2))

    print(f"\n  {'cs':>9s} {'gap%':>7s}   "
          + "  ".join(f"{'P_'+t:>8s}" for t, _ in sigmas) + "   "
          + "  ".join(f"{'N50_'+t:>7s}" for t, _ in sigmas))
    for mcs in (2.575633, 2.582286, 2.585060, 2.588362, 2.590559, 2.591868,
                2.595, 2.600, 2.610):
        gap = math.log(RECORD / mcs)
        ps = [pnorm_ge(gap / s) for _, s in sigmas]
        print(f"  {mcs:9.6f} {gap*100:+7.3f}   "
              + "  ".join(f"{p*100:7.3f}%" for p in ps) + "   "
              + "  ".join(f"{(0.6931/p if p > 0 else float('inf')):7.0f}" for p in ps))

    # ---- (5) our own receipts ----
    ours = [r for r in recs if r["solver"] == "morganmcg1"]
    print(f"\n===== morganmcg1: {len(ours)} receipts, newest 24")
    for r in ours[-24:]:
        print(f"  {r['ts'][:19]} {r['id']} {r['commit'][:8]:8s} "
              f"cs={r['cs']:.6f} L={r['L']:.6f} score={r['score']:.6f} {r['status']}")


if __name__ == "__main__":
    main()
