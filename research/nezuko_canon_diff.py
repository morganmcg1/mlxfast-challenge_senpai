#!/usr/bin/env python3
"""Show where the canonical form of a file diverges after comment stripping."""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nezuko_comment_tool as T  # noqa: E402


def main(argv: list[str]) -> int:
    path = Path(argv[1])
    text = path.read_text(encoding="utf-8")
    mode = T.mode_for(path)
    stripped, _freed, _kept = T.strip_text(text, mode)
    before = T.canonical(text, mode)
    after = T.canonical(stripped, mode)
    if before == after:
        print("canonical forms match")
        return 0
    a = before.replace("\x00", "\u2400").splitlines()
    b = after.replace("\x00", "\u2400").splitlines()
    shown = 0
    for line in difflib.unified_diff(a, b, "before", "after", n=1, lineterm=""):
        print(line[:300])
        shown += 1
        if shown > 60:
            print("... truncated")
            break
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
