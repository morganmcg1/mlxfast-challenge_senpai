#!/usr/bin/env python3
"""Census + reachability audit for the vendor comment-relocation byte recovery.

Two modes:

  census   <file>...   comment-byte pool per file, split by marker style, with an
                       explicit count of comment-looking lines that sit inside a
                       Swift `\"\"\"` multi-line literal (those are embedded kernel
                       source, never Swift comments -- see
                       research/frieren_comment_strip_check.sh's precondition).

  reach    <file>...   symbols declared in each file, word-boundary matched
                       against Sources/MLXFastModel/LagunaRuntimeModel.swift, so a
                       "not on the scored path" claim is machine-checked rather
                       than asserted. File-scope declarations are decisive; a
                       member name is only reachable through its owning type and
                       is reported separately because it collides with generic
                       identifiers.

`.git/shallow` grafts this checkout's history, so per-file commit counts are a
meaningless constant here and provenance must come from reachability plus a
campaign-marker grep instead.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCORED = REPO / "Sources/MLXFastModel/LagunaRuntimeModel.swift"

DECL = re.compile(
    r'\b(?:class|struct|enum|protocol|actor|func|var|let|typealias|case|init)'
    r'\s+([A-Za-z_][A-Za-z0-9_]*)'
)
TOP_DECL = re.compile(
    r'^(?:@\w+\s+)*(?:public\s+|internal\s+|package\s+|open\s+|final\s+|private\s+)*'
    r'(class|struct|enum|protocol|actor|typealias|func|extension)\s+'
    r'([A-Za-z_][A-Za-z0-9_]*)'
)
CAMPAIGN = re.compile(r'DARKBLOOM|MLXFast|ranked|deviat|upstream|Laguna', re.I)


def literal_lines(lines):
    """1-based line numbers inside a Swift `\"\"\"` multi-line literal."""
    inside = False
    marked = set()
    for n, line in enumerate(lines, 1):
        if inside:
            marked.add(n)
        if line.count('"""') % 2 == 1:
            inside = not inside
            marked.discard(n)
    return marked


def census(paths):
    tot = {'bytes': 0, 'doc': 0, 'plain': 0, 'inlit': 0, 'campaign': 0}
    print(f"{'file':58s} {'bytes':>8s} {'///B':>8s} {'//B':>7s} "
          f"{'poolB':>8s} {'pool%':>6s} {'inLitB':>7s} {'campL':>6s}")
    for p in paths:
        lines = Path(p).read_text().splitlines(keepends=True)
        unsafe = literal_lines([l.rstrip('\n') for l in lines])
        doc = plain = inlit = camp = 0
        for n, raw in enumerate(lines, 1):
            s = raw.lstrip()
            if not s.startswith('//'):
                continue
            if n in unsafe:
                inlit += len(raw.encode())
                continue
            if s.startswith('///'):
                doc += len(raw.encode())
            else:
                plain += len(raw.encode())
            if CAMPAIGN.search(raw):
                camp += 1
        b = sum(len(l.encode()) for l in lines)
        pool = doc + plain
        rel = Path(p).relative_to(REPO) if Path(p).is_absolute() else p
        print(f"{str(rel):58s} {b:8d} {doc:8d} {plain:7d} {pool:8d} "
              f"{100.0 * pool / b:5.1f}% {inlit:7d} {camp:6d}")
        tot['bytes'] += b
        tot['doc'] += doc
        tot['plain'] += plain
        tot['inlit'] += inlit
        tot['campaign'] += camp
    print(f"{'TOTAL':58s} {tot['bytes']:8d} {tot['doc']:8d} {tot['plain']:7d} "
          f"{tot['doc'] + tot['plain']:8d} "
          f"{100.0 * (tot['doc'] + tot['plain']) / tot['bytes']:5.1f}% "
          f"{tot['inlit']:7d} {tot['campaign']:6d}")


def _match(names, target):
    hits = {}
    for n in sorted(names):
        pat = re.compile(r'\b' + re.escape(n) + r'\b')
        for i, l in enumerate(target, 1):
            if pat.search(l):
                kind = 'COMMENT' if l.lstrip().startswith('//') else 'CODE'
                hits.setdefault(n, []).append((i, kind, l.strip()[:96]))
    return hits


def _report(label, names, hits):
    print(f"  -- {label}: {len(names)} name(s), {len(hits)} matched")
    for n, where in hits.items():
        code = sum(1 for _, k, _ in where if k == 'CODE')
        i, kind, l = where[0]
        print(f"     {n:28s} x{len(where):<3d} code={code:<3d} "
              f"first :{i:<6d} {kind:7s} {l}")
    if not hits:
        print("     (no word-boundary reference from the scored forward pass)")


def reach(paths):
    target = SCORED.read_text().splitlines()
    for p in paths:
        src = Path(p).read_text()
        top, members = set(), set()
        for line in src.splitlines():
            if line.lstrip().startswith('//'):
                continue
            m = TOP_DECL.match(line)
            if m and len(m.group(2)) >= 4:
                top.add(m.group(2))
                continue
            m = DECL.search(line)
            if m and len(m.group(1)) >= 4:
                members.add(m.group(1))
        members -= top
        rel = Path(p).relative_to(REPO) if Path(p).is_absolute() else p
        print(f"===== {rel}")
        _report("file-scope entry points (decisive)", top, _match(top, target))
        _report("members (ambiguous; reachable only via owning type)",
                members, _match(members, target))


if __name__ == '__main__':
    mode, args = sys.argv[1], sys.argv[2:]
    {'census': census, 'reach': reach}[mode](args)
