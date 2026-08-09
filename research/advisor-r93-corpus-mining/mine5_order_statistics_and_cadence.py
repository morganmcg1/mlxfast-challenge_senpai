import json, statistics as st, collections, math

rows = json.load(open("research/r91b-runs/baseline-drift.json"))
rows = [r for r in rows if isinstance(r, dict) and r.get("cand_dec") and r.get("cand_pre")]
rows.sort(key=lambda r: r["ts"])
OUR_D, OUR_P = 0.0048937119140625, 0.000188042724609375
MB_D, MB_P = 0.013855009542, 0.000372473193
TARGET = 2.61650354381456
def cs(d, p): return (MB_D/d)**0.75 * (MB_P/p)**0.25
OURS = cs(OUR_D, OUR_P)

print("=== A. per-solver decode distribution for the top pack (best-of-n as order statistic) ===")
by = collections.defaultdict(list)
for r in rows: by[r["solver"]].append(r)
# expected min of n standard normals (Blom)
def emin(n): 
    from statistics import NormalDist
    return NormalDist().inv_cdf((1-0.375)/(n+0.25))*-1  # magnitude
print("  %-16s %4s %9s %9s %9s %9s %9s" % ("solver","n","mean%","sd%","min%","z_min","E|min| Blom"))
for s in ["MyatKaung","morganmcg1","a-github-name","yudduy","lBroth","davidtai","metaspartan","polymorf","saucegodbased","0xkydo","Gajesh2007"]:
    rs = by.get(s,[])
    if len(rs) < 3: continue
    pct = [100*(r["cand_dec"]/OUR_D-1) for r in rs]
    m, sd, mn = st.mean(pct), st.stdev(pct), min(pct)
    print("  %-16s %4d %9.3f %9.3f %9.3f %9.2f %9.2f" % (s, len(rs), m, sd, mn, (mn-m)/sd, emin(len(rs))))

# recent-generation only (last 3 days) for the top pack
print("\n  --- restricted to receipts on/after 2026-08-06 ---")
for s in ["MyatKaung","morganmcg1","a-github-name","yudduy","lBroth"]:
    rs = [r for r in by.get(s,[]) if r["ts"] >= "2026-08-06"]
    if len(rs) < 3: continue
    pct = [100*(r["cand_dec"]/OUR_D-1) for r in rs]
    m, sd, mn = st.mean(pct), st.stdev(pct), min(pct)
    print("  %-16s %4d %9.3f %9.3f %9.3f %9.2f %9.2f" % (s, len(rs), m, sd, mn, (mn-m)/sd, emin(len(rs))))

print("\n=== B. score variance decomposition (rule 47 refined) ===")
s_bld, s_blp, s_cdd, s_cdp = 0.2345, 2.1829, 0.2924, 0.2573
terms = {"bl_dec (0.75w)": (0.75*s_bld)**2, "cand_dec (0.75w)": (0.75*s_cdd)**2,
         "bl_pre (0.25w)": (0.25*s_blp)**2, "cand_pre (0.25w)": (0.25*s_cdp)**2}
tot = sum(terms.values())
for k, v in sorted(terms.items(), key=lambda kv: -kv[1]):
    print("  %-20s var=%.5f  share=%5.1f%%  sd_contrib=%.4f%%" % (k, v, 100*v/tot, math.sqrt(v)))
sig = math.sqrt(tot)
print("  TOTAL sigma(published score) = %.4f %%   (baseline-only empirical was 0.540 %%)" % sig)

deficit = 100*(TARGET/OURS - 1)
z = deficit/sig
from statistics import NormalDist
p = 1 - NormalDist().cdf(z)
print("\n=== C. promotion arithmetic at zero code improvement ===")
print("  our common-baseline cs        = %.6f" % OURS)
print("  record                        = %.6f" % TARGET)
print("  deficit                       = %.4f %% of score" % deficit)
print("  sigma(score)                  = %.4f %%" % sig)
print("  z                             = %.3f" % z)
print("  P(one draw promotes)          = %.2f %%" % (100*p))
print("  k50 (median draws to promote) = %.1f" % (math.log(0.5)/math.log(1-p)))
print("  k90                           = %.1f" % (math.log(0.10)/math.log(1-p)))
for g in [0.25, 0.5, 0.75, 1.0]:
    d2 = 100*(TARGET/cs(OUR_D*(1-g/100), OUR_P) - 1)
    z2 = d2/sig; p2 = 1-NormalDist().cdf(z2)
    print("  decode -%.2f%% -> deficit %.4f%%  P=%.2f%%  k50=%.1f  (x%.1f)" % (g, d2, 100*p2, math.log(0.5)/math.log(1-p2), p2/p))

print("\n=== D. empirical check: fraction of all draws that would promote Arm R ===")
for lab, sub in [("all", rows), ("since 08-06", [r for r in rows if r["ts"]>="2026-08-06"]), ("since 08-08", [r for r in rows if r["ts"]>="2026-08-08"])]:
    n = 0
    for r in sub:
        s = (r["bl_dec"]/OUR_D)**0.75 * (r["bl_pre"]/OUR_P)**0.25
        if s > TARGET: n += 1
    pe = n/len(sub)
    print("  %-12s n=%4d  promote=%3d  P=%.2f%%  k50=%.1f" % (lab, len(sub), n, 100*pe, math.log(0.5)/math.log(1-pe) if pe>0 else float('inf')))
