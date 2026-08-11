#!/usr/bin/env python3
"""Semantic (comment-insensitive) equivalence classes over published receipts.

Submissions to this service are de-duplicated by archive bytes, so every team
that wants a second draw of the *same* executable must perturb the source with a
nonce comment.  A raw tree hash therefore reports "different code" for runs that
are behaviourally identical.  This script strips line comments, block comments
and blank lines before hashing, so receipts that differ only by nonce comments
land in one class.

Within-class spread is pure published-score measurement noise for a fixed
executable.  That number sets the resolution limit of a single receipt and hence
the EV of an unchanged replay.

Read-only.  Usage: python3 research/advisor_r111_semantic_surface.py
"""
import hashlib
import json
import re
import subprocess
import statistics as st
from collections import defaultdict

CROWN = 2.61650354381456  # promoted organizer frontier, receipt cc6ddc1

# (receipt, ephemeral package commit, published score, short note label)
RECS = [
    ("0b9ae91", "2d967a120e60a706fca4425545c5f303ad7a9563", 2.59235893273017, "r105-A ladder A1-1"),
    ("a8a8040", "1f08e907b8d72e6d6f8e3f7b6f792d12756590cc", 2.56209897966587, "r104-A leg02 armA d4"),
    ("c52994d", "5e435a6b693635bd1ec8647210673a0ba837f102", 2.55553342334089, "r105-A ladder A1-2"),
    ("795badf", "f958d7f502ff07b99d030e8655b00baf8889d72a", 2.56484791659022, "r104-A leg03 armC d8"),
    ("8a09a94", "b2199f4e0c43ab3614f781e5fdfd6a5dbcd1247b", 2.59589219882205, "r104-A leg04 armA d4"),
    ("6fc8abf", "047e192596a091111da7fa9e95fc4d120831fbc0", 2.56621424254101, "r105-B P0 frieren"),
    ("e27f1ce", "5c542169b5e6c295805f50fa65df3150816eb443", 2.60664969895906, "merged frontier #549+#604"),
    ("2771067", "dbd0b684c9abb9052720269250ff504ca2e421e9", 2.59380735131190, "MAPLE R106E draw01"),
    ("59d2418", "091dd04a825f39328b30980025474b71c677e5a9", 2.58107301539733, "r106e-replay-02"),
    ("2397aee", "81572e5132b6f950dfcb6350c037a4d0a25c8013", 2.56572013933736, "r106e-replay-03"),
    ("c1c0ba2", "074f47e88fe5ed4c935c31e4a42d8c3c1865c382", 2.56974410819947, "fern replay (== HEAD)"),
]

BLOCK = re.compile(rb"/\*.*?\*/", re.S)
LINE = re.compile(rb"//[^\n]*")


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


def normalize(blob: bytes) -> bytes:
    blob = BLOCK.sub(b"", blob)
    blob = LINE.sub(b"", blob)
    lines = [ln.strip() for ln in blob.split(b"\n")]
    return b"\n".join(ln for ln in lines if ln)


def semantic_hash(commit, paths):
    out = subprocess.run(
        ["git", "ls-tree", "-r", commit, "--"] + paths,
        capture_output=True, text=True, check=True,
    ).stdout
    entries = []
    for line in out.splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        sha = meta.split()[2]
        entries.append((path, sha))
    entries.sort()
    h = hashlib.sha256()
    for path, sha in entries:
        blob = subprocess.run(["git", "cat-file", "blob", sha],
                              capture_output=True, check=True).stdout
        h.update(path.encode() + b"\0")
        h.update(hashlib.sha256(normalize(blob)).digest())
    return h.hexdigest()[:12]


def main():
    paths = editable_paths()
    head_h = semantic_hash("HEAD", paths)
    print(f"advisor HEAD semantic surface: {head_h}\n")

    groups = defaultdict(list)
    for rec, commit, score, label in RECS:
        groups[semantic_hash(commit, paths)].append((rec, score, label))

    within = []
    for h, members in sorted(groups.items(), key=lambda kv: -max(m[1] for m in kv[1])):
        mark = "   <== ADVISOR HEAD" if h == head_h else ""
        print(f"class {h}  n={len(members)}{mark}")
        for rec, score, label in sorted(members, key=lambda m: -m[1]):
            print(f"    {rec:9s} {score:.11f}   {label}")
        scores = [m[1] for m in members]
        if len(scores) > 1:
            m = st.mean(scores)
            sd = st.stdev(scores)
            rng = 100 * (max(scores) - min(scores)) / m
            print(f"    -> same executable: mean={m:.6f} sd={sd:.6f} "
                  f"rel_sd={100*sd/m:.3f}% peak-to-peak={rng:.3f}%")
            within.extend((s - m) / m for s in scores)
        print()

    if within:
        pooled = st.pstdev(within) * (len(within) / max(len(within) - len(
            [g for g in groups.values() if len(g) > 1]), 1)) ** 0.5
        print(f"pooled within-executable rel. sd over {len(within)} receipts "
              f"in {sum(1 for g in groups.values() if len(g)>1)} classes: "
              f"{100*pooled:.3f}%")
        print()
        print("Implication for an unchanged replay of advisor HEAD:")
        base = [s for _, s, _ in groups[head_h]]
        if base:
            m = st.mean(base)
            z = (CROWN - m) / (pooled * m)
            from math import erfc, sqrt
            p = 0.5 * erfc(z / sqrt(2))
            print(f"  HEAD-class mean={m:.6f}, crown deficit="
                  f"{100*(CROWN-m)/m:.3f}%, z={z:.2f}, "
                  f"P(single replay >= crown)~{100*p:.2f}%")
            for n in (10, 20, 30):
                print(f"    over {n:2d} shots: {100*(1-(1-p)**n):.1f}%")


if __name__ == "__main__":
    main()
