#!/usr/bin/env python3
"""Static AIR census for the R107-C expert gather-GEMM BN ledger.

Reads the `air-objdump --disassemble` text for the BN=64 and BN=32
`fp_gather_qmm_rhs_expert_nax` instantiations and emits a rule-82 static
geometry / occupancy / byte ledger. No timing is measured or claimed.
"""
import json
import re
import sys

D = "research/artifacts/maple-alphonse-r107c"
VARIANTS = ("down-bn64", "down-bn32")

PATTERNS = {
    "dev_ld": r"^\s*%\S+ = (?:tail )?load .*addrspace\(1\)",
    "dev_st": r"^\s*store .*addrspace\(1\)",
    "tg_ld": r"^\s*%\S+ = (?:tail )?load .*addrspace\(3\)",
    "tg_st": r"^\s*store .*addrspace\(3\)",
    "const_ld": r"^\s*%\S+ = (?:tail )?load .*addrspace\(2\)",
    "barr": r"@air\.wg\.barrier",
    "mma_run": r"__tensorops_impl_matmul2d_op_run_cooperative",
    "mma_getptr": r"destination_tensor_get_element_pointer",
    "phi": r"^\s*%\S+ = phi ",
    "br": r"^\s*br ",
    "alloca": r"^\s*%\S+ = alloca ",
    "lifetime": r"llvm\.lifetime\.start",
    "insertelement": r"insertelement",
    "extractelement": r"extractelement",
    "fmul": r"^\s*%\S+ = fmul",
    "fadd": r"^\s*%\S+ = fadd",
    "memcpy": r"llvm\.memcpy",
    "store_slice_spec": r"BaseNAXFrag11store_slice",
}

# Compile-time geometry, from kernels/fp_quantized_nax.h and quantized.cpp.
GEOM = {
    "down-bn64": dict(BM=64, BN=64, BK=64, WM=4, WN=1),
    "down-bn32": dict(BM=64, BN=32, BK=64, WM=4, WN=1),
}
BK_PADDED = 72  # BK + 16/sizeof(bfloat16)
N_OUT = 2048
K_IN = 512
EGROUPS = 256


def census(name):
    lines = open(f"{D}/{name}.ir").read().splitlines()
    row = {"ir_lines": len(lines)}
    for key, pat in PATTERNS.items():
        rx = re.compile(pat)
        row[key] = sum(1 for l in lines if rx.search(l))
    g = GEOM[name]
    bn = g["BN"]
    row["threads_per_tg"] = g["WM"] * g["WN"] * 32
    row["simdgroups_per_tg"] = g["WM"] * g["WN"]
    row["tg_bytes_ws"] = bn * BK_PADDED * 2
    row["tg_bytes_total"] = row["tg_bytes_ws"] + 8  # + bounds[2]
    row["SM"] = g["BM"] // g["WM"]
    row["SN"] = bn // g["WN"]
    row["TN_frags"] = (bn // g["WN"]) // 16
    row["tgs_launched"] = (N_OUT // bn) * EGROUPS
    row["grid_dims"] = f"({N_OUT // bn}, {EGROUPS}, 1)"
    return row


def main():
    rows = {v: census(v) for v in VARIANTS}
    keys = list(rows[VARIANTS[0]].keys())
    w = max(len(k) for k in keys)
    print(f"{'metric'.ljust(w)}  {'BN=64':>12} {'BN=32':>12}  delta")
    print("-" * (w + 42))
    for k in keys:
        a, b = rows[VARIANTS[0]][k], rows[VARIANTS[1]][k]
        if isinstance(a, str):
            print(f"{k.ljust(w)}  {a:>12} {b:>12}  -")
        else:
            print(f"{k.ljust(w)}  {a:>12} {b:>12}  {b - a:+}")
    json.dump(rows, open(f"{D}/air-census.json", "w"), indent=2, sort_keys=True)
    print(f"\nwrote {D}/air-census.json")


if __name__ == "__main__":
    sys.exit(main())
