import json, statistics as st, collections, math, sys

P = "research/r91b-runs/baseline-drift.json"
raw = json.load(open(P))
rows = raw if isinstance(raw, list) else raw.get("receipts") or raw.get("rows") or list(raw.values())[0]
rows = [r for r in rows if isinstance(r, dict)]

MB_D, MB_P = 0.013855009542, 0.000372473193
OUR_D, OUR_P = 0.0048937119140625, 0.000188042724609375
TARGET = 2.61650354381456

def cs(d, p):
    return (MB_D / d) ** 0.75 * (MB_P / p) ** 0.25

ok = [r for r in rows if r.get("cand_dec") and r.get("cand_pre")]
for r in ok:
    r["cs"] = cs(r["cand_dec"], r["cand_pre"])
ok.sort(key=lambda r: r["ts"])
print("total receipts", len(rows), "with cand timings", len(ok))

# ---------- 1. MyatKaung profile ----------
print("\n=== 1. MyatKaung full profile ===")
mk = [r for r in ok if r["solver"] == "MyatKaung"]
for r in mk:
    print("  %s %s dec=%.12f (%+.3f%%) pre=%.12f (%+.3f%%) cs=%.6f pub=%.6f harness=%s status=%s" % (
        r["ts"], r["id"][:8], r["cand_dec"], 100*(r["cand_dec"]/OUR_D-1),
        r["cand_pre"], 100*(r["cand_pre"]/OUR_P-1), r["cs"], r.get("score") or -1,
        str(r.get("harness"))[:8], r.get("status")))
print("  adjacent |delta| cand_dec:", ["%.4f%%" % (100*abs(mk[i+1]["cand_dec"]/mk[i]["cand_dec"]-1)) for i in range(len(mk)-1)])
print("  adjacent minutes:", [round((__import__('datetime').datetime.fromisoformat(mk[i+1]["ts"].replace("Z","+00:00"))-__import__('datetime').datetime.fromisoformat(mk[i]["ts"].replace("Z","+00:00"))).total_seconds()/60,1) for i in range(len(mk)-1)])

# ---------- 2. merit per submission ----------
print("\n=== 2. merit per submission (n>=3) ===")
by = collections.defaultdict(list)
for r in ok:
    by[r["solver"]].append(r)
tab = []
for s, rs in by.items():
    if len(rs) < 3: continue
    rs.sort(key=lambda r: r["ts"])
    best = max(rs, key=lambda r: r["cs"])
    idx = rs.index(best) + 1
    tab.append((best["cs"], s, len(rs), idx, best["id"][:8], best["ts"][:16]))
tab.sort(reverse=True)
print("  %-22s %5s %5s %6s  %-10s %s" % ("solver", "n", "n_to_best", "best_cs", "id", "ts"))
for c, s, n, idx, i, t in tab:
    print("  %-22s %5d %9d %8.6f  %-10s %s" % (s, n, idx, c, i, t))

# ---------- 3. harness forensics ----------
print("\n=== 3. harness_hash forensics ===")
hs = collections.Counter(str(r.get("harness")) for r in ok)
print("  distinct harness values:", len(hs))
for h, n in hs.most_common():
    sub = [r for r in ok if str(r.get("harness")) == h]
    print("    %s n=%4d  ts %s .. %s  bl_dec mean=%.9f sd=%.9f  bl_pre mean=%.9f sd=%.9f" % (
        h[:10], n, sub[0]["ts"][:16], sub[-1]["ts"][:16],
        st.mean(x["bl_dec"] for x in sub if x.get("bl_dec")),
        (st.stdev([x["bl_dec"] for x in sub if x.get("bl_dec")]) if n > 2 else 0),
        st.mean(x["bl_pre"] for x in sub if x.get("bl_pre")),
        (st.stdev([x["bl_pre"] for x in sub if x.get("bl_pre")]) if n > 2 else 0)))
gs = collections.Counter(str(r.get("golden")) for r in ok)
print("  distinct golden values:", len(gs))
for g, n in gs.most_common():
    sub = [r for r in ok if str(r.get("golden")) == g]
    print("    %s n=%4d ts %s .. %s" % (g[:10], n, sub[0]["ts"][:16], sub[-1]["ts"][:16]))
# interleaving test: is harness time-partitioned?
print("  time-ordered harness run-lengths:")
runs = []
cur = None; cnt = 0
for r in ok:
    h = str(r.get("harness"))[:8]
    if h != cur:
        if cur is not None: runs.append((cur, cnt))
        cur = h; cnt = 0
    cnt += 1
runs.append((cur, cnt))
print("   ", runs[:40], "... total runs:", len(runs))

# ---------- 4. harness-grouped fast-candidate decode ----------
print("\n=== 4. harness-grouped cand_dec for fast candidates (<0.0055) ===")
fast = [r for r in ok if r["cand_dec"] < 0.0055]
byh = collections.defaultdict(list)
for r in fast:
    byh[str(r.get("harness"))[:10]].append(r)
for h, rs in sorted(byh.items(), key=lambda kv: -len(kv[1])):
    d = [r["cand_dec"] for r in rs]
    p = [r["cand_pre"] for r in rs]
    print("  %s n=%4d  cand_dec mean=%.9f (%+.3f%% vs ours) sd=%.9f | cand_pre mean=%.9f (%+.3f%%) sd=%.9f" % (
        h, len(rs), st.mean(d), 100*(st.mean(d)/OUR_D-1), (st.stdev(d) if len(d) > 2 else 0),
        st.mean(p), 100*(st.mean(p)/OUR_P-1), (st.stdev(p) if len(p) > 2 else 0)))
