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


# Two-sided 97.5th percentile of Student t by integer degrees of freedom. The
# lookup floors df and clamps at 30, so a fractional Welch df never picks a
# critical value smaller than the exact one.
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
       14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
       20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
       26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}


def t95(df):
    if df <= 0 or df != df:
        return float("nan")
    return T95[min(30, max(1, int(math.floor(df))))]


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
    return mb - ma, t95(df) * se, df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--kernel", default="shared_nvfp4_swiglu_qmv_rows1")
    ap.add_argument("--per-step", type=int, default=39)
    ap.add_argument("--steps", type=int, required=True)
    ap.add_argument("--baseline-arm", default="off")
    ap.add_argument("--arm-regex", default=ARM_RE.pattern,
                    help="capture group 1 names the arm in the file name")
    args = ap.parse_args()
    arm_re = re.compile(args.arm_regex)

    by_arm = collections.defaultdict(list)
    print(f"{'file':>26} {'arm':>8} {'n':>6} {'us/call':>9} {'median':>8} "
          f"{'se':>7} {'us/step':>9}")
    for path in sorted(args.paths):
        m = arm_re.search(os.path.basename(path))
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
