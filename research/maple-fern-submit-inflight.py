#!/usr/bin/env python3
"""Report whether the shared solver account has a submission in flight.

Two modes, same exit contract (0 = in flight, 1 = free, 2 = unknown):

    inflight.py            discovery: read the whole submission feed and print
                           every non-terminal row for this account
    inflight.py <id>       watch: read one submission by id and report whether
                           that specific row is still non-terminal

The in-flight limit is per solver account ("account already has 1
submission(s) in flight"), so only rows for this campaign's account count;
other solvers validate concurrently and must not gate our dispatch.

Why two modes. The feed is oldest-first, has no working `limit`/`status`/`id`
filter, ignores `Range`, and costs 17.3 MB (8.3 MB gzipped, ~1-3 s) per read,
so it cannot be polled quickly. `GET /api/submissions/<id>` returns the same
row shape in 13.6 KB in ~0.6 s. Once discovery has named the blocking row,
watching that row costs 1/600th of a feed read, so the dispatcher can detect a
freed slot in seconds while using *less* bandwidth than a two-minute feed poll.

Terminal statuses are enumerated positively; anything else counts as in flight,
so a status this script has never seen delays a submit rather than duplicating
one. The dispatcher's forced-attempt timer covers the opposite error.
"""
import gzip
import json
import os
import sys
import urllib.request

API = "https://api.mlx.fast/api"
BENCH = "eigenlabs%2Fmlxfast-challenge"
ACCOUNT = "morganmcg1"
TERMINAL = {"rejected", "failed", "promoted", "accepted", "cancelled",
            "canceled", "error", "errored", "completed", "complete",
            "superseded", "expired", "timeout", "timed_out"}


def get(path):
    req = urllib.request.Request(
        API + "/" + path,
        headers={"Authorization": "Bearer " + os.environ["MLXFAST_API_TOKEN"],
                 "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return json.loads(raw)


def live(row):
    return str(row.get("status", "")).lower() not in TERMINAL


def show(row):
    print("inflight %s %s %s %s" % (row.get("id"), row.get("status"),
                                    row.get("solverUsername"),
                                    row.get("createdAt")))


watch = sys.argv[1] if len(sys.argv) > 1 else None
try:
    if watch:
        row = get("submissions/" + watch)["submission"]
        if live(row):
            show(row)
            sys.exit(0)
        print("terminal %s %s" % (row.get("id"), row.get("status")))
        sys.exit(1)
    raw = get("benchmarks/%s/submissions" % BENCH)
    subs = raw if isinstance(raw, list) else raw.get("submissions",
                                                     raw.get("data", []))
    rows = [s for s in subs if s.get("solverUsername") == ACCOUNT and live(s)]
    for row in rows:
        show(row)
    sys.exit(0 if rows else 1)
except Exception as exc:  # network/auth/parse/missing row: unknown, not "free"
    print("listing error: %s" % type(exc).__name__)
    sys.exit(2)
