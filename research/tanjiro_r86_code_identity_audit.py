#!/usr/bin/env python3
"""Independent verification that the files kept from our tree during the
organizer-frontier adoption are code-identical to the frontier's copies.

The advisor's method was a comment-stripped MD5. This uses two different
methods and, crucially, *diffs* rather than hashes, so any real difference is
named rather than merely detected:

  method A: a Swift-aware lexer that drops comments and normalises whitespace,
            then a line diff of the surviving code;
  method B: a token-stream comparison built from the same lexer output but
            reduced to identifiers, numbers and operator glyphs, which is
            insensitive to line breaking and indentation entirely.

A file passes only when both methods report no difference.
"""

import subprocess
import sys
import difflib

OURS = "HEAD"
FRONTIER = "c5b0a13"

FILES = [
    "Sources/MLXFastModel/LagunaConfig.swift",
    "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/BaseConfiguration.swift",
    "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/BatchKVCache.swift",
    "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/CompilableKVCache.swift",
    "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/CompilableRotatingKVCache.swift",
    "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/CompiledDecode.swift",
    "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/Evaluate.swift",
    "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift",
]


def blob(ref, path):
    return subprocess.run(
        ["git", "show", f"{ref}:{path}"], capture_output=True, text=True, check=True
    ).stdout


def strip_comments(src):
    """Swift-aware comment stripper.

    Handles // line comments, /* */ block comments (nested, as Swift allows),
    ordinary string literals with escapes, multiline \"\"\" literals, and raw
    string literals with # delimiters, so that comment glyphs inside strings
    survive and string content is never mistaken for a comment.
    """
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "#":
            j = i
            while j < n and src[j] == "#":
                j += 1
            if j < n and src[j] == '"':
                close = '"' + "#" * (j - i)
                end = src.find(close, j + 1)
                end = n if end < 0 else end + len(close)
                out.append(src[i:end])
                i = end
                continue
            out.append(c)
            i += 1
            continue
        if src.startswith('"""', i):
            end = src.find('"""', i + 3)
            end = n if end < 0 else end + 3
            out.append(src[i:end])
            i = end
            continue
        if c == '"':
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == '"':
                    j += 1
                    break
                j += 1
            out.append(src[i:j])
            i = j
            continue
        if src.startswith("//", i):
            end = src.find("\n", i)
            i = n if end < 0 else end
            continue
        if src.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if src.startswith("/*", j):
                    depth += 1
                    j += 2
                elif src.startswith("*/", j):
                    depth -= 1
                    j += 2
                else:
                    j += 1
            out.append(" ")
            i = j
            continue
        out.append(c)
        i += 1
    return "".join(out)


def code_lines(src):
    lines = []
    for raw in strip_comments(src).splitlines():
        s = " ".join(raw.split())
        if s:
            lines.append(s)
    return lines


def tokens(src):
    text = strip_comments(src)
    toks, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            toks.append(text[i:j])
            i = j
            continue
        if c.isdigit():
            j = i
            while j < n and (text[j].isalnum() or text[j] in "._"):
                j += 1
            toks.append(text[i:j])
            i = j
            continue
        toks.append(c)
        i += 1
    return toks


SELF_TESTS = [
    ('let a = 1 // drop\nlet b = 2\n', ["let a = 1", "let b = 2"]),
    ('let s = "keeps // this"\n', ['let s = "keeps // this"']),
    ('let s = #"raw // and /* this */"#\n', ['let s = #"raw // and /* this */"#']),
    ('/* outer /* inner */ still */ let x = 1\n', ["let x = 1"]),
    ('#if DEBUG\nlet d = 1\n#endif\n', ["#if DEBUG", "let d = 1", "#endif"]),
    ('let m = """\n// not a comment\n"""\n', ['let m = """', "// not a comment", '"""']),
    ('let q = a / b // div\n', ["let q = a / b"]),
]


def self_test():
    for src, want in SELF_TESTS:
        got = code_lines(src)
        if got != want:
            print(f"LEXER_SELFTEST=FAIL src={src!r} want={want!r} got={got!r}")
            return False
    print(f"LEXER_SELFTEST=PASS cases={len(SELF_TESTS)}")
    return True


def raw_diff_lines(a, b):
    """Differing lines before any comment stripping."""
    la, lb = a.splitlines(), b.splitlines()
    return [
        line[1:]
        for line in difflib.unified_diff(la, lb, lineterm="", n=0)
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]


def classify(line):
    """Method C: per-line classification, independent of the whole-file lexer.

    Only decides whether a single differing line is unambiguously non-code.
    Anything it cannot prove is comment or blank is reported as 'other'.
    """
    s = line.strip()
    if not s:
        return "blank"
    if s.startswith("//"):
        return "comment"
    if s.startswith(("/*", "*/", "*")):
        return "comment"
    return "other"


def main():
    if not self_test():
        return 2
    failures = []
    print(
        f"\n{'file':<34} {'raw-diff':>8} {'code-lines':>17} {'tokens':>13}  verdict"
    )
    total_raw = 0
    other = []
    for path in FILES:
        a, b = blob(OURS, path), blob(FRONTIER, path)
        la, lb = code_lines(a), code_lines(b)
        ta, tb = tokens(a), tokens(b)
        raw = raw_diff_lines(a, b)
        total_raw += len(raw)
        other += [(path, s) for s in raw if classify(s) == "other"]
        ok = la == lb and ta == tb
        name = path.split("/")[-1]
        print(
            f"{name:<34} {len(raw):>8} {len(la):>8}/{len(lb):<8} "
            f"{len(ta):>6}/{len(tb):<6}  {'IDENTICAL' if ok else 'DIFFERS'}"
        )
        if not ok:
            failures.append(path)
            for line in list(
                difflib.unified_diff(la, lb, "ours", "frontier", lineterm="", n=1)
            )[:40]:
                print("    " + line)
    print()
    print(f"raw_line_diffs_total={total_raw}")
    print(f"method_c_unproven_lines={len(other)}")
    for path, s in other[:30]:
        print(f"    {path.split('/')[-1]}: {s.strip()[:100]}")
    if failures:
        print("CODE_IDENTITY=FAIL differing=" + ",".join(failures))
        return 1
    print(
        f"CODE_IDENTITY=PASS files={len(FILES)} "
        "methods=code-line-diff,token-diff,per-line-classification"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
