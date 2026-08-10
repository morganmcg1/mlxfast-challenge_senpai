import json, os, urllib.request
tok = os.environ["MLXFAST_API_TOKEN"]
url = "https://api.mlx.fast/api/benchmarks/1854efdf-feba-4773-bae9-b80520881a74/submissions"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
d = json.load(urllib.request.urlopen(req, timeout=40))
rows = d["submissions"] if isinstance(d, dict) else d
print("total receipts on benchmark:", len(rows))
users = {}
for r in rows:
    u = r.get("solverUsername")
    users[u] = users.get(u, 0) + 1
print(sorted(users.items(), key=lambda kv: -kv[1])[:6])
mm = [r for r in rows if r.get("solverUsername") == "morganmcg1" and r.get("officialScore")]
mm.sort(key=lambda r: -r["officialScore"])
print("top 8 morganmcg1 published:")
for r in mm[:8]:
    om = r.get("officialMetrics") or {}
    print("  %s %s %.11f commit=%s status=%s promo=%s" % (
        r["id"][:7], r.get("createdAt"), r["officialScore"],
        str(om.get("commit"))[:8], r["status"], r.get("promotionStatus")))
print("n with score:", len(mm), "max:", mm[0]["officialScore"])
allsc = [r for r in rows if r.get("officialScore")]
allsc.sort(key=lambda r: -r["officialScore"])
print("global top 6:")
for r in allsc[:6]:
    print("  %s %s %.11f" % (r["id"][:7], r.get("solverUsername"), r["officialScore"]))
