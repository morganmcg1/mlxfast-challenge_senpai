#!/usr/bin/env python3
"""Fit the PR47 D1 in-model chained-vs-unchained ladder from local-iterate JSONs.

usage: tanjiro-pr47-d1-fit.py [OUTDIR] [PREFIX]
  OUTDIR default research/tanjiro-pr47
  PREFIX default "d1-"   (use "d1-tg8-" for the tg=8 addendum)
"""
import json, glob, os, re, sys, math

OUT = sys.argv[1] if len(sys.argv) > 1 else "research/tanjiro-pr47"
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "d1-"

rows = []
for p in sorted(glob.glob(os.path.join(OUT, PREFIX + "*.json"))):
    tag = os.path.basename(p)[len(PREFIX):-5]
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

print("== %s/%s* ==" % (OUT, PREFIX))
for r in rows:
    print("%-16s rep=%d n=%5d chain=%d  decode=%.6f  T=%9.4f ms  S=%9.3f ms"
          % (r["tag"], r["rep"], r["n"], r["chain"], r["dspt"], r["T"], r["S"]))

def ols(xs, ys):
    n = len(xs)
    if n < 2: return None, None, float("nan"), 0.0
    mx = sum(xs)/n; my = sum(ys)/n
    sxx = sum((x-mx)**2 for x in xs)
    if sxx == 0: return None, None, float("nan"), 0.0
    b = sum((x-mx)*(y-my) for x, y in zip(xs, ys)) / sxx
    a = my - b*mx
    resid = [y - (a + b*x) for x, y in zip(xs, ys)]
    if n > 2:
        s2 = sum(e*e for e in resid) / (n - 2)
        return a, b, math.sqrt(s2 / sxx), math.sqrt(s2)
    return a, b, float("nan"), 0.0

print()
# n=0 is shared by both arms (chain is irrelevant when no empties are injected)
base = [r for r in rows if r["n"] == 0]
T0 = sum(r["T"] for r in base)/len(base) if base else float("nan")
fit = {}
for chain in (1, 0):
    arm = [r for r in rows if r["n"] > 0 and r["chain"] == chain]
    if not arm: continue
    xs = [r["n"] for r in arm]; ys = [r["T"] for r in arm]
    a, b, se_b, rms = ols(xs, ys)
    knee = (T0 - a)/b if (b and T0 == T0) else float("nan")
    fit[chain] = dict(slope=b, offset=a, se=se_b, rms=rms)
    print("arm chain=%d  npts=%2d  slope=%.4f +-%.4f us/disp  offset=%.4f ms  residRMS=%.4f ms  implied knee=%.1f"
          % (chain, len(arm), b*1000.0, se_b*1000.0, a, rms, knee))
    xs2 = xs + [r["n"] for r in base]; ys2 = ys + [r["T"] for r in base]
    a2, b2, _, _ = ols(xs2, ys2)
    print("            with n=0 pooled: slope=%.4f us/disp  offset=%.4f ms" % (b2*1000.0, a2))
if base:
    spread = (max(r["T"] for r in base) - min(r["T"] for r in base)) if len(base) > 1 else 0.0
    print("n=0 T mean=%.4f ms  (npts=%d, spread=%.4f ms)" % (T0, len(base), spread))

if 1 in fit and 0 in fit:
    sc, su = fit[1]["slope"], fit[0]["slope"]
    ec, eu = fit[1]["se"], fit[0]["se"]
    ratio = sc/su
    print()
    print("ratio chained/unchained slope = %.4f   excess = %.4f us/dispatch" % (ratio, (sc-su)*1000.0))
    if ec == ec and eu == eu:
        rel = math.sqrt((ec/sc)**2 + (eu/su)**2)
        print("  ratio 1sigma = %.4f  -> 1sd CI [%.4f, %.4f]   3sd CI [%.4f, %.4f]"
              % (ratio*rel, ratio*(1-rel), ratio*(1+rel), ratio*(1-3*rel), ratio*(1+3*rel)))

# Per-point pairwise chained-minus-unchained excess (same rep, same n): an
# estimator independent of both regression fits, so it cross-checks the ratio.
print()
pairs = {}
for r in rows:
    if r["n"] == 0: continue
    pairs.setdefault((r["rep"], r["n"]), {})[r["chain"]] = r["T"]
per = []
for k in sorted(pairs):
    d = pairs[k]
    if 0 in d and 1 in d:
        e = (d[1]-d[0])*1000.0/k[1]
        per.append(e)
        print("paired rep=%d n=%5d  chained-unchained = %+.4f ms  (%+.4f us/disp)"
              % (k[0], k[1], d[1]-d[0], e))
if len(per) > 1:
    m = sum(per)/len(per)
    sd = math.sqrt(sum((e-m)**2 for e in per)/(len(per)-1))
    se = sd/math.sqrt(len(per))
    print("PAIRED EXCESS  mean=%+.4f  sd=%.4f  se=%.4f us/dispatch  (npairs=%d, %.2f sigma from 0)"
          % (m, sd, se, len(per), abs(m)/se if se else float("inf")))
    if 1 in fit and fit[1]["slope"]:
        print("  as a fraction of the chained slope (%.4f us/disp): %.2f%%"
              % (fit[1]["slope"]*1000.0, 100.0*m/(fit[1]["slope"]*1000.0)))
