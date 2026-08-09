#!/usr/bin/env python3
"""Research-only (PR #456): show the actual instruction delta for the handful
of symbols whose bodies differ across the split.

`fern_emit_compare.py asm` reports *that* two bodies differ. For a claim of
neutrality that is not enough: the question is whether the delta is the
expected consequence of widening five `private` declarations to `internal`
(which changes how their once-tokens and accessors are reached) or evidence of
a real semantic change. This prints the aligned diff so the answer is visible
rather than asserted.
"""
import difflib
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fern_emit_compare import _disassemble, _text_symbol_names  # noqa: E402

SNAP = os.environ.get("SNAP", "/tmp/maple-r85b-snap")
SYMS = sys.argv[1:] or [
    "LagunaRuntimeB5InnerCyAcA0C6ConfigVcfc",
    "LagunaRuntimeDecoderLayerC_8layerIdxAcA0C6ConfigV_Sitcfc",
]


def bodies(arm, needle):
    binary = f"{SNAP}/{arm}/mlxfast-runtime-worker"
    return _disassemble(binary, _text_symbol_names(binary, needle))


base = bodies("base", "LagunaRuntime")
cand = bodies("cand", "LagunaRuntime")

for want in SYMS:
    names = [n for n in set(base) | set(cand) if want in n]
    for name in sorted(names):
        b, c = base.get(name, []), cand.get(name, [])
        if b == c:
            print(f"== {name}\n   identical ({len(b)} insns)\n")
            continue
        print(f"== {name}")
        print(f"   base {len(b)} insns -> cand {len(c)} insns")
        for line in difflib.unified_diff(b, c, "base", "cand", n=6, lineterm=""):
            print("   " + line)
        print()

# The mnemonic multiset is the semantic-relevant view: a pure relocation
# changes operands (addresses/offsets), not which operations execute.
print("=== mnemonic-multiset comparison (operands ignored) ===")
for want in SYMS:
    for name in sorted(n for n in set(base) | set(cand) if want in n):
        mb = sorted(i.split("\t")[0] for i in base.get(name, []))
        mc = sorted(i.split("\t")[0] for i in cand.get(name, []))
        verdict = "SAME mnemonics" if mb == mc else "MNEMONICS DIFFER"
        extra = [m for m in mc if mc.count(m) > mb.count(m)]
        print(f"{verdict:17} {name[:96]}")
        if mb != mc:
            print(f"   only-in-cand mnemonics: {sorted(set(extra))}")
