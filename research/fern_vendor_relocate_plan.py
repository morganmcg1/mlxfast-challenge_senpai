#!/usr/bin/env python3
"""Emit research/fern_vendor_relocate_spec.json for the vendor byte-recovery pass.

The five in-scope MLXLMCommon files are unreachable from the scored forward pass
(`fern_vendor_byte_census.py reach` shows zero file-scope references), so their
comment pool is pure documentation weight on a capped submission surface. This
tool decides, per comment block, how many leading lines stay at the declaration
and what moves verbatim into notes/.

Policy, applied uniformly and reported per block so the diff is auditable:

  HARD KEEP (whole block, never split)
    - copyright headers
    - `MARK:` separators
    - any block naming a `DARKBLOOM_*` flag: those are live runtime contracts
    - any block carrying an upstream-provenance or must-match pin

  ABSTRACT KEEP (default)
    Keep the leading sentence -- leading lines up to and including the first one
    ending in `.`/`!`/`?`, stopping early at a blank comment line or a DocC
    section marker, and never more than ABSTRACT_MAX_LINES. The remainder moves.

  The remainder only moves when it clears MIN_RELOCATE_BYTES, otherwise the cost
  of the note section exceeds the recovery. A `// See notes/...` pointer is only
  added above POINTER_MIN_BYTES, matching research/frieren_build_relocate_spec.py.

  SPLIT_OVERRIDE re-opens three large HARD_KEEP blocks. Each is a file banner or
  DocC block where the pinned text (port provenance, a `DARKBLOOM_*` contract) is
  a handful of lines wrapped around a much longer design narrative, so keeping the
  whole block would forfeit most of the file's recoverable bytes. The kept and
  moved sub-ranges are hand-audited and listed individually for review.

Run from the research/ directory. Verify with fern_comment_strip_check output.
"""

import json
import re
import sys
from pathlib import Path

from frieren_comment_blocks import blocks

REPO = Path(__file__).resolve().parents[1]
BASE = "63ab67c888e1892086b7b5b623de4dd0ebe68c90"
VENDOR = "Vendor/mlx-swift-lm/Libraries/MLXLMCommon"

ABSTRACT_MAX_LINES = 3
MIN_RELOCATE_BYTES = 30
POINTER_MIN_BYTES = 500

# (file, block start) -> relocatable sub-ranges inside an otherwise HARD_KEEP block.
# CompilableKVCache:1-31   keeps 1-6 (title, port provenance, the "only traceable
#                          full-attention cache" pin) and 27-31 (the Darkbloom
#                          UNWIRED wiring contract); 7-26 is design narrative.
# CompilableRotatingKVCache:1-22 keeps 1-4 (title, port provenance); 5-22 restates
#                          the DocC block at 28-43 and is redundant in-file.
# CompiledDecode:149-167   keeps 149-160, which carries the
#                          `DARKBLOOM_COMPILED_DECODE=1` precondition list; 161-167
#                          is the DocC parameter/return body.
SPLIT_OVERRIDE = {
    ("CompilableKVCache.swift", 1): [(7, 26, "CompilableKVCache", True)],
    ("CompilableRotatingKVCache.swift", 1): [(5, 22, "CompilableRotatingKVCache", True)],
    ("CompiledDecode.swift", 149): [(161, 167, "setup", False)],
}

FILES = [
    ("BatchKVCache.swift", "MLXLMCommon-BatchKVCache.notes.md"),
    ("CompilableRotatingKVCache.swift", "MLXLMCommon-CompilableRotatingKVCache.notes.md"),
    ("CompiledDecode.swift", "MLXLMCommon-CompiledDecode.notes.md"),
    ("CompilableKVCache.swift", "MLXLMCommon-CompilableKVCache.notes.md"),
    ("BaseConfiguration.swift", "MLXLMCommon-BaseConfiguration.notes.md"),
]

HARD_KEEP = re.compile(
    r"DARKBLOOM_"
    r"|Copyright"
    r"|MARK:"
    r"|must match"
    r"|Ported from"
    r"|upstream",
    re.I,
)
SECTION = re.compile(r"^\s*//[/!]?\s*(?:-\s*(?:Parameters?|Returns?|Throws):|###\s|\d\.\s)")
BLANK_C = re.compile(r"^\s*//[/!]?\s*$")
SENTENCE_END = re.compile(r"[.!?][)`\"']?\s*$")
DECL = re.compile(
    r"\b(?:func|var|let|struct|class|enum|protocol|actor|extension|typealias|case)"
    r"\s+([A-Za-z_]\w*)"
)


def symbol_for(lines, end):
    """Nearest declaration below the block; falls back to a line-anchored name."""
    for j in range(end, min(end + 6, len(lines))):
        s = lines[j].strip()
        if not s or s.startswith("//"):
            continue
        m = DECL.search(s)
        if m:
            return m.group(1)
        if s.startswith("init"):
            return "init"
        break
    return f"line{end}"


def keep_count(body):
    """Number of leading lines that stay: the block's opening sentence."""
    for k, line in enumerate(body):
        if k and (BLANK_C.match(line) or SECTION.match(line)):
            return k
        if SENTENCE_END.search(line):
            return k + 1
        if k + 1 >= ABSTRACT_MAX_LINES:
            return k + 1
    return len(body)


def plan(name, rel, lines, bl):
    out, kept, moved, hard = [], 0, 0, 0
    for start, end, body, unsafe in bl:
        nb = sum(len(x) + 1 for x in body)
        if unsafe:
            sys.exit(f"FAIL {rel}:{start}-{end} sits inside a \"\"\" literal")
        text = "\n".join(body)
        if HARD_KEEP.search(text):
            override = SPLIT_OVERRIDE.get((name, start))
            if override:
                for s, e, sym, ptr in override:
                    if not start <= s <= e <= end:
                        sys.exit(f"FAIL {rel}: override {s}-{e} escapes block "
                                 f"{start}-{end}")
                    rb = sum(len(lines[i - 1]) + 1 for i in range(s, e + 1))
                    out.append({"start": s, "end": e, "symbol": sym,
                                "pointer": ptr})
                    moved += rb
                    nb -= rb
            kept += nb
            hard += nb
            continue
        k = keep_count(body)
        rest = body[k:]
        rb = sum(len(x) + 1 for x in rest)
        if not rest or rb < MIN_RELOCATE_BYTES:
            kept += nb
            continue
        out.append({
            "start": start + k,
            "end": end,
            "symbol": symbol_for(lines, end),
            "pointer": rb >= POINTER_MIN_BYTES,
        })
        kept += nb - rb
        moved += rb
    return out, kept, moved, hard


def main():
    spec = {"base_sha": BASE, "files": []}
    tm = tk = th = 0
    print(f"{'file':44s} {'blocks':>7s} {'mv':>5s} {'movedB':>8s} "
          f"{'keptB':>7s} {'hardB':>7s}")
    for name, note in FILES:
        rel = f"{VENDOR}/{name}"
        bl, lines = blocks(REPO / rel)
        entries, kept, moved, hard = plan(name, rel, lines, bl)
        entries.sort(key=lambda b: b["start"])
        spec["files"].append({"file": rel, "note": note, "blocks": entries})
        print(f"{name:44s} {len(bl):7d} {len(entries):5d} {moved:8d} "
              f"{kept:7d} {hard:7d}")
        tm += moved
        tk += kept
        th += hard
    print(f"{'TOTAL':44s} {'':7s} {'':5s} {tm:8d} {tk:7d} {th:7d}")
    target = REPO / "research" / "fern_vendor_relocate_spec.json"
    target.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target.relative_to(REPO)}")


if __name__ == "__main__":
    main()
