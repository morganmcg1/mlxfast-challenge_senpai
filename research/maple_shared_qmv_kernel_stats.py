#!/usr/bin/env python3
"""Research-only (PR #301): per-kernel arm statistics from SPLIT=1 profile logs.

Reads the `GPUPROF` stderr of `research/decode_probe.py --profile` runs produced
by `research/maple_shared_qmv_prefetch_abba.sh` and, for one kernel, reports the
per-call GPU duration by arm with a process-level confidence interval.

Only the steady decode window is used: for a kernel that runs `--per-step` times
per decode step, the last `per_step * (steps - 1)` records are kept, which drops
the seed forward and step 0 without needing the driver's wall-clock spans.

  python3 research/maple_shared_qmv_kernel_stats.py --steps 33 \\
      --kernel shared_nvfp4_swiglu_qmv_rows1 --per-step 39 \\
      /tmp/maple-shared-qmv/*.err
"""
import argparse
import collections
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_probe import parse_gpuprof_line  # noqa: E402

ARM_RE = re.compile(r"-(off|on|pairwise)\.err$")


def kernel_calls(path: str, kernel: str, steps: int, per_step: int):
    """Per-call microseconds for `kernel` inside the steady decode window."""
    spans = []
    with open(path, errors="replace") as fh:
        for line in fh:
            if not line.startswith("GPUPROF ") or kernel not in line:
                continue
            rec = parse_gpuprof_line(line)
            if rec is not None:
                spans.append((rec[1] - rec[0]) * 1e6)
    want = per_step * (steps - 1)
    if len(spans) < want:
        raise SystemExit(f"{path}: {len(spans)} calls of {kernel}, need {want}")
    return spans[-want:]


def welch(a, b):
    """Welch two-sample mean difference (b - a) with a 95% interval."""
    na, nb = len(a), len(b)
    ma, mb = statistics.mean(a), statistics.mean(b)
    va = statistics.variance(a) / na if na > 1 else 0.0
    vb = statistics.variance(b) / nb if nb > 1 else 0.0
    se = math.sqrt(va + vb)
    if se == 0.0:
        return mb - ma, 0.0, float("nan")
    df = (va + vb) ** 2 / (
        (va ** 2 / (na - 1) if na > 1 else 0.0)
        + (vb ** 2 / (nb - 1) if nb > 1 else 0.0))
    # 97.5th percentile of Student t, small-sample table then normal.
    tcrit = {1: 12.71, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
             7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}.get(round(df), 2.0)
    return mb - ma, tcrit * se, df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--kernel", default="shared_nvfp4_swiglu_qmv_rows1")
    ap.add_argument("--per-step", type=int, default=39)
    ap.add_argument("--steps", type=int, required=True)
    ap.add_argument("--baseline-arm", default="off")
    args = ap.parse_args()

    by_arm = collections.defaultdict(list)
    print(f"{'file':>26} {'arm':>8} {'n':>6} {'us/call':>9} {'median':>8} "
          f"{'se':>7} {'us/step':>9}")
    for path in sorted(args.paths):
        m = ARM_RE.search(os.path.basename(path))
        if not m:
            raise SystemExit(f"cannot infer arm from {path}")
        arm = m.group(1)
        calls = kernel_calls(path, args.kernel, args.steps, args.per_step)
        mean = statistics.mean(calls)
        se = statistics.stdev(calls) / math.sqrt(len(calls))
        by_arm[arm].append(mean)
        print(f"{os.path.basename(path):>26} {arm:>8} {len(calls):6d} "
              f"{mean:9.3f} {statistics.median(calls):8.3f} {se:7.3f} "
              f"{mean * args.per_step:9.1f}")

    print(f"\nkernel {args.kernel}: process-level arm means (us/call)")
    for arm, means in sorted(by_arm.items()):
        print(f"  {arm:>8} n={len(means)} mean={statistics.mean(means):.3f} "
              + ("sd=%.3f" % statistics.stdev(means) if len(means) > 1 else ""))
    base = by_arm.get(args.baseline_arm)
    if base:
        for arm, means in sorted(by_arm.items()):
            if arm == args.baseline_arm:
                continue
            d, hw, df = welch(base, means)
            rel = d / statistics.mean(base) * 100
            print(f"  {arm} - {args.baseline_arm}: {d:+.3f} us/call "
                  f"[{d - hw:+.3f}, {d + hw:+.3f}] ({rel:+.2f}%, df={df:.1f}) "
                  f"= {d * args.per_step:+.1f} us/step")
    return 0


if __name__ == "__main__":
    sys.exit(main())
