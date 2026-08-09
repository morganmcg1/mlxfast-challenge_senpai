#!/usr/bin/env python3
"""Round-103: map every morganmcg1 receipt to its submitted commit SHA.

Purpose: our best-ever candidate merit is cs = 2.590559 (2026-08-09), but the
merged advisor frontier measured only cs = 2.582286 on #565's receipt. That is
a 0.320 % gap in candidate speed that the three "restorations" did NOT recover.
This script localises which commit produced each high-cs receipt so the gap can
be diffed rather than guessed.

usage: advisor_r103_our_commits.py [out.json]
"""

import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"
MB_D = 0.013855009542
MB_P = 0.000372473193
US = "morganmcg1"

token = os.environ.get("MLXFAST_API_TOKEN")
base = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")
cfg_path = pathlib.Path.home() / ".config/mlxfast/config.json"
if not token and cfg_path.exists():
    cfg = json.loads(cfg_path.read_text())
    base = cfg.get("apiBaseUrl", base).rstrip("/")
    token = cfg["token"]
if not token:
    sys.exit("no MLXFAST_API_TOKEN and no ~/.config/mlxfast/config.json")


def get(path):
    req = urllib.request.Request(
        f"{base}{path}", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def main():
    bid = get(f"/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}")["benchmark"]["id"]
    rows = get(f"/api/benchmarks/{bid}/submissions")["submissions"]
    mine = [r for r in rows if r.get("solverUsername") == US]
    recs = []
    for r in mine:
        m = r.get("officialMetrics") or {}
        if not isinstance(m, dict):
            continue
        d, p = m.get("decode_seconds_per_token"), m.get("prefill_seconds_per_token")
        bd = m.get("baseline_decode_seconds_per_token")
        bp = m.get("baseline_prefill_seconds_per_token")
        if not (d and p and bd and bp):
            continue
        cs = (MB_D / d) ** 0.75 * (MB_P / p) ** 0.25
        score = (bd / d) ** 0.75 * (bp / p) ** 0.25
        recs.append(
            dict(
                id=r["id"][:8],
                commit=(r.get("commitSha") or r.get("commit") or m.get("commit") or "")[:12],
                ts=m.get("timestamp") or r.get("createdAt"),
                cs=cs,
                score=score,
                L=score / cs,
                dec=d,
                pre=p,
                status=r.get("status"),
            )
        )
    recs.sort(key=lambda x: -x["cs"])
    print(f"morganmcg1 receipts with metrics: {len(recs)}")
    print(f"  {'rank':>4s} {'cs':>10s} {'score':>10s} {'L':>9s} {'dec us/tok':>11s} "
          f"{'pre us/tok':>11s} {'sub':>9s} {'commit':>13s}  ts")
    for i, r in enumerate(recs, 1):
        print(f"  {i:4d} {r['cs']:10.6f} {r['score']:10.6f} {r['L']:9.6f} "
              f"{r['dec']*1e6:11.3f} {r['pre']*1e6:11.3f} {r['id']:>9s} "
              f"{r['commit']:>13s}  {r['ts']}")
    if len(sys.argv) > 1:
        pathlib.Path(sys.argv[1]).write_text(json.dumps(recs, indent=1, sort_keys=True))

    # the gap that matters
    best = recs[0]
    cur = [r for r in recs if r["id"].startswith("e08d759f")]
    if cur:
        c = cur[0]
        print(f"\nbest-ever cs {best['cs']:.6f} ({best['id']}, commit {best['commit']})")
        print(f"merged frontier cs {c['cs']:.6f} ({c['id']}, commit {c['commit']})")
        print(f"gap = {(best['cs']/c['cs'] - 1)*100:+.4f} % of candidate merit")
        print(f"  decode leg: {(c['dec']/best['dec'] - 1)*100:+.4f} % slower than best")
        print(f"  prefill leg: {(c['pre']/best['pre'] - 1)*100:+.4f} % slower than best")


if __name__ == "__main__":
    main()
