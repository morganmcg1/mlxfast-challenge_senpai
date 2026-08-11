#!/usr/bin/env python3
"""fern R109-F: how much of the integration branch's diff against fork main is
comment/whitespace, and how much is real code?

Motivation: `git diff --shortstat 1bc1c895 HEAD -- Sources Vendor` reports
+2382/-5213, which reads like "our branch dropped 5213 lines of fork main's
optimisations".  But `git log` shows one of the removing commits is

    f720e9e7  r99-B rung 1: reclaim 176,468 editable bytes from vendored
              comment content

i.e. a deliberate comment-stripping pass done to buy editable-byte budget.
Comments do not reach the compiler, so any line we removed that was a comment
cannot explain a decode regression.  This script splits every +/- line of the
diff into CODE vs COMMENT/BLANK so the regression claim can be scoped to the
lines that actually compile.

Usage:
    python3 research/fern_r109f_comment_fraction.py BASE_SHA HEAD_SHA [-- paths...]
"""

from __future__ import annotations

import collections
import re
import subprocess
import sys

# A line is "non-code" if, on its own, it contributes nothing to the compiler:
# pure whitespace, a // line comment, a /* ... */ opener/closer, or a line that
# is only continuation prose inside a block comment (leading '*').
_BLANK = re.compile(r"^\s*$")
_LINE_COMMENT = re.compile(r"^\s*//")
_BLOCK_ONLY = re.compile(r"^\s*/\*.*\*/\s*$")
_BLOCK_OPEN = re.compile(r"^\s*/\*")
_BLOCK_CONT = re.compile(r"^\s*\*")
_BLOCK_CLOSE = re.compile(r"^\s*\*/\s*$")
_DOC = re.compile(r"^\s*(///|#\s*$)")


def classify(line: str) -> str:
    """Return 'blank', 'comment', or 'code' for a single source line."""
    if _BLANK.match(line):
        return "blank"
    if _LINE_COMMENT.match(line) or _DOC.match(line):
        return "comment"
    if _BLOCK_ONLY.match(line) or _BLOCK_CLOSE.match(line):
        return "comment"
    if _BLOCK_OPEN.match(line) or _BLOCK_CONT.match(line):
        return "comment"
    return "code"


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) < 2:
        print(__doc__)
        return 2
    base, head = argv[0], argv[1]
    paths = argv[2:]
    if paths and paths[0] == "--":
        paths = paths[1:]
    if not paths:
        paths = ["Sources", "Vendor"]

    cmd = ["git", "diff", "--no-color", "-U0", base, head, "--"] + paths
    diff = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout

    # per-file counters: added/removed x code/comment/blank
    per_file: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    cur = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:]
            per_file[cur]  # touch
            continue
        if line.startswith("--- ") or line.startswith("+++ "):
            continue
        if line.startswith("diff --git") or line.startswith("@@"):
            continue
        if line.startswith("index ") or line.startswith("similarity "):
            continue
        if cur is None:
            continue
        if line.startswith("+"):
            per_file[cur]["add_" + classify(line[1:])] += 1
        elif line.startswith("-"):
            per_file[cur]["del_" + classify(line[1:])] += 1

    tot = collections.Counter()
    rows = []
    for f, c in per_file.items():
        for k, v in c.items():
            tot[k] += v
        code_churn = c["add_code"] + c["del_code"]
        rows.append((code_churn, f, c))
    rows.sort(reverse=True)

    print("=" * 100)
    print("fern R109-F: CODE vs COMMENT/BLANK split of the integration diff")
    print(f"  base = {base}")
    print(f"  head = {head}")
    print(f"  paths = {' '.join(paths)}")
    print("=" * 100)
    print()
    hdr = "%-62s %7s %7s | %7s %7s" % (
        "file",
        "+code",
        "-code",
        "+cmnt",
        "-cmnt",
    )
    print(hdr)
    print("-" * len(hdr))
    for code_churn, f, c in rows:
        short = f if len(f) <= 62 else "..." + f[-59:]
        print(
            "%-62s %7d %7d | %7d %7d"
            % (
                short,
                c["add_code"],
                c["del_code"],
                c["add_comment"] + c["add_blank"],
                c["del_comment"] + c["del_blank"],
            )
        )
    print("-" * len(hdr))
    add_code, del_code = tot["add_code"], tot["del_code"]
    add_non = tot["add_comment"] + tot["add_blank"]
    del_non = tot["del_comment"] + tot["del_blank"]
    print(
        "%-62s %7d %7d | %7d %7d"
        % ("TOTAL", add_code, del_code, add_non, del_non)
    )
    print()
    tot_add = add_code + add_non
    tot_del = del_code + del_non
    print(f"raw diff              : +{tot_add} / -{tot_del}")
    print(f"code-only diff        : +{add_code} / -{del_code}")
    print(f"comment/blank-only    : +{add_non} / -{del_non}")
    if tot_del:
        print(
            f"share of DELETIONS that are comment/blank: "
            f"{100.0 * del_non / tot_del:.1f}%"
        )
    if tot_add:
        print(
            f"share of INSERTIONS that are comment/blank: "
            f"{100.0 * add_non / tot_add:.1f}%"
        )
    print()
    print("Interpretation: only the code-only columns can move decode time.")
    print("Files with -code >> +code are places where the integration branch")
    print("genuinely dropped fork-main code and are the regression suspects.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
