"""Assert every advisor-flagged bit-exactness pin stays in the scored file.

The advisor named six source lines that must not leave LagunaRuntimeModel.swift.
This resolves each to its enclosing comment block and reports whether the plan
hard-keeps that block, so a policy change cannot quietly release one of them.

Run from the repository root: python3 research/fern_partB_pin_audit.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, "research")
from frieren_comment_blocks import blocks
from fern_vendor_relocate_plan import hard_keep, rule_bearing

PINS = [1240, 3696, 4469, 2502, 8491, 10023]

bl, lines = blocks(Path("Sources/MLXFastModel/LagunaRuntimeModel.swift"))
spec = json.load(open("research/fern_partB_lagunaruntimemodel_spec.json"))
planned = spec["files"][0]["blocks"]

fail = 0
for pin in sorted(PINS):
    owner = next(((s, e, b, u) for s, e, b, u in bl if s <= pin <= e), None)
    if owner is None:
        print(f"FAIL  L{pin} sits in no comment block")
        fail += 1
        continue
    s, e, body, _ = owner
    kept = hard_keep(body, lines, e)
    released = [p for p in planned if p["start"] <= pin <= p["end"]]
    tag = "ok  " if kept and not released else "FAIL"
    if tag == "FAIL":
        fail += 1
    print(f"{tag}  L{pin}  block {s}-{e}  hard_keep={kept}  "
          f"rule_bearing={bool(rule_bearing(chr(10).join(body)))}  "
          f"relocated={bool(released)}")

print(f"\npins released by the plan: {fail}")
sys.exit(1 if fail else 0)
