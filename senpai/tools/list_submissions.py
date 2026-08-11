#!/usr/bin/env python3
"""List this account's official submissions with status, score and timing.

Read-only channel telemetry for the advisor: shows whether the one official
slot is busy, how long the last draw took, and the raw decode/prefill legs of
every terminal receipt.

Usage: list_submissions.py [limit]
Reads MLXFAST_API_TOKEN from the environment.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

API = os.environ.get("MLXFAST_API_URL", "https://api.mlx.fast")
TOKEN = os.environ.get("MLXFAST_API_TOKEN", "")
BENCH = os.environ.get("MLXFAST_BENCHMARK", "mlxfast-challenge")


def get(path: str) -> dict:
    req = urllib.request.Request(
        API.rstrip("/") + path,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv: list[str]) -> int:
    limit = int(argv[0]) if argv else 25
    account_id = get("/api/me")["account"]["id"]
    bench = None
    try:
        bench = get("/api/benchmarks/" + urllib.parse.quote(BENCH, safe=""))["benchmark"]
    except Exception as exc:  # noqa: BLE001
        print(f"ref {BENCH!r}: {exc}", file=sys.stderr)
    if bench is None:
        cands = [
            b
            for b in get("/api/benchmarks")["benchmarks"]
            if "mlxfast" in str(b.get("name", "")).lower()
        ]
        print("mlxfast benchmarks: " + ", ".join(f"{b['name']}={b['id']}" for b in cands),
              file=sys.stderr)
        if not cands:
            return 1
        bench = cands[0]
    rows = get(f"/api/benchmarks/{bench['id']}/submissions")["submissions"]
    mine = [r for r in rows if r.get("solverAccountId") == account_id]
    mine.sort(key=lambda r: str(r.get("createdAt", "")), reverse=True)
    print(f"account={account_id} benchmark={bench['id']} total_mine={len(mine)}")
    keys = (
        "id", "status", "score", "createdAt", "updatedAt", "startedAt",
        "completedAt", "commitSha", "note", "error", "message",
    )
    for r in mine[:limit]:
        print("-" * 72)
        for k in keys:
            if k in r and r[k] not in (None, ""):
                v = str(r[k])
                print(f"  {k}: {v[:200]}")
        extra = {k: v for k, v in r.items() if k not in keys}
        print("  other: " + json.dumps(extra, sort_keys=True)[:600])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
