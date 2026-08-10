#!/usr/bin/env python3
"""Win probability per official shot, from the n=16 maple-fern receipt sample.

published = normalized x draw
  normalized = (REF_decode/cand_decode)^0.75 * (REF_prefill/cand_prefill)^0.25
  draw       = the harness's baseline re-measurement on that run

The two factors are measured separately on every receipt, so their spreads can
be estimated independently and recombined without assuming anything about the
service.
"""
import json
import math
import statistics as st

CACHE = "research/artifacts/fern-r109f/receipts/submissions.json"
REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626
CROWN = 2.61650354381456
BEST_OURS = 2.60664969895906


def norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


rows = json.load(open(CACHE))
if isinstance(rows, dict):
    rows = rows.get("submissions", rows.get("items", []))
mine = []
allrows = []
for r in rows:
    m = r.get("officialMetrics") or {}
    if not m.get("decode_seconds_per_token"):
        continue
    cd, cp = m["decode_seconds_per_token"], m["prefill_seconds_per_token"]
    bd, bp = (
        m["baseline_decode_seconds_per_token"],
        m["baseline_prefill_seconds_per_token"],
    )
    norm = (REF_D / cd) ** 0.75 * (REF_P / cp) ** 0.25
    pub = (bd / cd) ** 0.75 * (bp / cp) ** 0.25
    rec = dict(
        ts=r.get("createdAt", ""),
        who=r.get("solverUsername"),
        norm=norm,
        pub=pub,
        draw=pub / norm,
    )
    allrows.append(rec)
    if rec["who"] == "morganmcg1" and rec["ts"].startswith("2026-08-10"):
        mine.append(rec)

mine.sort(key=lambda d: d["ts"])
norms = [d["norm"] for d in mine]
draws = [d["draw"] for d in mine]

nm, ns = st.mean(norms), st.stdev(norms)
dm, ds = st.mean(draws), st.stdev(draws)
print(f"own receipts n={len(mine)}  (2026-08-10)")
print(f"  normalized  mean {nm:.9f}  sd {ns:.9f}  cv {ns/nm*100:.4f}%")
print(f"  draw        mean {dm:.6f}     sd {ds:.6f}     cv {ds/dm*100:.4f}%")
pubs = [d["pub"] for d in mine]
pm, ps = st.mean(pubs), st.stdev(pubs)
print(f"  published   mean {pm:.9f}  sd {ps:.9f}  cv {ps/pm*100:.4f}%")
print(
    f"  variance share of draw: {(ds/dm)**2/((ds/dm)**2+(ns/nm)**2)*100:.1f}% "
    f"of published variance"
)

# Draw spread from the whole late population is a better estimate of the
# service's baseline noise: it is the same harness for every solver.
late = [d for d in allrows if d["ts"] >= "2026-08-10T00:00:00"]
ldraws = [d["draw"] for d in late]
ldm, lds = st.mean(ldraws), st.stdev(ldraws)
print(f"\nlate-population draw n={len(ldraws)}  mean {ldm:.6f} cv {lds/ldm*100:.4f}%")

print("\nP(published > crown 2.61650354381456) per shot:")
print(f"{'normalized held':>18}{'needed draw':>14}{'z':>8}{'P/shot':>10}{'shots@50%':>11}")
for label, nz in (
    ("own mean", nm),
    ("own best (e27f1ce)", max(norms)),
    ("+0.25%", max(norms) * 1.0025),
    ("+0.50%", max(norms) * 1.005),
    ("+1.00%", max(norms) * 1.010),
    ("+1.32% (=crown/1.0)", CROWN / dm),
):
    need = CROWN / nz
    z = (need - dm) / ds
    p = 1.0 - norm_cdf(z)
    shots = (math.log(0.5) / math.log(1 - p)) if 0 < p < 1 else float("inf")
    print(f"{label:>18}{need:14.6f}{z:8.3f}{p*100:9.3f}%{shots:11.0f}")

print("\nsanity: P(beat our own best published 2.60664969895906) per shot")
for label, nz in (("own mean", nm), ("own best", max(norms))):
    need = BEST_OURS / nz
    z = (need - dm) / ds
    p = 1 - norm_cdf(z)
    print(f"  {label:10s} needed draw {need:.6f}  z {z:6.3f}  P {p*100:6.2f}%")

# What normalized gain would a code change need to make the crown a coin flip?
need_nz = CROWN / dm
print(
    f"\nnormalized needed for P=50%/shot: {need_nz:.9f} "
    f"= +{(need_nz/max(norms)-1)*100:.3f}% over our best receipt"
)
print("programme law: %score = 0.0070 x delta M4_steady_step_wall_us")
print(
    f"  => needs {(need_nz/max(norms)-1)*100/0.0070:.0f} us off the M4 step "
    f"(or the M5 equivalent)"
)
