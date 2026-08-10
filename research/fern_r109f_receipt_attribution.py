import json, os, re, urllib.request
tok = os.environ["MLXFAST_API_TOKEN"]
url = "https://api.mlx.fast/api/benchmarks/1854efdf-feba-4773-bae9-b80520881a74/submissions"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
d = json.load(urllib.request.urlopen(req, timeout=40))
rows = d["submissions"] if isinstance(d, dict) else d
REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626
out = []
for r in rows:
    if r.get("solverUsername") != "morganmcg1":
        continue
    om = r.get("officialMetrics") or {}
    k = ("decode_seconds_per_token", "prefill_seconds_per_token")
    if any(not om.get(x) for x in k):
        continue
    cd, cp = om[k[0]], om[k[1]]
    norm = (REF_D / cd) ** 0.75 * (REF_P / cp) ** 0.25
    note = r.get("note") or ""
    stud = re.findall(r"(maple-[a-z]+|cedar-[a-z]+)", note)
    camp = set()
    if re.search(r"\bcedar\b", note, re.I):
        camp.add("cedar")
    if re.search(r"\bmaple\b", note, re.I):
        camp.add("maple")
    out.append((norm, r["id"][:7], r.get("createdAt", "")[:16], r.get("officialScore"),
                str(om.get("commit"))[:8], "/".join(sorted(camp)) or "?",
                ",".join(sorted(set(stud))) or "-"))
out.sort(reverse=True)
print("%-11s %-8s %-17s %-9s %-9s %-11s %s" %
      ("normalized", "receipt", "created", "published", "commit", "campaign", "students"))
for o in out[:22]:
    print("%.9f %-8s %-17s %.6f %-9s %-11s %s" % o)
print()
print("... maple HEAD class for reference:")
for o in out:
    if o[1] in ("c1c0ba2", "2771067"):
        print("%.9f %-8s %-17s %.6f %-9s %-11s %s" % o)
