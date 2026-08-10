#!/usr/bin/env python3
"""Round-106: is the campaign's best-ever tree a semantic no-op vs the base?

Claim under test
----------------
`ef055b9b` ("Arm R", officially cs 2.589321) and `e33efe4e` (officially
cs 2.575633, which the current campaign base `1bc1c895` matches on every
compiled path) differ by +0.5314 % of candidate merit.  If the two programs are
in fact identical after comments and dead code are removed, that 0.53 % is not
an optimisation at all.

Method
------
For every compiled Swift/C/C++/Metal path, strip comment-only and blank lines
and compare the resulting multiset of code lines per *target*, not per file, so
that moving code between files inside a target is not counted as a change.

usage: advisor_r106_semantic_noop_proof.py [OLD_SHA] [NEW_SHA]
"""

import collections
import subprocess
import sys

OLD = sys.argv[1] if len(sys.argv) > 1 else "1bc1c895"
NEW = sys.argv[2] if len(sys.argv) > 2 else "ef055b9b"

# Compiled targets. Harness targets are excluded: they are trusted-harness
# local-iterate code and do not enter the graded binary.
TARGETS = [
    "Sources/MLXFastModel",
    "Sources/MLXFastTransform",
    "Sources/MLXFastCore",
    "Vendor/mlx-swift-lm",
    "Vendor/mlx-swift",
]
CODE_EXT = (".swift", ".c", ".cpp", ".h", ".hpp", ".metal", ".m", ".mm")


def files(sha, prefix):
    p = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", sha, "--", prefix],
        capture_output=True, text=True,
    )
    return [f for f in p.stdout.split() if f.endswith(CODE_EXT)]


def code_lines(sha, path):
    p = subprocess.run(
        ["git", "show", f"{sha}:{path}"], capture_output=True, text=True
    )
    out, in_block = [], False
    for raw in p.stdout.splitlines():
        s = raw.strip()
        if in_block:
            if "*/" in s:
                in_block = False
                s = s.split("*/", 1)[1].strip()
            else:
                continue
        if s.startswith("/*"):
            if "*/" not in s:
                in_block = True
                continue
            s = s.split("*/", 1)[1].strip()
        if not s or s.startswith("//"):
            continue
        out.append(" ".join(s.split()))
    return out


print(f"comparing compiled code lines: {OLD}  ->  {NEW}\n")
verdict = True
for tgt in TARGETS:
    a = collections.Counter()
    b = collections.Counter()
    for f in files(OLD, tgt):
        a.update(code_lines(OLD, f))
    for f in files(NEW, tgt):
        b.update(code_lines(NEW, f))
    only_old = a - b
    only_new = b - a
    tot = sum(a.values())
    ok = not only_old and not only_new
    verdict &= ok
    print(f"{tgt:28s} code lines {tot:7d}   "
          f"only-in-{OLD[:8]}: {sum(only_old.values()):5d}   "
          f"only-in-{NEW[:8]}: {sum(only_new.values()):5d}   "
          f"{'IDENTICAL' if ok else 'DIFFERS'}")
    if not ok:
        for line, n in list(only_old.items())[:12]:
            print(f"      -{n}x  {line[:120]}")
        for line, n in list(only_new.items())[:12]:
            print(f"      +{n}x  {line[:120]}")

print("\nVERDICT:", "SEMANTIC NO-OP across all compiled targets"
      if verdict else "a real code difference exists (see above)")
