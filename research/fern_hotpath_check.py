#!/usr/bin/env python3
"""Confirm the timed-path functions are in the body-identical set (research-only).

The per-symbol asm sweep (fern_emit_compare.py asm) reports only the symbols
that were NOT body-identical. This script takes the opposite view: it
enumerates the functions that execute inside the timed prefill/decode window,
checks each was present and compared on both sides, and asserts none appears in
the not-identical set. That is the direct answer to "did the private ->
internal widening cost an inlining or specialization opportunity on the scored
path".
"""
import re
import subprocess
import sys

EMIT = sys.argv[1] if len(sys.argv) > 1 else "../mlxfast-r85b-emit"

# A `private` declaration's mangled name embeds a hash of its file, so moving
# one to another file renames it. Normalise exactly as fern_emit_compare.py
# does, so a symbol that only changed file-of-origin still matches by shape.
PRIVATE_DISCRIMINATOR = re.compile(r"\d+_[0-9A-Fa-f]{32}LL")

# Substrings of the demangled name of every function on the timed path. Kept as
# substrings so a specialization or thunk of the same function still matches.
HOT = [
    "LagunaRuntimeModelInner.callAsFunction",
    "LagunaRuntimeDecoderLayer.callAsFunction",
    "LagunaRuntimeSparseMoEBlock",
    "LagunaRuntimeMLP.callAsFunction",
    "LagunaRuntimeMoEGate",
    "LagunaRuntimeAttention",
    "lagunaDecodeRouter",
    "lagunaDecodeEmbeddingRoPEAtlas",
    "lagunaPrefill",
    "lagunaRoPE",
    "makeLagunaAttentionGateProjection",
    "LagunaNativeAffineWeight",
]


def xcrun(tool):
    return subprocess.run(["xcrun", "--find", tool], capture_output=True,
                          text=True, check=True).stdout.strip()


def text_symbols(binary):
    nm = xcrun("llvm-nm")
    out = subprocess.run([nm, "-n", "--defined-only", binary],
                         capture_output=True, text=True, check=True).stdout
    syms = []
    for line in out.splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3 and parts[0].strip() and parts[1].upper() == "T":
            if "MLXFastModel" in parts[2]:
                syms.append(parts[2])
    return syms


def demangle(names):
    out = subprocess.run([xcrun("swift-demangle"), "-compact"] + names,
                         capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout:
        return dict(zip(names, names))
    return dict(zip(names, out.stdout.splitlines()))


def main():
    raw_base = text_symbols(f"{EMIT}/base-worker.bin")
    raw_cand = text_symbols(f"{EMIT}/cand-worker.bin")
    report = open(f"{EMIT}/asm-diff-mlxfastmodel.txt").read()

    def norm(name):
        return PRIVATE_DISCRIMINATOR.sub("<PRIV>", name)

    kinds = {}
    for line in report.splitlines():
        m = re.match(r"^\s+\[([^\]]+)\]\s+(?:\d+->\d+ insns\s+)?(\S+)$", line)
        if m:
            kinds[norm(m.group(2))] = m.group(1)

    base, cand = {norm(s) for s in raw_base}, {norm(s) for s in raw_cand}
    common = sorted(base & cand)
    raw_of = {norm(s): s for s in raw_base}
    names = {}
    for i in range(0, len(common), 300):
        chunk = [raw_of[s] for s in common[i:i + 300]]
        names.update({norm(k): v for k, v in demangle(chunk).items()})

    print(f"MLXFastModel __text symbols: base={len(raw_base)} cand={len(raw_cand)} "
          f"matched-after-discriminator-normalisation={len(common)}")
    print(f"symbols the asm sweep did not call body-identical: {len(kinds)}")
    print()

    diff = 0
    for pat in HOT:
        hits = [s for s in common if pat in names.get(s, s)]
        hit_kinds = [(s, kinds[s]) for s in hits if s in kinds]
        real = [s for s, k in hit_kinds if k == "DIFF"]
        if not hits:
            status = "NO SYMBOL"
        elif real:
            status = "DIFFERENT"
        elif hit_kinds:
            status = "ISLAND"
        else:
            status = "IDENTICAL"
        print(f"  {status:>9}  n={len(hits):>3}  {pat}")
        for s, k in hit_kinds:
            print(f"            [{k}] {s[:110]}")
        diff += len(real)

    print()
    print(f"timed-path symbols with a DIFFERENT body: {diff}")
    print("(ISLAND = every body instruction identical; the only extra instruction "
          "is an unreachable linker branch island in inter-function padding)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
