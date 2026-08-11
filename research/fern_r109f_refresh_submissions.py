#!/usr/bin/env python3
"""fern r109-f: one read-only refresh of the public submissions listing.

Single GET against the benchmark's public `submissions` collection. No writes,
no submission creation, no polling loop -- one shot, then exit. Used for the
bar-raise contingency (item f), the item (d) presence answer and the
one-in-flight-per-solver test.

Usage: research/fern_r109f_refresh_submissions.py <out.json>
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
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv: list[str]) -> int:
    out = argv[0]
    # The ref-based lookup (/api/benchmarks/mlxfast-challenge) 404s; the UUID
    # is the only working handle, as already recorded in the receipt ledger.
    bid = os.environ.get(
        "MLXFAST_BENCHMARK_ID", "1854efdf-feba-4773-bae9-b80520881a74")
    bench = {"id": bid}
    try:
        bench = get("/api/benchmarks/" + urllib.parse.quote(BENCH, safe=""))["benchmark"]
        bid = bench["id"]
    except Exception as exc:  # noqa: BLE001
        print(f"ref lookup {BENCH!r} failed ({exc}); using pinned id {bid}",
              file=sys.stderr)
    print(f"benchmark id={bid}")
    data = get(f"/api/benchmarks/{bid}/submissions")
    rows = data.get("submissions", [])
    print(f"fetched {len(rows)} submissions")
    with open(out, "w") as f:
        json.dump({"submissions": rows, "benchmark": bench}, f)
    print(f"wrote {out}")

    scored = [r for r in rows if isinstance(r.get("officialScore"), (int, float))
              and r["officialScore"] > 0]
    scored.sort(key=lambda r: -r["officialScore"])
    print("\n=== current top 8 by officialScore ===")
    for r in scored[:8]:
        print(f"  {r['officialScore']:.11f} {str(r.get('submissionCommitSha'))[:12]} "
              f"{r.get('solverUsername')} status={r.get('status')} "
              f"promotion={r.get('promotionStatus')} created={r.get('createdAt')}")

    promoted = [r for r in scored if r.get("promotionStatus") == "promoted"]
    print("\n=== current top 6 PROMOTED (the standing bar) ===")
    for r in promoted[:6]:
        print(f"  {r['officialScore']:.11f} {str(r.get('submissionCommitSha'))[:12]} "
              f"{r.get('solverUsername')} finished={r.get('promotionFinishedAt')} "
              f"snapshot={str(r.get('promotionSnapshotRef'))[:12]}")

    live = [r for r in rows if r.get("status") not in
            ("completed", "failed", "accepted", "rejected", "cancelled", "error")]
    print(f"\n=== non-terminal rows right now: {len(live)} ===")
    for r in live[:20]:
        print(f"  {r['id'][:8]} {r.get('solverUsername')} status={r.get('status')} "
              f"created={r.get('createdAt')} updated={r.get('updatedAt')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
