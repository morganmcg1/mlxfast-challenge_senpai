#!/usr/bin/env python3
"""Twin consistency check for a Metal header and its mlx-generated/*.cpp copy.

For kernel families with an ``mlx-generated/*.cpp`` twin it is that embedded
string, not the ``.h``, that is compiled at runtime. Editing only the header
therefore produces a build that passes every compile, link and static check
while the GPU keeps running the old kernel. Nothing in the build system
notices.

The generator copies the header verbatim into an ``R"preamble( ... )preamble"``
literal, minus a small, fixed set of regions. So the two sides must differ only
*structurally*:

  * a block of generator boilerplate prepended before the header text,
  * a block appended after it,
  * whole-run deletions of ``#include`` lines, and
  * whole-run deletions of ``// PRAGMA-VARIANT`` comment blocks.

Any other difference -- in particular a hunk that both removes and adds lines,
or a deletion of real code -- means the twin is stale. Offsets are not
hardcoded: the classifier reads the diff, so the check keeps working as the
files move around.

Usage: research/nax_twin_check.py [stem ...]        (default: fp_quantized_nax)
"""

import difflib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HDR_DIR = ROOT / "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels"
GEN_DIR = ROOT / "Vendor/mlx-swift/Source/Cmlx/mlx-generated"

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def inner_block(cpp_lines, stem):
    starts = [i for i, l in enumerate(cpp_lines) if 'R"preamble(' in l]
    ends = [i for i, l in enumerate(cpp_lines) if ')preamble";' in l]
    if not starts or not ends:
        raise SystemExit(f"{stem}: no R\"preamble( ... )preamble\" block")
    return cpp_lines[starts[0] + 1 : ends[0]]


def droppable(run):
    """A removed run is structural only if it is entirely one dropped kind."""
    if all(re.match(r"\s*#include\b", l) for l in run):
        return "#include"
    if all(re.match(r"\s*//", l) for l in run) and "PRAGMA-VARIANT" in run[0]:
        return "PRAGMA-VARIANT block"
    return None


def check(stem):
    hdr = HDR_DIR / f"{stem}.h"
    gen = GEN_DIR / f"{stem}.cpp"
    for p in (hdr, gen):
        if not p.exists():
            raise SystemExit(f"missing {p}")

    a = hdr.read_text().splitlines()
    b = inner_block(gen.read_text().splitlines(), stem)
    diff = list(difflib.unified_diff(a, b, lineterm="", n=0))

    structural, content = [], []
    i = 0
    while i < len(diff):
        m = HUNK_RE.match(diff[i])
        if not m:
            i += 1
            continue
        a_start, a_len = int(m.group(1)), int(m.group(2) or 1)
        removed, added = [], []
        i += 1
        while i < len(diff) and not diff[i].startswith("@@"):
            (removed if diff[i].startswith("-") else added).append(diff[i][1:])
            i += 1

        if removed and added:
            content.append((a_start, "replaced content", removed, added))
        elif added and a_start == 0:
            structural.append(f"+{len(added)} generator preamble")
        elif added and a_start >= len(a):
            structural.append(f"+{len(added)} generator trailer")
        elif added:
            content.append((a_start, "inserted content", removed, added))
        else:
            kind = droppable(removed)
            if kind:
                structural.append(f"-{a_len} {kind} at .h:{a_start}")
            else:
                content.append((a_start, "removed content", removed, added))

    print(f"{stem}: .h {len(a)} lines, generated block {len(b)} lines")
    for s in structural:
        print(f"  structural  {s}")
    for a_start, why, removed, added in content:
        print(f"  DIVERGENT   .h:{a_start} {why}")
        for l in removed[:6]:
            print(f"      only in .h  | {l}")
        for l in added[:6]:
            print(f"      only in cpp | {l}")
    return len(content)


if __name__ == "__main__":
    stems = sys.argv[1:] or ["fp_quantized_nax"]
    bad = sum(check(s) for s in stems)
    if bad:
        print(f"\nTWIN CHECK: {bad} divergent hunk(s); the generated copy is stale")
    else:
        print("\nTWIN CHECK: generated copy matches the header")
    sys.exit(1 if bad else 0)
