#!/usr/bin/env python3
"""R109-D stage 0a: price the QK reduction of the sliding fused attention kernel.

Extracts `laguna_sliding_fused_attn_ring_v1` out of LagunaRuntimeModel.swift,
emits one .metal file per arm with a matched signature, and censuses the
`__compute` byte size on both architectures via senpai/tools/agx-census-probe.

Every arm below the `base` row changes behaviour. They exist only to attribute
static bytes to the eight hot-loop `simd_sum` sites and to price the formulations
a re-tiled or MMA-shaped QK reduction would have to use instead.

Usage: python3 research/edward-r109/census_qk_reduction.py [OUTDIR]
"""
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LRM = os.path.join(ROOT, "Sources/MLXFastModel/LagunaRuntimeModel.swift")
CENSUS = os.path.join(ROOT, "senpai/tools/agx-census-probe/census.sh")
KERNEL = "laguna_sliding_fused_attn_ring_v1"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/edward_r109_census"

QK_PREFIXES = ["pair", "pipeb", "pipec", "piped"]

PREAMBLE = """#include <metal_stdlib>
#include <metal_simdgroup>
using namespace metal;
typedef bfloat bfloat16_t;

"""

SIGNATURE = """[[kernel]] void custom_kernel_%s(
  const device bfloat16_t* raw_queries [[buffer(0)]],
  const device bfloat16_t* raw_keys [[buffer(1)]],
  const device bfloat16_t* raw_values [[buffer(2)]],
  const device bfloat16_t* query_weight [[buffer(3)]],
  const device bfloat16_t* key_weight [[buffer(4)]],
  const device float* angles [[buffer(5)]],
  const device bfloat16_t* k_cache [[buffer(6)]],
  const device bfloat16_t* v_cache [[buffer(7)]],
  const constant uint32_t* params [[buffer(8)]],
  const constant float* scale_arr [[buffer(9)]],
  device bfloat16_t* attended [[buffer(10)]],
  uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
  uint thread_index_in_simdgroup [[thread_index_in_simdgroup]],
  uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]]) {
""" % KERNEL


def extract_literal(lines, label, start):
    open_i = next(
        i for i in range(start, len(lines)) if lines[i].strip() == '%s: """' % label
    )
    close_i = next(
        i for i in range(open_i + 1, len(lines)) if lines[i].strip() in ('""",', '"""')
    )
    indent = len(lines[close_i]) - len(lines[close_i].lstrip(" "))
    body = [(l[indent:] if l.startswith(" " * indent) else l.lstrip(" "))
            .replace("\\\\", "\\")
            for l in lines[open_i + 1:close_i]]
    return "\n".join(body), close_i


def extract_kernel():
    lines = open(LRM).read().split("\n")
    decl = next(i for i, l in enumerate(lines) if 'name: "%s"' % KERNEL in l)
    src, src_end = extract_literal(lines, "source", decl)
    hdr, _ = extract_literal(lines, "header", src_end)
    return src, hdr


def sub_qk(src, template):
    """Replace each `X_score{0,1} = simd_sum(X_score{0,1});` with a template."""
    out = src
    n = 0
    for prefix in QK_PREFIXES:
        for h in (0, 1):
            v = "%s_score%d" % (prefix, h)
            old = "    %s = simd_sum(%s);" % (v, v)
            assert out.count(old) == 1, "site not unique: %s" % old
            out = out.replace(old, template.format(v=v))
            n += 1
    assert n == 8
    return out


ARMS = [
    # Reference.
    ("base", lambda s: s),
    # Free ceiling: the reduction disappears, MACs and loads stay live.
    ("qk_free", lambda s: sub_qk(s, "    {v} = ({v});")),
    # Five-stage shuffle butterfly: what any hand-rolled full-width reduction,
    # including the tail of an MMA fragment reduction, has to pay.
    ("qk_ladder5", lambda s: sub_qk(
        s,
        "    {v} += simd_shuffle_xor({v}, 1u);\n"
        "    {v} += simd_shuffle_xor({v}, 2u);\n"
        "    {v} += simd_shuffle_xor({v}, 4u);\n"
        "    {v} += simd_shuffle_xor({v}, 8u);\n"
        "    {v} += simd_shuffle_xor({v}, 16u);")),
    # Depth-2 butterfly: the per-site cost of the re-tiled layout in which each
    # lane already owns 32 of the 128 dims, so only masks 8 and 16 remain.
    ("qk_ladder2", lambda s: sub_qk(
        s,
        "    {v} += simd_shuffle_xor({v}, 8u);\n"
        "    {v} += simd_shuffle_xor({v}, 16u);")),
    # Quad reduction: the cheapest hardware reduce that exists, used by a layout
    # where four lanes own the 128 dims of one (row, head).
    ("qk_quad", lambda s: sub_qk(s, "    {v} = quad_sum({v});")),
    # One broadcast after a concentrated reduce: the unavoidable extra step for
    # any layout whose row score does not already land in every lane.
    ("qk_quad_bcast", lambda s: sub_qk(
        s, "    {v} = simd_shuffle(quad_sum({v}), 0u);")),
    # One bare broadcast: the exact shape of an MMA epilogue, where the row
    # score already exists in one lane of the accumulator fragment and only has
    # to reach the 32 lanes that own the output dims.
    ("qk_bcast0", lambda s: sub_qk(s, "    {v} = simd_shuffle({v}, 0u);")),
]


def census(path):
    r = subprocess.run(["bash", CENSUS, path], capture_output=True, text=True)
    if r.returncode != 0:
        return {"error": (r.stderr.strip() or r.stdout.strip())[:300]}
    out = {}
    for line in r.stdout.strip().split("\n")[1:]:
        f = line.split("\t")
        if len(f) == 3:
            out[f[0]] = f[2]
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    src, hdr = extract_kernel()
    rows = []
    for name, fn in ARMS:
        path = os.path.join(OUT, "%s.metal" % name)
        with open(path, "w") as f:
            f.write(PREAMBLE + hdr + "\n" + SIGNATURE + fn(src) + "\n}\n")
        rows.append((name, census(path)))

    base = rows[0][1]
    print("arm\tg16s\tg17s\tdelta_g16s\tdelta_g17s\tinstr_est_g16s\tper_site")
    for name, c in rows:
        if "error" in c:
            print("%s\tCOMPILE_FAIL\t%s" % (name, c["error"]))
            continue
        g16, g17 = c.get("applegpu_g16s", "NA"), c.get("applegpu_g17s", "NA")
        d16 = int(g16) - int(base["applegpu_g16s"])
        d17 = int(g17) - int(base["applegpu_g17s"])
        print("%s\t%s\t%s\t%+d\t%+d\t%+.1f\t%+.2f"
              % (name, g16, g17, d16, d17, d16 / 8.0, d16 / 8.0 / 8.0))


main()
