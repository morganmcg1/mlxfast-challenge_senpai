#!/usr/bin/env python3
"""Identical-tree noise floor for the official M5 instrument (PR #13).

Reads the archived official receipts in this directory and prints the
normalised score, the S/T decomposition and the replicate spreads.

    S = 512 * prefill_seconds_per_token   (512-token seed forward)
    T = decode_seconds_per_token - S/128  (steady one-token decode step)
    norm = (0.013890/D)**0.75 * (0.0003845/P)**0.25

The canonical baseline is the mode of the last 12 promoted official runs, so
`norm` removes the session baseline draw that dominates `officialScore`.
"""

import glob
import json
import os

CANON_D = 0.013890
CANON_P = 0.0003845


def metrics(path):
    with open(path) as fh:
        doc = json.load(fh)
    sub = doc.get("submission", doc)
    om = sub.get("officialMetrics")
    if isinstance(om, str):
        om = json.loads(om)
    return sub, om


def norm(d, p):
    return (CANON_D / d) ** 0.75 * (CANON_P / p) ** 0.25


def decompose(d, p):
    """Return (S, T) in milliseconds."""
    s = 512.0 * p
    return s * 1e3, (d - s / 128.0) * 1e3


def spread(vals):
    lo, hi = min(vals), max(vals)
    return 100.0 * (hi - lo) / lo


def main():
    rows = []
    here = os.path.dirname(os.path.abspath(__file__))
    for path in sorted(glob.glob(os.path.join(here, "[A-Z]_*.json"))):
        label = os.path.basename(path).split("_")[0]
        sub, om = metrics(path)
        if not om:
            print(f"{label}: {sub.get('status')}, no metrics yet")
            continue
        d = om["decode_seconds_per_token"]
        p = om["prefill_seconds_per_token"]
        bd = om["baseline_decode_seconds_per_token"]
        bp = om["baseline_prefill_seconds_per_token"]
        s, t = decompose(d, p)
        sb, tb = decompose(bd, bp)
        rows.append(
            dict(
                label=label, score=sub.get("officialScore"), norm=norm(d, p),
                d=d, p=p, bd=bd, bp=bp, s=s, t=t, sb=sb, tb=tb,
                ds=om["decode_speedup"], ps=om["prefill_speedup"],
                sigma=100.0 * (s / 1e3 / 128.0) / d,
            )
        )

    if not rows:
        return

    hdr = (f"{'run':>4} {'official':>12} {'norm':>10} {'S ms':>9} {'T ms':>9} "
           f"{'S_b ms':>10} {'T_b ms':>9} {'T_b/T':>7} {'sigma%':>7}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        sc = f"{r['score']:.7f}" if r["score"] is not None else "-"
        print(f"{r['label']:>4} {sc:>12} {r['norm']:10.7f} {r['s']:9.4f} "
              f"{r['t']:9.5f} {r['sb']:10.4f} {r['tb']:9.5f} "
              f"{r['tb'] / r['t']:7.4f} {r['sigma']:7.2f}")

    if len(rows) < 2:
        return

    print(f"\nspreads over {len(rows)} identical-tree replicates, (max-min)/min %:")
    keys = [
        ("official score", "score"), ("NORMALISED score", "norm"),
        ("candidate S", "s"), ("candidate T", "t"),
        ("candidate D", "d"), ("candidate P", "p"),
        ("baseline S", "sb"), ("baseline T", "tb"),
        ("baseline D", "bd"), ("baseline P", "bp"),
        ("decode_speedup", "ds"), ("prefill_speedup", "ps"),
    ]
    for name, key in keys:
        vals = [r[key] for r in rows if r[key] is not None]
        if len(vals) == len(rows):
            print(f"  {name:<17} {spread(vals):7.3f}   "
                  + " ".join(f"{v:.8g}" for v in vals))

    ratio = spread([r["score"] for r in rows]) / spread([r["norm"] for r in rows])
    print(f"\nnormalising is {ratio:.1f}x tighter than the published score")


if __name__ == "__main__":
    main()
