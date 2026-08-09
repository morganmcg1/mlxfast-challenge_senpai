#!/usr/bin/env python3
"""Robustness of the baseline-arm noise estimate: SD vs MAD-sigma vs IQR."""
import json
import math
import statistics as st
import sys

rows = sorted([r for r in json.load(open(sys.argv[1])) if r.get("cs")],
              key=lambda r: r["ts"])


def summarize(vals, tag):
    m = st.median(vals)
    sd = st.stdev(vals)
    mad = st.median([abs(v - m) for v in vals])
    sig_mad = 1.4826 * mad
    q = sorted(vals)
    lo, hi = q[len(q) // 4], q[3 * len(q) // 4]
    sig_iqr = (hi - lo) / 1.349
    print(f"  {tag:28s} n={len(vals):4d}  sd {100*sd:.4f} %   "
          f"MAD-sigma {100*sig_mad:.4f} %   IQR-sigma {100*sig_iqr:.4f} %   "
          f"min {100*(min(vals)-m):+.2f} %  max {100*(max(vals)-m):+.2f} %")
    return sig_mad


print("[baseline-arm log-time scatter; the baseline is byte-identical code "
      "in every session]")
for tag, key in (("ln bl_dec  full corpus", "bl_dec"), ("ln bl_pre  full corpus", "bl_pre")):
    summarize([math.log(r[key]) for r in rows], tag)
for tag, key in (("ln bl_dec  last 150", "bl_dec"), ("ln bl_pre  last 150", "bl_pre")):
    summarize([math.log(r[key]) for r in rows[-150:]], tag)

print("\n[implied sigma of cs in cs-percent units, MAD-based, last 150]")
sd = 1.4826 * st.median([abs(x - st.median([math.log(r['bl_dec']) for r in rows[-150:]]))
                         for x in [math.log(r['bl_dec']) for r in rows[-150:]]])
sp = 1.4826 * st.median([abs(x - st.median([math.log(r['bl_pre']) for r in rows[-150:]]))
                         for x in [math.log(r['bl_pre']) for r in rows[-150:]]])
d, p = 100 * 0.75 * sd, 100 * 0.25 * sp
print(f"  decode leg {d:.4f} %   prefill leg {p:.4f} %   total {math.hypot(d,p):.4f} %")
print(f"  prefill share of variance {100*p*p/(d*d+p*p):.1f} %")
print("\n[decode-leg sigma by calendar day, last 10 days with n>=8]")
days = {}
for r in rows:
    days.setdefault(r["ts"][:10], []).append(r)
for dkey in sorted(days)[-12:]:
    g = days[dkey]
    if len(g) < 8:
        continue
    v = [math.log(x["bl_dec"]) for x in g]
    w = [math.log(x["bl_pre"]) for x in g]
    print(f"  {dkey}  n={len(g):3d}  decode leg {100*0.75*st.stdev(v):.4f} %   "
          f"prefill leg {100*0.25*st.stdev(w):.4f} %")
