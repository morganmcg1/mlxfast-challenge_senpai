#!/usr/bin/env python3
"""Does an official run that misses a speedup floor still publish its metrics?

Answering this decides how large an output-neutral work injection may be. If a
floor breach is reported as `rejected` with complete `officialMetrics`, the
0.95 floors are not binding constraints on a measurement submission and the
lever arm can be chosen purely for fit precision.
"""
import json
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/subs.json"


def main():
    subs = json.load(open(PATH))["submissions"]
    below = []
    for s in subs:
        m = s.get("officialMetrics") or {}
        d = m.get("decode_speedup")
        p = m.get("prefill_speedup")
        if d is None or p is None:
            continue
        if d < 0.95 or p < 0.95:
            below.append((s, m, d, p))
    print(f"{len(subs)} submissions; {len(below)} publish a speedup below the 0.95 floor")
    keys = ("prefill_seconds_per_token", "decode_seconds_per_token",
            "baseline_decode_seconds_per_token", "passed_correctness")
    for s, m, d, p in below[:12]:
        have = sum(1 for k in keys if k in m)
        print(f"  {s.get('status'):10} decode {d:6.3f} prefill {p:6.3f} "
              f"metric-keys {len(m):3d} core {have}/{len(keys)} "
              f"score {str(m.get('score'))[:8]:8} {str(s.get('id'))[:8]}")
    statuses = {}
    for s, _, _, _ in below:
        statuses[s.get("status")] = statuses.get(s.get("status"), 0) + 1
    print("  status histogram:", statuses)

    pub = [(s, (s.get("officialMetrics") or {})) for s in subs]
    dec = sorted((m["decode_speedup"], s.get("status"), str(s.get("id"))[:8])
                 for s, m in pub if m.get("decode_speedup") is not None)
    pre = sorted((m["prefill_speedup"], s.get("status"), str(s.get("id"))[:8])
                 for s, m in pub if m.get("prefill_speedup") is not None)
    print(f"\n{len(dec)} receipts publish decode_speedup; slowest five:")
    for v, stt, i in dec[:5]:
        print(f"  {v:7.4f} {stt:10} {i}")
    print(f"{len(pre)} receipts publish prefill_speedup; slowest five:")
    for v, stt, i in pre[:5]:
        print(f"  {v:7.4f} {stt:10} {i}")
    nom = sum(1 for s in subs if not (s.get("officialMetrics") or {}))
    print(f"\n{nom} submissions publish no officialMetrics at all")


if __name__ == "__main__":
    main()
