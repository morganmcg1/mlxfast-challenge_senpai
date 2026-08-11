#!/usr/bin/env python3
"""Analyse the R125-A shared-QMV threadgroup-width atlas campaign.

Reads the `decode_probe.py --profile` logs written by
`research/maple_r125a_atlas.sh` (one per slot, named `b<block>_s<slot>_tg<W>.log`)
and reports:

  * the per-step GPU-busy cost of the shared-expert SwiGLU QMV kernel family
    under each threadgroup width, as an arm mean and as a within-block paired
    difference (the mirrored 64 256 256 64 order makes the pairing exact);
  * a negative control over every untouched kernel, against the +/-0.655 us/step
    atlas resolution established in research/maple-alphonse-r109e-bwatlas.py.

Usage: python3 research/maple_r125a_analyze.py OUTDIR [OUTDIR ...]
"""
from __future__ import annotations

import math
import os
import re
import statistics
import sys

SHARED_QMV = "shared_nvfp4_swiglu_qmv_rows1_halved"
RESOLUTION_US = 0.655
ROW = re.compile(
    r"^\s*([0-9.]+)\s+([0-9.]+)%\s+([0-9.]+)\s+([0-9.]+)\s\s(.+?)\s*$")
SLOT = re.compile(r"^b(\d+)_s(\d+)_tg(\d+)$")


def parse_log(path: str):
    """-> (per-step totals by kernel, header dict) or None if the slot failed."""
    kernels: dict[str, tuple[float, float]] = {}
    header: dict[str, float] = {}
    in_table = False
    with open(path, errors="replace") as fh:
        for line in fh:
            if line.startswith("per steady step:"):
                for k, v in re.findall(r"(\w+)=([0-9.]+)", line):
                    header[k] = float(v)
                continue
            if line.lstrip().startswith("us/step"):
                in_table = True
                continue
            if in_table:
                m = ROW.match(line.rstrip("\n"))
                if not m:
                    if line.strip():
                        in_table = False
                    continue
                us_step, _share, n_step, _us_call, kernel = m.groups()
                kernels[kernel] = (float(us_step), float(n_step))
    if not kernels or "wall" not in header:
        return None
    return kernels, header


def family_total(kernels: dict[str, tuple[float, float]], needle: str):
    us = sum(v[0] for k, v in kernels.items() if needle in k)
    n = sum(v[1] for k, v in kernels.items() if needle in k)
    return us, n


def mean_sem(xs):
    m = statistics.mean(xs)
    if len(xs) < 2:
        return m, float("nan")
    return m, statistics.stdev(xs) / math.sqrt(len(xs))


# Two-sided 95% t quantiles for small samples, indexed by degrees of freedom.
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
       7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179}


def ci95(xs):
    if len(xs) < 2:
        return float("nan"), float("nan")
    m, s = statistics.mean(xs), statistics.stdev(xs) / math.sqrt(len(xs))
    t = T95.get(len(xs) - 1, 1.96)
    return m - t * s, m + t * s


def main(outdirs):
    slots = {}
    for outdir in outdirs:
        for name in sorted(os.listdir(outdir)):
            if not name.endswith(".log"):
                continue
            tag = name[:-4]
            m = SLOT.match(tag)
            if not m:
                continue
            parsed = parse_log(os.path.join(outdir, name))
            if parsed is None:
                print(f"WARNING: {outdir}/{name} has no usable profile table")
                continue
            block, slot, tg = int(m.group(1)), int(m.group(2)), int(m.group(3))
            slots[(block, slot)] = (tg, *parsed)

    if not slots:
        raise SystemExit("no parseable slots found")

    arms = sorted({v[0] for v in slots.values()})
    blocks = sorted({b for b, _ in slots})
    print(f"slots={len(slots)} blocks={blocks} arms={arms}\n")

    print(f"{'block':>5} {'slot':>4} {'tg':>4} {'qmv us/step':>12} "
          f"{'n/step':>7} {'busy ms':>8} {'wall ms':>8}")
    per_arm: dict[int, list[float]] = {a: [] for a in arms}
    for (block, slot), (tg, kernels, header) in sorted(slots.items()):
        us, n = family_total(kernels, SHARED_QMV)
        per_arm[tg].append(us)
        print(f"{block:5d} {slot:4d} {tg:4d} {us:12.2f} {n:7.2f} "
              f"{header.get('gpu_busy_sum', float('nan')):8.3f} "
              f"{header.get('wall', float('nan')):8.3f}")

    print("\n== shared-QMV family, arm means ==")
    base_arm = arms[0]
    for a in arms:
        m, s = mean_sem(per_arm[a])
        print(f"tg={a:4d} n={len(per_arm[a])} mean={m:8.2f} sem={s:5.2f} us/step")

    print("\n== within-block paired deltas vs tg=%d ==" % base_arm)
    for a in arms[1:]:
        deltas = []
        for b in blocks:
            ref = [v[1] for (bb, _), v in slots.items()
                   if bb == b and v[0] == base_arm]
            cand = [v[1] for (bb, _), v in slots.items()
                    if bb == b and v[0] == a]
            if not ref or not cand:
                continue
            r = statistics.mean(family_total(k, SHARED_QMV)[0] for k in ref)
            c = statistics.mean(family_total(k, SHARED_QMV)[0] for k in cand)
            deltas.append(c - r)
            print(f"  block {b}: tg{base_arm}={r:7.2f} tg{a}={c:7.2f} "
                  f"delta={c - r:+7.2f}")
        m, s = mean_sem(deltas)
        lo, hi = ci95(deltas)
        base_mean = statistics.mean(per_arm[base_arm])
        print(f"  tg{a} vs tg{base_arm}: delta={m:+.2f} +/-{s:.2f} us/step "
              f"CI95=[{lo:+.2f},{hi:+.2f}] "
              f"({m / base_mean * 100:+.2f}% of the tg{base_arm} kernel cost); "
              f"{sum(1 for d in deltas if d > 0)}/{len(deltas)} blocks positive")

    print("\n== negative control: untouched kernels ==")
    common = None
    for _, kernels, _ in slots.values():
        keys = {k for k in kernels if SHARED_QMV not in k}
        common = keys if common is None else (common & keys)
    flagged = 0
    for a in arms[1:]:
        for kernel in sorted(common):
            deltas = []
            for b in blocks:
                ref = [v[1][kernel][0] for (bb, _), v in slots.items()
                       if bb == b and v[0] == base_arm]
                cand = [v[1][kernel][0] for (bb, _), v in slots.items()
                        if bb == b and v[0] == a]
                if ref and cand:
                    deltas.append(statistics.mean(cand) - statistics.mean(ref))
            if not deltas:
                continue
            m, _ = mean_sem(deltas)
            if abs(m) > RESOLUTION_US:
                flagged += 1
                ref_all = statistics.mean(
                    v[1][kernel][0] for v in slots.values() if v[0] == base_arm)
                sign = sum(1 for d in deltas if d > 0)
                print(f"  tg{a} {kernel[:58]:58s} delta={m:+7.2f} "
                      f"({m / ref_all * 100:+6.2f}% of {ref_all:8.2f}) "
                      f"{sign}/{len(deltas)} positive")
    print(f"  {flagged}/{len(common) * max(1, len(arms) - 1)} untouched-kernel "
          f"comparisons exceed the +/-{RESOLUTION_US} us/step atlas resolution")

    print("\n== whole-step GPU-busy sum (diagnostic, SPLIT=1 inflated) ==")
    for a in arms:
        xs = [h.get("gpu_busy_sum", float("nan"))
              for tg, _, h in slots.values() if tg == a]
        m, s = mean_sem(xs)
        print(f"tg={a:4d} busy_sum mean={m:8.3f} sem={s:.3f} ms/step")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["/tmp/maple-r125a-atlas"]))
