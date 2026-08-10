#!/usr/bin/env python3
"""Splice the analyzer's report-ready block into the R108-K report, idempotently.

Rerunnable: the first run replaces the `<!--RESULTS-->` placeholder with a
BEGIN/END pair, and every later run replaces whatever sits between that pair, so
refreshing the numbers as new probe blocks land never duplicates the section.
"""
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPORT = HERE / "maple-frieren-r108k-decode-dispatch-merge.md"
ANALYZER = HERE / "maple-frieren-r108k-barrier-price-analyze.py"
SINK = sys.argv[1] if len(sys.argv) > 1 else "/tmp/r108k-barrier-price.tsv"
BEGIN = "<!--RESULTS:BEGIN-->\n"
END = "<!--RESULTS:END-->\n"

raw = subprocess.run(
    [sys.executable, str(ANALYZER), SINK, "--markdown"],
    capture_output=True, text=True, check=True,
).stdout
block = raw[raw.index("## §3.3 Results"):].rstrip() + "\n"
payload = BEGIN + block + END

text = REPORT.read_text()
if BEGIN in text:
    text = re.sub(
        re.escape(BEGIN) + ".*?" + re.escape(END), lambda _m: payload, text, flags=re.S
    )
elif "<!--RESULTS-->\n" in text:
    text = text.replace("<!--RESULTS-->\n", payload, 1)
else:
    sys.exit("no results marker found in report")
REPORT.write_text(text)

rows = raw.split("usable rows ")[1].split(",")[0]
verdict = [ln for ln in raw.splitlines() if "P-" in ln and ln.startswith("**")][-1]
print(f"spliced {len(block.splitlines())} lines from {rows} usable rows")
print(f"mechanical verdict: {verdict}")
