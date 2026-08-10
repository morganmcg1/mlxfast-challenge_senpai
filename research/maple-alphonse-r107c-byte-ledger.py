#!/usr/bin/env python3
"""Rule-82 static byte / geometry ledger for the R107-C expert down-projection
`bn` 64 -> 32 candidate.

Every quantity below is derived from the pinned Laguna geometry
(`Sources/MLXFastModel/LagunaConfig.swift`), the kernel's compile-time tiling
(`kernels/fp_quantized_nax.h`) and the host dispatch in `quantized.cpp`. The
only measured inputs are the two `staticThreadgroupMemoryLength` values and the
resident-threadgroup census, both recorded in the report. No millisecond is
claimed for this host.
"""
import json

# Pinned model geometry.
LAYERS_MOE = 39  # layers 1..39; layer 0 is a dense MLP
EXPERTS = 256
TOP_K = 8
PREFILL_TOKENS = 512
HIDDEN = 2048
MOE_INTERMEDIATE = 512
GROUP = 16

ROWS_TOTAL = PREFILL_TOKENS * TOP_K  # 4096 expanded rows
ROWS_PER_EXPERT = ROWS_TOTAL // EXPERTS  # 16 mean rows per expert

# Down projection: y[M, N] = x[M, K] @ w[N, K]^T, per expert.
N_OUT = HIDDEN  # 2048
K_IN = MOE_INTERMEDIATE  # 512

BM, BK, WM, WN = 64, 64, 4, 1
SM = BM // WM  # 16 rows per simdgroup
THREADS_PER_TG = WM * WN * 32  # 128

# Measured pipeline facts (see report; probe = maple-alphonse-r107c-pipeline-probe.swift).
TG_BYTES = {64: 9232, 32: 4624}
# Measured resident-threadgroup census, max over 5 reps at 128 threads/threadgroup
# (maple-alphonse-r107c-occupancy-census.swift; full curve archived as
# artifacts/maple-alphonse-r107c/occupancy-census.csv).
RESIDENT_TGS = {64: 133, 32: 165}
CENSUS_CURVE = {0: 216, 1024: 222, 2048: 210, 4096: 227, 4624: 165, 6144: 152,
                8192: 137, 9232: 133, 12288: 127, 16384: 118, 24576: 116,
                32768: 103}
GPU_CORES = 20  # this host: Apple M4 Pro, 20 GPU cores


def per_expert_weight_bytes():
    packed = N_OUT * (K_IN // 2)
    scales = N_OUT * (K_IN // GROUP)
    return packed + scales


def ledger(bn):
    n_tiles = N_OUT // bn
    tgs_per_layer = n_tiles * EXPERTS
    # Weight staging: each threadgroup stages its own bn-wide column band once
    # per M chunk. One M chunk per expert at mean routing (16 rows <= BM).
    w_bytes_per_tg = bn * (K_IN // 2) + bn * (K_IN // GROUP)
    w_bytes_layer = tgs_per_layer * w_bytes_per_tg
    # A operand: only simdgroups with sgp_sm > 0 read x. At 16 mean rows and
    # SM = 16 that is simdgroup 0 alone.
    active_sgs = min(WM * WN, -(-ROWS_PER_EXPERT // SM))
    a_bytes_per_tg = ROWS_PER_EXPERT * K_IN * 2
    a_bytes_layer = tgs_per_layer * a_bytes_per_tg
    # Output: each element written exactly once.
    y_bytes_layer = ROWS_TOTAL * N_OUT * 2
    resident = RESIDENT_TGS[bn]
    return dict(
        bn=bn,
        grid_dims=f"({n_tiles}, {EXPERTS}, 1)",
        tgs_per_layer=tgs_per_layer,
        threads_per_tg=THREADS_PER_TG,
        simdgroups_per_tg=WM * WN,
        mma_active_simdgroups_per_tg=active_sgs,
        SN=bn // WN,
        dtile_frags_TMxTN=(SM // 16) * ((bn // WN) // 16),
        tg_bytes_measured=TG_BYTES[bn],
        weight_bytes_per_tg=w_bytes_per_tg,
        weight_bytes_per_layer=w_bytes_layer,
        weight_bytes_family_gb=w_bytes_layer * LAYERS_MOE / 1e9,
        a_bytes_per_tg=a_bytes_per_tg,
        a_reread_multiplicity=n_tiles,
        a_bytes_per_layer=a_bytes_layer,
        a_bytes_family_gb=a_bytes_layer * LAYERS_MOE / 1e9,
        a_unique_bytes_per_layer=ROWS_TOTAL * K_IN * 2,
        y_bytes_per_layer=y_bytes_layer,
        resident_tgs_measured=resident,
        resident_tgs_per_core=round(resident / GPU_CORES, 2),
        resident_simdgroups_per_core=round(resident * WM * WN / GPU_CORES, 2),
        resident_threads=resident * THREADS_PER_TG,
        weight_bytes_in_flight_per_core=round(
            resident / GPU_CORES * (bn * (BK // 2) + bn * (BK // GROUP))),
    )


def main():
    rows = [ledger(64), ledger(32)]
    keys = [k for k in rows[0] if k != "bn"]
    w = max(len(k) for k in keys)
    print(f"{'quantity'.ljust(w)}  {'bn=64':>16} {'bn=32':>16}  ratio")
    print("-" * (w + 56))
    for k in keys:
        a, b = rows[0][k], rows[1][k]
        if isinstance(a, str):
            print(f"{k.ljust(w)}  {a:>16} {b:>16}  -")
        else:
            r = "-" if not a else f"{b / a:.3f}x"
            fa = f"{a:.4g}" if isinstance(a, float) else f"{a}"
            fb = f"{b:.4g}" if isinstance(b, float) else f"{b}"
            print(f"{k.ljust(w)}  {fa:>16} {fb:>16}  {r}")
    out = "research/artifacts/maple-alphonse-r107c/byte-ledger.json"
    json.dump({str(r["bn"]): r for r in rows}, open(out, "w"), indent=2, sort_keys=True)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
