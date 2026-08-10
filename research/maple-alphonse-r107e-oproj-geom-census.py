#!/usr/bin/env python3
"""R107-E static ledger for the decode NVFP4 output-projection geometry sweep.

Emits the resolved kernel body straight out of the shipped Swift generator (not
a transliteration of it), wraps it in the signature MLX's `metal_kernel` writes,
compiles each arm offline with `xcrun metal`, and censuses the AIR.

Two things this establishes that timing alone cannot:

1. The G0 arm's emitted MSL is byte-identical to the pre-parameterisation base.
   That is what licenses using `DARKBLOOM_OPROJ_GEOM` unset as the paired
   baseline instead of a separate unchanged-base build.
2. The device-load instruction count per unit FMA work, which is the quantity
   the amortisation hypothesis actually predicts. `T = B/BW + L` is fitted from
   timing; this file supplies the `L` side's instruction budget.

No timing is measured or claimed here.

Usage: research/maple-alphonse-r107e-oproj-geom-census.py [BASE_SHA]
"""
import json
import os
import re
import subprocess
import sys

SRC = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
OUT = "research/artifacts/maple-alphonse-r107e"
FN = "func lagunaGatedAffineOProjNVFP4Source("
END = "private let lagunaGatedAffineOProjNVFP4Kernels"

# (num_simdgroups, results_per_simdgroup) per the assignment's arm table.
ARMS = {
    "g0": (2, 4),
    "g1": (2, 8),
    "g2": (1, 8),
    "g3": (4, 4),
}
HEADS = (64, 48)
OUT_VEC = 2048
HEAD_DIM = 128

STUBS = """import Foundation

enum LagunaConstants {
    static let hiddenSize = 2_048
    static let headDim = 128
    static let fullAttentionHeads = 48
    static let slidingAttentionHeads = 64
}

// Every gate below defaults ON in the runtime (`env != "0"`), so the resolved
// emission this ledger compiles is the one the scored decode path dispatches.
let lagunaNvfp4QmvSignCarryEnabled = true
let lagunaNvfp4QmvSeedElisionEnabled = true
let lagunaNvfp4ScaleFoldEnabled = true
let lagunaE4M3SignDomainCertified = true
"""

MAIN_PARAM = """
let a = CommandLine.arguments
print(lagunaGatedAffineOProjNVFP4Source(
    heads: Int(a[1])!, preActivatedGate: true, laneMajor: true, pairwise: true,
    numSimdgroups: Int(a[2])!, resultsPerSimdgroup: Int(a[3])!), terminator: "")
"""

MAIN_PLAIN = """
let a = CommandLine.arguments
print(lagunaGatedAffineOProjNVFP4Source(
    heads: Int(a[1])!, preActivatedGate: true, laneMajor: true,
    pairwise: true), terminator: "")
"""

# Mirrors mlx/backend/common/metal_kernel.cpp write_signature(): every input is
# `device` here because max_constant_array_size is 8 *elements*.
SIGNATURE = """#include <metal_stdlib>
#include <metal_simdgroup>
using namespace metal;

[[kernel]] void {name}(
  const device bfloat* attention_output [[buffer(0)]],
  const device bfloat* gate_values [[buffer(1)]],
  const device uint32_t* weight_codes [[buffer(2)]],
  const device uint8_t* scale_nibbles [[buffer(3)]],
  const device uint8_t* scale_bases [[buffer(4)]],
  const device uint8_t* weight_scales [[buffer(5)]],
  device bfloat* projected [[buffer(6)]],
  uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
  uint3 thread_position_in_threadgroup [[thread_position_in_threadgroup]],
  uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
  uint thread_index_in_simdgroup [[thread_index_in_simdgroup]]) {{
{body}
}}
"""

PATTERNS = {
    "dev_ld": r"^\s*%\S+ = (?:tail )?load .*addrspace\(1\)",
    "dev_st": r"^\s*store .*addrspace\(1\)",
    "tg_ld": r"^\s*%\S+ = (?:tail )?load .*addrspace\(3\)",
    "tg_st": r"^\s*store .*addrspace\(3\)",
    "const_ld": r"^\s*%\S+ = (?:tail )?load .*addrspace\(2\)",
    "barr": r"@air\.wg\.barrier",
    "simd_sum": r"air\.simd_sum",
    "alloca": r"^\s*%\S+ = alloca ",
    "fmul": r"^\s*%\S+ = fmul",
    "fadd": r"^\s*%\S+ = fadd",
    "br": r"^\s*br ",
    "phi": r"^\s*%\S+ = phi ",
}


def run(argv, **kw):
    return subprocess.run(argv, check=True, capture_output=True, text=True, **kw)


def extract(text):
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith(FN))
    stop = next(i for i, l in enumerate(lines) if l.startswith(END))
    return "\n".join(lines[start:stop]).rstrip() + "\n"


def build_emitter(fn_text, path):
    parameterised = "numSimdgroups" in fn_text.split(") -> String {")[0]
    with open(path, "w") as fh:
        fh.write(STUBS + "\n" + fn_text)
        fh.write(MAIN_PARAM if parameterised else MAIN_PLAIN)
    binary = path[:-6]
    run(["xcrun", "swiftc", "-O", "-o", binary, path])
    return binary, parameterised


def emit(binary, parameterised, heads, geom):
    argv = [binary, str(heads)]
    if parameterised:
        argv += [str(geom[0]), str(geom[1])]
    return run(argv).stdout


def census(ir_path):
    lines = open(ir_path).read().splitlines()
    row = {"ir_lines": len(lines)}
    for key, pat in PATTERNS.items():
        rx = re.compile(pat)
        row[key] = sum(1 for l in lines if rx.search(l))
    return row


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else None
    os.makedirs(OUT, exist_ok=True)
    ledger = {"host_note": "static AIR ledger; no timing measured", "arms": {}}

    head_fn = extract(open(SRC).read())
    head_bin, head_param = build_emitter(head_fn, f"{OUT}/emit-head.swift")
    if not head_param:
        sys.exit("working tree generator is not parameterised")

    # Invariant 1: the G0 emission must survive the refactor unchanged.
    if base:
        base_src = run(["git", "show", f"{base}:{SRC}"]).stdout
        base_bin, base_param = build_emitter(extract(base_src), f"{OUT}/emit-base.swift")
        identical = {}
        for heads in HEADS:
            a = emit(base_bin, base_param, heads, ARMS["g0"])
            b = emit(head_bin, head_param, heads, ARMS["g0"])
            identical[f"h{heads}"] = a == b
            if a != b:
                with open(f"{OUT}/g0-drift-h{heads}.diff", "w") as fh:
                    fh.write(a)
        ledger["g0_emission_identical_to_base"] = identical
        ledger["base_sha"] = base

    for arm, geom in ARMS.items():
        ns, rps = geom
        rows_per_tg = ns * rps
        threads_per_tg = ns * 32
        arm_row = {
            "num_simdgroups": ns,
            "results_per_simdgroup": rps,
            "rows_per_threadgroup": rows_per_tg,
            "threads_per_threadgroup": threads_per_tg,
            "threadgroups": OUT_VEC // rows_per_tg,
            "grid_threads": (OUT_VEC // rows_per_tg) * threads_per_tg,
            "heads": {},
        }
        for heads in HEADS:
            body = emit(head_bin, head_param, heads, geom)
            name = f"oproj_{arm}_h{heads}"
            metal = f"{OUT}/{name}.metal"
            with open(metal, "w") as fh:
                fh.write(SIGNATURE.format(name=name, body=body))
            ir = f"{OUT}/{name}.ir"
            log = f"{OUT}/{name}.compile.log"
            cmd = [
                "xcrun", "metal", "-std=metal4.0", "-fno-fast-math",
                "-S", "-emit-llvm", metal, "-o", ir,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            with open(log, "w") as fh:
                fh.write(proc.stdout + proc.stderr)
            if proc.returncode != 0:
                arm_row["heads"][f"h{heads}"] = {"compiled": False}
                continue
            row = census(ir)
            row["compiled"] = True
            # k-blocks each thread walks: in_vec_size / (values_per_thread*32).
            row["k_blocks"] = (heads * HEAD_DIM) // 512
            # FMA-equivalent products per thread over the whole dispatch.
            row["products_per_thread"] = row["k_blocks"] * 16 * rps
            arm_row["heads"][f"h{heads}"] = row
        ledger["arms"][arm] = arm_row

    path = f"{OUT}/geom-air-ledger.json"
    with open(path, "w") as fh:
        json.dump(ledger, fh, indent=2, sort_keys=True)
    print(json.dumps(ledger, indent=2, sort_keys=True))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
