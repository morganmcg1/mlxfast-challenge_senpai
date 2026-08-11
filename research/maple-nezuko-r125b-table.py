#!/usr/bin/env python3
"""R125-B: emit the two Markdown tables of §3.2 straight from the certify TSV.

Transcription of measured numbers into prose is where write-ups lie by
accident, so the tables in §3.2 are generated, not typed. Units and direction
are baked into every column header, per the advisor's comment-4 requirement.

  usage: python3 research/maple-nezuko-r125b-table.py [ROWS.tsv]

Geometry columns come from §3.0 arithmetic (total simdgroups pinned; h64 rows
= 10240, so TGs(h64) = 10240/ns and simdgroups/core is ns-invariant).
"""
import csv
import random
import statistics as st
import sys

ROWS = sys.argv[1] if len(sys.argv) > 1 else "/tmp/r125b-certify.tsv"
REF = "N2"
NS = {"N2": 2, "N4": 4, "N8": 8}
CORES = (20, 40)
B_BOOT = 20000
SEED = 125

rows = [r for r in csv.DictReader(open(ROWS), delimiter="\t") if r.get("arm")]
lvl = {}
for r in rows:
    lvl.setdefault(r["arm"], {})[int(r["block"])] = float(r["decode_s_per_token"]) * 1e6
golds = sorted({r["golden"] for r in rows})
passes = sorted({r["passed"] for r in rows})
arms = [a for a in ("N2", "N4", "N8") if a in lvl]
grand = st.mean(v for a in arms for v in lvl[a].values())

print("**Levels.** Geometry columns are §3.0 arithmetic; the level columns are")
print("measured. Total simdgroups are pinned at 10240 (h64) across the ladder, so")
print("simdgroups/core does not move — only the packaging does.\n")
hdr = ("| arm | `ns` | threads/TG | TGs h64 | TGs/core C=20 | TGs/core C=40 "
       "| simdgroups/core C=20 | simdgroups/core C=40 | n runs "
       "| mean level, µs/step (minimize) | sd, µs/step | cv |")
print(hdr)
print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
for a in arms:
    ns = NS[a]
    v = list(lvl[a].values())
    tg = 10240 // ns
    label = a + (" (ref, shipped)" if a == REF else "")
    print(f"| {label} | {ns} | {32*ns} | {tg} | {tg/CORES[0]:.1f} | {tg/CORES[1]:.1f} "
          f"| {10240/CORES[0]:.0f} | {10240/CORES[1]:.0f} | {len(v)} "
          f"| **{st.mean(v):.3f}** | {st.stdev(v):.2f} | {100*st.stdev(v)/st.mean(v):.3f} % |")

print()
print("**Paired contrasts.** Each block contributes one delta (same block, same")
print("thermal state, rotated slot). Positive = candidate is SLOWER = worse;")
print("the landing rule needs a CI strictly below zero.\n")
print("| contrast | per-block Δ, µs/step (minimize) | median Δ | mean Δ "
      "| bootstrap CI95 (B=20000) | covers 0 | blocks with Δ<0 (a win) "
      "| sign-test p | Δ as % of step |")
print("|---|---|---:|---:|---|---|---:|---:|---:|")
rnd = random.Random(SEED)
summary = {}
for a in arms:
    if a == REF:
        continue
    blocks = sorted(set(lvl[a]) & set(lvl[REF]))
    d = [lvl[a][b] - lvl[REF][b] for b in blocks]
    boots = sorted(st.median(rnd.choice(d) for _ in d) for _ in range(B_BOOT))
    lo, hi = boots[int(0.025 * B_BOOT)], boots[int(0.975 * B_BOOT) - 1]
    neg = sum(1 for x in d if x < 0)
    n = len(d)
    # exact two-sided sign test
    from math import comb
    k = min(neg, n - neg)
    p = min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)
    med = st.median(d)
    cell = ", ".join(f"{x:+.2f}" for x in d)
    print(f"| **{a} − {REF}** | {cell} | **{med:+.2f}** | {st.mean(d):+.2f} "
          f"| [{lo:+.2f}, {hi:+.2f}] | {'YES' if lo <= 0 <= hi else 'NO'} "
          f"| {neg} / {n} | {p:.4f} | {100*med/grand:+.4f} % |")
    summary[a] = (med, lo, hi, neg, n)

print()
print(f"Grand mean level across all {len(rows)} runs: **{grand:.1f} µs/step "
      f"(minimize)**. `passed_correctness` = {'/'.join(passes)} on every run; "
      f"golden hash{'es' if len(golds) > 1 else ''} observed: "
      + ", ".join('`' + g[:8] + '…' + g[-8:] + '`' for g in golds)
      + f" ({len(golds)} distinct across {len(rows)} runs).")
for a, (med, lo, hi, neg, n) in summary.items():
    print(f"  {a}: median {med:+.2f} CI95 [{lo:+.2f}, {hi:+.2f}], "
          f"{n-neg}/{n} blocks slower")
