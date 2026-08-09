#!/usr/bin/env python3
"""Pull the full ranked-receipt listing and report raw candidate timings.

The listing endpoint carries `officialMetrics` for every scored submission on
the benchmark, including the raw `decode_seconds_per_token` /
`prefill_seconds_per_token` of the candidate and of that session's pinned
baseline.  Raw timings are the only sound cross-session comparison (rule 47).

usage: pull_receipts.py <out.json> [solver] [n_tail]
"""

import json
import pathlib
import sys
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"
MB_D = 0.013855009542
MB_P = 0.000372473193

cfg = json.loads(pathlib.Path.home().joinpath(".config/mlxfast/config.json").read_text())
base = cfg.get("apiBaseUrl", "https://api.mlx.fast").rstrip("/")
token = cfg["token"]


def get(path):
    req = urllib.request.Request(f"{base}{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def common_score(dec, pre):
    return (MB_D / dec) ** 0.75 * (MB_P / pre) ** 0.25


def main():
    out = pathlib.Path(sys.argv[1])
    solver = sys.argv[2] if len(sys.argv) > 2 else None
    tail = int(sys.argv[3]) if len(sys.argv) > 3 else 20

    bid = get(f"/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}")["benchmark"]["id"]
    rows = get(f"/api/benchmarks/{bid}/submissions")["submissions"]

    scored = []
    for row in rows:
        m = row.get("officialMetrics") or {}
        if not isinstance(m, dict) or m.get("decode_seconds_per_token") is None:
            continue
        dec = m["decode_seconds_per_token"]
        pre = m["prefill_seconds_per_token"]
        scored.append({
            "id": row["id"][:8],
            "full_id": row["id"],
            "solver": row.get("solverUsername"),
            "status": row.get("status"),
            "score": row.get("officialScore"),
            "ts": m.get("timestamp") or row.get("createdAt"),
            "commit": (m.get("commit") or "")[:8],
            "bl_dec": m.get("baseline_decode_seconds_per_token"),
            "bl_pre": m.get("baseline_prefill_seconds_per_token"),
            "cand_dec": dec,
            "cand_pre": pre,
            "dec_su": m.get("decode_speedup"),
            "pre_su": m.get("prefill_speedup"),
            "cs": common_score(dec, pre),
        })
    scored.sort(key=lambda r: r["ts"] or "")
    out.write_text(json.dumps(scored, indent=2, sort_keys=True))
    print(f"wrote {out} ({len(scored)} scored receipts)")

    sel = [r for r in scored if solver is None or r["solver"] == solver][-tail:]
    hdr = f"{'id':10s} {'ts':21s} {'commit':9s} {'cand_dec':14s} {'cand_pre':16s} {'bl_dec':14s} {'bl_pre':16s} {'score':10s} {'cs':10s}"
    print(hdr)
    for r in sel:
        print("%-10s %-21s %-9s %-14.12f %-16.14f %-14.12f %-16.14f %-10.6f %-10.6f" % (
            r["id"], (r["ts"] or "")[:20], r["commit"], r["cand_dec"], r["cand_pre"],
            r["bl_dec"] or float("nan"), r["bl_pre"] or float("nan"),
            r["score"] or float("nan"), r["cs"]))


if __name__ == "__main__":
    main()
