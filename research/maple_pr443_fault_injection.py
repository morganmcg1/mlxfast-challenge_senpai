#!/usr/bin/env python3
"""Research-only (PR #443): fault-injection hooks for the halved-plane arm.

Standing rule 16: the upstream-equivalence oracle is structurally blind to the
fused shared gate/up family (`prepareFusedSharedGateUp()` is only reached
through `LagunaRuntimeWeights.loadLibraryModel`, while
`LagunaUpstreamEquivalence.swift:66-88` builds the model directly), so an oracle
PASS proves nothing about `DARKBLOOM_SHARED_SCALE_HALVED` and a 0-divergence
teacher-forced result has no demonstrated power until a deliberately wrong build
is shown to fail.

This is PR #301's instrument re-aimed at the halved-only arm, with two changes
that PR #301's sensitivity gap called for.

1. PR #301 injected inside `lagunaHalvedGroup32ScalePlane`, which three
   different planes call: the routed down plane and the shipped
   `DARKBLOOM_PACKED_SCALES` routed gate/up bank are built in *both* arms. A
   detection there was therefore not attributable to the shared plane. Every
   plane fault here is gated on the shared fused plane's exact byte count
   (1024 rows x 128 group-16 bytes), so the routed banks stay pristine.
2. `plane_byte` (one bit of one row) was undetected 0/128 in PR #301 while
   `plane_shift` (every byte of every row) fired 17/128. `plane_column` fills
   that two-orders-of-magnitude gap with one flipped bit per row, i.e. 32 of
   each row's 2048 weights mis-scaled, so the battery reports a bounded
   detection threshold instead of an unbounded one.

Modes, weakest first:

    plane_byte      One data byte of the halved plane is bit-flipped: the
                    scale of 32 gate weights of row 0. Smallest possible
                    "halved plane is wrong" fault.
    header_drop     The halved loop ignores the 128-byte patch header and
                    reads the even byte for K-block 0, i.e. exactly the two
                    quantizer-unequal pairs the losslessness argument depends
                    on. Directly tests whether the header branch is load-
                    bearing.
    plane_column    One data byte per row is bit-flipped (1024 bytes).
    plane_shift     The plane's data region is shifted one byte left, so every
                    lane of every row reads its neighbour's scale. Tests the
                    consumer's `block / 32 + (lane >> 1)` indexing.
    activation_zero The rows1 kernel writes 0 for every activation, i.e. the
                    shared expert is deleted. Bounds the tripwire's power on
                    this code path: if even this is undetected, no
                    0-divergence result here has any power at all.

The hooks live only in the working tree. Nothing is committed to the submitted
surface, so `Sources/MLXFastModel/LagunaRuntimeModel.swift` byte growth is
unchanged; `revert` restores both files with `git checkout --`.

    python3 research/maple_pr443_fault_injection.py check
    python3 research/maple_pr443_fault_injection.py apply
    python3 research/maple_pr443_fault_injection.py revert
"""
from __future__ import annotations

import subprocess
import sys

MODEL = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
WEIGHTS = "Sources/MLXFastModel/LagunaRuntimeWeights.swift"

# 1024 fused rows x (2048 / 16) group-16 scale bytes. The routed down plane and
# the packed routed gate/up bank both call the same helper with different sizes.
SHARED_PLANE_SCALE_BYTES = 1024 * 128

FLAG_ANCHOR = '''private let lagunaSharedSwiGLUQMVHalvedScalesEnabled =
    ProcessInfo.processInfo.environment["DARKBLOOM_SHARED_SCALE_HALVED"] == "1"
    && lagunaSharedSwiGLUQMVRows1Enabled
    && !lagunaSharedSwiGLUQMVPrefetchEnabled
'''

FLAG_PATCH = FLAG_ANCHOR + '''
// RESEARCH-ONLY fault injection (PR #443, standing rule 16). Never submitted;
// applied and reverted by research/maple_pr443_fault_injection.py.
private let lagunaSharedQMVFaultMode =
    ProcessInfo.processInfo.environment["DARKBLOOM_SHARED_QMV_FAULT"] ?? ""
private let lagunaSharedQMVFaultActivationSuffix =
    lagunaSharedQMVFaultMode == "activation_zero" ? " * bfloat(0)" : ""
private let lagunaSharedQMVFaultHeaderDrop =
    lagunaSharedQMVFaultMode == "header_drop" ? " && false" : ""

// Reconstructs every group-16 scale byte the halved kernel would read -- the
// group-32 plane byte for the lane pair, overridden by the patch header at the
// two allow-listed first pairs -- and compares it against the group-16 plane
// the default kernel reads. This is the detector the token-level tripwire is
// not sensitive enough to be: one flipped plane byte is one mismatch.
func lagunaSharedPlaneVerify(original: MLXArray, halved: MLXArray) {
    let orig = original.asArray(UInt8.self)
    let plane = halved.asArray(UInt8.self)
    let rows = 1024
    let g16 = 128
    let g32 = 64
    let headerBytes = 128
    var mismatch = 0
    var firstBad = -1
    for r in 0..<rows {
        for g in 0..<g16 {
            var got = plane[headerBytes + r * g32 + g / 2]
            if g == 1 && r == 0 { got = plane[0] }
            if g == 1 && r == 512 { got = plane[1] }
            if got != orig[r * g16 + g] {
                mismatch += 1
                if firstBad < 0 { firstBad = r * g16 + g }
            }
        }
    }
    let hdr0: UInt8 = plane[0]
    let hdr1: UInt8 = plane[1]
    let even0: UInt8 = plane[headerBytes]
    let even1: UInt8 = plane[headerBytes + 512 * g32]
    let orig0: UInt8 = orig[1]
    let orig1: UInt8 = orig[512 * g16 + 1]
    var line = "mlxfast: plane-verify bytes=\\(rows * g16)"
    line += " mismatches=\\(mismatch) first=\\(firstBad)"
    line += " hdr=\\(hdr0),\\(hdr1) even=\\(even0),\\(even1)"
    line += " orig=\\(orig0),\\(orig1)\\n"
    FileHandle.standardError.write(Data(line.utf8))
}
'''

TRACE_ANCHOR = '''            guard let scales = qmvScales else { return nil }
            activated = lagunaSharedSwiGLUQMV(
'''

TRACE_PATCH = '''            guard let scales = qmvScales else { return nil }
            // RESEARCH-ONLY fault injection (PR #443, standing rule 16).
            lagunaTrace("shared gate/up QMV (fused shared down input)")
            activated = lagunaSharedSwiGLUQMV(
'''

VERIFY_ANCHOR = '''                _fusedGateUpHalvedScales = halved
                prepared.append(halved)
'''

VERIFY_PATCH = '''                _fusedGateUpHalvedScales = halved
                prepared.append(halved)
                // RESEARCH-ONLY fault injection (PR #443, standing rule 16).
                if ProcessInfo.processInfo.environment[
                    "DARKBLOOM_SHARED_PLANE_VERIFY"] == "1"
                {
                    lagunaSharedPlaneVerify(original: fusedScales, halved: halved)
                }
'''

PATCH_ANCHOR = "            const bool patch = patch_lane && block == 0;\n"
PATCH_PATCH = (
    "            const bool patch = patch_lane && block == 0"
    "\\(lagunaSharedQMVFaultHeaderDrop);\n"
)

ACT_ANCHOR = "    activated[row] = bfloat(silu * up);\n"
ACT_PATCH = (
    "    activated[row] = bfloat(silu * up)"
    "\\(lagunaSharedQMVFaultActivationSuffix);\n"
)

NAME_ANCHOR = '''    name: lagunaSharedSwiGLUQMVPairwiseScalesEnabled
        ? "laguna_shared_nvfp4_swiglu_qmv_rows1_ps_bf16_v1"
        : lagunaSharedSwiGLUQMVHalvedScalesEnabled
            ? "laguna_shared_nvfp4_swiglu_qmv_rows1_hs_bf16_v1"
            : "laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1",
'''

NAME_PATCH = '''    name: (lagunaSharedSwiGLUQMVPairwiseScalesEnabled
        ? "laguna_shared_nvfp4_swiglu_qmv_rows1_ps_bf16_v1"
        : lagunaSharedSwiGLUQMVHalvedScalesEnabled
            ? "laguna_shared_nvfp4_swiglu_qmv_rows1_hs_bf16_v1"
            : "laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1")
        + (lagunaSharedQMVFaultMode.isEmpty
            ? "" : "_fault_" + lagunaSharedQMVFaultMode),
'''

PLANE_ANCHOR = "    return contiguous(concatenated([MLXArray(header), even]))\n"

PLANE_PATCH = f'''    // RESEARCH-ONLY fault injection (PR #443, standing rule 16). Scoped to the
    // shared fused plane so the routed down plane and the packed routed
    // gate/up bank, which call this helper in both arms, stay pristine.
    let faultMode =
        ProcessInfo.processInfo.environment["DARKBLOOM_SHARED_QMV_FAULT"] ?? ""
    guard scales.size == {SHARED_PLANE_SCALE_BYTES},
        ["plane_byte", "plane_column", "plane_shift"].contains(faultMode)
    else {{
        return contiguous(concatenated([MLXArray(header), even]))
    }}
    var faultBytes = even.asArray(UInt8.self)
    let rowBytes = faultBytes.count / 1024
    switch faultMode {{
    case "plane_byte":
        faultBytes[1] ^= 1
    case "plane_column":
        for row in 0..<1024 {{
            faultBytes[row * rowBytes + 1] ^= 1
        }}
    default:
        for index in 0..<(faultBytes.count - 1) {{
            faultBytes[index] = faultBytes[index + 1]
        }}
    }}
    return contiguous(concatenated([MLXArray(header), MLXArray(faultBytes)]))
'''

EDITS = [
    (MODEL, FLAG_ANCHOR, FLAG_PATCH),
    (MODEL, PATCH_ANCHOR, PATCH_PATCH),
    (MODEL, ACT_ANCHOR, ACT_PATCH),
    (MODEL, NAME_ANCHOR, NAME_PATCH),
    (MODEL, VERIFY_ANCHOR, VERIFY_PATCH),
    (MODEL, TRACE_ANCHOR, TRACE_PATCH),
    (WEIGHTS, PLANE_ANCHOR, PLANE_PATCH),
]

MODES = (
    "plane_byte",
    "header_drop",
    "plane_column",
    "plane_shift",
    "activation_zero",
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
