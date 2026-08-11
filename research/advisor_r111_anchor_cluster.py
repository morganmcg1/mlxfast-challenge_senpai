#!/usr/bin/env python3
"""Which published receipts were produced by an editable surface byte-identical
to the current advisor HEAD?  Recompute the replay lottery EV from exactly those.

Read-only.  Usage: python3 research/advisor_r111_anchor_cluster.py
"""
import json
import subprocess
import statistics as st
from math import erfc, sqrt

CROWN = 2.61650354381456  # promoted organizer frontier, receipt cc6ddc1

# (receipt, ephemeral package commit, published score)
RECS = [
    ("0b9ae91", "2d967a120e60a706fca4425545c5f303ad7a9563", 2.59235893273017),
    ("a8a8040", "1f08e907b8d72e6d6f8e3f7b6f792d12756590cc", 2.56209897966587),
    ("c52994d", "5e435a6b693635bd1ec8647210673a0ba837f102", 2.55553342334089),
    ("795badf", "f958d7f502ff07b99d030e8655b00baf8889d72a", 2.56484791659022),
    ("8a09a94", "b2199f4e0c43ab3614f781e5fdfd6a5dbcd1247b", 2.59589219882205),
    ("6fc8abf", "047e192596a091111da7fa9e95fc4d120831fbc0", 2.56621424254101),
    ("e27f1ce", "5c542169b5e6c295805f50fa65df3150816eb443", 2.60664969895906),
    ("2771067", "dbd0b684c9abb9052720269250ff504ca2e421e9", 2.59380735131190),
    ("59d2418", "091dd04a825f39328b30980025474b71c677e5a9", 2.58107301539733),
    ("2397aee", "81572e5132b6f950dfcb6350c037a4d0a25c8013", 2.56572013933736),
    ("c1c0ba2", "074f47e88fe5ed4c935c31e4a42d8c3c1865c382", 2.56974410819947),
]


def editable_paths():
    acc = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "editablePaths":
                    acc.append(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(json.load(open("benchmark.json")))
    return sorted({p for s in acc for p in s})


def main():
    paths = editable_paths()
    same = []
    print("receipt      score            editable surface vs advisor HEAD")
    for rec, commit, score in RECS:
        d = subprocess.run(
            ["git", "diff", "--stat", commit, "HEAD", "--"] + paths,
            capture_output=True, text=True,
        ).stdout.strip()
        if d:
            tag = "DIFFERS (" + d.splitlines()[-1].strip() + ")"
        else:
            tag = "IDENTICAL"
            same.append(score)
        print(f"{rec:10s} {score:.11f}  {tag}")

    print()
    print(f"n identical-to-HEAD receipts: {len(same)}")
    if len(same) < 2:
        return
    m = st.mean(same)
    sd = st.stdev(same)
    z = (CROWN - m) / sd
    p = 0.5 * erfc(z / sqrt(2))
    print(f"mean={m:.6f}  sd={sd:.6f}  rel_sd={100*sd/m:.3f}%")
    print(f"min={min(same):.5f}  max={max(same):.5f}")
    print(f"crown={CROWN}  deficit_of_mean={100*(CROWN-m)/m:.3f}%  z={z:.3f}")
    print(f"P(single replay >= crown) ~= {100*p:.3f}%")
    for n in (10, 20, 30):
        print(f"  cumulative over {n:2d} shots: {100*(1-(1-p)**n):.1f}%")
    print()
    print("empirical: shots at or above crown =",
          sum(1 for s in same if s >= CROWN), "of", len(same))


if __name__ == "__main__":
    main()
