#!/usr/bin/env python3
"""All six statistics on the two identical-tree replicate triplets."""
import json, math, statistics as st

D0, P0 = 0.013890, 0.0003845
rows = json.load(open("/tmp/pr137_submit/feed.json"))
short = {}
for r in rows:
    short.setdefault(r["id"][:8], r)

TRIPLETS = [["f8502e12", "71586bcf", "f3cda678"], ["5d522d6a", "5e0e9cd1", "c210d200"]]

STATS = {
    "officialScore":   lambda r, m: r["officialScore"],
    "ns (fixed)":      lambda r, m: (D0 / m["decode_seconds_per_token"]) ** 0.75
                                    * (P0 / m["prefill_seconds_per_token"]) ** 0.25,
    "nsd (decode)":    lambda r, m: (D0 / m["decode_seconds_per_token"]) ** 0.75,
    "decode_speedup":  lambda r, m: m["decode_speedup"],
    "prefill_speedup": lambda r, m: m["prefill_speedup"],
    "cand decode s/t": lambda r, m: m["decode_seconds_per_token"],
    "cand prefill s/t": lambda r, m: m["prefill_seconds_per_token"],
    "base decode s/t": lambda r, m: m["baseline_decode_seconds_per_token"],
    "base prefill s/t": lambda r, m: m["baseline_prefill_seconds_per_token"],
}

print("pooled CV over the two identical-tree triplets (4 dof), and per-triplet")
print("%-18s %8s   %8s %8s" % ("statistic", "pooled", "trip1", "trip2"))
res = {}
for name, f in STATS.items():
    sq, dof, per = 0.0, 0, []
    for t in TRIPLETS:
        v = [f(short[s], short[s]["officialMetrics"]) for s in t]
        c = st.stdev(v) / st.mean(v)
        per.append(100 * c)
        sq += st.variance(v) / st.mean(v) ** 2 * 2
        dof += 2
    pooled = 100 * math.sqrt(sq / dof)
    res[name] = pooled
    print("%-18s %7.3f%%   %7.3f%% %7.3f%%" % (name, pooled, per[0], per[1]))

print()
print("ratio ns/nsd            %.2fx" % (res["ns (fixed)"] / res["nsd (decode)"]))
print("ratio officialScore/nsd %.2fx" % (res["officialScore"] / res["nsd (decode)"]))
print("ratio officialScore/ns  %.2fx" % (res["officialScore"] / res["ns (fixed)"]))

# correlation of candidate vs baseline within the triplets
print()
for axis in ("decode", "prefill"):
    xs, ys = [], []
    for t in TRIPLETS:
        c = [short[s]["officialMetrics"]["%s_seconds_per_token" % axis] for s in t]
        b = [short[s]["officialMetrics"]["baseline_%s_seconds_per_token" % axis] for s in t]
        mc, mb = st.mean(c), st.mean(b)
        xs += [x / mc - 1 for x in c]
        ys += [y / mb - 1 for y in b]
    n = len(xs)
    sx = math.sqrt(sum(x * x for x in xs))
    sy = math.sqrt(sum(y * y for y in ys))
    rho = sum(x * y for x, y in zip(xs, ys)) / (sx * sy)
    print("within-triplet rho(candidate, baseline) %-8s %+.3f  (n=%d)" % (axis, rho, n))

# GO/KILL in sigma, under both noise estimates
print()
ADV, GO, KILL = 2.5982163, 2.6045, 2.5919
for label, sd in (("triplet ns sd %.3f%%" % res["ns (fixed)"], res["ns (fixed)"]),
                  ("cluster ns sd 0.425%", 0.425)):
    pair = sd * math.sqrt(2)
    print("%-24s  GO %+.2f sigma(single) %+.2f sigma(paired) | full transfer 0.933%% = %.2f sigma(paired)"
          % (label, 100 * (GO / ADV - 1) / sd, 100 * (GO / ADV - 1) / pair, 0.933 / pair))
