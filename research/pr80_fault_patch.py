#!/usr/bin/env python3
"""Apply the PR80 fault-injection harness to the two scored sources.

Research-only. The patch adds `DARKBLOOM_PR80_FAULT` / `DARKBLOOM_PR80_BYPASS_CERT`
so one build can serve every fault arm; it must be reverted before submission.

Usage:
    research/pr80_fault_patch.py apply
    research/pr80_fault_patch.py check
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEIGHTS = ROOT / "Sources/MLXFastModel/LagunaRuntimeWeights.swift"
MODEL = ROOT / "Sources/MLXFastModel/LagunaRuntimeModel.swift"

GLOBALS = '''/// Research-only fault injection for the PR80 bitwise logit certificate.
let lagunaPR80Fault = ProcessInfo.processInfo.environment["DARKBLOOM_PR80_FAULT"] ?? ""
let lagunaPR80BypassCert =
    ProcessInfo.processInfo.environment["DARKBLOOM_PR80_BYPASS_CERT"] == "1"

'''

EDITS = [
    # ---- LagunaRuntimeWeights.swift -------------------------------------
    (
        WEIGHTS,
        "/// Packs a uint8 NVFP4 scale plane into `LagunaLaneMajorScaleBank`.",
        GLOBALS + "/// Packs a uint8 NVFP4 scale plane into `LagunaLaneMajorScaleBank`.",
    ),
    (
        WEIGHTS,
        "    var fits = span .<= 15\n",
        "    var fits = span .<= 15\n"
        '    if lagunaPR80Fault == "D-F2" { fits = span .>= 0 }\n',
    ),
    (
        WEIGHTS,
        "    if pairwise {\n"
        "        fits = fits .&& (halves[0] .== halves[1]).all(axes: [1, 2, 3]).reshaped([rows, 1])\n"
        "        kept = halves[0]\n"
        "    }\n",
        "    if pairwise {\n"
        '        if lagunaPR80Fault != "D-F1" {\n'
        "            fits =\n"
        "                fits\n"
        "                .&& (halves[0] .== halves[1]).all(axes: [1, 2, 3]).reshaped([rows, 1])\n"
        "        }\n"
        "        kept = halves[0]\n"
        "    }\n"
        '    if lagunaPR80Fault == "P-F1" {\n'
        "        let flat = kept.reshaped([rows, -1])\n"
        "        let parts = flat.split(indices: [1], axis: 1)\n"
        "        kept = concatenated([parts[1], parts[0]], axis: 1)\n"
        "    }\n",
    ),
    (
        WEIGHTS,
        "    let u16 = contiguous(index).view(dtype: .uint16)\n"
        "    let nibbles = contiguous(\n"
        "        ((u16 & MLXArray(UInt16(0x000F)))\n"
        "            | ((u16 >> 4) & MLXArray(UInt16(0x00F0)))).asType(.uint8))\n",
        "    let u16 = contiguous(index).view(dtype: .uint16)\n"
        "    let nibbles = contiguous(\n"
        '        (lagunaPR80Fault == "P-F2"\n'
        "            ? (((u16 >> 8) & MLXArray(UInt16(0x000F)))\n"
        "                | ((u16 << 4) & MLXArray(UInt16(0x00F0))))\n"
        "            : ((u16 & MLXArray(UInt16(0x000F)))\n"
        "                | ((u16 >> 4) & MLXArray(UInt16(0x00F0))))).asType(.uint8))\n",
    ),
    (
        WEIGHTS,
        "    guard lagunaLaneMajorScaleBankReproducesScales(bank, scales) else {\n",
        "    guard lagunaPR80BypassCert || lagunaLaneMajorScaleBankReproducesScales(bank, scales)\n"
        "    else {\n",
    ),
    # ---- LagunaRuntimeModel.swift: QKV kernel ---------------------------
    (
        MODEL,
        '            + \\(pairwise ? "(simd_lid >> 1)" : "simd_lid");',
        '            + \\(pairwise ? lagunaPR80KFOne("(simd_lid >> 1)") : "simd_lid");',
    ),
    (
        MODEL,
        "            sb[b] = uint8_t(row_base + ((packed >> (b << 2)) & 0x0Fu));",
        "            sb[b] = uint8_t(row_base + ((packed >> \\(lagunaPR80QKVShift)) & 0x0Fu));",
    ),
    (
        MODEL,
        "    thread uint8_t sb[blocks_per_row];\n"
        "    const uint8_t row_base = scale_bases[out_row];\n"
        "    if (row_base != 0xFFu) {",
        "    thread uint8_t sb[blocks_per_row];\n"
        "    const uint8_t row_base = scale_bases[out_row];\n"
        "    if (\\(lagunaPR80QKVEscape)) {",
    ),
    # ---- LagunaRuntimeModel.swift: o_proj kernel ------------------------
    (
        MODEL,
        '    let laneIdx = pairwise ? "(simd_lid >> 1)" : "simd_lid"',
        '    let laneIdx = pairwise ? lagunaPR80KFOne("(simd_lid >> 1)") : "simd_lid"',
    ),
    (
        MODEL,
        "        uint nsh = 0;",
        "        uint nsh = \\(lagunaPR80Fault == \"K-F2\" ? 4 : 0);",
    ),
    (
        MODEL,
        "            const bool esc = rb == 0xFFu;",
        "            const bool esc = \\(lagunaPR80OProjEscape);",
    ),
    # ---- LagunaRuntimeModel.swift: kernel-name fault tags ---------------
    (
        MODEL,
        'name: "laguna_decode_nvfp4_qkv_h\\(heads)_r1_v1_lm1"',
        'name: "laguna_decode_nvfp4_qkv_h\\(heads)_r1_v1_lm1" + lagunaPR80Tag',
    ),
    (
        MODEL,
        'name: "laguna_gated_affine_oproj_nvfp4_qmv_h\\(heads)_v1_lm1"',
        'name: "laguna_gated_affine_oproj_nvfp4_qmv_h\\(heads)_v1_lm1" + lagunaPR80Tag',
    ),
    (
        MODEL,
        'name: "laguna_oproj_act_h\\(heads)_v1_lm1"',
        'name: "laguna_oproj_act_h\\(heads)_v1_lm1" + lagunaPR80Tag',
    ),
]

MODEL_HELPERS = '''/// Research-only PR80 fault-injection helpers; reverted before submission.
let lagunaPR80Tag = lagunaPR80Fault.isEmpty
    ? "" : "_f" + lagunaPR80Fault.lowercased().replacingOccurrences(of: "-", with: "")
func lagunaPR80KFOne(_ expr: String) -> String {
    lagunaPR80Fault == "K-F1" ? "((simd_lid >> 1) ^ 1)" : expr
}
let lagunaPR80QKVShift = lagunaPR80Fault == "K-F2" ? "((b ^ 1) << 2)" : "(b << 2)"
let lagunaPR80QKVEscape = lagunaPR80Fault == "K-F3" ? "true" : "row_base != 0xFFu"
let lagunaPR80OProjEscape = lagunaPR80Fault == "K-F3" ? "false" : "rb == 0xFFu"

'''


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    texts = {p: p.read_text() for p in (WEIGHTS, MODEL)}
    if "lagunaPR80Fault" in texts[WEIGHTS]:
        print("already patched")
        return 0
    if mode != "apply":
        for path, old, _ in EDITS:
            n = texts[path].count(old)
            print(f"{n}  {path.name}: {old.splitlines()[0][:70]}")
        return 0
    for path, old, new in EDITS:
        n = texts[path].count(old)
        if n != 1:
            raise SystemExit(f"anchor matched {n}x in {path.name}: {old[:80]!r}")
        texts[path] = texts[path].replace(old, new)
    anchor = "private func lagunaDecodeNVFP4QKVLaneMajorSource"
    texts[MODEL] = texts[MODEL].replace(anchor, MODEL_HELPERS + anchor, 1)
    for path, text in texts.items():
        path.write_text(text)
    print("patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
