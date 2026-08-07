#!/usr/bin/env python3
"""Research-only (PR #158 r2): per-kernel median and half-range across SPLIT=1 replicates.

The r1 census rested on a single SPLIT=1 run, so no kernel row carried a
dispersion estimate. This aggregates N independent SPLIT=1 profile logs and
reports, per kernel, the median us/step and the half-range
(max - min) / 2 across runs. Rows whose half-range exceeds --flag-frac of
their own median are marked `!` -- those are the rows a single-run census had
no right to quote to three significant figures.

  python3 research/nezuko_pr158_r2_replicate_stats.py \
      /tmp/a.err /tmp/b.err /tmp/c.err --steps 199 --per-step 406
"""
import argparse
import collections
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_probe import parse_gpuprof_line  # noqa: E402


def per_kernel_us_per_step(path, steps, per_step):
    records = []
    with open(path, errors="replace") as fh:
        for line in fh:
            if not line.startswith("GPUPROF "):
                continue
            parsed = parse_gpuprof_line(line)
            if parsed is not None:
                records.append((parsed[0], parsed[1], parsed[3]))
    want = steps * per_step
    if len(records) < want:
        raise SystemExit(f"{path}: only {len(records)} records, need {want}")
    window = records[-want:]
    agg = collections.defaultdict(float)
    calls = collections.Counter()
    for start, end, name in window:
        agg[name] += (end - start) * 1e6 / steps
        calls[name] += 1
    span = (window[-1][1] - window[0][0]) / steps * 1e3
    return agg, calls, span


def shorten(name):
    n = name.replace("custom_kernel_laguna_", "").replace("custom_kernel_", "")
    return n[:58]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--steps", type=int, required=True)
    ap.add_argument("--per-step", type=int, required=True)
    ap.add_argument("--flag-frac", type=float, default=0.10)
    args = ap.parse_args()

    runs, spans = [], []
    for p in args.paths:
        agg, calls, span = per_kernel_us_per_step(p, args.steps, args.per_step)
        runs.append((agg, calls))
        spans.append(span)
        print(f"# {os.path.basename(p)}: busy_sum={sum(agg.values()):.1f} us/step "
              f"span={span:.3f} ms/step kernels={len(agg)}")

    totals = [sum(a.values()) for a, _ in runs]
    print(f"\nbusy_sum across {len(runs)} runs: median={statistics.median(totals):.1f} "
          f"half_range={(max(totals) - min(totals)) / 2:.1f} us/step "
          f"({(max(totals) - min(totals)) / 2 / statistics.median(totals) * 100:.2f}%)")
    print(f"window_span across runs: median={statistics.median(spans):.3f} "
          f"half_range={(max(spans) - min(spans)) / 2:.3f} ms/step")

    names = set()
    for agg, _ in runs:
        names |= set(agg)
    print(f"\n{'median':>9} {'halfrng':>8} {'hr%':>6} {'n/step':>7} "
          f"{'us/call':>8}  kernel")
    rows = []
    for name in names:
        vals = [agg.get(name, 0.0) for agg, _ in runs]
        med = statistics.median(vals)
        hr = (max(vals) - min(vals)) / 2
        n = statistics.median([c.get(name, 0) / args.steps for _, c in runs])
        rows.append((med, hr, n, name))
    flagged = 0
    for med, hr, n, name in sorted(rows, reverse=True):
        frac = hr / med if med else 0.0
        mark = "!" if frac > args.flag_frac else " "
        flagged += mark == "!"
        print(f"{med:9.1f} {hr:8.2f} {frac * 100:5.1f}%{mark} {n:7.2f} "
              f"{med / n if n else float('nan'):8.2f}  {shorten(name)}")
    print(f"\nrows with half-range > {args.flag_frac * 100:.0f}% of median: {flagged}"
          f"/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
