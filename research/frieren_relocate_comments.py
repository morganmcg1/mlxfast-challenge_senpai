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
from pathlib import Path


def slug(text):
    return re.sub(r'[^a-z0-9]+', '', text.lower())


def strip_marker(line):
    stripped = line.lstrip()
    for marker in ('/// ', '//! ', '// ', '///', '//!', '//'):
        if stripped.startswith(marker):
            return stripped[len(marker):]
    return stripped


def main():
    spec = json.loads(Path(sys.argv[1]).read_text())
    base_sha = spec['base_sha']
    for entry in spec['files']:
        path = Path(entry['file'])
        note_path = Path('notes') / entry['note']
        lines = path.read_text(encoding='utf-8').split('\n')
        blocks = sorted(entry['blocks'], key=lambda b: b['start'])

        sections = []
        for b in blocks:
            body = lines[b['start'] - 1:b['end']]
            sections.append((b, [strip_marker(l) for l in body]))

        moved = 0
        added = 0
        for b in reversed(blocks):
            start, end = b['start'] - 1, b['end']
            block = lines[start:end]
            moved += sum(len(l.encode('utf-8')) + 1 for l in block)
            replacement = []
            if b.get('pointer'):
                indent = block[0][:len(block[0]) - len(block[0].lstrip())]
                ptr = f"{indent}// See {note_path.as_posix()}#{slug(b['symbol'])}"
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
        for b, body in sections:
            out.append(f"## `{b['symbol']}`")
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
