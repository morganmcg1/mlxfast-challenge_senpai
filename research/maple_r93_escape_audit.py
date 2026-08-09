#!/usr/bin/env python3
"""Count lane-major NVFP4 scale-bank escaped rows (research-only).

`DARKBLOOM_ATTN_SCALE_NARROW_LOG=1` makes `LagunaNarrowScaleLog` print one
`escaped <n>/<rows>` line per built bank. Escaped rows read the 128 B/row stock
scale plane instead of the 32 B/row packed nibble plane, so their fraction is
the only free parameter in the R93-C QKV/o_proj byte arithmetic.

  python3 research/maple_r93_escape_audit.py OUTDIR
"""
import collections
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = re.compile(
    r"narrow-scales (lane-major(?: pairwise)?) L(\d+) escaped (\d+)/(\d+): (.+)")


def main() -> int:
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    err = os.path.join(outdir, "escape.err")
    env = dict(os.environ)
    env["DARKBLOOM_ATTN_SCALE_NARROW_LOG"] = "1"
    env.pop("NEZUKO_R93_PROBE", None)
    env.pop("DARKBLOOM_GPU_PROFILE", None)
    proc = subprocess.run(
        [sys.executable, os.path.join(REPO, "research/decode_probe.py"),
         "--steps", "2", "--stderr", err],
        cwd=REPO, env=env, capture_output=True, text=True)
    text = open(err).read() if os.path.exists(err) else ""
    text += proc.stderr + proc.stdout

    per_site = collections.defaultdict(lambda: [0, 0, 0])  # escaped, rows, banks
    for form, _layer, esc, rows, site in LINE.findall(text):
        key = f"{site.strip()} [{form}]"
        per_site[key][0] += int(esc)
        per_site[key][1] += int(rows)
        per_site[key][2] += 1

    print(f"returncode={proc.returncode}  log bytes={len(text)}")
    if not per_site:
        print("no `escaped n/rows` lines found -- check that the build carries "
              "LagunaRuntimeWeights.swift:939 and that stderr was captured")
    for site, (esc, rows, banks) in sorted(per_site.items()):
        pct = 100.0 * esc / rows if rows else 0.0
        print(f"  {site:<44} banks={banks:<4} escaped {esc}/{rows} = {pct:.4f}%")

    out = {site: {"escaped": e, "rows": r, "banks": b,
                  "escaped_pct": 100.0 * e / r if r else 0.0}
           for site, (e, r, b) in per_site.items()}
    with open(os.path.join(outdir, "escape.json"), "w") as f:
        json.dump(out, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
