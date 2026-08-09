#!/usr/bin/env python3
"""R102-B section 10: record probability on the statistic the leaderboard actually ranks.

Key correction: 2.61650354381456 is a `score` (same-session paired), not a `cs`
(pinned-calibration). Comparing our cs to it is a category error.

Decomposition used here:
    score = cs * L      where  L = (bl_dec/MB_D)^0.75 * (bl_pre/MB_P)^0.25
`cs` is the candidate-only quality term (pinned MB_D/MB_P constants); `L` is the
same-session baseline draw -- the "baseline lottery".  L is measured empirically
per receipt, so no distributional assumption is needed.
"""
import json
import math
import statistics as st

RECORD = 2.61650354381456
OUR_SCORE = 2.58189090485267
OUR_CS = 2.582286297407117
OUR_COMMIT = "bd33883e"

rows = json.load(open("/tmp/r102b-receipts.json"))
if isinstance(rows, dict):
    for k in ("receipts", "items", "rows", "data"):
        if k in rows:
            rows = rows[k]
            break


def g(r, *names):
    for n in names:
        if n in r and r[n] is not None:
            return r[n]
    return None


recs = []
for r in rows:
    s = g(r, "score")
    c = g(r, "cs", "calibrated_score")
    if s is None or c is None or s <= 0 or c <= 0:
        continue
    recs.append(
        dict(
            sha=(g(r, "commit", "commit_sha", "sha") or "")[:8],
            solver=g(r, "solver", "model", "submitter"),
            ts=g(r, "created_at", "ts", "timestamp"),
            score=float(s),
            cs=float(c),
            L=float(s) / float(c),
        )
    )

print(f"receipts with both score and cs: n = {len(recs)}")

by_score = max(recs, key=lambda r: r["score"])
by_cs = max(recs, key=lambda r: r["cs"])
print(f"\ncorpus max by SCORE : {by_score['score']:.14f}  cs={by_score['cs']:.6f}  "
      f"sha={by_score['sha']}  solver={by_score['solver']}  ts={by_score['ts']}")
print(f"corpus max by CS    : cs={by_cs['cs']:.14f}  score={by_cs['score']:.6f}  "
      f"sha={by_cs['sha']}  solver={by_cs['solver']}  ts={by_cs['ts']}")
print(f"\nRECORD constant     : {RECORD:.14f}")
print(f"  matches max-by-score exactly: {abs(by_score['score'] - RECORD) < 1e-12}")
print(f"  matches max-by-cs          : {abs(by_cs['cs'] - RECORD) < 1e-12}")

print("\n--- the record holder's own decomposition ---")
print(f"  score = {by_score['score']:.6f}")
print(f"  cs    = {by_score['cs']:.6f}   <- candidate quality")
print(f"  L     = {by_score['L']:.6f}   ({(by_score['L']-1)*100:+.4f} % baseline draw)")

print("\n--- our receipt (%s) ---" % OUR_COMMIT)
our_L = OUR_SCORE / OUR_CS
print(f"  score = {OUR_SCORE:.6f}")
print(f"  cs    = {OUR_CS:.6f}   <- candidate quality")
print(f"  L     = {our_L:.6f}   ({(our_L-1)*100:+.4f} % baseline draw)")
print(f"\n  our cs vs record-holder cs : {(OUR_CS/by_score['cs']-1)*100:+.4f} %  "
      f"(we are {'AHEAD' if OUR_CS > by_score['cs'] else 'BEHIND'} on candidate quality)")
print(f"  our score vs record        : {(OUR_SCORE/RECORD-1)*100:+.4f} %")

# ---- empirical distribution of the baseline lottery L -------------------
Ls = sorted(r["L"] for r in recs)
n = len(Ls)


def q(p):
    i = p * (n - 1)
    lo, hi = int(math.floor(i)), int(math.ceil(i))
    return Ls[lo] + (Ls[hi] - Ls[lo]) * (i - lo)


lnL = [math.log(x) for x in Ls]
print("\n--- empirical baseline-lottery multiplier L = score/cs (n=%d) ---" % n)
print(f"  mean   {st.mean(Ls):.6f}   median {st.median(Ls):.6f}")
print(f"  sd(lnL) {st.pstdev(lnL)*100:.4f} %   "
      f"MAD-sd(lnL) {st.median([abs(x-st.median(lnL)) for x in lnL])/0.6745*100:.4f} %")
for p in (0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1.0):
    print(f"  p{p*100:5.1f}  {q(min(p,1.0)):.6f}  ({(q(min(p,1.0))-1)*100:+.3f} %)")

# ---- P(beat record) for a candidate of our measured quality ------------
need = RECORD / OUR_CS
k = sum(1 for x in Ls if x >= need)
p_emp = k / n
print("\n--- P(one official receipt of OUR candidate beats the record) ---")
print(f"  need L >= {need:.6f}  ({(need-1)*100:+.4f} %)")
print(f"  empirical: {k}/{n} draws qualify  ->  p = {p_emp:.5f}  (1 in {1/p_emp:.0f})"
      if k else f"  empirical: 0/{n} draws qualify -> p < {1/n:.5f}")

mu, sd = st.mean(lnL), st.pstdev(lnL)
z = (math.log(need) - mu) / sd
p_norm = 0.5 * math.erfc(z / math.sqrt(2))
print(f"  lognormal fit: z = {z:.4f}  ->  p = {p_norm:.5f}  (1 in {1/p_norm:.0f})")
for target in (0.5, 0.9):
    for p_, tag in ((p_emp, "empirical"), (p_norm, "lognormal")):
        if p_ > 0:
            nn = math.log(1 - target) / math.log(1 - p_)
            print(f"  receipts for {target*100:.0f}% chance of >=1 record ({tag}): {nn:.1f}")

# ---- how much candidate quality would make it a coin flip? -------------
med_L = st.median(Ls)
cs_needed_median = RECORD / med_L
print("\n--- candidate quality required ---")
print(f"  cs to beat record at the MEDIAN draw   : {cs_needed_median:.6f} "
      f"({(cs_needed_median/OUR_CS-1)*100:+.4f} % over ours)")
for p in (0.75, 0.90):
    csn = RECORD / q(1 - p)
    print(f"  cs to beat record with prob {p*100:.0f}%        : {csn:.6f} "
          f"({(csn/OUR_CS-1)*100:+.4f} % over ours)")
print(f"  corpus max cs ({by_cs['sha']}) would need L >= {RECORD/by_cs['cs']:.6f} "
      f"-> p = {sum(1 for x in Ls if x >= RECORD/by_cs['cs'])/n:.4f}")

# ---- is L independent of cs? (it should be: different measurement legs) --
xs = [math.log(r["cs"]) for r in recs]
ys = [math.log(r["L"]) for r in recs]
mx, my = st.mean(xs), st.mean(ys)
sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
sxx = sum((a - mx) ** 2 for a in xs)
syy = sum((b - my) ** 2 for b in ys)
rho = sxy / math.sqrt(sxx * syy)
tstat = rho * math.sqrt((n - 2) / max(1e-18, 1 - rho * rho))
print(f"\n--- independence check: corr(ln cs, ln L) = {rho:+.4f}  t = {tstat:+.2f} "
      f"({'consistent with independence' if abs(tstat) < 2 else 'DEPENDENT'})")

# ---- where do we rank on each statistic? -------------------------------
rs = sorted(recs, key=lambda r: -r["score"])
rc = sorted(recs, key=lambda r: -r["cs"])
pos_s = 1 + next(i for i, r in enumerate(rs) if r["score"] <= OUR_SCORE)
pos_c = 1 + next(i for i, r in enumerate(rc) if r["cs"] <= OUR_CS)
print(f"\n--- our rank ---\n  by score: {pos_s}/{n}\n  by cs   : {pos_c}/{n}")
