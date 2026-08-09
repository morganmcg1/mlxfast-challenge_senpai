#!/usr/bin/env python3
"""Compare two dumps of JIT-compiled Metal source, keyed by library name.

Corpora are produced by the research-only MLX_NEZUKO_MSL_DUMP instrumentation in
Device::get_library (Vendor/mlx-swift/.../metal/device.cpp), which is the single
caller of build_library_ and therefore sees every JIT-compiled Metal source a
process compiles. Comparing two corpora byte-for-byte answers the only question
that matters for a comment-relocation edit: did any character that the Metal
compiler actually sees change?

Exit status is 0 only when the two corpora have identical library-name sets and
every library's source bytes are identical.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def digest_corpus(root: Path) -> dict[str, tuple[str, int, bytes]]:
    entries: dict[str, tuple[str, int, bytes]] = {}
    for path in sorted(root.glob("*.metal")):
        data = path.read_bytes()
        entries[path.name] = (hashlib.sha256(data).hexdigest(), len(data), data)
    return entries


def first_difference(left: bytes, right: bytes) -> int:
    limit = min(len(left), len(right))
    for index in range(limit):
        if left[index] != right[index]:
            return index
    return limit


def context(data: bytes, offset: int, width: int = 90) -> str:
    start = max(0, offset - width // 2)
    chunk = data[start : start + width]
    return chunk.decode("utf-8", errors="replace").replace("\n", "\\n")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: nezuko_msl_corpus_diff.py BEFORE_DIR AFTER_DIR", file=sys.stderr)
        return 2

    before_root, after_root = Path(argv[1]), Path(argv[2])
    before, after = digest_corpus(before_root), digest_corpus(after_root)

    print(f"before: {len(before)} libraries  {sum(v[1] for v in before.values())} bytes")
    print(f"after:  {len(after)} libraries  {sum(v[1] for v in after.values())} bytes")

    only_before = sorted(set(before) - set(after))
    only_after = sorted(set(after) - set(before))
    shared = sorted(set(before) & set(after))

    failures = 0
    for name in only_before:
        print(f"MISSING-IN-AFTER  {name}  ({before[name][1]} bytes)")
        failures += 1
    for name in only_after:
        print(f"MISSING-IN-BEFORE {name}  ({after[name][1]} bytes)")
        failures += 1

    for name in shared:
        before_hash, before_len, before_data = before[name]
        after_hash, after_len, after_data = after[name]
        if before_hash == after_hash:
            continue
        failures += 1
        offset = first_difference(before_data, after_data)
        print(f"DIFFERS {name}")
        print(f"  before sha256={before_hash} bytes={before_len}")
        print(f"  after  sha256={after_hash} bytes={after_len}")
        print(f"  first differing byte offset={offset}")
        print(f"  before context: {context(before_data, offset)}")
        print(f"  after  context: {context(after_data, offset)}")

    if failures:
        print(f"RESULT: FAIL ({failures} library mismatches)")
        return 1

    combined_before = hashlib.sha256()
    combined_after = hashlib.sha256()
    for name in shared:
        combined_before.update(name.encode() + before[name][2])
        combined_after.update(name.encode() + after[name][2])
    print(f"corpus digest before: {combined_before.hexdigest()}")
    print(f"corpus digest after:  {combined_after.hexdigest()}")
    print(f"RESULT: PASS ({len(shared)} libraries byte-identical)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
