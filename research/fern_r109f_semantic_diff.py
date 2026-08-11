#!/usr/bin/env python3
"""fern R109-F: the *semantic* diff between two trees, with comments and
whitespace normalised away.

Why this exists
---------------
`git diff --shortstat 1bc1c895 HEAD -- Sources Vendor` says +2382/-5213, which
invites the reading "the integration branch dropped 5000 lines of fork main's
optimisations".  Two layers of illusion sit on top of that number:

  1. Commit f720e9e7 ("r99-B rung 1: reclaim 176,468 editable bytes from
     vendored comment content") deliberately stripped comment blocks out of
     vendored sources to buy editable-byte budget.  Comments never reach the
     compiler.
  2. Even a line-level "is this line a comment" filter over-counts, because the
     same pass also removed *inline* comments from otherwise-unchanged code
     lines, e.g.
         int64_t C_batch_stride /* = 0*/,   ->   int64_t C_batch_stride ,
         }  // namespace                    ->   }
     Those lines look like code churn to a line classifier but are semantically
     identical.

This script therefore lexes each file, deletes comments, normalises whitespace,
drops blank lines, and only then diffs.  What survives is the set of lines that
can actually change the emitted machine code.

Usage:
    python3 research/fern_r109f_semantic_diff.py BASE_SHA HEAD_SHA [paths...]
    python3 research/fern_r109f_semantic_diff.py BASE HEAD --show FILE
"""

from __future__ import annotations

import difflib
import subprocess
import sys


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout


def strip_comments(text: str) -> list[str]:
    """Remove // line comments and /* */ block comments, collapse whitespace.

    Handles string and char literals so that a "//" inside a literal is kept.
    Good enough for C/C++/Metal/Swift sources in this tree.
    """
    out: list[str] = []
    i, n = 0, len(text)
    buf: list[str] = []
    state = "code"  # code | line_comment | block_comment | dquote | squote
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state == "code":
            if c == "/" and nxt == "/":
                state = "line_comment"
                i += 2
                continue
            if c == "/" and nxt == "*":
                state = "block_comment"
                i += 2
                # a block comment acts as a token separator
                buf.append(" ")
                continue
            if c == '"':
                state = "dquote"
                buf.append(c)
                i += 1
                continue
            if c == "'":
                state = "squote"
                buf.append(c)
                i += 1
                continue
            if c == "\n":
                out.append("".join(buf))
                buf = []
                i += 1
                continue
            buf.append(c)
            i += 1
            continue
        if state == "line_comment":
            if c == "\n":
                state = "code"
                out.append("".join(buf))
                buf = []
            i += 1
            continue
        if state == "block_comment":
            if c == "*" and nxt == "/":
                state = "code"
                i += 2
                continue
            if c == "\n":
                # keep line structure so line numbers stay roughly meaningful
                out.append("".join(buf))
                buf = []
            i += 1
            continue
        if state in ("dquote", "squote"):
            buf.append(c)
            if c == "\\":
                if nxt:
                    buf.append(nxt)
                    i += 2
                    continue
            elif (state == "dquote" and c == '"') or (
                state == "squote" and c == "'"
            ):
                # closing quote only if it is not the opening one we just added
                if len(buf) >= 2:
                    state = "code"
            i += 1
            continue
    out.append("".join(buf))
    # normalise whitespace, drop blanks
    norm = []
    for line in out:
        s = " ".join(line.split())
        if s:
            norm.append(s)
    return norm


def blob(sha: str, path: str) -> str:
    try:
        return git("show", f"{sha}:{path}")
    except subprocess.CalledProcessError:
        return ""


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) < 2:
        print(__doc__)
        return 2
    base, head = argv[0], argv[1]
    rest = argv[2:]
    show = None
    if "--show" in rest:
        k = rest.index("--show")
        show = rest[k + 1]
        rest = rest[:k]
    paths = rest or ["Sources", "Vendor"]

    changed = [
        p
        for p in git(
            "diff", "--name-only", base, head, "--", *paths
        ).splitlines()
        if p.strip()
    ]

    if show:
        a = strip_comments(blob(base, show))
        b = strip_comments(blob(head, show))
        print(f"=== semantic diff of {show} ===")
        print(f"    {base} -> {head}")
        any_line = False
        for line in difflib.unified_diff(
            a, b, fromfile=f"{base}:{show}", tofile=f"{head}:{show}", lineterm="",
            n=3,
        ):
            any_line = True
            print(line)
        if not any_line:
            print("    (no semantic change: comments/whitespace only)")
        return 0

    rows = []
    for p in changed:
        a = strip_comments(blob(base, p))
        b = strip_comments(blob(head, p))
        sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        add = dele = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "replace":
                dele += i2 - i1
                add += j2 - j1
            elif tag == "delete":
                dele += i2 - i1
            elif tag == "insert":
                add += j2 - j1
        raw = git("diff", "--numstat", base, head, "--", p).split()
        raw_add, raw_del = (
            (int(raw[0]), int(raw[1])) if len(raw) >= 2 and raw[0] != "-" else (0, 0)
        )
        rows.append((add + dele, p, add, dele, raw_add, raw_del))

    rows.sort(reverse=True)
    print("=" * 104)
    print("fern R109-F: SEMANTIC diff (comments + whitespace normalised away)")
    print(f"  base = {base}")
    print(f"  head = {head}")
    print("=" * 104)
    hdr = "%-58s %6s %6s | %7s %7s" % ("file", "+sem", "-sem", "+raw", "-raw")
    print(hdr)
    print("-" * len(hdr))
    tot = [0, 0, 0, 0]
    nz = 0
    for churn, p, add, dele, raw_add, raw_del in rows:
        tot[0] += add
        tot[1] += dele
        tot[2] += raw_add
        tot[3] += raw_del
        if churn:
            nz += 1
        short = p if len(p) <= 58 else "..." + p[-55:]
        flag = "" if churn else "   <- comments only"
        print(
            "%-58s %6d %6d | %7d %7d%s"
            % (short, add, dele, raw_add, raw_del, flag)
        )
    print("-" * len(hdr))
    print("%-58s %6d %6d | %7d %7d" % ("TOTAL", tot[0], tot[1], tot[2], tot[3]))
    print()
    print(f"files touched          : {len(rows)}")
    print(f"files with real change : {nz}")
    print(f"raw line churn         : +{tot[2]} / -{tot[3]}")
    print(f"semantic line churn    : +{tot[0]} / -{tot[1]}")
    if tot[2] + tot[3]:
        print(
            "semantic share of churn: "
            f"{100.0 * (tot[0] + tot[1]) / (tot[2] + tot[3]):.1f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
