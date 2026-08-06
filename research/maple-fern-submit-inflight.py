#!/usr/bin/env python3
"""Exit 0 if the shared account has a submission in flight, 1 if free, 2 if unknown.

The in-flight limit is per solver account ("account already has 1
submission(s) in flight"), so only rows for this campaign's account count;
other solvers validate concurrently and must not gate our dispatch.

Terminal statuses are enumerated positively; anything else counts as in flight,
so a status this script has never seen delays a submit rather than duplicating
one. The dispatcher's forced-attempt timer covers the case where that
classification is wrong in the other direction.
"""
import json
import os
import sys
import urllib.request

FEED = ("https://api.mlx.fast/api/benchmarks/"
        "eigenlabs%2Fmlxfast-challenge/submissions")
ACCOUNT = "morganmcg1"
TERMINAL = {"rejected", "failed", "promoted", "accepted", "cancelled",
            "canceled", "error", "errored", "completed", "complete",
            "superseded", "expired", "timeout", "timed_out"}

try:
    req = urllib.request.Request(
        FEED, headers={"Authorization": "Bearer " + os.environ["MLXFAST_API_TOKEN"]})
    raw = json.load(urllib.request.urlopen(req, timeout=60))
except Exception as exc:  # network/auth/parse: unknown, not "free"
    print(f"listing error: {type(exc).__name__}")
    sys.exit(2)

subs = raw if isinstance(raw, list) else raw.get("submissions", raw.get("data", []))
live = [s for s in subs
        if s.get("solverUsername") == ACCOUNT
        and str(s.get("status", "")).lower() not in TERMINAL]
for s in live:
    print("inflight %s %s %s %s" % (str(s.get("id", "?"))[:7], s.get("status"),
                                    s.get("solverUsername"), s.get("createdAt")))
sys.exit(0 if live else 1)
