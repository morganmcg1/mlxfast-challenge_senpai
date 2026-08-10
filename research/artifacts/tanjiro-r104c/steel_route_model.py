#!/usr/bin/env python3
"""R104-C: one deterministic route model for the prefill steel-GEMM path.

The model is a direct transcription of the routing/tile/swizzle predicates in
Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp at base
9527bb727caad1c495e6b62ecbf2445a25e937dd.  It is run twice:

  Tier 2 (validation): use_nax=False, devc='s'  -> must reproduce all 237
      observed M4 Pro rows exactly, kernel name and grid/group included.
  Tier 1 (derivation): use_nax=True,  devc='s'  -> the M5 Max prediction.

Reproducing the observed configuration exactly is the only evidence that the
derived configuration is trustworthy; the two tiers are never merged.

Usage:
  python3 steel_route_model.py            # validate + emit CSV/JSON
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import sys
from dataclasses import dataclass, asdict, field

HERE = os.path.dirname(os.path.abspath(__file__))
OBSERVED = os.path.join(HERE, "steel_dispatch_order_m4.txt")

M5_CORES = 40  # M5 Max GPU cores (official ranked host)
M4_CORES = 20  # M4 Pro GPU cores (this host)


# --------------------------------------------------------------------------
# matmul.cpp transcription
# --------------------------------------------------------------------------

def next_pow2(n: int) -> int:
    """mlx::core::next_power_of_2 semantics for positive n."""
    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()


def get_block_dims(dim0: int, dim1: int, dim2: int, pow2: int = 10):
    """metal/utils.h get_block_dims."""
    pows = [0, 0, 0]
    sum_pows = 0
    while True:
        presum = sum_pows
        for i, d in enumerate((dim0, dim1, dim2)):
            if (1 << (pows[i] + 1)) > d:
                continue
            pows[i] += 1
            sum_pows += 1
            if sum_pows == 10 or sum_pows == pow2:
                break
        if sum_pows == presum or sum_pows == 10 or sum_pows == pow2:
            break
    return (1 << pows[0], 1 << pows[1], 1 << pows[2])


@dataclass
class Route:
    path: str            # "splitk" | "regular"
    nax: bool
    kernel: str
    bm: int
    bn: int
    bk: int
    wm: int
    wn: int
    parts: int | None
    psize: int | None
    swizzle_log: int
    grid: tuple
    group: tuple
    predicate_line: str


def route(M: int, N: int, K: int, *, use_nax: bool, devc: str,
          prefill_tile: bool = True,
          a_dtype: str = "bfloat16", out_dtype: str = "bfloat16",
          transpose_a: bool = False, transpose_b: bool = True,
          batch_size_out: int = 1) -> Route:
    """steel_matmul_axpby top-level decision, matmul.cpp:888-960."""
    _tm = -(-M // 16)          # :888
    _tn = -(-N // 16)          # :889
    _tk = K // 16              # :890

    min_tmn = 2048 if devc in ("s", "d") else 1024   # :896

    ta = "t" if transpose_a else "n"
    tb = "t" if transpose_b else "n"

    # ---- non-NAX split-K, :898 -------------------------------------------
    if (not use_nax and batch_size_out == 1 and (_tm * _tn) <= min_tmn
            and _tk >= 8 and K >= max(M, N)):
        return _splitk_nonnax(M, N, K, ta, tb, a_dtype, out_dtype)

    # ---- NAX split-K, :922 -----------------------------------------------
    if (use_nax and batch_size_out == 1
            and (K >= 3 * max(M, N)
                 or (max(M, N) <= 1024 and K > 2 * max(M, N)))):
        return _splitk_nax(M, N, K, ta, tb, a_dtype, out_dtype, devc,
                           prefill_tile)

    # ---- regular, :957 ----------------------------------------------------
    if use_nax:
        return _regular_nax(M, N, K, ta, tb, a_dtype, out_dtype, devc)
    return _regular_nonnax(M, N, K, ta, tb, a_dtype, out_dtype, devc)


def _splitk_nonnax(M, N, K, ta, tb, a_dtype, out_dtype) -> Route:
    """steel_gemm_splitk_axpby, matmul.cpp:528-598."""
    bm = 16 if M < 40 else 32                 # :528
    bn = 16 if N < 40 else 32                 # :529
    bk = 16                                   # :530
    wm = wn = 2                               # :531
    _tm = -(-M // bm)
    _tn = -(-N // bn)
    _tk = -(-K // bk)
    parts = min(max(2, next_pow2(_tk // (_tm * _tn))), 32)      # :534
    gemm_k_iterations = (K // bk) // parts                       # :536
    psize = gemm_k_iterations * bk                               # :537
    mn_aligned = (M % bm == 0) and (N % bn == 0)
    k_aligned = K % bk == 0
    kernel = (f"steel_gemm_splitk_{ta}{tb}_{a_dtype}_float32"
              f"_bm{bm}_bn{bn}_bk{bk}_wm{wm}_wn{wn}"
              f"_MN_{'t' if mn_aligned else 'n'}aligned"
              f"_K_{'t' if k_aligned else 'n'}aligned")
    tn = -(-N // bn)
    tm = -(-M // bm)
    return Route("splitk", False, kernel, bm, bn, bk, wm, wn, parts, psize,
                 0, (tn, tm, parts), (32, wn, wm),
                 "matmul.cpp:898 (non-NAX split-K)")


def _splitk_nax(M, N, K, ta, tb, a_dtype, out_dtype, devc,
                prefill_tile) -> Route:
    """steel_gemm_splitk_axpby_nax, matmul.cpp:664-766."""
    bm = bn = 128
    bk = 512
    wm = wn = 4
    psize = 4096
    if (M + N) // 2 < 512 or K <= 4096:       # :670
        bm = bn = 64
        bk = 256
        wm = wn = 2
    if prefill_tile and (M + N) // 2 >= 512 and K > 4096:   # :676
        bm = bn = 64
        wm = wn = 2
    if K <= 1024:
        psize = K // 2
    elif K <= 2048:
        psize = 1024
    elif K <= 4096:
        psize = 2048
    parts = -(-K // psize)
    tm = -(-M // bm)
    tn = -(-N // bn)
    swizzle_log = 0 if tm <= 3 else 1          # :744
    tile = 1 << swizzle_log
    tm_s = -(-tm // tile)
    tn_s = tn * tile
    kernel = (f"steel_gemm_splitk_nax_{ta}{tb}_{a_dtype}_float32"
              f"_bm{bm}_bn{bn}_bk{bk}_wm{wm}_wn{wn}")
    return Route("splitk", True, kernel, bm, bn, bk, wm, wn, parts, psize,
                 swizzle_log, (tn_s * tm_s * parts, 1, 1), (32, wn, wm),
                 "matmul.cpp:922 (NAX split-K)")


def _regular_nax(M, N, K, ta, tb, a_dtype, out_dtype, devc) -> Route:
    """steel_matmul_regular_axpby_nax, matmul.cpp:210-308."""
    bm, bn, bk, wm, wn = 128, 128, 512, 4, 4          # :210
    if devc in ("s", "c", "d"):                        # :214
        bk = 64 if (K >= 8192 and K > (M + N)) else 256
        bm = 64
        wm = 2
    tm = -(-M // bm)
    tn = -(-N // bn)
    swizzle_log = 0 if tm <= 3 else 1                  # :280
    if devc in ("s", "c", "d"):                        # :283
        swizzle_log = 2
    tile = 1 << swizzle_log
    tm_s = -(-tm // tile)
    tn_s = tn * tile
    kernel = (f"steel_gemm_fused_nax_{ta}{tb}_{a_dtype}_{out_dtype}"
              f"_bm{bm}_bn{bn}_bk{bk}_wm{wm}_wn{wn}")
    return Route("regular", True, kernel, bm, bn, bk, wm, wn, None, None,
                 swizzle_log, (tn_s, tm_s, 1), (32, wn, wm),
                 "matmul.cpp:957 (NAX regular)")


def _regular_nonnax(M, N, K, ta, tb, a_dtype, out_dtype, devc) -> Route:
    """steel_matmul_regular_axpby, matmul.cpp:376-462.

    GEMM_TPARAM_MACRO: M4 Pro (devc='s') takes the "Medium device" branch.
    """
    bm, bn, bk, wm, wn = 64, 64, 16, 2, 2
    tm = -(-M // bm)
    tn = -(-N // bn)
    kernel = (f"steel_gemm_fused_{ta}{tb}_{a_dtype}_{out_dtype}"
              f"_bm{bm}_bn{bn}_bk{bk}_wm{wm}_wn{wn}")
    return Route("regular", False, kernel, bm, bn, bk, wm, wn, None, None,
                 0, (tn, tm, 1), (32, wn, wm),
                 "matmul.cpp:957 fallthrough (non-NAX regular)")


def accum_dispatch(M: int, N: int):
    """steel_gemm_splitk_accum, matmul.cpp:652-654 (dispatch_threads)."""
    return (N, M, 1), get_block_dims(N, M, 1)


# --------------------------------------------------------------------------
# observed trace
# --------------------------------------------------------------------------

REG_RE = re.compile(
    r"\[steel-reg\] (\S+) M=(\d+) N=(\d+) K=(\d+) "
    r"grid=\((\d+),(\d+),(\d+)\) group=\((\d+),(\d+),(\d+)\)")
SPK_RE = re.compile(
    r"\[steel-splitk\] (\S+) M=(\d+) N=(\d+) K=(\d+) parts=(\d+) psize=(\d+) "
    r"grid=\((\d+),(\d+),(\d+)\) group=\((\d+),(\d+),(\d+)\)")


def load_observed(path: str):
    rows = []
    with open(path) as fh:
        for idx, line in enumerate(fh):
            m = SPK_RE.search(line)
            if m:
                g = m.groups()
                rows.append(dict(
                    seq=idx, path="splitk", kernel=g[0],
                    M=int(g[1]), N=int(g[2]), K=int(g[3]),
                    parts=int(g[4]), psize=int(g[5]),
                    grid=(int(g[6]), int(g[7]), int(g[8])),
                    group=(int(g[9]), int(g[10]), int(g[11]))))
                continue
            m = REG_RE.search(line)
            if m:
                g = m.groups()
                rows.append(dict(
                    seq=idx, path="regular", kernel=g[0],
                    M=int(g[1]), N=int(g[2]), K=int(g[3]),
                    parts=None, psize=None,
                    grid=(int(g[4]), int(g[5]), int(g[6])),
                    group=(int(g[7]), int(g[8]), int(g[9]))))
    return rows


# --------------------------------------------------------------------------
# site attribution (Laguna XS 2.1 text tower, 40 layers)
# --------------------------------------------------------------------------

SITES = {
    (512, 1024, 2048): "attn wk / wv  (K and V projections, all 40 layers)",
    (512, 256, 2048): "MoE router logits GEMM (38 MoE layers)",
    (512, 64, 2048): "attn g_proj (per-head gate), sliding-window layers",
    (512, 48, 2048): "attn g_proj (per-head gate), full-attention layers",
    (512, 8192, 2048): "attn wq, sliding-window layers + layer-0 dense gate/up",
    (512, 2048, 8192): "attn wo, sliding-window layers + layer-0 dense down",
    (512, 6144, 2048): "attn wq, full-attention layers",
    (512, 2048, 6144): "attn wo, full-attention layers",
    (512, 2048, 2048): "layer-39 [K;V] bank projection",
}


def main() -> int:
    observed = load_observed(OBSERVED)
    if len(observed) != 237:
        print(f"FATAL: expected 237 observed rows, got {len(observed)}")
        return 2

    # ---- Tier 2 validation ------------------------------------------------
    mismatches = []
    for r in observed:
        pred = route(r["M"], r["N"], r["K"], use_nax=False, devc="s")
        bad = []
        if pred.kernel != r["kernel"]:
            bad.append(f"kernel {pred.kernel} != {r['kernel']}")
        if tuple(pred.grid) != tuple(r["grid"]):
            bad.append(f"grid {pred.grid} != {r['grid']}")
        if tuple(pred.group) != tuple(r["group"]):
            bad.append(f"group {pred.group} != {r['group']}")
        if pred.parts != r["parts"]:
            bad.append(f"parts {pred.parts} != {r['parts']}")
        if pred.psize != r["psize"]:
            bad.append(f"psize {pred.psize} != {r['psize']}")
        if pred.path != r["path"]:
            bad.append(f"path {pred.path} != {r['path']}")
        if bad:
            mismatches.append((r["seq"], r["M"], r["N"], r["K"], bad))

    print(f"Tier-2 validation: {len(observed) - len(mismatches)}/"
          f"{len(observed)} rows reproduced exactly")
    for mm in mismatches[:20]:
        print("  MISMATCH", mm)
    if mismatches:
        return 3

    # ---- emit both tiers --------------------------------------------------
    out_rows = []
    for r in observed:
        M, N, K = r["M"], r["N"], r["K"]
        flops = 2 * M * N * K
        site = SITES.get((M, N, K), "unattributed")

        # Tier 2: observed M4 Pro
        tg = r["grid"][0] * r["grid"][1] * r["grid"][2]
        thr = r["group"][0] * r["group"][1] * r["group"][2]
        out_rows.append(dict(
            tier=2, tier_label="observed-M4Pro", seq=r["seq"],
            M=M, N=N, K=K, a_dtype="bfloat16",
            out_dtype="float32" if r["path"] == "splitk" else "bfloat16",
            path=r["path"], nax=False, kernel=r["kernel"],
            bm=_kv(r["kernel"], "bm"), bn=_kv(r["kernel"], "bn"),
            bk=_kv(r["kernel"], "bk"), wm=_kv(r["kernel"], "wm"),
            wn=_kv(r["kernel"], "wn"),
            parts=r["parts"], psize=r["psize"], swizzle_log=0,
            grid_x=r["grid"][0], grid_y=r["grid"][1], grid_z=r["grid"][2],
            group_x=r["group"][0], group_y=r["group"][1],
            group_z=r["group"][2],
            threadgroups=tg, threads_per_tg=thr,
            tg_per_core=round(tg / M4_CORES, 4),
            gflop=round(flops / 1e9, 4),
            predicate="matmul.cpp:898 (non-NAX split-K)"
            if r["path"] == "splitk"
            else "matmul.cpp:957 fallthrough (non-NAX regular)",
            site=site))

        # Tier 1: derived M5 Max
        p = route(M, N, K, use_nax=True, devc="s")
        tg1 = p.grid[0] * p.grid[1] * p.grid[2]
        thr1 = p.group[0] * p.group[1] * p.group[2]
        out_rows.append(dict(
            tier=1, tier_label="derived-M5Max", seq=r["seq"],
            M=M, N=N, K=K, a_dtype="bfloat16",
            out_dtype="float32" if p.path == "splitk" else "bfloat16",
            path=p.path, nax=True, kernel=p.kernel,
            bm=p.bm, bn=p.bn, bk=p.bk, wm=p.wm, wn=p.wn,
            parts=p.parts, psize=p.psize, swizzle_log=p.swizzle_log,
            grid_x=p.grid[0], grid_y=p.grid[1], grid_z=p.grid[2],
            group_x=p.group[0], group_y=p.group[1], group_z=p.group[2],
            threadgroups=tg1, threads_per_tg=thr1,
            tg_per_core=round(tg1 / M5_CORES, 4),
            gflop=round(flops / 1e9, 4),
            predicate=p.predicate_line, site=site))

    cols = list(out_rows[0].keys())
    with open(os.path.join(HERE, "steel_census_237.csv"), "w",
              newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)
    with open(os.path.join(HERE, "steel_census_237.json"), "w") as fh:
        json.dump({
            "base_sha": "9527bb727caad1c495e6b62ecbf2445a25e937dd",
            "source": "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/"
                      "metal/matmul.cpp",
            "observed_host": "Apple M4 Pro, 20 GPU cores, macOS 26.5.2",
            "derived_host": "Apple M5 Max, 40 GPU cores (is_nax_available()"
                            " true)",
            "dispatches_per_prefill": 237,
            "rows": out_rows,
        }, fh, indent=1)

    _summary(out_rows)
    return 0


def _kv(kernel: str, key: str) -> int:
    m = re.search(rf"_{key}(\d+)", kernel)
    return int(m.group(1)) if m else -1


def _summary(rows):
    for tier, cores, label in ((2, M4_CORES, "observed M4 Pro"),
                               (1, M5_CORES, "derived M5 Max")):
        sub = [r for r in rows if r["tier"] == tier]
        classes = {}
        for r in sub:
            k = (r["kernel"], r["M"], r["N"], r["K"], r["parts"])
            c = classes.setdefault(k, dict(n=0, r=r))
            c["n"] += 1
        print(f"\n=== Tier {tier} ({label}) — {len(sub)} dispatches, "
              f"{len(classes)} classes ===")
        print(f"{'n':>4} {'M':>5} {'N':>6} {'K':>6} {'prts':>4} "
              f"{'grid':>16} {'grp':>10} {'TG':>7} {'TG/core':>8} "
              f"{'GFLOP':>8}  kernel")
        tot_tg = tot_fl = 0
        for k, c in sorted(classes.items(), key=lambda x: -x[1]["n"]):
            r = c["r"]
            g = f"({r['grid_x']},{r['grid_y']},{r['grid_z']})"
            gp = f"({r['group_x']},{r['group_y']},{r['group_z']})"
            print(f"{c['n']:>4} {r['M']:>5} {r['N']:>6} {r['K']:>6} "
                  f"{str(r['parts']):>4} {g:>16} {gp:>10} "
                  f"{r['threadgroups']:>7} {r['tg_per_core']:>8.2f} "
                  f"{r['gflop']:>8.2f}  {r['kernel']}")
            tot_tg += c["n"] * r["threadgroups"]
            tot_fl += c["n"] * r["gflop"]
        print(f"{'':>4} total threadgroups={tot_tg}  "
              f"total GFLOP={tot_fl:.1f}  "
              f"mean TG/core={tot_tg / len(sub) / cores:.2f}")


if __name__ == "__main__":
    sys.exit(main())
