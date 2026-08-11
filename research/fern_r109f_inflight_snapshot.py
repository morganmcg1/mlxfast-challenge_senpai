#!/usr/bin/env python3
"""READ-ONLY: snapshot the public submissions collection and report rows-in-flight.

Creates no submission.  One HTTP GET per invocation against the same public
collection endpoint used by research/advisor_r106_channel_idle_watch.py.

Why this exists: observed sojourn is a monotone function of how many rows are
in flight when a row is created (medians 16.8 / 17.9 / 24.5 / 30.7 / 40.2 /
43.3 / 57.6 min for inflight 0/1/2/3/4/5/6+).  So the safe last-fire time is
not a fixed clock value -- it is a lookup on a single observable that anyone
can read in five seconds before firing.

Usage: python3 research/fern_r109f_inflight_snapshot.py [--save out.json]
"""
import argparse
import datetime
import json
import os
import sys
import urllib.parse
import urllib.request

BASE = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")
BENCHMARK = os.environ.get("MLXFAST_BENCHMARK", "eigenlabs/mlxfast-challenge")
TERMINAL = {"rejected", "failed", "accepted", "promoted", "completed", "error"}
CLOSE = datetime.datetime(2026, 8, 11, 17, 0, tzinfo=datetime.timezone.utc)

# p90 sojourn (minutes) by rows-in-flight at creation, from 1860 terminal rows
# Curve with the 6+ clamp OPENED (see ledger 8.1) and our own account premium
# folded in: p90 proxy = max(global p90_k, 1.415 x global median_k), ledger 8.3.
# The old clamped table stopped at 6 and understated the endgame regime.
MED_BY_INFLIGHT = {0: 16.8, 1: 17.9, 2: 24.5, 3: 30.7, 4: 40.0, 5: 43.0,
                   6: 50.7, 7: 45.8, 8: 58.0, 9: 60.7, 10: 60.6}
P90_BY_INFLIGHT = {0: 22.3, 1: 25.4, 2: 34.5, 3: 43.2, 4: 57.9, 5: 67.0,
                   6: 80.0, 7: 100.6, 8: 99.5, 9: 113.3, 10: 111.7}
MAX_K = max(P90_BY_INFLIGHT)


def token():
    for k in ("MLXFAST_API_TOKEN", "MLXFAST_TOKEN"):
        v = os.environ.get(k)
        if v:
            return v.strip()
    return None


def get(url, tok):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {tok}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save")
    a = ap.parse_args()

    tok = token()
    if not tok:
        print("no MLXFAST_API_TOKEN available", file=sys.stderr)
        return 3

    b = get(f"{BASE}/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}", tok)
    bid = (b.get("benchmark") or b)["id"]
    doc = get(f"{BASE}/api/benchmarks/{bid}/submissions", tok)
    rows = doc.get("submissions", doc.get("data", doc)) if isinstance(doc, dict) else doc

    now = datetime.datetime.now(datetime.timezone.utc)
    if a.save:
        json.dump({"submissions": rows, "fetched_at": now.isoformat()},
                  open(a.save, "w"))

    live = [r for r in rows if str(r.get("status", "")).lower() not in TERMINAL]
    live.sort(key=lambda r: r.get("createdAt") or "")
    print(f"fetched_at={now.isoformat()}  rows={len(rows)}  IN FLIGHT={len(live)}")
    for r in live:
        c = datetime.datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
        age = (now - c).total_seconds() / 60.0
        mine = " <== OURS" if r.get("solverUsername") == "morganmcg1" else ""
        print(f"  {r['id'][:8]}  {str(r.get('status')):<11} {r.get('solverUsername'):<12} "
              f"created={r['createdAt'][11:19]}Z  age={age:6.1f}m{mine}")

    # price a shot fired right now
    k = min(len(live), MAX_K)      # a new row would see this many ahead of it
    med, p90 = MED_BY_INFLIGHT[k], P90_BY_INFLIGHT[k]
    budget = (CLOSE - now).total_seconds() / 60.0
    print(f"\nIf a shot were fired NOW it would see inflight={k}"
          f"{'+' if k == MAX_K else ''}: expected {med:.1f}m, p90 {p90:.1f}m")
    print(f"  budget to 17:00Z = {budget:.1f}m  ->  "
          f"{'SAFE' if budget > p90 else ('MARGINAL' if budget > med else 'TOO LATE')} "
          f"(need > p90={p90:.1f}m for safe)")
    print(f"  last safe fire at this concurrency = "
          f"{(CLOSE - datetime.timedelta(minutes=p90)).strftime('%H:%M')}Z")
    return 0


if __name__ == "__main__":
    sys.exit(main())
