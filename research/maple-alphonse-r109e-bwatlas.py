#!/usr/bin/env python3
"""Per-kernel achieved-bandwidth atlas from one raw pr91 GPUPROF capture.

    research/maple-alphonse-r109e-bwatlas.py CAPTURE.err[.gz] [STEADY_STEPS]

Answers the question PR #685 comment 5247182400 asks: rank the decode step's
kernels by size, and say for each whether its time is bought by DRAM traffic or
by something else. A kernel already at the machine's bandwidth ceiling cannot be
made faster without moving fewer bytes; a kernel far below it is paying for
latency, occupancy or ALU, and is the only kind of kernel an in-kernel rewrite
can help.

The GB/s column is a *ratio* of two sums over the same records, so it needs no
steady-window selection and is immune to warm-up contamination. The us/step
column does need a step count; pass the probe's steady-step count to get it,
otherwise it is reported as a share only.

Only meaningful on a SPLIT=1 capture, where one dispatch occupies one command
buffer so bytes and time are attributable to a single kernel. On SPLIT=0 a
record covers ~9 dispatches and the name field is a join of all of them.

SPLIT=1 inflates each record by a fixed per-command-buffer cost, measured in
this session at 1.554 us/call (see maple-alphonse-r109e-qk-ceiling.md 7.3.2).
The `us/step_c` column subtracts it; the GB/s column does not, so the reported
bandwidth is a *lower* bound on the true achieved bandwidth.
"""
import gzip
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_probe import parse_gpuprof_line  # noqa: E402

SPLIT1_INFLATION_US = 1.554
# M4 Pro spec DRAM bandwidth. The best-achieving kernels in this capture reach
# 280 GB/s once SPLIT=1 inflation is removed, so 273 is if anything pessimistic;
# treat >=95% as "at the ceiling".
M4_PRO_PEAK_GB_S = 273.0
# MLX reports a gather-matmul's input_bytes as the whole expert tensor, not the
# slice actually read. Laguna routes top-8 of 256 experts, so a `routed_` kernel
# touches 1/32 of its declared bytes. Without this the two MoE kernels read as
# 2800% of peak, which is how the over-count announces itself.
GATHER_DIV = 32.0
GATHER_MARK = "routed_"


def load(path):
    op = gzip.open if path.endswith(".gz") else open
    agg = {}
    with op(path, "rt", errors="replace") as fh:
        for line in fh:
            if not line.startswith("GPUPROF "):
                continue
            parts = line.rstrip("\n").split(" ", 5)
            if len(parts) != 6 or not parts[4].isdigit():
                continue  # hook variant without the input_bytes field
            rec = parse_gpuprof_line(line)
            if rec is None:
                continue
            start, end, _nops, name = rec
            if "|" in name:
                continue  # batched command buffer: not attributable
            a = agg.setdefault(name, [0.0, 0, 0])
            a[0] += end - start
            a[1] += int(parts[4])
            a[2] += 1
    return agg


def short(name):
    n = name.replace("custom_kernel_laguna_", "")
    for cut in ("_bfloat16_t_", "_bfloat16_bfloat16_"):
        i = n.find(cut)
        if i > 0:
            return n[:i]
    return n[:56]


def main():
    path = sys.argv[1]
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 199
    min_per_step = float(os.environ.get("MIN_N_PER_STEP", "0.9"))
    agg = load(path)
    rows = []
    for name, (secs, byts, n) in agg.items():
        n_step = n / steps
        if n_step < min_per_step:
            continue  # prefill-only or once-per-run kernel, not a decode cost
        gathered = GATHER_MARK in name
        real_bytes = byts / GATHER_DIV if gathered else float(byts)
        us_call_c = secs * 1e6 / n - SPLIT1_INFLATION_US
        gbs = real_bytes / n / (us_call_c * 1e-6) / 1e9
        us_step_c = us_call_c * n_step
        floor_step = real_bytes / n / M4_PRO_PEAK_GB_S / 1e9 * 1e6 * n_step
        rows.append((us_step_c - floor_step, us_step_c, floor_step, gbs,
                     n_step, us_call_c, real_bytes / n / 1e6, gathered, name))
    rows.sort(reverse=True)
    tot_c = sum(r[1] for r in rows)

    print(f"{path}: {len(rows)} decode kernels at >= {min_per_step}/step, "
          f"{tot_c:.1f} us/step corrected (SPLIT=1 inflation "
          f"{SPLIT1_INFLATION_US} us/call removed), peak {M4_PRO_PEAK_GB_S} GB/s")
    print("headroom = corrected busy time minus the time the same bytes would "
          "take at peak DRAM bandwidth")
    print()
    print(f"{'headroom':>9} {'us/step_c':>10} {'floor':>8} {'share':>7} "
          f"{'GB/s':>7} {'%peak':>6} {'n/step':>7} {'us/call':>8} "
          f"{'MB/call':>9}  kernel")
    for head, us_step_c, floor, gbs, n_step, us_call, mb, gathered, name in rows:
        print(f"{head:9.1f} {us_step_c:10.1f} {floor:8.1f} "
              f"{us_step_c / tot_c * 100:6.2f}% {gbs:7.1f} "
              f"{gbs / M4_PRO_PEAK_GB_S * 100:5.1f}% {n_step:7.2f} "
              f"{us_call:8.2f} {mb:9.3f}{'g' if gathered else ' '} {short(name)}")


if __name__ == "__main__":
    main()
