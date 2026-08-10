import json, os, urllib.request, statistics as st, math
tok = os.environ["MLXFAST_API_TOKEN"]
url = "https://api.mlx.fast/api/benchmarks/1854efdf-feba-4773-bae9-b80520881a74/submissions"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
d = json.load(urllib.request.urlopen(req, timeout=40))
rows = d["submissions"] if isinstance(d, dict) else d
REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626
CROWN = 2.61650354381456


def ax(r):
    om = r.get("officialMetrics") or {}
    k = ("decode_seconds_per_token", "prefill_seconds_per_token",
         "baseline_decode_seconds_per_token", "baseline_prefill_seconds_per_token")
    if any(not om.get(x) for x in k):
        return None
    cd, cp, bd, bp = (om[x] for x in k)
    return {
        "id": r["id"][:7], "user": r.get("solverUsername"), "created": r.get("createdAt"),
        "pub": r.get("officialScore"),
        "norm": (REF_D / cd) ** 0.75 * (REF_P / cp) ** 0.25,
        "draw": (bd / REF_D) ** 0.75 * (bp / REF_P) ** 0.25,
        "cd": cd * 1e6, "cp": cp * 1e6, "bd": bd * 1e6, "bp": bp * 1e6,
    }


recs = [a for a in (ax(r) for r in rows) if a and a["pub"]]
print("receipts with full legs:", len(recs))
crown = [a for a in recs if a["id"] == "cc6ddc1"]
print()
print("== crown receipt ==")
for a in crown:
    print("  %s %s %s pub %.11f norm %.9f draw %.6f cd %.1f cp %.2f bd %.1f bp %.2f"
          % (a["id"], a["user"], a["created"], a["pub"], a["norm"], a["draw"],
             a["cd"], a["cp"], a["bd"], a["bp"]))
print()
byn = sorted(recs, key=lambda a: -a["norm"])
print("== top 10 by NORMALIZED (executable quality, luck removed) ==")
for a in byn[:10]:
    print("  %-8s %-16s pub %.6f norm %.9f draw %.6f cd %.1f cp %.2f"
          % (a["id"], a["user"], a["pub"], a["norm"], a["draw"], a["cd"], a["cp"]))
print()
mine = [a for a in recs if a["id"] in ("c1c0ba2", "2771067")]
hn = st.fmean([a["norm"] for a in mine])
print("maple HEAD class normalized mean: %.9f" % hn)
for a in byn[:1]:
    print("best normalized anywhere: %.9f (%s, %s) => maple code gap %.3f %%"
          % (a["norm"], a["id"], a["user"], 100 * (a["norm"] / hn - 1)))
cn = crown[0]["norm"] if crown else None
if cn:
    print("crown normalized: %.9f => maple code gap to the crown EXECUTABLE %.3f %%"
          % (cn, 100 * (cn / hn - 1)))
    print("crown draw: %.6f ; account draw mean %.6f ; crown luck premium %.3f %%"
          % (crown[0]["draw"],
             st.fmean([a["draw"] for a in recs if a["user"] == "morganmcg1"]),
             100 * (crown[0]["draw"] / st.fmean([a["draw"] for a in recs]) - 1)))
print()
draws = [a["draw"] for a in recs]
print("draw distribution over ALL %d receipts: mean %.6f cv %.4f %% min %.6f max %.6f"
      % (len(draws), st.fmean(draws), 100 * st.stdev(draws) / st.fmean(draws),
         min(draws), max(draws)))
mmd = [a["draw"] for a in recs if a["user"] == "morganmcg1"]
print("draw distribution over morganmcg1 %d receipts: mean %.6f cv %.4f %% max %.6f"
      % (len(mmd), st.fmean(mmd), 100 * st.stdev(mmd) / st.fmean(mmd), max(mmd)))
need = CROWN / hn
print()
print("required draw for a HEAD-class replay to take the crown: %.6f" % need)
print("  observed draws >= that, all accounts: %d / %d (%.3f %%)"
      % (sum(1 for x in draws if x >= need), len(draws),
         100 * sum(1 for x in draws if x >= need) / len(draws)))
mu = st.fmean([math.log(x) for x in draws])
sg = st.stdev([math.log(x) for x in draws])
z = (math.log(need) - mu) / sg
p = 0.5 * math.erfc(z / math.sqrt(2))
print("  lognormal fit (n=%d, sd %.4f %%): z %.3f  P/shot %.4f %%  P over 30 shots %.2f %%"
      % (len(draws), 100 * sg, z, 100 * p, 100 * (1 - (1 - p) ** 30)))
mud = st.fmean([math.log(x) for x in mmd])
sgd = st.stdev([math.log(x) for x in mmd])
zd = (math.log(need) - mud) / sgd
pd = 0.5 * math.erfc(zd / math.sqrt(2))
print("  lognormal fit on morganmcg1 only (n=%d, sd %.4f %%): z %.3f  P/shot %.4f %%  P over 30 shots %.2f %%"
      % (len(mmd), 100 * sgd, zd, 100 * pd, 100 * (1 - (1 - pd) ** 30)))
