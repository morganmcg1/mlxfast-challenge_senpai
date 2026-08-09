#!/usr/bin/env python3
"""Literal-aware comment census / stripper / canonical-hash tool.

Subcommands
  census FILE...            per-file comment byte pool
  canon  FILE... [--naive]  canonical (comment-free) sha256 per file
  strip  FILE...            rewrite in place, removing comment content

Canonicalisation is the safety artifact.  It is deliberately stronger than a
regex: string/char literals are preserved verbatim (so a stripper bug that eats
literal text is *visible* in the hash), and C-family text is line-spliced first
(so deleting a comment line inside a backslash-continued macro is visible too).

Language modes: .swift -> swift, {.c,.h,.cpp,.hpp,.metal} -> c.
"""

import argparse
import bisect
import hashlib
import os
import re
import sys

C_EXT = {".c", ".h", ".cpp", ".hpp", ".cc", ".metal", ".mm", ".m"}
SWIFT_EXT = {".swift"}

# Comment text that carries licensing or toolchain meaning is never removed.
# `/* name = */ arg` is the C++ argument-label idiom, and
# Tests/MLXFastTests/NAXSplitKGEMMTests.swift asserts on it as source-exact text,
# so it is a checked signature marker rather than prose.
PRESERVE = re.compile(
    r"copyright|\(c\)\s*\d{4}|©|SPDX-|licen[sc]e|clang-format|NOLINT|"
    r"swiftlint|swift-format|IWYU|pragma|=\s*\*/\s*$",
    re.IGNORECASE,
)

CODE, COMMENT, LITERAL = "code", "comment", "literal"


def mode_for(path):
    ext = os.path.splitext(path)[1]
    if ext in SWIFT_EXT:
        return "swift"
    if ext in C_EXT:
        return "c"
    raise SystemExit("unsupported extension: " + path)


def segments_c(t):
    """Yield (kind, start, end) over C-family text."""
    n, i = len(t), 0
    while i < n:
        c = t[i]
        if c == "/" and i + 1 < n and t[i + 1] == "/":
            j = i + 2
            while j < n:
                if t[j] == "\\" and t.startswith("\n", j + 1):
                    j += 2  # spliced continuation keeps the comment open
                    continue
                if t[j] == "\\" and t.startswith("\r\n", j + 1):
                    j += 3
                    continue
                if t[j] == "\n":
                    break
                j += 1
            yield COMMENT, i, j
            i = j
        elif c == "/" and i + 1 < n and t[i + 1] == "*":
            j = t.find("*/", i + 2)
            j = n if j < 0 else j + 2
            yield COMMENT, i, j
            i = j
        elif c == "R" and t.startswith('R"', i):
            m = re.compile(r'R"([^ ()\\\t\n]{0,16})\(').match(t, i)
            if m:
                close = ')' + m.group(1) + '"'
                j = t.find(close, m.end())
                j = n if j < 0 else j + len(close)
                yield LITERAL, i, j
                i = j
            else:
                yield CODE, i, i + 1
                i += 1
        elif c in '"\'':
            j = i + 1
            while j < n:
                if t[j] == "\\":
                    j += 2
                    continue
                if t[j] == c:
                    j += 1
                    break
                if t[j] == "\n":  # unterminated; do not run past the line
                    break
                j += 1
            yield LITERAL, i, j
            i = j
        else:
            j = i + 1
            while j < n and not (
                t[j] in '"\''
                or (t[j] == "/" and j + 1 < n and t[j + 1] in "/*")
                or (t[j] == "R" and t.startswith('R"', j))
            ):
                j += 1
            yield CODE, i, j
            i = j


def _swift_string(t, i):
    """Return end index of a Swift string literal starting at i (after hashes)."""
    n = len(t)
    m = re.compile(r"#*").match(t, i)
    hashes = m.group(0)
    j = m.end()
    if not t.startswith('"', j):
        return None
    multi = t.startswith('"""', j)
    delim = '"""' if multi else '"'
    j += len(delim)
    esc = "\\" + hashes
    while j < n:
        if t.startswith(esc, j):
            k = j + len(esc)
            if k < n and t[k] == "(":  # interpolation: scan balanced parens
                depth, k = 1, k + 1
                while k < n and depth:
                    if t[k] in '"#' and (t[k] == '"' or t.startswith('#"', k)):
                        e = _swift_string(t, k)
                        if e:
                            k = e
                            continue
                    depth += (t[k] == "(") - (t[k] == ")")
                    k += 1
                j = k
                continue
            j = k + 1
            continue
        if t.startswith(delim + hashes, j):
            return j + len(delim) + len(hashes)
        if not multi and t[j] == "\n":
            return j
        j += 1
    return n


def segments_swift(t):
    n, i = len(t), 0
    while i < n:
        c = t[i]
        if c == "/" and t.startswith("//", i):
            j = t.find("\n", i)
            j = n if j < 0 else j
            yield COMMENT, i, j
            i = j
        elif c == "/" and t.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if t.startswith("/*", j):
                    depth += 1
                    j += 2
                elif t.startswith("*/", j):
                    depth -= 1
                    j += 2
                else:
                    j += 1
            yield COMMENT, i, j
            i = j
        elif c == '"' or (c == "#" and re.compile(r'#+"').match(t, i)):
            j = _swift_string(t, i)
            yield LITERAL, i, j
            i = j
        else:
            j = i + 1
            while j < n and not (
                t[j] == '"'
                or (t[j] == "/" and j + 1 < n and t[j + 1] in "/*")
                or (t[j] == "#" and re.compile(r'#+"').match(t, j))
            ):
                j += 1
            yield CODE, i, j
            i = j


def segments(text, mode):
    gen = segments_swift if mode == "swift" else segments_c
    return list(gen(text))


def splice(t):
    return t.replace("\\\r\n", "").replace("\\\n", "")


def canonical(text, mode, naive=False):
    """Comment-free canonical form.  Literals verbatim, code whitespace collapsed."""
    if naive:
        stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        stripped = re.sub(r"//[^\n]*", "", stripped)
        lines = [ln.rstrip() for ln in stripped.splitlines()]
        return "\n".join(ln for ln in lines if ln.strip())
    src = splice(text) if mode == "c" else text
    literals, out = [], []
    for kind, a, b in segments(src, mode):
        if kind == COMMENT:
            out.append(" ")  # a comment is exactly one space, per C phase 3
        elif kind == LITERAL:
            out.append("\x01%d\x02" % len(literals))
            literals.append(src[a:b])
        else:
            # Newlines stay newlines: they separate statements and directives.
            out.append(re.sub(r"\s+", lambda m: "\n" if "\n" in m.group(0) else " ",
                              src[a:b]))
    # Segment boundaries can emit adjacent spaces (`x /*c*/,` -> `x` + ` ` + ` `);
    # outside literals only the presence of whitespace is significant, not its run
    # length, in both C and Swift.
    joined = re.sub(r"[ \t]+", " ", "".join(out))
    skeleton = re.sub(r" *\n[ \n]*", "\n", joined).strip()
    return re.sub(r"\x01(\d+)\x02", lambda m: "\x00" + literals[int(m.group(1))] + "\x00",
                  skeleton)


def digest(text, mode, naive=False):
    return hashlib.sha256(canonical(text, mode, naive).encode("utf-8")).hexdigest()


def _line_starts(text):
    starts, pos = [0], 0
    while True:
        pos = text.find("\n", pos)
        if pos < 0:
            break
        pos += 1
        starts.append(pos)
    return starts


def _unsafe_continuation(text, a, b):
    """C-family: comment whose removal would change backslash line splicing."""
    body = text[a:b]
    if re.search(r"\\\s*$", body):
        return True
    ls = text.rfind("\n", 0, a)
    if ls > 0:
        prev = text[text.rfind("\n", 0, ls) + 1: ls]
        if prev.rstrip().endswith("\\"):
            return True
    return False


MARK = "\x00"


def strip_text(text, mode, keep_lines=False):
    """Remove comment content.  Returns (new_text, removed_bytes, skipped).

    With keep_lines, a line left empty by the strip is retained as an empty
    line instead of being deleted.  Swift bakes __FILE__/#line into every
    precondition and fatalError, so preserving the line numbering is what lets
    the compiled object file stay byte-identical across the edit.
    """
    if MARK in text:
        raise SystemExit("source contains NUL; refusing to strip")
    kill, skipped = [], 0
    for kind, a, b in segments(text, mode):
        if kind != COMMENT:
            continue
        if PRESERVE.search(text[a:b]):
            skipped += 1
            continue
        if mode == "c" and _unsafe_continuation(text, a, b):
            skipped += 1
            continue
        kill.append((a, b))

    out, prev = [], 0
    for a, b in kill:
        out.append(text[prev:a])
        # A comment is one space to the compiler: never paste its neighbours.
        glue = a > 0 and b < len(text) and not text[a - 1].isspace() \
            and not text[b].isspace()
        out.append(MARK + " " if glue else MARK)
        prev = b
    out.append(text[prev:])

    lines = []
    for line in "".join(out).split("\n"):
        if MARK not in line:
            lines.append(line)
            continue
        line = line.replace(MARK, "").rstrip()
        if line.strip():
            lines.append(line)  # code survived; keep the tidied line
        elif keep_lines:
            lines.append("")
    new = "\n".join(lines)
    return new, len(text.encode()) - len(new.encode()), skipped


def cmd_census(paths):
    total = 0
    rows = []
    for p in paths:
        mode = mode_for(p)
        t = open(p, encoding="utf-8").read()
        pool = sum(
            len(t[a:b].encode())
            for k, a, b in segments(t, mode)
            if k == COMMENT and not PRESERVE.search(t[a:b])
        )
        size = len(t.encode())
        rows.append((pool, size, p))
        total += pool
    rows.sort(reverse=True)
    for pool, size, p in rows:
        if pool:
            print(f"{pool:8d}  {size:8d}  {100*pool/size:5.1f}%  {p}")
    print(f"TOTAL comment pool: {total} bytes over {len(paths)} files")


def cmd_canon(paths, naive):
    for p in paths:
        t = open(p, encoding="utf-8").read()
        print(f"{digest(t, mode_for(p), naive)}  {p}")


def cmd_strip(paths):
    total = 0
    for p in paths:
        mode = mode_for(p)
        t = open(p, encoding="utf-8").read()
        new, freed, skipped = strip_text(t, mode)
        before, after = digest(t, mode), digest(new, mode)
        if before != after:
            print(f"REFUSED (canonical mismatch): {p}", file=sys.stderr)
            return 1
        if freed:
            open(p, "w", encoding="utf-8").write(new)
        print(f"{freed:8d}  preserved={skipped:3d}  {p}")
        total += freed
    print(f"TOTAL freed: {total} bytes")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["census", "canon", "strip"])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--naive", action="store_true")
    a = ap.parse_args()
    if a.cmd == "census":
        cmd_census(a.paths)
    elif a.cmd == "canon":
        cmd_canon(a.paths, a.naive)
    else:
        sys.exit(cmd_strip(a.paths))


if __name__ == "__main__":
    main()
