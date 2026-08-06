#!/usr/bin/env python3
"""Dump real Laguna layer-1 routed-expert tensors for the group-32 halving harness.

Support tool for PR #72.  Emits the exact byte images the two decode kernels bind,
for the first 8 routed experts of layer 1 (expert 0 carries the only checkpoint
scale-pair exception in this slice, so the harness exercises the patch path).

    python3 research/nezuko_g32_dump.py
Outputs land in /tmp/nezuko_g32/.
"""

import json
import os
import struct

import numpy as np

OUT_DIR = "/tmp/nezuko_g32"
WEIGHT_DIR = "weights"
LAYER = 1
EXPERTS = 8


def load_headers():
    hdrs = []
    for name in sorted(os.listdir(WEIGHT_DIR)):
        if not name.endswith(".safetensors"):
            continue
        path = os.path.join(WEIGHT_DIR, name)
        with open(path, "rb") as f:
            n = struct.unpack("<Q", f.read(8))[0]
            hdrs.append((path, 8 + n, json.loads(f.read(n))))
    return hdrs


def tensor(hdrs, name):
    for path, offset, hdr in hdrs:
        if name in hdr:
            meta = hdr[name]
            dtype = {"U8": np.uint8, "U32": np.uint32, "BF16": np.uint16}[meta["dtype"]]
            begin, end = meta["data_offsets"]
            count = (end - begin) // np.dtype(dtype).itemsize
            arr = np.fromfile(path, dtype=dtype, count=count, offset=offset + begin)
            return arr.reshape(meta["shape"])
    raise KeyError(name)


def fp32_to_bf16(x):
    u = x.astype(np.float32).view(np.uint32)
    return ((u + 0x8000 + ((u >> 16) & 1)) >> 16).astype(np.uint16)


def packed_bank_order(rows):
    order = []
    for tile in range(rows // 8):
        for kblock in range(4):
            for sub in range(8):
                logical_row = tile * 4 + sub // 2
                gate_row = (logical_row // 32) * 64 + logical_row % 32
                fused_row = gate_row if sub % 2 == 0 else gate_row + 32
                order.append(fused_row * 4 + kblock)
    return np.asarray(order, dtype=np.int64)


def write(name, arr):
    path = os.path.join(OUT_DIR, name)
    arr.tofile(path)
    print(f"  {path}: {arr.nbytes} bytes {arr.dtype} {arr.shape}")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    hdrs = load_headers()
    base = f"model.layers.{LAYER}.mlp.switch_mlp"

    gate_w = tensor(hdrs, f"{base}.gate_proj.weight")[:EXPERTS]
    up_w = tensor(hdrs, f"{base}.up_proj.weight")[:EXPERTS]
    gate_s = tensor(hdrs, f"{base}.gate_proj.scales")[:EXPERTS]
    up_s = tensor(hdrs, f"{base}.up_proj.scales")[:EXPERTS]
    down_w = tensor(hdrs, f"{base}.down_proj.weight")[:EXPERTS]
    down_s = tensor(hdrs, f"{base}.down_proj.scales")[:EXPERTS]

    e, split, weight_depth = gate_w.shape
    scale_depth = gate_s.shape[2]
    pair_rows = 32
    fused_w = np.concatenate(
        [gate_w.reshape(e, split // pair_rows, pair_rows, weight_depth),
         up_w.reshape(e, split // pair_rows, pair_rows, weight_depth)], axis=2
    ).reshape(e, 2 * split, weight_depth)
    fused_s = np.concatenate(
        [gate_s.reshape(e, split // pair_rows, pair_rows, scale_depth),
         up_s.reshape(e, split // pair_rows, pair_rows, scale_depth)], axis=2
    ).reshape(e, 2 * split, scale_depth)

    rows = 2 * split
    row_blocks = fused_s.reshape(e, rows * 4, 32)
    packed = np.ascontiguousarray(row_blocks[:, packed_bank_order(rows), :])

    write("fused_weight.bin", np.ascontiguousarray(fused_w))
    write("packed_scales.bin", packed)
    write("down_weight.bin", np.ascontiguousarray(down_w))
    write("down_scales.bin", np.ascontiguousarray(down_s))

    # Shared expert down projection: bound unchanged by the fused
    # routed+shared down/residual kernel, which is the primary decode path.
    shared = f"model.layers.{LAYER}.mlp.shared_expert"
    write("shared_down_weight.bin",
          np.ascontiguousarray(tensor(hdrs, f"{shared}.down_proj.weight")))
    write("shared_down_scales.bin",
          np.ascontiguousarray(tensor(hdrs, f"{shared}.down_proj.scales")))

    rng = np.random.default_rng(20260806)
    write("input.bin", fp32_to_bf16(rng.standard_normal(2048) * 0.35))
    write("activated.bin", fp32_to_bf16(rng.standard_normal(EXPERTS * split) * 0.2))
    write("shared_activated.bin", fp32_to_bf16(rng.standard_normal(512) * 0.2))
    write("residual.bin", fp32_to_bf16(rng.standard_normal(2048) * 0.5))
    write("router_weights.bin",
          (rng.random(EXPERTS).astype(np.float32) * 0.4 + 0.05))
    keys = np.full(256, 0xFFFFFFFE, dtype=np.uint32)
    keys[:EXPERTS] = np.arange(EXPERTS, dtype=np.uint32)
    write("router_keys.bin", keys)
    write("indices.bin", np.arange(EXPERTS, dtype=np.uint32))

    # Report the exact pair exceptions the harness must reproduce.
    for label, arr, allowed in (
        ("packed gate/up", packed.reshape(-1), [0, 16]),
        ("shipped down", down_s.reshape(-1), [0]),
    ):
        pairs = arr.reshape(-1, 2)
        bad = np.nonzero(pairs[:, 0] != pairs[:, 1])[0]
        print(f"  {label}: {len(bad)} unequal pairs at {bad[:8].tolist()} "
              f"(allowed {allowed})")
        for p in bad[:8]:
            print(f"      pair {p}: even={pairs[p, 0]} odd={pairs[p, 1]}")


if __name__ == "__main__":
    main()
