#!/usr/bin/env python3
"""Research-only (PR #301): summarise the Stage 3 end-to-end ABBA.

Reads the `*.score.json` copies produced by
`research/maple_shared_qmv_local_iterate_abba.sh` and reports, per arm and per
scored axis, the mean / sd / standard error together with Welch two-sample 95 %
confidence intervals for every arm pair. Both scored axes are kept separate:
`--local-iterate` runs one 512-token prefill and a 128-step teacher-forced
decode pass, and the challenge scores them with different weights and separate
floors.

    python3 research/maple_shared_qmv_stage3_stats.py /tmp/maple-shared-qmv-stage3-r*

Filenames must keep the driver's `<idx>-rep<N>-<arm>.score.json` shape; the
index is used for the position-balance check.
"""
from __future__ import annotations

import glob
import json
import math
import os
import re
import sys

AXES = (
    ("prefill_seconds_per_token", "prefill s/tok"),
    ("decode_seconds_per_token", "decode s/tok"),
)
NAME_RE = re.compile(r"^(\d+)-rep(\d+)-([a-z]+)\.score\.json$")

# Welch two-sided 95 % critical values by degrees of freedom. df is floored and
# clamped at 30 so a fractional df never picks a value smaller than the exact
# one; above 30 the 2.042 entry is still conservative against the 1.96 limit.
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
       14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
       20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
       26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}


def t95(df: float) -> float:
    if df <= 0:
        return float("nan")
    return T95[min(30, max(1, int(math.floor(df))))]


def mean(xs):
    return sum(xs) / len(xs)


def sd(xs):
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def welch(a, b):
    """Return (delta = mean(b) - mean(a), half_width, df)."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return mean(b) - mean(a), float("nan"), 0.0
    va, vb = sd(a) ** 2 / na, sd(b) ** 2 / nb
    se = math.sqrt(va + vb)
    df = (va + vb) ** 2 / (va ** 2 / (na - 1) + vb ** 2 / (nb - 1)) if se else 0.0
    return mean(b) - mean(a), t95(df) * se, df


def arm_values(rows, arms, key):
    """Per-arm value lists. Runs that failed correctness carry zeroed timings
    and must never enter an arm mean."""
    return {a: [r[key] for r in rows
                if r["arm"] == a and r[key] is not None and r["passed_correctness"]]
            for a in arms}


def load(paths):
    rows = []
    for pattern in paths:
        expanded = glob.glob(pattern) if any(c in pattern for c in "*?[") else [pattern]
        for entry in expanded:
            if os.path.isdir(entry):
                expanded_dir = sorted(glob.glob(os.path.join(entry, "*.score.json")))
            else:
                expanded_dir = [entry]
            for path in expanded_dir:
                m = NAME_RE.match(os.path.basename(path))
                if not m:
                    print(f"skip (unparsed name): {path}", file=sys.stderr)
                    continue
                with open(path) as fh:
                    doc = json.load(fh)
                metrics = doc.get("metrics", {})
                rows.append({
                    "path": path,
                    "src": os.path.basename(os.path.dirname(os.path.abspath(path))),
                    "idx": int(m.group(1)),
                    "rep": int(m.group(2)),
                    "arm": m.group(3),
                    "prefill_seconds_per_token": metrics.get("prefill_seconds_per_token"),
                    "decode_seconds_per_token": metrics.get("decode_seconds_per_token"),
                    "passed_correctness": metrics.get("passed_correctness"),
                    "checked_steps": metrics.get("checked_steps"),
                    "error": metrics.get("error"),
                    "score": doc.get("score"),
                    "passed": doc.get("passed"),
                })
    return sorted(rows, key=lambda r: (r["src"], r["rep"], r["idx"]))


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    rows = load(argv[1:])
    if not rows:
        print("no score files found", file=sys.stderr)
        return 1

    arms = []
    for r in rows:
        if r["arm"] not in arms:
            arms.append(r["arm"])

    blocks = sorted(set((r["src"], r["rep"]) for r in rows))
    print(f"runs: {len(rows)}  reps: {len(blocks)}  arms: {arms}")
    print(f"rep blocks (launch dir, rep): {blocks}")
    bad = [r for r in rows if not r["passed_correctness"]]
    steps = sorted(set(r["checked_steps"] for r in rows))
    print(f"passed_correctness: {len(rows) - len(bad)}/{len(rows)}  checked_steps: {steps}")
    for r in bad:
        print(f"  CORRECTNESS FAIL: {r['path']}")

    print("\nper-run values")
    print(f"{'run':<46} {'arm':<9} {'prefill s/tok':>14} {'decode s/tok':>14} {'corr':>5}")
    for r in rows:
        tag = f"{r['src']}/{os.path.basename(r['path']).replace('.score.json', '')}"
        print(f"{tag:<46} {r['arm']:<9} {r['prefill_seconds_per_token']:>14.8f} "
              f"{r['decode_seconds_per_token']:>14.8f} {str(r['passed_correctness']):>5}")

    good = [r for r in rows if r["passed_correctness"]]
    for key, label in AXES:
        by_arm = arm_values(good, arms, key)
        print(f"\n=== {label} ===")
        print(f"{'arm':<9} {'n':>3} {'mean':>13} {'sd':>12} {'se':>12} {'cv%':>7}")
        for a in arms:
            xs = by_arm[a]
            if not xs:
                print(f"{a:<9} {0:>3} {'-':>13} {'-':>12} {'-':>12} {'-':>7}")
                continue
            m, s = mean(xs), sd(xs)
            se = s / math.sqrt(len(xs))
            print(f"{a:<9} {len(xs):>3} {m:>13.8f} {s:>12.8f} {se:>12.8f} "
                  f"{100.0 * s / m:>7.3f}")
        for i, a in enumerate(arms):
            for b in arms[i + 1:]:
                xa, xb = by_arm[a], by_arm[b]
                if not xa or not xb:
                    print(f"{a} -> {b}: no comparison (n={len(xa)} vs {len(xb)})")
                    continue
                d, hw, df = welch(xa, xb)
                base = mean(xa)
                head = (f"{a} -> {b}: delta {d:+.8f} ({100.0 * d / base:+.3f} %)")
                if math.isnan(hw):
                    print(f"{head} 95% CI undefined: n={len(xa)} vs {len(xb)}, "
                          f"replication insufficient - point estimate only")
                    continue
                print(f"{head} 95% CI [{d - hw:+.8f}, {d + hw:+.8f}] "
                      f"([{100.0 * (d - hw) / base:+.3f} %, "
                      f"{100.0 * (d + hw) / base:+.3f} %]) df {df:.1f}")

        print("position balance (mean index within a rep, correct runs only):")
        for a in arms:
            idxs = [r["idx"] for r in good if r["arm"] == a]
            if not idxs:
                print(f"  {a:<9} no correct runs")
                continue
            per_rep = [((i - 1) % max(1, len(arms) * 2)) + 1 for i in idxs]
            print(f"  {a:<9} raw idx mean {mean(idxs):.2f} "
                  f"in-rep slot mean {mean(per_rep):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
