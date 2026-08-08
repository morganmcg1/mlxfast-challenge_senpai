#!/usr/bin/env python3
"""Research-only (PR #457): where the give-back kernels sit in dispatch order.

Placement and cache-state transfer predict different *locations* for a
give-back. If turning on a flag slows untouched kernels because the changed
kernel leaves L2 in a different state, the damage must land on its immediate
dispatch neighbours. If it is buffer placement, the damage follows addresses
and has no reason to respect dispatch adjacency.

The GPUPROF stream is a deterministic dispatch log, so one steady step answers
this with no extra GPU time.

  python3 research/maple_r85_dispatch_map.py /tmp/maple-pr443-abba/01-rep1-off.err
"""
import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_probe import parse_gpuprof_line, shorten  # noqa: E402
from maple_r85_arm_stats import GIVEBACK_KERNELS  # noqa: E402


def step_sequence(path, cbs_per_step, steady_steps):
    recs = []
    with open(path, errors="replace") as fh:
        for line in fh:
            if line.startswith("GPUPROF "):
                rec = parse_gpuprof_line(line)
                if rec is not None:
                    recs.append(rec)
    window = recs[-cbs_per_step * steady_steps:]
    seq = []
    for _, _, nops, names in window[:cbs_per_step]:
        key = "|".join(shorten(p) for p in names.split("|"))
        seq.append(f"[{nops}] {key}" if nops > 1 else key)
    return seq


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--cbs-per-step", type=int, default=406)
    ap.add_argument("--steps", type=int, default=33)
    ap.add_argument("--subject", default="shared_nvfp4_swiglu_qmv_rows1")
    ap.add_argument("--radius", type=int, default=2)
    args = ap.parse_args()

    seq = step_sequence(args.path, args.cbs_per_step, args.steps - 1)
    subject = [i for i, k in enumerate(seq) if args.subject in k]
    print(f"{len(seq)} dispatches/step; subject {args.subject} at {subject[:8]}"
          f"{' ...' if len(subject) > 8 else ''} (n={len(subject)})")

    print(f"\nneighbourhood of the first 2 subject dispatches:")
    for i in subject[:2]:
        for j in range(max(0, i - 4), min(len(seq), i + 5)):
            hit = any(g in seq[j] for g in GIVEBACK_KERNELS)
            mark = "SUBJ" if j == i else ("GIVE" if hit else "    ")
            print(f"  {j:3d} {mark}  {seq[j][:70]}")
        print()

    near = {j for i in subject
            for j in range(i - args.radius, i + args.radius + 1)}
    counts = collections.Counter()
    nears = collections.Counter()
    for j, key in enumerate(seq):
        for g in GIVEBACK_KERNELS:
            if g in key:
                counts[g] += 1
                nears[g] += j in near
    print(f"dispatches within +-{args.radius} of a subject dispatch:")
    for g in GIVEBACK_KERNELS:
        n = counts[g]
        frac = f"{100*nears[g]/n:5.1f}%" if n else "   n/a"
        print(f"  {g:38s} n={n:4d} near={nears[g]:4d} {frac}")
    others = collections.Counter()
    onear = collections.Counter()
    for j, key in enumerate(seq):
        if any(g in key for g in GIVEBACK_KERNELS) or args.subject in key:
            continue
        others[key] += 1
        onear[key] += j in near
    print("\nsame statistic for kernels that did NOT give back:")
    for key, n in others.most_common(10):
        print(f"  {key[:38]:38s} n={n:4d} near={onear[key]:4d} "
              f"{100*onear[key]/n:5.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
