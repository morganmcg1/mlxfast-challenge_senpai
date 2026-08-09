#!/usr/bin/env python3
"""Regenerate the rung-1 evidence bundle from BASE_SHA and the working tree.

Emits, into research/nezuko-r99b/:
  canon-before.txt / canon-after.txt  canonical (comment-stripped) digests
  strip-log.txt                        per-file bytes freed, descending
  rung1-comment-strip.patch            reversible diff for the restore script
"""

import hashlib
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nezuko_comment_tool import digest, mode_for  # noqa: E402

BASE_SHA = "ad39bfc6c36c0a8257ee0de1916edafdbf52278e"
OUT = "research/nezuko-r99b"
EXCLUDE_PREFIX = "Vendor/mlx-swift/Source/Cmlx/mlx-generated/"


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def editable_vendor_files():
    import json

    spec = json.load(open("benchmark.json"))["editablePaths"]
    files = []
    for entry in spec:
        if entry.startswith("Sources/"):
            continue
        if os.path.isdir(entry):
            for root, _, names in os.walk(entry):
                files += [os.path.join(root, n) for n in names]
        elif os.path.isfile(entry):
            files.append(entry)
    return sorted(f for f in files if not f.startswith(EXCLUDE_PREFIX))


def main():
    os.makedirs(OUT, exist_ok=True)
    paths = editable_vendor_files()
    before, after, rows, total = [], [], [], 0
    for p in paths:
        mode = mode_for(p)
        old = sh("git", "show", f"{BASE_SHA}:{p}")
        new = open(p, encoding="utf-8").read()
        before.append(f"{digest(old, mode)}  {p}")
        after.append(f"{digest(new, mode)}  {p}")
        freed = len(old.encode()) - len(new.encode())
        rows.append((freed, p))
        total += freed
    open(f"{OUT}/canon-before.txt", "w").write("\n".join(before) + "\n")
    open(f"{OUT}/canon-after.txt", "w").write("\n".join(after) + "\n")

    rows.sort(key=lambda r: (-r[0], r[1]))
    log = [f"{f:8d}  {p}" for f, p in rows]
    log.append(f"TOTAL freed: {total} bytes over {len(paths)} in-scope files")
    log.append(f"files changed: {sum(1 for f, _ in rows if f)}")
    open(f"{OUT}/strip-log.txt", "w").write("\n".join(log) + "\n")

    patch = sh("git", "diff", BASE_SHA, "--", *paths)
    open(f"{OUT}/rung1-comment-strip.patch", "w").write(patch)

    mismatches = [b.split("  ")[1] for b, a in zip(before, after) if b != a]
    print(f"in-scope files: {len(paths)}")
    print(f"canonical digests equal: {len(paths) - len(mismatches)}/{len(paths)}")
    for m in mismatches:
        print(f"  MISMATCH: {m}")
    print(f"TOTAL freed: {total} bytes")
    print(f"patch bytes: {len(patch.encode())}  sha256: {hashlib.sha256(patch.encode()).hexdigest()}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
