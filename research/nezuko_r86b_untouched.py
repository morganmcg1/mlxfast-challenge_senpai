#!/usr/bin/env python3
"""Untouched-kernel delta table across ladder rungs (R86-B).

The GPUPROF census aggregates by command-buffer signature, so a per-kernel
delta is not recoverable for command buffers that received inserts. But the
command buffers whose signature contains no inserted op are byte-identical
work under every arm, and any movement in them is spillover rather than
inserted cost. Those are the untouched pool.
"""
import re
import sys
from pathlib import Path

CENSUS = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/r86b/census")
ARMS = ["off", "w0", "w2", "w16", "t0", "t2", "t16"]
ROW = re.compile(r"^\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s+(.*)$")
INSERT = "vs_Multiply"


def parse(path):
    rows = {}
    for line in path.read_text().splitlines():
        m = ROW.match(line)
        if not m:
            continue
        us, share, npc, uspc, kernel = m.groups()
        rows[kernel.strip()] = (float(us), float(share), float(npc))
    return rows


def short(sig):
    body = re.sub(r"^\[\d+\]\s*", "", sig)
    parts = body.split("|")
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} … {parts[-1]} ({len(parts)} k)"


def main():
    data = {a: parse(CENSUS / f"{a}.log") for a in ARMS}
    untouched = [s for s in data["off"] if INSERT not in s]
    # keep only signatures present and insert-free in every arm
    untouched = [s for s in untouched if all(s in data[a] for a in ARMS)]
    untouched.sort(key=lambda s: -data["off"][s][0])

    print(f"{'signature':<58}{'share':>7}", end="")
    for a in ARMS:
        print(f"{a:>9}", end="")
    print(f"{'w16-w0':>9}{'t16-t0':>9}")
    tot = {a: 0.0 for a in ARMS}
    for s in untouched:
        print(f"{short(s):<58}{data['off'][s][1]:>6.2f}%", end="")
        for a in ARMS:
            print(f"{data[a][s][0]:>9.1f}", end="")
            tot[a] += data[a][s][0]
        print(f"{data['w16'][s][0]-data['w0'][s][0]:>9.2f}"
              f"{data['t16'][s][0]-data['t0'][s][0]:>9.2f}")
    print(f"{'TOTAL untouched pool':<58}{sum(data['off'][s][1] for s in untouched):>6.2f}%", end="")
    for a in ARMS:
        print(f"{tot[a]:>9.1f}", end="")
    print(f"{tot['w16']-tot['w0']:>9.2f}{tot['t16']-tot['t0']:>9.2f}")

    print()
    print(f"untouched pool k=0   (w0)  : {tot['w0']:.1f} us/step")
    print(f"untouched pool k=640 (w16) : {tot['w16']:.1f} us/step  "
          f"delta {tot['w16']-tot['w0']:+.2f} us/step "
          f"({100*(tot['w16']-tot['w0'])/tot['w0']:+.3f}%)")
    print(f"untouched pool k=0   (t0)  : {tot['t0']:.1f} us/step")
    print(f"untouched pool k=640 (t16) : {tot['t16']:.1f} us/step  "
          f"delta {tot['t16']-tot['t0']:+.2f} us/step "
          f"({100*(tot['t16']-tot['t0'])/tot['t0']:+.3f}%)")
    print(f"off arm reference          : {tot['off']:.1f} us/step")
    print()
    print("share of the 640-boundary WIDE gross cost that lands outside the "
          "insert-bearing command buffers:")
    gross_w = 640 * 1.4064
    print(f"  gross WIDE at k=640 = {gross_w:.1f} us/step; untouched movement "
          f"= {tot['w16']-tot['w0']:+.2f} us/step "
          f"= {100*(tot['w16']-tot['w0'])/gross_w:+.2f}% of it")


if __name__ == "__main__":
    main()
