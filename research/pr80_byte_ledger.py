#!/usr/bin/env python3
"""Escape-adjusted decode-step scale-plane byte ledger for PR #80.

Each arm is priced from **its own** witness log, because the escape predicate
differs per packing form: the pairwise arm escapes strictly more rows than the
plain lane-major arm, so pricing every arm from one escape census overstates
the pairwise gains. The runtime emits the census under
DARKBLOOM_ATTN_SCALE_NARROW_LOG=1.

Per-row read cost, `g` = groups in the row:

    stock        g                      (one E4M3 byte per group)
    narrow       g/2 + g/8 + g/32       (nibbles + bit-4 plane + block bases)
    lane-major   g/2 + 1                (nibble run + row base)
    lm pairwise  g/4 + 1
    escaped row  g   + 1                (stock plane + its 0xFF base byte)

Usage:
    pr80_byte_ledger.py A=logA B=logB C=logC D=logD
"""
import re
import sys

# Score conversion: decode weight 0.75, M5 bandwidth 651.8 GB/s, decode window
# 5036 us/step. Derived in research/CURRENT_RESEARCH_STATE.md (#72 entry).
PCT_PER_MB = 0.75 * (1e6 / 651.8e9) / 5036e-6 * 100

# 40 layers; every 4th is full attention (48 heads), the rest sliding (64).
# qkv rows, qkv groups, o_proj groups; o_proj always has 2048 rows.
GEOM = [
    (8192 if layer % 4 == 0 else 10240, 128, 384 if layer % 4 == 0 else 512)
    for layer in range(40)
]
OPROJ_ROWS = 2048


def row_bytes(form, g):
    return {
        "stock": g,
        "narrow": g // 2 + g // 8 + g // 32,
        "lm": g // 2 + 1,
        "lm_pw": g // 4 + 1,
    }[form]


def parse(path):
    """-> {site: (form, {layer: escaped_rows})}"""
    text = open(path, errors="replace").read()
    out = {}
    for site in ("qkv", "oproj"):
        esc = {
            int(m.group(1)): int(m.group(2))
            for m in re.finditer(rf"L(\d+) escaped (\d+)/(\d+): {site}", text)
        }
        if esc:
            form = "lm_pw" if f"built lane-major pairwise: {site}" in text else "lm"
        elif re.search(rf"built: {site}", text):
            form = "narrow"
        else:
            form = "stock"
        declined = len(re.findall(rf"declined L\d+ .*: {site}", text))
        if declined:
            raise SystemExit(f"{path}: {site} declined {declined} layers")
        if form in ("lm", "lm_pw") and len(esc) != 40:
            raise SystemExit(f"{path}: {site} has {len(esc)} witness lines, want 40")
        out[site] = (form, esc)
    return out


def arm_bytes(sites):
    total = 0
    for layer, (qrows, qg, og) in enumerate(GEOM):
        for site, rows, g in (("qkv", qrows, qg), ("oproj", OPROJ_ROWS, og)):
            form, esc = sites[site]
            e = esc.get(layer, 0)
            total += (rows - e) * row_bytes(form, g) + e * (g + 1)
    return total


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    order, arms = [], {}
    for spec in sys.argv[1:]:
        name, _, path = spec.partition("=")
        arms[name] = parse(path)
        order.append(name)

    rows = {"qkv": sum(r for r, _, _ in GEOM), "oproj": 40 * OPROJ_ROWS}
    totals = {n: arm_bytes(arms[n]) for n in order}
    stock = sum(r * qg + OPROJ_ROWS * og for r, qg, og in GEOM)

    for name in order:
        sites = arms[name]
        desc = " ".join(f"{s}={sites[s][0]}" for s in ("qkv", "oproj"))
        esc = {s: sum(sites[s][1].values()) for s in ("qkv", "oproj")}
        print(
            f"{name:5s} {totals[name]:>12,} B/step   {desc:26s}"
            f" escaped qkv {esc['qkv']:5d}/{rows['qkv']} "
            f"({100*esc['qkv']/rows['qkv']:.4f}%)"
            f"  oproj {esc['oproj']:5d}/{rows['oproj']} "
            f"({100*esc['oproj']/rows['oproj']:.4f}%)"
        )
    print(f"{'stock':5s} {stock:>12,} B/step   (unpacked E4M3 planes)")
    print()
    pairs = list(zip(order, order[1:]))
    if len(order) > 2:
        pairs.append((order[0], order[-1]))
    for lo, hi in pairs:
        d = totals[lo] - totals[hi]
        print(
            f"{lo:>4s} -> {hi:<4s}: {d:>11,} B = {d/1e6:7.3f} MB"
            f" -> {d/1e6*PCT_PER_MB:+.4f} % score"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
