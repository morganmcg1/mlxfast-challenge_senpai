#!/usr/bin/env python3
"""r103-D rung 0: pull the ranked-receipt corpus with EVERY field preserved.

Read-only official API. Never submits, never prints the token.

usage: fern_r103d_pull.py <out-raw.json> [--detail SUBMISSION_ID_PREFIX ...]
"""

import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"

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
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def main():
    out = pathlib.Path(sys.argv[1])
    bid = get(f"/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}")["benchmark"]["id"]
    rows = get(f"/api/benchmarks/{bid}/submissions")["submissions"]
    out.write_text(json.dumps(rows, indent=1, sort_keys=True))
    print(f"pulled {len(rows)} raw receipts -> {out}")

    top_keys = {}
    metric_keys = {}
    for r in rows:
        for k, v in r.items():
            top_keys[k] = top_keys.get(k, 0) + (v is not None)
        m = r.get("officialMetrics")
        if isinstance(m, dict):
            for k, v in m.items():
                metric_keys[k] = metric_keys.get(k, 0) + (v is not None)
    print(f"\ntop-level fields (non-null count of {len(rows)}):")
    for k, c in sorted(top_keys.items(), key=lambda kv: -kv[1]):
        print(f"  {k:26s} {c:5d}")
    print("\nofficialMetrics fields:")
    for k, c in sorted(metric_keys.items(), key=lambda kv: -kv[1]):
        print(f"  {k:40s} {c:5d}")

    for pref in sys.argv[2:]:
        hit = [r for r in rows if r["id"].startswith(pref)]
        if not hit:
            print(f"\n[detail] no receipt matching {pref}")
            continue
        rid = hit[0]["id"]
        for path in (f"/api/submissions/{rid}", f"/api/benchmarks/{bid}/submissions/{rid}"):
            try:
                d = get(path)
            except Exception as exc:  # noqa: BLE001
                print(f"\n[detail] {path} -> {type(exc).__name__}: {exc}")
                continue
            print(f"\n[detail] {path} ->")
            print(json.dumps(d, indent=1, sort_keys=True)[:4000])


if __name__ == "__main__":
    main()
