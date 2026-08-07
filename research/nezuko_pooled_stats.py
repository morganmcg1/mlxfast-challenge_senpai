#!/usr/bin/env python3
"""Robust + pre-registered statistics on the pooled PR205 decode-probe pairs."""
import itertools
import math
import random

S1 = [-9.17, 29.83, -21.10, -6.21, 26.50, -6.63]
S2 = [5.77, 37.33, 30.02, 64.17, 9.44, 21.31, 40.77, -32.52, -8.79, 29.35, -101.10, 34.85]
POOL = S1 + S2

D_M4 = 8293.0          # us/step, arm-B median-of-medians, session 2
D_M5 = 4928.12         # us/step, official decode_seconds_per_token (mine)
PRED = 14.02           # us/step, pre-registered kernel-level projection


def tcrit(df):
    tab = {5: 2.571, 11: 2.201, 17: 2.110, 1e9: 1.960}
    return tab[min(tab, key=lambda k: abs(k - df))]


def summarize(name, xs):
    n = len(xs)
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    se = sd / math.sqrt(n)
    tc = tcrit(n - 1)
    lo, hi = m - tc * se, m + tc * se
    print(f"{name}: n={n} mean {m:+.2f} sd {sd:.2f} se {se:.2f} t {m/se:+.2f}")
    print(f"    95% CI [{lo:+.2f}, {hi:+.2f}] half-width {tc*se:.2f}")
    print(f"    zero in CI {lo <= 0 <= hi} | pred {PRED} in CI {lo <= PRED <= hi}")
    return m, sd, se


print("=== pre-registered (mean of run-median pair savings) ===")
summarize("session1", S1)
summarize("session2", S2)
m_pool, sd_pool, se_pool = summarize("POOLED  ", POOL)
print(f"    pooled as % of M4 step: {100*m_pool/D_M4:+.4f} %")

print("\n=== robust secondary (NOT pre-registered) ===")
srt = sorted(POOL)
n = len(srt)
med = (srt[n // 2 - 1] + srt[n // 2]) / 2
trim = srt[2:-2]
print(f"median {med:+.2f}  10%-trimmed mean {sum(trim)/len(trim):+.2f}  (dropped {srt[:2]} {srt[-2:]})")

pos = sum(1 for x in POOL if x > 0)
p1 = sum(math.comb(n, k) for k in range(pos, n + 1)) / 2 ** n
print(f"sign test: {pos}/{n} pairs positive, one-sided p={p1:.4f}, two-sided p={min(1,2*p1):.4f}")

# Wilcoxon signed-rank, exact null by sign enumeration on |x| ranks
mag = sorted(range(n), key=lambda i: abs(POOL[i]))
rank = [0] * n
for r, i in enumerate(mag, 1):
    rank[i] = r
wobs = sum(rank[i] for i in range(n) if POOL[i] > 0)
cnt = 0
tot = 0
for signs in itertools.product((0, 1), repeat=n):
    tot += 1
    if sum(rank[i] for i in range(n) if signs[i]) >= wobs:
        cnt += 1
print(f"wilcoxon W+={wobs} exact one-sided p={cnt/tot:.4f}")

random.seed(11)
boot = sorted(sum(random.choice(POOL) for _ in range(n)) / n for _ in range(200000))
print(f"bootstrap mean 95% CI [{boot[4999]:+.2f}, {boot[194999]:+.2f}]")

print("\n=== M5 receipt contrast (vs ranked anchor 08ddee45) ===")
sig_pct = 0.3637
obs_pct = -0.4912
m5, s5 = obs_pct / 100 * D_M5, sig_pct / 100 * D_M5
print(f"decode_speedup {obs_pct:+.4f} % +- {sig_pct:.4f} % (1 sigma)")
print(f"  as us/step saved: {m5:+.2f} +- {s5:.2f}")
print(f"  95% CI [{m5-1.96*s5:+.2f}, {m5+1.96*s5:+.2f}] | pred in CI {m5-1.96*s5 <= PRED <= m5+1.96*s5}")

print("\n=== heterogeneity + caveated inverse-variance meta-analysis ===")
w4, w5 = 1 / se_pool ** 2, 1 / s5 ** 2
comb = (m_pool * w4 + m5 * w5) / (w4 + w5)
sec = math.sqrt(1 / (w4 + w5))
zdiff = (m_pool - m5) / math.sqrt(se_pool ** 2 + s5 ** 2)
print(f"M4 in-situ {m_pool:+.2f} +- {se_pool:.2f} | M5 receipt {m5:+.2f} +- {s5:.2f}")
print(f"agreement between hosts: z={zdiff:+.2f} (|z|<1.96 -> not distinguishable)")
print(f"combined {comb:+.2f} +- {sec:.2f}  95% CI [{comb-1.96*sec:+.2f}, {comb+1.96*sec:+.2f}]")
print(f"  zero in CI {comb-1.96*sec <= 0 <= comb+1.96*sec} | pred in CI {comb-1.96*sec <= PRED <= comb+1.96*sec}")

print("\n=== power ===")
for target in (PRED, PRED / 2):
    need = sd_pool ** 2 * (1.96 + 0.84) ** 2 / target ** 2
    print(f"  pairs for 80% power vs {target:.2f} us: {math.ceil(need)}  (~{math.ceil(need)*2*51/60:.0f} min)")
