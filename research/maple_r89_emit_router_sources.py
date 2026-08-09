#!/usr/bin/env python3
"""Emit the router kernel's Metal source for every R89-A prefetch arm.

Research-only. The Metal text is produced by the SCORED generator itself:
this script lifts `lagunaResidualRMSNormRouterSource` and its dependencies
verbatim out of `Sources/MLXFastModel/LagunaRuntimeModel.swift`, compiles them
into a throwaway driver, and runs it. Nothing is re-implemented here, so the
probe can never drift from the kernel the runtime actually dispatches.

    python3 research/maple_r89_emit_router_sources.py OUTDIR [ROWS_PER_GROUP]
"""

import os
import subprocess
import sys

SCORED = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
ARMS = [0, 1, 2, 3, 4, 5]

# Phase-split diagnostics. Not shippable and never numerically correct; they
# exist only to put a duration on each half of arm 0 so the latency-overlap
# ceiling can be quoted as a fraction of the reduction phase.
NORM_ONLY_ARM = 6
GEMV_ONLY_ARM = 7

# (start-line prefix, end predicate) for every declaration the generator needs.
REGIONS = [
    ("private let lagunaRouterPrecomputedKeysEnabled =",
     lambda l: l.startswith("    ProcessInfo")),
    ("private let lagunaNormInvMeanScratch =", lambda l: True),
    ("private func lagunaNormReductionTail(", lambda l: l == "}"),
    ("private let lagunaNormReductionTail2048 = lagunaNormReductionTail(",
     lambda l: l.endswith(")")),
    ("private let lagunaDecodeRouterOrdinalHeader = \"\"\"",
     lambda l: l == '"""'),
    ("private func lagunaRouterPrefetchGroups(", lambda l: l == "}"),
    ("private func lagunaResidualRMSNormRouterSource(", lambda l: l == "}"),
]


def extract(lines, start_prefix, is_end):
    starts = [i for i, l in enumerate(lines) if l.startswith(start_prefix)]
    if len(starts) != 1:
        raise SystemExit(f"expected 1 match for {start_prefix!r}, got {len(starts)}")
    i = starts[0]
    out = [lines[i]]
    in_literal = lines[i].count('"""') % 2 == 1
    j = i
    while True:
        j += 1
        line = lines[j]
        out.append(line)
        if line.count('"""') % 2 == 1:
            in_literal = not in_literal
        if not in_literal and is_end(line):
            break
    return "\n".join(out)


def cut(text, start_anchor, end_anchor, replacement):
    i = text.index(start_anchor)
    j = text.index(end_anchor, i) + len(end_anchor)
    return text[:i] + replacement + text[j:]


def phase_variants(arm0):
    """Split arm 0 into its reduction half and its router-GEMV half."""
    # Keep every barrier, the residual add, the reduction and the normalize
    # loop; drop only the 2048-column weight read and its FMAs. The shuffle
    # ladder and epilogue stay so nothing downstream is dead-code eliminated.
    norm_only = cut(
        arm0,
        "        uint column = simd_lane * n_reads;",
        "            column += 4 * block_width;\n        }",
        "        router_result[0] = float(normalized_row[simd_lane * n_reads]);",
    )
    # Drop the cross-simdgroup reduction and its three barriers; keep the GEMV.
    gemv_only = cut(
        arm0,
        "acc = simd_sum(acc);",
        "float laguna_inv_mean = local_inv_mean[0];",
        "float laguna_inv_mean = 1.0f;",
    )
    return norm_only, gemv_only


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    outdir = os.path.abspath(sys.argv[1])
    rpg = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    os.makedirs(outdir, exist_ok=True)
    lines = open(SCORED, encoding="utf-8").read().split("\n")

    decls = []
    for prefix, is_end in REGIONS:
        if prefix.startswith("private let lagunaNormInvMeanScratch"):
            idx = [i for i, l in enumerate(lines) if l.startswith(prefix)]
            decls.append(lines[idx[0]])
            continue
        decls.append(extract(lines, prefix, is_end))

    driver = os.path.join(outdir, "emit.swift")
    with open(driver, "w", encoding="utf-8") as fh:
        fh.write("import Foundation\n\n")
        fh.write("\n\n".join(decls))
        fh.write(
            "\n\nlet outdir = CommandLine.arguments[1]\n"
            f"let rpg = {rpg}\n"
            f"for arm in {ARMS} {{\n"
            "    let src = lagunaResidualRMSNormRouterSource("
            "rowsPerGroup: rpg, prefetch: arm)\n"
            '    try! src.write(toFile: outdir + "/arm\\(arm).metal", '
            "atomically: true, encoding: .utf8)\n"
            "}\n"
            'try! lagunaDecodeRouterOrdinalHeader.write(toFile: outdir + "/header.metal", '
            "atomically: true, encoding: .utf8)\n"
            'print("keys=\\(lagunaRouterPrecomputedKeysEnabled) rpg=\\(rpg)")\n'
        )

    binary = os.path.join(outdir, "emit")
    subprocess.run(
        ["xcrun", "swiftc", "-O", driver, "-o", binary], check=True)
    subprocess.run([binary, outdir], check=True)
    arm0 = open(os.path.join(outdir, "arm0.metal"), encoding="utf-8").read()
    norm_only, gemv_only = phase_variants(arm0)
    for arm, text in ((NORM_ONLY_ARM, norm_only), (GEMV_ONLY_ARM, gemv_only)):
        with open(os.path.join(outdir, f"arm{arm}.metal"), "w",
                  encoding="utf-8") as fh:
            fh.write(text)

    for arm in ARMS + [NORM_ONLY_ARM, GEMV_ONLY_ARM]:
        path = os.path.join(outdir, f"arm{arm}.metal")
        print(f"arm{arm}: {os.path.getsize(path)} bytes  {path}")


if __name__ == "__main__":
    main()
