#!/usr/bin/env python3
"""Split the exposed decode-step head region into its components.

Consumes the stderr stream of a worker built with the research-only
`FRIEREN_CBPROF=1` instrumentation:

  FRCB  commit_s kstart_s kend_s gpu_start_s gpu_end_s done_s ops
  FRSTEP entry_s pre_layer_loop_s first_async_s model_return_s call_return_s

and reports, per steady decode step:

  * entry -> first command-buffer commit            (host, fully exposed)
  * first commit -> first GPU kernel start          (driver launch latency)
  * front idle  = prev step last GPU end -> this step first GPU start
  * GPU busy union, idle union, and where idle sits relative to the marks

Research-only; not part of the submitted surface.
"""

import argparse
import statistics
import sys


def parse(path):
    cbs = []
    steps = []
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            if line.startswith("FRCB "):
                f = line.split()
                cbs.append(tuple(float(x) for x in f[1:7]) + (int(f[7]),))
            elif line.startswith("FRSTEP "):
                f = line.split()
                steps.append(tuple(float(x) for x in f[1:6]))
    cbs.sort(key=lambda r: r[0])
    steps.sort(key=lambda r: r[0])
    return cbs, steps


def union_busy(intervals, lo, hi):
    """Union length of [gstart, gend] clipped to [lo, hi), plus gap list."""
    clipped = []
    for a, b in intervals:
        a2, b2 = max(a, lo), min(b, hi)
        if b2 > a2:
            clipped.append((a2, b2))
    clipped.sort()
    merged = []
    for a, b in clipped:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    busy = sum(b - a for a, b in merged)
    gaps = []
    for i in range(1, len(merged)):
        gaps.append((merged[i - 1][1], merged[i][0]))
    return busy, merged, gaps


def q(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def stats(name, xs, unit=1e6, digits=1):
    xs = [x * unit for x in xs]
    if not xs:
        print(f"{name:<44} n=0")
        return
    m = statistics.median(xs)
    mean = statistics.fmean(xs)
    sd = statistics.pstdev(xs) if len(xs) > 1 else 0.0
    se = sd / (len(xs) ** 0.5) if xs else 0.0
    print(
        f"{name:<44} n={len(xs):4d} median={m:9.{digits}f} mean={mean:9.{digits}f} "
        f"se={se:7.{digits}f} p10={q(xs, 0.1):8.{digits}f} p90={q(xs, 0.9):8.{digits}f}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--drop-first", type=int, default=80,
                    help="skip warmup steps at the start of the stream")
    ap.add_argument("--drop-last", type=int, default=2)
    ap.add_argument("--gap-threshold-us", type=float, default=20.0)
    args = ap.parse_args()

    cbs, steps = parse(args.log)
    if not cbs or not steps:
        sys.exit(f"no FRCB/FRSTEP records in {args.log} "
                 f"(cbs={len(cbs)} steps={len(steps)})")
    print(f"records: cb={len(cbs)} steps={len(steps)}")

    bad_order = sum(1 for c in cbs if not (c[0] <= c[3] <= c[4] <= c[5] + 1e-6))
    print(f"clock sanity: commit<=gpu_start<=gpu_end<=done violated in "
          f"{bad_order}/{len(cbs)} command buffers")

    gpu_intervals = [(c[3], c[4]) for c in cbs]
    lo = args.drop_first
    hi = len(steps) - args.drop_last
    sel = list(range(lo, hi - 1))
    if not sel:
        sys.exit("no steady steps selected")

    period, pre_commit, launch, front_idle = [], [], [], []
    entry_to_loop, entry_to_async, async_to_commit = [], [], []
    fwd_wall, model_wall, tail_wall = [], [], []
    busy_frac, idle_total = [], []
    idle_loop, idle_head, idle_after_return, cb_count = [], [], [], []
    ops_first, gpu_len_first = [], []

    for i in sel:
        m0, m1, m2, m3, m4 = steps[i]
        n0 = steps[i + 1][0]
        win = [c for c in cbs if m0 <= c[0] < n0]
        if not win:
            continue
        first = win[0]
        period.append(n0 - m0)
        pre_commit.append(first[0] - m0)
        launch.append(first[3] - first[0])
        ops_first.append(first[6])
        gpu_len_first.append(first[4] - first[3])
        entry_to_loop.append(m1 - m0)
        entry_to_async.append(m2 - m0)
        async_to_commit.append(first[0] - m2)
        model_wall.append(m3 - m0)
        fwd_wall.append(m4 - m0)
        tail_wall.append(n0 - m4)

        prev_end = max((c[4] for c in cbs if c[4] <= m0), default=None)
        if prev_end is not None:
            front_idle.append(first[3] - prev_end)

        busy, merged, gaps = union_busy(gpu_intervals, m0, n0)
        busy_frac.append(busy / (n0 - m0))
        idle_total.append((n0 - m0) - busy)
        cb_count.append(len(win))
        thr = args.gap_threshold_us * 1e-6
        il = ih = ia = 0.0
        for a, b in gaps:
            if b - a < thr:
                continue
            if b <= m3:
                il += b - a
            elif b <= m4:
                ih += b - a
            else:
                ia += b - a
        idle_loop.append(il)
        idle_head.append(ih)
        idle_after_return.append(ia)

    print(f"\nsteady steps analysed: {len(period)}   (microseconds unless noted)")
    stats("step period (entry->entry)", period, digits=1)
    stats("forward wall (entry->call return)", fwd_wall)
    stats("  model wall (entry->model return)", model_wall)
    stats("tail wall (call return->next entry)", tail_wall)
    print()
    stats("(1) entry -> first cb commit", pre_commit)
    stats("    entry -> pre-layer-loop mark", entry_to_loop)
    stats("    entry -> first asyncEval call", entry_to_async)
    stats("    first asyncEval -> first commit", async_to_commit)
    stats("(2) first commit -> first GPU start", launch)
    stats("    first cb GPU length", gpu_len_first)
    stats("    front idle (prev GPU end->GPU start)", front_idle)
    print()
    stats("GPU idle total in step", idle_total)
    stats("(3a) idle inside layer loop", idle_loop)
    stats("(3b) idle in head/norm/logits region", idle_head)
    stats("(3c) idle after call return (argmax/IPC)", idle_after_return)
    stats("GPU busy fraction of step (%)", busy_frac, unit=100.0, digits=2)
    stats("command buffers per step", cb_count, unit=1.0, digits=2)
    stats("dispatches in first cb", ops_first, unit=1.0, digits=2)


if __name__ == "__main__":
    main()
