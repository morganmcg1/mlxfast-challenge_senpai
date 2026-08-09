#!/usr/bin/env python3
"""Segment the verbose-dump kernel order into prefill and per-decode-step phases.

MLX prints the generated MSL once per custom-kernel *op construction*
(metal_kernel.cpp:342-347), and op construction happens in Swift call order, so
the ordered name list is an exact dispatch trace of the scored runtime for the
oracle's 512-token prefill plus N single-token decode steps. No profiler hook,
no vendor patch, no timing perturbation.

Phase boundaries come from two structural markers. The prefill MoE tail kernel
fires only during prefill, so prefill ends just after its last dispatch. The
layer-0 dense residual epilogue fires exactly once per decode step, at a fixed
offset from the step start, which fixes the remaining boundaries.

Usage: python3 segment_dispatches.py [kernel-order.txt]
"""
import sys
from collections import Counter

PREFILL_ONLY = "laguna_prefill_moe_tail_bf16_v1"
DENSE_EPILOGUE = "laguna_dense_down_residual_bf16_v1"

path = sys.argv[1] if len(sys.argv) > 1 else "research/r92-runs/kernel-order.txt"
names = [l.strip() for l in open(path) if l.strip()]
n = len(names)

prefill_end = max(i for i, x in enumerate(names) if x == PREFILL_ONLY) + 1
dense = [i for i, x in enumerate(names) if x == DENSE_EPILOGUE]
offset = dense[0] - prefill_end
starts = [prefill_end] + [d - offset for d in dense[1:]]

bounds = starts + [n]
print(f"total dispatches: {n}")
print(f"decode steps found: {len(starts)}   prefill dispatches: {starts[0]}")

print("\nper-decode-step dispatch counts:")
step_hists = []
for i in range(len(starts)):
    hist = Counter(names[bounds[i]:bounds[i + 1]])
    step_hists.append(hist)
    print(f"  step {i}: {sum(hist.values())} dispatches")

kernels = sorted({k for h in step_hists for k in h}, key=lambda k: -step_hists[-1][k])
print("\nkernel".ljust(60) + "".join(f"s{i}".rjust(5) for i in range(len(starts))))
for k in kernels:
    print(k.ljust(60) + "".join(str(h[k]).rjust(5) for h in step_hists))

print("\nsteady-state (last step) decode call order, compressed:")
blocks = []
for x in names[bounds[-2]:bounds[-1]]:
    if blocks and blocks[-1][0] == x:
        blocks[-1][1] += 1
    else:
        blocks.append([x, 1])
for name, count in blocks:
    print(f"  x{count:<4d} {name}")

print("\nprefill histogram (descending):")
for k, v in Counter(names[: starts[0]]).most_common():
    print(f"  {v:5d}  {k}")
