#!/usr/bin/env python3
"""Within-identical-code dispersion of SCORE (not cs), and corr(ln cs, ln L).

score = cs * L.  Planning "how many draws to the record?" needs sd(ln score)
for a FIXED tree, and that is NOT sqrt(sd(ln cs)^2 + sd(ln L)^2) unless the two
channels are independent.  The verified identical-code replicate groups (our own
139 fetched submission commits, grouped by sha256 of the Sources/ tree) let us
measure it directly instead of assuming.

Inputs (all committed under research/artifacts/advisor-r103/):
  receipt-corpus-frozen.json   list of 1205 receipts: id, solver, ts, cs, L, score, ...
  replicate-sigma.json         .digests : {submission_commit_sha -> sources_tree_digest}
  our-receipts-provenance.json list of 142: id8, sub_sha, cs, D, P, ts, status
"""
import json
import math
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "artifacts", "advisor-r103")
CORPUS = json.load(open(os.path.join(ART, "receipt-corpus-frozen.json")))
SIGMA = json.load(open(os.path.join(ART, "replicate-sigma.json")))
PROV = json.load(open(os.path.join(ART, "our-receipts-provenance.json")))

RECORD = 2.61650354381456

by_id = {r["id"][:8]: r for r in CORPUS}
digest_of = SIGMA["digests"]


def stats(xs):
    n = len(xs)
    m = sum(xs) / n
    s = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    return m, s, n


# ---- build identical-code groups over OUR receipts -------------------------
groups = defaultdict(list)
missing_digest, missing_corpus = 0, 0
for p in PROV:
    sha = p.get("sub_sha") or ""
    dg = digest_of.get(sha)
    if not dg:
        missing_digest += 1
        continue
    r = by_id.get(p["id8"])
    if r is None or r.get("L") is None or r.get("score") is None:
        missing_corpus += 1
        continue
    groups[dg].append(r)

print(f"our receipts: {len(PROV)}   no tree digest: {missing_digest}   "
      f"not joinable to corpus: {missing_corpus}")
usable = {k: v for k, v in groups.items() if len(v) >= 2}
print(f"identical-code groups with n>=2: {len(usable)}  "
      f"(receipts {sum(len(v) for v in usable.values())})")

print("\n  digest        n   sd(ln cs)%  sd(ln L)%  sd(ln score)%  corr(cs,L)")
tot = {"cs": [0.0, 0], "L": [0.0, 0], "sc": [0.0, 0]}
cov_num, cov_den = 0.0, 0
trimmed = {"cs": [0.0, 0], "L": [0.0, 0], "sc": [0.0, 0]}
tcov_num, tcov_den = 0.0, 0
for dg, rows in sorted(usable.items(), key=lambda kv: -len(kv[1])):
    lcs = [math.log(r["cs"]) for r in rows]
    lL = [math.log(r["L"]) for r in rows]
    lsc = [math.log(r["score"]) for r in rows]
    mcs, scs, n = stats(lcs)
    mL, sL, _ = stats(lL)
    msc, ssc, _ = stats(lsc)
    c = sum((a - mcs) * (b - mL) for a, b in zip(lcs, lL))
    r_ = c / ((n - 1) * scs * sL) if scs > 0 and sL > 0 else float("nan")
    print(f"  {dg[:12]} {n:3d}   {100*scs:8.4f}   {100*sL:8.4f}   "
          f"{100*ssc:10.4f}   {r_:9.3f}")
    for key, s in (("cs", scs), ("L", sL), ("sc", ssc)):
        tot[key][0] += (n - 1) * s ** 2
        tot[key][1] += n - 1
    cov_num += c
    cov_den += n - 1
    if scs < 0.01:   # same 1% trim used for the sigma table (drops pre-rebase mixtures)
        for key, s in (("cs", scs), ("L", sL), ("sc", ssc)):
            trimmed[key][0] += (n - 1) * s ** 2
            trimmed[key][1] += n - 1
        tcov_num += c
        tcov_den += n - 1


def report(tag, tt, cn, cd):
    pcs = math.sqrt(tt["cs"][0] / tt["cs"][1])
    pL = math.sqrt(tt["L"][0] / tt["L"][1])
    psc = math.sqrt(tt["sc"][0] / tt["sc"][1])
    pr = (cn / cd) / (pcs * pL)
    indep = math.sqrt(pcs ** 2 + pL ** 2)
    print(f"\n  {tag} (dof={tt['sc'][1]}):")
    print(f"    sd(ln cs)    = {100*pcs:.4f}%")
    print(f"    sd(ln L)     = {100*pL:.4f}%")
    print(f"    sd(ln score) = {100*psc:.4f}%   "
          f"[independence would predict {100*indep:.4f}%]")
    print(f"    pooled corr(ln cs, ln L) = {pr:+.4f}")
    return pcs, pL, psc, pr


ALL = report("POOLED, all groups", tot, cov_num, cov_den)
TRIM = report("POOLED, trimmed (sd(ln cs) < 1%)", trimmed, tcov_num, tcov_den)

# ---- re-price the draw lottery with the MEASURED score dispersion ----------
print("\n=== p(record) per draw, measured vs assumed-independent ===")
Ls = sorted(r["L"] for r in CORPUS if r.get("L"))
medL = Ls[len(Ls) // 2]
print(f"  median corpus L = {medL:.6f}   (n={len(Ls)})")


def p_rec(mu_score, sd):
    z = (math.log(RECORD) - math.log(mu_score)) / sd
    return 0.5 * math.erfc(z / math.sqrt(2))


sd_meas = TRIM[2]
sd_indep = math.sqrt(TRIM[0] ** 2 + TRIM[1] ** 2)
print(f"\n  sd used: measured sd(ln score) = {100*sd_meas:.4f}%, "
      f"independence prediction = {100*sd_indep:.4f}%")
print("\n  tree cs                                 mu_score   "
      "p/draw meas  p/draw indep  draws-50% meas")
for label, mu_cs in (("honest mean r93-null quintuplet 2.583111", 2.583111),
                     ("  95% CI low                  2.577962", 2.577962),
                     ("  95% CI high                 2.588271", 2.588271),
                     ("Arm R                         2.589321", 2.589321),
                     ("frontier                      2.582286", 2.582286),
                     ("control                       2.575633", 2.575633)):
    mu_score = mu_cs * medL
    pm = p_rec(mu_score, sd_meas)
    pi = p_rec(mu_score, sd_indep)
    d50 = math.log(0.5) / math.log(1 - pm) if 0 < pm < 1 else float("inf")
    print(f"  {label:40s} {mu_score:.6f}   {100*pm:8.3f}%   "
          f"{100*pi:8.3f}%   {d50:8.0f}")

print("\n  marginal value of REAL work, from the honest mean, measured sd:")
base = p_rec(2.583111 * medL, sd_meas)
d50b = math.log(0.5) / math.log(1 - base)
for d in (0.001, 0.002, 0.003, 0.005, 0.010):
    p = p_rec(2.583111 * math.exp(d) * medL, sd_meas)
    d50n = math.log(0.5) / math.log(1 - p)
    print(f"    +{100*d:.1f}% cs -> p/draw {100*p:6.3f}%  (x{p/base:5.2f})   "
          f"draws-50% {d50b:5.0f} -> {d50n:5.0f}  (saves {d50b-d50n:5.0f} draws)")

print("\n  T-denominated (1% cs = 65.67 us/step):")
for us in (10, 20, 30, 50, 100):
    d = us * 0.00015228
    p = p_rec(2.583111 * math.exp(d) * medL, sd_meas)
    print(f"    {us:4d} us/step = {100*d:.4f}% cs -> p/draw {100*p:7.3f}%")

# ---- who holds the record, and on what ------------------------------------
print("\n=== who holds the record, and on what ===")
best = max((r for r in CORPUS if r.get("score")), key=lambda r: r["score"])
print(f"  record receipt: id={best['id'][:8]} solver={best['solver']}  "
      f"score={best['score']:.8f}")
print(f"    cs={best['cs']:.6f}  L={best['L']:.6f}  ts={best['ts']}  "
      f"status={best.get('status')}")
rank = sum(1 for x in Ls if x <= best["L"]) / len(Ls)
print(f"  that L sits at the {100*rank:.2f}th percentile of the corpus L draw")
better_cs = [r for r in CORPUS if r.get("cs") and r["cs"] > best["cs"]]
print(f"  receipts in the whole corpus with a BETTER cs than the record's: "
      f"{len(better_cs)}")
solvers = defaultdict(int)
for r in better_cs:
    solvers[r["solver"]] += 1
print("    by solver: " + ", ".join(f"{k}={v}" for k, v in
                                    sorted(solvers.items(), key=lambda kv: -kv[1])[:10]))
top_cs = sorted((r for r in CORPUS if r.get("cs")), key=lambda r: -r["cs"])[:10]
print("\n  top-10 cs in the entire corpus:")
for r in top_cs:
    print(f"    cs={r['cs']:.6f}  L={r['L']:.6f}  score={r['score']:.6f}  "
          f"{r['solver']:16s} {r['ts']}")
top_sc = sorted((r for r in CORPUS if r.get("score")), key=lambda r: -r["score"])[:10]
print("\n  top-10 score in the entire corpus:")
for r in top_sc:
    print(f"    score={r['score']:.6f}  cs={r['cs']:.6f}  L={r['L']:.6f}  "
          f"{r['solver']:16s} {r['ts']}")
