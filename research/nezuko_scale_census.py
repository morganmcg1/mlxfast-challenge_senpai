#!/usr/bin/env python3
"""Census of pairwise redundancy in NVFP4 scale planes (raw uint8 E4M3 codes).

Question: does scale[2k] == scale[2k+1] hold, bitwise, on the SHIPPED routed
expert scale plane the way it provably does on the runtime-quantized attention
plane (MLX fp_quantize group_size==16 branch)?

Usage:
  python3 research/nezuko_scale_census.py --layers 1,2,3
  python3 research/nezuko_scale_census.py --all
"""

import argparse
import json
import re
import struct
import sys
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
WEIGHTS = REPO / "weights"


def load_headers():
    hdrs = {}
    for shard in sorted(WEIGHTS.glob("model-*-of-*.safetensors")):
        with open(shard, "rb") as f:
            n = struct.unpack("<Q", f.read(8))[0]
            hdr = json.loads(f.read(n))
        hdrs[shard] = (8 + n, hdr)
    return hdrs


def tensor_index(hdrs):
    idx = {}
    for shard, (base, hdr) in hdrs.items():
        for k, v in hdr.items():
            if k == "__metadata__":
                continue
            idx[k] = (shard, base + v["data_offsets"][0], base + v["data_offsets"][1],
                      v["dtype"], tuple(v["shape"]))
    return idx


def read_u8(idx, name):
    shard, a, b, dtype, shape = idx[name]
    assert dtype == "U8", (name, dtype)
    with open(shard, "rb") as f:
        f.seek(a)
        buf = f.read(b - a)
    arr = np.frombuffer(buf, dtype=np.uint8)
    assert arr.size == int(np.prod(shape)), (name, arr.size, shape)
    return arr.reshape(shape)


def census(arr):
    """arr: (..., G) uint8. Pair along the last (contiguous, input-feature) axis.

    NOTE the pairing is taken over the FLAT tensor, not per row: the MLX
    fp_quantize dispatch is 1-D over w.size(), so pair k spans flat scale
    indices (2k, 2k+1) regardless of row boundaries. Row width is a multiple
    of 2 for every tensor here, so the two views coincide.
    """
    flat = arr.reshape(-1)
    rows = arr.reshape(-1, arr.shape[-1])
    g = rows.shape[-1]
    assert g % 2 == 0
    even_eq = (flat[0::2] == flat[1::2]).reshape(rows.shape[0], g // 2)
    odd_eq = flat[1:-1:2] == flat[2::2]                   # pairs (2k+1, 2k+2)
    codes = np.bincount(rows.reshape(-1), minlength=256)
    # column profile of exceptions for the even pairing
    col_bad = (~even_eq).sum(axis=0)
    bad_flat = (np.nonzero(~even_eq.reshape(-1))[0] * 2).tolist()
    return {
        "bad_flat": bad_flat,
        "rows": rows.shape[0],
        "g": g,
        "entries": rows.size,
        "even_pairs": even_eq.size,
        "even_eq": int(even_eq.sum()),
        "odd_pairs": odd_eq.size,
        "odd_eq": int(odd_eq.sum()),
        "distinct_codes": int((codes > 0).sum()),
        "codes": codes,
        "col_bad": col_bad,
        "row_all_eq": int(even_eq.all(axis=1).sum()),
    }


def merge(a, b):
    if a is None:
        return b
    out = {}
    for k in ("rows", "entries", "even_pairs", "even_eq", "odd_pairs", "odd_eq", "row_all_eq"):
        out[k] = a[k] + b[k]
    out["bad_flat"] = a["bad_flat"] + b["bad_flat"]
    out["g"] = a["g"] if a["g"] == b["g"] else -1
    out["codes"] = a["codes"] + b["codes"]
    out["col_bad"] = a["col_bad"] + b["col_bad"] if a["g"] == b["g"] else None
    out["distinct_codes"] = int((out["codes"] > 0).sum())
    return out


def report(label, s):
    ef = 100.0 * s["even_eq"] / s["even_pairs"]
    of = 100.0 * s["odd_eq"] / s["odd_pairs"] if s["odd_pairs"] else float("nan")
    print(f"{label:52s} entries={s['entries']:>12,d} "
          f"even(2k,2k+1)={ef:8.4f}%  odd(2k+1,2k+2)={of:8.4f}%  "
          f"distinct_codes={s['distinct_codes']:3d}  rows_all_eq={s['row_all_eq']:,d}/{s['rows']:,d}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layers", default="1,2,3")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--experts", type=int, default=0, help="0 = all experts")
    args = ap.parse_args()

    hdrs = load_headers()
    idx = tensor_index(hdrs)

    all_layers = sorted({int(m.group(1)) for k in idx
                         for m in [re.match(r"model\.layers\.(\d+)\.mlp\.switch_mlp\.", k)] if m})
    layers = all_layers if args.all else [int(x) for x in args.layers.split(",")]
    print(f"# switch_mlp layers present: {all_layers[0]}..{all_layers[-1]} (n={len(all_layers)})")
    print(f"# censusing layers: {layers}")
    print(f"# expert subsample: {'all 256' if args.experts == 0 else args.experts}")
    print()

    fams = {}
    exc_all = []
    for L in layers:
        for kind in ("switch_mlp", "shared_expert"):
            for proj in ("gate_proj", "up_proj", "down_proj"):
                name = f"model.layers.{L}.mlp.{kind}.{proj}.scales"
                if name not in idx:
                    continue
                arr = read_u8(idx, name)
                if kind == "switch_mlp" and args.experts:
                    arr = arr[: args.experts]
                s = census(arr)
                if s["bad_flat"]:
                    exc_all.append((name, tuple(idx[name][4]), s["bad_flat"]))
                if len(layers) <= 4:
                    report(f"L{L:02d} {kind}.{proj} {idx[name][4]}", s)
                fams[(kind, proj)] = merge(fams.get((kind, proj)), s)

    print()
    print("=== aggregate by family ===")
    total = None
    for k in sorted(fams):
        report(f"{k[0]}.{k[1]}", fams[k])
        total = merge(total, fams[k]) if fams[k]["g"] == (total or fams[k])["g"] else total
    print()

    # Global aggregate (ignore col_bad mismatch across widths)
    ep = sum(f["even_pairs"] for f in fams.values())
    ee = sum(f["even_eq"] for f in fams.values())
    op = sum(f["odd_pairs"] for f in fams.values())
    oe = sum(f["odd_eq"] for f in fams.values())
    codes = sum(f["codes"] for f in fams.values())
    print(f"GLOBAL even(2k,2k+1) = {100.0*ee/ep:.6f}%   ({ee:,d}/{ep:,d})")
    print(f"GLOBAL odd (2k+1,2k+2) = {100.0*oe/op:.6f}%   ({oe:,d}/{op:,d})")
    print(f"GLOBAL distinct codes = {int((codes>0).sum())}")
    nz = np.nonzero(codes)[0]
    frac = codes[nz] / codes.sum()
    order = np.argsort(-frac)[:12]
    print("top codes (u8, share):", ", ".join(f"0x{nz[i]:02x}:{100*frac[i]:.2f}%" for i in order))
    sub = codes[:8].sum() + codes[128:136].sum()  # E4M3 exp==0 -> subnormal
    print(f"subnormal-code share (exp field == 0): {100.0*sub/codes.sum():.2f}%")

    print()
    print("=== every exception, exact flat scale index ===")
    ntensor = sum(1 for L in layers for kind in ("switch_mlp", "shared_expert")
                  for proj in ("gate_proj", "up_proj", "down_proj")
                  if f"model.layers.{L}.mlp.{kind}.{proj}.scales" in idx)
    print(f"tensors examined: {ntensor}; tensors with >=1 exception: {len(exc_all)}")
    nonzero_pos = [b for _, _, bl in exc_all for b in bl if b != 0]
    print(f"exceptions at flat index 0: {sum(1 for _,_,bl in exc_all for b in bl if b==0)}")
    print(f"exceptions elsewhere: {len(nonzero_pos)}  -> {nonzero_pos[:20]}")
    for name, shp, bl in exc_all[:6]:
        print("   ", name, shp, "bad flat idx", bl)

    print()
    print("=== exception column profile (even pairing), per family ===")
    for k in sorted(fams):
        cb = fams[k]["col_bad"]
        if cb is None:
            continue
        nzc = np.nonzero(cb)[0]
        print(f"{k[0]}.{k[1]}: g={fams[k]['g']} bad_pair_columns={len(nzc)}/{len(cb)} "
              f"first10={list(nzc[:10])} counts_first10={[int(cb[i]) for i in nzc[:10]]}")


if __name__ == "__main__":
    main()
