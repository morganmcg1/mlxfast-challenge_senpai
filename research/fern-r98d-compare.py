#!/usr/bin/env python3
"""Bracketed base/candidate/base comparison for the r98-D local screen."""
import json
import sys

LEGS = [
    ("base A", "research/artifacts/fern-r98d-base-A.json"),
    ("cand  ", "research/artifacts/fern-r98d-rung1-cand.json"),
    ("base B", "research/artifacts/fern-r98d-control-B.json"),
]

rows = []
for name, path in LEGS:
    m = json.load(open(path))["metrics"]
    rows.append(m)
    print(
        name,
        m["timestamp"],
        "commit", m["commit"],
        "wall", m["benchmark_wall_seconds"],
        "decode", m["decode_seconds_per_token"],
        "prefill", m["prefill_seconds_per_token"],
        "maxabs", m["max_abs_diff"],
        "corr", m["passed_correctness"],
    )

a, c, b = (r["decode_seconds_per_token"] for r in rows)
ctrl = (a + b) / 2
print()
print("base mean decode  = %.10f" % ctrl)
print("cand - base mean  = %+.3f us/token (%+.3f %%)" % ((c - ctrl) * 1e6, (c / ctrl - 1) * 100))
print("base B - base A   = %+.3f us/token (%+.3f %%)  <- control-only spread" % ((b - a) * 1e6, (b / a - 1) * 100))

pa, pc, pb = (r["prefill_seconds_per_token"] for r in rows)
print()
print("prefill A/C/B     = %.9f %.9f %.9f" % (pa, pc, pb))
print("prefill B - A     = %+.3f %%  <- must be 0 by construction" % ((pb / pa - 1) * 100))
print("prefill C - A     = %+.3f %%" % ((pc / pa - 1) * 100))

sys.exit(0)
