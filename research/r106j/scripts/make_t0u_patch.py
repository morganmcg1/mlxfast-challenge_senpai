#!/usr/bin/env python3
"""Isolate the unroll-depth hunks of the T0->T1 contrast into a standalone patch.

Reads the two blobs from git objects only; never touches the worktree. Emits a
`git apply -p1`-able patch on stdout plus the sha256/byte guard for the arm.
"""
import hashlib
import re
import subprocess
import sys

BASE = "446fe9875d1f95b1216628b5809a99da844e5c79"
T1 = "4b0e051bf3cd9777bd6d2be64e172c490705f9a5"
PATH = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
KEEP_OLD_STARTS = {1636, 1740}


def blob(rev):
    return subprocess.run(
        ["git", "show", f"{rev}:{PATH}"], check=True, capture_output=True
    ).stdout.decode()


def hunks(diff_text):
    out, cur = [], None
    for line in diff_text.splitlines(True):
        m = re.match(r"^@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@", line)
        if m:
            cur = {"old_start": int(m.group(1)), "body": []}
            out.append(cur)
        elif cur is not None and line[:1] in (" ", "-", "+", "\\"):
            cur["body"].append(line)
    return out


def main():
    base_lines = blob(BASE).splitlines(True)
    diff_text = subprocess.run(
        ["git", "diff", "-U3", BASE, T1, "--", PATH], check=True, capture_output=True
    ).stdout.decode()

    selected = [h for h in hunks(diff_text) if h["old_start"] in KEEP_OLD_STARTS]
    if len(selected) != len(KEEP_OLD_STARTS):
        sys.exit(f"expected {len(KEEP_OLD_STARTS)} hunks, matched {len(selected)}")

    out, cursor = [], 0
    for h in sorted(selected, key=lambda x: x["old_start"]):
        start = h["old_start"] - 1
        if start < cursor:
            sys.exit("selected hunks overlap")
        out.extend(base_lines[cursor:start])
        cursor = start
        for line in h["body"]:
            tag, text = line[0], line[1:]
            if tag == "\\":
                continue
            if tag in " -":
                if base_lines[cursor] != text:
                    sys.exit(f"context mismatch at old line {cursor + 1}")
                cursor += 1
            if tag in " +":
                out.append(text)
    out.extend(base_lines[cursor:])

    new_text = "".join(out)
    sys.stderr.write(
        "T0U %s sha256=%s bytes=%d\n"
        % (PATH, hashlib.sha256(new_text.encode()).hexdigest(), len(new_text.encode()))
    )

    import difflib

    sys.stdout.writelines(
        difflib.unified_diff(
            base_lines, out, fromfile="a/" + PATH, tofile="b/" + PATH, n=3
        )
    )


if __name__ == "__main__":
    main()
