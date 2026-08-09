#!/usr/bin/env python3
"""Clean defined-symbol comparison for the R104-C host-side channel gate.

The gate script concatenated `nm -Ug` with `nm -U`, which double-counted globals
and let string-literal fragments through.  This re-reads the surviving pass-2
objects and keeps only Swift-mangled defined names, once each.
"""
import json
import os
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OBJREL = ".build-worker/arm64-apple-macosx/release/MLXFastModel.build"
OUT = os.path.join(ROOT, "research/artifacts/tanjiro-r104c/hostgate/symdiff_clean.json")


def defined(rev):
    d = os.path.join(ROOT, ".mlxfast-private", "r103b-" + rev, OBJREL)
    objs = [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".o")]
    out = subprocess.run(["nm", "-jU"] + objs, capture_output=True, text=True).stdout
    return {s for s in out.split("\n") if s.startswith("_$s")}


syms = {r: defined(r) for r in ("old", "mid", "new")}
report = {r: {"defined_mangled": len(syms[r])} for r in syms}
for r in ("old", "mid", "new"):
    print("%s: %d distinct Swift-mangled defined symbols" % (r, len(syms[r])))

pairs = {}
for a, b in (("old", "mid"), ("mid", "new"), ("old", "new")):
    only_a = sorted(syms[a] - syms[b])
    only_b = sorted(syms[b] - syms[a])
    pairs["%s->%s" % (a, b)] = {"only_" + a: only_a, "only_" + b: only_b}
    print("\n%s -> %s : only_%s=%d  only_%s=%d"
          % (a, b, a, len(only_a), b, len(only_b)))
    if a == "mid" and b == "new":
        for s in only_a:
            print("   -", s)
        for s in only_b:
            print("   +", s)

report["pairs"] = pairs
with open(OUT, "w") as fh:
    json.dump(report, fh, indent=1)
print("\nwrote", OUT)
