"""Campaign-A follow-up: is the decode contrast confounded with the prefill channel?

Prefill is a mechanism-null channel. The packed dense-MLP path is gated on
x.dims(1, 1, hidden), so a 512-token prefill provably never enters it and both
arms execute byte-identical prefill code. Any arm effect measured on prefill is
therefore nuisance, and prefill can be used as a covariate to remove the part
of the decode contrast that is shared run-level state.
"""

import glob
import itertools
import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))

rows = []
for path in sorted(glob.glob(os.path.join(HERE, "a_*.json"))):
    name = os.path.basename(path)
    m = json.load(open(path))["metrics"]
    slot = int(name.split("_")[1])
    arm = name.split("_")[2].split(".")[0]
    rows.append((slot, arm, m["decode_seconds_per_token"], m["prefill_seconds_per_token"]))
rows.sort()

dec = [r[2] for r in rows]
pre = [r[3] for r in rows]
n = len(rows)


def pearson(a, b):
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den


r = pearson(dec, pre)
print(f"within-run Pearson r(decode, prefill) over n={n}: {r:+.4f}")
print("  a strong NEGATIVE r would mean a run-level see-saw; a weak r means the")
print("  two channels move independently and cannot be one shared nuisance.\n")

# Regress decode on prefill, then contrast the residuals by arm.
mp, md = statistics.mean(pre), statistics.mean(dec)
slope = sum((p - mp) * (d - md) for p, d in zip(pre, dec)) / sum((p - mp) ** 2 for p in pre)
resid = [d - slope * (p - mp) for d, p in zip(dec, pre)]
print(f"OLS slope d(decode)/d(prefill) = {slope:+.4f}")


def contrast(vals, arms, label, ref):
    on = [v for v, a in zip(vals, arms) if a == "on"]
    off = [v for v, a in zip(vals, arms) if a == "off"]
    delta = statistics.mean(on) - statistics.mean(off)
    pct = 100 * delta / ref
    # exact two-arm permutation, one-sided on "on is slower"
    allv = on + off
    k = len(on)
    hits = tot = 0
    for combo in itertools.combinations(range(len(allv)), k):
        s = set(combo)
        a = [allv[i] for i in combo]
        b = [allv[i] for i in range(len(allv)) if i not in s]
        tot += 1
        if statistics.mean(a) - statistics.mean(b) >= delta:
            hits += 1
    print(f"{label}: on-minus-off = {pct:+.4f}%   exact p(on slower) = {hits}/{tot} = {hits/tot:.4f}")
    return pct


arms = [r[1] for r in rows]
print()
raw = contrast(dec, arms, "decode raw            ", md)
adj = contrast(resid, arms, "decode prefill-adjusted", md)
contrast(pre, arms, "prefill (null channel) ", mp)

print(f"\nregression retained after adjusting for the null channel: "
      f"{adj:+.4f}% of {raw:+.4f}%")
