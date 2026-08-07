#!/usr/bin/env python3
"""Census comment-only bytes across the editable submission surface.

Splits each file's comment-only bytes into two buckets:

  outside  — comment-only lines at Swift statement scope. Safe to relocate.
  inside   — comment-only lines sitting inside a `\"\"\"` multi-line string literal.
             These are embedded Metal/kernel source, NOT Swift comments, so
             relocating them would change the program.

An odd number of `\"\"\"` on a line toggles literal state. `blockCommentMarkers`
counts `/*` occurrences: this tool does not model block comments, so a non-zero
count is a caveat on that file's `outside` figure.

Usage:
  research/frieren_comment_census.py                  # whole editable surface
  research/frieren_comment_census.py PATH [PATH ...]  # named files
"""

import json
import subprocess
import sys
from pathlib import Path


def is_comment(line):
    return line.lstrip().startswith('//')


def census(path):
    lines = Path(path).read_text(encoding='utf-8', errors='replace').split('\n')
    inside = False
    out_b = out_n = in_b = in_n = 0
    for line in lines:
        toggles = line.count('"""') % 2 == 1
        if is_comment(line) and not toggles:
            nbytes = len(line.encode('utf-8')) + 1
            if inside:
                in_b += nbytes
                in_n += 1
            else:
                out_b += nbytes
                out_n += 1
        if toggles:
            inside = not inside
    total = sum(len(l.encode('utf-8')) + 1 for l in lines) - 1
    return {
        'path': str(path), 'total': total,
        'outsideBytes': out_b, 'outsideLines': out_n,
        'insideBytes': in_b, 'insideLines': in_n,
        'tripleQuotes': sum(l.count('"""') for l in lines),
        'blockCommentMarkers': sum(l.count('/*') for l in lines),
    }


def editable_paths():
    spec = json.loads(Path('benchmark.json').read_text())
    files = []
    for entry in spec['editablePaths']:
        p = Path(entry)
        if p.is_dir():
            files += [f for f in sorted(p.rglob('*')) if f.is_file()]
        elif p.is_file():
            files.append(p)
    return files


def main():
    targets = [Path(a) for a in sys.argv[1:]] or editable_paths()
    rows = [census(p) for p in targets if p.suffix in {'.swift', '.metal', '.cpp', '.h'}]
    rows.sort(key=lambda r: -r['outsideBytes'])

    surface = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True,
                             text=True).stdout.strip()
    print(f"comment census at HEAD={surface[:12]}  files={len(rows)}")
    print(f"{'outsideB':>9} {'outsideL':>8} {'insideB':>8} {'totalB':>8} {'\"\"\"':>4} "
          f"{'/*':>3}  path")
    for r in rows:
        if r['outsideBytes'] == 0 and r['insideBytes'] == 0:
            continue
        print(f"{r['outsideBytes']:>9} {r['outsideLines']:>8} {r['insideBytes']:>8} "
              f"{r['total']:>8} {r['tripleQuotes']:>4} {r['blockCommentMarkers']:>3}  "
              f"{r['path']}")
    print(f"\nTOTAL outside={sum(r['outsideBytes'] for r in rows)} "
          f"inside={sum(r['insideBytes'] for r in rows)} "
          f"surface={sum(r['total'] for r in rows)}")


if __name__ == '__main__':
    main()
