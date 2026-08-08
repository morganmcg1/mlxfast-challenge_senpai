#!/usr/bin/env python3
"""Research-only (PR #301): fault-injection hooks for the shared-expert QMV.

Standing rule 16: the upstream-equivalence oracle is structurally blind to the
fused shared gate/up family (`prepareFusedSharedGateUp()` is only reached
through `LagunaRuntimeWeights.loadLibraryModel`, while
`LagunaUpstreamEquivalence.swift:66-88` builds the model directly), so an oracle
PASS proves nothing about this PR and a 0-divergence teacher-forced result has
no demonstrated power until a deliberately wrong build is shown to fail.

This script patches three env-gated faults into the runtime, one per mechanism
under test, so a single worker build can serve every fault arm:

    prefetch_stale  mechanism (a). The prefetch block loads the *current*
                    block's scale byte instead of the next one, i.e. the
                    "forgot to advance the prefetch index" bug. K-blocks 1..3
                    of every row then use a stale scale.
    prefetch_zero   mechanism (a), calibration at the *same* patched line.
                    The prefetched scale bytes are forced to 0, so K-blocks
                    1..3 contribute nothing. If this diverges while
                    `prefetch_stale` does not, the hook site is demonstrably
                    live and the stale-scale perturbation is genuinely
                    subthreshold rather than absent.
    activation_zero shared-expert calibration. The rows1 kernel writes 0 for
                    every activation, i.e. the shared expert is deleted. This
                    bounds the teacher-forced tripwire's power on this code
                    path: if even this is undetected, no 0-divergence result
                    on the shared QMV has any power at all.
    plane_byte      mechanism (b), minimal. One data byte of the halved
                    group-32 scale plane is bit-flipped, which corrupts the
                    scale of exactly 16 gate weights of one row: the smallest
                    possible "halved plane is wrong" fault.
    plane_shift     mechanism (b), gross. The halved plane's data region is
                    shifted one byte left, so every lane of every row reads its
                    neighbour's scale.

The hooks live only in the working tree. Nothing is committed to the submitted
surface, so `Sources/MLXFastModel/LagunaRuntimeModel.swift` byte growth is
unchanged; `revert` restores both files with `git checkout --`.

    python3 research/maple_pr301_fault_injection.py check
    python3 research/maple_pr301_fault_injection.py apply
    python3 research/maple_pr301_fault_injection.py revert
"""
from __future__ import annotations

import subprocess
import sys

MODEL = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
WEIGHTS = "Sources/MLXFastModel/LagunaRuntimeWeights.swift"

FAULT_FLAG_ANCHOR = '''private let lagunaSharedSwiGLUQMVPrefetchEnabled =
    ProcessInfo.processInfo.environment["DARKBLOOM_SHARED_QMV_PREFETCH"] == "1"
    || lagunaSharedSwiGLUQMVPairwiseScalesEnabled
'''

FAULT_FLAG_PATCH = FAULT_FLAG_ANCHOR + '''
// RESEARCH-ONLY fault injection (PR #301, standing rule 16). Never submitted;
// applied and reverted by research/maple_pr301_fault_injection.py.
private let lagunaSharedQMVFaultMode =
    ProcessInfo.processInfo.environment["DARKBLOOM_SHARED_QMV_FAULT"] ?? ""
private let lagunaSharedQMVFaultActivationSuffix =
    lagunaSharedQMVFaultMode == "activation_zero" ? " * bfloat(0)" : ""
'''

PREFETCH_ANCHOR = r'''            gate_sb = gate_row_scale[next_block / \(weightsPerScaleByte)];
            up_sb = up_row_scale[next_block / \(weightsPerScaleByte)];
'''

PREFETCH_PATCH = r'''            gate_sb = gate_row_scale[\(faultStaleBlock) / \(weightsPerScaleByte)];
            up_sb = up_row_scale[\(faultStaleBlock) / \(weightsPerScaleByte)];
            \(faultScaleOverride)
'''

STALE_LET_ANCHOR = "    let weightsPerScaleByte = lagunaSharedSwiGLUQMVRows1WeightsPerScaleByte\n"
STALE_LET_PATCH = STALE_LET_ANCHOR + (
    '    let faultStaleBlock =\n'
    '        lagunaSharedQMVFaultMode == "prefetch_stale" ? "block" : "next_block"\n'
    '    let faultScaleOverride =\n'
    '        lagunaSharedQMVFaultMode == "prefetch_zero"\n'
    '        ? "gate_sb = 0; up_sb = 0;" : ""\n'
)

ACT_ANCHOR = "    activated[row] = bfloat(silu * up);\n"
ACT_PATCH = (
    "    activated[row] = bfloat(silu * up)"
    "\\(lagunaSharedQMVFaultActivationSuffix);\n"
)

NAME_ANCHOR = '''    name: lagunaSharedSwiGLUQMVPairwiseScalesEnabled
        ? "laguna_shared_nvfp4_swiglu_qmv_rows1_ps_bf16_v1"
        : "laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1",
'''

NAME_PATCH = '''    name: (lagunaSharedSwiGLUQMVPairwiseScalesEnabled
        ? "laguna_shared_nvfp4_swiglu_qmv_rows1_ps_bf16_v1"
        : "laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1")
        + (lagunaSharedQMVFaultMode.isEmpty
            ? "" : "_fault_" + lagunaSharedQMVFaultMode),
'''

PLANE_ANCHOR = "    return contiguous(concatenated([MLXArray(header), even]))\n"

PLANE_PATCH = '''    // RESEARCH-ONLY fault injection (PR #301, standing rule 16).
    var faultBytes = even.asArray(UInt8.self)
    switch ProcessInfo.processInfo.environment["DARKBLOOM_SHARED_QMV_FAULT"] ?? "" {
    case "plane_byte":
        faultBytes[1] ^= 1
    case "plane_shift":
        for index in 0..<(faultBytes.count - 1) {
            faultBytes[index] = faultBytes[index + 1]
        }
    default:
        return contiguous(concatenated([MLXArray(header), even]))
    }
    return contiguous(concatenated([MLXArray(header), MLXArray(faultBytes)]))
'''

EDITS = [
    (MODEL, FAULT_FLAG_ANCHOR, FAULT_FLAG_PATCH),
    (MODEL, STALE_LET_ANCHOR, STALE_LET_PATCH),
    (MODEL, PREFETCH_ANCHOR, PREFETCH_PATCH),
    (MODEL, ACT_ANCHOR, ACT_PATCH),
    (MODEL, NAME_ANCHOR, NAME_PATCH),
    (WEIGHTS, PLANE_ANCHOR, PLANE_PATCH),
]

MODES = (
    "prefetch_stale",
    "prefetch_zero",
    "activation_zero",
    "plane_byte",
    "plane_shift",
)


def check() -> int:
    problems = 0
    for path, anchor, patch in EDITS:
        with open(path) as fh:
            text = fh.read()
        n_anchor = text.count(anchor)
        n_patch = text.count(patch)
        state = "applied" if n_patch else ("clean" if n_anchor == 1 else "BROKEN")
        head = anchor.strip().splitlines()[0][:64]
        print(f"{state:<8} {path}  anchor x{n_anchor}  :: {head}")
        if state == "BROKEN":
            problems += 1
    return 1 if problems else 0


def apply() -> int:
    for path, anchor, patch in EDITS:
        with open(path) as fh:
            text = fh.read()
        if patch in text:
            print(f"already applied: {path} :: {anchor.strip().splitlines()[0][:48]}")
            continue
        if text.count(anchor) != 1:
            raise SystemExit(
                f"anchor not unique in {path} "
                f"(count={text.count(anchor)}): {anchor!r}")
        with open(path, "w") as fh:
            fh.write(text.replace(anchor, patch))
        print(f"patched: {path} :: {anchor.strip().splitlines()[0][:48]}")
    print("fault modes now available via DARKBLOOM_SHARED_QMV_FAULT="
          + "|".join(MODES))
    return 0


def revert() -> int:
    subprocess.run(["git", "checkout", "--", MODEL, WEIGHTS], check=True)
    print(f"reverted: {MODEL} {WEIGHTS}")
    return check()


def main(argv):
    commands = {"check": check, "apply": apply, "revert": revert}
    if len(argv) != 2 or argv[1] not in commands:
        print(__doc__)
        return 2
    return commands[argv[1]]()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
