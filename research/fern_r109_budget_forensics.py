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


def main() -> int:
    for ref in sys.argv[1:]:
        sha = git("rev-parse", "--verify", f"{ref}^{{commit}}").strip()
        total, count = committed_total(sha)
        print(
            f"{ref:<44} {sha[:8]} total={total} headroom={MAX_TOTAL - total} "
            f"files={count}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
