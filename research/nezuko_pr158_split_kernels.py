#!/usr/bin/env python3
"""Research-only (PR #158): full per-dispatch table from a SPLIT=1 profile log.

`decode_probe.analyze_profile` needs the Python-side step boundaries to select
the steady window and truncates its table. At SPLIT=1 every command buffer holds
exactly one dispatch, so the steady window can be recovered from the record
stream alone: the last `steps * dispatches_per_step` records are the steady
decode steps (the trailing IPC pings and shutdown emit no command buffers).

  python3 research/nezuko_pr158_split_kernels.py /tmp/...split1....err \
      --steps 199 --per-step 406
"""
import argparse
import collections
import statistics
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--steps", type=int, required=True)
    ap.add_argument("--per-step", type=int, required=True)
    args = ap.parse_args()

    records = []
    with open(args.path, errors="replace") as fh:
        for line in fh:
            if not line.startswith("GPUPROF "):
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            records.append((float(parts[1]), float(parts[2]), parts[4]))

    want = args.steps * args.per_step
    if len(records) < want:
        print(f"only {len(records)} records, need {want}")
        return 1
    window = records[-want:]
    span = window[-1][1] - window[0][0]

    per_kernel = collections.defaultdict(list)
    for start, end, name in window:
        per_kernel[name].append((end - start) * 1e6)

    total = sum(sum(v) for v in per_kernel.values())
    print(f"records={len(records)} window={want} "
          f"window_span={span/args.steps*1e3:.3f} ms/step "
          f"gpu_busy_sum={total/args.steps:.1f} us/step "
          f"kernels={len(per_kernel)}")
    print(f"{'us/step':>9} {'share':>7} {'n/step':>7} {'us/call':>8} "
          f"{'p10':>7} {'p90':>7}  kernel")
    rows = sorted(per_kernel.items(), key=lambda kv: -sum(kv[1]))
    for name, spans in rows:
        s = sum(spans) / args.steps
        ordered = sorted(spans)
        n = len(ordered)
        print(f"{s:9.1f} {s/(total/args.steps)*100:6.2f}% "
              f"{n/args.steps:7.2f} {statistics.mean(ordered):8.2f} "
              f"{ordered[n//10]:7.2f} {ordered[9*n//10]:7.2f}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
