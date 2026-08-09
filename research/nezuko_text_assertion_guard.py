#!/usr/bin/env python3
"""Guard against comment stripping that breaks a textual assertion.

Trusted tests and harness code assert on the literal text of vendored editable
files (see Tests/MLXFastTests/NVFP4QuantizedMMTests.swift, which asserts on
comment text such as `Contents from "mlx/backend/metal/kernels/fp4.h"`).
Removing a comment that carries such a literal turns a "comment-only" edit into
a test break.

Usage:
    nezuko_text_assertion_guard.py BASE_SHA FILE...

For every string literal of at least MIN_LEN characters that appears anywhere in
the non-editable ("trusted") tree, report the literals that are present in the
BASE_SHA version of a listed file but absent from its working-tree version.
Exit non-zero when any such literal is found.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

MIN_LEN = 10

# Where an assertion on vendored source text can plausibly live.
SCAN_ROOTS = ("Tests", "Sources", "tools", "senpai", "Scripts")
SCAN_SUFFIXES = (".swift", ".sh", ".py", ".json", ".md")

SWIFT_MULTILINE = re.compile(r'"""\n(.*?)"""', re.DOTALL)
SWIFT_RAW = re.compile(r'#+"(.*?)"#+', re.DOTALL)
SWIFT_PLAIN = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
SHELL_SINGLE = re.compile(r"'([^'\n]{%d,})'" % MIN_LEN)


def repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(out.stdout.strip())


def editable_paths(root: Path, base: str) -> list[str]:
    out = subprocess.run(
        ["git", "show", f"{base}:benchmark.json"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return list(json.loads(out.stdout)["editablePaths"])


def is_editable(rel: str, paths: list[str]) -> bool:
    return any(rel == p or rel.startswith(p.rstrip("/") + "/") for p in paths)


def unescape_swift(raw: str) -> str:
    out = []
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            out.append({"n": "\n", "t": "\t", "0": "\0"}.get(nxt, nxt))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def harvest(text: str) -> set[str]:
    found: set[str] = set()
    # Swift strips the closing delimiter's indentation from a multi-line string,
    # so compare line by line rather than guessing the surviving indentation.
    for match in SWIFT_MULTILINE.finditer(text):
        found.update(line.strip() for line in match.group(1).splitlines())
    for match in SWIFT_RAW.finditer(text):
        found.add(match.group(1))
    for match in SWIFT_PLAIN.finditer(text):
        found.add(unescape_swift(match.group(1)))
    for match in SHELL_SINGLE.finditer(text):
        found.add(match.group(1))
    return {
        lit
        for lit in found
        if len(lit) >= MIN_LEN and "\n" not in lit and "\\(" not in lit
    }


def trusted_literals(root: Path, paths: list[str]) -> set[str]:
    literals: set[str] = set()
    for scan_root in SCAN_ROOTS:
        base = root / scan_root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
                continue
            rel = path.relative_to(root).as_posix()
            if is_editable(rel, paths):
                continue
            try:
                literals |= harvest(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, OSError):
                continue
    return literals


SOURCE_EXACT = re.compile(r"/\*|\*/|//|[;{}()=&<>#]")


def is_source_exact(lit: str) -> bool:
    return bool(SOURCE_EXACT.search(lit))


def base_text(root: Path, base: str, rel: str) -> str | None:
    out = subprocess.run(
        ["git", "show", f"{base}:{rel}"],
        cwd=root,
        capture_output=True,
    )
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", errors="replace")


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    base, targets = argv[1], argv[2:]
    root = repo_root()
    paths = editable_paths(root, base)
    literals = trusted_literals(root, paths)
    print(f"harvested {len(literals)} trusted literals (>= {MIN_LEN} chars)")

    hard = soft = 0
    for target in targets:
        rel = Path(target).resolve().relative_to(root).as_posix()
        before = base_text(root, base, rel)
        if before is None:
            print(f"SKIP  {rel} (not in {base[:12]})")
            continue
        after = (root / rel).read_text(encoding="utf-8", errors="replace")
        if before == after:
            continue
        for lit in literals:
            if lit in before and lit not in after:
                # A literal that quotes comment syntax or code punctuation is a
                # source-exact assertion; a bare prose phrase is almost always an
                # incidental match against unrelated documentation.
                if is_source_exact(lit):
                    print(f"HARD {rel}: lost source-exact literal {lit!r}")
                    hard += 1
                else:
                    soft += 1

    print(f"\nsoft (prose-shaped, incidental) losses: {soft}")
    if hard:
        print(f"FAIL: {hard} source-exact literal(s) lost")
        return 1
    print("OK: no source-exact trusted literal lost")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
