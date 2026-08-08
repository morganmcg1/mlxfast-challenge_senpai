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
    - any block carrying a rule idiom (campaign rule 29, see RULE_IDIOM)
    - any block whose *following declaration* carries one of those markers: the
      flag docs above `lagunaFusedSharedSwiGLUQMVEnabled` and friends name no
      `DARKBLOOM_` symbol in the prose, only in the `let` two lines below.

  ABSTRACT KEEP (default)
    Keep the leading sentence -- leading lines up to and including the first one
    ending in `.`/`!`/`?`, stopping early at a blank comment line or a DocC
    section marker. The scan never cuts mid-sentence; ABSTRACT_HARD_LINES only
    bounds a block that has no sentence end at all. The remainder moves.

  The remainder only moves when it clears MIN_RELOCATE_BYTES and when the block
  still nets bytes after its pointer, otherwise the cost of the note section
  exceeds the recovery. A `// See notes/...` pointer is added above
  POINTER_MIN_BYTES and unconditionally for any rule-bearing block.

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

ABSTRACT_HARD_LINES = 3
MIN_RELOCATE_BYTES = 30
POINTER_MIN_BYTES = 120
DECL_LOOKAHEAD = 6

# fern_vendor_relocate_spec.json was planned and applied under a 500-character
# threshold. Lowering the live value to 120 UTF-8 bytes is a Part B policy fix;
# `plan()` keeps the frozen number so --regenerate still reproduces the artifact
# that was actually applied instead of silently re-deciding 28 of its 54 blocks.
POINTER_MIN_BYTES_APPLIED = 500


def nbytes(line):
    """UTF-8 size of one source line including its newline.

    The per-file and total caps in benchmark.json are byte caps, so a comment
    holding a non-ASCII character costs more than its character count; counting
    characters here reported a projection the applier could not reproduce.
    """
    return len(line.encode("utf-8")) + 1

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

# Campaign rule 29. A keep policy that only recognises `must match` misses every
# other way a bit-exactness pin is written in this tree. The capitalised idioms
# are matched literally because a case-insensitive `\bMUST\b` would swallow every
# ordinary "must" in narrative prose; the lowercase phrases are matched either way.
RULE_IDIOM_CS = re.compile(r"\bMUST\b|NOT knobs|Exactness")
RULE_IDIOM_CI = re.compile(
    r"must be|must not|must match|load-bearing|bit-(?:identical|exact)"
    r"|keep .* in sync|pin(?:s|ned)? those",
    re.I,
)


def rule_bearing(text):
    """True when `text` carries a bit-exactness or contract pin (rule 29)."""
    return bool(RULE_IDIOM_CS.search(text) or RULE_IDIOM_CI.search(text))


HARD_KEEP = re.compile(
    r"DARKBLOOM_"
    r"|Copyright"
    r"|MARK:"
    r"|Ported from"
    r"|upstream",
    re.I,
)


def hard_keep(body, lines=None, end=None):
    """Whole-block keep test, including the declaration the block documents.

    `lines`/`end` are optional so Part A's callers keep their old behaviour; when
    supplied, the next DECL_LOOKAHEAD source lines join the match text. Several
    flag docs in LagunaRuntimeModel.swift describe a `DARKBLOOM_*` contract whose
    only textual mention is in the `let` two or three lines below the comment.
    """
    text = "\n".join(body)
    if lines is not None and end is not None:
        text = "\n".join([text] + lines[end:min(end + DECL_LOOKAHEAD, len(lines))])
    return bool(HARD_KEEP.search(text)) or rule_bearing(text)


SECTION = re.compile(r"^\s*//[/!]?\s*(?:-\s*(?:Parameters?|Returns?|Throws):|###\s|\d\.\s)")
BLANK_C = re.compile(r"^\s*//[/!]?\s*$")
SENTENCE_END = re.compile(r"[.!?][)`\"']?\s*$")
DECL = re.compile(
    r"\b(?:func|var|let|struct|class|enum|protocol|actor|extension|typealias|case)"
    r"\s+([A-Za-z_]\w*)"
)


def symbol_for(lines, end, start=None):
    """Nearest declaration below the block, else the enclosing one above it.

    A `line<N>` anchor is invalidated by the very commit that creates it, so when
    nothing is declared below the block we walk back to the declaration the block
    sits inside -- the name a future reader will actually grep for.
    """
    for j in range(end, min(end + DECL_LOOKAHEAD, len(lines))):
        s = lines[j].strip()
        if not s or s.startswith("//"):
            continue
        m = DECL.search(s)
        if m:
            return m.group(1)
        if s.startswith("init"):
            return "init"
        break
    for j in range((start if start is not None else end) - 2, -1, -1):
        s = lines[j].strip()
        if s.startswith("//"):
            continue
        m = DECL.search(s)
        if m:
            return m.group(1)
    return f"line{end}"


def keep_count(body):
    """Number of leading lines that stay: the block's opening sentence.

    Never cuts mid-sentence: the scan runs to the first sentence end and only
    falls back to the ABSTRACT_HARD_LINES bound when the block has none.
    """
    for k, line in enumerate(body):
        if k and (BLANK_C.match(line) or SECTION.match(line)):
            return k
        if SENTENCE_END.search(line):
            return k + 1
        if k + 1 >= ABSTRACT_HARD_LINES:
            return k + 1
    return len(body)


def plan(name, rel, lines, bl):
    out, kept, moved, hard = [], 0, 0, 0
    for start, end, body, unsafe in bl:
        nb = sum(nbytes(x) for x in body)
        if unsafe:
            sys.exit(f"FAIL {rel}:{start}-{end} sits inside a \"\"\" literal")
        if hard_keep(body, lines, end):
            override = SPLIT_OVERRIDE.get((name, start))
            if override:
                for s, e, sym, ptr in override:
                    if not start <= s <= e <= end:
                        sys.exit(f"FAIL {rel}: override {s}-{e} escapes block "
                                 f"{start}-{end}")
                    rb = sum(nbytes(lines[i - 1]) for i in range(s, e + 1))
                    out.append({"start": s, "end": e, "symbol": sym,
                                "pointer": ptr})
                    moved += rb
                    nb -= rb
            kept += nb
            hard += nb
            continue
        k = keep_count(body)
        rest = body[k:]
        rb = sum(nbytes(x) for x in rest)
        if not rest or rb < MIN_RELOCATE_BYTES:
            kept += nb
            continue
        out.append({
            "start": start + k,
            "end": end,
            "symbol": symbol_for(lines, end, start + k),
            "pointer": rb >= POINTER_MIN_BYTES_APPLIED,
        })
        kept += nb - rb
        moved += rb
    return out, kept, moved, hard


def main():
    target = REPO / "research" / "fern_vendor_relocate_spec.json"
    # This spec has already been applied: the five vendor files in the checkout no
    # longer hold the blocks it names, so a silent re-plan would emit ranges for
    # the *relocated* text and quietly overwrite the record of what was moved.
    if target.exists() and "--regenerate" not in sys.argv[1:]:
        sys.exit(f"refusing to overwrite applied {target.relative_to(REPO)}; "
                 f"pass --regenerate to re-plan from the current checkout")
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
    target.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target.relative_to(REPO)}")


if __name__ == "__main__":
    main()
