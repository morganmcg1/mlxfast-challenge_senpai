#!/usr/bin/env python3
"""Fit the PR47 D1 in-model chained-vs-unchained ladder from local-iterate JSONs."""
import json, glob, os, re, sys, math

OUT = sys.argv[1] if len(sys.argv) > 1 else "research/tanjiro-pr47"

rows = []
for p in sorted(glob.glob(os.path.join(OUT, "d1-*.json"))):
    tag = os.path.basename(p)[3:-5]
    if tag == "warmup":
        continue
    m = re.match(r"r(\d+)-n(\d+)(?:-c(\d))?$", tag)
    if not m:
        print("skip", tag); continue
    rep = int(m.group(1)); n = int(m.group(2))
    chain = 1 if m.group(3) is None else int(m.group(3))
    d = json.load(open(p))
    tm = d["metrics"]
    dspt = tm["decode_seconds_per_token"]
    pspt = tm["prefill_seconds_per_token"]
    S = 512000.0 * pspt          # ms, prefill component
    T = 1000.0 * dspt - S / 128.0  # ms, decode-only component
    rows.append(dict(tag=tag, rep=rep, n=n, chain=chain, dspt=dspt, pspt=pspt, S=S, T=T))

for r in rows:
    print("%-16s rep=%d n=%5d chain=%d  decode=%.6f  T=%9.4f ms  S=%9.3f ms"
          % (r["tag"], r["rep"], r["n"], r["chain"], r["dspt"], r["T"], r["S"]))

def ols(xs, ys):
    n = len(xs)
    if n < 2: return None, None
    mx = sum(xs)/n; my = sum(ys)/n
    sxx = sum((x-mx)**2 for x in xs)
    if sxx == 0: return None, None
    b = sum((x-mx)*(y-my) for x, y in zip(xs, ys)) / sxx
    a = my - b*mx
    return a, b

print()
# n=0 is shared by both arms (chain irrelevant at n=0)
base = [r for r in rows if r["n"] == 0]
for chain in (1, 0):
    arm = [r for r in rows if r["n"] > 0 and r["chain"] == chain]
    if not arm: continue
    xs = [r["n"] for r in arm]; ys = [r["T"] for r in arm]
    a, b = ols(xs, ys)
    print("arm chain=%d  npts=%2d  slope=%.4f us/disp  offset=%.4f ms  (supra-knee only, indep offset)"
          % (chain, len(arm), (b or 0)*1000.0, a or 0))
    xs2 = xs + [r["n"] for r in base]; ys2 = ys + [r["T"] for r in base]
    a2, b2 = ols(xs2, ys2)
    print("            with n=0 pooled: slope=%.4f us/disp  offset=%.4f ms" % ((b2 or 0)*1000.0, a2 or 0))
if base:
    print("n=0 T mean=%.4f ms  (npts=%d)" % (sum(r["T"] for r in base)/len(base), len(base)))
