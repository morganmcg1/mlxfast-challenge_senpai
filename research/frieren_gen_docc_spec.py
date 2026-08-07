#!/usr/bin/env python3
"""Emit relocation blocks for long DocC bodies, keeping each abstract in place.

For every comment-only block outside a Swift multiline-string literal, the first
`- Parameters:` / `- Returns:` / `- Throws:` / `### <heading>` line starts the
relocatable body. Everything above it -- the abstract and any `* Important:` or
`Note:` caveat -- stays at the declaration.
"""
import json
import re
import sys

from frieren_comment_blocks import blocks

BODY = re.compile(r"^\s*///\s*(- Parameters:|- Returns:|- Throws:|### )")
DECL = re.compile(r"\b(func|var|let|struct|class|enum|protocol|init|case)\b")
DOC = re.compile(r"^\s*///")
BLANK_DOC = re.compile(r"^\s*///\s*$")


def abstract_end(body):
    """Index (within body) of the last line of the leading abstract paragraph."""
    if not DOC.match(body[0]):
        return None
    for k, line in enumerate(body):
        if BLANK_DOC.match(line):
            return k - 1
    return None


def symbol_for(lines, end):
    for j in range(end, min(end + 6, len(lines))):
        s = lines[j].strip()
        if s and DECL.search(s):
            m = re.search(
                r"\b(?:func|var|let|struct|class|enum|protocol)\s+([A-Za-z_]\w*)", s
            )
            if m:
                return m.group(1)
            if s.startswith("init"):
                return "init"
    return f"line{end}"


def main():
    path = sys.argv[1]
    minb = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    mode = sys.argv[3] if len(sys.argv) > 3 else "body"
    bl, lines = blocks(path)
    out = []
    for start, end, body, unsafe in bl:
        if unsafe:
            continue
        hit = None
        if mode == "all":
            hit = start
        elif mode == "abstract":
            ae = abstract_end(body)
            if ae is not None and ae >= 0:
                hit = start + ae + 1
        else:
            for k, line in enumerate(body):
                if BODY.match(line):
                    hit = start + k
                    break
        if hit is None or hit > end:
            continue
        nb = sum(len(lines[i - 1]) + 1 for i in range(hit, end + 1))
        if nb < minb:
            continue
        out.append(
            {
                "start": hit,
                "end": end,
                "symbol": symbol_for(lines, end),
                "bytes": nb,
                "pointer": True,
            }
        )
    total = sum(b["bytes"] for b in out)
    print(json.dumps(out, indent=1))
    print(f"# {len(out)} blocks, {total} bytes", file=sys.stderr)


if __name__ == "__main__":
    main()
