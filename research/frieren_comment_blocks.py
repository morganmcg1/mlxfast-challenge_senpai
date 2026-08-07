#!/usr/bin/env python3
"""List maximal comment-only line blocks in a Swift file with byte sizes.

Blocks inside a Swift multiline-string literal are marked UNSAFE and must never
be relocated: the embedded Metal kernel source there is compiled at runtime.
"""
import re
import sys

COMMENT_ONLY = re.compile(r"^\s*//")


def blocks(path):
    lines = open(path, encoding="utf-8").read().split("\n")
    inside = False
    out = []
    cur = None
    for i, line in enumerate(lines, 1):
        was_inside = inside
        if line.count('"""') % 2 == 1:
            inside = not inside
        is_c = bool(COMMENT_ONLY.match(line)) and not was_inside and not inside
        unsafe = was_inside or inside
        if is_c:
            if cur is None:
                cur = [i, i, [line], unsafe]
            else:
                cur[1] = i
                cur[2].append(line)
        else:
            if cur:
                out.append(cur)
            cur = None
    if cur:
        out.append(cur)
    return out, lines


def main():
    path = sys.argv[1]
    minb = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    bl, lines = blocks(path)
    total = 0
    for start, end, body, unsafe in bl:
        nb = sum(len(x) + 1 for x in body)
        total += nb
        if nb < minb:
            continue
        tag = "UNSAFE" if unsafe else "ok"
        nxt = lines[end].strip()[:90] if end < len(lines) else ""
        print(f"### {start}-{end}  {nb}B  {tag}  next={nxt!r}")
        for x in body:
            print("    " + x.rstrip())
    print(f"\n# {path}: {len(bl)} blocks, {total} comment-only bytes")


if __name__ == "__main__":
    main()
