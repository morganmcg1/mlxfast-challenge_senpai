#!/usr/bin/env python3
"""Phase 3 of the Part B dry run: rule-29 containment and arithmetic agreement.

Three independent assertions, each a hard failure:

  rule   every relocated line is extracted from the pristine copy. A line that
         carries a bit-exactness idiom (research/fern_vendor_relocate_plan.py's
         RULE_IDIOM alternation) may only leave the scored file when its block
         emits a pointer, so the pin stays reachable from the call site.
  bytes  every relocated line must land in the note under its own heading, in
         order, with only the comment marker stripped. A silently dropped,
         reordered or duplicated line changes one side only.
  size   the planner's projected final size must equal the applier's actual final
         size to the byte, so a projection can never be quoted as a result.

Usage: fern_partB_phase3_check.py SPEC PRISTINE RELOCATED NOTE
Set MLXFAST_DRY_RUN_INJECT=rule|bytes|size to corrupt one input and prove the
corresponding assertion fires.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fern_vendor_relocate_plan import nbytes, rule_bearing
from frieren_relocate_comments import anchors, strip_marker

SPEC, PRISTINE, RELOCATED, NOTE = (Path(p) for p in sys.argv[1:5])
INJECT = os.environ.get("MLXFAST_DRY_RUN_INJECT", "")

spec = json.loads(SPEC.read_text())
blocks = spec["files"][0]["blocks"]
pristine = PRISTINE.read_text().split("\n")
fail = 0

if INJECT == "rule":
    # Force one pointer-less block to swallow a pin line.
    victim = next(b for b in blocks if not b["pointer"])
    victim["start"], victim["end"] = 8488, 8493
    print(f"INJECT rule: block now covers 8488-8493 with pointer=False")

print("--- 3a: relocated lines carrying a rule-29 idiom ---")
moved_lines = []
pinned = 0
for b in blocks:
    body = pristine[b["start"] - 1:b["end"]]
    moved_lines.extend(body)
    hits = [x for x in body if rule_bearing(x)]
    if not hits:
        continue
    pinned += len(hits)
    tag = "ok  " if b["pointer"] else "FAIL"
    if not b["pointer"]:
        fail += 1
    print(f"{tag}  {b['start']}-{b['end']} pointer={b['pointer']} "
          f"{b['symbol']}")
    for x in hits:
        print(f"        {x.strip()[:88]}")
print(f"relocated lines            {len(moved_lines)}")
print(f"rule-bearing among them    {pinned} "
      f"({'all behind a pointer' if not fail else 'UNPOINTED'})")

print("\n--- 3b: every relocated line lands in the note, in order ---")
moved_bytes = sum(nbytes(x) for x in moved_lines)
note = NOTE.read_text().split("\n")
if INJECT == "bytes":
    note = [x for x in note if not x.startswith("_relocated from lines ")]
    print("INJECT bytes: dropped every section provenance line from the note")
sha8 = spec["base_sha"][:8]
landed = 0
missing = 0
for b, (heading, _anchor) in zip(blocks, anchors(blocks)):
    body = [strip_marker(l) for l in pristine[b["start"] - 1:b["end"]]]
    try:
        i = note.index(heading)
    except ValueError:
        print(f"FAIL  {b['start']}-{b['end']} heading absent: {heading}")
        missing += 1
        continue
    want = ["", f"_relocated from lines {b['start']}-{b['end']} at base {sha8}_",
            ""] + body
    got = note[i + 1:i + 1 + len(want)]
    if got != want:
        j = next(k for k in range(len(want)) if k >= len(got) or got[k] != want[k])
        seen = got[j] if j < len(got) else "<eof>"
        print(f"FAIL  {b['start']}-{b['end']} diverges at note line {i + 2 + j}")
        print(f"        want {want[j]!r}")
        print(f"        got  {seen!r}")
        missing += 1
        continue
    landed += sum(nbytes(x) for x in body)
print(f"blocks in spec             {len(blocks)}")
print(f"moved bytes (with markers) {moved_bytes}")
print(f"landed bytes (stripped)    {landed}")
print(f"blocks that did not land   {missing}")
if missing:
    fail += 1
else:
    print("ok    all relocated prose is reachable in the note, in order")

print("\n--- 3c: planner projection == applier actual ---")
proj = spec.get("projection")
if proj is None:
    print("FAIL  spec carries no projection block")
    fail += 1
else:
    actual_before = len(PRISTINE.read_bytes())
    actual_after = len(RELOCATED.read_bytes())
    if INJECT == "size":
        proj = dict(proj, size_after=proj["size_after"] - 50)
        print("INJECT size: planner projection shifted by -50 B")
    print(f"planner size_before        {proj['size_before']}")
    print(f"actual  size_before        {actual_before}")
    print(f"planner size_after         {proj['size_after']}")
    print(f"actual  size_after         {actual_after}")
    print(f"planner net_bytes          {proj['net_bytes']}")
    print(f"actual  net_bytes          {actual_before - actual_after}")
    for label, a, b in (("size_before", proj["size_before"], actual_before),
                        ("size_after", proj["size_after"], actual_after)):
        if a != b:
            print(f"FAIL  {label} planner {a} != actual {b} (delta {b - a})")
            fail += 1
    if proj["moved_bytes"] != moved_bytes:
        print(f"FAIL  moved_bytes planner {proj['moved_bytes']} != "
              f"extracted {moved_bytes}")
        fail += 1
    if not fail:
        print("ok    projection and actual agree to the byte")

print(f"\nphase 3 failures: {fail}")
sys.exit(1 if fail else 0)
