#!/usr/bin/env python3
"""Reconcile editable-surface byte totals across commits.

`senpai/check-editable-budget.sh` reports `current`/`headroom` from the WORKING
TREE (find + wc -c, which also counts untracked and ignored files under an
editable directory) while `growth` compares against the BASE_SHA git tree. So
two agents on the same base can print different headroom whenever their working
trees differ. This script computes the committed total for any commit so a
reported headroom can be attributed to an exact tree.
"""

import json
import subprocess
import sys

MAX_TOTAL = 3_000_000
MAX_FILE = 524_288
MAX_GROWTH = 262_144


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout


def committed_total(sha: str) -> tuple[int, int]:
    contract = json.loads(git("show", f"{sha}:benchmark.json"))
    files: set[str] = set()
    for path in contract["editablePaths"]:
        listing = git("ls-tree", "-r", "--name-only", "-z", sha, "--", path)
        files.update(entry for entry in listing.split("\0") if entry)
    total = 0
    for name in sorted(files):
        total += int(git("cat-file", "-s", f"{sha}:{name}").strip())
    return total, len(files)


def editable_files(sha: str) -> dict[str, int]:
    contract = json.loads(git("show", f"{sha}:benchmark.json"))
    names: set[str] = set()
    for path in contract["editablePaths"]:
        listing = git("ls-tree", "-r", "--name-only", "-z", sha, "--", path)
        names.update(entry for entry in listing.split("\0") if entry)
    return {n: int(git("cat-file", "-s", f"{sha}:{n}").strip()) for n in sorted(names)}


def audit(base: str, ref: str) -> bool:
    """Static submission-surface audit of one arm branch against the base.

    Every cap is checked from committed trees, because the working-tree headroom
    that `senpai/check-editable-budget.sh` prints depends on whatever untracked
    files happen to be present and so cannot be attributed to an arm.
    """
    base_sha = git("rev-parse", "--verify", f"{base}^{{commit}}").strip()
    sha = git("rev-parse", "--verify", f"{ref}^{{commit}}").strip()
    base_files = editable_files(base_sha)
    ref_files = editable_files(sha)
    base_total, total = sum(base_files.values()), sum(ref_files.values())

    changed = [
        n
        for n in sorted(set(base_files) | set(ref_files))
        if base_files.get(n) != ref_files.get(n)
    ]
    diff = [
        p
        for p in git("diff", "--name-only", f"{base_sha}..{sha}").split("\n")
        if p
    ]
    outside = [p for p in diff if p not in ref_files and p not in base_files]

    ok = True
    print(f"=== {ref}  {sha[:8]}  vs base {base_sha[:8]}")
    print(f"  total={total} headroom={MAX_TOTAL - total} files={len(ref_files)}")
    growth = total - base_total
    verdict = "OK" if growth <= MAX_GROWTH else "OVER"
    ok &= growth <= MAX_GROWTH
    print(f"  growth={growth} cap={MAX_GROWTH} {verdict}")
    print(f"  submitted files changed: {len(changed)}")
    for n in changed:
        was, now = base_files.get(n, 0), ref_files.get(n, 0)
        flag = "OK" if now <= MAX_FILE else "OVER-PER-FILE-CAP"
        if now > MAX_FILE:
            ok = False
        print(
            f"    {n}  {was} -> {now} ({now - was:+d})  "
            f"per-file headroom={MAX_FILE - now}  {flag}"
        )
    print(f"  non-submitted paths touched: {len(outside)}")
    for p in outside:
        print(f"    (research-only) {p}")
    if not changed:
        print("  VERDICT: EMPTY SUBMITTED SURFACE -- nothing to integrate")
        ok = False
    return ok


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--audit":
        if len(args) < 3:
            print("usage: --audit BASE REF [REF...]", file=sys.stderr)
            return 2
        results = [audit(args[1], ref) for ref in args[2:]]
        return 0 if all(results) else 1
    for ref in args:
        sha = git("rev-parse", "--verify", f"{ref}^{{commit}}").strip()
        total, count = committed_total(sha)
        print(
            f"{ref:<44} {sha[:8]} total={total} headroom={MAX_TOTAL - total} "
            f"files={count}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
