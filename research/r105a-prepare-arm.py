#!/usr/bin/env python3
"""Prepare one r105-A ladder rung: set the compiled tile default and the marker.

usage: research/r105a-prepare-arm.py ARM VARIANT "one-line description"

Rewrites exactly two things in the submitted surface:

1. the ``if (s.empty())`` fallback inside ``darkbloom_stage_bm128_variant()``,
   which is the compiled-in default the ranked host will execute; and
2. the inert receipt-marker comment at the end of the same file, which exists
   only so replicate archives are not deduplicated by the service.

It then regenerates the rung's public note. Review ``git diff`` before
committing; a wrong default silently spends an official receipt on the wrong
arm.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGET = ROOT / "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp"
MARKER = "// r105-A ladder receipt marker: "
FUNCTION = "int darkbloom_stage_bm128_variant() {"


def main() -> int:
    arm, variant, desc = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    text = TARGET.read_text()

    start = text.index(FUNCTION)
    end = text.index("\n}\n", start)
    body = text[start:end]
    patched, count = re.subn(
        r"(if \(s\.empty\(\)\) \{\n      return )\d+(;\n    \})",
        rf"\g<1>{variant}\g<2>",
        body,
        count=1,
    )
    if count != 1:
        raise SystemExit("could not locate the compiled tile-selection default")
    text = text[:start] + patched + text[end:]

    text, count = re.subn(rf"{re.escape(MARKER)}\S+", f"{MARKER}{arm}", text, count=1)
    if count != 1:
        raise SystemExit("could not locate the receipt marker comment")
    TARGET.write_text(text)

    subprocess.run(["bash", "research/r105a-make-note.sh", arm, desc], cwd=ROOT, check=True)
    subprocess.run(["git", "--no-pager", "diff", "--", str(TARGET.relative_to(ROOT))], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
