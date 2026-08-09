#!/usr/bin/env python3
"""Verify that the comment-insensitive replicate groups really are inert.

For every pair of commits merged into a group, print every added/removed line
in `Sources/` so a human can confirm the difference is a marker comment that
lives in Swift code (semantically inert) and NOT inside an embedded-MSL string
literal (which would change the emitted Metal and hence the compiled kernel).
"""
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(REPO, "research", "artifacts", "advisor-r103")
SIG = os.path.join(ART, "replicate-sigma.json")


def sh(args):
    return subprocess.run(args, cwd=REPO, capture_output=True, text=True).stdout


def main():
    rep = json.load(open(SIG))
    for g in rep["groups"]:
        if g.get("n_distinct_raw_trees", 1) < 2 or g["n"] < 2:
            continue
        print(f"\n################ digest {g['digest']}  n={g['n']}  "
              f"rawtrees={g['n_distinct_raw_trees']} ################")
        rs = g["receipts"]
        base = rs[0]
        for r in rs[1:]:
            if r["raw_tree"] == base["raw_tree"]:
                continue
            print(f"--- {base['id8']} ({base['sub_sha'][:8]}) vs "
                  f"{r['id8']} ({r['sub_sha'][:8]}) ---")
            d = sh(["git", "diff", "-U0", base["sub_sha"], r["sub_sha"],
                    "--", "Sources"])
            for line in d.splitlines():
                if line.startswith(("+++", "---", "diff ", "index ")):
                    continue
                if line.startswith(("+", "-", "@@")):
                    print("   ", line)


if __name__ == "__main__":
    sys.exit(main())
