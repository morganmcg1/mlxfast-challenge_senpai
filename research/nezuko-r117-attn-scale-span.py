#!/usr/bin/env python3
"""R117-C: per-row E4M3 scale-code span histogram for the decode attention
projections, computed from the shipped checkpoint.

Why this is computed and not read: despite the repository name
(`Laguna-XS-2.1-NVFP4-mlx`), the attention tensors q/k/v/o/g_proj ship as plain
BF16 with **no `.scales` companion** -- only the MLP tensors
(`shared_expert.*`, `switch_mlp.*`) are pre-quantized.  The attention scale
plane is therefore derived at load time by MLX's `fp_quantize`, whose rule is
(Vendor/mlx-swift/.../kernels/fp_quantized.h, `fp_quantize`):

    scale = simd_max(|w|) over the group of `group_size` values
    scale /= (bits == 4 ? 6.0 : 448.0)
    q_scale = fp8_e4m3(scale).bits

with `group_size = 16`, `bits = 4` for this model, and no per-tensor second
level scale.  E4M3 is monotone in magnitude for non-negative values, so the
span of codes within a row is exactly

    code(max_g maxabs_g / 6) - code(min_g maxabs_g / 6)

i.e. it is fixed by the row's largest and smallest group maxima.  That lets the
whole histogram be built from two reductions per row instead of an E4M3
encode of every group.

Span matters because it prices the only surviving scale-plane arm: a row whose
codes all sit within a `2^b`-wide window can be stored as one base byte plus
b-bit deltas.  The shipped `lagunaLaneMajorNVFP4ScaleBank` already does this at
b = 4 (span <= 15); rows that do not fit escape to the full stock plane.

Usage:  nezuko-r117-attn-scale-span.py [--layers N] [--json OUT]
"""
import argparse
import json
import os
import struct
import sys

import numpy as np

SNAP = os.path.expanduser(
    "~/.cache/huggingface/hub/models--poolside--Laguna-XS-2.1-NVFP4-mlx/"
    "snapshots/841778bda563a36104dd521e37d99218e46f4f25")
GROUP = 16


def e4m3_code(x):
    """OCP fp8 E4M3 bit pattern for a non-negative float array (round-nearest-even).

    Layout s eeee mmm, exponent bias 7, no infinities, 0x7F = NaN,
    max finite 0x7E = 448, subnormal step 2^-9.
    """
    x = np.asarray(x, dtype=np.float64)
    out = np.zeros(x.shape, dtype=np.int32)
    pos = x > 0
    if not np.any(pos):
        return out
    xv = x[pos]
    e = np.floor(np.log2(xv)).astype(np.int64)
    e = np.maximum(e, -6)                       # clamp into the normal range
    man = np.round(xv / np.power(2.0, e.astype(np.float64)) * 8.0)
    # round-half-even is numpy's default for .round on .5 ties
    carry = man >= 16
    e = np.where(carry, e + 1, e)
    man = np.where(carry, man / 2, man)
    sub = xv < 2.0 ** -6                        # subnormal: 0 exponent field
    code = np.where(sub,
                    np.round(xv / 2.0 ** -9),
                    ((e + 7) * 8) + (man - 8))
    code = np.clip(code, 0, 0x7E)
    out[pos] = code.astype(np.int32)
    return out


def read_header(path):
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        return json.loads(f.read(n)), 8 + n


def load_bf16(path, meta, base, name):
    info = meta[name]
    assert info["dtype"] == "BF16", (name, info["dtype"])
    lo, hi = info["data_offsets"]
    with open(path, "rb") as f:
        f.seek(base + lo)
        raw = np.frombuffer(f.read(hi - lo), dtype=np.uint16)
    wide = np.zeros(raw.size, dtype=np.uint32)
    wide |= raw.astype(np.uint32) << 16          # bf16 -> f32 is a shift
    return wide.view(np.float32).reshape(info["shape"])


def row_spans(w):
    """(span, n_groups) for every row of a [rows, in] BF16-derived matrix."""
    rows, inn = w.shape
    g = np.abs(w.astype(np.float32)).reshape(rows, inn // GROUP, GROUP).max(axis=2)
    gmax = g.max(axis=1) / 6.0
    gmin = g.min(axis=1) / 6.0
    return e4m3_code(gmax) - e4m3_code(gmin), inn // GROUP


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layers", type=int, default=4,
                    help="how many transformer layers to sample")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    wm = json.load(open(os.path.join(SNAP, "model.safetensors.index.json")))["weight_map"]
    shards = {}
    for shard in sorted(set(wm.values())):
        p = os.path.join(SNAP, shard)
        shards[shard] = (p,) + read_header(p)

    n_layers = 1 + max(int(k.split(".")[2]) for k in wm if k.startswith("model.layers."))
    picks = sorted({int(round(i * (n_layers - 1) / max(args.layers - 1, 1)))
                    for i in range(args.layers)})
    print(f"model has {n_layers} layers; sampling {picks}")

    tally = {}
    for layer in picks:
        qname = f"model.layers.{layer}.self_attn.q_proj.weight"
        if qname not in wm:
            continue
        qrows = shards[wm[qname]][1][qname]["shape"][0]
        heads = qrows // 128          # head_dim = 128
        for proj in ("q_proj", "k_proj", "v_proj", "o_proj"):
            name = f"model.layers.{layer}.self_attn.{proj}.weight"
            if name not in wm:
                continue
            path, meta, base = shards[wm[name]]
            shape = meta[name]["shape"]
            w = load_bf16(path, meta, base, name)
            spans, groups = row_spans(w)
            del w
            key = f"{proj}_h{heads}"
            tally.setdefault(key, []).append((layer, spans, groups))
            print(f"  layer {layer:2d} h{heads} {proj:7s} shape={shape} "
                  f"groups/row={groups} rows={spans.size} "
                  f"span: med={int(np.median(spans))} p99={int(np.percentile(spans,99))} "
                  f"max={int(spans.max())}")

    print("\n=== per-row E4M3 code span, pooled over sampled layers ===")
    print(f"{'tensor':12s} {'rows':>8s} {'grp/row':>8s} "
          f"{'<=7':>8s} {'<=15':>8s} {'<=31':>8s} {'<=63':>8s} {'max':>5s}")
    summary = {}
    CAPS = (1, 3, 7, 15, 31, 63)
    for key, items in sorted(tally.items()):
        allspans = np.concatenate([s for _, s, _ in items])
        groups = items[0][2]
        f = {b: float((allspans <= b).mean()) for b in CAPS}
        summary[key] = {"rows": int(allspans.size), "groups_per_row": groups,
                        "frac": f, "max": int(allspans.max()),
                        "median": int(np.median(allspans)),
                        "layers": [l for l, _, _ in items]}
        print(f"{key:12s} {allspans.size:8d} {groups:8d} "
              + " ".join(f"{f[b]*100:7.3f}%" for b in (7, 15, 31, 63))
              + f" {allspans.max():5d}")

    print("\n=== effective scale-plane bytes per row at delta width b ===")
    print("    fit rows pay 1 base byte + b bits per group (pairwise halves the")
    print("    group count on the shipped bank); escaped rows pay the full stock")
    print("    plane of 1 byte per group.")
    print(f"{'tensor':12s} {'stock':>7s} " + " ".join(f"{'b=%d' % b:>10s}" for b in (2, 3, 4)))
    for key, s in sorted(summary.items()):
        g = s["groups_per_row"]
        row = f"{key:12s} {g:7d}"
        for b in (2, 3, 4):
            hit = s["frac"][2 ** b - 1]
            eff = hit * (1 + (g / 2) * b / 8.0) + (1 - hit) * g
            row += f" {eff:10.2f}"
        print(row + "   (pairwise: g/2 deltas)")

    if args.json:
        json.dump(summary, open(args.json, "w"), indent=1)
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    sys.exit(main())
