#!/usr/bin/env python3
"""Advisor r104: refresh the STANDING RECORD and re-price a receipt.

Why: every round-104 scheduling decision (nezuko spends the round's only 8
receipts) is priced against the standing global record as of
2026-08-08T09:17:33Z -- a-github-name, score 2.616504, cs 2.574594, L 1.016278.
That is over a day stale. If the record advanced, P(record)/receipt falls and
the value of an un-levered receipt falls with it.

Round-103 established (advisor-r103-what-winning-costs.md SS1) that
`status == accepted` <=> a new GLOBAL record: tested over 1205 receipts,
"beat global running max" survives 146/147.

Field names follow advisor_r103_freeze_corpus.py (rule 58) --
officialMetrics.{decode,prefill}_seconds_per_token and their baselines.

READ-ONLY. Never submits. Never prints the token.

usage: advisor_r104_record_watch.py [since_iso]
"""

import json
import math
import os
import pathlib
import sys
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"
MB_D = 0.013855009542
MB_P = 0.000372473193

# frozen round-103 reference points
REF_RECORD_TS = "2026-08-08T09:17:33Z"
REF_RECORD_SCORE = 2.616504
REF_RECORD_CS = 2.574594
OUR_HONEST_CS = 2.583111
SD_LN_SCORE = 0.004595  # 0.4595 %
MEDIAN_L = 0.998572

token = os.environ.get("MLXFAST_API_TOKEN")
base = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")
cfg_path = pathlib.Path.home() / ".config/mlxfast/config.json"
if not token and cfg_path.exists():
    cfg = json.loads(cfg_path.read_text())
    base = cfg.get("apiBaseUrl", base).rstrip("/")
    token = cfg["token"]
if not token:
    sys.exit("no MLXFAST_API_TOKEN and no ~/.config/mlxfast/config.json")

SECRET = token


def get(path):
    req = urllib.request.Request(
        f"{base}{path}", headers={"Authorization": f"Bearer {SECRET}"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def cs_of(dec, pre):
    return (MB_D / dec) ** 0.75 * (MB_P / pre) ** 0.25


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def main():
    since = sys.argv[1] if len(sys.argv) > 1 else REF_RECORD_TS
    bid = get(f"/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}")["benchmark"]["id"]
    rows = get(f"/api/benchmarks/{bid}/submissions")["submissions"]
    print(f"pulled {len(rows)} raw submission records")

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
        cs = cs_of(d, p)
        score = (bd / d) ** 0.75 * (bp / p) ** 0.25
        recs.append(
            dict(
                sid=str(r.get("id", ""))[:8],
                who=r.get("solverUsername") or "?",
                ts=str(m.get("timestamp") or r.get("createdAt") or ""),
                cs=cs,
                score=score,
                L=score / cs,
                status=(r.get("status") or "").lower(),
                dec_us=d * 1e6,
                pre_us=p * 1e6,
            )
        )
    recs.sort(key=lambda x: x["ts"])
    print(f"{len(recs)} metric-bearing receipts")

    acc = [d for d in recs if d["status"] == "accepted"]
    print(f"{len(acc)} accepted (== global records)")
    if not acc:
        sys.exit("no accepted receipts found")

    best = max(acc, key=lambda d: d["score"])
    print("\n===== STANDING RECORD =====")
    print(f"  ts     {best['ts']}")
    print(f"  solver {best['who']}")
    print(f"  score  {best['score']:.6f}")
    print(f"  cs     {best['cs']:.6f}    L {best['L']:.6f}")
    print(f"  T-ish decode {best['dec_us']:.3f} us/step   prefill {best['pre_us']:.4f} us/tok")
    print(f"  our honest cs {OUR_HONEST_CS:.6f} = {100*(OUR_HONEST_CS/best['cs']-1):+.3f} % vs record cs")

    print("\n===== vs the round-103 frozen reference =====")
    print(f"  ref  {REF_RECORD_TS}  score {REF_RECORD_SCORE:.6f}  cs {REF_RECORD_CS:.6f}")
    moved = best["score"] > REF_RECORD_SCORE + 1e-9
    print(f"  RECORD MOVED: {moved}")
    if moved:
        print(f"  advance: {100*(best['score']/REF_RECORD_SCORE-1):+.4f} %")

    newer = [d for d in recs if d["ts"] > since]
    print(f"\n===== {len(newer)} receipts since {since} =====")
    for d in newer[-30:]:
        print(f"  {d['ts']}  {d['who'][:20]:20s} {d['score']:.6f} cs {d['cs']:.6f} {d['status']}")

    newacc = [d for d in newer if d["status"] == "accepted"]
    print(f"\n  of which accepted (new records): {len(newacc)}")
    for d in newacc:
        print(f"    {d['ts']}  {d['who'][:20]:20s} {d['score']:.6f}  cs {d['cs']:.6f}")

    # how many receipts have BETTER cs than the standing record?
    better_cs = [d for d in recs if d["cs"] > best["cs"]]
    print(f"\n  receipts with cs better than the record's cs: {len(better_cs)} / {len(recs)}")

    # ---- re-price a receipt against the CURRENT record ----
    target = best["score"]
    print("\n===== P(new record) per receipt, at the CURRENT record =====")
    print(f"  model: ln score ~ N(ln(cs*{MEDIAN_L}), sd={SD_LN_SCORE:.6f}), must beat {target:.6f}")
    print(f"  {'d_cs':>7} {'cs':>10} {'P/receipt':>11} {'n@50%':>8} {'n@90%':>8}")
    for dcs_pct in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
        cs = OUR_HONEST_CS * (1 + dcs_pct / 100.0)
        mu = math.log(cs * MEDIAN_L)
        z = (math.log(target) - mu) / SD_LN_SCORE
        p = 1.0 - norm_cdf(z)
        if p <= 0:
            print(f"  {dcs_pct:6.2f}% {cs:10.6f} {'~0':>10}  {'inf':>8} {'inf':>8}")
            continue
        n50 = math.log(0.5) / math.log(1 - p) if p < 1 else 1.0
        n90 = math.log(0.1) / math.log(1 - p) if p < 1 else 1.0
        print(f"  {dcs_pct:6.2f}% {cs:10.6f} {100*p:10.3f}% {n50:8.1f} {n90:8.1f}")

    # 8-receipt budget (nezuko's round-104 spend)
    print("\n===== nezuko's 8-receipt budget =====")
    for dcs_pct in (0.0, 0.5, 1.0, 1.5):
        cs = OUR_HONEST_CS * (1 + dcs_pct / 100.0)
        mu = math.log(cs * MEDIAN_L)
        z = (math.log(target) - mu) / SD_LN_SCORE
        p = 1.0 - norm_cdf(z)
        print(f"  d_cs {dcs_pct:4.2f}%  P(>=1 record in 8) = {100*(1-(1-p)**8):6.2f} %")


if __name__ == "__main__":
    main()
