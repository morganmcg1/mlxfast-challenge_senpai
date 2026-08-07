#!/usr/bin/env python3
"""Occupancy and DRAM re-read model for PR #293 (H2 skinny-N NAX tile downsize).

Reproduces the grid arithmetic of
Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp:298-330 for the
regular-NAX steel path and independently recomputes the assignment's DRAM
re-read table, so a disagreement with the brief is visible rather than assumed.

Research-only: never referenced by Sources/ and never on the submitted surface.
"""

M5_CORES = 40
ELEM_BYTES = 2  # bfloat16 operands as seen by the steel GEMM

# (label, M, N, K, count, routes_to)
# Shapes recovered from the Laguna XS 2.1 text tower at the pinned frontier.
# "split-K" classes never enter steel_matmul_regular_axpby_nax at all
# (matmul.cpp:986-989 admits them), so the proposed guard cannot see them.
CLASSES = [
    ("wq slide + dense gate/up", 512, 8192, 2048, 0, "regular-NAX"),
    ("wq full", 512, 6144, 2048, 0, "regular-NAX"),
    ("wk + wv  <-- TARGET", 512, 1024, 2048, 78, "regular-NAX"),
    ("L39 [K;V] bank", 512, 2048, 2048, 0, "regular-NAX"),
    ("wo slide / dense down", 512, 2048, 8192, 0, "split-K"),
    ("wo full", 512, 2048, 6144, 0, "split-K"),
    ("router", 512, 256, 2048, 0, "split-K"),
    ("g_proj", 512, 128, 2048, 0, "split-K"),
    # Decode-phase probes: M=1 shapes that DO reach the regular-NAX function
    # and must be excluded, because decode carries 75% of the score weight.
    ("decode wq/gate/up (M=1)", 1, 8192, 2048, 0, "regular-NAX"),
    ("decode wk+wv (M=1)", 1, 1024, 2048, 0, "regular-NAX"),
    ("decode L39 bank (M=1)", 1, 2048, 2048, 0, "regular-NAX"),
]

INCUMBENT = (64, 128, 256, 2, 4)  # bm, bn, bk, wm, wn on M5 (devc=='s')
CAND_A = (64, 64, 256, 2, 2)
CAND_B = (32, 64, 256, 2, 2)


def ceil_div(a, b):
    return -(-a // b)


def grid(M, N, tile):
    """matmul.cpp:298-330 with swizzle_log == 2 (unconditional on devc=='s')."""
    bm, bn = tile[0], tile[1]
    tiles_m, tiles_n = ceil_div(M, bm), ceil_div(N, bn)
    swizzle = 4  # 1 << swizzle_log, swizzle_log == 2
    tm, tn = ceil_div(tiles_m, swizzle), tiles_n * swizzle
    return tiles_m, tiles_n, tm * tn


def admitted(M, N, tile):
    """The guard proposed for matmul.cpp, evaluated on the incumbent tile."""
    bm, bn, _, _, wn = tile
    if not (bn == 128 and wn == 4 and N % 64 == 0):
        return False
    tiles_m, tiles_n = ceil_div(M, bm), ceil_div(N, bn)
    return tiles_m >= 4 and tiles_m * tiles_n <= 96


def dram_elems(M, N, K, tile):
    """A re-read once per N-tile column + B re-read once per M-tile row."""
    bm, bn = tile[0], tile[1]
    return ceil_div(M, bm) * K * N + ceil_div(N, bn) * M * K


def main():
    print(f"M5 Max: {M5_CORES} GPU cores. swizzle_log=2 => swizzle tile=4.\n")

    hdr = (f"{'class':<26} {'M':>5} {'N':>5} {'K':>5} {'route':<12} "
           f"{'tiles':>10} {'TG':>5} {'TG/core':>8}  {'guard':<8} "
           f"{'TG_new':>6} {'TG/core_new':>11}")
    print(hdr)
    print("-" * len(hdr))
    for label, M, N, K, cnt, route in CLASSES:
        tm_, tn_, tg = grid(M, N, INCUMBENT)
        hit = route == "regular-NAX" and admitted(M, N, INCUMBENT)
        if hit:
            _, _, tg_new = grid(M, N, CAND_A)
            new = f"{tg_new:>6} {tg_new / M5_CORES:>11.2f}"
        else:
            new = f"{'-':>6} {'-':>11}"
        print(f"{label:<26} {M:>5} {N:>5} {K:>5} {route:<12} "
              f"{tm_:>4}x{tn_:<5} {tg:>5} {tg / M5_CORES:>8.2f}  "
              f"{'ADMIT' if hit else 'exclude':<8} {new}")

    print("\nDRAM re-read for the admitted wk/wv class (512x1024x2048, 78 GEMMs):")
    print(f"{'tile':<22} {'elems':>12} {'MB/GEMM':>9} {'GB x78':>9} {'vs base':>8}")
    base = None
    for name, tile in (("incumbent 64/128", INCUMBENT), ("A 64/64", CAND_A),
                       ("B 32/64", CAND_B)):
        e = dram_elems(512, 1024, 2048, tile)
        mb = e * ELEM_BYTES / 1e6
        gb = mb * 78 / 1e3
        base = base or e
        print(f"{name:<22} {e:>12,} {mb:>9.1f} {gb:>9.2f} "
              f"{(e / base - 1) * 100:>7.0f}%")

    M, N, K = 512, 1024, 2048
    flops = 2 * M * N * K
    compulsory = (M * K + N * K + M * N) * ELEM_BYTES
    print(f"\nwk/wv arithmetic intensity, {flops / 1e9:.2f} GFLOP per GEMM:")
    print(f"  compulsory traffic only : {compulsory / 1e6:>6.2f} MB "
          f"-> {flops / compulsory:>6.0f} FLOP/byte  (the brief's 293 figure)")
    for name, tile in (("incumbent 64/128", INCUMBENT), ("A 64/64", CAND_A)):
        t = dram_elems(M, N, K, tile) * ELEM_BYTES
        print(f"  achieved, {name:<16}: {t / 1e6:>6.2f} MB "
              f"-> {flops / t:>6.0f} FLOP/byte")

    # Roofline sanity check on the re-read penalty. If the re-read really went
    # to DRAM it would cost more than the occupancy win is worth, so the
    # hypothesis depends on the working set being cache-resident.
    print("\nRe-read penalty if it were served from DRAM (~550 GB/s on M5 Max):")
    for name, tile in (("incumbent 64/128", INCUMBENT), ("A 64/64", CAND_A)):
        gb = dram_elems(M, N, K, tile) * ELEM_BYTES * 78 / 1e9
        print(f"  {name:<16} {gb:>5.2f} GB over 78 GEMMs -> {gb / 550 * 1e3:>5.2f} ms")
    ws = compulsory / 1e6
    print(f"  BUT the per-GEMM working set is only {ws:.1f} MB (A {M * K * ELEM_BYTES / 1e6:.1f}"
          f" + B {N * K * ELEM_BYTES / 1e6:.1f} + C {M * N * ELEM_BYTES / 1e6:.1f}),")
    print("  well inside an M-series Max system-level cache, so the extra")
    print("  re-reads should be SLC hits rather than DRAM traffic. This is the")
    print("  main quantitative risk to H2 and only the ranked M5 run resolves it.")


if __name__ == "__main__":
    main()
