#!/usr/bin/env python3
"""Paired local-submit timing ledger for the R109-F integration arm.

Reads the `score.local-submit.<family><n>.json` snapshots that
`./benchmark.sh --local-submit` leaves in `score.json` (one copy per
replicate, because the harness overwrites `score.json` every run) and reports
per-family dispersion plus the paired candidate-vs-baseline ratios that the
official weighted score uses:

    score = decode_speedup^0.75 * prefill_speedup^0.25

Everything here is a *ratio between two families measured on this host*.  The
absolute `score` field a local run prints is not comparable to an official M5
receipt: this box is an M4 Pro, whose prefill is far slower relative to the
pinned M5 prefill constant, so `prefill_speedup` and therefore the local score
are structurally depressed.  Only same-host candidate/baseline ratios carry
information.

Usage:
    python3 research/fern_r109_timing_ledger.py                # all families
    python3 research/fern_r109_timing_ledger.py base cand      # pair two
"""

import argparse
import json
import pathlib
import re
import statistics
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
PATTERN = re.compile(r"^score\.local-submit\.([A-Za-z0-9_\-]+?)(\d+)\.json$")

DECODE_W = 0.75
PREFILL_W = 0.25


def load_families(root=ROOT):
    fams = defaultdict(list)
    for path in sorted(root.glob("score.local-submit.*.json")):
        m = PATTERN.match(path.name)
        if not m:
            continue
        d = json.loads(path.read_text())
        met = d["metrics"]
        fams[m.group(1)].append(
            {
                "replicate": int(m.group(2)),
                "path": path.name,
                "decode": met["decode_seconds_per_token"],
                "prefill": met["prefill_seconds_per_token"],
                "score": d["score"],
                "passed": d["passed"],
                "correct": met["passed_correctness"],
                "max_abs_diff": met["max_abs_diff"],
                "golden_hash": met["golden_hash"],
                "commit": met["commit"],
                "timestamp": met["timestamp"],
                "peak_ram_gb": met["peak_ram_gb"],
                "base_decode": met["baseline_decode_seconds_per_token"],
                "base_prefill": met["baseline_prefill_seconds_per_token"],
            }
        )
    for reps in fams.values():
        reps.sort(key=lambda r: r["replicate"])
    return fams


def spread(vals):
    lo, hi = min(vals), max(vals)
    return (hi - lo) / statistics.median(vals)


def summarize(name, reps):
    dec = [r["decode"] for r in reps]
    pre = [r["prefill"] for r in reps]
    return {
        "family": name,
        "n": len(reps),
        "decode_median": statistics.median(dec),
        "decode_min": min(dec),
        "decode_max": max(dec),
        "decode_spread": spread(dec),
        "prefill_median": statistics.median(pre),
        "prefill_min": min(pre),
        "prefill_max": max(pre),
        "prefill_spread": spread(pre),
        "all_correct": all(r["correct"] for r in reps),
        "max_abs_diff": max(r["max_abs_diff"] for r in reps),
        "golden_hashes": sorted({r["golden_hash"] for r in reps}),
        "commits": sorted({r["commit"] for r in reps}),
    }


def paired(base, cand):
    """Candidate-vs-baseline weighted ratio from medians (lower s/token wins)."""
    d = base["decode_median"] / cand["decode_median"]
    p = base["prefill_median"] / cand["prefill_median"]
    return {
        "decode_ratio": d,
        "prefill_ratio": p,
        "weighted_ratio": d**DECODE_W * p**PREFILL_W,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("families", nargs="*", help="baseline family first")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    fams = load_families()
    if not fams:
        print("no score.local-submit.<family><n>.json snapshots found", file=sys.stderr)
        return 1

    names = args.families or sorted(fams)
    missing = [n for n in names if n not in fams]
    if missing:
        print(f"unknown families: {missing}; have {sorted(fams)}", file=sys.stderr)
        return 1

    summaries = {n: summarize(n, fams[n]) for n in names}

    if args.json:
        out = {"families": summaries}
        if len(names) >= 2:
            base = summaries[names[0]]
            out["pairs"] = {
                n: paired(base, summaries[n]) for n in names[1:]
            }
        print(json.dumps(out, indent=2))
        return 0

    for n in names:
        s = summaries[n]
        print(f"=== {n}  (n={s['n']}) ===")
        for r in fams[n]:
            print(
                f"  rep{r['replicate']}  decode={r['decode']:.9f}  "
                f"prefill={r['prefill']:.9f}  score={r['score']:.6f}  "
                f"correct={r['correct']}  diff={r['max_abs_diff']}  "
                f"commit={r['commit']}  {r['timestamp']}"
            )
        print(
            f"  decode  median={s['decode_median']:.9f} "
            f"min={s['decode_min']:.9f} max={s['decode_max']:.9f} "
            f"spread={s['decode_spread'] * 100:.3f}%"
        )
        print(
            f"  prefill median={s['prefill_median']:.9f} "
            f"min={s['prefill_min']:.9f} max={s['prefill_max']:.9f} "
            f"spread={s['prefill_spread'] * 100:.3f}%"
        )
        print(
            f"  correctness: all_correct={s['all_correct']} "
            f"max_abs_diff={s['max_abs_diff']} "
            f"golden_hashes={s['golden_hashes']}"
        )
        print()

    if len(names) >= 2:
        base = summaries[names[0]]
        print(f"=== paired ratios vs {names[0]} (>1 means candidate faster) ===")
        for n in names[1:]:
            pr = paired(base, summaries[n])
            print(
                f"  {n}: decode x{pr['decode_ratio']:.6f}  "
                f"prefill x{pr['prefill_ratio']:.6f}  "
                f"weighted x{pr['weighted_ratio']:.6f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
