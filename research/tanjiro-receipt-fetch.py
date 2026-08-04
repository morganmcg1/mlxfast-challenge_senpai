#!/usr/bin/env python3
"""Print the official receipt for one or more submission id prefixes.

The per-submission endpoint does not return JSON, so read the list feed (which
publishes complete `officialMetrics` for every non-failed run) and filter.

    python3 research/tanjiro-receipt-fetch.py <feed.json> <id-prefix> [...]
"""
import json
import sys

FIELDS = [
    "prefill_seconds_per_token",
    "decode_seconds_per_token",
    "baseline_prefill_seconds_per_token",
    "baseline_decode_seconds_per_token",
    "prefill_speedup",
    "decode_speedup",
    "passed_correctness",
    "max_abs_diff",
    "passed_prefill_speedup_floor",
    "passed_decode_speedup_floor",
    "gpqa_ttft_seconds",
    "gpqa_ttft_passed",
    "semantic_gpqa_passed",
    "benchmark_wall_seconds",
    "peak_ram_gb",
    "commit",
    "error",
]


def load(path):
    d = json.load(open(path))
    if isinstance(d, list):
        return d
    for key in ("submissions", "items", "data", "results"):
        if isinstance(d.get(key), list):
            return d[key]
    raise SystemExit(f"no submission list in {path}: keys={list(d)}")


def main():
    feed, prefixes = sys.argv[1], sys.argv[2:]
    for s in load(feed):
        sid = s.get("id") or ""
        if not any(sid.startswith(p) for p in prefixes):
            continue
        print(f"=== {sid}")
        for key in ("status", "score", "createdAt", "updatedAt"):
            print(f"  {key:32s} {s.get(key)}")
        for key in ("failureStep", "failedStep", "failureReason", "statusReason"):
            if s.get(key):
                print(f"  {key:32s} {s[key]}")
        m = s.get("officialMetrics") or {}
        if not m:
            print("  officialMetrics                   (none published)")
            continue
        for key in FIELDS:
            if key in m:
                print(f"  {key:32s} {m[key]}")
        p = m.get("prefill_seconds_per_token")
        d = m.get("decode_seconds_per_token")
        if p is not None and d is not None:
            S = 512000.0 * p
            print(f"  -> S (prefill ms)                {S:.4f}")
            print(f"  -> T (decode step ms)            {1000.0 * d - S / 128.0:.5f}")
        bp = m.get("baseline_prefill_seconds_per_token")
        bd = m.get("baseline_decode_seconds_per_token")
        if bp is not None and bd is not None:
            bS = 512000.0 * bp
            print(f"  -> baseline S (ms)               {bS:.4f}")
            print(f"  -> baseline T (ms)               {1000.0 * bd - bS / 128.0:.5f}")


main()
