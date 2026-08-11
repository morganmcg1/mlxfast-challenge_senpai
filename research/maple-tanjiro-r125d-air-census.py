#!/usr/bin/env python3
"""Static AIR + byte ledger for the R125-D routed-down BN ladder.

Reads `air-objdump --disassemble` text for the BN in {32,64,128}
`fp_gather_qmm_rhs_expert_nax` instantiations of the down shape
(K=512, N=2048, eg=256, bm=64, bk=64, wm=4, wn=1) and emits the static
geometry / traffic / instantiation-validity ledger. No timing is claimed:
this host is Apple GPU generation 16, so the kernel is unreachable at
runtime here and only offline compilation evidence is available.

Usage: research/maple-tanjiro-r125d-air-census.py [BN ...]   (default 32 64 128)
"""
import json
import re
import sys

D = "research/artifacts/tanjiro-r125d"

PATTERNS = {
    "dev_ld": r"^\s*%\S+ = (?:tail )?load .*addrspace\(1\)",
    "dev_st": r"^\s*store .*addrspace\(1\)",
    "tg_ld": r"^\s*%\S+ = (?:tail )?load .*addrspace\(3\)",
    "tg_st": r"^\s*store .*addrspace\(3\)",
    "barr": r"@air\.wg\.barrier",
    "mma_run": r"__tensorops_impl_matmul2d_op_run_cooperative",
    "mma_getptr": r"destination_tensor_get_element_pointer",
    "alloca": r"^\s*%\S+ = alloca ",
    "insertelement": r"insertelement",
    "extractelement": r"extractelement",
    "fmul": r"^\s*%\S+ = fmul",
    "fadd": r"^\s*%\S+ = fadd",
    "store_slice_spec": r"BaseNAXFrag11store_slice",
}

BM, BK, WM, WN = 64, 64, 4, 1
BK_PADDED = BK + 8            # BK + 16/sizeof(bfloat16)
N_OUT, K_IN, EGROUPS = 2048, 512, 256
ROWS = 512 * 8            # routed rows per MoE layer (512 prefill tokens x top-8)
MOE_LAYERS = 38
BYTES_PER_W_ELEM = 0.5625     # 4-bit weight + pairwise fp8 scale (9/16 byte)


def census(bn):
    lines = open(f"{D}/down-bn{bn}.ir").read().splitlines()
    row = {"BN": bn, "ir_lines": len(lines)}
    for key, pat in PATTERNS.items():
        rx = re.compile(pat)
        row[key] = sum(1 for line in lines if rx.search(line))
    row["SM"] = BM // WM
    row["SN"] = bn // WN
    row["TM_frags"] = (BM // WM) // 16
    row["TN_frags"] = (bn // WN) // 16
    row["threads_per_tg"] = WM * WN * 32
    row["simdgroups_per_tg"] = WM * WN
    row["tg_bytes_ws"] = bn * BK_PADDED * 2
    row["tg_bytes_total"] = row["tg_bytes_ws"] + 8      # + bounds[2]
    row["tgs_per_layer"] = (N_OUT // bn) * EGROUPS
    row["grid_dims"] = f"({N_OUT // bn}, {EGROUPS}, 1)"
    # Traffic per MoE layer, down projection only.
    row["w_bytes_per_layer_mb"] = round(
        N_OUT * K_IN * EGROUPS * BYTES_PER_W_ELEM / 1e6, 2)
    unique_x_mb = ROWS * K_IN * 2 / 1e6
    row["x_unique_mb"] = round(unique_x_mb, 3)
    row["x_reread_per_layer_mb"] = round((N_OUT // bn) * unique_x_mb, 2)
    row["x_reread_family_gb"] = round(
        MOE_LAYERS * (N_OUT // bn) * unique_x_mb / 1e3, 3)
    # Per-iteration staged weight bytes (one SK step stages BN x SK elems).
    row["staged_bytes_per_sk_step"] = int(bn * 32 * BYTES_PER_W_ELEM)
    return row


def main():
    bns = [int(a) for a in sys.argv[1:]] or [32, 64, 128]
    rows = [census(b) for b in bns]
    keys = [k for k in rows[0]]
    w = max(len(k) for k in keys)
    head = "  ".join(f"BN={r['BN']:>4}".rjust(12) for r in rows)
    print(f"{'metric'.ljust(w)}  {head}")
    print("-" * (w + 14 * len(rows)))
    for k in keys:
        cells = "  ".join(f"{r[k]!s:>12}" for r in rows)
        print(f"{k.ljust(w)}  {cells}")
    out = {f"down-bn{r['BN']}": r for r in rows}
    json.dump(out, open(f"{D}/air-census.json", "w"), indent=2, sort_keys=True)
    print(f"\nwrote {D}/air-census.json")


if __name__ == "__main__":
    sys.exit(main())
