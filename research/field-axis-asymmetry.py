#!/usr/bin/env python3
"""Has anyone in the public field actually moved prefill?

Pulls every public receipt for the benchmark from the mlxfast API, decomposes
each one onto the renormalised axes, and asks a single question: how many
receipts beat our own unchanged tree on S (prefill) and on T (decode), measured
in units of the instrument's own noise?

The control is the three byte-identical receipts of our base (f8502e12,
71586bcf, f3cda678), which cost nothing because the service dedupes identical
archives. Their spread IS the instrument's 1-sigma, so it is the correct ruler
for both axes.

    S  = 512000 * prefill_seconds_per_token      (ms, 512-token seed forward)
    T  = 1000*decode_seconds_per_token - S/128   (ms, steady one-token step)
    ns = (0.013890/D)**0.75 * (0.0003845/P)**0.25

Reads MLXFAST_API_TOKEN from the environment; never prints it.

    python3 research/field-axis-asymmetry.py
"""
import collections
import json
import os
import statistics as st
import sys
import urllib.parse
import urllib.request

DEC_REF = 0.013890
PRE_REF = 0.0003845
CONTROL = ["f8502e12", "71586bcf", "f3cda678"]


def fetch():
    base = os.environ.get("MLXFAST_API_URL", "https://api.mlx.fast").rstrip("/")
    ref = os.environ.get("MLXFAST_BENCHMARK_REF", "eigenlabs/mlxfast-challenge")
    tok = os.environ.get("MLXFAST_API_TOKEN")
    if not tok:
        sys.exit("MLXFAST_API_TOKEN not set")
    url = "%s/api/benchmarks/%s/submissions" % (
        base, urllib.parse.quote(ref, safe=""))
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + tok)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        doc = json.loads(r.read().decode())
    if isinstance(doc, dict):
        for k in ("submissions", "items", "data", "results"):
            if isinstance(doc.get(k), list):
                return doc[k]
    return doc


def axes(m):
    d = float(m["decode_seconds_per_token"])
    p = float(m["prefill_seconds_per_token"])
    s = 512000.0 * p
    t = 1000.0 * d - s / 128.0
    ns = (DEC_REF / d) ** 0.75 * (PRE_REF / p) ** 0.25
    return s, t, ns


def main():
    rows, ctl = [], {}
    partition = collections.Counter()
    for r in fetch():
        m = r.get("officialMetrics") or {}
        have = bool(m.get("decode_seconds_per_token")) and \
            bool(m.get("prefill_seconds_per_token"))
        partition[(r.get("status"), have)] += 1
        if not have:
            continue
        sid = str(r["id"])[:8]
        s, t, ns = axes(m)
        rows.append((sid, s, t, ns))
        if sid in CONTROL:
            ctl[sid] = (s, t)

    print("status partition (metrics present?):")
    for (status, have), c in sorted(partition.items(), key=lambda x: str(x[0])):
        print("  %-12s %5d  %s" % (status, c, "yes" if have else "no"))
    print("  -> 'rejected' is the ranking band, not correctness: those runs")
    print("     cleared every gate and were timed. 'failed' carries no metrics.")
    print()

    missing = [c for c in CONTROL if c not in ctl]
    if missing:
        sys.exit("control receipts absent from response: %s" % missing)

    cS = [ctl[c][0] for c in CONTROL]
    cT = [ctl[c][1] for c in CONTROL]
    mS, sdS = st.mean(cS), st.stdev(cS)
    mT, sdT = st.mean(cT), st.stdev(cT)
    n = len(rows)

    print("byte-identical control (n=3):")
    print("  S %.3f +- %.3f ms (%.3f%%)   T %.4f +- %.4f ms (%.3f%%)"
          % (mS, sdS, 100 * sdS / mS, mT, sdT, 100 * sdT / mT))
    print("public receipts with metrics: %d\n" % n)

    for axis, idx, mu, sd in (("S (prefill)", 1, mS, sdS),
                              ("T (decode)", 2, mT, sdT)):
        vals = [r[idx] for r in rows]
        print("%s -- receipts beating our unchanged tree:" % axis)
        for k in (1, 2, 3, 5, 10):
            c = sum(1 for v in vals if v < mu - k * sd)
            print("  < mean - %2d sigma (%9.4f):  %4d / %d  (%5.2f%%)"
                  % (k, mu - k * sd, c, n, 100 * c / n))
        print("  best public value %.4f = %.2f sigma better\n"
              % (min(vals), (mu - min(vals)) / sd))

    # Frontier-restricted spread: are the top receipts distinguishable at all?
    rows.sort(key=lambda r: -r[3])
    print("frontier spread vs control sigma (top-K by ns):")
    print("  %-6s %9s %8s %9s %8s" % ("K", "S sigma", "S/ctl", "T sigma",
                                      "T/ctl"))
    for k in (10, 20, 50, 100, 200, n):
        if k > n:
            continue
        S = [r[1] for r in rows[:k]]
        T = [r[2] for r in rows[:k]]
        sS = st.stdev(S) / st.mean(S) * 100
        sT = st.stdev(T) / st.mean(T) * 100
        print("  %-6d %8.3f%% %7.2fx %8.3f%% %7.2fx"
              % (k, sS, sS / (100 * sdS / mS), sT, sT / (100 * sdT / mT)))

    bs = min(rows, key=lambda r: r[1])
    bt = min(rows, key=lambda r: r[2])
    print("\nbest-S receipt %s: S %.3f  T %.4f  ns %.5f" % (bs[0], bs[1], bs[2],
                                                            bs[3]))
    print("best-T receipt %s: S %.3f  T %.4f  ns %.5f" % (bt[0], bt[1], bt[2],
                                                          bt[3]))


if __name__ == "__main__":
    main()
