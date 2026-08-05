#!/usr/bin/env python3
"""Prepend the per-arm receipt header to the shared MB-per-buffer note body."""
import sys
from pathlib import Path

ORDER = ["low", "high", "control"]
ARMS = {
    "low": (50, 85, "about **2% faster** decode"),
    "high": (400, 19, "about **2% slower** decode"),
    "control": (200, 34, "**no change**; this is the A/A noise-floor probe"),
}

arm = sys.argv[1]
mb, cbs, pred = ARMS[arm]
pos = ORDER.index(arm) + 1
siblings = ", ".join(f"A/{a} ({ARMS[a][0]})" for a in ORDER if a != arm)
root = Path(__file__).resolve().parent

header = f"""# Receipt A/{arm} — `MLX_MAX_MB_PER_BUFFER = {mb}`

| field | value |
| --- | --- |
| arm | **{arm}** |
| `MLX_MAX_MB_PER_BUFFER` | **{mb}** (frontier value is 200) |
| `MLX_MAX_OPS_PER_BUFFER` | 200 (unchanged) |
| position in this round | **{pos} of 3** (pre-registered order: {", ".join(ORDER)}) |
| commits per decode step, measured locally | **{cbs}** (control arm: 34) |
| dispatches per decode step | 406 (identical in all three arms) |
| local prediction for this arm | {pred} |
| sibling arms in this round | {siblings} |

The submission order of the three arms was drawn before any of them was
submitted, seeded on the pull-request number, so that arm position cannot be
confounded with arm identity. This is arm {pos} of 3.

---

"""
body = (root / "nezuko-mbpb-submission-note.md").read_text()
out = Path(f"/tmp/note.{arm}.md")
out.write_text(header + body)
print(f"{out} {len(header) + len(body)} bytes")
