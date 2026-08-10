#!/usr/bin/env python3
"""Compare the submitted editable surface of two revisions.

Usage: python3 research/maple-frieren-r106e-surface-compare.py REV [REV ...]
"""
import json
import subprocess
import sys


def editable_paths():
    return json.load(open("benchmark.json"))["editablePaths"]


def surface(rev, paths):
    out = subprocess.run(["git", "ls-tree", "-r", "-l", rev],
                         capture_output=True, text=True, check=True).stdout
    files = {}
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        parts = meta.split()
        if parts[3] == "-":
            continue
        if any(path == e or path.startswith(e.rstrip("/") + "/") for e in paths):
            files[path] = int(parts[3])
    return files


def main():
    paths = editable_paths()
    for rev in sys.argv[1:]:
        files = surface(rev, paths)
        total = sum(files.values())
        biggest = max(files.items(), key=lambda kv: kv[1])
        print(f"{rev}: files={len(files)} bytes={total} "
              f"headroom={3_000_000 - total} "
              f"largest={biggest[0]}={biggest[1]}B "
              f"file_headroom={524_288 - biggest[1]}")


if __name__ == "__main__":
    main()
