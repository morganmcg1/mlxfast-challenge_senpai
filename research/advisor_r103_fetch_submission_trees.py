#!/usr/bin/env python3
"""Fetch official submission commits from origin and diff their trees against
local advisor-lineage commits.

Discovery (round 103): submission commits published in the receipt API
(`submissionCommitSha` / `officialMetrics.commit`) are NOT reachable from any
local branch, but `git fetch origin <sha>` succeeds. That makes every measured
receipt's exact source tree materialisable and diffable, which settles the
"which local commit was actually measured?" provenance question directly
instead of by inference.

Usage:
    python3 research/advisor_r103_fetch_submission_trees.py
"""
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "research", "artifacts", "advisor-r103",
                   "submission-tree-provenance.json")

# receipt-id -> (label, official submission commit)
# NOTE: `git fetch origin <sha>` needs the FULL 40-char SHA; an abbreviation
# fails with "couldn't find remote ref".
TARGETS = [
    ("25e1f18e", "rank1-best-cs-2.590559", "4b0e051bf3cd9777bd6d2be64e172c490705f9a5"),
    ("7ce1262d", "ArmR-2.589321", "ef055b9b1956e8056267972308fd7deddd89649d"),
    ("83fd2642", "rank3-2.588750", "5a43d32955a52af95d2480e54f8f57805f2a98ae"),
    ("05dd8bbf", "rank4-2.587191", "e1b6e2be27927ba6efec468c3ea45435e16cc1f0"),
    ("e08d759f", "frontier-2.582286", "bd33883eb89209c9714c8c570e399613ecbaa848"),
    ("59bd72a3", "control-2.575633", "e33efe4e2f381f59d7b7dfb81944f02e11072ced"),
]

# local anchors we want to compare against
ANCHORS = [
    ("30f752df", "believed ArmR tree"),
    ("c6c66344", "control tree"),
    ("74e89d71", "fallback anchor 1"),
    ("6ada66c9", "fallback anchor 2"),
    ("e510bb3d", "fallback anchor 3"),
    ("0f6862d0", "round-103 base"),
]


def sh(args, check=True):
    p = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} -> {p.returncode}\n{p.stderr}")
    return p


def resolve(sha):
    p = sh(["git", "rev-parse", sha + "^{commit}"], check=False)
    if p.returncode != 0:
        return None
    return p.stdout.strip()


def fetch(sha):
    """Try to fetch a loose commit from origin. Returns full sha or None."""
    have = resolve(sha)
    if have:
        return have
    p = sh(["git", "fetch", "--quiet", "origin", sha], check=False)
    if p.returncode != 0:
        return None
    return resolve("FETCH_HEAD")


def tree_of(sha):
    return sh(["git", "rev-parse", sha + "^{tree}"]).stdout.strip()


def diffstat(a, b, pathspec=None):
    args = ["git", "diff", "--numstat", a, b]
    if pathspec:
        args += ["--", pathspec]
    out = sh(args).stdout.strip()
    files, ins, dels = 0, 0, 0
    names = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        files += 1
        names.append(parts[2])
        if parts[0] != "-":
            ins += int(parts[0])
        if parts[1] != "-":
            dels += int(parts[1])
    return {"files": files, "insertions": ins, "deletions": dels, "names": names}


def main():
    report = {"fetched": {}, "anchors": {}, "comparisons": []}

    for sha, label in ANCHORS:
        full = resolve(sha)
        report["anchors"][sha] = {
            "label": label,
            "commit": full,
            "tree": tree_of(full) if full else None,
        }

    resolved = {}
    for rid, label, sub in TARGETS:
        full = fetch(sub)
        report["fetched"][sub] = {
            "receipt": rid,
            "label": label,
            "commit": full,
            "fetched": full is not None,
        }
        if full:
            report["fetched"][sub]["tree"] = tree_of(full)
            subj = sh(["git", "log", "-1", "--format=%H%x09%ct%x09%s", full]).stdout.strip()
            report["fetched"][sub]["log"] = subj
            resolved[sub] = full
        print(f"{sub} ({label}): {'FETCHED ' + full if full else 'NOT FETCHABLE'}")

    # cross diff every fetched submission tree against every anchor
    for sub, full in resolved.items():
        st = tree_of(full)
        for sha, label in ANCHORS:
            a = resolve(sha)
            if not a:
                continue
            at = tree_of(a)
            identical = at == st
            row = {
                "submission": sub,
                "anchor": sha,
                "anchor_label": label,
                "identical_tree": identical,
            }
            if not identical:
                row["all"] = diffstat(a, full)
                row["sources"] = diffstat(a, full, "Sources")
            report["comparisons"].append(row)
            mark = "IDENTICAL" if identical else (
                f"{row['sources']['files']} Sources files, "
                f"+{row['sources']['insertions']}/-{row['sources']['deletions']}")
            print(f"  vs {sha} ({label}): {mark}")

    # pairwise between fetched submissions
    subs = list(resolved.items())
    report["pairwise"] = []
    for i in range(len(subs)):
        for j in range(i + 1, len(subs)):
            a, b = subs[i][1], subs[j][1]
            row = {
                "a": subs[i][0], "b": subs[j][0],
                "identical_tree": tree_of(a) == tree_of(b),
            }
            if not row["identical_tree"]:
                row["sources"] = diffstat(a, b, "Sources")
            report["pairwise"].append(row)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    sys.exit(main())
