#!/usr/bin/env python3
"""Per-kernel nesting fraction from a SPLIT=1 GPUPROF capture (research only).

PR #685 comment 5246874781 retracts the archive claim that decode dispatches are
serialized: the old evidence was a SPLIT=0 profile, where one record is a whole
command buffer, so `busy_sum ~= busy_union` was a statement about command
buffers rather than kernels. Under SPLIT=1 each command buffer holds exactly one
dispatch, so the same ratio finally measures kernel concurrency.

`decode_probe.py --profile` prints the *global* ratio. This adds the per-kernel
question the advisor actually asked: of the wall time during which kernel K is
running, what fraction has some other kernel running concurrently? That is the
fraction of K's busy time that is already hidden, and therefore the fraction of
any busy saving in K that would *not* show up in the step wall clock.

  python3 research/maple-alphonse-r109e-nesting.py <err-file> [KERNEL ...]

Reads the same `GPUPROF` lines decode_probe.py writes; accepts .gz.
"""
import gzip
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_probe import parse_gpuprof_line  # noqa: E402

DEFAULT_KERNELS = (
    "full_fused_attn_grow",
    "sliding_fused_attn_ring",
    "laguna_gate_sp",
    "routed_swiglu",
)


def load(path):
    op = gzip.open if path.endswith(".gz") else open
    recs = []
    with op(path, "rt", errors="replace") as fh:
        for line in fh:
            if line.startswith("GPUPROF "):
                rec = parse_gpuprof_line(line)
                if rec is not None:
                    recs.append(rec)
    return recs


def union(intervals):
    """Total measure of a union of half-open intervals."""
    total = 0.0
    cur_s = cur_e = None
    for s, e in sorted(intervals):
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total


def overlap_measure(a, b):
    """Measure of union(a) intersect union(b), by sweep over both coverages."""
    events = []
    for s, e in a:
        events.append((s, 0, 1))
        events.append((e, 0, -1))
    for s, e in b:
        events.append((s, 1, 1))
        events.append((e, 1, -1))
    events.sort()
    ca = cb = 0
    prev = None
    total = 0.0
    for t, which, delta in events:
        if prev is not None and ca > 0 and cb > 0:
            total += t - prev
        prev = t
        if which == 0:
            ca += delta
        else:
            cb += delta
    return total


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    kernels = tuple(sys.argv[2:]) or DEFAULT_KERNELS
    recs = load(path)
    if not recs:
        print(f"no GPUPROF records in {path}")
        return 1

    lo = min(r[0] for r in recs)
    hi = max(r[1] for r in recs)
    # Warm-up and the one-time step-0 KV concat live at the front; drop the
    # first 10% of the captured span so the ratio is a steady-state statement.
    cut = lo + 0.10 * (hi - lo)
    win = [r for r in recs if r[0] >= cut]
    nops = sum(r[2] for r in win)
    multi = sum(1 for r in win if r[2] != 1)
    busy_sum = sum(e - s for s, e, _, _ in win)
    busy_union = union([(s, e) for s, e, _, _ in win])
    print(f"{path}: {len(recs)} records, {len(win)} after 10% warm-up cut, "
          f"{nops} dispatches ({multi} records with nops != 1)")
    if multi:
        print("WARNING: records carry more than one dispatch, so this capture "
              "is NOT SPLIT=1 and per-kernel nesting is not measurable.")
    print(f"global busy_sum/busy_union = {busy_sum / busy_union:.4f}  "
          f"=> {(1 - busy_union / busy_sum) * 100:.2f}% of busy is hidden")

    print(f"\n{'nested%':>8} {'busy_sum_ms':>12} {'union_ms':>10} "
          f"{'n':>7}  kernel")
    for kern in kernels:
        mine = [(s, e) for s, e, _, names in win if kern in names]
        if not mine:
            print(f"{'--':>8} {'--':>12} {'--':>10} {0:7d}  {kern}")
            continue
        others = [(s, e) for s, e, _, names in win if kern not in names]
        u = union(mine)
        ov = overlap_measure(mine, others)
        print(f"{ov / u * 100:7.2f}% {sum(e - s for s, e in mine) * 1e3:12.3f} "
              f"{u * 1e3:10.3f} {len(mine):7d}  {kern}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
