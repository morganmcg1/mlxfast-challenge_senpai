#!/usr/bin/env python3
"""Static live-across-barrier pressure for the residual_rms_router variants.

Counts SSA values that are defined before a threadgroup barrier and still used
after it. That count is the direct static proxy for the register live ranges a
hoist extends across the barrier, and it costs no GPU time to obtain.

pf0  = no prefetch salvo
pf1  = four loads hoisted above the first barrier
pf1c = the same four loads issued below that barrier
"""
import re
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / "msl"
DEF = re.compile(r"^\s*(%[\w.]+)\s*=")
USE = re.compile(r"(%[\w.]+)")
BARRIER = re.compile(r"call.*barrier", re.I)


def analyse(path: Path):
    lines = path.read_text().splitlines()
    # Restrict to the kernel body: AIR metadata after the first "!" block is noise.
    body = [l for l in lines if not l.startswith("!") and not l.startswith("attributes")]

    barrier_idx = [i for i, l in enumerate(body) if BARRIER.search(l)]
    defs = {}
    for i, l in enumerate(body):
        m = DEF.match(l)
        if m:
            defs.setdefault(m.group(1), i)

    out = []
    for bi in barrier_idx:
        live = set()
        for j in range(bi + 1, len(body)):
            for u in USE.findall(body[j]):
                d = defs.get(u)
                if d is not None and d < bi:
                    live.add(u)
        out.append(len(live))
    return out, len(defs), len(barrier_idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="also write the counts as JSON")
    args = ap.parse_args()

    rows = []
    for v in ("pf0", "pf1", "pf1c"):
        p = HERE / f"r100c_rpg8_{v}.air.ll"
        if not p.exists():
            print(f"missing {p}", file=sys.stderr)
            return 1
        live, ndefs, nbar = analyse(p)
        rows.append((v, live, ndefs, nbar))

    print(f"{'variant':6} {'ssa defs':>9} {'barriers':>9}  live-across-barrier (per barrier)")
    for v, live, ndefs, nbar in rows:
        print(f"{v:6} {ndefs:9d} {nbar:9d}  {live}  max={max(live) if live else 0}")

    print()
    base = dict((v, live) for v, live, _, _ in rows)
    if all(len(base[v]) == len(base["pf0"]) for v in base):
        print("per-barrier delta vs pf0:")
        for v in ("pf1", "pf1c"):
            d = [a - b for a, b in zip(base[v], base["pf0"])]
            print(f"  {v:5} {d}  sum={sum(d):+d}")
        d = [a - b for a, b in zip(base["pf1"], base["pf1c"])]
        print(f"  pf1 - pf1c (placement only) {d}  sum={sum(d):+d}")

    if args.json:
        doc = {
            v: {"ssa_defs": n, "barriers": b, "live_across_barrier": live,
                "live_max": max(live) if live else 0}
            for v, live, n, b in rows
        }
        for a, b in (("pf1", "pf0"), ("pf1c", "pf0"), ("pf1", "pf1c")):
            doc[f"delta_{a}_minus_{b}"] = [
                x - y for x, y in zip(base[a], base[b])]
        with open(args.json, "w") as fh:
            json.dump(doc, fh, indent=1, sort_keys=True)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
