#!/usr/bin/env python3
"""Analyse the A0 dispatch-type discriminator sweep.

Reads a `research/nezuko-a0-dispatch-type` style output directory produced by
`research/nezuko_a0_dispatch_type_abba.sh` and reports, per phase, the
serial-minus-concurrent delta in all three currencies that were recorded in the
same runs: decode step wall, gpu_busy_sum, and the per-kernel breakdown.

The per-kernel section is what discriminates the pre-registered resolutions:

  R-A seam pipelining : per-kernel busy delta tracks *call count*
  R-B sibling shadow  : per-kernel busy delta concentrates in a few kernels
  R-C currency mismatch: busy barely moves while wall moves

Usage: nezuko_a0_analyze.py <dir> [--top 25]
"""
from __future__ import annotations

import argparse
import itertools
import re
import statistics
import sys
from pathlib import Path

PROFILE_RE = re.compile(
    r"per steady step: wall=([\d.]+) ms gpu_busy_sum=([\d.]+) ms "
    r"gpu_busy_union=([\d.]+) ms gap=([-\d.]+) ms \([-\d.]+% of wall\) "
    r"cbs=([\d.]+) dispatches=([\d.]+)")
KERNEL_RE = re.compile(r"^\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s\s(.+)$")
DIVERGE_RE = re.compile(r"teacher-forced greedy tokens: (\d+) divergences")


def load_run(txt: Path):
    """Return a dict of per-run scalars plus the per-kernel table."""
    out = {"tag": txt.stem, "kernels": {}}
    body = txt.read_text(errors="replace")

    m = DIVERGE_RE.search(body)
    out["divergences"] = int(m.group(1)) if m else None

    steps = txt.with_suffix(".steps.txt")
    if steps.exists():
        vals = [float(x) for x in steps.read_text().split()]
        out["wall_median_ms"] = statistics.median(vals[1:])
        out["wall_mean_ms"] = statistics.mean(vals[1:])
        out["n_steps"] = len(vals) - 1

    m = PROFILE_RE.search(body)
    if m:
        (out["prof_wall_ms"], out["busy_sum_ms"], out["busy_union_ms"],
         out["gap_ms"], out["cbs"], out["dispatches"]) = (
            float(g) for g in m.groups())

    in_table = False
    for line in body.splitlines():
        if line.startswith("  us/step"):
            in_table = True
            continue
        if in_table:
            km = KERNEL_RE.match(line)
            if not km:
                if line.strip() == "" or line.lstrip().startswith("..."):
                    continue
                in_table = False
                continue
            us_step, _share, n_step, us_call, key = km.groups()
            out["kernels"][key] = (float(us_step), float(n_step), float(us_call))
    return out


def perm_p(a, b):
    """Two-sided permutation p on the difference of medians."""
    pool = list(a) + list(b)
    k = len(a)
    obs = abs(statistics.median(b) - statistics.median(a))
    idx = range(len(pool))
    hits = total = 0
    for combo in itertools.combinations(idx, k):
        left = [pool[i] for i in combo]
        right = [pool[i] for i in idx if i not in combo]
        total += 1
        if abs(statistics.median(right) - statistics.median(left)) >= obs - 1e-12:
            hits += 1
    return hits, total


def summarize(name, conc, ser, key, unit="ms"):
    a = [r[key] for r in conc if key in r]
    b = [r[key] for r in ser if key in r]
    if not a or not b:
        return None
    ma, mb = statistics.median(a), statistics.median(b)
    print(f"  {name:<16} concurrent={ma:9.3f} serial={mb:9.3f} "
          f"delta={mb - ma:+8.3f} {unit} ({(mb - ma) / ma * 100:+6.2f}%)")
    print(f"    {'':<14} conc runs: " + " ".join(f"{v:.3f}" for v in a))
    print(f"    {'':<14} ser  runs: " + " ".join(f"{v:.3f}" for v in b))
    if len(a) == len(b) >= 3:
        hits, total = perm_p(a, b)
        print(f"    {'':<14} permutation p = {hits}/{total} = {hits / total:.4f}"
              f"   separation={'complete' if max(a) < min(b) or max(b) < min(a) else 'overlap'}")
    return mb - ma


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    root = Path(args.dir)
    runs = [load_run(p) for p in sorted(root.glob("*.txt"))
            if not p.name.endswith(".steps.txt")]

    phases = sorted({r["tag"].split("_")[0] for r in runs})
    for phase in phases:
        sel = [r for r in runs if r["tag"].startswith(phase + "_")]
        conc = [r for r in sel if r["tag"].endswith("_concurrent")]
        ser = [r for r in sel if r["tag"].endswith("_serial")]
        print(f"\n{'=' * 78}\nphase {phase}  "
              f"({len(conc)} concurrent, {len(ser)} serial runs, "
              f"hook={'ON' if phase.startswith('h1') else 'OFF'})\n{'=' * 78}")
        bad = [r["tag"] for r in sel if r.get("divergences") != 0]
        print(f"  divergences: {'ALL ZERO' if not bad else 'NONZERO/MISSING in ' + str(bad)}")
        d_wall = summarize("step wall", conc, ser, "wall_median_ms")
        summarize("step wall(mean)", conc, ser, "wall_mean_ms")
        d_busy = summarize("gpu_busy_sum", conc, ser, "busy_sum_ms")
        summarize("gpu_busy_union", conc, ser, "busy_union_ms")
        summarize("gap (wall-union)", conc, ser, "gap_ms")
        summarize("cbs/step", conc, ser, "cbs", unit="cb")
        summarize("dispatches/step", conc, ser, "dispatches", unit="disp")

        if d_wall is not None and d_busy is not None:
            print(f"\n  DISCRIMINATOR: wall delta {d_wall * 1e3:+.1f} us/step, "
                  f"busy_sum delta {d_busy * 1e3:+.1f} us/step, "
                  f"busy/wall = {d_busy / d_wall if d_wall else float('nan'):.3f}")

        keys = set()
        for r in sel:
            keys |= set(r["kernels"])
        if not keys:
            continue
        rows = []
        for k in keys:
            ca = [r["kernels"][k][0] for r in conc if k in r["kernels"]]
            cb = [r["kernels"][k][0] for r in ser if k in r["kernels"]]
            na = [r["kernels"][k][1] for r in conc if k in r["kernels"]]
            nb = [r["kernels"][k][1] for r in ser if k in r["kernels"]]
            if not ca or not cb:
                continue
            mc, ms_ = statistics.median(ca), statistics.median(cb)
            nc, ns_ = statistics.median(na), statistics.median(nb)
            rows.append((ms_ - mc, k, mc, ms_, nc, ns_))
        rows.sort(key=lambda t: -t[0])
        tot = sum(t[0] for t in rows)
        tot_calls = sum(t[4] for t in rows)
        print(f"\n  per-kernel gpu_busy_sum delta (serial - concurrent), "
              f"total {tot:+.1f} us/step over {tot_calls:.0f} calls/step "
              f"= {tot / tot_calls if tot_calls else float('nan'):+.3f} us/call")
        print(f"  {'d_us/step':>10} {'conc':>9} {'serial':>9} {'n/step':>7} "
              f"{'d_us/call':>10} {'share_d':>8}  kernel")
        for d, k, mc, ms_, nc, _ns in rows[:args.top]:
            print(f"  {d:10.1f} {mc:9.1f} {ms_:9.1f} {nc:7.2f} "
                  f"{d / nc if nc else float('nan'):10.3f} "
                  f"{d / tot * 100 if tot else float('nan'):7.1f}%  {k}")
        rest = rows[args.top:]
        if rest:
            print(f"  {sum(t[0] for t in rest):10.1f} {'':9} {'':9} "
                  f"{sum(t[4] for t in rest):7.2f} {'':10} "
                  f"{sum(t[0] for t in rest) / tot * 100 if tot else 0:7.1f}%  "
                  f"... {len(rest)} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
