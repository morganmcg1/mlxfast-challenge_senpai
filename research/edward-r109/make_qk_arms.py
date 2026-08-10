#!/usr/bin/env python3
"""R109-D stage 0b: emit timing-probe arms for the sliding kernel QK reduction.

Each arm is a full copy of LagunaRuntimeModel.swift with only the eight hot-loop
QK `simd_sum` sites rewritten, so `research/fern_r100_attn_probe.swift` can
extract and time it. Arms other than the base are deliberately wrong; they exist
only to bound what removing or reformulating the reduction could ever buy.
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LRM = os.path.join(ROOT, "Sources/MLXFastModel/LagunaRuntimeModel.swift")
OUTDIR = os.path.dirname(os.path.abspath(__file__))
PREFIXES = ["pair", "pipeb", "pipec", "piped"]

ARMS = {
    "qk_free": "    {v} = ({v});",
    "qk_ladder2": ("    {v} += simd_shuffle_xor({v}, 8u);\n"
                   "    {v} += simd_shuffle_xor({v}, 16u);"),
    "qk_quad_bcast": "    {v} = simd_shuffle(quad_sum({v}), 0u);",
}


def sliding_span(lines):
    """Line span of the sliding kernel literal.

    The full-attention kernel later in the file reuses the same `pair_score`
    names, so an unbounded replace would silently edit alphonse's kernel too.
    """
    start = next(i for i, l in enumerate(lines)
                 if 'name: "laguna_sliding_fused_attn_ring_v1"' in l)
    end = next(i for i, l in enumerate(lines)
               if i > start and "MLXFast.metalKernel(" in l)
    return start, end


def main():
    lines = open(LRM).read().split("\n")
    start, end = sliding_span(lines)
    for arm in sys.argv[1:] or list(ARMS):
        block, n = "\n".join(lines[start:end]), 0
        for p in PREFIXES:
            for h in (0, 1):
                v = "%s_score%d" % (p, h)
                old = "    %s = simd_sum(%s);" % (v, v)
                assert block.count(old) == 1, "site not unique: %s" % old
                block = block.replace(old, ARMS[arm].format(v=v))
                n += 1
        assert n == 8
        path = os.path.join(OUTDIR, "cand_%s.swift" % arm)
        out = lines[:start] + block.split("\n") + lines[end:]
        open(path, "w").write("\n".join(out))
        print("%s: %d sites in lines %d-%d -> %s"
              % (arm, n, start + 1, end, path))


main()
