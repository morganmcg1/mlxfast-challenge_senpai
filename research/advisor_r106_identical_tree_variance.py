#!/usr/bin/env python3
"""Round-106: measure the official channel's REPLICATION variance directly.

Method
------
`advisor_r103_our_commits.py` maps every morganmcg1 receipt to the commit that
was submitted.  Two receipts whose submitted commits share a byte-identical
`Sources/` tree ran the *same program*: any difference between their scores is
pure channel/rig variance, with no candidate effect mixed in.  Grouping the
receipt corpus by `git rev-parse <commit>:Sources` therefore yields a direct,
assumption-free estimate of sd(cs) and sd(decode) under replication.

Why it matters
--------------
Every promotion decision in this campaign has been taken on 1-vs-1 receipt
differences using an *assumed* sigma.  If the measured replication sigma is
materially larger than the assumed one, those promotions are not supported.

usage: advisor_r106_identical_tree_variance.py [our_commits.json]
"""

import collections
import json
import math
import statistics
import subprocess
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/r106_our_commits.json"
rows = json.load(open(path))


def subtree(sha, sub):
    p = subprocess.run(
        ["git", "rev-parse", f"{sha}:{sub}"], capture_output=True, text=True
    )
    return p.stdout.strip() if p.returncode == 0 else None


def codediff(a, b):
    """Files differing outside the research/ and senpai/ note trees."""
    p = subprocess.run(
        ["git", "diff", "--name-only", a, b, "--",
         ".", ":(exclude)research", ":(exclude)senpai"],
        capture_output=True, text=True,
    )
    return [x for x in p.stdout.split() if x]


def codekey(sha):
    """Identity of everything that can affect the graded binary.

    `Sources/` alone is NOT enough: the vendored MLX/Metal sources under
    `Vendor/` are compiled too, and two commits can share a `Sources/` tree
    while differing in `Vendor/`.  Anything under `research/` or `senpai/` is
    notes and tooling and cannot reach the graded binary.
    """
    p = subprocess.run(
        ["git", "ls-tree", sha], capture_output=True, text=True
    )
    if p.returncode != 0:
        return None
    parts = []
    for line in p.stdout.splitlines():
        meta, _, name = line.partition("\t")
        if name in ("research", "senpai", "docs", "tools", "Tests", "README.md",
                    "AGENTS.md", "TASK.md", ".gitignore", ".agents"):
            continue
        parts.append(f"{name}:{meta.split()[2]}")
    return "|".join(sorted(parts))


for r in rows:
    r["_t"] = codekey(r["commit"])
    r["dec_us"] = r["dec"] * 1e6  # feed reports seconds/step

groups = collections.defaultdict(list)
for r in rows:
    if r["_t"]:
        groups[r["_t"]].append(r)

resolved = sum(len(v) for v in groups.values())
print(f"receipts: {len(rows)}   with a locally resolvable Sources/ tree: {resolved}")
print("\n=== IDENTICAL Sources/ TREES SUBMITTED MORE THAN ONCE ===")

pooled = []
for t, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    if len(rs) < 2:
        continue
    cs = [x["cs"] for x in rs]
    dec = [x["dec_us"] for x in rs]
    rs = sorted(rs, key=lambda y: y["ts"])
    extra = codediff(rs[0]["commit"], rs[-1]["commit"])
    print(f"\ngroup n={len(rs)}   code files differing across the group: "
          f"{len(extra)} {extra if extra else ''}")
    for x in rs:
        print(
            f"   cs {x['cs']:.6f}  decode {x['dec_us']:9.3f} us  "
            f"{x['commit'][:12]}  {x['ts']}  {x['status']}"
        )
    m = statistics.mean(cs)
    print(
        f"   -> cs     mean {m:.6f}  sd {statistics.stdev(cs):.6f} "
        f"({100 * statistics.stdev(cs) / m:.4f}% of cs)  "
        f"range {max(cs) - min(cs):.6f} ({100 * (max(cs) - min(cs)) / m:.4f}%)"
    )
    print(
        f"   -> decode mean {statistics.mean(dec):.3f}  "
        f"sd {statistics.stdev(dec):.3f} us  range {max(dec) - min(dec):.3f} us"
    )
    pooled.append((len(rs), statistics.stdev(cs), m, statistics.stdev(dec)))

if pooled:
    df = sum(n - 1 for n, _, _, _ in pooled)
    sd_cs = math.sqrt(sum((n - 1) * s * s for n, s, _, _ in pooled) / df)
    sd_dec = math.sqrt(sum((n - 1) * s * s for n, _, _, s in pooled) / df)
    mean_cs = statistics.mean([m for _, _, m, _ in pooled])
    print(f"\nPOOLED replication sd(cs)     = {sd_cs:.6f}  "
          f"({100 * sd_cs / mean_cs:.4f}% of cs)   df={df}")
    print(f"POOLED replication sd(decode) = {sd_dec:.3f} us/step")
    print(f"=> sd of a 1-vs-1 DIFFERENCE: cs {100 * sd_cs * math.sqrt(2) / mean_cs:.4f}%"
          f"  decode {sd_dec * math.sqrt(2):.2f} us/step")

    # Robust variant: drop the single worst group, which is dominated by one
    # extreme draw, so the floor is not carried by a single pathological run.
    trimmed = sorted(pooled, key=lambda p: p[1] / p[2])[:-1]
    if trimmed:
        df2 = sum(n - 1 for n, _, _, _ in trimmed)
        sd2 = math.sqrt(sum((n - 1) * s * s for n, s, _, _ in trimmed) / df2)
        m2 = statistics.mean([m for _, _, m, _ in trimmed])
        print(f"ROBUST (worst group dropped) sd(cs) = {sd2:.6f} "
              f"({100 * sd2 / m2:.4f}% of cs), df={df2}; "
              f"1-vs-1 difference sd = {100 * sd2 * math.sqrt(2) / m2:.4f}% of cs")

    print("\n=== ANCHOR PAIRS OF INTEREST (z uses the ROBUST 1-vs-1 sd) ===")
    sd_diff_pct = 100 * sd2 * math.sqrt(2) / m2
    by_commit = {r["commit"][:8]: r for r in rows}
    pairs = [
        ("4b0e051b", "ef055b9b", "router weight prefetch arm 1 vs arm 0 "
                                 "(ONLY difference; matched pair)"),
        ("ef055b9b", "e33efe4e", "surface-reclaim tree vs current-base-equivalent "
                                 "(semantically null for Laguna)"),
        ("4b0e051b", "e33efe4e", "best-ever vs current-base-equivalent"),
        ("bd33883e", "e33efe4e", "merged frontier vs current-base-equivalent"),
    ]
    for a, b, label in pairs:
        ra, rb = by_commit.get(a), by_commit.get(b)
        if not ra or not rb:
            print(f"   {a}/{b}: not in corpus")
            continue
        d = 100 * (ra["cs"] - rb["cs"]) / rb["cs"]
        print(f"   {a} cs {ra['cs']:.6f} vs {b} cs {rb['cs']:.6f}: "
              f"{d:+.4f}% of cs, z = {d / sd_diff_pct:+.2f}   [{label}]")
else:
    print("\n(no identical tree was submitted twice)")
