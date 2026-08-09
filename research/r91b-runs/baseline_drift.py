#!/usr/bin/env python3
"""Tabulate the ranked host's *pinned baseline* timings across every scored
submission on the benchmark.

The baseline is the same frozen implementation in every session, so any change
in `baseline_*_seconds_per_token` measures the session and harness, not the
candidate. That makes it the controlled quantity for asking whether scores are
comparable across sessions.

usage: baseline_drift.py <out.json>
"""

import json
import pathlib
import sys
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"

cfg = json.loads(pathlib.Path.home().joinpath(".config/mlxfast/config.json").read_text())
base = cfg.get("apiBaseUrl", "https://api.mlx.fast").rstrip("/")
token = cfg["token"]


def get(path):
    req = urllib.request.Request(f"{base}{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


bid = get(f"/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}")["benchmark"]["id"]
rows = get(f"/api/benchmarks/{bid}/submissions")["submissions"]

scored = []
for row in rows:
    m = row.get("officialMetrics") or {}
    if not isinstance(m, dict) or m.get("baseline_decode_seconds_per_token") is None:
        continue
    scored.append({
        "id": row["id"][:8],
        "solver": row.get("solverUsername"),
        "status": row.get("status"),
        "score": row.get("officialScore"),
        "ts": m.get("timestamp") or row.get("createdAt"),
        "harness": (m.get("harness_hash") or "")[:8],
        "golden": (m.get("golden_hash") or "")[:8],
        "bl_dec": m.get("baseline_decode_seconds_per_token"),
        "bl_pre": m.get("baseline_prefill_seconds_per_token"),
        "cand_dec": m.get("decode_seconds_per_token"),
        "cand_pre": m.get("prefill_seconds_per_token"),
        "d_su": m.get("decode_speedup"),
        "p_su": m.get("prefill_speedup"),
    })

scored.sort(key=lambda r: r["ts"] or "")
pathlib.Path(sys.argv[1]).write_text(json.dumps(scored, indent=2, sort_keys=True))
print(f"total submissions={len(rows)} scored-with-baseline={len(scored)}")

print("\n=== pinned-baseline timings grouped by harness revision ===")
groups = {}
for r in scored:
    groups.setdefault(r["harness"], []).append(r)
for h, rs in sorted(groups.items(), key=lambda kv: kv[1][0]["ts"] or ""):
    dec = [r["bl_dec"] for r in rs]
    pre = [r["bl_pre"] for r in rs]
    print(f"\nharness {h}  n={len(rs)}  {rs[0]['ts']} .. {rs[-1]['ts']}")
    print(f"  baseline_decode  min={min(dec):.12f} max={max(dec):.12f} mean={sum(dec)/len(dec):.12f}")
    print(f"  baseline_prefill min={min(pre):.12f} max={max(pre):.12f} mean={sum(pre)/len(pre):.12f}")

print("\n=== last 25 scored submissions ===")
print(f"{'id':<9}{'ts':<21}{'harn':<9}{'score':<19}{'bl_dec':<17}{'bl_pre':<19}{'solver'}")
for r in scored[-25:]:
    print(f"{r['id']:<9}{str(r['ts']):<21}{r['harness']:<9}{str(r['score'])[:18]:<19}"
          f"{r['bl_dec']:<17.10f}{r['bl_pre']:<19.12f}{r['solver']}")
