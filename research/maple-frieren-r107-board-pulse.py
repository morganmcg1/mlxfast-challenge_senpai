#!/usr/bin/env python3
"""R107 board pulse — read-only.

Three questions the draw ladder needs answered periodically:

  1. Is the record target still 2.61650354381456, or has someone moved it?
     (If it moves, the required draw `ln(target/cs)` moves and the pricing in
     research/maple-frieren-r107-session-noise.md is stale.)
  2. What is the actual receipt throughput right now?  Rule 95.1 assumed
     ~0.9 receipts/h; the ladder budget is linear in this number.
  3. What is the state of our in-flight submission, if one was named?

Never writes to the repo and never submits.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import urllib.request
from datetime import datetime, timedelta, timezone

FEED = ("https://api.mlx.fast/api/benchmarks/"
        "1854efdf-feba-4773-bae9-b80520881a74/submissions")
MB_D = 0.013855009542
MB_P = 0.000372473193
RECORD = 2.61650354381456
OUR_CS = 2.590559          # 4b0e051b merit
SIGMAS = (0.5269, 0.5503, 0.5546)


def fetch(url):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {os.environ['MLXFAST_API_TOKEN']}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def dig(obj, *names):
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k in names and isinstance(v, (int, float)) and not isinstance(v, bool):
                    return float(v)
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def sdig(obj, *names):
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k in names and isinstance(v, str) and v:
                    return v
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission", default=None)
    ap.add_argument("--hours", type=float, default=24.0)
    args = ap.parse_args()

    feed = fetch(FEED)
    subs = feed["submissions"] if isinstance(feed, dict) and "submissions" in feed else feed
    now = datetime.now(timezone.utc)

    rows = []
    for s in subs:
        official = dig(s, "officialScore", "official_score")
        ts = parse_ts(sdig(s, "createdAt", "created_at", "submittedAt", "completedAt"))
        sha = sdig(s, "submissionCommitSha", "submission_commit_sha", "commitSha")
        sid = sdig(s, "id", "submissionId", "submission_id")
        if official is None:
            continue
        cd = dig(s, "decodeSecondsPerToken", "decode_seconds_per_token")
        cp = dig(s, "prefillSecondsPerToken", "prefill_seconds_per_token")
        cs = None
        if cd and cp and min(cd, cp) > 0:
            cs = (MB_D / cd) ** 0.75 * (MB_P / cp) ** 0.25
        rows.append({"official": official, "ts": ts, "sha": sha, "id": sid, "cs": cs})

    print(f"feed receipts with an officialScore: {len(rows)}")

    # --- 1. record target ---------------------------------------------------
    top = sorted(rows, key=lambda r: -r["official"])[:5]
    print("\nTOP 5 BY officialScore")
    print("  rank |  officialScore  |    cs    |    f %   | sha      | when")
    for i, r in enumerate(top, 1):
        f = 100 * math.log(r["official"] / r["cs"]) if r["cs"] else float("nan")
        cs = f"{r['cs']:.6f}" if r["cs"] else "   n/a  "
        when = r["ts"].strftime("%m-%dT%H:%M") if r["ts"] else "?"
        sha = (r["sha"] or "?")[:8]
        print(f"  {i:>4} | {r['official']:.12f} | {cs} | {f:+8.4f} | {sha} | {when}")

    best = top[0]["official"]
    print(f"\nrecord on record (rule 95.1): {RECORD:.11f}")
    print(f"record on the feed now:       {best:.11f}")
    if abs(best - RECORD) < 1e-9:
        print("  -> UNCHANGED; pricing stands.")
    else:
        print(f"  -> ** MOVED by {100*math.log(best/RECORD):+.4f} % ** pricing is stale.")

    # --- 2. throughput ------------------------------------------------------
    print(f"\nTHROUGHPUT over trailing windows (all solvers)")
    for h in (3, 6, 12, args.hours):
        cut = now - timedelta(hours=h)
        n = sum(1 for r in rows if r["ts"] and r["ts"] >= cut)
        print(f"  last {h:>5.1f} h: {n:>4} receipts  = {n/h:5.2f} /h")

    # --- 3. pricing at the live target -------------------------------------
    need = math.log(best / OUR_CS) * 100
    print(f"\nPRICING from our tree (cs {OUR_CS:.6f}) against the live target")
    print(f"  required session factor: {need:+.4f} %")
    print("  sigma % |   z   | P/draw % | P(12) % | P(18) % | P(24) %")
    for s in SIGMAS:
        z = need / s
        p = 0.5 * math.erfc(z / math.sqrt(2))
        row = " | ".join(f"{100*(1-(1-p)**k):7.1f}" for k in (12, 18, 24))
        print(f"  {s:7.4f} | {z:5.3f} | {100*p:8.3f} | {row}")

    # --- 4. our in-flight submission ---------------------------------------
    if args.submission:
        hit = [r for r in rows if r["id"] == args.submission]
        print(f"\nSUBMISSION {args.submission}")
        if not hit:
            print("  not present in the public feed yet (still queued/validating).")
        else:
            r = hit[0]
            f = 100 * math.log(r["official"] / r["cs"]) if r["cs"] else float("nan")
            print(f"  officialScore {r['official']:.12f}")
            print(f"  cs            {r['cs']:.6f}" if r["cs"] else "  cs n/a")
            print(f"  f             {f:+.4f} %")
            print(f"  sha           {r['sha']}")
            print(f"  beats record? {'YES' if r['official'] > RECORD else 'no'}")


if __name__ == "__main__":
    main()
