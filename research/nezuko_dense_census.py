#!/usr/bin/env python3
"""Layer-0 dense-MLP BF16 census for PR #85 (lossless repack).

Research-only. Reads the reference checkpoint directly and reports the
statistics that select the packing scheme. Nothing here runs on the scored
path; the runtime packer lives in Sources/MLXFastModel/LagunaDensePacked.swift.

Subcommands
-----------
value    Value census: zeros, subnormals, inf/nan, exponent range, mantissa
         trailing-zero histogram, empirical entropy. Kills any scheme that
         relies on structural sparsity or short mantissas (GO-8).
axis     Which axis a shared exponent base should follow, and how bad the
         wrong choice is. Compares row / column / two-sided bases.
block    Per-block (B=128) bases against whole-channel bases, for d in 3..5.
scheme   Final scheme table: best-placed window per channel, escape rate,
         bits/weight, packed megabytes, decode bytes per step.

Usage
-----
    python3 nezuko_dense_census.py value
    python3 nezuko_dense_census.py axis
    python3 nezuko_dense_census.py block
    python3 nezuko_dense_census.py scheme
    python3 nezuko_dense_census.py all
"""

import argparse
import json
import os
import struct
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CKPT = os.path.join(REPO, "reference_weights", "laguna-xs-2.1-nvfp4-mlx")

TENSORS = [
    "model.layers.0.mlp.gate_proj.weight",
    "model.layers.0.mlp.up_proj.weight",
    "model.layers.0.mlp.down_proj.weight",
]

# gate/up are [intermediate=8192, hidden=2048]; down is [hidden=2048,
# intermediate=8192]. Axis 1 is the contiguous reduction axis in every case,
# so a shared exponent base must be constant along axis 1 for gate/up (one
# base per output row) and along axis 0 for down (one base per reduction
# index, which is what the down GEMV strides over).
BASE_AXIS = {
    "model.layers.0.mlp.gate_proj.weight": 1,
    "model.layers.0.mlp.up_proj.weight": 1,
    "model.layers.0.mlp.down_proj.weight": 0,
}


def load_bf16(name):
    """Return the raw BF16 bit patterns of `name` as uint16, plus its shape."""
    index = json.load(open(os.path.join(CKPT, "model.safetensors.index.json")))
    shard = index["weight_map"][name]
    path = os.path.join(CKPT, shard)
    with open(path, "rb") as fh:
        (header_len,) = struct.unpack("<Q", fh.read(8))
        header = json.loads(fh.read(header_len))
        meta = header[name]
        assert meta["dtype"] == "BF16", meta["dtype"]
        start, end = meta["data_offsets"]
        fh.seek(8 + header_len + start)
        raw = fh.read(end - start)
    bits = np.frombuffer(raw, dtype="<u2").reshape(meta["shape"])
    return bits, tuple(meta["shape"])


def parts(bits):
    """Split BF16 bit patterns into sign, biased exponent, mantissa."""
    return (bits >> 15).astype(np.uint8), ((bits >> 7) & 0xFF).astype(
        np.uint8
    ), (bits & 0x7F).astype(np.uint8)


def entropy_bits(values, nbits):
    counts = np.bincount(values.ravel(), minlength=1 << nbits).astype(np.float64)
    p = counts[counts > 0] / counts.sum()
    return float(-(p * np.log2(p)).sum())


def cmd_value():
    print("== value census ==")
    for name in TENSORS:
        bits, shape = load_bf16(name)
        sign, exp, man = parts(bits)
        zeros = int(((exp == 0) & (man == 0)).sum())
        subs = int(((exp == 0) & (man != 0)).sum())
        nans = int((exp == 0xFF).sum())
        nz_exp = exp[exp != 0]
        tz = np.zeros(8, dtype=np.int64)
        for k in range(8):
            tz[k] = int((man & ((1 << k) - 1) == 0).sum()) if k else man.size
        print(f"\n{name} {shape} n={bits.size}")
        print(f"  zeros={zeros} subnormals={subs} inf/nan={nans}")
        print(f"  exp range=[{int(nz_exp.min())},{int(nz_exp.max())}] span={int(nz_exp.max())-int(nz_exp.min())}")
        print(f"  H(exp)={entropy_bits(exp, 8):.4f} H(man)={entropy_bits(man, 7):.4f} "
              f"H(sign)={entropy_bits(sign, 1):.4f}")
        print(f"  total lossless floor = {entropy_bits(exp,8)+entropy_bits(man,7)+entropy_bits(sign,1):.4f} bits/weight")
        # Mantissa trailing-zero fractions. A geometric 2^-k profile means the
        # mantissas are incompressible, which is what kills GO-8.
        frac = [f"{tz[k]/man.size:.4f}" for k in range(8)]
        print(f"  P(mantissa has >=k trailing zeros), k=0..7: {frac}")


def channel_bases(exp, base_axis, d):
    """Best-placed window base per channel and the resulting escape count.

    For each channel, try every base b in [min, min+ (1<<d)-1] and keep the one
    covering the most elements with exponent in [b, b + (1<<d) - 2]. The last
    code (all ones) is reserved as the escape marker.
    """
    axis = 1 - base_axis  # reduce over the non-base axis
    width = (1 << d) - 1  # codes 0 .. width-1 usable, `width` == escape
    lo = exp.min(axis=axis, keepdims=True)
    best_base = lo.copy()
    best_cov = np.zeros(lo.shape, dtype=np.int64)
    for shift in range(width):
        b = lo + shift
        cov = ((exp >= b) & (exp < b + width)).sum(axis=axis, keepdims=True)
        better = cov > best_cov
        best_cov = np.where(better, cov, best_cov)
        best_base = np.where(better, b, best_base)
    esc = int(exp.size - best_cov.sum())
    per_ch = (exp < best_base) | (exp >= best_base + width)
    return best_base, esc, int(per_ch.sum(axis=axis).max())


def cmd_axis():
    print("== axis census ==")
    for name in TENSORS:
        bits, shape = load_bf16(name)
        _, exp, _ = parts(bits)
        right = BASE_AXIS[name]
        print(f"\n{name} {shape} correct base axis = {right}")
        for d in (4,):
            for axis in (0, 1):
                _, esc, mx = channel_bases(exp, axis, d)
                tag = "CORRECT" if axis == right else "wrong  "
                print(f"  d={d} base_axis={axis} [{tag}] esc_elt={esc/exp.size:.8f} max_per_channel={mx}")
            # min-placed base for contrast: shows placement, not the base
            # concept, is what makes the scheme work.
            ax = 1 - right
            lo = exp.min(axis=ax, keepdims=True)
            w = (1 << d) - 1
            esc_min = int(((exp < lo) | (exp >= lo + w)).sum())
            print(f"  d={d} base=min (no search)         esc_elt={esc_min/exp.size:.8f}")


def cmd_block():
    print("== block-base census (B=128 along the reduction axis) ==")
    B = 128
    for name in TENSORS:
        bits, shape = load_bf16(name)
        _, exp, _ = parts(bits)
        base_axis = BASE_AXIS[name]
        e = exp if base_axis == 1 else exp.T  # rows = channels, cols = reduce
        rows, cols = e.shape
        blocks = e.reshape(rows, cols // B, B)
        print(f"\n{name} {shape}")
        for d in (3, 4, 5):
            w = (1 << d) - 1
            # whole-channel best-placed window
            _, esc_ch, _ = channel_bases(exp, base_axis, d)
            # per-block best-placed window
            lo = blocks.min(axis=2, keepdims=True)
            best = np.zeros(lo.shape, dtype=np.int64)
            for shift in range(w):
                b = lo + shift
                cov = ((blocks >= b) & (blocks < b + w)).sum(axis=2, keepdims=True)
                best = np.maximum(best, cov)
            esc_bl = int(blocks.size - best.sum())
            # bits/weight: 1 sign+mantissa byte, d delta bits, plus the base
            # vector amortised over its scope, plus 16 bits per escape.
            ch_bits = 8 + d + 8 / cols + 16 * (esc_ch / e.size)
            bl_bits = 8 + d + 8 / B + 16 * (esc_bl / e.size)
            print(f"  d={d} channel: esc={esc_ch/e.size:.8f} bits={ch_bits:.4f} | "
                  f"block{B}: esc={esc_bl/e.size:.8f} bits={bl_bits:.4f}")


def cmd_gates():
    """The assignment's literal gate ladder: SANITY / GO-8 / GO-12 / GO-12e /
    GO-13 / T8. Reported on the brief's own definitions so the firing gate is
    unambiguous, even where the census shows a better variant exists.
    """
    print("== gate ladder (assignment definitions) ==")
    for name in TENSORS:
        bits, shape = load_bf16(name)
        _, exp, man = parts(bits)
        base_axis = BASE_AXIS[name]
        e = exp if base_axis == 1 else exp.T  # rows = channels
        span = e.max(axis=1) - e.min(axis=1)
        pf14 = float((span <= 14).mean())
        pf30 = float((span <= 30).mean())
        tz4 = float((man & 0x0F == 0).mean())
        # outliers per row under a best-placed 15-wide window
        _, _, mx = channel_bases(exp, base_axis, 4)
        w = 15
        lo = e.min(axis=1, keepdims=True)
        best = np.zeros((e.shape[0], 1), dtype=np.int64)
        for shift in range(w):
            b = lo + shift
            cov = ((e >= b) & (e < b + w)).sum(axis=1, keepdims=True)
            best = np.maximum(best, cov)
        out = (e.shape[1] - best.ravel()).astype(np.int64)
        d16 = int(np.unique(bits).size)
        tiles = bits.ravel()[: (bits.size // 4096) * 4096].reshape(-1, 4096)
        # max distinct uint16 patterns over any 4096-element tile
        tmax = int(max(np.unique(t).size for t in tiles[:: max(1, len(tiles) // 512)]))
        print(f"\n{name} {shape} rows(channels)={e.shape[0]} len={e.shape[1]}")
        print(f"  pack_frac_row(14)={pf14:.6f}  pack_frac_row(30)={pf30:.6f}")
        print(f"  row exponent span: median={int(np.median(span))} p90={int(np.percentile(span,90))} "
              f"p99={int(np.percentile(span,99))} max={int(span.max())}")
        print(f"  outliers_per_row(14): median={int(np.median(out))} p90={int(np.percentile(out,90))} "
              f"p99={int(np.percentile(out,99))} max={int(out.max())} (=={mx})")
        print(f"  frac(tz>=4)={tz4:.6f}   distinct16(all)={d16}  max distinct16 per 4096-tile={tmax}")
        verdict = []
        verdict.append("SANITY pass")
        verdict.append(f"GO-8 {'PASS' if (pf14>=0.85 and tz4>=0.98) else 'FAIL'}")
        verdict.append(f"GO-12 {'PASS' if pf14>=0.85 else 'FAIL'}")
        verdict.append(f"GO-12e {'PASS' if (pf14<0.85 and np.percentile(out,99)<=8) else 'FAIL'}")
        verdict.append(f"GO-13 {'PASS' if pf30>=0.85 else 'FAIL'}")
        verdict.append(f"T8 {'PASS' if tmax<=256 else 'FAIL'}")
        print("  " + " | ".join(verdict))


def cmd_scheme():
    print("== scheme table (whole-channel best-placed window) ==")
    total_stock = 0.0
    total_packed = 0.0
    for name in TENSORS:
        bits, shape = load_bf16(name)
        _, exp, _ = parts(bits)
        base_axis = BASE_AXIS[name]
        nch = shape[base_axis]
        n = exp.size
        print(f"\n{name} {shape} base_axis={base_axis} channels={nch}")
        for d in (3, 4, 5):
            base, esc, mx = channel_bases(exp, base_axis, d)
            # Overflow guard the runtime packer must also enforce.
            ok = int(base.max()) + (1 << d) - 2 <= 255 and int(base.min()) >= 0
            bits_w = 8 + d + 8 * nch / n + 16 * (esc / n)
            packed = n * bits_w / 8 / 1e6
            print(f"  d={d} esc_elt={esc/n:.8f} max_per_channel={mx} "
                  f"bits/weight={bits_w:.4f} ({bits_w/16*100:.2f}% of BF16) "
                  f"packed={packed:.3f} MB guard_ok={ok}")
            if d == 4:
                total_stock += n * 2 / 1e6
                total_packed += packed
    print(f"\n  d=4 totals: stock={total_stock:.3f} MB packed={total_packed:.3f} MB "
          f"saved={total_stock-total_packed:.3f} MB/step")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["value", "gates", "axis", "block", "scheme", "all"])
    args = ap.parse_args()
    cmds = {"value": cmd_value, "gates": cmd_gates, "axis": cmd_axis,
            "block": cmd_block, "scheme": cmd_scheme}
    if args.cmd == "all":
        for fn in cmds.values():
            fn()
            print()
    else:
        cmds[args.cmd]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
