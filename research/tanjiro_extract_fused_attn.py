#!/usr/bin/env python3
"""Reconstruct the exact Metal library text MLX generates for the two fused
decode attention kernels, so a standalone tool can compile them and report
pipeline occupancy limits without building the scored worker.

Generation contract (Vendor/mlx-swift/.../common/metal_kernel.cpp):
  utils() preamble  ->  header verbatim  ->  "[[kernel]] void <entry>(\n"
  -> input params -> output params -> builtins -> source -> "\n}\n"
Address space is `constant` when the array has fewer than 8 elements, else
`device`; builtins are emitted only when their name occurs in `source`, in the
order of the table at metal_kernel.cpp:222.

Research-only. Not part of the submitted surface.
"""

import argparse
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME = os.path.join(REPO, "Sources/MLXFastModel/LagunaRuntimeModel.swift")
UTILS = os.path.join(
    REPO, "Vendor/mlx-swift/Source/Cmlx/mlx-generated/utils.cpp")

# (name, metal type, address space) in inputNames order; see the two
# `MLXFast.metalKernel(` call sites and their `precondition` dtype/size checks.
INPUTS = [
    ("raw_queries", "bfloat16_t", "device"),
    ("raw_keys", "bfloat16_t", "device"),
    ("raw_values", "bfloat16_t", "device"),
    ("query_weight", "bfloat16_t", "device"),
    ("key_weight", "bfloat16_t", "device"),
    ("angles", "float", "device"),
    ("k_cache", "bfloat16_t", "device"),
    ("v_cache", "bfloat16_t", "device"),
    ("params", "uint32_t", "constant"),
    ("scale_arr", "float", "constant"),
]
OUTPUTS = [("attended", "bfloat16_t")]
BUILTINS = [
    ("simdgroup_index_in_threadgroup", "uint"),
    ("thread_index_in_simdgroup", "uint"),
    ("threadgroup_position_in_grid", "uint3"),
]


TRIPLE = '"' * 3


def swift_multiline(text, marker, after):
    """Return the body of the Swift multiline literal introduced by `marker`."""
    i = text.index(marker, after)
    start = text.index(TRIPLE, i) + 4  # past the newline after the opener
    end = text.index("\n" + TRIPLE, start)
    return text[start:end], end


def unescape(body):
    """Swift multiline literals only escape backslash and quote here."""
    return body.replace("\\\\", "\\")


def extract(name):
    text = open(RUNTIME).read()
    anchor = text.index('name: "%s"' % name)
    source, after = swift_multiline(text, "source:", anchor)
    header, _ = swift_multiline(text, "header:", after)
    return unescape(source), unescape(header)


def preamble():
    text = open(UTILS).read()
    start = text.index('R"preamble(') + len('R"preamble(')
    return text[start:text.index(')preamble"', start)]


def signature(entry):
    lines = ["[[kernel]] void %s(" % entry]
    parts = []
    slot = 0
    for nm, ty, space in INPUTS:
        parts.append("  const %s %s* %s [[buffer(%d)]]" % (space, ty, nm, slot))
        slot += 1
    for nm, ty in OUTPUTS:
        parts.append("  device %s* %s [[buffer(%d)]]" % (ty, nm, slot))
        slot += 1
    for nm, ty in BUILTINS:
        parts.append("  %s %s [[%s]]" % (ty, nm, nm))
    return lines[0] + "\n" + ",\n".join(parts) + ") {\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(REPO, "research/tanjiro_kernels"))
    ap.add_argument("--kernel", action="append", default=None)
    args = ap.parse_args()
    names = args.kernel or [
        "laguna_sliding_fused_attn_ring_v1",
        "laguna_full_fused_attn_grow_v1",
    ]
    os.makedirs(args.out, exist_ok=True)
    pre = preamble()
    for name in names:
        source, header = extract(name)
        entry = "custom_kernel_" + name
        text = pre + header + signature(entry) + source + "\n}\n"
        path = os.path.join(args.out, name + ".metal")
        with open(path, "w") as fh:
            fh.write(text)
        print("%s -> %s (%d bytes, source %d, header %d)"
              % (entry, path, len(text), len(source), len(header)))


if __name__ == "__main__":
    sys.exit(main())
