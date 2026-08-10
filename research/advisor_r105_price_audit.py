#!/usr/bin/env python3
"""Rule 105.11 — sweep the live document for uncorrected M5-price conversions.

Rule 105 established that `%cs = delta_M4[us/step] * k * 0.015228` with
k = alpha (bytes, 0.4369) or beta (latency, 0.5).  A conversion that used the
bare price 0.015228 on an M4 delta over-credits by 1/k = 2.29x (bytes) or
2.00x (latency).

This scans for `<A> us/step` and `<B> %` appearing near each other and reports
every pair where B/A is within tolerance of the BARE price -- i.e. the
signature of the host-unit error -- versus the alpha/beta-corrected prices.

Run:  python3 research/advisor_r105_price_audit.py [file ...]
"""
import re
import sys

PRICE = 0.015228
ALPHA = 0.4369
BETA = 0.5
TOL = 0.02          # 2 % relative tolerance on the implied ratio

NUM = r"([0-9]+(?:[.,][0-9]+)?)"
US = re.compile(NUM + r"\s*(?:µs|us)\s*/\s*(?:step|token)")
PCT = re.compile(NUM + r"\s*%")

FILES = sys.argv[1:] or ["research/CURRENT_RESEARCH_STATE.md"]


def f(s):
    return float(s.replace(",", ""))


def classify(ratio):
    """Return label for an implied %-per-us/step ratio."""
    for name, k in (("BARE  (M5 price on an M4 delta -> WRONG)", 1.0),
                    ("alpha (bytes, correct)", ALPHA),
                    ("beta  (latency, correct)", BETA),
                    ("alpha-lo (0.389 sensitivity)", 0.389)):
        want = k * PRICE
        if abs(ratio - want) / want < TOL:
            return name
    return None


hits = {}
for path in FILES:
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError as e:
        print(f"skip {path}: {e}")
        continue
    for i, line in enumerate(lines, 1):
        us = [f(m) for m in US.findall(line)]
        pc = [f(m) for m in PCT.findall(line)]
        if not us or not pc:
            continue
        for a in us:
            for b in pc:
                if a <= 0 or b <= 0:
                    continue
                lab = classify(b / a)
                if lab and lab.startswith("BARE"):
                    hits.setdefault(path, []).append((i, a, b, line.strip()))

total = 0
for path, rows in hits.items():
    # de-duplicate by line
    seen = set()
    print(f"\n=== {path} ===")
    for ln, a, b, txt in rows:
        if ln in seen:
            continue
        seen.add(ln)
        total += 1
        corr_a = a * ALPHA * PRICE
        corr_b = a * BETA * PRICE
        print(f"\nL{ln}: {a} us/step  <->  {b} %   (ratio {b/a:.6f} "
              f"= bare price {PRICE})")
        print(f"      corrected: {corr_a:.4f} % (bytes, alpha) / "
              f"{corr_b:.4f} % (latency, beta)")
        print(f"      | {txt[:220]}")

print(f"\n\nTOTAL candidate uncorrected conversions: {total}")
print("NOTE: a hit is only an error if the us/step figure is an M4 measurement.")
print("      If the figure is already M5, the bare price is correct.")
