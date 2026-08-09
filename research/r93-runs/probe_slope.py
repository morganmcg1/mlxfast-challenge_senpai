#!/usr/bin/env python3
"""Arm C read-out: price one injected fused-multiply-add on the official M5.

Two estimators, deliberately kept separate because they carry different
assumptions:

  (1) vs the n=5 null mean. Uses every null replicate, so it has the tightest
      standard error, but the nulls are built from a *probe-off* source while
      the probe candidates bind a 128 MiB pool and select a renamed pipeline.
      Section 10.4 measured that placement term at -0.88 % on M4 with a sign we
      cannot explain, so this estimator is confounded by it.

  (2) between two probe rungs. Both candidates select the same pipeline object
      shape and the same pool binding and differ only in the loop trip count,
      so the placement term cancels by construction. Only two receipts, so the
      standard error is the null sigma scaled by sqrt(2), but it is the clean
      estimator and it is what section 10.7 pre-registered.

Usage: python3 probe_slope.py            (reads receipts/probe-*.json + nulls)
"""
import glob
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REC = os.path.join(HERE, "receipts")

# two-sided t at 0.05
T = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365}


def metrics(path):
    s = json.load(open(path))["submission"]
    m = s.get("officialMetrics")
    if not m:
        return None
    return {
        "status": s.get("status"),
        "commit": s.get("submissionCommitSha"),
        "dec": m["decode_seconds_per_token"] * 1e6,
        "pre": m["prefill_seconds_per_token"] * 1e6,
        "bl_dec": m["baseline_decode_seconds_per_token"] * 1e6,
        "bl_pre": m["baseline_prefill_seconds_per_token"] * 1e6,
        "raw": m,
    }


def sd(xs):
    n = len(xs)
    mu = sum(xs) / n
    return math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1)), mu


nulls = []
for f in sorted(glob.glob(os.path.join(REC, "null-*.json"))):
    m = metrics(f)
    if m:
        nulls.append(m)
if len(nulls) < 3:
    sys.exit("FATAL: need >= 3 null receipts, found %d" % len(nulls))

probes = {}
for f in sorted(glob.glob(os.path.join(REC, "probe-*.json"))):
    mo = re.search(r"probe-(\w+)-(\w+)-(\d+)\.json$", os.path.basename(f))
    m = metrics(f)
    if mo and m:
        probes[int(mo.group(3))] = (mo.group(1), mo.group(2), m)
if not probes:
    sys.exit("FATAL: no probe receipt with officialMetrics under %s" % REC)

s_dec, mu_dec = sd([x["dec"] for x in nulls])
s_pre, mu_pre = sd([x["pre"] for x in nulls])
nn = len(nulls)
cv = 100.0 * s_dec / mu_dec

print("=" * 78)
print("NULL REFERENCE (n=%d, machine-code-identical)" % nn)
print("=" * 78)
print("  decode  mean %10.4f us   sd %7.4f   CV %.4f%%" % (mu_dec, s_dec, cv))
print("  prefill mean %10.4f us   sd %7.4f   CV %.4f%%"
      % (mu_pre, s_pre, 100.0 * s_pre / mu_pre))
print()

print("=" * 78)
print("PROBE RECEIPTS")
print("=" * 78)
print("  %-6s %-14s %10s %10s %10s %10s  %s"
      % ("n", "spec", "decode", "prefill", "bl_dec", "bl_pre", "status"))
for n in sorted(probes):
    tgt, kind, m = probes[n]
    print("  %-6d %-14s %10.4f %10.4f %10.4f %10.4f  %s"
          % (n, "%s:%s:%d" % (tgt, kind, n), m["dec"], m["pre"],
             m["bl_dec"], m["bl_pre"], m["status"]))
print()

print("=" * 78)
print("ESTIMATOR 1: each rung vs the null mean  (CONFOUNDED by placement)")
print("=" * 78)
df = nn - 1
tcrit = T[df]
se1 = s_dec * math.sqrt(1.0 + 1.0 / nn)
for n in sorted(probes):
    tgt, kind, m = probes[n]
    d = m["dec"] - mu_dec
    t = d / se1
    lo, hi = d - tcrit * se1, d + tcrit * se1
    dp = m["pre"] - mu_pre
    print("  n=%-4d  delta %+9.3f us  = %+7.4f %%   t=%+6.3f on %d df (crit %.3f)"
          % (n, d, 100.0 * d / mu_dec, t, df, tcrit))
    print("          95%% CI [%+9.3f, %+9.3f] us = [%+7.4f %%, %+7.4f %%]"
          % (lo, hi, 100.0 * lo / mu_dec, 100.0 * hi / mu_dec))
    print("          per injected op %+8.4f us   |  prefill control %+7.4f %%"
          % (d / n if n else float("nan"), 100.0 * dp / mu_pre))
print()

print("=" * 78)
print("ESTIMATOR 2: rung-to-rung slope  (PLACEMENT-FREE by construction)")
print("=" * 78)
ns = sorted(probes)
if len(ns) < 2:
    print("  only one rung so far; needs a second probe receipt")
else:
    for i in range(len(ns) - 1):
        for j in range(i + 1, len(ns)):
            a, b = ns[i], ns[j]
            da = probes[a][2]["dec"]
            db = probes[b][2]["dec"]
            d = db - da
            dn = b - a
            # each rung is a single receipt, so Var(difference) = 2 sigma^2
            se = s_dec * math.sqrt(2.0)
            t = d / se
            lo, hi = d - tcrit * se, d + tcrit * se
            print("  n=%d -> n=%d  (%d ops)" % (a, b, dn))
            print("     delta %+9.3f us = %+7.4f %% of the n=%d step"
                  % (d, 100.0 * d / da, a))
            print("     t=%+6.3f on %d df (crit %.3f, se %.3f us)"
                  % (t, df, tcrit, se))
            print("     95%% CI on delta   [%+9.3f, %+9.3f] us" % (lo, hi))
            print("     slope             %+8.4f us/op   95%% CI [%+8.4f, %+8.4f]"
                  % (d / dn, lo / dn, hi / dn))
            print("     prefill control   %+7.4f %%"
                  % (100.0 * (probes[b][2]["pre"] - probes[a][2]["pre"])
                     / probes[a][2]["pre"]))
print()

if 0 in probes:
    print("=" * 78)
    print("C0' PLACEMENT CONTROL (section 10.9)")
    print("=" * 78)
    y0 = probes[0][2]["dec"]
    d0 = y0 - mu_dec
    print("  probe n=0 is name- and residency-matched to the loaded rungs but")
    print("  executes zero injected ops, so (n=0 minus null) IS the placement term.")
    print("  measured placement %+8.3f us = %+7.4f %%  (t=%+.3f, ns at 4 df)"
          % (d0, 100.0 * d0 / mu_dec, d0 / se1))
    # the two competing readings pre-registered in section 10.8
    if 24 in probes and 64 in probes:
        y24, y64 = probes[24][2]["dec"], probes[64][2]["dec"]
        slope_hi = (y64 - y24) / 40.0
        predB = y64 - 64.0 * slope_hi          # linear through both loaded rungs
        predA = mu_dec                          # knee: placement is nil
        print("  reading (A) knee      predicted %9.3f us  ->  miss %+8.3f us"
              % (predA, y0 - predA))
        print("  reading (B) placement predicted %9.3f us  ->  miss %+8.3f us"
              % (predB, y0 - predB))
        print("  |miss| in units of the single-receipt se (%.3f us): A %.2f, B %.2f"
              % (se1, abs(y0 - predA) / se1, abs(y0 - predB) / se1))
        print("  verdict: %s"
              % ("(A) KNEE - placement is nil, the low segment is genuinely cheap"
                 if abs(y0 - predA) < abs(y0 - predB)
                 else "(B) PLACEMENT - the response is linear from n=0"))
        print()
        # convexity: slope(24->64) - slope(0->24), sharing the n=24 receipt
        s_lo = (y24 - y0) / 24.0
        var = s_dec ** 2 * (2.0 / 40.0 ** 2 + 2.0 / 24.0 ** 2
                            + 2.0 / (24.0 * 40.0))
        se_c = math.sqrt(var)
        dc = slope_hi - s_lo
        print("  CONVEXITY  slope(24->64) - slope(0->24) = %+8.4f us/op" % dc)
        print("             se %.4f (shares the n=24 receipt), t=%+.3f on %d df"
              % (se_c, dc / se_c, df))
        print("             95%% CI [%+8.4f, %+8.4f] us/op"
              % (dc - tcrit * se_c, dc + tcrit * se_c))
        print("             ratio high/low = %.2f x" % (slope_hi / s_lo))
    print()

print("=" * 78)
print("PRE-REGISTERED READ-OUT (section 10.7)")
print("=" * 78)
if len(ns) >= 2 and 24 in probes and 64 in probes:
    d = probes[64][2]["dec"] - probes[24][2]["dec"]
    pct = 100.0 * d / probes[24][2]["dec"]
    print("  observed n=24 -> n=64 shift: %+.4f %% (%+.3f us)" % (pct, d))
    if pct >= 4.5:
        v = "M4 PRICE AFTER ALL (~+6.7 %% expected) -> re-cost byte-for-ALU trades"
    elif pct >= 0.9:
        v = "LIVE AND LINEAR (~+1.8 %% expected) -> M5 price ~1.4 us/fma, absorbed"
    elif pct >= -0.9:
        v = "PROBE INERT on M5 -> section 10.5 must be withdrawn"
    else:
        v = "NEGATIVE and outside noise -> instrument defect, do not interpret"
    print("  verdict: %s" % v)
else:
    print("  needs both the n=24 and n=64 receipts")
