#!/usr/bin/env python3
"""Resolve the `one-side` symbols left over by maple_r85b_split_asm.sh.

`compare_asm` reports symbols present in only one arm. Those are not evidence of
new code until each one is matched to a body-identical partner on the other
side. This prints the one-side sets and, for every only-in-base body, every
only-in-cand body that matches it instruction for instruction.

Usage: maple_r85b_oneside_pairs.py [SNAPSHOT_DIR] [NEEDLE]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fern_emit_compare import _disassemble, _text_symbol_names  # noqa: E402


def main() -> int:
    snap = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/maple-r85b-snap")
    needle = sys.argv[2] if len(sys.argv) > 2 else "12MLXFastModel"

    bodies = {}
    for arm in ("base", "cand"):
        binary = snap / arm / "mlxfast-runtime-worker"
        bodies[arm] = _disassemble(binary, _text_symbol_names(binary, needle))

    only_base = sorted(set(bodies["base"]) - set(bodies["cand"]))
    only_cand = sorted(set(bodies["cand"]) - set(bodies["base"]))

    for arm, names in (("BASE", only_base), ("CAND", only_cand)):
        src = bodies[arm.lower()]
        print(f"only-in-{arm} ({len(names)}):")
        for name in names:
            print(f"   [{len(src[name]):>4} insns] {name}")

    print("\n=== body-identical partners across the one-side sets ===")
    unmatched = 0
    for name in only_base:
        body = bodies["base"][name]
        hits = [c for c in only_cand if bodies["cand"][c] == body]
        unmatched += not hits
        print(f"base {name}\n     -> {len(hits)} partner(s)")
        for hit in hits:
            print(f"        {hit}")
    print(f"\nonly-in-base symbols with no body-identical partner: {unmatched}")
    return 1 if unmatched else 0


if __name__ == "__main__":
    raise SystemExit(main())
