#!/usr/bin/env python3
"""Plan (never apply) the comment relocation for LagunaRuntimeModel.swift.

Part B of the vendor byte-recovery assignment. This tool must leave
`Sources/MLXFastModel/LagunaRuntimeModel.swift` byte-identical: it only reads the
file and writes a machine-applicable spec plus a human manifest under research/.

Three things make the scored file different from the five vendor files:

  1. It embeds Metal kernel sources in `\"\"\"` literals, and five of those lines
     look like Swift comments (:4587-4591, 372 B). They are compile input. Every
     block overlapping a literal is refused here and re-checked by the applier.
  2. Three PRs are in flight against it. Each planned block is labelled
     `apply after fence` when it overlaps a declared in-flight range, so the
     manifest can be applied in two waves without a textual conflict.
  3. Its comment pool is 120,254 B against a 524,288 B per-file cap, so the
     projected post-relocation size is the number that matters, not the delta.

Policy is inherited verbatim from fern_vendor_relocate_plan.py so Part A and
Part B recover bytes under one auditable rule.
"""

import json
import sys
from pathlib import Path

from frieren_comment_blocks import blocks
from fern_vendor_relocate_plan import (
    HARD_KEEP, MIN_RELOCATE_BYTES, POINTER_MIN_BYTES, keep_count, symbol_for,
)

REPO = Path(__file__).resolve().parents[1]
BASE = "63ab67c888e1892086b7b5b623de4dd0ebe68c90"
REL = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
NOTE = "LagunaRuntimeModel.notes.md"
PER_FILE_CAP = 524_288

# Declared in-flight edit ranges, from the assignment brief. A planned block that
# overlaps any of these must wait for the owning PR to land or close.
FENCES = {
    "#301": [(6577, 6716), (6801, 6900), (7545, 7690)],
    "#308": [(4035, 4457), (6801, 6900), (7545, 7690), (7851, 8027)],
    "#309": [(4610, 4881), (763, 792), (801, 801), (837, 1099)],
}


def fences_for(start, end):
    return sorted(
        pr for pr, rs in FENCES.items()
        if any(start <= b and a <= end for a, b in rs)
    )


def literal_comment_lines(lines):
    """1-based lines that look like a comment but sit inside a `\"\"\"` literal.

    Mirrors research/frieren_comment_strip_check.sh's phase-1 awk exactly, so the
    manifest and the checker agree on which lines are embedded kernel source.
    """
    inside = False
    hits = []
    for i, line in enumerate(lines, 1):
        was = inside
        if line.count('"""') % 2 == 1:
            inside = not inside
        if was and line.lstrip().startswith("//"):
            hits.append((i, len(line.encode("utf-8")) + 1))
    return hits


def main():
    bl, lines = blocks(REPO / REL)
    lit = literal_comment_lines(lines)
    lit_bytes = sum(b for _, b in lit)
    lit_set = {i for i, _ in lit}
    entries = []
    kept = moved = hard = 0

    for start, end, body, unsafe in bl:
        nb = sum(len(x.encode("utf-8")) + 1 for x in body)
        if unsafe:
            sys.exit(f"FAIL {REL}:{start}-{end} sits inside a \"\"\" literal")
        if HARD_KEEP.search("\n".join(body)):
            kept += nb
            hard += nb
            continue
        k = keep_count(body)
        rest = body[k:]
        rb = sum(len(x.encode("utf-8")) + 1 for x in rest)
        if not rest or rb < MIN_RELOCATE_BYTES:
            kept += nb
            continue
        s = start + k
        entries.append({
            "start": s,
            "end": end,
            "symbol": symbol_for(lines, end),
            "pointer": rb >= POINTER_MIN_BYTES,
            "bytes": rb,
            "fences": fences_for(s, end),
        })
        kept += nb - rb
        moved += rb

    entries.sort(key=lambda b: b["start"])

    clash = [i for i in lit_set
             if any(b["start"] <= i <= b["end"] for b in entries)]
    if clash:
        sys.exit(f"FAIL literal-interior lines inside a planned block: {clash}")

    now = (REPO / REL).stat().st_size
    ptr_bytes = sum(
        len(f"// See notes/{NOTE}#{b['symbol'].lower()}".encode("utf-8")) + 1
        for b in entries if b["pointer"]
    )
    net = moved - ptr_bytes

    imm = [b for b in entries if not b["fences"]]
    dfr = [b for b in entries if b["fences"]]
    by_pr = {pr: 0 for pr in FENCES}
    for b in dfr:
        for pr in b["fences"]:
            by_pr[pr] += b["bytes"]

    print(f"file                    {REL}")
    print(f"size now                {now} B")
    print(f"comment blocks          {len(bl)}")
    print(f"  literal-interior      {len(lit)} line(s), {lit_bytes} B at "
          f"{','.join(str(i) for i, _ in lit)}  (never a block; 0 in any plan)")
    print(f"  hard-keep             {hard} B")
    print(f"planned blocks          {len(entries)}  ({len(imm)} immediate, {len(dfr)} fenced)")
    print(f"moved bytes             {moved}")
    print(f"pointer bytes added     {ptr_bytes}")
    print(f"NET recovery            {net}")
    print(f"projected size          {now - net} B  "
          f"({100.0 * (now - net) / PER_FILE_CAP:.1f}% of the {PER_FILE_CAP} B cap)")
    print(f"headroom now            {PER_FILE_CAP - now} B")
    print(f"headroom projected      {PER_FILE_CAP - (now - net)} B")
    print()
    print("wave 1 (apply immediately): "
          f"{len(imm)} blocks, {sum(b['bytes'] for b in imm)} B")
    print("wave 2 (apply after fence): "
          f"{len(dfr)} blocks, {sum(b['bytes'] for b in dfr)} B")
    for pr in sorted(by_pr):
        n = sum(1 for b in dfr if pr in b["fences"])
        print(f"    overlaps {pr}: {n} blocks, {by_pr[pr]} B")

    spec = {
        "base_sha": BASE,
        "files": [{
            "file": REL,
            "note": NOTE,
            "blocks": [
                {k: b[k] for k in ("start", "end", "symbol", "pointer")}
                for b in entries
            ],
        }],
    }
    out = REPO / "research" / "fern_partB_lagunaruntimemodel_spec.json"
    out.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")

    wave1 = {
        "base_sha": BASE,
        "files": [{
            "file": REL,
            "note": NOTE,
            "blocks": [
                {k: b[k] for k in ("start", "end", "symbol", "pointer")}
                for b in imm
            ],
        }],
    }
    out1 = REPO / "research" / "fern_partB_lagunaruntimemodel_spec_wave1.json"
    out1.write_text(json.dumps(wave1, indent=2) + "\n", encoding="utf-8")

    rows = REPO / "research" / "fern_partB_lagunaruntimemodel_blocks.tsv"
    with rows.open("w", encoding="utf-8") as fh:
        fh.write("start\tend\tbytes\tpointer\tfences\tsymbol\n")
        for b in entries:
            fh.write(f"{b['start']}\t{b['end']}\t{b['bytes']}\t"
                     f"{int(b['pointer'])}\t{','.join(b['fences']) or '-'}\t"
                     f"{b['symbol']}\n")
    for p in (out, out1, rows):
        print(f"wrote {p.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
