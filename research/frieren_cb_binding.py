#!/usr/bin/env python3
"""Decide which of MLX's two command-buffer commit limits actually binds.

MLX cuts a command buffer when

    buffer_ops_ > max_ops_per_buffer_  ||  (buffer_sizes_ >> 20) > max_mb_per_buffer_

(`Device::needs_commit`, checked after each op is encoded). So a buffer that was
cut by the *op* rule carries exactly `max_ops + 1` ops, and a buffer that was cut
by the *byte* rule carries fewer. Counting ops per committed buffer therefore
tells us which limit is live without any timing at all.

Consumes the stderr of a worker built with the research-only FRIEREN_CBPROF=1
instrumentation (FRCB / FRSTEP records). Research-only.
"""

import argparse
import statistics
import sys
from collections import Counter


def parse(path):
    cbs, steps = [], []
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            if line.startswith("FRCB "):
                f = line.split()
                cbs.append((float(f[1]), int(f[7])))
            elif line.startswith("FRSTEP "):
                f = line.split()
                steps.append((float(f[1]), float(f[5])))
    cbs.sort()
    steps.sort()
    return cbs, steps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("--label", default="")
    ap.add_argument("--max-ops", type=int, required=True)
    ap.add_argument("--max-mb", type=int, required=True)
    ap.add_argument("--skip-steps", type=int, default=10)
    args = ap.parse_args()

    cbs, steps = parse(args.raw)
    if len(steps) < args.skip_steps + 20:
        print(f"{args.raw}: only {len(steps)} steps recorded", file=sys.stderr)
        return 1

    steady = steps[args.skip_steps:]
    per_step, ops = [], []
    j = 0
    for i in range(len(steady) - 1):
        lo, hi = steady[i][0], steady[i + 1][0]
        while j < len(cbs) and cbs[j][0] < lo:
            j += 1
        k = j
        count = 0
        while k < len(cbs) and cbs[k][0] < hi:
            ops.append(cbs[k][1])
            count += 1
            k += 1
        per_step.append(count)

    hist = Counter(ops)
    at_ops_limit = sum(n for o, n in hist.items() if o >= args.max_ops + 1)
    top = sorted(hist.items(), key=lambda kv: -kv[1])[:8]

    print(f"label            {args.label}")
    print(f"caps             max_mb={args.max_mb} max_ops={args.max_ops}")
    print(f"steady steps     {len(per_step)}")
    print(f"cb/step median   {statistics.median(per_step):.1f}"
          f"  mean {statistics.fmean(per_step):.2f}"
          f"  min {min(per_step)}  max {max(per_step)}")
    print(f"ops/cb           median {statistics.median(ops):.1f}"
          f"  mean {statistics.fmean(ops):.2f}  max {max(ops)}")
    print(f"cbs at ops limit {at_ops_limit} / {len(ops)}"
          f"  ({100.0 * at_ops_limit / len(ops):.2f}%)  [ops>= {args.max_ops + 1}]")
    print("ops histogram    " + "  ".join(f"{o}:{n}" for o, n in top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
