#!/usr/bin/env python3
"""Is the ranked-M5 receipt channel a usable INSTRUMENT for +0.5 % levers?

Round 103 concluded "the receipt channel cannot settle this at any affordable
cost".  That verdict was formed against a 20 us/step decode contrast (0.31 % of
score).  Round 103 also established that only a GLOBAL RECORD scores, so the
only levers worth building are >= +0.5 %.  Those are much bigger targets, and
the power question must be re-asked at that size.

Part 1: trimmed within-identical-code sd for BOTH channels, and the number of
        receipt pairs needed to resolve a +0.5 % and a +1.0 % lever.
Part 2: is there a platform-imposed receipt quota?  (max/day/solver, minimum
        inter-arrival, evidence of throttling).  If not, the 6-receipts/student
        cap is advisor-imposed and is the binding constraint on measuring the
        M5-specific effects where every remaining big lever lives.
"""
import json
import math
import os
import datetime as dt
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "artifacts", "advisor-r103")
CORPUS = json.load(open(os.path.join(ART, "receipt-corpus-frozen.json")))
SIGMA = json.load(open(os.path.join(ART, "replicate-sigma.json")))
PROV = json.load(open(os.path.join(ART, "our-receipts-provenance.json")))
digest_of = SIGMA["digests"]

PCT_PER_MS_PREFILL = 0.3781
PCT_PER_US_DECODE = 0.015228
# group excluded in r103 as a verified outlier (sd(ln cs) = 2.24 %)
OUTLIER = "7cbffc2c17d7"


def sd(xs):
    n = len(xs)
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


groups = defaultdict(list)
for r in PROV:
    d = digest_of.get(r.get("sub_sha") or "")
    if not d or r.get("D") is None or r.get("P") is None:
        continue
    groups[d].append({"D": r["D"], "P": r["P"], "T": r["D"] - 4.0 * r["P"]})
groups = {k: v for k, v in groups.items() if len(v) >= 2 and not k.startswith(OUTLIER)}

ssT = ssP = dof = 0
for rows in groups.values():
    Ts = [r["T"] for r in rows]; Ps = [r["P"] for r in rows]
    mT = sum(Ts)/len(Ts); mP = sum(Ps)/len(Ps)
    ssT += sum((t-mT)**2 for t in Ts); ssP += sum((p-mP)**2 for p in Ps)
    dof += len(rows) - 1
sdT = math.sqrt(ssT/dof)
sdP = math.sqrt(ssP/dof)
sdP_ms = sdP * 512.0 / 1000.0

print("=" * 74)
print(f"PART 1  trimmed identical-code noise ({len(groups)} groups, dof {dof})")
print("=" * 74)
print(f"  sd(T) = {sdT:7.3f} us/step   -> {sdT*PCT_PER_US_DECODE:.4f} % of score")
print(f"  sd(P) = {sdP:7.4f} us/tok = {sdP_ms:.4f} ms wall"
      f" -> {sdP_ms*PCT_PER_MS_PREFILL:.4f} % of score")

dT = sdT * math.sqrt(2.0)
dP = sdP_ms * math.sqrt(2.0)
print(f"\n  sigma of a 1-vs-1 receipt difference, in SCORE %:")
print(f"    decode  {dT*PCT_PER_US_DECODE:.4f} %      prefill {dP*PCT_PER_MS_PREFILL:.4f} %")
print(f"    -> prefill is {(dT*PCT_PER_US_DECODE)/(dP*PCT_PER_MS_PREFILL):.2f}x "
      f"the more precise channel per unit of score")

print(f"\n  {'lever':22s} {'decode z':>9s} {'n pairs 80%':>12s} "
      f"{'prefill z':>10s} {'n pairs 80%':>12s}")
for pct in (0.25, 0.50, 0.75, 1.00, 1.50):
    us = pct * 65.67
    ms = pct / PCT_PER_MS_PREFILL
    zd = us / dT
    zp = ms / dP
    # pairs for 80 % power at alpha=0.05 two-sided: (1.96+0.84)^2 / z^2
    nd = (2.80 / zd) ** 2
    npf = (2.80 / zp) ** 2
    print(f"  +{pct:.2f} % of score      {zd:9.2f} {nd:12.1f} {zp:10.2f} {npf:12.1f}")

print("\n" + "=" * 74)
print("PART 2  is there a PLATFORM receipt quota?")
print("=" * 74)


def parse(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


by_solver_day = defaultdict(int)
by_solver = defaultdict(list)
for r in CORPUS:
    s = r.get("solver")
    ts = r.get("ts")
    if not s or not ts:
        continue
    t = parse(ts)
    by_solver_day[(s, t.date())] += 1
    by_solver[s].append(t)

top = sorted(by_solver_day.items(), key=lambda kv: -kv[1])[:10]
print("\n  busiest solver-days (receipts submitted in one UTC day):")
for (s, d), n in top:
    print(f"    {str(d)}  {s:20s} {n:4d}")

print("\n  tightest inter-arrival gaps per solver (min / 5th pct), n>=20:")
print(f"    {'solver':22s} {'n':>4s} {'min gap s':>10s} {'p05 gap s':>10s} {'median s':>9s}")
for s, ts in sorted(by_solver.items(), key=lambda kv: -len(kv[1])):
    if len(ts) < 20:
        continue
    ts = sorted(ts)
    gaps = sorted((ts[i+1]-ts[i]).total_seconds() for i in range(len(ts)-1))
    p05 = gaps[max(0, int(0.05*len(gaps))-1)]
    med = gaps[len(gaps)//2]
    print(f"    {s:22s} {len(ts):4d} {gaps[0]:10.0f} {p05:10.0f} {med:9.0f}")

# global busiest hour
by_hour = defaultdict(int)
for r in CORPUS:
    if r.get("ts"):
        t = parse(r["ts"])
        by_hour[(r.get("solver"), t.replace(minute=0, second=0, microsecond=0))] += 1
mx = sorted(by_hour.items(), key=lambda kv: -kv[1])[:5]
print("\n  busiest solver-hours:")
for (s, h), n in mx:
    print(f"    {h.isoformat()}  {s:20s} {n:3d} receipts in one hour")

status = defaultdict(int)
for r in CORPUS:
    status[r.get("status")] += 1
print(f"\n  status counts across corpus: {dict(status)}")
print("  (rejected receipts DO carry full cand_dec / cand_pre metrics)")
