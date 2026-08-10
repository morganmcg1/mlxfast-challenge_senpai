#!/usr/bin/env python3
"""Multiset line-content diff between the T0 and T1 MLXFastModel trees.

A pure code move shows up as a huge textual diff but a zero multiset
difference, so this separates "moved between files" from "genuinely changed".
"""
import collections
import os
import subprocess
import sys

T0 = os.environ.get("TCD_A", "446fe987")
T1 = os.environ.get("TCD_B", "4b0e051b")
PATHS = ("Sources/MLXFastModel", "Sources/MLXFastTransform")


def files(sha):
    out = subprocess.run(["git", "ls-tree", "-r", "--name-only", sha, "--", *PATHS],
                         capture_output=True, text=True).stdout.split()
    return [f for f in out if f.endswith(".swift")]


def lines(sha):
    c = collections.Counter()
    for f in files(sha):
        txt = subprocess.run(["git", "show", f"{sha}:{f}"],
                             capture_output=True, text=True).stdout
        for ln in txt.splitlines():
            s = ln.strip()
            if s and not s.startswith("//"):
                c[s] += 1
    return c


def top(c, n):
    for s, k in c.most_common(n):
        print(f"   x{k:<3d} {s[:150]}")


def main():
    global PATHS
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    if len(sys.argv) > 2:
        PATHS = tuple(sys.argv[2:])
    print("paths:", " ".join(PATHS))
    c0, c1 = lines(T0), lines(T1)
    print(f"T0={T0} non-comment lines {sum(c0.values())} ({len(files(T0))} files)")
    print(f"T1={T1} non-comment lines {sum(c1.values())} ({len(files(T1))} files)")
    gone, new = c0 - c1, c1 - c0
    print(f"multiset: T0-only {sum(gone.values())}  T1-only {sum(new.values())}")
    print("\n### content present in T0 but nowhere in T1:")
    top(gone, n)
    print("\n### content present in T1 but nowhere in T0:")
    top(new, n)


if __name__ == "__main__":
    main()
