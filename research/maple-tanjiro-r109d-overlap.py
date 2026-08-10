#!/usr/bin/env python3
"""Measure per-kernel GPU-busy overlap from a GPUPROF worker trace.

Answers the stage-0 (iii) question for R109-D: how much of `laguna_gate_sp`'s
GPU-busy time is on the decode critical path, versus hidden inside a concurrent
kernel's execution window.

Usage: maple-tanjiro-r109d-overlap.py TRACE [FOCUS_SUBSTRING ...]
"""
import re
import sys
from collections import defaultdict

LINE = re.compile(r"^GPUPROF\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+)\s+(\d+)\s+(\S+)")


def short(name):
    n = name
    n = re.sub(r"^custom_kernel_", "", n)
    # strip the trailing MSL type-signature suffix
    n = re.sub(
        r"(_(bfloat16_t|uint32_t|uint8_t|float|c_float|c_bfloat16_t|int32_t|bool))+$",
        "",
        n,
    )
    return n


def union(intervals):
    if not intervals:
        return 0.0
    iv = sorted(intervals)
    total = 0.0
    cs, ce = iv[0]
    for s, e in iv[1:]:
        if s > ce:
            total += ce - cs
            cs, ce = s, e
        else:
            ce = max(ce, e)
    total += ce - cs
    return total


def main():
    path = sys.argv[1]
    focus = sys.argv[2:] or ["gate_sp"]
    recs = []
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            m = LINE.match(line)
            if not m:
                continue
            s, e, _, nbytes, name = m.groups()
            recs.append((float(s) * 1e6, float(e) * 1e6, int(nbytes), short(name)))
    if not recs:
        print("no GPUPROF records found")
        return 1
    recs.sort()

    span = recs[-1][1] - recs[0][0]
    busy_sum = sum(e - s for s, e, _, _ in recs)
    busy_union = union([(s, e) for s, e, _, _ in recs])
    print(f"trace           : {path}")
    print(f"dispatches      : {len(recs)}")
    print(f"wall span       : {span:,.1f} us")
    print(f"gpu_busy_sum    : {busy_sum:,.1f} us")
    print(f"gpu_busy_union  : {busy_union:,.1f} us")
    print(
        f"CONCURRENCY     : sum/union = {busy_sum / busy_union:.4f}  "
        f"(hidden by overlap = {busy_sum - busy_union:,.1f} us = "
        f"{100.0 * (busy_sum - busy_union) / busy_sum:.2f}% of busy_sum)"
    )
    print(
        "  archive 6333 claimed sum==union to 1us (zero concurrency); "
        "a ratio > 1.01 refutes that for this trace"
    )

    per = defaultdict(list)
    for s, e, nbytes, name in recs:
        per[name].append((s, e, nbytes))

    print("\n=== top kernels by gpu_busy_sum ===")
    print(f"{'kernel':<62} {'n':>5} {'busy_sum us':>12} {'mean us':>9} {'MB/disp':>8}")
    rows = sorted(per.items(), key=lambda kv: -sum(e - s for s, e, _ in kv[1]))
    for name, iv in rows[:16]:
        bs = sum(e - s for s, e, _ in iv)
        mb = sum(b for _, _, b in iv) / len(iv) / 2**20
        print(f"{name[:62]:<62} {len(iv):>5} {bs:>12,.1f} {bs / len(iv):>9.2f} {mb:>8.3f}")

    for key in focus:
        sel = [(n, iv) for n, iv in per.items() if key in n]
        if not sel:
            print(f"\n=== FOCUS '{key}': no matching kernel ===")
            continue
        print(f"\n=== FOCUS '{key}' — critical-path share ===")
        print(
            f"{'kernel':<44} {'n':>4} {'busy us':>10} {'covered':>10} "
            f"{'exposed':>10} {'%hidden':>8}"
        )
        tot_busy = tot_exposed = 0.0
        for name, iv in sorted(sel):
            busy = 0.0
            exposed = 0.0
            for s, e, _ in iv:
                busy += e - s
                # union of every OTHER dispatch, clipped to [s,e]
                others = [
                    (max(os_, s), min(oe, e))
                    for os_, oe, _, on in recs
                    if not (oe <= s or os_ >= e) and not (os_ == s and oe == e and on == name)
                ]
                others = [(a, b) for a, b in others if b > a]
                exposed += (e - s) - union(others)
            covered = busy - exposed
            tot_busy += busy
            tot_exposed += exposed
            print(
                f"{name[:44]:<44} {len(iv):>4} {busy:>10,.1f} {covered:>10,.1f} "
                f"{exposed:>10,.1f} {100.0 * covered / busy:>7.2f}%"
            )
        print(
            f"{'TOTAL':<44} {'':>4} {tot_busy:>10,.1f} "
            f"{tot_busy - tot_exposed:>10,.1f} {tot_exposed:>10,.1f} "
            f"{100.0 * (tot_busy - tot_exposed) / tot_busy:>7.2f}%"
        )
        print(
            "  'exposed' is the only part an occupancy speedup of this kernel "
            "can remove from the critical path."
        )

        # who covers it
        cover = defaultdict(float)
        for name, iv in sel:
            for s, e, _ in iv:
                for os_, oe, _, on in recs:
                    if on == name:
                        continue
                    a, b = max(os_, s), min(oe, e)
                    if b > a:
                        cover[on] += b - a
        if cover:
            print(f"\n  concurrent kernels covering '{key}':")
            for on, us in sorted(cover.items(), key=lambda kv: -kv[1])[:8]:
                print(f"    {on[:64]:<64} {us:>10,.1f} us")
    return 0


if __name__ == "__main__":
    sys.exit(main())
