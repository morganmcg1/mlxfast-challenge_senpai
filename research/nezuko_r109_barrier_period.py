#!/usr/bin/env python3
"""Recover the per-decode-step barrier count from a GPUBARRIER census log.

The census edit (research/nezuko_r109_barrier_census_edit.py) logs one line per
CommandEncoder::maybeInsertBarrier() that actually emits a barrier, naming the
*downstream* (blocked) kernel via current_pso_.  Decode steps are structurally
identical, so the tail of the sequence is exactly periodic; the period is the
number of intra-command-buffer dependency barriers per decode step.
"""
import collections
import gzip
import sys


def load(path):
    op = gzip.open if path.endswith(".gz") else open
    seq = []
    with op(path, "rt", errors="replace") as f:
        for ln in f:
            i = ln.find("GPUBARRIER")
            if i >= 0:
                seq.append(ln[i + 10:].strip())
    return seq


def period(seq, lo=20, hi=1200, window=8000):
    tail = seq[-window:]
    for per in range(lo, hi):
        if 3 * per > len(tail):
            break
        if tail[-per:] == tail[-2 * per:-per] == tail[-3 * per:-2 * per]:
            return per, tail[-per:]
    return None, []


def short(name):
    n = name.replace("custom_kernel_laguna_", "")
    for cut in ("_bfloat16_t", "_float", "_uint32_t", "_uint8_t"):
        i = n.find(cut)
        if i > 0:
            n = n[:i]
    return n


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    diff = "--diff" in sys.argv
    counts = {}
    for path in args:
        seq = load(path)
        per, step = period(seq)
        print(f"=== {path}")
        print(f"  total barrier records : {len(seq)}")
        if per is None:
            print("  no exact 3x period found")
            continue
        print(f"  barriers per decode step: {per}")
        c = collections.Counter(short(k) for k in step)
        counts[path] = (per, c)
        if not diff:
            for k, v in c.most_common(16):
                print(f"    {v:4d}  {k[:96]}")

    if diff and len(counts) == 2:
        (pa, (na, ca)), (pb, (nb, cb)) = counts.items()
        print(f"\n=== per-kernel barrier diff: {pb} minus {pa}  ({nb} - {na} = {nb - na})")
        for k in sorted(set(ca) | set(cb), key=lambda k: -abs(cb.get(k, 0) - ca.get(k, 0))):
            d = cb.get(k, 0) - ca.get(k, 0)
            if d:
                print(f"    {d:+5d}   (A={ca.get(k, 0):4d} -> B={cb.get(k, 0):4d})  {k[:80]}")


if __name__ == "__main__":
    main()
