#!/usr/bin/env python3
"""Print one official receipt's axes and gate verdicts by id prefix.

Usage: pr34_receipt.py <subs.json> <id-prefix> [...]
"""

from __future__ import annotations

import json
import sys

KEYS = (
    "passed_correctness",
    "max_abs_diff",
    "passed_prefill_speedup_floor",
    "passed_decode_speedup_floor",
    "prefill_speedup",
    "decode_speedup",
    "gpqa_ttft_seconds",
    "gpqa_ttft_max_seconds",
    "gpqa_ttft_passed",
    "semantic_gpqa_passed",
    "benchmark_wall_seconds",
    "peak_ram_gb",
    "error",
)


def main() -> None:
    path, prefixes = sys.argv[1], sys.argv[2:]
    subs = json.load(open(path))["submissions"]
    for s in subs:
        sid = s.get("id") or ""
        if not any(sid.startswith(p) for p in prefixes):
            continue
        m = s.get("officialMetrics") or {}
        print(f"=== {sid}")
        print(
            f"  status={s.get('status')} officialScore={s.get('officialScore')} "
            f"reason={s.get('rejectionReason')}"
        )
        print(f"  created={s.get('createdAt')} updated={s.get('updatedAt')}")
        if m.get("prefill_seconds_per_token"):
            S = 512_000.0 * m["prefill_seconds_per_token"]
            T = 1000.0 * m["decode_seconds_per_token"] - S / 128.0
            bS = 512_000.0 * m["baseline_prefill_seconds_per_token"]
            bT = 1000.0 * m["baseline_decode_seconds_per_token"]
            print(f"  S={S:.4f} ms   T={T:.5f} ms")
            print(f"  baseline S={bS:.4f} ms   baseline T={bT:.5f} ms")
            for k in KEYS:
                if k in m:
                    print(f"  {k} = {m[k]}")
        else:
            print("  (no timed metrics yet)")


if __name__ == "__main__":
    main()
