#!/usr/bin/env python3
"""Low-rate read-only channel poller for the r109-f endgame.

Emits one JSON line per poll: rows in flight, the arrival rate, our own rows'
states, and -- when a row we are tracking goes terminal -- its exact sojourn and
score. Because `updatedAt` is the terminal timestamp, a slow poll loses no
accuracy on sojourn measurement, so the interval is deliberately long to keep the
load on the service trivial.

Read-only: one GET per poll. Creates no submission, fires nothing.

Usage:
  python3 research/fern_r109f_channel_poll.py [--interval 600] [--until 15:15]
                                              [--track 5fae2f13]
"""
import argparse
import datetime
import json
import os
import sys
import time
import urllib.parse
import urllib.request

TERMINAL = {"rejected", "failed", "accepted", "promoted", "completed", "error"}
OURS = "morganmcg1"
BASE = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")
BENCHMARK = os.environ.get("MLXFAST_BENCHMARK", "eigenlabs/mlxfast-challenge")
CLOSE = datetime.datetime(2026, 8, 11, 17, 0, tzinfo=datetime.timezone.utc)

# p90 proxy per rows-in-flight; ledger 8.3
P90 = {0: 22.3, 1: 25.4, 2: 34.5, 3: 43.2, 4: 57.9, 5: 67.0,
       6: 80.0, 7: 100.6, 8: 99.5, 9: 113.3, 10: 111.7}
MED = {0: 16.8, 1: 17.9, 2: 24.5, 3: 30.7, 4: 40.0, 5: 43.0,
       6: 50.7, 7: 45.8, 8: 58.0, 9: 60.7, 10: 60.6}


def token():
    for k in ("MLXFAST_API_TOKEN", "MLXFAST_TOKEN"):
        v = os.environ.get(k)
        if v:
            return v.strip()
    return None


def get(url, tok):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {tok}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())


def emit(obj):
    print(json.dumps(obj), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=600)
    ap.add_argument("--until", default="15:15", help="stop at this UTC HH:MM")
    ap.add_argument("--track", action="append", default=[])
    a = ap.parse_args()

    hh, mm = (int(x) for x in a.until.split(":"))
    stop = datetime.datetime(2026, 8, 11, hh, mm, tzinfo=datetime.timezone.utc)

    tok = token()
    if not tok:
        print("no MLXFAST_API_TOKEN available", file=sys.stderr)
        return 3

    b = get(f"{BASE}/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}", tok)
    bid = (b.get("benchmark") or b)["id"]
    url = f"{BASE}/api/benchmarks/{bid}/submissions"

    seen_terminal = set()
    while True:
        now = datetime.datetime.now(datetime.timezone.utc)
        if now >= stop:
            emit({"event": "poller_done", "at": now.isoformat()})
            return 0
        try:
            doc = get(url, tok)
        except Exception as exc:
            emit({"event": "poll_error", "at": now.isoformat(), "error": str(exc)})
            time.sleep(a.interval)
            continue

        rows = doc.get("submissions", doc.get("data", doc)) if isinstance(doc, dict) else doc
        live = [r for r in rows if str(r.get("status", "")).lower() not in TERMINAL]
        k = min(len(live), max(P90))
        budget = (CLOSE - now).total_seconds() / 60.0
        lsf = (CLOSE - datetime.timedelta(minutes=P90[k])).strftime("%H:%MZ")

        # arrivals in the last hour
        hour_ago = now - datetime.timedelta(hours=1)
        arrivals = sum(
            1 for r in rows if r.get("createdAt")
            and datetime.datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00")) >= hour_ago)

        rec = {
            "event": "poll", "at": now.isoformat(), "inflight": len(live),
            "arrivals_last_hour": arrivals,
            "expected_sojourn_min": MED[k], "p90_sojourn_min": P90[k],
            "budget_to_close_min": round(budget, 1),
            "last_safe_fire": lsf,
            "safe_to_fire_now": budget > P90[k],
            "ours_live": [r["id"][:8] for r in live if r.get("solverUsername") == OURS],
        }
        emit(rec)

        # report any tracked row that has just gone terminal
        for r in rows:
            sid = r["id"][:8]
            if sid in seen_terminal:
                continue
            if a.track and not any(sid.startswith(t[:8]) for t in a.track):
                continue
            if str(r.get("status", "")).lower() in TERMINAL:
                seen_terminal.add(sid)
                c = datetime.datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
                u = r.get("updatedAt")
                soj = ((datetime.datetime.fromisoformat(u.replace("Z", "+00:00")) - c)
                       .total_seconds() / 60.0) if u else None
                emit({"event": "TRACKED_TERMINAL", "at": now.isoformat(),
                      "id": sid, "status": r.get("status"),
                      "created": r.get("createdAt"), "updated": u,
                      "sojourn_min": round(soj, 1) if soj is not None else None,
                      "score": r.get("score"), "user": r.get("solverUsername")})

        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
