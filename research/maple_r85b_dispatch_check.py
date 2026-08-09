#!/usr/bin/env python3
"""Research-only (PR #456): dispatch-structure checks on a GPUPROF campaign.

Two questions that are answered from the command-buffer stream alone, with no
statistics and therefore no power problem:

  period   How many command buffers is one decode step? PR #457 used 406. That
           number is re-derived here from the stream instead of inherited, by
           two independent routes that must agree: the spacing between decode
           step terminators, and the smallest exact period of the tail label
           sequence. A disagreement means the window is mis-specified and every
           downstream timing comparison is invalid.

  identity Do all runs issue the *same* command buffers in the same order? A
           verbatim source move must change zero dispatches. This compares the
           label sequence of the steady window across every run, which
           separates "the split changed the work" from "the split changed how
           fast the same work ran".

Usage:
    maple_r85b_dispatch_check.py period   <run.err>...
    maple_r85b_dispatch_check.py identity <run.err>...   [--cbs N] [--steps N]
"""
import argparse
import collections
import sys

TERMINATOR = "argmax_bfloat16"


def labels(path):
    out = []
    with open(path, errors="replace") as fh:
        for line in fh:
            if line.startswith("GPUPROF "):
                out.append(line.rstrip("\n").split(" ", 4)[4])
    return out


def smallest_period(lab, window=40000, limit=2000):
    tail = lab[-window:]
    for p in range(1, limit):
        if all(tail[i] == tail[i + p] for i in range(len(tail) - p)):
            return p
    return None


def cmd_period(paths):
    agreed = set()
    for path in paths:
        lab = labels(path)
        idx = [i for i, l in enumerate(lab) if l == TERMINATOR]
        gaps = collections.Counter(b - a for a, b in zip(idx, idx[1:]))
        mode, count = gaps.most_common(1)[0]
        period = smallest_period(lab)
        ok = "OK" if period == mode else "MISMATCH"
        print(f"{path.split('/')[-1]}: records={len(lab)} steps={len(idx)}")
        print(f"  terminator-gap mode {mode} (x{count}), other gaps "
              f"{sorted(g for g in gaps if g != mode)}")
        print(f"  smallest exact tail period {period}   -> {ok}")
        if ok == "OK":
            agreed.add(period)
    print(f"\ncbs-per-step: {sorted(agreed)}")
    return 0 if len(agreed) == 1 else 1


def cmd_identity(paths, cbs, steps):
    want = cbs * (steps - 1)
    ref = labels(paths[0])[-want:]
    print(f"reference {paths[0].split('/')[-1]}: {len(ref)} records "
          f"= {cbs}/step x {steps - 1} steady steps")
    bad = 0
    for path in paths:
        lab = labels(path)[-want:]
        if lab != ref:
            bad += 1
            n = sum(1 for a, b in zip(lab, ref) if a != b)
            print(f"  DIFFERS {path.split('/')[-1]}: len={len(lab)} mismatched={n}")
    print(f"runs compared: {len(paths)}, differing: {bad}")
    print("VERDICT: dispatch-sequence identical across all runs" if not bad
          else "VERDICT: DISPATCH DIFFERS")
    return 0 if not bad else 1


ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=("period", "identity"))
ap.add_argument("paths", nargs="+")
ap.add_argument("--cbs", type=int, default=406)
ap.add_argument("--steps", type=int, default=200)
a = ap.parse_args()
sys.exit(cmd_period(a.paths) if a.mode == "period"
         else cmd_identity(a.paths, a.cbs, a.steps))
