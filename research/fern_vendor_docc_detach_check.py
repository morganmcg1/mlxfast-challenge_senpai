#!/usr/bin/env python3
"""Fail if a relocation pointer detached a DocC abstract.

Swift attaches a `///` run to the following declaration only when the run is
contiguous. A `//` line spliced into that run truncates the abstract silently,
so every comment run that both mixes marker styles and immediately precedes a
declaration is reported.

Usage: fern_vendor_docc_detach_check.py [PATH ...]
PATH is repo-relative (or absolute, so a scratch relocation copy can be checked).
With no argument the five Part A MLXLMCommon files are used.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VENDOR = "Vendor/mlx-swift-lm/Libraries/MLXLMCommon"
DEFAULT_FILES = [
    f"{VENDOR}/BatchKVCache.swift",
    f"{VENDOR}/CompilableRotatingKVCache.swift",
    f"{VENDOR}/CompiledDecode.swift",
    f"{VENDOR}/CompilableKVCache.swift",
    f"{VENDOR}/BaseConfiguration.swift",
]
# Repo-relative paths, so the check runs on any relocation target rather than
# only Part A's five vendor files.
FILES = sys.argv[1:] or DEFAULT_FILES
DECL = re.compile(
    r"^\s*(@\w+\s+)*(public|internal|private|fileprivate|open|final|static|"
    r"nonisolated|override)?\s*(func|var|let|class|struct|enum|case|init|"
    r"subscript|protocol|extension|typealias)\b"
)

bad = 0
for rel in FILES:
    lines = (REPO / rel).read_text().splitlines()
    i = 0
    while i < len(lines):
        if not lines[i].lstrip().startswith("//"):
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].lstrip().startswith("//"):
            j += 1
        run = lines[i:j]
        styles = {"///" if x.lstrip().startswith("///") else "//" for x in run}
        follows_decl = j < len(lines) and DECL.match(lines[j])
        if len(styles) > 1 and follows_decl:
            print(f"DETACH-RISK {rel}:{i + 1}-{j} -> {lines[j].strip()[:70]}")
            for k, x in enumerate(run):
                print(f"    {i + 1 + k:5d}| {x}")
            bad += 1
        i = j

print(f"\nmixed-style runs preceding a declaration: {bad}")
sys.exit(1 if bad else 0)
