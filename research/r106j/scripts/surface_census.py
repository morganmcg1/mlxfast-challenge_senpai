#!/usr/bin/env python3
"""Rule 75 census of the submitted surface.

Emits sha256 + byte count for every file reachable from benchmark.json's
editablePaths at HEAD, the total against the 3,000,000 B cap, the largest file
against the 524,288 B cap, and growth against a reference commit's own surface
(the 262,144 B per-review growth cap).

Reads git object state only; never touches the working tree.
"""

import hashlib
import json
import subprocess
import sys

TOTAL_CAP = 3_000_000
FILE_CAP = 524_288
GROWTH_CAP = 262_144


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout


def editable_paths(rev: str) -> list[str]:
    return json.loads(git("show", f"{rev}:benchmark.json"))["editablePaths"]


def surface(rev: str) -> dict[str, tuple[str, int]]:
    """Map path -> (sha256, bytes) for every file under rev's editablePaths."""
    paths = editable_paths(rev)
    prefixes = [p.rstrip("/") for p in paths]
    out: dict[str, tuple[str, int]] = {}
    for line in git("ls-tree", "-r", "-z", rev).split("\0"):
        if not line:
            continue
        meta, path = line.split("\t", 1)
        mode, otype, oid = meta.split()
        if otype != "blob":
            continue
        if not any(path == p or path.startswith(p + "/") for p in prefixes):
            continue
        blob = subprocess.run(
            ["git", "cat-file", "blob", oid], capture_output=True, check=True
        ).stdout
        out[path] = (hashlib.sha256(blob).hexdigest(), len(blob))
    return out


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else None
    head = git("rev-parse", "HEAD").strip()

    head_surface = surface("HEAD")
    for path in sorted(head_surface):
        digest, nbytes = head_surface[path]
        print(f"{digest}  {nbytes:>7}  {path}")

    total = sum(n for _, n in head_surface.values())
    biggest = max(head_surface.items(), key=lambda kv: kv[1][1])
    print()
    print(f"head_commit          {head}")
    print(f"surface_files        {len(head_surface)}")
    print(
        f"surface_bytes        {total}   cap {TOTAL_CAP}   "
        f"headroom {TOTAL_CAP - total}   {'PASS' if total <= TOTAL_CAP else 'FAIL'}"
    )
    print(
        f"largest_file_bytes   {biggest[1][1]}   cap {FILE_CAP}   "
        f"headroom {FILE_CAP - biggest[1][1]}   "
        f"{'PASS' if biggest[1][1] <= FILE_CAP else 'FAIL'}   {biggest[0]}"
    )

    if base is None:
        return 0

    base_surface = surface(base)
    base_total = sum(n for _, n in base_surface.values())
    growth = total - base_total
    print()
    print(f"base_commit          {base}")
    print(f"base_surface_files   {len(base_surface)}")
    print(f"base_surface_bytes   {base_total}")
    print(
        f"growth               {growth}   cap {GROWTH_CAP}   "
        f"{'PASS' if growth <= GROWTH_CAP else 'FAIL'}"
    )

    changed = sorted(
        p
        for p in set(head_surface) | set(base_surface)
        if head_surface.get(p) != base_surface.get(p)
    )
    print()
    print(f"changed_vs_base      {len(changed)} file(s)")
    for path in changed:
        b = base_surface.get(path)
        h = head_surface.get(path)
        if b is None:
            print(f"  ADD  {h[0]}  {h[1]:>7}  {path}")
        elif h is None:
            print(f"  DEL  {b[0]}  {b[1]:>7}  {path}")
        else:
            print(f"  MOD  {h[0]}  {h[1]:>7}  (was {b[1]}, {h[1] - b[1]:+d})  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
