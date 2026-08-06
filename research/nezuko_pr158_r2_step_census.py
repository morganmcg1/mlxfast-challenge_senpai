#!/usr/bin/env python3
"""Research-only (PR #158 r2): driver-free per-decode-step census from GPUPROF logs.

`decode_probe.analyze_profile` windows GPU records with the driver's
`time.perf_counter` spans. That correlation silently produced an empty window
under CPython 3.9, whose macOS `perf_counter` epoch is process-relative while
`MTLCommandBuffer.GPUStartTime` is mach-absolute (see the r2 report, "GPUPROF
window correlation"). This tool needs no driver clock at all: every decode step
emits exactly one cluster of lm-head command buffers, so the record stream
segments itself.

  python3 research/nezuko_pr158_r2_step_census.py /tmp/a.err /tmp/b.err --steps 199

Reported per file: command buffers, dispatches, GPU-busy sum and union, and
occupied span, all per steady decode step.
"""
import argparse
import collections
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_probe import parse_gpuprof_line  # noqa: E402

STEP_MARKER = "lmhead"


def read_records(path):
    records = []
    with open(path, errors="replace") as fh:
        for line in fh:
            if not line.startswith("GPUPROF "):
                continue
            parsed = parse_gpuprof_line(line)
            if parsed is not None:
                records.append(parsed)
    return records


def step_slices(records, steps):
    """Return the last `steps` (start, stop) index pairs, one per decode step.

    The lm-head projection runs once per decode step but spans a run of
    adjacent command buffers, so each cluster is collapsed to its last index
    and consecutive cluster ends delimit one step.
    """
    marks = [i for i, r in enumerate(records) if STEP_MARKER in r[3]]
    if not marks:
        raise SystemExit(f"no {STEP_MARKER!r} command buffer; wrong log?")
    mark_set = set(marks)
    ends = [i for i in marks if i + 1 not in mark_set]
    pairs = [(ends[i] + 1, ends[i + 1] + 1) for i in range(len(ends) - 1)]
    if len(pairs) < steps:
        raise SystemExit(f"only {len(pairs)} decode steps, need {steps}")
    return pairs[-steps:]


def union_seconds(window):
    spans = sorted((s, e) for s, e, _, _ in window)
    total = 0.0
    cur_s, cur_e = spans[0]
    for s, e in spans[1:]:
        if s > cur_e:
            total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    return total + cur_e - cur_s


def census(path, steps):
    records = read_records(path)
    slices = step_slices(records, steps)
    cbs, disp, busy, union, span = [], [], [], [], []
    kernels = collections.defaultdict(float)
    calls = collections.Counter()
    for a, b in slices:
        window = records[a:b]
        cbs.append(len(window))
        disp.append(sum(r[2] for r in window))
        busy.append(sum(e - s for s, e, _, _ in window) * 1e6)
        union.append(union_seconds(window) * 1e6)
        span.append((window[-1][1] - window[0][0]) * 1e6)
        for s, e, nops, names in window:
            key = names if nops == 1 else f"[{nops}] {names}"
            kernels[key] += (e - s) * 1e6 / steps
            calls[key] += 1
    return {
        "records": len(records),
        "cbs": statistics.median(cbs),
        "cbs_spread": (min(cbs), max(cbs)),
        "disp": statistics.median(disp),
        "disp_spread": (min(disp), max(disp)),
        "busy": statistics.median(busy),
        "busy_mean": statistics.mean(busy),
        "union": statistics.median(union),
        "span": statistics.median(span),
        "kernels": kernels,
        "calls": calls,
    }


def shorten(name):
    n = name.replace("custom_kernel_laguna_", "").replace("custom_kernel_", "")
    return n[:58]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--steps", type=int, default=199)
    ap.add_argument("--top", type=int, default=0,
                    help="also print the top-N kernels of the first log")
    args = ap.parse_args()

    print(f"{'busy_med':>9} {'busy_avg':>9} {'union':>8} {'span':>8} "
          f"{'cbs':>5} {'disp':>6}  log")
    first = None
    for path in args.paths:
        c = census(path, args.steps)
        first = first or c
        flag = ""
        if c["cbs_spread"][0] != c["cbs_spread"][1]:
            flag += f" cbs={c['cbs_spread']}"
        if c["disp_spread"][0] != c["disp_spread"][1]:
            flag += f" disp={c['disp_spread']}"
        print(f"{c['busy']:9.1f} {c['busy_mean']:9.1f} {c['union']:8.1f} "
              f"{c['span']:8.1f} {c['cbs']:5.0f} {c['disp']:6.0f}  "
              f"{os.path.basename(path)}{flag}")

    if args.top and first:
        rows = sorted(first["kernels"].items(), key=lambda kv: -kv[1])
        total = sum(first["kernels"].values())
        print(f"\n{'us/step':>9} {'share':>7} {'n/step':>7} {'us/call':>8}  kernel")
        for key, us in rows[:args.top]:
            n = first["calls"][key]
            print(f"{us:9.1f} {us/total*100:6.2f}% {n/args.steps:7.2f} "
                  f"{us*args.steps/n:8.2f}  {shorten(key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
