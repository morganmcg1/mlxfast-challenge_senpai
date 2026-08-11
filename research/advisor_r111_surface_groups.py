#!/usr/bin/env python3
"""Group published receipts into exact editable-surface equivalence classes.

For each ephemeral package commit we hash the *editable* subtree only (the bytes
that actually become the scored executable), then group receipts by that hash.
Receipts in the same class ran the same code; spread within a class is pure
measurement noise.  Spread across classes is code plus noise.

Read-only.  Usage: python3 research/advisor_r111_surface_groups.py
"""
import hashlib
import json
import subprocess
import statistics as st
from collections import defaultdict

CROWN = 2.61650354381456

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


def surface_hash(commit, paths):
    """Hash of (path, blob-sha) for every file under the editable paths."""
    out = subprocess.run(
        ["git", "ls-tree", "-r", commit, "--"] + paths,
        capture_output=True, text=True, check=True,
    ).stdout
    lines = sorted(
        line.split("\t", 1)[1] + " " + line.split()[2]
        for line in out.splitlines() if line.strip()
    )
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()[:12], len(lines)


def main():
    paths = editable_paths()
    head_h, head_n = surface_hash("HEAD", paths)
    print(f"advisor HEAD editable surface: {head_h}  ({head_n} files)\n")

    groups = defaultdict(list)
    for rec, commit, score in RECS:
        h, n = surface_hash(commit, paths)
        groups[h].append((rec, score, n))

    for h, members in sorted(groups.items(), key=lambda kv: -max(m[1] for m in kv[1])):
        mark = "  <== ADVISOR HEAD" if h == head_h else ""
        scores = [m[1] for m in members]
        hdr = f"class {h}  n={len(members)}  files={members[0][2]}{mark}"
        print(hdr)
        for rec, score, _ in sorted(members, key=lambda m: -m[1]):
            print(f"    {rec:9s} {score:.11f}")
        if len(scores) > 1:
            m = st.mean(scores)
            sd = st.stdev(scores)
            print(f"    mean={m:.6f} sd={sd:.6f} rel_sd={100*sd/m:.3f}%")
        print(f"    best is {100*(CROWN-max(scores))/max(scores):+.3f}% below crown")
        print()


if __name__ == "__main__":
    main()
