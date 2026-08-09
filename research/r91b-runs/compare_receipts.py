#!/usr/bin/env python3
"""Compare two MLXFast receipts field by field and split the score gap into its
decode and prefill contributions under score = D**0.75 * P**0.25.

usage: compare_receipts.py <reference.json> <candidate.json> [ref_label] [cand_label]
"""

import json
import sys

FIELDS = [
    "decode_speedup",
    "prefill_speedup",
    "decode_seconds_per_token",
    "prefill_seconds_per_token",
    "baseline_decode_seconds_per_token",
    "baseline_prefill_seconds_per_token",
    "peak_ram_gb",
    "checked_steps",
    "case_count",
    "max_abs_diff",
    "timestamp",
    "harness_hash",
    "golden_hash",
    "weights_hash",
]


def load(path):
    obj = json.load(open(path))
    return obj.get("submission", obj)


def main():
    ref, cand = load(sys.argv[1]), load(sys.argv[2])
    rl = sys.argv[3] if len(sys.argv) > 3 else "REF"
    cl = sys.argv[4] if len(sys.argv) > 4 else "CAND"
    rm, cm = ref["officialMetrics"], cand["officialMetrics"]

    for label, sub in ((rl, ref), (cl, cand)):
        print(f"{label:<6} id={sub['id']} status={sub['status']} "
              f"score={sub['officialScore']} solver={sub.get('solverUsername')} "
              f"commit={sub.get('submissionCommitSha')}")
    print()

    print(f"{'field':<38} {rl:<26} {cl:<26} ratio")
    for k in FIELDS:
        rv, cv = rm.get(k), cm.get(k)
        ratio = ""
        if isinstance(rv, (int, float)) and isinstance(cv, (int, float)) and rv:
            ratio = f"{cv / rv:.6f}"
        print(f"{k:<38} {str(rv)[:25]:<26} {str(cv)[:25]:<26} {ratio}")
    print()

    d0, p0 = rm["decode_speedup"], rm["prefill_speedup"]
    d1, p1 = cm["decode_speedup"], cm["prefill_speedup"]
    print(f"score identity {rl}: {d0 ** 0.75 * p0 ** 0.25!r} vs reported {ref['officialScore']!r}")
    print(f"score identity {cl}: {d1 ** 0.75 * p1 ** 0.25!r} vs reported {cand['officialScore']!r}")
    print()
    pct = lambda x: f"{x * 100:+.4f} %"
    print(f"decode speedup  {cl} vs {rl}: {pct(d1 / d0 - 1)}")
    print(f"prefill speedup {cl} vs {rl}: {pct(p1 / p0 - 1)}")
    print(f"score contribution, decode : {pct((d1 / d0) ** 0.75 - 1)}")
    print(f"score contribution, prefill: {pct((p1 / p0) ** 0.25 - 1)}")
    print(f"score total                : {pct(cand['officialScore'] / ref['officialScore'] - 1)}")
    print(f"score absolute delta       : {cand['officialScore'] - ref['officialScore']!r}")


main()
