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
     `apply after fence` when it comes within FENCE_GUTTER lines of a declared
     in-flight range, so the manifest can be applied in two waves without a
     textual conflict.
  3. Its comment pool is a sixth of the file against a 524,288 B per-file cap, so
     the projected post-relocation size is the number that matters, not the delta.
     The exact pool total is printed below rather than quoted here.

Policy is inherited verbatim from fern_vendor_relocate_plan.py so Part A and
Part B recover bytes under one auditable rule.
"""

import json
import sys
from pathlib import Path

from frieren_comment_blocks import blocks
from frieren_relocate_comments import anchors, pointer_text
from fern_vendor_relocate_plan import (
    MIN_RELOCATE_BYTES, POINTER_MIN_BYTES, hard_keep, keep_count, nbytes,
    rule_bearing, symbol_for,
)

REPO = Path(__file__).resolve().parents[1]
BASE = "63ab67c888e1892086b7b5b623de4dd0ebe68c90"
REL = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
NOTE = "LagunaRuntimeModel.notes.md"
NOTE_REL = f"notes/{NOTE}"
PER_FILE_CAP = 524_288

# Declared in-flight edit ranges, from the assignment brief. A planned block that
# comes within FENCE_GUTTER lines of any of these must wait for the owning PR to
# land or close.
FENCES = {
    "#301": [(6577, 6716), (6801, 6900), (7545, 7690)],
    "#308": [(4035, 4457), (6801, 6900), (7545, 7690), (7851, 8027)],
    "#309": [(4610, 4881), (763, 792), (801, 801), (837, 1099)],
}

# A block that merely abuts a fence still conflicts in practice: `git apply` and
# `git merge` resolve hunks with three lines of leading and trailing context, so a
# deletion touching line N-1 rewrites the same hunk the fence owner edits at N.
FENCE_GUTTER = 3


def fences_for(start, end, gutter=FENCE_GUTTER):
    return sorted(
        pr for pr, rs in FENCES.items()
        if any(start <= b + gutter and a - gutter <= end for a, b in rs)
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
            hits.append((i, nbytes(line)))
    return hits


def price_pointers(entries, lines):
    """Attach each entry's exact pointer text and byte cost.

    The applier disambiguates duplicate symbols by appending `(L<start>)`, which
    lengthens the pointer, so the price depends on the whole surviving set. Set
    and cost are therefore driven to a fixpoint: dropping an entry can only
    shorten a sibling's anchor, never lengthen one.
    """
    while True:
        for b, (_, anchor) in zip(entries, anchors(entries)):
            ptr = pointer_text(lines[b["start"] - 1], NOTE_REL, anchor)
            b["anchor"] = anchor
            b["ptr_bytes"] = nbytes(ptr) if b["pointer"] else 0
        # A pointer that costs at least what it replaces is pure loss; drop the
        # relocation rather than silently shipping a negative block.
        keep = [b for b in entries if b["bytes"] - b["ptr_bytes"] > 0]
        if len(keep) == len(entries):
            return entries, []
        dropped = [b for b in entries if b not in keep]
        entries = keep
        if not entries:
            return entries, dropped


def main():
    bl, lines = blocks(REPO / REL)
    lit = literal_comment_lines(lines)
    lit_bytes = sum(b for _, b in lit)
    lit_set = {i for i, _ in lit}
    entries = []
    pool = hard = 0

    for start, end, body, unsafe in bl:
        nb = sum(nbytes(x) for x in body)
        pool += nb
        if unsafe:
            sys.exit(f"FAIL {REL}:{start}-{end} sits inside a \"\"\" literal")
        if hard_keep(body, lines, end):
            hard += nb
            continue
        k = keep_count(body)
        rest = body[k:]
        rb = sum(nbytes(x) for x in rest)
        if not rest or rb < MIN_RELOCATE_BYTES:
            continue
        s = start + k
        entries.append({
            "start": s,
            "end": end,
            "symbol": symbol_for(lines, end, s),
            # A relocated rule pin must stay traceable from the code that obeys
            # it, whatever its size, so it is pointed at unconditionally.
            "pointer": rb >= POINTER_MIN_BYTES or rule_bearing("\n".join(rest)),
            "bytes": rb,
            "fences": fences_for(s, end),
            "fences_strict": fences_for(s, end, gutter=0),
        })

    entries.sort(key=lambda b: b["start"])
    entries, unpriced = price_pointers(entries, lines)

    clash = [i for i in lit_set
             if any(b["start"] <= i <= b["end"] for b in entries)]
    if clash:
        sys.exit(f"FAIL literal-interior lines inside a planned block: {clash}")

    now = (REPO / REL).stat().st_size
    moved = sum(b["bytes"] for b in entries)
    ptr_bytes = sum(b["ptr_bytes"] for b in entries)
    net = moved - ptr_bytes

    imm = [b for b in entries if not b["fences"]]
    dfr = [b for b in entries if b["fences"]]
    # Blocks wave 1 forfeits purely to the gutter: clear of every declared range
    # but inside its three-line merge context.
    gut = [b for b in dfr if not b["fences_strict"]]
    by_pr = {pr: 0 for pr in FENCES}
    for b in dfr:
        for pr in b["fences"]:
            by_pr[pr] += b["bytes"]

    imm_net = sum(b["bytes"] - b["ptr_bytes"] for b in imm)
    rule_ptr = [b for b in entries if b["pointer"] and b["bytes"] < POINTER_MIN_BYTES]

    print(f"file                    {REL}")
    print(f"size now                {now} B")
    print(f"comment blocks          {len(bl)}")
    print(f"  comment pool          {pool} B ({100.0 * pool / now:.1f}% of the file)")
    print(f"  literal-interior      {len(lit)} line(s), {lit_bytes} B at "
          f"{','.join(str(i) for i, _ in lit)}  (never a block; 0 in any plan)")
    print(f"  hard-keep             {hard} B")
    print(f"planned blocks          {len(entries)}  ({len(imm)} immediate, {len(dfr)} fenced)")
    print(f"  pointer below floor   {len(rule_ptr)} rule-bearing blocks under "
          f"{POINTER_MIN_BYTES} B, pointed anyway")
    print(f"  dropped, pointer>=mv  {len(unpriced)} blocks")
    print(f"moved bytes             {moved}")
    print(f"pointer bytes added     {ptr_bytes}")
    print(f"NET recovery            {net}")
    print(f"projected size          {now - net} B  "
          f"({100.0 * (now - net) / PER_FILE_CAP:.1f}% of the {PER_FILE_CAP} B cap)")
    print(f"headroom now            {PER_FILE_CAP - now} B")
    print(f"headroom projected      {PER_FILE_CAP - (now - net)} B")
    print()
    print(f"wave 1 (apply immediately): {len(imm)} blocks, "
          f"{sum(b['bytes'] for b in imm)} B moved, "
          f"{sum(b['ptr_bytes'] for b in imm)} B pointers, net {imm_net} B")
    print(f"wave 1 projected size   {now - imm_net} B  "
          f"(headroom {PER_FILE_CAP - (now - imm_net)} B)")
    print("wave 2 (apply after fence): "
          f"{len(dfr)} blocks, {sum(b['bytes'] for b in dfr)} B")
    for pr in sorted(by_pr):
        n = sum(1 for b in dfr if pr in b["fences"])
        print(f"    overlaps {pr}: {n} blocks, {by_pr[pr]} B")
    print(f"    of which gutter-only (>=1 fence within {FENCE_GUTTER} lines, "
          f"none overlapping): {len(gut)} blocks, {sum(b['bytes'] for b in gut)} B")
    for b in gut:
        print(f"      {b['start']}-{b['end']}  {b['bytes']:5d} B  "
              f"{','.join(b['fences'])}  {b['symbol']}")

    # The projection travels inside the spec so the dry run can assert the
    # planner's arithmetic against the applier's actual output byte for byte.
    def build(sel, sel_net):
        return {
            "base_sha": BASE,
            "projection": {
                "size_before": now,
                "moved_bytes": sum(b["bytes"] for b in sel),
                "pointer_bytes": sum(b["ptr_bytes"] for b in sel),
                "net_bytes": sel_net,
                "size_after": now - sel_net,
            },
            "files": [{
                "file": REL,
                "note": NOTE,
                "blocks": [
                    {k: b[k] for k in ("start", "end", "symbol", "pointer")}
                    for b in sel
                ],
            }],
        }

    out = REPO / "research" / "fern_partB_lagunaruntimemodel_spec.json"
    out.write_text(json.dumps(build(entries, net), indent=2) + "\n",
                   encoding="utf-8")

    out1 = REPO / "research" / "fern_partB_lagunaruntimemodel_spec_wave1.json"
    out1.write_text(json.dumps(build(imm, imm_net), indent=2) + "\n",
                    encoding="utf-8")

    rows = REPO / "research" / "fern_partB_lagunaruntimemodel_blocks.tsv"
    with rows.open("w", encoding="utf-8") as fh:
        fh.write("start\tend\tbytes\tptr_bytes\tnet\tpointer\trule\tfences\t"
                 "fences_strict\tsymbol\n")
        for b in entries:
            body = "\n".join(lines[b["start"] - 1:b["end"]])
            fh.write(f"{b['start']}\t{b['end']}\t{b['bytes']}\t{b['ptr_bytes']}\t"
                     f"{b['bytes'] - b['ptr_bytes']}\t{int(b['pointer'])}\t"
                     f"{int(rule_bearing(body))}\t{','.join(b['fences']) or '-'}\t"
                     f"{','.join(b['fences_strict']) or '-'}\t{b['symbol']}\n")
    for p in (out, out1, rows):
        print(f"wrote {p.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
