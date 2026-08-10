#!/usr/bin/env python3
"""Fail loudly when the R108-K report's hand-written figures drift from the sink.

The §3.3 block is spliced from the analyzer, but the summary table, §3.4, §3.5 and
the prediction table restate the same figures in prose. As probe blocks land, the
fitted values move and those restatements go stale. This recomputes the canonical
figures from the sink and checks each one appears verbatim in the report.
"""
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPORT = HERE / "maple-frieren-r108k-decode-dispatch-merge.md"
ANALYZER = HERE / "maple-frieren-r108k-barrier-price-analyze.py"
SINK = sys.argv[1] if len(sys.argv) > 1 else "/tmp/r108k-barrier-price.tsv"
DISPATCHES_PER_STEP = 40  # family E, advisor's corrected n (comment 6)
DECODE_WEIGHT = 0.75

raw = subprocess.run(
    [sys.executable, str(ANALYZER), SINK], capture_output=True, text=True, check=True
).stdout
# The spliced §3.3 block is regenerated from the sink and so always agrees with it;
# checking it would make this script vacuous. Only hand-written prose can go stale.
report = re.sub(
    r"<!--RESULTS:BEGIN-->.*?<!--RESULTS:END-->", "", REPORT.read_text(), flags=re.S
)

LADDER = re.compile(
    r"(unchained / concurrent|chained / serialized) \(.*?\): k = "
    r"([+-][\d.]+) \[([+-][\d.]+), ([+-][\d.]+)\].*?\(B=(\d+),(\d+)\)"
)
CONTROL = re.compile(r"mean\(C\)=([\d.]+)")

fits = {m.group(1): tuple(m.group(i) for i in (2, 3, 4, 5, 6)) for m in LADDER.finditer(raw)}
if "unchained / concurrent" not in fits:
    sys.exit("analyzer produced no unchained rung fit; nothing to check")

k, lo, hi, b_low, b_high = fits["unchained / concurrent"]
control = float(CONTROL.search(raw).group(1))

print(f"sink: {SINK}   control mean {control:.2f} M4 us/step   blocks {b_low}/{b_high}")
print(f"canonical k (unchained) = {k} [{lo}, {hi}] M4 us/dispatch")
if "chained / serialized" in fits:
    ck, clo, chi, *_ = fits["chained / serialized"]
    print(f"canonical k (chained)   = {ck} [{clo}, {chi}] M4 us/dispatch")

print("\nprize at each k, for the summary table and §3.5:")
for label, value in (("point", k), ("lo", lo), ("hi", hi)):
    us = float(value) * DISPATCHES_PER_STEP
    pct_dec = 100.0 * us / control
    print(f"  {label:5s} k={float(value):+.4f} -> {us:6.1f} us/step "
          f"{pct_dec:.2f} % decode  {pct_dec * DECODE_WEIGHT:.2f} % score")

stale = [f"{name} = {want}" for name, want in
         (("k point", k), ("k lo", lo.lstrip("+")), ("k hi", hi.lstrip("+")))
         if want.lstrip("+") not in report]
print("\nverbatim presence in report:")
if stale:
    for item in stale:
        print(f"  STALE  {item} does not appear in the report text")
    sys.exit(1)
print("  OK  every canonical k figure appears verbatim")
