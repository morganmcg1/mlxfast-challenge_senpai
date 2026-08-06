#!/usr/bin/env python3
"""Dump raw BF16 attention q/k/v projection weights for the PR #72 step-4a control.

Writes one flat little-endian uint16 blob per (layer, projection) plus a manifest
that the Swift harness (research/nezuko_attention_scale_control.swift) reads.

Usage:
    python3 research/nezuko_attn_dump.py [--layers N]
"""

import argparse
import glob
import json
import os
import re
import struct

OUT = "/tmp/nezuko_g32/attn"
PROJS = ("q_proj", "k_proj", "v_proj")
GENERATED = "Vendor/mlx-swift/Source/Cmlx/mlx-generated"

# jit_kernels.cpp:925-936 -- get_quantized_kernel concatenates exactly these
# four generated preambles and then the template definition produced by
# kernels.h:404-424 from the kname built at quantized.cpp:2433-2442.
JIT_PARTS = ("utils.cpp", "gemm.cpp", "quantized_utils.cpp", "fp_quantized.cpp")
KNAME = "nvfp4_quantize_bfloat16_t_gs_16_b_4"
TEMPLATE_DEF = (
    f'\ntemplate [[host_name("{KNAME}")]] [[kernel]] '
    "decltype(fp_quantize<bfloat16_t, 16, 4>) fp_quantize<bfloat16_t, 16, 4>;\n"
)


def emit_jit_source():
    parts = []
    for name in JIT_PARTS:
        text = open(os.path.join(GENERATED, name)).read()
        match = re.search(r'R"preamble\(\n(.*)\)preamble";', text, re.S)
        assert match, name
        parts.append(match.group(1))
    out = os.path.join(os.path.dirname(OUT), "fpq_source.metal")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        fh.write("".join(parts) + TEMPLATE_DEF)
    print(f"jit source -> {out}")


def load_header(path):
    with open(path, "rb") as fh:
        n = struct.unpack("<Q", fh.read(8))[0]
        return json.loads(fh.read(n)), 8 + n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layers", type=int, default=40)
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    emit_jit_source()
    index = {}
    for path in sorted(glob.glob("weights/model-*-of-*.safetensors")):
        hdr, base = load_header(path)
        for key, meta in hdr.items():
            if key == "__metadata__":
                continue
            index[key] = (path, base, meta)

    manifest = []
    for layer in range(args.layers):
        for proj in PROJS:
            key = f"model.layers.{layer}.self_attn.{proj}.weight"
            path, base, meta = index[key]
            assert meta["dtype"] == "BF16", (key, meta["dtype"])
            start, end = meta["data_offsets"]
            out = os.path.join(OUT, f"L{layer}_{proj}.bin")
            with open(path, "rb") as fh:
                fh.seek(base + start)
                data = fh.read(end - start)
            with open(out, "wb") as fh:
                fh.write(data)
            manifest.append(
                {"layer": layer, "proj": proj, "shape": meta["shape"], "file": out}
            )
            print(f"{key} {meta['shape']} -> {out} ({len(data)} B)")

    with open(os.path.join(OUT, "manifest.json"), "w") as fh:
        json.dump(manifest, fh)
    print(f"manifest: {len(manifest)} dispatches")


if __name__ == "__main__":
    main()
