#!/usr/bin/env python3
"""Relocate comment prose out of a submitted file into a research sidecar.

Rung 2 of maple-r99-b-comment-byte-reclamation removes comment content from
Sources/ files that count against the per-file editable cap. The assignment
requires that DARKBLOOM_* flag documentation and receipt provenance survive the
edit verbatim rather than being deleted, so this tool writes every removed
comment block, in source order and byte-for-byte, to a Markdown sidecar under
research/ before the strip runs.

    nezuko_relocate_tool.py plan  FILE SIDECAR    # write sidecar, do not edit
    nezuko_relocate_tool.py apply FILE SIDECAR    # write sidecar, then strip

Blocks are runs of comment segments separated only by whitespace. A block is
tagged when it mentions a DARKBLOOM_ flag or receipt provenance so the sidecar
can be searched for the classes the assignment calls out by name.

The strip reuses nezuko_comment_tool.strip_text, which refuses to write any
file whose canonical (comment-stripped, literal-preserving) digest changes, so
relocation cannot alter compiled behaviour.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nezuko_comment_tool import (  # noqa: E402
    COMMENT,
    PRESERVE,
    digest,
    mode_for,
    segments,
    strip_text,
)

TAGS = (
    ("darkbloom-flag", re.compile(r"DARKBLOOM_[A-Z0-9_]+")),
    ("receipt-provenance", re.compile(r"receipt", re.I)),
)


def blocks(text, mode):
    """Yield (start, end) spans of consecutive removable comment segments."""
    spans = [
        (a, b)
        for k, a, b in segments(text, mode)
        if k == COMMENT and not PRESERVE.search(text[a:b])
    ]
    out = []
    for a, b in spans:
        if out and not text[out[-1][1] : a].strip():
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    # Widen each block over the blanks that separate it from the line start or
    # from preceding code.  A merged block already carries the indentation of
    # its later lines, so this is what makes the record exactly reversible.
    widened = []
    for a, b in out:
        start = a
        while start > 0 and text[start - 1] in " \t":
            start -= 1
        widened.append((start, b))
    return widened


def write_sidecar(path, sidecar, text, mode):
    starts = [0]
    for ch in text:
        starts.append(starts[-1] + (1 if ch == "\n" else 0))
    spans = blocks(text, mode)
    tagged = {name: 0 for name, _ in TAGS}
    body = [
        f"# Relocated comment prose from `{path}`",
        "",
        "Every comment block removed from the submitted file, verbatim and in",
        "source order. The strip preserves line numbering, so these labels are",
        "line numbers in both the pre-strip and the post-strip file. Verify and",
        "reverse the edit with `research/nezuko_r103c_relocation_verify.py`.",
        "",
        f"Blocks: {len(spans)}.",
        "",
    ]
    for a, b in spans:
        chunk = text[a:b]
        names = [n for n, rx in TAGS if rx.search(chunk)]
        for n in names:
            tagged[n] += 1
        lo, hi = starts[a] + 1, starts[min(b, len(text) - 1)] + 1
        label = f"L{lo}" if lo == hi else f"L{lo}-L{hi}"
        tag = f" — {', '.join(names)}" if names else ""
        body += [f"## {label}{tag}", "", "```swift", chunk.rstrip("\n"), "```", ""]
    body.insert(
        6,
        "Tagged blocks: "
        + ", ".join(f"{n}={tagged[n]}" for n, _ in TAGS)
        + ".",
    )
    os.makedirs(os.path.dirname(sidecar) or ".", exist_ok=True)
    open(sidecar, "w", encoding="utf-8").write("\n".join(body))
    return spans, tagged


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ("plan", "apply"):
        print(__doc__, file=sys.stderr)
        return 2
    cmd, path, sidecar = sys.argv[1:]
    mode = mode_for(path)
    text = open(path, encoding="utf-8").read()
    spans, tagged = write_sidecar(path, sidecar, text, mode)
    pool = sum(len(text[a:b].encode()) for a, b in spans)
    print(f"{path}: {len(spans)} blocks, {pool} bytes of comment prose")
    print("  tagged: " + ", ".join(f"{n}={tagged[n]}" for n, _ in TAGS))
    print(f"  sidecar: {sidecar} ({os.path.getsize(sidecar)} bytes)")
    if cmd == "plan":
        return 0
    new, freed, skipped = strip_text(text, mode, keep_lines=True)
    if digest(text, mode) != digest(new, mode):
        print(f"REFUSED (canonical mismatch): {path}", file=sys.stderr)
        return 1
    if new.count("\n") != text.count("\n"):
        print(f"REFUSED (line count changed): {path}", file=sys.stderr)
        return 1
    open(path, "w", encoding="utf-8").write(new)
    print(f"  stripped: freed={freed} bytes, preserved={skipped} comments")
    print(f"  size: {len(text.encode())} -> {len(new.encode())} bytes")
    print(f"  lines: {text.count(chr(10))} (unchanged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
