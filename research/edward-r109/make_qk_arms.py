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
KARRAY = {"pair": "pipe_ka", "pipeb": "pipe_kb",
          "pipec": "pipe_kc", "piped": "pipe_kd"}

# Twelve extra products per site, i.e. 4x the useful QK MACs: the padding bill an
# 8x8x8 MMA pays for the M=2 decode tile.
FMA4X = "".join("    {v} += {q}[%d] * {k}[%d];\n" % ((d + r) % 4, d)
                for r in (1, 2, 3) for d in range(4))

# Same twelve products, but folded in through a runtime-zero factor so the score
# stays bit-identical. `widx` is a kernel argument, so the compiler cannot prove
# `zero_` is zero and cannot drop or sink the padding work; the softmax path then
# sees exactly the base values. Needed because the score feeds a value-dependent
# `LAGUNA_RESCALE` branch, so a value-changing arm cannot price instructions.
_PAD_PRODUCTS = [((d + r) % 4, d) for r in (1, 2, 3) for d in range(4)]
PAD4X_NEUTRAL = (
    "    {{\n"
    "      const U zero_ = U(widx > 0x3fffffffu);\n"
    "      U pad_ = {q}[%d] * {k}[%d];\n" % _PAD_PRODUCTS[0]
    + "".join("      pad_ += {q}[%d] * {k}[%d];\n" % qd
              for qd in _PAD_PRODUCTS[1:])
    + "      {v} += pad_ * zero_;\n"
    "    }}\n")

ARMS = {
    "qk_free": "    {v} = ({v});",
    "qk_ladder2": ("    {v} += simd_shuffle_xor({v}, 8u);\n"
                   "    {v} += simd_shuffle_xor({v}, 16u);"),
    # Cheapest hardware reduce that exists, and the same with the broadcast a
    # concentrated reduce needs to reach the 32 lanes that own the output dims.
    "qk_quad": "    {v} = quad_sum({v});",
    "qk_quad_bcast": "    {v} = simd_shuffle(quad_sum({v}), 0u);",
    # Correct all-lane butterfly: what an explicit-shuffle or fragment
    # reduction has to fall back on when `simd_sum` is unavailable.
    "qk_ladder5": ("    {v} += simd_shuffle_xor({v}, 1u);\n"
                   "    {v} += simd_shuffle_xor({v}, 2u);\n"
                   "    {v} += simd_shuffle_xor({v}, 4u);\n"
                   "    {v} += simd_shuffle_xor({v}, 8u);\n"
                   "    {v} += simd_shuffle_xor({v}, 16u);"),
    # Mechanism control: one cross-lane broadcast, no reduction, so the
    # lane-dependency cost is separated from the reduction cost.
    "qk_bcast0": "    {v} = simd_shuffle({v}, 0u);",
    # 4x the QK MACs with the reduction untouched, then the same with an
    # MMA-shaped epilogue: together they price the M=2 MMA tile's padding under
    # the assumption that an MMA MAC costs what a scalar FMA MAC costs.
    "qk_fma4x": FMA4X + "    {v} = simd_sum({v});",
    "qk_fma4x_bcast0": FMA4X + "    {v} = simd_shuffle({v}, 0u);",
    # Value-neutral versions of the two arms above. Paired against `null` and
    # `qk_bcast0` respectively, these price the MMA padding without perturbing
    # the softmax path.
    "qk_pad4x": PAD4X_NEUTRAL + "    {v} = simd_sum({v});",
    "qk_pad4x_bcast0": PAD4X_NEUTRAL + "    {v} = simd_shuffle({v}, 0u);",
    # Advisor arm (c): keep every K/V load and every QK MAC, drop the reduction
    # (via the ARMS entry) and the whole softmax/PV epilogue of each pipeline
    # stage (via PV_STRIP), sinking scores and V values into the live
    # accumulators so nothing can be eliminated. Prices the memory system plus
    # bare MAC issue.
    "qk_loadonly": "    {v} = ({v});",
}

# Replaces one pipeline stage's rescale/exp/PV-accumulate block. `pair_max`
# consumes the score so the K loads and QK MACs stay live; `pair_o0` consumes
# the four V registers so the V loads stay live. `pair_sum*` is left at its
# initial 0, which the existing epilogue already handles.
PV_STRIP = ("    pair_max0 = metal::max(pair_max0, {p}_score0);\n"
            "    pair_max1 = metal::max(pair_max1, {p}_score1);\n"
            "    pair_o0[0] += U(pipe_{s}0);\n"
            "    pair_o0[1] += U(pipe_{s}1);\n"
            "    pair_o0[2] += U(pipe_{s}2);\n"
            "    pair_o0[3] += U(pipe_{s}3);")
PV_ARMS = {"qk_loadonly"}
VSUFFIX = {"pair": "va", "pipeb": "vb", "pipec": "vc", "piped": "vd"}


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
                block = block.replace(old, ARMS[arm].format(
                    v=v, q="pair_q%d" % h, k=KARRAY[p]))
                n += 1
        assert n == 8
        if arm in PV_ARMS:
            for p in PREFIXES:
                head = "    U %s_new_max0 = metal::max(pair_max0, %s_score0);" % (p, p)
                tail = ("    pair_o1[3] = pair_o1[3] * %s_factor1 + %s_exp1 * pipe_%s3;"
                        % (p, p, VSUFFIX[p]))
                i, j = block.index(head), block.index(tail) + len(tail)
                block = block[:i] + PV_STRIP.format(p=p, s=VSUFFIX[p]) + block[j:]
        path = os.path.join(OUTDIR, "cand_%s.swift" % arm)
        out = lines[:start] + block.split("\n") + lines[end:]
        open(path, "w").write("\n".join(out))
        print("%s: %d sites in lines %d-%d -> %s"
              % (arm, n, start + 1, end, path))


if __name__ == "__main__":
    main()
