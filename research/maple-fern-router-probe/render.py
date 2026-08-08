#!/usr/bin/env python3
"""Render router Top-8 butterfly variants and run the offline AIR census (PR #442).

Extracts `lagunaDecodeRouterOrdinalHeader` and `lagunaRouterTop8PrologueHeader`
verbatim from LagunaRuntimeModel.swift, substitutes each butterfly variant, and
emits a standalone `.metal` file whose `[[kernel]] void probe(...)` signature
`main.swift` binds by buffer index.

The census compiles with the same flags MLX's `Device::build_library_` uses
(`fastMathEnabled = false`) and counts `air.simd_shuffle_xor.*` call sites.

usage: python3 render.py [out_dir]
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SWIFT = ROOT / "Sources/MLXFastModel/LagunaRuntimeModel.swift"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/maple_fern_router_probe")

SCALAR = """    for (ushort offset = 16; offset > 0; offset >>= 1) {
        uint other_ordinal = simd_shuffle_xor(best_ordinal, offset);
        uint other_index = simd_shuffle_xor(best_index, offset);
        if (laguna_router_ordinal_before(
            other_ordinal, other_index, best_ordinal, best_index)) {
            best_ordinal = other_ordinal;
            best_index = other_index;
        }
    }"""

UINT2 = """    for (ushort offset = 16; offset > 0; offset >>= 1) {
        uint2 other = simd_shuffle_xor(uint2(best_ordinal, best_index), offset);
        if (laguna_router_ordinal_before(
            other.x, other.y, best_ordinal, best_index)) {
            best_ordinal = other.x;
            best_index = other.y;
        }
    }"""

# Stage-3 fault injection. Arm A drops butterfly offset 16; arm B swaps the two
# packed lanes; arm C is a byte-identical copy of the shipped scalar butterfly.
FAULT_A = UINT2.replace("ushort offset = 16", "ushort offset = 8")
FAULT_B = UINT2.replace(
    "uint2(best_ordinal, best_index)", "uint2(best_index, best_ordinal)")

# Timing-only counterfactuals. They are numerically wrong on purpose: they hold
# the comparator and loop shape fixed and vary only the hardware shuffle count,
# so `half` is exactly what the uint2 arm would cost if `simd_shuffle_xor` on a
# `uint2` lowered to a single hardware shuffle, and `none` bounds the total
# butterfly shuffle cost.
HALF_SHUFFLES = SCALAR.replace(
    "        uint other_index = simd_shuffle_xor(best_index, offset);",
    "        uint other_index = best_index ^ (uint)offset;")
NO_SHUFFLES = HALF_SHUFFLES.replace(
    "        uint other_ordinal = simd_shuffle_xor(best_ordinal, offset);",
    "        uint other_ordinal = best_ordinal ^ (uint)offset;")

VARIANTS = {
    "scalar": SCALAR,
    "uint2": UINT2,
    "faultA_offset8": FAULT_A,
    "faultB_swapped": FAULT_B,
    "faultC_control": SCALAR,
    "cf_half_shuffles": HALF_SHUFFLES,
    "cf_no_shuffles": NO_SHUFFLES,
}

PROBE = """
[[kernel]] void probe(
    const device float* raw_keys [[buffer(0)]],
    device uint* out [[buffer(1)]],
    const device uint* params [[buffer(2)]],
    uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
    uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
    uint thread_index_in_simdgroup [[thread_index_in_simdgroup]]) {
    uint case_id = threadgroup_position_in_grid.x * 2u
        + simdgroup_index_in_threadgroup;
    uint lane = thread_index_in_simdgroup;
    uint repeats = params[0];
    uint sink = params[1];
    const device float* keys = raw_keys + case_id * 256u;
    uint acc = 0u;
    for (uint rep = 0; rep < repeats; ++rep) {
        thread uint top8_keys[8];
        for (uint j = 0; j < 8; ++j) {
            top8_keys[j] = laguna_router_key_ordinal(
                keys[lane + 32u * j + (acc & sink)]);
        }
        uint top8_mask = 0u;
        for (uint r = 0; r < 8; ++r) {
            uint winner = laguna_router_top8_extract_round(
                top8_keys, top8_mask, lane);
            acc += winner;
            if (rep == 0u && lane == 0u) {
                out[case_id * 8u + r] = winner;
            }
        }
    }
    if (lane == 0u && (acc & sink) != 0u) {
        out[case_id * 8u] ^= acc;
    }
}
"""


def literal(name: str) -> str:
    text = SWIFT.read_text()
    m = re.search(r'let %s = """\n(.*?)\n"""' % name, text, re.S)
    if not m:
        raise SystemExit(f"literal {name} not found in {SWIFT}")
    return m.group(1)


def compile_ir(src: Path) -> Path:
    ll = src.with_suffix(".ll")
    cmd = [
        "xcrun", "-sdk", "macosx", "metal", "-x", "metal", "-std=metal4.0",
        "-Wall", "-Wno-c++17-extensions", "-Wno-c++20-extensions",
        "-fno-fast-math", "-S", "-emit-llvm", str(src), "-o", str(ll),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout + r.stderr)
        raise SystemExit(f"compile failed for {src}")
    return ll


def census(ll: Path) -> dict:
    text = ll.read_text()
    counts: dict = {}
    for m in re.finditer(r"@(air\.simd_shuffle_xor[\w.]*)", text):
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    for m in re.finditer(r"^declare .*@(air\.simd_shuffle_xor[\w.]*)", text, re.M):
        counts[m.group(1)] -= 1
    return counts


def main() -> None:
    ordinal = literal("lagunaDecodeRouterOrdinalHeader")
    prologue = literal("lagunaRouterTop8PrologueHeader")
    if SCALAR not in prologue:
        raise SystemExit("shipped scalar butterfly not found in prologue header")
    OUT.mkdir(parents=True, exist_ok=True)
    for tag, butterfly in VARIANTS.items():
        src = OUT / f"router_{tag}.metal"
        src.write_text(
            "#include <metal_stdlib>\n#include <metal_simdgroup>\n"
            "using namespace metal;\n\n"
            + ordinal + "\n\n"
            + prologue.replace(SCALAR, butterfly) + "\n"
            + PROBE
        )
        print(f"{tag:16s} {src}  {census(compile_ir(src))}")


if __name__ == "__main__":
    main()
