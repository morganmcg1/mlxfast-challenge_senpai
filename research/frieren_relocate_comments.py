#!/usr/bin/env python3
"""Mechanically relocate comment blocks out of byte-capped submitted Swift files.

Reads a JSON spec of {file, note, blocks:[{start,end,symbol,pointer}]}, moves each
1-based inclusive line range verbatim into the companion markdown note, deletes it
from the source, and optionally leaves a single `// See notes/<note>#<slug>` pointer
at the original indentation.

Ranges are applied bottom-up per file so earlier line numbers stay valid. The
prose is copied byte-for-byte with only the leading comment marker stripped; this
tool never rewrites wording.

Verify the result with research/frieren_comment_strip_check.sh.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path


def slug(text):
    return re.sub(r'[^a-z0-9]+', '', text.lower())


def anchors(blocks):
    """Per-block (heading, anchor) pairs, disambiguated within one file.

    Two comment blocks can document the same declaration. A bare duplicate
    heading gives both the same slug, so every pointer to it would silently
    resolve to the first section; the `(L<start>)` suffix keeps the markdown
    anchor GitHub generates and the slug this tool writes in agreement.
    """
    dup = {s for s, n in Counter(b['symbol'] for b in blocks).items() if n > 1}
    return [(f"## `{b['symbol']}` (L{b['start']})", f"{slug(b['symbol'])}-l{b['start']}")
            if b['symbol'] in dup else (f"## `{b['symbol']}`", slug(b['symbol']))
            for b in blocks]


def pointer_text(first_line, note_rel, anchor):
    """The `// See notes/...` line left behind in place of a relocated block.

    Shared with the planners so a projected byte count cannot drift from the
    applied one. A `//` pointer dropped into a `///` run would detach the kept
    abstract from its declaration, so the block's own marker is mirrored.
    """
    indent = first_line[:len(first_line) - len(first_line.lstrip())]
    marker = '///' if first_line.lstrip().startswith('///') else '//'
    return f"{indent}{marker} See {note_rel}#{anchor}"


def strip_marker(line):
    stripped = line.lstrip()
    for marker in ('/// ', '//! ', '// ', '///', '//!', '//'):
        if stripped.startswith(marker):
            return stripped[len(marker):]
    return stripped


COMMENT_ONLY = re.compile(r'^\s*//')


def literal_lines(lines):
    """1-based line numbers sitting inside a Swift `\"\"\"` multi-line literal.

    A `//` line inside such a literal is embedded Metal/kernel source, not a Swift
    comment, so relocating it would change the program. An odd count of delimiters
    on a line toggles literal state.
    """
    inside = False
    marked = set()
    for n, line in enumerate(lines, 1):
        if inside:
            marked.add(n)
        if line.count('"""') % 2 == 1:
            inside = not inside
            marked.discard(n)
    return marked


def validate(path, lines, blocks):
    unsafe = literal_lines(lines)
    claimed = set()
    for b in blocks:
        if not 1 <= b['start'] <= b['end'] <= len(lines):
            sys.exit(f"FAIL {path}: block {b} out of range (file has {len(lines)} lines)")
        span = set(range(b['start'], b['end'] + 1))
        if span & claimed:
            sys.exit(f"FAIL {path}: block {b} overlaps an earlier block")
        claimed |= span
        for n in sorted(span):
            if not COMMENT_ONLY.match(lines[n - 1]):
                sys.exit(f"FAIL {path}:{n} is not a comment-only line: {lines[n - 1]!r}")
            if n in unsafe:
                sys.exit(f"FAIL {path}:{n} sits inside a \"\"\" literal; relocating it "
                         f"would change embedded source")


def main():
    spec = json.loads(Path(sys.argv[1]).read_text())
    base_sha = spec['base_sha']
    for entry in spec['files']:
        path = Path(entry['file'])
        note_path = Path('notes') / entry['note']
        lines = path.read_text(encoding='utf-8').split('\n')
        blocks = sorted(entry['blocks'], key=lambda b: b['start'])
        validate(entry['file'], lines, blocks)
        heads = anchors(blocks)

        sections = []
        for b, (heading, _) in zip(blocks, heads):
            body = lines[b['start'] - 1:b['end']]
            sections.append((b, heading, [strip_marker(l) for l in body]))

        moved = 0
        added = 0
        for b, (_, anchor) in reversed(list(zip(blocks, heads))):
            start, end = b['start'] - 1, b['end']
            block = lines[start:end]
            moved += sum(len(l.encode('utf-8')) + 1 for l in block)
            replacement = []
            if b.get('pointer'):
                ptr = pointer_text(block[0], note_path.as_posix(), anchor)
                replacement = [ptr]
                added += len(ptr.encode('utf-8')) + 1
            lines[start:end] = replacement

        path.write_text('\n'.join(lines), encoding='utf-8')

        out = [
            f"# Relocated commentary — `{path.name}`",
            "",
            f"Measurement narrative and design history moved verbatim out of `{entry['file']}`",
            "to free bytes on the capped editable submission surface. Line numbers refer to",
            f"the file as it stood at base `{base_sha[:8]}`. Nothing here is compiled or",
            "submitted, and the code is unchanged (see",
            "`research/frieren_comment_strip_check.sh`).",
            "",
        ]
        for b, heading, body in sections:
            out.append(heading)
            out.append("")
            out.append(f"_relocated from lines {b['start']}-{b['end']} at base {base_sha[:8]}_")
            out.append("")
            out.extend(body)
            out.append("")
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text('\n'.join(out).rstrip('\n') + '\n', encoding='utf-8')
        print(f"{entry['file']}: {len(blocks)} blocks, moved {moved} B, "
              f"added {added} B of pointers, net {moved - added} B -> {note_path}")


if __name__ == '__main__':
    main()
