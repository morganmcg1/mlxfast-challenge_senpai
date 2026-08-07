#!/usr/bin/env python3
"""Emit research/frieren_relocate_spec.json for the round-2 byte-recovery pass.

Evaluate.swift blocks are derived mechanically (DocC abstract kept, body moved).
The two Sources/MLXFastModel/ entries are hand-audited sub-ranges: every range
here carries a measurement outcome or session identity, and each one that leaves
a dangling clause is repaired by hand after this tool runs.

Run from the research/ directory.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASE = "e1d070f256a1f5cef5a62a1d001dfbfe8b81bd0c"
POINTER_MIN_BYTES = 500


def docc_blocks(rel, minb, mode="abstract"):
    out = subprocess.run(
        [sys.executable, "frieren_gen_docc_spec.py", str(REPO / rel), str(minb), mode],
        capture_output=True, text=True, check=True,
    ).stdout
    blocks = json.loads(out[out.index("["):])
    for b in blocks:
        # `all` mode empties the file of prose, so a single hand-written banner
        # at the top replaces per-block pointers that would cost more than they
        # recover.
        b["pointer"] = mode != "all" and b["bytes"] >= POINTER_MIN_BYTES
        del b["bytes"]
    return blocks


spec = {
    "base_sha": BASE,
    "files": [
        {
            "file": "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/Evaluate.swift",
            "note": "MLXLMCommon-Evaluate.notes.md",
            "blocks": docc_blocks(
                "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/Evaluate.swift", 1, "all"
            ),
        },
        {
            "file": "Sources/MLXFastModel/LagunaRuntimeWeights.swift",
            "note": "LagunaRuntimeWeights.notes.md",
            "blocks": [
                {"start": 420, "end": 431, "symbol": "wired residency measurement history", "pointer": True},
                {"start": 451, "end": 459, "symbol": "wired residency host headroom", "pointer": True},
                {"start": 503, "end": 507, "symbol": "greedy argmax PSO miss trace", "pointer": True},
                {"start": 526, "end": 537, "symbol": "wired residency dose curve", "pointer": True},
                {"start": 1001, "end": 1004, "symbol": "group16 scale pair census", "pointer": True},
            ],
        },
        {
            "file": "Sources/MLXFastModel/LagunaConfig.swift",
            "note": "LagunaConfig.notes.md",
            "blocks": [
                {"start": 8, "end": 13, "symbol": "Laguna architecture summary", "pointer": True},
            ],
        },
    ],
}

target = REPO / "research" / "frieren_relocate_spec.json"
target.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
print(f"wrote {target} with "
      + ", ".join(f"{e['file'].rsplit('/', 1)[-1]}={len(e['blocks'])}" for e in spec["files"]))
