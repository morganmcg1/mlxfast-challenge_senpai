"""Research-only generator (not part of the submission surface).

Splices the 4-deep software pipeline into the `laguna_sliding_fused_attn_ring_v1`
main accumulation loop of the scored source. Every slot block is emitted from one
template so the four blocks are textually identical up to their name prefix; that
textual identity is what makes the rewrite bit-exact rather than merely close.

Slot order stays strictly ascending (i, i+BN, i+2BN, i+3BN), which reproduces the
2-deep arm's row order exactly, so the online-softmax reduction order is unchanged.

Usage: python3 research/nezuko_r96_gen4deep.py [depth]
"""

import sys

DEPTH = int(sys.argv[1]) if len(sys.argv) > 1 else 4
SUFFIX = "abcd"[:DEPTH]
PREFIX = {"a": "pair", "b": "pipeb", "c": "pipec", "d": "piped"}


def slot_block(p, k, v):
    out = [f"    U {p}_score0 = 0;", f"    U {p}_score1 = 0;"]
    for j in range(4):
        out.append(f"    {p}_score0 += pair_q0[{j}] * {k}[{j}];")
        out.append(f"    {p}_score1 += pair_q1[{j}] * {k}[{j}];")
    out.append(f"    {p}_score0 = simd_sum({p}_score0);")
    out.append(f"    {p}_score1 = simd_sum({p}_score1);")
    out.append("")
    out.append(f"    U {p}_new_max0 = metal::max(pair_max0, {p}_score0);")
    out.append(f"    U {p}_new_max1 = metal::max(pair_max1, {p}_score1);")
    out.append(f"    U {p}_factor0;")
    out.append(f"    U {p}_factor1;")
    out.append(f"    LAGUNA_RESCALE({p}_factor0, pair_max0 - {p}_new_max0);")
    out.append(f"    LAGUNA_RESCALE({p}_factor1, pair_max1 - {p}_new_max1);")
    out.append(f"    U {p}_exp0 = metal::fast::exp({p}_score0 - {p}_new_max0);")
    out.append(f"    U {p}_exp1 = metal::fast::exp({p}_score1 - {p}_new_max1);")
    out.append("")
    out.append(f"    pair_max0 = {p}_new_max0;")
    out.append(f"    pair_max1 = {p}_new_max1;")
    out.append(f"    pair_sum0 = pair_sum0 * {p}_factor0 + {p}_exp0;")
    out.append(f"    pair_sum1 = pair_sum1 * {p}_factor1 + {p}_exp1;")
    out.append("")
    for j in range(4):
        out.append(
            f"    pair_o0[{j}] = pair_o0[{j}] * {p}_factor0 + {p}_exp0 * {v}{j};")
        out.append(
            f"    pair_o1[{j}] = pair_o1[{j}] * {p}_factor1 + {p}_exp1 * {v}{j};")
    return out


def kptr(s):
    return "pair_keys" if s == "a" else f"pipe_keys_{s}"


def vptr(s):
    return "pair_values" if s == "a" else f"pipe_values_{s}"


def mul(n, unit):
    """Emit `unit` rather than `1 * unit` so depth 2 reproduces the shipped text."""
    return unit if n == 1 else f"{n} * {unit}"


body = ["int i = sg;",
        f"for (; i + {mul(DEPTH - 1, 'BN')} < N; i += {mul(DEPTH, 'BN')}) {{"]
for n, s in enumerate(SUFFIX):
    if n:
        body.append(
            f"    const device bfloat* pipe_keys_{s} = "
            f"pair_keys + {mul(n, 'inner_k_stride')};")
for n, s in enumerate(SUFFIX):
    if n:
        body.append(
            f"    const device bfloat* pipe_values_{s} = "
            f"pair_values + {mul(n, 'inner_v_stride')};")
for n, s in enumerate(SUFFIX):
    rhs = "uint(i)" if n == 0 else f"uint(i + {mul(n, 'BN')})"
    body.append(f"    const bool sub_{s} = {rhs} == widx;")
for s in SUFFIX:
    body.append(f"    U pipe_k{s}[4];")
for s in SUFFIX:
    body.append(f"    T_LOAD_K(pipe_k{s}, sub_{s}, {kptr(s)});")
for s in SUFFIX:
    body.append(f"    bfloat pipe_v{s}0, pipe_v{s}1, pipe_v{s}2, pipe_v{s}3;")
for s in SUFFIX:
    body.append(
        f"    T_LOAD_V(pipe_v{s}0, pipe_v{s}1, pipe_v{s}2, pipe_v{s}3, sub_{s},")
    body.append(f"        {vptr(s)});")
for s in SUFFIX:
    body.append("")
    body += slot_block(PREFIX[s], f"pipe_k{s}", f"pipe_v{s}")
body.append("")
body.append(f"    pair_keys += {mul(DEPTH, 'inner_k_stride')};")
body.append(f"    pair_values += {mul(DEPTH, 'inner_v_stride')};")
body.append("}")

PATH = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
lines = open(PATH).read().split("\n")
start = lines.index("int i = sg;")
assert lines[start + 1] == "for (; i + BN < N; i += 2 * BN) {", lines[start + 1]
end = start + 2
depth = 1
while depth:
    depth += lines[end].count("{") - lines[end].count("}")
    end += 1
assert lines[end - 1] == "}", repr(lines[end - 1])
open(PATH, "w").write("\n".join(lines[:start] + body + lines[end:]))
print(f"sliding loop lines {start + 1}..{end} -> depth {DEPTH}, {len(body)} lines")
