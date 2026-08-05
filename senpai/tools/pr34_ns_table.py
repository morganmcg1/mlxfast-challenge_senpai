#!/usr/bin/env python3
"""Tabulate every receipt on candidate axes plus the pinned-reference score `ns`.

Usage: pr34_ns_table.py <subs.json> <label>:<id-prefix> [...]

`ns` replaces `officialScore` for ranking. It divides by pinned constants
instead of the same-session baseline arm, so the 1.932% prefill and 0.248%
decode spread of that pinned-code baseline arm never enters the number.

    ns = (0.013890 / decode_s_per_tok)**0.75 * (0.0003845 / prefill_s_per_tok)**0.25
"""

from __future__ import annotations

import json
import sys

REF_DECODE_SPT = 0.013890
REF_PREFILL_SPT = 0.0003845


def ns(m: dict) -> float:
    d = REF_DECODE_SPT / m["decode_seconds_per_token"]
    p = REF_PREFILL_SPT / m["prefill_seconds_per_token"]
    return d**0.75 * p**0.25


def main() -> int:
    subs = json.load(open(sys.argv[1]))["submissions"]
    want = [a.split(":", 1) for a in sys.argv[2:]]
    by_prefix = {}
    for s in subs:
        for label, pre in want:
            if s.get("id", "").startswith(pre):
                by_prefix[label] = s

    hdr = ("label", "receipt", "status", "S", "T", "bS", "bT", "Dcand", "ns", "official")
    print(f"{hdr[0]:<10} {hdr[1]:<10} {hdr[2]:<9} {hdr[3]:>9} {hdr[4]:>8} "
          f"{hdr[5]:>9} {hdr[6]:>9} {hdr[7]:>8} {hdr[8]:>9} {hdr[9]:>9}")
    for label, pre in want:
        s = by_prefix.get(label)
        if s is None:
            print(f"{label:<10} {pre:<10} MISSING")
            continue
        m = s.get("officialMetrics") or {}
        st = s.get("status", "?")
        if "decode_seconds_per_token" not in m:
            print(f"{label:<10} {s['id'][:8]:<10} {st:<9} no timed metrics")
            continue
        S = 512_000.0 * m["prefill_seconds_per_token"]
        bS = 512_000.0 * m["baseline_prefill_seconds_per_token"]
        T = 1000.0 * m["decode_seconds_per_token"] - S / 128.0
        bT = 1000.0 * m["baseline_decode_seconds_per_token"] - bS / 128.0
        D = 1000.0 * m["decode_seconds_per_token"]
        off = s.get("officialScore")
        off_s = f"{off:.6f}" if isinstance(off, (int, float)) else "n/a"
        print(f"{label:<10} {s['id'][:8]:<10} {st:<9} {S:9.4f} {T:8.5f} "
              f"{bS:9.4f} {bT:9.5f} {D:8.5f} {ns(m):9.6f} {off_s:>9}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
