#!/usr/bin/env python3
"""Escape-adjusted decode-step scale-plane byte ledger for PR #80.

Reads the real per-layer `escaped N/rows` witness the runtime emits under
DARKBLOOM_ATTN_SCALE_NARROW_LOG=1, so the ledger is measured rather than
assumed. An escaped row reads the stock plane (groups bytes) plus its base
byte; a fitting row reads only its nibble run plus its base byte.
"""
import argparse
import re
import sys

# Score conversion: decode weight 0.75, M5 bandwidth 651.8 GB/s, decode window
# 5036 us/step. Derived in research/CURRENT_RESEARCH_STATE.md (#72 entry).
PCT_PER_MB = 0.75 * (1e6 / 651.8e9) / 5036e-6 * 100


def parse(path):
    text = open(path, errors="replace").read()
    out = {}
    for m in re.finditer(r"L(\d+) escaped (\d+)/(\d+): (qkv|oproj)", text):
        out[(m.group(4), int(m.group(1)))] = (int(m.group(2)), int(m.group(3)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    args = ap.parse_args()
    rows = parse(args.log)
    if len(rows) != 80:
        print(f"expected 80 witness lines, found {len(rows)}", file=sys.stderr)
        return 2

    totals = dict(stock=0, A=0, B=0, C=0, D=0)
    for layer in range(40):
        qe, qr = rows[("qkv", layer)]
        oe, orow = rows[("oproj", layer)]
        qg = 128
        og = 384 if qr == 8192 else 512
        narrow_o = 252 if og == 384 else 336
        totals["stock"] += qr * qg + orow * og
        # A: promoted frontier -- QKV lane-major, o_proj block-narrow.
        totals["A"] += (qr - qe) * (qg // 2 + 1) + qe * (qg + 1) + orow * narrow_o
        # B: + o_proj lane-major.
        totals["B"] += (
            (qr - qe) * (qg // 2 + 1) + qe * (qg + 1)
            + (orow - oe) * (og // 2 + 1) + oe * (og + 1)
        )
        # C: + pairwise QKV.
        totals["C"] += (
            (qr - qe) * (qg // 4 + 1) + qe * (qg + 1)
            + (orow - oe) * (og // 2 + 1) + oe * (og + 1)
        )
        # D: + pairwise o_proj.
        totals["D"] += (
            (qr - qe) * (qg // 4 + 1) + qe * (qg + 1)
            + (orow - oe) * (og // 4 + 1) + oe * (og + 1)
        )

    for site in ("qkv", "oproj"):
        esc = sum(v[0] for k, v in rows.items() if k[0] == site)
        tot = sum(v[1] for k, v in rows.items() if k[0] == site)
        print(f"{site:6s} escaped {esc:6d} / {tot:7d} rows = {100*esc/tot:.4f}%")
    print()
    for name in ("stock", "A", "B", "C", "D"):
        print(f"{name:6s} {totals[name]:>12,} B/step")
    print()
    for label, lo, hi in (
        ("O-LM   (A->B)", "A", "B"),
        ("PW-QKV (B->C)", "B", "C"),
        ("PW-O   (C->D)", "C", "D"),
        ("stack  (A->D)", "A", "D"),
    ):
        d = totals[lo] - totals[hi]
        print(f"{label}: {d:>11,} B = {d/1e6:7.3f} MB -> {d/1e6*PCT_PER_MB:+.4f} % score")
    return 0


if __name__ == "__main__":
    sys.exit(main())
