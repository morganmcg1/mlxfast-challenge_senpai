#!/usr/bin/env python3
"""R106-J: recover the REAL per-run correctness evidence from the preserved
score JSONs.

Motivation: `max_abs_diff` is hard-coded to 0 at every emission site in
Sources/MLXFastTrustedHarness/{LagunaRuntimeBenchmark,LagunaRuntimeLocalIterate}.swift,
and `golden_hash` is sha256 of the golden *fixture file* (an input), not of the
emitted token stream. Neither field carries output information. The fields that
do are `passed`, `passed_correctness`, `checked_steps`, `case_count`,
`first_failing_case`, `first_failing_step` and `error`.
"""
import collections
import glob
import json
import re
import sys

FIELDS = [
    "passed_correctness",
    "checked_steps",
    "case_count",
    "first_failing_case",
    "first_failing_step",
    "error",
    "golden_hash",
    "max_abs_diff",
    "harness_hash",
]


def rec_of(path):
    j = json.load(open(path))
    m = j.get("metrics", {})
    out = [j.get("passed")]
    for k in FIELDS:
        v = m.get(k)
        if k in ("golden_hash", "harness_hash") and isinstance(v, str):
            v = v[:16]
        if k == "error":
            v = (v or "")[:60]
        out.append(v)
    return tuple(out)


def show(label, paths):
    agg = collections.Counter(rec_of(p) for p in paths)
    print("%s: %d run(s), %d distinct correctness signature(s)" % (label, len(paths), len(agg)))
    for rec, n in agg.most_common():
        print("  n=%d" % n)
        print("    passed              = %r" % (rec[0],))
        for k, v in zip(FIELDS, rec[1:]):
            print("    %-19s = %r" % (k, v))


def main():
    d = "research/artifacts/maple-fern-r106j/abba_t0_t0p"
    runs = sorted(
        glob.glob(d + "/run*.json"),
        key=lambda p: int(re.search(r"run(\d+)\.", p).group(1)),
    )
    t0 = [p for p in runs if ".T0." in p]
    t0p = [p for p in runs if ".T0P." in p]
    show("ALL sweep runs", runs)
    print()
    show("T0 arm", t0)
    print()
    show("T0P arm", t0p)
    print()
    show("final_head", ["research/artifacts/maple-fern-r106j/final_head.score.json"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
